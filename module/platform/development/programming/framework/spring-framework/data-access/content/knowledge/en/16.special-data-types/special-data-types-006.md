# Choosing the Right LOB API for Your Spring Version and JDBC Driver

In Spring Framework Data Access, a **LOB (Large OBject)** is large data stored in a database in binary or character form. When writing images, PDFs, attachments, or long documents with Spring JDBC, the question is not just "use `BLOB` or `CLOB`?", but also: **which Spring version is running, what exact SQL type is the column, which write/read methods does the JDBC driver support, and should large payloads be streamed or loaded fully into memory?**

An example from older documentation may use `LobHandler`, `LobCreator`, or `SqlLobValue`. A modern example from Spring 6.1.4 onward may use `SqlBinaryValue` and `SqlCharacterValue`, or direct JDBC methods. These two API families **are not simple drop-in class renames**: choosing `Types.BLOB`, `Types.CLOB`, `Types.LONGVARBINARY`, or `Types.LONGVARCHAR`, handling streams, and database differences must still be verified.

Lesson objectives: identify the right API for your Spring version; distinguish real `BLOB/CLOB` from `BYTEA/TEXT/VARBINARY`; decide when to use `byte[]`/`String`, streams, or JDBC callbacks; maintain proper stream and transaction lifecycles; and test your choice against a real driver.

## 1. Identify the LOB Kind Before Choosing an API

| Data and Column | Common Read/Write APIs | Notes |
| --- | --- | --- |
| Binary data: SQL `BLOB` column | `PreparedStatement.setBlob(...)` or `setBinaryStream(...)` when driver accepts; `ResultSet.getBlob(...)`, `getBinaryStream(...)`, `getBytes(...)` | `Blob` may be an object/locator requiring an open connection |
| Long binary as `VARBINARY`, `LONGVARBINARY`, PostgreSQL `BYTEA` | `setBytes(...)`, `setBinaryStream(...)` and `getBytes(...)`/`getBinaryStream(...)` | Do not declare `Types.BLOB` if the DB does not use a true BLOB |
| Long text as `CLOB` | `setClob(...)`, `setCharacterStream(...)`, `getClob(...)`, `getCharacterStream(...)`, `getString(...)` | Character stream is `Reader`, distinct from binary `InputStream` |
| Long text as `LONGVARCHAR`, `TEXT`/`LONGTEXT` | `setString(...)`, `setCharacterStream(...)`, `getString(...)`/`getCharacterStream(...)` | DB column type may be TEXT rather than CLOB |
| International text as `NCLOB` | `NClob` APIs, `setNCharacterStream(...)`, `getNCharacterStream(...)` if driver and column require | Do not assume all DBs/drivers support `NCLOB` identically |

**LOB is a data concept; `java.sql.Blob` and `java.sql.Clob` are JDBC interface types; the physical column type determines which API fits.** For example, PostgreSQL `BYTEA` and PostgreSQL Large Objects referenced by `OID` are **two different storage mechanisms**. A MySQL `TEXT` column can hold long strings without necessarily requiring JDBC `Clob`.

For small, bounded payloads, `byte[]` or `String` is usually simpler. For large files, prefer streams/callbacks to avoid holding multiple copies of the entire content on the heap at once. "Using streams" also does not guarantee the driver will not buffer: verify memory usage and driver behavior.

## 2. Spring Version Matrix: Which API Should You Use?

| Spring Framework Version | Available APIs and Status | Usage Guidance |
| --- | --- | --- |
| Spring 5.3.x and Spring 6.0.x | Historical APIs like `LobHandler`, `DefaultLobHandler`, `LobCreator`, `SqlLobValue` are widely used; direct JDBC is always available | Maintain when existing systems rely on driver-specific handling; can use `JdbcTemplate` with `PreparedStatement`/`ResultSet` directly |
| Spring 6.1.0–6.1.3 | Traditional LOB APIs remain; **does not yet have** `SqlBinaryValue`/`SqlCharacterValue` | Do not copy code using the two new classes into projects not upgraded to at least 6.1.4 |
| From Spring **6.1.4** through 6.1.x | Has `org.springframework.jdbc.core.support.SqlBinaryValue` and `SqlCharacterValue`; legacy APIs remain | Prefer trying the two new value classes for standard writes, paired with matching SQL types |
| Spring **6.2.x** | `LobHandler`, `DefaultLobHandler`, `LobCreator`, `SqlLobValue`, and legacy LOB callback helpers are marked `@Deprecated(since = "6.2")`; the two new classes remain supported | Choose `SqlBinaryValue`/`SqlCharacterValue` or direct JDBC for new code; minimize new dependencies on deprecated APIs |
| Spring 7.x | Check Javadoc of the **exact running artifact version**: some legacy APIs may still appear in deprecated state in published releases | Do not assume deprecated means removed, nor rely on it for future-version compatibility |

**The key milestones to remember are 6.1.4 (new APIs added) and 6.2 (old APIs deprecated).** Spring Boot version numbers and Spring Framework version numbers are not the same; Boot apps usually manage framework versions via dependency management. Inspect the actual dependency tree instead of guessing from tutorials.

You can check the framework version in Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc
~~~

In Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-jdbc --configuration runtimeClasspath
~~~

In multi-module projects, run the command in the module that holds the JDBC dependency. Both commands **inspect dependencies**, they do not prove the API works against the database.

### The Modern API Group

- `SqlBinaryValue`: constructed from `byte[]`, `InputStream + length`, `InputStreamSource + length`, or a Spring `Resource`; implements `SqlTypeValue`, used as a parameter in `JdbcTemplate`/`JdbcClient`.
- `SqlCharacterValue`: constructed from `CharSequence`, `char[]`, `Reader + length`, or an ASCII `InputStream + length`; also implements `SqlTypeValue`.
- `SqlParameterValue`: **optionally** wraps an explicit SQL type, e.g., `new SqlParameterValue(Types.BLOB, new SqlBinaryValue(bytes))`. Only pass `Types.BLOB` when the column/driver is a true BLOB; similarly `Types.CLOB` for a true CLOB.
- `JdbcTemplate` with `PreparedStatement` callbacks: use when you need explicit control over `setBytes`, `setBinaryStream`, `setBlob`, `setClob`, stream length, or driver exceptions.
- On read, `ResultSet.getBytes`, `getString`, `getBinaryStream`, and `getCharacterStream` are the natural reading paths; Spring callbacks close the ResultSet/statement upon completion.

`JdbcClient` (introduced in Spring 6.1) provides a fluent query API but **does not alter JDBC driver rules for LOBs**. This lesson focuses on `JdbcTemplate` to keep operations explicit; the same type-selection and resource-management principles apply when using `JdbcClient`.

## 3. API Selection Process: Ask the Right Four Questions

**Question 1 — Which Spring Framework version is running?** If lower than 6.1.4, do not use `SqlBinaryValue`/`SqlCharacterValue`. From 6.1.4 onward, prefer them for standard writes. From 6.2 onward, avoid writing new code tightly coupled to `SqlLobValue`/`LobHandler` unless a specific compatibility reason exists.

**Question 2 — What type is the SQL column?** Distinguish true `BLOB` from `BYTEA`/`VARBINARY`, and true `CLOB` from `TEXT`/`LONGVARCHAR`. Identify the SQL type from the DDL and driver. Calling something "LOB" in business terms is not enough to assume `Types.BLOB`.

**Question 3 — Size and transport?** For a few KB already in memory, `byte[]`/`String` is simple. For tens/hundreds of MB, consider streams and driver support for `setBinaryStream`/`setBlob(InputStream, length)` or `setCharacterStream`/`setClob(Reader,length)`. Note that length is in bytes for binary streams, whereas it is **character count** for character streams.

**Question 4 — Which API does the real driver support?** If `SqlBinaryValue` delegates to a JDBC setter that the driver does not handle properly for that column, use a `PreparedStatement` callback to invoke the required setter directly. Measure and test with the exact database, JDBC driver, version, SQL type, transaction mode, and realistic payload sizes.

~~~text
Spring < 6.1.4?
  ├─ Yes → JDBC PreparedStatement / legacy LobHandler-SqlLobValue if appropriate
  └─ No  → Prefer SqlBinaryValue / SqlCharacterValue for writes
                |
                v
       Is DDL true BLOB/CLOB?
         ├─ Yes → try Types.BLOB / Types.CLOB + matching driver
         └─ No  → use actual binary/text type;
                  do not force BLOB/CLOB
                |
                v
     Does driver handle stream/locator cleanly?
         ├─ Yes → keep API simple, run round-trip tests
         └─ No  → PreparedStatement callback + appropriate setter
~~~

This diagram is a decision guide; **testing against the real driver** is always mandatory before claiming compatibility.

## 4. Runnable Java 17 Example with Spring 6.2 and H2

We create a real table with `BLOB` and `CLOB`, write using `SqlBinaryValue`/`SqlCharacterValue` with `SqlParameterValue` specifying the SQL types, and read back using JDBC getters. H2 lets the example run without an external database server.

Structure:

~~~text
lob-api-demo/
├── pom.xml
└── src/main/java/example/LobApiDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>lob-api-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.4.240</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.LobApiDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/example/LobApiDemo.java`:

~~~java
package example;

import java.sql.Types;
import java.util.Arrays;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.support.SqlBinaryValue;
import org.springframework.jdbc.core.support.SqlCharacterValue;

public final class LobApiDemo {

    record Loaded(byte[] payload, String description) {}

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:lob_api_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE lob_entry (
                    id BIGINT PRIMARY KEY,
                    payload BLOB NOT NULL,
                    description CLOB NOT NULL
                )
                """);

        byte[] bytes = {0, 1, 2, 127, (byte) 255, 42};
        String description = "Xin chào – LOB tiếng Việt";

        int affected = jdbc.update(
                "INSERT INTO lob_entry (id, payload, description) VALUES (?, ?, ?)",
                7L,
                new SqlParameterValue(
                        Types.BLOB,
                        new SqlBinaryValue(bytes)
                ),
                new SqlParameterValue(
                        Types.CLOB,
                        new SqlCharacterValue(description)
                )
        );

        Loaded loaded = jdbc.queryForObject(
                "SELECT payload, description FROM lob_entry WHERE id = ?",
                (rs, rowNum) -> new Loaded(
                        rs.getBytes("payload"),
                        rs.getString("description")
                ),
                7L
        );

        System.out.println("rows=" + affected);
        System.out.println("binaryBytes=" + loaded.payload().length);
        System.out.println("binaryMatches="
                + Arrays.equals(bytes, loaded.payload()));
        System.out.println("textMatches="
                + description.equals(loaded.description()));
    }
}
~~~

With JDK 17+ and Maven in the `lob-api-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program in the H2 environment above:

~~~text
rows=1
binaryBytes=6
binaryMatches=true
textMatches=true
~~~

**Explanation:** The H2 table has true `BLOB`/`CLOB` columns, so `Types.BLOB`/`Types.CLOB` fit this example. Spring's two value objects prepare the parameters; `JdbcTemplate` creates the `PreparedStatement`, sends it to H2, executes `INSERT`, and then the `ResultSet` mapping uses `getBytes` and `getString`. `Arrays.equals` verifies the binary content byte-for-byte, including `0xFF` — without turning a binary payload into a `String`. `String.equals` verifies exact Unicode text.

This is a **small, in-memory round-trip** to make the API clear. Running cleanly on H2 does not prove PostgreSQL, Oracle, or SQL Server will accept the exact same SQL type hints. Run separate integration tests on your target database.

### Why Not Always Pass `Types.BLOB`?

When a column is a regular binary type (not a JDBC BLOB), the driver may require `setBytes` or `setBinaryStream` and a SQL type such as `Types.LONGVARBINARY`. For text columns like `TEXT`/`LONGVARCHAR`, a SQL type such as `Types.LONGVARCHAR` may fit better than `Types.CLOB`. `SqlBinaryValue` and `SqlCharacterValue` can often work **without forcing a type** because many drivers handle them automatically; if you add a type hint, base it on the DDL and driver. Do not apply `Types.BLOB` uniformly across every DB merely because the content is an image.

## 5. Streaming When Data Exceeds Convenient Memory Size

### 5.1. Writing Streams with the New Classes

When transferring file contents, `SqlBinaryValue(InputStream, long length)` takes a byte stream and byte length. For text, `SqlCharacterValue(Reader, long length)` takes a `Reader` and **character** count. You can pass `-1` if the length is unknown, though not every driver supports unknown-length overloads equally well.

The snippet below **illustrates usage in an application that already has `JdbcTemplate jdbc`, table `lob_entry`, and id 7**, not a second standalone program:

~~~java
import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Types;

import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.support.SqlBinaryValue;
import org.springframework.jdbc.core.support.SqlCharacterValue;

// binaryFile and textFile are application-controlled Paths.
try (InputStream binaryInput = Files.newInputStream(binaryFile);
     Reader textReader = Files.newBufferedReader(
             textFile, StandardCharsets.UTF_8)) {

    long bytes = Files.size(binaryFile);

    jdbc.update(
            "UPDATE lob_entry SET payload = ?, description = ? WHERE id = ?",
            new SqlParameterValue(
                    Types.BLOB, new SqlBinaryValue(binaryInput, bytes)),
            new SqlParameterValue(
                    Types.CLOB, new SqlCharacterValue(textReader, -1)),
            7L
    );
}
~~~

Wrap `try-with-resources` **around the JDBC call**, without closing `InputStream`/`Reader` before `update` runs. Note that `Files.size(textFile)` returns **byte** count, not Unicode character count, so do not pass it directly as the `Reader length`. If the driver demands an exact character length, compute/know the character count ahead of time or pick a loading strategy matching business needs. With `-1`, verify whether the JDBC driver supports unknown-length streams.

`SqlBinaryValue(Resource)` can obtain length via `Resource.contentLength()`. However, not every `Resource` knows its length cheaply; a one-shot source may be consumed when queried for size. Use a re-openable source or pass an explicit length. Do not assume `InputStreamSource` or `Resource` can always open fresh streams endlessly.

### 5.2. Reading Streams: Consume While ResultSet Is Still Open

The snippet below writes a BLOB to an output file; it resides inside an application method with existing `JdbcTemplate jdbc`, `long id`, and `Path target`:

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Boolean found = jdbc.query(
        "SELECT payload FROM lob_entry WHERE id = ?",
        rs -> {
            if (!rs.next()) {
                return false;
            }
            try (InputStream in = rs.getBinaryStream("payload")) {
                if (in == null) {
                    return false;
                }
                Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING);
                return true;
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        },
        id
);
~~~

`ResultSetExtractor` explicitly calls `rs.next()` and reads the entire stream inside the callback; `JdbcTemplate` may close the ResultSet/statement when the callback ends. **Never return an `InputStream` or `Reader` obtained from `ResultSet` outside the callback** to be read after the transaction/connection has closed. For real target files, validate `target` paths and ensure the overwrite policy suits the app. When reading CLOBs, use `rs.getCharacterStream(...)` with `Reader` and `Writer` using the proper charset/encoding instead of treating everything as ASCII.

`ResultSet.getBlob`/`getClob` may return database-managed locators; locators can require an active transaction and explicit resource cleanup (`Blob.free()`/`Clob.free()`) depending on driver capabilities. When straightforward streaming suffices and the driver supports it, `getBinaryStream`/`getCharacterStream` inside the callback is usually easier to manage.

## 6. When You Need Direct JDBC Setter Control

Spring's convenience classes cannot erase differences across drivers. If a driver requires `setBlob` instead of `setBinaryStream`, or needs a special type, use `PreparedStatementCreator`/`PreparedStatementSetter`:

~~~java
// Illustration: inside a method receiving JdbcTemplate jdbc,
// an open InputStream source, and a known long byteLength.
int updated = jdbc.update(connection -> {
    var ps = connection.prepareStatement(
            "UPDATE lob_entry SET payload = ? WHERE id = ?");
    ps.setBlob(1, source, byteLength);
    ps.setLong(2, 7L);
    return ps;
});
~~~

This snippet **depends on JDBC 4.x and the driver's `setBlob(int, InputStream, long)` support**. For byte-array columns, you can substitute `ps.setBinaryStream(1, source, byteLength)` or `ps.setBytes(1, bytes)` if required by the driver. `source` must remain open during the `jdbc.update` call. `JdbcTemplate` manages closing the statement/connection per its contract; the application manages external resources (the stream) per its chosen lifecycle.

For `CLOB`, compare `setClob(index, reader, charLength)` with `setCharacterStream(index, reader, charLength)` and test the driver. Do not "fix" type errors by arbitrarily switching from `setCharacterStream` to `setBinaryStream`: one deals with Unicode characters, the other with bytes.

### Notes on JDBC Stream Length

- `setBinaryStream(..., long length)`: byte length; writing fewer/more bytes than expected can raise an error or truncate data depending on the driver.
- `setCharacterStream(..., long length)`: character length; UTF-8 byte length is **not** equal to character count for many Vietnamese strings.
- Length-less overloads exist since JDBC 4, but must be tested with the real driver. Do not assume all drivers/DBs implement them uniformly.
- Never read a whole file into `byte[]` only to wrap it in a stream if the goal is saving heap. That still holds the content in memory.
- Streaming does not mean the transaction can close before writing finishes; locators and large objects must respect transaction boundaries.

## 7. What If the Project Already Uses `SqlLobValue`/`LobHandler`?

This is **compatibility code for legacy projects**, not a recommended example for new Spring 6.2+ code:

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.support.SqlLobValue;
import org.springframework.jdbc.support.lob.DefaultLobHandler;
import org.springframework.jdbc.support.lob.LobHandler;

// Illustrative snippet assuming jdbc, bytes, and text are initialized.
LobHandler lobHandler = new DefaultLobHandler();

jdbc.update(
        "INSERT INTO lob_entry (id, payload, description) VALUES (?, ?, ?)",
        new Object[] {
                7L,
                new SqlLobValue(bytes, lobHandler),
                new SqlLobValue(text, lobHandler)
        },
        new int[] {Types.BIGINT, Types.BLOB, Types.CLOB}
);
~~~

In older versions, `LobHandler` supplied the LOB read/write strategy and `LobCreator` could hold resources requiring cleanup after statement execution. `SqlLobValue` works with `LobCreator` and Spring utilities handle post-call cleanup; never keep a `LobCreator` around across threads/transactions.

In Spring 6.2, this group of classes is deprecated because the new APIs and direct JDBC already cover most LOB needs. **Deprecated does not mean "removed" or "all legacy code is broken".** If a project relies on a special driver strategy, verify behavior before migrating rather than changing everything blindly just to silence warnings.

### Legacy Options Commonly Seen in Older Guides

`DefaultLobHandler` used to offer several flags:

| Legacy Setting | Actual Meaning | What to Check Before Replacing |
| --- | --- | --- |
| Default | Uses `setBinaryStream`/`setCharacterStream` or direct JDBC accessors | Does the driver support them cleanly for the target BLOB/CLOB column? |
| `setWrapAsLob(true)` | Wraps values as `Blob`/`Clob` and calls LOB setters | Previously used in examples for PostgreSQL **OID**; do not apply to PostgreSQL `BYTEA` |
| `setStreamAsLob(true)` | Uses JDBC 4 APIs like `setBlob(InputStream, ...)`/`setClob(Reader, ...)` | Does the driver implement the corresponding overloads? |
| `setCreateTemporaryLob(true)` | Creates a temporary LOB managed by JDBC/database when needed | Is this still needed on the current driver, and how is cleanup handled? |

When migrating to `SqlBinaryValue`/`SqlCharacterValue`, check whether the driver still needs a specialized setter. The two new classes **are not a clone carrying all the customization flags of `DefaultLobHandler`**; for special cases, invoking the exact JDBC setter is the clearest choice.

## 8. Important Differences Across Databases and JDBC Drivers

| Database / Storage | How to Start | Avoid Confusion |
| --- | --- | --- |
| **PostgreSQL `BYTEA`** | `setBytes`/`getBytes` or `setBinaryStream`/`getBinaryStream`; evaluate `SqlBinaryValue` per driver and real SQL type | Do not mechanically pass `Types.BLOB`; `BYTEA` differs from Large Object OID |
| **PostgreSQL Large Object/`OID`** | Use pgJDBC's Large Object mechanism or appropriate `Blob` strategy; open an explicit transaction | OID stores a reference to a separate Large Object, requires a transaction, and may require explicit LOB deletion when deleting rows |
| **Oracle `BLOB`/`CLOB`** | Try `SqlBinaryValue`/`SqlCharacterValue` with matching SQL types and modern JDBC driver; if needed, use `setBlob/setClob`, driver temporary LOBs | Oracle driver limits, locators, stream support, and behavior change across versions |
| **MySQL/MariaDB `BLOB/LONGBLOB`, `TEXT/LONGTEXT`** | Try `setBytes`/`setBinaryStream` and `setString`/`setCharacterStream` or matching wrappers | Do not assume TEXT is JDBC CLOB; column size limits, encoding, and packet size also apply |
| **H2 `BLOB/CLOB`** | Suitable for demos, `SqlBinaryValue`/`SqlCharacterValue` + `Types.BLOB/CLOB` or standard JDBC | Passing H2 tests does not prove production compatibility |
| **SQL Server `VARBINARY(MAX)`/`NVARCHAR(MAX)`** | Use APIs suited for binary/Unicode and Microsoft JDBC driver behavior | Do not blindly tag all MAX columns as JDBC CLOB/BLOB; test realistic large sizes |

PostgreSQL illustrates how **picking the wrong API can violate the entire storage model**, not just hurt performance. pgJDBC distinguishes `BYTEA` from Large Objects (OID): `getBytes/setBytes` works for BYTEA, whereas Large Objects use a separate API or driver-supported `Blob` handling and must run inside a transaction. Deleting a row containing an OID **does not automatically** delete the Large Object itself — lifecycle cleanup is required. This is why you should never copy `DefaultLobHandler.setWrapAsLob(true)` from an old article and apply it to every PostgreSQL binary column.

**A version-specific detail:** Spring 6.2's Javadoc for `SqlBinaryValue` explicitly notes not using `Types.BLOB` for PostgreSQL `BYTEA` columns; if a type must be declared with this wrapper, there are specific driver rules documented. Consequently, the safe, clear starting choice for BYTEA is usually `PreparedStatement.setBytes` or `setBinaryStream` per pgJDBC, before testing wrappers with integration tests. Avoid forcing a single SQL type across all drivers.

## 9. How Data Lifecycle and Transactions Affect API Choice

A LOB upload/download involves more than just SQL types:

1. **ResultSet/Connection boundary.** JDBC streams/locators may become invalid once the ResultSet, statement, transaction, or connection closes. With `JdbcTemplate`, read completely inside the callback if streaming.
2. **Transactions.** Some databases, notably PostgreSQL Large Objects, require an active transaction. `@Transactional` only takes effect on calls routed through a Spring proxy with a matching transaction manager; putting the annotation on an unmanaged method guarantees nothing.
3. **Input stream source.** Keep the source open until JDBC finishes consuming it; if a provider reads slowly, plan for timeouts, size limits, and file descriptor cleanup.
4. **Actual length.** Pick a length-aware method when the driver requires it; distinguish byte count from character count. Missing length should never be "solved" by passing UTF-8 byte count to `Reader`.
5. **Freeing locators.** When using `Blob`/`Clob` objects and the driver holds special resources, call `free()` properly and avoid passing locators across thread/transaction boundaries.
6. **Memory and throughput.** Measure heap, GC, speed, and buffer copies. An API with "stream" in its name does not guarantee zero-copy or zero internal buffering.
7. **Business reliability.** For large uploads, consider timeouts, retries, and post-write checksum verification; avoid blind retries that create duplicate rows or orphan Large Objects outside the row.

If data is so large that storing it in the database incurs prohibitive cost, that is a separate storage-architecture problem. Within this lesson, we assume the database has already been chosen as the store, and focus on picking the right JDBC API.

## 10. Error Checklist and Troubleshooting

| Symptom | Check First |
| --- | --- |
| IDE reports missing `SqlBinaryValue` or `SqlCharacterValue` | Spring Framework must be **6.1.4+**; inspect actual dependencies rather than trusting a tutorial version |
| Spring 6.2 warns deprecated on `LobHandler`/`SqlLobValue` | This is the API status; consider moving to the new value classes and running driver integration tests |
| `Invalid column type`, cast error from binary to OID/BLOB | Compare SQL column type and JDBC type; on PostgreSQL distinguish `BYTEA` and `OID` |
| `SQLFeatureNotSupportedException` calling `setBlob`/`setClob` | Driver lacks that overload; try `setBinaryStream`, `setCharacterStream`, or driver-recommended methods |
| Stream write fails or truncates data | Stream closed early, wrong length, driver requires length, file modified while measuring size, timeout/driver limits |
| CLOB containing Vietnamese turns into `?`/garbled characters | Use `Reader`/`Writer` and proper encoding; do not coerce all text to ASCII; check collation/charset |
| `LOB cannot be used after transaction ends` or locator errors | Reading/writing outside connection/transaction lifecycle or returning stream outside callback; consume inside callback |
| Uploads of a few MB work but hundreds of MB cause OOM | Something reads into `byte[]`/`String`, driver buffers internally, or many concurrent uploads; measure memory and limit requests |
| H2 tests pass green but production fails | DDL, JDBC driver, SQL type, setter, and transaction behavior differ; add integration tests on target DB |
| Deleting PostgreSQL OID row does not shrink LO storage | Separate Large Object was not unlinked; implement proper lifecycle cleanup |
| Using `SqlParameterValue(Types.BLOB, ...)` on `TEXT`/`BYTEA` column | Type hint mismatches storage type; choose the right type or use an explicit JDBC setter |

### What Information to Gather When Debugging?

- Exact framework version (`spring-jdbc` and related Spring jars), driver artifact + version, JDBC URL (redacting secrets).
- Exact column DDL, especially `BLOB`/`CLOB` vs. `BYTEA`/`OID`/`TEXT`.
- Setter used (`setBlob`, `setBinaryStream`, `setBytes`…), `Types.*` type hint, input form (`byte[]`/`InputStream`/`Reader`), and passed length.
- SQLState, vendor error code, `SQLException`/`DataAccessException` chain; keep logs free of raw file contents.
- Whether a transaction is active, whether streams close early, and whether normal vs. unusually large sizes behave differently.
- If the driver has dedicated stream/buffer/LO settings, test the exact configuration used in production.

Diagnosing with those facts is far more effective than randomly toggling `DefaultLobHandler` flags.

## 11. Compatibility Testing Before Switching APIs

An integration test for LOB API selection should run against **the exact target database and JDBC driver**, not H2 alone:

1. Create the schema with real migrations; record the column's SQL type and `spring-jdbc` version.
2. Write and read back **`byte[]` containing `0x00`, `0xFF`, and non-character bytes**, comparing byte-for-byte or by checksum. Never convert binary data to a string for comparison.
3. Write and read back text with Vietnamese diacritics, emojis, newlines, and punctuation; verify Unicode/encoding.
4. Test `NULL`, empty `0-byte` payloads, multi-KB, and multi-MB payloads; if permitted, test above typical driver/DB thresholds.
5. For streaming, verify the source does not close early, length is accurate, the stream is read inside the callback, and resources close on both success and failure.
6. For OID/locators, verify transactions and cleanup; inspect DB state after commit and rollback.
7. Measure heap, read/write latency, and connection hold times under concurrent requests. Do not conclude a stream uses "zero RAM" merely because a streaming API was called.
8. When upgrading 6.1.x to 6.2.x, selectively migrate `SqlLobValue` to `SqlBinaryValue`/`SqlCharacterValue`; compare identical datasets on the real DB and monitor driver errors.

The desired QA outcome is not "zero deprecation warnings", but **an API aligned with your framework version, SQL columns matching parameter binding, lossless round-trip data, and sound memory and transaction behavior**.

## 12. Self-Check Questions

**1. A Spring 6.1.3 project copies `new SqlBinaryValue(bytes)` and fails to compile because the class is missing. Why?** — Because `SqlBinaryValue` was introduced in Spring **6.1.4**. Upgrade the framework version or use direct JDBC / an API compatible with the current version.

**2. A Spring 6.2 project uses `SqlLobValue` and still runs, though the IDE warns it is deprecated. Has the API been removed?** — No. "Deprecated since 6.2" signals you should move to the newer API for new code; legacy code may still work. Migration requires real testing.

**3. PostgreSQL has a `BYTEA` column. Should every binary parameter be forced to `Types.BLOB`?** — No. `BYTEA` and Large Object `OID` are different. For BYTEA, pgJDBC supports `setBytes/setBinaryStream` and `getBytes/getBinaryStream`; verify any wrapper type hints if used.

**4. A UTF-8 file occupies 1,200 bytes. Is passing `length=1200` to `SqlCharacterValue(Reader, length)` guaranteed to be correct?** — No. `Reader` length measures **characters**, not file bytes. For multi-byte/Unicode text, the two numbers can differ.

**5. Should `JdbcTemplate.query(...)` return `rs.getBinaryStream(...)` for the controller to process afterward?** — No, if the callback closes the ResultSet/connection before the controller reads it. Consume the stream inside the proper lifecycle, or explicitly design streaming with clear resource management.

## Official References

- [Spring Framework 6.2 — SqlBinaryValue Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/support/SqlBinaryValue.html) — available since 6.1.4, constructors and SQL type rules.
- [Spring Framework 6.2 — SqlCharacterValue Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/support/SqlCharacterValue.html) — CharSequence, Reader, length, and SQL types.
- [Spring Framework 6.2 — Deprecated API List](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/deprecated-list.html) — `LobHandler`, `LobCreator`, `SqlLobValue`, and legacy helpers.
- [Spring Framework — JDBC Parameter Handling](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html) — handling BLOB/CLOB and legacy patterns.
- [pgJDBC — Storing Binary Data](https://jdbc.postgresql.org/documentation/binary-data/) — distinguishing `BYTEA` from Large Objects/`OID`, transactions, and cleanup.
