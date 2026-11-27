# Searching with $regex and Index-Friendly Conditions in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Text Search

## 1. Problem Statement and Goals

An e-commerce application allows users to search for products by name or SKU. Common requirements include:

- SKU **starts** with `PH`.
- Name **contains** `phone` at any position.
- SKU **ends** with `-VN`.
- Name starts with `phone` in a **case-insensitive** manner.
- Literal codes containing a dot or plus sign, such as `AB.42` or `C++`.

These can be expressed using regex:

~~~javascript
db.products.find({ sku: /^PH/ });
db.products.find({ name: /phone/ });
db.products.find({ sku: /-VN$/ });
db.products.find({ name: /^phone/i });
~~~

However, these regex patterns **do not share the same ability to leverage a B-tree index**.

**Core principle:** A **case-sensitive** regex anchored at the start of the string with `^` or `\A` and **immediately followed by a simple literal prefix** allows MongoDB to construct a narrow index scan range. Contains regexes, suffix regexes, leading wildcards, or patterns using the `i` flag generally do not receive the same benefit.

This lesson helps you:

1. Use `$regex` and `$options` with proper syntax.
2. Distinguish between exact, prefix, contains, and suffix matches.
3. Know which conditions form a **prefix expression** capable of using an index range.
4. Read `explain("executionStats")` and understand that `IXSCAN` does not automatically mean a fast query.
5. Combine equality filters with regex in a compound index.
6. Understand why a case-insensitive collation index does not automatically optimize an `i`-flagged regex.
7. Choose a normalized field when case-insensitive prefix search is required.
8. Escape user input and control CPU-intensive regexes.
9. Practice using the MongoDB Java Sync Driver.
10. Know when to use a text index or MongoDB Search instead.

## 2. Regex Is String Pattern Matching, Not Semantic Search

The `$regex` operator is a query predicate that checks whether a string matches a *regular expression*.

~~~javascript
db.products.find({
  name: { $regex: "phone" }
});
~~~

This can match `phone case`, `smartphone cover`, `headphone`, or `new phone stand`.

~~~javascript
db.products.find({
  name: { $regex: "^phone" }
});
~~~

This only matches strings starting with `phone` under standard regex mode.

Regex **does not** natively provide:

- Vietnamese word segmentation and synonym understanding.
- Fuzzy matching for typos.
- Stemming, tokenization, or language analyzers.
- Relevance scoring and sorting by relevance.
- Vietnamese diacritic/accent removal.
- Searching for a word inside the middle of text with the same performance as a prefix index.

### 2.1. Basic Regex Syntax

| Pattern | Meaning |
|---|---|
| `/^PH/` | Starts with PH |
| `/PH/` | Contains PH at any position |
| `/PH$/` | Ends with PH |
| `/^PH$/` | Matches the entire string PH |
| `/^PH-\d{3}$/` | PH- followed by three digits |
| `/^PH[0-9]/` | Starts with PH followed by one digit |
| `/^P[Hh]/` | Starts with P followed by H or h |
| `/^(PH|TAB)/` | Starts with PH or TAB |
| `/^phone/i` | Starts with phone, case-insensitive |
| `/\bphone\b/` | Matches word boundary according to the regex engine |

The characters `.`, `*`, `+`, `?`, `[ ]`, `( )`, `|`, `^`, `$`, and `\` all have special roles. Only use them as regex operators when the user **genuinely requests regex matching**.

## 3. Two Ways to Write $regex in mongosh

### 3.1. Regex Literal Form

~~~javascript
db.products.find({ sku: /^PH/ });

db.products.find({
  sku: { $regex: /^PH/ }
});
~~~

### 3.2. String Form

~~~javascript
db.products.find({
  sku: { $regex: "^PH" }
});

db.products.find({
  name: {
    $regex: "^phone",
    $options: "i"
  }
});
~~~

The string form is convenient when constructing queries at runtime or using PCRE2 syntax that cannot be represented as a JavaScript RegExp literal.

### 3.3. Common Options

| Flag | Meaning | Trade-off |
|---|---|---|
| `i` | Case-insensitive | Lacks the same case-sensitive prefix advantage |
| `m` | Multiline, `^`/`$` can match line boundaries | Anchors are no longer restricted to the start of the whole string |
| `s` | Dot-all, `.` matches newline | Unnecessary for simple prefix matching |
| `x` | Ignores certain whitespace and regex comments | Requires care if the pattern contains literal whitespace |

~~~javascript
db.products.find({
  description: {
    $regex: "phone.*case",
    $options: "is"
  }
});
~~~

### 3.4. Escaping When the Pattern Is a JavaScript String

~~~javascript
// Regex literal.
db.products.find({ sku: /^PH-\d+/ });

// In a string, the backslash must be escaped.
db.products.find({
  sku: { $regex: "^PH-\\d+" }
});
~~~

MongoDB Server uses **PCRE2 starting in version 6.1**. Some PCRE2 constructs may differ from JavaScript regexes; therefore, do not automatically convert every JavaScript RegExp into an advanced PCRE2 expression and expect identical semantics.

Example of a PCRE2 pattern string with scoped case-insensitivity:

~~~javascript
db.products.find({
  sku: { $regex: "(?i)ph(?-i)-100" }
});
~~~

Just because a regex is supported by PCRE2 **does not mean it can produce index prefix bounds**.

## 4. Practice Dataset

Open `mongosh` on a MongoDB instance you have permission to use and select a dedicated lab database:

~~~javascript
const lab = db.getSiblingDB("regex_index_lab");
const products = lab.getCollection("products");

products.insertMany([
  {
    _id: 1, tenantId: "t1", status: "ACTIVE",
    sku: "PH-100", name: "Phone Case",
    nameLower: "phone case", category: "accessory"
  },
  {
    _id: 2, tenantId: "t1", status: "ACTIVE",
    sku: "PH-101", name: "Phone Charger",
    nameLower: "phone charger", category: "accessory"
  },
  {
    _id: 3, tenantId: "t1", status: "ACTIVE",
    sku: "PH-102", name: "Phone Stand",
    nameLower: "phone stand", category: "accessory"
  },
  {
    _id: 4, tenantId: "t1", status: "ACTIVE",
    sku: "TAB-100", name: "Tablet Stand",
    nameLower: "tablet stand", category: "accessory"
  },
  {
    _id: 5, tenantId: "t1", status: "ARCHIVED",
    sku: "PH-200", name: "Phone Case Old",
    nameLower: "phone case old", category: "accessory"
  },
  {
    _id: 6, tenantId: "t1", status: "ACTIVE",
    sku: "XPH-300", name: "Smartphone Cover",
    nameLower: "smartphone cover", category: "accessory"
  },
  {
    _id: 7, tenantId: "t1", status: "ACTIVE",
    sku: "PH-VN", name: "iPhone 15",
    nameLower: "iphone 15", category: "device"
  },
  {
    _id: 8, tenantId: "t1", status: "ACTIVE",
    sku: "ph-103", name: "iphone Mini",
    nameLower: "iphone mini", category: "device"
  },
  {
    _id: 9, tenantId: "t1", status: "ACTIVE",
    sku: "LAP-VN", name: "Laptop Pro",
    nameLower: "laptop pro", category: "device"
  },
  {
    _id: 10, tenantId: "t1", status: "ACTIVE",
    sku: "AB.42", name: "Cable USB-C",
    nameLower: "cable usb-c", category: "accessory"
  },
  {
    _id: 11, tenantId: "t2", status: "ACTIVE",
    sku: "PH-100", name: "Phone Case",
    nameLower: "phone case", category: "accessory"
  },
  {
    _id: 12, tenantId: "t2", status: "ACTIVE",
    sku: "PH-900", name: "phone headset",
    nameLower: "phone headset", category: "accessory"
  },
  {
    _id: 13, tenantId: "t2", status: "ACTIVE",
    sku: "TAB-500", name: "Tablet",
    nameLower: "tablet", category: "device"
  },
  {
    _id: 14, tenantId: "t1", status: "ACTIVE",
    sku: "VN-PH", name: "Headphone",
    nameLower: "headphone", category: "device"
  },
  {
    _id: 15, tenantId: "t1", status: "ACTIVE",
    sku: "NOTE-01", name: "Điện thoại phổ thông",
    nameLower: "điện thoại phổ thông", category: "device"
  },
  {
    _id: 16, tenantId: "t1", status: "ACTIVE",
    sku: "NOTE-02", name: "Điện Thoại Thông Minh",
    nameLower: "điện thoại thông minh", category: "device"
  },
  {
    _id: 17, tenantId: "t1", status: "ACTIVE",
    sku: "PH-777", name: "Phone Grip",
    nameLower: "phone grip", category: "accessory"
  },
  {
    _id: 18, tenantId: "t1", status: "ACTIVE",
    sku: "CASE-PH", name: "New phone case",
    nameLower: "new phone case", category: "accessory"
  }
]);

print("Products:", products.countDocuments({}));
~~~

The sample dataset has **18 documents**. Run the data seeding script only once on an empty lab database; running it again will cause duplicate key errors on `_id`. Never run `dropDatabase()` on production data or shared databases to reset the exercise.

### 4.1. Create the Indexes

~~~javascript
products.createIndex(
  { sku: 1 },
  { name: "idx_sku" }
);
products.createIndex(
  { name: 1 },
  { name: "idx_name" }
);
products.createIndex(
  { nameLower: 1 },
  { name: "idx_name_lower" }
);
products.createIndex(
  { tenantId: 1, status: 1, sku: 1 },
  { name: "idx_tenant_status_sku" }
);

printjson(products.getIndexes());
~~~

These are **candidate indexes for the lab**. Do not copy all of them into production blindly: every index increases write overhead and storage usage.

## 5. Prefix Expression: When Can a Regex Leverage a B-Tree Index Range?

MongoDB documentation describes a **prefix expression** as a regex that:

1. Starts with the anchor `^` or `\A`.
2. Is followed by a **simple, fixed** character sequence that every matching string must start with.

Example:

~~~javascript
products.find({ sku: /^PH/ });
~~~

With the index `{sku:1}`, MongoDB can derive an **index range** for keys starting with `PH`.

### 5.1. Visualizing an Ordered Index

~~~text
AB.42
CASE-PH
LAP-VN
NOTE-01
NOTE-02
PH-100       ┐
PH-101       │
PH-102       │  Key range with prefix PH
PH-200       │
PH-777       │
PH-900       │
PH-VN        ┘
TAB-100
VN-PH
XPH-300
ph-103
~~~

A B-tree index stores values in sorted order, so it can read a contiguous range instead of scanning every key.

Do not manually construct an upper bound by incrementing the last character by one. MongoDB and its query planner have their own bound-generation mechanism depending on index type, collation, pattern, and server version.

### 5.2. ^ Is an Anchor, but ^ Alone Is Not Enough

~~~javascript
// Has an explicit PH prefix.
products.find({ sku: /^PH/ });

// The ^ anchor is present, but the beginning is arbitrarily consumed by .*.
products.find({ sku: /^.*PH/ });
~~~

The second regex **does not require** the SKU to start with PH; it can match `XPH-300` or `CASE-PH`. Therefore, there is no common PH prefix to form the same index range.

### 5.3. \A in PCRE

The `\A` symbol anchors to the start of the entire string. When using it in `mongosh`, choose the string pattern form:

~~~javascript
products.find({
  sku: { $regex: "\\APH" }
});
~~~

The JavaScript string `"\\APH"` represents the PCRE pattern `\APH` after string escaping. Do not confuse it with a regex literal, which the JavaScript parser interprets under JavaScript RegExp rules.

### 5.4. Regex Forms and Prefix Derivability

| Regex | Fixed Prefix | Index Implications |
|---|---|---|
| `/^PH/` | PH | Good candidate |
| `/^PH-10/` | PH-10 | Potentially more selective range |
| `/^PH.*/` | PH | Can use bounds, but does extra work |
| `/^PH.*$/` | PH | May have bounds; trailing part is usually unnecessary |
| `/^PH[0-9]/` | PH | Must additionally check the digit |
| `/^P[Hh]/` | P | Shorter literal prefix |
| `/^.*PH/` | Not useful | Wildcard precedes the literal |
| `/PH/` | None | Contains |
| `/PH$/` | None | Suffix |
| `/^ph/i` | Anchored, but case-insensitive | Does not receive the same prefix optimization |
| `/^(PH|TAB)/` | Multiple branches | Do not assume optimization like a single prefix |
| `/^[A-Z]+PH/` | No concrete leading literal | Do not expect narrow prefix bounds |

**Note:** A regex without a literal prefix may still be routed through an `IXSCAN` by the planner to inspect many index entries. The difference is **whether it can scan a narrow range**, not merely whether "an index is mentioned."

## 6. Why Is /^a/ Better Than /^a.*/ and /^a.*$/?

MongoDB documentation highlights three expressions:

~~~javascript
/^a/
/^a.*/
/^a.*$/
~~~

For typical single-line values, they may match the same strings starting with `a`, yet they have **different performance characteristics**.

- `/^a/` directly expresses a prefix condition; evaluation can stop once keys fall outside the range.
- `/^a.*/` adds a `.*` part that a `startsWith` check does not need.
- `/^a.*$/` also expresses matching up to the end of the string, offering no benefit for a simple prefix goal.

Therefore:

~~~javascript
// Prefer this when you only need startsWith.
products.find({ sku: /^PH/ });

// No need to append .* just to match longer SKUs.
products.find({ sku: /^PH.*/ });
~~~

The regex `/^PH/` already matches `PH-100`; there is no requirement that the entire string consist solely of PH.

**Caution:** Newlines or the `m` or `s` options can change the semantics of `.`, `^`, and `$`. The recommendation above applies to single-line code/name strings and prefix search goals.

## 7. Contains and Suffix: Why Is a B-Tree Less Helpful?

### 7.1. Contains

~~~javascript
products.find({ sku: /PH/ });
~~~

This can match:

- `PH-100`.
- `XPH-300`.
- `VN-PH`.
- `CASE-PH`.

These values do not start with the same literal, so a B-tree ordered from the start of the string cannot form a single contiguous range like `/^PH/`.

### 7.2. Suffix

~~~javascript
products.find({ sku: /-VN$/ });
~~~

This can match `PH-VN` and `LAP-VN`. Strings sharing the same suffix do not necessarily sit next to each other in an index built on the full SKU.

### 7.3. Reversed Field Technique for Suffix Queries

If suffix searches are frequent, you can store the reversed value:

~~~javascript
{
  sku: "LAP-VN",
  skuReversed: "NV-PAL"
}
~~~

Create an index `{skuReversed:1}` and query:

~~~javascript
products.find({
  skuReversed: /^NV-/
});
~~~

Drawbacks:

- Additional field and index.
- Must be updated whenever the SKU changes.
- Must handle Unicode/code points properly if values are not strictly ASCII.
- Not helpful if users primarily need full-text or fuzzy search.

This is a deliberate data modeling solution, not a built-in feature of regex.

## 8. Exact Match: Prefer Equality

For the exact SKU `PH-100`:

~~~javascript
products.find({ sku: "PH-100" });
~~~

is generally clearer and more appropriate than:

~~~javascript
products.find({ sku: /^PH-100$/ });
~~~

Equality uses direct equality bounds, avoids invoking the regex engine, and integrates cleanly with compound and unique indexes.

If case-insensitive equality is needed, you can use an appropriate collation or a normalized key.

## 9. The i Flag and Case-Insensitive Indexes Are Two Different Things

### 9.1. Case-Sensitive

~~~javascript
products.find({ name: /^Phone/ });
~~~

Matches `Phone Case` but does not automatically match `phone headset`.

### 9.2. Case-Insensitive

~~~javascript
products.find({ name: /^phone/i });
~~~

Matches more casing variants but does not receive the same **literal prefix bounds** advantage as a case-sensitive regex.

### 9.3. A Collation Index Does Not Automatically Optimize $regex

Suppose you create this index:

~~~javascript
products.createIndex(
  { name: 1 },
  {
    name: "idx_name_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Equality with the matching collation:

~~~javascript
products.find({
  name: "phone case"
}).collation({
  locale: "en",
  strength: 2
});
~~~

can use the appropriate index.

However, a regex:

~~~javascript
products.find({
  name: /^phone/i
}).collation({
  locale: "en",
  strength: 2
});
~~~

**does not automatically gain prefix optimization from a case-insensitive collation index**. MongoDB documentation emphasizes that regexes are not collation-aware, so case-insensitive indexes do not speed up regex queries the way users often assume.

### 9.4. Normalized Search Field

When an application primarily needs case-insensitive prefix autocomplete, you can store:

~~~javascript
{
  name: "Phone Charger",
  nameLower: "phone charger"
}
~~~

Create the index:

~~~javascript
products.createIndex({ nameLower: 1 });
~~~

Query with a case-sensitive regex on the normalized key:

~~~javascript
products.find({ nameLower: /^pho/ });
~~~

Your process must:

- Generate `nameLower` using the same rule on insert and update.
- Normalize user input with the exact same algorithm.
- Backfill existing data.
- Account for Unicode, locale, and accent-insensitivity separately.
- Evaluate the cost of the extra field and index.

## 10. Vietnamese and Unicode

The `i` flag does not remove diacritics:

~~~javascript
products.find({
  name: /dien thoai/i
});
~~~

will not match `Điện thoại phổ thông` by default.

It is important to distinguish:

1. **Case-insensitive**: `Phone` and `phone`.
2. **Accent-insensitive**: `điện` and `dien`.
3. **Unicode normalization**: visually identical characters encoded differently.
4. **Word segmentation**: identifying word/phrase boundaries.
5. **Fuzzy search**: handling typos.

If your product requires Vietnamese accent-insensitive matching, design a consistent searchable key or Search analyzer; do not assume `toLowerCase()` or `/i` solves every case.

MongoDB 6.1+ supports certain PCRE2 Unicode options such as `(*UCP)`, which carry extra processing overhead. Example in a pattern string:

~~~javascript
products.find({
  name: { $regex: "(*UCP)\\bphone\\b" }
});
~~~

Unicode word boundaries do not equate to Vietnamese word segmentation or synonym handling.

## 11. Equality + Prefix in a Compound Index

An API often needs to filter by tenant, status, and then SKU prefix:

~~~javascript
products.find({
  tenantId: "t1",
  status: "ACTIVE",
  sku: /^PH/
});
~~~

Candidate index:

~~~javascript
products.createIndex(
  { tenantId: 1, status: 1, sku: 1 },
  { name: "idx_tenant_status_sku" }
);
~~~

For this query:

- `tenantId` is an equality predicate.
- `status` is an equality predicate.
- `sku` can produce a prefix range.

This is a favorable pattern for indexing equality fields first, followed by the range field.

### 11.1. Leading Fields Matter

The index `{tenantId:1,status:1,sku:1}` is not as directly suitable as `{sku:1}` for:

~~~javascript
products.find({ sku: /^PH/ });
~~~

because the query omits equality predicates on the leading fields.

If there are system-wide SKU queries, you may need a separate `{sku:1}` index; weigh the write overhead and workload.

### 11.2. Without the Status Condition

~~~javascript
products.find({
  tenantId: "t1",
  sku: /^PH/
});
~~~

The index places `status` between `tenantId` and `sku`, leaving `status` unconstrained. You might need a `{tenantId:1,sku:1}` index if this is a hot query. Avoid creating countless indexes for every possible combination.

### 11.3. Overly Short Prefixes

The regex `/^P/` may match the majority of products. **Indexable** does not mean **selective**. If a prefix is too common, the index range can still be huge, and a collection scan might even be cheaper.

### 11.4. Sort

~~~javascript
products.find({
  tenantId: "t1",
  status: "ACTIVE",
  sku: /^PH/
}).sort({ sku: 1 }).limit(20);
~~~

A compound index can support both filtering and sorting when key ordering aligns. However, if you sort by another field after the regex range, do not assume that appending that field to the index will always eliminate an in-memory sort across all results.

## 12. $or, $in, $not, and Multiple Regexes

### 12.1. Two Different Prefixes

~~~javascript
products.find({
  tenantId: "t1",
  $or: [
    { sku: /^PH/ },
    { sku: /^TAB/ }
  ]
});
~~~

MongoDB can plan each branch if a suitable index exists, though you should verify with explain.

A combined regex:

~~~javascript
products.find({
  sku: /^(PH|TAB)/
});
~~~

does not automatically produce two efficient ranges the way an explicit `$or` query can.

### 12.2. $in Accepts Regex Literals

~~~javascript
products.find({
  sku: {
    $in: [/^PH/, /^TAB/]
  }
});
~~~

However, do not place `{$regex:"..."}` objects inside an `$in` array in place of regex literals:

~~~javascript
// Not a supported $in regex form.
products.find({
  sku: {
    $in: [
      { $regex: "^PH" },
      { $regex: "^TAB" }
    ]
  }
});
~~~

When you need string-form `$regex` with `$options`, use `$or` for each predicate.

### 12.3. $not

~~~javascript
products.find({
  sku: { $not: /^PH/ }
});
~~~

A negated condition can return nearly the entire collection and is typically not selective. Do not treat a negative regex as index-efficient merely because it has an anchor.

### 12.4. Two Regexes on the Same Field

~~~javascript
products.find({
  $and: [
    { sku: /^PH/ },
    { sku: /VN$/ }
  ]
});
~~~

The planner may use the prefix to narrow candidates and apply the suffix regex as a residual filter. Do not expect both together to automatically form a single exact index range.

## 13. $regex in Aggregation Differs from $regexMatch

A predicate inside `$match`:

~~~javascript
products.aggregate([
  {
    $match: {
      tenantId: "t1",
      sku: /^PH/
    }
  },
  {
    $project: { sku: 1, name: 1 }
  }
]);
~~~

can be pushed down by the optimizer to an index scan when the pipeline qualifies.

By contrast, `$regexMatch` is an aggregation expression that evaluates to a boolean:

~~~javascript
products.aggregate([
  {
    $project: {
      sku: 1,
      startsWithPH: {
        $regexMatch: {
          input: "$sku",
          regex: "^PH"
        }
      }
    }
  }
]);
~~~

If you only need to filter documents, do not assume that:

~~~javascript
{
  $match: {
    $expr: {
      $regexMatch: {
        input: "$sku",
        regex: "^PH"
      }
    }
  }
}
~~~

is equivalent in index optimization to:

~~~javascript
{ $match: { sku: /^PH/ } }
~~~

Similarly, computing `$toLower: "$name"` inside a pipeline does not turn an index on `name` into an index on the lowercased output.

## 14. Reading explain("executionStats")

~~~javascript
const result = products.find({
  sku: /^PH/
}).explain("executionStats");

printjson(result.queryPlanner);
printjson(result.executionStats);
~~~

Key metrics to inspect:

| Metric | Interpretation |
|---|---|
| `IXSCAN` | Index scan occurred |
| `COLLSCAN` | Collection scan occurred |
| `FETCH` | Retrieves documents after index filtering |
| `indexBounds` | Range of index values examined |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of documents returned |
| `executionTimeMillis` | Reported execution time |
| `winningPlan` | Selected execution plan |

### 14.1. Three-Case Experiment

~~~javascript
const tests = [
  ["prefix", /^PH/],
  ["contains", /PH/],
  ["insensitive", /^ph/i]
];

for (const [label, pattern] of tests) {
  const exp = products.find({
    sku: pattern
  }).explain("executionStats");

  printjson({
    label: label,
    nReturned: exp.executionStats.nReturned,
    keys: exp.executionStats.totalKeysExamined,
    docs: exp.executionStats.totalDocsExamined,
    millis: exp.executionStats.executionTimeMillis
  });
}
~~~

**Do not draw production performance conclusions from 18 documents.** The query planner may choose `COLLSCAN` simply because the dataset is tiny.

### 14.2. Having IXSCAN Is Not Enough

A contains query `/PH/` may scan most of the index to test every key, whereas `/^PH/` can scan a narrow prefix range.

Read **bounds and keysExamined**, not just the stage name. Explain JSON output also varies between the classic engine, Slot-Based Execution (SBE), and server versions.

### 14.3. Hint Is for Investigation Only

~~~javascript
products.find({
  sku: /^PH/
}).hint("idx_sku").explain("executionStats");

products.find({
  sku: /PH/
}).hint("idx_sku").explain("executionStats");
~~~

A hint forces a specific index plan for inspection; it does not prove that plan is optimal. Use hints cautiously in production.

## 15. Benchmarking on Larger Data

An 18-document collection is insufficient for latency comparisons. In the lab database, you can generate 20,000 products:

~~~javascript
const bench = lab.getCollection("products_bench");
const batch = [];

for (let i = 0; i < 20000; i++) {
  const prefix = i % 50 === 0 ? "PH" : "ITEM";

  batch.push({
    _id: i,
    tenantId: "t" + (i % 20),
    status: i % 7 === 0 ? "ARCHIVED" : "ACTIVE",
    sku: prefix + "-" + String(i).padStart(7, "0"),
    name: prefix === "PH" ? "Phone Sample " + i : "Item " + i
  });
}

bench.insertMany(batch);
bench.createIndex({ sku: 1 });
bench.createIndex({ tenantId: 1, status: 1, sku: 1 });
~~~

Then run:

~~~javascript
bench.find({ sku: /^PH/ }).explain("executionStats");
bench.find({ sku: /PH/ }).explain("executionStats");
bench.find({ sku: /^ph/i }).explain("executionStats");
~~~

Evaluate:

- Do the queries return the same results?
- Keys examined relative to nReturned?
- Docs examined?
- Index bounds?
- Query latency across multiple runs, warm vs. cold cache?
- CPU/I/O and realistic prefix distribution?

Do not compare `executionTimeMillis` from a single run and draw conclusions.

## 16. Escaping User Input

An SKU search box normally accepts **literal text**, not a regex pattern.

If a user types:

~~~text
AB.42
~~~

and the code concatenates:

~~~javascript
const pattern = "^" + userInput;
~~~

then the `.` means "any single character"; the regex could match `ABX42`.

### 16.1. Literal Escape Function

~~~javascript
function escapeRegexLiteral(value) {
  return value.replace(/[.*+?^{}()|[\]\\$]/g, "\\$&");
}

const raw = "AB.42";
const pattern = "^" + escapeRegexLiteral(raw);

print(pattern); // ^AB\.42

products.find({
  sku: { $regex: pattern }
});
~~~

Inputs like `C++` or `foo(bar)` must also be escaped when the goal is literal matching.

### 16.2. Length Validation

~~~javascript
function validatePrefix(input) {
  if (typeof input !== "string") {
    throw new Error("Prefix must be a string");
  }

  const value = input.trim();

  if (value.length < 1 || value.length > 64) {
    throw new Error("Prefix length must be 1..64");
  }

  return value;
}
~~~

64 is purely an illustrative policy. With Unicode, the count of UTF-16 code units may differ from the number of characters visible to the user.

### 16.3. Guarding Against CPU-Intensive Regexes

Patterns with nested quantifiers such as:

~~~text
^(a+)+$
~~~

can trigger CPU-heavy backtracking on certain long strings. Do not let a public API accept arbitrary regexes and run them across millions of documents without risk controls.

Mitigations:

- Expose a literal prefix API instead of raw regex.
- Escape metacharacters.
- Restrict length and complexity.
- Set query timeouts and `maxTimeMS`.
- Limit result counts.
- Apply rate limiting and monitoring.
- Switch to Search when requirements outgrow B-tree regexes.

Example:

~~~javascript
products.find({ sku: /^PH/ })
  .limit(20)
  .maxTimeMS(500);
~~~

A timeout is an **execution error**, not "no results found."

## 17. Case-Insensitive Prefix Search API

Suppose we have an endpoint:

~~~text
GET /api/products?prefix=Pho&limit=20
~~~

Requirements:

1. Tenant comes from the security context.
2. Input is treated as a literal.
3. Case-insensitive matching via a normalized key.
4. Return only ACTIVE products.
5. Results include limit, sort, and timeout.

### 17.1. Data and Index

~~~javascript
{
  name: "Phone Charger",
  nameLower: "phone charger",
  tenantId: "t1",
  status: "ACTIVE"
}
~~~

Candidate index:

~~~javascript
products.createIndex(
  { tenantId: 1, status: 1, nameLower: 1, _id: 1 },
  { name: "idx_tenant_status_name_lower" }
);
~~~

Do not assume `_id` is always needed at the end of the index; it is only a candidate for a sort tie-breaker, and its cost must be evaluated.

### 17.2. Query

~~~javascript
function escapeRegexLiteral(value) {
  return value.replace(/[.*+?^{}()|[\]\\$]/g, "\\$&");
}

function searchProducts(tenantId, rawPrefix) {
  if (typeof rawPrefix !== "string") {
    throw new Error("Missing prefix");
  }

  const prefix = rawPrefix.trim().normalize("NFC").toLowerCase();

  if (prefix.length < 2 || prefix.length > 64) {
    throw new Error("Invalid prefix length");
  }

  const pattern = "^" + escapeRegexLiteral(prefix);

  return db.getSiblingDB("regex_index_lab")
    .products
    .find({
      tenantId: tenantId,
      status: "ACTIVE",
      nameLower: { $regex: pattern }
    })
    .sort({ nameLower: 1, _id: 1 })
    .limit(20)
    .maxTimeMS(500)
    .toArray();
}

printjson(searchProducts("t1", "Pho"));
~~~

This is a technical illustration, not a complete authorization template; the backend must enforce tenant permissions independently.

### 17.3. Maintaining the Derived Field

When updating the name:

~~~javascript
products.updateOne(
  { _id: 2, tenantId: "t1" },
  {
    $set: {
      name: "Phone Adapter",
      nameLower: "phone adapter"
    }
  }
);
~~~

Updating both fields in the same document operation prevents the searchable key from going stale. Existing data must be backfilled before switching the API to `nameLower`.

## 18. Regex on Arrays, Nested Fields, and Non-Strings

### 18.1. String Arrays

~~~javascript
products.insertOne({
  _id: 99,
  tenantId: "t1",
  status: "ACTIVE",
  sku: "PACK-99",
  name: "Gift Pack",
  tags: ["phone-accessory", "gift", "portable"]
});

products.find({
  tags: /^phone/
});
~~~

This can match if any string element in the array satisfies the regex. An index on `tags` is a multikey index and requires understanding specific multikey bounds rules.

### 18.2. Nested Fields

~~~javascript
products.find({
  "manufacturer.name": /^Sony/
});

products.createIndex({
  "manufacturer.name": 1
});
~~~

An index on `name` does not automatically cover `manufacturer.name`.

### 18.3. Non-Strings

Regex does not automatically convert numbers or Dates into strings. If numeric codes require prefix lookup, store a string searchable key or use numeric operators when business logic calls for them.

## 19. Java Sync Driver: Filters.regex()

### 19.1. Complete Example

Assuming dependency `org.mongodb:mongodb-driver-sync`:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import static com.mongodb.client.model.Filters.regex;
import static com.mongodb.client.model.Sorts.ascending;

public final class RegexPrefixExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            uri = "mongodb://127.0.0.1:27017";
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("regex_index_lab");
            MongoCollection<Document> products = db.getCollection("products");

            Bson filter = regex("sku", "^PH");

            for (Document doc : products.find(filter)
                    .sort(ascending("sku"))
                    .limit(20)) {
                System.out.println(doc.toJson());
            }
        }
    }
}
~~~

### 19.2. Regex Options

~~~java
import static com.mongodb.client.model.Filters.regex;

Bson sensitive = regex("name", "^Phone");
Bson insensitive = regex("name", "^phone", "i");
~~~

Adding `i` does not turn it into a case-sensitive prefix range index query.

### 19.3. Java Pattern

~~~java
import java.util.regex.Pattern;
import static com.mongodb.client.model.Filters.regex;

Pattern pattern = Pattern.compile("^PH");
Bson filter = regex("sku", pattern);
~~~

Be careful, as Java regex syntax and server-side PCRE2 can differ for advanced constructs.

### 19.4. Escaping User Input with Pattern.quote

~~~java
import java.util.regex.Pattern;
import static com.mongodb.client.model.Filters.regex;

String userPrefix = "AB.42";
String safeRegex = "^" + Pattern.quote(userPrefix);
Bson filter = regex("sku", safeRegex);
~~~

`Pattern.quote()` typically produces `\Q...\E` for literal matching. PCRE2 supports this quoting mechanism in appropriate contexts. Never pass raw input when the UI only intends literal prefix matching.

### 19.5. Java Service with a Normalized Field

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.regex;

public final class ProductPrefixService {
    private final MongoCollection<Document> products;

    public ProductPrefixService(MongoCollection<Document> products) {
        this.products = products;
    }

    public List<Document> search(
            String tenantId,
            String rawPrefix,
            int maxResults) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (rawPrefix == null) {
            throw new IllegalArgumentException("Missing prefix");
        }

        String prefix = Normalizer.normalize(
                rawPrefix.trim(), Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT);

        if (prefix.length() < 2 || prefix.length() > 64) {
            throw new IllegalArgumentException("Invalid prefix length");
        }

        int limit = Math.max(1, Math.min(50, maxResults));

        Bson filter = and(
                eq("tenantId", tenantId),
                eq("status", "ACTIVE"),
                regex("nameLower", "^" + Pattern.quote(prefix))
        );

        return products.find(filter)
                .limit(limit)
                .into(new ArrayList<>());
    }
}
~~~

Production applications need authorization, timeouts, rate limiting, and consistent normalization rules across all writes and updates.

### 19.6. Explain from Java

~~~java
import com.mongodb.ExplainVerbosity;
import org.bson.Document;

Document explain = products.find(regex("sku", "^PH"))
        .explain(ExplainVerbosity.EXECUTION_STATS);

System.out.println(explain.toJson());
~~~

Setting a time limit:

~~~java
import java.util.concurrent.TimeUnit;

for (Document row : products.find(regex("sku", "^PH"))
        .limit(20)
        .maxTime(500, TimeUnit.MILLISECONDS)) {
    System.out.println(row.toJson());
}
~~~

## 20. Sharding, Tenant Isolation, and Two Optimization Layers

On a sharded collection, distinguish between:

- **Shard targeting:** `mongos` decides which shards will receive the query.
- **Index filtering:** each shard applies its index/range to its local data.

~~~javascript
products.find({
  sku: /^PH/
});
~~~

If the shard key involves `tenantId` and the query omits `tenantId`, it may have to scatter-gather across multiple shards.

~~~javascript
products.find({
  tenantId: "t1",
  sku: /^PH/
});
~~~

When constrained appropriately by the shard key, the router can target shards much more effectively.

A prefix regex with an index on each shard **does not automatically guarantee a single-shard query**. At the same time, `tenantId` must be verified from the security context; never omit it merely to shorten the query.

## 21. When Should You Avoid $regex?

| Requirement | Solution to Consider |
|---|---|
| Exact SKU lookup | Equality + B-tree |
| Starts with literal, case-sensitive | Anchored `$regex` + B-tree |
| Starts with literal, case-insensitive | Normalized indexed field or MongoDB Search |
| Large-scale substring contains | MongoDB Search or a search engine |
| Frequent suffix matching | Reversed key or Search |
| Word-based full-text search | `$text`/text index or Search |
| Fuzzy, typo tolerance, autocomplete | Search with appropriate analyzer/operator |
| Relevance, synonyms, stemming | Search engine |
| Admin-entered regex patterns | `$regex` with resource/permission controls |

### 21.1. $text Differs from $regex

~~~javascript
products.createIndex({ name: "text" });

products.find({
  $text: { $search: "phone" }
});
~~~

A text index follows its own tokenization, stemming, and stop-word rules; it is not a B-tree for prefix regexes and does not solve arbitrary substring lookups.

### 21.2. MongoDB Search

MongoDB Search / Atlas Search uses a **search index** with semantics distinct from collection-level `$regex`. It is better suited for fuzzy matching, autocomplete, phrase queries, full-text ranking, and multi-field search.

Do not use Search regex/wildcard syntax and assume B-tree `$regex` delivers the same performance.

## 22. Common Design Mistakes

| Mistake | Problem | Solution |
|---|---|---|
| `/PH/` for startsWith | No fixed literal prefix at start | `/^PH/` if aligned with requirements |
| `/^.*PH/` believing `^` is enough | Wildcard consumes start of string | Remove wildcard when only prefix is needed |
| `/^PH.*$/` when only startsWith is needed | Unnecessary regex work | Use `/^PH/` |
| `/^ph/i` + case-insensitive index | Regex is not collation-aware | Normalized field / Search |
| Regex for exact SKU | Unnecessary regex engine overhead | Equality |
| Concatenating raw input | Wrong matches / regex abuse | Escape literals |
| Allowing arbitrary regex in public API | ReDoS / CPU spikes | Limit length, pattern, and timeout |
| Assuming IXSCAN means optimal | Could be a full index scan | Inspect bounds and keysExamined |
| Benchmarking on 18 docs | Not representative | Benchmark against realistic workloads |
| Treating `$regexMatch` as an indexed predicate | Computed expression may prevent pushdown | Use `$match` directly where appropriate |
| Assuming `i` strips Vietnamese accents | Incorrect semantics | Normalization / search analyzer |
| Missing tenant filter | Data leak risk / scatter-gather | Authentication + predicate |
| Creating too many indexes | High write/storage cost | Design around actual query patterns |
| Regex on numeric fields | Not a string search | Searchable string key or numeric comparison |
| `$in` containing `{$regex:...}` objects | Not a valid regex literal in `$in` | Use regex literals or `$or` |
| Assuming negative regex is fast | May match most of the collection | Evaluate selectivity |
| Using `maxTimeMS` instead of validation | Does not eliminate all risks | Validate, escape, and rate-limit |
| Forgetting to update normalized field | Missing or stale results | Update atomically and backfill |
| Using regex for typos/relevance | Lacks those semantics | Search engine |

## 23. Analysis Scenarios

### 23.1. IXSCAN with Very High totalKeysExamined

A contains query may traverse an index while inspecting nearly every key. It is still reported as `IXSCAN` but lacks narrow bounded prefix ranges. Compare keys examined against documents returned and adjust the query or filter if business rules allow.

### 23.2. Single-Character Prefix

`/^P/` may match 40% of products. An index might still be used, yet selectivity is low. Enforce a minimum prefix length, result limit, and rate limiting in the UX.

### 23.3. Adding the i Flag Slows Down Autocomplete

Changing `/^Phone/` to `/^phone/i` finds more results, but the index bounds differ. Do not try to fix it with a case-insensitive collation index as you would for equality; consider a normalized field or Search.

### 23.4. Regex on a Computed Field

If a pipeline computes a `$toLower` field and runs a regex on it, the original index on `name` cannot automatically act like an index on the computed `lowerName`. A precomputed key or Search may be more appropriate.

### 23.5. Regex Input Containing a Dot

A user types `AB.42`, but a raw regex query `^AB.42` can match `ABX42`. Escape literals whenever the input field searches for literal codes.

## 24. Exercises

### Exercise A — Predict the Results

Given the SKUs:

~~~text
PH-100
PH-101
PH-VN
XPH-300
CASE-PH
ph-103
~~~

Predict the results of:

1. `/^PH/`.
2. `/PH/`.
3. `/PH$/`.
4. `/^ph/i`.
5. `/^PH.*$/`.

Explain why 1 and 5 usually return the same results on single-line strings yet differ in performance.

### Exercise B — Explain

1. Create the `{sku:1}` index.
2. Explain `/^PH/`, `/PH/`, and `/^ph/i`.
3. Compare `indexBounds`, `totalKeysExamined`, and `totalDocsExamined`.
4. Explain why MongoDB might choose `COLLSCAN` when there are only 18 docs.
5. Use `hint` in the lab to investigate index cost.

### Exercise C — Compound Index

For a query with `tenantId` equality, `status` equality, and `sku` prefix, propose an index. Then drop `status` or `tenantId` from the query and analyze how compound index usability changes.

### Exercise D — Case-Insensitive

1. Compare `name:/^phone/i` and `nameLower:/^phone/`.
2. Create an index on `nameLower`.
3. Inspect explain output.
4. List the migration and update costs.

### Exercise E — Escaping

Users enter `AB.42`, `C++`, and `foo(bar)`.

- Use `escapeRegexLiteral()` to construct a literal prefix regex.
- Explain why skipping escaping causes incorrect matches.
- Define a length-limit and timeout policy.

### Exercise F — Java Sync Driver

Try:

- `Filters.regex("sku","^PH")`.
- `Filters.regex("name","^phone","i")`.
- `Pattern.quote(userInput)`.
- Combining tenant and status equality filters.
- Explain and `maxTime`.

### Exercise G — Vietnamese

A user types `dien thoai` to search for `Điện thoại phổ thông`:

- Is the `i` flag sufficient?
- What normalization or accent removal is needed?
- When should you use a MongoDB Search analyzer?
- How do you preserve the original display name for the UI?

### Exercise H — Sharding

A collection is sharded by tenant. Compare queries with and without `tenantId`. Distinguish shard targeting from index bounds.

### Exercise I — Tool Selection

Choose among equality, prefix regex, normalized field, text index, Search, or reversed key for these features: exact SKU, name prefix, description contains, typo-tolerant autocomplete, warehouse code suffix, and relevance ranking.

### Exercise J — Performance Runbook

A prefix search API becomes slow after adding the `i` flag. Write a runbook:

1. Verify the query and semantics.
2. Check indexes and collations.
3. Read explain output.
4. Inspect selectivity and tenant distribution.
5. Test a normalized indexed field.
6. Benchmark on representative data.
7. Set up monitoring and rollback.

## 25. Checklist

- [ ] Exact, prefix, contains, or suffix?
- [ ] Literal input or regex pattern?
- [ ] Start-of-string anchor with a simple literal prefix?
- [ ] Do `i` or `m` flags alter semantics?
- [ ] Are equality filters and compound index aligned?
- [ ] Is the prefix selective enough?
- [ ] What are the index collation and query collation?
- [ ] Checked `indexBounds`, `keysExamined`, `docsExamined`?
- [ ] Is user input escaped and validated?
- [ ] Is tenant authorization enforced?
- [ ] Are `limit`, `maxTimeMS`, and rate limits configured?
- [ ] Is the normalized key backfilled and kept in sync?
- [ ] Are accent-insensitive, fuzzy, or relevance requirements beyond regex?
- [ ] Benchmarked on a representative workload?

## 26. Official Documentation

- [MongoDB Manual – $regex Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/regex/)
- [MongoDB Manual – Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/)
- [MongoDB Manual – Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual – Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/)
- [MongoDB Manual – $regexMatch](https://www.mongodb.com/docs/manual/reference/operator/aggregation/regexMatch/)
- [MongoDB Manual – $text](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Manual – Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/)
- [MongoDB Search](https://www.mongodb.com/docs/atlas/atlas-search/)
- [MongoDB Java Sync Driver – Filters Builders](https://www.mongodb.com/docs/drivers/java/sync/current/builders/filters/)
- [MongoDB Java Sync Driver – Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)

## 27. Conclusion

`$regex` is a useful tool for string pattern matching. However, **the most effective B-tree index utilization generally comes from a simple, case-sensitive literal prefix immediately following `^` or `\A`**. Contains, suffix, leading wildcard, and case-insensitive matching do not share the same optimization properties.

Do not stop at "there is an index" or "explain shows IXSCAN." Inspect index bounds, keys and documents examined, result counts, and latency on a representative workload. Use equality for exact matches, a normalized field for certain case-insensitive prefix use cases, escape user input for safety, and move to a Search engine when requirements involve fuzziness, relevance, or complex full-text search.
