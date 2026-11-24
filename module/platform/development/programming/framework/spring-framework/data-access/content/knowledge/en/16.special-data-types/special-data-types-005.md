# BLOB and CLOB LOBs: Full Materialization vs. Streaming in JDBC/Spring

In Spring Framework Data Access applications, a SQL column may hold very large data: images, PDF files, binary blobs, long text, XML documents, or editorial content. JDBC calls this category **Large Objects (LOB)**. The two core kinds are **BLOB** (*Binary Large Object*) and **CLOB** (*Character Large Object*).

The key point of this lesson is not only picking the column type, but **choosing how to retrieve data from the database into Java**: reading it all at once into `byte[]`/`String`, or consuming it incrementally via `InputStream`/`Reader`. Both approaches can yield the same data yet have vastly different memory footprints, connection lifetimes, latency, and error-handling characteristics.

## 1. How Do BLOB, CLOB, and Regular Data Differ?

| Value Type | What Is Stored? | Java/JDBC Representation | Examples |
| --- | --- | --- | --- |
| `BLOB` | A sequence of **bytes**; the database does not interpret the content as text like CLOB | `byte[]`, `java.sql.Blob`, `InputStream` | PNG images, PDF files, ZIP archives, binary files |
| `CLOB` | A large **character** sequence; subject to database charset/collation | `String`, `java.sql.Clob`, `Reader` | Article body, long text, XML, documents |
| `NCLOB` | Character LOB using a national character set as supported by the RDBMS | `java.sql.NClob`, `Reader` | International text in systems supporting NCLOB |
| `VARBINARY`/`VARCHAR` | Bytes/characters typically smaller or with different limits than LOBs | `byte[]`/`String` | Hashes, status codes, short descriptions |

**BLOB is bytes; CLOB is characters.** Never decode PDF/PNG using `getString()`, and do not arbitrarily treat large Unicode text as raw bytes without charset rules. Vietnamese strings or emojis are character data; a UTF-8 file can be bytes if the application intentionally stores raw file contents in a BLOB.

SQL names and storage vary across DBMSs. PostgreSQL commonly uses `bytea` and `text`; Oracle has `BLOB`/`CLOB`/`NCLOB`; MySQL has the `BLOB`/`TEXT` families; H2 supports `BLOB`/`CLOB`. **You cannot infer that every byte-holding column returns `java.sql.Blob` across all drivers.** Choose the JDBC getter based on SQL type, driver, and application contract.

Example schema used in this lesson (H2, syntax similar across many RDBMSs):

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    picture BLOB,
    body CLOB
);
```

A row might contain a 20 MB image and a 200,000-character text body. If the app only needs to display a list of document titles, it should query metadata or small columns instead of always running `SELECT *` and pulling entire LOBs across the wire.

## 2. Two Reading Strategies: Materialization and Streaming

### 2.1. Full Materialization

Full materialization means the application asks JDBC to construct an object holding **the entire value** on the Java side before proceeding.

```java
byte[] image = rs.getBytes("picture");  // BLOB as byte[]
String text = rs.getString("body");     // CLOB as String
```

This is an **illustrative code snippet** inside `ResultSet rs` processing, not a standalone program. It works well when size is tightly bounded or when random access or multiple passes over the full content are needed. `getBytes()` and `getString()` can return `null` if the SQL value is `NULL`.

Materialization has these consequences:

- A BLOB of `N` bytes requires at least a `byte[]` proportional to `N`, in addition to driver buffers and copies made during processing or response writing.
- A CLOB creates a `String` proportional to character count and may require temporary memory for transcoding; do not assume one character always takes one byte.
- Loading many LOB rows into a `List` at once can multiply heap demand substantially.
- Once you have `byte[]` or `String`, the application can use the data after closing the `ResultSet`/connection because it is Java data detached from JDBC resources.

### 2.2. Streaming

Streaming means the application consumes data **piece by piece** while keeping the required JDBC resources open and valid.

```java
InputStream binary = rs.getBinaryStream("picture");
Reader characters = rs.getCharacterStream("body");
```

These two lines merely illustrate the APIs. With streams obtained from `ResultSet`, **finish consuming one stream before calling a getter for another column**; per the JDBC contract, calling the next getter may close the current stream. For BLOBs use `InputStream` reading into a `byte[] buffer`; for CLOBs use `Reader` reading into a `char[] buffer`.

Streaming can keep **application-side processing memory** close to the buffer size (e.g., 8 KiB) rather than the size of the entire LOB, provided the application forwards chunks directly to a file, network, or incremental processor. However:

- **Stream APIs do not guarantee the driver/database actually transfers chunks over the network.** The driver may prefetch or buffer the LOB partially or completely. You must check the driver version, configuration, and test real memory usage.
- Total data transferred from database to destination still depends on LOB size; streaming reduces holding all data in memory at once, it does not make data vanish.
- The connection/`ResultSet`/LOB locator may need to stay alive throughout the read; a slow-downloading user can tie up a database connection for a long time.
- `InputStream.readAllBytes()` or `InputStream.transferTo(new ByteArrayOutputStream())` **still collects the entire payload onto the heap**, even though the initial input was a stream.

### 2.3. Quick Comparison Table

| Criterion | Full Materialization | Streaming |
| --- | --- | --- |
| Typical APIs | `getBytes`, `getString`; `Blob.getBytes`, `Clob.getSubString` | `getBinaryStream`, `getCharacterStream`; `Blob/Clob` streams |
| Output object | `byte[]`, `String` | `InputStream`, `Reader` consumed while still open |
| App memory | Proportional to data size, potentially with copies | Can stay near buffer size if not accumulated and driver supports it |
| Random access | Convenient | Typically sequential; re-reading may require re-querying |
| Connection hold time | Can end right after materialization | Usually extends until reading finishes |
| Best suited for | Small thumbnails, bounded text, full-content processing | Large files, large exports, sequential processing, direct copying |

There is no universal MB threshold valid for every system. Thresholds must be based on concurrency, heap size, driver behavior, actual LOB sizes, connection-holding cost, and business requirements.

## 3. Corresponding JDBC APIs: `Blob`, `Clob`, and `ResultSet`

There are two approaches:

**Read directly from `ResultSet`:**

```java
byte[] allBytes = rs.getBytes(1);
String allText = rs.getString(2);

InputStream byteStream = rs.getBinaryStream(1);
Reader charStream = rs.getCharacterStream(2);
```

These are **alternative or properly sequenced calls**, not instructions to open all four sources simultaneously on a single row. When streaming, consume and close the source before moving to another getter.

**Obtain the LOB object first:**

```java
Blob blob = rs.getBlob("picture");
Clob clob = rs.getClob("body");
```

`java.sql.Blob` and `java.sql.Clob` model LOBs per the JDBC standard, often via a *locator* used by the driver to access data. For `Blob`:

- `length()` returns the **byte** count as a `long`.
- `getBytes(long pos, int length)` fetches a slice into a `byte[]`.
- `getBinaryStream()` returns an `InputStream`; has an overload taking `pos` and `length`.
- `free()` releases resources associated with the `Blob` when no longer needed.

For `Clob`:

- `length()` returns the **character** length described by JDBC/driver as a `long`.
- `getSubString(long pos, int length)` fetches a slice as a `String`.
- `getCharacterStream()` returns a `Reader`; has a slice overload.
- `free()` releases resources associated with the `Clob`.

**Both `getBytes(pos, length)` and `getSubString(pos, length)` use 1-based `pos`, not 0-based.** The `length` parameter is an `int`, so you cannot cast an arbitrary `long length()` to `int` to fetch a whole LOB. For large LOBs, read in slices or stream.

A safer snippet when a `Blob blob` has already been obtained and verified non-null:

```java
long size = blob.length();
long maxAllowed = 8L * 1024 * 1024; // 8 MiB: illustrative limit
if (size > maxAllowed) {
    throw new IllegalArgumentException("BLOB too large for full read");
}
byte[] all = blob.getBytes(1L, Math.toIntExact(size));
```

`Math.toIntExact` rejects a `long` exceeding `int` range, but the 8 MiB check beforehand is the **memory policy** of this example. Never rely solely on `int` limits to protect the heap. After using streams or copying data from a locator, close the stream and call `free()` when supported by the driver and `Blob`/`Clob` is no longer needed.

Do not call `getAsciiStream()` on a CLOB for Vietnamese/Unicode text: it only gives an ASCII representation stream and does not replace `getCharacterStream()` when full characters are needed.

## 4. Runnable Java 17 + H2 Example: Same Data, Two Reading Approaches

This example uses in-memory H2 so no external database server is needed. It requires **JDK 17+** and the **H2 2.x** JDBC driver jar (named `h2.jar` in the working directory). The JDBC driver is loaded from the classpath via Java Service Provider; no H2-specific imports are needed in code. Sample data is intentionally small for easy output verification; the same reading principles apply to large LOBs.

Create `LobReadDemo.java` with the full contents below:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class LobReadDemo {
    private static final long DOCUMENT_ID = 1L;

    public static void main(String[] args) throws Exception {
        try (Connection connection =
                DriverManager.getConnection("jdbc:h2:mem:lobdemo", "sa", "")) {
            createData(connection);
            readAllAtOnce(connection);
            readInChunks(connection);
        }
    }

    private static void createData(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute("""
                CREATE TABLE documents (
                    id BIGINT PRIMARY KEY,
                    picture BLOB,
                    body CLOB
                )
                """);
        }

        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO documents (id, picture, body) VALUES (?, ?, ?)")) {
            statement.setLong(1, DOCUMENT_ID);
            statement.setBytes(2, new byte[] {0, 1, 2, (byte) 0xFF});
            statement.setString(3, "Xin chào JDBC");
            statement.executeUpdate();
        }
    }

    private static void readAllAtOnce(Connection connection)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT picture, body FROM documents WHERE id = ?")) {
            statement.setLong(1, DOCUMENT_ID);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Document not found");
                }

                // Materialize the entire BLOB and CLOB onto the heap.
                byte[] bytes = rs.getBytes("picture");
                String text = rs.getString("body");

                if (bytes == null || text == null) {
                    throw new SQLException("Unexpected SQL NULL");
                }

                System.out.println("all_blob_bytes=" + bytes.length);
                System.out.println("all_clob_text=" + text);
            }
        }
    }

    private static void readInChunks(Connection connection)
            throws SQLException, IOException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT picture, body FROM documents WHERE id = ?")) {
            statement.setLong(1, DOCUMENT_ID);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Document not found");
                }

                long byteCount = 0;
                try (InputStream input = rs.getBinaryStream("picture")) {
                    if (input == null) {
                        throw new SQLException("BLOB is SQL NULL");
                    }
                    byte[] buffer = new byte[8192];
                    int size;
                    while ((size = input.read(buffer)) != -1) {
                        byteCount += size;
                    }
                } // Close the binary stream before reading another column.
                System.out.println("stream_blob_bytes=" + byteCount);

                long charCount = 0;
                try (Reader reader = rs.getCharacterStream("body")) {
                    if (reader == null) {
                        throw new SQLException("CLOB is SQL NULL");
                    }
                    char[] buffer = new char[4096];
                    int size;
                    while ((size = reader.read(buffer)) != -1) {
                        charCount += size;
                    }
                }
                System.out.println("stream_clob_chars=" + charCount);
            }
        }
    }
}
~~~

Compile from the directory containing `LobReadDemo.java`:

~~~bash
javac -encoding UTF-8 LobReadDemo.java
~~~

Run on Linux/macOS (using `:` as the classpath separator):

~~~bash
java -cp ".:h2.jar" LobReadDemo
~~~

Or on Windows PowerShell (using `;` as the classpath separator):

~~~powershell
java -cp ".;h2.jar" LobReadDemo
~~~

**Expected output with the created data:**

~~~text
all_blob_bytes=4
all_clob_text=Xin chào JDBC
stream_blob_bytes=4
stream_clob_chars=13
~~~

Because `"Xin chào JDBC"` is 13 UTF-16 code units long in this example, the loop over `Reader` counts 13. When supplementary characters like emojis appear, the number of Java `char` units read may differ from the number of Unicode code points visible to the user. Never equate characters, code points, UTF-8 bytes, and displayed glyphs.

**Why the example proves the difference:** `readAllAtOnce` constructs a `byte[]` and `String` and uses them after the getters return; `readInChunks` holds only a `byte[8192]` and `char[4096]`, counting chunks as read without collecting into large arrays. On 4 bytes and 13 chars both are fine; the memory advantage of the second approach becomes clear when LOB size grows and the driver does not preload the entire value.

In real programs, the streaming loop typically **writes data to a destination** or feeds chunks through a processor. The example above only counts to make output easy to check; it creates no files.

## 5. Streaming Shines When Transferring Data to a Real Destination

### 5.1. Copying a BLOB to a File

When `ResultSet rs` is positioned on the target row, the snippet below can write a BLOB to a file using `java.nio.file.Files`. This is an **illustrative snippet within an open ResultSet/Statement/Connection scope**:

~~~java
Path output = Path.of("download.bin");
try (InputStream source = rs.getBinaryStream("picture");
     OutputStream target = Files.newOutputStream(output)) {
    if (source == null) {
        throw new IllegalStateException("SQL NULL cannot be downloaded");
    }
    long bytesCopied = source.transferTo(target);
    System.out.println("bytesCopied=" + bytesCopied);
}
~~~

Imports required: `java.io.InputStream`, `java.io.OutputStream`, `java.nio.file.Path`, `java.nio.file.Files`. `InputStream.transferTo(OutputStream)` (Java 9+) copies sequentially; when the target is a `FileOutputStream`, it does not require holding the entire content in an application `byte[]`. **Do not open the final output file before verifying data exists**, or use a temporary file and atomically rename after a successful copy to avoid leaving corrupted files on transfer errors.

This example assumes the path is controlled by the application. In real services, validate destination paths, filesystem permissions, path traversal, disk space, and temp-file cleanup on failure.

### 5.2. Processing a CLOB via `Reader`

For text, `Reader` yields chunks of **characters**, not bytes. If writing to a UTF-8 file, specify the charset when creating the `Writer`:

~~~java
Path output = Path.of("article.txt");
try (Reader source = rs.getCharacterStream("body");
     Writer target = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
    if (source == null) {
        throw new IllegalStateException("SQL NULL cannot be exported");
    }
    long charsCopied = source.transferTo(target);
    System.out.println("charsCopied=" + charsCopied);
}
~~~

Imports required: `java.io.Reader`, `java.io.Writer`, `java.nio.charset.StandardCharsets`, and `Path`/`Files`. `Reader.transferTo(Writer)` returns **the number of Java `char` units transferred**; the resulting UTF-8 file may be more bytes. Never call `new String(byte[], charset)` on arbitrary binary chunks: a multi-byte UTF-8 character can be split across chunk boundaries. For CLOBs, use `Reader`; when genuinely reading a byte stream containing text, use `InputStreamReader` with an explicit charset and stateful decoder.

### 5.3. Operations That Accidentally Defeat Streaming

These patterns can end up **holding the entire LOB on the heap**:

~~~java
byte[] all = rs.getBinaryStream(1).readAllBytes();
ByteArrayOutputStream memory = new ByteArrayOutputStream();
rs.getBinaryStream(1).transferTo(memory);
StringWriter text = new StringWriter();
rs.getCharacterStream(2).transferTo(text);
~~~

This is only a **brief anti-pattern example**, not a sequence to run back-to-back on the same `ResultSet`. `readAllBytes`, `ByteArrayOutputStream`, and `StringWriter` all accumulate content in memory. Streaming only truly reduces application memory when **the destination or processor also operates incrementally**, such as a file, counter, checksum, incremental parser, or a network connection with backpressure.

## 6. Resource Lifecycle: The Easiest Part to Get Wrong with LOBs

LOBs may be represented by the driver using a locator pointing to database-side data; `Blob`/`Clob` objects are specified as having a lifecycle tied to the transaction that created them. Furthermore, streams returned from `ResultSet` depend on the `ResultSet` and statement resources. Therefore:

1. Open connection and statement, execute query.
2. Call `rs.next()`, verify a row exists; call the LOB getter.
3. **Read completely or process the desired part immediately while still open.**
4. Close `InputStream`/`Reader`, and free the `Blob`/`Clob` locator if one was obtained and the driver supports it.
5. Only then close `ResultSet`, `Statement`, and return the connection to the pool.

A common mistake:

~~~java
// BAD lifecycle design: method returns a stream after closing ResultSet.
InputStream fetchLater(Connection connection) throws SQLException {
    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT picture FROM documents WHERE id = 1");
         ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            return null;
        }
        return rs.getBinaryStream(1);
    } // ResultSet and PreparedStatement close here.
}
~~~

When the caller starts calling `read()` on the returned stream, the connection/result set may already be closed and the operation fails. Some drivers buffer all data, hiding **the bug in test environments**, yet this pattern violates the resource contract.

**Correct approach:** pass an `OutputStream`/`Writer` or a callback function into the query layer, perform copying or processing inside the callback, and return only **results independent of JDBC** (byte count, checksum, completed file path, metadata DTO). For small data, returning materialized `byte[]`/`String` is valid if sizes are capped.

Never hold JDBC `ResultSet`, `Blob`, `Clob`, `InputStream`, or `Reader` in a singleton Spring bean field or application cache as long-lived objects. In particular, returning a database stream directly to an async task or an HTTP response written after the repository method exits easily outlives the transaction/connection lifecycle.

### What Role Does a Transaction Play?

With some drivers, accessing a LOB locator may require **the transaction to remain open**. Auto-commit behavior, cursors, server-side LOB storage, commit/rollback behavior, and post-commit streaming capability vary across RDBMSs. If a read workflow requires a transaction, ensure it spans the entire read on the right connection/transaction manager. **Do not assume `@Transactional(readOnly = true)` preserves the transaction in another async thread**, because standard Spring transactions are bound to the current thread.

An HTTP request downloading a large file directly from the database can hold a pool connection until the client finishes downloading; with many slow clients, the pool can be exhausted. Consider time/size limits, storing content in object storage, or staging valid temporary files served from a separate store if download lifetimes are long. That is an architectural decision, not a prerequisite for every small LOB.

## 7. Spring JDBC: Using `JdbcTemplate` with Proper Lifecycle

`JdbcTemplate` manages connections, statements, `ResultSet`, and translates `SQLException` into `DataAccessException`. It **does not** magically make a JDBC stream safe after the callback finishes. Therefore, streaming reads must happen **inside** a `ResultSetExtractor` or `RowCallbackHandler`.

The following example is **a repository class in a Spring project** using `spring-jdbc`, `DataSource`, and an existing `documents` table. It shows both full materialization of a small BLOB and streaming copy of a large BLOB. Method `copyBlobTo` accepts a caller-managed `OutputStream` and **does not close the destination itself**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UncheckedIOException;

import org.springframework.dao.DataRetrievalFailureException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class DocumentLobRepository {
    private final JdbcTemplate jdbcTemplate;

    public DocumentLobRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public byte[] loadSmallBlob(long id) {
        return jdbcTemplate.queryForObject(
                "SELECT picture FROM documents WHERE id = ?",
                (rs, rowNum) -> rs.getBytes(1),
                id);
    }

    @Transactional(readOnly = true)
    public long copyBlobTo(long id, OutputStream destination) {
        Long copied = jdbcTemplate.query(
                "SELECT picture FROM documents WHERE id = ?",
                (ResultSetExtractor<Long>) rs -> {
                    if (!rs.next()) {
                        throw new EmptyResultDataAccessException(1);
                    }

                    try (InputStream input = rs.getBinaryStream(1)) {
                        if (input == null) {
                            throw new DataRetrievalFailureException(
                                    "Document BLOB is SQL NULL");
                        }
                        return input.transferTo(destination);
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                },
                id);
        return copied;
    }
}
~~~

**Key points to understand:**

- `loadSmallBlob` uses `queryForObject`/`getBytes`; reasonable when business policy guarantees small images. If no row is found, Spring throws an unexpected result size exception. If the column is SQL `NULL`, the return value may be `null`.
- `copyBlobTo` uses `ResultSetExtractor<Long>`: Spring keeps the `ResultSet` open while the callback transfers data to `destination`.
- `EmptyResultDataAccessException` indicates **no row found**; `DataRetrievalFailureException` here indicates **the row has a NULL BLOB**—two distinct situations.
- `IOException` is wrapped in `UncheckedIOException` because the `ResultSetExtractor` callback declares `SQLException` and `DataAccessException`, not checked `IOException`.
- Spring handles closing the connection/statement; the repository closes the `InputStream` it opened. The caller manages `destination` and must close it after the method returns.
- `@Transactional(readOnly = true)` expresses a read scope when invoked through a Spring proxy with an appropriate transaction manager; the annotation does not guarantee every driver truly streams or blocks writes at the DB.
- A callback copying to an HTTP response can block on slow-reading clients; under high concurrency, weigh the impact on the pool and connection hold time.

For CLOBs, replace `InputStream` with `Reader`, `OutputStream` with `Writer`, and `rs.getBinaryStream(1)` with `rs.getCharacterStream(1)`; `Reader.transferTo(Writer)` returns the number of character units transferred. If you need to map multiple rows and process each row, `RowCallbackHandler` is appropriate, but finish consuming **each row's** stream before Spring advances to the next row.

### On the Write Side: Full Materialization and Stream Writing Also Exist

For small files, you can insert with `PreparedStatement.setBytes(index, bytes)`, or small CLOBs with `setString(index, text)`. For large sources already available as streams:

~~~java
// Snippet inside a PreparedStatement callback or JDBC method.
ps.setLong(1, documentId);
ps.setBinaryStream(2, inputStream);
ps.setCharacterStream(3, reader);
ps.executeUpdate();
~~~

For drivers requiring the size upfront, JDBC provides overloads accepting `long length` and related variants. An input stream must stay open **until JDBC finishes consuming it during execute**, and the owner must close it. Never build a giant `byte[]` just to call `setBytes` when a stream source is already available. Also, do not assume `setBinaryStream` guarantees chunked transfer by the DB; verify the driver.

## 8. `NULL`, Length, and Unicode Text Data

These three cases are **different**:

1. **No row**: query returns zero rows; `rs.next()` returns `false`.
2. **Row exists, LOB is SQL `NULL`**: `getBytes`/`getString`/`getBinaryStream`/`getCharacterStream` can return `null`; `getBlob`/`getClob` can also return `null`.
3. **Row exists, empty LOB**: typically yields a 0-length array, empty string, or an immediately-ending stream; how empty LOBs are created/distinguished depends on the RDBMS.

Do not write `rs.getBinaryStream(...).transferTo(...)` without handling `null` if the column allows SQL `NULL`. Even when a column is `NOT NULL`, still distinguish the "no row found" case.

**Length:** `Blob.length()` counts bytes; `Clob.length()` counts characters per JDBC/DB; Java's `String.length()` and `Reader` counters use UTF-16 `char` units. Consequently, UTF-8 bytes on disk, Unicode code points, and user-perceived characters do not necessarily share the same count. For UI-constrained content, pick a consistent measurement unit and Unicode handling.

**Charset:** CLOBs are represented by JDBC as character data, so `Reader` avoids manual byte decoding in the application layer. If a source is a BLOB intentionally holding UTF-8 text, converting it to characters requires an explicit charset (e.g., `StandardCharsets.UTF_8`) and a decoder capable of handling characters split across chunk boundaries. Never use `Reader` on arbitrary binary bytes.

## 9. Performance Risks and Limits to Set

These considerations clarify LOB usage in production environments:

- **Size and concurrency:** 30 concurrent requests each materializing 40 MiB already require roughly 1.2 GiB of raw array data, before counting Java and driver buffers/copies. That is an arithmetic example of **minimum memory for those arrays alone**, not an actual heap measurement.
- **Buffer size:** typically start from a few KiB to tens of KiB (e.g., 8 KiB); measure throughput and latency instead of blindly increasing buffer size. Overly large buffers multiplied by concurrent requests also consume heap.
- **Driver may prefetch/buffer:** stream APIs do not self-verify chunked transfer. Monitor heap, GC, round trips, and the JDBC/DB driver in realistic environments.
- **Connection pool:** long streaming holds connections; set timeouts, size/rate limits where appropriate, and handle cancellation when clients disconnect.
- **No `SELECT *` in list queries:** query metadata and LOBs separately, by ID; optimize indexes and avoid fetching unused columns.
- **Compression/encoding:** do not recompress already compressed formats like JPEG/ZIP expecting meaningful savings; do not convert BLOBs to Base64 when raw bytes can be transferred directly, because Base64 inflates size.
- **Security:** enforce per-user authorization on LOB downloads, validate trusted MIME types/filenames, restrict file write directories, guard against path traversal, and avoid logging sensitive LOB content.
- **Data architecture:** for very large payloads or heavy download traffic, consider object storage and keep only keys, metadata, or short-lived signed URLs in the database. Choose based on business rules, backups, security, transactions, and cost.

## 10. Testing and Verification

A thorough LOB test suite should cover these cases:

| Case | Verification |
| --- | --- |
| Small BLOB with `0x00`, `0xFF`, non-printable bytes | Full read and streaming return **the exact same byte sequence** when written to `ByteArrayOutputStream` in a size-bounded test, or compare checksums |
| CLOB with Vietnamese text, newlines, emojis | Read-back content matches original without diacritic corruption; do not confuse byte count with character count |
| Empty LOB | Distinguish 0 bytes/0 characters from `NULL` |
| SQL `NULL` | Getters handle `null` without unexpected `NullPointerException` |
| Missing record for ID | Return proper "not found" status, not an empty file |
| LOB larger than full-read threshold | Reject per policy or switch to streaming; no overflow casting `long` to `int` |
| File write target fails mid-way | Stream/statement/connection closed, temp file cleaned up per policy |
| Multiple concurrent downloads | Measure heap, GC, database connections, pool wait time, and throughput |
| Early transaction termination | Ensure no stream depending on a closed ResultSet/connection is returned |

When comparing the two strategies, check **content** via checksum (for BLOB) or string/character comparison (for CLOB), not just length. Two different byte sequences can have the same length.

An integration test with the exact target JDBC driver and DBMS is essential to determine whether streaming truly reduces heap and how the driver handles locators, transactions, fetch size, charset, and `NULL`. Tests on H2 prove basic JDBC mechanics, **not that another driver shares the same memory or transaction behavior**.

## 11. Common Misconceptions

**"Just calling `getBinaryStream()` guarantees low RAM usage?"** Not necessarily. Streams let application code process sequentially, but the driver may buffer; moreover, feeding it to `readAllBytes()` materializes everything in the app anyway.

**"`Blob.getBytes(1, (int) blob.length())` is always safe?"** No. `length()` is a `long`; casting can corrupt the length and allocating a huge array can exhaust the heap. Cap size first and choose streaming when needed.

**"CLOB and BLOB only differ by SQL type name?"** No. CLOB holds characters, BLOB holds bytes. Transcoding rules, APIs, lengths, and data handling differ.

**"An `InputStream` returned from a repository can be read after `JdbcTemplate.query` finishes?"** Do not rely on this; Spring closes JDBC resources after the callback. Consume the stream inside the callback or return JDBC-independent data.

**"`@Transactional` on a synchronous controller automatically protects a `StreamingResponseBody` running later?"** Not guaranteed. Response writing may execute asynchronously on another thread, not inheriting the transaction bound to the thread that created the response. Design DB access scopes and data copying explicitly.

**"Increasing `fetchSize` always optimizes downloading one giant BLOB?"** No. Fetch size mainly tunes how the driver fetches **multiple rows**; single-LOB transfer behavior depends on other driver settings and mechanisms.

**"Reading a 200,000-character CLOB means downloading 200,000 bytes?"** No. Stored/transferred bytes depend on charset/encoding; Java `String`/`Reader` also use their own `char` units.

## 12. Self-Check Questions

1. A row has a 300 MiB BLOB, and the app only needs to write its bytes to a file. Why is `ResultSet.getBytes()` usually a poor choice? **Because it materializes a huge array; you can copy directly from `getBinaryStream()` to `OutputStream` with a small buffer**, keeping driver buffering and connection lifetime in mind.
2. A CLOB column contains the text "Chào bạn". Should you use `InputStream` or `Reader`? **`Reader`**, because character/Unicode handling is needed; use bytes only when an explicit encoding convention is established.
3. A repository returns a `Blob` locator to a service called after the transaction ends. Is that safe? **No guarantee**; locators typically depend on the transaction/connection. Process within an open scope or materialize small data under a size limit.
4. `rs.next()` is `true`, yet `rs.getBinaryStream("picture")` returns `null`. What does that mean? **The row exists and the column value is SQL `NULL`**, which is not the same as a 0-byte file.
5. In the H2 example, why do both approaches yield the same byte and character counts? **Because both read the same LOB value to the end**; the difference lies in how data is held/moved, not in its content.

## 13. References

- Java SE 17, `java.sql.Blob` — length, `getBytes`, `getBinaryStream`, `free`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Blob.html
- Java SE 17, `java.sql.Clob` — `getSubString`, `getCharacterStream`, `free`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Clob.html
- Java SE 17, `java.sql.ResultSet` — `getBytes`, `getString`, `getBinaryStream`, `getCharacterStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Spring Framework, `JdbcTemplate` and JDBC callbacks: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring `ResultSetExtractor<T>`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html
- H2 Database, `BLOB`/`CLOB` data types: https://h2database.github.io/html/datatypes.html