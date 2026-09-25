# 配置和验证 ALE 下载任务

网站已经部署在 https://data-download-task.vercel.app 。七个任务的
`task.yaml` 中，`params.site_url` 均指向这个地址，不需要再配置 Vercel。

每个 `tasks/<任务名>/` 都可以单独交给 ALE：

- `task.yaml`：网站地址、资源、超时和网络策略。
- `instruction.md`：给 agent 的要求。
- `image/`：安装 Chromium 和 Playwright。
- `setup/`：启动可见浏览器，设置下载目录 `/home/user/output/`。
- `oracle/`：通过网页入口完成下载的参考解法。
- `verify/`：根据文件名、大小和 SHA-256 判断下载结果。

## 不需要模型密钥的验证

以下命令在相邻的 `ale/` 目录执行。当前仓库的七个任务使用生产域名：

```bash
uv run ale lint ../data-download-task/tasks
uv run ale validate ../data-download-task/tasks/corgis-airlines \
  --runs-dir ../data-download-task/reports/runs
# 验证全部七个任务
uv run ale validate ../data-download-task/tasks \
  --runs-dir ../data-download-task/reports/runs
```

`lint` 只检查任务结构。`validate` 会实际创建容器，分别运行空操作和参考解法。
合格条件是空操作的所有评分项为 0、参考解法的所有评分项为 1，且评分项名称相同。
结果保存在 `reports/runs/validate-*/validation.json`；同一目录下保留每轮的日志、
验证结果和运行记录。完整运行目录被 Git 忽略，需另行保存；公开摘要放在 `reports/`。

截至 2026-09-25，七个任务已通过本地同源网站的完整容器验证，运行 ID 为
`validate-4028e976`。当前版本的 CORGIS 单任务已直接通过生产域名验证；
完整生产域名验证因本机到部分 Vercel 边缘地址连接超时尚未通过。
具体结果见 [`ale-validation.json`](../reports/ale-validation.json)。

这些命令需要本机可用的 ALE 桌面基础镜像。公开 GHCR 镜像拉取曾返回 401，
本机已通过 ALE 源码构建基础镜像；来源和构建调整见
[`ale-base-provenance.json`](../reports/ale-base-provenance.json)。其他机器需要
自行取得或构建基础镜像，GitHub 仓库不包含 Docker 镜像。
本机复现七任务已通过的运行时，先把 Flask 绑定到 Docker 网桥地址，
再使用 `scripts/build_tasks.py --base-url http://网桥地址:8765 --output .local/tasks`
生成临时任务副本，对 `.local/tasks` 执行 `ale validate`。详见
[`handoff.md`](handoff.md)。临时任务地址不能当作生产地址提交。

## 用 Codex 订阅运行真实 GUI agent

这台机器的普通 Codex CLI 已登录 ChatGPT，但 ALE 根据自己的
[`subscription-auth` 指南](https://github.com/AgentsLastExam/ale/blob/04b0599928317191ca6557847a456a70ab2d0438/docs/guides/subscription-auth.md)
只读取 ALE checkout 专用的登录文件。你需要在 `ale/` 目录执行一次：

```bash
CODEX_HOME="$PWD/.ale/auth/codex-cli" codex login
chmod 0600 .ale/auth/codex-cli/auth.json
CODEX_HOME="$PWD/.ale/auth/codex-cli" codex login status
```

登录会打开浏览器；完成后告诉我“已登录”，不要发送登录文件或令牌。
普通 `~/.codex` 登录不应复制到这里。之后在同一目录运行：

```bash
uv run ale run ../data-download-task/tasks/corgis-airlines \
  --agent codex-cli --auth subscription --model gpt-5.6-luna \
  --set 'agent.mcp_servers=[{ builtin = "cua-desktop" }]' \
  --runs-dir ../data-download-task/reports/runs
```

`cua-desktop` 给 agent 提供屏幕截图、点击和键盘输入。任务指令要求使用
可见浏览器的网页入口下载。运行后需同时检查评分、`trajectory.json` 中的
桌面工具调用、截图和 `/home/user/output/` 中的文件；只看文件哈希不足以证明
agent 使用了 GUI。上面的命令和模型名称已按本机 ALE `04b0599` 的配置格式
检查，但目前尚未完成专用登录，因此尚未运行真实模型回合。

## 使用其他模型服务

本次审阅的 ALE `04b0599` 的 `computer-use` harness 使用 Anthropic messages
兼容的 computer-use 服务。确定服务地址和支持的模型后，在主机环境设置密钥，执行：

```bash
uv run ale run ../data-download-task/tasks/corgis-airlines \
  --agent computer-use --model MODEL_NAME \
  --base-url MODEL_ENDPOINT --api-key-env MODEL_API_KEY \
  --runs-dir ../data-download-task/reports/runs
```

`MODEL_API_KEY` 是环境变量名；不要将密钥写进网站、任务或 Git。
`--base-url` 是模型服务地址，不是 Vercel 网站地址。
检查评分、下载产物以及 `trajectory.json` 中的截图和点击动作。
参考解法通过不能证明模型会通过，文件哈希也不能单独证明下载全程只使用 GUI。

## 合并给导师之前

保留任务提交号、ALE 提交号、镜像标识、网站地址、数据哈希和实际运行记录。
目前任务使用 `network.mode: open`；原因和限制见
[`handoff.md`](handoff.md)。正式纳入 benchmark 前还需要确认网络策略，
与后续分析任务合并后也应重新运行验证。
