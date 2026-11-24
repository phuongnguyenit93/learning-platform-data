# Backward Compatibility of Payloads in Spring Framework Application Events

**Backward compatibility of an event payload** means a consumer written against an older contract can still process data produced by a newer producer version, within the scope of published compatibility guarantees. With Spring Framework Application Events, distinguish clearly between:

1. **In-JVM events:** the publisher sends a Java object through `ApplicationEventPublisher`; `@EventListener` selects methods by **event type**. Compatibility involves class names, packages, constructors, methods/accessors, type parameters, and **business semantics**.
2. **Serialized events:** payloads are written to an outbox, audit log, Kafka/RabbitMQ, or sent over HTTP/JSON/Avro/Protobuf. Here producers and consumers may run **multiple independent versions**, requiring additional contracts for **schemas, handling missing/extra fields, versioning, and migration policies**.

A change can be compatible at the Java layer yet incompatible with JSON, or vice versa. Never lump both scopes under a single "Spring is automatically compatible" label.

For example: the first version of `OrderPlaced` has only `orderId` and `customerId`. A later version wants to add `channel` (sales channel). If old listeners only read the first two properties, you can design it so those listeners **need no code changes**. However, if you remove `customerId` or change a field's unit from dollars to cents, the change can break logic even though the program still compiles.

## 1. Producer, Payload, and Consumer Model

```text
            Producer                    Spring Event Bus              Consumer
    OrderService / Aggregate       ApplicationEventPublisher       @EventListener
              |                              |                            |
              |-- OrderPlaced(payload) ----->|-- dispatch by Java type -->|
              |                              |                            |
              |                              |                     read fields
              |                              |                     per contract
              v                              v                            v
  version may change              same JVM, same classpath        old / new listeners

If an outbox or message broker is also used:
      Java Object -> serialize -> schema/message -> deserialize -> Other Consumer
                       ^              ^                 ^
                    format        version policy     unknown/missing field
```

In Spring Framework, `publishEvent(Object)` accepts ordinary objects without requiring `ApplicationEvent` inheritance. When passing a POJO/record, Spring wraps it in `PayloadApplicationEvent` for dispatch; an `@EventListener` method can still declare its parameter as **the payload type itself**.

```java
public record OrderPlaced(String orderId, String customerId) {}

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Invoked when the publisher emits a matching OrderPlaced payload.
}
```

This is **skeleton code**, not a standalone program. Adding a field does not create an automatic version-conversion mechanism: Spring does not automatically map an independent `OrderPlacedV2` into `OrderPlacedV1`.

### Four Compatibility Levels to Consider Separately

| Level | Question | Breaking Example |
| --- | --- | --- |
| **Source compatibility** | Does old consumer source code still compile against the new event library? | Removing `customerId()` accessor called by old code |
| **Binary compatibility** | Can previously compiled consumers still link/run with the new event class? | Removing `OrderPlaced(String, String)` constructor called by old bytecode |
| **Semantic compatibility** | Do old consumers still interpret **business meaning accurately** even if code runs? | Changing `amount` from major units to minor units while keeping name and `long` type |
| **Wire/schema compatibility** | Can independent consumers read JSON/Avro/messages from the new producer? | Renaming `orderId` to `id` without alias/upcaster support |

**Important:** binary/source compatibility does not guarantee semantic compatibility. A "meaning-only" change can be more dangerous than a compile error because the system silently processes data incorrectly.

## 2. Rules for Safe Payload Evolution

### 2.1. Prefer Adding Optional Fields with Reasonable Defaults

Suppose `OrderPlaced` v1 has:

```json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "eventId": "evt-101",
  "orderId": "ORD-42",
  "customerId": "CUS-7"
}
```

A v2 message adds `channel`:

```json
{
  "eventType": "order.placed",
  "schemaVersion": 2,
  "eventId": "evt-102",
  "orderId": "ORD-43",
  "customerId": "CUS-7",
  "channel": "MOBILE"
}
```

A compatible design can support:

- **New consumers reading old messages:** if `channel` is missing, use a **semantically clear** default such as `UNKNOWN`.
- **Old consumers reading new messages:** can keep processing if the deserializer is configured to **ignore unknown properties** and does not assume an exact fixed set of fields.
- Producers must preserve the meaning of `orderId` and `customerId`; never silently alter types or semantics.
- Test **both directions** if the system has rolling deployments or replays historical events.

**Never assume every JSON library ignores unknown fields automatically.** For example, plain Jackson has different defaults for unknown properties and constructors than a Spring Boot-customized mapper. With records, a missing field may be passed as `null` to the constructor depending on deserializer version and settings. To guarantee compatibility, test your **actual application mapper**.

### 2.2. Do Not Remove or Rename Fields Still Used by Consumers

High-risk operations:

- Renaming `orderId` to `id` without keeping the old name/alias on the wire.
- Changing `amount` from `long` to `String` or altering currency units without an explicit `currency`/`unit` field.
- Changing `occurredAt` from timezone-aware ISO-8601 to epoch milliseconds while keeping the same field name.
- Turning a nullable field into required non-null when historical data lacks it.
- Changing `eventType` or the Java class/package used for event dispatch without an adapter.
- Replacing an enum with a new set of values when old consumers use a `switch` without a fallback.

If the change is a **breaking change**, create a new event version, build an adapter/upcaster, or use a transition window to migrate consumers. Editing an old persisted/replayed schema in place usually makes historical data unreadable.

### 2.3. Defaults Must Reflect Business Reality

Not every missing field can be replaced with `""`, `0`, or `false`. For example:

- `channel = UNKNOWN` makes sense when consumers only categorize channels and accept an unknown bucket.
- `discountPercent = 0` is **not always** equivalent to "no discount info", because 0% carries specific business meaning.
- `currency = VND` is dangerous if the system previously supported multiple currencies.
- Mandatory fields driving payment decisions **should not be arbitrarily defaulted**; move to a new schema or add an enrichment/validation step.

A sound default should be documented in the contract and tested against historical events.

## 3. Runnable Java 17+: Adding a Field While Supporting Legacy Listeners

This is an **in-process Spring Application Events** example demonstrating **keeping the same Java type** and **preserving the old constructor** when evolving a record.

Initially callers created events via `new OrderPlaced(orderId, customerId)`. The new version adds `channel` while keeping the **two-argument** constructor so old call sites are not forced to change immediately. Legacy listeners only call `orderId()`/`customerId()`, while modern listeners also read `channel()`.

### 3.1. Project Structure

```text
payload-compatibility-demo/
├── pom.xml
└── src/main/java/PayloadCompatibilityDemo.java
```

### 3.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>payload-compatibility-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>PayloadCompatibilityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.3. `src/main/java/PayloadCompatibilityDemo.java`

```java
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class PayloadCompatibilityDemo {

    // Evolved version: adds channel while keeping the legacy API.
    public record OrderPlaced(
            String orderId,
            String customerId,
            String channel) {

        public OrderPlaced {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(customerId, "customerId");
            channel = (channel == null || channel.isBlank())
                    ? "UNKNOWN" : channel;
        }

        // Legacy callers can still invoke the two-argument constructor.
        public OrderPlaced(String orderId, String customerId) {
            this(orderId, customerId, "UNKNOWN");
        }
    }

    public static class LegacyListener {
        @EventListener
        @Order(10)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("legacy: order=" + event.orderId()
                    + " customer=" + event.customerId());
        }
    }

    public static class ModernListener {
        @EventListener
        @Order(20)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("modern: order=" + event.orderId()
                    + " channel=" + event.channel());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(LegacyListener.class);
            context.registerBean(ModernListener.class);
            context.refresh();

            System.out.println("publish old signature");
            context.publishEvent(new OrderPlaced("ORD-42", "CUS-7"));

            System.out.println("publish new signature");
            context.publishEvent(
                    new OrderPlaced("ORD-43", "CUS-7", "MOBILE"));
        }
    }
}
```

Run from the project directory (requires JDK 17+, Maven, and network access for initial dependency download):

```bash
mvn -q compile exec:java
```

Lines printed by the program, in order:

```text
publish old signature
legacy: order=ORD-42 customer=CUS-7
modern: order=ORD-42 channel=UNKNOWN
publish new signature
legacy: order=ORD-43 customer=CUS-7
modern: order=ORD-43 channel=MOBILE
```

**Explanation:**

1. `OrderPlaced` is the evolved Java record with three components, plus a two-argument constructor delegating to the canonical constructor with `channel = "UNKNOWN"`.
2. `LegacyListener` calls only the old accessors, so it still handles both events in the example. `ModernListener` additionally reads the new property.
3. `@Order(10)` and `@Order(20)` give deterministic display order under the default synchronous listener configuration; never assume asynchronous listeners always finish in this order.
4. `AnnotationConfigApplicationContext` and `@EventListener` accept plain objects: Spring wraps the payload appropriately when `publishEvent(...)` is called.

**Limitations of the example:** it proves **a specific API call path** and listener behavior within **a single JVM running the new class version**; it does not prove that all precompiled binaries, serializers, reflection code, or consumers in other environments remain compatible. Per the Java Language Specification, **adding/removing/reordering record components can break binary compatibility**, particularly because the canonical constructor, accessors, `equals()`, `hashCode()`, and record representation can change. The two-argument compatibility constructor only preserves part of the contract used by callers.

If a long-lived contract across precompiled libraries is required, consider representing the event as an immutable class with stable constructors/factories, or using separate versioned DTOs. Test old compiled Java bytecode in CI if binary compatibility is a real requirement.

## 4. JSON Compatibility Does Not Follow Automatically from Java Compatibility

For events living solely inside `ApplicationEventPublisher`, Spring usually dispatches by Java type without serializing the payload. Once an event is converted to JSON, Avro, or Protobuf, establish clear agreements:

| Component | Recommended Rule |
| --- | --- |
| `eventType` | Stable business name, decoupled from Java class/package names |
| `schemaVersion` | Explicitly published schema version; critical for stored/replayed events |
| `eventId` | Unique ID for one **logical event**, supporting deduplication/idempotency |
| `aggregateId` | Related aggregate/business entity key, aiding routing and tracing |
| `occurredAt` | Occurrence timestamp in an agreed format/timezone |
| Payload fields | Types, units, meaning, optionality/defaults, aliasing rules |
| Unknown fields | Must specify what consumers do with unrecognized new fields |
| Missing fields | Must specify what consumers do when old events lack fields |
| Enums | Must have a policy for new values or a new version |

With Jackson, old consumer DTOs can be configured to ignore unrecognized fields:

```java
// Illustrative code; requires Jackson dependency and corresponding annotation import.
@JsonIgnoreProperties(ignoreUnknown = true)
public record LegacyOrderPlacedDto(
        String orderId,
        String customerId) {}
```

This only **ignores unknown fields**; it does not adjust the meaning of known fields, nor does it guarantee record deserialization when required fields are missing. Test with the real `ObjectMapper`, covering constructors, null-handling, timestamps, enums, and strict validation policies.

Do not embed Java class names in JSON relying on `@class` polymorphic metadata unless you fully control the contract and an allowlist of permitted types: renaming packages/classes couples the wire format to code, and polymorphic deserialization on untrusted input creates security risks. Prefer explicit `eventType` and schemas with controlled mapping.

### Backward vs. Forward Compatibility Differ

- **Backward compatibility:** **new** consumers can read **old** messages; useful for replaying history after deploying a new version.
- **Forward compatibility:** **old** consumers can read **new** messages; vital when producers deploy ahead of consumers or multiple versions run concurrently.

In casual speech, people sometimes say "backward compatibility" to mean any case where old consumers do not break. When planning rollouts, specify the **exact reading direction** rather than one umbrella label. When both directions are required, producers and consumers must satisfy **full compatibility** under the active schema policy.

## 5. When Changes Break the Contract: Create a V2 Event and Adapter

Some changes should not be forced into the same class or schema:

- Removing a field that was previously required by consumers.
- Changing `String customerId` into a different ID structure unknown to old consumers.
- Merging multiple business meanings into one old event or splitting one event into distinct semantic events.
- Changing the order/types of a public constructor used by legacy libraries.
- Shifting the rule "OrderPlaced means order placed successfully" to "draft order created".

In those cases, model versions explicitly:

```java
public record OrderPlacedV1(String eventId, String orderId) {}

public record OrderPlacedV2(
        String eventId,
        String orderId,
        String customerId,
        String salesChannel) {}
```

These two records are **two distinct Java types**. A listener accepting `OrderPlacedV1` **does not automatically** receive `OrderPlacedV2` unless they share a suitable type hierarchy. Spring's event bus does not automatically "upcast" versions.

A practical migration path:

1. **Inventory** consumers, event stores, and historical data; identify which fields are actively used.
2. **Deploy consumers that understand V2** or add an adapter from V1 to the current domain model; retain V1 reading while old events remain.
3. **Dual-publish during transition** only if consumers truly exist that only understand V1, attaching the same `eventId`/correlation ID to avoid double business processing. When possible, prefer keeping one logical message with an adapter at the consumer layer instead of widespread dual-publishing.
4. **Measure V1 consumption**, and define retention/replay windows and a deprecation schedule per policy.
5. **Stop publishing V1** once legacy consumers have migrated; do not immediately delete V1 read support if historical events still need replay.

Illustrative *migration publisher example*, not a standalone application:

```java
public void publishDuringMigration(String eventId, String orderId) {
    // Do this only if deduplication is designed and both consumer kinds must be supported.
    applicationEventPublisher.publishEvent(
            new OrderPlacedV1(eventId, orderId));
    applicationEventPublisher.publishEvent(
            new OrderPlacedV2(eventId, orderId, "CUS-7", "MOBILE"));
}
```

Two emissions can trigger **two side effects** if a consumer subscribes to both V1 and V2. An `eventId` check in the consumer/inbox or an explicit V1 exclusion rule is mandatory whenever side effects are not idempotent. On a synchronous Spring application event bus, an exception in a listener can affect the publish flow; dual-publishing is not automatically an atomic transaction.

### Upcasters in Event Stores or Consumers

For persisted events, historical data can remain immutable while applying an **upcaster** at read time:

```text
Stored OrderPlaced v1
       |
       v
decode + validate schemaVersion == 1
       |
       v
upcast: add channel = UNKNOWN, preserve eventId/orderId
       |
       v
Current internal OrderPlaced representation
       |
       v
Business handler
```

Upcasters need tests covering missing data, legacy enums, timestamps, and old formats. Never rewrite historical event meaning or fabricate data. An upcaster is a **message/DTO** transformation layer, not an automatic feature of `@EventListener`.

## 6. How to Roll Out Changes Safely in Real Applications

### Step 1: Define the Contract Before Editing the Record

Document clearly:

- Event type/name and invariant business meaning.
- Which fields are required, which are optional, and what defaults mean.
- Which consumers depend on which fields, and whether any run independently deployed versions.
- Whether events are saved to an outbox/log for replay or emitted solely within the same JVM.
- Transaction boundaries for publication and side effects.

### Step 2: Classify the Change Type

| Change | Default Assessment | Action |
| --- | --- | --- |
| Add optional field with safe default | Usually compatible **if consumers accept unknown fields** | Test old + new consumers, configure serializers |
| Keep old fields and add constructor/factory | May help legacy Java APIs | Test source/binary; avoid absolute guarantees for records |
| Remove/rename an old field | Breaking for consumers using that field | Alias/upcaster or V2 |
| Change field type or unit | Usually breaking even if Java still compiles | Create new field, deprecate old field, or V2 |
| Change enum value set | Potentially semantically breaking | `UNKNOWN` fallback/validation or new version |
| Change Java event class/package | Breaking for legacy listeners/callers | Adapter or coordinated migration |
| Shift publish timing from before to after commit | Significant semantic shift | Review listeners/transactions, test ordering and retries |
| Turn Java payload into external message | Adds wire/delivery contract | Add `eventId`, schema policy, outbox, idempotency |

### Step 3: Deploy Consumer-First During Rolling Deployments

Example v1 → v2 adding `channel`:

1. Consumer v2 handles messages missing `channel`.
2. CI verifies consumer v1 (or an equivalent compiled binary/fixture) reads v2 properly **if parallel execution is required**.
3. New producers begin emitting payloads with `channel`.
4. After the transition window, consider making `channel` required only once no historical data or v1 consumers remain.

If step 2 cannot be guaranteed, never send an incompatible v2 schema to v1 consumers. Use a separate schema version, separate endpoint/topic, or isolated adapter per your architecture.

### Step 4: Do Not Overlook Spring Transaction Semantics

`ApplicationEventPublisher.publishEvent(...)` with the default multicaster is synchronous on the publisher's thread. If the publisher runs inside a transaction, `@EventListener` methods can run **before commit**. When processing must happen only after a successful commit, use:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    // React after commit, provided the event was published inside a transaction.
}
```

This is an **illustrative integration snippet**, requiring proper Spring beans and transaction annotation imports. By default, such listeners **do not run if the event is published outside a transaction** (`fallbackExecution = false`). Post-commit failures do not roll back the already-committed transaction.

**Payload compatibility does not solve delivery reliability.** If events must durably reach external systems, consider writing a **Transactional Outbox** in the same transaction as the aggregate, then relaying/retrying independently after commit. Design consumers to be idempotent by `eventId`. An in-JVM event bus by itself is not a persistent, replayable message broker.

## 7. Testing Compatibility Contracts

Do not write just one test for the new producer. The test suite should cover version combinations:

| Producer / Data | Consumer | Expected Outcome |
| --- | --- | --- |
| V1 Java constructor (2 args) | Current listener using only old fields | No errors, data semantics preserved |
| V2 Java constructor (3 args) | Legacy listener | Still reads `orderId`/`customerId` accurately |
| V2 Java constructor | Modern listener | Reads `channel` accurately |
| V1 JSON missing `channel` | V2 consumer | Applies agreed default or raises explicit contract error |
| V2 JSON with extra `channel` | V1 consumer | Ignores unknown field **if** policy permits |
| Historical data with different enum/timestamp | V2 consumer/upcaster | Converts accurately without fabricating data |
| Previously compiled consumer binary | New event artifact | Links cleanly or detects breaking changes early |
| Post-commit event + listener error | Consumer/transaction | Committed source transaction data is not reverted |

A practical testing approach:

- **Golden JSON fixtures:** store v1/v2 samples and deserialize them using the production-configured `ObjectMapper`.
- **Consumer-driven contract tests:** consumers publish required expectations; the producer pipeline validates before changing schemas.
- **Binary compatibility checks:** run tests against consumer JARs **compiled against the old version**, not just recompiling all source together; consider public API diff tools if the event library is widely distributed.
- **Semantic checks:** verify units, timezones, nullability, enum fallbacks, and cross-field relationships.
- **Replay/upcaster tests:** replay historical event samples and verify handler output, especially for fields that can no longer be reconstructed.
- **Delivery/idempotency checks:** with dual-publishing, retries, or outboxes, verify the same logical `eventId` never causes duplicate side effects.

A test proving the program still compiles is **insufficient** to conclude backward compatibility. The goal is preserving **legacy consumer behavior under real-world scenarios**.

## 8. Common Mistakes and Fixes

**Mistake 1: Adding a component to a Java record and claiming total compatibility.**  
Records alter the canonical constructor, component metadata, and `equals/hashCode`, potentially impacting binaries, reflection, and JSON mapping. Keeping an old constructor only protects specific call sites; test the exact published contract.

**Mistake 2: Using class names as wire event types.**  
Refactoring a Java package can accidentally break historical data. Define a stable business `eventType` with controlled mapping.

**Mistake 3: Adding a required field with no default for historical events.**  
V1 replays will fail. Declare the field optional/unknown or apply an upcaster with deterministic logic.

**Mistake 4: Ignoring unknown fields without verifying semantics.**  
The deserializer may parse the message while the consumer computes wrong results if an enum or currency unit shifted. Test semantic compatibility, not just parsing.

**Mistake 5: Dual-publishing V1 and V2 and letting consumers process twice.**  
Use a shared `eventId` for the logical event, deduplication/idempotency mechanisms, and a bounded migration schedule.

**Mistake 6: Assuming Spring automatically converts V1 to V2.**  
`@EventListener` dispatches by type, not as a schema migration engine. Use explicit adapters/upcasters for breaking changes.

**Mistake 7: Confusing "event published" with "transaction committed".**  
Synchronous listeners can run before commit; for post-commit-only side effects, use `@TransactionalEventListener` or an appropriate outbox.

**Mistake 8: Turning on Jackson ignore-unknown and treating every change as safe.**  
That flag does not fix removed fields, type changes, semantic shifts, or unexpected nulls. Schema policies and contract tests remain necessary.

## 9. Self-Assessment Questions

**1. An old listener accepts `OrderPlaced(orderId, customerId)`; a new producer needs to add `channel`. What is the preferred approach?**  
Keep existing fields and meanings, add `channel` with a clear default/optionality, preserve the API needed by old callers, and verify both Java listeners and serializers if events are serialized.

**2. Why isn't adding a field to a Java record always binary-compatible?**  
Because it can change the canonical constructor, component metadata, and APIs relied upon by precompiled bytecode/serialization. Test against old compiled binaries, not only fresh source compiles.

**3. Does Spring automatically convert an independent `OrderPlacedV2` into `OrderPlacedV1` for legacy listeners?**  
No. Unless the two classes share a compatible type hierarchy, an explicit adapter or dual-publishing design is required.

**4. Can a V1 consumer read V2 JSON with an added field?**  
Only when the deserializer/schema policy allows unknown fields and the semantics relied upon by the consumer are preserved. Never assume it.

**5. Why is `eventId` important during dual-publishing?**  
Because one logical event may reach the same side effect through two versions or retries. A stable `eventId` lets consumers/inboxes eliminate duplicate processing.

**6. If a transaction rolls back after `@EventListener` has already run, is the payload automatically retracted?**  
No. The event bus does not undo side effects. Choose transaction-bound listeners or an outbox based on consistency requirements.

## 10. References

- [Spring Framework 6.2 — Standard and Custom Events, `ApplicationEventPublisher` and `@EventListener`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 Javadoc — `ApplicationEventPublisher`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2.9 Javadoc — `EventListener`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Java Language Specification — Binary Compatibility, Evolution of Record Classes (`13.4.27)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.4.27)

