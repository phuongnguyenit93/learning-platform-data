# LOB Locator, In-Row/Out-of-Row Data, and Resource Lifecycle in Oracle Database

Oracle uses Large Object (LOB) data types to store large content such as long text, images, PDFs, audio, video, or binary payloads. When working with LOBs, an application does not necessarily read the entire content into memory on every query. Instead, the database returns a **LOB locator** — a reference that allows PL/SQL or a client to access the content in chunks.

Three concepts should be distinguished:

- **LOB value:** the actual content, such as the characters of a CLOB or the bytes of a BLOB.
- **LOB locator:** a reference to a LOB value; a variable of type CLOB/BLOB in PL/SQL typically holds a locator rather than containing the entire payload.
- **LOB storage:** where Oracle stores the payload, which can be within the data row (in-row) or in a separate LOB segment (out-of-row).

Resource lifecycle also depends on the LOB type. A persistent LOB belongs to a row in a table; a temporary LOB is created for intermediate processing within a session/call; a BFILE only references a file outside the database and is read-only through Oracle.

This lesson explains how locators work, the difference between in-row and out-of-row storage, BasicFiles and SecureFiles, how to create/read/write LOBs using DBMS_LOB, manage temporary LOBs, use BFILEs, inspect metadata, and safely retain resources in applications.

## 1. LOB Data Types

### 1.1. The Four Main LOB Types

| Type | Content | Storage Location | Characteristics |
| --- | --- | --- | --- |
| BLOB | Binary data | Inside database | Bytes, suitable for images, PDFs, compressed files, binary payloads |
| CLOB | Text in the database character set | Inside database | Large character data |
| NCLOB | Text in the national character set | Inside database | Text using the national character set |
| BFILE | Binary data in a file outside the database | Database server file system | Read-only locator; database does not manage file content like internal LOBs |

BLOB, CLOB, and NCLOB are **internal LOBs** because their payloads are stored inside the database. BFILE is an **external LOB**: the database stores the locator and directory/file metadata, while the content resides on the external file system.

### 1.2. CLOB and NCLOB

CLOB stores character data in the database character set. NCLOB stores character data in the national character set. Choose based on character encoding requirements and application data standards; do not use NCLOB merely because its name includes "National".

Operations on CLOB/NCLOB work in character units according to LOB API rules. This differs from BLOB, where offset and amount are measured in bytes.

### 1.3. BLOB

BLOB stores bytes without interpreting them as text. It is the appropriate choice for:
- Images and PDF documents.
- Compressed files or encrypted data.
- Audio/video files.
- Application-generated binary content.

Do not convert a BLOB to VARCHAR2 merely for convenience. Conversion can alter bytes or hit length limits.

### 1.4. BFILE

BFILE stores a locator to a file in an Oracle directory object. The database can check, open, and read the file via DBMS_LOB, but cannot write content back to the file through BFILE. Because the file resides outside the database, OS permissions, DIRECTORY privileges, and file system backups must be managed separately.

### 1.5. Why Not Use VARCHAR2 for Everything?

VARCHAR2 is suitable for string data within SQL size limits. LOBs are designed for large content and provide APIs for piecewise reading/writing. Using LOBs for every small string is not optimal either; choose the type based on size, access patterns, and data lifecycle.

## 2. What Is a LOB Locator?

### 2.1. A Locator Is a Reference, Not the Payload

When querying a CLOB column:

~~~sql
SELECT document_body
FROM   documents
WHERE  document_id = 100;
~~~

Oracle can return the LOB locator. The application uses the locator to read the content, rather than being forced to convert the entire CLOB into a fixed-size string variable.

In PL/SQL:

~~~sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_body)
    );
END;
/
~~~

The variable `l_body` holds a locator to the CLOB. `DBMS_LOB.GETLENGTH` retrieves the LOB length; it does not require printing the entire content.

### 2.2. Locators and Data Are Managed Separately

The locator enables Oracle to identify a LOB value and its storage location. Internal LOBs have metadata stored in the database; the payload may reside in the row or in a LOB segment. Oracle manages the related storage structures and internal index.

Do not directly modify internal LOB segments or indexes. Use SQL and the DBMS_LOB API to manipulate content; use dictionary views to observe metadata.

### 2.3. Copying a Locator Does Not Copy the Content

If you assign one locator to another locator variable, do not assume Oracle has created an independent copy of the entire LOB. To copy content to a destination LOB, use operations such as `DBMS_LOB.COPY` or `DBMS_LOB.APPEND` as appropriate.

This matters when an application needs to keep an independent copy of content before modifying it. Create the destination LOB and copy the payload, rather than merely assigning the locator and assuming the two contents are separated.

### 2.4. Locator Lifecycle Is Tied to the Session/Connection

In applications, a locator returned by the database is tied to the corresponding connection and execution context. With JDBC, read/write the LOB and complete the stream while the connection is still valid. Do not hold a locator or stream and then return the connection to the pool, close the connection, or use it from another connection.

In PL/SQL, local locators are typically used within the scope of a block/procedure. For persistent LOBs, if you want to write to the content of an existing row, you must lock the row appropriately, typically using `SELECT ... FOR UPDATE`.

## 3. Persistent LOB, Temporary LOB, and BFILE

### 3.1. Persistent LOB

A persistent LOB is a BLOB/CLOB/NCLOB stored in a column of a row. Its lifecycle follows the table data:
- Create the row and initialize the LOB.
- Obtain the locator to read/write.
- Commit the changes along with the transaction.
- Update or replace the content.
- Delete the row or set the LOB column to NULL when business logic requires.

Persistent LOBs are managed by the database within database transactions and backup/recovery.

### 3.2. Temporary LOB

A temporary LOB is created for intermediate content processing, such as concatenating large text, building returned content, or transforming a LOB. It is not a LOB value stored as a persistent column of a row.

It can be explicitly created with `DBMS_LOB.CREATETEMPORARY` and freed with `DBMS_LOB.FREETEMPORARY`. Temporary LOBs consume temporary tablespace/session resources; failing to free them properly can increase resource consumption, especially in connection-pooled applications.

### 3.3. BFILE

A BFILE is a locator to an external file. The database does not own the file payload, and BFILE is read-only through DBMS_LOB. The file must exist on the database server at the path mapped by a DIRECTORY object, and the database account needs the READ privilege on the DIRECTORY.

### 3.4. Lifecycle Comparison

| Attribute | Persistent LOB | Temporary LOB | BFILE |
| --- | --- | --- | --- |
| Where is the payload? | Database | Temporary storage | External file system |
| Stored in a table column? | Yes | Not necessarily | Column stores locator |
| Write content? | Yes, subject to privileges and transactions | Yes | Not via BFILE |
| Transaction | Participates in data transactions | Has its own rules for temporary LOBs | External file content is outside DB transactions |
| Release | Via UPDATE/DELETE and segment management | FREETEMPORARY or end of duration | FILECLOSE; file managed by OS |
| Database backup | Yes | Not as persistent data | File must be backed up separately |

## 4. In-Row and Out-of-Row Storage

### 4.1. The Locator Remains in the Row

For internal LOBs, the table row always contains the locator/metadata needed to access the LOB. The difference between in-row and out-of-row is where the **LOB payload** is stored.

- **In-row:** the locator and small LOB payload are stored together in the table row.
- **Out-of-row:** the row contains the locator, while the payload resides in a separate LOB segment.

Therefore, out-of-row does not mean the row contains nothing related to the LOB. The locator remains the bridge Oracle uses to find the payload.

### 4.2. ENABLE STORAGE IN ROW

By default, Oracle typically allows storing small LOB payloads directly in the row via `ENABLE STORAGE IN ROW`. Small values (typically up to around 4 KB, depending on limits and row conditions) can be stored in-row. Larger payloads are stored out-of-row.

Example:

~~~sql
CREATE TABLE document_notes (
    note_id NUMBER PRIMARY KEY,
    note_text CLOB
)
LOB (note_text) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
);
~~~

In-row storage can make reading small LOBs faster because the payload sits with the row, avoiding a separate LOB segment access for those cases. On the other hand, table rows become larger.

### 4.3. DISABLE STORAGE IN ROW

You can require LOB payloads to always be stored out-of-row:

~~~sql
CREATE TABLE document_payloads (
    payload_id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS SECUREFILE (
    DISABLE STORAGE IN ROW
    NOCACHE
);
~~~

Even small LOBs are stored in the LOB segment; the row holds the locator. This can keep table rows more compact when LOB content is usually large or accessed separately.

### 4.4. Comparison

| Criterion | In-row | Out-of-row |
| --- | --- | --- |
| Payload location | Inside table row | LOB segment |
| Row size | Increases with small payloads | Row holds locator; payload stored separately |
| Small LOB access | May require fewer I/O steps | May require accessing the LOB segment |
| Scanning many rows without needing LOB content | Rows may be larger | Rows are typically more compact |
| Large LOBs | Not stored inline when exceeding threshold | Stored out-of-row |
| Control | ENABLE STORAGE IN ROW | DISABLE STORAGE IN ROW |

### 4.5. Not Every LOB Should Be Forced Out-of-Row

If the application frequently queries metadata and reads short CLOBs, in-row storage can be beneficial. If a table has millions of rows and queries typically only read key/status columns without needing the LOB, out-of-row payloads can help reduce row size and increase block density.

The decision depends on payload size, LOB access frequency, scan patterns, caching, and workload. Do not choose based on guesswork alone.

### 4.6. The 4 KB Threshold Is Not an Absolute Guarantee on Row Size

A common rule of thumb is that small LOB payloads up to about 4 KB can be stored in-row when ENABLE STORAGE IN ROW is enabled. Actual behavior also depends on row format and available row space. Payloads exceeding the threshold are stored out-of-row. Check the documentation for your exact release and measure on real data.

## 5. LOB Segment, LOB Index, and CHUNK

### 5.1. LOB Segment

When a payload is stored out-of-row, Oracle uses a LOB segment to store the content. Each LOB column can have its own segment; for partitioned tables, storage can be organized by partition/subpartition.

The LOB segment is managed by Oracle. Do not directly access blocks or manually update the segment to modify content.

### 5.2. LOB Index

Oracle creates and manages an internal LOB index to map locators to LOB data pieces. This is not a regular business index for applications to target with predicates. Do not manually DROP, rebuild, or modify the internal LOB index outside of Oracle-supported operations.

### 5.3. CHUNK

With BasicFiles, `CHUNK` defines the unit of LOB allocation/read/write in blocks or groups of blocks. Choose a chunk size appropriate for data size and access patterns; too large a chunk can waste space for small operations, while too small a chunk can increase overhead.

SecureFiles manages storage differently from BasicFiles; do not mechanically apply every BasicFiles parameter to SecureFiles. Consult the SQL Language Reference and LOB storage clause for your Oracle version.

### 5.4. Inspecting Segments

You can inspect segments in the schema:

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks
FROM   user_segments
WHERE  segment_type LIKE 'LOB%'
ORDER  BY segment_type, segment_name;
~~~

Segment names may be system-generated by Oracle. Use metadata from USER_LOBS to identify the corresponding LOB column.

## 6. BasicFiles and SecureFiles

### 6.1. BasicFiles

BasicFiles is the traditional LOB implementation. It supports internal LOBs but offers fewer optimization capabilities and features than SecureFiles. Parameters such as CHUNK and PCTVERSION frequently appear in BasicFiles configurations.

### 6.2. SecureFiles

SecureFiles is Oracle's modern LOB architecture, designed to improve performance and support features such as:
- Compression.
- Deduplication.
- Encryption.
- Improved caching and storage management.

Feature availability depends on database version, configuration, tablespace, and licensing policies. SecureFiles generally requires a tablespace using Automatic Segment Space Management (ASSM) and an appropriate compatible setting.

### 6.3. Creating a SecureFiles LOB

~~~sql
CREATE TABLE documents (
    document_id NUMBER GENERATED ALWAYS AS IDENTITY,
    title       VARCHAR2(200) NOT NULL,
    body        CLOB,
    payload     BLOB,
    CONSTRAINT pk_documents PRIMARY KEY (document_id)
)
LOB (body) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    DISABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

This example assumes tablespace LOB_TS already exists and meets SecureFiles requirements. Adjust the tablespace name and options to match your environment.

### 6.4. Creating a BasicFiles LOB

~~~sql
CREATE TABLE legacy_documents (
    document_id NUMBER PRIMARY KEY,
    body CLOB
)
LOB (body) STORE AS BASICFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    PCTVERSION 10
    NOCACHE
    LOGGING
);
~~~

This is an example for schemas that require BasicFiles. For new systems, evaluate SecureFiles first; do not switch merely because a single parameter looks appealing.

### 6.5. Compression, Deduplication, and Encryption

SecureFiles can support:
- **Compression:** reduces storage space for compressible data, at the cost of CPU during compression/decompression.
- **Deduplication:** detects duplicate content to reduce storage usage, useful when many LOBs are identical.
- **Encryption:** protects stored data according to Oracle configuration.

These options may carry licensing requirements or feature restrictions depending on edition/version. Confirm licensing policies and benchmark CPU, latency, and storage costs before enabling them.

## 7. CACHE, NOCACHE, and LOGGING

### 7.1. CACHE

CACHE allows LOB blocks to participate in the buffer cache according to Oracle's policy. This can be useful when applications repeatedly read the same LOB or read it multiple times within a session.

### 7.2. NOCACHE

NOCACHE limits placing LOB data into the buffer cache according to Oracle's storage behavior. It can be suitable for large LOBs, infrequently repeated accesses, or workloads where LOBs should not displace OLTP data from the cache.

### 7.3. CACHE READS

Some configurations support CACHE READS, meaning caching occurs on reads without applying the same caching policy to writes. Check syntax and behavior for your LOB type and version.

### 7.4. LOGGING and NOLOGGING

LOGGING/NOLOGGING affects redo generation for supported operations. NOLOGGING does not mean "no backup needed" or "no recovery risk". It can affect media recovery and Data Guard depending on the operation and configuration.

Do not choose NOLOGGING merely for speed without evaluating backup, recovery, standby, and data protection requirements.

## 8. NULL, EMPTY_CLOB, and EMPTY_BLOB

### 8.1. NULL Differs from an Empty LOB

A LOB column can be NULL or contain an empty LOB value:
- NULL: there is no valid LOB locator to manipulate content.
- EMPTY_CLOB()/EMPTY_BLOB(): creates an initialized empty LOB from which a locator can be obtained and data written.

Example:

~~~sql
INSERT INTO documents (title, body, payload)
VALUES ('Draft', EMPTY_CLOB(), EMPTY_BLOB());
~~~

Do not use NULL when you intend to call DBMS_LOB.WRITE or WRITEAPPEND without properly initializing the LOB first.

### 8.2. Checking NULL and Length

~~~sql
SELECT document_id,
       CASE WHEN body IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS body_state,
       CASE
           WHEN body IS NULL THEN NULL
           ELSE DBMS_LOB.GETLENGTH(body)
       END AS body_length
FROM   documents;
~~~

An empty LOB has a locator and length 0; a NULL LOB has no locator. Check for NULL state before calling APIs that require a valid locator.

### 8.3. Initializing via UPDATE

~~~sql
UPDATE documents
SET body = EMPTY_CLOB()
WHERE document_id = 100;
~~~

Afterward, you can obtain the locator using SELECT FOR UPDATE to write content.

## 9. Creating and Writing Persistent LOBs with DBMS_LOB

### 9.1. INSERT and RETURNING Locator

A common pattern to create a row and write content in the same block:

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(32767) := 'New document content';
BEGIN
    INSERT INTO documents (title, body)
    VALUES ('Getting Started', EMPTY_CLOB())
    RETURNING body INTO l_body;

    IF l_text IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_body,
            LENGTH(l_text),
            l_text
        );
    END IF;

    COMMIT;
END;
/
~~~

RETURNING retrieves the locator of the newly initialized LOB. WRITEAPPEND appends content to the end of the CLOB. For CLOB, amount is measured in characters; for BLOB, amount is measured in bytes.

In real applications, do not COMMIT inside shared procedures if transactions are controlled by the caller. The COMMIT here is only to illustrate a standalone script.

### 9.2. Writing to an Existing LOB

When updating an existing persistent LOB, obtain the locator and lock the row:

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(32767) := 'Appended section';
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100
    FOR UPDATE;

    IF l_body IS NULL THEN
        UPDATE documents
        SET body = EMPTY_CLOB()
        WHERE document_id = 100
        RETURNING body INTO l_body;
    END IF;

    IF l_text IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_body,
            LENGTH(l_text),
            l_text
        );
    END IF;

    COMMIT;
END;
/
~~~

SELECT FOR UPDATE locks the row to protect the LOB update transactionally. If the LOB is currently NULL, initialize a locator before writing.

### 9.3. WRITE and WRITEAPPEND

- WRITE writes data at a specified offset.
- WRITEAPPEND appends data to the end of the LOB.

Example writing from the beginning:

~~~sql
DBMS_LOB.WRITE(
    lob_loc => l_body,
    amount  => LENGTH(l_text),
    offset  => 1,
    buffer  => l_text
);
~~~

WRITE does not automatically truncate old trailing data beyond the written range. If you want to replace the entire content, TRIM to 0 before writing or replace the LOB with a new value appropriately.

### 9.4. Replacing the Entire Content

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(32767) := 'Replacement content';
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100
    FOR UPDATE;

    IF l_body IS NULL THEN
        UPDATE documents
        SET body = EMPTY_CLOB()
        WHERE document_id = 100
        RETURNING body INTO l_body;
    ELSE
        DBMS_LOB.TRIM(l_body, 0);
    END IF;

    IF l_text IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_text), l_text);
    END IF;
END;
/
~~~

TRIM reduces the LOB length to the specified number of units. For CLOB, length is in characters; for BLOB, in bytes. This example omits COMMIT so the caller controls the transaction.

### 9.5. Writing a BLOB in Bytes

For BLOBs, the buffer is of type RAW. Example with sample byte data:

~~~sql
DECLARE
    l_payload BLOB;
    l_chunk   RAW(32767);
BEGIN
    l_chunk := HEXTORAW('4F5241434C45');

    INSERT INTO documents (title, payload)
    VALUES ('Binary sample', EMPTY_BLOB())
    RETURNING payload INTO l_payload;

    DBMS_LOB.WRITEAPPEND(
        l_payload,
        UTL_RAW.LENGTH(l_chunk),
        l_chunk
    );
END;
/
~~~

Hex 4F5241434C45 represents sample bytes. When processing real files, read bytes from a stream/file; do not assume all binary data can be safely converted through character strings.

## 10. Reading LOBs in Chunks

### 10.1. GETLENGTH

Retrieve LOB length:

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(body) AS body_length
FROM   documents
WHERE  body IS NOT NULL;
~~~

GETLENGTH returns character count for CLOB/NCLOB and byte count for BLOB/BFILE based on the locator type.

### 10.2. SUBSTR

DBMS_LOB.SUBSTR retrieves a portion of the content:

~~~sql
DECLARE
    l_body  CLOB;
    l_piece VARCHAR2(4000);
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    l_piece := DBMS_LOB.SUBSTR(l_body, 1000, 1);

    DBMS_OUTPUT.PUT_LINE(l_piece);
END;
/
~~~

The second parameter is the number of units to read; the third parameter is the starting offset. For CLOB, offset/amount are in characters; for BLOB, in bytes. The returned value is also subject to PL/SQL VARCHAR2/RAW size limits and character sets.

Do not use SUBSTR to load an entire very large LOB into a single VARCHAR2 variable. Read in chunks.

### 10.3. READ

DBMS_LOB.READ reads into a PL/SQL buffer:

~~~sql
DECLARE
    l_body   CLOB;
    l_buffer VARCHAR2(32767);
    l_amount PLS_INTEGER := 1000;
    l_offset PLS_INTEGER := 1;
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    IF l_body IS NOT NULL THEN
        DBMS_LOB.READ(
            lob_loc => l_body,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        DBMS_OUTPUT.PUT_LINE(l_buffer);
    END IF;
END;
/
~~~

READ may adjust amount to reflect the actual quantity of data read. For large LOBs, loop over offsets to process chunks; control buffer size and termination conditions carefully.

### 10.4. Chunk-Reading Loop

~~~sql
DECLARE
    l_body   CLOB;
    l_buffer VARCHAR2(32767);
    l_offset INTEGER := 1;
    l_amount INTEGER;
    l_length INTEGER;
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    IF l_body IS NOT NULL THEN
        l_length := DBMS_LOB.GETLENGTH(l_body);

        WHILE l_offset <= l_length LOOP
            l_amount := LEAST(4000, l_length - l_offset + 1);

            DBMS_LOB.READ(
                l_body,
                l_amount,
                l_offset,
                l_buffer
            );

            -- Process chunk here; printing the entire content is unnecessary.
            l_offset := l_offset + l_amount;
        END LOOP;
    END IF;
END;
/
~~~

In applications, process each chunk and write it to the corresponding stream/file or parser. Avoid concatenating all chunks into a single VARCHAR2 if total content could exceed memory limits.

## 11. Key DBMS_LOB Operations

| API | Purpose |
| --- | --- |
| GETLENGTH | Get LOB length |
| SUBSTR | Extract a portion of a LOB |
| READ | Read a portion into a buffer |
| WRITE | Write at an offset |
| WRITEAPPEND | Append to the end |
| APPEND | Append content from a source LOB |
| COPY | Copy a portion from a source LOB to a destination LOB |
| TRIM | Truncate a LOB to a specified length |
| ERASE | Clear/overwrite a range according to LOB rules |
| INSTR | Search for a string or byte pattern in a LOB |
| COMPARE | Compare LOB contents |
| OPEN/CLOSE | Explicitly open/close a LOB when needed |

### 11.1. APPEND and COPY

APPEND appends the entire content of a source LOB to a destination LOB:

~~~sql
DBMS_LOB.APPEND(
    dest_lob => l_destination,
    src_lob  => l_source
);
~~~

COPY lets you specify the amount and source/destination offsets:

~~~sql
DBMS_LOB.COPY(
    dest_lob    => l_destination,
    src_lob     => l_source,
    amount      => 1000,
    dest_offset => 1,
    src_offset  => 1
);
~~~

Locators must be valid and of compatible LOB types. If you need to create an independent copy, create the destination LOB first and then copy the payload.

### 11.2. Differences Between TRIM and ERASE

- TRIM reduces the length of the LOB from the end.
- ERASE replaces content within a range according to the rules of the LOB type, without necessarily reducing the LOB length.

For BLOBs, the erased region is filled with zero bytes; for CLOBs, it is filled with spaces according to LOB semantics. Verify the API and offset/amount units for your data type before using.

### 11.3. INSTR and COMPARE

INSTR finds the position of a string or byte pattern inside a LOB. COMPARE compares a range of two LOBs. These APIs are useful when you need to search or verify content without transferring the entire LOB to the client.

### 11.4. OPEN and CLOSE

DBMS_LOB.OPEN/CLOSE allows explicitly opening a LOB for a sequence of operations. Not every LOB operation requires calling OPEN first. When explicitly opened, call CLOSE when finished and before ending the transaction per Oracle guidelines, especially if indexes depend on LOB content.

Use an exception handler to ensure the LOB is closed on errors. Do not keep an opened LOB open longer than necessary.

## 12. Temporary LOBs and Resource Cleanup

### 12.1. Creating a Temporary LOB

~~~sql
DECLARE
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp,
        LENGTH('Temporary content'),
        'Temporary content'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_temp)
    );

    DBMS_LOB.FREETEMPORARY(l_temp);
END;
/
~~~

DBMS_LOB.CALL limits the duration to the call; DBMS_LOB.SESSION keeps the temporary LOB in the session until freed or the session ends. Choose the duration based on actual lifecycle, preferring short scopes when possible.

### 12.2. Checking for a Temporary LOB

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_temp);
END IF;
~~~

ISTEMPORARY indicates whether a locator references a temporary LOB. Only call FREETEMPORARY on a valid temporary locator.

### 12.3. Freeing in Exception Handlers

~~~sql
DECLARE
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp,
        LENGTH('Working data'),
        'Working data'
    );

    -- Process data here.

    DBMS_LOB.FREETEMPORARY(l_temp);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_temp);
        END IF;
        RAISE;
END;
/
~~~

In production code, ensure cleanup runs on every exit path. If multiple temporary LOBs exist, manage each locator explicitly. Do not catch an exception and swallow the error just to perform cleanup.

### 12.4. Implicitly Created Temporary LOBs

Some SQL/PLSQL operations on LOBs, such as LOB concatenation or functions returning a LOB, can implicitly create temporary LOBs. Applications need to know when a result is a temporary LOB and free it via the appropriate API if its lifetime outlasts the automatic call scope.

Do not assume every CLOB/BLOB locator is persistent. Use ISTEMPORARY when resource-management code needs to distinguish them.

### 12.5. Connection Pools

With connection pools:
- Do not let SESSION-duration temporary LOBs linger indefinitely on reused connections.
- Free temporary LOBs before returning a connection to the pool.
- Close driver-level stream and locator objects according to their API.
- Do not hold locators across two independent requests.
- Monitor temporary tablespace and session resources under heavy LOB workloads.

## 13. BFILE and Files Outside the Database

### 13.1. Creating a DIRECTORY Object

Example of a DBA creating a directory object:

~~~sql
CREATE DIRECTORY import_files AS '/u01/app/import';
GRANT READ ON DIRECTORY import_files TO app_user;
~~~

The path is a path on the database server, not the client machine. The Oracle database process needs appropriate OS permissions to read the file. A DIRECTORY object does not automatically grant OS permissions.

### 13.2. Creating a BFILE Locator

~~~sql
DECLARE
    l_file BFILE;
BEGIN
    l_file := BFILENAME('IMPORT_FILES', 'sample.bin');

    IF DBMS_LOB.FILEEXISTS(l_file) = 1 THEN
        DBMS_OUTPUT.PUT_LINE(
            'File bytes = ' || DBMS_LOB.GETLENGTH(l_file)
        );
    ELSE
        DBMS_OUTPUT.PUT_LINE('File not found');
    END IF;
END;
/
~~~

BFILENAME creates a locator; it does not read the entire file and does not prove the caller has OS permissions beyond configured database/OS privileges.

### 13.3. Opening, Reading, and Closing a BFILE

~~~sql
DECLARE
    l_file   BFILE;
    l_buffer RAW(32767);
    l_amount BINARY_INTEGER := 100;
BEGIN
    l_file := BFILENAME('IMPORT_FILES', 'sample.bin');

    IF DBMS_LOB.FILEEXISTS(l_file) = 1 THEN
        DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);

        DBMS_LOB.READ(
            lob_loc => l_file,
            amount  => l_amount,
            offset  => 1,
            buffer  => l_buffer
        );

        DBMS_OUTPUT.PUT_LINE(
            'Read bytes = ' || UTL_RAW.LENGTH(l_buffer)
        );

        DBMS_LOB.FILECLOSE(l_file);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

BFILE is read-only. Calling FILECLOSE after reading is an important step to release the file handle.

### 13.4. BFILEs Are Not Included in Database Backups

Because the payload resides on an external file system, database backups do not automatically protect the files. You must:
- Back up the file directory separately.
- Synchronize retention between rows storing locators and the files.
- Check file existence when reading.
- Protect OS and DIRECTORY permissions.
- Have a procedure for handling files renamed or deleted outside the database.

If data must be backed up and recovered together with database transactions, consider storing the content in a BLOB instead of a BFILE.

## 14. Inspecting LOB Metadata

### 14.1. USER_LOBS

View LOB configurations in the current schema:

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       index_name,
       tablespace_name,
       securefile,
       in_row,
       chunk,
       cache,
       logging
FROM   user_lobs
ORDER  BY table_name, column_name;
~~~

Some displayed columns or values depend on the Oracle version and storage type. USER_LOBS helps link a LOB column to its internal segment/index.

### 14.2. DBA_LOBS and ALL_LOBS

- USER_LOBS: LOBs owned by the current schema.
- ALL_LOBS: LOBs accessible to the user.
- DBA_LOBS: LOBs across the entire database, requiring appropriate DBA privileges.

Use the view matching your privilege scope; do not grant DBA privileges just so an application can read metadata.

### 14.3. Segments and Storage Size

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes / 1024 / 1024 AS size_mb
FROM   user_segments
WHERE  segment_type LIKE 'LOB%'
ORDER  BY bytes DESC;
~~~

Allocated segment size does not necessarily equal the sum of currently referenced payload lengths. Deleting or trimming LOBs can create reusable free space within the segment; returning space to the tablespace is a separate administrative task.

### 14.4. LOB Partitions

For partitioned tables, check USER_LOB_PARTITIONS or USER_LOB_SUBPARTITIONS if the release provides the corresponding views. LOB storage can be organized by partition; when adding, exchanging, truncating, or dropping partitions, review both table partition and LOB partition metadata.

## 15. Persistent LOB Lifecycle and Space Reclamation

### 15.1. Creation

Initialize the LOB with EMPTY_CLOB/EMPTY_BLOB, obtain the locator via RETURNING or SELECT FOR UPDATE, and write the payload. NULL and empty LOB have different meanings.

### 15.2. Reading

Retrieve the locator from the row and use GETLENGTH/SUBSTR/READ or driver streams. For large content, read in chunks instead of materializing the entire value in memory.

### 15.3. Updating

You can replace the entire LOB, write at an offset, or append. When writing to an existing row, use appropriate transactions and row locks. When overwriting from the start, remember to handle any old trailing content with TRIM if the new content is shorter.

### 15.4. Deletion

Set the LOB column to NULL or delete the row according to business rules. The data is no longer referenced, but the segment may still retain allocated space for reuse. Do not assume that deleting a row immediately shrinks the datafile.

### 15.5. Space Reclamation

LOB space management depends on BasicFiles/SecureFiles, segments, partitioning, tablespaces, and Oracle version. Before using shrink/move/rebuild, consult the administration documentation and evaluate locks, I/O, duration, and availability. Do not run reclaim operations in production solely because of a segment size number without checking actual usage.

## 16. LOBs in Applications and JDBC

### 16.1. Use Streams Instead of Loading Everything

With Java JDBC:
- CLOB/NCLOB can be read using a character stream.
- BLOB can be read using a binary stream.
- When writing, use character/binary streams or the driver's corresponding LOB API.
- Close the stream when finished.
- Keep the connection valid throughout the entire read/write duration.

Example reading a CLOB:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT body FROM documents WHERE document_id = ?")) {
    ps.setLong(1, 100L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (Reader reader = rs.getCharacterStream("BODY")) {
                char[] buffer = new char[8192];
                int count;

                while ((count = reader.read(buffer)) != -1) {
                    // Process the character chunk just read.
                }
            }
        }
    }
}
~~~

Example reading a BLOB:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT payload FROM documents WHERE document_id = ?")) {
    ps.setLong(1, 100L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (InputStream in = rs.getBinaryStream("PAYLOAD")) {
                byte[] buffer = new byte[8192];
                int count;

                while ((count = in.read(buffer)) != -1) {
                    // Write chunk to file or process binary data.
                }
            }
        }
    }
}
~~~

### 16.2. Locators and Streams Have Lifetimes

Do not return a locator/stream out of the repository layer and immediately close the connection. Drain the stream within a valid connection scope or design a streaming API with clear ownership so the connection is not returned to the pool prematurely.

### 16.3. Do Not Use DBMS_OUTPUT to Transfer Payloads

DBMS_OUTPUT is a text buffer for debugging, not a transport channel for files or large LOBs. Use JDBC streams, REST streaming, object storage, or an appropriate file transfer mechanism.

## 17. Performance and Selection Guidelines

### 17.1. Choose In-Row/Out-of-Row Based on Access Patterns

Ask:
- Are LOBs usually small or large?
- Do table queries usually read the LOB?
- Are there many queries that read only metadata without reading the payload?
- Does the application read the whole LOB or piecewise?
- Are many rows packed into the same block?
- Are LOBs updated frequently?

In-row can reduce access steps for small LOBs. Out-of-row can keep rows compact when payloads are large or rarely read.

### 17.2. Choose CACHE/NOCACHE Based on Workload

Measure re-read rates, working set, and buffer cache pressure. CACHE can help for frequently read content; NOCACHE can suit large payloads with low reuse. No single option is right for every table.

### 17.3. Avoid Overly Small Round-Trips

Reading a LOB in overly small chunks increases the number of API calls/round-trips. Overly large chunks increase memory footprint. Choose chunk size based on driver, network, memory, and measured throughput.

### 17.4. Avoid Printing or Converting Entire LOBs

DBMS_OUTPUT, VARCHAR2, and text logs are not suitable places to hold entire large files. Only read the needed slice or stream directly to the consumer.

### 17.5. Measure Before Changing Storage

Changing SecureFiles, compression, deduplication, caching, or in-row policies can impact CPU, I/O, storage space, and latency. Use representative data, measure both reads and writes, and verify backup/recovery before deploying.

## 18. Common Errors and Misconceptions

**“A LOB locator is the LOB content itself.”** No. A locator is a reference; the payload may be stored elsewhere.

**“Out-of-row means the locator is not in the row.”** No. The row still stores the locator; the payload resides in the LOB segment.

**“CLOB and BLOB use offsets in the same unit.”** No. CLOB/NCLOB use character units in the API; BLOB uses bytes.

**“NULL and EMPTY_CLOB are the same.”** No. NULL has no locator to operate on; EMPTY_CLOB creates an initialized empty LOB.

**“Assigning a locator to another variable copies the content.”** Do not assume that. Use DBMS_LOB.COPY/APPEND to copy payloads.

**“DBMS_LOB.WRITE overwrites and automatically truncates the old tail.”** No. If replacing the entire content, consider TRIM or replacing the LOB value.

**“Temporary LOBs disappear immediately when unused.”** Do not rely on that assumption. Choose duration and free explicitly with FREETEMPORARY.

**“BFILE is a BLOB with a path.”** No. BFILE is an external, read-only locator, and the file is not included in database backups.

**“In-row is always faster.”** No. Larger rows can reduce block density and increase cost for queries that do not need the LOB.

**“Out-of-row is always better for large LOBs.”** You cannot conclude this from size alone; access patterns and storage layout matter too.

**“Deleting a LOB immediately shrinks the datafile.”** No. The segment may retain space for reuse; reclamation is a separate administrative task.

**“DBMS_LOB.OPEN is always required.”** No. Only use explicit OPEN/CLOSE when needed; if opened, close properly.

## 19. Practice Exercises

Exercises use a learning schema. Adjust tablespaces and privileges for your environment.

### Exercise 1 — Create a CLOB/BLOB Table

Create a DOCUMENTS table with CLOB and BLOB columns. Identify which column holds text and which holds bytes.

### Exercise 2 — Compare NULL and EMPTY_CLOB

Insert one row with BODY as NULL and one row with EMPTY_CLOB. Use IS NULL and DBMS_LOB.GETLENGTH to compare them.

### Exercise 3 — Write a CLOB Using RETURNING

Insert EMPTY_CLOB, retrieve the locator with RETURNING INTO, and use WRITEAPPEND to write content. Commit and read back the length.

### Exercise 4 — Write a BLOB

Create an empty BLOB and write a RAW chunk. Check the length with GETLENGTH.

### Exercise 5 — Read a CLOB in Chunks

Use DBMS_LOB.READ in a loop. Record the offset and amount of each read.

### Exercise 6 — Replace with Shorter Content

Write a long string, then replace it with a shorter string. Compare the result of only calling WRITE from offset 1 versus calling TRIM to 0 before writing.

### Exercise 7 — Copy a LOB

Create a destination LOB and use DBMS_LOB.COPY to copy part of a source LOB. Compare GETLENGTH and COMPARE.

### Exercise 8 — Temporary LOB

Create a temporary CLOB with CALL duration, write data, verify ISTEMPORARY, and call FREETEMPORARY. Test adding an exception to verify cleanup.

### Exercise 9 — In-Row and Out-of-Row

Create two tables with ENABLE STORAGE IN ROW and DISABLE STORAGE IN ROW. Load small and large LOBs, then inspect metadata and segments. Do not draw conclusions from a single row.

### Exercise 10 — SecureFiles and BasicFiles

Create two demo tables using the storage types supported by your environment. Compare USER_LOBS, segments, and configuration options. Check ASSM and compatibility before creating SecureFiles.

### Exercise 11 — BFILE

Have a DBA create a DIRECTORY object, grant READ to the test schema, create a BFILE locator, and read a portion of the file. Close the file in both success and exception paths.

### Exercise 12 — JDBC Streaming

Write Java code to read a CLOB using Reader and a BLOB using InputStream. Ensure streams are closed before the connection is returned to the pool.

### Exercise 13 — Monitor Storage Usage

Query USER_LOBS and USER_SEGMENTS. Compare segment size with the total length of currently referenced LOBs; explain why the two numbers do not necessarily match.

### Exercise 14 — Lifecycle Planning

Design a workflow for uploading, reading, updating, deleting, and backing up a large document. Clearly state where the payload is stored, who owns the locator/stream, and when each resource is freed.

## 20. Oracle Reference Documentation

- [Oracle Database SecureFiles and Large Objects Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/): LOB locators, storage, SecureFiles, BasicFiles, and working with LOBs.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html): READ, WRITE, WRITEAPPEND, COPY, APPEND, TRIM, OPEN/CLOSE, and temporary LOBs.
- [Oracle Database SQL Language Reference — LOB Storage Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LOB-storage-clause.html): ENABLE/DISABLE STORAGE IN ROW and LOB storage configuration.
- [Oracle Database Reference — USER_LOBS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_LOBS.html): metadata of LOB columns in the schema.
- [Oracle Database Reference — USER_SEGMENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_SEGMENTS.html): segment sizes.
- [Oracle Database SQL Language Reference — CREATE DIRECTORY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-DIRECTORY.html): directory objects used with BFILE.

A LOB locator is a reference that enables accessing large content without loading the entire payload into a single string variable. For internal LOBs, the locator resides in the row while the payload can be in-row or out-of-row; BasicFiles and SecureFiles differ in storage models and capabilities. Distinguish persistent LOBs, temporary LOBs, and BFILEs, use DBMS_LOB to read/write in chunks, free temporary LOBs, and close BFILEs/streams properly along their lifecycle. **Good LOB design must account for payload location, access patterns, transactions, connections, and resources requiring reclamation.**
