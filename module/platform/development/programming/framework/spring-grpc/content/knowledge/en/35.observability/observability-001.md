# RPC Count Metric by Service and Method

When operating a gRPC system, the total request count across the entire application is often insufficient to pinpoint the root cause of an incident. A service may receive many read RPCs and few write RPCs, yet the error rate of a specific method can spike sharply. Counting RPCs by service and method helps identify which endpoints are receiving load, which methods are spiking, and whether traffic changes correlate with a rollout.

The **RPC count metric by service and method** is a metric that counts RPC invocations, grouped by stable gRPC service and method names. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on defining precisely when an RPC is counted, collecting metrics on the server/client, and querying the data without creating excessive cardinality.

## 1. Defining the Unit Being Counted

In gRPC, an RPC is a single invocation of a service method, such as `Inventory.GetStock` or `Order.CreateOrder`. An RPC can be unary or streaming:

- Unary: one request and one response.
- Server streaming: one request, multiple response messages.
- Client streaming: multiple request messages, one response.
- Bidirectional streaming: multiple messages in both directions.

The RPC count metric must count **once per call**, not per message. A server-streaming call that sends 500 messages is still one RPC. If you need to know message throughput, create a separate metric such as messages sent/received.

Before creating metrics, align on what each metric counts:

| Metric | Increment Timing | Meaning |
| --- | --- | --- |
| RPC started | When the call is received on the server or started on the client. | Volume of calls initiated, including calls that have not yet finished. |
| RPC completed | When the call reaches a terminal state. | Volume of finished calls, broken down by status. |
| RPC in-flight | Incremented when the call starts, decremented when the call finishes. | Number of active calls at the time of observation. |
| RPC attempt | Each attempt to an endpoint. | Used to analyze retries/failovers, if instrumentation can observe each attempt. |
| Logical operation | A business intent from the caller. | May encompass multiple RPC attempts or multiple service calls. |

Do not sum these metrics together. One logical operation can generate multiple RPCs; one streaming RPC can carry thousands of messages.

## 2. Grouping by Service and Method

Service and method names should come from the Protobuf method descriptor, not from manually concatenated URLs or payloads. For example:

| gRPC full method name | Service label | Method label |
| --- | --- | --- |
| inventory.Inventory/GetStock | inventory.Inventory | GetStock |
| inventory.Inventory/WatchStock | inventory.Inventory | WatchStock |
| orders.OrderService/CreateOrder | orders.OrderService | CreateOrder |

Use the full service name including the package to avoid collisions between services with the same short name. The method label is the method name within the service. This is a finite set of values defined in the API, making it suitable for metric labels.

Basic metrics should include:

- Service: full name of the Protobuf service.
- Method: method name of the RPC.
- Status: RPC termination code, such as OK, CANCELLED, DEADLINE_EXCEEDED, or UNAVAILABLE.
- Direction: server or client if sharing a single metric family.

Do not use user ID, order ID, request ID, trace ID, arbitrary IP addresses, or error message text as labels. These values can have millions of variants and cause the number of time series to grow uncontrollably. Use logs or traces to investigate a specific request.

## 3. Choosing a Counter for RPC Count

Call count is a cumulative quantity, so use a Counter. A Counter only increases; the metrics backend computes the rate of increase over a time window.

Example server metric definition:

~~~text
grpc.server.calls.started
  tags: service, method

grpc.server.calls
  tags: service, method, status
~~~

The started counter increments once when the server receives a call. The completed counter increments exactly once when the call reaches a terminal state. You can sum across statuses to get the total completed RPCs by service/method.

If you only need a single total RPC count metric, the completed metric with a status tag is usually sufficient. The started metric adds visibility into calls received but not yet finished, which is especially useful when comparing against completed calls in the same time window.

Do not use a Gauge to count total RPCs since application startup; a Gauge can go up and down, whereas total calls are cumulative. A Gauge is appropriate for the number of currently active calls.

## 4. Collecting Server Metrics with ServerInterceptor

`ServerInterceptor` sits at the boundary where RPCs are received, so it can extract service/method from `MethodDescriptor` and record the status when the call ends. The example below uses Micrometer's `MeterRegistry`:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcCountServerInterceptor implements ServerInterceptor {

    private final MeterRegistry registry;

    public RpcCountServerInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String fullMethod = call.getMethodDescriptor().getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        registry.counter(
                "grpc.server.calls.started",
                "service", service,
                "method", method
        ).increment();

        AtomicBoolean recorded = new AtomicBoolean();
        java.util.function.Consumer<Status> recordTerminal = status -> {
            if (recorded.compareAndSet(false, true)) {
                registry.counter(
                        "grpc.server.calls",
                        "service", service,
                        "method", method,
                        "status", status.getCode().name()
                ).increment();
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        recordTerminal.accept(status);
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                // Client cancellation/deadline can cause the server not to go through close()
                // with an application-emitted status.
                recordTerminal.accept(Status.CANCELLED);
                super.onCancel();
            }
        };
    }
}
~~~

The interceptor increments `started` when receiving a call. The `ServerCall` wrapper records the actual status when the server closes the call. `onCancel` acts as a fallback path when the peer cancels the call; `AtomicBoolean` ensures only one terminal count is recorded even if cancellation and `close` occur close together.

In some versions or transports, the order of terminal callbacks can differ. Test the interceptor with the `grpc-java` version in use, especially the race between `onCancel` and `close`. If `onCancel` has already recorded `CANCELLED` before `close` is called, the `recorded` flag prevents recording a second time.

Register the interceptor on the server builder or via the global interceptor mechanism used by your Spring gRPC starter. Example with a builder:

~~~java
serverBuilder.intercept(new RpcCountServerInterceptor(meterRegistry));
~~~

The exact bean/interceptor registration mechanism depends on the starter and version in use. If the starter manages the server itself, use the starter's official extension point; avoid creating an extra server or a parallel interceptor registration outside the application's lifecycle.

## 5. Measuring Client-Side RPC Count

Server metrics answer "how many calls did the service receive and finish". Client metrics answer "which methods did the application call and what results did it receive". These can be collected in a `ClientInterceptor`:

~~~java
public final class RpcCountClientInterceptor implements ClientInterceptor {

    private final MeterRegistry registry;

    public RpcCountClientInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String fullMethod = method.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String methodName = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                registry.counter(
                        "grpc.client.calls.started",
                        "service", service,
                        "method", methodName
                ).increment();

                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                registry.counter(
                                        "grpc.client.calls",
                                        "service", service,
                                        "method", methodName,
                                        "status", status.getCode().name()
                                ).increment();
                                super.onClose(status, trailers);
                            }
                        };

                super.start(monitored, headers);
            }
        };
    }
}
~~~

Client and server metrics do not necessarily match. A client may cancel before the server receives the request; the server may finish but the response is lost; a proxy may reject the call before it reaches the server. Set `direction` explicitly so the two perspectives are not added together.

One note regarding retries: metrics at `ClientInterceptor` typically reflect calls at the interceptor boundary; whether it counts logical calls or individual transport attempts depends on instrumentation placement and the retry mechanism in the gRPC version. If you need accurate attempt counts, use instrumentation capable of observing at the attempt level or metrics provided by a proxy/control plane. Do not label a client interceptor metric as an attempt count without verifying it with tests.

## 6. Handling Cancellation and Terminal Status Exactly Once

An RPC has several termination paths:

- Server returns a successful response.
- Server returns an error via a status.
- Client actively cancels.
- Deadline expires.
- Connection or transport encounters an error.

The completed metric must increment exactly once per call. If incremented in both `onCancel` and `close` without deduplication, `CANCELLED` RPCs may be double-counted.

On the server, client cancellations or deadline expirations may both be observed as `CANCELLED`. Clients typically distinguish explicit cancellation from deadline expiry via their final status: `CANCELLED` or `DEADLINE_EXCEEDED`, respectively. Therefore, server-side metrics cannot always classify the root cause from the `onCancel` callback alone. When differentiation is needed, combine client metrics, deadline context, and traces; do not infer that every server-side `CANCELLED` means a user clicked a cancel button.

For streaming RPCs, record `completed` only when the entire call finishes. Do not increment the counter in every `onNext`. If you need to measure messages, use separate metrics:

~~~text
grpc.server.messages.sent
  tags: service, method

grpc.server.messages.received
  tags: service, method
~~~

## 7. Calculating Request Rate and Total RPC Count

Counters store cumulative totals since process startup or since the backend started tracking the series. Dashboards usually need two forms:

- **Rate:** RPCs per second over a recent window, suitable for observing current load.
- **Increase:** total additional RPCs over a period of time, suitable for hourly/daily reporting.

When Micrometer exports to Prometheus, the meter name `grpc.server.calls` is typically normalized to `grpc_server_calls_total`. Example PromQL:

~~~promql
# RPCs per second by service and method, across all statuses.
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)

# Total completed RPCs in one hour by service and method.
sum by (service, method) (
  increase(grpc_server_calls_total[1h])
)

# RPCs by status to detect error spikes.
sum by (service, method, status) (
  rate(grpc_server_calls_total[5m])
)
~~~

Final metric and label names depend on the registry/exporter and naming normalization rules. Check the actual scrape endpoint before adding queries to a dashboard. If using OpenTelemetry Collector or another backend, query syntax will differ, but the principle of grouping by service/method remains the same.

Do not calculate rate by dividing the current counter value by process uptime if your goal is load over the last 5 minutes. Use the backend's `rate`/`increase` functions to handle counter resets when a process restarts.

## 8. Reading Metrics Together with Status and Latency

Looking only at RPC count can be misleading. Increased traffic could be normal growth or a retry storm. Pair call counts with status and duration:

| Observation | Possible Indication | What to Check |
| --- | --- | --- |
| RPC count increases, latency stable, low errors | Normal load growth. | Capacity and traffic trends. |
| RPC count increases alongside UNAVAILABLE | Retry storm or unstable instance/service. | Retry policy, endpoint health, connection state. |
| RPC count stable but DEADLINE_EXCEEDED increases | Slow service or overly short deadline. | Duration, queueing, dependency latency. |
| Started increases but completed is low | Many long-running calls or missing terminal instrumentation. | In-flight gauge, stream duration, cleanup path. |
| One method spikes suddenly | New client, RPC call loop, or business flow change. | Release, caller, traces, and request rate. |
| Client count higher than server count | Calls blocked before server, connection failure, or counting difference. | Client/server metrics, proxy, and transport. |

You should also add:

- Duration histogram by service/method to measure latency.
- Gauge of in-flight RPCs by service/method.
- Counter by status to calculate error rate.
- Retry attempt metric if you need to distinguish logical calls from transport attempts.

Do not overload a single counter to represent multiple types of data by reinterpreting it. Each metric needs a clear name, unit, update timing, and semantics.

## 9. Cardinality and Label Design

Cardinality is the number of distinct label combinations the backend must store. If a service has 20 methods and 6 statuses, the baseline series count is roughly 120 per direction/instance dimension. This is usually a manageable scale.

If you add a request ID with millions of values, each call can create a new time series. The consequence is higher memory usage, ingest cost, slow queries, and potential overload of the metrics backend.

Should use:

- Service/method names taken from the API descriptor.
- Status codes from a finite enum set.
- Direction with two values (`client`/`server`) if sharing a metric family.
- Region/zone if the value set is small, stable, and genuinely needed for operations.

Avoid:

- Unbounded user ID, account ID, order ID, or tenant ID.
- Trace ID, span ID, or request ID.
- Ephemeral IP addresses/ports or short-lived pod hostnames.
- Exception messages, error descriptions, or arbitrary metadata.
- Full URLs/paths containing dynamic parameters.

Per-request identifying details belong in traces/logs. Metrics are for aggregating trends and alerting.

## 10. Metrics in a Spring gRPC System

In a Spring application, `MeterRegistry` is typically managed as a bean when the project integrates Micrometer. Interceptors should also be managed following the application lifecycle and share the same registry:

~~~java
@Configuration
class GrpcMetricsConfiguration {

    @Bean
    RpcCountServerInterceptor rpcCountServerInterceptor(
            MeterRegistry meterRegistry) {
        return new RpcCountServerInterceptor(meterRegistry);
    }
}
~~~

The bean above only creates the interceptor; the application still needs to register it with the gRPC server via the extension point of the starter in use. Do not assume every starter automatically attaches all `ServerInterceptor` beans. Check the starter's documentation/version and verify that metrics appear after a test RPC.

If using the OpenTelemetry Java agent or a gRPC instrumentation library that already collects RPC metrics automatically, avoid installing an additional interceptor that counts with the same semantics. You can use the standard metrics provided by the instrumentation or custom metrics, but clearly document the source and meaning. If using both custom metrics and automatic instrumentation, place them in different namespaces and verify they are not summed twice.

## 11. Testing the RPC Count Metric

An interceptor test can use `SimpleMeterRegistry` to verify counters:

~~~java
@Test
void countsOneCompletedRpcByServiceAndMethod() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    RpcCountServerInterceptor interceptor =
            new RpcCountServerInterceptor(registry);

    // Use an in-process server with the interceptor attached and invoke a successful RPC.
    // After the client receives the terminal callback, verify:
    double started = registry.get("grpc.server.calls.started")
            .tag("service", "inventory.Inventory")
            .tag("method", "GetStock")
            .counter()
            .count();

    double completed = registry.get("grpc.server.calls")
            .tag("service", "inventory.Inventory")
            .tag("method", "GetStock")
            .tag("status", "OK")
            .counter()
            .count();

    assertEquals(1.0, started);
    assertEquals(1.0, completed);
}
~~~

The test snippet above illustrates the assertion part; the in-process fixture must actually attach the interceptor to the server and wait for the call to finish before reading the registry. Add cases for:

1. Calling two different methods; verify counters are separated by method.
2. Calling two services with the same method name; verify the service label prevents series collision.
3. Server returning an error; verify the status label reflects the final status.
4. Client cancelling; verify there is only one terminal count even when `onCancel` and `close` run close together.
5. Calling a multi-message streaming RPC; verify the RPC counter increments only once.
6. Retrying a call; verify the instrumentation's logical call/attempt semantics match documentation and tests.
7. Checking that the label set does not contain request ID, user ID, or payload.

Tests with `SimpleMeterRegistry` verify in-process meter logic. Integration tests with a Prometheus/OpenTelemetry exporter verify actual metric names, labels, and queries after normalization.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| A long stream increments the counter per message | Incrementing the RPC counter in onNext. | Increment the terminal counter only once per call; create a separate message counter. |
| RPC is counted twice on cancellation | Both onCancel and close record the metric. | Use AtomicBoolean or an idempotent lifecycle recorder. |
| Cannot tell which method has increased load | Only attaching the service label or omitting method. | Extract full service/method from MethodDescriptor. |
| Dashboard has too many series | Using user/request/trace ID as labels. | Keep labels bounded; move detailed identifiers to traces/logs. |
| Client and server counts do not match | Measured at different boundaries or errors occur before the server receives the call. | Keep direction separate and understand each metric's semantics. |
| Retries make count higher than business operations | Counting RPC attempts as logical operations. | Define RPC count, attempt count, and business operation count separately. |
| CANCELLED status is interpreted as user-initiated cancellation | Server cannot always distinguish cancellation causes. | Cross-reference client status, deadline, and traces. |
| Metrics do not appear in Prometheus | Interceptor is not registered or exporter is not scraping the meter. | Check server wiring, registry, and scrape endpoint. |

## 13. Hands-On Exercises

1. Write a `ServerInterceptor` that counts started and completed RPCs by full service name, method, and status.
2. Test a unary method and a streaming method; prove that a multi-message stream increments the RPC counter only once.
3. Add a `ClientInterceptor` or equivalent instrumentation to measure client calls; document whether the metric counts logical calls or attempts.
4. Export Micrometer metrics to Prometheus; build `rate` and `increase` queries by service/method.
5. Create a dashboard showing RPC rate, status distribution, and p95 latency per method.
6. Add a cancellation race test to verify the terminal counter does not increment twice.
7. Audit cardinality by confirming metric labels contain only service, method, status, and approved bounded dimensions.

After this lesson, you should be able to define when an RPC is counted, use a Counter for total calls, group by service/method/status, and guarantee each call has only one terminal count. By combining RPC count with latency, status, in-flight, and retry metrics, operations teams can spot methods experiencing load spikes or errors in a Spring gRPC system without overloading the metrics backend with high cardinality.
