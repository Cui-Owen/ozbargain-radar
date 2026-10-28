# 表格与抓取记录绑定

全站／多条优惠表格必须经过 `scripts/render_report.py`。工作 JSON 与 Markdown 是内部中间文件，最终表格仍直接贴在对话中。

## 固定输入

1. 将抓取命令的真实 JSON 输出保存到任务 `work/`，保留全站、分类和补读分页各自的文件。不要从聊天记忆重建 JSON。补读正文时，先将实际读到的文本及来源保存进同一节点记录，再冻结快照；不能把模型总结当成抓取正文。
2. 用 `prepare` 合并，按节点去重。同一节点标题或链接冲突时停止，重读该帖确定身份后重建快照；票数变化保留第一份完整记录，不交叉拼字段。

```bash
python3 scripts/render_report.py prepare work/latest.json work/categories.json --out work/bound-report
```

输出 `snapshot.json`、每批默认 15 条的 `batch-001.source.json` 与对应 `batch-001.annotations.json`。输出目录必须是新目录，以免混入旧扫描的批次。15 条是处理批次，不是收录数量上限；所有批次都要处理。

## 按批写中文介绍

一次只读取一个 `.source.json`，填写对应 `.annotations.json`，完成后再读取下一批。快照和 `.source.json` 不允许模型修改。不要一次把数百条加载后凭记忆重写。

每个 annotation 必须保留原样的 `node_id`、`source_hash`，只填写：

- `group`：中文品类。
- `priority`：0～3，重点到小众；结合实际优惠价值，不能只按票数排序。
- `title_zh`：`{"text": "中文商品名与规格", "quote": "完整原标题"}`。只翻译原商品，不换商品、不补型号或卖点。品牌无明确中文名时保留原名；混合字母数字的型号和技术单位保留原写法，如 P110M、10W-40、5L、256GB；普通 50-Count 可译为 50 粒。价格与促销机制留在专用列，不放进中文商品名。
- `intro`：`{"text": "中文用途说明", "quote": "同条原文中的连续片段"}`。用中文简洁解释有来源的用途，不能加入原文没有的功能或适用人群。
- `offer_quote`：同条原文中同时保留金额和适用语境的连续片段。不能仅截取返现、月付、首月、以旧换新或最低规格中的数字冒充到手价。缺失时留空，表中显示“见原标题”。
- `conditions_quote`：同条原文中与成交相关的连续片段，缺失时留空。标题已写的资格、运费、套餐等条件不能因缺少独立条件字段而省略。
- `note`：与 `intro` 相同的 text/quote 对象，补充有依据的优惠解释；无新增信息时两个字段都留空。

`quote` 必须逐字存在于同条的 `title`、`description_snippet`、`snippet`、`description` 或 `body`。需要更完整的条件就先补读正文、重建快照。`intro.text` 与 `note.text` 不得写链接、金额或数字折扣；价格与折扣直接引用原文。原文证据匹配不能证明中文翻译正确：每批逐行检查中文商品类别、品牌、型号、用途和条件是否对应原文，不能用校验通过代替语义核对。

## 生成、校验、原样发送

处理完全部 annotation 批次后执行：

```bash
python3 scripts/render_report.py render --snapshot work/bound-report/snapshot.json --annotations work/bound-report/batch-*.annotations.json --output work/bound-report/report.md
python3 scripts/render_report.py verify --snapshot work/bound-report/snapshot.json --annotations work/bound-report/batch-*.annotations.json --output work/bound-report/report.md
```

脚本检查未知节点、重复／遗漏、快照 hash、节点与链接、证据原文、字段白名单，并拒绝注释自带链接或价格。中文商品名须绑定完整原标题，包含中文，不得引入原文没有的数字，并保留混合字母数字的型号／技术单位。此检查不能识别所有误译；每批仍要核对商品类别、品牌、规格和用途。原标题保留在快照，表格默认显示中文商品名与介绍，链接仍取同一原始记录。输出按品类和优先级分表，每表默认最多 15 行，完整总数不变。

新建批次必须填写 `title_zh`；不能删除此字段绕过中文标题校验。脚本兼容旧注释文件：旧文件没有该字段时仍显示原标题，避免旧报告无法重现。

逐表读取生成结果并原样贴入当前对话，不能再次“润色”、改价、替换商品名、重写链接或重新手工组表。解释需要修改时修改对应 annotation，再重新生成和校验。不要把工作文件当交付附件，也不要让用户靠打开文件才能看全。

`verify` 只核对本地表格与抓取记录，不发起网络请求，不确认网页此刻可用。用户要求现时可访问性、或发现可疑／失效链接时，另行读取原帖：HTTP 200 还需核对商品身份；403／429 表示受限，不等于 404。按技能的浏览器备用路径确认页面。不得据本地校验声称“所有链接 100% 有效”。
