# Identifying the Timestamp, Position, or GTID Before an Erroneous Operation

When an accidental delete, bad update, or destructive migration corrupts data, the binary log helps pinpoint the exact transaction that caused the incident. To recover to the state immediately before that transaction, operators must find three related pieces of information: **time of occurrence**, **file/position boundaries**, and, if the server has GTID enabled, the **transaction's GTID**.

These three pieces of information serve distinct roles. Time narrows down the area to investigate. GTID identifies a transaction across replication history. File/position tells `mysqlbinlog` where to start or stop reading. An approximate timestamp or a GTID spotted in a log is not yet enough to stop recovery safely; you must determine the starting boundary of the entire erroneous transaction and validate it on a test restore.

## 1. Understanding Transaction Boundaries in the Binary Log

The binary log stores events sequentially. For an InnoDB transaction with GTID and row-based logging, an event group typically has the general form:

```text
# at 1200
# ... GTID ...
SET @@SESSION.GTID_NEXT='3e11fa47-71ca-11e1-9e33-c80aa9429562:501'/*!*/;

# at 1265
START TRANSACTION

# at 1330
# ... Table_map: `appdb`.`orders` ...

# at 1400
# ... Update_rows ...
### UPDATE `appdb`.`orders`
### WHERE
###   @1=9001
### SET
###   @3='CANCELLED'

# at 1550
# ... Xid = ...
COMMIT/*!*/;
```

This is a structural illustration, not fixed output across every version or `binlog_format`. Key landmarks when reading `mysqlbinlog` output are:

- `# at N`: starting offset of the event in the binary log file.
- `end_log_pos M`: offset immediately following that event, usually the starting offset of the next event.
- `GTID` and `SET @@SESSION.GTID_NEXT`: identifies the transaction when GTID is enabled.
- `BEGIN`/`START TRANSACTION` and `Xid`/`COMMIT`: define the transaction's scope.
- `Table_map`, `Write_rows`, `Update_rows`, `Delete_rows`: indicate the table and change type when using row-based logging.

To recover to before a transaction, you must stop at the starting position of the event opening that transaction, typically the GTID event in GTID mode. Never use `end_log_pos` of the transaction's final event as the stop point before the transaction: that is the position after the event, meaning the transaction has already been read through. On servers not using GTID, locate the event opening the transaction group or the event containing the erroneous statement if it is an autocommit statement.

A transaction can span multiple row events and completes only at `Xid`/`COMMIT`. Never stop between events of the same transaction. Stopping mid-transaction can leave partial transaction output that does not represent a valid data state we want to restore.

## 2. Preserving Logs and Narrowing the Incident Timeframe

As soon as an error is detected, preserve the relevant binary logs and prevent retention policies from deleting them before copying them to a safe place. Gather timestamps from application logs, audit logs, deployment schedules, error alerts, and operators. Normalize timestamps to UTC while recording the time zones of the application, MySQL, and the host running log inspection tools.

On MySQL 8.4, inspect binary log status using:

```sql
SHOW BINARY LOG STATUS;
SHOW BINARY LOGS;

SELECT
    @@GLOBAL.server_uuid AS server_uuid,
    @@GLOBAL.gtid_mode AS gtid_mode,
    @@GLOBAL.gtid_executed AS gtid_executed,
    @@GLOBAL.gtid_purged AS gtid_purged;

SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
```

On older versions, `SHOW MASTER STATUS` is the command commonly used to inspect current binary log status. `SHOW BINARY LOG STATUS` or `SHOW MASTER STATUS` only reports the current coordinates at command execution time; they cannot look backward to find the position of a past incident. `SHOW BINARY LOGS` helps see which files remain on the server, though you must also check external log archives if older logs were purged.

Copy the relevant log files together with checksums, preserve file ordering, and record source, collection time, and file sizes. Do not run `PURGE BINARY LOGS` during investigation. If logs must be shipped off the source, use controlled archive procedures and verify copy readability before altering retention.

Details worth recording in the incident report:

| Detail | Example | Purpose |
|---|---|---|
| Source | `server_uuid`, hostname, MySQL version | Avoid reading logs from the wrong host or a replica with a different history. |
| Time window | From 10:20 to 10:35 UTC | Narrow down files and event regions to analyze. |
| Data scope | `appdb.orders`, affected order keys | Match row events with data and application logs. |
| Actor | DB account, service, migration/job | Locate the originating statement or transaction. |
| Log state | File list, checksums, current GTID set | Confirm investigative logs remain complete. |

## 3. Using Time to Narrow the Event Region

Once an approximate timeframe is known, use `mysqlbinlog` to inspect a small slice rather than opening the entire history. Example against archived log files on an investigation host:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 10:20:00" \
  --stop-datetime="2026-11-19 10:35:00" \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000120 > incident-window.txt
```

`--start-datetime` and `--stop-datetime` narrow the event range by timestamp. Verify the time zone used to interpret timestamps and reconcile against application clocks. Time typically has one-second resolution, so multiple transactions can share the same timestamp or sit closely together. Event timestamps also do not replace business commit times logged by applications.

For incidents spanning multiple files, read consecutive files across that timeframe:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 10:20:00" \
  --stop-datetime="2026-11-19 10:35:00" \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000120 mysql-bin.000121 mysql-bin.000122 \
  > incident-window.txt
```

This is a search step, not a recovery command. Output may contain many valid transactions in the same timeframe; never select a stop point based merely on the first matching timestamp line.

If affected table names or record keys are known, match them against events in the window. With row-based logging, `mysqlbinlog --verbose --base64-output=DECODE-ROWS` decodes row events into `###` descriptions for human reading. These lines are analytical comments, not directly executable SQL statements. When replaying logs, run `mysqlbinlog` in default output mode, not the decoded comment output.

## 4. Confirming the Exact Erroneous Transaction

Never conclude a transaction is the root cause merely because it appeared near the time the application reported errors. Confirm at least the following points:

1. Correct source server and binary log file.
2. Timestamp falls within the incident window after time zone conversion.
3. Schema, table, operation, and record keys match the affected scope.
4. Before/after image contents or SQL text show the exact erroneous change.
5. Transaction boundaries are traced from the opening event to the commit event.

For example, with row-based logging, an update may appear as follows:

```text
### UPDATE `appdb`.`orders`
### WHERE
###   @1=9001
###   @2='ORD-9001'
###   @3='PAID'
### SET
###   @1=9001
###   @2='ORD-9001'
###   @3='CANCELLED'
```

Numbers `@1`, `@2`, `@3` represent column ordinals in the table; consult `Table_map` and the corresponding schema to understand column names, types, and meaning. `binlog_row_image=FULL` records fuller row images. With `MINIMAL`, before/after images may contain only columns needed to identify the row and changed columns; never assume omitted columns are empty.

If the binary log uses statement-based logging, events may contain the original SQL text. With mixed format, some operations are logged as statements and others as row events. Read the actual event type rather than assuming every log contains readable SQL.

You can use `SHOW BINLOG EVENTS` to inspect a basic event list and positions:

```sql
SHOW BINLOG EVENTS
IN 'mysql-bin.000120'
FROM 1200
LIMIT 50;
```

This command is useful for checking event order and positions. For row events, inspecting data contents generally requires `mysqlbinlog` for decoding and analysis.

## 5. Finding the GTID of the Erroneous Transaction

If `gtid_mode` is enabled, every transaction written to the binary log carries a GTID. In `mysqlbinlog` output, find the `SET @@SESSION.GTID_NEXT` line near the event group containing the erroneous change. Example:

```text
# at 184320
# ... GTID ...
SET @@SESSION.GTID_NEXT='3e11fa47-71ca-11e1-9e33-c80aa9429562:501'/*!*/;
```

In this example, the transaction's GTID is:

```text
3e11fa47-71ca-11e1-9e33-c80aa9429562:501
```

You can filter specifically by GTID to read its contents:

```bash
mysqlbinlog \
  --include-gtids='3e11fa47-71ca-11e1-9e33-c80aa9429562:501' \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000120
```

`--include-gtids` is handy for inspecting an already-identified transaction. If the GTID is unknown, first inspect by timeframe and affected table/keys, then extract the GTID from the event. A GTID set such as `@@GLOBAL.gtid_executed` only shows which transactions have executed; the set itself does not contain a direct mapping from a GTID to a file/position. To find a GTID's position, you must read the binary log containing that transaction.

If the server does not use GTID, transactions can still be identified via file/position and event boundaries. In that case, there is no GTID to filter or compare; keep the file/position pair alongside source metadata accurately.

## 6. Finding the File/Position to Stop Before the Erroneous Transaction

Once the erroneous transaction is confirmed, inspect the start of that event group in `mysqlbinlog` output. Suppose the output looks like:

```text
# at 184320
# ... GTID ...
SET @@SESSION.GTID_NEXT='3e11fa47-71ca-11e1-9e33-c80aa9429562:501'/*!*/;

# at 184385
START TRANSACTION
```

Position `184320` is the start of the GTID event in this example. To recover to the state immediately before transaction `...:501`, set the stop point at `184320`, i.e., before the event opening the transaction. The `end_log_pos` of the preceding event usually equals this position, but inspect and verify `# at` on the opening event to avoid confusing it with the end of another event.

For transactions without GTID, locate the `BEGIN`/`START TRANSACTION` event opening the group or the first event of the transaction in the file. For autocommit statements such as certain DDL, the event containing the statement itself is the boundary to stop before. DDL operations trigger implicit commits; do not apply transaction rollback assumptions as with InnoDB DML.

If the transaction resides in `mysql-bin.000122` with start position `184320`, you can use:

```bash
mysqlbinlog \
  --stop-position=184320 \
  mysql-bin.000122 > before-bad-transaction.sql
```

`--stop-position` stops before the first event whose position is greater than or equal to the specified offset. Position is an offset within the specified file, not a global offset across all binary log files. Always record the filename together with the position; recording `184320` without the filename cannot identify the anchor.

When starting from an older backup and replaying across multiple files, `--start-position` applies to the first file in the list and `--stop-position` applies to the last file. For instance, if the backup ended at position `45600` in the first file and the erroneous transaction starts at position `184320` in the last file:

```bash
mysqlbinlog \
  --start-position=45600 \
  --stop-position=184320 \
  mysql-bin.000120 mysql-bin.000121 mysql-bin.000122 \
  > replay-before-incident.sql
```

The file list must be continuous and in sequence; no intermediate file may be missing. Inspect the generated SQL output to ensure it begins after the backup anchor and ends before the erroneous transaction's GTID event. Before using in earnest, test-run on an isolated recovery server.

## 7. Using Time, Position, and GTID for the Right Purpose

| Anchor | What it is used for | Caveats to remember |
|---|---|---|
| Time (`--start-datetime`, `--stop-datetime`) | Narrowing events by incident window. | Multiple transactions can share the same second; time zones and timestamps must be verified. |
| File/position (`--start-position`, `--stop-position`) | Specifying exact read boundaries in the binary log. | Positions only have meaning within one specific file; must choose valid transaction boundaries. |
| GTID (`--include-gtids`, `--exclude-gtids`) | Identifying or filtering transactions in a GTID topology. | GTIDs hold no data and do not reveal file/position without reading logs. |

When the goal is stopping recovery before an erroneous transaction, file/position at the start of the transaction is usually the most direct anchor. GTID is strong identifying evidence confirming you picked the right transaction and reconciling with replicas. Time is a search clue, not the sole basis for exact recovery boundaries.

`--exclude-gtids` can skip a specific GTID in the output stream while continuing with subsequent transactions:

```bash
mysqlbinlog \
  --exclude-gtids='3e11fa47-71ca-11e1-9e33-c80aa9429562:501' \
  mysql-bin.000120 mysql-bin.000121 \
  > replay-without-one-transaction.sql
```

This filters out one transaction; it is not the same as recovering to before that transaction. Subsequent transactions may still be replayed and could depend on data created or altered by the skipped transaction. Use this only after analyzing dependencies and confirming subsequent transactions remain valid. If you need a consistent pre-incident state, stop at the beginning of the erroneous transaction, inspect, and then decide whether to selectively replay valid transactions.

## 8. Replaying up to Before the Erroneous Operation on a Recovery Host

A safe workflow starts from a consistent backup restored onto an isolated server. Never test replay commands directly on a live production server holding corrupted data. Before running, verify:

- Backup and metadata belong to the right `server_uuid`/source.
- Replay start file/position matches the snapshot.
- All binary logs from the backup anchor through the file containing the erroneous transaction are complete and continuous.
- GTID state on the target server matches the backup; if a dump set `GTID_PURGED`, do not re-mark or replay GTIDs already included in the snapshot.
- The target is isolated from application writes throughout recovery.

Example replaying from backup coordinates up to before the erroneous transaction across three files:

```bash
mysqlbinlog \
  --start-position=45600 \
  --stop-position=184320 \
  mysql-bin.000120 mysql-bin.000121 mysql-bin.000122 \
  | mysql --host=restore-db.internal --user=recovery
```

This command assumes `mysql-bin.000122:184320` is the start of the erroneous transaction, and `mysql-bin.000120:45600` is the continuation point right after the snapshot. `mysql` will prompt for a password if the account requires authentication; never embed real passwords on the command line or in shell history. Replace hostname, account, files, and positions with verified values from actual manifests and logs.

After replaying, check affected data, row counts, primary keys, constraints, related tables, and business state. Compare against pre-incident state if reference data exists. When valid transactions occurring after the erroneous operation must be preserved, plan selective extraction and application on the verified recovery copy; never blindly replay the rest of the log automatically.

## 9. Situations Prone to Selecting the Wrong Anchor

| Situation | Risk | How to check |
|---|---|---|
| Clock skew between application and MySQL | Choosing the wrong time window. | Check NTP, time zones, application logs, and event timestamps; normalize to UTC. |
| Multiple transactions within the same second | Stopping after the bad transaction or too early before valid transactions. | Use event contents, GTIDs, and file/position to distinguish. |
| Stopping at `end_log_pos` of the transaction's last event | The erroneous transaction is included in the replay stream. | Find `# at` of the transaction's opening event and stop at that position. |
| Stopping mid-row-event or before `Xid` | Replays a partial transaction, producing an incomplete stream. | Inspect the full event group from start to commit; choose a pre-transaction anchor. |
| Erroneous transaction near log rotation | Missing a file or misreading positions. | Inspect the last event of the prior file and first event of the next file; preserve file sequence. |
| Binary log already purged from source | Unable to find or replay transactions from source. | Locate archive copies; verify checksums and missing file ranges. |
| Row image in `MINIMAL` mode | Not all row columns appear. | Cross-check schema, identifying keys, and columns recorded in before/after images. |
| Single application transaction invoking multiple SQL statements | Seeing one event and missing the rest of the transaction. | Follow GTID/BEGIN through Xid or COMMIT; never split a transaction by individual row events. |
| DDL or autocommitting statements | Transaction rollback assumptions no longer hold. | Identify implicit commits and recover from a copy prior to the DDL. |
| Skipping a GTID while replaying later transactions | Subsequent transactions may depend on skipped data. | Analyze business dependencies and reconcile data before selective replay. |

## 10. Checklist Before Confirming a PITR Anchor

- [ ] Identified the exact source server and preserved copies of relevant binary logs.
- [ ] Recorded incident time window, time zone, and evidence sources.
- [ ] Confirmed affected schema, table, operation type, and records.
- [ ] Read the complete transaction from its opening event to commit or autocommit event.
- [ ] Recorded GTID if present, along with filename and starting position of the opening event.
- [ ] Chose `--stop-position` before the erroneous transaction, not `end_log_pos` of the last event.
- [ ] Verified all consecutive files from backup coordinates through the stop anchor.
- [ ] Restored and test-replayed on an isolated server.
- [ ] Verified data before deciding to bring the recovered system into service.

A reliable PITR anchor must explicitly specify **file + position**, accurately capture **transaction boundaries**, and be cross-checked with **GTID** if present. Time locates the log region to inspect; row/statement event contents confirm the erroneous operation; the position at the start of the transaction lets you stop replay before that change is applied. Archive all of this evidence alongside the recovery report so future reviews can audit and reproduce the decision.
