# Mapping _class, Inheritance, and @TypeAlias

> **Chapter:** Basic Mapping  
> **Module:** `SPRING_DATA_MONGODB`

Spring Data MongoDB converts Java objects into BSON documents and back through `MappingMongoConverter`. For regular Java classes, the target type can be inferred from the property declaration or query parameter. However, when a property has an **interface** or **abstract class** type, or when a single collection holds multiple subclasses, the converter needs to know the **actual concrete type** that was stored in order to instantiate the right object. Under default settings, Spring Data MongoDB uses the **`_class`** metadata field to carry that type information.

The `@TypeAlias` annotation replaces long Java class names in `_class` with a shorter, more stable identifier. Combining this mechanism with inheritance allows an application to model domain variants, such as multiple event types in the same collection, while still reading back the right Java subclasses. However, how metadata is stored affects data compatibility, package refactoring, migrations, and correctness when type hints are absent.

This lesson sits within the `SPRING_DATA_MONGODB` module: using Spring Data MongoDB to connect, map documents, and access data via `MongoTemplate` or repositories; it is also a foundation for building queries, aggregations, indexes, transactions, reactive access, tests, and data performance diagnostics in later lessons.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the `_class` field in BSON, when type hints are written, and how Spring Data uses them on read.
2. Map parent–child class hierarchies into the same collection or inside nested documents.
3. Use `@TypeAlias` on concrete classes and explain its impact on existing data.
4. Distinguish `@TypeAlias` from `@Document`, `@Field`, `@Id`, business discriminators, and JSON polymorphism.
5. Recognize risks when disabling/changing type mapping and design tests for polymorphic data.

## 2. What Is _class?

Consider an entity:

```java
package com.example.demo.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class Product {
    @Id
    private String id;
    private String name;

    protected Product() {}

    public Product(String name) {
        this.name = name;
    }
}
```

With the default `MappingMongoConverter`, a document might be written as follows (shown in `mongosh` syntax):

```javascript
{
  _id: ObjectId("66a000000000000000000010"),
  name: "Mechanical keyboard",
  _class: "com.example.demo.model.Product"
}
```

Here:

- `_id` is the document identifier key in the collection; it **does not** identify the Java type.
- `name` is the product's business data.
- `_class` is **Spring Data mapping** metadata helping the converter identify the corresponding class. The MongoDB server does not understand `"com.example.demo.model.Product"` as a Java type or an inheritance relationship.

Under default configuration, Spring Data MongoDB may store the fully qualified Java class name (FQCN) on root documents and at nested positions needing concrete type information. On read, `MappingMongoConverter` combines `_class` metadata with the requested Java type to decide how to instantiate the object.

> **Distinction:** `_class` is not a required MongoDB field. A document created directly via `mongosh` may have no `_class` at all; MongoDB can still store and query it, though mapping it to an abstract Java type may fail without alternative type information.

### 2.1. Default Conversion Flow

```text
               Java -> BSON

new OrderCreatedEvent(...)
          |
          v
   MappingMongoConverter
   - checks @Document, @Id, field mapping
   - resolves actual Java type
   - writes type hint via MongoTypeMapper
          |
          v
{ "_id": ..., "_class": "order_created", ... }


               BSON -> Java

{ "_class": "order_created", ... }
          |
          v
   MongoTypeMapper + MappingContext
   - resolves registered alias/type
          |
          v
   MappingMongoConverter
   - instantiates exact concrete class
   - populates fields
          |
          v
   OrderCreatedEvent(...)
```

If a document only has simple fields and the read target is already a concrete class, it can be read successfully without `_class`. The critical issue arises when Java only knows a **supertype**, while actual stored records correspond to multiple subtypes.

### 2.2. Why _class Is Not a Business Schema

Do not use the FQCN as a public business type code, because package refactors or language changes can alter that value. If an API or report needs an "order type" or "event type", consider an explicit domain field like `eventType` with stable meaning independent of mapping details.

`@TypeAlias` keeps technical metadata concise and less tied to packages, yet the alias itself remains a **contract between stored data and the converter**; changing aliases carelessly can make old data unreadable.

## 3. Inheritance: One Collection Holding Multiple Event Types

Suppose a sales system stores events emitted from orders:

- `OrderCreatedEvent`: order was created, containing `orderId` and `amountMinor`.
- `OrderCancelledEvent`: order was cancelled, containing `orderId` and `reason`.

Both are `AuditEvent` instances sharing base fields like occurrence timestamp. We want to store them in the **same `audit_events` collection**, then read a unified list while still getting back the right concrete subclasses.

### 3.1. Parent Class

File `AuditEvent.java`:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_events")
public abstract class AuditEvent {
    @Id
    private String id;
    private Instant occurredAt;

    protected AuditEvent() {}

    protected AuditEvent(Instant occurredAt) {
        this.occurredAt = occurredAt;
    }

    public String getId() {
        return id;
    }

    public Instant getOccurredAt() {
        return occurredAt;
    }
}
```

The parent class is abstract because the domain never creates an untyped "generic event". Inherited properties such as `id` and `occurredAt` are mapped by Spring Data MongoDB alongside subclass-specific properties.

### 3.2. Subclass: Order Created

File `OrderCreatedEvent.java`:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_events")
@TypeAlias("order_created_v1")
public class OrderCreatedEvent extends AuditEvent {
    private String orderId;
    private long amountMinor;

    protected OrderCreatedEvent() {}

    public OrderCreatedEvent(
            Instant occurredAt, String orderId, long amountMinor) {
        super(occurredAt);
        this.orderId = orderId;
        this.amountMinor = amountMinor;
    }

    public String getOrderId() {
        return orderId;
    }

    public long getAmountMinor() {
        return amountMinor;
    }
}
```

### 3.3. Subclass: Order Cancelled

File `OrderCancelledEvent.java`:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_events")
@TypeAlias("order_cancelled_v1")
public class OrderCancelledEvent extends AuditEvent {
    private String orderId;
    private String reason;

    protected OrderCancelledEvent() {}

    public OrderCancelledEvent(
            Instant occurredAt, String orderId, String reason) {
        super(occurredAt);
        this.orderId = orderId;
        this.reason = reason;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getReason() {
        return reason;
    }
}
```

**Point to remember:** both subclasses declare the same `@Document(collection = "audit_events")` to make the target collection explicit when operating on a concrete type. The `@TypeAlias` annotation only controls the type name stored in metadata; it does not set the collection on its own.

### 3.4. Writing and Reading with MongoTemplate

Illustrative service file:

```java
package com.example.shop.audit;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class AuditEventService {
    private final MongoTemplate mongoTemplate;

    public AuditEventService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void appendDemoEvents() {
        mongoTemplate.insert(
            new OrderCreatedEvent(
                Instant.parse("2026-11-20T01:00:00Z"),
                "ORD-100", 350000L),
            "audit_events"
        );
        mongoTemplate.insert(
            new OrderCancelledEvent(
                Instant.parse("2026-11-20T02:00:00Z"),
                "ORD-101", "Customer changed mind"),
            "audit_events"
        );
    }

    public List<AuditEvent> loadAll() {
        return mongoTemplate.findAll(
            AuditEvent.class, "audit_events");
    }
}
```

In the database, the two documents may look like this:

```javascript
// Document 1
{
  _id: ObjectId("66a000000000000000000011"),
  occurredAt: ISODate("2026-11-20T01:00:00Z"),
  orderId: "ORD-100",
  amountMinor: NumberLong(350000),
  _class: "order_created_v1"
}

// Document 2
{
  _id: ObjectId("66a000000000000000000012"),
  occurredAt: ISODate("2026-11-20T02:00:00Z"),
  orderId: "ORD-101",
  reason: "Customer changed mind",
  _class: "order_cancelled_v1"
}
```

The `_class` values are the aliases provided by `@TypeAlias` instead of the FQCNs of the two subclasses. When the mapping context knows both aliases, calling `findAll(AuditEvent.class, "audit_events")` restores the exact `OrderCreatedEvent` and `OrderCancelledEvent` instances.

Example handling the results:

```java
for (AuditEvent event : service.loadAll()) {
    if (event instanceof OrderCreatedEvent created) {
        System.out.println(
            "Created " + created.getOrderId()
            + ": " + created.getAmountMinor());
    } else if (event instanceof OrderCancelledEvent cancelled) {
        System.out.println(
            "Cancelled " + cancelled.getOrderId()
            + ": " + cancelled.getReason());
    }
}
```

The snippet above assumes `service` is an instance of `AuditEventService` and Java supports pattern matching for `instanceof`. In real business logic, handling can be dispatched per event type rather than concentrated in a single loop.

### 3.5. Repository for the Parent Class

A shared repository can be declared:

```java
package com.example.shop.audit;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditEventRepository
        extends MongoRepository<AuditEvent, String> {
}
```

This repository has `AuditEvent` as its domain type, while the collection stores multiple subtypes. On read, instantiating the right subtype still depends on type hints and the mapping context. The repository does not infer variants from `reason` or `amountMinor` if suitable metadata is missing.

If event types have very different lifecycles, indexes, or access permissions, using **separate collections per type** may be a better fit. Placing multiple classes in one collection is a data-modeling decision, not a mandatory consequence of Java inheritance.

## 4. How Does @TypeAlias Work?

The annotation lives in `org.springframework.data.annotation.TypeAlias` and is applied to a **mapped class**, for example:

```java
@TypeAlias("order_created_v1")
public class OrderCreatedEvent extends AuditEvent {
    // ...
}
```

Comparing documents with and without aliases:

| Configuration | Illustrative `_class` Value | Characteristics |
| --- | --- | --- |
| Default, without `@TypeAlias` | `com.example.shop.audit.OrderCreatedEvent` | Tightly coupled to Java package/class name |
| With `@TypeAlias("order_created_v1")` | `order_created_v1` | Shorter, can remain stable across Java refactors |
| Type hints disabled via `DefaultMongoTypeMapper(null)` | No `_class` written by mapper | Must solve subtype reading via another mechanism |

### 4.1. Choosing Stable, Unique Aliases

An alias should:

- Have clear meaning within the application scope, such as `order_created_v1` or `payment_card_v1`.
- Be **unique** among all classes known to the mapping context, avoiding two Java types sharing one alias.
- Be treated as part of the stored data format; keep it unchanged across package refactors if data behavior has not changed.
- Be changed in a controlled way when introducing a new storage format version.

There is no need to bump a version on every method rename or Java file move. The `_v1` suffix in the examples only reflects application versioning intent, not a framework requirement.

### 4.2. @TypeAlias Is Not @Field or @Document

```java
@Document(collection = "audit_events") // target collection
@TypeAlias("order_created_v1")         // type metadata value
public class OrderCreatedEvent extends AuditEvent {

    @Field("order_ref")               // BSON field name
    private String orderId;
}
```

This standalone snippet illustrates how the annotations differ; if applying `@Field("order_ref")` to the code in section 3, new BSON documents will use `order_ref` instead of `orderId`. Do not rename fields on a live model without assessing existing data.

| Annotation | Effect |
| --- | --- |
| `@Document(collection = "...")` | Determines the collection used when saving/reading the entity by Java type |
| `@Id` | Maps the Java identifier property to `_id` |
| `@Field("...")` | Renames or tunes BSON field metadata |
| `@TypeAlias("...")` | Sets the type key Spring Data writes/reads instead of the fully qualified class name |

None of the annotations above create foreign keys or server-side inheritance structures in MongoDB.

## 5. _class Metadata on Nested Objects

Root documents are not the only places needing type hints. Consider a delivery job whose `destination` field is declared as an interface. When saved, the actual value might be an email or a webhook.

File `Destination.java`:

```java
package com.example.shop.delivery;

public interface Destination {
}
```

File `EmailDestination.java`:

```java
package com.example.shop.delivery;

import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document
@TypeAlias("destination_email_v1")
public record EmailDestination(String address)
        implements Destination {
}
```

File `WebhookDestination.java`:

```java
package com.example.shop.delivery;

import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document
@TypeAlias("destination_webhook_v1")
public record WebhookDestination(String endpoint)
        implements Destination {
}
```

File `DeliveryJob.java`:

```java
package com.example.shop.delivery;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "delivery_jobs")
public record DeliveryJob(
    @Id String id,
    String message,
    Destination destination
) {
}
```

Example writing via repository/`MongoTemplate`:

```java
var job = new DeliveryJob(
    null,
    "Order has been delivered",
    new EmailDestination("contact@example.com")
);

mongoTemplate.insert(job);
```

This snippet assumes an injected `MongoTemplate mongoTemplate` in a service. Illustrative document:

```javascript
{
  _id: ObjectId("66a000000000000000000013"),
  message: "Order has been delivered",
  destination: {
    address: "contact@example.com",
    _class: "destination_email_v1"
  },
  _class: "com.example.shop.delivery.DeliveryJob"
}
```

Here **`destination._class` identifies the implementation class** of `Destination`. When writing:

```java
DeliveryJob restored =
    mongoTemplate.findById(id, DeliveryJob.class);

if (restored != null
        && restored.destination() instanceof EmailDestination email) {
    System.out.println(email.address());
}
```

`id` is the existing identifier value of the document. The converter uses the metadata at the nested location to instantiate `EmailDestination` instead of trying to instantiate the `Destination` interface.

**Why did the example place `@Document` on the two nested classes?** In an application configured with Spring Data entity scanning, this annotation helps subtypes be discovered and have their metadata registered at startup. It **does not** cause MongoDB to split `destination` into a separate collection: the field remains embedded inside `delivery_jobs`. If a project uses custom mapping context setup, ensure subtypes are included in the initial entity set or registered appropriately.

### 5.1. When Does Nested _class Not Appear?

Spring Data does not force writing `_class` on every sub-object. When the declared type is already concrete and the mapper does not need to preserve a runtime type different from the declared type, no type hint may appear at that position. Hence, do not build business logic assuming "every nested object always has `_class`".

Conversely, when a field is declared as `Destination` yet stores `EmailDestination`, type metadata is generally needed to restore the subtype under default mapping. Decisions to disable metadata must consider nested fields too, not just root documents.

## 6. Requirements for Resolving Aliases After Restart

`@TypeAlias` **does not** create a global alias table on the MongoDB server. Mapping alias strings back to Java classes happens inside the application's `MongoMappingContext` and type mapper.

An easily overlooked pitfall:

1. Application A writes `_class: "destination_email_v1"`.
2. Application A stops and restarts.
3. The new instance reads `delivery_jobs` before ever writing an `EmailDestination`.
4. If the mapping context **does not yet know** the class carrying `@TypeAlias("destination_email_v1")`, alias resolution may fail.

To avoid depending on "write before read", ensure the Spring Data mapping context recognizes concrete subclasses right at startup. This can be done through entity scanning matching your Spring Boot/Spring Data setup, or by setting the **initial entity set** containing the subtypes. When putting `@Document` on subtypes as shown above, verify their packages are actually covered by entity scanning.

**Note:** `@EnableMongoRepositories` scans repository interfaces; it does not automatically register every subtype for `@TypeAlias` resolution. Repository scanning, component scanning, and entity/mapping scanning are distinct mechanisms.

## 7. Parent Classes, Subclasses, and _class: Specific Read Scenarios

| Read Scenario | With Valid Type Hint | Without Type Hint |
| --- | --- | --- |
| Reading document directly as `OrderCreatedEvent.class` | Mapper can use metadata and map to subclass | Usually still instantiates concrete class if fields match |
| Reading document as `AuditEvent.class` (abstract) | Can select the right registered subclass | May fail because it doesn't know which concrete class to instantiate |
| Field `Destination` declared as interface | Can choose `EmailDestination` or `WebhookDestination` | Cannot reliably infer subtype from interface alone |
| Document has `_class` alias, but alias is unregistered | Mapper cannot resolve desired subtype | Must declare/register type mapping or custom converter |
| Legacy document has renamed or deleted FQCN | Reading depends on ability to resolve old class | Needs compatibility strategy or migration |

Do not assume Spring Data decides subtypes by "seeing a `reason` field so it must be a cancellation event." To infer types that way, write a custom converter/logic and test missing fields, schema changes, and invalid values.

### 7.1. Reading the Same Collection as Different Types

Example:

```java
// Reading at parent level: suitable when handling multiple subtypes.
List<AuditEvent> all = mongoTemplate.findAll(
    AuditEvent.class, "audit_events");

// Reading one concrete class: requires understanding what document kinds exist in the collection.
List<OrderCreatedEvent> created = mongoTemplate.findAll(
    OrderCreatedEvent.class, "audit_events");
```

**Caution with the second call:** reading directly into `OrderCreatedEvent.class` is not automatically a safe business discriminator filter on a multi-type collection. Add an explicit filter condition or design a suitable repository/query; otherwise, documents of other subtypes may be mapped erroneously or raise errors depending on metadata and converter version.

When filters must survive refactoring or multi-language access, use a dedicated `eventType` field rather than tying business queries strictly to `_class`.

## 8. Should You Disable _class?

Sometimes an application wants BSON documents free of Java coupling or wants a leaner schema for polyglot services. Spring Data MongoDB supports customizing `MongoTypeMapper`; a commonly referenced way is:

```java
import org.springframework.data.mongodb.core.convert.DefaultMongoTypeMapper;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;

// Call when creating/configuring the converter before using it for reads/writes.
public static void disableTypeHints(MappingMongoConverter converter) {
    converter.setTypeMapper(new DefaultMongoTypeMapper(null));
}
```

This is an **illustrative method**, placed inside a Java configuration class and called when constructing/configuring the converter prior to use; it is not a complete Spring bean by itself. `DefaultMongoTypeMapper(null)` **disables writing the default type discriminator field**. Creating an actual `MappingMongoConverter` bean requires wiring `MongoDatabaseFactory`, `MongoMappingContext`, custom conversions, and application auto-configuration. Replacing the converter carelessly can disable or alter existing auto-configured settings.

### 8.1. What Changes When Removing _class?

Suppose we read abstract `AuditEvent` or interface `Destination`. Without a type hint, the default mapper lacks the information to pick a subclass. Several design alternatives exist:

- **Avoid polymorphism at storage level:** each collection stores one concrete class with strongly typed queries.
- **Use a stable business discriminator field:** store `eventType`/`destinationType` and implement matching read/write converters.
- **Read by known concrete type:** choose the concrete class from API context or query criteria rather than inferring from an interface.
- **Keep type hints where needed:** do not strip metadata just to save a few bytes if added complexity and misread risks outweigh the savings.

The size of a `_class` field is rarely the primary cause of slow queries. Performance depends on indexes, document sizes, projections, query patterns, and database round-trips. Measure before overhauling the entire mapping mechanism.

### 8.2. Renaming the Metadata Field, Not Just the Value

`MongoTypeMapper` can be configured with a different type hint key:

```java
// Placed in a configuration class, applied to the created converter:
public static void useCustomHintField(MappingMongoConverter converter) {
    converter.setTypeMapper(new DefaultMongoTypeMapper("javaType"));
}
```

Then the technical discriminator field becomes `javaType` instead of `_class`. This **changes the stored document format**; older documents using `_class` may not be handled equivalently without a compatibility or migration strategy. `@TypeAlias` only sets the **value**, while `DefaultMongoTypeMapper("javaType")` changes the **field name**.

## 9. Backward Compatibility and Migration When Changing Classes or Aliases

For data retained over years, Java changes can directly impact `_class`:

| Change | If Storing FQCN | If Using a Stable Alias |
| --- | --- | --- |
| Package rename | Old documents point to old class name | Alias can keep mapping to new class once registered |
| Class rename | Risk of failing to locate old type | Usually unaffected if alias and schema remain compatible |
| Deleting a subtype | Old documents may become unreadable | Still requires a replacement class/converter |
| Changing alias from `order_created_v1` to `order_created_v2` | N/A if aliases weren't used | Must support or migrate documents using old alias |
| Renaming fields / changing BSON types | Needs migration/converter | Alias **does not** automatically handle schema changes |

### 9.1. Inspecting Stored Types

In `mongosh`:

```javascript
db.audit_events.aggregate([
  { $group: { _id: "$_class", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
])
```

Output may reveal new aliases, legacy FQCNs, unusual values, and documents missing `_class`. Before migrating, locate every place containing metadata: root documents, nested objects, and arrays holding polymorphic elements.

### 9.2. Example Migrating Metadata from FQCN to Alias

Suppose some legacy documents stored:

```javascript
{ _class: "com.example.shop.audit.OrderCreatedEvent", orderId: "ORD-100" }
```

A migration command for **root** documents might be:

```javascript
db.audit_events.updateMany(
  { _class: "com.example.shop.audit.OrderCreatedEvent" },
  { $set: { _class: "order_created_v1" } }
)
```

This command only updates `_class` on matching root documents; it **does not** transform type hints inside nested objects or arrays. Nor does it prove the remaining documents match the new Java class fields.

A safe rollout process should include:

1. **Data audit first:** how many documents exist per `_class`, which aliases are present, and which nested paths exist.
2. **Define the target format:** new aliases, concrete Java types, field mappings, and compatibility version.
3. **Ensure a transition period:** if multiple application versions run concurrently, readers must handle both old and new formats; compatible classes/converters may be needed temporarily.
4. **Test migration on representative data:** verify both root and nested type hints, incomplete documents, and especially inherited data.
5. **Execute a controlled migration with error monitoring:** ensure backups/recovery exist and re-runs do not corrupt data.
6. **Verify post-change:** read documents via repository/template in the new application version; reconcile counts and returned types.

If you already moved packages so the old FQCN no longer exists, merely adding `@TypeAlias` to the new class **will not automatically** turn old FQCN strings into the new alias. You need a compatibility mechanism or an actual data migration.

## 10. Impact on Queries, Aggregations, and Indexes

`_class` is a BSON field visible and queryable in `mongosh`:

```javascript
db.audit_events.find(
  { _class: "order_created_v1" },
  { orderId: 1, amountMinor: 1, occurredAt: 1, _class: 1 }
)
```

If the business frequently filters by event type and timestamp, consider an appropriate index:

```javascript
db.audit_events.createIndex({
  _class: 1,
  occurredAt: -1
})
```

However:

- Indexing `_class` couples performance to the current metadata strategy; changing aliases or disabling metadata affects queries.
- For dashboards, audits, or APIs needing long-term classification, an explicit `eventType` field is usually easier to govern, migrate, and share across services.
- Indexes incur write and storage costs; create them only when real queries need them.
- Aggregations in MongoDB operate on BSON documents. A `$match` pipeline stage does not understand Java inheritance unless explicit conditions are placed in the pipeline.

Inspect execution plans:

```javascript
db.audit_events
  .find({ _class: "order_created_v1" })
  .sort({ occurredAt: -1 })
  .limit(20)
  .explain("executionStats")
```

Review metrics like `totalDocsExamined`, `totalKeysExamined`, and execution time on a representative dataset. A collection with only a few documents is not sufficient to assess index benefit.

## 11. Common Misconceptions

| Misconception | Reality | How to Handle |
| --- | --- | --- |
| "MongoDB needs `_class` to store documents" | `_class` is metadata created by Spring Data mapping | Do not treat it as a database-server requirement |
| "`@TypeAlias` changes the collection name" | Alias only changes the type hint value | Use `@Document(collection = "...")` to pick the collection |
| "An abstract superclass can read documents lacking `_class`" | Cannot know by default which subtype to instantiate | Keep type hints or use a custom converter/discriminator |
| "Every nested object has `_class`" | Hints may appear only when needed to represent concrete runtime types | Inspect actual BSON and mapping rules |
| "Package renames are always safe once aliases are set" | Aliases stabilize metadata, but fields and readers still must stay compatible | Re-test existing data and subtype registration |
| "`@TypeAlias` automatically migrates old `_class` values" | The annotation does not modify already-written BSON documents | Plan a migration or support reading both legacy and new formats |
| "Disabling `_class` always yields major speedups" | Performance also depends on schemas, indexes, queries, and read/write counts | Benchmark and weigh the cost of losing polymorphism |
| "`@EnableMongoRepositories` registers all aliases" | Repository scanning and entity/mapping discovery are separate | Ensure subtypes are known to the mapping context before reads |
| "Using `findAll(Subclass.class)` replaces a business filter" | Specifying a target Java type is not always a discriminator query | Add explicit filters and consider a stable business type field |

## 12. Testing Polymorphic Mapping

A unit test that merely calls `new OrderCreatedEvent(...)` does not prove BSON reads back as the right subtype. A **round-trip test** against a real MongoDB or appropriate test MongoDB environment is needed.

Example using Spring Boot Test, JUnit 5, and AssertJ:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AuditEventMappingTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void readsStoredAliasBackAsConcreteSubtype() {
        String orderId = "TEST-ORDER-909";

        OrderCreatedEvent saved = mongoTemplate.insert(
            new OrderCreatedEvent(
                Instant.parse("2026-11-20T00:00:00Z"),
                orderId, 100000L),
            "audit_events"
        );

        Document stored = mongoTemplate
            .getCollection("audit_events")
            .find(new Document("orderId", orderId))
            .first();

        assertThat(stored).isNotNull();
        assertThat(stored.getString("_class"))
            .isEqualTo("order_created_v1");

        AuditEvent restored = mongoTemplate.findById(
            saved.getId(), AuditEvent.class, "audit_events");

        assertThat(restored).isInstanceOf(OrderCreatedEvent.class);
        assertThat(((OrderCreatedEvent) restored).getOrderId())
            .isEqualTo(orderId);
    }
}
```

**Note on `_id` when checking directly via the driver:** in the Java example, `@Id String id` may be converted by Spring Data to BSON `ObjectId` when the value fits. `MongoTemplate.findById` handles conversion per mapping, whereas the driver's `getCollection(...)` API works directly with BSON types. Thus the BSON check above queries by `orderId` rather than passing a Java string to an `_id` filter. Isolate test data so `orderId` does not collide with other documents.

### 12.1. Recommended Test Matrix

| Case | Expectation |
| --- | --- |
| Write/readback `OrderCreatedEvent` | BSON has expected alias; Java returns right subtype and inherited fields |
| Write/readback `OrderCancelledEvent` | Other alias resolves accurately without mixing fields |
| Write/readback `DeliveryJob` with `EmailDestination` | `destination._class` restores the right implementation |
| Write/readback `DeliveryJob` with `WebhookDestination` | Other implementation branch is handled properly |
| Start fresh context and read existing data | Aliases are already registered in mapping context without "write-before-read" dependency |
| Read document missing `_class` into abstract class/interface | Application responds predictably rather than silently constructing a wrong object |
| Read document with unknown alias or legacy FQCN | Defined error/compatibility handling is in place |
| Rename Java package while keeping alias | Legacy data still reads properly if schema and metadata match |

For Spring Data MongoDB projects, use an isolated test MongoDB instance such as Testcontainers when infrastructure allows. Reactive access uses `ReactiveMongoTemplate` or reactive repositories, yet still needs verification of the same BSON contract and subtype resolution; reactive APIs do not remove mapping metadata requirements.

## 13. Applied Exercise

A notification system has three delivery channels: email, SMS, and webhook. Every notification shares `createdAt`, `userId`, and `status`, while each channel has specific fields (email address, phone number, webhook URL).

Try designing:

1. A parent `Notification` class (or appropriate interface) and three implementations with distinct `@TypeAlias` values.
2. Decide whether to store all subtypes in a `notifications` collection or split collections per channel; justify using common read and update patterns.
3. Write `MongoTemplate` calls to save two subtypes and read them back as the parent type.
4. Inspect BSON for accurate `_class` values and analyze the case where historical data lacks that field.
5. Describe a strategy for renaming Java packages without breaking old documents.

**Reference solution outline:** if the application needs a unified notification queue, keeping one collection with aliases such as `notification_email_v1`, `notification_sms_v1`, and `notification_webhook_v1` can work well. Each subclass is explicitly mapped and registered with the mapping context. If channels have vastly different retention periods, indexes, and write loads, separate collections may be a better choice. Either way, verify the BSON → Java round trip and plan historical data compatibility.

## Takeaways

The **`_class`** field stores type information that Spring Data MongoDB can use when mapping BSON documents back to Java objects, which is especially important for **inheritance and polymorphism**. **`@TypeAlias`** sets a shorter and more stable type name than an FQCN, though it does not change the collection, business fields, or already-written data. When storing multiple subtypes in the same collection or in nested objects, ensure the mapping context recognizes the aliases, protect backward compatibility for old data, and only alter the type hint mechanism with an explicit migration strategy.
