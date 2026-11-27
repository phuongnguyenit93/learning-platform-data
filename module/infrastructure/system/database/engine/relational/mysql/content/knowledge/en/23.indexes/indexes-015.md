# Distinguishing B-tree, FULLTEXT, SPATIAL, and Hash Indexes by Engine

MySQL has multiple index types because each solves a different kind of search. B-tree suits equality lookups, comparisons, and range scans; `FULLTEXT` serves word and text content search; `SPATIAL` supports geometric data queries; hash suits exact equality comparisons on engines that support it.

Not every engine supports every index type. InnoDB, MyISAM, MEMORY, and NDB Cluster differ in storage capabilities and index implementations. When designing a table, choose both the engine and index types based on query requirements, transactions, durability, and MySQL version limits.

## 1. Overview of index types

| Index type | Structure / concept | Best suited for | Unsuitable for |
|---|---|---|---|
| B-tree | Balanced tree; implemented as B+Tree in InnoDB | `=`, `<`, `>`, `BETWEEN`, prefix `LIKE`, sorting, and range scans | Natural-language search inside long text or complex spatial relationships |
| `FULLTEXT` | Inverted index mapping words/tokens to documents or rows | Word/phrase search and `FULLTEXT` text queries | Arithmetic comparisons, range scans, or general single-column sorting |
| `SPATIAL` | R-tree structure over bounding rectangles of spatial objects | Region containment, intersections, or spatial relationships | Routine primary key lookups or text string searches |
| `HASH` | Hash function mapping keys to buckets | Whole-key equality comparisons | Range scans, sort ordering, prefix searches, and greater/less comparisons |

These types are not direct drop-in replacements for one another. One table can have B-tree indexes on identifier keys, a `FULLTEXT` index on content, and a `SPATIAL` index on a geometry column if the engine supports them and the workload needs those search modes.

## 2. B-tree index: the general-purpose index type

B-tree is the most common index type in MySQL. InnoDB stores table data in a clustered index and uses B+Trees for its indexes. Pages in the tree keep keys sorted, enabling the engine to traverse from root to leaf to locate a value or scan a key interval.

Example:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status_created (status, created_at),
    KEY idx_orders_created (created_at)
) ENGINE = InnoDB;
```

B-trees can support query patterns such as:

```sql
-- Equality comparison
SELECT * FROM orders WHERE customer_id = 2001;

-- Range scan
SELECT * FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';

-- Greater/less comparison
SELECT * FROM orders WHERE order_id > 10000;

-- String prefix search
SELECT * FROM orders WHERE status LIKE 'PAI%';

-- Sorting by indexed columns when predicates and order align
SELECT order_id, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC;
```

For composite indexes, the leftmost prefix rule still applies. For example, `(status, created_at)` can serve conditions starting with `status`, followed by `created_at`. The index does not naturally serve queries filtering solely on `created_at` with equal efficiency.

### Advantages and costs

- Supports a wide variety of comparison operators and range queries.
- Can support `ORDER BY`, `GROUP BY`, and covering queries when column order aligns.
- Can be used in key-based joins.
- Consumes storage space and updates whenever relevant key values change.
- Too many indexes or overly wide indexes increase `INSERT`, `UPDATE`, and `DELETE` costs.

In InnoDB, the clustered index is a B+Tree storing row data in leaf pages; secondary indexes are also B+Trees carrying the primary key to locate rows. This is an InnoDB storage characteristic, not how every engine implements B-trees identically.

## 3. FULLTEXT index: searching text content

A `FULLTEXT` index is designed for searching words and tokens within text content. Rather than sorting whole column values like a B-tree, `FULLTEXT` uses an inverted index structure linking extracted words to rows containing them.

MySQL supports `FULLTEXT` on `CHAR`, `VARCHAR`, and `TEXT` columns. Both InnoDB and MyISAM support `FULLTEXT`; tokenization details, stopwords, and configuration can vary by engine and version.

Example creating an articles table with a `FULLTEXT` index:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    published_at DATETIME NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_articles_title_body (title, body)
) ENGINE = InnoDB;
```

Searching in natural language mode:

```sql
SELECT article_id, title,
       MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
```

`MATCH()` specifies the `FULLTEXT` columns to search; the column list must match an eligible `FULLTEXT` index. `AGAINST()` provides the search string and search mode.

### Common FULLTEXT modes

**Natural language mode** is the default mode, ranking results by word relevance within each document and across the dataset:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE);
```

**Boolean mode** allows operators to require or exclude words:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+mysql +index -oracle' IN BOOLEAN MODE);
```

In the example, `+mysql` and `+index` require those words to be present, while `-oracle` excludes results containing `oracle`. Boolean mode has its own syntax and does not rank identically to natural language mode in all scenarios.

**Query expansion** broadens searches based on relevant documents from an initial pass, which can surface additional related content while also introducing less targeted results:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('deadlock' WITH QUERY EXPANSION);
```

### Tokens, stopwords, and languages

`FULLTEXT` does not necessarily index every character sequence. Words that are too short or appear on a stopword list may be ignored depending on engine, parser, and settings. InnoDB and MyISAM have separate configurations for token length and stopwords.

For languages that do not separate words with spaces—such as Chinese, Japanese, or certain multilingual content—the default parser may not tokenize as expected. MySQL provides the ngram full-text parser for several of these languages. Test with real data and inspect parser, stopword, and token-length settings before concluding a missing search term is due to missing data.

`FULLTEXT` suits content searching, yet does not replace B-trees for predicates such as `created_at >= ...`, `price BETWEEN ...`, or foreign-key joins.

## 4. SPATIAL index: searching spatial data

`SPATIAL` indexes support geometric data types such as `POINT`, `LINESTRING`, `POLYGON`, and geometry collections. In InnoDB and MyISAM, spatial indexes use an R-tree structure over objects' minimum bounding rectangles (MBRs).

An MBR is the smallest rectangle enclosing a geometric object. Searching by MBR quickly eliminates most objects that cannot intersect the search region. After preliminary filtering, exact geometric relation checks may still be required.

Example creating a places table using InnoDB and an SRID-restricted `POINT` column:

```sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    place_name VARCHAR(150) NOT NULL,
    position POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id),
    SPATIAL INDEX sp_places_position (position)
) ENGINE = InnoDB;
```

In InnoDB, spatial indexes require geometry columns to have a fixed SRID (SRID-restricted). Declaring an SRID informs the engine of the coordinate system and enables spatial query optimizations. Keep coordinate systems consistent between stored data and query geometries.

Example finding points within a search region:

```sql
SET @search_area = ST_GeomFromText(
    'POLYGON((106.60 10.70, 106.80 10.70, 106.80 10.90,
             106.60 10.90, 106.60 10.70))',
    4326
);

SELECT place_id, place_name
FROM places
WHERE MBRContains(@search_area, position)
  AND ST_Within(position, @search_area);
```

`MBRContains()` checks whether a point lies within the region's bounding rectangle; `ST_Within()` verifies the exact geometric relationship against the polygon. When using geographic SRIDs, pay attention to axis order per the SRS definition and WKT input; the example above illustrates longitude/latitude order, so verify `axis-order` matches your real data.

`SPATIAL` indexes do not replace B-trees on `place_id`, nor do they automatically solve all distance calculations. For nearest-distance queries, design a candidate region filter followed by exact distance computation and sorting per business rules.

## 5. HASH index: exact equality lookup

A hash index uses a hash function to map keys to buckets. It is optimized for whole-key equality comparisons, such as `WHERE token = ...`. On hash collisions, the engine still checks the actual key value to confirm matching rows.

Hash indexes do not preserve key order, making them unsuitable for:

- `BETWEEN`, `<`, `>`, `<=`, `>=`.
- `ORDER BY` on the key.
- Prefix searches such as `LIKE 'abc%'`.
- Probing a subset of a composite key without supplying the full key.

The `MEMORY` engine supports both `HASH` and `BTREE`; `HASH` is the default index type in `MEMORY` unless specified otherwise. You can declare it explicitly:

```sql
CREATE TABLE session_lookup (
    token VARBINARY(32) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    PRIMARY KEY (token) USING HASH,
    KEY idx_session_expiry (expires_at) USING BTREE
) ENGINE = MEMORY;
```

Or use a secondary `HASH` index:

```sql
CREATE TABLE feature_flags_cache (
    flag_key VARCHAR(100) NOT NULL,
    flag_value VARCHAR(255) NOT NULL,
    KEY idx_flag_key (flag_key) USING HASH
) ENGINE = MEMORY;
```

In this example, `HASH` fits exact equality lookups for a `flag_key`. If you need to scan by `expires_at` or sort chronologically, B-tree fits better.

### HASH in MEMORY is not InnoDB's Adaptive Hash Index

InnoDB has an internal Adaptive Hash Index (AHI) mechanism. InnoDB can automatically build an in-memory hash structure over frequently accessed B-tree pages to accelerate certain lookups. AHI is engine-managed; it is not an index an application declares with `CREATE INDEX ... USING HASH` on an InnoDB table.

Therefore, you cannot convert an InnoDB secondary B-tree into `HASH` simply by adding `USING HASH`. If an InnoDB workload is primarily equality lookups, B-tree remains the standard index choice; the engine may apply AHI internally when beneficial.

## 6. Support capabilities by storage engine

The following table summarizes common capabilities in MySQL 8.x. Confirm exact support against your deployed version and engine variant.

| Storage engine | B-tree / ordered index | HASH | FULLTEXT | SPATIAL | Notes |
|---|---|---|---|---|---|
| InnoDB | Yes; clustered and secondary B+Trees | No direct `HASH` index declaration; internal Adaptive Hash Index exists | Yes | Yes; geometry columns require a fixed SRID for spatial indexes | General-purpose transactional engine supporting ACID and row-level locking |
| MyISAM | Yes | Does not support standard `HASH` indexes | Yes | Yes | Does not provide transactions or foreign keys like InnoDB |
| MEMORY | Yes, via `USING BTREE` | Yes; default for indexes unless specified otherwise | No | No | Table data resides in memory and is lost on server restart |
| NDB Cluster | Has ordered indexes | Has hash indexes per NDB architecture | Does not support `FULLTEXT` like InnoDB/MyISAM | Not a typical `SPATIAL` index choice | Index mechanisms and syntax differ in NDB; check version-specific docs |

Do not choose a storage engine solely for one index type. For example, `MEMORY` offers `HASH` indexes, yet data in `MEMORY` tables is lost across server restarts and the engine has data type, sizing, and feature limits. If business data requires transactions, foreign keys, and durability, InnoDB is usually the right fit.

## 7. Choosing an index type by problem

| Requirement | Index type to consider | Example |
|---|---|---|
| Key lookup, range comparison, sorting | B-tree | Finding orders by `customer_id` or `created_at` |
| Word search across titles and body text | `FULLTEXT` | Finding articles containing `transaction isolation` |
| Points inside a region or intersecting geometries | `SPATIAL` | Finding places inside a polygon |
| Exact whole-key lookup in a `MEMORY` table | `HASH` | Looking up a token or cache key |

Before creating an index, answer these questions:

1. Does the query require exact equality, range scans, word search, or geometric relations?
2. Does the table's storage engine support that index type?
3. Does the query require sorting, additional filtering, or returning many columns outside the index?
4. Will the index significantly raise write costs and disk usage?
5. Do your MySQL version and parser/SRID settings satisfy the requirements?

## 8. Inspecting indexes and execution plans

`SHOW INDEX` lists existing indexes on a table, including names, types, and column order:

```sql
SHOW INDEX FROM orders;
SHOW INDEX FROM articles;
SHOW INDEX FROM places;
```

The `Index_type` field identifies index types such as `BTREE`, `HASH`, or `RTREE` depending on engine and index. `Seq_in_index` shows column position in composite indexes.

Use `EXPLAIN` to check whether the optimizer chooses a suitable index:

```sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 2001;
```

For `FULLTEXT`, inspect `MATCH ... AGAINST` statements and verify the query uses the `FULLTEXT` index under an appropriate plan. For `SPATIAL`, check MBR predicates and SRIDs so the optimizer can exploit the spatial index. For `HASH` on `MEMORY`, verify whole-key equality predicates; do not expect range scans or sorted results from `HASH`.

## 9. Common misconceptions

**Assuming every engine supports the same index types.** `MEMORY` has `HASH` and `BTREE`; InnoDB has B-tree, `FULLTEXT`, and `SPATIAL` but does not support declaring standard `HASH` indexes. Check the specific engine.

**Using FULLTEXT for numeric or date conditions.** `FULLTEXT` searches tokens inside text; B-tree fits date intervals, monetary amounts, and standard comparisons.

**Using HASH for range queries.** Hashes store no key order, so they support neither range scans nor key-ordered `ORDER BY`.

**Assuming SPATIAL returns exact geometric matches solely from MBR.** MBR is a bounding rectangle; exact geometric functions may also be required to filter out bounding-box-only intersections.

**Confusing Adaptive Hash Index with user-declared HASH indexes.** AHI is an internal InnoDB mechanism; you cannot create it via `CREATE INDEX ... USING HASH` on InnoDB.

**Choosing MEMORY purely for fast HASH lookups.** Weigh data loss on restart, engine constraints, and the fact that `MEMORY` tables do not replace transactional InnoDB tables.

## 10. Self-check

1. Which query condition types does B-tree support that `HASH` does not?
2. Why does `FULLTEXT` suit text content searches better than a standard B-tree?
3. What structure do `SPATIAL` indexes rely on, and what does MBR mean?
4. Which index types does the `MEMORY` engine support, and which is the default?
5. Why can you not declare a standard `HASH` index on an InnoDB table?
6. How does InnoDB's Adaptive Hash Index differ from `MEMORY`'s `HASH` index?
7. Why does an index being invisible or merely existing not guarantee the optimizer will use it?
