# Replacing the Root Document with $replaceRoot and $replaceWith in MongoDB

## 1. The Problem: When the Input Document Shape Is Not the Desired Output Shape

MongoDB stores data in **BSON documents**. A document can contain nested objects, arrays, and fields describing many parts of an entity. The optimal storage structure is not always the structure that an API, report, or subsequent processing step expects to receive.

Example order document:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  orderNo: "ORDER-1001",
  status: "PAID",
  shipping: {
    recipient: "An",
    city: "Hà Nội",
    postalCode: "100000"
  },
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 120000 },
    { sku: "PEN-01", quantity: 3, unitPrice: 10000 }
  ]
}
```

An application might need three output shapes:

1. **Shipping details only**: the output has `recipient`, `city`, and `postalCode` at the top level, without the wrapping `shipping` object.
2. **Each line item as its own document**: the output has `sku`, `quantity`, `unitPrice`, and a few essential order fields.
3. **Combining data from multiple sources**: building a result document with a completely different structure from the original document.

In an aggregation pipeline, two stages solve the problem of **replacing the entire current root document**:

- `$replaceRoot` — specifies the expression under the `newRoot` property.
- `$replaceWith` — writes the expression producing the new document directly.

They share the same purpose and differ mainly in syntax. **Root document** here means the document **a pipeline stage is currently processing**, not automatically overwriting documents stored in the collection.

This lesson helps you:

- Understand the root document concept and how it differs from modifying fields with `$set` or selecting fields with `$project`.
- Write equivalent `$replaceRoot` and `$replaceWith` stages.
- Promote nested objects to the top level, replace the root with a custom-built document, and retain required fields.
- Combine `$unwind`, `$group`, and `$lookup` with root replacement.
- Handle missing objects, `null`, wrong types, and arrays so pipelines do not fail unexpectedly.
- Distinguish root replacement in read-only pipelines from modifying real documents with update pipelines.

## 2. What Is the Root Document?

### 2.1. Documents Flowing Through Stages

An aggregation pipeline is a sequence of stages:

```text
Collection
    |
    v
$match  --> $project --> $replaceWith --> $sort
    |         |             |            |
    v         v             v            v
Documents at each step can have different shapes
```

A stage receives a document from the preceding stage and passes a document to the next stage. "Root" is the **current top-level object** of the document at that position.

Suppose the initial document is:

```javascript
{
  _id: "ORDER-1001",
  status: "PAID",
  shipping: {
    recipient: "An",
    city: "Hà Nội"
  }
}
```

When the pipeline receives this document:

- `$_id` accesses the `_id` field of the current root.
- `$shipping` accesses the `shipping` object at the root.
- `$shipping.city` accesses the `city` field inside `shipping`.
- `$$ROOT` is the system variable representing the **entire root document at the current stage**.

After a stage replaces the root with `shipping`:

```javascript
{
  recipient: "An",
  city: "Hà Nội"
}
```

In subsequent stages, `$city` accesses the city directly; `$shipping.city` no longer exists, because `shipping` is no longer an enclosing object. `_id` and `status` are not kept automatically either.

### 2.2. Replacing the Root Replaces the Entire Shape

When using `$replaceRoot` or `$replaceWith`, the old document **is completely replaced** by the object value returned by the expression. MongoDB does not merge the two objects automatically, nor does it keep `_id`.

This differs from:

```javascript
{ $set: { city: "$shipping.city" } }
```

`$set` adds or updates the `city` field on the existing document while keeping other fields intact (unless modified/removed by another stage).

### 2.3. Replacing the Root Does Not Write to the Collection by Default

```javascript
db.orders.aggregate([
  { $replaceWith: "$shipping" }
]);
```

An `aggregate()` pipeline reads and returns transformed results. **Documents stored in `db.orders` do not change** merely because `$replaceWith` or `$replaceRoot` appears in a read pipeline.

Writing aggregation output to a collection requires an explicit write stage such as `$merge` or `$out` with proper permissions and governance. Additionally, MongoDB supports **aggregation pipeline updates** with a subset of stages, including root replacement, to update stored documents; that case is contrasted later.

## 3. Syntax of $replaceRoot and $replaceWith

### 3.1. `$replaceRoot`

Syntax:

```javascript
{
  $replaceRoot: {
    newRoot: <expression>
  }
}
```

`<expression>` can be:

- a path to a nested object in the document, such as `"$shipping"`;
- a new object constructed from existing fields;
- an expression returning a document, such as `$mergeObjects`;
- the result of a conditional expression returning an object.

Example:

```javascript
db.orders.aggregate([
  {
    $replaceRoot: {
      newRoot: "$shipping"
    }
  }
]);
```

In this stage, `newRoot` must evaluate to **a document (object)** for every input passing through the stage.

### 3.2. `$replaceWith`

Syntax:

```javascript
{
  $replaceWith: <expression>
}
```

Example:

```javascript
db.orders.aggregate([
  {
    $replaceWith: "$shipping"
  }
]);
```

This is a shorter form omitting the `newRoot` property name. Functionally, `$replaceWith` is an alternative syntax for `$replaceRoot` in most cases.

### 3.3. Two Equivalent Stages

The following two pipelines express the exact same transformation:

```javascript
// Option A.
db.orders.aggregate([
  { $replaceRoot: { newRoot: "$shipping" } }
]);

// Option B.
db.orders.aggregate([
  { $replaceWith: "$shipping" }
]);
```

Given the same input documents and the same expression, **both stages have identical result-type requirements and error-handling behavior**. Neither stage alters source data, catches `null` automatically, or preserves `_id`.

### 3.4. Quick Comparison Table

| Feature | `$replaceRoot` | `$replaceWith` |
| --- | --- | --- |
| Syntax | `{ $replaceRoot: { newRoot: expr } }` | `{ $replaceWith: expr }` |
| Expected expression return type | Document | Document |
| Replaces the entire current root | Yes | Yes |
| Keeps `_id` automatically | No | No |
| Used to promote nested objects to root | Yes | Yes |
| Works with `$mergeObjects` | Yes | Yes |
| Running on missing/`null`/non-object values | Can error | Can error |
| Modifies collection in read-only `aggregate()`? | No | No |

## 4. Creating Practice Data via mongosh

Examples use a dedicated test database `mongo_replace_root_row186_lab` and two collections `orders_demo` and `customers_demo`. Connect to an authorized MongoDB instance before running. Example:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Adjust the URI for your environment's host, TLS, and authentication. In `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_replace_root_row186_lab");
const orders = lab.getCollection("orders_demo");
const customers = lab.getCollection("customers_demo");

const runId = "row186-" + new ObjectId().toHexString();
const anId = new ObjectId();
const binhId = new ObjectId();

customers.insertMany([
  {
    _id: anId,
    runId,
    displayName: "Nguyễn An",
    tier: "GOLD"
  },
  {
    _id: binhId,
    runId,
    displayName: "Trần Bình",
    tier: "SILVER"
  }
]);

const order1Id = new ObjectId();
const order2Id = new ObjectId();
const order3Id = new ObjectId();
const order4Id = new ObjectId();

orders.insertMany([
  {
    _id: order1Id,
    runId,
    orderNo: "ORDER-186-01",
    customerId: anId,
    status: "PAID",
    createdAt: ISODate("2026-11-10T02:00:00Z"),
    totalAmount: 270000,
    shipping: {
      recipient: "An",
      city: "Hà Nội",
      postalCode: "100000"
    },
    items: [
      { sku: "BOOK-01", quantity: 2, unitPrice: 120000 },
      { sku: "PEN-01", quantity: 3, unitPrice: 10000 }
    ]
  },
  {
    _id: order2Id,
    runId,
    orderNo: "ORDER-186-02",
    customerId: binhId,
    status: "NEW",
    createdAt: ISODate("2026-11-11T03:00:00Z"),
    totalAmount: 99000,
    shipping: {
      recipient: "Bình",
      city: "Đà Nẵng",
      postalCode: "550000"
    },
    items: [
      { sku: "NOTE-01", quantity: 1, unitPrice: 99000 }
    ]
  },
  {
    _id: order3Id,
    runId,
    orderNo: "ORDER-186-03",
    customerId: anId,
    status: "DRAFT",
    createdAt: ISODate("2026-11-12T04:00:00Z"),
    totalAmount: 0,
    shipping: null,
    items: []
  },
  {
    _id: order4Id,
    runId,
    orderNo: "ORDER-186-04",
    customerId: anId,
    status: "DRAFT",
    createdAt: ISODate("2026-11-13T05:00:00Z"),
    totalAmount: 0,
    items: []
    // Intentionally missing the shipping field.
  }
]);

print("database=" + lab.getName());
print("runId=" + runId);
print("orders=" + orders.countDocuments({ runId }));
```

The first two orders have a `shipping` object, the third has `shipping: null`, and the fourth lacks the `shipping` field. This data clearly highlights the issues when promoting sub-objects to root.

The examples below assume the **same `mongosh` session**, where `lab`, `orders`, `customers`, `runId`, and ID variables remain defined. Do not query/delete using a guessed `runId` after opening a new session.

## 5. Promoting a Nested Object to Root

### 5.1. Simple Case: All Documents Have a Valid Object

We select only orders where `shipping` is an object:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceRoot: {
      newRoot: "$shipping"
    }
  }
]);
```

The two output documents look like:

```javascript
{
  recipient: "An",
  city: "Hà Nội",
  postalCode: "100000"
}
{
  recipient: "Bình",
  city: "Đà Nẵng",
  postalCode: "550000"
}
```

Key observations:

- `shipping` is no longer a wrapping object.
- `recipient`, `city`, and `postalCode` become root-level fields.
- The order's `_id` is no longer in the result document.
- `orderNo`, `status`, `customerId`, and `runId` are not automatically retained either.

This is the intentional behavior of **replacing the entire root**.

### 5.2. Equivalent Form with `$replaceWith`

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  { $replaceWith: "$shipping" }
]);
```

No change to input data or filters is needed when switching between the two stages—only the root-replacement syntax changes.

### 5.3. Why Use `$expr + $type` Beforehand?

The expression:

```javascript
{
  $expr: {
    $eq: [{ $type: "$shipping" }, "object"]
  }
}
```

checks that the field value in the **current document** has BSON type object. Consequently:

- Documents with `shipping` as an object proceed.
- Documents with `shipping: null` are filtered out.
- Documents missing `shipping` are filtered out.
- Documents where `shipping` is a string, number, or array are kept out of the root-replacement stage.

This differs from some query field matches that may inspect array elements. When protecting a root-replacement expression against non-object values, checking the type of the **expression value** expresses the guard clearly.

## 6. What Happens When the Field Is Missing or Not a Document?

### 6.1. Error Case

If you run the following pipeline on all four orders:

```javascript
// Example THAT CAN ERROR due to null/missing shipping.
orders.aggregate([
  { $match: { runId } },
  { $replaceWith: "$shipping" }
]);
```

The root-replacement stage requires the expression to return a valid document. When `$shipping` is `null`, missing, or a type such as string/array, aggregation fails instead of returning an empty document.

MongoDB does not coerce `null` to `{}`, expand arrays into multiple documents, or silently skip failing documents in this stage.

### 6.2. Approach 1: Filter First

If the requirement only needs documents that **actually have valid shipping**:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  { $replaceWith: "$shipping" }
]);
```

This omits orders without shipping info from the **pipeline result**, without deleting them from the collection.

### 6.3. Approach 2: Default Value for Null/Missing

When data guarantees `shipping` can only be an object, `null`, or missing, you can use `$ifNull`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      $ifNull: [
        "$shipping",
        {
          recipient: "Not provided",
          city: "Unspecified"
        }
      ]
    }
  }
]);
```

For orders with `shipping: null` or missing `shipping`, the result is the default object. However, if `shipping` holds a **string**, `$ifNull` still returns that string because it is not null, and `$replaceWith` will still error.

Therefore:

> `$ifNull` handles null/missing, **not** general type checking.

### 6.4. Approach 3: Check Type and Fallback

To guard against malformed types as well:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      $cond: {
        if: {
          $eq: [{ $type: "$shipping" }, "object"]
        },
        then: "$shipping",
        else: {
          recipient: "Not provided",
          city: "Unspecified"
        }
      }
    }
  }
]);
```

Here both branches of `$cond` produce a document. If the `then` branch receives an object, it is used; all other types fall back to the default object.

In production systems, distinguish:

- **Legitimately absent business data** → a fallback can be appropriate.
- **Schema-violating data** → sometimes you should raise an error, fix the parser, or migrate rather than silently masking it.

Fallbacks make pipelines resilient, but do not replace data-quality governance.

## 7. Retaining Old Root Info with $mergeObjects

### 7.1. The Lost-Information Problem

After `$replaceWith: "$shipping"`, the API only sees the address. To return:

```javascript
{
  orderId: ObjectId("..."),
  orderNo: "ORDER-186-01",
  status: "PAID",
  recipient: "An",
  city: "Hà Nội",
  postalCode: "100000"
}
```

you must **explicitly bring the desired order fields into the new root**.

A well-suited aggregation operator is `$mergeObjects`.

### 7.2. What Does `$mergeObjects` Do?

`$mergeObjects` takes multiple objects and produces a combined object. When two objects share a field name, **the value from the later object overwrites the earlier value**. `null` operands are ignored per `$mergeObjects` semantics.

Example:

```javascript
{
  $mergeObjects: [
    { city: "Unspecified", active: false },
    { city: "Hà Nội", recipient: "An" },
    { active: true }
  ]
}
```

Expression result:

```javascript
{
  city: "Hà Nội",
  active: true,
  recipient: "An"
}
```

Operand order is therefore critical whenever field names overlap.

### 7.3. Promoting Shipping to Root While Retaining Needed Fields

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$shipping",
          {
            orderId: "$_id",
            orderNo: "$orderNo",
            status: "$status",
            createdAt: "$createdAt"
          }
        ]
      }
    }
  }
]);
```

The object built from order fields comes **after** `"$shipping"`. If shipping happened to contain a field named `status` or `orderNo`, the order's value wins under this merge order.

The output includes both shipping fields and order metadata, without a nested `shipping` object and without automatically keeping `_id`. The `orderId` field is explicitly included to preserve the order ID under a new name.

### 7.4. Retaining `_id` Itself

If the API needs the order's `_id` in the output:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$shipping",
        {
          _id: "$_id",
          orderNo: "$orderNo",
          status: "$status"
        }
      ]
    }
  }
]);
```

MongoDB keeps `_id` solely because you **explicitly added it to the new object**. Otherwise, the new output will lack `_id`.

### 7.5. Using a Default Object to Avoid Missing Fields

To emit a document for every order, even when shipping is absent:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      $mergeObjects: [
        {
          recipient: "Not provided",
          city: "Unspecified"
        },
        {
          $cond: [
            { $eq: [{ $type: "$shipping" }, "object"] },
            "$shipping",
            {}
          ]
        },
        {
          orderId: "$_id",
          orderNo: "$orderNo",
          status: "$status"
        }
      ]
    }
  }
]);
```

Each of the three operands has a clear role:

1. **Default** — provides baseline fields.
2. **Valid shipping object** — overrides defaults with actual data.
3. **Order metadata** — supplies mandatory output fields.

If you only need to handle null/missing and are certain no wrong types exist, you can replace `$cond` with `{ $ifNull: ["$shipping", {}] }`. When mixed types are possible, checking `$type` ensures the merge operator never receives a string or array.

## 8. Keeping the Original Document and Partially "Flattening" It

Sometimes the goal is not dropping old fields, but promoting shipping fields to the top level **while keeping all other fields**.

### 8.1. Using `$$ROOT`

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$$ROOT",
        "$shipping"
      ]
    }
  }
]);
```

In the root-replacement stage, `$$ROOT` represents the entire current document. Then `$shipping` is merged on top. Original fields like `orderNo` and `items` remain, and shipping fields are added at the root.

Example:

```javascript
{
  _id: ObjectId("..."),
  orderNo: "ORDER-186-01",
  status: "PAID",
  shipping: {
    recipient: "An",
    city: "Hà Nội",
    postalCode: "100000"
  },
  recipient: "An",
  city: "Hà Nội",
  postalCode: "100000",
  items: [/* ... */]
}
```

This **copies nested info to the outer level**; it does not automatically remove the nested field. The `shipping` object still remains.

### 8.2. Removing the Nested Object After Promoting Its Fields

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: ["$$ROOT", "$shipping"]
    }
  },
  { $unset: "shipping" }
]);
```

`$unset` drops the `shipping` field from the pipeline result document. In practice, watch out for **field name collisions**: if the shipping object contains a `status` field, the later merge overwrites the order's status. For a stable, safe output contract, building the target object explicitly with `$project` or `$replaceWith` is often cleaner.

## 9. Using $replaceWith to Build a New Document per API Contract

You do not have to extract an existing sub-object. `$replaceWith` accepts a custom-built object expression:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      orderId: "$_id",
      code: "$orderNo",
      state: "$status",
      amount: "$totalAmount",
      orderedAt: "$createdAt",
      city: {
        $ifNull: ["$shipping.city", "Unspecified"]
      },
      label: {
        $concat: ["Order ", "$orderNo"]
      }
    }
  },
  { $sort: { orderedAt: -1 } }
]);
```

The newly constructed object has:

- `orderId` taken from `_id`.
- `code` renamed from `orderNo`.
- `state` renamed from `status`.
- `amount` renamed from `totalAmount`.
- `orderedAt` renamed from `createdAt`.
- `city` extracted from the sub-object with a fallback.
- `label` computed using `$concat`.

After `$replaceWith`, the `$sort` stage must use the new field name `orderedAt`, because `createdAt` no longer exists in the output. This is a very common side effect of replacing the root mid-pipeline.

### 9.1. Constant Values and Field Names Starting with Special Characters

Inside expressions, a string starting with `$` is interpreted as a **field path** or expression syntax. To emit a literal like `"$10 voucher"`, use `$literal`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      promotionLabel: { $literal: "$10 voucher" }
    }
  }
]);
```

An object returned by `$replaceWith` must still be a valid document obeying field-name and BSON rules. Never use an expression returning a scalar at the top level of a root-replacement stage.

## 10. Combining $unwind to Turn Array Elements into Roots

### 10.1. Why Is `$unwind` Needed?

An order document contains multiple line items:

```javascript
{
  orderNo: "ORDER-186-01",
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 120000 },
    { sku: "PEN-01", quantity: 3, unitPrice: 10000 }
  ]
}
```

If you pass `$items` directly to root:

```javascript
// Not the right way to create one document per item.
{ $replaceWith: "$items" }
```

`$items` is an **array**, not a document. Root replacement requires an object, so an array cannot become multiple roots via `$replaceWith` alone.

To make **each array element become an output document**, use `$unwind` first:

```text
Order (items = [A, B])
          |
       $unwind
        /    \
       v      v
 Order+A    Order+B
       |      |
       +-- $replaceWith: "$items"
             |
             v
        Item A, Item B
```

### 10.2. Each Line Item as Its Own Root

```javascript
orders.aggregate([
  { $match: { runId } },
  { $unwind: "$items" },
  { $replaceWith: "$items" }
]);
```

Result from the sample dataset:

```javascript
{ sku: "BOOK-01", quantity: 2, unitPrice: 120000 }
{ sku: "PEN-01", quantity: 3, unitPrice: 10000 }
{ sku: "NOTE-01", quantity: 1, unitPrice: 99000 }
```

Orders with `items: []` contribute zero elements under default `$unwind` behavior. After `$unwind`, `$items` is a single line-item object, so root replacement succeeds.

### 10.3. Splitting Line Items While Retaining Order Info

To give each item its order code for further processing:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $unwind: "$items" },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$items",
          {
            orderId: "$_id",
            orderNo: "$orderNo",
            orderStatus: "$status",
            createdAt: "$createdAt"
          }
        ]
      }
    }
  },
  { $sort: { orderNo: 1, sku: 1 } }
]);
```

The result contains item fields alongside `orderId`, `orderNo`, and `orderStatus`. Placing order metadata last in `$mergeObjects` gives order fields precedence if any names overlap.

If each item had its own `_id`, distinguish item ID from order ID: use clear names like `orderId` and `lineItemId` rather than blindly carrying `_id` across flattening steps.

### 10.4. Non-Object Array Elements

If `items` is an array of strings such as `["A","B"]`, after `$unwind` each `$items` is a string; `$replaceWith: "$items"` is invalid. When an array holds primitive values, **wrap them in an object**:

```javascript
db.catalog.aggregate([
  { $unwind: "$tags" },
  {
    $replaceWith: {
      sourceId: "$_id",
      tag: "$tags"
    }
  }
]);
```

This illustrates a tag array in a hypothetical `catalog` collection; because the new root is **constructed as an object**, string values in `tags` do not cause a root-type error. General rule: the expression in `$replaceWith` must return an object, regardless of the types of individual fields inside that object.

## 11. Combining $group to Promote Grouping Keys to Root Fields

A reporting pipeline often includes `$group`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: {
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$totalAmount" }
    }
  }
]);
```

The output has the shape:

```javascript
{
  _id: { status: "PAID" },
  orderCount: 1,
  totalAmount: 270000
}
```

If the report wants `status` as a top-level field rather than `_id.status`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: {
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$totalAmount" }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$_id",
        {
          orderCount: "$orderCount",
          totalAmount: "$totalAmount"
        }
      ]
    }
  },
  { $sort: { status: 1 } }
]);
```

Output:

```javascript
{
  status: "PAID",
  orderCount: 1,
  totalAmount: 270000
}
```

In the `$group` step, `_id` was built as an **object**, so it can be merged. If the grouping key is a scalar, e.g. `_id: "$status"`, then `$replaceWith: "$_id"` is **invalid**, because the string `"PAID"` is not a document. In that case, wrap the scalar in an object:

```javascript
{
  $replaceWith: {
    status: "$_id",
    orderCount: "$orderCount"
  }
}
```

Constructing an explicit object also helps control exactly which fields appear in the report.

## 12. Combining $lookup with $unwind and Root Replacement

### 12.1. Joined Data Typically Lives in an Array

For orders with `customerId`, `$lookup` against `customers_demo` creates a `customer` field as an **array of documents**, even when each `customerId` matches at most one customer.

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $lookup: {
      from: "customers_demo",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
```

The result retains the full order plus:

```javascript
customer: [
  {
    _id: ObjectId("..."),
    runId: "row186-...",
    displayName: "Nguyễn An",
    tier: "GOLD"
  }
]
```

You cannot promote `"$customer"` directly to root because it is an array. Handle the array type first.

### 12.2. Extracting One Customer and Merging with Order Metadata

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $lookup: {
      from: "customers_demo",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $replaceWith: {
      $mergeObjects: [
        "$customer",
        {
          orderId: "$_id",
          orderNo: "$orderNo",
          orderStatus: "$status",
          orderAmount: "$totalAmount"
        }
      ]
    }
  },
  {
    $project: {
      _id: 0,
      orderId: 1,
      orderNo: 1,
      orderStatus: 1,
      orderAmount: 1,
      displayName: 1,
      tier: 1
    }
  }
]);
```

Explanation:

1. `$match` scopes down to orders from this practice run.
2. `$lookup` joins `customerId` against `customers_demo._id`.
3. `$unwind` turns the `customer` array into a single object per result.
4. `$mergeObjects` creates a root combining customer details and order metadata.
5. `$project` selects exact fields required by the API, preventing accidental leakage of full customer records.

If an order matches no customer, default `$unwind` drops that order. To keep orders with missing customers, use `preserveNullAndEmptyArrays: true` and provide fallbacks via `$mergeObjects` or conditional expressions. Base the missing-data policy on business requirements rather than blindly ignoring or accepting it.

### 12.3. Avoiding Field Name Collisions

After `$lookup`, the customer document also has `_id`, and the order has `_id`. Using `$mergeObjects: ["$$ROOT", "$customer"]` causes the customer's `_id` to overwrite the order's `_id`.

For clarity:

- extract `orderId` explicitly from `$_id` before promoting customer fields to root;
- name `customerId` unambiguously according to the customer key;
- use `$project` or explicit object construction when field names collide;
- ensure the API never confuses an order's `_id` with a customer's `_id`.

## 13. Comparing $replaceRoot/$replaceWith with Other Stages

| Stage | Primary role | Replaces entire root? |
| --- | --- | --- |
| `$project` | Selects, drops, renames, or computes output fields | Shapes specified fields, but lacks direct "make sub-object the root" syntax like `$replaceWith` |
| `$set` / `$addFields` | Adds or overwrites fields on the current document | Does not drop other fields by default |
| `$unset` | Removes fields | Does not replace the entire document with another object |
| `$replaceRoot` | Replaces root using the `newRoot` expression | Yes |
| `$replaceWith` | Replaces root using a direct expression | Yes |
| `$unwind` | Splits each array element into a downstream document | Does not promote elements to root on its own |
| `$group` | Groups documents and computes group aggregates | Creates group documents, typically with `_id` as the grouping key |

Example showing three output strategies with different meanings:

```javascript
// A: add a field at root level while keeping most existing fields.
{
  $set: {
    city: "$shipping.city"
  }
}

// B: output only selected fields.
{
  $project: {
    _id: 0,
    orderNo: 1,
    city: "$shipping.city"
  }
}

// C: use the entire shipping object as the root.
{
  $replaceWith: "$shipping"
}
```

Choose the stage based on the output contract:

- Need to **adjust a few fields**: `$set` is often more intuitive.
- Need to **select a fixed set of fields**: `$project` is easy to control.
- Need to **promote a nested or merged object to become the entire root**: `$replaceRoot`/`$replaceWith` is the right fit.

Do not force `$replaceWith` into every problem just because its syntax is concise. Stage count, computational cost, code readability, and field-loss risk all matter.

## 14. Stage Order and Index Usage

### 14.1. Filter Early Whenever Possible

When a pipeline only needs documents for a given tenant or status, filter early on source fields before replacing the root:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      status: "PAID"
    }
  },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      city: "$shipping.city",
      amount: "$totalAmount"
    }
  }
]);
```

Reasons:

- `$match` on original fields can exploit indexes if suitable ones exist.
- Fewer documents need transformation.
- After `$replaceWith`, old field names/paths may no longer exist, so filters would have to be rewritten for the new shape.

For instance, if the root was replaced with `shipping`, a trailing `{$match:{status:"PAID"}}` fails to match as intended because `status` no longer exists in the output.

MongoDB can optimize stage order automatically when safe. Even so, never write pipelines expecting the optimizer to recover fields you already dropped or reshaped.

### 14.2. Does Root Replacement Use Indexes Directly?

`$replaceWith` is a document-shaping stage, not an index scan mechanism. Indexes assist selection, filtering, and sorting phases under suitable conditions. Replacing the root may force the engine to read non-indexed fields; it does not make a query covered by itself.

For example, an index on `{runId:1,status:1}` helps the corresponding `$match`. Yet if `$replaceWith` needs the whole `shipping` object which is not in the index, MongoDB must fetch the source documents.

In real systems, use `explain("executionStats")` to inspect documents/index keys scanned, the winning plan, and execution steps. A multi-stage pipeline is not inherently slow; cost depends on document counts, data sizes, and how indexes serve inputs.

### 14.3. Sort Before or After Root Replacement?

If you only need to preserve original chronological order:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $sort: { createdAt: -1 } },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      city: "$shipping.city"
    }
  }
]);
```

Sort by `createdAt` before dropping that field from the document. To sort afterward, keep an output field holding the sort value, e.g., `orderedAt: "$createdAt"`, and then run `$sort: {orderedAt:-1}`.

## 15. Distinguishing Read Aggregation from Write Update Pipelines

### 15.1. A Stage Does Not Alter the Collection on Its Own

The command:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $replaceWith: { orderNo: "$orderNo" } }
]);
```

returns documents containing only `orderNo`, yet afterward:

```javascript
orders.findOne({ _id: order1Id });
```

still returns the stored document with `_id`, `status`, `shipping`, `items`, etc., unchanged. This is **root replacement in the result stream**, not a durable update.

### 15.2. Aggregation Pipeline Updates Can Alter Stored Documents

MongoDB also supports update pipelines using an allowed subset of stages, including `$replaceRoot`/`$replaceWith`. In that case, the final document emitted by the update pipeline replaces the stored data.

Example **on a test collection only**:

```javascript
orders.updateOne(
  {
    _id: order1Id,
    runId
  },
  [
    {
      $replaceWith: {
        $mergeObjects: [
          "$$ROOT",
          {
            note: "Structure reviewed",
            updatedAt: "$$NOW"
          }
        ]
      }
    }
  ]
);
```

This pipeline uses `$$ROOT` to retain existing fields and appends `note` and `updatedAt`. Because it runs inside `updateOne`, it **modifies the stored document**—completely different from a read-only `aggregate()`. `$$NOW` is a MongoDB-provided timestamp variable, not a literal string.

Precautions for update pipelines:

- `_id` is an immutable document field; never accidentally change or omit `_id` when updating existing documents.
- Schema validation and indexes still apply according to collection write rules.
- Dropping fields during root replacement in an update permanently deletes real data, not just API shape.
- When updating many documents, narrow filters carefully and design safe migrations/retries.
- Never run root-replacing updates against production just to test an aggregation.

### 15.3. When Are `$merge` or `$out` Needed?

If you want to persist transformed aggregation output into a reporting collection or materialized view, use write stages like `$merge` or `$out` with proper permissions and policies. Those stages **differ** from `$replaceRoot`/`$replaceWith`: they dictate where and how output documents are written.

Study the documentation for `$merge`, `$out`, and aggregation updates before running operations with storage side effects. This lesson focuses on transforming the pipeline's **root document**.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `$replaceWith: "$shipping"` when field is missing | Stage errors because no document is produced | `$match` object type or apply a safe fallback |
| `$replaceWith` receives `null`, string, number, array | Not a valid root document | Check `$type`, wrap in an object, or use `$unwind` when needed |
| Promoting `items` array directly to root | Arrays do not auto-expand into documents | `$unwind` first, then replace root or build an object |
| Assuming `_id` is kept automatically | ID is lost from output | Add `_id: "$_id"` or rename to `orderId` |
| Assuming other fields are kept | `status`, `runId`, `items` disappear | Construct target object or use `$mergeObjects` |
| Using `$mergeObjects` without checking operand order | Fields overwritten unintentionally | Determine which operand wins on name collisions |
| Using `$$ROOT` and forgetting to drop nested object | Data duplicated at two levels | `$unset` the unwanted nested field |
| Replacing root with an array field after `$lookup` | Invalid root type | `$unwind` or extract/pick a valid object |
| Grouping by scalar then `$replaceWith:"$_id"` | Scalar is not a document | Wrap scalar in an object |
| `$match` on original field after renaming | Fails to filter properly | Filter beforehand or use the new field name |
| Returning entire customer object after lookup | May expose fields not meant for API | Build explicit object/`$project` |
| Thinking `aggregate()` updated the collection | Stored data remains unchanged | Distinguish shaping stages from write stages/commands |
| Using `$replaceWith` in an update without `_id` | Update may error or strip fields | Keep `_id` and verify fields to preserve |
| Ignoring null/missing data before pipeline | A few bad documents break the entire aggregate | Schema validation, type filtering, or deliberate fallbacks |

## 17. Comprehensive Practice Exercises

### 17.1. Exercise A: Returning Shipping Addresses

Task: produce output with `orderNo`, `recipient`, and `city` for every order, including orders lacking shipping. Hint:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      recipient: {
        $ifNull: ["$shipping.recipient", "Not provided"]
      },
      city: {
        $ifNull: ["$shipping.city", "Unspecified"]
      }
    }
  }
]);
```

Because the new root is constructed as an explicit object, the **root's type** does not depend on whether `shipping` is an object or null. Still, if `shipping` holds unexpected types, field-path resolution and fallbacks must follow business rules.

### 17.2. Exercise B: One Result per Line Item

Task: produce output documents shaped like:

```javascript
{
  orderNo: "ORDER-186-01",
  sku: "BOOK-01",
  quantity: 2,
  unitPrice: 120000,
  lineAmount: 240000
}
```

Sample pipeline:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $unwind: "$items" },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      sku: "$items.sku",
      quantity: "$items.quantity",
      unitPrice: "$items.unitPrice",
      lineAmount: {
        $multiply: [
          "$items.quantity",
          "$items.unitPrice"
        ]
      }
    }
  },
  { $sort: { orderNo: 1, sku: 1 } }
]);
```

Difference from the previous example: `$unwind` can make the output document count **larger or smaller** than the input order count; `$replaceWith` shapes each unwound document.

### 17.3. Exercise C: Promoting Grouping Keys to Root

Task: count orders by status, returning `status` and `count` instead of a nested `_id`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: { status: "$status" },
      count: { $sum: 1 }
    }
  },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$_id",
          { count: "$count" }
        ]
      }
    }
  },
  { $sort: { status: 1 } }
]);
```

### 17.4. Exercise D: Spotting Pipelines That Can Error

Given these expressions:

```javascript
// 1.
{ $replaceWith: "$shipping" }

// 2.
{ $replaceWith: { city: "$shipping.city" } }

// 3.
{ $replaceWith: "$items" }

// 4.
{ $replaceWith: { $ifNull: ["$shipping", {}] } }

// 5.
{ $replaceWith: {
    $cond: [
      { $eq: [{ $type: "$shipping" }, "object"] },
      "$shipping",
      {}
    ]
  }
}
```

Analyze:

1. Which expression can error when `shipping` is missing or null?
2. Which expression creates a new object **regardless of whether shipping is null**?
3. If `shipping` is a string, is expression 4 safe?
4. Why does expression 3 not automatically split an array into multiple documents?
5. When using expression 2, is `_id` kept automatically?

Key takeaway: check the **type of the final root expression**, not just the type of a subfield inside the new document.

## 18. Cleaning Up Practice Data Safely

Before cleaning up, verify the database, collection, `runId`, and IDs created during this session:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);

const ownedOrders = orders.find(
  { runId },
  { _id: 1, runId: 1, orderNo: 1 }
).toArray();

const ownedCustomers = customers.find(
  { runId },
  { _id: 1, runId: 1, displayName: 1 }
).toArray();

printjson(ownedOrders);
printjson(ownedCustomers);
```

If the list matches the data you just created, delete **only those IDs paired with `runId`**:

```javascript
for (const order of ownedOrders) {
  const result = orders.deleteOne({
    _id: order._id,
    runId
  });
  print("order deleted=" + result.deletedCount);
}

for (const customer of ownedCustomers) {
  const result = customers.deleteOne({
    _id: customer._id,
    runId
  });
  print("customer deleted=" + result.deletedCount);
}

print("remaining orders=" + orders.countDocuments({ runId }));
print("remaining customers=" + customers.countDocuments({ runId }));
```

Do not use `deleteMany({})`, `drop()`, or `dropDatabase()` in a database that might be shared with others. If `runId` was lost or preview output looks unexpected, stop to confirm ownership before deleting. Read-only `aggregate()` examples in this lesson do not create stored documents that need cleanup.

## 19. Review Questions

1. What is the root document at an aggregation stage? What does `$$ROOT` represent?
2. Do `$replaceRoot` and `$replaceWith` differ in purpose, or mainly in syntax?
3. Why does `$replaceWith: "$shipping"` fail when `shipping` is `null` or missing?
4. Does `$ifNull` guard against `shipping` being a string? If not, what mechanism is needed?
5. After replacing the root with `shipping`, what happens to `_id` and `status`?
6. How do you retain the source document's `orderId` when promoting shipping info as the root?
7. In what order does `$mergeObjects` resolve two objects that share the same field name?
8. Why can `$replaceWith: "$items"` not replace `$unwind` on an array?
9. After `$lookup`, what must you do if `customer` is an array and you want to make the customer the root document?
10. Why can an object grouping key be promoted to root more directly than a scalar grouping key?
11. When should you use `$project` instead of `$replaceWith`?
12. Why does an `aggregate()` containing only `$replaceWith` leave stored documents untouched, while an `updateOne` with an aggregation pipeline modifies them?
13. Should `$match` be placed before or after `$replaceWith` when filtering on source fields?
14. What risk arises when merging an entire customer object into an order document without controlling output fields?

## 20. Conclusion

`$replaceRoot` and `$replaceWith` are two ways to **replace the entire root document flowing through an aggregation pipeline**. They are useful for promoting nested objects to the top level, turning array elements into documents after `$unwind`, lifting `$group` keys to the root, or building result documents from `$lookup` data.

The root-replacement expression **must evaluate to a document**—never `null`, missing, string, number, or array. When replacing the root, old fields—including `_id`—**are not preserved automatically**; use `$mergeObjects` or construct an object explicitly to retain required fields. Finally, always distinguish **shaping results in `aggregate()`** from **updating real data in an update pipeline**: the same stage behaves differently depending on the execution context.