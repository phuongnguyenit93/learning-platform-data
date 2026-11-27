# DBWn, LGWR, CKPT, SMON, PMON, and Their Coordinated Roles

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Architecture  
> **Objective:** Understand the five key background process groups of Oracle Database—knowing which process writes data, which writes redo, who coordinates checkpoints, who assists with crash recovery, and who cleans up when a user process fails.

## 1. Where Background Processes Fit in Oracle Architecture

A running Oracle Database is more than just tables and data files. At a high level, it consists of two cooperating parts:

- **Database:** the set of physical files, notably **datafiles**, **control files**, and **online redo logs**.
- **Instance:** the shared memory **SGA (System Global Area)** together with **background processes** that run database operations.

When an application connects and runs SQL, a **server process** performs the work for the session: reading and modifying blocks in memory, generating undo/redo information, and handling transactions. Background processes handle behind-the-scenes duties such as writing blocks, writing redo, checkpointing, and cleaning up after failures. Process-private memory is called the **PGA**; this lesson focuses on the SGA and directly related background processes.

Two SGA components to recognize:

1. **Database Buffer Cache:** stores copies of actively accessed data blocks. A block modified in the cache but not yet written to a datafile is a **dirty buffer**.
2. **Redo Log Buffer:** holds **redo entries** describing changes needed for replay during recovery. Redo entries are written by LGWR out to online redo logs.

A simplified model:

```text
          Application / SQL Developer / JDBC
                        |
                        v
                Server process
                        |
              +---------+---------+
              |                   |
              v                   v
     Database Buffer Cache   Redo Log Buffer
        (SGA, data blocks)   (SGA, redo entries)
              |                   |
             DBWn                LGWR
              |                   |
              v                   v
          DATAFILES         ONLINE REDO LOGS
              ^
              |
       CKPT coordinates checkpoints,
       tracks progress milestones, and
       updates checkpoint info
       in CONTROL FILE / datafile headers

     SMON: instance recovery after crash
     PMON: monitors and cleans up failed processes
```

This is a **responsibility diagram**; it does not mean CKPT directly writes data blocks or that one SQL statement sequentially triggers each process one by one. These processes operate concurrently depending on activity type and system state.

### Quick Comparison Table

| Process | Common Full Name | Primary Responsibility | Primary Work Target |
|---|---|---|---|
| **DBWn** | Database Writer | Writes dirty buffers from the buffer cache out to datafiles | Datafiles |
| **LGWR** | Log Writer | Writes redo from the redo log buffer out to online redo logs | Online redo logs |
| **CKPT** | Checkpoint Process | Coordinates and records checkpoint progress information | Control file, datafile headers |
| **SMON** | System Monitor | Coordinates instance recovery when needed; performs certain system maintenance tasks | Database state, redo/undo during recovery |
| **PMON** | Process Monitor | Monitors and cleans up consequences when user/server processes fail | Sessions and associated resources |

The notation **DBWn** emphasizes that there can be multiple database writers—such as `DBW0`, `DBW1`—depending on version and configuration. These processes are internal components of the Oracle instance; users do not need to and should not spawn them manually via application scripts.

## 2. Before Going Deeper: How Do Data, Redo, and Undo Differ?

The three concepts most easily confused in this topic are **data block**, **redo**, and **undo**.

| Component | What Is It Used For? | Where Does It Live? | Relationship to Processes |
|---|---|---|---|
| **Data block** | Carries table, index, and metadata contents | Buffer cache and datafiles | DBWn flushes dirty blocks from cache down to datafiles |
| **Redo** | Records changes for replay when recovery is needed | Redo log buffer, online redo logs, and archived redo logs when archiving is enabled | LGWR writes redo into online redo logs |
| **Undo** | Enables transaction rollback and consistent reads of older versions | Undo segments in undo tablespace; undo blocks also pass through cache | Server processes generate undo; changes to undo blocks also generate redo |

Key takeaways:

- **Redo is not a full snapshot copy of an entire table.** Redo records sufficient change information for Oracle to perform recovery mechanisms.
- **Undo is not the online redo log.** Undo enables reverting to a valid logical state on rollback and supports consistent reads.
- **DBWn can write a block modified by an uncommitted transaction.** This does not automatically commit the transaction, because redo and undo preserve Oracle's ability to restore the correct state.
- **Commit does not require DBWn to immediately write every dirty block to a datafile.** Standard commit relies on redo, including the commit record, being durably written by LGWR.

For example: an `UPDATE` statement modifies a row in the buffer cache. Redo representing the change is placed in the redo log buffer; undo retains the information needed for rollback/read consistency. At any instant, both the new data in the buffer cache and the redo/undo may be awaiting separate disk writes.

### Write-Ahead Logging (WAL) Principle

Oracle follows the rule of **writing the required redo before writing the corresponding data block down to a datafile**. If DBWn writes a dirty block, Oracle must ensure the associated redo has already been durably written first. Thus, a datafile can contain blocks from an uncommitted transaction while the database still has everything required to identify and undo invalid state after a crash.

WAL explains why **datafile write order does not need to match commit order**, while recoverability remains guaranteed.

## 3. DBWn — Database Writer: Writing Dirty Buffers to Datafiles

### 3.1. Primary Job

**DBWn** writes modified blocks in the **Database Buffer Cache** down to **datafiles**. Once written successfully, eligible buffers can be treated as clean until modified again.

Conceptual data flow:

```text
Server process modifies block in buffer cache
               |
               v
          Dirty buffer
               |
         DBWn writes to disk
               |
               v
            Datafile
```

DBWn serves buffer cache management and checkpoint progress. For example, Oracle may trigger DBWn when:

- More reusable buffers are needed for blocks about to be read into the cache.
- The count of dirty buffers grows and some must be proactively written to datafiles.
- Writes are requested by checkpoints or administrative operations.
- The system needs to advance background writing to bound crash recovery work.

Trigger thresholds, batching strategies, and writer counts depend on version and configuration; **there is no rule that "every COMMIT makes DBWn run once"**.

### 3.2. What DBWn Does Not Do

DBWn is **not** the process that decides which transactions are committed, nor is it the process that writes online redo logs. DBWn can write data belonging to an uncommitted transaction: this is completely normal behavior in a transactional database with redo/undo.

Example:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Not yet COMMITted in this session.
```

While the session holds this uncommitted transaction open, the block may be written to a datafile by DBWn. Other users still do not see the change as committed data, and if the transaction rolls back, Oracle uses undo to handle it properly.

Point to remember: **a datafile containing a change does not mean that change was committed**.

### 3.3. Why Are There Multiple DBWn Processes?

On systems with heavy I/O load or suitable configuration, Oracle can use multiple database writers (e.g., `DBW0`, `DBW1`) to share the workload. How many writers exist depends on version, configuration, resources, and auto-tuning mechanisms. Do not infer performance purely from "more DBWn processes".

## 4. LGWR — Log Writer: Writing Redo and Securing Commit Durability

### 4.1. What Does LGWR Do?

**LGWR** transfers redo entries from the **Redo Log Buffer** in the SGA out to **online redo log files**.

```text
Transaction modifications
              |
              v
       Redo Log Buffer
              |
         LGWR writes
              |
              v
      Online redo log(s)
```

Online redo logs hold the change stream serving **instance recovery**; when the database runs in `ARCHIVELOG` mode, filled online redo logs are copied by the archiver into archived redo logs for broader recovery scenarios. Creating archives typically involves **ARCn**, not LGWR's primary responsibility.

LGWR typically writes redo when needed for commits, when the redo buffer meets write conditions, or via Oracle's background write cycle. Exact thresholds and write cadence are internal implementation details and can vary across versions.

### 4.2. How Does COMMIT Tie to LGWR?

Suppose a session executes:

```sql
INSERT INTO orders (order_id, amount)
VALUES (101, 250000);

COMMIT;
```

Conceptual sequence:

1. The server process modifies table/index/undo blocks in the cache and generates corresponding redo.
2. On `COMMIT`, Oracle records a **commit record** in the redo stream and requests that required redo be written to the online redo log.
3. Under standard synchronous commit mode, **LGWR durably writes the required redo**, and then the session receives commit confirmation.
4. DBWn **does not need** to immediately write the block containing order `101` down to a datafile before the `COMMIT` statement finishes.

Hence, the transaction remains durable after the user receives "Commit complete", even though datafiles do not yet contain every new block. If the instance crashes immediately afterward, Oracle uses redo to recover the committed changes.

> **Key distinction:** Standard commit durability relies on redo written by LGWR; datafile writing is DBWn's separate job. Oracle also supports commit options such as `WRITE NOWAIT`/`BATCH` that change whether the session waits for redo writes, so the description above reflects the **synchronous default**.

### 4.3. Group Commit

When multiple sessions commit close together, Oracle can batch redo from several transactions into a single LGWR write. **Group commit** reduces individual write operations while still preserving standard synchronous commit semantics for all commits.

This is why you should not picture "every `COMMIT` statement equals one isolated disk write for one user".

### 4.4. How Do Redo Log Switches Relate?

Online redo logs typically consist of **groups** used in rotation. When the current redo group needs to switch to another group, Oracle performs a **log switch**. Log switches tie into checkpoint progress and conditions allowing a redo group to be reused.

If the system writes dirty buffers too slowly, a **`checkpoint not complete`** warning can appear when a redo group cannot yet be safely reused. This demonstrates the operational relationship between DBWn, CKPT, and redo group reuse, even though each component performs a distinct task. In archiving mode, an unarchived group can also block reuse; distinguish the exact cause.

## 5. CKPT — Checkpoint Process: Coordinating Checkpoint Progress

### 5.1. What Problem Does a Checkpoint Solve?

As Oracle runs over time, many data blocks are modified without yet being completely flushed to datafiles. If the instance crashes, Oracle must process redo to bring the database to a consistent state. A **checkpoint** lets Oracle record a progress milestone and bound the amount of recovery work required.

**CKPT** coordinates checkpointing and records checkpoint information in the **control file** and **datafile headers**. Through internal mechanisms, CKPT signals DBWn about required write progress or drives checkpoint activity.

Two tasks must be kept distinct:

- **DBWn writes data blocks** down to datafiles.
- **CKPT does not directly write those data blocks.** It coordinates and updates checkpoint metadata.

Do not interpret "CKPT runs" as "CKPT copies all tables to disk".

### 5.2. SCN and Checkpoints

An **SCN (System Change Number)** is a logical sequence number Oracle uses to pinpoint and order change/state progression in the database. An SCN is not simply wall-clock time.

Checkpoint metadata and redo tell Oracle **where to begin recovery** and which data needs updating after a failure. As checkpoint progress advances, the span of redo needed for instance recovery generally shrinks; however, overall effectiveness still depends on write traffic and other I/O activity.

### 5.3. "Full" Checkpoints vs. Incremental Checkpoints

Checkpoints happen in several ways depending on the situation:

- **Event-driven checkpoints** such as administrative actions or log switches may ask DBWn to perform specific write work.
- **Incremental checkpoints** let Oracle continuously advance dirty-block write progress over time rather than dumping everything in one massive burst.

A running system can still hold unwritten dirty buffers even as checkpoint progress advances. Therefore, **not every checkpoint means the entire cache is clean** or that every transaction is immediately flushed to datafiles.

### 5.4. Relationship to Recovery Time

If too many dirty buffers accumulate, crash recovery may need to read and apply a larger volume of redo. If checkpoint progress is pushed too aggressively, background writes can create heavy I/O pressure.

Oracle provides mechanisms and parameters to balance **target instance recovery time** against **runtime write cost**, notably `FAST_START_MTTR_TARGET` in supported releases/editions. Administrators should review statistics and workload traits before changing settings.

**Do not tune checkpoint parameters merely because dirty buffers exist.** Having dirty buffers is normal; tuning must be based on real metrics.

## 6. SMON — System Monitor: Instance Recovery and System Maintenance

### 6.1. When Is Instance Recovery Needed?

An **instance failure** occurs when an instance cannot complete a normal database shutdown—for instance due to host power loss, failure of an essential process, or an abrupt OS crash.

After the failure, three states can coexist:

1. Transactions that **committed** with redo written, whose corresponding data blocks had **not yet** reached datafiles.
2. **Uncommitted** transactions; some of their blocks **may already** have been written by DBWn to datafiles.
3. Redo logs and datafiles reflect different physical points in time, so transactional consistency must be restored.

**SMON** plays a central role in organizing/coordinating **instance recovery** when the database is reopened after an instance failure. Oracle may also employ dedicated recovery processes depending on version and configuration.

### 6.2. Two Conceptual Phases of Instance Recovery

An intuitive way to describe instance recovery:

**Phase 1 — Roll forward (redo application):**

Oracle reads required redo and reapplies changes not yet fully reflected in datafiles. Replayed changes may belong to **both committed and uncommitted transactions** at the time of failure.

**Phase 2 — Transaction recovery (rollback):**

Oracle uses undo information to **roll back uncommitted transactions** according to transactional semantics. As a result, the database never treats uncommitted changes as valid data.

```text
Instance crashes unexpectedly
         |
         v
Oracle reads checkpoint/redo state
         |
         v
Roll forward: apply required redo
         |
         v
Undo/transaction recovery for
uncommitted transactions
         |
         v
Database returns to transactionally consistent state
```

In live systems, rollback phases and tasks may interleave or be parallelized; part of transaction recovery can continue after the database has opened for work. Do not take the diagram as a single rigid sequence that always blocks every connection until **all** cleanup completes.

**Important point:** Instance recovery uses redo/undo to recover the database after an instance failure. It differs from **media recovery**, where datafiles are lost or damaged and backups plus redo sources are required.

### 6.3. Beyond Instance Recovery

SMON also participates in system maintenance activities such as resource cleanup or background tasks in certain scenarios depending on version. Segment and space management in modern Oracle involves multiple specialized processes/features; do not mechanically memorize outdated descriptions claiming "SMON always coalesces all free space".

### 6.4. SMON Does Not Replace LGWR and DBWn

SMON performs recovery **using data maintained by the other components**:

- Because LGWR wrote redo, there is a source to replay changes under valid recovery conditions.
- Because DBWn wrote some blocks, recovery handles the remaining delta.
- Because CKPT updated progress info, Oracle knows where to scope recovery.

SMON cannot "guess" a transaction if the needed recovery data does not exist. Protecting online redo, datafiles, control files, backups, and archived logs is an essential operational responsibility.

## 7. PMON — Process Monitor: Handling User Process Failures

### 7.1. Difference Between Process Failure and Instance Failure

Not every connection failure brings down the **entire Oracle instance**.

- **Process failure:** a server/user process or session encounters an error or terminates abnormally while the instance keeps running.
- **Instance failure:** the entire instance stops functioning normally, usually requiring instance recovery upon restart.

**PMON** monitors processes and coordinates cleanup of resources tied to failed processes. In modern releases, some cleanup work is delegated to other processes such as **CLMN** and cleanup workers; hence think of **PMON as the monitoring/coordinating role**, not necessarily performing every tiny action itself.

### 7.2. Resources That Must Be Handled

If a server process dies abruptly while serving a session, Oracle must properly handle resources associated with it, such as:

- Reclaiming or releasing unused process/session resources.
- Handling incomplete transactions, including restoring data/locks to proper state via rollback/recovery mechanisms.
- Cleaning up internal structures and locks/resources attached to the failed process when cleanup permits.

**Do not equate "PMON cleans up resources" with "every transaction rolls back instantaneously".** With large transactions or complex connections, cleanup/rollback can proceed asynchronously and take time; certain resources are only released once required steps finish.

### 7.3. PMON and Listener Registration: Changes Across Versions

In older Oracle documentation, PMON was also described as the process **registering the instance/services with the listener**.

Starting with **Oracle Database 12c**, dynamic registration with the listener was largely assigned to **LREG (Listener Registration Process)**. When studying Oracle 19c, 21c, 23ai, or 26ai, do not attribute listener registration directly to PMON as a fixed rule.

This is one example showing how process names and background responsibility splits evolve across releases; always check the documentation for the exact version you are using.

## 8. Coordination Timeline: From DML to COMMIT

Consider a simulated banking transaction:

```sql
-- Connected in an application schema with an illustrative ACCOUNTS table.
UPDATE accounts
SET balance = balance - 500
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 500
WHERE account_id = 20;

COMMIT;
```

This is one transaction consisting of two updates and one commit. Architectural coordination flow:

```text
Step 1: Server process executes both UPDATEs
    |
    +--> Reads/modifies blocks in Database Buffer Cache
    |         -> corresponding buffers become dirty
    |
    +--> Generates undo for potential rollback/consistent read
    |
    +--> Generates redo entries in Redo Log Buffer

Step 2: COMMIT
    |
    +--> Creates commit record and requests required redo write
    |
    +--> LGWR durably writes redo to online redo logs
    |
    +--> Session receives COMMIT confirmation (standard synchronous mode)

Concurrently / not tied directly to COMMIT:
    |
    +--> DBWn may write dirty buffers to datafiles
    |
    +--> CKPT coordinates checkpoint progress
    |
    +--> SMON/PMON normally have no session failure to handle
```

### What If Datafiles Are Not Yet Written After Commit?

Suppose LGWR has written sufficient redo for the transfer transaction and the session received commit confirmation, while DBWn has not yet written the data blocks for both accounts. If the instance loses power right then:

1. Online redo logs hold the committed change information.
2. On restart, Oracle performs instance recovery involving SMON and recovery components.
3. Changes missing from datafiles are reconstructed from the required redo.
4. The committed transfer transaction can be preserved under the durability guarantees of the commit and storage configuration.

This is a practical manifestation of the **D in ACID (Durability)**.

### What If a Session Runs UPDATE and Disconnects Abruptly?

Suppose a client issues an `UPDATE` without `COMMIT`, and the server process dies while the instance remains running:

1. PMON / associated cleanup processes detect and coordinate handling the failed process/session.
2. The database restores the uncommitted transaction to a valid state via rollback/undo mechanisms.
3. Datafiles may already hold some dirty blocks from that transaction; that still does not make the transaction committed.
4. New sessions will never see uncommitted results of the failed transaction as completed changes.

Because the instance did not crash, this scenario differs from **SMON recovering the entire instance at startup**.

## 9. Coordination Timeline: Checkpoints and Power Loss

Another perspective focuses on **write timing**.

| Time | What Happened | Meaning |
|---|---|---|
| T1 | Application modifies block A, generating redo | A is dirty in cache; redo is being generated |
| T2 | Transaction modifying A commits; LGWR writes redo | Committed change has a recovery path without needing DBWn to write A yet |
| T3 | DBWn writes some dirty blocks, potentially including A | Datafiles move closer to the newer state |
| T4 | CKPT updates appropriate checkpoint progress | Helps locate/scope recovery in case of failure |
| T5 | Another transaction modifies block B without committing; DBWn may have written B per WAL | Datafiles can contain uncommitted data |
| T6 | Host loses power; instance stops uncleanly | Instance recovery required on restart |
| T7 | SMON/recovery workers replay required redo and undo uncommitted transactions | Preserves committed A; removes uncommitted effects of B |

This timeline only illustrates what can happen. In a real system, redo flushes, datafile writes, checkpoints, and transaction recovery can occur concurrently across many sessions and buffers.

### What Would Break Without Write-Ahead Logging?

Suppose DBWn could flush an uncommitted block to a datafile while its associated redo was lost. When a crash occurs, the database could lack the information needed to recover consistently. That is why Oracle coordinates **WAL, redo, undo, DBWn, and recovery** instead of simply forcing "write every block on commit".

## 10. Observing Processes and Live Metrics via SQL

This section uses **read-only status queries**. On Oracle, privileges to inspect dynamic performance views (such as `V$PROCESS`, `V$BGPROCESS`, `V$SYSSTAT`) are typically granted by a DBA; ordinary application accounts may encounter `ORA-00942` or corresponding privilege errors. You may use an authorized administrative account in a permitted practice environment to observe, but do not grant `DBA` broadly just to run examples.

### 10.1. Viewing Recognized Oracle Background Processes

```sql
SELECT name, description
FROM v$bgprocess
WHERE name IN ('LGWR', 'CKPT', 'SMON', 'PMON')
   OR name LIKE 'DBW%'
ORDER BY name;
```

Here:

- `LGWR`: Log Writer.
- `CKPT`: Checkpoint Process.
- `SMON`: System Monitor.
- `PMON`: Process Monitor.
- `DBW0`, `DBW1`, ...: Database Writers when the environment has multiple writers.

`V$BGPROCESS` may display metadata for background process types; seeing a description row **does not by itself confirm every process is actively busy writing**. Auxiliary process names and view layouts can vary by version.

To view actual processes of the instance (when authorized):

```sql
SELECT pname, program
FROM v$process
WHERE pname IN ('LGWR', 'CKPT', 'SMON', 'PMON')
   OR pname LIKE 'DBW%'
ORDER BY pname;
```

The `PNAME` column and process info depend on version; in some environments you may need OS tools or cross-referencing appropriate views.

### 10.2. Viewing Instance/Database Status

```sql
SELECT instance_name, status, startup_time
FROM v$instance;

SELECT name, open_mode
FROM v$database;
```

With multitenant, inspect PDBs:

```sql
SELECT name, open_mode
FROM v$pdbs
ORDER BY name;
```

This helps distinguish "background processes are running" from "the user-facing PDB is open".

### 10.3. Viewing Write and Redo Statistics

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN ('redo size', 'redo writes', 'physical writes')
ORDER BY name;
```

Interpreting the output:

- `redo size`: total redo generated in Oracle's statistical units.
- `redo writes`: count of redo write operations.
- `physical writes`: instance-wide physical write I/O statistic.

Values are typically **cumulative** over instance uptime. A single snapshot is insufficient to derive rates; to estimate rate, compare values at two timestamps on the same instance. Also, **physical writes are not exclusively performed by DBWn**; do not use that metric to infer exact DBWn write counts without additional context.

### 10.4. Viewing Online Redo Log Group Status

```sql
SELECT group#, sequence#, status
FROM v$log
ORDER BY group#;
```

Common statuses:

- `CURRENT`: redo log group currently being written to.
- `ACTIVE`: log group still needed for instance recovery; cannot yet be considered unneeded.
- `INACTIVE`: log group no longer needed for instance recovery; reuse may still require meeting archiving/configuration rules.

This output helps connect log switches and checkpoints; it **does not** directly show which individual transactions committed.

### 10.5. Finding Checkpoint/Recovery Info

In releases where this view exists and you have privileges:

```sql
SELECT target_mttr, estimated_mttr
FROM v$instance_recovery;
```

- `TARGET_MTTR`: target instance recovery time per Oracle's calculation.
- `ESTIMATED_MTTR`: estimated instance recovery time at observation time.

These are **system estimates**, not a guarantee that the database will always reopen in the exact number of seconds displayed. Metrics can depend on settings and version.

> **Practice note:** Observation queries do not make DBWn "flush all dirty blocks immediately", do not force LGWR to write outside normal rules, and do not replace checking the alert log during real incidents.

## 11. Distinguishing Roles in Commonly Confused Scenarios

| Scenario | Primary Process Role | Why? |
|---|---|---|
| Buffer cache holds many dirty blocks; Oracle needs free buffers | **DBWn** | Writes dirty blocks from cache out to datafiles |
| User issues `COMMIT`, requiring durable transaction confirmation | **LGWR** | Writes redo including commit info to online redo logs |
| Oracle records a checkpoint milestone and updates metadata | **CKPT** (coordinating with **DBWn**) | CKPT coordinates checkpoints; DBWn writes data blocks |
| Instance crashes and restarts, needing redo replay and rollback of uncommitted transactions | **SMON** plus recovery workers | Performs/coordinates instance recovery |
| One session's server process dies while the instance stays up | **PMON** plus cleanup workers | Monitors and cleans up failed processes/sessions |
| Listener does not see a service because the instance hasn't registered it | **LREG** on Oracle 12c+ | Dynamically registers services with the listener, separate from redo/checkpoint |
| Online redo log group fills up and must switch to the next group | **LGWR** and log switch/checkpoint mechanisms | Log groups rotate; reuse eligibility depends on checkpoint/archiving |
| Application runs an ordinary `SELECT` | Primarily **server process** and read/cache mechanisms | The five background processes do not replace server processes executing SQL |

### Wrong Claims to Eliminate

**"Once COMMIT finishes, the datafile must already be written."** Incorrect. Under standard synchronous commit, LGWR ensures required redo is durably written, while DBWn writes dirty buffers on its own schedule.

**"DBWn only writes committed blocks."** Incorrect. DBWn can write blocks from uncommitted transactions; undo/redo keep the database consistent.

**"LGWR writes table data directly into datafiles."** Incorrect. LGWR writes redo into online redo logs.

**"CKPT is the process that writes all dirty buffers."** Incorrect. CKPT coordinates checkpoints and updates metadata; DBWn writes data blocks. Incremental checkpoints also do not mean every block in the database is instantly clean.

**"SMON and PMON do the same job."** Incorrect. SMON stands out in **instance recovery**; PMON stands out in **handling process failures while the instance remains running**.

**"PMON always registers services with the listener."** No longer true as a general statement in modern Oracle; from 12c onward, dynamic registration belongs primarily to LREG.

**"Redo and undo are two names for the same log."** Incorrect. Redo replays changes during recovery; undo enables rollback and read consistency.

## 12. Diagnosing Related Performance Symptoms and Incidents

In operations, these processes typically appear indirectly via statistics, wait events, or alert log messages.

### 12.1. Many Sessions Waiting Long on Commit

If an application reports slow `COMMIT` operations, one investigation path is redo write latency. Wait events such as **`log file sync`** typically reflect foreground time waiting for commit completion; **`log file parallel write`** relates to LGWR's redo write activity.

Verification direction: inspect wait times, write speed/latency of storage holding online redo logs, system load, and commit cadence. A single wait event alone is not enough to conclude hardware failure or blindly raise parameters.

### 12.2. Buffer Cache Running Short of Reusable Buffers

If sessions wait for buffers to be freed and the workload generates many dirty buffers, check DBWn write speed, datafile I/O performance, and memory configuration. Wait events such as **`free buffer waits`** may point to clean buffer availability issues. Do not assume simply raising DBWn count solves it.

### 12.3. Alert Log Shows "checkpoint not complete"

This message suggests checkpoint progress may not yet allow reusing a redo log group. Check the size and number of redo groups, log switch frequency, DBWn/CKPT write progress, and causes of slow storage. On systems with ARCHIVELOG enabled, also inspect archiving/archive storage status when relevant.

### 12.4. Slow Startup After Power Loss

If an instance stops abruptly, startup may require time for instance recovery. Redo volume to apply, checkpoint state, I/O speed, and transaction recovery can all affect completion time. Check the alert log and recovery info before intervening.

### 12.5. One Session Disappears While the Database Keeps Running

If an application/server process fails, Oracle may need to clean up and roll back incomplete transactions. This involves PMON/cleanup workers, not necessarily instance recovery. A large transaction not yet finished rolling back can delay releasing locks/resources immediately.

> In production environments, never deliberately kill background processes like LGWR, DBWn, CKPT, SMON, or PMON to "test recovery". Failing essential processes can bring down the instance. Recovery practice must use an isolated environment and prepared administrative procedures.

## 13. Practice Exercises: Reading Diagrams and Identifying the Right Process

### Exercise 1 — Assigning Duties

For each description below, identify the appropriate process:

1. Dirty buffers in the buffer cache are written down to datafiles.
2. Redo in the SGA is written to online redo logs.
3. Checkpoint metadata is updated in the control file and datafile headers.
4. The instance loses power; at startup, redo must be applied and uncommitted transactions resolved.
5. One server process dies unexpectedly while the entire instance keeps running.

**Answer:** (1) DBWn; (2) LGWR; (3) CKPT (coordinating with DBWn); (4) SMON and recovery mechanisms; (5) PMON and related cleanup processes.

### Exercise 2 — Analyzing an Uncommitted Transaction

A session runs:

```sql
UPDATE products
SET price = price + 1000
WHERE product_id = 42;

-- No COMMIT; the session stays open.
```

Suppose DBWn may already have written the block affected by this change. Questions:

- Has that data become **committed**?
- Why, after session rollback or instance recovery, can Oracle still restore a consistent state?
- Which process is responsible for writing redo while the transaction executes?

**Hint:** Not committed; undo/redo and the WAL rule protect transaction semantics; LGWR is the process writing redo from the log buffer to online redo logs.

### Exercise 3 — Explaining Commit Success Before Datafiles Are Updated

An application calls `COMMIT` and receives success. Then the instance crashes before DBWn writes all modified blocks. Describe:

1. What did LGWR write for a standard synchronous commit to be confirmed?
2. What is SMON's role upon restart?
3. Why does DBWn not need to write all data blocks immediately at `COMMIT`?

**Hint:** LGWR ensures required redo, including the commit record, is durably saved; instance recovery applies redo to restore committed changes; redo writing and datafile writing are decoupled to preserve both performance and durability.

### Exercise 4 — Observing a Live Instance

In a lab environment with read privileges on dynamic performance views:

```sql
SELECT name, description
FROM v$bgprocess
WHERE name IN ('LGWR', 'CKPT', 'SMON', 'PMON')
   OR name LIKE 'DBW%';

SELECT name, value
FROM v$sysstat
WHERE name IN ('redo size', 'redo writes', 'physical writes');

SELECT group#, sequence#, status
FROM v$log
ORDER BY group#;
```

Short report requirements:

- What DBWn names does the instance list?
- Which metrics relate to redo? Which metric relates to physical writes?
- Why are these statistics insufficient to tell whether one specific transaction committed?
- If you see a `CURRENT` log group, what does that say about LGWR; if a group is `ACTIVE`, what does it imply for instance recovery?

**Note:** This is an observation exercise; there is no need to force checkpoints, log switches, or induce database errors.

## 14. Connection to ACID and Oracle Reliability

The five processes covered in this lesson help explain key properties of a relational database management system:

- **Atomicity:** a transaction is treated as a single logical unit; if uncommitted and rolled back, Oracle uses undo/recovery to undo it cleanly.
- **Consistency:** the database maintains valid constraints and state via transaction mechanisms and SQL enforcement.
- **Isolation:** sessions do not see each other's uncommitted changes by default; Oracle uses undo-based read consistency and concurrency control.
- **Durability:** for standard synchronous commits, redo durably written by LGWR enables recovering committed transactions even when datafiles have not yet caught up.

These properties result from **multiple cooperating mechanisms**, not one single process "guaranteeing everything".

When asked **"Why does COMMIT succeed even though DBWn has not written the datafile?"**, remember **LGWR + redo + recovery**. When asked **"Why does the database remain consistent if a datafile already holds an uncommitted block?"**, remember **undo + redo + WAL + transaction recovery**. When asked **"Who coordinates checkpoints, who recovers the instance, and who cleans up failed sessions?"**, think respectively of **CKPT, SMON, and PMON** within their roles and modern Oracle's supporting processes.

---

### Core Glossary

| Term | Meaning |
|---|---|
| **SGA** | Shared memory of the Oracle instance |
| **Database Buffer Cache** | Area caching accessed data blocks in memory |
| **Dirty buffer** | A buffer modified in memory whose modified version has not yet been written to the corresponding datafile |
| **Redo Log Buffer** | Redo buffer inside the SGA |
| **Online redo log** | Redo file written by LGWR to support recovery |
| **Undo** | Information supporting rollback and consistent reads |
| **Checkpoint** | Mechanism tracking/coordinating write progress and recovery milestones |
| **SCN** | System Change Number, logical sequence ordering changes/states |
| **Instance recovery** | Restoring a valid state after instance failure using redo and undo |
| **Process cleanup** | Reclaiming resources associated with failed processes/sessions |

**Version-specific references:** *Oracle Database Concepts* (instance architecture, background processes, redo, undo, checkpoints) and *Oracle Database Administrator's Guide* (instance startup/recovery, redo log management) on [Oracle Database Documentation](https://docs.oracle.com/en/database/). When inspecting a specific release such as 19c, 21c, or Oracle AI Database 26ai, cross-check auxiliary process names and views against the exact documentation for that release.

