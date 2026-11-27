# Mapping Fields, Constructors, and Nested Data

## 1. The Mapping Problem in Spring Data MongoDB

In the **Basic Mapping** chapter of **Spring Data MongoDB**, we need to understand how a Java object is converted into a BSON document in MongoDB and then reconstructed back into a Java object when read. This is the foundation for working with data via `MongoTemplate` and `MongoRepository` while keeping a clean domain model.

For example, a customer management application has a Java class containing `displayName`, `address`, and `contacts`. In the collection, the development team wants to store the customer's name under the `display_name` key, the address as a nested subdocument, and the contact list as an array of documents. To get this right, three questions must be answered:

1. **Field mapping:** do Java property names and BSON field names correspond directly, or do they need to be specified with annotations?
2. **Constructor mapping:** which constructor does Spring Data use to recreate the object, especially with immutable classes or Java records?
3. **Nested mapping:** how are objects, lists, and maps stored; how does this differ from referencing another collection?

Spring Data uses entity mapping metadata and `MappingMongoConverter` to answer these questions. The mapping mechanism does not replace data modeling, indexing, query design, or consistency policies; it defines the **shape of data exchanged between Java and MongoDB**.

> Examples focus on Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x, with the MongoDB Java Sync Driver at the connection layer. Check the corresponding APIs and configuration if your project uses a different major version.

## 2. Default Mapping Conventions

Suppose we have a simple entity:

~~~java
package com.example.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class SimpleCustomer {
    @Id
    private String id;
    private String displayName;
    private int loyaltyPoints;

    public SimpleCustomer() {}

    // Appropriate getters/setters or property accessors are defined as needed.
}
~~~

When Spring Data writes this entity, by default:

- `@Document(collection = "customers")` identifies the collection for storing the entity. The annotation does not automatically mean the collection and indexes already exist.
- The property annotated with `@Id` is mapped to the BSON `_id` field. With a `String` ID, Spring Data can convert strings representing a valid ObjectId into a BSON `ObjectId`; do not assume every String ID is stored as a BSON String.
- `displayName` and `loyaltyPoints` are stored under their corresponding property names unless annotations or mapping configuration change this.
- Primitive types and common types are converted to appropriate BSON types; if there are explicit BSON type requirements, conversion rules must be defined.
- Type metadata `_class` may be stored by default to assist in reading back the object type, especially in graphs with multiple types. Document examples below may omit `_class` to focus on fields.

These rules are enforced when operating **through Spring Data mapping**, such as `MongoTemplate.save(entity)` or `MongoRepository.save(entity)`. When working directly with the driver's `MongoCollection<Document>`, the application must use exact BSON field names and handle necessary conversions itself.

### Basic Annotations

| Annotation | Meaning | Practical Notes |
|---|---|---|
| `@Document(collection = "...")` | Declares an entity bound to a collection | May not be needed for embedded objects; does not automatically create indexes |
| `@Id` | Marks the identifier property, mapped to `_id` | With String IDs, watch out for conversion to BSON ObjectId |
| `@MongoId` | Controls ID mapping with the desired BSON type | Use when explicit control over `_id` type is needed instead of `@Id` conversion behavior |
| `@Field(name = "...")` | Sets a BSON field name different from the Java property name | Queries using Java properties through Spring Data mapping can be translated to the actual stored name |
| `@Field(targetType = ...)` | Specifies the target BSON type for a property | Useful for types like `BigDecimal` that should be stored as Decimal128 |
| `@Transient` | Does not store the property in the document | Do not use as a required parameter of a persistence constructor because no data exists to restore it |
| `@PersistenceCreator` | Explicitly marks the constructor/factory used when restoring an entity | Useful when a class has multiple constructors; parameter names must be properly resolvable |

In Java, annotations are typically placed on fields or record components depending on framework and version support. Within a single entity, pick a consistent style so readers know which property serves as the mapping source.

## 3. Renaming Fields with @Field

Suppose the Java model uses camelCase naming while the collection standardizes on snake_case field names:

~~~java
package com.example.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "profiles")
public record Profile(
        @Id String id,
        @Field(name = "display_name") String displayName,
        @Field(name = "phone_number") String phoneNumber) {
}
~~~

With `Profile("p-101", "Lan", "0900000000")`, the BSON data might look like this (omitting `_class` metadata):

~~~json
{
  "_id": "p-101",
  "display_name": "Lan",
  "phone_number": "0900000000"
}
~~~

Important:

- When writing Java code and working with the entity, the properties remain `displayName` and `phoneNumber`.
- In direct MongoDB queries, the actual field names are `display_name` and `phone_number`.
- Do not rename Java properties solely to match BSON names when `@Field` already expresses the storage convention.
- Changing an annotation from `@Field("display_name")` to `@Field("name")` **does not automatically rename existing data**. That is a storage schema change; it requires a migration/backfill plan and an audit of code reading the old field.

Query example using `MongoTemplate`, where Spring Data knows the target entity:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Profile findByDisplayName(MongoTemplate template, String displayName) {
    Query query = Query.query(Criteria.where("displayName").is(displayName));
    return template.findOne(query, Profile.class);
}
~~~

With `Profile.class`, Spring Data maps the `displayName` property to the `display_name` BSON field. This is why entity-aware access paths should be preferred when building queries with `MongoTemplate`.

Conversely, MongoDB shell commands use BSON names:

~~~javascript
db.profiles.find({ display_name: "Lan" });
~~~

If using raw BSON APIs or aggregation stages constructed directly as unmapped documents, check how Spring Data handles each API; do not assume all field-name strings are automatically translated.

## 4. Mapping Nested Data: Documents, Lists, and Maps

MongoDB stores data in document structures, allowing a field to contain an object, an array of objects, or a map. Spring Data MongoDB normally maps nested value-type objects directly when they are properties of an entity.

Let's build a complete example consisting of three Java records in package `com.example.mongo`.

**Address.java**

~~~java
package com.example.mongo;

import org.springframework.data.mongodb.core.mapping.Field;

public record Address(
        String street,
        String city,
        @Field(name = "postal_code") String postalCode) {
}
~~~

**ContactPoint.java**

~~~java
package com.example.mongo;

public record ContactPoint(
        String kind,
        String value) {
}
~~~

**Customer.java**

~~~java
package com.example.mongo;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "customers")
public record Customer(
        @Id String id,
        @Field(name = "display_name") String displayName,
        Address address,
        List<ContactPoint> contacts,
        Map<String, String> attributes,
        Instant createdAt) {
}
~~~

An example object:

~~~java
Customer customer = new Customer(
        "c-101",
        "Lan",
        new Address("12 Example Street", "Hanoi", "100000"),
        List.of(
                new ContactPoint("email", "lan@example.test"),
                new ContactPoint("phone", "0900000000")),
        Map.of("tier", "gold", "preferredLanguage", "vi"),
        Instant.parse("2026-11-20T08:00:00Z"));

mongoTemplate.save(customer);
~~~

The snippet above sits inside a service class with `MongoTemplate mongoTemplate` injected; the records are declared in the same package. The stored document takes a form like this (timestamps shown in MongoDB Extended JSON; `_class` omitted):

~~~json
{
  "_id": "c-101",
  "display_name": "Lan",
  "address": {
    "street": "12 Example Street",
    "city": "Hanoi",
    "postal_code": "100000"
  },
  "contacts": [
    { "kind": "email", "value": "lan@example.test" },
    { "kind": "phone", "value": "0900000000" }
  ],
  "attributes": {
    "tier": "gold",
    "preferredLanguage": "vi"
  },
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Because `Address` and `ContactPoint` are **objects nested inside the customer document**, they do not need their own `@Document`. When saving `Customer`, Spring Data can serialize the entire object graph; when reading, it reconstructs the nested records via their constructors.

### 4.1. Nested Objects and Field Paths

The MongoDB path `address.city` accesses the `city` field of the `address` subdocument; `address.postal_code` accesses the field renamed via `@Field`.

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Customer> findByCity(MongoTemplate mongo, String city) {
    Query query = Query.query(Criteria.where("address.city").is(city));
    return mongo.find(query, Customer.class);
}

public List<Customer> findByPostalCode(MongoTemplate mongo, String postalCode) {
    Query query = Query.query(
            Criteria.where("address.postalCode").is(postalCode));
    return mongo.find(query, Customer.class);
}
~~~

The path `address.postalCode` is a **Java property path**. When using typed operations with `Customer.class`, Spring Data applies nested property mapping to build a query on `address.postal_code`. If querying with raw `Document` via the driver, you must use `address.postal_code` directly.

### 4.2. Lists and Arrays

`List<ContactPoint>` is stored as a BSON array. You can find customers that have at least one element matching a condition:

~~~java
Query query = Query.query(
        Criteria.where("contacts")
                .elemMatch(Criteria.where("kind").is("email")));

List<Customer> customers = mongoTemplate.find(query, Customer.class);
~~~

When multiple conditions must match **the same array element**, use `$elemMatch` instead of loosely combining multiple dot paths; otherwise, conditions can match different elements within the same array.

For arrays that grow over time or have an independent lifecycle, consider splitting into another collection and storing references. Embedding objects allows single-document reads, but MongoDB has a **16 MiB** BSON size limit per document; unbounded array growth is a signal to revisit the design.

### 4.3. Maps

`Map<String, String> attributes` is stored as a document with dynamic keys, such as `"tier"` and `"preferredLanguage"`. This model suits a small, flexible set of attribute names.

Do not use arbitrary map keys from user input as update paths without validation: special characters like dots (`.`), `$` signs, and field naming rules can affect querying, updating, indexing, or import/export depending on MongoDB version and mapping setup. For frequently queried fields, consider fixed-property models or an explicit key/value structure.

### 4.4. Embedding or Referencing?

An `Address` property in the example above is stored **embedded**. It does not automatically become a reference just because that type might also appear in another entity.

- **Embedding:** the object resides inside the parent document; fits small data commonly read together with a shared lifecycle.
- **ID referencing:** the parent document stores a key pointing to a document in another collection; the application runs separate queries or aggregations to fetch related parts.
- **`@DBRef` or `@DocumentReference`:** Spring Data reference mechanisms with distinct storage formats and resolution behavior; must be intentionally chosen with a clear understanding of loading behavior.

Choose the model based on query patterns, document size, update frequency, and consistency requirements. Mapping annotations help translate the chosen structure; they do not automatically decide how data relationships should be designed.

## 5. Constructor Mapping: How Does Spring Data Instantiate Objects on Read?

When a document is read, `MappingMongoConverter` must create an appropriate Java object and populate its property values. For mutable classes with a no-arg constructor and setters/field access, this process is relatively straightforward. For immutable classes or records, the **constructor becomes a critical state restoration point**.

### 5.1. Java Records: Canonical Constructor

In the `Customer` record example, when reading, Spring Data can use the record's **canonical constructor** with parameters `id`, `displayName`, `address`, `contacts`, `attributes`, and `createdAt`. The value of `display_name` in BSON is passed into parameter **`displayName`**, because `@Field` metadata links the stored name with the Java property name.

Advantages:

- No setters are needed for entities represented as records.
- Record components clearly describe the state of the document.
- Immutable nested types can be placed inside the record and the entire graph restored.

Limitations:

- If legacy schemas are missing a required field, the constructor may receive `null` or fail object creation when non-null constraints exist.
- When changing data types or renaming fields without a migration, reconstruction can fail.
- Immutable records must be carefully designed for database-generated IDs, framework-updated fields, and the save lifecycle; verify supported copy/ID-initialization mechanisms.

To keep the example simple, we **provide an explicit ID** (`c-101`), avoiding dependence on how the framework assigns auto-generated IDs to immutable types.

### 5.2. Classes with Multiple Constructors: @PersistenceCreator

When a class has multiple constructors, you can designate which constructor to use on read with `@PersistenceCreator`:

~~~java
package com.example.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "catalog_items")
public final class CatalogItem {
    @Id
    private final String id;
    @Field(name = "display_title")
    private final String title;
    private final String category;

    @PersistenceCreator
    public CatalogItem(String id, String title, String category) {
        this.id = id;
        this.title = title;
        this.category = category;
    }

    // Convenience constructor when ID and title are explicitly known.
    public CatalogItem(String id, String title) {
        this(id, title, "general");
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getCategory() { return category; }
}
~~~

Given document:

~~~json
{
  "_id": "item-101",
  "display_title": "Notebook",
  "category": "stationery"
}
~~~

Spring Data invokes the annotated constructor, passing the corresponding values to parameters `id`, `title`, and `category`. **Constructor parameter names match Java property names**, meaning `title` rather than `display_title`.

Constructor notes:

1. When only one suitable constructor exists, the framework can usually identify it automatically. With multiple constructors, `@PersistenceCreator` removes ambiguity.
2. Spring Data needs to know constructor parameter names, such as through parameter-name metadata when compiled with the `-parameters` flag, or supported annotation/metadata mechanisms. If parameter names are missing on a regular class, mapping can fail.
3. Constructor parameters must correspond to properties that can be materialized from the document. Do not use a `@Transient` property as a required persistence constructor parameter.
4. Constructors with validation or side effects must account for historical data. A strict new rule can make old documents unreadable.

**Do not declare a constructor just to satisfy the mapping mechanism and then place heavy business logic inside it**. Constructors should build a valid object from stored state; side effects such as service calls, network requests, or event publishing do not belong there.

### 5.3. Missing Fields, Nulls, and Default Values

When MongoDB holds documents created by multiple application versions, a property may:

- **Be absent** in older documents.
- **Exist with BSON null**.
- **Exist with a different data type** due to schema changes.

These cases affect constructors differently depending on property types, converters, and default handling. For instance, an optional `Integer` can accept `null`, whereas primitive `int` cannot represent null. A constructor asserting `Objects.requireNonNull` can throw an error when reading old documents missing that field.

A safe policy distinguishes:

- **New required fields:** write a migration/backfill before or alongside deploying mandatory-read logic.
- **Optional fields:** use nullable types and handle defaults explicitly in the domain/adapter layer.
- **Renamed fields:** establish a compatibility window reading both names, migrate data, and retire the old name in a planned way.
- **Changed BSON types:** inspect actual data and converters; do not assume the framework will infer every conversion.

Do not rely on Java field default initializers as an automatic migration mechanism, especially with immutable entities instantiated via constructors.

## 6. Controlling BSON Types and Conversions

Field names are only half the mapping problem. Actual data types in MongoDB affect comparisons, indexes, aggregations, and compatibility.

### 6.1. String IDs and ObjectIds

`@Id String id` has special conversion behavior for strings shaped like valid ObjectIds. If the application genuinely needs `_id` to be a **BSON String** regardless of content, you can use `@MongoId(FieldType.STRING)` per Spring Data's supported API:

~~~java
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

public record ExternalKey(
        @MongoId(FieldType.STRING) String id,
        String label) {
}
~~~

This record example only illustrates ID mapping; if used as an aggregate root, add `@Document` and the appropriate collection. When working with raw BSON driver commands, always verify the actual `_id` type: querying `eq("_id", "507f...")` with a BSON String differs from `eq("_id", new ObjectId("507f..."))`.

### 6.2. BigDecimal and Decimal128

Monetary prices require decimal precision. You can specify storing `BigDecimal` in BSON Decimal128 format:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public record Price(
        @Field(targetType = FieldType.DECIMAL128) BigDecimal amount,
        String currency) {
}
~~~

This example represents **a price object embedded inside a parent document**. If there are rounding rules, scale, currency, or precision limits, handle them explicitly in the business layer. BSON Decimal128 has its own representation limits; not every arbitrary `BigDecimal` can be represented intact.

### 6.3. Instant, Enums, and Converters

- `Instant` is usually stored as BSON Date/UTC according to supported conversions. BSON Date has **millisecond** precision, so do not expect lossless nanosecond round-trips.
- Enums are normally stored as string names under default mapping; renaming enum constants can make legacy data unreadable without a compatibility policy.
- Specialized domain types may need `@ReadingConverter`, `@WritingConverter`, and registering `MongoCustomConversions`. Converters must be consistent across both write and read paths, especially when queries and aggregations are involved.

Data-type decisions should be verified on **actual BSON documents**, since numeric and date comparisons in MongoDB depend on the stored type.

## 7. Querying and Updating Nested Fields with MongoTemplate

With the `Customer` entity from section 4, both queries and updates can use Java property paths:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class CustomerDataAccess {
    private final MongoTemplate mongo;

    public CustomerDataAccess(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<Customer> byPostalCode(String postalCode) {
        Query query = Query.query(
                Criteria.where("address.postalCode").is(postalCode));
        return mongo.find(query, Customer.class);
    }

    public boolean changeCity(String customerId, String newCity) {
        Query byId = Query.query(Criteria.where("id").is(customerId));
        Update update = new Update().set("address.city", newCity);
        return mongo.updateFirst(byId, update, Customer.class)
                .getModifiedCount() == 1;
    }
}
~~~

Points to note:

- `Criteria.where("id")` is mapped to `_id` of the target entity.
- `address.postalCode` is a Java property name, translated by Spring Data into field `address.postal_code` when creating typed queries.
- `updateFirst` updates **one matching document** without reloading the whole object. The code changes only the `address.city` field.
- `getModifiedCount() == 0` can mean either no document was found or the document already held the desired value; do not assume "does not exist" solely from that number.
- For updating multiple elements in an array, understand `$`, `$[]`, `$[identifier]`, and array filters; do not use simple nested-path syntax as a substitute for complex array-update logic.

If the application uses **immutable records**, `MongoTemplate.updateFirst` still modifies the document in the database, but **does not mutate already-loaded record objects in memory**. To obtain a fresh snapshot, reload the document or work with the result of an appropriate operation. This is not an identity map mechanism like some relational ORMs.

## 8. Common Mapping Errors

| Symptom | Possible Cause | How to Verify or Fix |
|---|---|---|
Java field has a value, but BSON stores it under another name | `@Field`, naming strategy, or converter | Read raw BSON and cross-check mapping metadata
Raw BSON query finds no data | Using Java property name instead of BSON name | Check physical field name, e.g., `display_name`
Reading immutable class fails at constructor | Multiple constructors, missing `@PersistenceCreator`, or missing parameter-name metadata | Check annotations, `-parameters` compiler flag, and conversion logs
Old record fails to read after adding a required field | Missing/null field fails constructor validation | Design compatibility or migration/backfill
`_id` lookup mismatches | One side uses BSON String, the other uses ObjectId | Inspect actual type and enforce consistent `@Id`/`@MongoId`
Nested data reads incorrectly | Field path or sub-class type changed | Inspect stored document and nested property mapping
Saves fine, but slow or document is huge | Too many embedded arrays/objects or poor index design | Measure document size, explain queries, and consider splitting collections
Monetary values have wrong type in queries/aggregations | Inconsistent `BigDecimal` vs. Decimal128/String | Specify `targetType`, migrate, and test BSON data
Entity changed in Java, but document unchanged | Only mutated Java object in memory without saving | Call appropriate save/update operation and verify result
Raw driver write bypasses callbacks/converters | Direct driver path skips Spring Data mapping | Keep access paths unified or explicitly convert in an adapter

## 9. Testing Mapping with a Real MongoDB

Unit tests that merely invoke Java constructors **do not prove** Spring Data writes the right field names and BSON types. Use integration tests against a real MongoDB, such as Testcontainers or a dedicated test MongoDB instance.

With Spring Boot 3.x, `@DataMongoTest` focuses on Spring Data MongoDB infrastructure. The test below uses `MongoTemplate` and reads back **raw BSON** to reveal the difference between property names and stored field names.

~~~java
package com.example.mongo;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class CustomerMappingTest {
    @Autowired
    MongoTemplate mongo;

    @Test
    void mapsFieldNamesAndNestedRecords() {
        Customer expected = new Customer(
                "c-101",
                "Lan",
                new Address("12 Example Street", "Hanoi", "100000"),
                List.of(new ContactPoint("email", "lan@example.test")),
                Map.of("tier", "gold"),
                Instant.parse("2026-11-20T08:00:00Z"));

        mongo.save(expected);

        Document bson = mongo.getCollection("customers")
                .find(eq("_id", "c-101"))
                .first();

        assertThat(bson).isNotNull();
        assertThat(bson.getString("display_name")).isEqualTo("Lan");
        assertThat(bson.get("displayName")).isNull();
        assertThat(bson.get("address", Document.class)
                .getString("postal_code")).isEqualTo("100000");

        Customer restored = mongo.findById("c-101", Customer.class);
        assertThat(restored).isEqualTo(expected);
    }
}
~~~

This test requires a MongoDB database available at the configured URI. `@DataMongoTest` **does not start a MongoDB server by itself**. Testcontainers can provide an ephemeral MongoDB and dynamic URI; configure it appropriately for your Spring Boot/Testcontainers version. To avoid ID collisions between tests, use isolated collections/databases or clean up test data reliably.

Additional tests should cover:

1. **Field names:** saving, reading, querying, and updating `displayName`/`display_name` as well as `address.postalCode`/`postal_code`.
2. **Constructors:** restoring a class with multiple constructors and `@PersistenceCreator` from a real document.
3. **Nested arrays:** verifying `$elemMatch` when two array elements have different attributes.
4. **Backward compatibility:** reading documents missing fields, with null fields, or old BSON types; verifying expected errors.
5. **BSON types:** verifying String/ObjectId `_id` matches design, Decimal128, and timestamp precision.
6. **Update operations:** ensuring only intended fields change and previously read objects do not auto-update in memory.

## 10. Practice Exercises

**Exercise 1 — Field renaming.** Create `@Document(collection = "products")` with properties `productName` and `listedPrice`, stored in BSON under `product_name` and `listed_price`. Write a `MongoTemplate` query using Java property names, then inspect raw BSON to prove the physical stored names.

**Exercise 2 — Immutable constructor.** Create a `PurchaseOrder` class with two constructors; mark one with `@PersistenceCreator` and use at least one `@Field(name = "...")`. Write a document and read it back to confirm Spring Data restores the object properly. Try stripping parameter-name metadata in a test setup to observe the error and explain the cause.

**Exercise 3 — Nested documents.** Design `Delivery` containing `recipient`, `address`, and a `packages` array. Query by `address.postalCode`, find documents containing a package with `weightGrams >= 1000` using `$elemMatch`, and then update the city without replacing the entire document.

**Exercise 4 — Historical data.** Add a new property to a record when the collection already holds older data. Propose a default/migration mechanism so both old and new documents can be read while keeping business constraints in the right layer.

**Exercise 5 — Data types.** Save two documents whose `_id` values are 24-character hex strings, using `@Id` and `@MongoId(FieldType.STRING)` respectively. Inspect the raw BSON and explain why direct queries with `String` and `ObjectId` can return different results.

## 11. Takeaways

In **Spring Data MongoDB**, mapping is the contract between **Java properties** and **BSON fields**. `@Document` identifies the entity/collection; `@Id` or `@MongoId` defines how the key is stored; `@Field` renames fields or specifies BSON types; `@PersistenceCreator` and record canonical constructors support restoring immutable objects.

Nested objects, lists, and maps can be stored in the same document when the data model fits, while references must be designed deliberately. When building queries with `MongoTemplate` using an entity type, prefer Java property paths so the framework applies mapping. For raw MongoDB commands, use the actual BSON field names.

Always **read back raw BSON in integration tests**, test constructors against missing/null data, watch `_id`, numeric, and date types, and plan migrations when renaming fields or changing field types. Those steps ensure that queries, aggregations, indexes, and repository operations in subsequent lessons operate on consistently structured data.
