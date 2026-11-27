# Window Analysis with $setWindowFields: Ranking and Running Totals in MongoDB

## Lesson Objectives

Business reports often need to answer questions that `$group` alone cannot express conveniently:

- What is a store's **cumulative revenue** up to each transaction?
- What is an employee's **rank within a store** by revenue?
- If two employees tie, should they share a rank or still receive a **unique row number**?
- What is the moving average of the **last three transactions**?
- How does revenue over the **last two days** differ from the last two transactions?
- What percentage does each row contribute to the **total group revenue**?

Starting in version **5.0**, MongoDB provides the **`$setWindowFields`** aggregation stage to compute values over a subset of neighboring or group-related documents—called a **window**—while keeping each individual document in the output. It is a key tool in **Advanced Aggregation** for dashboards, time-series reports, leaderboards, and sequence analytics.

This lesson focuses on two primary use cases:

1. **Ranking** with `$rank`, `$denseRank`, and `$documentNumber`.
2. **Running totals** using `$sum` with a window from the start of the partition to the current document.

After this lesson, you will be able to:

- Read and write `partitionBy`, `sortBy`, `output`, and `window` accurately.
- Distinguish **partition**, **order within a partition**, and **window bounds**.
- Understand ranking **with gaps**, **gapless** ranking, and **unique** row numbers.
- Compute running totals, running counts, moving averages, partition totals, and share percentages.
- Distinguish **document-based** windows from **value- or time-range** windows.
- Handle duplicate timestamps, missing/null values, wrong BSON types, and non-deterministic ordering.
- Structure pipelines properly to filter data without unintentionally corrupting accumulations.
- Evaluate sort, memory, disk spill, and index costs, and apply them in `mongosh` or the Java Driver.

> **Key takeaway:** `$group` typically **collapses multiple documents into one summary row** per group. `$setWindowFields` **preserves every document**, appending results computed over the data relevant to that document.

---

## 1. Why Is Window Analysis Needed?

### 1.1. Group Totals vs. Row-Level Questions

Suppose store HCM has three transactions:

| Transaction | Date | Revenue |
|---|---|---:|
| A | 01/01 | 100 |
| B | 02/01 | 200 |
| C | 03/01 | 50 |

To find **HCM's total revenue**, `$group` works well:

~~~javascript
db.sales.aggregate([
  {
    $group: {
      _id: "$store",
      totalRevenue: { $sum: "$revenue" }
    }
  }
]);
~~~

Result for HCM: one document containing `totalRevenue: 350`.

However, if you need:

| Transaction | Row Revenue | Cumulative Revenue Through Row |
|---|---:|---:|
| A | 100 | 100 |
| B | 200 | 300 |
| C | 50 | 350 |

you must **preserve the rows** and sum from the start up to each row. `$setWindowFields` expresses this requirement directly.

### 1.2. Mental Model

~~~text
Collection sales
        |
        v
      $match            select scope of data to analyze
        |
        v
  $setWindowFields
     partitionBy        split by store / customer / employee...
     sortBy             define order inside each group
     output.window      define which rows are visible
     output.operator    $sum, $avg, $rank, $denseRank...
        |
        v
      $sort             define final output order
        |
        v
     $project           pick fields for report / API
~~~

Never confuse three distinct concepts:

- **Partition:** documents sharing the same partition key.
- **Sort:** order used for calculations inside each partition.
- **Window:** count or range of documents considered for the **current document**.

A partition may hold 10,000 documents while a row's window sees only 3 neighboring documents—or all 10,000 documents—depending on the window specification.

---

## 2. General Syntax of `$setWindowFields`

~~~javascript
db.collectionName.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$groupField",
      sortBy: {
        orderField: 1
      },
      output: {
        newField: {
          $sum: "$numericField",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Meaning:

| Component | Role | Required? |
|---|---|---|
| `partitionBy` | Expression splitting documents into independent groups | Optional; omitting puts all input in one partition |
| `sortBy` | Sort keys and direction `1`/`-1` within each partition | Required for rank/order operators and bounded windows; not required in all cases |
| `output` | Defines fields appended to each document | Required |
| `$sum`, `$avg`, `$rank`... | Window operator used to compute the value | Per output field |
| `window` | Data span for operators supporting explicit windows | Optional for some operators; rank operators disallow `window` |
| `documents` | Window bounds by row position offset | One window type |
| `range` | Window bounds by sort field value | One window type |
| `unit` | Time unit for time-range windows | Used with time-based range windows |

Key notes:

1. `output` can define **multiple computed fields** in a single stage.
2. `$setWindowFields` appends fields to output documents rather than replacing entire documents.
3. Multiple `$setWindowFields` stages can be chained in a pipeline if different sort orders are needed.
4. Omitting `window` on an operator that supports explicit windows defaults to an **unbounded full-partition window**, **not a running total up to the current row**.
5. Rank operators like `$rank` and `$denseRank` use an **implicit window**: **do not specify `window`** on them.
6. This stage **does not guarantee output document order**. If an API expects sorted output, add a separate `$sort` stage afterward.

### 2.1. Single-Partition Illustration

~~~text
Partition: HCM
sortBy: { day: 1, _id: 1 }

row 1      row 2      row 3      row 4
  100        200        200         50
   |----------|----------|----------|

Window at row 3:
  documents: ["unbounded", "current"]
  => [100, 200, 200] => $sum = 500

Window at row 3:
  documents: [-1, 0]
  => [200, 200] => $sum = 400

Window at row 3:
  documents: ["unbounded", "unbounded"]
  => [100, 200, 200, 50] => $sum = 550
~~~

In every window, both bounds are **inclusive** per `$setWindowFields` rules.

---

## 3. Preparing Practice Data in mongosh

Use a dedicated test database; **never run create/delete commands in production**.

~~~javascript
use window_analysis_lab

db.sales.insertMany([
  {
    _id: 1,
    store: "HCM",
    seller: "An",
    day: ISODate("2026-01-01T00:00:00Z"),
    revenue: 100
  },
  {
    _id: 2,
    store: "HCM",
    seller: "Bình",
    day: ISODate("2026-01-02T00:00:00Z"),
    revenue: 200
  },
  {
    _id: 3,
    store: "HCM",
    seller: "Chi",
    day: ISODate("2026-01-02T00:00:00Z"),
    revenue: 200
  },
  {
    _id: 4,
    store: "HCM",
    seller: "Dung",
    day: ISODate("2026-01-04T00:00:00Z"),
    revenue: 50
  },
  {
    _id: 5,
    store: "HN",
    seller: "Hà",
    day: ISODate("2026-01-01T00:00:00Z"),
    revenue: 150
  },
  {
    _id: 6,
    store: "HN",
    seller: "Lan",
    day: ISODate("2026-01-03T00:00:00Z"),
    revenue: 150
  },
  {
    _id: 7,
    store: "HN",
    seller: "Minh",
    day: ISODate("2026-01-04T00:00:00Z"),
    revenue: 300
  },
  {
    _id: 8,
    store: "DN",
    seller: "Ngọc",
    day: ISODate("2026-01-02T00:00:00Z"),
    revenue: 0
  },
  {
    _id: 9,
    store: "DN",
    seller: "Phúc",
    day: ISODate("2026-01-03T00:00:00Z"),
    revenue: null
  },
  {
    _id: 10,
    store: "DN",
    seller: "Quân",
    day: ISODate("2026-01-04T00:00:00Z")
  }
]);
~~~

Verify:

~~~javascript
db.sales.countDocuments({});

db.sales.find(
  {},
  { _id: 1, store: 1, seller: 1, day: 1, revenue: 1 }
).sort({ store: 1, day: 1, _id: 1 });
~~~

When inserted once, the lab set has **10 documents**.

Intentional data characteristics:

- **HCM:** 4 transactions, two rows on 02/01, tied revenue of 200.
- **HN:** 3 transactions, two rows with tied revenue of 150.
- **DN:** 3 transactions, one with revenue 0, one `null`, one **missing the revenue field**.
- `_id` is unique, making it useful for breaking ties on duplicate timestamps when deterministic ordering is needed.
- Dates are BSON Date values, suitable for time-range windows.

To reset the lab, use a new database/collection or delete lab documents according to plan. Never run broad deletes outside practice scope.

---

## 4. Running Totals with `$sum` and `documents: ["unbounded", "current"]`

### 4.1. Business Question

"Up through **each transaction**, how much cumulative revenue has the store accumulated?"

For HCM, sorted by ascending day and ascending `_id`:

| `_id` | Day | Revenue | Running total |
|---:|---|---:|---:|
| 1 | 01/01 | 100 | 100 |
| 2 | 02/01 | 200 | 300 |
| 3 | 02/01 | 200 | 500 |
| 4 | 04/01 | 50 | 550 |

Key point: the two same-day transactions are tie-broken by `_id`, giving **row-by-row** accumulation deterministic ordering.

### 4.2. Pipeline

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: [
              "unbounded",
              "current"
            ]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      store: 1,
      seller: 1,
      day: 1,
      revenue: 1,
      runningRevenue: 1
    }
  }
]);
~~~

Explanation:

- `partitionBy: "$store"` forms three partitions: HCM, HN, and DN.
- `sortBy: {day:1,_id:1}` orders transactions **within each partition**.
- `documents: ["unbounded","current"]` spans from the start of the partition to the current row.
- `$sum: "$revenue"` adds revenues inside the window.
- Trailing `$sort` defines **final output order**, because `$setWindowFields` does not guarantee output order.

### 4.3. Expected Results for All Three Partitions


| Store | `_id` | Revenue | Running total |
|---|---:|---:|---:|
| DN | 8 | 0 | 0 |
| DN | 9 | null | 0 |
| DN | 10 | Missing | 0 |
| HCM | 1 | 100 | 100 |
| HCM | 2 | 200 | 300 |
| HCM | 3 | 200 | 500 |
| HCM | 4 | 50 | 550 |
| HN | 5 | 150 | 150 |
| HN | 6 | 150 | 300 |
| HN | 7 | 300 | 600 |

Windowed `$sum` ignores non-numeric values per accumulator rules; null/missing entries in DN contribute nothing to revenue. **Do not interpret a running total of 0 as proof that every row had valid revenue data.** To verify data quality, count null/missing/wrong-typed rows separately.

### 4.4. Why Is the `_id` Tie-Breaker Needed?

If you write only:

~~~javascript
sortBy: { day: 1 }
~~~

then HCM's two 02/01 transactions have identical sort keys. If you only need **daily** totals, same-day rows form a single time-value group. Yet if you need a **per-transaction** running total, their relative order must be explicit.

With a document-position window, when sort keys tie without a tie-breaker, a transaction could receive 300 on one run and 500 on another under certain conditions; never build application logic on unguaranteed order.

A common pattern:

~~~javascript
sortBy: {
  day: 1,
  _id: 1
}
~~~

However, if `_id` does not reflect true business sequence, use a well-defined ordering field such as `sequenceNo`, `eventId`, or `ingestedAt + stable ID`.

---

## 5. Special Caveat: Omitting `window` Does Not Mean Running Total

Compare two outputs:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        storeRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "unbounded"]
          }
        }
      }
    }
  },
  {
    $sort: { store: 1, day: 1, _id: 1 }
  }
]);
~~~

Meaning:

- `runningRevenue`: changes from row to row.
- `storeRevenue`: **entire partition total**, identical on every row of the store.

For HCM:

| ID | Running | Total store |
|---:|---:|---:|
| 1 | 100 | 550 |
| 2 | 300 | 550 |
| 3 | 500 | 550 |
| 4 | 550 | 550 |

For window operators supporting explicit windows, omitting `window` defaults to the **full partition**, not `["unbounded","current"]`.

For example:

~~~javascript
output: {
  storeRevenue: {
    $sum: "$revenue"
  }
}
~~~

computes the full-partition sum and **does not** produce a row-by-row running total. Always write explicit window bounds for running totals to avoid mistakes.

### 5.1. Difference Between Cumulative and Partition Total

| Requirement | Window | HCM First Row |
|---|---|---:|
| Cumulative total through row | `documents:["unbounded","current"]` | 100 |
| Full group total | `documents:["unbounded","unbounded"]` | 550 |
| Current row only | `documents:["current","current"]` | 100 |
| Current and previous row | `documents:[-1,0]` | 100 on first row |
| Last 3 rows including current | `documents:[-2,0]` | 100 on first row |

Relative bounds are **clamped by partition boundaries**: a window never crosses into another store.

---

## 6. Computing Multiple Metrics in One `$setWindowFields` Stage

A real report often needs several metrics sharing the same partition and sort.

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        runningTransactions: {
          $count: {},
          window: {
            documents: ["unbounded", "current"]
          }
        },
        storeRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "unbounded"]
          }
        },
        latestThreeAverage: {
          $avg: "$revenue",
          window: {
            documents: [-2, 0]
          }
        }
      }
    }
  },
  {
    $sort: { store: 1, day: 1, _id: 1 }
  }
]);
~~~

Outputs:

| Field | Meaning |
|---|---|
| `runningRevenue` | Revenue from start of partition through current row |
| `runningTransactions` | Document count from start of partition through current row |
| `storeRevenue` | Total revenue across entire partition |
| `latestThreeAverage` | Mean numeric revenue across up to 3 rows: 2 prior plus current |

### 6.1. Why Does `runningTransactions` Differ from Counting Valid Revenues?

Window `$count` counts **documents inside the window**, including documents where revenue is null or missing. For DN:

| Row | Revenue | Running transactions | Running revenue |
|---:|---:|---:|---:|
| 8 | 0 | 1 | 0 |
| 9 | null | 2 | 0 |
| 10 | Missing | 3 | 0 |

This is expected: three transactions is different from three transactions having **valid numeric revenue**.

To count only numeric revenues, use `$sum` with a conditional expression:

~~~javascript
validRevenueCount: {
  $sum: {
    $cond: [
      { $isNumber: "$revenue" },
      1,
      0
    ]
  },
  window: {
    documents: ["unbounded", "current"]
  }
}
~~~

`$isNumber` is an aggregation expression. Thus DN gets `validRevenueCount = 1` after row 8 and does not increment on the null/missing rows.

### 6.2. Moving Average of the Last Three Transactions

For HCM sorted by `day, _id`:

| ID | Revenue | 3-Row Window | Average |
|---:|---:|---|---:|
| 1 | 100 | [100] | 100 |
| 2 | 200 | [100,200] | 150 |
| 3 | 200 | [100,200,200] | ≈166.67 |
| 4 | 50 | [200,200,50] | 150 |

When a window contains null, missing, or non-numeric strings, `$avg` ignores non-numeric values per accumulator rules; if no valid numbers exist, it returns null.

**Do not** treat this average as a **three-day** moving average: it averages three **documents**, whereas HCM has two transactions on the same day.

---

## 7. Ranking with `$rank`, `$denseRank`, and `$documentNumber`

The three operators most frequently confused when building leaderboards:

| Operator | Assigns equal values the same rank? | Skips rank numbers after a tie? |
|---|---|---|
| `$rank` | **Yes** | **Yes** |
| `$denseRank` | **Yes** | **No** |
| `$documentNumber` | **No**; every document gets a unique number | N/A (does not share ranks on ties) |

Suppose descending scores are 90, 80, 80, 70:

| Score | `$rank` | `$denseRank` | `$documentNumber` |
|---:|---:|---:|---:|
| 90 | 1 | 1 | 1 |
| 80 | 2 | 2 | 2 |
| 80 | 2 | 2 | 3 |
| 70 | 4 | 3 | 4 |

**Definitions:**

- **Competition rank (`$rank`):** two tied entries occupy two slots, so the next score jumps ahead.
- **Dense rank (`$denseRank`):** distinct score levels receive consecutive ranks with no gaps.
- **Row number (`$documentNumber`):** unique sequential position per sort inside the partition; when sort keys tie, add a tie-breaker for stability.

### 7.1. Syntax

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$store",
    sortBy: {
      revenue: -1
    },
    output: {
      competitionRank: {
        $rank: {}
      },
      denseRank: {
        $denseRank: {}
      }
    }
  }
}
~~~

Key points:

1. `$rank` and `$denseRank` are used **inside `$setWindowFields`**.
2. Each takes an empty object: `{$rank:{}}` and `{$denseRank:{}}`.
3. They **do not accept `window`** because they use an implicit window.
4. `sortBy` is required to determine rank order.
5. For **`$rank`** and **`$denseRank`**, `sortBy` allows **a single field** as the ranking key per operator requirements; do not append `_id` in the same `sortBy` when ranking by a single metric.

### 7.2. Why Not Use `sortBy: {revenue: -1, _id: 1}` for `$rank`?

The purpose of `$rank` is to give documents with equal revenue **the same rank**. Adding `_id` as a secondary sort key would differentiate equal-revenue rows into distinct sort tuples; moreover, `$rank` restricts `sortBy` to **a single field**.

Right pattern:

- **Use `sortBy: {revenue: -1}` to compute ranks/ties**.
- **Use `$sort: {store: 1, revenue: -1, _id: 1}` afterward** for deterministic display order.
- If you want "exactly 3 rows" instead of "rows within the top 3 ranks," use `$documentNumber` in a separate stage with a tie-broken sort.

---

## 8. Hands-On Revenue Leaderboard

### 8.1. Filter Out Null/Missing Before Numeric Ranking

DN contains null and missing revenue. If the leaderboard covers valid revenues only, filter first:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1
      },
      output: {
        competitionRank: {
          $rank: {}
        },
        denseRank: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      revenue: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      store: 1,
      seller: 1,
      revenue: 1,
      competitionRank: 1,
      denseRank: 1
    }
  }
]);
~~~

`$type: "number"` matches BSON numeric types. If revenues were stored as numeric strings, this query does not cast them automatically; clean data or apply an explicit conversion policy first.

### 8.2. Expected Results for HCM

In HCM: descending revenues are 200, 200, 100, 50.

| Seller | Revenue | `$rank` | `$denseRank` |
|---|---:|---:|---:|
| Bình | 200 | 1 | 1 |
| Chi | 200 | 1 | 1 |
| An | 100 | 3 | 2 |
| Dung | 50 | 4 | 3 |

Bình and Chi tie at rank 1. With `$rank`, rank 2 is **skipped** and An gets rank 3. With `$denseRank`, An gets rank 2.

### 8.3. Expected Results for HN

HN data: 300, 150, 150.

| Seller | Revenue | `$rank` | `$denseRank` |
|---|---:|---:|---:|
| Minh | 300 | 1 | 1 |
| Hà | 150 | 2 | 2 |
| Lan | 150 | 2 | 2 |

### 8.4. Note on Row Granularity

In the lab dataset, each transaction maps to one seller. If a seller has **multiple transactions**, the pipeline above ranks **transactions**, not **total revenue per seller**.

To build a **monthly seller revenue leaderboard**, run `$group` by seller first, then `$setWindowFields` to rank the aggregated seller documents. This is a critical business granularity distinction.

---

## 9. Ranking Employee Revenue After `$group`

### 9.1. Problem

Each seller may have multiple transactions. We want a leaderboard of **total revenue per seller** within each store.

Pipeline:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: { $type: "number" }
    }
  },
  {
    $group: {
      _id: {
        store: "$store",
        seller: "$seller"
      },
      sellerRevenue: {
        $sum: "$revenue"
      },
      transactionCount: {
        $sum: 1
      }
    }
  },
  {
    $set: {
      store: "$_id.store",
      seller: "$_id.seller"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        sellerRevenue: -1
      },
      output: {
        rankInStore: {
          $rank: {}
        },
        denseRankInStore: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      rankInStore: 1,
      seller: 1
    }
  },
  {
    $project: {
      _id: 0,
      store: 1,
      seller: 1,
      sellerRevenue: 1,
      transactionCount: 1,
      rankInStore: 1,
      denseRankInStore: 1
    }
  }
]);
~~~

In this small lab dataset, each seller happens to have one transaction. Yet this pipeline establishes the right **ranking unit** when real data has many transactions per seller.

### 9.2. Why Must `$group` Come First?

Flow:

~~~text
sales transactions
       |
       v
$group by (store,seller)
       |
       v
each seller = one total-revenue document
       |
       v
$setWindowFields rank by sellerRevenue
       |
       v
one row = one seller with rank in store
~~~

Placing rank before group ranks **individual transactions** rather than sellers—producing wrong rankings even though the syntax runs cleanly.

### 9.3. Partitioning by Multiple Attributes

Across multiple months and stores, construct a compound partition key:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      saleMonth: {
        $dateTrunc: {
          date: "$day",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $group: {
      _id: {
        store: "$store",
        saleMonth: "$saleMonth",
        seller: "$seller"
      },
      sellerRevenue: {
        $sum: "$revenue"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: {
        store: "$_id.store",
        saleMonth: "$_id.saleMonth"
      },
      sortBy: {
        sellerRevenue: -1
      },
      output: {
        monthlyRank: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $sort: {
      "_id.store": 1,
      "_id.saleMonth": 1,
      monthlyRank: 1,
      "_id.seller": 1
    }
  }
]);
~~~

Here `partitionBy` is a **group-key expression**, not necessarily a simple field path string. Stores and months are cleanly isolated. `$dateTrunc` with a timezone ensures business calendar months are aligned properly when timestamps are stored in UTC.

---

## 10. `$documentNumber`: Unique Sequence Numbers with a Tie-Breaker

### 10.1. Distinguishing "Shared Rank" from "Unique Row Number"

If two sellers tie at revenue 200:

- `$rank`: both get rank 1.
- `$denseRank`: both get dense rank 1.
- `$documentNumber`: they receive distinct sequence numbers, e.g., 1 and 2.

To ensure deterministic numbering on ties, include a unique secondary key in `sortBy`, which is allowed for `$documentNumber`:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1,
        _id: 1
      },
      output: {
        rowNumber: {
          $documentNumber: {}
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      rowNumber: 1
    }
  }
]);
~~~

For HCM, sorted by `revenue DESC, _id ASC`:

| ID | Revenue | Row number |
|---:|---:|---:|
| 2 | 200 | 1 |
| 3 | 200 | 2 |
| 1 | 100 | 3 |
| 4 | 50 | 4 |

### 10.2. When to Use Rank vs. Row Number?

| Requirement | Choose |
|---|---|
| Medals: multiple people share first place | `$rank` |
| Score tiers top-down without skipping numbers | `$denseRank` |
| Pagination or taking exactly N rows by criteria | `$documentNumber` with deterministic sort |
| "Top 3 ranks" which may return more than 3 documents | `$rank`/`$denseRank` per policy |
| "Exactly the first 3 rows" regardless of ties | `$documentNumber` |
| Tie-aware leaderboard with stable display order | `$rank`/`$denseRank` plus trailing `$sort` with tie-breaker |

### 10.3. Do Not Substitute `$documentNumber` for `$rank` When Ties Matter

A leaderboard numbering tied performers as 1, 2, 3 violates competition fairness rules. Use `$documentNumber` only when the product genuinely needs **row sequence numbers** rather than shared ranks.

---

## 11. Fetching Top N: Keep Ties or Not?

### 11.1. Top 2 Ranks with `$rank`

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1
      },
      output: {
        rankInStore: {
          $rank: {}
        }
      }
    }
  },
  {
    $match: {
      rankInStore: {
        $lte: 2
      }
    }
  },
  {
    $sort: {
      store: 1,
      rankInStore: 1,
      revenue: -1,
      _id: 1
    }
  }
]);
~~~

For HCM, both 200-revenue rows have rank 1 and are returned. The 100-revenue row has rank 3, falling outside Top 2 competition ranks.

For HN, Minh is rank 1 and Hà/Lan tie at rank 2: the Top 2 query **returns 3 documents** for HN. That is correct for "Top 2 **ranks**," rather than "exactly two rows."

### 11.2. Top 2 Score Levels with `$denseRank`

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1
      },
      output: {
        denseRankInStore: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $match: {
      denseRankInStore: {
        $lte: 2
      }
    }
  },
  {
    $sort: {
      store: 1,
      denseRankInStore: 1,
      _id: 1
    }
  }
]);
~~~

For HCM, the Top 2 **revenue tiers** include 200, 200, and 100—3 rows total.

### 11.3. Exactly 2 Documents with `$documentNumber`

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1,
        _id: 1
      },
      output: {
        rowNumber: {
          $documentNumber: {}
        }
      }
    }
  },
  {
    $match: {
      rowNumber: {
        $lte: 2
      }
    }
  },
  {
    $sort: {
      store: 1,
      rowNumber: 1
    }
  }
]);
~~~

This picks at most two documents per store. Because DN has only one valid numeric row, DN returns one row; no second row is fabricated.

**Product requirements must be explicit:** "Top 2 ranks" and "Top 2 rows" are two distinct requirements.

---

## 12. Document-Based Windows: Moving Sum and Moving Average

### 12.1. Last Three Transactions

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        last3Revenue: {
          $sum: "$revenue",
          window: {
            documents: [-2, 0]
          }
        },
        last3Average: {
          $avg: "$revenue",
          window: {
            documents: [-2, 0]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

`[-2,0]` means **two preceding documents + current document**, all confined to the store's partition.

For HCM:

| ID | Revenue | Last 3 revenue | Last 3 avg |
|---:|---:|---:|---:|
| 1 | 100 | 100 | 100 |
| 2 | 200 | 300 | 150 |
| 3 | 200 | 500 | ≈166.67 |
| 4 | 50 | 450 | 150 |

### 12.2. Partition Boundaries

At the first row of HN, even though HCM rows might precede it in display order, the window never pulls in HCM revenues. It **stops at the start of HN's partition**.

This differs from a collection-wide moving average. Omitting `partitionBy` puts all inputs in one partition and mixes stores.

### 12.3. Varying Window Widths

Valid examples for operators supporting bounded `documents` windows:

~~~javascript
// Current row only.
documents: ["current", "current"]

// Previous row and current row.
documents: [-1, 0]

// Two rows before and two rows after, including current.
documents: [-2, 2]

// From partition start to current row.
documents: ["unbounded", "current"]

// From current row to partition end.
documents: ["current", "unbounded"]

// Entire partition.
documents: ["unbounded", "unbounded"]
~~~

Numeric bounds in `documents` are **row position offsets**, not days, seconds, or revenue amounts.

---

## 13. Value-Based Windows: `range`

### 13.1. Distinguishing "Three Rows" from "Three Value Units"

`documents: [-2,0]` uses **two preceding rows**. `range: [-2,0]` uses **all rows whose `sortBy` field lies within `[currentValue - 2, currentValue]`**, per range window semantics.

Example `measurements` collection:

~~~javascript
db.measurements.insertMany([
  { _id: 1, sensor: "S1", minute: 1, value: 10 },
  { _id: 2, sensor: "S1", minute: 2, value: 20 },
  { _id: 3, sensor: "S1", minute: 2, value: 30 },
  { _id: 4, sensor: "S1", minute: 5, value: 40 }
]);
~~~

Value-based window on `minute`:

~~~javascript
db.measurements.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$sensor",
      sortBy: {
        minute: 1
      },
      output: {
        nearValueSum: {
          $sum: "$value",
          window: {
            range: [-2, 0]
          }
        }
      }
    }
  },
  {
    $sort: {
      sensor: 1,
      minute: 1,
      _id: 1
    }
  }
]);
~~~

At minute 2, `range: [-2, 0]` captures minutes 0 through 2, including minute 1 and **both minute-2 rows**, totaling `10 + 20 + 30 = 60`. At minute 5, it captures `[3, 5]`, yielding only `40`.

This highlights a vital difference from document-count windows: records with **tied `sortBy` values** are all included together in a value range, whereas a row-position `documents` window can cut right through the middle of tied values.

### 13.2. Key Rules for `range`

- A range window requires **a single field in `sortBy`**, in **ascending** order.
- For numeric ranges, the `sortBy` value must be a **number**.
- Range boundaries are evaluated on the **`sortBy` value** and are **inclusive on both ends**.
- `null`, missing, and incompatible types are excluded from numeric ranges per window rules.
- Never specify both `documents` and `range` inside the same `window`.

Do not write:

~~~javascript
// Invalid range window design:
{
  sortBy: {
    minute: 1,
    _id: 1
  },
  output: {
    moving: {
      $sum: "$value",
      window: {
        range: [-2, 0]
      }
    }
  }
}
~~~

because a range window permits only one `sortBy` field. If you need per-row tie-breaking and positional stability, use a **documents window** instead of `range`.

---

## 14. Time-Range Window: Revenue Over the Last Two Days

### 14.1. Problem

For each transaction row, compute revenue across records whose timestamp falls **within two days prior up to the current row's timestamp**, rather than taking just the prior two transactions.

Use a time-range window:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1
      },
      output: {
        revenueWithinTwoDays: {
          $sum: "$revenue",
          window: {
            range: [-2, "current"],
            unit: "day"
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

Requirements:

- `sortBy` has **one field** in **ascending** order.
- The `sortBy` field is a valid date/time type.
- `unit: "day"` specifies the time unit.
- Bounds `[-2, "current"]` span from two days prior through the current row's timestamp, inclusive on both ends.
- Time range bounds must use valid integer unit values; do not pass `-1.5` days expecting it to work.

### 14.2. Analyzing HCM

HCM data:

| ID | Date | Revenue |
|---:|---|---:|
| 1 | 01/01 | 100 |
| 2 | 02/01 | 200 |
| 3 | 02/01 | 200 |
| 4 | 04/01 | 50 |

- Row 1 (01/01): window 30/12–01/01 → 100.
- Rows 2 and 3 (02/01): window 31/12–02/01 → `100 + 200 + 200 =` **500** for **both rows sharing the same timestamp**.
- Row 4 (04/01): window 02/01–04/01 → `200 + 200 + 50 =` **450**.

Compared with the document-based running total:

| ID | Row-ordered running total | Two-day time-range total |
|---:|---:|---:|
| 1 | 100 | 100 |
| 2 | 300 | 500 |
| 3 | 500 | 500 |
| 4 | 550 | 450 |

Results differ **even though both use `$sum`**, because the window definitions differ.

### 14.3. Why Can't a Time-Range Window Use Two Sort Keys?

A time window is evaluated from **a single date/time value**. If sorted by both `day` and `_id`, there is no single "two days earlier" interval over the composite tuple. Therefore, for time ranges use:

~~~javascript
sortBy: {
  day: 1
}
~~~

And if stable display order is needed, append `$sort` after `$setWindowFields`:

~~~javascript
{
  $sort: {
    store: 1,
    day: 1,
    _id: 1
  }
}
~~~

### 14.4. `documents` and Time `range` Are Not Interchangeable

| Intent | Use |
|---|---|
| Revenue of the last 5 transactions | `documents:[-4,0]` |
| Revenue over the last 7 days | `range:[-7,"current"],unit:"day"` |
| Running total of all transactions up to current row | `documents:["unbounded","current"]` |
| Full partition total | Full partition window |
| Ranking by score/revenue | Rank operator without `window` |
| Exactly the 10 latest rows | `$documentNumber` with stable sort then filter |

---

## 15. Computing Share and Completion Percentage Using Two Windows

### 15.1. Question

"Up through the current transaction, what **percentage of the period's total store revenue** has the store achieved?"

Required pieces:

1. `runningRevenue` from start through current row.
2. `storeRevenue` across the entire partition.
3. `$divide` and `$multiply` to calculate the percentage.
4. Safe handling when the denominator is 0.

### 15.2. Pipeline

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        storeRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "unbounded"]
          }
        }
      }
    }
  },
  {
    $set: {
      runningSharePercent: {
        $cond: {
          if: {
            $gt: ["$storeRevenue", 0]
          },
          then: {
            $multiply: [
              {
                $divide: [
                  "$runningRevenue",
                  "$storeRevenue"
                ]
              },
              100
            ]
          },
          else: null
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      store: 1,
      seller: 1,
      runningRevenue: 1,
      storeRevenue: 1,
      runningSharePercent: 1
    }
  }
]);
~~~

HCM totals 550, giving row shares of roughly 18.18%, 54.55%, 90.91%, and 100%. HN totals 600. DN totals 0 and returns `null` for the percentage per the `$cond` policy, avoiding division-by-zero errors.

### 15.3. Single-Row Revenue Share Differs from Cumulative Share

If you want "what % of store total does the current transaction represent":

~~~javascript
{
  $divide: [
    "$revenue",
    "$storeRevenue"
  ]
}
~~~

after verifying numeric `revenue` and non-zero `storeRevenue`.

By contrast, `runningRevenue/storeRevenue` measures **cumulative** share. They are two different metrics; field names should reflect that clearly.

### 15.4. Never Assume Totals Are Always Non-Negative

When revenues include refunds or negative adjustments, a partition total can be 0 or negative. The `$gt: ["$storeRevenue", 0]` check above is an **example business rule**. In real systems, define how refunds, net revenue, and negative denominators should behave.

---

## 16. Duplicate Timestamps, Tied Scores, and Result Stability

### 16.1. For Running Totals: Row Order Matters

Two orders sharing a timestamp with different revenues:

~~~javascript
{ _id: 100, day: ISODate("2026-01-02T00:00:00Z"), revenue: 10 }
{ _id: 101, day: ISODate("2026-01-02T00:00:00Z"), revenue: 20 }
~~~

With `documents: ["unbounded","current"]`, whichever row comes first determines who gets running total 10 and who gets 30. Sorting only by `day` leaves tie order undefined.

Solution when deterministic row-level totals are needed:

~~~javascript
sortBy: {
  day: 1,
  _id: 1
}
~~~

If true business event order is required, use a source sequence number; `_id` provides deterministic tie-breaking, though it does not guarantee true transaction chronology.

### 16.2. For Ranking: Ties Must Be Preserved

Conversely, when ranking by revenue, two sellers with equal revenue must share the same rank. Do not add `_id` to the ranking criterion if it breaks ties, and `$rank`/`$denseRank` enforce a single `sortBy` field anyway.

Keep them separate:

~~~text
Ranking:
  sortBy revenue DESC
  => equal revenues receive equal rank

Display:
  $sort store ASC, rank ASC, _id ASC
  => tied rows render in deterministic order
~~~

### 16.3. For `$documentNumber`: Tie-Breakers Are Meaningful

`$documentNumber` assigns a unique sequence number per row in the partition, yet if sort keys are non-unique, which tied document gets 1 vs. 2 is non-deterministic. Use `sortBy: {revenue: -1, _id: 1}` when consistency matters.

### 16.4. `$setWindowFields` Does Not Guarantee Output Order

This is an easy mistake to miss:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Even with `sortBy` inside the stage, final output **is not guaranteed to arrive in that order**. Whenever a UI or report expects sorted results, append:

~~~javascript
{
  $sort: {
    store: 1,
    day: 1,
    _id: 1
  }
}
~~~

Never rely on incidental output order for tests or pagination.

---

## 17. Missing/Null and BSON Types in Accumulation and Ranking

### 17.1. `$sum` Does Not Turn Nulls into "Valid Revenue"

For DN:

~~~javascript
{ _id: 8, revenue: 0 }
{ _id: 9, revenue: null }
{ _id: 10 }
~~~

The running totals are 0, 0, 0. Yet the three rows mean very different things:

- ID 8 has a valid number 0.
- ID 9 has `revenue: null`.
- ID 10 is missing `revenue`.

If a report needs data-completeness visibility, add a tracking counter:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      revenueState: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$revenue" },
                  "missing"
                ]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: [
                  { $type: "$revenue" },
                  "null"
                ]
              },
              then: "NULL"
            },
            {
              case: {
                $isNumber: "$revenue"
              },
              then: "VALID"
            }
          ],
          default: "INVALID_TYPE"
        }
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        invalidCount: {
          $sum: {
            $cond: [
              { $eq: ["$revenueState", "VALID"] },
              0,
              1
            ]
          },
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: { store: 1, day: 1, _id: 1 }
  }
]);
~~~

DN receives `invalidCount` = 0, 1, 2 across its rows, preventing a total of 0 from being mistaken for clean input data.

### 17.2. Ranking with Null or Missing Fields

`$rank` and `$denseRank` use BSON comparison ordering to position documents with null/missing sort fields. **Starting in MongoDB 8.0, null and missing are treated equivalently during ranking with these operators**; older versions had differences to check when upgrading.

If business logic should exclude null/missing records from a leaderboard, **filter before ranking**:

~~~javascript
{
  $match: {
    revenue: {
      $type: "number"
    }
  }
}
~~~

Never implicitly assign "last place" to corrupt/missing data. An employee leaderboard missing revenue figures should normally report "insufficient data" separately.

### 17.3. String-Numbers Are Not Numbers

Example:

~~~javascript
{
  revenue: "200"
}
~~~

`$sum` does not treat that string as the number 200 for accounting. In ranking, mixing numbers and strings follows BSON type comparison order rather than numeric value order.

If historical records hold string numbers, consider normalizing in the pipeline:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      revenueNumber: {
        $convert: {
          input: "$revenue",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenueNumber",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

`$convert` with `onError` and `onNull` shields the pipeline from parse exceptions, yet collapsing parse errors and nulls into a single null can **mask data errors**. For financial reporting, retain a conversion status field or enforce validation at the source.

### 17.4. Avoid Inconsistent Numeric Types

MongoDB BSON includes int32, int64, double, and Decimal128. In financial reporting:

- If currency is stored in minor units as integers, watch range limits and overflow.
- If using Decimal128, standardize inputs and rounding rules.
- Avoid mixing numbers and strings and relying on undefined implicit coercions.
- A cumulative sum can grow larger than any single document value; choose a wide enough numeric type.

---

## 18. Mistakes Placing `$match` Before vs. After Window Analysis

### 18.1. Filtering Before Window Changes the **Accumulated Dataset**

Suppose you want HCM's running total **since the start of the month**, while the API only displays transactions from 02/01 onward.

If you write:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      store: "HCM",
      day: {
        $gte: ISODate("2026-01-02T00:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: { day: 1, _id: 1 }
  }
]);
~~~

transaction ID 1 from 01/01 was discarded before window calculation. ID 2's running total becomes **200**, instead of **300** for a month-to-date cumulative sum.

### 18.2. Filtering After Calculation Preserves History

~~~javascript
db.sales.aggregate([
  {
    $match: {
      store: "HCM"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $match: {
      day: {
        $gte: ISODate("2026-01-02T00:00:00Z")
      }
    }
  },
  {
    $sort: { day: 1, _id: 1 }
  }
]);
~~~

ID 2 gets `runningRevenue: 300` because ID 1 participated in the window. The trailing `$match` removes earlier documents only from the **final output**, not from the history used to compute the window.

### 18.3. Practical Rule

- `$match` defining the **analytical scope** (tenant, store, event type, calculation month) belongs before the window when appropriate.
- `$match` selecting the **display subset** without discarding prior cumulative history belongs after the window.
- `$match` on `rank <= N` naturally belongs after the stage that computes rank.
- On huge datasets, accumulating from the very beginning of time can be expensive; consider pre-aggregation or opening-balance snapshots instead of scanning unbounded history.

Never move `$match` back and forth solely to optimize scans if doing so alters metric semantics.

---

## 19. Partitioning by Tenant, Month, and Business Unit

### 19.1. Omitting `partitionBy` Merges All Inputs

Example:

~~~javascript
{
  $setWindowFields: {
    sortBy: { day: 1, _id: 1 },
    output: {
      runningRevenue: {
        $sum: "$revenue",
        window: {
          documents: ["unbounded", "current"]
        }
      }
    }
  }
}
~~~

Without `partitionBy`, the entire input becomes **a single partition**: HCM, HN, and DN revenues mix into one cumulative series.

### 19.2. Partitioning in Multi-Tenant Systems

In multi-tenant applications, filter strictly by authorized tenant first and partition by business unit:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      tenantId: "TENANT-01"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

This is a **structural example** for collections with `tenantId`; the Section 3 lab data does not have `tenantId`. In production, tenant authorization filtering is a security requirement—never rely on `partitionBy` as a substitute for access control.

If a pipeline legitimately analyzes multiple tenants together, include `tenantId` in the partition key so tenants never mix:

~~~javascript
partitionBy: {
  tenantId: "$tenantId",
  store: "$store"
}
~~~

### 19.3. Monthly Partitions: Should Cumulative Totals Reset Monthly?

If revenue must reset at the start of each month, compute `saleMonth` with `$dateTrunc`:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      saleMonth: {
        $dateTrunc: {
          date: "$day",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: {
        store: "$store",
        month: "$saleMonth"
      },
      sortBy: { day: 1, _id: 1 },
      output: {
        monthlyRunningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      saleMonth: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

Now the partition is **store + month**, so cumulative totals reset each new month. When `day` is UTC and business months follow Vietnam time, specifying `timezone` prevents misclassifying transactions near UTC midnight.

### 19.4. Documents Missing a Partition Key

If `store` is missing or null, multiple documents can fall into a single nullish partition depending on expression evaluation. Never let a report silently lump records with unknown stores together.

Options:

- Filter to documents with valid stores.
- Use `$ifNull` to route them into an `"UNKNOWN_STORE"` bucket for tracking.
- Reject malformed documents at the API or via JSON Schema validation.
- Build a separate data-quality report rather than mixing bad rows into official financial totals.

---

## 20. Window Calculation Order and Display Order Are Two Different Things

### 20.1. Window Sort Serves the Calculation

~~~javascript
sortBy: {
  day: 1,
  _id: 1
}
~~~

defines chronological order for calculating the running total.

### 20.2. Final Sort Serves the UI

~~~javascript
{
  $sort: {
    store: 1,
    day: -1,
    _id: -1
  }
}
~~~

lets the newest transaction appear first in the UI, **while `runningRevenue` was still computed in ascending chronological order** in the preceding stage.

Example for HCM:

| Descending display order | Revenue | Running from start of month |
|---:|---:|---:|
| ID 4 | 50 | 550 |
| ID 3 | 200 | 500 |
| ID 2 | 200 | 300 |
| ID 1 | 100 | 100 |

This is not a bug. Window `sortBy` governs calculation order; final `$sort` governs presentation order.

### 20.3. Be Careful with Pagination

If a pipeline computes a running total and then applies `$skip` and `$limit` at the end, metrics still reflect full history (correct when displaying one page of a cumulative ledger).

If `$skip`/`$limit` sits **before** the window stage, only surviving documents enter the calculation. Page 2 would then reset the running total at the top of the page—usually wrong for period-to-date reports.

On large collections, design pagination, checkpoints, or page-opening balances so reports stay both accurate and resource-efficient.

---

## 21. Performance: Sorting, Indexes, Memory, and Disk Spill

### 21.1. `$setWindowFields` Can Be Expensive

Window analytics require ordering and partition state. Across millions of rows:

- Sorting by `partitionBy`/`sortBy` must be performed.
- Partition/window state may be buffered in memory.
- Unbounded or wide windows demand significant resources.
- Multiple output operators or multiple `$setWindowFields` stages multiply computation.
- Skewed data with one giant partition can become a bottleneck.

Benchmark realistic workloads rather than assuming a window operation is as cheap as a simple addition.

### 21.2. Metrics to Monitor

- Overall pipeline latency and p95/p99.
- Document count entering `$setWindowFields`.
- Partition size distribution.
- Memory consumption and disk spills if any.
- Keys/documents examined in index-backed stages.
- CPU, disk I/O, server load, and impact on concurrent queries.
- Write rate and read-model refresh needs.

### 21.3. `allowDiskUse`

On versions/configurations supporting spill, you can enable:

~~~javascript
db.sales.aggregate(
  [
    {
      $setWindowFields: {
        partitionBy: "$store",
        sortBy: { day: 1, _id: 1 },
        output: {
          runningRevenue: {
            $sum: "$revenue",
            window: {
              documents: ["unbounded", "current"]
            }
          }
        }
      }
    }
  ],
  {
    allowDiskUse: true
  }
);
~~~

**Do not treat `allowDiskUse: true` as a guarantee that every pipeline runs fast or without resource caps.** It allows eligible stages to use temporary disk files per server rules, which increases I/O and latency.

Starting in MongoDB 6.0, `allowDiskUseByDefault` can change default behavior for memory-intensive stages; deployments vary by configuration. Across many releases, stages have roughly a 100 MB memory threshold under their respective rules. Always read docs for your exact running MongoDB version rather than assuming one fixed limit everywhere.

### 21.4. Indexes Supporting Filters and Sorts

Suppose queries consistently filter by store and order by day and `_id`:

~~~javascript
db.sales.createIndex(
  {
    store: 1,
    day: 1,
    _id: 1
  },
  {
    name: "idx_sales_store_day_id"
  }
);
~~~

This index can support query shapes with equality on `store` and sort on `day, _id`. However, **there is no guarantee** MongoDB will always use that index for every `$setWindowFields` pipeline; verify with `explain` on your actual version and dataset.

A pipeline:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      store: "HCM"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

can leverage an index to cut part of the access cost, yet it does not remove the need to measure sorting, memory, and window state.

### 21.5. Rank Indexes Differ from Cumulative Indexes

Two workloads:

~~~javascript
// Running total
sortBy: {
  day: 1,
  _id: 1
}
~~~

~~~javascript
// Ranking
sortBy: {
  revenue: -1
}
~~~

have completely different sort orders. An index tuned for chronological running totals does not necessarily help a revenue leaderboard.

Adding indexes indiscriminately for every ad-hoc query increases write amplification and storage footprint. Prioritize the most critical query shapes.

### 21.6. `explain`

~~~javascript
db.sales.explain("executionStats").aggregate([
  {
    $match: {
      store: "HCM"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Inspect the winning plan, sort stages, index scans, document counts, and memory-related stats if reported by your version. Explain structure for window stages varies across versions and engines; never write scripts assuming a fixed JSON path.

---

## 22. Large Reports: When to Pre-Aggregate or Materialize?

### 22.1. Daily Revenue Chart Problem

A store has millions of transactions over 5 years. The dashboard only needs a **cumulative daily revenue** chart, not individual transactions.

Running a window directly over every raw transaction can be expensive. An alternative strategy:

1. `$group` to sum revenue by **store + day**.
2. `$setWindowFields` over the **daily** revenue documents.
3. Compute running totals across a few thousand days instead of millions of transactions.
4. Choose how to store/refresh the summary appropriately for your system.

### 22.2. Two-Tier Pipeline

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $group: {
      _id: {
        store: "$store",
        day: "$day"
      },
      dailyRevenue: {
        $sum: "$revenue"
      },
      dailyTransactions: {
        $sum: 1
      }
    }
  },
  {
    $set: {
      store: "$_id.store",
      day: "$_id.day"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1
      },
      output: {
        cumulativeDailyRevenue: {
          $sum: "$dailyRevenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1
    }
  },
  {
    $project: {
      _id: 0,
      store: 1,
      day: 1,
      dailyRevenue: 1,
      dailyTransactions: 1,
      cumulativeDailyRevenue: 1
    }
  }
]);
~~~

For HCM, the two 02/01 transactions collapse into `dailyRevenue = 400`. Daily output:

| Date | Daily revenue | Cumulative |
|---|---:|---:|
| 01/01 | 100 | 100 |
| 02/01 | 400 | 500 |
| 04/01 | 50 | 550 |

**Do not apply this approach if the product needs per-transaction running totals**, since `$group` collapses same-day transactions.

### 22.3. Materialized Aggregates and Opening Balances

If a dashboard reads continuously, maintain a `daily_sales_summary` collection keyed by store/day, then run window calculations on that summary collection. Whenever historical data changes, update affected days and any materialized downstream cumulative totals.

Another pattern for huge ledgers:

- Store an **opening balance** or checkpoint per period.
- Run window calculations only over transactions after the checkpoint.
- Add the checkpoint balance to the in-period running sum.

This dramatically shrinks history scans, though it requires handling backdated events, edits/deletes, and checkpoint consistency carefully.

---

## 23. Reading vs. Writing: Aggregation Does Not Mutate the Collection

`$setWindowFields` in:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

produces a **read result**. It **does not write** `runningRevenue` back to documents in `sales`.

To materialize results, design a pipeline with an appropriate write stage such as `$merge` and dedicated operational controls, specifying:

- Unique key of the materialized collection.
- When recomputation runs.
- Whether historical edits invalidate subsequent running totals.
- Concurrent writers, transactions, and read concerns.
- Validation and rollback strategy.
- Indexes on the target collection.
- Idempotency rules.

Never assume `updateMany` with an update pipeline supports `$setWindowFields`. Window analytics is an aggregation stage with its own scope and restrictions; persisting results requires an intentional write pipeline.

---

## 24. Additional Useful Window Operators

Although this lesson focuses on ranking and cumulative sums, `$setWindowFields` supports many other window operators:

| Operator | Use Case |
|---|---|
| `$avg` | Moving average of revenue, temperature |
| `$min` / `$max` | Minimum / maximum value in the window |
| `$count` | Document count in the window |
| `$first` / `$last` | First / last value in the window |
| `$push` | List of values in the window |
| `$stdDevPop` / `$stdDevSamp` | Volatility / standard deviation |
| `$shift` | Value from a preceding/following row in the partition |
| `$expMovingAvg` | Exponential moving average |
| `$derivative` / `$integral` | Rate of change or integral over time in supported cases |

Operators have specific rules regarding version, `sortBy`, `window`, and data types; never assume every operator shares identical syntax.

### 24.1. Comparing with the Previous Transaction via `$shift`

Example:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        previousRevenue: {
          $shift: {
            output: "$revenue",
            by: -1,
            default: null
          }
        }
      }
    }
  },
  {
    $set: {
      revenueChange: {
        $cond: {
          if: {
            $and: [
              { $isNumber: "$revenue" },
              { $isNumber: "$previousRevenue" }
            ]
          },
          then: {
            $subtract: [
              "$revenue",
              "$previousRevenue"
            ]
          },
          else: null
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

`$shift` also uses an implicit window and **does not accept `window`**. `by: -1` reads the previous row; at the start of a partition it returns `default: null`. Use `$cond` to avoid subtraction errors when either value is non-numeric.

### 24.2. Do Not Overuse Operators Simultaneously

A pipeline needing only a running sum should not also compute rank, denseRank, documentNumber, rolling average, and shift "just in case." Every output field adds cost; compute only what users actually need.

---

## 25. Java Sync Driver Window Pipeline Example

Java applications can construct aggregation pipelines using `Document` or builders appropriate to the driver version.

Example computing running total per store:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class RunningRevenueExample {

    public static void run(MongoCollection<Document> sales) {

        Document window = new Document(
            "documents",
            Arrays.asList("unbounded", "current")
        );

        Document runningSum = new Document(
            "$sum",
            "$revenue"
        ).append(
            "window",
            window
        );

        Document output = new Document(
            "runningRevenue",
            runningSum
        );

        Document spec = new Document(
            "partitionBy",
            "$store"
        ).append(
            "sortBy",
            new Document("day", 1).append("_id", 1)
        ).append(
            "output",
            output
        );

        Bson windowStage = new Document(
            "$setWindowFields",
            spec
        );

        Bson finalSort = new Document(
            "$sort",
            new Document("store", 1)
                .append("day", 1)
                .append("_id", 1)
        );

        List<Bson> pipeline = Arrays.asList(
            windowStage,
            finalSort
        );

        sales.aggregate(pipeline)
            .forEach(System.out::println);
    }
}
~~~

In this example:

- `sales` is a `MongoCollection<Document>` obtained from a valid client connection.
- `Document("$setWindowFields", spec)` mirrors the exact MQL structure from `mongosh`.
- `windowStage` does not write data; `aggregate()` returns a readable cursor.
- The driver does not automatically coerce mistyped revenues; ensure clean schemas or convert before computing.
- For large results, avoid blindly calling `into(new ArrayList<>())` which can exhaust RAM; stream through the cursor with an appropriate batch size.

### 25.1. Java Leaderboard

Constructing the output:

~~~java
Document rankOutput = new Document(
    "competitionRank",
    new Document("$rank", new Document())
).append(
    "denseRank",
    new Document("$denseRank", new Document())
);

Document rankSpec = new Document(
    "partitionBy",
    "$store"
).append(
    "sortBy",
    new Document("revenue", -1)
).append(
    "output",
    rankOutput
);

Bson rankStage = new Document(
    "$setWindowFields",
    rankSpec
);
~~~

When using `$rank` and `$denseRank`, **do not add `window`** inside those output definitions.

### 25.2. DTO Design

If outputs contain Decimal128 revenues and integer ranks, DTOs should reflect the true data types. Avoid deserializing every field as a string only to re-parse and compute in Java.

Illustrative JSON response:

~~~json
{
  "store": "HCM",
  "seller": "Bình",
  "revenue": 200,
  "competitionRank": 1,
  "denseRank": 1
}
~~~

This represents an application presentation schema, not a guarantee of how BSON Decimal128 serializes to JSON across every driver.

---

## 26. Common Errors and How to Fix Them

### Error 1 — Forgetting `partitionBy` When Separate Accumulation Is Needed

**Symptom:** HCM's running total includes HN revenue.

**Cause:** Omitting `partitionBy` treats the entire input as one partition.

**Fix:** Add a partition key matching the business unit, possibly including tenant/store/month.

### Error 2 — Omitting `window` and Getting the Full Group Total

**Symptom:** Every HCM row shows 550 instead of 100, 300, 500, 550.

**Cause:** For supported operators, the default window spans the full partition.

**Fix:** Specify `documents: ["unbounded","current"]` for cumulative totals.

### Error 3 — Tied Ranks When Unique Sequence Numbers Were Wanted

**Symptom:** Two sellers both get rank 1 and rank 2 is missing.

**Cause:** `$rank` preserves ties and skips subsequent rank numbers.

**Fix:** Use `$denseRank` for gapless ranks, or `$documentNumber` for unique row numbers.

### Error 4 — Using `$denseRank` While Expecting Competition Rank Rules

**Symptom:** After two people tied at rank 1, the next person receives rank 2 instead of rank 3.

**Cause:** `$denseRank` produces no gaps.

**Fix:** Use `$rank` if business rules require competition ranking.

### Error 5 — Adding `_id` to `$rank`'s `sortBy`

**Symptom:** Error due to invalid `sortBy` or altered tie semantics.

**Cause:** Rank operators allow only one sort field.

**Fix:** Rank on one metric; add a trailing `$sort` with `_id` for stable display. Use `$documentNumber` when unique row numbering is needed.

### Error 6 — Specifying `window` on `$rank`

**Symptom:** Aggregation throws an error.

**Cause:** `$rank`, `$denseRank`, and `$documentNumber` use implicit windows and reject `window`.

**Fix:** Remove `window` from rank operator definitions.

### Error 7 — Assuming Stage `sortBy` Guarantees Output Order

**Symptom:** Returned documents occasionally appear out of expected UI order.

**Cause:** `$setWindowFields` does not guarantee output document order.

**Fix:** Add a trailing `$sort`.

### Error 8 — Same-Timestamp Transactions Make Running Totals Unpredictable

**Symptom:** Row-level cumulative values swap between same-day rows.

**Cause:** Sort keys do not define a total order.

**Fix:** Use `sortBy: {day: 1, _id: 1}` or a business sequence key.

### Error 9 — Using `documents` to Compute Over Days

**Symptom:** "Last 3 days" returns only the last 3 transactions, missing other same-day transactions.

**Cause:** `documents` counts row positions, not time spans.

**Fix:** Use time `range` with `unit: "day"` when calendar/time intervals are required.

### Error 10 — Using `range` with Multiple Sort Fields

**Symptom:** Invalid aggregation error.

**Cause:** Range and time-range windows require a single ascending `sortBy` field.

**Fix:** Use one numeric/date field for `range`; if multiple keys are needed to order rows, use a `documents` window.

### Error 11 — Filtering Dates Before Window Resets Totals

**Symptom:** Month-to-date running total omits revenue from earlier days.

**Cause:** Pre-window `$match` discarded needed historical rows.

**Fix:** Filter by store/tenant first, run the window, then filter display dates afterward—or use a valid opening balance.

### Error 12 — Ranking Transactions When Seller Ranking Was Wanted

**Symptom:** One seller appears multiple times with multiple ranks.

**Cause:** Forgot to `$group` down to one document per seller before ranking.

**Fix:** Group by seller/store/time bucket first, then rank the aggregated documents.

### Error 13 — Treating Null/Missing Revenue as Valid Zero

**Symptom:** Reports fail to flag records missing revenue.

**Cause:** `$sum` skips non-numeric values; sums can evaluate to 0.

**Fix:** Track `invalidCount`/`validRevenueCount` or enforce schema validation.

### Error 14 — Mixing String-Numbers and Numbers in Ranking

**Symptom:** Ranks do not match monetary order.

**Cause:** BSON cross-type comparison order or dirty data.

**Fix:** Standardize numeric types, use `$convert` with `onError`, and remediate data quality.

### Error 15 — Filtering `$rank <= N` When Exactly N Rows Were Wanted

**Symptom:** Receiving more or fewer than N rows due to ties.

**Cause:** `$rank` represents rank tiers, not unique row indices.

**Fix:** Use `$documentNumber` with a deterministic sort when exactly N rows are required.

### Error 16 — Too Much Data in a Single Partition

**Symptom:** High memory usage, disk spill, or slow queries.

**Cause:** Huge partition forcing large sorts and window state buffers.

**Fix:** Scope time ranges, pre-aggregate, add suitable indexes, monitor spills, and benchmark.

### Error 17 — Enabling `allowDiskUse` and Assuming No Problems Exist

**Symptom:** Query remains slow or I/O-heavy.

**Cause:** Spilling prevents OOM but is not a magic speedup.

**Fix:** Measure partition sizes, stage costs, memory, sorts, and intermediate volume.

### Error 18 — Confusing Read Aggregation with Collection Updates

**Symptom:** Pipeline output shows `runningRevenue`, yet collection documents lack the field.

**Cause:** `aggregate()` only reads and transforms returned results unless an explicit write stage is used intentionally.

**Fix:** To persist values, design a materialization pipeline with `$merge` plus update/reconciliation workflows.

---

## 27. Practice Exercises

### Exercise 1 — Running Total per Store

Using collection `sales`:

1. Write `$setWindowFields` partitioned by `store`.
2. Sort by ascending `day`, ascending `_id`.
3. Compute `runningRevenue` from partition start to current row.
4. Add a final `$sort` to inspect results.
5. Verify HCM yields 100, 300, 500, 550; HN yields 150, 300, 600.

### Exercise 2 — What Happens If `window` Is Omitted?

Rewrite Exercise 1 omitting `window` inside `$sum`. Explain why every HCM row gets 550. Demonstrate the difference between full-partition total and cumulative total.

### Exercise 3 — Ranking with Ties

Rank only documents with numeric revenue:

- `partitionBy: "$store"`.
- `sortBy: {revenue: -1}`.
- Output both `competitionRank` and `denseRank` together.

Explain the ranks for HCM revenues 200, 200, 100, 50 and HN revenues 300, 150, 150.

### Exercise 4 — Exactly Two Rows per Store

Use `$documentNumber` with `sortBy` descending revenue, ascending `_id`, keeping `rowNumber <= 2`. Compare the document count against `$rank <= 2` when ties exist.

### Exercise 5 — Top 2 Revenue Tiers

Use `$denseRank <= 2`. Which revenues does HCM return? How many rows does HN return? Explain why this differs from Top 2 rows.

### Exercise 6 — Moving Sum of Three Transactions

Using `documents: [-2, 0]`, compute moving sum and moving average across up to the last three HCM rows. Manually verify the result at `_id: 4`.

### Exercise 7 — How Do Two Days Differ from Three Transactions?

Use `range: [-2, "current"], unit: "day"`. Compute the time-range revenue for HCM's two 02/01 documents and the 04/01 document. Compare against `documents: [-2, 0]`.

### Exercise 8 — Cumulative Share Percentage

In one stage compute `runningRevenue` and `storeRevenue` (full partition), then compute `runningSharePercent`. Handle DN's `total = 0` safely without dividing by zero.

### Exercise 9 — Missing and Null

Using `$type`, `$isNumber`, and `$cond`:

- Count documents with numeric revenue per partition.
- Track cumulative null/missing/invalid counts.
- Explain why DN has `runningRevenue: 0` despite having data-quality errors.

### Exercise 10 — Filtering Before vs. After Window

Display HCM from 02/01 onward while keeping cumulative totals starting from 01/01. Write two pipelines with `$match` in different positions. Point out where `_id: 2` gets `runningRevenue: 200` vs. `300`.

### Exercise 11 — Monthly Seller Leaderboard

Insert multiple transactions for the same seller across multiple months. Use `$dateTrunc` with timezone `"Asia/Ho_Chi_Minh"`, `$group` revenue by store/month/seller, then apply `$denseRank` by descending `sellerRevenue`.

### Exercise 12 — Adding a Same-Timestamp Transaction

Insert a new HCM document on 02/01 with a different `_id`. Run cumulative sum with:

- `sortBy: {day: 1}` only.
- `sortBy: {day: 1, _id: 1}`.

Explain why only the second approach defines deterministic row-by-row running totals.

### Exercise 13 — Java Driver

Write a Java `Document` pipeline producing `runningRevenue`. Add a second pipeline for ranking, ensuring `window` is omitted from rank outputs. Stream results via cursor instead of loading everything into RAM.

### Exercise 14 — Optimizing Large Datasets

Suppose a collection has 50 million transactions and you only need cumulative daily revenue:

1. Propose an index supporting tenant/store/day if the workload fits.
2. `$group` by day before the window stage.
3. Measure `explain`, memory, spill, and p95 latency.
4. Propose a materialized daily summary or checkpoint design.
5. Explain how to handle a late-arriving transaction backdated to an earlier day.

---

## 28. Review Questions

1. In which MongoDB version was `$setWindowFields` introduced?
2. What is the core difference between `$group` and `$setWindowFields`?
3. What does `partitionBy` do, and what happens if it is omitted?
4. What is `sortBy` used for? Does it guarantee final output order?
5. Why does a running total require `documents: ["unbounded", "current"]`?
6. If `window` is omitted from `$sum`, what does the result represent?
7. What do `"current"` and `"unbounded"` bounds mean?
8. Which rows are included in `documents: [-2, 0]`?
9. How does `range: [-2, 0]` differ from `documents: [-2, 0]`?
10. What `sortBy` restriction applies to a time range with `unit: "day"`?
11. Why can two same-day documents share the same time-range sum while having different row-by-row running sums?
12. How do `$rank` and `$denseRank` differ regarding rank gaps?
13. How does `$documentNumber` differ from both rank operators?
14. Why don't rank operators accept a `window` parameter?
15. How many `sortBy` fields can `$rank` use?
16. How do you preserve ties in rank while keeping display order deterministic?
17. When you want exactly N rows, should you use rank or document number?
18. Why must `$group` run first when ranking sellers by total revenue?
19. Why can placing `$match` before the window stage change running totals?
20. How does `$sum` handle null/missing values, and what business risk does that pose?
21. What changed in how rank handles null/missing starting in MongoDB 8.0?
22. Why must string-numbers be normalized before ranking?
23. When should daily pre-aggregation precede a window stage?
24. What costs should be monitored when a single partition grows huge?
25. Why isn't `allowDiskUse` a complete optimization strategy by itself?
26. When should results be materialized, and how should historical updates be handled?
27. How do you separate window calculation order from UI display order?
28. Why shouldn't `$skip`/`$limit` precede the window stage when computing period-to-date totals?

---

## 29. Summary

`$setWindowFields` is an essential MongoDB Aggregation stage for computing metrics **per document while referencing other documents in the same group**.

- **`partitionBy`** determines how calculations are grouped by store, tenant, seller, or time period.
- **`sortBy`** defines ordering for window calculations.
- **`output` and `window`** specify the operators and span each row sees.
- **`$rank`** preserves ties and skips subsequent rank numbers.
- **`$denseRank`** preserves ties without skipping rank numbers.
- **`$documentNumber`** assigns a unique sequence number to each document.
- **`$sum` with `documents: ["unbounded", "current"]`** computes cumulative totals from partition start to the current row.
- **`documents`** operates by row position; **`range`** operates by numeric/date value under specific rules.

Four core habits when implementing window pipelines:

1. **Clearly define the unit of analysis:** transaction, employee, store, day, or month.
2. **Ensure meaningful ordering:** tie-breakers for row-level running totals, deliberate tie preservation for rankings.
3. **Distinguish valid values from missing/null/wrong types** instead of confusing zero revenue with missing data.
4. **Verify both correctness and execution cost:** trailing `$sort`, `explain`, indexes, memory, disk spills, and pre-aggregation options.

A good window pipeline does more than output neat numbers—it answers the exact business question: **who is ranked under what rules, over what scope are totals accumulated, and will results stay stable and reliable as data grows or changes**.

## Official MongoDB References

- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — $rank](https://www.mongodb.com/docs/manual/reference/operator/aggregation/rank/)
- [MongoDB Manual — $denseRank](https://www.mongodb.com/docs/manual/reference/operator/aggregation/denseRank/)
- [MongoDB Manual — $documentNumber](https://www.mongodb.com/docs/manual/reference/operator/aggregation/documentNumber/)
- [MongoDB Manual — $sum](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/)
- [MongoDB Manual — $avg](https://www.mongodb.com/docs/manual/reference/operator/aggregation/avg/)
- [MongoDB Manual — $count (window expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count-accumulator/)
- [MongoDB Manual — $shift](https://www.mongodb.com/docs/manual/reference/operator/aggregation/shift/)
- [MongoDB Manual — $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB Manual — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — MongoDB 8.0 Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/8.0-compatibility/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
