# Do Not Leave Deadlines Infinite by Default

In gRPC, if a client does not set a deadline, the call defaults to **having no completion time limit**. The client may keep waiting when the server hangs, a downstream service is slow, or a request gets stuck in a queue. Such calls hold resources longer than intended and make it harder for the system to recover under load.

With **Spring gRPC**, set finite deadlines for normal RPCs right at the client boundary, based on each business group's budget. Some long-lived streams may need their own lifecycle, but they must be explicit exceptions designed with idle timeouts, session limits, cancellation, and reconnection mechanisms. The goal is **to never let an RPC wait indefinitely simply because the caller forgot to configure a deadline**.

## 1. Why is having no default deadline risky?

A gRPC call without a deadline can stay open until it finishes, is cancelled, or the channel closes. If the server or downstream does not respond, the client can hold the request, callback, future, and associated resources for a very long time.

~~~mermaid
flowchart TD
    A["Client calls RPC"] --> B{"Has deadline?"}
    B -->|"Yes"| C["Finite time budget"]
    C --> D{"Completes before limit?"}
    D -->|"Yes"| E["Receive response"]
    D -->|"No"| F["DEADLINE_EXCEEDED"]
    B -->|"No"| G["Wait with no time limit"]
    G --> H["Server/downstream hangs"]
    H --> I["Request and resources held"]
~~~

Risks typically cascade in a chain:

- The client holds a pending request.
- The server holds the context, processing state, or subscription.
- The parent service keeps waiting on the child service.
- Thread pools, connection pools, or queues become occupied.
- As load grows, new requests wait longer and trigger additional timeouts in other layers.

A deadline does not replace concurrency limits, queue capacities, or database timeouts. It establishes an **overall time bound for the RPC**, giving other protection mechanisms a clear termination point.

## 2. Setting finite deadlines per call

With gRPC Java, use **withDeadlineAfter** on the stub:

~~~java
GetCustomerRequest request = GetCustomerRequest.newBuilder()
    .setCustomerId("customer-42")
    .build();

GetCustomerResponse response = customerStub
    .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
    .getCustomer(request);
~~~

The returned stub carries the deadline for the next call. The original stub is unchanged, so different budgets can be chosen for each operation:

~~~java
var readStub = customerStub.withDeadlineAfter(
    500, TimeUnit.MILLISECONDS);

var updateStub = customerStub.withDeadlineAfter(
    1500, TimeUnit.MILLISECONDS);
~~~

These numbers are examples only, not universal defaults suitable for every system. A deadline must account for resource wait time, network latency, server processing, and response delivery. Choose budgets according to SLAs, p95/p99 latency under valid load, and headroom for the calling layer to finish.

Do not set an overly long deadline just to avoid timeout errors. Long deadlines can cause requests to hold threads, connections, or processing state longer while the system is overloaded.

## 3. Setting a fallback deadline at the client boundary

If multiple code teams create stubs and can easily forget deadlines, you can apply a **default deadline interceptor**. The interceptor only adds a fallback deadline when the call has no explicit deadline and does not inherit one from a parent context.

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.MethodDescriptor;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.Objects;
import java.util.function.Predicate;

public final class DefaultDeadlineInterceptor
        implements ClientInterceptor {

    private final Duration fallback;
    private final Predicate<String> requiresFiniteDeadline;

    public DefaultDeadlineInterceptor(
            Duration fallback,
            Predicate<String> requiresFiniteDeadline) {
        if (fallback == null || fallback.isZero() || fallback.isNegative()) {
            throw new IllegalArgumentException(
                "fallback deadline must be positive");
        }
        this.fallback = fallback;
        this.requiresFiniteDeadline =
            Objects.requireNonNull(requiresFiniteDeadline);
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        Deadline effective = callOptions.getDeadline();
        Deadline parent = Context.current().getDeadline();

        // Do not let the child call exceed the parent RPC's deadline.
        if (parent != null
                && (effective == null || parent.isBefore(effective))) {
            effective = parent;
        }

        // Only apply fallback to methods covered by the finite-deadline policy.
        if (effective == null
                && requiresFiniteDeadline.test(method.getFullMethodName())) {
            effective = Deadline.after(
                fallback.toNanos(), TimeUnit.NANOSECONDS);
        }

        CallOptions effectiveOptions = effective == null
            ? callOptions
            : callOptions.withDeadline(effective);
        return next.newCall(method, effectiveOptions);
    }
}
~~~

The interceptor above illustrates a general fallback policy. It can be registered on the channel when creating the client:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forTarget(target)
    .useTransportSecurity()
    .intercept(new DefaultDeadlineInterceptor(
        Duration.ofSeconds(2),
        methodName -> !methodName.equals(
            "acme.events.v1.EventService/WatchEvents")))
    .build();
~~~

The predicate in this example excludes a long-lived subscription that already has its own designed lifecycle. When a method is outside the finite-deadline policy and has no deadline from the caller or parent context, the interceptor leaves CallOptions untouched. In a real application, manage the method list through explicit configuration or use a policy that returns a budget by full method name.

In a Spring application, channels may be managed by a starter or configuration beans. Attach the interceptor through the customizer/interceptor registration mechanism supported by the version in use; do not assume all starters share the same configuration properties.

A fallback is only a **safety net**. Methods with different SLAs should still set explicit deadlines at the call site. The interceptor also needs a dedicated policy for long-lived methods; do not apply one short timeout uniformly to every stream.

## 4. Do not override the caller's or parent context's deadline

A dangerous bug is an interceptor that unconditionally calls **withDeadlineAfter** and overwrites a deadline already set by the caller. That can extend a call that was meant to be more tightly bounded.

Safe policy:

1. Preserve the explicit deadline in CallOptions if one is already set.
2. If the parent context has an earlier deadline, use the earlier deadline.
3. Only create a fallback when neither source provides a deadline.
4. Never copy the initial timeout again for each nested call.

For example: the caller has 300 ms remaining, while the client's fallback is 2 seconds. The child call must still end according to the parent deadline, not receive another 2 seconds. Conversely, if the caller sets a 5-second deadline and the fallback policy is only 2 seconds, the fallback should not silently alter the caller's explicit deadline; if the system wants to enforce a maximum ceiling, that should be a separate, explicitly documented and tested **policy cap**.

## 5. Choosing deadlines by RPC type

There is no single right deadline value for every method. Group methods by behavior:

| RPC Group | Typically Appropriate Policy |
| --- | --- |
| Unary data read | Finite deadline based on query latency and SLA |
| Transactional unary command | Enough time to validate, commit, and return result; retries must be safe |
| Nested downstream call | Must not exceed parent request's remaining budget; may set a shorter child limit |
| Client streaming upload | Bounded by size, throughput, and maximum upload session duration |
| Server streaming subscription | Use session lifetime or reconnection policy matching event-delivery needs |
| Health check | Short, consistent deadline to detect unresponsive services |

For methods with different SLAs, configure by full method name or business group. Avoid a single interceptor applying the same timeout to GetCustomer, CreatePayment, and WatchEvents if their characteristics differ.

## 6. Exception: long-lived streams must have an explicit lifecycle

A subscription may be designed to stay open long-term to receive continuous events. Setting a few-second deadline on such a stream would constantly drop connections; yet leaving a stream unbounded without lifecycle management also creates resource-retention risks.

If a method genuinely needs a long-lived stream, treat it as an **intentional exception**, and add:

- An idle timeout or heartbeat to detect connections that are no longer useful.
- Stream limits per user/tenant and across the whole server.
- Queue limits and backpressure when consumers are slow.
- A cancellation handler to stop the producer and close the subscription.
- A maximum session lifetime if infrastructure requires connection rotation.
- A cursor/sequence so the client can reconnect and resume from the last received position.

Do not send heartbeats merely to keep a stream alive without monitoring client state. Heartbeats should help detect dead connections or inactive processes, and must be rate-limited.

## 7. Default deadlines do not replace timeouts in other layers

An RPC with a 2-second deadline can still leave work behind if the server does not propagate cancellation to resources. Each layer needs appropriate limits:

| Layer | Protection Mechanism |
| --- | --- |
| gRPC client | Finite deadline per RPC |
| gRPC server | Check context cancellation and stop work |
| Database | Query timeout, statement cancel, and transaction timeout |
| HTTP client | Connect/read/request timeouts and cancel API |
| Executor | Bounded queue, worker limits, and future cancellation |
| Streaming | Backpressure, idle timeout, session limits, and cleanup |

The overall deadline should encompass component timeouts. For example, if the client deadline is 1 second, the database query timeout should not be 5 seconds; otherwise, the server may keep holding a connection after the client has already timed out.

## 8. Retries must stay within the time budget

Expired deadlines usually produce **DEADLINE_EXCEEDED**, yet this status does not prove the server has not executed side effects. If the client retries an order-creation or payment command, the operation could execute twice.

When retrying:

1. Keep the same idempotency key for the same business intent.
2. Bound total retry duration within the parent request's deadline.
3. Only retry statuses and operations designated as retryable.
4. Use bounded backoff; do not retry continuously until resources are exhausted.
5. If the outcome is uncertain, query status by operation ID before issuing a new command.

A retry policy must not create a new deadline longer than the caller's budget. If the parent request has 100 ms remaining, do not start a retry attempt that needs 2 seconds.

## 9. Testing default deadline policies

Test both the fallback behavior and the exceptions:

- A call with no deadline and no parent context receives the finite fallback.
- A call with an explicit deadline preserves that deadline.
- When the parent context has a shorter deadline, the child call does not exceed the parent deadline.
- Long-lived stream methods follow their own policy instead of receiving a short unary timeout.
- Deadline expiration causes the server to observe cancellation and stop cancellable work.
- Retries stay within the total budget and do not create duplicate side effects.

You can test the interceptor with a mock Channel recording the received CallOptions, or use gRPC in-process with a controlled-delay server. With Spring, integration tests should verify the interceptor is actually attached to the channel created by the application configuration.

## 10. Observing calls without deadlines and timeouts

Track by full method name:

- Number of outbound RPCs without a deadline before fallback is applied.
- Effective deadline and remaining time when the call starts.
- Rates of DEADLINE_EXCEEDED, CANCELLED, and p95/p99 latency.
- Number of tasks still running after the RPC ends.
- Number of long-lived streams, stream age, idle timeouts, and reconnect counts.
- Retry rate and commands deduplicated by idempotency key.

If outbound calls still lack deadlines, determine whether the method is an approved long-lived exception or a code path missing configuration. Do not measure timeout rates alone; also measure work still running after the client finishes the RPC.

## 11. Summary and self-check

gRPC does not automatically set a finite deadline for client calls. Therefore, **normal RPCs need explicit finite deadlines**, chosen according to SLAs and method characteristics. A fallback interceptor can guard calls where a deadline was forgotten, but it must preserve caller/parent context deadlines and apply a separate policy for long-lived streams.

Self-check:

1. What can happen when a gRPC client makes a call without setting a deadline?
2. Why shouldn't a fallback interceptor overwrite a deadline already set by the caller?
3. When can a long-lived stream be exempted from the fallback deadline, and what controls are required?
4. Why must the overall deadline coordinate with query timeouts and HTTP client timeouts?
5. Why do retries after DEADLINE_EXCEEDED need an idempotency key and still need to fit within the caller's budget?

Setting finite deadlines by policy helps Spring gRPC bound wait times, release resources promptly, and prevent a single misconfigured call from impacting the entire service chain.
