# Defining the Proto for an Order Management Service

In a Spring gRPC project, a Protocol Buffers contract needs to clearly describe the operations a client is allowed to perform, the data exchanged, and the rules the server must enforce. This hands-on lesson designs a contract for an order management service: creating an order, reading an order, listing orders with pagination, updating notes, cancelling an order, and watching events for an order.

The goal is not merely to write a `.proto` file that can generate Java code. The contract must keep field numbers stable, represent presence properly, prevent clients from dictating server-owned data like prices, support safe retries for order creation, and clearly define streaming semantics. After this lesson, you can use the schema as input to generate gRPC stubs and implement the provider/client in Spring.

## 1. Defining Scope and Use Cases

The service manages the order lifecycle with the following use cases:

| Use case | RPC | RPC Type |
| --- | --- | --- |
| Create an order from a list of products | CreateOrder | Unary |
| Retrieve details of a single order | GetOrder | Unary |
| List a customer's orders | ListOrders | Unary with pagination |
| Edit an order's note | UpdateOrder | Unary |
| Cancel an order while eligible | CancelOrder | Unary |
| Watch changes for a single order | WatchOrderEvents | Server streaming |

Choose unary for operations that take a single request and return a finite result. ListOrders uses a page token so the client controls each page; streaming the entire history is unnecessary because pagination bounds memory usage and supports resumable queries. WatchOrderEvents uses server streaming because a client can subscribe to receive multiple events over a period of time.

A few business rules must be agreed upon before writing the proto:

- A new order is created by the server in the PENDING state.
- The client sends the product ID and quantity; the server looks up the product name, price, and status at order creation time.
- Every item in a single order must use the same currency.
- Quantity must be greater than 0; the server checks inventory and customer permissions.
- An order can only be cancelled when its current state permits cancellation.
- Each order change emits an event with a monotonically increasing sequence number scoped to the order.
- CreateOrder accepts an idempotency key so retries do not create duplicate orders.

These rules form the behavior contract. The proto defines the structure and RPC shape; the server must still validate and enforce these rules.

## 2. Choosing the Package and Java Options

Use a versioned package to establish a stable namespace:

- Protobuf package: `shop.order.v1`.
- Java package: `com.myshop.order.v1`.
- File: `src/main/proto/shop/order/v1/order_service.proto`.
- Service: `OrderService`.

`v1` is the version of the public contract, not the application build version. When breaking changes cannot remain backwards-compatible, a new package/service version such as `shop.order.v2` can be created while maintaining v1 during the transition period.

The messages use `google.protobuf.Timestamp` for timestamps and `google.protobuf.FieldMask` for partial updates. These are well-known types bundled with Protocol Buffers.

## 3. Defining the order_service.proto File

Create the file `src/main/proto/shop/order/v1/order_service.proto` with the following content:

```proto
syntax = "proto3";

package shop.order.v1;

option java_multiple_files = true;
option java_package = "com.myshop.order.v1";
option java_outer_classname = "OrderServiceProto";

import "google/protobuf/field_mask.proto";
import "google/protobuf/timestamp.proto";

service OrderService {
  // Creates an order. The idempotency key makes retries safe.
  rpc CreateOrder(CreateOrderRequest) returns (Order);

  // Returns one order visible to the authenticated caller.
  rpc GetOrder(GetOrderRequest) returns (Order);

  // Lists orders using an opaque page token.
  rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);

  // Updates only the fields named in update_mask.
  rpc UpdateOrder(UpdateOrderRequest) returns (Order);

  // Cancels an order if its current state allows cancellation.
  rpc CancelOrder(CancelOrderRequest) returns (Order);

  // Streams events whose sequence is greater than after_sequence.
  rpc WatchOrderEvents(WatchOrderEventsRequest)
      returns (stream OrderEvent);
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_SHIPPED = 3;
  ORDER_STATUS_DELIVERED = 4;
  ORDER_STATUS_CANCELLED = 5;
}

enum OrderEventType {
  ORDER_EVENT_TYPE_UNSPECIFIED = 0;
  ORDER_EVENT_TYPE_CREATED = 1;
  ORDER_EVENT_TYPE_UPDATED = 2;
  ORDER_EVENT_TYPE_CANCELLED = 3;
}

message OrderItemInput {
  string product_id = 1;
  int32 quantity = 2;
}

message OrderItem {
  string product_id = 1;
  string product_name = 2;
  int32 quantity = 3;
  int64 unit_price_minor = 4;
  string currency_code = 5;
}

message Order {
  string order_id = 1;
  string customer_id = 2;
  repeated OrderItem items = 3;
  OrderStatus status = 4;
  int64 total_amount_minor = 5;
  string currency_code = 6;
  google.protobuf.Timestamp created_at = 7;
  google.protobuf.Timestamp updated_at = 8;
  optional string note = 9;
  int64 version = 10;
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderItemInput items = 2;
  optional string note = 3;
  string idempotency_key = 4;
}

message GetOrderRequest {
  string order_id = 1;
}

message ListOrdersRequest {
  string customer_id = 1;
  optional OrderStatus status = 2;
  int32 page_size = 3;
  string page_token = 4;
}

message ListOrdersResponse {
  repeated Order orders = 1;
  string next_page_token = 2;
}

message OrderPatch {
  optional string note = 1;
}

message UpdateOrderRequest {
  string order_id = 1;
  OrderPatch patch = 2;
  google.protobuf.FieldMask update_mask = 3;
  int64 expected_version = 4;
}

message CancelOrderRequest {
  string order_id = 1;
  string reason = 2;
  int64 expected_version = 3;
}

message WatchOrderEventsRequest {
  string order_id = 1;
  int64 after_sequence = 2;
}

message OrderEvent {
  string event_id = 1;
  string order_id = 2;
  int64 sequence = 3;
  OrderEventType event_type = 4;
  google.protobuf.Timestamp occurred_at = 5;

  oneof detail {
    Order order_snapshot = 6;
    string cancellation_reason = 7;
  }
}
```

This is an intentionally scoped v1 contract. It provides the core operations for practicing generated Java APIs, unary calls, pagination, and server streaming. Features such as payments, refunds, administrative authorization, or multi-criteria search can be added later once their use cases are clear.

## 4. Designing Requests and Responses Around Data Ownership

CreateOrderRequest only accepts the product ID and quantity. The client must not send a product name or unit price for the server to write directly onto the order, because price and name must be resolved from a trusted catalog at order creation time. The server stores a price snapshot in OrderItem so order history remains unchanged when catalog prices are updated.

Order uses integer `unit_price_minor` and `total_amount_minor`, avoiding binary floating-point rounding errors when calculating money. `currency_code` specifies the currency; the service contract must define how major/minor units convert per currency and ensure all items in an order share the same currency. Never sum amounts across different currencies.

`Order.version` is a version counter incremented after every update. UpdateOrderRequest and CancelOrderRequest send `expected_version`; the server rejects the write if the current version has changed. This detects lost updates when multiple clients modify the same order concurrently.

`created_at`, `updated_at`, and `occurred_at` use UTC Timestamp instead of custom-formatted date-time strings. Clients should convert them to the appropriate time type in their language and avoid assuming the server's local timezone.

## 5. Presence and Validation Decisions

Standard proto3 scalars have implicit presence: if a client omits a string, the getter returns an empty string; if it omits an int32, the getter returns 0. For fields where absent must be distinguished from an explicit default, declare `optional`.

In this schema:

- `Order.note` is optional so clients can distinguish an order with no note from one where a note is present.
- `CreateOrderRequest.note` is optional to know whether the caller sent a note.
- `ListOrdersRequest.status` is optional to distinguish no status filtering from filtering by a specific enum value.
- `OrderPatch.note` is optional to support setting or clearing via the update mask.

Proto3 has no required keyword. The server must validate:
- customer_id and idempotency_key must not be empty.
- items must contain at least one element and not exceed the maximum item limit.
- product_id must not be empty, and quantity must be greater than 0.
- page_size must be within bounds, e.g., 1–100. If 0, the server can apply a documented default.
- order_id must have a valid format and the caller must have access to the order.
- expected_version must match the current version.

Invalid requests should terminate with INVALID_ARGUMENT. An order not found returns NOT_FOUND; an unauthorized caller returns PERMISSION_DENIED. Ineligibility for cancellation returns FAILED_PRECONDITION; an expected_version conflict can return ABORTED. These statuses are part of the behavior contract and should be tested explicitly.

## 6. Defining Semantics for Each RPC

**CreateOrder**

The server authenticates the customer, validates each product, inventory, currency, and quantity, then computes the total from the catalog. `idempotency_key` must be stored alongside the order creation result scoped to the customer/caller. If the same key and same payload are resent, return the already-created order; if the same key is reused with a different payload, return an error per documented policy, typically INVALID_ARGUMENT or ALREADY_EXISTS.

**GetOrder**

The server validates the order ID and access permissions. Do not leak the existence of orders belonging to other customers if security policy requires hiding resources; in that case, return NOT_FOUND instead of PERMISSION_DENIED according to a consistent policy.

**ListOrders**

`page_size` has a clear default and maximum. `page_token` is an opaque token issued by the server, not an offset incremented by the client. The token should be bound to the filter/customer and sort order so the client cannot alter the query between pages. An empty `next_page_token` indicates the last page.

**UpdateOrder**

`update_mask` determines which fields are updated. In v1, only the `note` path is supported. If the mask does not contain note, keep the existing note unchanged. If the mask contains note and `patch.hasNote()` is true, set the new value; if the mask contains note but the field is absent, clear the note. The server rejects any path outside the allowlist. `expected_version` protects against concurrent updates.

**CancelOrder**

The server validates the state transition. For example, PENDING or CONFIRMED orders can be cancelled per policy; SHIPPED or DELIVERED orders cannot be cancelled directly. A successful cancellation updates status, increments version, and emits an OrderEvent. Repeated cancel calls need clear semantics: either return the already-CANCELLED order if the reason/operation is idempotent, or return FAILED_PRECONDITION if required by the contract.

**WatchOrderEvents**

The server emits only events with a sequence greater than `after_sequence`, in ascending order. Each event carries an `event_id` so consumers can deduplicate upon reconnect. If the cursor is too old and events have expired past retention, the server can return OUT_OF_RANGE with guidance for the client to fetch a snapshot via GetOrder and then open a new stream. Client cancellation of the stream must cause the server to stop the subscription and release resources.

## 7. Schema Evolution Rules

Field numbers are wire identifiers and must never be reused. When removing a field, reserve both its number and name. Do not change a field's type or cardinality, or move a field into or out of a oneof without evaluating compatibility.

Key principles for v1:
- Add new fields with new numbers in an additive manner.
- Keep published enum numbers; add new enum values with unused numbers.
- Maintain a zero enum value suffixed with UNSPECIFIED.
- Clients must handle unknown enum values gracefully.
- Never change published package, service, or method paths.
- Never change a unary RPC to streaming on the same method.
- If breaking changes are unavoidable, release v2 and maintain v1 during a support window.

For example, if the old `note` field at number 9 in Order is later removed, do not reuse number 9:

```proto
message Order {
  string order_id = 1;
  reserved 9;
  reserved "note";
  // Keep the previously published field numbers for the remaining fields.
}
```

## 8. Generating Java Code and Verifying the Contract

With protoc and the gRPC Java plugin installed in the build environment, you can generate message classes and gRPC stubs from the proto file. Example command:

```bash
protoc \
  -I src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  --plugin=protoc-gen-grpc-java=/path/to/protoc-gen-grpc-java \
  --grpc-java_out=build/generated/source/proto/main/grpc \
  src/main/proto/shop/order/v1/order_service.proto
```

The plugin path and output directory depend on the environment. The project's build plugin can configure protoc and the gRPC Java generator automatically; what matters is that both generators use the same proto source and compatible dependency versions.

The main generated classes include:
- Message classes such as CreateOrderRequest, Order, OrderItem, and OrderEvent.
- `OrderServiceGrpc` with blocking, async, and future stubs depending on the generator/dependencies.
- `OrderServiceImplBase` as the base class for the provider implementation.
- Descriptors for inspecting the package, service, methods, request/response types, and RPC cardinality.

A simple descriptor test:

```java
@Test
void orderServiceExposesExpectedRpcMethods() {
    io.grpc.ServiceDescriptor descriptor =
            OrderServiceGrpc.getServiceDescriptor();

    Set<String> methods = descriptor.getMethods().stream()
            .map(io.grpc.MethodDescriptor::getFullMethodName)
            .collect(Collectors.toSet());

    assertTrue(methods.contains(
            "shop.order.v1.OrderService/CreateOrder"));
    assertTrue(methods.contains(
            "shop.order.v1.OrderService/WatchOrderEvents"));
}
```

This test confirms that the generated gRPC descriptor contains the expected method paths. It does not prove that the provider has registered or implemented the handlers; provider integration tests verify that when implementing the service.

## 9. Using the Generated Stub from the Client

Example of building a request and calling CreateOrder with a blocking stub:

```java
CreateOrderRequest request = CreateOrderRequest.newBuilder()
        .setCustomerId("customer-42")
        .addItems(OrderItemInput.newBuilder()
                .setProductId("keyboard-01")
                .setQuantity(2))
        .setIdempotencyKey("checkout-2026-000184")
        .build();

Order order = orderStub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .createOrder(request);

assertEquals(OrderStatus.ORDER_STATUS_PENDING, order.getStatus());
assertEquals("customer-42", order.getCustomerId());
```

In a Spring application, channels and stubs should be managed with an appropriate lifecycle; deadlines are set per call. Never create a new channel per request. Authentication credentials and correlation metadata are attached via client credentials/interceptors rather than embedding tokens inside the protobuf request.

For WatchOrderEvents, use an async stub and a StreamObserver to receive events continuously. The client must handle onError/onCompleted, track the last sequence cursor, and reconnect in a controlled manner. On reconnect, send after_sequence to resume from the next event; event_id supports deduplication if the server replays an event across the reconnect boundary.

## 10. Project Completion Checklist

- [ ] The proto file is in the correct package path and versioned as v1.
- [ ] java_package, java_multiple_files, and outer class are explicitly set.
- [ ] Unary/streaming RPCs match the use cases.
- [ ] Requests only contain inputs the client is permitted to supply.
- [ ] The server owns price lookup, total calculation, and state transitions.
- [ ] Field numbers are unique, enums have a zero UNSPECIFIED value, and numbers are never reused.
- [ ] Optional/presence is used on fields that need to distinguish absent from default.
- [ ] Pagination uses an opaque page token.
- [ ] CreateOrder includes an idempotency key and retry semantics.
- [ ] UpdateOrder uses FieldMask and expected_version.
- [ ] WatchOrderEvents defines sequence, cursor, and cancellation behavior.
- [ ] Status codes for validation, not-found, permission, conflict, and precondition are defined.
- [ ] Java messages/stubs are generated from the exact proto source.
- [ ] Descriptor tests confirm full method paths and RPC shapes.
- [ ] A compatibility/versioning plan exists for future extensions.

**Self-Check**

**Question 1.** Why shouldn't CreateOrderRequest accept the unit price from the client?

*Answer:* Prices must be looked up by the server from a trusted catalog at order creation time. Trusting client-supplied prices would allow callers to tamper with prices and corrupt financial data.

**Question 2.** Why is idempotency_key needed for CreateOrder?

*Answer:* When a response is lost or a client retries after a deadline, the same order-creation intent may be sent multiple times. An idempotency key lets the server return the already-created result instead of creating duplicate orders.

**Question 3.** Why does ListOrders use page_token instead of an offset?

*Answer:* An opaque token lets the server maintain a stable cursor/sort/filter and change pagination internals without exposing internal offsets. The client simply sends back the token issued by the server.

**Question 4.** How do update_mask and optional note work together?

*Answer:* update_mask specifies which fields are permitted to be updated. When the mask includes note, the presence of patch.note distinguishes setting a new value from clearing the note according to the published semantics.

**Question 5.** Why does WatchOrderEvents need both after_sequence and event_id?

*Answer:* after_sequence lets the client resume from the last received position after reconnecting; event_id supports deduplication if an event is replayed across the connection boundary.

A well-defined proto clarifies data ownership, business states, retries, pagination, and stream lifecycles right at the client/server boundary. With OrderService v1, the RPCs have stable names and shapes, fields have clear numbers, optional/presence matches requirements, and the event stream includes a cursor for reconnection. This forms the foundation for generating Java stubs and implementing the order management service in Spring gRPC.
