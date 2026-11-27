# Document Mapping, POJO Codecs, and Field Naming Conventions in the MongoDB Java Driver

## Lesson Objectives

When working with MongoDB using the **Java Sync Driver**, an application must convert back and forth between **BSON** (the document format stored in MongoDB) and data structures Java understands. Two common representations are:

- **`Document`**: a flexible map-like structure suited for dynamic queries, reading unknown schemas, prototyping, and working with fields that vary per record.
- **POJO (Plain Old Java Object)**: a strongly typed Java class suited for domain models, compile-time checks, and stable business APIs.

To read and write POJOs, the Java Driver needs an appropriate **codec**. `CodecRegistry` looks up the codec for each type, while `PojoCodecProvider` generates codecs from class metadata, conventions, getters/setters, and annotations such as `@BsonId`, `@BsonProperty`, `@BsonIgnore`, and `@BsonCreator`.

A common pitfall is that **Java property names do not automatically match BSON field names in the database**. For example, `customerName` might be stored under the key `customer_name`, and when writing string-based `Filters.eq(...)` or `Updates.set(...)`, you must use the **BSON field name**, not the Java property name.

This lesson belongs to **Database Engine Document MongoDB → Java Driver → Document Mapping, POJO Codecs, and Field Naming Conventions**.

After this lesson, you will be able to:

1. Explain the conversion pipeline `Java object ↔ Codec ↔ BSON ↔ MongoDB`.
2. Use `Document` to create, read, update, and traverse nested documents.
3. Distinguish `Document`, `BsonDocument`, POJOs, Java records, and DTOs.
4. Configure `PojoCodecProvider` alongside the **default codec registry** for `MongoCollection<YourPojo>`.
5. Use annotations to map `_id` and custom BSON field names.
6. Understand JavaBean conventions, constructors, getters/setters, private fields, and `@BsonCreator`.
7. Design consistent `camelCase`/`snake_case` conventions across POJOs, queries, indexes, and JSON APIs.
8. Handle BSON `ObjectId`, integers, `Decimal128`, dates/times, UUIDs, enums, nested arrays, and maps.
9. Recognize the difference between **missing**, **null**, and **default value** fields.
10. Protect data during field renames, schema evolution, adding/removing properties, and replace updates.
11. Debug `CodecConfigurationException`, codec registry ordering, naming mismatches, and legacy data issues.
12. Write round-trip integration tests that verify the actual persisted data, not just the Java-side POJO.

> **Important rule:** A POJO is a **representation**, not an absolute schema enforced automatically by MongoDB. If a collection holds inconsistent data or a query uses the wrong BSON field name, mapping can fail or return unexpected results.

---

## 1. From Java to MongoDB: The Data Path

Suppose Java has an object:

~~~java
Customer customer = new Customer();
customer.setFullName("Nguyen An");
customer.setLoyaltyPoints(120);
~~~

MongoDB may store the corresponding document:

~~~javascript
{
  _id: ObjectId("6914bb000000000000000001"),
  full_name: "Nguyen An",
  loyalty_points: 120
}
~~~

The path:

~~~text
  Java code
      |
      v
  Customer POJO
      |
      v
  CodecRegistry -> Codec<Customer>
      |
      v
  BSON encoding
      |
      v
  MongoDB: _id, full_name, loyalty_points

  MongoDB BSON
      |
      v
  BSON decoding + Codec<Customer>
      |
      v
  Customer POJO
~~~

### 1.1. Encoding and Decoding

- **Encoding/serialization**: converting a Java object into BSON to send via the driver or store in the database.
- **Decoding/deserialization**: reading BSON and reconstructing the Java object.
- **Round-trip**: encoding then decoding and verifying that the object/result matches the contract.

### 1.2. What Is a Codec?

`Codec<T>` defines how to convert between BSON and Java type `T`. The driver provides codecs for built-in types such as `String`, `Integer`, `Date`, `ObjectId`, `Document`, `List`, and supported BSON types.

A domain POJO `Customer` does not automatically have a codec merely by existing in the project. You must register `PojoCodecProvider`, configure the model, or supply an appropriate custom codec.

### 1.3. How Does `CodecRegistry` Work?

A registry is a collection of codecs/providers; when the driver needs a codec for `Customer.class`, it searches registered registries/providers in order. If no matching codec is found, you get:

~~~text
org.bson.codecs.configuration.CodecConfigurationException:
Can't find a codec for CodecCacheKey{clazz=...}
~~~

Registration order matters because the first matching codec or provider wins.

---

## 2. Using `Document` Before POJOs

`org.bson.Document` is a key-value document type capable of holding numbers, strings, dates, nested documents, lists, and supported BSON values.

### 2.1. Creating a Document in Java

~~~java
import org.bson.Document;
import org.bson.types.ObjectId;

Document customer = new Document()
    .append("_id", new ObjectId())
    .append("full_name", "Nguyen An")
    .append("loyalty_points", 120)
    .append("active", true);

System.out.println(customer.toJson());
~~~

In MongoDB, the actual keys are `_id`, `full_name`, `loyalty_points`, and `active`.

### 2.2. Creating a `Document`-Typed Collection

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

String uri = System.getenv("MONGODB_URI");

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase db =
        client.getDatabase("java_codec_lab");

    MongoCollection<Document> collection =
        db.getCollection("customers");

    Document customer = new Document()
        .append("full_name", "Nguyen An")
        .append("loyalty_points", 120);

    collection.insertOne(customer);

    System.out.println(customer.get("_id"));
}
~~~

This snippet requires a running MongoDB instance and a valid `MONGODB_URI` environment variable. Run it against a lab database; never write test data to production.

### 2.3. Reading a Document

~~~java
Document found = collection.find(
    new Document("full_name", "Nguyen An")
).first();

if (found != null) {
    String name = found.getString("full_name");
    Integer points = found.getInteger("loyalty_points");

    System.out.println(name);
    System.out.println(points);
}
~~~

Typed getters like `getString` and `getInteger` require the decoded value to match a compatible Java type. They do not automatically coerce `Long` into `Integer`.

### 2.4. Nested Documents

~~~java
Document shippingAddress = new Document()
    .append("city", "Ho Chi Minh City")
    .append("district", "Binh Thanh");

Document order = new Document()
    .append("tenant_id", "tenant-a")
    .append("order_code", "ORD-101")
    .append("shipping_address", shippingAddress)
    .append("status", "PAID");
~~~

Reading nested fields:

~~~java
Document address =
    order.get("shipping_address", Document.class);

String city =
    address == null ? null : address.getString("city");
~~~

### 2.5. Arrays

~~~java
import java.util.List;

Document order = new Document()
    .append("order_code", "ORD-102")
    .append("tags", List.of("express", "gift"))
    .append(
        "items",
        List.of(
            new Document("sku", "SKU-1")
                .append("qty", 2),
            new Document("sku", "SKU-2")
                .append("qty", 1)
        )
    );
~~~

When reading `items`, validate the actual element types. `Document` is flexible, but provides no compile-time schema safety.

---

## 3. How Do `Document`, `BsonDocument`, `Bson`, and POJOs Differ?

| Type | Characteristics | When to Use |
|---|---|---|
| `Document` | Key-value map with Java object values | Dynamic schemas, raw projections, tooling |
| `BsonDocument` | Map with explicit `BsonValue` types | When exact BSON types must be inspected |
| `RawBsonDocument` | Holds raw BSON bytes for specialized handling | Raw data processing and specific performance cases |
| `Bson` | Interface representing BSON filters/updates/stages | `Filters`, `Updates`, aggregations |
| POJO | Typed Java class mapped by codecs | Domain models/CRUD with relatively stable schemas |
| Java record | Immutable carrier per Java record contract | Read models/immutable data when driver supports it |

### 3.1. `Document` Is Not JSON

`Document` is a Java object. `toJson()` serializes it to a JSON/Extended JSON string for display, whereas MongoDB stores binary BSON.

~~~java
Document doc = new Document(
    "_id",
    new ObjectId()
);

String json = doc.toJson();
~~~

`json` is merely a text representation; never treat that JSON string as MongoDB's storage format.

### 3.2. `BsonDocument` When Distinguishing Numeric Types

~~~java
import org.bson.BsonDocument;

BsonDocument raw = new BsonDocument()
    .append("quantity", new org.bson.BsonInt32(3))
    .append("total", new org.bson.BsonInt64(3000000000L))
    .append("name", new org.bson.BsonString("Pen"));

System.out.println(raw.get("quantity").getBsonType());
System.out.println(raw.get("total").getBsonType());
~~~

When you need to distinguish `INT32` vs. `INT64` or `DECIMAL128`, `BsonDocument` is far clearer than reading JSON text.

### 3.3. `Document.parse` Requires Understanding Extended JSON

~~~java
Document parsed = Document.parse(
    "{\"name\":\"An\",\"score\":10}"
);
~~~

For `ObjectId`, `Date`, `Decimal128`, and `Binary`, use proper Extended JSON syntax to preserve BSON types. Never parse unvalidated client-supplied JSON into unbounded MongoDB update pipelines.

### 3.4. `Document` and POJOs Can Coexist

A single service can use:

- POJOs for the `customers` collection.
- `Document` for aggregation reports with dynamic shapes.
- `BsonDocument` when diagnosing exact BSON payloads.
- Dedicated DTOs for HTTP JSON responses.

There is no rule forcing one representation across an entire project.

---

## 4. Limitations of `Document`: Runtime Type Checking

Suppose a collection contains two documents:

~~~javascript
{ _id: 1, loyalty_points: 120 }
{ _id: 2, loyalty_points: NumberLong("120") }
~~~

When the driver decodes:

~~~java
Document doc = collection.find(
    new Document("_id", 2)
).first();

Integer points =
    doc.getInteger("loyalty_points"); // May fail with a type error.
~~~

The second document's field may decode as `Long` instead of `Integer`.

### 4.1. Never Cast Blindly

~~~java
Object raw = doc.get("loyalty_points");

if (raw instanceof Number value) {
    long points = value.longValue();
    System.out.println(points);
}
~~~

This is valid only when the schema allows numeric types within `long` range. `Number.doubleValue()` or other conversions can silently lose precision.

### 4.2. Missing vs. Null

~~~java
Document a = new Document();
Document b = new Document("loyalty_points", null);

System.out.println(a.containsKey("loyalty_points")); // false
System.out.println(b.containsKey("loyalty_points")); // true
~~~

Both return `null` from `get()`, yet their persisted storage semantics differ.

### 4.3. Field Rename Pitfalls

If a developer changes a Java string constant `"full_name"` to `"fullName"` without migrating existing data, queries will miss older records. This is a classic trap when moving from `Document` to POJOs.

---

## 5. Defining a Clean Java POJO

Suppose we want to map:

~~~javascript
{
  _id: ObjectId("6914cc000000000000000001"),
  full_name: "Nguyen An",
  loyalty_points: 120,
  active: true
}
~~~

to a Java class:

~~~java
package example.model;

import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.codecs.pojo.annotations.BsonProperty;
import org.bson.types.ObjectId;

public class Customer {

    @BsonId
    private ObjectId id;

    @BsonProperty("full_name")
    private String fullName;

    @BsonProperty("loyalty_points")
    private Integer loyaltyPoints;

    private Boolean active;

    // No-arg constructor for POJO codec.
    public Customer() {
    }

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public Integer getLoyaltyPoints() {
        return loyaltyPoints;
    }

    public void setLoyaltyPoints(Integer loyaltyPoints) {
        this.loyaltyPoints = loyaltyPoints;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

### 5.1. Four Explicit Mappings

| Java Property | Annotation | BSON Field |
|---|---|---|
| `id` | `@BsonId` | `_id` |
| `fullName` | `@BsonProperty("full_name")` | `full_name` |
| `loyaltyPoints` | `@BsonProperty("loyalty_points")` | `loyalty_points` |
| `active` | None needed (same name) | `active` |

### 5.2. Why Use Wrapper Types `Integer` and `Boolean`?

Wrapper types can represent **no value present** as `null`. Primitives `int`/`boolean` always initialize to defaults (`0`/`false`), which can mask missing BSON fields.

If business rules guarantee a field is always present, primitives paired with schema validation can work; when reading legacy data, understand the difference.

### 5.3. Getters/Setters Are Part of the POJO Codec Contract

The driver's POJO codec relies on JavaBean-style getters and setters to read and write private properties. Getter/setter names must match the Java property consistently.

Never mix `getFullName()` with a mismatched setter like `setFull_name()` and expect the codec to guess your intent.

---

## 6. Combining `PojoCodecProvider` with `CodecRegistry`

This is the most important setup step when using the Java Sync Driver with POJOs.

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;

import org.bson.codecs.configuration.CodecProvider;
import org.bson.codecs.configuration.CodecRegistry;
import org.bson.codecs.pojo.PojoCodecProvider;

import static org.bson.codecs.configuration
    .CodecRegistries.fromProviders;
import static org.bson.codecs.configuration
    .CodecRegistries.fromRegistries;

String uri = System.getenv("MONGODB_URI");

CodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .automatic(true)
        .build();

CodecRegistry registry = fromRegistries(
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(pojoProvider)
);

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database = client
        .getDatabase("java_codec_lab")
        .withCodecRegistry(registry);

    MongoCollection<Customer> customers =
        database.getCollection("customers", Customer.class);

    // Insert/find operations are now typed with Customer.
}
~~~

### 6.1. Why Keep the Default Registry?

The default registry includes codecs for `String`, numbers, `ObjectId`, `Document`, lists, and many other built-in types. Replacing it solely with `PojoCodecProvider` leaves types like enums or nested standard types without codecs.

### 6.2. `automatic(true)`

`automatic(true)` lets the provider generate codecs on the fly for encountered POJO classes/fields rather than requiring explicit registration of every class.

Convenient while learning, in large systems **explicit registration** of domain classes/packages tightly scopes the model and prevents unintended automatic mapping.

### 6.3. Explicit Registration by Class or Package

~~~java
CodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .register(
            Customer.class,
            Address.class
        )
        .build();
~~~

Or:

~~~java
CodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .register("example.model")
        .build();
~~~

When using explicit registration, ensure all nested POJOs and derived types used by the model are registered as well.

### 6.4. Registries Apply at Multiple Levels

You can attach a registry via:

- `MongoClientSettings.codecRegistry(...)` at the client level.
- `database.withCodecRegistry(...)` at the database level.
- `collection.withCodecRegistry(...)` at the collection level.

Apply it consistently so one collection does not decode POJOs while another fails with a missing codec.

---

## 7. Typed CRUD with `MongoCollection<Customer>`

### 7.1. Insert

~~~java
Customer customer = new Customer();
customer.setFullName("Nguyen An");
customer.setLoyaltyPoints(120);
customer.setActive(true);

customers.insertOne(customer);
~~~

With `@BsonId ObjectId` and the matching generator convention, the codec can generate an `ObjectId` when the ID is null. Always check the ID after insert or read `InsertOneResult.getInsertedId()` per business rules; never assume every ID type auto-generates.

### 7.2. Find

~~~java
import static com.mongodb.client.model.Filters.eq;

Customer found =
    customers.find(
        eq("full_name", "Nguyen An")
    ).first();

if (found != null) {
    System.out.println(found.getFullName());
}
~~~

**Note:** The string `"full_name"` in `Filters.eq` is the persisted **BSON field name**, not the Java property `fullName`.

### 7.3. Update

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

customers.updateOne(
    eq("full_name", "Nguyen An"),
    set("loyalty_points", 130)
);
~~~

`Updates.set` likewise requires the BSON field name `loyalty_points`.

### 7.4. Delete

~~~java
customers.deleteOne(
    eq("_id", found.getId())
);
~~~

### 7.5. Typed Collections Do Not Rewrite Filter Strings

`MongoCollection<Customer>` only sets the document class for encoding/decoding results. It **does not translate** Java property names inside filter strings into their BSON field names.

This is one of the most critical lessons when transitioning from raw `Document` to POJOs.

---

## 8. Java Field Name, BSON Key, and JSON API Name Are Three Separate Layers

An endpoint might accept JSON:

~~~json
{
  "customerName": "Nguyen An",
  "loyaltyScore": 120
}
~~~

Domain POJO:

~~~java
private String fullName;
private Integer loyaltyPoints;
~~~

BSON:

~~~javascript
{
  full_name: "Nguyen An",
  loyalty_points: 120
}
~~~

All three names can **differ intentionally**.

### 8.1. Separate the Layers

| Layer | Role | Related Tooling |
|---|---|---|
| HTTP JSON DTO | Public API contract | Jackson, JSON-B |
| Java domain POJO | Business types and validation | Java code |
| BSON document | Persistent storage schema | MongoDB Java Codec |
| Query/index field name | Path inside MongoDB | `Filters`/`Updates`/indexes |
| Aggregation output alias | Temporary/report field name | `$project`/`$group` |

### 8.2. `@JsonProperty` Does Not Replace `@BsonProperty`

If the application uses Jackson:

~~~java
@JsonProperty("customerName")
private String fullName;
~~~

That annotation configures **Jackson** JSON serialization—it does not change the BSON field name used by MongoDB's native `PojoCodec`.

Conversely:

~~~java
@BsonProperty("full_name")
private String fullName;
~~~

does not rename the HTTP JSON response field.

### 8.3. Avoid Mixing Both Mechanisms Carelessly

A class can carry both Jackson and BSON annotations if designed deliberately, but doing so couples the public API to persistence storage. In larger systems, prefer separate DTOs.

---

## 9. Field Naming Conventions: Choose Early, Apply Consistently

Common conventions:

| Convention | Java | BSON |
|---|---|---|
| Uniform camelCase | `customerName` | `customerName` |
| Java camelCase, BSON snake_case | `customerName` | `customer_name` |
| Business-specific | `id` | `_id` |
| Legacy alias | `postalCode` | `zip` |
| Acronym policy | `apiKey` | `api_key` |
| Nested | `shippingAddress.city` | `shipping_address.city` |

### 9.1. Option A — Uniform camelCase

Pros:

- Fewer annotations.
- Query strings are easily inferred from property names.
- Minimal conversion rules.

Cons: if the existing database uses `snake_case`, you must migrate or maintain aliases.

### 9.2. Option B — Java camelCase, BSON snake_case

Pros:

- Consistent when teams or legacy schemas standardize on `snake_case`.
- Stored field names are decoupled from Java variable naming.

Cons:

- Requires annotations or a custom naming convention.
- Queries, indexes, and aggregations must always know the **BSON field names**.
- Renaming a Java property must not accidentally alter the persistent schema.

### 9.3. Adopt a Formal Policy

Example policy:

~~~text
Java classes/properties:
  PascalCase / camelCase

MongoDB collections:
  plural lowercase (customers, purchaseOrders)

BSON fields:
  snake_case, exception _id

Date/time:
  *_at for timestamps; stored as BSON Date UTC

Identifier:
  *_id for references, _id for primary key

Money:
  *_minor_units or Decimal128, with currency

Tenant:
  tenant_id sourced from authentication context
~~~

This policy is illustrative; **what matters is that individual developers do not invent ad-hoc variations**.

### 9.4. Avoid Field Names with Special Characters

MongoDB has special rules for keys containing `.` or starting with `$`, and dotted paths behave differently from literal field names. In normal Java apps, avoid BSON field names with dots, `$` prefixes, odd whitespace, or characters hard to parse as property paths.

### 9.5. Indexes Must Match BSON Names

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    full_name: 1
  }
);
~~~

If the stored field is `full_name`, indexing `fullName` will not serve queries and will cause confusion.

---

## 10. `@BsonProperty`: Renaming a Specific Field

~~~java
import org.bson.codecs.pojo.annotations.BsonProperty;

public class Product {

    @BsonProperty("product_code")
    private String productCode;

    @BsonProperty("display_name")
    private String displayName;

    public Product() {}

    public String getProductCode() {
        return productCode;
    }

    public void setProductCode(String value) {
        productCode = value;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String value) {
        displayName = value;
    }
}
~~~

BSON:

~~~javascript
{
  product_code: "SKU-2026",
  display_name: "Product A"
}
~~~

### 10.1. Annotation Convention Must Be Enabled

`Conventions.DEFAULT_CONVENTIONS` includes `ANNOTATION_CONVENTION`; in custom configurations, omitting `ANNOTATION_CONVENTION` stops `@BsonProperty` from taking effect.

### 10.2. Where to Place Annotations?

Driver docs support placing annotations on fields or accessors; for private field mapping, provide matching getters/setters or configure conventions so the driver accesses the property cleanly.

Keep a single consistent style (such as annotations on private fields with public JavaBean accessors) to avoid conflicts.

### 10.3. `@BsonProperty` Does Not Automatically Rewrite Queries

~~~java
Filters.eq("product_code", "SKU-2026");
~~~

is required when the stored MongoDB field is `product_code`. Do not write `Filters.eq("productCode", ...)` expecting POJO metadata to rewrite the filter.

---

## 11. `@BsonId` and the `_id` Key

### 11.1. Native ObjectId

~~~java
public class Product {

    @BsonId
    private ObjectId id;

    public Product() {}

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }
}
~~~

BSON `_id` has a unique index by default; the driver/codec can generate an `ObjectId` via the generator convention when `id` is null.

### 11.2. Business Identifier vs. Physical ID

~~~javascript
{
  _id: ObjectId("6914dd000000000000000001"),
  tenant_id: "tenant-a",
  product_code: "SKU-2026"
}
~~~

`product_code` is the business key; `_id` is the MongoDB document ID. You may need a compound unique index on `tenant_id + product_code`, but do not conflate the two concepts.

### 11.3. `String` with BSON ObjectId Representation

When the application requires a `String` ID property while MongoDB stores BSON `ObjectId`, use:

~~~java
import org.bson.BsonType;
import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.codecs.pojo.annotations.BsonRepresentation;

public class LegacyEntity {

    @BsonId
    @BsonRepresentation(BsonType.OBJECT_ID)
    private String id;

    public LegacyEntity() {}

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }
}
~~~

`@BsonRepresentation` is **not an arbitrary type converter**. Driver docs illustrate `String ↔ ObjectId`; other types may require a codec implementing `RepresentationConfigurable`.

### 11.4. Never Unintentionally Mix ObjectId and String in the Database

~~~javascript
{ _id: ObjectId("6914dd000000000000000001") }
~~~

is distinct from:

~~~javascript
{ _id: "6914dd000000000000000001" }
~~~

These are two different BSON types; queries and index equality checks do not treat them as the same ID.

### 11.5. Composite `_id`

You can use an object/value type as `_id` when required by schema design, provided a codec exists for the embedded ID type and values are immutable. Never attempt to mutate `_id` on an existing document via normal updates.

---

## 12. Key Annotations in POJO Codecs

| Annotation | Function | When Used |
|---|---|---|
| `@BsonId` | Maps property to `_id` | Document identifier |
| `@BsonProperty` | Specifies BSON field name | `snake_case`/legacy fields |
| `@BsonIgnore` | Excludes property from mapping | Derived/runtime-only values |
| `@BsonCreator` | Selects constructor/static factory when decoding | Immutable/constructor-only models |
| `@BsonRepresentation` | Changes BSON representation when supported by codec | E.g., `String ↔ ObjectId` |
| `@BsonExtraElements` | Captures unmapped fields | Forward compatibility/dynamic fields |
| `@BsonDiscriminator` | Distinguishes subtypes | Polymorphic document hierarchies |

These annotations live in package:

~~~java
org.bson.codecs.pojo.annotations
~~~

### 12.1. There Is No Built-In Annotation for Collection Name

The native POJO codec has no built-in MongoDB annotation mapping a class to a collection name. Normally you specify it explicitly:

~~~java
database.getCollection("products", Product.class);
~~~

You can store a `COLLECTION_NAME` constant in the class or repository.

### 12.2. Annotations Are Not Validators

`@BsonProperty("full_name")` tells the codec how to map a field; it does **not** enforce that documents in MongoDB always contain `full_name` or that `loyalty_points` is non-negative.

To enforce schema rules in the database, consider `$jsonSchema` validation and indexes; validate inputs separately in the application.

---

## 13. `@BsonIgnore`: Excluding Properties from Storage

Example:

~~~java
public class Customer {

    private String fullName;

    @BsonIgnore
    private String displayLabelCache;

    public Customer() {}

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String value) {
        fullName = value;
    }

    public String getDisplayLabelCache() {
        return displayLabelCache;
    }

    public void setDisplayLabelCache(String value) {
        displayLabelCache = value;
    }
}
~~~

`displayLabelCache` can be computed from other fields and does not need to be stored in BSON.

### 13.1. `transient` and `static`

Default POJO mapping targets supported instance properties. `static` or `transient` fields should not be relied upon accidentally for business persistence.

### 13.2. Watch Out for Sensitive Data

Adding `@BsonIgnore` alone does not secure sensitive data: the field can still appear in JSON APIs, logs, or traces without matching controls. Persistence mapping and data exposure are separate layers.

### 13.3. Derived Values

If a class defines `getFullNameUpperCase()` without a backing field, the driver may treat it as a bean property depending on conventions. Model or `@BsonIgnore` explicitly so inserts/replaces do not unexpectedly write computed fields.

---

## 14. `@BsonCreator`: Parameterized Constructors

By default, the POJO codec uses a no-arg constructor and then calls setters. For immutable classes or classes without public setters, annotate a constructor or static factory with `@BsonCreator`.

~~~java
import org.bson.codecs.pojo.annotations.BsonCreator;
import org.bson.codecs.pojo.annotations.BsonProperty;

public final class CountryCode {

    private final String code;
    private final String displayName;

    @BsonCreator
    public CountryCode(
        @BsonProperty("code") String code,
        @BsonProperty("display_name") String displayName
    ) {
        this.code = code;
        this.displayName = displayName;
    }

    public String getCode() {
        return code;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

### 14.1. Why Annotate Every Parameter?

Driver docs require `@BsonCreator` parameters to carry `@BsonProperty` or `@BsonId` so the codec knows how to bind BSON fields when instantiating the object.

### 14.2. This Is Not a Default JSON Constructor

Jackson's `@JsonCreator` does not replace `@BsonCreator`. If using both frameworks, configure annotations appropriately for each layer.

### 14.3. Missing Constructor Arguments in Data

When a constructor parameter is required but missing from the BSON document, behavior yields default/null/exception depending on type and model. Validate critical invariants right in the constructor:

~~~java
if (code == null || code.isBlank()) {
    throw new IllegalArgumentException(
        "code is required"
    );
}
~~~

When older documents lack a newly added property, plan migrations or defaults rather than letting production reads fail en masse.

---

## 15. JavaBean Conventions, Private Fields, and Setter Access

### 15.1. Standard Path

Example:

~~~java
private String city;

public String getCity() { return city; }

public void setCity(String city) {
    this.city = city;
}
~~~

With POJO codecs, matching getters and setters with appropriate visibility map the `city` property cleanly.

### 15.2. Private Setters or Missing Setters

When public setters are absent, deserializing into private fields may require enabling the convention:

~~~java
import org.bson.codecs.pojo.Conventions;
import org.bson.codecs.pojo.PojoCodecProvider;

import java.util.ArrayList;
import java.util.List;

List<org.bson.codecs.pojo.Convention> conventions =
    new ArrayList<>(Conventions.DEFAULT_CONVENTIONS);

conventions.add(
    Conventions.SET_PRIVATE_FIELDS_CONVENTION
);

PojoCodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .automatic(true)
        .conventions(conventions)
        .build();
~~~

This convention sets **private fields** via reflection when setters are absent, under driver rules. Getters are still required for serialization in standard cases. Do not use it as an excuse to skip clean constructors and encapsulation.

### 15.3. Getter/Setter Visibility Must Align

The native POJO codec relies on JavaBean property introspection and visibility rules. Mixing a private getter with a public setter on the same property can break mapping.

### 15.4. Java Records Are Not Traditional JavaBean POJOs

Records have canonical constructors and `name()` accessors instead of `getName()`. Modern Java Drivers include a dedicated **record codec** and guidance; do not blindly apply mutable POJO getter/setter assumptions to records.

---

## 16. Java Records: When to Prefer Them Over Mutable POJOs

Java records provide immutable data carriers useful for read-only views and DTOs.

~~~java
public record CustomerSummary(
    String fullName,
    int loyaltyPoints
) {}
~~~

Modern Java Drivers support encoding/decoding records via the default codec registry as documented in **Document Data Format: Records**. Java records require Java 16+ syntax (commonly Java 17 LTS).

### 16.1. Records and BSON Naming

If BSON uses `full_name` while the record component is `fullName`, configure mapping using record-codec annotations supported by your driver version or convert explicitly via DTOs. Do not assume `@BsonProperty` works identically across all POJO and record versions without checking.

### 16.2. Immutable in Java Does Not Make the Database Immutable

A record object lacks setters in Java, yet MongoDB documents can still be updated with `Updates.set(...)`. Domain object immutability and database write privileges are two separate concepts.

### 16.3. When to Use Mutable POJOs?

Use mutable POJOs when JavaBeans, legacy frameworks, setters, or complex mapped entities are required. For immutable constructor-based classes, `@BsonCreator` is another option.

---

## 17. Nested POJOs: Mapping Nested Documents

BSON:

~~~javascript
{
  customer_name: "Nguyen An",
  shipping_address: {
    city: "Ho Chi Minh City",
    district: "Binh Thanh"
  }
}
~~~

Nested POJOs:

~~~java
public class Address {

    private String city;
    private String district;

    public Address() {}

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getDistrict() {
        return district;
    }

    public void setDistrict(String district) {
        this.district = district;
    }
}
~~~

~~~java
public class Order {

    @BsonProperty("customer_name")
    private String customerName;

    @BsonProperty("shipping_address")
    private Address shippingAddress;

    public Order() {}

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String name) {
        customerName = name;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public void setShippingAddress(Address address) {
        shippingAddress = address;
    }
}
~~~

The registry must include codecs for both `Order` and `Address` (via automatic or explicit registration).

### 17.1. Dotted Paths in Queries

~~~java
Filters.eq(
    "shipping_address.city",
    "Ho Chi Minh City"
);
~~~

`shipping_address` is the parent BSON field; `city` is the nested `Address` BSON field.

### 17.2. Nested Arrays and Maps

~~~java
public class Order {

    private java.util.List<OrderItem> items;

    @BsonProperty("extra_attributes")
    private java.util.Map<String, String> extraAttributes;

    public Order() {}

    // Getters and setters for both properties.
}
~~~

Element types should be concrete. `List<OrderItem>` tells the codec each item's object type; `List<Object>` complicates schema governance and versioning.

### 17.3. Map Keys Become BSON Field Names

With `Map<String, String>`, map keys become field names inside the nested BSON document. Validate user-supplied keys to reject unintended dots, `$`-prefixed keys, and oversized payloads.

---

## 18. Enum Serialization and Legacy Values

~~~java
public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    BLOCKED
}
~~~

~~~java
public class Customer {

    private CustomerStatus status;

    public Customer() {}

    public CustomerStatus getStatus() {
        return status;
    }

    public void setStatus(CustomerStatus status) {
        this.status = status;
    }
}
~~~

### 18.1. Default Enum Codecs

The driver's default codec registry includes support for enum types. Since Java Driver 4.5, `PojoCodecProvider` does not automatically include a built-in enum codec on its own; combine it with the default registry or supply a custom enum codec.

### 18.2. Renaming Enums Can Break Decoding

Database stores:

~~~javascript
{ status: "INACTIVE" }
~~~

If code renames the enum constant to `DISABLED` without migrating legacy documents or adding custom mapping, decoding will fail.

### 18.3. Do Not Treat Java Enum Names as Immutable Schema

You can persist stable codes like `"A"` or `"I"` with a custom codec to decouple from Java enum identifiers; ensure custom codecs are registered consistently and migrations are tested.

### 18.4. Unrecognized Values

If a newer app version writes a new enum value, older app instances may not recognize it. Establish a forward-compatibility policy: fail explicitly, map to a controlled `UNKNOWN` sentinel, or deploy readers before writers during rollouts.

---

## 19. Missing, Null, and Primitive Defaults in POJOs

BSON can contain:

~~~javascript
{ _id: 1 }
{ _id: 2, loyalty_points: null }
{ _id: 3, loyalty_points: 0 }
~~~

In a POJO:

~~~java
private Integer loyaltyPoints;
~~~

`null` can represent either a missing field or an explicit BSON `null` after decoding; inspecting the Java property alone cannot tell them apart.

### 19.1. Default Null Serialization

Per native POJO codec docs, properties whose value is `null` are **omitted when serializing by default**, unless custom serialization is configured.

Therefore:

~~~java
customer.setLoyaltyPoints(null);
customers.insertOne(customer);
~~~

does not guarantee BSON stores `loyalty_points: null`. Always inspect the raw persisted document.

### 19.2. Be Careful with PATCH Operations

An HTTP PATCH:

~~~json
{
  "loyaltyPoints": null
}
~~~

may mean **clear the field**, whereas a `null` POJO property could also mean **the client omitted the field**.

Never blindly decode into a simple POJO and run `replaceOne` for PATCH endpoints without distinguishing three states:

- Omitted → leave unchanged.
- Explicit `null` → set `null` or `$unset` per API contract.
- Value provided → update value.

### 19.3. Primitive Defaults

~~~java
private int loyaltyPoints;
private boolean active;
~~~

When BSON omits the field, the object holds `0` and `false`. If business logic must distinguish "missing" from "explicitly 0/false," use wrapper types or explicit presence flags with validation.

### 19.4. MongoDB Null Filter Semantics

~~~javascript
db.customers.find({ loyalty_points: null });
~~~

Matches both documents where the field is `null` **and documents where the field does not exist**. To match only existing explicit `null`, use `$type: 10` (or combine `$exists`); to match missing only, use `$exists: false`.

---

## 20. `@BsonExtraElements`: Preserving Unknown Fields

Suppose BSON gains new fields:

~~~javascript
{
  _id: ObjectId("6914ee000000000000000001"),
  full_name: "Nguyen An",
  loyalty_points: 120,
  preferred_language: "vi",
  app_feature_flag: "BETA"
}
~~~

An older POJO only knows `full_name` and `loyalty_points`.

To preserve unknown fields:

~~~java
import org.bson.Document;
import org.bson.codecs.pojo.annotations.BsonExtraElements;

public class FlexibleCustomer {

    @BsonProperty("full_name")
    private String fullName;

    @BsonExtraElements
    private Document extras;

    public FlexibleCustomer() {}

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String value) {
        fullName = value;
    }

    public Document getExtras() {
        return extras;
    }

    public void setExtras(Document extras) {
        this.extras = extras;
    }
}
~~~

`@BsonExtraElements` accepts `Document`, `BsonDocument`, or `Map<String, Object>` per documentation.

### 20.1. When to Use It?

- Incremental schema evolution.
- Reading dynamic metadata.
- Tenant-extensible fields.
- Migration tools that must preserve unknown properties.

### 20.2. Do Not Abuse It

If users can write arbitrary extra fields, enforce validation, size caps, and authorization. Unmanaged unknown fields can collide with newly added fields from other app versions.

### 20.3. Unknown Fields and Replace

If a POJO **lacks** `@BsonExtraElements`, decodes a document containing newer fields, and then writes it back via `replaceOne`, the unknown fields will be wiped out. Schema evolution must therefore pair with safe update strategies.

---

## 21. Polymorphism and `@BsonDiscriminator`

Suppose multiple event types share one collection:

~~~text
Event
  +-- UserCreatedEvent
  +-- OrderPaidEvent
~~~

A BSON document stores a subtype discriminator field:

~~~javascript
{
  _t: "OrderPaidEvent",
  order_id: "ORD-101",
  amount: NumberLong("500000")
}
~~~

`@BsonDiscriminator` or `ClassModelBuilder.enableDiscriminator(true)` lets the codec resolve the concrete subtype when decoding an abstract base or interface in supported setups.

### 21.1. Rules

- Register the base class and all concrete subtypes.
- Define explicit discriminator keys/values as part of your contract.
- Never allow untrusted user input to supply arbitrary discriminator class names outside an allowlist.
- Never rename discriminator values on deploy without a migration/compatibility plan.
- Test reading legacy documents whenever adding a new subtype.

### 21.2. Illustrative Annotation Example

~~~java
import org.bson.codecs.pojo.annotations.BsonDiscriminator;

@BsonDiscriminator(
    key = "_t",
    value = "OrderPaidEvent"
)
public class OrderPaidEvent {
    // Properties + getters/setters + no-arg constructor.
}
~~~

If a property is typed as base `Event` but holds derived instances, configure the provider/model for polymorphic decoding; annotating only one subtype is not always sufficient across all hierarchies.

### 21.3. When to Use Discriminators?

Useful for union-like models, though if event schemas diverge widely, `Document` with explicit event-type dispatch or separate collections is often simpler to operate.

---

## 22. `ClassModel`, `PropertyModel`, and Custom Conventions

When annotations are not enough, POJO codecs support programmatic model configuration:

- `ClassModel`: metadata for a class, constructor, ID, discriminator, and properties.
- `PropertyModel`: metadata for one property, BSON field names, codec, and serialization policy.
- `Convention`: rule applied to models while building codecs.

### 22.1. Explicit ClassModel Example

~~~java
import org.bson.codecs.pojo.ClassModel;
import org.bson.codecs.pojo.PojoCodecProvider;

ClassModel<Customer> customerModel =
    ClassModel.builder(Customer.class)
        .build();

PojoCodecProvider provider =
    PojoCodecProvider.builder()
        .register(customerModel)
        .build();
~~~

### 22.2. Setting BSON Field Names via Model Builder

The Java Driver provides `PropertyModelBuilder` with `readName(...)` and `writeName(...)`. These control the BSON field names used for reading and writing. Normally, **set the same target name for both directions** unless intentionally splitting them during a migration, and check the Javadoc for your exact driver version.

Conceptual example:

~~~java
var model = ClassModel.builder(Customer.class);

model.getProperty("fullName")
    .readName("full_name")
    .writeName("full_name");
~~~

Then register `model.build()` with `PojoCodecProvider`. Across many classes, implement a `Convention` to enforce the naming policy in one place.

### 22.3. Custom snake_case Convention

A convention can iterate over `ClassModelBuilder.getPropertyModelBuilders()`, convert `camelCase` to `snake_case`, and rename mapped properties. Be sure to handle:

- Acronyms: `apiURL` → `api_url` or `api_u_r_l`?
- IDs: `id` must stay `_id`.
- Fields with explicit `@BsonProperty`: should the annotation take precedence?
- Legacy field names that break the rule.
- Nested POJOs and maps.
- Convention ordering.
- Both read and write names together.

### 22.4. Convention Ordering Matters

`Conventions.DEFAULT_CONVENTIONS` includes:

- `CLASS_AND_PROPERTY_CONVENTION`.
- `ANNOTATION_CONVENTION`.
- `OBJECT_ID_GENERATORS`.

Builders execute conventions in order, so a later convention can override an earlier one. Write tests verifying that explicit `@BsonProperty` annotations are not clobbered by a custom naming convention.

### 22.5. Practical Recommendations

- Only a few fields differ: use `@BsonProperty`.
- Hundreds of classes in `snake_case`: consider a custom convention, with thorough tests for acronyms and legacy names.
- Complex migrations: explicit mapping or DTO conversion is easier to control.
- Do not write full custom codecs for every POJO when conventions already handle it.

---

## 23. Custom Codecs for Value Objects

A domain may define custom types like `Money`, `EmailAddress`, or `CurrencyCode` while BSON stores strings or `Decimal128`.

Without a codec:

~~~text
CodecConfigurationException:
Can't find a codec for class example.domain.Money
~~~

### 23.1. Custom Type Example

~~~java
public final class EmailAddress {

    private final String value;

    public EmailAddress(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email cannot be empty"
            );
        }
        this.value = value;
    }

    public String value() {
        return value;
    }
}
~~~

### 23.2. Writing a `Codec<EmailAddress>`

~~~java
import org.bson.BsonReader;
import org.bson.BsonWriter;

import org.bson.codecs.Codec;
import org.bson.codecs.DecoderContext;
import org.bson.codecs.EncoderContext;

public final class EmailAddressCodec
        implements Codec<EmailAddress> {

    @Override
    public void encode(
            BsonWriter writer,
            EmailAddress value,
            EncoderContext context) {

        writer.writeString(value.value());
    }

    @Override
    public EmailAddress decode(
            BsonReader reader,
            DecoderContext context) {

        return new EmailAddress(reader.readString());
    }

    @Override
    public Class<EmailAddress> getEncoderClass() {
        return EmailAddress.class;
    }
}
~~~

### 23.3. Registry Ordering

~~~java
import static org.bson.codecs.configuration
    .CodecRegistries.fromCodecs;
import static org.bson.codecs.configuration
    .CodecRegistries.fromProviders;
import static org.bson.codecs.configuration
    .CodecRegistries.fromRegistries;

CodecRegistry registry = fromRegistries(
    fromCodecs(new EmailAddressCodec()),
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(
        PojoCodecProvider.builder()
            .automatic(true)
            .build()
    )
);
~~~

Place custom codecs ahead of default/POJO providers so they take precedence. Note that this codec only handles BSON `String` and does not handle BSON `null` or other types; production models must define null semantics, normalization, and error handling.

### 23.4. Why Not Just Map Email as a String?

For a small system, `String` is simpler. Value Objects help enforce invariants and normalization at the cost of extra mapping and maintenance. Choose based on project needs.

---

## 24. Decimal128, Money, and Precision

BSON supports `Int32`, `Int64`, `Double`, and `Decimal128`. When monetary values require exact decimal precision, establish a clear contract.

### 24.1. Storing `Decimal128` in a `Document`

~~~java
import org.bson.types.Decimal128;
import java.math.BigDecimal;

Document invoice = new Document()
    .append("currency", "USD")
    .append(
        "total",
        new Decimal128(new BigDecimal("123.45"))
    );
~~~

### 24.2. POJO Property

~~~java
public class Invoice {

    private Decimal128 total;

    public Invoice() {}

    public Decimal128 getTotal() {
        return total;
    }

    public void setTotal(Decimal128 value) {
        total = value;
    }
}
~~~

For domain arithmetic:

~~~java
BigDecimal amount =
    invoice.getTotal().bigDecimalValue();
~~~

### 24.3. Avoid `double` for Money

~~~java
double total = 0.1 + 0.2;
~~~

Binary floating-point cannot represent `0.1` or `0.2` exactly. Use `BigDecimal`/`Decimal128` or integer minor units per contract, and store the currency.

### 24.4. `Decimal128` Is Not `Long`

If BSON stores `total` as `Decimal128` while the POJO declares `Long`, the codec does not silently convert with guaranteed precision. Migrate the data or write a controlled custom codec/mapper.

### 24.5. Null and Missing

Missing, `null`, and `0` monetary fields can carry distinct business meanings; validators and migrations should define them clearly.

---

## 25. Date, Instant, LocalDate, and Timezones

MongoDB BSON Date stores an instant in time as milliseconds since the UTC epoch. Display layers may format in local timezones, but the stored point-in-time is UTC.

### 25.1. Java `Date`

~~~java
import java.util.Date;

public class AuditEvent {

    private Date createdAt;

    public AuditEvent() {}

    public Date getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Date value) {
        createdAt = value;
    }
}
~~~

### 25.2. Java `Instant`

~~~java
import java.time.Instant;

Instant now = Instant.now();
~~~

Modern Java Drivers include codecs for standard `java.time` types including `Instant`. Use `Instant` for exact points in time, verifying exact type/codec behavior in your driver version.

### 25.3. `LocalDate` Is a Calendar Date, Not a Timestamp

A birth date like `"1995-06-10"` should not be accidentally converted into a timestamp with an ambiguous timezone. Represent it as an ISO string or a driver-supported type per domain contract.

### 25.4. `LocalDateTime` Carries No Timezone

Using `LocalDateTime` as an absolute event timestamp without a zone leaves the timezone ambiguous. Use `Instant` for `createdAt`/`paidAt`, `LocalDate` for calendar dates, and store an explicit timezone if business logic requires it.

### 25.5. Millisecond Precision

BSON Date has millisecond precision, whereas Java `Instant` supports nanoseconds. A round-trip truncates sub-millisecond nanoseconds; avoid asserting `Instant.equals` on un-normalized nanosecond inputs.

### 25.6. Date/Time Field Naming

`created_at`, `updated_at`, and `paid_at` denote timestamps. `billing_date` may denote a calendar date. Field names should clearly reflect semantics.

---

## 26. UUIDs and Binary Representation

UUIDs in Java use `java.util.UUID`, while BSON supports different binary subtypes/representations. When migrating from legacy drivers, pay close attention to `UuidRepresentation`.

### 26.1. Explicitly Configure UUID Representation

Example (use only when your BSON schema stores UUIDs in `STANDARD` format):

~~~java
import com.mongodb.MongoClientSettings;
import org.bson.UuidRepresentation;

MongoClientSettings settings =
    MongoClientSettings.builder()
        .applyConnectionString(
            new com.mongodb.ConnectionString(uri)
        )
        .uuidRepresentation(
            UuidRepresentation.STANDARD
        )
        .build();

try (MongoClient client =
         MongoClients.create(settings)) {

    // ...
}
~~~

### 26.2. Never Change Representation Arbitrarily

Legacy data written with a different representation will fail lookups if you switch representation without migrating. Migrations must inspect binary subtypes/bytes, test round-trips, and plan conversion carefully.

### 26.3. UUID String Differs from UUID Binary

`"550e8400-e29b-41d4-a716-446655440000"` as a BSON String will not match a UUID stored as BSON Binary. Queries must use the exact matching type.

---

## 27. Unknown Fields, Schema Evolution, and Backwards Compatibility

MongoDB allows documents in the same collection to have evolving structures:

~~~javascript
// V1
{
  _id: 1,
  full_name: "Nguyen An"
}

// V2
{
  _id: 2,
  full_name: "Binh",
  loyalty_points: 20
}

// V3
{
  _id: 3,
  full_name: "Chi",
  loyalty_points: 40,
  preferred_language: "vi"
}
~~~

### 27.1. Adding a New Property

If V3 code expects `preferredLanguage`, V1/V2 documents will decode with `null`/default. If the field is mandatory, backfill or handle defaults in the app before enforcing it.

### 27.2. Removing a Property from a Java Class

If new code drops `oldField` while the database still holds it, reads ignore it—but **`replaceOne` from the new POJO will delete `oldField`**. Avoid blind full replacements during rolling deployments.

### 27.3. Renaming a Field Is a Data Migration

When migrating BSON `full_name` to `display_name`:

1. Inventory all affected queries, indexes, and aggregations.
2. Deploy code that reads both fields during a compatibility window.
3. Backfill existing documents.
4. Create/update indexes accordingly.
5. Switch writes to the new field name.
6. Reconcile data.
7. Drop the old field only after no active app version uses it.

Changing `@BsonProperty("full_name")` to `@BsonProperty("display_name")` does **not** automatically rename existing data in MongoDB.

### 27.4. Schema Version

Storing a `schema_version` field helps distinguish document formats, though it does not replace migration or validation—decoders must still handle every live version.

### 27.5. Rolling Application Deployments

While V1 and V2 run concurrently, V2 must not write a BSON shape that crashes V1 decoders unless isolated by feature flags or traffic routing. Follow the expand → migrate → contract pattern.

---

## 28. Update Operators vs. Replacing the Entire POJO

### 28.1. Partial Updates Are Safer for PATCH

~~~java
customers.updateOne(
    Filters.eq("_id", customerId),
    Updates.combine(
        Updates.set("full_name", "Nguyen An"),
        Updates.set("loyalty_points", 150)
    )
);
~~~

Only the specified fields change; any unknown fields remain intact.

### 28.2. `replaceOne` Replaces the Entire Document

~~~java
customers.replaceOne(
    Filters.eq("_id", customer.getId()),
    customer
);
~~~

Replace serializes the entire POJO as the new document (subject to `_id` immutability). Any legacy field omitted from the POJO is removed from the database.

### 28.3. Null + Replace Can Cause Data Loss

If a POJO was decoded from a projection omitting fields, those missing properties become `null`. Default encoding omits nulls; therefore, **never replace a document using a partially loaded POJO**.

### 28.4. When Is Replace Appropriate?

- The document represents an aggregate root and all fields were loaded and validated.
- A version field enforces optimistic concurrency.
- The schema is strictly governed.
- A full overwrite is intentional.
- No external writers or unmapped legacy fields exist.

### 28.5. `_id` Cannot Be Changed

If the POJO carries a different `_id` than the target document, replace fails because `_id` is immutable. Keep ID types and representations consistent.

---

## 29. Projections and Typed POJOs

Suppose a query only needs the customer's name:

~~~java
Customer partial = customers.find(
    Filters.eq("_id", customerId)
).projection(
    Projections.include("full_name")
).first();
~~~

The decoded POJO will look like:

~~~text
id            = ObjectId...
fullName      = "Nguyen An"
loyaltyPoints = null
active        = null
~~~

### 29.1. A Partial POJO Is Not a Full Entity

Passing `partial` to `replaceOne` would wipe out `loyalty_points` and `active`.

### 29.2. Better: Use a DTO / Read Model

Read projections with `Document` and map to a DTO:

~~~java
Document doc = customers
    .withDocumentClass(Document.class)
    .find(
        Filters.eq("_id", customerId)
    )
    .projection(
        Projections.include("full_name")
    )
    .first();

String name =
    doc == null ? null : doc.getString("full_name");
~~~

### 29.3. Aggregations with Shapes Different from the Entity

If `$group` outputs `_id` and `totalRevenue`, that is not a `Customer` POJO. Decode into `Document` or a dedicated report/read model rather than forcing it into `Customer`.

---

## 30. Optimistic Locking with a Version Field

A POJO can track a business version:

~~~javascript
{
  _id: ObjectId("6914ff000000000000000001"),
  full_name: "Nguyen An",
  loyalty_points: 120,
  version: 3
}
~~~

### 30.1. Conditional Update

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;

long expectedVersion = 3L;

var result = customers.updateOne(
    and(
        eq("_id", customerId),
        eq("version", expectedVersion)
    ),
    combine(
        set("loyalty_points", 130),
        inc("version", 1)
    )
);

if (result.getModifiedCount() != 1) {
    throw new IllegalStateException(
        "Optimistic concurrency conflict"
    );
}
~~~

### 30.2. Why Is This Needed?

Two concurrent requests reading the same entity and replacing it later can cause lost updates. Filtering on `version` ensures a writer detects concurrent modifications.

### 30.3. POJO Codecs Do Not Add Optimistic Locking Automatically

`@BsonProperty("version")` only maps the field; it does not turn `replaceOne` into a compare-and-swap operation. The application layer must construct the version filter, increment, and retry policy.

---

## 31. Field Names in Filters, Updates, Sorts, and Indexes

If:

~~~java
@BsonProperty("full_name")
private String fullName;
~~~

then:

~~~java
Filters.eq("full_name", "Nguyen An");
Updates.set("full_name", "Nguyen Binh");
Sorts.ascending("full_name");
Indexes.ascending("full_name");
~~~

is how you reference the persisted field.

### 31.1. Avoid Scattered Magic Strings

A clean pattern:

~~~java
public final class CustomerFields {

    public static final String ID = "_id";
    public static final String FULL_NAME = "full_name";
    public static final String LOYALTY_POINTS = "loyalty_points";
    public static final String TENANT_ID = "tenant_id";

    private CustomerFields() {}
}
~~~

Usage:

~~~java
Filters.eq(
    CustomerFields.FULL_NAME,
    "Nguyen An"
);
~~~

### 31.2. Do Not Reflect Java Getters on Every Query

Typed query DSLs can be built at the application layer, but ad-hoc reflection mappers must handle annotations, nested paths, polymorphism, and custom conventions. Avoid writing an untested custom ORM just to save a few constants.

### 31.3. Dotted Paths After Renames

If a parent field changes from `shippingAddress` to `shipping_address`, update query paths too:

~~~java
Filters.eq(
    "shipping_address.city",
    "Ho Chi Minh City"
);
~~~

---

## 32. Codec Registry Order and Conflicts

### 32.1. Registries Are Searched in Order

~~~java
CodecRegistry registry = fromRegistries(
    fromCodecs(new EmailAddressCodec()),
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(pojoProvider)
);
~~~

Putting the custom codec first ensures `EmailAddressCodec` handles `EmailAddress`.

### 32.2. Putting POJO Auto Provider Before Default Can Cause Issues

If automatic POJO codecs attempt to map types handled natively by the default registry, unexpected behavior can occur. MongoDB documentation recommends placing the **default codec registry before `PojoCodecProvider`**.

### 32.3. Multi-Module Applications

One module registers a custom `Money` codec while another creates a client with only the default registry. One module works while the other fails. Centralize database client/registry configuration and test it.

### 32.4. Dependency Versions

`mongodb-driver-sync`, `mongodb-driver-core`, and `bson` must share compatible versions. Mixed JAR versions on the classpath cause runtime codec failures unrelated to MongoDB Server.

---

## 33. Diagnosing `CodecConfigurationException`

### 33.1. "Can't find a codec for class X"

Common causes:

- `PojoCodecProvider` was never registered.
- Codec registry only contains default codecs.
- Nested class omitted in explicit registration mode.
- Field type `Optional<T>`, interface, or generic lacks a codec.
- Registry applied to one database/collection while querying another using client defaults.
- Custom value type lacks a codec.
- Class, constructor, getters, or setters do not meet requirements.

Steps to resolve:

1. Identify the exact class missing a codec.
2. Check the collection's actual generic type.
3. Inspect the configured codec registry.
4. Register the POJO/class/package or custom codec.
5. Test encoding/decoding against a sample document.

### 33.2. Failure on a Nested Property

If `Customer` fails with missing codec for `Money`, `Customer` itself is not the missing codec—register a codec for the **nested property type**.

### 33.3. Unresolvable Constructor

Without a no-arg constructor or valid `@BsonCreator`, the driver cannot instantiate the object during decoding.

### 33.4. Field Name Mismatch

`Filters.eq("fullName", ...)` returning zero results when BSON stores `full_name` is **not a codec error**—it is a wrong query field key.

### 33.5. Unexpected Enum Value

If the database contains `"SUSPENDED"` absent from the Java enum, decoding fails. Fix with data migration or fallback policies, not just registry tweaks.

### 33.6. Numeric Type Mismatch

Never assume `Long` ↔ `Integer` or `Decimal128` ↔ `Double` convert silently. Check actual BSON types with `BsonDocument`.

---

## 34. Inspecting Raw BSON When POJO Reads Fail

### 34.1. Inspecting via `mongosh`

~~~javascript
use java_codec_lab

db.customers.findOne({
  full_name: "Nguyen An"
});
~~~

### 34.2. Inspecting via `Document` Collection in Java

~~~java
MongoCollection<Document> rawCustomers =
    database.getCollection(
        "customers",
        Document.class
    );

Document raw = rawCustomers.find(
    Filters.eq(
        "full_name",
        "Nguyen An"
    )
).first();

if (raw != null) {
    System.out.println(raw.toJson());
}
~~~

### 34.3. Compare Three Things

- Raw BSON field names and BSON types.
- POJO annotations/conventions and Java field types.
- Filter/projection/update paths sent by the application.

Example:

~~~text
Raw BSON:        loyalty_points (INT64)
POJO:            loyaltyPoints (Integer)
Query filter:    loyaltyPoints
~~~

There are at least two mismatches here: numeric type and query field name.

### 34.4. `toJson` Is for Inspection, Not Type Proof

Extended JSON has multiple output modes (relaxed vs. canonical). Use BSON-aware inspection or decode tests to verify exact BSON types.

---

## 35. Safe Round-Trip Testing in the Lab

### 35.1. Create a Customer

~~~java
Customer customer = new Customer();
customer.setFullName("Test Customer");
customer.setLoyaltyPoints(25);
customer.setActive(true);
~~~

### 35.2. Insert and Read Back by ID

~~~java
customers.insertOne(customer);

ObjectId id = customer.getId();

Customer actual = customers
    .find(Filters.eq("_id", id))
    .first();

if (actual == null) {
    throw new AssertionError(
        "Customer was not found"
    );
}

if (!"Test Customer".equals(actual.getFullName())) {
    throw new AssertionError(
        "fullName round-trip failed"
    );
}

if (!Integer.valueOf(25)
        .equals(actual.getLoyaltyPoints())) {
    throw new AssertionError(
        "loyaltyPoints round-trip failed"
    );
}
~~~

### 35.3. Verify the Raw Persisted Schema

~~~java
Document raw = customers
    .withDocumentClass(Document.class)
    .find(Filters.eq("_id", id))
    .first();

if (raw == null
        || !raw.containsKey("full_name")) {
    throw new AssertionError(
        "BSON field full_name missing"
    );
}

if (raw.containsKey("fullName")) {
    throw new AssertionError(
        "Unexpected Java-style BSON field"
    );
}
~~~

### 35.4. Cleanup

~~~java
customers.deleteOne(
    Filters.eq("_id", id)
);
~~~

Run only against test databases/collections. In real test suites, use unique IDs, teardown hooks, and assertion frameworks (JUnit/AssertJ) to isolate tests.

### 35.5. Why Verify Raw Fields?

If both encoder and decoder mistakenly map to `fullName` instead of the `full_name` contract, Java-only POJO round-trip tests **still pass**. Inspecting raw BSON catches schema contract drift immediately.

---

## 36. Testing Migrations and Field Renames

Suppose we migrate `customer_name` to `full_name`.

### 36.1. Prepare a Legacy Document

~~~javascript
db.customers.insertOne({
  _id: "legacy-101",
  customer_name: "Legacy Customer",
  loyalty_points: 10
});
~~~

### 36.2. Reading with the New Mapping

If the POJO only has `@BsonProperty("full_name")`, `fullName` will decode as `null`. Do not assume data was lost; the old field is still in MongoDB.

### 36.3. Choose a Migration Strategy

- **Expand:** code reads both old and new schemas via a migration mapper.
- **Backfill:** copy old field values into the new field.
- **Switch writes:** roll out app versions writing the new field.
- **Contract:** remove the old field and old indexes once safe.
- **Validate:** count documents missing the new field and verify consistency.

### 36.4. Simplified Migration Example (Lab Only)

~~~javascript
db.customers.updateMany(
  {
    customer_name: { $exists: true },
    full_name: { $exists: false }
  },
  [
    {
      $set: {
        full_name: "$customer_name"
      }
    },
    {
      $unset: "customer_name"
    }
  ]
);
~~~

In production, perform dry-runs, privilege checks, rollback planning, batching/rate limiting, duplicate/conflict handling, and auditing beforehand.

### 36.5. Combine with Optimistic Concurrency

If live traffic updates the same documents, migrations must not overwrite newer edits. Lock writes during a brief window or use version/generation CAS across bulk batches.

---

## 37. Naming Policies in Multi-Microservice Systems

A system has Java, Node.js, and Python clients reading the same collection:

~~~text
Java service:    customerName
Node service:    customerName
Python service:  customer_name
MongoDB BSON:    full_name
~~~

If every service picks its own mapping independently, each may write different field names.

### 37.1. A Schema Contract as the Single Source of Truth

Define a language-agnostic BSON schema:

~~~yaml
collection: customers
fields:
  _id: objectId
  tenant_id: string
  full_name: string
  loyalty_points: int32
  created_at: date
~~~

This is a **sample schema contract**, not an auto-applied MongoDB config. Pair it with `$jsonSchema` validators where appropriate.

### 37.2. Contract Tests

- Java serializes exact expected field names.
- Node/Python read them accurately.
- Neither `full_name` nor `fullName` coexists outside migration windows.
- Nullable/default behavior is explicitly defined.
- Date precision and timezones align.
- Currency/`Decimal128` schemas are unambiguous.

### 37.3. Versioning

When renaming BSON fields, coordinate across all teams sharing the collection. Never change an annotation in one repository assuming every other client adapts automatically.

---

## 38. Performance: Cost of POJO Mapping vs. Document

### 38.1. POJOs Are Not Automatically Faster in Every Case

Driver codecs encode/decode per type. POJOs improve type safety, while runtime performance depends on:

- Codec cache, reflection, and model initialization.
- BSON types.
- Document sizes.
- Number of fields and nested arrays.
- Projections.
- HTTP boundary serialization.
- Network, query plan, and index overhead.

For most CRUD workloads, query plans, indexes, and network latency outweigh minor differences between POJOs and `Document`.

### 38.2. `Document` Fits Dynamic Shapes

Aggregations returning variable fields (e.g., pivots or dashboards) fit `Document` well without proliferating one-off POJOs.

### 38.3. POJOs Fit Stable Domain Models

Explicit types enable:

- Compile-time error detection.
- Clean domain validation.
- Safe IDE refactoring.
- Focused unit tests.
- Clear API/service signatures.
- Readable nested structures.

### 38.4. Projections Shrink Payloads

If only two fields are needed, avoid decoding hundreds. Just avoid passing partial POJOs to full entity `replaceOne`.

### 38.5. Benchmark Properly

Measure p50/p95/p99 latency and CPU across:

- Raw `Document` queries.
- Typed POJO queries.
- Small projections.
- Deeply nested arrays.
- 100 concurrent requests.
- Production-like data sizes, indexes, and schemas.

Never claim "POJOs are X% faster" without measuring on your actual workload.

---

## 39. Security and Validation During BSON Mapping

### 39.1. Never Trust User Input

An API converting arbitrary JSON directly into a `Document` for DB updates can let callers overwrite:

- `tenant_id`.
- `role`.
- `is_admin`.
- `balance`.
- `deleted_at`.
- `schema_version`.
- Security flags/metadata fields.

Use allowlisted DTOs and explicit update fields—never pass raw client maps straight to updates or replaces.

### 39.2. User-Supplied Field Names

If a caller submits paths like `"tenant_id"` or `"$where"`, never let them become arbitrary query or update operators. Build safe APIs via strict field allowlists.

### 39.3. Tenant Isolation

~~~java
Filters.and(
    Filters.eq("tenant_id", trustedTenantId),
    Filters.eq("_id", customerId)
);
~~~

`trustedTenantId` must come from the authenticated server context, never from arbitrary request JSON.

### 39.4. Redact Sensitive Fields in Logs

`Document.toJson()` can dump password reset tokens, PII, or payment details. Log only allowlisted fields or redact before logging.

### 39.5. Codecs Are Not Data Encryption

`PojoCodec` and annotations only map fields and types. If encryption is required (CSFLE / Queryable Encryption), configure proper libraries, KMS, and keys—never treat `@BsonIgnore` or `@BsonProperty` as security encryption.

---

## 40. Quick Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Can't find a codec for class Customer` | POJO provider not registered | Add provider to registry |
| `Can't find a codec for class Money` | Nested custom type missing codec | Register custom codec |
| `fullName == null` after find | BSON is `full_name` but annotation missing/wrong | Check raw BSON and mapping |
| `find(eq("fullName", ...))` returns nothing | Wrong BSON field name | Use `full_name` |
| `@BsonProperty` has no effect | Annotation convention disabled | Enable `ANNOTATION_CONVENTION` |
| Cannot instantiate POJO | Missing no-arg constructor / creator | Add public ctor or `@BsonCreator` |
| Private property stays unset | Missing setter / convention | Add JavaBean setter or private-field convention |
| Field lost after `replaceOne` | POJO missing field or partial projection | Use `$set`/DTO/full entity |
| Enum decode failure | DB holds value missing from enum | Migrate data or use fallback codec |
| Integer/Long mismatch | Legacy BSON numeric types differ | Migrate schema / validate types |
| UUID query misses ID | Binary representation mismatch | Verify subtype / config |
| Date timezone drift | Used `LocalDateTime` without zone | Use `Instant`/UTC + business zone |
| Nested POJO fails to map | Nested type lacks codec | Register nested type |
| Unknown field dropped | POJO does not map field | Use `@BsonExtraElements` or migrate |
| JSON right, BSON wrong | Confused Jackson vs. BSON annotation | Separate `@JsonProperty`/`@BsonProperty` |
| Failure after driver upgrade | Version conflict / behavior change | Check dependencies + round-trip tests |
| `@BsonRepresentation` error | Codec does not support representation | Use custom codec or align schema |
| Query ignores index | Index created on Java name, BSON differs | Index the actual BSON field |

---

## 41. POJO Mapping Design Checklist

### 41.1. Model

- [ ] Clear domain classes instead of raw maps everywhere.
- [ ] Valid constructors/getters/setters or `@BsonCreator`.
- [ ] ID maps cleanly to `_id` and BSON type.
- [ ] Null, missing, and default semantics defined.
- [ ] Nested classes, enums, UUIDs, and custom types have codecs.
- [ ] Runtime-only properties excluded from persistence.
- [ ] Java records not misconfigured with mutable POJO assumptions.

### 41.2. Codec

- [ ] `PojoCodecProvider` / classes registered.
- [ ] Default registry retained for built-in types.
- [ ] Registry applied consistently at client/database/collection level.
- [ ] Conventions include annotation processing where required.
- [ ] Custom codecs ordered with proper precedence.
- [ ] No conflicting driver JAR versions on classpath.

### 41.3. Naming

- [ ] Clear policy for Java properties vs. BSON names.
- [ ] `@BsonProperty` applied wherever names differ.
- [ ] `Filters`/`Updates`/`Indexes` use actual BSON keys.
- [ ] HTTP JSON mapping separated from BSON mapping.
- [ ] Dotted paths and array/map keys validated.
- [ ] Shared field constants or schema contracts across services.
- [ ] Migration plan for renaming legacy fields.

### 41.4. Data Correctness

- [ ] Round-trip tests executed against real MongoDB.
- [ ] Raw BSON field names and types verified.
- [ ] Missing, `null`, and zero values tested.
- [ ] Numeric precision / `Decimal128` tested.
- [ ] Timezones and `Date` millisecond precision tested.
- [ ] Legacy documents and unknown fields tested.
- [ ] Partial POJOs never passed to `replaceOne`.
- [ ] Optimistic concurrency implemented where concurrent writers exist.
- [ ] Database schema validation configured appropriately.

### 41.5. Security

- [ ] Tenant ID sourced from trusted context.
- [ ] Input DTOs strictly allowlisted.
- [ ] Arbitrary update fields never exposed.
- [ ] Sensitive fields redacted in logs.
- [ ] Encryption, roles, and permissions enforced independently of POJO codecs.

---

## 42. Hands-On Exercises

### Exercise 1 — Basic Document

Create a `Document` for a customer with `_id`, `full_name`, `loyalty_points`, and `active`. Insert into a lab collection, query by `full_name`, and print `toJson()`.

### Exercise 2 — Nested Document

Create an order with `shipping_address.city` and an `items` array. Use `get("shipping_address", Document.class)` to read the city.

### Exercise 3 — Missing vs. Null

Create two documents: one with `loyalty_points` missing and one explicitly `null`. Check `containsKey`/`get` and compare with MongoDB `$exists`.

### Exercise 4 — BsonDocument Types

Create an `Int32` field and an `Int64` field both holding value `10`. Verify their distinct BSON types.

### Exercise 5 — POJO Codec Registration

Create `Customer` with a public no-arg constructor and getters/setters. Combine `PojoCodecProvider` with the default registry, and insert/fetch via `MongoCollection<Customer>`.

### Exercise 6 — `@BsonProperty`

Map Java property `fullName` to BSON `full_name`. Inspect the raw persisted document to confirm the exact field name.

### Exercise 7 — Query Name Trap

Run both `Filters.eq("fullName", ...)` and `Filters.eq("full_name", ...)`; explain why one query returns no customer.

### Exercise 8 — `@BsonId`

Use an annotated `ObjectId id` and insert when `id` is `null`. Read the generated ID from the result/entity and query by the exact BSON type.

### Exercise 9 — String ObjectId Representation

Create a model with `String id` and `@BsonRepresentation(BsonType.OBJECT_ID)`. Compare raw BSON with a model using `String` ID without that annotation.

### Exercise 10 — `@BsonIgnore`

Add a cache-only property `displayLabelCache`. Verify it does not appear in BSON after insert.

### Exercise 11 — `@BsonCreator`

Create an immutable `CountryCode` with an annotated parameterized constructor. Insert/read it as a nested object and test invariants.

### Exercise 12 — Private Fields Convention

Create a POJO missing a setter for a private field, configure `SET_PRIVATE_FIELDS_CONVENTION`, test decoding, and compare against default conventions.

### Exercise 13 — Java Record

Create a record decoded from BSON using the default registry per record codec docs. Compare with a mutable POJO.

### Exercise 14 — Nested POJO

Create `Order` containing `Address` and `List<OrderItem>`. Register nested codecs properly and read it back.

### Exercise 15 — Enum and Legacy Value

Persist enum `ACTIVE`; insert a document with status `SUSPENDED` absent from the enum. Observe the decode failure and propose a migration.

### Exercise 16 — Unknown Fields

Add `preferred_language` to BSON unknown to an older POJO. Use `@BsonExtraElements` to preserve it.

### Exercise 17 — Null Serialization

Insert a POJO with `Integer loyaltyPoints = null`. Compare raw BSON against a document containing an explicit `null` field.

### Exercise 18 — PATCH vs. Replace

Create a document containing `preferred_language` absent from the POJO. Run `replaceOne` with a partial POJO in the lab and observe the field loss; then use `Updates.set` to update only one field safely.

### Exercise 19 — Decimal128

Store monetary value `123.45` using `Decimal128(BigDecimal)`. Verify it does not turn into `Double`.

### Exercise 20 — Instant Precision

Persist an `Instant` with nanoseconds and read it back. Explain BSON Date precision and how to normalize to milliseconds.

### Exercise 21 — UUID

Create a record with `STANDARD` UUID representation. Inspect the BSON binary subtype and explain risks with legacy representations.

### Exercise 22 — Schema Rename Migration

Migrate `customer_name` to `full_name` using expand/migrate/contract and verify both Java and MongoDB queries.

### Exercise 23 — Optimistic Locking

Add `version`, filter by `_id + version` on update, simulate two concurrent writers, and detect the conflict.

### Exercise 24 — DTO vs. Entity

Design an HTTP DTO with `customerName` while the MongoDB entity uses `full_name`. Show how to keep Jackson and BSON boundaries clean.

### Exercise 25 — Custom Codec

Implement `EmailAddressCodec` encoding/decoding BSON strings and test both valid and invalid emails.

### Exercise 26 — Naming Convention

Design a `snake_case` rule handling `customerName`, `apiURL`, `createdAt`, and `_id`. Add tests ensuring the convention never renames `_id` or overrides explicit annotations.

### Exercise 27 — Partial Projection

Fetch `Customer` with a projection containing only `full_name` and explain why `replaceOne` must not be called with that partial entity.

### Exercise 28 — Data Compatibility

Insert documents where `loyalty_points` is `Int32`, `Int64`, `null`, and missing. Propose schema migration/validation and test POJO decoding.

### Exercise 29 — Security

Design an API allowing users to edit only `full_name`. Prevent request JSON from modifying `tenant_id`, `role`, or `balance`.

### Exercise 30 — Full Integration Lab

Build the `customers` collection, POJO model, registry, indexes, CRUD, versioned updates, raw BSON assertions, migration tests, and cleanup. Never run against production data.

---

## 43. Review Questions

1. How does BSON differ from JSON?
2. What is `Document`?
3. When should you prefer `Document` over a POJO?
4. How does `BsonDocument` differ from `Document`?
5. What is a codec?
6. What is `CodecRegistry` used for?
7. What does `PojoCodecProvider` do?
8. Why doesn't simply creating a Java class enable automatic deserialization?
9. Why must you include the default codec registry?
10. How does `automatic(true)` differ from explicit `register(...)`?
11. Does `MongoCollection<Customer>` automatically translate filter field strings?
12. Which BSON field does `@BsonId` map to?
13. What does `@BsonProperty("full_name")` mean?
14. Should queries use `fullName` or `full_name` when data is stored in `snake_case`?
15. Does `@JsonProperty` change MongoDB BSON field names?
16. Why shouldn't API DTOs and persistence entities be mixed carelessly?
17. Which constructor does the default POJO codec use to instantiate objects?
18. What problem does `@BsonCreator` solve?
19. Which annotations do `@BsonCreator` constructor parameters require?
20. How does `@BsonIgnore` differ from `transient` fields and API privacy controls?
21. What is `SET_PRIVATE_FIELDS_CONVENTION` used for?
22. Why do JavaBean naming conventions matter?
23. How do Java records differ from mutable POJOs?
24. What does `Conventions.DEFAULT_CONVENTIONS` contain?
25. Why does convention ordering matter?
26. How do `ClassModel` and `PropertyModel` differ?
27. When should you use a custom convention instead of `@BsonProperty`?
28. Why must acronyms be handled explicitly when converting `camelCase` → `snake_case`?
29. Can `@BsonRepresentation` convert any arbitrary type?
30. How does a BSON `ObjectId` differ from a string containing `ObjectId` hex?
31. Why can renaming an enum break decoding of older documents?
32. What problem does `@BsonExtraElements` solve?
33. When are unknown fields at risk of being lost?
34. How do missing fields and explicit `null` differ in MongoDB?
35. How can primitive default values mask missing schema fields?
36. How does the default POJO codec serialize `null` properties?
37. Why shouldn't you use `replaceOne` for HTTP PATCH?
38. How does `replaceOne` differ from `Updates.set`?
39. Why shouldn't a partial projection be passed back as a full entity replacement?
40. What data is `Decimal128` suited for?
41. Why is `double` dangerous for money?
42. What precision does BSON Date preserve?
43. How does `Instant` differ from `LocalDateTime`?
44. What errors can a UUID representation mismatch cause?
45. Which codecs does `List<OrderItem>` require?
46. Why must `Map` keys be validated?
47. When do polymorphic POJOs need a discriminator?
48. How does codec registry ordering affect resolution?
49. What are the common causes of `CodecConfigurationException`?
50. Why is raw BSON verification important even if POJO round-trip tests pass?
51. What steps are required in a field-rename schema migration?
52. Which fields belong in a cross-language schema contract?
53. Do POJO codecs generate optimistic concurrency automatically?
54. When do you need a database `$jsonSchema` validator?
55. Does a system using POJOs still need tenant authorization and input allowlisting?

---

## 44. Summary

When accessing MongoDB from Java, data always flows through a conversion layer between **Java objects** and **BSON**. Depending on your needs, use `Document` for flexibility or POJOs for strong typing, stable domain APIs, and maintainable code.

Key takeaways:

1. **`Document` is flexible**, ideal for dynamic schemas and aggregation outputs, but requires runtime type checking.
2. **POJO codecs require configuration**: combine `PojoCodecProvider` with the default `CodecRegistry` and apply it at client, database, or collection level.
3. **Java property names do not automatically equal BSON names**: `@BsonProperty` maps field names; `Filters`, `Updates`, and indexes still reference stored BSON names.
4. **`@BsonId` identifies `_id`**, and `@BsonCreator` enables constructor-based decoding without a no-arg constructor.
5. **Null, missing, default values, and unknown fields are distinct**: never let POJO replacement silently drop unmapped fields.
6. **Nested types, enums, money, dates, and UUIDs require explicit mapping contracts**; never rely on implicit type coercion.
7. **Renaming a field is a schema migration**, not just an annotation edit in code.
8. **Codec registry order matters** when using custom types and custom conventions.
9. **Test both directions and verify raw persisted BSON**, because symmetric mapping mistakes still pass POJO-only round-trip tests.
10. **Security and data validation live outside mapping**: POJOs do not enforce tenant isolation, write privileges, schema invariants, or encryption.

**Final check question:** After renaming a Java property from `fullName` to `displayName`, can the app still read last week's BSON `full_name`, do queries and indexes still align, and do updates preserve new fields added by another service? If you can answer and verify those questions, you truly control your data mapping layer.

## References

- [MongoDB Java Sync Driver — Document Data Format: Documents](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/)
- [MongoDB Java Sync Driver — Document Data Format: POJOs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-pojo/)
- [MongoDB Java Sync Driver — POJO Customization](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/pojo-customization/)
- [MongoDB Java Sync Driver — Document Data Format: Records](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-record/)
- [MongoDB Java Sync Driver — Encode Data with Type Codecs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/codecs/)
- [MongoDB Java Sync Driver — BSON Data Formats](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/)
- [MongoDB Java Sync Driver — Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Update Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Java Sync Driver — Insert Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/insert/)
- [MongoDB Java Sync Driver — BSON Type Mapping](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/bson/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB Manual — Field Names](https://www.mongodb.com/docs/manual/core/dot-dollar-considerations/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Java Driver Javadoc — POJO Codecs](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/bson/org/bson/codecs/pojo/package-summary.html)
