# How cancellation differs from a deadline

In gRPC, **cancellation** and **deadline** are related, yet they express two different intents. Cancellation means a call no longer needs to continue; a deadline sets the latest point in time a call is allowed to remain alive. When a deadline expires, gRPC terminates the RPC by cancelling the call. However, a caller can also actively cancel before that point, and a call can be cancelled due to a parent context, channel shutdown, or a lost connection.

Distinguishing the two concepts helps a Spring gRPC client choose the right status, decide whether to retry, and propagate time budgets across services. This lesson belongs to the **Cancellation** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem from Protocol Buffers contracts and generated Java code, supporting unary/streaming RPCs, metadata, deadlines, statuses, interceptors, TLS, integration testing, and observability.

## 1. The two concepts differ in purpose

**Cancellation** is a signal to terminate an RPC before it completes normally. The caller may no longer need the result, such as when a user leaves a screen or the originating HTTP request is cancelled. Cancellation can also come from a parent context or the transport when the peer disappears.

**Deadline** is a time limit for an RPC. The caller sets a duration or deadline; when that point arrives and the RPC has not yet completed, gRPC automatically terminates the call. In gRPC Java, clients typically set a relative duration with an API like withDeadlineAfter(...). Deadlines are represented internally as a point in time and remaining budget, avoiding dependence on identical wall clocks across machines.

| Attribute | Cancellation | Deadline |
| --- | --- | --- |
| Purpose | Stop an RPC because the caller or system no longer needs it to continue. | Bound the maximum time for an RPC to complete. |
| How initiated | Explicit cancel, context cancelled, channel/transport termination. | Configured at call time or via service config; expires automatically over time. |
| Can occur before time expires? | Yes; caller can cancel at any time. | Only expires when the time budget runs out. |
| Is it mandatory? | Can occur even if no deadline is set. | May be unset; in that case the RPC has no finite deadline bound. |
| Status commonly seen on client | CANCELLED when caller actively cancels. | DEADLINE_EXCEEDED when deadline expires. |
| Server side | Context/call is marked cancelled. | When expired, context/call is also cancelled; server can read the deadline to tell whether it has expired. |

Core relationship: **deadline expiration leads to cancellation**, but not every cancellation is caused by a deadline. Therefore, seeing Context.isCancelled() on the server is not enough to conclude that the deadline has expired.

## 2. Client-side status and server-side signal

On the client, the final status usually helps distinguish the cause:

- CANCELLED: the call was cancelled before completing, typically because the caller actively cancelled or an associated context/transport was cancelled.
- DEADLINE_EXCEEDED: the call did not complete before the configured deadline.
- UNAVAILABLE: the transport or service is unavailable; not synonymous with active cancellation or deadline.
- OK: the RPC completed successfully before being cancelled or expiring.

On the server, both explicit cancellation and deadline expiration transition the RPC's context to the cancelled state. The server can read the deadline from the context and check whether it has expired:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()) {
    if (deadline != null && deadline.isExpired()) {
        // Deadline has already expired at the time of check.
    } else {
        // Call was cancelled for another reason or the peer disappeared.
    }
}
~~~

This is a point-in-time check. If a deadline exists and has not expired yet, the call can still be cancelled by the client or lose its connection. If the deadline has expired, that is evidence the deadline had expired at the moment of the check; in a race, do not treat this check as absolute proof of the sole root cause that led to call termination.

ServerCallStreamObserver.setOnCancelHandler(...) receives notification when the call is cancelled. This handler does not classify the cause itself. Context.cancellationCause() may provide a cause in some cases, but you should not rely on it as a stable classification code across all transports and cancellation sources.

A server cannot send a new status to a client that has already cancelled or disconnected. Once the context is cancelled, prioritize stopping work and cleaning up rather than calling onError(...), onCompleted(), or onNext(...) again.

## 3. Setting a deadline on a client RPC

With a blocking stub, set the time limit directly on the stub instance used for the call:

~~~java
StockReply reply = inventoryStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getStock(request);
~~~

If the server does not finish within 800 ms, the client receives an error with status DEADLINE_EXCEEDED. The deadline applies to the entire RPC, including time waiting for connection/readiness and round-trip exchange with the server; it does not measure only business method execution time on the server.

For async or streaming stubs, the deadline is also set on the stub before invoking the method:

~~~java
GreeterGrpc.GreeterStub boundedStub =
        greeterStub.withDeadlineAfter(3, TimeUnit.SECONDS);

boundedStub.sayHello(request, responseObserver);
~~~

Setting default deadlines per service/method via gRPC Service Config or an interceptor protects calls where the caller did not specify a custom timeout. Choose timeouts based on SLOs, RPC type, and stream lifetime. A short deadline suitable for a unary query can cause a server-streaming subscription to terminate prematurely even though the client still wants to receive data.

gRPC Java does not automatically set a finite deadline on every RPC if the application does not configure one. Therefore, do not treat a connected channel or enabled keepalive as a guarantee that an RPC will automatically terminate after some time.

## 4. Actively cancelling an RPC before the deadline

If the caller no longer needs the result, cancel the call immediately instead of waiting for the deadline to expire. With an async stub, use ClientResponseObserver to obtain the call handle:

~~~java
AtomicReference<ClientCallStreamObserver<HelloRequest>> activeCall =
        new AtomicReference<>();

ClientResponseObserver<HelloRequest, HelloReply> observer =
        new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<HelloRequest> call) {
                activeCall.set(call);
            }

            @Override
            public void onNext(HelloReply reply) {
                handleReply(reply);
            }

            @Override
            public void onError(Throwable failure) {
                handleFailure(failure);
            }

            @Override
            public void onCompleted() {
                handleCompletion();
            }
        };

greeterStub.withDeadlineAfter(10, TimeUnit.SECONDS)
        .sayHello(request, observer);

// When the caller no longer needs the result:
ClientCallStreamObserver<HelloRequest> call = activeCall.get();
if (call != null) {
    call.cancel("User left the screen", null);
}
~~~

This example illustrates call-level cancellation. Production code must handle the race if the caller cancels before beforeStart(...) stores the handle: keep a cancellationRequested flag and check it inside beforeStart. Also ensure the call handle belongs to the right RPC; do not store it in a shared mutable field of a singleton Spring service.

If wrapping the RPC in a CompletableFuture, wire future.cancel(true) to ClientCallStreamObserver.cancel(...). Cancelling only the future in the application layer without propagating the signal down to the call can leave the RPC running on the transport/server.

## 5. How does the server handle both cancellation and deadlines?

On the server, cancellation is a cooperative signal. The handler needs to stop workers, subscriptions, or downstream calls; the deadline additionally provides a time budget so layers do not keep waiting too long.

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();
AtomicBoolean stopped = new AtomicBoolean(rpcContext.isCancelled());

Context.CancellationListener listener = ignored -> stopped.set(true);
rpcContext.addListener(listener, Runnable::run);

try {
    if (stopped.get()) {
        return;
    }

    long remainingMillis = deadline == null
            ? 0
            : deadline.timeRemaining(TimeUnit.MILLISECONDS);

    if (deadline != null && remainingMillis <= 0) {
        return;
    }

    performWork(stopped);
} finally {
    rpcContext.removeListener(listener);
}
~~~

The example shows the same listener receiving the cancellation signal regardless of its source. If a deadline exists, the handler can read the remaining time to bound its work. The value 0 in the example represents no deadline; production code should use an explicit default policy rather than interpreting 0 as a zero wait time.

The listener should only set a flag or issue a quick stop request. Do not block waiting for a worker, perform potentially blocking resource closes, or roll back a transaction from a callback running on another thread. The worker owning the resources must react to the flag/interrupt and clean up in finally or try-with-resources.

## 6. Propagating the deadline budget downstream

A request may traverse multiple services. If the original request only has 400 ms left, do not grant a fresh 2 seconds to each downstream call. Pass the **remaining time**:

~~~java
Deadline parentDeadline = Context.current().getDeadline();
InventoryGrpc.InventoryBlockingStub downstream = inventoryStub;

if (parentDeadline != null) {
    long remainingNanos =
            parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);
    if (remainingNanos <= 0) {
        throw new UpstreamDeadlineExpiredException();
    }

    downstream = downstream.withDeadlineAfter(
            remainingNanos, TimeUnit.NANOSECONDS);
}

StockReply reply = downstream.getStock(request);
~~~

If the parent call is explicitly cancelled before the deadline expires, passing only the remaining deadline is not enough: downstream can keep running until the deadline. You need to wire parent context cancellation to the downstream call handle, especially with async stubs:

~~~java
Context parentContext = Context.current();
AtomicBoolean cancelled = new AtomicBoolean(parentContext.isCancelled());
AtomicReference<ClientCallStreamObserver<StockRequest>> downstreamCall =
        new AtomicReference<>();

Context.CancellationListener listener = ignored -> {
    cancelled.set(true);
    ClientCallStreamObserver<StockRequest> call = downstreamCall.get();
    if (call != null) {
        call.cancel("Parent RPC cancelled", null);
    }
};
parentContext.addListener(listener, Runnable::run);
~~~

When creating the downstream async call, store the handle in beforeStart(...) and recheck cancelled to handle the race. Remove the listener in the parent call's terminal path. Handle both directions: deadline bounds total time; cancellation actively stops earlier than the deadline.

## 7. Retries differ by termination reason

Cancellation and deadline lead to different retry decisions:

| Outcome | Should automatically retry? | Reason |
| --- | --- | --- |
| Caller actively cancels | Usually no. | Caller stated it no longer needs the result; retrying goes against that intent. |
| DEADLINE_EXCEEDED | Only if the operation is safe and total budget remains. | Server may have committed side effects even though the client received no response. |
| UNAVAILABLE | Possibly with an appropriate retry policy/backoff. | Service/transport may be temporarily unavailable; idempotency still applies. |
| Server returns CANCELLED | Do not infer cause from code alone. | Inspect call lifecycle and the operation's policy. |
| OK | Do not retry. | RPC completed successfully. |

An overall deadline should encompass all retries and backoffs. Do not grant the full initial timeout again for each attempt, because total duration could exceed the original request budget. If using gRPC retries via Service Config, inspect the retry policy and effective deadline together.

For write RPCs, DEADLINE_EXCEEDED does not prove the server did not execute the operation. Use a stable idempotency key, operation status lookup, or deduplication mechanism before retrying. For explicit cancellation, do not auto-retry unless another business layer intentionally creates a new operation.

## 8. Cancellation and deadline are not rollbacks

A client can cancel a call after the server has committed a transaction. A deadline can also expire right after commit but before the response reaches the client. Both cases leave the caller unaware of the result while the side effect already exists.

For write operations:

- Check cancellation before resource-intensive steps and before the commit point.
- Use transactions to roll back database changes if cancellation is detected before commit.
- Use an idempotency key to retry the same intent without creating duplicate records/side effects.
- With external services or message brokers, use an outbox, state machine, and compensation; a DB transaction cannot roll back external systems.
- Provide a status lookup API if the client can lose the response after the operation has been accepted.

Cancellation is a call-termination signal, and deadline is a time limit. Neither mechanism guarantees rolling back an already-committed side effect on its own.

## 9. Testing to distinguish the two cases

An integration test should verify both the client-side status and server-side context behavior:

1. **Explicit cancel before deadline:** server holds the RPC incomplete; client cancels the call; client observes CANCELLED, server cancellation handler is invoked, and worker stops.
2. **Deadline expires:** server holds the RPC longer than the deadline; client observes DEADLINE_EXCEEDED, server context transitions to cancelled, and deadline is reported as expired.
3. **Cancel before deadline expires:** verify server context is cancelled while the deadline still has time remaining.
4. **Very short deadline:** verify the handler does not start downstream work if the budget is already exhausted.
5. **Parent cancel while downstream is running:** verify child call is cancelled before the original deadline expires.
6. **Side effect committed before call terminates:** verify the operation still exists and the client can look it up by idempotency key.

With an in-process server, use CountDownLatch or CyclicBarrier to hold the handler at a deterministic point, avoiding arbitrary Thread.sleep(). Testing over TCP/TLS additionally verifies transport, proxies, and peer-disconnect scenarios. In-process tests do not fully simulate latency in detecting silent network drops.

## 10. Common mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Seeing context cancelled and concluding deadline expired | Explicit cancel or peer disconnect also cancels context. | Check getDeadline() and isExpired(); do not infer cause solely from isCancelled(). |
| Waiting for deadline to expire even though caller left the screen | Not wiring caller lifecycle to call cancellation. | Call ClientCallStreamObserver.cancel(...) when caller no longer needs the result. |
| Downstream runs until deadline even though parent cancelled | Only propagating deadline, not cancellation. | Wire parent listener to the downstream call handle. |
| Retrying every CANCELLED | Not distinguishing caller intent from other cancellations. | Respect caller cancellation and check cause/lifecycle. |
| Every retry gets a fresh timeout | Not preserving overall deadline. | Use remaining budget across attempts. |
| Increasing deadline to fix every slow error | Errors may be due to overload or hung dependencies. | Measure latency, bound concurrency, and set deadlines per SLO. |
| Assuming timeout means the server has not written data | Commit can occur before the response is lost. | Idempotency, status lookup, and reconciliation. |
| Cancellation callback waits for worker to finish | Blocking cleanup directly inside the listener. | Listener emits signal; worker owner stops itself and cleans up. |

## 11. Hands-on exercises

1. Call a unary RPC with a 500 ms deadline and verify status DEADLINE_EXCEEDED when the server responds slowly.
2. Use ClientResponseObserver to actively cancel the same RPC before the deadline; verify the client status is CANCELLED.
3. In the server handler, record Context.isCancelled() and Deadline.isExpired() for both cases; explain why cancellation does not imply deadline expiration.
4. Wire parent RPC cancellation to a downstream async call and pass the remaining deadline downstream.
5. Enable retries for an idempotent read RPC; verify total duration and backoff remain within the overall deadline.
6. Test a write RPC whose deadline expires after commit; use an idempotency key and status lookup API to determine the outcome.
7. Write in-process tests for explicit cancel, deadline expiry, and cancellation before deadline expiry; add an integration test over TCP/TLS.

After this lesson, you should be able to distinguish cancellation as a signal to stop a call from a deadline as a time limit that automatically terminates a call upon expiration. The server usually observes both through the cancelled context state, but can inspect the deadline to tell whether it has expired. Distinguishing them properly helps a Spring gRPC client/server stop work on time, propagate budgets downstream, and make safe retry decisions.
