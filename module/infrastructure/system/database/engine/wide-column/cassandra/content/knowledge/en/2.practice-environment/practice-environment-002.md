# Preparing CPU, RAM, Disk, OS, and Time Synchronization

## 1. Objectives and Relevance to Cassandra

Apache Cassandra is a **distributed wide-column** database. Every node simultaneously handles CQL queries, writes to the commit log, holds data in memtables, flushes to SSTables, compacts SSTables, and exchanges data with replicas. Therefore, preparing the environment is not just about "getting the database installed": CPU, RAM, disk space, the operating system, and the system clock all affect learning **partition keys, query-driven table design, replication, consistency levels, compaction, repair, failure handling, and Java connectivity**.

By the end of this lesson, you will be able to:

1. Choose appropriate resources for a single-node lab and a multi-node lab, and distinguish them from production requirements.
2. Explain where CPU is spent, how RAM is split across heap/off-heap/page cache, and why Cassandra needs free disk space during compaction/repair.
3. Inspect resources on Linux, Windows/macOS with Docker, and inside the container.
4. Create a Cassandra 5.0.9 node with resource limits, a data volume, and verification steps.
5. Verify time synchronization across host/VM/container and explain the impact of clock skew on **last-write-wins**.
6. Diagnose CPU starvation, OOM, full disk, and clock drift errors.

> **Lab limitation:** the guide below uses Docker and a single node to verify resources. It does not replace performance benchmarking, capacity planning, failure domain design, or hardware selection for a production cluster.

## 2. Selecting Hardware Specifications by Purpose

### 2.1. Reference Baselines

| Environment | Reference CPU | Reference RAM | Disk and Purpose |
|---|---|---|---|
| **1-node lab** | Host with at least ~2–4 usable CPU threads; test allocating up to 2 CPUs to the container | Host from **8 GiB**; test allocating **4 GiB** to container; 16 GiB host is comfortable if running a Java IDE | SSD with **20 GiB or more** free for image, volume, logs, and small datasets |
| **3-node lab on same machine** | Around 6+ CPU threads so nodes contend less for CPU; in practice CPU can be shared | Host **24 GiB or more** is comfortable when giving 4 GiB per node and leaving RAM for OS/Java/Docker | SSD with **60 GiB or more** free for lab data and streaming/compaction operations |
| **Production, per node** | Apache docs list a minimum of **2 cores**, real systems typically use **8+ cores** | Minimum **8 GiB**, typical systems usually **32 GiB or more** | Sized by data volume, RF, growth rate, throughput, IOPS, compaction, repair, and headroom |

The **lab** figures are **starting recommendations**, not Apache-guaranteed minimums. A machine with less RAM can still start Cassandra for experiments, though it may OOM or take very long to start. Conversely, using lab specs for production sizing is unsafe. Apache documents **production** baselines in [Hardware Choices](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/hardware.html); real sizing must be based on benchmarks and query characteristics.

**Distinguishing three resource layers:**

```text
Physical machine / host OS: CPU, RAM, SSD, system clock
  └── Docker Engine or Docker Desktop VM (Windows/macOS)
        └── Cassandra container: CPU quota / memory limit
              ├── JVM heap + off-heap + process memory
              └── /var/lib/cassandra: commitlog, SSTables, caches, hints
```

On Linux, containers share the kernel with the host. On Windows/macOS, Docker Desktop typically runs Linux containers inside a VM; **RAM and disk allocated to the VM** can be smaller than total physical RAM/disk. `docker stats` only shows container resources; it does not prove the host or VM has enough capacity for all operations.

A **3-node cluster on a single laptop** lets you practice consistency levels and replication logic, but if the laptop powers off, all 3 nodes go down together: it does not represent 3 independent failure domains.

### 2.2. Recording Baseline Metrics Before Installing Cassandra

On **Linux**, run on the host:

```bash
uname -srm
nproc
free -h
df -h .
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

On **Windows PowerShell**:

```powershell
Get-CimInstance Win32_Processor | Select-Object NumberOfLogicalProcessors
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
Get-PSDrive -PSProvider FileSystem
wsl --status
[DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
```

On **macOS**, basic commands are:

```bash
sw_vers
sysctl -n hw.logicalcpu
sysctl -n hw.memsize
df -h .
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

`TotalPhysicalMemory` and `hw.memsize` return **bytes**; convert them to GiB when filling out your table. `df -h .` reports the filesystem holding the **current working directory**, which may differ from where Docker actually stores images/volumes. On Docker Desktop, also check the VM/disk allocation in Docker Desktop settings; if using WSL2, confirm the WSL2 VM is operational.

## 3. CPU: Reserving Capacity for Both Queries and Background Work

Cassandra handles many requests concurrently. On writes, the node appends to the commitlog and updates the memtable; on reads, it accesses memtables/SSTables and merges results. Background tasks also consume significant CPU:

| Task | Why CPU is needed | Symptoms when CPU-starved |
|---|---|---|
| CQL processing and partition-key routing | Request parsing, replica coordination, result merging | Higher p95/p99 latency; request timeouts |
| Flush and **compaction** | Writing, compression/decompression, merging SSTables | Growing pending compactions, high I/O |
| Repair and streaming | Comparing/exchanging data across nodes, checksum calculation | Slow repairs, degraded query latency |
| JVM garbage collection | Reclaiming Java memory | Longer GC pauses under CPU contention |
| Java driver/application | Threads/event loops, serialization, response handling | Slow application even when Cassandra is not overloaded |

In Docker, `--cpus=2` means the container can consume at most roughly **two CPUs worth of compute time** per quota, **not** two dedicated physical cores. `--cpuset-cpus` pins processes to specific CPUs, which is normally unnecessary for labs.

Useful observation commands:

```bash
# After creating the container in section 6:
docker stats --no-stream cassandra-resources-lab
docker exec cassandra-resources-lab nodetool tpstats
docker exec cassandra-resources-lab nodetool compactionstats
```

`nodetool tpstats` shows thread pools and queues; `compactionstats` shows active or pending compaction tasks. Do not jump to "CQL is slow due to lack of CPU" from a single `docker stats` sample: inspect I/O, memory, query patterns, contention, and GC as well.

## 4. RAM: JVM Heap Is Only Part of Cassandra's Memory Usage

Simplified layout:

```text
RAM allocated to node/container
├─ Java heap (Xmx): objects and JVM-managed structures
├─ Off-heap/native: bloom filters, compression metadata, direct buffers...
├─ Memory for threads, JVM, and native libraries
└─ OS memory / page cache: accelerates reading SSTables from disk
```

**Never allocate all RAM to the heap.** Apache recommends production heap sizes generally be **at least 2 GiB** and **no more than 50% of node RAM**; the rest serves off-heap, page cache, and the OS. Exact sizing depends on Cassandra version, GC, dataset size, and deployment model. A container limit of **4 GiB** and heap of **2 GiB** is strictly a starting lab configuration, not guaranteed for heavy workloads.

Key points to remember:

- Host Java for running the **Java application/driver** is a separate process; Cassandra's JVM runs inside the container when using a Docker image.
- `--memory=4g` is the **container memory limit**, not just the Java heap limit. Heap, off-heap, native memory, and overhead combined must stay within that limit.
- `MAX_HEAP_SIZE=2G` is the heap environment variable supported by the Cassandra Docker image. When using G1GC, do not arbitrarily set `HEAP_NEWSIZE` as that option belongs to a different GC setup.
- `--memory-swap=4g` alongside `--memory=4g` disables extra swap beyond the Docker memory limit. This avoids slow swapping in the lab but triggers OOM errors if memory is insufficient; monitor and increase RAM when needed.
- Making the heap too large shrinks available page cache and can worsen GC pauses. Do not fix every memory issue by increasing `-Xmx`.

When the node is running:

```bash
docker stats --no-stream cassandra-resources-lab
docker exec cassandra-resources-lab nodetool info
docker inspect --format "{{.HostConfig.Memory}}" cassandra-resources-lab
docker inspect --format "{{.State.OOMKilled}}" cassandra-resources-lab
```

`HostConfig.Memory` reports **bytes**; `OOMKilled=true` indicates the container was killed by the kernel due to OOM in its current run state. If the container is still running, check `docker logs` and `docker stats`; if stopped, inspect `docker inspect` and logs to confirm—never guess the cause just because the process disappeared.

## 5. Disk: Accounting for Commitlog, SSTables, Compaction, and Repair

### 5.1. Why "Enough Space for Data" Is Not Enough

During writes:

1. Cassandra appends mutations to the **commitlog** and updates the **memtable**.
2. Memtables flush into **immutable SSTables** on disk.
3. SSTables undergo **compaction**: new SSTables are written before old SSTables can be reclaimed.
4. Repair, bootstrap/streaming, snapshots, and compaction strategy changes can require extra I/O or temporary space.

Because SSTables are immutable, **UPDATE/DELETE does not overwrite old files in place**; obsolete records and tombstones remain until cleanup conditions and compaction run. During compaction, old and new files coexist on disk temporarily. A node with only a few gigabytes free can still run out of disk during a large rewrite.

| Storage Area | Role | What to Watch |
|---|---|---|
| `data_file_directories`, default under `/var/lib/cassandra/data` in image | SSTables and data storage components | Grows with replication factor, compression, tombstones, compaction |
| `commitlog_directory`, default `/var/lib/cassandra/commitlog` | Recovers unflushed writes on node restart | Sequential writes, needs steady I/O |
| `saved_caches_directory`, default under `/var/lib/cassandra/saved_caches` | Persisted caches on disk | Does not replace OS page cache |
| Hints, logs, snapshots | Operational and recovery support | Can consume disk outside active serving SSTables |

Apache hardware guidance recommends fast local storage; avoid assuming **NFS/SAN** is ideal for Cassandra data. In real deployments, SSD/NVMe, stable Linux filesystems like XFS/ext4, and monitoring **latency/IOPS** matter more than raw GB alone. If using multiple physical HDDs, consider separating commitlog and SSTables to avoid mechanical contention, following hardware guidance and deployment architecture.

### 5.2. Rough Capacity Sizing Example

Suppose a system has **12 GiB of physical compressed data for one replica**, replication factor `RF=3`, and **3 balanced nodes** in a single datacenter:

```text
Cluster-wide replica size ≈ 12 GiB × 3 = 36 GiB
Baseline data per node ≈ 36 GiB / 3 = 12 GiB
```

Adding an illustrative **12 GiB/node** headroom for growth and temporary operations yields **24 GiB/node** before adding commitlog/logs/snapshots. This is **not** an official sizing formula: partition skew, compression, indexes, TTLs, tombstones, strategies like LCS/TWCS/UCS, repairs, and backups can substantially change actual usage. Production sizing must measure real data, growth patterns, and worst-case scenarios.

During operation, inspect:

```bash
docker exec cassandra-resources-lab sh -c "df -h /var/lib/cassandra"
docker exec cassandra-resources-lab sh -c "du -sh /var/lib/cassandra/data /var/lib/cassandra/commitlog"
docker exec cassandra-resources-lab nodetool compactionstats
docker system df
```

`df -h` shows free space on the volume's filesystem; `du -sh` shows current directory sizes. `docker system df` reflects all Docker images/containers/caches/volumes and is **not equivalent** to free space on the filesystem mounted into Cassandra. Never manually delete SSTables or commitlogs just because disk space looks low: doing so can corrupt or lose data.

### 5.3. Choosing a Volume to Preserve Data Across Container Recreation

The lab example uses a **Docker named volume**:

```bash
docker volume create cassandra_resources_data
```

When running Cassandra, mount `-v cassandra_resources_data:/var/lib/cassandra`. A named volume preserves data across container stops/removals **as long as the volume is not deleted**. On Windows/macOS with Docker Desktop, prefer Docker's Linux volumes for database I/O; bind mounts into Windows/macOS host folders can have different filesystem semantics and performance.

## 6. Preparing the OS and Starting a Resource-Limited Lab

### 6.1. Pre-Flight Checks

- **Linux:** kernel and Docker Engine running, user authorized for Docker; check `df`, RAM, cgroups, and permissions on data paths. For bare-metal Linux multi-node setups, review ulimits/file descriptors, swap, filesystems, networking, and production recommendations.
- **Windows:** run **Linux containers** via Docker Desktop (typically WSL2). Verify virtualization is enabled, WSL2/VM has enough RAM/disk, and Docker Engine is running; Windows containers are not suitable for this Linux image.
- **macOS:** use Docker Desktop with its Linux VM, check VM memory/disk settings and CPU-compatible image architecture.
- **All environments:** host port `9142` is free; Docker can pull `cassandra:5.0.9`; never use a machine serving production workloads to test OOM limits.

Docker checks from the host terminal (PowerShell or shell):

```bash
docker version
docker info
docker image inspect cassandra:5.0.9
```

If the image is missing, `docker image inspect` reports not found; pull it first:

```bash
docker pull cassandra:5.0.9
```

### 6.2. Running a Dedicated Node for This Lesson

To avoid port `9042` conflicts with other labs, this example maps **host 9142 → container 9042**. Single-line command usable in PowerShell, Bash, or any Docker CLI terminal:

```bash
docker run -d --name cassandra-resources-lab --cpus=2 --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=resources-lab -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=datacenter1 -e CASSANDRA_RACK=rack1 -p 127.0.0.1:9142:9042 -v cassandra_resources_data:/var/lib/cassandra cassandra:5.0.9
```

Parameters:

| Parameter | Effect |
|---|---|
| `--cpus=2` | Caps total CPU time usage to the equivalent of 2 CPUs |
| `--memory=4g` | Caps container RAM, covering all memory consumers beyond the heap |
| `--memory-swap=4g` | Grants no extra swap to the container beyond the RAM limit |
| `MAX_HEAP_SIZE=2G` | Sets a 2 GiB JVM heap for the experiment while leaving room for native/off-heap/page cache |
| `-p 127.0.0.1:9142:9042` | Host apps connect to `127.0.0.1:9142`, inside the container port stays `9042` |
| `-v ...:/var/lib/cassandra` | Persists data into the named volume |
| `CASSANDRA_DC=datacenter1` and snitch | Identifies the datacenter for topology and Java driver practice |

This command assumes the machine has **at least 4 GiB of real RAM available to Docker/container** with RAM left for the host. If not, **allocate more memory to the Docker VM/host** before retrying; do not set heap too large or lower container limits so far that the node repeatedly OOMs.

### 6.3. Verifying the Node and Resources

```bash
docker ps --filter name=cassandra-resources-lab
docker logs cassandra-resources-lab
docker stats --no-stream cassandra-resources-lab
docker exec cassandra-resources-lab nodetool status
docker exec cassandra-resources-lab nodetool info
docker exec cassandra-resources-lab cqlsh -e "SELECT release_version, data_center, cluster_name FROM system.local;"
```

Wait until `nodetool status` reports the node as **`UN`** (*Up/Normal*). `docker run -d` succeeding **does not mean** Cassandra is ready for CQL yet. `cqlsh` running **inside the container** uses the default port `9042`; Java programs running on the host will use `127.0.0.1:9142` and local datacenter `datacenter1`.

To see volume space as seen by Cassandra:

```bash
docker exec cassandra-resources-lab sh -c "df -h /var/lib/cassandra"
docker volume inspect cassandra_resources_data
```

`docker volume inspect` reports metadata/mountpoint from Docker Engine's perspective; on Docker Desktop, that mountpoint lives inside the Linux VM, not necessarily as a directly accessible Windows/macOS path.

### 6.4. Checking the Disk Impact of Flush

Run a small CQL sequence to produce observable data:

```bash
docker exec cassandra-resources-lab cqlsh -e "CREATE KEYSPACE IF NOT EXISTS resource_lab WITH replication = {'class':'SimpleStrategy', 'replication_factor':1};"
docker exec cassandra-resources-lab cqlsh -e "CREATE TABLE IF NOT EXISTS resource_lab.events_by_user (user_id text, event_id timeuuid, payload text, PRIMARY KEY ((user_id), event_id));"
docker exec cassandra-resources-lab cqlsh -e "INSERT INTO resource_lab.events_by_user (user_id, event_id, payload) VALUES ('u-1', now(), 'demo');"
docker exec cassandra-resources-lab cqlsh -e "SELECT * FROM resource_lab.events_by_user WHERE user_id='u-1';"
docker exec cassandra-resources-lab nodetool flush resource_lab events_by_user
docker exec cassandra-resources-lab nodetool tablestats resource_lab
docker exec cassandra-resources-lab sh -c "du -sh /var/lib/cassandra/data /var/lib/cassandra/commitlog"
```

`flush` explicitly writes the memtable to SSTables to illustrate the storage engine. Because the sample data is tiny, disk size changes may appear rounded and are unsuitable for throughput benchmarking or production size estimation. `SimpleStrategy` with RF=1 is strictly **for a single-node lab**; when deploying across multiple nodes, racks, and datacenters, learn and use an appropriate `NetworkTopologyStrategy`.

## 7. Time Synchronization: A Requirement for Data Correctness

### 7.1. Why Does Cassandra Need Accurate Clocks?

Cassandra attaches a **mutation timestamp** to changes and resolves conflicts using **last-write-wins**: among competing values for the same cell, the larger timestamp generally wins. Timestamps can be **supplied by the client** or generated by the **coordinator** when omitted by the client. Consequently:

- If node A's clock runs **fast**, a write via A may receive a larger timestamp than a later real-time write via node B.
- Data written later at B with a smaller timestamp may lose the conflict unexpectedly.
- Clock drift makes TTLs, expirations, tombstones, logs, and incident debugging confusing.
- **Replication factor** and **consistency level** cannot repair bad timestamps from the source; time synchronization is essential for predictable behavior.

This is why Cassandra's [Dynamo architecture documentation](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html) emphasizes running a time sync service such as **NTP**.

Logical example: the first write carries timestamp `2000` and value `A`; a write sent **later** carries timestamp `1999` and value `B`. For the same cell, Cassandra retains `A` because its timestamp is larger; the order in which the application sent requests **does not override** timestamp order. Skewed clocks across client/coordinator or incorrect `USING TIMESTAMP` values can create this exact situation.

### 7.2. Distinguishing Time Zones from Clocks

| Concept | Example | Conclusion |
|---|---|---|
| Display time zone | Linux uses UTC, personal laptop displays UTC+7 | The same instant in time displays differently; **not a sync error** |
| Clock synchronization | Node clocks follow a reliable NTP source together | Ensures timestamps reflect a shared timeline |
| Clock skew | One node is 90 seconds fast despite both displaying UTC | Can invert mutation timestamp ordering and affect data |
| Client-supplied timestamp | Java/driver or CQL sets an arbitrary timestamp | Server clock sync **cannot prevent** bad client timestamps |

In Java, use explicit time APIs like `Instant` when working in UTC; avoid generating custom mutation timestamps from unsynchronized machine clocks. In labs, always compare **UTC**—never treat the difference between two local time strings in different time zones as proof of clock skew.

### 7.3. Checking NTP on the Host and UTC in the Container

On a **Linux host using systemd**:

```bash
timedatectl status
timedatectl show -p NTPSynchronized --value
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

If the host uses **chrony**, inspect sync quality:

```bash
chronyc tracking
chronyc sources -v
```

Not every environment has `chronyc` or `timedatectl` (e.g., minimal containers or WSL without those services). When a command is missing, verify the time sync service running on the **actual host or VM** rather than treating "command not found" as proof of clock drift.

On a **Windows host** (PowerShell):

```powershell
[DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
w32tm /query /status
```

`w32tm` reflects Windows Time status if the service is active; if no valid source/info appears, check **Set time automatically** and Windows/VM time sync settings. On **macOS**, run `date -u` and verify automatic date & time settings in System Settings.

Check UTC time inside the container:

```bash
docker exec cassandra-resources-lab date -u +"%Y-%m-%dT%H:%M:%SZ"
```

Run the host and container commands back-to-back. Results should match within reasonable typing/execution latency. If a persistent discrepancy appears, inspect NTP and the clock of the **Docker host/VM**. Normal containers share the Linux host/VM kernel clock, so changing time zones or trying to run NTP inside a container **does not fix the root cause** of a drifted VM clock.

In multi-machine clusters, synchronize **all nodes**, as well as machines **that may generate client-side timestamps**. Continuously monitor clock offset and sync source status in operations rather than checking only once at setup.

### 7.4. Optional Lab Demonstrating Timestamp Semantics

The following example uses **manually supplied timestamps** to demonstrate last-write-wins **without altering the system clock**:

```sql
CREATE KEYSPACE IF NOT EXISTS time_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS time_lab.cell_demo (
    id text PRIMARY KEY,
    value text
);

INSERT INTO time_lab.cell_demo (id, value)
VALUES ('same-key', 'written-first')
USING TIMESTAMP 1780000000000000;

UPDATE time_lab.cell_demo
USING TIMESTAMP 1770000000000000
SET value = 'sent-later-smaller-timestamp'
WHERE id = 'same-key';

SELECT id, value, WRITETIME(value)
FROM time_lab.cell_demo WHERE id = 'same-key';
```

Run these statements inside `docker exec -it cassandra-resources-lab cqlsh`. The expected value remains `written-first` because `1780000000000000 > 1770000000000000` (microseconds since Unix epoch). This example intentionally injects timestamps and does not measure real skew. Afterward, keep the output as evidence or drop the **lab** keyspace deliberately; do not use `USING TIMESTAMP` arbitrarily on business data.

## 8. Common Issues and Troubleshooting

| Symptom | Possible Cause | Evidence to Gather and Remediation |
|---|---|---|
| Container starts and exits immediately | OOM, JVM error, volume/permissions, filesystem | Check `docker logs`, `docker inspect --format "{{.State.OOMKilled}}"`, `docker stats`, and disk state; allocate proper resources |
| `docker ps` shows container up, CQL refuses connection | Cassandra still booting, CPU/disk very slow | Wait for `UN` in `nodetool status`, inspect logs and I/O; verify port mapping |
| Java `OutOfMemoryError` | Insufficient heap, workload exceeds memory, leak, or native memory/GC | Distinguish JVM error from kernel OOM; inspect GC/heap, off-heap, and container limit before raising heap |
| `OOMKilled=true` | Total process memory exceeded cgroup or host ran out of RAM | Check limits, container metrics, and OS logs; add RAM/reduce load instead of just raising Xmx |
| Slow queries, CPU near 100% | High request rate, compaction/repair CPU contention, GC | Measure latency, `tpstats`, `compactionstats`, GC, and CPU quota; change one variable at a time and re-test |
| `No space left on device` | SSTables, commitlog, snapshots, or compaction need more room | Check `df -h /var/lib/cassandra`, `du -sh`, and host/VM; add capacity safely |
| Host `df` shows plenty of space, Cassandra reports disk full | Docker volume resides on another filesystem/VM, or VM has its own disk cap | Run `df` **inside the container at the volume**, check Docker Desktop/WSL disk image |
| Reads/writes show unexpected chronological results | Clock skew, client timestamps, TTL/tombstones, different partitions | Check `WRITETIME`, node/client UTC/NTP; analyze timestamps, consistency, and keys |
| Host/VM clock drifts after sleep/resume | Time sync service/VM has not resynchronized clock | Re-check host/VM NTP and UTC across nodes before resuming distributed experiments |
| CQL reads succeed yet repair/compaction fails | Insufficient disk or heavy I/O throttling | Inspect `compactionstats`, disk usage, and logs; never assume "node UN = completely healthy system" |

A sound troubleshooting sequence is **record symptom → collect logs/metrics → identify bottleneck → apply controlled change → re-measure**. In a lab, you can recreate the container from the pinned image; where data must be preserved, protect the volume and follow a recovery procedure before altering storage settings.

## 9. Completion Checklist and Self-Check Exercises

### 9.1. Environment Preparation Record

Fill in **actual** observed values rather than copying example values verbatim:

| Check Item | Recorded Value |
|---|---|
| Host OS and CPU architecture | OS version, `amd64/arm64`, logical CPUs |
| Host RAM and Docker/VM RAM | Total, available, VM limit if applicable |
| Cassandra container limits | `--cpus`, `--memory`, `--memory-swap`, `MAX_HEAP_SIZE` |
| Disk/volume | Storage type, filesystem, `df -h` at `/var/lib/cassandra` |
| Cassandra image | `cassandra:5.0.9`, image digest if exact reproducibility is needed |
| Node status | `nodetool status` shows `UN` |
| CQL | `release_version` and `data_center` |
| Time sync | Host/VM NTP status; host and container UTC; offset if measured |
| Workload observation | `docker stats`, `nodetool tpstats`, `nodetool compactionstats` |

### 9.2. Practice Questions

1. A machine has 8 GiB RAM and runs both a Java IDE and Docker Desktop. Why can giving `--memory=8g` to Cassandra still starve the system of RAM even when JVM heap is set to only 2 GiB?
2. A node has 12 GiB of active SSTables and only 2 GiB of free disk space. Why can a compaction cycle fail even with no new INSERTs?
3. `docker stats` shows CPU near the 2-CPU quota while `nodetool compactionstats` shows an active task. Which measurements help separate compaction overhead from queries using the wrong partition key?
4. A Windows laptop has 100 GiB free on `D:`, yet the Cassandra container reports disk full. At **which layer** should you check disk usage before concluding Docker is broken?
5. Nodes A and B display different local time zones, yet `date -u` matches. Is that clock skew? Conversely, if one node runs 1 minute fast, what consequence can last-write-wins suffer?
6. A later write uses `USING TIMESTAMP` with a smaller value than an earlier write. Will adding replicas and querying with `QUORUM` make the newer value win?
7. Is a 3-node setup running on one machine enough to test losing an entire datacenter or independent power failure? Contrast logical testing with production topology.

**Passing criteria:** you know available host and VM CPU/RAM/disk, have the lab node running in `UN` state, query CQL via `cqlsh`, use a named volume, inspect RAM/CPU/disk inside the container, and identify the host's time sync source. Learners can explain why low disk affects compaction/repair and why skewed timestamps can make Cassandra results differ from application write order.

### 9.3. Stopping the Lab While Keeping Data

```bash
docker stop cassandra-resources-lab
docker rm cassandra-resources-lab
docker volume ls --filter name=cassandra_resources_data
```

These commands stop/remove the container **without deleting the named volume**. If you recreate the container using the **same Cassandra version** and re-attach the volume, lab data persists in the volume (provided the volume wasn't deleted). When switching to another Cassandra version, follow upgrade rules; never arbitrarily attach data back to an older version.

## 10. References

- [Apache Cassandra — Hardware Choices](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/hardware.html): production CPU/RAM baselines, heap/off-heap usage, and disk choices.
- [Apache Cassandra — Compaction Overview](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/overview.html): immutable SSTables, compaction, and storage overhead.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html): mutation timestamps, last-write-wins, and NTP requirements.
- [Apache Cassandra — Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html): replication strategy and production cluster settings.
- [Docker Docs — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU quota, memory limits, memory-swap, and OOM.
- [Docker Hub — Official Cassandra image](https://hub.docker.com/_/cassandra): tags, environment variables, and Docker examples.
- [Docker Docs — WSL2 backend](https://docs.docker.com/desktop/features/wsl/): how Docker Desktop uses WSL2 on Windows.
