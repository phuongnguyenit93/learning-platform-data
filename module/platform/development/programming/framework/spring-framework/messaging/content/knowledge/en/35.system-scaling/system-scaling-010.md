# Capacity Assessment Using Realistic Workloads, p95/p99, and Fault Injection

## 1. Goal: Measuring the System Under Production-Like Operation

A Spring Messaging application may run smoothly with only a few clients, yet slow down or destabilize as connection counts, subscriptions, and messages grow. To assess true capacity, generate workloads resembling how users and services actually interact, measure latency across layers, locate saturation points, and test behavior when a component fails.

A valuable test result must answer:

- How many messages or requests per second can the system sustain while still meeting SLOs?
- What are typical latency and tail latency?
- How do p95 and p99 change as load increases?
- Where does the bottleneck sit: in the Spring application, message broker, database, network, or consumers?
- When a dependency slows down, disconnects, or restarts, does the system apply backpressure, recover, and avoid message loss/duplication?
- Once an incident ends, how long does it take to drain the accumulated backlog?

**Capacity** is not merely the maximum request rate before the server crashes. It is the load level that can be sustained over time while latency, error rate, message loss, queue growth, and resource usage remain within acceptable bounds.

## 2. Metrics to Measure

Do not evaluate a system by a single throughput or CPU number. Observe the following metric groups together.

| Group | Metrics | Meaning |
| --- | --- | --- |
| Inbound load | Offered rate, request/message rate | Number of requests generated per second. |
| Accepted load | Accepted rate, rejected rate | Requests admitted by the server or broker versus rejected. |
| Outcomes | Completed/acknowledged rate, error rate | Requests completed or confirmed; failure rate. |
| Latency | p50, p95, p99, max | Distribution of elapsed time from send to response or ACK. |
| Connections | Active connections, sessions, streams | Number of open WebSocket/RSocket connections and active streams. |
| Subscriptions | Subscription count, fan-out | Number of subscriptions and how many consumers receive a published message. |
| Queues | Queue depth, oldest message age, consumer lag | Backlog size, age of oldest queued message, and consumer processing lag. |
| Data | Payload size, bytes/s | Size and volume of transmitted data. |
| Resources | CPU, heap, GC, threads, network, file descriptors | Process utilization and saturation status. |
| Dependencies | DB pool, query latency, broker connections | Responsiveness of downstream components. |

### 2.1. Measuring Latency Correctly

For a request-response interaction, end-to-end latency is usually measured from when the client sends the request until the client receives the complete response. For asynchronous messaging, define exact start and end boundaries:

- Publish latency: from producer send until broker confirms receipt.
- Queue latency: from broker receipt until consumer begins processing.
- Processing latency: time the consumer spends executing logic.
- Delivery latency: from publish until consumer receives the message.
- End-to-end business latency: from user action until the business result becomes usable.

Do not add metrics that do not share the same time boundaries or correlation ID. When total latency is needed, measure directly at the client and use traces/spans to break down time per hop.

### 2.2. Throughput Must Be Measured by Outcomes

Distinguish:

- **Offered throughput:** rate the load generator attempts to send.
- **Accepted throughput:** rate the system admits requests.
- **Completed throughput:** rate requests finish successfully.
- **Acknowledged throughput:** rate consumers acknowledge messages, if the protocol and broker support ACKs.

A system can accept 10,000 messages/second while processing only 7,000 messages/second. In that case, the backlog grows by roughly 3,000 messages every second. Looking only at sent or accepted counts overestimates capacity.

Error rates should separate timeouts, rejections, conversion errors, disconnects, broker errors, and business errors. Do not lump everything into one bucket when diagnosing root causes.

## 3. Understanding p50, p95, and p99 Properly

Percentiles describe positions in the latency distribution after sorting samples in ascending order.

- **p50 (median):** 50% of requests have latency less than or equal to this value.
- **p95:** 95% of requests complete at or below this value; the remaining 5% are slower.
- **p99:** 99% of requests complete at or below this value; the remaining 1% are slower.

Example:

| Metric | Latency |
| --- | ---: |
| p50 | 35 ms |
| p95 | 180 ms |
| p99 | 850 ms |

Most requests finish quickly, yet a small fraction take nearly a second. Reporting only a 60 ms average hides tail latency problems.

### 3.1. Computing Percentiles via Nearest-Rank

A simple illustration is nearest-rank. Given `n` sorted samples, the position for quantile `q` is:

\[
rank = \lceil q \times n \rceil
\]

Positions are 1-indexed. This is an illustrative method; statistical tools and histograms may use different interpolation schemes. When comparing results across tools, use the same definition or document the calculation method.

Java 17+ example:

~~~java
import java.util.Arrays;

public class PercentileDemo {

    static long percentile(long[] sorted, double q) {
        if (sorted.length == 0 || q <= 0 || q > 1) {
            throw new IllegalArgumentException("Invalid input");
        }
        int rank = (int) Math.ceil(q * sorted.length);
        return sorted[rank - 1];
    }

    public static void main(String[] args) {
        long[] latencyMillis = {8, 10, 11, 12, 13, 14, 15, 18, 25, 80};
        Arrays.sort(latencyMillis);

        System.out.println("p50=" + percentile(latencyMillis, 0.50) + " ms");
        System.out.println("p95=" + percentile(latencyMillis, 0.95) + " ms");
        System.out.println("p99=" + percentile(latencyMillis, 0.99) + " ms");
    }
}
~~~

Save the file as `PercentileDemo.java` and run:

~~~bash
javac PercentileDemo.java
java PercentileDemo
~~~

Stdout:

~~~text
p50=13 ms
p95=80 ms
p99=80 ms
~~~

With only 10 samples, p95 and p99 both equal the maximum value. That does not mean tail latency was measured accurately; it shows a small sample size is insufficient to characterize the tail. With 100,000 requests, p99 represents roughly the slowest 1,000 requests, providing far richer data for analysis.

### 3.2. Why Does p99 Matter?

Tail latency can degrade user experience even when the median looks great. Common causes include:

- Requests waiting on a connection pool or thread pool.
- Garbage collection pauses.
- Database queries hitting slow execution plans.
- Broker queues building up or consumers falling behind.
- Certain messages having large payloads or fanning out to many subscribers.
- Retries and timeouts adding extra load.
- Network congestion or a single overloaded node.

p95 is good for seeing the experience of the vast majority of requests; p99 is useful when controlling very slow outliers matters. Do not pick higher percentiles merely for false precision: p99.9 requires large sample sizes and appropriate histogram collection.

### 3.3. Avoiding Percentile Aggregation Mistakes

Never average p95 across multiple instances to produce a cluster-wide p95. Percentiles do not add linearly. An instance with few requests and an instance with many requests must contribute in proportion to their actual sample counts.

A better approach is collecting mergeable histogram buckets, summing counts per bucket across instances, and computing quantiles on the merged distribution.

Also avoid:

- Mixing successful requests while excluding timed-out requests from samples.
- Measuring only fast requests and dropping failed requests.
- Computing percentiles over overly short windows or too few samples.
- Using overly coarse histogram buckets that poorly estimate p99.
- Comparing p99 across runs with different workloads or sample sizes.

## 4. Designing Realistic Workloads

Load generators must simulate real user and producer behavior, not just loop a tiny message at a constant rate.

Before running tests, gather or estimate these characteristics:

1. Concurrent client count and new connection creation rate.
2. Subscriptions per session.
3. Mix of request-response, request-stream, request-channel, or publish/subscribe.
4. Realistic payload size distribution: small, medium, and large.
5. Share of messages fanning out to 1, 10, 100, or more subscribers.
6. Message rate over time, including peak hours and bursts.
7. Session lifetimes, reconnects, and heartbeats.
8. Error, retry, duplicate, and rejection rates.
9. Consumer behavior: fast processing, slow processing, pauses, ACK, or NACK.
10. Frequency of database and external service calls inside handlers.

Use synthetic data with distributions close to real data. Never put personal data, tokens, credentials, or sensitive payloads into load tests. When masking or synthesizing payloads, keep sizes and structures realistic so serialization and network costs are not underestimated.

### 4.1. Open Workload vs. Closed Workload

The two load-generation models behave differently.

**Open model** issues requests at a predetermined arrival rate—such as 200 requests/second—regardless of whether the system responds quickly or slowly. This fits modeling external event streams or scheduled producers.

**Closed model** maintains a fixed number of virtual users. Each user sends a request, waits for the response, and then sends the next. When the system slows down, each user generates fewer requests. Consequently, a closed model can throttle its own offered load while the system saturates, masking problems.

| Characteristic | Open Model | Closed Model |
| --- | --- | --- |
| Control | Arrival rate | User count / concurrency |
| When server slows down | Keeps attempting target send rate | Send rate drops with response wait time |
| Best suited for | Event streams, producers, fixed traffic rates | Interactive sessions with think time |
| Risk | Can build huge backlogs if server falls behind | Can hide overload and cause coordinated omission |

Pick the model matching the real workload. Messaging systems often require both: producers generating load at an arrival rate and consumers/sessions maintaining steady connection or subscription counts.

### 4.2. Little's Law: Linking Throughput, Latency, and Concurrency

For a stable system, Little's Law states:

\[
L = \lambda \times W
\]

Where:

- L is the average number of requests in the system.
- λ is average throughput (requests/second).
- W is average time spent in the system (seconds).

Example: 200 requests/second with a 0.25-second average processing time corresponds to roughly 50 requests currently executing or waiting in the system. When latency rises, concurrency and in-flight requests also grow if arrival rate stays constant.

Do not plug p99 into W as though p99 were average latency. Apply Little's Law using averages over the same measurement scope.

## 5. Types of Load Tests

No single run is enough to declare capacity. Each test type answers a different question.

| Test Type | How It Runs | Question Answered |
| --- | --- | --- |
| Baseline | Low, steady load | What are latency and resource usage when the system is healthy? |
| Load test | Ramp up to expected production load | Does the system meet SLOs at target load? |
| Stress test | Push beyond target load | What are the saturation point and failure modes? |
| Spike test | Sudden load surge | How does the system absorb bursts and scale? |
| Soak test | Sustain load for a long duration | Are there memory leaks, queue growth, or degradation over time? |
| Capacity test | Step up load incrementally | What is the highest throughput still meeting SLOs? |
| Resilience test | Inject faults while under load | Does the system stay available and recover properly? |

A test cycle should include:

1. **Warm-up:** let the JVM, JIT, connection pools, and caches stabilize.
2. **Ramp-up:** increase load in steps to avoid an unintended spike.
3. **Steady state:** hold target load long enough for meaningful samples.
4. **Ramp-down:** reduce load smoothly.
5. **Recovery observation:** keep observing until queues, threads, and resources return to normal.

Do not use warm-up measurements to evaluate steady-state SLOs. At the same time, do not ignore cold starts if production receives immediate traffic right after deployment or restart; test that as its own scenario.

## 6. Spring Messaging-Specific Scenarios

Messaging workloads involve factors absent from simple HTTP request tests.

### 6.1. WebSocket and STOMP

For STOMP-over-WebSocket, measure:

- Concurrent WebSocket connections and connection churn.
- Handshake and STOMP `CONNECT` times.
- Subscriptions per session.
- Published messages per second and payload sizes.
- Fan-out: how many subscribers receive each message.
- Time from `SEND` to `MESSAGE` receipt.
- Heartbeats, disconnects, reconnects, and session cleanup.
- Slow consumers, outbound buffers, and queue accumulation.

If production uses a broker relay such as RabbitMQ or ActiveMQ, run load tests with the real broker. The in-memory simple broker is helpful for functional tests but does not represent production broker throughput, persistence, clustering, ACK/NACK, or limits.

Fan-out changes total work dramatically. For example, 1,000 messages/second with 100 subscribers each can produce roughly 100,000 deliveries/second. A modest producer rate does not mean the broker and outbound path are lightly loaded.

### 6.2. RSocket

For RSocket, separate connections, streams, and payloads:

- Request-Response: measure per-request latency and concurrent requests.
- Request-Stream: measure active streams, demand, emission rate, and cancellations.
- Request-Channel: measure both directions, backpressure, and completion times.
- Fire-and-Forget: measure receipt, processing, and business-level confirmation rates; do not infer completion merely from sending a frame.
- Measure payload sizes, serialization, reconnects, and per-stream errors.

Backpressure can throttle emission rate, yet the whole pipeline must be verified. If a consumer slows down, does the publisher honor `request(n)` or keep pushing items into an unbounded queue? When a stream is cancelled, are upstream resources freed?

### 6.3. Message Channels and Executors in Spring

Monitor the executors serving inbound, outbound, and broker channels if configured by the application. Useful metrics include active threads, pool size, queue size, task rejections, and queue wait times.

A thread pool with an unbounded queue can make the system look healthy at first: requests are accepted yet wait a long time before executing. Continuously growing queues indicate offered rate exceeds completed rate. Consider bounded queues, explicit rejection policies, and protocol-appropriate backpressure.

## 7. Measuring in Spring with Micrometer

Micrometer provides `Timer` to measure duration and invocation counts. In Spring Boot applications, Actuator can export metrics to a configured registry such as Prometheus.

A `Timer` for message processing duration:

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class MessagingMetrics {

    private final MeterRegistry registry;
    private final Timer handlerTimer;

    public MessagingMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.handlerTimer = Timer.builder("messaging.handler.duration")
            .description("Time from handler subscription to termination")
            .tag("interaction", "request-response")
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofMillis(25),
                Duration.ofMillis(50),
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofMillis(500),
                Duration.ofSeconds(1)
            )
            .register(registry);
    }

    public Timer handlerTimer() {
        return handlerTimer;
    }
}
~~~

For reactive publishers, measure from subscription until the publisher completes, errors, or cancels. Do not measure only `Mono`/`Flux` construction time because actual work often starts only upon subscription.

Example:

~~~java
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

public Mono<Reply> handle(Command command) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        return Mono.defer(() -> service.process(command))
            .doFinally(signal -> sample.stop(handlerTimer));
    });
}
~~~

This timer measures handler publisher duration up to the terminal signal. If the subscriber cancels, the timer also stops at cancellation; it does not prove detached background work or underlying resources stopped. Measure worker and queue execution times separately if they have independent lifecycles.

Maintain separate counters for outcomes such as `success`, `error`, `timeout`, `cancel`, and `rejected`. Use bounded, consistent tag values so dashboards can compare across instances.

### 7.1. Histograms and Percentiles

There are two common ways to export percentiles:

- **Client-side percentiles:** the registry computes p95/p99 per instance. Useful for a single instance, but cannot be summed or averaged to produce cluster-wide percentiles.
- **Histogram buckets:** exports sample counts across latency buckets. The backend can aggregate buckets across instances and then estimate quantiles.

With Prometheus, a `Timer` with histograms produces bucket series. Example p99 query:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(messaging_handler_duration_seconds_bucket[5m])
  )
)
~~~

Actual metric names depend on the registry and naming conventions. Verify exported series before putting queries into dashboards. A histogram quantile is a bucket-based estimate, not an exact per-request percentile.

When using Prometheus, include the appropriate registry dependency and expose metrics endpoints per Spring Boot Actuator configuration. Expose only necessary endpoints and protect access in real environments.

### 7.2. Avoiding High-Cardinality Tags

Do not put nearly unique values into metric tags:

- `sessionId`, `connectionId`, `requestId`, `messageId`.
- Unbounded `userId`, `email`, `tenantId`.
- Dynamically generated destinations containing IDs.
- Exception messages containing free-form data.

Each tag combination creates a new time series. High cardinality inflates memory, CPU, and storage costs in the metrics system.

Use tags with small finite value sets, for example:

| Tag | Appropriate Values |
| --- | --- |
| `interaction` | `request-response`, `request-stream`, `channel`, `fire-and-forget` |
| `outcome` | `success`, `error`, `timeout`, `cancel`, `rejected` |
| `destination_group` | `orders`, `notifications`, `telemetry` |
| `payload_class` | `small`, `medium`, `large` |
| `instance` | platform-managed instance label |

Correlation IDs belong in logs and traces, not in unbounded metric tags.

## 8. Breaking Down Bottlenecks and Finding Capacity

As load increases, plot p50/p95/p99 latency, completed throughput, error rate, and queue depth on the same timeline.

A system typically exhibits three regions:

1. **Underloaded:** latency is steady and throughput scales roughly with offered rate.
2. **Near saturation:** throughput grows more slowly while p95/p99 and queue latency climb rapidly.
3. **Overloaded:** completed throughput stalls or drops, queues grow, timeouts/rejections appear, and resources saturate.

The point where latency turns nonlinear or backlogs stop draining on their own signals where to investigate. Never record only the peak request rate before the server crashes; that is not safe capacity.

### 8.1. Reading Symptom Patterns

| Observation | Likely Cause to Check |
| --- | --- |
| CPU near saturation, latency rising | Serialization, compression, business logic, GC, or thread contention. |
| Low CPU yet high p99 | Queue waits, network, locks, database, broker, or slow dependency. |
| Heap growing over time | Unbounded queues, retained references, uncleaned sessions/subscriptions, or memory leaks. |
| Rising GC pauses | Allocation rate, large payloads, buffers, or heap sizing. |
| DB pool constantly exhausted | Slow queries, long transactions, or undersized pool. |
| Broker queue growing | Consumer rate below producer rate, slow consumers, or broker resource limits. |
| Connection count rising continuously | Reconnect loops, leaked sessions, or clients never disconnecting. |
| Error rate jumps with retries enabled | Retry amplification, missing backoff, or retrying non-recoverable errors. |
| Only one instance has high p99 | Load imbalance, noisy neighbor, or an issue specific to that instance/dependency. |

### 8.2. Estimating Headroom

Run load in controlled steps—such as 25%, 50%, 75%, 100%, 125%, and 150% of target load. Hold each step long enough for queues and latency to reflect steady state.

Safe capacity is the highest load at which the system still meets SLOs, accumulates no backlog, shows no rising error trend over time, and retains headroom to absorb bursts or incidents. The exact headroom margin depends on traffic volatility, scaling speed, cost, and service criticality; no single percentage fits every system.

If adding instances fails to increase throughput, check shared bottlenecks such as the broker, database, network, or external APIs. Scaling application instances does not automatically scale shared dependencies.

## 9. Designing Fault Injection Tests

Fault injection intentionally introduces a controlled failure to observe how the system reacts. The goal is not breaking things for fun, but validating assumptions about timeouts, retries, backpressure, failover, data integrity, and recovery.

Start with a clear hypothesis:

- If the broker temporarily stops accepting connections, producers time out or fail fast within the configured limit.
- If consumers slow down, queues grow while memory stays bounded.
- If database latency spikes, requests are bounded by deadlines rather than creating unbounded threads/queues.
- If one instance restarts, clients reconnect and subscriptions recover per policy.
- If the network drops, messages can be retried without duplicate side effects.

### 9.1. Faults to Simulate

| Fault | How to Induce | What to Observe |
| --- | --- | --- |
| Network latency/jitter | Inject delay or latency variance between service and broker | p95/p99, timeouts, queues, and retries. |
| Packet loss / connection reset | Interrupt connections within test scope | Reconnects, stream/session cleanup, and message delivery. |
| Broker restart | Restart broker or stop one node | Failover, reconnects, redeliveries, and backlog recovery. |
| Slow consumer | Throttle processing speed or pause consumers | Queue depth, backpressure, memory, and oldest-message age. |
| Database slowdown | Induce controlled slow queries | DB pool, handler latency, timeouts, and retries. |
| CPU pressure | Cap CPU or run competing workload | Scheduler delay, throughput, and tail latency. |
| Memory pressure | Lower memory limit in test environment | GC, OOM behavior, and restart recovery. |
| Thread pool saturation | Cap workers or hold tasks in controlled wait | Queue growth, rejections, and thread starvation. |
| Instance termination | Restart or terminate one test instance | Load balancing, reconnects, and recovery capability. |
| Downstream failure | Return errors or timeouts from dependency | Circuit breakers, fallbacks, and retry amplification. |

Do not inject multiple faults at once on the first run. Once individual fault impacts are understood, combine two faults to test interactions—such as a slow broker while an instance restarts.

### 9.2. Measuring Recovery Capability

Beyond latency and error rate during the fault, measure:

- **Detection time:** how fast the system notices an unhealthy dependency.
- **Time to fail:** how long requests take to fail or fall back.
- **Time to recover:** from when the dependency recovers until the service operates normally.
- **Backlog drain time:** time needed to clear accumulated queues.
- **Data integrity:** messages lost, duplicated, or processed out of required order.
- **Recovery amplification:** retry/reconnect storms triggered after recovery.
- **User impact:** request success rate and duration of user-visible impact.

A system may restore network connections in seconds yet take minutes to drain backlogs. Therefore, recovery is not just health checks returning to `UP`.

### 9.3. Scope and Abort Conditions

Before each experiment, define:

- Which environment, services, instances, brokers, and dependencies are in scope.
- Background load and the fault to be injected.
- Experiment duration and how to end the fault.
- SLOs and abort thresholds—such as error rate, queue depth, memory, or latency crossing agreed limits.
- Observers and rollback steps if the system fails to self-recover.

Start with a narrow blast radius and expand gradually. Use staging or a production-equivalent test environment. If running fault injection in production, require strict controls, bounded scope, and an immediate kill switch.

## 10. Combining Load and Fault Injection

Testing faults while the system is idle rarely uncovers capacity problems. A dependency might survive a restart with zero queued messages yet trigger a massive backlog when restarted during peak traffic.

A useful test matrix:

| Load | Healthy System | Slow Dependency | Disconnected Dependency | After Recovery |
| --- | --- | --- | --- | --- |
| Baseline | Measure baseline | Verify timeouts | Verify graceful failure | Measure stabilization time |
| Target load | Confirm SLOs | Check p95/p99 and queues | Check errors and retries | Measure backlog drain |
| Burst | Test burst absorption | Check queue limits | Check rejections/backpressure | Check recovery amplification |
| Near capacity | Find saturation point | Find collapse point | Verify fail-fast | Measure return to steady state |

Not every cell in the matrix must run immediately. Prioritize high-risk scenarios first, then expand based on findings.

## 11. Retries, Timeouts, Backpressure, and Idempotency

Resilience mechanisms can amplify load if misconfigured together.

- **Timeout:** caps how long a caller waits or how long processing may run.
- **Retry:** re-attempts an operation after a recoverable failure.
- **Backoff:** spaces out intervals between retries.
- **Jitter:** adds randomness so many clients do not retry in lockstep.
- **Circuit breaker:** pauses calls to a failing dependency to avoid further overload.
- **Bulkhead:** isolates resources for one request group so failures do not spill into others.
- **Backpressure:** regulates emission rate to match consumer demand.
- **Idempotency:** ensures retrying the same business intent does not create duplicate side effects.

Never retry infinitely or immediately. If 1,000 clients time out together and retry after exactly one second, a newly recovered dependency gets hit by a fresh spike. Use bounded exponential backoff with jitter.

For messages with side effects, timeouts create uncertain outcomes: the consumer may have finished processing while the ACK or response was lost. Use message IDs/idempotency keys and store processing state to deduplicate. Define at-most-once, at-least-once, or exactly-once semantics explicitly within system boundaries; never claim exactly-once merely because a broker has ACKs.

## 12. Tools and Choosing a Load Generator

Tools must accurately simulate the protocol without becoming the bottleneck themselves.

| Tool / Approach | Best Fit | Notes |
| --- | --- | --- |
| Gatling | HTTP and WebSocket load tests; can send STOMP frames over WebSocket | Must model STOMP framing, handshakes, and session behavior accurately. |
| k6 | HTTP and WebSocket workloads | For STOMP, build protocol-compliant frames manually; k6 is not a native RSocket client. |
| JMeter | HTTP, WebSocket via plugins, and multiple protocols | Verify plugin support for desired protocol versions and load patterns. |
| RSocket-native client/load driver | Request-Response, Request-Stream, Request-Channel | Suitable for measuring demand, stream lifecycles, and frame-level behavior. |
| `WebSocketStompClient` | Integration/E2E functional tests and small controlled loads | Not intended by default as a high-throughput load generator for tens of thousands of sessions. |

Run load generators on machines or containers separate from the server under test. Monitor CPU, memory, network, and connection counts on the generator side. If the generator saturates before the server, results do not reflect application capacity.

Run multiple generators when scaling connections or throughput. Use identical workload definitions and synchronized clocks for comparisons. Never run load tests against production simply because a tool can generate load; require agreed scope, caps, and monitoring.

## 13. Example Capacity Test Design for STOMP

Suppose a system delivers notifications through a STOMP broker relay. An illustrative plan:

**Workload**

- 2,000 WebSocket sessions.
- Average of 3 subscriptions per session.
- 500 published messages/second.
- Median payload 1 KB, with a share of 10 KB messages.
- Average fan-out of 20 subscribers/message.
- 10 minutes warm-up, 20 minutes steady state, 5 minutes ramp-down.

These are illustrative numbers showing how to structure a plan; real loads must come from production traffic or validated forecasts.

**Measurements**

- Handshake and STOMP `CONNECT` latency.
- Active sessions and subscriptions.
- Publish rate, broker accepted rate, and delivery rate.
- End-to-end publish-to-receive latency: p50, p95, p99.
- Outbound queues, consumer lag, and oldest message age.
- CPU, heap, GC, network, thread pools, and broker resources.
- Disconnects/reconnects, delivery failures, and duplicate counts.

**Experiments**

1. Run a baseline at 10% load.
2. Step up to 25%, 50%, 75%, 100%, and 125%.
3. Hold target load to verify p95/p99 stability and non-growing queues.
4. Slow down one group of consumers to observe slow-consumer behavior.
5. Restart a broker node within test scope and monitor reconnects.
6. Restore the broker, measure backlog drain, and check for duplicate/lost messages.
7. Run a soak test to catch memory leaks or uncleaned subscriptions.

Results should state the highest load meeting SLOs, which component saturated first, discovered limits, and post-fault recovery times.

## 14. Interpreting Results and Making Decisions

A good report contains more than charts. It needs context so others can reproduce it:

- Versions of the application, JVM, Spring, Reactor, and broker.
- Instance specs, CPU, memory, thread pools, connection pools, and broker configuration.
- Load generator, generator count, workload model, and payload distribution.
- Warm-up, ramp-up, steady-state, and measurement durations.
- Offered/accepted/completed throughput.
- p50/p95/p99, error rates, timeouts, rejections, and queue depths.
- Dependency metrics over the same time window.
- Injected faults, start/end timestamps, and recovery times.
- Measurement limitations, sample sizes, and noisy events.

Compare two runs only when workload, environment, duration, and metric definitions match. If configuration changed, document it precisely to distinguish gains from code, resources, or lighter load.

When p99 rises, do not rush to add CPU or instances. Break down latency to see whether it rose in queues, the broker, handlers, the database, or clients. If throughput fails to rise when scaling the application, look for shared bottlenecks. If queues grow while CPU is low, consumers may be bound by I/O or a separate executor.

## 15. Common Mistakes

| Mistake | Why It Misleads | Fix |
| --- | --- | --- |
| Reporting only average latency | Hides tail latency. | Report p50, p95, p99, and sample distributions. |
| Measuring only producer send rate | Does not show how much consumers actually process. | Measure accepted, delivered, completed, and acknowledged rates. |
| Using only a single tiny payload | Underestimates serialization, network, and memory costs. | Use a realistic payload distribution. |
| Testing only one connection | Fails to reflect connection/session scaling. | Scale sessions, subscriptions, and connection churn. |
| Using a closed model for fixed-rate traffic | Load drops as responses slow, masking overload. | Use an open arrival rate for matching workloads. |
| Using `Thread.sleep` to generate load | Does not control arrival rate or concurrency accurately. | Use a load generator with explicit scenarios and pacing. |
| Averaging p99 across instances | Percentiles cannot be aggregated that way. | Merge histogram buckets and compute quantiles. |
| Ignoring queue depth | Misses accumulating backlogs. | Track queue depth, oldest message age, and drain rate. |
| Testing simple broker and concluding production broker has capacity | In-memory broker does not represent a real broker. | Test against the real production broker relay/cluster. |
| Running the load generator on the server host | Generator competes for CPU/network and skews results. | Isolate generators and monitor load-client resources. |
| Fault testing only under zero load | Misses backlogs and retry amplification. | Inject faults under baseline, target, and controlled burst loads. |
| Retrying without backoff | Re-overloads a recovering dependency. | Backoff, jitter, retry caps, and circuit breakers. |
| Using `requestId`/`sessionId` as metric tags | Creates massive cardinality. | Use bounded-value metric tags; keep IDs in logs/traces. |
| Stopping tests as soon as health checks turn `UP` | Queues may still hold large backlogs. | Wait for latency, errors, and queues to return to steady state. |

## 16. Pre-Capacity-Signoff Checklist

### Workload

- [ ] Workload reflects realistic request rates, sessions, subscriptions, fan-out, and payloads.
- [ ] Open/closed model chosen appropriately for system behavior.
- [ ] Load generator has sufficient resources and is not the bottleneck.
- [ ] Warm-up, ramp-up, steady-state, and ramp-down durations are defined.

### Metrics and SLOs

- [ ] p50, p95, p99 recorded with sufficiently large sample sizes.
- [ ] Offered, accepted, completed, and acknowledged throughput tracked.
- [ ] Errors, timeouts, rejections, queue depth, and consumer lag measured.
- [ ] CPU, heap, GC, threads, network, database, and broker metrics captured.
- [ ] SLOs and abort thresholds defined before running tests.

### Resilience

- [ ] Slow consumers, dependency latency, and connection loss tested.
- [ ] Restarts/failover tested within safe boundaries.
- [ ] Retries, backoff, idempotency, and duplicate handling verified.
- [ ] Recovery time and backlog drain time measured.
- [ ] Confirmed no message loss outside accepted semantics.

### Reporting

- [ ] Versions, configuration, environment, and tools recorded.
- [ ] Sample sizes, run durations, and percentile definitions documented.
- [ ] Highest load meeting SLOs explicitly stated.
- [ ] Bottlenecks, headroom, limits, and improvement steps listed.

## 17. Takeaways

- Capacity is the sustainable load that meets SLOs without accumulating backlogs.
- p95/p99 reveal tail latency; averages are insufficient to judge experience under heavy load.
- Measure offered, accepted, completed, and acknowledged throughput.
- Workloads must reflect sessions, subscriptions, fan-out, payloads, heartbeats, and consumer behavior.
- Open models maintain arrival rate; closed models maintain user counts and can mask overload.
- Use histogram buckets to aggregate percentiles across instances; never average p95/p99.
- For Spring Messaging, test with the production broker and protocol; the simple broker does not represent broker relay behavior.
- Fault injection requires a hypothesis, scope, abort thresholds, and recovery measurements.
- Retries must include backoff, jitter, and proper idempotency.
- Declare capacity only after verifying SLOs, queue stability, headroom, and recovery.

## 18. References

- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer integration and metrics endpoints.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): `Timer`, histograms, and percentiles.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): client-side percentiles and histogram buckets.
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): aggregating histograms and computing quantiles.
- [Prometheus — histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile): function for computing percentiles from histogram buckets.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models and RSocket integration.
- [Spring Framework — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html): simple broker, broker relay, and message routing.
- [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/): latency, traffic, errors, and saturation.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): measuring and alerting on SLOs.
- [Gatling Documentation](https://docs.gatling.io/): building scenarios and workloads for performance testing.
- [k6 Documentation — Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/): controlling workloads and arrival rates.
