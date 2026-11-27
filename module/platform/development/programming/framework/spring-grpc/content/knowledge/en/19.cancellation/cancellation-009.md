# Cancellable future and reactive bridge

## 1. Why is a cancellable bridge needed?

In **Spring gRPC**, a client can invoke an RPC using a generated async stub, a future stub, or a reactive API such as Reactor `Mono`/`Flux`. Each API represents results differently, yet all of them must preserve the lifecycle of an RPC: when the caller is no longer interested, the request must be cancelled in the gRPC runtime and server-side resources need to be released when possible.

A bridge that only forwards responses from callbacks into a `Mono` while ignoring cancellation creates a lifecycle bug: the subscriber has timed out or cancelled its subscription, while the RPC keeps running and continues consuming connections, CPU, database connections, or broker subscriptions.

A proper bridge must propagate signals in both directions:

- **RPC completes/errors:** translate the gRPC result or error into a terminal signal of Future/Mono/Flux.
- **Caller cancels:** cancel the corresponding Future or gRPC call.
- **Deadline expires:** gRPC ends the call; the bridge forwards the timeout status to the caller.
- **Race condition:** handle the case where cancellation occurs before the bridge receives the call handle.

## 2. gRPC Java APIs and cancellation capabilities

gRPC Java provides several stub forms:

| Stub/API | Result type | Cancellation |
| --- | --- | --- |
| Async stub | Callbacks via `StreamObserver` | Use `ClientCallStreamObserver.cancel()` once the call handle is obtained |
| Blocking stub | Returns result directly or throws exception | Blocks calling thread; use deadline to bound time. Do not use blocking stub as a bridge for a reactive event loop |
| Future stub | `ListenableFuture<T>` for unary RPCs | `future.cancel(true)` cancels the future and propagates cancellation to the gRPC call |
| Reactor bridge | `Mono<T>` or `Flux<T>` | When subscriber cancels, the bridge must cancel the Future or gRPC call |

The generated **future stub only supports unary RPCs**. For server-streaming, client-streaming, and bidirectional-streaming, use an async stub and bridge from callbacks/stream observers.

Do not call `.get()` or `.block()` on an event loop just to turn an asynchronous API into a synchronous one. That can block threads processing the reactive pipeline and degrade throughput.

## 3. Cancellation of a gRPC Future

For unary RPCs, the generated future stub returns a Guava `ListenableFuture`:

```java
ListenableFuture<GetItemResponse> future =
        catalogFutureStub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .getItem(request);

// When the caller no longer needs the result:
future.cancel(true);
```

Cancelling the future cancels the corresponding gRPC call. The `true` parameter should not be understood as gRPC forcibly stopping every piece of running server code; it requests cancellation of the future/call operation. The server needs to observe cancellation/deadline and stop stoppable work itself.

Cancellation is not a rollback. If the server has already committed a database change before receiving the cancellation signal, that change can still persist. For commands with side effects, idempotency and a status lookup API are needed to handle indeterminate outcomes.

## 4. Converting ListenableFuture into a Reactor Mono

Reactor `Mono` represents at most one result. You can bridge a future stub with `Mono.create`; the key point is registering cancellation to cancel the future.

Place the helper method below in a Java class; imports are listed in the example.

```java
import com.google.common.util.concurrent.FutureCallback;
import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;
import com.google.common.util.concurrent.MoreExecutors;
import reactor.core.publisher.Mono;
import java.util.function.Supplier;
import java.util.concurrent.TimeUnit;

static <T> Mono<T> fromGrpcFuture(
        Supplier<ListenableFuture<T>> callFactory) {
    return Mono.defer(() -> {
        ListenableFuture<T> call = callFactory.get();
        return Mono.create(sink -> {
            // Register first so cancellation from downstream is always forwarded.
            sink.onCancel(() -> call.cancel(true));

            Futures.addCallback(call, new FutureCallback<>() {
                @Override
                public void onSuccess(T result) {
                    sink.success(result);
                }

                @Override
                public void onFailure(Throwable error) {
                    sink.error(error);
                }
            }, MoreExecutors.directExecutor());
        });
    });
}
```

Usage:

```java
Mono<GetItemResponse> itemMono = fromGrpcFuture(
        () -> catalogFutureStub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .getItem(request));
```

`Mono.defer()` ensures the RPC is only created when there is a subscriber. If you create the `ListenableFuture` outside and then pass it into the bridge, the RPC can start before a subscriber subscribes; cancellation and execution timing become harder to manage.

The bridge preserves exceptions from gRPC, typically `StatusRuntimeException` or cancellation errors. Calling layers can classify the status using `Status.fromThrowable(error)`; you should not convert every error into a generic exception that loses the status code.

## 5. Converting an async unary RPC into a Mono

If using an async stub, `ClientResponseObserver` provides `beforeStart()` to obtain `ClientCallStreamObserver`. This is the handle needed to cancel the call when the reactive subscriber cancels.

```java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import reactor.core.publisher.Mono;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.TimeUnit;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

// catalogAsyncStub is an async stub injected into the client component.
Mono<GetItemResponse> getItemReactive(GetItemRequest request) {
    return Mono.create(sink -> {
        AtomicReference<ClientCallStreamObserver<GetItemRequest>> callRef =
                new AtomicReference<>();
        AtomicBoolean cancelled = new AtomicBoolean();

        ClientResponseObserver<GetItemRequest, GetItemResponse> observer =
                new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<GetItemRequest> call) {
                callRef.set(call);
                // Handle race: subscriber may cancel before the call handle arrives.
                if (cancelled.get()) {
                    call.cancel("Reactive subscriber cancelled", null);
                }
            }

            @Override
            public void onNext(GetItemResponse response) {
                sink.success(response);
            }

            @Override
            public void onError(Throwable error) {
                sink.error(error);
            }

            @Override
            public void onCompleted() {
                // Unary response has usually already been emitted in onNext().
            }
        };

        sink.onCancel(() -> {
            cancelled.set(true);
            ClientCallStreamObserver<GetItemRequest> call = callRef.get();
            if (call != null) {
                call.cancel("Reactive subscriber cancelled", null);
            }
        });

        try {
            catalogAsyncStub.getItem(request, observer);
        } catch (RuntimeException error) {
            sink.error(error);
        }
    });
}
```

Both race-handling branches are necessary:

- If the subscriber cancels after `beforeStart()` runs, `callRef` already has a value and cancellation directly cancels the call.
- If the subscriber cancels before `beforeStart()` runs, the `cancelled` flag is set; when the handle appears, `beforeStart()` immediately cancels the call.

This is a unary bridge. For production APIs, ensure callbacks emit a terminal signal only once, handle the case where the server completes without emitting a response per contract, and preserve statuses/trailers needed by callers.

## 6. Bridging server-streaming into a Flux

A server-streaming RPC emits multiple response messages, so the matching reactive type is `Flux<T>`. When the subscriber cancels, the gRPC call must be cancelled so the server receives cancellation:

```java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BiConsumer;
import com.example.orders.v1.OrderEvent;

static <ReqT, RespT> Flux<RespT> toFlux(
        ReqT request,
        BiConsumer<ReqT, ClientResponseObserver<ReqT, RespT>> invoke) {
    return Flux.create(sink -> {
        AtomicReference<ClientCallStreamObserver<ReqT>> callRef =
                new AtomicReference<>();
        AtomicBoolean cancelled = new AtomicBoolean();

        ClientResponseObserver<ReqT, RespT> observer =
                new ClientResponseObserver<>() {
            @Override
            public void beforeStart(ClientCallStreamObserver<ReqT> call) {
                callRef.set(call);
                if (cancelled.get()) {
                    call.cancel("Flux subscriber cancelled", null);
                }
            }

            @Override
            public void onNext(RespT value) {
                if (!sink.isCancelled()) {
                    sink.next(value);
                }
            }

            @Override
            public void onError(Throwable error) {
                sink.error(error);
            }

            @Override
            public void onCompleted() {
                sink.complete();
            }
        };

        sink.onCancel(() -> {
            cancelled.set(true);
            ClientCallStreamObserver<ReqT> call = callRef.get();
            if (call != null) {
                call.cancel("Flux subscriber cancelled", null);
            }
        });

        try {
            invoke.accept(request, observer);
        } catch (RuntimeException error) {
            sink.error(error);
        }
    }, FluxSink.OverflowStrategy.BUFFER);
}
```

Example invocation:

```java
Flux<OrderEvent> events = toFlux(
        watchRequest,
        (request, observer) ->
                orderEventsAsyncStub.watch(request, observer));
```

The example uses `BUFFER` to retain messages if the producer is faster than the subscriber. That is an unbounded buffer in a basic bridge; do not use it as-is for long-lived streams or high-rate sources. Production needs explicit backpressure design: use gRPC's manual inbound flow control (`disableAutoRequestWithInitial`/ `request(n)`) to map Reactor demand to the number of messages allowed, or use a bounded queue with an explicit overflow policy.

Do not call `sink.next()` concurrently from multiple producer threads if the bridge does not serialize callbacks. gRPC response callbacks are normally ordered within a single call; if the application dispatches messages through a separate executor, preserve ordering and guard terminal signals.

## 7. Cancellation, deadline, and reactive timeout

Cancellation and deadline are related yet distinct:

| Mechanism | Who initiates? | Meaning |
| --- | --- | --- |
| Caller cancellation | Caller cancels subscription/future/call | Caller no longer cares about the result |
| gRPC deadline | Caller sets time limit, runtime tracks it | RPC ran out of its time budget |
| Reactor `timeout()` | Reactive pipeline | Pipeline emits timeout and cancels upstream subscription |
| Server cancellation signal | gRPC runtime notifies server | Server knows the call is no longer active on the client side |

Example:

```java
Mono<GetItemResponse> result = fromGrpcFuture(
        () -> catalogFutureStub
                .withDeadlineAfter(3, TimeUnit.SECONDS)
                .getItem(request))
        .timeout(Duration.ofSeconds(2));
```

Here, Reactor's 2-second timeout cancels the upstream subscription; the bridge propagates cancellation to the future, then to the gRPC call. The 3-second gRPC deadline acts as an additional safety net if the call remains active due to a bridge bug or improper caller cancellation. Normally, choose a unified budget to avoid overlapping timeouts that are hard to reason about.

If using `timeout()` with a fallback, remember that timeout can switch to the fallback after cancelling the initial RPC. The fallback does not prove the server operation was not executed; write commands still require idempotency or status lookup.

## 8. The server must react to cancellation

When the client cancels or the deadline expires, the server can receive a cancellation signal. With gRPC Java:

- Use `ServerCallStreamObserver.setOnCancelHandler()` to clean up subscriptions/resources attached to the call.
- Check `isCancelled()` before emitting messages if work runs asynchronously.
- You can use gRPC `Context.current().addListener(...)` to wire cancellation to context-dependent tasks.
- Cancel scheduled tasks, broker subscriptions, or stoppable work.
- Do not emit `onNext()` after a terminal signal.

Example:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;

// Fragment inside a server method; eventStore/orderId are service
// dependencies and parameters. close() must be safe when called multiple times.
ServerCallStreamObserver<OrderEvent> output =
        (ServerCallStreamObserver<OrderEvent>) responseObserver;

AtomicBoolean stopped = new AtomicBoolean();
Object writeLock = new Object();
EventSubscription subscription = eventStore.subscribe(orderId);

output.setOnCancelHandler(() -> {
    synchronized (writeLock) {
        stopped.set(true);
        subscription.close();
    }
});

subscription.start(event -> {
    synchronized (writeLock) {
        if (stopped.get() || output.isCancelled()) {
            stopped.set(true);
            subscription.close();
            return;
        }
        try {
            output.onNext(toProto(event));
        } catch (RuntimeException sendError) {
            stopped.set(true);
            subscription.close();
        }
    }
});
```

If subscription callbacks can run concurrently with cancellation, synchronize terminal state so messages are not emitted after the call is closed. Closing the subscription should be idempotent so multiple cleanup paths do not cause errors.

Register the cancellation handler before starting the subscription. The `EventSubscription` implementation should treat `close()` before `start()` as a terminated state; in that case `start()` must emit no further events.

Cancellation is a cooperative signal. It does not automatically interrupt every thread, roll back committed transactions, or cancel side effects in external systems. The server must design tasks that can check cancellation and terminate safely.

## 9. Avoiding resource leaks in bridges

A bridge needs a clear owner for the call handle, listeners, and auxiliary resources:

1. Register the cancellation handler as soon as the bridge is created.
2. Handle the race when cancel occurs before the call handle is provided.
3. Forward terminal callbacks exactly once.
4. Cancel timers and subscriptions on cancel, error, or completion.
5. Do not retain references to the subscriber after terminal state.
6. For long-lived Fluxes, bound buffers or apply flow control.
7. Do not create a dedicated scheduler/executor per RPC when a managed executor can be used.

If a bridge converts a Future to a CompletableFuture, wire cancellation bidirectionally explicitly. `CompletableFuture.cancel()` does not automatically cancel an external task unless bridge code calls `grpcFuture.cancel()`.

## 10. Testing cancellation and reactive bridges

Test with an in-process server/channel or a test server capable of observing cancellation:

| Scenario | Assertion |
| --- | --- |
| Unary future succeeds | Mono emits exactly one response then completes |
| Unary future returns gRPC error | Mono emits error preserving status |
| Subscriber cancels before response | Future/call is cancelled |
| Cancel occurs before `beforeStart()` | Call is cancelled as soon as handle appears |
| Reactor timeout | Upstream gRPC call receives cancellation |
| Server-streaming Flux is cancelled | Client call cancels and server cleanup runs |
| Stream completes normally | Flux completes, no spurious cancel invoked |
| Server sends multiple events | Event order is preserved |
| Slow subscriber | Buffer/flow control does not grow unboundedly |
| Caller cancels after server commit | Client stops waiting; test does not assume transaction rollback |

To verify cancellation actually reaches the server, the test server can count how many times `onCancelHandler` runs or confirm the subscription closes using a latch with a timeout. Do not only check that `Disposable.dispose()` was called on the Reactor side; verify the corresponding gRPC call is also cancelled.

## 11. Common mistakes

1. **Only converting callbacks to Mono without registering `sink.onCancel`.** The RPC keeps running after the subscriber leaves.
2. **Assuming `CompletableFuture.cancel()` automatically cancels gRPC.** The bridge must wire cancellation to `ListenableFuture.cancel()` or the call handle.
3. **Using a future stub for streaming RPCs.** Future stubs only generate unary methods.
4. **Calling `.block()` inside a reactive event loop.** Can block threads and cause stalls.
5. **Ignoring the race between cancel and `beforeStart()`.** The call handle may appear after the subscriber has already cancelled.
6. **Using an unbounded buffer for long-lived Fluxes.** Slow subscribers can cause unbounded memory growth.
7. **Treating cancellation as rollback.** The server may have already committed side effects.
8. **Converting all errors into a generic exception.** Loses the gRPC status needed for retries/fallbacks.
9. **Not cleaning up subscriptions/server tasks.** Client cancelled yet server-side resources keep running.

## 12. Hands-on exercises

With `catalog.v1.CatalogService`:

1. Create a unary future stub call `GetItem` and bridge it to `Mono<GetItemResponse>`.
2. Cancel the subscriber before the server returns a response; verify the gRPC future/call is cancelled.
3. Create an async server-streaming RPC `WatchItems` and bridge it to `Flux<ItemEvent>`.
4. Cancel the Flux after three events; verify the server subscription is closed.
5. Try a Reactor `timeout()` shorter than the gRPC deadline and observe status/cancellation.
6. Simulate a slow subscriber; design manual flow control or a bounded buffer.
7. Simulate server commit before client cancel; verify the client does not infer that the side effect rolled back.

**Completion criteria:** learners can bridge unary Future/async callbacks to Mono and server-streaming to Flux, propagate cancellation to gRPC calls, handle race conditions, deadlines, backpressure, and server-side cleanup.

### References

- [gRPC Java FutureStub API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/AbstractFutureStub.html): future stub for unary RPCs.
- [gRPC Java ClientCallStreamObserver API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientCallStreamObserver.html): client-side cancellation and flow control.
- [gRPC Java ClientResponseObserver API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientResponseObserver.html): obtaining the call handle before receiving responses.
- [Reactor Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): publisher of at most one element and cancellation.
- [Reactor Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): multi-element publisher and overflow strategy.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): integrating gRPC client/server in Spring.
