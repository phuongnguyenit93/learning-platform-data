# Streaming Large Data Instead of Loading Everything into Application Memory

When an application reads or writes files, images, videos, documents, large JSON, or long text data in Oracle Database, loading the entire content into a variable or byte array can cause memory usage to grow with the data size. If many requests run concurrently, the application may run out of heap, experience increased garbage collection, slow down, or run out of memory.

Streaming processes data in small, bounded chunks. The application reads a chunk from the source, transfers that chunk to the destination, and continues until all data is consumed. Memory used for the content is typically proportional to the buffer size rather than the entire LOB size.

In Oracle, common large data types are:

- BLOB: binary data such as images, PDFs, compressed files, and media content.
- CLOB: large character data using the database character set.
- NCLOB: large character data using the national character set.
- BFILE: a locator to an external binary file outside the database, read by Oracle according to directory object privileges and read-only through the LOB mechanism.

For effective streaming, three layers must work together: how Oracle stores the LOB, how the driver provides the LOB locator/stream, and how the application transfers data in chunks. Simply replacing a large byte array with a large string still loads all data into memory.

## 1. Why Shouldn't You Load the Entire LOB into Memory?

Suppose an application downloads a 500 MB BLOB file. If the code calls an API that returns the entire content as a byte array, the heap needs to hold at least about 500 MB for that array, not counting objects, intermediate buffers, copies during processing, and memory for other requests.

If there are 20 concurrent requests, the content alone could require around 10 GB if each request holds the full 500 MB.

With streaming, each request might only need a 64 KB or 256 KB buffer:

| Approach | Memory for content of one request |
|---|---:|
| Reading the entire 500 MB file into a byte array | Approximately 500 MB or more |
| Streaming with a 64 KB buffer | Approximately 64 KB plus overhead |
| Streaming with a 256 KB buffer | Approximately 256 KB plus overhead |

These are conceptual estimates. Drivers, frameworks, compression, TLS, and other buffers also consume memory. However, streaming bounds memory by configuration rather than by file size.

### 1.1 Memory Formula with Concurrent Requests

If each request uses a buffer B and there are N requests currently streaming, buffer memory is approximately:

~~~text
Memory for buffers ≈ N × B
~~~

For example, 100 requests × 64 KB ≈ 6.4 MB for application buffers. Actual usage will be higher because each stream also involves objects, driver buffers, connections, TLS, and framework overhead.

If each request kept the entire 500 MB file, 100 requests could require around 50 GB for the content alone.

### 1.2 Streaming Does Not Mean Data Is Unbuffered

Streaming still requires buffers at multiple layers:

- Application buffers.
- JDBC driver buffers.
- Network/socket buffers.
- Oracle and operating system buffers.
- HTTP server or client buffers.

The goal is to control buffer capacity and avoid materializing the entire content. You do not need to eliminate all buffering; you need to avoid memory growing unboundedly with data size.

## 2. Understanding LOB Locators Before Reading Data

A LOB column is not simply a long VARCHAR2 value. Oracle manages LOBs using a locator and its corresponding LOB storage area.

A LOB locator is a reference that allows a program to access LOB content. When querying a BLOB/CLOB column, the driver can return a locator or an object representing the LOB; the content can then be read incrementally through a stream.

Example table storing documents:

~~~sql
CREATE TABLE documents (
    document_id   NUMBER PRIMARY KEY,
    file_name     VARCHAR2(255 CHAR) NOT NULL,
    content_type  VARCHAR2(100 CHAR),
    payload       BLOB,
    text_content  CLOB,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);
~~~

In the application:

- Obtaining a BLOB/CLOB object does not mean fetching the entire content into a byte array/String.
- Use getBinaryStream or getCharacterStream to read content as a stream.
- Keep the connection, statement, and result set open while the stream is being consumed.
- Do not keep a locator or stream longer than the connection/transaction lifecycle required by the driver.

### 2.1 Locator vs. Content

| Object | Role |
|---|---|
| BLOB/CLOB column | Stores LOB content in the database |
| LOB locator | Reference to the LOB for reading/writing |
| InputStream | Reads binary data in chunks |
| Reader | Reads character data in chunks |
| OutputStream | Writes binary data in chunks |
| Writer | Writes character data in chunks |

Do not assume that calling getBlob or getClob always materializes the entire LOB. Usually, the returned object is a locator. What you must avoid is calling APIs such as getBytes for the entire BLOB or getSubString for the entire CLOB and holding large results in the heap.

## 3. Choosing the Right LOB Type

### 3.1 BLOB

BLOB is used for binary content:

- Images.
- PDFs.
- Video/audio.
- ZIP files.
- Office files.
- Binary payloads.

BLOB does not interpret character encoding. The application must track the file format and content type itself.

### 3.2 CLOB

CLOB is used for large text in the database character set:

- Article content.
- Text documents.
- Text-based XML/JSON.
- HTML content.
- Multilingual text.

CLOB stores characters, not raw file bytes. When reading/writing via JDBC, use Reader/Writer so the driver handles character set conversion.

### 3.3 NCLOB

NCLOB uses the national character set. Only choose it when the schema and character set requirements truly require this type. In many systems using AL32UTF8 as the database character set, CLOB already supports full Unicode.

### 3.4 BFILE

BFILE is a locator to a binary file on the database server filesystem via a DIRECTORY object. Oracle can read a BFILE but cannot write content to that file through the BFILE locator.

How BFILE differs from BLOB:

- BLOB is stored inside the database.
- BFILE points to a file outside the database.
- BFILE requires a DIRECTORY object and corresponding privileges.
- A BFILE can be modified outside the database, so its content is not transactionally managed like a BLOB.

### 3.5 Do Not Use VARCHAR2 to Store Large Files

VARCHAR2 in PL/SQL and SQL has its own length limits; it does not replace BLOB/CLOB for large content. Use a LOB when data exceeds the suitable range of regular string types or requires stream operations.

## 4. Anti-Pattern Against Streaming: Materializing All Data

In JDBC, a convenient approach to write—but unsuitable for very large LOBs—is:

~~~java
Blob blob = resultSet.getBlob("payload");
long length = blob.length();
byte[] bytes = blob.getBytes(1, (int) length);
~~~

getBytes returns a byte array. The entire requested portion of data must fit in application memory. Casting length to int also risks overflow for data larger than the int limit.

With CLOB:

~~~java
Clob clob = resultSet.getClob("text_content");
long length = clob.length();
String text = clob.getSubString(1, (int) length);
~~~

getSubString returns a large String. This is still full-content materialization.

The following APIs typically materialize data in memory:

- Blob.getBytes(pos, length).
- Clob.getSubString(pos, length).
- InputStream.readAllBytes().
- Files.readAllBytes().
- Reader reading everything into a StringBuilder/String.
- Converting an entire BLOB into a Base64 String.

Streaming APIs:

- ResultSet.getBinaryStream().
- ResultSet.getCharacterStream().
- Blob.getBinaryStream().
- Clob.getCharacterStream().
- PreparedStatement.setBinaryStream().
- PreparedStatement.setCharacterStream().
- Blob.setBinaryStream().
- Clob.setCharacterStream() if supported by the driver.

## 5. Reading a BLOB Using JDBC InputStream

Example of downloading a BLOB from Oracle to a file without creating a full byte array:

~~~java
String sql = """
    SELECT payload
    FROM documents
    WHERE document_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new IllegalArgumentException("Document not found");
        }

        try (InputStream input = resultSet.getBinaryStream("payload");
             OutputStream output = Files.newOutputStream(destination)) {

            byte[] buffer = new byte[64 * 1024];
            int count;

            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        }
    }
}
~~~

Processing flow:

1. Query only the needed row.
2. Obtain an InputStream from the BLOB column.
3. Read up to 64 KB per iteration.
4. Write the chunk to the destination file.
5. Loop until EOF.
6. Close the stream, ResultSet, Statement, and Connection in lifecycle order.

The 64 KB size is an example, not the optimal value for every application. You can benchmark 32 KB, 64 KB, 128 KB, or 256 KB.

### 5.1 Keep ResultSet and Connection Open While Streaming

Do not do the following:

~~~java
InputStream input;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet resultSet = statement.executeQuery()) {

    resultSet.next();
    input = resultSet.getBinaryStream(1);
}

// Do not continue reading here:
// ResultSet/Statement/Connection are already closed.
~~~

The stream/LOB locator may depend on the connection and ResultSet. Finish reading before closing the resources that own it, unless the driver/framework has a clearly documented materialization or detach mechanism.

### 5.2 Checking for NULL LOB

If the BLOB column is NULL, getBinaryStream may return NULL. You must handle that case:

~~~java
InputStream input = resultSet.getBinaryStream("payload");
if (input == null) {
    throw new IllegalStateException("Document has no payload");
}
~~~

Distinguish between:

- No row: resultSet.next() returns false.
- Row exists but LOB is NULL: the stream may be null.
- Row exists and LOB is empty: the LOB exists but its length is 0.

These three states have different business meanings.

## 6. Reading a CLOB Using JDBC Reader

CLOB is character data, so use Reader instead of InputStream when the application needs text content:

~~~java
String sql = """
    SELECT text_content
    FROM documents
    WHERE document_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new IllegalArgumentException("Document not found");
        }

        try (Reader reader = resultSet.getCharacterStream("text_content");
             Writer writer = Files.newBufferedWriter(
                 destination,
                 StandardCharsets.UTF_8
             )) {

            char[] buffer = new char[8 * 1024];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                writer.write(buffer, 0, count);
            }
        }
    }
}
~~~

Reader returns character data. Writer writes to a UTF-8 file in this example. Oracle JDBC performs character set conversion from the CLOB to the Java character stream; do not manually convert a CLOB into a byte array.

### 6.1 Do Not Confuse Byte Length with Character Length

For BLOB:

- Length is typically measured in bytes.
- InputStream/OutputStream transfer bytes.

For CLOB:

- LOB length and offsets in LOB APIs are measured in character units according to CLOB rules.
- Reader/Writer transfer characters.
- The byte count of a UTF-8 file after encoding may differ from the character count.

Do not use the byte length of a UTF-8 file as the character count when calling CLOB APIs. Conversely, do not use the character count as the byte length of a BLOB.

### 6.2 Unicode and Surrogate Pairs

Java String/Reader work with UTF-16 code units; some Unicode code points outside the Basic Multilingual Plane are represented by surrogate pairs. Reader handles the character stream and JDBC performs the encoding conversion. Avoid manually slicing strings by bytes or splitting a surrogate pair in the middle of a chunk.

When processing characters yourself, use Reader/Writer and let them manage buffer boundaries. When converting to bytes, use an explicit charset, such as UTF-8.

## 7. Uploading a BLOB Using PreparedStatement.setBinaryStream

If the application receives a file from a client or the filesystem, you can bind an InputStream directly to the BLOB:

~~~java
String sql = """
    INSERT INTO documents (
        document_id,
        file_name,
        content_type,
        payload
    )
    VALUES (?, ?, ?, ?)
    """;

long fileSize = Files.size(source);

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (InputStream input = Files.newInputStream(source);
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, fileName);
        statement.setString(3, contentType);
        statement.setBinaryStream(4, input, fileSize);

        statement.executeUpdate();
        connection.commit();
    } catch (SQLException | IOException error) {
        connection.rollback();
        throw error;
    }
}
~~~

setBinaryStream passes the byte stream to the JDBC driver. The overload accepting length uses the long type in modern JDBC. Check the JDBC driver version and supported APIs in the target application; some older environments only have the int overload or require a length.

### 7.1 Uploading When Length Is Unknown Ahead of Time

Modern JDBC has an overload that does not require declaring the length:

~~~java
statement.setBinaryStream(4, input);
~~~

The driver reads the stream until EOF per the JDBC contract. Verify support in your driver and enforce upload limits at the application layer. Never trust a request to send an unbounded amount of data.

### 7.2 Using a Stream from an HTTP Request

In web applications, you can obtain an InputStream from a multipart upload and bind it directly to a PreparedStatement. Avoid calling APIs that read the entire multipart into a byte array before saving.

Flow:

~~~text
HTTP request body
       |
       v
Multipart InputStream
       |
       v
JDBC setBinaryStream
       |
       v
Oracle BLOB
~~~

Limit upload sizes, and validate permissions, content type, checksum, and processing time. Reading a stream directly does not replace file safety checks.

## 8. Uploading a CLOB Using Reader

If the source is a UTF-8 text file, open a Reader with an explicit charset:

~~~java
String sql = """
    INSERT INTO documents (
        document_id,
        file_name,
        text_content
    )
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (Reader reader = Files.newBufferedReader(
             source,
             StandardCharsets.UTF_8
         );
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, fileName);
        statement.setCharacterStream(3, reader);

        statement.executeUpdate();
        connection.commit();
    } catch (SQLException | IOException error) {
        connection.rollback();
        throw error;
    }
}
~~~

setCharacterStream passes characters to the CLOB. The driver converts from Java character data to the database character set.

### 8.1 Do Not Use setString for Very Large Text

setString accepts a String that is already in the heap. If the application has already read the entire file into a String, streaming is lost before JDBC is even called.

For large CLOBs, create a Reader from the source and use setCharacterStream. For small data, setString can be simpler and more appropriate; choose based on actual size and limits.

## 9. Uploading with a LOB Locator and SELECT FOR UPDATE

Another approach is to create the row with EMPTY_BLOB/EMPTY_CLOB, fetch the locator, and write a stream to the locator.

SQL to create the row:

~~~sql
INSERT INTO documents (
    document_id,
    file_name,
    payload
)
VALUES (
    :document_id,
    :file_name,
    EMPTY_BLOB()
);
~~~

Then query the locator to update:

~~~sql
SELECT payload
FROM documents
WHERE document_id = :document_id
FOR UPDATE;
~~~

In JDBC, obtain the Blob and use setBinaryStream on the locator:

~~~java
connection.setAutoCommit(false);

try (PreparedStatement statement = connection.prepareStatement(
         "SELECT payload FROM documents WHERE document_id = ? FOR UPDATE"
     )) {
    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new IllegalArgumentException("Document not found");
        }

        Blob blob = resultSet.getBlob(1);
        try (InputStream input = Files.newInputStream(source);
             OutputStream output = blob.setBinaryStream(1)) {

            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        } finally {
            blob.free();
        }
    }
}

connection.commit();
~~~

This example illustrates locator-based writes. Verify Oracle JDBC driver support for Blob.setBinaryStream and how locators are managed on the version you use. The row must be locked with FOR UPDATE while updating the LOB; the transaction must remain open until writing completes and commits.

For many applications, binding the stream directly with setBinaryStream in INSERT/UPDATE is simpler. Locator-based writes are useful when you need to manipulate an existing LOB or use the LOB object API.

## 10. Writing and Reading LOBs in PL/SQL in Chunks

In PL/SQL, you can use DBMS_LOB.READ to read a portion of a LOB and DBMS_LOB.WRITE/WRITEAPPEND to write in chunks.

### 10.1 Reading a BLOB with DBMS_LOB.READ

~~~sql
DECLARE
    l_blob    BLOB;
    l_length  INTEGER;
    l_offset  INTEGER := 1;
    l_amount  INTEGER;
    l_buffer  RAW(32767);
BEGIN
    SELECT payload
    INTO l_blob
    FROM documents
    WHERE document_id = 1001;

    l_length := DBMS_LOB.GETLENGTH(l_blob);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);

        DBMS_LOB.READ(
            lob_loc => l_blob,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        -- Process the chunk in l_buffer here.
        -- l_amount is the actual number of bytes read.

        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

Characteristics:

- BLOB offsets are measured in bytes and start at 1.
- BLOB amounts are measured in bytes.
- RAW in PL/SQL has a maximum limit of 32,767 bytes.
- Do not increment the offset by a fixed buffer size if the final read returns fewer bytes; use the actual amount.

### 10.2 Reading a CLOB with DBMS_LOB.READ

~~~sql
DECLARE
    l_clob    CLOB;
    l_length  INTEGER;
    l_offset  INTEGER := 1;
    l_amount  INTEGER;
    l_buffer  VARCHAR2(8000);
BEGIN
    SELECT text_content
    INTO l_clob
    FROM documents
    WHERE document_id = 1001;

    l_length := DBMS_LOB.GETLENGTH(l_clob);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(8000, l_length - l_offset + 1);

        DBMS_LOB.READ(
            lob_loc => l_clob,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        -- Process the character chunk in l_buffer here.

        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

For CLOB:

- Offset and amount are measured in characters.
- The buffer is VARCHAR2.
- Buffer size is measured in bytes and subject to PL/SQL limits; choose an amount small enough for multi-byte character sets.
- DBMS_LOB.READ may adjust amount to the actual number of characters read.

The value 8,000 in this example is a conservative chunk size for a VARCHAR2 buffer; consider the character set and actual content.

### 10.3 DBMS_LOB.SUBSTR Is Not a Way to Load an Entire LOB

DBMS_LOB.SUBSTR returns a portion of a LOB within the buffer size limit of its return type. It is useful for small text snippets or displaying a preview, not suitable for fetching an entire large LOB into a single VARCHAR2/RAW.

If you need to process the entire dataset, use a chunk loop with DBMS_LOB.READ or stream via the driver.

## 11. Writing a BLOB in Chunks in PL/SQL

You can initialize an empty BLOB and write in chunks:

~~~sql
DECLARE
    l_blob    BLOB;
    l_chunk   RAW(32767);
    l_amount  PLS_INTEGER;
BEGIN
    INSERT INTO documents(document_id, file_name, payload)
    VALUES (2001, 'sample.bin', EMPTY_BLOB())
    RETURNING payload INTO l_blob;

    -- Example binary data chunk.
    l_chunk := HEXTORAW('010203040506');
    l_amount := UTL_RAW.LENGTH(l_chunk);

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_blob,
        amount  => l_amount,
        buffer  => l_chunk
    );

    -- Write subsequent chunks the same way.
    COMMIT;
END;
/
~~~

WRITEAPPEND appends the buffer to the end of the LOB. For BLOB, amount is the number of bytes. For CLOB, amount is the number of characters.

### 11.1 Writing at an Offset

DBMS_LOB.WRITE writes data at a specified position:

~~~sql
DBMS_LOB.WRITE(
    lob_loc => l_blob,
    amount  => UTL_RAW.LENGTH(l_chunk),
    offset  => 1,
    buffer  => l_chunk
);
~~~

LOB offsets start at 1. WRITE can overwrite an existing region or extend the LOB depending on the position and content.

### 11.2 Do Not Assemble the Entire BLOB into RAW

Do not create a huge RAW or concatenate all chunks into one variable to write once at the end. That reverts to materialization and hits PL/SQL variable size limits.

Read/receive a chunk, process the chunk, write the chunk, and release the reference to the chunk before handling the next part.

## 12. Writing a CLOB in Chunks in PL/SQL

Example of creating an empty CLOB and appending text:

~~~sql
DECLARE
    l_clob   CLOB;
    l_chunk  VARCHAR2(8000);
BEGIN
    INSERT INTO documents(document_id, file_name, text_content)
    VALUES (2002, 'notes.txt', EMPTY_CLOB())
    RETURNING text_content INTO l_clob;

    l_chunk := 'First text segment';
    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_clob,
        amount  => LENGTH(l_chunk),
        buffer  => l_chunk
    );

    l_chunk := 'Second text segment';
    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_clob,
        amount  => LENGTH(l_chunk),
        buffer  => l_chunk
    );

    COMMIT;
END;
/
~~~

For CLOB, amount is the number of characters in the buffer, not LENGTHB. If the data has multiple bytes per character, do not replace LENGTH with LENGTHB.

## 13. Temporary LOBs

PL/SQL can create temporary LOBs using DBMS_LOB.CREATETEMPORARY:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    lob_loc => l_temp_clob,
    cache   => TRUE,
    dur     => DBMS_LOB.CALL
);
~~~

Temporary LOBs are useful when you need to build large content in the database's LOB memory before writing or returning results.

### 13.1 Temporary LOB Lifecycle

Typical steps:

1. Declare the locator.
2. Call CREATETEMPORARY.
3. Write or append chunks.
4. Use the LOB in SQL statements or further processing.
5. Call FREETEMPORARY when no longer needed.

Example:

~~~sql
DECLARE
    l_temp_clob CLOB;
    l_chunk     VARCHAR2(4000);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    l_chunk := 'Header text';
    DBMS_LOB.WRITEAPPEND(
        l_temp_clob,
        LENGTH(l_chunk),
        l_chunk
    );

    -- Use l_temp_clob for the required operation.

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

FREETEMPORARY frees temporary LOB resources. Do not leave temporary LOBs alive longer than necessary, especially in long-running sessions or when handling many requests.

### 13.2 CALL and SESSION Duration

DBMS_LOB.CALL creates a temporary LOB scoped to the PL/SQL call; DBMS_LOB.SESSION keeps the temporary LOB within the session scope until freed or the session ends.

Choose the appropriate duration:

- CALL when the LOB is only used within a single call.
- SESSION when it must be shared across multiple calls in the same session with clear lifecycle management.

Do not choose SESSION merely for convenience; make sure to call FREETEMPORARY promptly.

### 13.3 Temporary LOBs Still Consume Resources

A temporary LOB is not free memory. It can use temporary tablespace, cache, and session resources. Monitor temporary LOB usage and ensure cleanup on both success and exception paths.

## 14. Transactions, Row Locks, and LOB Stream Lifetime

Reading LOBs:

- Execute SELECT and consume the stream while the connection/result set is still open.
- Do not return an InputStream out of the repository layer if upper layers will use it after the connection has been returned to the pool.
- Avoid committing or closing the connection before the stream finishes.

Writing LOBs:

- When updating a locator, SELECT ... FOR UPDATE is typically required.
- Keep the transaction open throughout the write process.
- Close the stream before COMMIT.
- Roll back on error according to the transaction contract.

### 14.1 Long Streams Hold Connections Long

Streaming 2 GB over a slow network can hold a database connection for a long time. This affects the connection pool:

- One request occupies a connection until reading completes.
- Slow clients cause connections to be held longer.
- Many concurrent downloads can exhaust the pool.
- Transactions/row locks in write scenarios may persist longer than desired.

For downloads, avoid holding write transactions or unnecessary row locks. For uploads via SELECT FOR UPDATE, bound the upload time and consider staging so rows are not locked for too long.

### 14.2 Do Not Close the Stream Too Early

The driver may read data from the database when the application calls read, rather than loading everything at getBinaryStream time. Therefore, the connection, statement, and result set must remain valid throughout the streaming process.

### 14.3 Connection Pool and HTTP Streaming

If HTTP clients download very slowly, the servlet can hold database connections for a long time. Some architectures can:

- Stream directly if size and duration are controlled.
- Use asynchronous responses while still clearly managing connection/LOB lifetimes.
- Copy to object storage or staging files via a controlled process, then serve files from storage.
- Use time-limited download URLs if the storage system supports them.

You cannot close the connection and then continue reading the locator arbitrarily.

## 15. Backpressure and Bounded Buffers

Good streaming respects the speed of the receiver. If the source reads faster than the destination writes, the application should not accumulate chunks indefinitely in a queue.

Example flow:

~~~text
Oracle LOB stream
       |
       v
Fixed-size read buffer
       |
       v
Application processing
       |
       v
HTTP/file/object-storage output
~~~

Each step requests the next chunk only after the previous step has processed enough. This is application-level backpressure.

### 15.1 Unbounded Queues Defeat Streaming

If code continuously reads from Oracle and pushes chunks into an unbounded queue while network output is slow, memory still grows with total data size.

Use a bounded queue and a producer-consumer mechanism with backpressure. Do not spawn a separate thread per chunk without good reason and concurrency limits.

### 15.2 Choosing Buffer Size

Small buffer:

- Reduces memory per request.
- Increases the number of read/write calls and function call overhead.

Large buffer:

- Reduces call count.
- Increases memory per request.
- May not improve throughput if the bottleneck is in the network/storage.

Test with several reasonable sizes. Measure throughput, latency, CPU, heap, GC, and concurrent requests. Choose the buffer based on the service's overall memory budget.

## 16. Streaming a BLOB from Oracle to an HTTP Response

A download endpoint can read a BLOB directly and write to the response output stream:

~~~java
String sql = """
    SELECT file_name, content_type, payload
    FROM documents
    WHERE document_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            response.sendError(404);
            return;
        }

        String fileName = resultSet.getString("file_name");
        String contentType = resultSet.getString("content_type");
        InputStream input = resultSet.getBinaryStream("payload");

        if (input == null) {
            response.sendError(404);
            return;
        }

        response.setContentType(
            contentType != null ? contentType : "application/octet-stream"
        );
        response.setHeader(
            "Content-Disposition",
            buildSafeAttachmentHeader(fileName)
        );

        try (InputStream in = input) {
            OutputStream out = response.getOutputStream();
            byte[] buffer = new byte[64 * 1024];
            int count;

            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }

            out.flush();
        }
    }
}
~~~

buildSafeAttachmentHeader is an application helper that must be implemented safely, handling filenames per HTTP header rules and preventing CR/LF injection. The example only illustrates the streaming flow; how the response stream is closed depends on the servlet container/framework that owns the output stream.

### 16.1 Do Not Guess Content-Length

If the exact BLOB length is known, you can obtain the length from metadata/LOB locator before streaming. Otherwise, let the HTTP server use chunked transfer or the framework's streaming mechanism.

Do not read the entire BLOB just to compute Content-Length. Do not cast long to int if the size can exceed the int range.

### 16.2 Client Disconnection

If the client cancels the download, writing to the response may throw an IOException. Stop reading the LOB, close the stream, and return the connection to the pool. Do not continue reading the entire LOB after the destination has closed.

### 16.3 Range Requests

If you need to support HTTP Range for large files, the application must read the exact byte range:

- Validate the range.
- Determine offset and length in byte units.
- Use an API that supports reading a LOB slice or appropriate seeking.
- Return the accurate status and Content-Range header.
- Do not use CLOB character offsets for BLOB byte ranges.

Range requests are a separate feature requiring testing; streaming alone does not automatically enable resume support.

## 17. Streaming a CLOB to an HTTP Response

CLOB is text. When sending over HTTP, specify the charset and content type:

~~~java
response.setContentType("text/plain; charset=UTF-8");

try (Reader reader = resultSet.getCharacterStream("text_content")) {
    Writer writer = response.getWriter();
    char[] buffer = new char[8 * 1024];
    int count;

    while ((count = reader.read(buffer)) != -1) {
        writer.write(buffer, 0, count);
    }

    writer.flush();
}
~~~

Do not call getSubString to create a full String before writing the response. Also do not use the CLOB's byte count as its character count.

If the CLOB contains HTML, JSON, or XML, define the content type, encoding, and escaping/validation policies. Streaming does not automatically guarantee content is safe when rendered in a browser.

## 18. LOB Prefetch and ResultSet Fetch Size

JDBC has fetch size to hint how many rows to retrieve per trip from the database:

~~~java
statement.setFetchSize(100);
~~~

Fetch size tunes retrieving multiple rows in a ResultSet. It does not mean the entire LOB of each row is read incrementally or capped at 100 rows × a fixed buffer.

Distinguish:

- Fetch size: the number of rows the driver fetches in batches.
- LOB stream: how BLOB/CLOB content is read.
- LOB prefetch: some Oracle drivers can prefetch metadata or a small portion of a LOB to reduce round trips.

LOB prefetch is a driver-specific option and can increase memory if set too high. Check the Oracle JDBC documentation for your exact version and measure with realistic LOB sizes.

When reading multiple rows containing LOBs:

- Set a fetch size appropriate for the row count.
- Only SELECT the LOB when the content is actually needed.
- Read and close one row's stream before advancing to the next row if required by the driver.
- Do not hold multiple locators/streams simultaneously unless necessary.

## 19. Processing Data Chunk by Chunk in the Application

A streaming pipeline can perform per-chunk processing:

- Computing checksums.
- Counting bytes.
- Compressing or decompressing.
- Encrypting/decrypting.
- Converting encodings.
- Writing to files or object storage.

Example of computing SHA-256 while copying a BLOB:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");

try (InputStream input = resultSet.getBinaryStream("payload");
     OutputStream output = Files.newOutputStream(destination)) {

    byte[] buffer = new byte[64 * 1024];
    int count;

    while ((count = input.read(buffer)) != -1) {
        digest.update(buffer, 0, count);
        output.write(buffer, 0, count);
    }
}

byte[] checksum = digest.digest();
~~~

The checksum is computed incrementally without holding the entire content. You can compare it against a stored checksum to detect corrupted transfers.

### 19.1 Compression and Encryption

Stream wrappers such as GZIPOutputStream or CipherOutputStream can be chained into the pipeline. Define the compression/encryption order:

- On upload: source → compress (if needed) → encrypt (if needed) → database.
- On download: database → decrypt → decompress → destination.

The order must match the stored format. Do not overwrite the original content type or original size with inaccurate metadata after compression/encryption.

### 19.2 Validating Input Data

Streaming does not replace validation:

- Maximum size.
- Actual MIME type and file signature.
- Filename and path.
- Virus/malware scan per policy.
- Checksum.
- User permissions for the document ID.
- Text/HTML content when displaying.

You can validate the signature on the first chunk and continue copying. If full-file scanning is required, use a streaming pipeline or bounded staging.

## 20. Storing Large Files in Oracle or Object Storage?

Not every large file should be stored in a BLOB. Consider:

| Criterion | BLOB in Oracle | Object/file storage |
|---|---|---|
| Transactions with business data | Can share the same transaction | Usually requires outbox/saga or two-step flow |
| Backup/restore | Follows database policy | Follows separate storage policy |
| Streaming | JDBC LOB stream | SDK/file stream |
| Metadata management | SQL and constraints | Usually via database + object metadata |
| Very large files, high volume | Can increase database storage/backup size | May fit better depending on architecture |
| Access control | Database authorization | IAM/presigned URL/ACL |
| Cost | Database storage and I/O | Storage/network/egress |

If the file is part of business data requiring atomicity with the row, BLOB may fit. If files are huge, high-volume, or need CDN/distributed downloads, object storage may be more suitable.

There is no single choice for every system. Factor in transaction consistency, cost, retention, backup, compliance, and access patterns.

### 20.1 Pattern: Metadata in Database, File in Object Storage

A common pattern:

1. Create document metadata in PENDING state.
2. Stream upload to object storage with a unique object key.
3. Verify checksum/size.
4. Update metadata to READY.
5. If upload fails, clean up the temporary object and update error state.

Because the database and object storage do not share an ACID transaction, you need idempotency, retries, and reconciliation to handle states where one side succeeds and the other fails.

## 21. SecureFiles and LOB Storage

Oracle supports SecureFiles for LOBs in eligible tablespaces. SecureFiles offers features such as compression, deduplication, and encryption depending on version, configuration, and privileges/licensing.

Example creating a LOB table:

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
);
~~~

STORAGE IN ROW only applies to small LOBs within Oracle's threshold; large LOBs are stored out-of-row. Streaming via JDBC remains meaningful for both in-row and out-of-row LOBs.

### 21.1 Streaming and SecureFiles Are Two Different Layers

- SecureFiles determines how Oracle stores and manages LOBs.
- Streaming determines how the application reads/writes content.
- A LOB using SecureFiles can still be loaded entirely into a byte array if the application calls getBytes.
- A LOB using BasicFiles can still be read via a stream if the driver supports it.

Do not expect changing the storage format to automatically fix code that materializes the entire content.

## 22. BFILE and Reading External Files

BFILE allows Oracle to access files in a directory on the database server through a DIRECTORY object.

Example:

~~~sql
CREATE OR REPLACE DIRECTORY document_dir AS '/u01/app/documents';
GRANT READ ON DIRECTORY document_dir TO app_user;
~~~

Declaring a BFILE:

~~~sql
CREATE TABLE external_documents (
    document_id NUMBER PRIMARY KEY,
    external_file BFILE
);
~~~

Reading in PL/SQL:

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
    l_offset INTEGER := 1;
    l_amount INTEGER;
    l_buffer RAW(32767);
BEGIN
    SELECT external_file
    INTO l_file
    FROM external_documents
    WHERE document_id = 100;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);
        DBMS_LOB.READ(l_file, l_amount, l_offset, l_buffer);

        -- Process chunk.

        l_offset := l_offset + l_amount;
    END LOOP;

    DBMS_LOB.FILECLOSE(l_file);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

The example illustrates the read loop; you must handle NULL locators or FILEOPEN errors before calling FILEISOPEN. BFILE cannot be written via DBMS_LOB.WRITE; to bring content into the database, use DBMS_LOB.LOADFROMFILE or stream from the application through an appropriate workflow.

## 23. Common Streaming Errors

| Symptom | Cause | Solution |
|---|---|---|
| OutOfMemoryError when downloading files | getBytes/readAllBytes or full String | Use InputStream/Reader in chunks |
| Stream fails after repository method returns | Connection/ResultSet already closed | Consume stream while resources remain open |
| Unusually slow upload | Buffer too small, network or database bottleneck | Measure throughput and test buffer sizes |
| Connection pool exhaustion | Slow downloads hold connections long | Limit concurrent streams, timeouts, or staging |
| Corrupted characters in CLOB | Using byte stream/unclear charset | Use Reader/Writer and explicit charset |
| Truncated content | Variable limits or improper getSubString | Use stream or chunk API |
| Wrong offset | Confusing bytes and characters, or forgetting 1-based offsets | BLOB uses bytes, CLOB uses characters |
| BLOB upload length overflow | Casting long file size to int | Use JDBC overload supporting long |
| Temporary LOBs keep growing | Missing FREETEMPORARY | Free on both success and exception paths |
| LOB write locking error | Missing SELECT FOR UPDATE with locator update | Hold transaction and row lock as required |
| Client cancels download but DB keeps reading | Not stopping pipeline on output error | Cancel read, close stream, return connection |
| Heap still grows despite streaming | Unbounded queue or full intermediate buffer | Use bounded queue and backpressure |
| Wrong Content-Length | Using character count for bytes or vice versa | Use correct unit and metadata |
| Error using JDBC stream | Incompatible driver/API overload | Check JDBC driver version and Oracle docs |

## 24. Streaming Implementation Workflow

A practical workflow:

1. Identify the data source: BLOB, CLOB, file upload, object storage, or BFILE.
2. Determine maximum size and concurrent stream count.
3. Choose the appropriate stream API: InputStream/OutputStream for binary, Reader/Writer for text.
4. Set a fixed buffer and concurrency limits.
5. Define the lifecycle of connections, ResultSets, locators, and transactions.
6. Handle mid-stream errors, timeouts, and client cancellations.
7. Validate checksums, content types, and access permissions.
8. Measure heap, GC, throughput, latency, and connection pool usage.
9. Test empty data, large data, Unicode, and network failures.
10. Deploy monitoring and resource limits.

## 25. Self-Check Practice Exercises

Exercises should be run in a test schema using test files of varying sizes.

### Exercise 1 — Compare Materialization and Streaming

Create a BLOB of several tens of MB. Read it with getBytes and getBinaryStream. Compare heap, GC, and elapsed time. Increase file size to observe memory growth.

### Exercise 2 — Stream a BLOB to a File

Write JDBC code using getBinaryStream, a 64 KB buffer, and Files.newOutputStream. Compare the destination file's checksum with the source checksum.

### Exercise 3 — Stream a CLOB to a UTF-8 File

Create a CLOB containing Vietnamese text and Unicode characters outside the BMP. Read it with getCharacterStream and write UTF-8 using Writer. Confirm no characters are lost.

### Exercise 4 — Upload a BLOB

Use setBinaryStream to INSERT a file into a BLOB. Do not call Files.readAllBytes. Measure heap and elapsed time.

### Exercise 5 — Upload a CLOB

Use Reader and setCharacterStream to store a UTF-8 text file into a CLOB. Compare against reading the entire file into a String and calling setString.

### Exercise 6 — DBMS_LOB.READ

Write PL/SQL to read a BLOB using RAW(32767) and a CLOB using VARCHAR2 chunks. Log the offset, amount, and final length.

### Exercise 7 — WRITEAPPEND

Create EMPTY_BLOB/EMPTY_CLOB and write multiple chunks using DBMS_LOB.WRITEAPPEND. Verify content and length.

### Exercise 8 — Temporary LOB

Create a temporary CLOB, append multiple segments, check ISTEMPORARY, and call FREETEMPORARY in both success and exception branches.

### Exercise 9 — Backpressure

Simulate output slower than input. Push chunks into a bounded queue and compare with an unbounded queue. Monitor heap usage.

### Exercise 10 — Connection Lifetime

Attempt to read a stream after closing ResultSet/Connection. Observe the error and fix it to consume the stream within resource scope.

### Exercise 11 — HTTP Download

Create an endpoint that streams a BLOB to the response. Test with slow clients and disconnected clients. Confirm the connection is returned to the pool.

### Exercise 12 — Concurrency Benchmark

Run 1, 10, 50, and 100 concurrent downloads with different buffer sizes. Track throughput, p95 latency, heap, GC, and connection pool metrics.

## 26. Production Streaming Checklist

**Data**

- Are BLOB/CLOB/NCLOB/BFILE chosen with the right semantics?
- Are file size and type limits enforced?
- Are NULL LOB, empty LOB, and missing row distinguished?
- Does CLOB have a clear charset/encoding?

**Application**

- Are InputStream/Reader used instead of full byte[]/String?
- Are buffers bounded?
- Are queues bounded with backpressure?
- Does reading stop when the client cancels?
- Are unnecessary simultaneous LOB streams avoided?

**JDBC and Transactions**

- Does the driver support the stream overload in use?
- Are Connection/Statement/ResultSet open while streaming?
- Are locators used with proper transactions and row locks?
- Are streams closed before commit/connection close?
- Do exceptions roll back per contract?

**Resources**

- Is the connection pool sized for long streams?
- Are timeouts and concurrency limits configured?
- Have heap, GC, PGA, throughput, and latency been measured?
- Are temporary LOBs freed?

**Security**

- Are document read permissions checked?
- Are size, MIME type, and file signature validated?
- Is the filename safely encoded in HTTP headers?
- Are checksums/scans performed as required?
- Is sensitive data excluded from logs?

## 27. Key Takeaways

| Concept | What to Remember |
|---|---|
| BLOB | Large binary data |
| CLOB | Large text in the database character set |
| NCLOB | Large text in the national character set |
| BFILE | Locator to an external file outside the database, read-only |
| LOB locator | Reference to a LOB; does not mean the full content is in the heap |
| getBytes/getSubString | Materializes the requested data slice into memory |
| getBinaryStream | Reads BLOB via a byte stream |
| getCharacterStream | Reads CLOB via a character stream |
| setBinaryStream | Uploads BLOB from an InputStream |
| setCharacterStream | Uploads CLOB from a Reader |
| DBMS_LOB.READ | Reads LOB in chunks |
| DBMS_LOB.WRITE/WRITEAPPEND | Writes LOB at an offset or at the end |
| Temporary LOB | Lifecycle must be managed and FREETEMPORARY called |
| BLOB offset | Measured in bytes, starting at 1 |
| CLOB offset | Measured in characters, starting at 1 |
| Backpressure | Avoid unbounded chunk accumulation when the destination is slow |
| Connection lifetime | Keep connection/locator valid during streaming |
| Fetch size | Controls row batching, does not replace LOB streaming |
| SecureFiles | LOB storage layer, independent of how the application streams |

Streaming large data is an end-to-end design spanning Oracle LOBs, the driver, and the application. Use locators with InputStream/Reader for reading, setBinaryStream/setCharacterStream for writing, or DBMS_LOB in chunks when processing in PL/SQL. Keep buffers and queues bounded, manage connections and transactions throughout the transfer, and measure under concurrent load. That way, application memory stays bounded by chunk size rather than scaling with total file size.
