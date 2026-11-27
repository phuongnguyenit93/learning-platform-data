# Multi-Branch Aggregation with $facet and Its Dedicated Memory Limit in MongoDB

## 1. Why Is $facet Needed?

On a product listing page, an application often needs to return **multiple perspectives over the same dataset**: the first few products, total matching count, counts by category, price ranges, brands, and inventory statistics. Running each query independently requires sending multiple commands to MongoDB and duplicating part of the filtering logic.

**`$facet`** is an **aggregation stage** that executes **multiple independent sub-pipelines** over the **same input document stream**, then returns **a single document** containing each branch's results as separate **arrays**.

Example of desired output:

~~~javascript
{
  products: [ /* products on the current page */ ],
  totalCount: [ { total: 11 } ],
  byCategory: [ /* counts per category */ ],
  byBrand: [ /* counts per brand */ ],
  priceRanges: [ /* price buckets */ ]
}
~~~

With `$facet`, all branches see **the same input produced by stages preceding `$facet`**, yet each branch can filter, group, sort, or limit independently.

This lesson focuses on:

1. Data flow through `$facet` and multi-branch syntax.
2. Distinguishing **shared pre-facet filtering** from **branch-specific filtering**.
3. Designing metadata, pagination, statistics, `$bucket`, and `$sortByCount`.
4. **`$facet`'s dedicated memory limit**: 100 MB for the intermediate document built by the stage, without `allowDiskUse` spilling; final output is still subject to the **16 MiB BSON** limit.
5. Disallowed stages inside facets and how to leverage indexes.
6. Inspecting with `explain()`, handling empty results, optimizing memory, and deciding when not to use `$facet`.

## 2. Syntax and Data Flow Diagram

General syntax:

~~~javascript
db.collection.aggregate([
  { $match: { /* shared condition */ } },
  {
    $facet: {
      branchA: [
        { /* stage A1 */ },
        { /* stage A2 */ }
      ],
      branchB: [
        { /* stage B1 */ }
      ],
      branchC: [
        { /* stage C1 */ }
      ]
    }
  }
]);
~~~

Each **branch name** (`branchA`, `branchB`, ...) becomes an **array field** in the output document. Each branch is an array of aggregation stages valid inside `$facet`.

~~~text
                      orders / products
                              |
                              v
                     $match (SHARED filter)
                              |
                              v
                    +---------+---------+
                    |       $facet      |
                    +---------+---------+
                       /      |       \
                      v       v        v
                  products  category   price
                    |         |         |
                  $sort     $group     $bucket
                    |         |         |
                  $limit    $sort     [buckets]
                    |         |         |
                    +---------+---------+
                              |
                              v
                   SINGLE OUTPUT DOCUMENT
        {
          products: [ ... ],
          category: [ ... ],
          price:    [ ... ]
        }
~~~

Branches share three key properties:

- **Shared input:** all receive the document set passed into `$facet`.
- **Independence:** one branch never alters another branch's input or output. A `$limit` in `products` does not restrict how many documents `category` sees.
- **No direct cross-branch piping:** you cannot write a sub-pipeline expecting to read another branch's output inside the same `$facet`. To combine the generated arrays, place **stages after `$facet`**.

**Do not confuse** `$facet` with issuing multiple independent aggregations from the application. `$facet` shares the input stream and returns one aggregated document, yet carries different memory constraints and indexing behavior than separate queries.

## 3. Preparing mongosh Data

Open `mongosh`, connect to MongoDB, and create a dedicated database:

~~~javascript
const lab = db.getSiblingDB("facet_memory_lab");

// Drop only the collection dedicated to this practice lesson.
lab.products.drop();

lab.products.insertMany([
  {
    _id: 101,
    name: "Laptop Air",
    category: "laptop",
    brand: "Nova",
    price: 1200,
    rating: 4.7,
    stock: 6,
    status: "active",
    tags: ["portable", "sale"]
  },
  {
    _id: 102,
    name: "Laptop Pro",
    category: "laptop",
    brand: "Nova",
    price: 1900,
    rating: 4.9,
    stock: 2,
    status: "active",
    tags: ["premium"]
  },
  {
    _id: 103,
    name: "Laptop Lite",
    category: "laptop",
    brand: "Orion",
    price: 800,
    rating: 4.0,
    stock: 0,
    status: "active",
    tags: ["budget"]
  },
  {
    _id: 104,
    name: "Phone Mini",
    category: "phone",
    brand: "Nova",
    price: 450,
    rating: 4.3,
    stock: 11,
    status: "active",
    tags: ["portable", "budget"]
  },
  {
    _id: 105,
    name: "Phone Max",
    category: "phone",
    brand: "Orion",
    price: 950,
    rating: 4.8,
    stock: 3,
    status: "active",
    tags: ["premium", "sale"]
  },
  {
    _id: 106,
    name: "Phone Old",
    category: "phone",
    brand: "Nova",
    price: 300,
    rating: 3.8,
    stock: 0,
    status: "archived",
    tags: ["sale"]
  },
  {
    _id: 107,
    name: "Keyboard",
    category: "accessory",
    brand: "Orion",
    price: 100,
    rating: 4.4,
    stock: 18,
    status: "active",
    tags: ["office"]
  },
  {
    _id: 108,
    name: "Mouse",
    category: "accessory",
    brand: "Nova",
    price: 60,
    rating: 4.2,
    stock: 40,
    status: "active",
    tags: ["office", "sale"]
  },
  {
    _id: 109,
    name: "Headphones",
    category: "accessory",
    brand: "Sonic",
    price: 180,
    rating: 4.6,
    stock: 8,
    status: "active",
    tags: ["portable"]
  },
  {
    _id: 110,
    name: "Monitor",
    category: "accessory",
    brand: "Sonic",
    price: 350,
    rating: 4.7,
    stock: 5,
    status: "active",
    tags: ["office", "premium"]
  },
  {
    _id: 111,
    name: "Tablet",
    category: "tablet",
    brand: "Nova",
    price: 700,
    rating: 4.5,
    stock: 4,
    status: "active",
    tags: ["portable"]
  },
  {
    _id: 112,
    name: "MongoDB Book",
    category: "book",
    brand: "Paper",
    price: 40,
    rating: 4.9,
    stock: 25,
    status: "active",
    tags: ["learning"]
  }
]);

lab.products.find({}, {
  name: 1,
  category: 1,
  brand: 1,
  price: 1,
  stock: 1,
  status: 1
}).sort({ _id: 1 });
~~~

There are **12 products** in total: **11 active** and **1 archived** (`_id = 106`).

For reference verification, the active set has:

| Category | Active Product Count |
| --- | ---: |
| accessory | 4 |
| laptop | 3 |
| phone | 2 |
| book | 1 |
| tablet | 1 |
| **Total** | **11** |

Across this same active set, total inventory is **122** units, with **10 in-stock products** and **1 product with stock = 0**. The `price` values are simple numbers for price-bucketing illustration; real financial systems should consider `Decimal128` and rounding rules.

## 4. First Facet: Listing and Count Over the Same Filtered Set

A product page needs two things:

- `data` array: the three most expensive currently active products.
- `metadata` array: total count of active products, **not just counting the three items on the page**.

~~~javascript
const firstFacet = [
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            name: 1,
            category: 1,
            price: 1
          }
        }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
];

lab.products.aggregate(firstFacet).toArray();
~~~

Output shape:

~~~javascript
[
  {
    data: [
      { _id: 102, name: "Laptop Pro",
        category: "laptop", price: 1900 },
      { _id: 101, name: "Laptop Air",
        category: "laptop", price: 1200 },
      { _id: 105, name: "Phone Max",
        category: "phone", price: 950 }
    ],
    metadata: [
      { total: 11 }
    ]
  }
]
~~~

Note the **two array levels** here:

1. `aggregate(...).toArray()` returns the cursor's result array; here it holds **one document**.
2. That document holds the **`data` and `metadata` arrays** produced by the facet branches.

`$limit: 3` sits **inside the `data` branch**, so `metadata` still counts all 11 active documents.

### 4.1. Logic Bug When Placing $limit Too Early

The following example **fails the goal of counting all active products**:

~~~javascript
// WRONG if metadata needs the total across all active products.
lab.products.aggregate([
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  { $limit: 3 },
  {
    $facet: {
      data: [{ $project: { name: 1, price: 1 } }],
      metadata: [{ $count: "total" }]
    }
  }
]);
~~~

Placing `$limit: 3` **before `$facet`** leaves **both branches** seeing only three products. `metadata` then reports `total: 3` instead of 11.

Rule: **shared filters** go before facet when all branches must respect them; **branch-specific limits** go inside the right branch.

## 5. Multiple Summary Branches: Category, Brand, Price, and Stock

A dashboard may need multiple analytical dimensions in one response. Run the pipeline:

~~~javascript
const dashboard = [
  {
    $match: {
      status: "active"
    }
  },
  {
    $facet: {
      products: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            name: 1,
            category: 1,
            brand: 1,
            price: 1
          }
        }
      ],

      totalCount: [
        { $count: "total" }
      ],

      byCategory: [
        { $sortByCount: "$category" },
        { $sort: { count: -1, _id: 1 } }
      ],

      byBrand: [
        {
          $group: {
            _id: "$brand",
            count: { $sum: 1 }
          }
        },
        { $sort: { count: -1, _id: 1 } }
      ],

      priceRanges: [
        {
          $bucket: {
            groupBy: "$price",
            boundaries: [0, 100, 500, 1000, 2000],
            default: "other",
            output: { count: { $sum: 1 } }
          }
        }
      ],

      stockStats: [
        {
          $group: {
            _id: null,
            totalStock: { $sum: "$stock" },
            inStockProducts: {
              $sum: {
                $cond: [
                  { $gt: ["$stock", 0] },
                  1,
                  0
                ]
              }
            }
          }
        },
        {
          $project: {
            _id: 0,
            totalStock: 1,
            inStockProducts: 1
          }
        }
      ]
    }
  }
];

const result = lab.products.aggregate(dashboard).toArray();

printjson(result[0]);
~~~

All **six branches** receive the input set of 11 active products. Each branch transforms **its own output** without altering any other branch's input.

### 5.1. The byCategory Branch and $sortByCount

`$sortByCount: "$category"` is conceptually equivalent to `$group` by category, counting documents, and sorting by descending count. The sample data produces:

~~~javascript
[
  { _id: "accessory", count: 4 },
  { _id: "laptop", count: 3 },
  { _id: "phone", count: 2 },
  { _id: "book", count: 1 },
  { _id: "tablet", count: 1 }
]
~~~

`$sort: { count: -1, _id: 1 }` is added after `$sortByCount` to guarantee **deterministic ordering when groups tie on count**. If a chart does not care about tie-break ordering, that extra sort stage can be omitted.

### 5.2. The byBrand Branch and $group

Expected result:

| Brand | Active Product Count |
| --- | ---: |
| Nova | 5 |
| Orion | 3 |
| Sonic | 2 |
| Paper | 1 |
| **Total** | **11** |

`$group` fits when you need accumulators such as `$avg`, `$sum`, `$min`, `$max`, or `$addToSet`. Do not write `$group` thinking it "branches": **`$facet` creates branches, `$group` aggregates within one branch**.

### 5.3. The priceRanges Branch and $bucket

`boundaries` must be ascending thresholds. Each bucket represents an interval **inclusive of the lower bound and exclusive of the upper bound**:

| Bucket | Price Interval | Product Count |
| --- | --- | ---: |
| `_id: 0` | [0, 100) | 2 |
| `_id: 100` | [100, 500) | 4 |
| `_id: 500` | [500, 1000) | 3 |
| `_id: 1000` | [1000, 2000) | 2 |
| `"other"` | Outside declared intervals | 0 (no other bucket appears in the sample data) |

At price exactly `100`, a product belongs to bucket `[100, 500)`, not `[0, 100)`. When `default: "other"` is specified, values outside the intervals (or non-matching types per grouping rules) are routed to the default bucket.

Do not use `$bucketAuto` when business rules define **fixed price tiers**. `$bucketAuto` picks boundaries from data distribution and may not suit price labels that must remain stable across runs.

### 5.4. The stockStats Branch

Result:

~~~javascript
stockStats: [
  {
    totalStock: 122,
    inStockProducts: 10
  }
]
~~~

`stockStats` holds **one object** in its array because `$group: { _id: null }` collapses all input into a single group.

**Important check:** `inStockProducts` counts documents with `stock > 0`; it is **not** the total stock units. The pair `10` and `122` measure two different quantities.

## 6. Scoping Individual Branches Without Corrupting Statistics

Suppose the shared filter is **status active**, and the user filters to brand Nova. Two distinct business requirements arise:

**Requirement A — every facet is scoped to brand Nova:** put `brand: "Nova"` in `$match` before `$facet`. Then total, byCategory, and priceRanges all reflect only Nova.

**Requirement B — listing shows Nova, yet the brand sidebar still shows counts across all active brands:** put the brand filter **inside the `data` branch**, so the brand statistics branch still sees all active products.

Example for Requirement B:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $match: { brand: "Nova" } },
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, brand: 1, price: 1 } }
      ],
      allBrands: [
        { $sortByCount: "$brand" }
      ]
    }
  }
]).toArray();
~~~

The `data` branch returns Nova's three priciest products (Laptop Pro, Laptop Air, Tablet), while `allBrands` still includes Nova/Orion/Sonic/Paper. **The two results do not contradict each other**: the branches apply **different filters after receiving the same input**.

Deciding whether a filter goes before or inside facet must follow the **search screen's contract**, not performance alone.

## 7. How Does `$facet` Build Its Output Document?

`$facet` normally produces **one document** containing one array field per branch. Each branch can emit 0, 1, or many documents; they are placed into its corresponding array.

Example:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      highPrice: [
        { $match: { price: { $gt: 10000 } } },
        { $project: { name: 1 } }
      ],
      allActive: [
        { $count: "n" }
      ]
    }
  }
]).toArray();
~~~

Result:

~~~javascript
[
  {
    highPrice: [],
    allActive: [ { n: 11 } ]
  }
]
~~~

A branch with no matching documents yields an empty array `[]`, **without dropping the entire output document**.

### 7.1. `$count` on an Empty Set

~~~javascript
lab.products.aggregate([
  { $match: { status: "does-not-exist" } },
  {
    $facet: {
      data: [{ $limit: 3 }],
      metadata: [{ $count: "total" }]
    }
  }
]).toArray();
~~~

Result:

~~~javascript
[
  {
    data: [],
    metadata: []
  }
]
~~~

With zero input documents, `$count` **does not emit a document with total = 0**; it emits **no document at all**. Hence `metadata` is an empty array. The API should normalize it to 0 when required.

### 7.2. Normalizing Output After `$facet`

For REST APIs, you often want:

~~~javascript
{
  data: [ /* ... */ ],
  total: 11
}
~~~

instead of:

~~~javascript
{
  data: [ /* ... */ ],
  metadata: [{ total: 11 }]
}
~~~

Add a `$project` **after** facet:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, price: 1 } }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  },
  {
    $project: {
      _id: 0,
      data: 1,
      total: {
        $ifNull: [
          { $arrayElemAt: ["$metadata.total", 0] },
          0
        ]
      }
    }
  }
]).toArray();
~~~

`$arrayElemAt` extracts the first element of the `metadata.total` values array, and `$ifNull` falls back to 0 when empty. This cleanly maps facet output to the response contract.

**Warning:** `$project` after `$facet` simplifies the response and drops the redundant `metadata` array, yet **it cannot prevent errors if `$facet` itself already exceeded the 100 MB memory limit or BSON limits before shrinking**. Size must be controlled via **inputs or inside the branches**.

## 8. Dedicated Memory Limit of `$facet`

This is the core focus of the lesson.

Per the MongoDB Manual, **while stages inside `$facet` execute, the output document constructed by `$facet` is limited to 100 MB**. If `$facet` builds a document exceeding this limit, MongoDB throws an **`ExceededMemoryLimit`** error.

Specifically:

- **`$facet` cannot spill to disk** to bypass its stage-specific 100 MB limit.
- Setting **`allowDiskUse: true` does not change `$facet`'s 100 MB limit**.
- The final document returned by the aggregation must still satisfy the **16 MiB BSON limit**.
- Because facet output packs **multiple arrays into a single document**, the combined size of those arrays easily becomes a bottleneck at scale.

### 8.1. Two Distinct Thresholds

| Limit | Where Does It Apply? | Can `allowDiskUse` Exceed It? |
| --- | --- | --- |
| **100 MB** | Intermediate document built by `$facet` during execution | **No**: `$facet` does not spill |
| **16 MiB BSON** | Each final output document of the aggregation | **No** |
| **Memory limit of other stages** | E.g., `$sort`, `$group`, `$bucket` depending on version | **Potentially**, if the stage supports spilling and settings allow |
| **Client RAM limit** | Calling `toArray()` or buffering huge responses | Application-dependent; not removed by MongoDB |

**Do not mistakenly believe each branch gets its own 100 MB budget and you can sum dozens of branches into an unbounded output.** All branches are **packed into the same `$facet` document**, so their combined size must be controlled.

**Do not mistakenly believe 100 MB is the allowed final document size returned to clients.** MongoDB allows at most **16 MiB per BSON result document**; intermediate values larger than 16 MiB may exist during pipeline execution in supported cases, but they must be shrunk validly before final output and stay under 100 MB in `$facet`.

### 8.2. Why Does `$facet` Hit Limits More Easily Than Multi-Row Queries?

Compare:

~~~text
Without $facet:
  aggregate() -> doc1 -> doc2 -> doc3 -> ... -> cursor
  Each result document has its own BSON limit.
  The cursor streams documents in batches.

With $facet:
  aggregate() -> {
    branchA: [doc1, doc2, doc3, ...],
    branchB: [x1, x2, x3, ...]
  }
  All elements sit inside ONE single BSON document.
~~~

If `products` returns hundreds of thousands of products with images, long descriptions, and tags while `byCategory` holds thousands of groups, the facet output exceeds 16 MiB **even if the client sets `batchSize: 1`**.

Cursor batch size controls **how many result documents are fetched per network batch**—it **never splits arrays inside a single facet document**. Calling `toArray()`, `batchSize`, or `limit()` **after** facet will not fix an oversized facet document.

### 8.3. How Is `allowDiskUse` Different?

In general aggregations, blocking stages such as `$sort` or `$group` have memory thresholds and, when eligible, can spill temporary files to disk if `allowDiskUse` is enabled. Starting in MongoDB 6.0, `allowDiskUseByDefault` governs the default spilling behavior for spill-capable stages.

Example:

~~~javascript
lab.products.aggregate(
  [
    { $match: { status: "active" } },
    { $sort: { price: -1 } },
    { $group: { _id: "$category", count: { $sum: 1 } } }
  ],
  { allowDiskUse: true }
);
~~~

Certain pipeline stages **outside `$facet`** can use memory/disk according to their own rules. However, running:

~~~javascript
// Does NOT make $facet a spill-capable stage.
lab.products.aggregate(
  [
    {
      $facet: {
        allDocuments: [
          { $project: { name: 1, category: 1, price: 1 } }
        ]
      }
    }
  ],
  { allowDiskUse: true }
);
~~~

has **no exception** allowing `$facet` to hold an array exceeding its limit. When returning large numbers of documents, design a **multi-document streaming cursor** or separate reporting queries from listing queries rather than packing everything into one document.

### 8.4. Version-Specific Thresholds and Other Limits

Beyond `$facet`'s dedicated limit, MongoDB enforces overall limits on document size, pipeline stage count, per-stage memory, and in newer versions **operation-wide memory limits**. For example, MongoDB 9.0 documents an operation-level memory cap mechanism.

**Never infer from a global server setting like `allowDiskUseByDefault` that `$facet` is permitted to spill.** Consult docs for your exact running version and distinguish:

- `$facet`'s own intermediate document budget.
- `$sort`/`$group` stage memory under their own rules.
- Single BSON result document limit.
- Client memory when receiving responses.
- Operation-level and deployment resource limits.

## 9. An Example Likely to Fail Due to Memory

Suppose a real collection has 500,000 products, each carrying long descriptions, images, specs, and metadata. The following pipeline **packs every document** into one branch:

~~~javascript
// ANTI-PATTERN on large datasets: facet output can grow too large.
db.bigProducts.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      allRows: [
        { $project: { _id: 1, name: 1, description: 1, images: 1 } }
      ],
      total: [
        { $count: "n" }
      ]
    }
  }
], { allowDiskUse: true });
~~~

Problems:

1. `allRows` constructs an **array containing every active product**.
2. The facet document holds `allRows` plus `total` plus BSON overhead.
3. Element count and per-element size easily push the facet document past 16 MiB and/or 100 MB.
4. `allowDiskUse: true` does not make `$facet` safe for holding the whole array.
5. Once the server errors, shrinking cursor `batchSize` will not shrink the facet document.

The fix must change the **output shape**, not just toggle an option.

### 9.1. Genuinely Bounding the Listing Branch

~~~javascript
db.bigProducts.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      page: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $limit: 20 },
        {
          $project: {
            _id: 1,
            name: 1,
            category: 1,
            price: 1
          }
        }
      ],
      total: [
        { $count: "n" }
      ]
    }
  }
]);
~~~

The `page` branch keeps at most 20 **compact** documents, and `total` produces one count document. These two changes drastically cut facet output size.

However, `$sort` inside `page` may still process a large input stream and cannot directly use a source collection index from inside the facet. To optimize sorting, see the indexing section and evaluate the trade-off between one shared facet and two separate queries.

### 9.2. Keep Only Aggregated Data in Summary Branches

Do not write:

~~~javascript
// PRONE TO BLOAT: pushing entire documents into an array.
{
  $group: {
    _id: "$category",
    allProducts: { $push: "$$ROOT" }
  }
}
~~~

if you only need the count per category. Replace with:

~~~javascript
{
  $group: {
    _id: "$category",
    count: { $sum: 1 }
  }
}
~~~

If you need representative product samples per category, bound the sample sensibly using version-appropriate sorting/slicing, but avoid `$push: "$$ROOT"` across all documents. A group branch emitting only a few group documents **can still contain giant arrays inside each document**.

## 10. Optimizing in Order: Shrink Input, Shrink Fields, Shrink Output

There are three places to cut cost:

~~~text
Collection
   |
   v
[1] Early $match and appropriate $project
   |
   v
$facet
  |-- [2] branch A: $sort + $limit + $project
  |-- [2] branch B: $group -> counts/sums/avgs only
  |-- [2] branch C: $bucket -> compact output
   |
   v
[3] Final $project/$set -> API-ready response
~~~

### 10.1. Shared Filtering Before Facet

~~~javascript
lab.products.aggregate([
  {
    $match: {
      status: "active",
      price: { $gte: 100 }
    }
  },
  {
    $facet: {
      byCategory: [{ $sortByCount: "$category" }],
      total: [{ $count: "n" }]
    }
  }
]);
~~~

Only active products priced at 100 or above enter `$facet`. This reduces the documents buffered/processed and gives filters a chance to use indexes.

If a filter belongs only to one branch, never lift it outside mechanically: doing so corrupts the other branches.

### 10.2. Project Out Heavy Fields Before Facet When No Branch Needs Them

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $project: {
      name: 1,
      category: 1,
      brand: 1,
      price: 1,
      stock: 1
    }
  },
  {
    $facet: {
      byCategory: [{ $sortByCount: "$category" }],
      byBrand: [{ $sortByCount: "$brand" }],
      totalStock: [
        {
          $group: {
            _id: null,
            n: { $sum: "$stock" }
          }
        }
      ]
    }
  }
]);
~~~

Now branches do not carry `tags`, `description`, `images`, or unused fields. Still, **do not strip `price` if another branch needs it**, and do not assume an early `$project` is always faster since the MongoDB optimizer already prunes unused fields when safe.

### 10.3. Bound Inside the Right Branch

~~~javascript
{
  $facet: {
    topProducts: [
      { $sort: { price: -1, _id: 1 } },
      { $limit: 5 },
      { $project: { name: 1, price: 1 } }
    ],
    byCategory: [
      { $sortByCount: "$category" }
    ]
  }
}
~~~

Limiting `topProducts` does not affect counts in `byCategory`.

When sorting on a **field without a tie-breaker**, products with identical prices can change order across runs. Add `_id` as a secondary sort key when deterministic ordering is required.

### 10.4. Keep Only API-Needed Fields After Facet

~~~javascript
{
  $project: {
    _id: 0,
    page: 1,
    total: {
      $ifNull: [
        { $arrayElemAt: ["$metadata.total", 0] },
        0
      ]
    }
  }
}
~~~

This is response formatting, **not a substitute for bounding arrays inside the facet**. Once a branch pushes `$facet` past 100 MB, downstream stages never get a chance to fix it.

## 11. `$facet` and Indexes: Stage Placement Matters

Per the MongoDB Manual:

- If **`$facet` is the first stage**, it performs a **COLLSCAN** and does not use indexes to select input.
- If stages before `$facet` use indexes (such as `$match` or `$sort`), `$facet` **does not force the server to re-scan the entire collection** from scratch.
- **Branches inside `$facet` do not regain independent collection/index access like standalone queries.** They operate on the document stream handed into `$facet`.

### 11.1. Creating an Index for Shared Filtering

~~~javascript
lab.products.createIndex(
  { status: 1, price: -1, _id: 1 },
  { name: "ix_status_price_id" }
);
~~~

A pipeline can leverage the index:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  {
    $facet: {
      page: [
        { $limit: 3 },
        { $project: { name: 1, price: 1 } }
      ],
      total: [
        { $count: "n" }
      ]
    }
  }
]);
~~~

Pro: `$match` and `$sort` sit **before `$facet`**, allowing them to use the collection's compound index. Con: **every document entering all branches** passes through `$sort`, even though `total` does not care about order. With millions of documents, measure the cost rather than assuming pre-facet sorting is always faster.

### 11.2. Sorting Inside a Branch vs. Sorting Before Facet

Compare:

~~~javascript
// A. Sort inside the branch:
[
  { $match: { status: "active" } },
  {
    $facet: {
      page: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 }
      ],
      total: [{ $count: "n" }]
    }
  }
]
~~~

with:

~~~javascript
// B. Sort before facet:
[
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  {
    $facet: {
      page: [{ $limit: 3 }],
      total: [{ $count: "n" }]
    }
  }
]
~~~

Both pipelines return the same page and total on the sample dataset, yet **execution plans and memory usage differ**. In B, an index can satisfy the outer sort; in A, the branch-local sort must sort the stream arriving at `$facet`. When only `page` needs sorting, A avoids sorting for the whole pipeline, though it cannot use the collection index the same way. Always inspect `explain()` and metrics on realistic workloads.

### 11.3. Inspecting explain

~~~javascript
lab.products.explain("executionStats").aggregate([
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  {
    $facet: {
      page: [{ $limit: 3 }],
      total: [{ $count: "n" }]
    }
  }
]);
~~~

Inspect pre-facet stage plans, scan type, `totalKeysExamined`, `totalDocsExamined`, and any sort/memory indicators reported by your server version.

Since the lab dataset has only 12 documents, the optimizer may choose **COLLSCAN** over an index because scanning 12 documents is cheaper. Never draw broad conclusions from a tiny test. Furthermore, optimized stages in `explain` do not always map 1-to-1 to the source pipeline stages.

## 12. Stages Disallowed Inside `$facet` Sub-Pipelines

Not every aggregation stage is permitted inside a facet branch. Per MongoDB documentation, the following stages **cannot** be placed inside `$facet`:

- `$collStats`
- `$facet`
- `$geoNear`
- `$indexStats`
- `$out`
- `$merge`
- `$planCacheStats`
- `$search`
- `$searchMeta`
- `$vectorSearch`

Specifically:

1. **Do not nest a second `$facet`** directly inside a facet branch.
2. **Do not write to collections** using `$out` or `$merge` inside a facet sub-pipeline.
3. **Do not place `$search` or `$vectorSearch` inside a facet branch**. If search is required, run the Search stage in a supported outer position and facet its output, or split into separate queries.
4. Server metadata/stats stages such as `$indexStats` are invalid inside sub-pipelines.

Invalid example:

~~~javascript
// INVALID: $facet nested inside $facet.
lab.products.aggregate([
  {
    $facet: {
      nested: [
        {
          $facet: {
            categories: [
              { $sortByCount: "$category" }
            ]
          }
        }
      ]
    }
  }
]);
~~~

If you need to process outputs across multiple branches, place stages **after `$facet`**:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      byCategory: [
        { $sortByCount: "$category" }
      ],
      total: [
        { $count: "n" }
      ]
    }
  },
  {
    $set: {
      totalValue: {
        $ifNull: [
          { $arrayElemAt: ["$total.n", 0] },
          0
        ]
      }
    }
  },
  {
    $project: {
      byCategory: 1,
      totalValue: 1,
      _id: 0
    }
  }
]);
~~~

This derives `totalValue` from the `total` array **after facet completes**, rather than trying to reference one branch from inside another during execution.

## 13. `$bucket`, `$bucketAuto`, and `$sortByCount` Inside Facets

Common stages paired with `$facet` to build multi-dimensional filter UIs:

| Stage in Branch | Purpose | Example |
| --- | --- | --- |
| `$sortByCount` | Count value frequencies | Product counts per brand |
| `$bucket` | Group into predefined boundary intervals | Prices 0–99, 100–499, 500–999 |
| `$bucketAuto` | Generate buckets from data distribution | Split into price ranges of roughly equal count |
| `$group` | Custom key-based statistics | Total stock, average price, count by category |
| `$match` | Filter a single branch | In-stock items only |
| `$project` | Shrink output array elements | Keep only id, name, price |
| `$sort`/`$limit` | Top N within a branch | Top 10 brands or products |

### 13.1. Using `$bucketAuto` When Boundaries Are Not Fixed

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      dynamicPrice: [
        {
          $bucketAuto: {
            groupBy: "$price",
            buckets: 3,
            output: {
              count: { $sum: 1 },
              minPrice: { $min: "$price" },
              maxPrice: { $max: "$price" }
            }
          }
        }
      ]
    }
  }
]);
~~~

`$bucketAuto` attempts to partition data into the requested bucket count, deriving bounds from data distribution and value granularity. Actual bucket count may be lower if there are too few distinct values. **Do not hardcode `$bucketAuto` boundary values** as a fixed frontend contract when underlying data changes often.

### 13.2. Multi-Dimensional Search and Filter Counts

Suppose the frontend filters globally on `status: "active"` and `category: "accessory"`. If both sit before facet, `byCategory` sees only `accessory` and loses counts for other categories.

When building an e-commerce filter sidebar, consider **self-excluding facets**: the category facet counts under all active filters **except category**, while the brand facet counts under all filters except brand. This requires **per-branch filters** or separate queries, not just one shared `$match`.

Example:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      products: [
        { $match: { category: "accessory", brand: "Nova" } },
        { $sort: { price: -1, _id: 1 } },
        { $limit: 10 },
        { $project: { name: 1, category: 1, brand: 1, price: 1 } }
      ],
      categories: [
        // Filters by brand, without restricting category.
        { $match: { brand: "Nova" } },
        { $sortByCount: "$category" }
      ],
      brands: [
        // Filters by category, without restricting brand.
        { $match: { category: "accessory" } },
        { $sortByCount: "$brand" }
      ]
    }
  }
]);
~~~

Here:

- `products` returns only items matching both accessory and Nova (Mouse).
- `categories` counts categories across all active Nova products.
- `brands` counts brands across all active accessories.

Totals across branches should not be expected to sum to one shared total when **filter scopes differ**. This is an intentional hallmark of faceted search design.

## 14. `$facet` for Pagination: Pros and Risks

A common pattern:

~~~javascript
const page = 2;
const pageSize = 3;
const skip = (page - 1) * pageSize;

lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $skip: skip },
        { $limit: pageSize },
        { $project: { name: 1, price: 1 } }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

Across the 11 active products, page 2 sorted by descending price returns:

~~~text
_id 103: Laptop Lite   price 800
_id 111: Tablet        price 700
_id 104: Phone Mini    price 450
~~~

Metadata total remains 11.

### 14.1. Do Not Equate Skip Inside Facet with Index-Based Seek

`$skip` in the `data` branch skips documents already fed into that branch. At deep offsets, it lacks the efficiency of keyset pagination backed by a compound index at the source.

When datasets are huge and users browse hundreds of pages, it is often better to:

- Use **keyset pagination** in a simple `find()` or `aggregate()`, backed by a deterministic sort and matching compound index.
- Compute totals or facets in separate, cacheable queries.
- Use `$facet` only when you genuinely need **multiple statistical views from the same input** with bounded output sizes.

Putting `data` and `count` in one command does not automatically beat two separate commands; actual speed depends on data volume, indexes, page depth, and caching.

### 14.2. Always Include a Tie-Breaker in Sorts

If multiple products share the same price, `$sort: { price: -1 }` leaves ties non-deterministic. When pairing `$skip` and `$limit` for pagination, append a unique tie-breaker:

~~~javascript
{ $sort: { price: -1, _id: 1 } }
~~~

This ensures deterministic ordering over a static dataset. Note that inserts, deletes, or price updates between requests can still cause offset pagination to repeat or skip items.

## 15. Computing Totals and Statistics Across Branches Without Keeping Raw Records

Summary branches typically need only aggregated metrics. For example, total list price across active products:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      totals: [
        {
          $group: {
            _id: null,
            productCount: { $sum: 1 },
            totalListPrice: { $sum: "$price" },
            averagePrice: { $avg: "$price" }
          }
        },
        {
          $project: {
            _id: 0,
            productCount: 1,
            totalListPrice: 1,
            averagePrice: 1
          }
        }
      ],
      inStock: [
        { $match: { stock: { $gt: 0 } } },
        { $count: "n" }
      ]
    }
  }
]);
~~~

From our dataset:

- `productCount = 11`.
- `totalListPrice = 6730`.
- `averagePrice` is approximately **611.82**.
- `inStock = [{ n: 10 }]`.

`totals` emits one tiny document; `inStock` also emits one tiny document. This `$facet` pattern scales well to large datasets provided the shared filter is selective and aggregations stay within resource budgets.

**Distinguish metrics carefully:** summing catalog list prices is **not sales revenue**; a product catalog holds no paid-order data. Revenue calculations require transactional order sources plus rules for refunds, taxes, and cancellations.

## 16. Post-`$facet` Multi-Step Shaping Without Bloating the Document

Because `$facet` outputs an object of arrays, downstream stages can apply array aggregation expressions.

### 16.1. Extracting Count from the Metadata Array

~~~javascript
[
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, price: 1 } }
      ],
      metadata: [
        { $count: "n" }
      ]
    }
  },
  {
    $set: {
      total: {
        $ifNull: [
          { $arrayElemAt: ["$metadata.n", 0] },
          0
        ]
      }
    }
  },
  {
    $unset: "metadata"
  }
]
~~~

### 16.2. Combining Results of Two Branches After They Are Built

For example, building two count branches and computing the in-stock ratio:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      total: [{ $count: "n" }],
      available: [
        { $match: { stock: { $gt: 0 } } },
        { $count: "n" }
      ]
    }
  },
  {
    $set: {
      totalN: {
        $ifNull: [{ $arrayElemAt: ["$total.n", 0] }, 0]
      },
      availableN: {
        $ifNull: [{ $arrayElemAt: ["$available.n", 0] }, 0]
      }
    }
  },
  {
    $project: {
      _id: 0,
      totalN: 1,
      availableN: 1,
      availabilityRatio: {
        $cond: [
          { $gt: ["$totalN", 0] },
          { $divide: ["$availableN", "$totalN"] },
          null
        ]
      }
    }
  }
]);
~~~

Lab result:

~~~javascript
{
  totalN: 11,
  availableN: 10,
  availabilityRatio: 0.9090909090909091
}
~~~

When there are no active products, the expression avoids division by zero and returns `availabilityRatio: null` (or whatever default the business contract requires).

### 16.3. Do Not Treat Post-Facet Stages as Operating on Individual Array Items

After `$facet`, `$project` or `$match` receives **one document containing arrays**, **not individual product documents**. To transform elements inside `data`, use array expressions such as `$map`/`$filter`, or `$unwind` only when you intentionally want to expand the array back into separate documents.

Example transforming items in `data` into a list of names:

~~~javascript
{
  $project: {
    _id: 0,
    names: {
      $map: {
        input: "$data",
        as: "product",
        in: "$$product.name"
      }
    }
  }
}
~~~

Do not add `$unwind: "$data"` just to extract names when `$map` suffices: `$unwind` turns one facet document into many documents, altering the API contract and introducing BSON/document-stream implications.

## 17. Distinguishing the 100 MB and 16 MiB Limits Through Scenarios

### Scenario A — Branches Holding Only Small Count Groups

~~~javascript
{
  $facet: {
    byCategory: [{ $sortByCount: "$category" }],
    total: [{ $count: "n" }]
  }
}
~~~

Category count is bounded and output is tiny. This is an ideal, textbook use case.

### Scenario B — Branch Retaining Hundreds of Thousands of Documents

~~~javascript
{
  $facet: {
    allRows: [{ $project: { name: 1, description: 1 } }]
  }
}
~~~

Output is one huge array inside a single BSON document, risking both 16 MiB and 100 MB failures. Neither `allowDiskUse` nor cursor batch size can save it.

### Scenario C — Group Building a Massive `$push` Array

~~~javascript
{
  $facet: {
    grouped: [
      {
        $group: {
          _id: "$category",
          allIds: { $push: "$_id" }
        }
      }
    ]
  }
}
~~~

Even with few groups, each group can hold an enormous `allIds` array. Both `$push` and `$facet` have memory constraints; `allowDiskUse` does not reliably prevent errors from huge `$push` accumulators. If only counts are needed, replace `$push` with `$sum: 1`.

### Scenario D — Placing `$limit` Afterward

~~~javascript
[
  {
    $facet: {
      allRows: [
        { $project: { name: 1, description: 1 } }
      ]
    }
  },
  { $limit: 1 }
]
~~~

`$limit: 1` at the end only limits **output documents in the stream**, not the length of `allRows` inside the facet document. Because `$facet` already emits one document, trailing `$limit: 1` does practically nothing for size.

**Solution:** Put `$limit` **inside the `allRows` branch**, and `$project` away unneeded heavy fields.

### Scenario E — Slicing the Array in a Downstream Stage

~~~javascript
[
  {
    $facet: {
      allRows: [
        { $project: { name: 1, description: 1 } }
      ]
    }
  },
  {
    $project: {
      allRows: { $slice: ["$allRows", 10] }
    }
  }
]
~~~

If `$facet` already exceeded 100 MB while constructing its document, downstream stages never run to rescue it. **Never rely on slicing output after facet to tame an oversized input stream.** Bound and trim inside each branch from the start.

## 18. Measuring BSON Size Before Hitting Limits

When output is small and valid, you can use `$bsonSize` to inspect the approximate size of the generated document:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, category: 1, price: 1 } }
      ],
      metadata: [{ $count: "total" }]
    }
  },
  {
    $project: {
      _id: 0,
      data: 1,
      metadata: 1,
      facetDocumentBytes: { $bsonSize: "$$ROOT" }
    }
  }
]);
~~~

`facetDocumentBytes` reports the BSON size of the document entering `$project`, measured **after `$facet`**. This helps track how response size grows as `pageSize` or bucket counts increase.

However:

- It **cannot run to "measure a failing document"** if `$facet` already failed due to the 100 MB or BSON limit beforehand.
- Final output size differs slightly because the measurement field itself adds bytes.
- On older MongoDB versions lacking `$bsonSize`, measure payload size in another way or in the application.
- Never target 16 MiB as a "safe ceiling to approach"; multi-megabyte responses also degrade latency, RAM, and network cost.

**Recommendation:** Intentionally keep `pageSize`, bucket counts, and projected API fields small.

## 19. When Should `$facet` Be Split into Multiple Queries?

`$facet` neatly organizes multiple aggregations over the same input, yet splitting queries is often better in these situations:

| Situation | Why Consider Splitting? |
| --- | --- |
| Very deep product pagination | Keyset/compound indexes in a standalone query beat sorting inside a facet |
| Facet with thousands or millions of buckets | One massive output document risking 16 MiB |
| A branch needs `$search`/`$vectorSearch` | Those stages are forbidden inside `$facet` sub-pipelines |
| Branches need completely different indexes | Separate queries can each leverage dedicated filter/sort indexes |
| Counts change rarely while listings change often | Cache counts/facets separately and re-query only the listing |
| One branch is slow or memory-heavy | Split to isolate timeouts, resources, and retries |
| Need to stream the entire dataset | Never pack a full stream into one facet array |
| Need strict snapshot consistency across multiple writes/transitions | Requires read concern/snapshot or transaction design, not just a single API call |

### 19.1. Example Splitting Data and Count

~~~javascript
const filter = {
  status: "active"
};

// Page query, able to leverage a sort index.
const data = lab.products.find(
  filter,
  { name: 1, category: 1, brand: 1, price: 1 }
).sort({ price: -1, _id: 1 })
 .limit(3)
 .toArray();

// Independent total count query.
const total = lab.products.countDocuments(filter);

printjson({ data, total });
~~~

In exchange, data can mutate between the two commands. If all reads must observe a single consistent snapshot, evaluate sessions, read concerns, and transactions for your server version and topology rather than assuming two commands naturally see the same instant.

**Never assume `$facet` automatically means "cheaper because it scans the source once."** It may avoid multiple scans yet introduce heavy in-memory sorts/groups, lose branch index usage, and hit single-document BSON limits. Benchmark on realistic workloads before deciding.

## 20. Limits Under Concurrent Mutations and Consistency Requirements

A `$facet` uses the same input stream within **a single aggregation invocation**, so all branches observe the same stream of documents delivered to the stage. However, this does not mean MongoDB automatically provides **snapshot isolation** for every aggregation in every configuration.

When clients concurrently update, insert, or delete:

- Consistency properties of an `aggregate` depend on read concern and deployment topology.
- Two runs of the same pipeline can return different totals.
- Running a facet followed immediately by another query does not guarantee both saw the same data state.
- If business rules require point-in-time accuracy, design explicit read concern/snapshot isolation or versioned datasets matching those guarantees.

Fast-moving dashboards typically tolerate a few seconds of eventual consistency. Financial reconciliation reports should rely on period-close snapshots or immutable/versioned records rather than an ad-hoc live `$facet` query.

## 21. Diagnosing Issues by Testing Each Branch Alone

When facet output looks wrong, run **a single branch as a standalone aggregation** using the same shared pre-filters.

Verifying `byCategory`:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  { $sortByCount: "$category" },
  { $sort: { count: -1, _id: 1 } }
]).toArray();
~~~

Verifying `byBrand`:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  { $group: { _id: "$brand", count: { $sum: 1 } } },
  { $sort: { count: -1, _id: 1 } }
]).toArray();
~~~

Verifying `total`:

~~~javascript
lab.products.countDocuments({ status: "active" });
// 11
~~~

If standalone branches are right yet facet output misses a field, check:

1. Are branch field names spelled properly?
2. Did a post-facet `$project` or `$unset` drop that array?
3. Did a shared filter outside facet shrink the input unintentionally?
4. Was `$limit` misplaced in the outer pipeline?
5. Did the branch emit an empty array because zero documents matched?
6. Did you assume `$group` preserves output order?
7. Did one branch retain too many documents, pushing `$facet` past memory limits?

**Cost caution:** running branches individually multiplies scans and CPU compared to one facet. Use this as a controlled diagnostic technique, not something automated hundreds of times on a live production cluster.

### 21.1. Verifying Bucket Totals

On the active dataset:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [0, 100, 500, 1000, 2000],
      default: "other",
      output: { count: { $sum: 1 } }
    }
  }
]).toArray();
~~~

The bucket counts sum to `2 + 4 + 3 + 2 = 11`. If bucket counts sum to less than `totalCount`, check for missing `default` buckets, mismatched filters, or missing/wrong-typed values. If the sum is larger, check whether documents were duplicated (e.g., via `$unwind`) before bucketing.

## 22. Operational Notes: explain, Profiler, and Monitoring

Run `explain` on the actual pipeline:

~~~javascript
lab.products.explain("executionStats").aggregate(dashboard);
~~~

Inspect:

- Whether stages before `$facet` perform `IXSCAN` or `COLLSCAN`.
- How `$match` predicates were pushed down by the query planner.
- Whether sorts execute in memory or use an index.
- `nReturned`, keys/docs examined, execution time, and memory/spill stats reported by your version.
- Any `ExceededMemoryLimit` errors and output size growth as data scales.

**Profiler/log `usedDisk`** only shows whether spill-capable stages actually spilled to disk. The absence of `usedDisk` never proves `$facet` used little RAM; `$facet` cannot spill to exceed its own limit anyway.

When errors occur, identify **which stage hit the limit**:

- `$facet` document too large → shrink element count/size inside branches; split queries.
- Outer `$sort` exceeds RAM (may spill depending on settings) → add index or `$sort + $limit`, consider `allowDiskUse`.
- `$group` with huge array accumulator → remove unbounded `$push`.
- Final BSON exceeds 16 MiB → cannot return that document regardless of cursor batch size.

Never tweak internal MongoDB thresholds indiscriminately just to keep an unsound data model running. Redesign the output shape first.

## 23. Common Errors and Remedies

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `ExceededMemoryLimit` when using facet | `$facet` intermediate document exceeded 100 MB | Shrink input, bound branches, project out heavy fields, split queries |
| Still errors with `allowDiskUse: true` | `$facet` does not spill | Do not rely on `allowDiskUse` to raise `$facet` limits |
| BSON document exceeds maximum size | Final output document exceeds 16 MiB | Shrink arrays/fields or split output into multiple documents |
| `batchSize: 1` does not fix it | One facet document holds oversized arrays | Bound data **inside each branch** |
| Metadata count equals `pageSize` | `$limit` placed before `$facet` | Move limit inside the `data` branch |
| Branch returns unexpectedly few items | Shared `$match` is too restrictive | Audit shared vs. branch-specific filter scopes |
| `metadata: []` when no data matches | `$count` emits nothing on empty input | Normalize to 0 after facet |
| Missing `_id` or expected fields | `$project` inside or after facet dropped them | Check each branch's output shape |
| Brand counts differ from category counts | Branches use different filters or have missing fields | Align scopes or verify intentional faceted search contract |
| `$search`/`$vectorSearch` rejected inside facet | Stage is disallowed in facet sub-pipelines | Move outside facet in a supported position or split queries |
| Leading `$facet` causes COLLSCAN | Facet cannot use indexes when placed first | Place `$match`/`$sort` before facet per workload |
| Branch sort remains slow despite index | Branch processes post-facet stream without direct index access | Sort before facet or split into standalone queries |
| Post-facet `$project` still fails at 100 MB | Facet exceeded limit before projection ran | Project/limit inside branches and before facet |
| `$sortByCount` tied groups reorder | No secondary tie-breaker key | Add explicit `$sort` |
| Only one document returned after facet | Expected output shape of `$facet` | Extract arrays from that document |
| API stays slow despite single aggregate | Multiple blocking stages, huge sorts, bloated output | Benchmark split queries, cache metadata, tune indexes |

## 24. Practice Exercises

The exercises below use `lab.products` from Section 3. No data modifications are needed unless you create new fixtures in a dedicated practice collection.

### Exercise 1 — First Two-Branch Facet

Build a pipeline selecting only active products:

- `data` branch: the two highest-priced products, returning only `name` and `price`.
- `metadata` branch: total count of active products.

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 2 },
        { $project: { _id: 0, name: 1, price: 1 } }
      ],
      metadata: [{ $count: "total" }]
    }
  }
]);
~~~

`data` returns Laptop Pro and Laptop Air; `metadata` returns `total: 11`.

### Exercise 2 — Predicting the Misplaced `$limit` Bug

Move `$limit: 2` **before** `$facet`. Predict `metadata` and explain why it no longer reflects the full active set.

Answer: `metadata` counts only the 2 documents surviving the limit; it no longer returns the true total of 11.

### Exercise 3 — Counting by Category and Brand

Add two branches:

~~~javascript
byCategory: [{ $sortByCount: "$category" }],
byBrand:    [{ $sortByCount: "$brand" }]
~~~

Verify:

~~~text
Categories: accessory=4, laptop=3, phone=2, book=1, tablet=1.
Brands:     Nova=5, Orion=3, Sonic=2, Paper=1.
~~~

Why doesn't `$limit: 2` inside `data` reduce these counts?

### Exercise 4 — Fixed Price Buckets

Use `$bucket` with boundaries `[0, 100, 500, 1000, 2000]` and `default: "other"`. Verify the count per interval against the dataset:

~~~text
[0,100)       -> 2
[100,500)     -> 4
[500,1000)    -> 3
[1000,2000)   -> 2
~~~

Explain why a product priced at 100 falls into the second bucket.

### Exercise 5 — Automatic Price Buckets

Use `$bucketAuto` with `buckets: 3`. Compare its boundaries against fixed `$bucket` and explain when each is appropriate.

### Exercise 6 — Inventory Statistics

Build a `stockStats` branch returning:

~~~javascript
{ totalStock: 122, inStockProducts: 10 }
~~~

Use `$group` and `$cond` as in Section 5.4. Explain the difference between total stock units and count of in-stock products.

### Exercise 7 — Empty Results and `$count`

Filter `status: "unknown"` before facet with `data` and `total: [{ $count: "n" }]`. Predict each branch's output. Write a post-facet `$project` returning `total: 0` when the count array is empty.

### Exercise 8 — Explaining the 100 MB and 16 MiB Limits

A facet builds a 50 MB intermediate document, then `$project` trims it down to a 5 MB array. Distinguish the 100 MB and 16 MiB limits, and explain why even though it fits the size rules, relying on giant intermediate documents is still unwise.

Flip the scenario: facet attempts to build 120 MB before a trailing stage cuts it to 1 MB. Why cannot `allowDiskUse: true` save it?

### Exercise 9 — Identifying Disallowed Stages

In the sub-pipelines below, which stages are disallowed?

~~~javascript
{
  $facet: {
    a: [{ $match: { brand: "Nova" } }],
    b: [{ $group: { _id: "$category", n: { $sum: 1 } } }],
    c: [{ $search: { /* search definition */ } }],
    d: [{ $merge: "results" }],
    e: [{ $facet: { nested: [{ $count: "n" }] } }]
  }
}
~~~

Answer: branches c, d, and e contain stages forbidden inside `$facet`; a and b use valid stage types.

### Exercise 10 — Branch Limiting Instead of Outer Pipeline

Design a paginated API for active products sorted by descending price, `pageSize = 3`, requiring `metadata` `total = 11`. Put `$sort`, `$skip`, and `$limit` inside `data`. Verify page 2 returns Laptop Lite, Tablet, and Phone Mini.

### Exercise 11 — Output BSON Size Metric

Add a post-facet `$project` using `$bsonSize: "$$ROOT"`. Record the document size in the lab. Increase `pageSize` from 3 to 8 and compare.

Question: if the facet document already exceeded the 100 MB limit, would the trailing size-measurement stage run? Why or why not?

### Exercise 12 — Pre-Facet Index

Create the index:

~~~javascript
lab.products.createIndex({ status: 1, price: -1, _id: 1 });
~~~

Compare `explain` between `$match + $facet (sort inside branch)` and `$match + $sort + $facet (limit inside branch)`. Why do plans and resource costs differ? Distinguish source index usage from branch processing.

### Exercise 13 — Choosing Facet vs. Two Queries

A system has 5 million products, users paginate 20 items per page, and brand counts change only a few times a day. Design how to fetch pages and metadata.

Suggested answer: evaluate index-backed keyset pagination for data pages, and compute/cache facet statistics separately per filter; use a single shared facet only when benchmarks and consistency/freshness requirements prove it beneficial.

### Exercise 14 — Self-Excluding Facets

A user selects `category = "accessory"` and `brand = "Nova"`. Design three branches:

- `products`: applies both filters.
- `categories`: applies only the brand filter.
- `brands`: applies only the category filter.

Explain why sums across branches do not need to match and why this behavior is desired in filter UIs.

## 25. Summary

`$facet` is a powerful tool when you need **multi-dimensional aggregations over the same input within one pipeline**. Each branch runs its own sub-pipeline on the documents delivered to `$facet` and returns results inside an **array within a single document**.

Key points to remember:

1. **`$facet` runs independent branches**; one branch's output cannot be piped directly into another inside the same stage.
2. **Pre-facet filters apply to all branches**; branch-local filters and limits affect only that branch.
3. **Facet output is a single BSON document containing multiple arrays**, unlike a cursor streaming many small documents.
4. **The 100 MB intermediate document limit of `$facet` is dedicated and cannot spill**, even with `allowDiskUse: true`.
5. **The final document remains subject to the 16 MiB BSON limit**; cursor `batchSize` or post-facet `$limit` cannot shrink an oversized facet document in time.
6. **Bound output inside branches** using `$limit`, `$project`, and summary `$group` stages—never unbounded `$push: "$$ROOT"`.
7. **A leading `$facet` triggers COLLSCAN**; put `$match`/`$sort` before facet to leverage indexes when compatible with the data contract.
8. **Never nest `$facet` or use `$merge`, `$out`, `$search`, `$vectorSearch`, or other disallowed stages** inside sub-pipelines.
9. **`$count` on empty input yields an empty array**, so normalize `total` to 0 if the API expects a number.
10. **Choose `$facet` vs. separate queries based on data and workload**; sharing one scan across branches does not always beat separate queries with optimal indexes and caching.

### Official MongoDB Documentation

- [`$facet` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/) — syntax, independent branches, 100 MB and 16 MiB limits, indexing, and disallowed stages.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — size limits, memory, `allowDiskUse`, and version differences.
- [`$bucket`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/) — grouping by explicit boundaries.
- [`$bucketAuto`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucketAuto/) — automatic bucketing by distribution.
- [`$sortByCount`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortByCount/) — counting frequencies and sorting.
- [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — grouping and accumulators.
- [`$count`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count/) — counting documents in a pipeline.
- [`$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonSize/) — measuring BSON document size.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — filter/sort pushdown, pipeline optimization, and indexes.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — inspecting query plans and execution stats.
