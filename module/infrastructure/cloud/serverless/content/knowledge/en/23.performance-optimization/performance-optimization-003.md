# Tuning Memory, CPU, and Timeouts Based on Measurements

In the **Performance Optimization** chapter, tuning memory, CPU, and timeouts is the process of finding the configuration that matches actual workload, latency requirements, and budget. Increasing memory can help a function run faster if the platform allocates additional CPU alongside memory; increasing the timeout only gives the function more time to finish, without making the code itself faster. If configurations are chosen by guesswork, the system may cost more, hold concurrency longer, or still time out on slow requests.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying applications using the serverless model, especially Java functions triggered by HTTP, messages, or events. Learners work with triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to determine when to use FaaS. Performance optimization requires measuring execution duration, memory usage, CPU, cold starts, retries, and throughput in the context of real triggers.

## 1. Why Tune Based on Measurements?

A slow function does not necessarily lack CPU or memory. The cause may be:

- High-complexity algorithms or redundant data processing.
- Waiting on a database, HTTP API, DNS, or message broker.
- Connection pool exhaustion or blocked threads.
- Frequent garbage collection.
- The JVM initializing classes, JIT compiling, or opening connections during a cold start.
- Function throttling due to concurrency or quota limits.
- Incompatible timeouts across dependencies, the function, and the caller.
- Retries causing a single workload to execute multiple times.

Therefore, do not start by blindly increasing timeouts or memory across the board. First, identify the bottleneck and measure a baseline. A change only counts as an improvement when the target metric improves without degrading cost, error rate, or other guardrail metrics.

## 2. How Do Memory, CPU, and Timeouts Relate?

These three settings influence one another yet mean different things.

| Parameter | Meaning | Primary Impact |
|---|---|---|
| Memory | Memory limit allocated to the execution environment | Heap, native memory, buffers, and data processing capacity |
| CPU | Compute capacity allocated by the platform | Computation speed, compression, encryption, parsing, and part of initialization time |
| Timeout | Maximum duration for a single invocation | Processing time limit before the platform terminates the invocation |

On AWS Lambda, CPU is allocated proportionally to the memory configuration. Increasing memory can simultaneously increase CPU and certain other resource capacities of the execution environment. On other platforms, CPU and memory may be configured independently or in predefined resource tiers; be sure to verify the model of the runtime you use.

Timeout is only an upper bound. If a function needs 2 seconds to process but has a 60-second timeout, the function will not run any faster on its own. A longer timeout can hold concurrency longer when a dependency hangs, increasing queue age and making callers wait.

The goal is to choose enough memory/CPU to handle the expected load with acceptable latency and cost, then set the timeout just long enough for valid processing time plus measured variance.

## 3. Measure a Baseline Before Making Changes

A good baseline should reflect real traffic, not just a single manual call.

Collect:

- Invocation count and request rate.
- Duration p50, p95, and p99.
- Error rate, timeouts, and throttling.
- Max Memory Used and memory allocation.
- Init Duration or cold start duration.
- Concurrent executions.
- Queue age, iterator age, and retry count for event triggers.
- Throughput: successful requests or messages processed per second.
- Cost per invocation and per unit of completed work.

Measure across scenarios:

1. Cold start after creating a new execution environment.
2. Warm invocation when an environment is reused.
3. Small, medium, and large payloads.
4. Normal load and peak load.
5. Fast-responding dependencies and controlled slow-dependency scenarios.
6. Production-like batch size, architecture, and concurrency.

Do not compare two configurations if inputs, deployment region, downstream load, or concurrency differ significantly. Record the commit, runtime version, memory, timeout, environment, and benchmark timestamp so the measurement can be reproduced.

## 4. Key Metrics

### 4.1. Duration and Percentiles

Duration measures handler execution time as defined by the platform. Averages are useful for seeing overall trends, but can obscure a subset of very slow invocations.

- p50 shows the experience of the invocation at the middle of the distribution.
- p95 shows that 95% of invocations finish within this time or less.
- p99 helps reveal tail latency and rare but very slow requests.
- Maximum can be skewed by outliers or downstream incidents.

Set SLOs using percentiles appropriate for the user experience. Interactive APIs typically focus on p95/p99; background batch processing may focus on throughput and total batch completion time.

Function duration is not always end-to-end latency. For HTTP, there is also gateway, authorizer, network, and client time. For queues, there is also wait time before a message is processed and retry time.

### 4.2. Memory Metrics

On AWS Lambda, the REPORT line in CloudWatch Logs can provide Memory Size and Max Memory Used for an invocation. This is a key signal for detecting when a function is approaching its limit.

Example report line:

~~~text
REPORT RequestId: ... Duration: 840.12 ms
Billed Duration: 841 ms Memory Size: 1024 MB
Max Memory Used: 612 MB Init Duration: 420.00 ms
~~~

The numbers above illustrate only how to read the fields, not a benchmark or latency commitment. Max Memory Used is the peak usage recorded by the platform for the invocation; it does not state separately how much Java heap was used.

If Max Memory Used approaches Memory Size, inspect heap, native memory, thread stacks, direct buffers, class metadata, and native libraries. Do not look only at a heap dump and conclude the entire process still has plenty of memory.

### 4.3. Cold Start and Init Duration

A cold start may include runtime startup, class loading, running static initializers, creating clients, and establishing connections. With Java, class loading, framework bootstrap, and JIT warm-up can make initialization substantial.

In AWS Lambda, Init Duration appears separately in the REPORT log for invocations that undergo an init phase. Handler Duration and Init Duration should be analyzed separately to avoid attributing the entire latency to request-processing code.

A higher memory setting can shorten part of init if the function receives more CPU, but it does not replace trimming heavy dependencies or avoiding unnecessary initialization.

### 4.4. Metrics by Trigger

| Trigger | Metrics to Track |
|---|---|
| HTTP | Integration latency, response code, request rate, throttles |
| SQS | ApproximateAgeOfOldestMessage, messages visible, DLQ depth, retries |
| Kinesis/DynamoDB Streams | IteratorAge, batch failure, checkpoint lag |
| Async invocation | Event age, retries, dropped events |
| Scheduled | Lateness, duration, missed/overlapping runs |

Do not optimize only the function's Duration. A function with low Duration whose queue age keeps rising still fails to meet processing requirements.

## 5. Understanding Java Runtime Memory

A function's memory allocation is typically a limit for the entire execution environment or container, not just the Java heap.

A JVM process can use:

- **Java heap:** objects, arrays, and most application data.
- **Metaspace:** class metadata.
- **Code cache:** machine code generated by the JIT compiler.
- **Thread stacks:** memory region for each thread.
- **Direct buffers:** off-heap buffers, such as NIO.
- **Native memory:** native libraries, TLS, compression, and runtime.
- **Agent/extension memory:** if the platform runs additional processes or extensions counted toward the same limit.

If heap still has free space yet the process exceeds its memory limit, check native memory, thread count, direct buffers, and extensions. Conversely, if heap is frequently near max heap, GC may run more often and increase tail latency.

### 5.1. Observing Heap and Non-Heap in Java

You can read basic JVM metrics:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public final class JvmMemorySnapshot {
    private JvmMemorySnapshot() {
    }

    public static void logSnapshot() {
        var memoryBean = ManagementFactory.getMemoryMXBean();

        MemoryUsage heap = memoryBean.getHeapMemoryUsage();
        MemoryUsage nonHeap = memoryBean.getNonHeapMemoryUsage();

        long maxHeap = Runtime.getRuntime().maxMemory();
        long freeHeap = Runtime.getRuntime().freeMemory();

        System.out.printf(
                "heapUsed=%d heapCommitted=%d heapMax=%d " +
                "nonHeapUsed=%d runtimeMaxHeap=%d freeHeap=%d%n",
                heap.getUsed(),
                heap.getCommitted(),
                heap.getMax(),
                nonHeap.getUsed(),
                maxHeap,
                freeHeap);
    }
}
~~~

These values help analyze the JVM, but do not replace the platform's Max Memory Used. Runtime.maxMemory reflects the heap limit recognized by the JVM, not the function's entire memory quota.

Avoid logging snapshots on every invocation if that creates excessive logs and cost. Sample them, log during benchmarks, or emit custom metrics with low cardinality.

### 5.2. Watch Threads and Direct Buffers

An oversized thread pool can consume thread stack memory and send too many concurrent requests to dependencies. Direct buffers can use native off-heap memory. An oversized connection pool can increase sockets, threads, and memory even when heap looks fine.

Bound executors, HTTP connection pools, database connection pools, and buffers according to actual concurrency. Do not create a new thread pool per invocation when a single thread-safe client/thread pool can be reused within the execution environment.

## 6. Identifying CPU-Bound, Memory-Bound, or I/O-Bound Bottlenecks

Before increasing memory, classify the workload.

| Symptom | Possible Bottleneck | Remediation Direction |
|---|---|---|
| CPU near saturation, high wall time | CPU-bound | Increase CPU if possible, optimize algorithms |
| Memory near limit, frequent GC | Memory-bound | Increase memory, reduce allocations/working set |
| Low CPU, high wait time | I/O-bound | Optimize network, connection pools, timeouts |
| High p99 but good p50 | Tail latency | Look for outliers, locks, GC, cold starts, retries |
| High init duration | Cold start/bootstrap | Reduce classpath/init, reuse clients, consider provisioned capacity |
| Increasing throttles | Concurrency/quota | Adjust concurrency, load, and downstream capacity |

CPU time and wall-clock time are different. A function may burn 100 ms of CPU yet take 2 seconds because it waits on a database. Increasing CPU may yield little improvement if most time is spent waiting on the network.

Use a profiler or traces to pinpoint time-consuming code. For Java, Java Flight Recorder (JFR), async-profiler, or a runtime-compatible profiler can help find hot methods, allocation pressure, lock contention, and GC pauses. Production profiling should be enabled carefully since it can add overhead.

## 7. Trading Memory for CPU

On AWS Lambda, increasing memory simultaneously increases allocated CPU. Thus, a CPU-bound function sometimes runs significantly faster when memory is increased, even if the data itself does not need extra heap.

Workloads that commonly benefit:

- File compression/decompression.
- Data encryption, decryption, or signing.
- Parsing large JSON/XML payloads.
- Image or document conversion.
- Computation and batch processing.
- Heavy Java framework initialization.

If the function mostly waits on HTTP or a database, increasing memory may not reduce latency proportionally. Benchmark multiple memory tiers and compare both duration and GB-seconds.

### 7.1. Do Not Infer from Heap Percentage Alone

30% heap usage does not prove the function is over-provisioned on memory. The function may be CPU-limited and need higher memory to obtain more CPU. Conversely, 90% heap usage does not necessarily require more memory if you can reduce object allocations or fix a memory leak.

Compare:

- Platform-level Max Memory Used.
- Heap used/max and GC behavior.
- CPU profile or CPU utilization if provided by the platform.
- Duration p50/p95/p99.
- Cost per successful unit of work.

## 8. Choosing Memory via Controlled Benchmarks

A practical approach is testing several memory tiers on the same workload. Do not change code, payload, concurrency, or downstream services simultaneously.

Procedure:

1. Use the current memory setting as the baseline.
2. Select several lower/higher tiers within platform limits.
3. Run the same representative set of payloads.
4. Repeat enough times to observe the distribution.
5. Separate cold starts and warm invocations.
6. Record Duration, p95/p99, Max Memory Used, errors, and cost.
7. Choose the configuration that meets the SLO at an appropriate cost.
8. Rerun at production-like concurrency to confirm.

For AWS Lambda, AWS Lambda Power Tuning is an open-source tool using Step Functions to execute a function across multiple memory tiers and compare execution time and estimated cost. The tool helps automate testing, but results still depend on payload, downstream services, concurrency, and test data generation. Run it in a test account/environment, bound invocation counts, and avoid using sensitive production data.

The table below uses hypothetical numbers to illustrate the calculation, not measurements from a real application:

| Memory | Mean duration | p95 | Max memory used | Memory × mean duration |
|---:|---:|---:|---:|---:|
| 512 MB | 2.40 s | 3.80 s | 455 MB | 1.20 GB-s |
| 1024 MB | 1.30 s | 2.00 s | 470 MB | 1.30 GB-s |
| 1536 MB | 0.82 s | 1.20 s | 490 MB | 1.23 GB-s |
| 2048 MB | 0.55 s | 0.82 s | 500 MB | 1.10 GB-s |

In this example, 2048 MB delivers the best p95 and lowest GB-seconds among the four options. The 1024 MB tier is faster than the baseline yet has higher GB-seconds. This demonstrates that higher memory is not necessarily more expensive per invocation if duration drops enough.

The GB-seconds formula in the table is memory in GB multiplied by mean duration in seconds. Actual billing also depends on platform rounding granularity, invocation type, architecture, enabled features, and current pricing. Use actual billing/usage data to decide.

## 9. Measuring Cost per Successful Unit of Work

Cost is not merely memory multiplied by duration. A general model:

\[
Cost \approx RequestCost + GBSeconds \times UnitPrice + OtherCharges
\]

Where:

- RequestCost depends on the number of invocations.
- GBSeconds depends on configured memory and billed duration.
- OtherCharges may include provisioned concurrency, data transfer, log ingestion, storage, extensions, or downstream services.

Remember to include retries. If a message takes three invocations to succeed, the cost per completed message is higher than a single invocation. A timeout can cause the function to be retried, generating extra database, queue, and network costs.

Metrics to track:

- Cost per 1,000 successful requests.
- Cost per completed message or batch.
- Retry and DLQ rates.
- Log and trace costs.
- Provisioned concurrency cost if used.
- Downstream costs generated by the function.

Do not optimize cost by cutting memory to the point where timeouts or retries increase. The cheapest configuration per invocation may not be the cheapest configuration per successful unit of work.

## 10. Optimizing CPU for Java

If the workload is CPU-bound, combine resource configuration with code optimization.

Useful steps:

- Profile hot methods before changing algorithms.
- Avoid parsing the same payload multiple times.
- Reduce object allocations in hot loops.
- Use streaming parsers for large data when appropriate.
- Avoid unnecessary serialization/deserialization.
- Choose appropriate algorithms and data structures.
- Limit parallelism to the allocated CPU.
- Avoid creating excessive threads and context switches.
- Reuse thread-safe clients instead of re-initializing them.

Do not use parallel streams or large thread pools assuming the function has many CPUs. On FaaS, CPU count can vary with memory tier or runtime configuration. Excessive parallelism can increase contention and memory usage without improving throughput.

### 10.1. Timing Code Blocks

Use System.nanoTime for intervals within the same process:

~~~java
long startedAt = System.nanoTime();

OrderResult result = orderService.process(command);

long elapsedNanos = System.nanoTime() - startedAt;
double elapsedMillis = elapsedNanos / 1_000_000.0;

// Emit metric with bounded name and dimensions.
// Avoid logging every invocation if volume is high.
metrics.recordDuration("order.process", elapsedMillis);
~~~

Do not use System.currentTimeMillis to measure short durations because the wall-clock can be adjusted. Do not put customer IDs, request IDs, or unbounded values into metric dimensions due to high cardinality.

## 11. Optimizing Memory and Garbage Collection

A high allocation rate can trigger frequent GC, increasing latency and CPU usage. Some ways to address this:

- Avoid allocating temporary objects in tight loops.
- Do not hold unbounded collections or caches.
- Use streaming instead of loading entire files onto the heap.
- Bound batch sizes and payloads.
- Set TTL/size bounds for caches.
- Avoid retaining references to request data after an invocation ends.
- Choose a GC and JVM options suited to the runtime after measuring.

Do not change GC collectors or JVM flags just because a blog post recommends it. Collect GC logs or JFR during benchmarks, observe pause times, allocation rates, and heap occupancy, and only then make changes.

With Java Lambda, a static cache can persist across multiple invocations in the same execution environment. That cache needs size and lifecycle bounds; otherwise, memory can grow steadily as the environment is reused. Do not use static fields to store business state that requires durable persistence.

## 12. Setting Timeouts Based on Deadlines and SLOs

A timeout must be long enough for a valid request under expected load, yet not so long that it holds resources when a dependency hangs. When a function hits its timeout, the platform terminates the invocation; do not rely on finally blocks, shutdown hooks, or cleanup actions completing after that point. Changes requiring durability must be persisted before the deadline and must be recoverable if the invocation is stopped.

One approach to setting timeouts:

1. Define the latency SLO or maximum time allowed for the work.
2. Measure p95/p99 under production-like load.
3. Allocate budgets for each step: authentication, database, HTTP dependencies, processing, and writing results.
4. Set each dependency's timeout lower than the remaining deadline.
5. Set the function timeout high enough for valid processing and required cleanup.
6. Ensure callers or gateways have compatible deadlines.
7. Check trigger retries and visibility timeouts.

Do not set a timeout simply as p99 plus an arbitrary number. Consider the SLO, variance, caller limits, and the impact of hung requests. If p99 is high due to an unstable dependency, raising the timeout may cause the system to hold requests longer without fixing the root cause.

### 12.1. Layered Timeouts

Example of an HTTP-triggered function calling a service and a database:

~~~text
Client deadline:            8.0 s
API gateway integration:    7.0 s
Function timeout:           6.0 s
External API timeout:       2.0 s
Database statement timeout: 1.5 s
Cleanup / response budget:  remaining time budget
~~~

These numbers only illustrate deadline ordering. In practice, account for gateway time, DNS, TLS, retries, connection acquisition, and serialization. Inner-layer timeouts should be shorter than the outer layer's remaining deadline so the application can return a controlled error.

If the gateway times out before the function, the client may receive an error while the function continues running. Client retries can trigger a second invocation. Thus, timeouts must be designed alongside idempotency.

### 12.2. Dependency Timeouts and Retries

Set connect timeout, read timeout, and overall request timeout separately when libraries support them. Do not retry a request whose deadline has already expired. Use exponential backoff with jitter for transient errors and cap total retry time.

Do not retry non-recoverable errors such as validation failures or AccessDenied. Retries must be based on error classification and operation semantics.

## 13. Timeouts in Lambda and Triggers

Each trigger has its own limits:

- HTTP clients/gateways have response wait timeouts.
- Lambda functions have invocation timeouts.
- SQS has visibility timeouts.
- Streams have checkpoints, batch windows, and retry mechanisms.
- Async invocations have retry policies and event age limits.
- Schedulers can trigger overlapping runs if the previous run has not finished.

With AWS Lambda, the maximum function timeout is 15 minutes. If a task requires longer, split it into steps, enqueue work, or use workflow orchestration rather than trying to stretch a single invocation.

For SQS event source mappings, the visibility timeout must be long enough for the function to process and for the platform to retry safely. AWS recommends setting the visibility timeout to at least six times the function timeout, plus the maximum batching window if batching is enabled. Verify exact trigger guidelines and real configuration before deploying.

Do not assume HTTP, SQS, Kinesis, and asynchronous invocations share the same retry semantics. Each source must be configured and tested independently.

## 14. Using Remaining Time to Stop Work Gracefully

An AWS Lambda Java handler can read remaining time from Context. The application can avoid starting a new operation when insufficient budget remains.

~~~java
import com.amazonaws.services.lambda.runtime.Context;

public final class DeadlineGuard {
    private static final long SAFETY_MARGIN_MS = 300;

    private DeadlineGuard() {
    }

    public static boolean canStart(Context context, long requiredMs) {
        long remaining = context.getRemainingTimeInMillis();
        return remaining > requiredMs + SAFETY_MARGIN_MS;
    }
}
~~~

This is a simple guard and does not replace HTTP client or database timeouts. If insufficient time remains, the application must choose a safe behavior: return an error so the source retries, save a checkpoint, or offload remaining work to a queue. Do not ACK a message before results are durably saved.

On other platforms, use the runtime's corresponding deadline/cancellation API. Do not assume AWS Context exists in every Java FaaS environment.

## 15. Concurrency, Throughput, and Timeouts

Concurrency is the number of invocations running at the same point in time. A rule-of-thumb estimate for steady workloads:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

If the system receives 100 requests per second and each takes 0.5 seconds on average, average concurrency is roughly 50. If duration rises to 2 seconds, average concurrency can rise to roughly 200 at the same arrival rate.

Long timeouts do not directly raise concurrency when requests always finish quickly, but when a dependency hangs, invocations stay alive longer and occupy slots longer. That can trigger throttling or grow queue backlogs.

Monitor:

- ConcurrentExecutions and Throttles.
- Reserved concurrency and account quotas.
- Queue age or iterator age.
- Duration percentiles.
- Downstream connection counts and latency.
- Requests waiting in client pools.

Do not increase concurrency without checking downstream database or API capacity. A function can scale faster than the systems it calls, causing connection storms and cascading failures.

## 16. Optimizing by Workload Type

| Workload Type | Key Symptoms | Optimization Direction |
|---|---|---|
| CPU-bound | High CPU, computation takes most of the time | Test higher memory tiers, profile algorithms |
| Memory-bound | Max Memory Used near limit, GC/OOM | Increase memory, reduce working set and allocations |
| I/O-bound | Low CPU, lots of waiting | Optimize network, connection pools, and downstream timeouts |
| Batch | Low throughput, large payloads | Tune batch size, memory, and parallelism |
| Latency-sensitive HTTP | High p95/p99, noticeable cold starts | Reduce init, optimize dependencies, consider provisioned capacity |
| Event-driven queue | Rising queue age and retries | Tune concurrency, batching, visibility timeout, and idempotency |

There is no single optimal configuration for all workload types. An image-processing function and a database-calling function may require vastly different memory/CPU/timeouts even on the same Java runtime.

## 17. Example Lambda Configuration Using SAM

A function can declare memory and timeout in a template:

~~~yaml
Resources:
  ResizeImageFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java17
      Handler: com.example.ResizeImageHandler::handleRequest
      CodeUri: target/function.zip
      MemorySize: 2048
      Timeout: 20
~~~

The values 2048 MB and 20 seconds are illustrative examples only. Do not copy them into production without measuring. The chosen Java runtime must still be supported by the platform at deployment time; templates should pin other settings such as architecture, role, environment, tracing, and triggers according to actual needs.

When changing MemorySize or Timeout, create a traceable configuration version, run benchmarks, and compare before/after. Avoid changing multiple parameters simultaneously because it becomes hard to tell which change produced the outcome.

## 18. Java-Specific: Reducing Init Time and Per-Invocation Cost

Several practices can help Java functions:

- Create AWS SDK clients and HTTP clients once per execution environment.
- Avoid unnecessary classpath scanning or reflection at startup.
- Reduce dependency count and framework auto-configuration.
- Load only needed configuration.
- Use bounded connection pools and reuse them safely.
- Measure cold starts separately from warm invocations.
- Inspect GC and JIT behavior with realistic workloads.
- Consider SnapStart or provisioned concurrency if supported by the platform and required by latency targets.

Reusing clients does not mean keeping request data or user security contexts in static fields. Shared objects must be thread-safe and contain no invocation state that could leak to the next request.

SnapStart, provisioned concurrency, and native images can alter startup behavior, but come with trade-offs in snapshotting, library compatibility, memory, and cost. Evaluate them after establishing a baseline; do not enable them just to reduce cold starts without first measuring the cold invocation rate.

## 19. Iterative Optimization Process

An optimization cycle can proceed in this order:

1. **Set goals:** for example, p95 under 700 ms, error rate below threshold, and cost per successful order within budget.
2. **Measure baseline:** use representative payloads and concurrency, separating cold and warm runs.
3. **Identify bottleneck:** CPU, heap/native memory, I/O, locks, GC, or downstream.
4. **Change one factor:** memory, CPU, code, connection pool, or timeout.
5. **Repeat benchmarks:** collect the distribution and verify stability.
6. **Compare cost and latency:** use GB-seconds, billed duration, and cost per success.
7. **Test load and failures:** timeouts, retries, duplicate events, slow downstream services.
8. **Canary the new configuration:** monitor production metrics and roll back if guardrails degrade.
9. **Document the decision:** configuration, commit, measurements, rationale, and review date.

Do not treat a single faster run as proof. Results can be affected by caching, JIT, noisy neighbors, network variance, or downstream load. Run multiple iterations under identical conditions and examine percentiles.

## 20. Common Mistakes

**Increasing timeout to hide a bottleneck:** Requests remain slow and hold concurrency longer. Profile and fix the root cause first.

**Increasing memory without benchmarking:** May raise cost without lowering duration. Test multiple tiers and compare GB-seconds.

**Looking only at average duration:** Tail latency can still be very high. Track p95/p99.

**Looking only at heap:** Native memory, thread stacks, and direct buffers also consume quota. Reconcile JVM metrics with Max Memory Used.

**Setting function timeout higher than all outer timeouts:** Callers may give up while the function keeps running. Design layered deadlines and idempotency.

**Excluding retries from cost:** A failing task can generate multiple invocations and downstream calls. Calculate cost per successful outcome.

**Increasing concurrency without checking downstream:** Databases or APIs can overload. Set limits and measure connections/latency.

**Setting connection pools too large:** Each environment opens many connections, causing connection storms. Calculate total connections from concurrency and environment count.

**Benchmarking only warm invocations:** Misses cold starts and init overhead. Measure cold and warm separately.

**Using one small payload for all tests:** Fails to expose memory pressure with large payloads. Use a realistic input distribution.

**Optimizing one function at the expense of the whole workflow:** Duration drops but queue retries or database load spike. Monitor end-to-end metrics.

## 21. Pre-Release Performance Configuration Checklist

- [ ] Clear baseline and latency/throughput SLOs exist.
- [ ] p50, p95, p99, and error rates have been measured.
- [ ] Cold starts are separated from warm execution.
- [ ] Max Memory Used and JVM heap/non-heap metrics have been inspected.
- [ ] Workload is classified as CPU-bound, memory-bound, or I/O-bound.
- [ ] Memory tier was selected via benchmarks with consistent payloads and concurrency.
- [ ] Cost was compared using actual billing duration/GB-seconds.
- [ ] Function timeout aligns with caller and trigger deadlines.
- [ ] HTTP/database client timeouts are shorter than remaining deadlines.
- [ ] Retries, visibility timeouts, DLQs, and idempotency have been tested.
- [ ] Concurrency aligns with quotas and downstream capacity.
- [ ] Connection pools, thread pools, and batch sizes are bounded.
- [ ] Guardrails exist for p95/p99, errors, throttles, queue age, and cost.
- [ ] The new configuration has been canaried with a rollback plan.
- [ ] Configuration and benchmark results are stored alongside the release record.

## Conclusion

Tuning memory, CPU, and timeouts is a measurement exercise. On AWS Lambda, memory also determines allocated CPU, so raising memory can reduce duration for CPU-bound workloads and sometimes lower cost per invocation. For I/O-bound workloads, focus on networking, connection pools, and dependency latency. Java must be observed across both heap and non-heap regions because function quotas cover multiple memory types beyond the heap.

Timeouts must reflect SLOs, caller deadlines, trigger limits, and retry behavior. Too short a timeout causes tasks to fail; too long a timeout can hold concurrency and grow backlogs when dependencies fail. Benchmarking with representative payloads and concurrency, tracking percentiles, Max Memory Used, GB-seconds, and cost per successful unit of work will support evidence-based, verifiable configuration choices.
