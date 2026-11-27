# Measuring CPU, RAM, I/O, Disk Latency, and Network from the OS

In MySQL operations, a slow query can originate from CPU saturation, memory pressure, storage bottlenecks, or network latency. Measuring at the operating system layer helps determine which resource is constrained, which process or device carries the load, and whether those symptoms coincide with MySQL slowness. This is an essential skill alongside reading execution plans, indexes, transactions, and internal database statistics.

This lesson explains how to collect and interpret CPU, RAM, I/O, disk latency, and network metrics on Linux, Windows, virtual machines, and containers. The goal is producing repeatable measurements, tying metrics accurately to the right MySQL server, and using evidence to isolate the root cause.

## 1. Observation Scope and Measurement Principles

### 1.1. Observing the Right Resource Layer

A MySQL host has several layers to distinguish:

- **Host**: CPU, RAM, block devices, filesystems, NICs, and kernel of the physical or virtual machine.
- **Process**: the **mysqld** or **mariadbd** process, consisting of many execution threads.
- **Container/cgroup**: CPU, RAM, and I/O limits allocated to the container. Free host resources do not mean the container still has quota.
- **Storage backend**: cloud volumes, SAN, RAID, LVM, NVMe devices, or network-attached storage layers. A path like **/var/lib/mysql** may not map to a single physical disk.
- **Network path**: host NIC, virtual switch, firewall, load balancer, cross-zone links, and client host. Measuring only at the server captures only part of the path.

Do not conclude "MySQL is CPU-starved" just because host CPU is high; another process may be consuming CPU. Similarly, high device **%util** alone does not prove disk saturation; devices with high concurrency can sustain high throughput while still having remaining headroom.

### 1.2. Measuring Over Defined Time Windows

Useful measurements must be anchored to a specific time window. Record:

1. Start and end timestamps, time zone, hostname, and MySQL instance.
2. Application load during that window: request count, throughput, query types, connection count, and incident start time.
3. Host-wide metrics alongside per-process, per-device, or per-interface metrics.
4. Baseline values during normal operation to compare against incident behavior.

Prefer 1–5 second sampling intervals over several minutes for short incidents; use longer intervals for daily or weekly trends. A single sample can miss spikes. For intermittent incidents, retain history using **sar**, a monitoring system, or metrics agents rather than running commands only after the incident ends.

Commands like **vmstat**, **iostat**, and certain utilities print averages since boot or tool start on their first line. When analyzing current load, inspect subsequent lines at the chosen sampling interval; never confuse the initial summary line with a one-second sample.

### 1.3. Identifying Host, Process, and Devices Before Measuring

On Linux, start with:

~~~bash
date --iso-8601=seconds
hostnamectl --static
uptime
nproc
lscpu
pgrep -a 'mysqld|mariadbd'
ps -eo pid,ppid,user,comm,args | grep -E '[m]ysqld|[m]ariadbd'
~~~

If a machine runs multiple instances, never pick a PID solely by process name. Match the PID against its service, command line, socket, port, and data directory. For example, with systemd:

~~~bash
systemctl status mysql
systemctl show mysql -p MainPID -p ControlGroup
~~~

The service name may be **mysqld**, **mysql**, **mariadb**, or an organization-specific name. If **MainPID** is 0 or the service runs under a supervisor/container, resolve the PID from the actual runtime environment.

Locate the devices and filesystems holding data, redo logs, binary logs, and temporary directories:

~~~bash
findmnt -T /var/lib/mysql
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,ROTA,MODEL
df -hT
df -i
~~~

Replace **/var/lib/mysql** with the actual **datadir**. Redo logs, binary logs, relay logs, and temporary directories may reside on separate mounts. **findmnt** shows the filesystem/mount; **lsblk** traces underlying block devices. With LVM, RAID, multipath, or cloud volumes, trace the full mapping stack so latency on one volume is not misattributed to another device.

On Windows, identify the service and process first:

~~~powershell
Get-CimInstance Win32_Service |
  Where-Object { $_.Name -match 'MySQL|MariaDB' } |
  Select-Object Name, State, StartName, ProcessId, PathName

Get-Process -Name mysqld -ErrorAction SilentlyContinue |
  Select-Object Id, CPU, WorkingSet64, PrivateMemorySize64, StartTime

Get-Volume
Get-Disk
Get-NetAdapter
~~~

**Get-Process** may return multiple instances. Match **ProcessId** with the corresponding service and command line. On Windows, use **Get-Partition**, **Get-Volume**, and the **datadir** path to locate the volume storing data.

## 2. Preparing Tools and Permissions

### 2.1. Linux

Common utilities:

| Tool | Purpose |
|---|---|
| **top**, **ps**, **lscpu**, **mpstat** | CPU, threads, and processes |
| **free**, **vmstat**, **sar -r**, **pidstat** | RAM, swap, page faults |
| **iostat**, **pidstat -d**, **iotop**, **lsblk** | Per-device and per-process I/O |
| **ip**, **ss**, **sar -n**, **nstat**, **ethtool** | NICs, TCP, and network errors |

**mpstat**, **iostat**, **sar**, and **pidstat** are typically provided by the **sysstat** package; package names and installation vary by distribution. **vmstat**, **free**, and **ps** usually come from **procps** or an equivalent package. **ss** belongs to **iproute2**. **iotop** and **ethtool** may require separate installation.

Most metric-reading commands require standard user privileges. Viewing detailed per-process, device, or kernel statistics may require **sudo**. Grant only required privileges and follow production operational procedures.

### 2.2. Windows

On Windows, collect metrics using Performance Monitor, Resource Monitor, Task Manager, PowerShell **Get-Counter**, and **Get-*** cmdlets. Performance counter instance names vary with process counts, adapters, and disks. Enumerate available counters on the target machine rather than assuming identical names across hosts.

~~~powershell
Get-Counter -ListSet Processor
Get-Counter -ListSet Memory
Get-Counter -ListSet PhysicalDisk
Get-Counter -ListSet 'Network Interface'
Get-Counter -ListSet TCPv4
~~~

Counter names may be localized according to the Windows display language. If a counter path is missing, locate the exact name using **Get-Counter -ListSet** or Performance Monitor.

## 3. Measuring CPU

CPU affects query execution, expression evaluation, joins, sorts, encryption, compression, checksums, connection handling, and InnoDB background threads. Separate host-wide CPU usage from the CPU actually consumed by the MySQL process.

### 3.1. Metrics to Understand

- **user (%usr)**: CPU executing user-space code, including most MySQL work.
- **system (%sys)**: CPU executing kernel code, such as I/O handling, network stack, filesystems, and system calls.
- **idle (%idle)**: idle CPU time.
- **iowait (%iowait)**: CPU idle while the system has outstanding I/O requests. This is neither disk busy percentage nor a direct measure of disk latency.
- **steal (%steal)**: time a virtual machine wanted to run while the hypervisor allocated CPU to another VM.
- **run queue**: number of runnable tasks waiting for CPU. If persistently higher than available CPUs, CPU contention likely exists.
- **load average**: average number of runnable tasks plus certain uninterruptible tasks (often waiting on I/O) over 1-, 5-, and 15-minute windows on Linux. Load average is not CPU utilization.

### 3.2. Collecting on Linux

Inspect per-core and aggregate CPU:

~~~bash
mpstat -P ALL 1 60
~~~

Columns **%usr**, **%sys**, **%iowait**, **%steal**, and **%idle** show CPU time breakdown by state. Do not read only the **all** line: one core may be 100% saturated while the host average looks low. This frequently happens when a single query thread or background thread becomes the bottleneck.

Measure the MySQL process specifically:

~~~bash
PID=$(pgrep -xo mysqld)
pidstat -u -p "$PID" 1 60
pidstat -w -p "$PID" 1 60
top -H -p "$PID"
~~~

If the process is named **mariadbd**, update the PID lookup accordingly. If multiple PIDs exist, specify the exact PID rather than taking the first match. **pidstat -u** reports process CPU usage; **pidstat -w** reports context switches; **top -H** shows individual threads to spot busy threads. For accurate comparisons, record available CPU count and how the tool normalizes percentages.

Observe run queue and blocked tasks with:

~~~bash
vmstat 1 60
uptime
~~~

In **vmstat**, column **r** is runnable tasks and **b** is blocked tasks. Compare **r** against the CPUs allocated to the process/container. Rising **b** alongside **wa** suggests I/O waiting, though it still must be cross-checked with **iostat** and storage metrics.

### 3.3. Interpreting CPU

- High host and MySQL **%usr**, rising run queue, low CPU idle: MySQL or its workload is genuinely consuming CPU.
- High host **%usr** but low MySQL CPU: find the competing process with **top**, **ps**, or **pidstat**.
- Sharp rise in **%sys**: check system calls, networking, filesystems, interrupts, context switches, and drivers.
- **%iowait** rising alongside device **await**: stronger evidence of storage waits. **%iowait** alone is insufficient.
- Rising **%steal**: investigate hypervisor/cloud throttling or noisy neighbors; SQL tuning alone may not fix it.
- High load average with plenty of idle CPU: check uninterruptible tasks, I/O, container quotas, and actual allocated CPUs.
- One thread near 100% while other cores sit idle: workload may be bottlenecked by a single thread or serialized processing step.

Process CPU percentage on Linux can exceed 100% when threads run concurrently across multiple cores, depending on tool reporting conventions. Do not interpret 180% as using 180% of the whole machine; compare against core count and the tool's normalization mode.

### 3.4. Collecting CPU on Windows

PowerShell can sample counters for one minute:

~~~powershell
Get-Counter -Counter @(
  '\Processor(_Total)\% Processor Time',
  '\System\Processor Queue Length',
  '\Process(mysqld)\% Processor Time'
) -SampleInterval 1 -MaxSamples 60
~~~

If the process instance is not named **mysqld** or has a suffix like **mysqld#1**, find the exact instance name via counter enumeration or Task Manager. **Processor(_Total)\% Processor Time** tracks overall utilization; **Processor(*)\% Processor Time** spots hot cores; **System\Processor Queue Length** helps detect CPU queuing. Use the same sampling window when comparing host and process metrics.

## 4. Measuring RAM and Memory Pressure

MySQL uses RAM for the InnoDB buffer pool, per-connection buffers, table caches, Performance Schema, query execution memory, and internal structures. The OS also needs RAM for the kernel, page cache, filesystems, and other processes. High RAM utilization alone does not imply a problem; determine whether the system lacks available memory, is swapping, or faces reclaim pressure.

### 4.1. Key Concepts

- **MemTotal**: total RAM recognized by the kernel.
- **MemAvailable**: estimate of RAM available to allocate to applications without significant swapping; far more useful than **MemFree** for assessing memory exhaustion.
- **RSS/Working Set**: pages currently resident in RAM for a process. RSS can include shared pages.
- **VIRT/VSZ**: virtual address space; not equivalent to actual physical RAM consumed.
- **Swap in/out**: pages moved between swap and RAM. Continuous swapping increases latency.
- **Major page fault**: requires reading a page from backing store; can stall execution. Minor page faults do not require disk reads.
- **Page cache**: kernel RAM caching filesystem data. Reclaimable when applications need memory.

### 4.2. Collecting on Linux

~~~bash
free -h
cat /proc/meminfo
vmstat 1 60
sar -r ALL 1 60
~~~

In **free -h**, focus on **available**, swap used, and trends over time. Do not conclude RAM is exhausted just because **free** is low: Linux proactively uses spare RAM for caching. In **vmstat**, watch **si** and **so**; persistent non-zero values during query slowness merit investigation. The first line of **vmstat** is typically an average since boot, so inspect subsequent lines for current rates.

Measure per-process memory and page faults:

The commands below use the **PID** variable identified in Section 3.2. If opening a new shell, re-assign PID after verifying the right MySQL instance.

~~~bash
pidstat -r -p "$PID" 1 60
ps -o pid,comm,rss,vsz,%mem --sort=-rss -p "$PID"
~~~

**pidstat -r** reports page faults and per-process memory metrics. **ps** gives point-in-time RSS/VSZ; it does not replace time series. When a process has many threads, memory belongs to a shared address space, so never sum RSS across threads.

Check for kernel OOM kills terminating processes:

~~~bash
journalctl -k --since "30 minutes ago" |
  grep -Ei 'out of memory|oom-killer|killed process'
~~~

On non-systemd hosts, check kernel logs via your distribution's logging mechanism. Correlate OOM timestamps with MySQL restarts and service manager alerts.

### 4.3. Distinguishing RAM Pressure from Cache Memory

A large buffer pool can reduce free RAM, yet if **MemAvailable** is stable, swap-in/out is negligible, and no OOMs occur, there is insufficient evidence to shrink the buffer pool. Conversely, steadily falling **MemAvailable**, active swapping, rising major faults, and climbing query latency indicate real memory pressure needing intervention.

Also check memory consumption outside MySQL: backup agents, antivirus, exporters, log shippers, co-located application processes, or container sidecars. Check cgroup limits because a process can be OOM-killed inside a container while the host still has abundant free RAM.

### 4.4. Collecting RAM on Windows

~~~powershell
Get-Counter -Counter @(
  '\Memory\Available MBytes',
  '\Memory\Committed Bytes',
  '\Memory\Pages/sec',
  '\Process(mysqld)\Working Set - Private'
) -SampleInterval 1 -MaxSamples 60

Get-Process -Name mysqld -ErrorAction SilentlyContinue |
  Select-Object Id, WorkingSet64, PrivateMemorySize64, VirtualMemorySize64
~~~

**Available MBytes** tracks available RAM; **Committed Bytes** reflects committed memory; **Pages/sec** measures system-wide paging activity, not MySQL alone. Also check Resource Monitor and Event Viewer to identify processes, disk paging, and low-memory events. With multiple instances, select the matching process counter instance.

## 5. Measuring I/O and Disk Latency

MySQL depends on storage for data pages, redo logs, undo, binary logs, relay logs, temporary files, and flush operations. Measure throughput, IOPS, queue depth, and latency together. A low-throughput volume is not necessarily slow; a high-throughput volume may be hitting IOPS or latency ceilings.

### 5.1. Identifying the Real Device Behind a Path

First locate the filesystems for **datadir**, redo logs, binary logs, and temporary directories using **findmnt -T <path>**. Then trace **lsblk**, LVM, RAID, device mapper, or cloud volumes. If data and logs sit on separate devices, measure each separately. If multiple mounts share one underlying volume, metrics reflect combined load.

~~~bash
findmnt -T /var/lib/mysql
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,ROTA,MODEL
df -hT /var/lib/mysql
~~~

**df -hT** checks free space and filesystem type; **df -i** checks inode usage. Exhausting space or inodes causes write failures even when latency is low. Check kernel logs for I/O errors, read-only filesystems, controller resets, or device timeouts.

### 5.2. Measuring per Device on Linux

~~~bash
iostat -xz 1 60
sar -d 1 60
~~~

**iostat -xz** provides extended per-device statistics. Common columns:

| Metric | Meaning |
|---|---|
| **r/s**, **w/s** | Reads/writes per second (observed IOPS) |
| **rkB/s**, **wkB/s** | Read/write throughput |
| **r_await**, **w_await** | Average latency per read/write operation, including queue and service time |
| **aqu-sz** | Average I/O queue length |
| **%util** | Percentage of time the device had an I/O request in flight as accounted by the kernel |

Read **r_await** and **w_await** separately to see whether reads or writes are affected. For synchronous redo log writes, write/flush latency can matter more than aggregate throughput. For read-heavy queries, random read IOPS and read latency are key.

**%util** near 100% can indicate a busy device, though it is not a universal saturation threshold for SSD/NVMe or parallel-capable storage arrays. Never rely on **%util** alone in place of **await**, **aqu-sz**, throughput, volume limits, and time trends. **await** is an average; it does not show p95/p99. When tail latency matters, use storage backend telemetry or appropriate tracing tools.

Measure per-process I/O:

Use the verified **PID** variable from Section 3.2; if multiple instances run on the host, specify the target instance's PID.

~~~bash
pidstat -d -p "$PID" 1 60
~~~

**pidstat -d** shows per-process read/write volumes and I/O delays attributed by the kernel. Because some I/O is buffered or asynchronous, per-process counters do not necessarily equal total device counters. You can use **iotop -oPa** to watch active I/O-generating processes; it typically requires elevated privileges and incurs overhead, so run it only during brief investigations.

### 5.3. Interpreting I/O Patterns

- Rising **await** and **aqu-sz** together: I/O requests are waiting longer in queues or backend servicing is slowing down.
- Rising **r_await** with stable **w_await**: inspect read workloads, cache misses, random reads, and data volumes.
- Rising **w_await** coinciding with slow commits: inspect redo logs, binary logs, fsyncs, log volumes, and write limits.
- Throughput near provisioned volume limits with latency climbing under load: the volume may be hitting its throughput cap.
- High IOPS with low throughput: likely many small/random I/O operations.
- High throughput with low IOPS: likely sequential operations or large I/O sizes.
- **df** shows nearly full filesystems or kernel logs report I/O errors: fix capacity or hardware issues before tuning queries.

Do not infer a single query's latency directly from device-wide average **await**. Compare matching time windows, volumes, and I/O types; other workloads sharing the volume can skew results.

### 5.4. Measuring Storage on Windows

In Performance Monitor, track **PhysicalDisk** counters:

- **Avg. Disk sec/Read** and **Avg. Disk sec/Write**: average read/write duration in seconds. Multiply by 1,000 for milliseconds.
- **Disk Reads/sec** and **Disk Writes/sec**: observed IOPS.
- **Disk Read Bytes/sec** and **Disk Write Bytes/sec**: throughput.
- **Current Disk Queue Length**: requests waiting or in progress at sample time.

PowerShell:

~~~powershell
Get-Counter -Counter @(
  '\PhysicalDisk(*)\Avg. Disk sec/Read',
  '\PhysicalDisk(*)\Avg. Disk sec/Write',
  '\PhysicalDisk(*)\Disk Reads/sec',
  '\PhysicalDisk(*)\Disk Writes/sec',
  '\PhysicalDisk(*)\Current Disk Queue Length'
) -SampleInterval 1 -MaxSamples 60
~~~

Select the exact disk instance holding MySQL data. If the volume sits on Storage Spaces, SAN, or cloud disks, also inspect counters at the corresponding volume/backend layer. Queue length must be interpreted relative to device type, thread count, and parallelism; never apply a single threshold to all disks.

Never run write benchmarks directly against an active MySQL data volume. Tools like DiskSpd or fio should only run under a dedicated test plan, on test volumes, or during approved maintenance windows with controlled load profiles.

## 6. Measuring Network

MySQL connections can slow down due to bandwidth limits, packet loss, retransmissions, high RTT, socket queues, NIC errors, or intermediate network issues. CPU and disk may look normal while clients wait on the network.

### 6.1. Network Metrics to Monitor

- **Throughput**: bytes/second or bits/second inbound and outbound.
- **Errors/drops**: corrupted or dropped frames/packets at the interface.
- **TCP retransmissions**: re-sent segments; often suggests packet loss or congestion.
- **RTT**: round-trip time on TCP connections.
- **Socket queues**: data queued waiting for the application to read or waiting to be sent.
- **Connection states**: established, time-wait counts, open/close churn, and listen queue health.

### 6.2. Collecting on Linux

Inspect interfaces and counters:

~~~bash
ip -br link
ip -s link
sar -n DEV 1 60
~~~

**ip -s link** displays cumulative bytes, packets, errors, and drops per interface. Compare two samples to determine growth rates, because cumulative counters since boot do not tell you if errors happened in the last minute. **sar -n DEV** reports periodic throughput and interface counters.

Inspect TCP and retransmissions:

~~~bash
sar -n TCP,ETCP 1 60
nstat -az
ss -s
~~~

**nstat -az** shows kernel network counters; many are cumulative and require time deltas. **sar -n TCP,ETCP** tracks TCP activity and errors/retransmissions depending on **sysstat** version.

Inspect sockets and TCP state:

~~~bash
ss -lntp
ss -tan
ss -ti state established
~~~

**ss -lntp** identifies the process listening on the MySQL port (commonly 3306, though it may differ). **ss -ti** provides detailed TCP stats such as RTT, retransmissions, congestion window, and send state for selected sockets. When many connections exist, filter by endpoint or port to avoid reading unrelated traffic.

For detailed NIC hardware counters:

~~~bash
ethtool -S eth0
ethtool eth0
~~~

Replace **eth0** with the actual interface name. Counters in **ethtool -S** depend on driver and hardware; names and semantics vary. Check **rx_dropped**, **tx_dropped**, checksum errors, ring buffer counters, and related stats per NIC documentation.

### 6.3. Separating Network Issues from Server Issues

- High RX/TX with zero drops/retransmissions: check bandwidth caps and NIC/instance limits.
- Rising drops or errors over time: inspect NICs, drivers, MTU, virtual switches, and network paths.
- Rising TCP retransmissions alongside RTT: likely packet loss or congestion; check both endpoints and intermediate network gear.
- Growing socket receive queue: the server-side application may not be reading fast enough, or the process is stalled.
- Growing socket send queue: sent data is not being acknowledged fast enough by TCP/peer; inspect network path and clients.
- MySQL shows low RTT to some clients and high RTT to others: investigate routing, deployment zones, VPNs, NAT, or client-side firewalls.

**ping** measures ICMP only and may be rate-limited or prioritized differently from TCP. Clean ping results do not prove MySQL TCP connections suffer zero packet loss. Use TCP telemetry, socket stats, and measurements from both client and server sides to conclude.

### 6.4. Collecting Network Metrics on Windows

~~~powershell
Get-NetAdapter |
  Select-Object Name, Status, LinkSpeed, InterfaceDescription

Get-NetAdapterStatistics

Get-Counter -Counter @(
  '\Network Interface(*)\Bytes Received/sec',
  '\Network Interface(*)\Bytes Sent/sec',
  '\Network Interface(*)\Packets Received Errors',
  '\Network Interface(*)\Packets Outbound Errors',
  '\TCPv4\Segments Retransmitted/sec',
  '\TCPv4\Connections Established'
) -SampleInterval 1 -MaxSamples 60
~~~

Pick the specific interface carrying MySQL traffic. TCP counters are system-wide and include other applications. Correlate with NIC stats, process metrics, firewall logs, and client-side observations to isolate scope.

## 7. Observing Inside Containers and Virtual Machines

### 7.1. Cgroup Resource Limits

Inside a container, CPU and RAM counts visible from the host do not reflect the quota allocated to the process. With cgroup v2, common files include:

| File | Content |
|---|---|
| **cpu.max** | CPU quota and period |
| **cpu.stat** | CPU time, throttle count, and throttled duration |
| **cpu.pressure** | CPU wait pressure |
| **memory.current** | Current memory usage |
| **memory.max** | Memory limit |
| **memory.events** | Limit breach, reclaim, or OOM events |
| **memory.pressure** | Memory stall pressure |
| **io.stat** | Per-device I/O accounted by the cgroup |
| **io.pressure** | I/O wait pressure |

Locate the process's cgroup:

~~~bash
cat /proc/"$PID"/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/io.stat
~~~

The actual cgroup path may live in a subdirectory; map the **0::...** line in **/proc/<pid>/cgroup** to the corresponding cgroup mount. Do not assume every container uses cgroup v2 or mounts at the exact same path.

For example, **cpu.max** containing **50000 100000** means a quota of 50,000 microseconds per 100,000-microsecond period—roughly 0.5 CPU. If **cpu.stat** shows **nr_throttled** and **throttled_usec** climbing rapidly, the process is being throttled even if the host has idle CPU. **memory.max** equal to **max** indicates no hard limit at that cgroup level; limits may still exist at a parent cgroup or orchestrator layer.

With Docker, **docker stats --no-stream** gives a quick container usage snapshot. With Kubernetes, **kubectl top pod** requires a working metrics pipeline and provides only partial visibility; inspect resource requests/limits, throttling, and node metrics when needed.

### 7.2. Virtual Machines and Cloud Environments

Rising **%steal** on a Linux guest indicates CPU time withheld by the hypervisor. Cloud storage and networking often enforce limits based on instance type, volume type, volume size, burst credits, or account quotas. When latency rises with load, compare guest metrics against provider metrics: IOPS, throughput, queues, burst balance, throttled operations, and network bandwidth.

A guest may see a single virtual block device backed by multiple infrastructure layers. Therefore, **iostat** inside a guest must be cross-checked with cloud volume metrics and host/hypervisor metrics when available. Low **await** inside the guest does not rule out delays in network or storage layers invisible to the guest.

## 8. Correlating OS Metrics with MySQL Metrics

OS metrics explain how machine resources are behaving. MySQL metrics explain what database activity occurred during that same window. Both sets must be captured with compatible timestamps.

Capture key status variables before and after the measurement window:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Uptime',
  'Threads_connected',
  'Threads_running',
  'Connections',
  'Aborted_connects',
  'Queries',
  'Slow_queries',
  'Innodb_buffer_pool_reads',
  'Innodb_data_reads',
  'Innodb_data_writes',
  'Innodb_os_log_fsyncs'
);
~~~

Status variables are typically cumulative counters since server startup or reset. Take two snapshots and compute deltas over the same window; never compare current cumulative totals between two servers with different uptimes. Variable names and availability can vary by version; verify on your running server with **SHOW GLOBAL STATUS**.

Examples of correlating evidence:

- **Threads_running** and query throughput rise, MySQL CPU climbs, storage latency stays flat: inspect execution plans, rows examined, joins/sorts, expressions, and concurrency.
- **Innodb_buffer_pool_reads** climbs rapidly alongside read IOPS and **r_await**: the workload is reading more from storage; check working set size, buffer pool, queries, and volume capacity.
- Slow commits coinciding with rising **w_await** or flush latency: investigate redo logs, binary logs, fsyncs, and storage backend.
- **Threads_connected** grows while CPU stays low and network RTT/retransmissions rise: investigate connection behavior, clients, and network paths.
- MySQL process CPU appears low while container throttling climbs: check quotas and resource limits.
- Host RAM looks stable while **memory.events** shows increasing **oom** or **max** events: check cgroup limits and container memory allocations.

Never infer root cause from a single status counter. Evaluate deltas, growth rates, observed latency, and workload mix within the same window.

## 9. Investigation Workflow When MySQL Slows Down

A concise, repeatable workflow:

1. **Capture scope**: hostname, instance, PID, service, container/VM, timestamp, and affected clients.
2. **Establish baseline**: compare current CPU, RAM, I/O, and network against normal hours with equivalent workload.
3. **Collect synchronously**: use aligned sampling windows for **mpstat**, **vmstat**, **pidstat**, **iostat**, **sar**, and MySQL status.
4. **Find divergences**: which metrics shifted at the exact moment query latency spiked?
5. **Isolate the layer**: host, process, cgroup, device, filesystem, NIC, client, or cloud backend.
6. **Test the hypothesis**: change one factor in a controlled way or compare against an unaffected instance.
7. **Preserve evidence**: keep timestamps, commands, outputs, quota configurations, and workload state so findings are reproducible.

Example quick collection pass on Linux:

~~~bash
PID=$(pgrep -xo mysqld)
date --iso-8601=seconds
hostnamectl --static
uptime
mpstat -P ALL 1 60
vmstat 1 60
pidstat -u -r -d -w -p "$PID" 1 60
iostat -xz 1 60
sar -n DEV,TCP,ETCP 1 60
~~~

If MySQL runs as **mariadbd**, update the PID lookup accordingly. If multiple instances run, assign PID explicitly. Note that sequential commands do not share identical start times; for tightly synchronized investigations, use centralized monitoring or collectors sharing synchronized timestamps. Remember these commands can produce large outputs; write them to an authorized diagnostic directory and protect sensitive data.

### 9.1. Example Incident Interpretation

Suppose application response time jumps from 30 ms to 400 ms for several minutes. Observations show:

- Overall CPU is 45%, yet one core hits nearly 100%; **pidstat** confirms the MySQL process consumes most of the CPU on that core.
- **MemAvailable** is stable with no significant swap-in/out.
- **iostat** shows **r_await** and **w_await** unchanged from baseline.
- NIC shows no increase in drops or retransmissions; client-to-server RTT is stable.
- **Threads_running** and active queries increased.

Available evidence points toward a CPU bottleneck inside the MySQL workload. The next step is identifying the growing query group, inspecting execution plans, checking rows examined/processed, sorts, temporary tables, and lock waits. Do not provision higher IOPS or add RAM merely because the app is slow when those metrics remained unchanged.

In another scenario: CPU idle remains high and **MemAvailable** is normal, yet **w_await** and device queue length spike precisely when commits slow down; fsync status counters also climb rapidly. Focus on the volumes holding redo/binary logs, write limits, durability policies, and concurrent write workload. This analysis still requires verification at the storage backend before altering durability settings.

## 10. Common Mistakes Reading OS Metrics

- **Looking only at average CPU**: misses a single saturated core or a competing process.
- **Equating load average with CPU**: load can rise due to tasks waiting on I/O.
- **Equating used RAM with RAM exhaustion**: page cache is reclaimable; inspect **MemAvailable**, swap, pressure, and OOM events.
- **Using VIRT to judge process RAM**: VIRT is virtual address space; check RSS/working set and cgroup limits.
- **Looking only at disk %util**: inspect latency, queue depth, IOPS, throughput, and device parallelism.
- **Treating await as p99**: **await** is an average; use percentile telemetry when investigating tail latency.
- **Measuring the wrong volume**: MySQL paths may traverse LVM, RAID, network storage, or cloud volumes.
- **Reading cumulative counters as rates**: compute deltas between two timestamps for rates and error rates.
- **Measuring only the server side**: latency may lie in the client, firewall, load balancer, or network path.
- **Ignoring container quotas**: spare host CPU/RAM does not prove the container has headroom.
- **Comparing windows with different workloads**: baselines must match time of day, traffic volume, and query mix.
- **Running uncontrolled benchmarks in production**: I/O benchmarks can spike latency on live data and trigger secondary outages.

## 11. Operational Checklist

Before concluding a resource bottleneck, confirm:

- [ ] Correct hostname, PID, MySQL instance, container, and service.
- [ ] Identified mounts/volumes holding data, redo logs, binary logs, and temporary files.
- [ ] Clear timestamps, time zones, duration, and sampling intervals.
- [ ] CPU examined per core, per process, and against cgroup quotas.
- [ ] RAM evaluated via **MemAvailable**, swap, page faults, pressure, and OOMs.
- [ ] Storage includes IOPS, throughput, read/write latency, queues, and backend metrics if available.
- [ ] Network includes throughput, errors/drops, retransmissions, RTT, and client-side data.
- [ ] MySQL status collected over the same window and compared via deltas.
- [ ] Conclusions grounded in deviations from baseline rather than arbitrary universal thresholds.
- [ ] Diagnostic outputs stored safely without unnecessary confidential data.

## 12. Hands-On Exercises

### Exercise 1: Identify the Exact Process and Devices

On a test machine running MySQL, identify the **mysqld/mariadbd** PID, corresponding service, **datadir** path, filesystem, and underlying block devices. Record hostname, CPU count, total RAM, and capture timestamp.

**Expected deliverable:** a mapping table of instance → PID → datadir → mount → device/volume.

### Exercise 2: Establish CPU and RAM Baselines

Run **mpstat -P ALL 1 60**, **vmstat 1 60**, and **pidstat -u -r -p <PID> 1 60** during a normal load window. Save the outputs and identify the hottest CPU core, run queue, **MemAvailable**, swap in/out, and page faults.

**Expected deliverable:** timestamped CPU/RAM baseline with workload description.

### Exercise 3: Measure Storage

Run **iostat -xz 1 60** and **pidstat -d -p <PID> 1 60**. Identify devices holding data and logs. Compare read/write IOPS, throughput, **r_await**, **w_await**, **aqu-sz**, and **%util**.

**Expected deliverable:** explain why high device **%util** alone does not prove saturation, and why latency must be read alongside queue depth.

### Exercise 4: Measure Network

Run **ip -s link**, **sar -n DEV,TCP,ETCP 1 60**, **ss -s**, and **nstat -az** before and after a load window. Compute deltas for drop/error/retransmission counters. If a test client host is available, compare RTT and counters at both ends.

**Expected deliverable:** distinguish normal throughput growth from signs of packet loss or congestion.

### Exercise 5: Analyze a Scenario

Simulate or use recorded telemetry to analyze one scenario: single-core CPU saturation; RAM swapping; rising disk write latency; rising TCP retransmissions; or container CPU throttling. State your hypothesis, supporting metrics, inconclusive metrics, and next verification steps.

**Expected deliverable:** a concise report with timeline, evidence, bounded conclusions, and next actions.

## 13. Completion Criteria

You complete this lesson when you can accurately identify the MySQL process and volumes; collect CPU, RAM, I/O, disk latency, and network metrics over a defined window; distinguish host metrics from process/container metrics; interpret averages, cumulative counters, and quotas; correlate OS metrics with MySQL status; and present a baseline-backed conclusion supported by multi-layer evidence.

Measurement only narrows down the problem. After identifying the constrained resource layer, inspect the corresponding queries, transactions, MySQL configuration, OS, storage backend, or network path before making production changes.
