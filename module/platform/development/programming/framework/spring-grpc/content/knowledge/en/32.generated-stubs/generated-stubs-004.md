# Immutable Stubs and Deadline Configuration

A generated stub in gRPC Java is a client object representing a service and holding references to a Channel and CallOptions. Stubs are designed to be **immutable**: configuration methods such as withDeadlineAfter, withDeadline, withWaitForReady, or withCompression return a new stub instead of mutating the existing object.

This property lets a Spring application share a base stub across many requests without one request's configuration affecting another. When invoking an RPC, create a derived stub with an appropriate deadline for that call. In particular, withDeadlineAfter() computes the deadline at the moment the derived stub is created; if you store that stub long-term and reuse it later, the underlying absolute deadline keeps ticking and will eventually expire.

## 1. What Does a Generated Stub Contain?

After compiling a .proto file, the plugin generates client classes per service. For example, for PaymentService, gRPC Java typically generates:

- PaymentServiceBlockingStub: synchronous calls, returning results directly or throwing StatusRuntimeException.
- PaymentServiceStub: asynchronous calls via StreamObserver.
- PaymentServiceFutureStub: uses ListenableFuture for supported unary methods.

Creating a stub from a channel:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("payment.internal", 9090)
    .useTransportSecurity()
    .build();

PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub =
    PaymentServiceGrpc.newBlockingStub(channel);
~~~

The channel manages connections and transport. The stub is a lightweight wrapper around the service, channel, and call options. Do not create a new channel for every RPC; channels are typically reused throughout the application lifecycle and closed when the Spring application context stops.

## 2. Immutability Means Configuration Produces a New Stub

Each configuration call returns a new object:

~~~java
var baseStub = PaymentServiceGrpc.newBlockingStub(channel);

var shortBudgetStub =
    baseStub.withDeadlineAfter(300, TimeUnit.MILLISECONDS);

var longerBudgetStub =
    baseStub.withDeadlineAfter(1500, TimeUnit.MILLISECONDS);
~~~

baseStub is unchanged after those two statements. shortBudgetStub and longerBudgetStub have their own CallOptions while still using the same channel.

A common mistake is calling a configuration method and ignoring its return value:

~~~java
baseStub.withDeadlineAfter(300, TimeUnit.MILLISECONDS);
PaymentResponse response = baseStub.getPayment(request);
~~~

The first statement creates a derived stub and discards it. The actual RPC is still invoked on baseStub, so the 300 ms deadline is never applied. You must invoke the RPC on the returned object:

~~~java
PaymentResponse response = baseStub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

## 3. Sharing a Base Stub in a Spring Application

Because stubs are immutable, you can create a base stub once and inject it into client services. Example when the application manages the channel directly:

~~~java
@Configuration
public class PaymentGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel paymentChannel() {
        return ManagedChannelBuilder
            .forAddress("payment.internal", 9090)
            .useTransportSecurity()
            .build();
    }

    @Bean
    PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub(
            ManagedChannel paymentChannel) {
        return PaymentServiceGrpc.newBlockingStub(paymentChannel);
    }
}
~~~

This example manages the channel directly; if the Spring gRPC starter already creates a channel, use the starter-managed channel instead of creating a duplicate one. Endpoint, TLS, interceptor, and lifecycle configuration should follow the integration points of the starter in use.

Service using the base stub:

~~~java
@Service
public class PaymentGateway {

    private final PaymentServiceGrpc.PaymentServiceBlockingStub baseStub;

    public PaymentGateway(
            PaymentServiceGrpc.PaymentServiceBlockingStub baseStub) {
        this.baseStub = baseStub;
    }

    public PaymentResponse getPayment(PaymentRequest request) {
        return baseStub
            .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
            .getPayment(request);
    }
}
~~~

Each call to getPayment creates a new derived stub with a 500 ms budget. Multiple threads can use baseStub concurrently; there is no need to store derived stubs in shared mutable fields.

## 4. Relative Deadlines and Derived Stub Lifecycle

withDeadlineAfter(duration, unit) converts a relative duration into a Deadline at the time the method is called. A Deadline represents an expiration point on the process's monotonic clock, not a countdown that resets every time an RPC is sent.

Avoid creating a stub with a relative deadline in a constructor and reusing it forever:

~~~java
// Avoid: the deadline starts ticking from the moment the bean is created.
private final PaymentServiceBlockingStub timedStub =
    baseStub.withDeadlineAfter(500, TimeUnit.MILLISECONDS);
~~~

After the application has been running for more than 500 ms, RPCs using timedStub can expire immediately. The right approach is to create the derived stub close to when each logical RPC begins:

~~~java
public PaymentResponse getPayment(PaymentRequest request) {
    var callStub = baseStub.withDeadlineAfter(
        500, TimeUnit.MILLISECONDS);
    return callStub.getPayment(request);
}
~~~

If you need to share the same expiration point across multiple downstream calls belonging to a parent request, use withDeadline(Deadline) with a deadline captured from the parent context. That is intentional because child calls must terminate within the parent request's budget.

## 5. Preserving the Parent Request's Deadline

When a Spring gRPC service calls another service, the child call's deadline must not exceed the parent call's remaining deadline. You can retrieve the deadline from Context.current() and pick the earlier of the parent deadline and the downstream call's own budget:

~~~java
private PaymentServiceBlockingStub stubForCurrentCall(
        Duration childBudget) {

    Deadline childDeadline = Deadline.after(
        childBudget.toNanos(), TimeUnit.NANOSECONDS);

    Deadline parentDeadline = Context.current().getDeadline();
    if (parentDeadline != null
            && parentDeadline.isBefore(childDeadline)) {
        childDeadline = parentDeadline;
    }

    return baseStub.withDeadline(childDeadline);
}
~~~

This helper example assumes childBudget has already been validated as positive. If the parent deadline has already expired, the child call expires immediately; do not invent a fresh budget to extend the parent request. If you need to reserve time for the parent service to process the response, subtract that reserve from the child budget before creating the deadline.

gRPC Java also uses the current context when creating a client call. However, when offloading work to another executor, you need to propagate context via Context.wrap(...) or a context-propagating executor; otherwise, the task may no longer see the parent request's deadline/cancellation.

## 6. Choosing Deadlines by Method Type

Do not apply a single long timeout to an entire service just because one method is slow. You can create helpers or wrappers aligned with business budgets:

| Method | Example Budget | Reason |
| --- | ---: | --- |
| GetPayment | 300–500 ms | Fast read query |
| CreatePayment | 1–2 s | Needs validation, transaction write, and response |
| GenerateStatement | 5–15 s | Bounded report processing |
| WatchPaymentEvents | Per session policy | Long-lived stream requires session lifetime, idle timeout, and reconnect |

These numbers are illustrative. Choose based on SLA, p95/p99 latency, payload size, and caller budget. For long-lived streams, do not hold a derived stub with an infinite deadline; use an explicit session policy and establish calls with a defined lifetime.

## 7. Applying Deadlines to Blocking, Async, and Future Stubs

All generated stub types expose CallOptions configuration APIs. Blocking stub:

~~~java
PaymentResponse response = blockingStub
    .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

Async stub:

~~~java
asyncStub.withDeadlineAfter(400, TimeUnit.MILLISECONDS)
    .getPayment(request, new StreamObserver<PaymentResponse>() {
        @Override
        public void onNext(PaymentResponse response) {
            handleResponse(response);
        }

        @Override
        public void onError(Throwable error) {
            Status status = Status.fromThrowable(error);
            handleFailure(status);
        }

        @Override
        public void onCompleted() {
            finishCall();
        }
    });
~~~

Future stub for unary methods:

~~~java
ListenableFuture<PaymentResponse> result =
    futureStub.withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .getPayment(request);
~~~

With blocking stubs, timeouts are typically observed via StatusRuntimeException. With async stubs, errors arrive via onError; with future stubs, the future completes exceptionally. Handle DEADLINE_EXCEEDED according to the API style and avoid blocking callback threads to wait for results.

## 8. Immutable Stubs and Thread Safety

Generated gRPC Java stubs inherit the immutable model of AbstractStub. A base stub can be shared across many requests, and independent derived instances can be created on each thread. CallOptions is also immutable; configuration operations return a new CallOptions instance.

However:

- Do not place request data or mutable state into shared fields of a wrapper around a stub.
- Do not cache a relative deadline created at startup to reuse for later requests.
- Do not close the channel when a single request finishes; the channel may be serving many calls.
- Do not create a new channel for each derived stub; withDeadlineAfter only creates a new wrapper and does not need a new transport.
- Close the channel according to the application lifecycle after stopping incoming calls.

## 9. Deadlines and Retries Share the Same Expiration Point

When a gRPC retry policy issues multiple attempts for one logical call, those attempts remain subject to that call's deadline. If implementing retries in application code, keep the same Deadline across all attempts and backoffs:

~~~java
Deadline overall = Deadline.after(1200, TimeUnit.MILLISECONDS);

for (int attempt = 1; attempt <= 3; attempt++) {
    if (overall.isExpired()) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("overall budget exhausted")
            .asRuntimeException();
    }

    try {
        return baseStub.withDeadline(overall)
            .getPayment(request);
    } catch (StatusRuntimeException ex) {
        if (ex.getStatus().getCode() != Status.Code.UNAVAILABLE
                || attempt == 3) {
            throw ex;
        }
        // Backoff must fit within the remaining overall budget.
    }
}
throw Status.UNAVAILABLE.asRuntimeException();
~~~

Do not call withDeadlineAfter(1200, MILLISECONDS) at the start of each attempt. Doing so grants the full duration again and causes total retry time to exceed the caller's SLA. For commands with side effects, an idempotency key is required because an expired deadline does not prove the server did not commit.

## 10. Testing Immutability and Deadlines

Key behaviors can be verified using a gRPC in-process server:

1. Create a base stub with no default deadline.
2. Call a slow method through a derived stub with a short deadline and verify DEADLINE_EXCEEDED.
3. Call a subsequent fast method through the base stub and verify it still succeeds.
4. Create two derived stubs with different budgets; verify one call does not alter the other.
5. Create a stub with a relative deadline, wait past that duration before invoking, and verify the deadline has already expired—reinforcing why timed stubs must not be stored in long-lived fields.
6. In nested calls, verify the child deadline does not exceed the parent deadline.

Use latches to control a slow server instead of long Thread.sleep calls. Tests should verify statuses, event ordering, and cleanup rather than asserting exact timeout durations down to the millisecond.

## 11. Common Pitfalls and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling withDeadlineAfter and ignoring the returned stub | RPC does not use the new deadline | Invoke the method on the derived stub |
| Caching a derived stub with a relative deadline from startup | Later calls can expire immediately | Create a new derived stub for each logical RPC |
| Recreating the channel on every call | Wastes connections, threads, and transport resources | Reuse a Spring-managed channel |
| Granting a fresh deadline per retry | Total duration exceeds the caller's budget | Keep one shared Deadline for the logical RPC |
| Child deadline longer than parent deadline | Downstream may run after the caller has already expired | Pick the earlier of parent and child budgets |
| Using one timeout for every method | Fast methods wait too long or long methods hit false timeouts | Set budgets per method/SLA |

## 12. Takeaways and Self-Check

**Generated stubs are immutable and safe to share; configuring a deadline produces a new derived stub.** withDeadlineAfter() computes the expiration point immediately when called, so create stubs with relative deadlines close to when the RPC starts. Keep channels shared, preserve parent deadlines for nested calls, and reuse a single deadline across all retries.

Self-check:

1. Why does withDeadlineAfter() not mutate the base stub?
2. What happens if you cache a stub on which withDeadlineAfter() was called inside a Spring singleton?
3. When should you use withDeadline(Deadline) instead of withDeadlineAfter(...)?
4. Why can generated stubs be shared across threads while mutable request state should not?
5. How do you prevent downstream deadlines and retries from exceeding the caller's deadline?

Understanding immutability and deadline lifecycles properly enables Spring gRPC clients to reuse channels and stubs effectively, enforce per-RPC budgets, and avoid spurious timeouts caused by reusing expired derived stubs.
