# 四类真实任务的路由对照 / Routing comparison on four real tasks

Each task started with the same source material and a fresh GPT-6.1 Sol lead at medium effort. The solo arm required one author. The automatic arm could delegate and chose one author in all four cases. Two further runs paired the lead with one GPT-6 Luna reader at low effort. The directory lookup used the actual site location as its check. The three other tasks used anonymized answers and criteria fixed before scoring. Each populated cell represents one run.

同一题使用相同输入，主笔均为新上下文中的 GPT-6.1 Sol，思考档位 medium。单人组由主笔独立完成。自动组自行判断是否分工，四题都选了单人。另在两道技术题上各补一次指定分工，由一名 GPT-6 Luna（low）协助核查。目录题用实际位置验收，其余三题将答卷匿名后按预设标准评分。表中每个有值的单元格对应一次运行。

| Task / 任务类别 | Solo / 单人 | Automatic / 自动 | Specified split / 指定分工 |
|---|---|---|---|
| Documentation lookup / 文档目录定位 | 1/1 · 18.1 s · 100,750 tokens (99,328 cached) | 1/1 · 19.8 s · 100,836 tokens (99,328 cached) | — |
| Tool comparison / 工具比较 | 6/8 · 120.6 s · 548,367 tokens (481,664 cached) | 7/8 · 135.2 s · 465,725 tokens (411,648 cached) | 7/8 · 202.6 s · 1,250,072 tokens (1,178,752 cached) |
| Graphics explanation / 画面原理说明 | 7.5/8 · 128.9 s · 339,923 tokens (302,720 cached) | 8/8 · 126.0 s · 357,943 tokens (285,056 cached) | 7/8 · 212.4 s · 1,190,571 tokens (1,128,320 cached) |
| Interview guide / 面试提纲 | 8/8 · 95.1 s · 69,257 tokens (65,792 cached) | 7.5/8 · 87.3 s · 69,136 tokens (65,920 cached) | — |

Each cell shows quality, elapsed seconds, and total tokens. The lead's elapsed time includes waiting for the reader. For the split runs, token totals include both participants. Cached input is included once. A dash marks an untested combination. All tasks produced text from read-only inputs.

每格依次列出质量分、耗时和总 Token。耗时从主笔开始算到交卷，包含等待子 Agent 的时间。指定分工组的 Token 包含两人的用量，其中缓存输入只计一次。横线表示未测。四题均为读取材料后交付文本。

On tool selection, the extra reader brought the score to 7/8, level with the automatic arm. On the graphics explanation, the split scored 7/8 against the automatic arm's 8/8. Both split runs took longer and used more tokens than either one-author run on the same task. A single run per cell cannot establish a general advantage. Token counts come from local logs and measure usage rather than price.

工具选型题加人后得到 7/8，与自动组持平。画面原理题加人后得到 7/8，自动组为 8/8。两次加人都比同题两份单人答卷花得更久、消耗更多 Token。各组只跑了一次，无法据此估计普遍收益。Token 取自本地用量记录，账单金额未测。
