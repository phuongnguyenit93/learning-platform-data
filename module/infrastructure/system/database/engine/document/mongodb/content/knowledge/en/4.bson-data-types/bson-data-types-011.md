# Reading and Writing Extended JSON Without Losing BSON Type Information

## 1. The Problem: JSON Looks Like BSON, Yet Lacks Sufficient Type Metadata

MongoDB stores documents in **BSON (Binary JSON)** format. BSON represents document and array structures much like JSON, while adding numerous value types with distinct semantics and handling rules: **ObjectId**, **Date**, **Int32**, **Int64**, **Double**, **Decimal128**, **Binary**, **Timestamp**, **Regular Expression**, and several specialized types.

Standard JSON has only objects, arrays, strings, numbers, booleans, and null. It **has no standard syntax** to distinguish 32-bit integers from 64-bit integers, double-precision floats from Decimal128, or character strings from BSON dates.

Suppose the database contains this document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberInt(12),
  sequence: NumberLong("9007199254740993"),
  unitPrice: NumberDecimal("19.99"),
  createdAt: ISODate("2024-01-01T00:00:00.000Z")
}
~~~

This is **`mongosh` value representation syntax**, not valid JSON text. If you flatten the document into plain JSON like this:

~~~json
{
  "_id": "507f1f77bcf86cd799439011",
  "quantity": 12,
  "sequence": 9007199254740993,
  "unitPrice": 19.99,
  "createdAt": "2024-01-01T00:00:00.000Z"
}
~~~

the payload becomes easier to read, yet loses critical information:

- **_id** becomes a plain string; nothing indicates it was an ObjectId.
- **quantity** becomes a plain JSON number; the Int32 tag is gone.
- **sequence** is a JSON number too large for JavaScript's `Number` type to represent accurately; passing through certain systems can round the value.
- **unitPrice** loses its Decimal128 type and may pass through binary floating-point arithmetic, introducing rounding error.
- **createdAt** becomes a string; standard JSON parsers do not instantiate a BSON Date.

This problem is especially severe in **export/import** pipelines, data transfer between Java and JavaScript, saving JSON files for re-import, event messaging over queues, and data migrations.

**MongoDB Extended JSON (EJSON)** solves this with **type wrappers** whose key names start with **`$`**. Type wrappers preserve the original value semantics when converting between BSON and JSON text.

## 2. What Is Extended JSON v2?

**Extended JSON v2** is a convention for representing BSON values as syntactically valid JSON text so MongoDB tools and drivers can reconstruct the matching types. Example:

~~~json
{
  "_id": { "$oid": "507f1f77bcf86cd799439011" },
  "quantity": { "$numberInt": "12" },
  "sequence": { "$numberLong": "9007199254740993" },
  "unitPrice": { "$numberDecimal": "19.99" },
  "createdAt": {
    "$date": { "$numberLong": "1704067200000" }
  }
}
~~~

Each wrapper carries explicit meaning:

- **$oid:** a 12-byte ObjectId represented as 24 hexadecimal characters.
- **$numberInt:** a 32-bit signed integer.
- **$numberLong:** a 64-bit signed integer.
- **$numberDecimal:** a Decimal128 decimal number.
- **$date:** a BSON Date; the canonical form above holds epoch milliseconds inside **$numberLong**.

The quoted numeric strings inside wrappers are intentional. For instance, **"9007199254740993"** is kept as a string to prevent JSON parsers from rounding it via `Number` before constructing Int64.

### 2.1. The Two Standardized Modes

EJSON v2 defines two primary modes:

| Mode | Goal | Level of BSON Type Preservation | Use Cases |
|---|---|---|---|
| **Canonical Extended JSON** | Express BSON types explicitly so data can round-trip. | Highest of the two modes; still subject to a few spec exceptions/limits. | Type-preserving data exchange, migrations, test fixtures, type auditing. |
| **Relaxed Extended JSON** | Compact, human-readable, close to plain JSON. | Can lose Int32/Int64/Double distinctions and lose precision when plain JSON numbers pass through unsupported parsers. | Logs/display, API exchanges where schemas predefine types and accept conversion. |

**Canonical** prioritizes type fidelity. **Relaxed** prioritizes convenience and readability. Both modes produce **syntactically valid JSON**, yet only an EJSON-aware parser reconstructs BSON values from the special wrappers.

### 2.2. Canonical vs. Relaxed for the Same Document

Canonical:

~~~json
{
  "count32": { "$numberInt": "42" },
  "count64": { "$numberLong": "42" },
  "ratio": { "$numberDouble": "2.5" },
  "cost": { "$numberDecimal": "12.50" },
  "createdAt": { "$date": { "$numberLong": "1704067200000" } },
  "_id": { "$oid": "507f1f77bcf86cd799439011" }
}
~~~

Relaxed:

~~~json
{
  "count32": 42,
  "count64": 42,
  "ratio": 2.5,
  "cost": { "$numberDecimal": "12.50" },
  "createdAt": { "$date": "2024-01-01T00:00:00Z" },
  "_id": { "$oid": "507f1f77bcf86cd799439011" }
}
~~~

In the relaxed output, both **count32** and **count64** become **42**. From the plain JSON number `42`, a parser cannot tell whether the original type was Int32 or Int64. Meanwhile, **Decimal128** and **ObjectId** still require wrappers in both modes.

**Practical rule:** if the requirement is "read and write without losing BSON type information," choose **Canonical EJSON** and use an **EJSON-aware reader/writer** on both sides.

## 3. Representation Table for Key BSON Types

The table below focuses on **Extended JSON v2**. Examples are written as standalone JSON values to highlight the wrappers clearly.

| BSON Type | Canonical EJSON | Relaxed EJSON | What Easily Breaks on Wrong Conversion |
|---|---|---|---|
| **ObjectId** | **{"$oid":"507f1f77bcf86cd799439011"}** | Same as canonical. | Downgraded into a 24-character string. |
| **Int32** | **{"$numberInt":"42"}** | **42** | Loses explicit 32-bit integer type metadata. |
| **Int64** | **{"$numberLong":"42"}** | **42** | Loses explicit 64-bit integer metadata; large integers risk rounding. |
| **Double** | **{"$numberDouble":"2.5"}** | **2.5** | Cannot be distinguished reliably from other numeric types if parser infers types. |
| **Decimal128** | **{"$numberDecimal":"19.99"}** | Same as canonical. | Converting to `Number` risks losing decimal precision. |
| **Date** | **{"$date":{"$numberLong":"1704067200000"}}** | **{"$date":"2024-01-01T00:00:00Z"}** | Confused with a plain string if wrapper is stripped. |
| **Binary** | **{"$binary":{"base64":"AQIDBA==","subType":"00"}}** | Same as canonical. | Loses raw bytes and/or subtype if reduced to a base64 string. |
| **Timestamp** | **{"$timestamp":{"t":1704067200,"i":1}}** | Same as canonical. | Confused with BSON Date or a plain nested object. |
| **Regex** | **{"$regularExpression":{"pattern":"^VIP","options":"i"}}** | Same as canonical. | Loses regex semantics and flags. |
| **MinKey** | **{"$minKey":1}** | Same as canonical. | Loses the lowest sentinel type in BSON sort order. |
| **MaxKey** | **{"$maxKey":1}** | Same as canonical. | Loses the highest sentinel type in BSON sort order. |

Types like **boolean**, **string**, **null**, and plain arrays/documents can use native JSON syntax. However, if nested arrays or documents contain specialized BSON types, wrappers must be preserved **recursively** at those positions.

### 3.1. ObjectId Differs from a 24-Character String

~~~json
{
  "mongoId": { "$oid": "507f1f77bcf86cd799439011" },
  "plainText": "507f1f77bcf86cd799439011"
}
~~~

Both look similar, yet **mongoId** has type ObjectId while **plainText** has type string. If Java or MongoDB queries an ObjectId **`_id`** field with a plain string supplied by the app, matching results will fail to align.

### 3.2. Int32, Int64, and Double Are Three Distinct Types

~~~json
{
  "a": { "$numberInt": "7" },
  "b": { "$numberLong": "7" },
  "c": { "$numberDouble": "7.0" }
}
~~~

In plain JSON, all three might be handled generically as numbers. In BSON, they carry **three different type tags**. This directly impacts schemas, Java mappings, `$type` checks, and data exchange.

Specifically, JavaScript `Number` only represents integers accurately **from `-(2^53 - 1)` to `+(2^53 - 1)`**. 64-bit integers can fall outside this range.

~~~javascript
// Run in a JavaScript environment:
Number.MAX_SAFE_INTEGER                 // 9007199254740991
Number("9007199254740993")              // may become 9007199254740992
Number.isSafeInteger(9007199254740993)  // false
~~~

Once a digit sequence has been rounded by a parser, adding **`$numberLong`** afterward **cannot recover the lost digits**. Keep the data in canonical format before any precision-losing parse step occurs.

### 3.3. Decimal128 Is for Decimal Values Requiring Precision

~~~json
{
  "price": { "$numberDecimal": "19.99" },
  "interestRate": { "$numberDecimal": "0.012500" }
}
~~~

**Decimal128** is essential for prices, currency, measurements, and decimals needing higher precision than binary floating-point. Do not convert it to double just to shorten JSON. Java applications should use compatible types such as **`Decimal128`** or controlled conversions to **`BigDecimal`** per the data contract.

### 3.4. Date Is an Instant; Strings Can Hold Many Other Formats

~~~json
{
  "asDate": { "$date": "2024-01-01T00:00:00Z" },
  "asString": "2024-01-01T00:00:00Z"
}
~~~

**asDate** is converted by an EJSON parser into a BSON Date, while **asString** remains a string. BSON Date stores **milliseconds since the Unix epoch**, without storing the user's input timezone. Two timestamps with different offsets representing the same instant store the exact same point in time; **original timezone metadata** needs a separate field if the business must retain it.

Canonical Date uses:

~~~json
{ "$date": { "$numberLong": "1704067200000" } }
~~~

Relaxed Date typically uses ISO-8601 when the instant falls within the supported range. For dates outside the relaxed representation range (such as prior to 1970), exporters may fall back to canonical epoch milliseconds.

### 3.5. Binary Must Preserve Both Bytes and Subtype

~~~json
{
  "rawData": {
    "$binary": {
      "base64": "AQIDBA==",
      "subType": "00"
    }
  },
  "uuidAsBinary": {
    "$binary": {
      "base64": "OyQRAeK7QlWMr0E2xWapYg==",
      "subType": "04"
    }
  }
}
~~~

Base64 encodes **bytes**, not original plain text. The **subType** field is part of the BSON binary type metadata:

- **00** is typically used for generic binary.
- **04** is used for UUID in the standard format.

EJSON also defines a convenient UUID shorthand:

~~~json
{ "$uuid": "3b241101-e2bb-4255-8caf-4136c566a962" }
~~~

Compliant EJSON parsers convert this wrapper into **BSON binary subtype 04**. Never arbitrarily turn every binary field into a UUID or swap subtypes `03`/`04` without knowing the legacy representation and driver UUID configuration; **having 16 bytes** alone is not enough to determine the intended UUID semantics.

### 3.6. Timestamp Is Not Date

~~~json
{
  "createdAt": { "$date": "2024-01-01T00:00:00Z" },
  "opTime": { "$timestamp": { "t": 1704067200, "i": 1 } }
}
~~~

**Date** is milliseconds since epoch. **BSON Timestamp** pairs a time component (**t**) and an increment counter (**i**) with dedicated semantics, typically found in internal mechanisms such as replication/oplog. Never convert **Timestamp** to Date when the application requires preserving the BSON type.

### 3.7. Double with NaN and Infinity

Standard JSON has no **`NaN`**, **`Infinity`**, or **`-Infinity`** literals. Extended JSON uses:

~~~json
{
  "notANumber": { "$numberDouble": "NaN" },
  "positiveInfinity": { "$numberDouble": "Infinity" },
  "negativeInfinity": { "$numberDouble": "-Infinity" }
}
~~~

Even in relaxed mode, non-finite values still require wrappers. Furthermore, for certain floating-point payloads, preserving **type** does not automatically guarantee bit-for-bit preservation of every exotic hardware representation; when byte-for-byte fidelity is required, work directly with BSON and its specification.

## 4. A Complete Canonical EJSON Document

This example can serve as a file payload transferred between systems:

~~~json
{
  "_id": { "$oid": "507f1f77bcf86cd799439011" },
  "orderCode": "ORD-0007",
  "tenantId": "TENANT-A",
  "quantity": { "$numberInt": "2" },
  "sequence": { "$numberLong": "9007199254740993" },
  "unitPrice": { "$numberDecimal": "129.9900" },
  "discountRate": { "$numberDouble": "0.125" },
  "paid": false,
  "createdAt": {
    "$date": { "$numberLong": "1704067200000" }
  },
  "receiptBytes": {
    "$binary": { "base64": "AQIDBA==", "subType": "00" }
  },
  "tags": ["new", "priority"],
  "warehouseStock": [
    { "warehouse": "HN", "units": { "$numberInt": "12" } },
    { "warehouse": "HCM", "units": { "$numberInt": "8" } }
  ],
  "fulfillment": null
}
~~~

When parsed by an EJSON-aware parser, we recover:

| Field | Target BSON Type |
|---|---|
| **_id** | ObjectId |
| **orderCode**, **tenantId**, **tags[]** | String |
| **quantity**, **warehouseStock[].units** | Int32 |
| **sequence** | Int64 |
| **unitPrice** | Decimal128 |
| **discountRate** | Double |
| **paid** | Boolean |
| **createdAt** | Date |
| **receiptBytes** | Binary subtype 00 |
| **fulfillment** | Null |

An EJSON-unaware reader treats **`{"$numberLong":"9007199254740993"}`** as a plain object containing a key named **`$numberLong`**, rather than an Int64. Thus, **having valid JSON syntax is not enough; decoding must follow the Extended JSON specification**.

## 5. Reading and Writing EJSON in mongosh

**mongosh** exposes **`EJSON`** helpers to serialize and deserialize BSON-typed values:

| Function | Role |
|---|---|
| **EJSON.stringify(value, ..., options)** | Returns an EJSON-encoded **JSON string**. |
| **EJSON.parse(text, options)** | Reads an **EJSON string** and restores the corresponding BSON values. |
| **EJSON.serialize(value, options)** | Returns a **JavaScript object** containing EJSON type wrappers. |
| **EJSON.deserialize(value, options)** | Reads a serialized EJSON object and restores BSON values. |

The difference: **stringify/parse** operate on **text**; **serialize/deserialize** operate on **object values**. Both pairs require choosing the right mode.

### 5.1. Creating a Document with Multiple BSON Types

In mongosh, run:

~~~javascript
use ejson_lab

const original = {
  _id: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberInt(12),
  sequence: NumberLong("9007199254740993"),
  unitPrice: NumberDecimal("19.99"),
  discountRate: 0.125,
  createdAt: ISODate("2024-01-01T00:00:00Z"),
  payload: BinData(0, "AQIDBA==")
};
~~~

**`ObjectId`**, **`NumberInt`**, **`NumberLong`**, **`NumberDecimal`**, **`ISODate`**, and **`BinData`** here are **mongosh constructors/helpers**. Never paste this snippet verbatim into a JSON file expecting a plain JSON parser to read it.

### 5.2. Writing Canonical EJSON and Reading It Back

~~~javascript
const canonicalText = EJSON.stringify(
  original,
  null,
  2,
  { relaxed: false }
);

print(canonicalText);

const restored = EJSON.parse(canonicalText);

// Insert the restored document into MongoDB.
db.samples.insertOne(restored);
~~~

Passing **`relaxed: false`** requests Canonical EJSON. **`EJSON.parse`** interprets wrappers to recreate BSON values, unlike **`JSON.parse`**, which produces plain JavaScript objects, numbers, and strings.

To work with EJSON objects instead of text strings:

~~~javascript
const ejsonObject = EJSON.serialize(original, { relaxed: false });
const bsonValues = EJSON.deserialize(ejsonObject);

db.samples.insertOne(bsonValues);
~~~

When practicing repeatedly, running both **`insertOne`** calls with the same **`_id`** consecutively on the same collection raises a **duplicate key** error. Pick one write path, change **`_id`**, or test in a separate collection.

### 5.3. Checking Types After Insertion

Use **`$type`** in aggregation to inspect stored types rather than guessing from console output:

~~~javascript
db.samples.aggregate([
  {
    $match: { _id: ObjectId("507f1f77bcf86cd799439011") }
  },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      quantityType: { $type: "$quantity" },
      sequenceType: { $type: "$sequence" },
      priceType: { $type: "$unitPrice" },
      createdType: { $type: "$createdAt" },
      payloadType: { $type: "$payload" }
    }
  }
]);
~~~

Expected types:

~~~javascript
{
  idType: "objectId",
  quantityType: "int",
  sequenceType: "long",
  priceType: "decimal",
  createdType: "date",
  payloadType: "binData"
}
~~~

To verify Int64 **values**, also use a constructor/driver supporting 64-bit integers; never coerce them into JavaScript `Number` before comparing.

### 5.4. What Happens When Using `JSON.stringify`?

~~~javascript
const nativeJson = JSON.stringify(original);
const nativeCopy = JSON.parse(nativeJson);

print(nativeJson);
// nativeCopy contains only plain JSON values.
~~~

Plain JSON strings carry no guarantee of preserving **ObjectId**, **Date**, **Decimal128**, or **Int64**. Some BSON values expose custom **`toJSON`** methods, yet their output is not equivalent to Canonical EJSON. For JavaScript `Number` values past the safe integer limit, precision loss can occur even before stringify.

**Do not use `JSON.stringify`/`JSON.parse` as a BSON → JSON → BSON round-trip pipeline when type preservation is required.**

## 6. Reading and Writing Canonical EJSON with the MongoDB Java Driver

In Java, the MongoDB Java driver provides classes such as **`Document`**, **`BsonDocument`**, **`BsonValue`**, and **`JsonWriterSettings`**. When exact BSON types must be preserved at I/O boundaries, **`BsonDocument`** is an explicit choice because it stores every value as a strongly typed **`BsonValue`**.

### 6.1. Parsing Canonical EJSON into `BsonDocument`

Java example using **`org.mongodb:bson`** or its transitive dependency from the MongoDB Java Sync Driver:

~~~java
import org.bson.BsonDocument;
import org.bson.json.JsonMode;
import org.bson.json.JsonWriterSettings;

public class EjsonRoundTripExample {
    public static void main(String[] args) {
        String canonicalJson = """
            {
              "_id": { "$oid": "507f1f77bcf86cd799439011" },
              "quantity": { "$numberInt": "12" },
              "sequence": { "$numberLong": "9007199254740993" },
              "unitPrice": { "$numberDecimal": "19.99" },
              "createdAt": {
                "$date": { "$numberLong": "1704067200000" }
              }
            }
            """;

        // EJSON-aware parser: restores the original BSON types.
        BsonDocument document = BsonDocument.parse(canonicalJson);

        System.out.println(document.get("_id").getBsonType());
        System.out.println(document.get("quantity").getBsonType());
        System.out.println(document.get("sequence").getBsonType());
        System.out.println(document.get("unitPrice").getBsonType());
        System.out.println(document.get("createdAt").getBsonType());

        // Read Int64 as Java long without passing through double.
        long sequence = document.getInt64("sequence").getValue();
        System.out.println(sequence); // 9007199254740993

        JsonWriterSettings canonical = JsonWriterSettings.builder()
                .outputMode(JsonMode.EXTENDED)
                .build();

        // JsonMode.EXTENDED corresponds to Canonical EJSON v2.
        String serialized = document.toJson(canonical);
        BsonDocument restored = BsonDocument.parse(serialized);

        System.out.println(document.equals(restored)); // true for this example
    }
}
~~~

**`BsonDocument.parse`** understands EJSON type wrappers. **`JsonMode.EXTENDED`** emits Canonical EJSON; the enum constant in the Java driver is **`EXTENDED`**, not **`CANONICAL`**. Using **`BsonDocument`** prevents code from accidentally routing Int64 through JavaScript `Number`/`Double`.

### 6.2. Relaxed EJSON in Java

~~~java
JsonWriterSettings relaxed = JsonWriterSettings.builder()
        .outputMode(JsonMode.RELAXED)
        .build();

String humanReadable = document.toJson(relaxed);
System.out.println(humanReadable);
~~~

The output is shorter, yet Int32/Int64 integers and Double floats may lose their exact numeric type tags when parsed back. Choose **`RELAXED`** only for flows where the schema/application explicitly accepts that trade-off.

### 6.3. How Does `Document` Differ from `BsonDocument`?

~~~java
import org.bson.Document;

Document doc = Document.parse(canonicalJson);
System.out.println(doc.get("_id").getClass().getName());
System.out.println(doc.get("sequence").getClass().getName());
~~~

**`Document.parse`** also understands Extended JSON, decoding values into standard Java types such as **`ObjectId`**, **`Long`**, **`Date`**, and **`Decimal128`**. Meanwhile, **`BsonDocument`** retains explicit typed BSON wrappers on every field. In Spring Data MongoDB or POJO mapping, converters and Java field types also determine what gets persisted/read; Canonical EJSON only guarantees clean conversion when intermediate layers do not apply unintended type coercions.

### 6.4. Notes When Binding Data to DTOs/POJOs

Suppose EJSON contains **`{"$numberLong":"9007199254740993"}`**, while a Java DTO declares the field as **`double`**. The system can corrupt the value during DTO binding even if the input text was strictly canonical. Prefer:

- **`long`/`Long`** for Int64 within signed 64-bit Java bounds.
- **`int`/`Integer`** for Int32.
- **`BigDecimal`/`Decimal128`** when business logic requires exact decimals, with a proper converter.
- **`ObjectId`** or a validated converter for BSON ObjectId.
- **`Instant`/`Date`** with UTC conventions and millisecond precision for BSON Date.
- **`byte[]`/`Binary`** with subtype if the domain distinguishes binary subtypes.

EJSON **transports type metadata across text boundaries**, yet faithful restoration still depends on your application's readers, DTOs, codecs, and converters.

## 7. Exporting and Importing with MongoDB Database Tools

The two JSON tools are **mongoexport** and **mongoimport**. Modern versions of MongoDB Database Tools use Extended JSON v2.

### 7.1. Default Export Typically Uses Relaxed Mode

Example:

~~~bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017/shop" \
  --collection=orders \
  --out=orders-relaxed.jsonl
~~~

By default, **mongoexport** emits Extended JSON v2 in **relaxed mode**. Exact numeric sub-types may not survive re-import, especially if another JSON parser processes the file in between.

### 7.2. Select Canonical Mode to Preserve Types During Data Transfer

~~~bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017/shop" \
  --collection=orders \
  --jsonFormat=canonical \
  --out=orders-canonical.jsonl
~~~

The **`--jsonFormat=canonical`** flag selects canonical mode. The **`.jsonl`** extension reminds readers that the default output is **one JSON document per line** (JSON Lines), rather than wrapping the whole file in a single JSON array.

The multi-line command shows Linux/macOS shell syntax. In PowerShell, write it on one line or use PowerShell line-continuation syntax:

~~~powershell
mongoexport --uri="mongodb://127.0.0.1:27017/shop" --collection=orders --jsonFormat=canonical --out=orders-canonical.jsonl
~~~

The output contains wrappers for specialized types. A line may look like:

~~~json
{"_id":{"$oid":"507f1f77bcf86cd799439011"},"quantity":{"$numberInt":"2"},"sequence":{"$numberLong":"9007199254740993"},"createdAt":{"$date":{"$numberLong":"1704067200000"}}}
~~~

### 7.3. Importing into a Target Database/Collection

~~~bash
mongoimport \
  --uri="mongodb://127.0.0.1:27017/shop_copy" \
  --collection=orders \
  --file=orders-canonical.jsonl \
  --mode=insert \
  --stopOnError
~~~

**mongoimport** accepts Extended JSON v2 in either canonical or relaxed form by default, decoding wrappers back into BSON on write. **`--stopOnError`** halts the import on errors instead of continuing past certain data failures.

Here we import into **`shop_copy`** to avoid overwriting or colliding with documents in the source database. If the target collection already contains matching **`_id`** values, import will hit duplicate key errors; prepare a clear migration plan before running in production.

### 7.4. JSON Array Files vs. JSON Lines

By default **mongoexport** writes one document per line. To export as a single JSON array using **`--jsonArray`**, the corresponding import command must also specify **`--jsonArray`**; keep an eye on size constraints in that mode.

~~~bash
mongoexport --uri="mongodb://127.0.0.1:27017/shop" --collection=orders --jsonFormat=canonical --jsonArray --out=orders-array.json
mongoimport --uri="mongodb://127.0.0.1:27017/shop_copy" --collection=orders --jsonArray --file=orders-array.json
~~~

Never mix line-delimited reading with an array file—or vice versa—without configuring the parser accordingly.

### 7.5. JSON Export/Import Is Not a Full Backup

**mongoexport/mongoimport** are great for text-based data movement, yet **they do not replace `mongodump`/`mongorestore`** for full backup and restore. JSON exports omit index definitions, collection options, users/roles, metadata, database-wide point-in-time consistency, and other requirements of a live backup under concurrent writes.

For recoverable MongoDB backups, evaluate **`mongodump`/`mongorestore`**, topology-aware backup tools, or managed backup solutions; never choose JSON files simply because they open easily in a text editor.

## 8. Practice: Round-Tripping and Verifying Types After Import

A clean verification workflow in a lab environment:

1. Prepare a collection holding diverse representative BSON types.
2. Export with **`--jsonFormat=canonical`**.
3. Read with an EJSON parser, avoiding intermediate **`JSON.parse`** steps that strip BSON types.
4. Import into another collection.
5. Compare **both values and BSON types**, especially Int32, Int64, Double, Decimal128, Date, and Binary.

### 8.1. Create Sample Data

In mongosh:

~~~javascript
use ejson_lab

db.type_samples.insertOne({
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tinyCount: NumberInt(15),
  hugeCount: NumberLong("9007199254740993"),
  exchangeRate: NumberDecimal("1.234567890123456789"),
  measurement: 12.5,
  activeSince: ISODate("2024-01-01T00:00:00Z"),
  blob: BinData(0, "AQIDBA=="),
  tags: ["canonical", "bson"]
});
~~~

### 8.2. Export and Import

~~~bash
mongoexport --uri="mongodb://127.0.0.1:27017/ejson_lab" --collection=type_samples --jsonFormat=canonical --out=type_samples.jsonl
mongoimport --uri="mongodb://127.0.0.1:27017/ejson_lab" --collection=type_samples_copy --file=type_samples.jsonl --stopOnError
~~~

### 8.3. Compare Types with Aggregation

~~~javascript
const inspectTypes = (collectionName) =>
  db.getCollection(collectionName).aggregate([
    {
      $project: {
        _id: 0,
        tinyCount: { $type: "$tinyCount" },
        hugeCount: { $type: "$hugeCount" },
        exchangeRate: { $type: "$exchangeRate" },
        measurement: { $type: "$measurement" },
        activeSince: { $type: "$activeSince" },
        blob: { $type: "$blob" }
      }
    }
  ]).toArray();

printjson(inspectTypes("type_samples"));
printjson(inspectTypes("type_samples_copy"));
~~~

When imported properly, both outputs contain the same type names:

~~~json
{
  "tinyCount": "int",
  "hugeCount": "long",
  "exchangeRate": "decimal",
  "measurement": "double",
  "activeSince": "date",
  "blob": "binData"
}
~~~

Matching **`$type`** values is a helpful check, though not sufficient on its own to prove value equality. Also verify large Int64 values, Decimal128 precision, **binary subtypes**, millisecond timestamps, and nested fields.

### 8.4. Verification on the Java Path

To verify each document parsed from canonical text, compare **`BsonDocument`** before and after serialization:

~~~java
BsonDocument before = BsonDocument.parse(canonicalJson);

JsonWriterSettings canonical = JsonWriterSettings.builder()
        .outputMode(JsonMode.EXTENDED)
        .build();

BsonDocument after = BsonDocument.parse(before.toJson(canonical));

if (!before.equals(after)) {
    throw new IllegalStateException("EJSON round-trip changed BSON values");
}
~~~

This performs BSON value comparison in Java for supported types, **not a guarantee that every exotic bit-level representation survives byte-for-byte through EJSON**. When a workflow requires strict byte-for-byte fidelity, use BSON binary with controlled codecs and versions.

## 9. Common Errors When Reading and Writing EJSON

### 9.1. Calling `JSON.parse` and Expecting an ObjectId

~~~javascript
const text = '{"_id":{"$oid":"507f1f77bcf86cd799439011"}}';

const ordinary = JSON.parse(text);
const bsonAware = EJSON.parse(text);

printjson(ordinary);
printjson(bsonAware);
~~~

**`ordinary._id`** remains a plain object with a **`$oid`** key; **`bsonAware._id`** is an actual BSON ObjectId. When loading EJSON files into MongoDB, always use an EJSON-aware reader.

### 9.2. Converting ObjectId to String and Querying with a String

~~~javascript
// When _id is stored as BSON ObjectId:
db.type_samples.findOne({
  _id: ObjectId("507f1f77bcf86cd799439012")
});

// Same characters in a text string, but a different BSON type:
db.type_samples.findOne({
  _id: "507f1f77bcf86cd799439012"
});
~~~

Results will differ. MongoDB matches on both type and value; never assume the driver or server automatically casts strings into ObjectIds.

### 9.3. Passing Large Int64 Through JavaScript `Number`

~~~javascript
const unsafeNumber = 9007199254740993;
const exactLong = NumberLong("9007199254740993");

// unsafeNumber may already be rounded when Number was evaluated.
// exactLong is constructed from a string to preserve the Int64 value.
~~~

You cannot repair already-lost digits by wrapping with **`NumberLong(unsafeNumber)`**. Keep the value as a string inside **`$numberLong`** or use BSON `Long` with supporting APIs.

### 9.4. Treating Decimal128 Like Double

~~~javascript
db.prices.insertOne({
  code: "P-1",
  precise: NumberDecimal("0.1"),
  approximate: 0.1
});
~~~

These two fields differ in both type and numeric representation. For financial workflows, avoid passing Decimal128 values through **`double`/`Number`** variables when exact decimal arithmetic is contracted.

### 9.5. Dropping the `$date` Wrapper Because "It's Already an ISO String"

~~~json
{
  "wrongForBsonDate": "2024-01-01T00:00:00Z",
  "bsonDate": { "$date": "2024-01-01T00:00:00Z" }
}
~~~

A date string can be fine in a **public REST API** if the schema documents conversion to Date. However, it is **not** Canonical EJSON preserving the BSON type in text form.

### 9.6. Keeping Only Base64 and Dropping `subType`

~~~json
{
  "rawString": "AQIDBA==",
  "binaryValue": {
    "$binary": { "base64": "AQIDBA==", "subType": "00" }
  }
}
~~~

Not every Base64 string denotes BSON binary. Subtype distinguishes binary classifications, especially in UUID scenarios.

### 9.7. Using `mongosh` Syntax Instead of Valid JSON

~~~javascript
// Syntax for mongosh or shell representations:
{ _id: ObjectId("507f1f77bcf86cd799439011") }
~~~

~~~json
{
  "_id": { "$oid": "507f1f77bcf86cd799439011" }
}
~~~

Only the second form is valid JSON that can be sent over APIs or saved to standard files readable by generic JSON parsers. The MongoDB Java driver has a **Shell JSON mode**, yet that format does not replace Canonical EJSON v2 when interoperating with JSON-compliant tools.

### 9.8. Mixing Extended JSON v1 and v2

MongoDB formerly used **Legacy Extended JSON v1** with different wrappers, particularly for dates, binary, and regex. Legacy formats used representations such as **`$binary`/`$type`** or **`$regex`/`$options`**, which differ from v2 wrappers.

Modern MongoDB Database Tools use EJSON v2. **`mongoimport`** accepts **`--legacy`** for v1 files when migrating old exports; never apply `--legacy` blindly to EJSON v2 files.

### 9.9. Mixing Type Metadata with Untrusted User Input

An EJSON parser turns special wrappers into BSON values. If an application accepts JSON from users and passes the parsed object directly as a **MongoDB query filter or update**, attackers can inject query operators or unexpected fields that alter query semantics.

Example of an unchecked incoming filter:

~~~json
{
  "status": { "$ne": "CANCELLED" }
}
~~~

While not directly about type fidelity, this underscores that **correctly parsing BSON types does not make untrusted input safe to execute as a query**. Use allowlisted DTOs/schemas, construct filters explicitly from validated fields, and enforce access control.

## 10. Designing Data Contracts at Application Boundaries

Not every HTTP API needs to expose Canonical EJSON. Choose the representation based on your goal:

| Need | Recommended Representation | Notes |
|---|---|---|
| **Round-trip MongoDB ↔ JSON file ↔ MongoDB** | Canonical EJSON v2. | Both writer and reader must support EJSON. |
| **ETL preserving BSON types** | Canonical EJSON or BSON binary. | Avoid intermediate layers coercing numbers to double. |
| **Java ↔ Node.js with large Int64** | Canonical **`$numberLong`** or explicit string/Long contract. | Never pass through JavaScript `Number`. |
| **Public API returning timestamps to clients** | ISO-8601 string if the contract defines it as a Date/instant. | Do not expect `JSON.parse` to create Date automatically. |
| **Human-readable logs/documents** | Relaxed EJSON if losing numeric type metadata is acceptable. | Never treat such logs as an import source of truth. |
| **Database backup/restore** | Topology-aware MongoDB backup tools. | `mongoexport` JSON does not replace full backups. |

### 10.1. Distinguishing "Intentional Type Conversion" from "Accidental Type Loss"

An API can intentionally return:

~~~json
{
  "id": "507f1f77bcf86cd799439011",
  "createdAt": "2024-01-01T00:00:00Z",
  "price": "19.99"
}
~~~

This is a **valid DTO contract** if API docs specify that fields are an ObjectId string, ISO timestamp, and decimal string and the backend converts them under strict validation. However, it is **not an EJSON round-trip**. It depends on per-field schemas and business rules to recover types.

If your goal is faithful BSON exchange, use:

~~~json
{
  "id": { "$oid": "507f1f77bcf86cd799439011" },
  "createdAt": { "$date": { "$numberLong": "1704067200000" } },
  "price": { "$numberDecimal": "19.99" }
}
~~~

You do not need to force every consumer to speak EJSON when an API can define and validate explicit DTO conversions. The rule is: **never mistake a human-friendly DTO for a lossless BSON clone**.

### 10.2. Watch Intermediate Hops

In real architectures, data often traverses:

~~~text
MongoDB BSON
   |
   v
MongoDB Driver
   |
   v
Canonical EJSON writer
   |
   v
File / message / HTTP payload
   |
   v
EJSON-aware parser
   |
   v
BSON values / typed DTO
   |
   v
MongoDB destination
~~~

If an intermediate hop inserts:

~~~text
Canonical EJSON -> JSON.parse -> manual wrapper unwrapping -> Number/Date/string
~~~

then fidelity drops to whatever that custom unwrapping logic preserves. Systems running **JavaScript**, **Python**, **Java**, **Go**, or data platforms parse JSON numbers and timestamps differently; your pipeline must specify the parser, post-parse types, and mapping rules explicitly.

### 10.3. Don't Forget Metadata Outside Documents

Reading and writing EJSON preserves **field types inside documents** where supported; it does not automatically preserve **index definitions**, **collection validation**, **collation**, **TTL policies**, **shard keys**, users/roles, or transaction snapshots. Those belong to migration, backup, and database administration workflows.

## 11. When Should You Use BSON Binary Instead of EJSON?

Canonical EJSON is built for portable text exchange and handles most type-preservation needs. However, **BSON binary** is a better fit when:

- Exchanges or backups require preserving exact binary BSON records under strict compatibility standards.
- Data volume is large and you want to avoid text wrapper and Base64 overhead.
- MongoDB drivers sit at both ends with no requirement for humans to inspect raw JSON files.
- Edge cases demand exact bit-for-bit preservation that Canonical EJSON does not guarantee.

Conversely, Canonical EJSON excels when data must traverse JSON-only infrastructure while retaining type tags so the receiver can reconstruct BSON accurately.

## 12. Real-World Scenarios

### 12.1. Recovering Large Sequence Numbers After Passing Through JavaScript

A Java service writes sequence **9007199254740993** as BSON Int64. A Node.js gateway reads from MongoDB, calls **`JSON.stringify`** in a way that converts `Long` to a plain number, and sends it to a consumer. The consumer receives **9007199254740992** due to JavaScript `Number`'s safe integer limit.

Protection: preserve **BSON `Long`** in the driver, emit **`{"$numberLong":"9007199254740993"}`** or use a documented decimal string/`BigInt` contract; have the consumer reconstruct it via an EJSON parser or `Long` library.

### 12.2. Syncing Order Data with Drifting Prices

Application A stores prices in Decimal128; Application B reads relaxed output or custom JSON and parses prices into `double` before calculations. Displayed prices may look similar, yet rounding and totals drift.

Protection: use **`$numberDecimal`** in EJSON and proper Decimal128/`BigDecimal` mapping on the receiving side; never pass through binary floats when exact decimal math is required.

### 12.3. Re-Importing Data with the Wrong `_id` Type

An export script turns ObjectIds into plain strings and strips wrappers. Upon import, the new collection gets **string `_id` values**. Java driver queries passing ObjectId no longer find those documents despite matching 24 characters.

Protection: use Canonical EJSON with **`$oid`**; verify **`$type`** after import.

### 12.4. Logs Show Dates, Yet Re-Imported Records Become Strings

An app logs **`"createdAt":"2024-01-01T00:00:00Z"`** and later replays logs as import input. The parser sees only strings, breaking Date queries and Date-based TTL indexes.

Protection: if logs will be replayed as data, emit Canonical EJSON or enforce a controlled date-conversion schema; human-readable logs are not a canonical import source by default.

## 13. Self-Check Questions

1. Why is the JSON number **42** insufficient to distinguish BSON Int32, Int64, and Double?
2. Why is passing Int64 **9007199254740993** through JavaScript `Number` risky, and how does **`$numberLong`** solve it?
3. What is the difference between **`{"$date":"2024-01-01T00:00:00Z"}`** and **`"2024-01-01T00:00:00Z"`**?
4. How do **`JSON.parse`** and **`EJSON.parse`** behave differently on **`$oid`** and **`$numberDecimal`**?
5. In the MongoDB Java driver, what are **`JsonMode.EXTENDED`** and **`JsonMode.RELAXED`** used for?
6. Which flag makes **`mongoexport`** emit Canonical EJSON instead of relaxed?
7. Why must **`subType`** of a BSON Binary value be preserved alongside Base64?
8. Why is an EJSON document export still insufficient to serve as a consistent database backup?
9. When `_id` values have accidentally turned from ObjectId into strings, how can you audit them with MongoDB aggregation?
10. Is a REST API using ISO strings and decimal strings automatically wrong? Distinguish a DTO contract from a BSON round-trip.

## 14. Practical Summary

The goal of **"reading and writing Extended JSON without losing BSON type information"** can be achieved consistently by following these principles:

1. **Export Canonical EJSON v2** whenever type tags must be preserved—especially Int32, Int64, Double, Decimal128, ObjectId, Date, and Binary.
2. **Read with an EJSON-aware parser** such as `EJSON.parse` in mongosh or `BsonDocument.parse`/`Document.parse` in the MongoDB Java driver.
3. **Avoid implicit coercions** through JavaScript `Number`, `JSON.stringify`, `double` DTOs, or plain date strings unless conversion is intentional.
4. **Use `mongoexport --jsonFormat=canonical`** for JSON export/import pipelines needing BSON types, and confirm `mongoimport` supports EJSON v2.
5. **Verify values and `$type`** in the destination environment; for critical data, check Decimal128, large Int64, Date, and Binary subtypes.
6. **Separate document export from database backup/migration**: EJSON does not preserve all schemas, indexes, or metadata and does not create consistent snapshots on its own.

### Official References

- [MongoDB Extended JSON v2](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — canonical/relaxed formats and wrapper tables for every BSON type.
- [MongoDB Extended JSON Specification](https://specifications.readthedocs.io/en/latest/extended-json/extended-json/) — conversion contracts and technical boundaries.
- [MongoDB Java Sync Driver: Extended JSON](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-extended-json/) — `BsonDocument.parse`, `JsonWriterSettings`, and `JsonMode`.
- [mongoexport](https://www.mongodb.com/docs/database-tools/mongoexport/) — the `--jsonFormat=canonical` option.
- [mongoimport](https://www.mongodb.com/docs/database-tools/mongoimport/) — ingesting EJSON v2 data and the `--legacy` option.

Whenever a data flow spans multiple programming languages or conversion tools, define upfront the **source BSON types**, **EJSON mode written**, **destination parser**, and **post-parse application types**. Even a single BSON-unaware intermediate step can strip type fidelity while leaving the final JSON completely valid syntactically.
