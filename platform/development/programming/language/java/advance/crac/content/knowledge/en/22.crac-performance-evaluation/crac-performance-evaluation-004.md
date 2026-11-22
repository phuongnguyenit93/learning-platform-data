# Measuring Image Fetch, Restore, and Resource Reopening Time

In Java CRaC, post-restore startup time is not just the time the runtime takes to read the checkpoint image. The application must also reopen external resources, verify dependencies, and bring workers or request listeners back to a ready state.

To evaluate performance accurately, measure each part of the journey separately:

1. **Fetching or staging the checkpoint image:** retrieving the artifact from object storage/registry, copying it to the node, and verifying files.
2. **Runtime restore:** launching the JVM from the image and restoring process state.
3. **Reopening resources:** executing afterRestore() callbacks and recreating connections, file handles, clients, or native resources.
4. **Readiness and warm-up:** validating dependencies, starting workers, populating necessary caches, and opening traffic.
5. **First request:** measuring the actual latency observed by users or callers.

These milestones distinguish CRaC's benefits from image transfer costs, I/O, network connections, and post-restore startup tasks. Measuring only from running the restore command until the JVM appears can omit much of the interval during which the application cannot yet serve requests.

## 1. Defining Timeline Milestones Accurately

A restore sequence can be described as follows:

~~~text
Start fetching checkpoint image
          |
          v
Image is on node and verified
          |
          v
Begin runtime restore request
          |
          v
Runtime recovers process and JVM
          |
          v
Resource.afterRestore() begins
          |
          v
Reopen database, HTTP, file, and native resources
          |
          v
Dependency validation completes
          |
          v
Workers / schedulers ready
          |
          v
Readiness transitions to READY
          |
          v
First request completes
~~~

Name milestones consistently so runs can be compared:

| Milestone | Meaning |
|---|---|
| T0 | Start fetching or copying image |
| T1 | Image finished writing on the target node |
| T2 | Integrity/checksum verification completed |
| T3 | Begin runtime restore request |
| T4 | Application enters the first afterRestore() callback |
| T5 | Mandatory resources have reopened |
| T6 | Application marks READY and permits traffic |
| T7 | First verification request completes |

From these milestones, you can calculate:

- **Image staging time:** T1 - T0.
- **Image verification time:** T2 - T1.
- **Runtime restore-to-callback time:** T4 - T3.
- **Resource reopen time:** T5 - T4.
- **Readiness time:** T6 - T3.
- **First-request latency window:** T7 - T6.
- **End-to-end time to serve:** T7 - T0.

Runtime restore-to-callback measures externally until the first application callback; it can include runtime process recovery, loading required memory pages, and transferring control to the application. To break this down further, use runtime-provided logs or tracing and keep interpretation aligned with the running JDK/CRaC version.

If the image is already present on the node, T0 and T1 may not be on the restore path. Document that condition explicitly rather than assuming image fetch time is zero across all environments.

## 2. Distinguishing Image Creation Time, Image Fetch Time, and Restore Time

Three operations are frequently conflated into one:

- **Checkpoint creation:** the runtime freezes state and writes the checkpoint image.
- **Image transfer/staging:** delivering the image to the restore location.
- **Restore:** the runtime reads the image and recovers the process.

They answer different performance questions.

| Activity | Question to Answer | Example Metric |
|---|---|---|
| Create checkpoint | How long does creating the artifact take? | checkpoint duration, image size |
| Fetch/stage image | How long does moving the artifact to the node take? | bytes, throughput, staging duration |
| Restore | How long until the process resumes executing? | restore-to-callback duration |
| Reopen resources | How long until dependencies operate again? | per-resource reopen duration |
| Readiness | How long until traffic is accepted? | time-to-ready |
| First request | How much latency do users see? | first-request latency |

Do not add checkpoint creation time into restore latency when the goal is measuring single-startup latency. However, when evaluating total operational cost, you can amortize image creation cost across the number of restores the image serves.

For example, if an image is created once and used for 100 restores, report checkpoint creation cost separately alongside an amortized cost metric:

~~~text
Amortized checkpoint cost per restore
    = checkpoint creation duration / 100
~~~

This is a lifecycle cost analysis method, not actual restore duration.

## 3. Using the Right Clock for Each Measurement

### Within the Same JVM: System.nanoTime()

Measure elapsed time inside callbacks or within an operation using System.nanoTime():

~~~java
long started = System.nanoTime();

reopenDatabase();

long elapsedNanos = System.nanoTime() - started;
long elapsedMillis =
    TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

nanoTime() is suitable for measuring durations because it is unaffected by system wall-clock adjustments. Do not use System.currentTimeMillis() to measure short spans, as NTP updates or system clock changes can cause jumps.

### Across Processes: Use the Harness Monotonic Clock

Never take two System.nanoTime() values from two different JVMs and subtract them. The API guarantees consistency only for measuring elapsed intervals within the same JVM; do not assume identical nanoTime() origins across processes or hosts.

To measure T3 to T6, use an external supervisor or orchestration harness:

- Record the start timestamp using the harness's monotonic clock.
- Launch the restore command.
- Wait for a callback or readiness signal from the application.
- Record the signal arrival timestamp using the same monotonic clock.
- Calculate elapsed time inside the harness itself.

If steps span multiple hosts, use an end-to-end measurer at the orchestrator or controlled clock synchronization. Never subtract timestamps from different machines without accounting for clock skew.

### Wall-Clock Timestamps for Log Correlation

You can record UTC timestamps to correlate logs across the JVM, runtime, and orchestrator:

~~~java
Instant eventTime = Instant.now();
~~~

Timestamps aid event correlation, but primary durations should still be computed via a monotonic clock within the same measurement domain.

## 4. Measuring Checkpoint Image Fetch or Staging Time

If the image is fetched from remote storage, measure separately:

- Download/copy start timestamp.
- File write completion timestamp.
- Actual image size.
- Checksum or signature verification time.
- Average throughput.
- Volume attach/mount wait time, if applicable.
- Decompression or artifact preparation time, if part of the workflow.

Example using GNU time to measure a local copy operation:

~~~bash
/usr/bin/time -f 'elapsed_s=%e max_rss_kb=%M' \
  cp /source/checkpoint-image /local/checkpoints/checkpoint-image
~~~

For images fetched from object storage, use transfer client or orchestrator timings and record actual bytes transferred. Separate network wait, download, and checksum durations if supported by the tooling.

Average throughput:

\[
Throughput = \frac{ImageSizeBytes}{StagingDurationSeconds}
\]

If the image size is 2 GiB and staging takes 8 seconds, average throughput is approximately 256 MiB/s in binary units. When reporting, specify clearly whether MB or MiB is used.

### Do Not Skip Checksums

A fast download of a corrupted image is not a valid performance result. Verify checksums or signatures before restore and record verification time separately.

Do not exclude checksum validation from end-to-end measurements if production always performs that step. You can report both staging-only and staging-plus-verification so readers understand each step's cost.

### Storage Caching

The first image read may be slower due to cold caches; subsequent runs may be faster because data already resides in the page cache or storage-layer cache.

Explicitly label each measurement as:

- Cold cache: the node has not read the image recently.
- Warm cache: the image or relevant pages are already cached.
- Local storage: the image resides on node disk/volume.
- Remote storage: the image is fetched over the network or remote filesystem.

Do not mix cold-cache and warm-cache runs into the same percentile without grouping.

## 5. Measuring Runtime Restore Time

Runtime restore begins when the system instructs the JVM to recover from the checkpoint image. The end of the measured interval should be an observable application milestone, such as the first afterRestore() callback.

An external harness can:

1. Record T3 using a monotonic clock.
2. Launch the JVM with the restore option matching the CRaC JDK distribution.
3. Wait for the application to write marker T4 or emit an event over a socket/pipe.
4. Record T4 using the same harness clock.
5. Compute runtime restore-to-callback duration.

Restore launch syntax varies by CRaC JDK distribution and deployment environment. Use the command documented for your running runtime; do not mistake the checkpoint command for the restore command.

### Marker from the First Callback

A Resource can emit a marker when the callback begins:

~~~java
@Override
public void afterRestore(Context<? extends Resource> context)
        throws Exception {
    markerSink.record("AFTER_RESTORE_BEGIN");
    reopenResources();
}
~~~

The marker sink should be a test channel or telemetry sink already ready at callback time. If the marker is written to a file, that file must sit on a filesystem accessible to the restored process.

For production, use structured metrics or events. Do not let marker emission become a new dependency capable of failing the callback if the telemetry server is temporarily unavailable.

### Runtime Logs

Some JDK distributions provide logging for CRaC or checkpoint/restore. When using them, document the exact log flags, runtime version, and specific event used as the milestone. Do not assume an internal log line carries identical semantics across different JDK distributions.

Without a reliable runtime milestone, report T3 to T4 as "restore-to-first-application-callback" rather than calling it pure runtime CPU time.

## 6. Measuring Reopening Time for Each Resource in afterRestore()

Do not measure only the total afterRestore() duration. When total duration rises, you need to know whether the database pool, HTTP client, file handles, or secret provider consumes the majority of time.

You can define an interface for reopenable resources:

~~~java
public interface ReopenableResource {
    String name();
    void reopen() throws Exception;
}
~~~

A CRaC Resource can instrument each operation:

~~~java
import java.util.concurrent.TimeUnit;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class TimedRestoreResource implements Resource {
    private final ReopenableResource[] resources;
    private final RestoreMetrics metrics;

    public TimedRestoreResource(
            ReopenableResource[] resources,
            RestoreMetrics metrics) {
        this.resources = resources;
        this.metrics = metrics;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Close resources in application dependency order.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        long totalStarted = System.nanoTime();

        for (ReopenableResource resource : resources) {
            long started = System.nanoTime();

            try {
                resource.reopen();

                long elapsed = System.nanoTime() - started;
                metrics.recordSuccess(
                    resource.name(),
                    elapsed,
                    TimeUnit.NANOSECONDS
                );

            } catch (Exception failure) {
                long elapsed = System.nanoTime() - started;
                metrics.recordFailure(
                    resource.name(),
                    elapsed,
                    failure
                );
                throw failure;
            }
        }

        metrics.recordTotal(
            System.nanoTime() - totalStarted,
            TimeUnit.NANOSECONDS
        );
    }
}
~~~

RestoreMetrics is an application-implemented abstraction. It may write logs, update Micrometer timers, or emit events to a telemetry system. Keep the metric recording path simple and independent of the resource currently being reopened.

### Recording Both Successes and Failures

When a resource fails, still record the attempt's duration and error type. Recording only successful metrics can hide the slowest or failing restores from dashboards.

Suggested metrics:

| Metric | Meaning |
|---|---|
| crac_resource_reopen_seconds | Time spent reopening each resource |
| crac_resource_reopen_total | Count of resource reopen attempts |
| crac_resource_reopen_failures_total | Count of failed reopens |
| crac_after_restore_seconds | Total duration of callback or callback group |
| crac_restore_readiness_seconds | Time from restore to READY |

Use low-cardinality labels such as fixed resource_type or resource_name values. Never put instance IDs, request IDs, tenant-containing paths, or secrets into high-cardinality metric labels.

## 7. Measuring Readiness and Time to Serve the First Request

A completed afterRestore() callback does not mean the application can already serve requests.

The application may still need to:

- Validate database connectivity.
- Authenticate with a broker or secret manager.
- Start workers.
- Populate critical caches.
- Initialize schedulers.
- Run health checks.
- Open request listeners or traffic gates.

Maintain explicit readiness states:

~~~text
RESTORING
    |
    v
REOPENING_RESOURCES
    |
    v
VALIDATING_DEPENDENCIES
    |
    v
STARTING_WORKERS
    |
    v
WARMING_UP
    |
    v
READY
~~~

T6 should mark when the application actually accepts traffic, not merely when the last callback returns if additional startup steps remain.

To measure T7, send a probe request following a realistic request path and record the time from when the client starts sending until a complete response arrives. Measure separately:

- First request latency.
- First successful business request.
- Latency of subsequent requests during the warm-up period.
- Error rate in the window immediately following READY.

A simple health endpoint may return READY before database queries or workers are genuinely operational. Choose a readiness probe representing the workload's mandatory dependencies.

## 8. Measuring Total afterRestore() Duration

If multiple independent Resources exist, each can time its own callback. To measure the combined duration across all afterRestore() calls, use a single coordinator or a timestamp-collecting registry.

Example using a simple timer:

~~~java
public final class RestoreTimer {
    private long startedAt;

    public void start() {
        startedAt = System.nanoTime();
    }

    public long elapsedNanos() {
        return System.nanoTime() - startedAt;
    }
}
~~~

Do not share a single static timer variable across multiple restores if the application can create multiple contexts or instances within the same test process. Scope the timer to a specific restore attempt.

When callbacks run across multiple Resources, record each callback and the total coordinator duration. Do not sum callback durations if parallel execution is possible; actual elapsed wall time and total CPU time are different concepts.

## 9. Sequential vs. Parallel Resource Reopening?

Sequential resource reopening is straightforward and fits cases with dependencies:

~~~text
Secret Provider
      |
      v
Database Pool
      |
      v
Repository-dependent worker
~~~

If operations are independent—such as creating two unrelated HTTP clients—consider opening them in parallel. However, parallelization must be measured and controlled:

- Total elapsed time may decrease.
- CPU, memory, and concurrent connections may increase.
- Dependency ordering becomes more complex.
- One task failing while another succeeds requires coordinated cleanup.
- Callbacks must not return before all mandatory resources finish.

Do not use parallel streams or ad-hoc executors inside callbacks without managing thread lifecycles, shutdown, and timeouts. Measure a sequential baseline first, then test parallel execution with bounded concurrency while verifying dependency order.

## 10. Measuring Duration with JFR, Micrometer, and Logs

### Java Flight Recorder

JFR can help analyze CPU, allocations, threads, class loading, file I/O, and runtime events. You can start a recording around startup or apply a JFR configuration suited to your JDK.

JFR helps explain why callbacks or warm-up are slow, though it does not replace the orchestrator's end-to-end stopwatch. Enabling recordings also adds slight overhead; document the configuration when comparing runs.

### Micrometer

If the application uses Spring Boot Actuator/Micrometer, a Timer can measure duration:

~~~java
Timer.Sample sample = Timer.start(registry);

try {
    reopenDatabase();
    sample.stop(registry.timer(
        "crac.resource.reopen",
        "resource", "database"
    ));
} catch (Exception failure) {
    sample.stop(registry.timer(
        "crac.resource.reopen",
        "resource", "database",
        "result", "failure"
    ));
    throw failure;
}
~~~

This example illustrates how to record timers. In real applications, avoid creating meters with labels that vary per instance or per request.

### Structured log

An event can log:

~~~text
event=crac_restore_phase
phase=resource_reopen
resource=database
duration_ms=182
result=success
restore_generation=restore-42
~~~

Include application, JDK, and runtime versions in benchmark metadata. Never log credentials, JDBC passwords, tokens, or user data.

## 11. Designing Comparable Benchmarks

A useful measurement must have repeatable conditions.

### Preparing Run Groups

Include at least these groups:

1. **Cold JVM startup:** launching the application without using a checkpoint.
2. **CRaC restore, local image:** image already present on the node.
3. **CRaC restore, remote image:** requires staging from storage.
4. **CRaC restore with warm dependencies:** database/broker already ready.
5. **CRaC restore with cold dependencies:** requires creating fresh connections or caches.

If the goal is measuring improvements over normal startup, cold startup and CRaC restore must use the same application version, configuration, workload, and equivalent dependency conditions.

### Iteration Counts and Percentiles

Run multiple iterations to avoid concluding from a single trial. You can start with around 30 iterations per configuration, then increase counts if more stable tail-latency estimates are needed.

Report:

- Minimum.
- Median (p50).
- p90.
- p95.
- p99 when sample size is sufficient.
- Maximum.
- Success rate.

Do not report only the average. A slow restore caused by storage or DNS can be hidden inside an average value.

### Controlling Confounding Factors

Record:

- CPU model, core count, and quota.
- Memory limit and RSS.
- JDK vendor, version, build, and CRaC implementation.
- Kernel and container runtime.
- Checkpoint image size.
- Filesystem and storage type.
- Cold/warm cache state.
- Number of resources to reopen.
- Database/broker latency.
- Network RTT.
- Worker and thread counts.
- Logging/JFR configuration.
- Number of warm-up requests.

Do not compare two runs if one uses a local image and the other fetches over the network without explicitly noting the difference.

## 12. Calculating and Presenting Results

Example benchmark table:

| Scenario | Stage image | Runtime restore | Reopen resources | Ready | First request |
|---|---:|---:|---:|---:|---:|
| Cold startup | — | — | — | 4.8 s | 120 ms |
| CRaC, local image | 0 ms | 0.7 s | 0.9 s | 1.9 s | 95 ms |
| CRaC, remote image | 1.1 s | 0.7 s | 0.9 s | 3.0 s | 96 ms |

Numbers only illustrate presentation format and are not real benchmarks or expectations for every application.

This can be computed as:

~~~text
CRaC time-to-ready
    = image staging
    + image verification
    + runtime restore
    + resource reopen
    + readiness / warm-up
~~~

If the image is already local, the staging term can be zero in that measurement. When comparing against cold startup:

~~~text
Startup improvement
    = cold-start time-to-ready
      - CRaC time-to-ready
~~~

Improvement percentage:

\[
ImprovementPercent =
\frac{T_{cold} - T_{CRaC}}{T_{cold}} \times 100
\]

Use the exact same READY definition across both groups. Measuring cold startup up to ApplicationReadyEvent while measuring CRaC up to JVM resume makes the comparison unfair.

## 13. Analyzing When a Phase Becomes a Bottleneck

### Slow Image Staging

Inspect image size, storage throughput, network, checksums, compression, and mounts. You can reduce duration by placing images closer to restore nodes, choosing storage with appropriate throughput, or avoiding redundant copies when artifacts remain valid.

Do not drop integrity checks just to shave a few milliseconds.

### Slow Runtime Restore

Inspect CRaC/runtime logs, image size, memory mappings, page faults, storage latency, and CPU quota. A large image or mismatched host configuration can slow down restoration.

If the runtime uses lazy page loading, part of the cost may surface after the first callback when the application accesses unmapped pages. Therefore, also measure warm-up and first-request durations.

### Slow afterRestore()

Use per-resource metrics to pinpoint which resource consumes time. Common culprits include:

- Creating database connection pools.
- TLS handshakes.
- DNS lookups.
- Reading secrets or certificates.
- Restoring file handles or mounts.
- Starting workers and consumers.
- Rebuilding caches.

Optimize only the component measured to be the bottleneck. For instance, increasing pool size may not reduce restore time if the database limits concurrent connections.

### Slow Readiness Despite Open Resources

Inspect health checks, warm-up queries, cache loading, migrations, or startup runners. Do not open traffic early if dependencies are not genuinely ready.

### Slow First Request

This can stem from JIT compilation, class loading, lazy initialization, page faults, DNS, TLS sessions, or cache misses. Compare the first request against the 10th, 100th, and steady-state requests to observe the warm-up curve.

## 14. Lazy Page Loading and Deferred Post-Restore Costs

Some checkpoint/restore implementations may defer loading portions of memory pages until the application accesses them. When that happens:

- Restore-to-callback can appear fast.
- afterRestore() can finish quickly.
- The first request may still be slow due to page faults or I/O.
- Warm-up can lengthen READY time while lowering real request latency.

Do not conclude that fast runtime restore equals fast request serving. Measure at least three points: first callback, readiness, and first request.

If the workload has critical code paths, run controlled warm-up before opening traffic. Warm-up must represent real usage paths without causing business side effects such as creating orders or triggering payments.

## 15. Tracking Performance Across Multiple Restores

When an image stays in long-term use, restore times can shift with environmental changes:

- Storage volume was changed.
- Database or secret manager became slower.
- Certificates or credentials had to be refreshed.
- An older image no longer fits newer nodes cleanly.
- Caches are cold or datasets grew larger.
- The number of resources requiring reopening increased.
- CPU/memory quotas changed.

Record a restore generation ID to correlate metrics within the same restore attempt. Put this ID in logs or traces, avoiding metric labels if it creates excessive cardinality.

Dashboards should display:

- Time-to-ready p50/p95.
- Image staging duration and throughput.
- Runtime restore-to-callback duration.
- afterRestore duration.
- Per-resource reopen p95.
- Restore success/failure counts.
- First-request latency.
- CPU, RSS, page faults, and I/O.
- Retry and timeout counts when opening dependencies.

Set alert thresholds based on real SLOs. For example, if p95 time-to-ready exceeds its threshold across consecutive intervals, investigate whichever phase grew most rather than simply restarting the application.

## 16. Common Measurement Mistakes

**Measuring only the restore command time:** omits image staging, resource reopening, warm-up, and readiness.

**Using currentTimeMillis() for durations:** the clock can be adjusted. Use nanoTime() inside the same JVM and a monotonic clock in the harness.

**Subtracting nanoTime() across two JVMs:** origins are not guaranteed to be comparable across processes. Use an external harness.

**Mixing cold cache and warm cache runs:** makes percentiles hard to interpret. Group by cache state and storage tier.

**Comparing mismatched READY milestones:** cold start and CRaC restore may use different readiness criteria. Standardize the end milestone.

**Measuring only aggregate afterRestore():** hides whether database, HTTP, or files are slow. Measure each resource.

**Ignoring errors and retries:** recording only successful durations creates artificially optimistic results. Record failures, retries, and timeouts.

**Reporting only averages:** conceals tail latency. Report medians and percentiles.

**Warm-up causing side effects:** warm-up can create business data or send real messages. Use safe test endpoints and workloads.

**Optimizing by skipping validation:** can leave instances serving with invalid credentials or resources. Keep mandatory correctness steps intact.

## 17. Recommended Benchmarking Workflow

### Preparation

1. Select the same application version and configuration for both cold startup and CRaC restore.
2. Record the JDK, CRaC runtime, kernel, container, and storage.
3. Identify the checkpoint image, size, and storage location.
4. List Resources needing reopening and their dependency order.
5. Define the exact READY milestone and first request.
6. Prepare an external harness using a monotonic clock.

### Measuring Image Fetch

1. Start the timer when downloading or copying the image.
2. Record byte count and staging duration.
3. Verify checksums/signatures.
4. Record verification duration separately.
5. Classify cold cache vs. warm cache runs.

### Measuring Restore and Resources

1. Start the external timer before invoking the restore command.
2. Emit a marker at the first afterRestore() callback.
3. Use System.nanoTime() to measure each resource reopen.
4. Record successes, failures, and retries.
5. Record when all mandatory resources are ready.
6. Record when the application transitions to READY.

### Measuring Requests

1. Send a test request right after READY.
2. Record latency and outcome.
3. Send an additional batch of controlled warm-up requests.
4. Compare first-request latency with steady-state.
5. Ensure warm-up generates no business side effects.

### Aggregation

1. Repeat each scenario an adequate number of times.
2. Compute min, p50, p90, p95, and p99 when sample count permits.
3. Report success rate and failures.
4. Compare cold startup against CRaC on the exact same READY milestone.
5. Identify the bottleneck phase before proposing optimizations.
6. Store raw measurements alongside environment metadata for reproducibility.

## 18. Key Principles to Remember

- Separate image staging, checksum verification, runtime restore, resource reopening, readiness, and first request.
- Do not include checkpoint creation in restore latency when measuring startup time.
- Use System.nanoTime() to measure durations within the same JVM.
- Use a harness monotonic clock for cross-process timings.
- Never subtract nanoTime() values from two JVMs or two hosts.
- Record image size, storage tier, cache state, and execution environment.
- Measure each Resource individually in afterRestore(), including failures.
- Mark READY only after mandatory dependencies and workers are ready.
- Measure the first request to uncover lazy page loading and warm-up costs.
- Compare cold startup and CRaC restore on the exact same READY definition.
- Report percentiles and success rates, not averages alone.
- Never drop checksums, validation, or readiness gates merely to lower measured time.

A meaningful CRaC measurement must reflect when the application can genuinely serve requests. By separating image transfer, runtime restore, per-resource reopening, and readiness, the development team can pinpoint exactly which part consumes time, evaluate gains relative to cold startup, and optimize without compromising recovery correctness.
