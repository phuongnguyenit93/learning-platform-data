# Secondary Indexes Store the Primary Key and the Impact of Wide Primary Keys

InnoDB organizes tables around a **clustered index**: data rows are stored in the leaves of the primary key's B-tree. Each **secondary index** is also a separate B-tree; in its leaves, InnoDB stores the secondary key columns together with the primary key columns needed to locate the row in the clustered index. Consequently, the primary key size affects every secondary index on the table.

If the primary key is an 8-byte `BIGINT`, the primary key portion carried in secondary indexes is significantly more compact than a long string key or a multi-column composite key. When a table has millions of records and multiple secondary indexes, a small per-entry difference multiplies into substantial storage consumption, lowers the number of entries per page, increases the number of pages that must be read, and increases index write and update costs.

In the `DATABASE_MYSQL` module, primary key design must balance stability, uniqueness, business meaning, ID distribution capability, and storage overhead. This lesson focuses on the relationship between the clustered index, secondary indexes, and primary key width in InnoDB.

## Objectives

After this lesson, you will be able to:

- Explain how InnoDB stores tables in a clustered index.
- Describe why secondary indexes must carry the primary key to locate the corresponding row.
- Identify which primary key columns are included in secondary indexes and when overlapping columns do not need to be stored twice.
- Estimate the impact of narrow primary keys, long string keys, and composite keys on total index size.
- Distinguish between `BIGINT`, text UUIDs, and binary `BINARY(16)` UUIDs in terms of storage size.
- Understand how wide primary keys affect fan-out, page count, the buffer pool, I/O, and DML cost.
- Choose a primary key that is stable, compact, and suited to the workload.
- Inspect index sizes and query plans using metadata, `EXPLAIN`, and empirical measurements.

## 1. The Clustered Index in InnoDB

InnoDB does not store table data as a standalone heap with the primary key acting merely as an auxiliary index. The table is organized by the clustered index, typically the primary key. The leaf nodes of the clustered index B-tree hold the row data.

Example:

```sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(160) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

In this table, rows are organized by the `customer_id` key. Looking up a row by primary key goes directly to the clustered index; when searching via a secondary index, InnoDB first finds the entry in the secondary B-tree and then uses the primary key value in that entry to look up the row in the clustered index if the query needs columns not present in the secondary index.

### 1.1. When No PRIMARY KEY Is Declared

InnoDB requires a clustered index to organize rows. If a table lacks an explicit primary key, InnoDB selects the first `UNIQUE` key in which all columns are `NOT NULL` as the clustered index, if one exists. If no qualifying key exists, InnoDB generates a hidden internal row ID (commonly called `GEN_CLUST_INDEX`) to serve as the clustered key.

You should not rely on the hidden row ID as a primary key design. Applications cannot use it as an explicitly declared business key, and letting InnoDB auto-generate a clustered key is no substitute for the benefits of a deliberate, stable primary key.

## 2. Secondary Indexes Carry the Primary Key

A secondary index is an additional B-tree created by `INDEX` or `UNIQUE KEY` outside the clustered key. A secondary index leaf entry contains:

- The columns declared in the secondary index.
- The primary key columns required to locate the row in the clustered index.

Example:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status_created (order_status, created_at)
) ENGINE=InnoDB;
```

Conceptually, the secondary index `idx_orders_customer` stores `customer_id` along with `order_id`; the index `idx_orders_status_created` stores `order_status`, `created_at`, along with `order_id`. `order_id` is the value InnoDB needs to locate the row in the clustered index.

### 2.1. When a Secondary Key Already Contains Part of the Primary Key

If the primary key is a composite key, InnoDB only needs to append the primary key components not already present in the secondary key; it does not need to store a column twice if it is already part of the secondary key.

```sql
CREATE TABLE order_line (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_line_product (product_id)
) ENGINE=InnoDB;
```

In `idx_order_line_product`, each entry needs `product_id` and the composite key `(order_id, line_no)` to locate the row. If a secondary index already declares a primary key component, InnoDB does not need to repeat that component a second time in the physical record.

Another example:

```sql
KEY idx_order_line_order_created (order_id, created_at)
```

This index already contains `order_id`, so the remaining primary key component needed to locate the row is only `line_no`. The logical structure of the entry can be thought of as `(order_id, created_at, line_no)`.

### 2.2. Why Can Secondary Indexes Serve Covering Queries?

Because secondary indexes carry the primary key columns, certain queries selecting primary key columns can be served directly from the secondary index without returning to the clustered index:

```sql
EXPLAIN
SELECT customer_id, order_id
FROM orders
WHERE customer_id = 100;
```

The index `idx_orders_customer` has `customer_id` and the accompanying `order_id` value. If the query only needs these two columns, the optimizer can choose a covering index scan (`Using index` in some EXPLAIN formats). This is a useful consequence of secondary indexes storing the primary key.

Not every query filtering by a secondary key is covering. If the query needs `total_amount`, InnoDB may have to look up the clustered index for each matching entry:

```sql
SELECT customer_id, order_id, total_amount
FROM orders
WHERE customer_id = 100;
```

## 3. Wide Primary Keys Inflate Every Secondary Index

Suppose a table has `N` rows and `K` secondary indexes. If the primary key portion carried in each entry is on average `D` bytes wider, the rough additional payload cost can be estimated at:

\[
N \times K \times D
\]

This is only a rough estimate of the added key payload, not an exact file size formula. It does not account for record headers, page directories, fill factors, page splits, secondary key columns, compression, variable lengths, or B-tree metadata. Even so, it illustrates how a wide primary key is multiplied by the number of rows and the number of secondary indexes.

For example, consider a table with 5 million rows and 6 secondary indexes. Replacing an 8-byte primary key with a 36-byte key adds roughly 28 bytes to each secondary index entry:

\[
5{,}000{,}000 \times 6 \times 28
= 840{,}000{,}000\text{ bytes}
\]

That is roughly 840 MB in decimal units for the extra key payload alone. Actual index sizes can differ significantly; measure on representative data.

### 3.1. Comparison Table of Common Key Sizes

| Primary key form | Typical key payload | Notes |
|---|---:|---|
| `INT UNSIGNED` | 4 bytes | Narrow; suitable if the value range suffices |
| `BIGINT UNSIGNED` | 8 bytes | Common for large numeric IDs |
| Text UUID `CHAR(36)` ASCII | 36 bytes | Human-readable, but longer than binary UUID |
| Binary UUID `BINARY(16)` | 16 bytes | More compact than text; requires consistent conversion conventions |
| Composite key `BIGINT + INT` | 12 bytes | Both components are carried if the secondary index does not already include them |

The figures above represent basic key data widths. Actual records also incur metadata and alignment/storage overhead; `CHAR`, `VARCHAR`, charsets, and record formats can alter the size.

## 4. Text UUID vs. BINARY(16)

A standard UUID has 36 display characters, including hyphens. When stored as `CHAR(36)` with the ASCII charset, the character payload is 36 bytes. When stored as `BINARY(16)`, the UUID is represented in 16 bytes.

```sql
CREATE TABLE event_text_pk (
    event_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_text_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE event_binary_pk (
    event_id BINARY(16) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_binary_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB;
```

The secondary index of the first table carries a `CHAR(36)` key; the second carries a `BINARY(16)` key. For the primary key portion attached to each secondary entry alone, the binary UUID is 20 bytes smaller per entry than the 36-byte text UUID, before accounting for other overhead.

### 4.1. Converting Text UUIDs to Binary

MySQL provides the `UUID_TO_BIN()` and `BIN_TO_UUID()` functions for UUID conversion:

```sql
INSERT INTO event_binary_pk (event_id, tenant_id, created_at, payload)
VALUES (
    UUID_TO_BIN(UUID()),
    10,
    NOW(6),
    JSON_OBJECT('source', 'api')
);

SELECT BIN_TO_UUID(event_id) AS event_id
FROM event_binary_pk;
```

For UUID v1, the `swap_flag = 1` argument in `UUID_TO_BIN(uuid, 1)` swaps certain time fields to improve byte-wise sequential ordering in the index. When reading back, the same convention `BIN_TO_UUID(binary_uuid, 1)` must be used. Do not apply this swap mechanically to UUID v4 or other UUID formats; choose the convention based on UUID type and ensure all writers and readers use it consistently.

### 4.2. Trade-Offs of Using BINARY(16)

Advantages:

- Smaller key than text UUIDs, making secondary indexes more compact.
- Fewer bytes to compare and store in the B-tree.
- Avoids storing hyphens or character representations of the UUID.

Points to manage:

- Harder to read directly in SQL clients and logs without converting via `BIN_TO_UUID()`.
- Requires consistent byte order, UUID version, and `swap_flag` across services.
- Random UUIDs like v4 still have scattered insertion order; BINARY(16) reduces width but does not automatically turn random IDs into sequential ones.
- Requires clear serialization rules across APIs, message queues, backup/restore, and operational tooling.

## 5. Composite Keys Can Also Become Wide Primary Keys

Composite keys can represent a row's natural identity, such as `(tenant_id, external_code)` or `(order_id, line_no)`. However, each key component is included in secondary indexes if that index does not already contain the corresponding component.

```sql
CREATE TABLE tenant_document (
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    document_body JSON NOT NULL,
    PRIMARY KEY (tenant_id, external_code),
    KEY idx_document_status_created (status, created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

The secondary index `idx_document_status_created` needs to carry `tenant_id` and `external_code` to locate the row. `external_code` has variable length and can occupy many bytes, especially with multi-byte charsets. If the table has many secondary indexes, the composite key cost can be large.

### 5.1. Natural Keys and Surrogate Keys

A natural key is derived from business data, such as a country code, external account number, or document code. A surrogate key is a dedicated technical ID such as `BIGINT AUTO_INCREMENT`.

A common design pattern uses a narrow surrogate key as the primary key and places a unique constraint on the natural key:

```sql
CREATE TABLE tenant_document_alt (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    document_body JSON NOT NULL,
    PRIMARY KEY (document_id),
    UNIQUE KEY uq_document_tenant_code (tenant_id, external_code),
    KEY idx_document_status_created (status, created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Now other secondary indexes carry the narrower `document_id`. However, the unique index on `(tenant_id, external_code)` still has to store its two natural key columns; a surrogate key does not eliminate the cost of the unique constraint. It only makes other secondary indexes that do not need the natural key more compact.

### 5.2. Do Not Switch to Surrogate Keys Mechanically

A natural composite primary key can make sense when:

- The business key is small and stable.
- Queries frequently filter by the full key or key prefix.
- Child relationships naturally reference the composite key and joins are clear.
- The table has few secondary indexes or the composite key is not wide.

A surrogate key can make sense when:

- The natural key is long or changes with business rules.
- Many child tables need to reference it via a short key.
- The table has many secondary indexes and the cost of repeating the composite key is significant.
- Internal identity needs to be decoupled from external identifiers.

Compare actual storage and join costs. There is no rule that every table must use `BIGINT AUTO_INCREMENT`.

## 6. How Do Wide Primary Keys Affect the B-Tree?

### 6.1. Fewer Entries per Page

A B-tree page has a finite size. When each entry is wider, fewer entries fit on a page. For the same number of rows, the index requires more pages, which can increase tree height or the number of page reads during queries.

### 6.2. The Buffer Pool Holds Fewer Entries

InnoDB uses the buffer pool to cache data and index pages. Wide secondary indexes occupy more pages, reducing the number of entries that fit within the same buffer pool capacity. Workloads querying via secondary indexes may need more page reads from storage.

### 6.3. Higher Index Write and Update Costs

When inserting a new row, InnoDB must add entries to the clustered index and each secondary index. Because the primary key is carried in secondary entries, a wide key increases the amount of data written, can make page splits costlier, and increases index maintenance overhead.

If the primary key changes, the new primary key value must be reflected in the secondary indexes because they use the primary key to locate rows. This is an important reason to choose an immutable primary key.

### 6.4. Impact on Backup, Restore, and Replication Workloads

Large indexes increase the amount of data to back up and restore, and can increase I/O during dumps, imports, or index rebuilds. Index data also increases the number of pages read during scans. Specific impact depends on storage, compression, backup methods, and workload; backup duration cannot be deduced from key width alone.

### 6.5. Foreign Keys in Child Tables Are Also Affected

If a child table references a wide primary key, the foreign key columns in the child table must also use a compatible data type and store that wide value. Consequently, indexes supporting the foreign key also contain the wide referenced key; if the child table has other secondary indexes, the child table's own primary key continues to be carried in those indexes as well.

```sql
CREATE TABLE parent_text (
    parent_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    label VARCHAR(80) NOT NULL,
    PRIMARY KEY (parent_id)
) ENGINE=InnoDB;

CREATE TABLE child_of_text_parent (
    child_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    parent_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (child_id),
    KEY idx_child_parent (parent_id),
    KEY idx_child_status (status),
    CONSTRAINT fk_child_text_parent
        FOREIGN KEY (parent_id) REFERENCES parent_text (parent_id)
) ENGINE=InnoDB;
```

In the child table, `idx_child_parent` stores `parent_id` along with `child_id` to locate the child row. `idx_child_status` stores `status` along with `child_id`. If `parent_id` is replaced with `BINARY(16)` in both tables, the foreign key index will carry shorter reference values. When a parent table has many child tables or a child table has many rows, the cost of a wide referenced key can ripple across the entire data model.

Do not change a foreign key's type on only one side; type, size, and attributes must be compatible with the referenced key. Changing a PK in a running system can entail migrating many child tables, indexes, applications, and integrated data.

## 7. Sequential Primary Keys vs. Random Primary Keys

Width is not the only factor. The ordering of key values affects where inserts land in the clustered index B-tree.

### 7.1. AUTO_INCREMENT

`BIGINT AUTO_INCREMENT` typically generates monotonically increasing values. New inserts generally go toward the end of the clustered index, providing good locality and reducing scattered inserts. Under very high concurrent write workloads, the trailing end of the tree can become a point of latch/page contention; measure empirically rather than assuming every table hits this bottleneck.

### 7.2. Random UUIDs

UUID v4 is highly random. When used as a clustered primary key, inserts can scatter across many regions of the B-tree, causing page splits, fragmentation, and poorer cache locality compared to monotonically increasing keys. Using `BINARY(16)` makes the key narrower than text, yet retains the random insertion behavior of UUID v4.

### 7.3. Time-Ordered UUIDs

UUIDs with a timestamp field or time-ordered distributed IDs can improve locality compared to purely random UUIDs. However, you must choose an appropriate version/format, understand byte ordering, and weigh potential timestamp leakage or ID generation patterns. Do not assume every UUID has good insert ordering.

## 8. Choosing a Primary Key by Workload

A good primary key typically has these characteristics:

- Unique and `NOT NULL`.
- Compact to reduce payload in secondary indexes.
- Stable, never changing during the row's lifecycle.
- Clear ID generation rules, independent of easily edited data.
- Aligned with access patterns and write distribution.
- Efficiently referenceable by child tables.

Decision examples:

| Context | Option to consider | Reason |
|---|---|---|
| Internal transaction table with many secondary indexes | `BIGINT` surrogate | Narrow, easy to reference, and typically monotonically increasing |
| Child relationship table with a small, stable natural key | Composite key | Avoids adding an unnecessary ID and preserves relational semantics |
| System needing distributed IDs without a central sequence | UUID, preferring binary form if suitable | Generates IDs independently across nodes, reduces width vs. text |
| High-write event table needing locality | Sequential ID or time-ordered ID | Supports inserts near the trailing region of the index |
| Table with a long natural key and many secondary indexes | Surrogate PK + unique natural key | Avoids repeating the long natural key in every secondary index |

This is a starting point for evaluation, not a universal formula. Distributed requirements, security, imports, business ordering, and system compatibility must all be factored in.

## 9. Inspecting Secondary Indexes and Actual Storage Size

### 9.1. Viewing Index Definitions

```sql
SHOW CREATE TABLE orders\G

SHOW INDEX FROM orders;
```

`SHOW INDEX` displays declared index columns, column order, and index attributes. It does not explicitly show the full primary key portion implicitly carried by InnoDB inside secondary indexes.

### 9.2. Viewing Table and Index Sizes at the Schema Level

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('event_text_pk', 'event_binary_pk')
ORDER BY TABLE_NAME;
```

`DATA_LENGTH` and `INDEX_LENGTH` are storage-engine-level size statistics and may be point-in-time estimates; `TABLE_ROWS` for InnoDB is generally not an exact count. Do not use a single metadata query as a final benchmark.

### 9.3. Comparing with Representative Data

To measure the impact of the primary key, create two tables with the same business columns, the same row count, and the same secondary indexes, differing only in primary key type. Load the same data and value distribution; then:

1. Run `ANALYZE TABLE` to update statistics when appropriate.
2. Compare `DATA_LENGTH` and `INDEX_LENGTH` after the data has settled.
3. Inspect page/index page counts using statistics tools appropriate for your version and privileges.
4. Run the same read, write, and update workload.
5. Measure latency, I/O, buffer pool hit rate, and backup size if those are operational criteria.

Do not compare two tables with different row counts, data lengths, index counts, or fill patterns and attribute the entire difference to the primary key.

## 10. Covering Indexes and the Implicit Primary Key

Because a secondary index contains the primary key, a query selecting primary key columns alongside secondary key columns can be covered by the index:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);

EXPLAIN
SELECT customer_id, created_at, order_id
FROM orders
WHERE customer_id = 100
ORDER BY created_at;
```

InnoDB can use the secondary key columns and accompanying primary key to return results without reading the clustered record. This is a useful capability, though it does not mean index design can be neglected. If a query needs another column not in the secondary record, it still requires a clustered index lookup.

When designing covering indexes, account for the carried primary key. If the primary key is wide, a secondary index created with only a few columns may turn out larger than expected.

## 11. Index Key Length Limits

A primary key is itself an index, and primary key columns are placed into secondary indexes. An overly wide composite key can hit InnoDB's key length limit, especially when using `VARCHAR` with multi-byte charsets.

On common InnoDB configurations with a 16 KB page size and `DYNAMIC` or `COMPRESSED` row format, the key length limit is typically 3072 bytes. The limit decreases for smaller page sizes and can be lower for older row formats. Specific versions, row formats, and configurations must be verified before deployment.

For example, `VARCHAR(255)` with `utf8mb4` can require up to 4 bytes per character for character data. You cannot look only at character count to conclude an index key fits the byte limit. For multi-string composite primary keys, account for all components and appropriate overhead.

You should not pick a long business string as the primary key only to discover later that secondary indexes cannot be created. If a long unique natural key is needed, consider an appropriate unique constraint, a narrow surrogate key, or an alternative lookup model; do not replace a unique constraint with a hash while ignoring collision checks.

## 12. Common Design Mistakes

| Mistake | Consequence | Mitigation |
|---|---|---|
| Using `CHAR(36)` text UUID as PK in a table with many secondary indexes | Every secondary entry carries a long text key | Consider `BINARY(16)` or a surrogate key if suitable |
| Using a composite key of many long columns as PK | Inflates every secondary index that lacks the full key | Evaluate a surrogate key and unique natural key |
| Using a mutable PK column | Updating the clustered key forces secondary index updates | Choose an immutable key |
| Using UUID v4 and expecting sequential inserts | B-tree inserts remain scattered despite binary UUID storage | Choose an ordered ID if the workload needs locality |
| Creating too many secondary indexes | Increases storage usage and cost of every INSERT/UPDATE/DELETE | Keep only indexes serving actual workloads |
| Assuming SHOW INDEX displays the entire physical entry | Overlooks the implicitly carried PK | Understand InnoDB rules and measure actual indexes |
| Using `SUM(DISTINCT ...)` or hashes to mask key issues | Can drop valid data or suffer collisions | Keep unique keys with proper semantics and check collisions |
| Measuring size on tiny test tables | Overhead and page distribution are unrepresentative of production | Benchmark with representative data and workloads |

## 13. Checklist for Evaluating a Primary Key

When designing a new table or considering changing a primary key, answer each question in turn:

1. Is the key unique, `NOT NULL`, and stable throughout the row's lifecycle?
2. How many bytes does the key actually occupy? For strings, consider charset and max length.
3. How many secondary indexes does the table have? Which PK components will each index carry?
4. Do any secondary indexes already include part of a composite key so it does not need to be repeated?
5. How many child tables reference the PK and how wide are those foreign keys?
6. Does the key generation order support clustered index locality or cause scattered inserts?
7. Does the system need distributed ID generation without depending on a central node?
8. Could the natural key change or grow longer as business rules evolve?
9. Is the total length within the key length limit of the deployment configuration?
10. What differences appear in benchmarks with representative row counts, index counts, and workloads?

## 14. Practice Lab

Carry this out in a dedicated lab database with two tables `event_text_pk` and `event_binary_pk`:

1. Create tables with primary keys `BIGINT`, `CHAR(36)` ASCII, and `BINARY(16)`; keep the business columns identical.
2. Create the same secondary indexes on all three tables.
3. Load a sufficiently large dataset with the same value distribution; do not use just a few dozen rows.
4. Use `SHOW CREATE TABLE` and `SHOW INDEX` to inspect declared indexes.
5. Explain which primary key columns are carried in the secondary indexes.
6. Compare `DATA_LENGTH` and `INDEX_LENGTH` via `INFORMATION_SCHEMA.TABLES` after the data has settled.
7. Run a query filtering by a secondary key and selecting only the primary key; verify whether the optimizer can use a covering index.
8. Add a column not in the secondary index to the SELECT list; observe the need for a clustered index lookup.
9. Create a composite key `(tenant_id, external_code)` and another secondary index; describe the carried key payload.
10. Create a version using a surrogate `BIGINT` plus a unique natural key; compare secondary index sizes and join costs.
11. Load random UUID v4 values into `CHAR(36)` and `BINARY(16)`; compare storage sizes and insert characteristics under the same workload.
12. Test time-ordered UUIDs using a consistent conversion convention; compare locality and write throughput in the lab.
13. Check key length limits for your active page size and row format; test designing a wide composite key in the test environment.
14. Write a PK recommendation for an event table with 5 secondary indexes and tens of millions of records, including an estimate of added payload.

You have completed this lesson when you can explain why a primary key is repeated across multiple secondary indexes, estimate the cost of a wide key, and defend a PK choice based on workload rather than ID generation convenience alone.

## 15. Key Principles to Remember

- InnoDB stores row data in the clustered index; typically the primary key.
- Secondary indexes are separate B-trees whose leaf entries carry the secondary key columns plus the primary key components needed to locate the row.
- PK components already present in a secondary key do not need to be stored twice in the entry.
- A wide primary key inflates every secondary index that does not already contain the full key; costs scale with row count and index count.
- Composite keys can make secondary indexes large if they comprise many columns or long string columns.
- `BIGINT` is typically narrower than text UUIDs; `BINARY(16)` stores UUIDs more compactly than the `CHAR(36)` representation.
- `BINARY(16)` reduces UUID width but does not inherently give random UUIDs good locality.
- A primary key should be unique, `NOT NULL`, stable, and compact when the workload permits.
- A surrogate key does not eliminate the cost of a unique natural key; it lets other secondary indexes carry a narrower key.
- Monotonically increasing primary keys can help insert locality; measure actual bottlenecks under high concurrent write workloads.
- A secondary index can be covering when a query only needs columns already present in the secondary entry, including the PK.
- Verify key length limits against page size, row format, charset, and version.
- Use metadata as a reference and benchmark with representative data to decide.
