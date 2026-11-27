# Huge Pages, Swap, Filesystem, and Container Limits

PostgreSQL uses shared memory, per-backend private memory, memory for query operators, maintenance memory, OS memory, and storage for data/WAL. When PostgreSQL runs inside a VM or container, these resources are also subject to limits from the hypervisor, cgroups, Docker, or Kubernetes. Therefore, resource tuning must look at both PostgreSQL and the host/runtime.

**Huge pages** can reduce page-table management overhead for large shared memory regions. **Swap** is an OS mechanism to move memory pages out to storage under RAM shortage, yet swap pressure can sharply increase database latency. The **filesystem** determines how data, WAL, temporary files, and logs are persisted durably. **Container limits** cap CPU/memory/storage and can cause throttling or OOM kills if improperly sized.

This lesson explains these mechanisms, how to configure and verify them on Linux, considerations for running PostgreSQL in Docker/Kubernetes, building memory/storage budgets, and monitoring/troubleshooting. Examples primarily target Linux; file paths, permissions, and behavior may differ by distribution, kernel, PostgreSQL major version, and container runtime.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the memory layout of PostgreSQL and Linux.
2. Distinguish shared memory from backend private memory.
3. Explain the benefits and limits of explicit huge pages.
4. Distinguish explicit huge pages from Transparent Huge Pages (THP).
5. Estimate how many huge pages to reserve and verify PostgreSQL uses them.
6. Evaluate swap, swappiness, and OOM risk.
7. Build a memory budget from `shared_buffers`, `work_mem`, maintenance memory, and concurrency.
8. Read cgroup memory/CPU limits and understand their impact on PostgreSQL.
9. Distinguish container memory limits from `/dev/shm` capacity.
10. Configure appropriate Docker/Kubernetes resources and persistent volumes.
11. Understand filesystem durability, `fsync`, WAL, and inode/capacity constraints.
12. Monitor disk, I/O, memory, swap, huge pages, and container throttling.
13. Build runbooks for OOM, filesystem full, and resource throttling.

## 2. Resource Layers Used by PostgreSQL

A PostgreSQL instance relies on multiple resource layers:

| Layer | Examples | Managed by |
|---|---|---|
| Shared memory | `shared_buffers`, lock tables, WAL-related shared structures | PostgreSQL and kernel |
| Backend-private memory | Executor state, sort/hash, expression contexts | Each PostgreSQL process |
| Maintenance memory | VACUUM, CREATE INDEX, maintenance workers | PostgreSQL |
| OS page cache | Read or written file data/WAL | Linux kernel |
| Kernel memory | Page tables, sockets, filesystem metadata | Linux kernel |
| Container accounting | `memory.current`, `memory.max`, CPU quota | cgroups/runtime |
| Persistent storage | `PGDATA`, `pg_wal`, tablespaces | Filesystem/storage platform |
| Temporary storage | Temp files, temporary tables, spill files | Filesystem and PostgreSQL |

A memory budget cannot be computed by taking `shared_buffers` plus a fixed percentage. Workload concurrency, query plans, parallel workers, extensions, OS page cache, and cgroup accounting all affect total usage.

## 3. PostgreSQL Process Model and Memory

PostgreSQL generally uses a process-per-connection model on Unix-like systems. Each client backend has private memory contexts and can allocate memory for query execution. Background processes also run, including checkpointer, background writer, WAL writer, autovacuum workers, logical replication workers, and parallel workers.

### Two Key Memory Groups

- Shared memory is accessed concurrently by multiple PostgreSQL processes, such as shared buffers and shared control structures.
- Private memory belongs to individual processes/workers, such as sort/hash operations, executor state, PL runtimes, and certain buffers.

Shared memory does not mean every process pays for a full separate copy in RSS; mappings can reference the same physical pages. When reading process RSS, avoid mechanically summing RSS across all processes because shared pages get double-counted.

### Why Does Concurrency Matter?

One query can run multiple memory operations. Many concurrent queries and parallel workers can push total private memory far higher than a single connection. Pooling caps concurrency, yet does not automatically guarantee each query uses little memory.

## 4. PostgreSQL Memory Settings

Key settings with major memory impact:

| Setting | Scope/Meaning |
|---|---|
| `shared_buffers` | PostgreSQL shared buffer cache |
| `work_mem` | Max memory for certain query operations before spilling |
| `maintenance_work_mem` | Memory for maintenance operations |
| `autovacuum_work_mem` | Memory per autovacuum worker when set separately |
| `temp_buffers` | Per-session temporary-table buffers |
| `logical_decoding_work_mem` | Memory for logical decoding before spilling |
| `max_connections` | Maximum client connections, affecting backend count |
| `max_parallel_workers_per_gather` | Limit on parallel workers for one query |
| `max_worker_processes` | Total worker process capacity |

Check:

```sql
SHOW shared_buffers;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;
SHOW temp_buffers;
SHOW max_connections;
SHOW max_parallel_workers_per_gather;
```

Defaults vary by version/distribution. Verify effective configuration on the actual instance.

## 5. work_mem Is Not a Connection Memory Limit

`work_mem` is the maximum memory a query operation like sort or hash may use before spilling to temporary files. One query plan can run multiple operations simultaneously; parallel queries can spawn workers that each allocate memory separately.

Simple estimate:

\[
\text{query memory exposure}
\approx
\text{concurrent operations}
\times
\text{work\_mem}
\]

This is only a way to visualize risk, not an exact formula for every plan. Hash operations can also be scaled by `hash_mem_multiplier`; query plan, executor lifetime, and concurrency determine actual usage.

### Example

If `work_mem` is 64 MB, 20 queries run concurrently, each query has 2 live sort/hash operations, and some use parallel workers, total memory exposure can reach gigabytes. Thus, never raise `work_mem` globally just to fix one slow sort query.

### How to Control It

- Use `EXPLAIN (ANALYZE, BUFFERS)` to identify spills.
- Optimize queries/indexes before raising `work_mem`.
- Use `SET LOCAL work_mem` for specific transactions when appropriate.
- Limit query concurrency and parallelism.
- Monitor `temp_files`/`temp_bytes`.

## 6. shared_buffers and OS Page Cache

`shared_buffers` is page caching at the PostgreSQL layer. Linux also caches file pages in the page cache. Hence the database leverages RAM beyond `shared_buffers` to cache data files.

A common starting point on dedicated database servers is `shared_buffers` around 25% of RAM, though this is not a mandatory rule. Evaluate:

- Host/container RAM limit.
- Workload working set.
- OS page cache needs.
- Query concurrency and `work_mem`.
- Autovacuum/maintenance workload.
- Extensions and background processes.
- Huge page reservation and memory headroom.

Never push `shared_buffers` near total RAM. The OS still needs memory for page cache, filesystems, networking, the kernel, and other processes.

## 7. Page Size and Huge Pages

Memory is managed in pages. Standard page size on Linux x86-64 is commonly 4 KiB, depending on architecture/kernel. Huge pages are larger, typically 2 MiB or 1 GiB on supported systems.

| Page type | Common size |
|---|---:|
| Base page | 4 KiB |
| Huge page | 2 MiB |
| Large huge page | 1 GiB on supported hardware/kernel |

Huge pages reduce the number of page table entries needed to map large memory regions. This can reduce page table overhead and TLB pressure for large shared memory.

### Huge Pages Do Not Increase RAM

Huge pages change how memory pages are allocated/mapped. They do not create more RAM and do not replace memory sizing. Reserving too many huge pages reduces RAM left for other needs.

## 8. Explicit Huge Pages in PostgreSQL

PostgreSQL provides the `huge_pages` setting. Check:

```sql
SHOW huge_pages;
```

Common modes:

| Value | Behavior |
|---|---|
| `try` | Attempt to use huge pages; fall back to normal pages if unavailable |
| `on` | Require huge pages; startup fails if allocation fails |
| `off` | Do not use explicit huge pages |

On Linux, explicit huge pages generally require pre-reservation in the kernel, and the PostgreSQL service user must have permission to use them.

### When Are They Helpful?

Benefits are most worth considering on instances with large shared memory, particularly large `shared_buffers`. Actual workload gains depend on hardware, memory topology, and workload; benchmark rather than assuming huge pages always boost throughput.

### Which Region Uses Huge Pages?

PostgreSQL uses huge pages for its main shared memory region when supported and configured. Private allocations, `work_mem`, temp files, and the OS page cache do not automatically become huge pages.

## 9. Checking Huge Page Support on Linux

On the host:

```sh
grep -E 'HugePages|Hugepagesize|Hugetlb' /proc/meminfo
getconf PAGE_SIZE
```

Output typically includes:

- `HugePages_Total`: total huge pages reserved.
- `HugePages_Free`: unused pages.
- `HugePages_Rsvd`: pages reserved for mappings not yet faulted in.
- `HugePages_Surp`: surplus pages.
- `Hugepagesize`: size per page.

For example, if `Hugepagesize` is 2048 kB and `HugePages_Total` is 512, the reserved huge page pool is roughly 1 GiB.

Check kernel configuration:

```sh
sysctl vm.nr_hugepages
```

Paths and page sizes may vary by architecture.

## 10. Estimating Required Huge Pages

Minimum huge pages can be estimated by dividing PostgreSQL's shared memory region size by the huge page size, rounded up:

\[
\text{huge pages}
\approx
\left\lceil
\frac{\text{PostgreSQL shared memory bytes}}
{\text{huge page size bytes}}
\right\rceil
\]

Do not take `shared_buffers` alone as total shared memory. PostgreSQL also allocates shared control structures, WAL buffers, lock tables, and other areas.

On supported PostgreSQL versions, check:

```sql
SHOW shared_memory_size;
SHOW shared_memory_size_in_huge_pages;
SHOW huge_page_size;
```

Availability of these parameters depends on major version. If unavailable, use startup logs and version docs to determine the shared memory requirement.

### Estimation Example

Suppose the shared memory region is around 8 GiB and huge page size is 2 MiB:

\[
8 \times 1024 \div 2 = 4096\ \text{huge pages}
\]

This is an illustrative estimate. Reserve based on the actual shared memory requirement plus modest headroom.

## 11. Reserving Huge Pages via sysctl

Example reserving 4096 pages:

```sh
sudo sysctl -w vm.nr_hugepages=4096
```

To persist across reboots, add to the distribution's sysctl config, e.g.:

```ini
vm.nr_hugepages = 4096
```

After updating, verify:

```sh
sysctl vm.nr_hugepages
grep -E 'HugePages_Total|HugePages_Free|Hugepagesize' /proc/meminfo
```

### Reserving on a Running System

The kernel may fail to allocate enough huge pages if RAM is fragmented or lacks contiguous regions. For large page counts, reserving early at boot or via boot-time configuration is more reliable. Always check the actual allocated count, not just the requested sysctl value.

## 12. Permissions for Huge Pages

The PostgreSQL service user needs proper permissions to map huge pages. Linux may enforce this via hugetlbfs group ownership/permissions or capabilities/rlimits depending on deployment.

Check the service account and kernel/runtime configuration. Never grant broad permissions to all users just to get PostgreSQL to start.

### systemd

Some environments require configuring service limits/capabilities or group access. Unit names and management vary across packages/distributions. Inspect the actual unit file and systemd logs instead of applying a blind override.

## 13. Enabling huge_pages in PostgreSQL

In `postgresql.conf`:

```ini
huge_pages = on
```

Or use `try` during testing:

```ini
huge_pages = try
```

`huge_pages` is a startup setting; a PostgreSQL restart is required. With `on`, if the kernel cannot allocate enough huge pages or permissions fail, the server fails to start. With `try`, PostgreSQL falls back to normal pages.

### Rollout Procedure

1. Measure current RAM and shared memory.
2. Estimate the huge page requirement.
3. Reserve pages on the host.
4. Verify service user permissions.
5. Set `huge_pages=try` in staging or a maintenance window.
6. Restart and read startup logs.
7. Confirm huge pages are actually used.
8. Benchmark workload before/after.
9. Switch to `on` if policy requires fail-fast and operations are stable.

## 14. Verifying PostgreSQL Uses Huge Pages

Check:

```sql
SHOW huge_pages;
SHOW huge_page_size;
```

The `huge_pages` value shows configuration, not proof that mapping succeeded. Also inspect startup logs and kernel/process mapping details for your version.

On Linux:

```sh
grep -E 'HugePages|Hugepagesize' /proc/meminfo
grep -i huge /proc/<postgres_pid>/smaps
```

`smaps` reports per-process mapping details; read permissions depend on OS policy. Use the right PID for the postmaster/backend.

### Checking Logs

PostgreSQL typically logs messages regarding huge page usage or fallback. Exact log wording varies by version. If configured as `on` and startup fails, check the first error mentioning shared memory/huge pages and kernel allocation.

## 15. Transparent Huge Pages (THP)

Transparent Huge Pages is a kernel mechanism that automatically merges/allocates large pages for memory mappings without applications requesting explicit huge pages. THP differs from explicit hugetlb pages controlled by PostgreSQL via `huge_pages`.

### Why Distinguish Them?

- Explicit huge pages are explicitly reserved and managed.
- THP is managed dynamically by the kernel.
- THP can trigger compaction/defragmentation at allocation time.
- Latency-sensitive database workloads can suffer stalls from THP.

PostgreSQL documentation and platform guides commonly recommend considering disabling THP on Linux for database workloads while using reserved explicit huge pages. Check kernel/distribution guidance and benchmark on actual hardware.

## 16. Checking THP Status

On Linux:

```sh
cat /sys/kernel/mm/transparent_hugepage/enabled
cat /sys/kernel/mm/transparent_hugepage/defrag
```

The value in brackets is the active choice. For example, `[always] madvise never` means `always` is active.

Some kernels use different paths or support additional modes. If the file does not exist, consult kernel configuration/distribution docs.

## 17. Disabling THP When Policy Requires

Can be set at runtime:

```sh
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/defrag
```

This is a runtime change and may not survive reboot. Persistence depends on bootloader parameters, systemd services, or distribution tooling. Verify status after reboots and kernel updates.

### Do Not Accidentally Disable Explicit Huge Pages

THP and explicit hugetlb are separate mechanisms. Disabling THP does not delete `vm.nr_hugepages` or prevent `huge_pages=on` from working.

## 18. NUMA and Huge Pages

Multi-socket servers usually have NUMA nodes, each with local memory. Large shared memory can be allocated across one or more NUMA nodes depending on kernel policy, first-touch behavior, and process affinity.

### Why Care?

- Remote memory access can be slower than local access.
- Huge pages need sufficient contiguous memory on the appropriate node.
- CPU pinning and memory policies affect locality.
- One node may run out of huge pages even when total host free memory is plentiful.

### Checking

```sh
numactl --hardware
numastat
```

Do not apply `numactl` interleave or CPU pinning from a generic recipe. Measure memory locality, CPU utilization, and workload latency before changing NUMA policies.

## 19. Huge Page Allocation Failures

Common causes:

- `vm.nr_hugepages` is too low.
- RAM is fragmented and the kernel cannot reserve enough pages.
- Page size mismatch.
- Service user lacks permissions.
- Container was not granted huge page resources.
- Shared memory requirement grew after changing `shared_buffers`/`max_connections`/workers.

### Remediation Steps

1. Read the PostgreSQL startup log.
2. Check `HugePages_Total`, `HugePages_Free`, and `Hugepagesize`.
3. Check the shared memory requirement.
4. Check service account permissions.
5. Check cgroup/container hugepage limits.
6. Reserve sufficient pages during a maintenance window or at boot.
7. Test `huge_pages=try` if policy allows fallback.
8. Restart and verify.

Do not shrink `shared_buffers` or grant overly broad permissions before identifying the exact cause.

## 20. What Is Swap?

Swap is storage space Linux can use to hold memory pages when freeing RAM for other pages. Swap can be a partition or a file. It is a kernel mechanism, not separate memory managed by PostgreSQL.

### When Swap Can Help

- Provides a small buffer during brief memory pressure.
- Moves rarely accessed pages out to keep RAM for the active working set.
- Reduces sudden OOM risk in some scenarios.

### When Swap Hurts

- Swapped-out database pages must be read back from storage, spiking query latency.
- Swap I/O competes with database data/WAL I/O.
- Memory pressure can escalate into reclaim/thrashing.
- Latency becomes unpredictable.

The goal is to avoid sustained swap-in/swap-out pressure, rather than insisting every database host must always have or forbid swap in all environments.

## 21. Checking Swap on Linux

```sh
free -h
swapon --show
cat /proc/swaps
vmstat 1
```

`free` reports total/free/available memory and swap usage. `vmstat` displays `si` (swap in) and `so` (swap out) rates periodically. Non-zero swap used alone does not prove active pressure; what matters is ongoing swap-in/out activity and latency.

### Watching Trends

Track `si`/`so` continuously during peak hours alongside available memory, major page faults, disk latency, and PostgreSQL query latency. Old idle swap usage is far less concerning than active swap churn.

## 22. vm.swappiness

`vm.swappiness` is a kernel parameter influencing the tendency to reclaim anonymous memory vs. page cache. It is not a percentage of RAM to swap and does not directly set a swap limit for PostgreSQL.

Check:

```sh
sysctl vm.swappiness
```

The right value depends on kernel version, workload, memory pressure, and policy. Do not copy a value like `1` or `10` without understanding your current kernel's behavior.

### Changing

Can be tested at runtime in a controlled environment:

```sh
sudo sysctl -w vm.swappiness=10
```

To persist, use distribution sysctl config and verify after reboot. Measure swap activity and page cache behavior before/after.

## 23. Swap Policy for PostgreSQL Hosts

No single swap policy fits all environments:

- Some teams keep a small swap space as a safety buffer while alerting immediately on sustained swap activity.
- Some platforms/appliances mandate swap policies per vendor support.
- Containers may have separate swap limits or disable swap entirely.
- Kubernetes node behavior differs from container-level memory enforcement.

What matters is understanding actual memory limits, OOM policy, swap accounting, and incident response when memory pressure hits.

### Never Use Swap to Mask Memory Overcommit

If PostgreSQL routinely needs swap to run, audit the memory budget, query concurrency, `work_mem`, `shared_buffers`, connection pools, and container limits. Adding swap only delays OOM without fixing the root cause.

## 24. The OOM Killer and PostgreSQL

When Linux cannot satisfy memory allocations, the OOM killer selects a process to terminate. Inside containers, cgroup memory limits can trigger a cgroup OOM even when the host still has free RAM.

Consequences include:

- A PostgreSQL backend is killed and its transaction rolls back.
- The postmaster or a critical process is killed, triggering a database restart and crash recovery.
- The container is restarted by the orchestrator.
- Multiple pods are impacted if node memory pressure is severe.

### Verification

```sh
dmesg -T | grep -i -E 'oom|killed process'
journalctl -k --since '1 hour ago' | grep -i oom
```

In containers/cgroup v2, check `memory.events` and orchestrator termination reasons. Log paths and access permissions vary by platform.

## 25. Building a Memory Budget for PostgreSQL

A memory budget must account for:

1. Shared memory: `shared_buffers` and other shared structures.
2. Backend private memory: query execution, expressions, functions, extensions.
3. Concurrent query operations: `work_mem`/hash memory.
4. Maintenance/autovacuum workers.
5. Parallel workers.
6. OS/kernel/page cache.
7. Monitoring, backup agents, sidecars.
8. Safety headroom for spikes and failover.

Budgeting layout:

```text
Container/host memory limit
  - PostgreSQL shared memory
  - Estimated concurrent backend/query memory
  - Maintenance/parallel worker allowance
  - OS/kernel/sidecar overhead
  - Safety headroom
  = Remaining operational margin
```

### Do Not Mechanically Multiply work_mem by max_connections

Not every connection runs a sort/hash at the exact same instant. Conversely, never assume only one operation runs per connection. Use workload concurrency, `EXPLAIN` plans, and measured memory to calibrate estimates.

## 26. shared_buffers and Huge Pages in the Memory Budget

If explicit huge pages are reserved, those pages still consume host RAM. Never treat huge page reservations as free extra memory outside `shared_buffers`.

When budgeting:

- Estimate PostgreSQL shared memory.
- Reserve sufficient huge pages.
- Calculate remaining RAM for private memory and OS.
- Verify host/cgroup memory accounting.
- Ensure huge page reservations do not starve other processes of RAM.

On some systems, hugetlb pages are accounted separately from ordinary cgroup memory; verify the cgroup hugetlb controller and runtime policy.

## 27. Cgroups: Container Resource Control

Cgroups are a Linux kernel mechanism for grouping processes and limiting/accounting resources. Container runtimes use cgroups to enforce CPU/memory constraints.

Key resources:

- Memory limits and usage.
- CPU shares/weights or quotas.
- Memory pressure/events.
- HugeTLB page limits on supported systems.
- I/O controls.

### Cgroups v1 vs. v2

Linux has cgroups v1 and the unified hierarchy v2. File names and semantics differ. Never assume every container uses the same path or exposes identical metrics.

Check:

```sh
stat -fc %T /sys/fs/cgroup
cat /proc/self/cgroup
```

On cgroup v2, the filesystem type is typically `cgroup2fs`.

## 28. Cgroup v2 Memory Files

Commonly used files:

| File | Meaning |
|---|---|
| `memory.current` | Memory currently charged to the cgroup |
| `memory.max` | Hard memory limit |
| `memory.high` | Pressure/throttling/reclaim threshold |
| `memory.events` | Counters for high/max/oom/oom_kill |
| `memory.stat` | Breakdown of memory usage |
| `memory.swap.current` | Swap usage |
| `memory.swap.max` | Swap limit |
| `memory.pressure` | PSI memory pressure |

Inspect the cgroup path of the target process/container; do not read `/sys/fs/cgroup` root and assume it is the container limit if the process runs in a child cgroup.

Example:

```sh
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.swap.current
```

`max` in `memory.max` indicates no hard limit at that cgroup level. Parent cgroups may still enforce limits.

## 29. Cgroup Memory Pressure and OOM

In cgroup v2:

- `memory.high` triggers reclaim/throttling when usage crosses the threshold.
- `memory.max` is a hard cap; exceeding it triggers OOM within the cgroup.
- Rising `high`, `max`, `oom`, and `oom_kill` in `memory.events` pinpoint pressure.
- `memory.pressure` provides PSI to measure how much time tasks stall on memory pressure.

### Container OOM vs. Host OOM

The host may still have free RAM when a container hits `memory.max`. PostgreSQL processes inside the container can still be killed. Therefore, read `free -h` inside a container or on the host alongside cgroup limits/events.

## 30. CPU Limits and PostgreSQL

Cgroup CPU quotas cap how much CPU time a container can use per period. When workloads exceed the quota, processes are throttled even if the host has idle CPUs.

Consequences:

- Rising query latency.
- Slower WAL replay/autovacuum.
- Delayed checkpoints/background tasks.
- Growing connection queues.
- Health check timeouts.

Check cgroup v2:

```sh
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
```

`cpu.max` expresses quota and period; `cpu.stat` contains throttling counters/time. Cgroup v1 uses different files such as `cpu.cfs_quota_us`/`cpu.cfs_period_us`.

### CPU Requests and Limits

In Kubernetes, CPU requests primarily govern scheduling/relative allocation; CPU limits can be enforced via quota/throttling. A PostgreSQL pod with too low a limit can be heavily throttled during workload bursts.

## 31. /dev/shm and Dynamic Shared Memory

On Linux, PostgreSQL can use POSIX shared memory for dynamic shared memory segments, such as in certain parallel query operations. These segments are typically created under `/dev/shm` when `dynamic_shared_memory_type` is `posix`.

Check:

```sql
SHOW dynamic_shared_memory_type;
SHOW min_dynamic_shared_memory;
```

On the host/container:

```sh
df -h /dev/shm
mount | grep /dev/shm
```

### /dev/shm Is Not shared_buffers

PostgreSQL's main shared memory region and dynamic shared memory segments are separate concepts. Growing `/dev/shm` does not automatically increase `shared_buffers`. Conversely, a container with a tiny `/dev/shm` can fail when workloads need dynamic shared memory even when the overall memory limit has spare headroom.

### When Errors Occur

- Check free space and inodes on `/dev/shm`.
- Check PostgreSQL logs for shared memory segment creation errors.
- Check `dynamic_shared_memory_type`.
- Identify parallel queries/workloads driving allocations.
- Increase `/dev/shm` capacity or adjust parallelism per runtime design.

Do not reflexively disable parallel queries before confirming `/dev/shm` is the culprit.

## 32. Docker Memory and Swap Limits

Docker can set memory and swap limits on containers. Exact flags and semantics depend on Docker Engine, kernel, and cgroup version.

Illustrative example:

```sh
docker run \
  --memory=8g \
  --memory-swap=10g \
  --shm-size=1g \
  postgres:17
```

This example shows three distinct limits:

- `memory`: container memory limit.
- `memory-swap`: total memory + swap limit per Docker semantics; it does not always mean adding that exact amount of swap on top.
- `shm-size`: size of the `/dev/shm` tmpfs.

### Inspect Actual Runtime

Do not rely solely on command-line flags. Check `docker inspect`, cgroup files, container stats, and host configuration. Docker runs differently across cgroup v1 vs. v2.

### Swap Policy

If a container is denied swap, memory pressure triggers OOM sooner. If swap is allowed, sustained swap I/O still degrades PostgreSQL latency. Choose based on latency objectives and platform policies.

## 33. Kubernetes Memory Requests and Limits

In Kubernetes:

- `memory` request helps the scheduler place the pod on a node with sufficient capacity.
- `memory` limit sets the cgroup cap for the container.
- If a container exceeds its memory limit, the kernel may OOM-kill a process inside the container.
- The pod may restart depending on restart policy and workload controller.

Example:

```yaml
resources:
  requests:
    cpu: "2"
    memory: "8Gi"
  limits:
    cpu: "4"
    memory: "8Gi"
```

This is a configuration example only. The PostgreSQL memory budget must be sized to the container limit plus any sidecars/agents sharing limits or competing for node memory.

### QoS Class

Kubernetes QoS class depends on requests/limits across containers in the pod. Guaranteed QoS generally requires CPU and memory requests equal to limits on every container; Burstable/BestEffort behave differently under node pressure. Understand cluster QoS and eviction policies before choosing settings.

## 34. Kubernetes Huge Pages

Kubernetes can expose pre-allocated huge pages as sized resources, such as `hugepages-2Mi` or `hugepages-1Gi` on supported nodes.

Typical requirements:

1. Node kernel supports that page size.
2. Huge pages are pre-reserved on the node before pod scheduling.
3. Kubelet/runtime detects the resource.
4. Pod requests/limits huge pages appropriately.
5. Container has compatible mounts/permissions for PostgreSQL.

Illustrative resource request example:

```yaml
resources:
  requests:
    hugepages-2Mi: "1Gi"
  limits:
    hugepages-2Mi: "1Gi"
```

The pod may require a volume mount with medium `HugePages-2Mi` per Kubernetes/runtime design. Exact configuration depends on cluster version and page-size support.

### Huge Pages Cannot Be Overcommitted Like Regular RAM

Huge page resources are finite node resources. If a node lacks enough reserved pages, pods cannot schedule. Never declare huge page requests without verifying node capacity and PostgreSQL mapping behavior.

## 35. Kubernetes CPU Limits and Throttling

CPU requests influence scheduling and relative CPU weight. CPU limits can be enforced via CFS quota. A PostgreSQL process spawning multiple workers can be throttled when aggregate CPU time exceeds quota.

Check pod/container metrics:

- CPU usage.
- CPU throttled periods.
- CPU throttled seconds.
- Node run queue/CPU pressure.
- Query latency, WAL replay lag, and autovacuum duration.

### When to Avoid Low CPU Limits

Database workloads feature bursty queries, checkpoints, vacuuming, and parallel execution. Too low a CPU limit slows these background tasks, causing lag or storage pressure. Size requests/limits using capacity planning and platform policy, then benchmark.

## 36. Persistent Volumes for PostgreSQL

The PostgreSQL data directory must sit on storage with appropriate durability and lifecycle. In container orchestration, use a persistent volume/claim or supported storage service instead of the container writable layer.

### Distinguishing Storage Types

| Type | Used for | Risk |
|---|---|---|
| Container writable layer | Temporary runtime files | Lost when container is recreated |
| Persistent volume | `PGDATA`/WAL/tablespaces | Must verify durability/latency/attachment semantics |
| Ephemeral volume | Temp/cache/log staging | Unsuitable as durable data store |
| Backup object storage | Backup/archive repository | Requires restore/consistency workflow |

Never store `PGDATA` solely in the container layer and expect data to survive reschedules/recreates.

## 37. Filesystem and Durability Requirements

PostgreSQL relies on filesystem/storage semantics to ensure WAL and data are persisted durably per configuration. The filesystem must support locking, `fsync`, and semantics supported by PostgreSQL and the platform.

Common Linux filesystems like `ext4` and `XFS` work well for PostgreSQL when properly configured. No single filesystem is best for every workload; benchmarks and vendor/storage guidance matter greatly.

### What to Check

- Is the filesystem supported by your OS/storage vendor?
- Do mount options preserve durability semantics?
- Does storage implement proper flush/barrier semantics?
- Is `fsync` latency stable?
- Do snapshot/backup workflows coordinate properly with PostgreSQL?
- Are free space and inodes sufficient?

## 38. fsync and full_page_writes

PostgreSQL uses WAL to protect data changes. Key settings:

```sql
SHOW fsync;
SHOW full_page_writes;
SHOW synchronous_commit;
```

- `fsync=on` instructs PostgreSQL to ensure writes are flushed via system mechanisms.
- `full_page_writes=on` writes a full page image to WAL on the first change after a checkpoint to protect against torn pages in certain failure modes.
- `synchronous_commit` controls commit acknowledgment level, not replacing `fsync`.

### Do Not Disable Durability to Fix Slow I/O

Turning off `fsync` or `full_page_writes` risks data loss or corruption after crashes/power loss. Only alter them when you fully accept the risk for an approved use case like a disposable benchmark/test environment. Production must maintain proper durability policies.

## 39. Mount Options and Storage Semantics

Never copy mount options from blogs without checking filesystem, kernel, and storage. Options affect `atime`, barriers, journaling, write cache, and durability.

### Questions to Answer

- Does storage have battery/flash-backed write cache?
- Does `fsync` truly flush to stable storage?
- Are snapshots crash-consistent or application-consistent?
- Does the volume enforce IOPS/throughput caps?
- Are there burst credits and throttling once exhausted?
- Is multi-attach or fencing behavior handled properly?

### NFS and Network Storage

Do not assume every NFS/export is safe for `PGDATA`. Use network storage only when PostgreSQL version, OS, NFS protocol, locking, `fsync`, and vendor support meet requirements. Verify latency, failure semantics, and fencing; a working mount does not guarantee durability.

## 40. Organizing PGDATA, pg_wal, and Tablespaces

PostgreSQL can place `PGDATA`, WAL, and tablespaces on separate filesystems/volumes, yet separation only helps with clear capacity, I/O isolation, or operational reasons.

### PGDATA

Contains cluster metadata, relation files, catalogs, and configuration/state files per layout. Requires proper backup/restore and permission policies.

### pg_wal

Contains WAL segments needed for crash recovery, replication, and archiving. If the filesystem fills, PostgreSQL cannot keep writing transactions.

### Tablespaces

Allow placing relation data in different locations. Every tablespace needs explicit storage, mount, and backup/restore mapping.

### Do Not Separate WAL Arbitrarily

Putting `pg_wal` on a slow volume or one that fills independently can halt cluster writes. If separating, maintain dedicated monitoring, capacity reserves, and recovery plans.

## 41. Filesystem Capacity and Inodes

Filesystems have two distinct limits:

- Block capacity: remaining bytes.
- Inode capacity: remaining filesystem objects that can be created.

A filesystem can have gigabytes free yet run out of inodes, preventing PostgreSQL or exporters from creating new files.

Check:

```sh
df -h
df -i
findmnt
```

### Monitor Specific Mountpoints

Alert on each filesystem holding `PGDATA`, `pg_wal`, tablespaces, logs, temp files, and backup staging. Total host free disk can mask a full dedicated mount.

### Never Delete Database Files Manually

Never delete files in `base`, `global`, or `pg_wal` to free space. Identify the actual growth source and use PostgreSQL-aware cleanup/retention procedures.

## 42. WAL Growth and Replication Slots

WAL grows due to write workloads, checkpoint/full-page writes, replication lag, archive failures, or replication slots retaining needed segments.

Check slots:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots;
```

Some columns depend on PostgreSQL version. Verify view schemas on the live instance.

### Check WAL Directory

```sql
SELECT *
FROM pg_catalog.pg_ls_waldir()
ORDER BY modification DESC
LIMIT 20;
```

This function requires appropriate privileges. Use filesystem/exporter metrics and slot metrics to understand retention; do not rely solely on file counts in the directory.

### Never Delete WAL Manually

Never run `rm` inside `pg_wal`. PostgreSQL manages WAL recycling/removal based on checkpoints, replication slots, archiving, and recovery state. Manual deletion can render the cluster unrecoverable or break replicas.

## 43. WAL Archiving and Filesystem Pressure

If the archive command fails, WAL accumulates in `pg_wal`. Check:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_catalog.pg_stat_archiver;
```

### Recommended Alerts

- Rising archive failures.
- Time since last successful archive exceeding policy.
- Continuously growing WAL directory.
- Falling free disk / time-to-full.
- Replication slot retaining WAL beyond budget.

Never resolve this by wiping archive backlogs without understanding the backup/PITR chain.

## 44. Temporary Files and temp_tablespaces

Sort/hash operations exceeding memory budgets spill to temporary files. Temporary tables also generate I/O and consume filesystem space.

Check:

```sql
SHOW temp_file_limit;
SHOW temp_tablespaces;
```

Database-level stats report `temp_files`/`temp_bytes`:

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes
FROM pg_catalog.pg_stat_database
ORDER BY temp_bytes DESC;
```

Stats are cumulative since the last reset; compute deltas/rates over time. Temp file spikes indicate query spills, low `work_mem`, or inefficient query plans.

## 45. Backups and Filesystems

Backups generate heavy I/O and need staging space. Monitor separately:

- Backup destination free space.
- Backup duration/throughput.
- WAL archive backlog.
- Temporary staging files.
- Snapshot retention.
- Restore workspace capacity.

Backup repositories should not depend solely on the same filesystem that could fill from `PGDATA`/WAL. When using snapshots, verify consistency protocols and retention.

### Restore Capacity

Having enough space for a backup does not mean having enough space to restore. Account for data size, WAL replay, temporary expansion, indexes, and growth headroom during restore drills.

## 46. Overlay Filesystems in Containers

Container writable layers are typically implemented with an overlay filesystem. This works well for application image layers, yet should never be assumed optimal for PostgreSQL data.

Risks:

- Data loss when containers are recreated without persistent volumes.
- Copy-on-write overhead degrading I/O.
- Disk usage counted against ephemeral storage/node capacity.
- Image/layer cleanup will not save a full volume.

Place `PGDATA` on a supported persistent volume and verify the mount path inside the container.

## 47. Ephemeral Storage and Kubernetes Eviction

Kubernetes tracks ephemeral storage usage per container/pod and node. Logs, writable layers, and `emptyDir` all contribute to ephemeral storage consumption.

Exceeding limits or triggering node disk pressure causes pod eviction. This is a different failure mode from PostgreSQL memory OOM.

### Check

- Pod `ephemeral-storage` requests/limits.
- Node `DiskPressure` condition.
- Container writable layer usage.
- `emptyDir` usage.
- Container log rotation.
- Kubelet eviction events.

Never put backup staging or durable PostgreSQL data in `emptyDir` without a proper recovery policy.

## 48. Monitoring Memory and Huge Pages

Collect on the host:

- `MemAvailable`.
- Swap used and swap-in/swap-out rates.
- Major page faults.
- `HugePages_Total`/`Free`/`Rsvd`/`Surp`.
- THP `enabled`/`defrag` state.
- NUMA memory distribution.
- OOM events and memory PSI.

Collect in PostgreSQL:

- `shared_buffers`/`work_mem`/maintenance settings.
- `max_connections` and active backends.
- Parallel workers.
- `temp_files`/`temp_bytes`.
- Autovacuum workers and maintenance activity.
- Query latency and throughput.

Collect in containers:

- `memory.current`/`max`/`high`.
- `memory.events` and `memory.pressure`.
- `memory.swap.current`/`max`.
- CPU quota/throttling.
- Container restart/OOM reasons.

## 49. Monitoring Filesystems and Storage I/O

Track per mount:

- Used bytes/percent.
- Free bytes.
- Free inodes.
- Growth rate / time-to-full.
- Read/write throughput.
- IOPS and queue depth.
- Read/write latency.
- `fsync` latency where instrumented.
- Volume throttling / burst credits.

### Related PostgreSQL Signals

- WAL bytes generated.
- Checkpoint frequency/duration.
- Buffers written.
- Temp bytes.
- Archive failures.
- Replication slot retention.
- Query latency.

Combine storage metrics with database metrics to separate disk saturation from query plan or lock issues.

## 50. Memory Pressure in Containers and Hosts

When PostgreSQL slows down, compare:

1. Host `MemAvailable` and swap activity.
2. Container `memory.current` vs. `memory.max`.
3. `memory.events`, `memory.pressure`, and OOM counters.
4. PostgreSQL shared/private workload signals.
5. Sidecar/agent memory usage.
6. CPU throttling and I/O pressure.

If the host has free RAM yet the container hits its limit, adding host RAM will not fix the container cap. If container usage is low yet host memory pressure is high, inspect node contention, page cache, and kernel memory.

## 51. Resource Sizing Workflow

A practical workflow:

1. Measure baseline workloads across peak hours and batch windows.
2. Record host RAM, CPU, and storage IOPS/throughput/latency.
3. Determine container requests/limits and cgroup version.
4. Measure `shared_buffers` and shared memory size.
5. Estimate concurrent `work_mem`/hash operations.
6. Calculate maintenance/autovacuum/parallel worker allowances.
7. Reserve OS page cache, kernel, monitoring, and safety headroom.
8. Decide on explicit huge pages after benchmarking.
9. Set swap/OOM policies per platform.
10. Size `PGDATA`, `pg_wal`, tablespaces, temp, and backups.
11. Check `/dev/shm` and ephemeral storage separately.
12. Load test, failover test, and monitor after rollout.

### Leave Headroom

Never size strictly to average usage. Reserve headroom for traffic spikes, maintenance, failovers, catch-up replication, and restore/upgrade tasks.

## 52. Troubleshooting: PostgreSQL Fails to Start Due to Huge Pages

1. Read the first startup log message mentioning shared memory/huge pages.
2. Check the `huge_pages` setting.
3. Check `HugePages_Total`/`Free` and `Hugepagesize`.
4. Compare against the actual shared memory requirement.
5. Check user/group/capabilities.
6. Check container hugetlb resource limits.
7. Reserve pages for the correct page size.
8. Test `huge_pages=try` if policy allows fallback.
9. Restart and verify logs.

Do not reduce huge page reservations or change `shared_buffers` randomly; pinpoint whether it is insufficient pages, permissions, or cgroup limits.

## 53. Troubleshooting: Rising Swap Activity

1. Check `vmstat` `si`/`so` over time.
2. Check `MemAvailable` and memory pressure.
3. Check container `memory.current`/`max` if applicable.
4. Find top memory-consuming processes/containers.
5. Check `work_mem`, concurrency, and parallel workers.
6. Check connection pools and query workloads.
7. Check disk I/O latency and query latency.
8. Reduce concurrency or memory exposure for the workload.
9. Adjust memory limits/sizing if needed.
10. Verify swap-in/out drops and latency recovers.

## 54. Troubleshooting: Container OOMKilled

1. Check pod/container termination reason and exit status.
2. Check cgroup `memory.events`.
3. Inspect `memory.current`/`max`/`high` prior to the event if metrics exist.
4. Check node memory pressure and kernel logs.
5. Identify whether PostgreSQL or a sidecar was killed.
6. Check `shared_buffers`, `work_mem`, concurrency, and parallelism.
7. Check restart/crash recovery logs.
8. Raise limits or reduce memory exposure based on measurements.
9. Ensure requests match so the scheduler picks nodes with enough capacity.
10. Re-run load tests under the updated limits.

## 55. Troubleshooting: PostgreSQL Experiencing CPU Throttling

1. Read `cpu.stat`/throttling metrics.
2. Compare CPU request, limit, and host capacity.
3. Inspect query latency and run queues.
4. Check autovacuum/WAL replay/checkpoint durations.
5. Check parallel query worker counts.
6. Optimize queries and limit concurrency if needed.
7. Tune CPU requests/limits per workload and policy.
8. Measure throttling and throughput after changes.

## 56. Troubleshooting: Filesystem Full

1. Identify the exact mountpoint using `df -h`.
2. Check inodes using `df -i`.
3. Locate the growing directory using appropriate filesystem tools.
4. Check `pg_wal`, replication slots, and archive failures.
5. Check temp files, logs, backups, and tablespaces.
6. Determine file retention and ownership.
7. Perform PostgreSQL-aware cleanup or expand the volume per runbook.
8. Never manually delete files in `pg_wal`/`base`/`global`.
9. Monitor free bytes/inodes and PostgreSQL write health.
10. Tighten headroom alerts if detected too late.

## 57. Troubleshooting: Out of Inodes

If `df -h` shows free space yet file creation fails:

- Run `df -i`.
- Find directories creating huge numbers of small files.
- Check logs, temp files, archive staging, and backup metadata.
- Clean up according to retention policy.
- Evaluate filesystem inode density when provisioning new volumes.

Never delete data files by filename or file age without confirming ownership.

## 58. Troubleshooting: /dev/shm Out of Space

1. Check `df -h` and `df -i` for `/dev/shm`.
2. Check `dynamic_shared_memory_type`.
3. Inspect PostgreSQL logs and query parallelism.
4. Check other processes using tmpfs.
5. Increase `shm-size`/volume capacity per container policy or adjust workload.
6. Restart/retry only per procedure after confirming sufficient resources.

Distinguish `/dev/shm` full from container `memory.max` reached; they are two different limits.

## 59. Runbook: Memory Budget and OOM Review

1. Record host/container memory limits.
2. Gather cgroup `current`/`max`/`events`/`pressure`.
3. Record `shared_buffers` and shared memory.
4. Estimate `work_mem` operations × concurrency.
5. Account for maintenance/autovacuum/parallel workers.
6. Check sidecars, exporters, and backup agents.
7. Correlate swap/OOM events with the workload timeline.
8. Determine whether the bottleneck is PostgreSQL config, concurrency, or container limits.
9. Adjust one parameter group in a controlled manner.
10. Load test and verify headroom.

## 60. Deployment Checklist for Huge Pages, Swap, Filesystem, and Containers

### Huge Pages

- Verify kernel/page size support.
- Estimate shared memory requirement.
- Reserve the right number of huge pages on the host.
- Confirm permissions and cgroup/runtime support.
- Check THP policy.
- Enable `huge_pages` per rollout plan.
- Confirm logs and kernel mappings.
- Benchmark before/after.

### Swap and Memory

- Memory budget includes private/shared/OS/sidecar headroom.
- `work_mem` calculated across operations and concurrency.
- Swap activity monitored.
- OOM events/PSI monitored.
- Container memory limit is no lower than peak budget.
- Connection/query concurrency bounded.

### Filesystem/Storage

- `PGDATA` sits on persistent storage.
- `fsync`/`full_page_writes` policies preserved.
- `PGDATA`, `pg_wal`, tablespaces, and backups have capacity monitoring.
- Free bytes and inodes alerted.
- WAL slots/archive retention monitored.
- IOPS/latency/throttling monitored.
- No manual deletion of WAL/data files.

### Containers

- Cgroup version and effective limits identified.
- CPU requests/limits benchmarked.
- `memory.current`/`max`/`events` monitored.
- `/dev/shm` capacity sized for workload.
- Persistent volumes and ephemeral storage separated.
- Kubernetes OOM/eviction/restart events alerted.
- Huge page resources reserved and scheduled properly.

## 61. Practice Exercises

### Exercise 1 — Memory Layout

Distinguish shared memory, backend-private memory, OS page cache, and kernel memory in a PostgreSQL instance.

### Exercise 2 — RSS Accounting

Why can summing RSS across all PostgreSQL processes double-count shared memory? Which additional metrics should you use?

### Exercise 3 — work_mem

A query has three sort/hash operations and runs with four parallel workers. Why can `work_mem` not be treated as a per-connection memory limit?

### Exercise 4 — shared_buffers

Why is `shared_buffers` at ~25% of RAM only a starting point? List the factors affecting sizing.

### Exercise 5 — Huge Pages

Explain how huge pages reduce page table/TLB overhead and why they do not increase total RAM.

### Exercise 6 — Huge Page Calculation

A shared memory region requires 10 GiB and the huge page size is 2 MiB. Compute the simple minimum page count and list overheads to consider.

### Exercise 7 — huge_pages Modes

Compare `try`, `on`, and `off`. Under which mode can the server fail to start?

### Exercise 8 — Kernel Reserve

Write commands to inspect `vm.nr_hugepages`, `HugePages_Total`, `HugePages_Free`, and `Hugepagesize`.

### Exercise 9 — Permissions

A PostgreSQL service cannot map huge pages even though the kernel reserved enough. Which permissions/capabilities should you investigate?

### Exercise 10 — THP

Distinguish Transparent Huge Pages from explicit hugetlb pages. Why might database workloads care about THP defrag?

### Exercise 11 — NUMA

A dual-socket server has enough total huge pages yet startup fails to reserve them on the appropriate node. Explain NUMA locality and how to inspect it.

### Exercise 12 — Swap

Swap used is 4 GB, yet `si`/`so` are 0 over a long period. Why can you not immediately conclude the database is thrashing?

### Exercise 13 — swappiness

Explain `vm.swappiness` and why a value of `1` does not mean Linux uses only 1% swap.

### Exercise 14 — OOM

Distinguish host OOM from cgroup/container OOM. List the log/metric sources to inspect.

### Exercise 15 — Memory Budget

Design a memory budget covering `shared_buffers`, `work_mem` operations, maintenance workers, OS page cache, sidecars, and safety headroom.

### Exercise 16 — Cgroup v2

Explain `memory.current`, `memory.max`, `memory.high`, `memory.events`, and `memory.pressure`.

### Exercise 17 — CPU Throttling

Inspect `cpu.max` and `cpu.stat`. How can throttling affect WAL replay, autovacuum, and query latency?

### Exercise 18 — Docker Limits

Explain the differences between `--memory`, `--memory-swap`, and `--shm-size` in Docker.

### Exercise 19 — /dev/shm

Why can a full `/dev/shm` cause parallel queries to fail even before the container memory limit is reached?

### Exercise 20 — Kubernetes Requests/Limits

Distinguish CPU/memory requests and limits. What risks does a PostgreSQL pod face if its memory limit is below peak memory?

### Exercise 21 — Kubernetes Huge Pages

List the requirements for a pod to request `hugepages-2Mi` and for PostgreSQL to use those pages.

### Exercise 22 — Persistent Volumes

Why should `PGDATA` not sit in the container writable layer? Distinguish persistent volumes from ephemeral storage.

### Exercise 23 — Filesystem Durability

Explain why PostgreSQL requires a filesystem/storage layer with reliable `fsync` semantics.

### Exercise 24 — fsync and full_page_writes

State the roles of these two settings. Why should you not disable them merely to raise benchmark throughput?

### Exercise 25 — PGDATA and pg_wal

A cluster uses two separate filesystems for `PGDATA` and `pg_wal`. Which capacity, failure, and monitoring concerns apply?

### Exercise 26 — Inodes

A filesystem has 20 GB free yet is out of inodes. What errors can PostgreSQL encounter? Which command checks this?

### Exercise 27 — Replication Slots

An inactive logical slot retains WAL and causes `pg_wal` to grow. Write a query to inspect slots and describe how to investigate owner/retention.

### Exercise 28 — Archive Failures

Write a query to read `pg_stat_archiver` and list alerts needed when the archive backlog grows.

### Exercise 29 — Temporary Files

Use `pg_stat_database` to monitor `temp_files`/`temp_bytes`. What causes can drive temp I/O up?

### Exercise 30 — Storage I/O

List the IOPS, throughput, queue depth, latency, and volume throttling metrics to monitor for PostgreSQL.

### Exercise 31 — Network Storage

Why is a working NFS mount insufficient proof that storage is suitable for `PGDATA`? State durability/locking/fencing concerns.

### Exercise 32 — Overlay Filesystem

Explain copy-on-write overhead and data-loss risks when storing `PGDATA` in a container layer.

### Exercise 33 — Ephemeral Storage

A pod is evicted for `DiskPressure` even though its persistent volume has plenty of space. Which ephemeral storage sources should you check?

### Exercise 34 — Monitoring

Design a dashboard combining host memory, swap, huge pages, cgroup memory, CPU throttling, and PostgreSQL query metrics.

### Exercise 35 — Huge Page Failure

PostgreSQL startup fails with `huge_pages=on`. Write a runbook to distinguish missing reservation, permissions, or container hugetlb limits.

### Exercise 36 — Swap Pressure

Database latency rises alongside swap-in/out. Describe an investigation workflow covering memory budget, concurrency, and cgroup limits.

### Exercise 37 — Container OOMKilled

A PostgreSQL pod restarts with `OOMKilled` while the node still has free RAM. Explain how to use `memory.events` and pod status to diagnose the cause.

### Exercise 38 — Filesystem Full

The `pg_wal` filesystem is full. List growth sources to inspect and explain why WAL files must never be removed manually with `rm`.

### Exercise 39 — CPU Throttling

After setting a CPU limit, query latency and replication lag both climb. Design before/after measurements and quota adjustments.

### Exercise 40 — Designing PostgreSQL Resources in Kubernetes

A cluster has:

- PostgreSQL primary with 512 GiB RAM on a dual-socket NUMA node.
- `shared_buffers` 128 GiB.
- 200 application connections via PgBouncer.
- Query workload with sort/hash operations and parallel workers.
- Two physical standbys.
- `PGDATA` and `pg_wal` on separate persistent volumes.
- Pod memory limit 160 GiB.
- Node has reserved a pool of 2 MiB huge pages.
- Small default `/dev/shm`.
- Backup staging uses ephemeral storage.

Design:

1. A memory budget including shared memory, `work_mem` exposure, workers, OS, and headroom.
2. Huge page count estimate, host reservation, and PostgreSQL `huge_pages` mode.
3. THP/NUMA policy and benchmarking approach.
4. Swap/OOM policy and cgroup v2 metrics.
5. CPU requests/limits to avoid excessive throttling.
6. `/dev/shm` sizing and dynamic shared memory configuration.
7. `PGDATA`/`pg_wal` persistent volume capacity and durability checks.
8. Inode, temp, archive, and backup staging monitoring.
9. Kubernetes hugepages resources, scheduling, and pod restart policy.
10. Runbooks for OOM, disk full, WAL retention, and huge page startup failure.

## Conclusion

**Tuning PostgreSQL resources requires accounting for shared memory, private memory, the OS, storage, and runtime limits together.** Explicit huge pages can cut page-table overhead for large shared memory, yet require proper page-size reservation, permissions, and mapping verification. THP is a separate mechanism and must be evaluated independently. Swap can act as a buffer under brief memory pressure, yet sustained swap-in/out usually signals sizing or concurrency issues needing investigation.

The filesystem must deliver reliable durability semantics for WAL/data, sufficient bytes and inodes, and appropriate I/O latency/throughput. Monitor `PGDATA`, `pg_wal`, tablespaces, temp, logs, and backup staging individually. Keep `fsync`/`full_page_writes` aligned with durability policy; never delete WAL or relation files manually to reclaim disk space.

Inside containers, effective limits come from cgroups and orchestrators. Spare host RAM does not prevent container OOMs; CPU quotas can throttle queries and replay; `/dev/shm` and ephemeral storage impose separate limits. Use persistent volumes for durable data, and size memory budgets for sidecars, query concurrency, and headroom.

Finally, establish baselines, load test under exact container limits, monitor cgroup/host/PostgreSQL metrics, and rehearse OOM/disk/restore procedures in controlled environments. **A sound configuration is one with adequate headroom, clear durability, and verification under realistic workloads.**
