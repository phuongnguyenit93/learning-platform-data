# Text Indexes, $text, textScore, and Supported Languages in MongoDB

## 1. Problem Statement and Learning Objectives

An application storing articles, products, or technical documentation often needs to find documents containing relevant words in `title`, `description`, `body`, or `tags`. Using only an equality predicate:

~~~javascript
db.articles.find({ title: "MongoDB text search basics" });
~~~

only finds records whose `title` value matches the condition exactly. However, users may type a few words like `mongo search`, search for a phrase inside the content, or expect results with matching titles to rank higher.

MongoDB provides **legacy text search** capabilities consisting of:

- **Text index:** indexes words/tokens in string fields.
- **`$text` query operator:** performs searches against the text index.
- **`$meta:"textScore"`:** accesses the relevance score and supports sorting by it.
- **Language:** affects tokenization, stop words, and stemming.

This lesson belongs to the **Text Search** chapter of the **Database Engine Document MongoDB** module, titled **Text Indexes, $text, textScore, and Supported Languages**.

After this lesson, you will be able to:

1. Create single-field and multi-field text indexes and verify them with `getIndexes()`.
2. Distinguish `$text` from equality, `$regex`, and MongoDB Search.
3. Use `$search` to match single words, multiple words, exact phrases, and negated terms.
4. Understand token/OR combination, stemming, stop words, and substring-matching limitations.
5. Use `textScore` in projection, sorting, and aggregation.
6. Prioritize fields using `weights` without treating scores as probabilities.
7. Configure `default_language` and `language_override` to handle multilingual documents.
8. Understand the languages supported by `$text`, especially its limitations with Vietnamese.
9. Design compound text indexes with equality prefixes in multi-tenant systems.
10. Know the key restrictions: one text index per collection, no `hint()` with `$text`, aggregation rules, and collation.
11. Implement text search in `mongosh` and the Java Sync Driver, handle errors, and choose better-suited tools when requirements are advanced.

**Key takeaway:** A text index is a **token- and language-based search mechanism**, not "LIKE any arbitrary substring." `textScore` is a relevance score computed for the **current query**; it does not represent a percentage match and does not dictate result order unless you explicitly sort by it.

## 2. Distinguishing Four Search Approaches

Consider the document:

~~~javascript
{
  _id: 1,
  title: "Wireless mouse for laptop",
  description: "Comfortable Bluetooth mouse for daily work"
}
~~~

| Approach | Example | Meaning |
|---|---|---|
| Equality | `{title:"Wireless mouse for laptop"}` | Field value equals the condition |
| Regex | `{title:/mouse/i}` | Matches a regular expression against the string |
| Native text search | `{$text:{$search:"wireless mouse"}}` | Matches text-indexed tokens according to language rules |
| MongoDB Search | `$search` aggregation stage | Dedicated search with analyzers, autocomplete/fuzzy, facets, etc., on supported deployments |

### 2.1. Text Search Differs from Regex

`$regex` is useful for pattern matching, but it does not provide stemming, stop words, or relevance scoring like `$text`.

Conversely, a text index cannot replace every regex. If you need to match the middle of an SKU like `"ABC-123"` as a substring, a text index may not work because it indexes tokens rather than arbitrary substrings.

### 2.2. Text Search Differs from MongoDB Search

The naming can easily cause confusion:

~~~javascript
// Native text query: $text contains the $search parameter.
{ $text: { $search: "wireless mouse" } }
~~~

and:

~~~javascript
// MongoDB Search: the $search aggregation stage.
{
  $search: {
    index: "product_search",
    text: {
      query: "wireless mouse",
      path: ["title", "description"]
    }
  }
}
~~~

These are **two different mechanisms** using **two different index types**. The `$search` stage example only runs when the MongoDB environment has MongoDB Search deployed and the corresponding search index created.

Current MongoDB documentation recommends MongoDB Search for new and advanced full-text requirements; native `$text` remains suitable for simple keyword search or environments without a dedicated search index deployment.

## 3. Creating a Self-Contained Practice Dataset

Use a dedicated database in `mongosh`:

~~~javascript
use text_search_lab
~~~

The examples assume a fresh, empty collection. If the collection already exists, inspect it before inserting or indexing; never drop a production collection just to run a lab.

Insert documents with fixed IDs:

~~~javascript
const articles = [
  {
    _id: 1,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "MongoDB text search basics",
    body: "Learn to build a text index and search document content.",
    tags: ["database", "tutorial"],
    publishedAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: 2,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "Text indexing and relevance",
    body: "Search engines rank articles using text relevance scores.",
    tags: ["search", "database"],
    publishedAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: 3,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "Wireless mouse buying guide",
    body: "Choose a comfortable mouse and compare wireless models.",
    tags: ["hardware", "guide"],
    publishedAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: 4,
    tenantId: "tenant-A",
    status: "draft",
    lang: "english",
    title: "MongoDB performance checklist",
    body: "Tune database indexes, projections, and query plans.",
    tags: ["database", "performance"],
    publishedAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: 5,
    tenantId: "tenant-B",
    status: "published",
    lang: "english",
    title: "Database indexing for beginners",
    body: "Database indexes help queries find documents efficiently.",
    tags: ["database", "beginner"],
    publishedAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: 6,
    tenantId: "tenant-A",
    status: "published",
    lang: "none",
    title: "Hướng dẫn tìm kiếm văn bản MongoDB",
    body: "Ví dụ tìm kiếm tiếng Việt có dấu trong dữ liệu.",
    tags: ["mongo", "tìm kiếm"],
    publishedAt: ISODate("2026-10-06T08:00:00Z")
  },
  {
    _id: 7,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "MongoDB text search practice",
    body: "Practice keyword searches and matching exact phrases.",
    tags: ["tutorial", "search"],
    publishedAt: ISODate("2026-10-07T08:00:00Z")
  },
  {
    _id: 8,
    tenantId: "tenant-B",
    status: "archived",
    lang: "english",
    title: "Search index migration",
    body: "Plan index rebuilds and application rollouts.",
    tags: ["search", "migration"],
    publishedAt: ISODate("2026-10-08T08:00:00Z")
  }
];

db.articles.insertMany(articles);
~~~

When starting from an empty collection:

- There are **8** articles.
- `tenant-A` has 6 articles; `tenant-B` has 2.
- `tenant-A` has 5 published and 1 draft article.
- `tenant-A` includes 1 Vietnamese document marked `lang:"none"`.
- `title` and `body` are Strings; `tags` is an array of Strings.

Verify:

~~~javascript
db.articles.countDocuments({});
db.articles.find(
  {},
  { _id: 1, tenantId: 1, lang: 1, title: 1 }
).sort({ _id: 1 });
~~~

**Note:** Running `insertMany(articles)` a second time will raise a duplicate `_id` error on a regular collection because the IDs already exist. This is **unrelated** to text indexes.

## 4. Creating a Single-Field Text Index

A simple index:

~~~javascript
db.articles.createIndex(
  { title: "text" },
  { name: "idx_title_text" }
);
~~~

Then search:

~~~javascript
db.articles.find({
  $text: { $search: "MongoDB" }
});
~~~

`$text` only searches fields included in the text index. If the index only includes `title`, words appearing solely in `body` are not indexed for that text query.

### 4.1. Inspecting the Text Index

~~~javascript
db.articles.getIndexes();
~~~

You will see the index named `idx_title_text` and special metadata keys specific to text indexes. Depending on server version, the output may include `weights`, `default_language`, `language_override`, and `textIndexVersion`.

Do not infer from an index name that it covers every field: inspect the actual `weights` and definition.

### 4.2. At Most One Text Index per Collection

MongoDB allows **at most one text index** per collection. Therefore, do **not** attempt to create a second standalone text index on `body` when `idx_title_text` already exists:

~~~javascript
// Do not create a second independent text index on the same collection.
db.articles.createIndex({ body: "text" });
~~~

To search across `title`, `body`, and `tags`, you must create **one multi-field text index**.

### 4.3. Switching from Single-Field to Multi-Field Index

In the lab environment, after running the single-field example, drop that specific lab index:

~~~javascript
db.articles.dropIndex("idx_title_text");
~~~

Then create the new index in the next section. This is a sensitive DDL operation: never drop a production application's text index without a planned downtime or index replacement rollout strategy.

## 5. A Multi-Field Text Index and Weights

The single text index on `articles` used for most of this lesson:

~~~javascript
db.articles.createIndex(
  {
    title: "text",
    body: "text",
    tags: "text"
  },
  {
    name: "idx_article_search",
    default_language: "english",
    language_override: "lang",
    weights: {
      title: 10,
      tags: 4,
      body: 1
    }
  }
);
~~~

Here:

- `title`, `body`, and `tags` belong to **one index**.
- `title` has weight 10.
- `tags` has weight 4.
- `body` has weight 1.
- `default_language:"english"` applies when a document does not provide a language override.
- `language_override:"lang"` tells MongoDB to read the document's `lang` field to determine which language rules apply.
- Documents with `lang:"none"` use the mode with no stemming or stop words.

### 5.1. What Weights Mean

Suppose the word `MongoDB` appears in the `title` of article A, but only in the `body` of article B. All else being equal, article A can score higher because `title` has a larger weight.

**Weights do not mean `title` must match for a document to be found.** `body` is still indexed and can still match a document.

### 5.2. Weights Are Not a Simple Fixed Multiplication Formula

Do not treat a simplified formula like:

~~~text
score = 10 * matched terms in title
      + 4 * matched terms in tags
      + 1 * matched terms in body
~~~

as a MongoDB guarantee. The server uses its own relevance calculation influenced by term frequency, match strength, and server version. Weights are a **relative signal** of field importance, not an exact scoring contract.

### 5.3. Weight Range

MongoDB supports integer weights from **1 to 99,999**. The default weight for an indexed field if omitted is 1.

Avoid assigning an extreme weight to `title` just to "guarantee it always ranks first" without evaluating actual results. If strict business-rule prioritization is needed, build dedicated business ranking logic or query pipelines.

### 5.4. String Arrays Can Participate in a Text Index

`tags` in the sample dataset is an array of Strings:

~~~javascript
tags: ["database", "tutorial"]
~~~

A text index indexes strings inside arrays. However, it does not automatically turn complex nested objects or arrays into high-quality searchable text the way a dedicated analyzer can.

## 6. $text: Basic Syntax and Prerequisites

Text query:

~~~javascript
db.articles.find({
  $text: {
    $search: "database"
  }
});
~~~

Prerequisites:

1. The collection must have a valid text index.
2. `$search` must be a String.
3. `$language`, `$caseSensitive`, and `$diacriticSensitive` may be configured where supported.
4. A query may contain at most **one `$text` expression**.

Full structure:

~~~javascript
db.articles.find({
  $text: {
    $search: "text search",
    $language: "english",
    $caseSensitive: false,
    $diacriticSensitive: false
  }
});
~~~

### 6.1. Do Not Specify a Field Inside $text

Do not write:

~~~javascript
// Invalid syntax/semantics:
db.articles.find({
  $text: {
    field: "title",
    $search: "MongoDB"
  }
});
~~~

Searchable fields are **defined in the text index**. If you need to search only `title`, use an appropriately configured collection/index or a search engine supporting flexible path-level filtering.

### 6.2. Combining Regular Filters

~~~javascript
db.articles.find({
  tenantId: "tenant-A",
  status: "published",
  $text: { $search: "database" }
});
~~~

The `tenantId` and `status` predicates filter the text query results. In multi-tenant systems, the backend must derive the tenant from the authenticated user session rather than trusting an arbitrary client-supplied `tenantId`.

### 6.3. Can It Search Unindexed Fields?

Suppose a document has `internalNote:"database migration"`, while the text index only covers `title`, `body`, and `tags`. `$text` will not match via `internalNote` unless the term also appears in the indexed fields.

## 7. Multiple Words: Default Is OR

A text query:

~~~javascript
db.articles.find({
  $text: {
    $search: "database wireless"
  }
});
~~~

effectively finds documents containing **one or more** of the search terms according to tokenization and language rules. Do not assume both words are required.

With the sample dataset:

- Articles about databases match via `database`.
- The article about wireless mice matches via `wireless`.
- No document has to contain both.

### 7.1. Why Spaces Are Not Treated as AND

In native `$text`, a space-separated string of unquoted words does not mean "all words." MongoDB applies a logical **OR** across terms by default.

If a search screen requires **all terms must match**, you cannot simply write:

~~~javascript
$search: "word1 word2"
~~~

and claim it performs an AND. You must design specifically around MongoDB semantics or move to MongoDB Search, which expresses boolean logic more clearly.

### 7.2. Stemming Transforms Word Forms

With the English analyzer, words sharing a common stem are treated as related. For instance, `index` and `indexing` may map to the same stem; verify the exact behavior on real data.

### 7.3. Text Search Is Not Prefix Matching

If the index contains `blueberry`, searching `blue` will not match by default. Text search operates on words/tokens and stems rather than indexing every prefix.

This matters significantly for autocomplete, proper names, and SKUs.

## 8. Exact Phrase Matching with Double Quotes

To search for a multi-word phrase in exact order:

~~~javascript
db.articles.find({
  $text: {
    $search: "\"text search\""
  }
});
~~~

In JavaScript, `"\"text search\""` embeds double quotes inside the `$search` string value.

Example:

~~~javascript
const phrase = '"text search"';

db.articles.find({
  $text: { $search: phrase }
});
~~~

### 8.1. Difference Between Term OR and Phrase

| Search String | Primary Meaning |
|---|---|
| `text search` | Matches documents containing at least one of the terms |
| `"text search"` | Matches the phrase according to ordering/phrase semantics |
| `"wireless mouse"` | Matches the phrase wireless mouse |
| `"database index"` | Matches the phrase database index |

Stemming and stop-word rules can still apply depending on language and version. "Exact phrase" in `$text` does not mean raw byte-for-byte substring matching.

### 8.2. Mixing Phrases and Individual Terms

~~~javascript
db.articles.find({
  $text: {
    $search: "\"wireless mouse\" guide"
  }
});
~~~

Per MongoDB documentation, when a quoted multi-word phrase is combined with other terms, a document must contain the **multi-word phrase** to match. Do not interpret this string as a simple OR between `"wireless mouse"` and `guide` that ignores the phrase requirement.

### 8.3. A Quoted Phrase Does Not Restrict to Title

A text index covering `title`, `body`, and `tags` can match the phrase in any indexed field according to query rules. To restrict matches to a specific field with flexible query syntax, consider a `$search` stage with `path`.

## 9. Negation with a Minus Sign

Native text search allows negating terms using `-`.

~~~javascript
db.articles.find({
  $text: {
    $search: "mongodb -performance"
  }
});
~~~

Idea: find documents containing the term `MongoDB` while excluding documents containing `performance` in their indexed text.

### 9.1. At Least One Positive Term Is Required

~~~javascript
// Negation only: matches no documents.
db.articles.find({
  $text: {
    $search: "-performance"
  }
});
~~~

According to the MongoDB Manual, a search string consisting solely of negated terms matches zero documents.

### 9.2. Multiple Negations Combine as Exclusion

If the search is:

~~~text
database -beginner -migration
~~~

the negated terms exclude documents containing any of them. This is neither SQL `NOT LIKE` syntax nor a full boolean parser.

### 9.3. Hyphens in Compound Words

Searching:

~~~text
pre-market
~~~

does not necessarily negate `market`. MongoDB distinguishes hyphenated words from a standalone minus sign used for negation based on syntax and position.

Explicit negation example:

~~~text
pre -market
~~~

In applications where users might enter a minus sign as part of a product name, decide whether the UI should expose it as a negation operator.

## 10. textScore: What Is a Relevance Score?

When executing `$text`, MongoDB can attach **textScore** metadata to matching documents. This represents a relevance metric between the document and the search query based on the index and rules.

Do not interpret it as:

~~~text
score = 0.87 => 87% probability the document is correct
~~~

No such guarantee exists. Scores are used to **compare relative relevance within the same search context**.

### 10.1. Results Are Not Sorted by Score by Default

~~~javascript
db.articles.find({
  $text: { $search: "mongodb" }
});
~~~

Never assume the first returned document is the most relevant. For relevance ordering, you must sort explicitly.

### 10.2. Projecting the Score

~~~javascript
db.articles.find(
  {
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    tenantId: 1,
    score: { $meta: "textScore" }
  }
);
~~~

The `score` field is populated from query metadata, not read from a stored field on the document.

### 10.3. Sorting by Score

~~~javascript
db.articles.find(
  {
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
});
~~~

MongoDB sorts in **descending** relevance order when sorting by `textScore` metadata.

### 10.4. Adding a Tie-Breaker

~~~javascript
db.articles.find(
  {
    tenantId: "tenant-A",
    status: "published",
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" },
  _id: 1
});
~~~

`_id` acts as a tie-breaker for documents sharing the same score, stabilizing pagination and comparisons. As data or the index changes, scores and positions can still shift.

### 10.5. Can Scores Be Compared Across Queries?

Do not compare the score from query `"mongodb"` against the score from query `"wireless"` as if they share a globally normalized scale.

A score is meaningful only within a specific query, index, and dataset. Adding documents, tuning weights, or rebuilding the index can change rankings.

## 11. textScore in an Aggregation Pipeline

`$text` can be used inside `$match` in aggregation. However, the `$match` containing `$text` must be the **first stage** in the pipeline.

Example:

~~~javascript
db.articles.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "published",
      $text: { $search: "mongodb" }
    }
  },
  {
    $addFields: {
      relevance: { $meta: "textScore" }
    }
  },
  {
    $sort: {
      relevance: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      tenantId: 1,
      relevance: 1
    }
  },
  { $limit: 10 }
]);
~~~

`$addFields` reads the metadata after the initial `$match`, exposing the score as a regular pipeline field.

### 11.1. Sorting Directly by $meta in Aggregation

You can write:

~~~javascript
db.articles.aggregate([
  {
    $match: {
      $text: { $search: "search" }
    }
  },
  {
    $sort: {
      score: { $meta: "textScore" }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "textScore" }
    }
  }
]);
~~~

### 11.2. Invalid Example: Text Match in a Later Stage

~~~javascript
// Invalid for aggregation $text:
db.articles.aggregate([
  { $project: { title: 1, body: 1 } },
  { $match: { $text: { $search: "mongodb" } } }
]);
~~~

The `$match` containing `$text` must come first, before any other stage.

### 11.3. Do Not Wrap $text in $or or $not Inside a Pipeline

Invalid example:

~~~javascript
db.articles.aggregate([
  {
    $match: {
      $or: [
        { $text: { $search: "mongodb" } },
        { status: "published" }
      ]
    }
  }
]);
~~~

In aggregation, a text expression cannot appear inside `$or` or `$not`. Combine supported predicates with the text expression at the appropriate top level, or choose a different search mechanism.

### 11.4. Metadata Only Exists When a Text Query Runs

You cannot evaluate `{$meta:"textScore"}` in a pipeline that has no `$text` matching context and expect MongoDB to score documents out of thin air.

## 12. Stop Words and Stemming

A text index does not merely split strings on spaces and store every word verbatim.

### 12.1. Stop Words

English includes common words such as:

~~~text
the
and
a
an
~~~

These words may be stripped from the text index because they add little discriminative value.

Example:

~~~javascript
db.englishNotes.insertMany([
  { _id: 1, text: "the cat and the dog" },
  { _id: 2, text: "a blue cat" }
]);

db.englishNotes.createIndex(
  { text: "text" },
  { default_language: "english" }
);
~~~

Searching solely for `the` may return no results because it is treated as a stop word by the English processor.

### 12.2. Stemming

Inflected word forms sharing a root are conflated by the stemmer. For example, English can relate `blueberry` and `blueberries` by their stem.

However, `blue` is not an automatic prefix match for `blueberry`; it will not match just because it is a leading substring.

### 12.3. Stop Words Are Language-Specific

The word `hay` is a stop word in Spanish. Spanish and English documents follow different language-specific rules.

Thus, `default_language` and `language_override` are not merely UI metadata; they alter **which tokens get indexed**.

### 12.4. Tokenization Is Not General Multilingual NLP

Text indexes do not natively provide synonym dictionaries, fuzzy typo tolerance, optimal Vietnamese word segmentation, rich autocomplete, or AI ranking. If your application needs these capabilities, evaluate MongoDB Search.

## 13. Languages Supported by $text

The MongoDB Manual lists **15 languages** with native `$text` rule support:

| Language Name | Code | Notes |
|---|---|---|
| `danish` | `da` | Danish |
| `dutch` | `nl` | Dutch |
| `english` | `en` | English |
| `finnish` | `fi` | Finnish |
| `french` | `fr` | French |
| `german` | `de` | German |
| `hungarian` | `hu` | Hungarian |
| `italian` | `it` | Italian |
| `norwegian` | `nb` | Norwegian |
| `portuguese` | `pt` | Portuguese |
| `romanian` | `ro` | Romanian |
| `russian` | `ru` | Russian |
| `spanish` | `es` | Spanish |
| `swedish` | `sv` | Swedish |
| `turkish` | `tr` | Turkish |

You can specify either the full language name or its supported code. For example:

~~~javascript
db.articles.find({
  $text: {
    $search: "database",
    $language: "english"
  }
});
~~~

or:

~~~javascript
db.articles.find({
  $text: {
    $search: "database",
    $language: "en"
  }
});
~~~

### 13.1. Vietnamese Is Not Among These 15 Native Languages

Do **not** write:

~~~javascript
// Not a supported language in native $text.
db.articles.find({
  $text: {
    $search: "tìm kiếm",
    $language: "vietnamese"
  }
});
~~~

Likewise, `$language:"vi"` is not in the supported language list for native text search.

### 13.2. Can Vietnamese Text Be Searched with $text?

You can use **`default_language:"none"`** or a per-document override `"none"` to index tokens without English stemming or stop words.

Example in the dataset:

~~~javascript
{
  _id: 6,
  lang: "none",
  title: "Hướng dẫn tìm kiếm văn bản MongoDB"
}
~~~

That **does not** mean MongoDB has an analyzer that understands Vietnamese compound word structure.

For example, `"tìm kiếm"` contains two space-separated syllables that form a single lexical unit in Vietnamese. The native tokenizer does not perform Vietnamese word segmentation like a dedicated NLP engine.

### 13.3. Vietnamese Diacritics and textIndexVersion

A standard text index version 3 is **diacritic-insensitive** by default. However, do not mistake that for "full Vietnamese language support."

Case/diacritic normalization and **linguistic analysis** are two different things. Stripping diacritics can cause distinct Vietnamese words with different meanings to collide.

## 14. default_language When Creating an Index

If omitted, `default_language` on a text index defaults to `"english"`.

~~~javascript
db.englishNotes.createIndex(
  { text: "text" }
);
~~~

This applies English rules to documents that have no override.

To create a Spanish index:

~~~javascript
db.spanishNotes.insertMany([
  { _id: 1, text: "La suerte protege a los audaces." },
  { _id: 2, text: "Nada hay más surrealista que la realidad." }
]);

db.spanishNotes.createIndex(
  { text: "text" },
  {
    default_language: "spanish",
    name: "idx_spanish_text"
  }
);
~~~

Spanish stop words and stemming rules apply. For instance, `hay` may be skipped, while accented words can match unaccented search terms due to version-3 diacritic-insensitive semantics.

### 14.1. When to Change default_language

- Most documents share the same supported language.
- You want stemming and stop words for that specific language.
- Documents without an override field will inherit this default.

### 14.2. Risk of Using English Default for Vietnamese

If the data is purely Vietnamese, English stop words and stemming misrepresent Vietnamese text. `none` is generally safer for simple token lookups; MongoDB Search with an appropriate analyzer is usually better for sophisticated Vietnamese search products.

### 14.3. Changing Index Language Is Not a Simple Metadata Update

To change `default_language` or weights on an existing text index, you typically need a plan to **drop and recreate the text index**. You cannot simply update a configuration field and expect previously indexed tokens to reprocess under the new language automatically.

## 15. language_override: Multilingual Documents

A collection may contain English, Spanish, French, and unstemmed content together.

Example:

~~~javascript
db.multilingualDocs.insertMany([
  {
    _id: 1,
    lang: "english",
    text: "Blueberries and apples"
  },
  {
    _id: 2,
    lang: "spanish",
    text: "La realidad y la suerte"
  },
  {
    _id: 3,
    lang: "none",
    text: "Tìm kiếm tài liệu tiếng Việt"
  }
]);
~~~

Index:

~~~javascript
db.multilingualDocs.createIndex(
  { text: "text" },
  {
    name: "idx_multilingual_text",
    default_language: "english",
    language_override: "lang"
  }
);
~~~

With this configuration:

- Document 1 is processed using English.
- Document 2 is processed using Spanish.
- Document 3 is processed using `none`.
- Documents missing `lang` fall back to the English default.

### 15.1. language_override Is a Field Name, Not a Language Value

~~~javascript
language_override: "lang"
~~~

means "read the `lang` field inside each document." It does not mean "use a language named `lang`."

### 15.2. If language_override Is Omitted

The default override field name is `language`.

A document:

~~~javascript
{
  title: "Example",
  language: "spanish"
}
~~~

will be processed as Spanish by the text index even if you did not explicitly declare `language_override`, because the index checks that default field.

### 15.3. Avoid Accidentally Using a `language` Field for Something Else

If a business document contains `language:"unknown"` or an invalid language value, text indexing may fail on write.

A safer practice is to keep a dedicated field such as `textLanguage` or `lang` holding strictly controlled values, and configure `language_override` to point to it.

### 15.4. Query $language and Index-Time Language Play Different Roles

- **Index time:** language rules decide which tokens are indexed for each document.
- **Query time:** `$language` controls how the query's search terms are parsed and stemmed.

Changing `$language` at query time **does not** rewrite index entries already built under a different language. For reliable results, align index-time and document languages from the start.

## 16. The `none` Language Mode

`none` is a special language value:

~~~javascript
db.plainTokens.insertMany([
  { _id: 1, text: "the blue berries" },
  { _id: 2, text: "and blueberry" }
]);

db.plainTokens.createIndex(
  { text: "text" },
  {
    name: "idx_plain_tokens",
    default_language: "none"
  }
);
~~~

Characteristics:

- No language-specific stemmer is applied.
- No language-specific stop-word list is removed.
- Strings are still tokenized—it does not turn a text index into an exact-substring index.
- Does not add advanced Unicode Vietnamese word segmentation.

### 16.1. An Easy-to-Spot Example

With the English default, `the` is omitted from the index; with `none`, it remains indexed as a token.

~~~javascript
db.plainTokens.find({
  $text: {
    $search: "the",
    $language: "none"
  }
});
~~~

### 16.2. `none` Does Not Enable caseSensitive or diacriticSensitive

`none` controls stemming and stop words. Case and diacritic sensitivity are separate `$text` query options, and behavior also depends on the text index version.

Do not assume `default_language:"none"` forces Vietnamese to match accents and letter case strictly.

### 16.3. When Is `none` Appropriate?

- Short word-like identifiers where English stemming is undesirable.
- Content in languages lacking a native stemmer.
- Simple keyword lookups where every token should be preserved.
- Mixed-language data where no single analyzer fits, provided limitations are understood.

## 17. Case Sensitivity

Text index version 3 is case-insensitive by default.

Example:

~~~javascript
db.articles.find({
  $text: {
    $search: "MongoDB"
  }
});
~~~

Matches tokens regardless of letter casing per index semantics.

Enable case sensitivity:

~~~javascript
db.articles.find({
  $text: {
    $search: "MongoDB",
    $caseSensitive: true
  }
});
~~~

### 17.1. Performance Impact

Because the index itself is case-insensitive, MongoDB may retrieve candidate matches from the index and then post-filter by case. Enabling `$caseSensitive:true` can therefore increase processing cost.

### 17.2. Case Sensitivity Is Not Fuzzy Matching

`$caseSensitive:true` does not provide typo correction, synonyms, or autocomplete. It controls only one aspect of matching.

### 17.3. Do Not Confuse with Collation

A text index requires simple/binary collation in its index definition, yet text search applies case/diacritic folding per the text index version. These two statements do not contradict each other.

## 18. Diacritic Sensitivity and Accented Text

Text index version 3 is diacritic-insensitive by default. Characters such as `é`, `ê`, and `e` can be folded without distinguishing accents at the index level.

To enforce diacritic sensitivity:

~~~javascript
db.articles.find({
  $text: {
    $search: "café",
    $diacriticSensitive: true
  }
});
~~~

### 18.1. Why Does This Matter for Vietnamese?

Vietnamese has distinct words whose meanings change with tone marks and vowel accents, so an unaccented query string can match many unrelated candidates. Accent-insensitive matching increases recall at the expense of precision.

If an application requires exact diacritic matching, you can pass `$diacriticSensitive:true` with a version-3 text index. Still, this does not overcome the lack of Vietnamese tokenization and stemming.

### 18.2. How Older Versions Differ

Text index version 3 is diacritic-insensitive by default, whereas earlier text index versions behaved differently (earlier versions were diacritic-sensitive).

Do not treat test results from an old collection with `textIndexVersion:2` as representative of a modern version-3 text index.

### 18.3. Potential Extra Cost

Like case-sensitive search, requiring diacritic sensitivity against a folded index can force extra filtering and slow down queries.

## 19. textIndexVersion and Compatibility

MongoDB has had multiple text index versions:

| Version | Historical Context |
|---|---|
| v1 | Introduced in MongoDB 2.4 |
| v2 | Introduced in MongoDB 2.6 |
| v3 | Introduced in MongoDB 3.2; default on modern versions |

MongoDB documentation recommends using the default text index version unless you have a specific compatibility reason.

Example of what not to do arbitrarily:

~~~javascript
db.articles.createIndex(
  { title: "text" },
  { textIndexVersion: 1 }
);
~~~

on modern deployments.

### 19.1. Why Version Matters

The version affects token normalization, case/diacritic handling, and index internals. During server upgrades, do not assume an index created years ago behaves identically in every detail to a newly created index.

### 19.2. Inspection

~~~javascript
db.articles.getIndexes();
~~~

Look for `textIndexVersion` in the index definition and cross-reference the MongoDB Manual for your exact server version.

## 20. Compound Text Indexes: Combining Equality Filters with Text

A large collection may contain multiple tenants and `published`/`draft` statuses. If most queries filter by `tenantId` and `status`, consider a compound text index with an equality prefix.

**Important:** The `articles` collection already has a text index. Do not create a **second text index** on it. Use a separate lab collection:

~~~javascript
use text_search_lab

db.createCollection("tenantDocs");

db.tenantDocs.insertMany([
  {
    _id: 1,
    tenantId: "tenant-A",
    status: "published",
    title: "MongoDB index design",
    body: "Create efficient search indexes"
  },
  {
    _id: 2,
    tenantId: "tenant-A",
    status: "draft",
    title: "MongoDB text search draft",
    body: "Draft documentation"
  },
  {
    _id: 3,
    tenantId: "tenant-B",
    status: "published",
    title: "Search engines overview",
    body: "Compare text search strategies"
  }
]);
~~~

Create **one** compound text index:

~~~javascript
db.tenantDocs.createIndex(
  {
    tenantId: 1,
    status: 1,
    title: "text",
    body: "text"
  },
  {
    name: "idx_tenant_status_text",
    default_language: "english"
  }
);
~~~

### 20.1. Equality Required on Prefix Keys Before Text Fields

Query:

~~~javascript
db.tenantDocs.find({
  tenantId: "tenant-A",
  status: "published",
  $text: {
    $search: "mongodb"
  }
});
~~~

supplies equality conditions for both `tenantId` and `status`, which precede the text keys in the compound index.

If `status` is omitted:

~~~javascript
// May fail to use the compound text index as required.
db.tenantDocs.find({
  tenantId: "tenant-A",
  $text: { $search: "mongodb" }
});
~~~

per MongoDB's restriction: a `$text` query must include **equality conditions for all index keys preceding the text key**.

### 20.2. Why Compound Text Indexes Are Useful

Suppose you have 20 million documents across many tenants. If business queries always scope by tenant and status before searching text, the equality prefix shrinks the portion of text index entries that must be scanned.

### 20.3. Prefix Design Trade-Offs

If other screens in the application search across **all statuses** or **all tenants**, an index prefixed with `tenantId,status` cannot serve those queries.

Never pick a compound prefix based on a single endpoint while ignoring others. Because a collection allows only one text index, this is a critical architectural decision.

### 20.4. Text Keys Must Be Contiguous

When creating a compound index with multiple text fields, all text keys must be placed **contiguously** in the index specification.

Valid example:

~~~javascript
{
  tenantId: 1,
  title: "text",
  body: "text",
  publishedAt: -1
}
~~~

Do not insert a regular key between two text fields:

~~~javascript
// Invalid because the two text keys are not contiguous.
{
  tenantId: 1,
  title: "text",
  publishedAt: -1,
  body: "text"
}
~~~

### 20.5. Cannot Arbitrarily Combine with Other Special Index Types

Per MongoDB restrictions, a compound text index cannot be combined arbitrarily with other special index types such as geospatial or multikey-incompatible structures.

If you need combined geospatial and advanced full-text search, consider MongoDB Search or separate query designs rather than forcing everything into one native compound text index.

## 21. Does a Text Index Support Sorting Like a Regular B-Tree?

**No.** The MongoDB Manual notes that text indexes do not improve sort performance—even for compound text indexes.

That does not prevent calling `sort()`:

~~~javascript
db.articles.find({
  $text: { $search: "database" }
}).sort({ publishedAt: -1 });
~~~

However, do not assume the text index provides pre-sorted `publishedAt` order to avoid sort work.

### 21.1. Sorting by textScore Is Relevance Sorting

~~~javascript
db.articles.find(
  { $text: { $search: "database" } },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({ score: { $meta: "textScore" } });
~~~

### 21.2. Sorting by a Regular Field Is a Different Use Case

An application might offer two modes:

- **Relevance:** sort by `textScore`.
- **Latest:** sort by `publishedAt`.

Do not assume both modes share the same execution plan or cost. Combining relevance and recency requires an explicit ranking definition.

### 21.3. Use explain

~~~javascript
db.articles.find({
  $text: {
    $search: "database"
  }
}).sort({
  publishedAt: -1
}).explain("executionStats");
~~~

Depending on the MongoDB version, the plan shows stages for text matching and sorting; do not assume results emerge in index order.

## 22. Wildcard Text Indexes vs. Regular Wildcard Indexes

MongoDB can build a wildcard **text** index:

~~~javascript
db.anyFieldDocs.insertMany([
  { _id: 1, title: "Database guide", details: "Index tuning" },
  { _id: 2, summary: "Wireless mouse", notes: "Bluetooth accessories" }
]);

db.anyFieldDocs.createIndex(
  { "$**": "text" },
  {
    name: "idx_all_strings_text",
    default_language: "english"
  }
);
~~~

This index targets string fields across documents using wildcard text indexing.

**Distinction:**

~~~javascript
{ "$**": "text" }  // Wildcard TEXT index.
{ "$**": 1 }       // Regular wildcard index.
~~~

A regular `{"$**":1}` index does not support `$text`.

### 22.1. Risks of Text-Indexing All String Fields

- The index can grow very large.
- Indexes irrelevant fields such as statuses, codes, or low-value text.
- Can expose internal fields in matches if projection/permissions are not enforced.
- Hard to assign meaningful weights when schemas vary dynamically.
- Increases write amplification on document updates.

Only choose a wildcard text index with clear justification and measured workload impact. For stable schemas, naming specific fields in the text index is far easier to control.

### 22.2. Still Counts as the Single Text Index per Collection

A wildcard text index consumes the **one text index per collection** quota. You cannot add another standalone text index on `title` afterward.

## 23. Important Limitations of $text

| Limitation | Practical Impact |
|---|---|
| One text index per collection | Multiple searchable fields must be combined into one index |
| One `$text` expression per query | Cannot use two independent text predicates |
| `$text` disallowed inside `$nor` | That boolean form is unsupported |
| `$text` disallowed inside `$elemMatch` | Cannot target individual array elements that way |
| `$text` + `hint()` | Cannot specify an index hint on a text query |
| `$text` + `$natural` sort | Disallowed |
| `$or` clauses | Must satisfy MongoDB's index conditions across all branches |
| `$text` + operators needing other special indexes | Cannot combine arbitrarily with `$near` |
| Views | `$text` is not supported on views |
| Aggregation | `$match` with `$text` must be the first stage |
| Aggregation `$or`/`$not` | Cannot wrap text expressions in those operators |
| Text index sorting | Does not optimize regular field sorts |
| Compound prefix | Requires equality on all keys preceding text keys |
| Collation | Text indexes require simple/binary collation |

### 23.1. Example: Do Not Use hint

~~~javascript
// Do not use hint() with $text.
db.articles.find({
  $text: { $search: "mongodb" }
}).hint("idx_article_search");
~~~

When optimizing, adjust the index design and query shape instead of trying to force a hint on a text query.

### 23.2. One $text Expression Does Not Mean One Word

You can search multiple terms inside one `$text`:

~~~javascript
db.articles.find({
  $text: { $search: "database mongodb" }
});
~~~

Never write two independent `$text` expressions:

~~~javascript
// Invalid pattern:
{
  $and: [
    { $text: { $search: "database" } },
    { $text: { $search: "mongodb" } }
  ]
}
~~~

### 23.3. $text Is Not a General Text + Location Solution

You cannot arbitrarily combine `$text` with `$near`, which requires a geospatial special index. A "stores near me matching name..." feature needs an appropriate search/geospatial design.

### 23.4. Collation and Text Case-Insensitivity Are Not the Same

Text indexes require `simple` collation in their index configuration, while `$text` applies case/diacritic-insensitive folding according to its text index version. Do not conclude that a `simple` index collation forces text search to be case-sensitive.

## 24. Collation of a Text Index

If a collection was created with a non-simple default collation:

~~~javascript
db.createCollection("localeDocs", {
  collation: { locale: "en" }
});
~~~

creating a text index requires explicitly specifying `simple` collation:

~~~javascript
db.localeDocs.createIndex(
  { title: "text" },
  {
    name: "idx_locale_title_text",
    collation: { locale: "simple" }
  }
);
~~~

### 24.1. Why?

Text indexes do not support locale-based ICU collations like regular B-tree string indexes. They implement their own tokenization and normalization semantics.

### 24.2. Can You Search Vietnamese Using `vi` Collation?

You cannot put `collation:{locale:"vi"}` on a text index to enable a full Vietnamese stemmer.

If Vietnamese NLP is needed, evaluate a dedicated search analyzer/collection design and test real tokenization and diacritic behavior.

## 25. A Text Index Is Not a Unique Constraint

~~~javascript
db.articles.createIndex(
  { title: "text" }
);
~~~

does not enforce uniqueness on `title`.

Two documents with identical titles can coexist. If business rules require a unique slug or document code, create a dedicated unique B-tree index:

~~~javascript
db.articles.createIndex(
  { tenantId: 1, slug: 1 },
  { unique: true }
);
~~~

This is a **different index type**; it does not count toward the text index quota and enforces uniqueness on `(tenantId, slug)`.

### 25.1. Text Search Does Not Replace Data Validation

Documents where `body` is a Number or Date instead of a String will not automatically become searchable strings. Enforce schema and data types at ingestion time.

### 25.2. Text Search Does Not Replace Authorization

Draft documents or documents belonging to another tenant can still match inside the text index. The backend must filter by permissions:

~~~javascript
db.articles.find({
  tenantId: authenticatedTenantId,
  status: "published",
  $text: { $search: queryFromUser }
});
~~~

Here `authenticatedTenantId` and `queryFromUser` are application variables, not unverified values taken blindly from an unauthenticated request.

## 26. Paginating Search Results

An API:

~~~text
GET /articles?q=mongodb&page=1&pageSize=10
~~~

might run:

~~~javascript
const page = 1;
const pageSize = 10;

db.articles.find(
  {
    tenantId: "tenant-A",
    status: "published",
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    publishedAt: 1,
    score: { $meta: "textScore" }
  }
)
.sort({
  score: { $meta: "textScore" },
  _id: 1
})
.skip((page - 1) * pageSize)
.limit(pageSize);
~~~

### 26.1. Score Tie-Breaker

When multiple documents share the same relevance score, adding `_id` stabilizes the ordering for a given data snapshot.

### 26.2. Results Can Still Shift Between Requests

If documents or the text index change, scores can change. Two consecutive HTTP requests do not automatically share a point-in-time snapshot.

Never promise an immutable infinite-scroll feed solely because results are sorted by `textScore`.

### 26.3. Deep Skip Is Expensive

`skip(100000)` still requires scanning and discarding a huge number of results. For large search workloads, evaluate pagination strategies, page-depth caps, and MongoDB Search capabilities.

### 26.4. Bounding Search Input

Cap maximum query length `q`, abnormal term counts, pagination depth, and query execution time (`maxTimeMS`). Returning empty results differs from a timeout error; never disguise server errors as "no results found."

## 27. Java Sync Driver: Creating a Text Index

The MongoDB Java Sync Driver provides `Indexes.text()` and `IndexOptions`.

Example assuming `client` is a connected `MongoClient`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

MongoDatabase database =
    client.getDatabase("text_search_lab");

MongoCollection<Document> articles =
    database.getCollection("articles");

// Create the index only if the collection does NOT already have another text index.
String indexName = articles.createIndex(
    Indexes.compoundIndex(
        Indexes.text("title"),
        Indexes.text("body"),
        Indexes.text("tags")
    ),
    new IndexOptions()
        .name("idx_article_search")
        .defaultLanguage("english")
        .languageOverride("lang")
        .weights(
            new Document("title", 10)
                .append("tags", 4)
                .append("body", 1)
        )
);

System.out.println(indexName);
~~~

**Important:** Section 5 in `mongosh` already created `idx_article_search`. If that exact index already exists on the collection, you do not need to recreate it. If a different text index with conflicting options exists, MongoDB will return `IndexOptionsConflict` or a similar error.

### 27.1. Only One Text Index

Do not do this:

~~~java
articles.createIndex(Indexes.text("title"));
articles.createIndex(Indexes.text("body"));
~~~

expecting two separate text indexes to coexist.

Use a single compound text index covering all desired fields.

### 27.2. Java Index Options Are Server Configuration

The driver sends the index definition to MongoDB. The one-text-index limit, supported languages, collation, and weights are enforced by the server—the driver will not silently ignore invalid rules.

## 28. Java Sync Driver: Searching and Retrieving textScore

Build a text filter with `Filters.text`:

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

Bson filter = Filters.and(
    Filters.eq("tenantId", "tenant-A"),
    Filters.eq("status", "published"),
    Filters.text("mongodb")
);

Bson projection = Projections.fields(
    Projections.include("title", "tenantId"),
    Projections.metaTextScore("score")
);

Bson relevanceSort = Sorts.metaTextScore("score");

for (Document doc : articles.find(filter)
        .projection(projection)
        .sort(relevanceSort)
        .limit(10)) {
    System.out.println(doc.toJson());
}
~~~

This is how the Java Driver expresses:

- `$text:{$search:"mongodb"}`.
- Projection `score:{$meta:"textScore"}`.
- Sorting by relevance metadata.

### 28.1. Multi-Word Search

~~~java
Bson searchAnyTerm = Filters.text("mongodb database");
~~~

Defaults to OR across terms, not "must contain both."

### 28.2. Phrase Search

~~~java
Bson phrase = Filters.text("\"text search\"");
~~~

### 28.3. Negated Search

~~~java
Bson notPerformance = Filters.text("mongodb -performance");
~~~

### 28.4. Specifying Language, Case, and Diacritics

~~~java
import com.mongodb.client.model.TextSearchOptions;

TextSearchOptions options = new TextSearchOptions()
    .language("english")
    .caseSensitive(false)
    .diacriticSensitive(false);

Bson filter = Filters.text("database", options);
~~~

Do not use `language("vietnamese")` when server native `$text` does not support it.

### 28.5. Java Sort Tie-Breaker

For deterministic ordering:

~~~java
Bson sort = Sorts.orderBy(
    Sorts.metaTextScore("score"),
    Sorts.ascending("_id")
);
~~~

Note that in the Java Driver and MongoDB 4.4+, the field name passed to `Sorts.metaTextScore("score")` in a sort may be ignored by MongoDB when interpreting sort metadata; it acts as a builder for `$meta`, not a request to sort on a stored `score` field.

## 29. Java Aggregation with textScore

When a pipeline is needed:

~~~java
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.and(
            Filters.eq("tenantId", "tenant-A"),
            Filters.text("mongodb")
        )
    ),
    new Document("$addFields",
        new Document("relevance",
            new Document("$meta", "textScore")
        )
    ),
    Aggregates.sort(
        Sorts.orderBy(
            Sorts.descending("relevance"),
            Sorts.ascending("_id")
        )
    ),
    Aggregates.project(
        Projections.fields(
            Projections.include("title", "relevance")
        )
    ),
    Aggregates.limit(10)
);

articles.aggregate(pipeline)
    .forEach(doc -> System.out.println(doc.toJson()));
~~~

`Aggregates.match(...)` containing the text query sits at the **start of the pipeline**, satisfying MongoDB's constraint.

**Never use `$text` as a standalone aggregation stage.** It is a **query operator inside `$match`**.

## 30. Monitoring Performance with explain

On a collection with substantial data:

~~~javascript
db.articles.find({
  tenantId: "tenant-A",
  status: "published",
  $text: { $search: "database" }
})
.explain("executionStats");
~~~

Depending on server version and query engine, the plan shows stages for text matching, index scans, filtering, and sorting.

### 30.1. Metrics to Inspect

- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `executionTimeMillis` (interpreted in the context of your environment).
- Whether a blocking sort occurs.
- Number of documents filtered out by tenant/status after text matching.
- Whether the query supplies the full compound equality prefix.

### 30.2. High-Frequency Terms Can Be Expensive

A search term appearing in millions of documents generates massive candidate sets. Applying `limit` caps the returned documents, not necessarily all candidate selection and ranking work.

### 30.3. Text Indexes Have Maintenance Overhead

Every insert or update to an indexed field may require updating index tokens. Large indexes increase storage footprint and write cost, especially with lengthy `body` fields.

### 30.4. Changing Weights Alters Ranking

If an A/B test raises `title` weight from 10 to 20, result ordering can change. Never conclude a query is "faster" just because scores are higher; measure execution performance separately.

### 30.5. Memory and Newer Versions

Some newer MongoDB versions (e.g., changes starting in 8.3) enforce memory limits on the `TextOr` stage, with `allowDiskUse` behavior when thresholds are exceeded. If a deployment hits memory errors when sorting/ranking large result sets, consult the documentation for your **exact version** rather than blindly throwing more RAM at it.

## 31. Vietnamese Search in Production Products

Vietnamese brings specific challenges:

- A single lexical word may consist of multiple space-separated syllables, such as `"tìm kiếm"`.
- Rich tone marks and accented vowels.
- Users frequently type without diacritics.
- Proper nouns, place names, abbreviations, product codes, and loanwords.
- Demands for typo correction, prefix/autocomplete, and synonyms.

Native `$text` lacks a Vietnamese language analyzer in its supported list. Using `none` can work for **basic keyword search**, but it is not equivalent to a dedicated Vietnamese search engine.

### 31.1. A Simple Token-Matching Example

~~~javascript
db.articles.find({
  tenantId: "tenant-A",
  $text: {
    $search: "MongoDB",
    $language: "none"
  }
});
~~~

Matching a single token like `MongoDB` is far more predictable than matching compound words requiring Vietnamese word segmentation.

### 31.2. Do Not Treat Accent Stripping as Sufficient

An unaccented string can correspond to multiple distinct words with different meanings. Without an appropriate analyzer, both precision and recall suffer.

### 31.3. When to Use MongoDB Search

If the application requires:

- Explicitly configured analyzers and custom tokenizers.
- Fuzzy search.
- Autocomplete.
- Synonym maps.
- Highlighting.
- Facets and advanced scoring/ranking.
- Hybrid keyword/semantic search.

evaluate MongoDB Search (the `$search` aggregation stage) on a supported deployment. It is a different engine from native text indexes and requires its own search index configuration.

### 31.4. Does MongoDB Search Understand Vietnamese Perfectly Out of the Box?

Not automatically. Review supported analyzers and token filters, configure them thoughtfully, and test on real Vietnamese data—especially diacritics, compound words, and proper nouns. An advanced search engine never replaces evaluating result quality with real user queries.

## 32. Security and Search Data Quality

### 32.1. Never Let Users Choose Tenants Arbitrarily

Correct query:

~~~javascript
db.articles.find({
  tenantId: tenantFromAuthenticatedSession,
  status: "published",
  $text: { $search: textFromUser }
});
~~~

The application tier must obtain `tenantFromAuthenticatedSession` from authentication state, not from a user-editable query parameter.

### 32.2. Search Strings Have Their Own Syntax

If a user types:

~~~text
performance -mongodb
~~~

the minus sign may be parsed as a negation operator. If the UI intends literal matching, sanitize or explain the syntax rather than letting special characters silently alter user intent.

### 32.3. Request Limits

- Maximum search query length.
- Reasonable page size and maximum page depth.
- Query deadlines / `maxTimeMS`.
- Per-user and per-tenant rate limiting.
- Projections to avoid returning sensitive fields.
- Search logging compliant with personal-data policies.

### 32.4. Content Quality

If documents contain raw HTML, markup, corrupted encoding, or token spam, the text index will ingest noise. Clean and normalize content before writing, separate `title`/`body`/`tags`, and filter spam per business rules.

## 33. MongoDB Compass: Inspecting Text Indexes and Scores

Compass can create indexes and run queries/aggregations depending on version capabilities. Practice steps:

1. Connect to the lab database.
2. Open the `articles` collection.
3. Open the **Indexes** tab and locate `idx_article_search`.
4. Verify that `title`, `body`, and `tags` are text-indexed fields.
5. In the query filter bar, enter `{$text:{$search:"mongodb"}}`.
6. Set projection `{title:1,score:{$meta:"textScore"}}` if supported by the UI.
7. Set sort `{score:{$meta:"textScore"}}`.
8. Test an aggregation pipeline with `$text` inside the leading `$match` stage.
9. Compare searching `"mongodb database"` with quoted `"text search"`.
10. If the UI does not expose all options, verify the exact command in `mongosh`.

**Do not** assume Compass sorted results by relevance just because the list looks reasonable; always verify the sort specification.

## 34. Common Errors and Misconceptions

| Symptom / Claim | Root Cause | Resolution |
|---|---|---|
| "Cannot create a second text index" | One text index per collection | Combine fields into a single index |
| "`$text` misses words in body" | `body` is not in the text index | Include required fields in index definition |
| "Typing two words should require both" | `$search` terms default to OR | Adjust query semantics per requirements |
| "Searching `blue` should match `blueberry`" | Not a prefix search | Use full terms or autocomplete search |
| "No score in results" | Metadata not projected | Add `{$meta:"textScore"}` |
| "Results are not sorted by score" | `$text` does not sort automatically | Sort by `$meta:"textScore"` |
| "Score 0.75 means 75% match" | Not a probability | Compare relative relevance only |
| "Scores across two queries are directly comparable" | No global normalization | Compare only within the same query/index |
| "Weight 10 means score is always 10x" | Server scoring uses its own algorithm | Evaluate ranking on real corpus |
| "`the` is not found in an English index" | Stop word | Test `none` if stop words must match |
| "`$language: 'vi'` is supported" | Native list lacks Vietnamese | Use `none` or MongoDB Search |
| "`none` is a Vietnamese analyzer" | Disables stemming/stop words, no NLP | Use an appropriate analyzer |
| "Changing query `$language` re-indexes tokens" | Index-time language already ran | Rebuild index when changing index language |
| "Accented search must match exact accents" | v3 is diacritic-insensitive by default | Set `$diacriticSensitive:true` if needed |
| "Case-sensitive search adds zero overhead" | May require extra post-filtering | Measure query latency |
| "Regex and `$text` are identical" | Different semantics and index types | Choose tool per use case |
| "`$text` placed after `$project` in aggregation" | Text match must be the first stage | Move `$match` with `$text` to the start |
| "Using `hint()` with `$text`" | Unsupported restriction | Remove hint; optimize index design |
| "Compound text index needs no equality prefix" | Keys before text require equality | Add equality predicates or redesign index |
| "Text index optimizes latest-date sorting" | Text indexes do not optimize regular sorts | Check sort plan and architecture |
| "Text index searches every field" | Covers only indexed fields | Inspect index definition |
| "Wildcard `$**:1` supports `$text`" | Distinct from wildcard text index | Use `{"$**":"text"}` if appropriate |
| "Text search enforces tenant isolation" | Does not handle authorization | Filter explicitly by authorized tenant |
| "One `$text` index handles fuzzy/autocomplete" | Native text has limits | Use MongoDB Search |
| "Changing weights needs no rebuild" | Weights are index options | Plan an index rebuild |
| "Can read `textScore` without `$text`" | No text metadata exists | Use only in a `$text` query context |

## 35. Practice Exercises

All exercises use the `text_search_lab` database. Exercises that alter indexes should run on a separate lab collection or follow the lesson sequence; never drop production indexes.

### Exercise 1 — Create a Single-Field Text Index

Create a text index only on `title` in a new collection. Run a `$text` query for `"MongoDB"`.

**Question:** Why does a word appearing only in `body` fail to match via the `title` index?

### Exercise 2 — One Multi-Field Text Index

Create a single text index covering `title`, `body`, and `tags`. Why can you not create three separate text indexes?

### Exercise 3 — OR Terms

~~~javascript
{ $text: { $search: "database wireless" } }
~~~

**Question:** Is the default matching behavior OR or AND? Explain using the dataset.

### Exercise 4 — Phrase

Write a query searching for the phrase `"text search"`. Compare it against searching the two words without quotes.

### Exercise 5 — Negation

~~~javascript
{ $text: { $search: "mongodb -performance" } }
~~~

Which documents do you expect to exclude? Why does `"-performance"` alone return nothing?

### Exercise 6 — Projecting Score

Write a `find` projection including `title` and `score:{$meta:"textScore"}`. Explain why `score` is not a persisted document field.

### Exercise 7 — Relevance Sort

Write `sort({score:{$meta:"textScore"},_id:1})`. Why must sorting be requested explicitly?

### Exercise 8 — Weights

Configure weights `title:10,body:1,tags:4`. Explain why two documents containing the same term can receive different scores.

### Exercise 9 — Do Not Predict Scores with a Raw Formula

Document A matches once in `title`; Document B matches three times in `body`. Can you conclude Document A always scores 10 and Document B always scores 3?

**Answer:** No. Weights are inputs to the scoring algorithm; actual rankings must be tested.

### Exercise 10 — English Stop Words

In an English index, try searching for `the`. Explain why the query may match nothing even though the source text contains that word.

### Exercise 11 — `none`

Create a new collection with `default_language:"none"` and search for `the`. Point out how stop words and stemming differ, without confusing `none` with full Vietnamese NLP.

### Exercise 12 — Vietnamese Language

Why is `$language:"vi"` invalid for native `$text`? When searching accented Vietnamese text, propose two tiers of solutions: simple keyword search via `none` and an advanced search analyzer.

### Exercise 13 — Per-Document Language Override

Insert an English doc, a Spanish doc, and a `lang:"none"` doc; create an index with `language_override:"lang"`. Which rules apply to each document?

### Exercise 14 — Case Sensitivity

Compare `$caseSensitive:false` with `true`. Why can `true` take extra time?

### Exercise 15 — Diacritic Sensitivity

Search `"cafe"` and `"café"` in an accented corpus. Explain v3 behavior and the effect of `$diacriticSensitive:true`.

### Exercise 16 — Text Index Version

Compare diacritic sensitivity between text index v2 and v3. Why should you not arbitrarily set `textIndexVersion:1` on a new server?

### Exercise 17 — Compound Prefix

Collection `tenantDocs` has the index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  title: "text",
  body: "text"
}
~~~

Write a query with equality predicates for both `tenantId` and `status`. What happens if `status` is omitted?

### Exercise 18 — Keep Text Keys Contiguous

Analyze the index:

~~~javascript
{
  tenantId: 1,
  title: "text",
  publishedAt: -1,
  body: "text"
}
~~~

**Question:** Why is this invalid under the contiguous text-keys rule?

### Exercise 19 — Aggregation Text First

Write a pipeline with `$match` containing `$text` as the first stage, followed by `$project` for `textScore`, `$sort` by score, and `$limit`.

### Exercise 20 — `$text` and `hint`

Explain why a `$text` query disallows `hint("idx_article_search")`. What should you use to inspect the execution plan?

### Exercise 21 — Wildcard Text vs. Wildcard Index

Distinguish:

~~~javascript
{ "$**": "text" }
{ "$**": 1 }
~~~

Which index supports `$text`? When should you avoid indexing all string fields?

### Exercise 22 — Tenant Security

Design a search API that returns only published articles belonging to the current tenant. Which filters are required in addition to `$text`?

### Exercise 23 — Java Driver

Use `Filters.text("mongodb")`, `Projections.metaTextScore("score")`, and `Sorts.metaTextScore("score")` to retrieve results ordered by relevance.

### Exercise 24 — Search User Experience

An app needs character-by-character autocomplete, fuzzy typo tolerance, and synonyms. Is native `$text` enough? Contrast with the MongoDB Search `$search` stage.

### Exercise 25 — Production Diagnostics

A text query becomes slow when searching a very common word. Draft a plan to inspect the index definition, `explain`, total docs/keys examined, sort work, compound equality prefixes, query length, timeouts, and pagination.

## 36. Designing Text Search for a Real Application

### Step 1 — Define User Expectations

Do users expect keyword OR, phrase matching, all-terms matching, autocomplete, fuzziness, synonyms, or semantic search? Never label a feature "full-text search" and skip specifying exact behavior.

### Step 2 — Identify Searchable Fields

Only `title`, `body`, and `tags`, or every string field? Every field added to the text index increases cost and affects relevance.

### Step 3 — Identify Corpus Languages

For English, Spanish, or French, use supported native analyzers with proper language overrides. For Vietnamese, recognize native limits and evaluate `none` versus an advanced search engine.

### Step 4 — Choose Weights

`title` usually outranks `body`, with `tags` weighted appropriately. Test rankings against a representative query set; avoid extreme weights without empirical measurement.

### Step 5 — Design Access Scope

Filter `tenantId`, `status`, and visibility by user permissions. If every query includes equality on tenant/status, consider a compound prefix—remembering the one-text-index-per-collection limit.

### Step 6 — Choose Ranking Mode and Pagination

Relevance or latest? Tie-breaker included? Must results stay stable across requests? Bound `skip`/`pageSize`.

### Step 7 — Measure on Realistic Data

Use `explain`, index stats, p95/p99 query latency, term frequencies, and document counts. An 8-document lab proves nothing about production performance.

### Step 8 — Plan Index Changes

Changing fields, language, or weights on a text index typically requires a rebuild. Prepare staging/rollout steps and fallback handling if queries lack an index during transition.

### Step 9 — Test Result Quality

Build a golden set of queries with expected outputs, covering accented/unaccented Vietnamese, stop words, stemming, phrases, negation, and mixed languages.

### Step 10 — Decide Whether MongoDB Search Is Needed

If a native text index cannot meet quality needs, do not pile on ad-hoc regexes and manual hacks to imitate a search engine. Evaluate MongoDB Search alongside its concrete deployment and index costs.

## 37. Pre-Deployment Checklist

### Text Index and Query

- [ ] Collection has only one text index.
- [ ] All searchable fields are included in that text index.
- [ ] Text index is not used as a unique index.
- [ ] Understood that `$text.$search` terms default to OR.
- [ ] Tested quoted phrases and negation.
- [ ] Did not confuse token text search with substring/prefix search.
- [ ] Did not assume `$text` sorts by relevance automatically.
- [ ] Projected `$meta:"textScore"` when score is needed.
- [ ] Scores are not interpreted as probabilities or compared across queries.
- [ ] Weights validated via ranking tests.
- [ ] Compound text index receives its full equality prefix.
- [ ] `hint()` is not used with text queries.
- [ ] Aggregation `$match` with `$text` is placed first in the pipeline.
- [ ] Text index uses `simple` collation only.

### Language and Data

- [ ] Aware that `default_language` defaults to English.
- [ ] Configured `language_override` for multilingual corpora.
- [ ] Override field contains only valid language names or `none`.
- [ ] Aware that Vietnamese is not among the 15 native `$text` languages.
- [ ] Understood that `none` is not Vietnamese NLP.
- [ ] Tested case-sensitive and diacritic-sensitive semantics.
- [ ] Did not assume tokenization/stemming handles all special characters as expected.
- [ ] Avoided indexing strings containing unnecessary sensitive data.

### Operations and Product

- [ ] Queries always bind tenant/visibility from authenticated permissions.
- [ ] Enforced search string length limits, page size limits, and timeouts.
- [ ] Benchmarked index and read performance on a realistic corpus.
- [ ] Prepared a rebuild plan for weight/language/field changes.
- [ ] Set up monitoring for index conflicts and query timeouts.
- [ ] Maintained a relevance evaluation query set and quality feedback loop.
- [ ] Evaluated MongoDB Search if fuzzy, autocomplete, synonyms, or facets are needed.
- [ ] Avoided promising search features beyond native text index capabilities.

## 38. Summary

Legacy MongoDB text search consists of three core pieces:

1. **Text index:** defines tokenized fields, language rules, and weights. Each collection allows at most **one text index**, though it can cover multiple text fields.
2. **`$text`:** queries the index; space-separated terms default to OR, quoted phrases require phrase matching, and minus signs negate terms. It is not regex, substring matching, or autocomplete.
3. **`$meta:"textScore"`:** retrieves and sorts by relevance, though `$text` neither projects nor sorts by score automatically. Scores are relative signals per query, not exact probabilities.

Language configuration governs stemming and stop words. Native `$text` supports the 15 languages listed in the MongoDB Manual—**excluding Vietnamese**. `default_language:"none"` suits simple keyword searches without stemming or stop words, but it is not a dedicated Vietnamese analyzer.

For systems requiring advanced search capabilities, MongoDB now recommends MongoDB Search with dedicated search indexes and the `$search` aggregation stage. Choosing between a native text index and MongoDB Search should be driven by real **search semantics, language needs, result quality, latency, and operational cost**.

## Official References

- [MongoDB Manual — $text query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Manual — Text Search](https://www.mongodb.com/docs/manual/text-search/)
- [MongoDB Manual — Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/)
- [MongoDB Manual — Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/)
- [MongoDB Manual — Text Search Languages](https://www.mongodb.com/docs/manual/reference/text-search-languages/)
- [MongoDB Manual — Specify Text Index Language](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/specify-text-index-language/)
- [MongoDB Manual — Language Override](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/specify-language-text-index/use-any-field-to-specify-language/)
- [MongoDB Manual — Text Index Versions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-versions/)
- [MongoDB Manual — Text Search in Aggregation](https://www.mongodb.com/docs/manual/tutorial/text-search-in-aggregation/)
- [MongoDB Manual — Limit Text Index Entries Scanned](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/limit-number-of-items-scanned-for-text-search/)
- [MongoDB Java Sync Driver — Query Text](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/text/)
- [MongoDB Java Sync Driver — Sort Text Results](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/sort/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)
