# Facets, Highlighting, and Pagination of Search Results in MongoDB

## 1. Context: A Search Results Page Needs More Than a Document List

Suppose an e-commerce app stores hundreds of thousands of products. A user searches for **wireless**. Simply returning an array of matching products forces them to sift through results manually. A complete search page usually needs three features:

- **Facets:** filter groups with corresponding counts, such as category `audio (3)`, brand `nova (2)`, price `500,000–1,000,000 (2)`.
- **Highlighting:** excerpts showing matched terms so users immediately see why a document matched.
- **Pagination:** retrieving a bounded number of results per page with Next/Previous controls, avoiding loading the entire result set at once.

UI illustration (illustrative numbers):

```text
Keyword: [ wireless_________________ ] [Search]

Filters                         Page 1 Results
--------------------------------  --------------------------------
Category                          Wireless Headphones Light
[ ] audio        (3)              "... lightweight WIRELESS headphones ..."
[ ] accessory    (1)              890,000 VND
[ ] computer     (1)
                                  Wireless Earbuds Pro
Price                             "... compact WIRELESS earbuds ..."
[ ] 0–500k       (1)              950,000 VND
[ ] 500k–1M      (3)
[ ] 1M–2M        (1)                [Prev]  [Next]
```

These three features are related, yet they solve **three distinct problems**:

1. Facets summarize **the entire matching document set**.
2. Highlighting explains **where a specific document matched**.
3. Pagination manages **ordering and position** within the result list.

**Lesson objectives:** configure a MongoDB Search index, use `$searchMeta` to compute facets, use `$search` to return highlights and scores, use `$skip`/`$limit` or `searchAfter`/`searchBefore` to paginate, understand consistency limits, and structure a secure search API.

## 2. Distinguishing `$text` and MongoDB Search

MongoDB has two mechanisms often loosely referred to as "full-text search":

| Feature | Legacy MongoDB `$text` | MongoDB Search |
|---|---|---|
| Index | `createIndex({ name: "text" })` | Search index with mappings/analyzers |
| Query | `$text: { $search: ... }` | Aggregation `$search` or `$searchMeta` |
| Score | `$meta: "textScore"` | `$meta: "searchScore"` |
| Facets | `$match` followed by `$facet`/`$group` | Search `facet` collector |
| Native highlighting | No `searchHighlights` | Built-in `highlight` + `searchHighlights` |
| Token-based pagination | Not supported | `searchSequenceToken` + `searchAfter`/`searchBefore` |
| Analyzers and features | Relatively basic | Custom analyzers, fuzzy, phrase, autocomplete, facets, etc. |

**Our focus here is MongoDB Search.** A legacy text index is usually insufficient for a full facet, highlight, and Search pagination-token experience. A `$text` example is still shown near the end as a baseline fallback.

### 2.1. Requirements for Running MongoDB Search

MongoDB Search is supported on **MongoDB Atlas** and compatible self-managed setups on newer MongoDB versions. Per current documentation, MongoDB Community starting in **8.2** and corresponding Enterprise configurations support Search when all required components are deployed; this **does not** mean any standalone `mongod` can execute `$search`.

Verify deployment, MongoDB/`mongosh`/driver versions, account privileges, Search components, and Search index status before running queries. Token-based Search pagination carries its own version requirements (docs specify MongoDB 7.0.5+ on supported clusters).

### 2.2. Two Metadata Systems That Do Not Substitute for Each Other

```text
Text index:
  $text -> textScore

MongoDB Search index:
  $search -> searchScore, searchHighlights, searchSequenceToken
  $searchMeta -> count, facet buckets
```

Never use `$meta: "searchScore"` in a `$text`-only pipeline. Never expect `$text` to emit `searchHighlights`.

## 3. Practice Dataset

We use database `search_lab_307` and collection `products307`, leaving production data untouched.

### 3.1. Product Document

```javascript
{
  _id: "P001",
  sku: "P001",
  name: "Wireless Headphones Light",
  description: "Lightweight wireless headphones with long battery life.",
  category: "audio",
  brand: "nova",
  price: 890000,
  publishedAt: ISODate("2026-01-10T00:00:00Z"),
  active: true
}
```

`name` and `description` are used for search and highlighting; `category` and `brand` for string facets; `price` and `publishedAt` for range facets; `active` as a filter; and unique `sku` as a sort tie-breaker.

### 3.2. Seeding Lab Data

```javascript
const lab = db.getSiblingDB("search_lab_307");
const products = lab.products307;

if (products.countDocuments({}) !== 0) {
  throw new Error("Collection already contains data: choose an empty lab");
}

products.insertMany([
  {
    _id:"P001", sku:"P001",
    name:"Wireless Headphones Light",
    description:"Lightweight wireless headphones with long battery life.",
    category:"audio", brand:"nova", price:890000,
    publishedAt:ISODate("2026-01-10T00:00:00Z"), active:true
  },
  {
    _id:"P002", sku:"P002",
    name:"Wireless Earbuds Pro",
    description:"Compact wireless earbuds with noise isolation.",
    category:"audio", brand:"nova", price:950000,
    publishedAt:ISODate("2026-02-05T00:00:00Z"), active:true
  },
  {
    _id:"P003", sku:"P003",
    name:"Wireless Speaker Mini",
    description:"Portable wireless speaker for small rooms.",
    category:"audio", brand:"orion", price:1350000,
    publishedAt:ISODate("2026-03-01T00:00:00Z"), active:true
  },
  {
    _id:"P004", sku:"P004",
    name:"Wireless Charging Pad",
    description:"Wireless charging accessory for phones.",
    category:"accessory", brand:"orion", price:350000,
    publishedAt:ISODate("2026-04-11T00:00:00Z"), active:true
  },
  {
    _id:"P005", sku:"P005",
    name:"USB-C Data Cable",
    description:"Reliable cable for charging and data transfer.",
    category:"accessory", brand:"nova", price:120000,
    publishedAt:ISODate("2026-04-12T00:00:00Z"), active:true
  },
  {
    _id:"P006", sku:"P006",
    name:"Wireless Mouse Basic",
    description:"Silent wireless mouse for office work.",
    category:"computer", brand:"nova", price:490000,
    publishedAt:ISODate("2026-05-03T00:00:00Z"), active:false
  },
  {
    _id:"P007", sku:"P007",
    name:"Wireless Keyboard",
    description:"Slim wireless keyboard with compact layout.",
    category:"computer", brand:"orion", price:690000,
    publishedAt:ISODate("2026-06-15T00:00:00Z"), active:true
  }
]);

products.createIndex({ sku: 1 }, { unique: true });
```

Never run `drop()` or `deleteMany({})` on real data to reset a lab. If a collection already has data, pick a fresh test namespace.

### 3.3. Expected Matches

Querying `wireless` with `active: true` matches P001, P002, P003, P004, and P007. P006 contains `wireless` but has `active: false`; P005 lacks the term.

Ordering by **relevance** can differ from insertion order. Use these IDs to understand the dataset; do not assert exact Search scores before running queries.

## 4. Search Index: Text Fields Differ from Facet Fields

### 4.1. Choosing the Right Mapping

| Field | Search Type | Purpose |
|---|---|---|
| `name` | `string` | Text search and highlighting |
| `description` | `string` | Text search and highlighting |
| `category` | `token` | String facets, exact filter |
| `brand` | `token` | String facets, exact filter |
| `price` | `number` | Numeric facets, ranges, sorting |
| `publishedAt` | `date` | Date facets, ranges, sorting |
| `active` | `boolean` | Filtering |
| `sku` | `token` | Sort tie-breaker |

Per current Search documentation, **`token`** is recommended for string facets. `stringFacet` is an older type used in legacy guides. If **the same field needs both word search and faceting**, map it under **both appropriate types**; never assume `string` and `token` are interchangeable.

### 4.2. Creating the Index

Run only on a Search-enabled deployment:

```javascript
products.createSearchIndex("catalog_search_307", {
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "string",
        indexOptions: "offsets"
      },
      description: {
        type: "string",
        indexOptions: "offsets"
      },
      category: {
        type: "token",
        normalizer: "lowercase"
      },
      brand: {
        type: "token",
        normalizer: "lowercase"
      },
      price: { type: "number" },
      publishedAt: { type: "date" },
      active: { type: "boolean" },
      sku: { type: "token" }
    }
  }
});
```

Indexes created via `createSearchIndex()` **differ** from standard indexes created via `createIndex()`. A Search index may still be building after the create command returns.

### 4.3. Checking Index Status

```javascript
products.aggregate([
  { $listSearchIndexes: {} }
]);
```

Ensure `catalog_search_307` is ready. Never conclude `$search` syntax is broken while the Search index is still building.

### 4.4. Why Does Highlighting Need `offsets`?

Search needs **character positions of matched words/spans in the source text** to extract highlights. The field must be indexed as `string` with `indexOptions: "offsets"` (usually the default). Never map a field strictly as an exact `token` and expect multi-word text highlighting on it.

## 5. `$search`: Retrieving Documents and Relevance Scores

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      sku: 1,
      name: 1,
      price: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`$search` must be the **first stage** in any pipeline using it. Never place `$match` ahead of `$search`. To filter inside Search from the start, use `$search.compound.filter`.

### 5.1. Filtering `active` Without Skewing Text Scores

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      compound: {
        must: [
          {
            text: {
              query: "wireless",
              path: ["name", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "active",
              value: true
            }
          }
        ]
      }
    }
  },
  {
    $project: {
      sku: 1,
      name: 1,
      active: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`compound.must` requires text matching and scores it; `compound.filter` narrows documents without adding score like a text predicate.

### 5.2. Scores Are Not Percentages

`searchScore = 8.4` does not mean "84% correct." Score is a relative relevance measure governed by operators, analyzers, and corpus statistics; never compare raw scores across different keywords without calibration.

## 6. Facets: Grouping Across the Matching Result Set

With five active products matching `wireless`:

```text
P001 audio      890,000
P002 audio      950,000
P003 audio    1,350,000
P004 accessory  350,000
P007 computer   690,000

Category facet:
  audio       3
  accessory   1
  computer    1

Price facet:
  [0, 500k)     1
  [500k, 1M)    3
  [1M, 2M)      1
```

**Facets must be computed across the full filtered match set**, not just the 10–20 documents displayed on the current page.

### 6.1. Three Facet Types

| Type | Examples | Mechanism |
|---|---|---|
| String | Category, brand | Buckets by string value; requires `token` mapping |
| Number | Price, rating | Buckets by numeric intervals |
| Date | Publish date, release date | Buckets by date intervals |

Multi-valued fields (such as an array of `tags`) can contribute to **multiple buckets**, so bucket count sums **do not necessarily equal the unique document count**.

## 7. `$searchMeta`: Category Facets

`$searchMeta` returns **metadata** rather than the full product list.

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          compound: {
            must: [
              {
                text: {
                  query: "wireless",
                  path: ["name", "description"]
                }
              }
            ],
            filter: [
              { equals: { path: "active", value: true } }
            ]
          }
        },
        facets: {
          categories: {
            type: "string",
            path: "category",
            numBuckets: 10
          }
        }
      }
    }
  }
]);
```

### 7.1. Structure

- `facet.operator` defines **the matching result set**.
- `facets.categories` defines **how to group** that set.
- `type: "string"` specifies a string facet.
- `path: "category"` points to the `token`-mapped field.
- `numBuckets` caps the number of returned buckets—it does **not** cap how many documents Search inspects.

### 7.2. Illustrative Output

```javascript
[
  {
    count: { lowerBound: NumberLong("5") },
    facet: {
      categories: {
        buckets: [
          { _id: "audio", count: NumberLong("3") },
          { _id: "accessory", count: NumberLong("1") },
          { _id: "computer", count: NumberLong("1") }
        ]
      }
    }
  }
]
```

`_id` in each bucket is the **category value**, not a product ID. Exact field names and values depend on query and deployment; this is a condensed sample.

### 7.3. Facets Do Not Process Only the Top 10 Hits

If a query matches 100,000 products, `numBuckets: 10` returns at most the top 10 buckets per facet criteria—it does **not** mean Search reads only 10 products. High-cardinality fields can still consume significant memory and compute during faceting.

## 8. Numeric Facets: Grouping by Price Bands

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        },
        facets: {
          prices: {
            type: "number",
            path: "price",
            boundaries: [0, 500000, 1000000, 2000000],
            default: "other"
          }
        }
      }
    }
  }
]);
```

**Lab note:** this query omits `active: true`, so to facet **active products**, add the `active` filter inside `facet.operator`.

The intervals represent:

```text
[0, 500000)
[500000, 1000000)
[1000000, 2000000)
other
```

**Lower bounds are inclusive; upper bounds are exclusive.** Price `500000` falls into the second bucket, not the first. Price `2000000` falls into `other` as configured above.

Never store string `"890000"` in a numeric field expecting it to behave like the number `890000`.

### 8.1. Boundaries Are a Business Decision

A headphone store might bucket `0–500k`, `500k–1M`, `1M–2M`; a car marketplace uses completely different bands. Do not force equal min–max widths if uneven business bands help shoppers filter better.

## 9. Date Facets: Grouping by Time Intervals

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        },
        facets: {
          publishDates: {
            type: "date",
            path: "publishedAt",
            boundaries: [
              ISODate("2026-01-01T00:00:00Z"),
              ISODate("2026-04-01T00:00:00Z"),
              ISODate("2026-07-01T00:00:00Z")
            ],
            default: "otherDate"
          }
        }
      }
    }
  }
]);
```

Date facets group by **BSON Date** values—never convert dates into text tokens expecting numeric/date ranges to work naturally.

### 9.1. Time Zones Matter

A boundary at `2026-04-01T00:00:00Z` does not align with the start of Q2 in every local time zone. If the UI labels "Q2 (Vietnam time)," compute local midnight boundaries first and convert them to UTC instants for `boundaries`.

## 10. Multiple Facets in One Query

```javascript
const facetMetadata307 = products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          compound: {
            must: [
              {
                text: {
                  query: "wireless",
                  path: ["name", "description"]
                }
              }
            ],
            filter: [
              { equals: { path: "active", value: true } }
            ]
          }
        },
        facets: {
          categories: {
            type: "string",
            path: "category",
            numBuckets: 10
          },
          brands: {
            type: "string",
            path: "brand",
            numBuckets: 10
          },
          prices: {
            type: "number",
            path: "price",
            boundaries: [0, 500000, 1000000, 2000000],
            default: "other"
          }
        }
      }
    }
  }
]).toArray();

printjson(facetMetadata307);
```

Metadata output contains:

```javascript
{
  count: { lowerBound: NumberLong("5") },
  facet: {
    categories: { buckets: [/* ... */] },
    brands: { buckets: [/* ... */] },
    prices: { buckets: [/* ... */] }
  }
}
```

Each facet represents **one grouping dimension over the same matching set**. Never add `categories.count` and `brands.count` together as a total hit count.

## 11. When Users Select Filters: Conjunctive vs. Disjunctive

Suppose the user selects `category = "audio"`.

### 11.1. Conjunctive Faceting

The `category` facet is computed **after applying `category=audio`**:

```text
Match set:
  text=wireless AND active=true AND category=audio

Category facet:
  audio (3)
```

This is right when the UI only summarizes **the currently filtered subset**.

### 11.2. Disjunctive Faceting

Often the UI wants to keep sibling choices visible in the same dimension:

```text
[x] audio       (3)
[ ] accessory   (1)
[ ] computer    (1)
```

To compute the `category` facet, **drop only the active `category` filter** while keeping all other filters:

```text
Hits query:
  wireless AND active=true AND category=audio

Category facet query:
  wireless AND active=true
```

If the user also picks `brand=nova` and a price band, those filters remain active when computing the `category` facet under disjunctive rules.

### 11.3. Which Filter to Omit per Facet Dimension?

| Facet Being Computed | Which Filter to Omit to Keep Sibling Choices? |
|---|---|
| Category | Omit `category`; keep `brand`, `price`, `active` |
| Brand | Omit `brand`; keep `category`, `price`, `active` |
| Price | Omit `price`; keep `category`, `brand`, `active` |

No single faceting policy fits every UI. **Backend and frontend must agree explicitly on bucket-count semantics.**

### 11.4. Multi-Select OR Within One Dimension

A requirement:

```text
category = audio OR computer
brand = nova
active = true
```

can be expressed with Search `in` on the `token`-mapped `category` field:

```javascript
{
  compound: {
    must: [{
      text: {
        query: "wireless",
        path: ["name", "description"]
      }
    }],
    filter: [
      { equals: { path: "active", value: true } },
      { in: { path: "category", value: ["audio", "computer"] } },
      { equals: { path: "brand", value: "nova" } }
    ]
  }
}
```

Never let browsers pass arbitrary operators directly; the backend must allowlist fields, operators, filter counts, and data-access permissions.

## 12. Search `facet` Collector Differs from Aggregation `$facet`

### 12.1. Aggregation `$facet`

`$facet` is an **aggregation pipeline stage** executing multiple sub-pipelines over documents arriving from prior stages:

```javascript
products.aggregate([
  { $match: { active: true } },
  {
    $facet: {
      hits: [
        { $sort: { price: 1, _id: 1 } },
        { $limit: 5 }
      ],
      categories: [
        { $group: { _id: "$category", count: { $sum: 1 } } },
        { $sort: { count: -1, _id: 1 } }
      ]
    }
  }
]);
```

It processes documents produced by preceding pipeline stages. This is **not** the Search facet collector.

### 12.2. Search `facet` Collector

Configured inside `$searchMeta` or `$search`:

```javascript
{
  $searchMeta: {
    index: "catalog_search_307",
    facet: {
      operator: {
        text: { query: "wireless", path: "name" }
      },
      facets: {
        categories: { type: "string", path: "category" }
      }
    }
  }
}
```

It computes metadata directly from the Search index.

### 12.3. Invalid: Placing `$search` Inside a `$facet` Branch

```javascript
// INVALID:
[
  {
    $facet: {
      hits: [
        { $search: { text: { query: "wireless", path: "name" } } }
      ]
    }
  }
]
```

`$search` must be the first stage of the pipeline and **cannot be nested inside a `$facet` branch**. You can place `$facet` **after** `$search` when genuinely needed:

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      }
    }
  },
  {
    $facet: {
      hits: [
        { $limit: 5 },
        { $project: { name: 1, category: 1 } }
      ],
      categories: [
        { $group: { _id: "$category", count: { $sum: 1 } } }
      ]
    }
  }
]);
```

Never place `$limit` **before** `$facet` if you want counts across all matches. For large datasets, the Search `facet` collector is usually far better because aggregation `$facet` must materialize and group documents after Search.

## 13. Fetching Hits and Metadata in One Pipeline

One practical architecture runs **two queries**:

```text
Query A: $search -> hits + highlights + pagination tokens
Query B: $searchMeta -> facets + count
```

This allows caching facets independently and **avoids recomputing facets when the user simply clicks Next**.

### 13.1. Using `$$SEARCH_META`

MongoDB Search also supports the `facet` collector inside `$search`, exposing metadata via `$$SEARCH_META`.

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      facet: {
        operator: {
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        },
        facets: {
          categories: {
            type: "string",
            path: "category",
            numBuckets: 10
          }
        }
      },
      highlight: {
        path: ["name", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $facet: {
      hits: [
        {
          $project: {
            name: 1,
            category: 1,
            score: { $meta: "searchScore" },
            highlights: { $meta: "searchHighlights" }
          }
        }
      ],
      metadata: [
        { $replaceWith: "$$SEARCH_META" },
        { $limit: 1 }
      ]
    }
  },
  {
    $set: {
      metadata: { $arrayElemAt: ["$metadata", 0] }
    }
  }
]);
```

This returns one document containing `hits` and `metadata`. Note, however, that reading `$$SEARCH_META` downstream of `$search` requires at least one matching document to flow through; on zero hits, metadata may need a dedicated `$searchMeta` query.

Certain stages such as `$lookup` and `$unionWith` also clear access to `$$SEARCH_META` for subsequent stages. Extract metadata before those stages.

## 14. Highlighting: Matched Terms and Context

Highlighting is more than JavaScript substring coloring. Search leverages the analyzer to match inflected forms, multiple fields, and exact positions.

Highlight output is returned via `$meta: "searchHighlights"`. Condensed example:

```javascript
{
  path: "description",
  score: 2.35,
  texts: [
    { value: "Lightweight ", type: "text" },
    { value: "wireless", type: "hit" },
    { value: " headphones with long battery life.", type: "text" }
  ]
}
```

`texts.type`:

- `"hit"`: span to emphasize.
- `"text"`: surrounding context.

The highlight **passage** score is not the overall document relevance score.

### 14.1. `highlight` Syntax

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      },
      highlight: {
        path: ["name", "description"],
        maxNumPassages: 2,
        maxCharsToExamine: 5000
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      sku: 1,
      name: 1,
      score: { $meta: "searchScore" },
      highlights: { $meta: "searchHighlights" }
    }
  }
]);
```

**Option placement:** `highlight` is a direct child of `$search`, not nested inside `text`.

### 14.2. Why Does `$project` Need `searchHighlights`?

Highlights are **query metadata**, not stored fields inside product documents. To return them to the UI, include:

```javascript
{ highlights: { $meta: "searchHighlights" } }
```

### 14.3. Key Options

| Option | Role |
|---|---|
| `highlight.path` | Field or list of fields to extract passages from |
| `maxNumPassages` | Maximum passages returned per field |
| `maxCharsToExamine` | Maximum characters scanned when searching for highlights in a field |

If the keyword sits at character 15,000 while `maxCharsToExamine: 5000`, Search can still return the **matching document** while returning empty highlights for that field. **Empty highlights do not prove a document failed to match.**

### 14.4. Highlighting Is Not a Universal Post-Processor

If a field is not mapped as Search `string` with offsets, or uses an incompatible analyzer, highlights may be missing or unexpected. Never map a field solely as `token` for faceting and expect multi-word text highlights from it.

## 15. Rendering Highlights Safely to Prevent XSS

Suppose a description in the database contains:

```text
Wireless <script>alert("x")</script> headphones
```

If the frontend injects raw `segment.value` into `innerHTML`, user-supplied content can execute as HTML. Highlight metadata **is not an HTML XSS sanitizer**.

Safe browser rendering pattern:

```javascript
for (const segment of highlight.texts) {
  if (segment.type === "hit") {
    const mark = document.createElement("mark");
    mark.textContent = segment.value;
    container.appendChild(mark);
  } else {
    container.appendChild(
      document.createTextNode(segment.value)
    );
  }
}
```

`textContent` and `createTextNode` emit plain text safely rather than parsing HTML. In React or Vue, rely on default escaped text interpolation rather than raw `innerHTML`.

Beyond XSS, control field-level highlight permissions: **snippets can disclose restricted content** if an internal field was accidentally indexed.

## 16. Simple Pagination: `$skip` + `$limit`

With `pageSize=10`:

```text
Page 1 -> skip 0,  limit 10
Page 2 -> skip 10, limit 10
Page 3 -> skip 20, limit 10
Page N -> skip (N-1)*10, limit 10
```

Example:

```javascript
const page = 3;
const pageSize = 10;

products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      },
      sort: {
        score: { $meta: "searchScore" },
        sku: 1
      }
    }
  },
  { $skip: (page - 1) * pageSize },
  { $limit: pageSize },
  {
    $project: {
      name: 1,
      sku: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

### 16.1. Deterministic Sorting Needs a Tie-Breaker

If multiple products share the same score, relative order can drift across queries. Add a unique `token`-indexed `sku` field as a tie-breaker:

```javascript
sort: {
  score: { $meta: "searchScore" },
  sku: 1
}
```

Or:

```javascript
sort: {
  publishedAt: -1,
  sku: 1
}
```

**Sorting by date alone is insufficient** whenever multiple documents share identical `publishedAt` timestamps.

### 16.2. Deep Skip Is Resource-Intensive

Page 20,000 at 20 items per page:

```text
skip = (20000 - 1) * 20 = 399980
```

The server must step past hundreds of thousands of positions before emitting 20 hits. Offsets are convenient for the **first few pages** or jumping to a page number, but scale poorly for deep browsing.

### 16.3. Sorting Does Not Create a Snapshot

Between page 1 and page 2, a new document may be inserted near the top of the ranking. Offsets shift, causing page 2 to **repeat** an item from page 1 or **skip** an unseen item.

A tie-breaker stabilizes ties—it does not freeze data against concurrent inserts, updates, or deletes.

## 17. `searchAfter`: Paginating from a Reference Point

MongoDB Search supports `searchAfter` and `searchBefore` on compatible clusters and versions; MongoDB documentation describes support starting in **7.0.5+** on eligible deployments.

Contrast with `skip`:

```text
skip:
  Discard the first N results.

searchAfter:
  Start AFTER a reference hit in the Search sort order.
```

### 17.1. Generating Page 1 Tokens

```javascript
const size = 2;
const page1 = products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      compound: {
        must: [{
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        }],
        filter: [
          { equals: { path: "active", value: true } }
        ]
      },
      sort: {
        score: { $meta: "searchScore" },
        sku: 1
      }
    }
  },
  { $limit: size },
  {
    $project: {
      sku: 1,
      name: 1,
      score: { $meta: "searchScore" },
      paginationToken: { $meta: "searchSequenceToken" }
    }
  }
]).toArray();

const lastToken = page1.length > 0
  ? page1[page1.length - 1].paginationToken
  : null;

printjson(page1);
```

`searchSequenceToken` is a **Base64-encoded token** emitted by MongoDB Search for each hit. It is **not** a Change Stream resume token, MongoDB cursor ID, or document `_id`.

### 17.2. Using the Token for the Next Page

```javascript
const page2 = lastToken
  ? products.aggregate([
      {
        $search: {
          index: "catalog_search_307",
          compound: {
            must: [{
              text: {
                query: "wireless",
                path: ["name", "description"]
              }
            }],
            filter: [
              { equals: { path: "active", value: true } }
            ]
          },
          sort: {
            score: { $meta: "searchScore" },
            sku: 1
          },
          searchAfter: lastToken
        }
      },
      { $limit: size },
      {
        $project: {
          sku: 1,
          name: 1,
          paginationToken: { $meta: "searchSequenceToken" }
        }
      }
    ]).toArray()
  : [];

printjson(page2);
```

Crucially, **operators, filters, and sort must remain semantically identical** across pages. Whenever keyword, category, brand, price, analyzer, index, or sort changes, **discard the old token and restart from page 1**.

### 17.3. Use the Last Hit's Token—Never Fabricate One

Take the token from the **last** hit on the page as the `next` cursor. When a page is empty, never synthesize fake tokens from `Date.now()`, `ObjectId`, or scores.

## 18. `searchBefore` and the Previous Button

To page backward, take the token of the **first hit on the current page**:

```javascript
const firstToken = page2.length > 0
  ? page2[0].paginationToken
  : null;
```

Then run the **same query** replacing `searchAfter` with `searchBefore`:

```javascript
function previousPageFrom(token) {
  return products.aggregate([
    {
      $search: {
        index: "catalog_search_307",
        compound: {
          must: [{
            text: {
              query: "wireless",
              path: ["name", "description"]
            }
          }],
          filter: [
            { equals: { path: "active", value: true } }
          ]
        },
        sort: {
          score: { $meta: "searchScore" },
          sku: 1
        },
        searchBefore: token
      }
    },
    { $limit: size },
    {
      $project: {
        sku: 1,
        name: 1,
        paginationToken: { $meta: "searchSequenceToken" }
      }
    }
  ]).toArray().reverse();
}

const previousPage = firstToken
  ? previousPageFrom(firstToken)
  : [];
```

MongoDB Search returns hits preceding the reference point in **reverse order**. `.reverse()` restores the original UI display order.

Never switch `sort` to a different order expecting the old token to remain compatible.

## 19. Important Limitation: Tokens Do Not Freeze a Snapshot

MongoDB documentation explicitly notes that **`searchSequenceToken` is not bound to a fixed database snapshot**.

Example:

```text
T1:
  A(score=9), B(score=8), C(score=7), D(score=6)
  page 1 = [A, B], save token after B

T2:
  C is updated to score=10
  New order = C, A, B, D
```

When fetching page 2 with the old token, the application must not promise that users will **see every document exactly once**, because Search rankings shifted.

### 19.1. What `searchAfter` Gives You

- Walks Search results in order without skipping all prior pages from zero.
- Reduces deep-pagination cost significantly.
- Provides an engine-generated cursor anchor.

### 19.2. What `searchAfter` Does Not Give You

- Does not create snapshot isolation across HTTP requests.
- Does not freeze the index while source documents change.
- Does not turn a dynamic relevance list into a permanent order.
- Does not allow reusing a token across different queries, filters, or sorts.

If business logic demands an **exact-once, complete, consistent** export, use a dedicated snapshot or static dataset mechanism rather than Search page tokens.

### 19.3. Why Put `sort` Inside `$search`?

Tokens are tied to **Search's own sort order**. If the UI expects price sorting, yet the pipeline writes:

```javascript
[
  { $search: { /* sorted by score */ } },
  { $sort: { price: 1 } }
]
```

then the token semantics and UI ordering diverge. Always place:

```javascript
sort: { price: 1, sku: 1 }
```

**inside `$search`**, using fields properly mapped for Search sorting.

## 20. Comparing Offset, `searchAfter`, and Keyset Pagination

| Criterion | Offset `$skip` | `searchAfter` Token |
|---|---|---|
| Starting point | Number of positions to skip | A reference hit |
| API input | `page=5` | `nextToken=...` |
| Jumping to page 100 | Simple to express, expensive to run | Needs tokens or intermediate steps |
| Deep sequential browsing | Can be very resource-heavy | Usually much more efficient |
| Changing filter/sort | Compute new offset | Must discard old token |
| Live changing data | Can duplicate or miss items | Can still duplicate or miss items |

MongoDB Search supports combining `searchAfter` with a **small** `$skip` to jump a short distance from a known anchor. It does not make jumping millions of positions free.

**Manual keyset pagination** using predicates like `price > lastPrice` + `_id` fits standard MongoDB queries with deterministic sorts. When ordering by complex **relevance scores**, never invent manual score predicates thinking they behave like Search tokens.

## 21. Counts: `lowerBound` Differs from Exact `total`

A `$searchMeta` query may return:

```javascript
{
  count: { lowerBound: NumberLong("1000") }
}
```

`lowerBound` means **a lower bound**, never translate it as "exactly 1,000 results."

When an exact count is required, request:

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      },
      count: { type: "total" }
    }
  }
]);
```

Exact `total` costs more compute; many UIs do fine showing "Over 1,000 results." Never sum top-N facet bucket counts to infer total hits: buckets may be capped by `numBuckets`, array fields double-count documents, and disjunctive facets use different filters than hits.

## 22. API Design: Results, Facets, and Tokens

### 22.1. Explicit Input Contract

```json
{
  "q": "wireless",
  "filters": {
    "active": true,
    "categories": ["audio"],
    "priceMin": 0,
    "priceMax": 2000000
  },
  "sort": "relevance",
  "pageSize": 10,
  "after": null
}
```

The backend builds Search operators from **allowlisted** fields—never executing arbitrary aggregation JSON sent by clients.

### 22.2. Suggested Output Contract

```json
{
  "items": [
    {
      "id": "P001",
      "name": "Wireless Headphones Light",
      "price": 890000,
      "score": 4.2,
      "highlights": [
        {
          "path": "name",
          "texts": [
            { "type": "hit", "value": "Wireless" },
            { "type": "text", "value": " Headphones Light" }
          ]
        }
      ]
    }
  ],
  "facets": {
    "categories": [
      { "value": "audio", "count": 3 },
      { "value": "accessory", "count": 1 }
    ]
  },
  "count": {
    "value": 5,
    "relation": "lowerBound"
  },
  "nextToken": "opaque-token-from-mongodb-search",
  "previousToken": "opaque-token-from-mongodb-search"
}
```

This is an **illustrative backend contract**, not raw MongoDB output. Scores and tokens above are mock values.

### 22.3. Resetting Pagination When the Query Changes

```text
Currently viewing:
  q=wireless, category=audio, page=2
        |
        v
Also select brand=orion
        |
        v
Reset nextToken / previousToken
Return to page 1 of the new query
```

### 22.4. Protecting Tokens

An API can wrap a Search token with:

```javascript
{
  version: 1,
  queryHash: "hash-of-canonical-query-and-sort",
  searchToken: "opaque-base64",
  direction: "next"
}
```

When tokens travel to clients, verify integrity (e.g., HMAC) or store them server-side. **Base64 is neither encryption nor a signature.**

Tokens never replace authentication or authorization; the backend must reapply tenant and security filters on every page.

### 22.5. Never Allow Unbounded Page Sizes

```javascript
const requested = 10000;
const pageSize = Math.min(
  Math.max(requested, 1),
  50
);
```

Choose practical caps based on SLAs, document size, and infrastructure capacity.

## 23. `$text` + Aggregation `$facet` Without MongoDB Search

On deployments limited to legacy text search, create a text index:

```javascript
products.createIndex({
  name: "text",
  description: "text"
});
```

### 23.1. `$text` Query and `textScore`

```javascript
products.find(
  {
    $text: { $search: "wireless" },
    active: true
  },
  {
    name: 1,
    category: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" },
  _id: 1
}).limit(10);
```

### 23.2. Single Aggregation Returning Both Hits and Facets

```javascript
products.aggregate([
  {
    $match: {
      $text: { $search: "wireless" },
      active: true
    }
  },
  {
    $addFields: {
      score: { $meta: "textScore" }
    }
  },
  {
    $facet: {
      hits: [
        { $sort: { score: -1, _id: 1 } },
        { $limit: 10 },
        {
          $project: {
            name: 1,
            category: 1,
            price: 1,
            score: 1
          }
        }
      ],
      categories: [
        { $group: { _id: "$category", count: { $sum: 1 } } },
        { $sort: { count: -1, _id: 1 } }
      ],
      priceRanges: [
        {
          $bucket: {
            groupBy: "$price",
            boundaries: [0, 500000, 1000000, 2000000],
            default: "other",
            output: { count: { $sum: 1 } }
          }
        }
      ]
    }
  }
]);
```

The `$match` containing `$text` must be the first stage of the pipeline. The facet branches compute over the **full match set after `$match`**, not just the 10 `$limit`ed hits in the `hits` branch.

**Limitations:** `$text` lacks native Search `highlight` and `searchSequenceToken`. Hand-rolled regex highlighting can diverge from analyzer/stemming rules and create XSS/ReDoS risks if user input is mishandled.

## 24. Vietnamese Search and Analyzers

A system may need to handle:

```text
"tai nghe"
"tai nghe bluetooth"
"tai nghe không dây"
"khong day"
```

These strings are lexically/semantically related, yet they **do not automatically match each other** under every Search analyzer.

Decide explicitly:

- Case sensitivity requirements?
- Vietnamese accent stripping needed?
- How does the analyzer split tokens?
- Are domain synonyms like `"BT"` ↔ `"Bluetooth"` required?
- Are autocomplete or prefix suggestions needed?
- Do highlights reflect analyzer matches in a way users find intuitive?

Facets normally use **normalized tokens** for category/brand codes, whereas descriptions use **full-text analyzers**. Do not force a single analyzer onto every field just to simplify the index.

## 25. Java Sync Driver: Hits, Highlights, and Tokens

The MongoDB Java Sync Driver builds these pipelines using `Document`. `$search` syntax mirrors the server; execution requires a URI pointing to a Search-enabled deployment.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.ArrayList;
import java.util.List;

public class SearchPage307 {
    public static void main(String[] args) {
        // Mock URI; replace with a Search-enabled deployment address.
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> products = client
                .getDatabase("search_lab_307")
                .getCollection("products307");

            Document text = new Document("text",
                new Document("query", "wireless")
                    .append("path",
                        Arrays.asList("name", "description")));

            Document activeFilter = new Document("equals",
                new Document("path", "active").append("value", true));

            Document compound = new Document("must",
                Arrays.asList(text))
                .append("filter", Arrays.asList(activeFilter));

            Document search = new Document("index", "catalog_search_307")
                .append("compound", compound)
                .append("highlight", new Document(
                    "path", Arrays.asList("name", "description")))
                .append("sort", new Document("score",
                    new Document("$meta", "searchScore"))
                    .append("sku", 1));

            Document project = new Document("sku", 1)
                .append("name", 1)
                .append("price", 1)
                .append("score",
                    new Document("$meta", "searchScore"))
                .append("highlights",
                    new Document("$meta", "searchHighlights"))
                .append("paginationToken",
                    new Document("$meta", "searchSequenceToken"));

            List<Document> pipeline = Arrays.asList(
                new Document("$search", search),
                new Document("$limit", 10),
                new Document("$project", project)
            );

            List<Document> hits = products.aggregate(pipeline)
                .into(new ArrayList<>());

            for (Document hit : hits) {
                System.out.println(hit.toJson());
            }

            if (!hits.isEmpty()) {
                String nextToken = hits.get(hits.size() - 1)
                    .getString("paginationToken");
                System.out.println("Next token = " + nextToken);

                // Next request: same query/filter/sort,
                // add searchAfter: nextToken into $search.
            }
        }
    }
}
```

### 25.1. Next Page in Java

On the next request, build a new `Document search` **with identical semantics** and add:

```java
search.append("searchAfter", nextToken);
```

Never store tokens in shared static variables across users or reuse a token after filters change.

### 25.2. Facet Metadata from Java

```java
Document facet = new Document("operator",
        new Document("compound", compound))
    .append("facets", new Document("categories",
        new Document("type", "string")
            .append("path", "category")
            .append("numBuckets", 10)));

Document searchMeta = new Document("index", "catalog_search_307")
    .append("facet", facet);

List<Document> meta = products.aggregate(
    Arrays.asList(new Document("$searchMeta", searchMeta))
).into(new ArrayList<>());
```

This reuses `products` and `compound` from the Java method above. For disjunctive faceting, deliberately construct a **separate facet operator** omitting the selected dimension's filter.

## 26. Performance and Consistency

### 26.1. Facets Can Be Memory-Intensive

Faceting cost scales with **field cardinality** and concurrency—not just `numBuckets`. Faceting on `sku` across millions of distinct values does not belong in a sidebar filter UI.

### 26.2. Long Highlights Can Be Expensive

On descriptions hundreds of thousands of characters long, huge `maxCharsToExamine` and `maxNumPassages` inflate CPU, payload size, and latency. Return only necessary fields and excerpts.

### 26.3. Search Indexes Are Not Strictly Read-After-Write

MongoDB Search indexes update **asynchronously** with source writes. Right after a successful insert or update, `$search` may not reflect the change yet.

When business logic must verify a newly written order, read the source document with an appropriate consistency policy—**never treat Search results as definitive proof that a write did not occur**.

### 26.4. Facets and Hits May Observe Two Different Points in Time

When the backend issues two queries:

```text
$search -> hits
$searchMeta -> facets
```

updates can land between them. Facet counts and hit lists can therefore differ slightly under concurrent writes. Never claim two separate queries form an atomic snapshot.

### 26.5. Practical Optimizations

- Cache facet metadata keyed by `normalized query + filters + facet policy` where appropriate.
- Skip recomputing facets when the user merely clicks Next.
- Cap page sizes and projections.
- Use tokens for deep pagination instead of huge `$skip` offsets.
- Ensure deterministic sorting with tie-breakers.
- Avoid faceting on ultra-high-cardinality fields.
- Monitor `$search` and `$searchMeta` latencies separately.
- Tune mappings and analyzers around real query patterns.

## 27. Common Errors

| Symptom | Likely Cause | What to Check |
|---|---|---|
| `$search` unrecognized | Deployment lacks Search | Check Search compatibility/configuration |
| Search returns empty | Index still building, wrong field/analyzer/filter | `$listSearchIndexes`, minimal query |
| String facet fails | Field not mapped as `token` | Inspect index mapping |
| Highlights empty | Field lacks `offsets`, match in another field, char cap hit | Inspect mapping and `$project` |
| Category counts unexpectedly tiny | Computed after `$limit` or active category filter applied | Inspect facet operator and policy |
| Facet returns too few buckets | Small `numBuckets` or sparse matches | Check filter scope and cardinality |
| Page 2 repeats items | Score ties, changing data, shifting offsets | Add tie-breaker and page tokens |
| Search token rejected | Query/filter/sort changed or malformed token | Reset pagination |
| Previous page is reversed | Forgot to reverse `searchBefore` results | Reverse array before returning to UI |
| Counts disagree with display | `lowerBound`, top-N buckets, disjunctive rules | Verify count relation semantics |
| Query latency spikes | Deep `skip`, many facets, huge highlights | Trim cost and benchmark workload |

### 27.1. Never Attempt Fixes by Mutating Production Data

When a Search index is unavailable or queries misbehave, inspect configs and logs first. Never delete/reinsert production collections, drop production indexes impulsively, or alter mappings during peak hours without a rebuild plan.

## 28. Misconceptions to Avoid

| Misconception | Reality |
|---|---|
| `$text` includes `searchHighlights` | Native highlighting belongs to MongoDB Search |
| Aggregation `$facet` equals Search `facet` | Different execution layers and data sources |
| Nesting `$search` inside `$facet` is valid | `$search` is disallowed inside `$facet` branches |
| Counting facets over the top 10 hits is enough | Filter sidebars normally reflect the full match set |
| `numBuckets: 10` limits Search to reading 10 docs | Caps only the number of returned buckets |
| Mapping `category` as `string` always works for facets | Modern Search uses `token` for string facets |
| Sum of buckets equals total hits | Arrays, missing values, or top-N caps make them differ |
| Selecting a category leaves facets unchanged | Depends on conjunctive vs. disjunctive policy |
| Highlights automatically prevent XSS | UI must still escape text |
| Empty highlights mean no match | Passage/char limits can yield empty highlights |
| `searchScore` is a relevance percentage | Relative ranking signal dependent on the query |
| Sorting solely by score is always stable | Ties occur; add a tie-breaker |
| Deep `$skip` costs the same as page 1 | Deep skip can be very expensive |
| `searchAfter` prevents duplicates/gaps under live edits | Tokens are not bound to a snapshot |
| Search tokens equal Change Stream resume tokens | Completely different token systems |
| Reusing a token after changing filters works | Must restart from page 1 |
| `searchBefore` returns hits in forward UI order | Must usually reverse the array |
| Facet `lowerBound` is an exact total | It is strictly a lower bound |
| Search always sees committed writes instantly | Index updates asynchronously |
| Base64 tokens authenticate users | Tokens never replace auth or authorization |
| Facets return no docs, so they cannot leak data | Bucket counts themselves can leak sensitive info |

## 29. Practice Exercises

### Exercise 1 — Choose the Search Mechanism

A site needs: keyword search, category filtering, highlighting, and token-based Next/Previous pagination. Which features work with `$text` + `$facet`, and which require MongoDB Search? Contrast `textScore` and `searchScore`.

### Exercise 2 — Design Mappings

Given `name`, `description`, `category`, `brand`, `price`, `publishedAt`, `active`, and `sku`, choose each Search mapping type and explain why `sku` makes a good tie-breaker yet a poor sidebar facet across millions of products.

### Exercise 3 — Facet Counts

Given five hits:

```text
audio, audio, audio, accessory, computer
```

Write a `$searchMeta` string facet for `category`. If `pageSize=2`, should the category facet count 2 or 5 documents for a catalog overview UI?

### Exercise 4 — Numeric Boundaries

Given `[0, 500000, 1000000, 2000000]`, classify prices `499999`, `500000`, `999999`, `1000000`, and `2000000`. Why does `500000` not belong to the first bucket?

### Exercise 5 — Date Facets

Write a `$searchMeta` facet over quarterly intervals on `publishedAt`. If the UI uses Vietnam local dates, how must UTC `boundaries` be computed?

### Exercise 6 — Array Facets

Three documents have:

```javascript
{ tags: ["wireless", "portable"] }
{ tags: ["wireless"] }
{ tags: ["portable"] }
```

Can the sum of bucket counts exceed the document count? Why?

### Exercise 7 — Conjunctive vs. Disjunctive

A user selects `category=audio` and `brand=nova`. Specify the operator for fetching hits and the operator for computing **the `category` facet showing sibling categories**. Why can you not copy every filter verbatim?

### Exercise 8 — Invalid Pipeline

```javascript
[
  {
    $facet: {
      hits: [
        { $search: { text: { query: "wireless", path: "name" } } }
      ]
    }
  }
]
```

Why is this invalid? Fix it either with `$search` first followed by `$facet`, or with the Search `facet` collector.

### Exercise 9 — Highlighting

Given description `"Lightweight wireless headphones"` and query `wireless`, write the `texts` array with `hit`/`text` segments and explain how to render it safely in HTML.

### Exercise 10 — Empty Highlights

A description is 20,000 characters long, the match is at character 15,000, and `maxCharsToExamine=5000`. Can the document still match without returning highlights? Should you raise the limit infinitely?

### Exercise 11 — Offsets

With `pageSize=25`, calculate `skip` for pages 1, 3, and 1,000. Analyze deep-skip cost and the effect of new inserts landing at the top of results.

### Exercise 12 — Tie-Breaker

Ten documents share the exact same `searchScore`. If you sort solely by score, what pagination risk arises? Why does adding a unique `sku` clarify order without locking a snapshot?

### Exercise 13 — `searchAfter`

Write a page-1 pipeline projecting `searchSequenceToken`, then pass the last hit's token into `searchAfter`. What happens if the user changes `category` between pages?

### Exercise 14 — `searchBefore`

From the first hit's token on page 3, write a query fetching the previous page with `searchBefore`. Why must the array be reversed before display?

### Exercise 15 — Count Metadata

A query returns `count: { lowerBound: 1000 }`. The UI displays "Exactly 1,000 results." Is this right or wrong? When is `count: { type: "total" }` needed?

### Exercise 16 — Changing Data

T1: order is A(9), B(8), C(7), D(6); page 1 returns `[A, B]`. T2: C's score updates to 10. Explain why the token after B does not guarantee a duplicate-free, gap-free traversal.

### Exercise 17 — Security Filters

The hits query filters `tenantId`, while the facet query omits it. Even without returning document bodies, what information can facet counts leak? Propose a way to share security filters across both queries.

### Exercise 18 — Optimization and Monitoring

An app has millions of products, 50,000 brands, and recomputes the `brand` facet on every Next click. List at least five improvements covering cardinality, caching, indexing, pagination, highlight bounds, and p95 latency monitoring.

## 30. Reliable Implementation Workflow

1. **Verify Search support** on the deployment and inspect index status.
2. **Define business requirements:** text, category, brand, price, time, and sort orders.
3. **Create proper mappings:** `string` for text/highlights; `token` for facets/exact filters/string sorts; `number`/`date` for ranges.
4. **Build shared operators:** keep text predicates and security filters identical between hits and facets.
5. **Finalize facet semantics:** conjunctive vs. disjunctive, and what set bucket counts reflect.
6. **Pick metadata strategy:** separate `$searchMeta` or combined `$$SEARCH_META`.
7. **Configure highlights:** offsets, paths, passage bounds, and escaped rendering.
8. **Configure deterministic sorting:** relevance/price/date paired with a unique tie-breaker.
9. **Choose pagination:** offsets for early pages, `searchAfter` for deep browsing, `searchBefore` for Previous.
10. **Preserve query identity:** reset tokens whenever keywords, filters, or sorts change.
11. **Respect consistency:** Search tokens are not snapshot-bound; indexes sync asynchronously.
12. **Bound resources:** `pageSize`, faceted fields, `numBuckets`, and highlight scan limits.
13. **Monitor:** Search and metadata latency, index errors, zero-result rates, and filter usage.
14. **Enforce security:** apply tenant filters to facets, highlights, and hits; tokens never replace authentication.

## 31. Summary

**Facets** return grouping metadata across the **entire matching result set**; **highlighting** pinpoints matched text spans within **each hit**; **pagination** navigates a deterministic ordering without loading everything at once. All three complement each other without being interchangeable.

**MongoDB Search provides purpose-built tools:** `$search` for hits and `searchScore`; `$searchMeta` with the `facet` collector for category, number, and date buckets; `$meta: "searchHighlights"` for highlighted passages; and `$meta: "searchSequenceToken"`, `searchAfter`, and `searchBefore` for cursor-like pagination. Aggregation `$facet` is not the Search facet collector, and legacy `$text` has no native Search highlights.

**Correctness depends on semantics:** facets count prior to pagination under the chosen filter policy; highlights must be escaped on render; sorts require tie-breakers; tokens remain valid only for identical search queries, filters, and sorts. `searchAfter` cuts deep-pagination cost, yet **does not create a snapshot** when products are inserted, updated, or deleted mid-browsing.

By understanding these boundaries clearly, you can build MongoDB search pages that are **easy to filter**, **transparent to users**, and **efficient to browse** without making false promises about counts or data immutability.

## References

- [MongoDB Search — `$search`](https://www.mongodb.com/docs/search/query/aggregation-stages/search/): Search operators, sorting, metadata, and stage rules.
- [MongoDB Search — `$searchMeta`](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/): metadata-only queries.
- [MongoDB Search — Facet](https://www.mongodb.com/docs/search/query/operators-collectors/facet/): string/number/date facets and `$$SEARCH_META`.
- [MongoDB Search — Highlight Search Terms](https://www.mongodb.com/docs/search/query/highlighting/): offsets, `searchHighlights`, and passages.
- [MongoDB Search — Paginate Results](https://www.mongodb.com/docs/search/query/paginate-results/): `searchAfter`, `searchBefore`, and `searchSequenceToken`.
- [MongoDB Search — Token Field Type](https://www.mongodb.com/docs/search/indexes/field-types/token-type/): string facets and sorting.
- [MongoDB — `createSearchIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/): index creation.
- [MongoDB — `$text` Query](https://www.mongodb.com/docs/manual/reference/operator/query/text/): legacy text search option.
