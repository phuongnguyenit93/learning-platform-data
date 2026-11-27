# Estimating concurrency from traffic and processing time

Concurrency is the number of requests, invocations, or units of work being processed at the same time. In serverless, the platform usually provisions additional execution environments or instances automatically as load increases, but concurrency is still bounded by quotas, function configuration, event sources, databases, and dependent services. If estimated too low, requests get throttled, queue backlogs grow, or latency exceeds SLOs. If the limit is set too high, the system can unleash a massive surge of load onto downstream databases and APIs.

A foundational estimation method is **Little’s Law**: the average number of work items in the system equals the arrival rate of work multiplied by the average time a work item spends in the system. For HTTP APIs, the formula is typically applied as concurrency approximately equal to request rate multiplied by processing time. For batch consumers, you need to convert the event rate into an invocation rate based on batch size before calculating concurrency.

This lesson covers how to measure traffic, processing time, peak traffic, and headroom; calculate concurrency for HTTP and event-driven functions; cross-check against platform limits and downstream capacity; and then verify through load testing and monitoring.

## 1. What is concurrency?

Concurrency is the number of work items being executed simultaneously. Depending on the workload type, the unit can be:

- An HTTP request currently being processed.
- A running Lambda invocation.
- Concurrent requests on a Cloud Run instance.
- A batch message being processed by a worker.
- A stream batch being processed on a shard.
- A running job in a workflow.

Concurrency differs from request rate and throughput:

| Quantity | Meaning | Example units |
|---|---|---|
| Arrival rate | Number of requests/events arriving per unit of time | requests/second (RPS), events/second |
| Throughput | Number of work items completed per unit of time | completed requests/second |
| Latency/service time | Time a work item is processed or remains in the system | ms, seconds |
| Concurrency | Number of work items being processed at the same time | requests, invocations, workers |
| Queue depth | Number of work items waiting to be processed | messages, jobs |

An API might receive 200 requests/second yet have only 40 requests running concurrently if each request completes in 200 ms on average. Conversely, 50 requests/second can require 250 concurrency if each request takes 5 seconds on average.

## 2. Little’s Law and the basic formula

Little’s Law describes a stable system:

```text
L = λ × W
```

Where:

- **L:** average number of work items in the system.
- **λ (lambda):** rate at which work enters/completes in steady state.
- **W:** average time a work item spends in the system.

For requests currently being processed:

```text
Average concurrency ≈ arrival rate × average service time
```

Example:

- An API receives an average of 100 requests/second.
- The average processing time is 0.3 seconds.

```text
Concurrency ≈ 100 × 0.3 = 30
```

That means roughly 30 requests are running concurrently in steady state.

### Always use consistent units

If the arrival rate is in requests/second, the time must be converted to seconds. For example, 250 ms = 0.25 seconds.

```text
80 requests/second × 250 milliseconds
= 80 × 0.25
= 20 concurrent requests
```

Do not multiply RPS by time in milliseconds and treat the result as concurrency.

### Distinguish service time from end-to-end time

For an HTTP request, the service time to use in the concurrency calculation is the time the request occupies a processing slot in the function/service. It may include time spent waiting on a database or downstream API if the request still holds the slot while waiting.

For a queue, the time spent in the system may include both queue wait time and processing time. When estimating the number of actively executing workers, use the invocation processing time; when estimating the total number of messages residing across both the queue and workers, use the time from receipt to completion.

Little’s Law applies to a stable system. If the arrival rate exceeds processing capacity for a sustained period, the backlog will grow and the steady-state assumption no longer holds.

## 3. Estimating concurrency for HTTP functions

For an HTTP function that processes one request per invocation, the basic formula is:

```text
Required concurrency ≈ peak RPS × average request duration
```

Example:

- Peak traffic: 180 RPS.
- Average duration: 400 ms = 0.4 seconds.

```text
Required concurrency ≈ 180 × 0.4 = 72
```

The system needs about 72 concurrent requests during peak periods under this assumption. This is an average load estimate at peak, not the final safety limit.

If a function takes 1.5 seconds to process a request and receives 200 RPS:

```text
200 × 1.5 = 300 concurrent requests
```

Increased latency due to a slow database can drive concurrency up even when RPS stays unchanged. This is why a downstream incident can trigger a cascading failure: requests hold slots longer, the number of in-flight requests rises, instances scale out, and the database takes on even heavier load.

## 4. Using peak traffic and headroom

You should not size solely based on daily average traffic. You need to measure and estimate:

- Peak sustained RPS over a sufficiently long window.
- Burst RPS during short traffic spikes.
- Average processing time and latency distribution.
- Seasonality, campaigns, batch schedules, and peak hours.
- Projected user and tenant growth.
- Retries or traffic replay after an incident.

You can add headroom to absorb variability:

```text
Target concurrency =
  peak RPS × representative duration × headroom factor
```

For example, a headroom factor of 1.5 means adding a 50% buffer. This factor is an operational choice, not a mandatory constant. Workloads with heavy bursts or incomplete measurement data may require a different headroom factor.

### Peak calculation example

Suppose:

- Normal traffic: 120 RPS.
- Normal average duration: 250 ms.
- Peak traffic: 300 RPS.
- Duration at peak: 800 ms due to a slower downstream.
- Headroom: 1.5.

Normal:

```text
120 × 0.25 = 30 concurrent requests
```

At peak:

```text
300 × 0.8 = 240 concurrent requests
```

With headroom:

```text
240 × 1.5 = 360 target concurrent requests
```

This example shows that concurrency rises due to both higher traffic and longer processing times. Simply multiplying peak RPS by the daily average duration will underestimate load.

### How should percentile durations be used?

Little’s Law uses the average time. p95/p99 are useful for inspecting tail latency and building a conservative estimate, but they do not replace the exact formula. Multiplying peak RPS by p95 duration is a heuristic to create a capacity buffer; the result is not a guaranteed concurrency percentile.

Calculate the baseline using average duration, then use load tests and the latency distribution to determine headroom. If latency has a very long tail caused by timeouts, address the root cause rather than merely increasing concurrency.

## 5. Calculating instance count from concurrency

For platforms that allow a single instance to handle multiple concurrent requests, you can estimate the number of instances:

```text
Required instances ≈ ceil(target concurrency / target concurrency per instance)
```

For example, if target concurrency is 360 and Cloud Run instance concurrency is configured to 40:

```text
ceil(360 / 40) = 9 instances
```

This is a concurrency-based estimate. Actual capacity per instance also depends on CPU, memory, the Java thread pool, connection pools, CPU-bound time, and dependencies. Setting an instance concurrency of 40 does not mean it can always handle 40 requests well if the application can only efficiently execute 8 CPU-bound tasks simultaneously.

### With AWS Lambda

A typical Lambda execution environment handles one invocation at a time. Therefore, the number of concurrent invocations is close to the number of busy execution environments. The RPS × duration formula is commonly used to estimate concurrent executions.

For example, 60 invocations/second with an average duration of 2 seconds requires roughly 120 concurrent executions. Check function concurrency, reserved concurrency, account quotas, and trigger limits.

### With Cloud Run

Cloud Run lets you configure maximum concurrency per instance. The platform can send multiple concurrent requests to the same instance. Choose concurrency based on the actual processing capacity of the Java application, rather than just picking the maximum value.

### With other platforms

Azure Functions and other serverless platforms have their own scale controllers, worker/instance concurrency mechanisms, and quotas. Use the formula to estimate load, then map it to the specific settings of the hosting plan and trigger in use.

## 6. Java concurrency: concurrent requests do not equal constantly running CPU threads

A request may spend most of its time waiting on I/O:

- Waiting on a database query.
- Waiting on an HTTP API.
- Waiting on object storage.
- Waiting on a message broker.
- Waiting on a lock or connection pool.

As a result, high concurrency does not necessarily mean CPU is always high. A service can handle many concurrent requests using threads or async I/O, while still being constrained by connection pools and downstream quotas.

Conversely, CPU-bound workloads such as image compression, encryption, computation, or PDF conversion can saturate the CPU at much lower concurrency.

When sizing a Java service, measure separately:

- CPU time per request.
- Wall-clock duration.
- Thread count and runnable threads.
- Active/pending connection pool counts.
- GC pauses and heap usage.
- Async task queue depth.
- Downstream latency.

Do not increase concurrency to solve a CPU-bound bottleneck if doing so only causes more requests to contend for the same CPU and stretches latency further.

## 7. Estimating concurrency for batch consumers

With an event source mapping or queue consumer, a single invocation can process multiple messages in a batch. Therefore, do not multiply the event rate by the duration of a single record if the handler processes in batches.

Let:

- (lambda_e): event arrival rate (events/second).
- (B): average number of events in a batch.
- (T_b): time to process one batch (seconds).

When batches are full and steady:

```text
Invocation rate ≈ event rate / average batch size
Concurrency ≈ invocation rate × batch duration
```

Or:

```text
Concurrency ≈ (event rate / batch size) × batch duration
```

Example:

- 1,000 events/second.
- Average batch size of 100.
- Batch duration of 2 seconds.

```text
Invocation rate ≈ 1,000 / 100 = 10 invocations/second
Concurrency ≈ 10 × 2 = 20
```

If actual batches average only 60 records due to sparse traffic or a short batching window:

```text
Invocation rate ≈ 1,000 / 60 = 16.7 invocations/second
Concurrency ≈ 16.7 × 2 ≈ 34
```

The configured batch size is a maximum; the actual batch size may be lower due to batching window timeouts, payload limits, shard boundaries, or uneven traffic.

### Throughput per invocation

You can estimate throughput:

```text
Batch throughput ≈ average batch size / batch duration
```

If each batch contains 100 records and takes 2 seconds, one invocation processes about 50 events/second. With 20 invocations running concurrently, total theoretical throughput is roughly 1,000 events/second, assuming no other bottlenecks and full batches.

Measure actual throughput by completed records, not just ingested records. Retries and partial batch failures can lower useful throughput.

## 8. Concurrency by event source type

Different event sources have different scaling limits. The load calculation formula is a starting point; the event source itself may cap parallel invocations.

| Source | Factors affecting concurrency |
|---|---|
| SQS Standard | Number of available messages, number of pollers, batch size, maximum concurrency, and function limits |
| SQS FIFO | Number of message groups that can be processed in parallel, batching, and mapping limits |
| Kinesis Data Streams | Number of shards, parallelization factor, batching, and ordering per partition key |
| DynamoDB Streams | Number of shards, parallelization factor, batching, and ordering per item |
| Pub/Sub | Number of subscribers/instances, flow control, ack deadline, and batch settings |
| EventBridge | Target invocation rules, and target/service quotas and throttling |
| Scheduled event | Number of overlapping schedules, job duration, and concurrency limits |

### SQS Standard

A standard queue can scale across many pollers and consumer invocations. The event source mapping's maximum concurrency can be used to cap concurrent invocations from the mapping. Coordinate this limit with the function's reserved concurrency.

If a queue builds a large backlog, concurrency can ramp up rapidly. Verify downstream database and API capacity before letting consumers scale to maximum.

### SQS FIFO

FIFO preserves ordering within a message group. Messages belonging to the same group cannot be processed concurrently at will; the number of active message groups can limit useful concurrency. Increasing concurrency when there is only one message group will not produce linear throughput.

### Kinesis and DynamoDB Streams

Concurrency is influenced by shard count and parallelization factor. With a parallelization factor of 1, the mapping typically processes one batch at a time per shard. Increasing the factor can increase concurrent batches within service limits, while still preserving ordering per partition key/item and ensuring downstream services can handle the load.

Do not multiply shard count by batch size to infer invocation concurrency. Batch size is the number of records per invocation; shard count/parallelization determines how many batches can run in parallel.

## 9. Platform concurrency limits

After calculating target concurrency, cross-check the layers of limits:

1. **Account/service quota:** total concurrency or instances allowed in the account/project/region.
2. **Function reserved/max concurrency:** dedicated limit for the function or workload.
3. **Provisioned/warm capacity:** pre-prepared execution environments/instances to reduce cold starts; not equivalent to the total concurrency limit.
4. **Trigger limit:** number of pollers, shards, message groups, or event source maximum concurrency.
5. **Instance concurrency:** number of requests a single instance receives simultaneously.
6. **Downstream capacity:** databases, APIs, caches, and connection pools.
7. **Network capacity:** NAT, egress, connection tracking, or socket limits.

If target concurrency is 360 but the function is only allowed 200 concurrent invocations, excess load may be throttled or queued depending on the platform and trigger. Decide whether to raise quotas, shave peaks, queue/buffer, or enforce admission limits.

### Reserved concurrency and provisioned concurrency

On AWS Lambda:

- **Reserved concurrency** dedicates a slice of concurrency to a function and sets an upper limit for that function.
- **Provisioned concurrency** pre-initializes execution environments to reduce cold starts for a specified amount of invocations.

Provisioned concurrency does not automatically allow a function to exceed the account quota or reserved concurrency. If traffic exceeds provisioned capacity, Lambda may need to scale additional execution environments and cold starts may occur subject to configuration/quotas.

On Cloud Run, minimum instances keep instances warm; maximum instances cap scale-out; the concurrency setting defines the maximum requests per instance. These three settings solve different problems.

## 10. Databases often hit limits before functions do

Serverless can scale invocations very quickly, whereas databases typically have limits on connections, CPU, IOPS, or transaction throughput.

Example:

- Maximum instances: 20.
- Max connection pool per instance: 10.
- Total potential connections: 20 × 10 = 200.

If the database can only sustain 80 connections for this application, this configuration can exhaust connections even though the function is scaling appropriately for traffic.

```text
Potential database connections
≈ active instances × pool max per instance
```

Remember to account for connections from admin tools, migrations, other workers, and other services. Size the pool according to the total budget, use an appropriate connection proxy/pooling mechanism, and cap max instances if needed.

### A request does not necessarily hold a connection for its entire lifetime

Connection pools usually hold a connection only while executing queries. However, if each request keeps a transaction open for a long time or holds a connection while waiting on an external API, the number of connections required can climb sharply.

Do not hold a transaction open while calling a payment provider or performing long-running tasks unless necessary. Keeping transactions short reduces lock duration and connection occupancy.

## 11. Fan-out amplifies downstream concurrency

A single request can invoke multiple services. If each request makes 3 concurrent calls to inventory, pricing, and customer services, downstream services may receive more requests than the API's own concurrency.

Example:

- API concurrency: 200.
- Each request makes 3 parallel downstream calls.
- Total downstream in-flight calls is approximately 600 if all are active simultaneously.

```text
Downstream in-flight concurrency
≈ incoming request concurrency × concurrent calls per request
```

If calls are made sequentially, concurrent in-flight calls may be lower, but the total request rate to the dependency still increases by the number of calls per operation.

Identify the fan-out factor, retry factor, and timeouts. Retries across multiple layers can multiply request volume. For example, an API retrying a worker, the worker retrying a provider, and the provider client retrying can cause massive amplification when a dependency slows down.

## 12. Headroom, utilization, and safety limits

Target concurrency should not sit right at maximum capacity. When a system runs near 100% capacity, queues and latency tend to spike rapidly due to processing time variability.

One way to manage this is to set a target utilization for critical resources:

```text
Required capacity ≈ expected load / target utilization
```

For example, if expected CPU load requires 6 vCPUs at 100%, and you want to maintain a 70% target utilization:

```text
Required CPU capacity ≈ 6 / 0.70 ≈ 8.6 vCPU
```

This is a capacity estimation method for CPU, not a replacement for Little’s Law. For concurrency, use arrival rate × duration plus headroom; for CPU, use throughput benchmarks and target utilization.

Headroom needs to balance:

- Sudden traffic surges.
- Cold starts and scale-out time.
- Request duration variance.
- Retries and post-incident replays.
- An instance or availability zone becoming unavailable.
- Downstream quotas and scaling capabilities.

## 13. Backpressure and admission control

If the arrival rate exceeds processing capacity, raising concurrency is not always the right answer. The system must throttle or regulate incoming load to avoid crashing dependencies.

Measures include:

- Placing work into a durable queue instead of processing synchronously.
- Capping consumer maximum concurrency.
- Applying per-client or per-tenant rate limits.
- Returning 429/503 with an appropriate Retry-After header when unable to accept more work.
- Using bounded queues and rejecting early when full.
- Limiting concurrent downstream calls with semaphores/bulkheads.
- Using circuit breakers to stop calling failing dependencies.
- Isolating interactive and batch workloads to prevent resource contention.
- Setting end-to-end deadlines and per-hop timeouts.

Backpressure protects the system by slowing down or rejecting load when necessary. If clients retry immediately without backoff/jitter, backpressure can turn into a retry storm.

### Queues are buffers, not infinite capacity

Queues absorb short bursts, but if the long-term average arrival rate exceeds the average processing rate, the backlog will still grow. Monitor queue age, depth, retention, and time to drain the backlog.

### Estimating maximum throughput and drain time

If you know the concurrency cap and a representative processing time, you can estimate theoretical maximum throughput:

~~~text
Theoretical throughput ≈ concurrency cap / average service time
~~~

For example, a cap of 200 concurrent requests and an average service time of 0.8 seconds yields a theoretical throughput of about 250 requests/second. This is a simplified model upper bound; CPU, downstream dependencies, quotas, and latency variance usually make sustainable throughput lower. Use benchmarks to find sustainable throughput, then set admission limits below the saturation point.

For a queue, if the current backlog is Q, processing capacity is μ events/second, and the ongoing arrival rate is λ events/second, the approximate drain time when μ > λ is:

~~~text
Drain time ≈ Q / (μ - λ)
~~~

For example, with a backlog of 120,000 events, a consumer capable of processing 1,500 events/second, and a producer still sending 1,000 events/second:

~~~text
Drain time ≈ 120,000 / (1,500 - 1,000) = 240 seconds
~~~

If μ ≤ λ, the backlog will not shrink while traffic keeps arriving. In that case, you need to increase processing capacity, reduce the arrival rate, pause producers, or apply admission control. The drain formula is only an estimate when throughput is relatively stable and retention, partition, or dependency limits do not change.

## 14. Cold starts and scale-out speed

When traffic rises, the platform needs to spin up new execution environments or instances. The Java runtime may require time for JVM startup, class loading, framework initialization, dependency injection, and connection setup.

The concurrency target must account for whether the platform can scale fast enough. If a burst jumps from 20 to 500 requests in a few seconds, the formula tells you the capacity needed, but it does not guarantee that capacity appears instantaneously.

Measures:

- Provisioned concurrency or minimum instances for latency-sensitive workloads.
- Optimizing Java startup time and dependency graphs.
- Setting reasonable min/max instances.
- Using queues to absorb bursts for async workloads.
- Limiting admission to prevent overload while scaling.
- Tracking cold starts and time-to-scale during load tests.

Do not enable provisioned capacity for every function by default. Compare the cost of keeping instances warm against the value of latency reduction and SLO requirements.

## 15. Java example for preliminary concurrency estimation

You can write a small helper to avoid unit mistakes and make headroom explicit. This is only an initial calculation; input metrics should come from production telemetry or load tests.

~~~java
public record ConcurrencyEstimate(
        double peakRequestsPerSecond,
        double averageDurationMillis,
        double headroomFactor) {

    public ConcurrencyEstimate {
        if (!Double.isFinite(peakRequestsPerSecond)
                || !Double.isFinite(averageDurationMillis)
                || !Double.isFinite(headroomFactor)
                || peakRequestsPerSecond <= 0
                || averageDurationMillis <= 0
                || headroomFactor < 1.0) {
            throw new IllegalArgumentException(
                    "Invalid concurrency estimate inputs");
        }
    }

    public long requiredConcurrency() {
        double durationSeconds = averageDurationMillis / 1_000.0;
        double rawConcurrency =
                peakRequestsPerSecond * durationSeconds;
        return (long) Math.ceil(rawConcurrency * headroomFactor);
    }

    public static void main(String[] args) {
        var estimate = new ConcurrencyEstimate(
                300,   // peak RPS
                800,   // average duration at peak, milliseconds
                1.5);  // 50% headroom

        System.out.println(
                "Target concurrency = "
                        + estimate.requiredConcurrency());
    }
}
~~~

The example outputs 360. The helper does not account for quotas, database capacity, batch source limits, or cold starts; those aspects must be evaluated separately.

## 16. Load testing to verify sizing

Formulas give a baseline. Load testing confirms how the application, runtime, and dependencies behave under real load.

A test plan should include:

| Test type | Purpose |
|---|---|
| Baseline | Measure latency and throughput at normal load |
| Ramp-up | Gradually increase RPS to identify where scaling begins |
| Peak sustained | Hold peak traffic long enough to verify steady state |
| Spike | Rapidly increase load to observe scale-out and throttling |
| Soak | Run over a long duration to detect leaks, pool exhaustion, and memory growth |
| Cold-start test | Trigger new instances and measure the first request |
| Dependency degradation | Slow down databases/APIs in a test environment to observe how concurrency rises |
| Recovery/replay | Inject a backlog or retries to determine drain capability |

Measure at least:

- Actual arrival rate and completed throughput.
- Active concurrency per function/instance.
- Duration p50/p95/p99.
- Queue depth and age.
- Throttles, timeouts, retries, and error rate.
- CPU, memory, GC, and thread pools.
- Active/pending database connections.
- Downstream in-flight requests and latency.
- Cold start count and scale-out delay.

Use workloads with payload distributions and dependencies similar to production. A test that only calls an empty handler does not reflect concurrency when the function accesses databases and external APIs.

### Open-loop vs. closed-loop load testing

A closed-loop client waits for a response before sending the next request. When the server slows down, the client automatically slows its sending rate, which can mask the system's inability to handle overload.

An open-loop test dispatches requests at a predetermined arrival rate, making it suitable for verifying what peak RPS the system can sustain. Cap the load and run in authorized environments so production is not impacted.

## 17. Post-deployment monitoring

Track both concurrency and signals indicating the system is approaching its limits.

| Metric | Meaning |
|---|---|
| Concurrent executions/requests | Number of invocations or requests currently running |
| Throttles/rejected requests | Load rejected due to limits |
| Duration p50/p95/p99 | Processing time and tail latency |
| Instance count | Current scale-out level |
| Pending requests | Requests waiting for an instance or capacity |
| Queue depth/age | Backlog size and wait time |
| Iterator age | Stream reading lag |
| Retry/DLQ count | Processing errors and quarantined work items |
| DB active/pending connections | Connection pool pressure |
| Downstream latency/error | Dependency health |
| CPU/memory/GC | Java runtime resource limits |
| Cold start/startup latency | Cost of initializing new instances |

Set alerts on combined signals. For example, concurrency near max alongside rising throttles indicates insufficient capacity; rising concurrency alongside DB connection wait indicates a downstream bottleneck. Increasing queue age while consumer concurrency is already maxed out indicates a need to raise processing capacity or reduce the arrival rate.

Do not alert only when concurrency hits 100%. If latency and error rates are already climbing at 70%, investigate before hitting the limit.

## 18. Common sizing mistakes

- **Using daily average RPS:** ignores peaks and bursts; calculate based on sustained peaks and test spikes.
- **Forgetting to convert milliseconds to seconds:** throws off the result by 1,000x.
- **Using p99 as an average without explanation:** produces hard-to-interpret estimates; use the average for Little’s Law and percentiles to assess tail behavior and headroom.
- **Only calculating function concurrency:** ignores downstream databases, APIs, and queues.
- **Assuming higher max concurrency is always better:** can exhaust dependency connections or quotas.
- **Using configured batch size instead of actual batch size:** underestimates the invocation rate.
- **Ignoring shards or message groups:** event sources cannot scale beyond source-level parallelism limits.
- **Omitting retry amplification:** dependency incidents multiply outbound request volume many times over.
- **Treating provisioned concurrency as max concurrency:** these serve two different purposes.
- **Failing to measure cold starts and scale-out delay:** bursts can breach SLOs before new instances are ready.
- **Lacking backpressure:** backlogs and latency grow unchecked.
- **Testing only empty functions:** misses database pool and downstream bottlenecks.
- **Not monitoring queue age:** backlogs can grow even while invocations succeed.
- **Leaving no headroom:** the system runs right against its limits and is easily disrupted by minor fluctuations.

## 19. Concurrency estimation workflow

When sizing a Java serverless workload, follow these steps in order:

1. Define the unit of work: HTTP request, invocation, batch, or business operation.
2. Measure arrival rate per second and the peak/burst distribution.
3. Measure average processing time under representative load; track p95/p99.
4. Use Little’s Law to calculate the concurrency baseline.
5. For batches, convert event rate to invocation rate using actual batch size, then multiply by batch duration.
6. Add headroom based on variance and scale-out speed.
7. Cross-check account quotas, function limits, trigger limits, and instance concurrency.
8. Calculate downstream concurrency, database connections, and fan-out.
9. Set max concurrency, rate limits, and backpressure according to the dependency budget.
10. Choose min/provisioned capacity if cold starts affect SLOs.
11. Load test ramp, peak, spike, soak, and dependency degradation scenarios.
12. Monitor concurrency, throttles, latency, queue age, and downstream saturation after deployment.
13. Adjust using production data instead of keeping initial assumptions unchanged.

## 20. Key takeaways

Little’s Law lets you estimate average concurrency by multiplying arrival rate by the time a work item spends in the system. For HTTP functions, use peak RPS and request duration; for batch consumers, calculate invocation rate from event rate and actual batch size, then multiply by batch duration.

The result is only a baseline. Add headroom, verify function and event source limits, check downstream database/API capacity, and validate with load tests. Too little concurrency causes throttles and backlogs; too much concurrency can overload dependencies or inflate costs.

In Java serverless, measure wall-clock duration alongside CPU, threads, connection pools, and cold starts. Configure limits and backpressure based on the capacity of the entire path, not just the function's ability to scale. After deployment, use concurrency, latency, queue age, and downstream saturation metrics to refine sizing against real traffic.
