# Status Code Distribution

Counting total RPCs and measuring latency reveal load and processing speed, but do not explain why calls fail. The distribution of gRPC status codes shows the rates of success, timeouts, cancellations, input errors, permission errors, and infrastructure failures. When grouping statuses by service and method, operations teams can spot a method starting to return `UNAVAILABLE` after a rollout or `DEADLINE_EXCEEDED` spiking on a specific dependency.

**Status code distribution** is the distribution of finished RPCs by gRPC status code, typically grouped by service, method, and observation side. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on collecting terminal statuses exactly once, reading status distributions on the client/server, and using the data to distinguish business errors from infrastructure failures.

## 1. Status Code as the Final Outcome of an RPC

gRPC uses status codes to represent the final outcome of an RPC. A call that completes successfully has status `OK`; a call that fails or is cancelled has a different status. Status is transmitted with the terminal event, usually via HTTP/2 trailers.

The status distribution metric must count **once per RPC when the call enters a terminal state**. Do not increment the counter each time the server sends a message or the client receives a message. A server-streaming RPC that sends 10,000 messages and finishes with `OK` still contributes one call to the `OK` bucket.

Keep these quantities distinct:

| Quantity | When Is It Counted? | Question |
| --- | --- | --- |
| RPC started | When the call starts at the instrumentation boundary. | How many calls were initiated/received? |
| RPC completed by status | When the call finishes, tagged with terminal status. | Which status did calls terminate with? |
| RPC in-flight | Incremented on start, decremented on completion. | How many calls are currently running? |
| Message count | Each message sent or received. | How many messages does the stream exchange? |
| Logical operation | When a business intent starts/finishes. | Did a business operation succeed or fail? |

Status distribution is typically based on completed RPCs. If you only measure `started`, you cannot tell whether calls succeeded or failed. If you only measure `completed`, you may miss long-running calls; add an in-flight gauge to track them.

## 2. Status Codes to Recognize

gRPC defines a finite set of status codes. These values are well suited as metric labels:

| Status | Common Meaning | Investigation Direction |
| --- | --- | --- |
| OK | RPC completed successfully. | Track as the success baseline. |
| CANCELLED | Call was cancelled by the caller or associated context. | Check client lifecycle, deadline, and disconnects. |
| UNKNOWN | Error not mapped to a specific status. | Check exception mapping and server logs. |
| INVALID_ARGUMENT | Request is invalid independent of system state. | Check validation and caller contract. |
| DEADLINE_EXCEEDED | Call did not finish within the deadline. | Check latency, queues, and dependencies. |
| NOT_FOUND | Requested resource does not exist. | Check identifiers and data. |
| ALREADY_EXISTS | Resource or unique key already exists. | Check create semantics and idempotency. |
| PERMISSION_DENIED | Caller lacks permission for the operation. | Check authorization policy. |
| RESOURCE_EXHAUSTED | Quota or resource exhausted. | Check rate limits, thread/connection pools, and capacity. |
| FAILED_PRECONDITION | System state does not meet prerequisites for execution. | Check state transitions and prerequisites. |
| ABORTED | Operation aborted due to conflict or concurrency condition. | Check transactions/conflicts and retry at the appropriate layer. |
| OUT_OF_RANGE | Value is outside the valid range. | Check range bounds and pagination cursors. |
| UNIMPLEMENTED | Method or feature is not supported. | Check API version and server implementation. |
| INTERNAL | Internal error that should not be treated as a normal request error. | Check exceptions, invariants, and dependencies. |
| UNAVAILABLE | Service or transport is currently unavailable to serve. | Check instances, network, load balancer, and dependencies. |
| DATA_LOSS | Severe data loss or corruption. | Investigate persistence, replication, and recovery. |
| UNAUTHENTICATED | Caller does not have valid authentication. | Check credentials, tokens, and authentication. |

A status code is a contract between service and caller, not a complete root-cause taxonomy. For example, `UNAVAILABLE` can result from a stopped server, a proxy error, or an unavailable dependency. `DEADLINE_EXCEEDED` does not prove the server did not commit side effects. `CANCELLED` on the server also does not necessarily mean a user clicked a cancel button; deadline expiration or peer disconnect can lead to cancellation status on the server side.

## 3. Grouping Statuses to Read System Health

Dashboards usually need three views:

- **Success rate:** percentage of RPCs terminating with `OK`.
- **Error/status distribution:** rate of each non-`OK` status.
- **Status volume:** absolute count/rate of each status over time.

Do not lump every non-`OK` status into a single group. A spike in `INVALID_ARGUMENT` may indicate callers sending malformed requests; a spike in `UNAVAILABLE` may indicate an infrastructure issue; a spike in `PERMISSION_DENIED` may indicate a policy change. The remediation actions differ greatly.

You can group statuses for high-level overview while keeping raw metrics per individual status:

| Observation Group | Representative Statuses | Usage |
| --- | --- | --- |
| Success | OK | Baseline and success rate. |
| Caller/request | INVALID_ARGUMENT, NOT_FOUND, ALREADY_EXISTS, OUT_OF_RANGE | Track contracts, validation, and input data. |
| Identity/access | UNAUTHENTICATED, PERMISSION_DENIED | Track authentication and authorization. |
| Capacity/state | RESOURCE_EXHAUSTED, FAILED_PRECONDITION, ABORTED | Track quotas, concurrency, and state machines. |
| Availability/runtime | UNAVAILABLE, INTERNAL, UNKNOWN, UNIMPLEMENTED, DATA_LOSS | Investigate infrastructure, software bugs, and API compatibility. |
| Lifecycle/time | CANCELLED, DEADLINE_EXCEEDED | Track caller cancellations, timeouts, and processing time. |

This grouping is a dashboard organization technique; do not alter gRPC status codes, and do not replace the `status` label with a `group` label when detailed investigation is needed.

## 4. Metric and Label Design

A completed metric on the server can be named as follows:

```text
grpc.server.calls
  type: Counter
  tags: service, method, status

grpc.client.calls
  type: Counter
  tags: service, method, status
```

Service/method names come from the Protobuf `MethodDescriptor`, for example:

| Full method name | service | method |
| --- | --- | --- |
| inventory.Inventory/GetStock | inventory.Inventory | GetStock |
| orders.OrderService/CreateOrder | orders.OrderService | CreateOrder |

Status comes from `Status.Code.name()`, which is a finite set. If sharing one metric family for client and server, add a `direction` label with two values (`client`/`server`); the simpler approach is keeping separate metric names to avoid confusion.

Do not add request ID, trace ID, user ID, order ID, exception message, or arbitrary metadata as labels. Every new value can create a new time series; high-cardinality identifiers increase memory usage and ingest costs in the metrics backend. Use traces/logs for individual requests, and metrics for aggregated trends.

## 5. Collecting Server Status with ServerInterceptor

`ServerInterceptor` sees the method when the server receives a call and can wrap `ServerCall` to record the status when the call closes. You also need to handle the `onCancel` callback because a call cancelled by the peer may not go through an application-initiated `close` path:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcStatusServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public RpcStatusServerInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String fullMethod =
                call.getMethodDescriptor().getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        AtomicBoolean recorded = new AtomicBoolean();
        java.util.function.Consumer<Status> record = status -> {
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
                        record.accept(status);
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                record.accept(Status.CANCELLED);
                super.onCancel();
            }
        };
    }
}
```

`AtomicBoolean` guarantees one terminal count per call if `onCancel` and `close` occur together. Server-side `onCancel` is recorded as `CANCELLED` because that is the cancellation state observed by the server. It does not necessarily indicate whether the client-side final status was `CANCELLED` or `DEADLINE_EXCEEDED`.

The interceptor must be registered with the server managed by the Spring gRPC starter. Registration depends on the starter/version: use the official extension point or the server builder provided by the starter. Do not create a second server just to attach a metrics interceptor.

## 6. Collecting Client Status with ClientInterceptor

Client-side `onClose` receives the final status observed by the client application. This is the right place to measure status distribution from the caller's perspective:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;

public final class RpcStatusClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public RpcStatusClientInterceptor(MeterRegistry registry) {
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

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

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
```

Attach the interceptor to the channel via `ManagedChannelBuilder.intercept(...)` or the corresponding Spring starter extension point. A client call may have internal retries; the interceptor's position in the call chain determines whether instrumentation observes the logical call or each attempt. Do not name a metric as an attempt count without verifying the semantics of the version and retry mechanism in use.

## 7. Why Can Client and Server Statuses Differ?

Client and server observe the call at opposite ends of the transport. In several scenarios, the status recorded on each side can differ:

| Scenario | Server May Record | Client May See |
| --- | --- | --- |
| Server returns an error status | Status returned by the application, e.g., NOT_FOUND. | Same status if the response reaches the client. |
| Client explicitly cancels | onCancel, usually recorded as CANCELLED. | CANCELLED. |
| Client deadline expires | Server context is cancelled; interceptor may record CANCELLED if onCancel arrives before close. | DEADLINE_EXCEEDED. |
| Server closes with OK but response is lost on transport | Server already recorded OK. | UNAVAILABLE or another transport error. |
| Client cannot connect to server | Server may not receive the call so no server metric exists. | UNAVAILABLE or DEADLINE_EXCEEDED. |

Therefore, do not sum server counters and client counters to get "total RPCs". They are two independent perspectives. When root-cause analysis is needed, correlate via trace context or request correlation in logs, without using trace IDs as metric labels.

## 8. Calculating Status Rate and Error Ratio in Prometheus

Suppose Micrometer Counter `grpc.server.calls` is exported as `grpc_server_calls_total`. RPC rate by status:

```promql
sum by (service, method, status) (
  rate(grpc_server_calls_total[5m])
)
```

Total request rate by service and method:

```promql
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)
```

Ratio of non-OK statuses:

```promql
sum by (service, method) (
  rate(grpc_server_calls_total{status!="OK"}[5m])
)
/
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)
```

Ratio of `UNAVAILABLE`:

```promql
sum by (service, method) (
  rate(grpc_server_calls_total{status="UNAVAILABLE"}[5m])
)
/
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)
```

Percentages can be obtained by multiplying the result by 100 in the query or formatting in the dashboard. When the denominator is 0, the query may return `NaN`/no data; dashboards should display "no traffic" rather than misleadingly reporting a 0% error rate.

Exported metric and label names depend on the registry/exporter. Inspect the actual series before using queries. If the metric includes `direction`, filter `direction=server` or `client` to avoid mixing the two sides.

## 9. Interpreting Status Distribution by Method

An increase in a status should be placed in the context of request rate, latency, and deployment changes:

| Signal | Possibilities to Consider | Next Action |
| --- | --- | --- |
| UNAVAILABLE spikes across many methods | Instance, network, proxy, or dependency is unavailable. | Check subchannels, health, rollouts, and infrastructure. |
| DEADLINE_EXCEEDED increases on one method | Method or its dependency is slower than its budget. | Inspect latency histograms, deadlines, and downstream spans. |
| RESOURCE_EXHAUSTED increases | Quotas or capacity are hit. | Check rate limits, concurrency, pools, and retry storms. |
| INVALID_ARGUMENT spikes after release | Client/server contract or validation changed. | Compare client versions, proto contracts, and request validation. |
| UNAUTHENTICATED increases | Expired credentials, invalid tokens, or identity provider failure. | Check authentication metadata and token issuer. |
| PERMISSION_DENIED increases | Authorization policy changed or caller lacks permissions. | Check authorization rules; do not auto-retry. |
| CANCELLED increases | Callers leaving, parent context cancelled, or transport lifecycle changed. | Cross-reference client metrics, deadlines, and tracing. |
| INTERNAL/UNKNOWN increases | Unmapped exceptions or unexpected bugs. | Inspect logs with trace IDs and exception mapping. |

A non-OK status can be valid business behavior. For instance, `NOT_FOUND` when looking up a non-existent resource is not necessarily an incident. Define baselines/alerts per method and product expectations, rather than alerting on every non-`OK` status with the same severity.

## 10. Distinguishing gRPC Status from Exceptions and HTTP Statuses

A gRPC status is the outcome of an RPC, not an HTTP status code. gRPC typically runs over HTTP/2, but HTTP status at the transport layer and gRPC status in trailers have different semantics. Do not mechanically map HTTP 404 to gRPC `NOT_FOUND` or HTTP 503 to `UNAVAILABLE` without understanding the error source.

On the server, the application should intentionally convert business errors to statuses:

```java
throw Status.NOT_FOUND
        .withDescription("Inventory item not found")
        .asRuntimeException();
```

Do not put stack traces or sensitive data into descriptions returned to the client. Log exception details in server logs with trace/correlation IDs.

On the client, you can extract the status from a throwable:

```java
Status status = Status.fromThrowable(failure);
Status.Code code = status.getCode();

if (code == Status.Code.UNAVAILABLE) {
    // Apply retry policy if the operation is safe.
}
```

If the throwable does not contain a recognizable gRPC status, `Status.fromThrowable` typically returns `UNKNOWN`. Consequently, an increase in `UNKNOWN` can indicate unmapped exceptions or non-gRPC errors.

## 11. How Retries Affect Status Distribution

Retries complicate how statuses appear:

- A logical client call may have a failed attempt followed by a successful attempt.
- The client may ultimately receive `OK` even though an earlier attempt encountered `UNAVAILABLE`.
- The server that received the earlier attempts still records the status of each RPC it handled.
- Client instrumentation may only record the terminal status of the logical call, depending on interceptor placement and retry implementation.

Thus, client and server status distributions do not have to match. If you need attempt counts, retry successes, retry exhaustion, and logical call counts, create separate metrics using instrumentation with verified semantics. Do not infer retry count by subtracting client count from server count.

Retry policies must match the status and operation semantics:

| Status | Common Guideline |
| --- | --- |
| UNAVAILABLE | Can be retried with backoff/jitter if the operation is safe and deadline remains. |
| RESOURCE_EXHAUSTED | Retry only when transient and bounded by policy; retries can worsen overload. |
| ABORTED | May require retrying the entire transaction/operation at the business layer. |
| FAILED_PRECONDITION | Retry only after the prerequisite state has changed. |
| DEADLINE_EXCEEDED | Do not assume the operation did not commit; require idempotency/status lookup before retrying. |
| CANCELLED | Usually respect caller intent; do not auto-retry a call the caller abandoned. |
| INVALID_ARGUMENT, PERMISSION_DENIED, UNAUTHENTICATED | Usually require fixing the request/credentials/policy rather than retrying as-is. |

These are operational guidelines, not a default retry table for every service. Retryable statuses must be configured per method, idempotency, and deadline budget.

## 12. Status Distribution for Unary and Streaming

The status counter still increments once per RPC whether the call is unary or streaming. You can add an `rpc_type` label with a fixed set of values:

| rpc_type | Example |
| --- | --- |
| unary | One request, one response. |
| client_streaming | Multiple request messages, one response. |
| server_streaming | One request, multiple response messages. |
| bidi_streaming | Multiple messages in both directions. |

For long-lived streams, the status appears only when the stream terminates. An open stream does not belong to any terminal status counter until it completes, errors, or is cancelled. Use an active stream gauge to observe currently open streams.

Do not count each `onNext` as an RPC status. If you want to track message-level errors, create a separate metric and clearly define message processing outcomes as distinct from the terminal status of the entire stream.

## 13. Testing Status Instrumentation

Use `SimpleMeterRegistry` and an in-process gRPC server/channel to verify that interceptors record statuses accurately:

1. Invoke a successful unary RPC; verify a counter with status `OK`.
2. Have the service return `NOT_FOUND`; verify the status label is `NOT_FOUND`.
3. Invoke two different methods; verify series are separated by method.
4. Cancel a client call; verify the server terminal count increments only once even if `onCancel` and `close` race.
5. Set a short deadline; compare client `DEADLINE_EXCEEDED` with the cancellation status observed by the server.
6. Invoke a multi-message streaming RPC; verify the terminal counter increments only once when the stream ends.
7. Simulate a client failing to connect; verify the client has a status while the server has no completed call if the request never reached the server.
8. Verify labels do not contain request ID, trace ID, or data from arbitrary metadata.

Tests should wait for the terminal callback or a server latch before reading the registry. Do not use a fixed sleep to guess when the counter has incremented. With an actual exporter, also verify metric and label names after Prometheus/OpenTelemetry normalization.

## 14. Dashboards and Alerting

A useful status distribution dashboard should include:

- Stacked time series or ratio tables of statuses by service/method.
- Success rate and error ratio over a 5-minute window.
- `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, and `INTERNAL` broken out separately.
- Request rate to put error ratios in the context of the denominator.
- Latency p95/p99 to distinguish slowness from fast failures.
- Client/server direction to identify calls failing before reaching the server.

Alerts should be based on both ratio and minimum volume. For example, 1 error out of 2 requests produces a 50% error ratio, which may not be sufficient evidence of a widespread outage. Conversely, a 2% error rate across tens of thousands of RPCs can impact many callers. Use time windows, minimum traffic thresholds, and severity aligned with the method/SLO.

## 15. Cardinality and Security

Status is a small enum set, making it suitable as a label. Service and method are also finite according to the API. However, do not add:

- Request ID, trace ID, span ID.
- User, account, tenant, or order ID.
- Exception message, stack trace, or status description.
- Arbitrary metadata sent by clients.
- Ephemeral endpoint addresses if the value set is unbounded.

Status descriptions may contain sensitive data if the application embeds request contents in them. Metrics should only use code names; logs/traces must filter data and comply with security policies. Never expose raw authorization metadata or tokens to explain `UNAUTHENTICATED`.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Status counted per message | Incrementing counter in onNext. | Record one terminal status per RPC; separate message metrics. |
| CANCELLED is double-counted | Both onCancel and close increment the counter. | Use AtomicBoolean or an idempotent lifecycle recorder. |
| Server and client statuses differ | The two sides observe different boundaries and timings. | Keep metrics separate; correlate with traces and deadline context. |
| All errors collapse into INTERNAL | Overly generic exception mapping. | Map business and infrastructure errors to the proper statuses. |
| Treating every non-OK status as a critical incident | Some statuses are normal business outcomes. | Alert based on method, baseline, and SLO. |
| Retries make client see OK despite server errors | Earlier failed attempts succeeded on retry. | Track logical calls and attempts separately. |
| Status metric has high cardinality | Attaching descriptions or IDs as labels. | Use only service, method, status, and bounded dimensions. |
| Server has no metric while client has UNAVAILABLE | Call failed before reaching the server. | Monitor client-side status and transport/proxy. |

## 17. Hands-On Exercises

1. Write a `ServerInterceptor` that records a counter by full service name, method, and terminal status.
2. Write a `ClientInterceptor` that records the final client status and keeps the metric direction separate.
3. Test `OK`, `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAVAILABLE`, `CANCELLED`, and `DEADLINE_EXCEEDED`.
4. Build PromQL queries for status rate, success rate, and error ratio by service/method.
5. Test the `onCancel`/`close` race to verify each RPC produces only one terminal sample.
6. Enable retries for an idempotent unary read; compare client logical status with server attempt statuses.
7. Invoke a multi-message streaming RPC; verify the status counter increments only when the entire stream terminates.
8. Build a dashboard distinguishing caller/request errors, availability errors, deadlines, and authentication errors.

After this lesson, you should know how to collect status distributions by service/method, understand differences between client and server statuses, avoid double-counting on cancellation, and read error rates in the context of request rate, latency, retries, and RPC type. Clear status distributions help operations teams pinpoint the right layer to investigate in a Spring gRPC system without overloading the metrics backend with cardinality.
