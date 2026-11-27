# Limiting consumer concurrency and queue processing speed

A queue can receive messages faster than consumers can process them. If consumers open too many invocations, downstream databases or APIs can overload. If consumers process too little, backlogs and message age climb until work breaches SLAs. Therefore, the system must regulate both the number of items running concurrently and the rate at which new work is pulled.

Two concepts must be kept distinct:

- **Concurrency:** the number of messages or tasks being processed at the same time.
- **Processing rate:** the number of messages completed per unit of time, typically messages/second.

Concurrency limits protect resources by bounding in-flight work. Rate limits cap how fast operations start or call a dependency over a time interval. A consumer can have low concurrency yet still generate a high rate if each message completes very quickly; conversely, high concurrency with slow messages can yield low throughput.

This lesson covers how to set limits for Java serverless consumers, coordinate autoscaling with queues, apply backpressure and rate limiting, and use common configuration patterns on SQS, Pub/Sub, and Kafka.

## 1. Why throttle consumers?

Suppose a producer sends 1,000 messages/second while the database can only handle 200 writes/second. If consumers scale out unboundedly, the queue may drain quickly, yet the database bottlenecks, connection pools exhaust, and other requests fail too.

If concurrency is set too low, the database stays protected, but queue backlogs grow, message age exceeds SLAs, and the system cannot recover from bursts.

Load control must balance three objectives:

1. Keep downstream dependencies within safe limits.
2. Achieve enough throughput to handle arrival rates and backlogs.
3. Keep latency/message age within SLOs.

~~~mermaid
flowchart TD
    P["Producer"] --> Q["Queue"]
    Q --> C["Consumer scaling"]
    C --> L["Concurrency / rate controls"]
    L --> W["Java worker"]
    W --> D["Database / API"]
    D --> W
    W --> A["Ack / delete"]
    A --> Q
    L -. "Backpressure on overload" .-> C
~~~

There is no single right concurrency value for every system. Measure processing time, dependency capacity, batch sizes, platform limits, and SLOs before choosing.

## 2. How does concurrency differ from processing rate?

Concurrency is the number of tasks running simultaneously. Processing rate is the number of tasks completed per second. Both quantities are linked through processing duration.

If a consumer takes an average of \(d\) seconds per message and maintains \(c\) concurrent messages, approximate ideal throughput is:

\[
\mu \approx \frac{c}{d}
\]

If processing in batches of \(b\) messages each, ideal throughput is approximately:

\[
\mu \approx \frac{c \times b}{d_{\text{batch}}}
\]

These are estimates only. Real throughput is also bounded by CPU, memory, thread pools, connection pools, brokers, networks, and downstream quotas.

Example:

| Concurrency | Average processing time | Ideal throughput |
|---:|---:|---:|
| 10 | 0.5 seconds | 20 messages/second |
| 20 | 0.5 seconds | 40 messages/second |
| 20 | 0.2 seconds | 100 messages/second |
| 50 | 1 second | 50 messages/second |

Raising concurrency does not guarantee linear throughput scaling. If a dependency starts throttling, processing time increases and throughput can plateau or drop.

### 2.1. Little's Law and in-flight work items

Little's Law describes the relationship between the average number of items in the system \(L\), arrival rate \(\lambda\), and average residence time \(W\):

\[
L = \lambda \times W
\]

For example, a system receives 100 messages/second and each message takes 0.4 seconds on average; the average number of messages in flight needs to be roughly:

\[
L = 100 \times 0.4 = 40
\]

To sustain 100 messages/second throughput at 0.4 seconds per message, you need roughly 40 concurrent messages of processing capacity, assuming no other bottlenecks.

This is a steady-state average relationship, not a max concurrency setting to configure directly. Add controlled headroom and measure tail latency, since p95/p99 are typically higher than the average duration.

## 3. Determining limits from dependencies

Consumers frequently call multiple dependencies. Each dependency has its own capacity and quotas:

- Databases have limits on connections, transactions, and write throughput.
- Payment providers have requests-per-second quotas.
- Email/SMS providers have maximum sending rates.
- Internal APIs have concurrency or rate limits.
- Object storage has request rate and network throughput limits.
- Message brokers have pull, ack, and connection limits.

Identify which dependency is the bottleneck before setting consumer concurrency.

For example, a Java worker might handle 40 concurrent messages, each calling 2 APIs and opening 1 database transaction. If the database only supports 60 concurrent transactions, the safe worker limit must also account for other workloads sharing that database.

A simple capacity planning formula:

\[
C_{\text{consumer}} \leq
\min(C_{\text{compute}}, C_{\text{database}}, C_{\text{API}}, C_{\text{broker}})
\]

All limits must be converted into the same units and scope. For example, database limits are connection counts, API limits are requests/second, and broker limits are messages/second; you cannot take the minimum directly without converting by operations per message.

### 3.1. Allocating concurrency budgets

If multiple consumers hit one database, do not allow each consumer to claim the entire connection capacity.

Suppose a database can dedicate at most 120 connections to serverless workers. Three active consumers must share that budget while reserving connections for APIs and operational tasks.

| Workload | Example connection budget |
|---|---:|
| orders-worker | 40 |
| billing-worker | 30 |
| inventory-worker | 30 |
| Reserve and operational tasks | 20 |
| Total | 120 |

This is an illustrative allocation, not a universal recommendation. Account for instance count, per-instance connection pools, and non-serverless workloads.

If each instance has a max pool of 10 connections and the autoscaler can spin up 20 instances, potential connections reach 200. Simply setting a small pool size per instance can still overflow database limits during scale-out.

## 4. Three layers of load limits

A sound design typically throttles across multiple layers:

| Layer | Controls | Purpose |
|---|---|---|
| Platform/function | Reserved concurrency, max instances, max scale | Bounds total invocations or instances |
| Queue/event source | Polling, flow control, batch size, max concurrency | Bounds how many messages are delivered to consumers |
| Java application | Semaphores, bounded executors, rate limiters, bulkheads | Bounds work and dependency calls inside a process |

Not every system needs all three layers. However, when multiple consumers share a dependency, limiting inside a single process alone is often insufficient because total concurrency grows with instance count.

For example, if each instance permits 10 concurrent messages and the autoscaler spawns 15 instances, total concurrency can reach 150. If the database handles only 60 concurrent operations, reduce per-instance concurrency, cap max instances, or use a distributed rate limiter backed by a shared budget.

## 5. What is backpressure?

Backpressure is a mechanism that slows down or pauses intake of new work when consumers or dependencies lack sufficient capacity.

Without backpressure, consumers can keep pulling messages and dumping them into internal thread pools or in-memory queues. External queues appear to shrink, but the backlog has merely shifted into process heap. When a process restarts or hits OOM, work held in memory can be lost or reprocessed.

Principles:

- Pull only as many messages as the consumer can safely handle within limits.
- Use bounded queues/buffers.
- When downstreams slow down, reduce polling or pause receiving messages.
- Do not spawn unbounded threads or futures per message.
- Ack only after processing completes or work is durably persisted per policy.
- Monitor both broker backlog and in-process in-flight counts.

Backpressure can be applied by reducing polling, pausing partitions, capping outstanding messages, throttling autoscaling, or rejecting new requests with appropriate retryable errors.

### 5.1. Never ack too early

If a consumer acks a message immediately upon submitting it to an internal executor and the process dies before processing finishes, the broker assumes the message succeeded and will not redeliver it. Therefore:

- For synchronous processing, ack after side effects commit.
- For asynchronous processing, persist the message to a durable store/queue before acking.
- Never treat submission to an in-memory executor as durable acceptance.

When using batches, adhere to the event source's partial failure semantics. Do not ack an entire batch when only a subset of messages succeeded unless the event source supports an appropriate mechanism.

## 6. Rate limiting vs. concurrency limiting

A concurrency limiter caps how many tasks run at once. A rate limiter caps how many operations start within a time period.

Example:

- Concurrency cap: max 20 active payment requests.
- Rate limit: max 50 payment requests per second.
- Both: max 20 concurrent requests and 50 requests/second.

An API might handle 50 requests/second yet permit only 5 concurrent requests because each takes a long time. Another API might allow 100 concurrent requests while capping quota at 20 requests/second.

### 6.1. Token bucket

Token bucket is a popular rate-limiting algorithm:

- A bucket holds up to \(B\) tokens.
- Tokens replenish at a rate of \(r\) tokens/second.
- Each request consumes one or more tokens.
- If insufficient tokens exist, the request waits or is rejected.

The bucket permits short bursts up to capacity \(B\), while capping the long-term average rate at \(r\).

For example, a bucket with a capacity of 20 tokens and a refill rate of 10 tokens/second can absorb a burst of 20 requests when full, then sustain roughly 10 requests/second.

A token bucket does not by itself limit concurrent execution time. If requests run long, pair it with a concurrency limiter.

### 6.2. Fixed window, sliding window, and leaky bucket

| Algorithm | How it works | Characteristics |
|---|---|---|
| Fixed window | Counts requests in fixed time intervals | Simple, but prone to boundary bursts across adjacent windows |
| Sliding window | Counts requests in a rolling window | Smoother, but requires tracking history or more complex counters |
| Token bucket | Tokens replenish at a fixed rate | Allows bounded bursts |
| Leaky bucket | Processes requests at a steady rate | Smooths bursts into a uniform output rate |

Choose an algorithm matching dependency quotas and acceptable burst behavior. When multiple instances share a global quota, per-instance in-memory rate limiters are insufficient.

## 7. Limits inside a single Java process

A Java worker can use a `Semaphore` to limit concurrent calls to a dependency. The example below illustrates only a synchronous bulkhead:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class InventoryBulkhead {

    private final Semaphore permits = new Semaphore(8, true);
    private final InventoryClient client;

    public InventoryBulkhead(InventoryClient client) {
        this.client = client;
    }

    public InventoryResult reserve(
            String sku,
            int quantity,
            long waitMillis) throws InterruptedException {

        boolean acquired = permits.tryAcquire(
                waitMillis, TimeUnit.MILLISECONDS);

        if (!acquired) {
            throw new DependencyBusyException(
                    "Inventory concurrency limit reached");
        }

        try {
            return client.reserve(sku, quantity);
        } finally {
            permits.release();
        }
    }
}
~~~

The semaphore caps concurrent calls at 8 within one process. `finally` ensures the permit is released even if the dependency throws an exception.

With async APIs, hold the permit until the future completes—do not release right after creating the future. Even with virtual threads, still limit dependency concurrency; lightweight thread creation does not give external databases or APIs infinite capacity.

In-memory semaphores do not coordinate across instances. With 10 instances at 8 permits each, total concurrent calls can reach 80.

### 7.1. Bounded executor

A thread pool with an unbounded queue can accumulate huge task counts on the heap when producers outpace consumers. Use a bounded queue and an explicit rejection policy.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class WorkerPool {

    public static ThreadPoolExecutor create() {
        return new ThreadPoolExecutor(
                8,
                8,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(100),
                new ThreadPoolExecutor.AbortPolicy()
        );
    }
}
~~~

When all 8 threads and 100 queue slots are full, `AbortPolicy` throws `RejectedExecutionException`. Callers must translate this into a backpressure/retryable outcome appropriate for the queue trigger.

Do not use `DiscardPolicy` for business messages because tasks can be dropped silently without clear ack/retry handling. `CallerRunsPolicy` slows down the submitting thread, but confirm whether that thread is the event-handling thread and whether delaying it violates runtime timeouts.

## 8. Rate limiters in Java applications

You can use a rate-limiting library such as Resilience4j to cap dependency call rates. Illustrative example:

~~~java
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterConfig;

import java.time.Duration;
import java.util.function.Supplier;

public final class PaymentGateway {

    private final RateLimiter rateLimiter;
    private final PaymentClient client;

    public PaymentGateway(PaymentClient client) {
        this.client = client;

        RateLimiterConfig config = RateLimiterConfig.custom()
                .limitForPeriod(20)
                .limitRefreshPeriod(Duration.ofSeconds(1))
                .timeoutDuration(Duration.ofMillis(100))
                .build();

        this.rateLimiter = RateLimiter.of("payment-provider", config);
    }

    public PaymentResult charge(PaymentRequest request) {
        Supplier<PaymentResult> operation =
                RateLimiter.decorateSupplier(
                        rateLimiter,
                        () -> client.charge(request));

        return operation.get();
    }
}
~~~

This configuration limits roughly 20 permits per one-second refresh period for a single limiter instance. It does not guarantee the entire system sends only 20 requests/second if multiple instances run concurrently.

When the limiter denies permission within the timeout, the application must decide whether to return a retryable error, return the message to the queue, or defer processing. Do not sleep for long durations inside a Lambda invocation waiting for quota if the broker can hold the message and redeliver later.

## 9. Global limits across multiple instances

When a dependency's quota is global, instances must coordinate. Several approaches exist:

- Statically divide the quota per instance based on max instance count.
- Use a distributed token bucket in Redis or a store with atomic operations.
- Use an API gateway/service proxy as a shared throttling choke point.
- Use a dedicated queue for the dependency paired with a bounded consumer pool.
- Rely on provider-side quotas/rate limits as a last line of defense.

For example, with a provider quota of 100 requests/second and max 10 instances, splitting 10 requests/second per instance is simple, though wasteful if some instances sit idle. Distributed limiters utilize quota better but add a dependency and latency.

If a distributed limiter becomes unavailable, define a clear fail-open or fail-closed policy. For payments or strict-quota operations, fail-closed protects the provider while allowing backlogs to grow. For metrics or cache warming, fail-open may be preferable.

Do not assume a naive Redis counter automatically behaves like an accurate rate limiter. You need atomic updates, TTLs, clock handling, burst capacity, and limiter fault tolerance.

## 10. Throttling Lambda consumers with SQS

When Lambda reads SQS via an event source mapping, concurrency is governed by multiple settings:

- **Function reserved concurrency:** caps total concurrent invocations of the function, shared across event source mappings and other invokers.
- **Event source mapping maximum concurrency:** caps concurrent invocations permitted from that mapping; for SQS, this applies to standard queue mappings. FIFO queue parallelism depends on active message groups and ordering semantics.
- **Batch size:** maximum messages in a batch.
- **Maximum batching window:** wait duration to gather a batch before invoking.
- **Event source scaling:** the platform automatically scales pollers and invocations based on backlog and settings.
- **FIFO message groups:** bounds parallelism by active message groups and ordering semantics.

Do not confuse reserved concurrency with a rate limit. Reserved concurrency bounds concurrent invocations; processing rate also depends on duration and batch size.

### 10.1. Coordinating reserved concurrency and maximum concurrency

Suppose a function has two SQS event source mappings:

- The `orders` mapping has maximum concurrency 20.
- The `refunds` mapping has maximum concurrency 10.
- The function's reserved concurrency is 25.

Both mappings can compete within the shared 25-invocation budget. To guarantee dedicated capacity, separate functions or allocate concurrency appropriately.

An operational rule of thumb is that the sum of expected mapping maximum concurrencies should not exceed reserved concurrency in ways that cause unintended starvation. Reserved concurrency can also be consumed by other invokers if the function is triggered from multiple sources.

Maximum concurrency is an event source mapping limit, not a requests-per-second rate. With large batch sizes, each invocation can process many messages. Measure actual message throughput to verify real behavior.

### 10.2. FIFO queues and message groups

SQS FIFO preserves ordering within each message group. Messages in the same group run sequentially; different groups can run in parallel.

If a queue has only one active message group, raising Lambda concurrency adds no parallelism for that group. With 100 independent groups, many groups can run concurrently within mapping and function limits.

Test these cases:

- Single group with many messages: order is preserved.
- Multiple groups: parallel execution across groups is allowed.
- One group hits a failing message: observe impact on subsequent messages in the same group.
- Higher concurrency: does not break intra-group ordering.
- Retries: do not produce duplicate side effects.

## 11. Throttling Pub/Sub subscribers

Google Pub/Sub subscriber clients provide flow control to cap outstanding messages and total outstanding bytes held by the client before acking.

With the Java client, `FlowControlSettings` lets you set element and byte limits. Once reached, the subscriber can block receiving additional messages or apply the configured limit-exceeded behavior.

Illustrative configuration example:

~~~java
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.batching.FlowController.LimitExceededBehavior;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;

public final class OrdersSubscriber {

    public Subscriber create(
            String projectId,
            String subscriptionId,
            MessageReceiver receiver) {

        ProjectSubscriptionName name =
                ProjectSubscriptionName.of(projectId, subscriptionId);

        FlowControlSettings flowControl =
                FlowControlSettings.newBuilder()
                        .setMaxOutstandingElementCount(200L)
                        .setMaxOutstandingRequestBytes(20L * 1024 * 1024)
                        .setLimitExceededBehavior(
                                LimitExceededBehavior.Block)
                        .build();

        return Subscriber.newBuilder(name, receiver)
                .setFlowControlSettings(flowControl)
                .build();
    }
}
~~~

API names and overloads may vary by Google Cloud Pub/Sub Java client version. This is a conceptual configuration example; verify the exact dependency version in use. Flow control limits how many messages the client holds outstanding, not the requests-per-second quota of a downstream API.

When a receiver callback processes asynchronously, ack only when work completes according to application semantics. If the callback returns immediately after submitting to an executor, Pub/Sub may treat the message as handled before the worker finishes.

### 11.1. Ack deadline and parallelism

Flow control must coordinate with ack deadlines, ack extensions, executor concurrency, and processing time. If the outstanding limit is too high, the client may hold too many messages in memory. If too low, throughput drops and subscribers underutilize capacity.

Monitor outstanding message counts/bytes, ack latency, redeliveries, oldest unacked age, and callback processing duration. Tune one parameter at a time during load tests instead of raising everything simultaneously.

## 12. Throttling Kafka consumers

Kafka consumers are commonly throttled via:

- Topic partition count.
- Consumer count in a group.
- Records fetched per poll (`max.poll.records`).
- Maximum interval between polls (`max.poll.interval.ms`).
- Partition pause/resume mechanisms.
- Parallel worker count and offset commit strategy.
- Downstream concurrency/rate limits.

Consumer group parallelism is bounded by assigned partitions. If a topic has 8 partitions, scaling consumers to 20 will not process 20 partitions in parallel within one group; extra consumers sit idle.

When processing records asynchronously, ensure offset commits never advance past records not yet successfully processed under your chosen ordering and retry semantics. Committing early risks losing records on crash. Committing too late can cause redeliveries and duplicates.

### 12.1. Pause and resume

When downstreams overload, consumers can pause one or more partitions to stop fetching new records, finish processing already-fetched records, and resume once capacity recovers.

Do not block the consumer thread so long that it exceeds `max.poll.interval.ms` and triggers a group rebalance. In Java clients, design the poll loop to keep polling on cadence while worker pools process records; pause/resume and commits must align synchronously with the Kafka client API.

When partition ordering is required, process records within a partition in order or track completion sequences/offsets before committing. Never feed a random parallel thread pool and commit the highest offset while earlier records remain pending.

## 13. Batch size: throughput and failure blast radius

Large batches reduce invocation overhead and raise throughput. However, large batches also:

- Increase memory required for payloads.
- Extend single-invocation processing time.
- Increase the number of messages retried on batch-level failures.
- Potentially increase tail latency due to batch accumulation waits.
- Allow one poison message to impact many healthy messages.

Small batch sizes shrink blast radius and batching latency but raise overhead and invocation counts.

Choose batch sizes via load testing tailored to message type, processing duration, and partial failure semantics. If message sizes vary widely, bound both record count and total bytes.

### 13.1. Partial batch failure

With event sources supporting partial batch responses, consumers can report only failed records so the broker redelivers just what needs retrying. Without partial support, one failure in a batch can cause the entire batch to redeliver.

Consumers must be idempotent because previously succeeded records may reappear during batch retries. Use a stable event ID or idempotency key and persist processing outcomes durably.

Never catch exceptions and return success for the whole batch unless failed messages have been durably written to a DLQ or durable error handler.

## 14. Choosing concurrency and rate limits by workload

| Workload | Primary control to prioritize | Reason |
|---|---|---|
| Email/SMS delivery | Rate limit per provider quota | Providers typically enforce strict sending rates |
| Payment API | Rate limit + concurrency + idempotency | Protects quotas and prevents duplicate charges |
| Database writer | Connection/concurrency cap | Prevents connection exhaustion and lock contention |
| Image processing | CPU/memory concurrency | Each job can consume heavy compute |
| Kafka consumer | Partition parallelism + bounded workers | Preserves ordering and avoids premature commits |
| Pub/Sub subscriber | Outstanding message/byte flow control | Bounds memory and in-flight work |
| SQS Lambda consumer | Event source max concurrency + reserved concurrency | Caps total invocations and protects dependencies |

Do not apply the same concurrency cap to every message type. A message taking 5 ms and a message making a 2-second external API call have very different capacity profiles.

## 15. Interaction between autoscaling and concurrency caps

Autoscalers typically add consumer capacity as backlogs or request loads grow. Concurrency caps set an upper ceiling to protect dependencies.

If the cap is too low:

- Backlogs grow continuously.
- Oldest message age breaches SLAs.
- Drain times stretch out.
- The autoscaler may hit max scale while throughput remains insufficient.

If the cap is too high:

- Databases/APIs become overloaded.
- Timeouts and retries climb.
- Messages get reprocessed.
- Useful throughput drops despite high invocation counts.

A sound strategy is setting max scale from total downstream capacity, then tuning per-instance concurrency and batch size. Monitor backlog age and downstream saturation together.

### 15.1. Example limit calculation

Suppose a payment provider allows 100 requests/second. One request takes 250 ms on average. By Little's Law, average concurrent requests needed to fully utilize the quota is:

\[
C \approx \lambda \times W = 100 \times 0.25 = 25
\]

You can start benchmarking around concurrency 25 and a rate limit of 100 requests/second. Leave headroom for tail latency, retries, and other clients sharing the quota. If the provider quota is shared across services, the worker's budget must be lower than 100 requests/second.

Do not set concurrency to 100 just because the quota is 100 requests/second; processing duration and concurrency limits are two separate factors.

## 16. Retries can amplify load

When a dependency is overloaded, unbounded retries add even more requests. An initial burst can escalate into a retry storm.

For example, 100 messages/second retried three times due to a slow API can generate 300 requests/second during that window, not counting fresh traffic. If multiple consumers retry on the same cadence, load can synchronize into recurring spikes.

Measures:

- Exponential backoff.
- Jitter to spread out retries.
- Maximum retry attempt caps.
- Separating retryable from permanent errors.
- Circuit breakers when dependencies fail persistently.
- Lowering consumer concurrency when downstreams overload.
- Routing failed messages to DLQs per policy.
- Using idempotency keys for side effects.

Never retry immediately in a tight loop. Never retry business 4xx errors or permanent config errors like missing IAM permissions unless a specific remediation mechanism exists.

## 17. Circuit breakers and bulkheads

Bulkheads isolate resources between dependencies or workload groups. Circuit breakers temporarily stop calling a dependency when error rates breach thresholds, giving it time to recover.

Example:

- Payment provider is slow: open the circuit for payment calls.
- Inventory API remains healthy: keep processing message types that do not depend on payment.
- Workers reserve only a subset of permits for payment so payment cannot exhaust the whole thread pool.
- Payment messages can be deferred or retried per policy.

Circuit breakers do not replace queues or retry policies. When a circuit opens, consumers must decide whether to hold messages, fail so the broker retries, or transition to a waiting workflow state. Never ack a message as succeeded unless it is durably stored for continuation.

## 18. Handling overload and load shedding

When the system hits limits, decide which work gets priority:

- Reject non-essential work.
- Defer work that can wait.
- Leave messages in the queue rather than pulling them into the process.
- Prioritize messages with tighter deadlines if semantics allow.
- Lower batch/concurrency or pause consumers.
- Route permanent failures to DLQs.
- Enable degraded modes for secondary features.

Load shedding requires business rules. Do not drop payment or inventory-update messages simply because the system is overloaded. If work must be rejected, ensure messages are retained or failure states recorded.

## 19. Measuring load-control effectiveness

Track these metrics:

| Metric | Meaning |
|---|---|
| Active consumer concurrency | Number of messages currently processing |
| Configured max concurrency | Configured ceiling |
| Arrival rate | Incoming message rate |
| Processing/ack rate | Completion rate |
| Queue backlog | Remaining waiting work |
| Oldest message age | How long the oldest message has waited |
| In-flight/outstanding | Messages received but not yet finished |
| Rate limiter denied/wait | Frequency of rate-limit throttling |
| Bulkhead rejected | Tasks failing to acquire permits |
| Dependency latency/error | Downstream health |
| Retry and DLQ rate | Error and redelivery levels |
| Drain time estimate | Projected time to clear backlog |

A well-tuned concurrency cap keeps downstream latency stable without unbounded backlog growth. If backlogs grow while dependencies still have capacity, raise caps or consumer replicas carefully. If dependencies are already saturated, raising caps can make things worse.

Never put message IDs, order IDs, or customer IDs in metric labels. Keep those identifiers in logs/traces to avoid high cardinality.

## 20. Testing load control

A test suite should cover:

1. **Steady load:** constant arrival rate below capacity.
2. **Burst:** producer ramps rapidly for a short window.
3. **Sustained overload:** arrival rate exceeds processing rate over an extended period.
4. **Slow dependency:** database/API latency increases.
5. **Dependency throttling:** downstreams return 429 or throttling errors.
6. **Consumer crash:** process terminates while holding messages.
7. **Retry storm:** many messages retry concurrently.
8. **Cold scale-out:** autoscaler provisions new instances.
9. **Rate limiter exhaustion:** token bucket runs dry.
10. **Bulkhead full:** all permits are occupied.
11. **Large batch:** large payloads or batch sizes.
12. **FIFO ordering:** many messages in one group and across many groups.
13. **Kafka rebalance:** a consumer leaves the group while records are in flight.
14. **Pub/Sub flow control:** outstanding limits hit thresholds.
15. **Global quota:** multiple instances call a dependency sharing one quota.

In tests, verify:

- Total concurrency does not exceed configured limits.
- Actual rate does not breach quotas over the relevant measurement interval.
- Backlogs and message age recover after bursts.
- Dependency latency does not climb past safe thresholds.
- Messages are not lost when executors fill or consumers crash.
- Duplicates are handled idempotently.
- Required ordering is preserved.
- Alerts fire when backlogs or age breach SLOs.

## 21. Workflow for choosing and tuning limits

1. **Measure baseline.** Record arrival rates, processing durations, downstream latency, and backlogs.
2. **Identify bottlenecks.** Find limits across databases, APIs, brokers, CPU, and memory.
3. **Compute initial capacity.** Use empirical throughput and Little's Law to estimate concurrency.
4. **Set platform limits.** Configure reserved concurrency, max instances, or event source maximum concurrency.
5. **Configure queue flow control.** Bound outstanding messages/bytes, batch sizes, and polling.
6. **Set in-process Java limits.** Use bounded executors, semaphores, rate limiters, or bulkheads.
7. **Align retries.** Configure backoff, jitter, max attempts, and DLQs.
8. **Load test.** Step up traffic, bursts, and dependency latency.
9. **Monitor SLOs.** Watch oldest message age, drain times, and downstream saturation.
10. **Adjust one variable at a time.** Change one configuration group per iteration to observe impact.
11. **Document runbooks.** Define when to reduce concurrency, pause consumers, or add capacity.

Do not optimize strictly for zero backlog at all times. Queues exist to absorb bursts and smooth load. The goal is keeping message age within SLAs, protecting dependencies, and draining backlogs within an acceptable window.

## 22. Self-check questions

- How does concurrency differ from processing rate?
- How does Little's Law help estimate in-flight message counts?
- Why can't a semaphore in a single Java process cap total concurrency across multiple instances?
- How does backpressure differ from rate limiting?
- How does a token bucket allow bursts?
- How does reserved concurrency differ from event source mapping maximum concurrency?
- Why does SQS FIFO parallelism depend on message group count?
- How does Pub/Sub flow control cap outstanding messages and bytes?
- What limits the parallelism of a Kafka consumer group?
- What problem does a bounded executor prevent?
- Why should you not ack immediately after submitting a task to an in-memory executor?
- How can a retry storm further overload a dependency?
- When should you use a circuit breaker vs. a bulkhead?
- Why can raising consumer concurrency actually decrease throughput?
- Which metrics should you monitor when tuning load control?
