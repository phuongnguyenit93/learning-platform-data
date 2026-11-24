# Rate Limiting Processing Throughput

In a Spring Kafka system, the ability to **read fast** from Kafka does not equate to the ability to **process fast and safely**. Kafka can retain millions of records for consumers to read gradually, whereas the database, REST API, payment system, or compute resources used by the listener typically have their own limits. If a consumer fetches and processes more records than a dependency can sustain, the system may suffer timeouts, connection pool exhaustion, 429/503 errors, and retry storms. As a result, latency climbs even after raising consumer counts or concurrency.

**Processing rate limiting** is the practice of capping the number of business operations executed per unit of time or the number of concurrently running operations. In the **Pause and Backpressure** chapter, rate limiting must be considered alongside pause/resume, in-flight limits, consumer lag, and recovery behavior when downstream is overloaded.

The goal is not to slow Kafka down at all costs, but to **protect dependent systems and maintain a sustainable processing rate**, without losing records, without committing offsets before business work finishes, and without causing consumers to lose partition ownership due to excessive processing duration.

## 1. Why does a consumer need rate limiting?

Suppose a consumer group reads the `payment.requests` topic at an average rate of 1,200 records/second. Each record calls a payment API. The API can sustainably accept only around 700 requests/second.

Without control:

    Kafka: 1,200 records/s
              |
              v
    12 consumer threads
              |
              v
    Payment API: capacity 700 req/s
              |
              +--- HTTP 429 / 503
              +--- timeouts and growing queues
              +--- repeated retries
              +--- higher latency

Raising concurrency from 12 to 24 consumers does not make the API stronger; it can make the incident more severe.

When enforcing an aggregate cap around 600–700 operations/second, the service can operate more steadily:

    Kafka: 1,200 records/s
              |
              v
    Consumer + rate limiter: max 650 API calls/s
              |
              v
    Payment API: capacity 700 req/s
              |
              v
        Steady processing

However, rate limiting **does not erase backlog**. If data continues arriving faster than the processing rate, consumer lag still grows. The system must plan for retention, business wait tolerance, and ways to reduce producer load or scale the dependency.

## 2. Distinguishing rate limits, concurrency limits, and backpressure

These concepts are related but not identical:

| Mechanism | What does it limit? | Example |
|---|---|---|
| Rate limit | Operations per unit of time | Max 200 requests/second |
| Concurrency limit | Operations running simultaneously | Max 20 in-flight HTTP requests |
| Backpressure | Feedback mechanism when downstream falls behind | Pause consumer when queue exceeds threshold |
| Batch size limit | Records or bytes per read/processing pass | Max 100 records per poll |
| Retry backoff | Wait interval between retry attempts after failure | Wait 1, 2, 4 seconds |
| Autoscaling | Increasing or decreasing consumer instances | 2 pods to 4 pods |

A dependency might sustain 1,000 requests/second yet at most 50 concurrent requests. When each request takes 200 ms, concurrency and rate constrain each other by the approximation:

    Throughput <= ConcurrentRequests / AverageRequestDuration

For example, 50 concurrent requests each taking 0.2 seconds yields a theoretical maximum throughput around 250 requests/second without additional pipelining or overhead.

For stability, you may need **both a rate limit and a concurrency limit**. Limiting requests/second alone does not prevent a batch of slow requests from lingering too long and exhausting the connection pool.

## 3. Does the Kafka consumer provide business rate limiting out of the box?

The Kafka consumer has parameters to tune fetched data volume and poll cadence, but they are not a precise limiter of business side effects per second.

Several settings:

| Parameter | Primary effect | Is it an absolute records/second limit? |
|---|---|---|
| max.poll.records | Maximum records returned in a single poll | No |
| fetch.min.bytes | Bytes broker tries to accumulate before returning a fetch | No |
| fetch.max.wait.ms | Time broker may wait to accumulate a fetch | No |
| max.partition.fetch.bytes | Maximum bytes fetched per partition per config | No |
| concurrency (Spring Kafka) | Number of child consumers processing in parallel | No |
| idleBetweenPolls (Spring Kafka) | Idle interval between polls | No |
| pause/resume | Temporarily halt/resume fetching from partitions | No, though usable for backpressure |

For instance, `max.poll.records=100` only means each poll returns at most 100 records; the consumer can still call poll many times within a single second. Conversely, setting `max.poll.records=1` does not guarantee the listener processes only one record per second.

If the objective is protecting an API with a requests/second quota, the rate limiter must be placed at **the request callsite**, where the bounded operation can be measured accurately.

## 4. Choosing the unit of measurement before setting limits

Not every workload should be limited by record count.

Common units:

- **Records/second:** fits when every record has roughly uniform processing cost.
- **Requests/second:** fits when each record makes one or more API calls; the limiter must count actual calls.
- **Bytes/second:** useful when record sizes vary widely and network/serialization is the bottleneck.
- **Transactions/second:** fits when the dependency caps DB transactions.
- **Concurrent requests:** fits when latency is unstable and connection pools are the bottleneck.
- **Weighted tokens:** each record consumes tokens proportional to its expected weight.

For example, an `OrderCreated` record triggers one API call, while `OrderSettled` triggers five calls. A limit of 100 records/second does not equal a limit of 100 API requests/second.

Before selecting configuration, clearly identify the resource to protect and its actual quota unit.

## 5. Limiting per consumer, per pod, or across the whole consumer group?

This is a critical architectural decision.

Suppose there are four pods, each running `concurrency=3`:

    Pod A: 3 consumer threads
    Pod B: 3 consumer threads
    Pod C: 3 consumer threads
    Pod D: 3 consumer threads

If **each pod** has a shared rate limiter capped at 50 requests/second, the nominal total load is:

    4 pods x 50 req/s = 200 req/s

If **each consumer thread** creates a 50 requests/second limiter, the nominal total load can become:

    4 pods x 3 threads x 50 req/s = 600 req/s

If the external API only permits 200 requests/second for the **entire application**, the second approach can violate the quota even though each individual limiter works properly.

| Scope | Advantages | Risks |
|---|---|---|
| Per record handler | Easy to inspect inside handler logic | Easy to mis-instantiate a new limiter, no shared cap |
| Per consumer thread | Isolates each thread | Total quota multiplies by concurrency |
| Per pod/JVM | Simple, uses a singleton limiter | Total quota multiplies by replica count |
| Per tenant/key | Fair across user groups | Requires per-tenant state/quotas and key cardinality management |
| Global/distributed | Protects a cluster-wide shared quota | Requires coordination service, network latency, and limiter-failure strategy |

Determine whether the dependency's quota is per credential, per tenant, per node, or system-wide, and place the limiter accordingly. Do not accidentally multiply quota when an autoscaler adds pods.

## 6. Approach 1: Limiting requests inside the listener with a rate limiter

For some consumers and dependencies needing a simple requests/second quota, you can use Guava `RateLimiter` as a **singleton bean** per JVM.

Configuration example:

~~~java
import com.google.common.util.concurrent.RateLimiter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConsumerRateLimitConfiguration {

    @Bean
    RateLimiter paymentApiRateLimiter(
            @Value("${app.payment.max-requests-per-second:40}")
            double permitsPerSecond) {

        return RateLimiter.create(permitsPerSecond);
    }
}
~~~

Listener:

~~~java
import com.google.common.util.concurrent.RateLimiter;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentRequestListener {

    private final RateLimiter paymentApiRateLimiter;
    private final PaymentGateway paymentGateway;

    public PaymentRequestListener(
            RateLimiter paymentApiRateLimiter,
            PaymentGateway paymentGateway) {

        this.paymentApiRateLimiter = paymentApiRateLimiter;
        this.paymentGateway = paymentGateway;
    }

    @KafkaListener(
        id = "paymentRequestsListener",
        topics = "payment.requests",
        groupId = "payment-service"
    )
    public void consume(PaymentRequested event) {

        // All consumer threads in the JVM share the same limiter bean.
        paymentApiRateLimiter.acquire();

        // Side effect must be idempotent by event ID.
        paymentGateway.charge(
            event.paymentId(),
            event.amount(),
            event.eventId()
        );
    }
}
~~~

Declare the Guava dependency according to your project's build setup. `PaymentRequested` and `PaymentGateway` are illustrative domain types.

Notable points:

1. A `RateLimiter` bean is singleton-scoped by default in Spring, so listener threads in the same application share the quota.
2. `acquire()` **can block** waiting for a permit; this applies backpressure right on the consumer thread.
3. `acquire()` limits **how many times API calls are initiated**, not how many succeed.
4. With multiple pods, each pod still has its own quota; split the quota or use a distributed limiter.
5. Token/leaky-bucket limiters can allow brief bursts; do not confuse average rate with a strict cap over tiny sub-second windows.

**Important:** never create a new `RateLimiter` inside every `consume()` invocation, as that resets quota state continuously and practically disables rate limiting.

## 7. Risk when acquire() blocks the consumer for too long

`RateLimiter.acquire()` is simple and fits moderate limits, yet the consumer must still poll frequently enough to maintain group membership.

Suppose:

- `max.poll.records=500`.
- The listener averages 20 records/second because it waits on permits and the API.
- One poll can return 500 records.
- Processing the entire batch takes roughly 25 seconds, excluding retries and I/O.

If quota drops to 1 record/second, the same 500 records could require over 8 minutes, exceeding the common 5-minute default `max.poll.interval.ms`. The consumer can lose assignments, trigger a rebalance, and reprocess records because offsets have not committed.

An estimation rule:

    PollProcessingTime ~= RecordsPerPoll / EffectiveRecordsPerSecond
                          + AdditionalProcessingAndRetryTime

Size `max.poll.records`, rates, and timeouts so that processing time **in a reasonable worst case** leaves comfortable headroom below `max.poll.interval.ms`.

In addition, consumer threads in the same pod share the limiter, so each thread does not necessarily receive permits equally. If fairness across partitions or tenants is required, use a separate scheduling/quota policy.

## 8. Tuning max.poll.records to support rate limiting

Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        max.poll.records: 50
        max.poll.interval.ms: 300000
    listener:
      concurrency: 2
      ack-mode: record
~~~

`max.poll.records=50` only caps records per poll. Paired with a limiter, it caps the amount of work each consumer thread may have to process before returning to poll.

For instance, if a consumer sustains 10 records/second, processing 50 records takes roughly 5 seconds plus I/O time. If downstream gets slower, shrink batch size or switch to an appropriate pause policy instead of letting the listener block for minutes.

Do not mechanically drop `max.poll.records` to 1. Polling too frequently can increase overhead and hurt throughput. Measure `records-consumed-rate`, processing duration, poll intervals, and commit latency before picking a value.

## 9. Approach 2: idleBetweenPolls on the Spring Kafka container

Spring Kafka provides **idleBetweenPolls** on `ContainerProperties` to insert a wait interval between consumer polls. This is a container-level way to slow consumption cadence.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setIdleBetweenPolls(500L);

    return factory;
}
~~~

The value `500L` is in milliseconds. As the container waits this interval between polls, throughput can drop if the workload is poll-rate bound.

However:

- **It is not a 2 records/second quota.** A single poll can return many records.
- With multiple consumer threads, each consumer has its own poll cadence.
- Under sparse traffic, idle intervals can add unnecessary latency.
- With long listener processing, the wait interval must stay coordinated with `max.poll.interval.ms`.
- The container may adjust idle intervals to respect the consumer's poll interval limit; details depend on the version.

`idleBetweenPolls` fits when you want to simply slow poll cadence, not when you must guarantee an exact cluster-wide HTTP calls/second cap.

## 10. Approach 3: Pause/resume when downstream is overloaded

If a database or API is visibly overloaded, some systems should stop accepting new work even if the average quota has not been reached. In that case, you can **pause the container** and resume once the dependency recovers.

Spring Kafka exposes `MessageListenerContainer.pause()` and `resume()`. Containers can be accessed through `KafkaListenerEndpointRegistry` using listener ID.

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ConsumerFlowControl {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerFlowControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pausePayments() {
        MessageListenerContainer container =
                registry.getListenerContainer("paymentRequestsListener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumePayments() {
        MessageListenerContainer container =
                registry.getListenerContainer("paymentRequestsListener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

The container ID must match `id` on `@KafkaListener`. Do not assume the lookup method always returns non-null; a listener might not be registered yet, may have been removed, or may not be running.

**Pause is not stop.** When partitions are paused, the Spring Kafka container continues polling appropriately so the consumer stays in the group and sends heartbeats. The goal is halting new records from paused partitions without intentionally leaving the consumer group.

Even so, pause is not a promise to instantly freeze every running listener. Already-polled records and in-flight tasks may still be processing. If you need finer control at the record boundary, look at `pauseImmediate`.

## 11. pauseImmediate and already-polled records

When `pause()` is called on a Spring Kafka container, the pause request normally takes effect at a safe point in the poll loop. For a record listener, records polled earlier may continue processing before the container actually pauses.

In supporting Spring Kafka versions, `ContainerProperties` has the **pauseImmediate** property:

~~~java
factory.getContainerProperties().setPauseImmediate(true);
~~~

With this mode, after receiving a pause request, the container can pause processing after the current record, retaining records already polled but not yet delivered to the listener so they resume afterward.

This is a useful choice when a dependency starts overloading and you want to stop feeding more records to the listener sooner.

Understand clearly:

- `pauseImmediate` does not undo already-executed side effects.
- It does not forcibly interrupt a currently running record.
- It does not mean committing offsets for all polled data.
- Retained records must be processed after resume per container behavior.
- If the process crashes, replay still depends on committed offsets and Kafka retention.

Verify the API and semantics of your project's Spring Kafka version; do not apply newer-version configuration on an older dependency without confirming support.

## 12. Pausing per partition instead of the whole listener

In some cases, only a single partition or tenant is bottlenecked. Pausing the whole container stops healthy partitions too.

Modern Spring Kafka supports requesting pause/resume by `TopicPartition` through the listener container API:

~~~java
TopicPartition partition =
        new TopicPartition("payments", 3);

MessageListenerContainer container =
        registry.getListenerContainer("paymentRequestsListener");

if (container != null) {
    container.pausePartition(partition);
}

// When recovery conditions are met:
if (container != null) {
    container.resumePartition(partition);
}
~~~

Ensure the topic/partition actually pertains to that container, as assignments can shift to another consumer after a rebalance. In some versions, `pausePartition`/`resumePartition` APIs were added later than container-wide pause/resume.

Halting a partition does not make Kafka move records to another partition. Keys/ordering and ownership still follow the current assignment. If the paused partition keeps receiving new data from producers, lag on that partition will keep rising.

Per-partition pause is helpful when independent processing rules apply per partition. If quotas are per tenant yet multiple tenants share a partition, pausing the partition can slow down healthy tenants too.

## 13. Building a threshold-based backpressure controller

You can build a periodic controller driven by downstream capacity signals.

Suppose the service reads a queue-depth metric from a dependency:

    queue depth >= 1,000  -> request pause
    queue depth <=   300  -> request resume
    in between            -> keep current state

Two distinct thresholds create **hysteresis**, preventing continuous pause/resume oscillation when the queue hovers around a single value.

Interface and scheduling example:

~~~java
public interface DownstreamCapacitySignal {
    long pendingOperations();
}

@Component
@EnableScheduling
public class PaymentBackpressureController {

    private final DownstreamCapacitySignal capacity;
    private final ConsumerFlowControl flowControl;
    private boolean requestedPause;

    public PaymentBackpressureController(
            DownstreamCapacitySignal capacity,
            ConsumerFlowControl flowControl) {
        this.capacity = capacity;
        this.flowControl = flowControl;
    }

    @Scheduled(fixedDelay = 2_000L)
    public synchronized void evaluate() {
        long pending = capacity.pendingOperations();

        if (!requestedPause && pending >= 1_000L) {
            flowControl.pausePayments();
            requestedPause = true;
        }
        else if (requestedPause && pending <= 300L) {
            flowControl.resumePayments();
            requestedPause = false;
        }
    }
}
~~~

This is a **single-instance** control example, not a cluster-wide quota coordinator. `@EnableScheduling` should be placed on a configuration class suited to your application architecture; placing it on the component here illustrates that scheduling must be enabled.

In real deployments:

- Confirm the container exists and is running before recording `requestedPause`.
- Read `isPauseRequested` or consumer paused state if supported by the API version.
- When an instance restarts, `requestedPause` resets; decide whether to re-pause automatically based on downstream metrics.
- If metrics are unavailable, explicitly choose fail-open vs. fail-closed based on business criticality.
- The controller should not pause on a single anomalous data point; add dwell time or cooldowns.
- With multiple pods, each pod runs its own controller; if all pods pause together, lag can spike quickly. Coordinate if sharing a global quota.

## 14. Choosing between waiting for permits and pausing the consumer

The two strategies carry different trade-offs:

| Criterion | Waiting for permit in listener | Container pause/resume |
|---|---|---|
| Per-operation accuracy | Good if limiter sits close to the request | Does not guarantee a specific RPS |
| Poll loop | Listener can block for a long time | Container keeps polling/heartbeating while paused |
| In-flight | Current record must wait | In-flight may continue before pause takes effect |
| Ordering | Relatively easy to preserve with sync processing | Resume continues per partition |
| Incident control | Limited if the dependency is completely down | Well suited when downstream overloads or circuit opens |
| Complexity | Simple for a small quota | Requires controller and resume signals |
| Multiple pods | Local limiter easily multiplies quota | Pods must coordinate pause state |

A common design is:

1. Use a per-pod limiter to smooth requests under normal conditions.
2. Use a concurrency limit to prevent too many simultaneously running requests.
3. Use pause/resume when the dependency crosses overload thresholds or a circuit breaker opens.
4. Use backoff and DLT for genuine record errors, never infinite retries to throttle speed.

You do not need every mechanism on every listener. Choose according to bottlenecks and SLAs.

## 15. Limiting concurrent requests

A per-second rate limit may be insufficient when latency fluctuates. If a dependency slows down, concurrent in-flight requests grow even while requests-per-second stays under the threshold.

Java's `Semaphore` is a simple tool to bound concurrent operations, especially with thread pools or async workers:

~~~java
public final class BoundedGateway {

    private final Semaphore permits = new Semaphore(8);
    private final PaymentGateway gateway;

    public BoundedGateway(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void charge(PaymentRequested event)
            throws InterruptedException {

        permits.acquire();
        try {
            gateway.charge(
                event.paymentId(),
                event.amount(),
                event.eventId()
            );
        }
        finally {
            permits.release();
        }
    }
}
~~~

This example limits concurrency **within a single instance**. With 5 pods, total concurrency can be 40. Moreover, `acquire()` can wait indefinitely; in production you need timeouts, interrupt handling, and a pause/retry strategy when permits cannot be acquired quickly enough.

If a listener runs synchronously with `concurrency=4` and no async offloading, concurrent gateway calls from that listener are already bounded by the number of consumer threads. A semaphore shines when multiple workloads share the gateway or an async worker pool exceeds consumer concurrency.

Never offload a task and immediately call ack just to free up the consumer thread. Acknowledgments must correspond to durably completed side effects.

## 16. Backpressure with async processing and bounded queues

An unsafe design:

    Kafka listener polls fast
             |
             v
    unbounded executor.submit(record)
             |
             v
    JVM queue grows continuously
             |
             v
    OutOfMemory / crash / record replay

If the listener returns immediately after `submit()`, Spring Kafka may consider the record processed and commit offsets per `AckMode`, even while the task sits in the queue. When the JVM crashes, acked-but-unfinished tasks can be lost from the business flow.

A reliable async design requires:

- A bounded queue, never an unbounded one.
- Per-partition or per-instance in-flight limits.
- Acknowledging only after the task completes past the chosen durability boundary.
- Controlling ack ordering and pausing/resuming when pending tasks grow large.
- Stopping or fencing stale tasks when partitions are revoked/lost.
- Idempotent side effects for safe redelivery.
- A strategy when the queue is full: pause upstream, bounded wait, or controlled rejection **without acking success**.

Spring Kafka's async acknowledgments have version-specific behavior; handling out-of-order acks can cause the container to pause to avoid committing past incomplete records. Do not assume that acking one completed record lets offsets advance past an earlier incomplete record in the same partition.

If true async throughput is not required, synchronous processing with right-sized concurrency is usually simpler and easier to keep reliable.

## 17. Rate limiting with retries and DefaultErrorHandler

When downstream is already overloaded, retrying nonstop after 429/503 errors can be worse than the original traffic.

For example, a listener has a 50 requests/second limiter while `DefaultErrorHandler` retries three times per record. If retries also hit the dependency, total requests can multiply significantly.

Determine **where permits are counted**:

- If the limiter sits before every HTTP call, both initial calls and retries consume permits.
- If the limiter sits only at the top of the listener while an internal HTTP client retries multiple times, the quota misses those extra requests.
- If the listener is re-invoked on each retry, the limiter still applies on each attempt.
- If recovery/DLT publishing uses another dependency, it may need a separate quota.

A sample retry policy:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

handler.addNotRetryableExceptions(
    InvalidBusinessEventException.class
);
~~~

This is just a finite retry configuration example; `recoverer` and exception classes must be defined in the application.

Rate limiters are for **allocating normal capacity**; error handlers are for **handling failed records**. Do not throw fake exceptions so `DefaultErrorHandler` adds artificial delay to successful records. That inflates logs, retry counts, and lag, and can cause duplicate side effects.

When an API returns `Retry-After`, honor the recovery timestamp per the API contract whenever possible instead of retrying earlier merely because a limiter granted a permit.

## 18. Shared quotas and distributed rate limiters

If all pods share one API key with a 1,000 requests/second quota, per-pod limiters break down when replica counts change.

Implementation options:

**Divide quota by replica count:** a controller computes each pod's limit roughly as global quota / replica count. Simple, though it requires fast updates on scaling, headroom, and handling pods not yet ready.

**Distributed token bucket:** a coordination store such as Redis holds shared token state. Each API call acquires a permit from the cluster-wide quota. You must handle latency, Redis outages, clock/lease semantics, and choose fail-open vs. fail-closed.

**Centralized gateway:** all requests route through a single service enforcing a shared quota. Easy to monitor, yet the gateway becomes a new dependency that must scale and be protected.

**Per-tenant/key quota:** use separate keys per tenant if downstream enforces per-tenant quotas. Prevents one hot tenant from exhausting tokens for all other tenants.

Allocation example:

    Global API quota: 900 req/s
    Safety reserve:    90 req/s
    Available budget: 810 req/s
    Active pods: 3
    Local target: 270 req/s per pod

If scaled to six pods without updating local quotas:

    6 x 270 = 1,620 req/s -> breaches shared quota

Measure actual replica counts and enforce safety rules. The reserve margin is an operational decision leaving room for other traffic, retries, and measurement skew, not a mandatory constant.

## 19. Limiting by partition or business key

Kafka maintains ordering within each partition. If you want to throttle one data group while keeping others moving, consider quotas per partition or per key.

For example, a topic has tenant A and tenant B:

    Partition 0: Tenant A very high traffic
    Partition 1: Tenant B moderate traffic
    Partition 2: Tenant A + B mixed

Pausing Partition 0 can reduce Tenant A's load, yet Partition 2 still contains both A and B. If you only want to throttle A, you need per-key/tenant handling or suitable partitioning design.

Options:

- Per-tenant token bucket inside the listener.
- Separate topics for tenants with different SLAs.
- Stable partition keys to segregate workloads if business rules allow.
- Per-tenant quotas at a downstream gateway.
- Weighted fair scheduling with bounded queues.

Avoid creating a new limiter per `eventId`. `eventId` is almost always unique, so the limiter never accumulates state to enforce a quota. With high-cardinality `tenantId`, enforce TTLs and memory bounds on the limiter map.

Do not randomize keys merely to spread load when the business requires ordering by `orderId`/`customerId`.

## 20. How does lag change when throttling?

Suppose Kafka producers generate lambda records/second and consumers sustainably process mu records/second. When lambda > mu, lag grows approximately as:

    LagGrowthRate = lambda - mu
    LagAfter(t) ~= InitialLag + (lambda - mu) * t

Example:

    Input = 900 records/s
    Safe processing = 600 records/s
    Difference = 300 records/s

    After 10 minutes:
      Additional lag ~= 300 * 600 = 180,000 records

    After 1 hour:
      Additional lag ~= 300 * 3,600 = 1,080,000 records

This is why rate limiting cannot be the sole solution if producer rate continuously exceeds downstream capacity. Either reduce/throttle input, expand dependency capacity, or plan for backlog within designed SLAs and retention.

If input later drops to 300 records/second while the consumer still processes 600 records/second, backlog drains at a theoretical rate of 300 records/second:

    DrainRate = 600 - 300 = 300 records/s
    DrainTime ~= CurrentLag / DrainRate

With 180,000 records of lag, minimum drain time is estimated at 600 seconds (10 minutes), excluding rebalances, retries, partition skew, and I/O.

Formulas are approximate models only. Kafka lag is calculated from offsets and can differ from remaining business work if offsets commit early or a single record triggers multiple side effects.

## 21. Setting limits according to SLA and retention

Rate limiting is a trade-off between dependency stability and record processing latency.

Determine:

- What is the maximum event processing age allowed by the business?
- How many days of Kafka retention exist relative to potential backlog buildup?
- How do peak input rate and sustained rate differ?
- Does the dependency enforce a hard quota or a recommended threshold?
- Can producer traffic be throttled or certain events prioritized?
- If downstream has a 30-minute outage, how large will the backlog grow?
- After recovery, does the consumer have enough excess capacity to drain the backlog before records expire past retention?

For example, a topic has 24-hour retention. If a consumer is throttled so low that lag climbs continuously for days, old records risk expiring due to retention before being consumed. Rate limiting cannot be considered safe merely because the listener throws no exceptions.

Set alerts on **oldest unprocessed record age** alongside lag. A 50,000-record backlog might clear in seconds or hours depending on throughput.

## 22. Adaptive rate limiting based on dependency health

Fixed quotas are easy to configure but do not reflect downstream capacity changing over time. An adaptive controller can raise/lower rates based on latency, error rate, queue depth, or 429 responses.

Illustrative policy example:

| Condition | Action |
|---|---|
| Low p95 API latency, near-zero 429s, stable queue | May increase limit in small steps |
| p95 latency climbing continuously | Step down limit |
| 429/503 rate exceeds threshold | Cut limit sharply or pause |
| Circuit breaker open | Pause container in a controlled manner |
| Dependency healthy long enough | Resume and ramp limit up gradually |
| Kafka lag very high while dependency is healthy | Raise limit within known quota bounds |

Slow increase, fast decrease (additive increase / multiplicative decrease) helps dampen oscillation. Still, include **hysteresis**, cooldowns, min/max rates, and safeguards when metrics drop out.

Never raise the limit solely because Kafka lag grew while the dependency is signaling overload. Lag measures work demand; latency/errors/queue depth measure serving capacity. Good scaling/rate-limiting decisions require both signal groups.

Updating an active rate limiter must follow the thread-safe API of its implementation and avoid recreating limiters in ways that trigger uncontrolled bursts.

## 23. Circuit breakers and pause/resume

When a dependency fails continuously, a circuit breaker can trip OPEN and reject new calls. If the listener keeps polling and throwing exceptions for every record, the system can still generate needless retries and stall error partitions.

One design:

    Circuit CLOSED
       -> process records within rate limit
       -> errors exceed threshold
       -> Circuit OPEN
       -> container.pause()
       -> check dependency with an independent health probe
       -> Circuit HALF_OPEN
       -> test a very small request volume
       -> stable success
       -> container.resume()

Ensure the recovery-probing mechanism **does not depend on the paused listener**. If only the listener can call the API to prove the dependency is healthy, the system can lock itself into a permanent paused state.

Include a manual override or runbook for cases where the dependency does not self-recover. Upon resume, backlog may be large, so keep the limiter active and ramp up gradually instead of dumping all traffic at once.

## 24. Handling HTTP 429 and Retry-After

HTTP 429 typically indicates the client exceeded its quota. Responses may include a `Retry-After` header specifying how long to wait before sending more requests.

In a consumer pipeline:

1. Stop increasing concurrency/replicas.
2. Record which endpoint or API key is being throttled.
3. Temporarily lower global/per-pod rate limits.
4. If necessary, pause the relevant listener or partition.
5. Use bounded retries for failed records.
6. Do not send failed records to a DLT merely for temporary quota limits if recovery is feasible within SLA.
7. Resume after cooldown and monitor the 429 rate.

`Retry-After` should be handled with bounded durations and per the HTTP contract; values can be seconds or HTTP dates and must be parsed safely. Do not blindly trust an anomalous header that could pause a consumer for days.

If multiple consumers hit 429 simultaneously and resume at the exact same fixed instant, they create a **thundering herd**. Add jitter to resume or retry timing to spread load.

## 25. Observability for rate limiting

A system with a rate limiter but no metrics makes it hard to know whether the limit is protecting downstream or acting as an unnecessary bottleneck.

Suggested metrics:

| Metric | Meaning |
|---|---|
| acquired_permits_total | Total permits granted for processing |
| limiter_wait_duration | Time listener spent waiting for permits |
| limiter_rejected_total | Requests denied permits when using a nonblocking policy |
| downstream_requests_per_second | Actual dependency call rate |
| downstream_inflight | Number of currently running requests |
| downstream_429_503_total | Quota/overload errors |
| downstream_latency_p95_p99 | Dependency latency |
| consumer_lag | Backlog per group/topic/partition |
| oldest_record_age | Age of the oldest unprocessed record |
| consumer_pause_duration | Duration container/partition stayed paused |
| rebalance_count | Detects late polls or unstable membership |
| listener_processing_duration | Record processing time, including permit waits |
| dlt_rate | Tracks genuine errors needing recovery |

If the limiter protects the API while consumer lag climbs endlessly, limiter metrics might look "green" even as business SLAs are breached. Dashboards must display **capacity, backlog, and freshness** together.

When using Micrometer/Prometheus, avoid `eventId`, `orderId`, or `requestId` labels on metrics due to extreme cardinality. Attach `group`, `topic`, `API endpoint category`, `tenant tier`, or `limiter name`.

## 26. Testing rate limiting

Tests must verify both load limiting and consumer reliability.

### 26.1. Unit tests for the limiter

- With a controllable clock or random source, verify permit counts per time window.
- Verify multiple listener threads share the same singleton limiter per pod.
- Verify permit counts do not reset after each record.
- Verify internal HTTP retries also consume quota if limiting by HTTP calls.
- With nonblocking limiters, verify the path when no permit is available without acking records early.

### 26.2. Load tests with a broker and fake dependency

Use Embedded Kafka or Testcontainers with an HTTP stub recording request rates:

1. Create a multi-partition topic.
2. Publish a burst of 10,000 records.
3. Run the consumer at a 40 requests/second rate limit per pod.
4. Record a histogram of requests/second and concurrent request counts.
5. Observe lag growing during the burst and draining once input stops.
6. Verify committed offsets advance only after business success.
7. Scale from 1 to 3 pods and confirm aggregate quota changes as designed.

Avoid overly strict assertions over tiny windows because token buckets allow small bursts and OS thread scheduling is not millisecond-exact. Verify limits over sufficiently long windows with defined tolerances.

### 26.3. Pause/resume tests

1. Drive dependency queue depth past the high watermark.
2. Confirm the controller calls `container.pause()`.
3. Observe the container actually pauses and accepts no new records past the safe point.
4. Verify in-flight records are handled per policy.
5. Lower queue depth below the low watermark.
6. Confirm resume and processing of remaining records.
7. Kill a pod while paused; restart and verify continuation from committed offsets.

### 26.4. max.poll.interval.ms tests

1. Set a large `max.poll.records` and small quota to create long poll processing times.
2. Observe rebalance, commit failures, and redelivery when the poll interval is exceeded.
3. Reduce `max.poll.records` or switch to appropriate pausing.
4. Confirm the consumer maintains stable membership at the target load.

### 26.5. Downstream overload tests

1. Have the dependency return 429/503 or increase latency.
2. Observe limiter, circuit breaker, and pause behavior.
3. Verify bounded retries and jitter to avoid synchronized storms.
4. Let the dependency recover.
5. Confirm controlled ramp-up without bursting past quota.
6. Verify `eventId`/idempotency so no duplicate side effects happen after retries.

## 27. Runbook when the consumer is throttled too aggressively

If lag grows abnormally after deploying rate limits to production:

1. Verify inbound record rate and successful processing rate.
2. Check whether the current limit is per-pod, per-thread, or global.
3. Check whether replica/concurrency changes distorted the aggregate quota.
4. Measure permit wait time and actual dependency latency.
5. Check whether the consumer has been paused too long or lacks a resume condition.
6. Check `max.poll.interval.ms` and `max.poll.records` if listeners are blocking.
7. Inspect per-partition lag to detect hot partitions.
8. Check retries and DLT; do not confuse permanent payload errors with overload.
9. Calculate backlog drain time from excess capacity and SLA/retention.
10. Adjust quotas or dependency capacity in a controlled manner.
11. If input must be reduced, coordinate with producers or upstream data architecture.
12. Record root cause, thresholds, and outcomes to update the runbook.

Never resolve lag by committing past skipped records, manually bumping offsets, or disabling validation. Those actions drop business work rather than fixing the root cause.

## 28. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Creating a new limiter per message | Quota resets, practically no limit | Use a properly scoped limiter bean |
| Treating `max.poll.records` as RPS | API quota still breached | Limit at the downstream callsite |
| Per-thread limit mistaken for per-pod | Total quota multiplied by concurrency | Use a shared limiter or define scope explicitly |
| Per-pod limit while forgetting autoscaling | Total quota grows with pods | Partition quota or use a distributed limiter |
| `acquire()` blocks too long | `max.poll.interval.ms` breached, rebalance | Lower poll size, use pause or another policy |
| Pausing with no resume signal | Consumer lag grows forever | Clear health probes/cooldowns/runbooks |
| Pausing to hide schema errors | Poison records never recover | Classify exceptions, use DLT |
| Acking right after `executor.submit()` | Offset commits before task finishes | Ack after durable completion |
| Unbounded async queue | OOM, crashes, backlog in RAM | Bounded queue and backpressure |
| Limiting only initial request, ignoring HTTP retries | Downstream quota breached | Place limiter close to every attempt |
| Measuring only lag without overload signals | Autoscale overloads dependency | Combine lag, latency, errors, and in-flight |
| Scaling consumers past partition count | No useful parallelism gain | Check the partition ceiling |
| Sending all 429s to DLT | Transient failures pushed to manual recovery | Bounded retries and incident-driven pause |
| Dropping idempotency because a limiter exists | Redeliveries create duplicates | Use `eventId`/unique keys/Inbox |

## 29. Production deployment checklist

Before enabling processing rate limits, verify:

- Is quota measured in records, API calls, DB transactions, or bytes?
- Does the limit apply per thread, per pod, per consumer group, or cluster-wide?
- Is it designed for autoscaling and concurrency changes?
- How long can the listener wait for a permit before affecting `max.poll.interval.ms`?
- Was `max.poll.records` chosen based on actual processing time?
- Are pause/resume used to respond to sustained overload?
- Are container-wide pause and `pausePartition` distinguished where needed?
- Are hysteresis/cooldowns and independent resume signals configured?
- Are concurrent requests and async queues bounded?
- Do retries consume quota and use jitter to prevent retry storms?
- Are offsets committed strictly after durable side effects?
- Are side effects idempotent upon record redelivery?
- Does a dashboard track rate, in-flight, 429s, latency, lag, and oldest age?
- Is Kafka retention sufficient for backlog during peak load/outages?
- Have pause/resume, restarts, rebalances, overload, and multi-pod quotas been tested?

## 30. Conclusion

**Processing rate limiting** in Spring Kafka must be designed at the exact resource boundary: records/second, requests/second, concurrent requests, or shared quotas. The Kafka consumer lets you tune poll size, concurrency, and pause/resume, yet these mechanisms do not automatically replace a rate limiter at the dependency callsite.

Under normal conditions, limiters and concurrency bounds protect downstream. Under clear overload, controlled pause/resume provides backpressure without intentionally leaving the consumer group. In all cases, protect offset commits, redelivery safety/idempotency, lag monitoring, and business wait tolerance. **A slow consumer that loses no data is usually safer than a very fast consumer that crashes its dependent systems; however, the throttled rate must still remain sustainable enough to meet SLAs and Kafka retention.**
