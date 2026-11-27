# Measuring Post-Deployment Latency, Throughput, and Errors

In this project, you will add observability and run a load test against your deployed Spring gRPC service. You will generate controlled load, collect latency, throughput, and gRPC statuses, and then correlate metrics, traces, and logs to explain what happens as client concurrency or send rate increases.

The goal is to produce repeatable results useful for operational decisions. A single average latency number or one successful `grpcurl` call is not enough to evaluate performance. You need well-defined measurements, controlled input load, error rates, latency percentiles, and server resource usage.

## 1. Scenario and Project Scope

Assume you have a Spring gRPC service providing data lookup and update RPCs, with at least one unary RPC and one streaming RPC. After deployment, you need to answer these questions:

- As concurrent clients increase, how do p95 and p99 latencies change?
- How many RPCs or messages per second can the server handle at a given load level?
- Which error statuses appear as load rises, and at what load level do they start appearing?
- Is time spent in the server, a downstream dependency, or the network?
- For streaming, can the server sustain long-lived streams and handle slow-reading clients?
- After reaching a resource limit, how does the system recover when load drops?

The initial scope covers one deployment environment, one Spring gRPC service, a separate load-generator host or process, and a metrics collection stack. You can use Prometheus/Grafana and OpenTelemetry if already available in the environment. If your project uses another monitoring platform, map these concepts to its equivalent metrics.

Never change multiple server settings in the same test run. When comparing two versions, keep the load profile, payload, run duration, load-generator placement, and environmental conditions identical so comparisons remain meaningful.

## 2. Learning Objectives

Completing this project will enable you to:

- Distinguish client-observed RPC latency, server processing duration, and per-message stream latency.
- Measure throughput in RPCs/second, messages/second, and bytes/second.
- Interpret p50, p95, p99, error rates, and gRPC status distributions.
- Build load profiles with warm-up, ramp-up, steady state, and cool-down phases.
- Instrument the server with Micrometer or an equivalent metrics library.
- Correlate traces and logs to diagnose a slow or failing request.
- Design dashboards and reports with clear data, test conditions, and caveats.
- Distinguish errors caused by the server, dependencies, network, deadlines, and the load generator itself.

## 3. Defining Metrics to Measure

Before writing the load test, agree on the exact definition of every metric. The same name can refer to different time intervals.

| Metric | Project Definition | Usage |
| --- | --- | --- |
| Client-observed latency | Time from when the client starts an RPC until it receives the final response or terminal status | Reflects overall client experience |
| Server call duration | Time the server spends handling an RPC from arrival until closing the call | Separates server work from network and client overhead |
| Message round-trip latency | Time from when the client sends an identified message until it receives the matching ACK | Used for operations in bidirectional streaming |
| Time to first response | Time from opening the RPC to receiving the first response | Useful for server streaming and bidirectional streaming |
| Inter-message gap | Elapsed time between two consecutive responses received by the client | Detects stalled streams or slow server emission |
| Throughput | Successful RPCs, processed messages, or bytes transferred per unit time | Must state units clearly and measure only during steady state |
| Error rate | Failed RPCs or operations divided by total attempted RPCs or operations | Must state the denominator and how cancellations are classified |
| Active streams | Number of open streaming RPCs at a point in time | Tracks resource usage and long-lived session capacity |

For unary RPCs, per-call latency is straightforward. For streaming, the lifetime of an entire stream can span minutes or hours; never use stream lifetime as a substitute for per-message processing latency. Measure stream open time, time-to-first-response, message round-trip, and stream lifetime as separate metrics.

When measuring message round-trip, use a monotonic clock on the client: record the timestamp right before sending a message and stop when the ACK with the same `operation_id` arrives. Never subtract timestamps recorded on two separate machines without accounting for clock skew. To measure server-only processing time, record timestamps or durations on the server and use server-side traces/metrics.

Average latency can hide a long tail of slow requests. Report at minimum p50, p95, and p99 alongside sample counts. Percentiles across different time windows or instances cannot be simply summed or averaged to produce a system-wide percentile; compute them from histogram buckets or appropriate sample aggregation.

## 4. Preparing the Measurement Environment

Before generating load, record key environment details:

- Application version, commit/build ID, and active Spring gRPC configuration.
- CPU, RAM, container limits, replica count, and request load balancing.
- Java/JVM version, heap settings, garbage collector, and relevant thread/executor limits.
- Endpoint, TLS/mTLS, proxies, ingress, or load balancers along the path.
- Proto version and payload size for each RPC.
- Load generator placement and baseline network latency to the endpoint.
- Load generator version, channel/stub settings, and load-generator resource limits.
- Downstream dependencies called by handlers, along with their state and background load.

Run the load generator on a separate machine or process from the server. Generating load on the same host causes CPU or network contention with the server and skews conclusions. Monitor the load generator itself: CPU, RAM, thread count, connections/channels, event loops, and whether it sustains the target send rate.

Verify the endpoint with a small request before running benchmarks. `grpcurl` is useful for validating the service, method, reflection/proto, TLS, and metadata; it is not a concurrency benchmarking tool or a substitute for a load generator.

## 5. Building a Repeatable Load Profile

Create a dedicated load-test client using Java gRPC stubs or a gRPC load-testing tool suited to your environment. If writing a custom client, reuse channels, use the proper stub type, pre-build payloads, and collect latencies without blocking callback threads. Avoid creating a new channel per RPC, as that measures connection setup overhead and does not reflect realistic client behavior.

Each benchmark run should include these phases:

1. **Preflight:** verify endpoint, authentication, method, payload, and health status.
2. **Warm-up:** send light load so the JVM, connection pools, DNS, and caches stabilize; exclude this phase from steady-state numbers.
3. **Ramp-up:** gradually increase concurrent clients or request rate to avoid artificial spikes.
4. **Steady state:** hold target load long enough to gather statistically meaningful samples and stabilize system metrics.
5. **Ramp-down:** reduce load cleanly and observe queues, CPU, and active streams returning to baseline.
6. **Cool-down:** wait for metrics and logs to flush before starting the next run.

Example initial test matrix:

| Run | Concurrency | Warm-up Duration | Steady-State Duration | Purpose |
| --- | ---: | ---: | ---: | --- |
| A | 1 client | 30 seconds | 2 minutes | Capture low-load baseline latency |
| B | 10 clients | 30 seconds | 3 minutes | Observe light load |
| C | 25 clients | 30 seconds | 3 minutes | Observe trend as concurrency rises |
| D | 50 clients | 30 seconds | 3 minutes | Identify early saturation signs |
| E | 100 clients | 30 seconds | 3 minutes | Evaluate higher load if environment permits |

These levels are examples only. Adjust them to your environment limits and system load targets. Never exceed approved limits on shared environments. Run each configuration at least three times when comparing trends, and note run-to-run variance.

Hold payload and workload constant when comparing concurrency. Only then run separate matrices for small/large payloads, TLS on/off (if relevant), or different RPC types. Change one variable at a time so you know what caused any change in results.

## 6. Designing Workloads per RPC Type

Do not collapse all RPC types into a single throughput number. Each RPC pattern has its own unit of work and measurement approach.

| RPC Type | Workload | Latency to Record | Throughput to Record |
| --- | --- | --- | --- |
| Unary | Send independent requests with a fixed payload | Client-observed latency and server call duration | Successful RPCs/second |
| Server streaming | Open stream and request data; server emits multiple responses | Time-to-first-response, inter-message gap, completion time if applicable | Messages received/second and streams opened/second |
| Client streaming | Send a fixed number of messages, then half-close | Upload duration and time to final response | Messages received/second and streams completed/second |
| Bidi streaming | Maintain multiple streams, send messages at a steady rate, and receive ACKs/notifications | Message round-trip, time-to-first-response, stream age | Messages sent/received/second and active streams |

For streaming, record messages per stream, send rate per client, target stream lifetime, and stream-closing policy. Counting only completed RPCs makes a long-lived bidi stream look like near-zero throughput even when message rates are high.

Create at least two workloads:

- **Normal workload:** small payloads, steady rates, and a read/write ratio close to expected client behavior.
- **Heavy workload:** larger payloads or higher concurrent stream counts, still within configured limits and test objectives.

For bidi streaming, every message should carry an `operation_id` to correlate requests with ACKs. The load generator records the send time using a monotonic clock and updates the latency sample when the ACK arrives. If an ACK is missing, record the timeout or stream termination as an error sample rather than discarding it.

## 7. Collecting Server Metrics with Micrometer

If the application already uses Spring Boot Actuator and Micrometer, register metrics in `MeterRegistry` via a gRPC `ServerInterceptor` or your stack's equivalent instrumentation layer. If your starter provides built-in instrumentation, prefer the supported mechanism and verify actual metric names before building dashboards.

Baseline metrics to capture:

| Logical Metric | Metric Type | Suggested Tags/Labels |
| --- | --- | --- |
| RPCs started/completed | Counter | `method`, `status` |
| RPC processing duration | Timer/histogram | `method`, `status` |
| Messages received/sent | Counter | `method`, `direction` |
| Open streams | Gauge | `method` |
| Outbound queue | Gauge | `method` or fixed queue name |
| Queue-full events | Counter | `method`, `policy` |
| Dependency errors | Counter/timer | `dependency`, `outcome` |

Example interceptor skeleton to measure server call duration:

```java
public final class GrpcMetricsInterceptor implements ServerInterceptor {
    private final MeterRegistry registry;

    public GrpcMetricsInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        Timer.Sample sample = Timer.start(registry);
        AtomicBoolean recorded = new AtomicBoolean(false);
        registry.counter("grpc.server.calls.started", "method", method)
                .increment();

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendMessage(RespT message) {
                        registry.counter("grpc.server.messages", 
                                "method", method, "direction", "outbound")
                                .increment();
                        super.sendMessage(message);
                    }

                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (recorded.compareAndSet(false, true)) {
                            String code = status.getCode().name();
                            registry.counter("grpc.server.calls.completed",
                                    "method", method, "status", code)
                                    .increment();
                            sample.stop(Timer.builder("grpc.server.call.duration")
                                    .tag("method", method)
                                    .tag("status", code)
                                    .publishPercentileHistogram()
                                    .register(registry));
                        }
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);
        return new ForwardingServerCallListener.SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                registry.counter("grpc.server.messages",
                        "method", method, "direction", "inbound")
                        .increment();
                super.onMessage(message);
            }
        };
    }
}
```

This is an illustrative skeleton. Add missing imports, register the interceptor with the server, check your project's gRPC/Micrometer API versions, and verify the interceptor applies to the intended service. For streaming, `close()` measures the entire RPC duration, not per-message latency. To measure server-side message processing time, instrument inside the handler or processing pipeline with a timer scoped to the specific operation.

In real implementations, also cover termination paths like cancellation and exceptions so counters/gauges update exactly once. If you maintain an active-streams gauge, increment on call start and decrement on completion or cancellation. Never register a gauge backed by a transient object that can be garbage-collected.

### Cardinality Rules

Use only labels with small, bounded value sets, such as method name, gRPC status code, and direction. Never use `user_id`, `room_id`, `request_id`, `operation_id`, tokens, or payload contents as labels. Every unique label value creates a new time series; high-cardinality labels can overload Prometheus and dashboards.

## 8. Collecting Traces and Logs

Metrics show overall trends; traces help investigate individual requests. Configure OpenTelemetry or your existing tracing stack to emit spans for RPCs and the downstream dependencies handlers call.

A useful trace shows:

1. Client starts the RPC and sends metadata/trace context.
2. Server receives the RPC, runs interceptors, and invokes the handler.
3. Handler calls a database, HTTP client, or message broker.
4. Downstream dependency returns a result or times out.
5. Server sends the response and closes the RPC with a status.

For high-throughput streaming, avoid creating a new span for every single message if tracing overhead exceeds your budget. Create a span for the stream lifecycle and sample events/spans for selected operations, while relying on metrics for total message counts and latency distributions. Include trace IDs in logs to tie together log lines from the same call.

Logs should record method, status, duration, trace ID, and sanitized diagnostic context. Never log bearer tokens, private keys, full payloads, or personal data. Distinguish expected validation errors from system errors so dashboards do not turn every business error into an infrastructure incident.

## 9. Building the Dashboard

Create a dashboard with at least the following panels:

| Section | Chart or Table | Question Answered |
| --- | --- | --- |
| Traffic | RPC/s, message/s, byte/s by method | Does traffic match the load profile? |
| Latency | p50, p95, p99 by method | At what load does latency climb? |
| Errors | Error rate and status distribution | Which errors start appearing and when? |
| Concurrency | Active RPCs, active streams | How many concurrent calls/streams is the server holding? |
| Server resources | CPU, memory, heap, GC pauses, thread/executor queues | Which resource is nearing saturation? |
| Dependencies | Latency, timeouts, and errors of DB/HTTP/broker | Which dependency is consuming time? |
| Backpressure | Queue depth, `isReady`/slow consumers, overflow count | Are slow clients backing up queues? |

The PromQL examples below assume Micrometer metrics are exported under matching Prometheus names. Actual names may vary by exporter and naming conventions; check the metrics endpoint before writing queries.

Successful RPC throughput:

```promql
sum by (method) (
  rate(grpc_server_calls_completed_total{status="OK"}[5m])
)
```

Non-`OK` RPC completion rate:

```promql
sum(rate(grpc_server_calls_completed_total{status!="OK"}[5m]))
/
clamp_min(sum(rate(grpc_server_calls_completed_total[5m])), 1e-9)
```

p95 latency by method from histogram buckets:

```promql
histogram_quantile(
  0.95,
  sum by (le, method) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

Message rate by direction:

```promql
sum by (method, direction) (
  rate(grpc_server_messages_total[5m])
)
```

These expressions illustrate how to compute each view. Adjust metric and label names if your exported metrics differ. Do not calculate per-message error ratios from the RPC status if your application returns business errors inside stream frames; track accepted/rejected operations with a separate counter instead.

## 10. Running Tests and Recording Results

Execute at least the following experiments:

### Test A: Unary Baseline

Run one client or low concurrency with a fixed payload. Record p50/p95/p99, RPC/s, statuses, and CPU/memory. This establishes the baseline for comparing higher-load runs.

### Test B: Increasing Concurrency

Increase concurrency according to your test matrix. Watch for the point where p95/p99 starts rising sharply, throughput stops scaling proportionally, or errors appear. That indicates saturation in the server, a dependency, the network, or the load generator; use traces and resource metrics to pinpoint where.

### Test C: Small vs. Large Payloads

Hold concurrency and request rate constant while varying payload size. Monitor bytes/s, serialization CPU, network throughput, latency, and message size limits. Do not blame payload size if other variables changed simultaneously.

### Test D: Streaming

Open a target number of concurrent streams, send messages at a steady rate, and measure message round-trip latency. For server streaming, record time-to-first-response and inter-message gaps. For client streaming, record upload duration and latency to the final response. Watch active streams and queues when a client reads slowly.

### Test E: Deadlines and Slow Dependencies

In a controlled test environment, simulate a slow dependency or tight deadline. Verify clients receive the expected status, the server records error metrics, and traces capture dependency wait time. Never inject intentional faults in production or unauthorized shared environments.

### Test F: Ramp-Down and Recovery

After reducing load, verify whether active streams, queue depth, thread/executor queues, CPU, and memory return to normal baselines. Check for stuck tasks, unclosed streams, or growing backlogs.

For every run, record:

- Run ID, timestamp, commit/build ID, and environment.
- RPC/method, proto version, payload size, and TLS/proxy path.
- Concurrency or target request/message rate.
- Warm-up, ramp-up, steady-state, and ramp-down durations.
- Sent, succeeded, failed, timed-out, and cancelled RPC/message counts.
- p50/p95/p99, throughput, error rate, and active streams.
- CPU, memory, GC, thread/executor queues, and dependency latency.
- Anomaly notes and trace IDs for representative slow or failing requests.

## 11. Classifying gRPC Errors

Do not lump every non-`OK` status into a single error bucket. Preserve the per-status breakdown and identify which errors are expected outcomes of the test.

| Status | Investigation Direction |
| --- | --- |
| `UNAVAILABLE` | Server/endpoint not ready, dropped connection, proxy/upstream failure, or restarting instance. |
| `DEADLINE_EXCEEDED` | Deadline shorter than completion time, slow dependency, queueing delay, or overloaded server. |
| `RESOURCE_EXHAUSTED` | Quota, message size limit, queue capacity, concurrent stream limit, or resource threshold reached. |
| `INTERNAL` | Unhandled exception or internal failure; inspect trace ID and server-side stack trace. |
| `CANCELLED` | Client, proxy, or test harness cancelled the call; distinguish planned teardown cancellations from unexpected ones. |
| `UNAUTHENTICATED` | Missing, invalid, or expired credentials; check metadata and auth interceptor. |
| `PERMISSION_DENIED` | Principal lacks permission for the operation; check policies and tenant scope. |
| `INVALID_ARGUMENT` | Invalid payload or contract violation; inspect load-generator test data. |
| `UNIMPLEMENTED` | Method/service not registered or client using mismatched descriptor/method name. |

Define error rate according to workload type. For unary, divide non-`OK` RPCs by total completed RPCs. For streaming, report both the ratio of failed streams and the ratio of rejected or timed-out operations/messages. Separate intentional cancellations emitted by the test harness during teardown from errors occurring during steady state.

## 12. Interpreting Results and Finding Bottlenecks

Common patterns:

| Observation | Hypothesis to Verify |
| --- | --- |
| Throughput increases, p95 stays roughly flat | System still has headroom for increased load in the tested range. |
| Throughput plateaus, p95/p99 climbs rapidly | A component is nearing saturation; check CPU, thread queues, dependencies, and network. |
| High CPU, rising latency, rising GC pauses | Likely constrained by CPU, serialization, allocation rate, or GC. |
| Low CPU yet high latency | Check I/O waits, lock contention, connection pools, executor queues, and dependencies. |
| `DEADLINE_EXCEEDED` rises alongside queue depth | Requests wait too long in queues before processing, or dependencies miss deadlines. |
| `RESOURCE_EXHAUSTED` increases | Check quotas, message sizes, outbound queues, concurrent stream caps, and memory. |
| Unary is stable while streaming degrades | Inspect stream lifetimes, message counts, flow control, slow consumers, and cleanup. |
| Load generator CPU maxed or misses target rate | Test may be bottlenecked by the load generator; cannot yet conclude the server hit its limit. |
| High client latency with low server call duration | Inspect network, proxies, client scheduling, channels, and pre/post-server wait time. |

These are hypotheses, not automatic conclusions. Correlate traces and metrics from the exact same time window to confirm. Avoid blindly increasing thread pools, timeouts, or replicas based on a single chart; pair every change with a hypothesis and a controlled comparison run.

## 13. Acceptance Criteria

The project is considered complete when:

- [ ] Load generator runs independently from the server and reuses channels/stubs properly.
- [ ] At least one unary workload and one streaming workload are tested; if the module implements all four RPC types, capture measurements for each.
- [ ] Load profile includes preflight, warm-up, ramp-up, steady state, and ramp-down.
- [ ] Report clearly states definitions for latency, throughput, error rate, units, and sample counts.
- [ ] Includes p50, p95, p99, RPCs/s or messages/s, and gRPC status distribution.
- [ ] Streaming measures message round-trip / time-to-first-response rather than using stream lifetime alone as latency.
- [ ] Server exports metrics for call duration, calls, messages, and active streams or equivalents.
- [ ] Traces and logs suffice to diagnose one slow request and one representative failure.
- [ ] Dashboard visualizes traffic, latency, errors, concurrency, resources, and dependencies.
- [ ] Load generator is monitored to rule it out as the bottleneck.
- [ ] At least three repeated runs exist for key comparisons, or an explanation of why repetition was not possible.
- [ ] Credentials, sensitive payloads, and high-cardinality IDs are excluded from metrics and logs.

Do not impose a universal latency threshold across every environment. If your team has an SLO, use that SLO as the criterion. Otherwise, report baseline numbers and trends under load, and note that SLOs must be agreed upon with system owners before declaring pass/fail.

## 14. Deliverables

When submitting the project, provide:

- Load-generator source code or load-testing tool configuration with run instructions.
- Metric/tracing instrumentation configuration and instructions for enabling it in the test environment.
- Dashboard or dashboard configuration file along with the queries used.
- Result tables per run, including p50/p95/p99, throughput, error rates, statuses, and resource utilization.
- At least one analyzed trace of a slow request and one analyzed failure example.
- A report detailing test conditions, measurement limitations, confirmed bottlenecks, and next recommendations.

A strong report lets someone else re-run the exact same workload and understand how conclusions were reached. Latency, throughput, and error rate only carry meaning when paired with measurement definitions, load conditions, and observations from both server and client.
