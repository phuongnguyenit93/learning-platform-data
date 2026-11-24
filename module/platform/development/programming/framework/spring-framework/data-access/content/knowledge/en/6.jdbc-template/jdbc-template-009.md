# Setting fetchSize, maxRows, and queryTimeout in JdbcTemplate

When using `JdbcTemplate`, the three settings `fetchSize`, `maxRows`, and `queryTimeout` often appear together in configuration, yet **they address three completely different concerns**:

- **`fetchSize`:** hints to the JDBC driver how many rows to fetch per batch from a `ResultSet`. The goal is balancing database round-trips, latency, and memory.
- **`maxRows`:** caps the maximum number of rows permitted to appear in a statement's `ResultSet`. The goal is preventing too many rows from reaching the result reader.
- **`queryTimeout`:** limits how long a JDBC statement may execute, in **seconds**. The goal is preventing a SQL operation from running past an acceptable duration, insofar as the driver supports it.

These are three **distinct settings on JDBC `Statement`**; they are not three ways to limit record counts and do not guarantee automatic query optimization. This lesson uses Spring Framework 6.x, Spring Boot 3.3.x, and Java 17+ in examples. How a driver implements `fetchSize`, `maxRows`, statement cancellation on timeout, and streaming must be verified on your real DBMS and driver.

## 1. Quick Distinction Table

| Property | Spring method | Underlying JDBC | Unit | Directly caps result row count? |
| --- | --- | --- | --- | --- |
| Fetch size | `JdbcTemplate.setFetchSize(int)` | `Statement.setFetchSize(int)` | Rows/batch (hint) | **No** |
| Max rows | `JdbcTemplate.setMaxRows(int)` | `Statement.setMaxRows(int)` | Maximum rows in `ResultSet` | **Yes** |
| Query timeout | `JdbcTemplate.setQueryTimeout(int)` | `Statement.setQueryTimeout(int)` | **Seconds** | **No**; limits statement execution time |

Suppose a query has 50,000 potential rows:

- `fetchSize = 200` only asks the driver to **prefer fetching in chunks of ~200 rows** if the driver mode and DB permit. The full result can still contain all 50,000 rows.
- `maxRows = 1_000` instructs the JDBC statement to allow at most **1,000 rows** in its `ResultSet`; it does not mean the SQL server only processes 1,000 rows.
- `queryTimeout = 5` requests a **5-second** timeout when running the statement; it does not paginate results, set a DB connection timeout, or guarantee the entire HTTP request finishes within 5 seconds.

If all three are set together, they work alongside one another: the driver fetches in batches when supported, the result set is capped, and the statement has a time limit. **There is no mathematical relationship like `fetchSize × maxRows = queryTimeout`.**

## 2. Mechanism: How JdbcTemplate Passes Settings Down to Statement

`JdbcTemplate` creates/obtains a JDBC `Connection` from a `DataSource` and uses `Statement`, `PreparedStatement`, or `CallableStatement` to execute SQL. While preparing the statement, it applies the configured values to the corresponding JDBC APIs.

```text
Service / Repository
       |
       v
  JdbcTemplate
       |
       | configured once: fetchSize, maxRows, queryTimeout
       v
JDBC Statement / PreparedStatement
       |
       | setFetchSize(...)    --> fetch batch hint
       | setMaxRows(...)      --> ResultSet row cap
       | setQueryTimeout(...) --> execution time limit
       v
JDBC driver -------> Database
       |
       v
ResultSet --> RowMapper / RowCallbackHandler / ResultSetExtractor
```

### 2.1. Default Values and Zero

In Spring Framework 6.x, `JdbcTemplate` defaults all three properties to **`-1`**: meaning **do not invoke the corresponding setter to force a value**, letting the driver use its own default.

| Value | For `JdbcTemplate` | For JDBC `Statement` |
| --- | --- | --- |
| `-1` | Spring default: skips applying a specific value to the corresponding setter. | Standard `Statement` rejects negative values on normal setters. |
| `0` | Spring passes `0` down to the setter if configured as such. | `setFetchSize(0)`: ignore hint; `setMaxRows(0)`: unlimited; `setQueryTimeout(0)`: no statement execution time limit. |
| Positive integer | Spring passes it down to the driver. | Driver receives the value and applies it per JDBC contract/implementation. |

**Driver-specific exception:** Spring allows passing certain negative `fetchSize` values **other than `-1`** down to the driver to activate vendor-specific behavior (for example, some MySQL modes use `Integer.MIN_VALUE`). That is not portable JDBC behavior: use it only after checking the driver version and configuration. Do not pick arbitrary negative numbers without understanding their purpose.

`getFetchSize()`, `getMaxRows()`, and `getQueryTimeout()` on `JdbcTemplate` return the **template's configured values**, not proof that the driver actually batched rows or enforced timeouts as hoped.

### 2.2. Scope of Settings

`setFetchSize`, `setMaxRows`, and `setQueryTimeout` on `JdbcTemplate` are **shared defaults** for statements created and run by that template. They do not directly alter DB schemas, automatically inject `LIMIT` into SQL strings, or establish a global policy across all database connections.

`JdbcTemplate` is designed to be thread-safe **once configured**. Never call `jdbcTemplate.setMaxRows(...)` while serving different requests to "temporarily" change a limit for one request and restore it afterward: concurrent requests can observe the mutated setting.

## 3. Setting the Three Properties in Java

When instantiating `JdbcTemplate` yourself, configure it before sharing the instance with repositories/services:

```java
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;

public final class JdbcTemplateFactory {
    private JdbcTemplateFactory() {}

    public static JdbcTemplate createReportTemplate(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setFetchSize(200);  // hint to fetch 200 rows per batch
        jdbc.setMaxRows(1_000);  // maximum 1,000 rows in ResultSet
        jdbc.setQueryTimeout(5); // 5 SECONDS, not 5 ms
        return jdbc;
    }
}
```

This is a valid Java 17+ class when Spring JDBC is on the classpath; the method returns a configured instance, though it is **not a standalone `main` program**. The example sets a `maxRows` limit of 1,000 for illustration; real applications must note that every query using that instance shares the same cap, even queries intended to return fuller lists.

### 3.1. Dedicated Bean Configuration in Spring

`JdbcTemplate` is usually a singleton injected into repositories. If you have large reporting queries alongside small transactional queries, use **two templates with distinct stable policies** backed by the same `DataSource`:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class JdbcPolicyConfiguration {

    @Bean("normalJdbc")
    public JdbcTemplate normalJdbc(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setQueryTimeout(3);
        return jdbc;
    }

    @Bean("reportJdbc")
    public JdbcTemplate reportJdbc(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setFetchSize(500);
        jdbc.setMaxRows(10_000);
        jdbc.setQueryTimeout(30);
        return jdbc;
    }
}
```

In a repository:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class ReportRepository {
    private final JdbcTemplate jdbc;

    public ReportRepository(@Qualifier("reportJdbc") JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long countAll() {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM invoices", Long.class);
        return count == null ? 0L : count;
    }
}
```

These classes are **components of a Spring application** with a `DataSource` bean. When two or more `JdbcTemplate` beans exist, use `@Qualifier` explicitly at injection points. Sharing a `DataSource` does not mean every statement shares the same fetch size/timeout; each template keeps its own statement policy. Configure once inside `@Bean`, never reset per request.

**Note:** `setMaxRows(10_000)` applies to rows returned in a `ResultSet`; it does **not** limit rows updated by `UPDATE` or `DELETE`, and does not replace SQL data constraints.

## 4. fetchSize: Fetching Data in Batches

### 4.1. Fetch Size Is a Hint, Not a LIMIT

When a result has many rows, a driver may load everything in one round-trip and buffer it in client memory, or use a cursor to pull rows incrementally from the DB. `Statement.setFetchSize(n)` informs the driver that the application prefers roughly `n` rows per fetch batch.

Suppose there are 5,000 rows and `fetchSize=500`:

```text
Application reads ResultSet
       |
       +-- batch 1: rows 1..500
       +-- batch 2: rows 501..1000
       +-- ...
       +-- batch 10: rows 4501..5000
```

This is only an **idealized mental model**, not a guarantee of exactly 10 round-trips. Drivers may ignore the hint or use their own mechanisms, and extra round-trips may occur. Larger fetch sizes generally reduce round-trips at the cost of larger buffers; too small a fetch size can raise latency due to many fetch trips.

Specifically:

- `fetchSize=100` does **not** make a `SELECT` query return only 100 rows.
- `fetchSize=100` does **not** by itself guarantee processing holds only 100 Java objects.
- `fetchSize=100` does **not** necessarily enable a server cursor when the driver requires extra conditions.
- `fetchSize` does not alter SQL query plans or DB sorting/filtering.
- Test against your real driver and infrastructure, observing network traffic, memory, fetch counts, and latency.

### 4.2. RowMapper Building a List Still Accumulates Results

`JdbcTemplate.query(sql, RowMapper<T>)` maps each row and returns a `List<T>`. Even if the driver fetches rows in batches, the returned list **still holds every row read**.

Example:

```java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

public final class UserReader {
    private final JdbcTemplate jdbc;

    public UserReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record UserSummary(long id, String name) {}

    public List<UserSummary> listAll() {
        return jdbc.query(
            "SELECT id, name FROM users ORDER BY id",
            (rs, rowNum) -> new UserSummary(
                rs.getLong("id"),
                rs.getString("name")
            )
        );
    }
}
```

This class is used in an application with an existing `users` table and configured `JdbcTemplate`; it is **not** a standalone example with fixture data. With 1 million rows, one million records can be allocated and kept in the `List` despite `fetchSize=200`. To process large results with steadier memory, consider non-accumulating row-by-row processing with `RowCallbackHandler`/`ResultSetExtractor`, or `queryForStream` and **close the stream** with `try-with-resources`. The driver must still support appropriate fetching.

### 4.3. Processing Row by Row with RowCallbackHandler

The example below sums name lengths without building a list of all results. This is a Java 17+ class snippet for use inside a Spring application with a `users` table:

```java
import java.util.concurrent.atomic.LongAdder;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;

public final class UserStatistics {
    private final JdbcTemplate jdbc;

    public UserStatistics(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long totalNameLength() {
        LongAdder total = new LongAdder();

        jdbc.query(
            "SELECT name FROM users",
            (RowCallbackHandler) rs -> {
                String name = rs.getString("name");
                if (name != null) {
                    total.add(name.length());
                }
            }
        );
        return total.sum();
    }
}
```

`RowCallbackHandler` is invoked sequentially for each row; the callback **must not** call `rs.next()`. This code only keeps a counter, though memory can still spike if the driver buffers the full result set before invoking the callback. For massive datasets or long exports, verify driver cursors, transactions, and resource limits.

### 4.4. PostgreSQL and Conditions for Cursor-Based Fetching

With PostgreSQL JDBC (pgJDBC), a positive fetch size is **not sufficient by itself** to enable batched fetching. Cursor-based fetching normally requires:

1. The connection is **not in auto-commit mode** (bound inside an appropriate transaction); PostgreSQL closes cursors at transaction end.
2. `ResultSet` is `TYPE_FORWARD_ONLY`.
3. The query is a **single SQL statement**, not multiple statements combined in one call.
4. Driver and protocol support.

Spring example with `@Transactional(readOnly = true)` (properly managed by a JDBC transaction manager):

```java
import java.util.concurrent.atomic.LongAdder;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PostgresUserExportService {
    private final JdbcTemplate reportJdbc;

    public PostgresUserExportService(JdbcTemplate reportJdbc) {
        this.reportJdbc = reportJdbc;
    }

    @Transactional(readOnly = true)
    public long processCount() {
        LongAdder seen = new LongAdder();
        reportJdbc.query(
            "SELECT id FROM users ORDER BY id",
            (RowCallbackHandler) rs -> seen.increment()
        );
        return seen.sum();
    }
}
```

In this example, `reportJdbc` is assumed to have a positive `fetchSize` configured, and the method is invoked through a Spring transaction proxy. `@Transactional(readOnly=true)` is mainly a transaction/read-only hint; verify on your real system that auto-commit is disabled on the connection and the driver uses a cursor. Do not transfer this reasoning directly to H2/MySQL/Oracle without reading their respective driver documentation.

> **Trade-off:** Long-running cursor reads hold a connection and transaction open while processing results. Avoid heavy CPU work or slow network calls inside callbacks for long periods; you may need batching or cursors with bounded scope/timeouts.

## 5. maxRows: Limiting Returned Rows

`Statement.setMaxRows(1_000)` caps the maximum number of rows in any `ResultSet` produced by that statement (insofar as the driver enforces it). If SQL could return 4,000 rows, a template with `maxRows=1_000` delivers at most 1,000 rows to the application.

Example assuming a `users` table with many rows:

```java
JdbcTemplate limited = new JdbcTemplate(dataSource);
limited.setMaxRows(100);

var firstHundred = limited.query(
    "SELECT id, name FROM users ORDER BY id",
    (rs, rowNum) -> rs.getLong("id")
);
```

This is an **illustrative snippet inside a method that already has `dataSource`**, not standalone Java. The result contains at most 100 IDs. However:

- If SQL **lacks `ORDER BY`**, there is no deterministic "first 100 rows"; another run may return a different subset.
- `maxRows` is a **JDBC ResultSet** policy, not necessarily a DB-optimized SQL `LIMIT`. The DB may still scan, sort, or join large amounts of data.
- It provides no page numbers, total record count, or cursor for the next page.
- Other queries on **the same template** are also capped, which can cause **silent data truncation** if you forget this policy.

### 5.1. SQL-Level Limits Are Usually Better for Pagination

For a requirement like "first page of the 100 newest records," write an explicit limit and ordering in DBMS-appropriate SQL:

```sql
-- PostgreSQL/H2 and several other DBMSs:
SELECT id, name, created_at
FROM users
ORDER BY created_at DESC, id DESC
LIMIT 100;
```

The `created_at DESC, id DESC` pair keeps ordering deterministic when multiple rows share a timestamp. On SQL-standard DBMSs, you can use `FETCH FIRST 100 ROWS ONLY`; exact pagination syntax varies by DB. When offsets are large or data changes frequently, consider keyset pagination for stability and lower cost. Setting `maxRows=100` on a template can still act as a **safety guardrail**, not a replacement for SQL limits and pagination API design.

### 5.2. Do Not Use `maxRows` to Restrict Bulk Updates

`JdbcTemplate.update(...)` returns the **affected row count** of `INSERT`/`UPDATE`/`DELETE`. `maxRows` applies to `ResultSet` results, not to how many rows an `UPDATE users SET ...` statement is allowed to modify. To limit mutation scope, design `WHERE` clauses, transactions, permissions, and affected-row checks.

## 6. queryTimeout: Limiting Statement Execution Time

`JdbcTemplate.setQueryTimeout(5)` passes a 5-**second** timeout request down to `Statement.setQueryTimeout(5)` when applying statement settings. Per the JDBC contract, the driver applies the limit to statement execution methods such as `executeQuery`, `executeUpdate`, and `execute`. When a timeout expires and the driver detects it, it attempts to cancel the statement and throws an error (typically `SQLTimeoutException` at the JDBC layer).

In Spring JDBC, `SQLException` may be translated into an appropriate `DataAccessException`, including `QueryTimeoutException` depending on scenario/driver/translator. Do not write business logic relying on a specific SQL error message without verifying the driver and Spring's error translation.

### 6.1. Which Timeout? Do Not Confuse Layers

| Timeout | What does it control? | Typical configuration |
| --- | --- | --- |
| JDBC query timeout | Time waiting for statement execution/cancellation per driver | `JdbcTemplate.setQueryTimeout(seconds)` |
| Spring transaction timeout | Transaction duration limit via transaction manager; may propagate to JDBC statements | `@Transactional(timeout = 10)` or manager config |
| Connection acquisition timeout | Time waiting to borrow a connection from the pool | Hikari `connectionTimeout` (**milliseconds**) |
| Connect/login timeout | Time to establish a DB connection | JDBC driver/DataSource property |
| Socket/network timeout | Time waiting on network I/O | Driver/network property |
| HTTP/request deadline | End-to-end request deadline at API/gateway | Web server/client/gateway configuration |

**Example:** `setQueryTimeout(5)` does **not** guarantee a request finishes under 5 seconds. A request might wait 2 seconds to acquire a connection, execute multiple statements sequentially, or run Java/HTTP logic outside SQL. Statement timeout is not a stopwatch for the **entire service method**. Moreover, actual cancellation timing and capability depend on driver, network state, DB, and transaction state.

### 6.2. Transaction Timeout Can Override Template Timeout

Spring's `JdbcTemplate` documents clearly: if a Spring-managed JDBC transaction has a **transaction timeout**, the remaining time of the transaction **overrides** the template's `queryTimeout` when Spring applies the timeout to the statement.

Suppose a template sets `queryTimeout=30` while a service executes:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LookupService {
    private final ReportRepository repository;

    public LookupService(ReportRepository repository) {
        this.repository = repository;
    }

    @Transactional(timeout = 5, readOnly = true)
    public long countInTransaction() {
        return repository.countAll();
    }
}
```

Assuming the transaction manager and Spring proxy work properly, `countAll()` uses the same DataSource within this transaction. The **remaining transaction timeout** (part of which may already have elapsed before running the SQL) takes precedence on the statement. Do not assume a full 5 seconds always remains when the query begins.

### 6.3. Timeout Is Not a Guaranteed Rollback at Every Layer

If `@Transactional` sees a runtime `DataAccessException` escape the transactional method, Spring's default rollback rules normally mark the transaction for rollback. Yet in practice:

- The driver might not be able to cancel the statement immediately during network/DB issues.
- A cancelled statement does not mean **every** side effect outside the transaction was undone.
- Post-error transaction state depends on the DBMS and how transactions are structured.
- Never blindly auto-retry every `UPDATE`/`INSERT` after a timeout, because the operation might already have committed on the DB without the client receiving the response. Check idempotency, transaction outcome, and retry policies.

To limit the impact of locks or slow SQL, you can combine transaction timeouts, database statement/lock timeouts, and appropriate request deadlines. These are complementary safeguards, not one magic number.

## 7. Runnable Example: Spring Boot + H2

This example clearly verifies **`maxRows` taking effect on results** and shows configuration of all three properties. It does not simulate a real timeout, as sleep/lock timing tests are flaky across machines and drivers; nor does it claim H2 necessarily fetches in exact configured batches.

Create a Spring Boot 3.3.x application with Java 17+ and Gradle.

### 7.1. Gradle Dependencies

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:jdbc_tuning_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` keeps the in-memory H2 DB alive for the JVM's lifetime even after the last connection closes; used for the demo, not a mandatory production setting.

### 7.2. Complete Java Application

File `src/main/java/example/JdbcSettingsDemoApplication.java`:

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class JdbcSettingsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcSettingsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DataSource dataSource) {
        return args -> {
            // Template for data initialization, with no row cap.
            JdbcTemplate setup = new JdbcTemplate(dataSource);
            setup.execute("CREATE TABLE sample (id INT PRIMARY KEY)");

            for (int id = 1; id <= 5; id++) {
                setup.update("INSERT INTO sample(id) VALUES (?)", id);
            }

            // Dedicated template, configured before use.
            JdbcTemplate limited = new JdbcTemplate(dataSource);
            limited.setFetchSize(2);
            limited.setMaxRows(3);
            limited.setQueryTimeout(5);

            List<Integer> ids = limited.query(
                "SELECT id FROM sample ORDER BY id",
                (rs, rowNum) -> rs.getInt("id")
            );

            System.out.println("fetchSize=" + limited.getFetchSize());
            System.out.println("maxRows=" + limited.getMaxRows());
            System.out.println("queryTimeout=" + limited.getQueryTimeout());
            System.out.println("ids=" + ids);
        };
    }
}
```

Run from a project with the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell: `.\gradlew.bat bootRun`. When dependencies are resolved, a suitable Java toolchain is present, and H2 enforces `setMaxRows(3)` per the JDBC contract, the lines produced by `System.out` are:

```text
fetchSize=2
maxRows=3
queryTimeout=5
ids=[1, 2, 3]
```

Spring Boot may print additional startup logs. There is no timing measurement in the demo, so `queryTimeout=5` only confirms the template holds **5 seconds**, not that a statement would fail after 5 seconds. Likewise, `fetchSize=2` here only confirms configuration, not that the driver performed 3 fetch trips. The query has 5 underlying rows, `ORDER BY` makes ordering deterministic, and `maxRows=3` yields 3 rows.

**Key takeaway:** `fetchSize` adjusts **how data is fetched** when supported by the driver; `maxRows` adjusts the **row ceiling** received by the program; `queryTimeout` adjusts the **statement time ceiling**. One `DataSource` can serve multiple templates with different policies.

### 7.3. Testing One Property at a Time

For meaningful comparisons, run separate experiments:

1. Keep SQL, schema, and transaction identical; vary `fetchSize` across 0, 50, 500, and 5,000; measure speed, memory, and network/fetch trips on your real driver, especially with many rows.
2. Keep SQL with `ORDER BY`; vary `maxRows` between 0 (no JDBC cap) and 3; verify returned row counts. Never use an unbounded huge-data API in production just to measure.
3. Test `queryTimeout` with a controlled slow query on your specific driver; record exceptions, cancellation time, and transaction state. Do not extrapolate a theoretical timeout into an SLA.
4. Compare a query with `LIMIT`/`FETCH FIRST` against using `maxRows` alone; inspect the query plan and how much work the DB performs.

## 8. When Should These Properties Be Set?

### 8.1. Short Queries, Small Results

For a `SELECT ... WHERE id = ?` returning at most one row by primary key, tuning `fetchSize` is usually unnecessary. Set a reasonable statement or transaction timeout per operational needs. `maxRows=1` can serve as a defensive guardrail, though correctness still relies on key/unique constraints and the query API.

### 8.2. Paginated List Lookups

Prefer `ORDER BY` with limit/offset or keyset pagination in SQL. Setting `maxRows` can add extra protection against returning too many rows; pick `fetchSize` based on page size and driver behavior. Add an appropriate query timeout; do not expect `maxRows` to solve pagination.

### 8.3. Large Reports or Exports

When reading very many rows:

- Optimize SQL/indexes and select only needed columns.
- Pick a driver-appropriate `fetchSize`, considering cursors and transactions.
- Avoid `RowMapper` building a massive `List`; use row-by-row callbacks/streams and close resources properly.
- Set `maxRows` to an export limit **only if business rules genuinely allow truncating results**. If full exports are required, never leave a hidden cap that silently drops data.
- Consider a dedicated query timeout and short processing scopes; do not hold transactions/connections indefinitely while waiting on network/file I/O.
- Monitor row counts, memory, DB duration, read duration, active pool slots, and timeouts.

### 8.4. Multiple Query Types in the Same Application

Do not apply a single value globally just because an example configuration showed it. Define dedicated templates for small OLTP vs. long reporting queries, or structure repositories/configurations cleanly. Only change properties on an instance **before** it is shared. If per-request values are strictly required, use a proper statement-customization API and transaction management instead of mutating setters on a shared singleton during requests.

## 9. Common Mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| "`fetchSize=100` means only 100 rows are read" | It is a hint for fetch batch size. | Use `maxRows` or `LIMIT/FETCH FIRST` to cap row counts. |
| "`fetchSize=200` guarantees low RAM usage" | `RowMapper` can still accumulate a full List; the driver might buffer everything. | Choose callbacks/streams and verify driver streaming behavior. |
| "`maxRows=50` makes the DB process only 50 rows" | Capping JDBC ResultSet does not guarantee less DB scanning/sorting. | Limit in SQL and optimize indexes/query plans. |
| "`maxRows` implements pagination" | No page cursor, offset, or deterministic order. | Design proper `ORDER BY` and keyset/offset pagination. |
| "`queryTimeout=5000` is 5 seconds" | The unit of `setQueryTimeout` is **seconds**. | Use `5` for 5 seconds; verify driver behavior. |
| "Query timeout = connection timeout" | Waiting to borrow/connect and running SQL are separate phases. | Configure pool, driver/network, JDBC statement, and request timeouts separately. |
| "`@Transactional(timeout=3)` is unrelated to `JdbcTemplate`" | Remaining transaction timeout can override the statement setting. | Check your transaction manager and effective timeout values. |
| "A timeout guarantees data rolls back" | Driver cancellation, DB, transactions, and external side effects follow different rules. | Explicitly define transactions, rollbacks, idempotency, and retries. |
| "Mutating `JdbcTemplate.setMaxRows` per request is fine" | Shared template configuration is mutable, causing races across requests. | Configure once; use dedicated template instances. |
| "Seeing `getFetchSize()=200` proves 200 rows/packet" | The getter only returns config, not network traces. | Measure driver/DB, logs, profiling, and load tests. |

## 10. Self-Check Questions

**1.** A query returns 12,000 rows, with `fetchSize=300` and `maxRows=-1`. Is the application guaranteed to receive only 300 rows?

**Answer:** No. `fetchSize` hints how many rows to pull per fetch batch; it does not cap total rows. `maxRows=-1` adds no cap from `JdbcTemplate`, so all 12,000 rows can be returned.

**2.** How does `setMaxRows(25)` differ from `SELECT ... LIMIT 25`?

**Answer:** `setMaxRows` caps rows in the JDBC ResultSet; `LIMIT` is a SQL-layer limit understood by the DBMS that can be optimized in the query plan. Selecting 25 deterministic rows requires `ORDER BY`; SQL limit syntax varies across DBMSs.

**3.** A query stalls for 20 seconds waiting to borrow a connection from the pool while `queryTimeout=5`. Is the request guaranteed to fail after 5 seconds total?

**Answer:** No. `queryTimeout` limits JDBC statement execution, not total connection-wait time.

**4.** Inside `@Transactional(timeout=4)`, the template has `queryTimeout=20`. How does Spring typically apply the statement timeout?

**Answer:** When the Spring JDBC transaction manager and `JdbcTemplate` participate in a transaction with a timeout, the **remaining** transaction time is applied to the statement, overriding the template's 20 seconds.

**5.** Can memory for a huge export be controlled with `setFetchSize(100)` alone?

**Answer:** No. The driver must support batched/cursor fetching, and the code must process rows/batches without collecting the entire result into one giant `List`.

**6.** What does `setQueryTimeout(0)` mean in standard JDBC? How does `JdbcTemplate`'s default `-1` differ?

**Answer:** Standard JDBC treats `0` as no statement time limit; `-1` in Spring means skipping the setter call so the driver uses its own default (which might have its own timeout). Thus the two settings must not be treated as identical in all environments.

## 11. Pre-Merge Configuration Checklist

- [ ] Identify the **goal**: lower memory/round-trips, cap row counts, or cap execution time.
- [ ] Verify DBMS type, JDBC driver version, auto-commit/transaction setup, and cursor support.
- [ ] For `fetchSize`, measure fetch round-trips, memory, and duration on the actual driver.
- [ ] For `maxRows`, check `ORDER BY` ordering and data-truncation impact on every query sharing that template.
- [ ] For pagination, SQL has an explicit limit and deterministic ordering; do not rely on JDBC limits alone.
- [ ] For `queryTimeout`, remember the unit is **seconds** and distinguish it from Hikari `connectionTimeout` in **milliseconds**.
- [ ] Remember transaction timeouts can override query timeouts; do not treat cancellation as a standalone rollback guarantee.
- [ ] Never mutate settings on a singleton `JdbcTemplate` between requests.
- [ ] Gather real metrics on SQL duration, row counts, memory, DB load, connection pool, and timeouts.
- [ ] Test behavior on your deployment driver, not only on in-memory H2 in examples.

## 12. References

- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): setters/getters, `-1` default, and transaction timeout override behavior.
- [Java 21 — java.sql.Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): JDBC contract for `setFetchSize`, `setMaxRows`, `setQueryTimeout`, and units.
- [Spring Framework — DataSourceUtils](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): how transaction-linked statement timeouts are applied.
- [pgJDBC — Issuing a Query and Processing the Result](https://jdbc.postgresql.org/documentation/query/): conditions for cursor-based fetching with fetch size.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): patterns for `JdbcTemplate` and `ResultSet` handling.

**Remember:** `fetchSize` tunes **how** data is fetched (hint, driver-dependent), `maxRows` caps **how many rows are returned** via the JDBC ResultSet, and `queryTimeout` caps **statement execution time** (seconds). Combining them properly with ordered/limited SQL, sound transactions, and real-driver testing makes Spring applications safer and more predictable.
