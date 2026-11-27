# Transactions, Locking, and Consistency When Updating LOBs

LOB (Large Object) is an Oracle data type used to store large content such as long text, large JSON/XML, images, audio, video, documents, or binary data. The main LOB types are CLOB, NCLOB, BLOB, and BFILE. Because LOBs can be very large and are often stored outside ordinary row data, reading and writing LOBs have distinct characteristics regarding locators, transactions, locking, consistent reads, and data versioning.

When updating a LOB, two layers of state must be understood: the table row holding the LOB locator and the LOB content managed by Oracle. For persistent LOBs, write operations still belong to the session's transaction; the row lock is usually the key concurrency boundary. If multiple applications edit the same document concurrently, merely writing in chunks is not enough to prevent overwriting older edits. You must choose a pessimistic locking or optimistic version-control strategy, define commit boundaries, and decide how to handle partial uploads.

After this lesson, you will be able to:

- Distinguish CLOB, NCLOB, BLOB, BFILE, and persistent/temporary LOBs.
- Understand how a LOB locator references LOB content.
- Explain transactions, COMMIT, ROLLBACK, and read consistency when updating LOBs.
- Lock the row containing a LOB with SELECT ... FOR UPDATE before using DBMS_LOB to modify a persistent LOB.
- Understand row-level locking, lock duration, and contention across multiple sessions.
- Prevent lost updates when two users edit the same document concurrently.
- Use a version column to implement optimistic locking.
- Write LOBs piecewise with DBMS_LOB.WRITE, WRITEAPPEND, APPEND, and TRIM.
- Distinguish LOB chunk size from locking units or transaction units.
- Understand consistent reads, LOB retention, and snapshot too old errors.
- Design large uploads using staging, temporary LOBs, and short transactions.
- Diagnose errors such as ORA-22920, ORA-22924, ORA-22275, ORA-00054, and ORA-00060.

> This lesson focuses on LOBs stored inside Oracle Database. BFILE is a reference to a file outside the database and has different semantics. Storage syntax, SecureFiles/BasicFiles, and some features may depend on the Oracle version; verify against the release in use.

## 1. LOB Types and How Oracle Manages Them

### 1.1. CLOB

CLOB (Character Large Object) stores character data in the database character set. Commonly used for large text, HTML, XML, textual JSON, logs, or long documents.

Example:

```sql
CREATE TABLE lab_documents (
    document_id NUMBER PRIMARY KEY,
    document_name VARCHAR2(200),
    document_body CLOB,
    updated_at TIMESTAMP
);
```

### 1.2. NCLOB

NCLOB stores character data in the database's national character set. Use it when the application requires national character set semantics. Both CLOB and NCLOB are character LOBs; when using DBMS_LOB, offset/amount have character semantics for CLOB/NCLOB.

### 1.3. BLOB

BLOB (Binary Large Object) stores binary data such as images, PDFs, Office files, audio, or video.

Example:

```sql
CREATE TABLE lab_attachments (
    attachment_id NUMBER PRIMARY KEY,
    file_name VARCHAR2(255),
    mime_type VARCHAR2(100),
    file_content BLOB,
    created_at TIMESTAMP
);
```

For BLOB, offset and amount in DBMS_LOB are measured in bytes.

### 1.4. BFILE

BFILE is a locator referencing a binary file on a filesystem that Oracle accesses through a DIRECTORY object. The file content is not stored in a table's LOB segment, and the database does not manage file content transactionally like BLOB/CLOB.

Characteristics:

- BFILE is read-only through Oracle's LOB interface.
- Content resides outside the database.
- Modifying or deleting the file is managed by the OS/external processes.
- COMMIT/ROLLBACK in Oracle does not undo modifications to the external file.
- The file must be accessed via a DIRECTORY object and appropriate privileges.

If content must be protected by database transactions and backup/recovery, consider storing it in a BLOB rather than only referencing a BFILE.

### 1.5. Persistent LOBs and Temporary LOBs

| Type | Where Managed | Lifecycle |
| --- | --- | --- |
| Persistent LOB | LOB column of a table row | Persists with table data and transactions |
| Temporary LOB | Temporary LOB storage managed by Oracle | CALL or SESSION duration, depending on creation |
| BFILE | File outside the database; locator stored in row | External file lifecycle; file content is outside transactions |

Persistent LOBs store long-lived application data. Temporary LOBs are commonly used for string concatenation, intermediate processing, or assembling payloads before writing to a LOB column.

## 2. LOB Locators and LOB Content

### 2.1. What Is a Locator?

When selecting a LOB column into a PL/SQL variable, the variable typically holds a LOB locator. A locator is a reference to access LOB content; it should not be thought of as the entire large content immediately copied into the variable.

Example:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_body)
    );
END;
/
```

The variable l_body holds a locator to the corresponding LOB. DBMS_LOB operations can use the locator to read or modify content subject to privileges and locking.

### 2.2. A Locator Is Not an Independent Copy

A persistent locator is bound to the row's LOB in the database. If the row or LOB is modified or deleted, an old locator may no longer be valid in the usage context. Do not cache a locator in application memory assuming it remains valid indefinitely after commit, session termination, or data modification.

For client applications, drivers usually provide a LOB locator/streaming handle whose lifecycle is tied to the connection and result set. Read/write via driver APIs and close resources properly.

### 2.3. Empty LOBs and NULL

A LOB column can be NULL or contain an empty locator. Oracle provides EMPTY_CLOB() and EMPTY_BLOB() to initialize a non-NULL empty LOB:

```sql
INSERT INTO lab_documents (
    document_id,
    document_name,
    document_body,
    updated_at
)
VALUES (
    10,
    'Draft',
    EMPTY_CLOB(),
    SYSTIMESTAMP
);
```

NULL means no LOB value; EMPTY_CLOB() represents an empty LOB. Several DBMS_LOB operations require a valid locator, so distinguish the two cases.

### 2.4. LOB Length and Offset

DBMS_LOB.GETLENGTH returns the LOB length:

```sql
SELECT
    document_id,
    DBMS_LOB.GETLENGTH(document_body) AS body_length
FROM lab_documents;
```

For CLOB/NCLOB, length and offset use character units per LOB semantics. For BLOB, length and offset use bytes. Do not arbitrarily use LENGTHB or byte offsets for CLOBs; align units with the API being called.

## 3. Transactions When Updating Persistent LOBs

### 3.1. Persistent LOBs Belong to Transactions

When using SQL UPDATE or DBMS_LOB to modify a persistent LOB, changes are governed by the current transaction. COMMIT persists the changes; ROLLBACK undoes uncommitted changes per the transaction.

Example:

```sql
UPDATE lab_documents
SET document_body = TO_CLOB('New document text'),
    updated_at = SYSTIMESTAMP
WHERE document_id = 10;

-- Check within the same transaction.
SELECT DBMS_LOB.GETLENGTH(document_body)
FROM lab_documents
WHERE document_id = 10;

-- Caller decides:
COMMIT;
-- Or ROLLBACK;
```

There is no implicit commit merely because a LOB is large or because DBMS_LOB.WRITE is called. Persistent LOBs still follow database transactions.

### 3.2. Atomicity of a Single DML Statement

An UPDATE assigning a LOB is a single DML statement:

```sql
UPDATE lab_documents
SET document_body = :new_document_body
WHERE document_id = :document_id;
```

If the statement fails, Oracle rolls back the effects of that statement. Earlier successful DML statements in the same transaction remain pending until the caller commits or rolls back the entire transaction.

### 3.3. Multiple DBMS_LOB Writes in One Transaction

If one transaction calls DBMS_LOB.WRITE multiple times on the same LOB, those writes belong to the current transaction. You can commit after all chunks complete so the document is published only in a complete state.

If you commit after every chunk, the application exposes partially committed states. In that case, you must design checkpoints, upload status, checksums, and resume logic; otherwise readers may observe incomplete documents.

### 3.4. Long Transactions and Large LOBs

Keeping a transaction open for the entire duration of uploading a very large file can:

- Hold row locks for a long time.
- Force other sessions updating the same row to wait.
- Require holding undo/old versions longer.
- Increase contention risk and make rollback expensive.
- Prolong recovery if the client disconnects.

If an upload takes several minutes, consider writing into staging or a temporary LOB first, validating content, and then using a short transaction to swap the locator or copy data to the main row.

## 4. Locking the Row Containing a LOB

### 4.1. Why Is SELECT FOR UPDATE Needed?

When using DBMS_LOB to modify a persistent LOB, you must lock the row containing the LOB with SELECT ... FOR UPDATE before writing. This ensures the session owns permission to modify the row's LOB and prevents other sessions from concurrently modifying the same row while the transaction holds the lock.

Example:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(' - revised'),
        ' - revised'
    );

    COMMIT;
END;
/
```

For CLOB, amount is character count. For BLOB, amount is byte count.

If you do not lock the row before modifying a persistent LOB via DBMS_LOB, you can encounter:

```text
ORA-22920: row containing the LOB value is not locked
```

### 4.2. SQL UPDATE Acquires the Row Lock Automatically

If you update a LOB using a SQL UPDATE statement, Oracle automatically acquires the necessary DML lock on the row:

```sql
UPDATE lab_documents
SET document_body = :new_body,
    updated_at = SYSTIMESTAMP
WHERE document_id = :document_id;
```

You do not need a separate SELECT FOR UPDATE before a normal UPDATE just for Oracle to lock the row; the UPDATE statement does that itself. SELECT FOR UPDATE is required when the application fetches a locator and calls DBMS_LOB to modify it piecewise.

### 4.3. Locking Is by Row, Not by Chunk

Do not treat LOB CHUNK size as a locking unit. For persistent LOBs, the row lock on the row containing the LOB is the primary concurrency boundary. Two sessions modifying two different LOB columns on the same row will still contend on that row lock.

Conversely, two sessions modifying LOBs on different rows can generally proceed independently at the row-lock level, though they may still experience contention on shared resources such as I/O, buffers, LOB segments, or indexes.

### 4.4. Locks Are Held Until Transaction End

After SELECT FOR UPDATE or UPDATE, the row lock is held until COMMIT or ROLLBACK. Closing a cursor or exiting a PL/SQL block does not release the row lock.

Therefore:

- Do not hold a transaction open while a user reads or edits content in a UI.
- Do not wait on a slow client upload after locking the main row.
- Do not call external services while holding a row lock.
- Commit or roll back at well-defined business boundaries.

## 5. SELECT FOR UPDATE: WAIT, NOWAIT, and SKIP LOCKED

### 5.1. Default WAIT

If a session tries to lock a row currently locked by another session, default SELECT FOR UPDATE waits until the lock is released:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = 10
FOR UPDATE;
```

The second session waits until the first session runs COMMIT or ROLLBACK. Oracle then re-evaluates and locks the row per SELECT semantics.

### 5.2. NOWAIT

NOWAIT returns an error immediately if the lock cannot be acquired:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = 10
FOR UPDATE NOWAIT;
```

If the row is locked, it typically raises ORA-00054. The application can report that the document is being edited or prompt the user to retry.

### 5.3. WAIT n

WAIT n waits up to the specified number of seconds:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = 10
FOR UPDATE WAIT 5;
```

If the lock is not acquired within the wait window, Oracle raises the corresponding timeout error, typically ORA-30006. Choose timeout values based on SLAs and user experience.

### 5.4. SKIP LOCKED

SKIP LOCKED skips locked rows and is useful for queue workers processing many independent rows:

```sql
SELECT document_id
FROM lab_document_jobs
WHERE job_status = 'READY'
FOR UPDATE SKIP LOCKED;
```

In practice, it is often combined with a cursor/ROWNUM or FETCH FIRST to claim a batch. SKIP LOCKED is unsuitable when a user requests a specific document ID and needs to know whether it is being edited; skipping the row could be misinterpreted as the row not existing.

### 5.5. OF Column

In multi-table join queries, FOR UPDATE OF can specify which table's column indicates the table to lock:

```sql
SELECT d.document_id, d.document_body
FROM lab_documents d
JOIN lab_document_types t
  ON t.type_id = d.type_id
WHERE d.document_id = 10
FOR UPDATE OF d.document_body;
```

OF identifies the table/row to lock via the named column; it does not turn the LOB into a chunk-level lock. FOR UPDATE syntax has restrictions with DISTINCT, GROUP BY, set operators, and complex views; keep locking queries simple and test on your release.

## 6. Lost Updates When Multiple Users Edit the Same LOB

### 6.1. Scenario

Two users open the same document at version 7:

1. Session A reads version 7 content.
2. Session B also reads version 7 content.
3. A edits the beginning and saves a new version.
4. B edits the end based on the stale copy and writes the entire content back to the row.

If B does not check the current version, the content A just saved can be overwritten. This is a lost update.

```text
Time            Session A                    Session B
---------       ---------                    ---------
T1              Read document version 7      Read document version 7
T2              Edit content A               Edit content B
T3              Write full content A
T4                                           Write full content B
T5              Commit                       Commit

Final result: content B may overwrite A's changes.
```

Row locks only serialize concurrent writes during the transactions holding the lock. They do not automatically detect that B is submitting an outdated copy read earlier.

### 6.2. Pessimistic Locking

Pessimistic locking acquires a row lock before reading/writing so other sessions wait or fail:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = :document_id
FOR UPDATE;
```

The application acquires the lock before making changes and holds it until COMMIT/ROLLBACK. This works when:

- Documents must be edited serially.
- Edit duration is short so transactions remain brief.
- Conflicts are frequent and repeated retries should be avoided.
- The application controls sessions and transactions.

Do not lock a row while a user keeps a form open or edits offline. Users may take minutes; long row locks block other sessions and keep transactions open too long.

### 6.3. Optimistic Locking with a Version Column

A common approach is adding VERSION_NO:

```sql
ALTER TABLE lab_documents
ADD version_no NUMBER DEFAULT 1 NOT NULL;
```

When reading the document, the application retrieves both content and version:

```sql
SELECT document_body, version_no
FROM lab_documents
WHERE document_id = :document_id;
```

When saving, update only if the version still matches what was read:

```sql
UPDATE lab_documents
SET document_body = :new_body,
    version_no = version_no + 1,
    updated_at = SYSTIMESTAMP
WHERE document_id = :document_id
  AND version_no = :expected_version;
```

In PL/SQL:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_documents
    SET document_body = :new_body,
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = :document_id
      AND version_no = :expected_version;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20031,
            'Document changed since it was read. Reload before saving.'
        );
    END IF;
END;
/
```

If row count is 1, the update won and the version incremented. If 0, either the document does not exist or the version changed; the application must reload and resolve the conflict. The VERSION_NO predicate in the WHERE clause is what detects lost updates; checking SQL%ROWCOUNT after an UPDATE without that predicate does not provide concurrency control.

### 6.4. Comparing Pessimistic and Optimistic

| Criterion | Pessimistic Lock | Optimistic Version |
| --- | --- | --- |
| When conflict is detected | Before or while waiting for lock | At write time via version check |
| Locking during user edit | Should not be held across long user interactions | No row lock held during offline edits |
| Under high contention | Sessions wait on each other | Some saves fail and must retry/merge |
| Best suited for | Short edits needing serialization | Read-heavy, write-light, long edit durations |
| Mechanism | SELECT FOR UPDATE | UPDATE ... WHERE version_no = expected |

You can combine both: check version to detect stale reads, then acquire a row lock in a short transaction during the write.

### 6.5. Why Not Rely Solely on ORA_ROWSCN?

ORA_ROWSCN can help observe SCNs associated with row changes, but its granularity depends on ROWDEPENDENCIES and storage characteristics; it is not a straightforward business version token for all applications. An application-managed VERSION_NO column incremented in the same UPDATE is clearer and easier to control.

## 7. Writing LOBs Piecewise with DBMS_LOB

### 7.1. DBMS_LOB.WRITE

WRITE writes data into a LOB at a specified offset:

```sql
DBMS_LOB.WRITE(
    lob_loc => l_body,
    amount  => 6,
    offset  => 1,
    buffer  => 'Oracle'
);
```

For CLOB, amount and offset have character semantics; for BLOB, byte semantics. WRITE overwrites at the specified position and may not replace the rest of the LOB. If replacing the entire content, use SQL UPDATE to assign a new LOB, or TRIM/WRITE in an explicit sequence.

### 7.2. DBMS_LOB.WRITEAPPEND

WRITEAPPEND appends data to the end of a LOB:

```sql
DBMS_LOB.WRITEAPPEND(
    lob_loc => l_body,
    amount  => LENGTH(l_piece),
    buffer  => l_piece
);
```

Full example for CLOB:

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(1000) := 'More content';
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_piece),
        l_piece
    );

    COMMIT;
END;
/
```

If document_body is NULL, initialize a valid LOB before writing—for example, UPDATE the column to EMPTY_CLOB() RETURNING the locator INTO a variable in the same transaction, or use a case-appropriate statement.

### 7.3. DBMS_LOB.APPEND

APPEND appends the entire content from a source LOB to a destination LOB:

```sql
DBMS_LOB.APPEND(
    dest_lob => l_destination,
    src_lob  => l_source
);
```

Source and destination must be valid locators of compatible LOB types. For a persistent destination, lock the destination row before modifying.

### 7.4. DBMS_LOB.TRIM

TRIM truncates a LOB to the specified length:

```sql
DBMS_LOB.TRIM(
    lob_loc => l_body,
    newlen  => 100
);
```

TRIM removes content from the new length onward. It is a persistent data change belonging to the transaction; lock the row before calling on a persistent LOB.

### 7.5. DBMS_LOB.ERASE

ERASE clears a range of content by offset/amount without necessarily shortening the LOB. For BLOBs, the erased region is replaced with zero bytes; for CLOB/NCLOB, with spaces per LOB semantics. If the goal is removing the tail, TRIM is usually more appropriate.

### 7.6. DBMS_LOB.COPY

COPY copies a slice or the entirety of a source LOB to a destination LOB:

```sql
DBMS_LOB.COPY(
    dest_lob    => l_destination,
    src_lob     => l_source,
    amount      => DBMS_LOB.GETLENGTH(l_source),
    dest_offset => 1,
    src_offset  => 1
);
```

Amount/offset units match the LOB type. A persistent destination requires a row lock. For very large LOBs, consider memory, redo/undo, lock hold time, and staging-based copying.

### 7.7. Writing Multiple Chunks

Example writing a CLOB in pieces within one transaction:

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(4000);
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    l_piece := 'Part one. ';
    DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_piece), l_piece);

    l_piece := 'Part two. ';
    DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_piece), l_piece);

    l_piece := 'Part three.';
    DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_piece), l_piece);

    COMMIT;
END;
/
```

All chunks commit together at the end of the transaction. If an error occurs before COMMIT and the exception handler rolls back the transaction, uncommitted persistent LOB changes are undone with the transaction.

## 8. CHUNK Size and Performance

### 8.1. What Is CHUNK?

LOB CHUNK is the internal allocation/read/write unit of LOB storage. You can query chunk size with:

```sql
SELECT DBMS_LOB.GETCHUNKSIZE(document_body)
FROM lab_documents
WHERE document_id = 10;
```

Chunk size can affect performance during piecewise reads/writes and how Oracle manages the LOB segment.

### 8.2. CHUNK Is Not a Locking Unit

Do not assume that two sessions writing two different chunks of the same persistent LOB will not block each other. The row lock on the row holding the LOB is the critical concurrency boundary. CHUNK describes storage/I/O organization, not a mechanism for independent per-range write locks.

### 8.3. Choosing Buffer Size

When streaming from an application:

- Use a reasonably sized buffer to avoid loading entire large files into RAM.
- For BLOBs, measure amount in bytes.
- For CLOB/NCLOBs, measure amount in characters and account for multibyte character sets.
- Do not split a character string mid-character by bytes when APIs expect characters.
- Benchmark performance with realistic chunk sizes.

No single buffer size is optimal for every LOB. It depends on file size, network, driver, storage, memory, and latency.

### 8.4. CACHE, NOCACHE, and LOGGING

LOB storage has attributes such as CACHE/NOCACHE/CACHE READS and LOGGING/NOLOGGING depending on LOB type and version. They affect buffer cache usage and redo/recovery characteristics; they do not replace row locks or transaction isolation.

- CACHE can help when LOBs are read frequently.
- NOCACHE can suit large, rarely re-read LOBs.
- CACHE READS can suit read-heavy, write-light workloads.
- NOLOGGING can impact media recovery/standby depending on operation and configuration.

Never pick NOLOGGING just for speed while ignoring backups, Data Guard, and recoverability. Storage attributes should be chosen based on workload and DBA policy.

## 9. Read Consistency When Reading LOBs

### 9.1. Oracle MVCC

Oracle uses multi-version concurrency control (MVCC) to provide read consistency. A SELECT reads data as of a consistent SCN; if another session is modifying a row without committing, ordinary readers can still read the previously committed version instead of waiting on the writer.

For persistent LOBs, LOB content must also be read as of the statement's consistent version. Oracle manages needed versions through undo/LOB versioning mechanisms and LOB version retention settings.

### 9.2. Readers and Writers

In the common scenario:

- Session A updates a LOB and keeps the transaction uncommitted.
- Session B runs a regular SELECT.
- B reads the previously committed version and does not see A's uncommitted content.
- After A commits, a new SELECT by B can read the new version.
- If B uses SELECT FOR UPDATE, B must acquire the row lock and may wait on A.

This is the distinction between consistent reads and locking for modification.

### 9.3. One Statement Sees One Snapshot

If a query runs while another session updates a LOB, Oracle strives to return results consistent with the snapshot at statement start time. It does not arbitrarily mix part of old data and part of new data within the same logical read.

With SERIALIZABLE or READ ONLY transaction isolation, snapshot rules apply at the transaction scope per corresponding semantics; on update conflicts, Oracle may raise a serialization error rather than allowing overwrites.

### 9.4. Consistent Reads Do Not Retain Versions Forever

To construct consistent reads, Oracle must retain old version information long enough. For large LOBs, LOB version management has its own storage policies alongside normal undo. If a long-running read query needs a LOB version that has already been reclaimed, it can hit ORA-22924.

Do not assume that raising UNDO_RETENTION alone solves every snapshot-too-old error for LOBs. Check LOB retention/storage policies, long-running read workloads, and LOB update rates.

## 10. LOB Retention and Snapshot Too Old

### 10.1. Why Retain Old LOB Versions?

Suppose a query starts reading a very large document. While the query is running, another session updates the same LOB and commits a new version. For the first query to keep seeing snapshot-consistent data, Oracle may need the old LOB version for the duration of the read.

If the old version is not retained long enough, the query may fail rather than read an inconsistent mix of data.

### 10.2. BasicFiles and PCTVERSION

With BasicFiles LOBs, PCTVERSION controls the percentage of LOB segment space reserved for old versions in the versioning mechanism. Setting it too low relative to update/long-read workloads can cause needed consistent-read versions to be missing.

PCTVERSION is not the percentage of LOB space reserved for new application data; it pertains to space retaining old versions under BasicFiles mechanics.

### 10.3. SecureFiles and RETENTION

SecureFiles uses the RETENTION attribute to manage old LOB versions according to release-supported policies, such as AUTO or other retention modes. Specific behavior depends on version, tablespace configuration, and workload.

Do not copy a PCTVERSION value verbatim to SecureFiles. Review DDL storage clauses and Oracle documentation for the exact LOB type.

### 10.4. ORA-22924

ORA-22924 typically indicates snapshot too old when Oracle no longer has the LOB version needed for a consistent read. When encountering this error:

1. Determine how long the LOB-reading query/session runs.
2. Identify which LOB and table/partition are involved.
3. Check the LOB update rate during that window.
4. Check BasicFiles PCTVERSION or SecureFiles RETENTION.
5. Evaluate LOB segment size, tablespace space, and old-version retention overhead.
6. Shorten read duration or structure streaming appropriately.

Do not work around this by disabling read consistency. Consistency is a database requirement; provision adequate resources/version retention or adjust the workload.

### 10.5. LOB Retention Is Not Backup Retention

Retaining old versions for consistent reads is not a backup or archive retention policy. PCTVERSION/RETENTION does not replace RMAN backups, flashback, auditing, or business retention.

## 11. Temporary LOBs and Lifecycle

### 11.1. When to Use Temporary LOBs?

Temporary LOBs fit when:

- Concatenating multiple CLOB segments before saving.
- Creating intermediate content during data transformations.
- Receiving large data from APIs/drivers before updating the main table.
- Building previews or temporary computed results.

Temporary LOBs are not persistent table rows and are not shared like regular LOB columns.

### 11.2. Creating a Temporary CLOB

```sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp_clob,
        LENGTH('Temporary text'),
        'Temporary text'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_temp_clob)
    );

    DBMS_LOB.FREETEMPORARY(l_temp_clob);
END;
/
```

CREATETEMPORARY creates a temporary LOB; duration can be CALL or SESSION. CALL ties lifetime to the current call; SESSION keeps it in the session until freed or the session ends.

### 11.3. Temporary LOBs Do Not Share Persistent LOB Transaction Semantics

Changes to a temporary LOB are not transactional DML on a table row. Do not rely on ROLLBACK to revert temporary LOB contents like persistent LOBs. Temporary LOBs belong to the session/call and must be freed properly.

To persist content long-term, write the temporary LOB into a persistent LOB column via an appropriate INSERT/UPDATE. Writing to the persistent column is what participates in database transactions.

### 11.4. Freeing Temporary LOBs

Call FREETEMPORARY when the locator is no longer needed:

```sql
DBMS_LOB.FREETEMPORARY(l_temp_clob);
```

Do not free a locator and continue using it. When exceptions occur, have an exception handler free any created temporary LOBs before re-raising the error.

### 11.5. Temporary LOBs and TEMP Space

Temporary LOBs can consume temporary tablespace and PGA/memory depending on size, configuration, and processing. Applications creating many temporary LOBs or keeping SESSION duration without freeing can inflate temporary resource usage. Monitor sessions and free promptly.

## 12. BFILE and Transaction Boundaries

### 12.1. BFILE Is Only a Reference

A BFILE locator stores a reference to a file outside the database. Example creating a DIRECTORY:

```sql
CREATE OR REPLACE DIRECTORY LAB_FILE_DIR AS '/u01/app/files';
GRANT READ ON DIRECTORY LAB_FILE_DIR TO app_user;
```

Then you can store a BFILE locator:

```sql
CREATE TABLE lab_external_files (
    file_id NUMBER PRIMARY KEY,
    file_name VARCHAR2(255),
    external_content BFILE
);

INSERT INTO lab_external_files
VALUES (
    1,
    'manual.pdf',
    BFILENAME('LAB_FILE_DIR', 'manual.pdf')
);
COMMIT;
```

The filesystem path in the example depends on the database server; DIRECTORY is not a local path on a client machine.

### 12.2. BFILE Is Read-Only

You can open and read a BFILE using DBMS_LOB.FILEOPEN, DBMS_LOB.READ, and FILECLOSE. You cannot use DBMS_LOB.WRITE to modify BFILE contents. To update content inside the database, read the file and write it to a BLOB or use an appropriate import workflow.

### 12.3. COMMIT Does Not Protect External Files

Oracle does not control OS file transactions. If an external process modifies a file while a session is reading the BFILE, the database cannot roll the file back to an earlier version or guarantee a transactionally immutable file snapshot.

If strong consistency is required:

- Manage files with immutable names/versions.
- Record checksums, sizes, and metadata.
- Copy the file into a BLOB on import so the database owns the content.
- Publish the locator only after the file is verified.

### 12.4. BFILE Privileges and Errors

Users need READ privilege on the DIRECTORY object and appropriate filesystem permissions on the database server. Errors can come from missing files, wrong directory/filenames, OS permissions, or invalid locators. Do not confuse these errors with persistent LOB row locks.

## 13. BasicFiles and SecureFiles

### 13.1. BasicFiles

BasicFiles is the traditional LOB storage mechanism. It still appears in older databases or unmigrated systems. BasicFiles has management attributes such as CHUNK, PCTVERSION, CACHE/NOCACHE, and LOGGING.

### 13.2. SecureFiles

SecureFiles is Oracle's modern LOB storage mechanism, designed to improve LOB performance and manageability. Depending on version and licensing/configuration, SecureFiles supports features such as compression, deduplication, encryption, retention, and storage optimizations.

Example declaration:

```sql
CREATE TABLE lab_secure_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
    CACHE
    LOGGING
);
```

SecureFiles availability depends on tablespace and database configuration; not every environment can use every feature.

### 13.3. Storage Type Does Not Change Row-Locking Rules

Moving from BasicFiles to SecureFiles does not allow applications to skip SELECT FOR UPDATE before DBMS_LOB writes on persistent LOBs. Row locking, transaction boundaries, and concurrency control must still be designed properly.

### 13.4. Compression and Deduplication

Compression can reduce storage space at the cost of CPU on reads/writes. Deduplication can reduce storage when many LOBs have identical content. Both must be benchmarked with realistic data patterns and checked against licensing/version requirements.

Never treat deduplication as a guard against concurrent overwrites. It is a storage optimization, not a business lock.

## 14. OPEN/CLOSE LOB and Index Maintenance

### 14.1. DBMS_LOB.OPEN

DBMS_LOB.OPEN can be used to open a LOB before performing multiple read/write operations:

```sql
DBMS_LOB.OPEN(
    lob_loc => l_body,
    open_mode => DBMS_LOB.LOB_READWRITE
);
```

For persistent LOBs being modified, you still must lock the row containing the LOB before writing. OPEN does not replace SELECT FOR UPDATE.

### 14.2. DBMS_LOB.CLOSE

After completing operations, close the LOB:

```sql
DBMS_LOB.CLOSE(l_body);
```

If explicitly opened, CLOSE on both success and exception paths. You can use a flag variable to track whether the LOB is open to avoid calling CLOSE on an unopened locator.

### 14.3. Why Can OPEN/CLOSE Be Useful?

When a LOB is explicitly opened, Oracle can defer certain maintenance on LOB-related functional/domain indexes until CLOSE instead of repeating it after every write operation. This can help when writing many pieces. However, not every index type or workload benefits; check documentation and benchmark.

### 14.4. OPEN/CLOSE Is Not COMMIT

CLOSE ends the open state of the locator; it does not replace COMMIT. The transaction remains pending until the caller commits or rolls back.

### 14.5. Exception-Safe Pattern

Skeleton example:

```sql
DECLARE
    l_body CLOB;
    l_is_open BOOLEAN := FALSE;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    DBMS_LOB.OPEN(l_body, DBMS_LOB.LOB_READWRITE);
    l_is_open := TRUE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(' appended'),
        ' appended'
    );

    DBMS_LOB.CLOSE(l_body);
    l_is_open := FALSE;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF l_is_open THEN
            DBMS_LOB.CLOSE(l_body);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
```

This is an illustrative skeleton. In production code, exceptions raised by CLOSE must also be handled so the original error is not masked; transaction ownership must be clearly defined if the procedure is called from a larger transaction.

## 15. Designing Large LOB Uploads with Staging

### 15.1. Why Not Lock the Main Row During the Entire Upload?

A file of several hundred MB can take considerable time to upload over the network. If the application locks the main document row before receiving the first byte, the row lock is held throughout the entire data transfer. Readers can still read the committed version, but other writers trying to modify the same row must wait.

A better design usually receives data into a staging/temporary area, validates completeness, and then publishes in a short transaction.

### 15.2. Staging Table

Example staging table:

```sql
CREATE TABLE lab_document_uploads (
    upload_id NUMBER PRIMARY KEY,
    document_id NUMBER NOT NULL,
    upload_status VARCHAR2(20) NOT NULL,
    payload BLOB,
    expected_size NUMBER,
    actual_size NUMBER,
    checksum_value VARCHAR2(128),
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

States may include RECEIVING, VALIDATING, READY, PUBLISHED, FAILED, or EXPIRED. A clear state machine helps handle client disconnects and retries.

### 15.3. Upload Workflow

1. Create an upload_id and staging row in RECEIVING state.
2. Stream chunks into the staging payload.
3. Update actual_size and checksum progressively.
4. When upload finishes, validate size, checksum, MIME/type, and content.
5. Mark as READY.
6. Open a short transaction to lock the main document or use a version predicate.
7. Assign/copy the staging LOB to the main document.
8. Increment version, update metadata, and mark PUBLISHED in the same transaction.
9. Commit.
10. Clean up staging rows per retention policy.

### 15.4. Publishing with a Single UPDATE

Once the application has the complete BLOB payload in staging, it can update the main row with DML:

```sql
UPDATE lab_attachments a
SET a.file_content = (
        SELECT u.payload
        FROM lab_document_uploads u
        WHERE u.upload_id = :upload_id
          AND u.upload_status = 'READY'
    ),
    a.updated_at = SYSTIMESTAMP
WHERE a.attachment_id = :attachment_id
  AND a.version_no = :expected_version;
```

This is a conceptual example; a real schema needs version_no and must ensure the subquery returns exactly one row. Check SQL%ROWCOUNT to see whether publishing updated the document. If 0, either the version changed or the document does not exist.

### 15.5. Resume and Idempotency

If an upload is interrupted:

- Keep upload_id stable so the client can resume.
- Record received chunk sequences/offsets.
- Check for duplicate chunks before appending.
- Compute the final checksum before publishing.
- Never mark an incomplete file as READY.
- Run a cleanup job for expired staging records.

Never re-append an already received chunk without an offset/idempotency check, as retries could duplicate content.

## 16. Transaction Granularity and Chunk Commits

### 16.1. One Transaction for the Entire LOB

If readers must see only the old document or the complete new document, write the entire content into staging/temporary LOB first and publish in a short transaction. Alternatively, when writing directly to a persistent LOB, keep all chunks inside one transaction and commit only once finished.

Pros: other readers do not see uncommitted pieces; rollback undoes uncommitted persistent changes.

Cons: long transactions, long row locks, undo/version retention pressure, and complex retries.

### 16.2. Committing After Each Chunk

Committing per chunk shortens each transaction but exposes partial state. In that case you need:

- An UPLOADING/INCOMPLETE status so readers do not treat content as complete.
- Committed offset/checkpoint tracking.
- Per-chunk or full-file checksums.
- Idempotent resume logic without duplicate writes.
- An atomic publish step once all chunks are present.

If readers query only document_status = 'PUBLISHED', you can avoid exposing incomplete payloads.

### 16.3. Do Not Share Locators Across Sessions

A locator is a handle tied to an Oracle session/connection context. Do not pass a PL/SQL locator from one session to another as a durable token. To hand off work, pass document_id/upload_id and offset/checksum; the new session fetches a valid locator from the database.

### 16.4. Do Not Hold Row Locks While Waiting on Clients

Clients can be slow, drop connectivity, or close browsers. Never hold SELECT FOR UPDATE while waiting for a client to send the next chunk. Use staging and a short publish transaction to bound lock duration.

## 17. Common Errors When Operating on LOBs

| Error/Symptom | Possible Cause | Check / Resolution |
| --- | --- | --- |
| ORA-22920 | Row containing persistent LOB is not locked | SELECT ... FOR UPDATE before DBMS_LOB write |
| ORA-22275 | Invalid or uninitialized locator | Check NULL/EMPTY locator, locator lifetime, and LOB type |
| ORA-22924 | LOB version needed for consistent read no longer exists | Check PCTVERSION/RETENTION and long-running queries |
| ORA-00054 | NOWAIT failed to acquire row lock | Report busy, retry with backoff, or use WAIT |
| ORA-30006 | WAIT timed out waiting for lock | Tune timeout or reduce lock hold time |
| ORA-00060 | Deadlock between transactions | Check multi-row locking order and transaction graph |
| ORA-01555 | Snapshot too old involving undo/read consistency | Check query duration, undo, and update workload |
| LOB overwritten with stale content | Lost update due to client saving outdated copy | Use version column and optimistic locking |
| LOB has duplicated chunks | Non-idempotent append retry | Track offset/chunk ID, checksum, and upload state |
| Reader sees incomplete file | Per-chunk commit without publish state | Use staging and PUBLISHED status |
| Temporary LOB consumes excessive TEMP | Not freed or held with long SESSION duration | Call FREETEMPORARY and monitor sessions |
| BFILE fails to open | DIRECTORY grant, file path, or OS permissions | Check DIRECTORY, READ grant, and server permissions |
| BFILE data changes outside transaction | File modified by external process | Use immutable names/versions or import into BLOB |

## 18. Diagnosing Locks and Waiting Sessions

### 18.1. Checking Waiting Sessions

A DBA can inspect V$SESSION for wait events, blocking_session, and wait time:

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    event,
    wait_class,
    seconds_in_wait,
    blocking_session,
    sql_id
FROM v$session
WHERE blocking_session IS NOT NULL;
```

Privilege to query V$SESSION typically must be granted by a DBA. Do not request broad DBA privileges just to run an application; ask a DBA to extract relevant details during investigations.

### 18.2. Viewing Locked Objects and Row Waits

V$LOCKED_OBJECT helps identify objects locked by transactions at the object metadata level:

```sql
SELECT
    lo.session_id,
    lo.object_id,
    o.owner,
    o.object_name,
    o.object_type,
    lo.locked_mode
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id;
```

This view is not the sole tool for seeing exactly which row/LOB chunk is waited on. Combine V$SESSION, V$LOCK, SQL_ID, and ASH/AWR where privileges and licensing permit.

### 18.3. ORA-00060 and Lock Ordering

If transaction A locks document 10 then document 20, while B locks document 20 then document 10, the two transactions can deadlock. Reduce risk by locking multiple rows in a consistent order, such as ascending DOCUMENT_ID.

Never catch ORA-00060 and continue as if the statement succeeded. Oracle rolls back the statement causing the deadlock; the application should handle full-transaction retry per policy.

### 18.4. Retry with Backoff

For transient lock errors, retries should include:

- A bounded number of attempts.
- Increasing delay (backoff) and jitter when multiple clients contend.
- Distinguishing transient errors from data/constraint errors.
- Idempotency so retries do not duplicate chunks or side effects.
- Logging document_id, upload_id, version, and error codes.

Never retry indefinitely, as that increases load and prolongs contention.

## 19. Practice Lab: Creating a LOB Table and Writing Content

Run the labs below in a dedicated schema. Do not use production tables or document IDs holding real data.

### 19.1. Create the Table

```sql
CREATE TABLE lab_lob_documents (
    document_id NUMBER
        CONSTRAINT pk_lab_lob_documents PRIMARY KEY,
    document_name VARCHAR2(200) NOT NULL,
    document_body CLOB,
    version_no NUMBER DEFAULT 1 NOT NULL,
    document_status VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
    updated_at TIMESTAMP
);

INSERT INTO lab_lob_documents (
    document_id,
    document_name,
    document_body,
    version_no,
    document_status,
    updated_at
)
VALUES (
    1,
    'Concurrency lab',
    EMPTY_CLOB(),
    1,
    'DRAFT',
    SYSTIMESTAMP
);

COMMIT;
```

### 19.2. Write a CLOB with SQL UPDATE

```sql
UPDATE lab_lob_documents
SET document_body = TO_CLOB('First version of the document.'),
    updated_at = SYSTIMESTAMP
WHERE document_id = 1;

SELECT
    document_id,
    DBMS_LOB.GETLENGTH(document_body) AS body_length
FROM lab_lob_documents
WHERE document_id = 1;

COMMIT;
```

### 19.3. Append to a CLOB with DBMS_LOB

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(1000) := ' Added through DBMS_LOB.';
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_lob_documents
    WHERE document_id = 1
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_piece),
        l_piece
    );

    DBMS_OUTPUT.PUT_LINE(
        'New length = ' || DBMS_LOB.GETLENGTH(l_body)
    );

    COMMIT;
END;
/
```

Read back content:

```sql
SELECT DBMS_LOB.SUBSTR(document_body, 4000, 1)
FROM lab_lob_documents
WHERE document_id = 1;
```

DBMS_LOB.SUBSTR returns a portion of the content. For very large LOBs, read across multiple offsets/buffers rather than trying to fit everything into VARCHAR2.

### 19.4. Replace Entire Content Using RETURNING Locator

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(1000) := 'Replacement content.';
BEGIN
    UPDATE lab_lob_documents
    SET document_body = EMPTY_CLOB(),
        updated_at = SYSTIMESTAMP
    WHERE document_id = 1
    RETURNING document_body INTO l_body;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_piece),
        l_piece
    );

    COMMIT;
END;
/
```

UPDATE acquires the row lock; the returned locator references the newly initialized empty LOB. Write chunks and commit in the same transaction.

### 19.5. Check Version and Length

```sql
SELECT
    document_id,
    version_no,
    document_status,
    DBMS_LOB.GETLENGTH(document_body) AS body_length,
    updated_at
FROM lab_lob_documents
WHERE document_id = 1;
```

## 20. Practice Lab: Observing Row Locks with Two Sessions

Open two separate connections to the same lab schema.

### 20.1. Session A

Run the block without committing immediately:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_lob_documents
    WHERE document_id = 1
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(' Session A update.'),
        ' Session A update.'
    );

    DBMS_OUTPUT.PUT_LINE('A has updated the LOB; transaction is open.');
END;
/
```

The block finishes, but the transaction is uncommitted, so the row lock remains held.

### 20.2. Session B

Attempt to acquire the same row lock:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_lob_documents
    WHERE document_id = 1
    FOR UPDATE WAIT 5;

    DBMS_OUTPUT.PUT_LINE('B acquired the row lock.');
END;
/
```

Session B waits up to 5 seconds and then times out if A still holds the lock.

### 20.3. Back to Session A

```sql
COMMIT;
```

After A commits, re-run Session B's block. B can acquire the lock if no other session holds it.

### 20.4. Observing Read Consistency

While A holds the lock uncommitted, run a regular SELECT in B:

```sql
SELECT DBMS_LOB.SUBSTR(document_body, 4000, 1)
FROM lab_lob_documents
WHERE document_id = 1;
```

A regular reader reads the previously committed version, while SELECT FOR UPDATE must wait for the lock. Compare results before and after A's COMMIT.

## 21. Practice Lab: Optimistic Locking Against Lost Updates

### 21.1. Sessions A and B Both Read Version

In both sessions:

```sql
SELECT document_id, version_no
FROM lab_lob_documents
WHERE document_id = 1;
```

Assume both read VERSION_NO = 1.

### 21.2. Session A Updates First

```sql
UPDATE lab_lob_documents
SET document_body = TO_CLOB('Content saved by A'),
    version_no = version_no + 1,
    updated_at = SYSTIMESTAMP
WHERE document_id = 1
  AND version_no = 1;

SELECT SQL%ROWCOUNT FROM dual;
COMMIT;
```

Note: a standalone `SELECT SQL%ROWCOUNT` after UPDATE is not a valid SQL statement for reading UPDATE's row count. In real practice, use a PL/SQL block:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_lob_documents
    SET document_body = TO_CLOB('Content saved by A'),
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = 1
      AND version_no = 1;

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('A updated rows = ' || l_rows);
    COMMIT;
END;
/
```

### 21.3. Session B Saves Using Stale Version

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_lob_documents
    SET document_body = TO_CLOB('Content saved by B'),
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = 1
      AND version_no = 1;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        DBMS_OUTPUT.PUT_LINE(
            'Conflict: document was changed by another session.'
        );
    ELSE
        COMMIT;
    END IF;
END;
/
```

Because A already incremented version to 2, B's UPDATE does not match and row count is 0. B does not overwrite A's content.

### 21.4. Takeaway

Pessimistic locking coordinates sessions while a transaction is open. Optimistic locking detects stale copies at save time. For prolonged document editing, a version column is usually preferable to holding a row lock throughout user interaction.

## 22. Practice Lab: Staging Upload and Publish

### 22.1. Create Staging Table

```sql
CREATE TABLE lab_lob_upload_stage (
    upload_id NUMBER PRIMARY KEY,
    document_id NUMBER NOT NULL,
    upload_status VARCHAR2(20) NOT NULL,
    payload CLOB,
    expected_length NUMBER,
    actual_length NUMBER,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### 22.2. Load Data into Staging

```sql
INSERT INTO lab_lob_upload_stage (
    upload_id,
    document_id,
    upload_status,
    payload,
    expected_length,
    actual_length,
    created_at,
    completed_at
)
VALUES (
    1001,
    1,
    'READY',
    TO_CLOB('Complete staged document content.'),
    LENGTH('Complete staged document content.'),
    LENGTH('Complete staged document content.'),
    SYSTIMESTAMP,
    SYSTIMESTAMP
);

COMMIT;
```

### 22.3. Publish with Optimistic Version Check

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_lob_documents d
    SET document_body = (
            SELECT s.payload
            FROM lab_lob_upload_stage s
            WHERE s.upload_id = 1001
              AND s.upload_status = 'READY'
        ),
        version_no = version_no + 1,
        document_status = 'PUBLISHED',
        updated_at = SYSTIMESTAMP
    WHERE d.document_id = 1
      AND d.version_no = 2;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20032,
            'Publish conflict: document version has changed.'
        );
    END IF;

    UPDATE lab_lob_upload_stage
    SET upload_status = 'PUBLISHED',
        completed_at = SYSTIMESTAMP
    WHERE upload_id = 1001
      AND upload_status = 'READY';

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

In this example, updating the document and transitioning the staging status occur in the same transaction. If publishing fails, both changes roll back. In production data, verify the staging row exists uniquely and expected length/checksum match before publishing.

## 23. Design and Operational Principles

1. **Distinguish LOB types.** CLOB/NCLOB are characters; BLOB is bytes; BFILE is a file outside the database.
2. **Understand locators.** A locator is a reference with a lifecycle, not an independent durable copy.
3. **Lock the row before DBMS_LOB writes.** Use SELECT FOR UPDATE or UPDATE ... RETURNING locator.
4. **Do not treat CHUNK as a lock.** The row lock on the row containing the LOB is the key concurrency boundary.
5. **Keep transactions short.** Never lock the main row throughout a slow client upload.
6. **Choose pessimistic or optimistic locking by workload.** Long-edited documents typically fit a version column.
7. **Capture version on read and verify on write.** UPDATE ... WHERE version_no = expected detects lost updates.
8. **Define clear commit boundaries.** Use one transaction for the entire change when atomicity is needed; if committing per chunk, track upload state/checkpoints.
9. **Use staging for large files.** Validate payloads before publishing to the main row.
10. **Use offsets/chunk IDs and checksums.** Upload retries must be idempotent to prevent duplicated content.
11. **Distinguish persistent and temporary LOBs.** Temporary LOBs require lifetime management and FREETEMPORARY.
12. **Do not use BFILE if transactions on file content are required.** Import into BLOB when a durable snapshot is needed.
13. **Watch retention and consistent reads.** Long LOB reads during frequent updates may require longer old-version retention.
14. **Configure BasicFiles/SecureFiles appropriately for the type.** PCTVERSION and RETENTION are not a single shared attribute across all LOB types.
15. **Use OPEN/CLOSE intentionally.** CLOSE does not replace COMMIT; handle exceptions so open locators are never leaked.
16. **Monitor waits and errors.** Distinguish ORA-22920, ORA-22924, ORA-00054, ORA-30006, and ORA-00060.
17. **Do not retry infinitely.** Use backoff, retry limits, and idempotency.
18. **Test with multiple sessions.** Single-session success does not prove concurrency semantics are right.

## 24. Self-Check Questions

1. How do CLOB, NCLOB, BLOB, and BFILE differ?
2. How do persistent LOBs differ from temporary LOBs in lifecycle and transaction semantics?
3. What is a LOB locator? Why should a locator not be treated as a copy of content?
4. How does EMPTY_CLOB() differ from NULL?
5. Why is SELECT FOR UPDATE needed before DBMS_LOB.WRITE on a persistent LOB?
6. Does a direct SQL UPDATE on a LOB column require a separate SELECT FOR UPDATE beforehand?
7. How long is a row lock on a row containing a LOB held?
8. Why can two different LOB columns in the same row still contend?
9. Is CHUNK size a locking unit?
10. How do WAIT, NOWAIT, and SKIP LOCKED differ?
11. How do lost updates happen when two users save full content concurrently?
12. How does optimistic locking use VERSION_NO to prevent overwrites?
13. Why is ORA_ROWSCN not always a suitable business version token?
14. How does DBMS_LOB.WRITE differ from WRITEAPPEND and APPEND?
15. How do amount/offset units differ between CLOB and BLOB?
16. How does DBMS_LOB.TRIM differ from ERASE?
17. Why can committing after each chunk expose incomplete state to readers?
18. How do read consistency and row locks serve different roles?
19. How does ORA-22924 relate to retention/versioning?
20. What are BasicFiles PCTVERSION and SecureFiles RETENTION used for?
21. Why must temporary LOBs be freed?
22. Why can COMMIT not roll back changes to a BFILE on the filesystem?
23. How do staging uploads reduce row-lock hold time?
24. What information should be logged to support upload resume and retry?

## 25. Mental Model Summary

```text
PERSISTENT LOB
    |
    +-- LOB locator references content in table
    +-- DML/DBMS_LOB write belongs to transaction
    +-- SELECT FOR UPDATE before DBMS_LOB write
    +-- Row lock held until COMMIT/ROLLBACK
    |
    v
CONCURRENCY
    |
    +-- Pessimistic: lock row before editing
    +-- Optimistic: VERSION_NO in WHERE
    +-- SQL%ROWCOUNT = 0: conflict detected
    |
    v
CONSISTENCY
    |
    +-- MVCC for readers
    +-- LOB version retention for consistent reads
    +-- ORA-22924 when required version is missing
    |
    v
LARGE UPLOAD
    |
    +-- Staging / temporary LOB
    +-- Stream by chunk and checksum
    +-- Validate before publishing
    +-- Short transaction to swap main LOB
    |
    v
EXCEPTIONS
    |
    +-- BFILE is outside database transactions
    +-- Temporary LOBs require lifetime management
    +-- CHUNK is not a locking unit
```

**Key takeaway:** updating a persistent LOB is part of a database transaction. When modifying via DBMS_LOB, lock the row containing the LOB first; hold the lock until commit/rollback and never let transactions stretch to match slow client upload speeds. Use a version column to detect stale document edits, staging to prepare large files, and appropriate retention settings so readers can observe consistent versions.
