# Mapping ObjectId, UUID, Decimal128, Date/Time, and Null Values in the MongoDB Java Driver

When a Java application persists an object to MongoDB, the driver does not simply convert everything into a JSON string. MongoDB stores data in **BSON (Binary JSON)**, which has distinct types such as `ObjectId`, `Binary`, `Decimal128`, `Date`, and `Null`. Java, meanwhile, has `String`, `UUID`, `BigDecimal`, `Instant`, `LocalDate`, `Date`, and primitive/wrapper types. Mismatched mapping can cause unreadable data, missed indexes, lost monetary precision, shifted timestamps, or confusion between "missing value" and "null value."

This lesson, **"Mapping ObjectId, UUID, Decimal128, Date/Time, and Null Values"**, belongs to the **Java Driver** chapter of the **Database Engine Document MongoDB** module. It focuses on the **MongoDB Java Sync Driver** and BSON codec mechanisms; these BSON principles are equally valuable when using the reactive driver or higher-level frameworks.

Learning objectives:

1. Understand that **BSON type** is part of the data and query-matching criteria.
2. Correctly use `ObjectId`, hex strings, `UUID`, and BSON binary representations.
3. Store exact decimals with `Decimal128`/`BigDecimal` without accidentally passing through `double`.
4. Map BSON Date to `Date`/`Instant` and handle UTC, timezones, and nanosecond/millisecond precision.
5. Distinguish **BSON null**, **missing field**, and **Java null**.
6. Understand how `Document`/`BsonDocument` differs from POJO codecs, and when to configure a codec registry.
7. Verify actual data types before/after saving, write accurate filters/updates, and plan legacy data migrations.

> **Version note:** API names reflect modern MongoDB Java Sync Driver / BSON driver releases. Behavior can vary across Java driver, MongoDB server, codec registry, and framework versions. When using a specific dependency, verify against that exact version's API/docs. Run examples on a lab database rather than mutating production schemas directly.

## 1. Core Difference: JSON Does Not Capture All of BSON

Consider a MongoDB document:

```javascript
{
  _id: ObjectId("65f000000000000000000101"),
  requestId: UUID("b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"),
  price: NumberDecimal("199.90"),
  createdAt: ISODate("2026-11-14T08:15:30.123Z"),
  cancelledAt: null
}
```

Here:

- `_id` is a **BSON ObjectId**, not a 24-character string.
- `requestId` may be **BSON Binary UUID subtype 4**, not a UUID string. Exact encoding depends on client/representation configuration.
- `price` is **BSON Decimal128**, not a Java `double`.
- `createdAt` is **BSON DateTime**, a timestamp in milliseconds since the UTC Unix epoch; MongoDB does not store a timezone name inside the Date type.
- `cancelledAt` is **BSON null** because the field is present with value null.

If `cancelledAt` is completely absent, that represents a different data state.

### BSON Has Types Even When UI Displays Strings

Output in `mongosh` or admin tools may display `ObjectId`, `Date`, and `Decimal128` in human-readable formats. Screen formatting **does not turn them into strings**. Querying with identical characters but a different BSON type can return different results.

Example:

```javascript
// Match BSON ObjectId _id:
db.orders.findOne({
  _id: ObjectId("65f000000000000000000101")
});

// NOT equivalent if _id is actually ObjectId:
db.orders.findOne({
  _id: "65f000000000000000000101"
});
```

MongoDB does not implicitly coerce a hex string into an `ObjectId` during equality comparisons.

## 2. BSON ↔ Java Mapping Overview Table

| Business Meaning | BSON Type | Common Java Type | Notes |
| --- | --- | --- | --- |
| MongoDB-style generated ID | ObjectId | `org.bson.types.ObjectId` | 12-byte BSON, displayed as 24 hex chars |
| Standard UUID | Binary subtype 4 | `java.util.UUID` | Configure `UuidRepresentation.STANDARD` |
| Legacy UUID | Binary subtype 3 | `UUID` with specific legacy representation | Must know source byte-order convention |
| Money / exact decimal | Decimal128 | `org.bson.types.Decimal128` | 128-bit BSON decimal |
| Decimal in Java domain | Decimal128 via codec | `java.math.BigDecimal` | Check Decimal128 representability |
| Point in time | DateTime | `java.util.Date` or `java.time.Instant` | Milliseconds UTC; no zone name stored |
| Calendar date without time | Schema-dependent | `java.time.LocalDate` | Pick explicit convention; do not treat as instant |
| Local date-time | Schema-dependent | `LocalDateTime` | Lacks timezone; requires zone to convert to instant |
| Present null value | Null | `null` / `BsonNull.VALUE` | Must distinguish from absent field |
| Absent field | No BSON element | No key in `Document` | POJO property may still decode as Java `null` |
| 32-bit integer | Int32 | `Integer`/`int` | Distinct from Int64 |
| 64-bit integer | Int64 | `Long`/`long` | Read with matching codec/type |
| Floating point | Double | `Double`/`double` | Unsuitable for exact currency |

**Warning:** This is a common mapping reference, not a guarantee that every codec registry or framework chooses identically. A `Document` decodes values via `DocumentCodec`; a POJO uses `PojoCodec` and per-property codecs. Custom codecs and annotations alter behavior.

## 3. Codecs Bridge BSON and Java Objects

A **Codec** encodes Java objects to BSON and decodes BSON back into Java objects.

```text
Java object
   |
   v
Codec.encode(...)
   |
   v
BSON in MongoDB
   |
   v
Codec.decode(...)
   |
   v
Java object
```

A **Codec registry** is the collection of codecs used by the driver. Familiar classes include:

- `ObjectIdCodec` handles `ObjectId`.
- `UuidCodec` handles `UUID` per `UuidRepresentation`.
- `Decimal128Codec` handles `Decimal128`.
- `BigDecimal` codec can encode to Decimal128 in compatible registries.
- Java date/time codecs handle supported temporal types.
- `DocumentCodec` handles `org.bson.Document`.
- `PojoCodecProvider` supplies codecs for registered or auto-discovered Java classes per config.

Seeing `CodecConfigurationException` on read usually means **no matching codec is registered**, not necessarily database corruption.

### Two Programming Styles

**Working directly with `Document`:**

```java
MongoCollection<Document> collection =
    database.getCollection("orders");
```

The application explicitly chooses which value types to put into `Document` and must read them back with matching types.

**Working with POJOs:**

```java
MongoCollection<OrderRecord> collection =
    database.getCollection("orders", OrderRecord.class);
```

The driver needs codecs able to map the class and its properties. DTOs are strongly typed, yet depend on conventions, annotations, getters/setters, constructors, and the codec registry.

## 4. Setting Up the Hands-On Java Environment

Assumptions:

- Java 17+.
- A lab MongoDB instance reachable via `MONGODB_URI`.
- `org.mongodb:mongodb-driver-sync` dependency at a compatible version.
- Never commit real passwords into repositories or logs.

Connection template:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public class MongoConnectionExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("java_bson_mapping_lab");
            System.out.println(database.getName());
        }
    }
}
```

In subsequent examples, `collection` or `database` comes from an active `MongoClient`. Never reuse a `MongoCollection` after its `MongoClient` has been closed.

## 5. What Is an ObjectId?

**BSON ObjectId** is a **12-byte** BSON identifier, typically displayed as **24 hex characters**. MongoDB can auto-generate an `ObjectId` `_id` on many write paths if omitted; the Java driver can also pre-generate IDs client-side.

```java
import org.bson.types.ObjectId;

ObjectId id = new ObjectId();

System.out.println(id.toHexString());
// Example format: 65f000000000000000000101
```

Each call to `new ObjectId()` generates a fresh value, **not a fixed constant** like an example hex string.

### ObjectId Structure

An `ObjectId` encodes meaningful byte components:

```text
12 bytes:
  4 bytes  timestamp in seconds
  5 bytes  random value unique to process/machine
  3 bytes  counter

Display:
  24 hexadecimal characters
```

An `ObjectId` is not purely random. It embeds a creation timestamp in seconds, yet **it is not a strictly reliable audit timestamp**:

- Client clocks generating IDs can drift.
- Applications can supply pre-built older `ObjectId`s.
- IDs can be instantiated before document insertion.
- It stores neither milliseconds nor timezones.
- `ObjectId` ordering does not always reflect cluster-wide commit/transaction order.

Whenever business logic requires timestamps, store an explicit `createdAt` field.

## 6. Writing and Reading `ObjectId` with `Document`

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.ObjectId;

ObjectId orderId = new ObjectId();

Document newOrder = new Document("_id", orderId)
    .append("orderNo", "ORD-1001")
    .append("status", "NEW");

collection.insertOne(newOrder);

Document found = collection.find(
    new Document("_id", orderId)
).first();

if (found != null) {
    ObjectId storedId = found.getObjectId("_id");
    System.out.println(storedId.toHexString());
}
```

This stays consistent when `_id` truly has BSON type `ObjectId`.

### Mistakenly Reading as String

Avoid:

```java
// Incorrect if _id decodes as ObjectId:
String id = found.getString("_id");
```

`getString()` expects a `String`-compatible value. For `ObjectId`, use `getObjectId()` or retrieve the object and check its type.

### Looking Up by ID from a REST Path

An HTTP path passes a string:

```text
GET /orders/65f000000000000000000101
```

The application must convert it **with validation**:

```java
import org.bson.types.ObjectId;

public static ObjectId parseObjectId(String text) {
    if (text == null || !ObjectId.isValid(text)) {
        throw new IllegalArgumentException("Invalid ObjectId");
    }
    return new ObjectId(text);
}
```

`ObjectId.isValid()` only validates format—**it does not prove the document exists or that the user is authorized to view it**. Authentication, authorization, and tenant/owner filters are still required.

## 7. `_id` Does Not Have to Be an ObjectId

MongoDB permits `_id` to use any supported BSON type (under server rules); collections are not forced to use `ObjectId`. An application might use:

```javascript
{ _id: ObjectId("65f000000000000000000101"), name: "A" }
{ _id: "ORD-1001", name: "B" }
{ _id: NumberLong("1001"), name: "C" }
```

Some systems choose UUIDs as identifiers. **Schema consistency is critical**, because:

```javascript
db.orders.find({ _id: "65f000000000000000000101" })
```

will not match an `ObjectId` `_id` with the same hex characters.

### Never Change ID Types Arbitrarily

If the system currently stores:

```text
orders._id: ObjectId
payments.orderId: ObjectId
```

and new code writes `payments.orderId` as a string, lookups, indexes, and aggregation `$lookup` joins will stop matching.

An ID migration must address **all references**, indexes, URL/API contracts, historical records, and rollback—never simply call `.toString()` in one service.

## 8. ObjectId and POJO Mapping

In a POJO, a property annotated with `@BsonId` maps to `_id`.

```java
import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.types.ObjectId;

public class SimpleOrder {
    @BsonId
    private ObjectId id;
    private String orderNo;

    public SimpleOrder() {}

    public ObjectId getId() { return id; }
    public void setId(ObjectId id) { this.id = id; }

    public String getOrderNo() { return orderNo; }
    public void setOrderNo(String orderNo) {
        this.orderNo = orderNo;
    }
}
```

When POJO codecs are properly configured, `id` ↔ `_id` maps cleanly. Generating `_id` when `null` depends on POJO codec ID generators/conventions. Never assume every custom POJO class auto-generates IDs without valid codecs and conventions.

### Meaning in REST/JSON

An API may serialize `ObjectId` as a **hex string** for frontends:

```json
{
  "id": "65f000000000000000000101",
  "orderNo": "ORD-1001"
}
```

This is an **API representation**, not necessarily the BSON type. When receiving IDs back from clients, parse them to `ObjectId` before querying collections keyed by BSON `ObjectId`.

## 9. What Is a UUID, and Why Do Java ↔ BSON Mappings Often Fail?

`java.util.UUID` represents a 128-bit UUID. However, BSON does not have a dedicated top-level BSON type named UUID the way `ObjectId` is its own type. UUIDs are stored as **BSON Binary** with a subtype and byte order.

Two representation families to distinguish:

- **UUID STANDARD:** BSON Binary **subtype 4**, standard network byte order for UUIDs.
- **UUID LEGACY:** BSON Binary **subtype 3**, carrying historical byte-ordering rules that differed across drivers and platforms.

Java example:

```java
import java.util.UUID;

UUID requestId = UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"
);
```

`UUID.toString()` produces a 36-character `8-4-4-4-12` string. Yet if you call `append("requestId", requestId)` with `STANDARD` encoding, MongoDB stores **Binary subtype 4**, not a 36-character string.

### Two Values That Print Alike May Not Match in Queries

```javascript
{
  requestId: "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"
}
```

is a string.

Whereas:

```javascript
{
  requestId: UUID("b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a")
}
```

is shown in `mongosh` as a standard binary UUID. Equality between BSON String and BSON Binary **never coerces types automatically**.

## 10. Explicitly Configure `UuidRepresentation.STANDARD`

When using UUIDs, configure the representation **deliberately** and consistently across every application.

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.UuidRepresentation;

String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Missing MONGODB_URI");
}

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoCollection<Document> requests = client
        .getDatabase("java_bson_mapping_lab")
        .getCollection("requests");

    // Illustrates client configuration within this scope only.
}
```

With `UuidRepresentation.STANDARD`, the driver encodes `java.util.UUID` as BSON Binary subtype 4 and decodes UUIDs accordingly through matching codecs.

### Why Must It Be Explicit?

In modern Java driver releases, `UNSPECIFIED` is the default to prevent accidentally writing UUIDs with an unintended representation. Encoding a `UUID` without a valid representation throws `CodecConfigurationException` or an equivalent error. This protects against corrupting UUID byte order.

**Do not "fix" it by picking `JAVA_LEGACY` arbitrarily** for new data. `STANDARD` is the standard choice for greenfield multi-language systems; use `LEGACY` only when reading/writing legacy data governed by that contract.

## 11. Writing UUIDs with `Document` and Querying with the Right Type

Using `requests` from a client configured with `STANDARD`:

```java
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.UUID;

UUID requestId = UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"
);

requests.insertOne(new Document("requestId", requestId)
    .append("state", "PENDING"));

Document found = requests.find(
    Filters.eq("requestId", requestId)
).first();
```

The filter passes the `UUID` object directly so the codec encodes it consistently. **Never replace `requestId` with `requestId.toString()`** if the field is stored as BSON Binary UUID: a string will not match binary.

### Inspecting Subtype and Byte Order via `BsonDocument`

```java
import org.bson.BsonBinary;
import org.bson.BsonDocument;
import org.bson.UuidRepresentation;

BsonDocument bson = requests
    .withDocumentClass(BsonDocument.class)
    .find(Filters.eq("requestId", requestId))
    .first();

if (bson != null) {
    BsonBinary raw = bson.getBinary("requestId");
    UUID parsed = raw.asUuid(UuidRepresentation.STANDARD);
    System.out.println(parsed);
}
```

`BsonDocument` exposes exact BSON types, which is invaluable when verifying subtypes. If the subtype or representation mismatches, conversion throws or yields an unexpected UUID.

### Caution with `Document#get()`

How BSON Binary decodes inside `Document` depends on the configured codec/registry; avoid blindly casting `(UUID) document.get("requestId")` without knowing the codec's behavior. To verify subtypes reliably, inspect via `BsonDocument`. When using POJOs with `UUID` properties, keep the registry and `UuidRepresentation` consistent.

## 12. UUID Subtypes 3/4 and Legacy Data Migration

BSON Binary **subtype 3** is the legacy UUID storage format. Legacy representations include variants commonly named:

- `JAVA_LEGACY`.
- `C_SHARP_LEGACY`.
- `PYTHON_LEGACY`.

They differ in byte ordering. **You cannot look at a displayed UUID string alone and prove which representation originally wrote the subtype 3 bytes.**

A system might encounter:

```text
Old Java app
    UUID -> subtype 3 JAVA_LEGACY

New Java app
    UUID -> subtype 4 STANDARD
```

If the same logical UUID exists under two binary representations, equality and index matching treat them as **two distinct values**. Unique indexes enforce uniqueness on the raw BSON values and do not normalize legacy vs. standard UUIDs.

### Safe UUID Migration

1. **Audit:** identify all UUID fields, indexes, binary subtypes, and writers.
2. **Identify sources:** determine which app/driver versions wrote subtype 3.
3. **Choose canonical format:** usually `STANDARD` subtype 4 for new data.
4. **Write representation-aware conversion:** never copy raw 16 bytes directly to subtype 4 assuming the logical UUID stays identical.
5. **Migrate references:** if UUIDs link collections, update all references consistently.
6. **Test against fixtures:** pick known UUIDs written by the legacy app and verify before/after values.
7. **Plan dual-read/dual-write or cutover:** per system contract.
8. **Verify indexes and uniqueness:** prevent logical ID collisions across representations.
9. **Use backups and rollback:** never rewrite binary fields in production without testing.

### When to Store UUIDs as Strings?

Storing strings simplifies certain APIs and tools, provided you:

- Accept the larger storage and index footprint compared to Binary.
- Standardize on lowercase canonical dashed formatting.
- Never mix strings and binary in the same field.
- Remember that equality depends on case sensitivity and collation.

There is no rule requiring every UUID to be Binary. **Consistent schemas across all writers and readers matter far more.**

## 13. How Does ObjectId Differ from UUID?

| Attribute | ObjectId | UUID |
| --- | --- | --- |
| BSON representation | Dedicated `ObjectId` type | Binary subtype 4 / legacy subtype 3 or String per schema |
| Java type | `ObjectId` | `UUID` |
| Base binary size | 12 bytes | 16 bytes |
| Common display | 24 hex chars | 36 dashed chars |
| Embedded timestamp? | Second-resolution timestamp in structure | Standard UUIDs should not be treated as creation timestamps |
| Driver encoding | `ObjectId` codec | `UUID` codec + representation |
| Usable as `_id`? | Yes | Yes, with matching schema/design |
| Migration note | Hex string does not auto-become `ObjectId` | Subtypes 3/4, byte ordering, and String vs. Binary |

`ObjectId` is not a "short UUID," and `UUID` is not an `ObjectId`. Never cast between the two. If a system uses `UUID` for `_id`, choose either BSON binary representation or string and align all queries, indexes, and references.

## 14. Decimal128: Why Use It for Money?

`double` represents numbers in IEEE 754 binary floating-point. Simple base-10 fractions like `0.1` cannot be represented exactly in finite binary, introducing rounding drift when adding, subtracting, or multiplying monetary values.

Java provides `java.math.BigDecimal` for exact decimal math; MongoDB provides BSON **Decimal128** for high-precision decimal storage.

Example:

```javascript
{
  sku: "SKU-A",
  unitPrice: NumberDecimal("199.90"),
  taxRate: NumberDecimal("0.08")
}
```

This is `Decimal128`, not `Double`.

### Key Characteristics

- `Decimal128` supports **up to 34 significant decimal digits** and the IEEE 754 decimal128 exponent range.
- Not every arbitrary `BigDecimal` can be represented exactly in `Decimal128`.
- It supports special decimal128 values such as `NaN` and `Infinity`; monetary domains **must normally reject** those values.
- For money, explicitly define **scale, rounding mode, currency, and invariants**.
- `Decimal128` preserves exact decimal values, but does not replace business rounding policies.

If tracking money in integer minor units (cents/dong) within known bounds, `Long` minor units is also a valid option. There is no rule forcing every price to be `Decimal128`.

## 15. Never Construct BigDecimal from `double`

Java example:

```java
import java.math.BigDecimal;

BigDecimal wrong = new BigDecimal(0.1);
BigDecimal right = new BigDecimal("0.1");
BigDecimal alsoRight = BigDecimal.valueOf(0.1);

System.out.println(wrong);
System.out.println(right);
```

`new BigDecimal(0.1)` captures the **inexact binary approximation** of `double`, producing an unexpected trailing digit expansion. `new BigDecimal("0.1")` represents the exact decimal string.

When ingesting JSON, CSV, or external feeds, parse monetary amounts from **decimal strings** or decimal-aware parsers—never route through an intermediate `double` unnecessarily.

## 16. Writing Decimal128 to MongoDB with `Document`

```java
import java.math.BigDecimal;
import org.bson.Document;
import org.bson.types.Decimal128;

BigDecimal amount = new BigDecimal("199.90");
Decimal128 bsonAmount = new Decimal128(amount);

Document product = new Document("sku", "SKU-A")
    .append("unitPrice", bsonAmount)
    .append("currency", "VND");

products.insertOne(product);
```

Here `products` is a `MongoCollection<Document>` on a lab database.

### Reading It Back

```java
Document found = products.find(
    new Document("sku", "SKU-A")
).first();

if (found != null) {
    Decimal128 value = found.get("unitPrice", Decimal128.class);
    BigDecimal money = value.bigDecimalValue();
    System.out.println(money.toPlainString());
}
```

Call `bigDecimalValue()` only when the `Decimal128` value is finite and convertible. Handle `NaN` or `±Infinity` explicitly; never assume every `Decimal128` converts to a valid domain `BigDecimal`.

### Decimal Strings and Precision

```java
Decimal128 price = Decimal128.parse("199.90");
BigDecimal exact = price.bigDecimalValue();
```

Never call `value.doubleValue()` to convert to `double` and back to `BigDecimal`, as that reintroduces precision loss.

### BigDecimal Exceeding Representable Limits

```java
BigDecimal veryPrecise = new BigDecimal(
    "0.123456789012345678901234567890123456789");

// Decimal128 supports bounded precision and exponent ranges.
// Exact encoding of this value may not be possible.
```

Never assume the driver rounds silently according to your business policy. Validate precision/range and **apply explicit rounding** before persisting when permitted by the domain.

## 17. Does `BigDecimal` in a POJO Always Become Decimal128?

With a compatible Java BSON codec registry, `BigDecimal` encodes to BSON `Decimal128`. However, POJO behavior depends on:

- Active codec registry.
- Java driver/framework version.
- `PojoCodecProvider` and registration.
- Custom codecs/conventions.
- Application precision/rounding rules.

POJO example:

```java
public class Product {
    private String sku;
    private BigDecimal unitPrice;

    public Product() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }
}
```

When both the POJO codec and `BigDecimal` codec are properly registered, `unitPrice` writes as BSON `Decimal128`. **Verify the actual persisted BSON type** rather than relying solely on JSON responses. On `Document` write paths needing zero ambiguity, `new Decimal128(bigDecimal)` makes the BSON type explicit.

## 18. Decimal128 with Queries, Arithmetic, and Indexes

```javascript
db.products.createIndex({ unitPrice: 1 });

db.products.find({
  unitPrice: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("500.00")
  }
});
```

In Java:

```java
import com.mongodb.client.model.Filters;
import java.math.BigDecimal;
import org.bson.types.Decimal128;

products.find(
    Filters.and(
        Filters.gte("unitPrice",
            new Decimal128(new BigDecimal("100.00"))),
        Filters.lt("unitPrice",
            new Decimal128(new BigDecimal("500.00")))
    )
);
```

MongoDB defines cross-type comparison rules across numeric BSON types, yet mixing `Double`, `Decimal128`, `Int32`, and `Int64` makes **precision, aggregation output types, and business behavior** hard to control. For monetary fields, standardize on one type and use matching operand types in queries and updates.

### `$inc` and Addition

```java
import com.mongodb.client.model.Updates;

products.updateOne(
    Filters.eq("sku", "SKU-A"),
    Updates.inc("unitPrice",
        new Decimal128(new BigDecimal("0.10")))
);
```

This shows using a `Decimal128` operand; in real applications, **price updates** also need auditing, optimistic version/concurrency control, and rounding rules. Avoid storing `double` in half the records and `Decimal128` in the rest without a normalization plan.

## 19. Scale and Comparing `BigDecimal`

`BigDecimal.equals()` compares scale as well as value:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
```

In business logic, use `compareTo()` when comparing **numeric value**; if scale itself carries domain meaning (e.g., measurement precision), store or validate scale explicitly.

### Rounding Rules

```java
import java.math.RoundingMode;

BigDecimal subtotal = new BigDecimal("19.995");
BigDecimal rounded =
    subtotal.setScale(2, RoundingMode.HALF_UP);
```

Choosing `HALF_UP` here is **only an example**, not universal for tax, banking, or every currency. Some domains mandate `HALF_EVEN` or jurisdiction-specific rules. Apply rounding policies consistently **before storing `Decimal128`** as well as during Java calculations.

## 20. Date and Time: What Does MongoDB Date Actually Store?

BSON **DateTime** stores a **signed 64-bit integer representing milliseconds since the Unix epoch (UTC)**.

```text
Java Instant: 2026-11-14T08:15:30.123Z
        |
        v
epoch milliseconds (long)
        |
        v
BSON DateTime
        |
        v
mongosh: ISODate("2026-11-14T08:15:30.123Z")
```

The Date type **does not store timezone names** like `Asia/Ho_Chi_Minh` or `Europe/Berlin`, nor does it preserve the original `+07:00` offset. Two timestamps in different timezones representing the **same instant** store the **exact same millisecond value** in BSON Date.

### Same-Instant Example

```text
UTC:     2026-11-14 08:00:00 Z
UTC+07:  2026-11-14 15:00:00 +07:00

Two representations of the exact same instant.
```

Seeing `Z` in `mongosh` does not mean the app "shifted the timezone wrongly"—it is simply **displaying that same instant in UTC**.

## 21. `java.util.Date` and `Instant`

`java.util.Date` is the legacy millisecond-precision instant type; `java.time.Instant` in the modern Java Time API models a point on the UTC timeline and supports sub-millisecond precision.

Conversion example:

```java
import java.time.Instant;
import java.util.Date;

Instant time = Instant.parse("2026-11-14T08:15:30.123Z");

Date legacyDate = Date.from(time);
Instant restored = legacyDate.toInstant();

System.out.println(restored);
```

Java `Date` carries no timezone either. `Date.toString()` formats using the JVM's default timezone for **display**, while the underlying instant remains unchanged.

### Writing Date in a `Document`

```java
import java.time.Instant;
import java.util.Date;
import org.bson.Document;

Instant createdAt =
    Instant.parse("2026-11-14T08:15:30.123Z");

events.insertOne(
    new Document("eventType", "LOGIN")
        .append("createdAt", Date.from(createdAt))
);
```

`Date.from(instant)` is a clear, reliable path when writing BSON DateTime in a `Document`.

### Reading Back as `Instant`

```java
Document event = events.find(
    new Document("eventType", "LOGIN")
).first();

if (event != null) {
    Date date = event.getDate("createdAt");
    Instant instant =
        date == null ? null : date.toInstant();
}
```

Never call `getString("createdAt")` when the field stores BSON DateTime.

## 22. Precision: BSON Date Stores Milliseconds Only

A Java `Instant` can carry nanoseconds:

```java
Instant precise =
    Instant.parse("2026-11-14T08:15:30.123456789Z");

Date encodedDate = Date.from(precise);
Instant roundTripped = encodedDate.toInstant();

System.out.println(roundTripped);
// 2026-11-14T08:15:30.123Z
```

Microsecond/nanosecond digits beyond milliseconds are **not preserved** when converting through BSON DateTime/`Date` this way.

### Why Does This Affect Business Logic?

- Two events 100 microseconds apart end up with identical BSON DateTime values.
- Do not rely solely on millisecond timestamps to establish strict total ordering of high-frequency events.
- Systems needing micro/nanosecond precision may need an extra field like `epochNanos` (within appropriate schema/range bounds) or a logical sequence counter.
- When recording sub-millisecond latencies, never store only BSON DateTime expecting nanoseconds to survive.

If adding a high-precision field, document its unit, overflow limits, and index/query design. Never store epoch nanoseconds in a 32-bit `int`.

## 23. `LocalDate` Is Not an Instant

`java.time.LocalDate` represents a **calendar date** without time-of-day or timezone:

```java
import java.time.LocalDate;

LocalDate birthday =
    LocalDate.of(1995, 7, 21);
```

"Birth date 1995-07-21" is not a UTC millisecond instant. Converting it to UTC midnight can cause users in negative UTC offsets to see the previous day when rendered in local time.

### Two Common Schema Strategies

**A. Store date-only as an explicit ISO string**

```javascript
{
  birthday: "1995-07-21"
}
```

Advantage: unambiguous calendar date with zero timezone shifting as long as the whole system honors the convention. Enforce `YYYY-MM-DD` format and validation since it is stored as a string rather than BSON Date.

**B. Use a `LocalDate` codec/convention**

Some Java time codecs map `LocalDate` to BSON DateTime at UTC start-of-day. That is a **codec convention**, not `LocalDate` magically gaining a timezone. All other APIs/services must share the exact same decode convention.

If local calendar dates are business-critical, document the schema explicitly rather than relying on the Java class name.

## 24. `LocalDateTime` Carries No Timezone

`LocalDateTime` holds a **wall-clock date and time**, without a timezone or offset. For example:

```java
import java.time.LocalDateTime;

LocalDateTime scheduled =
    LocalDateTime.of(2026, 11, 14, 9, 0);
```

This value alone is **insufficient** to determine which UTC instant 09:00 represents. You need a `ZoneId` or offset:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local =
    LocalDateTime.of(2026, 11, 14, 9, 0);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant instant =
    local.atZone(zone).toInstant();
// 2026-11-14T02:00:00Z
```

Here the example uses `Asia/Ho_Chi_Minh` (+07:00 on that date). This illustrates **the rule for converting local wall-clock time to an instant**, not a default timezone to force onto every user.

### When You Need to Remember the Original Timezone

```javascript
{
  scheduledAt: ISODate("2026-11-14T02:00:00Z"),
  timeZone: "Asia/Ho_Chi_Minh",
  localTimeText: "2026-11-14T09:00:00"
}
```

Storing both `scheduledAt` and `timeZone` is essential for scheduling in user timezones, displaying original local times, and handling daylight saving transitions across regions.

Never store only `"2026-11-14T09:00:00"` assuming clients worldwide interpret it as the same instant.

## 25. Java Time Codecs and Choosing the Right Data Type

Depending on your MongoDB Java BSON Driver version and codec registry, codecs for `Instant`, `LocalDate`, and `LocalDateTime` may be registered by default or require explicit setup.

**Never assume "every `java.time` class saves automatically."** Types such as `OffsetDateTime` or `ZonedDateTime` may lack built-in codecs in your active registry or carry semantics requiring explicit conventions.

### Practical Mapping Guide

| Business Concept | Java Type | Clear BSON Schema |
| --- | --- | --- |
| Record creation instant | `Instant` | DateTime |
| Event timestamp | `Instant` | DateTime |
| Date-only birth date | `LocalDate` | ISO date string or explicit convention |
| Scheduled meeting in a timezone | `ZonedDateTime`/`LocalDateTime + ZoneId` | DateTime instant + zone ID |
| Duration | `Duration` | Long milliseconds/microseconds or explicit schema |
| Legacy numeric timestamp | `Long` | Document epoch units clearly and convert |

### Avoid Confusing Seconds and Milliseconds

`Instant.ofEpochSecond(...)` expects seconds; `Instant.ofEpochMilli(...)` expects milliseconds. Passing `Date.getTime()` (milliseconds) to `ofEpochSecond()` corrupts the date by thousands of years.

```java
long epochMillis = 1794644130123L; // example value

Instant correct =
    Instant.ofEpochMilli(epochMillis);

// WRONG when epochMillis is treated as seconds:
// Instant.ofEpochSecond(epochMillis);
```

When receiving timestamps via Kafka, REST, or CSV, name fields explicitly (`epochSeconds`, `epochMillis`, or `epochMicros`).

## 26. Date/Time Queries: Ranges Against BSON DateTime

When `createdAt` stores BSON DateTime:

```javascript
db.events.createIndex({ createdAt: 1 });

db.events.find({
  createdAt: {
    $gte: ISODate("2026-11-14T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
});
```

In Java:

```java
import com.mongodb.client.model.Filters;
import java.time.Instant;
import java.util.Date;

Instant from = Instant.parse("2026-11-14T00:00:00Z");
Instant to = Instant.parse("2026-11-15T00:00:00Z");

events.find(Filters.and(
    Filters.gte("createdAt", Date.from(from)),
    Filters.lt("createdAt", Date.from(to))
));
```

**Half-open intervals `[from, to)`** simplify daily range queries and avoid `"23:59:59.999..."` precision edge cases.

### Querying a Calendar Day in a User's Timezone

To find events occurring on **November 14 in `Asia/Ho_Chi_Minh`**:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;
import java.util.Date;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 14);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

events.find(Filters.and(
    Filters.gte("createdAt", Date.from(start)),
    Filters.lt("createdAt", Date.from(end))
));
```

Benefit: MongoDB compares **UTC instants**, while day boundaries follow the business timezone accurately. In timezones with daylight saving time, a calendar day may be 23 or 25 hours long—so never hardcode adding 86,400 seconds to find the next day.

## 27. Java `null` Is Not the Same as BSON `null`

In Java:

```java
String note = null;
```

is an object reference pointing to nothing. When writing to MongoDB, there are at least **two distinct representations**:

**Field present with BSON null:**

```java
Document a = new Document("name", "A")
    .append("note", null);
```

**Field absent:**

```java
Document b = new Document("name", "B");
```

Both produce:

```java
System.out.println(a.get("note")); // null
System.out.println(b.get("note")); // null
```

Yet:

```java
System.out.println(a.containsKey("note")); // true
System.out.println(b.containsKey("note")); // false
```

**This distinction is crucial when designing APIs, migrations, and validators.**

### BSON Null at the `BsonDocument` Level

```java
import org.bson.BsonDocument;
import org.bson.BsonNull;
import org.bson.BsonString;

BsonDocument explicitNull = new BsonDocument()
    .append("name", new BsonString("A"))
    .append("note", BsonNull.VALUE);

BsonDocument absent = new BsonDocument()
    .append("name", new BsonString("B"));
```

`BsonNull.VALUE` explicitly represents BSON Null. Omitting the key leaves the field absent.

## 28. Querying `null` in MongoDB

Suppose `users` contains:

```javascript
{ _id: 1, nickname: null }
{ _id: 2 }
{ _id: 3, nickname: "An" }
{ _id: 4, nickname: "" }
```

The query:

```javascript
db.users.find({ nickname: null });
```

matches documents where **the field is BSON null OR the field is missing** under MongoDB's null equality semantics; here, `_id: 1` and `_id: 2`.

In Java:

```java
import com.mongodb.client.model.Filters;

users.find(Filters.eq("nickname", null));
```

**Do not use this filter when the business requirement is "only documents where the field exists and equals null."**

### BSON Null Only, Excluding Missing

```javascript
db.users.find({
  nickname: { $type: 10 }
});
```

Type number `10` is BSON Null.

In Java:

```java
import org.bson.BsonType;
import com.mongodb.client.model.Filters;

users.find(Filters.type("nickname", BsonType.NULL));
```

If your driver version has a different overload, construct the BSON filter directly:

```java
users.find(new Document("nickname",
    new Document("$type", 10)));
```

### Field Exists, Regardless of Value

```javascript
db.users.find({
  nickname: { $exists: true }
});
```

Includes fields whose value is `null`, `""`, or any string.

### Missing Field Only

```javascript
db.users.find({
  nickname: { $exists: false }
});
```

In Java:

```java
users.find(Filters.exists("nickname", false));
```

### Field Exists and Is Not Null

```javascript
db.users.find({
  nickname: { $ne: null }
});
```

Under MongoDB semantics, this selects fields with non-null values as appropriate; remember that **empty string `""`**, **`0`**, and **`false`** are all non-null values.

## 29. `null`, Missing, Empty String, and Default Values

| BSON State | Possible Meaning | Java Reading via `Document` |
| --- | --- | --- |
| Field missing | Not provided / not applicable | `get(key)==null`, `containsKey==false` |
| Field = BSON null | Field exists, value unknown/unset | `get(key)==null`, `containsKey==true` |
| Field = `""` | User submitted empty string | Empty `String` |
| Field = `0` | Numeric zero | `Integer`/`Long`/`Decimal128`/... per BSON |
| Field = `false` | Boolean false | `Boolean.FALSE` |
| Field = `[]` | Empty array | Empty `List` or corresponding collection |

In a domain model:

- `middleName: null` may mean "asked and confirmed none."
- Missing `middleName` may mean "older schema never collected it."
- `middleName: ""` may mean "user cleared the input."

Do not collapse these three states if business logic distinguishes them. Likewise, using `0` as a default for a measurement is **not the same** as a missing measurement.

## 30. `Updates.set(field, null)` vs. `Updates.unset(field)`

In the Java Sync Driver:

```java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

// Field exists with value BSON Null:
users.updateOne(
    Filters.eq("_id", 1),
    Updates.set("nickname", null)
);

// Remove the field from the document:
users.updateOne(
    Filters.eq("_id", 1),
    Updates.unset("nickname")
);
```

These are two different operations. For REST PATCH endpoints, explicitly define:

- Field omitted from request → preserve existing value or remove?
- Request sends `"nickname": null` → set BSON null or `$unset`?
- Request sends `"nickname": ""` → is an empty string valid?

**Never implicitly equate Java `null` with `$unset`** unless the API contract specifies it.

## 31. Null in POJOs and Primitive vs. Wrapper Types

Consider a POJO:

```java
public class UserProfile {
    private String nickname;
    private Integer age;
    private int loginCount;

    public UserProfile() {}

    public String getNickname() { return nickname; }
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public int getLoginCount() { return loginCount; }
    public void setLoginCount(int loginCount) {
        this.loginCount = loginCount;
    }
}
```

If BSON `age` is missing or `null`, the Java `Integer` property decodes to `null`. If `loginCount` is missing, primitive `int` defaults to `0`, so the application **cannot tell "missing field" apart from "stored value 0" from the POJO alone**.

### POJO Serialization May Omit Nulls

Depending on conventions, annotations, and codecs, a Java `null` property may be omitted during serialization instead of writing BSON Null. Therefore, never assume:

```text
Java null property -> BSON Null
```

always holds across every POJO codec.

If the schema mandates that a field **be present with BSON null**, check your codec/convention behavior or write explicitly with `Document`/`BsonDocument`. Conversely, if you want nulls omitted, configure conventions/annotations for your version and test actual persisted documents.

## 32. Schema Validation Distinguishes Null and Missing

MongoDB `$jsonSchema` provides:

- `required` to enforce that a field **must exist**.
- `bsonType` to validate the BSON type when the field is present.

Example requiring `nickname` to exist while allowing `null`:

```javascript
db.createCollection("user_profiles", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["userId", "nickname"],
      properties: {
        userId: { bsonType: "string" },
        nickname: {
          bsonType: ["string", "null"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Consider these profiles:

```javascript
{ userId: "U1", nickname: null }
```

**Valid**: the field is present and `null` is an allowed type.

```javascript
{ userId: "U2" }
```

**Invalid**: `nickname` is missing from `required`.

```javascript
{ userId: "U3", nickname: 123 }
```

**Invalid**: `nickname` is numeric, which is not an allowed type.

### Optional Field That Disallows Null

Remove `nickname` from `required` and set `bsonType: "string"`. Then:

- Missing field: valid.
- String value: valid.
- BSON Null: invalid if the field is present.

This expresses a completely different policy.

## 33. `$ifNull` Treats Missing and Null Similarly

In aggregation:

```javascript
db.users.aggregate([
  {
    $project: {
      nicknameSafe: {
        $ifNull: ["$nickname", "(not set)"]
      }
    }
  }
]);
```

`$ifNull` handles both **null and missing/undefined** per operator semantics, which works nicely for uniform UI fallbacks. However, if you need to **count missing fields separately from BSON null**, inspect `$type` explicitly instead of merging them with `$ifNull`.

### Do Not Rely on `$ifNull` to Fix Missing Data Permanently

Fallback values in an aggregation are **computed output**, not persisted updates. To backfill missing fields, run a dedicated migration/update that distinguishes missing vs. null per business rules.

## 34. Extended JSON: Preserving BSON Types During Export/Import

Standard JSON lacks `ObjectId`, `Decimal128`, and `DateTime`. **MongoDB Extended JSON** represents these types cleanly for interchange:

```json
{
  "_id": {
    "$oid": "65f000000000000000000101"
  },
  "requestId": {
    "$binary": {
      "base64": "t/MEcn+9SqGbiiXsvPUiSg==",
      "subType": "04"
    }
  },
  "amount": {
    "$numberDecimal": "199.90"
  },
  "createdAt": {
    "$date": "2026-11-14T08:15:30.123Z"
  },
  "cancelledAt": null
}
```

**Note:** The `$binary` snippet illustrates Extended JSON syntax and subtype; generate and verify base64 from real bytes outside this lesson. Do not rely on an illustrative base64 string as a fixture proving a specific UUID without verifying encoding.

### Difference Between Canonical and Relaxed Forms

MongoDB Extended JSON offers modes to represent BSON types either strictly or human-readably. For instance, DateTime can render as a `$date` ISO string; integers may use `$numberLong` in canonical mode.

If a REST API emits:

```json
{
  "amount": 199.9,
  "createdAt": "2026-11-14T08:15:30.123Z"
}
```

clients may parse `amount` as a JavaScript Number (binary double) and `createdAt` as a string. That is **no longer an end-to-end BSON type mapping**. APIs may intentionally serve consumer-friendly JSON, provided you specify how to parse and validate types when writing back.

## 35. Using `BsonDocument` to Verify Actual Persisted Types

When in doubt about a field:

```java
import org.bson.BsonDocument;
import org.bson.BsonType;

BsonDocument raw = products
    .withDocumentClass(BsonDocument.class)
    .find(new Document("sku", "SKU-A"))
    .first();

if (raw != null) {
    BsonType type = raw.get("unitPrice").getBsonType();
    System.out.println(type);
}
```

If `unitPrice` is BSON `Decimal128`, this prints `DECIMAL128`; if accidentally written as `Double`, you will see `DOUBLE`. Watch out for missing fields: `raw.get("unitPrice")` returns `null`, so check `containsKey` in production before calling `getBsonType()`.

### Checking in `mongosh` with `$type`

```javascript
db.products.aggregate([
  {
    $project: {
      sku: 1,
      storedType: { $type: "$unitPrice" }
    }
  },
  { $limit: 20 }
]);
```

Sample output:

```text
{ sku: "SKU-A", storedType: "decimal" }
{ sku: "SKU-B", storedType: "double" }
{ sku: "SKU-C", storedType: "missing" }
```

This detects BSON-level type drift before planning a migration.

## 36. Complete POJO Codec Registry Setup

The Java Sync Driver uses `PojoCodecProvider` to map Java classes to BSON documents.

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.UuidRepresentation;
import org.bson.codecs.configuration.CodecRegistry;
import org.bson.codecs.pojo.PojoCodecProvider;

import static org.bson.codecs.configuration.CodecRegistries
    .fromProviders;
import static org.bson.codecs.configuration.CodecRegistries
    .fromRegistries;

String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Missing MONGODB_URI");
}

CodecRegistry pojoRegistry = fromRegistries(
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(
        PojoCodecProvider.builder()
            .automatic(true)
            .build()
    )
);

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .codecRegistry(pojoRegistry)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase database = client
        .getDatabase("java_bson_mapping_lab");

    MongoCollection<PaymentRecord> payments =
        database.getCollection("payments", PaymentRecord.class);

    // Use payments while the client remains open.
}
```

In this setup:

- `MongoClientSettings.getDefaultCodecRegistry()` supplies built-in driver codecs.
- `PojoCodecProvider.builder().automatic(true)` enables automatic POJO codecs for matching classes; production apps may prefer explicit class/convention registration.
- `UuidRepresentation.STANDARD` enforces standard UUID representation.
- `getCollection("payments", PaymentRecord.class)` returns a typed collection handle.

### Why Avoid Blindly Using Automatic POJO Codecs for Every Class?

Classes with complex fields/getters, inheritance, immutable constructors, or custom value objects often require explicit codecs, conventions, or annotations. Automatic mapping cuts boilerplate, yet never replaces schema contracts and BSON type tests.

## 37. POJO Combining ObjectId, UUID, BigDecimal, Date, and Nullable Fields

A model illustrating all the types covered:

```java
import java.math.BigDecimal;
import java.util.Date;
import java.util.UUID;
import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.types.ObjectId;

public class PaymentRecord {
    @BsonId
    private ObjectId id;
    private UUID requestId;
    private BigDecimal amount;
    private Date createdAt;
    private Date cancelledAt;
    private String note;

    public PaymentRecord() {}

    public ObjectId getId() { return id; }
    public void setId(ObjectId id) { this.id = id; }

    public UUID getRequestId() { return requestId; }
    public void setRequestId(UUID requestId) {
        this.requestId = requestId;
    }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) {
        this.createdAt = createdAt;
    }

    public Date getCancelledAt() { return cancelledAt; }
    public void setCancelledAt(Date cancelledAt) {
        this.cancelledAt = cancelledAt;
    }

    public String getNote() { return note; }
    public void setNote(String note) { this.note = note; }
}
```

### Persisting the POJO

```java
PaymentRecord payment = new PaymentRecord();
payment.setId(new ObjectId());
payment.setRequestId(UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"));
payment.setAmount(new BigDecimal("125000.50"));
payment.setCreatedAt(
    Date.from(Instant.parse("2026-11-14T08:15:30.123Z")));
payment.setCancelledAt(null);
payment.setNote("Test payment");

payments.insertOne(payment);
```

With an appropriate codec registry, expect:

- `id` → BSON `_id` `ObjectId`.
- `requestId` → UUID Binary `STANDARD` subtype 4.
- `amount` → `Decimal128` via the `BigDecimal` codec.
- `createdAt` → BSON `DateTime`.
- `cancelledAt` and `note` follow the POJO codec's **null serialization policy**, which may omit them rather than writing explicit BSON Null.

**Never assume `null` fields were stored as BSON Null without inspecting the persisted document.** If your schema requires fields to be present even when null, configure codecs/conventions or write explicitly.

### Never Regenerate `_id` During Retries

If a write times out after the server already inserted the document, retrying with a fresh `new ObjectId()` inserts a duplicate document. For idempotency, enforce a unique request ID, reuse the same `_id` on retry, or use conditional upserts by business key.

## 38. Round-Trip Testing on Lab Data

A thorough test verifies both **values and BSON types**:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;

ObjectId id = new ObjectId();
UUID uuid = UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a");
Instant instant =
    Instant.parse("2026-11-14T08:15:30.123Z");
BigDecimal amount = new BigDecimal("100.25");

Document source = new Document("_id", id)
    .append("requestId", uuid)
    .append("amount", new Decimal128(amount))
    .append("createdAt", Date.from(instant))
    .append("cancelledAt", null);

testCollection.insertOne(source);

Document restored = testCollection.find(
    new Document("_id", id)).first();

if (restored == null) {
    throw new AssertionError("Document not found");
}

if (!id.equals(restored.getObjectId("_id"))) {
    throw new AssertionError("ObjectId mismatch");
}

BigDecimal restoredAmount =
    restored.get("amount", Decimal128.class).bigDecimalValue();

if (restoredAmount.compareTo(amount) != 0) {
    throw new AssertionError("Decimal128 mismatch");
}

Instant restoredTime =
    restored.getDate("createdAt").toInstant();

if (!restoredTime.equals(instant)) {
    throw new AssertionError("DateTime mismatch");
}

if (!restored.containsKey("cancelledAt")) {
    throw new AssertionError("Expected explicit BSON null");
}
```

This assumes `testCollection` is a `MongoCollection<Document>` on a client configured with `STANDARD` UUID representation. UUID tests should also inspect `BsonDocument` to confirm the exact subtype and byte order rather than relying solely on `Document#get()`.

### Testing Sub-Millisecond Timestamps

If input `Instant` values carry nanoseconds not divisible by 1,000,000, do not assert strict equality after a BSON DateTime round-trip. Define a **precision policy**: truncate/round to milliseconds, or store an auxiliary field if higher precision is required.

## 39. Migrating Collections with Mixed BSON Types

A collection may accumulate multiple schema generations:

```javascript
// Legacy:
{
  _id: "65f000000000000000000101",
  requestId: "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a",
  amount: 199.9,
  createdAt: "2026-11-14T08:15:30.123Z",
  note: ""
}

// Target:
{
  _id: ObjectId("65f000000000000000000101"),
  requestId: UUID("b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"),
  amount: NumberDecimal("199.90"),
  createdAt: ISODate("2026-11-14T08:15:30.123Z"),
  note: null
}
```

**Never run a blanket migration converting everything solely because values look similar.** Business decisions are required:

- String `_id` may be referenced by external APIs and foreign keys.
- Converting `requestId` between String and Binary UUID affects all writers and indexes.
- `amount` stored as `Double` may already have precision loss that casting to `Decimal128` cannot recover.
- String `createdAt` may contain ambiguous local times or offsets.
- `note: ""` may differ semantically from `note: null`.

### Controlled Migration Steps

1. **Count actual types** using `$type`, broken down by source/version if available.
2. **Define the target schema** with explicit `ObjectId`/UUID/`Decimal128`/Date/`null` mappings.
3. **Define conversion policies** for precision, timezones, and null/missing.
4. **Dry-run on a staging copy** and verify results.
5. **Audit all foreign references** when changing IDs or join keys.
6. **Preserve raw values/audit trails** whenever conversion could lose information.
7. **Ensure all active writers share the target codec registry** before or alongside migration.
8. **Verify uniqueness, indexes, and validators** after type conversion.
9. **Batch, throttle, and make idempotent** so you do not overload production.
10. **Keep backups and rollback plans**, verifying with business queries rather than document counts alone.

For `Decimal128` specifically, converting an existing `double` to `Decimal128` **cannot undo prior binary rounding errors** without an authoritative source of truth.

## 40. Indexes and Equality When Changing BSON Types

Indexes store values along with their exact BSON types. Converting a field from String to `ObjectId` or Binary UUID impacts:

- Equality filters.
- Compound index selectivity.
- Unique constraints.
- Aggregation `$lookup` joins across collections.
- Range queries and sorting.
- Historical records still using older types.

Example:

```javascript
db.payments.createIndex({ orderId: 1 });

// ObjectId orderId:
db.payments.find({
  orderId: ObjectId("65f000000000000000000101")
});

// String orderId with identical characters:
db.payments.find({
  orderId: "65f000000000000000000101"
});
```

These two queries are not equivalent when data contains mixed types.

### Transition Strategy

During migrations, temporary dual-format reads may be necessary, provided you define:

- An explicit end date for compatibility mode.
- Metrics tracking remaining legacy records.
- Tie-breaking policy if both forms exist.
- Permission and performance bounds on broadened queries.

Never leave dual-format schemas in place indefinitely if every query must handle two data types.

## 41. Common Java Driver Errors

| Error / Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `ClassCastException` on `getString("_id")` | Field is BSON `ObjectId`, not String | Use `getObjectId()` |
| Query by hex string returns nothing | `_id` is stored as `ObjectId` | Parse `new ObjectId(hex)` |
| UUID encoding error | `UuidRepresentation.UNSPECIFIED` / missing codec | Configure `STANDARD` or exact legacy representation |
| Decoded UUID differs from written UUID | Legacy subtype/byte-order mismatch | Identify actual subtype and representation |
| UUID string query fails to match | Field is Binary subtype 4 | Query using properly encoded `UUID` |
| `CodecConfigurationException` with POJO | Missing/unrecognized POJO codec | Register `PojoCodecProvider`/conventions |
| `BigDecimal` fails to encode as `Decimal128` | Exceeds precision/exponent bounds | Validate range/scale and rounding policy |
| Monetary rounding drift | Passed through `double` | Parse decimal strings/`BigDecimal`; avoid blind casts |
| `Decimal128.bigDecimalValue()` fails | Special value (`NaN`/`Infinity`) | Reject/handle `NaN`/`Infinity` in domain validation |
| `getDate("createdAt")` returns `null` | Field missing/null or wrong mapping | Inspect BSON type and presence |
| Displayed time shifted by 7 hours | UTC instant rendered in another zone | Separate storage instant from display timezone |
| `LocalDate` shifts back by one day | Stored as UTC midnight then rendered in negative offset | Adopt date-only string or explicit convention |
| Nanoseconds lost | BSON DateTime has millisecond precision | Normalize to ms or add high-precision field |
| `Filters.eq(field, null)` matches missing fields | MongoDB null equality semantics | Use `$type: 10` or `$exists` |
| `Updates.set(field, null)` does not remove field | Setting BSON Null differs from unset | Use `Updates.unset()` to delete fields |
| Null POJO property absent in BSON | Codec/convention omits nulls | Verify serialization policy |
| Primitive `int` becomes `0` | Cannot represent missing/null | Use `Integer` and presence policy |
| Unique index allows two logically identical UUIDs | Different UUID subtypes/representations | Normalize format before/during migration |
| JSON API loses `Decimal128` precision | Serializer emits JSON Number | Use decimal strings or Extended JSON contracts |

## 42. Practice Exercises with Answers

### Exercise 1. ObjectId or String?

A collection has `_id: ObjectId("65f000000000000000000101")`. A Java query runs:

```java
Filters.eq("_id", "65f000000000000000000101")
```

Will it find the document?

**Answer:** No. String and BSON `ObjectId` are distinct types. Parse the hex string into `new ObjectId(...)` and pass the `ObjectId` to the filter.

### Exercise 2. Reading `_id`

`Document.getString("_id")` throws `ClassCastException` even though the document has an ID. Why?

**Answer:** `_id` decoded as `ObjectId`. Call `getObjectId("_id")` or inspect the runtime type before reading.

### Exercise 3. Timestamp Inside ObjectId

Can `ObjectId.getDate()` serve as a millisecond-accurate payment completion timestamp?

**Answer:** No. `ObjectId` timestamps have only 1-second resolution and ID creation time does not necessarily match business completion time. Store a separate `paidAt` BSON DateTime field.

### Exercise 4. UUID Subtype

A Java `UUID` is encoded using `STANDARD`. What BSON binary subtype is expected?

**Answer:** **Subtype 4**. Legacy UUIDs typically use subtype 3 with platform-specific representations.

### Exercise 5. Mismatched UUID Format

`requestId` is stored as BSON Binary UUID, while the API queries with `UUID.toString()`. Why does it fail to match?

**Answer:** The query sends a BSON String against a BSON Binary field. Configure a consistent UUID codec and representation and query with `UUID`.

### Exercise 6. Legacy UUID

A subtype 3 field was written by a legacy driver. Can you simply relabel the subtype byte as 4 without touching the 16 payload bytes?

**Answer:** No. You must know the legacy representation and decode/re-encode the logical UUID properly because byte order differs.

### Exercise 7. BigDecimal

Does `new BigDecimal(0.1)` equal `new BigDecimal("0.1")` in exact decimal value?

**Answer:** No. The `double` constructor captures binary floating-point approximation; construct from decimal strings or exact conversion policies.

### Exercise 8. Decimal128 Precision

A `BigDecimal` has 40 significant digits. Can `Decimal128` store it intact without loss?

**Answer:** No. `Decimal128` holds at most 34 significant decimal digits; validate representability and apply rounding policies.

### Exercise 9. Decimal128 ↔ BigDecimal

Is converting `Decimal128` to `double` and then constructing a `BigDecimal` safe for preserving money?

**Answer:** No. Use `Decimal128.bigDecimalValue()` for finite values and avoid intermediate binary `double`.

### Exercise 10. BigDecimal.equals

Why does `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` return `false`?

**Answer:** `equals()` checks both numeric value and scale. When comparing numeric value alone, use `compareTo() == 0`.

### Exercise 11. Date Timezones

The database stores `ISODate("2026-11-14T08:00:00Z")`; a UTC+07 user sees `15:00`. Did the stored data change?

**Answer:** No. It is the exact same instant rendered in two timezones.

### Exercise 12. LocalDateTime

Does `LocalDateTime.of(2026, 11, 14, 9, 0)` unambiguously identify a UTC instant?

**Answer:** No. It requires a `ZoneId`/offset or explicit convention. For instance, `Asia/Ho_Chi_Minh` resolves it to `02:00` UTC that day.

### Exercise 13. Precision

You write `Instant.parse("2026-11-14T08:15:30.123456789Z")` into BSON DateTime. Are all nanoseconds preserved?

**Answer:** No. BSON DateTime stores milliseconds; sub-millisecond digits are dropped on conversion.

### Exercise 14. Date-Only

Should birth date `1995-07-21` be treated as UTC midnight in every API?

**Answer:** Not by default. It has date-only semantics; store an ISO date string or follow a well-documented convention to avoid timezone shifting.

### Exercise 15. Null Equality

Does `{nickname: null}` in MongoDB match only documents where `nickname` is BSON Null?

**Answer:** No. Under null equality semantics, it also matches documents missing the `nickname` field.

### Exercise 16. BSON Null Only

How do you match documents where `nickname` is BSON Null without matching missing fields?

**Answer:** `{nickname: {$type: 10}}` or in Java `Filters.type("nickname", BsonType.NULL)`.

### Exercise 17. Missing Fields

To find documents lacking `nickname`, use:

```javascript
{ nickname: { $exists: false } }
```

**Answer:** Correct. `$exists: false` differs from null equality.

### Exercise 18. Set vs. Unset

What is the difference between `Updates.set("nickname", null)` and `Updates.unset("nickname")`?

**Answer:** `set` writes BSON Null to the field; `unset` removes the field from the document.

### Exercise 19. `Document.containsKey`

One `Document` has `note: null` and another lacks `note`. Can `get("note")` tell them apart?

**Answer:** No, because both return Java `null`. Check `containsKey("note")` or inspect BSON types.

### Exercise 20. Wrapper Types

A POJO uses primitive `int age`. If `age` is missing in BSON, can you distinguish it from stored `0`?

**Answer:** Not from the primitive alone; it defaults to `0`. Use `Integer` or explicit presence metadata and policy.

### Exercise 21. Validator

A validator specifies `required: ["nickname"]` and `bsonType: ["string", "null"]`. Is a document missing `nickname` valid?

**Answer:** No. `required` demands the field exist; BSON null is permitted, but missing is rejected.

### Exercise 22. Time Ranges

Why do daily event queries normally use `createdAt >= start` and `createdAt < nextDayStart` instead of `<= 23:59:59.999`?

**Answer:** Half-open intervals handle boundaries, precision levels, and timezone-aware calendar day lengths cleanly without assuming a fixed "last millisecond."

### Exercise 23. JSON APIs

A REST API emits `Decimal128` as a JSON number and the frontend parses it into JavaScript `Number`. What is the risk?

**Answer:** Precision loss because JavaScript `Number` is binary floating-point. Prefer decimal strings, Extended JSON, or decimal-aware parsers.

### Exercise 24. Mixed Types

`payments.orderId` contains both `String` and `ObjectId` values. Will a single `ObjectId` filter find all payments?

**Answer:** No. Audit and migrate the schema/references, or use a bounded dual-read transition with a clear retirement date.

### Exercise 25. UUID Round-Trip

A new app wants to migrate from UUID subtype 3 to subtype 4. What minimum checks should tests confirm?

**Answer:** Logical UUID before/after, subtype, byte-order/legacy representation, uniqueness/indexes, foreign references, and compatibility with older writers.

### Exercise 26. Choosing a Data Model

An app stores VND totals like `125000.50`, UTC payment timestamps, and UUID transaction IDs. Pick sensible Java/BSON types.

**Answer:** Use `BigDecimal`/`Decimal128` for money, `Instant`/BSON DateTime for timestamps, `UUID`/Binary subtype 4 `STANDARD` for request IDs, and `ObjectId` for MongoDB `_id` if the schema uses `ObjectId`. Document rounding, currency, timezone, and UUID representation explicitly.

## 43. Production Readiness Checklist

### IDs and UUIDs

- [ ] Verified actual BSON types of `_id` and reference fields.
- [ ] Hex strings parsed to `ObjectId` at the API boundary when schema uses `ObjectId`.
- [ ] Business timestamps stored explicitly rather than relying on `ObjectId` timestamps.
- [ ] `UuidRepresentation` configured explicitly for Binary UUIDs.
- [ ] Subtype 3/4 and byte ordering audited if legacy data exists.
- [ ] UUID Strings and Binary UUIDs never mixed unintentionally.
- [ ] Unique indexes and foreign references verified after any ID migration.

### Decimal128

- [ ] `BigDecimal`/`Decimal128` used per schema; `double` avoided for exact money.
- [ ] `BigDecimal` never constructed unnecessarily from binary `double`.
- [ ] Precision, exponent, and range validated before encoding `Decimal128`.
- [ ] Rounding mode, currency, scale, and `NaN`/`Infinity` handling defined.
- [ ] Numeric types aligned across persisted data, queries, updates, and aggregations.
- [ ] JSON API verified not to lose decimal precision unexpectedly.

### Date and Time

- [ ] BSON DateTime used for UTC epoch-millisecond instants.
- [ ] Sub-millisecond truncation documented when persisting Java `Instant`.
- [ ] Date-only `LocalDate` separated cleanly from instants.
- [ ] `LocalDateTime` never converted to UTC without an explicit `ZoneId`/offset.
- [ ] Original timezone stored separately whenever needed for display/scheduling.
- [ ] Range queries built with timezone boundaries and half-open intervals.
- [ ] Epoch seconds never confused with epoch milliseconds.

### Nulls, Schemas, and Codecs

- [ ] Differences among missing fields, BSON Null, and empty strings clearly defined.
- [ ] `Document.containsKey` or BSON types checked when distinguishing missing vs. null.
- [ ] `Filters.eq(field, null)` matching missing fields accounted for.
- [ ] `Updates.set(..., null)` distinguished from `Updates.unset(...)`.
- [ ] Wrapper types used instead of primitives whenever null/missing must be represented.
- [ ] POJO codec null-omission behavior verified against schema rules.
- [ ] `$jsonSchema` `required` and `bsonType` aligned with data contracts.
- [ ] Codec registry, Java Driver version, and UUID representation documented.
- [ ] Round-trip tests and `$type` checks run on critical BSON fields.
- [ ] Migration, backup, and rollback plans prepared before changing BSON types.

## 44. Summary

**BSON types are part of the data contract** between MongoDB and your Java application. An `ObjectId` is not a 24-character string; a `UUID` can be stored as Binary subtype 4 `STANDARD` or legacy subtype 3 variants, and choosing the wrong representation breaks queries and unique keys even for identical logical UUIDs. `Decimal128` stores high-precision decimals, yet Java `BigDecimal` still requires explicit control of precision, scale, and rounding—routing money through `double` is a classic bug.

For time, BSON DateTime stores **milliseconds since the UTC Unix epoch**, omits timezone names, and truncates `Instant` nanoseconds. `LocalDate` models calendar dates, while `LocalDateTime` cannot define an instant without a timezone. Daily range queries must compute business timezone boundaries rather than slicing timestamp strings.

For empty values, **BSON Null differs from a missing field**. Java `Document.get()` returns `null` for both, so use `containsKey`/`$exists`/`$type` whenever business logic distinguishes them. `Updates.set(field, null)` differs from `unset(field)`, and POJO codecs may omit null properties depending on conventions.

When adopting the Java Driver, define **type mappings at schema design time**, configure codecs and UUID representations explicitly, validate raw persisted BSON with round-trip tests, and govern legacy type migrations carefully. Data is trustworthy only when **storage types, Java types, queries, validators, and API contracts** all align.

### Official References

- [MongoDB Java Sync Driver — BSON and Data Formats](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/)
- [MongoDB Java Sync Driver — POJOs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/pojo-customization/)
- [MongoDB Java Sync Driver — UUIDs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/uuid/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [Java SE — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
