# CPU, memory, execution time, and temporary storage

Serverless functions let you deploy logic without managing servers yourself, yet every invocation still consumes finite compute resources. CPU, memory, execution time, and temporary storage settings directly determine processing capability, latency, stability, and cost. Provisioning too little can make a function slow, run out of memory, or time out; provisioning too much raises cost without meaningfully improving outcomes.

When sizing a function, look at both a single invocation and the overall execution environment. Some platforms couple CPU to the allocated memory; others let you configure CPU separately or select tiered presets. Concurrency can cause multiple requests to share the CPU and memory of the same instance. Temporary storage typically lives for the lifetime of the instance and is not durable data storage. Because these details vary by provider, runtime, and plan, measure inside the actual deployment environment.

## 1. The four resources to size

| Resource | Role | When under-provisioned | When over-provisioned |
|---|---|---|---|
| CPU | Executes code, serialization, encryption, compression, math, and data processing | Slow CPU-bound tasks, growing queues, timeouts | Higher cost or reserving unneeded capacity |
| Memory | Holds runtime, code, libraries, objects, buffers, caches, and active data | OOM, process termination, heavy GC, or paging if allowed by the platform | Higher cost; may not speed up CPU/I/O-bound workloads |
| Execution time | Maximum duration a single invocation is allowed to run | Invocation times out before completion | Workers may hold resources too long and mask unbounded tasks |
| Temporary storage | Stores intermediate files, downloads, extracted archives, scratch data | Disk full, write failures, or inability to process payloads | Higher cost and larger surface of temporary data to protect |

These four factors interact. Raising memory can also increase CPU on some platforms; raising concurrency can increase the memory working set and CPU contention; raising temporary storage does not increase memory; and raising timeouts does not fix an inefficient algorithm.

## 2. Understanding resources per invocation vs. per execution environment

A function is called serverless because the provider manages the servers and provisions execution environments automatically. However, do not assume every invocation gets its own dedicated virtual machine.

Distinguish two scopes:

- **Invocation:** a single execution of the function handling an event or request. An invocation has its own start time, end time, timeout, and outcome.
- **Execution environment/instance:** the runtime environment initialized by the platform to run the function. An environment may be reused across subsequent invocations or replaced during scaling, updates, or idle periods.

Depending on the platform, an execution environment may process one invocation at a time or handle multiple concurrent invocations. CPU, memory, and temporary storage may be accounted for at the instance, function, or invocation level under the platform’s model. Verify the runtime’s concurrency semantics before sizing capacity.

For example, if an instance handles four concurrent requests and each needs an extra 150 MB working set, peak memory can jump by roughly 600 MB on top of the baseline for runtime, libraries, and caches. If the runtime only processes one invocation per environment, the platform may spin up additional environments instead of sharing memory. The exact same memory setting can behave very differently as concurrency climbs.

## 3. CPU: compute capacity per invocation

CPU dictates instruction execution speed. Workloads generally fall into three categories:

- **CPU-bound:** compression/decompression, encryption, image processing, data transformation, numerical computation, or parsing large payloads.
- **Memory-bound:** operating on large datasets, wide working-set data structures, or algorithms bound by memory access bandwidth.
- **I/O-bound:** waiting on databases, object storage, HTTP APIs, queues, or filesystems.

Adding CPU usually helps CPU-bound workloads. It may do little for workloads waiting on databases or external APIs. For I/O-bound tasks, connection reuse, cutting round trips, batching requests, and query tuning often help more than adding CPU.

### 3.1. CPU may scale with memory or be configured separately

Serverless platforms allocate CPU using different models:

- Some platforms scale CPU share proportionally with configured memory.
- Some platforms allow choosing CPU and memory independently across valid tiers.
- Some platforms enforce CPU quotas or concurrency limits instead of assigning fixed vCPUs per invocation.
- Some container/serverless environments cap CPU by requests/limits or per instance.

Therefore, you cannot infer vCPU count from memory alone without checking the service and plan. When increasing memory, measure CPU utilization, duration, and throughput to verify real gains.

### 3.2. CPU contention as concurrency increases

When multiple invocations run concurrently inside one instance, they can contend for CPU. Warning signs include:

- Duration increases as concurrency rises even with identical payloads.
- CPU utilization stays pinned near the limit.
- Queuing or waiting invocations increase.
- p95/p99 climbs much faster than p50.
- One CPU-heavy request slows down co-located requests.

Lowering concurrency can improve per-request latency while increasing instance count. Raising concurrency utilizes resources better for I/O-bound workloads but creates contention for CPU-bound tasks. Benchmark at expected concurrency, not just with single isolated invocations.

## 4. Memory: sizing for the runtime and processed data

Memory does not hold only business objects. A function also needs memory for:

- The runtime and interpreter/VM.
- Loaded code, packages, and shared libraries.
- Frameworks, SDKs, and client connections.
- Heap, stack, and native allocations.
- Buffers for requests, responses, and serialization.
- In-process caches.
- Downloaded or intermediate data held in RAM.
- Multiple concurrent invocations if the runtime shares an instance.

A conceptual sizing formula:

\[
M_{required} \approx
M_{runtime} + M_{libraries} + M_{baseline}
+ (C \times M_{request}) + M_{buffer}
\]

Where `C` is the number of concurrent invocations sharing the same environment. This formula is an initial estimate; measure peak resident memory and runtime overhead under realistic conditions.

### 4.1. Signs of insufficient memory

- The function hits OOM or the runtime exits abnormally.
- Memory utilization stays close to the limit for extended periods.
- Garbage collection runs frequently or pause times climb in GC-managed runtimes.
- The process continuously evicts caches.
- Payloads above a threshold cause failures even though CPU has headroom.
- Files are read completely into RAM instead of streamed in chunks.

When OOM occurs, inspect logs and runtime metrics to determine peak memory. Do not just raise memory without checking for leaks, lingering object references, unbounded payloads, or full-file reads into memory.

### 4.2. Heap and native memory

For Java, .NET, Node.js, or VM-based runtimes, the function memory limit does not equal maximum heap size. Native memory, thread stacks, JIT code, direct buffers, TLS, and native libraries all consume memory. Configuring heap too close to the instance limit can trigger OOM before the heap even hits its ceiling.

In Python, object overhead and copies created during parsing/transformation can multiply memory usage well beyond raw payload size. In Node.js, buffers and large object graphs can retain memory longer than expected. Measure resident memory and runtime metrics rather than relying solely on input size.

### 4.3. Trim memory before raising the tier

Commonly effective steps:

- Stream files and responses instead of loading them entirely into RAM.
- Process data in small chunks or batches.
- Avoid creating redundant payload copies.
- Release references to large objects promptly after use.
- Cap request sizes and items per batch.
- Trim unnecessary caches or set strict TTL/size bounds.
- Choose data structures suited to the operation.
- Tune concurrency to fit each invocation’s working set.

If the workload genuinely requires large memory, raising the tier is appropriate. The goal is provisioning for valid peaks with headroom, not defaulting to the maximum limit.

## 5. Choosing memory and CPU through benchmarks

Instead of guessing, run the same workload across several valid configuration levels. Record:

- Allocated memory.
- CPU share or vCPUs if published by the platform.
- Invocation duration p50/p95/p99.
- Peak memory and OOM count.
- CPU utilization/throttling.
- Concurrency and execution environment count.
- Error/timeout rate.
- Cost per successful invocation or cost per batch.

Illustrative example for a JSON processing and data compression workload:

| Memory setting | Median duration | Peak memory | Outcome |
|---:|---:|---:|---|
| 512 MB | 1,200 ms | 470 MB | Risk of hitting limit on large payloads |
| 1 GB | 720 ms | 520 MB | Completes stably |
| 2 GB | 390 ms | 540 MB | Faster, though diminishing returns begin |
| 4 GB | 360 ms | 550 MB | Minimal speedup compared to added cost |

Numbers are illustrative only. When CPU scales with memory, duration can drop significantly even while peak memory stays flat. The 2 GB setting may be the sweet spot; 4 GB makes sense only if latency requirements demand that extra gain or per-task cost still improves.

### 5.1. Calculating cost per useful outcome

Under a GB-second pricing model, estimate compute cost for one invocation:

\[
C_{compute} \approx M_{GB} \times T_{billed} \times R_{GB-second}
\]

Where:

- `M` is allocated memory converted to GB.
- `T` is billed duration per platform rounding rules.
- `R` is the GB-second unit rate.

Some platforms bill CPU separately, charge per request, charge for concurrency, or enforce minimum billing durations; adjust the formula to match the actual billing model. Add overage fees for temporary storage and supporting services as applicable.

Cost per million successful invocations:

\[
C_{1M} =
\frac{C_{total}}
{N_{successful}}
\times 1{,}000{,}000
\]

Do not use total invoked count as the denominator if some requests time out or fail. For batch jobs, you can track cost per million records or cost per valid job.

## 6. Function execution time and timeouts

The execution timeout is the maximum duration the platform allows an invocation to run before terminating it or marking it failed. Exact limits depend on the provider, function type, runtime, plan, and service version.

Choose timeouts based on actual duration distributions and SLOs:

- p50 shows typical processing time.
- p95/p99 reveal the slow tail.
- Max duration flags outliers, though it can be noisy.
- Timeouts must allow enough time for valid loads and short fluctuations.
- Timeouts should not be endlessly long to hide hung dependencies or unbounded jobs.

For example, if normal p99 is 4 seconds and the SLO allows 8 seconds, set the invocation deadline reasonably above p99 for buffer, then set individual dependency timeouts smaller than the remaining deadline.

### 6.1. Overall deadline vs. dependency timeouts

A single invocation may perform several steps: reading the event, fetching secrets, calling APIs, querying a database, writing objects, and publishing messages. If each step has a long independent timeout, total time can exceed the execution timeout.

Propagate the remaining deadline through layers:

\[
T_{remaining} = T_{deadline} - T_{now}
\]

Each dependency gets a timeout no larger than the remaining time minus a reserve for cleanup and response. Set separate connect timeouts, read timeouts, query timeouts, and retry budgets.

When approaching the deadline, stop starting new work, cancel cancellable requests, and record state. Never start a retry if insufficient time remains to finish usefully.

### 6.2. Timeouts and side-effect handling

If a function times out after sending a write or payment request, the client may not know whether the operation completed. Retrying can create duplicate transactions.

Mitigations:

- Use idempotency keys for operations with side effects.
- Record job state via appropriate transactions or the outbox pattern.
- Design bounded retries with backoff.
- Distinguish definitive failures from ambiguous outcomes.
- Provide a status-check mechanism before retrying.

A timeout does not guarantee downstream work is automatically aborted. A request that already reached a database or external service can keep executing even after the function terminates.

## 7. When should a long job be split into multiple steps?

If work regularly approaches the timeout limit, reconsider the execution model. Functions suit short, bounded tasks that can be triggered by events. Long or multi-step jobs can move to workflows or container workers.

Signs you should split the job:

- Duration p95/p99 sits close to the timeout ceiling.
- Checkpointing is needed after each chunk of data.
- Waiting on dependencies can take several minutes.
- Retrying the entire job is expensive.
- A single invocation requires huge memory or massive temporary files.
- Pause/resume or human approval is required between steps.
- The job requires a long-lived process or persistent connections.

One design pattern is splitting large files into chunks, pushing each chunk onto a queue, and processing them independently. Workflow orchestration can coordinate state, retries, timeouts, and failure branches. Ensure ordering, idempotency, and partial-result handling.

## 8. What is temporary storage?

Temporary storage is local space reserved for transient data inside the execution environment. Depending on the platform, it may be mounted at a path like `/tmp` or exposed as a scratch disk.

Common use cases:

- Downloading files from object storage prior to processing.
- Extracting archives.
- Writing intermediate files for image/video libraries.
- Caching models or packages within the environment.
- Staging output files before uploading to object storage.
- Using SQLite or scratch files scoped to a single execution when appropriate.

Temporary storage is not a durable database or object store. Environments can be reclaimed, replaced, or scheduled onto other instances. Never assume files will exist on the next invocation.

### 8.1. Distinguishing memory from temporary storage

| Property | Memory | Temporary storage |
|---|---|---|
| Access method | Variables, objects, buffers in process | Files via filesystem/API |
| Speed | Usually very fast | Depends on storage backing and I/O |
| Capacity | Bounded by memory tier/instance | Bounded by ephemeral storage quota |
| Lifecycle | Tied to process/environment and runtime | Tied to storage/environment lifecycle |
| Sharing | Within process/runtime per concurrency model | May be shared across invocations on the same environment if retained, though never guaranteed |
| Purpose | Active working set | Intermediate files, scratch data, transient caches |
| Durability | Not durable storage | Not durable storage |

If a file can be reconstructed from durable sources, temporary storage fits well. If results must survive after the invocation ends, write them to object storage, a database, or a durable service before returning success.

### 8.2. Lifecycle and reusability

Some platforms retain execution environments to serve subsequent invocations. In that case, files in the temporary directory may survive into a later warm call. However:

- The platform can delete the environment at any time per service lifecycle rules.
- Another invocation may land on a different environment.
- Scale-out spins up additional environments with separate filesystems.
- Deploying a new version can create fresh environments.
- There is no guarantee of ordering or affinity across invocations.

Consequently, temporary storage should serve only as a performance cache, never as the authoritative data source.

## 9. Sizing temporary storage

Estimate the maximum total size that can coexist simultaneously on the filesystem.

A reference formula:

\[
D_{required} \approx
D_{input} + D_{extracted} + D_{intermediate}
+ D_{output} + D_{cache} + D_{safety}
\]

Watch out for compressed files that expand many times over when extracted. A video file can spawn multiple temporary segments. An image pipeline might hold the input, decoded bitmap, resized image, and output on disk concurrently.

For example, a function receives a 300 MB archive, extracts 1.2 GB, creates 500 MB of intermediate files, and produces a 250 MB output. If all coexist, disk demand can exceed 2 GB before counting caches and headroom. Clean up intermediate files early or stream/chunk processing to lower peak disk usage.

### 9.1. Provisioned vs. used capacity

Some platforms let you select ephemeral storage size; others grant a fixed amount or plan-based quota. Verify:

- Default and maximum capacity.
- Whether storage is billed or includes a free tier.
- Whether storage is disk-backed or a memory-backed filesystem.
- Whether it is shared across concurrent invocations on one instance.
- Whether IOPS/throughput limits apply.
- How data is encrypted and isolated across tenants/environments.
- Whether files are wiped when the instance terminates.

Do not infer temporary storage from the memory limit. Increasing memory does not necessarily enlarge the filesystem.

## 10. Managing temporary files safely

Temporary files can contain customer data, tokens, or business payloads. Apply these practices:

- Use unique filenames and a dedicated directory per invocation.
- Never trust client-supplied filenames or paths; prevent path traversal.
- Create files with restrictive permissions.
- Avoid writing secrets or credentials to temporary files unless necessary.
- Delete files upon completion or in cleanup paths.
- Enforce quotas and input size caps.
- Do not rely on cleanup running only on normal exit; timeouts/crashes can skip cleanup.
- Ensure files from a prior invocation cannot be accidentally read by the next invocation.
- Never dump sensitive file contents into logs.

Python example using an isolated temporary directory:

~~~python
from pathlib import Path
from tempfile import TemporaryDirectory

def handler(event, context):
    with TemporaryDirectory(prefix="job-") as temp_dir:
        workdir = Path(temp_dir)
        input_path = workdir / "input.bin"
        output_path = workdir / "output.bin"

        # Download data from durable storage to input_path.
        # Process in chunks to control memory usage.
        # Write output_path and upload the result to object storage.

        return {"status": "completed"}
~~~

This is a skeleton example. Download, processing, and upload steps need timeouts, size checks, bounded retries, and error handling. For large files, stream directly or process in chunks rather than loading everything into memory.

## 11. Combining memory and temporary storage for large files

A file-processing pipeline typically has four options:

1. **Load entirely into memory:** simple and fast for small files, but peak memory can exceed file size due to decoding and copies.
2. **Use temporary files:** eases RAM pressure, though sufficient disk and I/O are needed.
3. **Streaming:** reads/writes chunk by chunk, reducing both memory and intermediate disk usage.
4. **Split across multiple functions/jobs:** fits huge files or long processing times, but requires managing orchestration and invocation cost.

For example, do not read a 500 MB file into RAM if the library makes two extra copies. Peak memory could top 1 GB. If the algorithm supports streaming, 8 MB or 16 MB chunks can shrink the working set dramatically. Benchmark chunk sizes against real CPU, I/O, and throughput.

## 12. How concurrency affects CPU and memory

Concurrency is the number of invocations running simultaneously. It exists at multiple levels:

- Function-wide concurrency.
- Account/project/region-wide concurrency.
- Per-execution-environment concurrency.
- Runtime or worker-thread concurrency inside a process.
- Dependency concurrency such as database connections or HTTP pools.

As concurrency rises, throughput climbs until CPU, memory, network, or dependencies hit a limit. Beyond that point, latency and errors typically spike rapidly.

A memory estimate:

\[
M_{peak} \approx M_{base} + C \times M_{per-invocation}
\]

If each invocation holds a 120 MB working set and an environment runs 5 concurrent invocations, per-request memory runs roughly 600 MB above baseline. Measure because runtimes may share caches or duplicate payloads.

Do not set concurrency solely by desired request rate. Check database connection limits, external API rate limits, file descriptors, sockets, and downstream capacity.

### 12.1. Capping concurrency to protect dependencies

If a database can sustain only 200 connections for this workload, thousands of concurrent functions cannot open direct connections simultaneously. You may need:

- Reserved/maximum concurrency on the function.
- Connection pooling or a managed connection proxy.
- Queues to absorb bursts.
- Request batching or operation coalescing.
- Backpressure and retries with jitter.
- Rate limiting on dependency calls.

Concurrency acts as a system-wide guardrail, not merely a knob to boost function throughput.

## 13. Cold starts, warm starts, and resource sizing

A cold start is the time the platform needs to spin up a new execution environment, initialize the runtime, load code/dependencies, and run initialization before handling an invocation. Warm invocations can reuse an already-ready environment.

CPU and memory influence startup differently by platform:

- More CPU can speed up package extraction, module loading, or JIT compilation.
- Larger memory can bring a larger CPU share on some services.
- Large packages, heavy dependencies, or expensive initialization lengthen cold starts.
- JIT runtimes or heavy frameworks may require warm-up.
- Provisioned/warm capacity cuts cold starts at the cost of paying for ready environments.

Measure cold-start latency separately from warm invocation duration. Do not rely on blended averages, which hide the experience of initial requests during scale-out.

### 13.1. Reducing cold starts

- Shrink package size and remove unused dependencies.
- Avoid repeating client initialization or config reads if safely reusable.
- Choose a runtime suited to the workload and startup budget.
- Trim heavy work during initialization.
- Use provisioned/warm capacity when SLOs demand it and cost is justified.
- Measure cold starts after deployments, scale-outs, and long idle periods.

Do not keep business state or long-lived credentials in global variables merely to trim startup without assessing risk. Reusing connections/clients must handle stale connections, credential rotation, and network faults.

## 14. Costs tied to CPU, memory, runtime, and temporary storage

Serverless billing models vary across providers and service tiers. Cost components can include:

- Invocation/request count.
- Memory allocation multiplied by billed duration.
- CPU allocation or vCPU-time.
- Provisioned concurrency or warm instances.
- Temporary storage exceeding included allowances.
- Network egress and NAT.
- Log ingestion, metrics, and traces.
- Queues, workflows, databases, and object storage.
- Retries or failed invocations when platforms still bill execution time.

A general cost model:

\[
C_{total} =
C_{requests} + C_{compute} + C_{temp-storage}
+ C_{network} + C_{observability} + C_{dependencies}
\]

Do not optimize invocation price alone. A cheap function that triggers excessive retries, hammers databases, or emits massive log volume can drive total cost higher.

### 14.1. Higher memory can be cheaper when execution finishes faster

If the platform scales CPU with memory, a higher memory tier can finish invocations faster. Illustrative example:

| Configuration | Memory | Duration | Approximate GB-seconds |
|---|---:|---:|---:|
| A | 0.5 GB | 0.8 s | 0.40 |
| B | 1.0 GB | 0.4 s | 0.40 |
| C | 2.0 GB | 0.3 s | 0.60 |

Under this simplified model, A and B consume the same GB-seconds, yet B finishes twice as fast and can raise throughput or avoid timeouts. C is slightly faster but consumes more GB-seconds. This excludes real-world billing nuances such as per-request fees, separate CPU pricing, rounding increments, concurrency, ephemeral storage, and dependency costs.

### 14.2. Costs from timeouts and retries

If a function times out after burning most of its budget on an unresponsive dependency, retries can repeat that same cost. Simply slashing timeouts can spike errors if the dependency normally exhibits high tail latency. Combine:

- Reasonable timeouts aligned with p99 and deadlines.
- Retries restricted to transient errors and safe operations.
- Exponential backoff and jitter.
- Idempotency.
- Circuit breakers or queues when dependencies degrade.
- Tracking cost per successful operation.

## 15. Conceptual configuration example

The fields below illustrate sizing intent rather than a ready-to-use manifest for a specific provider:

~~~yaml
function:
  name: image-resizer
  runtime: python
  memory: 2048Mi
  cpu: platform-defined-by-memory-tier
  timeout: 30s
  concurrency:
    max-per-function: 40
    per-instance: platform-default
  temporary-storage:
    size: 3Gi
    use: intermediate-image-files
  observability:
    log-level: info
    capture-duration: true
    capture-memory-peak: true
~~~

When translating to real configuration, map fields to the exact service, plan, and API. Some platforms do not expose separate CPU tuning; some use MB instead of MiB; per-instance concurrency may be governed by the runtime or host.

### 15.1. How to read this configuration

- 2 GiB memory is the environment limit/allocation under the platform model, not guaranteed constant usage.
- CPU is allocated per platform rules; verify actual CPU share.
- The 30-second timeout is illustrative and must reflect latency and SLOs.
- Max concurrency 40 is a function-wide cap in this example; it does not imply one instance runs 40 calls at once.
- 3 GiB temporary storage is intended for intermediate files, not long-term result persistence.
- Observability should measure duration, peak memory, and errors without logging sensitive data.

## 16. Sizing workflow from real workloads

A practical workflow:

1. **Profile the workload:** input sizes, request rates, bursts, CPU/I/O mix, and dependencies.
2. **Define SLOs:** p95/p99 latency, error rate, maximum duration, and throughput.
3. **Check platform limits:** memory tiers, CPU model, timeouts, concurrency, ephemeral storage, and payload caps.
4. **Pick a baseline:** a configuration small enough to measure without hitting immediate OOM on standard loads.
5. **Run benchmarks:** vary one dimension at a time, such as memory or concurrency.
6. **Measure resources:** CPU, peak memory, duration, cold starts, and temporary disk usage.
7. **Test peaks:** large payloads, bursts, high concurrency, and slow dependencies.
8. **Compute cost per success:** include invocations, compute, storage, and dependencies.
9. **Add headroom:** absorb input and traffic variance.
10. **Pilot in production:** observe real behavior and tune from telemetry.
11. **Set guardrails:** concurrency caps, timeouts, input size limits, and quotas.
12. **Re-benchmark:** whenever runtimes, libraries, code, regions, or billing models change.

### 16.1. Test matrix

| Run | Memory | Concurrency | Input | Goal |
|---|---:|---:|---|---|
| 1 | Lowest valid | 1 | P50 | Baseline |
| 2 | Medium | 1 | P50 | Measure memory/CPU impact |
| 3 | Higher | 1 | P50 | Find diminishing returns |
| 4 | Selected tier | Expected level | P50 | Check contention |
| 5 | Selected tier | Expected peak | P95 input | Check memory/disk peaks |
| 6 | Selected tier | Burst | P95 input | Check scale-out, cold starts, and dependencies |

Change only one variable group per pass to isolate cause and effect. Changing memory, timeout, runtime, and concurrency simultaneously obscures what helped or hurt.

## 17. Example: an image-processing function

A function receives an event with an object key, downloads the image from object storage, resizes it, and writes the output image back to storage.

Resources to consider:

- **CPU:** decoding, resizing, encoding images; more CPU can shorten processing time.
- **Memory:** decoded images can be many times larger than compressed files; concurrent images raise peak memory.
- **Timeout:** covers download, decode, transform, and upload; leave buffer for storage tail latency.
- **Temporary storage:** input and output files if the library needs a filesystem; can be reduced via streaming.
- **Concurrency:** cap to avoid excessive parallel downloads/encodes and protect object storage.
- **Idempotency:** retrying the same event must not corrupt outputs or overwrite uncontrollably.

Reference flow:

~~~mermaid
flowchart TD
    A[Object-created event] --> B[Validate key and size]
    B --> C[Download or stream input]
    C --> D[Decode and resize]
    D --> E[Encode output]
    E --> F[Upload result]
    F --> G[Record completion]
    G --> H[Return success]
    C --> X[Retry or dead-letter on failure]
    D --> X
    F --> X
~~~

For large images, the function should validate dimensions and format before decoding. Temporary files or streaming can be used depending on the library. If processing time approaches function limits, split images into smaller tasks or use a container worker.

## 18. Runtime and package size

The runtime affects startup, baseline memory, CPU behavior, and library compatibility.

- Lightweight runtimes or native binaries can start fast, though libraries and portability must be verified.
- VM/JIT runtimes may require warm-up and carry a higher memory baseline.
- Packages with many dependencies lengthen download and initialization.
- Native extensions must match OS, CPU architecture, and ABI.
- Large container images can slow cold starts or image pulls depending on the platform.

No single runtime is best for every workload. Benchmark equivalent functionality under identical conditions; do not switch runtimes alongside algorithms or datasets and credit all gains to CPU/memory.

## 19. Platform limits to verify

Before deploying, check current limits for your provider and plan. Limits may include:

- Minimum/maximum memory and valid step increments.
- CPU shares, vCPUs, or CPU quotas.
- Maximum execution timeout.
- Default/maximum temporary storage and unit pricing.
- Payload/request/response size limits.
- Package or image size caps.
- File descriptor, thread, and process limits.
- Concurrency per function, account, or region.
- Execution environment count and scale-out quotas.
- Network access, VPC attachment, and cold-start overhead.
- Log, deployment, and invocation rate limits.

Limits can differ across service generations, regions, plans, and runtimes. Never copy a number from another provider’s example or an old config without verifying.

## 20. Post-deployment monitoring

Track metrics to verify the configuration fits production workloads:

| Metric | Question to answer |
|---|---|
| Invocation duration p50/p95/p99 | Is execution approaching the timeout? |
| Max/peak memory | Is memory close to the limit? |
| CPU utilization/throttling | Is the function CPU-bound or throttled? |
| Timeout/error count | Are failures concentrated in payloads, dependencies, or resource limits? |
| Concurrent executions | Is concurrency exceeding downstream capacity? |
| Cold start/init duration | Is scale-out driving up latency? |
| Temporary storage used | Is scratch space nearing capacity or growing abnormally? |
| Retry/DLQ count | Are there recurring errors or poison events? |
| Cost per successful invocation | Is cost per useful outcome climbing? |
| Dependency latency | Is time spent inside the function or external services? |

Alert on trends and SLOs rather than a single raw CPU threshold. For instance, peak memory near the limit paired with OOMs is a strong signal; brief high CPU during bursts can be healthy if latency targets still hold.

## 21. Checklist for choosing CPU, memory, timeout, and temporary storage

- [ ] Classified workload as CPU-bound, memory-bound, or I/O-bound.
- [ ] Verified whether CPU scales with memory or is configured independently.
- [ ] Measured runtime baseline, peak memory, and per-request working set.
- [ ] Accounted for concurrency impact on CPU and memory.
- [ ] Checked for OOMs, GC pressure, buffers, and memory leaks.
- [ ] Measured p50/p95/p99 duration and cold-start latency.
- [ ] Aligned invocation timeout and dependency timeouts with the overall deadline.
- [ ] Bounded retries with backoff, jitter, and idempotency for side effects.
- [ ] Distinguished memory from the temporary filesystem.
- [ ] Sized input, extracted, intermediate, output, and safety headroom for disk.
- [ ] Isolated temporary files, capped input sizes, and enforced cleanup.
- [ ] Persisted durable data to appropriate storage before returning success.
- [ ] Verified concurrency limits and downstream dependency capacity.
- [ ] Benchmarked multiple configurations against identical workloads and correctness metrics.
- [ ] Included compute, requests, storage, and dependencies in cost per successful operation.
- [ ] Verified current limits for provider, plan, region, and runtime.
- [ ] Configured dashboards/alerts for duration, memory, concurrency, temp storage, and cost.
- [ ] Established a plan to split long jobs into workflows or workers when needed.

## 22. Conclusion

CPU governs compute speed; memory must fit the runtime, libraries, and working set at peak concurrency; execution timeout caps each invocation’s duration; temporary storage holds intermediate files across the environment’s lifetime. These resources interact yet cannot substitute for one another: adding memory does not necessarily expand disk, extending timeouts does not fix slow dependencies, and adding CPU helps little when a function mostly waits on I/O.

Size based on real workloads, measure duration and peak resources across concurrency levels, inspect cold starts, track cost per successful operation, and keep adequate headroom. Temporary storage is purely scratch space; durable data must be written to an appropriate storage service. When limits, timeouts, cleanup, and observability are thoughtfully designed, serverless functions run reliably at appropriate resource and cost levels.
