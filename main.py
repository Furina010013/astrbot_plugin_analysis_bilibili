import os
import re
import asyncio
import httpx
import datetime
from pathlib import Path  # 确保导入了 Path
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain, Image, Video
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@register("bilibili_analysis", "YourName", "B站解析下载-逻辑优化版", "1.2.2")
class BiliParserPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)

        # 1. 确保 config 不为 None
        self.config = config if config is not None else {}

        # 2. 【核心修复】：使用 Path() 包装字符串，确保可以使用 / 拼接路径
        # 或者使用 os.path.join 这种更传统但稳健的方式
        base_path = Path(get_astrbot_data_path())
        self.temp_dir = base_path / "plugin_data" / "bilibili_analysis"

        # 3. 确保目录存在
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com"
        }

    @filter.regex(r"(BV[0-9A-Za-z]{10})|(b23\.tv/[0-9A-Za-z]+)")
    async def on_bili_link(self, event: AstrMessageEvent):
        msg_text = event.message_str
        bvid = None

        # 1. 提取 BVID
        if "b23.tv" in msg_text:
            short_url_match = re.search(r"https?://b23\.tv/[0-9A-Za-z]+", msg_text)
            if short_url_match:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    try:
                        resp = await client.get(short_url_match.group(0), headers=self.headers, timeout=10)
                        bvid_match = re.search(r"video/(BV[0-9A-Za-z]{10})", str(resp.url))
                        if bvid_match: bvid = bvid_match.group(1)
                    except:
                        pass

        if not bvid:
            bv_match = re.search(r"BV[0-9A-Za-z]{10}", msg_text)
            if bv_match: bvid = bv_match.group(0)

        if not bvid: return

        # 2. 获取数据
        video_data = await self.fetch_video_info(bvid)
        if not video_data or 'data' not in video_data:
            yield event.plain_result("❌ 无法获取视频详情")
            return

        v = video_data['data']
        cid = v['cid']
        title = v['title']
        duration = v['duration']
        stat = v['stat']
        owner = v['owner']
        pic_url = v['pic']
        pubdate = datetime.datetime.fromtimestamp(v['pubdate']).strftime('%Y-%m-%d %H:%M')

        desc = v.get('desc', '无简介').strip()
        if len(desc) > 150: desc = desc[:150] + "..."

        # 3. 发送介绍
        detail_md = (
            f"### {title}\n"
            f"👤 **UP主**: {owner['name']}  |  🕒 **发布**: {pubdate}\n"
            f"--- \n"
            f"| 播放 | 点赞 | 投币 | 收藏 |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| {stat['view']} | {stat['like']} | {stat['coin']} | {stat['favorite']} |\n\n"
            f"| 弹幕 | 评论 | 分享 | 时长 |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| {stat['danmaku']} | {stat['reply']} | {stat['share']} | {duration // 60}:{duration % 60:02d} |\n\n"
            f"> **视频简介**：\n"
            f"> {desc}"
        )
        yield event.plain_result(detail_md)

        # 4. 读取配置阈值
        threshold = self.config.get("video_duration_threshold", 300)

        if duration > threshold:
            img_path = await self.download_file(pic_url, f"{bvid}_cover.jpg")
            if img_path:
                yield event.chain_result([
                    Image.fromFileSystem(img_path),
                    Plain(f"\n⚠️ 视频时长超过 {threshold} 秒，仅展示封面。")
                ])
                asyncio.create_task(self.delayed_delete(img_path))
            else:
                yield event.plain_result("❌ 封面图下载失败。")
        else:
            video_url = await self.fetch_video_url(bvid, cid)
            if video_url:
                yield event.plain_result("🚀 视频较短，正在下载文件...")
                video_path = await self.download_file(video_url, f"{bvid}.mp4")
                if video_path:
                    yield event.chain_result([Video.fromFileSystem(video_path)])
                    asyncio.create_task(self.delayed_delete(video_path))
                else:
                    yield event.plain_result("❌ 视频下载失败。")
            else:
                yield event.plain_result("❌ 无法解析视频直链。")

    # --- 工具方法 ---

    async def fetch_video_info(self, bvid: str):
        url = "https://api.bilibili.com/x/web-interface/view"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params={"bvid": bvid}, headers=self.headers)
                return resp.json()
            except:
                return None

    async def fetch_video_url(self, bvid: str, cid: int):
        url = "https://api.bilibili.com/x/player/playurl"
        params = {"bvid": bvid, "cid": cid, "qn": 64, "platform": "html5", "high_quality": 1}
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params=params, headers=self.headers)
                return resp.json()['data']['durl'][0]['url']
            except:
                return None

    async def download_file(self, url: str, filename: str):
        # 确保这里也是路径对象操作
        path = self.temp_dir / filename
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=120) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code == 200:
                        with open(path, "wb") as f:
                            async for chunk in resp.aiter_bytes():
                                f.write(chunk)
                        return str(path)
        except Exception as e:
            logger.error(f"下载失败: {e}")
        return None

    async def delayed_delete(self, path: str):
        await asyncio.sleep(60)
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"清理临时文件: {path}")
            except Exception as e:
                logger.error(f"清理失败: {e}")