# Streaming CLOB/BLOB Reads and Writes and Closing Resources Properly

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Oracle JDBC  
> **Objective:** Read and write large LOBs using JDBC streaming APIs; distinguish CLOB, NCLOB, and BLOB; choose between direct stream binding and LOB locators; handle encoding and length; manage transactions, connections, statements, result sets, streams, and locators with proper lifecycles; avoid loading entire LOBs into heap; write connection-pool-safe code and handle errors.

## 1. Why stream LOBs?

Oracle Database supports storing large data in LOB types:

- **CLOB:** character data in the database character set.
- **NCLOB:** character data in the national character set.
- **BLOB:** binary data.
- **BFILE:** locator pointing to a binary file outside the database, read-only via Oracle-supported mechanisms.

A row may contain a PDF document, image, video, long HTML/XML/JSON payload, contract text, or large binary data. When an application reads or writes these values, how it handles them directly affects JVM memory, network traffic, connection hold time, and transaction duration.

If loading the entire content into memory:

- CLOB can be turned into a huge String.
- BLOB can be turned into a huge byte array.
- Concurrent requests can cause heap usage to spike rapidly.
- Garbage collection pauses can lengthen.
- The application can hit OutOfMemoryError.
- Connections and transactions may be held open long while copying.

Streaming processes data in small chunks. Instead of holding the entire LOB in heap, the application reads or writes through Reader/Writer or InputStream/OutputStream.

~~~text
Without streaming:

Database LOB
     |
     v
JDBC driver
     |
     v
Large String / byte[] in heap
     |
     v
Application processing

Streaming:

Database LOB
     |
     v
JDBC stream
     |
     v
Small buffer, looped repeatedly
     |
     v
File / HTTP response / Writer / OutputStream
~~~

Streaming does not mean zero buffering. Both the JDBC driver and application still use buffers, but the amount of data held in memory simultaneously is bounded.

## 2. Distinguishing CLOB, NCLOB, BLOB, and BFILE

| Type | Content | Common JDBC API | Length unit |
|---|---|---|---|
| CLOB | Characters in database character set | Clob, Reader, Writer | Characters |
| NCLOB | Characters in national character set | NClob, Reader, Writer | Characters |
| BLOB | Binary bytes | Blob, InputStream, OutputStream | Bytes |
| BFILE | External binary file outside database | BFILE locator/Oracle extension | Bytes |

### 2.1. CLOB is character data

CLOB suits long text such as:

- Article bodies.
- XML/JSON.
- Email content.
- Text documents.
- HTML content.

JDBC reads CLOB using Reader and writes using Writer or binds a Reader to PreparedStatement.

Do not use getString() for very large CLOBs when the goal is streaming. getString() allocates a String on the heap and can increase memory pressure.

### 2.2. NCLOB and Unicode

NCLOB stores data using the national character set. JDBC provides NClob and APIs such as getNCharacterStream/setNCharacterStream where appropriate.

Do not convert every CLOB to NCLOB just because data contains Unicode. Modern database character sets usually support Unicode; data type selection should follow schema and compatibility requirements.

### 2.3. BLOB is bytes, not text

BLOB is for binary content such as PDFs, images, audio, video, compressed archives, or encrypted payloads.

Use InputStream and OutputStream. Never use Reader/Writer for BLOBs because byte-to-character conversion can corrupt data.

If storing text inside a BLOB, the application must define an explicit encoding, such as UTF-8, and convert between byte streams and character streams itself. Never rely on the JVM's default charset.

### 2.4. BFILE differs from BLOB

BFILE is a locator to a file external to the database. The database does not store file content in a BFILE segment, and BFILE access is read-only. It requires a DIRECTORY object and filesystem permissions on the database server.

This lesson focuses on database-stored CLOB/BLOB. Do not use BFILE instead of BLOB if the application needs transactional and backup semantics for LOB data inside the database.

## 3. Example table

Example document storage table:

~~~sql
CREATE TABLE document_store (
    document_id   NUMBER PRIMARY KEY,
    document_name VARCHAR2(255) NOT NULL,
    text_body     CLOB,
    binary_body   BLOB,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

A row may store either content type depending on business logic. In production designs, metadata and LOBs may be separated, or document types split into separate tables to manage permissions, retention, and lifecycle.

### 3.1. NULL and EMPTY_CLOB/EMPTY_BLOB

A LOB column can hold NULL or an empty LOB:

- NULL: no LOB locator/content exists yet.
- EMPTY_CLOB(): valid LOB locator with length 0.
- EMPTY_BLOB(): valid BLOB locator with length 0.

This distinction matters when updating via a locator. If the column is NULL, getClob/getBlob may return null; you cannot call setCharacterStream or setBinaryStream on a null locator.

Example initializing empty LOBs:

~~~sql
INSERT INTO document_store (
    document_id,
    document_name,
    text_body,
    binary_body
)
VALUES (
    1001,
    'contract',
    EMPTY_CLOB(),
    EMPTY_BLOB()
);
~~~

Not every streaming write requires a prior locator; binding Reader/InputStream directly in INSERT/UPDATE is often simpler.

## 4. Primary JDBC streaming APIs

### 4.1. Reading CLOB

- ResultSet.getCharacterStream(column): returns Reader.
- ResultSet.getClob(column): returns Clob locator.
- Clob.getCharacterStream(): returns Reader.
- Clob.length(): length in characters.
- Clob.getSubString(position, length): loads a slice into String; suitable for small slices.

### 4.2. Writing CLOB

- PreparedStatement.setCharacterStream(index, reader): binds character stream.
- PreparedStatement.setClob(index, clob): binds Clob object.
- PreparedStatement.setClob(index, reader, length): binds Reader with known length, depending on JDBC/driver overloads.
- Clob.setCharacterStream(position): obtains Writer to write starting at a LOB position.
- Clob.truncate(length): truncates LOB to specified length.

### 4.3. Reading BLOB

- ResultSet.getBinaryStream(column): returns InputStream.
- ResultSet.getBlob(column): returns Blob locator.
- Blob.getBinaryStream(): returns InputStream.
- Blob.length(): byte count.
- Blob.getBytes(position, length): loads a slice into a byte array; use only for small slices.

### 4.4. Writing BLOB

- PreparedStatement.setBinaryStream(index, inputStream): binds binary stream.
- PreparedStatement.setBlob(index, blob): binds Blob object.
- PreparedStatement.setBlob(index, inputStream, length): binds stream with length, depending on JDBC/driver overloads.
- Blob.setBinaryStream(position): obtains OutputStream for writing.
- Blob.truncate(length): truncates BLOB to specified length.

Overload availability depends on the JDBC API and Oracle JDBC driver version. Verify your application's driver version; avoid calling overloads unsupported by the driver.

## 5. Streaming vs. loading the entire LOB

Avoid doing this for large LOBs:

~~~java
Clob clob = rs.getClob("TEXT_BODY");
String text = clob.getSubString(1, (int) clob.length());

Blob blob = rs.getBlob("BINARY_BODY");
byte[] bytes = blob.getBytes(1, (int) blob.length());
~~~

Problems:

- CLOB/BLOB may exceed int-based API limits.
- Entire data is materialized as objects on the heap.
- Concurrent requests multiply required memory.
- Creating intermediate String/byte[] copies can double or multiply memory footprint.
- Data cannot naturally flow directly to a file or HTTP output.

Use getCharacterStream/getBinaryStream or locator streams to process with buffers.

Never use InputStream.available() to measure total data size. available() only estimates bytes readable without blocking in some implementations, not the total BLOB length.

## 6. Buffered copy helpers

Copy helper functions form the foundation for streaming. Use a moderate buffer, such as 8 KB to 64 KB, and measure against your actual workload.

### 6.1. Copying characters

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;

public static long copyCharacters(Reader source, Writer target)
        throws IOException {

    char[] buffer = new char[16 * 1024];
    long total = 0;
    int count;

    while ((count = source.read(buffer)) != -1) {
        target.write(buffer, 0, count);
        total += count;
    }

    return total;
}
~~~

The buffer is a char array, so the count represents Java characters read, not UTF-8 bytes.

### 6.2. Copying bytes

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public static long copyBytes(InputStream source, OutputStream target)
        throws IOException {

    byte[] buffer = new byte[16 * 1024];
    long total = 0;
    int count;

    while ((count = source.read(buffer)) != -1) {
        target.write(buffer, 0, count);
        total += count;
    }

    return total;
}
~~~

The buffer is a byte array, so the count is in bytes. Never convert a BLOB into a String during copying.

### 6.3. Is flush needed?

When writing through Writer/OutputStream, closing the stream usually flushes data before releasing resources. You can call flush when data must be sent downstream promptly, but flush does not replace close.

For streams provided by JDBC to write LOBs, closing the Writer/OutputStream before committing is a critical step to finalize the write per driver behavior.

## 7. Reading CLOB with Reader

Example reading a CLOB directly from a ResultSet:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static long readClob(
        Connection connection,
        long documentId,
        Writer destination
) throws SQLException, IOException {

    String sql =
        "SELECT text_body FROM document_store WHERE document_id = ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, documentId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                throw new SQLException("Document not found");
            }

            try (Reader reader = resultSet.getCharacterStream(1)) {
                if (reader == null) {
                    return 0L;
                }

                return copyCharacters(reader, destination);
            }
        }
    }
}
~~~

In this example:

- PreparedStatement is closed.
- ResultSet is closed after reading finishes.
- Reader is closed via try-with-resources.
- Writer destination belongs to the caller, so the method does not close it.
- Connection belongs to the caller, so the method does not close or commit it.

Reader is consumed while ResultSet, Statement, and Connection remain open. Never return a Reader from a method and close ResultSet/Connection before the caller reads it.

### 7.1. Reading CLOB to a UTF-8 file

~~~java
import java.io.BufferedWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (Writer output = Files.newBufferedWriter(
        outputPath,
        StandardCharsets.UTF_8
)) {
    long characters = readClob(connection, documentId, output);
    System.out.println("Characters copied: " + characters);
}
~~~

UTF-8 is specified on the file side. The JDBC Reader already supplies Java characters; do not manually decode a Reader like a byte stream.

Never write files to an uncontrolled path from user input. Output files also need quotas, filesystem permissions, and proper retention.

## 8. Reading BLOB with InputStream

Example:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static long readBlob(
        Connection connection,
        long documentId,
        OutputStream destination
) throws SQLException, IOException {

    String sql =
        "SELECT binary_body FROM document_store WHERE document_id = ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, documentId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                throw new SQLException("Document not found");
            }

            try (InputStream input = resultSet.getBinaryStream(1)) {
                if (input == null) {
                    return 0L;
                }

                return copyBytes(input, destination);
            }
        }
    }
}
~~~

### 8.1. Reading BLOB to a file

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (OutputStream output = Files.newOutputStream(
        outputPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE
)) {
    long bytes = readBlob(connection, documentId, output);
    System.out.println("Bytes copied: " + bytes);
}
~~~

If the target file already exists, TRUNCATE_EXISTING wipes old contents before writing. Use it only when overwriting is intentional. For critical files, write to a temporary file first and atomically move once complete and verified.

### 8.2. Streaming to an HTTP response

In web applications, you can copy a BLOB directly to ServletOutputStream or the response output stream to avoid allocating huge byte arrays.

Requirements:

- Keep the JDBC connection and ResultSet open throughout the entire stream.
- Set content type, content length if known, and content disposition.
- Do not close an output stream owned by the servlet container if the framework manages its lifecycle.
- Handle client disconnects.
- Ensure the connection returns to the pool once streaming ends.
- Configure timeouts and cap concurrent downloads.

A slow download can hold a database connection for a long time. Measure load and consider storing files in object storage if downloads are large, frequent, or long-lived.

## 9. Writing CLOB with PreparedStatement.setCharacterStream

For typical INSERT/UPDATE statements, binding a Reader directly is usually the simplest approach:

~~~java
import java.io.Reader;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public static int insertTextDocument(
        Connection connection,
        long documentId,
        String documentName,
        java.nio.file.Path sourcePath
) throws Exception {

    String sql =
        "INSERT INTO document_store " +
        "(document_id, document_name, text_body) " +
        "VALUES (?, ?, ?)";

    try (Reader reader = Files.newBufferedReader(
            sourcePath, StandardCharsets.UTF_8);
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, documentName);
        statement.setCharacterStream(3, reader);

        return statement.executeUpdate();
    }
}
~~~

The driver consumes the Reader when executeUpdate runs. The Reader must remain open for the entire duration of statement execution.

If the driver or API requires a length, use a supported length-taking overload. For Reader, length is the character count per the JDBC contract, not the UTF-8 file's byte count. Never pass Files.size(path) as the character length for a Reader containing Unicode.

### 9.1. UPDATE CLOB

~~~java
String sql =
    "UPDATE document_store SET text_body = ? WHERE document_id = ?";

try (Reader reader = Files.newBufferedReader(
        sourcePath, StandardCharsets.UTF_8);
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setCharacterStream(1, reader);
    statement.setLong(2, documentId);

    int updated = statement.executeUpdate();

    if (updated != 1) {
        throw new SQLException("Expected exactly one document row");
    }
}
~~~

With application-managed transactions, commit after the statement and input stream complete. If the wrong number of rows was updated, roll back per the transaction contract.

### 9.2. Overloads with length

JDBC offers overloads taking Reader and length. Example:

~~~java
statement.setCharacterStream(parameterIndex, reader, characterLength);
~~~

Use a long length if the driver supports the corresponding JDBC overload. Older versions may only have int overloads. If character count is unknown beforehand and you still want to stream, use a lengthless overload if supported by the driver.

Do not read the entire file solely to count characters if doing so defeats streaming. Use a known file format/metadata or a lengthless API.

## 10. Writing BLOB with PreparedStatement.setBinaryStream

Example inserting a binary file:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

public static int insertBinaryDocument(
        Connection connection,
        long documentId,
        String documentName,
        Path sourcePath
) throws Exception {

    String sql =
        "INSERT INTO document_store " +
        "(document_id, document_name, binary_body) " +
        "VALUES (?, ?, ?)";

    try (InputStream input = Files.newInputStream(sourcePath);
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, documentName);
        statement.setBinaryStream(3, input, Files.size(sourcePath));

        return statement.executeUpdate();
    }
}
~~~

Files.size returns byte count, matching binary stream length. If the file can change while being read, a pre-fetched size may become stale; use an immutable file during upload or a lengthless overload if supported by the driver.

### 10.1. UPDATE BLOB

~~~java
String sql =
    "UPDATE document_store SET binary_body = ? WHERE document_id = ?";

try (InputStream input = Files.newInputStream(sourcePath);
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setBinaryStream(1, input, Files.size(sourcePath));
    statement.setLong(2, documentId);

    int updated = statement.executeUpdate();

    if (updated != 1) {
        throw new SQLException("Expected exactly one document row");
    }
}
~~~

For large data, monitor network, transaction duration, redo generation, and storage throughput. Streaming lowers heap usage but does not eliminate I/O and redo costs.

## 11. Writing via LOB locators and SELECT FOR UPDATE

Another approach is acquiring the LOB locator on a locked row and writing through a stream opened from that locator.

Pattern:

1. Start transaction.
2. SELECT LOB column FOR UPDATE.
3. Obtain Clob/Blob locator.
4. Truncate old contents if replacing completely.
5. Open Writer/OutputStream from the locator.
6. Copy data in buffered chunks.
7. Close stream.
8. Close ResultSet/Statement.
9. Commit transaction.
10. Free the locator.

### 11.1. Updating a CLOB locator

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.sql.Clob;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void replaceClob(
        Connection connection,
        long documentId,
        Reader source
) throws SQLException, IOException {

    if (connection.getAutoCommit()) {
        throw new SQLException(
            "replaceClob requires an explicit transaction"
        );
    }

    Clob clob = null;

    try {
        String sql =
            "SELECT text_body FROM document_store " +
            "WHERE document_id = ? FOR UPDATE";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, documentId);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    throw new SQLException("Document not found");
                }

                clob = resultSet.getClob(1);

                if (clob == null) {
                    throw new SQLException(
                        "CLOB is NULL; initialize it before locator write"
                    );
                }

                clob.truncate(0L);

                try (Writer writer = clob.setCharacterStream(1L)) {
                    copyCharacters(source, writer);
                }
            }
        }

        connection.commit();

    } catch (SQLException | IOException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;

    } finally {
        if (clob != null) {
            clob.free();
        }
    }
}
~~~

This method requires an explicit transaction and commits/rolls back itself in the example. In real applications, agree on who owns the transaction: service layer or DAO method. Never let multiple layers commit the same transaction without a clear contract.

The source Reader belongs to the caller; the method consumes it without closing it. The caller should close the Reader after the method completes.

If the CLOB column is currently NULL, initialize it with EMPTY_CLOB() in the same transaction before SELECT FOR UPDATE, or bind a stream directly in UPDATE.

### 11.2. Updating a BLOB locator

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Blob;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void replaceBlob(
        Connection connection,
        long documentId,
        InputStream source
) throws SQLException, IOException {

    if (connection.getAutoCommit()) {
        throw new SQLException(
            "replaceBlob requires an explicit transaction"
        );
    }

    Blob blob = null;

    try {
        String sql =
            "SELECT binary_body FROM document_store " +
            "WHERE document_id = ? FOR UPDATE";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, documentId);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    throw new SQLException("Document not found");
                }

                blob = resultSet.getBlob(1);

                if (blob == null) {
                    throw new SQLException(
                        "BLOB is NULL; initialize it before locator write"
                    );
                }

                blob.truncate(0L);

                try (OutputStream output = blob.setBinaryStream(1L)) {
                    copyBytes(source, output);
                }
            }
        }

        connection.commit();

    } catch (SQLException | IOException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;

    } finally {
        if (blob != null) {
            blob.free();
        }
    }
}
~~~

A LOB locator is a handle to data in the database. free() releases JDBC-side locator resources; it does not delete the row or erase committed LOB values.

In production, log if free() fails without masking the original exception. A cleanup helper can attach secondary exceptions as suppressed on the primary exception.

### 11.3. Why is SELECT FOR UPDATE needed?

Locator updates require the row holding the LOB to be locked in an appropriate transaction. SELECT FOR UPDATE locks the row so another transaction cannot modify the same row while the stream writes.

The lock can remain held throughout the entire copy duration. For very large files or slow sources, lock duration grows and the transaction holds resources longer. Where possible, bind streams directly in a single DML statement or use staging/asynchronous workflows to shorten lock duration.

## 12. LOB locators and streams have different lifecycles

A Clob/Blob locator is not the same as a Reader/Writer or InputStream/OutputStream.

- A locator is a JDBC object representing the LOB in the database.
- A stream is the channel for reading/writing LOB contents.
- Connection supplies the session/database context.
- Transaction governs locks and when changes commit/roll back.

Closing a stream does not necessarily release the locator. Calling free() releases the locator object. Closing ResultSet/Statement releases cursor/statement resources. Closing Connection returns or closes the database session depending on the connection pool.

Every resource must be managed according to its type and in the right order.

## 13. Resource lifecycle rules

A common safe order when reading a LOB:

1. Acquire Connection.
2. Create PreparedStatement.
3. Execute query.
4. Obtain ResultSet.
5. Open Reader/InputStream.
6. Copy all data.
7. Close Reader/InputStream.
8. Close ResultSet.
9. Close PreparedStatement.
10. Return Connection to pool.

When writing via a locator:

1. Acquire Connection.
2. Start transaction, disable auto-commit.
3. SELECT FOR UPDATE.
4. Obtain Clob/Blob locator.
5. Open Writer/OutputStream.
6. Write all data.
7. Close Writer/OutputStream.
8. Close ResultSet/Statement.
9. Commit or roll back.
10. Call free() on the locator.
11. Reset connection state and return Connection to pool.

Some cleanup ordering may vary slightly by driver, but never close Connection or ResultSet while a stream is still in use.

### 13.1. Using try-with-resources

The following classes implement AutoCloseable and work cleanly with try-with-resources:

- Connection.
- PreparedStatement.
- Statement.
- ResultSet.
- Reader/Writer.
- InputStream/OutputStream.

Clob and Blob are not AutoCloseable under the standard JDBC interface; call free() in a finally block after streams are closed.

### 13.2. Do not close caller-owned resources

A DAO receiving a Connection from the service layer should not close that connection if the contract says the caller owns it. Likewise, a method receiving a Writer/OutputStream managed by a web framework should not close that output stream.

Document ownership explicitly:

| Resource | Typically owned by? | Who closes it? |
|---|---|---|
| Connection acquired by DAO itself | DAO | DAO |
| Connection passed from transaction manager | Caller/framework | Caller/framework |
| PreparedStatement created in method | Method | Method |
| ResultSet created in method | Method | Method |
| Reader obtained from ResultSet | Reading method | Method |
| Reader passed into method | Caller | Caller, per contract |
| Writer obtained from Clob locator | Writing method | Method |
| ServletOutputStream | Web container/framework | Framework or caller per contract |
| Clob/Blob locator | Code that obtained locator | That code calls free() |

## 14. Transactions and auto-commit

### 14.1. Writing via bind streams

For INSERT/UPDATE using setCharacterStream or setBinaryStream, the driver consumes the input stream while executing the statement. Commit the transaction after the statement finishes and streams are closed.

If auto-commit is enabled, a successful statement may commit automatically per JDBC semantics. This may work for a single standalone DML, but not when the LOB write is part of multiple changes that must be atomic.

### 14.2. Writing via locators

With SELECT FOR UPDATE and locator streams, an explicit transaction is mandatory:

~~~java
connection.setAutoCommit(false);

try {
    // SELECT ... FOR UPDATE
    // Write LOB and close stream
    connection.commit();
} catch (Exception error) {
    connection.rollback();
    throw error;
}
~~~

Never commit while a Writer/OutputStream is still open. Close the stream first so the driver finishes writing.

### 14.3. Keep transactions short

Do not hold a transaction open while:

- Waiting for a user to upload a slow file.
- Reading a file from an unstable network share.
- Calling an external HTTP service.
- Waiting on a message broker.
- Waiting on lengthy antivirus scanning.
- Compressing/encrypting huge payloads if it can be done before the transaction.

Upload files to staging storage first, verify size/hash/antivirus, and then stream into the database in a shorter transaction. Or store files in object storage and store only metadata/references in Oracle if the architecture fits.

### 14.4. Rollback

If an error occurs mid-write:

- Close open streams.
- Roll back the transaction.
- Never return a connection with an unfinished transaction to the pool.
- Log the error along with document ID/correlation ID.
- Confirm old data remains intact per transaction semantics.
- Retry only if the source can be re-read and the operation is safe to retry.

Rollback does not replace cleanup. Streams, ResultSets, Statements, and locators still must be released.

## 15. Connection pools and session state

Applications typically use HikariCP, UCP, or an application server's connection pool. Connection.close() in a pooled environment normally returns the logical connection to the pool rather than closing the physical database session.

Before returning a connection:

- All Reader/InputStream/Writer/OutputStream objects are closed.
- ResultSet and Statement are closed.
- Transaction is committed or rolled back.
- Auto-commit is restored per pool policy.
- Read-only/isolation/schema/catalog/session state is not left dirty.
- No LOB locators/streams remain active.
- No background task retains a reference to the connection.

Never return a connection to the pool while another thread is still reading a BLOB. JDBC connections are generally not designed for concurrent use by multiple threads.

### 15.1. Connection leaks

If a download stream never finishes or a client disconnects without application cleanup, connections can remain held indefinitely.

Symptoms:

- Pool active connections climb.
- Idle connections drop.
- Connection acquisition timeouts occur.
- Requests queue waiting for the pool.
- Database sessions remain open long.
- Cursors/transactions stay open.

Use try-with-resources and timeouts across JDBC, web server, and network layers. Test client disconnect behavior to ensure finally/cleanup blocks always execute.

### 15.2. Never hold connections in background callbacks

Do not hand a ResultSet, Blob locator, or JDBC InputStream to an executor and return the connection to the pool before the task completes. All of those objects depend on the connection/session lifecycle.

If asynchronous processing is required, the worker must own its own connection for the entire streaming duration and close it upon completion.

## 16. Encoding and length

### 16.1. CLOB: characters vs. bytes differ

CLOB stores characters. Java Reader/Writer operates on Java characters. When reading a UTF-8 file into a Reader, CharsetDecoder converts bytes into characters.

One Unicode character can occupy multiple UTF-8 bytes. Therefore:

- Character count does not equal byte count.
- Reader length must not be computed with Files.size() on a UTF-8 file.
- HTTP Content-Length counts bytes, not characters.
- Never convert CLOB to bytes without specifying an explicit charset.

### 16.2. BLOB: bytes

BLOB stores bytes verbatim. InputStream/OutputStream does not interpret encoding.

If a BLOB contains UTF-8 JSON, decode with UTF-8 when reading text:

~~~java
try (InputStream input = blob.getBinaryStream();
     Reader reader = new java.io.InputStreamReader(
         input,
         java.nio.charset.StandardCharsets.UTF_8
     )) {
    // Read characters as a stream.
}
~~~

Never use Charset.defaultCharset() for data exchanged across hosts.

### 16.3. CLOB length and BLOB length

Clob.length() returns the LOB's character length. Blob.length() returns byte length. Both return long; never cast to int for large LOBs.

Standard JDBC getSubString/getBytes methods take int lengths, so never use them to materialize entire large LOBs.

### 16.4. Supplementary characters

Java Strings use UTF-16 code units. A Unicode code point outside the Basic Multilingual Plane takes two chars. When counting displayed characters, code points and UTF-16 code units can differ.

Do not treat String.length() as a byte measurement or always assume it equals the number of user-visible characters.

## 17. LOB prefetch and performance

Oracle JDBC supports LOB prefetch so the driver can retrieve metadata and an initial portion of LOB data alongside row fetches. This can improve performance for small, frequently read LOBs.

For large LOBs:

- Overly large prefetch can raise memory/network usage.
- Streaming is still necessary for handling large payloads.
- LOB prefetch can be tuned at connection/statement level per Oracle JDBC driver.
- Test with realistic LOB size distributions.
- Measure round trips, heap, throughput, and p95 latency.

LOB prefetch does not mean loading the entire LOB. It optimizes fetching metadata and an initial chunk of data.

### 17.1. Fetch size is not LOB prefetch

Statement fetch size generally controls how many rows are fetched per round trip. LOB prefetch controls pre-fetching LOB metadata/initial data.

Increasing fetch size reduces round trips across many rows, while increasing memory. Tune both based on workload and LOB sizes.

### 17.2. Buffer size

Buffers of 8 KB, 16 KB, or 64 KB are starting points for benchmarking, not absolute rules. Larger buffers reduce read/write calls while increasing per-stream memory.

With hundreds of concurrent streams, 64 KB per stream adds noticeable memory overhead. Measure at realistic concurrency.

### 17.3. Parallel streaming

Never assume a single JDBC Connection can be shared across threads to read multiple LOBs concurrently. Each worker should own its own connection, statement, and resources.

Bound concurrent streams using the connection pool and application semaphores. If downstream consumers are slow, propagate backpressure rather than opening excessive connections.

## 18. LOB locators, temporary LOBs, and free()

JDBC provides Connection.createClob() and Connection.createBlob() to create temporary LOB objects in the database per driver implementation. These can be used when preparing a LOB before binding, but they must be released with free().

Example:

~~~java
Clob temporaryClob = connection.createClob();

try {
    try (Writer writer = temporaryClob.setCharacterStream(1L)) {
        copyCharacters(sourceReader, writer);
    }

    try (PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO document_store(document_id, text_body) VALUES (?, ?)")) {
        statement.setLong(1, documentId);
        statement.setClob(2, temporaryClob);
        statement.executeUpdate();
    }
} finally {
    temporaryClob.free();
}
~~~

This creates a LOB object and then binds it, though it may consume extra temp storage/resources and copies. If the driver supports binding a Reader directly, direct stream binding is usually simpler.

Do not confuse temporary LOBs with persistent LOBs in tables. Temporary LOBs need free() when finished; calling free() on a persistent LOB locator only releases the JDBC handle and does not delete committed data.

## 19. Common errors when reading/writing LOBs

| Symptom | Possible cause | Resolution |
|---|---|---|
| OutOfMemoryError | Using getString/getBytes on large LOBs | Use Reader/InputStream and buffers |
| ORA-22922 nonexistent LOB value | Locator no longer valid or row/transaction context changed | Check locator, connection, and transaction lifetime |
| ORA-22990 LOB locators cannot span transactions | Invalidly using locator across transaction boundary | Do not hold locator across commit/rollback; acquire a fresh locator |
| ORA-22920 row containing the LOB value not locked | Writing locator without locking the row | Use SELECT FOR UPDATE inside a transaction |
| Truncated LOB write | Wrong bind length or source stream ended early | Check overload, character/byte length, and source |
| Corrupted Unicode content | Wrong charset conversion or using byte APIs for CLOB | Use Reader/Writer and explicit charsets |
| Corrupted BLOB | Passing binary data through Reader/String | Use InputStream/OutputStream |
| Old trailing data left in LOB | Writing from position 1 without truncating tail | Truncate LOB before replacing completely |
| NULL locator | LOB column is currently NULL | Use stream binding or initialize EMPTY_CLOB/EMPTY_BLOB |
| Connection pool exhausted | Streams/ResultSets/connections left unclosed | Use try-with-resources and timeouts |
| Long-held locks | Streaming to locator inside a long transaction | Stage uploads first, keep transactions short |
| Empty output file | Reader/stream not consumed or null handled wrong | Check resultSet.next(), nulls, and copy loop |
| Driver exception while streaming | Incompatible overload/driver | Check Oracle JDBC version and APIs |
| Client disconnect holds connection | Cleanup failed to run | Ensure finally/try-with-resources and cancellation handling |

### 19.1. ORA-22990 and transaction boundaries

LOB locators have lifetime rules. Do not obtain a locator, commit the transaction, and then continue using the locator as if it remained valid. Across a transaction boundary, re-query and obtain a fresh locator per semantics.

### 19.2. Errors when closing streams

Exceptions can occur while reading, writing, or closing streams. try-with-resources preserves the primary exception and attaches close exceptions as suppressed exceptions.

When logging, log both the primary exception and suppressed exceptions; never log only getMessage().

## 20. Handling null, empty, and full replacement

Before opening streams:

- Verify the row exists.
- Distinguish a NULL LOB column from an empty LOB.
- Determine whether the operation is append, overwrite, or partial update.
- When replacing completely via locator, truncate to 0 before writing.
- When binding a stream in UPDATE, the database stores the new LOB value per DML semantics.
- When the source is empty, decide whether to store EMPTY_CLOB/EMPTY_BLOB or NULL per business contract.

Never treat a 0-byte file, an empty LOB, and SQL NULL as identical states.

### 20.1. Append

To append to the end of a LOB, read the current length and open a locator stream at the corresponding position, or use an API/SQL appropriate for the data type and driver. LOB positions in JDBC are 1-based.

Appending via locators requires row locks and transactions. If multiple sessions append to the same row, serialize with locks and design retries.

### 20.2. Partial updates

Clob/Blob expose APIs to write at a position. Clearly define semantics for writing past current length, overwriting a slice, or truncating. For complex operations, DBMS_LOB may fit better, requiring careful management of offsets, lengths, and transactions.

Never write byte-offset logic for CLOBs; CLOB positions follow character semantics in LOB APIs.

## 21. LOBs and connection pools: safe service pattern

A service should separate responsibilities:

- Repository/DAO executes queries and copies LOBs.
- Service manages transaction boundaries.
- Controller manages HTTP response lifecycles.
- Connection pool manages physical connections.
- Caller manages external input/output streams per contract.

Download flow example:

~~~text
HTTP request
     |
     v
Service validates access
     |
     v
Acquire JDBC connection
     |
     v
Query row and open LOB stream
     |
     v
Copy chunks to HTTP response
     |
     v
Close JDBC stream/resultset/statement
     |
     v
Return connection to pool
     |
     v
Complete HTTP response
~~~

If the client disconnects, copying may throw IOException. In that event, close JDBC streams and release the connection in finally. Never leave a connection active indefinitely.

### 21.1. Upload flow

~~~text
HTTP upload
     |
     v
Validate size/type/checksum
     |
     v
Stage file or bounded stream
     |
     v
Acquire JDBC connection
     |
     v
Bind InputStream to BLOB
     |
     v
Execute DML and commit
     |
     v
Close JDBC resources
     |
     v
Return connection to pool
~~~

If request bodies can arrive slowly, avoid opening transactions and holding row locks from the start of upload. Stage the file first or use an upload protocol supporting resumable staging storage.

## 22. Security when handling LOBs

LOBs can hold personal data, contracts, official documents, or malicious files.

- Verify object access permissions before streaming.
- Enforce upload/download size limits.
- Validate MIME types by content when needed, not just file extensions.
- Scan for malware per policy.
- Encrypt transport and storage as required.
- Never log full LOB contents.
- Never include LOB content in exception messages.
- Limit retention time for staging files.
- Use server-generated filenames to prevent path traversal.
- Bound concurrency to prevent memory/connection exhaustion.
- Enforce authorization on every request to prevent IDOR when document IDs are client-supplied.

For BLOBs containing files, do not trust client-supplied Content-Type headers. Use magic-byte signatures and dedicated scanners before exposing files to other users.

## 23. Testing and performance measurement

A LOB test suite should cover multiple sizes and concurrency levels:

| Size | Target |
|---|---|
| 0 bytes | NULL/empty semantics |
| A few KB | Baseline overhead |
| 1 MB | Typical streaming |
| 10–100 MB | Heap and throughput |
| Very large up to business limit | Timeouts, backpressure, and connection lifetime |

Measure:

- Throughput in bytes/second or characters/second.
- p50/p95/p99 latency.
- Heap usage and allocation rate.
- Garbage collection.
- JDBC connection hold time.
- Transaction duration.
- Database CPU, I/O, and redo.
- Concurrent stream count.
- Errors and retries.
- Checksum or content hash verification after round-trip.

### 23.1. Integrity verification

For BLOBs, compute checksums/hashes at the source and after reading back. For CLOBs, compare content according to defined encoding/canonicalization.

Do not check row count alone. A BLOB can exist while truncated or byte-corrupted; a CLOB can suffer Unicode corruption or missing tails.

### 23.2. Concurrency testing

Test concurrent uploads and downloads. Verify:

- Connection pool does not exhaust unexpectedly.
- Memory scales cleanly within bounded buffer/concurrency limits.
- Row locks are not held abnormally long.
- No stream shares a connection across threads.
- Client disconnects still trigger cleanup.
- Retries do not create duplicate data.
- Transaction rollbacks preserve data integrity.

## 24. Pre-production checklist

### API and data types

- [ ] CLOB/NCLOB/BLOB/BFILE chosen according to content.
- [ ] CLOB uses Reader/Writer; BLOB uses InputStream/OutputStream.
- [ ] getString/getBytes not used for large LOBs.
- [ ] Distinguished NULL, EMPTY_CLOB, and EMPTY_BLOB.
- [ ] Character length not confused with byte length.
- [ ] Encodings explicitly defined.

### Streaming

- [ ] Bounded buffers used.
- [ ] Source stream stays open until execute/copy finishes.
- [ ] ResultSet Reader/InputStream consumed before closing ResultSet/Connection.
- [ ] Locator Writer/OutputStream closed before commit.
- [ ] InputStream.available() not used as total size.
- [ ] LOB prefetch measured and tuned per workload.

### Transactions and resource lifecycle

- [ ] Connection ownership clearly defined.
- [ ] Transaction boundaries explicit.
- [ ] SELECT FOR UPDATE used when locator updates need row locks.
- [ ] Never commit/roll back while streams remain open.
- [ ] Statement, ResultSet, and streams closed via try-with-resources.
- [ ] Clob/Blob locators freed with free() after use.
- [ ] Connection committed/rolled back and reset before returning to pool.
- [ ] Connections/locators/streams never shared concurrently across threads.

### Operations and security

- [ ] Upload/download size limits enforced.
- [ ] Timeouts and cancellation cleanup configured.
- [ ] Checksum/integrity validation implemented where needed.
- [ ] Document access authorization enforced.
- [ ] File scanning/validation per policy.
- [ ] Logs contain no sensitive content or secrets.
- [ ] Tested driver version, large LOBs, and concurrent load.
- [ ] Tested client disconnects, timeouts, rollbacks, and pool exhaustion.

## 25. Core takeaways

- CLOB is character data, NCLOB is national character data, BLOB is binary bytes; BFILE points to an external file outside the database with different semantics.
- Use Reader/Writer for CLOB and InputStream/OutputStream for BLOB.
- Buffered streaming avoids materializing entire LOBs as Strings or byte arrays.
- Direct JDBC binding via setCharacterStream/setBinaryStream fits most standard INSERT/UPDATE operations.
- LOB locators fit operations on existing LOBs; locator updates usually require SELECT FOR UPDATE and explicit transactions.
- When replacing completely via a locator, truncate before writing so old trailing data does not remain.
- NULL differs from EMPTY_CLOB/EMPTY_BLOB; a NULL locator cannot open a stream.
- CLOB length is in characters; BLOB length is in bytes; never pass a file byte size as character length.
- JDBC Reader/InputStream depends on ResultSet/Statement/Connection; consume them before closing underlying resources.
- LOB Writer/OutputStream must be closed before commit to finalize writes.
- Clob.free()/Blob.free() releases the locator handle; it does not delete committed LOB data.
- Never use locators across invalid transaction boundaries; fetch a fresh locator after commit/rollback.
- try-with-resources closes streams, ResultSets, and Statements even when exceptions occur.
- Connections managed by a transaction manager/pool should not be closed by DAOs outside contract; finish transactions and cleanup before returning to the pool.
- Never hold row locks while waiting on slow uploads/networks; staging or asynchronous processing may fit better.
- LOB prefetch and fetch size are two distinct mechanisms; tune by LOB size and concurrency.
- BLOB is raw bytes; if content is text, specify encoding explicitly.
- Test checksums, Unicode, NULL/empty, large payloads, concurrent streams, and client disconnects before production.

### Oracle and JDBC references to consult

- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC LOB support, streaming, LOB locators, prefetch, and driver behavior.
- [Oracle Database JDBC Java API Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/) — Oracle JDBC interfaces and extensions.
- [Java SE JDBC API — Clob](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Clob.html) — Character streams, locators, truncate, and free.
- [Java SE JDBC API — Blob](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Blob.html) — Binary streams, locators, truncate, and free.
- [Java SE JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — setCharacterStream, setBinaryStream, setClob, and setBlob overloads.
- [Java SE JDBC API — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html) — getCharacterStream, getBinaryStream, getClob, and getBlob.

JDBC overload availability and Oracle LOB streaming/prefetch behavior depend on the JDK and Oracle JDBC driver version. Verify your deployed driver, test large payloads and transaction boundaries, and measure connection hold time and memory under representative concurrency before production rollout.
