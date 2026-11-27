# LOB Compression, Deduplication, and Encryption in Oracle

## 1. Overview of LOBs and SecureFiles

Oracle uses LOB data types to store large content:

- `CLOB`: character data in the database character set.
- `NCLOB`: character data in the national character set.
- `BLOB`: binary data.
- `BFILE`: a locator referencing a file outside the database; file content is not stored in a LOB segment and BFILE is read-only.

For CLOB, NCLOB, and BLOB, Oracle stores content via internal LOB mechanisms. A small LOB can be stored inline in the row if configuration allows; large LOBs are usually stored in a separate LOB segment. Applications access content through a LOB locator or APIs such as `DBMS_LOB`.

As large data grows, LOB segment size, I/O, backups, redo, and transfer time can become bottlenecks. Oracle SecureFiles provides three key features:

- **Compression:** compresses LOB content to reduce storage usage.
- **Deduplication:** avoids storing multiple physical copies of identical LOB content within supported scope.
- **Encryption:** encrypts LOB content to protect data at rest.

These features can reduce storage or increase security, but come with prerequisites, CPU cost, performance impact, and separate licensing requirements. Do not enable them across the board without understanding the data and workload.

This lesson belongs to the **LOBs and Large Data** chapter and covers SecureFiles and BasicFiles, tablespace prerequisites, compression levels, deduplication, TDE encryption, combining features, syntax for creating and modifying LOBs, migrating existing data, inspecting metadata, measuring effectiveness, and licensing/feature conditions to verify.

## 2. BasicFiles and SecureFiles

Oracle has two common internal LOB storage architectures:

| Feature | BasicFiles | SecureFiles |
|---|---|---|
| Technology | Traditional LOB | Modern LOB mechanism |
| LOB Compression | No SecureFiles compression | Yes |
| Deduplication | No SecureFiles deduplication | Yes |
| LOB Encryption | No SecureFiles LOB encryption | Yes, via TDE |
| Tablespace | Per BasicFiles rules | Requires ASSM |
| New deployments | Only when compatibility requires | Typically the option to evaluate |

SecureFiles was introduced in Oracle Database 11g. Detailed features and syntax depend on version, edition, and database configuration.

### 2.1. Why SecureFiles Is Required

Compression, deduplication, and encryption are provided as attributes of SecureFiles LOBs. If a LOB column currently uses BasicFiles, adding `COMPRESS`, `DEDUPLICATE`, or `ENCRYPT` does not automatically convert it to SecureFiles.

When these features are needed, ensure the LOB column is stored as SecureFiles and the tablespace meets prerequisites. If existing data is in BasicFiles, plan to migrate or reorganize the LOB.

### 2.2. Checking LOB Type

```sql
SELECT table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile,
       compression,
       deduplication,
       encrypt
FROM user_lobs
ORDER BY table_name, column_name;
```

The `SECUREFILE`, `COMPRESSION`, `DEDUPLICATION`, and `ENCRYPT` columns indicate storage type and LOB attributes in the current schema. Use `ALL_LOBS` or `DBA_LOBS` when inspecting other schemas with appropriate privileges.

## 3. Prerequisites for Using SecureFiles

### 3.1. Tablespace Must Use ASSM

SecureFiles LOBs require a tablespace using **Automatic Segment Space Management (ASSM)**.

```sql
SELECT tablespace_name,
       segment_space_management,
       extent_management,
       status
FROM user_tablespaces
ORDER BY tablespace_name;
```

Or, with DBA privileges:

```sql
SELECT tablespace_name,
       segment_space_management
FROM dba_tablespaces
ORDER BY tablespace_name;
```

The value required in `SEGMENT_SPACE_MANAGEMENT` is `AUTO`.

Example creating a lab tablespace:

```sql
CREATE TABLESPACE lob_lab_ts
DATAFILE 'lob_lab_ts01.dbf' SIZE 500M
EXTENT MANAGEMENT LOCAL
SEGMENT SPACE MANAGEMENT AUTO;
```

The datafile path and size must fit your environment. This is illustrative syntax only; do not run verbatim without confirming storage location and quota.

### 3.2. The DB_SECUREFILE Parameter

The `DB_SECUREFILE` initialization parameter controls SecureFiles LOB creation behavior. Exact values and semantics should be checked for your Oracle version.

```sql
SHOW PARAMETER db_securefile;
```

Or:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_securefile';
```

Common values include:

- `PERMITTED`: allows creating SecureFiles when explicitly requested in DDL.
- `ALWAYS`: directs Oracle to prefer creating SecureFiles according to the parameter's rules.
- `NEVER`: disallows creating SecureFiles.
- Some versions also have other control values such as `FORCE` or `IGNORE`.

Do not change this parameter on production on your own. It is a database-level setting that can affect multiple schemas; changes require administrative privileges and operational change control.

### 3.3. Version Compatibility

SecureFiles has existed since Oracle Database 11g, though compression levels, algorithms, syntax, partition support, and administration capabilities can vary across versions.

Before deploying, verify:
- Release version and Release Update.
- Value of `COMPATIBLE`.
- Edition and licensed options.
- Tablespace uses ASSM.
- `DB_SECUREFILE` permits SecureFiles.
- Backup, Data Pump, replication, and standby support the desired configuration.

### 3.4. Licensing Requirements

Having SQL syntax or being able to create the LOB does not mean an organization is licensed to use every option.

Under Oracle's standard licensing model:

| SecureFiles Feature | Option Typically Requiring Verification |
|---|---|
| SecureFiles compression | Oracle Advanced Compression Option |
| SecureFiles deduplication | Oracle Advanced Compression Option |
| SecureFiles encryption | Oracle Advanced Security Option |
| Basic SecureFiles without the options above | Check edition and current licensing terms |

Licensing terms can vary by version, edition, cloud service, and contract. Always verify the Oracle Database Licensing Information User Manual for your exact release and your organization's agreements before enabling features. A DBA or license administrator must confirm entitlements; never infer licensing from DDL succeeding.

## 4. SecureFiles LOB Compression

Compression compresses LOB data to reduce space usage. It is often helpful for text, XML, JSON, logs, and content with repetitive structures.

### 4.1. Compression Levels

SecureFiles supports `LOW`, `MEDIUM`, and `HIGH` levels in supporting releases:

| Level | General Characteristics | When to Consider |
|---|---|---|
| `LOW` | Prioritizes speed, typically lower compression ratio | CPU-sensitive or frequently accessed workloads |
| `MEDIUM` | Balances compression ratio and CPU | Starting point for benchmarking |
| `HIGH` | Prioritizes space savings, typically higher CPU usage | Long-term archived data, rarely updated |

Actual compression ratios depend on content. There is no fixed percentage across all CLOBs/BLOBs.

### 4.2. Which Data Compresses Well?

Typically compresses well:
- Plain text, XML, JSON.
- Content with many repeated strings.
- Documents with repetitive structure and metadata.

Typically compresses poorly:
- JPEG, PNG, MP4, and already compressed media.
- ZIP, GZIP, and compressed archives.
- Data already encrypted before insertion into the LOB.
- High-entropy binary data.

If the application already compresses files before storing them in a BLOB, adding SecureFiles compression may save very little while still consuming CPU.

### 4.3. Creating SecureFiles with Compression

```sql
CREATE TABLE documents (
    document_id NUMBER PRIMARY KEY,
    document_name VARCHAR2(200),
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
);
```

`STORE AS SECUREFILE` instructs Oracle to store the LOB using SecureFiles. `COMPRESS MEDIUM` enables MEDIUM compression.

Example using LOW:

```sql
CREATE TABLE text_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS LOW
);
```

Or HIGH:

```sql
CREATE TABLE archive_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS HIGH
);
```

### 4.4. Performance Trade-offs

Compression can reduce the number of blocks stored and read, at the cost of CPU for compression and decompression. For frequently updated workloads, large LOBs, or strict latency requirements, higher compression levels can raise CPU and latency.

Measure:
- LOB size before and after.
- CPU during INSERT, UPDATE, and SELECT.
- Elapsed time for full-LOB reads and partial reads.
- Update-to-read ratio.
- Database CPU contention.

## 5. SecureFiles LOB Deduplication

Deduplication avoids storing multiple copies of identical LOB content within the supported LOB segment scope. When multiple rows store the same content, Oracle can share the LOB data portion instead of storing separate physical copies.

For example, a document management system where many records attach the same PDF template. If the BLOB bytes are completely identical, deduplication can reduce storage substantially.

### 5.1. Deduplication Differs from Compression

| Feature | Compression | Deduplication |
|---|---|---|
| How space is saved | Compresses data representation | Avoids storing multiple copies of identical content |
| Effectiveness depends on | Compressibility of each payload | Duplicate LOB ratio |
| Suitable data | Text and repetitively structured data | Identical files/documents |
| Cost | Compression/decompression CPU | CPU and metadata to detect/manage shared copies |

Files with different names but identical content bytes are deduplication candidates. Two documents that are mostly similar except for a few differing bytes will not necessarily deduplicate into a single copy.

### 5.2. DEDUPLICATE Syntax

```sql
CREATE TABLE shared_documents (
    document_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    DEDUPLICATE
);
```

`DEDUPLICATE` enables deduplication for the LOB segment.

It can be combined with compression:

```sql
CREATE TABLE shared_text_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
);
```

Combination support and conditions should be verified against your target Oracle release.

### 5.3. KEEP_DUPLICATES

If you want to keep separate physical copies for each LOB:

```sql
CREATE TABLE private_documents (
    document_id NUMBER PRIMARY KEY,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    KEEP_DUPLICATES
);
```

`KEEP_DUPLICATES` disables deduplication for the LOB segment. It fits when content has few duplicates or when deduplication overhead offers little benefit.

### 5.4. Deduplication Is Not Backup or Versioning

Deduplication does not create backup copies and does not retain document version history. It is purely a storage optimization. If the application needs versioning, auditing, or restoring prior versions, design separate data structures.

### 5.5. When Does Deduplication Pay Off?

Suitable when:
- Many rows contain the same file or identical content.
- Data rarely changes after being written.
- Duplicate ratio is high.
- Storage savings outweigh CPU/metadata cost.
- There is sufficient opportunity to share content within the same LOB segment.

May not be worthwhile when:
- Nearly every LOB is unique.
- Files are individually encrypted before storage, making byte contents differ.
- Data is frequently modified.
- Datasets are small and storage is not a concern.

## 6. SecureFiles LOB Encryption

Encryption protects LOB content at rest. SecureFiles encryption uses Transparent Data Encryption (TDE), where Oracle encrypts and decrypts data transparently during writes and reads; applications typically continue operating via SQL or DBMS_LOB as before.

### 6.1. Encryption at Rest

The primary goal is protecting data while stored on disk, datafiles, or storage media.

TDE does not replace all other security layers:
- It does not replace TLS/Oracle Native Network Encryption for protecting data in transit.
- It does not replace SELECT/UPDATE privileges and access controls.
- It does not stop authorized database users from reading data via SQL.
- It does not eliminate the need to protect wallets/keystores and backups.
- It does not replace auditing and identity management.

### 6.2. ENCRYPT Syntax

```sql
CREATE TABLE confidential_documents (
    document_id NUMBER PRIMARY KEY,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    ENCRYPT USING 'AES256'
);
```

`ENCRYPT` enables LOB encryption. `USING 'AES256'` selects the 256-bit AES algorithm in supporting versions. Default algorithms and supported algorithm sets depend on release/configuration; consult the documentation for your version.

You can use `ENCRYPT` without specifying an algorithm if database policy permits the default:

```sql
LOB (document_content) STORE AS SECUREFILE (
    ENCRYPT
);
```

### 6.3. TDE Keystore Prerequisites

TDE requires a configured keystore/wallet and properly managed encryption keys. Before creating or accessing encrypted LOBs, the DBA must confirm:
- TDE is configured according to the database architecture.
- The keystore has been created and opened per policy.
- The master encryption key has been set.
- Backup and recovery procedures include the keystore.
- Key access and operational duties are appropriately separated.

Keystore administration commands vary by version and security policy. Never embed wallet passwords in shared scripts, source control, or training materials.

### 6.4. Changing Algorithm or Disabling Encryption

You can change SecureFiles LOB attributes with `ALTER TABLE ... MODIFY LOB` per version syntax and capabilities. Example:

```sql
ALTER TABLE confidential_documents
MODIFY LOB (document_content)
(
    ENCRYPT USING 'AES256'
);
```

Disabling encryption:

```sql
ALTER TABLE confidential_documents
MODIFY LOB (document_content)
(
    DECRYPT
);
```

Consult Oracle documentation for your exact release, keystore state, privileges, and data migration requirements before running on large LOBs. Some changes may require reorganizing or rewriting existing data; do not assume a metadata change always converts all existing data instantaneously.

## 7. Combining Compression, Deduplication, and Encryption

SecureFiles allows designing LOBs with multiple storage attributes, though compatibility, licensing, and actual impact of each combination must be verified.

Example:

```sql
CREATE TABLE protected_shared_documents (
    document_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Meaning:
- `COMPRESS MEDIUM`: compresses LOB data at medium level.
- `DEDUPLICATE`: avoids storing multiple physical copies of identical content within supported scope.
- `ENCRYPT USING 'AES256'`: encrypts the LOB using the configured AES256 algorithm.

Combined syntax must be tested on the target version, edition, and configuration before deployment. Each feature still carries its own licensing requirements.

### 7.1. Conceptual Processing Order

Compression shrinks the data representation; deduplication detects duplicate content; encryption turns data into ciphertext. Ciphertext has high entropy and typically compresses poorly if you try to compress after encrypting. Oracle manages the internal SecureFiles pipeline; do not encrypt files yourself in the application with different keys/nonces and expect the database to still deduplicate them.

### 7.2. When to Combine?

| Data Characteristics | Compression | Deduplication | Encryption |
|---|---|---|---|
| Text documents repeated many times | Likely helpful | Likely helpful | Per security requirements |
| Identical PDFs stored for many customers | Depends on PDF compressibility | Likely helpful | Per data classification |
| JPEG images or compressed video | Usually minimal savings | Helpful if files are exact duplicates | Per security requirements |
| Identical ZIP files | Usually minimal savings | Likely helpful | Per security requirements |
| Files already encrypted individually in app | Usually minimal savings | Usually hard to dedup if ciphertext differs | Review encryption architecture |
| Unique, frequently updated data | Measure CPU and latency | Likely not worth it | Per security requirements |

### 7.3. Encryption Does Not Replace Authorization

If a user holds SELECT privileges on the LOB, TDE transparently decrypts inside the database so the authorized user can read the data. TDE primarily protects data at rest; it is not a mechanism to hide data from every user who has query privileges.

If partial masking per user or role is needed, consider object privileges, VPD, Data Redaction, or application-layer encryption depending on requirements. Each solution has distinct goals and limitations.

## 8. Creating a SecureFiles LOB Table with Explicit Attributes

Example record management table:

```sql
CREATE TABLE customer_files (
    file_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    file_name VARCHAR2(255) NOT NULL,
    file_content BLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
)
LOB (file_content) STORE AS SECUREFILE customer_files_lob (
    TABLESPACE lob_lab_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    CACHE READS
    LOGGING
    COMPRESS MEDIUM
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Explanation:
- `STORE AS SECUREFILE`: selects SecureFiles.
- `TABLESPACE`: LOB segment location.
- `ENABLE STORAGE IN ROW`: allows small LOBs to be stored in-row if eligible.
- `CHUNK`: LOB allocation/read/write unit per storage rules.
- `CACHE READS`: caches read operations per Oracle semantics.
- `LOGGING`: writes redo per logging configuration.
- `COMPRESS MEDIUM`: enables compression.
- `DEDUPLICATE`: enables deduplication.
- `ENCRYPT USING 'AES256'`: enables encryption.

Attributes like `CACHE`, `CHUNK`, `LOGGING`, and storage in-row affect I/O and storage; they are not prerequisites for enabling the three features covered here. Choose them based on workload rather than copying the example verbatim.

### 8.1. Note on BFILE

`BFILE` is a locator to an external file outside the database, not LOB content stored in a LOB segment. SecureFiles compression, deduplication, and encryption do not apply to external files through BFILE the way they apply to internal CLOB/BLOBs.

If the database must manage LOB security and storage, consider internal BLOB/CLOB. If using BFILE, manage filesystem permissions, directory objects, and external file lifecycles separately.

## 9. Modifying Existing LOB Attributes

For an existing SecureFiles LOB, you can use `ALTER TABLE ... MODIFY LOB` to alter certain attributes depending on version capabilities.

Enable compression:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    COMPRESS MEDIUM
);
```

Change compression level:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    COMPRESS HIGH
);
```

Disable compression:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    NOCOMPRESS
);
```

Enable deduplication:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    DEDUPLICATE
);
```

Keep individual copies:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    KEEP_DUPLICATES
);
```

Enable encryption:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    ENCRYPT USING 'AES256'
);
```

Disable encryption:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    DECRYPT
);
```

These commands illustrate attribute syntax. Before running in production, check the documentation for your exact release to confirm whether a change applies only to newly written LOBs, updates metadata, or requires moving/rewriting existing data. For large datasets, estimate duration, temporary space, redo, undo, locks, and maintenance windows.

## 10. Migrating BasicFiles to SecureFiles

If a LOB column currently uses BasicFiles, migrate storage to SecureFiles before using SecureFiles compression, deduplication, or encryption.

### 10.1. Checking Current Status

```sql
SELECT table_name,
       column_name,
       segment_name,
       securefile,
       compression,
       deduplication,
       encrypt
FROM user_lobs
WHERE table_name = 'LEGACY_DOCUMENTS';
```

If `SECUREFILE` is `NO`, the LOB is using BasicFiles.

### 10.2. MOVE LOB

Illustrative syntax:

```sql
ALTER TABLE legacy_documents
MOVE LOB (document_content)
STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
);
```

A MOVE operation can rebuild the LOB segment and migrate content. Evaluate:
- Migration duration based on size.
- Free space for the new segment.
- Locking and availability during the move.
- Affected indexes, constraints, triggers, and dependencies.
- Backups before and after migration.
- Impact on replication, standby, and recovery procedures.

### 10.3. Online Redefinition

For large tables needing minimal disruption, evaluate `DBMS_REDEFINITION` for online redefinition if the table and structure meet prerequisites. This process is more complex than MOVE and requires DBA planning to verify dependencies, space, and DML synchronization during redefinition.

Never run MOVE or online redefinition on production just to test features. Test on a clone or staging environment first.

## 11. Inspecting Metadata and Configuration

### 11.1. USER_LOBS

```sql
SELECT table_name,
       column_name,
       tablespace_name,
       segment_name,
       securefile,
       compression,
       deduplication,
       encrypt,
       in_row,
       cache
FROM user_lobs
ORDER BY table_name, column_name;
```

This view confirms LOB attributes in the current schema.

### 11.2. DB_SECUREFILE

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_securefile';
```

Requires privileges on `V$PARAMETER`. You can also run `SHOW PARAMETER` in SQL*Plus/SQLcl.

### 11.3. Tablespace ASSM

```sql
SELECT tablespace_name,
       segment_space_management
FROM user_tablespaces
ORDER BY tablespace_name;
```

SecureFiles requires an ASSM tablespace. If a tablespace does not qualify, create or select another suitable tablespace.

### 11.4. TDE Keystore Status

DBAs can check keystore-related views, for example:

```sql
SELECT wallet_type,
       status,
       wallet_order
FROM v$encryption_wallet;
```

Columns and privileges depend on version. Keystore details are security-sensitive data; only personnel responsible for TDE administration should query and share results appropriately.

### 11.5. Segment Size

```sql
SELECT s.segment_name,
       s.bytes,
       s.blocks
FROM user_segments s
JOIN user_lobs l
  ON l.segment_name = s.segment_name
WHERE l.table_name = 'CUSTOMER_FILES';
```

Segment size is a useful metric, though it does not by itself tell you logical LOB size or the exact deduplication ratio. Measure both content byte totals and allocated storage.

## 12. Measuring Compression and Deduplication Effectiveness

Do not enable a feature and look at just one storage figure. Compare before and after on a representative dataset.

### 12.1. Logical LOB Size

For BLOB:

```sql
SELECT SUM(DBMS_LOB.GETLENGTH(file_content)) AS logical_bytes,
       COUNT(file_content) AS lob_count
FROM customer_files;
```

For CLOB, `DBMS_LOB.GETLENGTH` returns character units per LOB semantics, not storage bytes. Do not compare CLOB length directly against `USER_SEGMENTS.BYTES` as if they shared the same unit.

### 12.2. Segment Size

```sql
SELECT s.segment_name,
       s.bytes,
       s.blocks
FROM user_segments s
JOIN user_lobs l
  ON l.segment_name = s.segment_name
WHERE l.table_name = 'CUSTOMER_FILES';
```

Some LOB structures may also involve a LOB index or auxiliary segments. Identify the exact segments to include and avoid double-counting.

### 12.3. Savings Ratio

\[
\text{Storage saving} =
\frac{\text{Before bytes} - \text{After bytes}}
{\text{Before bytes}} \times 100\%
\]

Example: 100 GB before, 65 GB after, 35% savings. This is an illustrative number, not a guaranteed SecureFiles ratio.

### 12.4. Measuring Deduplication with Real Data

If a table has many copies of identical content, compare:
- Total logical size of all LOBs.
- Actual segment size.
- Number of LOBs.
- Number of duplicate content groups in source data if identifiable.
- CPU and INSERT/UPDATE elapsed time.

Do not infer deduplication ratio from row counts alone. Two rows with the same filename do not guarantee identical bytes; two rows with different filenames can have byte-for-byte identical content.

### 12.5. Measuring Read and Write Workloads

| Metric | Purpose |
|---|---|
| INSERT elapsed time | Measures LOB write cost |
| UPDATE LOB elapsed time | Measures content modification cost |
| SELECT/read latency | Measures decompression/decryption and read cost |
| CPU time | Evaluates compression/encryption overhead |
| Physical reads | Evaluates storage I/O |
| Segment bytes | Evaluates actual allocated space |
| Redo size | Evaluates logging/recovery cost |
| PGA/SGA | Monitors memory resources |
| Concurrent throughput | Checks impact under concurrent session operations |

## 13. Performance Impact

### 13.1. Compression

Benefits:
- Reduces LOB storage space.
- May reduce I/O when reading data from storage.
- May reduce backup or data-transfer overhead in some workflows.

Costs:
- Compression CPU on writes.
- Decompression CPU on reads.
- Can increase latency for CPU-bound workloads.
- Frequently updated LOBs can incur substantial repeated recompression cost.

### 13.2. Deduplication

Benefits:
- Saves storage when many LOBs are identical.
- Avoids storing multiple physical copies of the same content within supported scope.

Costs:
- Detecting duplicate content consumes resources.
- Metadata and reference management add complexity.
- Heavy update workloads can erode benefits.
- Mostly unique content yields little savings.

### 13.3. Encryption

Benefits:
- Protects LOB data at rest.
- Supports security and compliance requirements.

Costs:
- CPU for encryption/decryption.
- Key management, keystore, and backup administration.
- More complex operational and recovery procedures.
- Can affect throughput/latency depending on workload and hardware.

### 13.4. Benchmarking Configurations

Compare on the same dataset:
1. SecureFiles with no options enabled.
2. Compression.
3. Deduplication.
4. Compression + deduplication.
5. Encryption.
6. Combined configuration meeting licensing and security requirements.

Choose based on measurements and business requirements. Never assume combining more options is always better.

## 14. Caching, Logging, and Other LOB Attributes

Compression, deduplication, and encryption are not the only SecureFiles attributes.

### 14.1. CACHE, NOCACHE, and CACHE READS

- `CACHE`: LOB data can be placed in the buffer cache per Oracle semantics.
- `NOCACHE`: limits buffer caching of LOB data per configuration.
- `CACHE READS`: caches on reads without applying the same CACHE behavior to all operations.

Choose based on LOB size and access frequency. Caching a very large LOB set can pressure the buffer cache; `NOCACHE` can suit large, rarely accessed, or streamed LOBs.

### 14.2. LOGGING and NOLOGGING

Logging affects redo and recoverability. Never pick `NOLOGGING` merely to speed up LOB writes without evaluating backup/recovery, Data Guard, and data protection requirements.

Compression/encryption do not replace redo logging or backups. Verify exact attribute semantics for your version and specific operations.

### 14.3. ENABLE/DISABLE STORAGE IN ROW

`ENABLE STORAGE IN ROW` lets small LOBs be stored in the row if eligible; `DISABLE STORAGE IN ROW` stores them out-of-row. This attribute affects layout and I/O, not compression or encryption.

## 15. Limitations and Operational Considerations

### 15.1. Already Compressed Files

Enabling compression on BLOBs holding ZIP, JPEG, MP4, or archive files may yield negligible additional space savings. Inspect file formats and test on samples first.

### 15.2. Application-Encrypted Files

If the application encrypts each file with a distinct IV/nonce before writing, ciphertexts will differ even when plaintexts are identical. This generally renders deduplication ineffective. Consider the encryption boundary: TDE at the database vs. application-layer encryption, depending on threat model and access requirements.

### 15.3. Deduplication Does Not Replace Content Management

Deduplication does not manage filenames, versions, sharing permissions, retention, or change history. Applications still require dedicated metadata and document policies.

### 15.4. Encryption Does Not Protect Data After an Authorized User Reads It

A user granted read access to the LOB through the database receives content decrypted by Oracle. Combine TDE with object privileges, roles, auditing, account controls, and network protection.

### 15.5. Backups and Recovery Must Include the Keystore

With TDE, backing up datafiles without the corresponding keystore/master key may not be sufficient to restore and read the data. Backup, restore, cloning, standby, and disaster recovery procedures must protect keys according to organizational policy.

### 15.6. Changing Attributes Can Take Time and Space

For large LOB segments, changing storage attributes can generate I/O, redo, and temporary space demand. Plan maintenance windows, check space, back up, and verify rollback/recovery capability.

### 15.7. Do Not Run Experimental DDL on Production

DDL can trigger implicit commits and alter structures immediately. Use a lab schema or data clone before testing `MOVE LOB`, changing encryption, or migrating BasicFiles to SecureFiles.

## 16. Design Examples by Scenario

### 16.1. Text Document Repository with Repetitive Content

Characteristics:
- Many CLOBs containing XML/JSON or text.
- Repetitive content patterns.
- Rarely updated after creation.

You can test:

```sql
CREATE TABLE text_archive (
    archive_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    body CLOB
)
LOB (body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
);
```

Measure compression ratio, duplicate ratio, and CPU. Confirm Advanced Compression licensing before enabling these options.

### 16.2. Image and Video Repository

Characteristics:
- BLOBs holding JPEG, PNG, MP4.
- Most files are already compressed.
- Exact duplicate files may exist.

Compression will likely offer little savings. Deduplication can help if many users upload the same file. Encryption depends on security requirements.

```sql
CREATE TABLE media_store (
    media_id NUMBER PRIMARY KEY,
    media_type VARCHAR2(50),
    media_data BLOB
)
LOB (media_data) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Verify encryption and deduplication licenses separately.

### 16.3. Sensitive Records

Characteristics:
- BLOBs containing scanned contracts, dossiers, or documents with personal data.
- At-rest protection required.
- Potentially low duplication.

Encryption is the priority per security requirements. Only enable compression/deduplication if licensing and workload justify the benefit.

```sql
CREATE TABLE sensitive_records (
    record_id NUMBER PRIMARY KEY,
    record_document BLOB
)
LOB (record_document) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    ENCRYPT USING 'AES256'
);
```

Beyond TDE, apply least-privilege access, auditing, keystore backups, and network protection.

### 16.4. Multi-Tenant Shared Document System

If the same content is referenced across multiple tenants, deduplication can save storage, but tenant isolation policies must be evaluated. Never let storage design leak information about whether another tenant stored the same content. APIs and access controls must ensure each tenant sees only authorized data.

## 17. Pre-Deployment License and Prerequisite Checklist

Checklist to review with the DBA/license administrator:

1. Oracle Database version and Release Update.
2. Database edition and service in use.
3. SecureFiles permitted by `DB_SECUREFILE`.
4. Tablespace uses ASSM.
5. TDE keystore configured if using encryption.
6. Advanced Compression entitlement if using compression/deduplication.
7. Advanced Security entitlement if using SecureFiles encryption.
8. Standby, backup, and restore support confirmed.
9. Syntax and behavior tested in staging.
10. Storage, CPU, latency, and concurrency benchmarked.
11. Migration plan if existing LOBs are BasicFiles.
12. Rollback or recovery plan if the change fails.

Do not use `V$OPTION`, UI visibility, or successful DDL execution as sole proof of licensing. Cross-check the Licensing Information User Manual for your exact release and active contracts.

## 18. Comprehensive Practice Lab

Examples use dedicated tables in a lab schema. Requires CREATE TABLE privilege and a suitable tablespace; encryption requires TDE configured and matching licensing. Never run verbatim on production.

### Step 1. Check Parameters and Tablespaces

```sql
SHOW PARAMETER db_securefile;

SELECT tablespace_name,
       segment_space_management
FROM user_tablespaces
ORDER BY tablespace_name;
```

Confirm the target tablespace shows `AUTO`.

### Step 2. Create a SecureFiles Table Without Options

```sql
CREATE TABLE lab_lob_plain (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
);
```

### Step 3. Create a Table with Compression

```sql
CREATE TABLE lab_lob_compressed (
    id NUMBER PRIMARY KEY,
    content CLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
);
```

Run only once Advanced Compression entitlement is confirmed.

### Step 4. Create a Table with Deduplication

```sql
CREATE TABLE lab_lob_dedup (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    DEDUPLICATE
);
```

### Step 5. Create a Table with Encryption

```sql
CREATE TABLE lab_lob_encrypted (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    ENCRYPT USING 'AES256'
);
```

Run only when the TDE keystore is ready and Advanced Security entitlement is confirmed.

### Step 6. Create a Table Combining Features

```sql
CREATE TABLE lab_lob_all_features (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Verify syntax and option combinations for your version before running.

### Step 7. Inspect Metadata

```sql
SELECT table_name,
       column_name,
       segment_name,
       securefile,
       compression,
       deduplication,
       encrypt,
       tablespace_name
FROM user_lobs
WHERE table_name LIKE 'LAB_LOB%'
ORDER BY table_name;
```

### Step 8. Inspect Segment Sizes

```sql
SELECT segment_name,
       segment_type,
       bytes,
       blocks
FROM user_segments
WHERE segment_name IN (
    SELECT segment_name
    FROM user_lobs
    WHERE table_name LIKE 'LAB_LOB%'
)
ORDER BY segment_name;
```

### Step 9. Test Modifying Attributes

```sql
ALTER TABLE lab_lob_compressed
MODIFY LOB (content)
(
    COMPRESS HIGH
);
```

Execute only if the feature is licensed. Re-query `USER_LOBS` and verify impact on existing data for your release.

### Step 10. Clean Up Lab Tables

Only when certain these are tables you created and the data is no longer needed:

```sql
DROP TABLE lab_lob_plain PURGE;
DROP TABLE lab_lob_compressed PURGE;
DROP TABLE lab_lob_dedup PURGE;
DROP TABLE lab_lob_encrypted PURGE;
DROP TABLE lab_lob_all_features PURGE;
```

`DROP TABLE ... PURGE` drops the table and data, bypassing the recycle bin. DDL performs an implicit commit. Never run on business objects or shared data.

## 19. Common Misconceptions

| Misconception | Reality |
|---|---|
| BasicFiles supports SecureFiles compression | LOB compression/deduplication/encryption in this lesson require SecureFiles |
| Just writing COMPRESS works in any tablespace | SecureFiles requires ASSM and permissive database configuration |
| Compression always saves space | Already compressed or encrypted files compress very little |
| HIGH is always the best choice | HIGH can cost more CPU; benchmark first |
| Dedup merges nearly identical files | Deduplication targets identical content per SecureFiles semantics, not near-duplicate matching |
| Dedup replaces versioning | Dedup is a storage optimization, not version history |
| Same filename means duplicate content | Actual LOB contents must be identical |
| Encryption protects data from every database user | TDE protects at rest; users with query privileges can still read decrypted content |
| Encryption replaces TLS | TDE does not replace protecting data in transit |
| DDL succeeding means you are licensed | Entitlement must be confirmed against Licensing Information and contracts |
| Compression and dedup are free of cost | Both can increase CPU/metadata overhead and affect latency |
| BFILE can use SecureFiles options | BFILE references external files; SecureFiles LOB options apply to internal LOBs |
| ALTER metadata always converts all LOBs immediately | Behavior depends on the operation and version; MOVE/rewrite may be needed |
| TDE needs no key backups | Restoring encrypted data requires the corresponding keystore/master key |
| COMMIT in cleanup scripts is harmless | DDL performs an implicit commit; PURGE removes data from the recycle bin |

## 20. Quick Reference Rules

| Need | Choice |
|---|---|
| Store large CLOB/BLOB with modern LOB features | Evaluate SecureFiles |
| Enable SecureFiles | ASSM tablespace and permissive `DB_SECUREFILE` |
| Compress text/XML/JSON | Test `COMPRESS LOW`, `MEDIUM`, `HIGH` |
| Store many identical payloads | Evaluate `DEDUPLICATE` |
| Keep individual copies | `KEEP_DUPLICATES` |
| Protect LOBs at rest | SecureFiles `ENCRYPT` with TDE |
| Choose cipher | `ENCRYPT USING 'AES256'` if release supports and policy allows |
| Compression/dedup licensing | Confirm Advanced Compression Option |
| Encryption licensing | Confirm Advanced Security Option |
| Inspect attributes | `USER_LOBS`/`ALL_LOBS`/`DBA_LOBS` |
| Inspect tablespace | `SEGMENT_SPACE_MANAGEMENT = AUTO` |
| Inspect DB_SECUREFILE | `SHOW PARAMETER` or `V$PARAMETER` |
| Migrate BasicFiles | Plan MOVE LOB or online redefinition |
| Measure effectiveness | Compare segment bytes, logical bytes, CPU, latency, and redo |
| TDE recovery | Protect and back up keystore/master key |

## 21. Self-Check Questions

**Question 1.** How does SecureFiles differ from BasicFiles with respect to this lesson?

**Answer:** SecureFiles provides LOB compression, deduplication, and encryption; BasicFiles does not provide these SecureFiles options.

**Question 2.** What is the key tablespace prerequisite for SecureFiles?

**Answer:** The tablespace must use Automatic Segment Space Management, meaning `SEGMENT_SPACE_MANAGEMENT = AUTO`.

**Question 3.** What is DB_SECUREFILE used for?

**Answer:** A parameter controlling database behavior for creating SecureFiles LOBs; check its values for your release.

**Question 4.** How do compression LOW, MEDIUM, and HIGH differ?

**Answer:** They represent different trade-offs between processing speed and storage savings; benchmark on real data.

**Question 5.** Which data types typically compress poorly?

**Answer:** JPEG, MP4, ZIP, already compressed data, or encrypted ciphertext.

**Question 6.** What does deduplication do?

**Answer:** Avoids storing multiple physical copies of duplicate LOB content within SecureFiles' supported scope.

**Question 7.** Does deduplication replace versioning?

**Answer:** No. It only optimizes storage; it does not manage version history.

**Question 8.** What does KEEP_DUPLICATES mean?

**Answer:** Retains separate copies and disables deduplication for the LOB segment.

**Question 9.** Which technology does SecureFiles encryption use?

**Answer:** Transparent Data Encryption (TDE), with key management via a keystore/wallet.

**Question 10.** Does TDE replace TLS?

**Answer:** No. TDE protects data at rest; TLS or network encryption mechanisms protect data in transit.

**Question 11.** Which license do compression and deduplication typically require?

**Answer:** Oracle Advanced Compression Option under standard licensing; confirm for your exact release, edition, and contract.

**Question 12.** Which license does SecureFiles encryption typically require?

**Answer:** Oracle Advanced Security Option under standard licensing; check Licensing Information for your release and contract.

**Question 13.** Why can you not conclude you have a license simply because DDL succeeds?

**Answer:** Technical capability of the database is not proof of contractual usage entitlement.

**Question 14.** Does BFILE use these SecureFiles options?

**Answer:** Not in the way internal CLOB/BLOBs do; BFILE references files outside the database.

**Question 15.** How do you inspect LOB configuration?

**Answer:** Query USER_LOBS, ALL_LOBS, or DBA_LOBS and check SECUREFILE, COMPRESSION, DEDUPLICATION, and ENCRYPT columns.

**Question 16.** Why must the keystore be backed up when using TDE?

**Answer:** Encrypted data requires the matching master key to decrypt after restore or disaster recovery.

**Question 17.** Is HIGH compression always faster than MEDIUM?

**Answer:** No. HIGH may save more storage but consume more CPU and increase latency.

**Question 18.** When should MOVE LOB be used?

**Answer:** When moving/reorganizing a LOB segment, such as converting BasicFiles to SecureFiles or changing storage requiring data rewrite.

## 22. Conclusion

SecureFiles provides compression, deduplication, and encryption to manage large LOBs more effectively. Compression reduces space based on content compressibility; deduplication avoids storing multiple copies of duplicate LOBs; encryption protects data at rest via TDE. Features can be combined depending on release capabilities and configuration, but each choice carries its own CPU, storage, I/O, and operational costs.

Before enabling, verify that the LOB uses SecureFiles, the tablespace has ASSM, `DB_SECUREFILE` permits it, the TDE keystore is ready if encrypting, and the required licenses are in place. Compression/deduplication are typically tied to the Advanced Compression Option; SecureFiles encryption is typically tied to the Advanced Security Option. Always verify release-specific licensing documentation and contracts rather than inferring rights from successful DDL execution.

Select features based on actual content: text can compress well, pre-compressed media usually saves little, duplicate content suits dedup, and sensitive data needs encryption per the threat model. Use `USER_LOBS`, segment statistics, and benchmarks to compare space, CPU, latency, redo, and concurrency. For existing BasicFiles, plan MOVE LOB or online redefinition, verify backups/keystores, and validate in staging before deploying to production.

