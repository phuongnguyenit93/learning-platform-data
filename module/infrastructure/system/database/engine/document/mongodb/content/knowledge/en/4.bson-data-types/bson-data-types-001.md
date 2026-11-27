# Distinguishing JSON, BSON, and Extended JSON in MongoDB

When working with MongoDB, the same document can be represented in several ways: as JSON text when exchanged over an API, as BSON when MongoDB stores and transmits data, or as Extended JSON when you need to inspect BSON-specific data types in a text document. These three concepts are closely related, yet they are **not interchangeable in every situation**.

For example, a MongoDB identifier has the **ObjectId** type, a point in time has the **Date** type, and a monetary amount has the **Decimal128** type. If you treat them merely as plain JSON strings and numbers, you can lose data type information, corrupt high-precision numbers, or run queries that fail to match the values stored in the database.

This lesson explains each format, compares their ability to represent data types, distinguishes between the two Extended JSON modes (Canonical and Relaxed), and walks through practical conversions and common pitfalls.

## 1. The Big Picture

Consider three representations of the same idea:

~~~text
Application / API / config file
          |
          | JSON text
          v
    {"name":"Pen", "quantity":5}

MongoDB Driver <------------------------> MongoDB Server
                  binary BSON document
                    (with type codes)
          |
          | Need to view, export, or exchange BSON data
          | as text while still representing types
          v
  Extended JSON
  {"quantity":{"$numberInt":"5"}}
~~~

A concise comparison:

| Criterion | JSON | BSON | Extended JSON (EJSON) |
|---|---|---|---|
| Nature | Text format following JSON syntax | Binary format with type information | Convention for representing BSON values in text using JSON syntax |
| Common uses | REST APIs, configuration, logs, data exchange | MongoDB documents, driver–server communication | Exporting/importing MongoDB data, documentation examples, inspecting typed data |
| Human-readable | Yes | Not directly | Yes, though many fields use wrapper objects |
| Basic types | object, array, string, number, boolean, null | Has corresponding types, plus many MongoDB-specific types | Uses JSON syntax and wrappers to express BSON types |
| ObjectId, Date, Decimal128 | No native types | Native types | Dedicated representations such as $oid, $date, $numberDecimal |
| Distinguishing Int32, Int64, Double | No type tags in standard JSON | Yes | Canonical EJSON uses explicit wrappers; Relaxed may use plain JSON numbers |
| Stored directly as an easily editable file | Yes | Not convenient | Yes |
| Preserves all BSON types accurately on conversion | Not guaranteed automatically | Yes if handled properly by the driver | Canonical aims to preserve type information, within conversion rules and tool support |

**Key takeaway:** Both JSON and Extended JSON can be written as text files; BSON is a binary format. Extended JSON is **not another binary storage format of MongoDB**; it is a way to write BSON values so that humans and text-based tools can exchange them.

## 2. JSON: The Ubiquitous Text Data Language

JSON (JavaScript Object Notation) is a text-based data interchange format. A JSON value can be:

- **Object:** a collection of field-name and value pairs.
- **Array:** an ordered list of values.
- **String:** a sequence of characters enclosed in double quotes.
- **Number:** a number written in JSON syntax, without type labels like Int32 or Decimal128.
- **Boolean:** true or false.
- **Null:** null.

Example of valid JSON:

~~~json
{
  "orderId": "ORD-001",
  "customer": {
    "name": "Lan",
    "city": "Hanoi"
  },
  "items": [
    {"sku": "PEN-01", "quantity": 2},
    {"sku": "BOOK-03", "quantity": 1}
  ],
  "total": 149900,
  "paid": false,
  "shippedAt": null
}
~~~

JSON is well suited for communicating with a frontend, sending HTTP requests/responses, or storing configuration. However, JSON notation **does not specify whether the number 149900 is an Int32, Int64, Double, or Decimal128**. The JSON parser must decide which numeric type to construct based on the language and library in use.

Standard JSON also lacks native date/time or MongoDB identifier types. In many APIs, the application adopts explicit conventions:

~~~json
{
  "id": "66f1c2a4b1d2e3f405162738",
  "createdAt": "2026-01-15T08:30:00.000Z"
}
~~~

At the JSON level, both **id** and **createdAt** are simply strings. Interpreting the first string as an ObjectId and the second as a timestamp must be handled by the application, schema, or serializer/deserializer.

### 2.1. JSON Is Not JavaScript Object Syntax

The expressions below frequently appear in JavaScript or the MongoDB Shell, but they are **not valid JSON**:

~~~javascript
// JavaScript / mongosh, not standard JSON
{
  name: "Lan",                         // field name not enclosed in double quotes
  createdAt: new Date(),               // JavaScript expression
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  quantity: NumberLong("5"),           // function call
}
~~~

JSON requires field names to be enclosed in double quotes; JSON does not support comments, function calls, or trailing commas at the end of a list. Therefore, you cannot copy a `mongosh` snippet verbatim and assume a JSON parser will understand it.

Special numeric values such as `NaN`, `Infinity`, or `-Infinity` are also not valid numeric literals in standard JSON.

## 3. BSON: MongoDB's Binary Document Format

BSON is an acronym commonly expanded as **Binary JSON**. It is a format that encodes data into a sequence of bytes, carrying a type code for each value. MongoDB uses BSON to represent documents during storage and transmission over the MongoDB wire protocol.

For a developer, a document can still be manipulated like an object or map:

~~~javascript
{
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  name: "Pen",
  quantity: 5,
  createdAt: ISODate("2026-01-15T08:30:00.000Z")
}
~~~

This is **how mongosh displays or constructs values**, not the raw BSON bytes. When a driver encodes a document, it writes out a binary structure. For a typical BSON document, the general layout contains:

~~~text
BSON Document
  ├── Document length (4 bytes, little-endian)
  ├── Element 1
  │     ├── Type code (1 byte)
  │     ├── Field name (C-string terminated by 0 byte)
  │     └── Type-encoded value
  ├── Element 2
  │     └── ...
  └── Document terminator byte (0)
~~~

Type information resides inside the binary data rather than relying on a reader to guess the format of a string or number from its contents. For instance, the same mathematical value **5** can be encoded as an Int32, Int64, or Double with different type codes.

### 3.1. Common BSON Types

| BSON Type | Meaning | Common Examples in MongoDB |
|---|---|---|
| String | UTF-8 string | Product name, email |
| Object / Embedded Document | Nested document | Address, shipping details |
| Array | Ordered list | List of items |
| Boolean | True or false | isActive |
| Null | Explicitly stored null value | middleName: null |
| Int32 | 32-bit signed integer | Quantity, small counters |
| Int64 / Long | 64-bit signed integer | Large counters, numeric IDs |
| Double | IEEE 754 double-precision floating-point number | Scores, physical measurements |
| Decimal128 | Decimal128 floating-point decimal number | Monetary amounts requiring decimal precision control |
| ObjectId | 12-byte BSON identifier | Common default _id |
| Date | 64-bit integer representing milliseconds since the Unix epoch | createdAt, updatedAt |
| Timestamp | Value consisting of seconds and an incrementing ordinal; typically used in internal/replication contexts | Oplog-related operations |
| Binary | Byte array with subtype | Hashes, binary payloads |
| Regular Expression | Regular expression pattern and optional flags | Stored pattern-matching criteria |
| MinKey / MaxKey | Special values used for BSON sort-order comparison | Specialized query/index cases |

BSON also has several legacy or specialized types, such as JavaScript Code or Undefined, which have been restricted or deprecated in many contexts. When designing new applications, choose standard types that are clearly supported by drivers.

### 3.2. Is BSON Always Smaller or Faster Than JSON?

Not necessarily. BSON is designed so that machines can parse and distinguish types easily, but each document carries additional length fields, type codes, and field names. For small payloads, a BSON representation **can be larger** than its corresponding JSON text. For numeric types, binary payloads, and parsing overhead, processing costs also differ.

Do not equate the word "Binary" with "data compression." BSON is **not automatically a compressed format**, and memory or storage efficiency also depends on schema design, storage-engine compression, data types, indexes, and workload.

MongoDB limits the size of a standard BSON document to **16 MiB**. This is a MongoDB document limit, not a general rule for all JSON files.

## 4. Extended JSON: Writing BSON Types Using JSON Syntax

Extended JSON (often abbreviated **EJSON**) defines how to represent BSON values using special objects in JSON. An ObjectId value is not degraded to a bare string; it can be written as:

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  }
}
~~~

A standard JSON parser can still parse the text above. However, it only produces an object with a **$oid** key; restoring a true ObjectId requires an **Extended JSON parser** that understands the `$oid` convention.

Similarly:

~~~json
{
  "createdAt": {
    "$date": "2026-01-15T08:30:00.000Z"
  },
  "amount": {
    "$numberDecimal": "149900.50"
  }
}
~~~

The **$date** and **$numberDecimal** wrappers carry data type semantics. This is why EJSON is useful when exporting documents to text or testing data scenarios where types must be preserved.

**Important:** Extended JSON is a convention built on top of JSON syntax, not a set of MongoDB query operators. For example, the object `{"$oid":"..."}` does not automatically mean an ObjectId if you pass it as a plain JavaScript object into a query method. To use it as an ObjectId, construct an ObjectId instance or decode it with the driver's EJSON parser.

### 4.1. Two Modes of Extended JSON v2

In Extended JSON v2, two formatting modes are commonly used:

1. **Canonical Extended JSON:** uses explicit representations for BSON types, especially numeric types. Ideal when controlled data exchange is needed or when type information must be preserved accurately across text serialization.
2. **Relaxed Extended JSON:** prioritizes readability by using standard JSON numbers where possible while retaining wrappers for types that JSON cannot represent directly, such as ObjectId and Decimal128. Suitable for human inspection, logs, or exchanges close to regular JSON.

These are two **representation modes of the same Extended JSON system**, not two different database engines or on-disk storage formats.

## 5. Canonical vs. Relaxed: Comparing on a Single Document

Suppose MongoDB stores a document with the following BSON types:

- _id: ObjectId
- title: String
- quantity: Int32
- total: Decimal128
- createdAt: Date
- active: Boolean

### 5.1. Canonical Extended JSON

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  },
  "title": "Notebook",
  "quantity": {
    "$numberInt": "12"
  },
  "total": {
    "$numberDecimal": "249.90"
  },
  "createdAt": {
    "$date": {
      "$numberLong": "1735689600000"
    }
  },
  "active": true
}
~~~

Here:

- **$numberInt** asserts that `quantity` has the BSON Int32 type, rather than being an ambiguous JSON number.
- **$numberDecimal** preserves the Decimal128 type and its decimal string representation.
- **$date** wraps **$numberLong**, recording milliseconds since `1970-01-01T00:00:00Z`, which is the Canonical representation of BSON Date.
- **$oid** describes the ObjectId as 24 hexadecimal characters, corresponding to 12 bytes.

### 5.2. Relaxed Extended JSON

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  },
  "title": "Notebook",
  "quantity": 12,
  "total": {
    "$numberDecimal": "249.90"
  },
  "createdAt": {
    "$date": "2025-01-01T00:00:00Z"
  },
  "active": true
}
~~~

Both examples describe the same **values**; only the presentation of integers and dates differs. Relaxed mode is easier to read, but some numeric type metadata may not be sufficiently explicit to distinguish Int32, Int64, and Double when moved across environments.

For example, looking solely at:

~~~json
{"score": 12}
~~~

You cannot be certain whether the original BSON value was `Int32(12)`, `Int64(12)`, or `Double(12)`. One library might choose Int32 based on range; another might construct a double-precision Number. If **preserving the exact original type** is a strict requirement, use Canonical Extended JSON with a compliant converter.

### 5.3. Conversion Table for Common BSON Types

| BSON | Canonical Extended JSON | Relaxed Extended JSON |
|---|---|---|
| Int32 equal to 42 | {"$numberInt":"42"} | 42 |
| Int64 equal to 42 | {"$numberLong":"42"} | May be 42 if safely representable under relaxed rules |
| Int64 larger than JavaScript's safe integer limit | {"$numberLong":"9007199254740993"} | Requires the long integer wrapper to avoid precision loss |
| Double equal to 3.5 | {"$numberDouble":"3.5"} | 3.5 |
| Decimal128 equal to 19.90 | {"$numberDecimal":"19.90"} | {"$numberDecimal":"19.90"} |
| ObjectId | {"$oid":"66f1c2a4b1d2e3f405162738"} | Same as Canonical |
| Date (typical UTC timestamp) | {"$date":{"$numberLong":"1735689600000"}} | {"$date":"2025-01-01T00:00:00Z"} |
| Binary three bytes 01 02 03, subtype 00 | {"$binary":{"base64":"AQID","subType":"00"}} | Same as Canonical |
| Regular Expression | {"$regularExpression":{"pattern":"^A","options":"i"}} | Same as Canonical |
| Timestamp | {"$timestamp":{"t":1710000000,"i":1}} | Same as Canonical |
| MinKey | {"$minKey":1} | Same as Canonical |
| MaxKey | {"$maxKey":1} | Same as Canonical |

These are representative patterns of **Extended JSON v2**. Certain edge cases such as Double `NaN`/`Infinity`, Date values outside the range supported by convenient ISO formatting, or legacy types follow dedicated rules; therefore, you should not hand-roll an EJSON parser by guessing from a few examples.

### 5.4. What Remains Identical Across All Three Views

String, Boolean, Null, Array, and embedded documents look nearly identical:

~~~json
{
  "name": "An",
  "active": true,
  "tags": ["mongodb", "bson"],
  "profile": {
    "city": "Da Nang",
    "verified": null
  }
}
~~~

Not **every field** needs an EJSON wrapper. Wrappers appear when it is necessary to carry or clarify type information that plain JSON lacks.

## 6. The Biggest Pitfall: Precision and Numeric Types

In standard JSON, numeric syntax allows writing:

~~~json
{
  "small": 7,
  "big": 9007199254740993,
  "price": 19.90
}
~~~

However, how numbers are stored after parsing **depends on the language and library**. In JavaScript, the `Number` type uses IEEE 754 double precision; integers are only preserved accurately within the range from **-(2^53 - 1)** to **2^53 - 1**. Converting a large Int64 into a JavaScript `Number` can round the value.

For example:

~~~javascript
// 9007199254740993 exceeds Number's safe integer limit.
const unsafe = 9007199254740993;
console.log(Number.isSafeInteger(unsafe)); // false

// A string preserves the exact digits; the driver needs to construct the corresponding Long/BSON type.
const exactText = "9007199254740993";
~~~

JSON can write that sequence of digits, but **`JSON.parse` in JavaScript** typically parses it into a `Number` and can lose precision. Thus, a large Int64 value should be represented in Extended JSON as:

~~~json
{
  "visits": {
    "$numberLong": "9007199254740993"
  }
}
~~~

A compliant EJSON parser recognizes this as a 64-bit integer and avoids the plain `Number` parsing step that drops digits. When processing it further, use an appropriate integer type (such as `Long` or `BigInt` depending on the driver and configuration) instead of coercing to `Number`.

### 6.1. Double Is Not Equivalent to Decimal128

Double stores numbers in binary floating-point form. Many decimal fractions, such as 0.1, have no exact finite representation in binary:

~~~javascript
console.log(0.1 + 0.2 === 0.3); // false in JavaScript Number
~~~

BSON **Decimal128** serves decimal calculations that require appropriate precision, such as monetary prices or financial data within the limits of the Decimal128 format. In EJSON:

~~~json
{
  "unitPrice": {
    "$numberDecimal": "0.10"
  },
  "tax": {
    "$numberDecimal": "0.20"
  }
}
~~~

Keeping the value as a string inside the wrapper allows libraries to instantiate Decimal128 without passing through an imprecise `Number`. When adding or subtracting in MongoDB, you still must choose appropriate operators, rounding rules, and decimal scale handling for your business logic; Decimal128 does not replace currency-handling design by itself.

### 6.2. Why 5, 5.0, and "5" Are Not the Same Type

- **5** in JSON is a number; after parsing, the original BSON type is ambiguous.
- **5.0** is a JSON numeric literal; when parsed, a library may not preserve the `.0` as type metadata.
- **"5"** is a string; MongoDB does not automatically treat it as a BSON number.
- **{"$numberInt":"5"}** in Canonical EJSON describes Int32.
- **{"$numberLong":"5"}** in Canonical EJSON describes Int64.
- **{"$numberDouble":"5.0"}** in Canonical EJSON describes Double.

Distinguishing between **mathematical value** and **representation type** is foundational when reading MongoDB data or checking whether a document's types changed after import/export.

## 7. ObjectId, Date, Timestamp, and Binary

### 7.1. ObjectId Is a BSON Type, Not Just a Hex String

A standard ObjectId has **12 bytes** of data; the **24-character** hex string is just a readable notation:

~~~javascript
// Mongosh
const id = ObjectId("66f1c2a4b1d2e3f405162738");
db.customers.findOne({ _id: id });
~~~

In Extended JSON:

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  }
}
~~~

Whereas in plain JSON:

~~~json
{
  "_id": "66f1c2a4b1d2e3f405162738"
}
~~~

These two documents are **not equivalent in `_id` type**: the first holds an ObjectId, while the second holds a String. If `_id` is stored as an ObjectId, querying with an unconverted hex string will not match just because the two look alike when printed.

MongoDB can use other types for `_id` (such as String) if the application intentionally chooses them. Therefore, do not blindly coerce every ID string into an ObjectId without knowing the schema.

### 7.2. BSON Date Is an Instant in Time, Without a Stored Timezone String

BSON Date stores **milliseconds since the Unix epoch** in a 64-bit integer. This instant is independent of how you format it for display in a particular timezone.

For example, the same instant:

~~~json
{
  "canonical": {
    "$date": {
      "$numberLong": "1735689600000"
    }
  },
  "relaxed": {
    "$date": "2025-01-01T00:00:00Z"
  }
}
~~~

The two fields illustrate two notations, not a requirement to store both in a real document. The **Z** suffix indicates UTC; when displayed to a user in Vietnam time (UTC+07:00), the corresponding local time is **07:00:00 on 2025-01-01**.

By contrast:

~~~json
{
  "createdAt": "2025-01-01T00:00:00Z"
}
~~~

This is merely a JSON string. If sent into MongoDB without converting to Date, the field will be stored as a BSON String, causing mismatches during temporal queries, date arithmetic, or indexing by the expected type.

### 7.3. Timestamp Differs from Date

MongoDB BSON Timestamp has two components: **t** (seconds) and **i** (increment). It commonly appears in internal mechanisms like replication/oplog:

~~~json
{
  "ts": {
    "$timestamp": {
      "t": 1710000000,
      "i": 1
    }
  }
}
~~~

Timestamp is **not** the default type to use for recording an order creation date. For business logic, BSON Date is generally more appropriate for storing a point in time.

### 7.4. Binary Contains Bytes and a Subtype

Extended JSON example of the three bytes `0x01`, `0x02`, `0x03`:

~~~json
{
  "payload": {
    "$binary": {
      "base64": "AQID",
      "subType": "00"
    }
  }
}
~~~

**base64** encodes byte data into characters for placement in JSON; **subType** identifies the BSON Binary classification. A plain JSON string containing `"AQID"` carries no information indicating it is binary subtype `00`.

## 8. Hands-on Conversion with the BSON Library in JavaScript

To see the differences without manually decoding BSON bytes, you can use the **bson** package from the MongoDB Node.js ecosystem. The example uses Node.js ES Modules syntax; the project needs the `bson` package installed:

~~~bash
npm install bson
~~~

Create the file **ejson-demo.mjs**:

~~~javascript
import {
  EJSON,
  ObjectId,
  Int32,
  Long,
  Decimal128
} from "bson";

const document = {
  _id: new ObjectId("66f1c2a4b1d2e3f405162738"),
  product: "Keyboard",
  quantity: new Int32(5),
  largeCounter: Long.fromString("9007199254740993"),
  price: Decimal128.fromString("199.90"),
  createdAt: new Date("2026-01-15T08:30:00.000Z"),
  active: true,
  tags: ["mongo", "ejson"]
};

const canonical = EJSON.stringify(
  document,
  null,
  2,
  { relaxed: false }
);

const relaxed = EJSON.stringify(
  document,
  null,
  2,
  { relaxed: true }
);

console.log("CANONICAL EJSON:\n", canonical);
console.log("RELAXED EJSON:\n", relaxed);

// The EJSON parser reconstructs the corresponding BSON objects/types.
const restored = EJSON.parse(canonical, { relaxed: false });
console.log("ObjectId:", restored._id instanceof ObjectId);
console.log("Int64:", restored.largeCounter.toString());
console.log("Decimal128:", restored.price.toString());
console.log("Date:", restored.createdAt.toISOString());
~~~

Run:

~~~bash
node ejson-demo.mjs
~~~

Observe in the Canonical output:

- **quantity** is wrapped with `$numberInt`.
- **largeCounter** is wrapped with `$numberLong` containing the full digit string.
- **price** is wrapped with `$numberDecimal`.
- **createdAt** is represented by `$date` containing `$numberLong`.
- **_id** is represented by `$oid`.

In the Relaxed output, `quantity` is easier to read because it is emitted as a normal JSON number, whereas ObjectId and Decimal128 still require wrappers. For 64-bit integers outside `Number`'s safe range, the EJSON library favors a representation that preserves the value accurately.

**Why not use `JSON.stringify` instead of `EJSON.stringify`?** A generic JSON serializer has no obligation to preserve all BSON types. Certain driver classes may provide their own JSON conversion methods, but those details are library-dependent; you should not treat `JSON.stringify` as a contract that preserves BSON types across systems.

### 8.1. Converting in the Right Direction

~~~text
BSON value in application
    |
    | EJSON.stringify(..., { relaxed: false })
    v
Canonical Extended JSON (text string)
    |
    | EJSON.parse(..., { relaxed: false })
    v
BSON-aware objects in application
    |
    | Driver serialize
    v
BSON bytes sent to MongoDB
~~~

Do not confuse **EJSON.parse** with **JSON.parse**. Both accept text with JSON syntax, but only an EJSON parser understands the BSON type wrappers to restore the corresponding types.

### 8.2. When Writing Java / Spring Data MongoDB

A Java application can work with the corresponding driver classes, for example:

~~~java
import java.time.Instant;
import java.util.Date;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;
import java.math.BigDecimal;

Document product = new Document()
        .append("_id", new ObjectId("66f1c2a4b1d2e3f405162738"))
        .append("name", "Keyboard")
        .append("quantity", 5)
        .append("price", new Decimal128(new BigDecimal("199.90")))
        .append("createdAt", Date.from(Instant.parse("2026-01-15T08:30:00Z")));
~~~

This example uses BSON and Java MongoDB driver classes; the Java code itself is **not JSON text**. When the driver sends the document to MongoDB, values are serialized to BSON according to the types determined by the codec. If receiving data from a JSON REST API, the application must map and validate inputs before constructing ObjectId, Date, or Decimal128 values.

## 9. MongoDB Shell, Drivers, APIs, and Export Tools

In practice, you will encounter different data formats depending on the tool.

### 9.1. mongosh Displays a Friendly Format, Not Standard JSON Files

~~~javascript
// MongoDB Shell (mongosh)
use shop

db.products.insertOne({
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  name: "Keyboard",
  quantity: NumberInt(5),
  price: NumberDecimal("199.90"),
  createdAt: ISODate("2026-01-15T08:30:00Z")
});

db.products.findOne({
  _id: ObjectId("66f1c2a4b1d2e3f405162738")
});
~~~

**`ObjectId()`, `NumberInt()`, `NumberDecimal()`, and `ISODate()` are mongosh helpers/syntax**, not JSON syntax. When the driver sends the data, those typed objects are converted into BSON.

If you have Canonical Extended JSON as text, use an EJSON parser or compatible import tool to restore types before constructing queries. Do not take:

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  }
}
~~~

directly and assume it acts as an ObjectId filter when passed as a plain object; in that case **`$oid`** remains just a field name inside an object until decoded as EJSON.

### 9.2. REST API Applications Should Choose a Clear Data Contract

An API might return a simple JSON payload:

~~~json
{
  "id": "66f1c2a4b1d2e3f405162738",
  "price": "199.90",
  "createdAt": "2026-01-15T08:30:00Z"
}
~~~

This is an **API design** choice: `id` and `price` are specified as strings, and `createdAt` is an ISO-8601 timestamp string. The API must document how to parse, validate, and convert them when persisting to MongoDB. Another API might choose EJSON with BSON type wrappers if it serves administrative tooling or data exchange that must preserve exact types.

For typical frontend-facing APIs, you do not necessarily have to force clients to understand `$oid` or `$numberDecimal`. The real goal is a **consistent data type contract**, not forcing every API to return Extended JSON.

### 9.3. mongoexport/mongoimport and mongodump/mongorestore

These two tool pairs serve different purposes:

| Tool | Purpose | Primary Data Format |
|---|---|---|
| mongoexport | Export a collection for exchange via text files | JSON/Extended JSON or CSV depending on flags |
| mongoimport | Import data from JSON/Extended JSON or CSV | Reads text and creates documents in MongoDB |
| mongodump | Create a data dump for backup/migration | BSON dump and corresponding metadata |
| mongorestore | Restore data from mongodump | Reads BSON dump to recreate collections/indexes per tool capabilities |

Illustrative example exporting data in Canonical Extended JSON:

~~~bash
mongoexport --uri="mongodb://localhost:27017" --db=shop --collection=products --jsonFormat=canonical --out=products.json
~~~

The example command assumes you already have an accessible MongoDB instance at that address and permission to export the collection. If MongoDB has authentication enabled, configure the URI and credential mechanism appropriately; avoid writing real passwords into shell history.

With the standard default JSON export mode, each document may appear on **its own JSON line** (JSON Lines), rather than wrapping the entire file in a single JSON array. When reading the output from an external application, check how the export tool structures lines.

For **true backup/restore**, `mongodump`/`mongorestore` are generally better suited than `mongoexport`/`mongoimport` because they preserve BSON data and metadata for restoration according to the tools' design. However, a production backup strategy must also address consistency requirements, downtime, recovery objectives, and restore testing.

## 10. Common Misconceptions That Cause Bugs

| Misconception | Consequence | Proper Understanding and Handling |
|---|---|---|
| JSON and BSON are the same | Unclear why MongoDB needs its own data types | JSON is text; BSON is a binary format carrying type information. |
| BSON is always smaller than JSON | Inaccurate storage estimation | BSON adds overhead; actual size depends on the specific data. |
| Any 24-character hex string is an ObjectId | `_id` queries may fail to match | Check the actual `_id` type; convert to ObjectId only if the schema requires it. |
| ISO time strings are always stored by MongoDB as Date | Comparisons, sorting, and queries may have wrong semantics | Parse strings into Date before writing, or intentionally choose String per schema. |
| JSON numbers preserve precision in every environment | Large Int64 values get rounded | Use Long/Decimal128 and Canonical EJSON, or pass numbers as strings by contract when needed. |
| Double 19.90 is equivalent to Decimal128 | Loss of type semantics and decimal precision | Use Decimal128 for data requiring exact decimal arithmetic. |
| `JSON.parse` automatically understands `$oid`, `$date` | Produces plain objects instead of ObjectId/Date | Use `EJSON.parse` or explicitly map to BSON types. |
| Canonical and Relaxed are two database storage modes | Incorrect storage mental model | Both are text-based representations of BSON. |
| Copying mongosh objects directly into a JSON file | JSON parser throws syntax errors | Use valid JSON/Extended JSON or JavaScript code depending on the target. |
| BSON Timestamp is BSON Date | Wrong temporal data type | Timestamp serves specialized internal cases; Date is normally used for business timestamps. |
| EJSON wrappers can always be sent directly as BSON filters in any API | Driver/server interprets wrapper as nested object/operator | Run through an EJSON parser first or construct values using driver BSON classes. |

### 10.1. Distinguishing null, Missing Fields, and Other Types

The following three documents represent three distinct situations:

~~~json
{"name":"An","age":null}
{"name":"An"}
{"name":"An","age":"null"}
~~~

In the first document, the `age` field exists with a BSON Null value. In the second document, the `age` field does not exist. In the third document, `age` is a String containing the text `"null"`.

Some MongoDB query conditions treat `null` and missing fields similarly; use operators such as **$exists** or type checks when you need to distinguish them precisely. This is a document semantics issue and is not solved by switching between JSON, BSON, and EJSON.

### 10.2. Avoid Manually Stripping Wrappers Starting with $

When you see:

~~~json
{"value":{"$numberLong":"42"}}
~~~

do not strip the wrapper by grabbing the string `"42"` and parsing it into a generic `Number` arbitrarily. It represents a long integer that needs to be converted to the proper type. Likewise, keys named **$oid**, **$date**, and **$binary** carry meaning in Extended JSON; receiving an object from a plain JSON parser does not mean the corresponding BSON type was created.

Do not assume every object whose key starts with `$` is Extended JSON. MongoDB also uses operator names such as **$set**, **$in**, and **$gt** in queries and updates; those operators have their own semantics and are not BSON type wrappers.

## 11. Practice Exercises: Identification and Conversion

### Exercise 1: Identify the Actual Types

Inspect the following values:

~~~json
{
  "a": "2026-01-15T08:30:00Z",
  "b": {"$date":"2026-01-15T08:30:00Z"},
  "c": "66f1c2a4b1d2e3f405162738",
  "d": {"$oid":"66f1c2a4b1d2e3f405162738"},
  "e": 42,
  "f": {"$numberLong":"42"}
}
~~~

Task: if decoded under Extended JSON v2, state the BSON type of each field and explain why **a** differs from **b**, and **c** differs from **d**.

**Hint:** `a` and `c` are String; `b` is Date, `d` is ObjectId; `e` is a number according to how the parser/driver interprets standard numeric literals; `f` explicitly specifies Int64. Do not claim `e` is always Int32 without knowing the parser and BSON conversion rules.

### Exercise 2: Write Canonical Extended JSON

An inventory record has the following fields:

| Field | Required BSON Type | Value |
|---|---|---|
| _id | ObjectId | 66f1c2a4b1d2e3f405162738 |
| sku | String | KB-01 |
| stock | Int32 | 10 |
| soldTotal | Int64 | 9007199254740993 |
| price | Decimal128 | 199.90 |
| createdAt | Date | 2025-01-01T00:00:00Z |

Create the **Canonical Extended JSON** document using `$oid`, `$numberInt`, `$numberLong`, `$numberDecimal`, and `$date` wrapping `$numberLong`.

**Reference answer:**

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  },
  "sku": "KB-01",
  "stock": {
    "$numberInt": "10"
  },
  "soldTotal": {
    "$numberLong": "9007199254740993"
  },
  "price": {
    "$numberDecimal": "199.90"
  },
  "createdAt": {
    "$date": {
      "$numberLong": "1735689600000"
    }
  }
}
~~~

### Exercise 3: Detect Discrepancies During Import/Export

Suppose the database stores:

~~~text
_id        : ObjectId(...)
soldTotal  : Int64(9007199254740993)
createdAt  : BSON Date
~~~

A program exports:

~~~json
{
  "_id": "66f1c2a4b1d2e3f405162738",
  "soldTotal": 9007199254740992,
  "createdAt": "2025-01-01T00:00:00Z"
}
~~~

Identify at least three risks:

1. `_id` changed from ObjectId to String.
2. `soldTotal` lost 1 due to rounding through a numeric type that cannot preserve large Int64 values.
3. `createdAt` changed from BSON Date to String if there is no type conversion step during import.

Propose using Canonical Extended JSON with an appropriate EJSON serializer/parser for round-tripping BSON data, or defining an API schema with explicit type conversion at system boundaries.

### Exercise 4: Choose Formats Based on Requirements

For each requirement below, select the appropriate format and explain why:

- Returning a product list to a web application with a well-defined DTO: typically **JSON** following the API contract.
- Sending and receiving documents between a MongoDB driver and MongoDB server: **BSON**.
- Exporting documents to a text file while preserving Int32, Int64, Date, and Decimal128: prefer **Canonical Extended JSON**.
- Viewing documents in a human-readable text file while still showing ObjectId and Date: **Relaxed Extended JSON** can be convenient.
- Creating a dump for restoring MongoDB data: use **mongodump/mongorestore** and the tool's BSON dump format.

## 12. Checklist When Designing MongoDB Applications

When reading a document, separate three questions:

1. **What type does the data actually have in MongoDB?** For example, ObjectId, String, Int32, Int64, Double, Decimal128, or Date.
2. **Which format is the data currently displayed or exchanged in?** For example, plain JSON, Canonical EJSON, Relaxed EJSON, or `mongosh` syntax.
3. **Which component is responsible for type conversion?** For example, the MongoDB driver, EJSON parser, DTO layer, REST serializer, or import/export tool.

JSON is convenient for text exchange; BSON provides MongoDB's binary structure and rich data types; Extended JSON acts as the bridge to carry those types inside JSON-formatted text. Choosing the right format and converter helps prevent numeric precision loss, date/time discrepancies, and type-mismatched queries.
