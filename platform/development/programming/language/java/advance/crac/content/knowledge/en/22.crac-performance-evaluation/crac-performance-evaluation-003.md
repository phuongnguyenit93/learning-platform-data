# Measuring Checkpoint Duration and Image Creation Cost

Checkpointing helps shorten the time required to bring a Java application to readiness, yet creating the image also consumes resources. The runtime must coordinate resources, snapshot process state, and write data to storage. Deployment pipelines may also compress, encrypt, upload, verify, and publish the artifact. Measuring only how long the checkpoint command call takes or looking solely at directory size overlooks a substantial portion of the cost.

Evaluating CRaC (Coordinated Restore at Checkpoint) performance requires distinguishing at least three quantities: how long the application takes to prepare and stop work, how long the runtime takes to create the checkpoint image, and the elapsed time from starting the checkpoint until the artifact can be restored in the target environment. Additionally, measure how long the application stops accepting traffic, CPU/memory/I/O overhead, image size, and restore duration. These figures answer different operational questions.

A useful benchmark must use representative workloads and resource limits, record source/target environments, execute multiple runs, and verify actual restores. A checkpoint that succeeds to create yet fails to restore, or one created quickly at the cost of excessive I/O that degrades application latency, is still an unacceptable outcome.

## 1. Components of Checkpoint Cost

The process can be decomposed into the following phases:

1. **Application quiescence:** Stopping acceptance of new work, draining in-flight requests/jobs, and bringing resources to a safe state.
2. **Pre-checkpoint callbacks:** Resources execute beforeCheckpoint(), closing or preparing sockets, files, pools, executors, and dependencies according to lifecycle.
3. **Process snapshot:** The runtime and platform checkpointing mechanism capture the required process state.
4. **Image write:** Memory pages and metadata are written to the checkpoint directory or runtime-designated storage.
5. **Artifact finalization:** Flushing data, writing final metadata, verifying files, and completing the save operation.
6. **Post-processing:** Compression, encryption, generating manifests, checksums/signatures, or converting packages if required by the pipeline.
7. **Distribution:** Uploading, replicating, or copying the artifact to the restore destination.
8. **Publishing:** Marking the artifact as complete and ready for use.

~~~text
Checkpoint request
       |
       v
Quiesce + beforeCheckpoint callbacks
       |
       v
Runtime snapshot / dump
       |
       v
Write checkpoint files + metadata
       |
       v
Flush / finalize image
       |
       v
Compress / encrypt / sign (if applicable)
       |
       v
Upload / replicate
       |
       v
Verify + publish artifact
       |
       v
Artifact ready for restore
~~~

Not every platform shares identical boundaries or callbacks as shown in the diagram. Some phases may run concurrently, be embedded in the runtime, or be executed by the deployment system. Therefore, record end-to-end time independently of phase metrics; do not mechanically sum phase durations when they overlap.

## 2. Distinguishing Different Time Metrics

A single "checkpoint duration" number is rarely enough to evaluate a system. Explicitly define the start and end points for each metric.

| Metric | Start | End | Meaning |
|---|---|---|---|
| Quiesce duration | Stop accepting new work begins | Ingress/workers stopped and in-flight work drained | Cost of bringing the application to a safe state |
| beforeCheckpoint duration | Preparation callbacks begin | All Resource callbacks complete | Cost of preparing resources |
| Snapshot duration | Runtime begins creating image | Runtime finishes snapshot portion per platform definition | Cost of capturing process state |
| Image write duration | Writing checkpoint data begins | Data/metadata files finish writing | Storage I/O cost |
| Finalization duration | Finalization begins | Local artifact is consistent and complete | Cost of flushing, metadata, verification |
| Packaging duration | Compression/packaging begins | Package completes | Additional CPU and I/O cost |
| Encryption duration | Encryption begins | Ciphertext and manifest complete | Cryptographic cost |
| Transfer duration | Upload/copy begins | Artifact reaches destination storage | Network cost |
| Artifact-ready duration | Checkpoint request begins | Artifact is verified and published | End-to-end waiting time |
| Application pause | Traffic intake stops | Instance is permitted to receive traffic again | Direct impact on availability |
| Restore-to-ready duration | Restore begins | Instance reaches readiness | Cost of bringing a new instance into service |

Distinguish image creation time from the duration the instance is paused. In one architecture, the application may resume running after the local checkpoint completes while the pipeline upload proceeds asynchronously. In another architecture, the instance may have to wait for artifact publishing or restore verification. Define application pause based on actual system behavior rather than inferring it from artifact creation time.

Similarly, restore duration is not checkpoint duration. Both metrics must be measured separately, even though both influence rollout or scale-out times.

## 3. Defining Measurement Goals Before Benchmarking

Before running trials, identify which decision the measurements will inform. Common goals include:

- Comparing standard startup against restoring from a checkpoint.
- Determining whether checkpointing is fast enough for autoscaling.
- Estimating storage and network capacity required for artifacts.
- Measuring the impact of heap occupancy on dump duration.
- Evaluating compression or encryption costs.
- Determining minimum CPU quotas and storage throughput.
- Checking whether checkpointing disrupts requests currently being served.
- Measuring time from image creation until the image can be used in another region.

Translate goals into quantitative criteria. For example:

| Goal | Primary Metric | Supplementary Metrics |
|---|---|---|
| Fast scale-out | Restore-to-ready p50/p95 | Artifact transfer, readiness failures |
| Minimize disruption | Application pause p95 | Request error rate, drain duration |
| Reduce storage cost | Artifact bytes | Compression ratio, retention |
| Reduce CPU overhead | CPU-seconds/checkpoint | CPU throttling, application latency |
| Accelerate publishing | Artifact-ready duration | Write throughput, encryption/upload time |
| Ensure reliability | Restore success rate | Integrity failures, retry count |

Do not set a goal simply as "checkpoint as fast as possible." A fast checkpoint that consumes massive CPU, produces an oversized image, or spikes request latency can increase total system cost.

## 4. Measuring Time with the Right Clock

For intervals within the same running process, use a monotonic clock such as System.nanoTime() to measure elapsed time. Do not use System.currentTimeMillis() to calculate durations because the wall clock can jump or be adjusted.

Example:

~~~java
long started = System.nanoTime();

prepareResources();

long elapsedNanos = System.nanoTime() - started;
long elapsedMillis = elapsedNanos / 1_000_000;

logger.info("resource preparation took {} ms", elapsedMillis);
~~~

This snippet fits measuring a synchronous phase within the same execution. For phases spanning checkpoint/restore, the process can be halted or restored at a different time. Never assume a nanoTime value saved in the heap can be safely compared across process, host, or runtime boundaries. Use timestamps from the orchestrator/host or clock-synchronized telemetry for end-to-end measurements.

If start and end occur on the same host, an external controller can use the host's monotonic clock. If the two milestones occur on different hosts, wall-clock timestamps must be synchronized and clock skew accounted for. Distributed tracing can help link phases, though clock skew must still be understood.

Practical rules:

- Use a monotonic clock for internal durations within the same process.
- Use the orchestrator or controller to measure checkpoint request to artifact-ready.
- Record wall-clock timestamps for auditing and correlation, rather than naively treating them as durations.
- Attach the same checkpoint ID across callback logs, runtime logs, storage operations, and restore events.
- State metric units and boundaries explicitly.

## 5. Measuring Pre-Checkpoint Callback Duration

Resource callbacks are where applications typically stop workers, drain requests, flush data, and close resources. Measure each resource separately to see which step consumes most of the preparation time.

Example of an instrumented Resource:

~~~java
import org.crac.Context;
import org.crac.Resource;

public final class TimedResource implements Resource {
    private final Lifecycle lifecycle;
    private final DurationRecorder recorder;

    public TimedResource(
            Lifecycle lifecycle,
            DurationRecorder recorder) {
        this.lifecycle = lifecycle;
        this.recorder = recorder;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        long started = System.nanoTime();
        try {
            lifecycle.stopAcceptingWork();
            lifecycle.awaitInFlightWork();
            lifecycle.closeCheckpointSensitiveResources();
        } finally {
            recorder.record(
                    "crac.resource.beforeCheckpoint",
                    System.nanoTime() - started);
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        long started = System.nanoTime();
        try {
            lifecycle.reopenResources();
            lifecycle.verifyReady();
        } finally {
            recorder.record(
                    "crac.resource.afterRestore",
                    System.nanoTime() - started);
        }
    }

    public interface Lifecycle {
        void stopAcceptingWork() throws Exception;
        void awaitInFlightWork() throws Exception;
        void closeCheckpointSensitiveResources() throws Exception;
        void reopenResources() throws Exception;
        void verifyReady() throws Exception;
    }

    public interface DurationRecorder {
        void record(String name, long elapsedNanos);
    }
}
~~~

This is an architectural example; Lifecycle and DurationRecorder are application-defined. If a callback throws an exception, finally still records the phase duration. However, the recorder must be safe enough not to raise secondary errors during the callback. Some systems write metrics to a local buffer or log instead of calling a telemetry service that may be unavailable.

Measuring each resource helps identify slow components, such as:

- Request draining waiting for a long-running request.
- Consumers committing offsets or closing sessions.
- Connection pools waiting for in-use connections.
- Schedulers waiting for running jobs to finish.
- File writers flushing data.
- Cloud clients waiting for background refresh tasks to stop.

Do not collapse everything into one metric if individual components need optimization. At the same time, avoid emitting excessive synchronous logs inside callbacks, as logging itself can lengthen checkpoint duration.

## 6. Measuring Snapshot and Image Write Duration Externally

Application callbacks measure only the application's resource preparation work. They do not measure the full snapshot work or the time the runtime spends writing the image. To measure these phases, use the checkpoint control tool or vendor-supported runtime logs.

An external controller can record:

- When the checkpoint request was dispatched.
- When the runtime began processing, if corresponding events/logs exist.
- When the command or API returned a result.
- When all checkpoint files appeared and stabilized.
- When the artifact was verified and published.

Example measurement logic in a controller:

~~~text
checkpoint_id = unique_id()

t_request = monotonic_now()
invoke_supported_checkpoint_operation()

wait_until_checkpoint_operation_completes()
t_runtime_done = monotonic_now()

wait_until_all_artifact_files_are_complete()
verify_artifact()
t_artifact_ready = monotonic_now()

snapshot_and_write_ms = t_runtime_done - t_request
artifact_finalize_ms = t_artifact_ready - t_runtime_done
artifact_ready_ms = t_artifact_ready - t_request
~~~

This is pseudocode, not a standard CRaC command. How checkpointing is invoked depends on the JDK distribution and platform. If the runtime does not expose separate milestones for snapshot and write, report only the total duration actually measured by the controller; do not guess internal timings from logs lacking reliable timestamps.

Do not equate the checkpoint command returning with artifact-ready if the runtime or pipeline must still write metadata, flush files, compress, encrypt, or upload. Clearly define completion criteria before stopping the timer.

## 7. Measuring Checkpoint Image Size

Checkpoint size does not necessarily equal the Java heap size. Depending on the runtime and configuration, the image may contain multiple kinds of state:

- Checkpointed memory pages.
- Native memory and supported mappings.
- Process and runtime metadata.
- Required resource or file descriptor state.
- Auxiliary files generated by the checkpoint engine.
- Retained data regions outside the Java heap.

Therefore, record separately:

1. Heap used and committed at checkpoint time.
2. Process RSS/PSS if provided by the platform.
3. Total logical size of checkpoint files.
4. Actual disk space allocated.
5. Size after compression.
6. Size after encryption/packaging.
7. Final size on storage and bytes transferred over the network.

On Linux, for a checkpoint directory, you can use:

~~~bash
du -sh ./checkpoint
du -sb ./checkpoint
find ./checkpoint -type f -printf '%s %p\n'
~~~

du -sh typically displays block-based disk usage; du -sb on GNU coreutils reports apparent size in bytes. The two numbers can differ due to sparse files, block allocation, and filesystem behavior. The find -printf syntax is a GNU extension not present on every operating system. Choose tools matching your deployment environment.

Do not record only the size of the largest file. A checkpoint may contain many small files; file count and metadata overhead also impact creation, upload, and restore durations.

## 8. Why Heap Size Does Not Accurately Predict Image Size

The Java heap is only one portion of process memory. Heap used indicates live/allocated objects from the GC's perspective; it does not cover every memory region the checkpoint engine may need to save.

Factors causing image size to differ from heap used include:

- Metaspace, code cache, and JVM native structures.
- Thread stacks and thread states.
- Direct buffers and native libraries.
- Memory-mapped files.
- Shared or private memory regions.
- Zeroed or compressible memory pages.
- Sparse files and filesystem block allocation.
- Deduplication or compression mechanisms in the checkpoint engine.
- Off-heap files and metadata that the runtime must preserve.

A large committed heap where most pages contain no active data can produce a different image than a heap with similar occupancy but different page distribution. Conversely, large native memory or mappings can inflate the image even when heap used is small.

Treat heap metrics as an explanatory variable, not a formula for computing image size.

## 9. Impact of Live Set and Heap Occupancy

The live set is the amount of data retained after GC collects unreferenced objects. Heap occupancy at checkpoint time can influence how many pages contain active data and compressibility, though the relationship is not always linear.

When benchmarking, record:

- Heap used.
- Heap committed and maximum.
- GC collector and configuration.
- Timestamp of the most recent GC.
- Count of objects or large cache structures, if measurable.
- Native memory and direct buffers.
- Process RSS/PSS.
- Image size and write duration.

Do not automatically invoke System.gc() before checkpointing just to shrink the image. A full GC consumes CPU, introduces pauses, alters heap state, and makes the benchmark unrepresentative of production. To evaluate an explicit GC policy, run it as a separate variant and include GC time/CPU in the total cost.

A workload holding a large live cache can produce a larger image even at low request rates. Therefore, benchmarks require stable warm-up and cache states resembling the real environment.

## 10. Compression and Compression Ratio

Compressing checkpoints can reduce storage footprint and network transfer, at the cost of CPU, memory, and time. Depending on the runtime, the image may already be partially compressed or use a specialized format. Do not add extra compression without measuring the benefit.

Record three sizes:

- S_raw: checkpoint size before compression.
- S_compressed: size after compression.
- S_final: final package size after encryption/packaging.

Compression ratio can be calculated as:

\[
R_c = \frac{S_{compressed}}{S_{raw}}
\]

For example, if S_raw = 4 GiB and S_compressed = 1.6 GiB, then R_c = 0.4, corresponding to roughly a 60% size reduction relative to the input.

Also measure:

\[
Saving = 1 - R_c
\]

Do not compare compression ratios alone. If compression sharply increases CPU time while yielding minimal space savings, it may not be worthwhile. If the network is a bottleneck or storage is expensive, compression can offer substantial value.

Compressing before encrypting is generally more effective because ciphertext has high entropy and compresses poorly. However, ensure the package format and processing order match the restore pipeline.

## 11. Encryption and Integrity Verification Costs

If checkpoints are encrypted client-side, the pipeline should measure separately:

- Time to generate or fetch the DEK.
- Time for KMS key wrapping.
- CPU time for AEAD encryption.
- Time to generate the manifest and signatures.
- Time to verify checksums/signatures.
- Time for KMS unwrapping during restore.
- CPU time for decryption and authentication.
- Memory used for buffers/chunks.

For large checkpoints, do not load the entire image into the heap for encryption. Streaming or chunked encryption bounds memory usage, though it introduces overhead for metadata, nonces, tags, and file handling.

If encryption runs in parallel, wall-clock duration may be shorter than total worker CPU time. Record both elapsed time and CPU-seconds to distinguish throughput from actual CPU consumption.

Do not omit verification costs. An artifact is considered ready only after integrity checks pass according to policy, not immediately upon upload completion.

## 12. Storage I/O and fsync Costs

Image creation can write a large volume of data in a short span. Storage throughput, latency, the filesystem, and the page cache directly affect completion time.

Factors to record:

- Total bytes written.
- Average and peak write throughput.
- File count and create/rename operations.
- fsync or flush latency if logged.
- Disk queue depth and I/O wait.
- Storage type: local SSD, network filesystem, block volume, or ephemeral disk.
- Filesystem and mount options.
- Storage quotas or throttling.
- Near-full disk conditions.

If the checkpoint directory sits on a network filesystem, metadata latency or network throughput may be the bottleneck. When using local ephemeral storage, uploading to object storage constitutes a separate phase. Do not combine two storage tiers into a single measurement when hunting for root causes.

You can use iostat, pidstat, process I/O counters, or volume/cloud storage metrics. Metric names and access permissions depend on the OS and runtime.

## 13. Measuring CPU and Memory Overhead During Image Creation

Checkpointing can induce peak resource usage. For example, the runtime writes page data right after the application drains requests; compression/encryption can spawn extra buffers and worker threads.

Record:

- User/system CPU time of the process and checkpoint helper.
- cgroup CPU throttling.
- RSS/PSS and peak memory.
- cgroup memory.current and memory.events.
- Thread count and PIDs usage.
- I/O bytes and I/O wait.
- GC pauses and allocation rate.
- Application request latency/error rate during preparation.

On Linux, /usr/bin/time -v can wrap a standalone command like a compression or encryption stage to report elapsed time, CPU time, and maximum resident set size. For a long-running Java process, use process/cgroup monitoring tools or a dedicated controller; wrapping the checkpoint trigger command does not make /usr/bin/time automatically measure all resources of the target process.

If the container is subject to a CPU quota, actual CPU time and wall-clock duration can diverge widely. A step consuming 10 CPU-seconds can take many more wall-clock seconds when throttled. Always record quotas and throttling statistics alongside benchmark results.

## 14. Measuring Application Pause and Request Impact

For online services, the critical metric may be how long the application cannot accept requests or how requests are impacted, rather than how long artifact publishing takes.

One way to measure:

1. Record when ingress begins returning a status indicating it is no longer accepting new work.
2. Measure the count of in-flight requests and drain duration.
3. Record when in-flight requests complete.
4. Record when the checkpoint runtime starts and completes.
5. Record when ingress reopens or a new instance reports ready.
6. Correlate with request latency, error rate, and load balancer events.

If the system creates checkpoints from a dedicated instance, traffic-serving instances may experience zero pause throughout publishing. If checkpointing a live traffic-serving instance directly, downtime can differ. Measure your actual architecture.

Continuous synthetic requests can detect outage windows, provided the probes themselves do not generate heavy load or skew results. Record p50/p95/p99 latency as well as errors and timeouts during the checkpoint window.

## 15. Controlled Comparative Benchmarks

To see what benefits CRaC delivers, compare against an appropriate baseline:

- Cold start: launching a fresh JVM and waiting for readiness.
- Warm restart: restarting from the same image/container without restoring a checkpoint.
- CRaC restore: restoring from a checkpoint artifact.
- If needed, add full checkpoint + transfer + restore to reflect the production workflow.

Measure using identical readiness definitions, workloads, dependencies, and resource limits. If cold start runs on a large host while restore runs inside a small container, results cannot be fairly compared.

A results table should include:

| Scenario | Startup/restore-to-ready | CPU-seconds | Artifact bytes | Error rate |
|---|---:|---:|---:|---:|
| Cold start | ... | ... | Not applicable | ... |
| CRaC restore local | ... | ... | ... | ... |
| CRaC restore remote | ... | ... | ... | ... |

Do not compare only the time from process launch until the HTTP port opens. Readiness must verify critical dependencies and the ability to handle a representative workload.

## 16. Experiment Design and Iteration Count

A benchmark can be affected by JIT warm-up, cache state, GC timing, disk caches, network contention, and noisy CPU neighbors. One run is not enough to draw conclusions.

Suggested procedure:

1. Pin JDK vendor/version/build, CRaC engine, and application build.
2. Pin container image, kernel, filesystem, storage, and resource limits.
3. Prepare identical warm-up workloads.
4. Run a few pipeline warm-up iterations and exclude them from statistics if they only stabilize the environment.
5. Execute multiple independent measurements, typically at least 10-20 runs if cost permits.
6. Record all failures and their causes; do not silently drop bad samples.
7. Report median, p90/p95, min/max, and dispersion.
8. Restore generated artifacts to confirm usability.
9. Retest under load and representative storage/network conditions.
10. Store environment metadata alongside results.

Increase iteration counts when variance is high or p95 is an SLO criterion. For very expensive measurements, start with fewer runs for screening and expand for the final configuration.

Do not mix measurements from multiple JDK builds or resource profiles into one dataset without labeling.

## 17. Variables to Control

The following factors can alter checkpoint time and image size:

| Category | Variables to Record |
|---|---|
| JVM | Vendor, version, flags, GC, heap max, heap used |
| CRaC | Runtime build, checkpoint engine, options, resource callbacks |
| Application | Build ID, workload, cache size, request concurrency |
| Process | RSS/PSS, thread count, FD count, native memory |
| Container | CPU quota, cpuset, memory limit, PIDs limit |
| Kernel | Version, cgroup v1/v2, CRIU/runtime support |
| Storage | Volume type, filesystem, throughput, free space |
| Network | Bandwidth, latency, proxy, region, packet loss |
| Pipeline | Compression, encryption, chunk size, upload concurrency |
| Dependency | Database, cache, broker, and service readiness |

Change one variable at a time when establishing causality. Changing heap size, CPU quota, and compression level simultaneously obscures which factor changed the timing.

## 18. Analyzing the Relationship Between Image Size and Checkpoint Time

Large image size typically increases write and transfer times, though it is not always the sole factor. If snapshot scanning or callbacks dominate execution time, shrinking the package may not noticeably reduce total duration.

You can analyze by plotting:

- Image bytes vs. snapshot/write duration.
- Heap used/RSS vs. image bytes.
- CPU-seconds vs. compression ratio.
- Storage throughput vs. image write duration.
- Artifact bytes vs. transfer duration.
- Quiesce duration vs. count of in-flight requests.

If write duration scales nearly linearly with image bytes under the same storage profile, storage throughput is likely the dominant factor. If duration grows while image size stays flat, check callbacks, CPU throttling, metadata operations, filesystem latency, or runtime logs.

Do not infer causality from correlation across a handful of samples. Run controlled experiments—for example, holding workload and storage constant while varying heap live set size or compression settings.

## 19. Estimating Throughput and Pipeline Cost

Write or transfer throughput can be calculated simply:

\[
Throughput = \frac{Bytes\ processed}{Elapsed\ seconds}
\]

For example, if 3 GiB of ciphertext is uploaded in 30 seconds, average throughput is roughly 102.4 MiB/s using binary units. When reporting, specify clearly whether using GB or GiB and MB/s or MiB/s.

Total artifact-ready time:

\[
T_{ready} = T_{quiesce} + T_{snapshot/write} + T_{finalize}
             + T_{compress} + T_{encrypt} + T_{transfer} + T_{verify}
\]

This formula is a sequential model. If some phases execute concurrently or overlap, measure T_ready directly and describe the overlap rather than summing durations.

Resource consumption can be reported as:

- CPU-seconds/checkpoint.
- GiB written/checkpoint.
- GiB transferred/checkpoint.
- Peak memory/checkpoint.
- Storage bytes retained across the retention period.
- Count of KMS/storage requests.
- Instance-seconds dedicated to checkpoint preparation.

These units help convert benchmarks into operational estimates without depending on any specific cloud pricing sheet.

## 20. Optimizing Callback and Quiesce Duration

If quiesce dominates duration, inspect the blocking operations instead of focusing solely on optimizing the runtime snapshot.

Approaches to consider:

- Stop accepting new work earlier.
- Bound drain duration and establish a policy for excessively long-running requests.
- Split large jobs into batches with separate business checkpoints.
- Avoid flushing large amounts of unnecessary data synchronously inside callbacks.
- Use close/stop APIs with explicit timeouts and observability.
- Stop schedulers before waiting on workers.
- Avoid having two Resources await the same operation or close the same client.
- Split metrics by resource to pinpoint which callback is slow.

Do not skip completing transactions or ensuring data durability merely to shave checkpoint duration. Quiesce duration must be optimized within business safety boundaries.

## 21. Optimizing Image Write and Storage

If writing the image is the bottleneck:

- Use storage with adequate throughput and IOPS.
- Place the checkpoint directory on a supported volume with sufficient space.
- Avoid placing images on slow network filesystems unless recommended by the runtime.
- Monitor disk queues and I/O wait.
- Minimize unnecessary file metadata operations.
- Evaluate compression if storage/network is the bottleneck.
- Avoid running multiple concurrent checkpoints on the same volume if it causes contention.
- Ensure artifacts are flushed/finalized as required before publishing.

Do not compromise durability by skipping fsync or verification steps if the pipeline needs artifact integrity guarantees after crashes. When changing durability settings, measure and assess artifact-loss risk upon host or volume failure.

## 22. Optimizing Compression and Encryption

Compression helps when storage or network is the bottleneck and spare CPU exists. If CPU quota is already tight, compression can slow the pipeline down and impact other workloads.

Encryption must be maintained per security requirements; optimize the implementation rather than removing protection:

- Use an optimized AEAD library with appropriate native acceleration.
- Encrypt in chunks to bound memory usage.
- Choose chunk size via benchmarking.
- Bound worker concurrency to fit the CPU quota.
- Avoid redundant buffer copies.
- Use streaming so the entire image is never loaded into the heap.
- Measure KMS latency separately from CPU encryption time.
- Use multipart uploads suited to the object size.

When compressing before encrypting, measure both compression CPU cost and storage space saved. Never look solely at the compression ratio.

## 23. Calculating Efficiency Relative to Cold Start

CRaC incurs checkpoint creation and storage costs. Net benefits generally emerge when the same image is restored many times or when startup latency is a critical factor.

A simple calculation:

- T_cold: cold start time to readiness.
- T_checkpoint: time to create and prepare the artifact.
- T_restore: restore time to readiness.
- N: number of instances launched from one checkpoint.

Total time across N instances using cold start:

\[
T_{cold,total} = N \times T_{cold}
\]

Simple model for a shared checkpoint:

\[
T_{crac,total} = T_{checkpoint} + T_{distribution}
                 + N \times T_{restore}
\]

This model omits parallelism, artifact storage retention costs, checkpoint builder operational overhead, and simultaneous load on dependencies. It serves only to estimate a preliminary break-even point.

If a checkpoint must be rebuilt on every deploy and restored only once, artifact creation cost can outweigh the benefit. If one image scales out many replicas, image creation cost is amortized across multiple restores.

Compare both time and resource usage. A faster restore requiring more RAM or CPU can reduce container packing density on nodes.

## 24. Verifying Artifact Completeness and Restorability

A successful checkpoint does not guarantee the artifact will restore elsewhere. After creating an image in a benchmark, add a verification step:

- The runtime finished the checkpoint operation.
- All expected files exist with reasonable sizes.
- Manifest and metadata match the JDK/build.
- No files remain open for writing.
- Checksum or authentication verification succeeded, if used by the pipeline.
- The artifact can be read from destination storage.
- A test restore completed.
- The application reached readiness and handled a representative workload.

It is unnecessary to test-restore every production artifact if equivalent verification exists and cost is prohibitive, yet benchmarks must validate at least representative artifacts. When changing runtime, format, compression, or encryption, running a restore test is essential.

## 25. Sample Benchmark Report

A useful report should include the environment, results, and metric definitions.

~~~text
Checkpoint ID: build-42-run-07
Application build: 42
JDK: vendor / version / build
CRaC runtime: version
Kernel / cgroups: Linux / v2
Container limits: CPU 2, memory 3 GiB, pids 1024
Storage: local SSD
Workload: warmed cache, 50 concurrent requests before quiesce

Timings:
  quiesce p50/p95:             120 / 185 ms
  beforeCheckpoint p50/p95:     45 /  70 ms
  snapshot + write p50/p95:    820 / 990 ms
  compression p50/p95:         310 / 380 ms
  encryption p50/p95:          140 / 175 ms
  transfer p50/p95:            900 / 1200 ms
  artifact-ready p50/p95:      2250 / 2800 ms
  restore-to-ready p50/p95:   1150 / 1450 ms

Sizes:
  raw image:                   3.8 GiB
  compressed:                  1.5 GiB
  final encrypted artifact:    1.5 GiB + metadata

Resources:
  peak cgroup memory:          ...
  CPU-seconds:                 ...
  bytes written/transferred:   ...
  CPU throttled time:          ...
  restore success:             ...
~~~

The figures above illustrate report formatting only and are not real measurements or performance targets. Clearly document iteration counts, percentiles, units, rounding rules, and whether phases overlap.

## 26. Monitoring and Alerting

In production, track trends by build and checkpoint ID:

| Metric | Alert When |
|---|---|
| Quiesce duration | Spikes abnormally or exceeds pause SLO |
| Snapshot/write duration | Increases despite similar workload and image size |
| Artifact bytes | Jumps unexpectedly between builds |
| Compression ratio | Degrades abnormally |
| CPU-seconds | Spikes sharply or causes contention |
| Peak cgroup memory | Approaches memory limit |
| CPU throttled time | Rises inside checkpoint pipeline |
| Transfer duration | Exceeds publishing window |
| Artifact verification failures | Any checksum, signature, or metadata mismatch occurs |
| Restore-to-ready | Increases or experiences timeouts |
| Restore success rate | Drops for a build or resource profile |

Attach JDK version, CRaC engine, application build, and resource profile to metrics for regression analysis. When dependencies, GC, heap sizing, or the checkpoint engine change, compare against a baseline under identical conditions.

Do not fire alerts on a single slight uptick. Use baselines, percentiles, and violation counts across an appropriate observation window.

## 27. Common Measurement Mistakes

**Measuring only how long the checkpoint command takes to return.** The artifact may still need finalization, compression, encryption, or upload. Measure through the artifact-ready milestone.

**Using callback time as snapshot time.** Callbacks measure only application preparation. Measure runtime operations using the controller or supported logs.

**Using currentTimeMillis to measure durations.** The wall clock can jump. Use a monotonic clock for intervals within the same process/host.

**Equating heap size with image size.** An image can include native memory, mappings, and metadata. Record heap, RSS/PSS, and artifact bytes separately.

**Measuring only once.** JIT, GC, caches, disk, and network cause metric variance. Run multiple iterations and report percentiles.

**Forcing GC before every checkpoint.** This alters the workload and adds overhead. Measure it only as a separate variant if production genuinely does so.

**Benchmarking compression/encryption on a large host and deploying in a small container.** CPU quotas and memory limits change outcomes. Benchmark inside the target resource profile.

**Failing to measure application pause.** Artifact creation might be fast while request draining takes long. Measure ingress pause duration and request latency.

**Ignoring temporary files and disk allocation.** Logical size and actual disk consumption can diverge. Record both apparent size and allocated size when needed.

**Skipping test restores of artifacts.** Successfully created files do not prove compatibility. Execute restore tests for significant changes.

**Summing concurrent phase durations.** The sum of phases can exceed wall-clock end-to-end time. Report individual phases and T_ready independently.

**Omitting environment metadata.** Results become non-reproducible and incomparable. Save JDK, kernel, cgroup, storage, and workload profile details.

## 28. Checklist for Measuring Checkpoint Time and Image Creation Cost

- [ ] Are checkpoint request, snapshot complete, and artifact-ready clearly defined?
- [ ] Are quiesce, callback, snapshot/write, finalization, and post-processing separated?
- [ ] Is application pause measured separately from artifact creation time?
- [ ] Is restore-to-ready measured separately?
- [ ] Is a monotonic clock used for elapsed times within the same process/host?
- [ ] Are controller timestamps captured for end-to-end operations?
- [ ] Is a consistent checkpoint ID propagated across logs and metrics?
- [ ] Are heap used/committed, RSS/PSS, native memory, and thread count recorded?
- [ ] Are logical image size, allocated disk size, and file count recorded?
- [ ] Are compression ratio, encryption time, and transferred bytes measured?
- [ ] Are CPU-seconds, peak memory, I/O throughput, and CPU throttling measured?
- [ ] Are CPU/memory/PIDs limits and storage type documented?
- [ ] Does the benchmark use representative workloads, warm-up, and cache state?
- [ ] Are cold-start and restore-to-ready baselines collected under identical conditions?
- [ ] Were multiple iterations executed with median/p95 or appropriate percentiles reported?
- [ ] Are failed runs retained and explained?
- [ ] Were representative artifacts verified and test-restored?
- [ ] Was image creation cost weighed against the benefit across multiple replica restores?

## Conclusion

Evaluating checkpoint performance requires separating application preparation, snapshot/write, finalization, compression/encryption, transfer, and publishing. Application pause, artifact-ready duration, and restore-to-ready are distinct metrics that cannot substitute for one another. Nor does checkpoint size equal heap size, because the image can contain native memory, mappings, and metadata.

A trustworthy benchmark must capture elapsed time, CPU-seconds, peak memory, I/O, artifact bytes, and request impact. Use a monotonic clock for phases within the same process/host, an external controller for end-to-end timings, run multiple iterations in a representative resource profile, and execute real restores. With complete data, the team can identify whether bottlenecks sit in callbacks, the runtime, storage, compression, encryption, or the network, and optimize the exact phase while preserving checkpoint consistency and restorability.
