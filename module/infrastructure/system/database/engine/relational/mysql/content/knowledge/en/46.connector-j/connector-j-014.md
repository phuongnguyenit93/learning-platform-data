# Reading and Writing TEXT/BLOB or JSON and max_allowed_packet Limits

Within the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plans, query tuning, authorization, backups, and relational database operational concerns. This lesson guides Java applications using MySQL Connector/J to store and read large text, binary data, and JSON while handling packet size limits between the JDBC client and MySQL Server.

When working with large payloads, choose the right column type and the right JDBC API. Text should flow through `String` or `Reader`, binary data through `byte[]` or `InputStream`, and JSON can be serialized to a string and bound to a `JSON` column. For large payloads, streaming lowers JVM memory pressure. However, streaming does not eliminate packet limits, transaction overhead, binary logging, or storage costs on the MySQL side.

## 1. Distinguishing TEXT, BLOB, and JSON

MySQL provides text and binary types with different capacity limits:

| Type | Maximum data-type capacity | Purpose |
|---|---:|---|
| `TINYTEXT` / `TINYBLOB` | 255 bytes | Very small text or binary data. |
| `TEXT` / `BLOB` | 65,535 bytes | Small/medium text or binary content. |
| `MEDIUMTEXT` / `MEDIUMBLOB` | 16,777,215 bytes | Larger content, such as documents or images. |
| `LONGTEXT` / `LONGBLOB` | 4,294,967,295 bytes | Very large content, within practical server, packet, and resource limits. |
| `JSON` | Subject to MySQL document, packet, and resource limits | Structured JSON requiring validation and path-based queries. |

TEXT/BLOB limits are measured in bytes. For TEXT, the actual character count depends on the character set: one UTF-8 character can occupy one to four bytes. Use `OCTET_LENGTH()` to measure bytes and `CHAR_LENGTH()` to measure characters.

```sql
SELECT
    OCTET_LENGTH(description) AS bytes_used,
    CHAR_LENGTH(description) AS characters_used
FROM article
WHERE id = 1001;
```

`TEXT` stores strings using the column's character set and collation. `BLOB` stores raw bytes without charset/collation semantics. Never use `BLOB` to store UTF-8 text and convert arbitrarily via `String`; decoding must use the exact charset. Conversely, never use `TEXT` for binary files such as images, PDFs, or archives.

### When to Use JSON

MySQL has a native `JSON` type. On insert or update, MySQL parses and rejects invalid JSON documents; values are stored in an internal binary format optimized for element access. Storing a JSON string in `TEXT` gives none of the JSON type's automatic validation or storage properties.

Example schema:

```sql
CREATE TABLE document_archive (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body MEDIUMTEXT,
    file_content LONGBLOB,
    metadata JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

In this example, `body` stores long text, `file_content` stores file bytes, and `metadata` stores structured attributes such as document type, tags, or source details. Avoid embedding entire large files inside JSON as Base64: that inflates size and wastes CPU encoding/decoding. For very large files or CDN/object-storage distribution, consider storing files in object storage and keeping only object keys, checksums, MIME types, sizes, and metadata in MySQL.

## 2. Mapping MySQL Types to Java via Connector/J

Connector/J supports converting many MySQL types to Java types. Common mappings:

| MySQL Type | Typical Java type | Preferred JDBC APIs |
|---|---|---|
| `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | `String` or `Reader` | `setString()`, `setCharacterStream()`, `getString()`, `getCharacterStream()` |
| `BLOB`, `MEDIUMBLOB`, `LONGBLOB` | `byte[]`, `InputStream`, `Blob` | `setBytes()`, `setBinaryStream()`, `setBlob()`, `getBinaryStream()`, `getBlob()` |
| `JSON` | `String` | `setString()`, `getString()`, then parse with your application's JSON library |

For small payloads, `String` and `byte[]` are convenient. For large payloads, avoid `getBytes()` or `getString()` unless the entire value must reside in heap. Use streams to read or write incrementally.

MySQL JSON maps to `String` in Connector/J's type conversion table. JDBC has no standard `java.sql.JSON` type; applications typically use Jackson, Gson, or an equivalent library to convert between Java objects and JSON strings.

## 3. Writing Large TEXT with PreparedStatement

For moderate text, use `setString()`:

```java
String sql = "INSERT INTO article (title, body) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, title);
    ps.setString(2, bodyText);
    ps.executeUpdate();
}
```

Connector/J converts Java Unicode strings to the connection's character encoding. Verify database, table, and column charset/collation, especially when storing Vietnamese or non-BMP characters. On modern MySQL, `utf8mb4` is the standard choice for full Unicode support.

For large content, read from a file with a `Reader` and bind via `setCharacterStream()`:

```java
String sql = "INSERT INTO article (title, body) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql);
     Reader bodyReader = Files.newBufferedReader(
         Path.of("article-body.txt"), StandardCharsets.UTF_8)) {

    ps.setString(1, "User Guide");
    ps.setCharacterStream(2, bodyReader);
    ps.executeUpdate();
}
```

Keep the `Reader` open until `executeUpdate()` finishes. For length-accepting overloads, the length passed to `setCharacterStream()` is the character count, not the byte count. Never pass `Files.size()` as the character count because UTF-8 has variable byte lengths per character.

If custom encoding control is needed for TEXT/CLOB, Connector/J has the `clobCharacterEncoding` property; otherwise the driver uses the configured connection encoding. Test accented and special characters with write/read round trips to catch transcoding bugs.

## 4. Writing Large BLOBs with InputStream

For binary files, use `setBinaryStream()` or `setBlob()` to stream bytes. Example:

```java
String sql = "INSERT INTO document_archive (title, file_content) VALUES (?, ?)";
Path file = Path.of("manual.pdf");

try (PreparedStatement ps = connection.prepareStatement(sql);
     InputStream input = Files.newInputStream(file)) {

    ps.setString(1, "Manual PDF");
    ps.setBinaryStream(2, input, Files.size(file));
    ps.executeUpdate();
}
```

Overloads accepting a `long` length support file sizes beyond `int` range. The length must match the exact byte count produced by the stream. If the length is wrong, data may be truncated or the write may fail. Keep the stream open until the statement finishes; close resources afterward using try-with-resources.

Do not load large files into `byte[]` just to call `setBytes()`. That allocates a large copy in heap and can cause `OutOfMemoryError` when multiple requests upload concurrently. Streaming reduces client-side heap buffering, though the server must still receive, process, and write the full payload.

### Reading a BLOB to a File

```java
String sql = "SELECT file_content FROM document_archive WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, documentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (InputStream input = rs.getBinaryStream("file_content");
                 OutputStream output = Files.newOutputStream(
                     Path.of("downloaded-manual.pdf"))) {
                input.transferTo(output); // Java 9+
            }
        }
    }
}
```

Read the stream before advancing to the next row or closing `ResultSet`/`Statement`. If Java 8 compatibility is required, replace `InputStream.transferTo()` with a buffered read/write loop to `OutputStream`.

### Reading Large TEXT with Reader

```java
String sql = "SELECT body FROM article WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, articleId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (Reader reader = rs.getCharacterStream("body");
                 Writer writer = Files.newBufferedWriter(
                     Path.of("article-copy.txt"), StandardCharsets.UTF_8)) {
                char[] buffer = new char[8192];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, count);
                }
            }
        }
    }
}
```

## 5. Reading Multiple Rows with Large BLOBs: Column Streaming vs. ResultSet Streaming

Two concepts are often confused:

- `getBinaryStream()` or `getCharacterStream()` provides a stream-based API to read a single column's value.
- ResultSet streaming controls how the driver fetches rows from the server, avoiding buffering the entire result set in memory before processing.

If a query returns thousands of rows, each with a large BLOB, using `getBinaryStream()` alone may not bound total memory for the ResultSet. Connector/J provides `useCursorFetch` to enable cursor-based fetching with server-side prepared statements. Enable `useCursorFetch=true` and set a positive fetch size on the statement:

```java
String url = "jdbc:mysql://db.example.com:3306/shop?useCursorFetch=true";

try (Connection connection = DriverManager.getConnection(url, properties);
     PreparedStatement ps = connection.prepareStatement(
         "SELECT id, file_content FROM document_archive ORDER BY id")) {

    ps.setFetchSize(50);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            Path target = Path.of("export", id + ".bin");

            try (InputStream input = rs.getBinaryStream("file_content");
                 OutputStream output = Files.newOutputStream(target)) {
                input.transferTo(output);
            }
        }
    }
}
```

When `useCursorFetch=true`, Connector/J automatically enables `useServerPrepStmts=true` because cursor fetching requires server-side prepared statements. `setFetchSize(50)` specifies how many rows the driver fetches per batch, not a BLOB byte limit. Choose fetch size based on row sizes and available memory; shrink fetch size when each row holds a large BLOB.

If the application only fetches a single record by primary key, cursor fetch is usually unnecessary. Test on your exact Connector/J version and workload. Any open stream consumes network, connection slots, and time; never hold a connection pool slot longer than necessary.

## 6. Writing and Reading JSON

MySQL validates JSON when writing to a `JSON` column. Applications should serialize Java objects using a JSON library rather than concatenating strings or manually escaping quotes.

Example using Jackson:

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(metadataObject);

String sql = "INSERT INTO document_archive (title, metadata) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "Monthly Report");
    ps.setString(2, json);
    ps.executeUpdate();
}
```

Read JSON via `getString()` and parse into an object or `JsonNode`:

```java
String sql = "SELECT metadata FROM document_archive WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, documentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String json = rs.getString("metadata");
            JsonNode metadata = mapper.readTree(json);
        }
    }
}
```

Malformed JSON is rejected by MySQL with the corresponding JSON error. You can inspect type and storage footprint with SQL:

```sql
SELECT
    JSON_TYPE(metadata) AS root_type,
    JSON_STORAGE_SIZE(metadata) AS storage_bytes
FROM document_archive
WHERE id = 1001;
```

Query or update a property using JSON functions:

```sql
UPDATE document_archive
SET metadata = JSON_SET(metadata, '$.status', ?)
WHERE id = ?;
```

Bind the status value with `PreparedStatement.setString()`. The JSON path in this example is a SQL constant; if paths come from user input, validate them strictly per application rules and never concatenate untrusted strings into SQL. When filtering frequently by a JSON field, consider a generated column with an index instead of scanning full documents.

## 7. What Is max_allowed_packet?

`max_allowed_packet` caps the maximum size of a protocol packet, an intermediate string constructed inside MySQL, or a parameter sent via a prepared statement's long-data transfer mechanism. This limit affects queries with large strings, BLOBs, large JSON payloads, and other transfers.

In MySQL 8.4, the server default is 64 MiB (`67,108,864` bytes), the minimum is 1,024 bytes, and the maximum is 1 GiB (`1,073,741,824` bytes). Other versions may have different defaults, so inspect the runtime value instead of assuming.

Check configuration:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW SESSION VARIABLES LIKE 'max_allowed_packet';
```

`max_allowed_packet` has both GLOBAL and SESSION scope and is dynamically adjustable. The SESSION value is read-only and initialized from the GLOBAL value at connection establishment. Changing GLOBAL does not automatically update existing connections' session values; connection pools must recreate physical connections to adopt the new value. Nor will the server send a client a packet larger than the current GLOBAL limit.

Column type limits and packet limits are two separate concepts. `LONGBLOB` allows very large storage capacity by data type, but that does not mean a single JDBC request can send arbitrarily huge payloads. Account for `max_allowed_packet`, client limits, chunk sizes, server resources, and how the driver transmits data.

## 8. Adjusting max_allowed_packet on the Server

If a valid workload requires packets larger than the current limit, raise the GLOBAL value:

```sql
SET GLOBAL max_allowed_packet = 268435456;
```

This sets 256 MiB and requires appropriate system variable privileges. To persist across restarts, use `SET PERSIST` on supported versions:

```sql
SET PERSIST max_allowed_packet = 268435456;
```

Or configure it in the option file:

```ini
[mysqld]
max_allowed_packet=256M
```

Values should be multiples of 1,024; MySQL rounds non-multiples down to the nearest multiple. The protocol ceiling is 1 GiB. Do not set 1 GiB out of habit: packet buffers can grow on demand per connection, so excessive values combined with high concurrency can significantly increase memory consumption risk.

After updating, verify:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
```

Then open a fresh JDBC connection and recheck the session value. With a connection pool, recycle the pool or ensure old physical connections are replaced safely.

## 9. Adjusting Limits on Connector/J

Connector/J provides the `maxAllowedPacket` connection property. When left unconfigured, the driver uses the server's `max_allowed_packet` to initialize its send limit upon connecting. When explicitly set, setting it higher than the server limit has no effect.

JDBC URL example:

```text
jdbc:mysql://db.example.com:3306/shop?maxAllowedPacket=268435456&useServerPrepStmts=true
```

Or configure via `Properties`:

```java
Properties properties = new Properties();
properties.setProperty("user", dbUser);
properties.setProperty("password", dbPassword);
properties.setProperty("maxAllowedPacket", "268435456");
properties.setProperty("useServerPrepStmts", "true");
```

Never set the client limit higher than the server's expecting the driver to raise the server limit. Coordinate server, client, and pool settings together. If `max_allowed_packet` increases on the server while the pool retains old connections, existing sessions may continue enforcing the previous limit.

### Connector/J Stream-Related Properties

| Property | Default per Connector/J docs | Effect |
|---|---:|---|
| `useServerPrepStmts` | `false` | Uses server-side prepared statements when supported by the server. |
| `useStreamLengthsInPrepStmts` | `true` | Honors lengths passed to `set*Stream()` methods. |
| `blobSendChunkSize` | 1 MiB | Chunk size when sending BLOB/CLOB via server-prepared statements; must not exceed `maxAllowedPacket` (driver adjusts if exceeded). |
| `useCursorFetch` | `false` | Uses cursor fetching when enabled with a positive fetch size; automatically enables server-side prepared statements. |

Example configuration for upload streaming:

```text
jdbc:mysql://db.example.com:3306/shop?useServerPrepStmts=true&maxAllowedPacket=268435456&blobSendChunkSize=1048576
```

`blobSendChunkSize` is the chunk size for sending BLOB/CLOB over server-prepared statements, not a total column capacity limit. When reusing a server-prepared statement that bound a large stream and switching that parameter to a smaller value, call `clearParameters()` and rebind all parameters before the next execute to reset the prepared statement's long-data state.

## 10. Why Streaming Does Not Replace max_allowed_packet

Streaming spares the application from holding an entire payload in a single byte array or string. Connector/J can send BLOB/CLOB values in chunks when using server-side prepared statements. Nonetheless, every packet/chunk must still obey protocol limits and client/server configuration. An oversized SQL string, oversized parameter, or huge result can still hit limits.

Beyond packet limits, consider:

- **JVM heap:** avoid making extra copies of the same payload via `readAllBytes()`, `getBytes()`, or Base64-encoding entire files.
- **Concurrent connections:** multiple concurrent large requests amplify buffer memory, network load, and server resource usage.
- **Transactions:** writing large BLOBs prolongs transactions, increases redo/undo volume, and can hold locks longer.
- **Binary logs and replication:** large transactions produce large logs, increasing replica transfer and apply latency.
- **Backup/restore:** large payloads inflate backup size, restore duration, and cross-region transfer costs.
- **Network timeouts:** slow file transfers may require adjusted timeouts, but never use huge timeouts to mask network or server failures.

For batch inserts, calculate total byte size per batch rather than capping row counts alone. A batch of 100 tiny metadata rows behaves nothing like 100 rows containing multi-megabyte BLOBs. Shrink batches or split runs when needed; never enable `rewriteBatchedStatements` without measuring rewritten statement sizes and packet impact.

## 11. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| `Packet for query is too large` / `ER_NET_PACKET_TOO_LARGE` | Packet or parameter exceeds server `max_allowed_packet`. | Check GLOBAL and SESSION values; raise reasonably if payload is valid; reopen connections. |
| `Communications link failure` or lost connection during upload | Server closed connection after oversized packet, network timeout, or stream failure. | Check server error logs, payload size, timeouts, and stream state; do not just raise timeouts. |
| Connector/J reports packet too large even after raising server limit | Client `maxAllowedPacket` is lower or physical connections still hold old session limits. | Check Connector/J properties, open fresh connections, and recycle pool. |
| File stored in BLOB is corrupted | Used character API for binary data, converted via String, wrong stream length, or encoding altered bytes. | Use `setBinaryStream()` with exact byte length; compare checksums before/after. |
| Accented TEXT is garbled | Incompatible charset/collation or `clobCharacterEncoding`. | Check connection charset, column charset, and stream encoding; test with accented UTF-8 data. |
| JSON insert reports syntax error | Invalid JSON string or manual serialization with bad escaping. | Serialize with a JSON library; bind via `setString()` and inspect server errors. |
| JVM heap spikes during export | Used `getBytes()`/`getString()` or buffered entire ResultSet before processing. | Stream large columns; enable cursor fetch with a positive fetch size when reading many rows. |
| Re-running prepared statement with previous stream fails | Stream already consumed/closed after execute or long-data state not reset. | Open a new stream; when switching from large to small parameters on server-prepared statements, call `clearParameters()` and rebind all parameters. |

When the server detects an oversized packet, it may close the connection. The application may receive a communication exception rather than a simple SQL error. Inspect MySQL error logs together with the full JDBC exception chain to identify the cause. Never blindly retry an oversized payload because retrying does not shrink the packet.

## 12. Hands-On Exercise

Create a table storing documents with text, binary files, and JSON metadata. Use a Java application and MySQL Connector/J to perform:

1. Create table `document_archive` with `MEDIUMTEXT`, `LONGBLOB`, and `JSON`.
2. Read a UTF-8 file using `Reader` and write its content to the TEXT column with `setCharacterStream()`.
3. Read a PDF file using `InputStream`, write it to BLOB via `setBinaryStream()`, and pass the exact byte length.
4. Serialize a Java object to JSON with Jackson, write with `setString()`, read back with `getString()`, and parse into `JsonNode`.
5. Read the BLOB out to a file using `getBinaryStream()`; compare SHA-256 checksums of the original and downloaded files.
6. Read multiple BLOB rows using `useCursorFetch=true` and `setFetchSize(10)`; observe heap and processing time.
7. Check `max_allowed_packet` at GLOBAL and SESSION scope; test uploading a payload exceeding the current limit in a test environment to observe the error.
8. Raise the server limit to a reasonable value, adjust `maxAllowedPacket` if needed, open a fresh connection, and confirm the upload succeeds.
9. Experiment with different batch sizes, recording packet sizes, durations, JVM heap, and replica lag if present.
10. Write a summary explaining when to use TEXT, BLOB, or JSON; when streaming is required; and how to determine actual system packet limits.

After this exercise, learners should be able to explain why BLOBs require binary APIs, why JSON is bound as strings over JDBC, why column capacity limits do not equal packet limits, and why changing GLOBAL `max_allowed_packet` requires recreating physical connections for sessions to pick up the new value. This forms the foundation for handling large payloads via Connector/J while controlling memory, reliability, and performance.

## Official References

- [MySQL Connector/J: Java, JDBC, and MySQL Types](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-type-conversions.html)
- [MySQL Connector/J: BLOB/CLOB Processing Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-blob-clob-processing.html)
- [MySQL Connector/J: Networking Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-networking.html)
- [MySQL Connector/J: Prepared Statement Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-prepared-statements.html)
- [MySQL Connector/J: Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html)
- [MySQL 8.4 Reference Manual: max_allowed_packet](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual: JSON Data Type](https://dev.mysql.com/doc/refman/8.4/en/json.html)
