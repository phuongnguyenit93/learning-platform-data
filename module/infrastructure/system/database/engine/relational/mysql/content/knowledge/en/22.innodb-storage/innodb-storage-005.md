# Page Splits, Page Merges, and Fragmentation During Inserts and Updates

## Lesson Objectives

After this lesson, you will be able to:

- Describe how InnoDB organizes data and indexes inside B-tree pages.
- Explain why an INSERT or UPDATE can cause a page to split.
- Distinguish between page split, page merge, page reorganization, and fragmentation.
- Predict how sequential keys, random keys, and secondary indexes affect page distribution.
- Explain MERGE_THRESHOLD and innodb_fill_factor, as well as the scope of each setting.
- Monitor split and merge counts using INNODB_METRICS.
- Recognize when to rebuild or run OPTIMIZE TABLE to reclaim space.
- Design keys and write patterns to reduce B-tree maintenance overhead.

InnoDB stores data and indexes in pages belonging to B-tree structures. When adding a record to a nearly full page, InnoDB may have to split the page into smaller pages and update the parent node. When deleting data or shortening a key, a page can become sparse; InnoDB may attempt to merge it with an adjacent page. These changes preserve index structure, while also creating additional write work, page allocation, and space management overhead.

Page splits and page merges are normal B-tree operations. They become a performance problem when they occur frequently, leave many sparse pages, or result in a physical page layout unfavorable for access. Accurate diagnosis requires understanding how INSERT and UPDATE affect the clustered index, secondary indexes, and tablespace space.

## 1. InnoDB Pages and B-Trees

### 1.1. The Page as the Basic Storage Unit

InnoDB divides table data and indexes into pages. The default page size is 16 KB; the actual value depends on innodb_page_size chosen when initializing the instance. An instance's page size cannot be changed after the instance has been initialized.

A B-tree index consists of multiple levels:

- The root page is the starting point for searches.
- Non-leaf pages contain separator keys and pointers to lower-level pages.
- Leaf pages contain index records. For a clustered index, leaf pages contain the row data; for a secondary index, leaf pages contain the secondary key alongside the row's primary key.

Leaf pages are ordered according to logical key order. The B-tree keeps the path from the root to every leaf balanced in depth, ensuring key lookups do not have to scan the entire table.

### 1.2. Clustered Index and Secondary Indexes

Each InnoDB table has one clustered index. Typically, the PRIMARY KEY is the clustered index, and rows are organized by the primary key.

If no PRIMARY KEY is declared, InnoDB selects a UNIQUE index whose columns are all NOT NULL as the clustered index. If no qualifying index exists, InnoDB creates a hidden clustered index on a row ID.

Secondary indexes are all remaining indexes. Each secondary index record contains the index's key columns and the corresponding primary key value so InnoDB can locate the row in the clustered index.

Example:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_product (product_id)
) ENGINE = InnoDB;
~~~

In this example:

- PRIMARY KEY (order_id, line_no) determines the order of the clustered index.
- idx_product is a secondary index.
- Records in idx_product store product_id along with the primary key columns order_id and line_no.

Because the primary key appears in secondary indexes, a long PRIMARY KEY causes every secondary index to consume more space. More pages mean the buffer pool must manage more pages, which can increase I/O as well as index maintenance work.

### 1.3. A Table Has Multiple Independent Index Trees

Each B-tree index has its own set of pages and its own key order. An INSERT into a table may need to update the clustered index and all secondary indexes.

For example, suppose a new row has an increasing id, while created_at and customer_id are distributed randomly:

- The clustered index can append the record in the highest-key region.
- The secondary index on created_at must locate the position by timestamp.
- The secondary index on customer_id must locate the position by customer_id.

Therefore, a sequential primary key does not eliminate page splits in secondary indexes whose keys are inserted in random order.

## 2. What Is a Page Split?

A page split occurs when a record needs to be inserted into a B-tree page, but the page lacks sufficient space. InnoDB must redistribute records across multiple pages to make room for the new record while maintaining index order.

At a high level, the process may include:

1. Finding the leaf page containing the target key position for insertion.
2. Attempting to insert the record and reorganizing the page if enough space remains.
3. If the page cannot fit the record, allocating another page and dividing records between the pages.
4. Updating page links and the parent node so the tree continues to search correctly.
5. If the parent node is also full, splitting may propagate upward to higher levels.
6. If the root needs to split, InnoDB can create a new root, increasing the tree height.

Not every INSERT causes a split. If the page has room, InnoDB simply inserts the record and updates the associated structures. A page split is a structural operation performed when the current page lacks space.

### Page Reorganization Differs from Page Split

Before allocating a new page, InnoDB can reorganize records inside the page to coalesce fragmented free regions into contiguous space. Page reorganization still uses the existing page; a page split requires adding a page and updating the tree structure. Thus, a successful reorganization is not a split.

### 2.1. Illustrating a Leaf Page Split

Suppose a leaf page currently holds keys in order:

~~~text
Page A
[ 10 | 20 | 30 | 40 | 50 | 60 ]
~~~

When key 35 needs to be inserted and the page no longer has enough room, InnoDB can split the data into two pages:

~~~text
Before:
Page A
[ 10 | 20 | 30 | 40 | 50 | 60 ]

After:
Page A                  Page B
[ 10 | 20 | 30 ]        [ 35 | 40 | 50 | 60 ]

The parent node is updated to point to both Page A and Page B.
~~~

This is an illustrative model for understanding splitting and parent node updates. How InnoDB chooses the split point and distributes free space depends on insertion position, record sizes, and page state; you should not assume every split divides strictly in half.

### 2.2. Splits Can Propagate Up Multiple Levels

If a leaf page splits, the parent node must receive information about the new page. If the parent node lacks space, it can split as well. The process can continue up to the root.

When the root splits, the tree can gain an additional level. Greater tree height is not necessarily a problem; B-trees are designed to maintain efficient lookups as data grows. What matters is the overhead incurred when splits happen continuously and the degree of page fragmentation.

### 2.3. Cost of a Page Split

A page split may require:

- Allocating a page and updating page management metadata.
- Moving or rearranging a subset of index records.
- Writing changes across multiple pages in the buffer pool.
- Updating the parent node and page links.
- Generating additional redo activity to ensure recoverability.
- Holding internal latches while modifying the B-tree structure.

A split does not mean the entire table is locked. However, it is extra work on the write path and can increase latency, I/O, and internal contention when multiple transactions update nearby index regions concurrently.

## 3. How INSERT Order Affects Page Splits

### 3.1. Sequential Key Inserts

When keys increase monotonically, new records are typically inserted near the end of the index. For a clustered index with strictly increasing or decreasing order, InnoDB can keep pages nearly full while leaving a portion of space for subsequent inserts or updates.

The MySQL 8.4 documentation notes that InnoDB tries to leave 1/16 of a page free in the clustered index for future growth. For sequentially inserted data, pages typically reach about 15/16 capacity.

AUTO_INCREMENT keys usually produce an increasing insert pattern:

~~~sql
CREATE TABLE event_update_demo (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_time DATETIME NOT NULL,
    event_type SMALLINT UNSIGNED NOT NULL,
    payload VARCHAR(160) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;

INSERT INTO event_update_demo (
    event_id,
    event_time,
    event_type,
    payload
)
VALUES (
    1001,
    '2026-02-15 10:10:00',
    1,
    'initial event'
);
~~~

New INSERTs into the clustered index typically go toward the highest key. This is sequential and generally leverages page locality better than random key inserts.

In workloads with very high transaction concurrency, the trailing region of the index can become a hotspot because multiple writer threads access neighboring pages simultaneously. Therefore, sequential keys reduce random inserts, but actual contention still needs to be measured.

### 3.2. Random Key Inserts

If the primary key is distributed randomly, each INSERT can land on a different leaf page depending on the key value. Pages across many regions of the tree simultaneously receive new records.

For a clustered index, the MySQL documentation notes that pages can reach roughly 1/2 to 15/16 full when records are inserted in random order. This is an observed range for how InnoDB fills pages, not a guarantee that every page split divides pages in half.

Consequences can include:

- Page splits occurring across many different regions of the tree.
- Pages retaining more empty space after splits.
- Logically adjacent pages not necessarily residing close together on storage media.
- The buffer pool having to hold many index regions being written to.
- Range scans in index order potentially needing to read more pages.

Example of an externally assigned primary key:

~~~sql
CREATE TABLE event_random_demo (
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    event_type SMALLINT UNSIGNED NOT NULL,
    payload VARCHAR(160) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;
~~~

If event_id comes from a random number generator or an unordered ID, INSERTs can distribute across many leaf pages. This is a common reason clustered indexes exhibit different page occupancy and fragmentation levels compared to sequential insert patterns.

Not all random keys are wrong. Some systems require unpredictable IDs or IDs generated independently across multiple nodes. When choosing a key, balance business requirements, distribution, key length, time-sortability, and index write costs.

### 3.3. Secondary Indexes Have Their Own Order

Suppose event_id increases monotonically, but event_time does not:

~~~sql
INSERT INTO event_update_demo (event_time, event_type, payload)
VALUES
    ('2026-02-15 10:10:00', 1, 'event A'),
    ('2026-01-04 08:30:00', 2, 'event B'),
    ('2026-02-02 17:45:00', 1, 'event C'),
    ('2026-01-21 12:00:00', 3, 'event D');
~~~

The clustered index receives new event_id values in AUTO_INCREMENT order. However, idx_event_time must insert timestamps into their corresponding positions within the secondary index B-tree. If timestamps are randomly distributed, the secondary index can still split.

Therefore, when analyzing page splits, you must inspect each index rather than looking only at PRIMARY KEY.

## 4. How Can UPDATE Cause a Split or Merge?

UPDATE can change row size, storage location, or index keys. The impact depends on which column is updated and how much free space remains in the page.

### 4.1. Updating a Non-Indexed Column

If a non-indexed column is updated and the row still fits in the current page, InnoDB can usually rewrite the row on the same page.

Example:

~~~sql
UPDATE event_update_demo
SET payload = 'updated payload'
WHERE event_id = 1001;
~~~

If payload grows in length yet the page still has enough room, the row can remain stored on the current page. If there is not enough room, InnoDB must handle record reorganization and may need another page or related storage structure adjustments.

You should not conclude that every UPDATE lengthening a VARCHAR causes a page split. The outcome depends on actual length, row format, how long columns are stored, and remaining free space.

### 4.2. Updating a Secondary Index Column

If an UPDATE changes the value of a column belonging to a secondary index, InnoDB must remove the old index entry and add a new index entry under the new key.

Example:

~~~sql
UPDATE event_update_demo
SET event_time = '2026-03-01 09:00:00'
WHERE event_id = 1001;
~~~

event_time is a column of idx_event_time. Updating it can remove the record from its old key position and insert it at the new position. The new position may reside on a different page and can trigger a page split if the target page lacks sufficient room.

Updating an indexed column can therefore be more expensive than updating a non-indexed column.

### 4.3. Updates That Lengthen or Shorten Keys

Suppose an index is created on code:

~~~sql
CREATE TABLE product_code (
    product_id BIGINT UNSIGNED NOT NULL,
    code VARCHAR(120) NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_product_code (code)
) ENGINE = InnoDB;
~~~

Updating code from a short string to a longer string can enlarge the secondary index record. If the target page lacks enough room, InnoDB may have to split the page.

Conversely, when an index key becomes shorter, the record can occupy less space. If the page becomes sparse and its fill ratio drops below MERGE_THRESHOLD, InnoDB may attempt to merge it with an adjacent page.

### 4.4. Updating the Primary Key

The primary key determines clustered index order and is stored inside secondary indexes. Changing the primary key can force the row to move to a new position in the clustered index and update the primary key value across secondary indexes.

Therefore, the primary key should remain stable throughout the record's lifecycle. If an application frequently mutates the primary key, the cost of updating multiple index trees can be substantial.

## 5. What Is a Page Merge?

A page merge is the operation of combining a sparsely populated index page with an adjacent page when their combined data can fit within a single page.

InnoDB may attempt a merge when:

- A record is deleted and the page becomes sparse.
- An UPDATE shortens records and lowers page utilization.
- The page's fill percentage falls below MERGE_THRESHOLD.

If two pages can hold their combined records after merging, InnoDB updates the parent node and frees one page for reuse in the tablespace.

Page merges help reclaim empty pages within the B-tree, though they do not necessarily shrink the .ibd file immediately. Freed pages can be reused for other data in the tablespace.

### 5.1. Illustrating a Page Merge

Suppose two adjacent pages currently hold:

~~~text
Page A                  Page B
[ 10 | 20 ]             [ 30 | 40 ]

After merge:
Page A
[ 10 | 20 | 30 | 40 ]

Page B is freed for InnoDB to reuse.
~~~

This is a conceptual model. Actual merging depends on total record size, page space, and the merge threshold.

### 5.2. Default MERGE_THRESHOLD Is 50

InnoDB uses MERGE_THRESHOLD to decide when to attempt merging pages. The default value is 50, meaning that when a page's fill percentage falls below 50% after a deletion or record-shortening operation, InnoDB attempts to merge it with an adjacent page.

Valid values range from 1 to 50. MERGE_THRESHOLD can be configured at the table level or per index:

- Index-level settings take precedence over table-level settings.
- If not declared, the default value is 50.
- Lowering the threshold causes InnoDB to wait until a page is sparser before attempting a merge.
- Setting the threshold too low can leave many underfilled pages and result in larger data files.

### 5.3. Why Does a Merge Lead to Another Split?

Suppose two pages are each nearly 50% full. When one page drops below the 50% threshold, InnoDB attempts to merge it with the neighboring page. If the newly merged page is nearly full, a subsequent INSERT can cause it to split again.

Repeated merge-split cycles can increase index maintenance work without providing steady-state benefit.

In workloads with frequent interleaved INSERTs and DELETEs in the same key range, you can try lowering MERGE_THRESHOLD. Any adjustment should be guided by split/merge counts, space utilization, and observed latency.

## 6. Configuring MERGE_THRESHOLD

### 6.1. Setting the Threshold for a Table

MERGE_THRESHOLD can be configured in the table COMMENT:

~~~sql
CREATE TABLE product_code_tuned (
    product_id BIGINT UNSIGNED NOT NULL,
    code VARCHAR(120) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_code (code)
) ENGINE = InnoDB
COMMENT = 'MERGE_THRESHOLD=45';
~~~

For an existing table:

~~~sql
ALTER TABLE product_code_tuned
COMMENT = 'MERGE_THRESHOLD=45';
~~~

### 6.2. Setting the Threshold for an Index

It can be configured per index using the index COMMENT:

~~~sql
CREATE TABLE event_by_customer (
    event_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_customer_time (customer_id, event_time)
        COMMENT 'MERGE_THRESHOLD=40'
) ENGINE = InnoDB;
~~~

If the index threshold is 40, that dedicated setting takes priority over the table-level threshold.

Checking the configuration:

~~~sql
SHOW INDEX FROM event_by_customer;
SHOW CREATE TABLE event_by_customer;
~~~

SHOW INDEX displays index comments in the Index_comment column. SHOW CREATE TABLE lets you verify the table definition and table comment.

### 6.3. Choosing a Threshold by Workload

| Workload pattern | Evaluation direction |
|---|---|
| Sequential INSERTs, few DELETEs | Usually no threshold customization needed |
| Random INSERTs interleaved with DELETEs | Monitor merge-split activity before adjusting |
| UPDATEs frequently shortening index keys | Inspect merge counts and page occupancy |
| Frequent merges followed by splits | Test lowering the threshold in a test environment |
| Need to minimize empty pages as much as possible | Do not lower the threshold too far if it wastes space |

There is no single optimal MERGE_THRESHOLD for every table. A lower threshold can reduce merge-split cycles while keeping more sparse pages. A higher threshold can reclaim pages sooner, though it more easily creates merge-then-split cycles.

## 7. innodb_fill_factor and Space Reserved for Growth

innodb_fill_factor controls how full pages are filled when InnoDB creates or rebuilds a B-tree index using a sorted index build.

The default value is 100. A value of 80 acts as a hint to fill roughly 80% of each page and reserve the rest for future growth. This is a hint rather than a strict limit; actual fill ratios may vary.

Key points to remember:

- innodb_fill_factor has GLOBAL scope and can be changed dynamically.
- Applies to both leaf pages and non-leaf pages of the B-tree.
- Does not apply to external pages storing TEXT or BLOB data.
- A value of 100 still leaves 1/16 of clustered index pages free per InnoDB's rules.
- This setting affects sorted index builds, not a direct switch controlling every normal INSERT.

Checking:

~~~sql
SHOW VARIABLES LIKE 'innodb_fill_factor';
~~~

Example reading the setting:

~~~sql
SELECT
    @@GLOBAL.innodb_fill_factor AS fill_factor;
~~~

If set to 80 before rebuilding indexes, InnoDB uses that value as a hint for sorted index builds:

~~~sql
SET @original_fill_factor = @@GLOBAL.innodb_fill_factor;

SET GLOBAL innodb_fill_factor = 80;

ALTER TABLE event_update_demo
FORCE;

SET GLOBAL innodb_fill_factor = @original_fill_factor;
~~~

This is an illustrative example for a test environment. ALTER TABLE ... FORCE rebuilds the table and indexes, which can consume I/O, time, and temporary space. The statements save and restore the original GLOBAL value in the current session; if the DDL fails midway, inspect and restore the setting manually. Evaluate impact on other concurrent DDLs and run only within an appropriate maintenance window.

Do not set a low fill factor simply because a few page splits were observed. Free page space absorbs growth, but also increases the number of pages that must be stored, read, and held in the buffer pool. The goal is to balance write costs and read costs based on real data patterns.

## 8. Fragmentation in InnoDB

Fragmentation refers to a state where page layout and data placement are no longer favorable for sequential access or space utilization.

In InnoDB, two symptoms may appear:

1. The physical order of index pages on disk is not close to the logical order of index records.
2. There are many unused pages inside the 64-page extents allocated to an index.

A table can end up occupying more space than expected or requiring more page reads during index scans.

### 8.1. Fragmentation from Random Inserts

Random key inserts into a secondary index can trigger page splits across many regions. Newly allocated pages do not necessarily sit physically adjacent to preceding pages.

When scanning the index in key order, InnoDB still follows the B-tree structure, but physical page layout can make reading data less sequential.

### 8.2. Empty Space from DELETE

DELETE in InnoDB does not necessarily remove records physically at the moment the statement runs. Records can be delete-marked and purged later when no longer needed by existing consistent reads.

After records are physically removed, a page may retain considerable empty space. If the page becomes sparse enough, the merge mechanism can combine it with an adjacent page.

Deleting many rows does not mean the .ibd file will shrink immediately. Freed pages can be reused internally. Returning space to the operating system typically requires rebuilding the table in a file-per-table tablespace.

### 8.3. InnoDB Still Needs Some Free Space

Not all empty space on a page is waste. InnoDB intentionally leaves room for future INSERTs and UPDATEs.

The MySQL 8.4 documentation notes that the fill factor of B-tree pages can vary between 50% and 100%. For clustered indexes, InnoDB tries to keep 1/16 of each page free for growth. Therefore, you should not expect every page to be 100% full.

InnoDB manages pages and tablespaces differently from MyISAM storage. Do not blindly apply MyISAM evaluation rules or periodic OPTIMIZE schedules to InnoDB.

## 9. Monitoring Splits, Merges, and Storage Size

### 9.1. Monitoring INNODB_METRICS

InnoDB provides counters in INFORMATION_SCHEMA.INNODB_METRICS. Relevant counters include:

- index_page_splits: number of index page splits.
- index_page_merge_attempts: number of page merge attempts.
- index_page_merge_successful: number of successful page merges.
- index_page_reorg_attempts: number of page reorganization attempts.
- index_page_reorg_successful: number of successful page reorganizations.

Index counters are usually disabled by default. You can enable the specific counters you want to monitor:

~~~sql
SET GLOBAL innodb_monitor_enable = index_page_splits;
SET GLOBAL innodb_monitor_enable = index_page_merge_attempts;
SET GLOBAL innodb_monitor_enable = index_page_merge_successful;
SET GLOBAL innodb_monitor_enable = index_page_reorg_attempts;
SET GLOBAL innodb_monitor_enable = index_page_reorg_successful;
~~~

Reading the counters:

~~~sql
SELECT
    name,
    count,
    status,
    time_enabled
FROM information_schema.innodb_metrics
WHERE name IN (
    'index_page_splits',
    'index_page_merge_attempts',
    'index_page_merge_successful',
    'index_page_reorg_attempts',
    'index_page_reorg_successful'
)
ORDER BY name;
~~~

These counters reflect instance-wide activity and are not broken down per table. Record values before and after a test workload to compare deltas. If multiple applications are writing concurrently, results may include activity from other tables.

Enabling metrics adds overhead. Before enabling, record the initial state of the module. Only disable a module after testing if you enabled it yourself and no other diagnostic workload is using it; do not disable a module that was already enabled by an administrator beforehand.

If these counters were previously disabled and were enabled specifically for this diagnosis, they can be disabled afterward:

~~~sql
SET GLOBAL innodb_monitor_disable = index_page_splits;
SET GLOBAL innodb_monitor_disable = index_page_merge_attempts;
SET GLOBAL innodb_monitor_disable = index_page_merge_successful;
SET GLOBAL innodb_monitor_disable = index_page_reorg_attempts;
SET GLOBAL innodb_monitor_disable = index_page_reorg_successful;
~~~

Appropriate administrative privileges are required to modify monitor variables. Test in development or staging environments before enabling on production.

### 9.2. Inspecting Table Storage Size

You can view estimated data size, index size, and free space:

~~~sql
SELECT
    table_name,
    engine,
    table_rows,
    data_length,
    index_length,
    data_free
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'event_update_demo',
      'event_random_demo',
      'product_code'
  );
~~~

InnoDB statistic values may be estimates. DATA_FREE reflects free space reported at the tablespace level and is not an accurate metric for the fragmentation ratio of an individual index.

You can also use:

~~~sql
SHOW TABLE STATUS LIKE 'event_update_demo';
SHOW INDEX FROM event_update_demo;
~~~

Combine size, growth rate, split/merge counts, query latency, and actual read patterns. Do not conclude a table is severely fragmented solely because DATA_FREE is large or an index has many sparse pages.

### 9.3. Comparing Metrics Over Time

A single metrics snapshot only shows cumulative counters. A more meaningful measurement process:

1. Record split, merge, and reorganization counts before the test.
2. Run a workload with a defined INSERT/UPDATE/DELETE pattern.
3. Read the counters again.
4. Compute the delta over the test interval.
5. Compare against rows written, index size, and query latency.
6. Repeat with a different key design or configuration.

Avoid comparing two measurements if row counts, indexes, cache states, or concurrency levels differ too widely.

## 10. When Should You Rebuild or Run OPTIMIZE TABLE?

InnoDB may benefit from a rebuild after deleting large amounts of data or when page distribution makes index and table scans inefficient. However, some level of fragmentation is normal.

### 10.1. OPTIMIZE TABLE with InnoDB

For InnoDB, OPTIMIZE TABLE maps to ALTER TABLE ... FORCE. This operation rebuilds the table, updates index statistics, and frees unused space in the clustered index.

Example:

~~~sql
OPTIMIZE TABLE event_update_demo;
~~~

Equivalent rebuild commands can be used:

~~~sql
ALTER TABLE event_update_demo ENGINE = InnoDB;
~~~

Or:

~~~sql
ALTER TABLE event_update_demo FORCE;
~~~

OPTIMIZE TABLE uses online DDL for standard InnoDB tables, reducing disruption to concurrent DML. Even so, the operation still requires brief exclusive locks during the prepare and commit phases. It can also consume substantial CPU, I/O, and disk space during the rebuild.

InnoDB tables with FULLTEXT indexes do not support this online DDL path and may fall back to the table-copy method. Settings such as old_alter_table or related server options can also alter how rebuilds run. Check specific conditions before running on large tables.

### 10.2. innodb_file_per_table and Space Reclamation

When innodb_file_per_table is enabled, each table has its own tablespace typically stored in an .ibd file. After rebuilding, space no longer needed can be returned to the operating system.

If the table resides in the shared system tablespace, empty pages can be reused by InnoDB for other tables, but the system tablespace file does not automatically shrink.

Checking:

~~~sql
SHOW VARIABLES LIKE 'innodb_file_per_table';
~~~

Do not assume OPTIMIZE TABLE always makes the data file smaller. The outcome depends on tablespace type, workload, and how much space is actually freed.

### 10.3. When Should a Rebuild Be Considered?

You can evaluate a rebuild when:

- A large volume of rows was deleted and free space is unlikely to be reused effectively.
- Table or index size grew disproportionately relative to the remaining data.
- Index scans or table scans slowed down noticeably after heavy write/delete phases.
- There is evidence of many sparse pages or poor page layout.
- Indexes need to be recreated after suitable data or structural changes.

Do not run OPTIMIZE TABLE on a fixed schedule for every table without measuring benefits. Rebuilds create I/O load, require working space, and can impact workload latency.

### 10.4. ANALYZE TABLE Does Not Replace a Rebuild

ANALYZE TABLE updates index statistics so the optimizer can estimate cardinality and pick query plans. It is not a table rebuild or defragmentation operation.

~~~sql
ANALYZE TABLE event_update_demo;
~~~

If the issue is the optimizer picking a poor index due to stale statistics, ANALYZE TABLE can help. If the issue is page distribution or wasted space after extensive writes and deletes, evaluate a rebuild separately.

## 11. Designing to Reduce Split Costs and Fragmentation

### 11.1. Choosing an Appropriate Primary Key

The primary key should be:

- Short to reduce secondary index sizes.
- Stable, rarely updated.
- Ordered to match write patterns when business requirements allow.
- Unique and NOT NULL.

AUTO_INCREMENT is a solid choice for many sequential-write tables. However, distributed systems or requirements for independently generated IDs may need other keys. Measure the cost of that choice across both the clustered index and secondary indexes.

### 11.2. Keeping Secondary Indexes Purposeful

Each secondary index must be updated on INSERT, DELETE, or UPDATE of relevant key columns. Too many indexes increase write work and the number of B-trees to maintain.

Before adding an index, identify which queries need it. After workload changes, evaluate unused indexes and consider controlled removal.

### 11.3. Limiting Unnecessary Index Key Changes

If a column is updated frequently and included in multiple secondary indexes, every change may require removing the old entry and inserting a new entry. Choose stable index keys whenever possible.

For variable-length string columns, consider realistic data lengths and their impact on page occupancy. There is no need to declare overly wide VARCHARs for every column when business data has clear bounds.

### 11.4. Batching Writes Appropriately

For bulk insert workloads, overhead can be reduced by loading data in batches and sorting input by an appropriate index key when doing so does not alter business semantics.

For newly created or rebuilt indexes, InnoDB uses sorted index builds to load records in order, reducing the cost of inserting entries one by one into the B-tree. This is a different mechanism from the normal INSERT path.

### 11.5. Evaluating Trade-Offs Instead of Optimizing a Single Metric

| Choice | Potential benefit | Cost to consider |
|---|---|---|
| Sequential primary key | Sequential clustered index inserts | Can concentrate writes at the trailing end |
| Random primary key | Easy distributed ID generation | Inserts across many regions, increasing splits and sparse pages |
| Fewer secondary indexes | Reduces index write work | Some queries may have to scan more rows |
| Lower fill factor on rebuild | Leaves room for growth | Increases page count and read costs |
| Lower MERGE_THRESHOLD | Reduces repeated merge-splits | Retains more sparse pages |
| Table rebuild | Reorganizes pages and reclaims space | Costs I/O, time, and working disk space |

## 12. Hands-On Comparison of Sequential vs. Random Keys

This lab creates two tables with the same data structure. One table uses AUTO_INCREMENT; the other receives randomly distributed primary keys. Both share a secondary index on event_time.

### 12.1. Creating the Tables

~~~sql
CREATE TABLE event_sequential (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_time DATETIME NOT NULL,
    category_id INT UNSIGNED NOT NULL,
    payload VARCHAR(100) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;

CREATE TABLE event_random (
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    category_id INT UNSIGNED NOT NULL,
    payload VARCHAR(100) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_time (event_time)
) ENGINE = InnoDB;
~~~

### 12.2. Loading Test Data

The following procedure generates 20,000 rows for each table. event_time has the same distribution pattern in both tables; the main difference is primary key ordering.

~~~sql
DELIMITER //

CREATE PROCEDURE seed_page_split_demo()
BEGIN
    DECLARE i BIGINT DEFAULT 1;
    DECLARE event_time_value DATETIME;

    WHILE i <= 20000 DO
        SET event_time_value = TIMESTAMPADD(
            SECOND,
            MOD(i * 3571, 1000003),
            '2026-01-01 00:00:00'
        );

        INSERT INTO event_sequential (
            event_time,
            category_id,
            payload
        )
        VALUES (
            event_time_value,
            MOD(i, 100),
            RPAD('x', 100, 'x')
        );

        INSERT INTO event_random (
            event_id,
            event_time,
            category_id,
            payload
        )
        VALUES (
            MOD(i * 7919, 1000003) + 1,
            event_time_value,
            MOD(i, 100),
            RPAD('x', 100, 'x')
        );

        SET i = i + 1;
    END WHILE;
END//

DELIMITER ;

CALL seed_page_split_demo();

DROP PROCEDURE seed_page_split_demo;
~~~

Run this in a practice database. The procedure inserts row by row to illustrate the key pattern; this is not a recommendation for bulk data loading in production.

### 12.3. Enabling and Reading Metrics

Before running the procedure, enable the split counter and record its initial value:

~~~sql
SET GLOBAL innodb_monitor_enable = index_page_splits;

SELECT
    name,
    count,
    status
FROM information_schema.innodb_metrics
WHERE name = 'index_page_splits'
ORDER BY name;
~~~

After running the procedure, read the counter again and compare the increase. Because the counter is instance-wide, run the lab on a test server with minimal competing workload. If you enabled the counter specifically for this lab and it was previously off, disable it afterward with SET GLOBAL innodb_monitor_disable = index_page_splits.

### 12.4. Comparing Storage Sizes

~~~sql
SELECT
    table_name,
    table_rows,
    data_length,
    index_length,
    data_free
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'event_sequential',
      'event_random'
  );
~~~

Statistical data may be approximate. With two small tables, differences may not yet be pronounced. Increase the row count or repeat the experiment to observe the trend.

### 12.5. Interpreting Results

When analyzing, answer:

- Which table has its clustered index inserted in sequential order?
- Does the secondary index event_time share the same insert pattern in both tables?
- How did the split count increase after loading the data?
- How do data_length and index_length differ?
- If event_time were changed to monotonically increasing order, how would the secondary index be affected?
- If the random primary key were changed to a monotonically increasing key, how would write costs change?

Exact numbers depend on MySQL version, page size, buffer pool state, row format, data, and workload. The goal of the lab is to observe trends, not to assert a fixed split ratio.

## 13. Workflow for Diagnosing Page Splits and Fragmentation

When suspecting heavy B-tree splits or fragmentation, follow this sequence:

1. Identify which tables and indexes experience heavy INSERT, UPDATE, or DELETE activity.
2. Inspect the clustered index and secondary indexes, including key order and key lengths.
3. Determine whether insert patterns are sequential or random.
4. Record split, merge, and reorganization counts using INNODB_METRICS.
5. Compare metric deltas against write volume and measurement duration.
6. Check data_length, index_length, data_free, and query latencies.
7. Determine whether sparse pages reflect intentional free space or the aftermath of deletes/updates.
8. Test adjusting MERGE_THRESHOLD or fill factor in a test environment if supporting evidence exists.
9. Re-measure under the same workload.
10. Rebuild only when expected benefits outweigh operational costs.

You can remember the relationship between data operations and page structures using this diagram:

~~~mermaid
flowchart TD
    A[INSERT or UPDATE] --> B{Index key changed?}
    B -->|No| C{Row grew larger?}
    B -->|Yes| D[Remove old entry and insert new entry]
    C -->|No| E[Rewrite row in page if space allows]
    C -->|Yes| F{Page has enough room?}
    F -->|Yes| E
    F -->|No| G[Reorganize or allocate page and split]
    D --> H{Target page has enough room?}
    H -->|Yes| I[Insert new entry]
    H -->|No| G
    I --> J[Check page state]
    E --> J
    G --> J
    J --> K{DELETE or UPDATE made page sparse?}
    K -->|Yes| L{Below MERGE_THRESHOLD?}
    L -->|Yes| M[Attempt merge with adjacent page]
    L -->|No| N[Keep current page]
    M --> O[Monitor merge-splits and size]
    K -->|No| N
~~~

## 14. Common Misconceptions

| Misconception | Reality | How to handle |
|---|---|---|
| Every INSERT causes a page split | A split is only needed when a page lacks room after reorganization | Monitor split counts instead of counting INSERTs |
| Only the clustered index splits | Every B-tree index can split | Evaluate secondary indexes as well |
| AUTO_INCREMENT eliminates all fragmentation | Secondary indexes can still receive random keys | Examine write ordering for each index |
| Page splits always divide strictly 50/50 | Split behavior depends on insert position and page state | Do not predict occupancy from a simplistic example |
| DELETE returns space to the OS immediately | Pages can be reused within the tablespace | Rebuild when reclaiming file-per-table space is needed |
| Updating any column splits pages | Only certain size or key changes require structural page changes | Check whether the column is indexed and whether the page has room |
| Lower MERGE_THRESHOLD is always better | A low threshold can leave many sparse pages | Measure merges, splits, and storage size |
| innodb_fill_factor controls every INSERT | It is a hint for sorted index builds | Adjust only when creating or rebuilding indexes |
| OPTIMIZE TABLE only updates statistics | On InnoDB, it rebuilds the table via ALTER TABLE ... FORCE | Plan for I/O, disk space, and DDL impact |
| DATA_FREE is an exact fragmentation ratio | It is a tablespace-level free space statistic | Combine metrics, sizes, and workload analysis |
| Page split means the entire table is locked | A split is a B-tree structural change, not a default full-table lock | Distinguish internal latches, row locks, and metadata locks |

## 15. Practice Exercises

### Exercise 1: Sketching B-Tree Structures

Create a table with a PRIMARY KEY and two secondary indexes. Sketch the root, non-leaf, and leaf pages for each index. Explain why a single row appears across multiple index trees.

### Exercise 2: Comparing Sequential vs. Random Keys

Use the two tables event_sequential and event_random. Load the same number of rows with both key patterns. Compare split counts and index sizes.

### Exercise 3: Random Inserts into a Secondary Index

Keep an AUTO_INCREMENT primary key while inserting out-of-order event_time values. Explain why the secondary index can still split.

### Exercise 4: Updating an Index Key

Create a table with a UNIQUE index on code. Update code from short values to long values, and from long values to short values. Analyze old entries, new entries, and split/merge potential.

### Exercise 5: Updating a Non-Indexed Column

Update payload on the same table. Compare with updating an indexed column. Explain the difference in B-tree maintenance work.

### Exercise 6: Observing MERGE_THRESHOLD

Create two tables with different MERGE_THRESHOLD settings. Run a DELETE and key-shortening UPDATE workload. Monitor merge attempts and successful merges.

### Exercise 7: Identifying Merge-Split Churn

Create a workload alternating DELETEs and INSERTs in the same key range. Monitor merge and split counts. Try lowering MERGE_THRESHOLD and compare.

### Exercise 8: Testing innodb_fill_factor

Record the current innodb_fill_factor value. Rebuild a test table with fill factors 80 and 100. Compare sizes, subsequent page splits, and read costs.

### Exercise 9: Evaluating Fragmentation

After inserting and deleting many rows, inspect data_length, index_length, data_free, and scan duration. Explain why a single metric alone is insufficient for conclusions.

### Exercise 10: Controlled Rebuild

Run OPTIMIZE TABLE on a test table. Record before-and-after sizes, execution time, and concurrent DML behavior. Identify conditions that make the operation suitable or unsuitable for production.

## Conclusion

A page split occurs when a new record no longer fits in a B-tree page; a page merge is an attempt to combine sparse pages after DELETEs or key-shortening UPDATEs. Key ordering, primary key length, number of secondary indexes, and how indexed columns are updated determine how much structural maintenance InnoDB must perform.

A certain amount of empty space on pages is necessary for growth and does not signify abnormal fragmentation. Use MERGE_THRESHOLD to tune when merges are attempted, innodb_fill_factor to control fill hints during sorted index builds, and INNODB_METRICS to observe actual behavior. Rebuild or run OPTIMIZE TABLE only when metrics show benefits large enough to justify the I/O, disk space, and operational time costs.

## References

- MySQL 8.4 Reference Manual — The Physical Structure of an InnoDB Index: https://dev.mysql.com/doc/refman/8.4/en/innodb-physical-structure.html
- MySQL 8.4 Reference Manual — Clustered and Secondary Indexes: https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html
- MySQL 8.4 Reference Manual — Sorted Index Builds: https://dev.mysql.com/doc/refman/8.4/en/sorted-index-builds.html
- MySQL 8.4 Reference Manual — Configuring the Merge Threshold for Index Pages: https://dev.mysql.com/doc/refman/8.4/en/index-page-merge-threshold.html
- MySQL 8.4 Reference Manual — InnoDB Startup Options and System Variables: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html
- MySQL 8.4 Reference Manual — Defragmenting a Table: https://dev.mysql.com/doc/refman/8.4/en/innodb-file-defragmenting.html
- MySQL 8.4 Reference Manual — OPTIMIZE TABLE Statement: https://dev.mysql.com/doc/refman/8.4/en/optimize-table.html
- MySQL 8.4 Reference Manual — InnoDB INFORMATION_SCHEMA Metrics Table: https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-metrics-table.html
- MySQL 8.4 Reference Manual — Optimizing Storage Layout for InnoDB Tables: https://dev.mysql.com/doc/refman/8.4/en/optimizing-innodb-storage-layout.html
