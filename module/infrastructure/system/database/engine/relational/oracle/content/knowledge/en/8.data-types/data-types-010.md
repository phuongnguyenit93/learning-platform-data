# CLOB, NCLOB, BLOB, and BFILE

In Oracle Database, a `VARCHAR2` column fits names, codes, addresses, and most short strings. Yet systems often have to store **long article bodies**, **text records**, **images**, **PDFs**, **audio files**, or **documents already sitting on a server**. Those scenarios call for the **LOB (Large Object)** data type family.

The four common types are:

- **`CLOB` (Character Large Object):** large text data using the **database character set**.
- **`NCLOB` (National Character Large Object):** large text data using the **national character set**.
- **`BLOB` (Binary Large Object):** large binary data that Oracle does not interpret as characters.
- **`BFILE` (Binary File):** a **reference to a binary file stored outside the database**, on a filesystem accessible to the Oracle server; file contents are **read-only through the BFILE interface**.

What they share is the ability to represent large payloads and use a **LOB locator** to reference contents; what sets them apart governs encoding, storage, transactions, backups, permissions, and retrieval.

## 1. Choosing the Right LOB Type from Requirements

| Type | Stores What? | Character Set | Where Contents Live | Can Oracle Update Contents? | Typical Scenarios |
| --- | --- | --- | --- | --- | --- |
| **`CLOB`** | Long text | Database character set | **Inside database** (LOB storage) | **Yes**, under Oracle transactional mechanics | Articles, text XML, text JSON when not using a dedicated JSON type, text logs |
| **`NCLOB`** | Long text | National character set | **Inside database** | **Yes**, under Oracle transactional mechanics | Text data explicitly requiring the national character set |
| **`BLOB`** | Byte sequences | No character set semantics | **Inside database** | **Yes**, under Oracle transactional mechanics | PDFs, PNG/JPEG images, ZIP archives, Office documents, encrypted byte payloads |
| **`BFILE`** | Locator referencing an external binary file | No character set semantics | **Outside database**, in an OS file | **Cannot modify file contents via BFILE**; can update the locator value | Files already placed on server storage that Oracle needs to read via a server path |

Concise selection rule:

```text
Is the data text?
   |
   +-- Yes --> Dedicated national character set required?
   |             |
   |             +-- Yes ----------------------> NCLOB
   |             |
   |             +-- No -----------------------> CLOB
   |
   +-- No ---> Should Oracle manage file contents
                 inside database/transactions/backups?
                    |
                    +-- Yes -------------------> BLOB
                    |
                    +-- No, file stays external --> BFILE
                        (only when strictly read-only
                         and accessible to the Oracle server)
```

**Do not choose `NCLOB` just because the content has Vietnamese.** If the database uses a Unicode character set such as `AL32UTF8`, `CLOB` already stores Unicode text. `NCLOB` is useful when data specifically requires the separate **national character set**, not as a "mandatory Unicode version" of `CLOB`.

**Do not choose `BFILE` just because a file is large.** With `BFILE`, Oracle only manages a pointer; the file itself does not participate in rollback/commit and is not included in Oracle database backups the way a `BLOB` stored inside the database is.

## 2. How Do LOBs Differ from `VARCHAR2`, `RAW`, and `LONG`?

Small string and binary types have value-size limits that depend on SQL/PLSQL context and Oracle configuration:

| Type | Used For | Key Boundaries |
| --- | --- | --- |
| `VARCHAR2` / `NVARCHAR2` | Short and medium strings | Bounded in SQL by `MAX_STRING_SIZE` and byte/char semantics; cannot replace LOBs for very large documents |
| `RAW` | Short byte payloads | Has SQL length limits; not for large images/PDFs |
| `LONG` / `LONG RAW` | Legacy types | Severely restricted in SQL/DDL operations; prefer `CLOB`/`BLOB` for new designs |
| `CLOB` / `NCLOB` | Very long text | Requires attention to character sets, LOB locators, LOB APIs/methods, and client limits |
| `BLOB` | Very large byte payloads | Requires binary read/write APIs; never apply string functions arbitrarily |
| `BFILE` | Reference to an external server file | File must exist with OS/directory read permissions; contents are outside Oracle transactions |

Under the common SQL setting `MAX_STRING_SIZE = STANDARD`, `VARCHAR2` has a SQL maximum of **4,000 bytes**; `EXTENDED` mode allows certain string/`RAW` types up to **32,767 bytes** subject to corresponding conditions and constraints. `VARCHAR2` in PL/SQL also caps at **32,767 bytes**. Those are limits for small string types/variables; LOBs are built for much larger payloads, with specific limits depending on release, block size, and storage configuration.

Do not convert every `VARCHAR2` column to `CLOB` by reflex. A `VARCHAR2(20)` customer code is far easier to length-check, constrain, and B-tree index than a LOB column; LOBs carry their own locator, storage, access, and maintenance overhead.

## 3. LOB Locators and Actual Contents Are Not the Same Thing

A LOB column stores information allowing Oracle to **locate the LOB contents**. In SQL/PLSQL/JDBC, you typically receive or pass a **LOB locator** (or use a streaming API), rather than pulling every byte of a multi-GB file into an application string variable by default.

```text
             ROW IN APPLICATION TABLE
   +------------------------------------------------+
   | DOCUMENT_ID | TITLE | CONTENT (LOB locator)    |
   +------------------------------------------------+
                            |
                            v
                   CLOB/BLOB/NCLOB data
                 managed by Oracle Database
                 (in-row or out-of-row
                  depending on size/configuration)

   For BFILE:
   +------------------------------------------------+
   | DOCUMENT_ID | EXTERNAL_FILE (BFILE locator)    |
   +------------------------------------------------+
                            |
                            v
             DIRECTORY object + OS filename
                            |
                            v
             File on DB server filesystem
             (outside database, read-only contents)
```

### 3.1. Internal LOBs vs. External LOBs

`CLOB`, `NCLOB`, and `BLOB` are **internal LOBs**: Oracle manages the LOB data inside the database. Changes are recorded by transaction/recovery mechanisms corresponding to the features and storage options in use.

`BFILE` is an **external LOB**: the column holds only a locator pointing to a **DIRECTORY object** and filename; the real data lives on the OS. Oracle manages updates to the **locator value** in the row, yet cannot control or roll back file content modifications made by external programs.

| Action | Internal `BLOB` / `CLOB` / `NCLOB` | External `BFILE` |
| --- | --- | --- |
| `INSERT` locator/value into row | Yes | Yes, stores file reference |
| Read contents via LOB API | Yes | Yes, if server can read the file |
| Modify contents via `DBMS_LOB` | Yes, using supported operations | **No**, BFILE contents are read-only |
| `COMMIT`/`ROLLBACK` controls contents | Yes, via Oracle transaction mechanisms | Does not control byte changes in the OS file |
| Database RMAN backup preserves contents | Yes, as database data within backup scope | Does not automatically back up OS files pointed to by BFILE |
| Permissions to watch | Table/LOB privileges and database policies | Additional `DIRECTORY` privileges and OS file read permissions |

### 3.2. In-Row and Out-of-Row Are Not Two Data Types

For internal LOBs, Oracle can store small LOB values **inside the row** or store the contents in a separate **LOB segment** while the row keeps the locator and metadata. This depends on size, storage attributes, release, and Oracle storage capabilities.

```text
Small internal LOB case:
  Table data block
    -> row and potentially LOB data stored in-row

Large internal LOB case:
  Table data block
    -> row + locator
                  |
                  +--> LOB segment holding large contents
                       (and internal metadata/index depending on type)
```

Do not assume a rigid rule like "values under X bytes are always in-row": overhead, LOB type, `ENABLE/DISABLE STORAGE IN ROW`, SecureFiles/BasicFiles, and block limits can vary the behavior. Accessing out-of-row LOBs can require additional I/O and appropriate reading/streaming patterns.

## 4. `CLOB`: Storing and Processing Long Text

**`CLOB` uses the database character set**. On a database configured with `AL32UTF8`, it is usually the natural choice for documents, article bodies, and large Unicode strings in modern applications.

Examples well suited for CLOB:

- Technical guides of several hundred KB.
- Contract text or transcripts containing multiple languages.
- Textual JSON payloads when the design does not yet use a native JSON type or dedicated JSON constraint.
- Long HTML/XML content where all characters must be preserved.

However, LOBs do not automatically turn the database into an optimized full-text search engine. If indexed full-text search is required, evaluate **Oracle Text** or search features supported by your release/edition rather than expecting a standard B-tree index over full `CLOB` contents.

### 4.1. Declaring a CLOB

```sql
CREATE TABLE lab_articles (
    article_id NUMBER PRIMARY KEY,
    title      VARCHAR2(200 CHAR) NOT NULL,
    body       CLOB
);
```

Insert short text to illustrate syntax:

```sql
INSERT INTO lab_articles (article_id, title, body)
VALUES (
    1,
    'Oracle Notes',
    TO_CLOB('Tutorial content on the CLOB data type.')
);

COMMIT;
```

`TO_CLOB` converts a compatible value to CLOB, yet **a SQL literal is still subject to SQL literal/expression length limits**. Never embed multi-MB string literals directly in `INSERT` statements: for large payloads, use bind variables, JDBC streams, or LOB read/write APIs.

### 4.2. Length and Substrings

```sql
SELECT
    article_id,
    title,
    DBMS_LOB.GETLENGTH(body) AS body_length,
    DBMS_LOB.SUBSTR(body, 80, 1) AS first_80_units
FROM lab_articles;
```

For CLOB, `DBMS_LOB.GETLENGTH` and LOB API offsets/amounts operate in **character units per Oracle's rules**, whereas BLOB operates in **bytes**. Supplementary Unicode characters carry UCS2-unit caveats in certain Oracle APIs; never blindly assume offsets equal UTF-8 byte counts or always match visible screen graphemes.

`DBMS_LOB.SUBSTR` returns only a **slice**. In SQL contexts, the returned string size is still bounded by return type, character set, and client limits. Do not write `DBMS_LOB.SUBSTR(body, 1000000, 1)` expecting an entire multi-MB document inside one VARCHAR2 cell.

### 4.3. Appending Content

In PL/SQL, you can fetch an internal LOB locator and call `DBMS_LOB.WRITEAPPEND`:

```sql
DECLARE
    l_body   CLOB;
    l_chunk  VARCHAR2(200) := ' Additional text segment.';
BEGIN
    SELECT body
      INTO l_body
      FROM lab_articles
     WHERE article_id = 1
       FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_body,
        amount  => LENGTH(l_chunk),
        buffer  => l_chunk
    );

    COMMIT;
END;
/
```

`FOR UPDATE` expresses row-locking intent before modifying the LOB in this example. Persistent LOB modification APIs must run inside a valid transaction, with proper privileges, a valid locator, and initialized data (not a `NULL` locator). Some scenarios may benefit from `DBMS_LOB.OPEN`/`CLOSE` to optimize consecutive writes or special index handling; do not add them blindly as a mandatory rule for every command.

## 5. `NCLOB`: Text in the National Character Set

`NCLOB` serves a similar goal to CLOB but uses the database's configured **national character set**, commonly `AL16UTF16` in typical Oracle environments. The national character set applies to `NCHAR`, `NVARCHAR2`, and `NCLOB`.

Check both database character set parameters (view privileges may depend on configuration):

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
```

Example output:

```text
NLS_CHARACTERSET       AL32UTF8
NLS_NCHAR_CHARACTERSET AL16UTF16
```

This is only an **example**; never assume every database uses these exact two values. When the database character set is already AL32UTF8 and the application uses proper Unicode, **CLOB usually satisfies storage needs for Vietnamese, Japanese, emoji, and multilingual text**. Use NCLOB only when data modeling or integration explicitly ties to the national character set.

### 5.1. Declaration and Conversion

```sql
CREATE TABLE lab_translations (
    translation_id NUMBER PRIMARY KEY,
    locale_code    VARCHAR2(20),
    text_national  NCLOB
);

INSERT INTO lab_translations (translation_id, locale_code, text_national)
VALUES (1, 'vi-VN', TO_NCLOB('Hello Oracle'));

COMMIT;
```

`TO_NCLOB` converts supported values to NCLOB. If a literal or application already lost characters **prior to conversion** due to client/database character set mismatch, converting to NCLOB cannot restore corrupted characters. Ensure client, driver, connection, and input encoding are right from the start.

SQL also has **national character literals** prefixed with `N'...'`, though how literals convert between client character set and national character set depends on Oracle configuration. Long Unicode data should be passed via **bind parameters** rather than concatenating literals into SQL strings.

### 5.2. Practical Differences Between CLOB and NCLOB

| Question | `CLOB` | `NCLOB` |
| --- | --- | --- |
| Storage character set | Database character set | National character set |
| Stores Unicode in an AL32UTF8 database? | Yes | Yes |
| Integrating with a system already using NCHAR/NVARCHAR2/NCLOB? | May require conversion | More consistent with the national character set model |
| Used for PDF/ZIP/PNG? | No | No |
| Length handling in Java apps | Verify API/driver and character units | Same, pay attention to national-character APIs |
| Default choice for new Unicode systems using AL32UTF8 | Usually sensible | Choose only with a clear justification |

**Technical note:** JDBC versions support **national character type** methods such as `setNClob` and `getNClob`. When using generic `setCharacterStream`, `setString`, or `setNString`, verify what mapping your Oracle JDBC driver supports and how your ORM framework handles types. Never assume an ORM automatically chooses national LOBs purely from Java's `String` type.

## 6. `BLOB`: Binary Bytes Inside the Database

**`BLOB` has no character set semantics.** If a PNG image starts with bytes `89 50 4E 47 ...`, those bytes must remain untouched. Never convert a binary BLOB into `VARCHAR2` and encode/decode it arbitrarily, as that can corrupt data.

Examples of suitable data:

- JPEG/PNG images, PDF documents, and ZIP archives.
- Binary output from an export engine.
- Small or medium audio/video clips when the application requires storing contents inside the DB.
- Byte payloads requiring transactional consistency and backups alongside business rows.

However, storing very large files in the database versus external object storage is an **architectural decision**: weigh file sizes, download traffic, backup/restore time, storage cost, caching, CDNs, data lifecycle, and access control. Just because `BLOB` is the right data type does not mean Oracle is always the optimal place to store all large media.

### 6.1. Declaring and Inserting a Small BLOB

```sql
CREATE TABLE lab_binary_files (
    file_id      NUMBER PRIMARY KEY,
    file_name    VARCHAR2(255 CHAR) NOT NULL,
    media_type   VARCHAR2(100 CHAR),
    file_bytes   BLOB
);

-- Hex string illustrates bytes only: 0x25 0x50 0x44 0x46...
INSERT INTO lab_binary_files (file_id, file_name, media_type, file_bytes)
VALUES (
    1,
    'example.bin',
    'application/octet-stream',
    TO_BLOB(HEXTORAW('255044462D312E37'))
);

COMMIT;
```

Those sample bytes start like the header of a PDF format, yet **they are not a valid complete PDF file**. `MEDIA_TYPE` and `FILE_NAME` are application metadata; Oracle does not validate BLOB contents from a client-supplied MIME type string.

Inspecting byte size:

```sql
SELECT
    file_id,
    file_name,
    DBMS_LOB.GETLENGTH(file_bytes) AS file_size_bytes,
    RAWTOHEX(DBMS_LOB.SUBSTR(file_bytes, 8, 1)) AS first_eight_bytes
FROM lab_binary_files;
```

For BLOB, `DBMS_LOB.GETLENGTH` returns length in bytes. `DBMS_LOB.SUBSTR` returns a RAW value, so `RAWTOHEX` helps display a hex slice for diagnostics—not a way to export an entire large binary file.

### 6.2. Appending Binary Data via `DBMS_LOB`

```sql
DECLARE
    l_blob BLOB;
    l_raw  RAW(100) := HEXTORAW('01020304AABBCCDD');
BEGIN
    SELECT file_bytes
      INTO l_blob
      FROM lab_binary_files
     WHERE file_id = 1
       FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_blob,
        amount  => UTL_RAW.LENGTH(l_raw),
        buffer  => l_raw
    );

    COMMIT;
END;
/
```

`UTL_RAW.LENGTH` measures **bytes** in a RAW value. For large payloads from applications, stream in chunks via driver APIs rather than loading entire files into `RAW` or huge byte arrays in Java memory.

### 6.3. BLOB and Character Encoding

Never call `UTL_RAW.CAST_TO_VARCHAR2` on an arbitrary PDF/ZIP BLOB expecting readable text. If a BLOB **genuinely stores UTF-8 encoded text**, the application must know the encoding and decode properly; an arbitrary binary file is not text. Conversely, if business content is **text requiring character-based SQL manipulation**, `CLOB` is usually the clearer choice.

## 7. `BFILE`: Reference to a File Outside the Database

**`BFILE` does not store the file's bytes inside datafiles**. It stores a locator built from two components:

1. **Oracle DIRECTORY object:** logical name of an OS directory declared by the DBA.
2. **Filename:** name of the file inside that directory.

Diagram:

```text
TABLE LAB_EXTERNAL_DOCS
  DOC_ID = 1
  ATTACHMENT = BFILENAME('LAB_BFILE_DIR', 'manual.pdf')
                           |
                           v
ORACLE DIRECTORY OBJECT LAB_BFILE_DIR
  DIRECTORY_PATH = /srv/oracle-lab/files
                           |
                           v
DB SERVER FILESYSTEM
  /srv/oracle-lab/files/manual.pdf
                           |
                           v
Oracle database process reads file contents
  using OS privileges + appropriate DIRECTORY privileges
```

**The path is on the machine running the Oracle Database server, not the laptop running SQL Developer or a Java client.** If the app runs on another host, `BFILENAME` cannot reference a client's `C:\Downloads` folder unless that storage is actually mounted and accessible to the Oracle server with proper permissions.

### 7.1. Creating a DIRECTORY: A DBA Task

Suppose the DBA prepared `/srv/oracle-lab/files` and placed `manual.pdf` on the **DB server**. An administrator with appropriate privileges can configure:

```sql
-- Only performed by DBA/user with CREATE ANY DIRECTORY,
-- after preparing the OS folder and file read permissions.
CREATE OR REPLACE DIRECTORY lab_bfile_dir
AS '/srv/oracle-lab/files';

GRANT READ ON DIRECTORY lab_bfile_dir TO lab_student;
```

Running `CREATE DIRECTORY` **does not create a physical folder and does not copy files**. The Oracle user also needs `READ` privilege on the DIRECTORY; the database OS process must be able to read the path and file. Never grant broad directory privileges to every user unnecessarily.

If your lab account lacks DBA privileges, **do not try to create a DIRECTORY yourself**. Use the directory object already granted by your instructor or DBA and verify its exact name.

### 7.2. Creating a Table and Storing a BFILE Locator

In an authorized practice schema:

```sql
CREATE TABLE lab_external_docs (
    doc_id     NUMBER PRIMARY KEY,
    doc_title  VARCHAR2(200 CHAR),
    attachment BFILE
);

INSERT INTO lab_external_docs (doc_id, doc_title, attachment)
VALUES (
    1,
    'PDF document on DB server',
    BFILENAME('LAB_BFILE_DIR', 'manual.pdf')
);

COMMIT;
```

`BFILENAME` constructs a locator from the **DIRECTORY object name** and filename. It **does not open the file or verify existence at insert time**: a locator can be stored even if the file does not exist on disk. At read time, verify file presence and access permissions.

The BFILE locator in a row can be changed via `UPDATE` or set to `NULL`, yet no LOB syntax lets you edit the bytes inside `manual.pdf` through BFILE like a BLOB.

### 7.3. Checking File Existence and Reading Size

```sql
DECLARE
    l_file BFILE;
    l_size NUMBER;
BEGIN
    SELECT attachment
      INTO l_file
      FROM lab_external_docs
     WHERE doc_id = 1;

    IF DBMS_LOB.FILEEXISTS(l_file) = 1 THEN
        DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);

        l_size := DBMS_LOB.GETLENGTH(l_file);
        DBMS_OUTPUT.PUT_LINE('Size: ' || l_size || ' bytes');

        DBMS_LOB.FILECLOSE(l_file);
    ELSE
        DBMS_OUTPUT.PUT_LINE('File not found or not accessible.');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
```

This is a PL/SQL demonstration requiring `DBMS_OUTPUT` enabled in your client. Opening a BFILE and querying its size can fail if directory privileges are missing, the OS path does not exist, or the file was deleted/renamed/unreadable. The exception block above closes the file if open and rethrows; production applications must handle null locators and OS errors per policy.

### 7.4. When Should BFILE NOT Be Used?

- The application must **upload, update, or delete file contents** inside Oracle transactions.
- Data must be **backed up and restored with the database** without maintaining a separate external file backup pipeline.
- Files live on end-user machines or cloud object storage not exposed to the Oracle server as an appropriate filesystem.
- File content versioning must stay transactionally consistent with the table row.
- Atomicity between row metadata and file bytes is required.

In those scenarios, **BLOB** or an external object storage architecture referencing URLs/object keys with explicit sync/backup workflows is usually better. **`BFILE` is not a generic API for Oracle to connect directly to S3/GCS or HTTP URLs**: it is tied to a DIRECTORY and files on a filesystem visible to the DB server.

## 8. Combined Example of All Four Types in One Table

To observe the types side by side, create a lab table in your own schema:

```sql
CREATE TABLE lab_lob_documents (
    document_id      NUMBER PRIMARY KEY,
    document_title   VARCHAR2(200 CHAR) NOT NULL,
    body_text        CLOB,
    body_national    NCLOB,
    content_binary   BLOB,
    external_file    BFILE,
    created_at       TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

Insert sample values, keeping in mind a BFILE locator is only usable when the corresponding DIRECTORY exists:

```sql
INSERT INTO lab_lob_documents (
    document_id, document_title,
    body_text, body_national, content_binary
)
VALUES (
    1,
    'Sample document',
    TO_CLOB('This is CLOB text with Vietnamese accents.'),
    TO_NCLOB('NCLOB text using the national character set.'),
    TO_BLOB(HEXTORAW('010203040506'))
);

COMMIT;
```

Query data type metadata:

```sql
SELECT column_id, column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_LOB_DOCUMENTS'
ORDER BY column_id;
```

The output will show `BODY_TEXT` as `CLOB`, `BODY_NATIONAL` as `NCLOB`, `CONTENT_BINARY` as `BLOB`, and `EXTERNAL_FILE` as `BFILE`. The BFILE column is currently `NULL` in the inserted row above; to attach a locator, use a DIRECTORY already configured by your DBA:

```sql
-- Run only if LAB_BFILE_DIR already exists
-- and proper access privileges exist for the file on the DB server.
UPDATE lab_lob_documents
SET external_file = BFILENAME('LAB_BFILE_DIR', 'manual.pdf')
WHERE document_id = 1;

COMMIT;
```

Read internal LOB content lengths:

```sql
SELECT
    document_id,
    DBMS_LOB.GETLENGTH(body_text)      AS clob_length,
    DBMS_LOB.GETLENGTH(body_national)  AS nclob_length,
    DBMS_LOB.GETLENGTH(content_binary) AS blob_bytes
FROM lab_lob_documents;
```

**How to read the output:** CLOB/NCLOB lengths follow Oracle API character units; BLOB is in bytes. Unicode data with multi-byte characters means UTF-8 byte count does not equal character count. Never compare `CLOB_LENGTH` directly to `BLOB_BYTES` to deduce which consumes "more memory".

## 9. `NULL` Differs from an Empty LOB

`NULL` means **there is no LOB locator/LOB value** in the column; an **empty LOB** exists with length 0. This distinction is critical when applications want to append data.

```sql
INSERT INTO lab_articles (article_id, title, body)
VALUES (2, 'No content yet', NULL);

INSERT INTO lab_articles (article_id, title, body)
VALUES (3, 'Empty content', EMPTY_CLOB());

COMMIT;

SELECT
    article_id,
    CASE WHEN body IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS lob_state,
    DBMS_LOB.GETLENGTH(body) AS lob_length
FROM lab_articles
WHERE article_id IN (2, 3)
ORDER BY article_id;
```

Expected result:

| ARTICLE_ID | LOB_STATE | LOB_LENGTH |
| --- | --- | --- |
| 2 | `NULL` | `NULL` |
| 3 | `NOT NULL` | `0` |

For BLOB, there is `EMPTY_BLOB()`. For NCLOB, initialize using an **empty NCLOB value via a supported API/type conversion**, rather than assuming an `EMPTY_NCLOB` function exists identically. BFILE is a locator to an OS file and has no Oracle-generated empty-content function `EMPTY_BFILE`.

If an internal LOB column is currently `NULL`, update it to an empty LOB or a valid LOB before calling modification APIs that require an initialized locator. `NULL`, an empty LOB, and a whitespace-only string carry distinct application meanings.

## 10. SecureFiles, BasicFiles, and Storage Configuration

Oracle has two primary internal LOB architectures:

- **BasicFiles LOB:** traditional LOB mechanism found in older systems or legacy datasets.
- **SecureFiles LOB:** modern LOB mechanism with advanced storage/management features and I/O optimizations where supported.

**SecureFiles does not mean "sensitive files are automatically encrypted".** **Compression, deduplication, and encryption** are specific configuration options; support status, licensing entitlements, and storage prerequisites depend on release/edition. Never assume an advanced feature is active merely from seeing SecureFiles.

### 10.1. LOB Segments and In-Row Storage Options

Illustrative configuration on a CLOB table:

```sql
CREATE TABLE lab_secure_articles (
    article_id NUMBER PRIMARY KEY,
    body       CLOB
)
LOB (body) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
```

**Prerequisites:** tablespace/segment-space management and Oracle version must support SecureFiles; legacy setups or DBA policies may disallow this clause. In a preconfigured lab, creating `CLOB` with environment defaults is usually simpler. This example is for reading DDL, not for altering server storage policies.

Common attributes:

| Attribute | Meaning |
| --- | --- |
| `STORE AS SECUREFILE` / `BASICFILE` | Selects internal LOB storage architecture when supported by the environment |
| `ENABLE/DISABLE STORAGE IN ROW` | Controls whether small LOBs can live inside the table row per Oracle rules |
| `CACHE` / `NOCACHE` | Controls how LOB I/O interacts with the buffer cache |
| `LOGGING` / `NOLOGGING` | Redo logging policy for eligible operations; `NOLOGGING` affects recoverability |
| LOB tablespace/segment | Separate storage area for out-of-row LOB data |
| Compression/deduplication/encryption | Optional features requiring resource, capability, and licensing review |

`NOLOGGING` **does not mean "zero redo in all situations"** and can make certain operations unrecoverable without appropriate backups. Never enable it just for speed while ignoring recovery requirements.

### 10.2. Inspecting LOB Metadata via the Data Dictionary

In the schema owning the tables:

```sql
SELECT
    table_name,
    column_name,
    segment_name,
    tablespace_name,
    securefile,
    in_row,
    cache,
    logging
FROM user_lobs
WHERE table_name IN (
    'LAB_LOB_DOCUMENTS',
    'LAB_ARTICLES',
    'LAB_SECURE_ARTICLES'
)
ORDER BY table_name, column_name;
```

`USER_LOBS` holds management metadata for **internal LOB columns**, LOB segments, and storage attributes; **`BFILE` is not managed as an internal database LOB segment**, because its contents live outside the DB. To check BFILE column types, query `USER_TAB_COLUMNS`; to inspect DIRECTORY objects, query directory views per your privileges.

`SEGMENT_NAME` is metadata for the LOB segment, yet it does not mean every tiny LOB has preallocated out-of-row blocks. On newly created tables, deferred segment creation and storage settings may defer segment allocation until needed.

### 10.3. LOBs and Undo/Redo

Internal LOBs support **transactional read consistency**, recovery, and content version retention depending on SecureFiles/BasicFiles, logging, and retention settings. Updating large LOBs can generate substantial redo/undo or LOB versions; backup sizes also scale with actual data.

BFILE has no transaction log for OS file edits; if another process modifies `manual.pdf` between two SQL queries reading the BFILE, Oracle cannot guarantee external file contents obey row-level snapshot consistency.

## 11. Reading/Writing LOBs in PL/SQL: Avoiding Regular String Limits

`DBMS_LOB` provides common APIs:

| API | General Role | Eligible Types |
| --- | --- | --- |
| `GETLENGTH` | Returns length | CLOB, NCLOB, BLOB, BFILE under proper open/read conditions |
| `SUBSTR` | Extracts a slice from an offset | CLOB, NCLOB, BLOB; BFILE under matching API and file state |
| `INSTR` | Searches for a pattern | Character LOB or binary LOB with matching pattern type |
| `READ` | Reads chunks into a buffer | Internal LOBs, BFILE via read-only interface |
| `WRITE` / `WRITEAPPEND` | Writes at offset or appends | Modifiable **internal LOBs** |
| `APPEND` | Appends one LOB's contents onto another | Internal LOBs of matching type pair |
| `CREATETEMPORARY` / `FREETEMPORARY` | Allocates and frees temporary LOBs | Temporary internal LOBs |
| `FILEEXISTS` / `FILEOPEN` / `FILECLOSE` | Checks, opens, and closes external files | **BFILE** |

You do not need to load an entire file into RAM to read it: if you only need the first 4,096 bytes of a BLOB, read a slice:

```sql
DECLARE
    l_blob BLOB;
    l_part RAW(4096);
BEGIN
    SELECT file_bytes
    INTO l_blob
    FROM lab_binary_files
    WHERE file_id = 1;

    l_part := DBMS_LOB.SUBSTR(l_blob, 4096, 1);
    DBMS_OUTPUT.PUT_LINE('Read chunk length: ' || UTL_RAW.LENGTH(l_part));
END;
/
```

The following example creates a **temporary CLOB**, appends text, and frees it:

```sql
DECLARE
    l_temp  CLOB;
    l_text  VARCHAR2(100) := 'Temporary text used during session processing.';
BEGIN
    DBMS_LOB.CREATETEMPORARY(l_temp, TRUE);
    DBMS_LOB.WRITEAPPEND(l_temp, LENGTH(l_text), l_text);
    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_temp));
    DBMS_LOB.FREETEMPORARY(l_temp);
END;
/
```

In production code, always free temporary LOBs when finished and handle exceptions cleanly. Holding temporary locators too long on pooled connections can grow session temporary space unexpectedly. Temporary LOBs are not durable table objects merely because `CREATETEMPORARY` was called.

## 12. Java JDBC: Streaming Text and Binary Properly

In Java applications, how contents are transferred depends on the JDBC API:

| Oracle Type | Common JDBC API | Java Type |
| --- | --- | --- |
| `CLOB` | `PreparedStatement.setCharacterStream` / `setClob`, `ResultSet.getCharacterStream` / `getClob` | `Reader`, `Clob` |
| `NCLOB` | `setNCharacterStream` / `setNClob`, `getNCharacterStream` / `getNClob` | `Reader`, `NClob` |
| `BLOB` | `setBinaryStream` / `setBlob`, `getBinaryStream` / `getBlob` | `InputStream`, `Blob` |
| `BFILE` | Oracle-specific JDBC APIs or driver-supported locator/read-only mechanisms | File on DB server, not a direct upload stream from the client |

Depending on your Oracle JDBC driver and JPA/JDBC framework, exact mappings can vary. For systems handling large files, prefer **streaming**, rather than calling `ResultSet.getBytes` on files of hundreds of MBs.

### 12.1. Uploading CLOB and BLOB Using Streams

Java example using the `LAB_LOB_DOCUMENTS` lab table created in Section 8. Assume `content.txt` is UTF-8 and `attachment.bin` is binary data:

```java
import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;

public class LobUploadExample {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("ORACLE_JDBC_URL");
        String user = System.getenv("ORACLE_DB_USER");
        String password = System.getenv("ORACLE_DB_PASSWORD");

        Path textPath = Path.of("content.txt");
        Path binaryPath = Path.of("attachment.bin");

        String sql = """
            INSERT INTO lab_lob_documents (
                document_id, document_title, body_text, content_binary
            ) VALUES (?, ?, ?, ?)
            """;

        try (Connection connection =
                 DriverManager.getConnection(url, user, password);
             Reader textReader =
                 Files.newBufferedReader(textPath, StandardCharsets.UTF_8);
             InputStream binaryStream = Files.newInputStream(binaryPath);
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, 1001L);
            statement.setString(2, "Document uploaded via JDBC");
            statement.setCharacterStream(3, textReader);
            statement.setBinaryStream(4, binaryStream, Files.size(binaryPath));
            statement.executeUpdate();
        }
    }
}
```

Environment variables must be provided by the runtime environment; for example, a PDB JDBC URL might look like `jdbc:oracle:thin:@//localhost:1521/FREEPDB1`, replaced with your actual service. Never hardcode passwords in source code. With your specific driver/framework, verify support for lengthless overloads of `setCharacterStream` and stream-size requirements.

**About commits:** JDBC typically defaults to auto-commit when opening a connection, though real applications often disable auto-commit or rely on a transaction manager. The example above leaves auto-commit unchanged; if you disable it, call `commit()` after `executeUpdate()` succeeds or let your transaction manager handle it.

### 12.2. Downloading a BLOB via Stream

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class LobDownloadExample {
    public static void main(String[] args) throws Exception {
        String sql = """
            SELECT content_binary
            FROM lab_lob_documents
            WHERE document_id = ?
            """;

        try (Connection connection = DriverManager.getConnection(
                 System.getenv("ORACLE_JDBC_URL"),
                 System.getenv("ORACLE_DB_USER"),
                 System.getenv("ORACLE_DB_PASSWORD"));
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, 1001L);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new IllegalStateException("Document not found");
                }

                try (InputStream content = rows.getBinaryStream(1);
                     OutputStream output =
                         Files.newOutputStream(Path.of("downloaded.bin"))) {
                    if (content == null) {
                        throw new IllegalStateException("BLOB is NULL");
                    }
                    content.transferTo(output);
                }
            }
        }
    }
}
```

Keep **ResultSet, PreparedStatement, and Connection open** while reading the stream; some drivers invalidate the locator/stream if the session closes early. Streaming binary data and closing resources properly also keeps RAM usage bounded.

For NCLOB, consider `setNCharacterStream` or `setNClob` per driver support. For BFILE, Java code must use Oracle JDBC's dedicated locator handling and rely on **DB server** file read permissions; calling `setBinaryStream` to "upload into a BFILE" misunderstands the model.

### 12.3. What Must Web APIs Serving BLOBs Watch Out For?

When implementing HTTP upload/download:

- Enforce file size limits and quota policies to avoid exhausting storage.
- Validate file types by application policy and, where needed, actual file contents; never trust client-supplied filenames or `Content-Type` headers blindly.
- Stream to cap RAM usage; configure timeouts and read/write duration limits.
- Enforce per-document authorization, especially on download endpoints.
- On responses, set appropriate `Content-Type` and `Content-Disposition` headers to prevent browser execution vulnerabilities on untrusted uploads.
- Account for backups, checksum/hash verification, failed partial uploads, and metadata–binary consistency.

LOBs solve **data representation inside the database**; they do not solve upload security or distributed content architecture by themselves.

## 13. Performance and Operations with LOBs

### 13.1. Factors Affecting Performance

| Factor | Impact to Evaluate |
| --- | --- |
| Average/maximum LOB size | LOB segment space, redo, backup, network transfer, cache |
| In-row vs. out-of-row storage | Can affect block accesses and main-table row width |
| `CACHE` / `NOCACHE` | How LOB I/O interacts with the buffer cache |
| SecureFiles/BasicFiles | Storage capabilities, management features, and overhead differ |
| Compression/deduplication | Can save space at the cost of CPU and feature/licensing availability |
| Encryption | Protects data at rest when configured properly; carries overhead and key-management needs |
| Full-LOB loading vs. chunked streaming | Heavily impacts app RAM and request/response footprints |
| Query and index patterns | Full-text/JSON searches may need specialized engines/indexes; never B-tree index entire LOBs like short key columns |
| Update frequency on large values | Redo, retention/LOB versioning, temporary space, throughput |

### 13.2. Avoid Unconditional `SELECT *` on LOB Tables

For document listing screens, applications often only need `ID`, `TITLE`, `CREATED_AT`, and content size. Query:

```sql
SELECT document_id,
       document_title,
       created_at,
       DBMS_LOB.GETLENGTH(content_binary) AS byte_count
FROM lab_lob_documents
ORDER BY created_at DESC;
```

Only fetch the BLOB contents in a separate operation when the user selects a specific document. This keeps a listing screen from pulling many LOBs at once. Even when LOB locators and drivers lazy-load internally, separating metadata and content APIs creates a cleaner contract.

### 13.3. Backup and Recovery

For **internal LOBs**, data resides in the database and is covered by Oracle backup/recovery strategies. A valid complete database backup includes the database components under your chosen RMAN/backup plan; exporting only a few metadata rows without LOBs is insufficient.

For **BFILE**, you need an **independent OS file backup plan**, along with procedures ensuring restored paths, permissions, checksums, and point-in-time alignment match the database restore. Successfully restoring a row with a BFILE locator **does not guarantee the referenced OS file still exists**.

When offloading BLOBs to object storage (S3 or equivalent), the same principle applies: a database transaction does not atomically commit with an external object store unless the application implements compensating/reconciliation protocols.

## 14. Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| "Vietnamese text requires NCLOB." | CLOB with a Unicode database character set like `AL32UTF8` already stores Vietnamese. |
| "BLOB is a large string searchable with LIKE." | BLOB holds bytes; if data is text, choose CLOB or define encoding and handle it explicitly. |
| "CLOB always lives inside the table row." | Oracle can store internal LOBs in-row or out-of-row in a LOB segment. |
| "BFILE stores the file inside Oracle datafiles." | BFILE stores only a locator; real bytes live on the DB server filesystem. |
| "CREATE DIRECTORY creates the folder on Linux." | It only creates an Oracle object pointing to a path; DBA/OS must prepare the folder and permissions separately. |
| "BFILENAME guarantees the file exists." | It constructs a locator; you must check file existence and readability when accessing it. |
| "COMMIT means Oracle backed up the BFILE." | Transactions only record locator changes in rows; OS files need separate backups. |
| "BFILE contents can be UPDATEd like BLOB." | BFILE is read-only through Oracle; byte updates must happen outside the database. |
| "CLOB and BLOB lengths use the same unit." | CLOB/NCLOB measure in API character units; BLOB measures in bytes. |
| "NULL and EMPTY_CLOB() are the same." | NULL means no LOB value; an empty CLOB is an existing LOB of length 0. |
| "A LOB locator holds all bytes of the file." | A locator is a reference; use streams/APIs to read or write contents. |
| "SecureFiles means encrypted and safely backed up." | Encryption/backup are separate configurations and procedures; the name SecureFiles does not provide them automatically. |
| "Just add RAM and load every BLOB with getBytes()." | Loading whole files into RAM still risks OOM and GC pressure; prefer streaming. |
| "B-tree index on a whole CLOB works like VARCHAR2." | LOBs have direct-indexing limits; full-text and advanced search require dedicated mechanisms. |

## 15. Practice Exercises

### Exercise 1 — Choose the Data Type

For each item, choose `CLOB`, `NCLOB`, `BLOB`, or `BFILE` and explain why:

1. A 200 KB tutorial article requiring keyword search inside paragraphs.
2. A 2 MB PNG image that must commit with the profile record and restore with DB backups.
3. A 50 MB PDF already sitting in a DB server folder, read-only for Oracle, with file backups managed by the storage team.
4. A legacy system mandating Oracle's national character set for all long text content.
5. An encrypted ZIP archive with no text semantics.

**Hint:** (1) CLOB, and evaluate full-text search; (2) BLOB; (3) BFILE **if** paths/permissions are stable and out-of-transaction semantics are acceptable; (4) NCLOB; (5) BLOB. When storing files externally outside Oracle's server filesystem, consider object storage + metadata instead of BFILE.

### Exercise 2 — Observe NULL vs. Empty LOB

Insert the two rows in `LAB_ARTICLES` per Section 9; query `BODY IS NULL` and `DBMS_LOB.GETLENGTH(BODY)`. Explain why empty data and nonexistent data may need distinct handling in an API.

### Exercise 3 — Inspect LOB Storage Metadata

After creating `LAB_LOB_DOCUMENTS`:

```sql
SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'LAB_LOB_DOCUMENTS'
ORDER BY column_id;

SELECT column_name, segment_name, securefile, in_row
FROM user_lobs
WHERE table_name = 'LAB_LOB_DOCUMENTS'
ORDER BY column_name;
```

Explain why the BFILE column appears in `USER_TAB_COLUMNS` yet has no corresponding internal LOB data segment in `USER_LOBS`.

### Exercise 4 — Write PL/SQL Handling Each LOB Type

1. For CLOB: use `DBMS_LOB.SUBSTR` to fetch the beginning and `DBMS_LOB.WRITEAPPEND` to append new text.
2. For BLOB: use `DBMS_LOB.GETLENGTH` and `RAWTOHEX(DBMS_LOB.SUBSTR(...))` to inspect the first few bytes.
3. For NCLOB: insert multilingual text and read using the appropriate character LOB API.
4. For BFILE: take a DBA-provided locator, use `DBMS_LOB.FILEEXISTS`; if present, open read-only, read length, and close it.

**Requirement:** operate only on your own lab tables/schema; never attempt to modify OS files via BFILE.

### Exercise 5 — Analyze a Document Upload API

A Spring Boot app receives uploaded files from users. Describe both designs:

- **Option A:** store contents as a BLOB in Oracle and metadata in standard columns. Detail how transactions, backups, and streaming work.
- **Option B:** store contents in object storage, keeping `OBJECT_KEY`/URL and checksum in Oracle. Describe how partial upload failures, access control, and separate backups are handled.

Explain why **BFILE is not automatically an implementation of Option B** if object storage is not presented as a filesystem accessible by the Oracle server.

### Exercise 6 — Verify JDBC Communication

Write a Java program using `setCharacterStream` to send a UTF-8 file to a CLOB and `setBinaryStream` to send a binary file to a BLOB. Read them back using `getCharacterStream` and `getBinaryStream`, then compare:

- Does the returned text preserve Vietnamese and Unicode characters?
- Does the downloaded byte count match the uploaded byte count?
- Do checksums of the binary streams match?
- Does the program close connection, statement, result set, and streams even on errors?

For binary data, checksums or byte-by-byte comparison provide far better proof than printing contents to the console.

### Clean Up Lab Objects

Run only when you created these tables yourself in the proper practice schema:

```sql
DROP TABLE lab_articles PURGE;
DROP TABLE lab_translations PURGE;
DROP TABLE lab_binary_files PURGE;
DROP TABLE lab_external_docs PURGE;
DROP TABLE lab_lob_documents PURGE;
DROP TABLE lab_secure_articles PURGE;
```

`PURGE` bypasses the recycle bin. If you did not create one of those tables, its `DROP` statement will report that it does not exist; do not run the whole block blindly as a mandatory script. **Never delete someone else's DIRECTORY object or physical files** during lab cleanup; those are separately managed DBA/OS resources.

## Conclusion

`CLOB` and `NCLOB` are for **long text**, differing in database character set versus national character set; `BLOB` is for **binary bytes** inside the database; `BFILE` is only a **read-only reference to a file on the DB server filesystem**. The three internal LOBs participate in Oracle transactions, backups, and storage management; BFILE requires external management of paths, OS permissions, existence, and backups.

In practice, choose based on **data semantics**, not just size: text vs. binary, Oracle-managed vs. external contents, Unicode requirements, read/write vs. read-only, and whether recovery must stay tied to database transactions/backups. When working with large payloads, use **LOB locators and streaming APIs** rather than stuffing entire files into a single string or byte array in application memory.

## Further Oracle Reading

- [Oracle Database SecureFiles and Large Objects Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/) — internal/external LOB architecture, SecureFiles/BasicFiles, locators, SQL and PL/SQL operations.
- [Oracle Database SQL Language Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — `CLOB`, `NCLOB`, `BLOB`, `BFILE`, `CREATE TABLE`, and `CREATE DIRECTORY` definitions.
- [Oracle Database PL/SQL Packages and Types Reference: DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html) — `GETLENGTH`, `SUBSTR`, `READ`, `WRITEAPPEND`, and BFILE operations.
- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — handling LOBs via JDBC and streaming APIs.
- [Oracle Database Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — `USER_LOBS`, `USER_TAB_COLUMNS`, and LOB metadata.

For an Oracle release other than 19c, consult the corresponding release documentation for LOB limits, SecureFiles options, API functions, and privilege policies before deploying to production.
