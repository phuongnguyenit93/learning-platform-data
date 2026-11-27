# Measuring Storage Size, Querying Metadata, and Handling Temporary LOB Leaks

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** LOBs and Large Data  
> **Objective:** Distinguish logical LOB size from allocated segment space; query LOB and segment metadata in the data dictionary; inspect BasicFiles, SecureFiles, IN ROW/OUT OF ROW storage, and partitioned LOBs; monitor temporary LOBs per session; manage lifecycles with DBMS_LOB.CREATETEMPORARY, ISTEMPORARY, and FREETEMPORARY; detect and resolve temporary LOB leaks in procedures, packages, and connection-pooled applications.

## 1. LOBs Have Several Distinct Size Concepts

LOB (Large Object) stores large content such as documents, images, audio, JSON, or long text. When investigating storage usage, three quantities must be distinguished:

1. **Logical length:** the content length seen by the application, measured by DBMS_LOB.GETLENGTH.
2. **Allocated segment space:** the number of extent bytes Oracle has allocated to the segment storing the LOB, viewed via USER_SEGMENTS/DBA_SEGMENTS.
3. **Temporary LOB usage:** temporary LOBs currently held by a session and the associated temporary tablespace usage.

These three numbers are not necessarily equal. A 1-million-character CLOB does not mean it occupies exactly 1 MB on disk. Character sets, IN ROW storage, LOB chunks, data versioning, SecureFiles compression/deduplication, free space within the segment, and extent allocation can all make physical storage differ from logical length.

In particular, a temporary LOB is not a persistent LOB stored in a table column. Temporary LOBs have lifecycles tied to a call or session and normally use the temporary tablespace. You cannot find them by querying USER_LOBS alone.

## 2. Distinguishing BLOB, CLOB, NCLOB, and BFILE

| Type | Content | Unit of DBMS_LOB.GETLENGTH |
|---|---|---|
| BLOB | Binary data | Bytes |
| CLOB | Text in database character set | Characters |
| NCLOB | Text in national character set | Characters |
| BFILE | Binary file outside the database | Bytes |

Example:

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(file_blob) AS blob_bytes,
       DBMS_LOB.GETLENGTH(content_clob) AS clob_characters
FROM documents;
~~~

BLOB length can be interpreted as content byte count. CLOB/NCLOB length is character count per LOB semantics; stored byte count depends on character set and encoding.

Do not take the result of GETLENGTH on a CLOB and divide by 1024 to conclude the exact KB on storage. That is merely dividing character count by an arithmetic factor, not physical storage size.

### 2.1. NULL LOB and Empty LOB

These two states differ:

- NULL LOB: the column has no LOB locator/content.
- Empty LOB: has a valid LOB locator, but content length is 0.

Example:

~~~sql
INSERT INTO documents(document_id, content_clob, file_blob)
VALUES (1, NULL, NULL);

INSERT INTO documents(document_id, content_clob, file_blob)
VALUES (2, EMPTY_CLOB(), EMPTY_BLOB());
~~~

You can check:

~~~sql
SELECT document_id,
       CASE WHEN content_clob IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS clob_state,
       DBMS_LOB.GETLENGTH(content_clob) AS clob_length
FROM documents
ORDER BY document_id;
~~~

For a NULL LOB, GETLENGTH returns NULL. For an empty LOB, length is 0. When analyzing statistics, count NULL rows, rows with locators, and total logical length separately.

## 3. Measuring Logical LOB Length in a Table

Suppose table DOCUMENTS has BLOB FILE_CONTENT and CLOB DESCRIPTION.

### 3.1. Measuring Length Per Row

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(file_content) AS file_bytes,
       DBMS_LOB.GETLENGTH(description) AS description_characters
FROM documents
ORDER BY document_id;
~~~

This query helps locate rows with unusually large LOBs. On very large tables, add predicates, partition pruning, or sample limits to avoid scanning the entire table solely for statistics.

### 3.2. Total Logical Length

~~~sql
SELECT COUNT(*) AS row_count,
       COUNT(file_content) AS nonnull_blob_count,
       SUM(DBMS_LOB.GETLENGTH(file_content)) AS total_blob_bytes,
       COUNT(description) AS nonnull_clob_count,
       SUM(DBMS_LOB.GETLENGTH(description)) AS total_clob_characters
FROM documents;
~~~

SUM ignores NULLs. Thus TOTAL_BLOB_BYTES sums only non-NULL BLOB lengths; empty BLOBs contribute 0.

### 3.3. Finding the Largest LOBs

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(file_content) AS file_bytes
FROM documents
WHERE file_content IS NOT NULL
ORDER BY DBMS_LOB.GETLENGTH(file_content) DESC
FETCH FIRST 20 ROWS ONLY;
~~~

FETCH FIRST requires an Oracle version supporting the row limiting clause. On older releases, wrap the query and use ROWNUM.

To find the largest CLOB by character count, use GETLENGTH on the CLOB; to measure actual encoded bytes, account for character set and storage representation.

### 3.4. Size Distribution

You can bucket rows by logical length:

~~~sql
SELECT CASE
           WHEN file_content IS NULL THEN 'NULL'
           WHEN DBMS_LOB.GETLENGTH(file_content) = 0 THEN 'EMPTY'
           WHEN DBMS_LOB.GETLENGTH(file_content) < 1024 THEN '< 1 KB'
           WHEN DBMS_LOB.GETLENGTH(file_content) < 1048576 THEN '1 KB - 1 MB'
           ELSE '>= 1 MB'
       END AS size_bucket,
       COUNT(*) AS document_count
FROM documents
GROUP BY
    CASE
        WHEN file_content IS NULL THEN 'NULL'
        WHEN DBMS_LOB.GETLENGTH(file_content) = 0 THEN 'EMPTY'
        WHEN DBMS_LOB.GETLENGTH(file_content) < 1024 THEN '< 1 KB'
        WHEN DBMS_LOB.GETLENGTH(file_content) < 1048576 THEN '1 KB - 1 MB'
        ELSE '>= 1 MB'
    END
ORDER BY size_bucket;
~~~

For BLOBs, these thresholds are bytes. For CLOBs, they are characters; rename bucket labels to reflect the proper unit.

## 4. Querying LOB Metadata Using the Data Dictionary

Oracle provides views scoped by privilege:

- USER_LOBS: LOB columns owned by the current schema.
- ALL_LOBS: LOB columns visible to the user.
- DBA_LOBS: LOB metadata across the database, requiring appropriate privileges.

Example:

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       index_name,
       tablespace_name,
       chunk,
       pctversion,
       retention,
       cache,
       in_row,
       securefile
FROM user_lobs
ORDER BY table_name, column_name;
~~~

These columns identify how the LOB column is stored and its corresponding segment/index. Some attributes carry different meanings depending on BasicFiles vs. SecureFiles and the Oracle release.

### 4.1. Key Metadata Columns to Note

| Attribute | Meaning |
|---|---|
| TABLE_NAME | Table containing the LOB column |
| COLUMN_NAME | LOB column name |
| SEGMENT_NAME | LOB data segment name for non-partitioned configurations |
| INDEX_NAME | Associated LOB index |
| TABLESPACE_NAME | Tablespace storing the LOB segment |
| CHUNK | Configured chunk size for LOB storage |
| PCTVERSION | BasicFiles parameter managing old LOB versions |
| RETENTION | LOB version retention policy, typically associated with SecureFiles |
| CACHE | Caching attribute of LOB storage |
| IN_ROW | Whether small LOBs are allowed to be stored inline in the row |
| SECUREFILE | Indicates whether the LOB uses SecureFiles or BasicFiles |

Do not interpret PCTVERSION and RETENTION as current LOB storage size. They are storage/versioning management attributes. LOB segment growth may relate to old versions, retention, or heavy DML updates rather than necessarily indicating a temporary LOB leak.

### 4.2. Viewing Table DDL for Storage Clauses

~~~sql
SELECT DBMS_METADATA.GET_DDL(
    'TABLE',
    'DOCUMENTS',
    USER
)
FROM dual;
~~~

DDL helps inspect LOB storage clauses, TABLESPACE, ENABLE/DISABLE STORAGE IN ROW, BasicFiles/SecureFiles, and compression/deduplication/encryption options if present.

DBMS_METADATA requires appropriate metadata access privileges. Object names are normally passed in uppercase if created with unquoted identifiers.

## 5. Segment Size: Allocated Extent Space

USER_SEGMENTS/ALL_SEGMENTS/DBA_SEGMENTS report segments and their allocated extent space.

Example viewing segments in the schema:

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb,
       extents
FROM user_segments
WHERE segment_type IN ('LOBSEGMENT', 'LOBINDEX')
ORDER BY bytes DESC;
~~~

The LOB data segment and LOB index are two separate structures. Common segment types are LOBSEGMENT and LOBINDEX.

### 5.1. Joining USER_LOBS with USER_SEGMENTS

For non-partitioned LOBs, you can join LOB metadata with segments:

~~~sql
SELECT l.table_name,
       l.column_name,
       l.segment_name AS lob_segment,
       l.index_name AS lob_index,
       l.tablespace_name,
       ROUND(NVL(s.bytes, 0) / 1024 / 1024, 2) AS lob_allocated_mb,
       ROUND(NVL(i.bytes, 0) / 1024 / 1024, 2) AS lob_index_mb
FROM user_lobs l
LEFT JOIN user_segments s
       ON s.segment_name = l.segment_name
      AND s.segment_type = 'LOBSEGMENT'
LEFT JOIN user_segments i
       ON i.segment_name = l.index_name
      AND i.segment_type = 'LOBINDEX'
ORDER BY l.table_name, l.column_name;
~~~

This query illustrates regular LOB segments. If a table is partitioned or subpartitioned, use the corresponding LOB partition views to get the segment names of each partition/subpartition; do not assume a single SEGMENT_NAME in USER_LOBS represents all partitioned segments.

### 5.2. Total LOB Space by Tablespace

~~~sql
SELECT tablespace_name,
       segment_type,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS allocated_mb,
       COUNT(*) AS segment_count
FROM user_segments
WHERE segment_type IN ('LOBSEGMENT', 'LOBINDEX')
GROUP BY tablespace_name, segment_type
ORDER BY tablespace_name, segment_type;
~~~

This shows space allocated to segments, not logical payloads. If totaling tables, regular indexes, and LOBs together, expand the segment type list and cross-check object metadata to avoid missing or double-counting segments.

### 5.3. Allocated Bytes Are Not Bytes Holding Active Data

USER_SEGMENTS.BYTES reflects allocated extents. A segment can contain internal free space, unused blocks, or space freed after LOBs were deleted or trimmed.

Deleting a row or calling DBMS_LOB.TRIM does not necessarily shrink the tablespace file immediately. The segment may retain extents for reuse by future writes.

To reclaim space back to the tablespace/file, evaluate shrink/move/reorganization appropriate for the LOB type, storage format, partitioning, and Oracle release. Do not run SHRINK/MOVE simply because logical length dropped; first measure internal free space and verify operational requirements.

## 6. IN ROW, OUT OF ROW, and Impact on Measurement

LOBs can be stored inline in the row or out of row:

- **IN ROW:** small LOB content can be stored with the row inside the table segment when storage permits.
- **OUT OF ROW:** the row stores a locator; content is stored in the LOB segment.

Therefore, when IN ROW is enabled, not every byte of LOB data appears in LOBSEGMENT. Part of the data resides in the table segment.

The IN_ROW attribute in USER_LOBS indicates whether configuration permits inline storage. It does not mean every LOB in the table is definitely stored inline; individual value size and storage conditions determine actual placement.

When calculating total storage of a table with LOBs, examine all of:

1. Table segment/partition.
2. LOB data segment/partition.
3. LOB index segment/partition.
4. Regular indexes and other auxiliary segments.

Do not add logical GETLENGTH to allocated segment bytes as if they were two independent parts of the same measurement.

## 7. BasicFiles, SecureFiles, and Compression/Deduplication

Oracle supports two main LOB storage models:

- BasicFiles is the traditional LOB storage mechanism.
- SecureFiles is the more modern LOB storage mechanism, offering capabilities such as compression, deduplication, and encryption depending on release/edition/licensing.

SecureFiles can reduce physical storage through compression or deduplication. In such cases, total logical length can be much larger than segment allocation. Encryption, metadata, chunks, and free space also affect actual byte counts.

Attributes such as COMPRESSION, DEDUPLICATION, and ENCRYPT can be viewed via the metadata view appropriate for your Oracle release:

~~~sql
SELECT table_name,
       column_name,
       securefile,
       compression,
       deduplication,
       encrypt,
       cache,
       in_row
FROM user_lobs
ORDER BY table_name, column_name;
~~~

If the view/version does not expose an attribute or privileges are insufficient, inspect DDL with DBMS_METADATA and check documentation for your running release.

Do not conclude SecureFiles is always smaller than BasicFiles in every workload. Compression/deduplication incur CPU costs, reduction ratios depend on content, and options may carry separate licensing requirements.

## 8. Partitioned LOBs and Per-Partition Metadata

Partitioned tables can have separate LOB segments for each partition or subpartition. Space is then spread across multiple segments rather than one single segment.

Commonly used views:

- USER_LOB_PARTITIONS / ALL_LOB_PARTITIONS / DBA_LOB_PARTITIONS.
- USER_LOB_SUBPARTITIONS / ALL_LOB_SUBPARTITIONS / DBA_LOB_SUBPARTITIONS.
- USER_SEGMENTS / DBA_SEGMENTS for segment allocations.

Example viewing LOB partition metadata:

~~~sql
SELECT table_name,
       column_name,
       partition_name,
       lob_partition_name,
       lob_indpart_name,
       tablespace_name
FROM user_lob_partitions
WHERE table_name = 'DOCUMENTS'
ORDER BY column_name, partition_name;
~~~

Column names and visibility may vary by partitioning type/release. Use DESC USER_LOB_PARTITIONS or consult the Data Dictionary Reference for your exact version if extending the query.

Then correlate LOB partition/index partition names with USER_SEGMENTS:

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb
FROM user_segments
WHERE segment_type IN ('LOBSEGMENT', 'LOBINDEX')
ORDER BY segment_name;
~~~

The second query lists LOB segments in the schema; combine it with segment names from partition metadata to determine which partition occupies space.

Do not use the earlier USER_LOBS join query as a complete measurement for partitioned tables. Sum all corresponding LOB partitions and subpartitions.

## 9. What Is a Temporary LOB?

A temporary LOB is a temporary LOB created to process data in PL/SQL/SQL rather than being a persistent LOB column of a table row.

A temporary LOB can be created:

- Explicitly via DBMS_LOB.CREATETEMPORARY.
- Implicitly by certain LOB operations, functions, or expressions.
- When processing intermediate CLOB/BLOB values, concatenating strings, or producing new LOB results.
- When an API returns a temporary LOB locator.

Temporary LOBs are normally stored in the temporary tablespace; cache attributes and operation types can affect resource usage. They are not listed as LOB columns in USER_LOBS.

### 9.1. Temporary LOBs vs. Persistent LOBs

| Criterion | Persistent LOB | Temporary LOB |
|---|---|---|
| Purpose | LOB data belonging to a table/row | Intermediate data during processing |
| Metadata | USER_LOBS/DBA_LOBS | Tracked via V$TEMPORARY_LOBS |
| Storage | Tablespace of the LOB segment | Temporary tablespace |
| Lifecycle | Follows table data and transactions | CALL or SESSION duration |
| Release | DELETE/UPDATE row and segment management | DBMS_LOB.FREETEMPORARY or end of duration |
| Is a table row? | Yes | Not necessarily |

Do not use DELETE FROM table to free a temporary LOB; temporary LOBs are not persistent rows in a table.

## 10. Creating Temporary LOBs with DBMS_LOB.CREATETEMPORARY

Example creating a temporary CLOB:

~~~sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_temp_clob,
        amount  => LENGTH('Temporary text'),
        buffer  => 'Temporary text'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_temp_clob)
    );

    DBMS_LOB.FREETEMPORARY(l_temp_clob);
END;
/
~~~

Parameters:

- LOB_LOC: locator receiving the temporary LOB.
- CACHE: requests caching LOB data per API option.
- DUR: CALL or SESSION duration.

Using DBMS_LOB.SESSION means the temporary LOB persists for the session until freed or the session terminates. With CALL duration, the temporary LOB is managed according to the corresponding call lifecycle.

### 10.1. CALL and SESSION Duration

| Duration | Lifecycle |
|---|---|
| DBMS_LOB.CALL | Freed when the call ends per temporary LOB semantics |
| DBMS_LOB.SESSION | Persists in the session until FREETEMPORARY or session termination |

SESSION duration is useful when a temporary LOB must survive across multiple subprogram calls within the same session. However, it creates an explicit cleanup responsibility. In connection pools, sessions are reused across many requests; failing to free session-duration temporary LOBs can cause temporary LOB counts to accumulate across requests.

### 10.2. CACHE and NOCACHE

CACHE requests Oracle to cache temporary LOB data as supported by the API/storage. NOCACHE avoids requesting caching under that option. Caching does not change logical length and does not replace freeing the locator.

Choose cache mode based on read/write patterns and performance testing. Do not enable CACHE for every large LOB out of habit, as it can affect the buffer cache and other workloads.

## 11. ISTEMPORARY and FREETEMPORARY

Two essential lifecycle management APIs:

- DBMS_LOB.ISTEMPORARY(locator): returns 1 if the locator points to a temporary LOB; returns 0 otherwise.
- DBMS_LOB.FREETEMPORARY(locator): frees the temporary LOB.

Example checking before freeing:

~~~sql
IF l_temp_clob IS NOT NULL
   AND DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1
THEN
    DBMS_LOB.FREETEMPORARY(l_temp_clob);
END IF;
~~~

Never call FREETEMPORARY on a persistent LOB locator. Checking ISTEMPORARY first distinguishes temporary locators from table-owned LOBs.

### 11.1. CLOSE Is Not the Same as FREETEMPORARY

DBMS_LOB.CLOSE ends an OPEN state on a locator when the application called DBMS_LOB.OPEN. It does not replace FREETEMPORARY.

- OPEN/CLOSE manages a LOB's open state for a sequence of operations.
- CREATETEMPORARY/FREETEMPORARY manages creating and freeing temporary LOBs.

Closing a LOB does not mean the temporary LOB has been freed.

### 11.2. TRIM Does Not Free the Locator

DBMS_LOB.TRIM can shorten LOB content to at most the specified length:

~~~sql
DBMS_LOB.TRIM(l_temp_clob, 0);
~~~

TRIM empties the content, but the locator remains a temporary LOB. When no longer used, FREETEMPORARY is still required. TRIM can be useful for reusing the same temporary LOB inside a loop, though it does not immediately return the entire temporary LOB to the pool.

## 12. Safely Freeing Temporary LOBs on Exceptions

A common source of leaks is creating a temporary LOB and having code raise an exception before FREETEMPORARY executes.

Cleanup pattern:

~~~sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp_clob,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp_clob,
        LENGTH('Generated content'),
        'Generated content'
    );

    -- Process l_temp_clob here.

    IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_temp_clob);
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        IF l_temp_clob IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_temp_clob);
        END IF;

        RAISE;
END;
/
~~~

In production code, cleanup can be placed in a nested block to ensure every normal and error path calls cleanup once. After FREETEMPORARY, do not continue reading/writing that locator.

Do not swallow exceptions in a cleanup handler. If the original error should propagate to the caller, call RAISE after releasing resources.

### 12.1. Returning a Temporary LOB to a Caller

If a procedure creates a temporary LOB and returns its locator via an OUT parameter, clearly define ownership:

- The procedure creates and returns the locator; the caller is responsible for calling FREETEMPORARY after use.
- Or the procedure copies content into a persistent LOB/other destination and frees the temporary LOB itself before exiting.

Never free the locator before the caller uses the result. Likewise, never let both caller and callee think they are the sole owner and free it multiple times.

Example ownership contract:

~~~sql
CREATE OR REPLACE PROCEDURE build_temp_document (
    p_result OUT CLOB
) IS
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        p_result,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        p_result,
        LENGTH('Document body'),
        'Document body'
    );
END;
/
~~~

Caller receives and frees it:

~~~sql
DECLARE
    l_result CLOB;
BEGIN
    build_temp_document(l_result);

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_result));

    IF DBMS_LOB.ISTEMPORARY(l_result) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_result);
    END IF;
END;
/
~~~

This is an illustrative pattern. Real APIs should document who owns the locator, which duration is used, and how the caller must clean up on exception paths.

## 13. Implicitly Created Temporary LOBs

Not every temporary LOB originates from an explicit CREATETEMPORARY call written by a developer. Certain LOB operations can create intermediate temporary LOBs.

Example processing a CLOB:

~~~sql
DECLARE
    l_source CLOB;
    l_result CLOB;
BEGIN
    SELECT description
    INTO l_source
    FROM documents
    WHERE document_id = 100;

    l_result := l_source || TO_CLOB(' - reviewed');

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_result));

    IF l_result IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_result) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_result);
    END IF;
END;
/
~~~

Depending on the expression and data types, an intermediate LOB result can be a temporary LOB. Use ISTEMPORARY to check before freeing; do not assume every locator is temporary.

SQL/PLSQL expressions returning CLOBs, LOB concatenations, or LOB transformation functions can create temporary results. When code runs in loops, inspect implicit temporary LOBs as well, not only explicit CREATETEMPORARY calls.

## 14. What Is a Temporary LOB Leak?

A temporary LOB leak occurs when an application creates temporary LOBs but retains locators or fails to free LOBs when no longer needed. Common scenarios:

- Calling CREATETEMPORARY inside every loop iteration without calling FREETEMPORARY.
- A procedure creates a SESSION-duration LOB and returns the result, and the caller forgets to free it.
- An exception exits a procedure before cleanup runs.
- A package global holds a temporary LOB locator across multiple calls.
- An application uses a connection pool where sessions are reused; temp LOBs from prior requests remain alive.
- Expressions create implicit temporary LOBs without code checking/freeing when appropriate.
- Copying locators across multiple variables obscures ownership.

### 14.1. Common Symptoms

- Per-session temporary LOB counts grow steadily after each request.
- Temporary tablespace usage grows over time even though SQL sort/hash workloads have not grown proportionally.
- One session holds many CACHE_LOBS or NOCACHE_LOBS.
- The first batch runs normally, while subsequent batches consume progressively more temporary space.
- When the session closes, the associated temporary LOB usage disappears.
- Session pool reuses connections, causing resources to persist across requests.

Seeing TEMP tablespace grow once is not enough to conclude a leak. Sorts, hash joins, temporary tables, and other SQL operations also use TEMP. Correlate per-session temporary LOB counts and temporary segment types.

## 15. Monitoring Temporary LOBs with V$TEMPORARY_LOBS

V$TEMPORARY_LOBS provides per-session temporary LOB counts, broken down by cache/abstract LOB categories supported by the view.

Example inspecting sessions:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.program,
       t.cache_lobs,
       t.nocache_lobs,
       t.abstract_lobs
FROM v$session s
JOIN v$temporary_lobs t
  ON t.sid = s.sid
WHERE s.username IS NOT NULL
ORDER BY
    t.cache_lobs + t.nocache_lobs + t.abstract_lobs DESC;
~~~

These columns are LOB counts per category, not byte sizes. Use this query to find sessions with abnormally high temporary LOB counts.

Access to V$SESSION and V$TEMPORARY_LOBS depends on account privileges. DBAs can grant access to dynamic performance views per policy; do not grant broad privileges merely for a regular application to monitor all sessions.

### 15.1. Monitoring the Current Session

If you know the session's SID, you can filter:

~~~sql
SELECT sid,
       cache_lobs,
       nocache_lobs,
       abstract_lobs
FROM v$temporary_lobs
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

This query helps compare before/after a procedure call within the same session. Repeat multiple times and observe counts after each call.

### 15.2. Oracle RAC

In RAC, each session belongs to an instance. You can use GV$TEMPORARY_LOBS and GV$SESSION, joining on INST_ID as well:

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       t.cache_lobs,
       t.nocache_lobs,
       t.abstract_lobs
FROM gv$session s
JOIN gv$temporary_lobs t
  ON t.inst_id = s.inst_id
 AND t.sid = s.sid
WHERE s.username IS NOT NULL
ORDER BY s.inst_id, s.sid;
~~~

If the database is not RAC, V$ views suffice. GV$ views require appropriate privileges and return cluster-wide data.

## 16. Monitoring the Temporary Tablespace

V$TEMPSEG_USAGE reports temporary segments currently in use. This view reflects sorts/hashes and other temporary segment types as well, not only temporary LOBs.

~~~sql
SELECT username,
       tablespace,
       segtype,
       sql_id,
       SUM(blocks) AS blocks_used,
       SUM(extents) AS extents_used
FROM v$tempseg_usage
GROUP BY username, tablespace, segtype, sql_id
ORDER BY blocks_used DESC;
~~~

Use SEGTYPE to distinguish segment categories. Values like LOB_DATA/LOB_INDEX may appear for temporary LOBs; SORT/HASH reflect other operations. Check actual values and documentation for your exact release before building dashboards tied to a hardcoded SEGTYPE list.

### 16.1. TEMP Tablespace Overview

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes_used) / 1024 / 1024, 2) AS used_mb,
       ROUND(SUM(bytes_free) / 1024 / 1024, 2) AS free_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

V$TEMP_SPACE_HEADER provides used/free space per tempfile and tablespace. These are aggregate totals and do not indicate that all space belongs to temporary LOBs.

You can query DBA_TEMP_FREE_SPACE to inspect total size, allocated, and free space of temporary tablespaces if your account has privileges.

### 16.2. Do Not Conclude a Leak from TEMP Usage Alone

TEMP growth can result from:

- Large sorts.
- Hash joins/hash aggregations.
- Global temporary tables or other temporary operations.
- Temporary LOBs.
- Parallel queries or running batches.

Combine V$TEMPORARY_LOBS, V$TEMPSEG_USAGE, SQL_ID, session, program, and workload timing to pinpoint the source.

## 17. Workflow for Investigating Temporary LOB Leaks

A practical workflow:

1. Pick a test session or observable application session.
2. Record baseline CACHE_LOBS, NOCACHE_LOBS, and ABSTRACT_LOBS.
3. Call the procedure once and check again.
4. Repeat the same procedure multiple times in the same session.
5. Observe whether counts rise steadily or return to baseline after each call.
6. Inspect code for CREATETEMPORARY or expressions producing temporary LOBs.
7. Check all normal and exception exit paths.
8. Audit package globals, locator-holding variables, and OUT parameter ownership.
9. Call FREETEMPORARY where locator ownership belongs.
10. Re-run the test and cross-check V$TEMPORARY_LOBS along with TEMP usage.

### 17.1. Baseline and Repeated Call Example

You can create a lab procedure that creates a SESSION-duration temporary LOB:

~~~sql
CREATE OR REPLACE PROCEDURE lab_create_temp_lob IS
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp,
        LENGTH('Temporary payload'),
        'Temporary payload'
    );

    -- Intentionally omitted free to observe in a lab schema.
END;
/
~~~

Call multiple times in the same session:

~~~sql
BEGIN
    lab_create_temp_lob;
    lab_create_temp_lob;
    lab_create_temp_lob;
END;
/
~~~

Inspect V$TEMPORARY_LOBS before and after. Then fix the procedure to call FREETEMPORARY and repeat the test.

This lab intentionally creates a leak scenario. Never run this procedure repeatedly on production or shared sessions; ending the lab session releases remaining session-duration temporary LOBs.

### 17.2. Comparing CALL Duration and SESSION Duration

Repeat the same test with CALL duration and SESSION duration:

- CALL duration is freed when the call finishes per corresponding semantics.
- SESSION duration stays alive until freed or session termination.

If code runs inside a session pool, session-duration temporary LOBs especially require explicit cleanup because the database session does not necessarily close after each application request.

## 18. Designing Cleanup Inside Loops

Common mistake:

~~~sql
FOR i IN 1 .. 10000 LOOP
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.SESSION
    );

    -- Create content and process.
    -- FREETEMPORARY not called.
END LOOP;
~~~

Each iteration allocates another session-duration temporary LOB. When the old locator is overwritten, the application loses the reference needed to free each individual LOB.

### 18.1. Create, Use, and Free Within Each Iteration

~~~sql
FOR i IN 1 .. 10000 LOOP
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.CALL
    );

    BEGIN
        DBMS_LOB.WRITEAPPEND(
            l_temp,
            LENGTH('Batch item'),
            'Batch item'
        );

        -- Process l_temp.
    EXCEPTION
        WHEN OTHERS THEN
            IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
                DBMS_LOB.FREETEMPORARY(l_temp);
            END IF;
            RAISE;
    END;

    IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_temp);
    END IF;
END LOOP;
~~~

This example demonstrates cleanup on both normal and exception paths. Even when using CALL duration and the call ends right after the loop, Oracle manages call lifetime, yet explicit freeing releases resources earlier once no longer needed.

### 18.2. Reusing One Temporary LOB

If a workload generates many sequential results, you can create one temporary LOB outside the loop and TRIM it to 0 for reuse:

~~~sql
DECLARE
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.SESSION
    );

    FOR i IN 1 .. 1000 LOOP
        DBMS_LOB.TRIM(l_temp, 0);

        DBMS_LOB.WRITEAPPEND(
            l_temp,
            LENGTH('One item'),
            'One item'
        );

        -- Process current content before the next iteration.
    END LOOP;

    DBMS_LOB.FREETEMPORARY(l_temp);
EXCEPTION
    WHEN OTHERS THEN
        IF l_temp IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_temp) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_temp);
        END IF;
        RAISE;
END;
/
~~~

TRIM preserves the locator while emptying content. This can reduce the number of temporary LOB allocations, though it should be benchmarked because underlying allocations may still be retained for reuse.

## 19. Package State and Connection Pools

A package can hold global variables across a session:

~~~sql
CREATE OR REPLACE PACKAGE temp_lob_state AS
    g_document CLOB;
END temp_lob_state;
/
~~~

If a package assigns a session-duration temporary LOB to G_DOCUMENT and fails to free it, the locator can persist in package state for the entire session.

In connection-pooled applications:

- Request A borrows database session 42 and creates a temporary LOB.
- Request A returns the connection to the pool, while the database session stays alive.
- Request B borrows session 42 again.
- Old temporary LOBs can still exist if not freed.
- Repeated requests can accumulate resources.

When returning a connection to a pool, do not assume the Oracle session closes. The application or a package cleanup hook must free created locators and reset package state per policy.

Do not hold temporary LOB locators in package globals without explicit ownership and cleanup lifecycles.

## 20. Temporary LOBs vs. Persistent LOBs: Avoiding Wrong Cleanup

Never call FREETEMPORARY on a persistent locator retrieved from a table column:

~~~sql
SELECT content_clob
INTO l_content
FROM documents
WHERE document_id = 100;
~~~

This locator references the row's persistent LOB. Do not use FREETEMPORARY to free it.

You can check:

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_content) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_content);
END IF;
~~~

Free only when ISTEMPORARY returns 1. Assigning a persistent locator to a PL/SQL variable does not turn the persistent LOB into a temporary LOB.

Conversely, an expression producing a temporary CLOB may be assigned to a variable and then require cleanup. Therefore, do not rely on variable names or the CLOB type alone to decide whether a locator is persistent or temporary.

## 21. When a LOB Segment Grows Without a Temporary LOB Leak

Several causes can grow a persistent LOB segment:

- The application updates LOBs frequently, creating old versions needed for read consistency.
- PCTVERSION/RETENTION retains old LOB versions per storage policy.
- Deleting/updating content leaves internal free space while extents remain allocated.
- SecureFiles compression/deduplication changes the ratio between logical and physical size.
- OUT OF ROW LOB storage grows due to large payloads.
- Partition segments grow according to data distribution.
- DML/retention/backup/recovery workloads create temporary storage demand.

Therefore, distinguish:

- USER_SEGMENTS growing for LOBSEGMENT: persistent LOB segments allocating additional extents.
- V$TEMPORARY_LOBS growing per session: increasing count of live temporary LOBs.
- V$TEMPSEG_USAGE growing: temporary segments in use, possibly from LOBs, sorts, or hashes.

These three signals help isolate the exact category of issue.

## 22. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Treating GETLENGTH(CLOB) as physical bytes | Wrong storage estimates | Explicitly track character vs. byte units |
| Treating USER_SEGMENTS.BYTES as logical payload | Confusing extent allocation with content | Compare GETLENGTH against segment allocation |
| Checking only USER_LOBS for partitioned tables | Missing LOB partitions/subpartitions | Query USER_LOB_PARTITIONS/SUBPARTITIONS |
| Forgetting LOB indexes | Incomplete storage metadata | Include INDEX_NAME and LOBINDEX |
| Ignoring IN ROW storage | Underestimating data stored in the table segment | Include the table segment when measuring a table |
| Assuming TEMP growth is definitely a LOB leak | Misdiagnosing sort/hash usage | Combine V$TEMPORARY_LOBS and V$TEMPSEG_USAGE |
| Creating SESSION-duration LOBs in a loop without freeing | Temporary LOBs accumulate in session | Call FREETEMPORARY or reuse under control |
| Cleaning up only on normal path | Exceptions leave locators alive | Clean up in exception handlers |
| Thinking CLOSE frees a temporary LOB | Locator remains alive | Call FREETEMPORARY |
| Thinking TRIM frees a locator | Only content is truncated | Call FREETEMPORARY when done |
| Freeing a persistent LOB locator | Wrong API/lifecycle usage | Check ISTEMPORARY |
| Both caller and callee freeing locator | Unclear ownership, potential errors | Designate one side as responsible |
| Package globals holding locators | Resources persist across requests | Reset state and free before returning session |
| Assuming connection pool closes session per request | Session-duration temporary LOBs linger | Clean up per request/session lifecycle |
| Concluding unshrunk segment is a leak | Extents may be retained for reuse | Inspect internal free space and storage policy |

## 23. Checklist for Measuring Storage and Investigating Temporary LOBs

### Measuring Persistent LOBs

- [ ] Identify table, column, and datatype BLOB/CLOB/NCLOB.
- [ ] Measure logical length using DBMS_LOB.GETLENGTH.
- [ ] Note clearly that BLOB is bytes and CLOB/NCLOB is characters.
- [ ] Separately count NULL, empty LOBs, and populated LOBs.
- [ ] Inspect USER_LOBS/ALL_LOBS/DBA_LOBS.
- [ ] Inspect USER_SEGMENTS/DBA_SEGMENTS for LOBSEGMENT and LOBINDEX.
- [ ] Check IN_ROW, SecureFiles/BasicFiles, compression/deduplication.
- [ ] If partitioned, inspect LOB partitions/subpartitions.
- [ ] Account for the table segment because inline LOBs can reside in rows.
- [ ] Do not confuse allocated bytes with logical payloads.

### Investigating Temporary LOBs

- [ ] Check code for CREATETEMPORARY or expressions producing intermediate LOBs.
- [ ] Identify CALL vs. SESSION duration.
- [ ] Define locator ownership when returned via OUT parameters.
- [ ] Check ISTEMPORARY before calling FREETEMPORARY.
- [ ] Clean up on both normal and exception paths.
- [ ] Audit package globals and locator-holding variables.
- [ ] Monitor V$TEMPORARY_LOBS by SID/session.
- [ ] Cross-check V$TEMPSEG_USAGE and V$TEMP_SPACE_HEADER.
- [ ] Distinguish LOB temp segments from SORT/HASH.
- [ ] Repeat the procedure on the same session to test whether counts accumulate.
- [ ] Test under connection pool session reuse.
- [ ] Never call FREETEMPORARY on persistent LOB locators.

## 24. Key Takeaways

- DBMS_LOB.GETLENGTH measures logical length: BLOB in bytes, CLOB/NCLOB in characters.
- Logical length is not allocated segment bytes; character sets, IN ROW storage, chunks, free space, and SecureFiles options affect storage.
- USER_LOBS describes LOB columns; USER_SEGMENTS reports allocated extents for LOBSEGMENT and LOBINDEX.
- For partitioned LOBs, inspect USER_LOB_PARTITIONS and USER_LOB_SUBPARTITIONS along with their corresponding segments.
- IN ROW can place part of LOB content inside the table segment, so do not measure LOBSEGMENT alone.
- BasicFiles PCTVERSION and SecureFiles RETENTION relate to old LOB versions; segment growth does not automatically mean a temporary LOB leak.
- Temporary LOBs hold intermediate data, typically use temporary tablespace, and do not appear as LOB columns in USER_LOBS.
- CREATETEMPORARY creates a temporary LOB; ISTEMPORARY identifies the locator; FREETEMPORARY frees it.
- CALL and SESSION durations have different lifecycles; SESSION duration requires explicit cleanup, especially with connection pools.
- CLOSE and TRIM do not replace FREETEMPORARY.
- Temporary LOBs can be created implicitly by LOB operations/functions, not solely via CREATETEMPORARY.
- V$TEMPORARY_LOBS counts temporary LOBs per session; it does not directly report byte size.
- V$TEMPSEG_USAGE and V$TEMP_SPACE_HEADER help correlate temporary segments and total TEMP usage, though TEMP is also used for sorts/hashes.
- Cleanup must execute on both success and exception paths; ownership of OUT locators must be explicit.
- When investigating, distinguish persistent LOB segment growth, temporary LOB counts, and temporary tablespace usage before drawing conclusions.

### Oracle Documentation to Consult

- [Oracle Database SecureFiles and Large Objects Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/) — LOB architecture, BasicFiles/SecureFiles, temporary LOBs, and DBMS_LOB.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html) — GETLENGTH, CREATETEMPORARY, ISTEMPORARY, FREETEMPORARY, TRIM, and duration.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — USER_LOBS, USER_SEGMENTS, V$TEMPORARY_LOBS, V$TEMPSEG_USAGE, and V$TEMP_SPACE_HEADER.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Tablespaces, tempfiles, segment allocation, and space management.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — LOB locators, PL/SQL variables, exception handling, and package state.

Dictionary column names, SecureFiles options, and temporary segment monitoring details may vary across Oracle releases. Consult documentation for your exact version, verify access privileges to dynamic performance views, and measure in a lab session before altering production storage or cleanup logic.

