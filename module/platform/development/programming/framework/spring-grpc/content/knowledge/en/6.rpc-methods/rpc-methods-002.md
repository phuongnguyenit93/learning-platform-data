# Defining Server Streaming RPCs in Spring gRPC

In a **Spring gRPC** service, a **server streaming RPC** allows the client to send **one request message**, after which the server sends back **a stream of zero, one, or many response messages**. The messages are transmitted sequentially within the same RPC over gRPC/HTTP/2, and the server signals completion with a success or error status. The contract is defined using **Protocol Buffers (Protobuf)**, from which code-generation tools generate message classes and stubs for both sides to implement.

This lesson walks through a method that retrieves a list of products by warehouse: the client sends one request, and the server sends each product as a separate message. Through this example, you will learn how to declare **stream** in a **.proto** file, implement the server with Spring, use Java stubs on the client, and handle deadlines, RPC cancellation, status, metadata, TLS, testing, and observability when running the service in production.

## 1. How Does a Server Streaming RPC Work?

Consider finding the products in warehouse **hcm-01**. Instead of packing the entire list into a single response, the server can send each product as a separate response message. The client can begin processing the first product without waiting for the entire list to finish.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as Spring gRPC server
    C->>S: ListProducts(ListProductsRequest)
    S-->>C: ProductView (SKU-001)
    S-->>C: ProductView (SKU-002)
    S-->>C: ProductView (SKU-003)
    S-->>C: onCompleted / gRPC status OK
    Note over C,S: Only 1 request, there can be 0..N responses
~~~

Core rules:

- The client sends **exactly one request message** per method invocation.
- On success, the server can emit **0..N response messages**, matching the message type declared in the Protobuf contract.
- The server ends the stream with **onCompleted()**; a successful call has gRPC status **OK**. An empty stream is valid: the server sends no responses and simply completes.
- When an error occurs, the server calls **onError(...)** with an appropriate gRPC status; do not call **onCompleted()** after an error.
- Message ordering is preserved within **one** gRPC stream. Ordering cannot be implicitly assumed between two separate RPCs or across multiple clients.
- A client may receive several messages before the RPC fails. Previously received messages are not automatically rolled back by gRPC.

| RPC Type | Request | Response on Success | Protobuf Declaration |
| --- | --- | --- | --- |
| Unary | 1 | 1 | **rpc GetProduct(GetRequest) returns (ProductView);** |
| **Server streaming** | **1** | **0..N** | **rpc ListProducts(ListRequest) returns (stream ProductView);** |
| Client streaming | Many | 1 | **rpc Upload(stream Chunk) returns (UploadResult);** |
| Bidirectional streaming | Many | Many | **rpc Chat(stream Message) returns (stream Message);** |

**When should you choose server streaming?** When you need to transfer many results incrementally, subscribe to updates emitted by the server, or let the client process early before all data is ready. For small lists, a unary RPC returning a message with a **repeated** field is also suitable. For queries requiring stable pagination, jumping between independent pages, and resuming via cursor, pagination can be simpler than a long-lived stream.

## 2. Declaring the Contract with Protocol Buffers

Create the file **src/main/proto/inventory.proto**:

~~~proto
syntax = "proto3";

package demo.inventory.v1;

option java_package = "vn.demo.grpc.inventory.v1";
option java_multiple_files = true;
option java_outer_classname = "InventoryProto";

service Inventory {
  // One request selects a warehouse; multiple responses, each response is a product.
  rpc ListProducts(ListProductsRequest) returns (stream ProductView);
}

message ListProductsRequest {
  string warehouse_id = 1;
}

message ProductView {
  string sku = 1;
  int32 available_quantity = 2;
}
~~~

The part that determines the RPC type is:

~~~proto
rpc ListProducts(ListProductsRequest) returns (stream ProductView);
~~~

The **stream** keyword appears only before the **response type**, so this is a server streaming RPC. Placing **stream** before the request type makes the method client streaming; placing it on both sides makes it bidirectional streaming.

Other components to understand:

1. **demo.inventory.v1** is the Protobuf namespace; the full gRPC method name is **/demo.inventory.v1.Inventory/ListProducts**.
2. **java_package** specifies the Java package for generated code; **java_multiple_files** generates separate message classes.
3. The numbers **= 1**, **= 2** are field numbers in the Protobuf binary format. When changing a released contract, do not change the meaning of a field number and use **reserved** for removed field numbers or names.
4. The request is still a regular message. The server can use **warehouse_id** to determine the dataset to emit.

After configuring the **protoc** compiler and the **protoc-gen-grpc-java** plugin in the build system, generated Java code typically includes **ListProductsRequest**, **ProductView**, **InventoryGrpc.InventoryImplBase**, **InventoryGrpc.InventoryStub** (async), and **InventoryGrpc.InventoryBlockingStub**. Do not edit the generated classes directly; edit the **.proto** file and regenerate code. Both server and client must use compatible contract versions.

## 3. Implementing Server Streaming in Spring

Assuming the Spring Boot project has configured the Spring gRPC server, gRPC Java dependencies, and the code-generation step from **inventory.proto**. The following example uses a small sample dataset to clearly demonstrate the stream lifecycle:

~~~java
package vn.demo.app;

import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.List;
import org.springframework.stereotype.Service;
import vn.demo.grpc.inventory.v1.InventoryGrpc;
import vn.demo.grpc.inventory.v1.ListProductsRequest;
import vn.demo.grpc.inventory.v1.ProductView;

@Service
public class InventoryService extends InventoryGrpc.InventoryImplBase {

    @Override
    public void listProducts(
            ListProductsRequest request,
            StreamObserver<ProductView> responseObserver) {

        String warehouseId = request.getWarehouseId().trim();
        if (warehouseId.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("warehouse_id must not be blank")
                    .asRuntimeException());
            return;
        }

        if (!warehouseId.equals("hcm-01")
                && !warehouseId.equals("hn-01")) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("warehouse not found")
                    .asRuntimeException());
            return;
        }

        // Example data: warehouse hn-01 exists but has no products yet.
        List<ProductView> products = warehouseId.equals("hcm-01")
            ? List.of(
                ProductView.newBuilder()
                    .setSku("SKU-001")
                    .setAvailableQuantity(12)
                    .build(),
                ProductView.newBuilder()
                    .setSku("SKU-002")
                    .setAvailableQuantity(5)
                    .build())
            : List.of();

        for (ProductView product : products) {
            // Do not continue generating or sending data when the RPC is cancelled.
            if (Context.current().isCancelled()) {
                return;
            }
            responseObserver.onNext(product);
        }

        if (!Context.current().isCancelled()) {
            responseObserver.onCompleted();
        }
    }
}
~~~

In Spring gRPC integrations that automatically register beans implementing **BindableService**, the **InventoryService** bean is registered with the gRPC server. The exact declaration and server/client auto-configuration depend on the Spring gRPC version or starter in use; in this lesson, **@Service** makes clear that the implementation class is Spring-managed.

Breakdown of the three **StreamObserver** operations:

| Call | Meaning | Usage Rule |
| --- | --- | --- |
| **onNext(item)** | Pushes another **ProductView** to the client | Can be called multiple times while the stream is open |
| **onCompleted()** | Signals all items sent; RPC succeeded | Call exactly once, after the last **onNext**; a stream may have zero **onNext** calls |
| **onError(cause)** | Signals an error and ends the RPC | Call instead of **onCompleted**, do not emit further messages |

In the example, requesting **hcm-01** receives two products, **hn-01** receives a successful but empty stream, while a nonexistent warehouse ID returns **NOT_FOUND**. Distinguish *empty data* from a *resource-not-found error* according to the API's business rules.

**Concurrency note:** A server-side **StreamObserver** does not allow multiple threads to call **onNext** concurrently in an arbitrary manner. If data arrives from multiple asynchronous tasks, the application must serialize send operations on the same observer and ensure only **one** terminal signal. The example uses a short sequential loop for clarity; do not copy large or unbounded loops into the RPC handler thread without throttling.

## 4. Creating a gRPC Client in a Spring Application

A client can consume server streaming via an **async stub**, where each incoming message is delivered to a callback. For server streaming, the **blocking stub** also supports an API returning an **Iterator**. Both use the same Protobuf contract.

Example configuring the channel and two stubs as Spring beans:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import vn.demo.grpc.inventory.v1.InventoryGrpc;

@Configuration
public class InventoryClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel() {
        // Use plaintext only in trusted local/dev environments.
        return ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();
    }

    @Bean
    InventoryGrpc.InventoryStub inventoryStub(
            ManagedChannel inventoryChannel) {
        return InventoryGrpc.newStub(inventoryChannel);
    }

    @Bean
    InventoryGrpc.InventoryBlockingStub inventoryBlockingStub(
            ManagedChannel inventoryChannel) {
        return InventoryGrpc.newBlockingStub(inventoryChannel);
    }
}
~~~

The code above illustrates gRPC Java directly. In real projects, configure the service address, TLS, and channels using the client management mechanism of your Spring gRPC version. Do not create a new channel per product or per request; channels are typically reused.

### 4.1. Async Stub: Processing Each Message via Callback

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import vn.demo.grpc.inventory.v1.InventoryGrpc;
import vn.demo.grpc.inventory.v1.ListProductsRequest;
import vn.demo.grpc.inventory.v1.ProductView;

@Service
public class InventoryClient {

    private final InventoryGrpc.InventoryStub stub;

    public InventoryClient(InventoryGrpc.InventoryStub stub) {
        this.stub = stub;
    }

    public void printProducts(String warehouseId) {
        ListProductsRequest request = ListProductsRequest.newBuilder()
            .setWarehouseId(warehouseId)
            .build();

        stub.withDeadlineAfter(5, TimeUnit.SECONDS)
            .listProducts(request, new StreamObserver<ProductView>() {
                @Override
                public void onNext(ProductView item) {
                    System.out.printf("%s: %d%n",
                        item.getSku(), item.getAvailableQuantity());
                }

                @Override
                public void onError(Throwable error) {
                    Status status = Status.fromThrowable(error);
                    System.err.println(
                        "Stream failed: " + status.getCode());
                }

                @Override
                public void onCompleted() {
                    System.out.println("Received full product list");
                }
            });
    }
}
~~~

Calling **printProducts(...)** initiates the RPC and returns control to the caller; callbacks execute as gRPC data/events arrive. In real applications, avoid long blocking work or throwing unhandled exceptions inside **onNext**; if heavy processing is needed, offload work to an appropriate executor and bound the number of pending tasks.

The execution flow can terminate in one of two ways: **onCompleted** after receiving all data, or **onError** when the RPC fails or is cancelled. **onCompleted receives no additional ProductView**; it only marks completion.

### 4.2. Blocking Stub: Iterating the Stream with Iterator

~~~java
ListProductsRequest request = ListProductsRequest.newBuilder()
    .setWarehouseId("hcm-01")
    .build();

try {
    var products = blockingStub
        .withDeadlineAfter(5, TimeUnit.SECONDS)
        .listProducts(request);

    while (products.hasNext()) {
        ProductView product = products.next();
        System.out.println(product.getSku());
    }
} catch (io.grpc.StatusRuntimeException ex) {
    System.err.println("RPC failed: " + ex.getStatus().getCode());
}
~~~

This snippet sits inside a method that already has a **blockingStub** variable of type **InventoryGrpc.InventoryBlockingStub**. **hasNext()** or **next()** may block waiting for a new response and may throw **StatusRuntimeException** if the stream errors. Only use the blocking stub where synchronous waiting is acceptable; avoid calling it directly on an event loop or a request-handling thread with non-blocking constraints.

## 5. Deadlines, Cancellation, and Flow Control

### Deadlines Apply to the Entire Stream

**withDeadlineAfter(5, TimeUnit.SECONDS)** limits the **entire lifetime of the RPC**, rather than granting an additional five seconds after each **onNext**. A long continuous stream can still be terminated with **DEADLINE_EXCEEDED** even while steadily emitting messages if the overall deadline elapses.

For finite streams, set the deadline according to the request completion budget. For long-lived update streams, design disconnect/reconnect intervals, resumption from a cursor/sequence number, and a reconnect policy. When forwarding a request across multiple services, account for the time budget of the parent RPC and its child RPCs.

### Cancelling an RPC When Data Is No Longer Needed

A client can cancel an RPC when a user leaves a screen or no longer needs the results. On the gRPC Java server side, you can check **Context.current().isCancelled()** as in the example, or use **ServerCallStreamObserver** to receive cancellation signals. With an async client, **ClientResponseObserver** provides a **ClientCallStreamObserver** in **beforeStart(...)** to manage the call, including **cancel(...)**.

If the server is reading a database, consuming a queue, or running background work, stop those tasks when the stream is cancelled. **Cancelling an RPC does not automatically roll back data changes** already made by the server; design idempotency and transactions for actions with side effects.

### Rate Control and Backpressure

When a client reads slowly, calling **onNext** continuously can increase the amount of data queued for transmission. gRPC Java provides **flow control** support along with **ServerCallStreamObserver.isReady()** and **setOnReadyHandler(...)** so the server can throttle message emission.

A safe workflow for large streams is:

1. Fetch data in small chunks or from a pausable source; do not load an entire massive dataset into memory.
2. Only send more messages when the observer is ready, while bounding the application buffer.
3. When the observer is no longer ready, stop emitting and wait for the **onReady** event to resume.
4. Ensure calls to **onNext**, **onError**, and **onCompleted** on the same stream are serialized; handle mid-stream client cancellation explicitly.

**isReady()** is a signal for throttling transmission pressure, not a guarantee that the message just sent has already been processed by the client. For streams with only a few items like the example, a sequential loop suffices for illustration; for long streams, control both the data source and the emission rate.

## 6. Status, Partial Data, and Error Handling

Suppose the server sends two products and then encounters an error while querying the third product:

~~~text
Client receives SKU-001
Client receives SKU-002
Server encounters a query error
Server terminates the RPC with status INTERNAL
Client receives onError(INTERNAL)
~~~

The two received products remain in the client application, yet **the entire RPC ends in error**. Therefore, you must not assume that any received data constitutes a complete list. If the business logic requires a consistent snapshot or atomic processing, establish clear conventions: snapshot/version, sequence number, expected total count, confirmation marker, or switch to unary if the data size fits.

| Status | Typical Case | How the Client Reacts |
| --- | --- | --- |
| **OK** | Stream completes successfully | Use the complete result |
| **INVALID_ARGUMENT** | **warehouse_id** is empty or malformed | Fix the request before calling again |
| **NOT_FOUND** | Warehouse does not exist per API contract | Display warehouse not found |
| **UNAUTHENTICATED** | Missing/invalid credentials | Refresh credentials if permitted |
| **PERMISSION_DENIED** | Client lacks permission to read warehouse | Stop and handle access control |
| **DEADLINE_EXCEEDED** | Exceeded total RPC time budget | Decide whether to keep/discard partial data |
| **CANCELLED** | RPC was cancelled | Release associated resources |
| **UNAVAILABLE** | Connection lost/service temporarily unavailable | May reconnect according to policy |
| **INTERNAL** | Server encountered an unexpected error | Log status code and investigate server-side |

Validate and return input errors **before** emitting any messages. For errors occurring after data has already been sent, emit **onError** once and let the client decide how to handle partial data. Do not return errors via a **ProductView** containing a dummy value like **sku = "ERROR"**, as that breaks the semantics of the data contract.

Retrying from the beginning may produce duplicate products if the client has already processed part of the stream. For mutable lists, provide stable IDs, sequence numbers, or cursors so the client can deduplicate and resume, and clearly specify how snapshots are taken when consistency is required.

## 7. Metadata, Interceptors, and TLS for Streaming

**gRPC metadata** carries call information, usually in headers/trailers, such as authentication tokens, request IDs, or trace IDs. Client/server **interceptors** can be applied consistently across the entire RPC: checking access permissions, creating tracing spans, recording timing, counting messages, or attaching correlation IDs. With server streaming, a single RPC has **one start/end** but **many message-send events**; metrics should distinguish call counts from message counts.

Header metadata is typically sent at the start of the call; do not assume you can attach different metadata to each **ProductView** mid-stream. If each item needs its own timestamp, sequence number, or business information, declare them as fields on the Protobuf response.

The channel configuration code above uses **usePlaintext()** for local/dev illustration. In production deployments, protect the transport with **TLS**, verify the server's identity, and consider **mTLS** when two services must mutually authenticate. Enforce authentication/authorization before serving warehouse data and avoid logging tokens or sensitive payloads; interceptors or the security layer must block unauthorized streams.

## 8. Testing Server Streaming RPCs

With gRPC Java, an **in-process server/channel** lets you test emitting multiple messages, empty streams, and gRPC statuses without opening a network port. The following illustrative test assumes the **InventoryService** class from the example has been created:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.inventory.v1.InventoryGrpc;
import vn.demo.grpc.inventory.v1.ListProductsRequest;
import vn.demo.grpc.inventory.v1.ProductView;

class InventoryServiceTest {

    @Test
    void streamsProductsAndHandlesEmptyAndInvalidRequests()
            throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new InventoryService())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            var stub = InventoryGrpc.newBlockingStub(channel);

            Iterator<ProductView> products = stub.listProducts(
                ListProductsRequest.newBuilder()
                    .setWarehouseId("hcm-01").build());
            List<String> skus = new ArrayList<>();
            products.forEachRemaining(p -> skus.add(p.getSku()));
            assertEquals(List.of("SKU-001", "SKU-002"), skus);

            Iterator<ProductView> emptyStream = stub.listProducts(
                ListProductsRequest.newBuilder()
                    .setWarehouseId("hn-01").build());
            assertFalse(emptyStream.hasNext());

            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> {
                    Iterator<ProductView> invalid = stub.listProducts(
                        ListProductsRequest.newBuilder()
                            .setWarehouseId(" ").build());
                    invalid.hasNext(); // Error may occur during iteration.
                });
            assertEquals(Status.Code.INVALID_ARGUMENT,
                error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

The test above requires the **grpc-inprocess** dependency and JUnit matching the gRPC Java version in use. It tests the server streaming contract and lifecycle at the gRPC Java level, but does not verify Spring bean registration or channel security.

In integration tests with a running **Spring context**, add cases verifying the service is actually registered, connecting to the server via the project's gRPC configuration, and testing **deadlines**, **cancellation**, **interceptors**, and **TLS**. For long streams, simulate a slow-reading client and verify that buffers do not grow unboundedly; for streams that fail after several messages, verify the client handles partial data as specified.

## 9. Monitoring and Operations

Because server streaming can last longer than unary RPCs, track dedicated metric groups:

- **Open in-flight RPCs**, total started/completed RPCs, and cancelled stream counts.
- **Time to first message**, total stream duration, and latency percentiles.
- **Messages/bytes sent per RPC** and emission rate over time.
- **Error rates by gRPC status** such as **UNAVAILABLE**, **DEADLINE_EXCEEDED**, and **INTERNAL**.
- **Memory pressure, queue sizes, open data sources**, and thread utilization.

Combine metrics with distributed tracing to tell whether a stream is slow at the database query, buffer, or network. A log saying only “RPC started” is insufficient to detect hung streams or streams that never complete. Set reasonable time and resource limits, detect abnormally long-lived streams, and define a clear connection-draining strategy during application shutdown.

## 10. Summary and Self-Check Questions

To define a **server streaming RPC**, declare the Protobuf method with the syntax **rpc Method(Request) returns (stream Response)**. In the Java server, write each response with **onNext**, then terminate with **onCompleted** or **onError**. On the client, use an **async stub** for callbacks or a **blocking stub** to iterate an **Iterator**. When deploying in a Spring application, combine service registration, channel management, deadlines, cancellation, flow control, TLS, testing, and telemetry so streams run reliably.

Self-check using these questions:

1. What is the sole difference in the **.proto** declaration between a unary RPC and a server streaming RPC?
2. What should the server call when a warehouse exists but has no products? How does this differ from the warehouse not existing?
3. If the client has received 20 messages and then the RPC returns **UNAVAILABLE**, can it assume the data is complete? How should resumption be designed?
4. Why is **withDeadlineAfter(5, SECONDS)** inappropriate if a stream is expected to run for hours?
5. When a client reads slowly, how do **isReady()** and bounded buffers help protect the server?

Once you can answer these questions and run the example, you have grasped the mechanics of server streaming RPCs and are ready to distinguish them from client streaming and bidirectional streaming in larger Spring gRPC services.
