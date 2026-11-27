# DateTimeProvider, UTC, and Deterministic Test Time

## 1. A Subtle Auditing Bug: Server-Dependent Time

An order service stores document creation and update timestamps in MongoDB. Locally on a developer machine, tests see reasonable `createdAt` and `updatedAt` values. Yet when deployed across two instances in different infrastructure regions or run in CI with a different timezone, time comparisons, logs, and tests become flaky.

Three separate issues are frequently conflated:

1. **Where does the time come from?** Is it the live host clock or an injected time source?
2. **How are timezones represented?** Java `Instant`, `LocalDateTime`, `OffsetDateTime`, and BSON Date have different semantics.
3. **Are tests deterministic?** Tests relying on real `Instant.now()` can fail intermittently or resort to sleeping until time advances.

Spring Data MongoDB auditing provides an extension point called **DateTimeProvider**. When registered with **@EnableMongoAuditing(dateTimeProviderRef = "...")**, the provider determines the instant auditing uses to populate **@CreatedDate** and **@LastModifiedDate**.

A testable design looks like:

~~~text
Clock.systemUTC() in production
           |
           v
  Injected DateTimeProvider
           |
           v
 Spring Data AuditingEntityCallback
           |
           v
  @CreatedDate / @LastModifiedDate
           |
           v
 MappingMongoConverter -> BSON Date -> MongoDB
~~~

In this lesson, **Clock** is the time source, **DateTimeProvider** is the bridge to Spring Data auditing, and **Instant** represents an absolute point in time independent of display timezone.

The lesson **DateTimeProvider, UTC, and Deterministic Test Time** belongs to the **Auditing** chapter of the **SPRING_DATA_MONGODB** module. The module explores connecting, document mapping, and operating on MongoDB via `MongoTemplate` or repositories, along with queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics.

### 1.1. Objectives

After this lesson, you will be able to:

- Enable MongoDB auditing using **@EnableMongoAuditing**.
- Implement **DateTimeProvider** backed by **java.time.Clock** using UTC explicitly.
- Use **Instant** for `@CreatedDate` and `@LastModifiedDate`.
- Distinguish an absolute instant from a display timezone.
- Test with **Clock.fixed** and controlled advancing clocks.
- Verify timestamps both on the entity and in **raw BSON Date**.
- Understand **modifyOnCreate**, **setDates**, lifecycle callback ordering, and read/write conversion.
- Distinguish auditing of **insert/save** from **MongoTemplate.updateFirst**, bulk operations, and the raw driver.
- Avoid flakiness, millisecond rounding mismatches, transaction retry surprises, wrong timezones, and `Thread.sleep` tests.
- Extend to reactive auditing and multi-instance time strategies.

## 2. What Does Auditing in Spring Data MongoDB Solve?

Auditing automatically records metadata about a record, for example:

| Metadata | Common Annotation | Meaning |
| --- | --- | --- |
| Creation time | `@CreatedDate` | When the entity was created per auditing lifecycle |
| Last modification time | `@LastModifiedDate` | When the entity was saved/updated through an audited lifecycle |
| Creator | `@CreatedBy` | Principal/creator, via `AuditorAware` |
| Last modifier | `@LastModifiedBy` | Principal/modifier, via `AuditorAware` |

This lesson focuses on **time**; the application does not have to enable `@CreatedBy`/`@LastModifiedBy`.

### 2.1. Use Case

An order document might need:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  orderNo: "ORD-001",
  status: "CREATED",
  createdAt: ISODate("2025-06-01T08:30:00.000Z"),
  updatedAt: ISODate("2025-06-01T08:30:00.000Z")
}
~~~

When saving a new status:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  orderNo: "ORD-001",
  status: "PAID",
  createdAt: ISODate("2025-06-01T08:30:00.000Z"),
  updatedAt: ISODate("2025-06-01T08:35:00.000Z")
}
~~~

**createdAt** remains unchanged; **updatedAt** is updated to the timestamp auditing sees for the new write. This is the usual goal, though the actual result depends on auditing configuration, new/existing entity detection, and the write path used.

### 2.2. Auditing Is Not Complete Change History

The two fields `createdAt`/`updatedAt` do not record:

- Who modified each field.
- Old and new values.
- Failed saves or rolled-back transactions.
- Updates from other applications or the raw MongoDB driver.
- Intermediate versions of the document.

For a legal audit trail or event log, you need **append-only events, movement records, or change streams/outbox** depending on business requirements. Do not treat two timestamps as complete proof of entire history.

## 3. Understanding Instant, OffsetDateTime, and LocalDateTime

Before configuring `DateTimeProvider`, choose the stored temporal type.

| Java Type | What Information Does It Carry? | Suitable for createdAt/updatedAt? |
| --- | --- | --- |
| `Instant` | A point on the UTC timeline | **Highly suitable** |
| `OffsetDateTime` | Date-time with UTC offset | Usable if keeping offset; must understand mapping |
| `ZonedDateTime` | Date-time and `ZoneId`/rules | Requires explicit conversion/policy |
| `LocalDateTime` | Date-time, **no offset/zone** | Error-prone if treated as a global timestamp |
| `LocalDate` | Date only, no time of day | Good for business dates, insufficient for audit timestamps |
| `java.util.Date` | Point on timeline at millisecond precision | Usable, though legacy API |

### 3.1. One Instant, Many Ways to Display

~~~text
Instant UTC:       2025-06-01T08:30:00Z
Asia/Ho_Chi_Minh:  2025-06-01 15:30:00 +07:00
Europe/London:     formatted per DST rules active at that instant
~~~

**Two display formats are not two different moments in time.** `Instant` holds the point in time; `ZoneId` is applied when formatting date/time for human viewers.

### 3.2. UTC Does Not Guarantee All Machines Share the Exact Time

**Clock.systemUTC()** uses UTC in the `java.time` API; it **does not synchronize the operating system clocks of nodes**. Machines with drifting clocks still produce inaccurate timestamps. Infrastructure needs NTP/time synchronization, clock drift monitoring, and clear policies when strict event ordering is required.

### 3.3. Avoid LocalDateTime as a Default "Timestamp"

~~~java
LocalDateTime createdAt;
~~~

`LocalDateTime` only describes e.g. "08:30 on June 1", without stating whether that is UTC or a user's timezone. Converting it to `Instant` requires choosing a `ZoneId`/`ZoneOffset`; changing the zone yields a different instant.

For audit timestamps across regions, **Instant** is cleaner and less ambiguous.

## 4. How Does BSON Date Store Data?

MongoDB BSON **Date** represents milliseconds since the Unix epoch, corresponding to an absolute instant. It does not directly store a `ZoneId` such as **Asia/Ho_Chi_Minh**.

~~~javascript
{
  createdAt: ISODate("2025-06-01T08:30:00.000Z")
}
~~~

When read into Java:

~~~java
java.util.Date rawDate =
    rawDocument.getDate("createdAt");

Instant createdAt = rawDate.toInstant();
~~~

### 4.1. Millisecond Precision

An `Instant` can contain nanoseconds:

~~~text
2025-06-01T08:30:00.123456789Z
~~~

However, BSON Date has **millisecond** precision. After a round-trip through BSON Date, you typically get back:

~~~text
2025-06-01T08:30:00.123Z
~~~

Therefore, **do not assert unpersisted nanoseconds**. For exact tests, pick an `Instant` with clean millisecond values or compare after `truncatedTo(ChronoUnit.MILLIS)`.

### 4.2. The Z Suffix Is UTC Offset

In ISO-8601 strings, the **Z** marker means UTC offset `+00:00`. It does not mean the document carries an embedded timezone attribute inside BSON Date.

### 4.3. User Timezone Belongs in the Presentation Layer

If an API returns an ISO instant:

~~~json
{"createdAt":"2025-06-01T08:30:00Z"}
~~~

the frontend can display 15:30 in Vietnam. If the business needs to remember the source/user timezone, store an extra **businessZoneId** field or similar instead of trying to embed `ZoneId` into BSON Date.

## 5. Illustrative Entity: @CreatedDate and @LastModifiedDate

~~~java
package com.example.auditing;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_orders")
public class AuditedOrder {

    @Id
    private ObjectId id;

    private String tenantId;
    private String orderNo;
    private String status;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    public AuditedOrder() {}

    public AuditedOrder(
            ObjectId id, String tenantId,
            String orderNo, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderNo = orderNo;
        this.status = status;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOrderNo() {
        return orderNo;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

This example uses a **mutable class** to illustrate Spring Data auditing updating annotated fields. With immutable entities/records, ensure compatible Spring Data constructor binding/property accessors and copying mechanisms. Do not assume every setterless record will be mutated by auditing the same way as a mutable POJO.

### 5.1. Do Not Set Audit Time via Setters or JSON Requests

`createdAt`/`updatedAt` should be governed by server/database auditing policy. Never accept auditing timestamps directly from clients if they represent trusted system metadata.

### 5.2. IDs and New-Entity Detection

Spring Data must distinguish **new entities** from **existing entities** to choose created vs. modified audit fields. Pre-assigned IDs, `@Version`, `Persistable.isNew`, and certain insert/save paths affect how new state is detected.

The test examples intentionally use **insert** for initial creation and **save** for subsequent edits. Do not conclude from `id != null` alone that every insert/save path is handled identically by auditing.

## 6. What Is DateTimeProvider?

The **org.springframework.data.auditing.DateTimeProvider** interface in Spring Data Commons supplies auditing timestamps:

~~~java
package org.springframework.data.auditing;

import java.time.temporal.TemporalAccessor;
import java.util.Optional;

@FunctionalInterface
public interface DateTimeProvider {
    Optional<TemporalAccessor> getNow();
}
~~~

This is an **explanatory signature**, not an interface you should redefine in your application.

- **getNow()** is called by the framework whenever an auditing timestamp is needed.
- **Optional<TemporalAccessor>** allows returning various `java.time` temporal types.
- **Instant** implements `TemporalAccessor` and can be wrapped in `Optional`.
- `DateTimeProvider` does not define how clocks are synchronized; the application chooses the time source.

### 6.1. Why Not Scatter Instant.now() Calls Everywhere?

~~~java
// Avoid calling wall-clock time directly in every service:
order.setCreatedAt(Instant.now());
~~~

Scattered `Instant.now()` calls:

- Are hard to replace with deterministic time in tests.
- Make it hard to guarantee all layers share the same time source.
- Force tests to use tolerance windows and sometimes `sleep`.
- Obscure timezone/policy when code mixes `LocalDateTime` and `Date`.

**Injecting Clock** establishes a single, consistently managed point of time.

### 6.2. What Does Optional.empty() Mean?

`DateTimeProvider` can return `Optional.empty()`, though that is not a way to choose UTC. It signals that the provider cannot supply a time value for that call; how auditing handles missing values depends on its contract.

For required audit timestamp fields, design the provider to return a **valid `Instant`** and test it, rather than returning empty expecting the framework to fall back to another time.

## 7. Configuring UTC Clock in Spring

~~~java
package com.example.auditing;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {

    @Bean("auditClock")
    public Clock auditClock() {
        return Clock.systemUTC();
    }
}
~~~

**Clock.systemUTC()** makes the auditing time convention explicit and lets tests swap in **Clock.fixed(...)**.

### 7.1. Clock Is an Ordinary Dependency

A service can accept it:

~~~java
import java.time.Clock;
import java.time.Instant;

public class OrderExpiryPolicy {

    private final Clock clock;

    public OrderExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

This method follows the same principle: time comes from a dependency rather than an unmockable global static call.

### 7.2. A System May Have Multiple Clocks

If the app also uses another `Clock` for billing or scheduling, use **@Qualifier("auditClock")** to identify the auditing `Clock`. Never assume there is only one `Clock` bean in every application context.

### 7.3. Clock.systemUTC Does Not Normalize Legacy Data

Switching the provider to UTC does not migrate documents previously stored as strings/`LocalDateTime` or incorrect timestamps. Perform dedicated data assessment and migration/backfill where required.

## 8. Registering DateTimeProvider with @EnableMongoAuditing

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(
    dateTimeProviderRef = "mongoAuditDateTimeProvider"
)
public class MongoAuditingConfiguration {

    @Bean("mongoAuditClock")
    public Clock mongoAuditClock() {
        return Clock.systemUTC();
    }

    @Bean("mongoAuditDateTimeProvider")
    public DateTimeProvider mongoAuditDateTimeProvider(
            @Qualifier("mongoAuditClock") Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
~~~

**@EnableMongoAuditing** activates auditing infrastructure for synchronous MongoDB mapping, and **dateTimeProviderRef** explicitly selects the bean supplying audit timestamps.

### 8.1. Wiring Structure

~~~mermaid
flowchart TD
    A["@EnableMongoAuditing(dateTimeProviderRef)"] --> B["Mongo auditing infrastructure"]
    C["Clock.systemUTC bean"] --> D["DateTimeProvider bean"]
    D --> B
    B --> E["AuditingEntityCallback"]
    E --> F["@CreatedDate / @LastModifiedDate"]
    F --> G["MappingMongoConverter -> BSON"]
~~~

### 8.2. Do Not Create Two Competing Auditing Configurations

If the application already has an `@EnableMongoAuditing` declared by another module, do not blindly add a second one. Two auditing configurations can introduce ambiguity over callbacks/providers or select unexpected beans.

Maintain a **single primary configuration source**, name beans explicitly, and test the Spring `ApplicationContext`.

### 8.3. AuditorAware Not Needed If Only Auditing Dates

**DateTimeProvider** handles timestamps. **AuditorAware** handles `createdBy`/`lastModifiedBy`. If you only declare `@CreatedDate` and `@LastModifiedDate`, there is no need to fabricate a dummy principal just to get timestamps.

### 8.4. Why Does the Provider Return () -> Optional.of(Instant.now(clock))?

~~~java
return () -> Optional.of(Instant.now(clock));
~~~

This is a supplier evaluated **when auditing requests the time**, not an `Instant` captured once at application startup. Calling `Instant.now(clock)` inside the lambda ensures each invocation reads a fresh timestamp.

Bad example:

~~~java
Instant startup = Instant.now(clock);
return () -> Optional.of(startup);
~~~

This freezes the timestamp at Spring context initialization: every document receives the startup timestamp even if users create documents hours later.

## 9. Complete Setup: Repository, Entity, and Save

Repository:

~~~java
package com.example.auditing;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditedOrderRepository
        extends MongoRepository<AuditedOrder, ObjectId> {
}
~~~

Service:

~~~java
package com.example.auditing;

import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;

@Service
public class AuditedOrderService {

    private final AuditedOrderRepository orders;

    public AuditedOrderService(AuditedOrderRepository orders) {
        this.orders = orders;
    }

    public AuditedOrder create(
            String tenantId, String orderNo) {
        AuditedOrder order = new AuditedOrder(
            null, tenantId, orderNo, "CREATED");
        return orders.insert(order);
    }

    public AuditedOrder markPaid(AuditedOrder order) {
        order.setStatus("PAID");
        return orders.save(order);
    }
}
~~~

With auditing enabled, `insert`/`save` through the mapping lifecycle populates **@CreatedDate** and **@LastModifiedDate** using `DateTimeProvider`.

### 9.1. Choose Methods by Semantics

- **insert** signals creating a new document and fails if the ID already exists.
- **save** can insert or replace/update depending on entity detection and `MongoTemplate`/repository semantics.
- Auditing must know whether the entity is **new** or **existing** to distinguish `createdAt` from `updatedAt`.

Do not use **save** as an unchecked upsert merely because it is "shorter", especially on entities with tenants, versions, and other invariants.

### 9.2. @Version and New Entities

If an entity has `@Version`, Spring Data can use the version to determine newness. This ties directly into auditing `isNew` detection. Where exact behavior matters, test **insert -> save -> save** with your actual entity and version type. In the service above, we deliberately pass **id=null** when creating the entity; Spring Data handles ID generation during insert. If you pre-assign an `ObjectId` before the first insert, ID-based `isNew` detection may treat the entity as existing, leaving `@CreatedDate` unpopulated even though the insert creates a new document. When IDs must be pre-assigned, use `@Version`/`Persistable` or an appropriate new-state strategy and test it.

### 9.3. Cases That Bypass This Service

The raw MongoDB driver, migration jobs, or another application may write to the same collection without knowing about Spring's `DateTimeProvider`. Spring's automatic auditing does not replace collection validation, write permissions, or timestamp conventions across external systems.

## 10. modifyOnCreate and setDates

**@EnableMongoAuditing** offers attributes controlling date population and whether modified dates are set on creation.

For example, when creation should populate only `createdAt` and leave `updatedAt` empty:

~~~java
@EnableMongoAuditing(
    dateTimeProviderRef = "mongoAuditDateTimeProvider",
    modifyOnCreate = false
)
~~~

With this setting, **@LastModifiedDate** is not automatically populated at creation time unless set elsewhere. After saving an existing entity, `updatedAt` is populated by auditing.

### 10.1. Default Values

In standard Spring Data versions, **modifyOnCreate** defaults to **true**. Thus a new entity receives both `createdAt` and `updatedAt` on initial creation.

**Do not write tests assuming `updatedAt == null`** unless `modifyOnCreate=false` has been explicitly configured.

### 10.2. setDates=false

~~~java
@EnableMongoAuditing(
    dateTimeProviderRef = "mongoAuditDateTimeProvider",
    setDates = false
)
~~~

This option disables auditing's automatic assignment of date fields under that configuration. It is **not** a setting to "change timezone while keeping automatic timestamps".

If `setDates` is disabled, the service or database needs another timestamp mechanism. Understand why before turning it off.

### 10.3. @CreatedBy and @LastModifiedBy Are Independent of Date Provider

`DateTimeProvider` does not determine the username. To record creator/modifier actors, configure **`AuditorAware`** (or its reactive counterpart) alongside controlled authentication policies.

## 11. In Which Lifecycle Phase Does Auditing Run?

In Spring Data MongoDB mapping, auditing uses **AuditingEntityCallback** during the **BeforeConvertCallback** phase. This gives Spring a chance to set `createdAt`/`updatedAt` on the entity **before `MongoConverter` builds the BSON Document**.

~~~mermaid
sequenceDiagram
    participant R as Repository/MongoTemplate
    participant A as AuditingEntityCallback
    participant P as DateTimeProvider
    participant M as MappingMongoConverter
    participant B as MongoDB
    R->>A: BeforeConvert(entity)
    A->>P: getNow()
    P-->>A: Optional(Instant)
    A-->>R: Entity with createdAt/updatedAt
    R->>M: Entity -> BSON Document
    M-->>R: createdAt/updatedAt as BSON Date
    R->>B: insert/save
    B-->>R: Write result
~~~

Other lifecycle events/callbacks may run in the pipeline; the diagram omits them to highlight where the date provider plugs in.

### 11.1. BeforeConvert vs. BeforeSave

**BeforeSaveCallback** receives both the entity and the already-converted `Document`. Modifying only `entity.updatedAt` inside `BeforeSaveCallback` can leave the old `updatedAt` inside the `Document`, because the converter does not run again automatically.

**AuditingEntityCallback** runs before conversion, so timestamps set on the persistent entity are serialized into BSON by the converter.

### 11.2. Ordering with Custom BeforeConvertCallback

Spring Data supports callback ordering, and the auditing callback has its own order within the `BeforeConvert` phase. If you also have a custom `BeforeConvertCallback` setting `createdAt`/`updatedAt`, the two callbacks can conflict.

Never have two mechanisms claiming ownership over timestamps without an explicit ordering contract. Best practice is letting auditing own `createdAt`/`updatedAt` while custom callbacks handle other metadata.

### 11.3. setDates and isNew

Auditing must determine whether an entity is new or existing. Pre-assigned IDs, custom `Persistable`, or versions can alter the result. Test with your project's actual entity/ID policy rather than relying on a single simplified rule.

## 12. Clock.fixed: Eliminating Real-Time Dependency

Suppose a test needs a controlled point in time:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Instant expected = Instant.parse(
    "2025-06-01T08:30:00.123Z");

Clock fixed = Clock.fixed(expected, ZoneOffset.UTC);

Instant actual = Instant.now(fixed);

assert actual.equals(expected);
~~~

**Clock.fixed** always returns the exact same instant across calls to `instant()` on that clock. Tests no longer depend on CPU speed, thread scheduling, OS timezone, or wall-clock time.

### 12.1. Wiring Clock.fixed to DateTimeProvider

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import org.springframework.data.auditing.DateTimeProvider;

Clock fixed = Clock.fixed(
    Instant.parse("2025-06-01T08:30:00.123Z"),
    ZoneOffset.UTC
);

DateTimeProvider provider =
    () -> Optional.of(Instant.now(fixed));
~~~

When auditing calls `provider.getNow()`, it gets the fixed `Instant`. This matches the production design, differing only in the injected `Clock`.

### 12.2. Avoid Tests Relying on Arbitrary Tolerance Windows

Counterexample:

~~~java
Instant before = Instant.now();
repository.insert(order);
Instant after = Instant.now();

assertThat(saved.getCreatedAt())
    .isBetween(before, after);
~~~

This can serve as a rough integration smoke test in some situations, yet it is noisy due to clock skew, precision truncation, callback timing, and CI load. If the goal is proving **the provider was used**, comparing against **a fixed `Instant`** is far clearer.

### 12.3. Tests Do Not Need Sleep

Another counterexample:

~~~java
repository.insert(order);
Thread.sleep(1000);
repository.save(order);
~~~

Sleeping slows test runs and still fails to guarantee deterministic behavior under load or simulated clocks. To verify `updatedAt` changes, control `Clock`/`DateTimeProvider` instead of waiting for wall-clock time to elapse.

## 13. Pure DateTimeProvider Unit Test Without MongoDB

Start with a small unit test:

~~~java
package com.example.auditing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.data.auditing.DateTimeProvider;

class DateTimeProviderUnitTest {

    @Test
    void returnsTheExactInstantFromInjectedClock() {
        Instant instant = Instant.parse(
            "2025-06-01T08:30:00.123Z");

        Clock clock = Clock.fixed(instant, ZoneOffset.UTC);
        DateTimeProvider provider =
            () -> Optional.of(Instant.now(clock));

        Optional<TemporalAccessor> result =
            provider.getNow();

        assertThat(result).isPresent();
        assertThat(Instant.from(result.orElseThrow()))
            .isEqualTo(instant);
        assertThat(clock.getZone())
            .isEqualTo(ZoneOffset.UTC);
    }
}
~~~

This test proves the provider reads from the injected `Clock` instead of calling zero-arg `Instant.now()`. **It does not yet prove Mongo auditing infrastructure uses that bean.** That requires an integration test.

### 13.1. Why Instant.from?

`DateTimeProvider` returns **`TemporalAccessor`**. **`Instant.from(temporalAccessor)`** converts a `TemporalAccessor` carrying instant fields back into an `Instant`. If a provider returned `LocalDateTime`, it could not be converted unambiguously to an `Instant` without knowing an offset/zone.

### 13.2. Testing Clock Timezone

A `Clock` can carry a different `ZoneId`, yet:

~~~java
Clock inHcm = Clock.fixed(
    Instant.parse("2025-06-01T08:30:00Z"),
    java.time.ZoneId.of("Asia/Ho_Chi_Minh"));

Instant sameMoment = Instant.now(inHcm);
~~~

**sameMoment** is still **2025-06-01T08:30:00Z**. The `Clock`'s `ZoneId` affects operations deriving local date/time (like `LocalDate.now(clock)`), not the underlying instant.

This is why auditing should return **`Instant`** rather than converting to `LocalDateTime` in the host's timezone.

## 14. Integration Test with @DataMongoTest and Fixed Clock

To verify Spring Data actually uses `DateTimeProvider`, create a MongoDB test slice with an auditing configuration **dedicated to testing**.

Example:

~~~java
package com.example.auditing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(FixedClockMongoAuditTest.AuditTestConfiguration.class)
class FixedClockMongoAuditTest {

    private static final Instant FIXED_INSTANT =
        Instant.parse("2025-06-01T08:30:00.123Z");

    @Autowired MongoTemplate template;

    @TestConfiguration
    @EnableMongoAuditing(
        dateTimeProviderRef = "fixedAuditDateTimeProvider")
    static class AuditTestConfiguration {

        @Bean("fixedAuditClock")
        Clock fixedAuditClock() {
            return Clock.fixed(
                FIXED_INSTANT, ZoneOffset.UTC);
        }

        @Bean("fixedAuditDateTimeProvider")
        DateTimeProvider fixedAuditDateTimeProvider(
                @Qualifier("fixedAuditClock") Clock clock) {
            return () -> Optional.of(Instant.now(clock));
        }
    }

    @Test
    void insertUsesFixedAuditInstantAndPersistsBsonDate() {
        AuditedOrder order = new AuditedOrder(
            null, "TEST-shop-a", "ORD-FIXED-001", "CREATED");

        ObjectId insertedId = null;
        try {
            AuditedOrder inserted = template.insert(order);
            insertedId = inserted.getId();

            assertThat(insertedId).isNotNull();
            assertThat(inserted.getCreatedAt())
                .isEqualTo(FIXED_INSTANT);
            assertThat(inserted.getUpdatedAt())
                .isEqualTo(FIXED_INSTANT);

            Document raw = template
                .getCollection("audit_orders")
                .find(new Document("_id", insertedId))
                .first();

            assertThat(raw).isNotNull();
            assertThat(raw.getDate("createdAt").toInstant())
                .isEqualTo(FIXED_INSTANT);
            assertThat(raw.getDate("updatedAt").toInstant())
                .isEqualTo(FIXED_INSTANT);
        } finally {
            if (insertedId != null) {
                template.remove(
                    Query.query(
                        Criteria.where("_id").is(insertedId)),
                    AuditedOrder.class
                );
            }
        }
    }
}
~~~

**Requirements:** runs against a test MongoDB instance, with **spring-boot-starter-data-mongodb**, JUnit 5, Spring Boot Test, AssertJ, and project-provided test environment configuration (e.g., Testcontainers). Never run tests against a production database.

### 14.1. Why Use @TestConfiguration?

`AuditTestConfiguration` declares a test-specific **Clock.fixed** and **DateTimeProvider** for the test slice without modifying production time configuration. Having `@EnableMongoAuditing` ensures auditing is enabled in the context under test.

If the test application accidentally imports another `@EnableMongoAuditing` configuration, consolidate/adjust the test configuration rather than letting two configs compete. One context with one explicit `DateTimeProvider` choice is far easier to reason about.

### 14.2. Why Leave id=null Before Insert?

Auditing distinguishes new/existing entities. For a new POJO entity using `@Id ObjectId` without `@Version`, **id=null** ensures new-state detection is not confused by a pre-assigned ID.

### 14.3. Why Compare Raw BSON?

Checking only:

~~~java
assertThat(inserted.getCreatedAt())
    .isEqualTo(FIXED_INSTANT);
~~~

only shows the Java entity holds the value. Reading:

~~~java
raw.getDate("createdAt").toInstant()
~~~

proves the field was actually converted to **BSON Date** and persisted in MongoDB.

### 14.4. Test Precision

`FIXED_INSTANT` has **123 milliseconds** and no sub-millisecond nanoseconds. Thus the **Instant before/after the MongoDB round-trip matches exactly**, needing no tolerance window.

If a test uses an `Instant` like `.123456789Z`, compare raw BSON after truncating to milliseconds per the conversion policy.

### 14.5. Test Isolation

The example cleans up by the exact inserted ID, strictly within the test database. To run tests reliably in parallel, use unique `orderNo`/test tenants or a dedicated database/schema per suite.

## 15. Testing Advancing Time Without Waiting for Real Time

`Clock.fixed` cannot "advance" inside the same instance. To test that **createdAt stays unchanged** while **updatedAt advances**, there are two options:

1. Use two test application contexts with `Clock.fixed` at two different instants.
2. Use a **controllable `Clock`** in tests, never using that class in production.

For a single test verifying both insert and save in the same application context, option 2 is convenient.

### 15.1. Thread-Safe Controllable Clock

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> now;
    private final ZoneId zone;

    public AdjustableClock(Instant initial) {
        this(new AtomicReference<>(
            Objects.requireNonNull(initial)),
            ZoneOffset.UTC);
    }

    private AdjustableClock(
            AtomicReference<Instant> now,
            ZoneId zone) {
        this.now = now;
        this.zone = zone;
    }

    public void setInstant(Instant instant) {
        now.set(Objects.requireNonNull(instant));
    }

    @Override
    public Instant instant() {
        return now.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new AdjustableClock(now, newZone);
    }
}
~~~

**AtomicReference** provides basic thread-safe reads and updates of `Instant`, though it does not turn business operations into transactions. This is strictly a deliberately mutable **test clock**.

### 15.2. Never Use a Test Clock as a Production Clock

Production must use `Clock.systemUTC()` or an organization-managed time source. Never expose an endpoint or debug command capable of calling `setInstant` on a production auditing clock.

### 15.3. Why Does withZone Share the Same AtomicReference?

Two `Clock` instances with different zones can represent the same timeline. Because the test clock shares the same **`AtomicReference<Instant>`**, updating the instant makes all derived `withZone` clocks observe the same time value.

### 15.4. Fixed Clock vs. Controllable Clock Solve Different Needs

| Test Need | Time Source |
| --- | --- |
| Verify insert uses an exact timestamp | `Clock.fixed` |
| Verify second modification gets a newer timestamp | `AdjustableClock` |
| Verify business expiry after 5 minutes | `AdjustableClock` or `Clock.offset` |
| Verify timezone presentation | Explicit `Clock`/`ZoneId` + conversion |
| Verify BSON Date persistence | Fixed clock at millisecond precision |

No **`Thread.sleep`** is needed for any of these tests.

## 16. Integration Test: createdAt Unchanged, updatedAt Advances

Create another test slice with `AdjustableClock` and `DateTimeProvider`.

~~~java
package com.example.auditing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.Optional;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(AdvancingClockMongoAuditTest.AuditTestConfiguration.class)
class AdvancingClockMongoAuditTest {

    private static final Instant CREATED = Instant.parse(
        "2025-06-01T08:30:00.000Z");

    private static final Instant MODIFIED = Instant.parse(
        "2025-06-01T08:35:00.000Z");

    @Autowired MongoTemplate template;
    @Autowired AdjustableClock clock;

    @TestConfiguration
    @EnableMongoAuditing(
        dateTimeProviderRef = "advancingAuditDateTimeProvider")
    static class AuditTestConfiguration {

        @Bean
        AdjustableClock testAuditClock() {
            return new AdjustableClock(CREATED);
        }

        @Bean("advancingAuditDateTimeProvider")
        DateTimeProvider provider(AdjustableClock clock) {
            return () -> Optional.of(clock.instant());
        }
    }

    @Test
    void savePreservesCreatedDateAndAdvancesModifiedDate() {
        ObjectId savedId = null;
        clock.setInstant(CREATED);

        try {
            AuditedOrder order = template.insert(
                new AuditedOrder(
                    null, "TEST-shop-a",
                    "ORD-ADVANCING-001", "CREATED")
            );
            savedId = order.getId();

            assertThat(order.getCreatedAt())
                .isEqualTo(CREATED);
            assertThat(order.getUpdatedAt())
                .isEqualTo(CREATED);

            clock.setInstant(MODIFIED);
            order.setStatus("PAID");
            AuditedOrder changed = template.save(order);

            assertThat(changed.getCreatedAt())
                .isEqualTo(CREATED);
            assertThat(changed.getUpdatedAt())
                .isEqualTo(MODIFIED);

            Document raw = template
                .getCollection("audit_orders")
                .find(new Document("_id", savedId))
                .first();

            assertThat(raw).isNotNull();
            assertThat(raw.getString("status"))
                .isEqualTo("PAID");
            assertThat(raw.getDate("createdAt").toInstant())
                .isEqualTo(CREATED);
            assertThat(raw.getDate("updatedAt").toInstant())
                .isEqualTo(MODIFIED);
        } finally {
            if (savedId != null) {
                template.remove(
                    Query.query(
                        Criteria.where("_id").is(savedId)),
                    AuditedOrder.class
                );
            }
        }
    }
}
~~~

This test focuses on **auditing across insert then save** without relying on wall-clock time. Both timestamps are asserted against exact values and verified back in MongoDB.

### 16.1. Why Use Two Test Contexts?

`FixedClockMongoAuditTest` and `AdvancingClockMongoAuditTest` have separate configurations so they do not share a clock bean in conflicting ways. They are **two independent test classes** in two Java source files, each with its own inner `TestConfiguration`.

### 16.2. Context Caching Risks Under Parallel Tests

Spring Test caches application contexts. If multiple tests mutate the same `AdjustableClock` bean concurrently, test results can interfere with each other. Keep such suites isolated, reset the clock at the start of each test, never share a mutable clock across parallel tests, or use separate contexts per configuration.

### 16.3. Testing modifyOnCreate=false

If you enable:

~~~java
@EnableMongoAuditing(
    dateTimeProviderRef = "advancingAuditDateTimeProvider",
    modifyOnCreate = false
)
~~~

then the insert assertion should change to expect **`updatedAt` not yet populated** (assuming the entity started null), and after save `updatedAt` becomes `MODIFIED`. Do not copy default-configuration assertions verbatim into a test with `modifyOnCreate=false`.

## 17. Writing Testable Services Without MongoDB

Even outside auditing, services need timestamps for business rules, such as payment deadlines:

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public class PaymentDeadlinePolicy {

    private final Clock clock;

    public PaymentDeadlinePolicy(Clock clock) {
        this.clock = clock;
    }

    public Instant dueIn(Duration duration) {
        if (duration.isNegative()) {
            throw new IllegalArgumentException(
                "Duration must not be negative");
        }
        return Instant.now(clock).plus(duration);
    }
}
~~~

Unit test:

~~~java
Instant origin = Instant.parse(
    "2025-06-01T08:30:00Z");

PaymentDeadlinePolicy policy = new PaymentDeadlinePolicy(
    Clock.fixed(origin, java.time.ZoneOffset.UTC));

Instant deadline = policy.dueIn(
    java.time.Duration.ofMinutes(15));

assertThat(deadline).isEqualTo(
    Instant.parse("2025-06-01T08:45:00Z"));
~~~

**The same `Clock`** can serve both auditing and business policies if they share the same time-source requirements. However, distinguish **action execution time** from **MongoDB commit time** or **downstream event processing time**.

## 18. UTC in API Responses and Display

An API should publish a clear time contract, such as ISO-8601 UTC instants:

~~~json
{
  "id": "507f1f77bcf86cd799439011",
  "createdAt": "2025-06-01T08:30:00Z",
  "updatedAt": "2025-06-01T08:35:00Z"
}
~~~

The frontend can format it as:

~~~text
UTC:              2025-06-01 08:35
Asia/Ho_Chi_Minh: 2025-06-01 15:35
~~~

Both lines represent the exact same `Instant`. Never convert to a local string and strip the zone/offset if data crosses system boundaries.

### 18.1. When Business Dates Are Needed

"Delivery date" or "store reporting date" is not always a UTC date. If a business rule defines dates in **Asia/Ho_Chi_Minh**, store or explicitly resolve the **store's `ZoneId`**, then convert `Instant` to `LocalDate` in that zone when calculating dates.

Do not force every `LocalDate` business field into midnight UTC `Instant` without reviewing business policy.

### 18.2. Store Original Offset Separately When Needed

BSON Date does not store the original offset. If you must know that a customer confirmed at "15:35 +07:00", store **`Instant` + `originalOffset`/`originalZoneId`** per the business contract. Avoid adding offsets just for display when the frontend already knows the viewer's timezone.

### 18.3. Avoid String Sorting for Audit Dates When BSON Date Fits

If documents store timestamps as ISO strings with inconsistent offsets or formats, lexical sorting may fail to reflect the real timeline. Use **BSON Date** with appropriate time indexes, and query with `Instant`/`Date` through Spring mapping.

## 19. How Does the JVM Timezone Matter?

Java has a **`systemDefault` `ZoneId`**, which can differ between developer machines, containers, and CI:

~~~java
java.time.ZoneId defaultZone =
    java.time.ZoneId.systemDefault();
~~~

If code calls:

~~~java
LocalDateTime.now();
~~~

the value depends on the system zone. If code calls:

~~~java
Instant.now(clock);
~~~

it yields an instant from `Clock`; formatting in another timezone is a separate presentation step.

### 19.1. Does Setting JVM Timezone to UTC Solve Everything?

Setting the default JVM timezone to UTC can reduce some legacy conversion bugs. Yet it does not replace:

- Using `Instant` instead of `LocalDateTime` for timestamps.
- Injecting `Clock` for deterministic tests.
- Defining `dateTimeProviderRef`.
- Verifying Java/BSON temporal converters.
- Specifying business timezones for calendar dates/store hours.

The JVM default timezone is an environment setting, whereas `DateTimeProvider` is an application time-source policy.

### 19.2. Why Can LocalDateTime Cause Bugs Around DST?

In regions observing Daylight Saving Time, certain local times do not exist or occur twice. Because `LocalDateTime` lacks a `ZoneId`, it carries insufficient information to identify a single instant uniquely.

**`Instant` + `ZoneId` at the display/business boundary** makes DST resolution explicit.

## 20. Entity Save Auditing Differs from MongoTemplate.updateFirst

This is one of the most critical pitfalls when applying auditing in production.

~~~java
AuditedOrder order = repository.findById(id)
    .orElseThrow();
order.setStatus("PAID");
repository.save(order);
~~~

On the **`repository.save(entity)`** path, the mapping lifecycle runs **`AuditingEntityCallback`** in `BeforeConvert` and updates the **`@LastModifiedDate`** field.

However:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("tenantId").is(tenantId)
);

Update update = new Update()
    .set("status", "PAID");

mongoTemplate.updateFirst(
    query, update, AuditedOrder.class);
~~~

is an **operator-based update**. It does not instantiate a full entity and pass it through `BeforeConvertCallback` like a normal `save(entity)`.

**Do not assume `DateTimeProvider` is called to update `@LastModifiedDate` in every `updateFirst`**, even if the entity class has the annotation.

### 20.1. Synchronizing Timestamps in Query Updates

If the app chooses the **application clock** as its time source:

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Update;

Instant now = Instant.now(auditClock);

Update update = new Update()
    .set("status", "PAID")
    .set("updatedAt", now);
~~~

The service explicitly updates **both fields**, using a helper/policy backed by the same `Clock` as the provider so write paths do not diverge.

### 20.2. Using $currentDate for Server Time

MongoDB supports:

~~~javascript
db.audit_orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    tenantId: "shop-a"
  },
  {
    $set: { status: "PAID" },
    $currentDate: { updatedAt: true }
  }
);
~~~

Spring Data:

~~~java
new Update()
    .set("status", "PAID")
    .currentDate("updatedAt");
~~~

Here **`updatedAt` is determined by MongoDB Server**, not the `Clock` in `DateTimeProvider`. The two mechanisms can produce very close timestamps, though you must never assume they are identical.

### 20.3. Choosing a Consistent Policy

| Write Path | Timestamp Policy |
| --- | --- |
| `Repository.save(entity)` | `@LastModifiedDate` via `DateTimeProvider` |
| `MongoTemplate.insert(entity)` | `@CreatedDate`/`@LastModifiedDate` via auditing lifecycle |
| `MongoTemplate.updateFirst(query,update)` | Set `updatedAt` from `Clock` or `$currentDate` |
| `MongoTemplate.findAndModify(query,update)` | Explicit `updatedAt` strategy |
| `BulkOperations` | Add `updatedAt` to each `UpdateDefinition` if needed |
| Raw `MongoCollection.updateOne` | Explicitly add field per server policy |
| Writers in other applications | Share schema/time contract or separate DB-side policy |

**Do not unknowingly let half your documents use application UTC while the other half use local JVM time.** If you choose the app clock for auditing and MongoDB server time for operator updates, account for potential skew and design comparison logic accordingly.

### 20.4. Test Distinguishing save and updateFirst

Integration tests should:

1. Insert an entity with `Clock=FIRST`.
2. Run `updateFirst` with `Clock=SECOND` **without setting `updatedAt`**.
3. Verify `updatedAt` did not auto-change via the auditing lifecycle.
4. Run `updateFirst` with **`set("updatedAt", Instant.now(clock))`**.
5. Verify raw BSON Date changes to `SECOND`.
6. Run `save(entity)` with `Clock=THIRD` and verify `@LastModifiedDate` becomes `THIRD`.

This test is far more valuable than merely checking that annotations exist in source code.

## 21. Reactive Auditing: @EnableReactiveMongoAuditing

In the **`ReactiveMongoTemplate`/`ReactiveMongoRepository`** stack, Spring Data MongoDB provides the **`@EnableReactiveMongoAuditing`** configuration annotation.

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;

@Configuration
@EnableReactiveMongoAuditing(
    dateTimeProviderRef = "reactiveAuditDateTimeProvider")
public class ReactiveMongoAuditingConfiguration {

    @Bean("reactiveAuditClock")
    Clock reactiveAuditClock() {
        return Clock.systemUTC();
    }

    @Bean("reactiveAuditDateTimeProvider")
    DateTimeProvider reactiveAuditDateTimeProvider(
            @Qualifier("reactiveAuditClock") Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
~~~

**`DateTimeProvider` here remains a synchronous, lightweight, non-I/O time source.** Reactive auditing integrates into the reactive entity mapping lifecycle; it does not require a Publisher just to read the clock.

### 21.1. Why Not Call an HTTP Time Server Inside the Provider?

If `getNow()` makes synchronous network calls, it blocks the write path. If synchronization with an external time source is needed, handle it via infrastructure clock synchronization or a controlled time service/policy; `DateTimeProvider` should return timestamps quickly and deterministically.

### 21.2. Reactive Save Executes Only on Subscription

~~~java
Mono<AuditedOrder> write =
    reactiveMongoTemplate.insert(
        new AuditedOrder(
            null, "shop-a", "ORD-RX-001", "CREATED"));
~~~

This Publisher describes the operation; auditing and insert execute when the pipeline is **subscribed**, not when the `write` variable is constructed.

**Do not call `subscribe()` inside a service** and also return the same `Mono` to WebFlux, as that can trigger two writes/callbacks and cause a duplicate key error.

### 21.3. Reactive Repository and Auditing

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveAuditedOrderRepository
        extends ReactiveMongoRepository<AuditedOrder, ObjectId> {
}
~~~

A reactive repository participates in the auditing mapping lifecycle per reactive configuration. Using a blocking **`MongoRepository`** inside a Reactor pipeline defeats reactive access.

### 21.4. Testing Reactive with StepVerifier

~~~java
Instant fixed = Instant.parse(
    "2025-06-01T08:30:00.123Z");

StepVerifier.create(
    reactiveRepository.insert(new AuditedOrder(
        null, "TEST-shop-a", "ORD-RX-001", "CREATED"))
)
.assertNext(saved -> {
    assertThat(saved.getCreatedAt()).isEqualTo(fixed);
    assertThat(saved.getUpdatedAt()).isEqualTo(fixed);
})
.verifyComplete();
~~~

This snippet assumes **`ReactiveMongoAuditingConfiguration`** in tests configures `DateTimeProvider` with `Clock.fixed(fixed, UTC)`, along with **`reactor-test`** and an injected repository bean. Do not leave production `Clock.systemUTC()` active and expect a test to match a fixed instant.

### 21.5. Reactive Transactions Are a Separate Concern

**@EnableReactiveMongoAuditing** only enables auditing. When a service needs multi-document transactions, use **`ReactiveMongoTransactionManager`** and a reactive transactional context per documentation; `DateTimeProvider` does not replace a transaction manager.

## 22. Auditing in MongoDB Transactions

A service can write multiple documents:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public AuditedOrder createWithOutbox(
        AuditedOrder order) {
    AuditedOrder saved = orderRepository.insert(order);
    outboxRepository.insert(
        buildOrderCreatedEvent(saved));
    return saved;
}
~~~

Here **`orderRepository`, `outboxRepository`, and `buildOrderCreatedEvent`** are domain components defined in your project.

Auditing timestamps are assigned when the mapper processes the entity inside the transaction. **They are not synonymous with commit time**; subsequent steps in the transaction can still take time.

### 22.1. Transaction Rollback Does Not Rewind the Clock

~~~text
T0: DateTimeProvider returns 08:30:00
T1: Order mapped with createdAt=08:30:00
T2: Outbox insert fails
T3: Transaction rolls back
~~~

The timestamp was created in memory, yet the transaction's document did not commit. If the application retries at T4, the provider may return a newer timestamp unless using `Clock.fixed` or a separately defined business-event timestamp.

### 22.2. Can Retries Change createdAt?

If a transaction attempt aborts and retries as a new entity, `DateTimeProvider` can supply a newer timestamp. That usually reflects the attempt write time rather than when the client sent the request.

If business logic requires a **`requestedAt`** that stays constant across retries, store a dedicated **`requestedAt`** business field captured at request entry rather than forcing `@CreatedDate` to carry that meaning.

### 22.3. Commit Time and Write Time Differ

Timestamps are set at callback/mapping time. Successful commit time, the moment replicas observe the document, and downstream consumer processing time can all differ. Do not use `updatedAt` to conclude "exactly when the transaction committed" without an appropriate event/commit time source.

### 22.4. Effect of Write Concern

A document having a valid `updatedAt` does not prove data is majority-committed unless the write concern enforces it. `DateTimeProvider` only supplies the time, whereas data durability is governed by MongoDB write concern and transaction options.

## 23. Multiple Instances: UTC Is Necessary but Not Sufficient

Suppose there are two instances:

~~~text
App A: clock +400ms relative to reference time
App B: clock -300ms relative to reference time
~~~

Both use **Clock.systemUTC()**, yet generated timestamps can still differ by ~700ms.

### 23.1. Why Must updatedAt Never Be Used as a Strict Sequence?

An operation processed later can carry an earlier `updatedAt` than an earlier operation due to:

- Clock skew between nodes.
- Retries or queue delays.
- One transaction starting earlier yet committing later.
- Precision capped at milliseconds in BSON Date.
- Two events sharing the exact same millisecond timestamp.

**Timestamps are neither unique sequence numbers nor a total order.**

When concurrency guards are needed:

- Use `@Version`/optimistic locking.
- Use update filters with expected state/version.
- Use unique operation IDs.
- Use event sequences or a transactional outbox.

### 23.2. NTP / Time Synchronization

Production needs OS/container/VM clock synchronization, drift measurement, and alerts if skew exceeds thresholds. Setting `ZoneId` to UTC on `Clock` does not fix clock drift.

### 23.3. When to Use Server-Generated Time?

If more consistent MongoDB-side timestamps are required for certain operator updates, **`$currentDate`** or pipeline updates with **`$$NOW`** (per server/API support) may fit.

However, that **differs from the app's `DateTimeProvider` source**. Choose and document a policy—application time for entity auditing vs. database time for direct write operations—and test accordingly.

### 23.4. TTL Is a Different Use Case

MongoDB TTL requires a **BSON Date** field and an appropriate TTL index, yet TTL cleanup runs asynchronously. If **`expiresAt`** is a business expiration instant, the service must still check the deadline during validation instead of relying solely on TTL deletion.

Do not use `@CreatedDate` as a mutable deadline unless business rules truly base expiration strictly on creation time.

## 24. Querying by UTC Time Ranges

With orders storing **`createdAt`** as BSON Date, Spring Data can query using `Instant`:

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Instant from = Instant.parse(
    "2025-06-01T00:00:00Z");

Instant to = Instant.parse(
    "2025-06-02T00:00:00Z");

Query query = Query.query(
    Criteria.where("tenantId").is("shop-a")
        .and("createdAt").gte(from).lt(to)
);
~~~

This is a half-open interval **[from, to)**: inclusive start, exclusive end. It prevents overlap between consecutive days/intervals.

### 24.1. When Business Day Is in Vietnam

June 1 in **Asia/Ho_Chi_Minh** is:

~~~text
Local start: 2025-06-01T00:00:00+07:00
UTC start:   2025-05-31T17:00:00Z
Local end:   2025-06-02T00:00:00+07:00
UTC end:     2025-06-01T17:00:00Z
~~~

Example:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone =
    ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate day = LocalDate.of(2025, 6, 1);

Instant from = day.atStartOfDay(
    businessZone).toInstant();

Instant to = day.plusDays(1)
    .atStartOfDay(businessZone)
    .toInstant();
~~~

Store timestamps as UTC `Instant`, yet **compute day boundaries in the business zone**. Do not compute a UTC day and apply it to international stores indiscriminately.

### 24.2. DST and Day Ranges

In DST regions, a local calendar day may not be 24 hours long. Use **`startOfDay` of the current day and `startOfDay` of the next day** in the `ZoneId`, rather than `from.plus(Duration.ofHours(24))`, when targeting local calendar days.

### 24.3. Indexes

If frequently querying orders by tenant and `createdAt`:

~~~javascript
db.audit_orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_audit_orders_tenant_created" }
);
~~~

Choose indexes based on filters, sorts, cardinality, and workload; never index every audit field just because it has an annotation. Inspect `explain` and index overhead on write-heavy collections.

## 25. Common Errors When Configuring DateTimeProvider

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `createdAt`/`updatedAt` both null | `@EnableMongoAuditing` not enabled, bean unscanned, or entity not recognized as new | Check Spring context, entity state, run real insert test |
| `createdAt` null yet `updatedAt` populated on insert | Pre-assigned ID causes `isNew=false` or different policy | Test `isNew`, leave ID null on create, or use `Persistable`/`@Version` |
| Tests always see a startup timestamp | Provider captured `Instant` at `@Bean` creation | Put `Instant.now(clock)` **inside** the lambda |
| Tests depend on CI host clock | Code calls `Instant.now()` directly | Inject `Clock.fixed` from test context |
| `updatedAt` equals `createdAt` on creation | `modifyOnCreate` defaults to `true` | If undesired, set `modifyOnCreate=false` |
| `updatedAt` null on new entity | `modifyOnCreate=false`, `setDates=false`, or other init | Check config and tests |
| `updatedAt` unchanged after `updateFirst` | Query update skips `BeforeConvert` auditing | Set `updatedAt` or `$currentDate` explicitly |
| `updatedAt` from raw driver ignores `Clock` | Driver does not know `DateTimeProvider` | Apply timestamp policy to every writer |
| Timestamp off by 7 hours in UI | Confusing UTC instant with local time | Format with `ZoneId`; do not alter `Instant` |
| Timestamps skew across nodes despite UTC | Clock drift | Synchronize host clocks, monitor NTP |
| Assertions off by micro/nanoseconds | BSON Date only stores milliseconds | Truncate to millis or use fixed millis |
| `LocalDateTime` reads differently after deploy | Default zone / JDK conversion mismatch | Use `Instant` and explicit temporal conversion |
| Test `updatedAt` does not advance | `Clock.fixed` always returns the same time | Use `AdjustableClock` or two fixed contexts |
| Two `DateTimeProvider` beans | Missing/wrong `dateTimeProviderRef` or duplicate configs | Specify bean name clearly, use one auditing config |
| `@CreatedBy` empty despite valid dates | Missing `AuditorAware` | Separate actor and time policies |
| Reactive insert gets no dates | Enabled imperative instead of reactive auditing | Use `@EnableReactiveMongoAuditing` |
| Reactive test never runs insert | `Mono` was never subscribed | Use `StepVerifier`/compose publisher |
| Java entity reads right yet raw BSON type is wrong | Conversion or raw writer | Check `raw.getDate` and converters |
| Commit time differs from `createdAt` | Timestamp assigned at callback before commit | Distinguish write preparation from commit instant |
| `updatedAt` decreases on a newer request | Clock skew or write from stale snapshot/clock source | Never use timestamps as versions; use `@Version` |
| `DateTimeProvider` blocks or throws | Provider calls network/time service | Use lightweight `Clock`; fail-fast/monitor time source |

### 25.1. Diagnostic Checklist for Unaudited Documents

1. Identify the write operation: `repository.insert/save`, `MongoTemplate.updateFirst`, or raw driver?
2. Verify the entity has **`@CreatedDate`/`@LastModifiedDate`** with compatible `java.time` types.
3. Verify **`@EnableMongoAuditing` / `@EnableReactiveMongoAuditing`** is registered.
4. Verify **`dateTimeProviderRef`** points to the right `DateTimeProvider` bean.
5. Confirm the provider reads **`Instant.now(clock)`** inside `getNow()`, not at startup.
6. Determine whether Spring Data sees the entity as **new** or **existing**.
7. Check **`modifyOnCreate`** and **`setDates`**.
8. Read the raw BSON document to inspect field name, BSON type, and milliseconds.
9. Check timezone conversion, client formatting, and clock drift.
10. Reproduce with `Clock.fixed`/`AdjustableClock` in tests instead of adding `sleep`.

## 26. Common Pitfalls in Time Testing

### 26.1. Relying on Wall Clock Instead of a Deterministic Value

~~~java
// Avoid if asserting exact equality:
assertThat(saved.getCreatedAt())
    .isEqualTo(Instant.now());
~~~

The two calls to `Instant.now()` execute at **different instants**, so the test can fail even when auditing works.

**Replace with** `Clock.fixed` sharing the exact `Instant` injected into the provider.

### 26.2. Sleeping to Wait for updatedAt to Change

~~~java
// Avoid:
Thread.sleep(50);
~~~

Sleeping slows tests and does not prove the clock/provider is wired. Use `AdjustableClock.setInstant`.

### 26.3. Comparing Instant Nanoseconds to BSON Milliseconds

~~~java
import java.time.temporal.ChronoUnit;

Instant expected = Instant.parse(
    "2025-06-01T08:30:00.123456789Z");

Instant expectedStored =
    expected.truncatedTo(ChronoUnit.MILLIS);
~~~

After a standard BSON round-trip, compare against **`expectedStored`** instead of expecting MongoDB to preserve 456789 nanoseconds absent from BSON Date.

### 26.4. Changing System Timezone in Parallel Tests

~~~java
// Causes JVM-wide interference:
java.util.TimeZone.setDefault(
    java.util.TimeZone.getTimeZone("UTC"));
~~~

This mutates **global JVM state** and can affect other tests running in parallel. Instead of changing the global timezone just to test auditing, use **`Clock.fixed(instant, ZoneOffset.UTC)`** and explicit `ZoneId` in conversions.

If you must test legacy code tied to `systemDefault`, run it in a separate environment/process or under strict isolation.

### 26.5. Sharing a Mutable Clock Singleton Across Test Classes

If the entire suite injects one `AdjustableClock` and tests set it concurrently, they will race. Use context isolation, per-test resource scoping, or a dedicated `Clock` per test so test A's time never affects test B.

### 26.6. Mocking DateTimeProvider Without Registering It in Auditing Context

~~~java
DateTimeProvider provider = () ->
    Optional.of(fixedInstant);
~~~

This only creates a Java object. If `@EnableMongoAuditing` points to another bean, auditing will not use this provider. Integration tests must verify the actual **bean name and wiring**.

### 26.7. Missing Creation Date with Pre-Assigned IDs

When using `new ObjectId()` before insert, `isNew` detection may see the ID is already set. If a test checks `@CreatedDate`, make the ID strategy explicit:

- ID is null and generated on the insert path.
- Entity implements `Persistable` with managed `isNew`.
- `@Version` is used to support newness semantics.

Do not hide this distinction behind another annotation without testing.

## 27. Layered Testing Strategy

| Test Layer | What It Verifies | Needs MongoDB? |
| --- | --- | --- |
| Unit: `Clock.fixed` | `Clock` returns exact `Instant` | No |
| Unit: `DateTimeProvider` | Provider calls `Clock` and returns `TemporalAccessor` | No |
| Unit: time policy | Expiry/deadlines computed accurately per `Clock` | No |
| Integration: `@DataMongoTest` | Provider is used by auditing infrastructure | Yes |
| Integration: raw BSON Date | Date mapping and millisecond precision | Yes |
| Integration: create vs. update | `createdAt` preserved, `updatedAt` updated | Yes |
| Integration: `updateFirst` | Does not assume callback ran | Yes |
| Integration: reactive | Publisher audits properly when subscribed | Yes |
| Integration: multiple instances | Clock drift / consistency policy | Needs infrastructure tests or fault injection |

### 27.1. Minimal Test Matrix

~~~text
Case A — create, Clock=2025-06-01T08:30Z, modifyOnCreate=true
  expect createdAt=08:30Z, updatedAt=08:30Z

Case B — save existing, Clock=2025-06-01T08:35Z
  expect createdAt=08:30Z, updatedAt=08:35Z

Case C — create, modifyOnCreate=false
  expect createdAt=08:30Z, updatedAt not auto-assigned

Case D — updateFirst(status only)
  expect updatedAt not auto-updated by AuditingEntityCallback

Case E — updateFirst(status + updatedAt)
  expect updatedAt written per chosen policy

Case F — BSON Date
  expect Instant after round-trip accurate to milliseconds

Case G — entity with preassigned ID
  expect behavior matching actual isNew policy, no guessing

Case H — display timezone
  expect same Instant when formatting UTC to Asia/Ho_Chi_Minh
~~~

### 27.2. Do Not Confuse Deterministic with "Mock Everything"

The goal is **controlling the time source**, not mocking `MongoTemplate`, Spring converters, and all auditing callbacks in integration tests. A proper integration test still runs against real MongoDB to verify mapping, while `Clock` is the swappable dependency.

### 27.3. Regression Checks on Spring Data Upgrades

When upgrading Spring Boot/Spring Data MongoDB versions, verify:

- Auditing annotation attributes and provider bean names.
- New/existing entity detection rules.
- Default date mapping types.
- Lifecycle callbacks triggered per write path.
- Callback ordering if custom `BeforeConvertCallback` beans exist.
- Reactive auditing and API imports.

Run the full integration test matrix rather than relying solely on clean compilation.

## 28. Hands-On Exercises

### Exercise 1: Choosing the Data Type

Requirement: store the exact timestamp when a document was created, independent of the viewer's timezone. Choose **Instant** or **LocalDateTime**?

**Answer:** **Instant** represents an absolute point in time. `LocalDateTime` requires an additional offset/zone to become an instant and causes ambiguity across hosts.

### Exercise 2: Declaring Annotations

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
~~~

**Question:** Which configuration must be enabled?

**Answer:** `@EnableMongoAuditing` in the imperative stack or `@EnableReactiveMongoAuditing` in the reactive stack, with `dateTimeProviderRef` if using a custom provider.

### Exercise 3: DateTimeProvider

Write a provider reading from an injected `Clock`:

~~~java
@Bean("mongoAuditDateTimeProvider")
DateTimeProvider provider(Clock clock) {
    return () -> Optional.of(Instant.now(clock));
}
~~~

**Answer:** Compute the time **inside** the `getNow` lambda, not once when creating the bean.

### Exercise 4: UTC

Instant is **2025-06-01T08:30:00Z**. In Asia/Ho_Chi_Minh (UTC+7), what time does it display?

**Answer:** **2025-06-01 15:30:00** on the same day. It is still the exact same instant.

### Exercise 5: Startup Clock Bug

~~~java
Instant startup = Instant.now(clock);
return () -> Optional.of(startup);
~~~

What is the bug?

**Answer:** Every audit gets the startup timestamp. Call `Instant.now(clock)` inside the lambda.

### Exercise 6: Fixed Test

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2025-06-01T08:30:00Z"),
    ZoneOffset.UTC);
~~~

What does calling `Instant.now(fixed)` 100 times return?

**Answer:** The exact same Instant **2025-06-01T08:30:00Z**, regardless of real wall-clock time.

### Exercise 7: Advancing Modification Date

You need to test `createdAt=08:30` and `updatedAt=08:35` in the same test without sleeping. Solution?

**Answer:** Inject `AdjustableClock` into `DateTimeProvider`, set `08:30` on insert, and `08:35` before saving the existing entity.

### Exercise 8: modifyOnCreate

Is `@LastModifiedDate` populated immediately when a new entity is created?

**Answer:** Under the common default `modifyOnCreate=true`, **yes**. To leave it unset on creation, configure `modifyOnCreate=false` and test it.

### Exercise 9: setDates=false

You enable `@EnableMongoAuditing(setDates=false)` and expect `createdAt` to still be set by `DateTimeProvider`. Is that assumption right?

**Answer:** No. `setDates=false` disables auditing's automatic assignment of date fields under that configuration.

### Exercise 10: Preassigned ID

An entity has a pre-assigned `@Id ObjectId` and no `@Version`. Is `@CreatedDate` guaranteed to be populated on `insert`?

**Answer:** Not guaranteed. Auditing newness detection may treat the entity as existing because the ID is non-null. Test and choose a strategy such as null ID on create, `@Version`, or `Persistable.isNew`.

### Exercise 11: BSON Precision

You persist `Instant` **2025-06-01T08:30:00.123456789Z** into BSON Date. Are the nanoseconds preserved?

**Answer:** No. BSON Date has millisecond precision, so typically only **`.123Z`** remains.

### Exercise 12: updateFirst

A service calls:

~~~java
mongoTemplate.updateFirst(
    query,
    new Update().set("status", "PAID"),
    AuditedOrder.class
);
~~~

Can you expect `@LastModifiedDate` to update automatically?

**Answer:** No. Query updates do not run the `BeforeConvert` entity-save auditing path. Update the timestamp explicitly via the app `Clock` or server `$currentDate`.

### Exercise 13: $currentDate

What is the difference between:

~~~java
new Update().set("updatedAt", Instant.now(clock));
~~~

and:

~~~java
new Update().currentDate("updatedAt");
~~~

?

**Answer:** The first takes application time from `Clock`; the second lets MongoDB Server assign its current date. The two sources can diverge.

### Exercise 14: Auditing and Transactions

A transaction writes an `Order`, then an Outbox insert fails and causes a rollback. `createdAt` was already generated by the provider in the JVM. Does MongoDB store the `Order`?

**Answer:** The `Order` will not commit if the transaction aborts properly. Computing a timestamp in memory does not mean the record persisted.

### Exercise 15: createdAt Is Not Commit Time

A transaction starts at 08:30:00, the callback sets `createdAt=08:30:01`, and commit finishes at 08:30:03. What is `createdAt`?

**Answer:** According to the callback/provider when resolving the value, **08:30:01**, not 08:30:03.

### Exercise 16: Two Nodes Both Using UTC

Node A is 400ms fast and Node B is 300ms slow. Does `Clock.systemUTC` fix that skew?

**Answer:** No. UTC is a zone convention, not clock synchronization; use NTP/monitoring.

### Exercise 17: Snapshot Is Not a Version

Two updates share the same `updatedAt` millisecond. Can `updatedAt` guarantee a unique order for every update?

**Answer:** No. Use `@Version`, expected state, or sequence numbers/idempotency keys when handling concurrency.

### Exercise 18: Store Business Day in Vietnam

When does June 1, 2025 in `Asia/Ho_Chi_Minh` start in UTC?

**Answer:** **2025-05-31T17:00:00Z**. Compute `startOfDay` in the store's `ZoneId`, not UTC midnight.

### Exercise 19: Reactive Auditing

An application uses `ReactiveMongoRepository` but only enables `@EnableMongoAuditing`. Is reactive auditing guaranteed to be active?

**Answer:** No. Use `@EnableReactiveMongoAuditing` appropriately and test the real Reactor Publisher.

### Exercise 20: Unit and Integration

A `DateTimeProvider` unit test returns the right `Instant`. Is that enough to prove `createdAt` is saved as a BSON Date?

**Answer:** Not yet. Write a `@DataMongoTest`/integration test calling insert/save and inspecting raw BSON Date.

### Exercise 21: TimeZone.setDefault

A test alters the JVM's global `TimeZone` to UTC hoping for determinism. What is the risk?

**Answer:** Affects other tests and legacy code in the same JVM; in parallel tests it causes races. Inject `Clock` and apply `ZoneId` only at display time.

### Exercise 22: Documents from External Systems

A raw MongoDB driver job writes `createdAt` as a `String` and omits `updatedAt`. Does Spring's `DateTimeProvider` automatically fix that document?

**Answer:** No. Raw writers bypass auditing infrastructure; you need dedicated schema policies and migrations.

## 29. Implementation Checklist

- **Time source:** Does `DateTimeProvider` obtain `Instant` from an injected `Clock`?
- **UTC:** Is `Clock.systemUTC` used consistently per policy?
- **Data type:** Do persisted audit timestamps use `Instant`/BSON Date?
- **Bean name:** Does `dateTimeProviderRef` point to the exact bean?
- **Lifecycle:** Are `@EnableMongoAuditing` or `@EnableReactiveMongoAuditing` matched to the stack?
- **New state:** Do entity ID/`@Version`/`Persistable` yield the right `isNew` state?
- **Create:** Is `createdAt` populated on insert; does `modifyOnCreate` match requirements?
- **Update:** Does `updatedAt` change on save; do query updates have an explicit policy?
- **setDates:** Has auditing date population been kept enabled (not accidentally turned off)?
- **Multi-writer:** Do external apps/raw driver follow the same schema/time policy?
- **Precision:** Do tests and APIs account for BSON Date millisecond precision?
- **Timezones:** Is `LocalDateTime` avoided as a global instant?
- **Business dates:** Are calendar dates calculated using the business `ZoneId`?
- **Clock drift:** Is infrastructure clock synchronization and skew monitoring in place?
- **Concurrency:** Is `updatedAt` avoided as a unique version/sequence?
- **Transactions:** Is callback time distinguished from commit time?
- **Retries:** Do business `requestedAt` and document `createdAt` have distinct semantics?
- **Reactive:** Are services free of blocking or double-subscribing?
- **Fixed test:** Are there tests using `Clock.fixed` + `DateTimeProvider` at exact instants?
- **Advancing test:** Are there tests verifying `createdAt` stays constant while `updatedAt` advances without `sleep`?
- **BSON test:** Does the test read raw `getDate`/`toInstant` after insert/save?
- **Test isolation:** Is a mutable `Clock` prevented from being shared across parallel tests?
- **Operations:** Are tenant/date indexes, monitoring, and cleanup policies properly set up?

## 30. Summary

1. **`DateTimeProvider`** is Spring Data auditing's mechanism for obtaining timestamps, configured via **`dateTimeProviderRef`**.
2. **`Clock.systemUTC()`** establishes a clear time-source convention; **`Clock.fixed`** enables deterministic tests.
3. **`Instant`** represents an absolute point in time; **`LocalDateTime`** lacks zone/offset and causes ambiguity.
4. **BSON Date** stores milliseconds since epoch without preserving the original `ZoneId`.
5. **`@CreatedDate`** and **`@LastModifiedDate`** are updated through the auditing lifecycle when entities follow supported insert/save paths and proper new-state detection.
6. **`modifyOnCreate`** controls whether `LastModifiedDate` is set on creation; **`setDates=false`** disables automatic date metadata assignment.
7. **`AuditingEntityCallback` runs before conversion**, unlike `BeforeSaveCallback` which runs after the `Document` is constructed.
8. **`Clock.fixed`/`AdjustableClock`** allow testing create/update without depending on real time or `Thread.sleep`.
9. **Integration tests** must verify provider wiring, entity timestamps, and real BSON Date values.
10. **`MongoTemplate.updateFirst`/findAndModify/bulk/raw driver** are not automatically equivalent to `save(entity)` auditing; update timestamps explicitly on those write paths.
11. **`$currentDate`** uses server time; **`Instant.now(clock)`** uses app time. Choose a time-source policy deliberately.
12. **`ReactiveMongoRepository`** requires reactive auditing configuration and a properly subscribed Publisher chain.
13. **UTC does not replace NTP**; timestamps do not replace optimistic locking or operation IDs.
14. **`createdAt` is not synonymous with transaction commit time**; a rolled-back transaction may have computed timestamps in memory without committing the document.
15. **User timezones and business dates** should be handled at display/calculation boundaries with an explicit `ZoneId`.

Mastering **DateTimeProvider, UTC, and deterministic test time** helps **SPRING_DATA_MONGODB** services produce timestamps with clear provenance, test them accurately, and maintain a unified convention across entity mapping, repositories, `MongoTemplate`, reactive access, and multi-instance deployments.

### References

- [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html) — enabling auditing, `@CreatedDate`, `@LastModifiedDate`, and configuration.
- [Spring Data MongoDB — EnableMongoAuditing API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableMongoAuditing.html) — `dateTimeProviderRef`, `modifyOnCreate`, `setDates`.
- [Spring Data MongoDB — EnableReactiveMongoAuditing API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableReactiveMongoAuditing.html) — auditing in the reactive stack.
- [Spring Data Commons — DateTimeProvider API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html) — `Optional<TemporalAccessor>` and `getNow()`.
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html) — `AuditingEntityCallback` and `BeforeConvert` lifecycle.
- [Spring Data MongoDB — MongoTemplate CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — insert/save/query-based update operators.
- [Java SE — Clock API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) — `systemUTC`, `fixed`, `offset`, and test time.
- [MongoDB Manual — BSON Date](https://www.mongodb.com/docs/manual/reference/bson-types/#date) — BSON Date representing milliseconds since Unix epoch.
