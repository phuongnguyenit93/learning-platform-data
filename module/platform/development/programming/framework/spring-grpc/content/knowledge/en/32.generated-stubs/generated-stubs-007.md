# Creating Stubs from a Channel

## 1. Objectives

In gRPC Java, a Protobuf file defines services and RPC methods; code generation creates the service classes along with client stub types to invoke them. Once an application has a Channel, the client creates a stub from that channel to call the generated methods. In Spring gRPC, the channel is typically managed as a shared dependency, while the stub is injected into gateways or services that need to make RPC calls.

**Creating a stub from a channel** is the step that connects the generated service API to a specific gRPC destination. The channel provides the ability to send RPCs over a transport; the stub provides the invocation style and methods corresponding to the service in the proto file.

After this lesson, you can:

- Create blocking, asynchronous, and future stubs from the same channel.
- Choose a stub type based on RPC cardinality and result-handling style.
- Distinguish the responsibilities of Channel, ManagedChannel, stubs, and individual RPC calls.
- Safely reuse channels/stubs in multithreaded applications.
- Create derived stubs with specific deadlines, credentials, or call options.
- Wrap a channel with client interceptors before creating a stub.
- Manage channel lifecycle in Spring and avoid closing channels after every request.

## 2. From Generated Service to Stub

Suppose Protobuf defines a service:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (Product);
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc WatchInventory(WatchInventoryRequest)
      returns (stream InventoryUpdate);
  rpc UploadImages(stream ImageChunk) returns (UploadSummary);
  rpc SyncCatalog(stream CatalogEvent) returns (stream SyncResult);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string name = 2;
}

message SearchRequest {
  string query = 1;
}

message SearchResponse {
  repeated Product products = 1;
}

message WatchInventoryRequest {
  string warehouse_id = 1;
}

message InventoryUpdate {
  string product_id = 1;
  int32 available_quantity = 2;
}

message ImageChunk {
  bytes content = 1;
}

message UploadSummary {
  int32 stored_images = 1;
}

message CatalogEvent {
  string event_id = 1;
}

message SyncResult {
  string event_id = 1;
  bool accepted = 2;
}
```

The gRPC Java plugin generates the CatalogServiceGrpc class. This class provides factory methods for creating stubs:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub blockingStub =
        CatalogServiceGrpc.newBlockingStub(channel);

CatalogServiceGrpc.CatalogServiceStub asyncStub =
        CatalogServiceGrpc.newStub(channel);

CatalogServiceGrpc.CatalogServiceFutureStub futureStub =
        CatalogServiceGrpc.newFutureStub(channel);
```

The exact names are generated from the service name. newBlockingStub, newStub, and newFutureStub take an io.grpc.Channel; therefore, you can pass either a ManagedChannel or a channel wrapper produced by interceptors.

A stub does not define an endpoint itself. It uses the passed channel to send methods with the corresponding full path, such as /catalog.v1.CatalogService/GetProduct.

## 3. Distinguishing Channel, ManagedChannel, and Stub

| Component | Responsibility | Lifecycle |
|---|---|---|
| Channel | Abstraction for sending RPCs to a service | Provided by transport or wrapper |
| ManagedChannel | Channel capable of managing connections, name resolution, load balancing, and shutdown | Typically lives alongside the application or dependency |
| Generated stub | Binds a service descriptor and invocation style to a channel | Reusable and supports derived instances |
| RPC call | One invocation of a specific method with request and call options | Ends when response/error completes |

The channel determines the target, transport, and connection policies. The stub determines the service/method and invocation style. Deadlines, credentials, or compression can be set on derived stubs or their corresponding call options.

Creating a stub does not mean opening a new TCP connection per stub. Many stubs can share one channel, and many RPCs can multiplex over the same HTTP/2 connection. The channel is typically the heavier resource; do not create/close a channel for each business request.

## 4. Creating a ManagedChannel

In a plain Java application, you can create a channel using the builder:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .build();
```

During local development, a plaintext server can use:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .usePlaintext()
        .build();
```

Only choose usePlaintext() when the environment genuinely does not use TLS and is configured intentionally. For production, configure TLS/trust and service authentication according to system policy.

ManagedChannelBuilder returns a connection-managing channel. Channel creation is usually lazy: calling build() constructs and configures the channel object; actual connections are established when RPC demand arises or the channel needs to connect. Do not treat successful stub creation as proof that the server is reachable.

## 5. Creating a Blocking Stub

A blocking stub is suitable for unary RPCs or server-streaming RPCs when the caller accepts waiting for the result on the current thread.

```java
CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(channel);

GetProductRequest request = GetProductRequest.newBuilder()
        .setProductId("product-42")
        .build();

Product product = stub.getProduct(request);
```

For a unary RPC, the method returns the response after the call finishes, or throws StatusRuntimeException if the call fails.

For server streaming, the blocking stub typically returns an Iterator for the caller to read each response:

```java
Iterator<InventoryUpdate> updates =
        stub.watchInventory(
                WatchInventoryRequest.newBuilder()
                        .setWarehouseId("warehouse-1")
                        .build());

while (updates.hasNext()) {
    InventoryUpdate update = updates.next();
    process(update);
}
```

Do not call a blocking stub on an event-loop thread or a thread that must serve many concurrent requests if waiting could bottleneck the system. With Spring MVC, consider thread pools and concurrency limits; with reactive pipelines, use asynchronous APIs or appropriate reactive integration.

## 6. Creating an Asynchronous Stub

An asynchronous stub is created with newStub(channel). It uses StreamObserver to receive responses and errors, and supports streaming RPC types:

```java
CatalogServiceGrpc.CatalogServiceStub stub =
        CatalogServiceGrpc.newStub(channel);

stub.getProduct(
        GetProductRequest.newBuilder()
                .setProductId("product-42")
                .build(),
        new StreamObserver<>() {
            @Override
            public void onNext(Product product) {
                process(product);
            }

            @Override
            public void onError(Throwable error) {
                handleGrpcError(error);
            }

            @Override
            public void onCompleted() {
                finish();
            }
        });
```

For unary RPCs, the observer receives one response and then onCompleted(), or receives onError(). For server streaming, onNext() may be called multiple times before onCompleted().

For client-streaming or bidirectional streaming, the method returns a StreamObserver for the client to send request messages:

```java
StreamObserver<UploadSummary> responseObserver =
        new StreamObserver<>() {
            @Override
            public void onNext(UploadSummary summary) {
                recordUpload(summary);
            }

            @Override
            public void onError(Throwable error) {
                handleGrpcError(error);
            }

            @Override
            public void onCompleted() {
                finishUpload();
            }
        };

StreamObserver<ImageChunk> requestObserver =
        stub.uploadImages(responseObserver);

requestObserver.onNext(
        ImageChunk.newBuilder().setContent(firstChunk).build());
requestObserver.onNext(
        ImageChunk.newBuilder().setContent(secondChunk).build());
requestObserver.onCompleted();
```

After onCompleted() or onError(), the client must not send any more messages on that observer. For large streams, design flow control, buffer bounds, cancellation, and backpressure; do not buffer the entire stream in memory just because the observer API lets you call onNext() repeatedly.

## 7. Creating a Future Stub

A future stub is created with newFutureStub(channel) and is suitable for unary RPCs when the caller wants the result as a ListenableFuture:

```java
CatalogServiceGrpc.CatalogServiceFutureStub stub =
        CatalogServiceGrpc.newFutureStub(channel);

ListenableFuture<Product> result = stub.getProduct(
        GetProductRequest.newBuilder()
                .setProductId("product-42")
                .build());
```

The caller can combine the future with callbacks or an executor instead of blocking immediately:

```java
Futures.addCallback(
        result,
        new FutureCallback<>() {
            @Override
            public void onSuccess(Product product) {
                process(product);
            }

            @Override
            public void onFailure(Throwable error) {
                handleGrpcError(error);
            }
        },
        callbackExecutor);
```

Future stubs only support unary RPCs. For server-streaming, client-streaming, or bidirectional streaming, use an asynchronous stub. ListenableFuture belongs to Guava; modules using future stubs need the corresponding dependency and should define an executor for callbacks.

## 8. Choosing a Stub Type by Cardinality

| RPC cardinality | Blocking stub | Async stub | Future stub |
|---|---|---|---|
| Unary | Returns response directly | One onNext, then complete | ListenableFuture<Response> |
| Server streaming | Iterator<Response> | StreamObserver<Response> | Not supported |
| Client streaming | Not supported | Returns request StreamObserver | Not supported |
| Bidirectional streaming | Not supported | Both request and response via observers | Not supported |

Choose a stub based on the RPC type and the caller's execution model, not because one stub style looks shorter in code. A single service can use multiple stub types on the same channel for different methods.

## 9. Stubs Are Immutable and Reusable

Generated stubs in gRPC Java are immutable. Configuration methods such as withDeadlineAfter() create a new stub with modified call options; they do not mutate the original stub:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub baseStub =
        CatalogServiceGrpc.newBlockingStub(channel);

var fastCallStub = baseStub.withDeadlineAfter(
        300, TimeUnit.MILLISECONDS);

var normalCallStub = baseStub.withDeadlineAfter(
        2, TimeUnit.SECONDS);
```

Both derived stubs share the same channel but have different deadlines. You can store the base stub in a singleton gateway and create derived instances for each group of calls needing its own policy.

Because stubs are immutable and channels are thread-safe, they can be reused across multiple threads. Do not place mutable request-specific state in fields of a shared gateway or interceptor. Each RPC should have its own request, observer, and call options.

## 10. Configuring Call Options on a Stub

### Deadline

```java
var stubWithDeadline = baseStub.withDeadlineAfter(
        700, TimeUnit.MILLISECONDS);
```

The deadline bounds how long the call is allowed to complete. Set RPC deadlines based on the business flow's latency budget; do not rely on an unbounded default timeout.

### Wait for ready

```java
var waitForReadyStub = baseStub.withWaitForReady();
```

withWaitForReady() lets the call wait until the channel is ready within the deadline instead of failing immediately when the channel is temporarily not ready. It does not guarantee RPC success and does not replace a retry policy.

### Call credentials

```java
var authenticatedStub = baseStub.withCallCredentials(callCredentials);
```

Call credentials attach authentication information to the RPC. Credentials must be issued and refreshed according to security policy; do not hard-code tokens into generated stubs or source code.

### Compression

```java
var compressedStub = baseStub.withCompression("gzip");
```

Only enable compression when both client and server support it and payloads actually benefit. Compression consumes CPU and can increase latency for small payloads or already-compressed data.

Configuration methods return a stub of the same concrete type. Multiple configurations can be chained:

```java
var callStub = baseStub
        .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
        .withWaitForReady()
        .withCallCredentials(callCredentials);
```

Call options apply to calls made from that derived stub. Do not alter a shared base stub per request.

## 11. Attaching Client Interceptors Before Creating a Stub

Interceptors handle cross-cutting concerns such as tracing, metrics, or metadata. You can wrap a channel with ClientInterceptors.intercept() and then create stubs from the wrapped channel:

```java
Channel interceptedChannel = ClientInterceptors.intercept(
        channel,
        tracingInterceptor,
        metricsInterceptor);

CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(interceptedChannel);
```

Interceptors are invoked when creating and executing RPCs; they do not replace the generated stub. The stub still defines the service methods and request/response types. The channel wrapper adds shared behavior for calls passing through it.

Interceptor order can affect metadata handling and call lifecycle order. Standardize the order in configuration, and avoid registering the same interceptor on both the channel builder and a wrapper if doing so would record metrics/tracing twice.

If metadata only needs to be attached for a specific group of calls, use a dedicated interceptor or appropriate call credentials. Do not store request-specific metadata in mutable fields of a singleton interceptor; construct metadata/call state per call.

## 12. Organizing Channels and Stubs in Spring

In Spring, a channel should be a bean whose lifecycle is managed by the application context. A gateway can receive the channel via constructor injection and create the stub once:

```java
@Configuration
public class CatalogClientConfiguration {

    @Bean(name = "catalogChannel", destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .useTransportSecurity()
                .build();
    }
}
```

Gateway:

```java
@Component
public class CatalogGateway {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub baseStub;

    public CatalogGateway(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        this.baseStub = CatalogServiceGrpc.newBlockingStub(channel);
    }

    public Product getProduct(String productId) {
        var request = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();

        return baseStub
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getProduct(request);
    }
}
```

This example illustrates a TLS channel to a dependency. Hostnames, ports, trust configuration, and how the Spring gRPC starter manages channels must match the project. Some starters have their own auto-configuration/channel factory mechanisms; when using such a starter, follow its supported lifecycle and configuration, and avoid creating a second channel to the same target without reason.

destroyMethod = "shutdown" instructs Spring to invoke shutdown when the bean is destroyed. For applications needing graceful shutdown, you can manage awaitTermination() and call shutdownNow() when the wait timeout elapses. Never close the channel inside getProduct() or after individual requests.

## 13. One Channel or Multiple Channels?

Reuse a single channel for multiple stubs when they share the same target and transport/security configuration:

- Multiple services on the same server can share a channel.
- Multiple stub types for the same service can share a channel.
- v1/v2 clients can share a channel if the target and TLS identity are identical.
- Calls with different deadlines or credentials can use derived stubs over a shared channel.

Create separate channels when there is a clear reason:

- Different targets or clusters.
- Different TLS trust, client certificates, or identities.
- Need to isolate connections, load balancing, or quotas.
- Independent lifecycle policies.

Do not create a channel per user or per RPC. Too many channels increase sockets, threads, connection management overhead, and name resolution cost.

## 14. Closing Channels Properly

Stubs do not have a close() method because stubs do not own the transport. ManagedChannel is the object that must be shut down:

```java
channel.shutdown();

if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
    channel.shutdownNow();
}
```

shutdown() stops accepting new calls and gives in-flight calls an opportunity to finish. shutdownNow() requests cancellation of active calls. The wait timeout should fit the application's shutdown budget.

If a gateway creates stubs from a Spring-managed channel, the gateway must not shut down the channel itself. Only the component that owns the channel lifecycle should close it. This prevents one bean from breaking other gateways sharing the same channel.

## 15. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| CatalogServiceGrpc not found | gRPC Java code generator has not run | Configure protoc-gen-grpc-java |
| Blocking RPCs stall threads | Using a blocking stub on an event loop or tiny pool | Switch to async or adjust concurrency |
| Future stub lacks streaming methods | Future stub only supports unary | Use an asynchronous stub |
| Every request creates a socket/channel | Creating and closing ManagedChannel inside gateway methods | Manage a shared channel per target |
| One request's stub affects another request | Sharing mutable state instead of derived stubs | Use immutable stubs and per-call options |
| Call waits too long | No deadline set | Use withDeadlineAfter() per latency budget |
| withWaitForReady() still times out | Deadline expired or server not ready | Set a sensible deadline and handle status |
| Metrics/tracing duplicated | Interceptor registered at multiple layers | Check channel wrappers and configuration |
| Channel closed while another gateway uses it | Gateway shuts down a shared dependency | Only the channel owner manages shutdown |
| Spring shutdown drops in-flight calls | Calling shutdownNow too early | Use graceful shutdown with a wait timeout |

## 16. Hands-On Exercise

**Scenario:** A Spring service calls Catalog over gRPC. The application needs unary GetProduct, server-streaming WatchInventory, and client-streaming UploadImages. Calls must use TLS, a tracing interceptor, and different deadlines.

Complete the following:

1. Create a ManagedChannel bean to Catalog with appropriate transport/security configuration.
2. Create a blocking stub for GetProduct and a future stub if a business flow requires ListenableFuture.
3. Create an asynchronous stub for WatchInventory and UploadImages.
4. Wrap the channel with tracing/metrics interceptors before creating stubs.
5. Reuse the channel for stubs targeting the same destination; do not create a channel per RPC.
6. Use derived stubs with an appropriate deadline for each call.
7. Test a successful unary call, a multi-message server stream, and a client stream completing with the proper observer lifecycle.
8. Test deadline exceeded and channel shutdown when the Spring application context closes.
9. Verify that interceptors do not duplicate metadata or metrics and hold no state across calls.

**Completion criteria:** each RPC type uses an appropriate stub; stubs share a centrally managed channel; call options are independent; interceptors are applied consistently; the channel is shut down only by its owner when the application stops.

## 17. Takeaways

Create stubs using the generated service's factory methods, passing a Channel or ManagedChannel. Blocking stubs suit unary/server-streaming with waiting callers; asynchronous stubs support all four cardinalities; future stubs are for unary calls. The channel manages target and transport, while the stub is an immutable client facade for the service API. Reuse channels and base stubs; create derived stubs for specific deadlines, credentials, or call options. Wrap channels with interceptors before creating stubs when shared tracing/metrics are needed. In Spring, let the application context manage the channel lifecycle and shut down channels only when the dependency owner stops, never after individual RPCs.
