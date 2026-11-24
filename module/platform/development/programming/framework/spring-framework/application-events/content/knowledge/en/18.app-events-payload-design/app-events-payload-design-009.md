# Event Versioning: Designing Evolvable Payloads in Spring Application Events

## 1. Why Must Events Be Versioned?

Events are often created at one point in time yet processed at another time, by code from a different version. Even with `ApplicationEventPublisher` running within the same process, producers and listeners can change across deployments. If events are also written to an outbox, persisted for replay, or sent over Kafka/RabbitMQ, **old payloads can outlive code upgrades by a long margin**.

Suppose the application initially emits an `OrderPlaced` event:

```json
{
  "orderId": "ORD-101",
  "amountMinorUnits": 1250
}
```

Later the system supports multiple currencies and sales channels:

```json
{
  "orderId": "ORD-101",
  "amountMinorUnits": 1250,
  "currency": "USD",
  "channel": "web"
}
```

If a new consumer assumes `currency` is always present, old events can cause errors. If a new producer sends extra fields while an old consumer uses a deserializer allowing only the original fields, upgrading the producer first can also break the old consumer. And if `amountMinorUnits` changes meaning from "smallest currency unit" to "amount divided by 100", that is a **semantic change** that cannot be solved merely by accepting a new field.

**Event versioning** defines the data contract and interpretation rules of an event type as it evolves. The goal is not bumping a version number on every code tweak, but helping producers and consumers know which contract correctly interprets a payload.

## 2. Distinguishing Three Kinds of Versions

| Attribute | Meaning | Must They Always Match? |
| --- | --- | --- |
| `schemaVersion` / `eventVersion` | Version of the **payload contract** for an event type | No |
| `aggregateVersion` / `revision` | State-change sequence of an aggregate; commonly used for concurrency control or event sourcing | No |
| Application / artifact version | Deployment version of the service or Java library | No |

For example, an `order.placed` event with `schemaVersion=2` might be the 17th change to aggregate `ORD-101` (`aggregateVersion=17`), emitted by application version 4.8.1. These three numbers answer **three different questions**.

- `schemaVersion=2`: the payload follows the v2 contract format and interpretation.
- `aggregateVersion=17`: the aggregate has undergone 17 update steps in the system model.
- Application 4.8.1: the deployed build; multiple builds can emit the same schema version.

**Spring Framework does not automatically issue or manage `schemaVersion` for POJO events.** `ApplicationEventPublisher.publishEvent(Object)` merely publishes an object; attaching versions, storing JSON, and checking compatibility are responsibilities of application design or the messaging/schema platform in use.

Naming a Java record `OrderPlacedV2` also **does not automatically** turn JSON messages on a broker into v2: explicit mapping, serializers, and data contracts are required.

## 3. Where Should Version Live in the Payload?

For events persisted durably or sent over a network, a common pattern separates **envelope metadata** from the **business payload**:

```json
{
  "eventId": "8f8e6278-9229-4c93-aeac-38f5590663b3",
  "eventType": "order.placed",
  "schemaVersion": 2,
  "occurredAt": "2026-09-01T10:15:30Z",
  "aggregateId": "ORD-101",
  "payload": {
    "orderId": "ORD-101",
    "amountMinorUnits": 1250,
    "currency": "USD",
    "channel": "web"
  }
}
```

Commonly used fields:

- **`eventId`:** identifier of one event occurrence; used to recognize copies during retries/duplicate delivery.
- **`eventType`:** business-stable event type name, e.g., `order.placed`.
- **`schemaVersion`:** contract version specifically for that `eventType`.
- **`occurredAt`:** when the event occurred, using a standard timestamp format and clear timezone.
- **`aggregateId`:** identifier of the related business object, if the contract models aggregates.
- **`payload`:** business data that can vary from one version to another.

This is an **application-designed envelope pattern**, not a structure mandated by Spring Application Events. Plain Java events passed solely within the same context may need neither serialization nor a full envelope. However, when replay or integration exists, separated metadata makes versioning and monitoring much easier.

When versioning, define version increments **per event type**, rather than sharing one global number system-wide. `order.placed/v2` does not have to stay synchronized with `payment.authorized/v2`.

## 4. Compatible vs. Incompatible Change Rules

### 4.1. Backward Compatibility and Forward Compatibility

In event design:

- **Backward compatibility:** consumers using the new schema can read messages created under the old schema.
- **Forward compatibility:** consumers using the old schema can read messages created by producers on the new schema.
- **Full compatibility:** satisfies both directions under the active policies and serializer/schema format.

Do not rely solely on the word "optional": actual compatibility depends on the **format** (JSON, Avro, Protobuf...), **validation rules**, **deserializer**, and **application logic**. For example, adding a JSON field may be ignored by old consumers or rejected if old consumers are configured to fail on unknown properties.

| Change Type | Risk | Approach |
| --- | --- | --- |
| Add optional field with meaningful default | Usually low if old consumers ignore unknown fields | Prefer additive evolution; test both directions |
| Add required field absent from old events | High for new consumers reading history | Provide a valid default or new version with conversion |
| Rename `orderId` to `id` | High | Keep aliases/mapping or emit v2 under a new contract |
| Change `amountMinorUnits` type to arbitrary string | High | Use a new field, adapter, or new schema version |
| Change field meaning without renaming | Very high, prone to silent errors | Treat as a breaking change; new version/event type |
| Remove a field currently used by consumers | High | Monitor usage, deprecate, migrate consumers, then remove |
| Change enum to a new set of values | Depends on whether consumers handle unknown values | Include an unknown/fallback branch or bump the contract |
| Change nested object structure | Potentially high | Upcasters and contract tests for historical data |

An "additive field" change is only safe once you know how old consumers behave. **Syntactic compatibility does not equate to business compatibility**: old consumers might misinterpret totals, states, or units of measure even when JSON deserializes cleanly.

### 4.2. Defaults Must Have a Business Basis

Suppose the `OrderPlacedV1` contract specifies that all orders are paid in USD. When upgrading to `OrderPlacedV2` with `currency`, defaulting v1 events to `"USD"` is a **justified default**.

If v1 could already represent multiple currencies without recording the field, setting `USD` blindly is **fabricating data**. Choose a more accurate strategy, such as:

- Looking up the original transaction record by ID in a controlled manner.
- Marking `currency=UNKNOWN` and requiring consumers to handle the missing-data branch.
- Disallowing interpretation of old data under the new schema without sufficient facts.
- Designing an audited migration with explicit handling for undetermined records.

Never silently introduce defaults that alter accounting, tax, payment, or authorization results.

## 5. Clear v1/v2 Example: Same Business Event, Different Contracts

**Assumed contract for the example:**

- `OrderPlacedV1` includes `orderId` and `amountMinorUnits`; during the v1 era, **all orders were in USD**.
- `OrderPlacedV2` adds `currency` and `channel`; `channel` describes the ordering channel.
- The consumer wants to normalize both into a unified internal read model (*canonical representation*).
- When v1 lacks a sales channel, return `unknown` rather than guessing `web`.

Spring-independent JSON examples:

```json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "payload": {
    "orderId": "ORD-101",
    "amountMinorUnits": 1250
  }
}
```

```json
{
  "eventType": "order.placed",
  "schemaVersion": 2,
  "payload": {
    "orderId": "ORD-102",
    "amountMinorUnits": 9900,
    "currency": "USD",
    "channel": "mobile"
  }
}
```

For systems using serialization, a router must inspect the `eventType + schemaVersion` pair and choose the matching decoder/upcaster. **Do not** deserialize every payload into the v2 class assuming v2 fields always exist; explicitly define how missing values in v1 are translated.

In Java within the same JVM, one illustrative approach uses two record types and two listeners, forwarding into a shared processing service. This is versioning **at the Java type level**; any JSON/broker routing must be implemented separately.

## 6. Runnable Java 17+ Spring Framework Example

This example uses **Spring Framework 6.2.13** with `spring-context`, without Spring Boot, a database, or a message broker. It illustrates how multiple event versions are received via `@EventListener` and normalized into a common model **without republishing a new event that causes duplicate processing**.

### Project Structure

```text
event-version-demo/
├── pom.xml
└── src/main/java/example/events/EventVersionDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-version-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### EventVersionDemo.java

```java
package example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventVersionDemo {

    // V1 contract: during this period the system ONLY supports USD.
    public record OrderPlacedV1(String orderId, long amountMinorUnits) {
    }

    // V2 contract: currency and channel are present in the payload.
    public record OrderPlacedV2(
            String orderId,
            long amountMinorUnits,
            String currency,
            String channel) {
    }

    // Consistent internal model so processing does not branch on v1/v2.
    public record CanonicalOrderPlaced(
            String orderId,
            long amountMinorUnits,
            String currency,
            String channel) {
    }

    public static class OrderEventConsumer {

        @EventListener
        public void onV1(OrderPlacedV1 event) {
            CanonicalOrderPlaced converted = new CanonicalOrderPlaced(
                    event.orderId(),
                    event.amountMinorUnits(),
                    "USD",         // Valid default per the v1 contract.
                    "unknown");    // V1 did not store sales channel.

            process(converted, 1);
        }

        @EventListener
        public void onV2(OrderPlacedV2 event) {
            CanonicalOrderPlaced converted = new CanonicalOrderPlaced(
                    event.orderId(),
                    event.amountMinorUnits(),
                    event.currency(),
                    event.channel());

            process(converted, 2);
        }

        private void process(
                CanonicalOrderPlaced event, int sourceVersion) {

            System.out.printf(
                    "CONSUMED v%d id=%s amount=%d currency=%s channel=%s%n",
                    sourceVersion,
                    event.orderId(),
                    event.amountMinorUnits(),
                    event.currency(),
                    event.channel());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        OrderEventConsumer orderEventConsumer() {
            return new OrderEventConsumer();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(AppConfig.class);
            context.refresh();

            context.publishEvent(new OrderPlacedV1("ORD-101", 1250L));

            context.publishEvent(new OrderPlacedV2(
                    "ORD-102", 9900L, "USD", "mobile"));
        }
    }
}
```

### Compiling and Running

Requires Java 17+, Maven 3.9+, and network access to download Maven dependencies on first run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.EventVersionDemo
```

Lines printed directly by the code, in exact order:

```text
CONSUMED v1 id=ORD-101 amount=1250 currency=USD channel=unknown
CONSUMED v2 id=ORD-102 amount=9900 currency=USD channel=mobile
```

**Explanation:**

1. `AnnotationConfigApplicationContext` is created and refreshed before publishing events; Spring registers the `OrderEventConsumer` bean along with both `@EventListener` methods.
2. When publishing `OrderPlacedV1`, only listener `onV1(...)` matches the type. It converts v1 into `CanonicalOrderPlaced` with USD based on the **explicitly documented hypothetical contract**, setting channel to `unknown`.
3. When publishing `OrderPlacedV2`, only `onV2(...)` matches and keeps the values provided in v2.
4. `process(...)` handles the single canonical data format; it needs no awareness of v1/v2 structures beyond the source version parameter used for observability.
5. By default, `ApplicationEventPublisher` with this context's `SimpleApplicationEventMulticaster` invokes listeners **synchronously**, so the two lines appear in the order of the two `publishEvent(...)` calls.

**Example limitations:** it passes no JSON, uses no serialization, and has no queue/retry/broker. Distinguishing `OrderPlacedV1` from `OrderPlacedV2` is handled by Spring via **runtime class type**, not by Spring reading a `schemaVersion` metadata field. When using an outbox, message broker, or event store, add tested serializers, deserializers, and a version router/upcaster.

## 7. Choosing a Payload Evolution Strategy

There are three common approaches. Not every system needs multiple event classes:

### Approach A — Evolving the Same Schema Under Compatibility Rules

Keep a single event type `order.placed`, adding optional fields, defaults, and unknown-field ignoring if serializer rules permit. New consumers can read old payloads; producers can roll out gradually without forcing all consumers to change simultaneously.

Pros: fewer version classes and fewer conversion branches. Condition: changes must be genuinely compatible in both data and business semantics. Require schema/contract tests rather than guessing from field names.

### Approach B — Separate Payload Versions

When changes break the contract, publish `order.placed` with `schemaVersion=2` or name it explicitly as `order.placed.v2`. Consumers use a router to pick a version-specific decoder, then convert into the canonical model. Keep the v1 read path alive as long as historical events or old producers exist.

Pros: explicit and supports replaying old data. Trade-off: increases conversion logic, documentation, and testing. Define clearly when a version is no longer read or may be retired.

### Approach C — Creating a New Business Event

If the **meaning of the fact** changes, bumping `schemaVersion` alone may be insufficient. For example, `OrderPlaced` means the customer confirmed placing an order, whereas a new event is needed when the system accepts risk and commits to fulfilling it; that may be `OrderAccepted`, a **business-distinct** event.

Event names should reflect what actually happened. Never let `OrderPlaced/v2` quietly shift emission timing from "request submitted" to "paid", because old consumers could misinterpret it without raising any syntax error.

## 8. Upcasting: Reading Old Data Under the Current Model

With an event store or outbox retaining payloads for years, you can build an **upcaster** to convert v1 → v2 and v2 → v3 before handing the event to domain/application handlers:

```text
Persisted event (type + version + payload)
                |
                v
Version router / deserializer
                |
        +-------+-------+
        |               |
        v               v
       v1              v2
        |               |
        v               |
  upcast v1->v2         |
        +-------+-------+
                |
                v
       Canonical handler
```

The pseudocode below illustrates a converter for an **already-deserialized model**, not a standalone program:

```java
CanonicalOrderPlaced upgrade(OrderPlacedV1 oldEvent) {
    return new CanonicalOrderPlaced(
            oldEvent.orderId(),
            oldEvent.amountMinorUnits(),
            "USD",      // Valid only if the v1 contract guarantees it.
            "unknown"); // Cannot infer sales channel.
}
```

Upcaster design rules:

- **Pure and deterministic:** the same old event always yields the same output; avoid reading mutable state or calling external services to guess values.
- **Lossless of facts:** preserve identifiers, occurrence timestamps, original amounts, and semantics; never overwrite `amountMinorUnits` with different data.
- **No unintended re-emission of domain events:** transforming read format only prepares data, not a new business action.
- **Fail loudly on unsupported versions:** never mistakenly deserialize v99 as v2 and silently drop required fields.
- **Keep historical fixtures:** store sanitized real-world samples and test replay whenever code changes.

Upcasting normally fits **at read time** rather than silently rewriting all historical events in place. If storage migration is required, plan separate backups, audits, compatibility tests, and recovery mechanisms.

### Event Sourcing Differs from Event Notification

In **event sourcing**, event history can serve as the source of truth for reconstructing aggregate state. Compatibility of old data then directly determines replay capability. In ordinary Spring Application Events **event notification**, events may live only in memory with no default historical replay mechanism. Do not force full event-sourcing architecture simply because an application calls `publishEvent(...)`.

## 9. Compatibility When Upgrading Multiple Producers and Consumers

A rollout plan for a new version should consider both producers and consumers as well as parallel execution of versions in production.

**Example v1 → v2 upgrade:**

1. Publish the v2 contract: define fields, types, units, mandatory/optional status, defaults, and sample payloads.
2. Upgrade consumers first if new consumers must understand both v1 and v2. Build adapters/upcasters and contract tests.
3. Test the new consumer against real v1 events, including missing new fields and rare states.
4. Upgrade producers to emit v2 once relevant consumers support it.
5. Monitor event counts by `eventType/schemaVersion`, deserialization errors, processing failures, and latency.
6. Stop emitting v1 once all producers are upgraded; **only** drop v1 read support after retention windows, replays, and legacy consumers are handled.

When you cannot control all consumers, you may need a transition period, versioned channels/streams, or edge adapters. **Dual-publishing** v1 and v2 is risky: consumers subscribed to both may execute business logic twice. If used, require a shared correlation or business-event ID, deduplication, and explicit routing rules.

**Never pick deployment order blindly:** backward/forward compatibility and the actual schema format dictate whether producers or consumers upgrade first. Some registries support `BACKWARD`, `FORWARD`, `FULL`, and `TRANSITIVE` variants, yet those modes do not apply automatically to a Java record published inside a Spring context.

## 10. Version, `eventId`, Ordering, and Duplicate Handling

Versioning does not replace other operational metadata:

- **`eventId`:** identifies a single unique occurrence, supporting deduplication on retries or broker redeliveries.
- **`aggregateId`:** groups events belonging to the same business entity.
- **`aggregateVersion` or sequence:** can help detect missing/out-of-order events and enforce optimistic locking, depending on storage design.
- **`schemaVersion`:** governs payload interpretation; never use it to order business events.
- **`occurredAt`:** informational timestamp; does not guarantee absolute ordering across machines.

For example, two events for the same aggregate can both have `schemaVersion=2` while having `aggregateVersion=17` and `aggregateVersion=18`. Two copies of **the exact same event** may be delivered twice with the **same `eventId`**, rather than representing two state transitions.

If during migration you emit both v1 and v2 representations of **the same fact**, link them via a business occurrence ID/correlation so receivers know they are not two separate orders. Whether they share the same `eventId` or use distinct IDs depends on the contract; define this upfront rather than changing silently mid-rollout.

## 11. Contract and Replay Testing

Java class unit tests alone suffice only for pure in-memory events. For serialized payloads, test the **actual bytes/JSON/Avro/Protobuf** that consumers receive.

| Scenario | Expected Outcome |
| --- | --- |
| Consumer v2 receives v1 payload | Reads cleanly or rejects intentionally with a clear error; no silent business corruption |
| Consumer v1 receives v2 payload | Succeeds only if forward-compatibility rules allow |
| Event v1 lacks `currency` | Defaults to USD **only when v1 guarantees USD** |
| Event v2 misses required field | Fails validation or routes to an explicit error flow, never skipped silently |
| Payload contains unknown field | Behaves per contract (ignore or reject) |
| Producer renames/changes field type | Contract tests catch the breaking change |
| Old event replayed multiple times | Upcaster is deterministic and side effects are idempotent |
| Same `eventId` delivered twice | Consumer prevents duplicate side effects per policy |
| Event with unsupported `schemaVersion` arrives | Not parsed as another version; logged/metered/quarantined properly |
| Both v1 and v2 emitted during migration | Same business logic is not executed twice automatically |

### Fixture Data

Store prior-version payloads as fixture files in the application's test suite, such as:

```text
src/test/resources/events/order-placed-v1.json
src/test/resources/events/order-placed-v2.json
```

Each fixture should verify at least: valid syntax, required fields, enums/currency units, defaults, event type, schema version, and conversion into the canonical model. Never generate test JSON solely with the current serializer: doing so easily misses cases where **real data from older versions** differs from assumptions.

When using a schema registry, configure compatibility policies per subject/type and run schema-evolution checks in CI. A registry catches type/structural violations against rules, yet **cannot validate all business semantic shifts**; contract tests and reviews remain essential.

## 12. Considerations Specific to Spring Application Events

Spring Application Events typically dispatch a **Java object** within the same process. When designing versions for this event model:

1. `@EventListener` selects listeners primarily by **event parameter type**. It does not inspect a field named `schemaVersion` to swap classes automatically.
2. A listener accepting only `OrderPlacedV2` will not automatically receive `OrderPlacedV1` unless the two records share an appropriate type relationship. You need a dedicated listener or a version router.
3. `ApplicationEventPublisher.publishEvent(Object)` provides no persistence, replay, schema registry, or transaction boundaries by default.
4. With `@Async`, consumers may run after the producer returns; never assume publication equals successful processing. In-memory queues do not replace an outbox.
5. With `@TransactionalEventListener`, the transaction phase controls when the event is handled, yet **does not automatically solve versioning or post-crash delivery guarantees**.
6. If an event type is strictly an internal Java class never persisted or sent remotely, you may not need a `schemaVersion` field. Even so, keep payload definitions clear and avoid silently altering field meanings.

**Usually well-suited design:** internal domain events remain rich, meaningful objects independent of transport details; an adapter at the integration boundary translates them into versioned envelopes, persists to an outbox, and sends via a broker when needed. This avoids polluting every domain object with infrastructure fields.

## 13. Common Mistakes to Avoid

**Mistake 1 — Bumping `schemaVersion` on every release.** Increment only when the data contract needs to distinguish versions; one release may leave schemas untouched, and multiple releases may read older versions.

**Mistake 2 — Assuming new fields are always compatible.** A consumer might reject unknown fields; verify against real payloads and parser settings.

**Mistake 3 — Changing a field's unit or meaning without changing its version.** E.g., switching `total=1000` from "cents" to "USD"; the data stays a number while the business value is severely wrong.

**Mistake 4 — Guessing defaults.** Currency, tax, and processing status must rest on historical data/contracts; when info is missing, surface the limitation explicitly.

**Mistake 5 — Deleting the v1 decoder as soon as producers emit v2.** Outboxes, broker retention, retries, dead-letter queues, and replays may still contain v1 events.

**Mistake 6 — Mutating historical event records in place without auditing.** Editing stored events can break immutability and replay. Prefer read-time upcasting or audited, verified migrations.

**Mistake 7 — Treating Java class names as wire contracts.** Package/class refactors can be internal code changes; persisted schemas need a stable `eventType` and controlled mapping.

**Mistake 8 — Dual-publishing without deduplication.** One business action may be processed twice. Use correlation/event IDs and track which consumers listen to which channels.

**Mistake 9 — Using `schemaVersion` to order events.** Order by aggregate sequence/offset and broker/storage rules when needed, never by schema version.

**Mistake 10 — Ignoring security of old schemas.** Old payloads may hold sensitive fields or attributes later removed for privacy. Enforce retention, masking, migrations, and proper access controls on persisted data.

## 14. Checklist for Designing Versioned Payloads

Before publishing a new event or changing a payload, confirm:

1. Does the event name describe **one consistent business fact** across versions?
2. Are `eventType`, `schemaVersion`, `eventId`, and `aggregateVersion` clearly separated?
3. Do fields and types have a clear contract: meaning, units, required/optional, nullability, defaults?
4. Can new consumers read old events needed for replay?
5. Is old consumer behavior verified when receiving new payloads?
6. Do breaking changes have routers/upcasters or new event types?
7. Do producers/consumers have rollout, monitoring, and rollback plans?
8. Could dual-publishing/retries cause duplicate processing, and is deduplication in place?
9. Have historical fixtures been tested instead of only serializing/deserializing with the current version?
10. If persisted durably, have retention, schema registry, replay, and legacy data protection policies been defined?

**Remember:** event versioning is managing **the data contract and semantics** among producers, consumers, and historical messages. Spring Application Events only help publish/receive objects within an application; the system itself must design compatibility, version translation, and processing guarantees when data leaves the process.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): how to publish events and use `@EventListener`.
- [Spring Framework — EventListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html): registering listeners by event type.
- [Confluent — Schema Compatibility](https://developer.confluent.io/patterns/event-stream/schema-compatibility/): backward and forward schema compatibility concepts.
- [Confluent — Schema Evolution](https://developer.confluent.io/patterns/event-stream/schema-evolution/): choosing between evolving a single schema or using separate streams/versions.
- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): compatibility modes; specifics depend on Avro/Protobuf/JSON Schema and registry policies.
