# Selecting, Adding, and Removing Fields with $project, $set, and $unset in MongoDB

## 1. Objectives and Real-World Scenarios

The Aggregation Pipeline in MongoDB is not just for filtering, grouping, or computing data. A very common task is **shaping output documents**: selecting which fields to return, creating computed fields, changing how data is structured, or removing fields that should not appear in the result.

For example, a fully stored order document:

~~~javascript
{
  _id: "ord-101",
  tenantId: "tenant-A",
  status: "PAID",
  customer: {
    id: "C01",
    name: "Lan",
    contact: {
      email: "lan@example.test",
      phone: "0900000001"
    }
  },
  items: [
    {
      sku: "BK-01",
      qty: 2,
      price: NumberDecimal("20.00"),
      internalCost: NumberDecimal("12.00")
    }
  ],
  internalNote: "Internal data"
}
~~~

However, a customer-facing API only needs:

~~~javascript
{
  orderId: "ord-101",
  status: "PAID",
  customerName: "Lan",
  itemCount: 1,
  items: [
    { sku: "BK-01", qty: 2 }
  ]
}
~~~

Three aggregation stages help solve this problem:

- **`$project`:** selects fields to keep, excludes fields, or creates computed fields in the output document.
- **`$set`:** adds new fields or overwrites existing fields while keeping all other fields. In aggregation, `$set` is an alias for **`$addFields`**.
- **`$unset`:** removes one or more fields from documents passing through the pipeline; it is a convenient alias for an exclusion projection.

This lesson belongs to the **Aggregation Basics** chapter of the **Database Engine Document MongoDB** module. You will learn:

1. How to distinguish inclusion and exclusion projections, especially how `_id` is handled.
2. How to use aggregation expressions to compute and rename fields.
3. How to add/overwrite fields with `$set` without losing remaining fields.
4. How to remove fields with `$unset`, including nested fields or fields inside arrays of documents.
5. How to understand the impact of **stage order** and which fields a stage is allowed to read.
6. How to handle missing fields, `null`, arrays, nested objects, and `$$REMOVE`.
7. How to distinguish aggregation `$set` from the `$set` update operator in `updateOne()`.
8. How to observe results using mongosh, Compass, and MongoDB Java Driver examples.

**Key takeaway right away:** A normal `aggregate()` pipeline **does not modify documents stored in the collection**. These stages shape intermediate and output documents. Stored data can only be modified when using explicit write operations such as `$merge`, `$out`, or an update command with a pipeline.

## 2. Pipeline Model: Documents Flow Through Each Stage

An aggregation pipeline is a sequence of stages. The output of the previous stage is the input to the next stage.

~~~text
Collection orders
      |
      v
  $match                 Choose which documents continue
      |
      v
  $set                   Add fields, compute new values
      |
      v
  $project               Select the output structure to keep
      |
      v
  $unset                 Remove any leftover fields
      |
      v
  API / mongosh          Receive result documents
~~~

Example:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $set: {
      customerName: "$customer.name"
    }
  },
  {
    $project: {
      _id: 0,
      customerName: 1,
      status: 1
    }
  }
]);
~~~

`$set` creates `customerName` from a nested field. `$project` keeps `customerName` and `status`, excludes `_id`, and omits other fields from the output.

**Note on operators and syntax:** Names starting with `$` inside a pipeline are MongoDB stage names or expression names, not JavaScript variables or arbitrary keys. Strings starting with `$` in an expression context are generally interpreted as field references.

## 3. Preparing the Database and Practice Dataset

The examples use an independent database. In `mongosh`:

~~~javascript
use aggregation_shape_lab
~~~

Create 6 orders with nested objects, line-item arrays, and several internal fields:

~~~javascript
const demoOrders = [
  {
    _id: "ord-101",
    tenantId: "tenant-A",
    status: "PAID",
    customer: {
      id: "C01",
      name: "Lan",
      contact: {
        email: "lan@example.test",
        phone: "0900000001"
      }
    },
    shipping: {
      city: "Hà Nội",
      method: "STANDARD"
    },
    items: [
      {
        sku: "BK-01",
        qty: NumberInt(2),
        price: NumberDecimal("20.00"),
        internalCost: NumberDecimal("12.00")
      },
      {
        sku: "PEN-01",
        qty: NumberInt(3),
        price: NumberDecimal("2.00"),
        internalCost: NumberDecimal("1.00")
      }
    ],
    tags: ["gift", "vip"],
    discount: NumberDecimal("5.00"),
    internalNote: "Priority processing",
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "ord-102",
    tenantId: "tenant-A",
    status: "NEW",
    customer: {
      id: "C02",
      name: "Minh",
      contact: {
        email: "minh@example.test",
        phone: "0900000002"
      }
    },
    shipping: {
      city: "Đà Nẵng",
      method: "EXPRESS"
    },
    items: [
      {
        sku: "BK-02",
        qty: NumberInt(1),
        price: NumberDecimal("15.50"),
        internalCost: NumberDecimal("9.00")
      }
    ],
    tags: ["new"],
    discount: NumberDecimal("0.00"),
    internalNote: "Unpaid",
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "ord-103",
    tenantId: "tenant-A",
    status: "PAID",
    customer: {
      id: "C03",
      name: "An",
      contact: {
        email: "an@example.test"
      }
    },
    shipping: {
      city: "Huế",
      method: "STANDARD"
    },
    items: [],
    tags: [],
    discount: NumberDecimal("0.00"),
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "ord-104",
    tenantId: "tenant-B",
    status: "PAID",
    customer: {
      id: "C04",
      name: "Hà",
      contact: {
        email: "ha@example.test",
        phone: "0900000004"
      }
    },
    shipping: {
      city: "TP. Hồ Chí Minh",
      method: "EXPRESS"
    },
    items: [
      {
        sku: "BK-03",
        qty: NumberInt(1),
        price: NumberDecimal("30.00"),
        internalCost: NumberDecimal("18.00")
      }
    ],
    tags: ["vip"],
    discount: NumberDecimal("2.00"),
    internalNote: "Do not share",
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "ord-105",
    tenantId: "tenant-A",
    status: "CANCELLED",
    customer: {
      id: "C05",
      name: "Bình",
      contact: {
        email: "binh@example.test"
      }
    },
    shipping: {
      city: "Hà Nội",
      method: "STANDARD"
    },
    items: [
      {
        sku: "NOTE-01",
        qty: NumberInt(1),
        price: NumberDecimal("4.00"),
        internalCost: NumberDecimal("2.50")
      }
    ],
    tags: ["cancelled"],
    discount: null,
    internalNote: "Customer cancelled",
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "ord-106",
    tenantId: "tenant-A",
    status: "SHIPPED",
    customer: {
      id: "C06",
      name: "Mai",
      contact: {
        email: "mai@example.test"
      }
    },
    shipping: {
      city: "Cần Thơ",
      method: "STANDARD"
    },
    items: [
      {
        sku: "PEN-02",
        qty: NumberInt(5),
        price: NumberDecimal("1.20"),
        internalCost: NumberDecimal("0.40")
      }
    ],
    tags: ["office"],
    createdAt: ISODate("2026-10-06T08:00:00Z")
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1 }
).sort({ _id: 1 });
~~~

Starting with an empty collection, there are **6 documents**, of which tenant-A has **5** and tenant-B has **1**. Using `replaceOne(..., {upsert:true})` lets you reload the sample IDs without duplicate `_id` errors, though it resets any records modified during practice; it does not delete documents outside that ID set.

Intentional edge cases included:

- `items` is an array of objects containing both `price` (safe to display) and `internalCost` (internal).
- `customer.contact.phone` may be missing.
- `discount` may be Decimal128, `null`, or missing.
- `items` may be an empty array (ID `ord-103`).
- `internalNote` may be present or missing.

Counts and result tables in the examples assume the collection holds only these sample documents and no extra records.

## 4. $project: Selecting Which Fields to Keep

### 4.1. Inclusion Projection

Basic syntax:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      status: 1,
      tenantId: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

For document `ord-101`, the result looks like:

~~~javascript
{
  _id: "ord-101",
  tenantId: "tenant-A",
  status: "PAID"
}
~~~

Here:

- A value of `1` in `$project` means **keep the field**.
- Unlisted fields are typically dropped from the output.
- **`_id` is kept by default**, even without declaring `_id:1`.
- Fields that do not exist in the input document are not automatically created just by writing `field:1`.

Query filters and projections serve two different goals: `$match` selects **which documents**; `$project` selects **which fields** in each document.

### 4.2. Excluding _id from the Result

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      tenantId: 1
    }
  }
]);
~~~

Result:

~~~javascript
{
  tenantId: "tenant-A",
  status: "PAID"
}
~~~

`_id: 0` is a special exception allowed alongside inclusion fields.

You can write `_id: 1` to state the intent to keep the ID explicitly, though in most inclusion projections it is unnecessary.

### 4.3. Selecting Nested Fields with Dot Notation

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      "customer.name": 1,
      "shipping.city": 1
    }
  }
]);
~~~

Result:

~~~javascript
{
  status: "PAID",
  customer: { name: "Lan" },
  shipping: { city: "Hà Nội" }
}
~~~

**Important:** Selecting `"customer.name"` preserves the **nested structure** of the field; it does not automatically create a top-level field named `customerName`.

To create a flattened field named `customerName`, use an expression:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      customerName: "$customer.name",
      city: "$shipping.city"
    }
  }
]);
~~~

Result:

~~~javascript
{
  customerName: "Lan",
  city: "Hà Nội"
}
~~~

In expression form, the string `"$customer.name"` is a **field reference**, not a literal string to output verbatim.

### 4.4. Selecting Specific Fields of Each Element in an Array

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      "items.sku": 1,
      "items.qty": 1
    }
  }
]);
~~~

Result:

~~~javascript
{
  items: [
    { sku: "BK-01", qty: 2 },
    { sku: "PEN-01", qty: 3 }
  ]
}
~~~

The array structure is preserved, while each object inside the array retains only the selected fields. For deeper transformations or per-element calculations, use `$map` covered later.

### 4.5. Inclusion Projection and Missing Fields

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-103" } },
  {
    $project: {
      status: 1,
      "customer.contact.phone": 1
    }
  }
]);
~~~

`ord-103` does not have `customer.contact.phone`. MongoDB does not insert a `null` value for a missing field merely because it was selected with `1`. If the API needs a default value, use an expression such as `$ifNull`.

## 5. $project: Excluding Unwanted Fields

### 5.1. Exclusion Projection

To keep almost the entire document while dropping the internal note:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      internalNote: 0
    }
  }
]);
~~~

`internalNote: 0` means exclude this field. Other fields, including `_id` and `items`, are kept in the output.

You can exclude multiple fields at once:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      internalNote: 0,
      "customer.contact.phone": 0,
      "items.internalCost": 0
    }
  }
]);
~~~

Since `items` is an array of objects, the path `"items.internalCost"` removes the internal cost field from the corresponding elements. If a field is already missing, an exclusion projection does not throw an error just because the field does not exist.

### 5.2. Do Not Mix Inclusion and Exclusion Arbitrarily

The following syntax is **invalid**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      status: 1,
      internalNote: 0
    }
  }
]);
~~~

A standard `$project` does not allow mixing **field inclusion** and **field exclusion** rules in the same specification, **except for the `_id` exception**.

Valid forms:

~~~javascript
// Inclusion: keep only status, keeps _id by default
{ $project: { status: 1 } }

// Inclusion: keep status, exclude _id
{ $project: { _id: 0, status: 1 } }

// Exclusion: exclude only internalNote
{ $project: { internalNote: 0 } }

// Exclusion: exclude internalNote and _id
{ $project: { _id: 0, internalNote: 0 } }
~~~

If you need to both compute new fields and drop sensitive fields, you can use:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name"
    }
  },
  {
    $unset: [
      "internalNote",
      "items.internalCost"
    ]
  }
]);
~~~

Or explicitly define an **output allowlist** using `$project` containing only permitted fields.

### 5.3. Computed Fields and Exclusion

When a projection creates computed fields, be mindful of the include/exclude mixing rule. The easiest-to-read approach is:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      status: 1,
      customerName: "$customer.name"
    }
  }
]);
~~~

This form keeps `status` and creates `customerName`, while other fields are automatically excluded.

Do not write a single specification that specifies `internalNote:0` alongside inclusion/computed fields expecting MongoDB to handle them as two independent operations. When you need conditional field removal, see `$$REMOVE` in section 11.

## 6. $project: Creating Computed Fields and Reshaping Output

`$project` accepts more than just `0` or `1`. The value of an output field can be an **aggregation expression**.

### 6.1. Creating Field Aliases

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerName: "$customer.name",
      status: 1
    }
  }
]);
~~~

Result:

~~~javascript
{
  orderId: "ord-101",
  customerName: "Lan",
  status: "PAID"
}
~~~

`orderId` is a new field existing only in the pipeline output. `_id:0` drops the original key from the output; it **does not change `_id` stored in the collection**.

### 6.2. Creating Labels from Expressions

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      isPaid: { $eq: ["$status", "PAID"] },
      statusUpper: { $toUpper: "$status" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Here:

- `$eq` returns a boolean based on the comparison.
- `$toUpper` converts a string to uppercase via an expression.
- `isPaid` and `statusUpper` are computed for each document.
- Neither computed field needs to exist in the original document.

If data can have a non-string, null, or missing `status`, define data rules and handle conditions before applying an expression that requires a specific string type.

### 6.3. Counting Array Elements

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

For ID `ord-101`, `itemCount = 2`; for `ord-103`, `itemCount = 0`.

`$ifNull` handles a missing or null `items` field with `[]`. If data might contain the wrong type such as `items: "not-an-array"`, `$ifNull` **does not convert a string into an array**; `$size` still requires an array input. To guard against malformed types, use `$isArray` and `$cond`, or fix the source data.

Safer example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      itemCount: {
        $cond: [
          { $isArray: "$items" },
          { $size: "$items" },
          0
        ]
      }
    }
  }
]);
~~~

### 6.4. Using $ifNull to Return Defaults

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-103" } },
  {
    $project: {
      _id: 0,
      name: "$customer.name",
      phone: {
        $ifNull: ["$customer.contact.phone", "Not available"]
      },
      discount: {
        $ifNull: ["$discount", NumberDecimal("0.00")]
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  name: "An",
  phone: "Not available",
  discount: NumberDecimal("0.00")
}
~~~

`$ifNull` treats missing and null values as cases needing a fallback. It is different from an exclusion projection: exclusion drops the field entirely, while `$ifNull` produces a field with a default value.

### 6.5. Expressions Returning Nested Documents

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      order: {
        id: "$_id",
        status: "$status"
      },
      customer: {
        name: "$customer.name",
        city: "$shipping.city"
      }
    }
  }
]);
~~~

The restructured output:

~~~javascript
{
  order: {
    id: "ord-101",
    status: "PAID"
  },
  customer: {
    name: "Lan",
    city: "Hà Nội"
  }
}
~~~

The `customer` field in the output no longer matches the original `customer` object; it is a new object built from expressions. This is a useful way to construct DTOs returned by an API.

## 7. $project and Literal Values: Distinguishing the Flag 1 from the Data Value 1

In `$project`, the numbers `1` and `0` in a field-value position mean **inclusion/exclusion**. If you need to create a field holding the actual numeric value 1 or 0, use `$literal`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      fixedOne: { $literal: 1 },
      fixedZero: { $literal: 0 },
      source: { $literal: "mongodb" }
    }
  }
]);
~~~

Result:

~~~javascript
{
  status: "PAID",
  fixedOne: 1,
  fixedZero: 0,
  source: "mongodb"
}
~~~

If you write:

~~~javascript
{
  $project: {
    fixedOne: 1
  }
}
~~~

MongoDB interprets `fixedOne:1` as **keep the fixedOne field if it already exists**, not create a new field holding the number 1.

### 7.1. Strings Starting with $ Have Special Meaning

~~~javascript
{
  $project: {
    copiedStatus: "$status"
  }
}
~~~

`"$status"` is a reference to the `status` field. To output the literal string `"$status"`, you must use:

~~~javascript
{
  $project: {
    text: { $literal: "$status" }
  }
}
~~~

This rule is equally important for `$set` and other aggregation expressions. Never let user-supplied strings starting with `$` get interpreted as field references when you actually want to store or display them verbatim.

## 8. $set: Adding New Fields While Keeping Existing Data

In an aggregation pipeline:

~~~javascript
{
  $set: {
    newField: <aggregation expression>
  }
}
~~~

`$set` is an alias for `$addFields`. It takes the input document and **adds** the declared fields while preserving all other fields, except those explicitly overwritten.

### 8.1. Adding a Field That Copies Data

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
]);
~~~

The output document still has `_id`, `tenantId`, `status`, `customer`, `shipping`, `items`, `tags`, `discount`, `internalNote`, and `createdAt`; alongside them, `customerName: "Lan"` is added.

Compare:

~~~javascript
// Keep only specific fields, drop others:
{ $project: { status: 1, customerName: "$customer.name" } }

// Keep all existing fields and add customerName:
{ $set: { customerName: "$customer.name" } }
~~~

This is why `$set` is convenient when you need multiple intermediate computation steps without restricting the output too early.

### 8.2. Overwriting an Existing Field

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-102" } },
  {
    $set: {
      status: "PENDING"
    }
  },
  {
    $project: {
      _id: 1,
      status: 1
    }
  }
]);
~~~

In the pipeline result, `ord-102`'s `status` becomes `PENDING`, even though the source document still stores `NEW`.

The new field value in `$set` can be a literal or an expression. Because `"PENDING"` does not start with `$`, MongoDB treats it as a string literal. If you need the verbatim value `"$PENDING"`, use `{ $literal: "$PENDING" }`.

### 8.3. Adding Nested Fields with Dot Notation

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      "shipping.label": {
        $concat: [
          "$shipping.city",
          " - ",
          "$shipping.method"
        ]
      }
    }
  },
  {
    $project: {
      _id: 0,
      shipping: 1
    }
  }
]);
~~~

Result:

~~~javascript
{
  shipping: {
    city: "Hà Nội",
    method: "STANDARD",
    label: "Hà Nội - STANDARD"
  }
}
~~~

Using the path `"shipping.label"` preserves sibling subfields such as `city` and `method` inside the `shipping` object.

### 8.4. Replacing the Entire Object Is Different

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      shipping: {
        city: "Cần Thơ"
      }
    }
  },
  {
    $project: {
      shipping: 1
    }
  }
]);
~~~

This **overwrites the entire `shipping` value in the intermediate document** with an object containing only `city`. The `shipping.method` field is not preserved automatically.

If you only want to modify one subfield while keeping siblings, use dot notation with the exact path.

### 8.5. Creating Multiple Computed Fields

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name",
      isPaid: { $eq: ["$status", "PAID"] },
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  {
    $project: {
      _id: 1,
      customerName: 1,
      isPaid: 1,
      itemCount: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Result on the sample dataset:

| ID | customerName | isPaid | itemCount |
|---|---|---|---:|
| `ord-101` | Lan | true | 2 |
| `ord-102` | Minh | false | 1 |
| `ord-103` | An | true | 0 |
| `ord-104` | Hà | true | 1 |
| `ord-105` | Bình | false | 1 |
| `ord-106` | Mai | false | 1 |

Note that `$size` works directly after `$ifNull` here because the sample data maintains an array type for `items`.

## 9. $unset: Removing Fields from Result Documents

### 9.1. Removing One Field

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $unset: "internalNote"
  }
]);
~~~

`$unset` removes `internalNote` from the intermediate document while keeping all other fields. The source collection still retains `internalNote` because this is a standard aggregation.

### 9.2. Removing Multiple Fields

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $unset: [
      "internalNote",
      "customer.contact.phone",
      "items.internalCost"
    ]
  }
]);
~~~

The argument can be a **field name string** or an **array of field name strings**. In the examples above, MongoDB removes the internal note, phone number, and internal cost fields from the output.

If a document already lacks `internalNote` or `phone`, removing the field does not introduce any new values.

### 9.3. $unset Is Equivalent to Exclusion Projection

For example:

~~~javascript
{ $unset: ["internalNote", "items.internalCost"] }
~~~

has the equivalent goal to:

~~~javascript
{
  $project: {
    internalNote: 0,
    "items.internalCost": 0
  }
}
~~~

Both remove the specified fields from the output while keeping all other fields.

Choose `$unset` when the intent is "drop these fields" and you want a readable pipeline. Choose inclusion `$project` when you want to specify the **exact set of allowed output fields**.

### 9.4. Removing _id from Output

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $unset: "_id" }
]);
~~~

The result omits `_id`. This is completely different from trying to delete `_id` from a **stored** document using an update command: `_id` is an immutable key in existing document writes.

### 9.5. Removing Nested Fields

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $unset: "customer.contact.phone" },
  {
    $project: {
      customer: 1
    }
  }
]);
~~~

The result keeps `customer.id`, `customer.name`, and `customer.contact.email` without `customer.contact.phone`.

Removing only the subfield by path, rather than deleting all of `customer.contact`, preserves the remaining needed fields.

## 10. Choosing $project, $set, or $unset?

| Need | Suitable Stage | Reason |
|---|---|---|
| Return only `status` and `customer.name` | Inclusion `$project` | Declares the list of fields to keep |
| Drop `internalNote` while keeping almost all other fields | `$unset` | Expresses exclusion clearly |
| Add `itemCount` while keeping the full document | `$set` | Adds a computed field without dropping others |
| Rename `customer.name` to `customerName` in a DTO | `$project` with expression | Places the output field at the desired position |
| Create `grossTotal` for the next stage to use | `$set` | Enriches intermediate documents |
| Drop multiple private fields at the end of a pipeline | `$unset` or inclusion `$project` | Controls output |
| Need both calculations and a 4-field response | `$set` first then `$project` later, or one `$project` with expressions | Separates computation from output selection |
| Remove a field conditionally | `$$REMOVE` inside an expression | Can drop fields based on logic |
| Modify documents stored in the collection | Do not use plain `aggregate()` | Requires appropriate update/pipeline write commands |

**Quick rule of thumb:** `$project` defines the **shape**, `$set` defines **added/updated values**, and `$unset` defines **fields that must disappear**.

## 11. $$REMOVE: Conditionally Removing Fields

`$unset` removes fields unconditionally for every document passing through the stage. If you want a field to appear for some documents and disappear for others, MongoDB supports the **`$$REMOVE`** system variable in appropriate expressions.

Example: keep `internalNote` in the output only when status is `CANCELLED`; omit the field for other statuses.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      noteForAudit: {
        $cond: [
          { $eq: ["$status", "CANCELLED"] },
          "$internalNote",
          "$$REMOVE"
        ]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

In the output:

- Document `ord-105` can have `noteForAudit: "Customer cancelled"`.
- Documents with other statuses do not contain the `noteForAudit` field.
- If the status is CANCELLED but the source lacks `internalNote`, the output field is not synthesized either.

### 11.1. $$REMOVE in $set

~~~javascript
db.orders.aggregate([
  {
    $set: {
      internalNote: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "$$REMOVE",
          "$internalNote"
        ]
      }
    }
  }
]);
~~~

When status is `PAID`, `internalNote` is removed from the intermediate document. For other statuses, the expression retains the existing field value.

This is useful when output shaping depends conditionally on a data field. However, **authorization and security** must never rely solely on a data-driven status condition. Sensitive fields should be controlled via access permissions and safe response contracts.

### 11.2. Distinguishing $$REMOVE from null

~~~javascript
{
  $project: {
    fieldA: { $literal: null },
    fieldB: "$$REMOVE"
  }
}
~~~

- `fieldA` **appears** with value null.
- `fieldB` **does not appear** in the output.

This is an important distinction for JSON APIs where an absent field and a null-valued field may carry different meanings.

## 12. $project and Path Collisions

A projection cannot simultaneously specify a parent field and a child path of that same field in a way that causes a **path collision**.

Invalid example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      customer: 1,
      "customer.name": 1
    }
  }
]);
~~~

Because you asked to keep the entire `customer` object and also specifically select `customer.name`, MongoDB will report a path collision error. Swapping the two keys does not resolve the issue.

Valid ways:

~~~javascript
// Select the entire object:
{
  $project: {
    customer: 1
  }
}

// Select only name inside the object:
{
  $project: {
    "customer.name": 1
  }
}

// Create a flattened field:
{
  $project: {
    customerName: "$customer.name"
  }
}
~~~

With `$set`, you should also avoid declaring conflicting parent/child paths in the same stage. If you genuinely need to construct a new object, define the final structure explicitly instead of specifying overlapping paths and relying on implicit write order.

## 13. Processing Arrays of Objects with $map

Selecting `"items.sku":1` is convenient when keeping simple fields. However, if you need to **calculate line totals**, you need an expression that iterates over each array element.

### 13.1. Computing lineTotal for Each Element

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      items: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            qty: "$$line.qty",
            price: "$$line.price",
            lineTotal: {
              $multiply: [
                "$$line.qty",
                "$$line.price"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Result for `ord-101`:

~~~javascript
{
  items: [
    {
      sku: "BK-01",
      qty: 2,
      price: NumberDecimal("20.00"),
      lineTotal: NumberDecimal("40.00")
    },
    {
      sku: "PEN-01",
      qty: 3,
      price: NumberDecimal("2.00"),
      lineTotal: NumberDecimal("6.00")
    }
  ]
}
~~~

The `internalCost` field was omitted from the `in` object, so it is excluded from the result array.

In `$map`:

- `input` is the array to iterate over.
- `as: "line"` names the variable for each element.
- `$$line` references that variable, unlike `$line` which references a document field.
- `in` is the expression producing each output element.

### 13.2. Keeping Existing Properties and Adding lineTotal

When you want to keep existing fields on each element, use `$mergeObjects`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      items: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            $mergeObjects: [
              "$$line",
              {
                lineTotal: {
                  $multiply: [
                    "$$line.qty",
                    "$$line.price"
                  ]
                }
              }
            ]
          }
        }
      }
    }
  },
  { $unset: "items.internalCost" },
  {
    $project: {
      _id: 0,
      items: 1
    }
  }
]);
~~~

Stage flow:

1. `$set` replaces `items` in the intermediate document with the array containing computed `lineTotal`.
2. `$unset` removes `internalCost` from each element.
3. `$project` returns only the `items` array.

If a document has `items: null` or lacks the field, `$map` can return null. If `items` is not an array, `$map` can throw an error. With unvalidated schemas, guard the type first:

~~~javascript
{
  $map: {
    input: {
      $cond: [
        { $isArray: "$items" },
        "$items",
        []
      ]
    },
    as: "line",
    in: "$$line.sku"
  }
}
~~~

### 13.3. Computing the Total Amount from an Array

For `ord-101`, line BK-01 = 2 × 20.00 = 40.00; line PEN-01 = 3 × 2.00 = 6.00. Total before discount = 46.00.

You can calculate this with `$map` followed by `$sum`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      grossTotal: {
        $sum: {
          $map: {
            input: { $ifNull: ["$items", []] },
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.price"
              ]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      grossTotal: 1
    }
  }
]);
~~~

On the sample data, `grossTotal` has a Decimal128 value of **46.00**.

When using Decimal128 for monetary values, avoid mixing unclear rounding rules into calculations. In real business domains, standardize currency units, taxes, discounts, and rounding rules according to the data contract.

### 13.4. Computing netTotal After Discount

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      grossTotal: {
        $sum: {
          $map: {
            input: { $ifNull: ["$items", []] },
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.price"
              ]
            }
          }
        }
      }
    }
  },
  {
    $set: {
      netTotal: {
        $subtract: [
          "$grossTotal",
          { $ifNull: ["$discount", NumberDecimal("0.00")] }
        ]
      }
    }
  },
  {
    $project: {
      _id: 0,
      grossTotal: 1,
      netTotal: 1
    }
  }
]);
~~~

Result values: `grossTotal = 46.00` and `netTotal = 41.00`.

Using two separate `$set` stages ensures `grossTotal` is created in the earlier stage before being referenced in the next stage. Do not rely on expressions within the same `$set` evaluating sequentially in declaration order to immediately reference a newly created sibling field.

## 14. Stage Order: Same Operators, Different Results

### 14.1. Using $set Before $project

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      customerName: "$customer.name"
    }
  },
  {
    $project: {
      _id: 0,
      customerName: 1,
      status: 1
    }
  }
]);
~~~

The result contains `customerName: "Lan"`, because `$set` can read `customer.name` before `$project` trims the document.

### 14.2. Using $project Too Early Can Lose Data Needed for Calculations

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      status: 1
    }
  },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
]);
~~~

After `$project`, the `customer` field no longer exists in the intermediate document. The expression `"$customer.name"` in the next stage cannot read back data that was dropped. Therefore, it cannot produce `"Lan"` like example 14.1.

If `customer.name` is still needed in a later stage, keep that field in the projection or move the calculation earlier.

### 14.3. Using $unset Too Early Causes the Same Problem

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $unset: "customer" },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
]);
~~~

Because `customer` was removed from the intermediate document, the next stage no longer has the data to create `customerName`. Stage ordering must follow field dependencies, not merely a habit of "dropping fields as early as possible."

### 14.4. Match Before or After Set?

When filtering on source fields:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $set: { customerName: "$customer.name" } },
  { $project: { customerName: 1, status: 1 } }
]);
~~~

An early `$match` typically limits the number of documents needing computation and creates opportunities for index usage.

When filtering on a **newly computed** field, you must create it first:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  { $match: { itemCount: { $gte: 2 } } },
  { $project: { _id: 1, itemCount: 1 } }
]);
~~~

In the sample set, ID `ord-101` has 2 elements while the rest have at most 1 or 0. Thus the result includes `ord-101`.

**There is no strict rule that every `$project` must be placed at the start of a pipeline for performance.** The MongoDB optimizer can automatically determine which fields are needed across stages in many scenarios. Prioritize a semantically clear pipeline and inspect the actual plan.

## 15. Distinguishing Aggregation $set from Update $set

Both syntaxes share the same name but appear in **different contexts**.

### 15.1. $set as an Aggregation Stage

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name",
      status: "VIEWED"
    }
  }
]);
~~~

This transforms documents in the aggregation result. It **does not save** `customerName` or `VIEWED` into the source collection.

### 15.2. $set as an Update Operator

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  {
    $set: {
      status: "SHIPPED"
    }
  }
);
~~~

This is a command updating a document stored in the database. After successful execution, `ord-101`'s `status` is modified on the server.

If you write a traditional update operator:

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
);
~~~

then with a traditional **update operator**, the string `"$customer.name"` is treated as a literal value to write, not an aggregation expression evaluated from a source field. Do not confuse it with the `$set` stage inside a pipeline.

### 15.3. Updating with an Aggregation Pipeline

MongoDB supports using an allowed subset of stages inside an **update pipeline**, for example:

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  [
    {
      $set: {
        customerName: "$customer.name"
      }
    },
    {
      $unset: "internalNote"
    }
  ]
);
~~~

In an **update pipeline** (where the update argument is an array of stages), `"$customer.name"` is evaluated as a field reference, and the new result is **written to the document**.

Key differences:

| Context | Example | Writes changes to collection? |
|---|---|---|
| `aggregate([{ $set: ... }])` | Stage in an aggregation query | No, if returning normal query results |
| `updateOne(filter, { $set: ... })` | Update operator | Yes |
| `updateOne(filter, [{ $set: ... }])` | Update pipeline stage | Yes |
| `aggregate([...,$merge])` | Pipeline with a write stage | May write per `$merge` configuration |

**Warning:** Applying `$unset` inside an update pipeline permanently deletes the field from the stored document. Therefore, do not practice update forms on production data and do not confuse them with pipelines meant only for shaping responses.

### 15.4. $unset Syntax in Two Different Contexts

Aggregation stage:

~~~javascript
{ $unset: "internalNote" }
{ $unset: ["internalNote", "items.internalCost"] }
~~~

Standard update operator:

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  {
    $unset: {
      internalNote: ""
    }
  }
);
~~~

Aggregation `$unset` accepts a string or an array of field-name strings. The `$unset` update operator takes an object mapping fields to placeholder values; the value after the field name does not determine what gets deleted. Do not copy syntax directly from one context to the other.

### 15.5. The _id Field and Immutability

In read-only pipelines, `$project: {_id:0}` or `$unset:"_id"` removes the ID from the **output**. The stored document still retains `_id`.

In update commands on existing documents, `_id` is immutable: it cannot be removed or modified even with an update pipeline. To expose a differently named ID, create an alias field such as `orderId` in the result instead of trying to alter the primary identifier.

## 16. $set and $addFields

Two aggregation stages:

~~~javascript
{
  $set: {
    customerName: "$customer.name"
  }
}
~~~

and:

~~~javascript
{
  $addFields: {
    customerName: "$customer.name"
  }
}
~~~

have the exact same meaning in aggregation: add or overwrite fields while keeping remaining fields.

Therefore, pick one consistent style in a codebase so readers can follow easily. `$set` often feels intuitive to those familiar with update operators, while `$addFields` clearly conveys "enriching the document" in a pipeline. Just remember that `$set` appears in both aggregate and update contexts, so pay attention to **which command** encloses it.

## 17. $project in find() Differs from the $project Stage in aggregate()

The `find()` query also accepts a **projection** as its second argument:

~~~javascript
db.orders.find(
  { tenantId: "tenant-A" },
  {
    _id: 0,
    status: 1,
    "customer.name": 1
  }
);
~~~

In aggregation:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 0,
      status: 1,
      "customer.name": 1
    }
  }
]);
~~~

For simple inclusion cases, both can produce equivalent output shapes.

However, do not treat them as completely identical APIs across all expressions or limitations. The `$project` stage is a pipeline component with computation capabilities that interacts with preceding and succeeding stages. `find()` projections have their own syntax, rules, and optimizations.

When you only need a simple query with filtering, sorting, and projection, `find()` may suffice. When you need to combine array calculations, grouping, joins, or multi-step shaping, an aggregation pipeline expresses the logic more clearly.

## 18. Data Security and Choosing Allowlist vs. Denylist

Suppose `orders` has these fields:

~~~text
public:
  _id
  status
  customer.name
  items.sku
  items.qty
  items.price

internal:
  tenantId
  customer.contact.phone
  items.internalCost
  internalNote
~~~

There are two output-shaping strategies.

### 18.1. Denylist with $unset

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $unset: [
      "tenantId",
      "customer.contact.phone",
      "items.internalCost",
      "internalNote"
    ]
  }
]);
~~~

This approach is simple when few fields need removal and the schema is stable. However, if an application later adds a sensitive field like `fraudScore` or `privateToken`, the old denylist **does not automatically drop the new field**.

### 18.2. Allowlist with $project

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      "customer.name": 1,
      "items.sku": 1,
      "items.qty": 1,
      "items.price": 1
    }
  }
]);
~~~

Only the listed fields appear. Newly added fields in the collection do not accidentally leak through the output.

For public APIs or documents containing sensitive data, an allowlist is usually safer to control. Even so, projection **does not replace authentication, authorization, MongoDB roles, or tenant checks**. Queries must filter permitted resources properly rather than relying solely on hiding a few fields.

### 18.3. $unset Is Not Permanent Erasure of Sensitive Data

In a normal aggregation:

~~~javascript
db.orders.aggregate([
  { $unset: "internalNote" }
]);
~~~

the `internalNote` value remains in the collection. If the requirement is to delete data from the database for retention/privacy policies, you need write operations, data governance procedures, backup checks, and scope audits; do not treat output projection as data erasure.

## 19. Performance and Projection Ordering

### 19.1. Should You $project Early to Reduce Load?

The MongoDB optimizer can automatically determine which fields are required across stages in many scenarios. Adding `$project` right at the start of a pipeline to "shrink size" does not always yield benefits.

For example:

~~~javascript
db.orders.aggregate([
  { $project: { status: 1 } },
  { $match: { status: "PAID" } }
]);
~~~

This may be reordered or optimized differently by the optimizer than the text order you see, depending on expressions and MongoDB version. However, if a later stage needs a field that was dropped, the pipeline cannot recover that field.

A clearer way when filtering on source fields:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $project: { _id: 1, status: 1 } }
]);
~~~

### 19.2. Does $project Reduce Network Transfer?

If the output no longer includes large fields like `items`, `customer.contact`, or internal metadata, the documents returned to the client are usually smaller. This can reduce payload size, network bandwidth, and JSON serialization overhead.

Still, the latency reduction depends on document counts, indexes, the pipeline, and infrastructure. It does not prove the server never had to read the excluded fields during intermediate processing.

### 19.3. Covered Queries and Indexes

An index can cover filtering/sorting/projection to the extent that full document fetches are unnecessary in certain query patterns. However, merely adding `$project` does not guarantee a covered query. Inspect the actual plan and distinguish fields satisfied from the index from fields fetched from the collection.

For example, consider an index serving a filter:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Then inspect the plan:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $project: { _id: 1, status: 1, createdAt: 1 } }
]);
~~~

Depending on the data and optimizer, the plan may contain `IXSCAN` or `COLLSCAN`. With 6 documents, a collection scan is usually not a sign needing urgent optimization.

### 19.4. Array Computations Have a Cost

`$map`, `$filter`, `$multiply`, `$sum`, and array reconstruction all require processing data. For very large arrays or multi-stage pipelines, calculations can consume significant CPU and memory.

Best practices:

- Filter unnecessary documents with `$match` when possible.
- Keep field dependencies clear across the pipeline.
- Measure `executionStats` and overall latency.
- Avoid returning huge arrays if the client only needs summaries.
- Reconsider the data model if arrays grow unbounded.

## 20. MongoDB Compass: Practicing Document Shaping

MongoDB Compass has an **Aggregations** tab for building and running pipelines. The UI may vary by version, but the general workflow is:

1. Connect to the MongoDB Server/cluster loaded with the `aggregation_shape_lab` database.
2. Open the `orders` collection.
3. Go to the **Aggregations** tab and create a new pipeline.
4. Add a `$match` stage to filter `tenant-A`:

   ~~~json
   {"tenantId":"tenant-A"}
   ~~~

5. Add a `$set` stage to create `customerName`:

   ~~~json
   {"customerName":"$customer.name"}
   ~~~

6. Add a `$project` stage to select the output:

   ~~~json
   {"_id":1,"status":1,"customerName":1}
   ~~~

7. Run the pipeline and observe how the document structure changes at each stage if Compass displays intermediate stage previews.
8. Replace `$project` with `$unset` on `internalNote` to compare inclusion and exclusion.
9. Experiment with the `items` array in `$project` or `$map` following the examples in section 13.
10. Return to the **Documents** tab and inspect the source records: transformations from a regular aggregation do not modify the collection.

If the stage editor does not accept an entire object wrapping the `$project` key, check whether the UI asks you to select the stage name in a separate dropdown. In mongosh, pipelines are always written in full:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $project: { status: 1 } }
]);
~~~

## 21. MongoDB Java Driver: Building Pipelines

With the Java Driver, you can construct aggregation pipelines using BSON `Document` objects. The following example assumes a connected `MongoDatabase` variable named `database` and a populated `orders` collection:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

MongoCollection<Document> orders = database.getCollection("orders");

List<Document> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "tenant-A")),

    new Document("$set",
        new Document("customerName", "$customer.name")),

    new Document("$project",
        new Document("_id", 1)
            .append("status", 1)
            .append("customerName", 1))
);

List<Document> result = orders.aggregate(pipeline)
    .into(new ArrayList<>());

for (Document order : result) {
    System.out.println(order.toJson());
}
~~~

The pipeline executes the same steps as the mongosh examples:

- `$match` restricts the tenant.
- `$set` adds the customer name from a nested field.
- `$project` builds an output containing only the selected fields.

### 21.1. Example: Removing Fields with the Java Driver

~~~java
List<Document> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "tenant-A")),

    new Document("$unset",
        Arrays.asList(
            "internalNote",
            "items.internalCost",
            "customer.contact.phone"
        ))
);

List<Document> publicOrders = orders.aggregate(pipeline)
    .into(new ArrayList<>());
~~~

`$unset` in aggregation accepts an array of strings; this preserves the exact MongoDB BSON structure. Applications can also use the Java Driver builders if the team agrees on them, while clearly distinguishing stage expressions from update operators.

### 21.2. DTOs and Response Contracts

An API can map aggregation documents to a DTO:

~~~java
public record OrderSummary(
    String orderId,
    String status,
    String customerName,
    int itemCount
) {}
~~~

To simplify mapping, the pipeline can shape the exact field names the DTO expects:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      status: 1,
      customerName: "$customer.name",
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  }
]);
~~~

That is a major benefit of `$project`: the API receives a shape ready for serialization instead of downloading full documents and stripping numerous fields in the application layer.

### 21.3. Distinguishing Output Shaping from Data Updates

If a developer runs:

~~~java
orders.aggregate(pipeline).into(new ArrayList<>());
~~~

this operation only reads results. It does not save `customerName` into the database. To persist changes, use a proper authorized write API; never mistake `$set` inside a read pipeline for an update operation.

## 22. Common Mistakes

| Situation | Cause | How to fix |
|---|---|---|
| Output still has `_id` | `$project` keeps `_id` by default | Use `_id:0` or `$unset:"_id"` |
| Output loses almost all fields | Used inclusion `$project` when intending to add fields | Use `$set` or list all fields to keep |
| Error mixing `1` and `0` | Inclusion/exclusion cannot be mixed arbitrarily | Choose one style, use another stage, or the `_id` exception |
| Path collision error | Selected both parent and child paths | Choose one path or define the output object explicitly |
| `customerName` does not appear properly | `customer` field was dropped in an earlier stage | Compute before dropping or keep the source field |
| `$set` loses nested subfields | Overwrote the entire `shipping` object | Use dot notation when updating only one subfield |
| `$unset` does not delete stored data | Normal aggregation does not write | Understand this only shapes output |
| Error passing an object to `$unset` stage | Confused with `$unset` update operator | The stage expects a string or array of strings |
| `$project` with `flag:1` does not produce number 1 | `1` means inclusion | Use `{ $literal: 1 }` |
| String `"$status"` displays status value | Strings starting with `$` are treated as field references | Use `$literal` if you want the literal string |
| `$size` errors when field is not an array | `$size` requires an array | Use `$isArray` and `$cond`/schema validation |
| `$map` returns null or errors | Input is null/missing or wrong type | Normalize/check input array |
| Field shows null when wanting full omission | Assigned `null` instead of `$$REMOVE` | Use `$$REMOVE` when the field should be absent |
| Accidental exposure of internal info | `$unset` denylist does not cover newly added fields | Use an allowlist `$project` for public APIs |
| After aggregation, `findOne` still shows old data | Read pipeline does not update the collection | Use an appropriate write API to persist changes |
| Page filter query is fast but pipeline is slow | Heavy array computation, different stage order/indexes | Inspect explain, measure CPU/I/O, and limit output |
| Referencing a sibling field in the same `$set` fails as expected | New field is not yet part of that stage's input | Split into sequential `$set` stages by dependency |

## 23. Comprehensive Practice Exercises

Run these in the `aggregation_shape_lab` database after loading the 6 sample documents. Each exercise can be run independently on the loaded collection because they use regular `aggregate()` without modifying source data.

### Exercise 1. Return Only Three Fields

Task: return only `_id`, `status`, and `customer.name` for tenant-A.

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      "customer.name": 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Expected:** 5 documents belonging to tenant-A, each containing only the requested fields.

### Exercise 2. Hide ID and Flatten Customer Name

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerName: "$customer.name",
      status: 1
    }
  }
]);
~~~

**Expected:** `{orderId:"ord-101",customerName:"Lan",status:"PAID"}` (no `_id` key in the output).

### Exercise 3. Remove Internal Data

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $unset: [
      "internalNote",
      "customer.contact.phone",
      "items.internalCost"
    ]
  }
]);
~~~

**Question:** Which fields remain in `items`? Is the source data in the collection modified?

### Exercise 4. Add customerName and itemCount

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name",
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  {
    $project: {
      _id: 1,
      customerName: 1,
      itemCount: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Expected:** `ord-101` has `itemCount:2`; `ord-103` has `itemCount:0`.

### Exercise 5. Using Literal Properly

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      countConstant: { $literal: 1 },
      dollarText: { $literal: "$status" }
    }
  }
]);
~~~

**Expected:** `countConstant` is the number 1; `dollarText` is the literal string `"$status"`, not `"PAID"`.

### Exercise 6. Computing lineTotal

For `ord-101`, use `$map` to return each item with `sku` and `lineTotal`; omit `internalCost`.

Hint:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      lines: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            lineTotal: {
              $multiply: ["$$line.qty", "$$line.price"]
            }
          }
        }
      }
    }
  }
]);
~~~

Result values for the two lines: **40.00** and **6.00**.

### Exercise 7. Computing grossTotal and netTotal

Use two `$set` stages:

1. Compute `grossTotal` from the `items` array.
2. Compute `netTotal = grossTotal - discount`, treating null/missing discount as 0.

For `ord-101`, expected results are **46.00** and **41.00**.

### Exercise 8. Conditionally Removing a Field

Return `noteForAudit` only when `status = "CANCELLED"`.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      noteForAudit: {
        $cond: [
          { $eq: ["$status", "CANCELLED"] },
          "$internalNote",
          "$$REMOVE"
        ]
      }
    }
  }
]);
~~~

**Question:** What is the difference between `$$REMOVE` and `null`?

### Exercise 9. Identifying Invalid Projections

Examine:

~~~javascript
{
  $project: {
    status: 1,
    internalNote: 0
  }
}
~~~

and:

~~~javascript
{
  $project: {
    customer: 1,
    "customer.name": 1
  }
}
~~~

**Task:** Explain the error in each snippet, then write the corresponding valid expressions.

### Exercise 10. Comparing $set and $project

Run sequentially:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $set: { isPaid: { $eq: ["$status", "PAID"] } } }
]);

db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      isPaid: { $eq: ["$status", "PAID"] }
    }
  }
]);
~~~

**Question:** Why does the first result have more fields? Does the second result include `_id`?

### Exercise 11. Nested Objects and Dot Notation

Try both approaches:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $set: { "shipping.city": "Cần Thơ" } },
  { $project: { shipping: 1 } }
]);

db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $set: { shipping: { city: "Cần Thơ" } } },
  { $project: { shipping: 1 } }
]);
~~~

**Expected:** The first query retains `shipping.method`; the second omits that field in the output. Check `findOne` to confirm the source document was not modified.

### Exercise 12. Testing Stage Order

Run `$project` keeping only `status` before `$set:{customerName:"$customer.name"}`, then swap the order of the two stages. Explain why the first approach fails to produce `"Lan"` like the second.

### Exercise 13. Distinguishing Update Pipelines from Aggregation

Compare:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-102" } },
  { $set: { status: "PENDING" } }
]);
~~~

with:

~~~javascript
// Only run in a practice database when intending to modify data.
db.orders.updateOne(
  { _id: "ord-102" },
  [
    { $set: { status: "PENDING" } }
  ]
);
~~~

**Question:** Why does only the second command alter the stored document? What happens the next time you reload the sample dataset?

### Exercise 14. Designing Output for a Public API

API requirement to return only:

~~~javascript
{
  orderId: "...",
  status: "...",
  customerName: "...",
  items: [
    { sku: "...", qty: 0, price: NumberDecimal("0") }
  ]
}
~~~

Write a pipeline:

- `$match` by authenticated `tenantId`.
- `$project` to create `orderId`, `customerName`, and keep `status`.
- Select the item fields `sku`, `qty`, and `price`.
- Ensure `internalCost`, `internalNote`, or `customer.contact.phone` never appear.

Compare the allowlist `$project` strategy against using only `$unset` based on the current field list.

## 24. Self-Check Questions

**Question 1.** Does `$project:{status:1}` keep `_id`?

*Answer:* Yes, unless `_id:0` is specified.

**Question 2.** Can you write `$project:{status:1, internalNote:0}`?

*Answer:* No, under standard include/exclude mixing rules; the exception is `_id` handling.

**Question 3.** If you only want to add an `itemCount` field while keeping all other fields, what should you use?

*Answer:* `$set` or `$addFields`.

**Question 4.** How do you remove `items.internalCost` from every element of an object array in the output?

*Answer:* Use `$unset:"items.internalCost"` or an equivalent exclusion projection if the data structure permits.

**Question 5.** Does `$unset:"internalNote"` in aggregate delete the field from the actual database?

*Answer:* No, when it is just an aggregation pipeline returning results without a write stage.

**Question 6.** Why does assigning `constant:1` in `$project` not set a field named `constant` to the number 1?

*Answer:* `1` is the inclusion flag; to output literal 1, use `{$literal:1}`.

**Question 7.** What is the difference between `"$customer.name"` and `"$$line.sku"`?

*Answer:* `$customer.name` reads a field of the input document; `$$line.sku` reads a property of the `line` variable created inside an expression such as `$map`.

**Question 8.** Can `$set` and `$project` stages be swapped arbitrarily?

*Answer:* No. If the projection drops a field needed by a later stage, the result changes.

**Question 9.** To drop a field when a condition is true, which tool should you look at?

*Answer:* `$$REMOVE` combined with an expression such as `$cond`.

**Question 10.** When an API returns documents to clients, is an allowlist or a denylist safer for response structure?

*Answer:* An allowlist `$project` generally provides better control against newly added fields later, though it does not replace authorization or access-control checks.

## 25. Key Principles to Remember

- **`$project`**: Selects, excludes, or computes fields in **output documents**. Keeps `_id` by default; cannot arbitrarily mix inclusion and exclusion.
- **`$set`**: Adds/overwrites fields while keeping other fields; is an alias for `$addFields` in aggregation.
- **`$unset`**: Removes one or more fields; functionally equivalent to an exclusion projection.
- **`$literal`**: Used when you need `0`/`1` as literal data values or strings starting with `$` without MongoDB interpreting them as control symbols.
- **`$$REMOVE`**: Conditionally removes a field, distinct from creating a field with a `null` value.
- **Nested paths**: Use dot notation to preserve nested structure or modify a single subfield; watch out for parent/child path collisions.
- **Arrays**: Select simple subfields via projection; use `$map` for per-element calculations and deeper shaping.
- **Stage order matters**: A field dropped in an earlier stage cannot be referenced as source data in a later stage.
- **Read aggregation differs from write updates**: `$set`/`$unset` in normal `aggregate()` does not alter the collection; an update pipeline is required to actually write.
- **Public APIs**: Prefer output allowlists and maintain tenant/permission filters; never rely solely on stripping known fields.
- **Performance**: Place `$match` thoughtfully, measure `explain` and computation cost; do not treat early `$project` as a guaranteed optimization.

The three stages `$project`, `$set`, and `$unset` are fundamental building blocks of aggregation pipelines. Once you clearly understand **selecting fields**, **adding or replacing fields**, and **removing fields** as three distinct operations, you can shape query results to match API contracts cleanly, keep calculations readable, and avoid leaking or losing data unintentionally.