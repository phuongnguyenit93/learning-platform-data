# Shared Filesystems, Input Data, and Cluster I/O Bottlenecks

In a High-Performance Computing (HPC) cluster, multiple compute nodes routinely need to read the same datasets, write results, and save checkpoints while jobs run in parallel. A shared filesystem provides a common file namespace so nodes access data via identical paths. This organization is convenient for applications requiring POSIX file semantics, yet it creates a shared resource: if too many nodes read, write, or look up metadata simultaneously, storage and networking can become bottlenecks even while CPUs sit idle.

Cluster I/O performance depends simultaneously on multiple factors: aggregate bandwidth, IOPS, latency, metadata processing speed, file sizes, data layout, client count, and application access patterns. Therefore, HPC storage design must start from the workload's actual access pattern, then select an appropriate shared filesystem, parallel filesystem, object storage, or local disk.

After this lesson, you will be able to:

- Distinguish shared filesystems from parallel filesystems and object storage.
- Choose ways to deliver input data to compute nodes without creating unnecessary I/O load.
- Identify bottlenecks in metadata, bandwidth, IOPS, latency, and networking.
- Design scratch, checkpoint, and output areas for multi-node workloads.
- Measure and verify filesystem performance before scaling up the cluster.

## 1. Shared Filesystems in an HPC Cluster

A shared filesystem lets multiple nodes mount the same filesystem and see the same namespace, directories, and files. For example, login nodes, controller nodes, and compute nodes can all access `/shared/project-a`. Users can stage data once, submit jobs to the scheduler, and let nodes read files from a unified location.

Common cloud services include:

- **Managed NFS file storage:** such as Amazon EFS, Google Cloud Filestore, or Azure NetApp Files. NFS suits many workloads sharing directories, home directories, scripts, libraries, and moderately parallel data. Check throughput, IOPS, latency, client limits, and tier characteristics.
- **Parallel filesystems:** such as Amazon FSx for Lustre or Azure Managed Lustre. These systems are engineered for large-scale parallel access, typically striping data across multiple storage targets and supporting high-throughput read/write workloads. Configure clients, networking, striping, and capacity per service guidelines.
- **Object storage:** such as Amazon S3, Azure Blob Storage, or Google Cloud Storage. Object storage scales broadly and suits storing datasets, archives, long-term outputs, and shared data repositories. It does not natively provide POSIX semantics like a mounted filesystem; applications usually access it via APIs or sync/staging tools.

Shared filesystems and parallel filesystems are not strictly synonymous. An NFS system can be shared across many nodes while still having centralized throughput or metadata service limits. Parallel filesystems are architected to distribute data and serve many concurrent clients. Product names alone are insufficient to guarantee performance; examine configuration, quotas, service limits, and benchmarks on real workloads.

### Components of the I/O Path

A read operation from a compute node traverses the following layers:

1. The application invokes `open`, `stat`, `read`, or `write` on the mounted path.
2. The kernel and filesystem client handle caching, metadata, and I/O requests.
3. Requests traverse the cluster network to the metadata service or filesystem servers.
4. The storage service locates data, reads/writes blocks, and returns results.
5. Data returns to the client and may be cached in node memory.

In distributed filesystems, metadata and file contents may be served by separate components. Metadata includes filenames, directories, permissions, sizes, timestamps, and data layout mappings. A workload creating millions of small files can overload the metadata service even when total bytes read are small. Conversely, a job sequentially reading large files is primarily bounded by data bandwidth.

## 2. Selecting a Filesystem by Access Pattern

Before choosing a service, characterize the workload with these questions:

- Do many nodes read the same file, or does each node read its own shard?
- Are files mostly large and read sequentially, or vast numbers of small files with constant open/close calls?
- Do nodes only read, or write concurrently to a single file?
- Are file locking, atomic renames, POSIX permissions, or shared directories required?
- How many nodes access concurrently, and what aggregate throughput does the data require?
- Is the data immutable input, temporary scratch, checkpoints, or long-term output?

| Workload pattern | Typically suitable storage approach | What to verify |
|---|---|---|
| Home directories, scripts, configs, and moderate shared data | Managed NFS file storage | Metadata latency, quotas, client count, permissions, and throughput |
| Multiple nodes reading/writing large files in parallel | Parallel filesystem | Aggregate bandwidth, stripe layout, client tuning, and network throughput |
| Large, rarely changing datasets reused across runs | Object storage as system of record; stage to filesystem or local scratch at runtime | Load times, request/egress costs, manifest consistency, and data versioning |
| Temporary, intermediate, or per-node scratch files | Local NVMe/SSD or instance storage | Data may be lost when the node stops; requires stage-in/stage-out steps |
| Checkpoints needed for failure recovery | Shared/parallel filesystem or object storage per checkpoint design | Write frequency, checkpoint size, integrity, and recovery time |

A cluster can combine multiple storage tiers simultaneously: object storage as the canonical dataset store, a parallel filesystem as the high-speed working tier, local NVMe as CPU-adjacent scratch, and shared NFS for home directories or configuration files. Tiering lets each data class live where it matches its lifespan and access pattern.

## 3. Delivering Input Data to Compute Nodes

Moving inputs to the cluster is part of performance design. If every node independently downloads the entire dataset from object storage when a job starts, hundreds of nodes can simultaneously generate massive request bursts and traffic. This phenomenon is commonly called a *thundering herd*. It inflates job startup time, request counts, data transfer costs, and load on the network or storage service.

A controlled staging workflow typically includes:

1. Store the canonical dataset in versioned object storage or a shared filesystem.
2. Generate a manifest specifying names, sizes, checksums, and versions for each data part.
3. Shard the dataset according to the algorithm's partitioning so each node downloads only what it needs.
4. If multiple nodes need the same data, stage once into a shared/parallel filesystem or use a controlled cache rather than downloading duplicates.
5. For intermediate files read repeatedly on a single node, copy them to local SSD/NVMe if capacity and load time allow.
6. After job completion, stage out outputs needing long-term retention to durable storage and clean temporary scratch per policy.

### Example: Staging Input Shards to Per-Node Scratch

With Slurm jobs, some environments provide a temporary directory via `SLURM_TMPDIR`. If the dataset is pre-sharded, each task can extract its corresponding shard to the node's local scratch, run its assigned computation, and write outputs to a dedicated directory:

```bash
#!/bin/bash
#SBATCH --job-name=matrix-run
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=1

set -euo pipefail

srun bash -c '
  set -euo pipefail
  WORKDIR="${SLURM_TMPDIR:-/tmp}/matrix-${SLURM_JOB_ID}-${SLURM_PROCID}"
  SHARD="/shared/datasets/matrix-case-07/node-${SLURM_PROCID}.tar"
  mkdir -p "$WORKDIR/input" "$WORKDIR/output"
  test -f "$SHARD"
  tar -xf "$SHARD" -C "$WORKDIR/input"

  ./solver --input "$WORKDIR/input" --output "$WORKDIR/output"

  RESULT_DIR="/shared/results/${SLURM_JOB_ID}/rank-${SLURM_PROCID}"
  mkdir -p "$RESULT_DIR"
  cp -a "$WORKDIR/output/." "$RESULT_DIR/"
'
```

This example assumes one task per node, `SLURM_PROCID` is a unique task index, and the matching shards are pre-staged on the shared filesystem. `srun` executes the staging block on each node so each task uses that node's local scratch; outputs are also written to rank-specific directories to avoid overwrites. For MPI applications with multiple ranks per node, stage once per node via a job prolog, data-prep step, or the scheduler's node-local staging mechanism rather than re-extracting the same shard for every rank. Verify scratch variables, write permissions, capacity, and how the scheduler distributes tasks in your actual environment.

If a dataset contains millions of small files, packing them into archives or container data formats reduces metadata operations during transfer. However, archiving also consumes CPU and temporary space; measure total stage, unpack, and read times before deciding. For data that can be read directly by region, chunked formats like HDF5, NetCDF, or Zarr can serve needed slices, provided chunks/shards are configured to match the application's access pattern.

## 4. Identifying I/O Bottlenecks

Not every I/O problem is a bandwidth shortage. A job can run slowly due to heavy metadata operations, many small requests, network latency, multi-node write contention, or misconfigured clients.

### Aggregate Bandwidth vs. Per-Node Bandwidth

Aggregate bandwidth is the total data rate the filesystem serves to the entire cluster per second. Per-node bandwidth is what a single node actually receives. If a filesystem delivers 20 GB/s to a 100-node cluster, an ideal even split is 200 MB/s per node; in reality, it depends on data distribution, networking, clients, and competing jobs. Adding nodes does not guarantee linear speedup if the filesystem or network has already hit its ceiling.

### IOPS and I/O Size

IOPS measures read/write operations per second. At the same bandwidth, many small operations consume far more IOPS and protocol overhead than a few large operations. For example, reading 1 million 4 KB files can be orders of magnitude slower than sequentially reading one 4 GB file, despite identical total bytes. Coalescing files, enlarging buffers, or reading in larger blocks can boost performance if the application permits.

### Metadata and Large Directories

`stat`, `open`, `close`, `mkdir`, `rename`, and directory listings all generate metadata load. A job launching thousands of processes where each scans the same directory containing millions of files can choke the metadata service before data transfer even begins. Splitting directories, using manifests, reducing directory scans, caching metadata sensibly, and avoiding opening the same file set from every rank reduce load.

### Latency, Contention, and Concurrent Writes

Latency-sensitive applications can suffer even when aggregate throughput has headroom. Multiple nodes writing to the same file may trigger locking or synchronization, causing contention and hurting parallelism. When possible, have each rank or node write to its own file, then merge in a final step. If shared writes are mandatory, use formats and libraries supporting parallel I/O such as MPI-IO or parallel HDF5, and confirm the filesystem supports the required access mode.

### Network and Data Locality

Remote filesystems depend on network bandwidth and latency between nodes and storage. I/O traffic can compete with MPI communication if both share the same network infrastructure. Inspect instance types, network bandwidth, placement, subnet paths, and service-side limits. If data is read repeatedly, caching near compute or on local scratch cuts traffic from shared storage.

## 5. Organizing Data for Reads, Writes, and Checkpoints

### Read-Mostly Inputs

Input datasets are usually immutable during a run. Prepare data once, verify checksums, and mount read-only or stage to cache. Partitioning data so each node reads only its own slice eliminates duplicate reads. If every node needs the same large file, a parallel filesystem or distributed cache may work better than every node downloading a separate copy.

### Outputs and Temporary Files

Never let every process write to a single log or CSV file. Have each rank write to a rank- or shard-specific file; after the job, an aggregation step sorts and merges outputs. Place temporary outputs on scratch so they do not slow down shared filesystems for other jobs, then move only retained outputs to durable storage.

### Checkpoints

Checkpointing saves compute state so a job can resume after preemption, node failures, or walltime limits. If checkpoints run too often, writing data consumes too much compute time. If too rare, a failure loses hours of processing. Choose the cadence based on checkpoint write duration, interruption probability, compute duration, and desired RPO.

For large checkpoints, write in parallel across multiple files or use an MPI-aware checkpoint library. Avoid having all ranks serialize writes into a single shared file. Record checkpoint metadata, verify sizes/checksums, and mark a checkpoint complete only after every part is durably written. Prune old checkpoints under a retention policy while preserving enough committed recovery points.

## 6. Cloud Storage Service Selection Examples

| Need | Example services | Usage and considerations |
|---|---|---|
| Shared POSIX directories across multiple VMs | Amazon EFS, Google Cloud Filestore, Azure NetApp Files | Mount on nodes; monitor throughput, IOPS, metadata latency, and client count |
| High-throughput parallel I/O for HPC | Amazon FSx for Lustre, Azure Managed Lustre | Use as scratch or working filesystem; design striping, clients, and networking for the workload |
| Canonical datasets and large archives | Amazon S3, Azure Blob Storage, Google Cloud Storage | Manage versions/manifests; stage needed portions to filesystem or local scratch at runtime |
| High-speed, short-lived intermediate data | Node-local NVMe/SSD | Leverage low latency; data may be lost if the node is preempted or stopped |

For example, a GPU simulation cluster can store canonical datasets in object storage, link or stage data into FSx for Lustre, and let compute nodes read in parallel. Temporary files and intermediate shards sit on local NVMe. Critical checkpoints are written back to a shared filesystem or object storage upon completion. This design prevents every GPU node from hitting object storage directly for small operations.

For managed NFS file storage, verify client limits, throughput modes, performance relative to workload size, and behavior when multiple nodes scan directories simultaneously. For parallel filesystems, check guidance on stripe count/size, metadata capacity, client mounting, and object storage integration. Never alter striping or mount options on a production cluster without testing alongside provider guidance and representative workloads.

## 7. Benchmarking and Verifying on the Cluster

Measure layer by layer to pinpoint bottlenecks. Start with a single-node baseline, then scale up node count in fixed increments. Compare aggregate throughput and per-node throughput; if aggregate throughput plateaus as nodes increase, the filesystem, network, or metadata layer has likely hit its limit.

Useful Linux inspection commands:

```bash
# View filesystem and mount type
df -hT /shared
findmnt /shared

# Monitor local block devices
iostat -xz 1

# For NFS mounts, if tools are installed
nfsiostat 1

# For Lustre clients, view capacity and stripe layout
lfs df -h /shared
lfs getstripe /shared/dataset.bin
```

Lustre commands only work on Lustre clients and vary by version/configuration. `iostat` reflects local block devices and does not fully capture network filesystem performance; combine client, network, and storage-service metrics. `nfsiostat` provides NFS metrics if the appropriate toolkit is installed.

To measure throughput, IOPS, and latency in a controlled way, you can run `fio` against a dedicated benchmark directory without touching production data:

```bash
mkdir -p /shared/benchmark/$USER

# Pre-create a test file in the dedicated benchmark directory.
fio --name=prepare \
  --directory=/shared/benchmark/$USER \
  --filename=fio-test-file \
  --size=4G \
  --rw=write \
  --bs=1M \
  --numjobs=1 \
  --group_reporting

# Measure sequential reads on the newly created file.
fio --name=seq-read \
  --directory=/shared/benchmark/$USER \
  --filename=fio-test-file \
  --size=4G \
  --rw=read \
  --bs=1M \
  --numjobs=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

This example measures a sequential baseline with one job. When testing parallel I/O, increase `--numjobs` or run multiple clients with separate files; if using `iodepth`, select an asynchronous `ioengine` and verify the filesystem supports the chosen I/O mode. Keep `--size` and duration modest so testing does not disrupt other users. The prepare step overwrites `fio-test-file`, so only use a fresh filename in a dedicated benchmark directory; never run random writes on mounts containing live data. Record throughput, IOPS, average latency, and high percentiles—not just a single MB/s figure.

When benchmarking across multiple nodes, keep data size and runtime consistent, scale client counts incrementally, and monitor storage-side metrics. Avoid having all nodes write to the same filename. Each node or job needs its own file to prevent lock contention and reflect intended parallelism.

### How to Interpret Results

- Throughput scales nearly linearly with node count: the filesystem still has scaling headroom across the tested load range.
- Aggregate throughput plateaus while node CPUs remain idle: check storage, network, or quota limits.
- High IOPS, low throughput, and rising latency: the workload likely performs many small or random I/Os.
- High `open`/`stat` times despite fast sequential reads: investigate metadata, file counts, and directory structure.
- One node runs much slower than others: check network path, placement, mount options, CPU steal, and shard location.
- Job starts fast then slows down: check burst credits/quotas if applicable, caching, contention, and competing jobs.

## 8. Common Design Mistakes

- **Every node downloads the entire dataset:** creates object storage bursts and drags out startup times. Use manifests, shards, caching, or single-pass staging.
- **Placing millions of small files in one directory:** slows metadata operations and listings. Shard directories or pack data into archives.
- **Every rank writes to one shared file:** causes locking, synchronization, and contention. Use per-rank/shard files or proper parallel I/O.
- **Using the shared filesystem as scratch for everything:** temporary files and logs compete with critical inputs/outputs. Move intermediate data to local scratch when appropriate.
- **Ignoring checkpoint storage sizing:** jobs can run out of space or fill the filesystem right when recovery is needed. Estimate capacity, cadence, and retention policies.
- **Testing one node and extrapolating cluster performance:** overlooks contention, networking, and metadata scaling as clients grow. Load test at increasing scales.
- **Looking only at CPU utilization:** low CPU can mean processes are stalled on I/O. Track wait times, throughput, latency, and I/O queues.

## Cluster I/O Design Checklist

- [ ] Classified data into inputs, scratch, checkpoints, outputs, and archives.
- [ ] Identified access patterns: sequential/random, large/small files, read/write, and concurrent node count.
- [ ] Selected shared filesystem, parallel filesystem, object storage, or local NVMe per data class.
- [ ] Created manifests, versioning, and checksums for input datasets.
- [ ] Avoided duplicate downloads with a clear staging/sharding plan.
- [ ] Separated temporary data from data requiring durable retention.
- [ ] Designed outputs and checkpoints to minimize concurrent writes to a single file.
- [ ] Verified capacity, quotas, metadata limits, bandwidth, IOPS, and networking.
- [ ] Benchmarked from a single node up to multi-node scale using representative data.
- [ ] Configured alerts for near-full filesystems, rising latency, dropping throughput, and I/O backlogs.
- [ ] Verified stage-out, checksums, checkpoint recovery, and scratch cleanup procedures.

Good I/O design ensures compute nodes spend most of their time computing rather than waiting on data. Match storage tiers to access patterns, distribute inputs deliberately, isolate scratch from durable data, and benchmark at realistic cluster scale before moving large workloads into production.
