# Designing Meaningful Requests and Responses in Spring gRPC

In **Spring gRPC**, the Protocol Buffers (`.proto`) file is the contract compiled into source code by both client and server. Method names may express the business capability accurately, yet an API remains hard to use if requests do not clearly state what to pass, responses lack stable semantics, or error states are mixed into success payloads. Good request/response design helps clients invoke unary or streaming RPCs correctly, servers validate inputs consistently, and both sides evolve schemas without breaking published contracts.

This lesson is part of the **Schema design** chapter of the **SPRING_GRPC** module. We will design a contract for a product catalog service, inspect Java examples in Spring gRPC, and examine how requests and responses relate to metadata, deadlines, gRPC status codes, integration testing, and compatibility.

After this lesson, you will be able to:

- Determine required fields, optional fields, default values, and validation rules for a request.
- Decide whether to return a single entity, a result collection, pagination metadata, or an event stream.
- Use `optional`, `oneof`, and `google.protobuf.FieldMask` with the right semantics.
- Separate business data in a response from RPC-level call errors.
- Design testable, extensible contracts while protecting existing clients.

## 1. Start From RPC Behavior

Before defining fields, write down four answers for each RPC:

1. **What does the client want to do?** Fetch one product, list by filter, update fields, or watch events?
2. **What must the client supply?** Which identifier selects the target, which filter criteria can be omitted, and are a pagination token or deduplication key needed?
3. **What does a successful outcome mean?** A current record, a possibly empty list, post-update state, or multiple events over time?
4. **Where are errors represented?** Missing identifiers, missing resources, insufficient permissions, or expired deadlines need appropriate gRPC status codes; a batch operation may need per-item results.

Example contract for `CatalogService`:

| RPC | Question the request answers | Response on success | Typical error cases |
| --- | --- | --- | --- |
| `GetProduct` | "Which product?" | Details of a single product | Missing ID: `INVALID_ARGUMENT`; missing resource: `NOT_FOUND` |
| `ListProducts` | "Which filters and which page?" | List (possibly empty) and next page token | Invalid token/filter semantics: `INVALID_ARGUMENT` |
| `UpdateProduct` | "Which product, and which fields?" | Product state after update | Not found: `NOT_FOUND`; invalid data: `INVALID_ARGUMENT` |
| `WatchProductEvents` | "Which product group to watch?" | Multiple events over time | Unauthorized: `PERMISSION_DENIED`; service disruption: `UNAVAILABLE` |

Design messages around **observable semantics**. Do not require clients to pass a `database_table_name` when the server can decide storage internally, or return `success = true` in every response when gRPC already distinguishes success from failure.

## 2. A Complete `.proto` Contract

Suppose `src/main/proto/catalog/v1/catalog.proto` contains:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";

import "google/protobuf/field_mask.proto";
import "google/protobuf/timestamp.proto";

service CatalogService {
  // One request -> one response.
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
  rpc ListProducts(ListProductsRequest) returns (ListProductsResponse);
  rpc UpdateProduct(UpdateProductRequest) returns (UpdateProductResponse);

  // One request -> a stream of responses.
  rpc WatchProductEvents(WatchProductEventsRequest)
      returns (stream ProductEvent);
}

message Product {
  string product_id = 1;
  string display_name = 2;
  string category_id = 3;

  // Price in the currency's smallest minor unit, e.g. 125000 VND.
  int64 price_minor_units = 4;
  string currency_code = 5;
  bool active = 6;
  google.protobuf.Timestamp updated_at = 7;
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  Product product = 1;
}

message ListProductsRequest {
  // Empty string means no category filter.
  string category_id = 1;
  // 0 uses the default page size; negative values are rejected.
  int32 page_size = 2;
  // Empty means the first page.
  string page_token = 3;
}

message ListProductsResponse {
  repeated Product products = 1;
  // Empty means there is no next page.
  string next_page_token = 2;
}

message UpdateProductRequest {
  // product_id identifies the target; other fields hold desired values.
  Product product = 1;
  // Only paths listed in the mask are updated.
  google.protobuf.FieldMask update_mask = 2;
  // Used to recognize retries of the same request, if supported by the server.
  string request_id = 3;
}

message UpdateProductResponse {
  // Latest state after a successful update.
  Product product = 1;
}

enum ProductEventType {
  PRODUCT_EVENT_TYPE_UNSPECIFIED = 0;
  PRODUCT_EVENT_TYPE_CREATED = 1;
  PRODUCT_EVENT_TYPE_UPDATED = 2;
  PRODUCT_EVENT_TYPE_DELETED = 3;
}

message WatchProductEventsRequest {
  // Empty means watch all categories the client is permitted to view.
  string category_id = 1;
}

message ProductEvent {
  // Event identifier so clients can detect duplicate messages.
  string event_id = 1;
  ProductEventType event_type = 2;
  // Always present for valid events.
  string product_id = 3;
  // May be omitted when the event represents product deletion.
  Product product = 4;
  google.protobuf.Timestamp occurred_at = 5;
}
```

This is an illustrative design, not a mandatory contract for every system. The conventions to lock down with API consumers are: `product_id` is non-empty for single-product operations; `ListProducts` returns an empty list when there are no matches; monetary amounts are always paired with `currency_code`; `UpdateProduct` modifies only the paths in `update_mask`; `ProductEvent` is one item in a server stream.

**Why separate `Product` from request/response types?** `Product` describes a reusable business entity. `GetProductRequest` holds lookup criteria; `ListProductsRequest` holds filter/pagination criteria; `UpdateProductRequest` holds both the target entity and the update scope. Separating them avoids forcing a single `Product` type to serve as input for every operation with conflicting semantics.

## 3. Designing Requests: Right Inputs, Clear Requirements

### 3.1. Fetching One Resource: Concise Yet Complete Criteria

```proto
message GetProductRequest {
  string product_id = 1;
}
```

The request does not need `display_name`, `category_id`, or product price: none of those are needed to look up by ID. The contract should clearly state the rules:

- `product_id` is **business-required**; an empty string is rejected with `INVALID_ARGUMENT`.
- If the ID is well-formed but the resource does not exist, return `NOT_FOUND`.
- If the identifier refers to an access-controlled resource, the server must also enforce authentication/authorization rules before returning data.

In proto3, `string product_id = 1;` defaults to `""` when omitted. The syntax does not automatically make a field required; the server must validate it. If you need to distinguish "not sent" from "intentionally sent an empty string", consider `optional string product_id = 1;` and check both presence and value; for APIs that only accept non-empty IDs, checking `isBlank()` may already suffice.

### 3.2. Listing: Clear Default Rules and Pagination

`ListProductsRequest` uses `category_id` to filter, `page_size` to cap the number of records, and `page_token` to resume from the previous page:

```json
{
  "categoryId": "CAT-10",
  "pageSize": 20,
  "pageToken": ""
}
```

In this example, agree on server-side rules:

| Field | Value | Interpretation |
| --- | --- | --- |
| `category_id` | `""` | Do not apply a category filter |
| `page_size` | `0` | Use default of 20 products/page |
| `page_size` | `1..100` | Up to the requested count, unless fewer records exist |
| `page_size` | Negative or greater than 100 | `INVALID_ARGUMENT` (per this example API's convention) |
| `page_token` | `""` | First page |
| `page_token` | Server-issued token | Retrieve the next page under the agreed criteria |

Do not return "all products" unbounded just because the client forgot to provide `page_size`. The server should enforce limits on item count and response size to protect performance and reliability.

`page_token` should be an **opaque token**: the client stores and sends it back verbatim without parsing or modifying it. When designing the server, decide whether the token is bound to filters, sort order, permissions, and expiration. If a consistent snapshot across multiple pages is required, a dedicated mechanism is needed; stable ordering alone does not prevent records from changing while a client paginates.

### 3.3. When Are `optional` or `oneof` Needed?

An ordinary scalar field in proto3 does not tell you reliably whether the client sent a value. This matters for update APIs or cases that must distinguish "omitted" from "sent the default value":

```proto
message SetProductVisibilityRequest {
  string product_id = 1;
  optional bool active = 2;
}
```

With appropriate generated Java code, `hasActive()` tells you whether the client sent the `active` field; `getActive()` returns the Boolean. When `active` is absent, the server should not infer an instruction to "set it to `false`".

When there are two mutually exclusive identifiers, `oneof` expresses the intent better than two arbitrary strings:

```proto
message LookupProductRequest {
  oneof selector {
    string product_id = 1;
    string sku = 2;
  }
}
```

`oneof` guarantees that a constructed message holds at most one choice from the group at a time. The server must still validate that **at least one valid choice is present** if the business logic requires exactly one.

## 4. Designing Responses: Success Must Have Unambiguous Meaning

### 4.1. Returning a Single Entity

```proto
message GetProductResponse {
  Product product = 1;
}
```

The contract specifies that when `GetProduct` succeeds, `product` must be present and carry a valid `product_id`. In proto3, a message field can be absent; therefore the server must guarantee its presence through tests and application logic. A successful response with a missing `product` forces the client to guess between "not found" and "server forgot to populate the payload".

You can also use `returns (Product)` directly when the contract is simple. Choose `GetProductResponse` when you want a clean per-method boundary and anticipate adding **business** result metadata; avoid pointless multi-layer wrappers.

Example ProtoJSON response when returning a product (`int64` values are encoded as JSON strings per ProtoJSON):

```json
{
  "product": {
    "productId": "P-100",
    "displayName": "Mechanical keyboard",
    "categoryId": "CAT-10",
    "priceMinorUnits": "125000",
    "currencyCode": "VND",
    "active": true,
    "updatedAt": "2026-11-19T08:00:00Z"
  }
}
```

Note: the JSON format shown here is **ProtoJSON**, not the binary protobuf bytes sent over HTTP/2 in standard gRPC. Tools like `grpcurl` can accept/emit JSON using that mapping.

### 4.2. Returning an Empty List Is a Valid Success

```proto
message ListProductsResponse {
  repeated Product products = 1;
  string next_page_token = 2;
}
```

Finding no products matching a filter is an `OK` result with an empty `products` list. Do not return `NOT_FOUND` simply because a list has zero items. An empty `next_page_token` indicates the end of pagination; a response containing data without a way to advance pages forces the client to guess.

```json
{
  "products": [],
  "nextPageToken": ""
}
```

In ProtoJSON, fields with default values may be omitted depending on serializer options; the example above illustrates the logical meaning of the response rather than guaranteeing every library always emits both keys. Clients should rely on protobuf field types and default values.

### 4.3. Returning the Updated Entity

`UpdateProductResponse.product` contains the final state after the server applies business rules, such as normalizing the name or updating `updated_at`. This is more useful than returning only a `success` flag because the client can immediately synchronize its state after the operation.

If no return payload is genuinely needed, you can use `google.protobuf.Empty`, while considering whether clients will need to re-read the resource. There is no need to attach `bool success`: in gRPC, normal completion indicates success, and failure cases must use status codes or a well-defined result model.

## 5. Partial Updates: Distinguishing "Unchanged" From "Reset to Default"

This is one of the most error-prone decisions. Suppose an existing product has `active = true`. The client wants to set `active = false` without changing the price. If the server blindly updates every field in `Product`, unsent fields take their default values and may be accidentally cleared.

In the design from Section 2, we use `google.protobuf.FieldMask`:

```proto
message UpdateProductRequest {
  Product product = 1;
  google.protobuf.FieldMask update_mask = 2;
  string request_id = 3;
}
```

Logical request:

```text
product.product_id = "P-100"
product.active = false
update_mask.paths = ["active"]
request_id = "change-20261119-001"
```

The server updates only `active` because the mask contains only that path; unlisted fields remain untouched. This is how you handle a Boolean `false` or an empty string that is **intentionally** sent to clear a value.

Rules to document clearly in the API specification:

1. Both `product` and `update_mask` must be present; `product.product_id` must be non-empty.
2. `update_mask.paths` must be non-empty. This project does not treat an empty mask as "update all fields".
3. Allow only the paths `display_name`, `category_id`, `price_minor_units`, `currency_code`, and `active`; reject `product_id` and `updated_at` since they are server-managed.
4. For fields with business coupling—such as price and currency code—validate the resulting combination to prevent inconsistent state.
5. `request_id` prevents duplicate processing **only if the server implements storing and checking idempotency keys** with a clear scope and expiration window; adding the field does not make the RPC idempotent by itself.

Paths in `FieldMask` are specified using **proto field names**, such as `display_name` and `active`. When representing a `FieldMask` in ProtoJSON, the mask string encoding follows JSON-specific rules (for example `"updateMask": "displayName,active"`). Do not confuse paths inside `FieldMask` with Java accessor method names.

An alternative is a dedicated request with `optional` scalar fields. That works well for updating a few fields, whereas with many attributes and nested data, `FieldMask` expresses the exact set of modified fields clearly. Whichever approach you choose, document the behavior for "omitted", "default value passed", and "value cleared".

## 6. Streaming RPCs: Responses Are No Longer a Single Result

Not every gRPC call has one request and one response:

| RPC kind | Proto signature | Request/response design |
| --- | --- | --- |
| Unary | `rpc GetProduct(GetProductRequest) returns (GetProductResponse);` | One request identifies the target; one response delivers the result |
| Server streaming | `rpc WatchProductEvents(WatchProductEventsRequest) returns (stream ProductEvent);` | Request selects the watch scope; each response is an event |
| Client streaming | `rpc UploadMeasurements(stream Measurement) returns (UploadMeasurementsResponse);` | Client sends multiple records; server returns a summary after reading the stream |
| Bidirectional streaming | `rpc SyncProducts(stream SyncProductsRequest) returns (stream SyncProductsResponse);` | Both sides send multiple messages independently; correlation and ordering must be specified |

The last two examples only illustrate signature shapes; to compile them, declare the corresponding `Measurement`, `UploadMeasurementsResponse`, `SyncProductsRequest`, and `SyncProductsResponse` messages.

### 6.1. Server Streaming: Each Response Must Be Self-Explanatory

In `WatchProductEvents`, each `ProductEvent` contains:

- `event_id` to detect or handle duplicate messages according to system policy.
- `event_type` so the client knows whether it is a creation, update, or deletion.
- `product_id` to identify the product even when a deletion event omits the `product` payload.
- `occurred_at` to record when the event happened rather than assuming the client's receipt time.

The contract must also specify event ordering, disconnect handling, replay, and starting position if supported. Simply adding `event_id` does not guarantee exactly-once delivery. If clients need to resume a stream after a disconnect, design a cursor/resume token and an appropriate event-storage mechanism.

The server may emit **zero messages** over a period of time while the stream remains healthy; that is neither an error nor "not found". Clients must support stream cancellation and deadlines where appropriate. If the domain requires heartbeat notifications, define an explicit event type or liveness check rather than emitting an ambiguous empty `ProductEvent`.

### 6.2. Client Streaming and Bidirectional: Define Relationships Between Messages

For client-streaming uploads, the summary response should report the accepted record count, rejected record count, and per-record error identifiers if partial processing is allowed. `accepted_count` and `rejected_count` are only meaningful when the contract defines what counts as accepted.

For bidirectional streaming, do not implicitly assume the `n`-th request always produces the `n`-th response. If the system processes requests concurrently or emits proactive events, add a `correlation_id` to related messages and document pairing rules, ordering, and retry policies. Deadlines, backpressure, half-closing each stream direction, and mid-stream errors must also be defined during implementation.

## 7. Separating Business Data From gRPC Error Status

**gRPC status** is a call-level outcome, separate from the message payload returned on success. Common codes include:

| Scenario | Appropriate status | Interpretation |
| --- | --- | --- |
| Missing `product_id`, negative `page_size`, invalid mask | `INVALID_ARGUMENT` | Request is invalid regardless of current system state |
| `GetProduct` cannot find the requested resource | `NOT_FOUND` | Target is valid in form but does not exist |
| Unauthenticated | `UNAUTHENTICATED` | Missing or invalid authentication credentials |
| Authenticated but not authorized | `PERMISSION_DENIED` | Insufficient permissions for the operation |
| Update conflicts with current state | `FAILED_PRECONDITION` or `ABORTED` depending on nature | Precondition no longer holds or transaction aborted due to conflict |
| Service temporarily unable to handle the call | `UNAVAILABLE` | May be suitable for retrying according to policy |
| Configured time budget expired | `DEADLINE_EXCEEDED` | Call did not finish before the deadline |

Do not stuff `status_code`/`error_message` into every response and return gRPC `OK` even when the request fails. Doing so misleads gRPC-layer interceptors, metrics, retries, and error observability. When clients need structured error details, the system can standardize on a rich error model (for example `google.rpc.Status` and error detail payloads); verify library support and metadata size limits before adopting it.

**Metadata and deadlines** also have distinct roles. Auth tokens, trace context, and control headers belong in metadata rather than being repeated as fields in every request. The client sets a call deadline; the server must respect cancellation/timeouts. TLS secures the transport; it is not an `encrypted = true` field in the request. Conversely, `product_id`, `page_token`, and `update_mask` are business data and belong in the message.

## 8. Illustrating a Unary Implementation in Spring gRPC

When compiling the proto with `protoc` and the gRPC Java plugin, classes such as `GetProductRequest`, `GetProductResponse`, `Product`, and `CatalogServiceGrpc` are generated under `java_package`. A service implemented with Spring gRPC can handle success and error cases as follows:

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import com.myshop.grpc.catalog.v1.Product;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class CatalogGrpcEndpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {

        String id = request.getProductId();
        if (id.isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id must not be blank")
                    .asRuntimeException());
            return;
        }

        // Fixed data to illustrate behavior; a real system reads from a repository.
        if (!id.equals("P-100")) {
            observer.onError(Status.NOT_FOUND
                    .withDescription("product not found")
                    .asRuntimeException());
            return;
        }

        Product product = Product.newBuilder()
                .setProductId("P-100")
                .setDisplayName("Mechanical keyboard")
                .setCategoryId("CAT-10")
                .setPriceMinorUnits(125000L)
                .setCurrencyCode("VND")
                .setActive(true)
                .build();

        GetProductResponse response = GetProductResponse.newBuilder()
                .setProduct(product)
                .build();
        observer.onNext(response);
        observer.onCompleted();
    }
}
```

In this example:

- For `product_id = ""`, the server calls `onError(INVALID_ARGUMENT)` and does **not** send a success response.
- For any ID other than `P-100`, the server calls `onError(NOT_FOUND)`.
- For `P-100`, the server emits one `GetProductResponse` containing `Product` and completes with `onCompleted()`.

The sample code intentionally omits repositories, authentication, and operational observability to keep the contract clear. In a real integration, enforce access checks and data validation before returning a product, avoid leaking sensitive details in error messages, and write tests covering every status. The import path for `@GrpcService` and starter configuration must match the Spring gRPC version your project uses.

A Java gRPC client with generated stubs can read the result and distinguish errors via `StatusRuntimeException`:

```java
import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import io.grpc.Channel;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;

public class CatalogClientExample {
    public static GetProductResponse fetch(Channel channel, String productId) {
        var stub = CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);

        try {
            return stub.getProduct(GetProductRequest.newBuilder()
                    .setProductId(productId)
                    .build());
        } catch (StatusRuntimeException ex) {
            if (ex.getStatus().getCode() == Status.Code.NOT_FOUND) {
                // Application chooses how to handle a missing resource.
                return null;
            }
            throw ex;
        }
    }
}
```

`Channel` is passed in so the example focuses on request/response handling; a Spring application should manage and reuse channels according to project configuration. Returning `null` in the `NOT_FOUND` branch is merely a choice of this client helper method, not a gRPC response sent by the server on error.

## 9. Designing for Change Without Surprises

In Protobuf, **field numbers and wire types** govern binary compatibility; meanwhile, field names affect generated code and ProtoJSON, and `service`/`rpc` names affect gRPC paths. When editing a published request or response, evaluate each compatibility layer:

| Change | Typical impact | Recommendation |
| --- | --- | --- |
| Add a new field with a new number | Old clients typically ignore unknown fields when decoding binary protobuf | Choose sensible defaults; do not make the new field mandatory for old clients without a transition |
| Rename a field while keeping number/type | May remain compatible on the binary wire, but changes Java accessors, ProtoJSON keys, and descriptors | Avoid after release; evaluate all clients, especially JSON clients |
| Change a published field number | Risks misreading or losing data | Never change; if removing a field, mark the removed number and name as `reserved` |
| Change a field type | Can alter the wire type or semantics, even if bytes still parse | Treat as a contract change; consider a new field or API version |
| Rename `service` or `rpc` | Changes the RPC path on the wire | Keep the old endpoint during transition or introduce a new version |
| Change `ListProducts` from returning all items to mandatory pagination | Old clients may unknowingly fetch only the first page | Publish pagination rules from the start; plan a clear migration if changing behavior |
| Change the semantics of `page_token` or `update_mask` | Does not necessarily alter proto structure, yet can break client logic | Preserve documented semantics; version the API when incompatible |

Example of protecting a removed field:

```proto
message Product {
  reserved 8;
  reserved "legacy_price";

  string product_id = 1;
  string display_name = 2;
}
```

This is a condensed snippet to illustrate `reserved`. In a real schema, keep all fields still in use; do not replace the entire message with this snippet. Number 8 and the name `legacy_price` may no longer be reused in `Product`.

## 10. Testing the Request/Response Contract

An integration test suite should verify the behavior clients actually observe, rather than only testing that builders can construct messages. For `CatalogService`, include at least these cases:

| Test case | Input | Expected result |
| --- | --- | --- |
| Fetch valid product | `GetProductRequest{product_id="P-100"}` | `OK`, `response.hasProduct()` is true, `product_id` matches |
| Missing identifier | `GetProductRequest{}` | `INVALID_ARGUMENT`, no success response |
| Not found | Valid ID format that does not exist | `NOT_FOUND` |
| Empty list | Filter with no matches | `OK`, zero items in `products`, no next page |
| Pagination | More records than `page_size` | Accurate page size and `next_page_token`; no omissions or duplicates under test conditions |
| Update Boolean to `false` | `update_mask.paths=["active"]` | `active` becomes `false`; fields outside the mask remain unchanged |
| Mask contains protected field | `update_mask.paths=["product_id"]` | `INVALID_ARGUMENT` |
| Stream canceled | Client cancels `WatchProductEvents` | Server stops related work and releases resources |
| Deadline exceeded | Client sets deadline shorter than processing time | Client receives `DEADLINE_EXCEEDED` or status consistent with completion/cancellation race; server handles cancellation |

For updates, retrying with the same `request_id` is only worth testing for idempotency if the contract **explicitly guarantees** it and the server actually persists deduplication state. For streaming events, also test duplicate handling, disconnects, ordering, and stream resumption according to your specific guarantees.

When a test server is running on `localhost:9090` in plaintext mode and proto files reside under `src/main/proto`, you can send a unary request:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto catalog/v1/catalog.proto \
  -d '{"productId":"P-100"}' \
  localhost:9090 shop.catalog.v1.CatalogService/GetProduct
```

The method path is `/shop.catalog.v1.CatalogService/GetProduct`; `productId` is the JSON form under ProtoJSON mapping for `product_id`. The `grpcurl` flags must match your actual port and TLS configuration—never assume every environment runs plaintext.

## 11. Self-Check Exercises

**Exercise 1 — Underspecified request.** An RPC is declared as:

```proto
rpc FindProduct(Product) returns (Product);
```

Clients only need to look up a product by its ID. How would you redesign the request/response so it is clear and prevents clients from sending irrelevant fields?

*Hint:* `GetProduct(GetProductRequest) returns (GetProductResponse)`; the request contains only `product_id`, and the response contains `Product product`. Document that a blank ID yields `INVALID_ARGUMENT`, missing resource yields `NOT_FOUND`, and a successful response must contain `product`.

**Exercise 2 — No data.** `ListProducts` finds no products in category `CAT-99`. Should it return `NOT_FOUND` or `OK` with an empty list?

*Hint:* `OK` with empty `products` and empty `next_page_token`. A list can validly have zero items even when the filter is valid.

**Exercise 3 — Updating a default value.** A product has `active = true`, and the client wants to change it to `false`. Why can sending a `Product` with `active = false` without specifying the update scope cause bugs?

*Hint:* Omitted proto3 scalars may be read as default values. If the server updates every field, other fields can be overwritten. Use `update_mask.paths = ["active"]` or an appropriate `optional`/presence model to distinguish "do not modify" from "set to false".

**Exercise 4 — Errors and responses.** If `GetProduct` cannot find ID `P-404`, should it return `GetProductResponse{product: default}` with `success = false` or gRPC status `NOT_FOUND`?

*Hint:* Use `NOT_FOUND` per the contract; do not send a fake success response. Clients can branch on status codes, while an empty list search remains a success.

**Exercise 5 — Interruptible streams.** With `WatchProductEvents`, a client receives two events with the same `event_id` after reconnecting. Can you conclude the server violated the contract?

*Hint:* Not yet. You need to check whether the API promises at-most-once, at-least-once, or a specific replay mechanism. `event_id` helps clients detect duplicates, but does not by itself prevent duplicate emission; the contract must specify resumption and deduplication behavior.

A well-defined request/response always answers: **what the client must send, which inputs are valid, what the server commits to returning, and how errors are represented**. Once those decisions are captured in the Protocol Buffers contract, Spring gRPC Java code, integration tests, and service observability all share a single consistent understanding.
