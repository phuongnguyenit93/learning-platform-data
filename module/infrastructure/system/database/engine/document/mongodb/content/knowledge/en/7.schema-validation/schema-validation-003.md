# Required Fields, Enums, Value Ranges, and String Rules in MongoDB Schema Validation

MongoDB is a document database with a **flexible schema**: documents in the same collection do not have to share identical fields or data types. While that flexibility speeds up development, it also introduces the risk of malformed data—such as a product missing a `sku`, a misspelled `"publised"` status, negative inventory counts, or improperly formatted codes.

**Schema validation** lets you place validation rules **on the MongoDB side** when applications write documents. This lesson focuses on four common rule groups:

1. **Required fields:** which fields must be present in a document?
2. **Enums:** which values is a field permitted to accept?
3. **Value ranges:** within what bounds must numeric values fall?
4. **String rules:** what length and format must strings satisfy?

After completing the exercises, you will be able to write validators with `$jsonSchema`, interpret validation failures, distinguish missing fields from `null` values, update rules with `collMod`, and understand how to apply schemas to existing data.

## 1. Where Does Schema Validation Fit in the Write Flow?

Consider a `products` collection written to by multiple sources: an admin portal, a REST API, batch imports, and automated jobs. Each client may validate input before writing, yet relying solely on application validation does not guarantee every write path enforces the same contract.

~~~text
Web app ───────────┐
REST API ──────────┤
Import script ─────┼──> MongoDB: products
Batch job ─────────┘          |
                              v
                       Collection validator
                         |             |
                      Valid         Invalid
                         |             |
                      Accept      Reject write
                                  (if action=error)
~~~

MongoDB provides a **collection-level `validator`**, commonly using the `$jsonSchema` operator to describe document shape, BSON types, and content constraints. When `validationAction` is `"error"`, any write operation that produces a non-conforming document is rejected.

Example business schema:

| Field | Expected Rule | Valid Example |
| --- | --- | --- |
| `sku` | Required, string 4–12 chars, leading uppercase letter, followed only by A–Z, 0–9, `_`, or `-` | `"MOUSE-01"` |
| `title` | Required, string 3–120 chars | `"Wireless mouse"` |
| `status` | Required, only `draft`, `published`, or `archived` | `"draft"` |
| `stock` | Required, BSON int32, range 0–100000 | `Int32(30)` |
| `price` | Required, BSON Decimal128, non-negative | `Decimal128("259000.00")` |
| `note` | Optional; if present, string at most 250 chars | `"Intra-city delivery"` |

This is a **data rule set**, not a copy of a Java entity or a frontend JSON Schema. The contract in MongoDB must account for **BSON types**, especially for numbers.

## 2. Preparing the Environment and Collection

The commands below run in **mongosh** connected to a running MongoDB instance. Use a dedicated database for this lesson.

~~~javascript
const labDb = db.getSiblingDB("schema_validation_lab");

// Only drops the practice collection in this database.
// If you already have data to keep, skip drop() and use another name.
labDb.products.drop();
~~~

`db.createCollection()` can declare a `validator` at creation time. Let's start with a complete schema for `products`:

~~~javascript
labDb.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "title", "status", "stock", "price"],
      properties: {
        sku: {
          bsonType: "string",
          minLength: 4,
          maxLength: 12,
          pattern: "^[A-Z][A-Z0-9_-]{3,11}$",
          description: "SKU must be 4-12 chars starting with A-Z"
        },
        title: {
          bsonType: "string",
          minLength: 3,
          maxLength: 120,
          description: "Product title must be between 3 and 120 chars"
        },
        status: {
          bsonType: "string",
          enum: ["draft", "published", "archived"],
          description: "Status must be in the allowed list"
        },
        stock: {
          bsonType: "int",
          minimum: 0,
          maximum: 100000,
          description: "Stock is an int32 from 0 to 100000"
        },
        price: {
          bsonType: "decimal",
          minimum: 0,
          description: "Unit price must be a non-negative Decimal128"
        },
        note: {
          bsonType: "string",
          maxLength: 250
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

**Structure to remember:**

- `bsonType: "object"`: the entire document must be a BSON object.
- `required`: list of **field names that must exist**.
- `properties`: constraints applied **when the corresponding field appears**.
- `bsonType` inside each property: enforces BSON type, e.g. `"string"`, `"int"`, `"decimal"`.
- `enum`: lists accepted values.
- `minimum`/`maximum`: numeric bounds.
- `minLength`/`maxLength`/`pattern`: string constraints.
- `validationLevel` and `validationAction`: control validation scope and reaction on failure.

By default, MongoDB still permits **undeclared** fields in `properties` because we have not set `additionalProperties: false`. The section on additional field rules explains when to tighten this.

### 2.1. Inserting a Valid Document

~~~javascript
labDb.products.insertOne({
  _id: "P-001",
  sku: "MOUSE-01",
  title: "Wireless mouse",
  status: "draft",
  stock: Int32(30),
  price: Decimal128("259000.00"),
  note: "Intra-city delivery"
});

labDb.products.findOne({ _id: "P-001" });
~~~

The operation succeeds because the document has all five required fields and every value satisfies its rules.

**Regarding numeric types:** `stock` is explicitly created with `Int32(...)`, and `price` with `Decimal128(...)`. Passing a plain JavaScript Number can produce a different BSON type than intended; the schema catches such mismatches when `bsonType` is tightly specified.

## 3. Required Fields with `required`

### 3.1. Presence Differs from Having a Valid Value

`required` is an **array of field names** at the object level being checked:

~~~javascript
{
  bsonType: "object",
  required: ["sku", "status"],
  properties: {
    sku: { bsonType: "string" },
    status: { bsonType: "string" }
  }
}
~~~

This means:

- `sku` completely absent → invalid.
- `sku: null` present → **satisfies "field exists"**, yet still **invalid** against `bsonType: "string"`.
- `sku: ""` present → satisfies `required` and `bsonType: "string"`, though if business logic forbids empty strings you must add `minLength` or `pattern`.

On the `products` validator, try writing a document missing the `sku` field:

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-MISSING",
    title: "Mechanical keyboard",
    status: "draft",
    stock: Int32(5),
    price: Decimal128("900000.00")
  });
} catch (error) {
  print("Rejected: " + error.message);
}
~~~

MongoDB rejects the operation because `sku` is in `required`. With `validationAction: "error"`, the error typically has code **121 (DocumentValidationFailure)** and details about the failing rule, depending on server and driver versions.

### 3.2. Optional Fields Must Still Have the Right Type

`note` is not in `required`, so a document **without `note`** is allowed. However, if `note` is present, it must still be a string of at most 250 characters.

~~~javascript
// Valid: no note field.
labDb.products.insertOne({
  _id: "P-002",
  sku: "KEY-200",
  title: "Mechanical keyboard",
  status: "draft",
  stock: Int32(7),
  price: Decimal128("900000.00")
});

// Invalid: note is present, but null
// does not match bsonType "string".
try {
  labDb.products.updateOne(
    { _id: "P-002" },
    { $set: { note: null } }
  );
} catch (error) {
  print("Note error: " + error.message);
}
~~~

If business logic permits either a string or `null`, change the rule to:

~~~javascript
note: {
  bsonType: ["string", "null"],
  maxLength: 250
}
~~~

`required` does not generate default values. If you want defaults for a field, implement them in the application or write pipeline; do not expect MongoDB to auto-insert `status: "draft"` just because an enum is declared.

### 3.3. `required` with Nested Objects

Each object needs its **own `required` at its exact level**. For instance, a `shipping` field is optional, yet if `shipping` is present, both `city` and `postalCode` are required:

~~~javascript
{
  bsonType: "object",
  properties: {
    shipping: {
      bsonType: "object",
      required: ["city", "postalCode"],
      properties: {
        city: {
          bsonType: "string",
          minLength: 2
        },
        postalCode: {
          bsonType: "string",
          pattern: "^[0-9]{5,6}$"
        }
      }
    }
  }
}
~~~

Because `shipping` is not in the **outermost** object's `required`, omitting it completely is still valid. However, a document containing `shipping: { city: "Hanoi" }` is invalid because `postalCode` is missing.

If `shipping` must always appear, add `"shipping"` to the outermost object's `required` array.

## 4. Allowed Value Lists with `enum`

`enum` defines a **finite set of values** that a field may hold. Product `status` field:

~~~javascript
status: {
  bsonType: "string",
  enum: ["draft", "published", "archived"]
}
~~~

Meaning of these three values:

| Value | Description in Example |
| --- | --- |
| `draft` | Product is being drafted |
| `published` | Product is published |
| `archived` | Product is archived/hidden from active flows |

If an application accidentally writes `"publised"`, MongoDB catches the mistake instead of creating an unintended status outside the data contract.

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-ENUM",
    sku: "MOUSE-02",
    title: "Wired mouse",
    status: "publised",       // Misspelled
    stock: Int32(10),
    price: Decimal128("99000.00")
  });
} catch (error) {
  print("Enum error: " + error.message);
}
~~~

**Notes on using enum:**

- Values must match the declared list exactly; `"PUBLISHED"` and `"published"` are not treated as equivalent in the list above.
- `enum` does not enforce valid state transitions such as `draft → published → archived`. It only checks whether the **final value** written belongs to the allowed set.
- When adding a new value to an enum, update the API contract, clients, data, and validator according to a rollout plan.
- If the field is optional, omitting it remains valid unless another rule requires it.
- If `null` is valid by business rules, configure both `enum` and `bsonType` accordingly—for example, `enum: ["draft", null]` paired with `bsonType: ["string", "null"]`.

Avoid using a huge `enum` listing thousands of ever-changing product codes or partner IDs; reference data, a separate collection, or application-level validation is more appropriate there.

## 5. Numeric Bounds with `minimum` and `maximum`

For numeric fields, MongoDB can use lower and upper bounds to reject out-of-range values:

~~~javascript
stock: {
  bsonType: "int",
  minimum: 0,
  maximum: 100000
}
~~~

In this example, both **0** and **100000** are valid. `minimum` and `maximum` bounds are **inclusive**. Values `-1` and `100001` are rejected.

| BSON Value of `stock` | Valid? | Reason |
| --- | --- | --- |
| `Int32(0)` | Yes | Equals lower bound |
| `Int32(500)` | Yes | Within range |
| `Int32(100000)` | Yes | Equals upper bound |
| `Int32(-1)` | No | Less than 0 |
| `Int32(100001)` | No | Greater than 100000 |
| `Long("50")` | No | Value 50 is in range, but BSON type is long |
| `"50"` | No | String, not int32 |

Try updating past the business domain range:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $set: { stock: Int32(-1) } }
  );
} catch (error) {
  print("Range error: " + error.message);
}
~~~

Because validation evaluates the **post-update document**, the operation is rejected and `stock` in `P-001` keeps its previous value.

### 5.1. BSON Type and Value Range Are Two Separate Constraints

Suppose `price` is a unit price that must be stored as Decimal128:

~~~javascript
price: {
  bsonType: "decimal",
  minimum: 0
}
~~~

The command below is rejected—even though 50000 is non-negative—because the BSON type is wrong:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $set: { price: 50000 } } // not an explicit Decimal128
  );
} catch (error) {
  print("Price type error: " + error.message);
}
~~~

Explicitly typed write:

~~~javascript
labDb.products.updateOne(
  { _id: "P-001" },
  { $set: { price: Decimal128("50000.00") } }
);
~~~

When multiple BSON numeric types must be accepted for a field, `bsonType` can be an array such as `["int", "long"]`. However, mixing numeric types can complicate arithmetic and application mapping; standardize whenever possible.

### 5.2. Integer Values, Decimal Values, and Rounding

A validator can enforce value ranges and BSON types, yet it **does not define rounding rules** or currency units. For example, `Decimal128("10.1234")` still satisfies `minimum: 0`.

If a unit price may have at most two decimal places, add an appropriate solution at the ingestion layer or a custom validation rule. Do not confuse `maximum` with precision/scale rules.

A constraint like `maximum: 100000` also **does not guarantee uniqueness**—two documents with the same price or stock can still be saved. Field uniqueness is enforced via a **unique index** or other mechanisms.

## 6. String Length with `minLength` and `maxLength`

These two keywords constrain the length of string values:

~~~javascript
title: {
  bsonType: "string",
  minLength: 3,
  maxLength: 120
}
~~~

| `title` | Valid? | Explanation |
| --- | --- | --- |
| `"Pen"` | Yes | String length is between 3 and 120 characters |
| `"A"` | No | Too short |
| `""` | No | Empty string |
| `"   "` | Yes under the length rules alone | Has three characters, though no meaningful content |
| String longer than 120 chars | No | Exceeds `maxLength` |
| `null` | No | Not the required string type |

Length bounds do not replace **trimming unwanted whitespace**, Unicode normalization, or checking for meaningful content.

If a title must not consist solely of whitespace, add a `pattern` requiring at least one non-whitespace character:

~~~javascript
title: {
  bsonType: "string",
  minLength: 3,
  maxLength: 120,
  pattern: "\\S"
}
~~~

Inside a JavaScript string, `"\\S"` produces the regular expression `\S`. An unanchored pattern like `\S` matches **anywhere** a non-whitespace character appears; it does not forbid leading or trailing whitespace. To disallow leading/trailing spaces, use an anchored regex or normalize and validate in the application.

### 6.1. Should Character Count Be Treated as Byte Count?

`minLength` and `maxLength` constrain **string length**, not the BSON byte size of the whole document. Vietnamese characters and emojis take more UTF-8 bytes than basic Latin characters. If an external protocol or system imposes a byte limit, validate that byte limit separately.

For display names in natural languages, do not arbitrarily use a regex allowing only `[A-Za-z]`: such an expression rejects accented letters, valid spaces, and characters from other scripts.

## 7. String Formatting with `pattern`

The `pattern` keyword accepts a **regular expression string**. MongoDB applies the regex to validate string values; if it does not match, the document is rejected.

In the opening validator, `sku` has:

~~~javascript
sku: {
  bsonType: "string",
  minLength: 4,
  maxLength: 12,
  pattern: "^[A-Z][A-Z0-9_-]{3,11}$"
}
~~~

Meaning of each part:

| Component | Meaning |
| --- | --- |
| `^` | Start of string |
| `[A-Z]` | First character must be an uppercase letter A–Z |
| `[A-Z0-9_-]` | Subsequent characters may be A–Z, 0–9, `_`, or `-` |
| `{3,11}` | Repeat 3 to 11 times for the remainder |
| `$` | End of string |

This expression allows a **total length of 4 to 12 characters**; keeping `minLength` and `maxLength` in the schema makes the business intent explicit even though the regex already bounds length.

| SKU | Valid? | Reason |
| --- | --- | --- |
| `MOUSE-01` | Yes | Valid characters, length 8 |
| `A123` | Yes | Leading `A` followed by three characters |
| `a123` | No | First letter is lowercase |
| `12AB` | No | Does not start with an uppercase letter |
| `AB` | No | Fewer than 4 characters |
| `A12#5` | No | Contains `#` |
| `A123456789012` | No | Longer than 12 characters |

### 7.1. Why Are Anchors `^` and `$` Needed?

If you write only:

~~~javascript
pattern: "[A-Z]{2}[0-9]{3}"
~~~

then `"xxxAB123yyy"` still matches **a substring**. To require the **entire string** to match the format, use:

~~~javascript
pattern: "^[A-Z]{2}[0-9]{3}$"
~~~

Depending on the goal, not every regex needs anchors; for instance, checking that a title contains at least one non-whitespace character can use `\S` without anchors.

### 7.2. Escaping Regex in JavaScript and JSON

When a schema is written as a **JavaScript string** in `mongosh`, regex backslashes must be escaped one extra level. For example, to match exactly six digits:

~~~javascript
pattern: "^[0-9]{6}$"

// Equivalent regex concept using \d:
pattern: "^\\d{6}$"
~~~

For schemas stored in **JSON** format, string escaping likewise requires `\\` to represent one `\` in the regex. Always distinguish between the **actual regex** and the **string literal holding the regex**.

### 7.3. Common Example Patterns

| Need | Sample `pattern` | Note |
| --- | --- | --- |
| Code with two letters then three digits | `"^[A-Z]{2}[0-9]{3}$"` | Case-sensitive |
| 5–6 ASCII digit postal code | `"^[0-9]{5,6}$"` | Does not apply to every country |
| Alphanumeric/`_`/`-` of 4–20 chars | `"^[A-Za-z0-9_-]{4,20}$"` | Disallows accents and spaces |
| String with at least one non-whitespace char | `"\\S"` | Does not trim leading/trailing spaces |
| String of ASCII digits only | `"^[0-9]+$"` | Does not replace integer value checks |

Simple regexes are insufficient for complex multi-rule formats such as deliverable email addresses, international phone numbers, or third-party identifiers. Those cases require dedicated parsers/libraries and sometimes live verification.

## 8. Testing Invalid Documents

To see each rule group in action, run these independent operations. Use `try/catch` so one error does not halt the entire lab.

### 8.1. Missing Required Field

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-1",
    sku: "BOOK-01",
    title: "MongoDB Book",
    // missing status
    stock: Int32(2),
    price: Decimal128("50000.00")
  });
} catch (e) {
  print("ERR-1: " + e.message);
}
~~~

### 8.2. Invalid Enum

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-2",
    sku: "BOOK-02",
    title: "Data Book",
    status: "active",  // not in enum list
    stock: Int32(2),
    price: Decimal128("50000.00")
  });
} catch (e) {
  print("ERR-2: " + e.message);
}
~~~

### 8.3. Out-of-Range Number

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-3",
    sku: "BOOK-03",
    title: "BSON Book",
    status: "draft",
    stock: Int32(100001),  // exceeds maximum
    price: Decimal128("50000.00")
  });
} catch (e) {
  print("ERR-3: " + e.message);
}
~~~

### 8.4. Invalid String Pattern

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-4",
    sku: "book-04",     // lowercase, fails pattern
    title: "Index Book",
    status: "draft",
    stock: Int32(3),
    price: Decimal128("70000.00")
  });
} catch (e) {
  print("ERR-4: " + e.message);
}
~~~

### 8.5. String Too Short

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-5",
    sku: "BOOK-05",
    title: "AB",        // shorter than minLength: 3
    status: "draft",
    stock: Int32(3),
    price: Decimal128("70000.00")
  });
} catch (e) {
  print("ERR-5: " + e.message);
}
~~~

After the failed commands, the collection still holds the valid documents inserted earlier, such as `P-001` and `P-002`:

~~~javascript
labDb.products.find(
  {},
  { _id: 1, sku: 1, status: 1, stock: 1, price: 1 }
);
~~~

**Schema validation errors do not auto-correct input.** Applications should surface meaningful reasons to users, fix the input data, or stop the write and log the error for remediation.

## 9. Does Schema Validation Apply to Updates?

Yes. With `validationLevel: "strict"` and `validationAction: "error"`, MongoDB checks the **document resulting from the update**. This holds even when a command modifies only one field and inadvertently makes the document invalid.

Example transitioning a product status to an allowed value:

~~~javascript
labDb.products.updateOne(
  { _id: "P-001" },
  { $set: { status: "published" } }
);
~~~

The update is valid. However, if you remove a required field:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $unset: { sku: "" } }
  );
} catch (e) {
  print("Cannot remove sku field: " + e.message);
}
~~~

The `$unset` causes the document to lose `sku`, so it is rejected. The source document retains its original `sku`.

Similarly:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $inc: { stock: -1000 } }
  );
} catch (e) {
  print("Cannot make stock negative: " + e.message);
}
~~~

If the final result of `$inc` violates `minimum: 0`, the operation is rejected.

**Do not confuse with state transition rules:** the enum validator accepts `draft`, `published`, and `archived`, yet it does not automatically block updating `archived → draft`. To enforce transitions, use update conditions, business logic, or advanced rules.

## 10. `additionalProperties`: Locking or Allowing Extra Fields

The initial validator only enforces rules on defined fields; a document adding `color: "black"` is still accepted.

~~~javascript
labDb.products.updateOne(
  { _id: "P-001" },
  { $set: { color: "black" } }
);
~~~

If you want to permit only declared fields, use:

~~~javascript
{
  bsonType: "object",
  required: ["sku"],
  additionalProperties: false,
  properties: {
    _id: {},
    sku: { bsonType: "string" }
  }
}
~~~

In MongoDB, `_id` normally exists in every document; **you must declare `_id` inside `properties` when using `additionalProperties: false`** unless you want documents rejected just for having `_id`.

Trade-off to consider: `additionalProperties: false` makes schema evolution harder because every new field requires updating the validator before writes occur. For continuously evolving applications, a practical approach is locking down sensitive fields and controlling the rest through application validation or per-field rules rather than banning all unknown fields from day one.

## 11. Inspecting and Updating Validators with `collMod`

### 11.1. Viewing the Current Configuration

~~~javascript
labDb.getCollectionInfos({ name: "products" });
~~~

In the returned metadata, `options.validator` holds the schema, while `options.validationLevel` and `options.validationAction` hold the enforcement policy.

You can extract the active `$jsonSchema` object:

~~~javascript
const info = labDb.getCollectionInfos({ name: "products" })[0];
const currentSchema = info.options.validator.$jsonSchema;

printjson(currentSchema);
~~~

### 11.2. Modifying Rules as Business Needs Evolve

Suppose you want to allow titles up to **150** characters instead of **120**. Build a new definition from the retrieved configuration and run `collMod`:

~~~javascript
// Run after reading currentSchema above.
const newSchema = EJSON.parse(EJSON.stringify(currentSchema));

newSchema.properties.title.maxLength = 150;

labDb.runCommand({
  collMod: "products",
  validator: { $jsonSchema: newSchema },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

This command updates **the collection's rules**; it does not rewrite existing documents. When changing a schema, both the application and the database schema must understand the new constraints together.

To add a new enum value, follow the same pattern:

~~~javascript
// Example alternative to editing title above, or after updating it:
newSchema.properties.status.enum = [
  "draft", "published", "archived", "discontinued"
];

// Only takes effect after running collMod with the new validator.
~~~

In production, roll out in an order that ensures old and new application versions can coexist safely during the transition window.

### 11.3. The Two `validationLevel` Modes

| `validationLevel` | New Documents | Updates to Currently Valid Docs | Updates to Currently Invalid Legacy Docs |
| --- | --- | --- | --- |
| `"strict"` | Checked | Checked | Checked |
| `"moderate"` | Checked | Checked | Not checked against the same validator, aiding gradual rollout on legacy data |

`moderate` helps when a collection contains legacy documents violating the new schema and you cannot fix all of them immediately. However, it **does not guarantee all documents eventually become valid**; you still need a cleanup plan and a path back to `strict`.

### 11.4. The Two `validationAction` Modes

| `validationAction` | When a Document Is Invalid |
| --- | --- |
| `"error"` | Rejects the write operation and returns an error |
| `"warn"` | Allows the operation and logs a validation warning to MongoDB logs |

You can use `warn` during an observation phase to see where applications are writing invalid data. However, invalid data is still persisted while `warn` is active; never treat `warn` as enforcing the data contract.

Example switching temporarily to warning mode:

~~~javascript
labDb.runCommand({
  collMod: "products",
  validationLevel: "strict",
  validationAction: "warn"
});

// When ready to reject invalid data:
labDb.runCommand({
  collMod: "products",
  validationLevel: "strict",
  validationAction: "error"
});
~~~

This snippet changes only how violations are handled; the existing validator stays intact. In real applications, monitor logs, fix bad write paths, and execute schema transitions systematically.

## 12. Legacy Data: Auditing Before Enabling `strict + error`

A critical point is that **adding a validator does not automatically fix or scan all stored documents**. The collection may still hold records that violate the new schema. Under `strict`, subsequent updates to those records can fail.

MongoDB lets you use `$jsonSchema` inside queries to locate conforming documents. Combine with `$nor` to find documents that **fail** the validator:

~~~javascript
const effectiveSchema = labDb
  .getCollectionInfos({ name: "products" })[0]
  .options.validator.$jsonSchema;

labDb.products.find({
  $nor: [
    { $jsonSchema: effectiveSchema }
  ]
});
~~~

On our practice dataset containing only documents accepted since collection creation, this query normally returns nothing. When evaluating legacy data, run this check **before** moving the collection to a stricter schema, or test in staging first.

A sound rollout process:

1. **Survey live data:** inspect actual BSON types, missing fields, enum values, and numeric ranges.
2. **Define the target schema:** align with business owners, backend teams, and ingestion pipelines.
3. **Audit violations:** query non-conforming documents and summarize root causes.
4. **Fix legacy data:** backfill fields, correct enums, normalize numeric types, and handle out-of-range values.
5. **Update all write paths:** ensure APIs, batch jobs, and admin tools follow the new contract.
6. **Enable enforcement:** switch to `validationLevel: "strict"` and `validationAction: "error"` once data and clients are ready.
7. **Monitor live errors:** watch validation error codes post-rollout to catch unexpected edge cases.

For gradual rollouts, `warn` or `moderate` can be used in a controlled way, provided there are clear completion criteria for the migration.

## 13. Distinguishing Schema Validation from Other Constraints

Schema validation is valuable, yet it does not replace every data integrity mechanism:

| Requirement | Is Schema Validation Enough? | Complementary Solution |
| --- | --- | --- |
| `sku` required and properly formatted | Yes, via `required`/`pattern` | Client-side UX validation |
| `status` in allowed list | Yes, via `enum` | State transition checks if applicable |
| `stock` within 0–100000 | Yes, via `minimum`/`maximum` and BSON type | Atomic updates when decrementing stock |
| `sku` unique across collection | No | **Unique index** |
| Category ID exists in another collection | No automatic foreign keys in `$jsonSchema` | Business logic/transactions or appropriate data modeling |
| Transition `archived → published` requires approval | Enum is insufficient | Business rules / authorization |
| Prevent unauthorized users from editing price | No | Authentication, authorization, RBAC |
| Verify email address can actually receive mail | Regex is insufficient | Parser and verification workflow |
| Monetary unit price has fixed scale and rounding | Minimum/type is insufficient | Business rules and decimal arithmetic |

Example SKU uniqueness:

~~~javascript
labDb.products.createIndex(
  { sku: 1 },
  { unique: true }
);
~~~

This index forbids two documents from sharing the same `sku` under index collation rules, whereas the validator requires `sku` to exist with the proper format. **Unique indexes** and **schema validation** complement each other.

To prevent negative stock under concurrent decrements, combine with an atomic filter condition:

~~~javascript
const result = labDb.products.updateOne(
  { _id: "P-001", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
);

print(result.modifiedCount);
~~~

The filter ensures decrementing occurs only when at least 2 units are in stock; the validator serves as the final guardrail ensuring the post-write value stays non-negative. Handle `modifiedCount: 0` in the application to report out-of-stock errors.

## 14. Practice: Building a Validator for User Profiles

Create a separate collection with these rules:

- `username`: required, string, 4–20 chars, consisting only of unaccented Latin letters, digits, and underscores.
- `role`: required, one of `reader`, `editor`, `admin`.
- `age`: optional, BSON int32, range 0–120.
- `displayName`: optional, string 1–80 chars.
- `score`: optional, BSON double, range 0–100.

Sample definition:

~~~javascript
labDb.createCollection("profiles", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["username", "role"],
      properties: {
        username: {
          bsonType: "string",
          minLength: 4,
          maxLength: 20,
          pattern: "^[A-Za-z0-9_]+$"
        },
        role: {
          bsonType: "string",
          enum: ["reader", "editor", "admin"]
        },
        age: {
          bsonType: "int",
          minimum: 0,
          maximum: 120
        },
        displayName: {
          bsonType: "string",
          minLength: 1,
          maxLength: 80
        },
        score: {
          bsonType: "double",
          minimum: 0,
          maximum: 100
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Test a valid document:

~~~javascript
labDb.profiles.insertOne({
  _id: "U-01",
  username: "user_01",
  role: "reader",
  age: Int32(22),
  displayName: "Nguyen An",
  score: Double(87.5)
});
~~~

Test an invalid document:

~~~javascript
try {
  labDb.profiles.insertOne({
    _id: "U-02",
    username: "ab",     // too short
    role: "owner",      // outside enum
    age: Int32(-5)      // out of range
  });
} catch (e) {
  print("Invalid profile: " + e.message);
}
~~~

If MongoDB returns detailed validator output, you can inspect multiple failing branches within the same document. In production, translate error results into appropriate messages instead of exposing raw technical error payloads.

**Extension exercises:**

1. Update `required: ["username", "role", "displayName"]` and try inserting without `displayName`.
2. Allow `age` to hold `null` via `bsonType: ["int", "null"]`, keeping `minimum` and `maximum` for numeric values.
3. Disallow whitespace or accented Vietnamese characters in `username` per hypothetical requirements; explain why an ASCII-only regex should not be applied indiscriminately to `displayName`.
4. Create a unique index on `username`, try adding an account with the same username and a different `_id`; distinguish **duplicate key error** from **DocumentValidationFailure**.
5. Update `role` to also allow `"moderator"` via `collMod`, then try writing a document with the new role.
6. Use `$jsonSchema` in a query to find documents failing the updated rules.

## 15. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Document failed validation`, error code 121 | Missing field, wrong BSON type, enum, range, or pattern | Inspect error details and compare against validator |
| Document has required field yet is still rejected | Field is `null` or has wrong type | Distinguish `required` from `bsonType` |
| Numeric value looks right yet is rejected | `Int32`, `Long`, `Double`, and `Decimal128` are distinct BSON types | Use the matching constructor/codec |
| `"PUBLISHED"` is rejected | Enum only specifies `"published"` | Normalize value or update contract safely |
| String has valid length yet is rejected | `pattern` does not match | Check anchors, allowed character classes, and regex escaping |
| Whitespace-only string is accepted | `minLength` does not check for meaningful content | Add a suitable `pattern` or normalize input |
| Legacy documents exist despite violating schema | Validator does not auto-scan/fix old data | Audit and migrate; consider `moderate` |
| Switching to `strict` breaks updates on old records | Post-update document still fails schema | Backfill or execute a migration strategy |
| Invalid writes still succeed | `validationAction: "warn"` | Switch to `error` once ready |
| Two documents with duplicate `sku` still save | Schema validation does not enforce uniqueness by default | Create a unique index |
| App updated, yet validator enforces old rules | Schema is stored on the MongoDB collection | Update via `collMod` and coordinate deployment |
| API writes invalid data via bypass | Command/client has bypass document validation privilege | Restrict `bypassDocumentValidation` permissions and write policies |

Specific error messages vary across MongoDB versions and clients. Always inspect **error code, namespace, active validator, and the submitted write operation** before altering a schema.

## 16. Principles for Maintainable Schema Validation

1. **Place rules at the right object level.** Root-level `required` does not cascade automatically to nested objects.
2. **Distinguish presence, type, and content.** `required`, `bsonType`, `enum`, `minimum`, and `pattern` solve different problems.
3. **Control BSON types deliberately.** JavaScript numeric values do not always match the numeric types expected by Java or other applications.
4. **Keep regexes proportional.** Use `^`/`$` when the entire string must match; do not turn regexes into a catch-all for complex business validation.
5. **Do not treat validators as uniqueness or authorization solutions.** Use indexes and access control for those responsibilities.
6. **Survey legacy data before tightening a schema.** A new validator does not automatically repair historical documents.
7. **Coordinate schema changes with application versions.** Adding enum values, tightening bounds, or changing BSON types can break live writers.
8. **Use `warn`/`moderate` with clear timelines and goals.** The final protection for new writes is usually `strict` and `error` when business rules mandate enforcement.

In MongoDB, flexible schemas and schema validation do not conflict: you can keep optional fields and allow document extensibility while strictly governing core data. Combining **required + enum + value ranges + string rules** provides a practical foundation for preventing inconsistent data right at the storage layer.

### Official References

- [MongoDB Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — overview of validation mechanisms and benefits.
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `$jsonSchema`, BSON types, and validator syntax.
- [JSON Schema Validation](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/) — keywords and usage of `$jsonSchema`.
- [Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — `strict` and `moderate`.
- [Choose How to Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — `error` and `warn`.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — updating validators with `collMod`.
