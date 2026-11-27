# Thread Safety of Generated Stubs

In a Spring gRPC application, many requests may call the same backend concurrently. If each request creates its own channel and stub, the application wastes connection resources, struggles with lifecycle management, and adds initialization overhead. In gRPC Java, generated stubs are immutable objects and can be shared across multiple threads. A single shared stub can serve many concurrent RPCs; each invocation creates an independent call with its own state.

That does not mean every object around the stub is safe for concurrent use. You must distinguish between stubs, channels, CallOptions, StreamObservers, protobuf builders, interceptors, and executors. This lesson focuses on the thread-safety scope of generated stubs and how to structure clients in Spring gRPC.

## 1. Generated Stubs Are Immutable and Shareable

From a protobuf service definition, gRPC Java generates the common stub types:

| Stub | Invocation Style | Result |
| --- | --- | --- |
| CatalogServiceBlockingStub | Synchronous method call | Returns response or throws StatusRuntimeException |
| CatalogServiceStub | Asynchronous method call | Receives results via StreamObserver |
| CatalogServiceFutureStub | Future-based call | Returns a future representing the RPC result |

Generated stubs are built on AbstractStub and hold a channel together with CallOptions. A stub's configuration is immutable; methods such as withDeadlineAfter, withWaitForReady, or withCompression return a new stub with updated call options without mutating the original stub.

Therefore, a stub can be injected into a singleton service and invoked concurrently by multiple request threads:

```java
@Service
public class CatalogClient {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    public CatalogClient(
            CatalogServiceGrpc.CatalogServiceBlockingStub stub) {
        this.stub = stub;
    }

    public Product getProduct(String productId) {
        GetProductRequest request = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();
        return stub.getProduct(request);
    }
}
```

There is no need to create a new stub instance per thread or synchronize the entire call just to protect the stub. Each independent RPC has its own call state managed by the gRPC runtime.

## 2. Channels Are Also Designed for Reuse

A stub does not open a separate TCP connection per method call. It communicates over a Channel; in typical client applications, the concrete channel is a ManagedChannel. gRPC Java channels are designed to be used concurrently and reused across many RPCs.

A Spring configuration can define the channel and stubs at application scope:

```java
@Configuration
public class CatalogGrpcClientConfiguration {
    @Bean(destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .useTransportSecurity()
                .build();
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceBlockingStub catalogBlockingStub(
            ManagedChannel catalogChannel) {
        return CatalogServiceGrpc.newBlockingStub(catalogChannel);
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceStub catalogAsyncStub(
            ManagedChannel catalogChannel) {
        return CatalogServiceGrpc.newStub(catalogChannel);
    }
}
```

This example illustrates a single channel shared by a blocking stub and an async stub. In a real project, configure TLS, load balancing, name resolvers, interceptors, and shutdown hooks according to your deployment environment.

Lifecycle principles:

- Create channels at the application or client component scope, not per request.
- Share a channel across multiple stubs if they target the same destination and share the same transport configuration.
- Do not call shutdown() after each RPC; other requests are still using the channel.
- Close the channel when the application shuts down or when the client component genuinely reaches the end of its lifecycle.
- If different transport settings are needed, create separate channels per target/policy and manage their lifecycles independently.

Stubs have no separate shutdown lifecycle; the channel is the resource that must be closed.

## 3. Create a New Stub When One RPC Needs Custom CallOptions

Because stubs are immutable, configure a deadline for an individual call by deriving a new stub:

```java
public Product getProduct(String productId) {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId(productId)
            .build();

    CatalogServiceGrpc.CatalogServiceBlockingStub callStub =
            baseStub.withDeadlineAfter(700, TimeUnit.MILLISECONDS);

    return callStub.getProduct(request);
}
```

baseStub retains its original deadline and call options. callStub applies the custom configuration only to this invocation. This pattern fits when different use cases have different time budgets.

Avoid reassigning a shared stub field per request:

```java
// Avoid: shared field gets mutated on every request.
this.stub = this.stub.withDeadlineAfter(timeout, TimeUnit.MILLISECONDS);
return this.stub.getProduct(request);
```

Even though each created stub is immutable, reassigning a singleton field introduces mutable shared state. Two concurrent requests can overwrite each other's configuration. Keep the base stub final and hold the derived stub in a local variable for the call.

CallOptions are also immutable; the with... methods produce a new configuration. A deadline is a per-call policy, not state that should be mutated on a shared stub.

## 4. Thread Safety Does Not Mean a Blocking Stub Is Always Suitable

A blocking stub can safely be called from multiple threads, yet each call holds the caller's thread until the RPC completes or fails. Thread safety only means sharing the object causes no data race; it does not guarantee scalability when many requests are waiting on the network.

| Scenario | Usually Suitable Choice |
| --- | --- |
| Synchronous processing flow on bounded worker threads | Blocking stub with an explicit deadline |
| Application needs callback/asynchronous handling | Async stub |
| Composing future pipelines | Future stub |
| Event loop or callback thread must stay non-blocking | Async/future API; do not call a blocking stub directly |

Do not invoke a blocking stub on a Netty event loop, a gRPC transport callback thread, or an executor with too few threads for the volume of waiting calls. One slow RPC can tie up a thread and starve other tasks. Use bounded executors, deadlines, and concurrency limits.

## 5. Each RPC Needs Its Own Observer and State

A generated async stub can be called concurrently, but the StreamObserver passed into a call is bound to that specific call. Never share a single mutable observer across independent RPCs:

```java
public void getProductAsync(
        String productId,
        Consumer<Product> onSuccess,
        Consumer<Throwable> onFailure) {

    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId(productId)
            .build();

    asyncStub.getProduct(request, new StreamObserver<>() {
        @Override
        public void onNext(Product response) {
            onSuccess.accept(response);
        }

        @Override
        public void onError(Throwable error) {
            onFailure.accept(error);
        }

        @Override
        public void onCompleted() {
            // Unary call has completed.
        }
    });
}
```

Each invocation creates a fresh observer, so callbacks and results cannot mix across requests. If the observer updates shared application state, that state still needs synchronization or an appropriate concurrency design.

Do not store a single RPC's request ID, response, exception, or callback in a mutable field on a singleton client. Keep state in local variables or a dedicated per-operation object.

## 6. StreamObserver Is Not Automatically Thread-Safe

For client streaming or bidirectional streaming, the async stub returns a StreamObserver<Request> for the application to send multiple messages:

```java
StreamObserver<ImportProductRequest> requestStream =
        asyncStub.importProducts(new StreamObserver<ImportSummary>() {
            @Override
            public void onNext(ImportSummary summary) {
                handleSummary(summary);
            }

            @Override
            public void onError(Throwable error) {
                handleFailure(error);
            }

            @Override
            public void onCompleted() {
                handleCompleted();
            }
        });

requestStream.onNext(firstBatch);
requestStream.onNext(secondBatch);
requestStream.onCompleted();
```

StreamObserver is not guaranteed to be thread-safe. If multiple producer threads call onNext, onError, or onCompleted on the same observer, the application must serialize those calls. You can use a sequential executor or a bounded queue with a single writer.

Rules:

- Do not call onNext from multiple threads on the same request observer.
- Send onCompleted or onError only once; these are terminal signals.
- Never send more messages after a terminal signal.
- Never share one stream's request observer with another stream.
- If synchronization via locks is needed, keep critical sections short and perform no blocking I/O inside them.

Similarly, server-side StreamObservers must follow your application's serialization rules. Having a thread-safe stub does not make observers or callback state thread-safe.

## 7. Protobuf Messages and Builders Have Different Characteristics

A generated protobuf message is immutable after build(), so it can be safely shared for reading across multiple threads. A Builder is mutable; never share a builder across threads without synchronization.

```java
GetProductRequest request = GetProductRequest.newBuilder()
        .setProductId("P-100")
        .build(); // A built message can be shared for reading.

GetProductRequest.Builder builder = GetProductRequest.newBuilder();
builder.setProductId("P-200"); // Mutable builder; use only within its owning scope.
GetProductRequest anotherRequest = builder.build();
```

A safe pattern is to create the builder inside the method or operation, build the message, and pass the immutable message to the stub. Never reuse a singleton builder to construct requests for multiple concurrent calls.

## 8. Interceptors and CallCredentials Must Also Handle Concurrent Load

Sharing a stub means channel-level interceptors and credential providers can be called from many RPCs simultaneously. Therefore:

- Interceptors should be stateless or hold only immutable/thread-safe dependencies.
- Create counters, timestamps, listener wrappers, and per-call state inside interceptCall.
- Never store request-specific metadata in interceptor fields.
- Credential providers must handle token refresh and caching in a thread-safe manner.
- Do not block for long inside an interceptor when fetching credentials; consider CallCredentials and appropriate async mechanisms.
- Use gRPC Context for call-scoped data; when switching to custom executors, propagate context explicitly.

For example, a safe interceptor captures per-call data in local variables:

```java
@Override
public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
        MethodDescriptor<ReqT, RespT> method,
        CallOptions callOptions,
        Channel next) {
    long startedAt = System.nanoTime();
    String methodName = method.getFullMethodName();
    ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
    return wrap(delegate, methodName, startedAt);
}
```

startedAt and methodName belong to the call being created and must not be stored in fields where subsequent RPCs could overwrite them.

## 9. Testing Stub Sharing

Concurrency tests should verify that multiple calls sharing a single stub still receive the right responses and statuses:

| Test Case | What to Verify |
| --- | --- |
| Multiple concurrent unary RPCs over one stub | Each call receives the response matching its request |
| Two different deadlines | One call's deadline does not alter the other call |
| Blocking and async stubs sharing a channel | Channel handles calls concurrently and is not closed mid-flight |
| Two streaming calls | Observers and message counts are not mixed |
| Multiple producers sending into one stream | Messages are serialized in the order defined by the application |
| Shared interceptor | No request-specific mutable state is shared |
| Application shutdown | Channel closes once after stopping new calls |

You can use an in-process server/channel for gRPC tests and bounded-thread stress tests. When testing Spring, inject the same stub bean into multiple parallel tasks to verify actual wiring and lifecycle. Do not write tests that create a brand-new stub each time, as that fails to test sharing a single stub.

## 10. Checklist for Safe Generated Stub Usage

- [ ] Reuse immutable generated stubs across threads.
- [ ] Reuse thread-safe ManagedChannels across multiple RPCs to the same destination.
- [ ] Manage channel shutdown in the application lifecycle, not per request.
- [ ] Use withDeadlineAfter to create a local derived stub for calls needing custom timeouts.
- [ ] Never reassign a singleton stub field per request.
- [ ] Choose blocking, async, or future stubs to match the application's thread model.
- [ ] Create separate observers and state for each RPC.
- [ ] Serialize operations on the same StreamObserver when multiple producer threads exist.
- [ ] Never share mutable protobuf Builders across threads; share built messages for reading.
- [ ] Ensure interceptors and credential providers are safe under concurrent invocation.
- [ ] Propagate gRPC Context across custom executors.
- [ ] Include concurrency tests for unary calls, streaming, deadlines, and shutdown.

**Self-Check**

**Question 1.** Can a generated blocking stub be injected into a Spring singleton service and called from multiple request threads?

*Answer:* Yes. Generated stubs are immutable and designed for concurrent sharing. Each invocation creates a separate RPC call; you still need appropriate deadlines and an executor model.

**Question 2.** Does withDeadlineAfter modify the deadline of the original stub?

*Answer:* No. It returns a new stub with new CallOptions; the original stub stays unchanged. Keep the derived stub in a call-local variable.

**Question 3.** Why should you avoid creating a ManagedChannel for every request?

*Answer:* A channel is a concurrently reusable transport resource. Repeated creation increases connections, threads, and initialization cost; channels should be managed at the application/client lifecycle level.

**Question 4.** Can multiple threads concurrently call onNext on the same request StreamObserver?

*Answer:* You must not assume observers are thread-safe. Serialize calls on the same observer using a sequential writer or an appropriate synchronization mechanism.

**Question 5.** How do protobuf messages and Builders differ regarding sharing across threads?

*Answer:* Built messages are immutable and can be shared for reading; Builders are mutable and must not be shared concurrently without synchronization.

Thread-safe generated stubs allow a Spring gRPC client to share stubs and channels across many requests without locking entire calls. Keep stub configuration immutable, derive per-call CallOptions, follow the concurrency contract for observer/stream state, and close channels on application shutdown—your client concurrency will stay clear and testable.
