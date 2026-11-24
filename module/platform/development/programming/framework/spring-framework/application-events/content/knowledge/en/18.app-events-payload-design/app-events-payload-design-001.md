# Event Contract and Evolvability in Spring Framework Application Events

## 1. What is an Event Contract and Why Design for Evolution?

In Spring Framework, an application can publish an object using `ApplicationEventPublisher.publishEvent(...)`, and beans registered with `@EventListener` receive the corresponding event. Technically, Java only needs to determine the object type. Architecturally, however, an **event contract** answers longer-term questions:

- **What happened?** For example, `OrderPlaced` means an order has been accepted; this is an event describing a *fact that already happened*, not a command saying "create an order".
- **When is that true?** Is the event published before or after the data-persistence transaction commits? The event publication time differs from the time the business fact occurred.
- **Which fields can consumers rely on?** Field names, types, units of measurement, nullability, valid values, and business meaning.
- **What guarantees does the producer provide?** Can events be replayed, delivered in duplicate, delivered out of order, or lost? Internal Spring events **do not inherently provide** broker guarantees.
- **How can the contract be changed?** Adding optional fields, changing formats, maintaining V1/V2 in parallel, or upgrading consumers without breaking existing systems.

A useful contract must fully describe **structure + semantics + publishing rules + processing expectations**. Having only a Java record or JSON Schema without specifying currency units, timing, or publishing conditions is incomplete.

For example, an order placement event contract might state:

> `OrderPlaced` is an immutable event created once for each order placement accepted by the system; `orderId` is a stable order identifier; `totalMinorUnits` is the total amount expressed in the smallest unit of `currency`; `eventId` identifies the business event occurrence. Consumers must tolerate the possibility of a message being reprocessed in an architecture with retry mechanisms.

If V1 only had `totalMinorUnits` without `currency`, consumers would have to rely on an agreed rule (for instance, the V1 system only accepts VND). When multi-currency payments are introduced, the contract needs to evolve rather than implicitly assuming the old number still carries the same meaning.

## 2. Business Events, Messages, and Payloads

When designing Spring Application Events, three layers should be distinguished:

| Layer | Role | Example |
| --- | --- | --- |
| **Business event** | A fact that has happened in the business domain, with a stable name and meaning. | "Order ORD-7 has been placed". |
| **Payload/contract** | Data that the producer publishes to consumers. | `orderId`, `eventId`, `amountMinorUnits`, `currency`. |
| **Envelope/transport metadata** | Information supporting delivery, tracing, routing, and decoding. | `eventType`, `schemaVersion`, `occurredAt`, `correlationId`. |

In **internal Spring Application Events**, the payload can be **any Java object**, without needing to extend `ApplicationEvent`. Spring wraps it in a `PayloadApplicationEvent` and dispatches it to matching listeners.

~~~java
public record OrderPlaced(String eventId, String orderId) {}

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Receive the OrderPlaced payload published by Spring.
}
~~~

*The snippet above illustrates code inside a Spring bean and requires appropriate imports; a complete runnable example is in section 6.*

When an event travels through a **message broker** or is stored as JSON/Avro/Protobuf, it also has a **wire contract**: format, topic name, schema, and serializer/deserializer compatibility strategy. Spring's `publishEvent(Object)` **does not inherently provide** a JSON schema registry, version negotiation, or serialization for internal events. Do not confuse Java compilation success with compatibility across all consumers.

## 3. Principles for Designing Evolvable Payloads

### 3.1. Name After Business Facts

Prefer names that describe a state that has already occurred:

- `OrderPlaced`, `PaymentCaptured`, `InventoryReserved`.
- Avoid `HandleOrder`, `SendEmail`, or `UpdateCache` if these are actually **commands** rather than events.
- Do not use an overly generic name like `DataChangedEvent` and force consumers to parse an arbitrary map to figure out the real action.

Names must have **semantic boundaries**: `OrderPlaced` is distinct from `OrderPaid` and `OrderShipped`. If the condition for creating the event changes from "order placed" to "order paid", that is a contract-breaking semantic change even if the class name and all fields remain identical.

### 3.2. Publish Necessary Data, Not the Entire Entity

Avoid putting `@Entity OrderEntity`, `EntityManager`, or lazy proxy objects directly into events published to multiple listeners:

~~~java
// Not recommended for a stable contract:
public record OrderPlaced(OrderEntity entity) {}
~~~

*The snippet above only illustrates an anti-pattern; `OrderEntity` is a hypothetical JPA type.*

The risks include JPA model changes implicitly altering the contract, the object being mutated after the event is published, `LazyInitializationException` during async processing, and accidentally exposing sensitive data. Payloads can use immutable values such as IDs, amounts, currencies, and necessary states; when consumers need the latest data, they query by ID inside an appropriate transaction.

**Choose snapshot or reference based on need:**

- **Reference event:** contains `orderId`, and the consumer loads the current state from the database. Suitable when the consumer needs the latest version, though subject to race conditions or losing visibility into the historical state at event time.
- **Snapshot event:** contains business values at the time of publication. Suitable for calculations or audits requiring historical data, though payloads are larger and demand stricter contract versioning.
- You can combine an ID with a few key snapshot fields. Avoid dumping the entire entity graph without a clear need.

### 3.3. Prefer Immutability with Clear Constraints

Java 17 `record`s are a convenient choice for **shallow, rarely changing data payloads**:

~~~java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        long amountMinorUnits,
        String currency) {}
~~~

A record has `final` fields, but **does not guarantee deep immutability** if a field is a list, map, or mutable object. When containing collections, perform defensive copying and prefer immutable data:

~~~java
public record OrderLines(List<String> skuIds) {
    public OrderLines {
        skuIds = List.copyOf(skuIds);
    }
}
~~~

*The snippet requires importing `java.util.List`.*

For critical contracts, constraints should be documented and validated:

- IDs are non-blank and stable within the system scope.
- `amountMinorUnits` is an exact integer; do not use `double` for money.
- `currency` follows a standard code such as ISO 4217; minor units must be consistent for each currency.
- Timestamps like `occurredAt` use `Instant`/UTC whenever possible, not relying on the machine's default timezone.
- New values may be `null`/absent only when the schema and consumers accept them; distinguish between "unknown" and "not applicable".
- Personal data fields must follow data minimization principles, masking/encrypting as required.

**Do not change a field's meaning without changing its name or version.** For example, changing `amount` from major currency units to minor units, or `createdAt` from UTC to local time, is a contract-breaking change even though both keep the `long`/`String` type.

## 4. What Should an Event Contract Document?

A practical contract document should at minimum cover:

| Contract Section | Questions to Answer |
| --- | --- |
| Name and identity | What is the event, which namespace owns it, and who is the producer? |
| Business definition | What completed fact does the event assert? What is the exact publishing condition? |
| Schema | Which fields are required, optional, data types, limits, defaults, and valid examples? |
| Version | Current version, changes from the previous version, and deprecation/end-of-support policy? |
| Timing | How do `occurredAt` and `publishedAt` (if present) differ? |
| Identifiers | `eventId` for the business occurrence; `aggregateId`/`orderId` for the entity. |
| Ordering/latency | Is ordering guaranteed per aggregate? Can consumers receive duplicates? |
| Transaction | Published inside or after commit; will it be received upon rollback? |
| Security | Which sensitive fields are prohibited, what are retention periods and access permissions? |
| Testing/operations | Who verifies compatibility, what is the rollout order, and which metrics monitor failures? |

**Example V2 contract table** for the `OrderPlaced` event:

| Field | Type | Required? | Meaning |
| --- | --- | --- | --- |
| `eventId` | String | Yes | Stable ID of the occurrence; used to support idempotency. |
| `orderId` | String | Yes | ID of the placed order, not the ID of the event. |
| `amountMinorUnits` | long | Yes | Total amount in the smallest unit of the corresponding currency. |
| `currency` | String | Yes in V2 | Currency code; V1 lacks this so the legacy convention applies **only when verified**. |

Messages with the same `orderId` can represent different events (`OrderPlaced`, `OrderPaid`, `OrderCancelled`). Therefore, **do not use `orderId` as a complete replacement for `eventId` for deduplication**; if the business domain has multiple occurrences of the same type on one aggregate, an appropriate deduplication key is needed.

## 5. Compatibility: Which Changes Are Safe, and Which Need a New Version?

"Backward-compatible" and "forward-compatible" always depend on the **reader**, the **schema format**, and the **parser/serializer rules**:

- **Backward compatibility:** a *new* consumer can read events published by an *old* producer.
- **Forward compatibility:** an *old* consumer can read events published by a *new* producer.
- **Full compatibility:** satisfies both directions within the scope of committed policies.

A change considered "additive" is not necessarily compatible in every system. For instance, a JSON parser might ignore unknown fields, while a strict deserializer rejects them; adding a field with a default to a Java record changes the Java constructor, so old call sites may fail to compile.

| Change | Common Assessment | Risk Mitigation |
| --- | --- | --- |
| Add an **optional** field, old consumers accept unknown fields | Usually compatible with wire schemas that allow unknown fields. | Add only after checking parser, default, and nullable behavior. |
| Add a **required** field missing from old events | Easily breaks backward compatibility. | Use a reliable default or a new version; do not guess historical data. |
| Remove a field needed by old consumers | Breaks forward compatibility. | Keep the field during the transition period; set a clear deprecation deadline. |
| Rename a field | Usually breaks if consumers read by name. | Support aliases/mapping or maintain V1 alongside V2. |
| Change `long` to `String` or alter nested structure | Can break parser/code/semantics. | New version and tested converters. |
| Add an enum value | Can break consumers using exhaustive `switch`. | Consumers include an unknown/fallback branch when business rules allow. |
| Change currency unit or meaning of a state | Breaks **semantics** even when schema is unchanged. | New contract/version and clear migration. |
| Change field order in a positional format | Can break consumers reading by position. | Use field IDs/names or appropriate schema evolution tools. |
| Relax/increase numeric limits or string lengths | Can cause overflows or validation failures in old consumers. | Test limits and update the contract. |

Do not rely on slogans like "adding fields is always safe" or "a new record is automatically backward-compatible". In **Java within the same codebase**, changing a constructor signature, getter, or class type can break compilation elsewhere. In **JSON-based messaging**, effectiveness depends on schema versions and deserialization settings. In **Avro/Protobuf**, you must follow their respective field default/field number/reserved field rules rather than mechanically applying Java rules.

## 6. Runnable Java 17+ Example: Keeping V1, Introducing V2, and Normalizing at the Consumer

We have a Spring Framework 6.2.9 application using internal events:

- V1 only carries `eventId`, `orderId`, and `amountMinorUnits`. **By the hypothetical legacy contract, all V1 amounts are recorded in VND**.
- V2 adds `currency`, clarifying the meaning of the monetary value.
- A single consumer receives both versions via **two separate typed listeners**, then converts them into a unified **internal processing model**. There is no need to republish a V2 message whenever V1 is received, avoiding running the same business logic twice.

### 6.1. Project Structure

~~~text
event-contract-demo/
├── pom.xml
└── src/main/java/EventContractDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/EventContractDemo.java`:

~~~java
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventContractDemo {

    // Legacy contract: all amountMinorUnits in V1 are in VND.
    public record OrderPlacedV1(
            String eventId,
            String orderId,
            long amountMinorUnits) {
    }

    // New contract: add explicit currency unit.
    public record OrderPlacedV2(
            String eventId,
            String orderId,
            long amountMinorUnits,
            String currency) {
    }

    // Consumer's internal model, not a public event contract.
    public record CanonicalOrderPlaced(
            String eventId,
            String orderId,
            long amountMinorUnits,
            String currency) {

        public CanonicalOrderPlaced {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(orderId);
            Objects.requireNonNull(currency);
            if (eventId.isBlank() || orderId.isBlank()
                    || currency.isBlank() || amountMinorUnits < 0) {
                throw new IllegalArgumentException("Invalid order payload");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Projection projection() {
            return new Projection();
        }
    }

    public static class Projection {

        @EventListener
        public void receiveV1(OrderPlacedV1 event) {
            // The VND rule is only valid because the V1 contract specifies it.
            accept(new CanonicalOrderPlaced(
                    event.eventId(),
                    event.orderId(),
                    event.amountMinorUnits(),
                    "VND"));
        }

        @EventListener
        public void receiveV2(OrderPlacedV2 event) {
            accept(new CanonicalOrderPlaced(
                    event.eventId(),
                    event.orderId(),
                    event.amountMinorUnits(),
                    event.currency()));
        }

        private void accept(CanonicalOrderPlaced event) {
            System.out.println("Projection: " + event.eventId()
                    + " | " + event.orderId()
                    + " | " + event.amountMinorUnits()
                    + " " + event.currency());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {

            context.publishEvent(new OrderPlacedV1(
                    "evt-1", "ORD-7", 120_000));

            context.publishEvent(new OrderPlacedV2(
                    "evt-2", "ORD-8", 4_500, "USD"));
        }
    }
}
~~~

From the directory containing `pom.xml`, run with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventContractDemo
~~~

Stdout printed by the program, excluding Maven logs:

~~~text
Projection: evt-1 | ORD-7 | 120000 VND
Projection: evt-2 | ORD-8 | 4500 USD
~~~

### 6.2. Why Does the Example Run This Way?

1. `AnnotationConfigApplicationContext` registers the `Projection` bean from `Config`; methods annotated with `@EventListener` are detected by Spring.
2. When `context.publishEvent(new OrderPlacedV1(...))` runs, Spring wraps the record object into a `PayloadApplicationEvent`. Only the listener matching the V1 payload type is invoked.
3. `receiveV1` applies the **established V1 rule** to normalize the currency to `VND`. If actual legacy data contains multiple currencies, this rule is **invalid**; you must look up the data source or design a different migration.
4. V2 already carries `currency`, so `receiveV2` passes that field directly into the canonical model.
5. `accept(...)` handles the same structure for both versions and prints two lines. Each occurrence in the example is published in **only one version**, avoiding duplicate processing.
6. By default, Spring dispatches events synchronously on the publishing thread (unless an executor/`@Async` is configured), so the two lines appear in the exact publication order.

**Key takeaway:** creating a V2 record different from the V1 class **does not automatically make every V1 listener receive V2**. If a listener only declares `onEvent(OrderPlacedV1)`, it will not automatically receive `OrderPlacedV2`. You need adapters, multi-version listeners, or another explicitly designed compatibility mechanism.

The example demonstrates **how to adapt event types**, not a cross-system serialization solution. When a consumer receives events from a broker, decoding V1/V2 must be determined by `eventType`/`schemaVersion`, a schema registry, or an equivalent convention before calling the normalization logic.

## 7. Contract Evolution Strategies: In-Place, Versioned Events, Upcasters

### 7.1. In-Place Additive Evolution

If the change only adds optional data with meaningful defaults, both producer and consumer are under shared control, and the serializer is compatible, you can extend the existing schema. With JSON, for example, a new producer adds `displayCurrency`, and old consumers ignore unknown fields **if configured to do so**. New consumers must accept historical events lacking that field.

For Java records passed within the same JVM, modifying the record declaration still alters the type/constructor signature; all producers and consumers must be checked. **Wire schema compatibility does not equate to Java API compatibility**.

### 7.2. Creating a Separate V2 Event

When a change breaks the contract—such as moving from a currency-less amount to multi-currency support—use an explicit type/version like `OrderPlacedV2`, or keep the same event name with an envelope `schemaVersion=2` if external-to-JVM systems use schema/version routing.

Pros: old consumers can continue receiving V1 during the transition period while new consumers roll out V2. Cons: requires a support sunset policy, mapping, migration, and version handling during replay.

### 7.3. Upcaster / Normalizer at the Boundary

An **upcaster** converts old event data into a form understood by new consumers. For example:

~~~text
Persisted event V1
  |
  | decode / verify schema V1
  | upcast: legacy amount -> {amountMinorUnits, currency=VND}
  v
Canonical event model
  |
  +--> projection / reporting / application handler

Persisted event V2
  |
  | decode / verify schema V2
  v
Canonical event model
  |
  +--> projection / reporting / application handler
~~~

The converter must be **semantically accurate** and never fabricate values. If currency cannot be inferred from the V1 contract, an upcaster defaulting to `VND` will corrupt data. In such cases, enrich from a trusted source, handle manually, or let the consumer represent a `currency=UNKNOWN` state when business rules permit.

When event data is persisted durably, **each version needs a clear way to decode and upcast**. Avoid assuming that renaming a Java class will automatically upgrade previously stored messages.

## 8. Rolling Out V1 → V2 Without Breaking Consumers

An **expand → migrate → contract** rollout is generally safer than changing producers and consumers simultaneously:

1. **Audit active consumers:** list who listens to V1, who stores events, and who depends on field names or enum values. Include rarely active consumers and replay jobs.
2. **Define V2:** document the business fact, schema, examples, and V1→V2 conversion rules; lock down ID and timing standards.
3. **Expand the consumer side:** deploy consumers capable of reading V1 + V2 or a centralized adapter, without yet requiring producers to stop V1.
4. **Add contract tests:** verify that new consumers can read stored V1 fixtures and V2 samples; ensure required fields/currency units have not silently shifted.
5. **Migrate producers on schedule:** opt to emit V2 for ready consumers. Across multiple independent services, consider short-term dual-publishing **only when deduplication rules exist**.
6. **Monitor operations:** track event/consumer counts by version, decode errors, duplicate events, and failure rates. Maintain the ability to roll back to V1 while both are still supported.
7. **Decommission V1 once verified:** all consumers/replay paths support V2, retention windows have expired or historical upcasters exist; only then remove V1 support code.

**Dual-publishing is dangerous if the same occurrence is emitted as both V1 and V2 and both listeners execute business logic.** If emitting two representations for the same fact is unavoidable, keep the exact same `eventId` for the **same occurrence**, use routing/version-aware mechanisms, and deduplicate where side effects occur. If a new `eventId` is generated for each V1/V2 copy, ID-based deduplication will not recognize them as the same occurrence.

Conversely, **never reuse one eventId** for two genuinely distinct business events; for instance, placing an order and paying for an order must have separate event identifiers.

## 9. Event ID, Idempotency, Ordering, and Transactions

Evolvability is only safe when **identifiers and duplicate handling** are clearly defined:

- **`eventId`:** ID for the occurrence; if a message is retried/replayed, it should retain the original occurrence's ID so deduplication remains meaningful.
- **`aggregateId`/`orderId`:** groups multiple events belonging to the same entity. It is not synonymous with event ID.
- **`occurredAt`:** when the business fact happened; may differ from when the message was published/consumed. Never use a timestamp as the sole deduplication key.
- **`correlationId`:** links multiple operations across the same business flow.
- **`causationId`:** indicates the event/command that caused the new event when the system actively tracks causal chains.
- **`aggregateVersion`/sequence`:** useful when per-aggregate ordering must be checked, but only accurate if the producer assigns sequence numbers consistently.

**Idempotency** means a consumer processes a repeated occurrence without producing unwanted side effects. For example, a consumer records processing in a DB table keyed by `(consumerName, eventId)` with a unique constraint; once processed, it will not recreate audit rows or trigger duplicate tasks. Real-world implementation must consider transactions and side-effect boundaries: checking "already processed?" before writing still suffers from race conditions across concurrent workers unless properly synchronized.

### Spring Application Events Are Not a Message Broker

By default, Spring's `ApplicationEventPublisher` only hands events to the multicaster within the **same application context/JVM**. Listeners can run synchronously or be switched to async if configured. It does not natively provide:

- Durable persistence for events.
- Broker-level acknowledgement/retry.
- Consumer offsets, dead-letter queues, or automatic replay.
- Once-only delivery guarantees across services.
- Atomic transactions spanning a DB commit and sending a network message.

If the requirement is "once an order is committed, the message must be sent without loss", use an appropriate pattern such as the **transactional outbox**: write an outbox record **in the same transaction** as the business change, then have a separate process forward it to the broker and handle retries. The outbox record's event contract can store `eventType`/`schemaVersion` so consumers can decode and upcast as needed.

### Publishing Before vs. After Commit

If a service calls `publishEvent(...)` inside a normal transaction, synchronous `@EventListener` methods may run **before the transaction commits**. If the business fact only takes effect after commit, consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` when using Spring-managed transactions. However, an `AFTER_COMMIT` callback **still does not guarantee redelivery** if the process crashes after commit and before processing finishes.

Do not change the `OrderPlaced` contract definition from "event sent" to "committed" without reviewing both producer and consumer. Transaction phase guarantees are **part of event semantics**.

## 10. Designing Envelopes for Cross-JVM Systems

If events cross API/broker boundaries, separate the business payload from communication metadata. Example JSON illustrating a V2 schema:

~~~json
{
  "eventId": "evt-2",
  "eventType": "sales.order.placed",
  "schemaVersion": 2,
  "aggregateId": "ORD-8",
  "occurredAt": "2026-01-15T08:12:00Z",
  "correlationId": "corr-25",
  "payload": {
    "orderId": "ORD-8",
    "amountMinorUnits": 4500,
    "currency": "USD"
  }
}
~~~

These fields are merely **contract design recommendations**, not a format Spring forces every `ApplicationEvent` to follow. `schemaVersion=2` can be an integer in the envelope, though a system might also use a versioned event type such as `sales.order.placed.v2`. What matters is consistent, testable routing and contract definitions.

### Where Should Version Live?

- **Event/class name:** `OrderPlacedV1` and `OrderPlacedV2` inside the JVM help the compiler/linter catch type mismatches.
- **Envelope `schemaVersion`:** suits message brokers, event stores, or contracts parsed by schema.
- **Schema registry:** can manage compatibility policies and schema IDs when using Avro, JSON Schema, or Protobuf; does not automatically resolve all business meaning changes.

Avoid putting a version in both the event name and the envelope without defining how they correspond. If `OrderPlacedV2` arrives with metadata `schemaVersion=1`, consumers may misinterpret it.

## 11. Contract Tests and Evolution Testing Workflow

Merely testing "publish and verify the listener is called" is insufficient for event contracts. Multiple test layers are needed.

### 11.1. Content and Invariant Tests

- Valid V1 has an ID, order, and amount in VND per the contract.
- Valid V2 has matching `currency` and amount.
- Negative amounts, blank IDs, or invalid currencies are rejected per agreed rules.
- Missing optional fields do not cause unexpected failures in new consumers.
- Sensitive fields do not accidentally appear in payloads.

### 11.2. Cross-Version Compatibility Tests

Example test fixture:

~~~json
{
  "eventId": "evt-old",
  "orderId": "ORD-1",
  "amountMinorUnits": 90000
}
~~~

A V2 consumer must be able to read/map V1 **if backward compatibility is committed**. You can also test V2 events against an old consumer to prove forward compatibility or explicitly document that it is unsupported.

If an event store exists, retain **historical fixtures** of V1 and V2 in tests to catch parser/schema changes that break replay. With independent consumers, consider consumer-driven contract tests or schema registry compatibility checks.

### 11.3. Runtime Tests in Spring

The example in section 6 demonstrates that two V1/V2 listener overloads are invoked according to payload type. For real-world problems, also test:

- Correct event types invoke the matching listener; other types do not trigger it by mistake.
- Exceptions in synchronous listeners can affect the publisher, whereas `@Async` does not automatically propagate exceptions back like a regular call.
- `@TransactionalEventListener(AFTER_COMMIT)` only reacts when the transaction commits successfully per the defined contract.
- When dual-publishing, consumers do not execute side effects twice for the same occurrence.
- When a new event version is added, the decode/upcast path does not drop critical fields.

When async listeners or brokers are involved, **do not assert arbitrary thread ordering**; use test hooks, bounded-timeout awaits, and business conditions instead of fixed `Thread.sleep(...)`.

## 12. Common Pitfalls

1. **Changing schema without updating semantics/contract docs.** Old consumers keep running but compute wrong results. For example, changing `amountMinorUnits` to major currency units while keeping the same name.
2. **Publishing entities directly.** ORM model changes become implicit contract changes and may leak sensitive data or lazy proxies.
3. **Assuming adding a field is always backward-compatible.** Record constructors, strict JSON parsers, validation, and defaults can break consumers.
4. **Arbitrarily using `null` as a default.** Consumers cannot tell missing data apart from unknown or not applicable; define specifics explicitly.
5. **Changing enums without an unknown-value strategy.** Old consumers may throw exceptions or take wrong branches.
6. **Duplicating versions without idempotency.** The same occurrence gets processed twice, causing duplicate emails/audits or double data mutations.
7. **Putting all business logic into upcasters.** Upcasters should perform well-defined format transformations; do not fabricate current state or produce side effects.
8. **Failing to support replaying old data.** New producers work, yet projection-rebuild jobs cannot read historical events.
9. **Overusing generic `Event<T>`.** An event with a type parameter may not preserve its type at runtime due to Java type erasure; use concrete subtypes or Spring's `ResolvableTypeProvider` if routing by generic type.
10. **Lacking an owner and version deprecation schedule.** V1 lives forever, and new consumers never know whether adapters can be removed.
11. **Confusing in-JVM events with wire contracts.** `ApplicationEventPublisher` does not automatically store JSON schemas or send over a broker.
12. **Believing post-commit events cannot be lost.** Internal callbacks lack durable delivery; use transactional outbox and retries when business requirements demand it.

## 13. Self-Check

**Q1.** Why can renaming the field `orderId` to `id` break the contract even though both remain Strings?

**Answer:** Consumers may depend on the field name in JSON, getters, constructors, or schemas. Renaming without an alias or migration prevents consumers from reading the data or causes misinterpretation.

**Q2.** A new producer adds `currency` to the V1 record and changes its constructor from three parameters to four. Is this automatically a compatible change?

**Answer:** No. Existing Java call sites may fail to compile. If sent over a broker, compatibility also depends on schema and parser configuration; testing or creating a separate V2 is required.

**Q3.** Why does the example use two listeners `receiveV1` and `receiveV2` instead of forcing every V1 listener to automatically receive V2?

**Answer:** The two event classes are distinct Java types. Spring dispatches events based on the declared listener parameter type. An explicit adapter normalizes both versions without silently assuming compatibility.

**Q4.** When is setting `currency="VND"` for V1 valid?

**Answer:** Only when the V1 business contract guarantees all amounts are in VND. Without that guarantee, such a default can corrupt data and must be replaced by a different migration process.

**Q5.** If both V1 and V2 are published for the same order placement, why can consumers run into trouble?

**Answer:** The same occurrence appears in two representations. If both paths execute side effects without proper deduplication or routing, processing happens twice. Parallel publishing requires clear routing and idempotency.

**Q6.** Why shouldn't `eventId` be replaced solely by `orderId`?

**Answer:** A single order has multiple distinct occurrences/events. `orderId` identifies the aggregate, whereas `eventId` identifies one event occurrence to support tracing and deduplication.

**Q7.** Does Spring `publishEvent(...)` guarantee durable replay after the JVM shuts down?

**Answer:** No. It is an in-application event-publishing mechanism; durable persistence, broker delivery, and replay guarantees must be provided by additional design.

## References

- [Spring Framework Reference — ApplicationContext: Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, payload objects, generic events, and the multicaster mechanism.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): `publishEvent(Object)`, `PayloadApplicationEvent`, and event handoff boundaries.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): binding listeners to transaction phases with `@TransactionalEventListener`.
- [Spring Framework Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html): typed listeners, condition filtering, and supporting multiple event types.
- [Martin Fowler — Event-Driven Architecture](https://martinfowler.com/articles/201701-event-driven.html): distinguishing styles of event usage and their coupling implications across systems.
