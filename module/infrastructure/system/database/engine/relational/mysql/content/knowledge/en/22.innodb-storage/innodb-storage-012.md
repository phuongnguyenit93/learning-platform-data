# Doublewrite Buffer and Protection Against Incomplete Page Writes

InnoDB stores data in pages. When a dirty page in the buffer pool is written down to a data file, the write can be interrupted midway by power loss, an abrupt OS halt, or storage hardware failure. As a result, the page on disk contains only part of the new data while the remainder is still old data. This phenomenon is commonly called a **torn page**.

InnoDB uses the **doublewrite buffer** to keep a complete copy of a page before writing that page to its official location in the tablespace. If a crash corrupts the page at its official location, InnoDB can restore the page from the doublewrite copy and then apply the redo log. This mechanism complements the redo log: redo protects the ability to replay logged changes, whereas doublewrite helps recover a partially written page.

## Objectives

After this lesson, you will be able to:

- Explain why a page write can be incomplete and cause a torn page.
- Describe the dirty page flush flow from the buffer pool through the doublewrite buffer to data files.
- Distinguish the roles of the doublewrite buffer, redo log, undo log, and binary log.
- Predict how InnoDB recovers when crashes happen at different points in the flush process.
- Inspect doublewrite configuration and metrics, and evaluate the risks of disabling this mechanism.

Examples assume MySQL 8.0 or later and tables using the InnoDB storage engine.

## 1. Why Can a Page Be Written Incompletely?

InnoDB reads and writes data in pages. The default page size is typically 16 KiB, though it can be configured at instance initialization. A single page can contain multiple rows or part of an index structure. When a dirty page is flushed, InnoDB asks the operating system and storage device to write that page to its corresponding location in the tablespace file.

Not every storage layer guarantees that a 16 KiB write is atomic. Devices may write in smaller sectors; a single page write can be split into multiple physical operations. If power fails or the system halts mid-operation, some sectors may already have the new contents while the remaining sectors still hold old contents.

Illustrative example of a page consisting of four write regions:

```text
Before flush:              After interrupted write:
+------+------+------+    +------+------+------+
| old  | old  | old  |    | new  | new  | old  |
+------+------+------+    +------+------+------+
| old  |                   | old  |
+------+                   +------+
```

After the failure, the page can hold a mix of old and new data. Headers, trailers, checksums, or record structures may no longer be consistent. If the page is a B-tree node, this corruption can impair reading rows or traversing the index.

**A torn page differs from losing a committed transaction.** A transaction may have durably written its redo log even though the corresponding data page has not been flushed yet. When the server restarts, the redo log can replay the change. However, if the underlying page was torn, InnoDB first needs a valid base page for recovery to build on. That is the problem doublewrite solves.

## 2. How Does the Doublewrite Buffer Work?

When InnoDB flushes a batch of dirty pages from the buffer pool, the doublewrite mechanism performs a two-step write:

1. Write the pages to the doublewrite area and ensure this copy is flushed to storage.
2. Then write the pages to their official locations in the data files or tablespaces.

You can visualize the data flow:

```text
Transaction modifies data
          |
          v
       Buffer pool
      (dirty page)
          |
          v
  Doublewrite buffer
  writes full page copy
          |
     flush complete
          |
          v
  Data file / tablespace
  writes page to main slot
```

The doublewrite copy is a complete page written in batches. Once the official pages finish writing, the doublewrite area can be reused for the next batch. Doublewrite is not a long-term database backup; it is a staging area protecting and recovering pages during the write path.

### Why Must the Copy Be Written First?

Order is decisive. If InnoDB wrote the official page first and the copy afterward, a crash during the first write could destroy the old page before a valid copy existed. By writing and flushing the doublewrite copy first, InnoDB has an intact page to restore from if writing to the official location is interrupted.

Doublewrite is structured to write multiple pages in a batch, reducing I/O cost compared to creating an individual copy via separate random writes per page. Only after the doublewrite batch is durably written are the pages written to their official positions.

## 3. Doublewrite Coordinates with the Redo Log

Doublewrite and the redo log solve two distinct parts of recovery.

| Component | Role | Question it answers |
|---|---|---|
| Redo log | Records changes to replay for restoring database state after a crash | How should logged changes be reapplied? |
| Doublewrite buffer | Holds a complete page copy before the page is written to its official slot | If a page in the data file is torn, where do we get a valid page? |
| Undo log | Stores info needed for rollback and building older versions for MVCC | Which uncommitted changes must be undone or which older versions read? |
| Binary log | Records server-level change events for replication and point-in-time recovery | Which SQL/row events need replication or point-in-time recovery? |

The redo log obeys write-ahead logging: relevant redo info must be durably written before the corresponding data page is written to its official position. This lets InnoDB replay changes after a crash even when dirty pages were not flushed yet.

However, the redo log is not always a substitute for a complete page. If a page on disk is torn, restoring a valid page from doublewrite first and then applying redo is how InnoDB safely recovers page structure.

## 4. When Does a Crash Happen?

Suppose page `P` in the buffer pool was modified and needs flushing. The following scenarios illustrate doublewrite's role:

| Crash timing | Possible state encountered | Recovery path |
|---|---|---|
| Before the doublewrite copy is durably written | Official page is still the old version; new page may exist only in memory | InnoDB uses the redo log to replay necessary changes |
| After doublewrite flushed, before official page write | Complete copy exists in the doublewrite area; official page may still be old | InnoDB can use the valid copy and apply redo if needed |
| During official page write | Official page may be torn; doublewrite copy was already written beforehand | InnoDB detects an invalid page, restores from the doublewrite copy, then applies redo |
| After official page write completes | Official page is written; staging copy can be reused later | Standard recovery verifies redo and page state |

During crash recovery, InnoDB checks pages and relevant doublewrite copies. If an official page is found corrupted yet a valid copy exists, the engine restores the page from doublewrite and continues applying redo logs from the checkpoint. Page validation mechanisms such as checksums help detect certain forms of invalid pages.

Do not read the table above as a guarantee that every kind of storage corruption is repairable. Doublewrite only helps when the page copy remains intact and readable. If both the doublewrite area and the official page are corrupted, or the device loses all data, backups and proper recovery procedures are required.

## 5. Checksums Help Detect Abnormal Pages

InnoDB stores checksum information inside pages to verify integrity when reading or recovering. If page contents change unexpectedly or are written incompletely, the checksum can mismatch and the engine detects a problem with the page.

Checksums and doublewrite play complementary roles:

- Checksums help detect invalid pages.
- Doublewrite provides a complete page copy to restore when the official page is torn.
- The redo log replays necessary changes once a valid base page is available.

Checksums do not repair data on their own. Nor does a valid checksum prove data is business-correct; an erroneous SQL operation can still produce a valid page containing wrong values.

You can check the configured checksum algorithm:

```sql
SHOW VARIABLES LIKE 'innodb_checksum_algorithm';
```

Do not change the checksum algorithm or disable checksums in a running environment merely to bypass a page warning. Verify version compatibility, backup/restore workflows, and operations documentation before altering related configuration.

## 6. Doublewrite Storage Location by MySQL Version

The physical location of the doublewrite area depends on the MySQL version:

- Prior to MySQL 8.0.20, the doublewrite area was stored inside the system tablespace.
- Starting in MySQL 8.0.20, doublewrite storage areas are placed in separate doublewrite files, allowing InnoDB to organize batch writes more independently from the system tablespace.

In newer versions, filenames and organization are managed by InnoDB. Never delete, rename, or manually move doublewrite files while the server is running. When changing data directories, configuring doublewrite paths, or restoring from backups, follow supported procedures for your exact version.

Certain configuration variables may exist depending on version:

| Variable | General meaning |
|---|---|
| `innodb_doublewrite` | Enables/disables or selects a doublewrite mode supported by the version |
| `innodb_doublewrite_dir` | Directory storing doublewrite files on versions supporting this setting |
| `innodb_doublewrite_files` | Number of doublewrite files organized by InnoDB per version configuration |
| `innodb_doublewrite_pages` | Cap on pages written in a batch per version configuration |

Not all variables above exist in every release. Check `SHOW VARIABLES` on the target server before relying on them in automation or runbooks.

## 7. Should Doublewrite Be Disabled?

Generally, keep doublewrite enabled. This mechanism is a protection layer against incomplete page writes, especially when the operating system or storage hardware does not guarantee atomic writes for InnoDB's page size.

Disabling doublewrite can reduce some write I/O, while simultaneously removing the page protection InnoDB relies on during crash recovery. Only consider it when the storage platform provides atomic page write guarantees explicitly supported by MySQL, verified on your exact version and hardware, and residual risk is accepted. Do not disable it merely because a short benchmark shows fewer writes.

Before changing it:

1. Verify device model, firmware, controller, cache, and power-loss protection.
2. Check whether the filesystem and I/O mode MySQL uses preserve atomic write guarantees properly.
3. Read MySQL documentation for your exact version and deployment platform.
4. Test realistic workloads, crash recovery, and backup/restore in an isolated environment.
5. Document the previous configuration, rollback procedure, and the risk-approval owner.

Doublewrite can introduce extra I/O, though actual cost depends on workload, storage hardware, and how InnoDB batches pages. Measure latency, throughput, and recovery time before deciding to optimize.

## 8. Checking Configuration and Activity

Read the current doublewrite value:

```sql
SHOW VARIABLES LIKE 'innodb_doublewrite';
```

Inspect doublewrite variables supported by the server:

```sql
SHOW VARIABLES LIKE 'innodb_doublewrite%';
```

View activity counters:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_dblwr%';
```

Two commonly useful counters are:

- `Innodb_dblwr_pages_written`: total number of pages written through the doublewrite mechanism.
- `Innodb_dblwr_writes`: total number of doublewrite batch writes.

Read the counters twice over an interval to compute the delta. The ratio `pages_written / writes` during the measurement interval gives a sense of average pages per batch. These are cumulative counters since server startup; do not use a single absolute value to conclude the system is slow or broken.

You can combine this with flushing and InnoDB status details:

```sql
SHOW ENGINE INNODB STATUS;
```

Correlate doublewrite metrics with dirty pages in the buffer pool, page cleaner activity, redo log, storage latency, and workload. Increasing doublewrite counters are normal when pages are flushed; they do not automatically mean torn pages occurred.

## 9. Doublewrite Does Not Replace Backups or Other Protection Layers

Doublewrite has a narrow scope: protecting pages on InnoDB's write path. It does not replace:

- **Backups:** required for file loss, device failure, accidental deletion, or widespread corruption.
- **Binary logs and point-in-time recovery:** enable restoring to a specific point in time using backups and binlogs.
- **Replication:** provides data copies on other servers, though backups and consistency checks are still required.
- **Redo log:** ensures necessary changes are replayed after a crash.
- **Checksums and monitoring:** help detect certain forms of page corruption and track activity.

If encountering checksum errors or page corruption messages, preserve evidence, check the error log, identify affected tablespaces/pages, and assess the latest backup. Avoid experimenting with overwriting data files directly or deleting doublewrite files to force the server to start. Force recovery modes exist strictly for controlled data rescue; they are not standard repairs for corrupted pages.

## 10. Practice Lab

On a test MySQL instance, without production data:

1. Check `innodb_doublewrite`, `innodb_checksum_algorithm`, and available `innodb_doublewrite%` variables.
2. Read `Innodb_dblwr_pages_written` and `Innodb_dblwr_writes`, wait through a period of write workload, then read again to compute the added pages and batches.
3. Run a workload updating many InnoDB rows and observe doublewrite counters alongside `SHOW ENGINE INNODB STATUS`.
4. Diagram the write sequence: redo log, doublewrite area, and official page location. Explain why the doublewrite copy must be durably written before the official page.
5. Describe how recovery handles an official page with an invalid checksum when the doublewrite copy remains intact.
6. Explain why doublewrite cannot replace backups if the storage device fails completely.

Never intentionally cut power or kill the database process on a machine holding real data to test torn pages. If testing crash recovery is needed, use a virtual machine or test instance with synthetic data, restorable snapshots, and dedicated test procedures.

## Takeaways

- A torn page occurs when a page is partially written and may contain a mix of old and new data.
- Doublewrite writes a complete page copy to a staging area and flushes the copy before writing the page to its official location.
- When an official page is corrupted, InnoDB can restore from the doublewrite copy and then apply the redo log.
- Redo log, undo log, doublewrite, and binary log serve distinct purposes; none completely replaces the others.
- Keep doublewrite enabled unless the platform's atomic write guarantees are clearly supported and verified for MySQL.
- Track doublewrite counters by deltas over time while checking page cleaners, redo, and storage latency.
- Doublewrite is not a backup; tested backups and recovery procedures remain essential for device failure or widespread corruption.
