# Search Queries, Filtering, Fuzzy, Autocomplete, and Ranking in MongoDB

## 1. Text Search Problems in Applications

A store saves products like:

~~~javascript
{
  _id: "P-100",
  tenantId: "store-a",
  title: "Chuột không dây M100",
  description: "Chuột Bluetooth nhỏ gọn, kết nối ổn định",
  category: "mouse",
  priceCents: 250000,
  active: true
}
~~~

Users may search in several ways:

- Enter **"chuột không dây"** to search both title and description.
- Mistype **"bluetooh"** and still expect to see Bluetooth products.
- Type **"chu"** and expect instant suggestions while typing.
- Pick a category, bound a price range, and view only active items.
- Rank title matches above description-only matches.
- Paginate, highlight matched snippets, and display category facet counts.
- Ensure users in **store-a** never see private products belonging to **store-b**.

A simple exact `find` cannot satisfy all of these requirements. MongoDB offers two distinct approaches:

1. **Legacy text indexes with `$text`**, supporting basic keyword matching and `textScore`.
2. **MongoDB Search** (also known as Atlas Search across many docs): dedicated Search indexes and the **`$search`**/**`$searchMeta`** aggregation stages, featuring relevance scoring, compound queries, fuzziness, autocomplete, highlighting, and facets.

This lesson focuses on building search experiences with **MongoDB Search**, while comparing it against `find`, regex, and `$text`. MongoDB Search features require a **Search-enabled deployment**—creating a legacy text index on an arbitrary standalone `mongod` is not enough.

### Objectives

After this lesson, you will be able to:

1. Distinguish exact matching, regex, full-text search, and fuzzy matching.
2. Design a Search index for full-text search, autocomplete, and structured filters.
3. Combine **`text`, `phrase`, and `compound.must`/`should`/`filter`/`mustNot`**.
4. Tune fuzziness, autocomplete, and relevance scoring.
5. Implement pagination, highlights, facets, and deterministic ordering.
6. Enforce tenant filters and secure authorization.
7. Write examples in `mongosh`, the Java Sync Driver, and Spring Data MongoDB.
8. Measure search quality, latency, and production index operations.

## 2. Exact Match, Regex, `$text`, and `$search`

### 2.1. Exact Match

~~~javascript
db.products.find({
  tenantId: "store-a",
  title: "Chuột không dây M100"
});
~~~

This is a value comparison that can leverage standard B-tree indexes. It does not understand synonyms, typos, or relevance. Collation changes string comparison rules, but does not turn exact matching into full-text search.

### 2.2. Regex

~~~javascript
db.products.find({
  title: {
    $regex: "^Chuột",
    $options: "i"
  }
});
~~~

Regex is useful for simple patterns, yet lacks tokenization, word relevance, BM25, and purpose-built autocomplete. Unanchored and case-insensitive regexes can be resource-heavy; never expose raw user-controlled regexes.

### 2.3. Legacy `$text`

~~~javascript
db.products.createIndex(
  {
    title: "text",
    description: "text"
  },
  {
    weights: {
      title: 10,
      description: 2
    }
  }
);

db.products.find(
  {
    tenantId: "store-a",
    $text: {
      $search: "wireless bluetooth"
    }
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
});
~~~

This uses a **MongoDB text index** created via `createIndex`, completely separate from a **MongoDB Search index** used by `$search`. `$text` can suffice for simple keyword search, but cannot fully replace MongoDB Search's fuzzy matching, autocomplete, facets, highlights, and ranking controls.

### 2.4. `$search`

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột không dây",
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
~~~

In a standard aggregation pipeline, **`$search` must be the first stage**. Never place `$match` before `$search` expecting Search to run on pre-filtered documents. To filter early inside the Search engine, use **`compound.filter`**.

### 2.5. Comparison Table

| Requirement | `find` / regex | `$text` | MongoDB Search |
|---|---|---|---|
| Exact ID / status / range | Ideal. | Combined in `find`. | `filter` alongside search. |
| Text relevance | Limited. | Basic. | **Rich operators and scoring.** |
| Fuzzy typo tolerance | Not built in. | Not a primary capability. | **`text`/`autocomplete` fuzzy.** |
| Typeahead autocomplete | Limited prefix regex. | Not designed for it. | **`autocomplete` operator/index.** |
| Highlights | Manual. | Manual. | **`highlight`.** |
| Facets and counts | Separate aggregation. | Separate aggregation. | **`$searchMeta`.** |
| Weighted ranking | Manual. | Text weights. | **`boost`/score functions/`compound`.** |

## 3. Sample Dataset for Queries

Use the **`mongo_search_lab`** database on a MongoDB Search-enabled deployment. Values below are test fixtures, not real products.

~~~javascript
use mongo_search_lab

db.products.insertMany([
  {
    _id: "P-100",
    tenantId: "store-a",
    title: "Chuột không dây M100",
    titleSuggest: "Chuột không dây M100",
    description: "Chuột Bluetooth nhỏ gọn, kết nối ổn định",
    category: "mouse",
    tags: ["bluetooth", "wireless"],
    priceCents: 250000,
    active: true,
    stock: 15,
    popularity: 80,
    publishedAt: ISODate("2026-05-10T08:00:00Z")
  },
  {
    _id: "P-101",
    tenantId: "store-a",
    title: "Chuột gaming RGB G1",
    titleSuggest: "Chuột gaming RGB G1",
    description: "Chuột chơi game có dây, cảm biến chính xác",
    category: "mouse",
    tags: ["gaming", "rgb"],
    priceCents: 390000,
    active: true,
    stock: 6,
    popularity: 92,
    publishedAt: ISODate("2026-05-11T08:00:00Z")
  },
  {
    _id: "P-102",
    tenantId: "store-a",
    title: "Bàn phím cơ K2",
    titleSuggest: "Bàn phím cơ K2",
    description: "Bàn phím cơ nhỏ gọn, kết nối Bluetooth",
    category: "keyboard",
    tags: ["mechanical", "bluetooth"],
    priceCents: 850000,
    active: true,
    stock: 8,
    popularity: 75,
    publishedAt: ISODate("2026-05-09T08:00:00Z")
  },
  {
    _id: "P-103",
    tenantId: "store-a",
    title: "Tai nghe không dây Air 200",
    titleSuggest: "Tai nghe không dây Air 200",
    description: "Tai nghe Bluetooth với thời lượng pin tốt",
    category: "headphone",
    tags: ["wireless", "audio"],
    priceCents: 620000,
    active: true,
    stock: 0,
    popularity: 88,
    publishedAt: ISODate("2026-05-08T08:00:00Z")
  },
  {
    _id: "P-104",
    tenantId: "store-a",
    title: "Chuột Bluetooth M2",
    titleSuggest: "Chuột Bluetooth M2",
    description: "Chuột không dây êm và nhẹ cho văn phòng",
    category: "mouse",
    tags: ["wireless", "office"],
    priceCents: 320000,
    active: true,
    stock: 22,
    popularity: 67,
    publishedAt: ISODate("2026-05-12T08:00:00Z")
  },
  {
    _id: "P-105",
    tenantId: "store-a",
    title: "Chuột không dây đời cũ",
    titleSuggest: "Chuột không dây đời cũ",
    description: "Sản phẩm đã ngừng kinh doanh",
    category: "mouse",
    tags: ["wireless"],
    priceCents: 180000,
    active: false,
    stock: 0,
    popularity: 30,
    publishedAt: ISODate("2025-12-20T08:00:00Z")
  },
  {
    _id: "P-900",
    tenantId: "store-b",
    title: "Chuột không dây B-Pro",
    titleSuggest: "Chuột không dây B-Pro",
    description: "Mẫu riêng của cửa hàng B",
    category: "mouse",
    tags: ["wireless"],
    priceCents: 280000,
    active: true,
    stock: 12,
    popularity: 100,
    publishedAt: ISODate("2026-05-13T08:00:00Z")
  }
]);
~~~

**Run the seed once on a fresh collection.** Re-running when `_id` values exist triggers duplicate key errors. Exact result ordering and relevance scores vary with analyzer, index, corpus, and search engine version.

### 3.1. Why Include `titleSuggest`?

For clarity, documents store two fields:

- **`title`**: mapped as full-text **`string`**.
- **`titleSuggest`**: mapped as **`autocomplete`** with the same title text.

Some Search configurations support **multiple mapping types on a single field** to avoid duplicating `title`; separating them here keeps the index definition simpler to follow. Whenever `title` changes, the app must update `titleSuggest` consistently.

### 3.2. Data Conventions

**`tenantId`** and **`category`** are normalized identifier strings for exact filters; **`active`** is a boolean; **`priceCents`/`stock`/`popularity`** are numbers; **`publishedAt`** is a BSON Date.

Never let clients send an arbitrary `tenantId` to self-assert search scope. Derive the tenant from the server-verified user identity.

## 4. Creating a MongoDB Search Index

MongoDB Search uses a **Search index**, distinct from B-tree or text indexes created by `createIndex`. Management tooling varies by environment: MongoDB Atlas UI/API, `mongosh`, or Search-enabled deployments.

### 4.1. Illustrative Index Mapping

~~~javascript
db.products.createSearchIndex(
  "products_search",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: {
          type: "string",
          analyzer: "lucene.standard"
        },
        titleSuggest: {
          type: "autocomplete",
          tokenization: "edgeGram",
          minGrams: 2,
          maxGrams: 15,
          foldDiacritics: true
        },
        description: {
          type: "string",
          analyzer: "lucene.standard"
        },
        tags: {
          type: "string",
          analyzer: "lucene.standard"
        },
        tenantId: {
          type: "token"
        },
        category: {
          type: "token"
        },
        active: {
          type: "boolean"
        },
        stock: {
          type: "number"
        },
        priceCents: {
          type: "number"
        },
        popularity: {
          type: "number"
        },
        publishedAt: {
          type: "date"
        }
      }
    }
  }
);
~~~

**Note:** `createSearchIndex` syntax and mapping options require support from your deployment and server version. Environments without MongoDB Search cannot simply add a regular index and run `$search`.

### 4.2. Mapping Semantics

| Field | Mapping | Purpose |
|---|---|---|
| `title` | **string** | Full-text ranking, phrase matching. |
| `titleSuggest` | **autocomplete** | Prefix suggestions while typing. |
| `description`, `tags` | **string** | Full-text recall. |
| `tenantId`, `category` | **token** | Exact string equality, category facets. |
| `active` | **boolean** | Active products only. |
| `stock`, `priceCents` | **number** | Range/equality filters. |
| `popularity` | **number** | Available as a ranking signal. |
| `publishedAt` | **date** | Recency filtering or boosting. |

**`dynamic:false`** indexes only explicitly listed fields, keeping Search index size bounded and preventing accidental indexing of sensitive data.

### 4.3. `token` vs. Analyzed `string`

**`string`** fields are split into terms by a tokenizer/analyzer, ideal for keyword search.

**`token`** stores the intact string value such as **`tenantId = store-a`** or **`category = mouse`**. Mapping `tenantId` with a full-text analyzer breaks whole-value equality semantics.

For tenant fields, you can configure a normalizer per data policy. If the index preserves casing, ensure writes and `tenantId` filters stay consistent.

### 4.4. Analyzers for Vietnamese

Analyzers govern how text is:

- Split into terms.
- Normalized for casing and diacritics.
- Handled for Unicode, stop words, and stemming where applicable.
- Synchronized between index time and query time.

**`lucene.standard`** does not guarantee accurate Vietnamese word segmentation in all cases. Terms such as **`chuột`, `chuot`, `điện thoại`, `dien thoai`** must be tested on a real corpus. If unaccented matching, synonyms, or advanced segmentation are required, design dedicated analyzers/normalized fields and an evaluation suite.

Edit-distance fuzziness **does not replace a Vietnamese linguistic processor**.

### 4.5. Waiting for the Search Index to Be Ready

Search index creation runs **asynchronously**. In `mongosh`, check with:

~~~javascript
db.products.getSearchIndexes();
~~~

Wait until the Search index reports queryable/ready status before evaluating queries. Results or errors observed while still building do not reflect steady-state behavior.

### 4.6. Do Not Confuse Index Names

~~~text
createIndex({title:"text"})     -> MongoDB text index
createSearchIndex("products_search", definition)
                               -> MongoDB Search index
~~~

Inside `$search`, specify **`index:"products_search"`**. A `$text` index cannot substitute for it.

## 5. Full-Text Queries with the `text` Operator

### 5.1. Searching a Single Field

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "Bluetooth",
        path: "title"
      }
    }
  },
  {
    $project: {
      title: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

MongoDB Search analyzes the query via the active analyzer/`searchAnalyzer` and evaluates documents whose `title` contains matching terms. This is not a raw literal substring operator.

### 5.2. Searching Multiple Fields Simultaneously

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "Bluetooth",
        path: [
          "title",
          "description",
          "tags"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

A product mentioning `Bluetooth` in `description` or `tags` can still match even if `title` omits it. To weight `title` above `description`, use **`compound.should`** with different boosts instead of treating all paths equally.

### 5.3. Multi-Word Queries

~~~javascript
{
  $search: {
    index: "products_search",
    text: {
      query: "chuột không dây",
      path: ["title", "description"]
    }
  }
}
~~~

Terms are tokenized by the analyzer and are not required to be adjacent or ordered like a phrase. When business logic requires matching the phrase **"không dây"**, use the **`phrase` operator** or explicit compound clauses.

### 5.4. `text` Query Array

The Search `text` operator accepts an array of query strings:

~~~javascript
{
  $search: {
    index: "products_search",
    text: {
      query: ["bluetooth", "wireless"],
      path: ["description", "tags"]
    }
  }
}
~~~

Understand `text` operator and analyzer semantics: passing a query array **does not require both strings to appear together**. When multiple conditions are mandatory, place separate clauses in **`compound.must`**.

## 6. Exact Phrase Matching with `phrase`

**`phrase`** is ideal when token order and proximity matter.

### 6.1. Exact Phrase

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      phrase: {
        query: "không dây",
        path: "title",
        slop: 0
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
~~~

With **`slop:0`**, phrase terms must appear immediately adjacent in the token stream emitted by the analyzer. Punctuation, stop words, and analyzer transformations affect adjacency, so test against actual data and analyzers.

### 6.2. Allowing Distance (`slop`)

~~~javascript
{
  $search: {
    index: "products_search",
    phrase: {
      query: "chuột M100",
      path: "title",
      slop: 2
    }
  }
}
~~~

**`slop`** permits bounded token-position gaps—it is not character distance or fuzzy edit distance.

### 6.3. Combining `text` and `phrase`

When a user enters `"chuột không dây"`, you can match products containing the terms and **boost** those matching the exact phrase. This is a ranking improvement, without discarding relevant documents that lack the exact contiguous phrase.

## 7. Other Search Operators to Know

| Operator | Purpose | Example Use Case |
|---|---|---|
| **text** | Match terms via analyzer. | Keyword product search. |
| **phrase** | Match ordered/proximate term sequences. | `"không dây"`, meaningful multi-word names. |
| **autocomplete** | Prefix suggestions while typing. | User types `"chu"`. |
| **equals** | Exact comparison on typed fields. | `tenantId`, `active`, `category`. |
| **range** | Numeric or date intervals. | Price 200,000–500,000. |
| **in** | Membership in a value list. | Multiple allowed categories. |
| **exists** | Field presence per Search mapping. | Has an indexed `description`. |
| **wildcard** | Wildcard term pattern matching. | Specialized pattern lookups. |
| **regex** | Lucene regex pattern matching. | Structured product codes. |
| **near** | Proximity to a number, date, or geo point. | Boost recently published products. |

**Do not equate MongoDB Search `regex` with MongoDB `$regex` in `find`.** Their syntax, analyzer interaction, and indexing behavior differ.

Broad Search `wildcard` or `regex` queries can be expensive. For typeahead UIs, **`autocomplete` is usually far better** than running wildcards over the whole corpus.

## 8. `compound`: Combining Search and Filtering

Production APIs must combine relevance with hard constraints:

- Authenticated tenant only.
- `active=true` products only.
- Price within range.
- Included or excluded categories.
- Multiple weighted text signals.

MongoDB Search **`compound`** provides four clauses:

| Clause | Meaning | Contributes to Relevance Score? |
|---|---|---|
| **must** | All clauses must match. | Yes, via child scores. |
| **should** | Boosts score when matched; can enforce a minimum match count. | Yes. |
| **filter** | All conditions must hold. | **No** score contribution. |
| **mustNot** | Excludes matching documents. | No. |

### 8.1. Mandatory Keyword, Tenant Filter, and Active Filter

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "store-a"
            }
          },
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
      title: 1,
      tenantId: 1,
      active: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

**`P-900` belonging to `store-b` must be excluded**, despite its matching title and high popularity. Inactive `P-105` is also excluded.

### 8.2. Filtering by Price and Stock

~~~javascript
{
  $search: {
    index: "products_search",
    compound: {
      must: [
        {
          text: {
            query: "chuột",
            path: ["title", "description"]
          }
        }
      ],
      filter: [
        {
          equals: {
            path: "tenantId",
            value: "store-a"
          }
        },
        {
          equals: {
            path: "active",
            value: true
          }
        },
        {
          range: {
            path: "priceCents",
            gte: 200000,
            lte: 500000
          }
        },
        {
          range: {
            path: "stock",
            gt: 0
          }
        }
      ]
    }
  }
}
~~~

Price filters compare **numerically**, avoiding lexicographical string bugs like `"500000"` vs. `"90000"`. If prices change frequently, account for Search index sync lag—final checkout pricing must always be verified in the write/checkout path.

### 8.3. `mustNot`

Exclude a category:

~~~javascript
{
  compound: {
    must: [
      {
        text: {
          query: "không dây",
          path: ["title", "description"]
        }
      }
    ],
    filter: [
      {
        equals: {
          path: "tenantId",
          value: "store-a"
        }
      }
    ],
    mustNot: [
      {
        equals: {
          path: "category",
          value: "headphone"
        }
      }
    ]
  }
}
~~~

`mustNot` removes matching documents rather than subtracting score from remaining hits.

### 8.4. `should` and `minimumShouldMatch`

~~~javascript
{
  compound: {
    should: [
      {
        text: {
          query: "chuột",
          path: "title"
        }
      },
      {
        text: {
          query: "chuột",
          path: "description"
        }
      }
    ],
    minimumShouldMatch: 1,
    filter: [
      {
        equals: {
          path: "tenantId",
          value: "store-a"
        }
      }
    ]
  }
}
~~~

**`minimumShouldMatch:1`** requires at least one `should` clause to match. When a `compound` mixes `filter` or `must` with `should`, omitting `minimumShouldMatch` turns `should` into an optional score booster—letting documents without the keyword match purely via `filter`.

### 8.5. AND Across Keywords

If business rules require both **chuột** and **bluetooth**:

~~~javascript
{
  compound: {
    must: [
      {
        text: {
          query: "chuột",
          path: ["title", "description"]
        }
      },
      {
        text: {
          query: "bluetooth",
          path: ["title", "description", "tags"]
        }
      }
    ]
  }
}
~~~

Each `must` clause is analyzed independently and must match. Results remain subject to each clause's tokenization and stemming.

### 8.6. Why Filter Inside `$search`?

Compare two approaches:

~~~javascript
// Early filter inside the Search engine.
{
  $search: {
    index: "products_search",
    compound: {
      must: [{ text: { query: "chuột", path: "title" } }],
      filter: [{ equals: { path: "tenantId", value: "store-a" } }]
    }
  }
}
~~~

~~~javascript
// Search first, then filter with aggregation $match.
{
  $search: {
    index: "products_search",
    text: {
      query: "chuột",
      path: "title"
    }
  }
},
{
  $match: {
    tenantId: "store-a"
  }
}
~~~

The second pattern forces Search to evaluate unnecessary candidates and breaks pagination/counts if `$limit` runs before `$match`. When Search index operators support the predicate, **`compound.filter` is preferred**. Still, enforce authorization in the API tier rather than trusting client-supplied tenant IDs.

## 9. Fuzzy Search: Controlled Typo Tolerance

Users may type **"bluetooh"** instead of **"bluetooth"**. Fuzzy matching expands term lookup using **edit distance** (insertions, deletions, or substitutions).

### 9.1. `text.fuzzy`

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "bluetooh",
              path: ["title", "description", "tags"],
              fuzzy: {
                maxEdits: 1,
                prefixLength: 2,
                maxExpansions: 50
              }
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

With `maxEdits=1`, a single-character omission is treated as a near match. Actual results depend on the analyzer and indexed tokens.

### 9.2. Meaning of the Three Parameters

| Parameter | Meaning | Trade-Off |
|---|---|---|
| **maxEdits** | Maximum allowed edits (typically 1 or 2). | Higher raises recall, but increases false positives and cost. |
| **prefixLength** | Leading characters that must match exactly. | Higher improves precision, but misses typos near the start. |
| **maxExpansions** | Cap on candidate variants explored during expansion. | Higher increases query cost. |

Edit distance **understands zero semantics**. Two tokens differing by one character can represent completely different SKUs. For SKUs or transaction IDs, prefer exact matching before fuzzy fallback.

### 9.3. Scaling `maxEdits` with Query Length

A common application heuristic:

~~~text
query length < 3  -> no fuzzy; suggest prefix or ask for more input.
3–5 characters    -> try maxEdits=1.
longer queries    -> can try maxEdits=1 or 2, per corpus and SLA.
~~~

This is not a MongoDB default rule. Benchmark precision, recall, and latency—especially for short tokens.

### 9.4. Prioritizing Exact Matches Over Fuzzy Matches

~~~javascript
{
  $search: {
    index: "products_search",
    compound: {
      should: [
        {
          text: {
            query: "bluetooh",
            path: ["title", "description"],
            score: { boost: { value: 5 } }
          }
        },
        {
          text: {
            query: "bluetooh",
            path: ["title", "description"],
            fuzzy: {
              maxEdits: 1,
              prefixLength: 2
            },
            score: { boost: { value: 1 } }
          }
        }
      ],
      minimumShouldMatch: 1,
      filter: [
        { equals: { path: "tenantId", value: "store-a" } }
      ]
    }
  }
}
~~~

When spelling is exact, the exact clause boosts the score higher; when misspelled, the fuzzy clause preserves recall. Final scores depend on all clauses, term statistics, and score combination—not just one boost multiplier.

### 9.5. Limits of Fuzziness for Vietnamese

Fuzziness does not automatically bridge every unaccented string to accented Vietnamese. Pairs like **"chuột"** and **"chuot"** depend on Unicode normalization, analyzers, and mappings. For unaccented Vietnamese search, design dedicated folded analyzers/fields and a Vietnamese test suite instead of merely bumping `maxEdits`.

### 9.6. Fuzziness and Synonyms

MongoDB Search supports synonyms via index configuration, yet **combining `text.fuzzy` and `synonyms` in the same clause has restrictions**. When both synonym expansion and typo tolerance are needed, separate them into distinct clauses and check version-specific docs rather than enabling both on one operator blindly.

## 10. Autocomplete: Suggestions While Typing

Fuzziness and autocomplete solve different goals:

~~~text
Fuzzy:
  "bluetooh" -> can match "Bluetooth".

Autocomplete:
  "Chu" -> suggests "Chuột không dây M100".
~~~

Autocomplete requires a field mapped as **`type:"autocomplete"`**, such as **`titleSuggest`** here.

### 10.1. Prefix Suggestions Query

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            autocomplete: {
              query: "Chu",
              path: "titleSuggest",
              tokenOrder: "sequential"
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 8 }
]);
~~~

Always limit autocomplete results to avoid returning huge slices of the catalog on the first few keystrokes.

### 10.2. Tokenization Modes

| Mode | Meaning | Use Case |
|---|---|---|
| **edgeGram** | Indexes prefixes from the start of each token. | Typing starts of words or names. |
| **rightEdgeGram** | Indexes suffixes from the end of each token. | Suffix matching needs. |
| **nGram** | Indexes substrings at any position. | Infix matching, at the cost of larger indexes. |

For **`bluetooth`**, `edgeGram` (`minGrams=2`) generates prefixes such as **`bl`, `blu`, `blue`, `bluet`** up to `maxGrams`. **`minGrams`/`maxGrams`** are index-time settings; changing them requires updating/rebuilding the Search index.

### 10.3. `tokenOrder`

~~~javascript
{
  autocomplete: {
    query: "chuột không",
    path: "titleSuggest",
    tokenOrder: "sequential"
  }
}
~~~

**`sequential`** requires query tokens to appear in order; **`any`** relaxes token ordering. Test both against your corpus to pick the best UX.

### 10.4. Autocomplete with Fuzziness

~~~javascript
{
  autocomplete: {
    query: "bluetoh",
    path: "titleSuggest",
    tokenOrder: "sequential",
    fuzzy: {
      maxEdits: 1,
      prefixLength: 2,
      maxExpansions: 50
    }
  }
}
~~~

Fuzzy autocomplete recovers typos while typing a prefix. However, very short queries combined with high `maxEdits` return noisy suggestions. Enforce minimum query length, debouncing, and quality checks.

### 10.5. Autocomplete Does Not Equal Full-Word Relevance

An exact phrase title does not automatically outrank every prefix match under pure autocomplete scoring. To favor exact/full-word matches:

- Combine **`text`/`phrase`** with **`autocomplete`** inside `compound.should`.
- Boost title or exact-phrase matches.
- Incorporate popularity or recency signals carefully.
- Re-rank shortlists using business rules where appropriate.

### 10.6. Frontend Debouncing

~~~text
User types "c":    no need to query yet.
User types "ch":   wait briefly.
User types "chu":  call suggest API.
User keeps typing: cancel or discard stale response.
~~~

Debounce intervals depend on UX and traffic, typically a few hundred milliseconds. **Debouncing is application logic**, not a `$search` option.

### 10.7. Autocomplete Does Not Automatically Deduplicate Suggestions

A query may match multiple documents sharing similar names. To show each suggestion once, deduplicate results or query a dedicated suggestions model—enabling `autocomplete` does not deduplicate automatically.

**Security:** autocomplete endpoints must also enforce `tenantId`, `active`, and visibility permissions, or they become an information-disclosure channel across tenants.

## 11. Ranking Results with `searchScore`

In full-text search, knowing whether a document matches is only half the task—we also need **how well it matches**.

MongoDB Search assigns a **relevance score** to matching documents. For full-text search, it typically uses term-statistics models such as BM25, combined with operator, analyzer, and score settings.

### 11.1. Retrieving the Score

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột",
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

**`searchScore` is a relative ranking metric within a query/index context**, not a correctness percentage or calibrated probability. Never display "87% match" in the UI just because `score = 8.7`.

### 11.2. Why Scores Vary

Contributing factors include:

- Which field matched the term.
- Term rarity vs. frequency across the corpus.
- Term frequency and field length normalization.
- Analyzers, tokenization, and synonyms.
- Fuzzy/phrase matching and scoring operators.
- Index configuration, score boosts, and score functions.
- Corpus growth and Search index versions.

Therefore, **never compare `searchScore` across two different queries as an absolute quantity**, and never hardcode score cutoffs without empirical evaluation.

### 11.3. Boosting `title` Above `description`

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        should: [
          {
            text: {
              query: "chuột",
              path: "title",
              score: {
                boost: { value: 5 }
              }
            }
          },
          {
            text: {
              query: "chuột",
              path: "description",
              score: {
                boost: { value: 1 }
              }
            }
          }
        ],
        minimumShouldMatch: 1,
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

**`boost` never forces a non-matching clause to match.** It scales a clause's score only when it matches. If a product matches only in `description`, boosting `title` does not turn it into a `title` match.

### 11.4. Prioritizing Exact Phrase Matches

~~~javascript
{
  $search: {
    index: "products_search",
    compound: {
      should: [
        {
          phrase: {
            query: "không dây",
            path: "title",
            slop: 0,
            score: { boost: { value: 6 } }
          }
        },
        {
          text: {
            query: "không dây",
            path: "title",
            score: { boost: { value: 3 } }
          }
        },
        {
          text: {
            query: "không dây",
            path: "description",
            score: { boost: { value: 1 } }
          }
        }
      ],
      minimumShouldMatch: 1,
      filter: [
        { equals: { path: "tenantId", value: "store-a" } }
      ]
    }
  }
}
~~~

A product matching the phrase also earns contributions from the other matching clauses. Clause interactions determine the final total; never assume it equals `6+3+1`.

### 11.5. Constant Scores and Score Functions

MongoDB Search provides additional score modifiers such as:

~~~javascript
score: {
  constant: {
    value: 5
  }
}
~~~

**`constant`** replaces the computed score with a fixed value for that clause, unlike **`boost`**, which multiplies the relevance score.

Search also supports **function scoring** to blend relevance with numeric fields, recency, or mathematical expressions. When doing so:

1. Normalize signals (do not let popularity `0–1,000,000` drown out relevance `1–10`).
2. Never boost an inactive or cross-tenant product into valid results; enforce those in `filter`.
3. Evaluate signal effects against a real query set.
4. Avoid fragile business rules tied to unversioned score formulas.

### 11.6. Recency and Popularity

In product search, recency and popularity serve well as secondary signals:

~~~text
Final ranking considerations:

Primary: text relevance / exact phrase / title match.
Secondary: popularity, publishedAt, in-stock.
Hard constraints: tenantId, active, authorized categories.
~~~

If a brand-new product lacks the search keyword, boosting recency **should not inject it into results** unless a discovery mode is explicitly intended.

### 11.7. Filters Add Zero Score

A document matching `tenantId="store-a"` and `active=true` should not gain extra relevance just for being authorized. That is why mandatory constraints belong in **`compound.filter`**.

Never put `"active"` or tenant IDs in `must.text` to fake security or status filtering.

### 11.8. Inspecting Score Details During Tuning

Supported MongoDB Search versions offer **`scoreDetails`** to explain score contributions:

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột",
        path: "title"
      },
      scoreDetails: true
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" },
      scoreDetails: { $meta: "searchScoreDetails" }
    }
  }
]);
~~~

**`scoreDetails` is meant for debugging and tuning** and adds overhead. Do not return internal scoring breakdowns to all production clients.

### 11.9. Sorting by Score and Stability

~~~javascript
{ $sort: { score: -1, _id: 1 } }
~~~

Sorts descending by score with `_id` as a tie-breaker. Keep in mind that updates to the Search index alter term statistics and rankings. **Deterministic sorting on an immutable snapshot differs from stable pagination over a live updating catalog.**

## 12. Highlighting: Emphasizing Matched Spans

Search results often display matched snippets:

~~~text
Chuột Bluetooth M2
Description: Chuột không dây êm và nhẹ cho văn phòng
                   ^^^^^^^^^^^^^^^
~~~

MongoDB Search provides **`highlight`** to return matching text snippets and token spans.

### 12.1. Requesting Highlights

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "bluetooth",
        path: ["title", "description"]
      },
      highlight: {
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" },
      highlights: { $meta: "searchHighlights" }
    }
  },
  { $limit: 10 }
]);
~~~

Highlight output returns structured path, text, and hit/text segment metadata per the Search schema. It is **not** a pre-built HTML string wrapped in `<mark>` tags.

### 12.2. Safe Frontend Rendering

Never take database text and assign it directly to `innerHTML` unescaped. In web apps:

- Render each segment as a safe text node.
- Apply styling classes to matched segments.
- Escape/encode user-generated content.
- Verify tenant and field visibility before returning highlight metadata.

Highlighting improves UX; it never replaces XSS defenses or authorization.

### 12.3. Highlights Do Not Guarantee Exact Whole-Query Equivalence

Fuzziness and analyzers transform terms, so highlight spans reflect Search token matching semantics. Never use highlights as proof that a document is "100% exact."

### 12.4. When to Skip Highlights

An autocomplete dropdown showing 5 product titles may only need title, thumbnail, and category. Skip highlighting overhead when the UI does not render snippets.

## 13. Counts and Faceted Search with `$searchMeta`

A search page often has two regions:

~~~text
Results for "bluetooth": 27 products

Category:
  Mouse (12)
  Keyboard (7)
  Headphone (8)

Price:
  Under 200,000
  200,000–500,000
  Over 500,000
~~~

**`$searchMeta`** returns Search metadata such as counts and facets without returning the full result documents.

### 13.1. Counting Matching Results

~~~javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "bluetooth",
              path: ["title", "description", "tags"]
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      },
      count: {
        type: "total"
      }
    }
  }
]);
~~~

**`total`** computes an exact count under query semantics; **`lowerBound`** can be chosen when latency takes priority over an exact count.

Never count across all tenants and display it alongside tenant-filtered results. Count queries must share the exact same business filters.

### 13.2. Category and Price Facets

~~~javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_search",
      facet: {
        operator: {
          compound: {
            must: [
              {
                text: {
                  query: "bluetooth",
                  path: ["title", "description", "tags"]
                }
              }
            ],
            filter: [
              { equals: { path: "tenantId", value: "store-a" } },
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
          priceBands: {
            type: "number",
            path: "priceCents",
            boundaries: [
              0,
              200000,
              500000,
              1000000
            ],
            default: "other"
          }
        }
      }
    }
  }
]);
~~~

Faceted fields must have compatible index mappings. For `category`, **`token`** mapping supports exact string faceting in modern Search versions; for `priceBands`, numeric fields must be mapped as `number`.

### 13.3. Facet Counts Depend on Active Filters

If the user selects **`category=mouse`** and the facet query also filters `category=mouse`, the `categories` facet returns only `mouse`, hiding sibling categories in the sidebar.

Depending on UX, use **disjunctive faceting**: when computing counts for the `category` facet, retain tenant, active, text, and price filters while omitting the active `category` filter. This may require multiple metadata queries or dedicated facet pipelines; align semantics with the product team.

### 13.4. Counts/Facets and Search Index Freshness

A Search index synced from MongoDB is not a transactionally consistent read of every business metric at the exact millisecond a user clicks. Counts and facets update in **near-real-time** as the Search index syncs.

Never use facet counts or Search results as the final check for pricing or inventory before committing an order.

## 14. Paginating Search Results

A search endpoint should never dump thousands of documents in one response. Typically 10–30 items per page plus total/next-page indicators suffice.

### 14.1. `$skip`/`$limit` for Early Pages

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      category: 1,
      priceCents: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $skip: 0 },
  { $limit: 10 }
]);
~~~

Page 2 can pass `skip=10`. However, **deep pagination** (huge `skip`) forces the engine to scan and discard vast numbers of hits, increasing latency and memory. Furthermore, concurrent Search index updates can shift item order between page fetches.

### 14.2. `searchAfter` and Sequence Tokens

MongoDB Search supports cursor-style pagination via **`searchSequenceToken`** on compatible versions/deployments. A request retrieves the token per hit:

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột",
              path: "title"
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } }
        ]
      },
      sort: {
        score: { $meta: "searchScore" },
        publishedAt: -1
      }
    }
  },
  {
    $project: {
      title: 1,
      publishedAt: 1,
      score: { $meta: "searchScore" },
      pageToken: { $meta: "searchSequenceToken" }
    }
  },
  { $limit: 10 }
]);
~~~

The next page passes **`searchAfter`** using the last item's token from the previous page, keeping the **identical query, filters, and sort**:

~~~javascript
{
  $search: {
    index: "products_search",
    text: {
      query: "chuột",
      path: "title"
    },
    sort: {
      score: { $meta: "searchScore" },
      publishedAt: -1
    },
    searchAfter: savedSearchSequenceToken
  }
}
~~~

The second snippet illustrates `searchAfter` structure. In real applications, **`savedSearchSequenceToken`** must be a valid token returned by Search, and **all query predicates and tenant filters must match the prior page**—never drop tenant restrictions when fetching subsequent pages.

### 14.3. Search Pagination Tokens Are Not Change Stream Resume Tokens

~~~text
MongoDB Search searchSequenceToken:
  -> Pagination position within Search results.

MongoDB Change Stream resume token:
  -> Position within the stream of committed database changes.
~~~

The two tokens serve completely different purposes and are not interchangeable.

### 14.4. Deterministic Ordering and Tie-Breaking

When multiple documents share identical scores or `publishedAt` timestamps, strict ordering requires a **secondary unique tie-break field indexed for Search sorting**. Tokens are valid only under the semantics of their corresponding query and sort specification.

Never expect zero pagination drift if the catalog or Search index updates mid-scroll. If immutable snapshot pagination is required, store a stateful result snapshot outside standard Search pagination.

### 14.5. Securing Page Tokens

Never treat a pagination token as proof of authorization. The API must verify tenant and permissions **on every page**. Sign or encrypt opaque tokens at the API layer if tampering or internal metadata exposure is a concern; never trust client-supplied tokens as access proof.

## 15. A Complete Product Search Pipeline

Suppose a user submits:

~~~text
q = "chuột không dây"
category = mouse
price = 200,000–500,000 VND
inStock = true
tenant = store-a (authenticated by backend)
~~~

Goals:

1. Full-text search on `title` and `description`.
2. Boost exact ordered phrase on `title`.
3. Filter by tenant, `active`, `category`, `priceCents`, and `stock`.
4. Return `title`, `priceCents`, `score`, and `highlights`.
5. Limit to the top 10 results.

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột không dây",
              path: ["title", "description"]
            }
          }
        ],
        should: [
          {
            phrase: {
              query: "chuột không dây",
              path: "title",
              slop: 0,
              score: {
                boost: { value: 6 }
              }
            }
          },
          {
            text: {
              query: "chuột không dây",
              path: "title",
              score: {
                boost: { value: 3 }
              }
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } },
          { equals: { path: "category", value: "mouse" } },
          {
            range: {
              path: "priceCents",
              gte: 200000,
              lte: 500000
            }
          },
          { range: { path: "stock", gt: 0 } }
        ]
      },
      highlight: {
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      description: 1,
      category: 1,
      priceCents: 1,
      stock: 1,
      score: { $meta: "searchScore" },
      highlights: { $meta: "searchHighlights" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

### 15.1. Distinct Roles of Each Clause

| Clause | Role |
|---|---|
| `must.text` | Requires matching query terms per analyzer. |
| `should.phrase` | Rewards exact phrase matches in `title`. |
| `should.text` (`title`) | Rewards matching `title` relevance. |
| `filter.tenantId` | Enforces store tenant boundary. |
| `filter.active` | Hides discontinued products. |
| `filter.category` | Restricts to the selected category. |
| `filter.priceCents` | Bounds price range. |
| `filter.stock` | Requires positive stock per Search index. |
| `highlight` | Returns keyword-highlighted snippets. |
| `sort`/`limit` | Returns top shortlist by score. |

### 15.2. Why Split Search into Two Modes?

Applications typically separate:

**Search results mode:** complete user query with filters, pagination, and highlights.

**Suggest mode:** while typing, short query using `autocomplete`, returning 5–8 lightweight suggestions.

Running fuzzy + phrase + highlight + facets + deep pagination on **every keypress** spikes cost and latency without helping UX.

### 15.3. What This Query Does Not Guarantee

- Does not atomically confirm live price or stock at checkout.
- Does not guarantee zero-lag Search index sync after writes.
- Does not create a transactional snapshot across MongoDB collections.
- Does not deduplicate CDC/outbox events if combined with external pipelines.
- Does not handle unaccented Vietnamese or synonyms unless configured in the index/analyzer.
- Does not turn scores into relevance probabilities.

## 16. Building a Secure Search API

### 16.1. Never Accept Raw Pipelines from Clients

Flawed design:

~~~text
POST /search
body = { "aggregationPipeline": [ ...user-controlled... ] }
~~~

Allowing clients to pass arbitrary Search operators or raw aggregation stages risks tenant bypass, unintended feature abuse, and expensive resource-exhaustion queries.

APIs should accept **strictly typed parameters**:

~~~json
{
  "query": "chuột",
  "category": "mouse",
  "minPriceCents": 200000,
  "maxPriceCents": 500000,
  "inStock": true,
  "limit": 10
}
~~~

The backend **assembles an allowlisted Search DSL**, never forwarding client JSON directly as a pipeline.

### 16.2. Pseudocode for Building `compound.filter`

~~~javascript
function buildProductSearchStages(request, authenticatedTenantId) {
  const q = String(request.query || "").trim();
  if (q.length < 2 || q.length > 100) {
    throw new Error("Query length is outside allowed range");
  }

  const limit = Math.min(
    30,
    Math.max(1, Number(request.limit || 10))
  );

  if (!Number.isSafeInteger(limit)) {
    throw new Error("Invalid limit");
  }

  const filters = [
    {
      equals: {
        path: "tenantId",
        value: authenticatedTenantId
      }
    },
    {
      equals: {
        path: "active",
        value: true
      }
    }
  ];

  const allowedCategories = new Set([
    "mouse",
    "keyboard",
    "headphone"
  ]);

  if (request.category != null) {
    if (!allowedCategories.has(request.category)) {
      throw new Error("Invalid category");
    }
    filters.push({
      equals: {
        path: "category",
        value: request.category
      }
    });
  }

  if (request.inStock === true) {
    filters.push({
      range: {
        path: "stock",
        gt: 0
      }
    });
  }

  const min = request.minPriceCents;
  const max = request.maxPriceCents;

  if (min != null || max != null) {
    if (
      (min != null && (!Number.isSafeInteger(min) || min < 0)) ||
      (max != null && (!Number.isSafeInteger(max) || max < 0)) ||
      (min != null && max != null && min > max)
    ) {
      throw new Error("Invalid price range");
    }

    const priceRange = { path: "priceCents" };
    if (min != null) priceRange.gte = min;
    if (max != null) priceRange.lte = max;
    filters.push({ range: priceRange });
  }

  return [
    {
      $search: {
        index: "products_search",
        compound: {
          must: [
            {
              text: {
                query: q,
                path: ["title", "description"]
              }
            }
          ],
          filter: filters
        }
      }
    },
    {
      $project: {
        title: 1,
        priceCents: 1,
        category: 1,
        score: { $meta: "searchScore" }
      }
    },
    { $sort: { score: -1, _id: 1 } },
    { $limit: limit }
  ];
}
~~~

This snippet illustrates a query builder, **not complete routing or authentication middleware**. It allows only fixed paths and filters, and receives `authenticatedTenantId` from server-side authentication.

### 16.3. Never Accept Arbitrary Score Boosts

If a client sends:

~~~json
{
  "boost": 1000000
}
~~~

and the backend injects it into score functions, results become unstable and costly. Permit only allowlisted, versioned, tested **ranking profiles**.

### 16.4. Minimize Returned Fields

Project only UI-needed fields: ID, title, price, image, category, and score/highlights when requested. Never return full documents exposing `wholesalePrice`, `internalNotes`, emails, or restricted attributes.

### 16.5. Never Use Search for Critical Transactional Decisions

Suppose a user sees a product with `stock=1`. Seconds before checkout, another user buys the last unit while the Search index is still catching up.

**Checkout must verify live stock and price using conditional writes or transactions against the MongoDB source of truth.** Search serves discovery and browsing only.

## 17. Java Sync Driver: Executing Search Aggregations

The MongoDB Java Sync Driver executes **`$search`** as **`Bson` stages**. Whenever dedicated builders lack a newly released Search operator for your version, construct the stage directly with **`org.bson.Document`**.

### 17.1. Filtered Product Search Example

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;
import java.util.concurrent.TimeUnit;

public final class ProductSearchDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI is required"
            );
        }

        // Tenant ID must be provided by an authenticated backend.
        String tenantId = "store-a";
        String query = "chuột";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "mongo_search_lab"
            );
            MongoCollection<Document> products =
                    database.getCollection("products");

            Document search = new Document(
                    "$search",
                    new Document("index", "products_search")
                            .append(
                                    "compound",
                                    new Document(
                                            "must",
                                            List.of(
                                                    new Document(
                                                            "text",
                                                            new Document("query", query)
                                                                    .append(
                                                                            "path",
                                                                            List.of(
                                                                                    "title",
                                                                                    "description"
                                                                            )
                                                                    )
                                                    )
                                            )
                                    ).append(
                                            "filter",
                                            List.of(
                                                    new Document(
                                                            "equals",
                                                            new Document(
                                                                    "path",
                                                                    "tenantId"
                                                            ).append(
                                                                    "value",
                                                                    tenantId
                                                            )
                                                    ),
                                                    new Document(
                                                            "equals",
                                                            new Document(
                                                                    "path",
                                                                    "active"
                                                            ).append(
                                                                    "value",
                                                                    true
                                                            )
                                                    )
                                            )
                                    )
                            )
            );

            Bson project = new Document(
                    "$project",
                    new Document("title", 1)
                            .append("category", 1)
                            .append("priceCents", 1)
                            .append(
                                    "score",
                                    new Document("$meta", "searchScore")
                            )
            );

            Bson sort = new Document(
                    "$sort",
                    new Document("score", -1)
                            .append("_id", 1)
            );

            List<Bson> pipeline = List.of(
                    search,
                    project,
                    sort,
                    new Document("$limit", 10)
            );

            products.aggregate(pipeline)
                    .maxTime(5, TimeUnit.SECONDS)
                    .forEach(System.out::println);
        }
    }
}
~~~

Explanation:

- **`search`** is a `Bson` stage placed first in the pipeline.
- **`must.text`** specifies text terms to match.
- **`filter.equals`** restricts tenant and `active` status without boosting score.
- **`$project`** retrieves **`searchScore`** via `$meta`.
- **`$sort`** orders descending by score, then `_id`.
- **`$limit`** bounds returned result counts.
- **`maxTime`** enforces a server-side execution deadline; handle timeouts as errors, never as empty result sets.

### 17.2. Fuzzy Search in Java

For fuzzy text, replace the `text` clause with:

~~~java
Document fuzzyText = new Document(
        "text",
        new Document("query", "bluetooh")
                .append(
                        "path",
                        List.of("title", "description", "tags")
                )
                .append(
                        "fuzzy",
                        new Document("maxEdits", 1)
                                .append("prefixLength", 2)
                                .append("maxExpansions", 50)
                )
);
~~~

Then attach **`fuzzyText`** to **`compound.must`** or **`compound.should`** per desired behavior.

### 17.3. Autocomplete in Java

~~~java
Document autocomplete = new Document(
        "autocomplete",
        new Document("query", "Chu")
                .append("path", "titleSuggest")
                .append("tokenOrder", "sequential")
);
~~~

Expose a dedicated suggest endpoint capping query length and returning 5–10 items. Never allow clients to specify arbitrary Search fields/paths or unbounded result limits.

### 17.4. Java Uses Search DSL Without Raw JSON String Interpolation

`Document` builders construct strongly typed BSON trees (numbers, booleans) instead of string concatenation:

~~~java
// Do not do this:
String json = "{ tenantId: '" + userInput + "' }";
~~~

Concatenating raw JSON from user input invites escaping bugs and query injection. Always build `Bson`/`Document` objects with **allowlisted field paths** and typed values.

### 17.5. Validation and Exception Handling

Production services must:

- Validate `q` length, min/max price bounds, and `limit`.
- Inject tenant filters from the security context.
- Handle timeouts and Search index unavailable errors cleanly.
- Avoid logging queries containing PII unless explicitly permitted.
- Emit latency metrics segmented by query type rather than raw user text.
- Return DTOs exposing only allowlisted fields.

## 18. Spring Data MongoDB: Using `AggregationOperation`

Spring Data MongoDB supports **`MongoTemplate.aggregate()`**. For `$search`, an **`AggregationOperation`** returning a raw stage `Document` avoids waiting for version-specific Spring Data DSL builders.

### 18.1. Sample Service

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class CatalogSearchService {

    private final MongoTemplate mongoTemplate;

    public CatalogSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> search(
            String tenantId,
            String query) {

        if (query == null
                || query.isBlank()
                || query.length() > 100) {
            throw new IllegalArgumentException("Invalid query");
        }

        Document text = new Document(
                "text",
                new Document("query", query.trim())
                        .append(
                                "path",
                                List.of("title", "description")
                        )
        );

        Document byTenant = new Document(
                "equals",
                new Document("path", "tenantId")
                        .append("value", tenantId)
        );

        Document activeOnly = new Document(
                "equals",
                new Document("path", "active")
                        .append("value", true)
        );

        Document compound = new Document(
                "must",
                List.of(text)
        ).append(
                "filter",
                List.of(byTenant, activeOnly)
        );

        AggregationOperation searchStage =
                context -> new Document(
                        "$search",
                        new Document("index", "products_search")
                                .append("compound", compound)
                );

        AggregationOperation projectStage =
                context -> new Document(
                        "$project",
                        new Document("title", 1)
                                .append("priceCents", 1)
                                .append(
                                        "score",
                                        new Document("$meta", "searchScore")
                                )
                );

        AggregationOperation sortStage =
                context -> new Document(
                        "$sort",
                        new Document("score", -1)
                                .append("_id", 1)
                );

        AggregationOperation limitStage =
                context -> new Document("$limit", 10);

        Aggregation pipeline = Aggregation.newAggregation(
                searchStage,
                projectStage,
                sortStage,
                limitStage
        );

        return mongoTemplate.aggregate(
                pipeline,
                "products",
                Document.class
        ).getMappedResults();
    }
}
~~~

In real apps, **`tenantId` must come from the security context**, never an arbitrary form parameter. Add DTO mapping, timeouts, and proper exception handling.

### 18.2. Why Must the Search Stage Come First?

~~~text
Valid:
  $search -> $project -> $sort -> $limit

Invalid in a standard pipeline:
  $match -> $search -> $project
~~~

If Spring Data code prepends `$match` or `$project` ahead of the Search stage, MongoDB rejects the pipeline. Ensure **`Aggregation.newAggregation(searchStage, ...)`** keeps `$search` first.

### 18.3. Spring Data Field-Mapping Caveat

When using raw `Document` stages, you write **actual MongoDB field names**. If a Java entity maps **`@Field("product_title")`** while the raw stage queries `"title"`, it will fail to match as expected.

Typed builders resolve mapped field names automatically; raw stages require matching the stored document schema directly.

### 18.4. `ReactiveMongoTemplate`

In reactive stacks, use **`ReactiveMongoTemplate.aggregate(...)`** returning a **`Flux`**; Search execution still runs in MongoDB Search with identical index and latency requirements. Never call the blocking Java Sync Driver on a reactive event loop.

### 18.5. Spring Data Repositories Do Not Auto-Convert Derived Queries to `$search`

A method like:

~~~java
List<Product> findByTitleContainingIgnoreCase(String title);
~~~

generates a standard Spring Data query (typically regex), not **MongoDB Search fuzziness, autocomplete, or ranking**. To use Search features, invoke aggregation stages or explicit framework-supported Search integrations.

## 19. Search and Data Consistency

### 19.1. The Search Index Is Not the Source of Truth

Typical data flow:

~~~text
Application write
       |
       v
MongoDB collection
       |
       v
Search index syncs asynchronously
       |
       v
Search query
~~~

A newly inserted or updated document takes a short interval to appear or reflect changes in the Search index. **This delay is known as near-real-time / index freshness lag.**

Consequently:

- Never assume saving a record makes it searchable within the same millisecond.
- Never check Search scores, prices, or stock as checkout invariants.
- When read-your-writes is needed for a specific document, fetch it by `_id` from the MongoDB source to confirm, while the Search index catches up asynchronously.

### 19.2. Authorization Must Never Rely on Search Index Freshness

Suppose a product is reassigned from tenant A to tenant B or access permissions change. While the Search index lags, stale index entries may still match a tenant A filter.

For sensitive data, enforce **authorization against source-of-truth reads or immediate invalidation mechanisms**. Search filters are vital, yet **insufficient as the sole security barrier** for permission changes requiring immediate effect.

### 19.3. Search After Transactions

A MongoDB transaction commits catalog edits atomically, yet Search index updates do not necessarily commit inside that same transaction. Do not run `$search` inside a transaction expecting a transactional snapshot of Search indexes; verify `$search` restrictions inside transactions for your server version.

### 19.4. Reindexing and Changing Analyzers

Changing Search index analyzers, tokenizers, `minGrams`, or mapped fields generally requires creating/updating the index and rebuilding search data.

Safe rollout:

1. Create **`products_search_v2`**.
2. Wait until ready.
3. Evaluate quality and latency on a test query set.
4. Shift a fraction of traffic to v2.
5. Ramp up gradually while keeping rollback to v1 intact.
6. Drop v1 only after stability is confirmed and no callers depend on it.

Never swap critical production indexes in place without canarying and a safe rollback path.

## 20. Optimizing MongoDB Search Performance

### 20.1. Scope the Index Tightly

With **`dynamic:false`**, index only fields required for Search. If documents have hundreds of fields while APIs search `title`, `description`, `tags` and filter a few attributes, do not index everything.

Overly broad indexes:

- Inflate Search RAM and disk usage.
- Increase sync work on every document update.
- Risk exposing unintended sensitive data inside Search indexes.
- Make analyzer and relevance tuning harder.

Design Search indexes per use case instead of indexing everything.

### 20.2. Autocomplete N-Grams Have Index Cost

Long terms generate many more n-grams than short terms. Using **`nGram`**, tiny `minGrams`, or huge `maxGrams` bloats index size and candidate counts.

When users type word prefixes, **`edgeGram`** is a sensible default. Choose `nGram` only when mid-token matching is genuinely required and benchmarked.

### 20.3. Bound Fuzzy Expansions

Fuzzy queries with **`maxEdits=2`**, **`prefixLength=0`**, and huge **`maxExpansions`** generate noisy matches and high CPU cost.

Recommended strategy:

1. Try exact text/phrase matching first.
2. Enable fuzziness only for sufficiently long queries.
3. Never apply fuzziness to SKUs or tenant IDs requiring exactness.
4. Cap `maxExpansions` and result limits.
5. Monitor p95/p99 latency and zero-hit rates.

### 20.4. Filter Early via `compound.filter`

Filtering tenant, `active`, category, and price **inside `$search`** cuts down the candidate set before scoring and document retrieval. Push hard constraints into **`filter`** whenever supported Search operators exist rather than post-filtering.

Verify index mappings: **`equals` on `token` `tenantId`** and **`range` on `number` `priceCents`** differ completely from querying improperly mapped string fields.

### 20.5. Limit Output and Payloads

- Return only the top N hits.
- Project only UI-required fields.
- Omit `scoreDetails` and `highlights` on endpoints that do not use them.
- Debounce and cancel in-flight autocomplete requests on rapid typing.
- Prefer `searchAfter` over huge `skip` offsets.
- Cache popular queries where authorization and freshness allow.

### 20.6. Reduce Faceting Overhead

Facets require extra computation. Never compute catalog-wide facets when a user merely opens the typeahead dropdown.

Separate two endpoints:

~~~text
GET /search/suggest?q=chu
  -> autocomplete, top 8, no facets.

GET /search/products?q=chuot&category=mouse
  -> text/compound, pagination, facets when needed.
~~~

Request exact `total` counts only when UX requires them; `lowerBound` counts or "has next page" indicators work well when prioritizing low latency.

### 20.7. Analyzing Query Plans

On versions/deployments supporting Search explain, use the **Search Query Analyzer / explain** tools to inspect stages, candidate counts, and execution timings.

Never assume a B-tree `find().explain()` reflects MongoDB Search costs—Search runs its own indexing and scoring engine.

### 20.8. Monitor Index Freshness

When backend updates appear slowly in Search results, inspect:

- Search index build/sync status.
- Write throughput and indexing backlog.
- Search node CPU, memory, and storage.
- Query latency during index updates.
- Errors in the Search service or network layer.

Index freshness is part of your **search SLO** and may warrant UI or admin alerts when lagging.

## 21. Evaluating Result Quality, Not Just Latency

A Search query returning in 20 ms is still a **poor result** if users cannot find the product they want to buy.

### 21.1. Precision and Recall

Suppose query **"chuột Bluetooth"** has 10 truly relevant products.

Search returns top 5, of which 4 are relevant:

~~~text
precision@5 = 4 / 5 = 0.8
recall@5    = 4 / 10 = 0.4
~~~

Fuzziness generally increases recall at the expense of precision. Raising `title` boost improves top ranks yet risks burying helpful matches in `description`.

### 21.2. Ranking Metrics

Common metrics:

| Metric | Meaning |
|---|---|
| **Precision@K** | Fraction of relevant results in top K. |
| **Recall@K** | Fraction of all relevant items retrieved in top K. |
| **MRR** | Mean reciprocal rank of the first relevant result across queries. |
| **NDCG@K** | Evaluates top-K ordering across graded relevance levels. |
| **Zero-result rate** | Share of queries returning zero hits. |
| **CTR / conversion** | User engagement after viewing results (watch for position/UI bias). |
| **Latency p50/p95/p99** | End-to-end latency of search and suggest endpoints. |

Do not optimize blindly for CTR alone, as clicks are heavily skewed by rank position, thumbnails, pricing, discounts, and UI layout.

### 21.3. Build an Evaluation Query Set

A test suite should include:

| Query | Goal |
|---|---|
| `chuột` | Finds mouse products within the tenant. |
| `chuột không dây` | Prioritizes matching titles and phrases. |
| `bluetooh` | Returns Bluetooth items when fuzziness is active. |
| `chuo` | Evaluates unaccented/typo handling per analyzer design. |
| `chu` | Autocomplete returns matching titles. |
| `M100` | Matches the exact model code. |
| `tai nghe không dây` | Does not rank mice above headphones. |
| non-existent keyword | Returns a clean empty state without unbounded scans. |

Include sanitized, anonymized queries from real search logs while keeping PII out of evaluation datasets.

### 21.4. A/B Testing Ranking Changes

Changing a `title` boost from 3 to 8 can:

- Lift title-matching products.
- Demote products with highly relevant descriptions.
- Improve long queries while hurting short ones.

Use **versioned ranking profiles**, offline evaluation, and canary traffic before rolling out globally.

### 21.5. Never Hardcode Exact Score Assertions

Do not write brittle tests such as:

~~~text
P-100 must always have searchScore == 3.147
~~~

Scores shift with corpus changes, analyzers, and engine versions. Assert **filter correctness**, presence of key relevant hits, and **relative ordering** in controlled fixtures.

## 22. Common Mistakes

### 22.1. Using a Legacy Text Index for `$search`

~~~javascript
db.products.createIndex({ title: "text" });
~~~

This **does not create** a MongoDB Search index. To use `$search`, create a Search index on a supported deployment.

### 22.2. Placing `$match` Before `$search`

~~~javascript
[
  { $match: { tenantId: "store-a" } },
  { $search: { /* ... */ } }
]
~~~

In standard pipelines, **`$search` must come first**. Use `compound.filter` to apply predicates early inside the Search engine.

### 22.3. Forgetting Tenant Filters in Autocomplete

Autocomplete can leak product names across tenants just like full search. Enforce tenant scoping on both `search` and `suggest` endpoints.

### 22.4. Mapping `category` as Full-Text `string` and Querying with `equals`

For **whole-value `equals`**, map the field appropriately—usually **`token`**. Full-text `string` analyzers tokenize values differently.

### 22.5. Applying Fuzziness on Short Queries

One edit on a 2–3 character word matches far too broadly. Enforce minimum input length, `prefixLength`, and bounded `maxEdits`, and monitor false positives.

### 22.6. Treating Autocomplete as Final Full-Text Search

Autocomplete optimizes prefix matching while typing; it may not rank full-word or phrase queries optimally. Combine `text`/`phrase` with boosts when full queries are submitted.

### 22.7. Treating `searchScore` as Probability

A score of 7.5 does not mean "75% match." Use scores strictly for relative ordering unless you build an explicit calibration model.

### 22.8. Omitting `minimumShouldMatch`

A `compound` mixing `should` and `filter` can return documents that satisfy only `filter` without matching any keyword if `should` is optional. Set **`minimumShouldMatch:1`** when at least one `should` clause is required.

### 22.9. Simulating Fuzziness with Regex

Regex does not compute edit distance or BM25. It is no substitute for a fuzzy-capable Search index.

### 22.10. Indexing Every Field into Search

Indexing sensitive fields, `internalNotes`, or credentials raises breach risk and cost. Use explicit mappings following least-privilege principles.

### 22.11. Treating Stale Search Results as Authoritative

Search indexes update asynchronously; always re-verify live price and inventory against the MongoDB source of truth at checkout.

### 22.12. Facet Counts Out of Scope with Results

Filtering results to tenant A while counting facets across tenant B leaks statistics and misleads users. Enforce identical authorized scopes across both Search and `$searchMeta` queries.

### 22.13. Deep Pagination with Large `$skip`

Skipping hundreds of thousands of rows inflates latency and compute. Use `searchAfter` and deterministic sorts where supported by your API and driver.

### 22.14. Failing to Test Analyzer Changes

Tuning an analyzer for Vietnamese alters tokenization and relevance across all queries. Validate with a test corpus, index versioning, and staged rollouts.

### 22.15. Assuming Search Indexes Have Transactional Consistency

Search indexes exhibit sync lag. Never use a Search query to verify read-your-writes or prove an immediate permission revocation.

### 22.16. Data Leakage Through Highlights

Highlights can surface snippets from indexed sensitive fields. Never index or highlight restricted fields, and always escape output in the frontend.

### 22.17. Failing to Validate Filter Values and Limits

Negative prices, `min > max`, huge limits, or invalid categories cause errors or excessive load. Validate types and bounds before building Search DSLs.

## 23. Production Search Deployment Checklist

### 23.1. Data and Indexes

1. Separate full-text search fields from exact-filter fields.
2. Design analyzers for real target languages.
3. Map `string`, `token`, `autocomplete`, `number`, and `date` deliberately.
4. Disable or restrict dynamic indexing and exclude sensitive fields.
5. Keep tenant, category, and price data cleanly normalized.
6. Version Search indexes and maintain a rollout/rebuild plan.

### 23.2. Queries and Ranking

1. Start with simple `text`/`phrase` queries.
2. Put hard constraints in `compound.filter`.
3. Enable fuzziness only above minimum lengths where false positives are acceptable.
4. Separate `suggest` autocomplete from full `search` results.
5. Apply intentional boosts across `title`, `description`, and `phrase`.
6. Use `scoreDetails`/explain during tuning, not for all live traffic.
7. Project minimal fields and cap result counts.
8. Plan counts, facets, and pagination strategies up front.

### 23.3. Security and Correctness

1. Never accept client-chosen `tenantId` in security filters.
2. Never accept raw aggregation or Search DSL JSON from clients.
3. Never treat Search indexes as authoritative for checkout or permissions.
4. Escape highlighted output.
5. Avoid logging raw user PII/search strings without an approved policy.
6. Apply rate limiting, debouncing, and query timeouts.
7. Never let broad fallback searches bypass tenant/visibility filters.

### 23.4. Monitoring and Evaluation

1. Track p50/p95/p99 query latency per endpoint.
2. Monitor Search index freshness and build status.
3. Track throughput and error/timeout rates.
4. Monitor zero-result rates and empty suggestion rates.
5. Measure `precision@K`/`NDCG` on a golden query set.
6. Track index size and Search resource utilization.
7. A/B test ranking changes before full rollout.

## 24. Practice Exercises

### Exercise 1 — Compare Exact, Regex, and Search

For title **"Chuột không dây M100"**, explain the differences among:

~~~javascript
db.products.find({ title: "Chuột không dây M100" });

db.products.find({ title: /^Chuột/i });

db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột",
        path: "title"
      }
    }
  }
]);
~~~

Which approach works best when users make typos?

### Exercise 2 — Legacy Text Index

Create a text index on `title`/`description` with weights `title=10, description=2`. Run `$text` and project `textScore`. Why cannot this index serve as a Search autocomplete index?

### Exercise 3 — Search Index Mappings

From the `products` schema, pick mappings for:

~~~text
title
titleSuggest
tenantId
category
priceCents
active
publishedAt
~~~

Explain why `tenantId` should not use a full-text analyzer.

### Exercise 4 — Single-Field Search

Write a `$search.text` query matching **"Bluetooth"** only in `description`. Project `title`, `description`, and `searchScore`, sorted descending.

### Exercise 5 — Multi-Field Search

Extend Exercise 4 to search `title`, `description`, and `tags` together. Why can a document containing `Bluetooth` only in `tags` still match?

### Exercise 6 — `phrase` vs. `text`

Write two queries:

1. `text` query **"không dây"** on `title`.
2. `phrase` query **"không dây"**, `slop=0`.

Describe the difference in token ordering and adjacency requirements.

### Exercise 7 — `compound.must`

Find documents containing both **"chuột"** and **"bluetooth"** across `title`/`description`/`tags`. Write two `must` clauses rather than a single `text` query array.

### Exercise 8 — Tenant and Active Filters

Find mice for **`store-a`** while excluding `store-b`'s `P-900` and inactive `P-105`. Write `compound.filter` and explain why filters contribute zero score.

### Exercise 9 — Range Filters

Filter `priceCents` between **200000 and 500000**, and `stock > 0`. Explain why both fields require `number` mappings.

### Exercise 10 — `mustNot`

Search **"không dây"** while excluding category **`headphone`**, scoped to `store-a`. Write `compound.mustNot` and `filter`.

### Exercise 11 — `minimumShouldMatch`

Design a `compound` with two `should` clauses (matching `title` and `description`) plus filter `active=true`. Why is `minimumShouldMatch:1` necessary?

### Exercise 12 — Fuzzy Typos

User enters **"bluetooh"**. Write `text.fuzzy` with `maxEdits=1, prefixLength=2, maxExpansions=50`. List at least two risks of setting `maxEdits` too high.

### Exercise 13 — Boosting Exact Matches

Write a `compound.should` containing:

- Standard `text` match, `boost=5`.
- Fuzzy `text` match (`maxEdits=1`), `boost=1`.

Explain why exact spelling receives an advantage.

### Exercise 14 — Accented and Unaccented Vietnamese

Using queries **"chuột"**, **"chuot"**, **"điện thoại"**, and **"dien thoai"**, design a test corpus to evaluate analyzers and normalization. Why is merely turning on fuzziness insufficient?

### Exercise 15 — Autocomplete While Typing

Write an `autocomplete` query on `titleSuggest` for **"Chu"** with `tokenOrder:"sequential"`. Limit to 8 hits and filter by `store-a` and `active=true`.

### Exercise 16 — `edgeGram` vs. `nGram`

Contrast `edgeGram` and `nGram`. If users only type word beginnings, which is the leaner starting choice?

### Exercise 17 — Fuzzy Autocomplete

Write an `autocomplete` query for **"bluetoh"** with `maxEdits=1`. Why should you enforce minimum query length and debouncing?

### Exercise 18 — Ranking `title` vs. `description`

Write `compound.should` with `title` `boost=5`, `description` `boost=1`, and `minimumShouldMatch=1`. Why can `boost` never replace a tenant filter?

### Exercise 19 — Boosting Phrase Matches

Search **"chuột không dây"**, boosting `phrase` on `title` (`slop=0`) above `text` on `description`. Describe when an exact phrase title match rises to the top.

### Exercise 20 — Displaying `searchScore`

Add `$project` with `score: {$meta:"searchScore"}` and descending `$sort`. Explain why `score=8` does not mean an 80% probability of correctness.

### Exercise 21 — Highlighting

Search **"bluetooth"**, requesting highlights on `title` and `description`. Describe how to render highlight segments safely against XSS.

### Exercise 22 — Counts and Facets

Write a `$searchMeta` query counting Bluetooth hits in `store-a` along with `category` and `priceBands` facets. Why must both result and metadata queries enforce the same tenant scope?

### Exercise 23 — Disjunctive Faceting

A user selects `category=mouse`. Design the `category` facet query so the UI still shows counts for other categories. How must the `category` filter be handled during facet computation?

### Exercise 24 — Pagination

Write `$skip`/`$limit` for page 2. Then describe how to use `searchSequenceToken`/`searchAfter` for deep pages and why Change Stream resume tokens cannot substitute for it.

### Exercise 25 — API Security

A client sends:

~~~json
{
  "query": "chuột",
  "tenantId": "store-b",
  "limit": 1000000
}
~~~

The backend authenticated the user under `store-a`. How must the API handle `tenantId` and `limit`? Why must clients never pass raw `$search` DSL?

### Exercise 26 — Checkout Consistency

Search shows `stock=1`, and two users check out concurrently. Why can you not decrement stock based solely on Search results? Propose conditional writes or transactions against the source collection.

### Exercise 27 — Java Sync Driver

Write a Java aggregation using `org.bson.Document` with `$search` first, `compound.must` `text`, `compound.filter` for `tenantId` and `active`, `searchScore` projection, sort, and limit.

### Exercise 28 — Spring Data

Write `MongoTemplate.aggregate()` using `AggregationOperation` to supply a raw `$search` `Document`. Explain why placing `Aggregation.match()` before the Search stage fails.

### Exercise 29 — Relevance Evaluation

Create 10 labeled queries, compute `precision@5`, and measure p95 latency. If fuzziness increases hit coverage while lowering `precision@5`, how should the team decide?

### Exercise 30 — Index Rollout

You want to change the analyzer to support unaccented Vietnamese. Describe a zero-breakage plan covering v2 index creation, building, offline relevance tests, canary traffic, and rollback.

## 25. Review Questions

1. How does a MongoDB text index differ from a MongoDB Search index?
2. Why cannot `$search` follow `$match` in a standard pipeline?
3. In what ways does a search analyzer affect query results?
4. When should you map a field as `string` vs. `token`?
5. Why does autocomplete require a dedicated `autocomplete` mapping?
6. How does `text` differ from `phrase`?
7. How do `must` and `should` differ?
8. When is `minimumShouldMatch` mandatory for business queries?
9. Why does `compound.filter` not add to relevance scores?
10. Why should tenant filtering happen inside the Search query itself?
11. What does fuzzy edit distance solve, and what does it not solve?
12. What do `maxEdits`, `prefixLength`, and `maxExpansions` control?
13. Why does fuzziness on short words easily trigger false positives?
14. How does autocomplete `tokenOrder:"sequential"` differ from `"any"`?
15. How do `edgeGram`, `rightEdgeGram`, and `nGram` differ?
16. Why is debouncing a UX/backend concern rather than a Search index setting?
17. Is `searchScore` a click probability or correctness percentage?
18. How do `boost` and `constant` scoring differ?
19. Why are title matches typically boosted above description matches?
20. What metadata does `highlight` return, and how must the frontend protect against XSS?
21. How does `$searchMeta` fit count and facet queries?
22. How does an active category filter affect category facet counts?
23. Why can a huge `$skip` introduce high latency?
24. How does a Search pagination token differ from a Change Stream resume token?
25. When the Search index updates mid-session, how can pagination shift?
26. Does a Search index always reflect newly committed writes immediately?
27. Why must price and stock at checkout be confirmed against the source of truth?
28. How does the Java Driver construct a `$search` stage with `org.bson.Document`?
29. Do Spring Data derived queries automatically use MongoDB Search fuzziness?
30. Which metrics evaluate both query latency and relevance quality?

## 26. Summary

Building effective text search in MongoDB requires treating **querying, filtering, fuzziness, autocomplete, and ranking** as parts of one cohesive user experience:

~~~text
User query
   |
   +-- Typing a prefix?
   |       |
   |       v
   |   autocomplete + prefix index
   |
   +-- Entered full keywords?
           |
           v
       text / phrase
           |
           +-- Need typo tolerance?
           |       |
           |       v
           |     fuzzy
           |
           v
       compound.filter
         tenant, active, category, price, stock
           |
           v
       relevance score + boosts
           |
           v
       ranking / pagination
           |
           v
       highlights, facets, result DTO
           |
           v
       UI and downstream actions
~~~

Core principles:

1. **MongoDB Search `$search`/`$searchMeta` differs from legacy `$text`**; it requires a Search index and Search-enabled deployment.
2. **Mappings must fit query shapes:** `string` for analyzed text, `token` for exact string filters, `autocomplete` for typeahead, and `number`/`date` for ranges.
3. **`compound.filter` holds hard constraints** like tenant, `active`, and price; never simulate authorization with score boosts.
4. **Fuzziness boosts recall but risks false positives:** bound `maxEdits`, `prefixLength`, `maxExpansions`, and minimum query length.
5. **Autocomplete targets typeahead prefixes:** keep payloads small, debounce client requests, and enforce identical tenant scoping.
6. **`searchScore` ranks relatively**, not as normalized probability; validate boosts against real queries.
7. **Highlights, facets, counts, and pagination** require aligned metadata, mappings, and query filters.
8. **Search indexes sync asynchronously**, never replacing the source of truth for final authorization or checkout.
9. **Java Sync Driver and Spring Data** send Search stages via `Bson`/`Document` with `$search` first in the pipeline.
10. **Search quality** is measured by precision/recall, NDCG, zero-hit rate, and business outcomes—not latency alone.

### Official References

- [MongoDB Search — Overview](https://www.mongodb.com/docs/atlas/atlas-search/) — full-text Search capabilities and indexes.
- [MongoDB Search Index Definitions](https://www.mongodb.com/docs/atlas/atlas-search/define-field-mappings/) — `string`, `token`, `autocomplete`, numbers, and mappings.
- [$search Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/) — `$search` syntax and options.
- [$searchMeta Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/searchMeta/) — count and facet metadata.
- [text Operator](https://www.mongodb.com/docs/atlas/atlas-search/text/) — full-text matching and fuzziness.
- [phrase Operator](https://www.mongodb.com/docs/atlas/atlas-search/phrase/) — phrase matching and `slop`.
- [autocomplete Operator](https://www.mongodb.com/docs/atlas/atlas-search/autocomplete/) — prefix suggestions and typo tolerance.
- [compound Operator](https://www.mongodb.com/docs/atlas/atlas-search/compound/) — `must`, `should`, `filter`, and `mustNot`.
- [equals Operator](https://www.mongodb.com/docs/atlas/atlas-search/equals/) — exact field matching.
- [range Operator](https://www.mongodb.com/docs/atlas/atlas-search/range/) — numeric and date range filters.
- [Score Results](https://www.mongodb.com/docs/atlas/atlas-search/scoring/) — `searchScore` and tuning options.
- [Highlight Search Terms](https://www.mongodb.com/docs/atlas/atlas-search/highlighting/) — `searchHighlights`.
- [Facet Search Results](https://www.mongodb.com/docs/atlas/atlas-search/facet/) — facets and counts.
- [Paginate Search Results](https://www.mongodb.com/docs/atlas/atlas-search/paginate-results/) — `searchSequenceToken` and `searchAfter`.
- [MongoDB $text Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/) — legacy text indexes.
- [MongoDB Java Sync Driver Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — aggregating with BSON stages.
- [Spring Data MongoDB Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — `MongoTemplate` and `AggregationOperation`.

When designing a Search API, start with **"What is the user trying to find, and which results truly belong?"** Only then choose analyzers, full-text clauses, mandatory filters, fuzziness/autocomplete, and ranking signals. A strong Search index does more than return fast hits—it **returns only authorized data, tolerates typos gracefully, ranks sensibly, and operates safely as your catalog evolves**.







