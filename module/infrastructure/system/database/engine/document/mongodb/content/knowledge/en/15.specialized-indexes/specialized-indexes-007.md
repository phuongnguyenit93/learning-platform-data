# Index Collation and Query Compatibility Requirements in MongoDB

## 1. Objectives and Real-World Problem

When building applications with MongoDB, not all string comparisons carry the same meaning. A customer management system might need to:

- Find `"Lan"` when a user types `"lan"` or `"LAN"`.
- Distinguish `"cafe"` from `"café"`, or intentionally treat them as equivalent.
- Sort names according to a specific language's rules rather than raw byte values.
- Place `"item2"` before `"item10"` when sorting numbers embedded inside strings.
- Prevent two emails differing only in letter case from both being created in a collection.
- Ensure an index used to accelerate filters and sorts has **comparison rules compatible with the query**.

MongoDB uses **collation** to describe language-specific rules for comparing and sorting strings. Collation can be configured on a collection, on an index, or on an individual query operation. What matters is not merely "creating an index on `name`", but **whether the index and the query share the same string comparison semantics**.

In the **Specialized Indexes** chapter of **MongoDB Document Database Engine**, this lesson focuses on index collation and query compatibility requirements. Afterward, you will be able to:

1. Explain `locale`, `strength`, `caseLevel`, `numericOrdering`, and common options.
2. Create indexes with a specific collation, even when the collection has a different default collation.
3. Write `find`, `sort`, `countDocuments`, and `aggregate` operations using compatible collations.
4. Distinguish **correct results** from **whether an index can be used efficiently**.
5. Understand collation-based unique index constraints and their impact on existing data.
6. Analyze compound indexes with non-string components, regexes, multilingual data, and pagination.
7. Use `explain("executionStats")` to observe query planner behavior.

> **Core principle:** MongoDB can still execute a query with a requested collation even if an index lacks that collation, yet an incompatible index may **fail to support the string comparison or sorting portion**. Returning correct results and running fast are two separate questions.

## 2. What Is Collation?

**Collation** is a set of rules for comparing string values. Instead of comparing strings strictly by byte order, MongoDB can apply rules based on Unicode and locale.

For example, the two strings:

~~~text
"Lan"
"lan"
~~~

can be:

- Treated as **distinct** under default binary comparison (*simple collation*).
- Treated as **equivalent** under a case-insensitive collation at an appropriate strength.

Similarly:

~~~text
"cafe"
"café"
~~~

can match if the collation ignores diacritics, or differ if diacritic sensitivity is required.

Example configuration:

~~~javascript
{
  locale: "en",
  strength: 2
}
~~~

Typical meaning: compare using English rules, distinguishing diacritics while ignoring letter-case differences at this strength level (when no other option alters that behavior).

### 2.1. Simple Collation

~~~javascript
{ locale: "simple" }
~~~

`simple` performs binary string comparison without applying ICU language rules like standard locales. In a collection using simple collation, the equality predicate:

~~~javascript
{ name: "Lan" }
~~~

does not match a document containing only `name: "lan"`.

Simple is the default collation when you do not configure collation at the collection or operation level and no other default rule is inherited.

### 2.2. Configuration Levels

Collation appears at three common scopes:

~~~text
Collection default collation
          |
          +--> Index may inherit default or declare its own
          |
          +--> Operation may inherit default or declare its own
                     |
                     +--> find / sort / count / aggregate ...
~~~

"Same indexed field" alone is not enough. For string comparisons, check whether the **operation's collation** is compatible with the **index's collation**.

## 3. Important Collation Options

### 3.1. `locale`

`locale` specifies which language rules to apply:

~~~javascript
{ locale: "en" } // English
{ locale: "vi" } // Vietnamese
{ locale: "fr" } // French
{ locale: "simple" } // binary comparison
~~~

Alphabetical sorting and accent/diacritic rules vary by locale. When real data contains Vietnamese names, determine whether users expect sorting by `vi`, another rule, or an application-controlled normalized code.

Do not assume every field shares the same comparison semantics simply because the UI displays Vietnamese: SKUs, UUIDs, emails, person names, and product descriptions often require different comparison policies.

### 3.2. `strength`: Character Comparison Sensitivity

The three most commonly used levels:

| `strength` | General Meaning | Comparing `Lan` vs. `lan` | Comparing `cafe` vs. `café` |
|---|---|---|---|
| `1` | Primary level; typically ignores case and diacritic differences | Equivalent | Equivalent |
| `2` | Distinguishes diacritics; typically ignores case | Equivalent | Different |
| `3` | Also distinguishes case | Different | Different |

This table illustrates common Latin-script examples without special options such as `caseLevel` enabled. Real-world Unicode/locale rules can be more nuanced than these sample pairs.

Case-insensitive yet accent-sensitive example:

~~~javascript
{ locale: "en", strength: 2 }
~~~

Basic case-insensitive and accent-insensitive example:

~~~javascript
{ locale: "en", strength: 1 }
~~~

If your product requires precise handling of Vietnamese diacritics, test actual cases rather than assuming all diacritic combinations behave as simply as `cafe/café`.

### 3.3. `caseLevel` and `caseFirst`

`caseLevel` can enable an extra case distinction level when using a lower strength:

~~~javascript
{
  locale: "en",
  strength: 1,
  caseLevel: true
}
~~~

`caseFirst` controls whether uppercase or lowercase sorts first where applicable:

~~~javascript
{
  locale: "en",
  strength: 3,
  caseFirst: "upper"
}
~~~

These options serve specialized sorting requirements. If you only want case-insensitive name lookups, `strength: 2` or `strength: 1` (depending on diacritic policy) is usually easier to reason about.

### 3.4. `numericOrdering`

For strings:

~~~text
"item1"
"item2"
"item10"
~~~

Standard string comparison places `item10` before `item2` due to character-by-character ordering. To compare contiguous digit sequences inside strings numerically, specify:

~~~javascript
{
  locale: "en",
  numericOrdering: true
}
~~~

This is **string comparison with numeric sub-sequences**, not converting the entire field to a Number type. Forms such as negative numbers, decimal points, or scientific notation are not handled like full arithmetic comparisons. If numeric ordering is the primary data rule, storing numbers as a BSON numeric type is a cleaner choice.

### 3.5. Other Options

| Property | Role |
|---|---|
| `alternate` | Controls how certain punctuation/whitespace characters are handled during comparison |
| `maxVariable` | Combined with `alternate: "shifted"` to choose which character classes may be ignored at primary/secondary levels |
| `backwards` | Can compare diacritics from the end of strings per applicable locale rules |
| `normalization` | Controls Unicode normalization during comparison |
| `caseFirst` | Adjusts uppercase vs. lowercase precedence when sorting |
| `numericOrdering` | Compares contiguous digit sequences by numeric value |

Some options only take effect alongside companion settings. Do not add every option to every index; start from the comparison rules your product actually requires.

## 4. Preparing the Practice Dataset

Use a dedicated database to avoid affecting real data:

~~~javascript
use collation_index_lab
~~~

Create a standard collection with no special default collation:

~~~javascript
if (db.getCollectionInfos({ name: "people" }).length === 0) {
  db.createCollection("people");
}
~~~

Insert sample data using `replaceOne` by ID so the script is idempotent:

~~~javascript
const samplePeople = [
  {
    _id: 1,
    name: "Lan",
    city: "Hà Nội",
    age: NumberInt(21),
    code: "item2",
    groupId: NumberInt(10)
  },
  {
    _id: 2,
    name: "lan",
    city: "Hà Nội",
    age: NumberInt(22),
    code: "item10",
    groupId: NumberInt(10)
  },
  {
    _id: 3,
    name: "LAN",
    city: "Huế",
    age: NumberInt(23),
    code: "item1",
    groupId: NumberInt(10)
  },
  {
    _id: 4,
    name: "cafe",
    city: "Đà Nẵng",
    age: NumberInt(24),
    code: "item9",
    groupId: NumberInt(20)
  },
  {
    _id: 5,
    name: "café",
    city: "Đà Nẵng",
    age: NumberInt(25),
    code: "item12",
    groupId: NumberInt(20)
  },
  {
    _id: 6,
    name: "Anh",
    city: "Huế",
    age: NumberInt(20),
    code: "item11",
    groupId: NumberInt(30)
  },
  {
    _id: 7,
    name: "anh",
    city: "Hà Nội",
    age: NumberInt(30),
    code: "item3",
    groupId: NumberInt(30)
  }
];

samplePeople.forEach(person => {
  db.people.replaceOne(
    { _id: person._id },
    person,
    { upsert: true }
  );
});

db.people.countDocuments({});
~~~

On a fresh collection, the result is **7 documents**. Re-running the seed snippet resets those 7 documents, though MongoDB will not automatically delete any extra records added separately to the collection.

### 4.1. Inspecting Data Before Applying Collation

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1, code: 1 }
).sort({ _id: 1 });
~~~

The dataset deliberately includes three `Lan`/`lan`/`LAN` variants, two `cafe`/`café` variants, and codes `item1`/`item2`/`item10`.

These cases let you observe differences between:

- Binary comparison vs. locale comparison.
- Accent-sensitive vs. accent-insensitive comparison.
- Equality filtering vs. sorting.
- Standard string sorting vs. `numericOrdering`.

## 5. Creating Indexes with Explicit Collation

### 5.1. Default Index and Case-Insensitive Index

Create an index on `name` with `en` collation and `strength: 2`:

~~~javascript
db.people.createIndex(
  { name: 1 },
  {
    name: "idx_name_en_strength2",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

This index orders string keys according to the configured collation rules. It can assist string comparisons or sorts **with a compatible collation** when the query planner chooses it.

Inspect index metadata:

~~~javascript
db.people.getIndexes();
~~~

In the definition of `idx_name_en_strength2`, check the `collation` field. Exact displayed fields depend on MongoDB version, yet the configured collation is the key setting to verify.

### 5.2. Adding a Simple Index on the Same Field

You can create multiple indexes with the same key pattern but **different collations**, using distinct index names:

~~~javascript
db.people.createIndex(
  { name: 1 },
  {
    name: "idx_name_simple",
    collation: { locale: "simple" }
  }
);
~~~

Here two indexes share the `{name:1}` key pattern while having different string ordering semantics:

| Index | Key Pattern | Collation |
|---|---|---|
| `idx_name_en_strength2` | `{name:1}` | `{locale:"en", strength:2}` |
| `idx_name_simple` | `{name:1}` | `{locale:"simple"}` |

This makes sense when an application genuinely needs both case-insensitive lookup and binary comparison. However, **every additional index consumes storage and write maintenance overhead**. Do not keep two indexes just because of an example; measure production workloads.

### 5.3. Why Must You Specify Index Names?

When multiple indexes share a key pattern with different collations, distinct index names simplify administration and prevent name collisions. Naming conventions should express intent:

~~~text
idx_name_simple
idx_name_en_strength2
idx_code_numeric_en
uniq_email_en_ci
~~~

Do not guess actual configuration from the name alone; always check `getIndexes()` to verify the definition stored on the server.

## 6. Queries Must Have a Collation Compatible with the Index

### 6.1. Query Without Explicit Collation

The `people` collection was created with defaults and no collation specified, so it uses simple collation. The query:

~~~javascript
db.people.find({
  name: "lan"
});
~~~

under simple comparison selects only the document with `name: "lan"`, i.e., ID **2**, without matching `Lan` or `LAN`.

Because this query uses simple collation, the simple index can serve the string comparison. `idx_name_en_strength2` has different semantics and cannot act as an equivalent simple index for this string predicate.

### 6.2. Query Specifying the Same Collation as the Index

~~~javascript
db.people.find(
  { name: "lan" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 2
}).sort({ _id: 1 });
~~~

With the sample dataset, the result is IDs **1, 2, 3**.

In this query, the operation's collation matches `idx_name_en_strength2`. The index can optimize string lookups under those semantics. The query planner may still pick another plan when the collection is tiny or estimated costs favor a different plan.

### 6.3. Query Using a Different Strength

~~~javascript
db.people.find({
  name: "lan"
}).collation({
  locale: "en",
  strength: 3
});
~~~

`strength: 3` requires case sensitivity, which the `strength: 2` index does not provide equivalently. Do not expect a strength-2 index to serve the exact string lookup semantics of a strength-3 query.

If the application regularly searches at strength 3, consider an index with that matching collation or use simple collation if binary semantics match requirements.

### 6.4. Practical Compatibility Matrix

| Query | `name` Index Strength 2 | `name` Index Simple | Notes |
|---|---|---|---|
| `find({name:"lan"})` default simple | Incompatible for simple string equality | Compatible | Returns only `lan` |
| `find({name:"lan"}).collation({locale:"en",strength:2})` | Compatible | Incompatible for case-insensitive equality | Returns all three `Lan` variants |
| `find({name:"lan"}).collation({locale:"en",strength:1})` | Not fully equivalent | Not equivalent | Strength 1 also ignores diacritics |
| `find({name:"lan"}).collation({locale:"en",strength:3})` | Not equivalent | Not equivalent | Strength 3 distinguishes case |
| `find({age:22})` | Collation does not determine numeric equality | Can use an index if a suitable `age` key exists | Do not confuse collation compatibility with index field presence |

"Compatible" in this table means the index has **matching semantics**, not that MongoDB is guaranteed to choose it on every dataset.

### 6.5. Why Cannot Incompatible Indexes Substitute for Each Other?

A string index does not store bytes in arbitrary order; it is ordered according to the collation's comparison rules.

If an index is organized treating `"Lan"`, `"lan"`, and `"LAN"` as equivalent keys, it cannot use the same key-lookup boundaries to execute binary comparisons that require distinguishing those exact strings.

Conversely, a simple index cannot natively supply locale equivalence groups without extra work. MongoDB can scan data and apply the query's collation afterward, yet that cost differs from a compatible index lookup.

## 7. Verifying with `explain()`

### 7.1. Query with a Compatible Collation

~~~javascript
db.people.find({
  name: "lan"
})
.collation({ locale: "en", strength: 2 })
.explain("executionStats");
~~~

Details to inspect:

- `winningPlan`: chosen execution plan.
- `IXSCAN`: whether an index scan is used.
- `COLLSCAN`: collection scan.
- `indexName`: index name if the plan performs an index scan.
- `indexBounds`: index key bounds scanned.
- `totalKeysExamined`: number of index keys examined.
- `totalDocsExamined`: number of documents inspected.
- `nReturned`: number of returned documents.

Seeing `IXSCAN` on `idx_name_en_strength2` indicates the compatible index was chosen.

### 7.2. Simple Query

~~~javascript
db.people.find({
  name: "lan"
})
.collation({ locale: "simple" })
.explain("executionStats");
~~~

Compare the plan with Section 7.1. Seeing the planner choose `idx_name_simple` reflects the match between query comparison rules and index collation.

### 7.3. Query with an Incompatible Collation

~~~javascript
db.people.find({
  name: "lan"
})
.collation({ locale: "en", strength: 1 })
.explain("executionStats");
~~~

This query ignores more differences than the strength-2 index. Do not assume it runs as a direct equality lookup on the strength-2 index.

**Data-size note:** With only 7 documents, MongoDB may pick `COLLSCAN` in every case because total cost is negligible. Do not conclude a collation index "isn't working" solely because the planner prefers a collection scan on a tiny sample set.

### 7.4. Do Not Force `hint()` to "Prove Compatibility"

You can use `hint()` when inspecting plans, yet forcing an index with an incompatible collation **does not turn it into an index capable of serving the string comparison directly**. The server may have to scan excessive keys or apply residual filtering.

For performance evaluation, observe the default plan first, then compare meaningful alternatives on representative data—rather than hinting an index, seeing `IXSCAN`, and assuming it is optimal.

## 8. Collection Default Collation and Inheritance

### 8.1. Creating a Collection with a Default Collation

Besides specifying collation per index, you can create a collection with a default collation:

~~~javascript
use collation_index_lab

if (db.getCollectionInfos({ name: "catalogDefaultCI" }).length === 0) {
  db.createCollection("catalogDefaultCI", {
    collation: {
      locale: "en",
      strength: 2
    }
  });
}
~~~

On a collection with a default collation like this:

- Queries without an explicit collation inherit the collection's default collation.
- Indexes created without an explicit collation inherit the collection's default collation.
- Individual indexes can still declare a different collation when needed.

Example:

~~~javascript
db.catalogDefaultCI.createIndex(
  { title: 1 },
  { name: "idx_title_default" }
);
~~~

`idx_title_default` inherits the collection's collation when created this way.

Inspect metadata:

~~~javascript
db.getCollectionInfos({ name: "catalogDefaultCI" });
db.catalogDefaultCI.getIndexes();
~~~

### 8.2. Queries Need Not Repeat It When Using the Default

~~~javascript
db.catalogDefaultCI.insertMany([
  { _id: 1, title: "MongoDB Guide" },
  { _id: 2, title: "mongodb guide" }
]);

db.catalogDefaultCI.find({
  title: "MONGODB GUIDE"
});
~~~

In a fresh collection defaulting to `locale:"en", strength:2`, a query without `.collation()` matches both variants by inheriting the default collation.

Re-running `insertMany` triggers duplicate `_id`; that is a seed-data error, not a collation error. Use `replaceOne(..., {upsert:true})` if you want idempotent reseeding.

### 8.3. When Should You Specify `simple` to Override?

To run a binary comparison on a collection whose default is case-insensitive:

~~~javascript
db.catalogDefaultCI.find({
  title: "MongoDB Guide"
}).collation({
  locale: "simple"
});
~~~

This command requests simple collation, overriding the collection default. If you need to accelerate **strings under simple collation**, consider adding an index with simple collation:

~~~javascript
db.catalogDefaultCI.createIndex(
  { title: 1 },
  {
    name: "idx_title_simple",
    collation: { locale: "simple" }
  }
);
~~~

Merely having an index on `title` does not mean queries with any arbitrary collation will be served efficiently by that index.

### 8.4. Do Not Arbitrarily Change Default Collation After Creation

Decide on default collation when designing the collection. On an existing collection, do not assume a routine `collMod` can change the entire default collation and automatically convert all indexes. Changing collection-level comparison rules typically requires a migration, new collection creation, or index rebuild process tailored to your server capabilities and data.

When you need a new collation for a specific query, set collation at the operation level alongside a matching index rather than rushing to alter collection-wide settings.

## 9. Sorting with Collation and Index Compatibility

Collation governs more than equality filters—it also determines **string sort order**.

### 9.1. Sorting with Simple Collation

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1 }
)
.sort({ name: 1, _id: 1 })
.collation({ locale: "simple" });
~~~

MongoDB compares names using simple ordering. Uppercase, lowercase, and diacritics can produce an order very different from what users expect in a directory.

### 9.2. Sorting by Locale and Strength

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1 }
)
.sort({ name: 1, _id: 1 })
.collation({
  locale: "en",
  strength: 2
});
~~~

`Lan`/`lan`/`LAN` tie at this collation strength. When you want **deterministic pagination order across pages**, include a unique tie-breaker field such as `_id`.

Do not generalize the exact ordering of every accented character in every locale from one small sample; ICU versions and environment details can affect subtle sorting rules.

### 9.3. Indexes for Collation-Aware Sorting

If the application regularly sorts by name with `en, strength:2`, a single `{name:1}` index with that collation is a candidate. For sorts with an `_id` tie-breaker:

~~~javascript
db.people.createIndex(
  { name: 1, _id: 1 },
  {
    name: "idx_name_id_en_strength2",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

Query:

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1 }
)
.sort({ name: 1, _id: 1 })
.collation({ locale: "en", strength: 2 })
.explain("executionStats");
~~~

When the matching index is chosen, MongoDB can avoid expensive in-memory sorting. If collations mismatch, the index cannot provide the requested sort order and the server may have to perform a separate sort stage.

### 9.4. Sorting Numbers Embedded in Strings

Example:

~~~javascript
db.people.find(
  {},
  { _id: 1, code: 1 }
)
.sort({ code: 1, _id: 1 })
.collation({
  locale: "en",
  numericOrdering: true
});
~~~

For codes like `item1`, `item2`, `item10`, numeric ordering yields the natural order readers expect compared to simple lexicographical sorting.

If this query is frequent, an index `{code:1}` with the exact same collation can support the sort:

~~~javascript
db.people.createIndex(
  { code: 1 },
  {
    name: "idx_code_numeric_en",
    collation: {
      locale: "en",
      numericOrdering: true
    }
  }
);
~~~

A query using `numericOrdering:true` and one without it do not share the same sort rules. Never treat two index configurations as equivalent merely because both use `locale:"en"`.

## 10. Unique Indexes and Collation: Semantic Duplicate Prevention

A signup system may treat uppercase and lowercase emails as the same business key. A unique index with a suitable collation enforces that rule on the server.

### 10.1. Creating a Case-Insensitive Unique Index

Create a separate practice collection:

~~~javascript
use collation_index_lab

if (db.getCollectionInfos({ name: "accountsUnique" }).length === 0) {
  db.createCollection("accountsUnique");
}
~~~

Create the index:

~~~javascript
db.accountsUnique.createIndex(
  { email: 1 },
  {
    name: "uniq_email_en_strength2",
    unique: true,
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Insert the first document:

~~~javascript
db.accountsUnique.insertOne({
  _id: "acc-001",
  email: "Hello@example.test",
  displayName: "First account"
});
~~~

Try inserting an email differing only in case:

~~~javascript
// Duplicate key error expected due to unique index with collation.
db.accountsUnique.insertOne({
  _id: "acc-002",
  email: "hello@example.test",
  displayName: "Second account"
});
~~~

Because the unique index's collation treats both strings as equivalent, inserting the second record is rejected with an **E11000 duplicate key** error.

### 10.2. A Unique Index Does Not Rewrite Stored Data

The index does not lowercase stored strings. The first document retains `"Hello@example.test"`; uniqueness is evaluated at write time using the index's comparison rules.

If the application needs uniform display and lookup casing, normalize emails to canonical form at the application layer. Keep in mind international email standards and business rules can be nuanced; locale collation does not replace a full identity/email policy.

### 10.3. Do Not Create a Unique Index Before Resolving Existing Duplicates

If the collection already contains:

~~~javascript
{ _id: 1, email: "Hello@example.test" }
{ _id: 2, email: "hello@example.test" }
~~~

creating a case-insensitive **unique index** will fail because existing data violates the constraint. You must:

1. Identify all strings considered duplicates under the target collation.
2. Decide which records to keep, merge, or update.
3. Clean up legacy data via a controlled process.
4. Create the unique index.
5. Monitor write errors from the application and surface clear messages to users.

Never run bulk deletes merely to make `createIndex` succeed without a data-preservation plan.

### 10.4. Strength 1 vs. Strength 2 for Uniqueness

For `cafe` and `café`:

- At strength 1, they can be treated as equivalent → the unique index will forbid storing both as distinct unique keys under that collation.
- At strength 2, they remain distinct values because diacritics are distinguished.
- At strength 3, letter case also distinguishes keys.

Therefore, before choosing a unique collation, decide the **business definition of "duplicate"**—especially for Vietnamese text, personal names, or identifiers.

### 10.5. A Unique Index Does Not Replace Other Rules

A unique collation index does not replace `_id` uniqueness, schema validation, required-field checks, or authorization. If business rules require every account to have an email, add validators/logic verifying presence and type instead of relying on the unique index alone.

## 11. Compound Indexes: Non-String Key Components

One subtle behavior: when a query's collation does not match the index's collation, MongoDB can still use **a compound index prefix composed of non-string fields**, if the query conditions permit. This does not mean the index can accelerate the incompatible string comparison itself.

### 11.1. Creating a Compound Index

~~~javascript
db.people.createIndex(
  { groupId: 1, name: 1 },
  {
    name: "idx_group_name_en_strength2",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

`groupId` is stored as Int32, while `name` is a string.

### 11.2. Query Filtering Only on `groupId`

~~~javascript
db.people.find({
  groupId: NumberInt(10)
}).collation({
  locale: "simple"
}).explain("executionStats");
~~~

Even though the index uses `en/strength:2` and the query uses simple collation, MongoDB **can** still use the non-string `groupId` prefix, because integer equality does not depend on string collation rules.

Still, the query planner is not forced to pick this index if the collection is tiny or another index is cheaper.

### 11.3. Query Filtering on Both `groupId` and `name`

~~~javascript
db.people.find({
  groupId: NumberInt(10),
  name: "lan"
}).collation({
  locale: "simple"
}).explain("executionStats");
~~~

The index can assist the `groupId` portion, yet comparing `name` under simple collation **is not equivalent** to the `en/strength:2` string keys in the index. The server may need to fetch and filter extra documents or pick a different plan.

When using the same collation as the index:

~~~javascript
db.people.find({
  groupId: NumberInt(10),
  name: "lan"
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

the index can serve both predicates together along the key pattern, subject to the optimizer and statistics.

### 11.4. Do Not Assume "Collation Mismatch ⇒ Index Never Used"

Accurate rules to remember:

- **String comparisons:** to leverage the index properly, collations must be compatible.
- **Non-string key prefixes:** a compound index can still be used for predicates on that prefix even when query collation differs.
- **String sorting:** the index must have compatible ordering semantics; otherwise, an in-memory sort may be required.
- **Actual plan:** always confirm with `explain()`, never conclude from the index name alone.

This example shows why you must inspect `indexBounds`, `FETCH`, and keys/documents examined, rather than seeing `IXSCAN` and assuming the entire query is index-optimized.

## 12. Collation in Aggregation and Other Query APIs

### 12.1. Specifying Collation at the Operation Level in Aggregation

Example grouping people by name case-insensitively:

~~~javascript
db.people.aggregate(
  [
    {
      $group: {
        _id: "$name",
        count: { $sum: 1 },
        ids: { $push: "$_id" }
      }
    },
    {
      $sort: { _id: 1 }
    }
  ],
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Aggregation collation affects string comparisons in `$group` and `$sort`. On our dataset, `Lan/lan/LAN` merge into one group under strength-2 collation.

Do not treat the representative group `_id` returned as a canonical spelling normalized by MongoDB. If the application needs a consistent display key, maintain a dedicated canonical field.

### 12.2. Aggregation `$match` and `$sort`

~~~javascript
db.people.aggregate(
  [
    { $match: { name: "lan" } },
    { $sort: { name: 1, _id: 1 } },
    { $project: { _id: 1, name: 1 } }
  ],
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Like `find()`, an aggregation pipeline needs a compatible collation and index-eligible leading stages for the optimizer to exploit a string index.

Aggregation collation is an **operation-level option**, not separate per-stage collations for `$match` and `$sort` inside the same command.

### 12.3. `countDocuments` with Collation

~~~javascript
db.people.countDocuments(
  { name: "lan" },
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

With the sample data and no extra records, the result is **3**. Counting without specifying collation uses `people`'s simple default, so `name: "lan"` matches only one document.

This is a classic bug in paginated APIs: page items are queried case-insensitively while total count runs under simple collation, causing `items` and `total` to describe different datasets.

### 12.4. `distinct` and Collation

Several distinct-value APIs also support collation. To pass options explicitly without depending on shell helper variants, you can run the database command:

~~~javascript
db.runCommand({
  distinct: "people",
  key: "name",
  query: {},
  collation: {
    locale: "en",
    strength: 2
  }
});
~~~

Which strings count as distinct depends on the specified collation. When reporting unique counts or name lists, align that rule with both business logic and indexes.

### 12.5. One Operation Cannot Arbitrarily Mix Multiple Collations

When a query both filters and sorts strings, the operation's collation generally applies uniformly across affected comparisons. If a requirement wants `name` case-insensitive while `code` uses exact binary matching, design your data model and filters accordingly rather than expecting to attach two independent collations to two fields in one standard query.

One strategy is storing separate canonical fields—such as `nameNormalized` and `codeExact`—with explicit derivation rules. Every extra field adds synchronization overhead and must be updated consistently.

## 13. `$regex` and Case-Insensitive Indexes: An Often-Overlooked Exception

A common misconception: "Once a case-insensitive index exists, any case-insensitive regex query automatically runs fast."

Example:

~~~javascript
db.people.find({
  name: /^lan/i
});
~~~

`$regex` is not collation-aware the way ICU collation equality and sort comparisons are. Therefore, **a case-insensitive collation index typically does not efficiently accelerate case-insensitive `$regex` queries**.

Adding collation to the query:

~~~javascript
db.people.find({
  name: /^lan/i
}).collation({
  locale: "en",
  strength: 2
});
~~~

does not turn a regex into a collation-index equality lookup.

### 13.1. Distinguishing Three Problems

| Requirement | Approach |
|---|---|
| Exact name lookup, case-insensitive | Equality query + compatible collation + index |
| Find strings starting with a prefix | Anchored prefix regex, or suitable search structure; measure plan |
| Fuzzy search, full-text, language-aware autocomplete | Dedicated search engine/index; do not assume collation indexes handle it |

A case-sensitive anchored prefix regex can use an index in appropriate cases, which is very different from expecting a strength-2 index to optimize arbitrary `/i` patterns.

### 13.2. When Should You Store a Normalized Field?

If the application needs case-insensitive prefix matching under a fixed rule, consider storing a normalized `nameSearch` field with an appropriate index and querying prefixes against it. However:

- Unicode and language normalization rules must be explicit.
- Simple lowercasing may not match every locale rule.
- Original display data must still be retained.
- Whenever a name changes, both original and normalized fields must stay in sync.
- For advanced search, a dedicated search solution may fit better.

Do not treat naive normalization as an automatic substitute for all locale-aware collations.

## 14. Collation and Pagination: Filter, Sort, and Count Must Agree

Suppose a user listing API needs:

~~~text
GET /people?name=lan&pageSize=2
~~~

Business rule: case-insensitive, accent-sensitive.

Filter:

~~~javascript
const filter = { name: "lan" };
const ciCollation = { locale: "en", strength: 2 };
~~~

Page query:

~~~javascript
const items = db.people.find(filter)
  .sort({ name: 1, _id: 1 })
  .collation(ciCollation)
  .limit(2)
  .toArray();
~~~

Count must use the exact same collation:

~~~javascript
const total = db.people.countDocuments(
  filter,
  { collation: ciCollation }
);
~~~

With three `Lan/lan/LAN` documents, the accurate total on the sample set is **3**, and the first page holds at most **2** documents.

### 14.1. Why Can Counts Be Wrong?

Bug:

~~~javascript
const items = db.people.find({ name: "lan" })
  .collation({ locale: "en", strength: 2 })
  .limit(2)
  .toArray();

const total = db.people.countDocuments({ name: "lan" });
~~~

On `people` (default simple), the second count matches only `"lan"`, while the page query sees all case variants. The API could return 2 items while reporting `total = 1`: the contradiction stems from **mismatched collations**, not a bug in `countDocuments`.

### 14.2. Seek Pagination on Strings with Collation

When paginating by `name` then `_id`, next-page cursor predicates must use the same collation ordering rules. Never take a cursor token generated under simple collation and apply it to a strength-2 query.

A cursor token should be bound to:

- Locale and collation options.
- Sort order and tie-breaker key.
- Filter/tenant scope and authorization context.
- BSON values of the last key from the previous page.

When changing sort or collation policies, invalidate old cursor tokens to avoid skipped or duplicated documents.

### 14.3. Collation-Aware Equality Can Produce Sort Ties

At `strength: 2`, `Lan`, `lan`, and `LAN` tie in string comparison. Sorting solely by `{name:1}` leaves their relative order non-deterministic for pagination.

Adding `_id` to the sort with a matching index ensures deterministic ordering. However, if `_id` itself is a string, secondary key comparison may also be affected by collation; verify ordering and uniqueness against real data types. Our sample uses numeric `_id` values, so the tie-breaker is unaffected by case differences.

## 15. Inspecting Index Collation via Metadata

The primary tool is:

~~~javascript
db.people.getIndexes();
~~~

Output contains objects with `key`, `name`, `collation`, `unique`, and related metadata.

Illustrative output:

~~~javascript
[
  {
    name: "idx_name_en_strength2",
    key: { name: 1 },
    collation: {
      locale: "en",
      strength: 2
      // Other default properties may appear.
    }
  },
  {
    name: "idx_name_simple",
    key: { name: 1 }
  }
]
~~~

Indexes with simple collation may omit an explicit `collation` object unlike locale-aware indexes; always verify the actual configured behavior from server output.

Inspect collection defaults:

~~~javascript
db.getCollectionInfos({ name: "people" });
db.getCollectionInfos({ name: "catalogDefaultCI" });
~~~

Distinguish:

- Collection `options.collation`: default for operations and indexes when not overridden.
- Per-index `collation`: how that index orders strings.
- Operation `collation(...)` or option: how a query compares/sorts strings.

### 15.1. Checklist for Diagnosing Why an Index Was Not Selected

When a query returns accurate results yet runs slowly, check in order:

1. **Fields and key pattern:** does the index cover the filtered/sorted fields?
2. **Operation collation:** does the query use simple, `en`, `vi`, or another configuration?
3. **Index collation:** does it have matching `locale`, `strength`, and options?
4. **Collection default:** is an unconfigured query inheriting an unexpected default?
5. **Types:** is the field string, number, Date, or mixed BSON types?
6. **Filter and sort:** is there a matching key prefix, or a blocking sort?
7. **Special predicates:** are there regexes or operators not optimized like equality?
8. **Data/selectivity:** does the index meaningfully reduce keys/documents scanned?
9. **Plan:** what do `IXSCAN`, `COLLSCAN`, `FETCH`, and `SORT` show in `explain`?
10. **Test scale:** is the collection so small that a full scan is cheaper?

These steps are purely for query-plan analysis; they do not mean you should immediately create or drop indexes without evaluation.

## 16. Multilingual Data and Business Requirements

### 16.1. One Collection Holding Names from Many Countries

If data mixes Vietnamese, English, French, and technical identifiers, a single default collation rarely suits every field.

For example:

- `displayName` may need sorting in the UI's active locale.
- `username` may follow fixed normalization rules independent of viewer locale.
- `productCode` usually needs exact identifier matching.
- `description` needs full-text word search, not equality checks.

Avoid creating one English case-insensitive index and assuming every language UI will get its expected alphabetical order.

### 16.2. When Should You Create Multiple Collation Indexes?

It can be justified when an application genuinely has two distinct critical workloads:

~~~text
Workload A: case-insensitive name lookups in en
Workload B: binary name sorting for technical data sync
~~~

Two indexes sharing the key pattern with different collations can serve both needs. However, if the application only uses one comparison mode, a single matching index is simpler.

When users dynamically choose among many locales, creating an index per locale grows maintenance costs quickly. Identify which locales are actually queried, analyze patterns, and consider alternative search architectures if highly dynamic multilingual sorting is required.

### 16.3. Do Not Treat Collation as Data Cleansing

Collation can make `"Lan"` and `"lan"` match in queries, yet it does not fix raw values stored on disk.

If business rules require:

- Usernames containing only an allowed character set.
- Canonicalized, unique emails.
- Original person names preserved alongside a dedicated search field.
- SKUs conforming to a strict format and type.

combine schema validation, application logic, and unique indexes per your data contract. Collation is solely a **comparison rule**, not a general normalization pipeline.

## 17. MongoDB Compass: Viewing Indexes and Testing Queries

MongoDB Compass lets you inspect documents, index definitions, and filters visually. Exact tab/button names vary by version, yet the basic workflow is:

1. Connect Compass to the same MongoDB server/cluster used in `mongosh`.
2. Open the `collation_index_lab` database and `people` collection.
3. Open **Indexes** and inspect `idx_name_en_strength2` and `idx_name_simple` along with their options if shown.
4. Open **Documents** and test the filter:

   ~~~json
   {"name":"lan"}
   ~~~

5. Check **Collation/Options** in the query bar if your Compass version supports it. Set `locale: "en"`, `strength: 2`, and compare against simple.
6. If Compass provides **Explain Plan**, compare the selected index name and keys/docs examined.
7. Run the identical query in `mongosh` with `.collation(...)` to confirm server results.
8. Test `name: "cafe"` at strength 1 vs. strength 2 and observe diacritic differences.
9. To test case-insensitive uniqueness, use `accountsUnique` from Section 10 and observe duplicate-key errors.

Do not assume every Compass version exposes identical collation UI controls for document queries. Whenever the UI omits options, use `mongosh` for exact verification.

## 18. Collation in the MongoDB Java Driver

Java Driver example using `Filters`, `Collation`, and `CollationStrength`. Assume `database` is a properly connected `MongoDatabase`:

~~~java
import static com.mongodb.client.model.Filters.eq;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

MongoCollection<Document> people =
    database.getCollection("people");

Collation caseInsensitive = Collation.builder()
    .locale("en")
    .collationStrength(CollationStrength.SECONDARY)
    .build();

List<Document> items = people.find(eq("name", "lan"))
    .collation(caseInsensitive)
    .into(new ArrayList<>());

System.out.println("Matching people: " + items.size());
~~~

`CollationStrength.SECONDARY` corresponds to strength 2 in this API.

### 18.1. Creating an Index from Java

~~~java
import static com.mongodb.client.model.Indexes.ascending;

import com.mongodb.client.model.IndexOptions;

String indexName = people.createIndex(
    ascending("name"),
    new IndexOptions()
        .name("idx_name_ci_java")
        .collation(caseInsensitive)
);
~~~

This snippet only demonstrates the API. If a similar index already exists or collides with an older index name, manage index names and creation policies explicitly. Never create new indexes on every application request.

### 18.2. Counts Must Use the Same Collation

~~~java
import com.mongodb.client.model.CountOptions;

long total = people.countDocuments(
    eq("name", "lan"),
    new CountOptions().collation(caseInsensitive)
);
~~~

If the page query uses strength-2 collation while count omits it, `total` can disagree with displayed items. Filters, tenant scopes, permissions, collation, and any option affecting semantics must be shared across both queries.

### 18.3. Collation in Aggregation

~~~java
import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Aggregates.sort;
import static com.mongodb.client.model.Sorts.ascending;

import org.bson.conversions.Bson;

import java.util.List;

List<Bson> pipeline = List.of(
    match(eq("name", "lan")),
    sort(ascending("name", "_id"))
);

List<Document> result = people.aggregate(pipeline)
    .collation(caseInsensitive)
    .into(new ArrayList<>());
~~~

This snippet shows query invocation, not a standalone application. In Spring Data MongoDB projects, verify how the framework propagates collation into queries and aggregations rather than assuming every repository method applies it automatically.

## 19. Common Errors and Misconceptions

| Symptom or Misconception | Common Cause | Fix |
|---|---|---|
| Index on `name` exists, yet case-insensitive query is slow | Simple index, query uses `en/strength:2` | Create/use an index with compatible collation and verify `explain()` |
| Query returns right results yet shows `COLLSCAN` | No matching index, tiny dataset, or planner prefers scan | Check index, collation, selectivity; don't infer a bug from scan alone |
| Searching `"lan"` misses `"Lan"` | Simple collation used | Specify appropriate collation or collection default |
| Searching `"cafe"` unexpectedly matches `"café"` | Strength ignores diacritics | Pick a strength that distinguishes diacritics if required |
| Case-insensitive unique index build fails | Legacy data collides under new collation | Audit/cleanse duplicates before creating the index |
| Two indexes on the same field raise a name error | No distinct names or conflicting options | Assign distinct names; inspect `getIndexes()` |
| Created collation index, yet queries ignore it | Operations default to simple or another collation | Specify matching collation on queries |
| Collection defaults to CI, yet exact match is needed | Query inherits default CI collation | Override `locale:"simple"` and add a simple index if needed |
| `countDocuments` total disagrees with list results | Count lacks collation or differs in filter | Share identical filter/collation/permission scope |
| CI index does not speed up `/i` regex | Regex is not collation-aware like equality | Use appropriate prefix/search design; inspect plan |
| Sorting is slow despite field index | Index collation/sort order mismatches | Build an index matching both sort order and collation |
| `numericOrdering` mishandles negatives or decimals | It orders digit runs in strings, not numeric fields | Store BSON numbers if arithmetic ordering is required |
| Compound index still shows `IXSCAN` when collation differs | Index may use a non-string prefix | Inspect `indexBounds`, `FETCH`, and `totalKeysExamined` |
| Assuming same locale with different strengths are equal | Strength alters case/diacritic distinction | Verify all collation options |
| Multilingual queries produce unexpected sort order | Locale does not match users/data | Confirm actual locale and test with representative data |
| Case-insensitive lookups still store mixed case | Collation governs comparison only | Normalize on write or keep a canonical field if needed |
| Pagination skips or repeats documents | Sort lacks a unique tie-breaker or cursor lacks collation | Add unique tie-breaker; keep filter/sort/collation consistent |

## 20. Practice Exercises

The exercises below use `collation_index_lab.people` with its 7 sample records and the two indexes created in Section 5. If other data exists, returned IDs may differ.

### Exercise 1. Comparing Simple vs. Case-Insensitive

Run:

~~~javascript
db.people.find(
  { name: "lan" },
  { _id: 1, name: 1 }
).sort({ _id: 1 });

db.people.find(
  { name: "lan" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 2
}).sort({ _id: 1 });
~~~

Expected results:

- Simple: ID **2**.
- Strength 2: IDs **1, 2, 3**.

Explain why the field and filter literal stay identical while the results differ.

### Exercise 2. Distinguishing Diacritics

Compare:

~~~javascript
db.people.find(
  { name: "cafe" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 1
}).sort({ _id: 1 });

db.people.find(
  { name: "cafe" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 2
}).sort({ _id: 1 });
~~~

At strength 1, both `cafe` and `café` can match (IDs **4, 5**). At strength 2, only ID **4** is expected under the example's diacritic rules. Derive how to choose strength from business needs.

### Exercise 3. Reading Index Definitions

~~~javascript
db.people.getIndexes();
~~~

Locate the name, key pattern, and collation of:

- `idx_name_en_strength2`.
- `idx_name_simple`.

Even if a UI or output omits some default attributes, learn to distinguish an explicitly collated index from a simple index.

### Exercise 4. Explain with Two Collations

~~~javascript
db.people.find({ name: "lan" })
  .collation({ locale: "en", strength: 2 })
  .explain("executionStats");

db.people.find({ name: "lan" })
  .collation({ locale: "simple" })
  .explain("executionStats");
~~~

Record `winningPlan`, `indexName` (if any), `totalKeysExamined`, and `totalDocsExamined`. Explain why on 7 documents, `COLLSCAN` does not automatically mean the index is broken.

### Exercise 5. Case-Insensitive Unique Email

Create `accountsUnique` and the index from Section 10. Insert:

~~~javascript
db.accountsUnique.insertOne({
  _id: "acc-101",
  email: "Student@example.test"
});
~~~

Then try:

~~~javascript
db.accountsUnique.insertOne({
  _id: "acc-102",
  email: "student@example.test"
});
~~~

**Expected:** The second insert is rejected because the unique index treats both strings as equivalent. Explain why dropping the unique index or changing strength changes the definition of "duplicate".

### Exercise 6. Collection Default Collation

Inspect:

~~~javascript
db.getCollectionInfos({ name: "catalogDefaultCI" });
db.catalogDefaultCI.getIndexes();
~~~

Explain why a query without `.collation()` on this collection can still be case-insensitive. Then test overriding with `{locale:"simple"}` and compare results.

### Exercise 7. Count and List Sharing the Same Collation

~~~javascript
const query = { name: "lan" };
const ci = { locale: "en", strength: 2 };

const total = db.people.countDocuments(
  query,
  { collation: ci }
);

const items = db.people.find(query)
  .collation(ci)
  .limit(2)
  .toArray();

printjson({
  total: total,
  pageItems: items.length
});
~~~

**Result:** `total = 3`, `pageItems = 2`.

Try removing `collation` from `countDocuments`. Why can `total` drop to 1 and disagree with the page results?

### Exercise 8. `numericOrdering`

~~~javascript
db.people.find(
  {},
  { _id: 1, code: 1 }
).sort({ code: 1 })
.collation({
  locale: "en",
  numericOrdering: true
});
~~~

Compare the ordering of `item1`, `item2`, `item10` against a query using simple collation. When should you store a separate numeric field instead of relying on `numericOrdering`?

### Exercise 9. Compound Index with a Numeric Prefix

Create index:

~~~javascript
db.people.createIndex(
  { groupId: 1, name: 1 },
  {
    name: "idx_group_name_en_strength2",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

Run:

~~~javascript
db.people.find({
  groupId: NumberInt(10),
  name: "lan"
}).collation({
  locale: "simple"
}).explain("executionStats");
~~~

Explain why the index can assist `groupId` yet cannot directly satisfy the name comparison under simple collation.

### Exercise 10. Regex and Collation

~~~javascript
db.people.find({
  name: /^lan/i
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

Explain why having a case-insensitive index does not guarantee `/i` regex queries are optimized like equality query `{name:"lan"}` with strength-2 collation.

### Exercise 11. Choosing Collation for Business Needs

| Need | Suitable Approach |
|---|---|
| Find names case-insensitively while distinguishing diacritics | Equality with matching locale, strength 2, and compatible index |
| Find names ignoring both case and diacritics | Consider strength 1; test against real data |
| Compare product codes byte-for-byte | Simple collation or separately managed canonical key |
| Case-insensitive unique username | Unique index with matching collation and canonical policy |
| Sort strings with numbers like `item2`/`item10` | `numericOrdering:true` or store a separate numeric field |
| Case-insensitive arbitrary prefix search | Do not assume collation index optimizes `/i` regex; design search appropriately |
| Locale-aware pagination by name | Same collation across filter, sort, count, seek cursor, and unique tie-breaker |
| Multiple user locales | Analyze workload/index budget; never create unbounded indexes for every locale |

## 21. Principles for Deploying Collation Indexes in Projects

1. **Define semantics before creating indexes.** Distinguish exact byte matching, case-insensitivity, diacritic-insensitivity, and locale-specific sorting.
2. **Choose appropriate locale and strength.** Do not assume all string comparisons share one definition of "equal".
3. **Keep operations synchronized with indexes.** Filters, sorts, counts, and aggregations must use compatible collations to both return correct results and utilize indexes.
4. **Understand collection defaults.** Queries omitting collation inherit collection defaults, not necessarily `simple`.
5. **Remember unique semantics.** A collation-based unique index blocks visually distinct strings that compare equivalent.
6. **Evaluate compound index prefixes.** Differing collations do not preclude using non-string prefix fields in a compound index.
7. **Do not confuse equality with regex.** A case-insensitive collation index does not automatically optimize `/i` regex queries.
8. **Use `explain()` on real data.** Inspect `indexName`, `indexBounds`, keys/docs examined, and `SORT`; avoid judging from key patterns alone.
9. **Keep pagination consistent.** Use identical filters, sorts, collations, and tie-breaker keys across pages and counts; bind seek tokens to the sort policy.
10. **Account for index maintenance costs.** Multiple indexes with different collations mean extra storage and write overhead.
11. **Clean data before adding new unique indexes.** Existing records may collide under the chosen collation rules.
12. **Document policies.** Whenever an API changes collation or normalization rules, check compatibility with existing data and consumers.

Collation lets MongoDB compare and sort strings in ways aligned with human languages and business requirements. However, **an index efficiently supports only operations whose comparison semantics are compatible with it**. Understanding how collection defaults, index collations, and operation collations interact is essential for accurate queries, duplicate prevention, and sustainable performance.

## References

- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — Indexes and Collation](https://www.mongodb.com/docs/manual/core/index-case-insensitive/)
- [MongoDB Manual — createIndex](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
