# Choosing Required Fields for Compatibility in Spring gRPC

When developing **Spring gRPC** services, business requirements often treat certain inputs as "required": an order ID must exist, quantity must exceed 0, a fulfillment method must be chosen. However, in a **Protocol Buffers** contract, being *business-required* does not mean *the field must always be physically required in the protobuf payload*. Confusing the two concepts can break older clients when the server deploys a new version.

This lesson belongs to the **Schema design** chapter of the **SPRING_GRPC** module and focuses on choosing and validating fields in `.proto` files so Java clients/servers, unary RPCs, and streaming RPCs can evolve together. These decisions affect code generation, validation, gRPC status codes, integration tests, retryability, and API reliability.

After this lesson, you will be able to:

- Distinguish three questions: whether a field *is present*, whether it *has a valid value*, and whether it *is required for a given business action*.
- Understand the differences among regular scalar fields, `optional`, messages, `oneof`, `repeated`, and enums in proto3.
- Design requests with clear validation without forcing legacy clients to send fields that were never previously required.
- Plan adding a new field safely across multiple client and server versions.
- Write Spring gRPC Java handlers that validate the right conditions, return appropriate errors, and build compatibility test suites.

## 1. "Required" Has Three Layers of Meaning

Suppose an e-commerce system exposes `CreateOrder`. The client sends a customer ID and order lines; the server creates the order only if every line's quantity is valid. Three levels of checks must be separated:

| Question | Example | Who decides? |
| --- | --- | --- |
| **Is the field present in the message?** | Did the client send `shipping_country`? | Protobuf *field presence* rules and incoming payload |
| **Is the value valid?** | `quantity > 0`, `customer_id` non-empty | API/server validation |
| **When does the domain need this field?** | A shipping address is needed only for home delivery | Contract and business rules |

The third layer is often conditional. For example, an in-store pickup order may not need a shipping address, whereas a home-delivery order requires a valid address. Forcing every client to send an address for every fulfillment method makes the API awkward and causes unnecessary churn.

A good schema documents these conditions in the contract and enforces them in server logic. **Declaring a field in `.proto` alone does not validate it.**

## 2. How Does Proto3 Handle Default Values and Presence?

In `proto3` syntax, the proto2 `required` keyword is **not allowed**. You normally declare regular fields and validate business constraints on the server. When you need to distinguish "client omitted the field" from "client explicitly sent the default value", use an appropriate presence mechanism.

| Proto3 field kind | When omitted | Presence check in generated Java | Design note |
| --- | --- | --- | --- |
| `string customer_id = 1;` | Reads as `""` | No `hasCustomerId()` for plain scalars | If `""` is forbidden, `isBlank()` may suffice for validation |
| `int32 quantity = 2;` | Reads as `0` | No `hasQuantity()` for plain scalars | Cannot tell whether client sent `0` or omitted it |
| `bool enabled = 3;` | Reads as `false` | No `hasEnabled()` for plain scalars | Easy to confuse "unchanged" with "set false" in updates |
| `optional bool enabled = 4;` | Absent, though getter still returns default | `hasEnabled()` | Distinguishes missing field from `enabled = false` |
| `Product product = 5;` | Message absent | `hasProduct()` | Message fields in proto3 track presence |
| `oneof selector { ... }` | No branch selected | `getSelectorCase()`, `has...()` for each branch | Represents at most one choice; does not enforce choosing one |
| `repeated Item items = 6;` | Empty list | `getItemsCount()` | Does not distinguish an omitted list from an empty list in standard form |
| `map<string, string> tags = 7;` | Empty map | `getTagsCount()` | No presence flag for the map as a whole like an optional scalar |

Illustrative examples:

```proto
syntax = "proto3";

message PreferenceRequest {
  bool active = 1;
  optional bool email_notifications = 2;
}
```

```java
// Java code generated from PreferenceRequest.
PreferenceRequest request = PreferenceRequest.newBuilder().build();

boolean active = request.getActive();                    // false
boolean email = request.getEmailNotifications();         // false
boolean sentEmailField = request.hasEmailNotifications(); // false
```

If a client builds:

```java
PreferenceRequest request = PreferenceRequest.newBuilder()
        .setEmailNotifications(false)
        .build();

boolean sentEmailField = request.hasEmailNotifications(); // true
```

Two requests can produce the exact same `getEmailNotifications() == false` yet carry **different intents**. Presence is especially important in partial updates, because "skip this field" is not always equivalent to "set this field to its default value".

### Presence Is Not Validation

`optional string customer_id = 1;` lets you check `hasCustomerId()`, but **does not guarantee** the ID is valid: a client can still send an empty string. Conversely, `string customer_id = 1;` lacks presence, yet checking `isBlank()` suffices to reject both an omitted value and an explicit empty string if the domain treats both the same way.

Therefore, **do not put `optional` on every field just to "look explicit"**. Use it when the system genuinely needs to know whether a field was sent.

## 3. Anti-Pattern: Adding a New Field and Immediately Requiring It

Suppose the initial version of `CreateOrderRequest` is already used by many Java and mobile apps:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  FulfillmentMethod fulfillment_method = 3;
  string request_id = 4;
}
```

Later, the server team wants to add `shipping_country`. They deploy:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  FulfillmentMethod fulfillment_method = 3;
  string request_id = 4;
  string shipping_country = 5;  // New field.
}
```

At the binary protobuf level, **adding field 5 is normally format-compatible**: old clients do not know about it and omit it; the new server still decodes older tags. The problem arises when the new server enforces:

```java
if (request.getShippingCountry().isBlank()) {
    throw Status.INVALID_ARGUMENT
            .withDescription("shipping_country is required")
            .asRuntimeException();
}
```

Every old client that does not send field 5 gets rejected, even for orders that succeeded previously. **Wire-compatible does not mean behavior-compatible.** You do not need to break binary framing or change an RPC path to break applications; tightening validation alone is enough.

If the order can infer the country from a trusted shipping profile or does not need a country for store pickup, the server can continue serving legacy requests via compatible rules. If a country is **truly mandatory for every request and cannot be inferred**, that is a breaking behavioral change; consider a new API/version instead of silently forcing it on `v1`.

## 4. Complete Design: Business-Required Fields, Compatible New Fields

The following example uses two unary RPCs for creating orders and updating order notes. The contract sits at `src/main/proto/order/v1/order.proto`:

```proto
syntax = "proto3";

package shop.order.v1;

option java_package = "com.myshop.grpc.order.v1";
option java_multiple_files = true;
option java_outer_classname = "OrderProto";

import "google/protobuf/timestamp.proto";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
  rpc UpdateOrderNote(UpdateOrderNoteRequest) returns (UpdateOrderNoteResponse);
}

enum FulfillmentMethod {
  FULFILLMENT_METHOD_UNSPECIFIED = 0;
  FULFILLMENT_METHOD_STORE_PICKUP = 1;
  FULFILLMENT_METHOD_HOME_DELIVERY = 2;
}

message OrderLine {
  string product_id = 1;
  int32 quantity = 2;
}

message CreateOrderRequest {
  // Business-required; server validates non-blank.
  string customer_id = 1;

  // Must have at least one line; each quantity must be > 0.
  repeated OrderLine lines = 2;

  // UNSPECIFIED = 0 is rejected when creating an order.
  FulfillmentMethod fulfillment_method = 3;

  // Included in the initial v1 contract; server guarantees ID-based retry deduplication.
  string request_id = 4;

  // Added after v1 already had clients. Not yet required for v1 clients.
  // When present, use an ISO 3166-1 alpha-2 country code, e.g. "VN".
  optional string shipping_country = 5;
}

message CreateOrderResponse {
  string order_id = 1;
  google.protobuf.Timestamp created_at = 2;
}

message UpdateOrderNoteRequest {
  string order_id = 1;

  // Omitted => no request to modify the note.
  // Empty string "" => request to clear the note content.
  optional string note = 2;
}

message UpdateOrderNoteResponse {
  string order_id = 1;
  google.protobuf.Timestamp updated_at = 2;
}
```

Key takeaways:

1. `customer_id`, `lines`, `fulfillment_method`, and `request_id` carry clear business requirements from the initial `v1` release. The server must validate them; protobuf does not force clients to populate them.
2. `FULFILLMENT_METHOD_UNSPECIFIED = 0` represents an unselected value. Enum naming aids validation; `0` is the proto3 enum default and should represent a non-actionable sentinel.
3. `shipping_country = 5` is a **later addition**: it uses a new tag, keeps all older tags intact, and does not immediately force `v1` clients to send it.
4. `optional string note` distinguishes "leave the note unchanged" from "clear the note with an empty string" in the update RPC.
5. `request_id` protects retries only when the server implements deduplication tied to the ID and payload. Naming a field `request_id` does not create idempotency automatically.

### Business Rules for `shipping_country`

The contract must state how the new field is applied:

| Order type | Client omits `shipping_country` | Client sends `shipping_country` |
| --- | --- | --- |
| `STORE_PICKUP` | Valid if store pickup does not require a country | May be used or ignored per published API policy |
| `HOME_DELIVERY` | Server continues using the delivery address source already supported in `v1`; if required data is missing, apply existing error rules | Validate the country code and apply it to delivery logic if allowed by the contract |

If country data in legacy profiles is unreliable, **do not fabricate a default `"VN"` for every customer**. Safe evolution also depends on how `v1` originally handled shipping. When no safe compatibility fallback exists, introduce a new contract or data migration flow before requiring the field.

### An Enum Compatibility Caveat

The server should distinguish `FULFILLMENT_METHOD_UNSPECIFIED` (not chosen) from an **unknown newer enum value** sent by a newer client. In protobuf Java, an enum field typically has both an enum getter and an integer getter, such as `getFulfillmentMethod()` and `getFulfillmentMethodValue()`. If a client sends a value unrecognized by the server, handle it according to API policy rather than silently falling back to `STORE_PICKUP`.

## 5. Java Code: Practical Validation at the Spring gRPC Boundary

With `protoc` and the gRPC Java plugin, `CreateOrderRequest` generates getters such as `getCustomerId()`, `getLinesCount()`, `getFulfillmentMethod()`, and `hasShippingCountry()`. A Spring gRPC handler can validate inputs without forcing legacy clients to send field 5.

```java
package com.myshop.server.order;

import com.myshop.grpc.order.v1.CreateOrderRequest;
import com.myshop.grpc.order.v1.CreateOrderResponse;
import com.myshop.grpc.order.v1.FulfillmentMethod;
import com.myshop.grpc.order.v1.OrderLine;
import com.myshop.grpc.order.v1.OrderServiceGrpc;
import com.google.protobuf.Timestamp;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.time.Instant;
import java.util.UUID;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class OrderGrpcEndpoint extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<CreateOrderResponse> observer) {

        if (request.getCustomerId().isBlank()
                || request.getRequestId().isBlank()
                || request.getLinesCount() == 0) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("customer_id, request_id and lines are required")
                    .asRuntimeException());
            return;
        }

        for (OrderLine line : request.getLinesList()) {
            if (line.getProductId().isBlank() || line.getQuantity() <= 0) {
                observer.onError(Status.INVALID_ARGUMENT
                        .withDescription("each line requires product_id and quantity > 0")
                        .asRuntimeException());
                return;
            }
        }

        if (request.getFulfillmentMethod()
                == FulfillmentMethod.FULFILLMENT_METHOD_UNSPECIFIED
                || request.getFulfillmentMethod()
                == FulfillmentMethod.UNRECOGNIZED) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("unsupported fulfillment_method")
                    .asRuntimeException());
            return;
        }

        // Validate field 5 only if the client actually sent it.
        if (request.hasShippingCountry()
                && !request.getShippingCountry().matches("[A-Z]{2}")) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("shipping_country must be an alpha-2 code")
                    .asRuntimeException());
            return;
        }

        // Example illustrates only validation and response construction.
        // A real application persists the order, handles idempotency, and arranges delivery.
        Instant now = Instant.now();
        Timestamp createdAt = Timestamp.newBuilder()
                .setSeconds(now.getEpochSecond())
                .setNanos(now.getNano())
                .build();

        CreateOrderResponse response = CreateOrderResponse.newBuilder()
                .setOrderId(UUID.randomUUID().toString())
                .setCreatedAt(createdAt)
                .build();

        observer.onNext(response);
        observer.onCompleted();
    }
}
```

In this sample code, the server checks:

- `customer_id` and `request_id` are non-blank, and `lines` has at least one element.
- Each line has a valid `product_id` and `quantity > 0`.
- `fulfillment_method` is neither `UNSPECIFIED` nor an unrecognized enum value.
- `shipping_country` matches the format **when sent**; when omitted, it is not blocked by this new rule.

This code only illustrates validation: in production, the handler must invoke a domain service to actually create the order, enforce authorization, resolve shipping addresses, manage transactions, and handle idempotency. If there is `v1`-compatible handling when `HOME_DELIVERY` omits the country, implement it in the domain service and cover it with tests. Do not use this example as a complete order-creation feature.

### Which Error Status Should Be Returned?

| Issue | Suggested gRPC status | Explanation |
| --- | --- | --- |
| Missing `customer_id`, empty line list, negative quantity | `INVALID_ARGUMENT` | Input data is invalid |
| Well-formed customer ID does not exist | `NOT_FOUND` | Requested target resource does not exist |
| Order cannot be created due to insufficient stock | `FAILED_PRECONDITION` | Domain preconditions are not met at processing time |
| Concurrent update conflict requiring re-read and retry | `ABORTED` in appropriate models | State contention, not invalid request syntax |
| Caller lacks permission to create orders | `PERMISSION_DENIED` | Authorization failure |
| Dependent service unavailable | `UNAVAILABLE` | Transient error; retries must consider whether the command already ran |

Do not return a response with `success = false` and complete with `OK` for a failed request; gRPC status codes let interceptors, client retries, and monitoring systems interpret outcomes accurately.

## 6. `optional`: When Absence and Default Values Mean Different Things

Consider updating a note:

```proto
message UpdateOrderNoteRequest {
  string order_id = 1;
  optional string note = 2;
}
```

In Java:

```java
// Note omitted: no change requested.
UpdateOrderNoteRequest a = UpdateOrderNoteRequest.newBuilder()
        .setOrderId("O-100")
        .build();
boolean aHasNote = a.hasNote();  // false

// Empty note sent: request to clear the note content.
UpdateOrderNoteRequest b = UpdateOrderNoteRequest.newBuilder()
        .setOrderId("O-100")
        .setNote("")
        .build();
boolean bHasNote = b.hasNote();  // true
```

If you drop `optional` and check only `getNote().isEmpty()`, the server cannot tell these two intents apart. The contract must state what `hasNote() == false` means: it could be a no-op or rejected because the RPC's sole purpose is updating the note. In this example, the clean choice is **returning `INVALID_ARGUMENT` when `note` is omitted**, while an empty string means clearing the note. That is validation driven by RPC semantics, not enforced automatically by `optional`.

### When to Choose `FieldMask`?

When an RPC updates multiple fields, use `google.protobuf.FieldMask` to list the paths being updated:

```proto
import "google/protobuf/field_mask.proto";

message EditableOrderFields {
  string delivery_note = 1;
  bool gift_wrap = 2;
}

message UpdateOrderRequest {
  string order_id = 1;
  EditableOrderFields changes = 2;
  google.protobuf.FieldMask update_mask = 3;
}
```

For example, `update_mask.paths = ["gift_wrap"]` with `changes.gift_wrap = false` means **intentionally set to false**. The server updates only fields listed in the mask, checks path whitelists, and leaves unlisted fields untouched. Paths in `FieldMask` use proto field names, such as `gift_wrap`, not Java getter names. The ProtoJSON representation of `FieldMask` converts paths to camelCase (for example `"updateMask": "giftWrap"`).

`optional` fits when only a few scalars need presence tracking; `FieldMask` fits when specifying a set of update paths, especially for large or nested objects. Never use either as an excuse to skip business validation.

## 7. `oneof` and Message Fields: Conditionally Required Types

A query may let clients choose *one of two* identifiers:

```proto
message FindOrderRequest {
  oneof selector {
    string order_id = 1;
    string external_reference = 2;
  }
}
```

`oneof` guarantees at most one branch is set in a message at a time. However, a client can still send **no branch at all**; the server must check `getSelectorCase()` and reject the unset case. Moreover, a client may select `order_id` and pass an empty string, so value validation is still required.

For message-typed fields:

```proto
message Address {
  string country_code = 1;
  string city = 2;
}

message ShipOrderRequest {
  string order_id = 1;
  Address destination = 2;
}
```

In Java, `hasDestination()` indicates whether `destination` is present. Yet an empty `Address` is still a present message: you must validate `country_code`, `city`, and other address constraints. Message presence does not replace validating the fields inside the message.

### Enums and Default Values

Enums in proto3 should have their first value equal to 0, commonly using the `_UNSPECIFIED` suffix:

```proto
enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2;
}
```

If business logic requires choosing a payment method, the server rejects `PAYMENT_METHOD_UNSPECIFIED`. However, do not force a newly introduced enum value on old requests: un-upgraded clients cannot send it. Design clear handling for unknown values and explicit versioning policies.

## 8. Designing for Compatibility When Adding New Fields: Rollout Plan

When adding a field to an in-use request, separate **extending the wire format** from **changing business rules**:

| Phase | Server | Client | Goal |
| --- | --- | --- | --- |
| 1. Publish | Accepts the new field; still supports legacy calls | Legacy clients stay unchanged | Avoid disrupting existing traffic |
| 2. Gradual upgrade | Validates the new value when present; preserves promised fallback | New clients begin sending the field | Verify the new field in production |
| 3. Observe | Tracks missing-field rate by client version if appropriate, without logging sensitive data | Remediate un-upgraded clients | Know who still depends on the old contract |
| 4. Enforce | Keep `v1` contract or publish a `v2` endpoint/namespace if incompatible | Migrate per migration guide | Change rules without unexpectedly breaking legacy clients |

Do not assume all clients "will upgrade soon" without evidence. With mobile apps, partner integrations, or independently deployed versions, old clients can linger for a long time. When the server cannot identify or manage client versions, enforcing a new field on an existing endpoint is even riskier.

### Why "New Server Can Read Old Requests" Is Not Enough

Consider all four version pairings:

| Version pair | What typically happens at the protobuf layer | Real-world risk |
| --- | --- | --- |
| **Old client → new server** | Old fields decode fine; new field is absent | New server may change validation and unexpectedly reject old clients |
| **New client → old server** | Old server normally ignores unknown new fields in binary protobuf | New intent may be **silently dropped**; e.g., shipping country is never applied |
| **New client → new server** | Both sides understand the new field | Still needs validation, permissions, and domain guarantees |
| **Old client → old server** | Legacy behavior continues | If migration is required, plan API lifecycle |

If a client **depends on the new behavior**, it should not send the new request to an old server and assume the new field was applied. During rolling deployments across multiple server instances, ensure older server instances do not silently ignore data that affects correctness. Deploy server support before enabling clients, use dedicated endpoints/capabilities when needed, or version the API.

### When Should You Create `v2`?

Consider a new version when **you cannot preserve the same semantics for old clients**, for example:

- Every home-delivery order now requires information that a `v1` server cannot safely derive.
- The old RPC allowed omitting a field, while new business rules require the client to supply it directly.
- A field's semantics or type changes so fundamentally that old clients cannot interpret it correctly.
- New clients require the server to act on an important field that old servers will definitely ignore.

A new namespace like `shop.order.v2` or a clearly documented new RPC lets contracts run side by side during transition. You do not need to bump the major version merely to add an optional field with a safe default.

## 9. Binary Compatibility, ProtoJSON, and Java Code Are Three Different Things

Do not judge impact solely by whether a protobuf message still parses:

| Change | Binary protobuf | ProtoJSON / Java / behavior |
| --- | --- | --- |
| Add a new optional field number | Old clients/servers typically ignore unknown fields | Old clients omit the field; new behavior needs a fallback |
| Change `string x = 1` to `optional string x = 1` | Tag and wire type remain compatible in many scenarios | Java adds `hasX()`; default value vs. presence representation can affect logic |
| Rename a field while keeping number and type | Binary payload may still decode | Java getters/builders, default JSON keys, and descriptors change |
| Change field number of a published field | Risk of misreading or losing data | Affects all consumers |
| Rename a message | Individual binary fields may remain unchanged | Generated APIs, reflection, and `google.protobuf.Any` can break |
| Change proto `package`, service name, or RPC name | Payload bytes may remain equivalent | **Changes the gRPC path** such as `/shop.order.v1.OrderService/CreateOrder` |

In ProtoJSON, fields typically use `lowerCamelCase` names (e.g. `shippingCountry` for `shipping_country`). Java callers can invoke `hasShippingCountry()` on an `optional` field, yet legacy JSON clients may omit the key. Moreover, serializers may emit or omit default values differently depending on configuration; never rely solely on JSON key presence to infer intent without understanding the mapping.

### Removing Fields and `reserved`

When a published field is removed from the schema, never reuse its number or name for a new meaning:

```proto
message ExampleRequest {
  reserved 7;
  reserved "legacy_customer_code";

  string customer_id = 1;
}
```

This snippet illustrates protecting a removed legacy field 7. `reserved` prevents developers from accidentally reusing old field numbers or names. Do not arbitrarily renumber existing fields to "tidy up" the schema.

## 10. Metadata, Deadlines, Errors, and Retries Cannot Replace a Field Contract

Message contracts should hold business data; many technical call concerns belong elsewhere:

| Concern | Where it belongs | Relation to required fields |
| --- | --- | --- |
| Caller authentication, trace context | gRPC metadata and interceptors | No need to add `auth_token` to every business request |
| Deadlines | gRPC client sets deadline, server handles cancellation | Deadline expiration does not guarantee a command did not commit |
| Error status | gRPC status and error details when needed | Report missing required input with `INVALID_ARGUMENT` |
| TLS/mTLS | Channel and server transport | Secures the wire rather than adding a `secure = true` field |
| Idempotency | Business request ID plus server storage/dedupe | If a client retries after a timeout, it must keep the same ID for the same intent |
| Monitoring | Per-service and per-method metrics/traces | Track missing-field rates to guide migration |

**Retry caution:** if `CreateOrder` committed but the client missed the response due to a deadline, retrying with a different `request_id` can create two orders. Therefore, when the contract promises idempotency, the server must enforce uniqueness and replay the stored result for the same request ID and payload. Likewise, "failed to send a new field" is not a transiently retryable error: if an old client does not know the field, retrying will keep omitting it.

For server streaming or bidirectional streaming, the same concerns apply to **every message in the stream**. Adding a new field and treating it as required on every event can break older stream clients; forcing old stream requests to send a new field breaks connections. Design compatibility around both message schemas and consumer behavior, and test cancellation, backpressure, chunking, and stream termination states.

## 11. Compatibility Testing: Don't Test Only the New Version

gRPC tests should use Java stubs generated from the relevant schema versions, or matching binary/ProtoJSON fixtures. After adding `shipping_country`, include at least these cases:

| Case | Input | Expected result |
| --- | --- | --- |
| `v1` client creates order | Tag 5 absent | Extended `v1` server still processes using promised compatibility rules |
| New client omits new field | `hasShippingCountry() == false` | Does not enforce the new requirement across all `v1` requests |
| Client sends valid country | `shipping_country = "VN"` | Validates and applies business policy properly |
| Client sends invalid country format | `shipping_country = "Vietnam"` | `INVALID_ARGUMENT` if contract requires alpha-2 codes |
| Empty line list | `lines_count = 0` | `INVALID_ARGUMENT`; no order created |
| Zero or negative quantity | `quantity <= 0` | `INVALID_ARGUMENT` |
| Unselected enum | `FULFILLMENT_METHOD_UNSPECIFIED` | `INVALID_ARGUMENT` |
| Update note without `note` | `hasNote() == false` | Returns error or no-op **per published convention** |
| Update note with empty string | `hasNote() == true`, `getNote().isEmpty()` | Clears note if valid |
| New client sends field to old server | Server unaware of tag 5 | Detects risk of ignored field; governs routing/rollout |
| Client retries with same `request_id` | Same payload after timeout | No duplicate creation within idempotency window |
| Old client calls `v2` API | New RPC or new package | Never assume old stubs work automatically; test explicit migration |

### Testing With `grpcurl`

When a test server is running on `localhost:9090` allowing plaintext connections, you can send a request using ProtoJSON mapping:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto order/v1/order.proto \
  -d '{
    "customerId": "C-100",
    "lines": [{"productId": "P-100", "quantity": 2}],
    "fulfillmentMethod": "FULFILLMENT_METHOD_STORE_PICKUP",
    "requestId": "order-20261119-001"
  }' \
  localhost:9090 shop.order.v1.OrderService/CreateOrder
```

The request intentionally **omits** `shippingCountry`, simulating a legacy client. A compatible server must not reject it *merely because* field 5 was omitted. In real environments, port and TLS settings must match, and the handler must implement real order-creation logic.

To test presence of the new field, add the key:

```json
{
  "shippingCountry": "VN"
}
```

This JSON snippet is an addition to the request above, not a complete standalone valid input. With `optional string shipping_country`, the Java server can check `hasShippingCountry()` instead of guessing from `getShippingCountry().isEmpty()`.

## 12. Decision Checklist Before Publishing a Field

Before adding, removing, or modifying a field in a Spring gRPC API, answer:

1. **Business need:** Is the field required on every call, only in one conditional branch, or purely an optional enhancement?
2. **Presence:** Do we need to distinguish "omitted" from "sent the default value"? If so, do scalar `optional`, `oneof`, a sub-message, or `FieldMask` match the intent?
3. **Old clients:** Will requests built from earlier protos omit this field? Can the new server safely preserve legacy behavior?
4. **New clients:** Could an old server ignoring the new field cause dangerous misbehavior? Do we need server-first deployment, capability negotiation, or a `v2` API?
5. **Validation:** How are blank strings, `0`, `false`, empty lists, unknown enums, and empty messages handled?
6. **Wire safety:** Are field numbers preserved, types compatible, and removed numbers/names marked `reserved`?
7. **Operations:** How are gRPC status codes, metadata, deadlines, idempotency, and missing-field rates per client version monitored?
8. **Testing:** Have you tested old client → new server, new client → old server, and presence edge cases?

### Self-Check

**Question 1.** In proto3, `int32 quantity = 1;` does not have `optional`. The server receives `getQuantity() == 0`. Can it tell for sure that the client sent `0`?

**Answer:** No. For plain scalars, the server has no presence flag to distinguish an explicit `0` from an omitted field. If the domain forbids both, rejecting `quantity <= 0` suffices; if you must distinguish them, use an appropriate presence mechanism.

**Question 2.** The `CreateOrder` API already has many clients. Adding `string shipping_country = 5;` is binary-compatible. Can you start returning `INVALID_ARGUMENT` tomorrow for every request missing field 5?

**Answer:** No, not if you must preserve behavioral compatibility with existing clients. Earlier clients cannot send this field. You need a safe fallback, migration, or a new contract before enforcing it.

**Question 3.** With `optional bool gift_wrap = 2;`, how do you distinguish "omitted" from "sent `false`" in Java?

**Answer:** Use `hasGiftWrap()` to check presence; `getGiftWrap()` returns the value. `hasGiftWrap() == true` together with `getGiftWrap() == false` means the client explicitly sent `false`.

**Question 4.** Why does `oneof` still need validation if the request requires choosing exactly one of two identifiers?

**Answer:** `oneof` guarantees at most one branch is set, yet zero branches may be sent; furthermore, the selected branch may still contain an empty or malformed value.

**Question 5.** A new client sends `shipping_country` to an old server, and the RPC returns `OK`. Is it certain the server used the submitted country?

**Answer:** No. The old server may ignore unknown fields when parsing binary protobuf. If new behavior depends on that field, ensure the client targets a supporting server or uses a new contract/version.

In gRPC schema design, **requirements must come from the business domain and be validated on the server**, while presence representation belongs to protobuf. When adding a field to a live contract, protect both *decodability* and *the behavior promised to existing clients*. That is the foundation for Spring gRPC services to scale reliably across versions and RPC types.
