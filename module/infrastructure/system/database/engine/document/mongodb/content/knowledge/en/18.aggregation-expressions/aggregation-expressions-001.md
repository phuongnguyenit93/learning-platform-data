# Field References, System Variables, and Variable Scope with $let in MongoDB

In the **MongoDB Aggregation Framework**, expressions can retrieve data from a field of the document being processed, read **system variables**, or use **local variables** declared by an operator. The syntax differs by only a single character, yet the meaning changes completely:

- **"$status"** is a *field path*, retrieving the value of the `status` field in the current document context.
- **"$$ROOT"** is a reference to the `ROOT` system variable, which holds the document passed into the expression at the current stage.
- **"$$item.price"** is the `price` field of the `item` variable's value, typically created in `$map` or `$filter`.
- **$let** assigns names to intermediate results, allowing the expression inside **in** to use them via the **$$variableName** syntax.

Understanding these references properly helps avoid wrong data bugs, undefined variable errors, confusing the root document with an array element, and variable scope mistakes when building multi-layered aggregation pipelines.

This lesson focuses on **field references, system variables, and variable scope with $let**, while illustrating how those concepts work together with **$project**, **$set**, **$map**, **$filter**, **$reduce**, **$lookup**, and **$expr**.

## 1. Distinguishing Field Paths and Variable References

Suppose a document is stored as follows:

~~~javascript
{
  _id: "O-1001",
  customerId: "C-01",
  status: "PAID",
  shipping: {
    city: "HCM",
    fee: NumberDecimal("15000.00")
  },
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPrice: NumberDecimal("100000.00")
    }
  ]
}
~~~

In an aggregation expression, you can reference:

| Expression | Data Source |
| --- | --- |
| **"$status"** | The status field of the current document |
| **"$shipping.city"** | The city field inside the shipping embedded document |
| **"$$ROOT"** | The entire input document in the stage's context |
| **"$$ROOT.status"** | The status field of the ROOT document |
| **"$$CURRENT.status"** | The status field of the CURRENT document |
| **"$$item"** | The value of the item variable declared in the appropriate scope |
| **"$$item.unitPrice"** | The unitPrice field belonging to the document held in the item variable |
| **{ $literal: "$status" }** | The literal string "$status" |

The **single $** syntax indicates a *field path* when the value is an expression string; the **double $$** syntax indicates a *variable reference*. The two forms are not interchangeable.

Example:

~~~javascript
{
  $map: {
    input: "$items",
    as: "item",
    in: "$$item.unitPrice"
  }
}
~~~

The **item** variable is created by `$map` for each element. Replacing **$$item.unitPrice** with **$item.unitPrice** would cause MongoDB to look up the field path **item.unitPrice** on the current context document instead of reading the array element variable.

### 1.1. Aggregation Expressions Differ from JavaScript

In `mongosh`, the string `"$status"` can be passed to MongoDB as part of a pipeline:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      state: "$status"
    }
  }
]);
~~~

The MongoDB server interprets that string as a field reference. In contrast:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      state: {
        $literal: "$status"
      }
    }
  }
]);
~~~

creates a `state` field containing the **literal string "$status"**, not the `PAID`/`PENDING` value from the document.

The JavaScript author constructs an object describing the pipeline, while MongoDB **evaluates aggregation expressions on the server**. JavaScript variables in `mongosh` do not automatically become MongoDB aggregation variables.

## 2. Preparing the Practice Dataset

Use `mongosh` and a dedicated database **aggregation_variables_lab**. The `drop` commands in this example should only be run in a test environment because they delete the entire collection.

~~~javascript
use aggregation_variables_lab

db.orders.drop();

db.orders.insertMany([
  {
    _id: "O-1001",
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    discountRate: NumberDecimal("0.10"),
    shippingFee: NumberDecimal("15000.00"),
    shipping: { city: "HCM", method: "STANDARD" },
    items: [
      {
        sku: "BOOK-01",
        quantity: 2,
        unitPrice: NumberDecimal("100000.00")
      },
      {
        sku: "PEN-01",
        quantity: 1,
        unitPrice: NumberDecimal("50000.00")
      }
    ]
  },
  {
    _id: "O-1002",
    customerId: "C-02",
    status: "PENDING",
    createdAt: ISODate("2026-11-02T10:00:00Z"),
    discountRate: NumberDecimal("0.00"),
    shippingFee: NumberDecimal("0.00"),
    shipping: { city: "HN", method: "PICKUP" },
    items: [
      {
        sku: "BOOK-02",
        quantity: 1,
        unitPrice: NumberDecimal("300000.00")
      }
    ]
  },
  {
    _id: "O-1003",
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-11-03T11:00:00Z"),
    discountRate: NumberDecimal("0.05"),
    shippingFee: NumberDecimal("12000.00"),
    shipping: { city: "DN", method: "STANDARD" },
    items: [
      {
        sku: "PEN-02",
        quantity: 3,
        unitPrice: NumberDecimal("40000.00")
      }
    ]
  },
  {
    _id: "O-1004",
    customerId: "C-03",
    status: "DRAFT",
    createdAt: ISODate("2026-11-04T12:00:00Z"),
    discountRate: NumberDecimal("0.00"),
    shippingFee: NumberDecimal("0.00"),
    shipping: { city: "HCM", method: "STANDARD" },
    items: []
  }
]);

db.customers.drop();

db.customers.insertMany([
  { _id: "C-01", name: "Nguyễn An", tier: "GOLD" },
  { _id: "C-02", name: "Trần Bình", tier: "STANDARD" },
  { _id: "C-03", name: "Lê Chi", tier: "STANDARD" }
]);
~~~

With the dataset above, the order total is determined by:

~~~text
gross = sum of (quantity × unitPrice) for each item
discountAmount = gross × discountRate
payable = gross - discountAmount + shippingFee
~~~

Expected results with no other incurred data:

| Order | gross | discountAmount | shippingFee | payable |
| --- | ---: | ---: | ---: | ---: |
| O-1001 | 250,000 | 25,000 | 15,000 | 240,000 |
| O-1002 | 300,000 | 0 | 0 | 300,000 |
| O-1003 | 120,000 | 6,000 | 12,000 | 126,000 |
| O-1004 | 0 | 0 | 0 | 0 |

The monetary examples use **NumberDecimal** to illustrate the Decimal128 type. In a real application, rounding rules, currency, and business constraints must be standardized.

## 3. Referencing Fields with a Single $

### 3.1. Top-Level Fields

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      orderStatus: "$status",
      customer: "$customerId"
    }
  }
]);
~~~

In a `$project` stage:

- **_id: 1** is how you request keeping the `_id` field.
- **orderStatus: "$status"** is an expression retrieving the `status` field.
- **customer: "$customerId"** is an expression retrieving the `customerId` field.

Do not treat the projection value `1` and the string `"$status"` as the same kind of syntax.

### 3.2. Nested Fields

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      city: "$shipping.city",
      deliveryMethod: "$shipping.method"
    }
  }
]);
~~~

The dot in **"$shipping.city"** represents traversing into the `shipping` embedded document and retrieving the `city` field.

### 3.3. Fields Inside an Array

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      quantities: "$items.quantity",
      prices: "$items.unitPrice"
    }
  }
]);
~~~

For O-1001, these expressions can produce the `quantities` list **[2, 1]** and the corresponding `prices`. However, the `prices` list is **not** the line-by-line total; to compute `quantity × unitPrice`, you need a per-element expression such as **$map** or **$reduce**.

### 3.4. Missing Fields vs. Fields with null

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      noteOrDefault: {
        $ifNull: [
          "$note",
          "No note"
        ]
      }
    }
  }
]);
~~~

**$ifNull** is useful when a field is missing or has a `null` value. However, it does not automatically handle every wrong data type. For example, a field that is supposed to be an array but is actually a string can still cause errors in operators that expect an array.

## 4. Variables Using Double $$

Variables are referenced as follows:

~~~text
$$name
$$name.child
$$name.child.deepField
~~~

The **name** part must correspond to a validly declared variable or an available system variable.

Common sources of variable declarations:

- **$let.vars** creates variables inside the `in` expression.
- **$map.as** creates an array element variable inside `in`.
- **$filter.as** creates an array element variable inside `cond`.
- **$reduce** provides two context variables: **$$value** and **$$this**.
- **$lookup.let** creates variables for use by the pipeline on the joined collection.
- The **let** option of certain aggregation commands allows passing command-level variables.
- **$$ROOT**, **$$CURRENT**, **$$NOW**, and **$$REMOVE** are system variables with dedicated semantics.

For example, the declared variable name does not include two dollar signs:

~~~javascript
{
  $map: {
    input: "$items",
    as: "line",
    in: "$$line.sku"
  }
}
~~~

**as: "line"** defines the variable. **"$$line.sku"** is how the variable is used.

### 4.1. Variables Do Not Exist Automatically

~~~javascript
db.orders.aggregate([
  {
    $project: {
      result: "$$unknownVariable"
    }
  }
]);
~~~

If **unknownVariable** is not declared in a valid scope, MongoDB may raise an error such as **Use of undefined variable**.

### 4.2. Variable Names Should Be Meaningful

User-declared names follow MongoDB variable naming rules, typically starting with a lowercase ASCII letter or valid non-ASCII character; they may contain letters, digits, and underscores according to supported rules.

Use names such as **line**, **gross**, **taxRate**, and **customerKey** instead of overly short names in deeply nested pipelines. Avoid naming variables in ways easily confused with **ROOT**, **CURRENT**, **NOW**, and other system variables.

## 5. $$ROOT: The Document in the Stage Context

**$$ROOT** references the document currently acting as the root of the expression in the executing stage.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      originalAtThisStage: "$$ROOT"
    }
  }
]);
~~~

At this stage, **originalAtThisStage** can contain a copy of the order document passed into `$project`.

However, **ROOT is not guaranteed to be the original document of the entire pipeline**. After structure-changing stages such as `$project`, `$set`, `$replaceRoot`, or `$unwind`, the document entering the next stage may already be different.

Example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      status: 1
    }
  },
  {
    $project: {
      currentRoot: "$$ROOT"
    }
  }
]);
~~~

In the second `$project`, `ROOT` is the document produced by the first projection; it does not automatically restore `customerId`, `shipping`, or `items` that were excluded.

### 5.1. $$ROOT Inside $map

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            statusOfOrder: "$$ROOT.status",
            skuOfItem: "$$item.sku",
            quantityOfItem: "$$item.quantity"
          }
        }
      }
    }
  }
]);
~~~

The two variables have different contexts:

~~~text
$$ROOT.status   -> status of the order at the stage
$$item.sku      -> sku of the items element being iterated
~~~

This is why using **$$item** properly instead of **$item** is especially critical in nested expressions.

## 6. $$CURRENT: Starting Point for Field References

In many typical expressions:

~~~text
"$status"
~~~

is equivalent to referencing:

~~~text
"$$CURRENT.status"
~~~

when **CURRENT** points to the current document.

Example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      fieldStatus: "$status",
      currentStatus: "$$CURRENT.status",
      rootStatus: "$$ROOT.status"
    }
  }
]);
~~~

In this context, all three output fields have the same `status`.

**CURRENT and ROOT are not conceptually synonymous.** `CURRENT` is the context used to resolve paths starting with a single `$`, and MongoDB has mechanisms to change the `CURRENT` context in appropriate expressions. `ROOT` is the root document at the current stage. You should not assume the two variables always hold the same value in every context.

## 7. System Variables Overview

Common system variables:

| Variable | Meaning | Use Case |
| --- | --- | --- |
| **$$ROOT** | Root document in the current stage | $project, $group, nested expressions |
| **$$CURRENT** | Current context for $field | Field-reading expressions |
| **$$NOW** | Current date/time value of type BSON Date, stable within the same pipeline | Timestamps, due dates |
| **$$CLUSTER_TIME** | Cluster time of type BSON Timestamp when supported | Cluster context |
| **$$REMOVE** | Special value to omit an output field in supported contexts | $project, $addFields/$set |
| **$$KEEP** | Keep document/subtree | $redact |
| **$$PRUNE** | Remove document/subtree | $redact |
| **$$DESCEND** | Continue processing sub-structures | $redact |
| **$$SEARCH_META** | Search metadata from Search features when supported | MongoDB Search/Atlas Search |
| **$$USER_ROLES** | Current user's roles in supported environments/versions | Certain policies/redaction |

Some variables depend on the **MongoDB version, deployment type, and stage**. For example, `$$CLUSTER_TIME` has cluster-level semantics and is not a substitute for BSON Date; `$$SEARCH_META` depends on the Search feature.

## 8. $$NOW in Date and Time Calculations

A common expression is checking how long an order has existed:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      createdAt: 1,
      observedAt: "$$NOW",
      ageMillis: {
        $subtract: [
          "$$NOW",
          "$createdAt"
        ]
      }
    }
  }
]);
~~~

Subtracting two BSON Date values returns the time difference in milliseconds.

### 8.1. $$NOW Is Stable Within a Single Pipeline Execution

MongoDB keeps the value of **$$NOW** consistent across stages and documents within a single pipeline execution according to the corresponding supported mechanism. It is not arbitrarily recomputed per document.

~~~javascript
db.orders.aggregate([
  {
    $set: {
      observedAt: "$$NOW"
    }
  },
  {
    $project: {
      observedAt: 1,
      samePipelineNow: "$$NOW"
    }
  }
]);
~~~

Within a single pipeline run, both fields above draw from the same `NOW` value.

### 8.2. $$NOW Differs from new Date() in mongosh

~~~javascript
const timestampFromClient = new Date();
~~~

This line is evaluated in the `mongosh` JavaScript environment before the value is sent to the server. In contrast, **"$$NOW"** is resolved by the server as a system variable in an aggregation expression.

When a fixed point in time chosen by business logic is needed, such as a month-end cutoff, a fixed BSON Date can be passed instead of relying on `NOW`. The time source and time zone must be clearly defined.

### 8.3. $dateDiff and Timezone

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      daysOld: {
        $dateDiff: {
          startDate: "$createdAt",
          endDate: "$$NOW",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

`$dateDiff` counts according to day unit and time zone rules, which is not always equivalent to dividing milliseconds by 86,400,000. In real applications, the appropriate unit and timezone must be chosen for the business domain.

## 9. $$REMOVE: Conditionally Omitting Fields

**$$REMOVE** is a special value that can be used to exclude a field from the output of supported stages.

For example, showing shipping details only for `PAID` orders:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      shippingWhenPaid: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "$shipping",
          "$$REMOVE"
        ]
      }
    }
  }
]);
~~~

For `PAID` orders, the **shippingWhenPaid** field appears. For `PENDING`/`DRAFT` orders, the field is omitted from the result, **not assigned null**.

### 9.1. Comparing REMOVE and null

~~~javascript
// Assign null when the condition is false:
{
  $cond: [
    { $eq: ["$status", "PAID"] },
    "$shipping",
    null
  ]
}
~~~

This approach keeps the output field with a `null` value. Use **"$$REMOVE"** to exclude the field when that is the intent.

### 9.2. Using in an Update Pipeline

~~~javascript
db.orders.updateOne(
  { _id: "O-1004" },
  [
    {
      $set: {
        optionalNote: {
          $cond: [
            { $eq: ["$status", "PAID"] },
            "Paid",
            "$$REMOVE"
          ]
        }
      }
    }
  ]
);
~~~

Here **$set** is an aggregation stage inside an **update pipeline** (the argument is an array). It differs from the **$set update operator** in a standard update document. `$$REMOVE` is an expression evaluated by the server.

## 10. Variables Related to $redact and Clusters

In **$redact**, the following system values control how the document tree is processed:

~~~text
$$KEEP     -> keep the current branch
$$PRUNE    -> remove the current branch
$$DESCEND  -> evaluate deeper into child branches
~~~

Formal illustrative example:

~~~javascript
db.records.aggregate([
  {
    $redact: {
      $cond: [
        { $eq: ["$accessLevel", "PUBLIC"] },
        "$$KEEP",
        "$$DESCEND"
      ]
    }
  }
]);
~~~

This snippet **is not a complete security policy**. You must clearly define how unlabeled data, access permission tiers, and missing-field cases are handled before using `$redact` for information control.

**$$CLUSTER_TIME** has the BSON Timestamp type and semantics for cluster coordination. If you need to calculate order age, display schedules, or determine overdue dates, **$$NOW** and standard BSON Dates are more appropriate; do not use `$$CLUSTER_TIME` directly in place of a Date.

## 11. The $let Operator: Syntax and Purpose

**$let is an expression operator**, not a standalone aggregation pipeline stage.

Syntax:

~~~javascript
{
  $let: {
    vars: {
      variableA: expressionA,
      variableB: expressionB
    },
    in: expressionUsingVariables
  }
}
~~~

Where:

- **vars** is a document declaring local variables and the expressions that compute their values.
- **in** is an expression that can read those declared variables via **$$variableA** and **$$variableB**.
- The scope of the variables is limited to the **in** expression of the corresponding `$let`.
- Variable assignment expressions in **vars** are evaluated in the **scope outside $let**, not in the scope of sibling variables just declared.

Simple example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      result: {
        $let: {
          vars: {
            base: 120,
            bonus: 30
          },
          in: {
            $add: [
              "$$base",
              "$$bonus"
            ]
          }
        }
      }
    }
  }
]);
~~~

Each document gets `result` = **150**.

### 11.1. Cannot Place $let Directly as a Stage

Incorrect:

~~~javascript
db.orders.aggregate([
  {
    $let: {
      vars: { x: 1 },
      in: "$$x"
    }
  }
]);
~~~

The top-level pipeline requires valid stages. The right way is to place `$let` inside an expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      value: {
        $let: {
          vars: { x: 1 },
          in: "$$x"
        }
      }
    }
  }
]);
~~~

### 11.2. Why Use $let?

`$let` is useful when an expression:

- Has multiple intermediate values that need meaningful names.
- Needs to reuse a value across multiple branches of the **in** expression.
- Could easily confuse field paths with array element variables.
- Has multi-step calculations that need to be organized by scope.
- Needs to express clearly named logic so maintainers can read it easily.

`$let` does not automatically speed up every pipeline. Performance still depends on the data, computations, and MongoDB's optimizer.

## 12. Important Rule: Sibling vars Cannot Reference Each Other

Consider:

~~~javascript
{
  $let: {
    vars: {
      low: 10,
      high: "$$low"
    },
    in: {
      $add: [
        "$$low",
        "$$high"
      ]
    }
  }
}
~~~

At first glance, one might assume **high = low = 10**, and result = 20. This assumption is **incorrect**.

In the **vars** declaration block, the **"$$low"** expression for `high` looks into the **scope outside $let**. It does **not** read the `low` variable declared next to it in the same `vars`.

If there is no `low` outside, the computation may fail with an undefined variable error. If an outer scope has `low`, `high` reads that value instead.

### 12.1. Correct Approach: Nesting Another $let

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            low: 10
          },
          in: {
            $let: {
              vars: {
                high: {
                  $multiply: [
                    "$$low",
                    2
                  ]
                }
              },
              in: {
                $add: [
                  "$$low",
                  "$$high"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

The outer `$let` creates `low = 10`. When the inner `$let` declares `high`, **$$low** is already available in its outer scope. Therefore `high = 20` and the result = 30.

### 12.2. Do Not Treat vars as a Sequential Script

Do not interpret:

~~~javascript
vars: {
  x: 10,
  y: "$$x"
}
~~~

like JavaScript:

~~~javascript
let x = 10;
let y = x;
~~~

The ordering of keys in `vars` **does not establish sequential dependencies**. If one variable must depend on another, you must organize the scopes appropriately.

## 13. Nested Scopes and Shadowing

A `$let` nested inside the **in** of another `$let` can read variables from the outer scope.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            base: 100
          },
          in: {
            $let: {
              vars: {
                extra: 25
              },
              in: {
                $add: [
                  "$$base",
                  "$$extra"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Result: `example` = **125**.

### 13.1. Same-Named Variable in Inner Scope Shadows Outer Variable

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            rate: 2
          },
          in: {
            $let: {
              vars: {
                rate: 5
              },
              in: "$$rate"
            }
          }
        }
      }
    }
  }
]);
~~~

The inner expression uses `rate = 5` from the nearest scope, not `rate = 2` from the outer scope. This behavior is called **shadowing**.

### 13.2. Inner vars Expressions Can Still Read Outer Variables

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            amount: 100
          },
          in: {
            $let: {
              vars: {
                amount: {
                  $add: [
                    "$$amount",
                    20
                  ]
                }
              },
              in: "$$amount"
            }
          }
        }
      }
    }
  }
]);
~~~

In the **vars** of the inner `$let`, `$$amount` reads `amount = 100` from the outer scope. In the **in** of the inner `$let`, `$$amount` reads the new variable = 120.

Thus the result = **120**, not an infinite recursive reference.

### 13.3. Variables Do Not Exist in Sibling Expressions

~~~javascript
db.orders.aggregate([
  {
    $project: {
      first: {
        $let: {
          vars: {
            temporary: 7
          },
          in: "$$temporary"
        }
      },
      second: "$$temporary"
    }
  }
]);
~~~

The `second` field is **outside** the `$let` that creates `temporary`. Unless `temporary` is declared in another scope, the `second` expression is invalid due to an undefined variable.

To share a value across multiple output fields, you can compute it beforehand using a **$set stage** and reference the field in subsequent stages, or construct a single object inside the `in` expression of `$let`.

## 14. $let vs. the $set Stage

`$let` creates **local variables inside an expression**. Conversely, the `$set` stage creates **fields in the pipeline document**.

Example of creating `gross` with `$set`:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      gross: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      gross: 1,
      discounted: {
        $multiply: [
          "$gross",
          {
            $subtract: [
              NumberDecimal("1"),
              "$discountRate"
            ]
          }
        ]
      }
    }
  }
]);
~~~

The second stage uses **"$gross"** because `gross` has become a field of the document entering that stage. Do not use **"$$gross"** unless a variable named `gross` was declared.

### 14.1. A Field Created in the Same $set Is Not Available to Sibling Fields

Example you should not expect to work:

~~~javascript
{
  $set: {
    gross: {
      $sum: "$lineTotals"
    },
    net: {
      $multiply: [
        "$gross",
        NumberDecimal("0.9")
      ]
    }
  }
}
~~~

as a guaranteed way for `net` to read the newly created `gross`. Expressions within the same stage are evaluated against the document entering that stage. Use two stages, or nested `$let`, when one calculation depends on the result of another.

~~~javascript
[
  {
    $set: {
      gross: {
        $sum: "$lineTotals"
      }
    }
  },
  {
    $set: {
      net: {
        $multiply: [
          "$gross",
          NumberDecimal("0.9")
        ]
      }
    }
  }
]
~~~

This example assumes `lineTotals` is a numeric array already present in the document before the first stage.

## 15. Computing Order Totals with $let

Using the sample data, `gross`, `discountRate`, and `shippingFee` can be computed in the same expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      payable: {
        $let: {
          vars: {
            gross: {
              $sum: {
                $map: {
                  input: "$items",
                  as: "line",
                  in: {
                    $multiply: [
                      "$$line.quantity",
                      "$$line.unitPrice"
                    ]
                  }
                }
              }
            },
            rate: {
              $ifNull: [
                "$discountRate",
                NumberDecimal("0")
              ]
            },
            fee: {
              $ifNull: [
                "$shippingFee",
                NumberDecimal("0")
              ]
            }
          },
          in: {
            $add: [
              {
                $multiply: [
                  "$$gross",
                  {
                    $subtract: [
                      NumberDecimal("1"),
                      "$$rate"
                    ]
                  }
                ]
              },
              "$$fee"
            ]
          }
        }
      }
    }
  }
]);
~~~

Here `gross`, `rate`, and `fee` are **independent** of each other in `vars`:

- `gross` is computed from the `items` array.
- `rate` is computed from `discountRate`.
- `fee` is computed from `shippingFee`.

The `in` block can use all three because they are declared in the same scope. Formula: **gross × (1 - rate) + fee**.

### 15.1. Nesting Scopes When discountAmount Depends on gross

Do not write **gross** and **discountAmount** as siblings and then reference `$$gross` in the assignment expression for `discountAmount`. Instead:

~~~javascript
{
  $let: {
    vars: {
      gross: {
        $sum: "$lineTotals"
      }
    },
    in: {
      $let: {
        vars: {
          discountAmount: {
            $multiply: [
              "$$gross",
              "$discountRate"
            ]
          }
        },
        in: {
          gross: "$$gross",
          discountAmount: "$$discountAmount",
          afterDiscount: {
            $subtract: [
              "$$gross",
              "$$discountAmount"
            ]
          }
        }
      }
    }
  }
}
~~~

The expression above assumes a `lineTotals` array exists beforehand. In this lesson's sample dataset, you can replace the `gross` part with **$sum + $map** as shown in the earlier example.

## 16. $map: Per-Element Array Variables

**$map** applies an expression to each array element:

~~~javascript
{
  $map: {
    input: arrayExpression,
    as: "item",
    in: itemExpression
  }
}
~~~

Example computing each line amount:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      lineTotals: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            amount: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Inside `in`:

- **$$line** is the element currently being processed.
- **$$line.sku** reads `sku` of that element.
- **$$line.quantity** and **$$line.unitPrice** are used in the multiplication.

### 16.1. Using $$this When as Is Omitted

~~~javascript
db.orders.aggregate([
  {
    $project: {
      lineTotals: {
        $map: {
          input: "$items",
          in: {
            $multiply: [
              "$$this.quantity",
              "$$this.unitPrice"
            ]
          }
        }
      }
    }
  }
]);
~~~

**$$this** is the default element variable in `$map` when `as` is not specified.

In expressions with multiple nested loops, specifying explicit **as** names usually helps avoid confusing which loop `$$this` belongs to.

### 16.2. Nested $map

Suppose a document has `groups`, and each `group` has `members`:

~~~javascript
{
  groups: [
    {
      groupName: "A",
      members: [
        { userId: "U-1", score: 8 },
        { userId: "U-2", score: 9 }
      ]
    }
  ]
}
~~~

It can be expressed as:

~~~javascript
{
  $map: {
    input: "$groups",
    as: "group",
    in: {
      name: "$$group.groupName",
      scores: {
        $map: {
          input: "$$group.members",
          as: "member",
          in: {
            userId: "$$member.userId",
            score: "$$member.score"
          }
        }
      }
    }
  }
}
~~~

The inner loop's `in` expression can read both `$$member` and `$$group`. `$$member` belongs to the inner loop's scope, while `$$group` belongs to the outer loop's scope.

## 17. $let Inside $map

`$let` is frequently placed inside the **in** of `$map` so that each element has its own computed local variables.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      itemsWithTax: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            $let: {
              vars: {
                subtotal: {
                  $multiply: [
                    "$$item.quantity",
                    "$$item.unitPrice"
                  ]
                },
                taxRate: NumberDecimal("0.08")
              },
              in: {
                sku: "$$item.sku",
                subtotal: "$$subtotal",
                taxAmount: {
                  $multiply: [
                    "$$subtotal",
                    "$$taxRate"
                  ]
                }
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Scope:

~~~text
Order document
    |
    v
$map creates the item variable for an element
    |
    v
$let has access to $$item when evaluating vars
    |
    v
$let.in uses $$item, $$subtotal, $$taxRate
    |
    v
Returns an object for the current element
~~~

The assignment expressions for `subtotal` and `taxRate` in the same `vars` do not depend on each other, so this structure is valid.

### 17.1. $let Outside $map

When there is a common rate shared across all elements of the same document:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      amountsWithTax: {
        $let: {
          vars: {
            commonRate: NumberDecimal("0.08")
          },
          in: {
            $map: {
              input: "$items",
              as: "item",
              in: {
                $multiply: [
                  "$$item.quantity",
                  "$$item.unitPrice",
                  {
                    $add: [
                      NumberDecimal("1"),
                      "$$commonRate"
                    ]
                  }
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

`$$commonRate` exists throughout the entire `in` expression of the outer `$let`, so the `$map` inside can read it.

## 18. $filter: Variables in Array Filtering Conditions

**$filter** selects array elements that satisfy a condition:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      largeQuantityLines: {
        $filter: {
          input: "$items",
          as: "line",
          cond: {
            $gte: [
              "$$line.quantity",
              2
            ]
          }
        }
      }
    }
  }
]);
~~~

For O-1001, only the item with `quantity = 2` is kept. For O-1002, `quantity = 1`, so the resulting array is empty.

### 18.1. Combining $filter with $let

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      expensiveItems: {
        $let: {
          vars: {
            minimumPrice: NumberDecimal("80000.00")
          },
          in: {
            $filter: {
              input: "$items",
              as: "item",
              cond: {
                $gte: [
                  "$$item.unitPrice",
                  "$$minimumPrice"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

The `minimumPrice` variable comes from the scope outside `$filter`; `item` comes from `$filter.as`.

### 18.2. When input Is Missing or null

~~~javascript
{
  $filter: {
    input: {
      $ifNull: [
        "$items",
        []
      ]
    },
    as: "item",
    cond: {
      $gte: ["$$item.quantity", 2]
    }
  }
}
~~~

Use `$ifNull` when `items` might be `null` or missing. If `items` is a string or a document of the wrong type instead of an array, schema validation or explicit conversion is required; do not assume `$ifNull` fixes every case automatically.

## 19. $reduce: $$value and $$this

**$reduce** iterates through an array and accumulates a value. Inside the **in** expression, the operator provides:

- **$$value:** the current accumulated value.
- **$$this:** the element currently being processed.

Example computing `gross`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      gross: {
        $reduce: {
          input: "$items",
          initialValue: NumberDecimal("0"),
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.quantity",
                  "$$this.unitPrice"
                ]
              }
            ]
          }
        }
      }
    }
  }
]);
~~~

For O-1001:

~~~text
Initially:
  $$value = 0

Pass 1:
  $$this = BOOK-01 (2 × 100000)
  new $$value = 0 + 200000 = 200000

Pass 2:
  $$this = PEN-01 (1 × 50000)
  new $$value = 200000 + 50000 = 250000

Result:
  gross = 250000
~~~

For O-1004, which has an empty `items` array, `$reduce` returns **initialValue = 0**.

### 19.1. Accumulator as a Document

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      summary: {
        $reduce: {
          input: "$items",
          initialValue: {
            lineCount: 0,
            gross: NumberDecimal("0")
          },
          in: {
            lineCount: {
              $add: [
                "$$value.lineCount",
                1
              ]
            },
            gross: {
              $add: [
                "$$value.gross",
                {
                  $multiply: [
                    "$$this.quantity",
                    "$$this.unitPrice"
                  ]
                }
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

`$$value.lineCount` and `$$value.gross` reference **fields inside the accumulator variable**. They are not direct field paths of the order document.

### 19.2. Comparing $map + $sum with $reduce

Both can compute a total amount:

~~~text
$map: produces a list of amounts for each item
$sum: sums that list
~~~

or:

~~~text
$reduce: accumulates directly via $$value and $$this
~~~

`$map + $sum` is easy to read when the formula is simple. `$reduce` is more suitable when the accumulator consists of multiple fields or complex accumulation logic. The two approaches have different costs depending on data and engine; choose based on clarity and actual requirements.

## 20. $lookup.let: Variable Scope Between Two Collections

In **pipeline-form $lookup**, the **let** property names values taken from the **outer** document so the joined collection's pipeline can reference them.

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      let: {
        customerKey: "$customerId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: [
                "$_id",
                "$$customerKey"
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            name: 1,
            tier: 1
          }
        }
      ],
      as: "customer"
    }
  }
]);
~~~

Context explanation:

~~~text
Outer orders document:
  customerId = "C-01"

$lookup.let:
  customerKey = "$customerId"

Inner customers document:
  _id = "C-01"

$match + $expr:
  "$_id"          -> _id of the current customer
  "$$customerKey" -> variable taken from the outer order
~~~

### 20.1. Why Does $match Inside Lookup Use $expr?

To compare a field with an aggregation variable inside a `$match` query filter, **$expr** is required:

~~~javascript
{
  $match: {
    $expr: {
      $eq: [
        "$_id",
        "$$customerKey"
      ]
    }
  }
}
~~~

If you write:

~~~javascript
{
  $match: {
    _id: "$$customerKey"
  }
}
~~~

that string value must not be interpreted as an expression comparison against the variable. A `$match` filter and an aggregation expression are interpreted differently; `$expr` is the proper way to use expressions in the condition.

### 20.2. $ and $$ in Lookup

- **"$customerId"** in `let` reads a field from the **outer order document**.
- **"$_id"** in `pipeline` reads a field from the **inner customer document**.
- **"$$customerKey"** in `pipeline` reads the variable provided by `let`.

This is one of the easiest places to confuse scope when using MongoDB aggregation.

### 20.3. $lookup.let Differs from the $let Operator

The `$let` operator:

~~~javascript
{
  $let: {
    vars: { x: "$field" },
    in: "$$x"
  }
}
~~~

The `$lookup.let` option:

~~~javascript
{
  $lookup: {
    from: "customers",
    let: {
      x: "$customerId"
    },
    pipeline: [
      {
        $match: {
          $expr: {
            $eq: [
              "$_id",
              "$$x"
            ]
          }
        }
      }
    ],
    as: "joined"
  }
}
~~~

Both constructs provide variables, but **$lookup.let does not have a vars/in pair** like the `$let` expression.

### 20.4. Indexes When Using $lookup with $expr

MongoDB can use an index on the joined collection in certain `$expr` comparisons against suitable `let` values. However, there are limitations, especially when `let` values are missing/empty or with multikey indexes. Do not assume every `$lookup` using `$expr` is automatically index-efficient. With large datasets, inspect `explain` and indexes on the joined collection.

## 21. Aggregate Command-Level Variables vs. Local Variables

Some MongoDB versions support the **let** option on the aggregation command, allowing you to declare variables usable by pipeline expressions.

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        $expr: {
          $gte: [
            "$createdAt",
            "$$cutoff"
          ]
        }
      }
    },
    {
      $project: {
        _id: 1,
        createdAt: 1,
        windowStart: "$$cutoff"
      }
    }
  ],
  {
    let: {
      cutoff: ISODate("2026-11-01T00:00:00Z")
    }
  }
);
~~~

The **cutoff** variable is passed in the options of the `aggregate` command, so the pipeline can reference **$$cutoff**.

### 21.1. JavaScript Variables Do Not Automatically Become MongoDB Variables

~~~javascript
const cutoff = ISODate("2026-11-01T00:00:00Z");
~~~

This line only defines a variable in `mongosh`. If a pipeline contains the string **"$$cutoff"**, the server still needs an aggregation variable named `cutoff` passed or declared properly. Do not confuse client variables with server variables.

### 21.2. Comparing the Two let Forms

| Criterion | Aggregate command let | $let operator |
| --- | --- | --- |
| Location | Options of the aggregate command | Inside an expression |
| Syntax | **let: { name: value }** | **$let: { vars: { ... }, in: ... }** |
| Scope | Pipeline expressions as supported | The `in` expression of that `$let` itself |
| Reference | **$$name** | **$$name** |
| Purpose | Parameterize a single execution | Create local intermediate values |

If an inner scope redeclares the same variable name, the **shadowing** rule from section 13 applies.

## 22. $let in $group

`$let` can be used inside a group key expression or an accumulator expression when appropriate. For example, classifying orders based on a computed `gross`:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      gross: {
        $reduce: {
          input: "$items",
          initialValue: NumberDecimal("0"),
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.quantity",
                  "$$this.unitPrice"
                ]
              }
            ]
          }
        }
      }
    }
  },
  {
    $group: {
      _id: {
        $let: {
          vars: {
            largeOrder: {
              $gte: [
                "$gross",
                NumberDecimal("200000")
              ]
            }
          },
          in: {
            $cond: [
              "$$largeOrder",
              "LARGE",
              "SMALL"
            ]
          }
        }
      },
      count: { $sum: 1 },
      totalGross: { $sum: "$gross" }
    }
  }
]);
~~~

In `$group`:

- **_id** is the **group key** computed by the expression, not implicitly the original `_id` field.
- **$$largeOrder** exists only inside the `in` expression of the `$let` that produces the group key.
- **count** and **totalGross** are separate accumulators and do not automatically see `$$largeOrder` from a sibling expression.

If you need to reuse the classification result in multiple places, you can create the classification field with a `$set` stage before grouping.

## 23. String Literals Starting with $ and Special Field Names

### 23.1. Using $literal When a String Starts with $

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      literalText: {
        $literal: "$VIP"
      }
    }
  }
]);
~~~

The resulting `literalText` contains the string **"$VIP"**.

If you write:

~~~javascript
{
  $let: {
    vars: {
      label: "$VIP"
    },
    in: "$$label"
  }
}
~~~

the `label` variable instead reads the `VIP` field rather than storing the literal `"$VIP"`. Wrap it with `$literal`:

~~~javascript
{
  $let: {
    vars: {
      label: {
        $literal: "$VIP"
      }
    },
    in: "$$label"
  }
}
~~~

### 23.2. Field Names That Actually Contain Dots

The path **"$price.usd"** is normally interpreted as the `usd` field inside the `price` embedded document. However, if a document has a **top-level field literally named "price.usd"**, that is a different case.

In supported versions, you can use **$getField**:

~~~javascript
{
  $getField: {
    field: "price.usd",
    input: "$$ROOT"
  }
}
~~~

For field names starting with a dollar sign, **$literal** may be needed to represent the literal field name. Do not use dot notation for special field names when the intent is to access a literal name.

## 24. Null, Missing, and Data Types

Variable-referencing expressions do not automatically fix data of the wrong type. When data may be missing:

~~~javascript
{
  $let: {
    vars: {
      rate: {
        $ifNull: [
          "$discountRate",
          NumberDecimal("0")
        ]
      },
      fee: {
        $ifNull: [
          "$shippingFee",
          NumberDecimal("0")
        ]
      }
    },
    in: {
      $add: [
        "$$fee",
        {
          $multiply: [
            NumberDecimal("100"),
            "$$rate"
          ]
        }
      ]
    }
  }
}
~~~

**$ifNull** handles `null`/missing values. If `discountRate` is stored as the string `"0.10"`, consider converting it to Decimal128 according to business rules.

Example of type conversion with fallback:

~~~javascript
{
  $convert: {
    input: "$discountRate",
    to: "decimal",
    onError: NumberDecimal("0"),
    onNull: NumberDecimal("0")
  }
}
~~~

**Caution:** Returning zero when type conversion fails can mask corrupted data. In many business domains, conversion errors should be logged or rejected on write rather than silently replaced with zero.

### 24.1. Missing Arrays in $map and $reduce

~~~javascript
{
  $reduce: {
    input: {
      $ifNull: [
        "$items",
        []
      ]
    },
    initialValue: NumberDecimal("0"),
    in: {
      $add: [
        "$$value",
        {
          $multiply: [
            "$$this.quantity",
            "$$this.unitPrice"
          ]
        }
      ]
    }
  }
}
~~~

If `items` is `null`/missing, the expression uses an empty array. However, if `items` is a string, schema validation or other type-conversion logic is required.

## 25. Java Sync Driver: Building $let Expressions

The MongoDB Java Sync Driver can represent aggregation expressions using **Document** and BSON structures.

The example below illustrates `$let` with hypothetical **grossAmount** and **discountRate** fields already stored in the document. The practice dataset at the beginning of the lesson does not have `grossAmount` precomputed; the goal here is to show the Java API structure.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.Arrays;

public class AggregationLetExample {

    public static void main(String[] args) {
        try (MongoClient client =
                MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase db =
                    client.getDatabase("aggregation_variables_lab");

            MongoCollection<Document> orders =
                    db.getCollection("orders");

            Document vars = new Document("gross", "$grossAmount")
                    .append("rate", "$discountRate");

            Document oneMinusRate = new Document(
                    "$subtract",
                    Arrays.asList(1, "$$rate")
            );

            Document netExpression = new Document(
                    "$multiply",
                    Arrays.asList("$$gross", oneMinusRate)
            );

            Document let = new Document("$let",
                    new Document("vars", vars)
                            .append("in", netExpression)
            );

            Document project = new Document("$project",
                    new Document("_id", 1)
                            .append("netAmount", let)
            );

            orders.aggregate(Arrays.asList(project))
                    .forEach(doc -> System.out.println(doc.toJson()));
        }
    }
}
~~~

For real monetary applications, standardize on the **Decimal128** type for values participating in arithmetic instead of mixing integers and doubles without control.

### 25.1. Distinguishing Java Variables and MongoDB Variables

~~~java
String fieldReference = "$grossAmount";
~~~

This is a variable in the Java program, used only when constructing the BSON command.

~~~javascript
{
  $let: {
    vars: {
      gross: "$grossAmount"
    },
    in: "$$gross"
  }
}
~~~

This declares a **server-side gross variable** inside a MongoDB expression. The string **"$$gross"** is evaluated by the server within the `$let` scope, rather than being a Java variable.

### 25.2. Inspecting the BSON Command Before Execution

~~~java
System.out.println(project.toJson());
~~~

Inspecting the BSON structure helps catch errors such as:

- Confusing `"$field"` and `"$$variable"`.
- Placing `vars` or `in` at the wrong nesting level.
- Lifting `$let` to the stage level instead of placing it inside an expression.
- Missing `$literal` for strings starting with a dollar sign.
- Referencing an out-of-scope variable.

Do not log sensitive customer data without proper log protection measures.

## 26. Expression Optimization and Maintainability

### 26.1. $let Does Not Persist Across Multiple Stages

Variables in `$let` live only within the **in** expression. To use a value across multiple stages, create a field with `$set`, reference it in subsequent stages, and optionally `$unset` it before returning the result.

### 26.2. $let Does Not Replace Indexes

~~~javascript
db.orders.aggregate([
  {
    $project: {
      x: {
        $let: {
          vars: {
            state: "$status"
          },
          in: "$$state"
        }
      }
    }
  }
]);
~~~

Assigning the `state` variable does not make MongoDB automatically use an index for queries filtering `status`. If you need to retrieve `PAID` orders, place an appropriate `$match`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $project: {
      status: 1
    }
  }
]);
~~~

Pipeline structure, indexes, selectivity, and query plans remain critical factors for performance.

### 26.3. Avoid Overly Deep Scope Nesting When Unnecessary

An expression with 5–6 nested `$let` layers can become difficult to maintain. When a calculation has multiple interdependent steps, consider:

- Splitting into `$set` stages with clear temporary field names.
- Using `$let` in small scopes, only for truly local variables.
- Naming variables to reflect business concepts.
- Keeping numeric types consistent in monetary calculations.
- Using a final `$project` to return only the desired fields.

Clarity usually reduces real-world bugs far more than shaving off a few pipeline lines.

## 27. Common Mistakes

| Mistake | Correct Understanding |
| --- | --- |
| Using **"$item.sku"** to read a `$map` variable | Must use **"$$item.sku"** |
| **$$anything** exists automatically | A variable must be declared in scope or be a system variable |
| **$$ROOT** is always the original document of the entire pipeline | `ROOT` belongs to the context of the document entering the current stage |
| **$$CURRENT** and **$$ROOT** are always completely identical | `CURRENT` is the field path context; `ROOT` is the stage's root |
| Writing **"$VIP"** to return the literal string `"$VIP"` | Use **$literal** |
| Two variables in the same `$let` `vars` can declare sequential dependencies | Each declaration expression looks at the scope **outside $let** |
| A variable created in `$let` can be used in sibling fields outside `let` | Only the `in` of `$let` can use that variable |
| `$let` is a pipeline stage | `$let` is an **expression operator** |
| A `$set` stage creates sibling `gross` and `net`, and `net` always reads the new `gross` | Create `gross` in a prior stage or nest scopes properly |
| `$map` automatically makes field path **$sku** point to the array element | Use **$$item.sku** or **$$this.sku** |
| `$$this`/`$$value` are global variables | They are provided by operators such as `$map`/`$reduce` within their own scope |
| `$lookup.let` has `vars`/`in` like `$let` | `$lookup.let` has its own structure |
| In `$lookup`, comparing **_id: "$$key"** is automatically an expression | Use **$expr** in `$match` when comparing against a variable |
| `$$NOW` is recomputed for every document | `NOW` is stable within a single pipeline execution |
| `$$REMOVE` is equivalent to `null` | `REMOVE` omits the field; `null` is a value |
| `$ifNull` handles every wrong BSON type | It handles `null`/missing; wrong types require separate handling |
| Using `$let` automatically makes aggregation faster | Performance also depends on the query plan and workload |

## 28. Practice Exercises

The exercises use the database and collections created in section 2.

### Exercise 1: Comparing Field, CURRENT, and ROOT

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      viaField: "$status",
      viaCurrent: "$$CURRENT.status",
      viaRoot: "$$ROOT.status",
      city: "$shipping.city"
    }
  }
]);
~~~

Explain why all three ways of retrieving `status` produce the same result in the example, and why `$$ROOT` after a `$project` stage no longer contains all original fields.

### Exercise 2: literal

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      evaluated: "$status",
      literalText: {
        $literal: "$status"
      }
    }
  }
]);
~~~

Point out the difference between the values of **evaluated** and **literalText**.

### Exercise 3: Simple $let

~~~javascript
db.orders.aggregate([
  {
    $project: {
      answer: {
        $let: {
          vars: {
            a: 5,
            b: 7
          },
          in: {
            $multiply: [
              "$$a",
              "$$b"
            ]
          }
        }
      }
    }
  }
]);
~~~

Result: `answer` = **35**. Explain why the declared names in `vars` do not have two dollar signs, while references in `in` do.

### Exercise 4: Spotting a Scope Error

~~~javascript
{
  $let: {
    vars: {
      a: 10,
      b: {
        $multiply: [
          "$$a",
          3
        ]
      }
    },
    in: {
      $add: [
        "$$a",
        "$$b"
      ]
    }
  }
}
~~~

Explain why `b` does not automatically evaluate to 30. Rewrite it using **nested $let** so that the result equals 40.

### Exercise 5: $map Producing lineTotals

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            amount: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

For O-1001, determine the `amount` of BOOK-01 and PEN-01. Then replace **$$line.unitPrice** with **$line.unitPrice** and explain why it no longer reads the array element properly.

### Exercise 6: Combining $filter with Variables

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      selected: {
        $let: {
          vars: {
            threshold: NumberDecimal("80000")
          },
          in: {
            $filter: {
              input: "$items",
              as: "item",
              cond: {
                $gte: [
                  "$$item.unitPrice",
                  "$$threshold"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Identify which scope `threshold` belongs to and which scope the `item` variable belongs to.

### Exercise 7: $reduce Accumulating a Document

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      summary: {
        $reduce: {
          input: "$items",
          initialValue: {
            count: 0,
            gross: NumberDecimal("0")
          },
          in: {
            count: {
              $add: [
                "$$value.count",
                1
              ]
            },
            gross: {
              $add: [
                "$$value.gross",
                {
                  $multiply: [
                    "$$this.quantity",
                    "$$this.unitPrice"
                  ]
                }
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Answer:

1. What does `$$value` contain on the first pass?
2. When does `$$this` change?
3. Why does O-1004 produce `count = 0` and `gross = 0`?
4. If you want the sum of `quantity` instead of the number of `items` lines, how should the `count` part be modified?

### Exercise 8: $lookup let and $expr

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      let: {
        customerKey: "$customerId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: [
                "$_id",
                "$$customerKey"
              ]
            }
          }
        }
      ],
      as: "customerInfo"
    }
  }
]);
~~~

Analyze each value source: **"$customerId"** of the order, **"$_id"** of the customer, and **"$$customerKey"** from the lookup variable.

### Exercise 9: NOW and REMOVE

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      observedAt: "$$NOW",
      paidLabel: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "Paid",
          "$$REMOVE"
        ]
      }
    }
  }
]);
~~~

Explain why `paidLabel` disappears on non-`PAID` orders instead of appearing with `null`.

### Exercise 10: Multi-Step Total Calculation

Build a pipeline from `items` and `discountRate` to calculate:

1. `gross` = sum of `quantity × unitPrice`.
2. `discountAmount` = `gross × discountRate`.
3. `net` = `gross - discountAmount`.
4. `payable` = `net + shippingFee`.

Constraint: **discountAmount must read gross from a valid scope**; do not declare both at the same `vars` level and reference incorrectly.

One approach:

~~~text
Outer $let:
    declare gross
       |
       v
Inner $let:
    declare discountAmount from $$gross
       |
       v
in:
    create object containing gross, discountAmount, net, and payable
~~~

The expected result for O-1001 is `gross` **250,000**, `discountAmount` **25,000**, `net` **225,000**, and `payable` **240,000**.

### Exercise 11: Command Variables vs. mongosh Variables

~~~javascript
const cutoff = ISODate("2026-11-02T00:00:00Z");
~~~

Write two versions:

- Pass the `cutoff` value directly from JavaScript into the pipeline when constructing the command.
- Declare **let: { cutoff: ... }** in the options of the `aggregate` command and then use **"$$cutoff"** in the pipeline.

Explain why **const cutoff** in `mongosh` does not automatically make the server understand **$$cutoff**.

## 29. Key Takeaways

When reading an aggregation expression, ask yourself:

1. **Is this value read from a field or a variable?** Single `$` for field path, double `$$` for variable.
2. **What is the source document?** `$$ROOT`, `$$CURRENT`, a `$map` element, a `$filter` element, or a document inside `$lookup`?
3. **Where is the variable declared?** `$let.vars`, `$map.as`, `$lookup.let`, or a system variable?
4. **Is the scope still active?** A `$let` variable lives only inside `in`; sibling variables in `vars` cannot see each other.
5. **Is the data an expression or a literal?** Strings starting with `$` need `$literal` if you want to keep them verbatim.
6. **How do the operators handle null, missing, and BSON types?** Do not assume every schema is clean.

The most important rule of **$let**:

> **Declare variables in `vars` to use in `in`; if a new variable depends on another new variable, nest another `$let` or split stages.** Do not assume `vars` is executed sequentially from top to bottom.

Understanding variable lexical scope is the foundation for building complex aggregation pipelines that remain accurate, readable, and maintainable.

## References

- [MongoDB Manual — Aggregation Variables](https://www.mongodb.com/docs/manual/reference/aggregation-variables/)
- [MongoDB Manual — $let](https://www.mongodb.com/docs/manual/reference/operator/aggregation/let/)
- [MongoDB Manual — $map](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/)
- [MongoDB Manual — $filter](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/)
- [MongoDB Manual — $reduce](https://www.mongodb.com/docs/manual/reference/operator/aggregation/reduce/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — $expr](https://www.mongodb.com/docs/manual/reference/operator/query/expr/)
- [MongoDB Manual — $literal](https://www.mongodb.com/docs/manual/reference/operator/aggregation/literal/)
- [MongoDB Manual — $getField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getField/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
