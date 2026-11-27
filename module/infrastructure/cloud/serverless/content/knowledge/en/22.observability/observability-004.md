# Measuring Cold Starts, Message Age, and Backlog

Serverless applications typically scale based on incoming requests or pending work. When traffic spikes suddenly, functions may need to initialize new execution environments. When consumers process slower than messages enter a queue, backlog grows and messages wait longer before being handled.

Three signals help detect these issues:

- **Cold start:** the time required to initialize a new execution environment or instance before the workload is ready to handle requests.
- **Message age:** the elapsed time a message has existed from publish/enqueue to a defined processing milestone.
- **Backlog:** the amount of pending or unacknowledged work.

These three metrics should not be viewed in isolation. Cold starts can slow consumers during scale-out. Rising backlog increases message age. Message age exceeding SLAs can cause business failures even while functions still return success. This lesson covers how to measure, analyze, and alert on these signals in Java serverless systems.

## 1. Viewing All Three Signals in the Same System

Suppose a Java function consumes an orders queue. During a traffic surge:

1. Producers send messages faster than consumers are currently processing them.
2. The platform increases the number of execution environments or instances.
3. New instances must initialize the JVM, framework, and dependencies.
4. During cold starts, processing capacity does not increase immediately.
5. Backlog and message age climb.
6. Once new instances become ready, throughput rises and backlog can decline.

~~~mermaid
flowchart TD
    P["Producer: message arrival rate increases"] --> Q["Queue"]
    Q --> B["Backlog grows"]
    B --> A["Autoscaler scales out consumers"]
    A --> C["Cold start: JVM and app initialization"]
    C --> W["Consumer capacity increases"]
    W --> D["Message processing / ack"]
    D --> R["Backlog shrinks if throughput > arrival rate"]
~~~

A dashboard showing only invocation counts and error rates can miss this scenario. Consumers still return 2xx or ack messages, yet messages wait far too long before being processed. Therefore, track wait times and pending work alongside initialization time.

## 2. Defining Cold Start

A cold start occurs when the platform must create a new execution environment or instance before processing a workload. For Java, this process can include:

- Provisioning or launching the runtime.
- Initializing the JVM.
- Loading classes and libraries.
- Running static initializers.
- Initializing the dependency injection container or framework.
- Reading configuration and secret references.
- Creating connection pools or clients.
- Running startup hooks and readiness checks.

Not every first invocation of a function is a cold start. The platform may reuse an already initialized execution environment across many subsequent invocations. Cold starts typically occur when a new environment is created due to scale-out, instance replacement, or no warm instance being available.

Cold start is part of the latency perceived by users or consumers, though measurement depends on the platform. AWS Lambda provides dedicated log/runtime signals for initialization; Cloud Run and Knative typically require combining instance startup logs, request latency, and application telemetry to analyze startup time.

### 2.1. Distinguishing Time Intervals

Do not collapse all latency into a single number. Time intervals may include:

| Interval | Meaning |
|---|---|
| Provisioning/scheduling | Platform allocates resources or schedules an instance |
| Image pull | Pulling the container image if the node does not have it cached |
| Runtime initialization | Initializing the runtime/JVM |
| Application initialization | Initializing framework, dependencies, and application |
| Request/handler duration | Time spent processing the invocation or request |
| Queue wait | Time a message waits before a consumer starts |
| End-to-end processing | From when a message is published until processing/ack completes |

Lambda's Duration metric generally reflects handler execution time; initialization information may be recorded separately. A Cloud Run request may include waiting for a new instance, yet exact init duration should not be inferred from request latency alone. Use platform logs/telemetry and custom startup timing to separate them.

## 3. Measuring Cold Starts on AWS Lambda

AWS Lambda writes invocation details to CloudWatch Logs. For execution environments that perform initialization, the report log may contain an Init Duration field. This field helps analyze initialization time separately from handler duration.

Illustrative report log example:

~~~text
REPORT RequestId: 8a1... Duration: 42.31 ms
Billed Duration: 120 ms Memory Size: 1024 MB
Max Memory Used: 188 MB Init Duration: 77.64 ms
~~~

Actual fields depend on the runtime, invocation type, and enabled features. Do not assume every invocation has Init Duration; reused environments may not run initialization during that invocation.

You can use CloudWatch Logs Insights to find reports with init duration:

~~~sql
filter @type = "REPORT"
| parse @message /Init Duration: (?<initMs>[0-9.]+) ms/
| filter ispresent(initMs)
| stats
    count() as coldStarts,
    avg(initMs) as avgInitMs,
    pct(initMs, 50) as p50InitMs,
    pct(initMs, 95) as p95InitMs,
    max(initMs) as maxInitMs
  by bin(5m)
~~~

This is an illustrative query for the corresponding log format. Verify the `@type` field, report contents, and Logs Insights syntax against your actual log group/runtime. If the log format changes, update the parser rather than interpreting empty results as zero cold starts.

### 3.1. Counting Cold Starts and Calculating Rate

You can calculate the cold start rate over a time window:

\[
\text{Cold start rate} =
\frac{\text{Observed initializations}}
{\text{Total invocations}}
\times 100\%
\]

The numerator definition must remain consistent. If counting via Init Duration reports, this represents log-observed initialization events, not necessarily a built-in standard metric across every runtime.

Monitor as well:

- Initializations per minute.
- Initialization-to-invocation ratio.
- p50/p95/p99 of init duration.
- p50/p95/p99 of handler duration.
- p50/p95/p99 of end-to-end latency.
- Instance/replica count and concurrency.
- Error or timeout rate on invocations that included init.

A high cold start rate is not automatically a problem. A batch workload may tolerate cold starts if its SLA is wide. What matters is actual latency, frequency, and impact on message age or request SLOs.

### 3.2. Lambda Telemetry API and Log-Based Metrics

The Lambda Telemetry API can deliver platform events related to runtime lifecycle and initialization to registered extensions. Extensions can use appropriate platform events to observe init and runtime lifecycles. This provides more granular metrics when needed, though extension overhead, buffering, and error handling must be managed.

A simpler option is creating metrics from logs containing Init Duration or using dashboards that query Logs Insights. Log-based metrics have different latency and limits compared to native platform metrics. Document the metric source and update interval on the dashboard.

Do not use a static `AtomicBoolean` in Java to conclude platform cold starts. That variable only knows whether this process has executed that code path; it does not accurately distinguish provider-managed lifecycles, snapshot restores, multiple classloaders, or runtime initialization behavior. Use platform signals for cold starts and custom timing for application initialization.

## 4. Measuring Cold Starts on Cloud Run and Knative

Cloud Run and Knative run containers, so you must observe instance lifecycle alongside application readiness time. Useful signals include:

- Instance/container startup and shutdown logs.
- Process start timestamp.
- Application initialization completion timestamp.
- Readiness probe success timestamp.
- First request on the instance.
- Request latency and concurrency.
- Instance count over time.
- Image pull/startup events if provided by the platform.

A Java application can log two distinct milestones: `app.initialization.started` and `app.ready`. The difference reflects in-process initialization. Time from request arrival to app readiness may also include scheduling, image pull, networking, and ingress queueing.

Example logging startup milestone in Java:

~~~java
import java.time.Duration;
import java.time.Instant;

public final class ApplicationStartup {

    private static final Instant PROCESS_STARTED = Instant.now();

    private ApplicationStartup() {
    }

    public static void markReady() {
        Instant readyAt = Instant.now();
        long initializationMs =
                Duration.between(PROCESS_STARTED, readyAt).toMillis();

        System.out.printf(
                "{\"event\":\"app.ready\",\"initialization_ms\":%d}%n",
                initializationMs);
    }
}
~~~

Call `markReady()` after required components are ready, such as after the Spring context finishes initializing and the server begins accepting requests. Calling it too early understates startup time. If startup includes lazy-loaded components, record their initialization time separately when first used.

### 4.1. Separating Application Startup from Request Latency

A first request may be slow due to cache misses or JIT compilation even when the process is already ready. Conversely, process startup may be fast while the first request is slow due to DNS, TLS, or database connection setup.

Therefore, measure separately:

- Process initialization duration.
- Framework/context ready duration.
- First request latency per instance.
- Warm request latency.
- Dependency connection/first-call latency.

Compare percentiles rather than averages alone. p95/p99 usually reflect the tail latency experienced by users.

## 5. Factors That Increase Java Cold Starts

| Factor | Impact | How to Measure/Inspect |
|---|---|---|
| Large container image | Increases pull and startup time | Image size, pull/start events |
| Many dependencies | Increases class loading and initialization | Startup profile, class loading |
| Framework scanning | Increases context creation time | Spring startup report or profiler |
| Heavy static initializers | Extends time before readiness | Component-level startup logs |
| Eager database connections | Waits on network/TLS and pool initialization | Connection latency, pool metrics |
| Loading config or secrets | Adds dependency calls to startup path | Secret/config request latency |
| Inadequate heap and CPU | Slow GC or initialization | CPU, memory, GC logs |
| JIT warm-up | First requests can be slower | Compare first request vs. warm requests |

Optimization measures should be driven by profiling. Moving all initialization to lazy loading may reduce startup time while making the first request slower. Increasing CPU can shorten init at higher cost. Keeping warm instances reduces cold starts but consumes compute during idle traffic.

### 5.1. Provisioned Concurrency, SnapStart, and Min Instances

Platforms offer different ways to reduce cold start impact:

- **AWS Lambda Provisioned Concurrency:** pre-initializes execution environments to serve invocations, in exchange for the cost of maintaining provisioned capacity.
- **AWS Lambda SnapStart:** takes a snapshot for supported Java runtimes/versions to reduce initialization time upon restore. Verify runtime compatibility and post-restore handling requirements for data/connections.
- **Cloud Run minimum instances:** keeps a minimum number of instances running, reducing scale-from-zero occurrences at a resource cost.
- **Knative min-scale:** maintains minimum replicas according to autoscaler configuration.

These features reduce wait time in certain phases without eliminating all latency. For example, requests can still be slow due to downstream services, DNS, databases, or traffic bursts exceeding pre-warmed capacity.

Do not use scheduled pings or keep-alives as a guarantee that instances stay ready. Platforms can recycle environments; only supported capacity configurations provide explicit readiness guarantees.

## 6. Defining Message Age

Message age is how long a message has existed from when the producer published/enqueued it until a specific measurement point.

There are at least two useful measurements:

\[
\text{Age at start} =
t_{\text{consumer start}} - t_{\text{published}}
\]

\[
\text{End-to-end age} =
t_{\text{processing complete}} - t_{\text{published}}
\]

- Age at start shows how long the message waited before a consumer started processing it.
- End-to-end age shows how long the message took to travel from the producer to completed processing.

If you need to measure processing time separately:

\[
\text{Processing duration} =
t_{\text{processing complete}} - t_{\text{consumer start}}
\]

These three metrics help distinguish rising queue wait time from slower handler processing.

### 6.1. Using a Trusted Source Timestamp

The publish timestamp should be generated by the producer or taken from broker metadata. Consumers must parse timestamps in UTC and document units explicitly. Do not use the consumer's message receipt time as the publish time, as age would always appear near zero.

Clocks between producer and consumer can drift. To reduce error:

- Synchronize runtime clocks using the platform's time service.
- Use broker-assigned timestamps when available.
- Track clock skew when age is negative or anomalous.
- Standardize on UTC everywhere.
- Do not convert timestamps to local timezones before computing duration.

If the broker exposes an oldest message age metric, use it to observe overall queue health and use custom consumer age metrics to observe messages actually being processed. The two metrics can differ due to sampling timing, semantics, and update lag.

## 7. What Is a Backlog Metric?

Backlog represents the amount of unfinished work at a point in time. You must understand each messaging system's states so you do not miscount.

A queue may contain:

- **Visible/ready:** messages waiting for a consumer to receive.
- **In-flight/invisible:** messages already received but not yet acked/deleted, or whose lease has not expired.
- **Delayed/scheduled:** messages not yet eligible for delivery.
- **Dead-letter:** messages moved to a failure queue after retry limits or policy rules.
- **Acknowledged/completed:** messages confirmed as successfully processed.

In some systems, the primary backlog metric counts only undelivered messages; in others, it may include unacked/in-flight messages. Read the metric provider's definition before summing or comparing.

Backlog count is only a quantity. A queue with 10,000 tiny messages might drain faster than a queue with 100 messages where each requires multiple API calls. Combine count with message age, processing duration, and throughput to understand true impact.

## 8. Measuring Backlog by Platform

Metric names and semantics differ across brokers. Examples:

| Platform | Commonly Used Metric | Meaning to Monitor |
|---|---|---|
| Amazon SQS | ApproximateNumberOfMessagesVisible | Messages waiting to be received |
| Amazon SQS | ApproximateNumberOfMessagesNotVisible | Messages currently in-flight/not visible |
| Amazon SQS | ApproximateAgeOfOldestMessage | Approximate age of oldest message per SQS semantics |
| Google Pub/Sub | subscription/num_undelivered_messages | Undelivered/unacknowledged messages per subscription metric |
| Google Pub/Sub | subscription/oldest_unacked_message_age | Age of the oldest unacknowledged message |
| Kafka | Consumer group lag / records-lag-max | Offset difference between consumer and log end offset |
| Azure Service Bus | Active messages, Dead-lettered messages | Active and dead-lettered message counts in the entity |

Exact names, units, sampling, and availability can vary by service/region/metric version. Check CloudWatch, Cloud Monitoring, Azure Monitor, or the Kafka exporter in use.

### 8.1. Amazon SQS

With SQS, monitor these together:

- ApproximateNumberOfMessagesVisible: volume of messages ready to be received.
- ApproximateNumberOfMessagesNotVisible: volume of messages received but not yet deleted/acked.
- ApproximateAgeOfOldestMessage: approximate age of the oldest message.
- NumberOfMessagesSent, NumberOfMessagesReceived, NumberOfMessagesDeleted: publish, receive, and delete trends.

SQS metrics are approximate and updated periodically; do not use a single data point to deduce the exact number of messages in the queue at any millisecond. Track trends over multiple periods and cross-reference with custom processing metrics.

With standard queues, a message can be received again if the visibility timeout expires before the consumer deletes it. This increases receive counts and can cause duplicate processing. Monitor receive counts, retries, and DLQs alongside backlog.

### 8.2. Google Pub/Sub

With Pub/Sub, subscription metrics help monitor unacknowledged message volume and the age of the oldest unacked message. If consumers ack slowly, oldest unacked age can rise even while new messages are still being processed.

Monitor ack throughput, delivery throughput, outstanding messages, and retries/dead-letters. If a subscription uses ordering keys or flow control, a blocked group of messages can cause partial backlog growth even when overall consumers have spare capacity.

### 8.3. Kafka

Kafka consumer lag is typically the offset difference between log end and the consumer group's committed offset. This is a record/offset lag count, not directly an age in seconds.

A low-throughput topic can have small lag while messages have still waited a long time. Conversely, a high-throughput topic can have large lag while age remains within SLA. Combine consumer lag with record timestamps and processing latency to evaluate real delay.

## 9. Arrival Rate, Processing Rate, and Drain Time

Two critical rates:

- **Arrival rate (\(\lambda\)):** messages arriving per second.
- **Processing/ack rate (\(\mu\)):** messages processed and acknowledged per second.

If \(\mu > \lambda\), consumers have spare capacity to drain the backlog. If \(\mu = \lambda\), the existing backlog barely shrinks. If \(\mu < \lambda\), the backlog continues to grow.

Given current backlog \(B\), assuming arrival and processing rates remain relatively stable, the estimated time to drain the backlog is:

\[
T_{\text{drain}} \approx \frac{B}{\mu-\lambda}
\quad \text{when } \mu > \lambda
\]

For example, a queue has 12,000 messages, consumers process 500 messages/second, and producers continue sending 200 messages/second:

\[
T_{\text{drain}} \approx \frac{12,000}{500-200}=40 \text{ seconds}
\]

If producers stop sending, the ideal time is \(B/\mu\). The formula is only an estimate; actual throughput varies with batch size, message complexity, retries, scaling, throttling, and downstream limits.

### 9.1. Estimating Capacity from Concurrency

If each instance handles up to \(c\) concurrent executions, average processing time per message is \(d\) seconds, and each batch processes \(b\) messages, approximate ideal throughput is:

\[
\mu \approx \frac{c \times b}{d}
\]

This is a simplified model. Batch processing may run sequentially or in parallel; concurrency may be constrained by thread pools, CPU, memory, database connections, or the broker. Use throughput measured in production-like load tests for capacity planning.

Do not increase concurrency indefinitely just to shrink backlog. If every message calls a database, excessive concurrency can overload the database, increasing latency and retries and reducing net throughput.

## 10. Measuring Message Age in a Java Consumer

A Java consumer should record at least:

- Processing start timestamp.
- Publish/enqueue timestamp.
- Message age at start.
- Processing duration.
- Outcome: success, retryable failure, or permanent failure.
- Batch size if receiving in batches.
- Consumer/service version and queue name.

Example using Micrometer to record age and processing duration. `publishedAt` is obtained from trusted message metadata:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.time.Instant;

public final class MessageMetrics {

    private final MeterRegistry registry;
    private final Timer processingTimer;
    private final DistributionSummary ageSummary;

    public MessageMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.processingTimer = Timer.builder("serverless.message.processing")
                .description("Time spent processing a message")
                .tag("queue", "orders")
                .tag("consumer", "orders-worker")
                .register(registry);

        this.ageSummary = DistributionSummary
                .builder("serverless.message.age")
                .baseUnit("milliseconds")
                .description("Message age when processing starts")
                .tag("queue", "orders")
                .tag("consumer", "orders-worker")
                .register(registry);
    }

    public Timer.Sample start(Instant publishedAt) {
        Instant startedAt = Instant.now();
        long ageMs = Duration.between(publishedAt, startedAt).toMillis();

        if (ageMs >= 0) {
            ageSummary.record(ageMs);
        } else {
            registry.counter(
                    "serverless.message.clock_skew",
                    "queue", "orders",
                    "consumer", "orders-worker"
            ).increment();
        }

        return Timer.start(registry);
    }

    public void stop(Timer.Sample sample) {
        sample.stop(processingTimer);
    }
}
~~~

In production code, start `Timer.Sample` right before processing and call `stop` in `finally` to record both success and failure cases. Outcome can be recorded with a separate Counter using a fixed set of values such as `success`, `retryable_error`, `permanent_error`.

Do not put `messageId`, `orderId`, `customerId`, trace ID, or exception messages into metric tags. These values have high cardinality; record them in controlled logs or traces instead.

### 10.1. Measuring End-to-End Age

If you need to measure up to when the message is acked or processing finishes, record the completion timestamp as well:

~~~java
Instant completedAt = Instant.now();
long endToEndAgeMs =
        Duration.between(publishedAt, completedAt).toMillis();
~~~

If acking happens asynchronously after the handler returns, the completion timestamp in code may not equal when the broker confirms the ack. When strict SLA measurement up to ack is needed, measure where ack/delete succeeds or use broker telemetry.

For batches, record age for each message or sample distribution per batch in a controlled way. Recording only the first message's timestamp in a batch fails to reflect the true age of all messages.

## 11. Backlog Age and Backlog Count Must Be Read Together

Typical scenarios:

| Backlog Count | Oldest Message Age | Interpretation |
|---|---|---|
| Low | Low | Queue is healthy |
| High | Low | Producers just sent a burst; consumers may be keeping up |
| High | High | Consumers lack capacity, are failing, or a dependency is slow |
| Low | High | Possible poison message, blocked partition/group, or very low traffic with one stuck old message |
| Decreasing | Still high | Queue is draining, but old messages have not finished clearing |
| Unchanged | Increasing | Arrival and processing may be balanced at a high backlog, or consumers are stalled |

Oldest age is often closer to business experience than backlog count alone. However, if you only watch age, a large burst of new messages might be missed before old messages cross the threshold. Combine age, count, throughput, and retries/DLQ.

With Kafka, lag count should accompany record age. With SQS/Pub/Sub, use broker-defined oldest message age alongside custom consumer age for cross-checking.

## 12. Dashboard for Observing Cold Starts and Queues

A useful dashboard can be organized into four groups:

**Startup and latency**

- Init duration p50/p95/p99.
- Cold start count/rate.
- Application initialization duration.
- First request latency and warm request latency.
- Handler/processing duration.

**Queue health**

- Visible/ready backlog.
- In-flight/unacked messages.
- Oldest message age.
- Dead-letter count.
- Retry/receive count.

**Capacity and throughput**

- Arrival rate.
- Processing/ack rate.
- Active instances/replicas.
- Concurrency and batch size.
- Estimated drain time.
- CPU, memory, connection pool, and throttling.

**Business SLO**

- Percentage of messages processed before deadline.
- p95/p99 end-to-end age.
- Number of messages breaching SLA.
- Number of delayed orders/jobs.
- Number of compensations or manual recoveries caused by late processing.

Place these charts on the same timeline to visualize correlations: instance count rises, cold starts increase, processing rate shifts, and backlog age responds.

## 13. SLO-Based Alerting

Do not use one fixed threshold for every queue. An email-sending queue may tolerate several minutes of age; an inventory update or payment event queue may require a much tighter SLA.

Illustrative policy examples:

| Signal | Alert Condition |
|---|---|
| Oldest message age | Exceeds 70% of business processing deadline over multiple periods |
| Backlog | Growing continuously while processing rate is below arrival rate |
| Drain time | Estimate exceeds remaining time before SLA deadline |
| DLQ | New messages arrive or count is rising |
| Cold start | p95 init duration rises while p95 request/message latency breaches SLO |
| Consumer errors | Sudden spike in retries, timeouts, or throttling |
| Capacity | Max concurrency/instance cap reached while backlog keeps growing |

Use warning and critical thresholds. Multi-period or time-window alerts prevent paging on single noisy metric points. For DLQs, a single message may be severe enough to alert immediately depending on business requirements.

Alerts should specify the queue, consumer, environment, region, metric, duration over threshold, and runbook. Do not include message IDs or sensitive data in alert notifications unless necessary.

### 13.1. Calculating On-Time Processing Ratio

An SLI can be the percentage of messages processed within deadline D:

\[
\text{On-time processing ratio} =
\frac{\text{Messages with end-to-end age} \leq D}
{\text{Total processed messages}}
\times 100\%
\]

Clearly define the denominator: messages completed in the window, messages received, or messages published. If only completed messages are counted, an unprocessed backlog may be excluded and make the SLI look artificially healthy. Also track pending messages that have already exceeded or are about to exceed the deadline.

## 14. Investigating Rising Backlog

When backlog increases, check in order:

1. **Arrival rate:** are producers sending more than usual?
2. **Processing rate:** did messages processed/acked per second drop?
3. **Consumer capacity:** have instance count, concurrency, and batch size hit limits?
4. **Cold starts:** is scale-out slowed by image pulls, JVM startup, or initialization?
5. **Processing duration:** are individual messages slower due to code or dependencies?
6. **Errors/retries:** are messages retrying repeatedly or hitting visibility timeouts?
7. **Downstream limits:** are databases, APIs, or connection pools throttling?
8. **Poison messages:** is one bad message blocking a partition, message group, or retry loop?
9. **DLQ:** are messages moving to the DLQ and disappearing from source queue metrics?
10. **Configuration:** are timeouts, visibility/ack deadlines, max concurrency, and batch sizes reasonable?

Do not solve every backlog by raising concurrency. If processing rate is low because of database throttling, adding consumers further overloads downstream systems. Identify the bottleneck first.

### 14.1. Analysis Example

Suppose the dashboard shows:

- Arrival rate: 800 messages/second.
- Processing/ack rate: 500 messages/second.
- Backlog: grew by 18,000 messages in one minute.
- Oldest message age: rose from 8 to 55 seconds.
- Consumer instances: hit max scale.
- Database p95 latency: tripled.

These signals show capacity is below arrival rate and the downstream database is likely the bottleneck. Raising max scale immediately could overwhelm the database. Inspect connection pools, query latency, batch sizes, and safe concurrency levels before increasing consumer capacity.

If arrival rate returns to 300 messages/second and processing rate holds at 500 messages/second, the 18,000-message backlog has an estimated drain time of:

\[
T_{\text{drain}} \approx \frac{18,000}{500-300}=90 \text{ seconds}
\]

Watch age during the drain to confirm old messages are being processed and the SLA recovers.

## 15. Investigating Rising Cold Starts

If cold starts rise alongside latency, check:

- Was there a traffic burst or unusual scale-out?
- Did min instances/provisioned concurrency change?
- Was a new image deployed or did image size increase?
- Did a framework or dependency add a startup hook?
- Are JVM heap/CPU constrained?
- Are secrets/configs/database connections loaded synchronously at startup?
- Is a node/region short on capacity or missing image caches?
- Did the runtime version or snapshot configuration change?

Compare the current revision against the previous revision under the same traffic profile. A deployment might barely change average latency while sharply increasing p99 due to a longer init path.

Do not compare only absolute cold start counts. When invocations increase tenfold, cold start count can rise even as the cold start rate drops. Use both count and rate.

## 16. Visibility Timeout, Ack Deadline, and Retries

Queue consumers need time to process a message and then acknowledge completion. If the lease/visibility/ack deadline is too short, the broker may redeliver the message while the original worker is still processing it. This creates duplicates and inflates backlog/in-flight counts.

If the deadline is too long, a stuck message takes much longer to be redelivered after a worker crashes.

Check:

- p95/p99 processing duration.
- Handler and downstream call timeouts.
- Visibility timeout or ack deadline.
- Heartbeat/lease extension if available.
- Delivery/receive counts.
- Retry backoff and DLQ policy.
- Side-effect idempotency.

Visibility/ack timeouts should include a safety margin over expected processing time and be extended appropriately for long workloads. Do not simply set huge timeouts; long timeouts slow recovery when a consumer dies.

With SQS Lambda event source mappings, batch size, maximum batching window, and visibility timeout must be coordinated per service guidelines. With Pub/Sub, ack deadlines and ack extensions must match processing time. With Kafka, offset commits and consumer rebalancing follow different semantics; do not apply queue visibility timeout assumptions to Kafka.

## 17. Batch Size and Partial Failures

Batching can boost throughput and lower overhead, but a single failing message can impact the entire batch if the consumer does not support partial batch responses or classify errors properly.

Monitor:

- Actual batch size.
- Batch processing duration.
- Succeeded/failed messages per batch.
- Batch retry rate.
- Age of the oldest message in the batch.
- Poison or DLQ-routed records.

With AWS Lambda event source mappings, some sources support partial batch responses so only failed records are retried. Configure the response format per event source. With Kafka or other brokers, commit/ack mechanisms have their own rules.

Do not measure only a single processing duration for the batch while ignoring per-record message age. A batch can mix fresh and old messages; SLOs should reflect the longest-waiting record or an appropriate age distribution.

## 18. OpenTelemetry and Metric Cardinality

Telemetry can be standardized by service name, service version, environment, queue/consumer, and region. Key metrics include:

~~~text
serverless.cold_start.count
serverless.initialization.duration
serverless.message.age
serverless.message.processing
serverless.message.processed
serverless.message.failed
serverless.queue.backlog
serverless.queue.oldest_message_age
serverless.queue.arrival_rate
serverless.queue.ack_rate
serverless.queue.drain_time
~~~

These are suggested metric names; naming conventions, units, and instrument types must be standardized across the system. Use histograms/distributions for duration and age; counters for message and error counts; gauges for backlog/current concurrency; rates computed from counters in the metrics backend.

Keep metric attributes low-cardinality:

~~~text
service.name=orders-worker
deployment.environment.name=production
messaging.destination.name=orders
messaging.operation=process
cloud.region=asia-southeast1
outcome=success
~~~

Do not attach `message.id`, `order.id`, `customer.id`, `execution.arn`, or exception text to metric labels. Put identifying values in logs or traces when needed for investigation.

## 19. Testing and Benchmarking

Test both startup and queue behavior in a production-like environment:

1. Send a request/message when no instances are warm to observe a cold start.
2. Send a burst to trigger scale-out.
3. Compare warm and cold latencies.
4. Gradually increase arrival rate to find sustainable throughput limits.
5. Build up a large backlog and measure drain time.
6. Slow down a database/API to observe backpressure and alerts.
7. Inject failing messages to test retries, poison messages, and DLQs.
8. Terminate a consumer while messages are in-flight to verify redelivery.
9. Test ack/visibility timeouts with processing near the deadline.
10. Deploy a new revision and compare init duration.
11. Verify dashboards distinguish visible, in-flight, and DLQ counts.
12. Confirm alerts fire when age or drain time breaches SLO.

Do not run load tests against production queues containing customer data or real side effects. Use dedicated sandbox queues, databases, and providers. Set cost caps and clean up after testing.

## 20. Runbook for Message Age Exceeding SLA

When oldest message age crosses the critical threshold:

1. Identify the affected queue, subscription, or consumer group.
2. Compare arrival rate with processing/ack rate.
3. Inspect backlog count, in-flight count, and DLQ depth.
4. Check consumer instance count, max scale, and concurrency.
5. Review cold starts and initialization duration since the latest deployment.
6. Check processing duration, timeouts, retries, and downstream latency.
7. If a dependency is overloaded, reduce or cap concurrency to protect it.
8. If consumers have spare capacity and dependencies are healthy, increase capacity in a controlled manner.
9. Handle poison messages or blocked partitions according to DLQ/replay policy.
10. Monitor drain time and oldest age until back within SLO.
11. Save execution/message correlation IDs for post-incident review.

When replaying a DLQ, preserve idempotency keys or business identities so duplicate side effects are not created. Never delete failed messages just to turn a dashboard green; document discard/replay decisions and reasons.

## 21. Observability Design Process for Java Serverless

1. **Define SLOs.** Determine the maximum allowed time from publish to completed processing.
2. **Select platform metrics.** Use available init duration, instance count, queue age, and backlog metrics.
3. **Add custom timing.** Measure application startup, message age, and processing duration.
4. **Measure throughput.** Calculate arrival rate, processing/ack rate, and drain time.
5. **Separate queue states.** Distinguish ready, in-flight/unacked, delayed, and DLQ.
6. **Standardize telemetry.** Use stable service/environment/queue attributes.
7. **Design dashboards.** Show startup, latency, backlog, throughput, errors, and SLOs on a shared timeline.
8. **Set deadline-driven alerts.** Alert early before messages breach SLA, and alert on DLQ by risk level.
9. **Test failure modes.** Bursts, cold starts, dependency slowdowns, retries, and consumer crashes.
10. **Write runbooks.** Guide operators on identifying bottlenecks and safely draining backlogs.

Cold starts reveal compute initialization overhead; message age shows how long work has waited; backlog shows how much work remains unfinished. Measuring all three alongside arrival rate, processing rate, and downstream health lets operations teams distinguish scale-up delays, consumer capacity shortfalls, and dependency issues, and choose the right recovery action.

## 22. Self-Check Questions

- How does a cold start differ from a warm invocation?
- Why can't a static variable in Java accurately measure all cold starts?
- Where does AWS Lambda record initialization duration?
- Which milestones do Cloud Run/Knative need to separate process startup from first request latency?
- How does message age at start differ from end-to-end age?
- Why must a trusted publish timestamp be used?
- How does visible backlog differ from in-flight/unacked messages?
- How do SQS, Pub/Sub, and Kafka represent backlog/lag differently?
- What happens when processing rate is lower than arrival rate?
- What assumptions does the drain time formula make?
- Why can increasing concurrency make a backlog worse?
- What problems do overly short visibility timeouts or ack deadlines cause?
- Why must DLQs be monitored alongside source queues?
- Which metric is best suited for alerting close to a message processing SLO?
- Why should message IDs or trace IDs not be put into metric labels?

