# Service definition in Protocol Buffers

## Learning objectives

After this lesson, you can:

- Explain the role of a **service definition** in a gRPC contract and how it connects the client, server, and HTTP/2 runtime.
- Write a **.proto** file using **proto3** syntax, including **package**, **message**, **enum**, **service**, and **rpc** methods.
- Distinguish request/response types across the four call patterns: **unary**, **server streaming**, **client streaming**, and **bidirectional streaming**.
- Understand how **protoc** and the gRPC Java plugin generate **message classes**, **method descriptors**, **client stubs**, and the server base class.
- Design service names, field numbers, and contract versions so clients and servers can evolve safely.
- Connect the Protocol Buffers contract to implementation registration, stub invocation, status/deadline handling, testing, and operations in Spring.

## 1. Where does the service definition sit in gRPC architecture?

In **SPRING_GRPC**, the starting point is the **Protocol Buffers contract**. This contract describes which RPCs a service provides, the types of incoming and outgoing messages, and whether each side sends **one or many messages**. From there, code generation tools produce Java APIs for the client to call and the server to implement; the gRPC library transports messages over HTTP/2.

For example, an ordering system has an **OrderService** where the client calls **GetOrder** with an order ID and receives order data.

~~~mermaid
flowchart LR
    P["order_service.proto<br/>service + rpc + message"] --> G["protoc + gRPC Java plugin"]
    G --> C["Generated client stubs"]
    G --> S["Generated server base + descriptors"]
    C --> H["ManagedChannel / HTTP/2"]
    H --> R["gRPC server transport"]
    R --> I["Spring service implementation"]
    S --> I
~~~

Each block in the diagram has its own responsibility:

| Component | What does it define or do? |
| --- | --- |
| **.proto file** | Service name, method names, request/response types, streaming cardinality, data structure |
| **Generated code** | Java APIs, protobuf serializers/deserializers, and RPC method descriptors |
| **Client stub** | Packages Java calls into RPCs over a Channel |
| **Server runtime** | Receives HTTP/2, decodes requests, and routes to the registered handler |
| **Server implementation** | Executes business logic, returns responses or gRPC error codes |
| **Environment configuration** | Server address, TLS, deadlines, authentication, retries, load balancing, metrics |

**A service definition is an API contract**, not an implementation, a connection address declaration, or a security configuration. A **.proto** file does not start a server by itself: after generating code, the application must still create and register a service implementation to receive RPCs.

An HTTP/2 request typically carries a path of the form:

~~~text
/<protobuf-package>.<ServiceName>/<MethodName>
~~~

With package **orders.v1**, service **OrderService**, and method **GetOrder**, the full path is:

~~~text
/orders.v1.OrderService/GetOrder
~~~

This path is part of the RPC's identity on the network. It differs from the Java package name and the host/port URL that the client configures on the Channel.

## 2. Structure of a .proto file

Let's create **order_service.proto** with the following complete example:

~~~proto
syntax = "proto3";

package orders.v1;

option java_package = "com.example.orders.grpc.v1";
option java_multiple_files = true;
option java_outer_classname = "OrderProto";

service OrderService {
  // One request, one response.
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);

  // One request, a stream of responses.
  rpc ListOrders(ListOrdersRequest) returns (stream Order);

  // A stream of requests, one summary response.
  rpc UploadEvents(stream OrderEvent) returns (UploadSummary);

  // Bidirectional interleaved message exchange.
  rpc Synchronize(stream SyncRequest) returns (stream SyncResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  Order order = 1;
}

message ListOrdersRequest {
  string customer_id = 1;
}

message Order {
  string id = 1;
  string customer_id = 2;
  OrderState state = 3;
  int64 created_at_epoch_ms = 4;
}

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_COMPLETED = 2;
}

message OrderEvent {
  string order_id = 1;
  string event_type = 2;
}

message UploadSummary {
  int32 accepted_count = 1;
}

message SyncRequest {
  string cursor = 1;
}

message SyncResponse {
  string cursor = 1;
  Order order = 2;
}
~~~

This is an example contract for learning. Fields such as **cursor**, **event_type**, and **created_at_epoch_ms** must have their semantics clearly defined in real product API documentation; proto syntax only defines field types and identities.

### 2.1. Explaining each part

| Part | Effect |
| --- | --- |
| **syntax = "proto3"** | Selects Protocol Buffers syntax version proto3 |
| **package orders.v1** | Identifies the protobuf namespace; contributes to the full service name on the protocol |
| **java_package** | Sets the package for generated Java classes |
| **java_multiple_files = true** | Generates top-level Java classes for messages, enums, and service-related classes rather than nesting them all in one outer class |
| **java_outer_classname** | Names the outer class used for Java code elements that belong in it, such as the file descriptor |
| **service OrderService** | Declares a group of RPC methods |
| **rpc GetOrder(...) returns (...)** | Declares the method name and request/response message types |
| **stream** | Indicates a direction capable of transmitting multiple messages within one RPC |
| **message** | Declares an exchanged data type |
| **enum** | Declares an integer-encoded set of values |
| **= 1, = 2, ...** | Data *field numbers* used in the protobuf binary format |

Do not confuse protobuf **package** with **java_package**:

- **package orders.v1** determines the full service name **orders.v1.OrderService** and the protobuf names in descriptors.
- **java_package com.example.orders.grpc.v1** determines where the generated Java classes live.
- Changing **java_package** may require updating Java imports even though the RPC name at the network layer does not change.
- Changing the protobuf **package** changes the full service name and RPC path, which can break older clients if the server no longer registers the old name.

The filename **order_service.proto** helps organize source code, but the RPC path does not come from the filename. For gRPC, method identity comes from **package + service + method**.

### 2.2. Declaring messages and field numbers

Inside a **message**, each field has a **type**, a **name**, and a **unique number**:

~~~proto
message GetOrderRequest {
  string order_id = 1;
}
~~~

In the Protocol Buffers wire format, the **field number** is part of the encoding key. The receiver uses the field number and wire type to decode; field names mainly serve source code, tooling, and formats such as ProtoJSON.

Some common types:

| Proto type | Meaning | Notes |
| --- | --- | --- |
| **string** | UTF-8 string | Proto3 usually returns an empty string when absent |
| **int32 / int64** | Signed integer | Consider size/range and Java conversion |
| **bool** | Boolean true/false | Default value is false |
| **bytes** | Binary data | Suitable for binary payloads needing explicit formatting |
| **enum** | Predefined status/state code | Should declare value 0 meaning "UNSPECIFIED"/"UNKNOWN" |
| **MessageType** | A nested message | Has message-field presence semantics |
| **repeated T** | List of multiple elements | Empty list if no elements |
| **map<K, V>** | Key-value table | Key types restricted by protobuf; do not rely on as business ordering |

In proto3, **ordinary scalar fields** like string, int32, and bool do not directly distinguish "not sent" from "sent with the default value" via basic accessors. When you need to know whether a scalar was explicitly set, consider **optional**:

~~~proto
message UpdateOrderRequest {
  string order_id = 1;
  optional string note = 2;
}
~~~

In Java code generated from proto3 with optional support, the application can check **hasNote()** to distinguish "do not update note" from "update note to an empty string". Never assume 0 or an empty string always means "not provided".

When data can belong to only **one of several mutually exclusive types**, use **oneof**:

~~~proto
message LookupOrderRequest {
  oneof key {
    string order_id = 1;
    string external_reference = 2;
  }
}
~~~

**oneof** models mutual exclusion at the data layer. It does not replace validation, authorization, or business constraints in the implementation.

## 3. From rpc syntax to the four communication patterns

The general form of a method in a service is:

~~~proto
rpc MethodName(RequestType) returns (ResponseType);
~~~

Add **stream** on the request or response side to indicate a direction sending multiple messages:

| RPC type | .proto declaration | Logical request/response count | Example |
| --- | --- | --- | --- |
| **Unary** | **rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);** | 1 request, 1 response | Fetch a single order by ID |
| **Server streaming** | **rpc ListOrders(ListOrdersRequest) returns (stream Order);** | 1 request, 0..n responses | Emit a list of orders message by message |
| **Client streaming** | **rpc UploadEvents(stream OrderEvent) returns (UploadSummary);** | 0..n requests, 1 response | Client sends events, server returns summary stats |
| **Bidirectional streaming** | **rpc Synchronize(stream SyncRequest) returns (stream SyncResponse);** | 0..n requests, 0..n responses | Synchronize progress between two systems |

**stream** is a contract keyword, not the name of an HTTP/2 connection. Each gRPC call uses **one HTTP/2 stream**, which can contain multiple gRPC messages. If a method sends 200 records from the server, it is still **one RPC** over **one HTTP/2 stream**, not 200 independent RPCs.

### 3.1. Choosing the RPC type by need

**Unary** fits short requests with bounded results: reading data, writing a single change, validating an action. It is easy to test and straightforward in synchronous workflows.

**Server streaming** fits when one request produces results emitted incrementally, such as large datasets, continuous updates, or long-running progress. The client must handle multiple **onNext** calls, backpressure, and cancellation.

**Client streaming** fits chunked uploads or batching multiple records; the client closes its **send direction** after the last message and waits for an aggregate response. The server must limit record counts, payload sizes, and processing time.

**Bidirectional streaming** fits continuous two-way interaction. Both sides can emit messages independently and interleaved; do not assume every request immediately produces exactly one response.

**Note on return types:** gRPC requires every method to have an explicitly declared request type and response type. If no payload is needed, you can use **google.protobuf.Empty**:

~~~proto
import "google/protobuf/empty.proto";

service HealthControl {
  rpc ResetCache(google.protobuf.Empty) returns (google.protobuf.Empty);
}
~~~

Use Empty according to API semantics; for important operations, an explicit response with business status and version is often more useful.

### 3.2. A definition does not capture the entire application protocol

For **Synchronize**, the proto only states there are multiple **SyncRequest** and **SyncResponse** messages. It does not specify:

- Whether each response corresponds to a single request.
- Whether messages must follow a strict order, or have checkpoints or retries.
- Exactly how **cursor** acts as a bookmark.
- Termination conditions, message limits, and how client cancellation is handled.

These rules must be documented and implemented consistently. For long-lived streaming, application-level protocol design often needs **start/data/ack/end** message types, or **oneof** with enums to represent states, rather than relying solely on `stream` in the rpc signature.

## 4. What does code generation produce?

After defining the contract, the code generation pipeline usually has two parts:

1. **protoc + Java protobuf generator** generates **message/enum** classes, builders, parsers, and file descriptors.
2. **protoc-gen-grpc-java** generates gRPC support classes, method descriptors, stubs, and server base classes.

For example, with **java_multiple_files = true** in section 2, notable Java classes typically include:

| Generated artifact | Role |
| --- | --- |
| **GetOrderRequest**, **GetOrderResponse**, **Order** | Protobuf data and builder/accessor APIs |
| **OrderState** | Java enum corresponding to the protobuf enum |
| **OrderProto** | File-level descriptor and supporting metadata |
| **OrderServiceGrpc** | Service descriptor, method descriptors, stub factories |
| **OrderServiceGrpc.OrderServiceImplBase** | Base class for the server to override methods |
| **OrderServiceGrpc.OrderServiceBlockingStub** | Blocking API, commonly used for unary/server streaming |
| **OrderServiceGrpc.OrderServiceStub** | Async API, usable for all RPC patterns |
| **OrderServiceGrpc.OrderServiceFutureStub** | Future API, mainly for unary |

**Never edit generated code directly.** When changing a service definition, edit the **.proto** file, rerun code generation, and update affected implementations/callers.

### 4.1. Commonly seen Java signatures

Example server-side methods when using the traditional gRPC Java base API:

~~~java
@Override
public void getOrder(
        GetOrderRequest request,
        StreamObserver<GetOrderResponse> responseObserver) {
    // unary
}

@Override
public void listOrders(
        ListOrdersRequest request,
        StreamObserver<Order> responseObserver) {
    // server streaming
}

@Override
public StreamObserver<OrderEvent> uploadEvents(
        StreamObserver<UploadSummary> responseObserver) {
    // client streaming
    // Return an observer that receives each OrderEvent.
}

@Override
public StreamObserver<SyncRequest> synchronize(
        StreamObserver<SyncResponse> responseObserver) {
    // bidirectional streaming
}
~~~

These are **signature illustrations** to highlight the differences; methods without bodies will need full implementations in a real server class. Types are imported from the chosen generated Java package, and **StreamObserver** belongs to **io.grpc.stub.StreamObserver**.

On the client side:

- **BlockingStub.getOrder(request)** returns **GetOrderResponse** or throws **StatusRuntimeException**.
- **BlockingStub.listOrders(request)** typically returns **Iterator<Order>**.
- **AsyncStub.uploadEvents(responseObserver)** returns **StreamObserver<OrderEvent>** so the client can send multiple requests.
- **AsyncStub.synchronize(responseObserver)** returns **StreamObserver<SyncRequest>** for two-way exchange.

The calling API directly mirrors the **stream** keyword on each side in the .proto file. Some generator versions or configurations may provide additional APIs, but the mapping principle remains the same.

### 4.2. Service descriptor and RPC routing

A gRPC service is not routed by an arbitrary Java method name. The runtime relies on service and method descriptors, for example:

~~~java
String fullServiceName =
        OrderServiceGrpc.getServiceDescriptor().getName();
// "orders.v1.OrderService"

String fullMethodName =
        OrderServiceGrpc.getGetOrderMethod().getFullMethodName();
// "orders.v1.OrderService/GetOrder"
~~~

Upon receiving a request, the server routes **/orders.v1.OrderService/GetOrder** to the handler registered for that method. The descriptor supplies the name, request/response types, RPC type, and required marshallers; attaching processing logic is the implementation's job.

Across the tooling ecosystem, descriptors are also used for contract testing, server reflection if enabled, and dynamic clients. **Reflection** is not enabled automatically just because descriptors were generated; the server must register/use an appropriate reflection mechanism.

## 5. Integrating the contract with a Spring server

Suppose the server needs to support unary **GetOrder**. A Spring bean class can extend the generated gRPC API:

~~~java
package com.example.orders.server;

import com.example.orders.grpc.v1.GetOrderRequest;
import com.example.orders.grpc.v1.GetOrderResponse;
import com.example.orders.grpc.v1.Order;
import com.example.orders.grpc.v1.OrderServiceGrpc;
import com.example.orders.grpc.v1.OrderState;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class OrderGrpcEndpoint extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        String id = request.getOrderId().trim();
        if (id.isEmpty()) {
            responseObserver.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("order_id must not be empty")
                            .asRuntimeException());
            return;
        }

        // Sample data; real implementations fetch from the business/repository layer.
        Order order = Order.newBuilder()
                .setId(id)
                .setCustomerId("customer-100")
                .setState(OrderState.ORDER_STATE_PENDING)
                .setCreatedAtEpochMs(1_700_000_000_000L)
                .build();

        responseObserver.onNext(
                GetOrderResponse.newBuilder().setOrder(order).build());
        responseObserver.onCompleted();
    }
}
~~~

The **getOrder** signature must match the generated method: **GetOrderRequest** in, **StreamObserver<GetOrderResponse>** out. Call **onNext** to emit the response, then **onCompleted** to end successfully. If the request is invalid, call **onError** with an appropriate gRPC status code and stop processing. Never call **onCompleted** after **onError** or emit more messages after a terminal event.

A service definition may contain four methods, which does not mean the illustrative implementation above completes all of them: un-overridden methods use the base class's default behavior, typically returning **UNIMPLEMENTED** when called. Therefore, verify every actually required RPC before exposing the service.

### 5.1. Registering the service with the runtime

When using the basic grpc-java API in Spring:

~~~java
package com.example.orders.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfiguration {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server orderGrpcServer(OrderGrpcEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(endpoint)
                .build();
    }
}
~~~

This is an example of **Spring-managed grpc-java beans**, separate from the auto-configuration mechanism of a Spring gRPC starter. If the framework in use auto-registers service beans and manages the server, follow that mechanism instead of creating an extra server on the same port.

**@Component** lets Spring manage the implementation instance, whereas **addService(endpoint)** tells the gRPC server which methods are being exposed. These two steps serve two different layers.

## 6. Client using stubs from the generated contract

The client application can create a shared **ManagedChannel** and build a blocking stub from that Channel:

~~~java
package com.example.orders.client;

import com.example.orders.grpc.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        // For local testing only.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderBlockingStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

The Spring service calls **GetOrder** as follows:

~~~java
package com.example.orders.client;

import com.example.orders.grpc.v1.GetOrderRequest;
import com.example.orders.grpc.v1.GetOrderResponse;
import com.example.orders.grpc.v1.OrderServiceGrpc;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderLookupClient(
            OrderServiceGrpc.OrderServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetOrderResponse getOrder(String id) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(id)
                .build();

        try {
            return stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getOrder(request);
        } catch (StatusRuntimeException error) {
            // The application layer maps the status by use case and retry policy.
            throw new IllegalStateException(
                    "GetOrder error: " + error.getStatus().getCode(),
                    error);
        }
    }
}
~~~

What the .proto file determines here are: the **getOrder** method, the **GetOrderRequest** type, and the **GetOrderResponse** type. The address **localhost:9090**, the **2-second** deadline, TLS, and exception handling are client/runtime-layer decisions. **withDeadlineAfter** produces a stub with new call options; configure deadlines close to the time of the call.

The example uses **usePlaintext()** to simplify local runs. In production, configure TLS, certificates/trust, and appropriate authentication. Reuse the Channel rather than creating a new Channel per call to avoid unnecessary connections.

## 7. Designing service definitions for long-term evolution

A stable service definition should be treated as a **public API for active clients**. When multiple teams deploy clients and servers independently, uncontrolled schema changes can cause compile-time or runtime failures.

### 7.1. Naming conventions

- Use a service name reflecting a business capability, such as **OrderService** rather than **GlobalService**.
- Start RPC names with clear action verbs, such as **GetOrder**, **ListOrders**, **CreateOrder**; stay consistent within an API.
- Use **snake_case** for field names, **PascalCase** for messages/services, and **UPPER_SNAKE_CASE** for enum values.
- Use versioned packages like **orders.v1** when managing major changes. Do not arbitrarily change package names once clients exist.
- Avoid naming messages merely **Request** or **Result**, which easily collide and hurt readability; **GetOrderRequest** provides clearer context.
- Document fields with special business rules, formats, or bounds: time units, cursor scope, idempotency, empty/null semantics.

Naming rules are API design conventions for maintainability; they should be agreed upon within the project. They are not hard requirements of the protobuf compiler.

### 7.2. Compatibility when modifying messages

Consider the initial **Order** message:

~~~proto
message Order {
  string id = 1;
  string customer_id = 2;
  OrderState state = 3;
  int64 created_at_epoch_ms = 4;
}
~~~

To add descriptive information, the generally compatible approach is **adding a new field with a new field number**:

~~~proto
message Order {
  string id = 1;
  string customer_id = 2;
  OrderState state = 3;
  int64 created_at_epoch_ms = 4;
  optional string description = 5;
}
~~~

Older clients usually ignore unknown field **5**; newer clients can still read messages from older servers, where **description** is simply absent. However, **wire compatibility does not automatically guarantee semantic compatibility**: if business rules require `description` to always have a value, older clients/servers may fail to satisfy the new requirement.

**Never reuse a published field number** for a different meaning. When removing a field, use **reserved** to prevent accidental reuse:

~~~proto
message OrderPatch {
  reserved 2, 5;
  reserved "legacy_note", "old_status";

  string order_id = 1;
  optional string description = 3;
  optional int64 expected_version = 4;
}
~~~

**reserved** does not strip old data from stored messages or perform migrations; it makes the compiler reject redefining reserved numbers/names.

Decision table when changing schemas:

| Change | Typical assessment | Reason |
| --- | --- | --- |
| Add a field with an unused number | Usually wire-compatible | Older clients can ignore unknown fields |
| Remove a field and mark reserved | Can preserve wire compatibility; check logic | Older clients may still send/read the old field as default or have it ignored |
| Change the number of a field in use | **Breaking** | Receiver decodes it as a different field or skips it |
| Reuse an old number for a new meaning | **Dangerous/breaking** | Old data can be misinterpreted |
| Change a field type | Must check specific compatibility rules; treat as risky by default | Wire type, range, presence, or data meaning may change |
| Rename protobuf package/service/method | **Breaking for existing RPC paths** | Full method name is used for routing |
| Change unary to streaming or vice versa | **Breaking** | API signatures and interaction protocol change |
| Add a new RPC | Usually non-breaking for existing RPCs | Older clients do not have to call the new method |
| Add an enum value | Usually wire-compatible; must handle unknown values | Older clients may not recognize the new value |

For proto3 enums, keep an **UNSPECIFIED = 0** value. Consumers should have a branch handling unknown values rather than assuming every server only emits enum values present in the client's current version.

### 7.3. When should you create v2?

When making breaking changes — such as redefining what **Order** means, changing RPC types, or reorganizing the entire service — you can design **orders.v2.OrderService** and keep the v1 API running during the transition period.

~~~proto
syntax = "proto3";

package orders.v2;

service OrderService {
  rpc FetchOrder(FetchOrderRequest) returns (FetchOrderResponse);
}

message FetchOrderRequest {
  string id = 1;
}

message FetchOrderResponse {
  string id = 1;
  string display_name = 2;
}
~~~

This is an example of a **different contract**, not a direct rename of v1. Clients using v1 will still call **/orders.v1.OrderService/GetOrder**; while still supported, the server must continue registering the v1 service or implement a suitable adapter. Do not simply change the package and expect old clients to automatically discover the new method.

## 8. What a service definition does not solve by itself

The .proto file is the source of truth for API and data contracts. Yet to operate reliably, an application needs many other decisions:

| Need | Declared directly in the service definition? | Common implementation approach |
| --- | --- | --- |
| **Metadata/correlation ID** | Not a mandatory part of the rpc signature | Send metadata via headers, use client/server interceptors |
| **Authentication/authorization** | Not enforced automatically by proto | TLS/mTLS, credentials, interceptors, and server policies |
| **Deadline** | Not fixed by the method signature | Client sets deadline; server observes cancellation/deadline |
| **gRPC status** | Not a separately declared response message | Handler returns errors with **Status** and runtime sends **grpc-status** |
| **Retry and idempotency** | Not guaranteed by contract syntax | Client policy and operation/idempotency-key design |
| **Load balancing/discovery** | Not inside the .proto file | ManagedChannel, name resolver, and load balancer |
| **Flow control/backpressure** | `stream` keyword only indicates data direction | HTTP/2 transport together with rate-controlling streaming logic |
| **Monitoring/tracing** | Not configured in message definitions | Metrics, tracing, and interceptors |
| **Actual endpoint registration** | No | gRPC server must register BindableService/implementation |

You can add custom **protobuf options** to describe API policies, but merely adding annotations/options in the schema **does not automatically activate** authentication, routing, or retries. Tooling and runtime support must understand and enforce those options.

### 8.1. Designing errors and deadlines around method semantics

For example, **GetOrder** may have outcomes such as:

- Success: return **GetOrderResponse** with **order**.
- Invalid input: return **INVALID_ARGUMENT**.
- Order not found: return **NOT_FOUND**.
- Client lacks permission: return **PERMISSION_DENIED**.
- Backend temporarily unavailable: return **UNAVAILABLE**.
- Timed out: caller may receive **DEADLINE_EXCEEDED**.

gRPC status usually arrives in **trailers**, while HTTP status may still be **200**. Clients must handle **StatusRuntimeException** or the **onError** callback rather than just reading the protobuf payload.

If an RPC creates or updates data, retrying after **DEADLINE_EXCEEDED** can execute the operation twice because the server might have processed it successfully before the response reached the client. When designing a service, document **idempotency** clearly or provide a request identifier/idempotency key when required by business logic.

## 9. Workflow and contract verification

A sound practical workflow:

1. **Design the .proto.** Agree on versioned package, method names, request/response messages, and streaming directions. Identify fields needing presence/oneof.
2. **Review the contract.** Check field numbers, data types, field semantics, backward compatibility, and behaviors not captured by syntax alone.
3. **Run code generation.** Use **protoc** and the gRPC Java codegen plugin in the build to generate message classes, descriptors, and stubs; keep tool versions compatible.
4. **Implement the server.** Override supported methods, attach business logic and Status codes; register the service with the gRPC runtime.
5. **Implement the client.** Create/reuse ManagedChannel, pick the appropriate stub, configure deadlines/TLS, and handle errors.
6. **Test.** Verify serialization, request/response handling, error statuses, streaming modes, and compatibility across different client/server versions.
7. **Observe at runtime.** Monitor method names, latency, status codes, in-flight RPCs, deadlines, and error rates; trace across client/server to isolate where delays originate.

### 9.1. Illustrating the Java codegen step

Assuming **protoc**, the standard Java plugin, and **protoc-gen-grpc-java** are installed, a conceptual invocation is:

~~~text
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  --grpc-java_out=build/generated/source/proto/main/grpc \
  src/main/proto/order_service.proto
~~~

Output paths depend on build configuration, and **protoc-gen-grpc-java** must be on PATH or explicitly declared. In Java/Spring projects, you normally configure a Maven/Gradle plugin to generate code automatically during build; **do not manually copy generated code** into developer-maintained source directories.

A contract is only truly active once both client and server build against compatible generated APIs; having a .proto file on disk does not automatically make the runtime aware of the service.

### 9.2. Testing over an in-process transport

You can verify registration and a unary RPC without opening a network port using **grpc-inprocess**. Illustrative JUnit 5 snippet using **OrderGrpcEndpoint** from section 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.orders.grpc.v1.GetOrderRequest;
import com.example.orders.grpc.v1.GetOrderResponse;
import com.example.orders.grpc.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class OrderContractTest {

    @Test
    void generatedStubCallsRegisteredMethod() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderGrpcEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(channel);

            GetOrderResponse result = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-123")
                            .build());

            assertEquals("order-123", result.getOrder().getId());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

In-process testing requires **grpc-inprocess** and test libraries compatible with the grpc-java version in use. It verifies generated APIs, method registration, serialization, and statuses through the gRPC runtime. It **does not** replace testing TLS, ALPN, HTTP/2 proxies, DNS, or load balancing over a real network. **directExecutor()** should only be used for small tests and does not faithfully simulate systems with blocking or concurrent callbacks.

### 9.3. Inspecting service discovery with reflection

When the server enables **gRPC Server Reflection** and the environment permits, tools like **grpcurl** can list services/methods or make test calls without building a full Java client:

~~~text
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe orders.v1.OrderService
grpcurl -plaintext -d '{"orderId":"order-123"}' \
  localhost:9090 orders.v1.OrderService/GetOrder
~~~

These commands **only work if reflection is registered on the server**; the simple server example in section 5 does not enable reflection automatically. The commands use **-plaintext** for local environments, not as a production default. JSON passed to grpcurl typically uses ProtoJSON field names (**orderId**) rather than the proto source name **order_id**, though parsers may accept both depending on the tool.

If reflection is not enabled, you can still test using local descriptor/proto files or generated clients, depending on the capabilities of your tooling.

## 10. Common mistakes when writing service definitions

| Symptom | Likely cause | How to verify/fix |
| --- | --- | --- |
| Client reports **UNIMPLEMENTED** | Server did not register service/method, implementation did not override, or client/server contracts differ | Check method descriptor, package, service name, handler registration, and RPC path |
| Java imports cannot find generated classes | Code generation has not run, output not added to source set, wrong **java_package** | Check generator config and generated package |
| Old clients can no longer call after a rename | Changing protobuf package/service/method changed the full RPC path | Keep the old API or release v2 with a migration path |
| Data decoded incorrectly after schema edit | Changed/reused field number, changed type without assessment | Restore stable field numbers, use reserved when deleting |
| Cannot tell whether a scalar field was sent | Relying on proto3 default values | Use **optional** or an appropriate message/oneof type |
| Streaming returns missing messages | Handler invoked terminal callback early or lacked backpressure management | Review onNext/onCompleted logic, cancellation, limits, and flow control |
| Client times out even though method exists in proto | Deadline too short, slow backend, or network failure | Monitor per-method latency, deadlines, logs/traces, and statuses |
| Schema upgrade still fails at runtime | Only one side regenerated or deployment compatibility untested | Build/test multiple client-server versions and roll out in stages |
| Auth metadata missing from request message | Metadata is an RPC-header concept, not a required message field | Configure credentials/interceptors and server authorization |

A successful protobuf compiler run only confirms **syntax and certain schema constraints**. It does not prove that the service is registered, the caller is authorized, the contract is semantically backward-compatible, or the whole system works over HTTP/2/TLS.

## 11. Hands-on lab and self-check questions

### Hands-on lab: safely extending OrderService

Start from **order_service.proto** in section 2 and try these steps:

1. Add **optional string note = 5;** to **Order**. Regenerate Java code and identify the corresponding presence-check method. Explain what an older client will do when a newer server returns this field.
2. Add a unary RPC **CancelOrder(CancelOrderRequest) returns (CancelOrderResponse)**. Design the request with **order_id** and **expected_version**; list the statuses that can be returned when the order is not found or already completed.
3. Add a **WatchOrder** method returning **stream Order**. Contrast its semantics with **GetOrder**: multiple messages, completion points, cancellation, and connection limits.
4. Create a Spring implementation for a new method, register it on the gRPC server, and test with the generated stub. If testing with grpcurl, explicitly enable reflection or supply the local schema.
5. Simulate an old client and new server. Evaluate message readability when adding a field, then try changing the protobuf **package** on a separate branch to observe the change in RPC path.

### Self-check questions

**1. Why doesn't a service definition need to specify a server address or port?**

Because the contract describes the **logical API**, while where to connect and how to transport calls are decided by **ManagedChannel/runtime/configuration**. One contract can be deployed across many addresses and environments.

**2. In proto, what does the stream keyword before ResponseType mean?**

The server can send multiple response messages within **one RPC**. It does not mean opening a new HTTP/2 connection for each response.

**3. How do protobuf package and java_package differ?**

**package** contributes to identifying the service/method in the gRPC wire protocol; **java_package** sets the package of the generated Java code. Changing the protobuf package can change the RPC path.

**4. Can you change field number 3 to 7 just to tidy up the schema?**

No. The **field number** is the field's identity in the protobuf wire format. Changing field numbers risks breaking compatibility; when removing an old field, use **reserved**.

**5. Why does the server return HTTP 200 yet the client still receives StatusRuntimeException?**

gRPC transmits the RPC status separately, typically in **grpc-status** inside trailers. HTTP 200 does not guarantee the RPC business operation succeeded.

**6. When .proto already declares GetOrder, why can the client still receive UNIMPLEMENTED?**

Because the server runtime may not have registered the service properly or the method is not yet supported by the implementation. **Declaring the API** and **implementing/registering the handler** are two separate steps.

## Summary

A **service definition in Protocol Buffers** is the contract source for gRPC in Spring: it specifies **service names, RPC names, request/response messages, and streaming directions**. From this contract, **protoc** and the gRPC Java plugin generate data classes, descriptors, stubs, and base APIs for the server to implement. Good design keeps published field numbers and RPC names stable, versions contracts clearly, separates schema from runtime configuration, and tests compatibility between client and server. This is the foundation for developing maintainable, operable, and safely extensible unary and streaming RPCs.
