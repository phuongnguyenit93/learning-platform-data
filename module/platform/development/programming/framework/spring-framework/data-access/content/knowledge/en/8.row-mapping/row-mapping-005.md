# RowCallbackHandler: Processing Row by Row Without Collecting Everything Into Memory

> **Context:** Spring Framework → JDBC → **Result Mapping**. This lesson explains `org.springframework.jdbc.core.RowCallbackHandler`, how `JdbcTemplate` invokes it for **each current row** of a `ResultSet`, and how to design a statistics or export task to **avoid building a `List` holding all results in application memory**. Important: row-by-row processing at the Java layer **does not automatically guarantee the JDBC driver/DBMS fetches data in batches**; see the sections on fetch size, transactions, and driver characteristics as well.

## 1. The Problem to Solve

Suppose the `sale` table has several million transactions. The requirement is to read paid transactions, calculate total revenue, and export a CSV. The familiar way of writing it:

~~~java
// Illustrative fragment: SaleMapper and jdbc are already defined.
List<Sale> sales = jdbc.query(
    "SELECT id, customer, amount FROM sale WHERE status = ?",
    saleMapper,
    "PAID"
);

for (Sale sale : sales) {
    // Sum amounts or write CSV.
}
~~~

`RowMapper<Sale>` is very useful when the application **truly needs a list of `Sale` objects**. However, with `query(..., RowMapper<T>)` returning `List<T>`, `JdbcTemplate` collects all mapped objects before returning to the caller. As the row count grows, the list, each object, and related strings can occupy substantial memory; if it exceeds heap capacity, there is a risk of `OutOfMemoryError`.

If the application only needs to **process each row and discard its detailed state**, you can switch to `RowCallbackHandler`:

~~~java
// Illustrative fragment: sum is a locally scoped accumulator.
jdbc.query(
    "SELECT amount FROM sale WHERE status = ?",
    (RowCallbackHandler) rs -> sum.add(rs.getBigDecimal("amount")),
    "PAID"
);
~~~

The callback is invoked for each row; it does not return a `Sale`, and `JdbcTemplate` **does not build a `List<Sale>` on the callback's behalf**. If `sum` only holds a running total, business state size grows very little with row count. If the callback itself calls `list.add(...)` for every row, it creates a large list on its own and loses this benefit.

**The right goal:** Avoid keeping all rows in the **application heap** when you only need to aggregate, validate, export line by line, or forward to a controlled downstream consumer. **Goal requiring extra conditions:** Avoid keeping all rows in the **JDBC driver buffer**, because that depends on driver fetch behavior and transactions.

## 2. Exact Contract of `RowCallbackHandler`

It is a functional interface in Spring JDBC:

~~~java
package org.springframework.jdbc.core;

@FunctionalInterface
public interface RowCallbackHandler {
    void processRow(java.sql.ResultSet rs)
        throws java.sql.SQLException;
}
~~~

This has five consequences:

1. **Receives `ResultSet`:** `JdbcTemplate` has already moved the cursor to the row being processed.
2. **Returns `void`:** The callback performs side effects or updates an externally owned accumulator; it does not return objects for `JdbcTemplate` to collect.
3. **Must not call `rs.next()`:** `JdbcTemplate` already advances the cursor between rows. Calling `next()` yourself skips rows or breaks the loop's expectations.
4. **May throw `SQLException`:** When an error occurs reading a JDBC column, let the exception propagate; `JdbcTemplate` handles and translates it according to Spring's mechanism.
5. **Is a synchronous callback of the query operation:** `jdbc.query(..., handler)` invokes the handler along the result-processing path and only finishes once all rows are processed or an error occurs. It is not an API that runs asynchronously on its own.

Minimal example to count rows:

~~~java
import org.springframework.jdbc.core.RowCallbackHandler;

final long[] count = {0L};
RowCallbackHandler handler = rs -> {
    count[0]++;
};

jdbc.query("SELECT id FROM sale", handler);
System.out.println("Row count = " + count[0]);
~~~

`long[]` here is a **local holder** allowing the lambda to update the counter in Java. It holds only one number, not row data. In production code, a clearly named accumulator class—or `LongAdder` when concurrency is truly involved—is usually clearer; this JDBC callback itself is not implicitly run in parallel across rows.

**Remember:** If you only need the total row count, a SQL query `SELECT COUNT(*) FROM sale` is usually more efficient because the database returns a single value; a callback is appropriate when counting accompanies per-row processing that SQL aggregates cannot easily replace.

## 3. How Does `JdbcTemplate` Coordinate the Loop?

Picture the conceptually equivalent algorithm:

~~~java
// PSEUDOCODE explaining the mechanism, not JdbcTemplate source code.
ResultSet rs = statement.executeQuery();
while (rs.next()) {
    handler.processRow(rs);
}
~~~

The developer **only writes the body of `processRow`**, not the `while (rs.next())` loop inside the callback. `JdbcTemplate` also handles many practical steps the pseudocode cannot show: obtaining a `Connection` matching the Spring transaction, creating the `Statement`/`PreparedStatement`, applying settings like fetch size/timeout, handling and translating `SQLException`, closing the `ResultSet`/`Statement`, and releasing the connection per context.

~~~mermaid
flowchart TD
    A["Service/Repository calls JdbcTemplate.query"] --> B["JdbcTemplate acquires Connection"]
    B --> C["Create and execute PreparedStatement"]
    C --> D["ResultSet is opened"]
    D --> E{"Does ResultSet have more rows?"}
    E -- "Yes" --> F["JdbcTemplate advances to current row"]
    F --> G["RowCallbackHandler.processRow(rs)"]
    G --> H["Keep only needed accumulator/output"]
    H --> E
    E -- "Done / error" --> I["Close ResultSet/Statement, release Connection"]
    I --> J["query returns void or throws exception"]
~~~

Between handler invocations, previous row data **is not automatically retained in any `List` created by `RowCallbackHandler`**. However, if the callback uses an `ArrayList`, a per-ID `Map`, a `StringBuilder` holding the entire CSV, or caches every row, the heap still grows linearly. **The API enables memory-efficient processing; actual behavior depends on the code inside the callback.**

### Avoid Confusing Resource Ownership

Inside the callback, do not call `rs.close()`, `rs.next()`, `connection.commit()`, `dataSource.close()`, or modify the `ResultSet` in a way that breaks the loop. Read the current row's column values, check required data, update a small state, or send output safely. `JdbcTemplate` cleans up JDBC resources when the query finishes.

## 4. Comparing with RowMapper, ResultSetExtractor, and Stream

| Approach | Main callback | Who controls the cursor? | Common result shape | Strengths | Memory notes |
| --- | --- | --- | --- | --- | --- |
| `query(..., RowMapper<T>)` | `T mapRow(ResultSet, int)` | JdbcTemplate | `List<T>` | Cleanly retrieves a domain/DTO list | `List` retains an object per row |
| `query(..., RowCallbackHandler)` | `void processRow(ResultSet)` | JdbcTemplate | `void`; state held by callback | Statistics, validation, line-by-line export | Can stay O(1) or O(batch) if callback does not accumulate everything |
| `query(..., ResultSetExtractor<T>)` | `T extractData(ResultSet)` | Extractor itself | Any type `T` | Full control over a `ResultSet`, building complex structures | Depends on extractor algorithm |
| `queryForStream(..., RowMapper<T>)` | Mapping in Java Stream | Framework / Stream | `Stream<T>` | Lazy processing; integrates with Stream API | Stream must be closed; driver may buffer |
| `SELECT COUNT/SUM/GROUP BY` | No per-row callback needed | DBMS | One/a few summary rows | Pushes aggregation down to the database | Often transfers far less data back |

If each row needs to become an independent object returned by an API, `RowMapper` is the usual choice. If you only need to count, sum, validate conditions, or write output, `RowCallbackHandler` fits well. If you need manual loop control, hierarchical grouping, or complex multi-row handling, consider `ResultSetExtractor`.

**Two kinds of “row-by-row processing”:** `RowMapper` is also **called per row**, yet the `query` overload returns a `List` retaining every row's result. `RowCallbackHandler` creates no `List` at the framework layer, and its work can release each row's data right after processing.

## 5. Commonly Used `JdbcTemplate.query` Overloads

### 5.1. Static SQL Without Parameters

~~~java
RowCallbackHandler handler = rs -> {
    System.out.println(rs.getLong("id"));
};
jdbc.query("SELECT id FROM sale ORDER BY id", handler);
~~~

This is the overload `void query(String sql, RowCallbackHandler rch)`. `System.out.println` should only be used for small sample data; printing millions of lines to the console can be very slow.

### 5.2. SQL with `?` Parameters

~~~java
RowCallbackHandler handler = rs -> {
    // Only read the already-positioned row.
    consume(rs.getLong("id"), rs.getBigDecimal("amount"));
};

jdbc.query(
    "SELECT id, amount FROM sale WHERE status = ? ORDER BY id",
    handler,
    "PAID"
);
~~~

This is the overload `void query(String sql, RowCallbackHandler rch, Object... args)`. Parameters are bound into the `PreparedStatement`; do not concatenate `status` directly into SQL. `consume(...)` is an illustrative helper and must be defined where the fragment is used.

### 5.3. With `PreparedStatementSetter` to Set Fetch Size

~~~java
PreparedStatementSetter setter = ps -> {
    ps.setString(1, "PAID");
    ps.setFetchSize(200);
};

RowCallbackHandler handler = rs ->
    consume(rs.getLong("id"), rs.getBigDecimal("amount"));

jdbc.query(
    "SELECT id, amount FROM sale WHERE status = ? ORDER BY id",
    setter,
    handler
);
~~~

This is the overload `void query(String sql, PreparedStatementSetter pss, RowCallbackHandler rch)`. `setFetchSize(200)` is a **hint/request to the driver**, not a guarantee that it will hold at most 200 rows. You must verify with the actual driver and transaction.

### 5.4. Customizing Statement Creation

There is `void query(PreparedStatementCreator psc, RowCallbackHandler rch)`:

~~~java
PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "SELECT id, amount FROM sale WHERE status = ? ORDER BY id",
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY
    );
    ps.setString(1, "PAID");
    ps.setFetchSize(200);
    return ps;
};
RowCallbackHandler handler = rs ->
    consume(rs.getLong("id"), rs.getBigDecimal("amount"));

jdbc.query(creator, handler);
~~~

The creator is passed the `Connection` chosen by Spring; do not acquire a separate new connection that breaks the current transaction. If SQL and parameters are standard, prefer the simpler overloads.

**Do not use an overload returning `List<T>` and discard the List** expecting to save heap: the list has already been constructed and populated before the call finishes.

## 6. Memory Usage: What Is Actually Saved?

Suppose `SELECT` returns N rows, and each mapped object occupies an average of M bytes (excluding List overhead, strings, references, internal arrays, and JDBC buffers).

- **`List<Sale>`:** Data retained by the Java application typically scales roughly as O(N × M).
- **Accumulating `RowCallbackHandler`:** Keeping only `long count` and `BigDecimal total`, application-layer logical state is roughly O(1) in N (ignoring tiny arithmetic growth as the total gets huge).
- **Line-by-line CSV `RowCallbackHandler`:** Keeps a bounded I/O buffer and current row data, instead of assembling the entire file in a `StringBuilder`.
- **JDBC Driver:** May fetch the entire `ResultSet` into the heap before Spring calls the handler; if so, **end-to-end memory can still approach O(N)** even though the callback is lean.
- **DBMS:** Queries with `ORDER BY`, joins, or aggregates may use server-side memory or temporary disk. `RowCallbackHandler` does not automatically reduce that cost.

Therefore, the accurate description is:

> **`RowCallbackHandler` avoids `JdbcTemplate` creating a `List` containing every result object and allows immediate per-row processing. To ensure the data stream into the JVM is not buffered all at once by the driver, proper JDBC/driver configuration is also required.**

In real measurements, look at **heap used, row count, driver fetch size, connection hold time, DB session/transaction, and network bytes**, not just whether the code uses a `List`.

## 7. Runnable Example: Spring Boot, H2, Statistics, and Line-by-Line CSV Export

To clearly observe callback invocations and application-layer memory behavior, the example below seeds 10,000 test transactions, filters 5,000 `PAID` transactions, sums revenue, and writes a CSV file directly inside the callback.

**Environment:** Java 21, Gradle, Spring Boot 3.3.5, Spring JDBC/HikariCP, H2. The project is a console application, needing no web server. The H2 example proves **no `Sale` list is built at the Java layer**, but is not proof that the H2 driver uses cursor streaming identically to PostgreSQL/MySQL.

### 7.1. File Structure

~~~text
row-callback-demo/
├── build.gradle
└── src/main/
    ├── java/com/example/rowcallback/
    │   ├── RowCallbackDemoApplication.java
    │   └── SaleRepository.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 7.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Spring Boot Starter JDBC provides a preconfigured `JdbcTemplate` from the `DataSource`. H2 is used to run standalone without installing a database server.

### 7.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:row_callback;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

The H2 database is freshly created when the application starts in a new JVM. `DB_CLOSE_DELAY=-1` keeps the in-memory database alive even if all connections are temporarily returned to the pool, without altering `RowCallbackHandler`'s contract.

### 7.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE sale (
    id BIGINT PRIMARY KEY,
    customer VARCHAR(60) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(16) NOT NULL
);
~~~

The table is created empty; the Java application inserts data once at startup. No additional `data.sql` file is needed.

### 7.5. Repository: `SaleRepository.java`

~~~java
package com.example.rowcallback;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Repository;

@Repository
public class SaleRepository {
    private final JdbcTemplate jdbc;

    public SaleRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Summary(long rows, BigDecimal total) {}

    public Summary summarize(String status) {
        Accumulator accumulator = new Accumulator();

        PreparedStatementSetter params = ps -> {
            ps.setString(1, status);
            ps.setFetchSize(200);
        };

        RowCallbackHandler handler =
            rs -> accumulator.accept(rs.getBigDecimal("amount"));

        jdbc.query(
            "SELECT amount FROM sale WHERE status = ? ORDER BY id",
            params,
            handler
        );

        return accumulator.snapshot();
    }

    public long exportCsv(String status, Path path) throws IOException {
        try (BufferedWriter writer =
                 Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {

            writer.write("id,customer,amount,status");
            writer.newLine();

            final long[] exported = {0L};

            PreparedStatementSetter params = ps -> {
                ps.setString(1, status);
                ps.setFetchSize(200);
            };

            RowCallbackHandler handler = rs -> {
                try {
                    writer.write(Long.toString(rs.getLong("id")));
                    writer.write(",");
                    writer.write(csv(rs.getString("customer")));
                    writer.write(",");
                    writer.write(
                        rs.getBigDecimal("amount").toPlainString()
                    );
                    writer.write(",");
                    writer.write(csv(rs.getString("status")));
                    writer.newLine();
                    exported[0]++;
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            };

            jdbc.query(
                "SELECT id, customer, amount, status " +
                "FROM sale WHERE status = ? ORDER BY id",
                params,
                handler
            );

            return exported[0];
        }
    }

    private static final class Accumulator {
        private long rows = 0L;
        private BigDecimal total = BigDecimal.ZERO;

        void accept(BigDecimal amount) {
            if (amount == null) {
                throw new IllegalStateException("Amount must not be NULL");
            }
            rows++;
            total = total.add(amount);
        }

        Summary snapshot() {
            return new Summary(rows, total);
        }
    }

    private static String csv(String value) {
        if (value.indexOf(',') < 0
                && value.indexOf('"') < 0
                && value.indexOf('\r') < 0
                && value.indexOf('\n') < 0) {
            return value;
        }
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }
}
~~~

**Code analysis:**

- `Accumulator` holds strictly two fields, `rows` and `total`, keeping no list of invoices. `snapshot()` runs only after `JdbcTemplate.query` completes.
- `PreparedStatementSetter` binds `status` and sets fetch size. Each query creates a local setter and handler, without sharing accumulators across requests.
- `RowCallbackHandler` only reads columns **of the current row**. There is no `rs.next()`, `List<Sale>`, `readAllBytes()`, or `StringBuilder` holding the entire CSV.
- `BufferedWriter` writes one row at a time to the file. The writer has a small bounded buffer and is closed by `try-with-resources` after the query ends.
- `IOException` is a checked exception not in `processRow`'s signature; therefore the callback wraps file-write errors in `UncheckedIOException` to abort the query and propagate failure to the caller. `SQLException` when reading the `ResultSet` is still allowed to be thrown directly.
- The `csv` function escapes commas, double quotes, and newlines following common CSV syntax. With real data, consider a battle-tested CSV library and CSV formula-injection mitigation when files target spreadsheets, along with encoding/quoting policies.
- `Path` is supplied by the caller; ensuring the directory exists, permissions, and temp-file safety on write failure are application-level policies.

### 7.6. Runnable Application: `RowCallbackDemoApplication.java`

~~~java
package com.example.rowcallback;

import java.io.BufferedReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RowCallbackDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RowCallbackDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(JdbcTemplate jdbc, SaleRepository sales) {
        return args -> {
            seed(jdbc);

            SaleRepository.Summary summary = sales.summarize("PAID");
            System.out.println("Paid rows = " + summary.rows());
            System.out.println("Paid total = " + summary.total());

            Path csvFile = Path.of("sales-export.csv");
            long exported = sales.exportCsv("PAID", csvFile);
            System.out.println("Exported rows = " + exported);

            try (BufferedReader reader = Files.newBufferedReader(
                    csvFile, StandardCharsets.UTF_8)) {
                reader.readLine(); // Skip header line.
                System.out.println(
                    "First exported row = " + reader.readLine()
                );
            }
        };
    }

    private static void seed(JdbcTemplate jdbc) {
        jdbc.batchUpdate(
            "INSERT INTO sale (id, customer, amount, status) " +
            "VALUES (?, ?, ?, ?)",
            new BatchPreparedStatementSetter() {
                @Override
                public void setValues(PreparedStatement ps, int index)
                        throws SQLException {
                    int id = index + 1;
                    ps.setLong(1, id);
                    ps.setString(2, "C-" + id);
                    ps.setBigDecimal(3, BigDecimal.valueOf(id, 2));
                    ps.setString(
                        4, id % 2 == 0 ? "PAID" : "PENDING"
                    );
                }

                @Override
                public int getBatchSize() {
                    return 10_000;
                }
            }
        );
    }
}
~~~

**Why does seeding use `batchUpdate`?** That is the **demo data-generation phase**, not the result-processing phase. It avoids writing 10,000 manual INSERTs. The subsequent read phase does not build a Java list containing the 5,000 paid rows. In real systems, data loading, indexes, batch size, and transactions should be designed for the workload.

### 7.7. Running and Expected Output

In the directory containing `build.gradle`, use the Gradle Wrapper if present:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell: `.\gradlew.bat bootRun`; if there is no wrapper but a compatible Gradle is installed: `gradle bootRun`. Java 21 (or a Gradle toolchain provisioned with Java 21) is required. When the application runs, ignoring Spring, HikariCP, and Gradle startup logs, the lines **explicitly printed by the demo code** are:

~~~text
Paid rows = 5000
Paid total = 250050.00
Exported rows = 5000
First exported row = 2,C-2,0.02,PAID
~~~

Runtime-independent calculation breakdown:

- There are 10,000 records `id = 1..10000`.
- Every even id is given `status = 'PAID'` ⇒ 5,000 rows.
- `amount` for id `i` is `i / 100` with two decimal places.
- Sum of even ids `2 + 4 + ... + 10000 = 5000 × 5001 = 25,005,000`; divided by 100 gives `250050.00`.
- The first PAID row when ordered by `ORDER BY id` is id 2, customer `C-2`, amount `0.02`.
- The file `sales-export.csv` contains one header line and 5,000 data lines. No step holds all 5,000 lines in a list or large string before writing.

**Verification scope:** The code demonstrates row-by-row callback processing at the Java layer; it **does not prove** that H2 or every JDBC driver buffers only 200 rows. `setFetchSize(200)` may be applied, altered, or ignored by a driver. To evaluate end-to-end streaming, run against the real database/driver with large row counts and measure heap, network, and transaction duration.

## 8. When Does JDBC Actually Fetch in Batches?

This is the most important distinction of this topic. `RowCallbackHandler` solves **how the application consumes the ResultSet**. Having the driver **deliver results in batches** is a separate matter. Many JDBC drivers default to fetching all results upfront. Switching from `List` to a callback alone is not enough to prevent OOM inside the driver on very large datasets.

### 8.1. Fetch Size Is a Hint, Not a Hard Limit

One way to configure it:

~~~java
jdbcTemplate.setFetchSize(500);
~~~

This applies the setting on a shared `JdbcTemplate`, so it can affect multiple queries. You can configure it for an **individual statement** via `PreparedStatementSetter`:

~~~java
PreparedStatementSetter pss = ps -> {
    ps.setString(1, "PAID");
    ps.setFetchSize(500);
};
RowCallbackHandler handler = rs -> {
    processOneRow(rs); // Application-defined helper.
};
jdbcTemplate.query(
    "SELECT id, amount FROM sale WHERE status = ?",
    pss,
    handler
);
~~~

`Statement.setFetchSize(int)` is a JDBC hint for fetch size. Some drivers only honor it in cursor mode, while others still transfer all data before the callback runs. Do not describe `setFetchSize(500)` as proof that heap usage is capped at 500 rows; there are also metadata, network buffers, `ResultSet` objects, and in-flight data.

### 8.2. PostgreSQL (pgJDBC): Transaction + Forward-Only + fetchSize

Per pgJDBC documentation, the driver can use a cursor-backed `ResultSet` when these conditions hold:

- The `Connection` **is not in autocommit mode**; the backend needs the cursor to live inside a transaction.
- The statement has a forward-only `ResultSet` type (`TYPE_FORWARD_ONLY`, usually the default).
- The query is eligible for cursor mode per driver rules, typically **a single SQL statement**.
- Positive fetch size, e.g., `setFetchSize(500)`.

In Spring Boot/Spring JDBC, you typically put a read-only transaction on a **public Service method** invoked through a Spring proxy, using the same `DataSource`/transaction manager as `JdbcTemplate`:

~~~java
// Architectural fragment — service/repository must be real Spring beans.
@Service
public class ReportService {
    private final SaleRepository sales;

    public ReportService(SaleRepository sales) {
        this.sales = sales;
    }

    @Transactional(readOnly = true)
    public void generateReport(Path destination) throws IOException {
        sales.exportCsv("PAID", destination);
    }
}
~~~

Requires imports `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `java.nio.file.Path`, `java.io.IOException`. This is a **PostgreSQL illustrative fragment**, without changing the H2 runnable program in Section 7. `readOnly=true` is an optimization hint and transaction policy; the transaction mechanism when the method runs through the proxy is what takes the connection out of autocommit under a properly configured transaction manager.

**Long-running transaction warning:** If exporting millions of rows to a slow file on the same thread, the query and transaction stay open until the callback finishes; the connection stays checked out for a long time, potentially impacting MVCC snapshots, timeouts, and vacuum/locking depending on the DB. In such cases, **keyset pagination with a bounded page size** can be more reliable for resource usage and recoverability.

### 8.3. MySQL Connector/J: Driver-Specific Streaming Behavior

MySQL Connector/J has its own modes. Driver documentation describes forward-only, read-only mode with `setFetchSize(Integer.MIN_VALUE)` to request row-by-row streaming, or cursor-based fetching when `useCursorFetch=true` is configured with a positive fetch size. These options **must not be copied blindly to PostgreSQL/H2**. While streaming results, executing another query on **the same Connection** may be restricted until the `ResultSet` is fully consumed or closed.

Therefore, your choice of driver/database dictates the exact configuration. Read the documentation for the driver version you run and load-test it; do not design one “magic fetch size” for everything.

### 8.4. H2 and Embedded Databases

H2 is convenient for learning because it requires no external DB container, yet a successful test with 10,000 rows **is not enough** to conclude how pgJDBC/MySQL stream rows over the network. H2 runs embedded and does not fully reproduce network latency, cursors, pool contention, MVCC, and production database transaction behavior.

## 9. Turning the Callback Into a Small State Processor

According to Spring docs, `RowCallbackHandler` **is typically stateful**, since it can hold aggregated results to be read after the query finishes. However, **stateful does not mean accumulating all raw data**.

### 9.1. Counting and Summing

~~~java
final class RevenueCounter implements RowCallbackHandler {
    private long rows;
    private BigDecimal revenue = BigDecimal.ZERO;

    @Override
    public void processRow(ResultSet rs) throws SQLException {
        rows++;
        revenue = revenue.add(rs.getBigDecimal("amount"));
    }

    public long rows() {
        return rows;
    }

    public BigDecimal revenue() {
        return revenue;
    }
}

// Usage:
RevenueCounter counter = new RevenueCounter();
jdbc.query("SELECT amount FROM sale", counter);
// Read counter.rows()/counter.revenue() after the query finishes.
~~~

This is a **fragment requiring imports** `ResultSet`, `SQLException`, `BigDecimal`, `RowCallbackHandler`, and a `jdbc` field/variable. Create **one counter instance per query**; do not register a mutable `@Component` singleton shared across all requests, as results can mix between calls and cause race conditions.

### 9.2. Processing Each Row Without Retaining History

~~~java
RowCallbackHandler handler = rs -> {
    long id = rs.getLong("id");
    BigDecimal amount = rs.getBigDecimal("amount");
    verify(id, amount); // Inspect one row without caching everything.
};
jdbc.query("SELECT id, amount FROM sale", handler);
~~~

`verify(...)` can log anomalies, increment a counter, or throw an exception upon detecting invalid data. If the callback calls a slow external API/network endpoint for **every row**, the JDBC connection stays open for a long time; avoid placing slow I/O or simultaneous external service calls inside the callback without timeout/backpressure design.

### 9.3. Writing to a File Line by Line

For file output:

- Open `BufferedWriter` **outside** the callback.
- Inside the callback, write only the current row's data.
- Use `try-with-resources` to close the Writer.
- Wrap `IOException` into `UncheckedIOException` or pass it through an appropriate error mechanism.
- If the file must be “all-or-nothing”, write to a temporary file and only rename/move to the final name once the query completes. Decide how to clean up the temp file on failure and consider filesystem support for atomic moves.

**Do not use `StringWriter`, `ByteArrayOutputStream`, or `StringBuilder` to collect the entire CSV before writing to disk** when memory efficiency is the goal.

## 10. Distinguishing `RowCallbackHandler` from `ResultSetExtractor`

A `ResultSetExtractor<T>` has the method:

~~~java
T extractData(ResultSet rs) throws SQLException;
~~~

It receives **the entire ResultSet** and controls the loop itself. For example:

~~~java
Long totalRows = jdbc.query(
    "SELECT id FROM sale",
    (ResultSetExtractor<Long>) rs -> {
        long rows = 0L;
        while (rs.next()) {
            rows++;
        }
        return rows;
    }
);
~~~

An extractor can return any result `T`, including a summary. With `RowCallbackHandler`, `JdbcTemplate` owns `rs.next()` and `query` returns `void`, while results are stored in an external accumulator or output side effect.

**When early stopping is needed:** `RowCallbackHandler` has no `return false` to tell JDBC to stop iterating. If you only need N rows, it is better to use SQL `LIMIT`/`FETCH FIRST` or dialect-appropriate pagination; if complex reading control is required, `ResultSetExtractor` lets you write `while(rs.next())` and `break` by your own rules. Throwing an exception just to stop after N rows usually makes code hard to understand and can be treated as a transaction error.

## 11. Avoid Confusing with `RowMapper` and `RowCountCallbackHandler`

### `RowMapper`: Mapping One Row to One Object

~~~java
RowMapper<Sale> mapper = (rs, rowNum) -> new Sale(
    rs.getLong("id"),
    rs.getBigDecimal("amount")
);

List<Sale> sales = jdbc.query(
    "SELECT id, amount FROM sale ORDER BY id",
    mapper
);
~~~

`RowMapper.mapRow` must also not call `rs.next()`, and the `rowNum` argument is provided by the framework. The difference is that `mapRow` returns an object; `JdbcTemplate.query(..., RowMapper)` collects those objects into a `List`. This remains the right API when the result set is small or the caller truly needs every object.

### `RowCountCallbackHandler`: Built-in Class

Spring provides `RowCountCallbackHandler`, a `RowCallbackHandler` implementation for counting rows and inspecting column metadata. Example:

~~~java
RowCountCallbackHandler count = new RowCountCallbackHandler();
jdbc.query("SELECT id, amount FROM sale", count);
System.out.println(count.getRowCount());
~~~

Spring documentation notes that a `RowCountCallbackHandler` instance is **for single-query use**; do not reuse an old instance as a singleton bean across multiple queries. In real applications, `SELECT COUNT(*)` is usually better if you only need the count, since the database computes it without transferring every row.

### Is `queryForStream` a Complete Replacement?

`JdbcTemplate.queryForStream(...)` provides a `Stream` for element-by-element processing, but **the stream must be closed**:

~~~java
try (Stream<Sale> stream = jdbc.queryForStream(
        "SELECT id, amount FROM sale",
        (rs, rowNum) -> new Sale(
            rs.getLong("id"),
            rs.getBigDecimal("amount")
        )
)) {
    stream.forEach(sale -> process(sale));
}
~~~

This fragment requires importing `Stream` and defining `Sale`/`process`. `Stream` is lazy in the Java API, yet the driver may still buffer and the connection must stay alive until reading finishes. `RowCallbackHandler` is straightforward when all processing happens directly inside the `query` call; `queryForStream` is helpful when composing Stream operations, at the cost of strict lifecycle management.

## 12. Transactions, Timeouts, and Data Consistency

Iterating a large `ResultSet` can hold a `Connection` for a long duration. If the callback runs inside a Spring transaction, the query uses the `Connection` bound to the current transaction. Several choices need to be made:

1. **Transaction scope:** PostgreSQL cursor-based fetch queries require an appropriate transaction. Choose `@Transactional(readOnly=true)` on a public Service method when appropriate, while verifying the method is invoked through the Spring proxy and the transaction manager matches the `DataSource`.
2. **Timeouts:** Set timeouts for the query/transaction and total export duration; if the Writer stalls, the query will not release itself early.
3. **Isolation:** Data may change while a long query runs; isolation level and snapshot semantics determine “consistent reporting” per DBMS.
4. **Connection pool:** Running 100 concurrent CSV export jobs on a pool of size 10 can starve critical transactional requests. Bound the concurrency of export jobs.
5. **Midway failure:** If the callback fails at row 4,000, JDBC resources are closed/released; however, the file that already received 3,999 rows **does not automatically roll back** with the database transaction.
6. **Retries:** When re-running a job, use a new/temp file, idempotency key, checkpoint, or progress tracking; do not blindly append again to a previously completed file.

**Do not open a new JDBC query using the same Connection from inside the callback** while the driver is streaming and has not finished consuming the current `ResultSet`. On some drivers, a nested query can fail, force buffering, or disrupt the cursor. A better design is to process only the columns already SELECTed, or split into clear separate steps.

## 13. When the Callback Exports to External Systems: Backpressure

Writing to a local file with `BufferedWriter` usually has a bounded buffer, whereas network outputs, Kafka, REST APIs, or object storage can be slower than DB reads. If the callback keeps pushing every row into an **unbounded queue**, the queue holds all data in the heap and defeats the goal of not collecting everything.

Design options depending on requirements:

- **Synchronous in callback:** Read one row → write one row. Simple, low memory, but holds the JDBC `Connection` while writing and risks timeouts.
- **Bounded queue:** The JDBC producer can only enqueue into a fixed-capacity queue; a consumer writes output. Requires backpressure, cancellation, exception coordination, and thread lifecycle management; none of that comes automatically just from using `RowCallbackHandler`.
- **Bounded micro-batches:** Accumulate up to B rows, flush one batch, then `clear()`. Heap is roughly O(B × M), not O(N × M).
- **Keyset pagination:** Each `SELECT` fetches at most B rows, closes the `ResultSet`/`Connection`, and then processes output. Adds query overhead, but offers checkpoints, shorter connection hold times, and better retry/resume support.

**Illustrative micro-batch fragment:**

~~~java
List<SummaryLine> batch = new ArrayList<>(500);

RowCallbackHandler handler = rs -> {
    batch.add(new SummaryLine(
        rs.getLong("id"),
        rs.getBigDecimal("amount")
    ));
    if (batch.size() >= 500) {
        flushBatch(batch); // Must finish processing the batch's data.
        batch.clear();     // Do not retain references to all rows.
    }
};

jdbc.query("SELECT id, amount FROM sale ORDER BY id", handler);
if (!batch.isEmpty()) {
    flushBatch(batch);
    batch.clear();
}
~~~

This fragment requires the `SummaryLine` class, `flushBatch` method, and imports to be defined. State stays bounded only if `flushBatch` does not silently retain every batch elsewhere. In particular, never treat `batch.clear()` as safe if an asynchronous consumer still holds a reference to that same list: clear ownership or copying with bounded memory is required.

## 14. Choose Good SQL Before Processing in Java

Some requirements do not need to read every row into the application:

| Need | Preferred approach | Why |
| --- | --- | --- |
| Count rows by status | `SELECT COUNT(*) ... WHERE ...` | DB returns one number instead of N rows |
| Total revenue | `SELECT SUM(amount) ...` | DB aggregates before transferring |
| Totals by month/customer | Appropriate `GROUP BY` | Reduces data sent over the network |
| Export all rows to CSV with complex formatting | `RowCallbackHandler` + Writer | Must walk every row while avoiding a huge `List` |
| Detect invalid rows per Java policy | `RowCallbackHandler` | Java logic can process/record issues immediately |
| Paginated UI screens | `LIMIT/OFFSET` or keyset pagination | Should not fetch all rows and then call `subList` |
| Very large analytical computations | SQL analytics / DB ETL | Avoid pulling everything into the JVM if the database can compute it |

When `ORDER BY id` is needed to export in deterministic order, the query must specify a stable sort order and ideally have indexes supporting filtering/ordering. `RowCallbackHandler` does not replace good SQL; queries should still select only needed columns, use proper `WHERE` predicates, and avoid unnecessary `SELECT *`.

### Offset Pagination Is Not Always a Good Choice

For large or rapidly changing data, very high `OFFSET` values can be expensive and risk duplicate or skipped rows when records change concurrently. Keyset pagination like `WHERE id > :lastId ORDER BY id LIMIT :limit` often benefits from an indexed unique key order. However, requiring a consistent snapshot across pages needs appropriate isolation or data cutoffs; keyset pagination does not guarantee a single snapshot by itself.

## 15. Handling Exceptions and Incomplete Export Files

Inside `processRow(ResultSet)`:

- `SQLException` from `rs.getXxx()`: let it throw; `JdbcTemplate` handles SQL error translation and cleanup.
- `IOException` from the Writer: wrap in a semantically clear unchecked error, such as `UncheckedIOException`, and let the query terminate with failure.
- `RuntimeException` from data violations or business errors: do not swallow and keep writing if that leaves the output untrustworthy.
- Control already-executed side effects: a DB transaction rollback **cannot undo files, emails, or network messages**.

Example temp-file strategy (architectural fragment):

~~~java
Path temp = Files.createTempFile("sale-export-", ".part");
boolean published = false;
try {
    repository.exportCsv("PAID", temp);
    // Validate content/metadata if needed.
    Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
    published = true;
} finally {
    if (!published) {
        Files.deleteIfExists(temp);
    }
}
~~~

This is not strictly atomic-publish; if an atomic rename is needed, use `StandardCopyOption.ATOMIC_MOVE` where supported by the filesystem, with appropriate fallback and awareness of cross-filesystem move limits. Creating the temp file **on the same filesystem/target directory** usually improves safe move reliability. Distinguish DB errors, I/O errors, cancellation, and business errors when reporting export status.

## 16. Verifying with Integration Tests and Measuring Heap

A handler unit test can use a mocked `ResultSet` for a few rows, but **does not prove** how `JdbcTemplate` acquires Connections, sets fetch size, or handles rollbacks. Those require integration tests.

**Suggested essential test suite:**

1. **Correct results:** With 10 rows of known data, the accumulator yields the exact count and total; CSV has the right header, row count, and order.
2. **Empty ResultSet:** Query with no matching rows returns accumulator count 0 and sum per policy (e.g., `BigDecimal.ZERO`); file contains only the header.
3. **Nulls and data types:** If the schema permits NULL, define policy for `rs.getBigDecimal` returning null, and remember `rs.getLong` can return 0 for SQL NULL so `rs.wasNull()` is needed to distinguish.
4. **SQLException:** Wrong column/invalid SQL must report properly; no connection leaks.
5. **IOException:** File write fails midway; JDBC resources are cleaned up and temp file is not published.
6. **Concurrency:** Two concurrent jobs using the same repository do not share a mutable singleton-bean accumulator.
7. **Real driver streaming:** Run high row counts on pgJDBC/MySQL with proper driver configuration; measure heap during the query, not only after the query returns.
8. **Transaction/timeout:** Long report export runs inside a transaction with an appropriate timeout, without unintentionally holding connections too long.

### Meaningful Measurements

To verify the “do not collect everything in memory” property, measure peak heap as row count scales (e.g., 10k → 100k → 1M) on the same data shape. If JDBC buffering is configured properly, a callback holding bounded state will exhibit a different application profile than `List<Sale>`. If peak heap still climbs sharply, check whether the driver loads the entire `ResultSet`, whether a queue/list/map in the callback grows with N, whether the Writer uses `StringWriter`, whether logging retains messages, or whether an ORM/persistence context is caching entities.

**Do not treat a successful measurement on H2 as proof of production streaming.** Use the real DB engine and JDBC driver, along with transactions, fetch size, and realistic network/pool settings.

## 17. Common Mistakes and Fixes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Calling `rs.next()` inside `processRow` | Skips rows or breaks the loop managed by `JdbcTemplate` | Only read the current row; let `JdbcTemplate` advance |
| Calling `jdbc.query(..., RowMapper)` and discarding the `List` | The `List` was still allocated in the heap | Use `RowCallbackHandler` when a List-shaped aggregate result is not needed |
| Calling `allRows.add(...)` unboundedly inside the handler | Heap still grows O(N) | Use a bounded accumulator, Writer, or bounded batches |
| Thinking `RowCallbackHandler` guarantees network streaming on its own | The driver may buffer the entire result set | Verify fetch size, transaction, and driver |
| Setting positive `setFetchSize` on pgJDBC with autocommit still on | Cursor mode does not activate per driver rules | Use an appropriate transaction, forward-only, and a single SQL statement |
| Applying `Integer.MIN_VALUE` fetch size to every DB | Drivers do not share the same convention | Use driver-specific settings only when supported |
| Putting `BufferedWriter` in try-with-resources inside each `processRow` | Opens/closes the file on every row, risking overwrites | Open the Writer once before the query, close after the query |
| Making slow network requests per row inside the handler | Holds the Connection long, increasing timeouts/pool contention | Consider bounded queues, batching, pagination, and timeouts |
| Using a singleton handler with mutable count/list fields | Race conditions and cross-request data mixing | Create handler/accumulator per invocation |
| Ignoring mid-export CSV write failures | Partial file treated as successful | Use a temp file, publish only after query completion, and clean up |
| Using `rs.getLong` and assuming SQL NULL equals 0 | Loses distinction between NULL and 0 | Call `rs.wasNull()` or use `getObject(..., Long.class)` if driver supports it |
| Throwing an exception to stop after 100 rows | Query treated as failed; hard to manage transactions | Put `LIMIT`/`FETCH` in SQL, or use an extractor/pagination |
| Closing Connection/ResultSet inside the callback | Breaks the lifecycle owned by `JdbcTemplate` | Only process data; let the framework clean up JDBC resources |
| Treating `@Transactional(readOnly=true)` as magic that makes every driver stream | Autocommit/driver and fetch size have additional conditions | Test directly with the actual driver, `DataSource`, and transaction manager |
| Switching from List to RowCallback while still SELECTing too many columns | Still wastes network/driver buffers/CPU | SELECT only needed columns, optimize SQL/indexes |

## 18. Self-Check Questions

**Question 1.** Should you call `rs.next()` inside `processRow`?  
**Answer:** No. `JdbcTemplate` has already positioned the `ResultSet` on the current row.

**Question 2.** Why does `RowMapper` also process row by row yet can still consume significant heap?  
**Answer:** The `JdbcTemplate.query(..., RowMapper)` overload returns a `List`, holding one object per mapped row until completion.

**Question 3.** Does the following callback achieve the goal of not collecting everything: `rs -> list.add(map(rs))`?  
**Answer:** No. The list built by the callback itself still grows with the row count.

**Question 4.** If you only need the total amount across the whole table, is SQL `SELECT SUM(amount)` or `RowCallbackHandler` usually better?  
**Answer:** Usually `SUM` in the database, because you do not need to transfer every row to the JVM.

**Question 5.** Does setting `ps.setFetchSize(500)` guarantee the JVM never receives more than 500 rows at once?  
**Answer:** No. It is a hint/mechanism depending on the JDBC driver, transaction, and database.

**Question 6.** For PostgreSQL cursor-based fetching, what role does autocommit play?  
**Answer:** pgJDBC requires a non-autocommit `Connection` for cursor `ResultSet`s to work as documented; a positive fetch size and forward-only mode are also required.

**Question 7.** What return type does `RowCallbackHandler` have? Where do you retrieve a total?  
**Answer:** `void`; the total resides in a caller-owned accumulator, or data is written directly to an output target.

**Question 8.** How does `JdbcTemplate.queryForStream` differ from `RowCallbackHandler`?  
**Answer:** It returns a `Stream` for lazy consumption by the caller; the stream must be properly closed and keeps the connection active until reading completes. `RowCallbackHandler` runs synchronously inside the `query` method and returns `void`.

**Question 9.** If exporting 1 million CSV rows and the Writer fails at row 100,000, does a database rollback delete the partial file?  
**Answer:** No. Files are side effects outside the DB transaction; write to a temp file and publish only when the query/Writer completes successfully.

**Practice exercise:** Add a `REFUNDED` status to the sample data and write `Summary summarizeByStatus(String status)` (the demo already has the status-parameterized method), verifying that `PAID` and `PENDING` both have 5,000 records with different totals. Then modify the export to select only rows with `amount >= ?`, adding parameter binding in `PreparedStatementSetter`. Inspect the CSV ordered by ID, compare before/after files, and try writing to an unwritable path to observe the exception path and cleanup. On real PostgreSQL, run a version with a read-only transaction and appropriate `fetchSize`; measure peak heap as row count scales.

## 19. Official Technical Documentation

- [Spring Framework — RowCallbackHandler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html): `processRow(ResultSet)`, must not call `next()`.
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `query` with `RowCallbackHandler`, setters, creators, and fetch size settings.
- [Spring Framework — JDBC core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `ResultSet` and `Connection` management responsibilities and data-access callbacks.
- [pgJDBC — Using a cursor to fetch ResultSet](https://jdbc.postgresql.org/documentation/query/): autocommit, forward-only, and fetch size conditions for batched reads.
- [MySQL Connector/J — JDBC implementation notes](https://dev.mysql.com/doc/connectors/en/connector-j-reference-implementation-notes.html): default buffering and specific streaming/cursor fetch modes.

## 20. Core Takeaways

1. `RowCallbackHandler.processRow(rs)` processes **the current row**, without calling `rs.next()` itself.
2. The `JdbcTemplate.query(..., RowCallbackHandler)` overload **does not build a List containing all results** for the caller; use an accumulator or Writer with bounded state.
3. Row-by-row processing in Java alone **is not enough to prove** the JDBC driver/DBMS is not buffering the entire dataset.
4. `setFetchSize`, transaction mode, and cursor mechanics **are driver-dependent**; test against the real database.
5. Querying millions of rows holds connections open longer; optimize SQL, backpressure, timeouts, concurrency, and guard against partial outputs.
6. If the database can compute `COUNT/SUM/GROUP BY` itself, push the calculation down into SQL instead of pulling every row into Java.

**Conclusion:** `RowCallbackHandler` is the right tool when the goal is **“read one row, process one row, do not retain all results in a `List`”**. To complete the **end-to-end memory-saving** picture, you must also design fetching, transactions, drivers, outputs, and system-wide resource bounds.
