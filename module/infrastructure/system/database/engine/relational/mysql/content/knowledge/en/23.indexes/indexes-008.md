# Prefix Indexes for Long Strings and Distinctiveness Limits

A prefix index is a B-tree index that stores only a leading portion of a string value rather than the entire string. In MySQL, this is useful when a very long `VARCHAR` or `TEXT`/`BLOB` column holds URLs, paths, identifiers, or large strings that queries frequently filter by their leading portion. A prefix index shrinks index entry size, at the cost that multiple distinct values can share the same indexed prefix.

Therefore, the critical question is not just "how many characters should we take?" but also "how many values in real data share the same prefix?" Prefix length should be chosen based on data distribution, collation, query predicates, key length limits, and write costs. Too short a prefix yields low selectivity; too long a prefix bloats the index for very little marginal gain.

In the **DATABASE_MYSQL** module, prefix indexes connect data type design, B-trees, composite indexes, selectivity, and execution plans. This lesson explains how MySQL stores and uses prefix indexes, how to measure distinctiveness at various lengths, the limitations of `UNIQUE` prefix indexes, and a workflow for selecting a prefix length and verifying it with real data.

## 1. What is a prefix index?

With a regular index on a string column, the B-tree stores the full column key value in the index structure. With a prefix index, only the first N characters of the string (or N bytes for binary strings) are stored as the key part.

Example:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(1000) NOT NULL,
    body LONGTEXT NOT NULL,
    PRIMARY KEY (article_id),
    KEY idx_tenant_title (tenant_id, title(80))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Index `idx_tenant_title` contains:

- The full `tenant_id` value.
- The first 80 characters of `title`.
- The primary key `article_id`, stored by InnoDB in the secondary index to locate the row.

Prefix `title(80)` does not mean MySQL truncates `title` in the table. The complete `title` value remains stored in the clustered record. Only the secondary index entry retains the specified leading portion.

For `TEXT` and `BLOB` columns, a prefix length normally must be specified when creating an index because these types can store very long values:

```sql
CREATE TABLE external_assets (
    asset_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    resource_url TEXT NOT NULL,
    PRIMARY KEY (asset_id),
    KEY idx_resource_url_prefix (resource_url(128))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

When a full index on a long string is unsuitable due to key length limits or storage cost, a prefix index is an option. However, you must verify whether the leading part of the string is distinct enough to narrow down candidates.

## 2. Syntax for creating a prefix index

You can create a prefix index when declaring the table:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    path VARCHAR(2000) NOT NULL,
    PRIMARY KEY (document_id),
    KEY idx_path_prefix (path(120))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Or add the index after the table exists:

```sql
CREATE INDEX idx_path_prefix
    ON documents (path(120));
```

In a composite index, the prefix length is placed directly after the corresponding string column:

```sql
CREATE INDEX idx_tenant_path
    ON documents (tenant_id, path(120), created_at);
```

In the example above:

- `tenant_id` is indexed in full.
- `path` takes only the first 120 characters.
- `created_at` is indexed in full.

Prefix length applies only to prefixable string key parts. Do not specify a prefix length for numeric, date/time, or other non-prefixable types.

### 2.1. Is prefix length measured in characters or bytes?

The measurement depends on the string type:

| Data type | Prefix length unit |
|---|---|
| `CHAR`, `VARCHAR`, `TEXT`, and non-binary string types | Characters |
| `BINARY`, `VARBINARY`, `BLOB`, and binary string types | Bytes |

With a multi-byte charset like `utf8mb4`, a single character can occupy up to 4 bytes. Hence, a 100-character prefix does not mean the index occupies only 100 bytes. Actual key space depends on the stored characters, charset, collation, column type, accompanying primary key, and index structure.

For instance, `path(120)` on a `VARCHAR` using `utf8mb4` can require up to roughly 480 bytes for the character portion, before accounting for other key parts and internal overhead.

### 2.2. Key length limits

InnoDB limits the total key length of an index. The maximum depends on MySQL version, page size, row format, and engine configuration.

With a 16 KB InnoDB page size, a common limit in modern configurations is 3072 bytes per index key; 8 KB and 4 KB page sizes have proportionally lower limits. Some older configurations or row formats have a 767-byte limit. With a composite index, sum the bytes across all key parts, not just a single column's prefix.

Do not assume 3072 bytes for every server. Check actual row format, page size, charset, and version before creating indexes. A `"Specified key was too long"` error usually indicates total key length exceeds the active limit.

The number 191 frequently appears in `utf8mb4` examples because 191 × 4 = 764 bytes, staying under the historical 767-byte limit. That is a compatibility workaround for older setups, not an optimal default length for all modern prefix indexes.

## 3. How prefix indexes work with queries

Suppose an index stores only the first 12 characters of `resource_url`. When a query searches for a full URL:

```sql
SELECT asset_id, resource_url
FROM external_assets
WHERE resource_url =
      'https://cdn.example.com/images/2026/product/large-photo.png';
```

MySQL can use the prefix in the B-tree to find entries sharing that leading part. If multiple rows share the same prefix, the engine must inspect the full value on candidate rows to verify the `WHERE` condition.

This means a prefix index acts as a filter to narrow the candidate set. It does not collapse strings sharing a prefix into the same value in the table, nor does it lose trailing data.

### 3.1. Equality lookup

With an equality predicate:

```sql
SELECT asset_id
FROM external_assets
WHERE resource_url = 'https://cdn.example.com/a/very/long/resource-name.json';
```

A prefix index can help find candidates. If many URLs share the same first 128 characters, the server must inspect the remainder to tell them apart. The less distinctive the prefix, the more candidates must be checked.

### 3.2. LIKE with a fixed prefix

A B-tree can support `LIKE` conditions beginning with a constant prefix:

```sql
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE 'https://cdn.example.com/images/%';
```

The optimizer can turn the fixed prefix into a range on the index. A prefix index still stores only the leading part; if the pattern is longer than the prefix, the index can narrow down part of the set and the remaining pattern is checked against the full value.

### 3.3. LIKE with a leading wildcard

The following condition typically cannot use a B-tree prefix index to build an effective range:

```sql
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE '%/product/%';
```

Because the initial characters are not fixed, MySQL does not know where in B-tree order to start scanning. Consider full-text search, derived columns, or other data structures if substring searching is a frequent requirement.

A prefix index is not a `FULLTEXT` index. It does not tokenize words, match mid-string terms, or provide natural-language search.

### 3.4. Conditions wrapping a column in a function

Wrapping a column in a function can prevent a regular index from being used for direct range access:

```sql
-- May not be able to use prefix index range access
SELECT asset_id
FROM external_assets
WHERE LOWER(resource_url) = LOWER(?);

-- Direct comparison using the column's collation when appropriate
SELECT asset_id
FROM external_assets
WHERE resource_url = ?;
```

If business logic needs searches over normalized values, consider storing a separate normalized column or using an indexed generated column depending on MySQL version capabilities. Keep normalization rules consistent between writes and queries.

## 4. Prefix distinctiveness and selectivity

Selectivity describes how well a predicate or key part narrows the dataset. For a prefix index, examine how many distinct prefixes exist in the value set.

A simple estimation formula:

\[
\text{Prefix selectivity}
=
\frac{\text{Number of distinct prefixes}}
{\text{Number of non-NULL values}}
\]

The closer the ratio is to 1, the better the prefix distinguishes rows in the measured data. A low ratio means many rows share the same prefix.

Example table with 1,000,000 non-`NULL` URLs:

| Prefix length | Distinct prefixes (illustrative estimate) | Selectivity |
|---:|---:|---:|
| 8 | 20,000 | 0.02 |
| 16 | 250,000 | 0.25 |
| 32 | 820,000 | 0.82 |
| 64 | 970,000 | 0.97 |

With prefix 8, many URLs share the same start on average. Prefix 32 already distinguishes most values; increasing to 64 yields only a modest improvement while making index keys longer.

This is only an illustrative example. Real data may have a very different distribution, especially with URLs, emails, paths, or identifiers with repetitive prefixes.

### 4.1. Measuring distinct prefix counts

You can measure several candidate lengths on real data:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(resource_url) AS non_null_values,
    COUNT(DISTINCT LEFT(resource_url, 8)) AS distinct_8,
    COUNT(DISTINCT LEFT(resource_url, 16)) AS distinct_16,
    COUNT(DISTINCT LEFT(resource_url, 32)) AS distinct_32,
    COUNT(DISTINCT LEFT(resource_url, 64)) AS distinct_64
FROM external_assets;
```

Compute the ratio over non-`NULL` values:

```sql
SELECT
    COUNT(DISTINCT LEFT(resource_url, 16))
        / NULLIF(COUNT(resource_url), 0) AS selectivity_16,
    COUNT(DISTINCT LEFT(resource_url, 32))
        / NULLIF(COUNT(resource_url), 0) AS selectivity_32,
    COUNT(DISTINCT LEFT(resource_url, 64))
        / NULLIF(COUNT(resource_url), 0) AS selectivity_64
FROM external_assets;
```

`COUNT(DISTINCT ...)` ignores `NULL`; use `COUNT(resource_url)` as the denominator so the ratio is not artificially depressed by `NULL` rows. If the column is `NOT NULL`, `COUNT(*)` and `COUNT(column)` return the same count.

`LEFT()` here is used to profile data, not to prove the optimizer will use an index identically. On large tables, `COUNT(DISTINCT)` operations can read substantial data and require memory or temporary structures. Run them on a replica/staging copy or within a window suited to system load.

### 4.2. Checking heavily colliding prefix groups

An overall distinct ratio can mask a handful of heavily skewed prefix groups. Inspect groups with many rows sharing the same start:

```sql
SELECT
    LEFT(resource_url, 16) AS url_prefix,
    COUNT(*) AS rows_in_group
FROM external_assets
WHERE resource_url IS NOT NULL
GROUP BY LEFT(resource_url, 16)
ORDER BY rows_in_group DESC
LIMIT 20;
```

If a few prefixes account for a huge share of rows, queries frequently targeting those groups may still inspect many candidates. Evaluate actual query distribution, not just an overall average ratio.

### 4.3. Choosing a prefix by diminishing returns

As prefix length increases:

- Distinct prefixes generally increase or remain flat.
- Average rows sharing a prefix generally decrease.
- Key entries grow longer and the index grows larger.
- Cache holds fewer entries as the index bloats.
- `INSERT`/`UPDATE` may incur extra index maintenance work.

Look for the point where adding several more characters improves selectivity very little. You do not necessarily need a prefix with selectivity near 1 if query gains do not justify storage and write costs.

## 5. Collation and character set affect distinctiveness

A prefix index follows the comparison rules of the column's collation. With a case-insensitive collation, values differing only in letter case can be considered equal in comparisons. With an accent-insensitive collation, accented and unaccented characters can be treated as equivalent.

For example, if a column uses a case-insensitive collation, two strings with identical letters but different casing may group together under collation rules. Consequently, `COUNT(DISTINCT LEFT(column, n))` reflects distinctiveness under the active collation, not necessarily byte or binary comparison.

Check charset and collation:

```sql
SHOW FULL COLUMNS FROM external_assets;
```

Or inspect column metadata:

```sql
SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    CHARACTER_MAXIMUM_LENGTH,
    CHARACTER_OCTET_LENGTH
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_assets'
  AND COLUMN_NAME = 'resource_url';
```

If an application queries using a different collation or type conversion, the optimizer may have to convert values and index usability can change. Prefix design must be grounded in the application's actual comparison semantics.

Do not switch to a binary collation just to inflate distinct prefix counts if business logic requires case-insensitive or accent-insensitive comparisons. Changing collation alters comparison outcomes, uniqueness, and sort ordering of data.

## 6. Prefix indexes and UNIQUE constraints

You can create a `UNIQUE` prefix index:

```sql
CREATE UNIQUE INDEX uq_external_url_prefix
    ON external_assets (resource_url(64));
```

However, this constraint guarantees the first 64 characters do not collide across rows—not that the full `resource_url` is unique.

Example with two values:

- `https://cdn.example.com/files/customer/1001/report.pdf`
- `https://cdn.example.com/files/customer/1001/report-final.pdf`

If both share the same first 64 characters, the `UNIQUE` prefix index rejects the second row even though the two full URLs differ.

This distinction must be clear:

- `UNIQUE` on the full value guarantees no two full values collide under collation semantics.
- `UNIQUE` on a prefix guarantees no two values share the indexed prefix.
- A `UNIQUE` prefix can reject distinct values simply because their leading parts match.

Therefore, do not use a `UNIQUE` prefix index to enforce uniqueness of a long string if business rules allow values sharing a prefix. Use it only when business rules genuinely require that prefix itself to be unique.

If you need full-length uniqueness on a long string yet cannot create a full unique index due to key length limits, design an appropriate canonical identifier/key with a proven collision-handling mechanism. A plain digest hash has very low collision probability yet provides no absolute mathematical guarantee; if using a hash as a `UNIQUE` key, you must either accept that risk or implement collision handling appropriate for data requirements.

## 7. Prefix indexes inside composite indexes

A prefix index can be a key part of a composite index:

```sql
CREATE INDEX idx_tenant_path_time
    ON documents (
        tenant_id,
        path(120),
        created_at
    );
```

This index fits queries filtering on `tenant_id` and conditions on the start of `path`, potentially combined with `created_at` depending on predicate structure:

```sql
SELECT document_id, created_at
FROM documents
WHERE tenant_id = 7
  AND path LIKE '/customers/active/%'
  AND created_at >= '2026-01-01';
```

The principles remain the same as regular composite indexes:

1. The first key part governs the primary search region.
2. Equality prefixes usually precede range key parts.
3. A string prefix stores only the leading portion, so values sharing a prefix can produce multiple candidates.
4. Key parts after a range typically do not continue narrowing the range as cleanly as an equality prefix.
5. Inspect `key_len`, `rows`, `filtered`, and `Extra` via `EXPLAIN`.

Do not mechanically add prefix lengths to every string column in a composite index. Use prefixes only for genuinely long columns where distinctiveness is sufficient.

## 8. Limits of prefix indexes with covering, ORDER BY, and GROUP BY

### 8.1. Covering index

Because a prefix index does not store the full string value, a query needing to return the entire column generally must read the clustered record to get the rest.

Example:

```sql
SELECT resource_url
FROM external_assets
WHERE resource_url = 'https://cdn.example.com/a/very/long/resource-name.json';
```

Index `resource_url(128)` can help locate candidates, yet lacks the full `resource_url` to return complete output. InnoDB must access the row in the clustered index to fetch the full string.

If the query needs only columns present in the index, the index can still act as a covering index for that query. For example, selecting only `asset_id` (the primary key stored inside secondary indexes) may avoid extra clustered record reads, depending on access path and conditions.

### 8.2. ORDER BY

A prefix index sorts only by the stored leading portion. When multiple values share the same prefix, the index lacks enough information to establish full ordering across the entire string within that group. An `ORDER BY` query on the full column may need an extra sort step.

```sql
SELECT resource_url
FROM external_assets
ORDER BY resource_url;
```

Do not assume a prefix index eliminates filesort for full-string ordering. Inspect `Extra` in `EXPLAIN` and verify results on real data.

### 8.3. GROUP BY and DISTINCT

Two values sharing a prefix are not necessarily the same full string. Thus, a prefix index cannot treat all values sharing a prefix as a single group when a query requires full-string semantics.

```sql
SELECT resource_url, COUNT(*)
FROM external_assets
GROUP BY resource_url;
```

MySQL still must distinguish full values according to the column's collation. A prefix index may assist part of the access path, but cannot replace full comparison for grouping.

## 9. Choosing prefix length by workload

There is no single optimal prefix length for every column. Choose as follows:

1. **Identify primary queries.** Are they equality, `LIKE` prefix, range, `ORDER BY`, or `GROUP BY`?
2. **Profile the data.** Measure distinct prefixes across multiple candidate lengths.
3. **Check collisions.** Find prefixes with large row counts and check whether queries frequently hit them.
4. **Check collation.** Distinctiveness must be measured under real comparison semantics.
5. **Calculate key length in bytes.** Include all key parts in composite indexes plus the primary key carried in secondary indexes.
6. **Create the index in staging.** Confirm DDL succeeds and check storage size.
7. **Inspect the execution plan.** Check chosen index and `rows` estimates.
8. **Measure real queries.** Use `EXPLAIN ANALYZE` for eligible `SELECT`s and benchmark a representative workload.
9. **Measure write cost.** Monitor `INSERT`/`UPDATE`, index size, and buffer pool impact.
10. **Pick the balance point.** Choose the shortest prefix that meets performance and semantic requirements.

### 9.1. Example comparing prefixes 16, 32, and 64

Suppose a URL table has 5 million rows. You measure:

| Length | Distinct prefixes | Selectivity |
|---:|---:|---:|
| 16 | 1.2 million | 0.24 |
| 32 | 4.1 million | 0.82 |
| 64 | 4.8 million | 0.96 |

If equality queries usually search by full URL, prefix 32 may already eliminate most candidates. Prefix 64 improves selectivity only from 0.82 to 0.96 while doubling index entry length compared to 32. Benchmark to quantify real gains.

If queries mostly target URLs starting with one popular domain, overall selectivity may poorly represent the workload. Check popular prefix groups and their query frequency.

## 10. Inspecting the index after creation

Use `SHOW INDEX` to inspect indexes:

```sql
SHOW INDEX FROM external_assets;
```

The `Sub_part` column shows the key part's prefix length; `NULL` typically indicates the entire column is indexed. `Cardinality` estimates distinct values in the index and can change with statistics.

You can query metadata:

```sql
SELECT
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX,
    SUB_PART,
    COLLATION,
    CARDINALITY
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_assets'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

After creating an index or after major data changes, refresh statistics:

```sql
ANALYZE TABLE external_assets;
```

`ANALYZE TABLE` refreshes optimizer statistics; it does not choose a prefix length for you. After updating, re-check `EXPLAIN` because the plan may change.

### 10.1. Reading EXPLAIN for an equality query

```sql
EXPLAIN
SELECT asset_id
FROM external_assets
WHERE resource_url =
      'https://cdn.example.com/a/very/long/resource-name.json';
```

Check:

- Whether `key` is `idx_resource_url_prefix`.
- Whether `type` is an appropriate `ref` or `range`.
- Whether estimated `rows` is reasonable.
- Whether `Extra` shows remaining filtering is needed.
- Whether a full scan occurs despite the index existing.

An index existing does not guarantee the optimizer will always pick it. If the prefix has low selectivity or the table is small, a full scan may be estimated cheaper.

### 10.2. Comparing with a LIKE query

```sql
EXPLAIN
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE 'https://cdn.example.com/images/%';
```

Check whether the fixed prefix allows range access. Change the pattern to `'%images%'` to observe the difference:

```sql
EXPLAIN
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE '%images%';
```

Exact plans depend on version, collation, column type, and data. Do not conclude from syntax alone; read `key` and `rows`.

## 11. When a prefix index is not a good choice

### 11.1. Strings with identical leading parts

URLs often start with common schemes and domains; paths may begin with the same root directory. Short prefixes then suffer low selectivity.

Example values:

- `https://cdn.example.com/images/users/...`
- `https://cdn.example.com/images/products/...`
- `https://cdn.example.com/images/archive/...`

A prefix of 16 may be identical across almost all rows. Extending the length past the branching point can improve selectivity, though this must be measured on data.

If the fixed leading portion is too long, consider indexing a more meaningful attribute such as `tenant_id`, `domain`, `resource_type`, or a separate normalized column.

### 11.2. Substring search queries

If the workload mainly uses `LIKE '%word%'`, a B-tree prefix index cannot solve it. Consider `FULLTEXT`, an appropriate ngram parser, or a dedicated search engine depending on language and requirements.

### 11.3. Full-value uniqueness required

A `UNIQUE` prefix has different semantics from `UNIQUE` on the full value and can reject valid data. Design a business-accurate unique key rather than choosing a prefix simply because the DDL is easy.

### 11.4. Exact sorting or grouping on the entire string

A prefix index may not establish complete ordering when many values share a prefix. If `ORDER BY`/`GROUP BY` on the full string is a critical workload, benchmark against a full index or an alternative design.

## 12. Alternatives

| Need | Potentially suitable alternative |
|---|---|
| Long `VARCHAR` that still fits within key limits | Full-column index |
| Searching by email domain or URL host | Indexed generated column / normalized column |
| Searching tokens or words in content | `FULLTEXT` or search engine |
| Equality lookups on very long strings | Non-unique digest/hash index combined with exact value comparison |
| Stable resource identification | Surrogate key or short business code |
| Suffix searching | Reversed normalized string column or suitable search solution |

### 12.1. Generated columns for meaningful attributes

Example querying frequently by email domain:

```sql
CREATE TABLE contacts (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    email_domain VARCHAR(255)
        GENERATED ALWAYS AS (
            SUBSTRING_INDEX(email, '@', -1)
        ) STORED,
    PRIMARY KEY (contact_id),
    KEY idx_email_domain (email_domain)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Query:

```sql
SELECT contact_id, email
FROM contacts
WHERE email_domain = 'example.com';
```

This indexes the business attribute you actually search rather than an arbitrary prefix of the entire email. Validate emails and normalize domains per application rules; the generated column in this example merely illustrates simple domain extraction.

### 12.2. Digest/hash for candidate filtering

For very long strings needing equality lookups, you can store a digest such as SHA-256 in a `BINARY(32)` column and index the digest. Queries use the digest to narrow candidates, then compare the original value:

Example adding a digest column and index to the `external_assets` table created earlier:

```sql
ALTER TABLE external_assets
    ADD COLUMN url_sha256 BINARY(32) NULL,
    ADD KEY idx_external_assets_url_sha256 (url_sha256);

UPDATE external_assets
SET url_sha256 = UNHEX(SHA2(resource_url, 256))
WHERE url_sha256 IS NULL;
```

For large tables, backfill in controlled batches. Afterward, the application must update `url_sha256` synchronously whenever `resource_url` is inserted or updated; application logic or tested database mechanisms can keep the two values consistent.

```sql
SELECT asset_id, resource_url
FROM external_assets
WHERE url_sha256 = UNHEX(SHA2(?, 256))
  AND resource_url = ?;
```

Digests must be computed consistently on writes and properly indexed. Never rely on a digest alone as absolute proof two strings are identical; if exact correctness is required, always compare the original value after candidate filtering. Also avoid putting `UNIQUE` on the digest unless your system has an appropriate collision-handling policy.

## 13. Impact of prefix indexes on writes and storage

A prefix index is smaller than a full-column index when strings are long and the chosen prefix is substantially shorter. This can help:

- Reduce B-tree disk footprint.
- Increase entries fitting per page.
- Lower buffer pool pressure.
- Reduce part of write and index maintenance overhead.

However, a prefix index is still a secondary index that requires updates whenever the prefix value changes. `INSERT` adds entries; `UPDATE` altering the leading portion may replace entries; `DELETE` marks corresponding entries for subsequent purge cleanup.

If an `UPDATE` modifies only the part after the prefix and the prefix itself stays unchanged, the engine may avoid changing that key part, yet still must update the clustered record. Do not assume changes to the suffix are completely free; other columns in the index, clustered records, transactions, and page layout all matter.

A shorter prefix does not always make queries faster. If a prefix is overly common, the server must verify many clustered records and performance can be worse than with a longer index.

## 14. Checklist for choosing and operating prefix indexes

Before creating:

- Identify which equality, `LIKE` prefix, range, `ORDER BY`, or `GROUP BY` queries must be supported.
- Check data lengths, charset, and collation.
- Measure distinct prefix counts at multiple lengths.
- Inspect prefix groups with heavy duplicate counts.
- Review `UNIQUE` semantics if considering a unique prefix.
- Calculate total key length in bytes for the full composite index.
- Compare against a full-column index, generated column, or `FULLTEXT` where appropriate.

After creating:

- Verify `Sub_part` via `SHOW INDEX` or `information_schema.STATISTICS`.
- Run `ANALYZE TABLE` when statistics need refreshing.
- Read `EXPLAIN` and confirm the optimizer uses the index as intended.
- Benchmark queries with representative parameters and data.
- Monitor `rows examined`, latency, index size, and DML cost.
- Re-evaluate whenever string distribution shifts significantly.

## 15. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Picking a 10- or 20-character prefix by intuition | May collide across too many values | Measure distinct prefixes on actual data |
| Thinking a prefix index stores the full string | Overlooking required clustered record reads | Understand the index stores only the leading part |
| Using a `UNIQUE` prefix to enforce full-string uniqueness | Rejects two distinct values sharing a prefix | Choose unique keys matching business semantics |
| Thinking shorter prefixes are always better | Low selectivity, too many candidates | Balance size against distinctiveness |
| Thinking longer prefixes are always better | Index bloats while marginal gains may be tiny | Measure marginal benefit at each length |
| Using a prefix index for `LIKE '%abc%'` | B-trees cannot build ranges from leading wildcards | Use `FULLTEXT` or another search structure |
| Ignoring collation | Selectivity estimates miss real comparison semantics | Measure under the column's collation |
| Counting characters while forgetting bytes | Exceeds index key length limits | Account for charset, page size, row format, and composite keys |
| Assuming prefix indexes are always covering | Queries needing the full string must still read rows | Check which columns are actually stored in the index |
| Using a prefix index to replace full-text search | Cannot search arbitrary tokens or substrings | Pick tools matching the search type |

## 16. Key takeaways

- A prefix index stores a leading portion of a string in the B-tree; full data remains in the row.
- Prefix length is measured in characters for `CHAR`/`VARCHAR`/`TEXT` and bytes for `BINARY`/`VARBINARY`/`BLOB`.
- With `utf8mb4`, one character can take up to 4 bytes; calculate total key length for composite indexes.
- Prefix indexes shrink entry size yet can produce multiple candidates sharing the same prefix.
- Prefix selectivity can be estimated as distinct prefixes divided by non-`NULL` values.
- Measure multiple lengths and inspect common prefix groups before deciding.
- Collation affects comparison and distinctiveness; measure under real semantics.
- Equality lookups and fixed-prefix `LIKE` can use prefix indexes; leading wildcards generally cannot form a B-tree range.
- A `UNIQUE` prefix guarantees only prefix uniqueness, not full-string `UNIQUE` semantics.
- Prefix indexes do not automatically provide covering access or full sorting/grouping on original string values.
- Use `SHOW INDEX`, `information_schema.STATISTICS`, `EXPLAIN`, and benchmarks to verify indexes.
- Consider full indexes, generated columns, `FULLTEXT`, or digests/hashes when better suited to the workload.

Prefix indexes are effective when the leading portion of strings has enough distinctiveness for your actual workload. Measure your data, account for collation, and calculate key lengths before choosing; then verify with execution plans and benchmarks to balance query speed, index size, and write costs.

## References

- MySQL 8.0 Reference Manual — Column Indexes: https://dev.mysql.com/doc/refman/8.0/en/column-indexes.html
- MySQL 8.0 Reference Manual — InnoDB Limits: https://dev.mysql.com/doc/refman/8.0/en/innodb-limits.html
- MySQL 8.0 Reference Manual — CREATE INDEX Statement: https://dev.mysql.com/doc/refman/8.0/en/create-index.html
- MySQL 8.0 Reference Manual — Character Sets and Collations: https://dev.mysql.com/doc/refman/8.0/en/charset.html
