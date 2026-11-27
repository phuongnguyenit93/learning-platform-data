# Declaring Validators with $jsonSchema and bsonType in MongoDB

MongoDB stores data in BSON document format. Documents in the same collection can have different fields and data types. This flexibility is useful during application development, yet it also introduces risks: a record might store **total** as a string instead of a number, miss **createdAt**, or contain a **status** value that the application does not know how to handle.

**Schema validation** lets you declare constraints directly on a collection. When an application inserts or updates a document, MongoDB can check the data against the **validator** and reject operations that fail the conditions. A common way to declare these rules is using the **$jsonSchema** operator together with the **bsonType** keyword to describe the document structure and accepted BSON types.

This lesson walks through writing validators from simple to nested structures, distinguishing **bsonType** from standard JSON types, creating and updating validators, controlling enforcement scope with **validationLevel** and **validationAction**, and applying them within a Java application development workflow.

## 1. Why Do We Need Schema Validation?

Suppose a retail application stores this document:

~~~javascript
{
  orderCode: "ORD-001",
  status: "NEW",
  total: NumberDecimal("149.90"),
  createdAt: ISODate("2026-11-14T03:00:00Z")
}
~~~

The application expects:

- **orderCode** is a non-empty string.
- **status** only accepts one of the allowed values.
- **total** is a Decimal128 decimal number and non-negative.
- **createdAt** is a BSON Date, not a timestamp string.

Without database-level constraints, another program could still write:

~~~javascript
{
  orderCode: "ORD-002",
  status: "UNKNOWN",
  total: "149.90",
  createdAt: "2026-11-14T03:00:00Z"
}
~~~

This is a structurally valid BSON document, but it violates the data contract the application requires. Missing shared rules can break queries, calculations, reports, or cross-service synchronization.

A validator brings foundational rules close to the data:

~~~text
Frontend / API / Batch job / Script / Java service
                     |
                     | insert / update / replace
                     v
             MongoDB Collection
                     |
              Validator rule
               /          \
            Valid        Invalid
              |               |
          Allow write   Reject write or warn
                       (per validationAction)
~~~

Schema validation is a **data control layer**, not a full replacement for application-level validation. The application still needs to validate input, provide user-friendly error messages, enforce business permissions, and manage transactions.

## 2. What Are validator, $jsonSchema, and bsonType?

| Component | Function | Example |
|---|---|---|
| **validator** | Collection option holding the document validation expression | validator: { $jsonSchema: ... } |
| **$jsonSchema** | Operator expressing schema rules in MongoDB-supported syntax | required, properties, bsonType |
| **bsonType** | Keyword declaring one or more accepted BSON data types | "string", "int", "date", "objectId" |
| **validationLevel** | Controls which documents are checked on write | "strict", "moderate", "off" |
| **validationAction** | Decides how to handle documents that violate the validator | "error", "warn" |

A simple validator:

~~~javascript
{
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name"],
      properties: {
        name: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  }
}
~~~

Meaning: the document must be a BSON object, contain the **name** field, and that field must be a string with at least one character. If **age** or another undescribed field is present, it is still allowed by default.

### 2.1. Difference Between a Schema and a Document

Data document:

~~~javascript
{
  name: "Lan",
  age: 22
}
~~~

Schema describing the rules:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    name: { bsonType: "string" },
    age: { bsonType: "int", minimum: 0 }
  }
}
~~~

**A schema does not contain a specific customer's data.** It describes which documents are accepted. One schema can apply to millions of documents in the same collection.

### 2.2. $jsonSchema Is Not the Entire JSON Schema Standard

MongoDB supports a **subset of JSON Schema keywords** and adds **bsonType** to reflect BSON data types. You should not blindly copy a JSON Schema designed for an HTTP API and assume MongoDB understands every keyword.

For example, familiar JSON Schema keywords may be unsupported in MongoDB or behave differently depending on the server version. Check the MongoDB documentation for your exact version when using less common keywords rather than assuming the validator implements all of modern JSON Schema.

More importantly, MongoDB checks the **actual BSON type stored in the document**. A string that looks like a date/time is still a BSON String; a 24-character hex string is still a String if the driver did not construct an ObjectId.

## 3. Declaring a Validator When Creating a Collection

Open MongoDB Shell (**mongosh**) and select the practice database:

~~~javascript
use validation_lab
~~~

Create an **orders** collection with mandatory validation checks:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderCode", "status", "total", "createdAt"],
      properties: {
        _id: {
          bsonType: "objectId"
        },
        orderCode: {
          bsonType: "string",
          minLength: 1
        },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        },
        total: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        createdAt: {
          bsonType: "date"
        }
      },
      additionalProperties: false
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

In this example:

1. **bsonType: "object"** requires the root document to be a BSON object.
2. **required** specifies four mandatory fields.
3. **properties** defines specific rules for each field.
4. **enum** restricts `status` to a discrete set of values.
5. **minimum** disallows negative totals.
6. **additionalProperties: false** rejects fields not listed in `properties`.
7. **validationLevel: "strict"** applies checks to inserts and document updates under strict rules.
8. **validationAction: "error"** rejects violating write operations.

Here, the **_id** field is declared even though it is not in **required**. MongoDB normally auto-generates `_id` as an ObjectId if a document is inserted without `_id`. When using **additionalProperties: false**, you must allow `_id` in **properties**; otherwise, documents will be rejected for containing an unlisted field.

If your application intentionally stores `_id` as a string or another BSON type, adjust the `_id` constraint accordingly. Not every MongoDB collection uses ObjectId for `_id`.

### 3.1. Attempting to Write a Valid Document

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-001",
  status: "NEW",
  total: NumberDecimal("149.90"),
  createdAt: new Date()
})
~~~

MongoDB receives the document, auto-generates `_id` if needed, and then checks the schema. With the configuration above, the document is valid because `total` is Decimal128, `createdAt` is Date, and the remaining fields meet the requirements.

Verify:

~~~javascript
db.orders.findOne({ orderCode: "ORD-001" })
~~~

### 3.2. Attempting to Write a Document with the Wrong Type

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-002",
  status: "NEW",
  total: "149.90",
  createdAt: new Date()
})
~~~

The operation is rejected because **total** is a BSON String. The string `"149.90"` looks like a monetary amount, but it is not Decimal128; the validator does not automatically coerce types to match application expectations.

Try another error:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-003",
  status: "SHIPPING",
  total: NumberDecimal("99.00"),
  createdAt: new Date()
})
~~~

The `status` field violates **enum** because the schema only allows `NEW`, `PAID`, or `CANCELLED`.

Try omitting a required field:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-004",
  status: "NEW",
  total: NumberDecimal("42.00")
})
~~~

This time **createdAt** is missing, so the document is rejected. Schema validation does not automatically populate `createdAt` or generate default values.

In a typical MongoDB environment, validator failures appear with the message **Document failed validation**, error code **121**, and—depending on server version and privileges—details explaining the failing fields. Error output formatting may vary between `mongosh` and drivers.

## 4. bsonType: Distinguishing BSON Data Types

MongoDB has more than just `number` and `string` as seen in JSON. BSON distinguishes multiple numeric, temporal, identifier, and binary types.

| Value to Store | bsonType | Creation Example in mongosh |
|---|---|---|
| String | "string" | "MongoDB" |
| Boolean | "bool" | true |
| Nested object | "object" | { city: "Hue" } |
| Array | "array" | ["A", "B"] |
| Null | "null" | null |
| 32-bit integer | "int" | NumberInt(12) |
| 64-bit integer | "long" | NumberLong("9007199254740993") |
| Double-precision float | "double" | NumberDouble("3.5") |
| Decimal128 | "decimal" | NumberDecimal("19.90") |
| Any common BSON numeric type | "number" | Int32, Int64, Double, or Decimal128 |
| BSON Date timestamp | "date" | ISODate("2026-01-15T08:30:00Z") |
| ObjectId | "objectId" | ObjectId("66f1c2a4b1d2e3f405162738") |
| Binary | "binData" | BinData(0, "AQID") |
| Timestamp | "timestamp" | Timestamp({ t: 1700000000, i: 1 }) |

BSON type names in **bsonType** do not always match type names in Java, JavaScript, or JSON Schema. For instance, **bool** is the name used in `bsonType`, whereas JSON Schema typically refers to **boolean**.

### 4.1. bsonType: "int" Differs from "long", "double", and "decimal"

Consider this schema:

~~~javascript
{
  bsonType: "object",
  properties: {
    quantity: {
      bsonType: "int",
      minimum: 0
    }
  }
}
~~~

This schema **only permits BSON Int32** for the `quantity` field. Values with the same mathematical meaning stored as Int64, Double, or Decimal128 are not automatically treated as Int32.

Explicit distinction example:

~~~javascript
NumberInt(5)
NumberLong("5")
NumberDouble("5")
NumberDecimal("5")
~~~

All four values represent the number five, yet they have different BSON types. This requires special attention when multiple Java, JavaScript, Python applications, or import tools write to the same collection.

If you want to accept multiple numeric types while still rejecting String:

~~~javascript
{
  bsonType: "number",
  minimum: 0
}
~~~

Or explicitly list the accepted numeric types:

~~~javascript
{
  bsonType: ["int", "long"],
  minimum: 0
}
~~~

The choice depends on the data contract:

- **int:** suitable when the entire system standardizes on 32-bit integers for a field.
- **long:** suitable for 64-bit counters or numeric IDs.
- **decimal:** suitable for values needing decimal precision, such as money per business rules.
- **number:** suitable when multiple BSON numeric types must be accepted, though less strict about storage representation.

Never conclude a value has the schema-required BSON type merely because it looks like a number on screen.

### 4.2. bsonType: "date" Does Not Accept ISO Strings

Example:

~~~javascript
{
  properties: {
    createdAt: {
      bsonType: "date"
    }
  }
}
~~~

Accepted:

~~~javascript
{ createdAt: ISODate("2026-01-15T08:30:00Z") }
~~~

Rejected:

~~~javascript
{ createdAt: "2026-01-15T08:30:00Z" }
~~~

The latter is a BSON String, even though it uses ISO-8601 timestamp formatting. In a Java application, map the appropriate date type via the MongoDB codec; in `mongosh`, use `Date`/`ISODate` instead of sending plain strings.

### 4.3. bsonType: "objectId" Does Not Accept Hex Strings

~~~javascript
{
  properties: {
    customerId: {
      bsonType: "objectId"
    }
  }
}
~~~

Accepted:

~~~javascript
{ customerId: ObjectId("66f1c2a4b1d2e3f405162738") }
~~~

Rejected:

~~~javascript
{ customerId: "66f1c2a4b1d2e3f405162738" }
~~~

Converting a hex string into an ObjectId must be handled by the application or driver according to data rules. The validator only checks the type of the value sent to MongoDB.

### 4.4. bsonType as an Array

A field can allow multiple BSON types:

~~~javascript
{
  properties: {
    nickname: {
      bsonType: ["string", "null"]
    }
  }
}
~~~

With this rule:

- **nickname: "Na"** is valid.
- **nickname: null** is valid.
- Omitting **nickname** is also valid, because it is not listed in `required`.
- **nickname: 123** is invalid.

This demonstrates that **required** and **bsonType** are two independent rules: one governs field presence, while the other validates the value when the field appears.

## 5. required and properties: Mandating Presence While Still Validating Values

Consider this schema:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    name: { bsonType: "string" },
    age: { bsonType: "int", minimum: 0 }
  }
}
~~~

| Document | Valid? | Reason |
|---|---|---|
| { name: "An" } | Yes | `name` is present with the right type; `age` is optional |
| { name: "An", age: NumberInt(20) } | Yes | `age` is Int32 and non-negative |
| { age: NumberInt(20) } | No | Missing `name` from `required` |
| { name: 99 } | No | `name` is present but not a string |
| { name: "", age: NumberInt(20) } | Yes | An empty string is still a string without `minLength` |
| { name: "An", age: null } | No | `null` does not match `bsonType` int |

To disallow empty strings:

~~~javascript
name: {
  bsonType: "string",
  minLength: 1
}
~~~

If you want to reject whitespace-only strings, add an appropriate **pattern** or validate normalized content in the application. For instance, `minLength: 1` does not reject `"   "`.

### 5.1. Can a Required Field Be null?

Yes, if the schema permits the null value:

~~~javascript
{
  required: ["notes"],
  properties: {
    notes: {
      bsonType: ["string", "null"]
    }
  }
}
~~~

The document **{ notes: null }** satisfies both `required` and `bsonType`. The document **{}** fails `required`. If business rules require `notes` to be a non-empty string, use `bsonType: "string"` together with length/pattern constraints.

### 5.2. What Happens If required Is Not Declared?

If you only write:

~~~javascript
{
  properties: {
    email: {
      bsonType: "string",
      pattern: "^[^@ ]+@[^@ ]+$"
    }
  }
}
~~~

A document missing **email** is still valid, because `properties` only validates `email` **if the field is present**. This is a common reason why an apparently strict schema still accepts documents with missing data.

## 6. Closing a Schema with additionalProperties

By default, a schema only constrains declared fields; documents can contain extra fields unless prohibited. For example:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    name: { bsonType: "string" }
  }
}
~~~

Can still accept:

~~~javascript
{
  name: "An",
  unexpectedField: 123
}
~~~

If you want to reject unlisted fields:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    _id: { bsonType: "objectId" },
    name: { bsonType: "string" }
  },
  additionalProperties: false
}
~~~

Now **unexpectedField** is rejected. The **_id** field is declared to remain compatible with standard MongoDB documents that carry `_id`; if your application uses an `_id` type other than ObjectId, adjust the constraint accordingly.

**Considerations when using additionalProperties: false:**

- Pros: catches field-name typos and blocks extraneous data outside the contract.
- Cons: whenever a new field is introduced, the validator must be updated in a controlled manner.
- For nested documents, **additionalProperties** must be placed at the exact object level you want to restrict. Closing the top-level schema does not automatically close inner objects unless their sub-schemas also declare it.

For records carrying dynamic metadata, you can intentionally allow an object-typed **metadata** field instead of leaving all root-level fields open.

## 7. Constraining Strings, Numbers, and Value Sets

Beyond `bsonType`, `$jsonSchema` supports common content-validation keywords.

### 7.1. Strings: minLength, maxLength, and pattern

~~~javascript
{
  bsonType: "string",
  minLength: 3,
  maxLength: 20,
  pattern: "^[A-Z0-9-]+$"
}
~~~

This example requires a code of 3–20 characters, accepting only uppercase ASCII letters, digits, or hyphens.

Sample values:

| Value | Result | Reason |
|---|---|---|
| "ORD-1001" | Valid | Matches length and pattern |
| "ab-01" | Invalid | Contains lowercase letters |
| "A" | Invalid | Shorter than `minLength` |
| 1001 | Invalid | Not a BSON String |

**Pattern** is a regular expression. Keep rules simple and test against real data, especially when strings contain Unicode or need complex rules like internationalized email addresses. A basic regex cannot replace full business validation.

### 7.2. Numbers: minimum, maximum, multipleOf

~~~javascript
{
  bsonType: "int",
  minimum: 1,
  maximum: 100
}
~~~

This rule fits quantities from 1 to 100 when the application consistently stores them as Int32.

Example of enforcing non-negative values:

~~~javascript
{
  bsonType: "decimal",
  minimum: NumberDecimal("0")
}
~~~

MongoDB supports constraints such as **minimum**, **maximum**, and **multipleOf** within its implemented JSON Schema scope. When validating money, do not rely solely on numeric types; the application still needs rounding rules, currency units, and valid ranges.

### 7.3. enum: Restricting to Specific Values

~~~javascript
{
  enum: ["PENDING", "PAID", "CANCELLED"]
}
~~~

A status field is usually a good fit for **enum**. Values must match both content and data type. If `status` evolves along a business workflow, `enum` only restricts the **set of storable states**—it does not guarantee every state transition is valid.

For instance, `enum` does not automatically block transitioning from `CANCELLED` back to `PAID`. State transition rules must be enforced in the application or in conditional updates that check the current state.

## 8. Nested Documents: properties and required at Each Level

MongoDB documents frequently contain objects inside objects. For example, an order:

~~~javascript
{
  orderCode: "ORD-010",
  shippingAddress: {
    recipient: "Lan",
    city: "Hanoi",
    postalCode: "100000"
  }
}
~~~

To validate `shippingAddress`, declare **bsonType: "object"** and nest **required** and **properties** inside it:

~~~javascript
{
  bsonType: "object",
  required: ["orderCode", "shippingAddress"],
  properties: {
    orderCode: {
      bsonType: "string",
      minLength: 1
    },
    shippingAddress: {
      bsonType: "object",
      required: ["recipient", "city"],
      properties: {
        recipient: {
          bsonType: "string",
          minLength: 1
        },
        city: {
          bsonType: "string",
          minLength: 1
        },
        postalCode: {
          bsonType: "string"
        }
      }
    }
  }
}
~~~

Here:

- The root document must include `shippingAddress`.
- `shippingAddress` must be an object, not a string or an array.
- Inside `shippingAddress`, **recipient** and **city** are mandatory.
- **postalCode** is optional.

**Top-level required does not cascade down to nested objects.** Each nested object needs its own `required` rule when subfields must be mandatory.

### 8.1. What If a Nested Field Can Be Absent?

If `shippingAddress` is omitted from the root-level `required` list, a document without an address is still accepted. However, whenever `shippingAddress` is present, all constraints declared underneath it still apply.

If `shippingAddress` can be null, declare `bsonType` to allow null and consider how sub-structure rules behave. Do not confuse an optional field with a field holding a null value.

## 9. Arrays: items, minItems, maxItems, and uniqueItems

An order containing a list of items:

~~~javascript
{
  items: [
    { sku: "PEN-01", quantity: NumberInt(2) },
    { sku: "BOOK-02", quantity: NumberInt(1) }
  ]
}
~~~

The schema can validate both the array type and its elements:

~~~javascript
{
  bsonType: "array",
  minItems: 1,
  maxItems: 50,
  items: {
    bsonType: "object",
    required: ["sku", "quantity"],
    properties: {
      sku: {
        bsonType: "string",
        minLength: 1
      },
      quantity: {
        bsonType: "int",
        minimum: 1
      }
    },
    additionalProperties: false
  }
}
~~~

Meaning:

- `items` must be a BSON Array.
- The array must contain at least 1 element and at most 50 elements.
- Every element must be an object.
- Every object must contain `sku` and `quantity` with the right types.
- Elements must not contain fields other than `sku` and `quantity`.

The **uniqueItems: true** constraint can require array elements to be distinct by full value comparison. However, it **does not enforce uniqueness on a single object field**. For example, two objects with the same `sku` but different `quantity` values are still distinct objects; if business rules require each `sku` to appear only once in the array, handle that rule separately.

## 10. A Complete Validator for a Products Collection

Now that each building block is clear, let's combine them into an example runnable in `mongosh`. Select the practice database:

~~~javascript
use validation_lab
~~~

Create the **products** collection:

~~~javascript
db.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "name", "price", "stock", "createdAt"],
      additionalProperties: false,
      properties: {
        _id: {
          bsonType: "objectId"
        },
        sku: {
          bsonType: "string",
          minLength: 3,
          maxLength: 30,
          pattern: "^[A-Z0-9-]+$"
        },
        name: {
          bsonType: "string",
          minLength: 1,
          maxLength: 150
        },
        price: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        stock: {
          bsonType: "int",
          minimum: 0
        },
        active: {
          bsonType: "bool"
        },
        createdAt: {
          bsonType: "date"
        },
        tags: {
          bsonType: "array",
          maxItems: 20,
          items: {
            bsonType: "string",
            minLength: 1
          }
        },
        dimensions: {
          bsonType: "object",
          required: ["width", "height"],
          additionalProperties: false,
          properties: {
            width: {
              bsonType: "number",
              minimum: 0
            },
            height: {
              bsonType: "number",
              minimum: 0
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Several design choices in this example:

- **sku** allows only characters matching the product code pattern.
- **price** is stored as Decimal128 rather than accepting any numeric type.
- **stock** must be a non-negative Int32.
- **active**, **tags**, and **dimensions** are optional; when present, they must match their declared types.
- **dimensions** is a nested object allowing only `width` and `height`.
- **_id** is permitted by `additionalProperties: false`, yet not required on insert because MongoDB can auto-generate it.

### 10.1. Inserting a Valid Product

~~~javascript
db.products.insertOne({
  sku: "PEN-001",
  name: "Blue ballpoint pen",
  price: NumberDecimal("12500.00"),
  stock: NumberInt(120),
  active: true,
  createdAt: new Date(),
  tags: ["stationery", "blue"],
  dimensions: {
    width: 1.1,
    height: 14.0
  }
})
~~~

The `width`/`height` values are accepted because the schema specifies **bsonType: "number"**. The `price` and `stock` fields are constructed with explicit type helpers to avoid differences in how languages or drivers infer numeric literals.

### 10.2. Inserting a Product Failing Multiple Rules

~~~javascript
db.products.insertOne({
  sku: "pen 002",
  name: "",
  price: NumberDouble("12500.0"),
  stock: NumberInt(-5),
  createdAt: "2026-11-14T03:00:00Z",
  unknownField: true
})
~~~

This document violates multiple rules:

1. `sku` has lowercase letters and a space, failing `pattern`.
2. `name` is an empty string, violating `minLength`.
3. `price` is Double instead of Decimal128.
4. `stock` is less than 0.
5. `createdAt` is String instead of Date.
6. `unknownField` is disallowed by `additionalProperties: false`.

With `validationAction: "error"`, the write is rejected. Typically, the application should give the user clear input error feedback before sending the document to MongoDB.

### 10.3. Creating a Unique Index for sku

The validator above **does not ensure `sku` is unique across documents**. If two documents share the same `sku` with different `_id` values and both satisfy the schema, the validator will not stop cross-document duplication.

Uniqueness requires an index:

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true }
)
~~~

This clearly illustrates the boundary:

| Requirement | Appropriate Mechanism |
|---|---|
| `sku` must be a string matching a pattern | $jsonSchema |
| `price` must be a non-negative Decimal128 | $jsonSchema |
| `stock` must be a non-negative Int32 | $jsonSchema |
| Each `sku` appears only once in the collection | Unique index |
| Which products user A is allowed to edit | Authorization / business conditions |
| Transitioning order states in valid order | Business logic, conditional updates, or appropriate transactions |

Do not expect a single document schema to replace all cross-document constraints or business rules.

## 11. Updating a Validator on an Existing Collection with collMod

**db.createCollection()** is for creating new collections. When a collection already exists and you want to update its validator or validation options, use the **collMod** command where supported.

Suppose the **legacyUsers** collection already contains data:

~~~javascript
db.legacyUsers.insertMany([
  { name: "An", age: NumberInt(20) },
  { name: "Binh", age: NumberInt(30) }
])
~~~

Attach a validator:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name"],
      properties: {
        name: {
          bsonType: "string",
          minLength: 1
        },
        age: {
          bsonType: "int",
          minimum: 0
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

The `collMod` command updates the rules applied to subsequent writes. **Declaring a validator does not automatically fix, delete, or cast existing documents**.

If the collection already contains invalid records, they remain in the database after the schema change. The `strict` setting takes effect when those documents are updated, so a data assessment plan is needed before enabling strict enforcement.

### 11.1. Changing Only the Violation Action

You can change `validationAction` without re-declaring the entire schema:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "warn"
})
~~~

Or switch back to rejecting writes:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "error"
})
~~~

During a migration, changing one option at a time in a controlled way lowers the risk of accidentally overwriting a complex validator with a simpler one.

### 11.2. Viewing the Currently Stored Validator

~~~javascript
db.getCollectionInfos({ name: "legacyUsers" })
~~~

The output includes collection metadata and stored options such as `validator` or `validationLevel`/`validationAction` when configured. Depending on MongoDB version, metadata display can vary; focus on the **options** object for the matching collection name.

You can list collections with:

~~~javascript
db.getCollectionNames()
~~~

If checking from an administrative tool, ensure the account has appropriate privileges to read metadata. Never assume a collection was created with the intended validator simply because its name exists.

## 12. validationLevel: strict, moderate, and off

**validationLevel** determines the scope of checks MongoDB performs when documents are inserted or updated.

| validationLevel | New Inserts | Updates to Currently Valid Documents | Updates to Currently Invalid Documents | Meaning |
|---|---|---|---|---|
| **strict** | Checked | Checked | Checked | Strict enforcement mode for write operations |
| **moderate** | Checked | Checked | Strict checks not enforced | Supports gradual rollout when legacy invalid data exists |
| **off** | Not checked | Not checked | Not checked | Disables validator execution |

Key takeaway: **moderate** still checks new documents. It also checks updates to currently valid documents, while allowing already-invalid historical records to be updated without immediately satisfying the entire schema.

For example, the collection contains an old document:

~~~javascript
{
  name: 123,
  age: NumberInt(25)
}
~~~

The new schema requires `name` to be a String. Under **strict**, an update to that document may be rejected if the post-update document still violates the validator. Under **moderate**, MongoDB skips applying the validator when updating a document that was already schema-invalid at evaluation time.

### 12.1. Why Understand moderate?

`moderate` helps when rolling out a new schema on a long-lived collection where fixing every record in one pass is not feasible. However, it also means invalid documents **can persist or continue to be updated while still invalid**.

Therefore, treat `moderate` as an intentional transitional step, not a permanent setting to ignore violations indefinitely.

### 12.2. Changing the Validation Level

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationLevel: "moderate"
})
~~~

Once legacy data is cleaned up and all writers are updated:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationLevel: "strict"
})
~~~

Switching from `moderate` to `strict` does not automatically re-validate or repair all existing documents at the moment `collMod` runs. Auditing the existing dataset is a separate step.

## 13. validationAction: error and warn

**validationAction** determines how MongoDB reacts when a write operation violates the validator (for documents within the scope of `validationLevel`).

### 13.1. error: Reject Violating Documents

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "error"
})
~~~

Choose this once rules are stable and the application requires new data to comply with the schema. A violating document triggers a **Document failed validation** error instead of being saved.

A Java application should catch the driver exception and map it to an appropriate response, avoiding leaking internal database structures to clients.

### 13.2. warn: Log Warnings While Still Allowing Writes

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "warn"
})
~~~

In this mode, MongoDB can record violations in the server log while still **allowing the write operation to proceed**. This is helpful for observing violation rates before turning on rejections, especially when multiple legacy applications write to the database.

**Warn is not a data integrity protection mechanism.** Violating data is still persisted; if the system needs hard constraints, switch back to `error` after fixing non-compliant writers.

### 13.3. Combining validationLevel and validationAction

The two options answer two distinct questions:

~~~text
validationLevel:
    "Which documents will be checked?"

validationAction:
    "When a document is checked and violates the rules,
     what should MongoDB do?"
~~~

Examples:

| Level | Action | Typical Outcome |
|---|---|---|
| strict | error | Checks all relevant inserts/updates and rejects violations |
| strict | warn | Checks broadly and logs warnings without blocking writes |
| moderate | error | Blocks invalid inserts and invalid updates to valid docs; allows gradual transition for invalid historical data |
| moderate | warn | Observes violations within `moderate` scope without blocking writes |
| off | error or warn | Validator is inactive, so `action` has no validation effect in `off` mode |

Newer MongoDB versions may offer additional action options; check your exact server version before deploying. The examples here use the two standard modes: **error** and **warn**.

## 14. How Does the Validator Apply to Updates?

Schema validation is not limited to inserts. When an update causes the resulting document to violate the schema, MongoDB can reject the operation if `validationLevel`/`validationAction` require checking and blocking.

Suppose `products` has an Int32 `stock` field:

~~~javascript
db.products.updateOne(
  { sku: "PEN-001" },
  { $set: { stock: NumberInt(95) } }
)
~~~

This operation is valid. However:

~~~javascript
db.products.updateOne(
  { sku: "PEN-001" },
  { $set: { stock: "ninety-five" } }
)
~~~

This is invalid because `stock` becomes a String.

Similarly:

~~~javascript
db.products.updateOne(
  { sku: "PEN-001" },
  { $unset: { createdAt: "" } }
)
~~~

This fails because `createdAt` is in **required**. MongoDB validates the resulting document state after the update rather than merely inspecting the `$set` or `$unset` operator names.

### 14.1. Must an Upsert Satisfy the Validator?

Yes. An upsert can create a new document if no matching record exists. That new document must satisfy the validator whenever `validationLevel` is active:

~~~javascript
db.products.updateOne(
  { sku: "BOOK-001" },
  {
    $setOnInsert: {
      name: "Notebook",
      price: NumberDecimal("25000.00"),
      stock: NumberInt(10),
      createdAt: new Date()
    }
  },
  { upsert: true }
)
~~~

If the record does not yet exist, the filter fields and `$setOnInsert` construct the new document; they must satisfy the schema. Never assume an upsert bypasses validation just because the call uses `updateOne`.

### 14.2. Bulk Writes and Transactions

Bulk writes and writes inside transactions are also subject to the validator. When a write violates validation, error reporting and whether the rest of the batch continues depend on the API, ordered vs. unordered mode, and transaction context. Applications must handle errors per driver contract and never assume an entire batch succeeds if one document is invalid.

## 15. Legacy Data: Auditing, Fixing, and Safely Deploying Validators

Adding a validator to a collection with substantial existing data requires a migration strategy. **Adding a validator does not mean the existing collection is clean.**

A typical workflow:

1. Define the target schema from the business contract and real BSON types.
2. Audit legacy documents; categorize missing fields, wrong types, duplicate keys, and invalid values.
3. Update application/worker write code to emit the correct BSON types.
4. Deploy the validator in an observation mode where appropriate, such as `strict` + `warn`.
5. Remediate legacy data via rerunnable migrations with a backup/rollback plan.
6. Switch to `strict` + `error` once the dataset and all writers are ready.
7. Monitor post-deployment write errors to catch clients still using the old schema.

### 15.1. Finding Documents That Do Not Match a Schema

Besides defining collection validators, the **$jsonSchema** operator can be used inside query filters. Example schema checking `name` and `age`:

~~~javascript
const userRules = {
  bsonType: "object",
  required: ["name"],
  properties: {
    name: {
      bsonType: "string",
      minLength: 1
    },
    age: {
      bsonType: "int",
      minimum: 0
    }
  }
};

// Documents matching the schema
db.legacyUsers.find({
  $jsonSchema: userRules
});

// Documents failing the schema
db.legacyUsers.find({
  $nor: [
    { $jsonSchema: userRules }
  ]
}).limit(20);
~~~

This technique is useful for surveying legacy data. On large collections, schema-evaluation queries can be expensive; schedule audits thoughtfully rather than scanning sensitive datasets under peak load.

### 15.2. Validators Do Not Perform Automatic Type Coercion

Suppose a record has:

~~~javascript
{
  name: "An",
  age: "25"
}
~~~

A schema with **bsonType: "int"** does not automatically convert `"25"` into Int32. Conversion is the responsibility of a migration or the application—for instance, after verifying the input string can safely parse as an integer.

Never blindly convert every string to a number or date: `"00123"` could be an identifier needing leading zeros, and a date without a timezone can change meaning.

### 15.3. Schema Evolution When Adding a New Field

Suppose `products` needs a new **category** field. If that field is meant to become mandatory, proceed sequentially:

~~~text
Phase 1: New application version starts writing category
Phase 2: Legacy data is backfilled with appropriate category values
Phase 3: Audit for remaining missing or wrong-type records
Phase 4: Validator adds category to required
Phase 5: Monitor post-rollout write errors
~~~

Adding `category` to `required` immediately while older clients are still omitting it—or before legacy documents are updated—can break normal updates under `strict` mode.

## 16. Why Doesn't a Validator Replace Java Application Validation?

An HTTP API can use DTOs, Jakarta Bean Validation, and business checks before constructing a MongoDB document. Example concept:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.math.BigDecimal;

public record CreateProductRequest(
        @NotBlank String sku,
        @NotBlank String name,
        @NotNull @PositiveOrZero BigDecimal price,
        @NotNull @PositiveOrZero Integer stock
) {
}
~~~

This is application-layer validation: it gives users fast feedback before hitting the database. When mapping to MongoDB, the application must also ensure:

- `BigDecimal` is stored as **Decimal128** if the schema requires `bsonType: "decimal"`.
- `Integer` is stored as **Int32** via the driver's codec/mapping configuration as intended.
- Creation timestamps are stored as **BSON Date** rather than strings.
- Server-owned fields such as `_id` or `createdAt` are not blindly trusted from client input.

Example using the Java MongoDB Sync Driver with explicit types:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.Date;

public class InsertValidatedProduct {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Document product = new Document("sku", "PEN-JAVA-01")
                .append("name", "Java Pen")
                .append("price", new Decimal128(new BigDecimal("12500.00")))
                .append("stock", 12)
                .append("createdAt", new Date());

        try (MongoClient client = MongoClients.create(uri)) {
            client.getDatabase("validation_lab")
                    .getCollection("products")
                    .insertOne(product);
        }
    }
}
~~~

This snippet demonstrates constructing **Decimal128**, **Int32** (a Java `Integer` encoded accordingly by the standard BSON codec), and **Date**. It requires a compatible `mongodb-driver-sync` dependency and a **products** collection created with the matching validator.

### 16.1. Validators Are Enforced in the Database

If a Java application uses `MongoRepository` or `MongoTemplate`, Spring Data MongoDB's object mapping creates BSON documents via its mapping layer. MongoDB still executes the configured collection validator regardless of whether inserts arrive from `mongosh`, the Java driver, or another service.

The benefit is a single shared constraint layer across multiple write sources. Even so, every writer must be built to send the **correct BSON types**, not merely valid JSON shapes.

### 16.2. Handling DocumentValidationFailure

When a write is rejected by the schema, the driver throws a write exception containing details from MongoDB. The application should:

1. Log internally with context while masking sensitive data.
2. Return an appropriate input or data-processing error for the API.
3. Never auto-retry the same schema-invalid document infinitely.
4. Track errors by collection and write source to fix broken data contracts.

Do not forward raw database errors or full document contents holding personal data back to the frontend just to display a validation reason.

## 17. What Requirements Does a Validator Not Solve?

Schema validation is very helpful, yet it has clear boundaries.

| Requirement | Fully Solved by $jsonSchema? | Complementary Mechanism |
|---|---|---|
| Check required fields | Yes | `required` |
| Check BSON types | Yes | `bsonType` |
| String must match a pattern | Yes, within supported regex scope | `pattern` |
| Number must fall within a valid range | Yes | `minimum`, `maximum` |
| Array must have a valid element count | Yes | `minItems`, `maxItems` |
| `sku` unique across the entire collection | No | Unique index |
| `customerId` points to an existing customer | Not automatically guaranteed | Business check or appropriate data model |
| Which documents a user may modify | No | Authorization, query conditions |
| Valid step-by-step state transitions | Not fully via `enum` | Business rules and conditional updates |
| Auto-generate default fields | No | Application code or write pipeline |
| Auto-fix documents saved before schema existed | No | Migration |
| Encryption, security, and access control | No | MongoDB and application security mechanisms |

Certain cross-field constraints can be expressed using query operators outside `$jsonSchema` in a validator, but keep rules readable and maintainable—avoid turning database validators into a dumping ground for complex business logic.

## 18. Operations, Privileges, and Common Errors

### 18.1. Bypassing Document Validation

MongoDB supports **bypassDocumentValidation** on certain write operations when the client holds appropriate privileges. This is a special administrative or migration feature; never treat a validator as an absolute barrier if accounts are permitted to bypass it.

Illustrative command-level insert example:

~~~javascript
db.runCommand({
  insert: "legacyUsers",
  documents: [
    { name: 123 }
  ],
  bypassDocumentValidation: true
})
~~~

The command can write a schema-invalid document **only if** the user account and configuration allow bypassing validation. Never run this against production data without a clear migration plan. Standard application users should follow least privilege and never use bypass as a workaround for write failures.

### 18.2. Typical Failure Scenarios

| Symptom | Common Cause | Resolution |
|---|---|---|
| Write fails with `Document failed validation` | Document violates one or more rules | Inspect the validator and actual BSON types of the fields |
| `total` looks numeric yet is rejected | Stored as String/Double instead of Decimal128 | Construct proper Decimal128 in the app/driver |
| `createdAt` has ISO-8601 format yet fails type check | Value was sent as a String | Convert to BSON Date when building the document |
| Document missing `name` still inserts | `properties` is present without `required` | Add `name` to `required` |
| Cannot insert with `additionalProperties: false` | `_id` or a new field was not declared | Declare `_id` and allowed fields, or adjust policy |
| Bad data still enters despite schema | `validationAction` is `warn`, `validationLevel` is `off`, or bypass is used | Check metadata and write privileges |
| `createCollection` reports namespace already exists | Collection already exists | Use `collMod` to update the validator where supported |
| Invalid documents remain after enabling `strict` | Existing data is not auto-repaired or deleted | Audit and migrate legacy data |
| Only certain updates fail after enabling schema | Update violates `required`/type, or existing doc is invalid | Inspect document state before/after update; plan migration |
| Two products with duplicate `sku` still save | `$jsonSchema` does not check cross-document uniqueness | Create a unique index |
| Validation fails after changing Java model | Codec/mapping emits a BSON type differing from schema | Verify ObjectId, Date, int/long/double/decimal against stored schema |

### 18.3. Inspecting Validators and Checking BSON Types

View metadata:

~~~javascript
db.getCollectionInfos({ name: "products" })
~~~

Inspect actual BSON types of fields with aggregation:

~~~javascript
db.products.aggregate([
  {
    $project: {
      sku: 1,
      priceType: { $type: "$price" },
      stockType: { $type: "$stock" },
      createdAtType: { $type: "$createdAt" }
    }
  },
  { $limit: 10 }
])
~~~

The output displays type names such as **decimal**, **int**, and **date**. This is useful when data arrives from multiple sources and you are unsure which BSON types a driver emitted.

### 18.4. Avoiding Abrupt Schema Changes

Enabling `strict` + `error` can break writes from older application versions even when external APIs have not changed. When changing a data contract, execute a transition plan covering auditing, updating all writers, migrating data, and monitoring errors. In multi-service architectures, code deployments and schema updates must be coordinated.

## 19. Practice Exercises

### Exercise 1. Create a Students Collection

Create a **students** collection with these requirements:

- **studentCode:** required, String, 3 to 15 characters.
- **fullName:** required, String, non-empty.
- **age:** optional, Int32, between 16 and 100.
- **enrolledAt:** required, BSON Date.
- **skills:** optional, Array of at most 10 elements, each a String.
- Allow default `_id`; disallow any other fields.
- Use `strict` and `error`.

**Reference solution:**

~~~javascript
db.createCollection("students", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentCode", "fullName", "enrolledAt"],
      additionalProperties: false,
      properties: {
        _id: { bsonType: "objectId" },
        studentCode: {
          bsonType: "string",
          minLength: 3,
          maxLength: 15
        },
        fullName: {
          bsonType: "string",
          minLength: 1
        },
        age: {
          bsonType: "int",
          minimum: 16,
          maximum: 100
        },
        enrolledAt: {
          bsonType: "date"
        },
        skills: {
          bsonType: "array",
          maxItems: 10,
          items: { bsonType: "string" }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Test with a valid document:

~~~javascript
db.students.insertOne({
  studentCode: "ST-001",
  fullName: "Lan",
  age: NumberInt(21),
  enrolledAt: new Date(),
  skills: ["Java", "MongoDB"]
})
~~~

Then try replacing **age** with string `"21"`, replacing **enrolledAt** with an ISO string, or omitting **fullName** to observe the errors.

### Exercise 2. Distinguishing required and nullable

A **phone** field is declared as:

~~~javascript
phone: {
  bsonType: ["string", "null"]
}
~~~

Explain the difference between these cases:

1. Document omits `phone`.
2. `phone` is `null`.
3. `phone` is `"0900000000"`.
4. `phone` is `NumberLong("900000000")`.

**Hint:** the first three cases are valid if `phone` is not in `required`; the fourth has the wrong type. When `phone` is added to `required`, the first case becomes invalid, whereas `phone: null` remains valid.

### Exercise 3. Validator vs. Unique Index

System requirements for `email`:

- Must be String with a basic pattern.
- Must not repeat across two different users.

Identify which part uses `$jsonSchema` and which requires a unique index. Explain why `enum` or `required` alone cannot guarantee email uniqueness across a collection.

### Exercise 4. Deploying a Schema on Legacy Data

The **employees** collection already contains many records where `salary` is sometimes String and sometimes Double. The new schema requires non-negative Decimal128.

Propose a rollout plan:

1. Inventory existing `salary` types using `$type`.
2. Finalize currency unit and conversion policy.
3. Update write code to emit Decimal128.
4. Convert legacy data that can be safely migrated and handle exceptions.
5. Add the validator and monitor warnings.
6. Enable `strict` + `error` once data and clients are aligned.

Explain why switching `validationAction` to `error` right at the start can break writes from applications still using legacy types.

### Exercise 5. Finding Schema-Violating Documents

Run this query:

~~~javascript
db.students.find({
  $nor: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["studentCode", "fullName", "enrolledAt"],
        properties: {
          studentCode: { bsonType: "string" },
          fullName: { bsonType: "string" },
          enrolledAt: { bsonType: "date" }
        }
      }
    }
  ]
})
~~~

Explain why this query finds documents failing **the smaller schema written inside the query**, rather than automatically copying all rules from the existing collection validator. For a complete audit, reuse the exact target schema rules so no conditions are missed.

## 20. Key Principles to Remember

1. **$jsonSchema** describes document structure and value constraints; **bsonType** specifies the actual BSON type stored.
2. **required** only checks field presence; to enforce field type and value constraints, declare the field in **properties** as well.
3. For nested objects and arrays, place rules at the right nesting level; **additionalProperties: false** must account for MongoDB's `_id` field.
4. **validationLevel** determines checking scope; **validationAction** determines whether failures warn or reject writes.
5. Adding or modifying a validator **does not automatically convert legacy data**. Schema changes require migration planning, writer updates, and data verification.
6. Schema validation checks individual documents, while cross-document uniqueness requires a **unique index**, and other business rules must be designed separately.

Declaring strict validators turns MongoDB into a shared enforcement point across multiple applications and scripts writing data. When you clearly understand **$jsonSchema**, **bsonType**, nested rules, and validation options, you can enjoy the flexibility of a document database while maintaining a consistent data contract.
