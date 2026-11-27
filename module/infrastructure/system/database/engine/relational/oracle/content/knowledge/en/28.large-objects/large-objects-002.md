# SecureFiles, BasicFiles, and Criteria for Choosing LOB Storage Mechanisms in Oracle

## 1. What Is a LOB?

LOB (Large Object) is a data type used to store large content such as documents, images, audio, video, PDFs, XML, JSON, or long text. Oracle Database has four main LOB types:

| Type | Content | Storage Method |
| --- | --- | --- |
| BLOB | Binary data | Stores bytes without interpreting by character set |
| CLOB | Text in the database character set | Stores characters |
| NCLOB | Text in the national character set | Stores characters in the national character set |
| BFILE | Binary file outside the database | Locator to an OS file; Oracle has read-only access |

BLOB, CLOB, and NCLOB are internal LOBs: the content belongs to the database and is managed by Oracle. BFILE is an external LOB: the content resides outside the database in a directory on the database server; Oracle stores a locator and provides an API to read the file.

LOBs differ from VARCHAR2/RAW in that they can hold much larger amounts of data than scalar column limits. A LOB column can store large content while the table row only holds a locator or a small portion of data.

## 2. LOB Locators and Data Storage Locations

### 2.1. A Locator Is Not the LOB Content

When an application selects a LOB column, Oracle typically returns a LOB locator. A locator is a reference that enables accessing the LOB content; it does not necessarily contain the entire document content.

For internal LOBs:
- The table row contains the locator.
- Small content can be stored directly in the row if STORAGE IN ROW is enabled and limits are met.
- Large content is usually stored in a separate LOB segment.
- Oracle manages the blocks, data versions, and metadata required to access the LOB.

~~~text
DOCUMENTS
  +----------------------------------------------+
  | DOC_ID | FILE_NAME | PAYLOAD_LOCATOR         |
  +----------------------------------------------+
                          |
                          v
                LOB segment (out-of-row)
                +-----------------------+
                | LOB data              |
                | LOB metadata          |
                +-----------------------+
~~~

Segment names and physical organization depend on LOB storage type, partitioning, and configuration. Do not operate directly on the internal LOB index as if it were a regular business index.

### 2.2. In-Row and Out-of-Row

Oracle supports:
- ENABLE STORAGE IN ROW: allows storing small LOBs directly in the table row.
- DISABLE STORAGE IN ROW: stores LOBs outside the row, with the locator residing in the row.

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    file_name   VARCHAR2(255 CHAR),
    content     BLOB
)
LOB (content) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
);
~~~

With ENABLE STORAGE IN ROW, small LOBs (typically up to around 4,000 bytes, also depending on row size and overhead) can be stored inline. Larger LOBs are stored out-of-row. Do not treat 4,000 bytes as a guarantee that all content of that size will always sit inline; the row also has other columns and overhead.

Choose ENABLE STORAGE IN ROW when there are many small LOBs and the application frequently reads the row together with the LOB content. Choose DISABLE STORAGE IN ROW when LOBs are usually very large, you want compact table rows, or the workload often reads metadata without reading content. Measure actual LOB sizes and metadata/content access ratios before deciding.

## 3. Persistent LOB, Temporary LOB, and BFILE

### 3.1. Persistent LOB

A persistent LOB is a LOB stored in a row of a table. BLOB, CLOB, and NCLOB can be persistent LOBs. They participate in transactions and recovery under database mechanisms.

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    content CLOB
);
~~~

### 3.2. Temporary LOB

A temporary LOB is created during processing for intermediate operations, such as concatenating large strings, transforming content, or preparing payloads before writing to a table.

Temporary LOBs use the temporary tablespace and have a lifecycle managed by the session/call depending on how they are created. They must be freed when no longer used.

~~~sql
DECLARE
    l_buffer CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_buffer,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_buffer,
        amount  => LENGTH('Temporary text'),
        buffer  => 'Temporary text'
    );

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_buffer));
    DBMS_LOB.FREETEMPORARY(l_buffer);
END;
/
~~~

If an exception occurs before FREETEMPORARY, you should have an exception handler or cleanup structure to free the temporary LOB. Do not leave temporary LOBs alive longer than necessary in shared sessions.

### 3.3. BFILE

BFILE points to a file outside the database. Oracle does not store file content in datafiles and does not allow modifying file content via a BFILE locator using DBMS_LOB.

~~~sql
CREATE DIRECTORY import_dir AS '/u01/app/import';
GRANT READ ON DIRECTORY import_dir TO app_user;

CREATE TABLE external_documents (
    document_id NUMBER PRIMARY KEY,
    file_name   VARCHAR2(255),
    external_file BFILE
);

INSERT INTO external_documents(document_id, file_name, external_file)
VALUES (1, 'manual.pdf', BFILENAME('IMPORT_DIR', 'manual.pdf'));
~~~

BFILE has these characteristics:
- The file content resides on the database server's filesystem.
- The database stores the directory object and file name in the locator.
- Oracle provides read-only access to the file via BFILE.
- The file must exist and the database server process must have read permissions.
- Database backups do not automatically protect external file content.

If the file is renamed, deleted, or filesystem permissions change, the locator may become unreadable. External files must be backed up and managed separately. BFILE is neither BasicFiles nor SecureFiles; those two mechanisms apply to internal LOBs.

## 4. BasicFiles and SecureFiles

Oracle has two internal LOB storage architectures:

- **BasicFiles:** the traditional LOB mechanism, present since older Oracle versions.
- **SecureFiles:** the newer LOB architecture, introduced in Oracle Database 11g, providing improved performance and advanced storage capabilities.

SecureFiles is recommended by Oracle for most new LOB workloads. BasicFiles is mainly needed when maintaining legacy systems, for compatibility, or under specific technical/deployment constraints.

### 4.1. BasicFiles

BasicFiles uses the traditional LOB architecture:
- Stores data in a separate LOB segment when out-of-row.
- Has the CHUNK parameter to control the LOB storage unit.
- Can use PCTVERSION to manage space retaining old LOB versions.
- Lacks full SecureFiles features such as built-in deduplication and compression.
- Can be used in tablespaces with ASSM or MSSM depending on support conditions.

BasicFiles suits legacy systems that need to preserve storage format, applications already tested with BasicFiles, workloads not needing SecureFiles features, or environments with compatibility constraints. BasicFiles is older technology and has been marked deprecated by Oracle in newer releases, though it can still be encountered in existing systems. Consult the support documentation and upgrade policy for the exact release in operation.

### 4.2. SecureFiles

SecureFiles is the more modern internal LOB architecture. Notable capabilities:
- Improved LOB read/write performance in many workloads.
- Support for compression, deduplication, and encryption.
- Support for appropriate caching, logging, and retention options.
- More flexible space management and LOB handling than BasicFiles.

SecureFiles requires a tablespace using Automatic Segment Space Management (ASSM). SecureFiles also requires an appropriate COMPATIBLE setting of 11.1.0 or higher.

~~~sql
CREATE TABLE document_secure (
    document_id NUMBER PRIMARY KEY,
    file_name   VARCHAR2(255 CHAR),
    content     BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

### 4.3. Comparison

| Criterion | BasicFiles | SecureFiles |
| --- | --- | --- |
| Architecture | Traditional | Newer, optimized for LOBs |
| ASSM | Not required in all cases | Required |
| COMPATIBLE | Supports older environments | Requires compatibility level 11.1.0 or higher |
| CHUNK | Has CHUNK parameter | Not configured the BasicFiles way |
| PCTVERSION | Can be used | Uses RETENTION mechanism instead of PCTVERSION |
| Compression | No SecureFiles LOB compression | Available |
| Deduplication | No SecureFiles dedup feature | Available |
| Encryption | No SecureFiles encryption mechanism | Available |
| Recommendation | Maintain for legacy when needed | Preferred for new designs if requirements are met |

Do not infer that SecureFiles is always faster in every case. Results also depend on LOB size, caching, storage, redo, compression level, access patterns, and system configuration.

## 5. Prerequisites for Creating SecureFiles

### 5.1. Tablespace Must Use ASSM

SecureFiles requires a tablespace with automatic segment space management. You can check:

~~~sql
SELECT tablespace_name,
       segment_space_management,
       extent_management,
       allocation_type
FROM user_tablespaces
ORDER BY tablespace_name;
~~~

If you need to inspect the entire database and have privileges:

~~~sql
SELECT tablespace_name, segment_space_management
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

SEGMENT_SPACE_MANAGEMENT must be AUTO to use SecureFiles. MSSM tablespaces do not satisfy this requirement.

### 5.2. Checking COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

SecureFiles requires COMPATIBLE 11.1.0 or higher. Changing COMPATIBLE is a major database administration decision affecting downgrade capability and compatibility; do not raise it just to create SecureFiles without an overall plan.

### 5.3. Checking DB_SECUREFILE

~~~sql
SHOW PARAMETER db_securefile;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_securefile';
~~~

DB_SECUREFILE controls SecureFiles creation. Exact values and behavior depend on Oracle configuration; common values include PERMITTED, ALWAYS, FORCE, NEVER, and IGNORE. PERMITTED allows creating SecureFiles when specified and other conditions are met. NEVER prevents creating SecureFiles.

Do not assume every LOB column automatically becomes SecureFiles just because the database is Oracle 19c. Explicitly specify STORE AS SECUREFILE or STORE AS BASICFILE when deterministic results are needed, then verify in the dictionary.

### 5.4. Edition and Licensing

Basic SecureFiles storage and extended features may carry separate licensing requirements. Specifically:
- SecureFiles compression and deduplication are tied to the Oracle Advanced Compression Option.
- SecureFiles encryption is tied to the Oracle Advanced Security Option/TDE under licensing policies.

Licensing terms vary by edition, deployment, and contract. Before enabling COMPRESS, DEDUPLICATE, or ENCRYPT in production, verify current Oracle Licensing Information and your organization's entitlements.
## 6. Specifying BasicFiles or SecureFiles at Table Creation

### 6.1. Explicitly Creating BasicFiles

~~~sql
CREATE TABLE document_basic (
    document_id NUMBER PRIMARY KEY,
    content     BLOB
)
LOB (content) STORE AS BASICFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    PCTVERSION 10
    NOCACHE
    LOGGING
);
~~~

CHUNK is a storage unit associated with BasicFiles. Its value must fit the database block size and workload. PCTVERSION reserves space for retaining old LOB versions to serve consistent reads under BasicFiles mechanics.

### 6.2. Explicitly Creating SecureFiles

~~~sql
CREATE TABLE document_secure (
    document_id NUMBER PRIMARY KEY,
    content     BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

SecureFiles does not use CHUNK and PCTVERSION in the BasicFiles configuration style. SecureFiles uses its own version/retention management mechanism.

### 6.3. Multiple LOB Columns

A table can have multiple LOB columns, and each column can have its own storage clause:

~~~sql
CREATE TABLE customer_documents (
    customer_id NUMBER PRIMARY KEY,
    profile_xml CLOB,
    avatar      BLOB,
    contract_pdf BLOB
)
LOB (profile_xml) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    CACHE READS
)
LOB (avatar) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    CACHE
)
LOB (contract_pdf) STORE AS SECUREFILE (
    TABLESPACE archive_lob_ts
    NOCACHE
    LOGGING
);
~~~

LOB columns with different access patterns can use different storage options. For example, avatars are frequently read, whereas contract PDFs may be large and rarely read.

### 6.4. Do Not Rely on Defaults When Control Is Required

Default storage can depend on DB_SECUREFILE, COMPATIBLE, and how the table is created. For systems requiring consistent deployment across dev/test/prod, specify the storage type explicitly and verify USER_LOBS after creation.

## 7. Key SecureFiles Options

### 7.1. CACHE, CACHE READS, and NOCACHE

Caching options affect how LOB data uses the database buffer cache:
- CACHE: LOB data is cached in the buffer cache on access.
- CACHE READS: cached on reads; suitable for some read-heavy, write-light workloads.
- NOCACHE: does not cache LOB data in the regular buffer cache path; suitable for large, rarely read, or streamed LOBs.

~~~sql
LOB (avatar) STORE AS SECUREFILE (CACHE)
~~~

~~~sql
LOB (manual_pdf) STORE AS SECUREFILE (NOCACHE)
~~~

Do not pick CACHE just because you want everything fast. Very large LOBs can flood the buffer cache and evict other useful data. NOCACHE also does not mean all metadata bypasses the cache.

### 7.2. LOGGING and NOLOGGING

LOGGING is the standard safe choice for recovery. NOLOGGING can reduce redo for certain supported operations, but can reduce media recoverability for data created under that mode.

~~~sql
LOB (payload) STORE AS SECUREFILE (LOGGING)
~~~

~~~sql
LOB (staging_payload) STORE AS SECUREFILE (NOLOGGING)
~~~

NOLOGGING does not mean the database generates zero redo. FORCE LOGGING at the database/tablespace level can override this choice. Before using NOLOGGING, review RMAN backups, Data Guard, standby apply, recovery windows, and post-operation backup procedures.

### 7.3. Compression

SecureFiles can compress LOBs:

~~~sql
LOB (content) STORE AS SECUREFILE (
    COMPRESS MEDIUM
)
~~~

SecureFiles compression levels include LOW, MEDIUM, and HIGH per supported Oracle syntax. Higher compression levels may save more space at the cost of increased CPU or latency impact. Measure on real data; PDF, JPEG, ZIP, video, or already compressed data may yield little additional savings.

Compression is helpful when content has repetition or redundancy, storage cost matters, and the workload can tolerate CPU overhead. Do not enable compression blindly on every LOB column. Verify compression ratios and CPU/latency impact before deploying.

### 7.4. Deduplication

SecureFiles deduplication detects duplicate LOB content to avoid storing multiple identical physical copies within Oracle's supported scope:

~~~sql
LOB (document_content) STORE AS SECUREFILE (
    DEDUPLICATE
)
~~~

If many rows hold the same file or identical content, deduplication can reduce storage consumption. For example, a document repository containing many copies of template contracts or shared manuals.

Do not confuse deduplication with a unique constraint:
- Deduplication is a physical storage optimization.
- It does not merge rows into one row.
- Each row retains its own locator and semantics.
- DML, access privileges, and metadata for each row remain managed independently.

Deduplication consumes CPU to detect duplicate content. It is useful when actual data duplication is high; if every LOB is unique, the benefit may be low.

You can use KEEP_DUPLICATES to disable deduplication:

~~~sql
LOB (private_payload) STORE AS SECUREFILE (
    KEEP_DUPLICATES
)
~~~

### 7.5. Encryption

SecureFiles supports LOB encryption:

~~~sql
LOB (sensitive_document) STORE AS SECUREFILE (
    ENCRYPT USING 'AES256'
)
~~~

Encryption protects LOB data stored on disk via Transparent Data Encryption. Proper keystore/wallet configuration and administrative privileges are required. Encryption does not replace application-level authorization; users with valid SELECT privileges can still read content through the database.

Before enabling encryption, review key management and keystore backups, restore capability when moving databases, Data Guard/standby, CPU performance, licensing, and security policies.

### 7.6. Combining Multiple Options

Example of a rarely modified document archive with many duplicates needing space savings:

~~~sql
CREATE TABLE legal_documents (
    document_id NUMBER PRIMARY KEY,
    owner_id    NUMBER NOT NULL,
    payload     BLOB
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE secure_lob_ts
    DISABLE STORAGE IN ROW
    NOCACHE
    LOGGING
    COMPRESS MEDIUM
    DEDUPLICATE
);
~~~

This is an illustrative configuration only. Do not use COMPRESS/DEDUPLICATE without appropriate licensing and workload benchmarking.

## 8. BasicFiles Storage Parameters and Version Management

### 8.1. CHUNK

CHUNK defines the storage unit associated with BasicFiles LOBs. Its value is specified in bytes and constrained by the database block size.

If chunk is too large relative to operations that usually read only a small slice, extra data may be read. If too small, metadata and I/O counts may increase. Choose based on read/write patterns and measure in practice.

SecureFiles uses a different LOB management architecture; do not apply BasicFiles CHUNK tuning thinking to SecureFiles.

### 8.2. PCTVERSION

BasicFiles uses PCTVERSION to specify the percentage of LOB segment space that may be reserved for old versions. Old versions are needed for consistent reads while another transaction is modifying the LOB.

If PCTVERSION is too low, enough old versions may not be retained for long-running queries. If too high, the segment may reserve more space for old versions than needed.

### 8.3. RETENTION

LOB storage can use RETENTION to control keeping old versions according to retention time/undo semantics. SecureFiles uses RETENTION instead of PCTVERSION.

Do not confuse LOB RETENTION with business retention policy:
- LOB RETENTION relates to retaining old LOB versions for consistent reads.
- Business retention defines how long data is kept in the system.

The two concepts serve different purposes.

## 9. DML and SQL LOB Operations

### 9.1. Direct LOB INSERT

For small content, you can INSERT a literal or an appropriate bind variable:

~~~sql
INSERT INTO document_store(document_id, content)
VALUES (1, TO_CLOB('Small text document'));
~~~

For large BLOBs, applications typically bind data using streams/LOB APIs rather than embedding literals in SQL.

### 9.2. EMPTY_CLOB and EMPTY_BLOB

EMPTY_CLOB() and EMPTY_BLOB() create an empty LOB locator, not NULL:

~~~sql
INSERT INTO document_store(document_id, content)
VALUES (2, EMPTY_CLOB());
~~~

This is useful when you want to create the row first and then write content using DBMS_LOB. A NULL column and an empty LOB differ:
- NULL: no locator/content assigned.
- EMPTY_CLOB/EMPTY_BLOB: has a locator for an empty LOB.

### 9.3. RETURNING Locator to Write a LOB

Example writing a CLOB:

~~~sql
DECLARE
    l_content CLOB;
    l_text    VARCHAR2(1000) := 'Oracle SecureFiles example';
BEGIN
    INSERT INTO document_store(document_id, content)
    VALUES (3, EMPTY_CLOB())
    RETURNING content INTO l_content;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_content,
        amount  => LENGTH(l_text),
        buffer  => l_text
    );

    COMMIT;
END;
/
~~~

For CLOB, amount is measured in characters; for BLOB, operations use bytes. Check DBMS_LOB documentation for the exact overload and units before writing binary or multibyte data.

### 9.4. Updating an Entire LOB

~~~sql
UPDATE document_store
SET content = TO_CLOB('Replacement text')
WHERE document_id = 3;
~~~

This replaces the entire CLOB value with new content. For large LOBs, applications should consider streaming and LOB APIs rather than passing huge strings inside SQL statements.

### 9.5. Partial LOB Access with DBMS_LOB

Commonly used routines:

| Routine | Purpose |
| --- | --- |
| GETLENGTH | Get LOB length |
| SUBSTR | Read part of a LOB |
| READ | Read data at an offset |
| WRITE | Write data at an offset |
| WRITEAPPEND | Append data to the end |
| APPEND | Append one LOB to another |
| COPY | Copy a range of a LOB |
| TRIM | Truncate a LOB |
| ERASE | Erase a range of content |
| COMPARE | Compare LOB contents |
| CREATETEMPORARY | Create a temporary LOB |
| FREETEMPORARY | Free a temporary LOB |

~~~sql
DECLARE
    l_content CLOB;
    l_piece   VARCHAR2(100);
BEGIN
    SELECT content
    INTO l_content
    FROM document_store
    WHERE document_id = 3
    FOR UPDATE;

    l_piece := DBMS_LOB.SUBSTR(l_content, 100, 1);
    DBMS_OUTPUT.PUT_LINE(l_piece);
END;
/
~~~

For persistent LOBs being modified, typically retrieve the locator inside a SELECT FOR UPDATE statement or use Oracle-supported locator/DML mechanisms. Do not use a locator that is out of scope or no longer valid.

### 9.6. OPEN and CLOSE

DBMS_LOB.OPEN/CLOSE can be used when performing multiple operations on a LOB. With certain LOB-related functional/domain indexes, opening and then closing the LOB lets Oracle defer index maintenance until CLOSE rather than updating after every write operation. Only use this when you understand index dependencies, and always CLOSE in both success and failure paths.

## 10. Temporary LOBs and Resource Management

Temporary LOBs can arise when calling CLOB-manipulating functions that return a temporary LOB, concatenating multiple large strings, converting between CLOB/NCLOB, using DBMS_LOB.CREATETEMPORARY, or processing intermediate data in PL/SQL.

Temporary LOBs consume temporary tablespace and can grow rapidly if an application creates many large LOBs or fails to free them.

~~~sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => FALSE,
        dur     => DBMS_LOB.SESSION
    );

    -- Perform operations on l_temp_clob.

    DBMS_LOB.FREETEMPORARY(l_temp_clob);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_temp_clob);
        END IF;
        RAISE;
END;
/
~~~

When using CALL duration, Oracle manages the lifecycle per call. When using SESSION duration, the application must ensure timely freeing or session closure. In connection pools, sessions live long, so forgetting cleanup can increase temporary LOB usage.
## 11. Choosing CACHE, COMPRESSION, DEDUPLICATION, and ENCRYPTION by Workload

### 11.1. Selection Matrix

| Workload | Consideration | Rationale |
| --- | --- | --- |
| Small avatar images, frequently read | ENABLE STORAGE IN ROW if size fits; CACHE | Content is small and often read with the row |
| Large videos, streamed, rarely updated | DISABLE STORAGE IN ROW; NOCACHE | Avoids flooding buffer cache with large LOBs |
| Contract PDFs, infrequently read | SecureFiles; NOCACHE or CACHE READS | Optimize based on read ratio and cache pressure |
| Many identical files | SecureFiles DEDUPLICATE | Can save storage space |
| Large, compressible text | SecureFiles COMPRESS after benchmarking | Reduces storage if CPU overhead is acceptable |
| Sensitive content | SecureFiles ENCRYPT and TDE | Protects data at rest |
| CLOB frequently updated in parts | Benchmark SecureFiles and DBMS_LOB APIs | Random/partial update patterns affect performance |
| Legacy application, ineligible for SecureFiles | Keep BasicFiles under a migration plan | Avoids changing storage before ready |

### 11.2. Do Not Enable All Features at Once

Compression, deduplication, and encryption can simultaneously affect CPU, I/O, latency, redo, and key management. Do not enable all of them just because SecureFiles supports them.

Selection process:
1. Measure LOB size distribution.
2. Measure read/write ratio and size per read/write.
3. Check the duplicate content ratio.
4. Measure compressibility on real data.
5. Determine encryption and key management requirements.
6. Benchmark on production-like storage.
7. Compare throughput, p95/p99 latency, CPU, I/O, redo, and storage size.
8. Verify licensing and recovery before deploying.

## 12. SecureFiles and BasicFiles in Partitioned Tables

Partitioned tables can store LOBs per partition. Each partition has a corresponding LOB segment and can set storage options as needed.

~~~sql
CREATE TABLE archived_documents (
    document_id NUMBER NOT NULL,
    created_at  DATE NOT NULL,
    payload     BLOB
)
PARTITION BY RANGE (created_at)
(
    PARTITION p2025 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026 VALUES LESS THAN (DATE '2027-01-01')
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    NOCACHE
    LOGGING
);
~~~

For partition maintenance, check which partition's LOB segment is affected, internal LOB indexes, other local/global indexes, required space during MOVE/EXCHANGE, and whether compression/encryption features are supported for the specific operation.

LOB partition metadata can be inspected via USER_LOB_PARTITIONS or DBA_LOB_PARTITIONS.

## 13. Migrating BasicFiles to SecureFiles

### 13.1. Why Migrate?

You may migrate when you want compression, deduplication, or encryption; when LOB workloads need better performance; to standardize storage architecture for new applications; or when BasicFiles becomes a barrier to operational strategy.

Do not migrate solely because SecureFiles is newer. First measure benefits, confirm licensing, verify ASSM tablespaces, and plan downtime/space.

### 13.2. MOVE LOB

For non-partitioned tables, ALTER TABLE MOVE LOB can move the LOB segment:

~~~sql
ALTER TABLE document_basic
MOVE LOB (content)
STORE AS SECUREFILE (
    TABLESPACE lob_ts
    NOCACHE
    LOGGING
);
~~~

This command rebuilds LOB storage as SecureFiles. Check syntax/limitations for your specific release and table type, reserve temporary space, and estimate DDL duration and locking impact.

### 13.3. Post-Migration Verification

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile,
       in_row,
       cache,
       logging,
       compression,
       deduplication,
       encrypt
FROM user_lobs
WHERE table_name = 'DOCUMENT_BASIC';
~~~

SECUREFILE should show YES after migration. Reconcile row counts, DBMS_LOB.GETLENGTH, application-level checksums/hashes if required, and test application reads/writes.

### 13.4. Migrating While the Table Serves Applications

ALTER TABLE MOVE LOB can incur locking and downtime depending on the operation, version, and object. If high availability is required, evaluate DBMS_REDEFINITION or a copy/swap strategy:
1. Create a destination table with SecureFiles.
2. Synchronize data and ongoing changes.
3. Recreate required constraints, indexes, grants, triggers, and dependencies.
4. Validate data.
5. Switch names/objects under a controlled procedure.

DBMS_REDEFINITION has support prerequisites and may require materialized view logs or specific privileges. Do not treat it as an automatic one-liner for every LOB table.

### 13.5. Rollback Plan

Before migrating:
- Take a backup or ensure an appropriate restore point/recovery strategy exists.
- Record DDL, grants, indexes, constraints, and triggers.
- Measure source/destination space.
- Prepare a fallback plan using the old table/segment or restore.
- Validate LOB data after migration.

DDL performs an implicit commit. You cannot roll back MOVE LOB with a standard ROLLBACK statement.

## 14. Monitoring LOB Storage with the Data Dictionary

### 14.1. USER_LOBS

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile,
       in_row,
       cache,
       logging,
       compression,
       deduplication,
       encrypt
FROM user_lobs
ORDER BY table_name, column_name;
~~~

Useful columns:
- TABLE_NAME and COLUMN_NAME: LOB column.
- SEGMENT_NAME: LOB segment.
- TABLESPACE_NAME: tablespace.
- SECUREFILE: storage type.
- IN_ROW: whether storage in row is enabled.
- CACHE and LOGGING: cache/logging choices.
- COMPRESSION, DEDUPLICATION, ENCRYPT: SecureFiles features.

Some dictionary columns depend on version and privileges; if a query reports invalid identifier, check the Reference for your exact release.

### 14.2. DBA_LOBS and ALL_LOBS

DBA_LOBS covers the entire database if you have privileges:

~~~sql
SELECT owner,
       table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile
FROM dba_lobs
ORDER BY owner, table_name, column_name;
~~~

ALL_LOBS shows LOB columns visible to the user.

### 14.3. LOB Partitions

~~~sql
SELECT table_name,
       column_name,
       partition_name,
       segment_name,
       tablespace_name,
       securefile
FROM user_lob_partitions
ORDER BY table_name, column_name, partition_name;
~~~

For subpartitioned tables, check the corresponding LOB subpartition views.

### 14.4. Segment Size

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks
FROM user_segments
WHERE segment_type LIKE 'LOB%'
ORDER BY bytes DESC;
~~~

A LOB segment can occupy many times more space than the table rows/locators. Monitor its growth separately rather than only looking at table segment size.

### 14.5. Temporary LOB Usage

You can check temporary segment usage through appropriate dynamic performance views according to privileges and database configuration, such as V$TEMPSEG_USAGE. Distinguish temporary LOB usage from temporary tablespace used for sorts/hashes.

## 15. Limitations and Considerations

### 15.1. SQL Operations on LOBs Are Not Like Scalars

Not all ordinary SQL operations apply directly to LOBs. For example, CLOB/BLOB cannot be treated like VARCHAR2/RAW in all expressions, GROUP BY, ORDER BY, or comparisons.

Use supported LOB functions such as DBMS_LOB.COMPARE, DBMS_LOB.SUBSTR, and DBMS_LOB.GETLENGTH when appropriate. For large text search, consider Oracle Text or a dedicated search architecture.

### 15.2. LOB Locators Have Lifetimes

A locator must remain valid within the session/transaction and per the API used. Do not store a locator and reuse it arbitrarily after the row is deleted, the session ends, or the locator scope expires.

### 15.3. CLOB and Character Sets

CLOB uses the database character set; NCLOB uses the national character set. Converting between character sets can trigger conversions and lose characters if the target character set cannot represent the content.

For multilingual content, check the database character set, national character set, driver, and binding method.

### 15.4. BLOB Is Bytes, Not Text

Do not convert a BLOB to VARCHAR2 for convenience. A BLOB can contain zero bytes, arbitrary binary data, and any encoding. If a BLOB is a PDF/ZIP/image, the application must process it according to that format.

### 15.5. Backup and Recovery

Internal LOBs are managed by the database and fall within database backup/recovery per configuration. BFILEs reside outside the database and must be backed up on the filesystem/object store separately.

NOLOGGING, encryption, keystores, and standbys can alter backup/recovery requirements. Test actual restores rather than only verifying that backup jobs report SUCCESS.
## 16. Choosing BasicFiles or SecureFiles?

### 16.1. SecureFiles for New Systems

Prefer SecureFiles when the database meets COMPATIBLE and ASSM requirements, needs modern LOB performance, can leverage compression/dedup/encryption if needed, licensing is verified, and the application can be tested with SecureFiles.

### 16.2. Keeping BasicFiles in Legacy Systems When Justified

Keep BasicFiles in the short term when the application or environment has compatibility constraints, the current tablespace uses MSSM with no immediate plan to move to ASSM, there is no migration window, or benchmarks show insufficient benefit.

This should be a managed decision with a modernization plan if BasicFiles becomes a limitation.

### 16.3. Quick Decision Table

| Question | If Yes | Direction |
| --- | --- | --- |
| Building a new system on Oracle 19c? | Yes | Start by evaluating SecureFiles |
| Does the tablespace use ASSM? | Yes | Satisfies a key prerequisite for SecureFiles |
| Is COMPATIBLE 11.1 or higher? | Yes | Satisfies the basic version prerequisite |
| Need compression/deduplication/encryption? | Yes | SecureFiles and verify licensing |
| Small LOB data, read together with the row? | Yes | Consider ENABLE STORAGE IN ROW and CACHE |
| Large LOBs, streamed, rarely read? | Yes | Consider DISABLE STORAGE IN ROW and NOCACHE |
| Legacy system currently stable? | Yes | Keep BasicFiles temporarily if migration has no clear benefit |
| Need to read files outside the database? | Yes | BFILE or object/file storage, not BasicFiles/SecureFiles |

### 16.4. Decision Flow

~~~text
Identify LOB data type
          |
          v
Internal or external?
    |             |
 Internal       External
    |             |
 BLOB/CLOB       BFILE / object storage
    |
    v
Oracle 19c, appropriate COMPATIBLE?
    |
    v
ASSM tablespace?
    |             |
   Yes            No
    |             |
Evaluate        Convert to ASSM or
SecureFiles     consider BasicFiles
    |
    v
Choose cache / compression / dedup / encryption
    |
    v
Verify license + benchmark + recovery
    |
    v
Select storage and deploy under control
~~~

## 17. Lab Example: Creating and Comparing Both LOB Types

Examples use a lab schema and an existing ASSM tablespace. If LOB_TS does not exist, substitute an ASSM tablespace provided by the DBA.

### 17.1. Create a BasicFiles Table

~~~sql
CREATE TABLE lob_basic_lab (
    id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS BASICFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    PCTVERSION 10
    NOCACHE
    LOGGING
);
~~~

### 17.2. Create a SecureFiles Table

~~~sql
CREATE TABLE lob_secure_lab (
    id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    DISABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

### 17.3. Verify Storage Type

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       securefile,
       in_row,
       cache,
       logging
FROM user_lobs
WHERE table_name IN ('LOB_BASIC_LAB', 'LOB_SECURE_LAB')
ORDER BY table_name;
~~~

Expect SECUREFILE = NO for the BasicFiles table and YES for the SecureFiles table.

### 17.4. Write BLOB Content with DBMS_LOB

~~~sql
DECLARE
    l_payload BLOB;
    l_bytes RAW(100) := UTL_RAW.CAST_TO_RAW('Sample binary payload');
BEGIN
    INSERT INTO lob_secure_lab(id, payload)
    VALUES (1, EMPTY_BLOB())
    RETURNING payload INTO l_payload;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_payload,
        amount  => UTL_RAW.LENGTH(l_bytes),
        buffer  => l_bytes
    );

    COMMIT;
END;
/
~~~

### 17.5. Read Length and Content

~~~sql
SELECT id, DBMS_LOB.GETLENGTH(payload) AS payload_bytes
FROM lob_secure_lab;
~~~

### 17.6. Compare Segment Sizes

~~~sql
SELECT segment_name,
       segment_type,
       bytes,
       blocks
FROM user_segments
WHERE segment_name IN (
    SELECT segment_name
    FROM user_lobs
    WHERE table_name IN ('LOB_BASIC_LAB', 'LOB_SECURE_LAB')
)
ORDER BY segment_name;
~~~

With a single small row, results may not show meaningful performance or size differences. Benchmarks require representative data volumes and realistic workloads.

### 17.7. Lab Cleanup

~~~sql
DROP TABLE lob_basic_lab PURGE;
DROP TABLE lob_secure_lab PURGE;
~~~

DDL performs an implicit commit. Run only after completing the practice exercise.

## 18. Common Errors

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-43853 | Creating SecureFiles in a tablespace that does not meet ASSM or prerequisites | Check SEGMENT_SPACE_MANAGEMENT and DB_SECUREFILE |
| ORA-43856 | Invalid or disallowed SecureFiles/BasicFiles configuration | Check DB_SECUREFILE, storage clause, and COMPATIBLE |
| ORA-22922 | LOB locator is no longer valid | Re-fetch the locator from the row in an appropriate transaction |
| ORA-22275 | Invalid or improperly initialized LOB locator | Check NULL/EMPTY locator and DBMS_LOB API usage |
| ORA-22288 | File operation error with BFILE | Check DIRECTORY, file existence, and OS permissions |
| ORA-01031 | Missing privileges on table, directory, or package | Grant appropriate least privileges |
| Abnormal temporary tablespace growth | Temporary LOBs not freed or processing too many large LOBs | Check LOB lifecycle and FREETEMPORARY |
| SecureFiles does not save space | Data is already compressed or has little duplication | Measure compression/dedup benefit before enabling |
| Slow LOB reads | Unsuitable CACHE/NOCACHE, storage I/O, or inefficient partial reads | Benchmark cache mode, streaming, and storage |
| MOVE LOB runs out of space | Space needed for target segment during the move | Provision tablespace space, inspect segments, and plan migration |
| Standby cannot recover NOLOGGING data | Redo-reducing operation without appropriate backup | Check FORCE LOGGING, backups, and Data Guard policy |
| Cannot read LOB after restore | Missing keystore or external BFILE content | Restore keystore and external files |

## 19. Checklist Before Choosing or Migrating LOB Storage

1. **What is the data type?** BLOB, CLOB, NCLOB, or BFILE.
2. **Is the LOB internal or external?** BFILE does not use SecureFiles/BasicFiles.
3. **What is the size distribution?** Mean, p95, p99, and maximum.
4. **What is the read/write pattern?** Full read, partial read, append, or random update.
5. **Are there many small LOBs?** Evaluate ENABLE STORAGE IN ROW.
6. **Are LOBs large and rarely read?** Evaluate DISABLE STORAGE IN ROW and NOCACHE.
7. **Does the tablespace use ASSM?** Required condition for SecureFiles.
8. **Is COMPATIBLE appropriate?** Do not change COMPATIBLE arbitrarily.
9. **Does DB_SECUREFILE allow it?** Check configuration before creation.
10. **Is compression needed?** Measure compression ratio and CPU overhead.
11. **Is there duplicate data?** Dedup only helps when duplicate content is significant.
12. **Is encryption needed?** Prepare TDE keystore, key backup, and licensing.
13. **Does LOGGING/NOLOGGING fit recovery?** Review backups, standby, and FORCE LOGGING.
14. **Are temporary LOBs freed?** Avoid growing the temporary tablespace.
15. **Is there a migration plan?** Evaluate MOVE LOB/DBMS_REDEFINITION, downtime, and rollback.
16. **Have you verified the data dictionary?** Confirm SECUREFILE, cache, logging, compression, dedup, and encryption.
17. **Have you benchmarked real data?** Measure throughput, latency, CPU, I/O, and storage.
18. **Do BFILEs have separate backups?** Database backups do not replace filesystem backups.

## 20. Self-Check Questions

**Question 1.** How do BLOB, CLOB, NCLOB, and BFILE differ?

**Question 2.** What is a LOB locator? Is it the LOB content itself?

**Question 3.** How do ENABLE STORAGE IN ROW and DISABLE STORAGE IN ROW differ?

**Question 4.** How do BasicFiles and SecureFiles differ in architecture and features?

**Question 5.** Why does SecureFiles require ASSM?

**Question 6.** What COMPATIBLE level is required to use SecureFiles?

**Question 7.** What role does DB_SECUREFILE play?

**Question 8.** Which mechanism are CHUNK and PCTVERSION tied to?

**Question 9.** What do SecureFiles compression and deduplication help with? What are their costs?

**Question 10.** How do CACHE, CACHE READS, and NOCACHE differ?

**Question 11.** Why should NOLOGGING be evaluated alongside backups and Data Guard?

**Question 12.** Are BFILEs backed up along with datafiles?

**Question 13.** How does EMPTY_CLOB differ from NULL?

**Question 14.** Why is FREETEMPORARY needed?

**Question 15.** How can BasicFiles be converted to SecureFiles?

**Question 16.** Why should compression/dedup/encryption not be enabled on every LOB column?

**Question 17.** How do you confirm a LOB column is actually SecureFiles?

**Question 18.** When should BasicFiles be kept in a legacy system?

<details>
<summary>Answer Hints</summary>

1. BLOB is bytes; CLOB is characters in the database character set; NCLOB is in the national character set; BFILE is a locator to a file outside the database.
2. A locator is a reference to access a LOB; it does not necessarily hold the entire content.
3. ENABLE allows small LOBs inline; DISABLE stores them outside the row.
4. SecureFiles is a newer architecture supporting compression, deduplication, encryption, and optimization for LOB workloads; BasicFiles is the traditional mechanism.
5. SecureFiles uses segment space management mechanisms that require ASSM.
6. COMPATIBLE 11.1.0 or higher.
7. Controls SecureFiles creation according to database configuration.
8. CHUNK and PCTVERSION are BasicFiles parameters; SecureFiles uses other mechanisms, including RETENTION.
9. Compression saves space if data is compressible; dedup avoids storing multiple identical copies; both can increase CPU usage and require appropriate licensing.
10. CACHE caches LOB data; CACHE READS caches on reads; NOCACHE does not cache LOB data in the usual path.
11. NOLOGGING can reduce redo and affect media recovery/standby; proper backups are required.
12. No. BFILEs reside on the filesystem outside the database and require separate backups.
13. EMPTY_CLOB is an empty LOB locator; NULL means no locator value.
14. To free temporary LOBs and avoid consuming temporary tablespace/session resources.
15. Use ALTER TABLE MOVE LOB to STORE AS SECUREFILE or an appropriate redefinition/copy strategy.
16. Because CPU, I/O, latency, licensing, and benefits depend on the data and workload.
17. Check USER_LOBS.SECUREFILE or ALL_LOBS/DBA_LOBS.
18. When compatibility constraints exist, the tablespace/architecture is not ready, or migration yields insufficient benefit.

</details>

## 21. Official Oracle Documentation

1. [Oracle Database SecureFiles and Large Objects Developer's Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/): LOB architecture, SecureFiles, BasicFiles, locators, and LOB operations.
2. [Oracle Database 19c SecureFiles and Large Objects Developer's Guide — SecureFiles](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/using-oracle-securefiles.html): prerequisites, features, and creating SecureFiles.
3. [Oracle Database 19c SecureFiles and Large Objects Developer's Guide — BasicFiles](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/basicfiles.html): BasicFiles architecture and parameters.
4. [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): LOB storage clauses and SecureFiles options.
5. [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): MOVE LOB and changing LOB storage.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html): reading, writing, comparing, temporary LOB, and BFILE APIs.
7. [Oracle Database 19c Reference — USER_LOBS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_LOBS.html): metadata of LOB columns in the current schema.
8. [Oracle Database 19c Reference — DB_SECUREFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DB_SECUREFILE.html): parameter controlling SecureFiles.
9. [Oracle Database 19c Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): check licensing requirements for compression, deduplication, and encryption.

**Principle to remember:** SecureFiles should be the first option evaluated for internal LOBs in modern Oracle systems, provided COMPATIBLE and ASSM requirements are met and DB_SECUREFILE is checked. BasicFiles may still exist for legacy compatibility. Choose CACHE, in-row storage, compression, deduplication, encryption, and logging based on data sizes, read/write patterns, security requirements, licensing, and recovery. BFILEs are files outside the database; temporary LOBs require cleanup; any storage migration must include benchmarking, spare space, backups, and a rollback plan.
