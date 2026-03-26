# astrbot_plugin_analysis_bilibili

这是一个基于 **AstrBot** 框架的 B 站视频解析插件。它能够自动识别聊天中的 B 站链接（包括短链接和 BV 号），提取视频元数据，并根据视频时长智能选择下载视频文件或发送视频封面。

## 🌟 功能特性

* **自动识别**：支持识别 `BVxxxxxxxxxx` 和 `b23.tv` 短链接。
* **丰富元数据**：以 Markdown 格式展示视频标题、UP 主、发布时间、播放量、点赞、投币等信息。
* **智能下载策略**：
    * **短视频**：如果视频时长在设定阈值内，自动下载并发送 `.mp4` 视频文件。
    * **长视频**：如果视频超过阈值，仅发送视频封面图，避免占用过大带宽和存储。
* **可视化配置**：支持在 AstrBot 管理面板直接修改下载阈值。

## 🛠️ 安装方法

下载安装包,在astrbot插件市场安装

##使用示例
<img width="1080" height="5168" alt="Image_1774496007464_56" src="https://github.com/user-attachments/assets/d3c35692-551b-4b13-9f6d-d542001e1ee4" />
<img width="2400" height="3687" alt="3b632a30970586cee2cd7553c769eeec" src="https://github.com/user-attachments/assets/780ad8b8-e1e2-40d6-b232-c16236347b09" />
<img width="1078" height="278" alt="PixPin_2026-03-26_11-35-19" src="https://github.com/user-attachments/assets/f7129d22-57d2-414f-945e-d4d42d5532d2" />

## ⚙️ 插件配置

你可以在 AstrBot 管理面板的“插件配置”中找到本项目，进行以下设置：

| 配置项                     | 类型       | 默认值 | 说明                                           |
| :------------------------- | :--------- | :----- | :--------------------------------------------- |
| `video_duration_threshold` | 整数 (int) | 300    | 视频下载的时长阈值（秒）。超过此值则只发封面。 |

### AI 生成声明
> ⚠️ **注意**：本项目的部分核心代码（包括 B 站 API 解析逻辑、异步文件下载处理、AstrBot 配置注入逻辑等）由 AI (Gemini) 辅助生成。
