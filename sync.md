# 本地 ↔ 服务器 同步

仓库：`https://github.com/YttriumP/SeaIce.git`
服务器：`Server`（`~/.ssh/config` 别名），工作区 `/home/gst/lcx`

---

## 0. 先做一次连通性检查（在服务器上）

```bash
git --version
curl -sS -m 8 -o /dev/null -w "%{http_code}\n" https://github.com
```

- 输出 `200` 或 `301` → 走 **方案 A**
- 超时、`000`、`Could not resolve host` → 走 **方案 B**

> 国内不少高性能集群的登录节点没有外网，或者只放行内网源。这一步不测，后面全是白费。

---

## 方案 A：服务器能直连 GitHub（首选）

### A1. 公开仓库

```bash
cd /home/gst/lcx
git clone https://github.com/YttriumP/SeaIce.git .
```

`.` 表示克隆到当前目录，这样仓库根就是 `/home/gst/lcx`，与 `AGENTS.md` 里的路径约定一致。
如果目录非空，先 `git clone <url> ~/Seaice_tmp`，再把内容移过来。

### A2. 私有仓库（推荐 deploy key，只读）

服务器上生成一把**专用密钥**：

```bash
ssh-keygen -t ed25519 -C "server-seoice" -f ~/.ssh/id_ed25519_github -N ""
cat ~/.ssh/id_ed25519_github.pub
```

复制输出的公钥 → GitHub 仓库 **Settings → Deploy keys → Add deploy key**
（标题随便写，**不要**勾 `Allow write access`）→ 粘贴保存。

配置 SSH 走这把钥匙：

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

测试并克隆：

```bash
ssh -T git@github.com          # 看到 "successfully authenticated" 即可
cd /home/gst/lcx
git clone git@github.com:YttriumP/SeaIce.git .
```

> deploy key 是**只读**的，服务器上推不上去——这是故意的。服务器只 `pull`，不 `push`。

---

## 方案 B：服务器连不上 GitHub（本地做中转）

思路：本地同时推到 GitHub 和服务器上的一个**裸仓库**，服务器从裸仓库拉。

### B0. 服务器上已经有 clone（常见：GitHub 时通时不通）

**不要重新 clone**，会丢掉服务器上的提交。改成"把裸库接到现有 clone 上"：

```bash
# 服务器
cd ~/lcx/SeaIce
git log --oneline -5              # 先记住服务器上有哪些提交
mkdir -p ~/repos
git init --bare ~/repos/SeaIce.git
git remote rename origin github   # 保留 GitHub 的 remote，改名备查
git remote add origin ~/repos/SeaIce.git
git push -u origin main           # 用服务器现有提交给裸库"播种"
```

```powershell
# 本地
cd "C:\Users\31504\Documents\deepseek-harness\default-workspace\seaice-teleconnection"
git remote add server Server:repos/SeaIce.git
git fetch server
git log --oneline --graph --all -20
```

看 `--graph` 的输出决定下一步：

| 情况 | 处理 |
|---|---|
| 本地没有服务器没有的提交 | `git merge --ff-only server/main` |
| 两边各有一些提交 | `git pull --rebase server main`，再 `git push server main` |
| 只有本地有新提交 | 直接 `git push server main` |

> 一旦这么做，**真源就变成服务器上的裸仓库 `~/repos/SeaIce.git`**，GitHub 降级为"能连的时候推一次"的备份。
> 之后别两边各自提交又都不推，否则每次都要 rebase。

### B1. 服务器上建裸仓库（只需一次）

```bash
mkdir -p ~/repos
git init --bare ~/repos/SeaIce.git
```

### B2. 本地加一个 remote 并推送

```powershell
cd "C:\Users\31504\Documents\deepseek-harness\default-workspace\seaice-teleconnection"
git remote add server Server:repos/SeaIce.git
git push server main
```

`Server` 是 ssh 别名，git 会直接走 SSH，不需要额外配置。

### B3. 服务器上克隆到工作区

```bash
cd /home/gst/lcx
git clone ~/repos/SeaIce.git .
```

### B4. 日常推送

```powershell
git push origin main   # GitHub
git push server main   # 服务器
```

想一条命令解决：

```powershell
git remote set-url --add --push origin https://github.com/YttriumP/SeaIce.git
git remote set-url --add --push origin Server:repos/SeaIce.git
git push                       # 一次推两个地方
```

注意：这样 `origin` 会有两个 push URL，`git remote -v` 能看到。

---

## 日常节奏

| 在哪 | 做什么 |
|---|---|
| **本地** | 改文档 / 改代码 → `git add -A` → `git commit -m "..."` → `git push` |
| **服务器** | `cd /home/gst/lcx && git pull` → `python3 scripts/xx.py` 或 `bash run.sh` |
| **铁律** | **服务器上不直接改代码**。要改就回本地改，再推下来 |

> 服务器上直接改，下次 `git pull` 就会冲突，这是新手 90% 的 git 痛苦来源。

## 产物不会冲突

`out/`、`figs/`、`logs/`、`data/` 都已在 `.gitignore` 里，服务器上跑出来的图和 CSV
不会被 `pull` 覆盖，也不会被误提交。要备份产物，用 `scp`/VSCode 单独拷，不要塞进 git。

---

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `fatal: detected dubious ownership` | 集群 home 是 NFS，属主与当前用户不一致 | `git config --global --add safe.directory /home/gst/lcx` |
| `git: command not found` | 服务器没装 git | `module load git` 或找管理员；或用方案 B 的 rsync 变体 |
| `Permission denied (publickey)` | deploy key 没配对 | `ssh -vT git@github.com` 看用了哪把钥匙 |
| `! [rejected] ... (fetch first)` | 两边都有新提交 | `git pull --rebase` 后再 push |
| `pull` 报本地文件会被覆盖 | 服务器上改过文件 | `git status` 看改动，确认不需要后 `git checkout -- .` |
| 克隆到非空目录失败 | `git clone` 要求空目录 | 先克隆到临时目录，再 `mv` 过来 |
