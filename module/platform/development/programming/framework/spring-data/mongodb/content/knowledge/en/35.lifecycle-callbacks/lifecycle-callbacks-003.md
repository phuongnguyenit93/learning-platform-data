# BeforeSaveCallback with the Converted Entity and Document

## 1. Scenario: Enriching Data Right Before Writing to MongoDB

A catalog management service stores products in MongoDB using Spring Data MongoDB. The Java entity has a **displayName** field, while the collection needs a normalized BSON field **search_display** to support search queries. The service also wants to attach **write_schema** to the document to identify the data format being written.

The requirement sounds simple: "When saving a product, automatically add these two fields before MongoDB receives the data." However, picking the wrong callback can cause Java's in-memory state to differ from the document actually stored.

In Spring Data MongoDB, **BeforeSaveCallback** is a very specific extension point:

- Receives the **Java entity** that has already gone through conversion.
- Receives the **`org.bson.Document`** being prepared for writing.
- Receives the **collection name**.
- Can mutate **`Document`** to change the BSON written to the server.
- Returns the entity, yet modifying persistent fields on the entity at this point **is not re-applied to the already-converted Document**.

Therefore:

**Want to modify persistent entity properties before conversion → BeforeConvertCallback.**

**Want to modify the BSON document after conversion but before writing → BeforeSaveCallback.**

This is the core principle of the lesson **BeforeSaveCallback with the Converted Entity and Document**, in the **Lifecycle and Callbacks** chapter of the **SPRING_DATA_MONGODB** module. The module covers MongoDB connections, document mapping, repositories, MongoTemplate, queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics.

### 1.1. After This Lesson, You Will Be Able To

1. Pinpoint the exact position of BeforeSaveCallback in the write pipeline.
2. Write callbacks with the signature **onBeforeSave(T entity, Document document, String collection)**.
3. Distinguish Java field names from mapped BSON field names such as **@Field("tenant_id")**.
4. Perform enrichment, masking, or document structure adjustments at the right stage.
5. Avoid the bug where "the entity was modified yet MongoDB data stayed unchanged."
6. Understand interactions with **BeforeConvertCallback, BeforeSaveEvent, AfterSaveCallback, and auditing**.
7. Know which operations invoke callbacks and which bypass them.
8. Design callbacks safely around inserts/saves, transactions, retries, and multi-tenancy.
9. Implement **ReactiveBeforeSaveCallback** when using ReactiveMongoTemplate.
10. Test both the entity and raw BSON after writing against real MongoDB.

## 2. Two Representations of One Object: Entity and BSON Document

A Java entity is mapped into BSON data to send to MongoDB:

~~~mermaid
flowchart LR
    A["CatalogProduct Java"] --> B["MappingMongoConverter"]
    B --> C["org.bson.Document"]
    C --> D["MongoDB Java Driver"]
    D --> E["Collection catalog_products"]
~~~

Example entity:

~~~java
package com.example.catalog;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "catalog_products")
public record CatalogProduct(
    @Id ObjectId id,
    @Field("tenant_id") String tenantId,
    String sku,
    @Field("display_name") String displayName,
    String status,
    Instant createdAt
) {}
~~~

An entity instance might contain:

~~~java
CatalogProduct product = new CatalogProduct(
    new ObjectId(),
    "shop-a",
    "BOOK-101",
    "  Spring Data MongoDB  ",
    "ACTIVE",
    Instant.parse("2025-06-01T09:00:00Z")
);
~~~

After the conversion step, the BSON document looks like:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenant_id: "shop-a",
  sku: "BOOK-101",
  display_name: "  Spring Data MongoDB  ",
  status: "ACTIVE",
  createdAt: ISODate("2025-06-01T09:00:00Z"),
  _class: "com.example.catalog.CatalogProduct"
}
~~~

This is **illustrative** BSON, not a claim that every deployment always includes **_class**. The type discriminator field depends on MongoTypeMapper configuration, mapping context, and converter choices.

### 2.1. Why Might Field Names Differ from Java?

Spring Data MongoDB may apply:

- **@Id** to store ObjectId under the **_id** key.
- **@Field** to map **tenantId → tenant_id**.
- **@Field** to map **displayName → display_name**.
- Converters to translate Java types to appropriate BSON types.
- Mapping metadata for nested objects, enums, numbers, and type hints.

Thus, inside BeforeSaveCallback, **Document holds the mapped keys**, not always the Java property names. Writing **document.put("displayName",...)** will likely add an unintended new BSON field instead of updating **display_name**.

### 2.2. The Java Entity and Document Are Not the Same Object

~~~text
Java entity:
    displayName = "  Spring Data MongoDB  "

Converted Document:
    display_name = "  Spring Data MongoDB  "
~~~

Document is constructed from entity data during conversion. Once created, changing an entity property **does not trigger a second conversion**.

This is the root cause of a very common mistake when using BeforeSaveCallback.

## 3. Where Does BeforeSaveCallback Sit in the Lifecycle?

Simplified write pipeline along the mapping path:

~~~mermaid
sequenceDiagram
    participant S as Service/Repository
    participant T as MongoTemplate
    participant BC as BeforeConvertCallback
    participant C as MongoConverter
    participant BS as BeforeSaveCallback
    participant D as MongoDB Driver
    S->>T: insert or save(entity)
    T->>BC: onBeforeConvert(entity, collection)
    BC-->>T: processed entity
    T->>C: convert entity to Document
    C-->>T: mapped Document
    T->>BS: onBeforeSave(entity, Document, collection)
    BS->>BS: Can mutate Document directly
    BS-->>T: Return entity
    T->>D: Send Document for write
    D-->>T: Write result
    T-->>S: save/insert result
~~~

In a system with both Spring **ApplicationEvents** and EntityCallbacks, BeforeConvertEvent/BeforeSaveEvent and callbacks can coexist. The diagram focuses on conversion and callback checkpoints, omitting event details, ID generation, auditing, and AfterSave.

### 3.1. Timing Table

| Extension Point | Timing | What Should Be Modified |
| --- | --- | --- |
| BeforeConvertCallback | Before MappingMongoConverter | Java Entity |
| BeforeSaveCallback | After convert, before insert/save command | **BSON Document** |
| AfterSaveCallback | After MongoDB write succeeds | Returned entity / appropriate side effect |
| AfterConvertCallback | After reading and converting Document to entity | Loaded entity |

**Only changes to Document inside BeforeSaveCallback directly affect the data written at that moment.** Mutating persistent entity fields inside BeforeSaveCallback is too late for conversion.

### 3.2. "BeforeSave" Is Not "BeforeConvert"

The callback name can mislead people into thinking any property mutation will be saved. The Spring Data MongoDB Javadoc emphasizes that the callback is invoked **after the entity has been converted into a Document**; Document is what gets written, and changes to persistent properties on the entity in this callback are not re-examined.

### 3.3. Callback Timing Inside a Transaction

If a save executes inside a MongoDB transaction, the callback executes when processing the write command **within the transaction**, not after commit. A later failure can still cause the transaction to roll back; external side effects triggered by the callback are not rolled back alongside MongoDB.

## 4. Official API Signature

~~~java
package org.springframework.data.mongodb.core.mapping.event;

import org.bson.Document;
import org.springframework.data.mapping.callback.EntityCallback;

@FunctionalInterface
public interface BeforeSaveCallback<T> extends EntityCallback<T> {

    T onBeforeSave(T entity, Document document, String collection);
}
~~~

The snippet above is an **illustrative signature of the framework interface**, not code to redefine the interface in your project. Applications import the interface provided by Spring Data MongoDB.

Three parameters:

| Parameter | Meaning | Usage Guidance |
| --- | --- | --- |
| entity | Domain object at save time | Read business info, inspect input values |
| document | Converted **org.bson.Document** | Modify BSON fields to be persisted |
| collection | Target collection name | Control scope if callback handles multiple cases |

The return value is **T**, which can be the same entity or another instance. However, **changing persistent fields on T does not cause MongoConverter to re-convert Document**. So in this callback, you should only replace the entity for transient attributes or when an explicit return-object contract exists.

### 4.1. Do Not Confuse Document Types

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.Document;
~~~

These two types are **different**:

- **org.bson.Document** is the BSON data class from the Java Driver.
- **org.springframework.data.mongodb.core.mapping.Document** is the annotation placed on entities.

If a Java file needs both, import `org.bson.Document` and use the annotation fully qualified on the entity, or put them in separate files. Java cannot import two types with the same simple name without disambiguation.

### 4.2. Registration

A Spring bean implementing BeforeSaveCallback with a matching generic type is picked up by the callback infrastructure:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.bson.Document;

@Component
public class CatalogProductBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        return entity;
    }
}
~~~

You do not need to call **onBeforeSave** manually from each service. Register the callback in the Spring ApplicationContext and let MongoTemplate/repository mapping lifecycles invoke it at the right stage.

## 5. Main Example: Adding search_display and write_schema to Document

Requirements:

1. The **display_name** field preserves the exact user-entered value for UI display.
2. The **search_display** field holds a normalized version for search.
3. The **write_schema** field holds an integer indicating the structural version.
4. These two extra fields **do not need to exist in the CatalogProduct entity**.

Example callback:

~~~java
package com.example.catalog;

import java.text.Normalizer;
import java.util.Locale;
import org.bson.Document;
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

@Component
public class CatalogProductBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        if (!"catalog_products".equals(collection)) {
            return entity;
        }

        String displayName = document.getString("display_name");

        if (displayName == null) {
            document.remove("search_display");
        } else {
            String normalized = Normalizer.normalize(
                displayName, Normalizer.Form.NFKC)
                .trim()
                .toLowerCase(Locale.ROOT);

            document.put("search_display", normalized);
        }

        document.put("write_schema", 1);

        return entity;
    }
}
~~~

**Decisive lines**:

~~~java
document.put("search_display", normalized);
document.put("write_schema", 1);
~~~

These mutate the **converted Document**, so they are included in the final write command.

### 5.1. Why Read document.getString("display_name") Instead of entity.displayName()?

When the goal is deriving a field from the **BSON value about to be saved**, reading Document lets you observe data after mapping/converters have run. Here displayName is a String, so both may match. When custom converters or field aliases are involved, Document reflects the actual stored representation.

Do not call `getString` on a field that might not be a BSON String; for BSON Date, nested Document, or Decimal128, read with the corresponding type.

### 5.2. Does Not Automatically Strip Vietnamese Diacritics

Normalizer.NFKC and lower-casing in this example **do not remove all Vietnamese diacritics**; for instance, **Sách** keeps its accent mark. If an application needs accent-insensitive or fuzzy search, design normalization, collation, or a search engine to fit the business requirement and test language behavior.

### 5.3. Schema Version Is Not Automatic Migration Code

**write_schema=1** is metadata stored alongside the document. Setting a version does not automatically migrate existing documents, create indexes, or ensure new code can read all older versions. You still need versioned reading logic, migration/backfill jobs, and a compatibility strategy.

### 5.4. Index for the Extra Field

If services query by **search_display**, an index may be needed:

~~~javascript
db.catalog_products.createIndex(
  { tenant_id: 1, search_display: 1 },
  { name: "idx_catalog_tenant_search_display" }
);
~~~

The **search_display** field is not declared on the Java entity, yet it can still be indexed in MongoDB. Index migrations and queries/criteria must reference the exact BSON field name. Do not add indexes automatically to every field just because a callback creates it.

## 6. Post-Insert Result: Two Representations Can Differ

The service calls:

~~~java
CatalogProduct product = new CatalogProduct(
    new ObjectId(),
    "shop-a",
    "BOOK-101",
    "  Spring Data MongoDB  ",
    "ACTIVE",
    Instant.parse("2025-06-01T09:00:00Z")
);

mongoTemplate.insert(product);
~~~

The written document may contain:

~~~javascript
{
  _id: ObjectId("..."),
  tenant_id: "shop-a",
  sku: "BOOK-101",
  display_name: "  Spring Data MongoDB  ",
  search_display: "spring data mongodb",
  write_schema: 1,
  status: "ACTIVE",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

**Do not expect the CatalogProduct entity after insert to automatically gain search_display/write_schema properties**, because those properties do not exist on the Java type. They live in the persisted BSON document. Spring Data by default maps fields with corresponding metadata; extra raw fields may be ignored when reading back into CatalogProduct.

### 6.1. Mapped Document Is Not the Java Entity's Source of Truth

An entity can be converted to Document, mutated by callbacks, written successfully, and returned from save. The returned entity instance is not required to reflect every raw Document tweak unless an appropriate read/mapping step occurs.

### 6.2. If the API Needs to Return search_display

Consider defining:

- A response DTO that computes the normalized string using the same rule.
- A projection DTO that reads the BSON field if mapped.
- Or an explicit query reading back BSON when truly necessary.

**Do not rely on BeforeSaveCallback side effects to keep all in-memory Java state synchronized.**

## 7. Classic Mistake: Only Mutating the Entity Inside BeforeSaveCallback

Suppose a mutable class is used:

~~~java
public class MutableCatalogProduct {

    private String displayName;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) {
        this.displayName = value;
    }
}
~~~

An **incorrect** callback if your goal is changing the BSON value of displayName:

~~~java
@Component
public class WrongBeforeSave
        implements BeforeSaveCallback<MutableCatalogProduct> {

    @Override
    public MutableCatalogProduct onBeforeSave(
            MutableCatalogProduct entity,
            Document document,
            String collection) {

        entity.setDisplayName(
            entity.getDisplayName().trim());

        return entity;
    }
}
~~~

At this stage, the converter already created Document from the old displayName. The setter mutates the in-memory Java object, yet **does not change the contents of the Document being written**.

### 7.1. A Confusing Consequence

~~~text
Before callback:
  entity.displayName = "  Name  "
  document.displayName = "  Name  "

After callback calling only entity.setDisplayName("Name"):
  entity.displayName = "Name"
  document.displayName = "  Name  "

MongoDB receives:
  document.displayName = "  Name  "
~~~

The application screen might hold the trimmed Java object and assume clean data was saved, only for a later MongoDB read to reveal the whitespace is still there.

### 7.2. If You Need to Modify a Persistent Field Before Mapping

Choose **BeforeConvertCallback**:

~~~java
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;

@Component
public class CatalogSkuBeforeConvert
        implements BeforeConvertCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeConvert(
            CatalogProduct entity, String collection) {

        if (!"catalog_products".equals(collection)) {
            return entity;
        }

        if (entity.sku() == null
                || entity.sku().isBlank()) {
            throw new IllegalArgumentException(
                "SKU is required");
        }

        String normalizedSku =
            entity.sku().trim().toUpperCase(Locale.ROOT);

        return new CatalogProduct(
            entity.id(),
            entity.tenantId(),
            normalizedSku,
            entity.displayName(),
            entity.status(),
            entity.createdAt()
        );
    }
}
~~~

This is an **immutable record**, so the callback returns a new instance rather than calling a setter. Because it runs **before MongoConverter**, Document is created from the normalized SKU.

### 7.3. If Intentionally Mutating Document to Change the Same Field

Once BSON already exists, you could do:

~~~java
String raw = document.getString("display_name");
if (raw != null) {
    document.put("display_name", raw.trim());
}
~~~

Here **the BSON is trimmed**, while **CatalogProduct still holds the old displayName**. If the application wants the Java object and MongoDB to stay consistent, prefer normalizing the entity in BeforeConvertCallback or before calling save.

### 7.4. Rules for Choosing a Callback

| Goal | What to Choose |
| --- | --- |
| Trim SKU and have post-save entity reflect the new SKU | BeforeConvertCallback |
| Compute a value for the converter to map into BSON | BeforeConvertCallback |
| Add a field that exists only in BSON | BeforeSaveCallback |
| Remove/hide a BSON field per post-mapping policy | BeforeSaveCallback, while controlling read/write behavior |
| Clean up a DTO solely before HTTP response | Map at service/DTO layer, not a save callback |
| Log success after operation | AfterSaveCallback or appropriate infrastructure |

## 8. Interaction with @Field and Nested BSON

When an entity has:

~~~java
@Field("tenant_id")
String tenantId;

@Field("display_name")
String displayName;
~~~

the callback must use **tenant_id** and **display_name** to read or update those two keys:

~~~java
String tenant = document.getString("tenant_id");
String name = document.getString("display_name");
~~~

Calling `document.put("tenantId", ...)` can leave MongoDB containing **both tenant_id and tenantId**:

~~~javascript
{
  tenant_id: "shop-a",
  tenantId: "shop-a"
}
~~~

That violates the schema; the converter will not automatically rename keys a second time.

### 8.1. Nested Documents

Suppose an entity maps to:

~~~javascript
{
  tenant_id: "shop-a",
  supplier: {
    code: " SUP-01 ",
    country: "VN"
  }
}
~~~

If the nested BSON is an **org.bson.Document**:

~~~java
Document supplier = document.get(
    "supplier", Document.class);

if (supplier != null) {
    String code = supplier.getString("code");

    if (code != null) {
        supplier.put("code", code.trim());
    }
}
~~~

This operates on the **converted nested Document**. If a custom converter stores `supplier` as a String or another BSON type, the cast above can fail. Always verify the actual data shape before mutating.

### 8.2. Arrays Containing Documents

~~~java
Object rawLines = document.get("lines");

if (rawLines instanceof java.util.List<?> lines) {
    for (Object rawLine : lines) {
        if (rawLine instanceof Document line) {
            String label = line.getString("label");
            if (label != null) {
                line.put("label", label.trim());
            }
        }
    }
}
~~~

Do not assume an array always contains Documents: it might hold scalar values, DBRefs, custom converter structures, or nulls.

### 8.3. Dynamic Field Names

When mutating dynamic field names in Document, remember MongoDB rules regarding dots (**`.`**), dollar signs (**`$`**), nested paths, and operators. **`Document.put("a.b", value)`** inserts a literal key into the Map; it does not traverse a nested path **a → b**.

To update nested fields, read and mutate the child Document or use appropriate update operators instead of assuming dotted paths traverse Maps.

## 9. What to Watch Out For with @Id, _id, and _class

MongoDB uses **_id** as the document identifier, and Spring Data typically maps the Java property annotated with **@Id** to it.

~~~java
@Id
ObjectId id;
~~~

Corresponding BSON field:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011") }
~~~

Inside **BeforeSaveCallback**, avoid arbitrarily altering **_id**:

~~~java
// Do not do this:
document.put("_id", new ObjectId());
~~~

Doing so can leave the Java entity holding a different ID from the written document, causing broken links and conflicts on later saves/updates. For existing documents, **_id** is immutable.

### 9.1. Where Should IDs Be Generated?

If business IDs must be generated, decide prior to conversion—for example in the service or **BeforeConvertCallback**—aligned with Spring Data's ID generation and mapping strategy.

Do not use BeforeSaveCallback to alter a document's ID after conversion without an explicit contract covering the returned object, save mode, and idempotency.

### 9.2. Do Not Blindly Remove _class

Spring Data MongoDB may store a type hint like:

~~~javascript
{ _class: "com.example.catalog.CatalogProduct" }
~~~

Removing or altering **_class** in a callback without understanding **DefaultMongoTypeMapper** can lose type metadata when reading polymorphic data. To customize type-hint policies, configure the converter/type mapper at the proper layer instead of silently stripping it per document.

### 9.3. Do Not Interfere with @Version Manually

If an entity uses optimistic locking:

~~~java
@Version
Long version;
~~~

Spring Data manages version values, update conditions, and callbacks according to its own rules. Do not directly alter **version** inside Document like an arbitrary counter, as that can desynchronize optimistic-lock checks from persisted state.

## 10. Interaction with Auditing

Spring Data MongoDB supports auditing via annotations like:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant modifiedAt;
~~~

When auditing is enabled, **AuditingEntityCallback** runs at the **BeforeConvertCallback** stage with a defined order (typically 100 in Spring Data documentation), meaning auditing values pass through the converter before the BeforeSave phase.

### 10.1. Example Auditing Flow

~~~mermaid
flowchart TD
    A["New entity"] --> B["Auditing BeforeConvertCallback"]
    B --> C["createdAt/modifiedAt on entity"]
    C --> D["MongoConverter"]
    D --> E["Document has BSON date fields"]
    E --> F["Custom BeforeSaveCallback"]
    F --> G["MongoDB insert/save"]
~~~

This differs from a BeforeSave callback calling a setter on `entity.modifiedAt`. A setter running **after conversion** changes the in-memory entity without updating the persisted field.

### 10.2. What About Server-Side Dates?

Spring Data mapping callbacks and update operators like **$currentDate** are two distinct mechanisms. For full inserts/saves, auditing callbacks fit well; for query-based updates, define an explicit timestamp update strategy.

Do not assume auditing callbacks run on every **updateFirst/findAndModify/bulk update** the same way as entity saves.

### 10.3. Prefer Built-In Mechanisms

Do not hand-roll a BeforeSaveCallback just to mimic `@CreatedDate`/`@LastModifiedDate` if auditing already satisfies the need. Reserve extra callbacks for truly specific BSON rules.

## 11. How Does BeforeSaveCallback Differ from BeforeSaveEvent?

Spring Data MongoDB also has **lifecycle ApplicationEvents**, such as:

~~~java
import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveEvent;

public class ProductBeforeSaveListener
        extends AbstractMongoEventListener<CatalogProduct> {

    @Override
    public void onBeforeSave(
            BeforeSaveEvent<CatalogProduct> event) {
        // Can access event.getSource()
        // and event.getDocument() per framework API.
    }
}
~~~

This is a separate example of an **event listener**, not a BeforeSaveCallback implementation. Both share lifecycle concepts yet integrate differently.

| Criterion | BeforeSaveCallback | BeforeSaveEvent listener |
| --- | --- | --- |
| Mechanism | Spring Data EntityCallback | Spring ApplicationEvent |
| Signature | onBeforeSave(entity, Document, collection) | onBeforeSave(BeforeSaveEvent<T>) |
| Return | Returns entity T | Listener is typically void |
| Ordering | Deterministic callback chain via ordering | Depends on event multicaster/listener setup |
| Reliable ordered mutation | Better suited for pre-write data changes | Risk of asynchrony if multicaster is configured async |
| Reactive counterpart | ReactiveBeforeSaveCallback | Cannot swap in sync events and assume non-blocking |

### 11.1. Why Are EntityCallbacks Recommended for Entity/BSON Mutations?

EntityCallbacks were built by Spring Data to handle checkpoints with clear ordering in the processing chain, across both imperative and reactive APIs. Event listeners route through **ApplicationEventMulticaster**, which may use an async executor and lose guarantees that mutations finish before writing.

So whenever BSON must be modified before sending to the driver, **BeforeSaveCallback** is a more natural fit than an event listener subject to multicaster scheduling.

### 11.2. When Both Exist

Per Spring Data docs, store-specific lifecycle ApplicationEvents are still published at their respective checkpoints; they are published **before** any registered EntityCallbacks. In practice, never build data rules implicitly depending on an event listener mutating a field in an unguaranteed order.

### 11.3. Events for Embedded Values

Standard lifecycle events fire for **root-level types**, not automatically for every embedded object as an independent aggregate. To modify nested fields inside the same root BSON, handle it in the root entity's callback or at the converter/schema level.

## 12. When Multiple BeforeSaveCallbacks Exist: Execution Order

An application might have several callbacks targeting **CatalogProduct**:

- Callback A adds `search_display`.
- Callback B strips forbidden fields.
- Callback C adds write-source metadata.

If multiple callbacks mutate the same field, whichever runs later can overwrite earlier changes. Spring Data EntityCallback supports **Ordered** or **@Order** to control execution sequence.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

@Component
@Order(100)
public class SearchFieldBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        String name = document.getString("display_name");
        if (name != null) {
            document.put("search_display",
                name.trim().toLowerCase(java.util.Locale.ROOT));
        }
        return entity;
    }
}
~~~

A second callback:

~~~java
@Component
@Order(200)
public class WriteSourceBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        document.put("write_source", "CATALOG_SERVICE");
        return entity;
    }
}
~~~

Lower order numbers generally run first. **These two classes are an alternative/standalone example compared to the main callback in section 5**; do not register all of them together without checking overlapping behavior.

### 12.1. Ordering Does Not Cross Phases

**@Order does not turn BeforeSave into BeforeConvert.** Even a BeforeSave callback running first within its group still receives an already-converted Document.

### 12.2. Design Rules for Multiple Callbacks

1. Clearly assign which callback owns which field.
2. Avoid having two callbacks mutate the same BSON key unless an explicit ordering contract exists.
3. Keep callbacks deterministic and free of external I/O.
4. Set `@Order` deliberately and document why.
5. Test the entire chain against real MongoDB data.

### 12.3. Auditing Order Does Not Reorder Phases

AuditingEntityCallback has its order within the **BeforeConvertCallback** group. Putting `@Order(50)` on a BeforeSaveCallback does not make it run before pre-conversion auditing.

## 13. Registering Callbacks via @Component or @Bean

Spring Data discovers EntityCallback beans registered in Spring's **ApplicationContext**.

### 13.1. Component Scanning

~~~java
@Component
public class CatalogProductBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {
    // ...
}
~~~

The class must be picked up by component scanning. If the package lies outside the Spring Boot application's scan root, **@Component** alone may not register the bean.

### 13.2. @Bean with Explicit Generic Type

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

@Configuration
class CatalogCallbackConfiguration {

    @Bean
    BeforeSaveCallback<CatalogProduct> productBeforeSaveCallback() {
        return (entity, document, collection) -> {
            document.put("write_schema", 1);
            return entity;
        };
    }
}
~~~

This is an alternative to `@Component`; do not register it alongside another callback with the same responsibility unless intentional.

### 13.3. Prefer Concrete Classes

Spring Data categorizes callbacks by generic target type. With lambdas or overly broad erased types, the runtime may not resolve the domain type as cleanly as with a concrete class. For critical callbacks across multiple domain types, prefer a concrete implementation class **BeforeSaveCallback<CatalogProduct>**.

### 13.4. Do Not Invoke Callbacks Manually

If you want to normalize a DTO on API intake, call a normalization function in the service/validator. Never invoke **onBeforeSave** manually outside the lifecycle, as that risks running logic twice or passing an improperly converted Document.

## 14. Collection and Domain Type Scope

The generic **BeforeSaveCallback<CatalogProduct>** defines the target domain type. The callback also receives the actual **collection** used by the write operation.

~~~java
if (!"catalog_products".equals(collection)) {
    return entity;
}
~~~

This guard is helpful if the same entity is saved to another collection with different schema/index rules. However, **never rely solely on collection names for authorization or data classification**.

### 14.1. Collection Overrides

Some MongoTemplate overloads let you specify an explicit collection name. If a service calls `save(entity, "catalog_products_archive")`, the callback receives that collection name; you may need to:

- Apply the same BSON rules.
- Enforce a separate schema policy.
- Or intentionally skip the callback for archive collections.

Base this decision on business contracts. Do not let archive data slip through unvalidated simply because the callback silently returned.

### 14.2. Multiple Tenants in a Shared Collection

For a shared collection:

~~~javascript
{
  tenant_id: "shop-a",
  sku: "BOOK-101"
}
~~~

**The collection name does not distinguish tenants.** The callback can inspect `document.getString("tenant_id")` to apply policies, but `tenantId` must be established by the service from a trusted authentication/authorization context.

### 14.3. Do Not Mistake Generic Callbacks for Schema Validators

Spring Data invokes callbacks only on write paths integrated with mapping. Raw driver commands, other apps, or admin scripts can bypass them. To protect collection-level invariants across all writers, consider **MongoDB schema validation**, unique indexes, and write permissions.

## 15. Insert/Save Have Callbacks; What About Query-Based Updates?

This is a critical limitation in this lesson.

~~~java
mongoTemplate.insert(product);
mongoTemplate.save(product);
repository.save(product);
repository.insert(product);
~~~

Entity write operations going through the **mapping lifecycle** such as insert/save trigger BeforeConvert/BeforeSave callbacks accordingly.

By contrast, a query-based update:

~~~java
Query query = Query.query(
    Criteria.where("sku").is("BOOK-101")
);

Update update = new Update()
    .set("displayName", "New Name");

mongoTemplate.updateFirst(
    query, update, CatalogProduct.class);
~~~

does not instantiate a new CatalogProduct entity and convert it into a full Document. MongoDB receives **update operators** or a pipeline update. Thus **BeforeSaveCallback is not automatically invoked for this style of update**.

### 15.1. Why Is This a Risk for Derived Fields?

Suppose before the update:

~~~javascript
{
  display_name: "Old Product",
  search_display: "old product"
}
~~~

The service runs:

~~~java
new Update().set("displayName", "New Product");
~~~

After the update:

~~~javascript
{
  display_name: "New Product",
  search_display: "old product"
}
~~~

If `search_display` is maintained **only via BeforeSaveCallback**, it becomes stale whenever a write path uses `updateFirst`.

### 15.2. Strategies to Prevent Stale Derived Fields

1. **Mandate that every relevant update writes both fields** in the service.
2. Create a shared helper computing normalized values for both insert/save and updates.
3. Where appropriate, use a MongoDB aggregation pipeline update to recompute derived fields server-side.
4. Use a separate snapshot or reindex/backfill job when eventual consistency is acceptable.
5. Write integration tests covering **both insert/save and updateFirst/findAndModify/bulk writes**.

Do not work around this by calling BeforeSaveCallback manually with a fake Document outside the converter and treating it as an automatic lifecycle update.

### 15.3. Other Write Paths

| Operation | Can You Rely on BeforeSaveCallback? |
| --- | --- |
| MongoTemplate.insert(entity) | **Yes**, on mapped entity lifecycle |
| MongoTemplate.save(entity) | **Yes**, on mapped entity lifecycle |
| Repository.save(entity) | **Yes**, when delegating through store mapping lifecycle |
| Repository.insert(entity) | **Yes**, in standard integrations |
| MongoTemplate.updateFirst(Query, Update, type) | **No**, does not convert full entity to save |
| MongoTemplate.updateMulti(...) | **No**, same reason |
| MongoTemplate.findAndModify(Query, Update, ...) | **No**, operator update is not an entity save |
| BulkOperations.updateOne/updateMulti | **Not by default**, operator/bulk commands |
| Raw MongoCollection.insertOne(Document) | **No**, bypasses Spring Data EntityCallbacks |
| mongoTemplate.remove(...) | **No**, deletes documents |

For **insertAll**, **saveAll**, or overloads with differing bulk/driver optimizations, verify behavior for your exact version and API; do not assume every batch path executes identically to individual `save(entity)` calls.

### 15.4. Indexes and Transactions Do Not Invoke BeforeSaveCallback

Index creation, counts, aggregation reads, query explains, or beginning/committing transactions do not convert an entity to save a Document through this lifecycle.

## 16. Idempotency and Multiple Callback Executions

A save can be executed more than once due to:

- User resubmitting an HTTP request.
- Application retries after a timeout.
- Transaction retries on transient errors.
- Scheduler re-running a job.
- Entity being saved again in another workflow.

If a callback runs:

~~~java
document.put("tags",
    document.getList("tags", String.class)
        .stream()
        .map(tag -> tag + "-indexed")
        .toList());
~~~

then reading a persisted document and saving it again produces values like **java-indexed-indexed**.

### 16.1. Choose Idempotent Transformations

Normalize from stable source data:

~~~java
String displayName = document.getString("display_name");
if (displayName != null) {
    document.put("search_display",
        displayName.trim().toLowerCase(java.util.Locale.ROOT));
}
~~~

The same input yields the same output. Never append suffixes or increment counters inside a callback without an anti-duplication guard.

### 16.2. Random UUIDs and Clocks

~~~java
// Do not use for an operation ID that must remain stable across retries:
document.put("operation_id", java.util.UUID.randomUUID().toString());
~~~

A callback can re-run and generate a new operationId, losing the ability to identify the same business request. Operation IDs/idempotency keys belong in the business layer and should be persisted via transactions/unique indexes when needed.

A timestamp like `writeProcessedAt` can make sense if its meaning is "time of each write attempt," but never use it as proof that an order was processed once.

### 16.3. External Side Effects Are Not Part of the Transaction

~~~java
@Override
public CatalogProduct onBeforeSave(
        CatalogProduct entity,
        Document doc,
        String collection) {

    // Never call payment gateways, send emails, or
    // publish to a message broker directly here.
    return entity;
}
~~~

The callback runs **before** the MongoDB write completes. If the write fails, the transaction rolls back, or the client retries, external side effects will not roll back automatically. Use **outbox, after-commit workflows, or state machines** for durable side effects.

## 17. Exceptions from Callbacks

Callbacks can throw exceptions on invalid data:

~~~java
if (entity.tenantId() == null
        || entity.tenantId().isBlank()) {
    throw new IllegalArgumentException(
        "tenantId is required");
}
~~~

When a callback throws on a standard lifecycle save, execution **does not proceed to the write**, and the caller receives the error on its call stack.

### 17.1. Do Not Rely on Callbacks as the Sole Security Boundary

Spring callbacks do not run when another writer uses the raw MongoDB Driver or a script. If you need:

- `tenantId` mandatory.
- SKU unique within a tenant.
- Non-negative fields.
- No dangerous BSON values.

you need a combination of **service validation, MongoDB schema validators, unique indexes, and access control**. BeforeSaveCallback is simply a convenient enforcement point inside the application.

### 17.2. Callback Failure Does Not Roll Back Prior Work

If a service already wrote to another collection and then calls `save(entity)` which hits a callback exception, earlier writes **do not automatically roll back** without a MongoDB transaction. A callback is not a transaction manager.

### 17.3. Avoid Leaking Sensitive Data in Error Messages

Never dump raw Documents or sensitive customer/order fields into exception messages or logs. Log only permitted identifiers, error types, and safe diagnostic metadata.

## 18. Performance: Callbacks Are Not for Extra I/O

A frequently invoked BeforeSaveCallback sits on a hot write path. If every save executes an extra query or HTTP call:

~~~java
// Anti-pattern:
CustomerDocument customer =
    customerRepository.findById(entity.customerId()).orElseThrow();

document.put("customer_name", customer.displayName());
~~~

round trips multiply, the callback becomes hard to test, and callback recursion can occur if it triggers saves on other entities.

### 18.1. Suitable for Small, Deterministic Processing

Good fits:

- Trimming/normalizing a few BSON fields.
- Adding a deterministic derived field.
- Stripping a clearly defined sensitive field.
- Adding controlled schema-version metadata.

Avoid:

- Querying dozens of collections.
- Calling payment gateways/HTTP APIs.
- Running heavy aggregations.
- Writing to other collections as a side effect.
- Sleeping or holding locks for long periods.
- Unnecessarily serializing huge object graphs.

### 18.2. Watch Throughput

At 10,000 saves/s, a callback running O(N) logic over large arrays on every document consumes noticeable CPU. Measure callback timing and payload sizes; avoid copying documents repeatedly unless necessary.

### 18.3. Do Not Treat Event Multicasters as Synchronous Callbacks

BeforeSaveCallback runs in an ordered callback chain; a BeforeSaveEvent listener is subject to event multicaster scheduling. If data must change **before the write**, never switch to an async event just to "optimize" at the cost of losing timing guarantees.

## 19. Data Safety: Intentionally Removing Fields from BSON

A BeforeSaveCallback can strip a field not allowed to be stored. Suppose a legacy mapping still has **rawAccessToken**, yet security policy forbids persisting it to the collection.

~~~java
@Override
public CatalogProduct onBeforeSave(
        CatalogProduct entity,
        Document document,
        String collection) {

    document.remove("raw_access_token");
    return entity;
}
~~~

This example only illustrates **`Document.remove`**; the sample CatalogProduct has no rawAccessToken. Never base a critical security policy solely on a callback that external write paths can bypass.

### 19.1. Better Design: Never Map Secrets in the First Place

If a field must never be persisted:

- Exclude it from the persistent entity.
- Use **@Transient** on the Java property if it must temporarily stay in memory.
- Separate request DTOs carrying secrets from persistence models.
- Configure converters to persist only allowlisted data.
- Enforce MongoDB schema validation and write permissions where needed.

If secrets truly must be stored, use proper encryption/key management rather than just stripping a field "to be safe."

### 19.2. What If the Field Already Exists in Legacy Data?

Stripping a field from Document before new saves does not clean up old documents. Run a migration/backfill/retention policy on historical records, and assess impact on backups and replicas.

### 19.3. Do Not Log Whole BSON Payloads

Avoid:

~~~java
log.debug("Saving {}", document.toJson());
~~~

If Document holds personal data or tokens, logs become a sensitive-data leak. Log only approved fields and truncate safely.

## 20. Callbacks and Business Rules: Keep Responsibilities in the Right Layer

Logic suited for callbacks:

- Adding a pure search key derived from an existing field.
- Normalizing BSON metadata.
- Writing a static schema version.
- Dropping a BSON field per clear schema rules.

Logic that generally belongs in the service/domain layer:

- Checking which tenants a user is authorized to update.
- Deciding whether an order may transition state.
- Checking whether sufficient inventory remains for sale.
- Sending notifications or charging payments.
- Guarding business operations against duplicate submission.
- Coordinating multiple collections with transactions.

### 20.1. Why Can't Callbacks Guarantee Uniqueness?

Two concurrent requests can both pass a callback check seeing an SKU as "not yet taken." Both proceed. Only a **MongoDB unique index** enforces server-side uniqueness under contention.

### 20.2. Why Don't Callbacks Replace Authorization?

If a client passes `tenantId` and the service skips checking it, a callback reading **tenant_id** still cannot tell whether the user is permitted to write to that tenant. Authentication/authorization must happen in the service layer, with tenant-scoped update filters.

### 20.3. Extract Pure Functions for Reuse

To prevent search normalization from diverging between BeforeSaveCallback and Update builders:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public final class SearchNormalizer {

    private SearchNormalizer() {}

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }
        return Normalizer.normalize(
            value, Normalizer.Form.NFKC)
            .trim()
            .toLowerCase(Locale.ROOT);
    }
}
~~~

Both the callback and service updates can then call **SearchNormalizer.normalize**. When rules change, there is one place to update and test.

### 20.4. Server-Owned vs. App-Owned Metadata

Fields like `write_source` or `write_schema` can be set by the app in a callback. Fields like `updatedAt` may be set via auditing or MongoDB `$currentDate`. Document clearly which source owns each value, its timezone/clock, and its semantics so two mechanisms do not overwrite each other.

## 21. BeforeSaveCallback with Transactions and Sessions

Suppose a service executes:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void publishProduct(CatalogProduct product) {
    mongoTemplate.save(product);
    outboxRepository.insert(buildOutbox(product));
}
~~~

In a transaction-capable MongoDB deployment with **MongoTransactionManager** configured, mapping saves and outbox inserts can join the same ClientSession/transaction.

BeforeSaveCallback runs when MongoTemplate processes **save(product)**—that is, **before the entire transaction commits**.

### 21.1. What If It Rolls Back?

Suppose the callback adds `search_display`, then inserting the outbox record fails and the transaction rolls back:

~~~text
BeforeSaveCallback: modifies Document
MongoDB: receives save command inside transaction
Outbox insert: fails
Transaction: aborts
=> Neither save nor outbox is committed in transaction
~~~

However, the callback already executed in the JVM. If it wrote a file, sent an email, or published a message externally, that side effect **does not roll back**.

### 21.2. Retrying the Whole Transaction

When a transaction fails transiently and retries from the beginning, the callback may be invoked again. Therefore, callbacks should be **deterministic/idempotent** and never generate a fresh operation ID per run when business logic requires a stable ID.

### 21.3. Raw Driver Inside a Transaction

If code uses raw MongoCollection directly with another MongoClient/session, BeforeSaveCallback does not run merely because Spring `@Transactional` wraps the method. All guarantees depend on the exact write path and session integration.

### 21.4. Transactions Do Not Invoke Callbacks for Query Updates

An `updateFirst` executing **inside a transaction** is still a query-based update and does not build an entity-converted Document via BeforeSaveCallback. Transactions govern commit/rollback atomicity, not which lifecycle hooks run.

## 22. ReactiveBeforeSaveCallback: Same Phase, Different Return Type

In the reactive stack, Spring Data MongoDB provides the corresponding interface:

~~~java
package org.springframework.data.mongodb.core.mapping.event;

import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.data.mapping.callback.EntityCallback;

@FunctionalInterface
public interface ReactiveBeforeSaveCallback<T>
        extends EntityCallback<T> {

    Publisher<T> onBeforeSave(
        T entity, Document document, String collection);
}
~~~

This is an **illustrative framework signature**, not a file to redefine yourself. The reactive variant returns **`Publisher<T>`**, typically `Mono<T>`.

### 22.1. Reactive Callback Example

~~~java
package com.example.catalog;

import java.text.Normalizer;
import java.util.Locale;
import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeSaveCallback;
import reactor.core.publisher.Mono;

@Component
public class ReactiveCatalogProductBeforeSave
        implements ReactiveBeforeSaveCallback<CatalogProduct> {

    @Override
    public Publisher<CatalogProduct> onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        if ("catalog_products".equals(collection)) {
            String name = document.getString("display_name");

            if (name != null) {
                document.put("search_display",
                    Normalizer.normalize(
                        name, Normalizer.Form.NFKC)
                        .trim()
                        .toLowerCase(Locale.ROOT));
            }
            document.put("write_schema", 1);
        }

        return Mono.just(entity);
    }
}
~~~

When using **ReactiveMongoTemplate** or reactive repositories through lifecycle mapping, reactive callbacks participate in the reactive processing chain.

### 22.2. Imperative Callbacks Do Not Automatically Apply to Reactive

Spring Data's EntityCallback API separates the two execution models:

- **BeforeSaveCallback<T>** for imperative mapping.
- **ReactiveBeforeSaveCallback<T>** for reactive mapping.

If an application uses both stacks, register the appropriate callback for each write path. Never expect an `@Component` implementing `BeforeSaveCallback` to run automatically during **`ReactiveMongoTemplate.save`**.

### 22.3. Mono.just Does Not Perform an Independent Write

~~~java
return Mono.just(entity);
~~~

This is the Publisher emitting the entity back to the callback pipeline. **Never call `subscribe()` yourself** to force writing BSON; the write continues via ReactiveMongoTemplate/repository when the caller subscribes to the save publisher.

### 22.4. Do Not Block Inside Reactive Callbacks

~~~java
// Do not do this:
CustomerDocument customer =
    blockingCustomerRepository.findById(id).orElseThrow();
~~~

Putting blocking I/O in a reactive callback can stall reactive threads. If asynchronous lookup is needed, move that logic to a **reactive service** and compose within Mono/Flux with clear lifecycle and error handling, rather than hiding N+1 lookups inside mapping callbacks.

### 22.5. When a Reactive Save Is Subscribed Twice

A save publisher can accidentally be subscribed twice in a faulty flow, triggering two writes and two callback runs. **Reactive does not give automatic idempotency.** If a business operation can be replayed, enforce operation IDs/unique constraints at the service layer.

## 23. Unit Testing the Callback Without MongoDB

First, you can test `onBeforeSave` as a pure function:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;

class CatalogProductBeforeSaveUnitTest {

    @Test
    void enrichesConvertedDocumentButReturnsEntity() {
        CatalogProduct entity = new CatalogProduct(
            new ObjectId(),
            "shop-a",
            "BOOK-101",
            "  MongoDB Guide  ",
            "ACTIVE",
            Instant.parse("2025-06-01T09:00:00Z")
        );

        Document bson = new Document()
            .append("_id", entity.id())
            .append("tenant_id", entity.tenantId())
            .append("sku", entity.sku())
            .append("display_name", entity.displayName());

        CatalogProductBeforeSave callback =
            new CatalogProductBeforeSave();

        CatalogProduct result = callback.onBeforeSave(
            entity, bson, "catalog_products");

        assertThat(result).isSameAs(entity);
        assertThat(bson.getString("search_display"))
            .isEqualTo("mongodb guide");
        assertThat(bson.getInteger("write_schema"))
            .isEqualTo(1);
        assertThat(bson.getString("display_name"))
            .isEqualTo("  MongoDB Guide  ");
    }
}
~~~

**This test verifies callback logic** given a Document with BSON keys. It does not prove Spring Data invokes the callback in the right place, check `@Field` mappings, or prove persistence. Integration tests below cover that.

### 23.1. Unit Tests Should Not Manually Invoke the Converter Unnecessarily

If the goal is testing normalization only, passing a constructed Document keeps the test small and MongoDB-free. If the goal is verifying **mapping + lifecycle + database**, write a test that calls real **MongoTemplate.insert/save**.

### 23.2. Testing Null/Missing Values

Test a Document without **display_name**, or with a null value. The main callback in section 5 must **remove("search_display")** without throwing a NullPointerException.

### 23.3. Testing Other Collections

When passing collection **catalog_products_archive**, the callback returns the entity without modifying Document. If schema rules require `search_display` on archives too, adjust the collection guard intentionally.

## 24. Integration Test: Reading Back Raw BSON After Insert

A real MongoDB test should verify three things:

1. Spring Data invokes **BeforeConvertCallback** prior to conversion.
2. Spring Data invokes **BeforeSaveCallback** after conversion and writes new fields into Document.
3. Fields in MongoDB match the **actual BSON key names**, not merely Java properties.

### 24.1. @DataMongoTest with @Import Callbacks

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import({
    CatalogSkuBeforeConvert.class,
    CatalogProductBeforeSave.class
})
class CatalogProductCallbackIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Test
    void savesMappedFieldsAndBeforeSaveBsonFields() {

        ObjectId id = new ObjectId();
        CatalogProduct product = new CatalogProduct(
            id,
            "shop-a",
            "  book-101 ",
            "  Sách MongoDB  ",
            "ACTIVE",
            Instant.parse("2025-06-01T09:00:00Z")
        );

        try {
            template.insert(product);

            Document raw = template
                .getCollection("catalog_products")
                .find(new Document("_id", id))
                .first();

            assertThat(raw).isNotNull();
            assertThat(raw.getString("tenant_id"))
                .isEqualTo("shop-a");
            assertThat(raw.getString("sku"))
                .isEqualTo("BOOK-101");
            assertThat(raw.getString("display_name"))
                .isEqualTo("  Sách MongoDB  ");
            assertThat(raw.getString("search_display"))
                .isEqualTo("sách mongodb");
            assertThat(raw.getInteger("write_schema"))
                .isEqualTo(1);
            assertThat(raw.containsKey("displayName"))
                .isFalse();

            CatalogProduct loaded =
                template.findById(id, CatalogProduct.class);

            assertThat(loaded).isNotNull();
            assertThat(loaded.sku())
                .isEqualTo("BOOK-101");
            assertThat(loaded.displayName())
                .isEqualTo("  Sách MongoDB  ");

        } finally {
            template.remove(
                Query.query(Criteria.where("_id").is(id)),
                CatalogProduct.class
            );
        }
    }
}
~~~

**Explanation:**

- BeforeConvertCallback uppercases the SKU.
- Converter maps **tenantId → tenant_id**, **displayName → display_name**.
- BeforeSaveCallback adds **search_display/write_schema** to the converted Document.
- MongoDB persists the extra fields.
- Reading back CatalogProduct still yields the **original displayName**, since the callback only added separate fields to BSON.

### 24.2. Why Use @Import?

**@DataMongoTest** is a test slice. Do not assume every `@Component` across all application packages is automatically scanned in this slice. `@Import` explicitly registers the callbacks under test, making wiring verifiable.

### 24.3. Isolated Test Database

This example requires a compatible test MongoDB instance configured by your project (e.g., via Testcontainers). Never run this test against production. Maintain isolation between tests and never use real user tenant IDs.

### 24.4. Reading Raw BSON vs. Reading the Entity

~~~java
Document raw = template.getCollection(
    "catalog_products").find(new Document("_id", id)).first();
~~~

The raw collection reveals the exact BSON keys persisted. Meanwhile:

~~~java
CatalogProduct loaded =
    template.findById(id, CatalogProduct.class);
~~~

returns the entity mapped according to the Java model. Use **both** to detect cases where a callback adds a field the entity does not expose or where the converter maps a field name incorrectly.

## 25. Integration Test: Query Updates Do Not Trigger BeforeSaveCallback

The test above proves the **insert(entity)** path. Add another test to expose the risk when updating with operators:

~~~java
import org.springframework.data.mongodb.core.query.Update;

@Test
void queryBasedUpdateCanLeaveBeforeSaveDerivedFieldStale() {
    ObjectId id = new ObjectId();

    CatalogProduct product = new CatalogProduct(
        id,
        "shop-a",
        "BOOK-102",
        "Old Name",
        "ACTIVE",
        Instant.parse("2025-06-01T09:00:00Z")
    );

    try {
        template.insert(product);

        Query byId = Query.query(
            Criteria.where("_id").is(id)
        );

        template.updateFirst(
            byId,
            new Update().set("displayName", "New Name"),
            CatalogProduct.class
        );

        Document raw = template
            .getCollection("catalog_products")
            .find(new Document("_id", id))
            .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("display_name"))
            .isEqualTo("New Name");

        // BeforeSaveCallback ran on insert,
        // but did not run for the updateFirst operator.
        assertThat(raw.getString("search_display"))
            .isEqualTo("old name");

        // A full entity save in another step can refresh
        // the derived field through the callback.
        CatalogProduct reloaded =
            template.findById(id, CatalogProduct.class);

        assertThat(reloaded).isNotNull();
        template.save(reloaded);

        Document afterSave = template
            .getCollection("catalog_products")
            .find(new Document("_id", id))
            .first();

        assertThat(afterSave).isNotNull();
        assertThat(afterSave.getString("search_display"))
            .isEqualTo("new name");

    } finally {
        template.remove(
            Query.query(Criteria.where("_id").is(id)),
            CatalogProduct.class
        );
    }
}
~~~

Place this method inside **CatalogProductCallbackIntegrationTest** from section 24. This is a critical integration test: it demonstrates the difference between the **entity save lifecycle** and the **query update lifecycle**.

### 25.1. Design Lesson

If `search_display` must always stay in sync with `display_name`, implementing BeforeSaveCallback alone **is not enough**. Every code path updating `display_name` must also update `search_display` by the same rule, or move the derived field to another suitable mechanism.

### 25.2. Do Not Treat Full Save as a Default Fix for Every Update

A naive workaround is calling `findById` immediately after `updateFirst` and then `save`. That adds round trips and risks lost updates unless concurrency/versioning is handled. Design a single update command setting all required fields or a dedicated sync mechanism rather than full-saving from potentially stale snapshots.

### 25.3. What If the Mapper Generates Different Field Names?

Testing with raw BSON confirms **display_name**, rather than just asserting a Java getter. If `@Field`, custom converters, or naming strategies change, raw BSON tests catch the mismatch immediately.

## 26. Reactive Tests and Callback Lifecycle

With **ReactiveMongoTemplate**, an example service method:

~~~java
import reactor.core.publisher.Mono;

public Mono<CatalogProduct> saveReactive(
        ReactiveMongoTemplate template,
        CatalogProduct entity) {
    return template.insert(entity);
}
~~~

**Mono<CatalogProduct>** is the returned publisher; it generally does not execute the insert until subscribed. Reactive callbacks participate in execution when the publisher runs.

### 26.1. Using StepVerifier

~~~java
StepVerifier.create(
    reactiveTemplate.insert(
        new CatalogProduct(
            new ObjectId(),
            "shop-a",
            "BOOK-103",
            "  Reactive MongoDB  ",
            "ACTIVE",
            Instant.parse("2025-06-01T09:00:00Z")
        )
    )
)
.assertNext(saved -> {
    assertThat(saved.sku()).isEqualTo("BOOK-103");
})
.verifyComplete();
~~~

This example assumes **reactiveTemplate** is injected and the **reactor-test** dependency is present. If the reactive callback only modifies raw Document and not the entity, **asserting on the saved entity does not prove raw BSON was updated**. Read back raw BSON as in section 24 or use a suitable projection/raw query.

### 26.2. Reactive Callbacks Are Not Reactive Transactions

A callback returning Mono does not automatically start a MongoDB transaction. If multiple MongoDB operations must commit/roll back together, use **ReactiveMongoTransactionManager** and compose them inside the proper transaction context.

### 26.3. Testing Errors

ReactiveBeforeSaveCallback can return:

~~~java
return Mono.error(
    new IllegalArgumentException("Invalid BSON"));
~~~

Then the save publisher emits an error signal and does not proceed through the normal write path. Tests should use `StepVerifier.expectError(...)` and confirm no new document was inserted when the callback fails in a controlled test environment.

### 26.4. Do Not Create Two Subscriptions to Test One Write

~~~java
Mono<CatalogProduct> write = reactiveTemplate.insert(product);

// Avoid subscribing twice separately and assuming only one insert occurred.
write.subscribe();
StepVerifier.create(write).verifyComplete();
~~~

Here the publisher can execute the insert twice; the second run may fail with a duplicate key on `_id`. In tests, use **a single subscription to trigger the write**, then chain a subsequent read publisher if verification is needed.

## 27. Common Mistakes When Using BeforeSaveCallback

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Calling setter yet BSON unchanged | BeforeSave runs after conversion | Mutate Document or move to BeforeConvert |
| MongoDB has both tenantId and tenant_id | Used Java name instead of BSON key | Check `@Field` mapping, mutate `tenant_id` |
| search_display stale after updateFirst | Query update skips BeforeSaveCallback | Keep fields in sync on update path |
| Raw BSON has new field yet entity lacks it | Field not declared/mapped on entity | Use DTO/projection or map appropriately |
| Callback does not run | Bean not in ApplicationContext | Check `@Component`/`@Bean`/`@Import` |
| Callback runs twice | Registered via both `@Bean` and `@Component`, or saved twice | Audit bean wiring and callers |
| `@Order` does not work as expected | Confused BeforeConvert phase with BeforeSave phase | Set order within each callback type |
| Unit test passes yet MongoDB lacks field | Invoked callback manually without lifecycle | `@DataMongoTest` + raw BSON readback |
| `_id` out of sync with entity | Mutated `_id` after converter | Generate ID before conversion; never mutate arbitrarily |
| Type mapping fails on read | Stripped/modified `_class` recklessly | Configure type mapper properly |
| Optimistic lock behaves unexpectedly | Mutated BSON version manually | Rely on `@Version`/Spring Data semantics |
| Timestamp unchanged on updateFirst | Auditing callback skips query updates | Set timestamp explicitly in Update |
| Saved data has stale search metadata | Some writer bypasses callback | Schema/migration and write-path strategy |
| Reactive write ignores sync callback | Separate callback APIs | Use `ReactiveBeforeSaveCallback` |
| Reactive callback slows app down | Blocking HTTP/repository calls inside callback | Use reactive service; remove I/O from callback |
| Email sent despite transaction abort | External side effect inside callback | Use outbox / after-commit workflow |
| Malicious/invalid data still persisted | Other writer bypasses callback | Schema validation, write permissions |
| Duplicate SKUs still inserted | Callback pre-check suffers race condition | MongoDB unique index |
| Nested field not modified | Wrong field name/path or different nested type | Inspect raw BSON and child Document |
| Callback throws causing save to fail | Invalid validation/mapping assumptions | Classify errors and fix input/schema |
| Write latency increases | Heavy work or N+1 queries in callback | Pure transforms and profiling |
| Callback bean errors on other types | Generic type too broad or erased | Use concretely typed implementations |

### 27.1. Quick Diagnostic Checklist

1. Determine whether the operation is **`insert/save(entity)`** or **`updateFirst`/bulk/raw driver**.
2. Check whether the BeforeSaveCallback bean is in the ApplicationContext.
3. Verify the entity generic type matches and any collection guard does not skip it.
4. Inspect Java schema annotations: **@Id, @Field, converters, nested mapping**.
5. Read the raw Document before callback mutation or construct a representative Document in a unit test.
6. Verify whether the logic mutates the **entity** or **Document**.
7. Check whether other BeforeConvertCallback/auditing/BeforeSaveEvent beans exist.
8. Inspect `@Order` across callbacks in the same phase.
9. Read raw BSON from MongoDB after insert/save and compare against the reloaded entity.
10. Also test query updates, transaction rollbacks, reactive paths, and retries.

## 28. Common Design Questions

### 28.1. Does Returning a New Entity from BeforeSaveCallback Update BSON?

**Not automatically.** Although the interface allows returning a different entity instance, conversion to Document has already occurred. If persistent fields on the new entity differ from Document, the persisted data still follows the already-converted/modified Document. To change persistent entity data, handle it in BeforeConvertCallback.

### 28.2. Can Both Document and Entity Be Modified Together?

It is possible in Java, but you must be clear how both states stay aligned. If both saved BSON and the returned entity must stay in sync, handling it in BeforeConvert or the business layer is usually cleaner. Avoid duplicating logic across two objects and relying on undocumented side effects.

### 28.3. Can BeforeSaveCallback Add Fields Not Present on the Entity?

**Yes.** That is a fitting use case: mutate the raw Document and the driver persists it. However, reading back the entity will not automatically provide a getter for unmapped fields.

### 28.4. Can BeforeSaveCallback Replace @Field?

No. **@Field** belongs to mapping metadata between Java properties and BSON names. BeforeSaveCallback is for post-mapping BSON additions or adjustments. Do not turn basic mapping rules into manual callback mutations.

### 28.5. Is the Callback Invoked Automatically for Embedded Items When Saving a Root?

Do not assume every embedded item gets an independent root callback. Once embedded data is converted into nested Documents, the root callback can inspect/mutate the child structures, or a custom converter can handle mapping per your model.

### 28.6. Can Callbacks Guarantee SKU Uniqueness?

No. A callback querying before saving still suffers races across concurrent writers. A matching unique index is required, such as **{tenant_id:1,sku:1} unique**.

### 28.7. Can MongoTemplate Be Called Inside a Callback for Extra Lookups?

Java syntax allows it, yet you generally **should not**: it introduces hidden I/O, adds latency, tangles transaction contexts, and risks callback recursion when saving other entities. Move multi-operation database logic into services.

### 28.8. What If Custom Converters Are Involved?

Document inside BeforeSaveCallback is the output of converters that already ran. Inspect the **actual BSON type**, rather than assuming Java String/enum/Instant keep their exact structure. If conversion contracts need to change, consider custom converters at the mapping layer.

### 28.9. Does BeforeSaveCallback Run on saveAll?

Batch-saving APIs can follow different execution paths depending on Spring Data version and bulk optimizations. Never assume from the name **saveAll** that every item behaves identically to an individual save call; write integration tests for the exact API used in production.

### 28.10. Can You Write a BeforeSaveCallback Just for Logging?

You can use callbacks for lightweight telemetry, provided logs never dump sensitive data, and remember callbacks do not guarantee the transaction committed. If metrics should reflect **completed writes**, observe post-write/post-commit at the proper layer instead of counting "before save invoked."

## 29. Hands-On Exercises

### Exercise 1: Identify Callback Timing

A CatalogProduct has `displayName="  A  "`. Spring Data has already converted the entity into a Document. Inside BeforeSaveCallback, you call `entity.setDisplayName("A")` on a mutable entity. Will MongoDB definitely store `"A"`?

**Answer:** No. The already-created Document is not automatically re-converted; you must mutate Document or move normalization to BeforeConvertCallback.

### Exercise 2: Method Signature

Complete the interface correctly:

~~~java
public class ProductCallback
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {
        return entity;
    }
}
~~~

**Answer:** Takes entity, **org.bson.Document**, and collection; returns CatalogProduct.

### Exercise 3: Mapped BSON Field Names

An entity has:

~~~java
@Field("tenant_id")
private String tenantId;
~~~

Which key do you use to read tenant from Document?

**Answer:** **tenant_id**, not `tenantId` by default.

### Exercise 4: Adding a Derived Field

Given a Document containing:

~~~javascript
{ display_name: "  MongoDB Essentials  " }
~~~

Write two lines creating `search_display` from the name:

~~~java
String name = document.getString("display_name");
document.put("search_display",
    name.trim().toLowerCase(java.util.Locale.ROOT));
~~~

**Answer:** `search_display` becomes **mongodb essentials**. In production, add null/type checks and Unicode rules.

### Exercise 5: Modifying a Persistent Field

You want SKU to be uppercased in both the returned entity after save and BSON. Choose BeforeSaveCallback or BeforeConvertCallback?

**Answer:** BeforeConvertCallback, returning an entity with the updated SKU **before conversion**. You can share a pure normalization helper from the domain/service layer.

### Exercise 6: Post-Save Result

BeforeSaveCallback adds `Document.write_schema=1`, while the entity has no matching property. Does `Repository.save` return an entity with a generated `writeSchema` getter?

**Answer:** No. Raw BSON contains `write_schema`, yet the Java type does not dynamically gain properties.

### Exercise 7: Nested Documents

Document contains:

~~~javascript
{ supplier: { code: " SUP-01 " } }
~~~

To trim `code`, can you call `document.put("supplier.code", "SUP-01")`?

**Answer:** No. `Document.put` with a dotted string inserts a literal key rather than updating the nested path like an update operator. Read **supplier** as a Document and update its **code** field.

### Exercise 8: Callback Ordering

Two BeforeSaveCallbacks both modify `search_display`. Can you rely solely on alphabetical class-name order to decide which wins?

**Answer:** No. Use **@Order/Ordered** deliberately, and even better, assign a single callback to own that field.

### Exercise 9: Auditing

You update `entity.updatedAt` in BeforeSaveCallback, yet BSON does not change. Explain why.

**Answer:** The callback runs after conversion. Use auditing/BeforeConvertCallback to modify persistent fields before mapping, or update Document/update operators per your contract.

### Exercise 10: insert vs. updateFirst

A service uses `MongoTemplate.insert`, so `search_display` is populated. Later `MongoTemplate.updateFirst` sets a new `displayName`. Is `search_display` automatically recomputed?

**Answer:** No. Query-based updates do not trigger entity save BeforeSaveCallback. Keep derived fields synchronized on the update path.

### Exercise 11: Raw Driver

A service directly calls `MongoCollection.insertOne(new Document(...))`. Does `BeforeSaveCallback<CatalogProduct>` run automatically?

**Answer:** No. The raw driver bypasses Spring Data entity mapping callback infrastructure.

### Exercise 12: Stripping _class

A callback deletes `_class` to shrink document size. Is that safe for every polymorphic entity?

**Answer:** No. `_class` may be used by converters as a type hint. Type-hint policies belong in mapping configuration and must be tested.

### Exercise 13: Schema Version

BeforeSaveCallback executes `put("write_schema", 3)`. Do existing version 1 documents in the database migrate automatically?

**Answer:** No. Callbacks run only on matching writes; stored data requires a dedicated migration/backfill.

### Exercise 14: Unique Index

Two requests use a callback checking that an SKU does not yet exist before inserting. Does the callback guarantee no duplicate SKUs?

**Answer:** No. Pre-checks suffer races. A unique index in MongoDB is required.

### Exercise 15: Exceptions

BeforeSaveCallback throws `IllegalArgumentException`. During a normal `MongoTemplate.insert`, does MongoDB receive that insert command?

**Answer:** The save pipeline stops before the normal write step; the caller receives the exception. Do not assume earlier writes in the same method roll back unless inside a transaction.

### Exercise 16: Transactions

A callback sends an email; then an outbox insert in the same MongoDB transaction fails. Is the email rolled back?

**Answer:** No. Email is outside the MongoDB transaction. Use an outbox or post-commit workflow with idempotency.

### Exercise 17: Reactive

An app registers only synchronous `BeforeSaveCallback<CatalogProduct>`, then calls `ReactiveMongoTemplate.save`. Will the sync callback run automatically?

**Answer:** No. Register **`ReactiveBeforeSaveCallback<CatalogProduct>`** to apply the same logic on the reactive mapping path.

### Exercise 18: Publisher Lifecycle

Inside ReactiveBeforeSaveCallback, a developer manually calls `subscribe()` to perform an extra update and returns `Mono.just(entity)`. What is wrong?

**Answer:** It spawns an uncoordinated side subscription, risking races, lost errors, and cancellations detached from the save pipeline. Never orchestrate uncontrolled I/O inside callbacks.

### Exercise 19: Performance

Every BeforeSaveCallback calls an HTTP API to fetch category names. When writing 2,000 products, what are the risks?

**Answer:** Hidden I/O, high latency, extra failure points, and transaction complications. Prepare data in the service or a denormalized read model; keep callbacks to brief BSON adjustments.

### Exercise 20: Proper Testing

A unit test calls the callback directly and sees Document modified. Is that enough to conclude MongoDB persists the right BSON keys?

**Answer:** No. You need an integration test invoking `MongoTemplate.insert/save`, then reading the **raw Document** from the collection and asserting actual fields.

### Exercise 21: Search Metadata

A product is updated via both `repository.save` and `MongoTemplate.updateFirst`. To keep `search_display` always matching `display_name`, propose a design.

**Answer:** Share one normalization function; BeforeSaveCallback maintains the field on entity insert/save, while the update path sets both `displayName` and `search_display` (or uses an appropriate pipeline update). Write tests for both paths.

### Exercise 22: Security Boundary

A callback strips `raw_access_token` from Document. Is that enough to guarantee no writer ever stores that field?

**Answer:** No. Writers using the raw driver or external tools bypass callbacks. Separate secrets from the persistence model, enforce policies, validation/permissions, and migrate legacy data.

## 30. Production Checklist Before Using BeforeSaveCallback

- **Purpose:** Do you truly need to change Document after conversion, or should you use BeforeConvert?
- **Signature:** Are you using `BeforeSaveCallback<T>` with `org.bson.Document` properly?
- **Timing:** Do you understand Document is already converted and mutating persistent entity properties is too late?
- **Mapping:** Have you verified `@Field`/`@Id`/custom converters and actual BSON names?
- **Nested:** Do you check actual Document/List types before mutating?
- **Null/type:** Does the callback safely handle missing, null, or unexpected BSON types?
- **_id:** Do you avoid arbitrarily changing mapped IDs?
- **_class:** Do you preserve type hints unless mapping configuration intentionally disables them?
- **@Version:** Do you avoid overwriting Spring Data-managed versions?
- **Auditing:** Do you avoid duplicating logic with BeforeConvert/auditing?
- **Scope:** Are the generic entity type and collection guard scoped accurately?
- **Ordering:** Do multiple callbacks in the same phase have explicit `@Order`?
- **AppEvent:** Do you avoid relying on async BeforeSaveEvent listeners for pre-write mutations?
- **Insert/save:** Have all entity write paths needing the callback been tested?
- **Updates:** Is there a strategy for `updateFirst`/findAndModify/bulk/raw driver paths?
- **Derived fields:** Are search/metadata fields protected from going stale?
- **Idempotency:** Is the callback deterministic and free of retry side effects?
- **Transactions:** Have you ensured no pre-commit HTTP/message/email calls happen in callbacks?
- **Security:** Have you ensured callbacks do not replace validation, authorization, or unique indexes?
- **Sensitive data:** Do raw BSON/logs exclude forbidden secrets and PII?
- **Performance:** Is the callback free of blocking I/O, N+1 DB queries, and heavy CPU work?
- **Reactive:** Did you implement `ReactiveBeforeSaveCallback` when using ReactiveMongoTemplate?
- **Testing:** Do you have both mutation unit tests and raw-BSON integration readback tests?
- **Boundary testing:** Did you test alternate collections, missing fields, and immutable entities?
- **Regression:** Do tests catch `@Field`/custom converter changes that alter BSON keys?
- **Operations:** Are metadata, indexes, and schema migrations aligned with the callback?

## 31. Summary

1. **BeforeSaveCallback** receives **the Java entity, the converted `org.bson.Document`, and the collection name**, and runs prior to writing through the entity mapping lifecycle.
2. **Only mutating Document directly affects the persisted BSON**. Changing persistent fields on the entity during BeforeSave does not automatically re-run conversion.
3. **BeforeConvertCallback** is the right choice for changing persistent entities prior to mapping; for immutable records, return a new instance.
4. **@Field/@Id/custom converters** determine the BSON keys visible to the callback; Java property names are not always the keys in Document.
5. Callbacks can add **search_display, write_schema**, or tweak nested BSON, but require clear schema contracts and raw BSON tests.
6. **BeforeSaveCallback does not replace @Id, @Version, auditing, or converters**; never arbitrarily alter framework-managed fields.
7. **EntityCallbacks differ from ApplicationEvents**: callbacks offer explicit ordering in the mapping pipeline, whereas event multicasters may run asynchronously.
8. **@Order** orders callbacks within the same phase; it never makes BeforeSave run before BeforeConvert.
9. **insert/save(entity)** and **query-based updateFirst/findAndModify/bulk/raw-driver writes** do not share the same lifecycle callbacks; derived fields must be maintained across all write paths.
10. **Transactions do not turn callbacks into after-commit hooks**; external side effects in callbacks do not roll back, and callbacks may re-run on retries.
11. **ReactiveBeforeSaveCallback** returns `Publisher<T>` and applies to reactive mapping; sync callbacks do not substitute for it.
12. **Schema validation, unique indexes, and authorization** remain necessary to protect data across all writers, as callbacks do not execute on every MongoDB command.
13. **Unit tests** verify Document-mutation logic, while **MongoDB integration tests** verify mapping and persisted BSON.
14. **Reading back both raw Document and the mapped entity after saving** is the best way to catch mismatches between modified Documents and returned Java objects.

Understanding **BeforeSaveCallback with the Converted Entity and Document** helps **SPRING_DATA_MONGODB** applications choose the right lifecycle hook, enrich or adjust BSON safely, and avoid silent data bugs across entity conversion, repository/MongoTemplate operations, and reactive access.

### References

- [Spring Data MongoDB — BeforeSaveCallback API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html) — `onBeforeSave` signature and post-conversion Document rules.
- [Spring Data MongoDB — ReactiveBeforeSaveCallback API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/ReactiveBeforeSaveCallback.html) — `Publisher<T>`, Document, and collection for reactive flows.
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html) — EntityCallbacks, mapping events, auditing, and lifecycle ordering.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — `@Document`, `@Field`, `@Id`, custom conversions.
- [Spring Data MongoDB — MongoTemplate CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — `insert/save/updateFirst/findAndModify` and auditing/versioning.
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — transactions, ClientSession, and reactive transaction manager.
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — database-level structural protection.
