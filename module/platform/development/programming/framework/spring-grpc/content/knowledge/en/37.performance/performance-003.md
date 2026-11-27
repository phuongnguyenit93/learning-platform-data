# Unary Latency and Throughput

A unary RPC sends one request and receives one response in a single call. When evaluating Spring gRPC performance, the two most important metrics are **latency** — the time to complete an RPC — and **throughput** — the number of RPCs completed per unit of time. These two metrics are related but not interchangeable: a system may respond very quickly under light load yet saturate rapidly with many clients, and a high-throughput system can still exhibit high tail latency.

To measure accurately, you must separate client time, server processing time, requests sent, requests completed successfully, and failed requests. This lesson focuses on unary RPCs, designing load measurements, finding the saturation point, and optimizing based on metrics.

## 1. Defining latency and throughput

**End-to-end latency** of a unary RPC is the elapsed time from when the client starts sending the call until it receives the final response or error. It may include:

- Client-side wait time before the call is sent.
- Client-side interceptors, credentials, and serialization.
- HTTP/2 scheduling, network, and TLS transport.
- Server-side queueing, deserialization, and interceptors.
- Business handler and dependencies such as databases or caches.
- Server serialization, response transport, and client deserialization.

Not every measurement includes all of these components. For example, a timer placed inside the handler measures only part of server processing; a timer around the stub call measures closer to the client experience. When reporting, always specify the exact start and end boundaries.

**Throughput** is typically reported in completed RPCs per second. Distinguish:

| Metric | Meaning |
| --- | --- |
| Offered rate | Rate at which the load generator attempts to send requests |
| Started RPC/s | Number of RPCs actually started per second |
| Completed RPC/s | Total RPCs finished per second, including successes and errors |
| Successful throughput / goodput | Number of RPCs completed successfully per second |
| Error rate | Percentage of RPCs ending with an error status or timeout |

Never report throughput using only requests sent. If the client sends 2,000 RPC/s while the server completes only 1,200 RPC/s and the rest time out, goodput is 1,200 RPC/s, not 2,000 RPC/s.

## 2. Reading latency percentiles

Average latency is useful for tracking trends, but it often hides the experience of slow requests. Report percentiles instead:

| Metric | Interpretation |
| --- | --- |
| p50 | Half of RPCs finish no slower than this value |
| p90 | 90% of RPCs finish no slower than this value |
| p95 | 95% of RPCs finish no slower than this value |
| p99 | 99% of RPCs finish no slower than this value |
| p99.9 | Tracks the very slow tail when sample volume is large enough |

For instance, p50 = 18 ms while p99 = 420 ms shows most requests are fast, yet a small group is significantly delayed. Reporting only the average hides this issue.

Latency histograms should use buckets suited to the SLA, keeping consistent units and measurement boundaries across benchmark runs. Do not average percentiles across multiple instances to produce a system-wide percentile; merge histograms or compute percentiles from an appropriate observation set. With small sample sizes, p99/p99.9 are unstable and easily lead to wrong conclusions.

Also monitor:

- RPC count and goodput per service/method.
- Status codes, timeouts, and cancellations.
- Payload size and concurrency.
- Client queue time and server queue time where measurable.
- CPU, heap, allocation rate, GC pauses, and thread pool saturation.
- Network bytes, retransmissions, and connection state.

## 3. Where does unary RPC latency come from?

Basic flow:

```text
Client creates request
       |
       v
Client interceptor + serialization
       |
       v
HTTP/2 stream / network
       |
       v
Server queue + deserialization
       |
       v
Server interceptor + business handler
       |
       v
Response serialization + HTTP/2
       |
       v
Client deserialization + callback
       |
       v
RPC completed
```

Within a single call, stages may overlap with other activity on the connection or server executor. This diagram shows logical stages, not a strict additive breakdown across every runtime.

A unary call always incurs fixed overhead for call lifecycle, metadata, HTTP/2 framing, and scheduling. For small requests, this overhead can outweigh business logic. For large requests, serialization, allocation, network, and parsing can dominate.

Measuring client end-to-end duration and server handler duration separately helps localize issues:

- High client latency, fast server handler: check client queue, network, TLS, serialization, connection, or server queue before the handler.
- Both client and handler slow: check business dependencies, CPU, locks, database, and GC.
- Fast handler but high client p99: investigate queues before/after the handler, transport, response parsing, and tail latency in dependencies.

## 4. Closed-loop and open-loop load tests

The load generation model directly shapes the results:

**Closed-loop** maintains a fixed number of concurrent clients/workers. A worker sends a call, waits for the response, and only then sends the next call. When latency rises, the request sending rate drops automatically. This model is suitable for simulating a pool of synchronous callers waiting on responses, but it can mask overload because the generator slows down its offered rate.

**Open-loop** attempts to issue requests at a defined arrival rate, independent of how long previous requests take to finish. This is closer to systems receiving continuous external traffic. When the server cannot keep up, queues and in-flight requests grow; queues must be bounded and dropped/rejected requests recorded.

| Property | Closed-loop | Open-loop |
| --- | --- | --- |
| How load is generated | Fixed concurrency, waits for call completion before sending next | Targets a fixed arrival rate |
| When latency increases | Offered rate usually drops | Offered rate stays constant if generator has capacity |
| Measurement risk | Masks queue buildup/overload | Can build huge queues if unbounded |
| Best suited for | Synchronous user/worker models | Continuous incoming traffic, capacity, and overload testing |

A good load test suite often uses both to understand both behaviors. With open-loop tests, track scheduled, actually started, completed, dropped, and timed-out requests. If you only measure latency of completed requests, you can miss requests that queued too long or were dropped.

## 5. Coordinated omission and properly paced load

Coordinated omission occurs when a load generator sends the next request only after the previous one completes. While the server slows down, the generator slows down too and fails to generate the requests that should have arrived during that interval. As a result, tail latency under steady traffic can be severely underestimated.

For example, suppose the server pauses for 2 seconds due to GC. A closed-loop client with few workers stops issuing most requests during that window. An open-loop client continues scheduling at the target arrival rate, revealing queueing and latency for traffic arriving during the stall.

To avoid misleading conclusions:

- Choose the load model to match production traffic.
- For open-loop, record both scheduled time and actual start time if the tool supports it.
- Report both queue delay and service latency when possible.
- Never exclude timeouts/drops from reports.
- Verify the load generator itself is not bottlenecked on CPU, network, or connections.

## 6. Concurrency, throughput, and Little's Law

Little's Law relates the number of requests in the system to throughput and average residence time:

\[
L = \lambda W
\]

Where:

- \(L\): average number of in-flight requests in the system.
- \(\lambda\): average throughput, in requests/second.
- \(W\): average time a request spends in the system, in seconds.

For example, if a service completes 600 RPC/s with an average end-to-end latency of 50 ms (0.05 seconds), the average number of in-flight RPCs is approximately:

\[
L = 600 \times 0.05 = 30
\]

If latency rises to 200 ms while throughput stays at 600 RPC/s, average in-flight RPCs rise to roughly 120. That can increase queueing, memory usage, and contention. Little's Law describes average behavior in a stable system; do not use it to predict tail latency or an unstable system.

Increasing concurrency can initially raise throughput because CPU and network are better utilized. Beyond the saturation point, additional concurrency mainly adds queueing and latency while goodput flattens or drops.

## 7. Reusing channels and warming up properly

`ManagedChannel` is a long-lived resource that supports many concurrent RPCs and multiplexes streams over HTTP/2 connections. Never create a new channel per request. Repeated channel creation repeats DNS resolution, TCP/TLS handshakes, HTTP/2 setup, and thread and buffer allocations.

Example client using one channel and reusing a stub:

```java
ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.default.svc.cluster.local:8443")
    .useTransportSecurity()
    .build();

OrderServiceGrpc.OrderServiceBlockingStub baseStub =
    OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = baseStub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Generated stubs are immutable; `withDeadlineAfter(...)` returns a new call-configured stub while reusing the channel. The channel should be shut down when the application stops.

Before benchmarking:

1. Create the channel once and wait for the resolver to resolve the target.
2. Send warm-up calls to complete connections, TLS handshakes, JIT compilation, and lazy resource initialization.
3. Verify the subchannel is in the `READY` state.
4. Start measuring only after the warm-up phase.
5. Keep channel, stub pattern, TLS, compression, and load balancing policy identical across runs.

If the goal is measuring cold start, measure channel/connection creation separately. Do not mix cold start into steady-state latency and report it collectively as unary latency.

## 8. Deadlines, timeouts, and statuses during measurement

Every RPC should carry a deadline aligned with its SLA. Deadlines cap how long the client waits and are propagated to the server so dependencies can cancel work when a call expires. Do not set artificially low deadlines just to make benchmark latency look better: timed-out requests reduce goodput and raise error rate.

When analyzing results, categorize by status:

| Status | How to interpret during benchmarks |
| --- | --- |
| `OK` | RPC completed successfully; counts toward goodput |
| `DEADLINE_EXCEEDED` | Did not finish within deadline; record as error/timeout |
| `UNAVAILABLE` | Transport/backend temporarily unavailable; inspect reconnect and retry |
| `RESOURCE_EXHAUSTED` | Likely hit quota, message limit, or capacity protection |
| `INTERNAL` | Server error; investigate instead of treating as normal latency |
| `CANCELLED` | Cancelled by caller or upstream; distinguish intentional vs. overload cancellation |

Never measure latency only for calls returning `OK`. A system with low p50 but high `DEADLINE_EXCEEDED` rate fails its SLA. Record deadlines, retry counts, and final status; if retries are enabled, distinguish single-attempt latency from overall logical RPC latency.

## 9. Measuring on client and server

The client is the most important end-to-end measurement point because it observes the time the caller actually experiences. You can wrap a blocking call with `System.nanoTime()` in a simple measurement:

```java
long started = System.nanoTime();
try {
    GetOrderResponse response = stub
        .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
        .getOrder(request);
    long elapsedNanos = System.nanoTime() - started;
    latencyHistogram.record(elapsedNanos);
} catch (StatusRuntimeException error) {
    errorCounter.increment(error.getStatus().getCode());
    throw error;
}
```

This snippet only illustrates the end-to-end boundary for a synchronous call. It is not a load generator and should not allocate a separate histogram per request. In real applications, use a metrics library with histogram buckets and avoid synchronous logging on the hot path.

A server interceptor can measure time from call receipt until call close. That is server-observed duration, which may include queueing depending on instrumentation placement, but excludes client-side delays. Use trace spans or correlated timestamps to analyze stages; clocks across hosts can drift, so avoid subtracting raw wall-clock timestamps unless clocks are synchronized.

Do not add client latency and server duration as two independent parts when client latency already includes server duration. They are overlapping views of the same call.

## 10. Designing a repeatable benchmark

A reliable unary benchmark must control:

- **Workload:** realistic methods, request/response sizes, cache hit/miss ratios, and business work.
- **Load model:** closed-loop or open-loop; concurrency/arrival rate explicitly documented.
- **Warm-up:** JVM, JIT, channel, TLS, and connections stabilized.
- **Duration:** long enough to observe GC, autoscaling, and load variance; exclude warm-up from measurements.
- **Environment:** identical CPU/memory limits, JVM flags, replica counts, network paths, and dependencies.
- **Load generator:** adequately provisioned, positioned appropriately relative to production clients, and not saturating before the server.
- **Reporting:** offered rate, started/completed, goodput, errors, p50/p95/p99, CPU, memory, and GC.

Change one variable at a time, such as concurrency, payload size, compression, or replica count. Run multiple iterations and compare medians/variance across runs; record the commit, configuration, and test data so results are reproducible.

## 11. Finding the saturation point and optimizing

Increase offered load in steps, holding each step long enough for the system to stabilize. Plot goodput and p99 latency against offered rate:

```text
Offered rate increases
       |
       v
Goodput grows nearly linearly
       |
       v
Reaches capacity region / saturation knee
       |
       +---- Goodput flattens out
       |
       +---- p95/p99 latency climbs rapidly
       |
       v
Queues, timeouts, and errors increase
```

The point where p99 begins climbing sharply while goodput stops scaling proportionally signals the system is approaching saturation. Do not operate continuously right at the knee; keep headroom for bursts, rollouts, and dependency variance.

Diagnose by resource:

| Observation | Direction to investigate |
| --- | --- |
| Server CPU near 100%, CPU-bound handler | Profile code, serialization, allocation, and worker count |
| Low CPU but high latency | Database, downstream RPCs, locks, thread starvation, or network |
| Executor/queue growing | Increase processing capacity or limit admission; do not just enlarge queues |
| Increasing GC pauses/allocation | Message size, object churn, buffer copies, and heap sizing |
| One backend hotter than others | Resolver/LB policy, connection reuse, and request distribution |
| High client CPU | Serialization, compression, interceptors, or load generator |
| Rising `RESOURCE_EXHAUSTED` | Quotas, message limits, concurrency limits, and flow control |

Optimize according to the measured bottleneck: reuse channels; trim unnecessary payload data; avoid blocking I/O on inappropriate executors; bound pools and concurrency; enforce deadlines; check load balancing; and scale out when the workload is truly distributable. Adding threads or enlarging queues without understanding the bottleneck can worsen context switching and tail latency.

## 12. Practice exercise

`OrderService.GetOrder` has p50 = 22 ms and p99 = 480 ms at 700 RPC/s. When raising the offered rate to 1,000 RPC/s, goodput increases only to 740 RPC/s, p99 exceeds 1 second, and `DEADLINE_EXCEEDED` rises. Server CPU is at 85%, and one replica receives more traffic than the others.

**Tasks:**

1. Identify additional metrics to collect on client, server, resolver, and load balancer.
2. Design both closed-loop and open-loop tests to determine whether the load generator is masking queueing.
3. Calculate average in-flight RPCs at 700 RPC/s with 40 ms average latency using Little's Law.
4. Inspect channel reuse, HTTP/2 connections, resolver results, and load balancing policy to find why one replica is hot.
5. Analyze server CPU, executor queues, downstream latency, allocation, and GC before adding threads.
6. Evaluate deadlines/retries to avoid amplifying load when the backend is already saturated.
7. Propose capacity headroom and alert thresholds based on goodput, p99, error rate, and queue depth.

**Self-check questions:**

- How does end-to-end latency differ from server handler duration?
- Why must goodput be reported alongside offered rate?
- What does a low p50 combined with a high p99 indicate?
- How can closed-loop testing mask overload?
- How does coordinated omission distort measurements?
- How does Little's Law relate throughput, latency, and in-flight requests?
- Why must channels and the JVM be warmed up before steady-state benchmarks?
- How do you recognize the saturation knee?
- When retries are enabled, how should per-attempt latency be distinguished from logical RPC latency?

**Key takeaway:** Unary latency reflects how long callers wait for an RPC; throughput must be based on completed calls, especially goodput. Measure percentiles and error rates alongside offered rate; pick closed-loop/open-loop appropriately; reuse channels and warm up before measuring. Step up load to find the saturation knee, use Little's Law and client/server telemetry to locate queueing, and optimize the real bottleneck instead of blindly raising concurrency.
