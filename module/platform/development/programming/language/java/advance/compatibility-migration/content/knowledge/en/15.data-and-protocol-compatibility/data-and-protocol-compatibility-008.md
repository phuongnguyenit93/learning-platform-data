# Protocol Between Old and New Services During Parallel Execution

In Java Advance Compatibility Migration, upgrading a service from an older JDK to a newer JDK rarely happens simultaneously across the entire system. Some instances or services still run Java 8/11, while other components have moved to Java 17/21 or a release aligned with the organization's roadmap. During a rolling update, canary, blue-green deployment, or incremental monolith extraction, **two versions may communicate with each other for days or weeks**.

If the protocol between them changes without planning, the application can fail even when each version works properly in isolation: the old side cannot read a new field; the new side misinterprets default values; an event is consumed twice; a new status code breaks old clients; or a binary rollback succeeds yet data written during parallel execution is no longer readable by the previous version.

Therefore, the **protocol between old and new services during parallel execution** is the set of contracts that must be preserved across coexisting versions: HTTP/gRPC APIs, payload formats, error codes, message schemas, event ordering and semantics, authentication and authorization, retry rules, stored data, processing timing, and deployment procedures. The goal is not to force all versions to be identical; the goal is to design changes so that supported version combinations **understand and process data according to contract**, while maintaining safe upgrade and rollback paths.

## 1. Why Run in Parallel and What Breaks Easily?

A system may run old and new versions in parallel due to:
- Rolling deployment: v1 instances are gradually replaced by v2.
- Canary: only a portion of traffic is routed to v2 to assess risk.
- Blue-green: two instance groups are ready simultaneously during traffic cutover.
- Extracting a capability from a monolith into a new microservice.
- Upgrading the JDK runtime, framework, serialization library, or message broker client service by service.
- Data migration requiring synchronization between old and new schemas.
- Supporting mobile apps, batch jobs, partners, or consumers that cannot upgrade simultaneously with the server.

In these situations, a request may traverse a chain:

~~~text
                 Gateway / Load balancer
                          |
                  +-------+-------+
                  |               |
             Orders v1        Orders v2
             (Old JDK)        (New JDK)
                  |               |
                  +-------+-------+
                          |
                     Inventory v1
                          |
                       Broker
                          |
                 Billing v1 / Billing v2
                          |
                    Shared storage
~~~

Consider not only v1 ↔ v2 of the same service, but also legacy API consumers, old/new event producers, concurrently accessed databases, caches, schedulers, and retry-handling components.

### 1.1. Multiple Types of Compatibility Coexist

| Compatibility Type | Question | Example Failure |
|---|---|---|
| **Wire format** | Can the receiver parse the bytes/payload? | JSON changes a number type to an object |
| **Schema** | Are fields, names, enum values, and field numbers still valid? | Protobuf reuses a field tag |
| **Semantic** | Do values still carry the same meaning? | `amount` changes from dong to xu without changing the contract |
| **Behavioral** | Do side effects, error codes, retries, and states honor the contract? | Retried POST creates two orders |
| **Temporal** | Are timestamps, timezones, expirations, and ordering interpreted consistently? | `LocalDateTime` treated as UTC in the new version |
| **Security** | Are authn/authz, TLS, signatures, and identity still compatible? | Old client omits a newly required claim |
| **Data/storage** | Can the old version read data written by the new version? | New DB enum value not handled by old code |
| **Operational** | Can we deploy, observe, shift traffic, and roll back? | App rolled back after DB dropped an old column |

An API that **parses successfully** does not necessarily have **compatible semantics**. For migration, explicitly describe each contract layer before modifying code.

## 2. Concepts of Backward and Forward Compatibility

Consider a producer (sender of data) and a consumer (reader/processor of data):

- **Backward compatibility**: a newer consumer version can read and process data created by an older producer version.
- **Forward compatibility**: an older consumer version can read and process data created by a newer producer version, within committed bounds.
- **Full compatibility**: both directions above are guaranteed for a specific set of changes/schemas.

These names are sometimes used with nuanced definitions in schema registries, especially when referring to reading old/new schemas. In project documentation, explicitly state **who produces the payload, who reads the payload, and which versions** rather than just writing "backward compatible" without communication direction.

### 2.1. Minimal Communication Matrix

During the coexistence phase, a typical required matrix is:

| Producer | Consumer | Objective |
|---|---|---|
| v1 | v1 | Existing running baseline |
| v1 | v2 | New version still understands old data |
| v2 | v1 | Old version does not break when receiving new data |
| v2 | v2 | New functionality works |

If producers and consumers span multiple independent services/versions, expand the matrix based on the **support window**. You do not need to test every historical combination indefinitely; test the versions actually running or supported.

For request-response, an interaction comprises **both request and response**:
- Client v1 must send requests that server v2 understands.
- Server v2 must return responses and errors that client v1 can handle.
- Client v2 sends new requests to server v1 only if the client has a fallback or capability negotiation mechanism.

A change stating only "server v2 accepts v1 requests" is not enough to prove client v1 can use server v2.

## 3. Start from the Contract, Not from Java Classes

Java classes inside a service may change across JDK/framework upgrades, but the **wire contract** must be defined independently of implementation: field names, external data types, HTTP codes, headers, auth claims, event names, schema versions, timezones, units, nullability, and business effects.

For example, a JSON response from Orders API v1:

~~~json
{
  "orderId": "ord-102",
  "status": "CREATED",
  "totalAmount": "125000",
  "currency": "VND"
}
~~~

Version v2 wants to add delivery information:

~~~json
{
  "orderId": "ord-102",
  "status": "CREATED",
  "totalAmount": "125000",
  "currency": "VND",
  "delivery": {
    "method": "STANDARD",
    "estimatedAt": "2026-11-18T09:00:00+07:00"
  }
}
~~~

Adding a field is usually a lower-risk extension than renaming or changing an existing field's type, **yet it is safe only when old consumers can ignore unknown fields** and are not bound by a published strict schema. If an old client configures its JSON deserializer to reject unknown fields, adding `delivery` can break compatibility. Therefore, do not treat "additive" as automatically compatible; confirm by testing against old binaries/clients.

### 3.1. What Should the Contract Record?

A typical contract table:

| Component | Decision to Document |
|---|---|
| Endpoint/method | `POST /orders`; order creation action |
| Request field | Name, type, required/optional, validation |
| Response field | Name, type, nullable values, defaults |
| Enum/status | Value list and how unknown values are handled |
| Number | Unit, precision, scale, rounding |
| Timestamp | UTC/offset/IANA zone, format, semantics |
| Headers | Auth, idempotency key, correlation ID, capability/version |
| Errors | HTTP status, error code, retryability, payload structure |
| Side effects | DB writes, event publishing, external service calls |
| Retry/timeout | Whether retries are allowed, which deadlines apply |
| Version window | Client/server versions to support |
| Deprecation | When old fields/endpoints retire and migration paths |

Do not leave these points existing solely as implementation details of a Java DTO or annotation inside one service.

## 4. Rules for Low-Disruption JSON/HTTP Evolution

### 4.1. Avoid Breaking Published Fields

During parallel execution, the following changes carry high risk:

- Renaming a field that an old client reads.
- Changing a `string` to an `object`, a `number` to a `string`, or an array to a singleton.
- Replacing `null` with a missing field or vice versa when consumers distinguish them.
- Making an optional field required.
- Changing units (millisecond ↔ second, dong ↔ xu) without changing the contract/version.
- Adding an enum value in a flow where old consumers use an exhaustive switch without fallback.
- Changing the error code structure or turning a retryable error into a fatal error.
- Changing pagination, sorting, or timezone without documentation.
- Renaming an HTTP header or auth requirement so old clients can no longer send requests.

A change may look "non-breaking" in Java source code while still breaking the wire/semantic contract.

### 4.2. Add Optional Fields with Explicit Defaults

Example v1 request:

~~~json
{
  "customerId": "cus-1",
  "items": [
    {"sku": "A-123", "quantity": 2}
  ]
}
~~~

Request v2 adds `deliveryPriority`:

~~~json
{
  "customerId": "cus-1",
  "items": [
    {"sku": "A-123", "quantity": 2}
  ],
  "deliveryPriority": "STANDARD"
}
~~~

For server v2 to continue accepting v1 requests, `deliveryPriority` should be optional on receipt, with a behaviorally compatible default:

~~~text
missing deliveryPriority -> STANDARD
explicit deliveryPriority -> validate allowed values
~~~

For server v1, a v2 request may be sent only if v1 can accept the new field or client v2 has an adapter stripping the field when calling v1. Otherwise, a new endpoint/version or feature negotiation may be required.

**Distinguish missing from explicit null.** For example, if `deliveryPriority` appears as `null`, the server must decide whether it means missing, "no priority set", or invalid input. Keep the rule consistent across versions.

### 4.3. Tolerant Readers Do Not Ignore Data Errors

A flexible consumer may ignore **unknown fields** while still validating:
- Types of the fields it uses.
- Enum/currency values per contract.
- Payload size and depth limits.
- Schema and signatures if the payload is protected.
- Semantics of required fields or critical validation rules.

Ignoring unknown fields **does not** mean automatically accepting any invalid payload or bypassing security checks. If a new field alters the meaning of an old field unknown to the consumer, a tolerant reader will still misprocess it.

### 4.4. Java Example with Jackson and Unknown Fields

An old Java consumer might define a DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class OrderResponseV1 {
    public String orderId;
    public String status;
    public String totalAmount;
    public String currency;
}
~~~

When reading a v2 payload with the added `delivery`, an appropriately configured Jackson version can ignore unknown fields:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public final class ReadNewOrderPayload {
    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "orderId": "ord-102",
                  "status": "CREATED",
                  "totalAmount": "125000",
                  "currency": "VND",
                  "delivery": {"method": "STANDARD"}
                }
                """;

        OrderResponseV1 result =
                new ObjectMapper().readValue(json, OrderResponseV1.class);

        System.out.println(result.orderId);
    }
}
~~~

Java text blocks require Java 15+; **if the consumer runs Java 8 or 11**, use ordinary Java strings or load fixtures from resources. This demonstrates the deserialization mechanism, not a requirement to raise the old consumer's source level. Moreover, the `@JsonIgnoreProperties` annotation must already exist in the old consumer binary before upgrading the server; you cannot edit the old class and claim that proves the released consumer is compatible.

When using other libraries such as Gson, JSON-B, Kotlinx Serialization, or custom mappers, rules for unknown fields and nullability may differ. Test **the actual old consumer artifact** rather than assuming Jackson-like behavior.

## 5. Monetary Amounts, Timestamps, and Statuses: Semantic Compatibility

### 5.1. Monetary Amounts

Do not change `totalAmount` from dong to xu while keeping the same field name/contract. Example:

~~~text
v1: "125000"  -> 125.000 VND
v2: "125000"  -> 125.000 xu?  (breaking if reinterpreted)
~~~

Publish `currency`, monetary unit, precision, rounding, whether negative values are permitted, and decimal serialization format. In Java, `BigDecimal` is usually appropriate for monetary calculations; do not use `double` to represent amounts requiring exact precision.

If the representation must change, add a new field with a distinct name/semantics, provide an adapter, and set a retirement plan for the old field. Also test edge cases: large numbers, fractional values, zero, null, unsupported currencies, and rounding.

### 5.2. Timestamps

A payload like:

~~~json
{"createdAt":"2026-11-12T09:30:00Z"}
~~~

describes an unambiguous UTC instant. A payload like:

~~~json
{"createdAt":"2026-11-12 16:30:00"}
~~~

lacks an offset/zone and thus depends on how the consumer interprets it. After Java migration, the JVM's default timezone or tzdb may change; two service versions could compute two different instants from the exact same string.

For events that have already occurred, prefer representing timestamps with an offset/UTC and document precision. For future schedules tied to local time, send local date-time together with an IANA ZoneId and a policy for DST gaps/overlaps.

### 5.3. Enums and Business States

Suppose v1 knows only:

~~~text
CREATED, PAID, CANCELLED
~~~

v2 adds:

~~~text
AWAITING_REVIEW
~~~

If v2 emits an `AWAITING_REVIEW` event to consumer v1, parsing the string into a Java enum may fail or a switch without fallback may misprocess it. Options:
- Temporarily **do not emit** the new value to consumer v1.
- Map to a v1 state with sufficiently equivalent semantics, approved by the business.
- Provide a new endpoint/topic/event type for consumers supporting the new state.
- Upgrade consumers and verify unknown-value handling before the producer emits the new value.

Do not blindly map every new state to `CREATED` if doing so could trigger incorrect billing, shipping, or business processing.

## 6. Protobuf/gRPC and Schema Evolution

In gRPC systems or binary messaging using Protocol Buffers, compatibility must be evaluated by **field number and wire type**, not just the generated Java field names.

Example v1:

~~~proto
syntax = "proto3";
package orders.v1;

message Order {
  string order_id = 1;
  string status = 2;
  int64 total_minor_units = 3;
}
~~~

An additive v2:

~~~proto
syntax = "proto3";
package orders.v1;

message Order {
  string order_id = 1;
  string status = 2;
  int64 total_minor_units = 3;
  string delivery_method = 4;
}
~~~

Key points:
- Do not reassign field numbers `1` or `2` to a different meaning.
- Do not reuse tags of deleted fields; use `reserved` for numbers/names when removing them.
- Do not assume renaming a field is always harmless, as JSON mapping, source code, and tooling may rely on names.
- Proto3 has rules for default values and presence; distinguish default values from absent fields, especially when changing contracts.
- Changing a scalar type can alter wire type or semantics; even a change that still parses on the wire can corrupt values.
- Adding enum values can leave old consumers unable to understand new values; test generated code and fallback behavior.
- gRPC **service methods**, request/response messages, metadata, status codes, and deadlines are also part of the contract.

### 6.1. Controlled Field Removal

When a field is no longer used, instead of reusing its tag for another meaning:

~~~proto
syntax = "proto3";
package orders.v1;

message Order {
  string order_id = 1;
  string status = 2;

  reserved 3;
  reserved "total_minor_units";

  string delivery_method = 4;
}
~~~

This is an example of reserving removed tags in the new schema; however, **removing field 3 can still break consumer v1 if it needs the monetary amount**, even when the parser skips the tag properly. Wire compatibility and semantic compatibility must be evaluated separately.

### 6.2. When Upgrading Proto/gRPC Libraries in Java

Upgrading the JDK may require upgrading gRPC/Netty/Protobuf versions. Check:
- Whether generated stubs and runtime libraries are compatible.
- Whether HTTP/2, TLS, ALPN, and proxies/load balancers handle traffic equivalently.
- Deadline propagation, retries, cancellation, and stream backpressure.
- Max message size, compression, metadata headers.
- Unknown fields, enums, and JSON transcoding.
- Server reflection/schema discovery if clients/tooling rely on it.

Merely keeping the proto file unchanged does not mean all transport behavior or generated Java APIs stay unchanged.

## 7. Events/Messages While Producers and Consumers Run in Parallel

With Kafka, RabbitMQ, JMS, or similar queue systems, deployment order often differs from HTTP request-response. A new producer can emit events that an old consumer reads minutes or days later, even after the new producer has already rolled back.

A v1 event:

~~~json
{
  "eventId": "evt-51",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T09:30:00Z",
  "payload": {
    "orderId": "ord-102",
    "totalAmount": "125000",
    "currency": "VND"
  }
}
~~~

A new event may add fields to `payload` or emit a different `schemaVersion`. For compatibility, define:
- Which consumers understand which event types and schema versions.
- Whether unknown fields may be ignored.
- Whether unknown event types should fail, skip, quarantine, or route to a dead-letter queue.
- How many times events are replayed or retried.
- Whether ordering guarantees exist per key/partition.
- Whether events can be duplicated, delayed, or out of order.
- Event identifiers and idempotency handling.

### 7.1. Envelope and Payload Are Two Contract Layers

Separate stable **envelope** fields for routing/observability from the business **payload**:

| Layer | Example Fields | Meaning |
|---|---|---|
| Envelope | eventId | Identify events and detect duplicates |
| Envelope | eventType | Select handler |
| Envelope | schemaVersion | Interpret payload by version |
| Envelope | occurredAt | Timestamp when the event occurred |
| Envelope | correlationId/traceId | Trace the business flow |
| Payload | orderId, amount, status | Business data of the event |

Do not treat `schemaVersion` as an automatic solution. It only tells consumers which parser/adapter to use; you still need version support rules and a schema upgrade path.

### 7.2. An Event Is Not a Command

An event like `OrderPaid` describes a fact that already happened. A command like `ChargePayment` requests an operation with side effects. During migration, resending a command can result in double payment without idempotency; replaying events must normally update materialized views or state under an idempotent policy.

Do not apply the same retry logic to both message types just because both travel over a broker.

### 7.3. Schema Registry and Compatibility Policies

If using Avro, Protobuf, or JSON Schema through a registry, configure a compatibility mode aligned with the support window. Check:
- Which direction of schema evolution the registry checks.
- Whether consumers use writer schema/reader schema automatically.
- How schema IDs are embedded into messages.
- Whether multiple historical versions or only the previous version must be supported.
- Which producers are authorized to publish new schemas and the review process.

Registry validation is useful, yet does not catch semantic breaks such as changed currency units or state meanings.

## 8. Idempotency, Retries, and Delivery Semantics

During traffic shifting across v1/v2, a timeout is easily mistaken for "request was not executed". A client may retry to another instance after the old instance already committed the transaction. Without server-side idempotency, a business command can be processed twice.

Example:

~~~text
Client ---- POST /payments ----> Payment v1
                  |
           v1 writes transaction successfully
                  |
           Response times out / is lost
                  |
Client ---- retry POST -------> Payment v2
                  |
           v2 creates transaction a second time  (wrong)
~~~

### 8.1. Define Idempotency Keys at the Business Level

For operations with side effects, the client sends a stable key for **the same business intent**:

~~~http
POST /payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: pay-request-7f4a

{"orderId":"ord-102","amount":"125000","currency":"VND"}
~~~

Both v1 and v2 must use **the same key verification mechanism**, not separate per-version in-memory caches. An idempotency contract should define:
- Key scope: by principal/tenant and which operation.
- Key retention TTL and post-expiration retry policy.
- Payload fingerprint: what to do when the same key arrives with a different payload.
- What response is returned when the request is resent.
- When the key is marked committed.
- Transaction boundary relative to actual side effects.
- How concurrent requests with the same key are handled.

A simple per-instance cache map does not guarantee correctness across rolling deployments, multiple replicas, or process crashes.

### 8.2. Database Transaction Example

An illustrative idempotency table:

~~~sql
CREATE TABLE request_dedup (
    tenant_id        VARCHAR(64) NOT NULL,
    operation_name   VARCHAR(64) NOT NULL,
    idempotency_key  VARCHAR(128) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    response_payload TEXT,
    state            VARCHAR(16) NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

The system needs transactions or appropriate concurrency control to ensure a key produces side effects only once per contract. **Creating the table alone does not guarantee exactly-once**: race conditions, multi-system commits, and external payment gateways can still cause duplicates. When calling downstream services with side effects, propagate an appropriate idempotency key or design verified sagas/compensation.

### 8.3. Event Delivery and Consumer Deduplication

In brokers with at-least-once delivery, a message can be redelivered. Consumers can store processed `eventId` values in the same transaction as state updates, or use operations that are idempotent by business key.

Conceptual example:

~~~text
Begin transaction
  if eventId already processed:
      no-op
  else:
      apply business change
      record eventId
Commit
Acknowledge message after successful commit
~~~

This is a mental model and must be adapted to the transaction semantics of the DB and broker. If ack happens before DB commit, messages may be lost; if DB commit finishes but ack fails, the message may be redelivered and must be deduplicated.

## 9. Ordering, Consistency, and State Machines

A system might receive:
 
~~~text
OrderCreated
OrderPaid
OrderCancelled
~~~

in different orders across consumers if multiple topics, partitions, services, retries, or replications are involved. When v1 and v2 use different schema/state logic, discrepancies become even harder to detect.

### 9.1. Per-Entity Ordering Instead of Global Ordering

If the broker guarantees ordering per partition, use a stable key like `orderId` so events for the same order enter the appropriate ordering scope. Understand the exact guarantees of the broker in use and how producers select partitions.

Do not assume "because the broker has queues, all events arrive in global order". Cross-partition and cross-topic traffic usually lack global ordering.

### 9.2. Aggregate/State Versioning

When consumers process state updates, you can include `aggregateVersion` or a sequence number issued by an authoritative source:

~~~json
{
  "eventId": "evt-53",
  "orderId": "ord-102",
  "aggregateVersion": 4,
  "eventType": "OrderPaid"
}
~~~

Consumers check the version to detect stale events or skipped steps. Do not assume version numbers increment sequentially if the system has multiple uncoordinated writers; define where versions are assigned and how gaps are handled.

### 9.3. Do Not Let v2 Create States That v1 Cannot Understand

During parallel execution, producer v2 may produce a new state value. If v1 instances or consumers are still routed to that entity, they may reject or misprocess it.

Control approaches:
- Temporarily disable creating the new state via a feature flag.
- Map the state to a v1 representation with approved semantics.
- Ensure entities using the new feature are processed only by v2 via affinity routing.
- Separate into a new topic/endpoint and connect only capable consumers.
- Wait until v1 is removed from all processing paths before enabling the new state.

This is an example where a **valid schema is still not enough**. Migration must coordinate data/state machines and deployment.

## 10. Shared Data: Expand–Migrate–Contract

A major risk of running in parallel is v1 and v2 accessing the same database simultaneously. An incompatible schema change can break v1 the moment v2 is deployed.

### 10.1. Expand

First add new structures in a way that keeps v1 working:
- Add nullable columns or columns with genuinely compatible defaults.
- Add new tables without dropping old tables.
- Add required indexes before enabling the feature.
- Write v2 code capable of reading the old representation.

Example:

~~~sql
ALTER TABLE orders ADD COLUMN delivery_priority VARCHAR(24);
~~~

Do not add NOT NULL immediately while v1 still inserts rows without that column. If the new data is conceptually mandatory, application v2 can apply a default on read during the transition.

### 10.2. Migrate/Backfill

Backfill historical data to the new representation in controlled batches. Check transaction sizes, locks, write amplification, replication lag, retries, and resumability. While both v1 and v2 are still writing, define synchronization rules so data does not drift.

Options include:
- Read the new column, falling back to the old column.
- Update both representations in the same transaction when in the same database.
- Use CDC or a sync pipeline with a clear owner.
- Isolate changes to a single designated writer service.

**Dual-writing across two databases or two services** without a shared transaction easily creates split states where one succeeds and the other fails. Use it only with explicitly designed reconciliation, retry/idempotency, and error handling.

### 10.3. Contract

Only after no v1 consumers remain and data/access compatibility is confirmed should you consider:
- Adding NOT NULL or new constraints.
- Dropping old columns/tables.
- Removing fallback reads.
- Discontinuing v1 fields/endpoints/events.

The contract phase is **the point at which rolling back to v1 may no longer be safe**. Require a clear release decision, backup/restore plan, and proof that no old consumers remain.

### 10.4. Illustrative Timeline

~~~text
T0  DB schema v1, App v1
 |
T1  Expand schema, App v1 still runs
 |
T2  Deploy App v2 (reads old/new), App v1 + v2 in parallel
 |
T3  Backfill and reconcile; emit compatible events
 |
T4  Disable writes on old path; confirm no v1 remains
 |
T5  Contract schema and retire old adapters/fields
 |
T6  End compatibility window
~~~

The T2–T4 interval is when data inconsistencies and complex rollbacks are most likely; monitor it closely.

## 11. API Versioning and Capability Negotiation

### 11.1. Additive Changes May Not Need a New URL Version

If v2 only adds optional fields that clients are proven able to ignore, you can keep `/orders` during the support window. However, when semantics change fundamentally, explicitly separating versions usually protects existing consumers.

Common strategies:
- Path versioning: `/v1/orders`, `/v2/orders`.
- Media type/version header.
- Protocol schema/service package versioning.
- Separate event types or topic versions.
- Capability negotiation via headers/handshake when needed.

There is no single versioning scheme right for every system. What matters is that **a version represents a supported contract**, not merely the deployed JVM version.

### 11.2. Capabilities Instead of Guessing from the Java Version

A client can send an explicit capability list:

~~~http
GET /orders/ord-102 HTTP/1.1
Accept: application/json
X-Client-Capabilities: delivery-status-v2
~~~

The server sends the new representation only when permitted by contract. This is an **application-specific design example**, not a standard HTTP header automatically understood by every framework. If used, specify its parsing, validation, security, and fallback.

Do not rely on User-Agent or the client's JDK version as definitive proof of which schema the client understands. Two applications both running Java 17 can support two different contract versions.

### 11.3. Anti-Corruption Layer/Adapter

When v1 and v2 have different business models, you can place an adapter at the boundary:

~~~text
Client v1  ->  V1 API adapter  ->  Domain model v2
Client v2  ->  V2 API adapter  ->  Domain model v2
~~~

The adapter is responsible for translating:
- Field names and value representations.
- Status/error codes.
- Monetary units and timestamps.
- Request validation semantics.
- Return payloads compatible with old clients.

Do not turn the adapter into a place that silently fixes every error or translates states that have no equivalent. For cases that cannot be mapped safely, require a new version, reject with clear errors, or schedule consumer migration.

## 12. HTTP, TLS, Authentication, and Protocol Errors

When upgrading the JDK, the networking stack may change at the same time: HTTP clients, TLS defaults, certificate trust, HTTP/2, cipher suites, or serialization libraries. An API with an unchanged JSON schema can still fail to connect.

### 12.1. Error and Retry Contracts

Example of a stable error response:

~~~json
{
  "errorCode": "ORDER_NOT_FOUND",
  "message": "Order does not exist",
  "retryable": false,
  "requestId": "req-7a1"
}
~~~

If v2 changes `ORDER_NOT_FOUND` to `NOT_FOUND` and client v1 checks the string, the old client can misinterpret it. If v2 changes 409 to 500, the client might retry a request that should not be retried.

Define:
- HTTP status + machine-readable error code.
- Whether retries are allowed, after how long, and whether to reuse the idempotency key.
- Whether 429/503 includes `Retry-After` or an equivalent rate-limit contract.
- Deadline/timeout and cancellation semantics.
- Safe error payloads without leaking stack traces/secrets.

### 12.2. TLS and Identity

Before canarying, check:
- TLS versions/cipher suites supported by both sides per security policy.
- Certificate chains, hostname validation, truststores, and certificate rotation.
- mTLS identity if used.
- Token formats, claims/roles/audiences, and token lifetimes.
- Old clients do not have to disable certificate validation to connect.
- New services do not drop authorization checks for compatibility.

In particular, **do not weaken security** to support old clients that no longer meet minimum requirements. When secure communication is impossible, use separate endpoints, policy-enforcing gateways, or an explicitly communicated deprecation schedule.

### 12.3. Java Object Serialization Is Unsuitable as a Default Wire Contract

Using `ObjectOutputStream`/`ObjectInputStream` directly between services creates tight coupling across class names, `serialVersionUID`, class loaders, and object graphs. This makes JDK/library migration hard to control and introduces deserialization risks when receiving untrusted data.

If the system currently uses Java native serialization in caches/RMI/messages:
- Inventory remaining usages and trust boundaries.
- Do not accept untrusted serialized objects without appropriate safeguards.
- Evaluate object input filtering while support is still needed.
- Plan migration to explicit schema contracts such as JSON/Protobuf/Avro per use case.
- Migrate stored/replay data as well and verify compatibility before disabling the old format.

## 13. Traffic Routing When v1 and v2 Run Together

### 13.1. Canary and Weighted Routing

A common approach is routing 1%, 5%, 25%, and then 100% of traffic to v2. However, **merely counting successful requests is not enough**. If requests have side effects and a new state machine, an entity might be handled alternately by v1 and v2.

Techniques:
- Route by a stable hash of tenant/account/order ID.
- Session/entity affinity when needed.
- Enable v2 features only for targeted tenant cohorts.
- Canary read-only endpoints before opening write paths.
- Separate queues/consumer groups to avoid processing the same command twice.

### 13.2. Shadow Traffic and Its Limitations

Shadow traffic mirrors requests to v2 to observe outputs without serving live responses. **Never send shadow writes to production resources with side effects** unless a designed sandbox or dry-run mechanism is in place.

For read endpoints:
- Compare v1/v2 responses after normalizing non-deterministic fields.
- Restrict and mask sensitive data.
- Verify whether shadow requests increase DB load or trigger indirect side effects.

For write endpoints:
- Use synthetic data or an isolated environment to reproduce.
- If running dual-execution with side effects, design explicit idempotency, ownership, and compensation; do not assume "shadow" is automatically safe.

### 13.3. Blue-Green and Consumers Outside the Load Balancer

Shifting traffic at the gateway does not guarantee all v1 consumers have vanished. There may still be:
- Batch jobs calling APIs directly.
- Un-upgraded mobile clients.
- Partner integrations.
- Legacy scheduled retries.
- Events in brokers with long retention periods.
- Replayable dead-letter queues.
- Caches retaining old payloads/schemas.

Do not remove the v1 contract right after the gateway dashboard shows 100% traffic on v2. Check all communication paths.

## 14. Cross-Version Contract Testing

The goal is to prove each supported combination using **real artifacts and configurations**, not only assumption-based mocks.

### 14.1. Consumer-Driven Contract Tests

Consumers can publish contract tests describing the requests/responses they actually rely on. Provider v2 runs those tests to confirm it still serves consumer v1. For events, also run producer/consumer contracts and schema registry validation in the actual data direction.

Note: contract tests typically verify a subset of observable behavior and do not prove transaction semantics, ordering, retries, or security. Add integration/end-to-end tests as well.

### 14.2. Using the Old Consumer Binary

In Java migration, do not recompile the old consumer against new dependencies if the goal is to prove the already-released consumer binary still works. For HTTP/message APIs, preserve:
- The actual client binary and config or release image.
- The client's serializer/deserializer library version.
- The client's request fixtures and expected behavior.
- The client's JDK within the supported range.

Then let the old client communicate with server v2. If client code must be modified to pass, that is a separate client migration, no longer proof that server v2 is compatible with the old client.

### 14.3. Practice Matrix

| Client/Producer | Server/Consumer | Scenario |
|---|---|---|
| Client v1 | Service v1 | Baseline order creation/retrieval |
| Client v1 | Service v2 | Old request + new response |
| Client v2 | Service v1 | Feature fallback or version negotiation |
| Client v2 | Service v2 | New functionality |
| Event producer v1 | Consumer v2 | Parse/process old events |
| Event producer v2 | Consumer v1 | Unknown field/status/schema behavior |
| Data writer v2 | Reader v1 | Rollback-read test on expanded schema |
| Retry to v1/v2 | Shared idempotency store | No duplicate side effects |

### 14.4. Failure Scenarios to Test

- Unknown fields and missing optional fields.
- Null/empty, numeric boundaries, and precision.
- New enums/statuses.
- Timestamps with varying offsets and DST date/times.
- Message duplication, delayed delivery, out-of-order events.
- Timeouts after the server has committed.
- Error codes and retry policies.
- Old/expired/claim-missing tokens and mTLS rotation.
- Consumer unable to reach schema registry/broker.
- Code rollback when the database already contains rows from v2.
- Startup with the planned JDK version, JSON/proto library, and HTTP/TLS stack.

Do not edit expected fixtures just to make tests pass when v2 output differs. Classify which differences are acceptable contract changes and which are breaking.

## 15. Observability During Parallel Operation

A v2 canary may raise no exceptions yet still cause business errors: mismatched totals, skewed delivery times, extra events, or elevated retry counts.

### 15.1. Attach Version and Correlation Metadata

At minimum, each request/event/trace should include:
- Service name and deployment version.
- Protocol/schema version or capability when applicable.
- Correlation/request ID and trace ID.
- Operation name and outcome.
- Retry count, queue lag, deduplication outcome.
- Runtime/JDK version when needed to investigate post-migration differences.

Do not put raw tokens, secrets, full PII, or financial payloads into metric labels or logs. High-cardinality labels like user/order IDs can also cause cardinality explosion in monitoring.

### 15.2. Key Metrics

| Metric | What to Monitor |
|---|---|
| Request success/error rate by version | Whether v2 produces more errors than v1 |
| Latency p50/p95/p99 by operation/version | Any regressions from JDK/framework/serialization |
| 4xx/5xx and error codes | Contract mismatch vs auth/rate-limit issues |
| Serialization/deserialization failures | Unknown fields, enums, schema, malformed payloads |
| Consumer lag/DLQ size | Whether new consumers stall or reject events |
| Retry/duplicate/idempotency hits | Indicators of side effects or timeouts |
| Data reconciliation mismatches | Whether v1/v2 write/read differing results |
| Auth/TLS failures | Old clients failing to connect securely |
| Business invariants | Orders paid once, accurate totals, no invalid state transitions |

When comparing versions, adjust for cohort/traffic mix. A canary serving only low-risk cohorts can look healthier in metrics without representing full production traffic.

### 15.3. Define Rollout Stop Criteria

Pre-define:
- What error rate or latency threshold above baseline halts the rollout.
- Acceptable reconciliation mismatch count.
- Whether any duplicate payment/order incident occurred.
- Maximum allowable consumer lag increase.
- When to shift traffic back to v1.
- When writes must stop and data be repaired prior to rollback.

A canary without clear decision thresholds is merely percentage-based traffic shifting, not a risk-reduction strategy.

## 16. Rollback Is Not Just Reverting to the Old JAR

Rolling back an application is a deployment action. Rolling back **behavior and data** requires more conditions.

Suppose v2 wrote an `AWAITING_REVIEW` status that v1 does not understand, or dropped a column v1 requires. Even if the load balancer routes all traffic back to v1, the system can still fail.

Determine:
- Can v1 still read every row v2 may write during the coexistence window?
- Does the broker still contain v2 events that consumer v1 cannot process?
- Does the cache hold v2 representations?
- Is there a feature flag preventing v2 from creating new state/data while rollback remains necessary?
- Can writes be disabled or reverse backfill/reconciliation performed?
- After the old schema contract is removed, is rollback still within supported scope?

### 16.1. Rollback Window and Point of No Return

Before rollout, publish milestones:
1. **Rollback-safe:** schema expanded and v2 has not yet written incompatible data.
2. **Guarded rollback:** v2 has written new data, yet adapters/reconciliation allow v1 to read it.
3. **Forward-only:** old columns/endpoints/schemas were dropped or data semantics can no longer be safely reversed.

Do not let a forward-only point appear silently inside a migration script. Require explicit release/operational approval, backups, and a proper recovery plan.

## 17. Recommended Rollout Process

### Phase A: Prepare Contracts

1. Inventory requests/responses, events, DBs, caches, and partner protocols.
2. Lock down the support window: which client/service versions remain active.
3. Identify which changes are additive and which break contracts.
4. Document schemas, errors, retries, idempotency, timestamps, and security semantics.
5. Write contract tests and fixtures using the released v1 binaries.

### Phase B: Expand and Bidirectional Compatibility

1. Add v1-compatible fields/DB schemas.
2. Deploy new consumers able to read old data.
3. Ensure the new producer does not yet emit fields/states unhandled by v1, or provide adapters/versioned routes.
4. Configure shared idempotency, event deduplication, and monitoring.
5. Validate the v1/v1, v1/v2, v2/v1, and v2/v2 matrix per support policy.

### Phase C: Canary/Parallel Run

1. Deploy v2 partially using stable cohort-based routing.
2. Use read-only shadow traffic if appropriate; never shadow-write indiscriminately.
3. Monitor contract failures, DB consistency, latency, and business metrics.
4. Test timeout/retry, duplicate, and rollback-read scenarios in a controlled environment.
5. Halt or roll back according to approved thresholds.

### Phase D: Full Cutover

1. Ramp up v2 traffic in stages.
2. Verify no v1 producers/consumers remain on paths to be retired.
3. Wait for relevant event/retry/DLQ retention periods to expire, or handle them via adapters.
4. Backfill/reconcile and verify invariants.
5. Only afterward drop old fields/schemas/endpoints and apply new constraints.

### Phase E: Conclude Migration

1. Remove end-of-life adapters/feature flags once safe.
2. Update versioning, API documentation, and client SDKs.
3. Pin verified JDK/runtime/images and dependencies.
4. Archive contract test evidence, deployment history, reconciliation, and rollback decisions.
5. Maintain CI checks to prevent breaking changes during the next support window.

## 18. Design Exercise: Migrating Orders v1 to v2

**Context:** Orders v1 runs on JDK 11; partner v1 clients still send `POST /orders` and read statuses `CREATED/PAID/CANCELLED`. Orders v2 upgrades to JDK 21, adding delivery priority and the `AWAITING_REVIEW` status. The system uses HTTP/JSON, Kafka, and a shared database.

**Requirements:** Both versions must run in parallel for at least one release cycle, and rollback to v1 must remain possible if the canary fails.

### 18.1. Unsafe Design

- Deploy v2 and immediately require `deliveryPriority` on requests.
- v2 emits `AWAITING_REVIEW` in existing events.
- v2 switches `totalAmount` to smaller currency units without renaming the field.
- v2 alters the `status` column to a DB enum understood only by v2 code.
- Retries exist, yet idempotency keys are stored only in-memory.
- After one day, drop the v1 endpoint and old columns.

These steps break HTTP, event, semantic, DB, and rollback contracts simultaneously.

### 18.2. Controlled Transitional Design

1. Keep old requests valid, defaulting `deliveryPriority=STANDARD` in v2.
2. Defer emitting `AWAITING_REVIEW` until all consumers in the support window handle it, or emit it on a separate contract/event version.
3. Keep `totalAmount` and `currency` with old semantics; if a new format is needed, add a versioned field.
4. Expand the DB first; do not enforce the new column while v1 still creates orders.
5. Both v1 and v2 share the same idempotency store and event deduplication policy.
6. Enable new features by cohort with routing affinity if v1 does not recognize the new state.
7. Run the client/service/event matrix and rollback-read tests.
8. Contract the DB/API only after v1 consumers have stopped or reliable adapters are in place.

### 18.3. Illustrative Acceptance Criteria

- Released client v1 binary can call Orders v2.
- Orders v2 processes v1 requests and returns responses matching the v1 contract.
- Events emitted by v2 during canary are safely processed by supported v1 consumers.
- Retries from v1 to v2 do not create duplicate orders/payments.
- Data written by v2 during the rollback window remains readable by v1 or has a verified recovery procedure.
- No regressions in TLS/auth, timestamps, or business invariants.
- Version-tagged logs/metrics and clear rollback decision thresholds are in place.

## 19. Common Mistakes During Parallel Execution

- **Testing only v2 against v2:** neglecting old clients and event replay.
- **Assuming adding a field is always compatible:** strict consumers may reject unknown properties.
- **Changing semantics while keeping the same field name:** parsing succeeds yet amounts, times, or states are wrong.
- **Adding enum values too early:** v1 fails to parse or misprocesses them.
- **Not sharing idempotency:** retries across v1/v2 instances create duplicate side effects.
- **Mistaking at-least-once for exactly-once:** messages can be reprocessed.
- **Dual-writing without reconciliation:** long-term data drift.
- **Shifting traffic only at the gateway:** batch jobs, partners, mobile apps, and event consumers still use the old contract.
- **Enabling v2 features immediately upon deploying v2:** new data can break rollback.
- **Assuming shadow traffic is always harmless:** shadow writes can trigger side effects.
- **Confusing UTC and local time:** new JDK/tzdb or default zone shifts timestamps.
- **Skipping TLS/auth testing on the new JDK:** payloads match yet connections fail.
- **Rolling back code after dropping schema:** v1 can no longer read data.
- **Measuring only HTTP errors:** missing business invariants, message lag, and duplicate transactions.
- **Retiring old endpoints on the server's release schedule:** external consumers may not upgrade at the same time.
- **Versioning solely by JDK version:** JVM release is not a contract version.

## 20. Checklist Before Ending the Coexistence Window

- [ ] Listed all clients/producers/consumers still within the support window.
- [ ] Established clear contracts for requests, responses, events, errors, retries, and security.
- [ ] Verified required v1→v1, v1→v2, v2→v1, and v2→v2 directions.
- [ ] Preserved semantics of existing fields: units, precision, nullability, timezone, and status.
- [ ] Unknown fields/enums/schema versions have policies and corresponding tests.
- [ ] Checked actual JDK/runtime/client library versions, not only new source code.
- [ ] Idempotency and deduplication operate across all instances/versions.
- [ ] Event ordering, replay, retries, and DLQs have been verified.
- [ ] If sharing a database, expanded schema allows v1 and v2 to operate together.
- [ ] Backfill/dual-write has reconciliation and partial-failure handling.
- [ ] Routing/canary/feature flags do not create state misunderstood by the other version.
- [ ] Shadow traffic causes no unintended production side effects.
- [ ] TLS, authn/authz, mTLS/tokens, and sensitive data remain protected.
- [ ] Metrics/logs/traces tagged by deployment/schema version, without logging secrets/PII indiscriminately.
- [ ] Canary stop thresholds and rollback runbook with concrete data conditions are ready.
- [ ] Confirmed no v1 consumers remain or adapters exist before contracting schemas/APIs.
- [ ] Drained/processed remaining events, retries, and replays before dropping old schemas.
- [ ] Collected contract test, integration test, and business invariant evidence on the target JDK.

## 21. Conclusion

Running old and new services in parallel during Java migration is not merely a problem of deploying two JARs or two containers. It is a problem of **maintaining contracts over the wire and at data boundaries** between independent versions. For safe migration, control schema readability, field semantics, error codes, authorization, idempotency, event delivery, database evolution, and rollback capability.

A practical roadmap is **contract-first → expand → bidirectional compatibility → canary/parallel run → reconcile → contract**. Throughout the support window, test actual old consumers/producers against the new service, avoid emitting incomprehensible or un-rollbackable data, monitor business invariants, and remove old contracts only when there is evidence that all relevant consumers have transitioned. As a result, upgrading a JDK or framework can proceed incrementally without disrupting communication across still-running components.