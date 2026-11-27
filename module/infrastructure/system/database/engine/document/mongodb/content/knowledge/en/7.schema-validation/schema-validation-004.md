# Validating Nested Documents, Arrays, and Array Elements in MongoDB

## 1. Problem Statement and Goals

MongoDB stores data as BSON documents. A document can contain nested objects, arrays of primitive values, arrays of objects, and multiple nesting levels. This flexibility helps align the data model with business needs, yet also introduces risks of storing records with missing fields, mismatched types, or broken structures.

For example, an order might embed customer details, shipping address, and line items together:

~~~javascript
{
  _id: "ord-001",
  customer: {
    customerId: "C001",
    contact: { email: "lan@example.test" }
  },
  shipping: {
    address: { city: "Hanoi", street: "12 Pho Hue" }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(2),
      unitPrice: NumberDecimal("19.90"),
      labels: ["new", "gift"]
    }
  ]
}
~~~

Without constraints, MongoDB can accept variants such as `customer: "Lan"`, `lines: "BOOK-01"`, or a line item missing `sku`. When the application reads that data, those documents can throw errors or corrupt calculations.

**Schema validation** lets you define collection-level rules. When documents are written, MongoDB checks their structure and data types against the `validator`; depending on the configured mode, it rejects invalid writes or logs a warning.

In this lesson under the **Schema validation** chapter of **Database Engine Document MongoDB**, we will:

- Define nested document structures using `$jsonSchema`, `properties`, and `required`.
- Validate arrays using `bsonType: "array"`, `items`, `minItems`, `maxItems`, and `uniqueItems`.
- Constrain **individual elements** of an array of objects, including properties inside each element.
- Distinguish missing fields, `null` values, empty objects, and empty arrays.
- Test valid and rejected `insertOne`, `updateOne`, and `$push` operations.
- Inspect active validators, modify them with `collMod`, and observe them in MongoDB Compass.
- Understand the limits of schema validation, especially uniqueness by a single field inside an array.

All write operations in the examples use a dedicated practice database `schema_validation_lab`. Do not run validator creation/modification commands on production collections without reviewing existing data and rollout procedures first.

## 2. Where Does Schema Validation Operate?

A collection can be created with a `validator` option:

~~~javascript
db.createCollection("collectionName", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        // Define fields to validate
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Basic execution flow:

~~~text
Client (mongosh, Compass, Java Driver, Spring Data MongoDB)
                           |
                           v
                  Send write command
                           |
                           v
                MongoDB evaluates validator
                      /              \
                  Valid            Invalid
                   |                     |
                   v                     v
             Allow write         error: reject write
                                 warn: write and log warning
~~~

Because the validator runs on the server, the same rules apply across writes from different clients. However, the application should still validate inputs to return user-friendly messages and enforce business rules broader than schema scope.

Key components:

| Component | Purpose |
|---|---|
| `validator` | Holds the conditions a document must satisfy on write |
| `$jsonSchema` | Describes document structure using MongoDB-supported JSON Schema keywords and BSON extensions |
| `bsonType` | Checks BSON type: `object`, `array`, `string`, `int`, `long`, `decimal`, ... |
| `properties` | Defines rules for child fields of an object |
| `required` | Specifies field names that must exist in the object |
| `items` | Defines rules for array elements |
| `validationLevel` | Determines which documents are checked during updates |
| `validationAction` | Determines how MongoDB responds to violating documents |

MongoDB supports **a subset** of JSON Schema along with BSON extensions. Never assume every keyword from a general JSON Schema library works identically in MongoDB. For instance, `bsonType` is a key extension specific to BSON data.

### 2.1. Viewing Data as a Structural Tree

~~~text
order (object)
├── _id (string)
├── customer (object)
│   ├── customerId (string)
│   └── contact (object)
│       ├── email (string)
│       └── phone (string, optional)
├── shipping (object)
│   └── address (object)
│       ├── city (string)
│       └── street (string)
└── lines (array)
    ├── [0] (object)
    │   ├── sku (string)
    │   ├── quantity (int)
    │   ├── unitPrice (decimal)
    │   └── labels (array)
    │       ├── [0] (string)
    │       └── [1] (string)
    └── [1] (object)
        └── Fields following the same items rules
~~~

At each object level, specify `bsonType: "object"`, `properties`, and `required` if needed. At each array level, specify `bsonType: "array"` and use `items` to describe the structure of **each element**.

## 3. Core Rules: object, properties, and required

### 3.1. Nested Fields

Consider a schema covering only customer information:

~~~javascript
const customerSchema = {
  bsonType: "object",
  required: ["customerId", "contact"],
  properties: {
    customerId: {
      bsonType: "string",
      minLength: 1
    },
    contact: {
      bsonType: "object",
      required: ["email"],
      properties: {
        email: {
          bsonType: "string",
          minLength: 3
        },
        phone: {
          bsonType: "string"
        }
      }
    }
  }
};
~~~

Here:

- `customerId` and `contact` must exist in the `customer` object.
- `contact` must be an object, not a string or an array.
- Inside `contact`, `email` is mandatory; `phone` is optional.
- `email` must be a string. `minLength: 3` only enforces minimum length; it does not replace full email address validation.

**`required` only mandates that the field be present.** It does not guarantee a non-`null` value, the right type, or non-emptiness. To exclude `null`, specify the appropriate type such as `bsonType: "string"`.

### 3.2. When Does a Nested Object's Schema Apply?

Suppose the parent schema says:

~~~javascript
{
  bsonType: "object",
  properties: {
    customer: customerSchema
  }
}
~~~

This schema constrains `customer`'s structure **if that field appears**, yet does not require the document to include `customer`.

To ensure the document always has this field:

~~~javascript
{
  bsonType: "object",
  required: ["customer"],
  properties: {
    customer: customerSchema
  }
}
~~~

Likewise, to mandate `customer.contact.email`, you must complete the entire path:

1. Root document requires `customer`.
2. `customer` schema requires `contact`.
3. `contact` schema requires `email`.
4. `bsonType` at each level must match the expected type.

You cannot simply put `"customer.contact.email"` into the root document's `required` array to replace the layered definitions above.

### 3.3. Undeclared Fields and additionalProperties

By default, an object may hold extra fields not listed in `properties`. To lock down the structure at a level, use:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  additionalProperties: false,
  properties: {
    name: { bsonType: "string" }
  }
}
~~~

This example accepts `{name:"An"}` but rejects `{name:"An",age:25}`.

**Root-level warning:** MongoDB documents normally include `_id`. If you set `additionalProperties: false` at the root document level, you must declare `_id` inside `properties`, even if it is not in `required`:

~~~javascript
{
  bsonType: "object",
  additionalProperties: false,
  properties: {
    _id: { bsonType: ["objectId", "string"] },
    name: { bsonType: "string" }
  }
}
~~~

If `_id` is omitted, an otherwise business-valid MongoDB document will be rejected because `_id` is treated as an "unpermitted" field.

## 4. Validating Arrays and Array Elements

### 4.1. Distinguishing Array Checks from Element Checks

~~~javascript
{
  bsonType: "array"
}
~~~

This only checks that the field is an array; elements can have mixed types. To enforce an array of strings:

~~~javascript
{
  bsonType: "array",
  items: {
    bsonType: "string"
  }
}
~~~

Expected outcomes:

| Value | Result |
|---|---|
| `["new", "gift"]` | Valid |
| `[]` | Valid unless `minItems` is set |
| `["new", 42]` | Invalid: contains a non-string element |
| `"new"` | Invalid: the field itself is not an array |
| `null` | Invalid if only `bsonType: "array"` is allowed |

`items` applies to **every element**. In a 100-element array, even a single wrong-typed element violates the schema.

### 4.2. Constraining Element Count

~~~javascript
{
  bsonType: "array",
  minItems: 1,
  maxItems: 20,
  items: { bsonType: "string" }
}
~~~

- `minItems: 1` rejects empty arrays.
- `maxItems: 20` caps the array at 20 elements.
- Both check **array length**, not the length of strings inside it.

If each string element must be at least three characters long, place `minLength` inside `items`:

~~~javascript
{
  bsonType: "array",
  minItems: 1,
  items: {
    bsonType: "string",
    minLength: 3
  }
}
~~~

### 4.3. Arrays of Objects

This is the typical pattern for order line-item lists:

~~~javascript
{
  bsonType: "array",
  minItems: 1,
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
    }
  }
}
~~~

Each element must be an object containing both required fields, with `quantity` as a BSON Int32 of at least `1`.

Writing `required: ["sku", "quantity"]` at the root document will not constrain array elements. You must put `required` **inside the `items` schema**.

### 4.4. uniqueItems Is Not Per-Property Uniqueness

~~~javascript
{
  bsonType: "array",
  uniqueItems: true,
  items: {
    bsonType: "string"
  }
}
~~~

For string arrays, `uniqueItems: true` forbids duplicate strings per schema element equality. For object arrays, uniqueness compares the **entire element**, so it does not automatically enforce uniqueness on a single field like `sku`.

For example:

~~~javascript
[
  { sku: "A", quantity: 1 },
  { sku: "A", quantity: 2 }
]
~~~

These two objects are not identical, so `uniqueItems: true` cannot be relied on to prevent duplicate `sku` values. To forbid duplicates by business key, validate in the application layer or remodel as a child collection with an appropriate unique compound index. A unique multikey index does not forbid two elements sharing the same key inside **the same document** the way many developers expect.

## 5. Creating a Collection with a Multi-Level Validator

In `mongosh`, select the practice database:

~~~javascript
use schema_validation_lab
~~~

Define a reusable schema for the `ordersValidated` collection:

~~~javascript
const orderSchema = {
  bsonType: "object",
  required: ["customer", "shipping", "lines"],
  properties: {
    _id: {
      bsonType: ["objectId", "string"]
    },

    customer: {
      bsonType: "object",
      required: ["customerId", "contact"],
      properties: {
        customerId: {
          bsonType: "string",
          minLength: 1
        },
        contact: {
          bsonType: "object",
          required: ["email"],
          properties: {
            email: {
              bsonType: "string",
              minLength: 3,
              pattern: "^[^@ ]+@[^@ ]+\\.[^@ ]+$"
            },
            phone: {
              bsonType: "string"
            }
          }
        }
      }
    },

    shipping: {
      bsonType: "object",
      required: ["address"],
      properties: {
        address: {
          bsonType: "object",
          required: ["city", "street"],
          properties: {
            city: {
              bsonType: "string",
              minLength: 1
            },
            street: {
              bsonType: "string",
              minLength: 1
            },
            postalCode: {
              bsonType: "string"
            }
          }
        }
      }
    },

    lines: {
      bsonType: "array",
      minItems: 1,
      maxItems: 100,
      items: {
        bsonType: "object",
        required: ["sku", "quantity", "unitPrice"],
        properties: {
          sku: {
            bsonType: "string",
            minLength: 1
          },
          quantity: {
            bsonType: "int",
            minimum: 1
          },
          unitPrice: {
            bsonType: "decimal",
            minimum: NumberDecimal("0")
          },
          labels: {
            bsonType: "array",
            uniqueItems: true,
            items: {
              bsonType: "string",
              minLength: 1
            }
          }
        }
      }
    }
  }
};
~~~

Validation layers:

1. Root document is an `object`; `customer`, `shipping`, and `lines` are required.
2. `customer.contact` is an object and must contain a string `email`.
3. `shipping.address` is an object and must contain `city` and `street`.
4. `lines` is an array with **1 to 100 elements**.
5. Every element `lines[i]` must be an object with non-empty string `sku`, Int32 `quantity` >= 1, and Decimal128 `unitPrice` >= 0.
6. If an element has `labels`, it must be an array of non-empty strings with no completely identical duplicates.

The example uses `NumberDecimal("0")` as the threshold matching the Decimal128 monetary field. The `pattern` regex illustrates only a basic email string format check; production systems should use dedicated email validation and verification.

Create the collection if it does not exist yet:

~~~javascript
if (db.getCollectionInfos({ name: "ordersValidated" }).length === 0) {
  db.createCollection("ordersValidated", {
    validator: {
      $jsonSchema: orderSchema
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}
~~~

Checking existence here avoids a "collection already exists" error when re-running the lab. **If the collection already exists with a different validator, the `if` block does not automatically update it**; inspecting and updating configuration is covered in Section 10.

### 5.1. Mapping Requirements to Schema Locations

| Business Requirement | Declaration Location | Rule |
|---|---|---|
| Order must have a customer | Root schema | `required: ["customer", ...]` |
| Customer must have contact info | `properties.customer` | `required: ["contact", ...]` |
| Contact must have an email | `properties.customer.properties.contact` | `required: ["email"]` |
| Shipping address must have a city | `shipping → address` | `required: ["city", ...]` |
| Order has at least one line item | `properties.lines` | `bsonType:"array", minItems:1` |
| Each line item has quantity >= 1 | `properties.lines.items.properties.quantity` | `bsonType:"int", minimum:1` |
| Each line item has Decimal128 price | `properties.lines.items.properties.unitPrice` | `bsonType:"decimal"` |
| Each label is a string | `lines.items.properties.labels.items` | `bsonType:"string"` |

Reading top-down from the root through each level helps prevent misplacing `required` or `items` where they only validate the outer "shell" of the document.

## 6. Inserting a Valid Document

Insert an order satisfying every condition:

~~~javascript
db.ordersValidated.insertOne({
  _id: "ord-001",
  customer: {
    customerId: "C001",
    contact: {
      email: "lan@example.test",
      phone: "0900000000"
    }
  },
  shipping: {
    address: {
      city: "Hanoi",
      street: "12 Pho Hue",
      postalCode: "100000"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(2),
      unitPrice: NumberDecimal("19.90"),
      labels: ["new", "gift"]
    },
    {
      sku: "BOOK-02",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("10.50")
    }
  ]
});
~~~

If the collection was created as in Section 5 and `_id: "ord-001"` did not yet exist, the result typically shows `acknowledged: true` and `insertedId: "ord-001"`.

Inspect:

~~~javascript
db.ordersValidated.findOne({ _id: "ord-001" });
db.ordersValidated.countDocuments({});
~~~

In the second element of the `lines` array, `labels` is omitted yet still valid because `labels` is **optional**. To disallow omitting `labels`, add it to `required` inside the **element** schema.

Re-running the exact same `insertOne` triggers a duplicate `_id` error, which is unrelated to schema validation. To repeat the exercise, use a new `_id` or modify the document via `updateOne`.

## 7. Validator Violation Examples

When `validationAction: "error"` is set, invalid document writes typically fail with **Document failed validation**, usually MongoDB error code **121**. Detailed information may appear in `errInfo.details`, depending on server and driver versions.

The following examples **are designed to fail**. Run each command individually in the lab environment; if the shell throws an exception, read the error and continue to the next example. Each snippet uses a distinct `_id` for clarity.

### 7.1. Missing Required Top-Level Object

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-missing-shipping",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Expected:** Rejected because `shipping` is missing from the root document.

### 7.2. Object Present but Missing Deeply Nested Field

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-missing-email",
  customer: {
    customerId: "C002",
    contact: {}
  },
  shipping: {
    address: {
      city: "Hue",
      street: "1 Tran Hung Dao"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Expected:** Rejected because `customer.contact.email` is a `required` field inside `contact`.

### 7.3. Nested Object with Wrong Type

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-address-type",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: "Hue"
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Expected:** Rejected because `shipping.address` must be an `object`, not a `string`.

### 7.4. Empty Array

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-empty-lines",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Hue",
      street: "1 Tran Hung Dao"
    }
  },
  lines: []
});
~~~

**Expected:** Rejected due to `minItems: 1` on `lines`.

### 7.5. One Array Element Has the Wrong Type

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-array-element",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Hue",
      street: "1 Tran Hung Dao"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    },
    "BOOK-02"
  ]
});
~~~

**Expected:** Rejected because element `lines[1]` is a string; the `items` schema requires **every element** to be an object.

### 7.6. Element Is an Object but Has Invalid Field

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-quantity",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Hue",
      street: "1 Tran Hung Dao"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(0),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Expected:** Rejected because `quantity` is Int32 yet violates `minimum: 1`.

Values like `"2"` (string), `NumberLong("2")` (Int64), or `2.5` (Double) also fail if the schema specifically demands `bsonType: "int"`. Looking like an integer to a human does not mean it has the right BSON type.

### 7.7. Nested Array Inside Element Has Duplicate Values

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-duplicate-label",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Hue",
      street: "1 Tran Hung Dao"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00"),
      labels: ["gift", "gift"]
    }
  ]
});
~~~

**Expected:** Rejected because `labels` specifies `uniqueItems: true`.

### 7.8. Null Values vs. Missing Fields

Two distinct scenarios:

~~~javascript
// A: Missing contact.email
contact: {}

// B: email present with null value
contact: { email: null }
~~~

Case A violates `required: ["email"]`. Case B satisfies **having the field name** yet violates `bsonType: "string"` on `email`. If business rules allow null, use `bsonType: ["string", "null"]`, but permitting null should always be a deliberate decision.

For arrays, `lines: null` is not an empty array; it violates `bsonType: "array"`. An empty array `[]` has the right array type yet still violates `minItems: 1`.

### 7.9. Failure Summary Table

| Invalid Data | Violated Condition | Level to Fix |
|---|---|---|
| Missing `customer` | `required` at root document | Root |
| `customer: "Lan"` | `bsonType: "object"` | `customer` |
| Missing `contact.email` | `required` at `contact` | `contact` |
| `shipping.address: []` | `bsonType: "object"` | `shipping.address` |
| `lines: []` | `minItems: 1` | `lines` |
| `lines: "BOOK-01"` | `bsonType: "array"` | `lines` |
| `lines: ["BOOK-01"]` | `items.bsonType: "object"` | Element level |
| Line item missing `sku` | `items.required` | Object inside array |
| `quantity: NumberInt(0)` | `minimum: 1` | Field inside element |
| `labels: ["a", "a"]` | `uniqueItems: true` | Nested array |
| `labels: ["a", 42]` | `items.bsonType: "string"` | Nested array element |

## 8. How Does the Validator Apply to Updates and $push?

Schema validation does not only run during `insertOne`. When an update leaves a document invalid while `strict`/`error` mode is enabled, the server rejects the update as well.

### 8.1. Valid Update to a Nested Object

On document `ord-001` inserted in Section 6:

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $set: {
      "shipping.address.city": "Da Nang",
      "customer.contact.phone": "0911111111"
    }
  }
);
~~~

Both updated/added fields match the schema; the update succeeds if the document exists and the user has write privileges.

### 8.2. Update Causing a Nested Object to Violate the Schema

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $set: {
      "shipping.address": "Da Nang"
    }
  }
);
~~~

**Expected:** Rejected because `shipping.address` would become a string. MongoDB validates the post-update document against active rules. Do not assume `$set` on a nested path bypasses the parent object's validator.

Similarly, using `$unset` to delete `customer.contact.email` violates `required` when `strict`/`error` validation is active.

### 8.3. Pushing a Valid Element into an Array

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $push: {
      lines: {
        sku: "BOOK-03",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("12.00"),
        labels: ["promo"]
      }
    }
  }
);
~~~

This is valid as long as the total element count does not exceed `maxItems: 100`.

### 8.4. Pushing an Invalid Element with $push

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $push: {
      lines: {
        sku: "BOOK-04",
        quantity: NumberInt(-1),
        unitPrice: NumberDecimal("12.00")
      }
    }
  }
);
~~~

**Expected:** Rejected because the new element violates `minimum: 1` at `lines.items.properties.quantity`. No invalid element is appended when the operation fails.

### 8.5. Exceeding maxItems

With `maxItems: 100`, even if every element is structurally valid, the post-update document is invalid if `lines` reaches 101 elements. This highlights two independent validation layers:

- **Array-level rules:** length, uniqueness.
- **Element-level rules:** type and content of each object.

For large datasets or frequent array appends, you must also consider MongoDB's maximum document size and data modeling; schema validation does not replace proper relationship/collection design.

## 9. Applying Advanced Constraints at the Right Level

### 9.1. Array of Objects with additionalProperties: false

Suppose each line item may contain only `sku`, `quantity`, and `unitPrice`:

~~~javascript
const strictLineItemSchema = {
  bsonType: "object",
  required: ["sku", "quantity", "unitPrice"],
  additionalProperties: false,
  properties: {
    sku: { bsonType: "string", minLength: 1 },
    quantity: { bsonType: "int", minimum: 1 },
    unitPrice: {
      bsonType: "decimal",
      minimum: NumberDecimal("0")
    }
  }
};
~~~

If this schema is placed at `lines.items`, any document whose element includes `discountCode` is rejected. In the Section 5 schema, `additionalProperties` was left unlocked, allowing extra fields if they violate no other rules.

Locking all fields helps enforce a very strict data contract, yet makes schema evolution harder. Know beforehand which systems write optional or extension fields.

### 9.2. Two-Dimensional Arrays

MongoDB supports deeply nested schemas. For example, a matrix of rows where each row has exactly three Int32 integers:

~~~javascript
const matrixSchema = {
  bsonType: "array",
  minItems: 1,
  items: {
    bsonType: "array",
    minItems: 3,
    maxItems: 3,
    items: { bsonType: "int" }
  }
};
~~~

Valid value:

~~~javascript
[
  [NumberInt(1), NumberInt(2), NumberInt(3)],
  [NumberInt(4), NumberInt(5), NumberInt(6)]
]
~~~

Invalid value:

~~~javascript
[
  [NumberInt(1), NumberInt(2)],
  [NumberInt(3), "4", NumberInt(5)]
]
~~~

The first row has only two elements; the second row contains the string `"4"`. `minItems`, `maxItems`, and `items` rules are enforced at each respective nesting level.

### 9.3. Arrays Allowing Multiple Element Types

If business logic genuinely permits both strings and integers in an array:

~~~javascript
{
  bsonType: "array",
  items: {
    bsonType: ["string", "int"]
  }
}
~~~

Use union types deliberately and avoid overly broad rules that defeat the purpose of the validator. For an order line-item list `lines`, keep all elements conforming to a single object schema.

### 9.4. Value and Format Constraints

Beyond types, you can add:

- `minLength` / `maxLength` for strings.
- `pattern` for regular expression string checks.
- `minimum` / `maximum` for numeric bounds.
- `enum` for allowed value sets.
- `minItems` / `maxItems` for array element counts.

Example constraining each line item's status:

~~~javascript
{
  bsonType: "string",
  enum: ["NEW", "RESERVED", "SHIPPED"]
}
~~~

MongoDB does not automatically **trim**, change case, or coerce inputs to "rescue" a schema-invalid value. Applications must normalize inputs prior to writing if required.

## 10. Reading and Modifying an Existing Validator

### 10.1. Inspecting Collection Metadata

~~~javascript
use schema_validation_lab

db.getCollectionInfos({ name: "ordersValidated" });
~~~

Extracting just the configuration:

~~~javascript
const info = db.getCollectionInfos({ name: "ordersValidated" })[0];

if (info) {
  printjson(info.options.validator);
  print("validationLevel: " + info.options.validationLevel);
  print("validationAction: " + info.options.validationAction);
}
~~~

`getCollectionInfos()` returns metadata. If no `validator` is configured or the account lacks permission to view it, the details may be absent or omitted.

### 10.2. Updating with collMod

An existing collection cannot be updated by calling `createCollection` again. Use `collMod` to update supported validation settings:

~~~javascript
db.runCommand({
  collMod: "ordersValidated",
  validator: {
    $jsonSchema: orderSchema
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

This example **re-applies the same schema** to illustrate syntax. For real schema changes, review existing data, active writers, and rollout plans. Changing a field from optional to required can break updates on legacy documents.

Note that `orderSchema` was defined in Section 5 within the same `mongosh` session. In a new session, re-declare the variable or supply the full schema before invoking `collMod`.

### 10.3. strict and moderate

Two common `validationLevel` values:

| Level | Meaning |
|---|---|
| `strict` | Applies the validator to all checked inserts and updates; default when validation is enabled |
| `moderate` | Checks new inserts and updates to currently valid documents; does not force immediate fixes on already-invalid legacy documents |

`moderate` can help when transitioning an old collection with dirty data. However, it still allows updates on already-invalid documents to proceed, so do not treat `moderate` as a substitute for data cleanup.

### 10.4. error and warn

| Mode | When a Document Is Invalid |
|---|---|
| `validationAction: "error"` | Rejects the violating write operation |
| `validationAction: "warn"` | Allows the write and emits a warning via the server's logging mechanism |

While evaluating legacy data, you can start with `warn` to uncover non-conforming write paths before switching to `error`. Ensure warnings are collected and monitored; never expect clients to receive an error while the server is only in `warn` mode.

MongoDB allows certain operations to pass `bypassDocumentValidation` **when the user account holds the required privilege**. This is intended for controlled administrative/import tasks, not normal application logic to skip validators.

### 10.5. New Validators and Existing Data

Adding a validator to a collection with existing data **does not cause MongoDB to automatically scan, repair, or delete non-conforming legacy documents**. Old documents remain in place; how future updates to them are checked depends on `validationLevel`.

For a safe rollout:

1. Survey legacy data to identify missing fields, wrong types, and invalid array elements.
2. Remediate or plan handling for violating data.
3. Choose an appropriate mode to observe write paths.
4. Update the validator.
5. Monitor write errors and warnings; move to `strict`/`error` when ready.

## 11. Finding Documents That Do Not Match a Schema

`$jsonSchema` can also appear inside query filters to match documents against a schema. Example on a historical collection:

~~~javascript
db.legacyOrders.find({
  $nor: [
    { $jsonSchema: orderSchema }
  ]
});
~~~

This finds documents **failing** `orderSchema`, which helps when surveying data that needs normalization before turning on strict validation.

If `legacyOrders` does not exist, the query simply returns an empty cursor; this snippet illustrates the query pattern. Reusing `orderSchema` inside `$jsonSchema` keeps your audit consistent with the target validator.

To inspect actual types of composite fields, use aggregation:

~~~javascript
db.ordersValidated.aggregate([
  {
    $project: {
      customerType: { $type: "$customer" },
      contactType: { $type: "$customer.contact" },
      linesType: { $type: "$lines" },
      lineCount: {
        $cond: [
          { $isArray: "$lines" },
          { $size: "$lines" },
          null
        ]
      }
    }
  }
]);
~~~

Before running bulk fixes, define the policy for every error category: skip, auto-fix when unambiguous, or flag for manual review. For instance, a `quantity` stored as `"2"` can safely convert to Int32 if properly formatted, whereas `"2.5"` or `"two"` needs explicit business rules.

## 12. Inspecting Validation Errors from Write Responses

When an insert/update is rejected, `mongosh` or the driver returns an error with code and message such as `Document failed validation`. Try an example catching the error:

~~~javascript
try {
  db.ordersValidated.insertOne({
    _id: "bad-catch-example",
    customer: {
      customerId: "C099",
      contact: {}
    },
    shipping: {
      address: {
        city: "Hanoi",
        street: "10 Trang Tien"
      }
    },
    lines: [
      {
        sku: "BOOK-01",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("5.00")
      }
    ]
  });

  print("Write succeeded");
} catch (error) {
  print("Code: " + error.code);
  print("Message: " + error.message);

  if (error.errInfo) {
    printjson(error.errInfo);
  }
}
~~~

With `strict`/`error` configured, the expected failure is the missing `customer.contact.email`. Depending on MongoDB version, `errInfo.details` may indicate the violated schema keyword, path, or element index. Never hardcode application logic against exact error message strings, as formatting can change.

In Java/Spring Data MongoDB applications, server errors may be wrapped in driver or data-access exceptions. Error handling should distinguish **invalid input** from **infrastructure failures**, and avoid logging entire documents containing sensitive fields.

### 12.1. Distinguishing Validation Errors from Other Errors

| Error | Meaning |
|---|---|
| `Document failed validation`, typically code 121 | Document failed the validator in error mode |
| `E11000 duplicate key` | Duplicate value in a unique index, commonly `_id` |
| `not authorized` | Account lacks privileges for the operation |
| `NamespaceExists` | Attempted to create a collection that already exists |
| Client-side BSON/serialization error | Data could not be serialized to valid BSON before sending |
| Network error or timeout | Unclear whether server accepted or rejected the write; verify state per context |

Validators do not replace **unique indexes**, authorization, or transactional guarantees. Each mechanism addresses a distinct set of rules.

## 13. MongoDB Compass and Schema Validation

MongoDB Compass provides a UI to inspect documents and certain collection settings; exact capabilities depend on the Compass version and server privileges.

Practice steps:

1. Connect to the server hosting the `schema_validation_lab` database.
2. Open the `ordersValidated` collection and view the **Documents** tab.
3. Filter with `{"_id":"ord-001"}` to inspect `customer`, `shipping`, and `lines`. Switch between Tree and JSON views if supported.
4. Open the **Validation** tab or collection settings if available, and inspect the active validator. Cross-check with `db.getCollectionInfos({name:"ordersValidated"})` in `mongosh`.
5. Try creating a document with `lines: []` using Insert Document in Compass, including all other fields. Under `strict`/`error`, the operation should be rejected.
6. Edit a `lines` element so `quantity` has an invalid value or wrong type, then save; the validator runs on write.
7. Restore or enter valid values and confirm the document saves.

When pasting JSON into Compass, pay attention to **BSON types**. Because `unitPrice` requires Decimal128, a plain JSON number `19.90` cannot be assumed to import as Decimal128. In interfaces supporting Extended JSON, decimal numbers can be written as:

~~~json
{
  "unitPrice": { "$numberDecimal": "19.90" }
}
~~~

In `mongosh`, use the explicit constructor `NumberDecimal("19.90")`. Likewise, to ensure `quantity` is Int32, use `NumberInt(2)` in the shell or the corresponding typed editor in Compass.

If Compass does not display detailed validation output or lacks the settings panel in your version, use `mongosh` to inspect `options.validator` and run write tests. Both clients obey the same validator because enforcement happens on the server.

## 14. Key Limitations to Know

### 14.1. Schema Validity Does Not Guarantee Business Validity

The schema in Section 5 confirms a line item has non-negative `unitPrice` and positive `quantity`. It does not prove that the SKU exists in the catalog, the price is currently active, the customer is allowed to buy, or the order total equals the sum of its lines.

Cross-entity or state-dependent constraints belong in application logic, transactions, or appropriate data modeling.

### 14.2. Array Validation Does Not Mean Key-Level Uniqueness

`uniqueItems` prevents completely identical elements under value comparison. For arrays of objects, it does **not** enforce uniqueness on `sku`. If business rules require each SKU to appear only once per order, the application can normalize/merge the list by SKU before writing or store line items in a dedicated collection.

### 14.3. Schemas Can Become Too Restrictive as Data Evolves

For example, `maxItems: 100` may fail for wholesale orders, or `bsonType: "int"` may break a driver sending quantities as Int64. Align data contracts across clients, drivers, backends, and MongoDB before enforcing them.

### 14.4. Schema Validation Has Runtime Overhead

Validators run on writes, so deep schemas, large arrays, and complex conditions add processing cost. That cost is usually worthwhile for data integrity, yet it should be benchmarked on real workloads—especially with very large arrays and high update frequencies.

### 14.5. Schemas Do Not Auto-Repair Data

A validator does not convert `"2"` into Int32, assign `default` values like many ORMs, or strip extra fields. Normalize inputs or run controlled migrations.

### 14.6. Document Size Limits Still Apply

A MongoDB BSON document has a maximum size limit. Even if `lines` satisfies `items` and `maxItems`, stuffing too much data into a single document causes design issues, update overhead, or size-limit failures. When element counts grow without business bounds, consider splitting into a separate collection.

## 15. Comprehensive Hands-On Lab

Run these steps in the `schema_validation_lab` database using the `ordersValidated` collection:

1. Define `orderSchema` from Section 5 and create the collection via `db.createCollection`.
2. Insert the valid `ord-001` document; run `findOne` to inspect it.
3. Test omitting `customer`, omitting `customer.contact.email`, and setting `shipping.address` to a string. Note which rules fail.
4. Test `lines: []`, `lines: "BOOK-01"`, and an array containing a string element. Compare array-level failures against element-level failures.
5. Test `quantity: NumberInt(0)` and `quantity: "2"` inside an element; explain how `minimum` differs from `bsonType`.
6. Test `labels: ["gift","gift"]`; explain why `uniqueItems` works for a label array yet does not guarantee unique SKUs across line-item objects.
7. Perform a valid update on `shipping.address.city`, then attempt updating all of `shipping.address` to a string.
8. Append a valid element to `lines` with `$push`, then attempt pushing an element with negative `quantity`.
9. Inspect metadata with `db.getCollectionInfos` to confirm `validator`, `validationLevel`, and `validationAction`.
10. Inspect the collection in Compass; test a schema-violating write and compare results with `mongosh`.

Quick verification commands:

~~~javascript
use schema_validation_lab

db.getCollectionInfos({ name: "ordersValidated" });

db.ordersValidated.findOne({ _id: "ord-001" });

db.ordersValidated.aggregate([
  {
    $project: {
      _id: 1,
      customerType: { $type: "$customer" },
      shippingType: { $type: "$shipping" },
      linesType: { $type: "$lines" },
      lineCount: { $size: "$lines" }
    }
  }
]);
~~~

Note that `$size` at the end assumes valid documents where `lines` is an array. When auditing unnormalized legacy data, check `$isArray` before calling `$size`, as shown in Section 11.

### Check-Yourself Questions

**Question 1.** A schema defines `properties.customer.contact.properties.email` without declaring `required` at any level. Will a document completely missing `customer` be rejected?

*Answer hint:* No—`properties` alone does not require a field to be present. To make `email` mandatory, add corresponding `required` arrays at every level along the path.

**Question 2.** Does `{ bsonType: "array", minItems: 1 }` guarantee that every element is an object?

*Answer hint:* No. It only checks array type and element count; you need `items: { bsonType: "object" }` to constrain elements.

**Question 3.** Why can `lines[0].quantity` using `NumberLong("2")` be rejected even though the value is the integer 2?

*Answer hint:* The schema requires BSON `int` (Int32), whereas `NumberLong` creates `long` (Int64). Their BSON types do not match.

**Question 4.** Does setting `uniqueItems: true` on an array of objects guarantee that every `sku` appears only once?

*Answer hint:* No. This rule compares entire elements, not uniqueness of a single field inside each object.

**Question 5.** Why shouldn't you add `additionalProperties: false` at the root document level while omitting `_id`?

*Answer hint:* MongoDB stores `_id`; if the schema does not declare it, documents may be rejected because `_id` is treated as an extra field.

**Question 6.** Does switching a validator to `strict`/`error` automatically delete existing schema-invalid documents?

*Answer hint:* No. You must proactively audit and remediate existing data, then govern subsequent writes according to the validation mode.

## 16. Key Principles to Remember

- **For objects:** use `bsonType: "object"`, `properties`, and `required` at the exact nesting level.
- **For arrays:** use `bsonType: "array"`; add `minItems`/`maxItems` when element count must be bounded.
- **For array elements:** use `items`; place `bsonType`, `required`, and `properties` inside it when elements are objects.
- **For nested arrays:** repeat the `items` pattern at each level; validators can inspect arbitrary nesting depths.
- **For null/missing:** `required` checks presence, while `bsonType` checks type; an empty array differs from a missing array and from `null`.
- **For uniqueness:** `uniqueItems` compares whole elements; do not confuse it with per-property uniqueness in object arrays.
- **For updates:** validators also check the outcome of `$set`, `$unset`, and `$push` when the corresponding validation mode is active.
- **For existing data:** inspect metadata, audit non-conforming documents, and roll out validators deliberately. Never assume enabling a validator fixes old data.
- **For clients:** `mongosh`, Compass, and the Java Driver all share the server-side validator, so each must send the exact BSON types to avoid rejections.

Designing schema validation to mirror the BSON structural tree keeps collections consistent even when documents contain deeply nested objects and arrays. When rules live at the right level, every document is verified not just at its outer shell, but across every nested field and element—providing a reliable foundation for queries and business processing.
