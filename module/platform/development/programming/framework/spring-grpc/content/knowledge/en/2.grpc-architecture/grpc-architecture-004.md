# RPC methods and request, response messages

## Learning objectives

After this lesson, you can:

- Distinguish an **RPC method** from a regular Java method, and explain why request/response messages are part of the gRPC contract.
- Read and declare **rpc** methods in Protocol Buffers (**.proto**), covering all four unary and streaming patterns.
- Understand how a method is identified, routed over HTTP/2, and linked to its **method descriptor**, client stub, and server implementation.
- Design request/response messages using field numbers, data types, **optional**, **repeated**, **oneof**, and enums; distinguish business data from metadata and gRPC status.
- Implement a unary RPC with **grpc-java** in Spring, set deadlines, return valid errors, and test the contract.
- Recognize schema changes that can break older clients, as well as performance and reliability boundaries of streaming methods.

## 1. What is an RPC method and how does it differ from a Java method?

In the **SPRING_GRPC** ecosystem, clients call a remote service using Java APIs generated from a **Protocol Buffers** contract. On the client side, the statement looks almost like a local method call:

~~~java
GetOrderResponse response = orderStub.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build());
~~~

However, **getOrder()** here is an **RPC method**: the call must pass through the stub, Channel, transport, and server runtime before reaching business logic. It can incur network latency, deadlines, authentication errors, connection drops, or server errors. Ordinary Java calls within the same process do not cross those network boundaries.

Every RPC method is bound to three things published in the contract:

1. **Identity**: which service provides the method, and what the method is named.
2. **Request type**: which protobuf message the caller must send.
3. **Response type**: which protobuf message the caller will receive, and whether each side sends one or many messages.

Actual communication is also governed by **metadata, deadlines, credentials, TLS, interceptors, retries, and observability** configuration. These belong to the runtime/method-usage policy; method syntax in .proto does not configure them automatically.

~~~mermaid
sequenceDiagram
    participant C as Spring client service
    participant S as Generated client stub
    participant H as ManagedChannel/HTTP2
    participant R as gRPC server runtime
    participant I as Spring server implementation
    C->>S: getOrder(GetOrderRequest)
    S->>H: MethodDescriptor + serialized request
    H->>R: POST /shop.orders.v1.OrderQueryService/GetOrder
    R->>I: getOrder(request, responseObserver)
    I-->>R: onNext(GetOrderResponse)
    I-->>R: onCompleted()
    R-->>H: response message + grpc-status
    H-->>S: deserialize + status
    S-->>C: GetOrderResponse
~~~

**An RPC method is not necessarily an HTTP request-response in the REST sense.** With server/client/bidirectional streaming, a single RPC can transmit many protobuf messages over **one HTTP/2 stream**.

### 1.1. Comparing related elements

| Component | Role | Example |
| --- | --- | --- |
| **Service** | Groups RPCs with a shared purpose | **OrderQueryService** |
| **RPC method** | A remote operation and bidirectional data types | **GetOrder(GetOrderRequest) returns (GetOrderResponse)** |
| **Request message** | Input payload, with schema and encoded data | **order_id = "order-42"** |
| **Response message** | Success result payload, with schema | **order.id, order.status** |
| **RPC metadata** | Header/trailer information at the call layer | Authorization, trace ID, request ID |
| **gRPC status** | Success/failure outcome of the call | **OK**, **INVALID_ARGUMENT**, **NOT_FOUND** |
| **ManagedChannel** | Provides the path from client to server and manages connections | Channel pointing to backend |
| **Implementation** | Registered method-handling logic on the server | Java override **getOrder(...)** |

The easiest pair to confuse is **response message** and **gRPC status**. The response describes data upon successful processing; gRPC status indicates whether the call succeeded or failed. On failure, the server may send only status and trailers, with no success response message.

## 2. Defining service, method, request, and response in .proto

A **.proto** file is the shared contract source between client and server. The example below defines an order query service with all four RPC types to make the relationship between methods and messages clear.

~~~proto
syntax = "proto3";

package shop.orders.v1;

option java_package = "com.example.shop.orders.v1";
option java_multiple_files = true;
option java_outer_classname = "OrdersProto";

service OrderQueryService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc WatchOrders(WatchOrdersRequest) returns (stream OrderEvent);
  rpc ImportOrderEvents(stream OrderEvent) returns (ImportOrderEventsResponse);
  rpc SyncOrders(stream SyncOrdersRequest) returns (stream SyncOrdersResponse);
}

message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
}

message GetOrderResponse {
  Order order = 1;
  string etag = 2;
}

message Order {
  string id = 1;
  string customer_id = 2;
  OrderStatus status = 3;
  int64 created_at_epoch_ms = 4;
  repeated OrderLine lines = 5;
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_COMPLETED = 2;
  ORDER_STATUS_CANCELLED = 3;
}

message WatchOrdersRequest {
  string customer_id = 1;
}

message OrderEvent {
  string order_id = 1;
  OrderStatus new_status = 2;
  int64 changed_at_epoch_ms = 3;
}

message ImportOrderEventsResponse {
  int32 accepted_count = 1;
}

message SyncOrdersRequest {
  string cursor = 1;
}

message SyncOrdersResponse {
  string next_cursor = 1;
  Order order = 2;
}
~~~

From this service definition, **protoc** and **protoc-gen-grpc-java** typically generate:

- Java messages such as **GetOrderRequest**, **GetOrderResponse**, **Order**, **OrderEvent**, along with **Builder** and parse/serialize APIs.
- The **OrderQueryServiceGrpc** class containing method descriptors, factories for client stub types, and the server base class **OrderQueryServiceImplBase**.
- Stubs **OrderQueryServiceBlockingStub**, **OrderQueryServiceStub** (async), and **OrderQueryServiceFutureStub**.

**Do not edit auto-generated Java code directly.** Modify the .proto file, rerun the generator, and update affected callers/implementations.

### 2.1. Significance of method names in the protocol

The **GetOrder** method belonging to service **OrderQueryService** in protobuf package **shop.orders.v1** has:

~~~text
Full service name: shop.orders.v1.OrderQueryService
Full method name:  shop.orders.v1.OrderQueryService/GetOrder
HTTP/2 :path:     /shop.orders.v1.OrderQueryService/GetOrder
~~~

**java_package** specifies the Java package of generated classes (**com.example.shop.orders.v1**); it does not change the full method name on the network. The .proto filename is not part of the RPC path either. Changing the protobuf package, service name, or method name used by clients changes the RPC path and can result in **UNIMPLEMENTED** for older clients.

### 2.2. What does a method signature specify?

Syntactically:

~~~proto
rpc MethodName(RequestType) returns (ResponseType);
~~~

For a standard RPC method:

- **RequestType** and **ResponseType** are protobuf **message types**. Do not declare **rpc GetOrder(string) returns (int32)** directly; use messages with the corresponding fields.
- The **stream** keyword before a type means that side sends **a sequence of messages**.
- Every method has a name, request type, and response type; there is no parameter-based overloading like in Java methods.
- If no request/response content is needed, you can use **google.protobuf.Empty**; there is still a message type, even with no fields.

Example:

~~~proto
import "google/protobuf/empty.proto";

service DiagnosticService {
  rpc Ping(google.protobuf.Empty) returns (google.protobuf.Empty);
}
~~~

**Note:** naming a method **Ping** does not automatically mean the runtime enables HTTP/2 PING or keepalive mechanisms. It is still an application-layer RPC.

## 3. Four RPC types determined by the signature

Following the same method definition rule, the **stream** keyword expands the number of messages sent.

| Type | Signature in .proto | Logical communication | Usage scenario |
| --- | --- | --- | --- |
| **Unary** | **rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);** | One request, one success response | Read/write a single entity, short operations |
| **Server streaming** | **rpc WatchOrders(WatchOrdersRequest) returns (stream OrderEvent);** | One request, zero to many responses | Watching changes, progressive data emission |
| **Client streaming** | **rpc ImportOrderEvents(stream OrderEvent) returns (ImportOrderEventsResponse);** | Zero to many requests, one success response | Batch import or aggregation |
| **Bidirectional streaming** | **rpc SyncOrders(stream SyncOrdersRequest) returns (stream SyncOrdersResponse);** | Zero to many messages in each direction | Two-way sync or interactive sessions |

A **successful** unary RPC must return exactly one response message of the declared type. On error, the server can terminate with a status without returning a success response message. With streaming, a side may send **0..n** messages before finishing.

### 3.1. Unary

~~~proto
rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
~~~

The client builds **GetOrderRequest**, invokes the stub, and receives **GetOrderResponse** or a gRPC error. This is the simple choice for most bounded operations, such as reading an order's status.

### 3.2. Server streaming

~~~proto
rpc WatchOrders(WatchOrdersRequest) returns (stream OrderEvent);
~~~

The client sends **one** WatchOrdersRequest and receives multiple **OrderEvent** messages. The server can emit results incrementally, stopping when there is no more data or when the client cancels or the deadline expires. In Java, callers can use the async stub and a response observer; the traditional blocking stub also supports server streaming via an **Iterator**.

**Never assume a stream runs forever.** A stream can complete normally, terminate with an error, or be cancelled. The API must clearly define stop rules, event cadence, and cursor/resume semantics if needed.

### 3.3. Client streaming

~~~proto
rpc ImportOrderEvents(stream OrderEvent) returns (ImportOrderEventsResponse);
~~~

The client opens the call and sends multiple **OrderEvent** messages; after the last message, the client calls **onCompleted()** on the request observer to half-close the send direction. The server processes them and emits one summary **ImportOrderEventsResponse** before completing the RPC.

If the client forgets to half-close, the server may keep waiting for more data and the call will only end upon deadline, cancellation, or error.

### 3.4. Bidirectional streaming

~~~proto
rpc SyncOrders(stream SyncOrdersRequest) returns (stream SyncOrdersResponse);
~~~

Both sides can send messages independently: the server can return a response even before the client finishes sending requests. Do not assume a **one request ↔ one response** mapping by default. If ACKs, sequence numbers, handshake protocols, retries, or resume are needed, they must be described in the **messages** and contract documentation.

~~~mermaid
sequenceDiagram
    participant Client
    participant Server
    Client->>Server: SyncOrdersRequest(cursor="a")
    Server-->>Client: SyncOrdersResponse(next_cursor="b")
    Server-->>Client: SyncOrdersResponse(next_cursor="c")
    Client->>Server: SyncOrdersRequest(cursor="c")
    Client->>Server: half-close (done sending)
    Server-->>Client: SyncOrdersResponse(next_cursor="d")
    Server-->>Client: trailers grpc-status=OK
~~~

Even though there are many messages, all of them belong to **one RPC on one HTTP/2 stream**; this is different from opening a separate HTTP/2 stream for each message.

## 4. Designing request messages

A request should express **clear intent** and carry enough business data, for example:

~~~proto
message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
}
~~~

Here:

- **order_id** is the business identifier to locate the order. Proto3 allows this field to be absent and a string getter returns an empty string, so **the server must validate it itself** if an ID is required.
- **locale** is optional; **optional string** allows distinguishing **not sent** from **sent as an empty string**.
- The numbers **1**, **2** are **field numbers** in the protobuf wire format, not display order in JSON or Java parameter order.

In generated Java code, creating the request can look like:

~~~java
GetOrderRequest request = GetOrderRequest.newBuilder()
        .setOrderId("order-42")
        .setLocale("vi-VN")
        .build();

// A Java class generated from proto3 optional typically has:
boolean localeProvided = request.hasLocale();
~~~

Because generated Java protobuf messages are typically immutable after **build()**, creating request variants is done through a builder or **toBuilder()**. This helps when multiple threads read the request, though it does not replace application-level synchronization responsibility.

### 4.1. Choosing field types

| Protobuf type | Example | Design considerations |
| --- | --- | --- |
| **string** | ID, name, locale | UTF-8, default empty string; document validation rules clearly |
| **int32/int64** | Quantity, timestamp | Define units and range; int64 has special representation in ProtoJSON |
| **bool** | Feature flag | Default **false**; use **optional** if distinguishing unset is needed |
| **bytes** | Hash/binary data | Avoid putting unbounded payloads in a single message |
| **enum** | Order status | Value 0 should be **UNSPECIFIED**; handle unknown values |
| **message** | Nested object | Presence can be checked on singular message fields |
| **repeated T** | List of line items | Bound element count; ordering may carry meaning |
| **map<K,V>** | Keyed attributes | Maps do not guarantee business ordering; avoid relying on serialization order |
| **oneof** | One of several lookup keys | Represents mutually exclusive options |
| **optional T** | Scalar field with presence | Distinguishes absent value from default value |

Defining a **timestamp** as **int64 created_at_epoch_ms** is one approach, provided the unit is stated explicitly. A more semantically expressive option for time is the standard type **google.protobuf.Timestamp**:

~~~proto
import "google/protobuf/timestamp.proto";

message OrderAudit {
  string order_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
}
~~~

Pick one consistent convention across the entire API; do not mix seconds, milliseconds, and microseconds without stating it clearly.

### 4.2. Presence: "not sent" vs "sent empty"

In proto3, many scalar fields lack explicit presence when declared normally:

~~~proto
message UpdateOrderRequest {
  string order_id = 1;
  string note = 2;
}
~~~

With a plain **note**, the Java getter **getNote()** returns **""** both when unset and when set to an empty string. This can make an update API ambiguous: did the user want to clear the note or leave the note unchanged?

The **optional** modifier partially solves this:

~~~proto
message UpdateOrderRequest {
  string order_id = 1;
  optional string note = 2;
}
~~~

With the corresponding generated Java code:

~~~java
if (request.hasNote()) {
    // The client explicitly requested to update note,
    // even when the value is an empty string.
    String newNote = request.getNote();
}
~~~

If you need patch-style updates across multiple fields, you can use **google.protobuf.FieldMask** or design a dedicated update request. Policies on updatable fields and empty values must still be clearly documented.

### 4.3. Oneof for multiple request variants

~~~proto
message FindOrderRequest {
  oneof lookup_key {
    string order_id = 1;
    string external_reference = 2;
  }
}
~~~

**oneof** represents selecting at most one field in the group. It **does not require** at least one field to be set: the server must check that **lookup_key** is populated before processing. In Java, generated code can provide **getLookupKeyCase()** to inspect which option was selected.

A common design mistake is placing multiple scalar fields like **order_id** and **external_reference** side by side without defining precedence when both are populated. **oneof** makes the contract clearer and reduces ambiguity.

### 4.4. Where should request validation live?

Proto only defines structure and certain type constraints. It does not guarantee **order_id** exists, **quantity** is greater than 0, or the caller is authorized to read the order. Therefore:

- **Client** validates known constraints early to avoid unnecessary RPCs; this cannot be treated as the sole line of defense.
- **Server implementation** enforces validation and authorization for every call.
- **Interceptors** suit authentication, tracing, and cross-service policies, while business validation usually lives in the service/domain layer.
- **Status.INVALID_ARGUMENT** for invalid requests; **NOT_FOUND** for missing resources; **PERMISSION_DENIED** when the caller lacks permission.

Even when using a validation library tied to protobuf, declaring rules in the schema only takes effect if the build/runtime actually includes a component that enforces those rules.

## 5. Designing response messages

The **GetOrder** method returns a wrapper response:

~~~proto
message GetOrderResponse {
  Order order = 1;
  string etag = 2;
}
~~~

The advantage of a dedicated wrapper is that you can add fields like **etag**, paging tokens, or provenance without changing the method's response type. It also keeps the success payload cleanly separated from gRPC status/errors.

In Java:

~~~java
Order order = Order.newBuilder()
        .setId("order-42")
        .setCustomerId("customer-7")
        .setStatus(OrderStatus.ORDER_STATUS_PENDING)
        .setCreatedAtEpochMs(1_700_000_000_000L)
        .build();

GetOrderResponse response = GetOrderResponse.newBuilder()
        .setOrder(order)
        .setEtag("version-3")
        .build();
~~~

Since **order** is a singular message field, the client can check **hasOrder()** before reading. For **GetOrder**, if the convention says success must include `order`, the server must guarantee that; proto does not enforce message-field presence by itself.

### 5.1. Responses for lists and pagination

For a unary RPC returning a list, a wrapper is typically used to carry items and a pagination token:

~~~proto
message SearchOrdersRequest {
  string customer_id = 1;
  int32 page_size = 2;
  string page_token = 3;
}

message SearchOrdersResponse {
  repeated Order orders = 1;
  string next_page_token = 2;
}
~~~

You must agree on maximum **page_size**, the meaning of an empty **next_page_token**, and result stability when data changes. **repeated Order** lets you return multiple items in one response, yet it is still **one protobuf message** in a unary RPC; for very large lists, consider pagination or server streaming.

### 5.2. When should a response carry business error codes?

Avoid adding a **success: bool** or **error_code** field and returning **grpc-status: OK** for everything when the failure should actually be represented by a gRPC status. That makes it hard for clients and metrics to distinguish failed RPCs from successful ones.

However, a successful response can contain valid business states: for example, an order being **PENDING** or **COMPLETED** is **OrderStatus** data, not a transport error. Distinguish carefully:

| Scenario | Usually appropriate representation |
| --- | --- |
| Pending order found | **GetOrderResponse.order.status = PENDING**, gRPC **OK** |
| Request missing ID | **INVALID_ARGUMENT**, safe error description |
| Order does not exist | **NOT_FOUND** |
| Caller not allowed to view order | **PERMISSION_DENIED**, avoid leaking details |
| Backend temporarily unavailable | **UNAVAILABLE** |
| RPC exceeded time limit | **DEADLINE_EXCEEDED** on caller side |

When structured error details are needed, the gRPC ecosystem can use **google.rpc.Status** and error details via the rich error model. This is an optional extension requiring matching support on client and server; do not confuse the **google.rpc.Status** message with the basic **grpc-status** in HTTP/2 trailers.

## 6. From messages to bytes: how gRPC transports data

Generated Java request/response messages handle protobuf serialization/deserialization. Stubs and the runtime apply message marshallers and transmit over HTTP/2.

A gRPC message on the wire is typically structured as:

~~~text
+----------------+--------------------------+-------------------------+
| Compressed-Flag| Message-Length           | Message bytes           |
| 1 byte         | 4 bytes, big-endian      | serialized protobuf     |
+----------------+--------------------------+-------------------------+
~~~

**The first five bytes** form gRPC's message framing layer: 1 byte for compression flag and 4 bytes for payload length. Multiple messages can appear sequentially on one HTTP/2 stream. One message can be split across multiple HTTP/2 DATA frames; conversely, one DATA frame can hold parts of multiple messages. Consequently:

- **Protobuf message** is not synonymous with **HTTP/2 frame**.
- **One RPC** is not synonymous with **one protobuf message** when streaming is used.
- **One RPC** normally uses **one HTTP/2 stream**, even when there are hundreds of messages.
- **An HTTP/2 connection** can multiplex many RPCs/streams concurrently.

Unary **GetOrder** example:

~~~text
Client -> Server:
  HEADERS   :method=POST
            :path=/shop.orders.v1.OrderQueryService/GetOrder
            content-type=application/grpc
            te=trailers
            grpc-timeout=2S
  DATA      [5-byte gRPC prefix][serialized GetOrderRequest]
  END_STREAM (client finished send direction)

Server -> Client:
  HEADERS   :status=200
            content-type=application/grpc
  DATA      [5-byte gRPC prefix][serialized GetOrderResponse]
  HEADERS   grpc-status=0    (trailers)
  END_STREAM
~~~

This is a **logical** representation for learning, not an actual binary frame dump. The **grpc-timeout** header is the relative time remaining before the deadline and is used by the runtime as appropriate; exact transmission details depend on caller and transport. Error cases can be **trailers-only** responses with no DATA frame.

**HTTP status 200 does not guarantee RPC success.** The gRPC client inspects **grpc-status** at the end of the exchange and translates it into the corresponding result or error.

### 6.1. Message size and performance

Protobuf can represent data more compactly than JSON in many scenarios, though concrete efficiency depends on schema and payload. Do not assume gRPC is always faster regardless of context.

Watch out for:

- **Serialized message size** and inbound/outbound message limits configured by the framework/transport.
- **Number of repeated elements**: a very large unary response can cause sudden memory allocation spikes.
- **Streaming message rate** and callback/serialization overhead.
- **HTTP/2 flow control** at stream and connection levels; the sender may have to wait for the receiver.
- **Deadlines and cancellation**: continuing wasted work after the caller has left consumes resources.
- **Compression**: can reduce bandwidth at the cost of CPU; enable only after empirical evaluation.

For APIs returning very large numbers of records, compare **unary + paging** against **server streaming**, evaluating client experience, recovery cost, backend load, and resumability after interruption.

## 7. Implementing a unary method in Spring with grpc-java

Below is an example of **plain gRPC Java managed by Spring beans**, using the messages and service defined in section 2. It separates **service implementation**, **server registration**, and **client stub** to make the architecture clear. When using Spring gRPC auto-configuration, use the service/stub registration mechanism of your library version to avoid starting duplicate servers on the same port.

### 7.1. Server implementation

~~~java
package com.example.shop.server;

import com.example.shop.orders.v1.GetOrderRequest;
import com.example.shop.orders.v1.GetOrderResponse;
import com.example.shop.orders.v1.Order;
import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import com.example.shop.orders.v1.OrderStatus;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class OrderQueryEndpoint
        extends OrderQueryServiceGrpc.OrderQueryServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        String orderId = request.getOrderId().trim();

        if (orderId.isEmpty()) {
            responseObserver.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("order_id must not be empty")
                            .asRuntimeException());
            return;
        }

        // Demo: the data store only contains one order.
        if (!"order-42".equals(orderId)) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Order not found")
                            .asRuntimeException());
            return;
        }

        Order order = Order.newBuilder()
                .setId("order-42")
                .setCustomerId("customer-7")
                .setStatus(OrderStatus.ORDER_STATUS_PENDING)
                .setCreatedAtEpochMs(1_700_000_000_000L)
                .build();

        GetOrderResponse response = GetOrderResponse.newBuilder()
                .setOrder(order)
                .setEtag("version-3")
                .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

The **getOrder(...)** method matches the signature from the generated base class. **StreamObserver<GetOrderResponse>** is an application-layer callback API; it is not an HTTP/2 stream object that we manipulate directly.

For a successful unary call, the server sends **one** response via **onNext()**, then **onCompleted()**. On failure, it sends **onError()** and stops. An RPC must not emit further responses after calling **onCompleted()** or **onError()**. A real server should delegate order retrieval to a business service/repository, map exceptions appropriately, and avoid leaking internal details in the description.

### 7.2. Registering with the gRPC server

~~~java
package com.example.shop.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server orderServer(OrderQueryEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(endpoint)
                .build();
    }
}
~~~

**@Component** registers the implementation in the Spring context. **addService(endpoint)** is what registers the method handlers with the gRPC server. These two steps have distinct responsibilities.

**initMethod = "start"** starts the server on bean initialization; **destroyMethod = "shutdown"** requests shutdown when closing the Spring context. Production deployments should have a **graceful shutdown** strategy, waiting with a bounded timeout for in-flight RPCs to finish.

The example only overrides **GetOrder**. The remaining RPCs in the contract will need their own implementations; calling an un-overridden method usually returns **UNIMPLEMENTED** from the base class.

### 7.3. Client stub and ManagedChannel in Spring

The following example lives in a **separate client application**:

~~~java
package com.example.shop.client;

import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        // Local demo; do not use plaintext as the default for real environments.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderQueryServiceGrpc.OrderQueryServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {
        return OrderQueryServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

~~~java
package com.example.shop.client;

import com.example.shop.orders.v1.GetOrderRequest;
import com.example.shop.orders.v1.GetOrderResponse;
import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupClient {
    private final OrderQueryServiceGrpc.OrderQueryServiceBlockingStub stub;

    public OrderLookupClient(
            OrderQueryServiceGrpc.OrderQueryServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetOrderResponse findOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        try {
            return stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getOrder(request);
        } catch (StatusRuntimeException error) {
            Status.Code code = error.getStatus().getCode();
            // Example: the application layer maps the code to an appropriate error.
            throw new IllegalStateException(
                    "GetOrder failed: " + code, error);
        }
    }
}
~~~

**ManagedChannel** should be reused to avoid opening a new connection on every call. **withDeadlineAfter(...)** creates a new stub with call options for that invocation; set deadlines close to the call time rather than keeping an expired deadline on a long-lived stub.

**Blocking stubs** fit unary calls in synchronous flows but block the caller thread. For streaming RPCs or asynchronous applications, use an async stub and manage observer lifecycles, backpressure, and cancellation.

**usePlaintext()** is only for local examples or tightly controlled networks. In real environments, configure TLS/mTLS, trust chains, and credentials according to your deployment architecture.

## 8. Mapping methods to client/server APIs in grpc-java

The RPC definition determines the Java signatures the generator produces. The following table helps read code from both sides.

| RPC | Server override | Client usage |
| --- | --- | --- |
| **Unary GetOrder** | **void getOrder(GetOrderRequest, StreamObserver<GetOrderResponse>)** | Blocking stub returns **GetOrderResponse**; async stub takes response observer |
| **Server streaming WatchOrders** | **void watchOrders(WatchOrdersRequest, StreamObserver<OrderEvent>)** | Blocking stub returns **Iterator<OrderEvent>**; async stub receives multiple onNext |
| **Client streaming ImportOrderEvents** | **StreamObserver<OrderEvent> importOrderEvents(StreamObserver<ImportOrderEventsResponse>)** | Async stub returns request observer; caller sends multiple onNext |
| **Bidi SyncOrders** | **StreamObserver<SyncOrdersRequest> syncOrders(StreamObserver<SyncOrdersResponse>)** | Async stub returns request observer; receives responses independently |

Some codegen modes or library versions add extra stub variants, but RPC patterns and message directions remain governed by the contract.

### 8.1. Two observers in client streaming

~~~java
// asyncStub is OrderQueryServiceGrpc.OrderQueryServiceStub.
// Callback flow example only; retry/backpressure are not handled here.
StreamObserver<ImportOrderEventsResponse> responseObserver =
        new StreamObserver<ImportOrderEventsResponse>() {
    @Override
    public void onNext(ImportOrderEventsResponse value) {
        System.out.println("Accepted: " + value.getAcceptedCount());
    }

    @Override
    public void onError(Throwable error) {
        System.err.println(
                "RPC failed: " + Status.fromThrowable(error).getCode());
    }

    @Override
    public void onCompleted() {
        System.out.println("Import completed");
    }
};

StreamObserver<OrderEvent> requestObserver =
        asyncStub.importOrderEvents(responseObserver);

requestObserver.onNext(OrderEvent.newBuilder()
        .setOrderId("order-42")
        .setNewStatus(OrderStatus.ORDER_STATUS_COMPLETED)
        .build());

requestObserver.onCompleted();
~~~

In this snippet, **StreamObserver**, **Status**, **OrderEvent**, **OrderStatus**, and **ImportOrderEventsResponse** are imported from grpc-java and generated code, while **asyncStub** has already been created from a shared Channel.

**requestObserver.onCompleted()** only marks that the client has finished its send direction. The caller must still wait for **responseObserver.onCompleted()** or **onError()** to learn the final outcome of the RPC.

### 8.2. Multiple responses do not mean multiple method calls

If the server sends three **OrderEvent** messages in a single **WatchOrders** call, the client typically receives three **onNext(...)** callbacks followed by one **onCompleted()**. That is still one call, one deadline, and one terminal status. With streaming, each observer is bound to **one specific RPC**; never reuse an observer from a finished call for a new call.

If multiple threads emit messages onto a single **StreamObserver**, the application must coordinate writes; observers do not automatically guarantee thread safety for concurrent calls. When sending large volumes, use **isReady()/setOnReadyHandler(...)** on grpc-java's specialized observers to integrate flow control and backpressure.

## 9. Metadata, deadlines, status, and interceptors related to methods

While request/response messages define business data, a real RPC also has context for access control, time bounds, and tracing.

### 9.1. Metadata lives outside the request message

**Metadata** typically travels in headers/trailers, such as authorization tokens and correlation IDs. Do not stuff authentication tokens into every request message just to pass them between services; it is cleaner to use **CallCredentials** or client interceptors according to your application's mechanism.

If a field has business meaning and needs persistence/auditing like **customer_id**, it can belong in the request/response schema. If it is only a **trace ID** or credential spanning many methods, metadata is the more suitable place. Avoid logging tokens or sensitive information.

### 9.2. Deadline is a property of the call

Suppose the client calls **GetOrder** with a 2-second deadline. If the backend is slow, the caller may receive **DEADLINE_EXCEEDED** even when the request is structurally completely valid. Increasing deadlines does not replace backend optimization or overload control.

The server should observe cancellation and stop unnecessary work when the client disconnects. However, a client timeout **does not guarantee** the server rolled back a write operation; for RPCs with side effects, retry policies must account for **idempotency** and duplicate-request handling.

### 9.3. Do not confuse business state codes with gRPC status

**OrderStatus.ORDER_STATUS_PENDING** indicates the order's state returned in a successful response. **Status.NOT_FOUND** is an error for the lookup call.

| Case | Data / status |
| --- | --- |
| Order found, pending | **GetOrderResponse.order.status = PENDING**, gRPC **OK** |
| Request missing order_id | No success response; gRPC **INVALID_ARGUMENT** |
| Order does not exist | No success response; gRPC **NOT_FOUND** |
| Caller not permitted | gRPC **PERMISSION_DENIED** |
| Server/connection temporarily unavailable | Typically gRPC **UNAVAILABLE** |
| Deadline expires before completion | Caller receives **DEADLINE_EXCEEDED** |

An HTTP/2 response with **:status 200** can still carry an error gRPC status. Obtain status from gRPC exceptions/callbacks and per-method metrics, not solely from HTTP status.

### 9.4. Interceptors for cross-cutting behavior

Interceptors are suitable for attaching/reading metadata, implementing authentication, collecting latency stats, tracing, and auditing at the **RPC level**. Authorization checks on a specific order object still belong in the server/business layer according to the application's permission model.

Interceptors do not have to appear in .proto files and do not operate on individual HTTP/2 frames. Similarly, a service definition does not enable TLS automatically: the Channel and gRPC server must be configured properly, along with proxies/LBs supporting HTTP/2 and ALPN when TLS is used.

## 10. Versioning and request/response compatibility

Messages are **shared contracts**. Changing how a field is interpreted can cause silent bugs even though the code compiles, especially when clients and servers deploy on different schedules.

### 10.1. Field numbers are identity on the wire

~~~proto
message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
}
~~~

To add **request_source**, you can normally use a new field number:

~~~proto
message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
  string request_source = 3;
}
~~~

Older clients usually ignore the unknown new field; newer clients receiving messages from older clients/servers see the corresponding default value. However, **wire compatibility** does not guarantee **semantic compatibility**: if the new server requires `request_source` to be non-empty, older clients will be rejected.

When removing a previously used field, never reuse its field number for a new meaning. Use **reserved** for old numbers and names:

~~~proto
message ArchivedOrder {
  reserved 3, 7;
  reserved "legacy_flag", "legacy_state";
  string id = 1;
  string customer_id = 2;
}
~~~

Reserving prevents the compiler from allowing reuse of those numbers/names; it does not automatically transform stored data.

### 10.2. Changes that need evaluation

| Change | Typical impact | Recommendation |
| --- | --- | --- |
| Add a new field, new number | Usually wire-compatible | Document defaults and fallbacks |
| Add an enum value | Wire format readable, but older clients do not know the value | Handle unknown/UNRECOGNIZED in APIs and do not assume all values are enumerated |
| Change a field number | Easily breaks existing data | Keep field numbers stable |
| Reuse a deleted field number | Risk of misinterpreting old data | Use **reserved** |
| Change a field type | May alter wire type/presence/range/semantics | Evaluate specific compatibility rules before applying |
| Rename protobuf package/service/method | Changes full RPC path | Treat as breaking for older clients |
| Change unary to streaming | Changes method descriptor and callback API | Treat as breaking; create a new method |
| Add an RPC method | Usually does not affect existing calls | Deploy/register before new clients call it |
| Change the meaning of data in an old field | Can break behavior even when wire is valid | Introduce a new field/version or a controlled migration |

**Example:** if **created_at_epoch_ms** was originally milliseconds and the server changes it to seconds while keeping the same field number and name, the wire type is still int64, yet clients will misinterpret the time. That is a semantic compatibility bug.

### 10.3. Designing API versions

Namespaces like **shop.orders.v1** distinguish contracts by version. If a change could break active clients, consider releasing **shop.orders.v2.OrderQueryService**, keeping v1 running during transition, and testing cross-version behavior. Directly renaming package v1 to v2 changes the RPC path; older clients will not automatically find the new endpoint.

The safe rollout pattern is usually: add new fields/endpoints first, deploy compatible servers, update clients, monitor legacy traffic, and only then retire deprecated APIs on a clear schedule.

## 11. Testing methods and messages with grpc-inprocess

Testing an implementation directly via plain Java method calls only covers part of the logic. To verify **generated stub → descriptor → gRPC runtime → registered implementation → response/status**, you can use the **in-process** transport.

The JUnit 5 example below uses **OrderQueryEndpoint** from section 7; it requires the **grpc-inprocess** dependency compatible with your grpc-java version, along with generated protobuf classes.

~~~java
package com.example.shop.server;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.shop.orders.v1.GetOrderRequest;
import com.example.shop.orders.v1.GetOrderResponse;
import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class OrderQueryEndpointTest {

    @Test
    void getOrderReturnsResponseAndValidatesRequest() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderQueryEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            OrderQueryServiceGrpc.OrderQueryServiceBlockingStub stub =
                    OrderQueryServiceGrpc.newBlockingStub(channel);

            GetOrderResponse result = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-42")
                            .build());

            assertEquals("order-42", result.getOrder().getId());

            StatusRuntimeException invalid = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.getOrder(
                            GetOrderRequest.newBuilder().build()));

            assertEquals(Status.Code.INVALID_ARGUMENT,
                    invalid.getStatus().getCode());

            StatusRuntimeException missing = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.getOrder(
                            GetOrderRequest.newBuilder()
                                    .setOrderId("order-404")
                                    .build()));

            assertEquals(Status.Code.NOT_FOUND,
                    missing.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

**directExecutor()** keeps tests simple since callbacks run inline; it is unsuitable for simulating complex blocking or concurrent workloads. In-process tests cover many parts of gRPC Java, yet **do not verify** TLS setup, HTTP/2 proxies, DNS, load balancing, or real network failures.

Add tests as needed for:

- **Serialization/compatibility**: client and server on two schema versions, testing new/old fields.
- **Method registration**: calling implemented and unimplemented methods to confirm proper statuses.
- **Validation/error**: empty ID, unauthorized, not found, and backend errors.
- **Deadline/cancellation**: slow backend or client cancel, verifying resources are released.
- **Streaming**: multiple messages, single termination, backpressure, and mid-stream connection drops.
- **Observability**: metrics/tracing should cleanly distinguish full method names and gRPC statuses.

## 12. Common design errors and troubleshooting

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| **UNIMPLEMENTED** when calling a method | Service/method name mismatch or server did not register/override handler | Compare full method name, proto version, registration |
| Caller thinks order_id is required, server sees empty | Proto3 does not enforce required strings automatically | Validate input on the server or apply explicit runtime validation |
| Client cannot distinguish "absent" from "empty" | Scalar field lacks presence | Use **optional**, **oneof**, or a field mask per use case |
| Server returns OK despite business error | Put error code in payload and still called onCompleted | Map real errors with appropriate gRPC statuses |
| Client sees HTTP 200 yet RPC fails | Reading only HTTP status | Inspect **grpc-status** and gRPC exceptions/callbacks |
| Changing field number causes misread data | Broke the wire-format contract | Restore old tag, reserve deleted tags, manage migration |
| Unary response too large | `repeated` field holds unbounded data | Paginate, bound size, or use server streaming |
| Client-streaming gets no result | Client did not half-close request observer | Call **onCompleted()** when done sending, wait for server terminal callback |
| Stream slow or consumes high memory | Slow consumer, unbounded queue, missing backpressure | Use appropriate isReady/onReady mechanisms, bound in-flight items |
| Deadline expires yet write still happened | Server committed before caller saw timeout | Design idempotency keys / reconciliation for write operations |
| Method works locally but fails behind reverse proxy | HTTP/2, TLS, ALPN, or routing misconfigured | Test real transport and inspect proxy settings |
| Repeated calls create too many connections | Creating a ManagedChannel per request | Share Channel and manage shutdown |

When investigating, isolate problems by layer: **contract** (package/method/message), **client** (stub/deadline/credentials), **transport** (HTTP/2/TLS), **server runtime** (registration/interceptors), and **implementation** (validation/business logic). Separating these helps locate the true cause rather than tweaking settings at random.

## 13. Hands-on lab and self-check questions

### Hands-on lab: extending the GetOrder RPC

1. From the .proto file in section 2, generate Java code with **protoc** and **protoc-gen-grpc-java**. Identify the request/response classes and method descriptor corresponding to **GetOrder**.
2. Start **OrderQueryEndpoint** on a gRPC server. Call **getOrder("order-42")** and check the order status in the response; test **order_id = ""** and **"order-404"**.
3. Add **optional string trace_label = 3;** to **GetOrderRequest**. Compare the getter with **hasTraceLabel()** in generated Java code, and explain the difference between not sending it and sending an empty string.
4. Design **SearchOrdersRequest/SearchOrdersResponse** with **page_size**, **page_token**, **repeated Order**, and **next_page_token**; enforce a `page_size` limit to prevent oversized responses.
5. Write an async client calling **WatchOrders**, receiving three events, and closing the observer cleanly. Then simulate mid-flight client cancellation and verify the server stops work.
6. Write an in-process test for GetOrder, then test with a real TLS/HTTP/2 server to verify transport and security settings.
7. Describe which changes require a new method or v2 package rather than modifying a schema still serving older clients directly.

### Self-check questions

**1. Does the Java package name determine the RPC's HTTP/2 :path?**  
No. The path is derived from **protobuf package + service + method**, such as **/shop.orders.v1.OrderQueryService/GetOrder**. **java_package** only decides where generated Java code is placed.

**2. Why must request/response use message types instead of raw string/int in the rpc signature?**  
gRPC contracts declare protobuf **messages** for both sides. Messages provide an evolvable schema, field numbers, and consistent encoding/decoding.

**3. How do unary and server streaming differ?**  
Unary has one request and one success response; server streaming has one request and can send multiple response messages within the same RPC.

**4. When using optional string note, what different questions do hasNote() and getNote() answer?**  
**hasNote()** tells whether the field was explicitly set; **getNote()** returns the value, which can be an empty string whether unset or explicitly set to empty.

**5. Is OrderStatus.PENDING a gRPC error code?**  
No. It is an enum value of business data. gRPC errors are represented by **Status.Code** such as **NOT_FOUND** or **INVALID_ARGUMENT**.

**6. When adding a field to a response, why must you still test with older clients?**  
Adding a new field with a new tag is usually wire-compatible, yet older client logic may not satisfy new business meanings or states. Testing uncovers semantic incompatibilities.

**7. In client-streaming, does calling onCompleted() on the request observer mean the RPC is complete?**  
No. The client has only finished its **send direction**; it must still wait for **onCompleted()** or **onError()** on the response observer to determine the final result.

## Summary

An **RPC method** is the unit of remote operation, identified by **protobuf package, service, and method name**. **Request/response messages** form the operation's data contract: consisting of field numbers, data types, and business semantics, encoded with Protocol Buffers. From those two parts, gRPC Java generates client/server APIs and the runtime transmits messages over HTTP/2. When building Spring gRPC services, properly design unary/streaming modes, validation and gRPC statuses, deadlines/security, schema compatibility, and test both the contract and operational behavior.
