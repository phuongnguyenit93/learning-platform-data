# Optimizing OS Configuration and File Descriptor Limits

A workload can suffer connection errors, fail to open files, stop accepting new requests, or experience higher latency even when CPU and RAM still have spare capacity. An often-overlooked cause is that the process has exhausted its **file descriptors (FDs)** or hit an operating system resource limit. On Linux, network sockets, files, pipes, devices, and many I/O objects are accessed by processes through file descriptors. If limits are too low, the application may return `Too many open files`, fail to open new connections, or fail to write logs.

OS tuning must start from workload metrics. Raising FD limits, changing kernel parameters, or tuning network queues helps only after identifying the corresponding bottleneck. Blanket configurations applied across the board can increase kernel memory usage, mask resource leaks, or make systems harder to recover under rising load.

## 1. What Is a File Descriptor?

On Unix/Linux, a file descriptor is a non-negative integer that a process uses to reference an open I/O object. Standard default FDs typically include:

- `0`: standard input (`stdin`).
- `1`: standard output (`stdout`).
- `2`: standard error (`stderr`).

When an application opens a file, creates a socket, pipe, event descriptor, or certain other kernel objects, the OS allocates an FD to the process. For example, an API server may use FDs for its listening socket, each client connection, log files, configuration files, database connections, inter-process pipes, and temporary files.

An FD is a process-level reference to an open file description or associated kernel object. Multiple FDs can point to the same open file description via `dup()` or after `fork()`. Thus, the FD count does not necessarily equal the number of unique physical files open.

For servers handling high concurrency, sockets typically make up a large share of FDs. If a request opens additional files or connects to multiple downstream services, FD usage can scale with concurrency. A process with plenty of CPU remaining can still refuse new connections if it runs out of FDs.

## 2. Distinguishing Per-Process vs. System-Wide FD Limits

Linux enforces multiple layers of FD-related limits. First distinguish per-process limits from system-wide file handle limits.

| Limit | Scope | Common Inspection Method |
|---|---|---|
| `RLIMIT_NOFILE` | Per process | `ulimit -n`, `prlimit`, `/proc/PID/limits` |
| `fs.nr_open` | Maximum ceiling on FDs a single process can allocate | `/proc/sys/fs/nr_open` |
| `fs.file-max` | System-wide allocated file handle limit | `/proc/sys/fs/file-max` |
| `file-nr` | Current kernel file handle statistics | `/proc/sys/fs/file-nr` |

`RLIMIT_NOFILE` has two values:

- **Soft limit:** the limit currently enforced on the process. A process can raise its soft limit up to the hard limit if permitted.
- **Hard limit:** the maximum ceiling an unprivileged process is permitted to raise its soft limit to.

`fs.nr_open` sets the kernel ceiling for per-process FD limits. Setting `RLIMIT_NOFILE` higher than `fs.nr_open` does not grant the ability to open more FDs. `fs.file-max` is the system-wide file handle limit; raising a single service's `RLIMIT_NOFILE` does not automatically raise this system limit.

A process can hit `RLIMIT_NOFILE` while the system still has abundant file handles. Conversely, many processes can collectively consume handles and push the system to `file-max` even though no individual process reached its own limit.

## 3. Recognizing File Descriptor Exhaustion Errors

Applications can manifest FD exhaustion in several ways:

- Linux returns `EMFILE` (`Too many open files`) when a process hits its own FD limit.
- Linux returns `ENFILE` when the system-wide file handle limit is reached.
- The server cannot accept new sockets or open connections to databases/caches.
- The application fails to open log files, temporary files, or config files at runtime.
- Logs show failures in `accept4`, `socket`, `open`, `pipe`, or `epoll_create`.
- Open connection count grows continuously without dropping proportionally after requests finish.

Do not infer root cause from an application-layer error message alone. For example, `Connection refused` usually indicates no process is listening or a firewall actively rejected the connection; it is not synonymous with FD exhaustion. Correlate `errno`, runtime logs, current FD counts, and actual limits.

## 4. Inspecting Active FDs of a Process

On Linux, each process has a `/proc/PID/fd` directory containing symbolic links to the objects it currently holds open. The number of entries in this directory is the number of FDs held by the process at that moment.

Examples:

```bash
# View process limits
cat /proc/1234/limits | grep -i 'open files'

# Count currently open FDs
find /proc/1234/fd -maxdepth 1 -type l | wc -l

# List open objects
sudo ls -l /proc/1234/fd | head -n 40

# View FD types and sockets
sudo lsof -nP -p 1234
```

Replace `1234` with the actual PID. `lsof` can generate huge output for connection-heavy processes; filter by PID or object type. Reading `/proc` may also be restricted by permissions, namespaces, or security policies.

To count FDs by type:

```bash
sudo lsof -nP -p 1234 | awk 'NR>1 {count[$5]++} END {for (type in count) print type, count[type]}'
```

The command above groups by the type column in `lsof` output; column formatting may vary by version and locale. For precise investigation, use `lsof` field-output options or analyze `/proc/PID/fd` alongside socket tables.

To identify which processes hold the most FDs, inspect multiple PIDs over a controlled window. Do not take only a single snapshot; record counts over time to spot monotonically rising trends.

## 5. Checking Current FD Limits

In a shell:

```bash
ulimit -Sn
ulimit -Hn
ulimit -n
```

`-S` displays the soft limit, `-H` displays the hard limit. `ulimit -n` usually displays the current shell's soft limit. These values reflect only that shell and child processes spawned from it; they are not necessarily the limits of a service running under systemd, a container runtime, or another session.

Inspect the process directly:

```bash
cat /proc/1234/limits
prlimit --pid 1234 --nofile
```

This is a more reliable source when diagnosing a specific process. If `ulimit -n` in your terminal shows a large number while `/proc/PID/limits` of the service shows a small number, the service was launched in a context with different limits.

## 6. Checking System-Wide File Handle Limits

The kernel exposes metrics under `/proc/sys/fs`:

```bash
cat /proc/sys/fs/file-max
cat /proc/sys/fs/file-nr
cat /proc/sys/fs/nr_open
```

- `file-max` is the system-wide file handle cap.
- `file-nr` reports allocated file handles, free slots in the pool, and the maximum limit. On modern Linux kernels, the middle field is typically 0 because file handles are dynamically allocated; consult kernel documentation for your running version.
- `nr_open` is the maximum per-process FD ceiling.

If `file-nr` approaches `file-max` and kernel logs record `ENFILE` errors, inspect total FDs across all processes, socket counts, mounts, and system activity. Do not raise `file-max` just because the number looks high; file handles and kernel structures still consume memory. Identify which workload drives the demand and check for leaks.

## 7. Estimating FD Demand for a Workload

FD limits should be chosen based on concurrently open resources at peak load plus reasonable headroom. An API server may need:

- FDs for listeners and active client sockets.
- FDs for outbound connections to databases, caches, message brokers, and HTTP dependencies.
- Log files, config files, certificates, and temporary files.
- Pipes, eventfds, epoll, inotify, or runtime descriptors.
- FDs opened by monitoring agents, profilers, or libraries inside the same process.

An estimation model can be written as:

\[
FD_{peak} \approx FD_{base} + C_{in} + C_{out} + F_{runtime} + F_{temporary}
\]

Where:

- `FD_base` is fixed FDs opened at service startup.
- `C_in` is concurrent inbound connections held directly by the process.
- `C_out` is concurrent outbound connections.
- `F_runtime` is FDs for runtime, logs, pipes, event loops, and agents.
- `F_temporary` is peak demand for temporary files or short-lived operations.

This is an approximate model. A proxy or load balancer may hold multiple sockets per request; a connection pool reuses sockets so FDs do not grow linearly with total requests; a library may open many files simultaneously. Measure actual FDs under representative load and add headroom for bursts, rollouts, and recovery scenarios.

For example, a service has 80 baseline FDs, up to 1,500 inbound connections, 250 outbound connections, and 120 runtime/temporary FDs. Estimated demand is 1,950 FDs. With 50% headroom, testing can start around 3,000 FDs. Final values must be based on measurements and platform limits; do not treat this example as a default for every API.

## 8. Adjusting FD Limits for systemd Services

For Linux services managed by systemd, configure limits directly in the unit file rather than changing terminal `ulimit` values.

Example unit file:

```ini
[Unit]
Description=Orders API
After=network-online.target
Wants=network-online.target

[Service]
User=orders
Group=orders
ExecStart=/usr/bin/java -jar /srv/orders/orders-api.jar
Restart=on-failure
RestartSec=5s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

`LimitNOFILE=` sets `RLIMIT_NOFILE` for the service process. `65536` is an illustrative example only; replace it with your sized value. After editing the unit:

```bash
sudo systemctl daemon-reload
sudo systemctl restart orders-api.service
sudo systemctl show orders-api.service -p LimitNOFILE
```

Restarting recreates the process with the new limit. Verify directly via `/proc/PID/limits` of the new PID. `systemctl show` reports the configuration systemd applies, while `/proc/PID/limits` reflects the actual running process limit.

Defaults for the service manager can be set via `DefaultLimitNOFILE=` in systemd manager configuration, though changing defaults affects many services and requires scope review. For a specific workload, per-unit limits are usually easier to control and test.

## 9. Role of PAM Limits and `ulimit`

`/etc/security/limits.conf` or files in `/etc/security/limits.d/` can set user/group limits for PAM-managed sessions via `pam_limits`. For example:

```text
orders soft nofile 32768
orders hard nofile 65536
```

This is useful for login sessions or applications launched through PAM. However, systemd system services do not generally read limits from `limits.conf` the way a login shell does. Do not edit this file and assume a service automatically picked up the new value.

Running `ulimit -n 65536` in a shell changes limits only for that shell and child processes spawned afterward, within the hard limit. It does not alter limits of already running processes, nor system-wide limits. After any change, verify the exact PID and exact service.

## 10. Tuning Related Kernel Limits

Several `sysctl` parameters relate to FDs or network capacity:

| Parameter | Role | When to Consider |
|---|---|---|
| `fs.file-max` | System-wide file handle limit | Evidence shows the system hits the cap and demand is legitimate |
| `fs.nr_open` | Per-process `RLIMIT_NOFILE` ceiling | A service legitimately needs a hard limit higher than current kernel ceiling |
| `net.core.somaxconn` | Listen socket backlog ceiling | Signs of listen queue overflow and the app can accept faster |
| `net.ipv4.ip_local_port_range` | Ephemeral source port range for IPv4 connections | Host opens many outbound connections and exhausts source ports |
| `net.core.netdev_max_backlog` | Packet queue when kernel receives faster than processing speed | Softnet backlog drops observed after checking CPU/driver/NIC |

Do not raise all parameters at once. Change one value at a time, record a baseline, measure before/after, and keep rollback capability. Network limits may also depend on kernel version, drivers, instance types, and cloud provider configurations.

### Viewing and Changing `sysctl`

Read current values:

```bash
sysctl fs.file-max
sysctl fs.nr_open
sysctl net.core.somaxconn
sysctl net.ipv4.ip_local_port_range
```

Apply a temporary change until reboot or overwrite:

```bash
sudo sysctl -w fs.file-max=2097152
```

The value above is illustrative, not a universal recommendation. To persist across reboots, manage settings in a dedicated file under `/etc/sysctl.d/`, for example:

```text
# /etc/sysctl.d/90-compute-workload.conf
fs.file-max = 2097152
```

Load configuration:

```bash
sudo sysctl --system
```

In production, `sysctl` changes should be managed via configuration management or image pipelines, with review and testing. Avoid manually editing many parameters directly on individual hosts, as fleet configurations easily drift.

## 11. Optimizing Backlogs and Network Connections

For TCP servers, multiple queues participate in connection establishment. `net.core.somaxconn` caps the listen backlog permitted by the kernel; applications also pass a backlog argument to `listen()`. The effective value depends on both. The SYN queue and accept queue serve different roles; raising `somaxconn` alone cannot fix an application that accepts slowly or an overloaded CPU.

When suspecting backlog issues:

```bash
ss -lnt
netstat -s | grep -Ei 'listen|overflow|drop'
```

Depending on the system, `ss -lnt` shows queued connections and the listen socket backlog limit. Look for listen overflow/drop counters in TCP statistics. If the backlog fills frequently, inspect worker counts, accept callback handling, CPU, scheduler, and burst traffic before raising limits.

Another issue is ephemeral port exhaustion when a host creates many outbound connections to the same destination. `TIME_WAIT` and short-lived connections can tie up source ports over a window. Inspect:

```bash
cat /proc/sys/net/ipv4/ip_local_port_range
ss -s
ss -tan state time-wait | wc -l
```

Effective remedies usually include reusing connections via connection pools/keep-alive, reducing short-lived connections, tuning concurrency, and reviewing port ranges after checking routing/NAT. Do not blindly enable legacy TCP options or shorten `TIME_WAIT` timers; they can break connections or compromise protocol safety.

## 12. Configuring File Descriptors in Containers

Linux containers still rely on host kernel and process/cgroup limits. `ulimit` inside a container is usually set by the runtime at container creation. Raising limits inside a debug shell after the application has started does not alter the main process's limits.

With Docker, `nofile` can be set at container creation, for example:

```bash
docker run --ulimit nofile=65536:65536 my-orders-api:1.0
```

This is illustrative syntax; verify Docker daemon, runtime, and host hard limits before use. In Docker Compose, equivalent settings can be declared under `ulimits` depending on Compose version.

In Kubernetes, configuring `RLIMIT_NOFILE` depends on the container runtime and node configuration. The Kubernetes API does not expose a portable `nofile` field on Pod specs the way it does for CPU/memory requests/limits. If adjustments are required, manage them via supported runtime/node configuration or image entrypoint mechanisms and verify from inside the process. Never assume `ulimit` in a debug shell matches the limits of PID 1 inside the container.

## 13. Windows: Handles Are Not Identical to Unix File Descriptors

Windows uses **handles** to reference files, sockets, processes, threads, events, and many other kernel objects. The concept serves a similar resource-management role, yet is not the same mechanism as POSIX file descriptors. Windows has no `ulimit -n` or `RLIMIT_NOFILE` in the Linux sense.

To inspect process handle counts, use PowerShell:

```powershell
Get-Process |
  Sort-Object Handles -Descending |
  Select-Object -First 20 ProcessName, Id, Handles, WorkingSet64
```

`Handles` is the total handles held by a process; it is not specifically open sockets or files. Sysinternals Handle or Process Explorer can identify the types of objects a process holds. For sockets, inspect `Get-NetTCPConnection`, network counters, and application logs.

If a Windows application uses a C runtime with POSIX-style interfaces, the runtime may have its own file stream limit such as `_setmaxstdio`; this is not an OS-wide handle limit. Diagnostics must distinguish handle leaks, socket exhaustion, file sharing/locking, and runtime limits.

## 14. Finding and Fixing FD Leaks

An FD leak happens when an application opens files/sockets and fails to close them after completion. FD counts grow steadily over time until hitting the limit. Common causes:

- Failing to close files or streams on error/exception paths.
- Creating a new HTTP client or database connection per request instead of pooling.
- Sockets left unclosed on timeouts or canceled requests.
- Watchers, pipes, temp files, or descriptors leaked inside native libraries.
- Threads or background tasks holding references to resources longer than expected.
- Retries opening new connections without releasing failed ones.

Leak investigation workflow:

1. Monitor FD count by PID under steady load.
2. Categorize growing FDs: sockets, files, pipes, eventfds, inotify, or other types.
3. Correlate against concurrent requests, connection pools, and log files.
4. Audit success, exception, timeout, and cancellation code paths for proper resource closure.
5. Use profilers, runtime diagnostics, or syscall inspection tools in a test environment.
6. Run a soak test after fixing and confirm FD counts stabilize as load rises and falls.

In Java, prefer try-with-resources for `InputStream`, `OutputStream`, `Socket`, `FileChannel`, and other closeable resources. Use HTTP clients and database pools with explicit lifecycle management. In native code, verify every exit path after `open()`, `socket()`, `accept()`, or `pipe()` calls `close()` appropriately.

Raising limits can help a service survive larger bursts, but if FD counts grow unboundedly, it only postpones the next outage. Fix leaks before treating a limit increase as a long-term fix.

## 15. Other OS Settings to Tune Based on Metrics

Beyond FDs, several OS parameters affect compute performance. Change them only when metrics or load tests prove the corresponding bottleneck:

| Area | Parameter / Capability | Signals to Investigate | Risk of Misconfiguration |
|---|---|---|---|
| CPU/scheduler | CPU quotas, affinity, cgroup CPU weights | CPU throttling, long run queues, rising latency | Reduces fairness or unnecessarily caps CPU |
| Memory | `vm.swappiness`, dirty pages/writeback, cgroup memory | Swap pressure, writeback stalls, memory PSI | Increases I/O or triggers earlier OOM if headroom shrinks |
| Filesystem | Mount options, inode capacity, file handles | I/O latency, inode exhaustion, metadata workloads | Alters durability or semantics |
| Network | Backlogs, ephemeral port ranges, queues, NIC limits | Listen overflows, port exhaustion, packet drops | Increases kernel memory or masks app bottlenecks |
| I/O scheduler | Scheduler and queue depth per block device type | I/O wait and storage latency | Hurts latency on other workloads |

On cloud VMs, certain hardware or scheduler controls sit outside the guest OS's authority. Do not try to change CPU frequency governors, interrupt affinity, or driver parameters if the platform does not support them or the provider advises against it. Start from guest-observable metrics and published instance/service limits.

### Example: `vm.swappiness`

`vm.swappiness` influences the kernel's preference for swapping anonymous memory versus reclaiming page cache. It is not the percentage of RAM that will be swapped, and no single value is optimal for every application. For latency-sensitive workloads, observe swap I/O and PSI before tuning; disabling swap or setting an ultra-low value can cause OOMs to occur sooner.

### Example: Writeback

Dirty page parameters control when and how aggressively the kernel flushes dirty data to storage. Raising thresholds can coalesce more writes, yet also creates large writeback bursts and increases data-loss risk during power loss if durability is not guaranteed by the application. Rely on storage latency, dirty pages, and writeback metrics; do not tune solely to inflate sequential benchmark numbers.

## 16. Controlled Tuning Workflow

A sound tuning workflow proves a change improves the workload without degrading other parts of the system:

1. **Set targets:** define SLOs such as request p95/p99 latency, throughput, error rate, and resource bounds.
2. **Measure baseline:** collect FD counts, OOM/ENFILE/EMFILE counts, CPU, memory, I/O, network, backlog, and connection metrics.
3. **Locate the bottleneck:** identify which process or kernel subsystem is hitting a limit.
4. **Estimate demand:** calculate peak FDs/concurrency/queues and needed headroom.
5. **Change a small scope:** prefer service-specific settings before host-wide changes.
6. **Run load tests:** use the same workload, data, and duration before and after.
7. **Monitor side effects:** kernel memory, latency, errors, socket states, logs, and recovery behavior.
8. **Roll out gradually:** canary first, then expand if results pass.
9. **Document and enable rollback:** manage configuration as code, retain previous values, and keep a rollback procedure.

Do not tune based on a single short benchmark. Run steady-state, burst, soak tests, and restart/scale scenarios to surface leaks or limits that emerge only over time.

## 17. Example: API Server Exhausting FDs Under Load

A Linux API server runs under systemd. Under normal load, the process holds roughly 4,000 FDs. During a traffic surge, logs show `accept4: Too many open files`; CPU is around 45% and plenty of RAM remains.

Investigation workflow:

1. Find the service PID and inspect `/proc/PID/limits` for soft/hard `Max open files`.
2. Count `/proc/PID/fd` and inspect FD types using `lsof`.
3. Check sockets: counts of `ESTABLISHED`, `CLOSE_WAIT`, `TIME_WAIT`, and listener backlog.
4. Correlate FD count with inbound connections, outbound pools, and request load.
5. Check application logs for unclosed sockets/files or retries opening new connections.
6. Verify systemd limits, `fs.nr_open`, and `fs.file-max`.
7. If legitimate peak demand exceeds the soft limit, increase `LimitNOFILE` per sizing and test; if FDs grow monotonically without dropping, fix leaks/pooling first.
8. Re-run burst and soak tests to confirm FD count stabilizes, zero `EMFILE`/`ENFILE` errors occur, and latency meets SLOs.

For example, if the process holds 4,000 FDs under normal load and measures 18,000 FDs at peak, it may need a limit above 18,000 plus headroom. `65,536` is commonly used in some environments, though it is not a mandatory standard. Consider instance limits, co-located services on the host, and kernel memory before deciding.

## 18. Common Mistakes

- **Only raising `ulimit -n` over SSH:** running systemd services do not inherit that value. Set limits properly in the unit or runtime.
- **Confusing `RLIMIT_NOFILE` with `fs.file-max`:** one is per-process, the other is system-wide. Check both.
- **Raising FDs into the millions without sizing:** the kernel uses memory for structures and workloads may retain more resources. Measure demand and headroom.
- **Raising `somaxconn` to fix every connection error:** backlog tuning cannot fix FD leaks, overloaded CPUs, or slow application accepts.
- **Looking only at current FD count:** a single snapshot misses gradual leaks. Track over time and load.
- **Adding swap or lowering swappiness by rule of thumb:** can worsen latency or trigger earlier OOMs. Tune based on working set and SLOs.
- **Changing multiple `sysctl` settings at once:** makes it hard to identify which change caused the effect. Change in isolated steps and re-measure.
- **Ignoring container runtimes:** limits inside a container process may differ from the host shell. Inspect the real PID and runtime config.
- **Confusing Windows handles with Unix FDs:** Windows does not use `RLIMIT_NOFILE`; diagnose using handle counts, sockets, and corresponding runtime limits.

## 19. OS and FD Optimization Checklist

- [ ] Measured process FD counts at normal load, peak load, and after load drops.
- [ ] Identified soft/hard `RLIMIT_NOFILE` of the exact PID.
- [ ] Checked `fs.nr_open`, `fs.file-max`, and `/proc/sys/fs/file-nr`.
- [ ] Categorized FDs across sockets, files, pipes, and runtime descriptors.
- [ ] Ruled out FD leaks and verified resources close on all error paths.
- [ ] Sized limits for peak concurrency plus headroom.
- [ ] Verified systemd/container services receive updated limits after restart/redeploy.
- [ ] Tuned backlogs, ephemeral ports, and network queues only with supporting metrics.
- [ ] Managed `sysctl` changes with versioned configuration and rollback capability.
- [ ] Tested burst, steady-state, and soak scenarios after changes.
- [ ] Monitored kernel memory, latency, throughput, errors, and OOMs post-tuning.
- [ ] On Windows, distinguished handle counts, sockets, and runtime limits instead of applying Linux `ulimit` concepts.

Optimizing OS configuration and file descriptor limits helps workloads utilize resources reliably as concurrency scales. By understanding limit layers, measuring the right process, fixing FD leaks, and tuning `sysctl` based on evidence, operations teams can prevent `Too many open files` errors, reduce I/O bottlenecks, and keep compute performance within expected bounds.
