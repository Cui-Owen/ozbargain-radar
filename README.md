# OzBargain Radar

[![Checks](https://github.com/Cui-Owen/ozbargain-radar/actions/workflows/check.yml/badge.svg)](https://github.com/Cui-Owen/ozbargain-radar/actions/workflows/check.yml)
[![Release](https://img.shields.io/github/v/release/Cui-Owen/ozbargain-radar)](https://github.com/Cui-Owen/ozbargain-radar/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

给 AI 助手用的澳洲优惠雷达。默认广泛收录 **OzBargain 最新优惠，保留低票新帖，在对话中按品类分表，从重点到小众完整介绍**；热门帖作为补充，单品支持价格线索和买家评论。Coles／Woolworths 半价仅在本次请求明确询问时查询，独立展示。

Python 3.9+，抓取脚本只用标准库；无 API Key、付费接口、数据库或后台服务。安装和更新另需 Git。支持本地运行的 Codex、Claude Code、Antigravity；其他支持 `SKILL.md` 的助手可手动安装。

## 安装

直接把下面这句话发给 AI 助手：

```text
请从 https://github.com/Cui-Owen/ozbargain-radar 安装这个 skill 到当前助手的全局技能目录，使用仓库自带的 install.py，保留已有本地修改。
```

或在终端运行（macOS / Linux）：

```bash
curl -fsSL https://raw.githubusercontent.com/Cui-Owen/ozbargain-radar/main/install.py -o /tmp/ozbargain-radar-install.py
python3 /tmp/ozbargain-radar-install.py --agent codex
```

Claude Code 将最后一项改为 `--agent claude`；Antigravity 改为 `--agent antigravity`。Windows 可下载 [install.py](https://raw.githubusercontent.com/Cui-Owen/ozbargain-radar/main/install.py)，使用 `py install.py --agent codex`。

| 助手 | 默认安装位置 |
| --- | --- |
| Codex | `~/.agents/skills/ozbargain-radar` |
| Claude Code | `~/.claude/skills/ozbargain-radar` |
| Antigravity | `~/.gemini/config/skills/ozbargain-radar` |

自定义路径：`python3 install.py --dest /你的技能目录/ozbargain-radar`。已有同名手动安装目录时，先移动旧目录或指定新路径。安装后在新会话中使用；未出现时重启助手。

## 使用

在 Codex 中可显式写 `$ozbargain-radar`；其他助手直接说技能名称和需求：

```text
用 ozbargain-radar 广泛查找今天的澳洲优惠，在对话里按品类分表，从重点到冷门小众完整介绍商品、折扣、到手价和门槛，附链接。
找最近的电脑配件和游戏优惠，分别看热门和最新帖子。
看看 Coles 和 Woolworths 的半价帖子，能确定规格的商品给出单位价格。
分析这个 OzBargain 链接：价格是否值得买，评论里有哪些规格和配送问题？
```

也可在安装目录直接执行：

```bash
python3 scripts/fetch_deals.py --latest --exclude-supermarket-half-price
python3 scripts/fetch_deals.py --feed computing,electronics --latest --exclude-supermarket-half-price
python3 scripts/fetch_deals.py --all-categories --latest --exclude-supermarket-half-price
python3 scripts/fetch_groceries.py --half-price-only --limit 0
python3 scripts/fetch_comments.py https://www.ozbargain.com.au/node/977982 --limit 25
```

`fetch_deals.py` 默认无票数门槛、无条数截断；`--limit 0` 读取每个 RSS 当前全部条目，正整数限制每个 feed。指定时间窗超出 RSS 时由助手补读公开列表分页。输出为 JSON，各脚本支持 `--help`。支持品类及判断规则见 [SKILL.md](SKILL.md)。

RSS 只覆盖当前返回条目；超市结果来自社区投稿。`ATL` 是帖子关键词，独立历史记录未核对时 `history_verified=false`。评论读取当前页且过滤短评，不自动翻页。访问失败由助手补读公开页面或浏览器。

## 表格与来源绑定

多条优惠表格由 `scripts/render_report.py` 从抓取快照生成，商品身份与链接绑定同一记录。表格默认展示中文商品名和中文用途介绍，原标题留在内部快照。模型每批处理 15 条，翻译须绑定完整原标题，保留型号及技术规格；脚本检查新增数字、型号／技术单位遗漏。价格与条件使用同条原文引用。脚本拒绝未知节点、重复／遗漏、节点链接不匹配、快照变化及无来源引用。最终表格直接贴在对话，不用工作文件替代正文。

使用流程与 annotation 字段见 [表格绑定说明](references/report-binding.md)。本地校验检查数据对应关系，不检查实时网页状态；中文释义仍需逐批核对。

## 更新与版本

重新运行安装命令即可更新到 `main`，或让助手执行：

```text
请更新已安装的 ozbargain-radar，使用它的 install.py，并保留本地修改。
```

Codex 终端更新：

```bash
python3 ~/.agents/skills/ozbargain-radar/install.py --agent codex
```

固定版本：安装或更新时加 `--ref v1.0.6`。回到持续更新版加 `--ref main`。安装器使用 Git 快进合并；发现本地修改或不同仓库时停止，不覆盖文件。

不使用 Git 时，从 [Releases](https://github.com/Cui-Owen/ozbargain-radar/releases) 下载 ZIP，解压成 `ozbargain-radar` 文件夹放入技能目录；升级时替换该文件夹。

卸载：删除对应助手技能目录中的 `ozbargain-radar` 文件夹。

## 开发与发布

```bash
git clone https://github.com/Cui-Owen/ozbargain-radar.git
cd ozbargain-radar
python3 -m unittest discover -s tests -v
```

修改后提交 PR。报告问题时附命令、公开来源 URL、Python 版本和实际结果，入口为 [Issues](https://github.com/Cui-Owen/ozbargain-radar/issues)。

维护者发布：更新 `VERSION`、`CHANGELOG.md`，提交后推送同版本标签（如 `v1.0.6`）。Actions 校验、测试并创建带 ZIP 和 SHA256 的 GitHub Release。`main` 是日常更新通道，Release 标签供固定版本使用。

基于 [Agent Skills](https://agentskills.io/) 格式；Codex 的技能发现路径见 [官方文档](https://developers.openai.com/codex/skills/)。

MIT © Cui-Owen。独立社区项目。
