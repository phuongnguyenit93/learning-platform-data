# Versioned Services and Versioned Messages

## 1. Why Version Services and Messages?

In **SPRING_GRPC**, Protobuf schemas define the requests, responses, and services that clients and servers use to communicate. Some changes only need a new field or RPC while keeping the existing contract intact. However, when a change causes old clients to misinterpret data, fail to call a method, or be unable to express new requirements, a clear version boundary is needed.

**Versioned services** and **versioned messages** allow multiple generations of an API to coexist during a transition period. Old clients keep calling the v1 contract; new clients use the v2 contract; the server can register both and translate data to the same application/domain service.

Versioning affects the Protobuf package and fully-qualified message names, full gRPC method names, generated Java classes/stubs, `Any` type URLs, reflection, schema registries, JSON/gateway mappings, health checking, authorization, metrics, tracing, and rollout plans.

This lesson focuses on designing v1 and v2 packages/services/messages, deciding when to create a new version, running two versions side by side, and testing compatibility when clients and servers upgrade at different times.

## 2. Distinguishing Service Version from Message Version

A gRPC API typically consists of services, RPC methods, and request/response messages. These components are related yet carry distinct identifiers:

| Component | Example | Role |
| --- | --- | --- |
| Protobuf package | `commerce.orders.v1` | Namespace for services, messages, and enums |
| Service | `OrderService` | Group of RPCs registered by the server |
| RPC method | `CreateOrder` | Operation invoked by the client |
| Request/response message | `CreateOrderRequest`, `OrderReply` | Data structures passed in and out |
| Java package | `com.acme.orders.v1` | Namespace of generated Java code |

In a common design, a versioned package such as `commerce.orders.v1` holds the services and messages for API v1. When a breaking change occurs, you create `commerce.orders.v2` with the corresponding services and messages.

The full method name of an RPC is built from the protobuf package, service name, and method name:

```text
/commerce.orders.v1.OrderService/CreateOrder
```

If the package moves to `commerce.orders.v2`, the RPC path changes as well:

```text
/commerce.orders.v2.OrderService/CreateOrder
```

Client v1 will not automatically call the v2 method path simply because the service and method names match. The server must register the exact service descriptor requested by the client.

## 3. Designing v1 and v2 Packages

Example v1 API:

```proto
syntax = "proto3";

package commerce.orders.v1;

option java_multiple_files = true;
option java_package = "com.acme.orders.v1";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (OrderReply);
  rpc GetOrder(GetOrderRequest) returns (OrderReply);
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
}

message GetOrderRequest {
  string order_id = 1;
}

message OrderLine {
  string product_id = 1;
  int32 quantity = 2;
}

message OrderReply {
  string order_id = 1;
  OrderState state = 2;
  int64 total_cents = 3;
}

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;
  ORDER_STATE_REJECTED = 3;
}
```

When v2 needs an idempotency key, a currency-aware money message, and a revised line-item structure, a new contract can be introduced:

```proto
syntax = "proto3";

package commerce.orders.v2;

option java_multiple_files = true;
option java_package = "com.acme.orders.v2";

import "google/protobuf/timestamp.proto";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (OrderReply);
  rpc GetOrder(GetOrderRequest) returns (OrderReply);
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated LineItem items = 2;
  string idempotency_key = 3;
}

message GetOrderRequest {
  string order_id = 1;
}

message LineItem {
  string product_id = 1;
  int32 quantity = 2;
  string fulfillment_group = 3;
}

message Money {
  int64 units_minor = 1;
  string currency_code = 2;
}

message OrderReply {
  string order_id = 1;
  OrderStatus status = 2;
  Money total = 3;
  google.protobuf.Timestamp created_at = 4;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_REJECTED = 3;
  ORDER_STATUS_CANCELLED = 4;
}
```

Here, the protobuf package, Java package, and service/message names are versioned consistently. Both generated APIs can share simple class names like `OrderReply`, while their fully-qualified Protobuf types and Java class packages remain distinct.

Do not create a v2 merely because of a new deployment. If a change only adds fields with unused numbers and safe defaults/fallbacks, you can usually extend the v1 contract. Create a new version when a change breaks compatibility or requires different semantics/API surfaces that cannot be safely evolved within v1.

## 4. When Is a New Version Needed?

Evaluate wire, source, JSON, and behavioral compatibility together:

| Change | Can usually stay in v1? | Notes |
| --- | --- | --- |
| Adding a new field with unused number | Yes, if defaults and semantics are safe | Old clients skip field; old servers ignore new request field |
| Adding a new RPC method | Usually yes | Server must deploy the method before new clients call it |
| Adding an enum value | Can keep wire compatibility | Old clients must handle unknown values; do not assume semantic understanding |
| Deleting a field currently in use | Should not be done directly | Requires deprecation, migration, and reserving number/name |
| Changing field type/semantics | Usually needs v2 or a new field | Same wire type can still misinterpret data |
| Changing package/service/method identity | Creates new RPC/type identity | Old clients call the old path |
| Incompatible request/response restructuring | Should create v2 | Retain v1 for old consumers during transition |

Versions should not be bumped for every minor tweak. If the package changes every time a compatible field is added, API surface area and operational overhead grow rapidly. Keep v1 for policy-compliant compatible extensions; create v2 for intentional contract-breaking changes.

A new enum value can be wire-compatible yet behaviorally breaking for clients using a `switch` without a fallback. A new field may parse cleanly yet break business logic if old servers ignore a field that new clients consider mandatory. Versioning decisions must account for real consumers, not just compilation results.

## 5. Protobuf Package Differs from Java Package

`package` in a proto file determines Protobuf fully-qualified names and helps construct the RPC full method name. `option java_package` only controls the Java package of generated classes.

Example:

```proto
package commerce.orders.v2;

option java_package = "com.acme.generated.orders";
```

If you only change `java_package`, binary message field tags and the gRPC method path remain intact, provided the protobuf package, service, and RPC names stay unchanged. However, Java source consumers may fail to compile because generated classes moved packages.

If you change the protobuf package from v1 to v2 while keeping `java_package` unchanged, the RPC path and fully-qualified message names still change even though the Java package did not. Both versions of generated classes can also collide in the same Java package if message names match; assign separate Java packages per version so both can be used side by side easily.

Never use `java_package` to version a gRPC endpoint. Clients invoke RPCs using the Protobuf service descriptor, not the Java package name.

## 6. Versioned Messages and Type Identity

A message has a fully-qualified name such as `commerce.orders.v1.OrderReply`. When creating v2, the new type is named `commerce.orders.v2.OrderReply`.

The binary payload of an ordinary message mainly contains field tags and values; the fully-qualified message name is not repeated inside each payload. If v1 and v2 share similar field layouts, bytes may parse under both descriptors in some cases. However, that **does not make the two messages the same type contract**.

Type identity is used by descriptors/reflection and dynamic message APIs; `google.protobuf.Any`, where the type URL embeds the message name; Protobuf JSON for `Any`; schema registries; event stores; data catalogs; validation tooling; and generated Java classes.

For example, an `Any` carrying type URL `type.googleapis.com/commerce.orders.v1.OrderReply` does not automatically transform into `commerce.orders.v2.OrderReply`. A v2 consumer needs to resolve the v1 type or run an explicit conversion step.

If persisted data relies on `Any`, descriptors, or type URLs, retain the v1 schema and the ability to resolve the old type for as long as that data exists. Do not delete v1 merely because v1 RPC traffic has stopped.

## 7. Should a v2 Service Use v1 Messages?

Technically, a service in package v2 can import and use messages from package v1:

```proto
syntax = "proto3";

package commerce.orders.v2;

import "commerce/orders/v1/order_messages.proto";

service OrderService {
  rpc GetOrder(commerce.orders.v1.GetOrderRequest)
      returns (commerce.orders.v1.OrderReply);
}
```

This can work if the messages genuinely represent a stable contract that does not change between the two service versions. Yet it creates an explicit coupling: the v2 API continues to carry v1 type identities. Consumers and tooling must be aware of that.

Do not reuse v1 messages solely to avoid writing new messages when semantics have diverged. Doing so locks v2 into v1's constraints and can mislead users into thinking requests/responses were upgraded.

There are three options:

1. **Reuse v1 messages:** only when structure and semantics are unchanged, and depending on v1 types is intentional.
2. **Create v2 messages:** when fields, presence, validation, or semantics have changed; translation between versions lives in adapters.
3. **Create an unversioned shared package:** only for genuinely stable types with an independent lifecycle managed as their own contract. Avoid dumping every message into a `common` package just to reduce duplication.

Prioritize clear contracts and independent lifecycles over eliminating every duplicated declaration line.

## 8. A Server Can Serve v1 and v2 Simultaneously

During migration, a single server can register two service implementations generated from two different packages:

```java
Server server = ServerBuilder.forPort(port)
    .addService(new OrderServiceV1Adapter(orderApplicationService))
    .addService(new OrderServiceV2Adapter(orderApplicationService))
    .build();
```

Adapter class names are illustrative. Each adapter implements the service base class generated from its respective contract.

Both adapters should call the same application/domain service instead of duplicating business logic. An adapter is responsible for converting v1 or v2 requests into commands/domain inputs; enforcing contract-specific validation and rules; translating domain results into version-appropriate responses; mapping domain errors to suitable gRPC statuses; and preserving version-specific semantics where they differ.

For example, v1 has `total_cents` while v2 has `Money`; both adapters can accept the same domain amount and convert it into their respective response types. If currency is absent in a v1 domain model, do not guess a currency when building a v2 response; rely on an explicit data source or business rule.

## 9. Mapping Between Message Versions and the Domain Model

Do not use generated Protobuf messages as the core domain model when multiple API versions have differing semantics. An application service can accept internal commands and return domain results:

```java
public interface OrderApplicationService {
    OrderResult createOrder(CreateOrderCommand command);
    OrderResult getOrder(String orderId);
}
```

The v1 adapter translates old requests into commands:

```java
CreateOrderCommand command = new CreateOrderCommand(
    request.getCustomerId(),
    mapV1Lines(request.getLines()),
    null
);

OrderResult result = applicationService.createOrder(command);
```

The v2 adapter translates new requests:

```java
CreateOrderCommand command = new CreateOrderCommand(
    request.getCustomerId(),
    mapV2Items(request.getItems()),
    request.getIdempotencyKey()
);

OrderResult result = applicationService.createOrder(command);
```

This illustrates the mapping; actual command/result types depend on your domain model. Decide explicitly how to handle v2 fields like an idempotency key when v1 requests lack that field. You might apply a default policy, derive an internal key under a documented rule, or disallow that feature over v1. Never fabricate fake values that could compromise correctness.

Separating adapters allows a version to be deprecated without forcing the domain service to change. Furthermore, testing adapters independently protects the mapping between contracts and business logic.

## 10. Safe v1/v2 Rollout

A standard sequence rolls out reading/receiving capability first, then migrates consumers:

1. **Inventory v1:** identify clients, servers, batch jobs, gateways, event consumers, and stored data using v1 packages/types.
2. **Freeze the v1 contract:** accept only policy-compliant compatible changes; never reuse field/enum numbers.
3. **Design v2:** create new packages/services/messages, documenting differences and mappings.
4. **Deploy dual-registered servers:** new servers serve both v1 and v2.
5. **Update infrastructure:** ensure health checking, authorization, interceptors, routing, service configs, reflection, metrics, and tracing recognize both versions.
6. **Test both APIs:** old clients call v1; new clients call v2; verify semantics and errors.
7. **Roll out v2 clients in cohorts:** gradually migrate consumers, monitoring errors and rollback readiness.
8. **Measure v1 traffic:** use metrics broken down by full method name to identify consumers still calling v1.
9. **Deprecate v1:** announce timelines, owners, and retirement criteria.
10. **Conditionally remove v1:** only when no traffic, stored-data dependency, or committed consumer support remains.

If v2 clients need to send requests with new semantics, servers must support v2 before clients send them. In rolling deployments, every replica able to receive traffic must register the v2 service before v2 clients are enabled.

## 11. Integrations to Update When Adding a Version

Adding a v2 service is more than adding generated classes. Check every component using service names, method paths, or message FQNs:

| Component | What needs updating |
| --- | --- |
| Server registration | Register both v1 and v2 during transition |
| gRPC health checking | Register health status for each supported service name |
| Authorization/interceptors | Allow v1/v2 full method names per policy |
| Service config/retry | Check whether method configs match the new path |
| Reflection | Expose required service descriptors |
| Gateway/transcoding | Add v2 routes and mappings |
| Metrics/tracing | Track versions separately; update dashboards/alerts |
| Any/type registry | Retain resolvers for both old and new message FQNs |
| Schema registry/CI | Compare each package/version against its proper baseline |
| Data stores/event consumers | Read and migrate v1 payloads when needed |

Do not merge v1 and v2 metrics into a single label if you need to see which consumers still use the old API. Avoid placing arbitrary type URLs or unbounded values into high-cardinality metric labels; choose bounded version/service labels.

## 12. Testing Versioned Services and Messages

A test suite should include:

| Test | What to verify |
| --- | --- |
| v1 client → dual-registered server | Full v1 method path continues to be served |
| v2 client → dual-registered server | Full v2 method path works |
| v1 message fixture → v1 parser | Old data reads accurately |
| v1 payload → adapter/domain | Old mapping preserves semantics |
| v2 request → adapter/domain | New fields are validated and processed accurately |
| v2 response → v2 client | Type identity and mapping are correct |
| Any v1/v2 | Old/new type URLs resolve as planned |
| Health/auth/reflection | Each service version is exposed and protected properly |
| Rollback | Clients reverting to v1 during a v2 incident can still call the v1 service |

Example verifying full method names:

```java
assertEquals(
    "commerce.orders.v1.OrderService/CreateOrder",
    OrderServiceGrpc.getCreateOrderMethod().getFullMethodName()
);

assertEquals(
    "commerce.orders.v2.OrderService/CreateOrder",
    com.acme.orders.v2.OrderServiceGrpc
        .getCreateOrderMethod()
        .getFullMethodName()
);
```

Generated Java class names depend on `java_package`; the example above assumes the two versions use separate Java packages. Beyond descriptor tests, run integration tests against a real server to confirm both services are registered and handle requests.

CI should run linting and breaking checks separately against each version's baseline. Adding v2 is no excuse to delete the v1 baseline or skip compatibility checks for v1 while v1 remains supported.

## 13. Deprecation and Retiring v1

An old version should only be removed once there is evidence consumers have migrated. A deprecation process must define deprecation start and target sunset dates; an owner responsible for communication; metrics proving v1 traffic has reached zero or remaining callers have been addressed; an inventory of batch jobs, external integrations, and slow-releasing clients; whether stored data, backups, and events containing v1 message FQNs/`Any` still need to be read; and a rollback plan if missed consumers surface.

Removing the v1 RPC and deleting the v1 schema from the repository are two separate decisions. A server can stop accepting v1 RPCs while still needing the v1 schema to read historical events or decode `Any` payloads. Only delete schemas and tooling once data lifecycles and contracts permit.

## 14. Review Checklist

- New version is created because contract changes genuinely require a new boundary.
- v1/v2 packages follow consistent conventions and full service method names are identified.
- v2 messages are created when semantics/structure changed; v1 messages are not reused merely to save code.
- `java_package` is managed independently from the protobuf package.
- Field numbers and enum numbers within each message/version are kept stable; removed numbers are never reused.
- `Any`, descriptors/reflection, and JSON mapping have been evaluated if used.
- Server can dual-register v1/v2 during the transition period.
- Adapters translate each version to the domain model with clear fallbacks and validation.
- Health, auth, retries, gateways, metrics, and tracing are updated.
- Integration tests cover old/new clients and rollback.
- CI breaking checks run against the right baseline for each version.
- Deprecation has an owner, traffic metrics, and sunset criteria.

With **SPRING_GRPC**, versioned services and versioned messages establish clean boundaries for API changes that cannot evolve safely within the old contract. The Protobuf package determines type identity and shapes the RPC path; the Java package determines the namespace of generated code. Keeping v1 and v2 coexisting through adapters, rolling out servers before clients, testing both RPC paths and message mappings, and retiring v1 only after old consumers and stored data are handled lets the system evolve without disrupting active clients.
