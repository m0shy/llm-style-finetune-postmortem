# 训练反复崩溃的真正原因：Windows TDR（显卡驱动超时复位）

> 结论先行：**不是我的代码、不是显存不够、不是配置错。**
> 这台机器的显卡驱动**默认的 TDR 超时是 2 秒**，而 4bit 7B 模型在 8GB 笔记本显卡上跑长序列，
> 单次 GPU 派发很容易超过 2 秒。一超时，Windows 就把显卡驱动复位一次，
> CUDA 上下文随之销毁，训练/推理进程当场报错退出。

---

## 一、证据：系统日志里的 `nvlddmkm 事件 153`

我从 Windows 系统日志（`System` 通道，来源 `nvlddmkm`）拉出了近 24 小时的全部记录：
十余条 `153` 事件（部分伴随成组出现的 `13` 事件），时间上横跨训练启动前后——
既有与训练完全无关的时段，也有 v3 训练期间、v5 第 0 步即崩与单探针（固定的对照测试输入）连续崩溃的时段。

**两个关键事实：**

1. **这些事件早在训练启动之前就开始了**，并非训练引入的。
   也就是说，显卡驱动反复复位是**机器本身早已存在的不稳定**，不是我把显卡跑坏的。
2. **每次我遇到的崩溃，时间点都精确对应一条 153 事件**。
   这解释了为什么报错五花八门（`illegal memory access` / `device-side assert` /
   `CUBLAS_STATUS_EXECUTION_FAILED` / LoRA `k_proj` / `logits scatter`）：
   **驱动一被复位，CUDA 上下文就废了，之后任意一个算子都会报错，报错位置是随机的。**

## 二、当前的 TDR 设置

查注册表 `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers`：

```
TdrDelay    = (未设置，用系统默认)   →  默认 2 秒
TdrDdiDelay = (未设置，用系统默认)
TdrLevel    = (未设置，用系统默认)
```

显卡驱动版本：（案例中的具体驱动版本已脱敏）。

**重启后至今，`nvlddmkm 153` 一条都没有，驱动目前是干净的。**

## 三、修法：把 TDR 超时从 2 秒放宽到 10 秒

这是 Windows 上跑深度学习负载的**标准做法**，改两个 DWORD 值即可，随时可逆。

**用管理员身份打开 PowerShell**，执行：

```powershell
$p = 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers'
New-ItemProperty -Path $p -Name TdrDelay    -PropertyType DWord -Value 10 -Force
New-ItemProperty -Path $p -Name TdrDdiDelay -PropertyType DWord -Value 10 -Force
```

然后**重启一次**生效。（TdrDelay 是"内核等待 GPU 响应的秒数"，TdrDdiDelay 是显示驱动初始化的等待秒数。）

想撤销就把值删掉：

```powershell
Remove-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' -Name TdrDelay, TdrDdiDelay
```

**副作用**：如果真的遇到显卡硬故障，系统会多等 10 秒才复位，
表现为"画面卡住约 10 秒然后恢复"，而不是立刻闪一下。对跑训练的机器来说这个代价可以接受。

## 四、顺带说明：我最初报告的"重启后立刻卡死"

这大概率**不是显卡的问题**。同一份系统日志里，开机后出现的错误是：
`DolbyLaboratories.DolbyAccess` 没有在要求时间内向 DCOM 注册（超时）；
**迅雷下载基础服务启动失败**，等待连接超时 30000 毫秒。

这两个都是**开机自启服务卡住**的典型表现，跟显卡无关。
如果开机经常卡一会儿，可以在「任务管理器 → 启动」里把迅雷相关的自启项关掉试试。

## 五、对后续训练的影响

- **不修 TDR**：训练仍可能随机崩。好消息是 `v8_watchdog.py`（未随仓库发布）能自动从最近检查点续训，
  但每次崩都白跑一段，一夜可能反复好几轮。
- **修了 TDR**：这类崩溃应当显著减少甚至消失（把 2 秒放宽到 10 秒，覆盖了绝大多数派发耗时）。

## 六、另外两个由这次排查顺带确认的事

1. **磁盘与内存都不是瓶颈**：C 盘剩 490G、D 盘剩 536G；内存 31.6G 总量、可用 20.1G。
2. **`nvidia-smi` 报 `Failed to initialize NVML: Unknown Error`**
   而 `torch.cuda.is_available()` 仍为 True。这台机器一直有这个现象（此前记录过），
   属已知无害，**不能拿 `nvidia-smi` 当显卡好坏的判据**。
