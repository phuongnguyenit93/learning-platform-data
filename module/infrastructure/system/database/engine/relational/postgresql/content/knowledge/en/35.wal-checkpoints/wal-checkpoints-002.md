# WAL Records, Segments, LSNs, and Change Ordering in PostgreSQL

## 1. Why Understand WAL and Write Ordering?

PostgreSQL uses **Write-Ahead Logging (WAL)** to protect consistency when the server fails and to stream physical changes to standbys. Instead of requiring every data page to be written to data files immediately before confirming a transaction, PostgreSQL records descriptions of changes into WAL in a deterministic order. After a crash, the server can read WAL and redo the required operations starting from an appropriate checkpoint.

WAL is not just a plain-text log file. It is a structured binary stream divided into records, pages, and segments. Each record occupies a region in the WAL stream and has a position represented by a **Log Sequence Number (LSN)**.

To understand why a confirmed COMMIT can survive even when data pages have not yet been flushed, you need to connect these concepts:

- **WAL record:** a binary unit of information describing a change or event needed for recovery/replication.
- **WAL page:** a page unit within the WAL stream, containing a header and holding part of one or more records.
- **WAL segment:** a physical file containing a contiguous range of the WAL stream.
- **LSN:** a logical address identifying a position in the WAL stream.
- **Page LSN:** the last WAL position applied to a data page.
- **Commit record:** a record marking transaction completion.
- **Checkpoint:** the point at which PostgreSQL has ensured required dirty data pages are written out, bounding the redo scope after a crash.
- **Timeline:** a WAL history branch, especially important after promotion/failover.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the write-ahead rule and the relationship between WAL and data pages.
2. Describe the basic components of a WAL record.
3. Distinguish between a WAL record, a WAL page, a WAL segment, and a transaction.
4. Read the LSN format and compute WAL distances using SQL.
5. Understand how WAL segments are named, created, recycled, and archived.
6. Explain WAL record ordering when multiple transactions run concurrently.
7. Distinguish between insert position, write position, and flush position.
8. Understand commit records, group commit, synchronous_commit, and durability.
9. Explain page LSN, redo, and checkpoints.
10. Inspect WAL/replication using PostgreSQL functions, views, and command-line tools.
11. Identify common mistakes when reading WAL and handling segment files.
12. Practice labs and exercises to interpret LSN/record ordering.

### 1.2. Version Scope

WAL/LSN concepts are foundational, but details of record formats, resource managers, system views, functions, and command-line options can change across major versions. The examples use modern PostgreSQL syntax; check the documentation for your exact server version, especially when using pg_walinspect, pg_waldump, or newer monitoring columns.

> WAL is data for recovery. Do not manually edit, rename, or delete files in pg_wal through filesystem operations. If you need to free WAL space, investigate retention causes across checkpoints, archiving, replication slots, and standbys.

---

## 2. Write-Ahead Logging: The Core Rule

### 2.1. The Write-Ahead Rule

The fundamental rule:

**WAL records describing changes to a data page must be durably written to WAL before the corresponding data page is durably written to its data file.**

Suppose an UPDATE modifies a row in a heap page:

~~~text
SQL UPDATE
    |
    v
Modify page in shared buffers (dirty page)
    |
    +--> Create WAL record describing the change
    |
    v
WAL record is inserted into WAL buffers
    |
    v
WAL is written/flushed per durability rules
    |
    v
Data page can be written to heap file later
~~~

This diagram is a conceptual model; the exact ordering across multiple buffers, the background writer, the WAL writer, and backends can be more intricate. What never changes is that PostgreSQL must ensure the required WAL is flushed before the data page containing the corresponding change is durably written.

### 2.2. Why Not Write the Data Page First?

If a data page is written to disk while the WAL record needed to recover that page is not yet durable, a crash could leave the page containing partial changes with no log available to redo or repair it properly.

The write-ahead rule lets recovery know which changes have been logged so it can replay them.

### 2.3. An Unflushed Data Page Does Not Mean an Un-Durable Transaction

A transaction can be COMMITted and acknowledged once its commit record has been flushed per the durability policy, even if the modified heap/index pages are still in shared buffers or not yet written to data files.

On a crash, PostgreSQL reads the checkpoint and redoes WAL to restore any missing page changes. This is why WAL is the foundation of durability.

### 2.4. WAL Does Not Replace Data Files

WAL is not a complete copy of the database that can substitute for the data directory. To restore a database to a desired state, you need an appropriate base backup/data files plus the WAL required by the recovery chain.

### 2.5. WAL and Crash Recovery

When PostgreSQL starts after a crash:

1. Reads checkpoint information.
2. Determines the appropriate redo starting position.
3. Reads WAL records in LSN order.
4. Reapplies necessary changes to data pages.
5. Skips or handles operations already reflected according to the recovery mechanism.
6. Brings the cluster back to a consistent state to serve connections.

Recovery details also involve transaction status, hint bits, full-page images, resource manager redo routines, and other internal mechanisms.

### 2.6. A WAL Record Is Not an SQL Statement

A single SQL statement can generate multiple WAL records:

- Heap tuple UPDATE.
- Updating one or more index entries.
- Related visibility/transaction metadata changes.
- Triggers writing to audit/outbox tables.
- Foreign key actions generating additional DML.
- Transaction/commit records.

Conversely, one WAL record does not equal one row or one SQL statement. WAL describes internal physical/logical changes needed for recovery; it does not store SQL text like a query log.

### 2.7. Rollback Can Also Generate WAL

A transaction that modifies pages and then executes ROLLBACK does not make the generated WAL bytes disappear. Rollback still records transaction/status records and any changes produced during the rollback process per PostgreSQL mechanics; the transaction's data changes do not become committed business state, yet the WAL stream has still advanced.

Therefore, you cannot run a large UPDATE and then ROLLBACK expecting the operation to be free in terms of WAL and I/O.

---

## 3. WAL Record: The Logging Unit

### 3.1. What Does a Record Describe?

A WAL record can describe an action requiring redo, for example:

- Inserting/updating/deleting a tuple in a heap.
- Modifying B-tree page structure.
- Changing transaction status.
- Modifying relation/database/tablespace metadata.
- Recording a checkpoint or WAL control event.
- Operations related to standby, replication origin, or logical decoding.

Each record is handled by the appropriate **resource manager** (RMGR). The resource manager knows how to interpret the record and perform its corresponding redo.

### 3.2. Conceptual Structure

A WAL record has a header and a payload. Conceptually, it looks like:

~~~text
+--------------------------------------------------+
| WAL record header                                |
| - total record length                            |
| - previous record pointer (xl_prev)              |
| - transaction ID (xid, if applicable)            |
| - resource manager ID                            |
| - info flags                                     |
| - CRC/checksum                                   |
+--------------------------------------------------+
| Block references / relation identifiers         |
| - tablespace/database/relation identity          |
| - fork and block number                          |
| - image metadata if present                      |
+--------------------------------------------------+
| Record-specific data                             |
| - heap/btree/transaction/control payload          |
+--------------------------------------------------+
~~~

This is a conceptual diagram, not a complete C ABI structure for manually parsing any PostgreSQL version. Specific fields, alignment, block reference layout, and format vary across sources and versions.

### 3.3. Header Fields

Fields commonly referenced in source/documentation:

- `xl_tot_len`: total record length.
- `xl_xid`: associated transaction ID when applicable.
- `xl_prev`: LSN of the previous WAL record in the WAL insertion-order chain.
- `xl_info`: info flags specific to the resource manager.
- `xl_rmid`: resource manager ID.
- `xl_crc`: checksum of the record according to format/version.

Not every field carries business meaning in every record. Some records do not belong to a specific transaction or carry an invalid xid.

### 3.4. Resource Manager (RMGR)

RMGR classifies records by the subsystem that handles them. Names/IDs can vary by version, but common groups include:

| Group | General Role |
|---|---|
| XLOG | Checkpoints, WAL control, and system events |
| XACT | Transaction commit/abort and related state |
| HEAP | Changes to heap tuples/pages |
| HEAP2 | Additional heap operations such as visibility/pruning/multi-insert |
| BTREE | Changes to B-tree indexes |
| SEQ | Sequence operations |
| SMGR | Storage manager/relation file operations |
| Database/Tablespace | Metadata related to databases/tablespaces |
| MULTIXACT | Multi-transaction state |
| STANDBY | Lock/standby-related records |
| Logical message/origin | Information related to logical decoding/replication |

The list above is illustrative. Do not hardcode RMGR numeric IDs or assume every version has the exact same list.

### 3.5. Block References

A record can reference one or more data blocks. Associated metadata can identify the relation, fork, and block number, along with delta payloads or full-page images when applicable.

An SQL UPDATE of one tuple may require records touching both heap and index; a B-tree page split can touch multiple blocks. Thus, the number of WAL records does not equal the number of rows.

### 3.6. Full-Page Image (FPI)

When `full_page_writes` is enabled, the first modification to a page after a checkpoint in applicable cases can write a full-page image into WAL. FPIs help protect against torn-page writes during crash scenarios.

An FPI can make a record much larger than a delta describing just a few changed bytes. WAL compression can shrink FPI size where supported, without sacrificing crash recovery protection.

### 3.7. CRC and Integrity Checks

Records carry a checksum/CRC to detect corruption within a WAL record. The specific mechanism and algorithm depend on version/build. A WAL checksum is not a cryptographic signature and does not replace network or archive storage encryption/authentication.

### 3.8. A Record Can Span Multiple WAL Pages

WAL records do not necessarily fit inside a single WAL page. A record can continue across a page boundary, and page header/continuation metadata enables reassembling the record. Therefore, LSN offsets and segment boundaries must follow WAL rules rather than assuming a record fits in one page.

---

## 4. WAL Page and WAL Segment

### 4.1. WAL Page

The WAL stream is organized into pages. In common PostgreSQL builds, a WAL page is typically 8 KiB; the page size depends on build-time configuration. Each page has a header containing control information such as the WAL page address/timeline and metadata needed to continue reading.

A WAL record can start on one page and continue onto the next.

### 4.2. What Is a WAL Segment?

A **WAL segment** is a physical file containing a contiguous range of the WAL stream. PostgreSQL creates, writes, and recycles segments sequentially, rather than creating a new file for every SQL statement or transaction.

Segment size is chosen at cluster initialization via `initdb` (`--wal-segsize` option on supported versions). The default is commonly 16 MiB, though a cluster can be initialized with a different size.

### 4.3. A Segment Is Not a Transaction

One segment can contain records from many transactions. One transaction can generate records spanning multiple segments. A segment can also contain records from uncommitted transactions alongside records from committed transactions.

You cannot look at a WAL segment and conclude it corresponds to a single transaction or a single table.

### 4.4. WAL File Naming

A segment filename in `pg_wal` is typically a 24-character hex string divided into three parts:

~~~text
TTTTTTTT LLLLLLLL SSSSSSSS
|        |        |
|        |        +-- segment number within log
|        +----------- log ID
+-------------------- timeline ID
~~~

Illustrative example:

~~~text
00000001000000000000000A
~~~

In this example filename:
- `00000001` is the timeline ID.
- `00000000` is the log ID.
- `0000000A` is the segment number.

The exact name reflects the timeline and position in the WAL numbering scheme. Do not rename files or infer LSNs by ad-hoc text parsing.

### 4.5. Segment Size and Calculating Segment Counts

If the segment size is 16 MiB and 160 MiB of WAL is generated, logically that corresponds to roughly 10 segments' worth of WAL. However, the actual number of files sitting in `pg_wal` does not have to be 10: PostgreSQL may keep recycled segments, retain extra ones for checkpoints/slots/archiving, or hold the current active segment.

### 4.6. WAL Rotation and Segment Switch

When the WAL stream reaches the end of a segment, PostgreSQL switches to the next segment. A segment switch can also be requested by certain operations/settings or administrative functions like `pg_switch_wal()`.

~~~sql
SELECT pg_switch_wal();
~~~

This function requests switching to the next WAL segment per server conditions. It is not a way to shrink `pg_wal`, nor should it be called continuously just to produce many smaller archive files.

### 4.7. Recycle and Reuse

Once a segment is no longer needed for recovery, replication, or archiving, PostgreSQL can recycle/reuse the segment instead of deleting and creating a new file. As a result:
- Increased WAL generation does not necessarily cause file counts to grow indefinitely.
- `pg_wal` directory size does not directly equal the WAL bytes generated over a given interval.
- Old segments can be reused for future positions.
- Retention by slots/archiving can prevent cleanup/recycling.

### 4.8. Archive Segment

When archiving is enabled, completed WAL segments can be sent to the archive destination via the archive command/provider. Archived segments are used for backup/PITR and follow their own retention policy. Never delete an archived segment while a backup chain still depends on it.

---

## 5. LSN: Address in the WAL Stream

### 5.1. What Is an LSN?

A **Log Sequence Number** identifies a byte position in the WAL stream. PostgreSQL typically displays LSNs in the format:

~~~text
HEX/HEX
~~~

Examples:

~~~text
0/16B6C50
0/16C4200
~~~

An LSN is a logical address—not a timestamp, transaction ID, row ID, or segment filename.

### 5.2. High/Low 32-Bit Format

The common `X/Y` representation corresponds to two 32-bit hex parts:
- The part before the slash is the high 32 bits.
- The part after the slash is the low 32 bits.

You can think of it as a 64-bit byte offset:

\[
LSN = (\text{high}_{32} \ll 32) + \text{low}_{32}
\]

This is the arithmetic meaning of the representation; when writing SQL, use the `pg_lsn` type and PostgreSQL functions instead of parsing text manually.

### 5.3. LSN Increases in WAL Insertion Order

On a given WAL timeline, new records are inserted at positions after earlier records in the stream. LSNs allow comparing WAL position order on that timeline.

This does **not** mean transaction IDs increase in commit order, nor that all records of a single transaction lie contiguously.

### 5.4. Calculating LSN Distance

~~~sql
SELECT pg_wal_lsn_diff(
    '0/16C4200'::pg_lsn,
    '0/16B6C50'::pg_lsn
) AS wal_bytes;
~~~

This function returns the byte distance between two LSNs (the first LSN minus the second LSN). The two values above are illustrative; use actual LSNs from your server when calculating.

Converting to MiB:

~~~sql
SELECT pg_wal_lsn_diff(
    '0/16C4200'::pg_lsn,
    '0/16B6C50'::pg_lsn
) / 1024 / 1024 AS wal_mib;
~~~

### 5.5. The pg_lsn Type

`pg_lsn` is PostgreSQL's built-in data type for LSNs. It supports proper comparisons and arithmetic; using this type avoids bugs from handling hex strings in application code.

Example:

~~~sql
SELECT
    '0/2000000'::pg_lsn > '0/1000000'::pg_lsn AS later_position;
~~~

### 5.6. LSN Is Not a Timestamp

A larger LSN means a later WAL position in that stream/timeline, not that a specific amount of wall-clock time has elapsed. WAL rates vary with workload; 100 MiB of WAL might be generated in one second or over several minutes.

To know elapsed time, combine timestamps, monitoring samples, and LSN deltas.

### 5.7. LSN Is Not a Transaction ID

A Transaction ID (XID) identifies transactions for MVCC, with wraparound semantics and special XIDs. An LSN addresses the WAL byte stream. A transaction can produce many WAL records at many LSNs, and concurrent transactions interleave their records.

### 5.8. LSN Is Not a Row Version

An LSN does not directly identify a row or tuple version. Page LSNs and WAL records support recovery/redo, whereas tuple identity/versioning requires heap/block/offset locations and MVCC metadata.

---

## 6. LSN Positions Provided by PostgreSQL

### 6.1. Current Insert LSN

~~~sql
SELECT pg_current_wal_insert_lsn();
~~~

The current WAL insertion position from the server's perspective. It can lead write/flush positions because WAL has been inserted into buffers without yet being written/flushed.

### 6.2. Current Write LSN

~~~sql
SELECT pg_current_wal_lsn();
~~~

The function commonly used to obtain the written WAL position per PostgreSQL semantics. Do not call it the "flush LSN" when comparing it against the separate flush function.

### 6.3. Current Flush LSN

~~~sql
SELECT pg_current_wal_flush_lsn();
~~~

The WAL position flushed according to server state. This is a key milestone when tracking durability/replication progress, though it should not be naively interpreted as meaning every transaction before that LSN committed; the WAL stream also contains records from other transactions and non-commit events.

### 6.4. Comparing the Three Positions

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

Typically:
- Insert position can be ahead of write position.
- Write position can be ahead of flush position.
- When the system is idle or the WAL writer/backends have synced, the positions can be close or identical.

Do not treat small or large differences as errors without understanding load, write/flush behavior, and sampling timing.

### 6.5. Insert, Write, and Flush Differ

| Position | Meaning |
|---|---|
| Insert | Record has been inserted into WAL buffers/stream position |
| Write | WAL bytes have been written to OS/file layer per server semantics |
| Flush | WAL has been flushed along the server's durability path |

`write` does not mean data pages were written; WAL `flush` does not mean all dirty data pages were flushed.

### 6.6. Is This the Current Session's LSN?

The current WAL LSN functions reflect the cluster-wide WAL stream, not just WAL bytes from the current session. When multiple transactions run concurrently, the LSN delta between two measurements includes cluster-wide activity.

### 6.7. Measuring WAL Delta in a Workload

Simple pattern:

~~~sql
SELECT pg_current_wal_lsn() AS before_lsn;

-- Run the defined workload and COMMIT.

SELECT pg_current_wal_lsn() AS after_lsn;
~~~

Then calculate:

~~~sql
SELECT pg_wal_lsn_diff(
    'AFTER_LSN'::pg_lsn,
    'BEFORE_LSN'::pg_lsn
);
~~~

Replace the placeholders with actual LSNs. For cleaner attribution, measure in an isolated environment or a quiet window with minimal concurrent writes. The result is the WAL stream distance, which does not by itself prove how many bytes a single SQL statement produced.

### 6.8. LSN and Segment Filename

You can ask PostgreSQL for the segment name corresponding to an LSN:

~~~sql
SELECT pg_walfile_name('0/16C4200'::pg_lsn);
~~~

And view both the segment name and byte offset:

~~~sql
SELECT *
FROM pg_walfile_name_offset('0/16C4200'::pg_lsn);
~~~

The output depends on segment size/timeline and the actual LSN. This is much safer than deriving filenames manually from hex strings.

---

## 7. Page LSN and Its Relationship to Data Pages

### 7.1. What Is a Page LSN?

A PostgreSQL data page has a header containing `pd_lsn` (page LSN): the WAL position of the last WAL record applied to that page under the storage/recovery mechanism.

On a heap or index page:
- A WAL record can modify the page.
- When the change is applied, the page LSN is updated to the relevant record's LSN.
- During recovery redo, the server can compare page LSN with record LSN to determine whether the page already reflects that change.

### 7.2. Why Is Page LSN Useful?

Suppose a crash occurs after a page was written to disk, while WAL still holds the corresponding record within the redo range. Recovery must avoid reapplying certain changes already present on the page. Page LSN is a key piece of information used to determine redo conditions.

Exact redo decisions depend on record type and resource manager; not every record is governed by one simplistic comparison alone.

### 7.3. Page LSN Is Not Commit LSN

A single page can hold updates from multiple transactions. Page LSN represents the last WAL position applied to the page, not the last transaction commit of every row on the page.

### 7.4. One Transaction Can Modify Multiple Pages

Updating one row can touch a heap page and index pages. Those pages may have different page LSNs. The commit record has its own LSN; there is no single page LSN representing a transaction.

### 7.5. Page LSN and Torn-Page Protection

Full-page images written to WAL after a checkpoint in applicable cases let recovery restore a page if a data page suffered a torn write. Page LSN and FPI are complementary pieces of the WAL/recovery mechanism; do not disable `full_page_writes` to save log space without understanding the risk.

---

## 8. Change Ordering: Record Order, Transaction Order, and Commit Order

### 8.1. A Single WAL Stream Has a Global Order

On a single timeline, WAL records are placed into the stream in LSN order. If record A is at a lower LSN than record B, A appears before B in the WAL stream.

However, transactions can execute concurrently. Their records can **interleave** in the stream.

### 8.2. Example of Two Interleaved Transactions

~~~text
WAL LSN order:

LSN 100  T1: UPDATE orders row A
LSN 200  T2: UPDATE inventory row B
LSN 300  T1: UPDATE audit row
LSN 400  T2: UPDATE inventory row C
LSN 500  T2: COMMIT
LSN 600  T1: COMMIT
~~~

This illustrative diagram shows that T1 does not occupy a single contiguous region. Transaction T2 can write records between T1's records. In this example, the commit order is T2 before T1 even though T1 started earlier.

### 8.3. Start Order Does Not Equal Commit Order

A transaction that starts earlier may finish later. XID assignment order is likewise not a general ordering mechanism for commits. To determine where a transaction committed in WAL, you need commit records and transaction status, not XIDs alone.

### 8.4. Commit Record

When a transaction commits, PostgreSQL writes a commit-related record into WAL. The commit record is the WAL proof of transaction completion; COMMIT is acknowledged to the client per the durability policy after the corresponding flush/replication conditions are met.

A transaction may have generated many WAL records before committing; the commit record does not bundle all changes into one single record.

### 8.5. Can a Transaction Generate No WAL Data Records?

A read-only transaction typically generates no heap/index modification records; there may still be activity/session/transaction-related records depending on circumstances. Do not assume every transaction generates the same amount of WAL.

### 8.6. A Transaction Does Not Have a Single LSN for All Changes

A transaction has:
- Multiple WAL records for its operations.
- Potential interleaving with records from other transactions.
- An associated commit/abort record.
- A commit LSN that may matter for replication or commit ordering.

Therefore, when referring to "a transaction's LSN," clarify whether you mean a specific record, its commit LSN, or an application-chosen snapshot/watermark position.

### 8.7. WAL Order Does Not Replace Isolation Semantics

WAL is a persistence, recovery, and replication mechanism. Record ordering does not replace transaction isolation, row locks, MVCC snapshots, or serialization rules. Two transactions can have WAL records in one order while SQL visibility across concurrent sessions still follows MVCC and isolation rules.

### 8.8. One SQL Statement Can Generate Records at Multiple Points

Operations supporting transaction execution, commit, cleanup, and control can write records at multiple points during a statement/transaction lifecycle. Do not assume all WAL records of an SQL statement lie cleanly in one block before a fixed marker, especially with triggers, indexes, concurrent transactions, and commit processing.

---

## 9. Ordering of Write, Flush, and COMMIT

### 9.1. Write Differs from Flush

- **Write:** WAL data is sent to the OS/file layer.
- **Flush:** ensures WAL reaches the durability level requested by PostgreSQL via the sync method/storage stack.
- **COMMIT acknowledgement:** the server returns commit success to the client per synchronous_commit and replication configuration.

Do not conflate these three milestones.

### 9.2. Durability with Default synchronous_commit

With standard durability settings, PostgreSQL does not confirm COMMIT before the WAL needed for the transaction is flushed to persistent storage per policy. Data pages can be written later; crash recovery will redo them.

### 9.3. synchronous_commit=off

This setting lets the server acknowledge a commit before its corresponding WAL is flushed, reducing latency in some workloads while accepting the risk of losing recently acknowledged transactions if the server crashes. WAL is still generated; this setting does not disable WAL.

### 9.4. Synchronous Replication

When a synchronous standby is configured, synchronous_commit modes affect what acknowledgement is waited for (local flush, remote write/flush/apply depending on mode and version). Depending on configuration, commit latency may depend on the standby.

Do not assume a successful COMMIT at the client means every replica has replayed the transaction, unless the policy/setting specifically requires and confirms that level.

### 9.5. Group Commit

Multiple transactions can wait together for a flush; PostgreSQL can flush WAL once for a group of commits. This is **group commit**, reducing storage syncs compared to each transaction flushing individually.

Group commit does not merge transactions into one shared transaction and does not alter their atomicity.

### 9.6. WAL Writer and Backend Flush

WAL can be written/flushed by backend processes or the WAL writer depending on internal mechanisms and timing. Parameters such as wal_writer_delay, wal_writer_flush_after, wal_buffers, and wal_sync_method affect behavior; tuning them requires benchmarking and understanding durability.

### 9.7. Lost Response After COMMIT

If the server commits and flushes successfully but the connection drops before the client receives the response, the client may not know whether the transaction committed. This is an **unknown commit outcome**. Retrying business operations requires idempotency keys, unique constraints, or reconciliation—you cannot rely solely on socket errors.

---

## 10. Checkpoint and Redo Start Point

### 10.1. What Does a Checkpoint Do?

A checkpoint is an event where PostgreSQL ensures required dirty pages prior to the checkpoint point are written to data files according to the checkpoint mechanism. The checkpoint record and control information record the state needed for crash recovery.

After a crash, PostgreSQL does not need to replay WAL from the beginning of database history; it begins redo from an appropriate point determined by the checkpoint.

### 10.2. Checkpoint Record

WAL contains XLOG resource manager records related to checkpoints and control state. Checkpoint metadata stores information such as the redo pointer and required state. Internal structure depends on version; do not parse it with hardcoded offsets.

### 10.3. Redo LSN

The redo pointer indicates the WAL position from which recovery must start considering redo. It is not necessarily the last WAL position before a crash, nor does it necessarily match the checkpoint record's LSN.

### 10.4. A Checkpoint Is Not a COMMIT

- COMMIT marks transaction completion.
- A checkpoint sets a recovery marker and syncs dirty data pages.
- A transaction can commit before the next checkpoint.
- A checkpoint can cover data pages modified by many committed transactions as well as some buffered changes per recovery rules.

### 10.5. A Checkpoint Does Not Always Delete Old WAL Segments Immediately

Old WAL segments may still be needed for:
- Completing archiving.
- Standbys or replication slots.
- wal_keep_size or retention settings.
- Recovery/backup policies.
- Other internal conditions.

A checkpoint may render some WAL unnecessary for local crash recovery, but it does not guarantee immediate segment deletion.

### 10.6. Checkpoint Frequency and WAL Volume

Frequent checkpoints can increase I/O bursts and post-checkpoint full-page image volume. checkpoint_timeout, max_wal_size, checkpoint_completion_target, and workload all interact. Do not raise or lower parameters arbitrarily based on a single observation of many segments.

### 10.7. Checkpoints and full_page_writes

With full_page_writes=on, the first time a page is modified after a checkpoint in applicable cases may require an FPI. This protects recovery, though it can sharply raise WAL bytes right after a checkpoint. Cutting FPIs by turning off full_page_writes is a dangerous trade-off, not a default optimization.

### 10.8. Inspecting Checkpoint Stats

In newer PostgreSQL versions, checkpoint metrics appear in pg_stat_checkpointer; in earlier versions, some metrics live in pg_stat_bgwriter. Check the right view and schema for your major version.

---

## 11. Timeline: WAL History After Failover

### 11.1. Why Do Timelines Exist?

When a standby is promoted to primary, WAL write history can branch away from the old primary. PostgreSQL uses a **timeline ID** to distinguish history branches.

### 11.2. Timeline History File

After a timeline switch, a history file describes the lineage and fork point of the new timeline. This file is crucial when restoring/performing PITR or attaching standbys along a timeline.

### 11.3. LSNs Can Overlap Across Timelines

An LSN only has full meaning within a timeline/history context. Two different timelines can have the same numeric LSN values while representing completely different histories after the fork point.

Therefore, in HA/recovery, never compare LSNs in isolation while ignoring timelines.

### 11.4. WAL Segment Filenames Contain the Timeline ID

The leading portion of a WAL segment filename represents the timeline ID. Upon promotion, new timeline segment names reflect the new history branch; segments from the prior timeline may still be needed in the recovery chain.

### 11.5. Timeline Is Not Database ID

A timeline distinguishes WAL history branches, not database OIDs, cluster names, or transaction IDs. One PostgreSQL cluster can host many databases while sharing the same WAL stream and timeline.

---

## 12. Streaming Replication and LSN Positions

### 12.1. Primary Sends WAL to Standby

Physical streaming replication sends the WAL stream from primary to standby. The standby can:
1. Receive WAL bytes.
2. Write WAL to local WAL files.
3. Flush WAL per state.
4. Replay WAL to apply changes to data files.

### 12.2. LSNs in pg_stat_replication

On the primary:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

These positions are generally interpreted as:
- sent_lsn: position the WAL sender has sent.
- write_lsn: position the standby has written.
- flush_lsn: position the standby has flushed.
- replay_lsn: position the standby has replayed.

Exact semantics, counters, and lag fields vary by version; consult server documentation.

### 12.3. Byte Lag

~~~sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS approximate_bytes_behind
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
~~~

This is an approximate WAL stream distance between the primary's current position and the standby's replay position. It does not directly mean "number of rows behind" or exact wall-clock time.

### 12.4. Standby Receives Without Replaying

If write_lsn/flush_lsn advance quickly while replay_lsn stalls, network/receive may be fine while apply/replay is slow. Inspect standby CPU/I/O, long-running queries/hot standby conflicts, WAL record processing, and storage.

### 12.5. Standby Receives Slowly

If sent_lsn pulls far ahead of write_lsn, there may be a network, receiver, or storage bottleneck. Check the network, replication connection, standby WAL write latency, and resource contention.

### 12.6. Standby Query

On the standby:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_commit_time;
~~~

The last replay commit timestamp can be NULL or stale when the primary is not generating new transactions. Combine LSNs, heartbeats, and workload expectations to measure lag accurately.

### 12.7. WAL Streaming Is Not a Logical Row Stream

Physical replication ships WAL so the standby reconstructs the corresponding physical state. It does not ship SQL statements or JSON events at the business level. Logical replication/decoding interprets row changes via a different mechanism with separate semantics.

---

## 13. WAL Archive and the Recovery Chain

### 13.1. Archiving WAL Segments

When a WAL segment is completed and eligible for archiving, PostgreSQL invokes the archive mechanism to store the segment in long-term storage per configuration. Archives are typically paired with base backups for PITR.

### 13.2. Archiving Is Not Arbitrary Copying of Live Segments

A segment currently being written should not be manually copied or treated as a complete archive file. PostgreSQL manages segment switching and archiving so the archive receives a complete segment with verifiable semantics.

### 13.3. pg_stat_archiver

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

These counters reflect archiver status, not the entire archive inventory. Combine them with destination logs, backup metadata, and restore testing.

### 13.4. Archive Command Failures

If archiving fails, WAL can remain in pg_wal for retries and recovery safety. Disk usage can climb. Never delete unarchived segments just to free disk space.

### 13.5. PITR Needs a Valid Chain

To recover to a point in time, you need a base backup and a matching continuous WAL chain from the backup to the target. Missing a single required segment can halt recovery before the target. Backup success should never be judged solely by seeing archive files appear; you must verify restorability.

---

## 14. Inspecting WAL with SQL and Tools

### 14.1. Current LSN Positions

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

These are cluster-wide positions. The role needs appropriate privileges to call these functions; behavior on a standby differs from a primary.

### 14.2. WAL Filename

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_segment;
~~~

The filename function maps an LSN to a segment name according to segment size and timeline. It does not tell you whether the segment has been archived.

### 14.3. LSN and Offset Within a Segment

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

The result returns the segment filename and matching byte offset. Use it to locate the segment holding an LSN, rather than guessing paths outside the configured WAL directory.

### 14.4. WAL Statistics

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

Views and columns can differ by version. Counters are server-wide and can be reset; to compute deltas, capture stats_reset and take two properly timed samples.

### 14.5. pg_waldump

pg_waldump is a command-line utility that reads and displays WAL records in WAL segments, useful for low-level analysis. Names, options, and filtering capabilities depend on version.

General example:

~~~bash
pg_waldump --path=/path/to/pg_wal --start=0/16B6C50 --end=0/16C4200
~~~

The path and options above are illustrative only. Use a binary compatible with your cluster's PostgreSQL version and valid WAL files. This tool is not an SQL query interface and does not replace recovery or backup verification.

### 14.6. pg_walinspect

On supported versions, the pg_walinspect extension provides SQL functions to inspect WAL records and statistics. Common functions in modern versions may include:
- pg_get_wal_record_info(lsn)
- pg_get_wal_records_info(start_lsn, end_lsn)
- pg_get_wal_stats(start_lsn, end_lsn)
- pg_get_wal_stats_till_end_of_wal(start_lsn)

Function names, output columns, required privileges, and extension availability depend on version. Install extensions only per DBA policy, and never grant broad WAL inspection rights to application roles.

### 14.7. Do Not Dump WAL Indiscriminately

WAL record inspection can expose sensitive information in page images and record payloads, generate I/O and CPU load, and produce massive output. Limit LSN ranges, store outputs securely, redact sensitive data, and restrict access to investigators who need it.

---

## 15. WAL Ordering in a Concrete Example

### 15.1. Create the Lab Table

~~~sql
CREATE SCHEMA IF NOT EXISTS wal_order_lab;

CREATE TABLE wal_order_lab.accounts (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO wal_order_lab.accounts(account_id,balance)
VALUES (1,1000.00),(2,500.00);
~~~

This is a lab table. The SQL statements above generate multiple internal operations and WAL records; you cannot assume each inserted row maps to exactly one record.

### 15.2. Measure the Before Marker

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS before_insert,
    pg_current_wal_lsn() AS before_write,
    pg_current_wal_flush_lsn() AS before_flush;
~~~

Record the actual output.

### 15.3. One Transaction Updating Two Accounts

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-100.00
WHERE account_id=1;

UPDATE wal_order_lab.accounts
SET balance=balance+100.00
WHERE account_id=2;

COMMIT;
~~~

The transaction executes two row updates. Its WAL records can include heap, index, and transaction records along with related internal operations.

### 15.4. Measure the After Marker

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS after_insert,
    pg_current_wal_lsn() AS after_write,
    pg_current_wal_flush_lsn() AS after_flush;
~~~

Compute the distance using actual LSNs:

~~~sql
SELECT pg_wal_lsn_diff(
    'AFTER_WRITE_LSN'::pg_lsn,
    'BEFORE_WRITE_LSN'::pg_lsn
) AS bytes_between_samples;
~~~

If another workload writes WAL concurrently, the delta includes those records. You cannot use it to claim exactly how many bytes the accounts transaction alone produced.

### 15.5. Observe Transaction Consistency

~~~sql
SELECT account_id,balance
FROM wal_order_lab.accounts
ORDER BY account_id;
~~~

After COMMIT, the total balance of the two rows remains 1,500.00. Both UPDATEs committed atomically in one transaction; readers never observe a half-committed state under MVCC.

### 15.6. Rollback Lab

If you want to test from the start:

~~~sql
BEGIN;
UPDATE wal_order_lab.accounts
SET balance=balance-10
WHERE account_id=1;
ROLLBACK;
~~~

The final data does not retain the change, yet WAL can still advance. Do not treat rollback as erasing WAL records.

---

## 16. Segment Rotation and Observing Filenames

### 16.1. View the Current Segment

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
~~~

### 16.2. Request a Switch in the Lab

~~~sql
SELECT pg_switch_wal();
~~~

The output is the LSN associated with the switch; exact behavior depends on current server state. Run only when needed for lab/maintenance; calling it repeatedly can increase segment and archive churn.

### 16.3. Read a Segment Name

~~~sql
SELECT pg_walfile_name('0/3000000'::pg_lsn);
~~~

This hypothetical LSN can map to different segments depending on timeline, segment size, and current state; use actual current LSNs in your lab.

### 16.4. Checking Segment Size

PostgreSQL provides pg_size_bytes to parse config size strings, but there is no single portable SQL function across all versions and providers to retrieve segment size in every context. Segment size is a cluster/initdb property; it can be checked via control data, appropriate tools, or deployment metadata. Never assume every cluster uses 16 MiB.

### 16.5. Why Does pg_wal Hold Many Old Files?

Segments may be retained because:
- Not yet eligible for recycling.
- Needed for archiving.
- A replication slot holds an old restart LSN.
- A standby is lagging.
- wal_keep_size or retention settings.
- Needed for checkpoint/recovery.
- PostgreSQL keeps preallocated/recycled segments for reuse.

Inspect slots, archiver, replication, and disk; never delete files manually.

---

## 17. Change Ordering and Transaction Atomicity

### 17.1. A Single Transaction with Multiple Statements

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-100
WHERE account_id=1;

UPDATE wal_order_lab.accounts
SET balance=balance+100
WHERE account_id=2;

COMMIT;
~~~

WAL records are generated across both UPDATEs and transaction completion. When COMMIT succeeds per durability policy, both changes complete together as one transaction.

### 17.2. Failed Transaction

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-100
WHERE account_id=1;

SELECT 1/0;

UPDATE wal_order_lab.accounts
SET balance=balance+100
WHERE account_id=2;

COMMIT;
~~~

After division_by_zero, the transaction enters an aborted state; the second UPDATE and normal COMMIT cannot succeed as intended. The caller must ROLLBACK. WAL records generated before the error may still exist; data changes are not committed.

### 17.3. Savepoint

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-10
WHERE account_id=1;

SAVEPOINT optional_step;

-- If an operation within the savepoint scope fails:
ROLLBACK TO SAVEPOINT optional_step;

COMMIT;
~~~

A savepoint allows partial rollback within a transaction, but does not create an independently committed transaction. Related records remain in WAL; the outer transaction still commits or aborts as one unit.

### 17.4. Commit Order and Visibility

A transaction becomes visible to other transactions under MVCC only after it commits. WAL record order supports recovery and replication, while visibility also depends on snapshots and isolation levels.

### 17.5. Do Not Infer Commit from Page Flush

A flushed data page does not by itself prove a transaction committed. A page can contain tuples from an uncommitted transaction or multiple tuples from different transactions. Commit status is determined via transaction state/WAL and MVCC, not by page LSN alone.

---

## 18. Frequently Asked Questions

### 18.1. Does One WAL Segment Hold One Transaction?

No. A segment holds a range of the WAL stream; many transactions can write records into the same segment, and one transaction can span multiple segments.

### 18.2. Does One WAL Record Equal One Row?

No. A record can describe page-level, index, transaction, or control changes. One row update can produce multiple records, and one record can carry changes affecting multiple items or blocks.

### 18.3. Does an Increasing LSN Mean a New Transaction Committed?

No. LSN advances whenever WAL records are inserted; they may belong to uncommitted transactions, background operations, or control records. A commit record is a distinct event.

### 18.4. Does Flush LSN Equal Commit LSN?

No. Flush LSN is the WAL position flushed to disk; a transaction's commit LSN is the position of its specific commit record. The flush position can advance past many records and transactions.

### 18.5. Is It Safe If COMMIT Succeeds Before Data Pages Are Written?

Under standard durability policy, the required WAL has been flushed; crash recovery redo can restore the page changes. Settings like synchronous_commit=off change the guarantee at acknowledgement time.

### 18.6. Can an Archived WAL Segment Be Deleted Immediately?

Not necessarily. PostgreSQL manages local lifecycle/reuse; archived copies for PITR must be retained according to backup policy. Never manually delete files in pg_wal or the archive destination.

### 18.7. Is an LSN Like a Timestamp?

No. An LSN is a byte position. You need timestamps and metrics to estimate WAL rate.

### 18.8. Do XIDs Increase Together with LSNs?

There is no simple guarantee that XIDs increase monotonically with all LSNs or commit order. XID assignment, transaction execution, and commit each follow distinct lifecycles.

### 18.9. Does WAL Contain Only Data Modifications?

No. It also contains transaction, checkpoint, storage/catalog, and control records needed for recovery and replication.

### 18.10. Once a Replica Receives WAL, Can Queries Immediately See the Data?

No. WAL may be received, written, and flushed without yet being replayed. Query visibility on a standby depends on replay progress and recovery state.

---

## 19. Checklist for Reading WAL and Investigating Incidents

### 19.1. When Interpreting an LSN

- [ ] Identify whether the LSN is insert, write, flush, receive, replay, or commit LSN.
- [ ] Identify whether you are inspecting the primary or a standby.
- [ ] Note the timeline/history when a failover has occurred.
- [ ] Use pg_lsn and pg_wal_lsn_diff rather than manual string parsing.
- [ ] Remember that LSN deltas are cluster-wide when concurrent workloads exist.

### 19.2. When Inspecting Segments

- [ ] Verify the cluster's actual segment size.
- [ ] Parse filenames by timeline/log/segment numbering.
- [ ] Use pg_walfile_name()/pg_walfile_name_offset() when appropriate.
- [ ] Check archive/slot/replica retention.
- [ ] Never arbitrarily rename, delete, or copy active segments.

### 19.3. When Interpreting Record Order

- [ ] Separate record order from transaction start and commit order.
- [ ] Locate commit/abort records when tools allow.
- [ ] Remember records from concurrent transactions can interleave.
- [ ] Do not infer business row identity from an LSN.
- [ ] Use version-compatible tools when decoding records.

### 19.4. When Evaluating Durability

- [ ] Check synchronous_commit.
- [ ] Check synchronous replication policy if configured.
- [ ] Distinguish WAL write from WAL flush.
- [ ] Distinguish WAL flush from data-page flush.
- [ ] Check fsync, full_page_writes, and storage assumptions.
- [ ] Handle unknown commit outcomes with idempotency/reconciliation.

### 19.5. When Evaluating Checkpoints and Recovery

- [ ] Identify checkpoint/redo LSN.
- [ ] Check checkpoint frequency and WAL growth.
- [ ] Inspect FPI volume.
- [ ] Verify archive continuity/PITR.
- [ ] Never delete segments needed for recovery or standbys.

---

## 20. Official References

When working with a specific major version, prefer the documentation for that exact version:

- [PostgreSQL — Write-Ahead Logging (WAL)](https://www.postgresql.org/docs/current/wal.html): WAL principles and crash recovery.
- [PostgreSQL — WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html): WAL records/pages/segments and LSNs.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoint and WAL configuration.
- [PostgreSQL — WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): durability, fsync, and write-ahead rules.
- [PostgreSQL — WAL Functions](https://www.postgresql.org/docs/current/functions-admin.html): LSN functions, WAL file naming, and administrative functions.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_wal, replication, and checkpoint statistics.
- [PostgreSQL — Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): send/write/flush/replay and standby behavior.
- [PostgreSQL — Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): WAL archiving and recovery.
- [PostgreSQL — pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html): reading WAL records from the command line.
- [PostgreSQL — pg_walinspect](https://www.postgresql.org/docs/current/pgwalinspect.html): inspecting WAL via SQL extension on supported versions.

Pages under /current/ can change as new PostgreSQL versions are released. The WAL binary format is an implementation detail; if building long-lived parsers or analysis tools, make them version-aware and base them on the source/docs of the exact release.

---

## 21. Summary

**WAL is an ordered binary stream addressed by LSN and physically stored in segments.** Understanding records, segments, LSNs, and change ordering explains crash recovery, COMMIT durability, checkpoints, and streaming replication.

Key points to remember:

1. **Write-ahead rule:** required WAL must be durably written before the corresponding data page is durably written.
2. **A WAL record is not an SQL statement or row:** one statement can generate many records, and one record can affect multiple blocks.
3. **WAL page and segment are distinct organizational layers:** a segment is a physical file containing many pages; records can cross page/segment boundaries.
4. **An LSN is a byte position in the WAL stream:** not a timestamp, XID, or row ID.
5. **LSNs increase in record insertion order:** records from multiple transactions can interleave; start order does not equal commit order.
6. **A transaction produces multiple WAL records:** the commit record is a separate event, not a bundle of all changes into one record.
7. **Insert, write, and flush are distinct milestones:** write is not flush; flushing WAL does not mean data pages are flushed.
8. **Commit acknowledgement depends on durability settings:** synchronous_commit and synchronous replication govern what must be waited for.
9. **Page LSN helps recovery decide redo:** it is not a commit LSN or transaction identity.
10. **Checkpoints establish a redo starting point:** a checkpoint is not a COMMIT and does not guarantee old WAL segments are immediately deleted.
11. **Segment names encode timeline/log/segment fields:** segment size depends on cluster initialization; never hardcode 16 MiB for all clusters.
12. **Timelines separate history after failover:** LSNs must be interpreted within their timeline context.
13. **Replication tracks receive/write/flush/replay progress:** receiving WAL does not mean the standby has replayed it for queries.
14. **Archives and slots can retain WAL:** never delete files manually to free disk space.
15. **Inspect the right milestone:** use current insert/write/flush LSNs, pg_stat_replication, pg_stat_wal, pg_walfile_name, and version-compatible tools.
16. **Unknown COMMIT outcomes require idempotency:** losing a response does not prove the transaction rolled back.

Mental workflow: **identify the timeline → choose the LSN type to inspect → map to the corresponding record/segment → separate insert/write/flush → locate commit/checkpoint/redo context → compare replica receive/replay and archive state → perform recovery via PostgreSQL metadata, never by editing WAL files manually**.

---

## 22. Inside WAL Pages and Segment Headers

### 22.1. Page Header

Each WAL page has a header enabling PostgreSQL to determine:
- Where in the stream the WAL page starts.
- Which timeline is in use.
- What page flags/metadata apply.
- Whether there is a record continuation from the previous page.

Internal structures commonly referenced in PostgreSQL source include the standard page header and the long page header. The long header includes additional fields such as the system identifier, WAL segment size, and WAL block size in appropriate contexts.

These are implementation details, not a stable API for applications to read using fixed offsets.

### 22.2. WAL Block Size and Segment Size

Distinguish between:
- **WAL block/page size:** the page unit within the WAL stream, commonly 8 KiB in standard PostgreSQL builds.
- **WAL segment size:** the size of each segment file, commonly 16 MiB by default but chosen at initdb.
- **Database block size:** the page size of heap/index files, commonly 8 KiB in standard builds.

These sizes are related but are not the same concept. Do not use database block size to infer segment size.

### 22.3. Continuation Records

If a record exceeds the remaining space on a WAL page, the rest of the record continues onto the next page. The continuation page header stores metadata telling the reader how many bytes remain from the prior record.

A record can also cross a segment boundary. Therefore, pg_waldump and WAL readers must traverse pages and segments in order rather than parsing each file as an isolated log.

### 22.4. Alignment and Padding

WAL records follow internal alignment and padding rules. Logical payload length does not necessarily equal the LSN distance to the next record once alignment and page headers are factored in. Use PostgreSQL types and tools for analysis; do not manually add record lengths to predict the next LSN.

### 22.5. Forks and Block References

A relation can have different forks such as main, FSM, VM, and init in relevant contexts. A WAL block reference can specify the relation, fork, and block involved. An operation does not modify only the main fork; visibility, free-space, and storage operations can produce their own records or involve different resource managers.

---

## 23. Common Types of WAL Records

### 23.1. Heap Records

Records from the heap resource manager describe operations such as insert, update, delete, clean/prune, or multi-insert depending on type. A bulk insert may use a record supporting multiple tuples on the same page rather than one simple record per row.

### 23.2. B-Tree Records

B-tree indexes maintain page, sibling, and parent structures. A single insert might just add an index tuple, whereas a page split or structural maintenance operation can emit records touching multiple pages. This is why an INSERT into an indexed table can generate far more WAL than just the heap row itself.

### 23.3. Transaction Records

The XACT resource manager logs transaction events such as commit, abort, and prepared transactions per applicable protocols. A commit record contains metadata required for transaction status and recovery; it is not a copy of the SQL statement.

### 23.4. Checkpoint/Control Records

The XLOG resource manager includes control records such as checkpoints and other WAL-level events. These records tell recovery where to start and what state is needed.

### 23.5. Sequence Records

Sequence changes follow their own semantics; do not infer sequence state merely from a table INSERT. Allocating nextval and rolling back a transaction behave differently from ordinary DML.

### 23.6. Logical Messages/Origins

WAL can carry logical messages and replication origin metadata to support logical decoding/replication. This does not mean every logical change is stored as a verbatim SQL statement or complete JSON row.

### 23.7. Relation/Database Metadata

Creating or dropping relations, databases, tablespaces, and storage files can generate WAL records so recovery and replication keep metadata consistent.

### 23.8. Do Not Map Each RMGR to a Single Business Operation

An INSERT into orders can emit HEAP and BTREE records alongside transaction records, while triggers can generate additional changes. RMGR is an internal classification for redo, not an application event taxonomy.

---

## 24. WAL, wal_level, and Types of Logged Information

### 24.1. WAL Always Exists for Crash Recovery

PostgreSQL always requires WAL to protect crash recovery. wal_level controls how much extra information is logged for capabilities like replication and logical decoding; it is not an off switch for WAL.

### 24.2. Common Levels

Common levels:
- **minimal:** logs enough information for crash recovery within usage constraints; unsuitable for normal physical replication or PITR.
- **replica:** logs information needed for streaming replication and archive/PITR per configuration.
- **logical:** adds information needed for logical decoding and logical replication.

Exact capabilities, lowest allowed level, and restart requirements depend on PostgreSQL version. Check docs and live config before changing it.

### 24.3. Do Not Lower wal_level to Fix Disk Full

Lowering wal_level can break replication, archiving, or logical decoding that the system relies on, and may require a restart. It does not clear the slot or archive retention holding WAL. Investigate consumers, the archiver, and disk usage first.

### 24.4. UNLOGGED Relations

Data in unlogged tables is not WAL-logged like logged tables and is not replicated to physical standbys in the normal way. After a crash, unlogged relation contents may be reset or truncated per PostgreSQL semantics. Do not use unlogged tables for unique authoritative data or checkpoints requiring durability.

### 24.5. Temporary Relations

Temporary tables have session-scoped lifecycles and special logging behavior. Do not use them as evidence that SQL operations produce minimal WAL compared to logged permanent tables. When analyzing WAL volume, know which relation types the workload touches.

---

## 25. Checkpoint Metadata and pg_control

### 25.1. Reading Checkpoint Metadata

PostgreSQL versions support the pg_control_checkpoint() function to inspect checkpoint/control info from the control file. Example:

~~~sql
SELECT *
FROM pg_control_checkpoint();
~~~

The output can include checkpoint LSN, redo LSN, timeline IDs, checkpoint time, next XID, and other metadata depending on version. This is administrative/recovery information, not a standard business query view.

### 25.2. Access Privileges

Functions reading control data typically require appropriate administrative or monitoring privileges. Never grant superuser to an application just to populate a dashboard. Use a DBA/monitor role following least privilege and verify version compatibility.

### 25.3. pg_controldata

pg_controldata is a command-line utility that reads control information from the data directory. It can display WAL block size, WAL segment size, checkpoint/redo information, and other control fields depending on version.

Run it with the matching PostgreSQL binary, data directory, and required permissions. This is a read-only diagnostic tool; never edit the control file with it.

### 25.4. Checkpoint LSN and Redo LSN

The checkpoint record and redo pointer do not necessarily share the same LSN. Checkpoint metadata records an appropriate recovery point; the redo pointer identifies the WAL position where recovery must begin evaluating redo.

### 25.5. Checkpoint Time Is Not Transaction Commit Time

Checkpoint time is when checkpoint metadata was written/completed per engine semantics. It does not tell you when a specific transaction committed. Querying commit timestamps requires other mechanisms such as commit timestamp tracking if enabled and available; do not infer it from checkpoint timestamps.

---

## 26. pg_waldump and pg_walinspect: Practicing Record Inspection

### 26.1. When Do You Need to Read Records?

WAL inspection tools are useful for:
- Investigating which record types or resource managers generate WAL.
- Comparing WAL before and after a lab workload.
- Checking a record range during replication/recovery analysis.
- Understanding FPI volume and block references.
- Learning how an SQL operation maps to WAL records.

They are not replacements for backup/restore tools or a business auditing API.

### 26.2. pg_waldump

General example:

~~~bash
pg_waldump --path=/path/to/pg_wal --start=0/16B6C50 --end=0/16C4200
~~~

Common options include:
- --path or -p: directory containing WAL segment files.
- --start or -s: starting LSN.
- --end or -e: ending LSN.
- --rmgr or -r: filter by resource manager in supported versions.
- --xid or -x: filter by transaction ID where supported.
- --stats: display statistics by record or resource manager in supported versions.

Check exact syntax and options with pg_waldump --help for your version. Contiguous segment files and read permissions may be required. Never mix a newer binary version with an older WAL format without verifying compatibility.

### 26.3. Reading an Output Line

Output can contain:
- Record start LSN.
- Transaction ID.
- Resource manager.
- Record type.
- Record length.
- Previous record LSN.
- Record description and block references.

Field names and formatting vary by version. This is low-level internal data, not SQL text.

### 26.4. The pg_walinspect Extension

On PostgreSQL versions supporting the extension, it can be installed in an appropriate database:

~~~sql
CREATE EXTENSION pg_walinspect;
~~~

The extension provides functions to inspect WAL ranges. Installation and privileges must follow DBA policy; do not enable the extension or grant broad WAL read access to arbitrary roles.

### 26.5. Reading a Specific Record

On supported versions:

~~~sql
SELECT *
FROM pg_get_wal_record_info('0/16B6C50'::pg_lsn);
~~~

The LSN must point to a valid record in accessible WAL. An LSN mid-record, a missing segment, or a recycled range can produce an error or no data.

### 26.6. Reading Multiple Records in a Range

~~~sql
SELECT
    start_lsn,
    end_lsn,
    prev_lsn,
    xid,
    resource_manager,
    record_type,
    record_length,
    main_data_length,
    fpi_length,
    description
FROM pg_get_wal_records_info(
    '0/16B6C50'::pg_lsn,
    '0/16C4200'::pg_lsn
);
~~~

Verify function signatures and output fields for your extension version. Keep the range narrow to avoid generating excessive output.

### 26.7. Record Range Statistics

~~~sql
SELECT *
FROM pg_get_wal_stats(
    '0/16B6C50'::pg_lsn,
    '0/16C4200'::pg_lsn
);
~~~

Statistics can break down record counts and bytes by resource manager or record type. Use this to understand lab workloads; do not call it the exact WAL bytes of a single session if the database has concurrent writes.

### 26.8. Safety When Inspecting WAL

WAL can contain page images and sensitive data. When exporting record descriptions or payloads:
- Restrict the LSN range.
- Never post raw WAL dumps to public places.
- Redact identifiers and payloads as needed.
- Do not retain dumps longer than policy allows.
- Avoid inspecting under overly broad roles when unnecessary.
- Use a binary/extension matching the PostgreSQL release.

---

## 27. WAL Milestones in an Illustrative Transaction

### 27.1. Conceptual Timeline

~~~text
T1 begins
   |
   +-- UPDATE heap page A ---- WAL record R1 @ LSN 100
   |
   +-- UPDATE index page B -- WAL record R2 @ LSN 180
   |
   +-- Audit trigger -------- WAL record R3 @ LSN 240
   |
   +-- COMMIT --------------- commit record @ LSN 310
                              |
                              v
                    WAL flushes past commit record
                              |
                              v
                    Server confirms COMMIT
                              |
                              v
                    Data pages written out later
~~~

The LSNs and ordering are illustrative only. If T2 runs concurrently, T2's records may appear between R1 and R2. A commit record LSN does not mean all records preceding it belong to T1.

### 27.2. Commit Confirmation Conditions

Under standard durability configuration, the server confirms transaction commit only after the WAL required for the transaction has been flushed to the required extent. If synchronous replication is configured, confirmation may also wait for a standby depending on mode.

### 27.3. Data Page Flush After COMMIT

A data page holding R1/R2 can be written to disk after COMMIT has been confirmed. At that point, the write-ahead rule guarantees the corresponding WAL was already durable before the page write. If a crash occurs before the data page write, recovery redoes WAL.

### 27.4. One Page Holding Multiple Transactions

If T1 and T2 modify the same heap page at different times, the page can hold effects from both transactions. The page LSN reflects the last WAL record applied to the page, not which transaction "owns" the page.

### 27.5. Commit Does Not Combine WAL into a Separate Contiguous Block

The WAL stream remains a single cluster-wide sequence of records. There is no separate segment file for T1. Recovery uses record metadata and transaction state to reconstruct results without needing T1's records grouped into their own file.

---

## 28. Lab: Reading LSN Positions

### 28.1. Take a Snapshot

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

Save the output. clock_timestamp() is the sampling time; LSNs can shift between function evaluations, and concurrent workloads can advance the positions.

### 28.2. Create a Transaction That Generates WAL

~~~sql
CREATE SCHEMA IF NOT EXISTS wal_order_lab;

CREATE TABLE IF NOT EXISTS wal_order_lab.demo (
    id bigint PRIMARY KEY,
    payload text NOT NULL
);
~~~

Measure before, then run:

~~~sql
BEGIN;

INSERT INTO wal_order_lab.demo(id,payload)
SELECT g, repeat('x',100)
FROM generate_series(1,1000) AS g
ON CONFLICT (id) DO UPDATE
SET payload=EXCLUDED.payload;

COMMIT;
~~~

### 28.3. Measure After

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

Record before/after LSNs and compute the diff. The delta represents the cluster-wide WAL stream between samples, not the record count of the INSERT.

### 28.4. Find the Segment Containing the Current LSN

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS wal_file,
    (pg_walfile_name_offset(pg_current_wal_lsn())).file_offset AS file_offset;
~~~

Syntax for accessing composite results can vary in display across clients and versions; you can run SELECT * FROM pg_walfile_name_offset(...) separately to inspect the columns clearly.

### 28.5. Check pg_stat_wal Before and After

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

Take two snapshots and compare the delta. If stats_reset changed between samples, do not compare directly. Counters are global; concurrent workloads introduce noise.

### 28.6. Test a Rollback

~~~sql
BEGIN;

INSERT INTO wal_order_lab.demo(id,payload)
VALUES (2001,'rollback-test');

ROLLBACK;
~~~

Verify:

~~~sql
SELECT *
FROM wal_order_lab.demo
WHERE id=2001;
~~~

No committed row exists, yet the WAL position may have advanced. This demonstrates the difference between business visibility and WAL generation.

---

## 29. Lab: Observing Checkpoints and Replication

### 29.1. Checkpoint Metadata

On a server/role with appropriate privileges, try:

~~~sql
SELECT *
FROM pg_control_checkpoint();
~~~

Inspect the checkpoint/redo/timeline fields. If the function does not exist or permission is denied, check the PostgreSQL version and role privileges; never grant superuser to an application.

### 29.2. Checkpoint Statistics

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

This view exists in newer PostgreSQL versions; older versions store some counters in pg_stat_bgwriter. Do not deploy a single SQL dashboard without version-gating.

### 29.3. Replication Progress on Primary

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

If no standby is connected, this view may be empty. Empty does not mean zero lag.

### 29.4. Receive/Replay on Standby

~~~sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

Compare receive with replay to see how much WAL the standby has received but not yet applied. The last replay timestamp does not accurately reflect lag when the primary is idle.

### 29.5. Archive Progress

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

Check last_archived_wal/time, failed_count, last_failed_wal/time, and stats_reset. Combine with logs and destination health to investigate archive backlogs.

---

## 30. Inference Rules When Reading WAL

### 30.1. From Lower to Higher LSN

An increasing LSN indicates a later record position in the WAL stream on that timeline. It does not by itself tell you which transaction committed, which business action succeeded, or which replica has replayed it.

### 30.2. From Commit Record

A commit record is a marker of transaction completion in WAL. Determining transaction state requires understanding XIDs, commit/abort records, and recovery semantics. Never conclude a row committed merely from seeing a heap record.

### 30.3. From Page LSN

Page LSN tells you up to which WAL position the page has applied changes per the storage/recovery mechanism. It cannot replace transaction status or commit records.

### 30.4. From Flush LSN

Flush LSN indicates WAL has been flushed up to a position. It does not mean every transaction with a record prior to that position committed; aborted/in-progress transactions and non-transactional records may exist in that range.

### 30.5. From Segment Filename

The filename indicates the timeline and segment position in WAL numbering. It does not tell you whether the segment was archived, replayed, or is still required by a slot.

### 30.6. From Archive Success

Archive success means the segment was archived according to the reporting mechanism, not that a backup chain is guaranteed restorable. You must run PITR tests.

---

## 31. Checklist for Reading WAL and Investigating Incidents

### 31.1. When Interpreting an LSN

- [ ] Identify whether the LSN is insert, write, flush, receive, replay, or commit LSN.
- [ ] Identify whether you are inspecting the primary or a standby.
- [ ] Note the timeline/history when a failover has occurred.
- [ ] Use pg_lsn and pg_wal_lsn_diff rather than manual string parsing.
- [ ] Remember that LSN deltas are cluster-wide when concurrent workloads exist.

### 31.2. When Inspecting Segments

- [ ] Verify the cluster's actual segment size.
- [ ] Parse filenames by timeline/log/segment numbering.
- [ ] Use pg_walfile_name()/pg_walfile_name_offset() when appropriate.
- [ ] Check archive/slot/replica retention.
- [ ] Never arbitrarily rename, delete, or copy active segments.

### 31.3. When Interpreting Record Order

- [ ] Separate record order from transaction start and commit order.
- [ ] Locate commit/abort records when tools allow.
- [ ] Remember records from concurrent transactions can interleave.
- [ ] Do not infer business row identity from an LSN.
- [ ] Use version-compatible tools when decoding records.

### 31.4. When Evaluating Durability

- [ ] Check synchronous_commit.
- [ ] Check synchronous replication policy if configured.
- [ ] Distinguish WAL write from WAL flush.
- [ ] Distinguish WAL flush from data-page flush.
- [ ] Check fsync, full_page_writes, and storage assumptions.
- [ ] Handle unknown commit outcomes with idempotency/reconciliation.

### 31.5. When Evaluating Checkpoints and Recovery

- [ ] Identify checkpoint/redo LSN.
- [ ] Check checkpoint frequency and WAL growth.
- [ ] Inspect FPI volume.
- [ ] Verify archive continuity/PITR.
- [ ] Never delete segments needed for recovery or standbys.

---

## 32. Official References

When working with a specific major version, prefer the documentation for that exact version:

- [PostgreSQL — Write-Ahead Logging (WAL)](https://www.postgresql.org/docs/current/wal.html): WAL principles and crash recovery.
- [PostgreSQL — WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html): WAL records/pages/segments and LSNs.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoint and WAL configuration.
- [PostgreSQL — WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): durability, fsync, and write-ahead rules.
- [PostgreSQL — WAL Functions](https://www.postgresql.org/docs/current/functions-admin.html): LSN functions, WAL file naming, and administrative functions.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_wal, replication, and checkpoint statistics.
- [PostgreSQL — Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): send/write/flush/replay and standby behavior.
- [PostgreSQL — Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): WAL archiving and recovery.
- [PostgreSQL — pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html): reading WAL records from the command line.
- [PostgreSQL — pg_walinspect](https://www.postgresql.org/docs/current/pgwalinspect.html): inspecting WAL via SQL extension on supported versions.

Pages under /current/ can change as new PostgreSQL versions are released. The WAL binary format is an implementation detail; if building long-lived parsers or analysis tools, make them version-aware and base them on the source/docs of the exact release.

---

## 33. Summary

**WAL is an ordered binary stream addressed by LSN and physically stored in segments.** Understanding records, segments, LSNs, and change ordering explains crash recovery, COMMIT durability, checkpoints, and streaming replication.

Key points to remember:

1. **Write-ahead rule:** required WAL must be durably written before the corresponding data page is durably written.
2. **A WAL record is not an SQL statement or row:** one statement can generate many records, and one record can affect multiple blocks.
3. **WAL page and segment are distinct organizational layers:** a segment is a physical file containing many pages; records can cross page/segment boundaries.
4. **An LSN is a byte position in the WAL stream:** not a timestamp, XID, or row ID.
5. **LSNs increase in record insertion order:** records from multiple transactions can interleave; start order does not equal commit order.
6. **A transaction produces multiple WAL records:** the commit record is a separate event, not a bundle of all changes into one record.
7. **Insert, write, and flush are distinct milestones:** write is not flush; flushing WAL does not mean data pages are flushed.
8. **Commit acknowledgement depends on durability settings:** synchronous_commit and synchronous replication govern what must be waited for.
9. **Page LSN helps recovery decide redo:** it is not a commit LSN or transaction identity.
10. **Checkpoints establish a redo starting point:** a checkpoint is not a COMMIT and does not guarantee old WAL segments are immediately deleted.
11. **Segment names encode timeline/log/segment fields:** segment size depends on cluster initialization; never hardcode 16 MiB for all clusters.
12. **Timelines separate history after failover:** LSNs must be interpreted within their timeline context.
13. **Replication tracks receive/write/flush/replay progress:** receiving WAL does not mean the standby has replayed it for queries.
14. **Archives and slots can retain WAL:** never delete files manually to free disk space.
15. **Inspect the right milestone:** use current insert/write/flush LSNs, pg_stat_replication, pg_stat_wal, pg_walfile_name, and version-compatible tools.
16. **Unknown COMMIT outcomes require idempotency:** losing a response does not prove the transaction rolled back.

Mental workflow: **identify the timeline → choose the LSN type to inspect → map to the corresponding record/segment → separate insert/write/flush → locate commit/checkpoint/redo context → compare replica receive/replay and archive state → perform recovery via PostgreSQL metadata, never by editing WAL files manually**.

---

## 34. Solutions — Exercises 16 to 30

### Exercise 16 — Flush and Durability

If the commit record has been flushed per durability policy, PostgreSQL already has the log required to recover the transaction. If a crash happens before the heap page is written, recovery reads WAL from the redo point and replays the needed changes. The write-ahead rule guarantees WAL is durable before the data-page write.

### Exercise 17 — synchronous_commit

No. WAL is still generated and written by the server mechanism; the setting can allow acknowledging COMMIT before the corresponding WAL is flushed, reducing latency while accepting the risk of losing recently confirmed commits on a crash. This is a durability trade-off, not "disabling WAL."

### Exercise 18 — Checkpoint, Redo, and Commit LSN

- Checkpoint LSN: position associated with the checkpoint record/metadata.
- Redo LSN: WAL point where recovery must begin considering redo.
- Commit LSN: position of a specific transaction's commit record.

A checkpoint syncs dirty pages and sets a recovery point; COMMIT marks transaction completion. The two events serve different goals.

### Exercise 19 — Timeline

After promotion, the standby becomes primary and WAL history can diverge. The same numeric LSN on two timelines does not necessarily share the same history. The timeline ID appears in the WAL segment filename and is recorded in timeline history metadata.

### Exercise 20 — Replication Positions

- sent_lsn: how far the sender has sent.
- write_lsn: how far the standby has written.
- flush_lsn: how far the standby has flushed.
- replay_lsn: how far the standby has applied WAL.

If flush advances while replay stalls, inspect standby CPU/I/O, the replay process, hot standby conflicts, long-running readers, and WAL apply bottlenecks. The network is likely not the primary culprit if receive/flush are keeping up.

### Exercise 21 — WAL Filename

~~~sql
SELECT pg_walfile_name(pg_current_wal_lsn());
~~~

And:

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

The results return the segment name and offset based on the current segment size and timeline.

### Exercise 22 — pg_waldump

It is a command-line utility that reads and interprets WAL segments. Output can show record start LSN, previous LSN, XID, resource manager, record type, length, block references, and descriptions. Options depend on version; use a binary compatible with the cluster.

### Exercise 23 — pg_walinspect

An extension providing SQL functions to read records, ranges, and statistics without manually parsing binary formats. You must limit the LSN range because output can be huge and payloads can contain sensitive data. WAL read privileges must follow policy, never granted broadly to application roles.

### Exercise 24 — Segment Rotation

pg_switch_wal() requests switching to the next WAL segment per server state. It does not free WAL; the segment may still be needed by checkpoints, archiving, standbys, or replication slots. Calling it repeatedly also creates extra archive and segment churn.

### Exercise 25 — Recycle and Archive

- Recycle: PostgreSQL reuses a segment file for future WAL positions once the old position is no longer needed.
- Archive: saves a completed segment to an archive destination for backup/PITR.

File counts can remain stable despite heavy WAL generation due to reuse; conversely, pg_wal can stay large due to retention even when current generation is low.

### Exercise 26 — Rollback

Yes. An UPDATE can generate WAL records prior to ROLLBACK. After rollback, business changes are not committed and are not visible as committed data, yet the WAL stream still advanced; aborted tuple versions may require cleanup/reuse.

### Exercise 27 — LSN Attribution

Current WAL LSN is cluster-wide. In production, other sessions, autovacuum, checkpoints, and background tasks can also write WAL between two samples. The delta measures server-wide WAL stream distance, not the exact WAL produced by one transaction.

### Exercise 28 — Checkpoint Inspection

~~~sql
SELECT *
FROM pg_control_checkpoint();
~~~

Two useful fields are checkpoint LSN and redo LSN (output column names may vary by version). You can also check timeline ID and checkpoint time for history and recovery context. This function requires appropriate version and privileges.

### Exercise 29 — Archive Failure

Safe steps:
1. Inspect pg_stat_archiver and PostgreSQL logs.
2. Check the archive destination, disk quota, permissions, network, and archive command.
3. Measure pg_wal free space and WAL generation rate.
4. Check replication slots/standbys to see what else is retaining WAL.
5. Restore the archive pipeline and monitor segment catch-up.
6. Never delete WAL segments manually; verify the backup/PITR chain.

### Exercise 30 — Slow Standby Replay

The primary generates WAL and flushes the commit record; the sender ships it to the standby. The standby receives, writes, and flushes WAL quickly, but the replay process cannot apply it fast enough, causing replay_lsn to lag behind flush_lsn.

Three groups of causes:
- CPU/replay processing bottleneck or heavy WAL record workload.
- Slow storage I/O on the standby.
- Hot standby conflicts, long-running queries, or resource contention blocking replay.

Inspect pg_stat_replication on the primary, receive/replay LSNs and recovery conflicts on the standby, CPU/I/O, logs, and wait events. If the app reads from replicas, account for eventual consistency and lag in routing.

---

## 35. Advanced Exercises: Analyzing WAL Sequences

### Exercise 31 — Interleaved Transactions

Given the WAL sequence:

~~~text
LSN 100: T1 UPDATE A
LSN 120: T2 UPDATE B
LSN 140: T1 UPDATE C
LSN 160: T2 COMMIT
LSN 180: T1 COMMIT
~~~

Answer: which transaction started first? Which transaction committed first? Can we say records 100–140 belong exclusively to T1?

### Exercise 32 — Insert/Write/Flush Positions

A sample shows:
- insert = 0/5000000
- write = 0/4F00000
- flush = 0/4E00000

Explain what the gaps between the three positions tell you and what cannot be concluded.

### Exercise 33 — Segment Count

A cluster using 16 MiB segments generates about 512 MiB of WAL in a measurement window. Can you conclude pg_wal must currently contain exactly 32 files? Why or why not?

### Exercise 34 — Page LSN

A heap page has pd_lsn=0/9000. A WAL record with LSN=0/8000 references that page within the redo range. Can you conclude redo always skips that record? State the caveat.

### Exercise 35 — WAL Record Crossing Pages

Why can a parser not assume a record always fits inside a single WAL page? What role does the continuation header play?

### Exercise 36 — Checkpoints and Segment Retention

After a new checkpoint, pg_wal still contains many old segments. List at least four possible reasons.

### Exercise 37 — Timeline and LSN

Two nodes report the same replay LSN but different timeline IDs after a failover. Can you conclude they share the same history? Explain.

### Exercise 38 — Archive Success

pg_stat_archiver shows archived_count increasing. Is that enough to confirm PITR works to any point in time? What else must be verified?

### Exercise 39 — LSN Delta

You read pg_current_wal_lsn() before and after a 5-second workload and observe a 200 MiB diff. Calculate the average WAL generation in MiB/s. List at least two limitations of this result.

### Exercise 40 — Commit Acknowledgement

A transaction COMMIT is acknowledged while synchronous_commit=off. The server loses power immediately afterward. Could the transaction be lost? Why does the application need idempotency?

### Exercise 41 — WAL Record vs. Query Log

Why is pg_waldump not an auditing tool for SQL statements or business events? What should be used for business auditing?

### Exercise 42 — Unlogged Table

An importer writes raw data into an UNLOGGED table, then merges it into a logged table. After a crash, what can happen to the raw staging table? What conditions make this pattern safe?

### Exercise 43 — wal_level

A DBA lowers wal_level to save disk space. Why does this fail to fix a stuck replication slot, and what consequences can it cause?

### Exercise 44 — WAL Writer

What roles do the WAL writer and backends play in write/flush? Why should you not tune wal_writer_delay based on a single latency measurement?

### Exercise 45 — Comprehensive Runbook

The primary commits normally, but replica lag rises, retained pg_wal grows, and archive failures increase. Write the steps to distinguish generation pressure from retention pressure and recover safely.

---

## 36. Solutions — Advanced Exercises

### Exercise 31 — Interleaved Transactions

T1 has its first record at LSN 100, so it began writing WAL first in this sequence. T2 committed at LSN 160 before T1 at LSN 180. You cannot say records 100–140 belong exclusively to T1 because T2 has an interleaved record at LSN 120.

### Exercise 32 — Position Gaps

Insert leads write, and write leads flush. At sample time, there are WAL bytes inserted into buffers but not yet written, and bytes written to the OS but not yet flushed. You cannot infer the exact count of uncommitted transactions or un-durable business rows from these gaps alone; you need concurrency, record types, and timing context.

### Exercise 33 — Segment Count

No. 512 MiB / 16 MiB = 32 segments' worth of WAL generation, but the directory may retain recycled segments, the active segment, or segments held by archiving, slots, standbys, or checkpoints. The current file count does not equal the generation during the window.

### Exercise 34 — Page LSN

If page LSN is already ahead of the record LSN, recovery generally does not need to redo that page change again under the appropriate redo logic. However, do not assume every record/resource manager shares identical skip conditions; redo routines, block references, FPIs, and record semantics can affect the decision.

### Exercise 35 — Continuation

A record's length may exceed the remaining space on a page. Continuation metadata on the next page tells the reader how many bytes remain from the previous record so the payload can be stitched together accurately. Parsers must understand page headers, alignment, and segment boundaries.

### Exercise 36 — Segment Retention

- Archive command has not finished.
- A physical standby or logical replication slot holds an old restart LSN.
- A standby is receiving/replaying slowly or is offline.
- wal_keep_size or retention settings.
- Needed for checkpoint/recovery.
- PostgreSQL segment recycle/reuse policy and minimum WAL retention.

### Exercise 37 — Timeline

No. Identical LSNs on two different timelines can point to different histories after the fork point. You must check timeline IDs, history files, and recovery lineage.

### Exercise 38 — Archive Success

Not enough. You need a valid base backup, continuous WAL from the backup to the target, required timeline history, an intact archive destination, and actual restore/PITR testing. archived_count is just a counter and does not prove the full chain is restorable.

### Exercise 39 — WAL Rate

200 MiB / 5 seconds = **40 MiB/s** average during the window. Limitations:
- WAL from all sessions and background tasks may be included together.
- Short-term rates can mask bursts before or after.
- LSN delta does not distinguish data, transaction, or FPI records.
- If the workload had idle gaps or a checkpoint, the sample is not representative of steady state.

### Exercise 40 — synchronous_commit=off

Yes. The server can acknowledge before the corresponding WAL is flushed; a power loss can lose recently confirmed commits. Lost responses at the client also create unknown outcomes. Idempotency keys, unique constraints, and reconciliation enable safe retries without duplicating business effects.

### Exercise 41 — WAL Is Not an SQL Audit

WAL logs internal binary changes for recovery/replication and does not guarantee preserving SQL text or business intent. One statement can produce many records, and a single record may not map directly to a business event. Auditing should use application audit events, an outbox/event log, or an appropriate database audit extension.

### Exercise 42 — UNLOGGED Staging

After a crash or unclean shutdown, the raw unlogged table can be truncated/reset per PostgreSQL semantics and is not replicated to physical standbys like logged tables. This pattern is safe only if the raw source is immutable, has checksums/versions, can be reloaded completely, authoritative checkpoints are logged, and the published destination is committed properly.

### Exercise 43 — wal_level

A replication slot retains WAL because a consumer needs bytes from restart_lsn; lowering wal_level neither catches up the consumer nor clears the retention dependency. Changing it can break physical/logical replication and archive/PITR assumptions and may require a restart. Fix the slot consumer or archive backlog per runbook.

### Exercise 44 — WAL Writer

Backends can insert, write, and flush WAL when needed; the WAL writer helps write/flush WAL buffers on a schedule/threshold. wal_writer_delay can alter write batching, latency, and I/O patterns; a single sample is insufficient because group commit, storage syncs, workload concurrency, and WAL buffer pressure all interact. Benchmark across multiple windows while preserving durability requirements.

### Exercise 45 — Runbook

1. Measure pg_stat_wal bytes/s, current insert/write/flush LSNs, and free disk space.
2. Inspect pg_stat_replication sent/write/flush/replay positions.
3. Check pg_stat_archiver failures and destination health.
4. Inspect pg_replication_slots restart_lsn, active status, and owner.
5. Distinguish whether WAL generation increased or retention is not releasing.
6. If generation pressure, throttle write rate/importers; if retention pressure, restore the archive pipeline, consumer, or standby.
7. Never delete WAL files or drop slots without an identified owner.
8. Ensure disk headroom, pausing safely at transaction boundaries if needed.
9. Reconcile transactions and unknown commit outcomes before resuming.
10. Resume with a small canary and ramp up gradually as replicas and archiving catch up.

---

## 37. Quick Reference Table

| Concept | Question Answered | Do Not Confuse With |
|---|---|---|
| WAL record | One internal event/change needed for redo | SQL statement, row |
| WAL page | Page holding a portion of the WAL stream | Heap page |
| WAL segment | Physical file holding a range of WAL pages | Transaction file |
| LSN | Byte position in the WAL stream | Timestamp, XID |
| Page LSN | Last WAL position applied to a data page | Commit LSN |
| Insert LSN | Inserted WAL position | Flush position |
| Write LSN | Written WAL position | Data page write |
| Flush LSN | Flushed WAL position | All transactions committed |
| Commit record | Transaction completion record | Checkpoint |
| Checkpoint | Recovery point / dirty-page synchronization | COMMIT |
| Redo LSN | Redo starting point | Current LSN |
| Timeline | WAL history branch | Database ID |
| Receive LSN | How far standby has received WAL | Replay LSN |
| Replay LSN | How far standby has applied WAL | Primary flush LSN |
| Archive | Saving completed segments for recovery | Recycle |
| pg_waldump | Reading WAL records offline | SQL audit log |
| pg_walinspect | Inspecting WAL via SQL functions | Business event store |

---

## 38. Extended Summary

When reading an LSN number, first ask whether it is an **insert, write, flush, receive, replay, redo, or commit position**. When reading a WAL filename, identify the **timeline, log ID, segment number, and segment size**. When reading a record, identify the **resource manager, record type, XID, block references, and transaction context**.

Always keep three axes separate:

1. **WAL order:** the order records are placed into the WAL stream, addressed by LSN.
2. **Transaction state:** whether a transaction is in-progress, committed, or aborted per XID/commit records/MVCC.
3. **Persistence/replication progress:** how far WAL has been inserted, written, flushed, received, replayed, or archived.

These axes are related but not interchangeable. A higher LSN does not by itself mean a transaction committed; a flush LSN does not prove a replica replayed it; a checkpoint is not a transaction commit; an archived segment does not guarantee a restorable PITR chain.

---

## 39. Foundational Exercises: Reading Records, Segments, and LSNs

### Exercise 46 — Role of WAL

A newcomer claims PostgreSQL only needs to write heap pages to disk, and WAL is just a debug log. Explain why this view is wrong.

### Exercise 47 — Records and Pages

A record is longer than the remaining free space on the current WAL page. How does PostgreSQL handle it so a record reader can continue reading?

### Exercise 48 — Segment Filename

Given the sample WAL filename 00000002000000010000000F, extract the timeline ID, log ID, and segment number.

### Exercise 49 — LSN Arithmetic

LSN A is 0/1000000 and LSN B is 0/1800000. Write a query to calculate the byte distance from A to B.

### Exercise 50 — XID and LSN

One transaction has a smaller XID than another transaction yet commits later. Does this contradict LSN ordering? Explain.

### Exercise 51 — Page LSN and Commit

A heap page has a page LSN higher than the commit LSN of a transaction that modified a row on that page. Can you infer the page contains that transaction's change? State the limits of this inference.

### Exercise 52 — Write-Ahead Rule

Can a data page be written to its data file before its corresponding WAL is flushed? Why or why not?

### Exercise 53 — Group Commit

Three transactions wait concurrently for a WAL flush. How can PostgreSQL reduce the number of syncs? Does group commit merge them into a single transaction?

### Exercise 54 — Checkpoint

After a checkpoint, where can PostgreSQL start crash recovery? Why does redo LSN not necessarily match the checkpoint record LSN?

### Exercise 55 — Segment Recycle

WAL generation increases by 1 GiB, yet the file count in pg_wal does not increase. Give a reasonable explanation.

### Exercise 56 — WAL Archive

A segment has been archived successfully. Does that mean PostgreSQL can immediately delete all related WAL from local disk? Why or why not?

### Exercise 57 — Timeline Fork

Both the old primary and the promoted standby have a record at LSN 0/5000000, but on two different timelines. Why can the two records not be treated as the same history?

### Exercise 58 — Replication Lag

The primary flush LSN advances and the standby receive LSN advances accordingly, but replay LSN lags. Classify the bottleneck and name three metrics to inspect.

### Exercise 59 — WAL Delta in Production

A job runs from 10:00 to 10:05 and the LSN diff is 2 GiB. Can you state the job generated 2 GiB of WAL? Describe how to make the measurement more reliable.

### Exercise 60 — Unknown Commit Outcome

A client sends COMMIT, but the connection resets before a response is received. Why can you not assume a rollback? Provide two application techniques to handle this.

---

## 40. Solutions — Foundational Exercises 46 to 60

### Exercise 46 — Role of WAL

WAL is a recovery and replication mechanism, not debug text. It records required changes in order and enables redo after a crash. Writing only data pages without matching durable WAL leaves the database unable to recover consistently after a crash or torn write.

### Exercise 47 — Record Spanning Pages

A record can continue onto the next WAL page. The page continuation header provides metadata such as the remaining portion of the record so the reader can concatenate bytes in order; parsers must also handle alignment and segment boundaries.

### Exercise 48 — Filename

24 hex chars:
- Timeline ID: 00000002.
- Log ID: 00000001.
- Segment number: 0000000F.

This is how the name structure breaks down; segment size and timeline history are still needed to interpret exact positions.

### Exercise 49 — LSN Diff

~~~sql
SELECT pg_wal_lsn_diff(
    '0/1800000'::pg_lsn,
    '0/1000000'::pg_lsn
) AS bytes;
~~~

The distance is 0x800000 = 8,388,608 bytes = 8 MiB. Use PostgreSQL functions instead of manually parsing hex in application code.

### Exercise 50 — XID and LSN

No contradiction. XID assignment/start order and commit order differ. LSN marks WAL record positions; records from concurrent transactions interleave, and a transaction can commit after another transaction with a higher XID.

### Exercise 51 — Page LSN and Commit

A page LSN higher than the commit LSN indicates a later record in the WAL stream was applied to the page, yet the page can hold changes from multiple transactions. From page LSN alone, you cannot determine whether a specific transaction's row is visible or committed; you need tuple/MVCC/transaction status.

### Exercise 52 — Write-Ahead Rule

No. Required WAL records must be durably flushed before the corresponding data page is durably written. Otherwise, the page could contain a change without an appropriate log for recovery to redo or repair it.

### Exercise 53 — Group Commit

PostgreSQL can batch multiple transactions waiting for a flush so a single WAL sync covers multiple commit records. Each transaction retains its own atomicity and commit state; group commit only optimizes I/O syncs.

### Exercise 54 — Checkpoint

Recovery begins redo from the appropriate redo pointer stored in checkpoint/control metadata. The checkpoint record is an event record; the redo LSN can be an earlier position that recovery must inspect, so the two LSNs need not match.

### Exercise 55 — Recycle

PostgreSQL can recycle old segments, reusing them for future WAL positions rather than increasing the file count. Some segments may also remain pinned by retention requirements; file count does not equal WAL generation.

### Exercise 56 — Archive

No. Local segments may still be required for checkpoints, replication slots, standbys, wal_keep_size, or recovery. PostgreSQL manages the lifecycle automatically; archived copies must also be retained per backup/PITR retention policy. Never delete local files manually.

### Exercise 57 — Timeline Fork

A new timeline can branch at an LSN after promotion. The same LSN value on two timelines can hold different bytes/records after the fork. You must evaluate timeline IDs/history, not just LSNs.

### Exercise 58 — Replay Lag

The standby has received and written WAL, but apply/replay is slow. Inspect:
- replay_lsn and its gap behind flush_lsn.
- CPU/I/O latency on the standby.
- Hot standby conflicts, long-running readers, recovery logs, and resource contention.

### Exercise 59 — LSN Delta

You cannot attribute the entire 2 GiB to the job if the database has concurrent workloads. Measure in an isolated environment, pause other writes if permitted, take multiple samples, record stats_reset, and cross-check pg_stat_wal/replication. If not isolated, explicitly report it as the cluster-wide WAL delta during the window.

### Exercise 60 — Unknown Commit Outcome

The server may have committed and flushed while the response was lost, or failed to commit before the connection dropped. Handling techniques:
1. Idempotency keys/unique business constraints so retries do not duplicate effects.
2. Reconnect and reconcile state using business keys, checkpoints, or an outbox.
A transactional outbox can also be combined for external side effects.

---

## 41. Foundational Exercises: Concept Check

### Exercise 1 — Purpose of WAL

State three primary roles of WAL in PostgreSQL. Why should WAL not be treated as an ordinary application log?

### Exercise 2 — Write Ordering

State the write-ahead rule in your own words. Before what type of data is written to data files must WAL be durable?

### Exercise 3 — Organizational Layers

Distinguish between record, page, and segment. Which layer is the physical file unit?

### Exercise 4 — A Single SQL Statement

What groups of WAL records can an INSERT into a table with a primary key and two secondary indexes generate?

### Exercise 5 — LSN

What does LSN stand for? What position does it address, and how is it commonly formatted?

### Exercise 6 — LSN and Time

By how many seconds later did a transaction occur if its LSN is higher than another's? Explain.

### Exercise 7 — Computing Delta

Write an SQL query using pg_wal_lsn_diff() to calculate the byte distance between two hypothetical LSNs.

### Exercise 8 — Three Positions

What are the names of the three SQL functions returning current WAL insert, write, and flush LSNs?

### Exercise 9 — Page LSN

Where is page LSN stored, and how does it assist recovery?

### Exercise 10 — Commit Record

Does a commit record replace prior heap/index WAL records? Why or why not?

### Exercise 11 — Transaction Interleaving

Why can records from two transactions interleave within the same WAL segment?

### Exercise 12 — Checkpoint

What problem does a checkpoint solve for crash recovery? Must every transaction wait for a checkpoint before COMMITting?

### Exercise 13 — Filename

What three hex fields make up a WAL segment filename? Which field distinguishes history after a failover?

### Exercise 14 — Segment Lifecycle

Distinguish recycle/reuse from archive. Why does the number of files in pg_wal not directly reflect the WAL rate?

### Exercise 15 — Timeline

After promoting a standby, why does PostgreSQL create a new timeline? Is an LSN alone sufficient to identify history?

### Exercise 16 — Flush and Durability

If the commit record has been flushed per durability policy, can PostgreSQL recover the transaction after a crash even if the heap page was not written?

### Exercise 17 — synchronous_commit

What does this setting control? Does it turn off WAL generation?

### Exercise 18 — Checkpoint, Redo, and Commit

Distinguish among these three LSNs/markers: checkpoint, redo, and commit.

### Exercise 19 — Timeline ID

Where is the timeline ID represented in WAL files? Why is it necessary to inspect the history file?

### Exercise 20 — Replication

Distinguish between sent_lsn, write_lsn, flush_lsn, and replay_lsn.

### Exercise 21 — Segment Lookup

Write a query to retrieve the current WAL filename and a query to retrieve the filename and offset from an LSN.

### Exercise 22 — pg_waldump

What does pg_waldump do? Does it display the exact SQL UPDATE statement sent by the application?

### Exercise 23 — pg_walinspect

What capability does pg_walinspect provide? Why should you avoid inspecting overly wide ranges?

### Exercise 24 — Segment Switch

What is pg_switch_wal() used for? Why is it not a disk-cleanup command?

### Exercise 25 — Archive Retention

For what reasons might an already-archived segment still remain in pg_wal?

### Exercise 26 — Rollback

Can DML that executes and then ROLLBACKs still generate WAL? Why?

### Exercise 27 — Attribution

What activity aside from the measured transaction can be included in a production LSN delta?

### Exercise 28 — Control Checkpoint

Which function can read checkpoint metadata in supported PostgreSQL versions? Why are appropriate administrative privileges required?

### Exercise 29 — Archiver Failure

List four things to check when archive failures increase and retained pg_wal grows.

### Exercise 30 — Replay Lag

If a standby has flushed WAL yet replay_lsn lags behind, at which stage is WAL stalled? Name three possible causes.

---

## 42. Solutions — Foundational Exercises 1 to 15

### Exercise 1 — Purpose of WAL

WAL supports crash recovery, physical streaming replication, and continuous archiving/PITR; logical decoding also relies on WAL. It is a structured binary stream ensuring database correctness, not a debug log to delete arbitrarily.

### Exercise 2 — Write Ordering

WAL records describing changes to a data page must be durably written before the corresponding data page is durably written to data files. This enables recovery redo when a crash happens before the page write finishes.

### Exercise 3 — Record/Page/Segment

A record is a WAL unit of information; a page is a block unit in the WAL stream with a header; a segment is a physical file containing a range of pages. The segment is the physical file layer.

### Exercise 4 — A Single INSERT

There can be a heap insert record, B-tree records for primary and secondary indexes, FPIs where applicable, transaction/commit records, and additional records from triggers or foreign-key actions. There is no one-INSERT-row = one-WAL-record relationship.

### Exercise 5 — LSN

A Log Sequence Number is a byte position in the WAL stream, typically represented in hex format X/Y. It is used to locate records/segments and compare progress within the same timeline context.

### Exercise 6 — LSN and Time

You cannot tell. An LSN is a byte position, not a timestamp. Because WAL generation rates vary by workload, the same byte delta can be produced over vastly different durations.

### Exercise 7 — Computing Delta

~~~sql
SELECT pg_wal_lsn_diff(
    '0/2000000'::pg_lsn,
    '0/1000000'::pg_lsn
) AS wal_bytes;
~~~

### Exercise 8 — Three Positions

- pg_current_wal_insert_lsn()
- pg_current_wal_lsn()
- pg_current_wal_flush_lsn()

They reflect insert, write, and flush positions respectively according to PostgreSQL semantics.

### Exercise 9 — Page LSN

Page LSN resides in the page header, commonly referred to as pd_lsn. It records the last WAL position applied to the page and helps redo logic decide whether the page already contains the corresponding change. It is not a commit LSN.

### Exercise 10 — Commit Record

No. A commit record records transaction completion and required metadata; earlier heap/index changes remain separate records. Records can interleave with other transactions.

### Exercise 11 — Interleaving

Multiple backends generate WAL records into one cluster-wide stream. WAL insertion order dictates LSN order, but transactions are not given isolated contiguous slices; their records can interleave.

### Exercise 12 — Checkpoint

A checkpoint establishes a recovery point and ensures required dirty pages are written per the checkpoint mechanism. Transactions do not wait for a checkpoint to commit; commit durability relies on the WAL flush policy.

### Exercise 13 — Filename

The three fields are timeline ID, log ID, and segment number. The timeline ID distinguishes WAL history branches after a failover or promotion.

### Exercise 14 — Segment Lifecycle

Recycle/reuse means reusing a segment file for future WAL positions; archive means copying a completed segment to an archive destination for backup/PITR. File count is affected by reuse and retention, so it does not equal WAL bytes generated in a window.

### Exercise 15 — Timeline

Promotion can cause WAL history to branch away from the old primary; a new timeline marks that branch. An LSN alone is insufficient because the same LSN value on different timelines can belong to different histories; you need the timeline ID and history.
