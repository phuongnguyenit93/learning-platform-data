# Updating Arrays with $, $[], and $[identifier] Combined with arrayFilters in MongoDB

## 1. Problem Statement: Modifying the Right Array Elements of a Document

A **MongoDB document** can contain multiple arrays, including arrays of scalar values and arrays of embedded documents. For example, an order stores line items inside an **items** field:

~~~javascript
{
  _id: "ORD-101",
  customerId: "CUS-01",
  status: "OPEN",
  items: [
    { sku: "PEN-BLUE", qty: 2, state: "NEW" },
    { sku: "NOTE-A5", qty: 1, state: "NEW" },
    { sku: "PEN-BLUE", qty: 5, state: "NEW" }
  ]
}
~~~

An application may need to:

1. Mark **the first line item with sku = PEN-BLUE** as packed.
2. Attach an attribute to **all line items**.
3. Change the status of **every line item with qty >= 3 and state = NEW**.
4. Within each line item, modify **elements of a nested array** according to a separate condition.

If you fetch the entire document into Java, edit the list in RAM, and overwrite the whole array, the application risks **lost updates** when concurrent requests modify the same order. MongoDB provides **positional update operators** to identify target elements directly inside the update path:

| Operator | Common Name | Meaning |
|---|---|---|
| **$** | Positional operator | Updates **the first element matching** the array query condition. |
| **$[]** | All positional operator | Updates **all elements** in the specified array. |
| **$[identifier]** | Filtered positional operator | Updates **all elements matching** the corresponding **arrayFilters** predicate. |

The three operators have completely different scopes. **$** is not a universal wildcard for all elements, **$[]** does not evaluate per-element filters on its own, and **$[identifier]** is invalid without a filter for that identifier.

~~~text
                      MongoDB document
                             |
                         items: [...]
                             |
              +--------------+--------------+
              |              |              |
         items.$         items.$[]      items.$[line]
              |              |              |
       First match         All       Every element
       by query         elements   matching arrayFilters
              |              |              |
           Query         No element   Query selects doc
      locates position   filter       + arrayFilters selects item
~~~

These operators commonly appear inside **$set**, **$inc**, **$unset**, **$mul**, and other update operators. They work in **updateOne()**, **updateMany()**, **bulkWrite()**, and corresponding MongoDB Driver update APIs. Acceptance of a specific statement also depends on server version, field types, and the semantics of the update operator used.

## 2. Preparing the Practice Data

In **mongosh**, select a database dedicated to practice:

~~~javascript
use positional_update_lab
~~~

Insert three sample documents. Each line item is an object in the **items** array:

~~~javascript
db.orders.insertMany([
  {
    _id: "ORD-101",
    customerId: "CUS-01",
    status: "OPEN",
    items: [
      {
        sku: "PEN-BLUE",
        qty: NumberInt(2),
        state: "NEW",
        price: NumberDecimal("12000.00")
      },
      {
        sku: "NOTE-A5",
        qty: NumberInt(1),
        state: "NEW",
        price: NumberDecimal("35000.00")
      },
      {
        sku: "PEN-BLUE",
        qty: NumberInt(5),
        state: "NEW",
        price: NumberDecimal("12000.00")
      }
    ]
  },
  {
    _id: "ORD-102",
    customerId: "CUS-02",
    status: "OPEN",
    items: [
      {
        sku: "PEN-BLUE",
        qty: NumberInt(6),
        state: "NEW",
        price: NumberDecimal("12000.00")
      },
      {
        sku: "ERASER",
        qty: NumberInt(3),
        state: "RESERVED",
        price: NumberDecimal("5000.00")
      }
    ]
  },
  {
    _id: "ORD-103",
    customerId: "CUS-03",
    status: "OPEN",
    items: []
  }
]);
~~~

**Note on execution order:** update commands in later sections mutate the actual data in the lab collection. "Expected results" are explained **starting from the initial state** unless noted otherwise. For independent testing, use a copy of the data or recreate the test collection cleanly; never run data-deletion operations against live databases.

Inspect the data before updating:

~~~javascript
db.orders.find(
  { _id: "ORD-101" },
  { _id: 1, items: 1 }
);
~~~

### 2.1. Distinguishing Document Selection Conditions from Element Selection Conditions

An update statement has these main parts:

~~~javascript
db.orders.updateOne(
  { /* filter selecting document */ },
  { /* update expression: paths and values */ },
  { /* options such as arrayFilters, upsert */ }
);
~~~

With **$**, the document filter also identifies the position of the first matching array element. With **$[]**, no per-element condition is needed. With **$[identifier]**, element conditions live inside **arrayFilters**, while the main filter still determines which documents get updated.

## 3. Positional Operator $: Updating the First Matching Element

### 3.1. Syntax

~~~javascript
db.collection.updateOne(
  { "arrayField.someKey": matchingValue },
  {
    $set: {
      "arrayField.$.otherKey": newValue
    }
  }
);
~~~

The **$** token in **arrayField.$.otherKey** stands for **the position of the first array element** identified by the query condition. This token differs from the **$** prefix on update operator names like **$set**.

### 3.2. Example: Updating the First Line Item with a Given SKU

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.sku": "PEN-BLUE"
  },
  {
    $set: {
      "items.$.state": "PACKED"
    }
  }
);
~~~

Document **ORD-101** has **two** line items with SKU **PEN-BLUE**. With positional **$**, only the **first matching element** is updated:

~~~javascript
{
  _id: "ORD-101",
  items: [
    { sku: "PEN-BLUE", qty: 2, state: "PACKED" },
    { sku: "NOTE-A5", qty: 1, state: "NEW" },
    { sku: "PEN-BLUE", qty: 5, state: "NEW" }
  ]
}
~~~

Other fields such as **price** are omitted in the abbreviated output above but remain in the document. The crucial point is that **the third line (also PEN-BLUE) did not change state**, even though it also matches the SKU.

**Rule:** when you need to update **all line items sharing a SKU**, do not use **$**; use **$[line]** with an appropriate **line.sku** filter.

### 3.3. Why Must the Filter Reference the Array?

A command lacking an array element condition, such as:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$.state": "PACKED" } }
);
~~~

cannot determine a position for **$** and raises an error such as **"The positional operator did not find the match needed from the query"**. Filtering solely by **_id** selects the document, without telling MongoDB **which element in items** to update.

Add an appropriate array condition:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.sku": "NOTE-A5"
  },
  {
    $set: {
      "items.$.state": "RESERVED"
    }
  }
);
~~~

### 3.4. When Multiple Conditions Must Hold on the Same Element

Consider the document:

~~~javascript
{
  _id: "ORD-X",
  items: [
    { sku: "PEN-BLUE", qty: 1 },
    { sku: "NOTE-A5", qty: 9 }
  ]
}
~~~

The filter:

~~~javascript
{
  "items.sku": "PEN-BLUE",
  "items.qty": { $gte: 5 }
}
~~~

matches the document because the SKU condition holds on the **first element** while the `qty` condition holds on the **second element**. Separate **dotted path** conditions do not bind to the same array element.

To update **the first element that has both sku = PEN-BLUE and qty >= 5**, use **$elemMatch**:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    items: {
      $elemMatch: {
        sku: "PEN-BLUE",
        qty: { $gte: 5 }
      }
    }
  },
  {
    $set: {
      "items.$.state": "REQUIRES_CHECK"
    }
  }
);
~~~

In the initial ORD-101 data, only the PEN-BLUE line with **qty = 5** satisfies both conditions, so **$** points to the third element. Using **$elemMatch** pinpoints the right element instead of accidentally matching conditions across different lines.

### 3.5. Positional $ on Scalar Arrays

Arrays do not have to contain objects. Example:

~~~javascript
db.students.insertOne({
  _id: "STU-01",
  scores: [62, 78, 91, 78]
});

db.students.updateOne(
  {
    _id: "STU-01",
    scores: 78
  },
  {
    $set: {
      "scores.$": 80
    }
  }
);
~~~

The resulting **scores** array is **[62, 80, 91, 78]**. Only the **first 78** is replaced. To replace **every** 78, use **$[score]** with **arrayFilters**.

### 3.6. Limitations of Positional $ to Remember

- **Only the first element** matching the query condition is replaced by **$**.
- **The array field must appear in the query** so the operator can determine the matching position.
- Queries involving **multiple array fields** can make positional resolution **ambiguous**; avoid mixing multiple array predicates when targeting a single element. Use precise conditions and consider **$[identifier]**.
- **$ cannot traverse multiple levels of nested arrays** as two independent array positions in one path; use **$[]/$[identifier]** for nested arrays.
- Negation operators such as **$ne**, **$nin**, or **$not** on arrays have specific positional limitations; in some cases negation must be placed **inside $elemMatch** to use positional **$**.
- **Do not use $ in an upsert** that may insert a new document: there is no matched element to locate, and **$** can be treated as a literal field name in the insert branch.

### 3.7. $unset with Positional $ Does Not Delete the Element

~~~javascript
db.students.updateOne(
  {
    _id: "STU-01",
    scores: 91
  },
  {
    $unset: {
      "scores.$": ""
    }
  }
);
~~~

With **$unset** targeting an **array element**, MongoDB sets that slot to **null** rather than shrinking the array. To **remove elements** matching a condition, use **$pull** with an appropriate predicate:

~~~javascript
db.students.updateOne(
  { _id: "STU-01" },
  { $pull: { scores: 91 } }
);
~~~

**$pull** removes matching elements from the array; it is not a variant of **$set**.

## 4. Operator $[]: Updating All Array Elements

### 4.1. Syntax

~~~javascript
db.collection.updateOne(
  { /* select document */ },
  {
    $set: {
      "arrayField.$[].someKey": value
    }
  }
);
~~~

**$[]** means "all positions in the array indicated by the path". It takes **no** identifier and requires no **arrayFilters**.

### 4.2. Adding an Audit Field to All Line Items of an Order

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[].reviewed": false
    }
  }
);
~~~

With the initial data, all three objects in **items** receive **reviewed: false**. MongoDB updates elements **inside the selected document**, not across every document in the collection.

Before running, distinguish:

- **updateOne()** selects at most one document to update.
- **$[]** updates every element of that document's array field.

When using **updateMany()**:

~~~javascript
db.orders.updateMany(
  { status: "OPEN" },
  {
    $set: {
      "items.$[].reviewed": false
    }
  }
);
~~~

MongoDB visits documents matching **status = OPEN** and updates every **items** element in **each** matched document. This still **does not** turn the multi-document batch into a single atomic transaction.

### 4.3. Incrementing All Numeric Values in an Array

~~~javascript
db.students.insertOne({
  _id: "STU-02",
  scores: [60, 70, 80]
});

db.students.updateOne(
  { _id: "STU-02" },
  {
    $inc: {
      "scores.$[]": 5
    }
  }
);
~~~

The result is **scores: [65, 75, 85]**. If the array contains non-numeric elements, **$inc** fails; design proper schemas and validate source data.

### 4.4. Empty Arrays and Missing Fields

When **items: []**, there are no elements to update. The operation matches the document without modifying any elements.

If **items** does not exist or is not an array at the target path, MongoDB rejects the operation with an error such as **"The path 'items' must exist in the document in order to apply array updates"** or a corresponding path error.

**$[] is not a tool for creating missing arrays or elements.** If an application requires the field to exist, initialize documents with a valid array value on insert or run a separate migration for legacy records.

### 4.5. When Is $[] Too Broad?

Suppose only line items with **state = NEW** should be packed. The command:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

also overwrites **ERASER**, which was **RESERVED**, violating business rules. **$[] ignores per-item state.** Whenever only a subset of an array should be updated, use **$[identifier]** with **arrayFilters**.

## 5. Operator $[identifier] and arrayFilters: Updating Elements Matching Conditions

### 5.1. General Syntax

~~~javascript
db.collection.updateOne(
  { /* filter selecting document */ },
  {
    $set: {
      "arrayField.$[elem].someKey": value
    }
  },
  {
    arrayFilters: [
      { "elem.someKey": condition }
    ]
  }
);
~~~

Where:

- **$[elem]** is a placeholder in the update path referring to array elements.
- **elem** is an **identifier** chosen by the author, not a real field in the document.
- **arrayFilters** is an array of filter documents specifying **which array elements** match that identifier.
- **The main filter** still selects documents; **arrayFilters** selects elements within each selected document.

An identifier must **begin with a lowercase letter** and contain only **alphanumeric characters**; e.g., **line**, **item2**, **grade**. Never use spaces, dots, or underscores in identifiers.

### 5.2. Updating All Items with Quantity 3 or More

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "NEEDS_REVIEW"
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 3 } }
    ]
  }
);
~~~

In the initial ORD-101 data:

| Index | sku | qty | Matches line.qty >= 3? | Result |
|---|---|---:|---|---|
| 0 | PEN-BLUE | 2 | No | State unchanged. |
| 1 | NOTE-A5 | 1 | No | State unchanged. |
| 2 | PEN-BLUE | 5 | Yes | State becomes NEEDS_REVIEW. |

**$[line] does not stop at the first match:** if three items satisfy the filter, all three are updated.

### 5.3. Multiple Conditions on the Same Element

Find elements with **qty >= 3** and **state = NEW**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "RESERVED"
    }
  },
  {
    arrayFilters: [
      {
        "line.qty": { $gte: 3 },
        "line.state": "NEW"
      }
    ]
  }
);
~~~

Inside one array filter document, conditions on different fields combine with **AND**. Thus an element must satisfy both **qty >= 3** and **state = NEW** to be updated.

Note that **state** values in the data may have changed if you ran the **NEEDS_REVIEW** example earlier. To verify each example independently, test against fresh initial documents.

### 5.4. Matching Multiple SKUs with $in Inside arrayFilters

~~~javascript
db.orders.updateMany(
  { status: "OPEN" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": {
          $in: ["PEN-BLUE", "NOTE-A5"]
        }
      }
    ]
  }
);
~~~

In every OPEN order, **every item** matching either SKU receives **reviewed: true**. There is no need for document-level **$or** when matching a list of values on **the same field**.

### 5.5. ArrayFilters Work Directly on Scalar Arrays

~~~javascript
db.students.insertOne({
  _id: "STU-03",
  scores: [62, 78, 91, 78]
});

db.students.updateOne(
  { _id: "STU-03" },
  {
    $set: {
      "scores.$[score]": 80
    }
  },
  {
    arrayFilters: [
      { score: 78 }
    ]
  }
);
~~~

Result: **scores: [62, 80, 91, 80]**. On scalar arrays, the filter references **score** directly rather than **score.someField**.

Range conditions work too:

~~~javascript
db.students.updateOne(
  { _id: "STU-03" },
  {
    $inc: {
      "scores.$[score]": 2
    }
  },
  {
    arrayFilters: [
      { score: { $gte: 90 } }
    ]
  }
);
~~~

Only scores **>= 90** before the update are incremented by 2. Values do not repeatedly cross thresholds within the same operation.

### 5.6. Similarities and Differences Between $[] and $[identifier]

| Aspect | **$[]** | **$[identifier]** |
|---|---|---|
| Element selection | Every element in the array. | Every element matching the filter. |
| Requires **arrayFilters**? | No. | Yes, with a filter for the identifier. |
| Works with scalar arrays? | Yes. | Yes. |
| Works with arrays of objects? | Yes. | Yes. |
| Can update multiple elements? | Yes. | Yes. |
| Use when | All elements genuinely need updating. | Only a conditional subset needs updating. |

### 5.7. $[identifier] Does Not Modify the Document Just Because the Document Filter Matched

Suppose the main filter is **{status: "OPEN"}** and **arrayFilters** checks for items with **qty >= 10**. An OPEN document lacking any qualifying item is still counted in **matchedCount**, while **modifiedCount** remains 0 because no element actually changed.

This is crucial when interpreting update results: **matchedCount is not the number of modified array elements**.

## 6. Rules for Declaring arrayFilters

### 6.1. Every Identifier Must Have a Corresponding Filter

The command below lacks a filter for **line**:

~~~javascript
// Wrong: $[line] present but no arrayFilters for line.
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[line].state": "PACKED" } }
);
~~~

MongoDB does not know which elements **line** represents and cannot execute the update.

Proper declaration:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[line].state": "PACKED" } },
  {
    arrayFilters: [
      { "line.sku": "PEN-BLUE" }
    ]
  }
);
~~~

### 6.2. Each Identifier Must Have Only One Filter Document

Do not split two conditions for the same identifier across two separate objects:

~~~javascript
// Wrong: identifier line declared across two separate filter documents.
{
  arrayFilters: [
    { "line.qty": { $gte: 3 } },
    { "line.state": "NEW" }
  ]
}
~~~

Combine conditions into **one** document:

~~~javascript
{
  arrayFilters: [
    {
      "line.qty": { $gte: 3 },
      "line.state": "NEW"
    }
  ]
}
~~~

For complex AND/OR logic on the same identifier, use supported logical operators inside **one filter document** rather than creating multiple filter documents for the same identifier name.

### 6.3. Restricted Operators Inside arrayFilters

MongoDB **disallows** the following operators inside **arrayFilters**:

- **$expr**;
- **$text**;
- **$where**.

If you want to filter by comparing two fields inside an item, you cannot simply put **$expr** in `arrayFilters`. Consider redesigning the data model, using an **aggregation pipeline update** with **$map/$cond** (subject to its own trade-offs), or computing eligibility in the application and translating into supported criteria.

### 6.4. Avoid Arbitrary Identifiers or Collisions with Real Field Names

In the path:

~~~javascript
"items.$[line].state"
~~~

**line** is merely a placeholder. MongoDB does not add a `line` field to each object. You can rename **line** to **item**, as long as the name in the update path matches `arrayFilters`:

~~~javascript
"items.$[item].state"
arrayFilters: [
  { "item.sku": "PEN-BLUE" }
]
~~~

There is no rule requiring the identifier to match the array name; it just needs to be valid and readable.

## 7. Updating Nested Arrays with Multiple Placeholders

Real-world documents can contain multiple levels of nested arrays. For instance, a shipment contains packages, and each package contains checks:

~~~javascript
db.shipments.insertOne({
  _id: "SHIP-001",
  status: "OPEN",
  packages: [
    {
      tracking: "PKG-A",
      checks: [
        { type: "WEIGHT", passed: false },
        { type: "LABEL", passed: false }
      ]
    },
    {
      tracking: "PKG-B",
      checks: [
        { type: "WEIGHT", passed: false },
        { type: "LABEL", passed: true }
      ]
    }
  ]
});
~~~

### 7.1. Filtering Each Array Level Independently

Requirement: inside package **PKG-A**, mark only the **WEIGHT** check as passed.

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[pkg].checks.$[check].passed": true
    }
  },
  {
    arrayFilters: [
      { "pkg.tracking": "PKG-A" },
      { "check.type": "WEIGHT" }
    ]
  }
);
~~~

Breakdown:

1. **_id** selects the shipment.
2. **$[pkg]** selects packages with tracking = PKG-A.
3. **$[check]** selects checks with type = WEIGHT **inside the selected packages**.
4. **$set** modifies **passed** on those matching elements.

After updating, **PKG-A/WEIGHT** becomes **true**. All other checks keep their existing values.

### 7.2. Combining $[] and $[identifier]

Requirement: mark **every WEIGHT check across all packages** as passed.

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[].checks.$[check].passed": true
    }
  },
  {
    arrayFilters: [
      { "check.type": "WEIGHT" }
    ]
  }
);
~~~

Here:

- **packages.$[]** selects every package;
- **checks.$[check]** selects WEIGHT checks inside each package;
- no filter is needed for **$[]**, only for **check**.

### 7.3. Using Two $[] Placeholders Across All Levels

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[].checks.$[].reviewed": true
    }
  }
);
~~~

This adds **reviewed: true** to every check of every package in the shipment, assuming valid array structures. Because the blast radius is wide, confirm business intent before running.

### 7.4. Why Positional $ Cannot Handle Nested Arrays Well

A path such as:

~~~javascript
// Do not use to locate two independent array positions.
"packages.$.checks.$.passed"
~~~

is not a viable way to index two array levels using plain positional **$**. **$** is limited when traversing multiple arrays. Placeholders **$[]** and **$[identifier]** exist specifically to express nested array updates cleanly.

### 7.5. Watch the Conditions at Each Level

If an update filters **pkg.tracking** without filtering **check.type**, an **$[]** at the check level updates every check in the selected package. Conversely, filtering `check` while using **packages.$[]** updates matching checks across **all** packages.

When nesting multiple arrays, read from left to right:

~~~text
packages
    -> which package to select?
       -> checks
           -> which check to select?
               -> which field to update?
~~~

## 8. ArrayFilters with AND, OR, and Different Data Types

### 8.1. AND Condition

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "PRIORITY"
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "PEN-BLUE",
        "line.qty": { $gte: 3 }
      }
    ]
  }
);
~~~

Only lines having both SKU PEN-BLUE and qty >= 3 are updated. In the initial data, that is the line with qty = 5.

### 8.2. OR Condition

OR criteria can be grouped inside **one filter document**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      {
        $or: [
          { "line.sku": "NOTE-A5" },
          { "line.qty": { $gte: 5 } }
        ]
      }
    ]
  }
);
~~~

The filter uses **the same identifier `line`** across both branches, obeying the rule of one filter document per identifier. If an OR condition merely checks a list of SKUs on the same field, **$in** is usually cleaner.

### 8.3. Integers, Decimal128, and BSON Types

When **price** is stored as Decimal128, match and assign using the exact BSON type:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].price": NumberDecimal("11000.00")
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "PEN-BLUE",
        "line.price": { $gt: NumberDecimal("10000.00") }
      }
    ]
  }
);
~~~

**NumberDecimal** preserves Decimal128 precision instead of accidentally storing a double. Java/Spring Data applications must map correspondingly to **Decimal128/BigDecimal**.

### 8.4. Elements Missing a Field

If an object inside the array lacks **state**, the filter:

~~~javascript
{ "line.state": "NEW" }
~~~

will not match that element. To backfill elements missing `state`, use **$exists: false**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "NEW"
    }
  },
  {
    arrayFilters: [
      { "line.state": { $exists: false } }
    ]
  }
);
~~~

This serves migration/normalization tasks. Validate payload types: if the array contains non-object elements, you cannot safely attach **state** to them.

## 9. Update Results: matchedCount and modifiedCount

Calling **updateOne/updateMany** typically returns **matchedCount**, **modifiedCount**, and **upsertedId** if an upsert occurred.

~~~javascript
const result = db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 100 } }
    ]
  }
);

printjson(result);
~~~

On the initial data, the main filter **_id = ORD-101** matches the document, yet **no line** has qty >= 100. Thus the output shows:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 0,
  upsertedCount: 0,
  upsertedId: null
}
~~~

Key points:

- **matchedCount** is the **number of documents** matching the main filter, not the number of matching array elements.
- **modifiedCount** is the **number of actually modified documents**, not the number of modified elements.
- One document with **100 modified elements** still counts as **1 modified document**.
- If the update sets values equal to existing values, the document matches without being modified.

To know the exact count of modified array elements for business reporting, design a separate tracking method (e.g., pre-reading/counting under consistent guards, emitting events, or computing in a pipeline). Never infer element counts directly from `modifiedCount`.

## 10. updateOne and updateMany Change Document Scope, Not Placeholder Semantics

### 10.1. Single Document

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[line].state": "BACKORDER" } },
  { arrayFilters: [ { "line.qty": { $gte: 5 } } ] }
);
~~~

Only **ORD-101** is examined; every item with qty >= 5 inside that document transitions state.

### 10.2. Multiple Documents

~~~javascript
db.orders.updateMany(
  { status: "OPEN" },
  { $set: { "items.$[line].state": "BACKORDER" } },
  { arrayFilters: [ { "line.qty": { $gte: 5 } } ] }
);
~~~

Every OPEN document is examined, and every line with qty >= 5 inside each document transitions state. If both ORD-101 and ORD-102 are OPEN, qualifying items in **both orders** are updated.

In multi-tenant systems, include **tenantId** from the authenticated context in the filter:

~~~javascript
db.orders.updateMany(
  {
    tenantId: "TENANT-A",
    status: "OPEN"
  },
  {
    $set: {
      "items.$[line].state": "BACKORDER"
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 5 } }
    ]
  }
);
~~~

This assumes production collections include **tenantId**, whereas the initial lab dataset lacks it; running this verbatim on the lab data matches zero documents.

**Atomicity:** each update on **a single document** is atomic under MongoDB semantics. **updateMany() does not automatically make all documents change together as one transaction.** If business rules require cross-document atomicity, evaluate multi-document transactions and their overhead.

## 11. Upsert: Special Behavior of $ and $[]/$[identifier]

**Upsert** allows MongoDB to insert a new document when no matching document is found. With positional updates, you cannot assume the array already exists.

### 11.1. Never Use Positional $ to Upsert an Array Item

~~~javascript
// Invalid way to create a new array element when no document exists.
db.orders.updateOne(
  { _id: "ORD-NEW", "items.sku": "PEN-BLUE" },
  { $set: { "items.$.state": "NEW" } },
  { upsert: true }
);
~~~

When no document matches, **$** has no element position to update. MongoDB restricts positional **$** in upserts; never use this expecting it to "auto-create an item".

To create a new order, insert a complete document with **insertOne()** or an upsert providing an explicit array payload rather than relying on placeholders.

### 11.2. $[] and $[identifier] in Upserts Require Specific Array Equality

With **$[]** or **$[identifier]**, when an upsert can enter the insert branch, MongoDB requires the filter to specify an **exact equality condition on the array field itself** to seed the initial array.

Example for a scalar array in a test collection:

~~~javascript
db.example_arrays.updateOne(
  { values: [0, 1] },
  {
    $set: {
      "values.$[]": 10
    }
  },
  { upsert: true }
);
~~~

When no document matches, **values: [0, 1]** provides an **exact equality** on the array, enabling MongoDB to execute the insert branch and apply the positional update to those seeded elements.

With **$[element]**:

~~~javascript
db.example_arrays.updateOne(
  { values: [0, 1] },
  {
    $set: {
      "values.$[element]": 2
    }
  },
  {
    arrayFilters: [
      { element: 0 }
    ],
    upsert: true
  }
);
~~~

The equality condition must suit your data and business logic; these examples merely illustrate syntax, not a typical API creation pattern. With a filter matching only **_id** and no array field, an upsert using **$[]/$[identifier]** will fail because the array path does not exist.

### 11.3. Safer Patterns

Separate creation from updates cleanly:

1. **Create**: use **insertOne** or upsert with **$setOnInsert** to initialize **items: []** or a complete explicit items array.
2. **Update existing**: use **$/$[]/$[identifier]** once you know the array exists.
3. **Append a new item**: use **$push** or **$addToSet** as needed, never positional updates, to add a previously absent element.

When concurrent requests race to create/update, add unique keys and retry strategies to handle race conditions.

## 12. Common Limitations and Syntax Errors

### 12.1. Using $ When the Query Does Not Identify an Element

~~~javascript
// Insufficient to determine position of items.$
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$.state": "DONE" } }
);
~~~

Fix: add an array condition to the query, or switch to **$[line]** with `arrayFilters`.

### 12.2. Confusing $[] with "All Elements Matching the Document Filter"

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.state": "NEW"
  },
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

The filter **"items.state": "NEW"** only selects **documents containing at least one NEW item**. Once the document matches, **$[] updates the state of every item**, including items already RESERVED or CANCELLED.

To update only NEW items:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "PACKED"
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

### 12.3. Supplying arrayFilters Without Referencing the Identifier in the Update Path

~~~javascript
// Wrong: filter line is not referenced in the update path.
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[].state": "PACKED" } },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

**$[]** has no **line** placeholder to bind to the filter. Either use **$[line]**, or drop `arrayFilters` if you truly intend to update every element.

### 12.4. Invalid Identifiers

~~~javascript
// Avoid identifiers with underscores or starting with an uppercase letter.
"items.$[line_item].state"
"items.$[Line].state"
~~~

Use names like **lineItem**, **item2**, or **grade**; identifiers must start with a lowercase letter and contain only ASCII letters and digits.

### 12.5. Forgetting Tenant/Document Filters

~~~javascript
db.orders.updateMany(
  {},
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

This broadly mutates every document with a matching array structure. Never pass an empty filter **{}** in production without a deliberate plan and rollout controls.

### 12.6. Updating an Array Field with the Wrong Data Type

Legacy documents may hold:

~~~javascript
{ _id: "LEGACY", items: null }
~~~

Paths like **items.$[].state** or **items.$[line].state** expect **items to be an array**. If the field is null, a string, or an incompatible structure, MongoDB errors and skips the update. Use migrations or validators to prevent schema drift.

### 12.7. Running $unset on an Array Element Expecting Removal

~~~javascript
{
  $unset: {
    "scores.$": ""
  }
}
~~~

On an array element, this leaves **null** in that slot. To delete matching items, use **$pull** and review index-ordering assumptions.

### 12.8. Bulk-Changing States Without Checking Valid Transitions

If an item is **CANCELLED**, a general command must not blindly overwrite it to **PACKED**. Filter by valid source state:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", status: "OPEN" },
  { $set: { "items.$[line].state": "PACKED" } },
  { arrayFilters: [ { "line.state": "NEW" } ] }
);
~~~

In complex workflows, enforce transition rules in the domain layer and coordinate side effects (inventory, payment, fulfillment).

## 13. Positional Updates, Atomicity, and Concurrency

### 13.1. Document-Level Atomicity

MongoDB guarantees atomicity for an update operation on **one document**. Example:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "PACKED",
      "lastUpdatedBy": "packing-service"
    },
    $currentDate: {
      updatedAt: true
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

Inside **ORD-101**, updating matching items and updating metadata occur in one atomic operation. If validation fails, MongoDB rejects the update rather than persisting a half-updated document.

### 13.2. Atomicity Alone Does Not Prevent Lost Updates in All Workflows

Suppose two services process the same order:

- Service A wants to move NEW items to PACKED.
- Service B wants to cancel NEW items.

If both use **$[]** without checking current state, the later request overwrites the state set by the earlier one. Embed **preconditions** into filters/arrayFilters—such as **line.state: "NEW"**—and handle **matched/modified counts** alongside business logic.

### 13.3. Optimistic Concurrency Using revision

You can store an order **revision** and update only when it matches what the client read:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    revision: NumberInt(7)
  },
  {
    $set: {
      "items.$[line].state": "PACKED"
    },
    $inc: {
      revision: 1
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

This assumes the document has **revision = 7**. If another update already bumped revision, the main filter fails to match and nothing changes.

**Consideration:** if the main filter matches while **zero items are NEW**, `$inc` on `revision` will still modify the document. Therefore, if revision should advance only when at least one qualifying element exists, add an **element existence check** to the main filter, such as **"items.state": "NEW"**, matching `arrayFilters`:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    revision: NumberInt(7),
    "items.state": "NEW"
  },
  {
    $set: {
      "items.$[line].state": "PACKED"
    },
    $inc: {
      revision: 1
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

In practice, the main filter should capture the exact precondition that makes the batch update meaningful. Checking **matchedCount** and **modifiedCount** does not replace defining invariants.

### 13.4. Retries and Repeatability

Most **$set** updates to a fixed value are idempotent at the field-value level, whereas **$inc** is not idempotent if the application replays an operation that already succeeded.

Example:

~~~javascript
db.students.updateOne(
  { _id: "STU-02" },
  { $inc: { "scores.$[]": 1 } }
);
~~~

If the application resends this as a fresh business request, every score increments again. MongoDB drivers support retryable writes under certain conditions, yet do not confuse automatic driver retries with replaying business events lacking idempotency keys.

## 14. Java Sync Driver: Updating Arrays with Filters and Updates

In the **MongoDB Java Sync Driver**, construct filters with **Filters**, updates with **Updates**, and **arrayFilters** via **UpdateOptions**. Paths like **items.$.state**, **items.$[].reviewed**, and **items.$[line].state** are still passed as field-path strings.

### 14.1. Positional $ in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

// MongoDatabase database has been created from MongoClient.
MongoCollection<Document> orders =
        database.getCollection("orders");

Bson filter = Filters.and(
        Filters.eq("_id", "ORD-101"),
        Filters.eq("items.sku", "PEN-BLUE")
);

Bson update = Updates.set("items.$.state", "PACKED");

UpdateResult result = orders.updateOne(filter, update);
System.out.println("Matched: " + result.getMatchedCount());
System.out.println("Modified: " + result.getModifiedCount());
~~~

**Filters.eq("items.sku", ...)** lets MongoDB locate the first matching element for positional **$**. If the same SKU appears multiple times, only the first matching element updates.

### 14.2. $[] in Java

~~~java
Bson filter = Filters.eq("_id", "ORD-101");
Bson update = Updates.set("items.$[].reviewed", false);

UpdateResult result = orders.updateOne(filter, update);
~~~

No **UpdateOptions.arrayFilters(...)** is needed because there is no named placeholder.

### 14.3. $[line] and UpdateOptions.arrayFilters

~~~java
import com.mongodb.client.model.UpdateOptions;
import java.util.List;

Bson filter = Filters.eq("_id", "ORD-101");
Bson update = Updates.set("items.$[line].state", "RESERVED");

UpdateOptions options = new UpdateOptions().arrayFilters(
        List.of(
                new Document("line.state", "NEW")
                        .append("line.qty",
                                new Document("$gte", 3))
        )
);

UpdateResult result = orders.updateOne(filter, update, options);
~~~

Every **line** in ORD-101 with **state = NEW** and **qty >= 3** transitions to RESERVED. **UpdateOptions** passes `arrayFilters` to the server; the **line** name in the BSON filter must match the update path.

### 14.4. Multiple Identifiers in Java

Assuming the **shipments** collection has the nested array structure from Section 7:

~~~java
MongoCollection<Document> shipments =
        database.getCollection("shipments");

Bson filter = Filters.eq("_id", "SHIP-001");
Bson update = Updates.set(
        "packages.$[pkg].checks.$[check].passed",
        true
);

UpdateOptions options = new UpdateOptions().arrayFilters(
        List.of(
                new Document("pkg.tracking", "PKG-A"),
                new Document("check.type", "WEIGHT")
        )
);

shipments.updateOne(filter, update, options);
~~~

Because the update path uses **two distinct identifiers**, the `arrayFilters` list holds **one filter document for `pkg` and one filter document for `check`**.

### 14.5. When Using POJOs Instead of Document

With POJO mapping, keep in mind:

- MongoDB field names may differ from Java field names via annotations or naming conventions.
- BSON types of **qty**, **price**, and **state** must align with codecs and validators.
- Names in **arrayFilters** must not be guessed from Java variable names; verify against actual stored document fields.
- The Java driver provides typed builders, yet positional path strings must still match stored schema fields.

The Java snippets above use **Document** to clearly show how MongoDB interprets update paths; production systems also require exception handling, authorization, logging/metrics, and result verification.

## 15. Spring Data MongoDB: Update.filterArray

In **Spring Data MongoDB**, you can use **MongoTemplate**, **Query**, **Criteria**, and **Update**. For **$[identifier]**, Spring Data provides **Update.filterArray(...)** to forward `arrayFilters` to MongoDB.

### 15.1. Positional $ with MongoTemplate

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

// MongoTemplate mongoTemplate is injected by Spring.
Query query = Query.query(
        Criteria.where("_id").is("ORD-101")
                .and("items.sku").is("PEN-BLUE")
);

Update update = new Update()
        .set("items.$.state", "PACKED");

UpdateResult result =
        mongoTemplate.updateFirst(query, update, "orders");
~~~

This still uses MongoDB positional **$**: **only the first element matching the query**, not all elements.

### 15.2. $[] with MongoTemplate

~~~java
Query query = Query.query(
        Criteria.where("_id").is("ORD-101")
);

Update update = new Update()
        .set("items.$[].reviewed", false);

mongoTemplate.updateFirst(query, update, "orders");
~~~

### 15.3. $[line] via Update.filterArray

~~~java
Query query = Query.query(
        Criteria.where("_id").is("ORD-101")
);

Update update = new Update()
        .set("items.$[line].state", "RESERVED")
        .filterArray(
                Criteria.where("line.state").is("NEW")
                        .and("line.qty").gte(3)
        );

UpdateResult result =
        mongoTemplate.updateFirst(query, update, "orders");
~~~

Spring Data's **filterArray** attaches criteria for identifier **line**. Important caveat: `filterArray` criteria may **not undergo the same entity field-name mapping as top-level query criteria**, depending on the Spring Data API and version. When using custom field names like **@Field("qty_value")**, verify the actual BSON field name and library behavior.

### 15.4. Multi-Level Filtering in Spring Data

~~~java
Query query = Query.query(
        Criteria.where("_id").is("SHIP-001")
);

Update update = new Update()
        .set("packages.$[pkg].checks.$[check].passed", true)
        .filterArray(
                Criteria.where("pkg.tracking").is("PKG-A")
        )
        .filterArray(
                Criteria.where("check.type").is("WEIGHT")
        );

mongoTemplate.updateFirst(query, update, "shipments");
~~~

Each identifier gets its own filter. This example targets the collection by name without requiring a pre-declared entity class.

### 15.5. Choosing updateFirst vs. updateMulti

- **updateFirst** updates the first document matching the query.
- **updateMulti** updates all documents matching the query.
- **$[]/$[identifier]** still operates **within each selected document**.

When updating multiple orders, constrain the main query by tenant/status/time range rather than passing an overly broad query.

## 16. Updating Arrays via Aggregation Pipeline: Alternatives to Positional Updates

MongoDB supports **aggregation pipeline updates** in supported versions. Pipelines shine when transforming an array using computed expressions, such as modifying specific elements with **$map** and **$cond**.

Example setting status on items with **qty >= 3** while leaving other items untouched:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  [
    {
      $set: {
        items: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $cond: [
                { $gte: ["$$line.qty", 3] },
                {
                  $mergeObjects: [
                    "$$line",
                    { state: "NEEDS_REVIEW" }
                  ]
                },
                "$$line"
              ]
            }
          }
        }
      }
    }
  ]
);
~~~

Breakdown:

1. **$map** iterates over **items**.
2. **$gte** evaluates each item's `qty`.
3. **$mergeObjects** builds a new object keeping existing fields while updating `state` when the condition holds.
4. **$cond** keeps the original element unchanged otherwise.
5. **$set** assigns the transformed array.

Here **$$line** is an aggregation pipeline variable, **distinct from** the placeholder identifier in **$[line]**. The two mechanisms are not syntactically interchangeable.

### 16.1. When to Choose $[identifier]

Choose **$[identifier]** when you only need to **filter elements using predicates supported by `arrayFilters`** and apply standard update operators like **$set/$inc** to specific fields.

### 16.2. When to Choose $map/$cond

Choose an **aggregation pipeline update** when you need to:

- Compute new values from existing fields of each element;
- Perform complex structural comparisons/transformations;
- Construct a new array from expressions;
- Use aggregation operators disallowed inside `arrayFilters`.

**Note:** pipeline updates do not use positional **$[]/$[identifier]** syntax like standard update documents; use aggregation expressions to transform arrays. Also note that this pipeline **rebuilds the entire array**, so benchmark its cost on large arrays. Let your data model and real workload guide the choice.

## 17. How Array Indices, $push, $pull, and $addToSet Differ from Positional Updates

MongoDB offers several ways to modify arrays. Do not use positional operators for every task.

| Need | Suitable Tool |
|---|---|
| Edit **the first element matching a query** | **$** |
| Edit **all elements** | **$[]** |
| Edit **elements matching conditions** | **$[identifier] + arrayFilters** |
| Append an element to the end of an array | **$push** |
| Add a value only if absent by equality | **$addToSet** |
| Remove all elements matching a condition | **$pull** |
| Remove first or last element of an array | **$pop** |
| Update a known fixed index | **arrayField.0**, **arrayField.1**, etc. |
| Transform whole array using expressions | **$map/$filter** in aggregation update pipeline |

### 17.1. Updating by Fixed Index

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.0.state": "PACKED" } }
);
~~~

The path **items.0** directly targets index 0 **without checking SKU**. If item ordering changes, the same command modifies a different line item. Use fixed indices only when position is guaranteed and remains valid.

### 17.2. Adding a Line Item

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $push: {
      items: {
        sku: "ERASER",
        qty: NumberInt(1),
        state: "NEW",
        price: NumberDecimal("5000.00")
      }
    }
  }
);
~~~

**$push** appends new elements, whereas **$/$[]/$[identifier]** modify existing elements.

### 17.3. Removing Cancelled Elements

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $pull: {
      items: { state: "CANCELLED" }
    }
  }
);
~~~

**$pull** changes the array length, unlike **$unset** on an array index, which can leave **null** in place.

### 17.4. Never Let Arrays Grow Unboundedly

Arrays like **history**, **events**, or **logs** can grow continuously. MongoDB enforces a **16 MiB** size limit per standard BSON document. For unbounded history, store events in a separate collection instead of endlessly updating an embedded array in one document.

## 18. Schema Validation for Safer Positional Updates

MongoDB's flexible schema does not automatically prevent a document from storing:

~~~javascript
{
  _id: "BAD-ORDER",
  items: [
    { sku: "PEN-BLUE", qty: "five", state: "NEW" },
    null,
    123
  ]
}
~~~

Updates targeting **items.$[line].qty** or **items.$[].state** will fail or behave unpredictably when elements are not objects or **qty** is a string.

MongoDB **$jsonSchema** lets you require **items** to be an array of objects with valid fields and types.

Example creating a separate collection for the validation lab:

~~~javascript
db.createCollection("validated_orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["items"],
      properties: {
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["sku", "qty", "state"],
            properties: {
              sku: { bsonType: "string" },
              qty: {
                bsonType: "int",
                minimum: 0
              },
              state: {
                enum: [
                  "NEW",
                  "RESERVED",
                  "PACKED",
                  "CANCELLED"
                ]
              }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

With this validator, standard inserts/updates violating the schema are rejected, preventing mixed-type arrays. Depending on your domain, also validate **price**, **tenantId**, maximum array size, and other business rules.

**Schema validation does not replace business logic.** For instance, transitioning **CANCELLED -> PACKED** may be illegal even though both appear in the `state` enum. Enforce state-transition rules in the service layer and update filters.

## 19. Indexes and Performance When Updating Array Elements

Positional updates have two distinct filter layers:

1. **The main filter** helps MongoDB locate candidate documents.
2. **arrayFilters** identifies **elements within each array** once a document is selected.

A **multikey index** can accelerate queries on array fields to find candidate documents, though it does not let **$[identifier]** skip reading/rewriting the document.

### 19.1. Indexing for the Main Filter

~~~javascript
db.orders.createIndex(
  { customerId: 1, "items.sku": 1 },
  { name: "ix_customer_item_sku" }
);
~~~

If the application often looks up orders by `customerId` and SKU, this index helps locate target documents:

~~~javascript
db.orders.find({
  customerId: "CUS-01",
  "items.sku": "PEN-BLUE"
}).explain("executionStats");
~~~

Measure benefits on representative data sizes. On collections with just a handful of documents, the query planner may pick a collection scan as cheaper than using an index.

### 19.2. ArrayFilters Do Not Replace Document-Level Filters

Example:

~~~javascript
db.orders.updateMany(
  {},
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.sku": "PEN-BLUE" }
    ]
  }
);
~~~

Even with selective **arrayFilters**, an empty main filter **{}** scans every document in the collection. If business rules target only customer CUS-01's orders containing that SKU, include both in the main query:

~~~javascript
db.orders.updateMany(
  {
    customerId: "CUS-01",
    "items.sku": "PEN-BLUE"
  },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.sku": "PEN-BLUE" }
    ]
  }
);
~~~

The main filter narrows candidate documents; `arrayFilters` selects which elements get updated. Not every condition must be duplicated in both places, yet tightening document selection directly impacts performance.

### 19.3. Large Arrays Still Have Overhead

A document with **5 elements** behaves very differently from one with **50,000 elements** in terms of I/O, cache footprint, and scan/edit latency. As arrays grow large:

- Consider **splitting elements into a separate collection** when accessed/written independently;
- Avoid sweeping **$[]** updates on huge arrays unless truly required;
- Use projections/targeted reads and benchmark update latency;
- Watch out for write contention when many services modify the same hot document.

MongoDB guarantees document-level atomicity, yet **an oversized array inside a single document** can still bottleneck concurrency and size limits.

### 19.4. Monitoring Performance

Metrics to track:

| Metric | Meaning |
|---|---|
| **matchedCount/modifiedCount** | Distinguishes matched documents from modified documents. |
| **Write latency p95/p99** | Surfaces slow large updates or hot-document contention. |
| **totalDocsExamined** in explain of matching read filter | Indicates selectivity and index effectiveness for finding documents. |
| **Replication lag / write concern latency** | Impact when large updates replicate across nodes. |
| **Disk/cache activity** | I/O pressure from document rewrites and index maintenance. |
| **Write errors/validation errors** | Signals schema drift, invalid array paths, or illegal states. |

There is no universal "optimal array length" for all workloads. Benchmark using realistic data and traffic patterns.

## 20. Designing Safe Array Update APIs

Consider an endpoint:

~~~text
PATCH /orders/{orderId}/items/state
~~~

Payload:

~~~json
{
  "sku": "PEN-BLUE",
  "expectedState": "NEW",
  "newState": "PACKED"
}
~~~

If the endpoint updates **all items with that SKU currently in NEW**, construct the query server-side:

~~~javascript
const orderId = "ORD-101";
const sku = "PEN-BLUE";
const expectedState = "NEW";
const newState = "PACKED";

db.orders.updateOne(
  {
    _id: orderId,
    status: "OPEN",
    items: {
      $elemMatch: {
        sku,
        state: expectedState
      }
    }
  },
  {
    $set: {
      "items.$[line].state": newState
    },
    $currentDate: {
      updatedAt: true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": sku,
        "line.state": expectedState
      }
    ]
  }
);
~~~

Why this works:

- The main filter ensures the order is OPEN and contains at least one qualifying item.
- `arrayFilters` updates only items with the matching SKU and expected state.
- Items already CANCELLED or RESERVED remain untouched.
- **$currentDate** applies only when the main filter matches; paired with **$elemMatch**, at least one qualifying line exists at match time.

Production implementations also need:

1. **tenantId/authorization** from a trusted session context, never trusting a raw user-supplied `orderId` alone.
2. Validation that **expectedState -> newState** is a permitted state transition.
3. Validation of SKU length and enum values.
4. Clear API semantics on whether to update **all lines sharing a SKU** or a single unique **lineId**.
5. Optimistic locking via **revision** when concurrent conflict detection is needed.
6. Handling MongoDB errors, timeouts, and retries per business guarantees.

If each line has a distinct **lineId**, filtering by **lineId** is usually more accurate than SKU because one SKU can appear multiple times in an order.

## 21. Practice Questions

### Exercise 1 — Updating Only the First Line Item

Starting from the initial ORD-101 document, update **the first element** with **sku = PEN-BLUE** to **state = PACKED** using positional **$**. Explain why the other PEN-BLUE line remains unchanged.

Hint:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", "items.sku": "PEN-BLUE" },
  { $set: { "items.$.state": "PACKED" } }
);
~~~

### Exercise 2 — Updating Every Line Item

Set **reviewed: false** on all **items** elements in ORD-102, regardless of current state.

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  { $set: { "items.$[].reviewed": false } }
);
~~~

### Exercise 3 — Selecting a Subset

Mark only items in ORD-102 with **qty >= 5** as **priority: true**.

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  {
    $set: {
      "items.$[line].priority": true
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 5 } }
    ]
  }
);
~~~

### Exercise 4 — Guarding State Transitions

From the initial state of ORD-102, transition only items with **state = NEW** to **PACKED**. Leave RESERVED items untouched.

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  { $set: { "items.$[line].state": "PACKED" } },
  { arrayFilters: [ { "line.state": "NEW" } ] }
);
~~~

### Exercise 5 — Filtering Nested Arrays

On SHIP-001, set **passed: true** only for **the WEIGHT check of package PKG-B**. Use two identifiers in a single update:

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[pkg].checks.$[check].passed": true
    }
  },
  {
    arrayFilters: [
      { "pkg.tracking": "PKG-B" },
      { "check.type": "WEIGHT" }
    ]
  }
);
~~~

### Exercise 6 — Analyzing matched and modified

Run an update with main filter **_id = ORD-101** and `arrayFilters` **line.qty >= 100**, then inspect the result. Why is **matchedCount = 1** while **modifiedCount = 0**?

### Exercise 7 — Catching Scope Mistakes

Explain why the query:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.state": "NEW"
  },
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

also updates items that are not NEW. Rewrite it using **$[line]** so only NEW items change.

### Exercise 8 — Designing a Migration

Some legacy orders have **items: null** or lack `items`, while newer orders have **items: []**. Outline a data normalization plan before running an **updateMany** using **items.$[]**. Why is filtering by **{status:"OPEN"}** alone insufficient for safety?

### Exercise 9 — Java Driver

Write a Java snippet using **Updates.inc("items.$[line].qty", 1)** and **UpdateOptions.arrayFilters(...)** to increment `qty` on all items with `sku = PEN-BLUE` in ORD-101. Analyze retry implications given addition is non-idempotent.

### Exercise 10 — Choosing the Update Pattern

For each requirement below, choose among **$**, **$[]**, **$[id]**, **$pull**, **$push**, and aggregation **$map**:

- Update the first element with a given product code.
- Mark all elements as read.
- Update every element whose quantity exceeds a threshold.
- Remove cancelled items from the array.
- Append a new item.
- Recompute each item's price from its old price and multiple fields of that item.

## 22. Summary

The three positional update operators are easy to master when you always separate two questions: **"which document?"** and **"which element(s) in the array?"**

~~~text
Select document:
    filter in updateOne/updateMany
              |
              v
Select array elements:

    items.$.field
       -> first element located by the query

    items.$[].field
       -> every element in the array

    items.$[line].field
       -> every element matching arrayFilters for line

    packages.$[pkg].checks.$[check].field
       -> multiple array levels, each identifier with its own filter
              |
              v
Apply $set / $inc / $unset / ...
within the selected document
~~~

Key principles to remember:

1. **$** updates **only the first matching element**, requires a matching condition in the query to establish position, and does not work well across multiple nested array levels.
2. **$[]** updates **all elements** of the array inside documents matching the main filter; the document filter does not restrict inner elements.
3. **$[identifier]** updates **all elements satisfying `arrayFilters`**; each identifier requires one valid filter document.
4. For **nested arrays**, combine **$[]** and multiple **$[identifier]** placeholders to address independent levels.
5. **$unset** on an array position differs from **$pull**; one leaves `null` in place, while the other removes elements.
6. **updateMany** modifies multiple documents, yet atomicity holds **per document**—it does not turn the whole collection update into a transaction.
7. Exercise care with **upserts**: positional **$** cannot be used for the insert branch, and **$[]/$[id]** requires exact array equality in the filter.
8. **Schema validation, state guards, authorization, optimistic locking, and retry policies** remain essential application responsibilities that positional operators alone cannot replace.
9. In **Java/Spring Data**, update paths keep MongoDB's operator notation, with **UpdateOptions.arrayFilters** or **Update.filterArray** supplying placeholder predicates.

### Official MongoDB and Spring Data Documentation

- [Positional $ Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional/) — updating the first matching element, query/upsert/nested array limits.
- [All Positional $[] Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/) — updating all elements and upsert notes.
- [Filtered Positional $[identifier] Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/) — `arrayFilters`, identifiers, nested arrays, and restrictions.
- [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/) — `updateOne`/`updateMany` syntax and update operators.
- [$elemMatch Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — binding multiple conditions to the same element.
- [$pull Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/pull/) — removing array elements by condition.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Java filters, updates, and `UpdateOptions`.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — `MongoTemplate`, `Update`, and `filterArray`.

When implementing in a real service, start by asking **"which elements must change and why?"**, then pick the matching operator. Using positional operators properly avoids read-modify-write array overwrites, prevents scope mistakes, and keeps business updates verifiable in a single MongoDB command.
