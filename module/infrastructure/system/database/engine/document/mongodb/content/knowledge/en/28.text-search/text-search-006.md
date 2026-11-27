# Search Indexes, Analyzers, Tokenizers, and Text Normalization in MongoDB

## 1. Why Does Text Search Require Deliberate Design?

In systems managing products, real estate, articles, documents, or support tickets, users typically type a few words instead of knowing an exact document key:

- Search `"máy lọc nước"` across product names and descriptions.
- Type `"may loc"` and still expect `"Máy lọc"` when the app supports accent-insensitive search.
- Type `"wireles"` and still find `"wireless"` via fuzzy matching.
- Type a few leading characters to see autocomplete suggestions.
- Search for the phrase `"data engineering"` in exact word order.
- Display only results belonging to the signed-in user's `tenantId` that are in stock and active.
- Preserve SKU `"AB-123-X"` for exact lookup instead of splitting it like prose.

A query such as:

```javascript
db.products.find({
  title: /máy lọc/i
});
```

works for simple scenarios, but does not natively provide word tokenization, diacritic handling, relevance scoring, fuzzy matching, multi-field search, or the full ranking pipeline of a search system.

MongoDB has two distinct families of text-search mechanisms:

1. **Legacy text index:** created with `createIndex({ field: "text" })` and queried via `$text`. This is MongoDB's traditional built-in text search.
2. **MongoDB Search** (previously commonly called **Atlas Search**), using a dedicated **Search index**, analyzers, and the `$search`/`$searchMeta` aggregation stages. Its search engine runs **Apache Lucene** via the `mongot` process.

This lesson focuses on **MongoDB Search indexes** and **text analysis** (analyzers, tokenizers, filters, and normalization). Legacy `$text` is contrasted separately so the two APIs are never conflated.

> **Foundational mindset:** Search does not compare raw strings naively; it transforms strings into searchable **tokens**. The analyzer determines how tokens are produced at index time and at query time.

---

## 2. Architecture: Data Documents and Search Indexes Are Separate Layers

A business document:

```javascript
{
  _id: "P100",
  tenantId: "T1",
  title: "Máy lọc nước mini",
  description: "Thiết bị lọc nước dùng trong gia đình.",
  sku: "MLN-100",
  brand: "AquaHome",
  status: "ACTIVE",
  priceMinor: 2490000
}
```

These fields live inside a `mongod` collection. A Search index is neither an extra field stuffed into the document nor a standard B-tree index.

Conceptual diagram:

```text
Application
     |
     +-- insert/update/delete ----------> mongod
     |                                      |
     |                                      | sync index
     |                                      v
     |                                   mongot
     |                              (Search/Lucene)
     |                                      |
     +-- aggregate([{$search: ...}]) -------+
             |
             v
     Documents + relevance scores
```

- `mongod` holds the source-of-truth data.
- `mongot` maintains search indexes synced from the source and handles search execution.
- Clients send aggregation queries to MongoDB through the driver; clients **do not connect directly to `mongot`**.
- Index data can update **asynchronously** relative to collection writes. Therefore, a search immediately after a write may not yet reflect every committed change.
- Search indexes serve lexical keyword search; for vector/semantic search there is **MongoDB Vector Search** (`$vectorSearch`), which is outside the primary scope of this lesson.

### 2.1. Deployment Requirements in 2026

MongoDB Search is no longer exclusive to MongoDB Atlas: as of mid-2026, MongoDB Search and Vector Search are also **generally available for self-managed Community Edition and Enterprise Advanced** under their respective deployment requirements.

| Environment | How Is Search Deployed? |
| --- | --- |
| MongoDB Atlas supporting Search | Atlas manages `mongot` and Search indexes per cluster configuration. |
| Supported self-managed MongoDB | Operations teams deploy, configure, and run `mongot` separately. |
| Standard `mongod` without Search integration | Having MongoDB server/driver alone does not guarantee `$search` availability. |
| Legacy `$text` index | Does not require the Search architecture, but offers fewer analysis and ranking features. |

**Important:** You cannot open an arbitrary standalone `mongod`, run `createSearchIndex()`, and expect full Search automatically without deploying `mongot` and meeting version/topology requirements. Always verify deployment options, compatibility, and management permissions.

Sources: [MongoDB Search deployment options](https://www.mongodb.com/docs/search/deployment/deployment-options/), [Self-Managed MongoDB Search](https://www.mongodb.com/docs/search/self-managed/current/).

---

## 3. Search Indexes Differ from B-Tree Indexes and Legacy Text Indexes

| Criterion | B-Tree Index | Legacy Text Index | MongoDB Search Index |
| --- | --- | --- | --- |
| Created by | `createIndex({field: 1})` | `createIndex({field:"text"})` | `createSearchIndex(...)` or Search tooling |
| Queried by | Standard `find`, `aggregate` | `$text` | `$search`, `$searchMeta` |
| Custom analyzer config | Not via Search analyzers | Language/text options, more limited | Full built-in and custom analyzers |
| Tokenizers / char / token filters | No | Not customizable as Search pipelines | Yes |
| Phrase, fuzzy, autocomplete | Not a B-tree goal | Limited | Dedicated operators |
| Scoring | No default relevance score | `textScore` | `searchScore` with rich scoring options |
| Exact equality and sorting | Ideal | Not a priority | `token` type and normalizers cover certain cases |
| Index cost | Depends on index keys | Server-side text index | Additional Search storage, indexing, `mongot` |
| Post-write sync | Part of MongoDB write/index path | Part of server mechanics | Search can exhibit indexing lag |

**Never mix up the syntax:**

```javascript
// Legacy text index:
db.products.createIndex({ title: "text" });

// Legacy text search:
db.products.find({
  $text: { $search: "water filter" }
});

// MongoDB Search index is a separate mechanism:
// db.products.createSearchIndex(...)

// MongoDB Search query:
db.products.aggregate([
  {
    $search: {
      index: "catalog_text_v1",
      text: {
        query: "water filter",
        path: "title"
      }
    }
  }
]);
```

`$text` and `$search` differ in more than name: they require **different index types** and follow non-identical analysis and ranking semantics.

---

## 4. Test Dataset Used Throughout This Lesson

To keep examples self-contained, create a new collection `searchLesson305` in a test database where MongoDB Search is supported. Never run these scripts against a production collection holding live data.

```javascript
const catalog = db.getSiblingDB("search_lab");
const products = catalog.getCollection("searchLesson305");

products.insertMany([
  {
    _id: "P001",
    tenantId: "T1",
    title: "Máy lọc nước mini",
    description: "Máy lọc nước gia đình, thiết kế nhỏ gọn",
    brand: "AquaHome",
    sku: "MLN-100",
    status: "ACTIVE",
    category: "home"
  },
  {
    _id: "P002",
    tenantId: "T1",
    title: "Máy lọc không khí",
    description: "Thiết bị lọc không khí trong phòng ngủ",
    brand: "AirPro",
    sku: "AIR-200",
    status: "ACTIVE",
    category: "home"
  },
  {
    _id: "P003",
    tenantId: "T1",
    title: "Bộ lọc nước thay thế",
    description: "Lõi lọc cho thiết bị gia đình",
    brand: "AquaHome",
    sku: "CORE-03",
    status: "ACTIVE",
    category: "parts"
  },
  {
    _id: "P004",
    tenantId: "T2",
    title: "Wireless Mouse",
    description: "Comfortable computer mouse with wireless connection",
    brand: "TechWorks",
    sku: "MOUSE-04",
    status: "ACTIVE",
    category: "electronics"
  },
  {
    _id: "P005",
    tenantId: "T1",
    title: "Water Filter",
    description: "Compact household water filtration system",
    brand: "AquaHome",
    sku: "WF-500",
    status: "ACTIVE",
    category: "home"
  },
  {
    _id: "P006",
    tenantId: "T1",
    title: "Data Engineering Handbook",
    description: "Learn data pipelines and modern analytics",
    brand: "BookLab",
    sku: "BOOK-06",
    status: "INACTIVE",
    category: "books"
  },
  {
    _id: "P007",
    tenantId: "T2",
    title: "Nước rửa tay",
    description: "Dung dịch chăm sóc gia đình",
    brand: "CareLife",
    sku: "CARE-07",
    status: "ACTIVE",
    category: "personal-care"
  }
]);
```

This sample dataset illustrates index building and pipeline structure—**not a promise of identical exact results across every version**. Text matching depends on analyzers, index definitions, and whether Search indexing has caught up.

### 4.1. Why Multiple Field Types Are Needed

- `title` and `description` are **natural language**, requiring tokenization.
- `sku` is an **identifier**, usually needing hyphens preserved and exact matching.
- `brand` is a **filter/facet attribute**, usually best treated as a single intact token.
- `tenantId` is an **access-control boundary** that must never depend solely on search score.
- `status` and `category` are filtering metadata.
- Vietnamese has diacritics, unaccented inputs, and **multi-syllable compound words**, requiring deliberate analyzer choices.

---

## 5. Creating Your First Search Index: Dynamic Mapping

A quick setup for experimentation:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_dynamic_v1",
    {
      mappings: {
        dynamic: true
      }
    }
  );
```

`dynamic: true` instructs MongoDB Search to index fields of supported data types automatically via dynamic mapping, enabling fast prototyping without listing every path.

### 5.1. Pros and Cons

**Pros:**

- Fast setup on sample data.
- Lets you search string fields without declaring each one explicitly.
- Useful for exploring query patterns during prototyping.

**Cons:**

- May index fields with no search use case, increasing storage and indexing costs.
- Under dynamic mapping, string fields default to `string`, not `token` for exact equality, faceting, or sorting.
- The default general analyzer may be unsuitable for `sku`, `brand`, or specific languages.
- Sensitive fields can inadvertently enter the Search index without a strict schema/mapping policy.

For production, **static/explicit mapping** is normally preferred to control field types and analyzers precisely.

### 5.2. Search Indexes Are Not Ready Immediately

`createSearchIndex()` triggers an **asynchronous build**. Command completion does not guarantee the index can be queried immediately.

Check status:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $listSearchIndexes: {
        name: "catalog_dynamic_v1"
      }
    }
  ]);
```

Status may appear as `PENDING`, `BUILDING`, `READY`, `FAILED`, or `STALE` depending on state. **Treat only `READY` as confirmation that a new index is fully usable**; while rebuilding an existing index, MongoDB can continue serving queries using the prior definition.

Never put index-creation polling inside user-facing request paths. Index management belongs to deployment and migration workflows.

---

## 6. Static Mapping: Which Field Is Indexed as Which Type?

An intentional index definition:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_text_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "string",
            analyzer: "lucene.standard"
          },
          description: {
            type: "string",
            analyzer: "lucene.standard"
          },
          brand: {
            type: "token",
            normalizer: "lowercase"
          },
          sku: {
            type: "token",
            normalizer: "none"
          },
          tenantId: {
            type: "token"
          },
          status: {
            type: "token"
          },
          category: {
            type: "token"
          }
        }
      }
    }
  );
```

Selected fields:

| Field | Search Field Type | Goal |
| --- | --- | --- |
| `title` | `string` | Full-text retrieval and ranking |
| `description` | `string` | Full-text search in descriptions |
| `brand` | `token` | Equality, facets, and sorting on normalized string |
| `sku` | `token` | Exact matching of intact product codes |
| `tenantId` | `token` | Exact tenant filtering |
| `status` | `token` | Status filtering |
| `category` | `token` | Category filtering |

**Key concepts:**

- **`string`**: uses an analyzer to produce one or more searchable terms from text.
- **`token`**: represents the entire string as **one intact token**; accepts a `normalizer` such as `none` or `lowercase`.
- Do not replace every `string` with `token` and expect `text` or `phrase` operators to work like full-text search.

### 6.1. Dynamic Mapping Does Not Default to True

If `mappings.dynamic` is omitted, it defaults to **false**. Thus:

```javascript
{
  mappings: {
    fields: {
      title: { type: "string" }
    }
  }
}
```

indexes only the explicitly declared `title` field; unlisted fields do not enter Search automatically.

---

## 7. Your First Query with $search

Before querying, confirm `catalog_text_v1` is `READY`.

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        text: {
          query: "water filter",
          path: ["title", "description"]
        }
      }
    },
    { $limit: 10 },
    {
      $project: {
        _id: 1,
        title: 1,
        brand: 1,
        score: { $meta: "searchScore" }
      }
    }
  ]);
```

Components:

- `$search`: aggregation stage invoking MongoDB Search; generally must be the **first stage** of its pipeline.
- `index`: Search index name, not a B-tree index.
- `text.query`: user search text.
- `text.path`: string field or array of `string`-mapped fields.
- `$limit`: caps returned results.
- `$meta: "searchScore"`: relevance score computed by Search, not merely a raw word-match count.

### 7.1. Search Is Not Exact Substring Matching by Default

If the query is `"filter"`, the analyzer produces token `filter` to match indexed document tokens. That does not mean substrings of `"filtering"` or `"filtration"` match automatically; results depend on the analyzer, stemmer, fuzziness, and operator.

### 7.2. Search Indexes Can Be "Stale" After Writes

If you insert a document and search immediately:

```javascript
db.searchLesson305.insertOne({
  _id: "P008",
  title: "New Water Filter"
});
```

a `$search` query run right away may not return `P008` yet. That is **indexing lag**, not a transaction failure or lost write. Flows requiring **immediate read-your-writes** must pair Search with direct key lookups instead of relying solely on Search.

---

## 8. What Is an Analyzer?

An **analyzer** is the pipeline that converts a string into **terms/tokens** for indexing or querying.

Custom analyzer flow:

```text
Original text
   |
   v
Character filters (0 or more)
   |
   v
Tokenizer (1)
   |
   v
Token filters (0 or more; in order)
   |
   v
Tokens used for indexing or querying
```

Visual example:

```text
Input:
  "MÁY-LỌC NƯỚC!"

Char normalization:
  Unicode normalization when configured

Tokenizer:
  "MÁY" | "LỌC" | "NƯỚC"

Lowercase:
  "máy" | "lọc" | "nước"

Accent folding (if configured):
  "may" | "loc" | "nuoc"

Index:
  terms mapped to the document
```

This is an **illustrative diagram**, not a claim that every analyzer emits these exact three tokens. Hyphen splitting and diacritic folding depend on the actual tokenizer and filters chosen.

### 8.1. Why Does This Matter?

Two documents may differ in raw strings yet emit identical tokens:

```text
"Wireless Mouse"
"wireless mouse"
```

When the analyzer lowercases, both produce `wireless` and `mouse`.

Conversely, if the tokenizer keeps the whole string intact:

```text
"Wireless Mouse" -> "Wireless Mouse"
```

then querying `"mouse"` cannot match just because `"mouse"` sits inside the token, unlike word-splitting full-text analysis.

**The analyzer defines "what counts as a searchable word" for both indexing and querying.**

---

## 9. Index Analyzer and Search Analyzer

MongoDB Search separates two configuration points:

- **`analyzer`**: used when **indexing** document text.
- **`searchAnalyzer`**: used when **analyzing query text** before matching against indexed terms.

Example:

```text
Document "Máy Lọc Nước"   --index analyzer--> ["may", "loc", "nuoc"]
Query    "may loc"        --search analyzer-> ["may", "loc"]

=> terms can align and match.
```

If the two analyzers are incompatible:

```text
Index analyzer keyword:
  "wireless mouse" -> ["wireless mouse"]

Search analyzer standard:
  "wireless mouse" -> ["wireless", "mouse"]

=> no shared "wireless mouse" token to match as expected.
```

### 9.1. Configuration Inheritance Order

For a `string` field, when omitted directly:

- Field `analyzer` typically falls back to the index-level `analyzer`, and ultimately to `lucene.standard`.
- Field `searchAnalyzer` prefers the field's declared `analyzer`, then index-level `searchAnalyzer` and index-level `analyzer` per Search inheritance rules, and finally `lucene.standard`.

To avoid surprises in production, **explicitly declare** important analyzers on fields or the index definition.

### 9.2. Why Intentionally Use Two Different Analyzers?

Asymmetric strategies exist:

- Index using n-grams for prefix support while querying with a tokenizer that emits fewer tokens.
- Index both original and stemmed forms while querying with lighter rules.
- Index an identifier like `"AB-123"` split by structure while normalizing user query input separately.

Not every analyzer pair is valid or behaves intuitively. **Always inspect output tokens on both sides.** For standard full-text search, using the same analyzer on both sides is simpler and more predictable.

---

## 10. Key Built-In Analyzers

Common built-in analyzers in MongoDB Search:

| Analyzer | Conceptual Behavior | Best Fit |
| --- | --- | --- |
| `lucene.standard` | Standard Unicode word-boundary analysis; default analyzer | General-purpose full-text |
| `lucene.simple` | Splits on non-letter characters, lowercases | Simple text |
| `lucene.whitespace` | Splits on whitespace, **preserves case** | Pre-normalized whitespace-delimited text |
| `lucene.keyword` | Treats the entire string as **one token**, preserves case | Strings that must remain intact as a single unit |
| `lucene.english` | English-specific analysis including stop words and stemming | English full-text when appropriate |
| Other `lucene.<language>` | Language-specific stop words, word breaking, and stemming | Data in supported languages |

### 10.1. Not Every Analyzer Lowercases

MongoDB documentation confirms:

- `lucene.simple` lowercases.
- `lucene.whitespace` **does not lowercase**.
- `lucene.keyword` **does not lowercase**.

If SKU `"Ab-123"` must be matched by `"ab-123"`, the keyword analyzer alone will not make it case-insensitive. Use an appropriate normalizer or custom analyzer.

### 10.2. Never Pick a Language Analyzer Based on the App's Country

An app in Vietnam may mix Vietnamese and English product names, technical codes, addresses, and brand names. Applying `lucene.english` across all fields applies English stop words and stemming in ways that distort non-English tokens.

**As of 2026 reference docs, MongoDB Search's built-in language analyzers do not include `lucene.vietnamese`.** Never invent that analyzer name. Vietnamese requires deliberate index/analyzer modeling and dedicated testing; strategies are detailed below.

Source: [Language analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/language/).

---

## 11. What Is a Tokenizer?

A **tokenizer** is the mandatory component of a custom analyzer: it receives text after character filters and determines **token boundaries**.

Example:

```text
Input: "USB-C Adapter 65W"
```

Different strategies yield different tokens:

| Tokenizer | Behavior |
| --- | --- |
| `standard` | Splits by Unicode word-break rules, not just spaces |
| `whitespace` | Splits strictly on whitespace |
| `keyword` | Keeps the entire input as a single token |
| `nGram` | Emits substrings of configured length n |
| `edgeGram` | Emits edge/prefix substrings, useful for typeahead |
| Regex-based tokenizers | Splits or captures groups per regex pattern |

Note: tokenizer names inside a **custom analyzer** are `standard`, `whitespace`, `keyword` (without the `lucene.` prefix), whereas **built-in analyzer names** are `lucene.standard`, `lucene.keyword`, etc.

### 11.1. Word Tokenization and Vietnamese

Vietnamese places spaces between **syllables**, while semantic words often span multiple syllables:

```text
"Bất động sản"

By whitespace:
  ["Bất", "động", "sản"]

With a dedicated Vietnamese word segmenter:
  may treat ["bất_động_sản"] as a single unit
```

Never claim `standard` or `whitespace` tokenizers understand Vietnamese compound words automatically. Exact phrase matching, semantic ranking, and homonym disambiguation require explicit linguistic strategies.

### 11.2. Tokenization Affects Phrase Queries

When a field indexes tokens with positions:

```text
"The quick brown fox"
  the (position 0)
  quick (1)
  brown (2)
  fox (3)
```

`phrase` uses positional data to verify token order and proximity. If an index stores only document frequencies without positions, positional phrase queries become unavailable.

---

## 12. Character Filters: Processing Before Tokenization

**Character filters** modify raw text **before the tokenizer runs**. They are suited for stripping HTML, replacing delimiters, or character-level normalization.

Main types:

- `htmlStrip`: strips HTML markup appropriately.
- `mapping`: replaces substrings/characters based on declared mappings.

Example:

```html
<h2>Wireless Mouse</h2><p>USB receiver included</p>
```

Tokenizing raw HTML directly pollutes results with tag names. An `htmlStrip` character filter extracts readable text before the tokenizer runs.

Custom analyzer configuration:

```javascript
{
  name: "htmlText",
  charFilters: [
    { type: "htmlStrip" }
  ],
  tokenizer: {
    type: "standard"
  },
  tokenFilters: [
    { type: "lowercase" }
  ]
}
```

### 12.1. Processing Order Matters

```text
HTML source
  -> htmlStrip
  -> standard tokenizer
  -> lowercase
  -> index terms
```

Never put `htmlStrip` inside `tokenFilters`—it is not a token filter. Never reorder stages arbitrarily and expect identical output.

### 12.2. Do Not Treat htmlStrip as an XSS Security Sanitizer

Character filters serve **search text analysis**, not XSS protection for rendered UI content. Whenever rendering user-authored HTML, escape and sanitize at the output layer per security standards.

---

## 13. Token Filters: Transforming Tokens After Tokenization

**Token filters** execute **after the tokenizer**, in exact declared order.

Key capabilities:

| Filter | Purpose |
| --- | --- |
| `lowercase` | Converts tokens to lowercase |
| `asciiFolding` | Maps Unicode characters to ASCII equivalents where defined |
| `icuFolding` | ICU Unicode folding (case, diacritics, equivalents) |
| `icuNormalizer` | Unicode normalization (`NFC`/`NFD`/`NFKC`/`NFKD`) |
| `stopword` | Strips configured stop words |
| `length` | Drops tokens shorter or longer than configured bounds |
| `nGram` | Generates n-grams from each token |
| `edgeGram` | Generates prefix n-grams from each token |
| Stemming filters | Reduces inflected words per language rules |
| `shingle` | Combines adjacent tokens into multi-token shingles |

### 13.1. Filter Ordering Example

```javascript
{
  tokenizer: { type: "standard" },
  tokenFilters: [
    { type: "icuNormalizer", normalizationForm: "nfc" },
    { type: "lowercase" },
    { type: "asciiFolding", originalTokens: "omit" }
  ]
}
```

Execution order:

```text
String -> standard tokens
       -> Unicode NFC
       -> lowercase
       -> ASCII folding
```

Do not assume every filter maps **one token to one token**. Filters like `nGram`, `edgeGram`, or `shingle` expand a single input into **many tokens**, affecting index size, phrase semantics, and operator compatibility.

### 13.2. Stemming Is Not Synonym Expansion

English stemming normalizes morphological variants:

```text
"talked" / "talking" / "talks" -> related stem
```

It does not equate `"car"` with `"automobile"` as synonyms. Synonyms require their own mapping dictionary.

### 13.3. More Stop Words Are Not Always Better

Removing `"the"`, `"a"`, `"of"` can help prose-heavy English corpora, yet short tokens in product names or addresses are often critical:

```text
"iPhone 15 Pro"
"USB C"
"Loại A"
"Đường 3/2"
```

Blindly dropping stop words or single-character tokens can break valid queries. Test against your domain.

---

## 14. Unicode Normalization: NFC, NFD, NFKC, NFKD

**Unicode normalization** resolves strings that look identical yet use different code-point encodings.

For example, `é`:

```text
U+00E9         : precomposed character "é"
U+0065 U+0301  : "e" + combining acute accent
```

Both render identically on screen yet differ in code-point sequences. Without proper normalization, search and indexing can treat them as distinct.

Four standard Unicode normalization forms:

| Form | Meaning |
| --- | --- |
| `NFD` | Canonical decomposition |
| `NFC` | Canonical decomposition followed by composition |
| `NFKD` | Compatibility decomposition |
| `NFKC` | Compatibility decomposition followed by composition |

### 14.1. Canonical vs. Compatibility

- Canonical normalization unifies **canonically equivalent** Unicode representations.
- Compatibility normalization merges visually or functionally similar forms, such as presentation variants.
- Compatibility folding can **erase meaningful distinctions** in certain domains.

Choosing `NFKC` does not mean "always safer than NFC." For identifiers, legal names, or character-exact data, keep source values intact and isolate search-only representations.

### 14.2. Using icuNormalizer

```javascript
{
  type: "icuNormalizer",
  normalizationForm: "nfc"
}
```

This differs from `asciiFolding`: `NFC` **does not** strip Vietnamese diacritics. To let unaccented queries match accented Vietnamese text, add explicit accent folding or a derived search field.

---

## 15. Case Sensitivity and Vietnamese Diacritics

Three distinct requirements often arise:

1. `"MÁY"` and `"máy"` match regardless of **case**.
2. `"máy"` and `"may"` match for **accent-insensitive search**.
3. `"má"`, `"mã"`, and `"mạ"` remain **distinguished** when exact meaning matters.

No single folding filter satisfies all three simultaneously in every scenario.

### 15.1. Lowercase Only Handles Letter Casing

```text
"MÁY" -> "máy"
"máy" != "may" before stripping accents.
```

### 15.2. Accent Folding Boosts Recall at the Expense of Precision

`asciiFolding` or `icuFolding` maps many accented Latin characters to unaccented forms.

```text
"nước" -> folded near "nuoc"
"máy"  -> folded near "may"
```

There is **no guarantee** every Vietnamese character folds as expected; in particular, `đ`/`Đ` behavior must be verified against the exact tokenizer and filter. If the domain requires `"đường"` to match `"duong"`, add test cases for it and consider explicit ingestion-time transliteration rules.

### 15.3. Dropping Diacritics Can Cause Semantic Collisions

```text
"ma" can correspond to:
"ma", "má", "mà", "mả", "mã", "mạ"
```

If everything is folded and scored equally, searching `"mã sản phẩm"` can return noisy hits containing unrelated words.

A common solution is a **dual-field / alternate analyzer** design:

- An accent-preserving analyzer for **precision**.
- A folded analyzer for unaccented **recall**.
- Higher score boost on accent-preserving matches over folded matches.
- Empirical relevance testing using real queries instead of merely counting hits.

---

## 16. Complete Custom Analyzer: Unicode and Vietnamese Example

Custom analyzer `viFold` example:

```javascript
const viFoldDefinition = {
  mappings: {
    dynamic: false,
    fields: {
      title: {
        type: "string",
        analyzer: "viFold",
        searchAnalyzer: "viFold"
      },
      description: {
        type: "string",
        analyzer: "viFold",
        searchAnalyzer: "viFold"
      }
    }
  },
  analyzers: [
    {
      name: "viFold",
      charFilters: [],
      tokenizer: {
        type: "standard"
      },
      tokenFilters: [
        {
          type: "icuNormalizer",
          normalizationForm: "nfc"
        },
        {
          type: "lowercase"
        },
        {
          type: "asciiFolding",
          originalTokens: "omit"
        }
      ]
    }
  ]
};

db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_folded_v1",
    viFoldDefinition
  );
```

**Design intent:**

- Index only `title` and `description`.
- Normalize to Unicode NFC.
- Lowercase tokens.
- Fold accented characters toward ASCII.
- Use the identical analyzer at index time and query time to minimize mismatches.

**This is not a "complete Vietnamese word segmenter."** The `standard` tokenizer still does not automatically recognize Vietnamese compound words, and `asciiFolding` does not guarantee every transliteration rule. Always test against your app's query corpus.

### 16.1. Querying the Custom Index

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_folded_v1",
        text: {
          query: "may loc nuoc",
          path: "title"
        }
      }
    },
    { $limit: 10 },
    {
      $project: {
        _id: 1,
        title: 1,
        score: { $meta: "searchScore" }
      }
    }
  ]);
```

Because the analyzer runs **at both index time and query time**, folded terms can match even when users type without diacritics. Never claim every Vietnamese phrase or proper noun matches accurately without testing on the server.

### 16.2. Weakness of a Folded-Only Index

If the index stores only folded tokens, distinct accented words collapse into the same term. The search engine then loses the signal needed to rank exact accented matches higher using that field alone. Systems with strict ranking requirements should pair original and folded representations.

---

## 17. Multi Analyzer: Keeping Multiple Analyses on One String Field

MongoDB Search supports the **`multi`** option on `string` fields: indexing one field with a primary analyzer alongside named **alternate analyzers**.

For example, indexing `title` simultaneously with:

- `lucene.standard`: standard full-text matching.
- `viFold`: folded form to widen recall.
- `lucene.keyword`: intact string for whole-string token cases.

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_multi_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "string",
            analyzer: "lucene.standard",
            multi: {
              folded: {
                type: "string",
                analyzer: "viFold",
                searchAnalyzer: "viFold"
              },
              whole: {
                type: "string",
                analyzer: "lucene.keyword"
              }
            }
          },
          tenantId: { type: "token" },
          status: { type: "token" }
        }
      },
      analyzers: [
        {
          name: "viFold",
          charFilters: [],
          tokenizer: { type: "standard" },
          tokenFilters: [
            { type: "icuNormalizer", normalizationForm: "nfc" },
            { type: "lowercase" },
            { type: "asciiFolding", originalTokens: "omit" }
          ]
        }
      ]
    }
  );
```

### 17.1. Querying an Alternate Analyzer via a Multi Path

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_multi_v1",
        text: {
          query: "may loc nuoc",
          path: {
            value: "title",
            multi: "folded"
          }
        }
      }
    },
    { $limit: 10 },
    { $project: { title: 1, score: { $meta: "searchScore" } } }
  ]);
```

`path: { value:"title", multi:"folded" }` targets the alternate analyzer subpath inside the Search index. Configuring `multi` **does not create a `title.folded` field in source documents**; it exists purely inside the Search index representation.

### 17.2. Limits of `multi`

- Supported only on eligible field types, primarily `string`.
- Cannot nest multiple levels of `multi`.
- More alternate analyzers increase index footprint and indexing cost.
- Search does not automatically pick the "best" analyzer for a query unless you structure your query and boosts explicitly.

### 17.3. Why Not Replace `multi` with Regex?

Running regex against raw text lacks relevance scoring, stop words, and accent folding, and degrades rapidly at scale. Multi analyzers pre-analyze text in the index to serve multiple query shapes efficiently.

---

## 18. Boosting Original Matches Over Unaccented Matches

Using `catalog_multi_v1`, combine both paths via `compound.should`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_multi_v1",
        compound: {
          should: [
            {
              text: {
                query: "máy lọc nước",
                path: "title",
                score: {
                  boost: {
                    value: 3
                  }
                }
              }
            },
            {
              text: {
                query: "máy lọc nước",
                path: {
                  value: "title",
                  multi: "folded"
                }
              }
            }
          ],
          minimumShouldMatch: 1,
          filter: [
            {
              equals: {
                path: "tenantId",
                value: "T1"
              }
            },
            {
              equals: {
                path: "status",
                value: "ACTIVE"
              }
            }
          ]
        }
      }
    },
    { $limit: 10 },
    {
      $project: {
        title: 1,
        tenantId: 1,
        score: { $meta: "searchScore" }
      }
    }
  ]);
```

Meaning:

- The primary `title` branch gets a boost of 3 in this example.
- The `folded` branch widens recall for unaccented searches.
- `minimumShouldMatch: 1` requires at least one `should` clause to match.
- `compound.filter` scopes results by tenant and status without adding score boosts.

**This is a tuning strategy**, not a claim that boost `3` is universally optimal. Evaluate with real queries while accounting for BM25, field length normalization, and token overlap.

### 18.1. Never Rely on Relevance Score to Protect Tenant Isolation

Without an explicit tenant filter in Search, cross-tenant data can enter candidate sets even if later layers attempt to filter. Enforce authorization in the proper query and data-access layers and test it thoroughly. `boost` controls ranking, **not ACLs**.

---

## 19. String Analyzers Differ from Token Normalizers

This distinction is frequently confused:

| Term | Where Used? | Token Count | Purpose |
| --- | --- | --- | --- |
| `analyzer` | `string` fields | Can emit many tokens | Full-text search and ranking |
| `tokenizer` | Inside custom analyzers | Splits text into tokens | Word-boundary rules |
| `token filter` | After tokenizer | Can transform or emit multiple tokens | Lowercasing, folding, n-grams, stemming |
| **`normalizer`** | **`token` fields** | One token for the entire string | Normalized exact equality, sorting, and faceting |

In MongoDB Search, `token` supports these normalizers:

- `none` (default): preserves the string verbatim.
- `lowercase`: converts the entire token to lowercase.

**You cannot assign an arbitrary `string` custom analyzer as a `token` field's `normalizer`.** They are separate configuration mechanisms.

### 19.1. SKUs Should Be `token`

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      sku: {
        type: "token",
        normalizer: "none"
      }
    }
  }
}
```

An SKU `"AB-100-X"` stays a single intact token instead of splitting into `ab`, `100`, `x` as prose analyzers would.

### 19.2. Brands Can Use the `lowercase` Normalizer

```javascript
{
  brand: {
    type: "token",
    normalizer: "lowercase"
  }
}
```

Enables case-insensitive equality per normalizer semantics, though **it does not strip accents or stem words**.

### 19.3. Querying `token` Fields with `equals`, `in`, and `range`

On `catalog_text_v1` where `brand` is a `token`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        equals: {
          path: "brand",
          value: "AquaHome"
        }
      }
    },
    { $project: { title: 1, brand: 1 } }
  ]);
```

If you also need word-level text search like `"aqua home"`, map the field **as `string` as well** or maintain a separate text field; `token` alone does not generate full-text terms.

---

## 20. One String Field May Need Multiple Field Types

A product title often serves multiple roles:

- Word-based search and description matching: `string`.
- Case-insensitive sorting by title: `token` with `lowercase`.
- Typeahead suggestions: `autocomplete`.

MongoDB Search allows mapping one field under multiple type definitions in the mapping array:

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      title: [
        {
          type: "string",
          analyzer: "lucene.standard"
        },
        {
          type: "token",
          normalizer: "lowercase"
        }
      ]
    }
  }
}
```

`string` does not automatically support all `token` operators. When you need `equals`, facets, or string sorting, modern docs recommend the `token` type rather than legacy `stringFacet`.

**Limitation:** every extra type/analyzer increases storage and indexing overhead. Declare only what queries actually use.

---

## 21. Autocomplete Is Not Included Automatically Just Because Search Is Enabled

Autocomplete is a distinct requirement from full-text search.

Example:

```text
User types: "wire"
Suggest:    "Wireless Mouse"
```

A standard text index creates tokens such as `wireless` and `mouse`; querying `wire` does not match the token `wireless`.

MongoDB Search provides the **`autocomplete` field type** and `autocomplete` operator:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_autocomplete_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "autocomplete",
            tokenization: "edgeGram",
            minGrams: 2,
            maxGrams: 15,
            foldDiacritics: true
          }
        }
      }
    }
  );
```

Once the index is `READY`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_autocomplete_v1",
        autocomplete: {
          query: "wire",
          path: "title"
        }
      }
    },
    { $limit: 10 },
    { $project: { _id: 1, title: 1 } }
  ]);
```

### 21.1. Three N-Gram Tokenization Strategies

| Tokenization | Meaning | Use Case |
| --- | --- | --- |
| `edgeGram` | Prefix of each token | Typing from the start of words |
| `rightEdgeGram` | Suffix of each token | Matching word endings |
| `nGram` | Arbitrary substrings of each token | Mid-token substring suggestions |

Conceptual example for `"water"` with grams 2 to 4:

```text
edgeGram  -> "wa", "wat", "wate"
nGram     -> "wa", "at", "te", "er", "wat", "ate", ...
```

Do not treat this as an exact trace of every tokenizer/normalizer; exact emitted tokens depend on Search configuration.

### 21.2. Why Avoid Setting `minGrams=1` Thoughtlessly?

Very short n-grams emit massive numbers of terms, hurting selectivity while bloating index size and query cost. Documentation often favors larger `minGrams` depending on UX, language, and typical token lengths.

### 21.3. Measure Autocomplete and Full-Text Separately

Autocomplete prioritizes low-latency response for partial typing, whereas full-text focuses on relevance for complete queries. Never route every search request through an autocomplete index simply because it matches substrings broadly.

---

## 22. Fuzzy Matching Differs from Normalization

When a user makes a typo:

```text
"wireles" instead of "wireless"
```

Fuzzy search relies on **edit distance** to match near-spelling tokens—not merely lowercasing or accent stripping.

Example:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        text: {
          query: "wireles",
          path: "title",
          fuzzy: {
            maxEdits: 1,
            prefixLength: 2,
            maxExpansions: 50
          }
        }
      }
    },
    { $limit: 10 },
    { $project: { title: 1, score: { $meta: "searchScore" } } }
  ]);
```

Meaning:

- `maxEdits` caps the allowed character edits.
- `prefixLength` requires leading characters of the token to match exactly per fuzzy rules.
- `maxExpansions` bounds how many candidate terms are evaluated.

Fuzziness is not Vietnamese transliteration: missing diacritics across multiple letters can exceed `maxEdits: 1`, so `fuzzy` cannot guarantee matching all unaccented Vietnamese words.

### 22.1. Fuzziness Can Increase False Positives

If overly permissive, short product queries match unrelated words, driving up CPU, latency, and result noise. Restrict fuzzy paths, bound expansions, measure precision, and plan fallback behavior.

---

## 23. Phrase Queries and Token Positions

Standard full-text matches words anywhere in a field. When word order matters, use the `phrase` operator:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        phrase: {
          query: "water filter",
          path: "title",
          slop: 0
        }
      }
    },
    { $project: { title: 1, score: { $meta: "searchScore" } } }
  ]);
```

`phrase` checks **token order and positions**, rather than doing a byte-for-byte SQL equality check. Tokenizers may strip punctuation or stop words and shift token positions depending on the analyzer.

### 23.1. `indexOptions`

A MongoDB Search `string` field can configure `indexOptions`:

- `docs`: records only which documents contain each term.
- `freqs`: adds term frequency.
- `positions`: adds term positions; required for `phrase` and positional operators.
- `offsets`: adds character offsets; required for highlighting.

The default is typically `offsets`. Lowering `indexOptions` saves index storage, but **can disable phrase queries and highlighting**. Choose based on actual feature requirements rather than shrinking index size blindly.

---

## 24. Highlighting Relies on Index Offsets

To return matched spans for UI highlighting:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        text: {
          query: "water",
          path: "title"
        },
        highlight: {
          path: "title"
        }
      }
    },
    { $limit: 5 },
    {
      $project: {
        title: 1,
        score: { $meta: "searchScore" },
        highlights: { $meta: "searchHighlights" }
      }
    }
  ]);
```

Highlight output includes `hit`/`text` segments so the UI can emphasize matches.

**UI security:** never inject unescaped document text directly into HTML just because highlights are returned. Highlighting is search metadata, not XSS protection.

### 24.1. Why Might Highlights Be Empty?

Common causes:

- The field is not mapped as `string` with `offsets` enabled.
- Search `path` and `highlight.path` do not align.
- Analyzer transformations altered tokens in ways that break offset mapping.
- The document matched on a different field than the one requested for highlighting.

---

## 25. Synonyms Differ from Stemming and Token Filters

Concepts often have multiple names:

```text
"tv" / "television"
"laptop" / "notebook computer"
"điện thoại" / "smartphone"
```

**Synonym mappings** expand queries across equivalent words or phrases, distinct from:

- Lowercasing: `TV` → `tv`.
- Accent folding: `máy` → unaccented form.
- Stemming: `running` → related stem.
- Fuzzy matching: `laptpo` near `laptop` via edit distance.

MongoDB Search supports declaring synonym mappings in a Search index backed by a synonyms source collection and querying with `text.synonyms`.

### 25.1. Key Caveats

- Synonym dictionaries require ongoing curation and quality review.
- Synonym queries require appropriate `positions`/`offsets` index options.
- Per Search docs, **do not combine `fuzzy` and `synonyms` in the same `text` operator**.
- Specify `matchCriteria` when using synonyms as recommended by MongoDB.
- Do not assume seemingly similar words are interchangeable in product names or addresses.

For instance, `"apple"` could mean the tech company or the fruit; context-free synonyms can introduce noise.

---

## 26. Normalize Before Storing or Inside the Analyzer?

There are two main strategies:

### 26.1. Keep Source Text Intact; Analyze Inside Search

```javascript
{
  title: "Máy lọc nước"
}
```

At index time, a custom analyzer derives the searchable forms.

Pros:

- Source data preserves diacritics and original casing.
- Multiple alternate analyzers can coexist on the same field.
- Changing search behavior only updates/rebuilds the Search index without mutating business documents.

Limits:

- Built-in and custom analyzers may not handle full Vietnamese word segmentation.
- Certain custom normalization rules cannot be expressed solely with built-in filters.

### 26.2. Add a Normalized Search Field at Ingestion

```javascript
{
  title: "Bất động sản",
  titleSearch: "bat dong san"
}
```

Pros:

- Application can apply custom transliteration or Vietnamese word segmentation.
- Domain rules (such as mapping `đ` to `d` per policy) are easy to enforce.

Risks:

- Extra field data to keep synchronized.
- Can collapse diacritic/semantic distinctions.
- Requires data migration/backfill whenever the normalization algorithm changes.
- If `title` changes without updating `titleSearch`, search becomes stale.

**Recommendation:** keep the original field as the source of truth, and apply normalization inside the **Search index or a versioned auxiliary field**—never overwrite display text.

---

## 27. Designing Specifically for Vietnamese

### 27.1. The Diacritics Problem

Queries:

```text
"may loc nuoc"
"máy lọc nước"
"Máy Lọc Nước"
```

often should find the same product. Yet queries like:

```text
"ma"
"mã"
"má"
```

should not always be treated as identical. Instead of uncontrolled global accent folding, combine:

1. An accent-preserving search field.
2. An alternate folded search field.
3. Higher boost on the accent-preserving field.
4. An evaluation corpus covering both accented and unaccented queries.
5. Domain tests for proper names, addresses, and product codes.

### 27.2. The Compound-Word Problem

```text
"bất động sản"
"công nghệ thông tin"
"máy học"
```

Whitespace tokenizers split on spaces, whereas Vietnamese semantic segmentation treats multi-syllable compounds as single units. Never claim `lucene.standard` understands these compounds automatically.

Options:

- Search regular tokens and use `phrase` for multi-syllable expressions.
- Index controlled shingles/n-grams if queries warrant it.
- Run external Vietnamese segmentation/normalization into a dedicated indexed field.
- Use hybrid or vector search when semantic similarity is needed, keeping its semantics distinct from lexical Search.

### 27.3. Codes and Brand Names

Do not apply natural-language analyzers to:

- SKUs and serial numbers.
- Contract codes.
- Building codes.
- Normalized email/phone keys.
- Order IDs.

Splitting `"AB-123"` into `ab` and `123` breaks exact code lookup. Use `token` fields or business-normalized exact keys instead.

### 27.4. Testing Special Characters and Edge Cases

Your test corpus should cover:

```text
Đường, đường, duong
Hòa, Hoà, hoa
máy, may, mã, ma
C++, C#, Node.js
USB-C, USB C
AB-123, AB123
iPhone 15 Pro
Trần, Tran
¼, 1/4
```

The goal is verifying tokenization, Unicode normalization, accent folding, and false matches against real data—not picking an analyzer based on a single tidy example.

---

## 28. Inspect Tokens Before Tuning Relevance

When a query misses a document that seems "obviously matching," do not blindly crank up fuzziness—check:

1. What is the exact stored source text?
2. Which Search field type maps that field?
3. What is the index analyzer?
4. What is the search analyzer?
5. What tokens does the document emit?
6. What tokens does the query emit?
7. Are tenant/status filters or field paths misconfigured?
8. Is the index `READY` and synced?

### 28.1. Mismatch Example

```text
Document:
  "AB-123-X"

Index analyzer keyword:
  ["AB-123-X"]

Query analyzer standard:
  ["ab", "123", "x"]

Result:
  terms fail to align.
```

For exact SKU lookups, use `token` + `equals`, not `text` against split tokens.

### 28.2. Using Text Analysis Inspection Tools

In the MongoDB Atlas Search Index editor, **View text analysis** lets you inspect index-time and query-time tokens for your analyzer config. On self-managed setups, consult the diagnostics tools supported by that environment; do not rely on unverified custom shell methods.

### 28.3. Capture Test Cases as Fixtures

```text
Input document: "Máy lọc nước"
Input query:    "may loc nuoc"

Expected:
  candidate P001 should match via the folded path.

Query: "mã sản phẩm"
Expected:
  should not produce excessive false matches for "ma".
```

Never stop at "the API returns HTTP 200"—validate ranking, false positives, false negatives, and multilingual inputs.

---

## 29. Serving Multiple Query Types in One Application

An e-commerce app can route different queries cleanly:

| Route | Requirement | Index / Query |
| --- | --- | --- |
| `GET /products/{sku}` | Exact lookup | B-tree index on SKU or Search `token + equals` |
| `GET /search?q=...` | Full-text | `string` analyzer + `$search.text` |
| `GET /suggest?q=...` | Prefix suggestions | `autocomplete` field/operator |
| `GET /search?q=...&brand=...` | Text + filter | `compound.must/filter` |
| `GET /search?sort=brand` | String sort | `token` type with matching normalizer |
| `GET /reports/category` | Facets | `token` field + `$searchMeta`/facets |
| Semantic similarity search | Meaning-based search | Dedicated Vector / hybrid architecture |

### 29.1. Do Not Solve Every Problem with Text Matching

In a system with `sku`, `tenantId`, and `status`, exact matches and filters deserve **exact types and operators**; never apply fuzziness to IDs where one character difference points to a completely different entity.

### 29.2. Lexical vs. Semantic Search

Lexical Search operates on terms, tokens, linguistic rules, and ranking. Vector Search uses embeddings to measure semantic proximity. Both can be combined at query time, yet a Search index's **normalizer** and **tokenizer** do not create semantic understanding on their own.

---

## 30. Java MongoDB Sync Driver: Executing `$search`

The Java Sync Driver supports aggregation pipelines. Using BSON `Document` avoids tying the example to a specific Search builder DSL:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

public final class ProductSearchRepository {

    public static void search(
            MongoCollection<Document> products,
            String userQuery
    ) {
        if (userQuery == null ||
            userQuery.isBlank() ||
            userQuery.length() > 200) {
            throw new IllegalArgumentException(
                "Invalid search query"
            );
        }

        Document searchStage = new Document(
            "$search",
            new Document("index", "catalog_text_v1")
                .append(
                    "text",
                    new Document("query", userQuery)
                        .append(
                            "path",
                            Arrays.asList(
                                "title",
                                "description"
                            )
                        )
                )
        );

        List<Document> pipeline = Arrays.asList(
            searchStage,
            new Document("$limit", 20),
            new Document(
                "$project",
                new Document("_id", 1)
                    .append("title", 1)
                    .append("brand", 1)
                    .append(
                        "score",
                        new Document(
                            "$meta",
                            "searchScore"
                        )
                    )
            )
        );

        products.aggregate(pipeline).forEach(
            document ->
                System.out.println(document.toJson())
        );
    }
}
```

Key reminders:

- `MongoCollection` must point to a collection holding the `catalog_text_v1` Search index.
- The MongoDB deployment must support Search/`mongot`.
- Pass query text as a **BSON value**, never string-interpolated JSON containing user input.
- Validate input length and empty queries; add authentication and tenant filters in real apps.
- `$search` comes first; follow with `$limit`, `$project`, pagination, and sorting as needed.

### 30.1. Why Not Java `String.hashCode` or Regex?

Search tokenization and indexing do not use Java `String.hashCode`. Java regex does not provide BM25, analyzers, or autocomplete. The driver dispatches the Search command; the server and `mongot` execute matching and ranking.

---

## 31. Java: Search with an Explicit Tenant Filter

In a multi-tenant SaaS, never search the whole catalog and **filter by tenant only after results are returned**.

`compound` example:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

public final class TenantCatalogSearch {

    public static void search(
            MongoCollection<Document> products,
            String tenantId,
            String keyword
    ) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException("Empty query");
        }

        Document textQuery = new Document(
            "text",
            new Document("query", keyword)
                .append("path", "title")
        );

        Document tenantFilter = new Document(
            "equals",
            new Document("path", "tenantId")
                .append("value", tenantId)
        );

        Document statusFilter = new Document(
            "equals",
            new Document("path", "status")
                .append("value", "ACTIVE")
        );

        Document compound = new Document(
            "must",
            Arrays.asList(textQuery)
        ).append(
            "filter",
            Arrays.asList(
                tenantFilter,
                statusFilter
            )
        );

        List<Document> pipeline = Arrays.asList(
            new Document(
                "$search",
                new Document("index", "catalog_text_v1")
                    .append(
                        "compound",
                        compound
                    )
            ),
            new Document("$limit", 20),
            new Document(
                "$project",
                new Document("title", 1)
                    .append("status", 1)
                    .append("tenantId", 1)
                    .append(
                        "score",
                        new Document("$meta", "searchScore")
                    )
            )
        );

        products.aggregate(pipeline).forEach(
            result -> System.out.println(result.toJson())
        );
    }
}
```

In production, `tenantId` must come from the **authenticated context**, never from a user-editable query parameter.

### 31.1. Filters Preserve Relevance

`compound.filter` narrows candidates without altering relevance scores, making it clean to combine "best text matches" with "authorized documents only."

### 31.2. Queries May Require Indexing Extra Metadata

If the Search index only maps `title` as `string` without mapping `tenantId` and `status` as `token`, `equals` filters will fail or miss due to incompatible mappings. Design index mappings and queries together.

---

## 32. Search Score: Ranking Order, Not a Confidence Percentage

MongoDB Search uses scoring models such as BM25 depending on query type and settings. `searchScore`:

- Ranks hits **relatively** within a query.
- Depends on term statistics, field length, frequency, and other factors.
- Is not bounded between 0 and 1.
- Is not a probability like "93% certain this document is right."
- Shifts as the corpus, Search index, analyzer, or deployment changes.

Example:

```javascript
{
  $project: {
    _id: 1,
    title: 1,
    relevance: { $meta: "searchScore" }
  }
}
```

### 32.1. Should You Hardcode a Fixed Score Threshold?

A cutoff like `score >= 5` may work on today's dataset yet break after adding a million documents or tweaking an analyzer. If a cutoff is needed, measure score distributions across representative queries and version the relevance policy.

### 32.2. Ranking and Pagination

When paginating by score, use a deterministic pagination strategy compatible with Search semantics. Across different search nodes with shifting term statistics, score-based ordering can fluctuate. MongoDB offers scoring options such as `stableTfl`/`boolean` for greater stability, trading off ranking nuance.

---

## 33. Fuzzy, Synonyms, Autocomplete, and Stemming: Do Not Mix Unchecked

Every recall-expanding technique carries a cost:

| Strategy | Expands Matching By | Risk |
| --- | --- | --- |
| Normalization / folding | Case, accents, forms | Collapsing distinct words |
| Stemming | Morphological/grammatical variants | Over-merging or wrong language rules |
| Fuzzy | Edit-distance spelling variants | False positives and expansion cost |
| Synonyms | Dictionary-based term equivalents | Context-inappropriate synonyms |
| Autocomplete / n-gram | Prefixes / substrings | Token bloat, larger indexes, noise |

Do not turn everything on assuming results become "smarter." Match the tool to the problem:

- Missing diacritics? Folding.
- Typos? Fuzzy.
- Partial words while typing? Autocomplete.
- Alternate vocabulary? Synonym mappings.
- English word inflections? Language-matched stemming.

You can combine techniques, provided you test their interactions and respect operator limits.

---

## 34. Index Size, Performance, and Cost

Text analysis indexes grow quickly because each string generates multiple terms.

Example:

```text
"wireless"
  standard analyzer -> 1 token

"wireless"
  nGram 2..5        -> many tokens

Indexing 1 million product titles:
  term count, memory, and storage differ dramatically.
```

Cost drivers:

1. `dynamic: true` indexing unnecessary fields.
2. Multiple `multi` analyzers on the same field.
3. `nGram`/`edgeGram` with overly small `minGrams`.
4. Storing unnecessary `positions`/`offsets`.
5. Indexing huge descriptions or unstripped HTML.
6. Large synonym dictionaries and complex analyzers.
7. Overly broad fuzzy expansions.
8. Redundant Search indexes duplicating functionality.
9. High write/update churn forcing `mongot` reindexing.
10. Queries missing tenant/status filters or scanning broad paths.

### 34.1. Token Length Limits

MongoDB Search enforces token length limits on `string` fields: per documentation, tokens exceeding **32,766 bytes** are not indexed. Because the `keyword` analyzer emits the entire string as a single token, long strings hit this limit easily.

The `token` type also enforces length handling (MongoDB Search notes strings exceeding **8,181 characters** may be truncated before indexing). Never map hundreds of kilobytes of text as `token` expecting full exact matching.

### 34.2. Do Not Use Search Indexes as Default Primary-Key Lookups

Looking up `_id` or unique `sku` with MongoDB's existing B-tree index is simpler and strongly consistent. Search indexes add overhead and sync lag, so reserve them for workloads that actually require Search features.

---

## 35. Updating Search Indexes and Changing Analyzers

Analyzers govern the terms **persisted inside the index**. Changing an analyzer is not merely a query tweak—the index representation must be rebuilt.

Example:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .updateSearchIndex(
    "catalog_text_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "string",
            analyzer: "lucene.simple"
          }
        }
      }
    }
  );
```

**This snippet replaces the entire supplied definition**, not just `title`'s analyzer. Running it on a live index drops other previously mapped fields. Never copy-paste without reviewing the complete current definition.

### 35.1. Plan for Changing an Analyzer in Production

1. Capture the active index definition.
2. Create a **new Search index with a distinct name** using the updated analyzer if tier quotas permit.
3. Wait for the new index to reach `READY`.
4. Run comparison tests for relevance and latency.
5. Shift traffic via canary or feature flag.
6. Monitor indexing lag, false negatives/positives, and errors.
7. Drop the old index only after verifying a clean rollback path.

This prevents breaking live search by changing definitions and query logic simultaneously without a fallback.

### 35.2. `READY` Does Not Mean Read-Your-Writes

`READY` indicates the index can serve queries. Syncing remains asynchronous, so a newly committed update may still lag briefly. Monitor Search sync lag and query behavior rather than status alone.

---

## 36. Case-Insensitive Exact Matching vs. Full-Text Search

Suppose:

```text
Stored brand: "AquaHome"
Query:        "aquahome"
```

With `brand` mapped as `token` and `normalizer:"lowercase"`, exact equality matches case-insensitively per the normalizer.

By contrast:

```text
Stored title: "Máy lọc nước mini"
Query:        "lọc"
```

is **full-text word retrieval**, requiring `string` + analyzer + the `text` operator.

Commonly confused scenarios:

| Requirement | Recommended Choice |
| --- | --- |
| Exact brand match, case-insensitive | `token + lowercase normalizer + equals` |
| Product title contains an analyzed word | `string + analyzer + text` |
| Product title matches entire normalized string | `token` or `keyword` analyzer per requirements |
| Product title has a word starting with typed letters | `autocomplete` |
| Product title contains minor typo | `text.fuzzy` |
| Semantic similarity search | Vector / semantic retrieval if needed |

Never conflate `normalizer` and `analyzer`; both can lowercase, yet their token and operator contracts differ completely.

---

## 37. Deployment Troubleshooting Guide

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `$search` reports index not found | Wrong index name or index not created/`READY` | `$listSearchIndexes`, index name |
| MongoDB does not support `$search` | Deployment lacks `mongot`/Search or incompatible version | Inspect Atlas/self-managed Search setup |
| Search misses newly inserted doc | Indexing lag | Monitor Search sync lag; retry as needed |
| `text` fails to match intact SKU | SKU tokenized or mapped as `token` only | Use `token + equals` |
| Unaccented query misses accented doc | Analyzer lacks folding | Design folded analyzer / `multi`, inspect tokens |
| `"đường"` vs. `"duong"` mismatches | Incomplete Unicode transliteration | Test `đ`, add custom normalization |
| English query drops key words | Over-aggressive stemming/stop words | Inspect per-field analyzers |
| Casing mismatches | `keyword`/`whitespace` preserves case | Add `lowercase` filter or `token` normalizer |
| `phrase` fails | `indexOptions` lacks `positions` or analyzer mismatch | Check field mapping |
| Highlights missing | Missing `offsets` or wrong highlight path | Check mapping and query paths |
| Autocomplete returns nothing | Field not mapped as `autocomplete` | Create `autocomplete` mapping/index |
| Autocomplete is too noisy | `minGrams` too small / `nGram` too broad | Raise threshold, tune ranking |
| Fuzzy is very slow | Large `maxExpansions` and broad scope | Restrict `path`, expansions, and latency budgets |
| Brand filter fails | Field not mapped as `token` or wrong type | Check mapping and `equals` |
| `$text` ignores Search index | Two separate mechanisms | Use `$search` |
| `$search` ignores B-tree `createIndex` | Search requires its own index | Create a Search index |
| `multi` path errors | Invalid field path or `multi` name | Compare against index definition |
| Relevance shifts after deploy | Changed analyzer, scoring, corpus, or index | Compare corpus and score details |
| Search leaks another tenant | Missing filter / authorization | Add `compound.filter` and ACL checks |
| Search slows on long descriptions | Overly broad index/query or excessive n-grams | Explain/monitor resources |
| Analyzer changed, old results persist | Rebuild incomplete or querying old index | Check index status and name |
| Long `keyword` field missing from index | Exceeded token length limit | Split content or use another analyzer |
| Vietnamese syllables split unexpectedly | `standard` is not a Vietnamese semantic segmenter | Use auxiliary field or NLP pipeline |
| `token` normalizer rejects custom analyzer | `token` supports only built-in normalizers | Use `string` / alternate field |

---

## 38. Practice Exercises

### Exercise 1 — Distinguish Index Types

Run:

```javascript
db.products.createIndex({ title: "text" });
```

**Question:** Does this command create a MongoDB Search index usable by `$search`?

**Answer:** No. That creates a legacy text index for `$text`. Search indexes are created with Search APIs/tools.

### Exercise 2 — Analysis Pipeline Order

A custom analyzer configures `htmlStrip`, `standard` tokenizer, and `lowercase`.

**Question:** What is the execution order?

**Answer:** Character filter → tokenizer → token filter.

### Exercise 3 — Preserving SKUs

SKU `"AB-123-X"` must match strictly intact without splitting.

**Answer:** Use a `token` field with an appropriate normalizer and `equals`, or an exact-match B-tree index.

### Exercise 4 — Unaccented Vietnamese

User types `"may loc nuoc"`, data holds `"Máy lọc nước"`.

**Answer:** Configure a folded analyzer or alternate field on both index and query paths, and test Vietnamese diacritics and `đ`.

### Exercise 5 — Keyword Analyzer

`"Wireless Mouse"` is indexed with `lucene.keyword` and queried with `"mouse"`.

**Question:** Does it match as an individual word by default?

**Answer:** No. `keyword` keeps the entire string as a single token.

### Exercise 6 — Whitespace and Casing

Index uses `lucene.whitespace` on `"HELLO world"`; query is `"hello"`.

**Answer:** `whitespace` preserves case, so `HELLO` and `hello` are distinct tokens. Add a `lowercase` filter or matching analyzer.

### Exercise 7 — Token Normalizer

You want `"aquahome"` to match `"AquaHome"` on `brand` and facet by brand.

**Answer:** `token` with `normalizer: "lowercase"` fits well.

### Exercise 8 — Token vs. Analyzer

A field is mapped as `token`. A developer tries to use the `text` operator to match a middle word.

**Answer:** `token` alone is insufficient; map the field as `string` to support `text` and `phrase` operators.

### Exercise 9 — Search Index Build

`createSearchIndex()` returns success, yet an immediate query fails.

**Answer:** Index builds are asynchronous; inspect `$listSearchIndexes` and wait for `READY`.

### Exercise 10 — One Field, Multiple Roles

`title` needs both full-text search and case-insensitive sorting.

**Answer:** Map `title` as both `string` and `token` (with `lowercase` normalizer) in the Search mapping.

### Exercise 11 — Autocomplete

User types `"wire"` and expects `"Wireless Mouse"`.

**Answer:** Use the `autocomplete` field type with the `autocomplete` operator/`edgeGram` per config—do not assume a `string` analyzer suffices.

### Exercise 12 — Fuzzy

User types `"wireles"` instead of `"wireless"`.

**Answer:** Use `text.fuzzy` with bounded `maxEdits`, `prefixLength`, and `maxExpansions`.

### Exercise 13 — Phrase and Positions

A field is indexed with `indexOptions: "docs"`. The team wants phrase queries.

**Answer:** `phrase` requires term positions. Update mapping to `positions` or `offsets`.

### Exercise 14 — Unicode

Two strings render as `"é"`, but one uses decomposed combining marks.

**Answer:** Use `icuNormalizer` with `NFC` for canonical equivalence; remember this does not strip diacritics.

### Exercise 15 — Vietnamese Stop Words

A team drops all single-character tokens and strips `"c"`.

**Question:** Why is this risky?

**Answer:** `C` can be a technical symbol or model identifier (`USB-C`). Tailor stop-word and length filtering to the domain.

### Exercise 16 — Ranking and Diacritics

A folded-only index receives query `"mã"` while many docs contain `"ma"`.

**Answer:** Folding merges distinct words. Keep an unfolded alternate path and boost exact accented matches.

### Exercise 17 — Tenant Isolation

A `$search.text` query matches products from both `T1` and `T2`, yet the user may only see `T1`.

**Answer:** Add `compound.filter` with `tenantId` from the authenticated context and enforce authorization.

### Exercise 18 — Data Freshness

A user updates a title and Search does not show the new title immediately.

**Answer:** Search indexing is asynchronous. Use direct database key reads when strict read-after-write is required.

### Exercise 19 — N-Gram Cost

Autocomplete uses `minGrams:1` across one million titles.

**Answer:** Emitted terms explode, inflating index size and query cost. Raise thresholds and tune tokenization strategy.

### Exercise 20 — Dynamic Mapping

Production uses `dynamic:true` on documents containing sensitive nested fields irrelevant to search.

**Answer:** Switch to explicit static mappings / field allowlists to avoid indexing sensitive data and wasting resources.

### Exercise 21 — Fuzzy and Synonyms

A `text` query specifies both `fuzzy` and `synonyms`.

**Answer:** Documentation forbids using both simultaneously inside the same `text` operator; adjust the query structure.

### Exercise 22 — Vietnamese Word Segmentation

Data contains `"bất động sản"`, and `standard` analyzer emits tokens at word breaks.

**Question:** Does it automatically recognize `"bất_động_sản"` as a single semantic word?

**Answer:** Do not assume so. Test and apply an appropriate analyzer or external linguistic preprocessing.

### Exercise 23 — Changing Analyzers

A team switches `lucene.standard` to `viFold` thinking only query parsing changes.

**Answer:** Indexed terms also change; plan an index rebuild/reindex and safe rollout.

### Exercise 24 — Search Score

Two hits return scores `5.6` and `3.2`.

**Question:** Can you state the first hit is "56% accurate"?

**Answer:** No. Scores reflect algorithmic relative ranking, not accuracy probabilities.

---

## 39. Designing Search for Production Systems

### Step 1 — Define the Search Contract

Document clearly:

- Which fields are searchable?
- Full-text or exact lookup?
- Unaccented Vietnamese needed?
- Multilingual, compound words, or phrases needed?
- Autocomplete, fuzziness, or synonyms needed?
- Tenant/status security filters?
- Ranking and latency SLAs?
- Strict read-your-writes requirements?

### Step 2 — Classify Fields

| Field Category | Examples | Search Type / Analyzer |
| --- | --- | --- |
| Prose | `title`, `description` | `string` + analyzer |
| Exact identifier | `sku`, `contractCode` | `token` or exact B-tree index |
| Facet / keyword | `brand`, `category` | `token` + normalizer |
| Prefix suggestions | `title` | `autocomplete` |
| Tenant / status | `tenantId`, `status` | `token` + compound filter |
| Vector semantics | `embedding` | Dedicated Vector Search architecture |

### Step 3 — Select Analyzers per Use Case

1. Start with `lucene.standard` when no special behavior is needed.
2. Validate lowercasing and Unicode normalization on fixtures.
3. Add a folded analyzer for unaccented Vietnamese recall.
4. Keep an un-folded path to preserve precision.
5. Never push IDs or SKUs through prose analyzers.
6. Add `nGram`/autocomplete only where query paths need them.
7. Benchmark every choice against the corpus.

### Step 4 — Version Your Indexes

Use versioned names:

```text
catalog_text_v1
catalog_multi_v2
catalog_autocomplete_v1
```

Wait for `READY`, validate on staging, and canary-shift traffic during major definition changes.

### Step 5 — Measure Search Quality

Metrics:

- `Precision@k`: fraction of relevant hits in the top k.
- `Recall@k`: fraction of expected items retrieved in top k (given ground truth).
- `MRR`/`NDCG` when graded relevance labels exist.
- Query zero-result rate.
- p50/p95/p99 latency.
- Search indexing lag.
- Index size, Search CPU/memory, and write throughput.
- Query expansion cost for fuzzy/n-gram queries.
- Share of unaccented, mixed-case, and misspelled queries.

### Step 6 — Change Management

When modifying analyzers or source data:

1. Version-control index configs.
2. Build a new parallel index when appropriate.
3. Run regression test suites.
4. Monitor low-result and zero-result queries.
5. Keep an index/query rollback path.
6. Avoid changing tokenizers and synonyms simultaneously if root-cause attribution becomes impossible.

---

## 40. Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| "`$text` indexes and Search indexes are the same." | Two distinct engines, APIs, and architectures. |
| "A Search index is just a B-tree index with an analyzer option." | MongoDB Search uses indexes maintained by `mongot`. |
| "MongoDB Search only runs on Atlas." | As of 2026, supported self-managed deployments exist; requires proper `mongot` setup. |
| "Once `createSearchIndex` returns success, you can query immediately." | Builds are asynchronous; wait for `READY`. |
| "Search is always read-your-writes." | Subject to indexing lag. |
| "An analyzer is just a tokenizer." | Analyzers combine char filters, a tokenizer, and token filters. |
| "Custom analyzers only need token filters." | A tokenizer is mandatory; char/token filters are optional. |
| "Search analyzers do not affect results." | Query tokens must align with indexed tokens. |
| "Every analyzer lowercases." | Built-in `keyword` and `whitespace` preserve case. |
| "Normalizers and analyzers are identical." | `normalizer` applies to `token` fields and emits one token. |
| "There is a built-in `lucene.vietnamese` analyzer." | Not present in 2026 MongoDB Search built-in language analyzers. |
| "The standard analyzer understands Vietnamese compounds." | Never assume semantic word segmentation. |
| "Lowercasing removes diacritics." | Lowercasing only changes letter case. |
| "NFC strips accents." | NFC is canonical normalization, not accent folding. |
| "Folding never loses meaning." | It merges distinct words such as `ma`/`má`/`mã`. |
| "`asciiFolding` always maps `đ` to `d`." | Must be tested or handled via custom transliteration. |
| "Stemming equals synonyms." | Stemming reduces inflections; synonyms map semantic equivalents. |
| "Fuzziness fixes every typo." | Bounded by edit distance and prone to false positives. |
| "Keyword analyzer matches individual words inside a string." | It emits one token for the entire string. |
| "Search `string` fields automatically optimize facets, sorts, and exact checks." | Use `token` fields for those operators. |
| "A full-text index automatically powers autocomplete." | Requires an `autocomplete` mapping and operator. |
| "`$search` returns scores as probabilities." | Scores rank relative relevance, not accuracy probability. |
| "Adding `limit` guarantees a cheap query." | Index size, expansions, and scanning still drive cost. |
| "`dynamic:true` is always best for production." | Can index unnecessary or sensitive fields. |
| "Search score enforces access control." | Filter and verify tenant authorization explicitly. |
| "Changing an analyzer needs no rebuild." | Indexed terms depend on the analyzer; plan rollout/reindex. |
| "Tokenizers handle all Vietnamese formats naturally." | Test real corpora; external preprocessing may be needed. |
| "Regex and `$search.text` are equivalent." | Differ in tokenization, indexing, and relevance. |
| "One matching query proves Search quality." | Measure precision/recall and p95/p99 across real workloads. |

---

## 41. Production Checklist

1. Does the deployment include supported MongoDB Search / `mongot`?
2. Are Search indexes `READY` and syncing cleanly?
3. Are Search indexes, legacy text indexes, and B-tree indexes clearly separated?
4. Does every mapped field use the Search type matching its use case?
5. Is dynamic mapping disabled or prevented from indexing unneeded fields?
6. Are index analyzers chosen intentionally?
7. Are search analyzers compatible with indexed terms?
8. Do custom analyzers order `charFilters` → `tokenizer` → `tokenFilters` properly?
9. Are SKUs and IDs protected from prose tokenization?
10. Do `token` fields use the intended `none`/`lowercase` normalizer?
11. Does Unicode `NFC`/`NFKC` fit domain rules?
12. Has accent folding been tested on `đ`, `Đ`, and combining marks?
13. Have Vietnamese compound words been tested?
14. Are exact accented matches preserved/boosted alongside folded paths?
15. Are `token` fields configured for facets, exact filtering, and sorting?
16. Does autocomplete have dedicated mappings/operators and sensible `minGrams`?
17. Does fuzziness bound edits/expansions to prevent overly broad queries?
18. Do `phrase` and `highlight` have matching `indexOptions`?
19. Are synonym dictionaries, analyzers, and `matchCriteria` clearly configured?
20. Are tenant/status filters enforced at both Search and authorization layers?
21. Is `$search` placed at the required pipeline position?
22. Are limits, projections, timeouts, and pagination strategies enforced?
23. Is `searchScore`/relevance measured against a test corpus rather than intuition?
24. Are indexing lag, Search node resources, and error rates monitored?
25. Do index/analyzer changes follow versioning, staging tests, canarying, and rollback?
26. Are lexical Search and semantic/vector Search cleanly distinguished?
27. Does logging avoid recording sensitive query or document content?
28. Does the test suite cover accented/unaccented Vietnamese, abbreviations, SKUs, and typos?
29. Are Search index counts and storage budgets bounded?
30. Can post-update read flows tolerate Search indexing lag?

---

## 42. Official MongoDB References

- [MongoDB Search Overview](https://www.mongodb.com/docs/search/): features, Search architecture, and operators.
- [Deployment Options](https://www.mongodb.com/docs/search/deployment/deployment-options/): Atlas and self-managed deployment choices.
- [Self-Managed Search](https://www.mongodb.com/docs/search/self-managed/current/): role of `mongot`, connectivity, and administration.
- [Create a Search Index — `db.collection.createSearchIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/): syntax and build states.
- [`$listSearchIndexes`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/listSearchIndexes/): `READY`/`BUILDING`/`STALE` states.
- [Search Index Definitions](https://www.mongodb.com/docs/search/indexes/index-definitions/): mappings, `analyzer`, `searchAnalyzer`, and custom analyzers.
- [Process Data with Analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/overview/): overview of analyzers, tokenizers, and normalizers.
- [Custom Analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/custom/): `charFilters`, `tokenizer`, and `tokenFilters`.
- [Character Filters](https://www.mongodb.com/docs/search/indexes/analyzers/character-filters/): `htmlStrip` and `mapping`.
- [Token Filters](https://www.mongodb.com/docs/search/indexes/analyzers/token-filters/): lowercase, Unicode, folding, stemming, and n-grams.
- [Built-in Language Analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/language/): language-specific analyzers.
- [String Field Type](https://www.mongodb.com/docs/search/indexes/field-types/string-type/): `analyzer`, `searchAnalyzer`, `multi`, and `indexOptions`.
- [Token Field Type](https://www.mongodb.com/docs/search/indexes/field-types/token-type/): exact/facet/sort and `normalizer`.
- [Multi Analyzer](https://www.mongodb.com/docs/search/indexes/analyzers/multi/): alternate analysis for string fields.
- [Autocomplete Field Type](https://www.mongodb.com/docs/search/indexes/field-types/autocomplete-type/): `edgeGram`/`nGram` and suggestion configuration.
- [`text` Search Operator](https://www.mongodb.com/docs/search/query/operators-collectors/text/): full-text, fuzzy, and synonyms.
- [`autocomplete` Search Operator](https://www.mongodb.com/docs/search/query/operators-collectors/autocomplete/): prefix and partial-match queries.
- [Score Details](https://www.mongodb.com/docs/search/query/score/get-details/): scoring and contributing factors.
- [Unicode Normalization Forms](https://unicode.org/reports/tr15/): NFC/NFD/NFKC/NFKD.
- [Java MongoDB Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/): building and executing pipelines in Java.

Note: field types, Search node/`mongot` deployment models, and index management methods continue to evolve across MongoDB releases. Always verify **server, driver, Atlas/self-managed setup, Search release, and FCV** before applying examples in production.

## 43. Conclusion

A **Search index** is specialized infrastructure for MongoDB lexical text search, independent of B-tree and legacy `$text` indexes. MongoDB Search executes queries via `$search`, supporting `text`, `phrase`, `fuzzy`, `autocomplete`, scoring, and filtering operators. In Search-enabled deployments, indexes are maintained by `mongot` and can update asynchronously.

**Analyzers** govern how strings become terms; **tokenizers** establish token boundaries; **character filters** normalize text prior to tokenization; **token filters** transform emitted tokens afterward. **Index analyzers** and **search analyzers** must emit compatible terms. For exact-match, faceting, and sorting fields, **`token` types and normalizers** serve a fundamentally different role from `string` full-text analyzers.

For Vietnamese, distinguish **case folding**, **Unicode normalization**, **accent folding**, and **word segmentation**. Stripping accents boosts recall at the cost of precision, so combining an accent-preserving path with a boosted folded path is often necessary. Product codes, proper nouns, and compound words require dedicated testing.

**Strong Search engineering does more than return hits—it ensures linguistic accuracy, strict tenant isolation, useful relevance ranking, predictable latency, and safe analyzer evolution as data changes.**
