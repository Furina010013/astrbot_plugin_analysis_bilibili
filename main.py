import os
import re
import asyncio
import httpx
import datetime
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain, Image, Video


@register("bilibili_analysis", "Furina", "B站解析下载", "1.3.1")
class BiliParserPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config if config is not None else {}

        # 1. 获取持久化目录 (返回 Path 对象)
        self.data_dir = StarTools.get_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com"
        }
        # 复用 Client
        self.client = httpx.AsyncClient(headers=self.headers, timeout=20.0, follow_redirects=True)
        self.max_download_size = 100 * 1024 * 1024

    @filter.regex(r"(BV[0-9A-Za-z]{10})|(b23\.tv/[0-9A-Za-z]+)")
    async def on_bili_link(self, event: AstrMessageEvent):
        msg_text = event.message_str

        bvid = await self.extract_bvid(msg_text)
        if not bvid: return

        video_data = await self.fetch_video_info(bvid)
        if not video_data:
            yield event.plain_result("❌ 无法获取视频详情。")
            return

        v = video_data.get('data', {})
        cid = v.get('cid')
        duration = v.get('duration', 0)
        pic_url = v.get('pic')

        desc = (v.get('desc') or '无简介').strip()
        if len(desc) > 150: desc = desc[:150] + "..."

        yield event.plain_result(self.build_detail_md(v, desc))

        try:
            threshold = int(self.config.get("video_duration_threshold", 300))
        except:
            threshold = 300

        # 处理媒体发送
        if duration > threshold:
            async for res in self.handle_cover_send(event, bvid, pic_url, threshold):
                yield res
        else:
            async for res in self.handle_video_send(event, bvid, cid):
                yield res

    async def extract_bvid(self, text: str) -> Optional[str]:
        if "b23.tv" in text:
            match = re.search(r"https?://b23\.tv/[0-9A-Za-z]+", text)
            if match:
                try:
                    # 使用 GET 请求跟随跳转，因为 HEAD 有时会被 B 站拒绝
                    resp = await self.client.get(match.group(0), timeout=5.0)
                    final_url = str(resp.url)
                    bv_match = re.search(r"video/(BV[0-9A-Za-z]{10})", final_url)
                    if bv_match: return bv_match.group(1)
                except Exception as e:
                    logger.error(f"短链解析异常: {e}")

        bv_match = re.search(r"BV[0-9A-Za-z]{10}", text)
        return bv_match.group(0) if bv_match else None

    async def fetch_video_info(self, bvid: str) -> Optional[Dict[str, Any]]:
        url = "https://api.bilibili.com/x/web-interface/view"
        try:
            resp = await self.client.get(url, params={"bvid": bvid})
            data = resp.json()
            if data.get('code') == 0: return data
        except Exception as e:
            logger.error(f"详情请求异常: {e}")
        return None

    async def handle_video_send(self, event: AstrMessageEvent, bvid: str, cid: int):
        if not cid: return
        api_url = "https://api.bilibili.com/x/player/playurl"
        params = {"bvid": bvid, "cid": cid, "qn": 64, "platform": "html5", "high_quality": 1}

        try:
            resp = await self.client.get(api_url, params=params)
            video_url = resp.json().get('data', {}).get('durl', [{}])[0].get('url')

            if video_url:
                yield event.plain_result("🚀 正在下载视频文件...")
                path = await self.download_file(video_url, f"{bvid}.mp4")
                if path:
                    yield event.chain_result([Video.fromFileSystem(str(path))])
                    asyncio.create_task(self.delayed_delete(path))
                else:
                    yield event.plain_result("❌ 视频下载失败（可能文件过大）。")
        except Exception as e:
            logger.error(f"视频发送异常: {e}")

    async def handle_cover_send(self, event: AstrMessageEvent, bvid: str, pic_url: str, threshold: int):
        if not pic_url: return
        path = await self.download_file(pic_url, f"{bvid}_cover.jpg")
        if path:
            yield event.chain_result([
                Image.fromFileSystem(str(path)),
                Plain(f"\n⚠️ 视频超过 {threshold}s，仅展示封面。")
            ])
            asyncio.create_task(self.delayed_delete(path))

    async def download_file(self, url: str, suffix: str) -> Optional[Path]:
        filename = f"{uuid.uuid4().hex}_{suffix}"
        path = self.data_dir / filename
        try:
            async with self.client.stream("GET", url) as resp:
                if resp.status_code != 200: return None
                total_size = int(resp.headers.get("Content-Length", 0))
                if total_size > self.max_download_size: return None

                with open(path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
                return path
        except Exception as e:
            logger.error(f"下载异常: {e}")
            if path.exists(): path.unlink()
        return None

    def build_detail_md(self, v: dict, desc: str) -> str:
        stat = v.get('stat', {})
        owner = v.get('owner', {})
        pubdate = datetime.datetime.fromtimestamp(v.get('pubdate', 0)).strftime('%Y-%m-%d %H:%M')
        return (
            f"### {v.get('title')}\n"
            f"👤 **UP主**: {owner.get('name')}  |  🕒 **发布**: {pubdate}\n"
            f"--- \n"
            f"| 播放 | 点赞 | 投币 |\n"
            f"| :--- | :--- | :--- |\n"
            f"| {stat.get('view', 0)} | {stat.get('like', 0)} | {stat.get('coin', 0)} |\n\n"
            f"> **视频简介**：\n> {desc}"
        )

    async def delayed_delete(self, path: Path):
        await asyncio.sleep(60)
        try:
            if path.exists(): path.unlink()
        except:
            pass