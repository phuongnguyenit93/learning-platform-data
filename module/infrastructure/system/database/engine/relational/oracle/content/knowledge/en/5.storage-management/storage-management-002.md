# Block Header, Row Piece, Row Chaining, and Row Migration

In Oracle Database, an application sees **a single row** through a `SELECT` statement, yet Oracle must store that row inside finite-sized **data blocks**. Each block needs to reserve space for metadata to manage the block itself, transactions, and row locations. One SQL row can be represented by **one or more row pieces**; the entire row does not always fit neatly within a single block.

Two special situations that are critical when analyzing storage and performance are:

- **Row chaining:** Oracle must represent a single row using multiple linked row pieces, typically because the row is too large to fit in one data block.
- **Row migration:** a row initially fits inside a block, then **grows in size during an `UPDATE`** and no longer has enough room in its original block; Oracle moves the row data to a new location and keeps forwarding information at the original location.

To understand the difference, you first need to understand the **block header**, **row directory**, **row piece**, and the relationship between **ROWID** and storage location.

## 1. What Storage Unit Is a Data Block?

Oracle organizes storage in layers:

```text
TABLE / INDEX / LOB ... (logical object)
              |
          SEGMENT
              |
           EXTENT
              |
       ORACLE DATA BLOCK
              |
         DATAFILE
              |
      System Storage
```

- A **data block** is the smallest logical storage unit Oracle uses to manage data in the database. Blocks belong to a datafile and are allocated to segments through extents.
- An **extent** is a set of contiguous data blocks allocated to a segment; a segment can consist of multiple extents.
- A **segment** is the storage area for an object such as a heap table or index. A segment has many blocks; a heap table block usually stores many small rows.
- A common Oracle block size is **8 KB**, though this is **not a constant across all databases**. Some environments use different block sizes and some tablespaces have a nondefault block size.

If an Oracle block is 8 KB in size, that **does not mean** every row can use the full 8 KB. Part of the block is reserved for headers, directories, transaction management, and internal structures. Free space reserved for updates also affects how much data can be packed into the block.

> **Scope of this article:** diagrams and examples focus on standard **heap-organized tables**, where rows are stored in table data blocks. Index-organized tables (IOTs), clusters, row compression, Hybrid Columnar Compression, out-of-line LOBs, and special storage organizations have different storage/inspection characteristics; do not treat the byte layout here as a fixed specification for every segment type or release.

## 2. Inside an Oracle Data Block

Conceptual diagram for a heap table's data block:

```text
                  ORACLE DATA BLOCK
   +---------------------------------------------+
   | COMMON + VARIABLE BLOCK HEADER              |
   | - block type, identification/status info    |
   | - transaction metadata, ITL entries ...     |
   +---------------------------------------------+
   | TABLE DIRECTORY                             |
   | - info on tables with rows in the block     |
   +---------------------------------------------+
   | ROW DIRECTORY                               |
   | - entries pointing to row pieces in block   |
   +---------------------------------------------+
   |                                             |
   |       FREE SPACE (depends on actual state)  |
   |                                             |
   +---------------------------------------------+
   | ROW DATA / ROW PIECES                       |
   | - row piece A                               |
   | - row piece B                               |
   | - row piece C ...                           |
   +---------------------------------------------+

   Logical illustration; actual byte order and sizes
   depend on block type, release, and configuration.
```

Oracle can use free space between the directory and row data, and these regions can grow in different directions. The diagram does not show every internal detail and **should not be used to infer absolute byte offsets**.

### 2.1. What Is the Block Header Used For?

The **block header** contains information that helps Oracle identify and manage the block. Key conceptual contents include:

| Information Group | Role |
|---|---|
| Common block info | Identifies block type, address/status information, and metadata for Oracle to verify and use the block properly |
| Version/change info | Information related to change timestamps, SCN, and consistency/recovery mechanisms |
| **Transaction header / ITL** | **Interested Transaction List** entries that help track active transactions modifying rows in the block |
| Space management info | Metadata Oracle needs to locate rows, manage usable space, and update the block |

Do not think of the header as a SQL object you can `SELECT` directly. It is an internal structure inside the block; Oracle exposes relevant information as metadata and statistics in data dictionary/dynamic performance views. Inspecting byte-level block dumps is an advanced diagnostic task, dependent on version and privileges.

#### ITL Is Not "One Transaction per Row"

An **ITL entry** associates the block with a transaction and supports row locking/consistency mechanisms. Oracle can have multiple transactions modifying different rows within the same block. Row headers are marked with the appropriate transaction info; **the ITL belongs to block-level metadata**, and an `UPDATE` does not necessarily create another row piece.

The storage parameter **`INITRANS`** relates to the number of ITL entries pre-allocated in the block. ITL contention between transactions is an access-concurrency issue; it **is not synonymous with** row migration or row chaining.

### 2.2. Table Directory and Row Directory

- The **table directory** stores identification info for tables that have rows in the block. In a normal heap table, rows typically belong to the same table; other block mechanisms such as clusters can be more complex.
- The **row directory** holds entries pointing to the locations of **row pieces** inside the block. Conceptually, Oracle locates a row piece by its *slot* in the block.

A row directory entry **does not guarantee** that it represents an entire SQL row sitting in one place. An entry may point to the first row piece of a chain or to forwarding information for a migrated row.

### 2.3. Free Space and the Meaning of `PCTFREE`

Oracle needs free space in the block to insert additional rows and allow existing rows to **grow in size when updated**.

For regular heap tables, **`PCTFREE`** configures the percentage of block space reserved for updates to rows already in the block, rather than continuing to pack in new rows right up to the limit. For example:

```sql
CREATE TABLE orders_storage (
    order_id NUMBER PRIMARY KEY,
    note     VARCHAR2(1000)
) PCTFREE 20;
```

`PCTFREE 20` expresses the intent to leave growth headroom when managing inserts into the block; it is **not** a guarantee that 20% of the block stays empty forever, nor does it automatically reallocate existing rows to immediately fix all migrated rows.

In **Automatic Segment Space Management (ASSM)**, Oracle uses bitmaps to track block fullness levels. How blocks are selected for inserts also depends on segment management; classic `PCTUSED` rules from **Manual Segment Space Management (MSSM)** should not be applied verbatim to ASSM.

## 3. Row Piece: A Physical Part of a SQL Row

Distinguish between:

- **Logical row (SQL row):** a set of column values read by an application via `SELECT`, e.g., order `ORDER_ID = 101`.
- **Row piece:** a physical representation unit of all or part of a SQL row, residing in a segment block.
- **Row header:** metadata preceding the column values of a row piece; it helps Oracle interpret the piece and row state.
- **ROWID:** a row identifier/location used by Oracle for fast access to a row in a heap table. For a heap table's **extended ROWID**, encoded info includes the data object number, relative file number, block number, and row slot.

A row piece has a header containing information such as **row flags**, lock state, number of columns in the piece, and linking info to another piece when needed, followed by column length/value data. Exact byte formats, flags, and NULL encodings depend on version and data types; never build applications that depend on those internal bytes.

Example of a logical row:

```text
SQL Row:
  (ID=101, CUSTOMER='An', DESCRIPTION='Same-day delivery')

When it fits in one block:
  Block 520, slot 7:
    [row-piece header | ID | CUSTOMER | DESCRIPTION]

When two pieces are needed:
  Block 520, slot 7:
    [row-piece header | ID | CUSTOMER | part of DESCRIPTION]
                     |
                   link
                     v
  Block 876, slot 2:
    [continuation header | remaining part of DESCRIPTION]
```

In the second case, **the application still sees a single row**, not two records requiring a manual JOIN. Oracle follows the physical links and reassembles the data into a logical row before returning the result.

### ROWID: Stable Does Not Mean Every Byte Stays in the Old Block

A `ROWID` can be used to find a heap row's original location, but **should not be used as a business key**:

- Row migration keeps a pointer at the original block so existing ROWID references continue working.
- Other operations, such as moving/reorganizing a table segment, enabling row movement, and certain administrative tasks, can **change the ROWID**.
- For IOTs, `UROWID` identifiers are organized differently; examples in this article do not treat them as identical to physical heap-table ROWIDs.

## 4. Row Chaining: A Row Must Reside Across Multiple Row Pieces

### 4.1. Mechanism

**Row chaining** occurs when Oracle must store a single row using multiple linked row pieces. The familiar case is right at **`INSERT`** time, when the row's size exceeds the space a single data block can hold.

For example, in a tablespace with 8 KB blocks, a row with three `VARCHAR2` columns each holding over 3 KB of data may exceed a single block's capacity after accounting for overhead.

```text
                      ROW CHAINING

Client SELECTs a logical row with ID = 200
                       |
                       v
    BLOCK A: [head row piece: col 1, part of col 2]
                                        |
                                   next piece
                                        v
    BLOCK B: [continuation: part of col 2, col 3]

Oracle reassembles the pieces before returning one SQL row.
```

Oracle can also create multiple row pieces when a row has **a very large number of columns** (for example, exceeding the limit of columns stored in one piece), even if all pieces reside in the **same block**. Therefore, saying "row chaining *always* means multiple blocks" is overly absolute: the clearest performance issue arises when Oracle must follow links and access **additional blocks**.

### 4.2. Common Causes

1. **Row is too wide:** total column data plus overhead cannot fit in one block.
2. **Physical column limit per row piece:** Oracle must split pieces for rows that are extremely wide in column count.
3. **Data grows in an already-chained structure:** the number of pieces or their distribution can change when the row is updated.

A large **CLOB/BLOB** value does not automatically mean the table suffers from chained rows: LOB data has inline/out-of-line storage mechanisms and separate LOB segments depending on configuration, so you must distinguish **heap-table row pieces** from **LOB storage**. Likewise, data compression and table types affect actual row size.

### 4.3. Consequences and Remediation Approach

If multiple blocks must be read to construct one logical row, Oracle may require additional logical I/O, physical I/O, and CPU work. Actual impact depends on access path, caching, data length, access frequency, and how many pieces reside outside the first block.

For rows **inherently larger than one block**, increasing `PCTFREE` will not make the row "fit in a block"; you must evaluate the data model, whether rarely accessed columns can be split into an auxiliary table, choosing appropriate data types/LOBs, or another storage strategy. Increasing the database block size is also **not** a simple configuration tweak or guaranteed fix: it is an architectural decision with platform constraints that requires separate evaluation.

## 5. Row Migration: A Row Grows After an Update

### 5.1. Mechanism

Suppose at `INSERT` time, a row fits neatly in Block A; after many other rows are inserted, the block becomes nearly full. An `UPDATE` statement increases the row's `NOTE` value from 50 bytes to 3,000 bytes. If the original block **no longer has enough free space**, Oracle can move the row to another block.

```text
                    BEFORE UPDATE

   BLOCK A
   +---------------------------------------+
   | row directory                         |
   | slot 5 -> [ID=101 | NOTE='short']     |
   | many other rows, little free space    |
   +---------------------------------------+

                    AFTER UPDATE

   BLOCK A (original location still identifies the row)
   +---------------------------------------+
   | slot 5 -> [forwarding pointer] --------+---+
   +---------------------------------------+   |
                                               v
   BLOCK B                                +---------------------+
                                          | [ID=101 | long NOTE]|
                                          +---------------------+

The logical ROWID of the heap row still locates via the original slot.
```

The information in the old block retains a **forwarding address/pointer** so Oracle can find the relocated row. Thus, **the ROWID of a migrated heap row does not change solely due to migration**, even though the main row data now resides in a different block.

### 5.2. Conditions Favorable to Migration

- Tables with many variable-length columns like `VARCHAR2` that start short and frequently grow.
- Blocks already packed with high insert density; `PCTFREE` is smaller than the actual row growth demand.
- Records updated repeatedly, increasing total row size until no space remains for the current row piece.

**Not every `UPDATE` causes migration:** updating values without increasing size, or increasing size while the block still has room, can keep the row in place. Conversely, tables with fixed-length types can still experience overhead/other changes; observe the environment rather than jumping to conclusions based solely on column types.

### 5.3. Why Can Migration Slow Down Queries?

If Oracle looks up a row via an **index ROWID**, it usually visits the original address first. For a migrated row, it must follow the pointer to the block currently holding the data:

```text
Index lookup
    |
    v
ROWID -> original block / row slot
                    |
                    +----> target block containing actual row
```

Having to access an extra block increases logical block reads and sometimes physical I/O. If the block is already in the buffer cache, the extra access does not necessarily mean a disk read, but it is still extra work Oracle must perform.

A **full table scan** has a different cost model and handling than an index lookup; you cannot look at one migrated row and claim every query on the table slows down to the same degree.

### 5.4. Relocation Is Not Delete + Insert at the SQL Level

Row migration is an **internal** Oracle storage operation during update execution; the application still interacts with one logical row. Constraints, transactions, locks, and SQL consistency still apply. Preserving the ROWID prevents breaking references in indexes that already hold the original ROWID during normal migration.

Never try to "fix" migrated rows by manually updating ROWIDs: ROWID is not a column to which you can assign a custom storage location.

## 6. Comparison Table: Chaining vs. Migration

| Question | **Row chaining** | **Row migration** |
|---|---|---|
| Typical scenario | Row is too large for one data block when created/stored, must be split into multiple pieces | Row originally fit in one block but grew due to `UPDATE`, original block lacks space |
| Physical form | Two or more linked **row pieces** | Original block retains **forwarding** info to the row moved to a new block |
| Is one logical row still one SQL row? | Yes | Yes |
| Can it occur on `INSERT`? | Yes, especially with very wide rows | Not under the typical mechanism; migration comes from an already-stored row growing |
| Can it be caused by `UPDATE`? | Can alter/trigger the need to split pieces | Yes, this is the classic case |
| Heap row `ROWID` | Points to the head/piece per Oracle's mechanism | Retains original location, even though data moved |
| Can a higher `PCTFREE` help? | Cannot fix a row inherently larger than one block's capacity | Can reduce risk when designed to match growth |
| Main remediation direction | Reduce row width, reconsider data organization and storage types | Reserve appropriate free space; reduce updates that enlarge rows; reorganize table when evidenced |
| Measurable with `LIST CHAINED ROWS` | Can be recorded | Can also be recorded |

**Key takeaway:** Oracle and many statistics tools often group **chained/migrated rows** into the same reporting bucket. Looking at a single total **is not enough** to tell whether all rows are chaining or migration; you must combine workload history, row width, table structure, and other evidence.

## 7. Observing the Right Storage Layer Using SQL

### 7.1. Viewing Tablespace, Row Count, and Table Configuration

When logged in as the heap table owner:

```sql
SELECT table_name,
       tablespace_name,
       pct_free,
       ini_trans,
       num_rows,
       avg_row_len,
       chain_cnt,
       last_analyzed
FROM user_tables
WHERE table_name = 'ROW_STORAGE_LAB';
```

Meaning:

- `PCT_FREE` shows the space percentage configured for row updates.
- `NUM_ROWS` and `AVG_ROW_LEN` are **statistics** that may be stale or not yet gathered; they are not live counts/measurements at the time of `SELECT`.
- `CHAIN_CNT` holds info on chained/migrated rows **collected by an appropriate analysis mechanism**, which may be `NULL` or stale. **`DBMS_STATS` should not be assumed to automatically update `CHAIN_CNT`**.
- `LAST_ANALYZED` reflects when statistics were updated; it does not confirm that `CHAIN_CNT` represents all recent transactions.

For applications, use `DBMS_STATS` following administrative procedures to maintain optimizer statistics; **do not arbitrarily run `ANALYZE TABLE ... COMPUTE STATISTICS` in production** just to look for chained rows.

### 7.2. Viewing a Row's Logical Location

Example querying a row with its physical `ROWID` in a heap table:

```sql
SELECT id, ROWID AS rid, LENGTHB(payload) AS payload_bytes
FROM row_storage_lab
WHERE id = 1;
```

Oracle can extract the components of an extended ROWID via the `DBMS_ROWID` package, if the account has execute privileges:

```sql
SELECT id,
       DBMS_ROWID.ROWID_RELATIVE_FNO(ROWID) AS relative_file_no,
       DBMS_ROWID.ROWID_BLOCK_NUMBER(ROWID) AS rowid_block_no,
       DBMS_ROWID.ROWID_ROW_NUMBER(ROWID)   AS row_slot
FROM row_storage_lab
WHERE id = 1;
```

**Interpretation warning:** seeing `ROWID` and `ROWID_BLOCK_NUMBER` **unchanged after an `UPDATE`** is *consistent* with migration, but **does not by itself prove migration happened**. Unmigrated rows also keep their ROWID. Confirmation requires additional diagnostics for chained/migrated rows.

### 7.3. Using `ANALYZE ... LIST CHAINED ROWS` for Detection

Oracle provides a statement to list chained/migrated rows into a helper table. The example below runs in a **lab schema** on a self-created heap table; the account needs privileges to create tables and analyze its own objects.

Create the output table once in the lab schema:

```sql
CREATE TABLE chained_rows (
    owner_name        VARCHAR2(128),
    table_name        VARCHAR2(128),
    cluster_name      VARCHAR2(128),
    partition_name    VARCHAR2(128),
    subpartition_name VARCHAR2(128),
    head_rowid        ROWID,
    analyze_timestamp DATE
);
```

This matches the purpose and structure of the table typically created by Oracle's `utlchain.sql` script. If the environment already has a properly structured `CHAINED_ROWS`, **do not create a duplicate**; if using IOTs or special objects, use the script/data types matching your release per Oracle documentation.

Run the listing analysis:

```sql
TRUNCATE TABLE chained_rows;

ANALYZE TABLE row_storage_lab
    LIST CHAINED ROWS INTO chained_rows;

SELECT owner_name, table_name, head_rowid, analyze_timestamp
FROM chained_rows
WHERE owner_name = USER
  AND table_name = 'ROW_STORAGE_LAB'
ORDER BY analyze_timestamp, head_rowid;
```

To read the exact rows in the list, you can join on ROWID when the output table contains valid head ROWIDs:

```sql
SELECT t.id, LENGTHB(t.payload) AS payload_bytes, c.head_rowid
FROM row_storage_lab t
JOIN chained_rows c
  ON t.ROWID = c.head_rowid
WHERE c.owner_name = USER
  AND c.table_name = 'ROW_STORAGE_LAB';
```

`LIST CHAINED ROWS` is useful when you need to know **which specific rows** have issues; it does not automatically classify the cause into a "MIGRATION" or "CHAINING" column. On large tables, scanning to list rows incurs I/O cost and requires privileges, so schedule appropriately. Never `TRUNCATE` a shared `CHAINED_ROWS` table used by the administration team.

### 7.4. Runtime Metrics for Supporting Evidence

Some Oracle statistics have names like **`table fetch continued row`**. With access to dynamic performance views, an administrator can monitor counter changes within a session:

```sql
SELECT n.name, s.value
FROM v$mystat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name = 'table fetch continued row';
```

This counter can reflect instances where Oracle had to continue fetching data from chained/migrated rows, though it **is not a unique error-row count** for a single table, does not fully separate the two causes, and depends on access type. Measure before/after an equivalent workload and combine with execution plans/I/O before concluding performance impact. Privileges to view `V$...` vary by account role.

## 8. Reproducible Practice

The commands below are for **a dedicated lab schema**—do not run them on business tables. They illustrate how a row grows and how to use `LIST CHAINED ROWS`. Specific results depend on **block size, block fullness, segment space management, version, and how Oracle allocates space**.

### 8.1. Trying to Trigger Row Migration

Create a table with a variable-length column and intentionally set `PCTFREE 0` so later row growth easily hits a lack of space:

```sql
CREATE TABLE row_storage_lab (
    id      NUMBER NOT NULL,
    payload VARCHAR2(4000 BYTE),
    CONSTRAINT pk_row_storage_lab PRIMARY KEY (id)
) PCTFREE 0;
```

Insert many small rows, then grow one row:

```sql
BEGIN
    FOR i IN 1..500 LOOP
        INSERT INTO row_storage_lab (id, payload)
        VALUES (i, RPAD('a', 120, 'a'));
    END LOOP;
    COMMIT;
END;
/

-- Record the ROWID of ID = 1 before UPDATE.
SELECT id, ROWID AS rid, LENGTHB(payload) AS bytes_before
FROM row_storage_lab
WHERE id = 1;

-- Grow the row once blocks already contain plenty of data.
UPDATE row_storage_lab
SET payload = RPAD('b', 3900, 'b')
WHERE id = 1;
COMMIT;

-- Read ROWID and length again.
SELECT id, ROWID AS rid, LENGTHB(payload) AS bytes_after
FROM row_storage_lab
WHERE id = 1;
```

**Guaranteed expectation:** the `PAYLOAD` length of ID 1 increases; the application still retrieves it with `ID = 1`. **What must not be inferred from ROWID alone:** even though the ROWID value stays the same, you need `LIST CHAINED ROWS` to know whether that specific installation actually moved the row. Oracle does not promise that an arbitrary number of inserts/updates will always produce migration in every configuration.

If you created the `CHAINED_ROWS` table per Section 7.3, run:

```sql
TRUNCATE TABLE chained_rows;

ANALYZE TABLE row_storage_lab
    LIST CHAINED ROWS INTO chained_rows;

SELECT t.id, LENGTHB(t.payload) AS payload_bytes
FROM row_storage_lab t
JOIN chained_rows c
  ON c.head_rowid = t.ROWID
WHERE c.owner_name = USER
  AND c.table_name = 'ROW_STORAGE_LAB';
```

If ID 1 appears, it shows Oracle recorded this row in the list requiring continuation via row piece/forwarding at analysis time. Given the **context of an initially small row, a large growth UPDATE, and PCTFREE 0**, migration is the fitting explanation; confirming the exact byte layout requires deeper diagnostics.

### 8.2. Trying to Trigger Row Chaining

With a standard **8 KB tablespace**, try a wide row whose total values exceed one block:

```sql
CREATE TABLE row_chaining_lab (
    id NUMBER PRIMARY KEY,
    part_a VARCHAR2(4000 BYTE),
    part_b VARCHAR2(4000 BYTE),
    part_c VARCHAR2(4000 BYTE)
);

INSERT INTO row_chaining_lab (id, part_a, part_b, part_c)
VALUES (
    1,
    RPAD('A', 3500, 'A'),
    RPAD('B', 3500, 'B'),
    RPAD('C', 3500, 'C')
);
COMMIT;

SELECT id,
       LENGTHB(part_a) + LENGTHB(part_b) + LENGTHB(part_c) AS total_value_bytes
FROM row_chaining_lab;
```

The total column value in this example is **10,500 bytes**, excluding row piece metadata. On an 8 KB block, one row piece cannot hold the entire row; Oracle must use multiple pieces. On a tablespace with a larger block size, this example **might not chain**, so you need to know the actual block size.

Continue observing:

```sql
TRUNCATE TABLE chained_rows;

ANALYZE TABLE row_chaining_lab
    LIST CHAINED ROWS INTO chained_rows;

SELECT table_name, head_rowid
FROM chained_rows
WHERE owner_name = USER
  AND table_name = 'ROW_CHAINING_LAB';
```

The difference from the migration experiment: the row **was already wide at insert time**. This illustrates a cause of chaining that increasing `PCTFREE` cannot resolve.

### 8.3. Cleaning Up the Lab Environment

Perform this only on the objects just created in your lab schema:

```sql
DROP TABLE row_storage_lab PURGE;
DROP TABLE row_chaining_lab PURGE;
-- Only DROP CHAINED_ROWS if you created it yourself for this lab
-- and no other analysis work uses it.
```

`PURGE` bypasses the recycle bin for the dropped table; in environments where data retention or recovery is needed, do not use it carelessly. Never run `DROP` on tables managed by others.

## 9. Reducing Impact and Choosing Solutions by Cause

### For Row Migration

1. **Estimate actual row growth.** `VARCHAR2` columns inserted short and frequently extended are a signal to inspect.
2. **Choose an appropriate `PCTFREE` from design/block-allocation time.** Increasing `PCTFREE` leaves room for `UPDATE`s, at the trade-off of **lower row density per block**; setting it too high can also increase I/O because the table occupies more blocks.
3. **Review update patterns.** Avoid patterns that insert short placeholders and later fill thousands of bytes into the same row if the business domain allows a cleaner data design.
4. **Evaluate segment reorganization when needed.** Operations like table move/redefinition or appropriate maintenance solutions can rewrite rows into a fresh layout. They can change ROWIDs, affect indexes, locks, storage, and availability; choose methods/options by release, test, and schedule rather than treating them as a "cure-all" command.
5. **Re-measure after changes** under the same workload/conditions and diagnostic tools. Reducing migrated row counts does not guarantee every query speeds up.

Changing a table attribute with `ALTER TABLE ... PCTFREE ...` generally affects how Oracle manages **subsequent inserts/allocations**; it **does not automatically relocate or "un-migrate" existing rows**.

### For Row Chaining

1. **Confirm whether rows exceed block capacity.** If a row is inherently larger than a block, increasing `PCTFREE` only reduces usable space for new inserts.
2. **Review row width:** which columns are always read together, which are rarely accessed, and can large data be placed in a separate structure without overcomplicating business logic?
3. **Choose suitable data storage:** for large documents, images, or long strings, evaluate LOBs and inline/out-of-line options per requirements; this is a data-type and access decision, not just renaming columns.
4. **Do not increase block size solely because stats show chained rows.** Weigh benefits, nondefault block size support, buffer cache, administration, and data migration requirements.
5. **Distinguish chaining from width vs. migration from updates** before picking a solution: a reorganize operation may re-lay out migrated rows, but cannot cram a row larger than a block into a smaller block.

### Trade-offs When Optimizing

| Option | Can Help | Trade-offs / Limitations |
|---|---|---|
| Increase `PCTFREE` reasonably | Reduces migration risk from post-insert row growth | Lowers data density; does not fix rows exceeding block size |
| Reduce row size / redesign large columns | Reduces chained rows and bytes read per query | Schema changes, code changes, and join costs |
| Planned table segment reorganization | Re-lays out rows, can reduce existing migration | Costs I/O/time/space; may change ROWIDs and affect indexes |
| Use LOBs as needed | Moves large values to suitable storage, keeping huge values out of heap rows | LOBs still incur access costs, metadata, and separate storage |
| Change block size/tablespace | May suit wide-row workloads within certain limits | Complex architectural decision, not a default tuning step |

## 10. Common Misconceptions

| Claim | Correct Understanding |
|---|---|
| "An 8 KB block holds exactly 8 KB of data for one row." | A block also holds headers, directories, transaction metadata, and row piece overhead. |
| "Block header is row header." | The **block header** manages the block; the **row header** describes a row piece inside the block. |
| "One row directory entry always points to the entire row." | It may point to a row piece or forwarding information; a row can span multiple pieces/blocks. |
| "Row chaining is only caused by updates." | Chaining typically occurs right from insert when a row doesn't fit in a block; migration typically occurs when an update enlarges a row. |
| "Row chaining always requires two different blocks." | Some wide-column rows may split pieces within the same block; inspect the actual layout. |
| "A migrated row changes its ROWID to the new block's address." | Oracle preserves the original ROWID via a forwarding pointer during normal heap-row migration. |
| "If ROWID before/after update is equal, there is no migration." | ROWID remains stable in both non-migration and migration cases, so that comparison alone cannot distinguish them. |
| "A non-`NULL` `CHAIN_CNT` is the exact current row count." | It depends on analysis execution and collection time; it can be stale. |
| "Increasing `PCTFREE` fixes all chaining." | It cannot make a row larger than a block's capacity fit inside one block. |
| "Reorganizing a table is always good tuning." | Requires I/O evidence and clear goals; table move/redefinition carries operational cost and risk. |
| "A table with large CLOBs always has chained rows in the heap table." | LOB data has its own storage mechanism; inspect inline/out-of-line settings and actual structure. |

## 11. Review Questions and Practical Scenarios

**Question 1.** A row is inserted with `NOTE = 'OK'` into a nearly full block, then `NOTE` is updated to 3,000 characters. Index-based queries sometimes have to read an extra block. What possibility should be checked?

**Hint:** row migration because the row grew after an update and the original block lacked space. Check using `LIST CHAINED ROWS`, review update history, and inspect runtime statistics. Do not treat an unchanged ROWID as proof disproving migration.

**Question 2.** A row has multiple `VARCHAR2` columns totaling 11 KB of data on an 8 KB tablespace right at insert time. Will raising `PCTFREE` from 10 to 30 eliminate the issue?

**Hint:** no. The row exceeds one block's capacity; Oracle must use multiple row pieces. Increasing `PCTFREE` does not create extra bytes inside a block.

**Question 3.** Why can a `SELECT ... WHERE ID = :id` query via an index be more sensitive to migration in one case than another, and does physical I/O always increase?

**Hint:** the index points to the original ROWID and must follow the forwarding pointer to find the data; reading an extra block may be logical I/O, while physical I/O increases only when data must be read from disk because it is not already in cache.

**Question 4.** The system reports `CHAIN_CNT = 0` while the application performs many `UPDATE`s that enlarge rows. Can you conclude with certainty that there are no migrated rows?

**Hint:** no. `CHAIN_CNT` depends on analysis execution and statistics collection timing. Verify again with appropriate tools and compare against the workload.

**Question 5.** A table has very wide rows because it contains many rarely read fields. How would you optimize it first?

**Hint:** identify access patterns, actual row width, row piece counts, and root cause. If chaining is an inevitable consequence of the data model, consider redesigning to separate rarely accessed parts or choosing suitable storage types. If the issue is migration, consider `PCTFREE`, update patterns, and planned reorganization.

## Summary

The **block header** holds block-level metadata including transaction/ITL info; the **row directory** points to physical **row pieces**; a **row piece** is how Oracle represents all or part of **one logical row**. **Row chaining** links multiple pieces because a row cannot or is not stored in a single piece; **row migration** typically arises when an update enlarges a row until no space remains in its original block, causing Oracle to move the data and keep a forwarding pointer to preserve the ROWID.

Understanding this distinction lets you choose the right metrics and fixes: **chaining** usually calls for reviewing row width and data organization, whereas **migration** usually calls for reviewing how rows grow and free-space policies. In all cases, performance conclusions must be grounded in workload, cache state, and actual evidence.

**Recommended Oracle documentation for further reading:**

- [Oracle Database Concepts 19c — Physical Storage Structures and Logical Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/index.html): explains data block format, row pieces, chaining/migration, and relationship to segments.
- [Oracle Database SQL Language Reference — ANALYZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ANALYZE.html): `LIST CHAINED ROWS` syntax and notes on the intended use of `ANALYZE`.
- [Oracle Database Reference — USER_TABLES / ALL_TABLES / DBA_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TABLES.html): metadata fields such as `PCT_FREE`, `AVG_ROW_LEN`, `CHAIN_CNT`, and `LAST_ANALYZED`.

When practicing on a release other than 19c, consult the documentation for that specific release because option syntax, observability, and storage characteristics may differ.
