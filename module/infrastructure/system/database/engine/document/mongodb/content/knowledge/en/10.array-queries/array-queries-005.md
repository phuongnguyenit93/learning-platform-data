# Checking Array Size with $size and Appropriate Expressions in MongoDB

MongoDB allows a document field to hold an **array**. This leads to many queries based on element counts: finding shopping carts with exactly three line items, accounts with no roles yet, students with at least two skills, or orders containing too many items. MongoDB provides the **$size** query operator for the condition **the array has exactly N elements**. When you need to compare element counts over a range, compare two arrays, or count elements satisfying a condition, you must use computed expressions such as **$size, $expr, $filter, $gt, $gte, $lt, $lte**.

An immediate distinction to make is that MongoDB has **two usages sharing the name $size**:

- **$size query operator**: written in a field's filter, taking a **non-negative integer N** and matching documents where that field is an array with exactly N elements.
- **$size aggregation expression**: takes an **expression returning an array**, counts its elements, and returns the **number of elements**. It can be used in an aggregation pipeline or placed inside **$expr** in find().

The two forms differ in syntax and in how they handle mistyped data. This lesson progresses from basic query examples to dynamic comparisons, null/missing-field handling, nested arrays, conditional counting, Java usage, and index optimization.

## 1. What Is Array Size Really?

The size of an array is the number of **direct elements** at the level being evaluated. It is not BSON byte count, not string character count, not the number of distinct values, and it does not recursively sum elements inside subarrays.

| Value of field tags | Size | Explanation |
|---|---:|---|
| [] | 0 | Empty array |
| ["mongo"] | 1 | One element |
| ["mongo", "java"] | 2 | Two elements |
| ["mongo", "mongo"] | 2 | Two elements despite duplicate values |
| [["mongo", "java"], "docker"] | 2 | Subarray counts as one element of the outer array |
| [{name: "A"}, {name: "B"}] | 2 | Two embedded documents |
| null | Not an array | BSON Null |
| "mongo" | Not an array | BSON String |
| Field absent from document | Not an array | No value to count |

For example, an order has two item lines with quantities 2 and 4 respectively: **$size of items equals 2**, while **total product units equals 6**. If business logic needs total quantity, you must sum the values inside elements instead of using $size.

## 2. Sample Dataset for Practice

In mongosh, select a dedicated database:

~~~javascript
use array_size_lab
~~~

Assume the **students** collection is empty. Run the sample dataset once:

~~~javascript
db.students.insertMany([
  {
    _id: "S01",
    name: "An",
    groups: ["java", "mongo"],
    scores: [80, 90, 75]
  },
  {
    _id: "S02",
    name: "Bình",
    groups: [],
    scores: [60]
  },
  {
    _id: "S03",
    name: "Chi",
    groups: ["mongo"],
    scores: [100, 65]
  },
  {
    _id: "S04",
    name: "Dũng",
    groups: ["java", "mongo", "docker"],
    scores: []
  },
  {
    _id: "S05",
    name: "Hà",
    groups: null,
    scores: null
  },
  {
    _id: "S06",
    name: "Huy"
  },
  {
    _id: "S07",
    name: "Lan",
    groups: "mongo",
    scores: "90"
  },
  {
    _id: "S08",
    name: "Minh",
    groups: ["java", "java"],
    scores: [80, 80]
  },
  {
    _id: "S09",
    name: "Nam",
    groups: [["java", "mongo"], "docker"],
    scores: [95, 70, 85, 55]
  },
  {
    _id: "S10",
    name: "Vy",
    groups: ["kafka", "mongo", "redis", "java"],
    scores: [88, 92, 77, 91, 66]
  }
])
~~~

Documents **S05, S06, S07** are intentionally designed without valid arrays in groups/scores—being **null**, **missing field**, and **String** respectively—to observe the difference between the $size query operator and the aggregation expression.

| ID | groups | groups element count | scores element count |
|---|---|---:|---:|
| S01 | ["java", "mongo"] | 2 | 3 |
| S02 | [] | 0 | 1 |
| S03 | ["mongo"] | 1 | 2 |
| S04 | ["java", "mongo", "docker"] | 3 | 0 |
| S05 | null | Not an array | Not an array |
| S06 | Missing field | Not an array | Not an array |
| S07 | "mongo" | Not an array | Not an array |
| S08 | ["java", "java"] | 2 | 2 |
| S09 | [["java", "mongo"], "docker"] | 2 | 4 |
| S10 | ["kafka", "mongo", "redis", "java"] | 4 | 5 |

To view documents in ID order:

~~~javascript
db.students.find().sort({ _id: 1 })
~~~

Do not rely on the default order of find(); include **sort()** when verifying the expected outputs in this lesson. The example outputs below apply to the initial data, before running the later update section.

## 3. $size Query Operator: Exactly N Elements

Syntax:

~~~javascript
db.collection.find({
  arrayField: { $size: N }
})
~~~

**N must be a non-negative integer**. Example:

~~~javascript
db.students.find(
  { groups: { $size: 2 } },
  { _id: 1, name: 1, groups: 1 }
).sort({ _id: 1 })
~~~

Result: **S01, S08, S09**. S08 still matches because the two "java" elements are duplicates yet occupy two positions; S09 matches because the subarray ["java", "mongo"] counts as **one element of the outer array**.

Other queries:

~~~javascript
// Empty array: S02
db.students.find({ groups: { $size: 0 } })

// Exactly one group: S03
db.students.find({ groups: { $size: 1 } })

// Exactly three groups: S04
db.students.find({ groups: { $size: 3 } })

// Exactly four groups: S10
db.students.find({ groups: { $size: 4 } })
~~~

**$size: 0 only finds empty arrays**. It does not treat groups: null (S05), missing groups (S06), or groups: "mongo" (S07) as arrays with zero elements. Those values do not match the $size query operator.

### 3.1. Applying to Nested Fields

Example order document:

~~~javascript
{
  orderCode: "ORD-001",
  customer: {
    contacts: ["email", "phone"]
  }
}
~~~

Query using dot notation:

~~~javascript
db.orders.find({
  "customer.contacts": { $size: 2 }
})
~~~

The operator counts only direct elements of **customer.contacts**, not any other fields in the document.

### 3.2. Easy-to-Confuse Syntax Forms

~~~javascript
// WRONG: query $size does not accept a comparison operator.
{ groups: { $size: { $gt: 2 } } }

// WRONG: size cannot be negative.
{ groups: { $size: -1 } }

// WRONG: do not pass a string instead of an integer size.
{ groups: { $size: "2" } }

// CORRECT: checks for exactly two elements.
{ groups: { $size: 2 } }
~~~

Writing **{ groups: { $size: 2, $gt: 2 } }** also **does not** mean "groups has more than two elements". Putting $gt next to $size is interpreted as a field-value comparison under MongoDB query rules, not a comparison against the element count. To compare size against a threshold, use the $size aggregation expression as shown in the next section.

## 4. $size Aggregation Expression: Computing Element Count

In aggregation, $size accepts **an expression returning an array** and produces the numeric size:

~~~javascript
{
  $size: "$groups"
}
~~~

The string **"$groups"** references the groups field value of the current document. The expression above is not synonymous with the query **{ groups: { $size: 2 } }**.

Comparison:

| Characteristic | $size query operator | $size aggregation expression |
|---|---|---|
| Syntax | { groups: { $size: 2 } } | { $size: "$groups" } |
| Input | Non-negative integer | Expression returning an array |
| Purpose | Checks exact length | Returns element count for calculations |
| Can be used with $gt/$lte | Not directly | Yes, inside $expr or pipeline |
| When field is not an array | Does not match | $size expression throws an error if argument is not an array |

### 4.1. Computing groupCount in $project

If data always has groups as an array:

~~~javascript
db.students.aggregate([
  {
    $match: { groups: { $type: "array" } }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      groupCount: { $size: "$groups" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

The $match stage selects documents where groups is an array; the $project stage computes the field's length. Results are S01, S02, S03, S04, S08, S09, S10 with groupCount values **2, 0, 1, 3, 2, 2, 4** respectively.

If you omit the $match step on the sample dataset, **$size: "$groups"** can error on S05/S06/S07 because null, missing fields, and String are **not arrays**.

### 4.2. $isArray + $cond to Avoid Errors on Mixed Data

When you are unsure whether a field is always an array, use a type-checked approach:

~~~javascript
db.students.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      groupCount: {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

In the expression:

1. **$isArray** checks whether groups is actually an array.
2. **$cond** selects groups if true, or [] if false.
3. **$size** counts the selected array, avoiding errors.

Under this policy, S05, S06, S07 receive a **conventional** groupCount of 0. That is a decision for handling invalid inputs; it does not mean null, missing, or String are inherently empty arrays.

### 4.3. $ifNull Only Handles Null or Missing

If the schema guarantees groups can only be an array, null, or missing, a shorter form is:

~~~javascript
{
  $size: {
    $ifNull: ["$groups", []]
  }
}
~~~

**$ifNull** replaces null/missing values with []; it **does not replace S07's String "mongo"**. Thus, on an unnormalized sample dataset, $size can still fail. When you must also guard against non-null mistyped fields, use **$isArray + $cond**.

## 5. Finding Arrays with More Than N Elements Using $expr

The **$expr** operator allows using aggregation expressions directly inside a **find()** filter. Because the $size expression returns a number, you can use **$gt** to find arrays longer than a threshold:

~~~javascript
db.students.find({
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

How to read it:

~~~text
document.groups
    |
    v
Check if it is an array?
    |                |
   Yes               No
    |                |
  groups             []
    |                |
    +------ $size ----+
              |
              v
         Size > 2 ?
         /         \
       true        false
~~~

Result from sample data: **S04** (3 groups) and **S10** (4 groups).

Note: **$gt** compares the **numeric result** of the $size expression; it does not compare elements of groups directly.

### 5.1. At Least N Elements with $gte

~~~javascript
db.students.find({
  $expr: {
    $gte: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

Result: **S01, S04, S08, S09, S10**. S03 has only one group; S02 is empty; S05/S06/S07 are mapped to [] and do not pass the threshold.

### 5.2. Fewer Than N Elements with $lt

~~~javascript
db.students.find({
  $expr: {
    $lt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

Result when **treating non-arrays as []**: **S02, S03, S05, S06, S07**. If business logic accepts only **actual arrays**, this is not the result set you want: you must exclude S05/S06/S07 or apply schema validation to prevent mistyped data.

### 5.3. At Most N Elements with $lte, Requiring an Array

To accept only documents where groups is an array of size at most two, combine:

~~~javascript
db.students.find({
  $expr: {
    $and: [
      { $isArray: "$groups" },
      {
        $lte: [
          {
            $size: {
              $cond: [
                { $isArray: "$groups" },
                "$groups",
                []
              ]
            }
          },
          2
        ]
      }
    ]
  }
}).sort({ _id: 1 })
~~~

Result: **S01, S02, S03, S08, S09**.

We still protect $size with **$cond** despite having $isArray in $and: do not rely on an assumption that MongoDB always evaluates $and branches in written order before encountering a potentially failing expression.

### 5.4. Conversion Table for Six Size Comparisons

Assume **arr** is an expression guaranteed to return an array:

| Need | Expression Used Inside $expr |
|---|---|
| Exactly N elements | { $eq: [{ $size: arr }, N] } |
| Different from N elements | { $ne: [{ $size: arr }, N] } |
| More than N elements | { $gt: [{ $size: arr }, N] } |
| At least N elements | { $gte: [{ $size: arr }, N] } |
| Fewer than N elements | { $lt: [{ $size: arr }, N] } |
| At most N elements | { $lte: [{ $size: arr }, N] } |

For **exactly N** elements on an array field, the query operator **{ groups: { $size: N } }** is usually cleaner than $eq + aggregation $size. The remaining cases require a computed expression or a dedicated count field.

## 6. Distinguishing Empty Arrays, Null, Missing, and Wrong Types

Some states look similar in a UI yet differ in the database:

~~~javascript
{ groups: [] }       // Empty array
{ groups: null }     // Field exists, BSON Null value
{ name: "Huy" }      // No groups field
{ groups: "mongo" }  // Field is String, not Array
~~~

On the sample data:

| Purpose | Filter | Result |
|---|---|---|
| Groups is an empty array | { groups: { $size: 0 } } | S02 |
| Groups is null or missing field | { groups: null } | S05, S06 |
| Groups does not exist | { groups: { $exists: false } } | S06 |
| Groups exists | { groups: { $exists: true } } | S01–S05, S07–S10 |
| Groups is an array | { groups: { $type: "array" } } | S01–S04, S08–S10 |
| Groups is a String | { groups: { $type: "string" } } | S07 |

This is why **$size: 0 cannot substitute for $eq: null**.

### 6.1. “No Groups Yet” Is a Business Rule

If the application defines “no groups yet” to include empty arrays, null, and missing fields:

~~~javascript
db.students.find({
  $or: [
    { groups: { $size: 0 } },
    { groups: null }
  ]
})
~~~

Result: **S02, S05, S06**. S07's String "mongo" is not counted as “no groups yet”.

In another system, null might mean “not yet synced”, missing might mean “legacy record”, and [] might mean “not enrolled”. Choose filters based on **business definitions**, instead of lumping distinct states together just to shorten a query.

### 6.2. Arrays with at Least One Element

The explicit way is checking length > 0 with $expr as shown earlier. If the schema guarantees groups is always an array, you can leverage the existence of position 0:

~~~javascript
db.students.find({
  "groups.0": { $exists: true }
})
~~~

A non-empty array has a first element at index 0. This is commonly used as a simple idiom to identify arrays with at least one element. However, if the schema allows objects with a `"0"` key or inconsistent structures, use an explicit type-checking expression. Do not use the **groups.0** trick for arbitrary length checks like “at least 10 elements” without evaluating semantics and indexing behavior.

## 7. Nested Arrays and Duplicate Elements

### 7.1. A Subarray Is Just One Element at the Outer Level

S09 has:

~~~javascript
{
  _id: "S09",
  groups: [
    ["java", "mongo"],
    "docker"
  ]
}
~~~

**$size of groups equals 2**. MongoDB does not automatically flatten subarrays. If you need to count all values across multiple levels, define the depth to traverse and use expressions like **$map**, **$reduce**, **$sum**, or design an appropriate pipeline.

For instance, to count elements inside the first element of groups in document S09:

~~~javascript
db.students.aggregate([
  { $match: { _id: "S09" } },
  {
    $project: {
      outerCount: { $size: "$groups" },
      innerCount: { $size: { $arrayElemAt: ["$groups", 0] } }
    }
  }
])
~~~

Specifically for S09, the two values are **2** and **2**. However, **innerCount** is not a general expression for every document: S01's first element is a String, so running it unchanged across the whole collection can throw an error.

### 7.2. Element Count Is Not Distinct Element Count

S08 has groups: ["java", "java"]. **$size returns 2**. If you need the count of **distinct values**, you can use **$setUnion**:

~~~javascript
db.students.aggregate([
  { $match: { _id: "S08" } },
  {
    $project: {
      _id: 1,
      totalCount: { $size: "$groups" },
      distinctCount: {
        $size: { $setUnion: ["$groups", []] }
      }
    }
  }
])
~~~

Result:

~~~javascript
{
  _id: "S08",
  totalCount: 2,
  distinctCount: 1
}
~~~

**$setUnion** uses set semantics to deduplicate elements; it does not preserve output element order and does not recursively flatten nested arrays.

## 8. Combining Element Count with Value Conditions

Check for an array having **exactly two elements and containing the string "mongo"**:

~~~javascript
db.students.find({
  groups: { $size: 2 },
  $and: [
    { groups: "mongo" }
  ]
})
~~~

Result: **S01**. S08 has two elements but does not have "mongo". S09 has a subarray ["java", "mongo"] and "docker"; a subarray is not a top-level string "mongo".

This can be written concisely by combining conditions on the same field:

~~~javascript
db.students.find({
  groups: {
    $size: 2,
    $in: ["mongo"]
  }
})
~~~

If the requirement is **exactly two groups and containing both "java" and "mongo"**:

~~~javascript
db.students.find({
  groups: {
    $size: 2,
    $all: ["java", "mongo"]
  }
})
~~~

Result: **S01**. **$all** requires the listed values to be present; **$size** requires exactly two elements. The two constraints complement each other.

If you need **at least three groups and having "java"**:

~~~javascript
db.students.find({
  groups: "java",
  $expr: {
    $gte: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      3
    ]
  }
})
~~~

Result: **S04 and S10**. The groups: "java" condition checks element values, while $expr checks element count.

For arrays of embedded documents, when multiple conditions must apply to **one item**, **$elemMatch** is typically used. However, $elemMatch only checks whether a matching element exists; it does not count how many elements qualify.

## 9. Counting Elements Matching a Condition with $filter + $size

A more advanced requirement is **“students with at least two scores of 80 or higher”**. This differs from “scores has at least two elements”, because only scores meeting the threshold are counted.

Combine three components:

1. **$filter** creates a new array containing only elements satisfying the condition.
2. **$size expression** computes the number of elements in the filtered array.
3. **$expr** and a comparison operator like $gte identify matching documents.

### 9.1. Computing the Count of Scores >= 80 in Aggregation

~~~javascript
db.students.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      highScoreCount: {
        $size: {
          $filter: {
            input: {
              $cond: [
                { $isArray: "$scores" },
                "$scores",
                []
              ]
            },
            as: "score",
            cond: {
              $gte: ["$$score", 80]
            }
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Meaning:

- **input** is the scores list guaranteed to be an array.
- **as: "score"** names the variable for each element being inspected.
- **"$$score"** references the element variable, unlike **"$scores"** which references the document-level field.
- **cond** selects score values of 80 or above.
- **$size** counts the filtered list.

Examples:

| ID | scores | Scores >= 80 | highScoreCount |
|---|---|---|---:|
| S01 | [80,90,75] | [80,90] | 2 |
| S02 | [60] | [] | 0 |
| S03 | [100,65] | [100] | 1 |
| S04 | [] | [] | 0 |
| S08 | [80,80] | [80,80] | 2 |
| S09 | [95,70,85,55] | [95,85] | 2 |
| S10 | [88,92,77,91,66] | [88,92,91] | 3 |

S05/S06/S07 receive highScoreCount = 0 under the convention of defaulting non-array fields to []. In reality, if these documents need data cleanup, handle them as data errors rather than silently assuming zero scores.

### 9.2. Finding Only Students with at Least Two Scores >= 80

~~~javascript
db.students.find({
  $expr: {
    $gte: [
      {
        $size: {
          $filter: {
            input: {
              $cond: [
                { $isArray: "$scores" },
                "$scores",
                []
              ]
            },
            as: "score",
            cond: { $gte: ["$$score", 80] }
          }
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

Result: **S01, S08, S09, S10**.

Here **$gte inside $filter** compares each score against 80; the **outer $gte** compares the count of qualifying scores against 2. Although identically named, the two operators check two different quantities.

### 9.3. Why Can't $elemMatch Replace Counting?

~~~javascript
db.students.find({
  scores: {
    $elemMatch: { $gte: 80 }
  }
})
~~~

This filter only requires **at least one element** with a score of 80 or higher. For instance, S03 has a single score of 100 so it matches $elemMatch, yet it **does not** satisfy “at least two scores >= 80”.

For “how many elements satisfy the condition” questions, you need **counting**, not merely an existence check.

### 9.4. Counting Embedded Documents Satisfying Multiple Conditions

Suppose an order document is:

~~~javascript
{
  _id: "ORD-001",
  items: [
    { sku: "PEN", quantity: 2, status: "ACTIVE" },
    { sku: "BOOK", quantity: 1, status: "CANCELLED" },
    { sku: "USB", quantity: 5, status: "ACTIVE" }
  ]
}
~~~

Count items having both **status = ACTIVE** and **quantity >= 2**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      eligibleItemCount: {
        $size: {
          $filter: {
            input: {
              $cond: [
                { $isArray: "$items" },
                "$items",
                []
              ]
            },
            as: "item",
            cond: {
              $and: [
                { $eq: ["$$item.status", "ACTIVE"] },
                { $gte: ["$$item.quantity", 2] }
              ]
            }
          }
        }
      }
    }
  }
])
~~~

The result for the sample document is **eligibleItemCount = 2** because PEN and USB satisfy both conditions. BOOK is excluded. If the items array can contain schema-invalid elements or string quantities, the application should normalize or type-check before applying business expressions.

## 10. Comparing Lengths of Two Arrays in One Document

Suppose each student has **groups** and **scores**. To find documents where **number of groups exceeds number of scores**, the sizes being compared vary per document; this cannot be expressed with a fixed-N $size query operator alone.

~~~javascript
db.students.find({
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      {
        $size: {
          $cond: [
            { $isArray: "$scores" },
            "$scores",
            []
          ]
        }
      }
    ]
  }
}).sort({ _id: 1 })
~~~

Result: **S04**, because groups has 3 elements and scores has 0. For the remaining documents, groupCount is not greater than scoreCount. The expression treats non-array fields as [] under the chosen policy.

If the requirement is to select only documents where **both fields are arrays**, add conditions:

~~~javascript
db.students.find({
  $expr: {
    $and: [
      { $isArray: "$groups" },
      { $isArray: "$scores" },
      {
        $gt: [
          {
            $size: {
              $cond: [{ $isArray: "$groups" }, "$groups", []]
            }
          },
          {
            $size: {
              $cond: [{ $isArray: "$scores" }, "$scores", []]
            }
          }
        ]
      }
    ]
  }
})
~~~

We still guard each $size so the expression does not depend on assuming condition branches always evaluate strictly left-to-right.

## 11. Aggregation Pipeline: Compute First, Then Filter

Instead of cramming everything into find/$expr, you can use **$set** to compute an intermediate field and then **$match** on that computed field:

~~~javascript
db.students.aggregate([
  {
    $set: {
      computedGroupCount: {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      }
    }
  },
  {
    $match: {
      computedGroupCount: { $gte: 2 }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      computedGroupCount: 1
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Results are **S01, S04, S08, S09, S10**, along with **computedGroupCount** for the application to display.

Note: **$set here is a read-only aggregation pipeline stage**. It creates a field on documents flowing through the pipeline and does not update documents stored in the collection. Persisting results to the database requires an explicit update operation or write mechanism.

The advantage of a pipeline is splitting work into clear steps:

~~~text
Input document
    |
    v
$set computedGroupCount = length of groups
    |
    v
$match computedGroupCount >= 2
    |
    v
$project output fields
~~~

This is also convenient when computing multiple array statistics—such as totalCount, highScoreCount, and distinctCount—for comparison or sorting.

## 12. Understanding Index Limitations of $size

**The $size query operator is not directly supported by indexes to locate documents with an array of exactly N elements.** A multikey index on an array primarily indexes element values, rather than indexing element counts as a corresponding query key.

Example:

~~~javascript
db.students.createIndex({ groups: 1 })

db.students.find({
  groups: { $size: 2 }
}).explain("executionStats")
~~~

An index on groups does not allow MongoDB to locate all documents of length 2 without examining candidate documents. Similarly, **$expr + $size** computes length from document values and does not automatically become an indexed range query on counts.

### 12.1. Combining with Another Selective Condition

If the collection has a **department** field, you can create an index:

~~~javascript
db.students.createIndex({ department: 1 })

db.students.find({
  department: "engineering",
  groups: { $size: 2 }
})
~~~

The department condition can narrow the candidate documents to examine. The $size predicate still has to be evaluated. Actual effectiveness depends on data distribution, selectivity, and the query planner.

### 12.2. Using explain() to Observe Behavior

~~~javascript
db.students.find({
  groups: { $size: 2 }
}).explain("executionStats")
~~~

Fields to inspect:

| Field | Meaning |
|---|---|
| winningPlan | Chosen execution plan |
| totalKeysExamined | Number of index entries scanned |
| totalDocsExamined | Number of documents read/examined |
| nReturned | Number of documents returned |

On a collection with only 10 documents, a collection scan is completely reasonable. Measure on data close to your real workload before deciding on an optimization strategy.

## 13. Storing a Derived Count Field When Filtering by Size Frequently

If an application has millions of documents and frequently filters for “at least five groups”, one optimization is **storing groupCount** alongside groups:

~~~javascript
{
  _id: "S11",
  name: "Quân",
  groups: ["java", "mongo", "docker"],
  groupCount: 3
}
~~~

Then you can use a normal numeric query:

~~~javascript
db.students.createIndex({ groupCount: 1 })

db.students.find({
  groupCount: { $gte: 3 }
})
~~~

If filtering frequently by department and group count together, consider a compound index:

~~~javascript
db.students.createIndex({
  department: 1,
  groupCount: 1
})

db.students.find({
  department: "engineering",
  groupCount: { $gte: 3 }
})
~~~

Indexes and field ordering should be driven by actual queries, data distribution, and sort requirements; not every system needs a new index for groupCount.

### 13.1. Risk of Derived Data Drift

**groupCount must equal the actual length of groups**. If the application appends or removes elements but forgets to update the counter, queries on groupCount will return wrong results.

Risk example:

~~~javascript
// Modifying only the array without updating groupCount
// leaves the document inconsistent.
db.students.updateOne(
  { _id: "S11" },
  { $push: { groups: "redis" } }
)
~~~

After the operation above, groups has length 4, while groupCount may still be 3. MongoDB does not know groupCount is a derived field and will not keep the two fields synchronized unless the application designs an update mechanism.

### 13.2. Updating the Array and Recomputing Length in an Update Pipeline

An example appending "redis" to groups and recomputing groupCount:

~~~javascript
db.students.updateOne(
  {
    _id: "S01",
    groups: { $type: "array" }
  },
  [
    {
      $set: {
        groups: {
          $concatArrays: ["$groups", ["redis"]]
        }
      }
    },
    {
      $set: {
        groupCount: { $size: "$groups" }
      }
    }
  ]
)
~~~

In an **aggregation pipeline update**, stages execute in order. The first stage updates groups; the second stage counts the updated groups value. With S01's initial data, groups has 3 elements after the operation and groupCount equals 3 as well.

A single document is updated atomically by one update command, yet the application still needs to handle deduplication on add, removals, replacements, and concurrent operations. The example command blindly appends an element, so running it again adds "redis" a second time. If **set** semantics without duplicates are needed, use an appropriate deduplicating mechanism and recompute count from the actual array state rather than blindly incrementing a counter.

### 13.3. Detecting Mismatched groupCount

Once a count field exists, you can compare it against actual $size:

~~~javascript
db.students.find({
  $expr: {
    $ne: [
      "$groupCount",
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      }
    ]
  }
})
~~~

If the collection contains legacy documents that do not yet have groupCount, the expression may also select unbackfilled documents. Define a migration policy before treating every match as a logic bug. For mistyped data, fix the schema instead of treating a String field as an empty array.

**In summary**, a derived count field trades extra write/maintenance overhead for indexed size filtering. It is a design option, not a mandatory replacement for $size.

## 14. Protecting Arrays with Schema Validation

When skill groups are designed to always be an array, enforce this at the write layer to prevent cases like groups: null or groups: "mongo". MongoDB supports validators using **$jsonSchema** and **bsonType**.

Example creating a new collection:

~~~javascript
db.createCollection("validatedStudents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "groups"],
      properties: {
        name: {
          bsonType: "string",
          minLength: 1
        },
        groups: {
          bsonType: "array",
          items: {
            bsonType: "string"
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

This collection requires groups to be a **BSON Array** whose elements are Strings. It allows [] but rejects null, Strings, or arrays containing subarrays. To require at least one element, add **minItems: 1**; to cap at five elements, add **maxItems: 5**:

~~~javascript
groups: {
  bsonType: "array",
  minItems: 1,
  maxItems: 5,
  items: { bsonType: "string" }
}
~~~

Distinguish:

| Mechanism | Question It Answers |
|---|---|
| $size query operator | On read: does the field currently have exactly N elements? |
| $size aggregation expression | During calculation: how many elements does the field have? |
| $jsonSchema minItems/maxItems | On write: is the element count within allowed bounds? |
| bsonType: "array" | On write: does the field have exact type Array? |
| Count field groupCount + index | On frequent reads: can we query element count via an index? |

Adding a validator to a collection that already contains data does not automatically convert String/null documents into arrays. You need a plan to clean existing data, update writers, and adjust the validator accordingly.

## 15. Java MongoDB Sync Driver: $size Queries

In a Java application with a compatible **mongodb-driver-sync** dependency, the MongoDB Driver provides **Filters.size()** to create exact-length filters.

### 15.1. Finding Students with Exactly Two Groups

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class FindStudentsWithTwoGroups {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson filter = Filters.size("groups", 2);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> students = client
                    .getDatabase("array_size_lab")
                    .getCollection("students");

            for (Document student : students.find(filter)
                    .sort(new Document("_id", 1))) {
                System.out.println(student.toJson());
            }
        }
    }
}
~~~

**Filters.size("groups", 2)** is equivalent to:

~~~javascript
{ groups: { $size: 2 } }
~~~

On the un-updated Section 2 dataset, the result is **S01, S08, S09**.

### 15.2. Querying More Than Two Groups with $expr in Java

MongoDB filters can be built as nested **Document** objects. Example:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.Collections;

public class FindStudentsWithManyGroups {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson arrayOrEmpty = new Document(
                "$cond",
                Arrays.asList(
                        new Document("$isArray", "$groups"),
                        "$groups",
                        Collections.emptyList()
                )
        );

        Bson lengthExpr = new Document("$size", arrayOrEmpty);

        Bson filter = new Document(
                "$expr",
                new Document("$gt", Arrays.asList(lengthExpr, 2))
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> students = client
                    .getDatabase("array_size_lab")
                    .getCollection("students");

            for (Document student : students.find(filter)
                    .sort(new Document("_id", 1))) {
                System.out.println(student.getString("_id"));
            }
        }
    }
}
~~~

This Java structure corresponds to:

~~~javascript
{
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}
~~~

This Java snippet demonstrates how to construct the BSON filter. In production code, name and reuse expressions intentionally rather than duplicating long Document trees across repository methods.

### 15.3. Why Validate the Size Parameter?

Suppose an API receives **groupCount** from a query parameter:

~~~text
GET /students?groupCount=2
~~~

HTTP passes values as strings; before calling Filters.size(), the application must parse it into an integer and verify **groupCount >= 0**:

~~~java
if (groupCount < 0) {
    throw new IllegalArgumentException(
            "groupCount must be non-negative"
    );
}

Bson filter = Filters.size("groups", groupCount);
~~~

Excessively large or invalid N values must also be handled per API rules. Never pass a raw string **"2"** into $size expecting the database to coerce it into a count.

## 16. Spring Data MongoDB: Criteria.size()

In Spring Data MongoDB, **Criteria.where("groups").size(2)** builds the $size query operator condition.

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class StudentQueryService {
    private final MongoTemplate mongoTemplate;

    public StudentQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findExactlyTwoGroups() {
        Query query = new Query(
                Criteria.where("groups").size(2)
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "students"
        );
    }
}
~~~

This example assumes MongoTemplate points to the **array_size_lab** database and documents are mapped per application configuration. The filter still selects documents whose groups array has exactly two elements.

**Do not write**:

~~~java
// Does NOT mean groups has length greater than 2.
Criteria.where("groups").size(2).gt(2);
~~~

size(2) produces the $size query operator for length **exactly 2**; gt(2) does not take the result of size() as its operand. For “more than 2”, use an $expr expression as shown in the MongoDB Sync Driver example or the corresponding aggregation APIs for your Spring Data MongoDB version.

## 17. Product Line Count vs. Total Units

Given the document:

~~~javascript
{
  _id: "ORDER-100",
  items: [
    { sku: "PEN", quantity: 2 },
    { sku: "BOOK", quantity: 4 }
  ]
}
~~~

**$size of items = 2** because there are two line items. However, total quantity = **6**. To compute total units, combine **$map** and **$sum**:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ORDER-100" } },
  {
    $project: {
      _id: 1,
      lineCount: { $size: "$items" },
      unitCount: {
        $sum: {
          $map: {
            input: "$items",
            as: "item",
            in: "$$item.quantity"
          }
        }
      }
    }
  }
])
~~~

For the valid example document, the output is:

~~~javascript
{
  _id: "ORDER-100",
  lineCount: 2,
  unitCount: 6
}
~~~

This expression requires items to be an array of objects with numeric quantities. For inconsistent data, add type checks or normalization steps to avoid aggregation errors.

## 18. Common Errors and How to Resolve Them

| Symptom | Cause | Resolution |
|---|---|---|
| $size: 0 misses documents with groups: null | Null is not an empty array | Include null/missing conditions if business rules allow |
| $size: 2 returns ["java", "java"] | $size counts elements, not distinct values | Use $setUnion + $size when distinctCount is needed |
| $size: 2 returns an array containing a subarray | A subarray counts as one outer element | Clarify which level to count or traverse deeper with expressions |
| $size: { $gt: 2 } throws an error | Query $size accepts only an exact integer | Use $expr and aggregation $size |
| $size expression errors when field is null | Aggregation $size requires an array argument | Wrap with $ifNull or $cond + $isArray |
| $ifNull still errors when field is String | $ifNull only replaces null/missing | Guard type with $isArray |
| $elemMatch selects a document with only one qualifying score | $elemMatch checks existence, not count of matches | Use $filter + $size |
| Putting $gt alongside query $size yields unexpected results | $gt does not compare the count output | Place the comparison inside $expr |
| Adding an index on groups still scans many documents | Multikey indexes do not directly index array length | Combine with selective predicates, or maintain an indexed count field |
| groupCount drifts from groups | Array was updated without syncing the counter | Use atomic pipeline updates and verification/migration jobs |
| Array has two items but six total units are needed | $size counts item lines, not quantity sums | Sum the quantity field across items |
| Query returns the right set in varying order | Missing sort() | Sort by a business key |

### 18.1. Distinguishing Filter Syntax from Aggregation Expression Syntax

Same **$size** keyword, yet not interchangeable:

~~~javascript
// Filter: groups has exactly 2 elements.
db.students.find({
  groups: { $size: 2 }
})

// Aggregation: outputs element count.
db.students.aggregate([
  { $match: { groups: { $type: "array" } } },
  {
    $project: {
      groupCount: { $size: "$groups" }
    }
  }
])

// Filter with expression: groups has more than 2 elements.
db.students.find({
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [{ $isArray: "$groups" }, "$groups", []]
        }
      },
      2
    ]
  }
})
~~~

Do not assume every place where **$size** can appear behaves identically or handles non-array values the same way.

### 18.2. Never Use Array Value Comparisons to Infer Length

Example:

~~~javascript
db.students.find({
  groups: { $gt: 2 }
})
~~~

This is **not** a filter for “groups has more than two elements”. $gt is a value comparison operator under MongoDB query semantics; on an array field it evaluates element-matching semantics. To compare length, compute **$size of the array** first.

### 18.3. Detecting Mistyped Data Fields

A collection may simultaneously contain:

~~~javascript
{ groups: [] }
{ groups: "java" }
{ groups: null }
~~~

Find schema-violating records:

~~~javascript
db.students.find({
  $expr: {
    $not: [
      { $isArray: "$groups" }
    ]
  }
})
~~~

On the sample data, records where groups is not an array are **S05, S06, S07**. Whether to convert them to [] or fix them from upstream data sources depends on business requirements.

Another approach is using aggregation to inspect BSON types:

~~~javascript
db.students.aggregate([
  {
    $project: {
      _id: 1,
      groupsType: { $type: "$groups" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

The output can display **array**, **null**, **missing**, **string**. This helps determine cleanup steps before enabling a validator.

## 19. Practice Exercises

The following exercises use the initial **students** collection, before running the update example that modifies S01's groups.

### Exercise 1. Exact Size Checks

Write queries for:

1. Students with **0 groups**.
2. Students with **2 groups**.
3. Students with **4 groups**.

Answer:

~~~javascript
// 0 groups
db.students.find({ groups: { $size: 0 } })

// 2 groups
db.students.find({ groups: { $size: 2 } })

// 4 groups
db.students.find({ groups: { $size: 4 } })
~~~

The results are **S02**, **S01/S08/S09**, and **S10** respectively. Explain why S08 (with duplicate values) and S09 (with a subarray) both satisfy $size: 2.

### Exercise 2. Choosing Query Operator vs. Expression

Requirements:

- Exactly 3 groups.
- More than 3 groups.
- At least 3 groups.
- At most 3 groups.

Select the appropriate syntax for each requirement. Hint:

~~~javascript
// Exactly 3: query operator.
{ groups: { $size: 3 } }

// More than 3: expression placed inside $expr.
{
  $gt: [
    { $size: "$groups" },
    3
  ]
}
~~~

The second expression is only safe when groups is guaranteed to be an array. On mixed data, use **$cond + $isArray**. The remaining requirements use **$gte** or **$lte** on the $size expression output with matching boundary semantics.

### Exercise 3. Distinguishing Empty Arrays and Unset Values

Identify IDs for:

1. groups is an empty array.
2. groups is null or does not exist.
3. groups is a String.
4. groups is a non-empty array.

Hint:

~~~javascript
{ groups: { $size: 0 } }
{ groups: null }
{ groups: { $type: "string" } }
{
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [{ $isArray: "$groups" }, "$groups", []]
        }
      },
      0
    ]
  }
}
~~~

Results respectively: **S02**; **S05, S06**; **S07**; **S01, S03, S04, S08, S09, S10**.

### Exercise 4. Counting High Scores

Find students with **at least two scores >= 80**.

Answer:

~~~javascript
db.students.find({
  $expr: {
    $gte: [
      {
        $size: {
          $filter: {
            input: {
              $cond: [{ $isArray: "$scores" }, "$scores", []]
            },
            as: "score",
            cond: { $gte: ["$$score", 80] }
          }
        }
      },
      2
    ]
  }
})
~~~

Result: **S01, S08, S09, S10**. Why is using only $elemMatch with $gte: 80 insufficient? Because it only requires **one** element to meet the threshold.

### Exercise 5. Comparing Two Arrays in One Document

Write a filter to find students with **more groups than recorded scores**.

Hint: use **$expr: { $gt: [...] }** with both sides as $size expressions guarded by $isArray. On the initial data, the result is **S04**.

### Exercise 6. Array Length vs. Distinct Element Count

For S08:

~~~javascript
{ groups: ["java", "java"] }
~~~

Determine:

- Element count from $size.
- Element count from $size after applying $setUnion.
- Why the two numbers differ and which business cases need distinctCount.

Answer: **2** and **1**. If group lists must not have duplicates, enforce deduplication rules on write rather than only fixing counts at query time.

### Exercise 7. Performance Considerations

A collection contains several million students. An API routinely filters by department and requires at least five groups.

Propose:

1. A query using **department** and **$expr + $size** before changing the schema.
2. A query using **department** and a count field **groupCount >= 5**.
3. An index likely suited to the second query.
4. How to ensure groupCount stays updated in sync whenever groups changes.

Guidance: consider the index **{ department: 1, groupCount: 1 }**, but measure with explain() and keep groupCount consistent so performance never comes at the cost of wrong results.

### Exercise 8. Line Item Count vs. Total Quantity

Consider:

~~~javascript
{
  orderCode: "O-200",
  items: [
    { sku: "A", quantity: 2 },
    { sku: "B", quantity: 4 },
    { sku: "C", quantity: 1 }
  ]
}
~~~

Answer: **What is $size of items? What is the total quantity?** To find orders with more than five product units, is using only $size correct?

Answer: **3 line items**, **7 units**; comparing total units requires summing quantity, not just counting subdocuments in the array.

## 20. Choosing the Right Tool for Each Requirement

| Question | Primary Tool |
|---|---|
| Array has exactly N elements? | Query operator $size |
| Array has more/fewer than N elements? | $expr + aggregation $size + comparison operator |
| Array A is longer than array B? | $expr with two $size expressions |
| At least K elements satisfy a condition? | $filter + $size + $gte |
| How many distinct elements? | $setUnion + $size |
| Accept only real arrays, rejecting null/String? | $isArray, $type, or schema validation |
| Prevent writing overly long arrays? | $jsonSchema with maxItems |
| Need frequent size filtering backed by an index? | Consistently updated derived count field |

**Rule of thumb:** **$size in a filter** matches **exact element count**; **$size in an aggregation expression** produces a **number for calculations or comparisons**. Combining them with type checks and proper data-handling policies ensures accurate array queries, avoids confusing empty arrays, null, missing fields, and mistyped values, and supports performance optimization as the system scales.
