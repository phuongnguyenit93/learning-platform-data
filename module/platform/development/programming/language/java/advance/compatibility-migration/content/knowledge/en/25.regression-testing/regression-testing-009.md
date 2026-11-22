
# Testing Multiple Service Versions Operating Together

Upgrading Java in a distributed system usually cannot be done by stopping all services, replacing all JARs at once, and then restarting them. In practice, multiple versions of **the same service** and **dependent services** can operate concurrently during rolling deployments, canary releases, blue–green deployments, rollbacks, or when a group of consumers has not yet been upgraded.

For example, while upgrading a service from JDK 11 to JDK 21, one replica running the old version and another replica running the new version may serve requests at the same time. A client deployed the day before continues calling the new API. An old consumer still reads events produced by the new producer. Old and new applications access the database concurrently during a schema transition phase. An old worker reads a job written to the queue by a new worker. If you only test that **each version runs fine on its own**, bugs that only surface in a mixed-version state will be missed.

This lesson in *Java Advance Compatibility Migration*, chapter *Regression Testing*, guides you on how to design **mixed-version compatibility tests**: defining contracts, building a compatibility matrix, standing up a multi-version environment, checking HTTP/gRPC/events/databases/state, handling rolling deployments and rollbacks, and using evidence to make safe release decisions.

## 1. What Does “Multiple Versions Operating Together” Mean?

A system can simultaneously have multiple types of versions:

- **Source/artifact version:** for example `orders-service 2.4.0` and `2.5.0`.
- **JDK runtime version:** for example Java 17 and Java 21.
- **Framework version:** different Spring/Jakarta/ORM generations or network libraries.
- **API contract version:** `/v1/orders` and `/v2/orders`, or media type/header version.
- **Event/schema version:** old events and events with added fields.
- **Database schema version:** tables/columns/constraints changing gradually.
- **Protocol/serialization version:** JSON, Protobuf, Avro, Java native serialization, custom binary.
- **Configuration/feature version:** feature flags, consumer capabilities, deployment policies.

Do not equate “service version 2” with “API v2”. Artifact v2 may still serve API v1; a single artifact can support multiple schema versions at the same time.

### 1.1. Three Distinct Scenarios

| Scenario | Example | Test Question |
|---|---|---|
| Multiple replicas of the same service | Order v1 and Order v2 together behind a load balancer | Do requests work regardless of which replica handles them? |
| Producer and consumer on different versions | Billing v1 reads Order v2 events | Does the old consumer understand the new event? |
| Multiple services sharing state | Order v1 and v2 accessing one DB together | Can both versions read/write the transitional schema? |

In addition, a request can traverse **an entire chain of mixed-version services**, such as Gateway v2 → Orders v1 → Payments v2. Therefore, a test that only calls Orders v2 directly is not enough for a microservices system.

### 1.2. Why Is This Regression Testing?

A change may be completely valid when all services are upgraded together yet cause errors during the transition:

- A renamed JSON field prevents the old consumer from parsing it.
- A DB column is dropped while an old instance is still reading it.
- A new event requires an enum constant unknown to the old consumer.
- A new token/session format cannot be read on an old replica.
- Different transaction or retry policies cause duplicate writes.
- A new framework has a different default HTTP serialization or time zone.
- A new JDK changes TLS/certificate/charset behavior.
- A new instance writes a Java-serialized object that an old instance cannot deserialize.

Mixed-version testing aims to prove that the system withstands **the period when multiple versions coexist**, not just the final state after the upgrade finishes.

## 2. Four Types of Compatibility to Distinguish

### 2.1. Backward compatibility

**The new version** still accepts data/APIs/behavior produced or used by **the old version**.

Example: Orders v2 can still read `OrderCreated` events sent by v1; v2 endpoints still serve v1 clients.

### 2.2. Forward compatibility

**The old version** can still process a subset of data/behavior produced by **the new version**, within the designed contract.

Example: consumer v1 can ignore v2's new JSON field `deliveryEstimate` without failing.

Forward compatibility **does not exist automatically**. If v2 changes a required field or adds an enum state that v1 considers invalid, consumer v1 may fail.

### 2.3. Binary compatibility

A precompiled JAR or plugin still links against a new API/library at the bytecode level. For example, method descriptors remain unchanged.

Binary compatibility **differs from** network protocol compatibility. Two services running in separate JVMs can communicate using JSON even if their bytecode is completely different; conversely, having the same Java types in source code does not guarantee compatible JSON wire formats.

### 2.4. Behavioral/semantic compatibility

The fact that a request or message still parses **does not mean** the result is right.

For example, both versions accept the `amount` field, but v1 interprets it as major currency units while v2 interprets it as minor units. This is a severe bug even though the formal schema did not change.

| Compatibility Level | Question | Example Failure |
|---|---|---|
| Syntax/format | Can the JSON/Protobuf be decoded? | Parser rejects the new field |
| Contract | Are endpoint, header, status, and schema valid? | API changes status 200 to 202 outside the contract |
| Semantics | Do values have the same meaning? | Dong changed to xu |
| Operational | Are timeout, retry, auth, and capacity met? | Retry duplicates order |
| State/data | Can DB/job/session state be read across versions? | Schema dropped too early |
| Binary | Does a precompiled library/agent still link? | `NoSuchMethodError` |

## 3. Think in Terms of “Contracts at Boundaries,” Not Per Repository

A service typically has multiple boundaries:

~~~mermaid
flowchart LR
    A["Client v1/v2"] --> B["Gateway v1/v2"]
    B --> C["Orders service v1/v2"]
    C --> D["Payments service v1/v2"]
    C --> E["Transitional database schema"]
    C --> F["Message broker"]
    F --> G["Billing consumer v1/v2"]
    C --> H["Shared session/cache"]
~~~

Each connecting edge is a **separate contract**:

- HTTP/gRPC between client and service.
- Events between producer and consumer.
- Schema/transactions between service and database.
- Cache/session records between replicas.
- Authentication tokens/claims between auth and consumers.
- Job payloads between scheduler/worker.
- Health/readiness protocol between app and deployment platform.

When upgrading JDK/frameworks, a contract can be unintentionally altered by a library, serializer, or default configuration, even when business source code barely changes.

### 3.1. Contract Inventory

An inventory table:

| Boundary | Producer/owner | Consumer | Format | SLO/risk | Evidence |
|---|---|---|---|---|---|
| `GET /orders/{id}` | Orders | Web/mobile | JSON/HTTP | Many old clients remain | Contract test |
| `OrderCreated` | Orders | Billing, Search | JSON/Avro | Events retained for many days | Replay test |
| `orders` table | Orders | Orders v1/v2 | SQL schema | Both write at the same time | Mixed DB test |
| Checkout session | Gateway | Gateway v1/v2 | Redis/JSON | Requests switch replicas | Session test |
| Access token | Auth | Gateway/Services | JWT or opaque | Key/claims rotation | Auth interoperability |
| Email job | Orders | Worker | Queue JSON | Retries and redelivery | Cross-version worker test |

Do not list only public APIs. Shared caches, background jobs, and migration scripts can also be real contracts.

## 4. Building a Basic Version Matrix

Suppose we have two consecutive releases:

- **V1:** currently running, using JDK 17.
- **V2:** about to be deployed, using JDK 21.

We need to test both directions.

| Client/producer | Server/consumer | Scenario | Goal |
|---|---|---|---|
| V1 | V1 | Baseline | No regression prior to the change |
| V1 | V2 | Old client/producer with new service | Backward compatibility |
| V2 | V1 | New client/producer with old service | Forward compatibility per contract |
| V2 | V2 | Post-migration state | New system works |
| V1 + V2 | Shared DB/cache | Mixed deployment | State is not corrupted |
| V2 → V1 rollback | State already written by V2 | Rollback | V1 can recover |

Not every combination must be supported forever. However, **combinations that can occur during real rollout/rollback** must be declared and tested.

### 4.1. Producer/Consumer Direction Matters

For events:

~~~text
Producer v1 -> Consumer v2
Producer v2 -> Consumer v1
~~~

These are two different directions. A new schema may read old events fine, while new events break old consumers.

### 4.2. Do Not Only Test N and N+1 Separately

If producer v2 produces a new value, consumer v1 may receive it during the mixed-version phase. Even if API v1 does not produce that value itself, the system can still pass the value through the database, events, or cache.

A test suite where “v1 + v1” and “v2 + v2” both pass green can still completely miss this bug.

## 5. Rolling Deployment Model

A rolling deployment gradually replaces instances, for example:

~~~text
T0: [V1, V1, V1, V1]
T1: [V1, V1, V1, V2]
T2: [V1, V1, V2, V2]
T3: [V1, V2, V2, V2]
T4: [V2, V2, V2, V2]
~~~

During T1–T3, the load balancer can route requests to any replica. A retried request may be handled by **a different version** from the first attempt.

### 5.1. Scenarios That Must Be Tested

- Old client calls V2.
- New client calls V1 during canary.
- The same user alternates calling V1/V2.
- A request starts at V1 and then retries to V2.
- A shared session/cache is created by V2 and then read by V1.
- V2 updates the DB, V1 reads the result.
- Background tasks from V1 and V2 run together.
- Scale-down/termination of V1 happens during a long request.
- Rollback of V2 to V1 after V2 has already written data.

### 5.2. Readiness Does Not Mean Compatibility

A `/health` probe returning 200 only states that the service is healthy enough according to probe conditions. It does not prove an endpoint can be called across multiple versions or that shared state remains compatible.

Readiness still needs to be combined with:

- Contract tests.
- Stateful integration tests.
- Data/serialization tests.
- End-to-end routing tests.
- Business invariants and SLOs.

## 6. Blue–Green and Canary Also Need Mixed-Version Testing

**Blue–green** maintains two environments and switches traffic. If traffic is completely isolated, mixed-version requests may be fewer, yet databases, queues, caches, or consumers can still be shared.

**Canary** shifts a small percentage of requests to V2. If old consumers still receive new events, a small HTTP request percentage does not limit the blast radius of a **breaking event schema**.

### 6.1. Questions Before Releasing

1. Do both versions share a DB?
2. Can a new event reach an old consumer?
3. Is session state held on the client or in a shared cache?
4. Can retries reach an instance of a different version?
5. Do background jobs run concurrently?
6. Is it possible to roll back without rolling back schema/data?
7. Are there long-lived connections such as WebSocket/gRPC streams?
8. Does a scheduler or leader election pick any arbitrary instance?

If yes, corresponding tests are needed even if the deployment strategy is not named “rolling”.

## 7. HTTP/JSON: Extending Contracts Safely

For example, V1 returns:

~~~json
{
  "orderId": "O-1001",
  "status": "CREATED"
}
~~~

V2 wants to add the estimated delivery time:

~~~json
{
  "orderId": "O-1001",
  "status": "CREATED",
  "deliveryEstimate": "2026-11-15T09:00:00Z"
}
~~~

This is an **additive** change in terms of JSON. However, whether old consumers accept it depends on how the deserializer is configured.

If a V1 client rejects unknown properties, it can still fail when receiving a V2 response.

### 7.1. Consumers Able to Ignore Unknown Fields

Example using Jackson (dependency/framework must be declared separately):

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderResponseV1(
        String orderId,
        String status) {
}
~~~

When parsing V2 JSON, the `deliveryEstimate` property that does not belong to the V1 record will be ignored if Jackson is configured/the corresponding annotation is applied.

However, this is not advice to “ignore all invalid data”. Consumers must still validate **required fields, data types, enums, and the semantic contract**.

### 7.2. New Fields Are Not Always Backward Compatible

If V2 changes `customerId` from a string into an object:

~~~json
{
  "customerId": {
    "value": "C-55",
    "region": "VN"
  }
}
~~~

while V1 expects:

~~~json
{
  "customerId": "C-55"
}
~~~

that is a type change, not an additive field. Old consumers may fail to parse or misprocess it.

### 7.3. “Optional” Must Be Defined Clearly

A field can be:

- Absent.
- Present with `null`.
- Present with an empty string.
- Have a default value.
- Have a valid or invalid value.

These situations **are not automatically equivalent**.

For example, if client V1 uses `null` to represent “no data yet”, V2 switching to omitting the field completely can change presence-check behavior.

### 7.4. Safe Two-Phase Field Renaming

If you want to rename `customerName` to `displayName`:

1. Producer V2 temporarily emits both fields.
2. New consumers are upgraded to read the new field, with fallback.
3. Telemetry confirms old consumers no longer depend on the old field.
4. Only then is the old field removed in a controlled release.

If the system has clients that cannot be upgraded simultaneously (mobile/offline), the support window can be longer than the server rollout.

## 8. REST: Endpoints, Status, Headers, and Pagination Are Also Contracts

Not just JSON bodies—changes in HTTP can break compatibility:

- `GET /orders/{id}` changes to a different route.
- Status `200 OK` changes to `202 Accepted`.
- Error response no longer contains the `code` field.
- `Content-Type` changes beyond the client's parser capabilities.
- `Location`, `ETag`, or cache headers change semantics.
- Pagination token format changes.
- Query parameter has a different default.
- Idempotency behavior changes.
- Timeout or body-size limit decreases.
- HTTP redirects are not handled by old clients.

### 8.1. Example Contract Table

| Case | V1 behavior | V2 expectation | Test |
|---|---|---|---|
| Order exists | `200` + JSON | Keep old shape, may add fields | V1 client → V2 |
| Not found | `404` + error code | Still preserve machine-readable code | V1 client → V2 |
| Create valid order | `201` + ID | Do not create duplicates on retry | V1/V2 clients |
| Duplicate idempotency key | Return previous result | Same semantics | Retry switches replica |
| Old pagination token | Readable by V1 | V2 must handle it or have expiration policy | Old token → V2 |
| Invalid input | Stable `4xx` | Do not change to `5xx` | Both directions |

### 8.2. Versioned Endpoints

Some APIs needing incompatible changes can use versioned routes:

~~~text
GET /api/v1/orders/O-1001
GET /api/v2/orders/O-1001
~~~

This allows two contracts to coexist, but does not automatically handle:

- Shared DB schema.
- Event payloads.
- Session data.
- Authentication.
- Data written by V2 that V1 must read.

Versioned URLs are only one layer of compatibility management, not the whole strategy.

## 9. Contract Tests: Producers and Consumers Share Understanding of One Contract

**Consumer-driven contract testing** lets consumers express expectations toward a provider. Provider verification then confirms the new version satisfies those expectations.

Common tools include Pact or equivalent contract-test solutions, depending on the ecosystem. One specific tool should not be treated as mandatory; what must be ensured is that **every active consumer has a corresponding verified contract**.

### 9.1. Example Contract

Consumer requires:

~~~json
{
  "orderId": "O-1001",
  "status": "CREATED"
}
~~~

Provider V2 can additionally return `deliveryEstimate` if the consumer contract allows new fields. Provider verification needs to check:

- Endpoint/HTTP method.
- Status and important headers.
- Required fields and types.
- Error semantics.
- Auth/rate-limit behavior when relevant.
- The contract version currently used by the consumer.

### 9.2. Why Testing Only the New Provider Is Not Enough?

If you only run V2 tests, those tests may have already been updated to match the new contract. Consumer V1, which is still active, is not represented.

Therefore, in CI:

1. Store contracts published by currently active consumers.
2. Have provider candidate V2 verify those contracts.
3. Have consumer candidate V2 verify against provider V1 if rolling deployment requires it.
4. Evaluate whether incompatible scenarios are blocked.
5. Avoid deleting old contracts before telemetry proves old consumers have stopped using them.

## 10. Java Example: HTTP Smoke Test Between Two Versions

`java.net.http.HttpClient` can be used to check endpoints across JVM/service versions without depending on the provider's web framework.

Example of a simple test helper:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class OrderApiSmoke {
    private OrderApiSmoke() {
    }

    public static void main(String[] args) throws Exception {
        URI base = URI.create(args[0]);

        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build()) {
            HttpRequest request = HttpRequest.newBuilder(
                    base.resolve("/api/v1/orders/O-1001"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                throw new AssertionError(
                        "Unexpected HTTP status: " +
                        response.statusCode());
            }

            if (!response.headers()
                    .firstValue("Content-Type")
                    .orElse("")
                    .toLowerCase(java.util.Locale.ROOT)
                    .contains("application/json")) {
                throw new AssertionError(
                        "Expected JSON response");
            }

            System.out.println(response.body());
        }
    }
}
~~~

**Note on Java version:** the example uses `HttpClient` with `try-with-resources`; `AutoCloseable` support on this API depends on the JDK release. To run the same source on older JDKs, you can remove the `try (...)` part and use the client according to the API available in the target release. The focus is on the smoke test structure, not the snippet's compatibility with every JDK.

### 10.1. A Smoke Test Is Not Enough to Prove a JSON Contract

The code snippet above only checks HTTP status/content type and prints the body. In real tests, you should parse JSON using the chosen library and assert:

- `orderId` is non-empty and matches the right ID.
- `status` belongs to the value set supported by the consumer.
- Optional fields do not cause the parser to fail.
- Error responses preserve the contract.
- Timestamps/currencies have the right semantics.

Do not use `String.contains` in place of JSON parsing in production contract tests.

### 10.2. Running Tests Against Both Targets

Suppose the test infrastructure has:

~~~text
http://localhost:8081   -> Orders V1 (JDK 17)
http://localhost:8082   -> Orders V2 (JDK 21)
~~~

Consumer V1 and consumer V2 should be run against both endpoints according to the compatibility matrix. Do not infer results merely from both endpoints returning 200 when invoked with `curl`.

## 11. Enum and State Machine Changes

Enums are a common place for semantic compatibility bugs.

V1:

~~~text
OrderStatus = CREATED | PAID | CANCELLED
~~~

V2 adds:

~~~text
OrderStatus = CREATED | PAID | CANCELLED | REFUNDED
~~~

If consumer v1 does:

~~~java
OrderStatus status = OrderStatus.valueOf(
        externalStatus);
~~~

then `REFUNDED` may cause an `IllegalArgumentException`. Some clients also have a `switch` without a default branch or handle errors under old assumptions.

### 11.1. Strategies

- Have a representation for unknown/future states when the contract allows.
- Do not change the meaning of old enum values.
- Do not reuse an old value code for a new meaning.
- Have a clear policy on gating features to only emit new states after consumers are ready.
- Test both valid/unknown states and fallback behavior.
- Do not silently map risky states like `REFUNDED` to `PAID`.

### 11.2. Feature Gating for New Values

Even when V2 is deployed, emitting the `REFUNDED` state can still be turned off until consumers are upgraded. However, **all producer paths** must be controlled, including admin tools, background jobs, and replays.

Feature flags help coordinate rollout, but do not replace contract tests.

## 12. Event-Driven Systems and Schema Evolution

In systems using Kafka, RabbitMQ, Pulsar, or other brokers, producers and consumers are often deployed independently. A new message may be read by:

- A running consumer v1.
- A canary consumer v2.
- An offline consumer that reconnects later.
- A replay job reading historical events.
- A dead-letter reprocessor using a different version.
- A data platform consumer outside the core development team.

### 12.1. Additive Event Example

V1:

~~~json
{
  "eventType": "OrderCreated",
  "eventId": "e-100",
  "orderId": "O-1001",
  "totalMinorUnits": 250000
}
~~~

V2:

~~~json
{
  "eventType": "OrderCreated",
  "eventId": "e-100",
  "orderId": "O-1001",
  "totalMinorUnits": 250000,
  "currency": "VND"
}
~~~

The `currency` field looks additive, yet if consumer v1 calculates money using a default currency, having v2 start emitting multiple currencies can break semantics even though JSON still parses.

### 12.2. Producer–Consumer Matrix

| Producer | Consumer | What to verify |
|---|---|---|
| V1 | V1 | Baseline |
| V1 | V2 | New consumer reads old events |
| V2 | V1 | Old consumer handles new events during rollout |
| V2 | V2 | Target state |
| Historical event | V2 | Replay/backfill |
| V2 retry/redelivery | V1/V2 | Idempotency, no duplicate writes |

### 12.3. Schema Registry and Compatibility Modes

With Avro, Protobuf, JSON Schema, or a schema registry, compatibility modes can differ, commonly using concepts such as backward, forward, or full compatibility.

**The mode name is no substitute for understanding reader/writer roles.** For example, Avro writer schemas and reader schemas have specific resolution rules and defaults must be valid, while Protobuf has field-number preservation rules different from JSON.

When applying:

1. Explicitly document the schema format and registry config.
2. Record writer version and reader version.
3. Test both V1→V2 and V2→V1 directions.
4. Check the schema evolution rules of the actual technology.
5. Test real message serialization/deserialization.
6. Test behavior when fields are absent, unknown, or have defaults.

### 12.4. Do Not Reuse Protobuf Field Numbers

With Protocol Buffers, field numbers are a critical part of the wire contract. When deleting a field, manage the field number/name according to Protobuf rules—often using `reserved` when appropriate—instead of reusing the number for another meaning.

Changing a field number/type can cause versions to mis-decode or lose data. This is not an issue solved merely by renaming a Java property.

## 13. Idempotency, Retries, and Duplicate Delivery

An event or request can be executed again when:

- A client times out and retries.
- A load balancer routes the request to a replica of a different version.
- A consumer rebalances.
- A worker crashes after the side effect succeeds but before acking.
- A broker redelivers a message.
- A rollback causes an old worker to continue processing the backlog.

In these cases, V1 and V2 must remain consistent on **idempotency keys** and side effects.

### 13.1. Order Creation API Example

Request:

~~~http
POST /api/v1/orders
Idempotency-Key: request-123
Content-Type: application/json

{"customerId":"C-9","totalMinorUnits":250000}
~~~

One call may hit V1, and its retry may hit V2. If the two versions use two different idempotency stores or generate keys with incompatible algorithms, the system can create **two orders**.

### 13.2. Specific Test Scenario

1. Send the first request to V1.
2. Simulate the client not receiving the response even though the server committed.
3. Retry with the same key to V2.
4. Assert there is only one business order/side effect.
5. Reverse the direction: V2 first, V1 second.
6. Test concurrent retries.
7. Check key retention/TTL.
8. Verify response mapping and error consistency.

If idempotency behavior changes between releases, the migration must have a state-sharing or feature-gating plan.

## 14. Database Schema: Expand–Migrate–Contract

This is the layer where rollbacks fail most easily. During a rolling deployment, V1 and V2 may read/write **the same schema**.

Suppose V1 uses:

~~~sql
CREATE TABLE orders (
    id VARCHAR(40) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

V2 wants to split the name into `first_name` and `last_name`. If `customer_name` is dropped directly in the first migration, a still-running V1 may fail.

### 14.1. Three-Phase Process

**Expand:** add the new structures while keeping the structures V1 depends on intact.

~~~sql
ALTER TABLE orders
    ADD COLUMN first_name VARCHAR(100);

ALTER TABLE orders
    ADD COLUMN last_name VARCHAR(100);
~~~

**Migrate:** backfill old data and deploy V2 code that knows how to read/write safely during the transition phase.

**Contract:** only after no consumer uses `customer_name` anymore, drop the old column according to plan.

~~~mermaid
flowchart TD
    A["Schema S1: V1 uses customer_name"] --> B["Expand S2: add first_name/last_name"]
    B --> C["V1 and V2 run together on S2"]
    C --> D["Backfill + dual-read/write or adapter"]
    D --> E["Confirm V1 has completely drained"]
    E --> F["Contract S3: drop old column"]
~~~

### 14.2. Expand Must Be Truly Compatible

Not every `ALTER TABLE ADD COLUMN` is safe. For instance, adding a `NOT NULL` column without a default can cause V1 `INSERT` statements to fail.

Similarly:

- Adding a unique constraint can block existing data.
- Changing types can make old drivers/ORMs behave differently.
- Changing defaults affects V1 writes.
- Changing triggers can affect both versions.
- Creating indexes or running large backfills can cause locks/load.

Test **V1 writes** against the post-expand schema, not just V2 reading data.

### 14.3. Dual-Write Has Risks

If V2 writes both old and new columns, determine:

- Which one is the source of truth?
- Can they be written out of sync?
- What if writing one side succeeds and the other fails?
- If V1 updates the old column, does V2 see the change in the new column?
- Can backfilling run while writes are still occurring?
- When should dual-write stop?

Some migrations require triggers, change-data-capture, or runtime-derived data. Do not apply “dual-write everything” without a consistency strategy.

### 14.4. Rollback After Schema Migration

Rolling back V2 to V1 **does not mean rolling back the database schema**. If V2 has already written data in a new shape that V1 does not understand, switching back container images can cause errors or lose information.

A pragmatic rule is to maintain a **rollback-compatible schema window** until a decision is made that rolling back to V1 is no longer needed.

## 15. Migrations Must Be Compatible with Multiple Code Versions

Flyway, Liquibase, or custom SQL migration mechanisms can run on app startup. If V1 and V2 start together, avoid:

- Two instances running migrations competitively.
- V2 contracting/dropping schema too early.
- V1 ORM automatically altering the schema back to the old state.
- Migration versions not understood by V1.
- DB locks causing readiness/rollout timeouts.
- New triggers/defaults changing semantics for V1.

### 15.1. Separating Migration Execution

In some systems, migrations should run as **a controlled deployment step** before routing V2 traffic. Other systems use migration frameworks with appropriate locking and orchestration.

Whichever model is chosen, there must be a scenario:

~~~text
Schema expanded
-> V1 still works
-> V2 is deployed
-> V1/V2 run together
-> Rollback of V2 is still safe
-> Contract schema only when V1 is gone
~~~

### 15.2. Testing Transaction Boundaries

If V2 changes the ORM/JPA version or transaction isolation, the two versions can write the same entity differently. Tests should include:

- Optimistic locking/version column.
- Concurrent update conflicts.
- Retry after deadlock.
- Transaction rollback.
- Duplicate insert prevention.
- Soft-delete semantics.
- Time zone and timestamp precision.
- Null/default values.
- Database driver behavior when changing JDK/framework.

Do not treat both versions executing `SELECT` successfully as proof that transaction semantics are compatible.

## 16. Cache, Session, and Shared State

A shared cache like Redis can contain:

- Session data.
- Serialized DTOs.
- Pagination/continuation tokens.
- Feature/permission snapshots.
- Rate-limit counters.
- Idempotency records.
- Locks and lease state.

If V2 changes the record format while V1 is still reading, errors may only show up when a request moves from V2 to V1.

### 16.1. Session-Format Matrix

| Session written by | Session read by | What to check |
|---|---|---|
| V1 | V1 | Baseline |
| V1 | V2 | New app still accepts old sessions |
| V2 | V1 | Rollback/traffic mix is safe |
| V2 | V2 | New behavior |
| Expired session | V1/V2 | TTL, logout, and invalidation |

### 16.2. Avoid Java Native Serialization in Shared State Without Contract Management

`Serializable`/`ObjectInputStream` is tied to Java class binary names, `serialVersionUID`, and object graphs. An object serialized by V2 may fail to deserialize on V1 if class shapes or dependencies change.

Beyond compatibility, native Java serialization also carries security risks if deserializing untrusted data. For cross-service caches/sessions, you should generally consider a **format with explicit schema and versioning**.

If a legacy system is forced to use Java serialization, explicit tests are needed for each runtime/artifact pair and inputs must be controlled with appropriate policies.

### 16.3. Cache Keys Are Also a Contract

If V1 writes:

~~~text
order:O-1001
~~~

but V2 reads:

~~~text
orders:v2:O-1001
~~~

cache misses or state inconsistencies can occur. Separating cache namespaces can be a reasonable strategy, but its impact on sessions, rate limits, and idempotency must be understood. Not every cache miss is harmless.

## 17. Authentication, Tokens, and Security Protocols Across Versions

During rollout, Auth v2 may issue tokens that Gateway v1 or downstream v1 does not yet understand.

Changes to test:

- JWT signing algorithm/key rotation.
- `kid` and key discovery.
- Audience/issuer changes.
- New claims or claims whose type changed.
- Token expiry and clock skew.
- Certificate truststore/TLS defaults after a JDK upgrade.
- Cookie name, domain, SameSite/Secure.
- CSRF token/session format.
- Permission/role semantics.
- HTTP header normalization across a new framework.

### 17.1. Key Rotation Within a Compatibility Window

A common strategy:

1. Consumers support verifying both the old key and the new key.
2. Auth producer starts signing with the new key.
3. Wait for old tokens to expire and observe compatibility.
4. Only then remove the old key.

Do not apply the reverse order while old gateways remain active.

### 17.2. Security Compatibility Does Not Mean Keeping Vulnerabilities

An old system may only support a TLS/cipher suite removed from the new security policy. You should not “guarantee mixed-version” by lowering security requirements indefinitely.

You need a plan to upgrade dependencies/clients first, have a controlled transition window, and block clients that are genuinely no longer supported.

## 18. gRPC and Protobuf

With gRPC, compatibility boundaries include:

- Service/method names.
- Protobuf messages and field numbers.
- Enum values.
- Streaming semantics.
- Status codes/metadata.
- Deadlines/retries.
- Compression/interceptors.
- TLS and certificate config.

### 18.1. Schema Evolution Example

V1:

~~~proto
syntax = "proto3";

message OrderReply {
  string order_id = 1;
  string status = 2;
}
~~~

Additive V2:

~~~proto
syntax = "proto3";

message OrderReply {
  string order_id = 1;
  string status = 2;
  string currency = 3;
}
~~~

In Protobuf, field numbers are a key part of the wire contract. Do not change the meaning of or reuse an already released field number.

### 18.2. Testing Streaming

A gRPC stream can be opened by a V1 client to a V1 server, and then a deployment begins. Check:

- Are open streams drained or terminated cleanly?
- Does the client reconnect to V2?
- Are resume cursors/tokens compatible?
- Do backpressure and deadlines change?
- Is event ordering preserved on reconnect?
- Does the new server accept metadata from old clients?

Passing unary RPC tests does not guarantee streaming upgrades are safe.

## 19. Long-Lived Connections: WebSocket, SSE, and Subscriptions

A short HTTP request usually lives through a single replica. However, WebSockets, Server-Sent Events, gRPC streams, or long polling can span multiple rollout phases.

### 19.1. Risks

- Deployment shuts down V1 while connections are still open.
- Client reconnects to V2 with a resume token issued by V1.
- Message schema changes mid-stream.
- Stateful subscription cursor is not shared.
- Events are duplicated or lost upon reconnect.
- An old client does not understand a new command.
- Sticky sessions keep users on V1 longer than expected.

### 19.2. Test

1. Open a connection with V1.
2. Send/receive baseline messages.
3. Deploy V2 concurrently.
4. Simulate termination/draining of V1.
5. Client reconnects to V2.
6. Assert resume position, ordering, and no-loss/no-duplicate policy.
7. Test client V2 connecting to V1 if possible.
8. Test rollback and repeated reconnects.

You must clearly define the contract for **at-least-once, at-most-once, or exactly-once effect** if the system claims it; “no duplicates” does not happen automatically on reconnect.

## 20. How Do Java/JDK Upgrades Affect Mixed-Version Setups?

Two services can communicate over HTTP/JSON and therefore do not need to run on the same Java major version. However, when upgrading the JDK, there are indirect changes:

- Default charset and how files/headers are read in legacy code.
- Locale/CLDR formatting of numbers, currency, and time.
- TLS/security providers and certificate validation.
- HTTP client implementation/version.
- XML/JSON serialization dependencies.
- Time zone database.
- JDBC driver/ORM behavior.
- Concurrency/threading and timeouts.
- JVM GC/latency causing retries/timeouts.
- Libraries removed from the JDK or module access changes.
- Jakarta EE namespace generation when upgrading frameworks at the same time.

### 20.1. Do Not Pass Java Object Identity Over the Network

A Java 17 client and a Java 21 server do not need to share the same `Class<?>` object to exchange JSON. The wire contract is what matters. However, if using Java native serialized objects or RMI/remote Java-type protocols, binary/class compatibility becomes a critical concern.

### 20.2. javax and jakarta Can Coexist Over the Network, Not on the Same Classpath

An old service using `javax.persistence` and a new service using `jakarta.persistence` can still communicate over JSON if the HTTP contract is compatible. However, when mixing two framework generations **in the same JVM/host classpath**, binary names and container APIs differ.

Do not confuse **cross-process compatibility over a protocol** with **the ability to share a classloader or a single framework API**.

### 20.3. JDK-Specific Tests Needed

In addition to mixed-version business tests, you need:

- TLS handshakes with real peers/versions.
- Charset/locale/timezone roundtrips.
- DB driver connectivity.
- Service startup and module availability.
- Old/new serialized payload fixtures.
- p95/p99 performance and timeout behavior.
- Graceful shutdown/draining.
- Java agent/observability compatibility.

A version with identical API behavior but slower latency can trigger retry storms and break invariants when running together.

## 21. Designing Multi-Version Fixtures

A test environment may have:

~~~text
Client V1 / Client V2
          |
    Gateway / router
      /        \
 Orders V1   Orders V2
     \          /
       Shared DB
          |
      Message broker
      /          \
 Consumer V1   Consumer V2
~~~

What matters is that the test runner can **explicitly target endpoints/consumers** to force version combinations.

### 21.1. Do Not Only Test Through a Random Load Balancer

If you send 100 requests to a single shared URL, most requests might hit the same replica. In that case, you cannot prove that both V1→V2 and V2→V1 were exercised.

You should have:

- Direct endpoints to each deployment in the test environment.
- Version headers/debug metadata used internally for tests only.
- Router rules forcing requests to a specific version.
- Traces/logs confirming the request traversed the intended version.

Do not expose internal endpoints or debugging headers containing sensitive information to public clients.

### 21.2. Fixture Data Must Be Representative

Test data needs:

- Records created by V1.
- Records created by V2.
- Records updated interleavedly.
- Null/empty/unknown fields.
- Unicode and different locales.
- Timestamps near DST/time-zone boundaries when relevant.
- Exact currency and decimal numbers.
- Old pagination tokens.
- Old sessions/tokens.
- Event retries and duplicates.
- Large data or deeply nested fields.

If you only create new data using V2, you may miss issues reading historical data.

## 22. Using Containers to Build Mixed-Version Environments

Docker Compose, Kubernetes namespaces, or Testcontainers can all help spin up multiple versions at the same time. What needs to be governed is **immutable image tags and exact versions**.

A structural Compose example:

~~~yaml
services:
  orders-v1:
    image: registry.example/orders:1.9.0
    environment:
      DATABASE_URL: "jdbc:postgresql://db:5432/app"
      SERVICE_INSTANCE_VERSION: "v1"
    depends_on:
      - db

  orders-v2:
    image: registry.example/orders:2.0.0
    environment:
      DATABASE_URL: "jdbc:postgresql://db:5432/app"
      SERVICE_INSTANCE_VERSION: "v2"
    depends_on:
      - db

  db:
    image: postgres:PINNED_VERSION
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test-only-password
~~~

This is an **illustrative template**, not a ready-to-run production/test file: valid image tags, network/ports/health checks, secrets, and database readiness need to be substituted and configured. Do not use test credentials in production.

### 22.1. Do Not Use latest in Compatibility Tests

If you use the `latest` image tag, a test today and tomorrow may run two different artifacts. You must pin:

- Image digest or immutable tag.
- JDK distribution/build.
- DB version.
- Broker version.
- Schema migration revision.
- Framework/service versions.
- Configuration/feature flags.

### 22.2. Readiness Before Starting Tests

Simple `depends_on` does not necessarily guarantee the DB is ready for connections in all setups. The test harness must wait for the corresponding health/readiness to avoid flakiness from startup races.

### 22.3. Separate Test Fixtures from Production Data

Mixed-version tests may run schema migrations or write incompatible data. Run against isolated, resettable databases/queues/caches and do not use real production resources unless there is a dedicated safe testing plan.

## 23. Example of a Controlled Test Matrix

A logical test suite:

~~~text
tests/
  contract/
    client_v1_to_orders_v2
    client_v2_to_orders_v1
  events/
    producer_v1_consumer_v2
    producer_v2_consumer_v1
    replay_old_events_consumer_v2
  state/
    write_v1_read_v2
    write_v2_read_v1
    concurrent_write_v1_v2
  deployment/
    mixed_replica_routing
    retry_switches_replica
    rollback_after_v2_write
    graceful_shutdown
~~~

### 23.1. Explicitly Document Expected Outcomes

Not every direction must be PASS in the sense of “full new features”. For example, a V2 client calling a V1 server may receive **a contract-defined capability-not-supported error**, rather than the server magically understanding an unreleased feature.

A valid expected outcome can be:

- Old features work as before.
- New features are disabled when calling the old version.
- Client is informed by the server of unsupported version/capability according to contract.
- No incorrect data is written.
- No crashes or infinite retries.
- No information leaks.

**Controlled failure** can be acceptable; silent data corruption is not.

### 23.2. Gate by Real-World Combinations

Once V1 is completely retired and rollback to V1 is no longer possible, some compatibility tests can be dropped from regular pipelines. However, this requires evidence about the fleet/consumers rather than relying solely on the release date.

## 24. Consumer-Driven Tests and Integration Tests Complement Each Other

Contract tests are fast and suitable to run on every PR, but do not cover:

- Database schema coexistence.
- Retry/idempotency across replicas.
- Real broker behavior.
- Authentication/TLS.
- Transactions.
- Timeouts/resource limits.
- Service mesh/load balancer routing.
- Graceful shutdown.
- Data migration/replay.

Therefore, a sound testing architecture includes:

| Layer | Goal | Recommended frequency |
|---|---|---|
| Unit tests | Logic and serialization functions | Every commit |
| Contract tests | API/schema between consumer/provider | Every PR or build |
| Component tests | Service with mocked/containerized DB/broker | Regular CI |
| Mixed-version integration | Two versions sharing state/broker | Pre-release, nightly when combinations are many |
| Deployment rehearsal | Rolling/canary/rollback | Release pipeline |
| Production canary observation | Real SLOs and errors | During rollout |

Actual frequency depends on release velocity and environment cost; it is not a fixed standard.

## 25. Feature Flags and Two-Phase Changes

A V2 build can contain code supporting new fields/states without emitting them yet because consumer V1 is not ready.

For example:

~~~text
Deploy V2 with new field reader
  -> Upgrade consumers to accept new field
  -> Enable new field writer in producers
  -> Observe
  -> Retire old format only after all consumers migrate
~~~

### 25.1. Reader First, Writer Second

A common principle in schema evolution is making consumers **capable of reading the new format before producers start emitting that format**.

However, rollback must be considered:

- If a V2 producer has already written new data and you roll back to a V1 reader, can V1 read it?
- If not, keep the feature write disabled until rollback is no longer needed or add backward support.

### 25.2. Feature Flags Can Drift Between Replicas

When V1 and V2 run together, a flag enabled on V2 that V1 does not know about can cause shared data to become inconsistent. Flag rollouts must have a clear owner, scope, and capability contract.

### 25.3. Do Not Tie Compatibility to Manual Deployment Order

A plan stating “must deploy A before B” can make sense, yet CI/release automation should verify the precondition instead of relying on humans to remember the order.

## 26. Rollback Is an Independent Compatibility Direction

Rollback is often tested less than rollout.

Scenario:

1. V1 is running.
2. Expand schema.
3. Deploy V2.
4. V2 writes new data/events/sessions.
5. A performance issue is discovered.
6. Roll back all instances to V1.
7. V1 must read/process the state V2 created.

If step 7 fails, rolling back the application image can make the system worse.

### 26.1. Data-Level Rollback Tests

- V1 reads rows created by V2.
- V1 reads events emitted by V2.
- V1 recovers/retries jobs enqueued by V2.
- V1 reads sessions updated by V2.
- V1 handles tokens issued by Auth V2.
- V1 does not overwrite/strip new fields when updating.
- V1 does not run reverse schema migrations that cause data loss.

### 26.2. When Direct Rollback Is Not Possible

There are breaking migrations where V1 cannot read the new state. In that case, you need to design one of these options:

- Roll-forward only under very strict conditions.
- Keep the compat writer around longer.
- Use a verified adapter/downgrade transform.
- Separate data stores or use versioned data.
- Have a backup/restore and downtime plan.
- Perform major migrations during an approved maintenance window.

What matters is **declaring the limitations**, rather than assuming rollback is always possible.

## 27. Testing Concurrency and Business Invariants

Mixed-version systems easily break when concurrency logic differs.

Example invariants:

~~~text
One idempotency key creates at most one order.
Balance must not become negative outside policy.
A payment can only be captured once.
An inventory reservation must not be issued twice.
An outbox event is only processed with an exactly-once business effect.
~~~

If V1 and V2 use different lock keys or one version changed a transaction boundary, sequential tests may still PASS.

### 27.1. Concurrent Scenarios

- V1/V2 update the same order concurrently.
- V1 retries while V2 is committing.
- Both instances process the same scheduled job concurrently.
- Consumer rebalance during version transition.
- Lock lease expires between the two versions.
- Optimistic-locking exceptions and retries.
- Outbox publisher v1/v2 look at the same record simultaneously.

### 27.2. Assert on Final Data

Do not assert only HTTP `200`. After the workload, inspect the database/event sink to prove invariants such as order count, payment count, and final state.

## 28. Background Jobs and Schedulers

Many services serve HTTP while also running background jobs. When two versions operate, the job system can easily be omitted from the matrix.

Risks:

- V1 does not understand a job type created by V2.
- V2 changes JSON fields in the queue payload.
- Both versions run a singleton scheduled job simultaneously.
- A job retry crosses into another version.
- Distributed lock keys change.
- Job results are written in V2 format that V1 cannot read.
- Dead-letter replay after rollback.

### 28.1. Separate Scheduler and Worker If Needed

One architectural strategy is managing the singleton scheduler independently from the worker fleet, or having supported leader election/locking. When upgrading versions, test job ownership and lock reclaim capability.

Do not merely rely on the scheduler running on a single instance “by luck” in the test environment.

## 29. Observing the System During Mixed-Version Rollout

To tell which version errors relate to, telemetry needs the right context attached:

- Service name and artifact version.
- JDK vendor/version.
- Framework/config version if relevant.
- Deployment environment, cluster/region.
- Instance/pod identity.
- Trace ID/correlation ID.
- API/schema version.
- Event type and producer version.
- Retry attempt/idempotency key if permitted and stripped of sensitive information.
- DB migration revision.
- Feature flag state.

### 29.1. Avoid High-Cardinality Labels

Do not turn arbitrary user IDs, raw URLs containing personal data, or per-request unique idempotency keys into metric labels because doing so increases cardinality and data risk.

Version/service/deployment labels can be useful; trace IDs and request-specific details belong better in protected tracing/logs.

### 29.2. Compare by Version

A dashboard should allow viewing:

~~~text
HTTP error rate V1 vs V2
Request latency p99 V1 vs V2
DB failures by version
JSON/Protobuf deserialization errors by version
Queue retry/DLQ by consumer version
Authentication failures by version
GC/CPU/memory by JDK version
~~~

Do not look only at the aggregate error rate; a 5% canary traffic slice failing 30% of the time can be masked by overall traffic.

### 29.3. Event Schema Failures Need Alerts

If a V1 consumer fails to parse a V2 event, infinite retries or growing dead-letter queues can occur while HTTP dashboards remain green. Independent monitoring is needed for queue lag, deserialization errors, and DLQ volume.

## 30. CI Pipeline: Testing Levels

A suggested pipeline:

~~~mermaid
flowchart TD
    A["Candidate V2 commit"] --> B["Unit + serialization tests"]
    B --> C["Consumer/provider contract verification"]
    C --> D["Build immutable V2 artifact"]
    D --> E["Start V1 + V2 + DB/broker"]
    E --> F["Run version matrix + state tests"]
    F --> G["Simulate rolling + rollback"]
    G --> H{"Contracts, invariants, SLO met?"}
    H -->|Yes| I["Canary and monitor production"]
    H -->|No| J["Block release, classify errors"]
~~~

### 30.1. Fast Test Suite on Every PR

- Serializer compatibility fixtures.
- API contract verification.
- Schema migration expand checks.
- Unit tests for version fallback.
- Several critical consumer/provider combinations.

### 30.2. Pre-Release Test Suite

- V1/V2 containers sharing DB/queue.
- Rolling deployment rehearsal.
- Concurrent writes.
- Event replay and retries.
- Token/session continuity.
- Long-running jobs/streams.
- Rollback after V2 has created state.
- Performance and SLO comparison on the target JDK.

### 30.3. Results Must Be Tied to Artifacts

Do not say “V2 tests are green” if the V2 image was silently rebuilt with different dependencies before release. Record the image digest, JDK update, DB/broker version, and test report.

## 31. A Test Matrix Configuration Template

Example matrix document:

~~~yaml
release_candidate:
  service: orders
  artifact: "orders:2.0.0"
  runtime: "JDK 21 approved update"

baseline:
  artifact: "orders:1.9.0"
  runtime: "JDK 17 approved update"

compatibility_window:
  allow_rolling_mix: true
  rollback_to_baseline: true

tests:
  - id: old-client-new-server
    client: v1
    server: v2
    expected: "Existing API contract preserved"

  - id: new-client-old-server
    client: v2
    server: v1
    expected: "Legacy capabilities work; new ones gated"

  - id: new-producer-old-consumer
    producer: v2
    consumer: v1
    expected: "Schema accepted or feature remains disabled"

  - id: new-write-old-read
    writer: v2
    reader: v1
    expected: "Rollback-compatible state"

  - id: mixed-replica-retry
    first_attempt: v1
    retry: v2
    expected: "At most one business order created"
~~~

This is a **document template**, not a configuration understood out of the box by a specific test runner. In real projects, test IDs should map to scripts/integration tests with verifiable evidence.

## 32. Common Mistakes

### 32.1. “V1 and V2 both pass unit tests, meaning they are compatible”

Not true. Bugs may only appear when the old version reads data/responses produced by the new version.

### 32.2. “Adding an API field is always backward compatible”

Not necessarily. Strict deserializers, default fields, and semantics can make old clients fail.

### 32.3. “Only test old clients against the new server”

Misses the **new client against old server** direction, especially in canary, retries, or when services deploy independently.

### 32.4. “Rolling deployment only needs a readiness probe”

Readiness does not prove payload/database/session compatibility.

### 32.5. “Schema migration can drop the column right after deploying V2 succeeds”

If V1 is still running or rollback to V1 is still allowed, dropping early can break the application.

### 32.6. “Rollback just requires switching the container image back”

Not true if V2 has already written state that V1 cannot read.

### 32.7. “Additive events cannot cause harm”

A new field or enum can change business semantics even if the old parser ignores the field.

### 32.8. “Handling idempotency per instance is enough”

If retries switch replicas/versions, idempotency requires proper contracts and state coordination.

### 32.9. “Having versioned API URLs makes everything compatible”

Databases, events, sessions, tokens, and background jobs can still be broken.

### 32.10. “Java 17 and Java 21 cannot run together in the system”

Independent JVMs can communicate over stable protocols. Test contracts and JDK/security/serialization differences rather than forcing every service onto the same Java version merely because they communicate over HTTP.

### 32.11. “Preserving binary compatibility means preserving wire compatibility”

Not equivalent. Bytecode class/method signatures and JSON/gRPC/event contracts are different layers.

### 32.12. “A 1% canary cannot affect shared data”

A small canary can still emit new events to a shared topic or migrate a shared DB, affecting 100% of consumers.

### 32.13. “A parser not throwing errors is enough”

It can parse syntax correctly yet misinterpret currency, units, timestamps, enums, or access permissions.

### 32.14. “Using latest for the test environment for convenience”

Makes results hard to reproduce because the baseline can change without the test name changing.

### 32.15. “With feature flags, compatibility tests are unnecessary”

A mis-scoped flag or one turned on by a secondary producer can still emit incompatible data.

### 32.16. “Only testing HTTP without testing queues/jobs”

Background tasks and event consumers can receive data from other versions even when HTTP traffic is normal.

## 33. Implementation Checklist for Mixed-Version Regression Tests

### Scope Definition

- [ ] Artifact versions and JDK runtime versions are explicitly recorded.
- [ ] Rolling/canary/blue–green and rollback topology are defined.
- [ ] All consumers, producers, and shared state are listed.
- [ ] How long the V1/V2 coexistence window lasts is defined.
- [ ] Supported combinations and “controlled failure” combinations are declared.
- [ ] Image digests, config, and DB/broker versions are pinned.

### API and Protocol

- [ ] V1 client calls V2 provider successfully with the old contract.
- [ ] V2 client calls V1 provider according to the contract/capability policy.
- [ ] HTTP status, headers, error codes, and pagination are stable.
- [ ] JSON unknown/missing/null/enum cases are tested.
- [ ] gRPC/Protobuf schema, field numbers, and metadata are verified if used.
- [ ] Long-lived streams/reconnects are tested.
- [ ] TLS/auth/token/key rotation works within the mixed-version window.

### Events, Jobs, and State

- [ ] V1 producer → V2 consumer.
- [ ] V2 producer → V1 consumer, or new writes remain gated.
- [ ] Replay historical events into V2.
- [ ] Duplicate/redelivery/retry does not produce wrong side effects.
- [ ] V1 and V2 read/write the transitional DB schema together.
- [ ] Migrations are expand-first, contract-last where appropriate.
- [ ] Schema can be rolled back to V1 within the declared window.
- [ ] Sessions/caches/tokens created by V2 are handled by V1 as required.
- [ ] Schedulers/workers do not duplicate or drop jobs.
- [ ] Concurrent writes preserve business invariants.

### Deployment and Operations

- [ ] Test runner can force requests to each version.
- [ ] Traces/logs prove the combinations actually ran.
- [ ] Graceful shutdown/draining is tested.
- [ ] Canary monitoring distinguishes V1/V2.
- [ ] DLQ/queue lag/deserialization alerts are present.
- [ ] Latency p95/p99, errors, and CPU/GC are compared.
- [ ] Rollback test is performed after V2 has written state.
- [ ] Artifacts and test evidence are stored alongside the release candidate.

### Post-Migration

- [ ] V1 is completely drained before dropping old fields/endpoints.
- [ ] Consumer telemetry confirms the old contract is no longer used.
- [ ] Temporary compatibility code is turned off/removed as planned.
- [ ] DB schema is contracted in the appropriate release.
- [ ] Migration/rollback decisions are saved.
- [ ] Contract inventory and version support policy are updated.

## Conclusion

**Testing multiple service versions operating together** is not just running two images side by side and sending a few HTTP requests. The real problem lies at the **compatibility boundaries**: client/server APIs, producer/consumer events, database schemas, sessions/caches, tokens, retries/idempotency, background jobs, and deployment lifecycles.

During *Java Advance Compatibility Migration*, especially when some services run a new JDK/framework and others remain on an older generation, **build a clear V1↔V2 matrix, test both directions of communication, create shared-state fixtures, test rollout and rollback, and verify business invariants alongside SLOs on real artifacts**. A system is considered ready when not only does V2 work well in its final state, but **the transition period and the safe path back** have also been proven by reproducible regression tests.
