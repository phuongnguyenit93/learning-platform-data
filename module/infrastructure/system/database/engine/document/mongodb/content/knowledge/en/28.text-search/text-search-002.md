# Distinguishing String Matching, Collation, and Full-Text Search in MongoDB

## 1. Lesson Objectives

A search feature in an application often begins with a seemingly simple question: "When a user types **cafe**, which results should the system return?" Depending on the goal, valid results can vary greatly:

- Return only records whose field is an exact match for `"cafe"`.
- Treat `"Cafe"`, `"CAFE"`, and `"cafe"` as the same name.
- Treat `"café"` and `"cafe"` as equivalent regarding accents/diacritics.
- Find products with the **prefix** `"caf"`.
- Find `"cafe"` appearing **at any position** within a description.
- Find articles containing a **word**, a **phrase**, or linguistically related words.
- Rank documents by **relevance**, supporting typos, typeahead suggestions, or synonyms.

In MongoDB, these requirements belong to **different mechanisms** and cannot all be solved cleanly by a single operator:

1. **Standard string matching:** equality, range, prefix/substring via `$regex` or a normalized key field.
2. **Collation:** locale-specific rules for comparing and sorting strings, handling case sensitivity, diacritics, and linguistic properties.
3. **Full-text search:** tokenizing text into terms, building an inverted/search index, matching words/phrases, and computing relevance rankings.

MongoDB provides **`$text` + text index** in the Database Query Language and **MongoDB Search** via the **`$search`** aggregation stage. They are not the same thing. MongoDB currently recommends MongoDB Search for rich full-text search needs; availability depends on version and deployment environment.

After this lesson, you will be able to choose the right mechanism for **product SKUs, person names, product titles, article search, autocomplete, and Vietnamese search**, understand index costs, and explain common incorrect query results.

## 2. Core Mental Model: Three Different Questions

Suppose a collection stores:

```javascript
{ sku: "CF-001", title: "Cà phê sữa", description: "Hương vị cà phê Việt Nam" }
```

Three categories of questions:

| Question | Typically Suitable Mechanism | Why |
| --- | --- | --- |
| Does SKU **equal** `"CF-001"`? | Equality + B-tree index | Deterministic key lookup requiring exactness |
| Are `"cafe"` and `"Café"` equivalent when **comparing**? | Collation or normalized key | Requires case and diacritic comparison rules |
| Which documents are about "cà phê" and are **most relevant**? | Full-text search | Requires tokenization and relevance scoring |
| Which names **start** with `"Ca"`? | Prefix regex/index or autocomplete index | Prefix query, not whole-field equality |
| Which descriptions **contain the substring** `"phe"`? | Substring regex / n-gram search | Substring lookup, not token search |
| Typeahead suggestions for `"ca ph"` | MongoDB Search autocomplete or search service | Needs an index optimized for prefix/semantic lookup |
| Sort names in Vietnamese alphabetical order | `collation: { locale: "vi", ... }` | Requires cultural/linguistic sort order |

**Do not confuse them:** a predicate `{ title: "cafe" }` does not find documents *that mention the word cafe* inside a longer sentence. It is an **equality check on the field value** under the active collation.

## 3. High-Level Comparison Table

| Property | Equality / string range | `$regex` | Collation | Legacy `$text` | MongoDB Search `$search` |
| --- | --- | --- | --- | --- | --- |
| Matching unit | Field value | Character pattern | Comparison/sort **rules** | Indexed tokens/words | Tokens, phrases, autocomplete, multiple operators |
| Full-field match | Yes | If properly anchored | When paired with equality | Not by default | Depends on operator/analyzer |
| Arbitrary-position substring | No | Yes | Not natively | No | Configurable via regex/wildcard/ngram |
| Case sensitivity | Yes with `simple` | Regex flags | `strength`, `caseLevel` | Depends on text index/query | Depends on analyzer/index |
| Diacritic sensitivity | Yes with `simple` | Per pattern/normalization | `strength` and locale | Depends on text index/query | Depends on analyzer |
| Stemming / stop words | No | No | No | Yes for supported languages | Depends on analyzer |
| Relevance score | No | Not by default | No | `textScore` | `searchScore` |
| Primary index | B-tree | B-tree for case-sensitive prefix | B-tree with **matching collation** | Text index | MongoDB Search index |
| Autocomplete / typo tolerance | No | Very limited | No | Not suitable | Dedicated operators/policies |
| Strengths | Exact keys, predictable performance | Small patterns, prefixes | Locale-aware equality/sort | Basic full-text | Rich search experience |
| Typical pitfalls | Confusing equality with contains | Scans, regex injection | Expecting collation to search words | Treating `$text` as substring | Missing Search index/analyzer setup |

**Collation is not a search engine.** It is a set of comparison rules applied to operations such as equality, range, sort, and uniqueness. Full-text search relies on its own **indexes and search algorithms**.

## 4. Lab A: String Matching and Collation

The following commands are meant for **mongosh** in a practice database. Never use `drop()` in production.

```javascript
const lab = db.getSiblingDB("string_search_lab");

lab.names.drop();

lab.names.insertMany([
  { _id: 1, name: "cafe",        code: "item2",  group: "drink" },
  { _id: 2, name: "Café",        code: "item10", group: "drink" },
  { _id: 3, name: "CAFE",        code: "item1",  group: "drink" },
  { _id: 4, name: "café",        code: "item12", group: "drink" },
  { _id: 5, name: "café mocha",  code: "item3",  group: "drink" },
  { _id: 6, name: "Cà phê sữa",  code: "item4",  group: "drink" },
  { _id: 7, name: "cà Phê Sữa",  code: "item5",  group: "drink" },
  { _id: 8, name: "Ca phe sua",  code: "item6",  group: "drink" },
  { _id: 9, name: "trà xanh",    code: "item7",  group: "drink" }
]);

lab.names.createIndex(
  { name: 1 },
  { name: "ix_name_simple" }
);

lab.names.createIndex(
  { code: 1 },
  { name: "ix_code_simple" }
);
```

**Note:** This collection is created with the default `simple` collation (binary comparison) because no `collation` was specified at creation time. Use the same fixture across queries to avoid confusing results due to changing data.

## 5. Equality on Strings: Field Value, Not Keyword Search

Query:

```javascript
lab.names.find(
  { name: "cafe" },
  { _id: 1, name: 1 }
).toArray();
```

With `simple` collation, this returns only the document:

```javascript
{ _id: 1, name: "cafe" }
```

It does not match `"CAFE"`, `"Café"`, or `"café mocha"`.

### 5.1. Strings Differing in Unicode Representation Also Differ

In terms of representation, `"é"` can be encoded as:

- A single precomposed code point: U+00E9.
- Two code points: `e` U+0065 and combining acute U+0301.

Both forms look identical on screen but **do not share the same byte/code-point sequence**. Under `simple`, comparison checks raw character code values and does not automatically treat different Unicode normalization forms as equivalent.

When an exact business key is required, define an application normalization policy (for example, NFC plus locale/rule-based lowercasing) and store a dedicated normalized key field. Do not assume lowercasing is trivial across all languages.

### 5.2. Equality, `$in`, and Range

```javascript
// Exact values in a set of choices.
lab.names.find({
  name: { $in: ["cafe", "CAFE"] }
});

// Lexicographical range under the active collation.
lab.names.find({
  name: { $gte: "C", $lt: "D" }
});
```

These operators do not understand meaning, stem words, or search substrings. Collation can alter how strings compare in equality and range predicates.

### 5.3. B-Tree Index for Equality

The `{ name: 1 }` index supports equality on `name` under the **same collation**. With `simple` and the predicate above, the query can use the index to avoid a full collection scan. On a tiny fixture, the optimizer may pick another plan because the collection has very few documents; do not infer from the lab that the server must always choose `IXSCAN`.

Inspect the plan:

```javascript
lab.names.find({ name: "cafe" })
  .explain("executionStats");
```

Read `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and the index path in your server version's output.

## 6. `$regex`: Character Patterns, Not Full-Text Search

MongoDB supports regular-expression predicates:

```javascript
// Name starts with "caf" (case-sensitive).
lab.names.find({ name: /^caf/ });

// Name contains the string "cafe" at any position.
lab.names.find({ name: /cafe/ });

// Ignore uppercase/lowercase differences.
lab.names.find({ name: /^cafe/i });

// Entire string must be "cafe", no trailing suffix allowed.
lab.names.find({ name: /^cafe$/i });
```

On the lab dataset:

- `/^caf/` matches `cafe`, `café`, and `café mocha` because all three start with lowercase `caf`; it does not match capitalized `Café` or `CAFE`.
- `/^cafe/i` matches `cafe`/`CAFE`, but **does not strip accents to match `"café"`**; `e` and `é` are different characters.
- `/^cafe$/i` requires the entire value to be `cafe` or a casing variant of the same unaccented letters, so it does not return `"café mocha"`.
- The pattern `/cafe/` does not tokenize words or rank relevance.

### 6.1. Prefix Regex Can Leverage an Index

MongoDB optimizes **case-sensitive prefix expressions** starting with `^` or `\A` followed by fixed characters:

```javascript
lab.names.find({ name: /^caf/ })
  .explain("executionStats");
```

With a suitable index, MongoDB can derive prefix bounds and restrict the portion of the index scanned.

Compare:

```javascript
lab.names.find({ name: /^caf/ });  // Prefix.
lab.names.find({ name: /caf/ });   // Substring anywhere.
lab.names.find({ name: /caf/i });  // Case-insensitive substring.
```

The latter two queries are generally much harder to serve efficiently with a B-tree; they may need to inspect many keys/documents.

**Not every regex is fast just because a field is indexed.** Pattern shape and flags matter greatly.

### 6.2. Case-Insensitive Regex Cannot Benefit from a Collation Index

A common design mistake:

```javascript
lab.names.createIndex(
  { name: 1 },
  {
    name: "ix_name_casefold",
    collation: { locale: "en", strength: 2 }
  }
);

// Do not expect this collation index to make an /i regex fast.
lab.names.find({ name: /^cafe/i })
  .collation({ locale: "en", strength: 2 });
```

`$regex` is **not collation-aware**. MongoDB documentation explicitly states that collation-based case-insensitive indexes **do not speed up `$regex`**. Use equality + matching collation for case-insensitive name matching, or use a dedicated autocomplete/search index if the true need is prefix typing.

### 6.3. User-Supplied Regex Needs Controls

Never concatenate raw user input directly into a regex as an arbitrary expression:

```javascript
// Not recommended if input is unvalidated:
const userPattern = request.query.q;
const query = { name: { $regex: userPattern } };
```

Risks:

- Characters such as `.`, `^`, `$`, `(`, `)` change pattern semantics.
- Complex patterns can exhaust CPU (ReDoS).
- Unanchored regexes can trigger broad scans.
- Unicode case folding and word boundaries may behave unexpectedly.
- Search-engine-style freeform queries may return irrelevant results.

Define clearly whether the API is "prefix", "contains", or "true regex"; when building a regex from literal input, **escape metacharacters**, enforce length limits, and apply timeouts/resource budgets. For large-scale search, consider a Search index.

## 7. What Is Collation?

**Collation** defines the rules MongoDB uses to compare and sort **strings**. MongoDB relies on the ICU library to support many locales, including `vi` (Vietnamese), `en`, `fr`, and others.

A collation document typically looks like:

```javascript
{
  locale: "vi",
  strength: 2
}
```

`locale` specifies the language/comparison rules. `strength` defines how strictly characters, diacritics, and letter casing are distinguished. Collation can be set:

- As the default on a **collection** upon creation.
- On an **index**.
- On individual **queries/sorts/aggregations** where supported.
- On certain comparison/uniqueness operations.

Collation **does not modify stored string data**. It changes how MongoDB determines whether two values are "equal" or how they sort.

## 8. `locale`, `strength`, and Case/Diacritic Sensitivity

Key configuration levels:

| Configuration | Primary Meaning | Case-sensitive? | Diacritic-sensitive? |
| --- | --- | --- | --- |
| `{ locale: "simple" }` | Binary / code-point comparison | Yes | Yes |
| `{ locale: "fr", strength: 1 }` | Base characters only (primary level) | Usually **no** | Usually **no** |
| `{ locale: "fr", strength: 2 }` | Base + diacritic differences | **No** if `caseLevel:false` | **Yes** |
| `{ locale: "fr", strength: 3 }` | Base + diacritics + case/variants | **Yes** | **Yes** |
| `strength: 1` + `caseLevel:true` | Adds case comparison at primary strength | **Yes** | Not at secondary strength |

Levels depend on the locale's ICU rules; do not assume all letter variants share the same base relationship across every language. `strength:3` is the default for non-`simple` locales; `caseLevel:false` is the default.

### 8.1. Testing with `"cafe"`/`"café"` Data

```javascript
// Ignore case and diacritics under French primary strength.
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 })
  .toArray();
```

Under this comparison policy, equivalent forms of the **same word** such as `"cafe"`, `"CAFE"`, `"café"`, and `"Café"` can match. However, `"café mocha"` **does not become `"cafe"`**, because collation is not substring matching.

```javascript
// Case-insensitive, while still distinguishing diacritics.
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 2 })
  .toArray();
```

Here `"cafe"` and `"CAFE"` are treated as equivalent in case; accented `"café"` remains distinct. With `strength: 3`, `"cafe"` and `"CAFE"` also differ.

### 8.2. Vietnamese Example

```javascript
lab.names.find({ name: "Cà phê sữa" })
  .collation({ locale: "vi", strength: 2 })
  .toArray();
```

Strength 2 is generally case-insensitive while preserving secondary diacritic differences. It can therefore compare variants like `"Cà phê sữa"` and `"cà Phê Sữa"` according to Vietnamese locale rules.

To also match unaccented `"Ca phe sua"`, evaluate `strength:1` collation or a **normalized search field**. In Vietnamese, letters such as `đ` may have a different base relationship to `d` in ICU, so "accent folding" via locale collation **is not a comprehensive transliteration**. Never claim all unaccented variants match without testing on real data.

### 8.3. `caseLevel` and `caseFirst`

```javascript
{
  locale: "en",
  strength: 1,
  caseLevel: true
}
```

Even though strength 1 skips secondary diacritic comparisons, `caseLevel:true` adds case distinction. `caseFirst:"upper"` or `"lower"` can influence case ordering when the comparison level evaluates case.

Define the business requirement clearly: **case- and accent-insensitive** differs from **accent-insensitive yet case-sensitive**.

## 9. Collation Changes Sort Order, Not Relevance Ranking

Compare the default sort:

```javascript
lab.names.find(
  {},
  { _id: 0, name: 1 }
).sort({ name: 1 });
```

with a Vietnamese locale sort:

```javascript
lab.names.find(
  {},
  { _id: 0, name: 1 }
)
.sort({ name: 1 })
.collation({ locale: "vi", strength: 3 });
```

The two orderings can differ because `simple` sorts by binary code values whereas locale `vi` follows ICU rules.

**Do not confuse alphabetic sorting with relevance.** If a user searches for `"mongodb"`, sorting `title` by locale only orders titles alphabetically; it has no notion of which article is more relevant to the query.

### 9.1. `numericOrdering`

A familiar use case:

```javascript
lab.names.find(
  {},
  { _id: 0, code: 1 }
)
.sort({ code: 1 })
.collation({ locale: "en", numericOrdering: true });
```

For strings like `item2` and `item10`, `numericOrdering:true` compares **sequences of positive digits** numerically rather than character-by-character (`item2` before `item10`). It is not a full number parser: negative signs, decimal points, and strings with separators have specific limitations. Do not use it as a substitute for storing true numeric values in BSON numeric types.

### 9.2. `alternate`, `normalization`, `backwards`

Collation also offers advanced options:

- `alternate:"shifted"`: can make certain whitespace/punctuation characters less significant at certain levels.
- `maxVariable`: specifies which variable characters are affected by `alternate`.
- `normalization:true`: checks/normalizes strings with differing Unicode normalization forms.
- `backwards:true`: reverses secondary diacritic weight evaluation in certain locales (e.g., certain French rules).

These are ICU parameters, not "understand sentence meaning" switches. Only use them when requirements are explicit and client/locale compatibility is verified.

## 10. Collation Indexes and Queries Must Match

**Essential rule:** For an index to support collation-based **string comparison**, the query must use the **exact same collation** as the index, or inherit the matching collection default collation.

Create an index with French primary strength:

```javascript
lab.names.createIndex(
  { name: 1 },
  {
    name: "ix_name_fr_strength1",
    collation: { locale: "fr", strength: 1 }
  }
);
```

Query using the same collation:

```javascript
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 })
  .explain("executionStats");
```

This index can serve equality predicates under those exact collation rules.

Query using a different collation:

```javascript
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 2 })
  .explain("executionStats");
```

Even when only `strength` differs, do not expect `ix_name_fr_strength1` to support string comparisons for the second collation. MongoDB may pick another index or choose a plan that does not use that index for string comparison.

### 10.1. Collection Default Collation

At collection creation:

```javascript
lab.namesWithDefault.drop();

lab.createCollection(
  "namesWithDefault",
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);

lab.namesWithDefault.insertMany([
  { _id: 1, name: "Cà phê sữa" },
  { _id: 2, name: "cà Phê Sữa" }
]);

// The index inherits the default collation.
lab.namesWithDefault.createIndex({ name: 1 });
```

`find()` and `sort()` on this collection inherit `vi/strength:2` by default unless overridden. Newly created indexes also inherit the default collation unless specified otherwise.

To run a binary query:

```javascript
lab.namesWithDefault.find({
  name: "Cà phê sữa"
}).collation({ locale: "simple" });
```

An index with the default `vi/strength:2` collation cannot serve binary string comparisons on the same field. If both are needed, you can create a **separate index with `locale:"simple"`** and a distinct name.

### 10.2. Collation-Aware Indexes Have Overhead

Collation indexes may store **ICU collation keys** larger than binary keys, increasing:

- Index size.
- Write and cache pressure.
- Index build time.
- The number of indexes to maintain if the app requires multiple comparison styles.

Do not create an index for every locale unless the product truly needs it; evaluate query patterns and `explain` output first.

## 11. Unique Indexes with Collation: Impact on Valid Data

Usernames often need to be case-insensitive, so a collation-aware unique index can enforce that invariant.

```javascript
lab.accounts.drop();

lab.accounts.createIndex(
  { username: 1 },
  {
    unique: true,
    name: "uq_username_case_insensitive",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);

lab.accounts.insertOne({
  username: "Alice"
});
```

Test:

```javascript
// Expect E11000 because "alice" is equivalent to "Alice"
// under collation strength 2.
lab.accounts.insertOne({
  username: "alice"
});
```

Uniqueness constraints are governed by the index's collation. This is very useful for usernames, but dangerous if a business key intentionally distinguishes uppercase from lowercase.

### 11.1. If Using Strength 1

With French collation strength 1, `"cafe"` and `"café"` can be treated as duplicates by a unique index. If the business considers accented and unaccented brand names distinct, strength 1 is inappropriate.

### 11.2. Migrations Must Check for Duplicates First

If a collection already contains both `"Alice"` and `"alice"`, creating a unique collation index immediately will fail with `E11000`. You must:

1. Identify the semantic key.
2. Detect collision groups under the target collation.
3. Resolve or merge duplicates according to business rules.
4. Create the unique index once the data is clean.
5. Handle race conditions and `E11000` errors in the API.

**Never** delete duplicate documents via script without business approval; two records may be linked to different accounts, histories, or permissions.

## 12. Collation Is Not Full-Text Search

Example:

```javascript
// Compares the entire name field against "cafe".
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 });
```

This query will not match `"café mocha"` just because `"café"` appears inside the string. Collation **does not tokenize words** and **does not rank results** by frequency or weights.

Similarly:

```javascript
lab.names.find({ name: "phê" })
  .collation({ locale: "vi", strength: 1 });
```

does not search for every name containing the word `phê`. If the requirement is "names containing a word in a sentence," use an appropriate `$regex`, `$text`, or Search index.

## 13. Full-Text Search with `$text` and Text Indexes

MongoDB supports the **`$text`** operator backed by a **text index**. It:

- Tokenizes strings into words/terms according to rules.
- Can apply **stemming** (reducing words to root forms) and **stop words** for supported languages.
- Finds documents containing matching tokens in indexed fields.
- Computes **`textScore`** for relative ranking.
- Supports single words, double-quoted phrases, and word negation.

This is a distinct mechanism from B-tree equality and index collation.

**MongoDB recommends MongoDB Search for advanced full-text capabilities.** Even so, `$text` remains useful for understanding the built-in mechanism and supporting smaller or legacy applications.

### 13.1. Legacy Text Index Limitations

- **At most one text index per collection**; that single index may cover multiple text fields.
- A text index **uses only simple binary collation**, even though `$text` tokenization/case-folding can be case-insensitive.
- `$text` requires an existing text index.
- Text indexes cannot be used to accelerate general sorting.
- Do not use `hint()` to force a text index for a `$text` query.
- Compound text indexes have restrictions around equality prefixes and special index types.
- `$text` does not sort by score by default.
- `$text` queries and the `$search` aggregation stage **do not share syntax or indexes**.

## 14. Lab B: `$text` on English Articles

Create a separate collection without a non-simple default collation:

```javascript
lab.articles.drop();

lab.articles.insertMany([
  {
    _id: 1,
    title: "MongoDB indexing basics",
    body: "Indexing helps queries run faster",
    category: "database"
  },
  {
    _id: 2,
    title: "MongoDB index tuning",
    body: "Compound indexes help queries",
    category: "database"
  },
  {
    _id: 3,
    title: "Coffee brewing guide",
    body: "Fresh beans and water",
    category: "lifestyle"
  },
  {
    _id: 4,
    title: "Fast MongoDB backup",
    body: "Backup restores and replicas",
    category: "database"
  },
  {
    _id: 5,
    title: "Search indexing practices",
    body: "Search engines rank documents",
    category: "technology"
  }
]);

lab.articles.createIndex(
  { title: "text", body: "text" },
  {
    name: "txt_title_body",
    default_language: "english",
    weights: { title: 10, body: 2 }
  }
);
```

`weights` affects the text relevance score: a term appearing in `title` carries higher weight than in `body`, per this configuration.

### 14.1. Searching a Single Word

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb"
  }
}).toArray();
```

`$text` looks for matching tokens across **text-indexed fields**, without requiring the entire `title` to equal `"mongodb"`. Documents containing MongoDB in `title` or `body` are candidates.

### 14.2. Multiple Words Are OR by Default

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb indexing"
  }
}).toArray();
```

Legacy `$text` tokenizes terms and performs a **logical OR** over non-stop-word, non-negated terms; by default it does not require both words to be present.

If you require all terms or complex boolean logic, add appropriate predicates or use MongoDB Search with `compound`/`matchCriteria`.

### 14.3. Phrase Search

```javascript
lab.articles.find({
  $text: {
    $search: "\"mongodb indexing\""
  }
}).toArray();
```

The double quotes inside the `$search` string **are part of the text query syntax**, requiring an exact phrase match. This is completely different from equality:

```javascript
lab.articles.find({
  title: "MongoDB indexing"
});
```

Equality on `title` matches only when the entire field equals that value under the active collation; phrase search checks whether the phrase appears within the text-indexed fields.

### 14.4. Excluding Tokens

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb -backup"
  }
}).toArray();
```

A leading `-` before a token in `$search` indicates negation, not arithmetic subtraction. Because the `$text` parser treats certain punctuation specially, do not pass literal SKUs/codes containing hyphens into `$text` expecting exact equality.

### 14.5. Stemming Is Not Substring Matching

English text indexes perform stemming. Related words like `index`, `indexes`, and `indexing` may reduce to the same root under the English stemmer. However, `"blue"` **does not** match `"blueberry"` by default merely because it is a prefix.

Contrast with regex:

```javascript
// Character prefix:
lab.articles.find({ title: /^Mongo/ });

// Indexed token:
lab.articles.find({
  $text: { $search: "mongo" }
});
```

`$text` is not a "match any substring" prefix search. For partial typing, use autocomplete/ngram indexing or an appropriate tool.

## 15. Ranking Results with `textScore`

MongoDB assigns a score to `$text` results. Never assume results are automatically sorted by score.

```javascript
lab.articles.find(
  { $text: { $search: "mongodb indexing" } },
  {
    title: 1,
    category: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).toArray();
```

Notes:

- The score is a **text-index relevance score**, not a probability that a document is correct.
- Weights `title:10` and `body:2` can rank matches in `title` higher.
- Do not hardcode score order or values across versions or changing corpora.
- You can add a deterministic secondary sort key for pagination when using an appropriate sort, without assuming score alone is unique.

### 15.1. Using `$text` in Aggregation

```javascript
lab.articles.aggregate([
  {
    $match: {
      $text: { $search: "mongodb" }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "textScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]).toArray();
```

Here `$match` containing `$text` is placed **as the first stage**, as required for `$text` in aggregation pipelines. Do not place `$project` or `$addFields` before it and expect the planner to accept it.

### 15.2. `$caseSensitive` and `$diacriticSensitive`

Example:

```javascript
lab.articles.find({
  $text: {
    $search: "MongoDB",
    $caseSensitive: true
  }
});
```

With a standard version-3 text index, `$text` is case- and diacritic-insensitive by default; setting `$caseSensitive:true` or `$diacriticSensitive:true` changes filtering behavior and can slow down the query.

**These are `$text` options**, not collation options. A text index restricted to binary collation can still perform case/diacritic-insensitive token matching via text-index mechanics. Do not conflate "binary index collation" with "how text token matching handles casing."

## 16. Language Limitations: Vietnamese as a Key Example

**MongoDB collation** provides the `vi` locale for string comparison rules. However, **legacy `$text` text indexes do not include Vietnamese stemming or stop-word support** in the MongoDB Database Manual's list of supported text search languages.

The two language lists are **different**:

- `collation({locale:"vi"})`: compares/sorts strings using Vietnamese ICU locale rules.
- `$text` with `default_language:"vietnamese"`: **is not a supported language option for legacy text indexes**.

Languages with official `$text` stemming/stop-word support include English, French, German, Spanish, Russian, Turkish, and others—but **not Vietnamese**.

### 16.1. Using `default_language:"none"` When You Do Not Want English Stemming

A basic option for multilingual documents:

```javascript
lab.viArticles.drop();

lab.viArticles.insertMany([
  {
    _id: 1,
    title: "Cà phê sữa Việt Nam",
    body: "Hướng dẫn pha cà phê sữa"
  },
  {
    _id: 2,
    title: "Trà xanh",
    body: "Uống trà và bảo quản lá trà"
  },
  {
    _id: 3,
    title: "Máy pha cà phê",
    body: "Thiết bị pha chế tại nhà"
  }
]);

lab.viArticles.createIndex(
  { title: "text", body: "text" },
  {
    name: "txt_vi_terms",
    default_language: "none"
  }
);
```

`none` stops MongoDB from applying language-specific stop-word removal and suffix stemming. It **does not create a Vietnamese tokenizer capable of recognizing every compound word or accented variant**.

```javascript
lab.viArticles.find({
  $text: {
    $search: "cà phê"
  }
}).toArray();
```

This is still parser-tokenized `$text` search, typically **OR**, rather than full Vietnamese semantic search. For a phrase:

```javascript
lab.viArticles.find({
  $text: {
    $search: "\"cà phê\""
  }
}).toArray();
```

Test the tokenizer, diacritics, normalization, and real multilingual data. Searching `"ca phe"` may behave differently from `"cà phê"` when the analyzer and stored data follow different normalization rules.

### 16.2. Normalized Text Fields for Specific Use Cases

If the requirement is searching **unaccented product names** per business rules, you can store them side by side:

```javascript
{
  title: "Cà phê sữa",
  titleKey: "ca phe sua"
}
```

`titleKey` is normalized **at ingestion** using a versioned, well-tested algorithm. For exact lookup:

```javascript
lab.products.find({
  titleKey: "ca phe sua"
});
```

This is equality modeling on a normalized key, **not full-text search**. Substring or prefix matching still requires its own index and query design. Do not blindly strip diacritics across the whole system if characters carrying distinct meaning (such as `d` vs. `đ`) must remain separate without an explicit policy.

## 17. Compound Text Indexes and Important Restrictions

A text index can be combined with regular keys in a compound index, subject to specific rules.

For example, tenant-specific text search:

```javascript
lab.tenantArticles.drop();

lab.tenantArticles.insertMany([
  { _id: 1, tenantId: "A", title: "MongoDB indexing", body: "Index basics" },
  { _id: 2, tenantId: "B", title: "MongoDB indexing", body: "Other tenant" }
]);

lab.tenantArticles.createIndex(
  { tenantId: 1, title: "text", body: "text" },
  {
    name: "txt_tenant_title_body",
    default_language: "english"
  }
);
```

When regular keys **precede** text keys in the index, `$text` queries must include equality predicates on those prefix fields:

```javascript
lab.tenantArticles.find({
  tenantId: "A",
  $text: { $search: "mongodb indexing" }
});
```

Do not assume a query containing only `$text` will use that compound index without providing `tenantId` as an equality predicate.

Additional rules:

- Each collection can have at most **one text index**, even if it covers multiple text fields.
- In a compound index, text keys must be listed **contiguously** per index rules.
- Compound text indexes cannot be arbitrarily combined with other special index types.
- Text indexes do not optimize sorting; sorting by date or relevance requires evaluating the plan and score separately.
- On a collection with a **non-simple default collation**, creating a text index requires **explicitly** specifying `{ collation: { locale:"simple" } }`.

### 17.1. Text Index on a Collection with a Default Collation

```javascript
lab.localizedArticles.drop();

lab.createCollection(
  "localizedArticles",
  {
    collation: {
      locale: "fr",
      strength: 1
    }
  }
);

// Text indexes require simple collation.
lab.localizedArticles.createIndex(
  { title: "text", body: "text" },
  {
    name: "txt_localized_simple",
    collation: { locale: "simple" },
    default_language: "english"
  }
);
```

Requiring the text index's collation to be **simple** does not mean `$text` queries can never perform case- or diacritic-insensitive matching. The two operate independently at different layers.

## 18. MongoDB Search with `$search`: The Advanced Option

MongoDB Search maintains a dedicated search index (powered by dedicated search technology), uses **analyzers** to tokenize and normalize text, and provides rich operators:

- `text`: searches analyzed terms.
- `phrase`: searches phrases with configurable term distance/slop.
- `autocomplete`: typeahead suggestions.
- `regex`/`wildcard`: conditional pattern matching.
- `compound`: combines `must`, `should`, `filter`, and `mustNot`.
- `fuzzy`: tolerates a bounded number of typos.
- Synonyms, highlighting, facets, and configurable scoring.

**Environment support update:** MongoDB Search is no longer exclusively an Atlas feature. Per current MongoDB documentation, `$search` is supported on Atlas as well as self-managed **MongoDB Community 8.2+** and **Enterprise 8.2+ with Kubernetes Operator**, subject to documented installation and deployment requirements. Older deployments or clusters without a configured Search service/index cannot simply copy a `$search` pipeline and run it.

### 18.1. `$text.$search` and the `$search` Aggregation Stage Are Different

**Legacy:**

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb"
  }
});
```

**MongoDB Search:**

```javascript
lab.articles.aggregate([
  {
    $search: {
      index: "title_body_search",
      text: {
        query: "mongodb",
        path: ["title", "body"]
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
```

These are two separate systems with **different indexes**, **different syntax**, and **different scores**. Do not confuse `$text`'s `textScore` with `$search`'s `searchScore`.

### 18.2. Creating a MongoDB Search Index (When Supported by Deployment)

In environments with MongoDB Search enabled, search indexes can be configured through the UI, API, or supported shell methods. Example index definition for `title` and `body`:

```javascript
lab.articles.createSearchIndex({
  name: "title_body_search",
  definition: {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        body: { type: "string" }
      }
    }
  }
});
```

Index builds are asynchronous; verify the index status is **READY/queryable** before running `$search`. Management APIs and workflows may vary by service and version. If an environment only has a legacy text index and no MongoDB Search, this snippet will not enable `$search`.

### 18.3. `text` and Fuzzy Matching

```javascript
lab.articles.aggregate([
  {
    $search: {
      index: "title_body_search",
      text: {
        query: "mongdb",
        path: ["title", "body"],
        fuzzy: {
          maxEdits: 1,
          prefixLength: 2
        }
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
```

This example requires an appropriate Search index. `fuzzy` does not blindly match every similar string: it relies on edit distance and analyzer tokenization; depending on token length, `prefixLength`, and configuration, a typo may still miss. Never guarantee specific fuzzy matches without testing on the actual index and corpus.

### 18.4. `phrase` and Autocomplete

Phrase search:

```javascript
lab.articles.aggregate([
  {
    $search: {
      index: "title_body_search",
      phrase: {
        query: "mongodb indexing",
        path: "title",
        slop: 0
      }
    }
  },
  { $project: { title: 1 } }
]);
```

For typeahead suggestions when typing `"mong"` or `"caf"`, create a **Search index with an `autocomplete` field mapping** and use the `autocomplete` operator. A `string` field mapping like the earlier example **does not automatically create an autocomplete mapping**.

```javascript
// Run only after creating a Search index with an autocomplete mapping
// for the title field.
lab.articles.aggregate([
  {
    $search: {
      index: "title_autocomplete",
      autocomplete: {
        query: "mong",
        path: "title"
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
```

A **Search index** must be designed intentionally. It may require a search analyzer, index analyzer, edge grams, min/max grams, and dedicated resource capacity; do not assume dynamic mapping automatically handles typos or prefix matching well.

### 18.5. Search Indexing Is Asynchronous

Search indexes have their own update pipeline. Immediately after an insert or update on the primary, `$search` may not reflect the change right away; account for **search index freshness** and consistency when the application requires read-your-writes semantics.

For recently updated SKU identifiers or access permissions, correctness-critical APIs should rely on **database equality and atomic operations**; never treat the search index as the source of truth just because results carry a score.

## 19. Designing for Vietnamese: `vi` Collation and Search Analyzers Are Not Equivalent

Common use cases:

| Vietnamese Requirement | Recommendation |
| --- | --- |
| Sort a list of Vietnamese names | Collation `locale:"vi"` with appropriate strength |
| Case-insensitive name matching | Equality + `vi` collation, strength 2, and matching index |
| Accent-insensitive name matching | Evaluate `strength:1` and verify ICU behavior; use a normalized key if custom accent-folding rules are needed |
| Search inside multi-sentence descriptions | MongoDB Search with a tested analyzer |
| Search phrase "cà phê sữa" | Search `phrase` with a suitable analyzer, or limited legacy `$text` |
| Typeahead "ca ph" | Search `autocomplete` and a normalized token policy |
| Exact lookup for code `CF-001` | Equality / B-tree index or normalized SKU key |
| Rank results | Search relevance scoring |
| Small dataset, literal prefix | Case-sensitive prefix `$regex` if fast enough |

### 19.1. Vietnamese Tokenization

Vietnamese places spaces between **syllables**, which do not always correspond one-to-one with semantic words. For instance, `"cà phê sữa"` can be tokenized into different terms depending on the analyzer. A generic Latin analyzer will not automatically recognize every Vietnamese compound word.

Test against a realistic dataset covering:

- Accented and unaccented text.
- Mixed uppercase and lowercase.
- Pairs of `d` and `đ`.
- NFC and NFD Unicode forms.
- Multi-syllable compound words.
- Punctuation, emojis, numbers, and SKU symbols.
- Abbreviations, proper nouns, and common typos.
- Mixed English and Vietnamese.
- Domain-specific synonyms.
- Brand names requiring exact matching.

**Never** run a single `"ca phe"` search, see a few results, and conclude the analyzer is good enough for the whole system.

### 19.2. A Schema Serving Multiple Purposes

```javascript
{
  _id: ObjectId("..."),
  sku: "CF-001",
  title: "Cà phê sữa",
  titleKey: "ca phe sua",
  description: "Cà phê pha cùng sữa đặc",
  categoryId: "beverages",
  locale: "vi",
  isActive: true
}
```

You can design:

- A unique index on `sku` to identify products.
- A B-tree index on `titleKey` for exact/prefix matches using normalized input conventions.
- A collation-aware index on `title` for locale sorting and display comparisons.
- A Search index on `title` and `description` for full-text relevance.
- Indexes on `categoryId` and `isActive` for filtering, or Search filter mappings where appropriate.

These are distinct responsibilities—there is no need to force a single field or index to handle all of them.

## 20. When to Use `$regex` vs. Search?

### 20.1. Short, Exact Prefix Matching

For example, finding codes starting with `"CF-"`:

```javascript
db.products.find({
  sku: /^CF-/
}).limit(20);
```

An index `{sku:1}` can support a case-sensitive prefix. If case-insensitive SKU matching is needed, it is usually better to **normalize the SKU on write** and query `skuKey`, rather than running `/i` across a large dataset every time.

### 20.2. Substring Inside Long Text

For example, descriptions containing `"phê"` anywhere:

```javascript
db.products.find({
  description: /phê/
});
```

Functionally this works, but cost can be high because there is no prefix bound optimization. For large volumes and search UX, consider a Search index with an appropriate analyzer/ngram configuration.

### 20.3. Search Requiring Relevance, Fuzziness, Synonyms, and Autocomplete

If requirements include:

- Fuzzy matching `"mongdb"` → `"mongodb"`.
- Typeahead suggestions.
- Boosting matches in `title` over `body`.
- Multi-language analysis.
- Phrase search and ranking.
- Highlighting matching snippets.

MongoDB Search is the right option to evaluate. It carries index, storage, and search-process costs, indexing latency, and relevance-testing overhead—it is not "free" compared to regex.

## 21. Collation and `$regex` in Aggregation

Collation applies to many string comparisons in supported aggregation stages:

```javascript
lab.names.aggregate(
  [
    { $match: { name: "cafe" } },
    { $sort: { name: 1 } }
  ],
  {
    collation: {
      locale: "fr",
      strength: 1
    }
  }
);
```

However, if `$match` uses `$regex`:

```javascript
lab.names.aggregate(
  [
    { $match: { name: { $regex: "^cafe", $options: "i" } } }
  ],
  {
    collation: {
      locale: "fr",
      strength: 1
    }
  }
);
```

the regex remains non-collation-aware; `"café"` will not automatically match `"cafe"` simply because of the aggregation collation.

### 21.1. `$toLower` Is Not a General Replacement for Collation

MongoDB provides string expressions such as `$toLower`, but their Unicode/locale handling and semantics are not equivalent to full ICU collation. Moreover, lowercasing data inside a query can prevent using a B-tree index on the original field.

If an application needs normalized search keys, normalize consistently **on write** and store a dedicated key rather than recomputing it across millions of documents on every request.

## 22. Node.js API Examples by Purpose

Example using the MongoDB Node.js Driver, assuming the `products` collection and appropriate indexes already exist:

```javascript
const { MongoClient } = require("mongodb");

async function examples() {
  const client = new MongoClient(process.env.MONGODB_URI);

  try {
    await client.connect();
    const products = client.db("app").collection("products");

    // 1. SKU identity: strict equality.
    const bySku = await products.findOne({
      sku: "CF-001"
    });

    // 2. Locale-aware case-insensitive name match.
    const byName = await products.find({
      title: "Cà phê sữa"
    }, {
      collation: { locale: "vi", strength: 2 }
    }).toArray();

    // 3. Prefix match on a normalized key.
    const prefix = await products.find({
      titleKey: /^ca phe/
    }).limit(20).toArray();

    console.log({
      foundSku: !!bySku,
      nameMatches: byName.length,
      prefixMatches: prefix.length
    });
  } finally {
    await client.close();
  }
}

examples().catch(err => {
  console.error(err);
  process.exitCode = 1;
});
```

These illustrate three search patterns serving three different contracts. `titleKey` must be generated consistently on write; if the `titleKey` index has an incompatible collation or input is unnormalized, results and performance will differ.

### 22.1. Legacy `$text` with Node.js

```javascript
const articles = client.db("app").collection("articles");

const results = await articles.find(
  {
    $text: {
      $search: "mongodb indexing"
    }
  },
  {
    projection: {
      title: 1,
      score: { $meta: "textScore" }
    },
    sort: {
      score: { $meta: "textScore" }
    },
    limit: 20
  }
).toArray();
```

This code requires an existing **text index**. Never create indexes dynamically per request. For advanced Search, use `aggregate([{$search:...}, ...])` on a deployment with a MongoDB Search index.

## 23. Java Sync Driver: Query Collation

The Java Driver provides `Collation`, `CollationStrength`, and `FindIterable` to configure collation:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;
import org.bson.Document;

public class StringMatchExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create(
                System.getenv("MONGODB_URI"))) {

            MongoDatabase database = client.getDatabase("app");
            MongoCollection<Document> products =
                database.getCollection("products");

            // Match name under the vi locale,
            // case-insensitive while preserving diacritic differences.
            Collation vietnamese = Collation.builder()
                .locale("vi")
                .collationStrength(CollationStrength.SECONDARY)
                .build();

            FindIterable<Document> matches = products.find(
                new Document("title", "Cà phê sữa")
            ).collation(vietnamese);

            for (Document product : matches) {
                System.out.println(product.toJson());
            }
        }
    }
}
```

Key takeaways:

- The driver forwards the collation specification to the database operation.
- Any index intended to accelerate the string comparison must share the matching collation.
- Collation does not turn an equality query into full-text search.
- Exact classes/imports may vary slightly by driver version; this example follows the standard Java Sync Driver API structure.

## 24. Choosing a Mechanism for Real-World Use Cases

| Use Case | Primary Choice | Why | Watch Out For |
| --- | --- | --- | --- |
| Lookup SKU, invoice ID, token ID | Equality + unique B-tree index | Must match one exact value | Do not make case-insensitive if IDs are case-sensitive |
| Case-insensitive username | Unique collation index or `usernameKey` | Prevents collisions | Data migration and Unicode policy |
| List of names sorted in Vietnamese | `vi` collation + matching index | Locale-aware ordering | Does not sort by relevance |
| Filter emails case-insensitively | Normalized email key or collation | Equality | Email normalization has domain-specific rules |
| Product code prefix | Anchored regex on normalized code | Can leverage B-tree | `/i` regex does not benefit from collation index |
| Small description substring | Controlled regex | Easy to implement | Can trigger broad scans |
| Word search in English articles | `$text` or MongoDB Search | Tokens and stemming | `$text` allows only one text index per collection |
| Typeahead, typo tolerance | MongoDB Search autocomplete/fuzzy | Dedicated search index | Index cost and configuration |
| Searching long Vietnamese content | MongoDB Search with tested analyzer | Relevance and customization | Word segmentation and Unicode |
| Exact brand name query | Equality + normalized/locale index | Avoids false positives | Over-aggressive accent stripping merges distinct names |
| Scored results | `$text` `textScore` or Search `searchScore` | Orders by relevance | Scores have no absolute cross-query meaning |
| Search right after a new write | Equality read with proper consistency | Avoids search-index lag | Search indexing can be asynchronous |

No single mechanism wins on every criterion. Production systems typically maintain **multiple indexes for different features** proportional to workload patterns.

## 25. Performance: Evaluate with `explain`, Not Intuition

### 25.1. B-Tree Equality

```javascript
lab.names.find({ name: "cafe" })
  .explain("executionStats");
```

Expect to inspect `IXSCAN`/`FETCH` (or equivalent plan), keys/docs examined, and `nReturned`.

### 25.2. Collation-Aware Equality

```javascript
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 })
  .explain("executionStats");
```

If an index with the matching collation exists, the query can use it. If the query overrides with a different collation, re-check the execution plan.

### 25.3. Prefix Regex vs. Contains Regex

```javascript
lab.names.find({ name: /^caf/ })
  .explain("executionStats");

lab.names.find({ name: /caf/ })
  .explain("executionStats");
```

On large datasets, case-sensitive prefixes generally scan a much narrower range. In a tiny lab collection, the optimizer may still pick a scan due to index startup overhead.

### 25.4. Legacy `$text`

```javascript
lab.articles.find({
  $text: { $search: "mongodb" }
}).explain("executionStats");
```

Do not confuse internal text index plans with B-tree equality plans. `$text` has distinct index rules and does not support `hint()` to force a text index.

### 25.5. MongoDB Search

For `$search`, use monitoring and explain/profiling features appropriate for your MongoDB version and search service. MongoDB Search has its own index structures, build times, and search-specific resource consumption.

**Metrics to measure:**

- Query latency p50/p95/p99.
- `nReturned`, documents and keys examined where applicable.
- Rate of queries falling back to `COLLSCAN` or broad scans.
- Index count and total index size.
- Insert/update cost (write amplification).
- Search index freshness.
- Relevance quality: precision/recall on an evaluation query set.
- CPU/memory/network and Search node/service cost.

## 26. Security and Correctness in Search

### 26.1. Never Turn Search into Access Control

If a user may only view products belonging to tenant A, every result must be **scoped by tenant/ACL** using an explicit predicate. Never treat search score as authorization.

Conceptual example:

```javascript
// Enforce tenant scope directly in the business query.
db.products.find({
  tenantId: "A",
  sku: "CF-001"
});
```

With MongoDB Search, apply `compound.filter` or post-query authorization checks per your architecture so data never leaks through autocomplete, facets, or highlighting.

### 26.2. Never Run Arbitrary User Regexes

Free-text search inputs can contain special characters. If an API is intended only for literal prefix matching, escape regex metacharacters, enforce length limits, and apply time/resource budgets.

### 26.3. Unique Constraints Are Business Invariants

A Search index **cannot** replace a unique index for `username` or `sku`. Full-text matching only returns relevant documents; it does not guarantee uniqueness under concurrency.

### 26.4. Search Indexes Can Lag

If an application creates a product and search does not immediately return it, the insert did not necessarily fail. Performing a direct lookup by `_id` or `sku` with appropriate write/read concerns gives an authoritative answer.

### 26.5. Do Not Blindly Strip Diacritics Everywhere

Normalizing personal names, addresses, codes, or brand names without a policy can accidentally merge distinct values. Store the **original display value** and the **normalized key** separately, and version the normalization algorithm.

## 27. Common Misconceptions

| Misconception | Why It Is Wrong | Fix |
| --- | --- | --- |
| `{title:"mongodb"}` finds all posts mentioning mongodb | Equality compares the entire field | Use `$text` or Search |
| Collation is full-text search | Collation does not tokenize or rank | Use a search index |
| `strength:1` removes all accents/transliterates every letter | ICU locales define primary differences | Test locale; use normalized field if needed |
| `/i` regex uses a case-insensitive collation index | Regex is not collation-aware | Equality + collation or Search |
| Regex `/cafe/` equals `$text:"cafe"` | Substring differs from token | Define the query contract |
| One B-tree index accelerates all prefix/contains regexes | Not all regexes derive prefix bounds | Inspect explain and consider Search |
| `$text` is the `$search` aggregation stage | Two distinct APIs and indexes | Use matching syntax and index |
| You can create multiple text indexes on one collection | Legacy allows only one text index | Combine fields or use Search |
| Text index with `vi` collation stems Vietnamese | Text indexes only allow simple collation; no Vietnamese stemmer | Use Search analyzer or limited `none` |
| `default_language:"english"` handles Vietnamese well | Stemming/stop words do not fit | Use `none` or Search depending on case |
| `$text` ANDs all words by default | Default is logical OR of tokens | Use phrases or compound semantics |
| `$text` sorts by relevance by default | It does not | Sort explicitly by `textScore` |
| `textScore` is a correctness probability | Score is relative to corpus and index | Evaluate ranking empirically |
| Searching `"mongo"` always matches `"mongodb"` | Text matching is not prefix matching | Use autocomplete or n-grams |
| Collation-aware unique index only affects sorting | It also governs uniqueness | Audit collisions before migrating |
| Changing collection collation leaves indexes unaffected | Default collation and index collation interact | Plan creation/migration carefully |
| Search reflects every write immediately | Search indexing can be async | Use direct lookup when freshness is required |
| Search indexes replace B-tree indexes | Different purposes | Use the right index per invariant/query |
| Seeing `IXSCAN` guarantees a fast query | Many keys/docs, sorts, or fetches may still occur | Measure `nReturned` and p95/p99 |
| No need to escape user regex | Pattern injection and CPU risk | Escape, limit, and set timeouts |
| Locale `vi` and `$text` language `vietnamese` are the same | Supported lists differ | Distinguish ICU collator from text stemmer |
| Enabling fuzzy matches every typo | Edit limits and analyzers have boundaries | Test against real corpus and options |

## 28. Practice Exercises

### Exercise 1 — Identify Requirements

For these four APIs, choose equality, regex, collation, `$text`, or MongoDB Search:

1. `GET /products/sku/CF-001`.
2. Case-insensitive lookup for username `Alice`.
3. Search articles about "indexing" and sort by relevance.
4. Autocomplete product names when the user has typed `ca`.

**Suggested answers:** 1. equality + B-tree; 2. collation-aware unique index or normalized key; 3. text search; 4. Search autocomplete or prefix regex if small.

### Exercise 2 — Simple Matching

Collection `names` contains `"cafe"`, `"CAFE"`, `"Café"`, and `"café"`. Which records does `{name:"cafe"}` match under `simple` collation?

**Answer:** Only `"cafe"` in the fixture.

### Exercise 3 — Strength 1 vs. 2

With `locale:"fr"`, search `"cafe"` at strength 1 and strength 2. Which level ignores both case and diacritics? Which ignores case but distinguishes diacritics?

**Answer:** Strength 1 ignores both case and diacritics per locale base rules; strength 2 ignores case while preserving diacritic differences.

### Exercise 4 — Collation Is Not Substring

Why does `{name:"cafe"}` with strength 1 not match `"café mocha"`?

**Answer:** Equality compares the **entire field value**, not tokens or substrings.

### Exercise 5 — Prefix Regex

Compare `/^caf/`, `/caf/`, and `/^cafe/i` in terms of semantics and index usage.

**Answer:** An anchored, case-sensitive prefix can derive index bounds; contains and case-insensitive regexes are less optimal.

### Exercise 6 — Regex and Diacritics

Does `/^cafe/i` match `"café"` by default? Why does collation strength 1 not make a regex accent-insensitive?

**Answer:** No; regex is not collation-aware.

### Exercise 7 — Matching Collation Index

Create `{name:1}` with `locale:"fr",strength:1`. Will a query with strength 2 use that same index to accelerate string comparison?

**Answer:** Do not expect it to; the query must match the index collation.

### Exercise 8 — Unique Username

Create a strength-2 unique index on `username`, then insert `"Alice"` followed by `"alice"`. What happens? What if the collection already contains both before index creation?

**Answer:** The second insert fails with a unique key violation; creating the index on existing colliding data also fails.

### Exercise 9 — Sorting Item Codes

Default string sorting places `item10` before `item2`. Which collation option compares positive numeric segments by numeric value?

**Answer:** `numericOrdering:true` with a supported locale.

### Exercise 10 — Basic Text Index

Create a text index on `title`/`body` with weights `title: 10, body: 2`. Explain what weights do; can you add a second text index on `description`?

**Answer:** Weights tune relevance scoring; a collection allows only one legacy text index, though it can include multiple fields.

### Exercise 11 — OR and Phrase

Compare:

```javascript
{ $text: { $search: "mongodb indexing" } }
{ $text: { $search: "\"mongodb indexing\"" } }
```

**Answer:** Unquoted multi-word strings typically OR tokens; double quotes require an exact phrase.

### Exercise 12 — Negation

What does `$search:"mongodb -backup"` mean? Why should searching for literal SKUs containing hyphens use equality instead of `$text`?

### Exercise 13 — TextScore

Write a `$text` query returning `title` and `score`, sorted descending by `score`. What happens if you omit `.sort()`?

**Answer:** `$text` does not sort by relevance by default.

### Exercise 14 — Text Index Language

Does legacy `$text` include a built-in Vietnamese stemming language? What does `default_language:"none"` provide, and what does it lack?

**Answer:** Vietnamese is not in the supported stemmer list; `none` disables language-specific stemming and stop words, without turning into a full Vietnamese analyzer.

### Exercise 15 — Distinguishing `$text` and `$search`

A developer writes a `$search` aggregation stage on a MongoDB cluster without a Search service/index configured, though a legacy text index exists. Will it work? Why or why not?

**Answer:** Having only a legacy text index is not enough; `$search` requires MongoDB Search availability and a matching Search index.

### Exercise 16 — MongoDB Search Fuzzy

Write a `$search.text` example with `fuzzy.maxEdits:1`. Explain why you should never guarantee every typo will match.

### Exercise 17 — Autocomplete

To suggest titles while typing `"mong"`, is creating a Search index with a `"string"` field mapping sufficient?

**Answer:** No; an `autocomplete` mapping and corresponding operator are required.

### Exercise 18 — Vietnamese

Design a test suite for searching `"Cà phê sữa"`, `"ca phe sua"`, `"cà Phê Sữa"`, `"cafe sua"`, and names containing `đ`/`d`. Which layers must test ICU collation, normalized keys, and Search analyzers?

### Exercise 19 — Query Performance

Run `explain("executionStats")` for equality, collation-aware equality, prefix regex, and substring regex. Which metrics matter more than simply seeing `IXSCAN`?

**Answer:** Keys/docs examined, `nReturned`, latency/p95/p99, and index size.

### Exercise 20 — Comprehensive Architecture Choice

Build a product search system with these requirements:

- SKU must be globally unique.
- Product title is displayed with diacritics.
- Case-insensitive name filtering.
- Vietnamese alphabetical sorting.
- Autocomplete and fuzzy matching.
- Relevance ranking combining title and description.
- Tenant data isolation.
- Awareness of when the search index has not yet caught up with recent writes.

Propose the schema, B-tree/collation/Search indexes, API routing, and security controls; explain why no single index can satisfy all requirements.

## 29. Summary

**String matching**, **collation**, and **full-text search** are three distinct layers:

1. **Equality/B-tree:** matches exact whole-field values; ideal for IDs, codes, and normalized keys.
2. **Regex:** tests character patterns; case-sensitive prefixes can be B-tree optimized, while contains and `/i` are usually more expensive.
3. **Collation:** rules for equality, sorting, and uniqueness by locale and strength. Collation neither tokenizes nor ranks text.
4. **Legacy `$text` + text index:** token-based search with stemming/stop words for supported languages, phrases, negation, and `textScore`; limited to one text index per collection.
5. **MongoDB Search `$search`:** advanced search using dedicated Search indexes/analyzers, relevance, fuzzy matching, autocomplete, phrases, synonyms, and filtering; requires a supported deployment and configuration.

For Vietnamese, distinguish **ICU collation locale `vi`** from **legacy text index languages**: support in the former does not imply Vietnamese stemming in the latter. When semantic search, typeahead, or accent-insensitive matching is critical, verify analyzers and normalization against real data.

**Final rule of thumb:** Clarify whether the product needs **exact equality**, **substring/character matching**, **locale-based comparison/sorting**, or **relevance-ranked word/phrase search**—only then pick the index and API.

### Official MongoDB Documentation

- [Comparison/Collation](https://www.mongodb.com/docs/manual/reference/collation/) — ICU rules, `strength`, `caseLevel`, `numericOrdering`, and index matching.
- [Collation Locales and Defaults](https://www.mongodb.com/docs/manual/reference/collation-locales-defaults/) — `vi`, `en`, `fr` locales and option defaults.
- [Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/) — matching collation indexes and regex limitations.
- [`$regex` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/regex/) — syntax, prefix optimization, and case-insensitive regex.
- [Text Search](https://www.mongodb.com/docs/manual/text-search/) — distinguishing legacy `$text` and MongoDB Search.
- [`$text` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/) — OR/phrase/negation/score and limitations.
- [Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/) — single text index, compound index rules, and binary collation.
- [Text Search Languages](https://www.mongodb.com/docs/manual/reference/text-search-languages/) — list of legacy stemming languages.
- [Specify Text Index Language](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/specify-text-index-language/) — English and `default_language: "none"`.
- [MongoDB Search `$search` Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/search/) — supported deployments and pipelines.
- [MongoDB Search Text Operator](https://www.mongodb.com/docs/search/query/operators-collectors/text/) — analyzers, fuzzy matching, and query semantics.
- [Search Autocomplete and Partial Match](https://www.mongodb.com/docs/search/tutorial/partial-match/) — autocomplete, phrase, regex, and wildcard.
- [Create a MongoDB Search Index](https://www.mongodb.com/docs/atlas/atlas-search/create-index/) — index definitions and builds.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness constraints on collections.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plans and `executionStats`.
