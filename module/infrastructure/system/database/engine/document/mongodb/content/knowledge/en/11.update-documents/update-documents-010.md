# Updating with Aggregation Pipelines and Allowed Stages in MongoDB

In MongoDB, a standard update command can increment a quantity using `$inc`, assign a value using `$set`, or remove a field using `$unset`. However, some business logic requires **computing new values from currently stored data**: selling price equal to unit price plus shipping fee, stock status derived from quantity, name normalization, enriching array elements, or transforming a legacy document structure.

**Aggregation pipeline updates** let you pass an **array of aggregation stages** as the update argument instead of a document of update operators. MongoDB executes the pipeline against each document matching the filter and writes back the resulting document, subject to update rules and collection validation.

Crucial point: **an update pipeline does not support all aggregation stages**. Only a specific subset of stages designed for **per-document** transformations is permitted.

After this lesson, you will know how to write update pipelines, distinguish the two forms of `$set`/`$unset`, leverage expressions such as `$add`, `$cond`, `$map`, `$filter`, and `$ifNull`, recognize disallowed stages, and choose the right update strategy for production applications.

## 1. From Update Operators to Update Pipelines

Both update forms can produce new values, yet their **syntax and interpretation** differ.

### 1.1. Traditional Update: Argument Is an Object

For example, incrementing `stock` by 2:

~~~javascript
db.products.updateOne(
  { _id: "P-101" },
  { $inc: { stock: 2 } }
);
~~~

The second object contains the **update operator `$inc`**. Familiar update operators include `$set`, `$unset`, `$inc`, `$mul`, `$push`, `$pull`, `$addToSet`, and others.

### 1.2. Update Pipeline: Argument Is an Array

The same goal of incrementing `stock` by 2, expressed using an aggregation expression:

~~~javascript
db.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        stock: { $add: ["$stock", 2] }
      }
    }
  ]
);
~~~

The key syntactic marker is that the second argument is wrapped in **square brackets `[...]`**:

~~~text
updateOne(filter, { updateOperator: ... })    -> traditional update
updateOne(filter, [ { stage: ... }, ... ])     -> update pipeline
~~~

In the pipeline example:

- `$set` is an **aggregation stage**.
- `$add` is an **aggregation expression** inside the `$set` stage.
- `"$stock"` references the **current `stock` field value of the document being updated**.
- `2` is a constant.
- The computed value is written to `stock`; other fields stay unchanged.

Update pipelines have been supported since **MongoDB 4.2**. Running the examples requires a server version and driver/`mongosh` supporting pipeline arrays in update arguments.

### 1.3. An Update Pipeline Is Not a Read-Only `aggregate` Command

Compare:

~~~javascript
// Aggregate: computes results and RETURNS them to client; does not modify source documents.
db.products.aggregate([
  { $set: { inventoryValue: { $multiply: ["$price", "$stock"] } } }
]);

// Pipeline update: computes results and WRITES changes back to source documents.
db.products.updateMany(
  {},
  [
    { $set: { inventoryValue: { $multiply: ["$price", "$stock"] } } }
  ]
);
~~~

Both pipelines can use stages with the same name, yet **`aggregate()`** produces an output cursor whereas **`updateMany()`** persists changes onto the selected documents.

Do not view an update pipeline as "running arbitrary aggregation and saving it back". MongoDB strictly restricts which stages are allowed inside an update command.

## 2. Allowed Stages: The Complete List

For aggregation pipeline updates, MongoDB supports only **six stage names across three functional groups**:

| Stage | Alias | Primary Effect |
| --- | --- | --- |
| **`$set`** | `$addFields` | Adds or recomputes field values while keeping remaining fields |
| **`$addFields`** | `$set` | Equivalent to `$set` |
| **`$unset`** | Exclusionary `$project` | Removes one or more fields |
| **`$project`** | `$unset` when excluding only | Selects/excludes/shapes fields of the resulting document; use cautiously in updates |
| **`$replaceRoot`** | `$replaceWith` | Replaces the entire document with the object produced by `newRoot` |
| **`$replaceWith`** | `$replaceRoot` | Replaces the entire document with the object produced by the expression |

These stages are allowed in `updateOne()`, `updateMany()`, and pipeline-capable update APIs such as `findOneAndUpdate()`.

**Do not use these stages inside an update pipeline**:

| Disallowed Stage in Update Pipeline | Why Is It Disallowed Here? | Appropriate Alternative |
| --- | --- | --- |
| `$match` | Document filtering belongs in the update's **filter argument** | `updateMany({ status: "active" }, [...])` |
| `$sort`, `$limit`, `$skip` | These stages alter document sets/result streams | Use the filter and appropriate API; query separately to select documents before updating |
| `$group`, `$count`, `$sortByCount` | Aggregates across multiple documents rather than transforming each document individually | Run a separate `aggregate()` for reporting/summaries |
| `$lookup`, `$graphLookup`, `$unionWith` | Joins/combines data from other collections | Design a separate read/compute flow and update afterward per business rules |
| `$unwind` | Can produce multiple output documents from one input document | Use array expressions `$map`, `$filter` inside `$set` |
| `$out`, `$merge` | Stages that write aggregation output to collections | Use with `aggregate()` when materializing results |
| `$facet`, `$bucket`, `$sample` | Operates on document streams or multiple branches | Keep outside update pipelines |

**Do not confuse stages with expressions.** For example, `$group` **cannot** be used as a stage in an update, whereas the `$sum` expression summing numeric elements of **an array within the same document** can appear inside `$set`. Similarly, `$map` and `$filter` are **expressions**, not stages of an update pipeline.

To filter target documents, place conditions in the **filter** argument:

~~~javascript
// CORRECT: filter goes outside the pipeline array.
db.products.updateMany(
  { status: "active", stock: { $gt: 0 } },
  [
    { $set: { available: true } }
  ]
);

// WRONG: $match is not allowed as an update pipeline stage.
db.products.updateMany(
  {},
  [
    { $match: { status: "active" } },
    { $set: { available: true } }
  ]
);
~~~

In the second example, MongoDB rejects the command because `$match` is not an allowed update pipeline stage. With a proper filter, MongoDB evaluates the pipeline only on documents selected by that filter.

## 3. Preparing Data in mongosh

Use a dedicated database so you can test updates without affecting other data. Monetary values are stored as **Decimal128** to demonstrate decimal arithmetic. Run in `mongosh`:

~~~javascript
const lab = db.getSiblingDB("mongo_update_pipeline_lab");

lab.products.drop();

lab.products.insertMany([
  {
    _id: "P-101",
    sku: "MOUSE-01",
    name: "  Wireless Mouse  ",
    category: "accessory",
    status: "active",
    price: Decimal128("150.00"),
    shippingFee: Decimal128("15.00"),
    stock: 5,
    tags: ["tech", "sale"],
    items: [
      { code: "USB", qty: 2, unitPrice: Decimal128("10.00") },
      { code: "PAD", qty: 1, unitPrice: Decimal128("25.00") }
    ],
    legacyCode: "OLD-M01"
  },
  {
    _id: "P-102",
    sku: "KEY-02",
    name: "Mechanical Keyboard",
    category: "accessory",
    status: "draft",
    price: Decimal128("500.00"),
    shippingFee: Decimal128("30.00"),
    stock: 0,
    tags: ["office"],
    items: [
      { code: "KEYCAP", qty: 0, unitPrice: Decimal128("50.00") }
    ]
  },
  {
    _id: "P-103",
    sku: "BOOK-03",
    name: "MongoDB Guide",
    category: "book",
    status: "active",
    price: Decimal128("80.00"),
    shippingFee: Decimal128("10.00"),
    stock: 12,
    tags: ["learning"],
    items: []
  }
]);

lab.products.find().sort({ _id: 1 });
~~~

In the following sections, each example **modifies actual data in the lab database**. To reproduce results from the initial state, re-run the setup block after confirming you want to wipe the practice collection with `drop()`. Never run that drop block against a collection holding data you need to keep.

## 4. $set and $addFields: Computing Values from the Document Itself

`$set` and `$addFields` are aliases for the same **aggregation stage**. The stage preserves existing fields while adding new fields or **overwriting fields of the same name** with computed expressions.

### 4.1. Computing Inventory Value

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        inventoryValue: { $multiply: ["$price", "$stock"] },
        shippingIncluded: { $add: ["$price", "$shippingFee"] },
        updatedAt: "$$NOW"
      }
    }
  ]
);

lab.products.findOne(
  { _id: "P-101" },
  { sku: 1, inventoryValue: 1, shippingIncluded: 1, updatedAt: 1 }
);
~~~

For the initial `P-101`:

- `inventoryValue = 150.00 × 5 = 750.00`.
- `shippingIncluded = 150.00 + 15.00 = 165.00`.
- `updatedAt` is the server timestamp recorded via the system variable `$$NOW`.

`$$NOW` provides a consistent timestamp throughout the pipeline execution of the command. `"$price"` reads the value from the current document, while `Decimal128` preserves decimal representation for supported operations within Decimal128 limits.

### 4.2. Conditional Computation with $cond

Suppose you want to derive an `availability` field from `stock`:

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        availability: {
          $cond: [
            { $gt: ["$stock", 0] },
            "in_stock",
            "out_of_stock"
          ]
        }
      }
    }
  ]
);

lab.products.find(
  {},
  { _id: 1, stock: 1, availability: 1 }
).sort({ _id: 1 });
~~~

Logical result:

| Product | Initial `stock` | `availability` |
| --- | ---: | --- |
| P-101 | 5 | `in_stock` |
| P-102 | 0 | `out_of_stock` |
| P-103 | 12 | `in_stock` |

Use `$switch` for multiple branches, such as zero stock, low stock, and healthy stock:

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        stockStatus: {
          $switch: {
            branches: [
              {
                case: { $lte: ["$stock", 0] },
                then: "out_of_stock"
              },
              {
                case: { $lt: ["$stock", 5] },
                then: "low_stock"
              }
            ],
            default: "in_stock"
          }
        }
      }
    }
  ]
);
~~~

Branch order in `$switch` matters: MongoDB picks the first branch whose `case` evaluates to true.

### 4.3. Normalizing a Field from Its Existing Value

`P-101`'s name has leading and trailing spaces. Use `$trim` to update it:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        name: { $trim: { input: "$name" } }
      }
    }
  ]
);

lab.products.findOne({ _id: "P-101" }, { name: 1 });
~~~

The stored name after updating is `"Wireless Mouse"`. In a traditional update, `{ $set: { name: "$name" } }` passes a literal string to the update operator rather than normalizing anything. A pipeline interprets `"$name"` as a field reference and allows nesting expressions such as `$trim`.

### 4.4. $ifNull for Conditional Default Values

When a field might be missing or `null`, use `$ifNull`:

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        tags: { $ifNull: ["$tags", []] },
        shippingFee: {
          $ifNull: ["$shippingFee", Decimal128("0.00")]
        }
      }
    }
  ]
);
~~~

`$ifNull` returns the fallback value when the input expression evaluates to `null` or is missing. This is a clean way to **backfill** missing values when all targeted documents need standard types.

**Caution:** `$ifNull` does not repair fields that exist with the wrong type (for instance, `tags` stored as a string instead of an array). With heterogeneous legacy data, check types using `$type` or normalize beforehand to avoid errors in subsequent expressions.

## 5. Sequential Stages: One Stage's Output Feeds the Next

An update pipeline can contain multiple stages:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        normalizedName: { $trim: { input: "$name" } }
      }
    },
    {
      $set: {
        displayName: {
          $concat: ["$normalizedName", " (", "$sku", ")"]
        }
      }
    },
    {
      $unset: "normalizedName"
    }
  ]
);

lab.products.findOne(
  { _id: "P-101" },
  { name: 1, displayName: 1, normalizedName: 1 }
);
~~~

The result has `displayName: "Wireless Mouse (MOUSE-01)"`, with no leftover temporary `normalizedName` field.

Stages execute **in array order**, so the second stage can read the field produced by the first stage. Inside a **single `$set` stage**, never assume assignments run strictly top-to-bottom so a later expression can read a field just assigned earlier in the same stage. When dependencies exist, split them into sequential stages as shown above.

Compared with traditional updates: traditional operators mutate fields, yet **cannot chain a sequence of expression stages** in this manner.

## 6. $unset and $project: Removing or Selecting Fields

### 6.1. The $unset Stage Removes Specified Fields

To delete an old field:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $unset: "legacyCode" }
  ]
);
~~~

To delete multiple fields at once:

~~~javascript
lab.products.updateMany(
  {},
  [
    { $unset: ["obsoleteField", "temporaryNote"] }
  ]
);
~~~

If a field is absent, removing it simply produces no change. The updated document must still satisfy all remaining collection constraints.

Distinguish clearly:

~~~javascript
// $unset as an UPDATE OPERATOR: update argument is an object.
lab.products.updateOne(
  { _id: "P-101" },
  { $unset: { legacyCode: "" } }
);

// $unset as an AGGREGATION STAGE: update argument is an array.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $unset: "legacyCode" }
  ]
);
~~~

Both commands remove the field, yet **you must not mix syntax** between the two contexts.

### 6.2. $project in Updates Can Drop Many Fields at Once

The `$project` stage normally selects fields in an aggregation. When placed inside an **update pipeline**, the document output by `$project` becomes **the document written to disk**. Consequently, any unretained fields are deleted from the database.

Example of a controlled "migrate document to a new schema" operation:

~~~javascript
// USE ONLY WHEN YOU INTEND TO DROP EVERY OTHER FIELD NOT LISTED.
lab.products.updateOne(
  { _id: "P-103" },
  [
    {
      $project: {
        _id: 1,
        sku: 1,
        name: 1,
        category: 1,
        status: 1,
        price: 1,
        stock: 1,
        tags: 1
      }
    }
  ]
);
~~~

After this update, `shippingFee`, `items`, and any other fields omitted from the list vanish from `P-103`. In actively evolving applications, an incomplete `$project` allowlist can accidentally cause data loss.

If you only want to delete a few legacy fields, **prefer `$unset`** over `$project` with a long allowlist of kept fields.

### 6.3. Never Delete or Change _id

`_id` is the immutable identifier of a document. An update pipeline cannot turn an existing document into one with a different `_id` or missing `_id`. Be careful with `$project`, `$replaceWith`, and `$replaceRoot`: although read-only aggregations can reshape `_id` freely, **persisting that output via an update must still obey `_id` immutability**.

Example to avoid:

~~~javascript
// Invalid when updating a document that already has an _id.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $set: { _id: "P-999" } }
  ]
);
~~~

The operation is rejected because it attempts to alter the stored document's identifier. Other constraints such as schema validation and shard keys (on sharded collections) also apply per deployment configuration.

## 7. $replaceRoot and $replaceWith: Rebuilding the Document

These two stages replace the **entire root object** with a new document computed by an expression.

Syntax:

~~~javascript
// $replaceRoot takes an object containing newRoot.
{ $replaceRoot: { newRoot: <documentExpression> } }

// $replaceWith takes the expression producing the document directly.
{ $replaceWith: <documentExpression> }
~~~

Inside an update pipeline, both stages are virtually identical in capability. Because the output is persisted back, **preserve `_id`** and all required business fields.

### 7.1. Using $replaceWith Combined with $mergeObjects

Suppose you want to attach an `audit` object to a product while keeping all other fields intact:

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $replaceWith: {
        $mergeObjects: [
          "$$ROOT",
          {
            audit: {
              source: "pipeline-lab",
              changedAt: "$$NOW"
            }
          }
        ]
      }
    }
  ]
);

lab.products.findOne(
  { _id: "P-102" },
  { _id: 1, sku: 1, audit: 1 }
);
~~~

Here:

- `$$ROOT` is the current document.
- `$mergeObjects` merges objects left-to-right; later objects overwrite same-named fields from earlier objects.
- `_id` resides inside `$$ROOT`, so it is preserved.
- The new `audit` replaces any prior `audit` object if one existed.

To **preserve existing subfields inside `audit`**, merge `audit` itself instead of overwriting the whole object:

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $replaceWith: {
        $mergeObjects: [
          "$$ROOT",
          {
            audit: {
              $mergeObjects: [
                { source: "unknown" },
                "$audit",
                { changedAt: "$$NOW" }
              ]
            }
          }
        ]
      }
    }
  ]
);
~~~

Any existing `source` inside `audit` is preserved because `"$audit"` follows the default object, while `changedAt` is updated. If `audit` is completely missing, `$mergeObjects` ignores missing/null operands and uses the default object.

### 7.2. Equivalent $replaceRoot Syntax

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $replaceRoot: {
        newRoot: {
          $mergeObjects: [
            "$$ROOT",
            { reviewFlag: true }
          ]
        }
      }
    }
  ]
);
~~~

The result keeps existing data and adds `reviewFlag`. For updates merely adding or changing a few fields, `$set` is simpler. `$replaceRoot`/`$replaceWith` suit complex structural transformations, though they also carry higher risk of dropping fields if `$$ROOT` is omitted or properties are missed.

### 7.3. Mandatory Requirements for Replacement

The expression in `$replaceWith` must evaluate to a **document/object**, not a string, number, or array. Returning `"$name"` (a string) is not a valid replacement document.

Beyond `_id` immutability, the result must satisfy collection **schema validation**, BSON document size limits, and deployment constraints. Always test on sample data before running wide updates.

## 8. Aggregation Expressions Available Inside Update Stages

Allowed stages are merely the **pipeline wrapper**. Inside stages like `$set`, MongoDB supports many **aggregation expressions** to compute field values.

| Need | Common Expressions | Target Example |
| --- | --- | --- |
| Add/subtract/multiply/divide | `$add`, `$subtract`, `$multiply`, `$divide` | Compute totals, deduct stock, scale prices |
| Comparison/logic | `$eq`, `$gt`, `$lt`, `$and`, `$or` | Derive status flags |
| Conditionals | `$cond`, `$switch` | Pick branch from current data |
| Missing/typed data | `$ifNull`, `$type` | Supply defaults, inspect types |
| Strings | `$concat`, `$trim`, `$toUpper`, `$toLower` | Normalize names and codes |
| Dates/times | `$$NOW`, `$dateAdd`, `$dateDiff` | Update timestamps or expiration deadlines |
| Arrays | `$map`, `$filter`, `$concatArrays`, `$setUnion`, `$size` | Transform and append elements |
| Objects | `$mergeObjects`, `$getField`, `$setField` | Merge/read/write fields |
| Type conversion | `$toInt`, `$toDecimal`, `$convert` | Normalize legacy data |

**Do not confuse same-named operators in different roles.** For example, `$and` inside a filter is a **query operator**; inside `$cond`, `$and` is an **aggregation expression** accepting an array of boolean expressions. Likewise, the `$set` pipeline stage differs from the `$set` update operator outside a pipeline.

### 8.1. Adding Based on Current Field Value

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        stock: { $add: ["$stock", 3] }
      }
    }
  ]
);
~~~

If `stock` started at 5, it becomes 8. Re-running increments by 3 again because the expression reads the current document's value. This operation is **not idempotent**; manage retries according to business semantics.

### 8.2. Rounding Money and Preserving Decimal Types

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        priceWithTax: {
          $round: [
            {
              $multiply: [
                "$price",
                Decimal128("1.08")
              ]
            },
            2
          ]
        }
      }
    }
  ]
);
~~~

Starting from `150.00` and multiplier `1.08`, the result is **162.00**. Passing the factor as `Decimal128("1.08")` keeps arithmetic in decimal precision within Decimal128 limits. Applications must still define explicit rounding rules and decimal precision per financial requirements.

### 8.3. Escaping Literal Strings Starting with $

Inside aggregation expressions, strings beginning with `$` are treated as **field references** or system variables. To store the literal string `"$VIP-2026"`, use `$literal`:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        campaignCode: { $literal: "$VIP-2026" }
      }
    }
  ]
);
~~~

Writing `campaignCode: "$VIP-2026"` causes MongoDB to interpret it as a field path rather than the intended literal string. This is especially important when values come from user input or external systems.

### 8.4. Using $convert When Legacy Data Has Mixed Types

Suppose a legacy collection stored `stock` as strings; you can convert them to integers:

~~~javascript
// Standalone illustration for legacy documents having stock = "12".
db.legacy_products.updateMany(
  { stock: { $type: "string" } },
  [
    {
      $set: {
        stock: {
          $convert: {
            input: "$stock",
            to: "int",
            onError: 0,
            onNull: 0
          }
        }
      }
    }
  ]
);
~~~

This example targets a hypothetical `legacy_products` collection not created in `lab.products`. Think carefully before setting `onError: 0`: malformed values silently become `0`, masking dirty data. In production, it is usually better to **flag invalid records for investigation** before deciding fallback values.

## 9. Updating Arrays Using $map, $filter, and $concatArrays

Aggregation pipeline updates do not accept traditional `arrayFilters`. When processing array elements in a pipeline, use **array expressions** inside an allowed stage.

### 9.1. Computing Values per Element with $map

Product `P-101` has an `items` array of `{code, qty, unitPrice}` objects. To add `lineTotal = qty × unitPrice` to **each** element:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        items: {
          $map: {
            input: { $ifNull: ["$items", []] },
            as: "item",
            in: {
              $mergeObjects: [
                "$$item",
                {
                  lineTotal: {
                    $multiply: [
                      "$$item.qty",
                      "$$item.unitPrice"
                    ]
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
);
~~~

The first element becomes:

~~~javascript
{
  code: "USB",
  qty: 2,
  unitPrice: Decimal128("10.00"),
  lineTotal: Decimal128("20.00")
}
~~~

`$map` builds a new array from transformed elements, while `$mergeObjects` preserves existing fields and adds `lineTotal`. If `items` is missing or null, `$ifNull` supplies an empty array to prevent errors. If `items` exists as a string, normalize/validate types first.

### 9.2. Dropping Invalid Elements with $filter

On `P-102`, `items` contains an element with `qty: 0`. To keep only elements with quantity greater than 0:

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $set: {
        items: {
          $filter: {
            input: { $ifNull: ["$items", []] },
            as: "item",
            cond: { $gt: ["$$item.qty", 0] }
          }
        }
      }
    }
  ]
);

lab.products.findOne({ _id: "P-102" }, { items: 1 });
~~~

`P-102`'s `items` becomes `[]`. `$filter` **retains elements matching the condition**, omitting all others from the persisted array.

### 9.3. Appending Elements with $concatArrays

To append a new tag to the end of an array:

~~~javascript
lab.products.updateOne(
  { _id: "P-103" },
  [
    {
      $set: {
        tags: {
          $concatArrays: [
            { $ifNull: ["$tags", []] },
            ["featured"]
          ]
        }
      }
    }
  ]
);
~~~

`$concatArrays` concatenates arrays in order; running it repeatedly appends `"featured"` multiple times. To **avoid duplicates**, use `$setUnion`:

~~~javascript
lab.products.updateOne(
  { _id: "P-103" },
  [
    {
      $set: {
        tags: {
          $setUnion: [
            { $ifNull: ["$tags", []] },
            ["featured"]
          ]
        }
      }
    }
  ]
);
~~~

`$setUnion` produces a deduplicated set, **without guaranteeing preserved array order**. Choose based on business rules: ordered history differs from unique tag sets.

### 9.4. Why Not $[identifier] with arrayFilters?

Traditional syntax for filtered array updates is:

~~~javascript
// This is a TRADITIONAL UPDATE, not an aggregation pipeline.
db.orders.updateMany(
  {},
  { $set: { "items.$[item].reviewed": true } },
  { arrayFilters: [{ "item.qty": { $gt: 0 } }] }
);
~~~

However, `arrayFilters` **cannot be used** when the second argument is an **aggregation pipeline**. In pipelines, express array transformations with `$map`, `$filter`, or other expressions rather than attaching `arrayFilters`.

Both mechanisms have distinct strengths:

- **Update operators + `arrayFilters`:** convenient when updating a few fields on qualifying elements.
- **Pipeline + `$map`/`$filter`:** convenient when computing values, restructuring elements, or combining multiple expressions per element.

Do not switch to a pipeline just to "look modern" if a simple update operator already expresses the business requirement cleanly.

## 10. Filtering Safely and Writing Safe Pipelines

### 10.1. The Update Filter Is the Document Selection Guard

Problem: deduct 2 units from inventory **only when at least 2 remain**. Place the condition directly in the filter:

~~~javascript
const result = lab.products.updateOne(
  {
    _id: "P-101",
    stock: { $gte: 2 }
  },
  [
    {
      $set: {
        stock: { $subtract: ["$stock", 2] },
        updatedAt: "$$NOW"
      }
    }
  ]
);

printjson(result);
~~~

The filter and update on that document execute atomically within **that single document**. If stock is insufficient when applied, the filter fails to match and nothing changes. Inspect `matchedCount` to distinguish qualifying from insufficient stock.

Avoid writing only:

~~~javascript
// Can easily push stock negative without a guard in the filter.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $set: { stock: { $subtract: ["$stock", 2] } } }
  ]
);
~~~

A schema validator can block negative stock, yet expressing the guard in the filter clearly states the **business invariant of a stock deduction**.

### 10.2. Avoiding Whole-Collection Impact from Broad Filters

`updateMany({}, pipeline)` targets every document in the collection. Be especially careful if stages use `$project`, `$unset`, or `$replaceWith`, as they can drop fields across the entire dataset.

Before a large update, inspect the filter scope:

~~~javascript
const targetFilter = {
  status: "draft",
  category: "accessory"
};

lab.products.find(
  targetFilter,
  { _id: 1, sku: 1, status: 1, category: 1 }
);

lab.products.countDocuments(targetFilter);
~~~

Only after confirming the scope, apply the pipeline:

~~~javascript
lab.products.updateMany(
  targetFilter,
  [
    {
      $set: {
        needsReview: true,
        reviewedAt: "$$NOW"
      }
    }
  ]
);
~~~

Pre-checking scope is helpful, though under concurrent writers data can still change between the read and write. Never treat a prior `find()` as a lock or transaction.

### 10.3. Atomicity Differences Between updateOne and updateMany

- `updateOne` updates at most one matching document.
- `updateMany` can update many documents, **without turning the entire command into a multi-document atomic transaction**.
- Each individual document modification is atomic at the document level. If multiple documents must succeed or fail together, use a **multi-document transaction** on a supported deployment alongside an appropriate retry strategy.

Complex pipelines or huge arrays also increase per-document processing time. You cannot put `$group` inside an update pipeline to turn it into a collection-wide aggregate transaction.

## 11. Upsert with Update Pipelines

`upsert: true` means if no document matches the filter, MongoDB **creates a new document** and applies the pipeline.

Example creating a new product if absent:

~~~javascript
lab.products.updateOne(
  { _id: "P-NEW" },
  [
    {
      $set: {
        sku: "NEW-001",
        name: "New Product",
        category: "accessory",
        status: "draft",
        stock: 0,
        price: Decimal128("0.00"),
        tags: [],
        createdAt: "$$NOW",
        updatedAt: "$$NOW"
      }
    }
  ],
  { upsert: true }
);
~~~

With `_id` in the filter as above, the inserted document gets `_id: "P-NEW"`. Re-running **updates** the existing document instead of inserting a second one.

**Caution:** in the snippet above, re-running overwrites `createdAt` because the pipeline sets it unconditionally. When `createdAt` should be set only on initial creation, use `$ifNull` to preserve existing values:

~~~javascript
lab.products.updateOne(
  { _id: "P-NEW" },
  [
    {
      $set: {
        sku: "NEW-001",
        createdAt: { $ifNull: ["$createdAt", "$$NOW"] },
        updatedAt: "$$NOW"
      }
    }
  ],
  { upsert: true }
);
~~~

Filter by a unique key—typically `_id` or a field backed by a **unique index**—to reduce the risk of concurrent upserts creating logically duplicate records.

If a pipeline computes from a field present only on existing documents, define explicit defaults for newly upserted documents. For instance, `{$add: ["$stock", 1]}` is unsafe when `stock` is missing; use `{$add: [{$ifNull: ["$stock", 0]}, 1]}` instead.

## 12. Distinguishing Pipeline Expressions from Update Operators

This is a frequent source of confusion when adopting aggregation pipeline updates.

| Goal | Traditional Update Operators | Update Pipeline (Stages/Expressions) |
| --- | --- | --- |
| Assign a constant to a field | `{ $set: { status: "active" } }` | `[ { $set: { status: "active" } } ]` |
| Increment stock by 2 | `{ $inc: { stock: 2 } }` | `[ { $set: { stock: { $add: ["$stock", 2] } } } ]` |
| Remove legacy field | `{ $unset: { legacy: "" } }` | `[ { $unset: "legacy" } ]` |
| Append element to array | `{ $push: { tags: "new" } }` | `[ { $set: { tags: { $concatArrays: ["$tags", ["new"]] } } } ]` |
| Keep only array elements matching condition | `$pull` to drop elements by condition | `$filter` inside `$set` to construct new array |
| Update elements via `arrayFilters` | Supported with `$[identifier]` and options | `arrayFilters` unsupported; use `$map` |
| Compute value from other fields | Requires custom approach, often multi-step or app logic | `$set` stage with `$add`/`$multiply`/`$concat`/`$cond` |

You cannot use the `$inc` update operator as a pipeline stage:

~~~javascript
// WRONG: $inc is not an allowed aggregation stage in an update pipeline.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $inc: { stock: 1 } }
  ]
);

// CORRECT: recompute stock using an aggregation expression.
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        stock: { $add: ["$stock", 1] }
      }
    }
  ]
);
~~~

Nor should you confuse the **`$set` stage** with the **`$set` update operator**:

~~~javascript
// Update operator: the string "$name" is the literal VALUE assigned under
// traditional update semantics.
{ $set: { displayName: "$name" } }

// Aggregation stage: "$name" is a REFERENCE to the current name field.
[ { $set: { displayName: "$name" } } ]
~~~

Simply checking **`{...}` vs. `[{...}]`** in the update argument tells you which semantics MongoDB applies.

## 13. Notes on Schema, Data Types, and Performance

### 13.1. Validation Still Applies After Updating

If a collection has a JSON Schema validator, the output of an update pipeline must still satisfy constraints such as:

- Required fields (`required`).
- BSON types (`bsonType`).
- Allowed values (`enum`).
- Numeric bounds (`minimum`/`maximum`).
- String rules (`minLength`/`pattern`).

For example, `$project` accidentally dropping a required field causes the update to be rejected when `validationLevel: "strict"` and `validationAction: "error"`. Validators do not auto-correct pipelines.

### 13.2. Computations Can Error on Missing or Mismatched Types

Suppose `stock` is occasionally stored as the string `"5"` instead of a number. The expression:

~~~javascript
{ $add: ["$stock", 1] }
~~~

errors because operands have incompatible types. Never assume update pipelines coerce arbitrary types to numbers automatically.

You can use `$convert`, `$toInt`, or `$ifNull` for specific cases, while enforcing a consistent policy for malformed input. Avoid silently turning corrupt data into `0` if doing so distorts inventory or financial balances.

### 13.3. Preserve _id and Respect Document Limits

- An existing document's `_id` cannot be changed via `$set` or replacement stages.
- Resulting documents must remain within the maximum BSON size and system limits.
- On sharded collections, shard key modifications follow strict rules; pipeline updates do not bypass them.
- Write privileges, write concern, and transaction semantics still apply.

### 13.4. Index Impact and Processing Cost

Indexes primarily help MongoDB **locate target documents** matching the filter:

~~~javascript
lab.products.createIndex({
  status: 1,
  category: 1
});
~~~

If you frequently run:

~~~javascript
lab.products.updateMany(
  { status: "active", category: "accessory" },
  [
    {
      $set: {
        inventoryValue: { $multiply: ["$price", "$stock"] }
      }
    }
  ]
);
~~~

a compound index on `status` and `category` helps select matching documents, depending on data distribution and the query planner. Once located, `$multiply` still executes for each matched document. Updating indexed fields also adds index maintenance overhead.

If a pipeline runs `$map` over a very large array, cost scales with the number of elements processed. A MongoDB update pipeline **does not store array deltas incrementally**: it writes the recomputed value back to the document.

### 13.5. Idempotency and Retries

A pipeline like:

~~~javascript
[
  { $set: { normalizedName: { $trim: { input: "$name" } } } }
]
~~~

is typically **idempotent**: re-running on the same data makes no further change once normalized.

Conversely:

~~~javascript
[
  { $set: { stock: { $add: ["$stock", 1] } } }
]
~~~

adds 1 on every execution. When network timeouts occur, applications must distinguish driver retryable writes from resending business requests. **Never blindly repeat an increment/decrement update** without knowing whether the prior attempt committed. Financial or inventory workflows generally require idempotency keys or safer update strategies.

## 14. Common Errors and Resolutions

| Error / Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Stage `$match`, `$group`, or `$lookup` reported invalid | Update pipelines allow only six stage names | Move filtering to the filter argument; move multi-doc aggregation to `aggregate()` |
| Stage `$inc`/`$push` rejected | Those are update operators, not aggregation stages | Use traditional updates or write `$add`/`$concatArrays` inside `$set` |
| Literal string `"$price"` stored unexpectedly | Confused traditional update vs. pipeline semantics | Use a pipeline when referencing current document fields |
| String `"$VIP"` treated as a field path | Literal value starts with `$` | Wrap with `{$literal: "$VIP"}` |
| `$add` errors on missing/string field | Incompatible operand types | Check BSON types, use `$ifNull` or `$convert` |
| `$project` drops many fields | Stage retains only explicitly listed fields | Use `$unset` when removing only a few fields |
| `$replaceWith` errors | Expression does not yield an object or violates update rules | Ensure valid object preserving `_id` and required fields |
| Cannot combine `arrayFilters` with pipeline | The two update forms cannot be mixed | Choose update operators + `arrayFilters` OR pipeline + `$map` |
| Array update produces duplicate elements | `$concatArrays` appends on every run | Use `$setUnion` if uniqueness is required, noting order |
| Upsert overwrites `createdAt` | Pipeline assigns `$$NOW` unconditionally | Use `$ifNull` or write-once initialization patterns |
| `matchedCount = 0` | No document matched the filter at update time | Verify conditions, data types, and current state |
| `modifiedCount = 0` with `matchedCount > 0` | Document matched but produced no actual change | Compare before/after values and pipeline logic |
| `updateMany` partially applied on error | No automatic multi-document atomicity | Design transactions or recovery mechanisms when needed |
| Slow command | Unindexed filter, heavy expressions/arrays, large document count | Optimize filters/indexes, narrow scope, check profiler/metrics |

Never rewrite a whole pipeline blindly when debugging errors. First check **whether the update argument is an object or an array**, **whether every stage is on the allowed list**, **whether expressions read the right fields/BSON types**, and **whether the output violates validation**.

## 15. Practice Exercises and Expected Results

These exercises assume you have re-initialized `lab.products` from section 3 if earlier updates ran. Write the commands yourself and read back documents afterward.

### Exercise 1 — Computing a New Field

Create `totalPrice` equal to `price + shippingFee` for all products.

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        totalPrice: { $add: ["$price", "$shippingFee"] }
      }
    }
  ]
);
~~~

Expected result from initial data:

| `_id` | Price | Shipping Fee | `totalPrice` |
| --- | ---: | ---: | ---: |
| P-101 | 150.00 | 15.00 | 165.00 |
| P-102 | 500.00 | 30.00 | 530.00 |
| P-103 | 80.00 | 10.00 | 90.00 |

### Exercise 2 — Adding and Dropping a Temporary Field

Create `temporaryLabel` from `sku`, derive `displayCode` in the next stage, and remove the temporary field.

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        temporaryLabel: { $concat: ["CODE-", "$sku"] }
      }
    },
    {
      $set: {
        displayCode: "$temporaryLabel"
      }
    },
    {
      $unset: "temporaryLabel"
    }
  ]
);
~~~

Result: `displayCode` is `"CODE-MOUSE-01"`, and `temporaryLabel` does not exist.

### Exercise 3 — Conditional Update

Apply only to `active` products, setting `canSell` based on `stock > 0`:

~~~javascript
lab.products.updateMany(
  { status: "active" },
  [
    {
      $set: {
        canSell: { $gt: ["$stock", 0] }
      }
    }
  ]
);
~~~

From initial data, `P-101` and `P-103` get `canSell: true`. `P-102` stays untouched because its status is `draft`.

### Exercise 4 — Transforming Array Elements

Add `lineTotal` to every item using `$map` and `$multiply`, keeping existing fields of each item. Run on `P-101` and compare the two elements:

- `USB` has `qty: 2`, `unitPrice: 10.00`, giving `lineTotal: 20.00`.
- `PAD` has `qty: 1`, `unitPrice: 25.00`, giving `lineTotal: 25.00`.

Hint: review section 9.1 on `$map` with `$mergeObjects`.

### Exercise 5 — Identifying Disallowed Stages

Review this snippet:

~~~javascript
lab.products.updateMany(
  {},
  [
    { $match: { stock: { $gt: 0 } } },
    { $set: { available: true } },
    { $sort: { stock: -1 } }
  ]
);
~~~

Rewrite it to **update only products with `stock > 0`**, without placing `$match` and `$sort` as update stages. One solution:

~~~javascript
lab.products.updateMany(
  { stock: { $gt: 0 } },
  [
    { $set: { available: true } }
  ]
);
~~~

Sort order has no effect on bulk-updating documents in this task.

### Exercise 6 — Choosing Between Traditional Updates and Pipelines

For each requirement, pick the cleanest and most accurate approach:

1. Increment `stock` by 1.
2. Compute `inventoryValue` as `price × stock`.
3. Remove a specific tag from an array.
4. Normalize `name` with `$trim`.
5. Transform each `items` element to include `lineTotal`.
6. Set a regular field to the constant `"active"`.

Hint: (1), (3), and (6) map naturally to traditional update operators; (2), (4), and (5) highlight where pipelines shine. For (3), if removal requires complex expressions, `$filter` is also an option.

### Exercise 7 — Distinguishing Update Pipelines from Read Aggregations

Compare two commands:

~~~javascript
// Command A
lab.products.aggregate([
  { $group: { _id: "$category", totalStock: { $sum: "$stock" } } }
]);

// Command B (invalid)
lab.products.updateMany(
  {},
  [
    { $group: { _id: "$category", totalStock: { $sum: "$stock" } } }
  ]
);
~~~

Explain why Command A runs as an aggregation whereas Command B is rejected in an update pipeline. If the goal is storing a total-stock report per category, build a dedicated aggregate/materialization flow rather than `updateMany()` with `$group`.

## 16. Summary of Key Principles

**Aggregation pipeline updates** let you compute updated values from the current document and chain transformation stages sequentially. They excel at conditional updates, field normalization, array transformations, and document restructuring.

Key principles to retain:

1. When the update argument is an **array `[...]`**, MongoDB treats it as a **pipeline**.
2. Only six stage names are permitted: **`$set`, `$addFields`, `$unset`, `$project`, `$replaceRoot`, `$replaceWith`**.
3. Expressions such as **`$add`, `$cond`, `$trim`, `$map`, `$filter`, `$mergeObjects`** belong **inside** allowed stages; they are not standalone stages.
4. Document selection belongs in the **filter**; never put `$match` inside an update pipeline.
5. Pipeline `$set` and `$unset` are **aggregation stages**, distinct from update operators of the same names.
6. When using `$project` or replacement stages, guard against **dropped fields, `_id` immutability errors, and schema validation failures**.
7. `arrayFilters` cannot combine with update pipelines; transform arrays with `$map`/`$filter` or use traditional updates when appropriate.
8. Single-document updates are atomic, whereas `updateMany()` is not automatically a multi-document atomic transaction.
9. Use proper filters, indexes, and result inspection to verify scope; design retries/idempotency carefully for increment or decrement operations.

### Official MongoDB Documentation

- [Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/) — syntax, allowed stages, `$literal`, and update examples.
- [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateone/) — filter, update pipeline, upsert, writeConcern, and result semantics.
- [db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updatemany/) — multi-document updates and atomicity.
- [$set (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/set/) — adding/overwriting fields with expressions.
- [$project (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) — reshaping document fields.
- [$replaceWith (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/replaceWith/) — replacing the entire root object.
- [$map (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/) and [$filter (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — computing over array elements.
- [MongoDB Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — update atomicity and multi-document transactions.
