# SCN, Checkpoints, and the Relationship Between Redo, Undo, and Committed Data

## 1. Architectural Question: Where Does a `COMMIT`ted Transaction Live?

Suppose an application transfers 500,000 VND from account A to account B. Oracle executes two `UPDATE` statements within the same transaction and then receives `COMMIT`. The application receives a success confirmation; immediately afterward, the server loses power. Even though the data blocks for the two accounts may **not yet have been written down to datafiles**, Oracle can still recover the entire committed transaction thanks to durably written **redo**. Conversely, a data block already written to a datafile may contain an **uncommitted** change; that change is invisible to other users and will be rolled back when needed.

To explain these phenomena accurately, distinguish five concepts:

1. **SCN (System Change Number)**: a logical sequence milestone Oracle uses to order changes, commits, and construct consistent data images.
2. **Redo**: information used to **replay** changes to database blocks, written by LGWR to online redo logs.
3. **Undo**: information used to **reverse** changes and reconstruct prior data versions for read consistency.
4. **Checkpoint**: the mechanism coordinating DBWn to flush dirty buffers to datafiles and recording recovery milestones, reducing the redo that must be reapplied if an instance fails.
5. **Commit**: the milestone marking successful transaction completion; under standard synchronous commit, the commit record and required redo are durable before Oracle returns success to the client.

Most important takeaway: **`COMMIT` does not mean Oracle must immediately write all of the transaction's data blocks down to datafiles; nor is `CHECKPOINT` an operation that commits transactions.**

## 2. Memory and Disk Picture: Where the Components Meet

```text
                          APPLICATION / USER SESSION
                                  │
                             UPDATE/INSERT
                                  │
                                  ▼
                         Oracle server process
                                  │
                 ┌────────────────┴─────────────────┐
                 │                                  │
                 ▼                                  ▼
       Database Buffer Cache              Redo Log Buffer
       ┌────────────────────┐             ┌────────────────────┐
       │ Modified data      │             │ Redo change vectors│
       │ blocks (dirty)     │             │ for data + undo    │
       │ Undo blocks        │             │ + transaction info │
       └─────────┬──────────┘             └──────────┬─────────┘
                 │                                   │
                 │ DBWn                              │ LGWR
                 ▼                                   ▼
       ┌────────────────────┐             ┌────────────────────┐
       │ Datafiles          │             │ Online redo logs   │
       │ ├─ Table/index     │             │ Group 1/2/3...     │
       │ └─ Undo tablespace │             └────────────────────┘
       └────────────────────┘                       │
                 ▲                                  │ ARCn if
                 │                                  │ ARCHIVELOG
                 │                                  ▼
          CKPT coordinates                  Archived redo logs
          and updates                       (for recovery)
          checkpoint metadata
          in control file
          + datafile headers
```

**Who writes what?**

| Component | Primary Role | What Not to Infer |
| --- | --- | --- |
| **Server process** | Executes DML, modifies blocks in buffer cache, generates associated undo and redo | `UPDATE` always writes datafiles immediately |
| **Redo log buffer** | Temporarily buffers redo before LGWR flushes | Redo still in RAM is already safe after power loss |
| **LGWR** (*Log Writer*) | Sequentially writes redo to online redo logs; participates in synchronous commits | LGWR writes table blocks down to datafiles |
| **DBWn/DBWR** (*Database Writer*) | Writes dirty data/undo buffers down to datafiles when needed | DBWn may only write committed data |
| **CKPT** (*Checkpoint Process*) | Updates checkpoint info in control file/datafile headers, drives checkpoint progress | CKPT directly writes table block contents |
| **Undo segments** | Stores data needed for rollback, transaction recovery, and consistent read images | Undo is a text log living outside the database |
| **ARCn** (*Archiver*) | Copies switched online redo log groups to archived redo logs in `ARCHIVELOG` mode | Archive logs completely replace active online redo |

These components operate **asynchronously at different times**. Separating sequential redo writes from scattered dirty data-block writes enables Oracle to achieve higher write performance and strong recoverability.

## 3. SCN: Oracle Database's Logical Clock

### 3.1. What Is an SCN?

A **System Change Number (SCN)** is a logical sequence number that advances with database activity. Oracle uses SCNs to track change order, mark commit points, preserve read consistency, and coordinate checkpoints and recovery.

Do not treat an SCN as a Unix timestamp or a counter that "increments by exactly 1 per SQL statement":

- An SCN represents **logical order**, not absolute wall-clock seconds.
- Gaps can occur; there is no one-to-one mapping between SCNs and the count of `INSERT`/`UPDATE` statements.
- A single transaction can contain **multiple changes and redo records**, yet has a **commit SCN** marking the logical point at which the transaction committed.
- In RAC, Oracle coordinates SCNs across instances to maintain consistent ordering; you cannot compare two SCN values from **independent databases** as if they shared a global clock.
- When analyzing backup/recovery, you must also consider **database incarnation and `RESETLOGS`**; a standalone SCN does not uniquely identify an entire recovery history.

Suppose transaction A commits at SCN `120500` and B commits at `120540` within the same database history branch. With a snapshot at SCN `120520`, Oracle can see the effects of A but not the effects of B, **provided both changes fall within the queried dataset and satisfy visibility rules**.

### 3.2. Commonly Seen SCNs

| Name / Milestone | Meaning | What Is It Used For? |
| --- | --- | --- |
| **Current SCN** | Current point recorded by the database | Observing activity, serving as a logical reference point |
| **Commit SCN** | Logical point marking a transaction commit | Determining whether changes committed before a snapshot |
| **Query/statement SCN** | Snapshot point of a consistent query | Returning data under read consistency |
| **Checkpoint SCN** | Checkpoint progress milestone for the database/datafile | Determining the starting point for redo in crash recovery |
| **Data block SCN** | Change/commit info stored in block headers | Checking block version, consistency, and recovery |
| **`RESETLOGS_CHANGE#`** | SCN at `OPEN RESETLOGS` | Identifying incarnation for backup/recovery |

These milestones have **distinct meanings**. You cannot see `CHECKPOINT_CHANGE#` lower than `CURRENT_SCN` and conclude that recently committed data is lost.

### 3.3. Viewing the Current SCN via a Read-Only Query

```sql
-- Requires read privilege on V$DATABASE (or appropriate privilege in your environment).
SELECT name,
       current_scn,
       checkpoint_change#,
       resetlogs_change#,
       log_mode
FROM   v$database;
```

Another approach using a package may require appropriate privileges:

```sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM   dual;
```

The SCN result can change between two consecutive queries. Do not treat this value as "rows updated", "milliseconds", or proof that all blocks up to that SCN have reached datafiles.

### 3.4. SCN and Wall-Clock Time

Oracle provides functions for **approximate** conversion between SCNs and timestamps while mapping information remains available within the supported window:

```sql
SELECT SCN_TO_TIMESTAMP(DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER)
       AS approximately_now
FROM   dual;
```

Not every historical SCN can be converted to a timestamp: mappings have a retention period and Oracle limits; values that are too old can raise errors such as `ORA-08181`. **`SCN_TO_TIMESTAMP` does not turn an SCN into an exact, absolute timestamp.** When performing point-in-time recovery or Flashback Query, verify that sufficient data/redo/undo exist and that the reference point is valid.

## 4. What Happens to an `UPDATE` Statement Before Commit?

Suppose row `accounts(id=1)` has `balance = 1_000_000`.

```sql
UPDATE accounts
SET    balance = balance - 500000
WHERE  id = 1;
```

Roughly speaking, Oracle performs the following:

1. Checks the row, transaction/locking, and reads the required block into the **database buffer cache** if not already present.
2. Generates an **undo record** sufficient to restore the pre-change image (e.g., the balance prior to subtraction); undo resides in a database undo segment.
3. Updates the in-cache copies of the data block and undo block; these blocks become **dirty buffers**.
4. Generates **redo change vectors** for modifications to the data block, undo block, and related transaction metadata; places redo into the **redo log buffer**.
5. Returns `1 row updated` for the `UPDATE` **without requiring the transaction to commit yet**.

At this moment, the transaction is still open:

- **The modifying session** sees its own changes.
- **Other sessions** must not see uncommitted values through normal consistent-read queries; Oracle uses undo to construct an appropriate read version.
- DBWn **may** write the dirty block down to a datafile if space or checkpointing requires it; on disk, a datafile can therefore hold an **uncommitted** change.
- LGWR **may** already have flushed part of the transaction's redo before `COMMIT`; redo written on disk does not mean the transaction has committed.

### Four Potentially Independent Outcomes

```text
Executing DML:
  Redo generated?                  YES
  Undo generated?                  YES (for normal DML on permanent tables)
  Data block dirty in cache?       YES
  Transaction committed?           NOT YET

After DML but before COMMIT:
  Can LGWR write redo?             YES
  Can DBWn write dirty block?      YES, after ensuring required redo is flushed
  Do other sessions see new row?   NO under normal consistent read
```

This is the root of two very common false beliefs: **"redo on disk = committed"** and **"data in datafile = committed"**. Both are false.

## 5. `COMMIT`: SCN, Commit Record, and LGWR

### 5.1. Standard Commit Flow

```text
Client: COMMIT
     │
     ▼
Oracle assigns a commit SCN to the transaction
     │
     ▼
Creates commit record and related transaction info in redo
     │
     ▼
LGWR writes required redo, including commit record, to online redo logs
     │
     ▼
Redo is durable (standard synchronous commit)
     │
     ▼
Oracle returns "Commit complete" to the client
     │
     └──────────────► DBWn can write datafiles later, when appropriate
```

At commit, Oracle updates the transaction's logical state and assigns a **commit SCN**. With **standard synchronous `COMMIT`**, LGWR writes the required redo records along with the commit record down to the online redo log before Oracle returns success. This is the foundation of **fast commit**: there is no need to wait for DBWn to write every data block of the transaction to datafiles.

A single LGWR write can contain **multiple commit records from multiple transactions** (*group commit*), reducing I/O operations without violating commit ordering or durability.

### 5.2. Commit SCN Differs from Checkpoint SCN

Suppose at inspection time:

```text
Current SCN           = 135900
Transaction X commit  = 135880
Checkpoint SCN        = 135200
```

There is **no contradiction** here. Transaction X has committed and its required redo can sit safely in the online redo log. DBWn may not yet have flushed all data blocks belonging to transaction X; checkpoints have not yet advanced to that milestone. If the instance crashes, instance recovery applies redo after the corresponding checkpoint milestone to recover X.

### 5.3. Exception to Know: `COMMIT WRITE NOWAIT`

The `COMMIT WRITE ... NOWAIT` clause allows Oracle to **return control to the client before commit redo finishes durable writing**; if the instance fails right in that window, the client may already have received success while redo is still at risk of loss. Oracle advises understanding the durability trade-off before using this mode. Hence the statement "Oracle always flushes redo before reporting commit success" holds only for **standard synchronous `WAIT` commit**, not every asynchronous commit option.

```sql
-- Syntax illustration related to durability trade-offs;
-- do not use NOWAIT in financial transaction labs.
COMMIT WRITE WAIT IMMEDIATE;
```

In addition, a network failure right around commit creates a special case: the server **may already have committed** while the client never received the reply. Applications should not blindly retry non-idempotent transactions without determining the final outcome; critical systems should examine mechanisms for resolving ambiguous commit outcomes (*Transaction Guard* or proper idempotency design).

## 6. Redo: The Log That Moves Forward After a Failure

### 6.1. What Does Redo Store?

Redo is not simply a text file re-recording SQL statements. Oracle writes **redo records**, containing **change vectors** that describe modifications to data blocks. One `UPDATE` statement can generate redo for:

- Modified table and/or index data blocks.
- Undo blocks containing information able to reverse the change.
- Transaction tables and related metadata.
- Rollback steps themselves can also generate additional redo because they modify blocks again.

LGWR writes redo sequentially, which from an I/O standpoint is generally far more favorable than DBWn writing dirty blocks scattered across datafiles.

### 6.2. Write-Ahead Logging (WAL)

A vital Oracle rule is **writing the required redo to disk before writing the corresponding dirty data block to a datafile**. If DBWn wants to write a dirty block whose associated redo has not yet been flushed by LGWR, DBWn must wait for LGWR to complete the required redo write.

```text
UPDATE generates redo R and dirty block B
                  │
                  ▼
         LGWR flushes R first
                  │
                  ▼
      DBWn may then write block B
```

From this, we see why Oracle can safely write an **uncommitted dirty block** down to a datafile: the operations needed to recover and—if the transaction never commits—undo it via reconstructed undo have already been logged.

### 6.3. Online Redo and Archived Redo Are Not the Same

| | Online Redo Log | Archived Redo Log |
| --- | --- | --- |
| Source | LGWR writes to log groups in rotation | ARCn copies log group contents after a log switch (when `ARCHIVELOG`) |
| Core purpose | Protects and recovers instance operation; holds newest redo | Preserves redo history for backup/media recovery, standby, and point-in-time recovery |
| Overwritten in rotation? | Yes, once Oracle determines a log is eligible for reuse | Not overwritten by the online redo group cycle; requires its own retention policy |
| Requires `ARCHIVELOG`? | No | Yes |

**Instance recovery** after an ordinary instance crash can use **online redo logs and current datafiles**, without necessarily needing archived redo logs. Conversely, **media recovery** from an older backup or after losing a datafile usually requires complete archived redo (and potentially the latest online redo) to bring data to the target point. A `NOARCHIVELOG` database still has online redo for instance recovery, yet its ability to recover from backups is severely restricted.

### 6.4. What If Redo Was Written and the Transaction Rolls Back?

A transaction's redo is not deleted on rollback. Oracle uses undo to reverse uncommitted changes, and the rollback operation itself can generate redo. When reading redo, **transaction state / commit markers** must be considered; do not assume every change vector represents a final committed change.

## 7. Undo: Information to Revert to Prior Images and Build Read Versions

### 7.1. Where Does Undo Live?

For normal DML on permanent data, Oracle maintains undo in **undo segments** belonging to an **undo tablespace**. Undo consists of **database blocks**, managed, cached, and written to datafiles just like other data blocks. Because undo blocks are themselves modified, undo modifications normally generate **redo for undo**.

This is a crucial point: **undo is not "an opposite file to the redo log"**. Undo is in-database data serving reversal/versioning; redo is the change stream—**including changes to undo blocks**—used to reconstruct the database after a crash.

Oracle has separate management for temporary undo on temporary objects; special operations such as no-logging modes or deferred inserts also have exceptions. This lesson focuses on the **standard permanent-table DML transaction flow with redo and undo**.

### 7.2. Four Roles of Undo

1. **Explicit rollback:** `ROLLBACK` or `ROLLBACK TO SAVEPOINT` undoes uncommitted changes.
2. **Transaction recovery:** after a crash, Oracle undoes transactions without a durable commit.
3. **Read consistency:** constructs block images as of the appropriate SCN for running queries, even when writers have already modified the block.
4. **Certain Flashback operations:** queries data as of an earlier SCN/timestamp, provided the required undo still exists.

### 7.3. Undo Does Not Vanish Immediately After Commit

After `COMMIT`, undo from the just-completed transaction **may continue to be retained** to serve queries that began before the commit, Flashback Query, and other consistent-read needs. Oracle manages the lifecycle of undo extents and reuses them when appropriate.

```text
Active transaction      → undo is ACTIVE, required for rollback
Committed transaction   → undo is no longer ACTIVE for that transaction's rollback
                          but may still be retained for consistent reads
Retention/conditions met→ undo may be reused
```

`UNDO_RETENTION` is a setting influencing the undo retention goal; **it does not automatically guarantee every historical query succeeds** without sufficient undo space and appropriate retention guarantee settings. When undo needed for a snapshot has already been overwritten, a query can encounter `ORA-01555: snapshot too old`.

### 7.4. A Row Is Updated Yet a Reader Still Sees the Old Value

```text
T0: Row balance = 1,000,000 is committed.

T1: Session A UPDATEs balance = 500,000; not yet COMMITted.
    ├─ Data block in cache may hold 500,000.
    ├─ Undo holds sufficient info to restore 1,000,000.
    └─ Redo describes changes to both data + undo.

T2: Session B SELECTs balance under READ COMMITTED.
    └─ Sees 1,000,000 via consistent read; no dirty read of 500,000.

T3: Session A COMMITs (commit SCN = 120500).

T4: Session C starts a new SELECT with snapshot SCN > 120500.
    └─ Sees 500,000.

T5: Session B has an earlier SELECT started before T3 still running.
    └─ Oracle continues ensuring an image consistent with the SCN when that SELECT started.
```

**Oracle does not have to block readers with locks on rows being updated by a writer.** Oracle creates a **consistent read (CR) clone** of the block when needed and applies undo to construct the image as of the SCN the query is permitted to see. Exception to recognize: `SELECT ... FOR UPDATE` is a query intended to lock rows, differing from an ordinary consistent `SELECT`.

## 8. What Is a Checkpoint Really?

### 8.1. Purpose: Shortening the Redo Span Needed for Instance Recovery

The database buffer cache holds many dirty buffers. If the instance dies abruptly, dirty buffers not yet written by DBWn vanish from RAM; Oracle needs redo to replay those changes. A **checkpoint** marks the progress of written dirty buffers and establishes the starting redo position needed for instance recovery.

According to Oracle documentation, a checkpoint position is a **position in the redo thread** associated with the **oldest dirty buffer**; the checkpoint SCN indicates a corresponding guaranteed recovery milestone. Oracle can continue operating and modifying blocks while checkpointing progresses: checkpoints do not freeze the entire database into a simple physical snapshot.

```text
Redo timeline (illustrative SCNs)

1000      1100      1200      1300      1400      1500
 |---------|---------|---------|---------|---------|
                          ▲                         ▲
                  checkpoint SCN                current SCN
                          │
                redo before this point is
                covered by the corresponding
                checkpoint for recovery
                          │
                          └────► redo after this point must be examined
                                 if the instance crashes
```

**Oracle Database Concepts 19c** describes the checkpoint position as guaranteeing that **committed** changes with an SCN lower than the checkpoint SCN have been written to datafiles for that checkpoint. However, **datafiles can still contain blocks with SCNs newer than the checkpoint** (even uncommitted changes), because DBWn is not forced to write every block in strict transaction order.

### 8.2. CKPT Differs from DBWn

- **DBWn** directly writes dirty data/undo blocks from the database buffer cache into datafiles.
- **CKPT** updates checkpoint info in the control file and datafile headers, and signals/coordinates DBWn to advance checkpoints.
- **LGWR** writes redo into online redo logs; CKPT does not write redo in place of LGWR.

```text
                 ┌────────────────┐
                 │ CKPT           │
                 │ coordinates &  │
                 │ records ckpt   │
                 │ metadata       │
                 └───────┬────────┘
                         │
             ┌───────────┴────────────┐
             ▼                        ▼
       Control file +           Signals DBWn
       datafile header          to flush buffers
             ▲                        │
             │                        ▼
             │                 Datafile contents
             │                 written by DBWn
             └────────────────────────┘
```

### 8.3. Incremental Checkpoints vs. Full Checkpoints

Modern Oracle continuously performs **incremental checkpoints** to advance the recovery starting point without waiting for every dirty buffer in the database to be written at once. DBAs can configure target recovery time goals via **Fast-Start Checkpointing** / `FAST_START_MTTR_TARGET` in supported environments.

**Full checkpoints** or broader checkpoints occur in specific situations, such as certain database shutdowns, file/tablespace status changes, and administrative events. Detailed checkpoint triggers depend on version and operation type; do not assume every `COMMIT` or every **log switch** waits for all dirty buffers in the entire database to finish writing.

A log switch can trigger checkpoint activity/demand, yet the switch itself can complete while checkpointing/DBWn continues running. If checkpoints have not advanced far enough, Oracle may not yet be allowed to reuse an online redo log group still needed for crash recovery, producing wait messages like **checkpoint not complete**.

### 8.4. Checkpoint SCNs Need Not Be Equal Across All Datafiles

Oracle tracks checkpoint information at both the **database and individual datafile** levels. Offline/read-only files, tablespaces in different states, or backup/recovery operations can cause checkpoint milestones across files to differ. Compare against the right file and state; do not subtract `V$DATAFILE_HEADER.CHECKPOINT_CHANGE#` from `V$DATABASE.CURRENT_SCN` and claim it represents seconds of data loss or recovery duration.

During an **online** backup, a datafile copy can be in a **fuzzy** state because blocks were copied at different times. To restore it to a consistent state, appropriate redo is required; checking only the file header is insufficient to declare a backup directly openable without recovery.

## 9. Why Can a Datafile Contain Uncommitted Data?

A valid sequence of events:

```text
1. Transaction T1 UPDATEs row R from 'A' to 'B'.
2. Oracle generates undo for image 'A' and redo for data/undo changes.
3. LGWR flushes the relevant redo per the write-ahead protocol.
4. DBWn writes the dirty data block holding 'B' down to a datafile.
5. T1 HAS NOT COMMITTED; on disk, the block already contains 'B'.
6. Another session SELECTs row R → receives 'A' via read consistency.
7. T1 ROLLBACKs → Oracle applies undo to restore 'A'.
```

Thus, a datafile **cannot by itself be interpreted as containing only committed data at one uniform timestamp**. Transaction state, undo, and redo are integral to determining the final valid data.

Conversely, another valid sequence:

```text
1. T2 UPDATEs row S from 'X' to 'Y'.
2. T2 COMMITs; commit record is durable in the redo log.
3. DBWn has not yet written block S down to a datafile.
4. Instance crashes; buffer cache is lost.
5. Oracle reads online redo and reapplies the committed update.
6. Recovery completes: 'Y' is preserved.
```

**Standard synchronous commit durability depends on durable redo**, not on DBWn having flushed every datafile at the exact second of commit.

## 10. Instance Recovery: REDO Rolls Forward, UNDO Rolls Back

### 10.1. Two Fundamental Phases

When an Oracle instance terminates abnormally yet **current datafiles and required online redo logs remain intact**, Oracle performs instance recovery:

**Phase A — Roll forward / cache recovery.** Oracle reads required redo starting from the appropriate checkpoint position and **reapplies changes** not yet fully reflected in datafiles. Because redo also records changes to undo blocks, this phase also reconstructs the undo needed for the next step. Roll forward can leave datafiles temporarily containing changes from both committed and uncommitted transactions.

**Phase B — Rollback / transaction recovery.** Oracle identifies transactions that had not committed cleanly at failure time and **uses undo** to reverse their changes. Recovery/rollback can proceed in parallel or on demand as blocks are accessed, depending on Oracle mechanisms.

```text
                  Instance loses power
                          │
                          ▼
        Read checkpoint position and redo thread
                          │
                          ▼
            ROLL FORWARD using REDO
       ┌────────────────────────────────┐
       │ Reapply data + undo changes    │
       │ for both committed and         │
       │ needed uncommitted txns        │
       └────────────────┬───────────────┘
                        │
                        ▼
          Identify open transactions
                        │
                        ▼
             ROLLBACK using UNDO
       ┌────────────────────────────────┐
       │ Undo uncommitted changes       │
       └────────────────┬───────────────┘
                        │
                        ▼
         Database transactionally consistent
         (committed retained, uncommitted undone)
```

### 10.2. Example of Three Transactions at Crash Time

Suppose initial committed data is:

```text
A = 10
B = 20
C = 30
```

Just before the crash:

| Transaction | Action | Redo in online log? | Durable commit record? |
| --- | --- | --- | --- |
| **T1** | Updates `A=11` | Yes | **Yes**, commit SCN 7100 |
| **T2** | Updates `B=21` | Yes | **No** |
| **T3** | Updates `C=31` | Yes | **Yes**, commit SCN 7200 |

DBWn might already have written block `B=21` while not yet writing `A=11` or `C=31`. That is completely valid and does not dictate which transactions committed. After instance recovery:

```text
A = 11  ← T1 committed; redo recovers it if block hadn't reached datafile.
B = 20  ← T2 did not commit; undo removes the change.
C = 31  ← T3 committed; redo recovers it if needed.
```

Under standard synchronous commit, success is defined by the durable commit record in redo. `NOWAIT` modes or storage failures losing required redo must be analyzed separately; do not use this example to promise full recovery regardless of storage corruption.

### 10.3. Why Is Redo for Undo Also Needed?

If only data-block redo existed, Oracle might reapply an uncommitted change and then **have no undo left** in RAM after power loss. Because undo also resides in the database and undo changes have corresponding redo, Oracle can reconstruct undo segments during roll forward and then undo failed transactions.

This is the architectural partnership: **redo ensures required changes can be replayed, while undo ensures the final transactional state is correct**. They complement rather than replace each other.

### 10.4. Instance Recovery Differs from Media Recovery

| Scenario | Remaining Data | Primary Mechanism |
| --- | --- | --- |
| Instance crashes; datafiles and online redo remain intact | Current datafiles + online redo | **Instance recovery**: roll forward and rollback |
| Datafile lost or corrupted; must restore from backup | Older datafile backup, required redo | **Media recovery**: restore + apply appropriate archived/online redo |
| Need to rewind before an accidental operation | Backup/redo or appropriate Flashback feature | Point-in-time recovery or Flashback, depending on case |
| All copies of required online redo lost while datafiles lack latest commits | May lack enough info for full recovery | Evaluate backups/archives/protection setup; **never** promise zero data loss |

Checkpoints reduce the redo reapplied during **instance recovery**, yet **they do not replace backups, archived redo, Data Guard, or a DR plan**.

## 11. SCN and Read Consistency: "Committed" Data Also Depends on Viewpoint

### 11.1. Snapshot of a SELECT

Under the default `READ COMMITTED` isolation level, an Oracle query has a **statement-level** snapshot: the `SELECT` sees committed data consistent **with the SCN when the query began**, plus uncommitted changes made by its own transaction if any.

```text
SCN 8000: A commits product price = 100.
SCN 8010: Session B starts a 20-second SELECT.
SCN 8020: A commits UPDATE product price = 120.
SCN 8030: B is still reading the tail of its earlier SELECT.

B cannot arbitrarily read half the query at price=100 and half at price=120.
Oracle uses undo when needed to build a consistent image at snapshot SCN 8010.
```

Under `READ COMMITTED` isolation, **a subsequent SELECT** in the same transaction can see a newer version committed after the earlier SELECT. Thus `READ COMMITTED` guarantees **statement-level consistency**, not that repeating a SELECT always returns identical results.

### 11.2. `SERIALIZABLE` and `READ ONLY`

Under `SERIALIZABLE` isolation, queries within the same transaction see a consistent snapshot as of the transaction start point (while still seeing the transaction's own changes). You must also understand update conflicts and errors such as `ORA-08177` when Oracle cannot serialize a transaction attempting to modify data. A read-only transaction can likewise use a consistent multi-query snapshot per Oracle semantics.

Snapshot SCNs also explain **data that is committed yet not yet visible in a running query**: the commit happened **after** the query's snapshot SCN, not because DBWn had not yet written the data to a datafile.

### 11.3. `ORA-01555: snapshot too old`

A long-running query needs to read an image as of an older SCN. While other transactions continue modifying data, the undo needed to construct that older image may be overwritten if not retained long enough. The query can hit `ORA-01555`. This is a **historical image retention issue**, not a sign that newly committed transactions were lost or redo failed.

Factors to investigate: query duration, undo generation rate, undo tablespace size, retention policy, transaction lifetimes, and how the application fetches data. Do not treat raising `UNDO_RETENTION` alone as a cure-all when undo space is insufficient.

### 11.4. Flashback Query `AS OF SCN`

When needing to view an earlier point in time while sufficient undo remains:

```sql
-- The SCN below is illustrative; choose an SCN still valid on the live DB.
SELECT account_id, balance
FROM   accounts AS OF SCN 8000
WHERE  account_id = 1;
```

`AS OF SCN` requires query privileges and sufficient undo history, and is subject to object/DDL and retention limits. **Redo/archived redo is not direct storage that Flashback Query arbitrarily searches for any past SCN.** Do not expect `ARCHIVELOG` mode to make every very old `AS OF SCN` query succeed.

## 12. Comparing Redo, Undo, Checkpoint, and Commit in One Table

| Question | **Redo** | **Undo** | **Checkpoint** | **Commit** |
| --- | --- | --- | --- | --- |
| What does it answer? | How to replay changes? | How to revert to a prior image? | What has been written enough to bound recovery? | Did the transaction finish successfully? |
| Primary storage | Online redo logs; archived copies when archiving enabled | Undo segments in undo tablespace | Metadata in control file/datafile headers and dirty buffer progress | Transaction state/commit record in redo, tagged with commit SCN |
| Primary actor | LGWR writes logs | Server process creates; used by rollback/consistent read/recovery | DBWn writes blocks, CKPT updates milestone | Server/LGWR coordinate transaction commit |
| Can exist before commit? | **Yes** | **Yes** | **Yes, independent of individual commits** | No, it is the commit event itself |
| Can have effects after commit? | Written redo is used for recovery | Undo can still serve older readers | Continues advancing the milestone | Commit SCN governs visibility |
| Equivalent to datafiles written? | No | No | Indicates write progress per checkpoint milestone | No |
| Role during crash | Roll forward | Roll back uncommitted transactions | Determines appropriate recovery start point | Distinguishes durably committed transactions |

**One-line interpretation example:** `T1 COMMIT at SCN 9000; checkpoint is at SCN 8800` means the transaction can already be durable via redo even though its dirty blocks may not yet have been flushed by DBWn. If the instance crashes, Oracle can use redo after the checkpoint and undo for other uncommitted transactions.

## 13. Two-Session Lab: Observing Visibility and Rollback

> **Perform only on a lab database and schema you are authorized to modify**. DDL statements perform implicit commits; never use real data tables or production accounts. The SQL below illustrates ordinary DML on a permanent table.

### 13.1. Setup in Session A

```sql
-- Session A, in the lab schema.
CREATE TABLE scn_checkpoint_lab (
    id      NUMBER PRIMARY KEY,
    balance NUMBER NOT NULL
);

INSERT INTO scn_checkpoint_lab(id, balance) VALUES (1, 1000);
COMMIT;

SELECT id, balance FROM scn_checkpoint_lab;
-- 1 | 1000
```

`CREATE TABLE` DDL performs an implicit commit before/after succeeding. Therefore do not mix DDL steps into a transaction used to observe rollback.

### 13.2. Session A Modifies Without Committing

```sql
-- Session A
UPDATE scn_checkpoint_lab
SET    balance = 900
WHERE  id = 1;

SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- Session A sees 900 (read-your-own-writes).

-- NOT YET COMMITTED.
```

Open Session B, logged into the same schema or with privileges to view A's table:

```sql
-- Session B (default READ COMMITTED)
SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- Sees 1000; does not see uncommitted 900.
```

At this moment, undo needed for rollback/consistent read has been created; redo has also been created for data/undo changes. No plain business SQL proves exactly which data buffers DBWn flushed down to the millisecond.

### 13.3. Session A Commits, Session B Reads Again

```sql
-- Session A
COMMIT;

-- Session B, a NEW SELECT
SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- Sees 900.
```

This verifies **read consistency** and **commit visibility**, yet **does not prove** Oracle wrote the data block to a datafile at the exact moment of commit.

### 13.4. Rollback: Changes That Generated Redo Still Do Not Become Final

```sql
-- Session A
UPDATE scn_checkpoint_lab SET balance = 700 WHERE id = 1;
SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- 700

ROLLBACK;

SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- 900
```

Here Oracle uses undo to reverse the uncommitted update. Redo previously generated for the `UPDATE` is not erased from the online redo log. Restoring `900` is transactional logic, not physically deleting every trace of redo.

### 13.5. Cleaning Up the Lab After Finishing

```sql
-- Only in the lab schema, after confirming the exact table to clean up.
DROP TABLE scn_checkpoint_lab PURGE;
```

Do not test `SHUTDOWN ABORT`, `ALTER SYSTEM SWITCH LOGFILE`, or `ALTER SYSTEM CHECKPOINT` on a database serving live workloads just to watch the lesson. Those administrative commands have real system impact and are unnecessary to understand the mechanism.

## 14. Architectural Observation Queries via SQL (Read-Only)

`V$...` dynamic views require appropriate privileges (usually DBA or explicit view read grants). In CDB/PDB and RAC, results also depend on the container/instance the session is querying. The following queries **only view information**, without forcing checkpoints or changing configuration.

### 14.1. Current SCN, Checkpoint, Archive Mode

```sql
SELECT name,
       current_scn,
       checkpoint_change#,
       resetlogs_change#,
       log_mode,
       open_mode
FROM   v$database;
```

- `CURRENT_SCN` shows the database's current SCN per the view.
- `CHECKPOINT_CHANGE#` is the checkpoint milestone reported by the control file.
- `RESETLOGS_CHANGE#` relates to database incarnation.
- `LOG_MODE` is `ARCHIVELOG` or `NOARCHIVELOG` (other values also exist in special cases).

**Do not** use `CURRENT_SCN - CHECKPOINT_CHANGE#` as a direct formula to predict recovery duration, transactions not yet in datafiles, or potential data loss.

### 14.2. Per-Datafile Checkpoint and File Headers

```sql
-- Metadata from the control file.
SELECT file#,
       name,
       checkpoint_change#,
       status
FROM   v$datafile
ORDER BY file#;

-- Actual metadata read from datafile headers.
SELECT file#,
       name,
       checkpoint_change#,
       fuzzy,
       recover
FROM   v$datafile_header
ORDER BY file#;
```

`V$DATAFILE` reads file info from the **control file**, whereas `V$DATAFILE_HEADER` reads info from **datafile headers**. Compare both sources when diagnosing restore/recovery; a difference alone is insufficient to conclude restore or recovery is needed. `FUZZY`/`RECOVER` flags must be interpreted by a DBA in the specific context of open/backup/recovery state.

### 14.3. Redo Log Groups and SCN Ranges

```sql
SELECT group#,
       thread#,
       sequence#,
       status,
       archived,
       first_change#,
       next_change#
FROM   v$log
ORDER BY thread#, group#;
```

`V$LOG` shows redo threads, log sequences, `CURRENT`/`ACTIVE`/`INACTIVE` status, and log group SCN boundaries. `NEXT_CHANGE#` on a **CURRENT** log can be a very large sentinel value rather than an actual future milestone. Do not equate `ACTIVE` with uncommitted transactions in that group; `ACTIVE` can mean the log is still needed for crash recovery. In RAC, each instance has its own redo thread and all relevant threads must be checked.

### 14.4. Undo Info and Long-Running Queries

```sql
SELECT begin_time,
       end_time,
       undoblks,
       maxquerylen,
       ssolderrcnt,
       tuned_undoretention
FROM   v$undostat
ORDER BY begin_time DESC
FETCH FIRST 20 ROWS ONLY;
```

`V$UNDOSTAT` helps investigate undo activity over time intervals: generated undo volume, max query length, and observed **snapshot too old** errors. It does not directly return every undo record of a specific transaction. Statistical values, aggregation rules, and instance scope should be read alongside your release's documentation.

Observing configuration:

```sql
SELECT name, value
FROM   v$parameter
WHERE  name IN (
           'undo_management',
           'undo_tablespace',
           'undo_retention',
           'fast_start_mttr_target'
       )
ORDER BY name;
```

The `FAST_START_MTTR_TARGET` parameter relates to target instance recovery time and incremental checkpoint pacing; **it is not a strict guarantee that every crash recovers in exactly N seconds**.

### 14.5. Distinguishing "Read-Only Metadata" from "Forcing a Checkpoint"

| Action | Impact Scope |
| --- | --- |
| `SELECT ... FROM V$DATABASE` | Observes SCN and metadata |
| `SELECT ... FROM V$DATAFILE_HEADER` | Observes header metadata; does not force a full checkpoint |
| `SELECT ... FROM V$UNDOSTAT` | Observes undo statistics |
| `ALTER SYSTEM CHECKPOINT` | **Administrative action**, forces checkpoint activity, generates I/O; unnecessary for this lab |
| `ALTER SYSTEM SWITCH LOGFILE` | **Administrative action**, switches redo group; can affect archiving/checkpoints |
| `SHUTDOWN ABORT` | **Causes abnormal instance stop**; use only in controlled, authorized testing |

Do not run administrative commands merely to watch an SCN number change. The mechanics of commit and recovery are already demonstrated through the session lab and read-only dynamic views.

## 15. Advanced Cases to Separate Clearly

### 15.1. Data Guard: SCN and Redo Transport to Standby

In Data Guard, the primary generates redo; the standby receives and can apply redo to maintain a replica. Concepts like **redo sequence**, **thread**, **transport lag**, **apply lag**, **commit SCN**, and **checkpoint** are related yet distinct. A successful `COMMIT` on the primary does not automatically mean the standby has already **applied** up to that commit SCN: that depends on protection mode, sync transport, apply progress, and architecture.

When asking "does the standby have transaction X yet?", check **whether redo arrived, whether redo was applied, and what query mode the standby is open in**. Never look only at `CURRENT_SCN` on the primary.

### 15.2. RAC: Multiple Redo Threads, One Logical Database

In RAC, instances share one database while each instance has its own redo thread. Oracle coordinates SCNs and cache fusion mechanisms to maintain consistent ordering and data. When instance recovery must recover a failed instance, Oracle inspects the **corresponding redo thread** and recovery state; do not assume a single online redo file describes the entire cluster's activity.

### 15.3. CDB/PDB: Snapshots and Undo per Container

In multitenant, services route sessions to PDBs; undo can be configured in **shared undo** or **local undo mode**, depending on release and deployment. Lessons on SCN, redo, and consistency still apply, though dynamic view scope, metadata access privileges, and undo placement must be determined by the actual container. In RAC/PDB, do not treat a single-instance example as an exact physical topology diagram.

### 15.4. `NOLOGGING` and Special Write Optimizations

Certain direct-path operations or operations using `NOLOGGING` **do not log full redo for data changes** like normal DML; redo may still be generated for dictionary/metadata and mandatory structures. This creates risk if media recovery from backup is needed, especially when archived redo lacks enough block changes to reconstruct contents. `FORCE LOGGING`, backup policy, and operation traits must be designed by a DBA.

Similarly, optimizations for temporary objects or deferred writes have their own redo/undo/durability rules. **Do not use those exceptions to invalidate the normal permanent-table DML model** explained here.

## 16. Diagnosing Real Symptoms Using the SCN–Redo–Undo–Checkpoint Model

### Symptom 1: "The app reports commit succeeded, yet the datafile's timestamp didn't change"

Usually **not an error**. LGWR flushes commit redo under synchronous protocol; DBWn may write datafiles later. A filesystem mtime is not a tool for checking commit SCNs or transaction state.

### Symptom 2: "A very long query still sees old values even though another session committed"

This can be normal under **statement-level read consistency**. The query uses its starting snapshot SCN, and Oracle builds CR versions from undo. A new query under `READ COMMITTED` can see the new value; if undo is exhausted, `ORA-01555` may occur.

### Symptom 3: "The datafile already contains a new value, yet rollback still restores the old value"

Completely possible. DBWn is allowed to write dirty buffers of an uncommitted transaction once the associated redo is durable. Undo restores transactional logic; a datafile holding a newer physical block does not make that data committed.

### Symptom 4: "After `SHUTDOWN ABORT`, Oracle requires recovery despite many prior checkpoints"

Checkpoints only **reduce** the span of redo to process; they do not eliminate all unflushed dirty buffers or uncommitted transactions. Instance recovery rolls forward required redo from the checkpoint and then rolls back uncommitted transactions. A clean controlled shutdown follows a different path from a crash.

### Symptom 5: "Redo log switch stalls with checkpoint not complete"

DBWn/CKPT have not pushed the recovery milestone far enough for the redo group slated for reuse to be safe. Check redo group size/count, redo generation rate, datafile write I/O, MTTR targets, and archiving status. **Do not try to fix this by issuing commits**; commit does not complete checkpoints.

### Symptom 6: "Archived redo exists, yet an old `AS OF SCN` query still fails"

Flashback Query uses undo to construct historical images within the supported window; archived redo primarily serves recovery/standby and does not automatically replace overwritten undo. For deep historical queries, evaluate Flashback Data Archive (when appropriate) or alternative history/backup strategies.

### Symptom 7: "Session crash lost data despite receiving a commit confirmation"

Verify **commit mode** (`WAIT` vs. `NOWAIT`), storage reliability/configuration, failure type, online redo status, and transaction logs. If the server performed a durable synchronous commit yet the client disconnected before receiving the reply, the outcome is **ambiguous to the client** rather than the database losing the commit. Do not equate an application timeout with a rollback.

## 17. Reinforcement Questions

**Question 1.** After `UPDATE` but before `COMMIT`, which statement can be true?

A. No redo exists yet because the transaction hasn't committed.  
B. DBWn cannot write the block before commit.  
C. Redo may already be in the online redo log and a datafile may contain the uncommitted dirty block.  
D. Other sessions always see the new value.

**Question 2.** `CURRENT_SCN=50000`, `CHECKPOINT_CHANGE#=49200`, yet transaction X committed at 49900. Can we conclude X is not durable?

**Question 3.** Why does recovery not just roll forward redo, and also require undo?

**Question 4.** Under `READ COMMITTED`, the first SELECT sees `A=100`; another session commits `A=110`; can a second SELECT in the same transaction see `110`?

**Question 5.** A very old `AS OF SCN` query fails even though the database has `ARCHIVELOG` enabled. What information is missing to draw a conclusion?

<details>
<summary>Answer Hints</summary>

1. **C.** Redo is generally created as blocks change and can be written by LGWR before commit; DBWn can write uncommitted blocks after required redo is written.
2. **No.** Commit SCN and checkpoint SCN serve different roles; a transaction can already be durable via online redo without datafiles yet flushing every block.
3. Because roll forward also reconstructs changes from uncommitted transactions; undo is needed to revert them to a valid image and restore atomicity.
4. **Yes.** Under `READ COMMITTED`, each SELECT gets its own snapshot; a second SELECT starting after the commit can see `110`.
5. You need to check whether undo for that snapshot still exists, whether the SCN is valid, whether DDL altered the table, Flashback privileges, and operation type. Archived redo does not guarantee Flashback Query for arbitrary SCNs.

</details>

## 18. Official Oracle Documentation

1. [Oracle Database 19c Concepts — Process Architecture](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/process-architecture.html): LGWR, fast commit, group commit, write-ahead protocol, DBWn, and CKPT.
2. [Oracle Database 19c Concepts — Oracle Database Instance](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/oracle-database-instance.html): checkpoints, purpose of instance recovery, roll forward, and rollback.
3. [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): query SCNs, MVCC/consistent read, undo, and transaction isolation.
4. [Oracle Database 19c Concepts — Logical Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/logical-storage-structures.html): undo segments, undo tablespace, rollback, and block version history.
5. [Oracle Database 19c Concepts — Physical Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/physical-storage-structures.html): online/archived redo logs, redo records, and change vectors.
6. [Oracle Database 19c SQL Language Reference — COMMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COMMIT.html): commit, `WAIT`/`NOWAIT`, `IMMEDIATE`/`BATCH`, and durability.
7. [Oracle Database 19c Database Reference — V$DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html), [V$DATAFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE.html), [V$DATAFILE_HEADER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE_HEADER.html), and [V$LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG.html): meaning of SCN/redo/checkpoint metadata.
8. [Oracle Database 19c Database Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): undo statistics and read-consistency troubleshooting.

**Causal chain to remember when reading an Oracle system:** DML modifies data and generates undo/redo → LGWR writes redo per the write-ahead protocol → synchronous commit succeeds when commit redo is durable → DBWn writes dirty blocks when appropriate → CKPT records checkpoint progress → if a crash occurs, redo replays needed changes and undo reverses uncommitted transactions → snapshot SCN determines which data version each query is permitted to see.
