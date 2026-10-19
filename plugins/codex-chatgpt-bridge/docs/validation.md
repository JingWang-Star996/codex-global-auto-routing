# 验证范围 / Validation scope

0.1.1 是文本/代码桥接的实验版本。公共测试覆盖幂等冲突、未知发送禁止重试、只读恢复、进程互斥、状态持久化、正文分页与SHA、MCP握手、任务匹配和完成判定。打包测试另外验证安装准备阶段不会依赖作者路径或调用Codex。

作者本机于2026-10-19完成一次Pro独立复核和一次Work数学计算往返。Pro发送后曾保守停止，随后从原对话恢复结果，没有重发。Work返回的质数个数1229、总和5736396由本地独立算法核对一致；网页显示计算动作，未独立读取云端工具原始stdout。MCP服务初始化、7个工具发现及浏览器连接也曾在本机验证。

这些是有范围的作者报告，不是公开可复现的所有账号保证。私人聊天URL、授权记录、完整回复、Token统计、备份ID和本机绝对路径未发布。CI只运行离线测试，不登录ChatGPT，不消耗网页额度，也不能替代真实网页联调。

The author reports two local live round trips on the date above, with narrow evidence boundaries. Public CI runs offline only; it does not authenticate with ChatGPT, send prompts, verify account availability or prove runtime route enforcement, model identity, billing, isolation, or performance improvement.
