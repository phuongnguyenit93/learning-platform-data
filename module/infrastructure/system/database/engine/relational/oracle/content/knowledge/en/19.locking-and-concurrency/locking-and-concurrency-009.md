# Hot Blocks, ITL, and Contention Under Concentrated Updates in Oracle

In Oracle systems where many sessions write data concurrently, performance sometimes degrades sharply even though sessions are updating different rows. The cause may be that those rows reside in the same **data block**, or many INSERT operations converge on the same **index leaf block**. Another form of contention appears when a block lacks enough **ITL entries** to record transactions concurrently modifying that block. These phenomena are often grouped under *hot block contention*, yet the proper fix depends on the exact contended resource.

For example, a page-view table has millions of sessions updating the same counter; an index on a monotonically increasing key has many sessions inserting into the same right-hand leaf block; or a table with many small rows packed into one block has many concurrent transactions updating those rows. All three scenarios produce waits, yet their nature differs:

- **Hot row:** many transactions try to modify the same row, typically waiting on a row lock.
- **Hot block:** many sessions need to access or modify the same block concurrently, even when working on different rows.
- **ITL contention:** a block lacks enough transaction slots to track additional concurrent transactions modifying rows in that block.

This lesson belongs to the **Locking and Concurrency** topic of *Database Engine Relational Oracle*. It focuses on:

- Data block structure and the role of the Interested Transaction List (ITL).
- Distinguishing row locks, hot blocks, ITL waits, and right-edge index contention.
- Common wait events and how to locate the contended segment/block.
- The roles of INITRANS, PCTFREE, ASSM, and index/partition design.
- Techniques to distribute write load, reduce concentrated updates, and validate with metrics.

## 1. Data blocks as the storage unit and convergence point of operations

Oracle stores data in data blocks. A table block can contain many rows; an index block can contain many entries. When a session reads or modifies a row, Oracle operates on the block containing that row in the buffer cache. Consequently, two transactions updating two different rows can still need the same block.

Example of a block containing rows:

~~~text
Data block #42
+----------------------------------+
| Block header                     |
| ITL slot 1 | ITL slot 2 | ...    |
|                                  |
| Row A: account_id = 101          |
| Row B: account_id = 102          |
| Row C: account_id = 103          |
| Row D: account_id = 104          |
+----------------------------------+
~~~

Session 1 updates Row A and Session 2 updates Row B. The two sessions do not compete for the same row lock, yet both must modify metadata in the same block, including ITL entries and row lock metadata. If the block lacks available ITL entries or cannot expand the ITL due to insufficient free space, a transaction may have to wait.

### A hot block does not mean a hot row

| Scenario | Contended Resource | Typical Symptom |
| --- | --- | --- |
| Many sessions updating the same row | Row lock on that same row | enq: TX - row lock contention |
| Many transactions modifying different rows in the same block, out of ITL slots | ITL slot in the block | enq: TX - allocate ITL entry |
| Many sessions needing the same buffer/block in cache | Buffer/block access or cache structures | May show buffer busy waits, cache buffers chains latch/mutex waits depending on version |
| Many INSERTs into the end of a monotonically increasing index | Right-edge index leaf block | May show buffer/cache contention; in RAC may show global cache waits |

The wait event name is a clue, not a standalone conclusion. Cross-check object, block, SQL_ID, operation type, and concurrency level before choosing a fix.

## 2. What is the ITL?

The **ITL (Interested Transaction List)** is a list of entries in a block used to record transactions currently interested in or modifying that block. Each entry stores metadata needed by Oracle to track the transaction and associated row locks within the block. When a transaction updates a row in a block, Oracle requires an ITL entry to record that transaction.

A way to visualize it:

~~~text
Data block
+--------------------------------------------------+
| Block header                                     |
| ITL 1: transaction X, lock metadata              |
| ITL 2: transaction Y, lock metadata              |
| ITL 3: transaction Z, lock metadata              |
|                                                  |
| Row directory / row data                         |
+--------------------------------------------------+
~~~

The ITL is block-level metadata, while logical DML locking remains row-level locking. Multiple transactions can update different rows in the same block as long as each transaction gets an ITL entry. If no free entry remains and the block cannot allocate another entry, a new transaction may have to wait for an existing transaction to finish so its entry can be reused.

### An ITL entry is not a single shared row lock for the whole block

A common misconception is thinking a block allows only one transaction to update at a time. That is false. A block can hold multiple ITL entries, letting multiple transactions concurrently modify different rows in that block. ITL contention appears when available entries are insufficient for actual concurrency.

### What happens when ITL slots are insufficient?

Suppose a block currently has two ITL entries:

1. Transaction A takes ITL 1 to update row A.
2. Transaction B takes ITL 2 to update row B.
3. Transaction C tries to update row C in the same block.
4. No free ITL entry remains; the block also lacks sufficient free space to expand the ITL.
5. Transaction C must wait for an ITL entry to be freed or for space to allocate one.

In this situation, Oracle may record the wait event enq: TX - allocate ITL entry. This is characteristic of insufficient ITL entries, distinct from waiting on a transaction locking the exact target row.

## 3. How do INITRANS and PCTFREE affect the ITL?

Two storage parameters commonly examined for ITL contention are INITRANS and PCTFREE.

### INITRANS: initial number of ITL entries

INITRANS specifies the initial number of transaction entries allocated in each new block of a segment. Oracle can allocate additional ITL entries dynamically if the block still has enough free space.

- Tables usually have a low default (typically 1).
- Indexes usually have a different default (typically 2).
- INITRANS can be increased when anticipating many concurrent transactions modifying rows in the same block.
- Higher INITRANS pre-reserves more space for ITL, reducing initial space available for row/index entries.

Example:

~~~sql
CREATE TABLE hot_rows_demo (
    id         NUMBER PRIMARY KEY,
    group_id   NUMBER NOT NULL,
    value_num  NUMBER
)
INITRANS 8
PCTFREE 20;
~~~

For an index:

~~~sql
CREATE INDEX ix_hot_rows_group
ON hot_rows_demo(group_id)
INITRANS 8
PCTFREE 20;
~~~

The values 8 and 20 are illustrative examples, not universal optimal settings. Choose based on concurrency, block size, row size, segment type, and actual wait metrics.

### PCTFREE: reserving space in a block

PCTFREE specifies the percentage of a block reserved as free space to support updates and metadata expansion such as ITL growth. If a block has no free space left, Oracle may be unable to expand the ITL even when initial transaction slots are exhausted.

Increasing PCTFREE can help keep space available for extra ITL entries and row growth during UPDATEs. Trade-offs:

- Fewer rows/index entries fit per block.
- The segment may require more blocks.
- Full scans may have to read more blocks.
- Buffer cache and I/O footprints can grow.

PCTFREE is not a switch that solves every hot block. If the root cause is many sessions updating the exact same row or the same index leaf block, increasing PCTFREE alone may not help.

### How INITRANS and PCTFREE work together

| Parameter | Role | Trade-off |
| --- | --- | --- |
| INITRANS | Pre-allocates initial ITL entries in blocks | Consumes extra block space up front |
| PCTFREE | Reserves free space so rows and ITL can grow | Reduces row/entry density per block |

If many concurrent transactions modify different rows in the same block, you may need to raise INITRANS and ensure PCTFREE is adequate for dynamic ITL expansion. Evaluate both parameters together with row distribution and block size.

### Does changing INITRANS immediately affect existing blocks?

Do not assume ALTER TABLE ... INITRANS or ALTER INDEX ... INITRANS immediately rewrites all existing blocks. Updated storage parameters primarily govern new block creation/formatting; existing blocks may retain their previously allocated ITL structures. To apply broadly to existing blocks, evaluate moving/rebuilding the segment appropriately and re-measure. For indexes, rebuild recreates leaf blocks with the new setting; for tables, MOVE or reorganization suited to your version and partitioning may be needed.

## 4. Distinguishing ITL contention from row lock contention

Both wait events start with TX, yet their nature differs:

### enq: TX - row lock contention

A transaction is waiting for another transaction to finish because the row it wants to modify is locked. For example, two sessions both updating ACCOUNT_ID = 10. Fixes usually involve shortening lock-holding transactions, reducing concurrent updates to the same row, or redesigning concentrated write targets.

### enq: TX - allocate ITL entry

A transaction needs an ITL entry in a block, yet no slot is available and the block cannot allocate another entry at that moment. The transactions may be modifying completely different rows. Fixes focus on ITL, free space, and spreading hot rows across more blocks.

| Characteristic | Row lock contention | ITL contention |
| --- | --- | --- |
| Resource | A specific row | An ITL slot in a block |
| Can transactions modify different rows? | Usually no, because the same row is locked | Yes |
| Typical wait event | enq: TX - row lock contention | enq: TX - allocate ITL entry |
| Remediation direction | Reduce same-row contention, shorten transactions | INITRANS, PCTFREE, block reorganization, load distribution |

Never raise INITRANS to cure a hot row. INITRANS does not let two transactions modify the same locked row; it only helps a block track more distinct concurrent transactions.

## 5. Table hot blocks vs. index hot blocks

Hot blocks can occur in different segment types. Identifying the location guides the right solution.

### Hot table block

A hot table block occurs when many DML operations concurrently access one table data block. Common causes:

- A very small group of rows is updated continuously.
- Many rows share one block because rows are tiny and a block holds many rows.
- INSERTs cluster into a region of blocks due to data layout or free-space allocation.
- Many sessions update columns in different rows while still updating metadata in the same block.

If waits are ITL allocation, inspect INITRANS/PCTFREE and spreading rows. If waits are buffer busy or cache buffers chains, identify which operations compete for the buffer and why that block is hot; raising INITRANS is not a default cure.

### Hot index leaf block

A B-tree index can become hot on its rightmost leaf block when the index key increases almost monotonically, such as an ascending sequence or current timestamp:

~~~text
Index leaf blocks (ascending keys)

[100-199] -> [200-299] -> [300-399] -> [400-499]
                                         ^^^^^^^
                                      many INSERTs
                                      target here
~~~

New INSERTs with larger keys typically land in the rightmost leaf block. When many sessions insert concurrently, they contend on that block even though each row in the table is brand new and distinct.

### Why can ascending sequences create hotspots?

Sequences supply unique keys, yet continuously increasing values push new index entries into one leaf block area. Sequence CACHE reduces number-generation overhead and dictionary/sequence state access, but **does not distribute index leaf blocks**. If waits center on the right-edge leaf block, revisit index structure or key distribution.

### Reverse key index

A reverse key index reverses the bytes of the key value before storing it in the index. Ascending keys are thereby spread across many leaf regions instead of piling onto the right edge.

~~~sql
CREATE INDEX ix_orders_id_reverse
ON orders(order_id)
REVERSE;
~~~

Advantages:

- Can reduce contention on right-edge leaf blocks for ascending-key INSERT workloads.
- Still supports equality lookups on the reversed key.

Limitations:

- Unsuitable for range scans in original key order such as BETWEEN or ORDER BY order_id.
- Does not fix hot table rows/blocks if the hotspot resides in the table segment.
- Must weigh queries, FKs, and application access patterns before switching the index.

Do not create a reverse key index merely because you see heavy INSERTs. First confirm waits actually concentrate on the leaf block of a monotonically increasing index.

### Hash-partitioned indexes and partitioning

Hash partitioning can distribute key values across multiple partitions, increasing the number of write targets when keys distribute well. For example, a global hash-partitioned index splits the index into partitions by key hash, each with its own B-tree.

Benefits depend on key distribution and query patterns. If all DML still hits the same key or same partition, partitioning will not remove the hotspot. On partitioned tables, local indexes can also separate workloads by partition key; partition key design must fit both queries and write distribution.

## 6. Wait events and reading symptoms

Wait events narrow down the contention class, but you still need segment and block details:

| Wait / Event | Suggested Cause | What to Verify |
| --- | --- | --- |
| enq: TX - row lock contention | Waiting for another transaction to release a row lock | Are two sessions modifying the same row/key? |
| enq: TX - allocate ITL entry | No ITL entry available in block | Which segment has high ITL waits? Does the block have free space? |
| buffer busy waits | Waiting for a buffer/block used by another session in a conflicting mode | Which file/block/class repeats? Is the object a table or index? |
| latch: cache buffers chains | Contention on hash chains managing buffers in cache | Are many sessions accessing the same set of buffers/blocks? |
| gc buffer busy acquire/release (RAC) | Buffer/block contention via Global Cache Service | Are instances concurrently writing to the same hot block? |
| gc current block busy (RAC) | Waiting for current block processing/transfer between instances | Is a block pinging back and forth across instances? |

Wait event names and details can vary by Oracle version, single-instance/RAC setup, and execution path. Do not conclude "hot block" from a single wait row; check frequency, duration, specific object, and block.

### Checking waiting sessions

Access to V$ views depends on privileges granted to the account:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       p1text, p1,
       p2text, p2,
       p3text, p3
FROM v$session
WHERE status = 'ACTIVE'
  AND state = 'WAITING'
  AND wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
~~~

The output shows what sessions are waiting on and the P1/P2/P3 event parameters. Parameter meanings depend on each wait event; do not assume P1/P2 always mean file/block for every event.

### Finding segments with high ITL waits and buffer busy waits

~~~sql
SELECT owner,
       object_name,
       subobject_name,
       statistic_name,
       value
FROM v$segment_statistics
WHERE statistic_name IN (
    'ITL waits',
    'buffer busy waits',
    'row lock waits'
)
ORDER BY value DESC;
~~~

Counters in this view are cumulative statistics. Compare two snapshots taken over a peak-load interval to see which segments climb rapidly; do not judge solely by total counts since instance startup. Statistic names can depend on version/segment type, so inspect the actual names exposed by your database.

### Using ASH when licensed

Active Session History can help locate SQL and blocks appearing frequently in active session samples:

~~~sql
SELECT sample_time,
       session_id,
       session_serial#,
       sql_id,
       event,
       current_obj#,
       current_file#,
       current_block#
FROM v$active_session_history
WHERE sample_time > SYSTIMESTAMP - INTERVAL '15' MINUTE
  AND event IS NOT NULL
ORDER BY sample_time DESC;
~~~

V$ACTIVE_SESSION_HISTORY and AWR/ASH historical views belong to the Diagnostics Pack feature set in Oracle editions subject to that licensing policy. Use only if your organization holds the proper license. Without a license, start with V$SESSION, V$SEGMENT_STATISTICS, appropriate traces, and licensed monitoring tools.

### Mapping file/block to the owning segment

Once you have a valid file number and block number (e.g., from ASH or clearly defined wait parameters), find the extent containing that block:

~~~sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       block_id,
       blocks
FROM dba_extents
WHERE file_id = :file_no
  AND :block_no BETWEEN block_id AND block_id + blocks - 1;
~~~

Both file_no and block_no binds must come from a source valid for the wait being analyzed. A partitioned segment may show partition_name; an index and table can both be involved in one DML operation yet belong to distinct segments.

## 7. Ordered diagnostic workflow

When the system slows down due to concentrated updates, trace from symptoms down to the block/object instead of immediately tweaking storage parameters:

1. **Identify timing and workload:** when do waits spike, is the operation INSERT or UPDATE, and how many concurrent sessions are active?
2. **Group by wait event:** row lock, ITL allocation, buffer busy, cache buffers chains, or global cache?
3. **Identify SQL:** capture SQL_ID, module/action, bind patterns, and DML type causing waits.
4. **Identify segment:** table, index, partition, or other segment; check V$SEGMENT_STATISTICS.
5. **Identify the hot block:** verify file/block from reliable sources and map to extent and object.
6. **Identify lock pattern:** same row, multiple rows in one block, or right-edge index leaf block?
7. **Pick an appropriate change:** reduce hot rows, raise ITL/free space, spread keys, or change index/partition structure.
8. **Re-measure under the same workload:** compare wait time, throughput, latency, block counts, redo, and impact on read queries.

A change is only beneficial if waits drop while business throughput and latency improve, not simply because a single isolated counter went down.

## 8. Choosing the right fix for the contention type

No single parameter fixes every hot block. Choose remediation based on the identified wait and segment.

### Case A: ITL allocation waits

If a segment shows sharply rising ITL waits and the workload truly updates many different rows in the same block:

1. Check INITRANS on the affected table/index.
2. Check PCTFREE and remaining free space in blocks.
3. Evaluate increasing INITRANS for newly allocated blocks.
4. If existing blocks still lack slots, evaluate MOVE/rebuild/reorganization to rewrite blocks with the new storage parameters.
5. Re-measure ITL waits and throughput under the same concurrent workload.

Example configuration for a newly created segment:

~~~sql
CREATE TABLE transaction_heavy_rows (
    row_id     NUMBER PRIMARY KEY,
    bucket_id  NUMBER NOT NULL,
    payload    VARCHAR2(100)
)
INITRANS 12
PCTFREE 25;
~~~

The numbers are purely illustrative. INITRANS 12 reserves more slots than default; PCTFREE 25 leaves a larger free-space reserve. If blocks normally see only two concurrent transactions, this setting could waste space without meaningful gain.

For an index experiencing ITL waits:

~~~sql
ALTER INDEX ix_transaction_heavy_rows
INITRANS 8;

ALTER INDEX ix_transaction_heavy_rows
REBUILD INITRANS 8 PCTFREE 20;
~~~

ALTER INDEX changes storage attributes for future blocks; REBUILD recreates the index segment with the specified settings. Rebuilding costs I/O, redo/undo, time, and may require extra space; schedule in an appropriate window and check index status afterward.

For a table, applying changes to existing blocks may require segment/partition reorganization, such as MOVE under appropriate conditions:

~~~sql
ALTER TABLE transaction_heavy_rows
MOVE INITRANS 12
PCTFREE 25;
~~~

MOVE can change ROWIDs and affect indexes/availability depending on version, table type, and online options. Check index validity, dependent objects, and deployment plans before executing. Never run example commands on production tables just to test.

### Case B: Many sessions updating the same row

If waits are row lock contention on a single row, INITRANS and PCTFREE will not solve the root cause. Architectural options:

- Reduce updates to the same row by batching/coalescing events.
- Use multiple sharded counters keyed by a distribution key, then SUM shards on read.
- Write append-only events and aggregate asynchronously if business latency allows.
- Use a queue/worker pattern to serialize updates that strictly require ordering.
- Redesign the data model so each write stream has its own data slice.

Example sharded counter:

~~~sql
CREATE TABLE page_view_counter (
    page_id   NUMBER NOT NULL,
    shard_no  NUMBER NOT NULL,
    view_count NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT pk_page_view_counter
        PRIMARY KEY (page_id, shard_no)
);
~~~

Instead of every session updating a single row per page_id, the application picks a shard_no from a shard pool and updates one row in that shard. When reading the total:

~~~sql
SELECT page_id,
       SUM(view_count) AS total_views
FROM page_view_counter
WHERE page_id = :page_id
GROUP BY page_id;
~~~

Counter sharding reduces the likelihood of many sessions locking the same row, at the cost of extra read and operational complexity. Pick shards based on write distribution; if every session still picks shard 0, the hotspot remains.

### Case C: Hot right-edge index leaf block

If INSERTs concentrate on the rightmost leaf block of an ascending-key index, consider:

- A reverse key index if equality queries dominate and key-order range scans are unnecessary.
- A global hash-partitioned index or suitable partition layout to spread inserts.
- A different key/index design if monotonic leading keys can be avoided.
- Scalable sequences or distributed key generation suited to your Oracle release and application.

Sequence CACHE lowers number-allocation overhead, but by itself does not eliminate a hot leaf block. Also avoid enabling ORDER on sequences in RAC unless the application strictly requires global ordering; ORDER can introduce extra serialization. Check sequence behavior and business requirements before changing it.

### Case D: Buffer busy or cache buffers chains

If ITL waits are negligible while buffer busy/cache buffers chains waits are high on a block:

- Determine whether the block is a table, index, segment header, bitmap, or another block type.
- Identify which SQL accesses that block and whether operations are insert/update/select.
- Check for hot rows, right-edge indexes, bitmap/free-space management, or centralized metadata structures.
- Spread operations across multiple blocks/partitions or alter the access pattern.
- Only change INITRANS/PCTFREE if evidence points to ITL/free space as the bottleneck.

## 9. ASSM, freelists, and free space management

Oracle has mechanisms to manage free space within segments. With Automatic Segment Space Management (ASSM), bitmap blocks track usage/free space of blocks in the segment. With Manual Segment Space Management (MSSM), freelists track blocks with space available for INSERTs.

ASSM helps reduce certain freelist/segment-header contention compared to manual management under suitable workloads, but **does not eliminate hot rows, hot index leaf blocks, or ITL contention**. A data block can still become hot if many transactions access it concurrently.

Distinctions to keep clear:

- ASSM bitmap contention involves space-management bitmap blocks; it is not the same as ITL waits in a table block.
- MSSM freelist contention involves multiple sessions pulling free blocks from the same freelist; FREELISTS/FREELIST GROUPS are parameters for manual management where applicable.
- ITL contention occurs inside blocks storing rows/index entries when transaction slots are exhausted.
- Hot index leaf blocks relate to B-tree structure and key distribution, not table freelists.

Do not migrate MSSM to ASSM or alter storage management solely from one wait event. Identify the exact block type and space-management mechanism governing the segment first.

## 10. RAC: hot blocks across multiple instances

In Oracle RAC, each instance has its own buffer cache. A block read/written by multiple instances must transfer ownership via Global Cache Service (GCS)/Cache Fusion. If multiple instances continuously update the same block, the block can ping back and forth and generate global cache waits.

Symptoms may include:

- gc buffer busy acquire/release.
- gc current block busy.
- gc current request or related global cache waits depending on version.

Ways to reduce contention:

- Partition workloads by service/instance if the application allows.
- Use partitioning or hash distribution so instances work on disjoint blocks.
- Avoid having multiple instances update the same set of hot rows/index leaf blocks.
- Check service affinity and session placement; do not scatter sessions across instances arbitrarily if it increases block pinging.
- Measure global cache traffic and waits by object/block before and after changes.

Instance affinity only helps if the workload is genuinely partitioned. If all instances still update the same block, pinning services will not eliminate the hotspot.

## 11. Measuring before and after tuning

A storage or schema change can lower one wait while enlarging the segment, increasing block reads, or hurting range scans. Measure across multiple dimensions:

| Metric | Question |
| --- | --- |
| ITL waits | Did waits caused by insufficient ITL entries decrease? |
| Buffer busy waits | Did overall block contention drop? |
| Row lock waits | Are there still hot rows or long-held transaction locks? |
| Throughput | Did transactions per second increase? |
| Latency | Did p95/p99 write latency decrease? |
| Redo/undo | Did redo/undo volume rise due to structural changes? |
| Segment size | Did INITRANS/PCTFREE/partitioning enlarge the footprint? |
| Read performance | Did range scans, equality lookups, and reports slow down? |
| RAC global cache | Did block transfers/pings decrease? |

Compare over equivalent time windows, data profiles, and concurrency levels. If the workload shifts substantially, counter differences may not reflect the configuration change.

## 12. Practice lab: observing rows, blocks, and ITL

This lab uses a learning schema with CREATE TABLE privilege and adequate quota. The goal is to observe how multiple rows pack into the same block and inspect storage metadata. Reproducing exact ITL waits depends on block size, row density, session count, and transaction timing; a small lab may not trigger waits if Oracle still has room to allocate ITL entries dynamically.

### Step 1: create a test table

~~~sql
CREATE TABLE hot_rows_demo (
    id         NUMBER PRIMARY KEY,
    group_id   NUMBER NOT NULL,
    value_num  NUMBER DEFAULT 0 NOT NULL,
    payload    VARCHAR2(30)
)
INITRANS 1
PCTFREE 0;

INSERT INTO hot_rows_demo (id, group_id, value_num, payload)
SELECT level,
       MOD(level, 20),
       0,
       RPAD('X', 20, 'X')
FROM dual
CONNECT BY level <= 2000;

COMMIT;
~~~

PCTFREE 0 is purely for demonstration so blocks have less free space; never use it as a default recommendation for frequently updated tables.

### Step 2: inspect which block holds which rows

~~~sql
SELECT DBMS_ROWID.ROWID_RELATIVE_FNO(rowid) AS file_no,
       DBMS_ROWID.ROWID_BLOCK_NUMBER(rowid) AS block_no,
       COUNT(*) AS rows_in_block,
       MIN(id) AS min_id,
       MAX(id) AS max_id
FROM hot_rows_demo
GROUP BY DBMS_ROWID.ROWID_RELATIVE_FNO(rowid),
         DBMS_ROWID.ROWID_BLOCK_NUMBER(rowid)
ORDER BY rows_in_block DESC;
~~~

Pick a block containing many rows. Record two different IDs residing in the same block to use across two sessions. For partitioned tables or specialized storage formats, ROWID/file number interpretation may need adjustment.

### Step 3: inspect storage attributes

~~~sql
SELECT owner,
       table_name,
       ini_trans,
       pct_free
FROM all_tables
WHERE table_name = 'HOT_ROWS_DEMO';
~~~

With DBA privileges, you can view all schemas via DBA_TABLES. For indexes:

~~~sql
SELECT owner,
       index_name,
       ini_trans,
       pct_free
FROM all_indexes
WHERE table_name = 'HOT_ROWS_DEMO';
~~~

### Step 4: test updating two rows in the same block

Open two separate sessions. Replace :id_a and :id_b with two distinct IDs confirmed to share the same block.

Session A:

~~~sql
UPDATE hot_rows_demo
SET value_num = value_num + 1
WHERE id = :id_a;

-- Keep transaction open, do not commit yet.
~~~

Session B:

~~~sql
UPDATE hot_rows_demo
SET value_num = value_num + 1
WHERE id = :id_b;
~~~

The two sessions modify two different rows. If enough ITL slots exist or Oracle can allocate another ITL dynamically, both complete without waiting. If the block runs out of ITL and cannot expand, a session may wait to allocate an ITL entry. Seeing zero waits in one small test does not prove ITL contention cannot occur under heavier workloads.

End Session A with COMMIT or ROLLBACK. Then inspect Session B and finish Session B's transaction. Do not leave test sessions holding locks for long.

### Step 5: inspect segment statistics

~~~sql
SELECT owner,
       object_name,
       statistic_name,
       value
FROM v$segment_statistics
WHERE object_name = 'HOT_ROWS_DEMO'
  AND statistic_name IN ('ITL waits', 'buffer busy waits', 'row lock waits');
~~~

Record figures before and after concurrent runs. These are cumulative counters; to evaluate accurately, take deltas over the same time window.

### Step 6: test changing INITRANS on new blocks

Create another test table with higher INITRANS:

~~~sql
CREATE TABLE hot_rows_demo_itl8 (
    id         NUMBER PRIMARY KEY,
    group_id   NUMBER NOT NULL,
    value_num  NUMBER DEFAULT 0 NOT NULL,
    payload    VARCHAR2(30)
)
INITRANS 8
PCTFREE 20;

INSERT INTO hot_rows_demo_itl8
SELECT *
FROM hot_rows_demo;

COMMIT;
~~~

Re-run the multi-session test and compare. Note that the new table may distribute rows across blocks differently; for a meaningful comparison, keep workload and test conditions comparable.

### Step 7: clean up data

~~~sql
DROP TABLE hot_rows_demo_itl8 PURGE;
DROP TABLE hot_rows_demo PURGE;
~~~

Run only after finishing the lab when data is no longer needed. DROP TABLE is DDL causing an implicit commit; PURGE bypasses the Recycle Bin.

## 13. Common mistakes and troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Many sessions wait despite updating different rows | Insufficient ITL or hot buffer block | Check wait event, ITL waits, object, and block. |
| Raised INITRANS yet waits did not drop | Cause is a hot row or other buffer/index contention | Distinguish row locks, ITL allocation, and buffer busy waits. |
| Raising PCTFREE made the table larger | Row density per block decreased | Measure block count, full scans, buffer gets, and actual ITL benefit. |
| Slow INSERTs on ascending-key index | Hot right-edge leaf block | Identify index/block; consider reverse key or hash partitioning if queries permit. |
| Reverse key index slowed down range queries | Reverse keys do not preserve original key order for range scans | Use only when equality workloads dominate; consider alternative index designs. |
| ASSM enabled yet hot blocks persist | ASSM does not eliminate row/block/ITL contention | Identify exact block type and wait event. |
| High global cache waits in RAC | Hot block transferred across instances | Review service affinity, workload partitioning, and global cache stats. |
| High ITL wait counter yet no current waits | Counters are cumulative metrics | Compare deltas over time rather than judging from totals. |
| ALTER TABLE INITRANS did not change old blocks as expected | Existing blocks were not rewritten | Consider planned MOVE/reorganization and verify indexes. |

## 14. Self-check questions

1. **What is a hot block?** A block accessed or modified concurrently by many sessions, creating a point of contention.
2. **How does a hot row differ from a hot block?** A hot row involves many transactions trying to modify one single row; a hot block can involve many different rows packed inside the same block.
3. **What is the ITL?** A list of transaction entries inside a block used to record transactions modifying rows in that block.
4. **Which wait event does ITL contention typically produce?** enq: TX - allocate ITL entry.
5. **Which wait event does row lock contention typically produce?** enq: TX - row lock contention.
6. **What does INITRANS do?** Pre-allocates the initial number of ITL entries in new blocks of a segment.
7. **How does PCTFREE support the ITL?** Reserves free space so rows and ITL entries can expand when needed.
8. **Does raising INITRANS fix a hot row?** No; it does not let multiple transactions modify the same locked row.
9. **Why can an ascending-key index become hot at its right edge?** New entries are continuously inserted into the trailing leaf block region.
10. **What does a reverse key index trade off?** It can spread inserts but does not support range scans in original key order.
11. **Does sequence CACHE eliminate a hot index leaf block?** No; CACHE reduces sequence-allocation cost, not index entry clustering.
12. **Does ASSM eliminate ITL contention?** No; ASSM manages free space, while the ITL still lives inside data/index blocks.
13. **Why identify the segment/block before tuning?** Tables, indexes, bitmaps, and segment headers have different causes and remedies.
14. **When should you inspect ASH?** When correlating sessions, SQL, wait events, and blocks over time; must comply with Diagnostics Pack licensing.
15. **Which metrics measure tuning outcomes?** ITL/buffer/row lock waits, throughput, latency, redo/undo, segment size, and impact on read queries.

Hot blocks, ITL, and contention under concentrated updates are related phenomena, yet not identical. Distinguish transactions waiting on the same row, waiting for an ITL slot, or contending on a buffer/index block. INITRANS and PCTFREE help when evidence points to insufficient ITL/free space; reverse keys, hash partitioning, and sharded counters can spread certain write hotspots at the cost of query and operational trade-offs. Diagnose the block, SQL, and wait events before altering structures; then re-measure on a comparable workload to confirm results.
