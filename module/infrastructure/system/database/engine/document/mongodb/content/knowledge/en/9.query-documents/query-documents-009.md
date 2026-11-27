# Querying by Time, Strings, and Collation in MongoDB

## 1. The Problem: One Document, Multiple Ways to Compare

A content-publishing application might need to find articles:

- published on **November 14 in Vietnam time**;
- whose title **starts with "MongoDB"**, or contains a phrase;
- whose title matches "cafe" even when stored as `Cafe` or `Café`;
- sorted by title in a lexical order natural to the reader's language.

At first glance these all look like data filtering, yet they involve three distinct MongoDB mechanisms:

1. **Time comparisons:** working with BSON `Date`, time boundaries, and comparison operators such as `$gte` and `$lt`.
2. **String matching and searching:** distinguishing exact-value queries, `$regex` regular expressions, aggregation expressions, and full-text search.
3. **Collation:** language-specific string comparison and sorting rules affecting equality, ordering, indexes, and uniqueness.

No single string-comparison strategy fits every case. Matching a case-sensitive identifier differs from matching a person's name; substring matching differs from keyword search; finding events by UTC date differs from finding events by local date in a specific time zone.

After this lesson, you will be able to write `mongosh` queries using proper data types, construct half-open date ranges, choose between equality and `$regex`, configure collation for queries and indexes, and recognize scenarios prone to wrong results or slow queries.

## 2. Preparing Practice Data

The examples use `mongosh` and the test database `mongo_query_row104_lab`. Connect to a MongoDB instance where you have permission before running:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

If you run MongoDB on another host/port or require authentication, use the URI for your environment. In the shell:

```javascript
const lab = db.getSiblingDB("mongo_query_row104_lab");
const articles = lab.getCollection("articles");
const runId = "row104-" + new ObjectId().toHexString();

print("Database: " + lab.getName());
print("Run ID: " + runId);

articles.insertMany([
  {
    runId,
    title: "MongoDB nhập môn",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-13T16:59:59.000Z")
  },
  {
    runId,
    title: "MongoDB và document",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-13T17:00:00.000Z")
  },
  {
    runId,
    title: "mongodb cho người mới",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T03:00:00.000Z")
  },
  {
    runId,
    title: "MONGODB nâng cao",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T16:59:59.000Z")
  },
  {
    runId,
    title: "MongoDB tổng kết",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T17:00:00.000Z")
  },
  {
    runId,
    title: "Café dữ liệu",
    category: "lifestyle",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T10:00:00.000Z")
  },
  {
    runId,
    title: "Cafe dữ liệu",
    category: "lifestyle",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T11:00:00.000Z")
  }
]);

printjson(
  articles.find(
    { runId },
    { _id: 0, title: 1, publishedAt: 1 }
  ).sort({ publishedAt: 1 }).toArray()
);
```

`runId` isolates this practice run's documents from other runs in the same collection. Most queries below include `runId` to operate only on the sample data. If you open a new `mongosh` session, the `runId` variable is not automatically preserved; record the printed value or recreate data for a new run.

**Type distinction:** `publishedAt` in the sample dataset is a BSON `Date`. The `title` field is a `string`. This distinction is crucial: MongoDB compares BSON Dates chronologically, whereas strings follow string comparison rules. A string that looks like a date/time does not automatically become a BSON Date during queries.

## 3. Querying Time with BSON Date

### 3.1. BSON Date Is an Instant in Time, Not a Display String

In MongoDB, BSON `Date` stores the number of **milliseconds** since the Unix epoch `1970-01-01T00:00:00Z` as a 64-bit signed integer. A Date value represents an **absolute instant**; it does not store the time-zone name used at input time.

The following two representations refer to the exact same instant:

```javascript
const utcInstant = ISODate("2026-11-14T01:30:00Z");
const localInstant = ISODate("2026-11-14T08:30:00+07:00");

print(utcInstant.getTime() === localInstant.getTime()); // true
print(localInstant.toISOString()); // 2026-11-14T01:30:00.000Z
```

When displayed to users in Vietnam, the instant `01:30 UTC` corresponds to `08:30` in `Asia/Ho_Chi_Minh` on that date. Queries should operate on concrete instants; formatting for display is handled separately.

### 3.2. Comparing Instants with `$gte`, `$gt`, `$lt`, `$lte`

Common comparison operators:

| Operator | Meaning | Time example |
| --- | --- | --- |
| `$gt` | Greater than | After a timestamp, exclusive |
| `$gte` | Greater than or equal to | From a timestamp, inclusive |
| `$lt` | Less than | Before a timestamp, exclusive |
| `$lte` | Less than or equal to | Before or at a timestamp, inclusive |
| `$eq` | Equal to exact value | Equal to a specific instant |
| `$exists` | Field exists | Check whether the time field is present |

Example finding articles from a point in time onward:

```javascript
articles.find(
  {
    runId,
    publishedAt: {
      $gte: ISODate("2026-11-14T00:00:00Z")
    }
  },
  { _id: 0, title: 1, publishedAt: 1 }
);
```

This filters by **UTC instant**. If the real requirement is "from the start of the day in Vietnam time", the start boundary must first be converted from Vietnam time to UTC, as shown next.

### 3.3. Selecting One Day with a Half-Open Interval `[start, end)`

To retrieve all events on `2026-11-14` in UTC:

```javascript
articles.find({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00.000Z"),
    $lt: ISODate("2026-11-15T00:00:00.000Z")
  }
});
```

A half-open interval has the form:

```text
start <= publishedAt < end
```

Using the **start of the next day** as the upper bound avoids missing values with fractional milliseconds and prevents double-counting boundary instants across consecutive daily queries.

Avoid filtering with an end bound of `23:59:59`, because timestamps from `23:59:59.001` to `23:59:59.999` will be skipped. Also avoid writing `publishedAt: ISODate("2026-11-14")` expecting "the whole day": equality matches only the exact UTC midnight instant.

### 3.4. A Day in Vietnam Time Requires Different Boundaries

"Articles published on November 14, 2026 in Vietnam time" spans the local interval:

```text
2026-11-14 00:00:00 +07:00  (inclusive)
                     to
2026-11-15 00:00:00 +07:00  (exclusive)
```

Equivalent in UTC:

```text
[2026-11-13T17:00:00Z, 2026-11-14T17:00:00Z)
```

Query:

```javascript
articles.find(
  {
    runId,
    publishedAt: {
      $gte: ISODate("2026-11-13T17:00:00Z"),
      $lt: ISODate("2026-11-14T17:00:00Z")
    }
  },
  { _id: 0, title: 1, publishedAt: 1 }
).sort({ publishedAt: 1 });
```

Or specify the offset timestamps directly:

```javascript
articles.find({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
});
```

On the sample dataset, this interval includes `MongoDB và document`, `mongodb cho người mới`, `MONGODB nâng cao`, `Café dữ liệu`, and `Cafe dữ liệu`. The record at `2026-11-13T16:59:59Z` falls before the boundary, and the record at `2026-11-14T17:00:00Z` already belongs to the next day in Vietnam time.

**Time-zone note:** `+07:00` describes the UTC offset in this example. In regions with daylight saving time, a local day can be 23 or 25 hours long. When writing reports for a zone such as `America/New_York`, compute **both local midnight boundaries** using the IANA time-zone name; do not assume adding 24 hours always works.

### 3.5. Querying Relative to Current Time and Deadlines

Example querying records whose publication time has arrived:

```javascript
const now = new Date();

articles.find({
  runId,
  publishedAt: { $lte: now }
});
```

`new Date()` in `mongosh` uses the clock of the machine running the shell. In a server application, the instant generated by the application host and the display time zone are two separate concerns. Clocks across participating systems must be synchronized properly.

When using a dynamic time window for pagination, pin the upper bound for the duration of a read session if stable results are needed, because new articles may be inserted while paging.

### 3.6. Missing Fields, `null`, and Wrong Types

If the same field is sometimes stored as Date and sometimes as string:

```javascript
{ publishedAt: ISODate("2026-11-14T01:30:00Z") }
{ publishedAt: "2026-11-14T01:30:00Z" }
```

These are **two different BSON types**. Do not expect a BSON Date comparison to treat date strings as Dates. MongoDB evaluates query comparisons within the matching BSON type group; mixed-type data leads to unpredictable results without strict conventions.

You can find documents whose timestamp field is a Date:

```javascript
articles.find({
  runId,
  publishedAt: { $type: "date" }
});
```

For legacy string data, consider a controlled migration to BSON Date. Parsing inside every query complicates logic, risks data errors, and cannot exploit indexes as effectively as direct comparisons on a Date field.

## 4. Exact String Queries: Equality and Basic Operators

### 4.1. Exact String Matching

```javascript
articles.find({
  runId,
  title: "MongoDB và document"
});
```

Without a custom collation, collections typically use **simple collation**, which performs binary string comparison. Under simple collation, `MongoDB`, `mongodb`, and `MONGODB` differ; `Cafe` and `Café` also differ.

Exact equality suits system codes, fixed strings, and fields where the application mandates exact matches. It does not automatically perform "contains phrase" matching or full-text search.

### 4.2. Querying by Lists and Logical Conditions

```javascript
// Matches only titles in the list.
articles.find({
  runId,
  title: {
    $in: ["MongoDB nhập môn", "MongoDB và document"]
  }
});

// Combining status, category, and string condition.
articles.find({
  runId,
  status: "PUBLISHED",
  category: "database",
  title: "MongoDB và document"
});
```

`$in` is useful when you have an exact list of values. When case-insensitive, accent-insensitive, or locale-aware matching is needed, consider **collation** rather than forcing every requirement into a regular expression.

### 4.3. String Sorting Depends on Comparison Rules

```javascript
articles.find(
  { runId },
  { _id: 0, title: 1 }
).sort({ title: 1 });
```

`sort({ title: 1 })` requests ascending order. Under simple collation, ordering may not match Vietnamese dictionary order expected by users; uppercase, lowercase, and accented characters may sort into unexpected positions. Collation, covered below, lets you select rules appropriate to the language.

## 5. Pattern Matching Strings with `$regex`

### 5.1. Regex Solves a Different Problem from Equality

`$regex` uses regular expressions to match character patterns inside a string. Common patterns:

| Pattern | Meaning | Use case |
| --- | --- | --- |
| `^MongoDB` | Starts with "MongoDB" | Prefix search |
| `MongoDB$` | Ends with "MongoDB" | Suffix search |
| `MongoDB` | Contains "MongoDB" anywhere | Substring search |
| `^MongoDB$` | Entire string equals "MongoDB" | Full-string match via regex |
| `MongoDB` + option `i` | Case-insensitive under regex rules | Case-insensitive search |
| `^MongoDB.*cơ bản$` | Starts and ends with two patterns | Matching a string shape |

In `mongosh`, you can use regex literals:

```javascript
// Only titles starting with exact "MongoDB" casing.
articles.find({
  runId,
  title: /^MongoDB/
});

// Case-insensitive prefix search.
articles.find({
  runId,
  title: /^mongodb/i
});

// Case-insensitive substring search anywhere.
articles.find({
  runId,
  title: /mongodb/i
});
```

Equivalent `$regex` string syntax:

```javascript
articles.find({
  runId,
  title: {
    $regex: "^mongodb",
    $options: "i"
  }
});
```

On the sample data, `/^MongoDB/` matches titles starting with exact `MongoDB`; `/^mongodb/i` also matches `mongodb` and `MONGODB`. These patterns do **not** strip Vietnamese diacritics or understand synonyms.

### 5.2. Regex Can Make Queries Expensive

Anchored prefix patterns with a clear start, such as `/^MongoDB/`, can utilize a standard **B-tree index** on a string field under appropriate conditions. Unanchored patterns like `/MongoDB/` or case-insensitive `/^mongodb/i` may have to inspect far more entries, especially on large collections.

```javascript
// In the practice database, you can create a simple index on title.
articles.createIndex(
  { title: 1 },
  { name: "title_simple" }
);

// Inspect the execution plan.
printjson(
  articles.find({
    title: /^MongoDB/
  }).explain("executionStats")
);
```

When reading `explain()`, examine fields such as `winningPlan`, documents examined, and documents returned. Actual behavior depends on data volume, indexes, and the query optimizer; on a collection with only a few documents, MongoDB may choose a collection scan as cheaper. Examples never force a single fixed execution plan.

**Warning:** A case-insensitive collation index does not automatically make `$regex` an efficient case-insensitive search. The `$regex` operator is **not collation-aware**, so a collation-based case-insensitive index generally does not accelerate `$regex` with the `i` option as expected. When the requirement is case-insensitive full-string matching, equality + collation is usually a better fit.

### 5.3. Regular Expressions and User Input

If a user types `C++` or `a.b`, the characters `+` and `.` have special meaning in regex. Never interpolate raw user input directly into a regex treating it as a literal substring search:

```javascript
// Do not treat this input as a safe literal regex.
const userInput = "a.b";
// new RegExp(userInput) treats "." as matching any character.
```

If a product offers "literal substring search", **escape metacharacters** before building the regex, cap input length and complexity, and enforce appropriate query resource limits. For natural-language search at scale, evaluate dedicated text/search engines rather than assuming regex covers everything.

### 5.4. How Regex Differs from Text Search

`$regex` matches **character patterns**. Full-text search typically handles **words**, tokens, language rules, and sometimes relevance scoring.

MongoDB provides `$text` when a collection has a text index; additionally, MongoDB Search on supported deployments offers dedicated search capabilities with corresponding indexes and analyzers. These mechanisms have different semantics from `$regex`, such as tokenization and Vietnamese language handling, so choose based on product requirements rather than swapping operators mechanically.

## 6. Collation: Language-Specific String Comparison Rules

### 6.1. What Is Collation?

**Collation** specifies how MongoDB compares and sorts string values. It can control:

- language/locale such as `en` or `vi`;
- sensitivity or insensitivity to case differences;
- sensitivity or insensitivity to accents/diacritics at specific comparison levels;
- handling of digit sequences during sorting;
- options such as punctuation and whitespace ordering, depending on purpose.

For example, when searching for a person's name, having "hoa" match "Hoa" can make sense. By contrast, a secret code or sensitive token should never be treated as equal merely because of a case difference. Configure collation based on **the semantics of the field**, rather than applying one collation blindly to every string.

### 6.2. Key Options to Know

| Option | Practical meaning |
| --- | --- |
| `locale` | Language rule set; e.g., `"en"`, `"vi"` |
| `strength: 1` | Primary-level comparison: typically ignores case and secondary accent differences, depending on the locale's alphabet |
| `strength: 2` | Adds secondary differences such as accents; typically still ignores case |
| `strength: 3` | Adds tertiary differences such as case/variants; common default for ICU collation |
| `caseLevel` | Enables fine-grained case distinction at lower strength levels when needed |
| `numericOrdering: true` | Sorts digit sequences by numeric value in supported cases |
| `normalization` | Controls Unicode normalization during collation comparison |

`strength` is a comparison level, **not simply an on/off accent switch** across all languages. Certain accented letters count as distinct primary characters depending on the locale; exact behavior should be verified against the target language, ICU version, and domain data.

### 6.3. Case- and Accent-Insensitive Equality

Example finding articles whose title matches `cafe dữ liệu` under English collation at primary strength:

```javascript
articles.find(
  { runId, title: "cafe dữ liệu" },
  { _id: 0, title: 1 }
).collation({
  locale: "en",
  strength: 1
});
```

On the sample dataset, the query illustrates case-insensitive comparison where accents count as secondary differences in this locale; the two variants `Cafe dữ liệu` and `Café dữ liệu` demonstrate this clearly. This is **equality** combined with collation—not regex, and not a transformation of stored data.

If you want **accent-sensitive but case-insensitive**:

```javascript
articles.find({
  runId,
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 2
});
```

Under this rule, `Cafe dữ liệu` matches `cafe dữ liệu` despite case, while `Café dữ liệu` has an acute accent on `é` and differs at the secondary level. If case sensitivity is required as well, use a higher strength or simple collation for binary matching.

### 6.4. Sorting Vietnamese Strings by Locale

```javascript
articles.find(
  { runId },
  { _id: 0, title: 1 }
).sort({ title: 1 }).collation({
  locale: "vi",
  strength: 3
});
```

This sorts according to Vietnamese locale rules via ICU, which differs from binary ordering under simple collation. When an application serves users across multiple regions, choose the locale according to display language or product sorting policy.

Do not treat collation as a "strip all Vietnamese diacritics" tool for normalizing proper names. In particular, distinct letters such as `đ` are not equivalent to `d` under standard collation rules. If a feature requires fuzzy matching, transliteration, full accent-stripping, or synonyms, design a dedicated search mechanism.

### 6.5. Sorting Strings Containing Numbers

For display labels `"Bài 2"` and `"Bài 10"`, binary sorting puts `"Bài 10"` before `"Bài 2"`. When digit sequences should be ordered numerically under collation:

```javascript
const labels = lab.getCollection("labels_demo");
labels.insertMany([
  { runId, label: "Bài 2" },
  { runId, label: "Bài 10" },
  { runId, label: "Bài 1" }
]);

labels.find(
  { runId },
  { _id: 0, label: 1 }
).sort({ label: 1 }).collation({
  locale: "vi",
  numericOrdering: true
});
```

The expected numerical order is `Bài 1`, `Bài 2`, `Bài 10`. `numericOrdering` handles supported digit sequences inside strings; do not treat it as a general parser for negative numbers, decimals, or complex version strings.

## 7. Collation on Collections, Queries, and Indexes

### 7.1. Where Is Collation Specified?

MongoDB lets you specify collation at multiple scopes:

1. **Collection default collation:** configured when creating the collection; used as the default for collation-aware operations unless overridden.
2. **Operation collation:** passed per `find`, `sort`, `aggregate`, and other operations when custom rules are needed.
3. **Index collation:** rules for an index on a string field, determining whether the index can serve a given comparison or sort.

If a collection has no custom default collation, string comparisons default to `simple`. When a query needs locale-aware comparison, specify the collation explicitly and ensure supporting indexes match.

Example creating a collection with a default collation for **new test data**:

```javascript
lab.createCollection("contacts_demo", {
  collation: {
    locale: "vi",
    strength: 2
  }
});
```

This new collection inherits the specified default collation. Do not call `createCollection` with the name of an existing collection; if a project needs to change defaults or update schemas, plan a separate migration.

### 7.2. Creating an Index Matching the Comparison

Suppose an application repeatedly looks up titles using accent- and case-insensitive equality in English locale:

```javascript
articles.createIndex(
  { title: 1 },
  {
    name: "title_en_primary",
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
```

The query must specify the same collation to leverage that index for string comparison:

```javascript
articles.find({
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 1
});
```

If the query uses a different collation from the index, MongoDB cannot use that index for string comparison or sorting as expected. Seeing an index on `title` is not enough; verify both **index collation and operation collation**.

For multi-field indexes, non-string prefixes may still be usable under certain conditions, but never assume a collation-mismatched index optimizes the whole query. Inspect `explain()` against realistic data and query patterns.

### 7.3. Simple Indexes and Collated Indexes Can Serve Two Needs

In this lab, we created `title_simple` (simple collation) for case-sensitive prefix searches. Index `title_en_primary` serves equality and sorting under English primary collation.

Both indexes can coexist on the same collection as long as they have distinct names and satisfy version rules. However, every index consumes storage and adds write maintenance overhead. In production, retain only indexes backed by critical queries and measurable gains.

### 7.4. Unique Indexes and Collation

Collation also affects string **uniqueness**. For example, if a system forbids nicknames that differ only by case:

```javascript
const accounts = lab.getCollection("accounts_demo");

accounts.createIndex(
  { nickname: 1 },
  {
    unique: true,
    name: "uniq_nickname_en_secondary",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

Under this rule, `"Minh"` and `"minh"` collide as the same unique key with respect to case. However, `"Mính"` has an accent difference and remains distinct at strength 2. This is a **user-identity rule**, not merely a display preference.

Never change collation or add a collated unique index on a production collection without checking for existing duplicates under the new rules. Creating a unique index fails if the collection already holds documents considered duplicates under the chosen collation.

### 7.5. Regex Does Not Follow Collation Like Equality

These two expressions have different meanings:

```javascript
// Equality compares according to collation.
articles.find({
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 1
});

// Regex follows regex semantics; collation does not turn regex
// into an accent-insensitive or locale-equivalent matcher.
articles.find({
  title: /cafe/i
}).collation({
  locale: "en",
  strength: 1
});
```

The `/cafe/i` pattern does not match `Café` merely because the operation specifies primary collation. Likewise, a case-insensitive collated index does not automatically optimize `i`-flag regexes. This is an important boundary when designing search APIs.

## 8. Combining Time, Strings, and Collation in One Query

### 8.1. Finding Articles in a Local Day with Collated Title Matching

Example: find articles on **November 14 in Vietnam**, with title matching "cafe dữ liệu" under English primary collation:

```javascript
const localDayStart = ISODate("2026-11-14T00:00:00+07:00");
const localNextDayStart = ISODate("2026-11-15T00:00:00+07:00");

articles.find(
  {
    runId,
    status: "PUBLISHED",
    publishedAt: {
      $gte: localDayStart,
      $lt: localNextDayStart
    },
    title: "cafe dữ liệu"
  },
  { _id: 0, title: 1, publishedAt: 1 }
).sort({
  publishedAt: 1
}).collation({
  locale: "en",
  strength: 1
});
```

In this example:

- `publishedAt` compares **BSON Dates**, not date strings.
- `title` compares **strings using the selected collation**.
- `sort({ publishedAt: 1 })` orders chronologically.
- `runId` scopes results to this lab run.

Date comparisons do not turn into lexical comparisons simply because the query specifies a collation. Collation governs string comparisons.

### 8.2. Prefix Search, Time Window, and Newest-First Sort

```javascript
articles.find(
  {
    runId,
    status: "PUBLISHED",
    publishedAt: {
      $gte: ISODate("2026-11-14T00:00:00+07:00"),
      $lt: ISODate("2026-11-15T00:00:00+07:00")
    },
    title: /^MongoDB/
  },
  { _id: 0, title: 1, publishedAt: 1 }
).sort({
  publishedAt: -1
});
```

Because regex is case-sensitive by default, this pattern does not match `mongodb cho người mới` or `MONGODB nâng cao`. If case insensitivity is needed, explicitly switch to the `i` flag or choose another search mechanism, and re-evaluate index support.

### 8.3. Choosing Indexes from Actual Queries

For an application that frequently filters articles by status and date range and sorts newest-first:

```javascript
articles.createIndex(
  { status: 1, publishedAt: -1 },
  { name: "status_publishedAt_desc" }
);
```

If queries often filter by exact title under a specific collation and fetch the newest record, consider a **compound index** matching that real pattern, for example:

```javascript
articles.createIndex(
  { title: 1, publishedAt: -1 },
  {
    name: "title_en_primary_publishedAt",
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
```

Index decisions should account for equality predicates, range predicates, sort order, selectivity, read/write frequency, and representative data. You do not need to keep every illustrative index in production. Verify with `explain("executionStats")` once data volume is large enough for meaningful measurement.

## 9. Aggregation: Extracting, Formatting, and Grouping by Date

`find` queries fit when the application needs matching documents. Aggregation pipelines excel at daily reporting, reformatting, and derived fields.

### 9.1. Displaying Time in a Local Time Zone

```javascript
articles.aggregate([
  { $match: { runId } },
  {
    $project: {
      _id: 0,
      title: 1,
      publishedAt: 1,
      publishedAtVietnam: {
        $dateToString: {
          format: "%Y-%m-%d %H:%M:%S",
          date: "$publishedAt",
          timezone: "Asia/Ho_Chi_Minh",
          onNull: null
        }
      }
    }
  },
  { $sort: { publishedAt: 1 } }
]);
```

`publishedAtVietnam` is a **display string**. The original `publishedAt` field remains a BSON Date. Using an IANA time-zone name applies regional rules accurately instead of merely appending `+07:00` to a UTC time.

### 9.2. Grouping Articles by Vietnam Day with `$dateTrunc`

```javascript
articles.aggregate([
  { $match: { runId, status: "PUBLISHED" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$publishedAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      articleCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      localDate: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$_id",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      articleCount: 1
    }
  }
]);
```

`$dateTrunc` with `unit: "day"` truncates each instant to **local midnight**. The resulting value is still a Date, so in the shell Vietnam `00:00` displays as `17:00Z` of the preceding UTC day. The `$dateToString` stage formats a readable local date label for reporting.

### 9.3. Checking Data Types When Legacy Data Is Mixed

```javascript
articles.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: { $type: "$publishedAt" },
      count: { $sum: 1 }
    }
  }
]);
```

In the sample dataset, `publishedAt` has type `date`. If production results also contain `string` or `missing`, define data-conversion rules and schema validation before building pipelines that assume every document holds a Date.

### 9.4. String Transformations in Aggregation

MongoDB provides string expressions such as `$toLower`, `$toUpper`, `$strLenCP`, and `$regexMatch`:

```javascript
articles.aggregate([
  { $match: { runId } },
  {
    $project: {
      _id: 0,
      title: 1,
      titleLengthCodePoints: { $strLenCP: "$title" },
      startsWithMongoDBCaseInsensitive: {
        $regexMatch: {
          input: "$title",
          regex: "^mongodb",
          options: "i"
        }
      }
    }
  }
]);
```

`$strLenCP` counts **Unicode code points**, which differs from UTF-8 byte length and can differ from user-perceived grapheme clusters when combining characters are present. `$regexMatch` performs regex matching inside aggregation and likewise does not follow operation collation.

For `$toLower` and `$toUpper`, note the Unicode/locale limitations of each operator and MongoDB version. Do not treat simple case folding as a complete replacement for locale-aware collation comparison.

## 10. Common Pitfalls and Remedies

| Scenario | Error-prone approach | Remedy |
| --- | --- | --- |
| Vietnam daily report | Using `00:00Z` to `00:00Z` next day | Compute boundaries in `Asia/Ho_Chi_Minh` and use `$gte`/`$lt` |
| Missing end-of-day records | Using `$lte` up to `23:59:59` | Filter with half-open `[start, nextStart)` |
| Dates stored as strings | Comparing lexicographically assuming chronological equivalence | Store instants as BSON Date and migrate legacy data carefully |
| Matching exact title via regex | Using `/title/i` when equality is needed | Use equality with an appropriate collation |
| Expecting regex to ignore accents | Using `/cafe/i` expecting to match `Café` | Remember regex is not collation-aware; use equality/collation or search |
| Regex on arbitrary input | Interpolating raw user strings into regex | Escape metacharacters, cap input length, and bound query resources |
| Paginating string-sorted lists | Sorting with collation without a tie-breaker | Add a deterministic tie-breaker, e.g. `title` and `_id` |
| Querying an index with a different collation | Index `en/strength1`, query `simple` expecting index optimization | Match operation and index collations; verify with `explain()` |
| Adding case-insensitive unique index on legacy data | Nicknames differing only by case already exist | Audit duplicates under the new collation before creating |
| Applying strength 1 to every field | Technical codes differing in case/accents collide | Choose collation per field semantics; keep simple for binary IDs |
| Checking only returned row counts | Missing that the query scanned millions of documents | Inspect `totalDocsExamined`, `totalKeysExamined`, time, and plan |

### 10.1. Unicode Strings Can Have Multiple Representations

Certain accented characters can be encoded either as **a single precomposed code point** or as **multiple combining code points**. Two strings may render identically while differing at the byte level. For technical IDs and storage keys, define Unicode normalization rules at the application layer if required. For names or titles, collation compares according to linguistic rules; understand your normalization policy and how systems exchange strings.

### 10.2. Deterministic Sorting When Collation Considers Values Equal

When `strength: 1` treats two titles as equal, sorting only by `title` may not produce a deterministic order among collation-equivalent documents. For pagination, append a stable tie-breaker:

```javascript
articles.find(
  { runId },
  { title: 1, publishedAt: 1 }
).sort({
  title: 1,
  _id: 1
}).collation({
  locale: "en",
  strength: 1
});
```

`_id` breaks ties among documents whose titles are equivalent under the collation. For cursor pagination, build the next-page condition using **the exact same sort keys and collation**.

## 11. Hands-On Query and Index Observation

### 11.1. Comparing Three Queries

Run each query on the dataset created earlier:

```javascript
// A. Exact title "Cafe dữ liệu".
articles.find({ runId, title: "Cafe dữ liệu" });

// B. Title equivalent to "cafe dữ liệu" under English primary collation.
articles.find({
  runId,
  title: "cafe dữ liệu"
}).collation({ locale: "en", strength: 1 });

// C. Title containing pattern "cafe", case-insensitive regex.
articles.find({
  runId,
  title: /cafe/i
});
```

Observe the semantic differences: A performs exact string matching; B performs whole-string comparison under collation; C matches character patterns via regex. C does not treat accents the same way B does.

### 11.2. Two Date Queries on the Same Data with Different Definitions

```javascript
// November 14 in UTC.
const utcDay = articles.countDocuments({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
});

// November 14 in Vietnam time.
const vietnamDay = articles.countDocuments({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
});

printjson({ utcDay, vietnamDay });
```

The counts can differ even though both queries are syntactically valid, because **the day is defined in two different time zones**. Boundary selection must come from business requirements.

### 11.3. Inspecting `explain()`

```javascript
const stats = articles.find({
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 1
}).explain("executionStats");

printjson(stats);
```

Metrics to understand:

- `nReturned`: number of documents returned by the query.
- `totalDocsExamined`: number of documents inspected.
- `totalKeysExamined`: number of index keys scanned.
- `winningPlan`: execution plan chosen by the optimizer.

Good vs. poor ratios cannot be judged from a handful of test documents alone; evaluate against data scale, query patterns, existing indexes, and acceptable product latency budgets.

### 11.4. Cleaning Up Practice Run Data

Before deleting, verify the exact database and `runId`, and preview matching documents:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
print("articles=" + articles.countDocuments({ runId }));
print("labels=" + labels.countDocuments({ runId }));

printjson(
  articles.find(
    { runId },
    { _id: 1, title: 1, runId: 1 }
  ).toArray()
);

printjson(
  labels.find(
    { runId },
    { _id: 1, label: 1, runId: 1 }
  ).toArray()
);
```

Once both result sets match the data you created in the test environment, delete using the verified `runId`:

```javascript
printjson(articles.deleteMany({ runId }));
printjson(labels.deleteMany({ runId }));

print("remaining articles=" + articles.countDocuments({ runId }));
print("remaining labels=" + labels.countDocuments({ runId }));
```

These delete commands **do not** remove documents with other `runId` values. They also **do not drop created indexes** or the `contacts_demo` and `accounts_demo` collections. In a dedicated exercise database, manage remaining resources according to environment procedures; never run `dropDatabase()` or `deleteMany({})` on a shared database as a shortcut.

## 12. Review Questions and Extended Exercises

1. Why is `publishedAt: ISODate("2026-11-14")` not equivalent to "all articles published on November 14"?
2. What are the UTC start and end instants for November 14, 2026 in Vietnam time? In regions with DST, why shouldn't you always add 24 hours to the start timestamp?
3. When should you use `title: "MongoDB nhập môn"`, when should you use `title: /^MongoDB/`, and when should you use equality with collation?
4. Does `/^mongodb/i` use the accent-insensitive comparison rules of `collation({ locale: "en", strength: 1 })`?
5. What is the difference between `strength: 1`, `strength: 2`, and `strength: 3` in collation?
6. Why is creating an index on `title` insufficient to guarantee that a query with an arbitrary collation will use it?
7. How does a unique index on `nickname` with a case-insensitive collation treat `"Minh"` and `"minh"`?
8. When users want to "find all titles containing an arbitrary phrase, accent-insensitive, ranked by relevance", why are simple regex or equality with collation insufficient?
9. Why should `_id` be added as a tie-breaker when paginating results sorted by title with collation?
10. How can you detect whether a `publishedAt` field contains both strings and Dates before deploying time-based reports?

Reliable query design starts from **data semantics**: Date represents an instant, reporting days always belong to a time zone, equality differs from pattern matching, and collation defines how strings are compared. From those choices, build filters, sorts, and indexes aligned with your application.
