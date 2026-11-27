# BSON Types and Their Corresponding Java Representations

MongoDB stores documents in **BSON (Binary JSON)** format. BSON has more data types than standard JSON: in addition to strings, numbers, booleans, arrays, and objects, it includes `ObjectId`, 32/64-bit integers, `Decimal128`, dates/times, binary data, and several system-oriented types. When using **Spring Data MongoDB**, Java objects are converted to BSON before writing and reconstructed when reading by `MappingMongoConverter` along with related converters/codecs.

Choosing the wrong type can cause loss of monetary precision, integer overflow, mismatched `_id` queries, incorrect time zones, or data being stored differently from the schema expected by the application. This lesson in the **Data Types** chapter builds the foundation for designing fields, queries, indexes, aggregations, transactions, and data testing through `MongoRepository` or `MongoTemplate`.

After this lesson, you will be able to:

- Read a BSON value and choose an appropriate Java type when working with Spring Data MongoDB.
- Distinguish `int32`, `int64`, `double`, `decimal128`, and the precision limits of each type.
- Choose how to store dates/times, `ObjectId`, UUID/Binary, nested documents, and arrays.
- Distinguish **a missing field**, **a field with value `null`**, and **the default value of a Java primitive**.
- Inspect BSON types using `mongosh`, Extended JSON, and `$type`, then compare them with data read through Java.
- Identify places where Spring Data requires explicit annotations or converters.

## 1. BSON, JSON, and Java Objects Are Three Different Representation Layers

A MongoDB document can be described as follows in `mongosh`:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  title: "Java with MongoDB",
  edition: NumberInt(2),
  views: NumberLong("9007199254740993"),
  price: NumberDecimal("129000.50"),
  active: true,
  publishedAt: ISODate("2026-01-15T08:30:00Z"),
  tags: ["java", "mongodb"],
  author: { name: "Lan", country: "VN" }
}
```

This is **MongoDB Shell representation syntax**, not pure JSON. For example, JSON does not have `ObjectId(...)` or `ISODate(...)` functions. When using Java:

1. The application creates objects containing types such as `String`, `Integer`, `Long`, `BigDecimal`, and `Instant`.
2. The Spring Data mapper converts properties to BSON according to default rules and entity metadata.
3. MongoDB stores the BSON values; queries, indexes, and aggregations operate on the **actual BSON types**.
4. When reading, Spring Data converts BSON back into the Java types declared in the domain class.

Do not infer a BSON type from how JSON is displayed in a REST API, logger, or Compass. For example, Java `Long` and `Integer` may both serialize to the same numeric literal in JSON, even though BSON stores them as `long` and `int` respectively.

### Extended JSON (EJSON) for Type-Preserving Transport

Extended JSON uses special markers to represent BSON types in JSON text:

```json
{
  "_id": { "$oid": "665f1f2a4b6c7d8e9f001234" },
  "edition": { "$numberInt": "2" },
  "views": { "$numberLong": "9007199254740993" },
  "price": { "$numberDecimal": "129000.50" },
  "publishedAt": { "$date": "2026-01-15T08:30:00Z" }
}
```

This is an example of **Canonical/Extended JSON**; it does not mean the document stored `$oid`, `$date`, or `$numberLong` as ordinary object fields. These markers describe types when converting BSON to a text representation. `mongosh`, MongoDB Compass, and various import/export tools may display different EJSON formats (such as Relaxed or Canonical). If you use a plain JSON parser that does not understand EJSON, you can mistakenly turn types into nested objects.

## 2. BSON and Java Reference Table

The following table is a **general mapping guide**, not a guarantee that every driver/framework maps identically by default. Spring Data MongoDB, MongoDB Java Driver, POJO codecs, custom converters, and UUID configurations may have different rules.

| BSON Type | Example in mongosh | Common Java Type | Notes |
| --- | --- | --- | --- |
| **String** | `"MongoDB"` | `String` | UTF-8 data; pay attention to collation, search, and length |
| **Boolean** | `true` | `Boolean`, `boolean` | Wrapper allows representing missing/`null` |
| **Int32** (alias `int`) | `NumberInt(42)` | `Integer`, `int` | 32-bit signed integer range |
| **Int64** (alias `long`) | `NumberLong("42")` | `Long`, `long` | 64-bit signed integer range |
| **Double** | `1.25` | `Double`, `double` | IEEE 754 binary floating-point; has decimal representation error |
| **Decimal128** (alias `decimal`) | `NumberDecimal("19.90")` | `BigDecimal`, `Decimal128` | Preserves decimal numbers with up to 34 significant digits; Spring Data may require `@Field(targetType = FieldType.DECIMAL128)` |
| **ObjectId** | `ObjectId("...")` | `org.bson.types.ObjectId`; sometimes `String` with conversion | 12-byte BSON value; the 24-character hex string is only a text representation |
| **Date** | `ISODate("2026-01-15T08:30:00Z")` | `Date`, `Instant` | UTC point in time in milliseconds since epoch; does not preserve original time zone |
| **Timestamp** | BSON timestamp type | `org.bson.BsonTimestamp` (or corresponding driver type) | Consists of time and increment; primarily for internal/oplog mechanisms |
| **Binary** (alias `binData`) | `BinData(...)`, `UUID("...")` | `byte[]`, `org.bson.types.Binary`, `UUID` | Requires consistent subtype/UUID representation |
| **Null** | `null` | `null` of a reference type | Distinct from a missing field and from primitive default values |
| **Array** | `["a", "b"]` | `List<T>`, `Set<T>`, or Java arrays when supported by mapping | Each element can have a different BSON type |
| **Document/Object** | `{ city: "Ha Noi" }` | Nested POJO, `Map<String, ?>`, `Document` | Suitable for nested objects; pay attention to keys and type metadata |
| **Regular Expression** | `/mongo/i` | `Pattern`, `BsonRegularExpression` | BSON regex used for queries; not equivalent to a text index |
| **JavaScript Code** | BSON Code type | `org.bson.types.Code` | Specialized type; generally should not be used in new domain models |
| **MinKey / MaxKey** | `MinKey()` / `MaxKey()` | `org.bson.types.MinKey` / `MaxKey` | Specialized values for comparison/sorting and queries |

Some older BSON types such as **Undefined**, **Symbol**, **DBPointer**, or **JavaScript code with scope** are historical or deprecated/discouraged in new designs. You may encounter them when reading legacy data, but should not introduce them into new domain models without a specific compatibility reason. `DBRef` is a convention for representing references using a special set of fields and should be distinguished from the deprecated BSON **DBPointer** type.

### Choosing Types by Business Need

| Data | Preferred Considerations | Avoid |
| --- | --- | --- |
| Inventory quantity, view count | `int` or `long` if values are integers and within range | `double` for exact counters |
| Currency | Integer in minor units **or** `Decimal128` with explicit rounding rules | `double` for calculations requiring decimal precision |
| Record creation/update timestamp | `Instant`/BSON Date; store instants in UTC | Interpreting a timezone-less date-time string as an arbitrary timestamp |
| Technical identifier | `ObjectId` or UUID per system convention | Mixing String/ObjectId/UUID Binary in the same field |
| Business identifier | `String` with appropriate uniqueness constraints | Assuming hex strings are automatically ObjectId |
| Optional label | Nullable `String`, clear rules for missing/null | Using primitives to detect absence of value |
| Sub-structure belonging to the same aggregate | Bounded embedded document/list | Embedding unboundedly growing arrays |

## 3. Numeric Group: Int32, Int64, Double, and Decimal128

### 3.1. Integer Ranges and Overflow Risk

| Type | Range / Characteristics | Java |
| --- | --- | --- |
| BSON Int32 | From `-2,147,483,648` to `2,147,483,647` | `Integer`/`int` |
| BSON Int64 | From `-9,223,372,036,854,775,808` to `9,223,372,036,854,775,807` | `Long`/`long` |
| BSON Double | 64-bit floating-point; approximately 15–17 significant decimal digits | `Double`/`double` |
| BSON Decimal128 | 128-bit decimal; precision up to 34 significant decimal digits within Decimal128 exponent range | `BigDecimal`/`Decimal128` |

In `mongosh`, when you need to specify exactly which numeric type is written, use BSON constructors:

```javascript
const sample = {
  quantity: NumberInt(125),
  totalViews: NumberLong("9007199254740993"),
  rating: 4.5,
  amount: NumberDecimal("19999999.99")
};
```

The value `9007199254740993` is larger than JavaScript `Number`'s maximum safe integer (`2^53 - 1`). Therefore, pass a string to `NumberLong("...")` rather than creating a JavaScript literal and converting afterward. In Java, `Long` represents this value accurately as long as it remains within the 64-bit range.

If a Java entity uses `int` to read a number from the DB that exceeds the Int32 limit, reading/conversion may fail or produce inaccurate values depending on the conversion path. When a counter can exceed 2.1 billion, consider `long` from the initial design.

### 3.2. Why Not Use `double` for Money?

Many decimal fractions cannot be represented exactly in binary. In Java:

```java
double total = 0.1 + 0.2;
System.out.println(total == 0.3); // false

java.math.BigDecimal correct =
    new java.math.BigDecimal("0.1")
        .add(new java.math.BigDecimal("0.2"));
System.out.println(correct); // 0.3
```

Two common strategies for money:

1. **Store integers in minor units**: for example, `amountMinor = 159900L` for a currency with two decimal places, representing 1,599.00 major units (depending on convention). The application must store `currency` and define the scale for each currency.
2. **Store BSON Decimal128**: suitable when direct decimal operations in MongoDB are needed; when going through Spring Data, use `BigDecimal` combined with metadata or converters to explicitly control the storage type.

Example with Spring Data MongoDB:

```java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Field(targetType = FieldType.DECIMAL128)
private BigDecimal unitPrice;
```

In many Spring Data MongoDB configurations, `BigDecimal` may be represented by default as a **BSON String** to avoid lossy conversions. `@Field(targetType = FieldType.DECIMAL128)` makes it explicit that **BSON Decimal128** should be stored. Decimal128 cannot store every `BigDecimal` of arbitrary precision/scale; check range and rounding rules before writing.

**Another trap:** `new BigDecimal(0.1)` takes the already-rounded binary approximation of `double`. When constructing from decimal constants, use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)`. When aggregating monetary amounts, define scale, rounding mode, and currency policy up front.

### 3.3. Comparison, Addition, and Aggregation

MongoDB supports comparing numeric types against one another in many comparisons/queries, but the results cannot undo precision issues that have already occurred. Arithmetic operations can change types or overflow depending on operators and values. Do not treat "comparable" as evidence that mixing Int32/Int64/Double/Decimal128 in the same business field is fine.

Example checking which BSON type a price field is stored as:

```javascript
db.catalog_items.aggregate([
  { $project: { _id: 0, priceType: { $type: "$unitPrice" } } },
  { $limit: 10 }
]);
```

If a collection contains some documents where `unitPrice` is String and others where it is Decimal128, prioritize **planned data migration and normalization** before writing sum pipelines. A string `"199.90"` does not automatically turn into Decimal128 just because the Java entity declares `BigDecimal`.

## 4. Date and Time: BSON Date vs. BSON Timestamp

### 4.1. BSON Date Carries an *Instant*

MongoDB BSON Date stores a signed count of milliseconds since the Unix epoch `1970-01-01T00:00:00Z`. The value is **a point in time** and does not preserve the time zone entered by the user.

```javascript
const date = ISODate("2026-01-15T08:30:00Z");
db.bson_dates_demo.insertOne({
  createdAt: date,
  description: "Sample date and time"
});
```

In Java, suitable types:

```java
import java.time.Instant;
import java.util.Date;

Instant createdAt = Instant.parse("2026-01-15T08:30:00Z");
Date legacyDate = Date.from(createdAt);
```

`Instant` represents a timezone-independent point in time. If the application receives a `LocalDateTime` such as "15/01/2026 15:30", that is **not enough information** to determine an instant: a zone/offset is required. Java `LocalDateTime` contains no offset, so converting it to BSON Date must follow an explicit policy; different converter versions/configurations may use different timezone rules.

If a use case needs to store a *birthday* or *local holiday*, a BSON Date at UTC midnight might not accurately convey the intended meaning. You can store dates as `YYYY-MM-DD` or a dedicated date structure per the data contract, or use a controlled converter. For scheduled meetings, store the instant and the zone ID when you need to reconstruct the exact local wall-clock time.

**Resolution:** BSON Date has **millisecond** precision. Java's `Instant` can hold nanoseconds; if sub-millisecond precision is needed, writing/reading through BSON Date may lose that extra precision.

### 4.2. BSON Timestamp Is Not a Replacement for `createdAt`

The BSON Timestamp type contains a time component (in seconds) and an incrementing counter. MongoDB uses it in internal mechanisms such as the oplog and replication. Do not use it for ordinary business date-time fields just because it is named "Timestamp". Choose BSON Date for `createdAt`, `updatedAt`, or event timestamps unless there is a specialized reason otherwise.

### 4.3. Java Choices and Risks

| Java Type | Suitable When | Notes |
| --- | --- | --- |
| `Instant` | Exact event instant in UTC | BSON Date has millisecond resolution |
| `java.util.Date` | Compatibility with legacy APIs | Mutable; limit use in new domain models if possible |
| `LocalDateTime` | Local date-time without a zone | Must determine zone when converting to an instant |
| `LocalDate` | Calendar date | Does not imply offset/time zone; requires an explicit storage contract |
| `OffsetDateTime` / `ZonedDateTime` | Need to preserve offset or zone | BSON Date does not keep original zone metadata; use additional fields/converters if needed |

## 5. ObjectId, String ID, and UUID/Binary

### 5.1. ObjectId Is an Independent BSON Type

`ObjectId` is 12 bytes long and is commonly displayed as 24 hexadecimal characters:

```javascript
const id = new ObjectId();
print(id.toHexString());
print(id.getTimestamp()); // Timestamp part in ObjectId
```

The timestamp embedded in an ObjectId has only **second** resolution, and an ID may be generated before the document is persisted. It does not replace an official `createdAt` field.

The following two documents have `_id` values of **different types** even though the characters match:

```javascript
const hex = "665f1f2a4b6c7d8e9f001234";
db.id_type_demo.insertOne({ _id: new ObjectId(hex), kind: "oid" });
db.id_type_demo.insertOne({ _id: hex, kind: "string" });

db.id_type_demo.findOne({ _id: new ObjectId(hex) }); // kind "oid"
db.id_type_demo.findOne({ _id: hex });               // kind "string"
```

With Spring Data MongoDB, you can declare:

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {
    @Id
    private ObjectId id;
    private String name;
}
```

`@Id ObjectId id` maps directly to an ObjectId `_id`. `@Id String id` often follows a rule that converts valid 24-hex strings to ObjectId when possible; therefore, Java `String` **does not automatically guarantee** BSON String. If you always need to keep strings as strings, consider `@MongoId String id` and define an explicit ID generation strategy. The repository's ID generic type must match the declared Java type.

### 5.2. UUID Is Usually Stored as BSON Binary

Conceptually, `java.util.UUID` is not a BSON String by default. Typically, UUIDs are stored as **BSON Binary subtype 4 (standard UUID)** when the driver/codec is configured accordingly. Legacy systems may use subtype 3 variants with different byte ordering.

Before exchanging UUIDs between the Java Driver, Spring Data MongoDB, other services, or migrating data:

- Finalize the storage format: standard BSON Binary UUID or String UUID.
- For BSON Binary, standardize on `UuidRepresentation.STANDARD` (or another representation if legacy compatibility is required) across read/write paths.
- Test write-read round-trips and queries by actual UUID; do not just compare display strings.
- When migrating legacy data, account for both subtype and byte order before converting.

A BSON Binary can also store `byte[]` for small payloads. Do not embed very large files into documents: MongoDB enforces a **16 MiB/document** limit; for large file data, consider GridFS or object storage depending on design.

## 6. Nested Documents, Arrays, Maps, and Enums

MongoDB stores nested object structures as BSON Document, and collections of elements as BSON Array:

```javascript
{
  sku: "BK-101",
  publisher: {
    name: "Example Publisher",
    address: { city: "Ha Noi", country: "VN" }
  },
  tags: ["java", "mongodb"],
  dimensionsCm: [12.5, 18.0, 2.0],
  status: "ACTIVE"
}
```

Java classes can model this:

```java
import java.util.List;
import java.util.Map;

class BookDetails {
    private Publisher publisher;
    private List<String> tags;
    private List<Double> dimensionsCm;
    private Map<String, String> attributes;
    private BookStatus status;
}

class Publisher {
    private String name;
    private Address address;
}

class Address {
    private String city;
    private String country;
}

enum BookStatus {
    ACTIVE, ARCHIVED
}
```

This is a **structural illustration**: for real usage you need constructors/getters/setters or the corresponding Spring Data construction mechanism. Spring Data MongoDB can map plain objects to nested documents, lists to BSON arrays, and enums typically to constant name strings unless a custom converter is configured.

Points to consider:

- **Arrays are ordered**. `List<T>` fits when element order matters; `Set<T>` has set semantics and does not guarantee the same ordering rules as List.
- A BSON array can contain mixed types, whereas a Java domain `List<String>` expects String elements only. Out-of-contract data may cause mapping failures.
- `Map<String, ?>` suits dynamic attributes, but keys must follow BSON and mapper validity/escaping rules. Thoroughly test keys containing dots (`.`), `$` characters, or special field names.
- **Nested documents** are convenient for data sharing a lifecycle that must be updated atomically with the root. Do not embed unboundedly growing lists inside a single document.
- Storing enums as string names is readable, but **renaming an enum constant** can break reading old data; consider converters or stable codes when schema versioning is needed.

## 7. Null, Missing, and Default Primitives

This is one of the subtler bugs when mapping BSON data into Java.

The following three documents carry different meanings:

```javascript
{ _id: 1, note: null }           // Field note exists, value is BSON Null
{ _id: 2 }                       // Field note does not exist
{ _id: 3, note: "" }             // Field note exists, empty string
```

In MongoDB:

```javascript
// Matches both note = null and missing note:
db.notes.find({ note: null });

// Matches only fields with BSON Null value:
db.notes.find({ note: { $type: "null" } });

// Matches only missing fields:
db.notes.find({ note: { $exists: false } });

// Matches all documents that have the note field, including null values:
db.notes.find({ note: { $exists: true } });
```

`$type` in an **aggregation expression** can also return the string `"missing"` when a field path does not exist, whereas the query `$type` operator checks for specific BSON types.

When mapping to Java:

| Java Declaration | Value When MongoDB Field Is Missing (Common) | Risk |
| --- | --- | --- |
| `Integer stock` | `null` | Can represent "unknown" |
| `int stock` | `0` from primitive default value | Hard to distinguish absent data from stock count 0 |
| `Boolean active` | `null` | Represents three-state logic |
| `boolean active` | `false` from primitive default value | Can turn an unset state into false |
| `String note` | `null` | Can lose the distinction between missing and explicit null without separate presence tracking |

Depending on constructors, default field initializers, or custom converters, actual values after reading may differ from the table. Do not treat this table as a contract replacing application mapping tests.

If the application needs to distinguish **missing / null / value**, design the data model explicitly or use field-level update operations and dedicated conversion rules. A Java primitive field cannot carry those three states on its own.

In Spring Data MongoDB, default behavior when writing `null` fields is also influenced by metadata and mapping configuration: a field may be omitted on write or written as BSON Null when configured appropriately. `@Field(write = Field.Write.ALWAYS)` is one way to require writing null values in Spring Data versions that support this attribute; check your project's library version before applying it. To remove a field entirely, use `$unset` rather than assuming `$set: { note: null }` is equivalent.

## 8. Creating a Spring Data MongoDB Entity with Explicit Storage Types

Example of a small invoice document using an ObjectId ID, an integer amount in minor units, and a Decimal128 tax amount:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "bson_invoices")
public class Invoice {
    @Id
    private ObjectId id;

    private String invoiceNo;
    private long subtotalMinor;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal taxAmount;

    private Instant createdAt;
    private List<Line> lines = new ArrayList<>();

    @Version
    private Long version;

    protected Invoice() {}

    public Invoice(
            String invoiceNo, long subtotalMinor,
            BigDecimal taxAmount, Instant createdAt) {
        this.invoiceNo = invoiceNo;
        this.subtotalMinor = subtotalMinor;
        this.taxAmount = taxAmount;
        this.createdAt = createdAt;
    }

    public ObjectId getId() { return id; }
    public String getInvoiceNo() { return invoiceNo; }
    public long getSubtotalMinor() { return subtotalMinor; }
    public BigDecimal getTaxAmount() { return taxAmount; }
    public Instant getCreatedAt() { return createdAt; }

    public static class Line {
        private String sku;
        private int quantity;
        private long unitPriceMinor;

        protected Line() {}

        public Line(String sku, int quantity, long unitPriceMinor) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPriceMinor = unitPriceMinor;
        }
    }
}
```

Repository declaring the matching ID type:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface InvoiceRepository
        extends MongoRepository<Invoice, ObjectId> {
}
```

Writing and reading:

```java
Invoice newInvoice = new Invoice(
    "INV-001",
    125000L,
    new BigDecimal("12500.50"),
    Instant.parse("2026-01-15T08:30:00Z")
);

Invoice saved = invoiceRepository.insert(newInvoice);
Invoice loaded = invoiceRepository.findById(saved.getId())
    .orElseThrow(() -> new IllegalStateException("Not found"));

System.out.println(loaded.getTaxAmount());
```

In BSON, the expected key fields are:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  invoiceNo: "INV-001",
  subtotalMinor: NumberLong("125000"),
  taxAmount: NumberDecimal("12500.50"),
  createdAt: ISODate("2026-01-15T08:30:00Z"),
  lines: [],
  version: NumberLong(0)
}
```

This is an **illustrative result**, not fixed values: ID, version, `_class` field, and numeric rendering may vary by Spring Data/driver configuration. `@Version` supports optimistic locking through write APIs that handle versioning; it does not make every custom update statement check the version automatically.

### When You Want Direct Type Control via the Java Driver

If you use `MongoTemplate` with mapped entities, Spring Data converters are applied. If you use `org.bson.Document` or `BsonDocument` via the lower-level driver, you are explicitly choosing the BSON representation:

```java
import java.math.BigDecimal;
import java.util.Date;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;

Document raw = new Document("_id", new ObjectId())
    .append("invoiceNo", "INV-RAW-001")
    .append("subtotalMinor", 125000L)
    .append("taxAmount", new Decimal128(new BigDecimal("12500.50")))
    .append("createdAt", new Date());
```

`Document` in this example is the MongoDB Java Driver class, **not Spring Data's `@Document` annotation**. `append` builds the client-side document structure; saving requires an appropriate collection/driver connection. With raw write operations, Java entity annotations do not automatically execute as they do through `MappingMongoConverter`.

## 9. Hands-On Practice: Inspecting Each BSON Type with mongosh

Create a dedicated practice collection and attach a marker so you only read/delete data from the current run:

```javascript
use spring_data_training

const lab = db.getCollection("bson_types_lab");
const runId = "data-types-001-" + new ObjectId().toHexString();

const result = lab.insertOne({
  runId: runId,
  textValue: "Hello BSON",
  boolValue: true,
  intValue: NumberInt(123),
  longValue: NumberLong("9007199254740993"),
  doubleValue: 0.1,
  decimalValue: NumberDecimal("0.10"),
  dateValue: ISODate("2026-01-15T08:30:00Z"),
  objectIdValue: new ObjectId(),
  uuidValue: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  nullValue: null,
  numbers: [NumberInt(1), NumberLong("2"), NumberDecimal("3.00")],
  nested: { enabled: true, tags: ["java", "bson"] }
});

printjson(result.insertedId);
```

The command above illustrates a record with multiple types. `UUID(...)` in mongosh creates a standard UUID representation; if you are using an older shell/driver that does not support this syntax, check your version before running or omit the `uuidValue` field. Explicit numeric types are created with `NumberInt`, `NumberLong`, and `NumberDecimal` to avoid JavaScript literal inference.

### 9.1. Using `$type` to Inspect BSON Types

```javascript
lab.aggregate([
  { $match: { _id: result.insertedId, runId: runId } },
  {
    $project: {
      _id: 0,
      textType: { $type: "$textValue" },
      boolType: { $type: "$boolValue" },
      intType: { $type: "$intValue" },
      longType: { $type: "$longValue" },
      doubleType: { $type: "$doubleValue" },
      decimalType: { $type: "$decimalValue" },
      dateType: { $type: "$dateValue" },
      objectIdType: { $type: "$objectIdValue" },
      uuidType: { $type: "$uuidValue" },
      nullType: { $type: "$nullValue" },
      missingType: { $type: "$notPresent" },
      arrayType: { $type: "$numbers" },
      nestedType: { $type: "$nested" }
    }
  }
]).toArray();
```

Expected values for these fields are: `string`, `bool`, `int`, `long`, `double`, `decimal`, `date`, `objectId`, `binData`, `null`, `missing`, `array`, and `object`. Note that `double` here is a **BSON type name**, not evidence that related arithmetic has the same precision as Decimal128.

### 9.2. Filtering by Exact BSON Type

```javascript
lab.find({
  runId: runId,
  decimalValue: { $type: "decimal" }
}).toArray();

lab.find({
  runId: runId,
  nullValue: { $type: "null" }
}).toArray();

lab.find({
  runId: runId,
  notPresent: { $exists: false }
}).toArray();
```

For arrays, the query `$type` operator can inspect elements inside an array in certain cases, whereas aggregation `$type` applies to the **expression value** and returns the type of the array itself. Therefore, when you want to know specifically whether a field is an Array or the type of each element, express the goal clearly and pick the appropriate expression.

### 9.3. Exporting Extended JSON and Comparing

```javascript
const doc = lab.findOne({ _id: result.insertedId, runId: runId });
print(EJSON.stringify(doc, null, 2, { relaxed: false }));
```

Canonical Extended JSON preserves markers for Int32/Int64/Date/Decimal128, which is useful when reconciling types with data read through Java. Even so, you must use an EJSON parser to reconstruct the corresponding types; an ordinary JSON parser does not understand that `{"$numberLong":"..."}` represents Int64.

After observing the results, clean up **only the record from the current run**:

```javascript
lab.deleteOne({ _id: result.insertedId, runId: runId });
```

Do not run `deleteMany({})` or `drop()` on other collections unless you are certain who owns the data.

## 10. BSON Types in Queries, Indexes, and Validators

### 10.1. Type Consistency Matters More Than Display Format

Suppose a collection stores `customerId` as both String `"665f..."` and ObjectId with the same characters. A query `{ customerId: ObjectId("...") }` does not automatically match the corresponding String, and adding an index will not resolve this.

To establish a stable data contract, you should:

1. Define the BSON type of every critical field at design time.
2. Choose the matching Java type, Spring Data annotation, or custom converter.
3. Audit older documents before changing schemas/types to avoid having multiple representations in the same field.
4. Create indexes aligned with actual queries and inspect `explain("executionStats")`.
5. Use validators when you want the database to reject structurally invalid documents.

### 10.2. MongoDB JSON Schema Validation Checks BSON Types

Example creating a **new collection dedicated to the validator exercise**:

```javascript
db.createCollection("typed_products_lab", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "stock", "price"],
      properties: {
        sku: {
          bsonType: "string",
          description: "sku must be String"
        },
        stock: {
          bsonType: "int",
          minimum: 0,
          description: "stock must be non-negative Int32"
        },
        price: {
          bsonType: "decimal",
          description: "price must be Decimal128"
        }
      }
    }
  }
});
```

From there, write with the right types:

```javascript
db.typed_products_lab.insertOne({
  sku: "SKU-01",
  stock: NumberInt(8),
  price: NumberDecimal("199.90")
});
```

If you write `price: "199.90"` as a String or `stock: "8"` as a String, the validator rejects it when validation is enforced (according to the validation level/action settings). A unique index enforces value **uniqueness**, while a validator checks **types and structure**; they solve two different requirements.

The `createCollection` example only runs if the collection name does not already exist. This is a design pattern, not an instruction to create a validator on a live production collection. With Spring Data MongoDB, Java annotations do not automatically replace a full MongoDB JSON Schema validator; you need a separate schema/index management process per project.

### 10.3. Diagnosing with Aggregation

To determine whether a monetary field has mixed types, group by BSON type:

```javascript
db.catalog_items.aggregate([
  {
    $group: {
      _id: { $type: "$unitPrice" },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
```

The results can reveal whether the collection contains `decimal`, `double`, `string`, or `missing`. This is a diagnostic step before deciding on a migration. Do not blindly run `$toDecimal` across all strings without first handling malformed values, scale, and rounding rules.

## 11. Common Pitfalls and How to Investigate

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| Monetary calculation `0.1 + 0.2` differs from `0.3` | Double is binary floating-point | Use minor-unit integers or Decimal128/BigDecimal per currency contract |
| Very large Long values change when passing through JSON/JavaScript | JavaScript Number is exact only for integers within the safe range | Use NumberLong from string, EJSON/codec that understands Int64 |
| `BigDecimal` stored as String | Default mapping rule or converter | Check `$type`, use `@Field(targetType = FieldType.DECIMAL128)` |
| `_id` query does not match | BSON ObjectId compared against BSON String | Inspect actual type, pick `@Id`/`@MongoId` and convert properly |
| UUID reads back differently than expected | Inconsistent subtype/UUID representation | Standardize representation; check subtype and byte order |
| Date-time field is off by 7 hours | Misinterpreting LocalDateTime and time zones | Store UTC Instant; store zone separately if local time reconstruction is needed |
| Timestamp loses nanosecond part | BSON Date only has millisecond precision | Choose suitable data precision or design supplementary storage |
| Cannot distinguish missing from `null` | Java reference null or `{ field: null }` query merges both cases | Use `$exists`, `$type`, and an explicit three-state model |
| Primitive `int` receives 0 even when field was omitted | Java primitive default | Use `Integer` when you need to distinguish "no value" |
| Legacy enum can no longer be read | Renamed enum constant while DB stores String name | Use stable code values or custom converter and migration |
| Nested/list data conversion error | BSON element type does not match Java generic type | Inspect data with `$type`, standardize schema and converters |
| Comparisons or aggregations return confusing results | Same field name holds multiple BSON types | Group by `$type`, fix data, and add a validator |

When diagnosing, start from the **actual BSON document** using `mongosh` or Compass. Then check Java metadata, active converters, and the actual write path (Spring Data repository/template vs. direct Java Driver). Identical JSON from a REST API does not prove two documents store the same BSON type.

## 12. Hands-On Exercises

**Exercise 1 — Type Classification.** Given a document with `qty: NumberInt(7)`, `views: NumberLong("9007199254740993")`, `price: NumberDecimal("15.75")`, and `createdAt: ISODate(...)`, write a mapping table pairing each BSON type with an appropriate Java type. Explain why `views` should not be read into an `int`.

**Exercise 2 — Money and Precision.** Create a `Product` entity with `quantity`, `price`, and `createdAt`; choose a money storage approach (minor units or Decimal128), and specify currency, scale, and rounding rules. Use `mongosh` to verify the `$type` of the `price` field.

**Exercise 3 — ObjectId and String.** Create two documents whose `_id` values share the same hex characters but have different BSON types. Write two queries to match each document accurately; choose between `@Id String` and `@MongoId String` if the application must always keep the ID as a string.

**Exercise 4 — Null or Missing.** Create three documents with `note: null`, missing `note`, and `note: ""` respectively. Write three filters to match each group accurately; test mapping into `String` and describe what information is lost if you only look at the Java object.

**Exercise 5 — Date and Zone.** A customer in the `Asia/Ho_Chi_Minh` time zone schedules an appointment at 15:00 on 2026-11-20. Calculate the corresponding UTC instant, store it as a BSON Date, then explain how to reconstruct the display time and why the zone ID must be preserved when business logic requires it.

**Exercise 6 — UUID.** Write a UUID as BSON Binary subtype 4 using appropriate driver configuration and read it back as Java `UUID`. Compare it with another document storing the same UUID as a BSON String, then explain why queries cannot treat the two storage formats as equivalent.

**Exercise 7 — Detecting Schema Drift.** On a test collection, insert `unitPrice` values in three forms: `String`, `Double`, and `Decimal128`. Use an aggregation with `$type` to summarize them, propose a safe migration, and define a validator to block mistyped data in the future.

### Key Takeaways

**BSON types are MongoDB's actual data contract.** Java has corresponding types, but conversion depends on Spring Data MongoDB, drivers, annotations, and converters. Proactively choose Int32/Int64, Decimal128, Date/Instant, ObjectId, and UUID/Binary based on business requirements; distinguish missing from null, avoid mixing types in the same field, and always verify with `$type` or Extended JSON before concluding that data is stored correctly.
