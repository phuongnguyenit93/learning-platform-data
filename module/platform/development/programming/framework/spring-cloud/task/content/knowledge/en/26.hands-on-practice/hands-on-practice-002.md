# CSV File Import with PostgreSQL and Persistent Execution History

In this **Hands-On Practice** chapter of the **SPRING_CLOUD_TASK** module, we build a single-run Spring Boot application that reads data from **CSV**, validates it, saves it into **PostgreSQL**, and exits. After the JVM terminates, operators can still inspect the **execution history** via `TaskRepository`: when each run started, when it ended, what its exit code was, and whether any errors occurred.

This lab also solves a critical requirement for scheduled or on-demand systems: **re-running the same file must not import duplicate data**. If the JVM stops right after PostgreSQL commits but before the Task finishes reporting completion, the next run must detect that the data is already present and exit safely.

We will build the `csv-import-task` application with these characteristics:

- Accepts `--input`, `--tenant`, `--businessDate`, `--sourceVersion`, and `--runId` parameters.
- Parses CSV properly with commas and double quotes using **Apache Commons CSV**; never uses `String.split(",")`.
- Validates headers, transaction IDs, `BigDecimal` amounts, currency codes, and duplicate IDs within the file.
- Computes a **SHA-256 checksum from the exact parsed bytes** to identify file contents.
- Uses JDBC transactions and PostgreSQL primary keys to guarantee **all-or-nothing import or rollback**, even when an error occurs mid-way.
- Records metadata for **each execution** in Spring Cloud Task's `TASK_EXECUTION` table; business data tables have their own duplicate-prevention mechanism.
- Includes tests for re-imports, modified files, invalid data, mid-transaction failures, and PostgreSQL restarts.

**Scope:** this example targets small files (up to **4 MiB, 10,000 data rows**), suitable for learning and running locally. For importing millions of rows, switch to streaming/chunk processing or Spring Batch, discussed at the end of this lesson.

## 1. Objectives and Acceptance Criteria

After this lesson, you will be able to:

1. Start PostgreSQL with a persistent volume on a development machine.
2. Create a Spring Cloud Task application using `ApplicationRunner` and a JDBC `TaskRepository`.
3. Write a CSV parser that validates data before opening a transaction.
4. Design a schema with a **business key**, checksum, and integrity constraints.
5. Apply `@Transactional` with `JdbcTemplate` and `INSERT ... ON CONFLICT DO NOTHING`.
6. Distinguish records in `TASK_EXECUTION` from imported rows in business tables.
7. Verify state after the JVM exits or PostgreSQL is stopped and restarted.
8. Safely handle import retries, validation failures, connection drops, and uncertain commit outcomes.
9. Know when to adopt Spring Batch for checkpoints, chunks, and restarts.

### Completion Criteria

| Scenario | Expected Outcome |
| --- | --- |
| Valid CSV, first run | 3 rows imported, Task execution recorded as completed |
| Re-import with same business key and same bytes | No rows added, application reports `ALREADY_APPLIED` |
| Same business key but different file content | Reports `IDEMPOTENCY_CONFLICT`, does not overwrite old results |
| CSV contains invalid data | No business results created, Task records error if repository is still reachable |
| Failure after writing first row but before commit | Both ledger and inserted rows roll back |
| JVM exits, re-runs, or PostgreSQL restarts | History and results persist in PostgreSQL |
| Multiple runs for the same request | May have multiple `TaskExecution` records, but **only one set of business results** |

## 2. Architecture and Execution Flow

~~~mermaid
flowchart TD
    A["Scheduler / CLI: business key + CSV path"] --> B["Spring Boot ApplicationRunner"]
    B --> C["Read a single byte snapshot of the file"]
    C --> D["Parse CSV, validate, and compute SHA-256"]
    D -->|"Invalid"| E["Throw exception, task fails"]
    D -->|"Valid"| F["ImportService @Transactional"]
    F --> G{"Ledger exists for business key?"}
    G -->|"No"| H["INSERT ledger + INSERT rows in same transaction"]
    G -->|"Yes, same hash"| I["ALREADY_APPLIED"]
    G -->|"Yes, different hash"| J["IDEMPOTENCY_CONFLICT"]
    H --> K["PostgreSQL COMMIT"]
    K --> L["Runner completes"]
    I --> L
    J --> E
    L --> M["Spring Cloud Task updates TaskRepository"]
    E --> M
    M --> N["JVM exits; history remains in PostgreSQL"]
~~~

Two kinds of data **must not be conflated**:

| Source | Example Tables | Purpose |
| --- | --- | --- |
| **Spring Cloud Task Metadata** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, `TASK_SEQ` | Tracks **each process execution**: timestamps, exit code, messages |
| **Business Data** | `csv_import`, `sales_line` | Determines whether a **CSV import job** has already been executed and which rows were committed |

A request may run two or three times due to timeouts or scheduler retries. `TASK_EXECUTION_ID` differs on every run, but the business key `(tenant_id, business_date, source_version)` must **stay the same** if it represents the same logical job.

## 3. Tools and Reference Versions

Prerequisites:

- **JDK 17+**, Maven or Maven Wrapper; Docker Desktop/Engine to run PostgreSQL.
- PostgreSQL 16 (example Docker image) and an unused TCP port.
- Spring Boot **3.5.x** with Spring Cloud release train **2025.0.x**, published as compatible; verify exact patch versions in official documentation.
- Spring Cloud Task, `spring-boot-starter-jdbc`, PostgreSQL JDBC Driver, and Apache Commons CSV.
- An optional SQL client such as `psql`, DBeaver, or DataGrip.

To give the Maven snippets a concrete baseline, the examples below choose **Spring Boot 3.5.13 + Spring Cloud 2025.0.2** (an announced compatible release-train pairing), Java 17, and Commons CSV 1.14.1. These numbers are an **illustrative baseline**, not guaranteed to be the latest versions or right for every project in 2026. If your project uses Spring Boot 4, pick the corresponding release train and check for API changes.

## 4. Preparing Persistent PostgreSQL

### 4.1. Starting the Container with a Named Volume

On your development machine, run the one-line command:

~~~bash
docker run -d --name csv-task-postgres -e POSTGRES_DB=taskdemo -e POSTGRES_USER=taskdemo -e POSTGRES_PASSWORD=local-demo-only -p 5433:5432 -v csv_task_pgdata:/var/lib/postgresql/data postgres:16
~~~

This command uses:

- Host port `5433` to avoid colliding with a PostgreSQL instance listening on `5432`; inside the container it remains `5432`.
- Database and user named `taskdemo`.
- Volume `csv_task_pgdata` so data **is not lost when the container stops and restarts**.
- Password `local-demo-only` **for localhost learning only**; never put real passwords on the command line, in Git, or in production logs.

Verify the DB is ready:

~~~bash
docker exec csv-task-postgres pg_isready -U taskdemo -d taskdemo
~~~

Expect a message that the database is accepting connections. If port `5433` is already in use, choose another host port and update the JDBC URL accordingly.

### 4.2. Opening the SQL Prompt Inside the Container

~~~bash
docker exec -it csv-task-postgres psql -U taskdemo -d taskdemo
~~~

The SQL statements in the following sections are executed inside the `psql` prompt or a SQL client connected to `localhost:5433/taskdemo`. **Do not delete the volume or reset the database when verifying durability.**

## 5. Creating the Business Schema

We create two tables. `csv_import` acts as the **ledger/idempotency record** for an import period; `sales_line` holds the imported rows.

~~~sql
CREATE TABLE csv_import (
    tenant_id      VARCHAR(64)  NOT NULL,
    business_date  DATE         NOT NULL,
    source_version VARCHAR(32)  NOT NULL,
    input_sha256   CHAR(64)     NOT NULL,
    row_count      INTEGER      NOT NULL CHECK (row_count > 0),
    completed_at   TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_date, source_version)
);

CREATE TABLE sales_line (
    tenant_id      VARCHAR(64)  NOT NULL,
    business_date  DATE         NOT NULL,
    source_version VARCHAR(32)  NOT NULL,
    external_id    VARCHAR(64)  NOT NULL,
    amount         NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    currency       CHAR(3)      NOT NULL CHECK (currency = 'USD'),
    PRIMARY KEY (
        tenant_id, business_date, source_version, external_id
    ),
    FOREIGN KEY (tenant_id, business_date, source_version)
        REFERENCES csv_import (
            tenant_id, business_date, source_version
        )
);
~~~

**Meaning of the constraints:**

- `PRIMARY KEY (tenant_id, business_date, source_version)` protects a single valid import per period and version.
- `input_sha256` lets a new import compare against **the exact bytes of the previous file**. Same key with different bytes must report a conflict.
- `row_count` records the number of rows the application committed to saving in the transaction.
- `sales_line`'s primary key prevents two rows with duplicate `external_id` in the same period.
- The foreign key prevents sales lines that do not link to a ledger entry.
- `NUMERIC(18,2)` and `BigDecimal` avoid floating-point rounding errors from `double` for monetary values.

**Do not hand-create** `TASK_EXECUTION` with the DDL above. The `TASK_*` tables are created by Spring Cloud Task using **the schema for its exact framework version** when the initializer is enabled, or pre-created by DBAs/migrations. Both table groups live in PostgreSQL in this lesson, which does not mean metadata updates and business data writes occur in the same transaction.

### Initial Check

~~~sql
SELECT COUNT(*) FROM csv_import;
SELECT COUNT(*) FROM sales_line;
~~~

Both values are expected to be `0` on a fresh database. Only run this lab in an **isolated** database; do not delete data from other projects.

## 6. Preparing the UTF-8 CSV File

Create `data/sales-2026-11-24.csv` (UTF-8 **without BOM**) with the following contents:

~~~csv
external_id,amount,currency
S-001,10.50,USD
S-002,"22.00",USD
S-003,3.25,USD
~~~

Contract rules:

| CSV Field | Parsed Type | Constraints |
| --- | --- | --- |
| `external_id` | `String` | `A-Z`, `0-9`, hyphen/underscore, max 64 characters; unique within the file |
| `amount` | `BigDecimal` | Greater than 0, at most 2 decimal places, fits `NUMERIC(18,2)` |
| `currency` | `String` | `USD` in this demo (normalized to uppercase) |

The line `S-002,"22.00",USD` demonstrates CSV quoting. In real-world data, a field may contain commas or escaped double quotes; **`String.split(",")` parses those cases incorrectly**.

To make verification easy, choose a file with exactly **3 data rows** totaling **35.75 USD**. Do not rely on the system date to implicitly pick a period, because a task launched late past midnight could accidentally import into the wrong date.

## 7. Maven Project Structure

Example file layout created by the learner in the practice project:

~~~text
csv-import-task/
├── pom.xml
├── data/
│   └── sales-2026-11-24.csv
└── src/
    └── main/
        ├── java/com/example/csvtask/
        │   ├── CsvImportApplication.java
        │   ├── CsvFileLoader.java
        │   └── CsvImportService.java
        └── resources/
            └── application.yml
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>csv-import-task</artifactId>
    <version>1.0.0</version>
    <name>csv-import-task</name>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.0.2</spring-cloud.version>
        <commons-csv.version>1.14.1</commons-csv.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-task</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-csv</artifactId>
            <version>${commons-csv.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Why is each dependency needed?**

- `spring-cloud-starter-task` provides Task infrastructure and `TaskRepository`.
- `spring-boot-starter-jdbc` provides `JdbcTemplate`, `DataSource`, and transaction management.
- `postgresql` is the database JDBC driver.
- `commons-csv` handles headers, field quoting, and record parsing.
- Spring Batch is omitted in the main demo step because **one `ApplicationRunner` suffices for small files**. The final section explains how to upgrade to Batch.

## 8. Configuring Spring Boot and TaskRepository

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: csv-import-task
  main:
    web-application-type: none
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5433/taskdemo}
    username: ${DB_USER:taskdemo}
    password: ${DB_PASSWORD:local-demo-only}
    driver-class-name: org.postgresql.Driver
  cloud:
    task:
      name: csv-import-task
      initialize-enabled: true
      closecontextEnabled: true

logging:
  level:
    org.springframework.cloud.task: INFO
~~~

Explanation:

- `spring.main.web-application-type: none`: the task runs as a console process without starting an HTTP server.
- `spring.datasource.*`: **persistent PostgreSQL** used by both Spring Cloud Task and business tables.
- `spring.cloud.task.name`: name used for querying in `TASK_EXECUTION`.
- `initialize-enabled: true`: enables initialization of Task tables using the Spring Cloud Task version's mechanism. **Use only in a lab on an isolated database**, after verifying the schema is created cleanly without conflicts.
- `closecontextEnabled: true`: instructs the context to close after runners finish and `TaskRepository` has been updated per framework behavior; helps finite processes exit when no background threads keep the JVM alive.
- Every run creates a **new `TaskExecution`**, even when inputs and business keys are identical.

**Production:** DBAs or a migration tool must manage `TASK_*` tables with exact version-matched DDL, switching `initialize-enabled: false` and using secrets for credentials. Do not grant `CREATE TABLE` privileges to runtime users unnecessarily. The configuration here is for local illustration; the demo password is not safe for real systems.

## 9. CSV Reading and Validation Class: CsvFileLoader

Reading and validating the file **before opening a transaction** keeps the JDBC transaction short and avoids holding locks while parsing. To hash the exact content that was parsed, this lesson reads a single byte snapshot; later file edits will not cause the checksum to diverge from imported data. Size limits help prevent exhausting heap memory in the example.

Create `src/main/java/com/example/csvtask/CsvFileLoader.java`:

~~~java
package com.example.csvtask;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.springframework.stereotype.Component;

@Component
public class CsvFileLoader {

    private static final int MAX_BYTES = 4 * 1024 * 1024;
    private static final int MAX_ROWS = 10_000;

    public record SaleRow(
            String externalId, BigDecimal amount, String currency) {}

    public record CsvData(String sha256, List<SaleRow> rows) {}

    public CsvData load(Path file) throws IOException {
        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException(
                    "INPUT_NOT_FILE: " + file);
        }

        long fileSize = Files.size(file);
        if (fileSize == 0 || fileSize > MAX_BYTES) {
            throw new IllegalArgumentException(
                    "INPUT_SIZE_INVALID: 4 MiB limit");
        }

        // Read a single byte snapshot for both parsing and checksum calculation.
        byte[] bytes = Files.readAllBytes(file);
        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("INPUT_SIZE_INVALID");
        }

        // Keep it simple for the lesson: require UTF-8 without BOM.
        if (bytes.length >= 3
                && (bytes[0] & 0xff) == 0xef
                && (bytes[1] & 0xff) == 0xbb
                && (bytes[2] & 0xff) == 0xbf) {
            throw new IllegalArgumentException(
                    "INPUT_BOM_NOT_SUPPORTED");
        }

        // Do not silently replace malformed UTF-8 bytes with U+FFFD.
        String csvText = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();

        CSVFormat format = CSVFormat.RFC4180.builder()
                .setHeader()
                .setSkipHeaderRecord(true)
                .setIgnoreEmptyLines(true)
                .get();

        List<SaleRow> rows = new ArrayList<>();
        Set<String> seenIds = new HashSet<>();

        try (CSVParser parser = CSVParser.parse(csvText, format)) {
            List<String> expected = List.of(
                    "external_id", "amount", "currency");

            if (!parser.getHeaderNames().equals(expected)) {
                throw new IllegalArgumentException(
                        "INPUT_HEADER_INVALID: " + parser.getHeaderNames());
            }

            for (CSVRecord record : parser) {
                if (!record.isConsistent()) {
                    throw new IllegalArgumentException(
                            "INVALID_COLUMNS: record=" + record.getRecordNumber());
                }
                if (rows.size() >= MAX_ROWS) {
                    throw new IllegalArgumentException(
                            "TOO_MANY_ROWS: max " + MAX_ROWS);
                }

                String id = record.get("external_id").trim();
                if (!id.matches("[A-Z0-9][A-Z0-9_-]{0,63}")) {
                    throw new IllegalArgumentException(
                            "INVALID_EXTERNAL_ID: record=" + record.getRecordNumber());
                }
                if (!seenIds.add(id)) {
                    throw new IllegalArgumentException(
                            "DUPLICATE_EXTERNAL_ID: " + id);
                }

                BigDecimal amount;
                try {
                    amount = new BigDecimal(
                            record.get("amount").trim())
                            .setScale(2, RoundingMode.UNNECESSARY);
                } catch (NumberFormatException | ArithmeticException ex) {
                    throw new IllegalArgumentException(
                            "INVALID_AMOUNT: record=" + record.getRecordNumber(),
                            ex);
                }
                if (amount.signum() <= 0 || amount.precision() > 18) {
                    throw new IllegalArgumentException(
                            "INVALID_AMOUNT_RANGE: record="
                            + record.getRecordNumber());
                }

                String currency = record.get("currency")
                        .trim().toUpperCase(Locale.ROOT);
                if (!"USD".equals(currency)) {
                    throw new IllegalArgumentException(
                            "INVALID_CURRENCY: record=" + record.getRecordNumber());
                }

                rows.add(new SaleRow(id, amount, currency));
            }
        }

        if (rows.isEmpty()) {
            throw new IllegalArgumentException("EMPTY_CSV");
        }

        return new CsvData(
                sha256(bytes),
                List.copyOf(rows));
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

### 9.1. Why Not Use String.split?

The CSV format allows values enclosed in double quotes that may contain commas, escaped double quotes, or line breaks inside a field. `String.split(",")` does not understand those rules. `CSVParser` handles record structure, while we validate **header names and business values**.

### 9.2. When Is a Checksum Considered Stable?

`sha256(bytes)` hashes the **raw bytes**, including encoding, line endings, and whitespace. Consequently, two files representing the same logical data but differing in CRLF/LF or trailing blank lines will produce different hashes and be treated as **different contents**. This is an intentional **strict-bytes policy** for the example.

If a system needs equivalence checks **by business record**, define a versioned canonicalization process prior to hashing. Never change the hashing policy silently after data has already been imported.

### 9.3. Demo Limitations

- The entire small file is loaded into a `byte[]`/`String` and its row list into memory; do not use this approach for multi-GiB CSV files.
- Only `USD` is supported to avoid multi-currency handling and differing rounding rules.
- The parser rejects UTF-8 with BOM; to support it, strip the BOM **properly** and specify which bytes are hashed.
- If a file is being written concurrently, a snapshot may capture incomplete content. Deliver files via **temp file → atomic rename** or object storage with versions/ETags.

## 10. Service Writing to PostgreSQL in One Transaction

Create `src/main/java/com/example/csvtask/CsvImportService.java`:

~~~java
package com.example.csvtask;

import java.sql.Date;
import java.time.LocalDate;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.csvtask.CsvFileLoader.CsvData;
import com.example.csvtask.CsvFileLoader.SaleRow;

@Service
public class CsvImportService {

    private final JdbcTemplate jdbc;

    public CsvImportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record ImportRequest(
            String tenant, LocalDate businessDate, String sourceVersion) {}

    public enum Outcome {
        CREATED, ALREADY_APPLIED
    }

    private record Existing(String sha256, int rows) {}

    @Transactional
    public Outcome importOnce(
            ImportRequest request,
            CsvData data,
            boolean failAfterFirstRow) {

        Date date = Date.valueOf(request.businessDate());

        // Ledger and all sales_line rows belong to the SAME transaction.
        int inserted = jdbc.update("""
            INSERT INTO csv_import (
                tenant_id, business_date, source_version,
                input_sha256, row_count
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, source_version)
            DO NOTHING
            """,
            request.tenant(), date, request.sourceVersion(),
            data.sha256(), data.rows().size());

        if (inserted == 0) {
            // When the business key already exists, DO NOT INSERT additional rows.
            Existing existing = jdbc.queryForObject("""
                SELECT input_sha256, row_count
                FROM csv_import
                WHERE tenant_id = ?
                  AND business_date = ?
                  AND source_version = ?
                """,
                (rs, i) -> new Existing(
                        rs.getString("input_sha256").trim(),
                        rs.getInt("row_count")),
                request.tenant(), date, request.sourceVersion());

            if (!existing.sha256().equals(data.sha256())
                    || existing.rows() != data.rows().size()) {
                throw new IllegalStateException(
                        "IDEMPOTENCY_CONFLICT: key already bound to another file");
            }

            Long actualRows = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM sales_line
                WHERE tenant_id = ?
                  AND business_date = ?
                  AND source_version = ?
                """,
                Long.class,
                request.tenant(), date, request.sourceVersion());

            if (actualRows == null
                    || actualRows.longValue() != data.rows().size()) {
                throw new IllegalStateException(
                        "INTEGRITY_MISMATCH: ledger differs from data");
            }

            return Outcome.ALREADY_APPLIED;
        }

        int rowNumber = 0;
        for (SaleRow row : data.rows()) {
            jdbc.update("""
                INSERT INTO sales_line (
                    tenant_id, business_date, source_version,
                    external_id, amount, currency
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                request.tenant(), date, request.sourceVersion(),
                row.externalId(), row.amount(), row.currency());

            rowNumber++;
            if (failAfterFirstRow && rowNumber == 1) {
                throw new IllegalStateException(
                        "DEMO_FAILURE_BEFORE_COMMIT");
            }
        }

        return Outcome.CREATED;
    }
}
~~~

### 10.1. Why Does the Transaction Span Both Tables?

When `@Transactional` runs properly through a Spring bean proxy, the same `DataSourceTransactionManager` wraps all SQL statements. If any row triggers an exception before commit, PostgreSQL rolls back **both the ledger and all previously inserted rows**.

Do not split into:

~~~text
transaction A: INSERT csv_import, COMMIT
transaction B: INSERT each sales_line, COMMIT
~~~

because the JVM could crash after transaction A, leaving a ledger claiming the import succeeded with incomplete data.

**In this example, no external APIs or output files are written inside the transaction**; if there were, JDBC rollback could not automatically undo those external side effects. Multi-step systems require checkpoints/outboxes/idempotency at the target boundary.

### 10.2. Why Is a Primary Key Needed Even with SELECT Checks?

Two processes launched for the same period could simultaneously `SELECT` and see "not present". If you only check-then-insert, both could write data. `PRIMARY KEY` and `ON CONFLICT DO NOTHING` place the guard inside PostgreSQL, resolving race conditions atomically. The example assumes PostgreSQL's default **READ COMMITTED** isolation level.

While one transaction holds an uncommitted unique lock, another transaction may have to wait for the outcome; do not infer from a slow "INSERT waiting" log that an error occurred. Under stricter isolation levels, account for serialization failures and retry **the entire transaction**.

### 10.3. Uncertain Commit Outcomes

Suppose PostgreSQL received `COMMIT` but the network dropped before returning the response. The caller may get a connection error and the Task report failure, **even though the data was saved**. A subsequent run with **the same business key and same bytes** will:

- Detect the existing ledger.
- Compare SHA-256, row count, and committed row count.
- Return `ALREADY_APPLIED` without creating duplicate data.

While the DB is unreachable, **you cannot conclude** the previous transaction rolled back. The orchestrator must mark the run for reconciliation and re-read later rather than launching retries blindly.

### 10.4. Performance

For a 3-row file, calling `jdbc.update` per row is easy to read. For several thousand rows, use `JdbcTemplate.batchUpdate` to cut round-trips while staying in **one transaction**. For very large files, wrapping everything in one transaction causes long locks, large rollback segments, and high memory usage; that is when Spring Batch's chunk model is needed.

## 11. ApplicationRunner: Parsing Arguments and Calling the Service

Create `src/main/java/com/example/csvtask/CsvImportApplication.java`:

~~~java
package com.example.csvtask;

import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import com.example.csvtask.CsvImportService.ImportRequest;
import com.example.csvtask.CsvImportService.Outcome;

@SpringBootApplication
public class CsvImportApplication {

    private static final Logger log =
            LoggerFactory.getLogger(CsvImportApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(CsvImportApplication.class, args);
    }

    @Bean
    ApplicationRunner importRunner(
            CsvFileLoader loader, CsvImportService service) {
        return args -> {
            String tenant = required(args, "tenant");
            String sourceVersion = required(args, "sourceVersion");
            LocalDate businessDate =
                    LocalDate.parse(required(args, "businessDate"));
            String runId = required(args, "runId");
            Path file = Path.of(required(args, "input"));

            if (!tenant.matches("[a-z0-9][a-z0-9-]{0,63}")) {
                throw new IllegalArgumentException("INVALID_TENANT");
            }
            if (!sourceVersion.matches(
                    "[A-Za-z0-9][A-Za-z0-9_-]{0,31}")) {
                throw new IllegalArgumentException("INVALID_SOURCE_VERSION");
            }

            log.info(
                    "event=csv.import.start runId={} tenant={} date={} version={}",
                    runId, tenant, businessDate, sourceVersion);

            CsvFileLoader.CsvData data = loader.load(file);
            ImportRequest request = new ImportRequest(
                    tenant, businessDate, sourceVersion);

            // Use this flag only in test environments to prove rollback.
            boolean failDemo = args.containsOption("failAfterFirstRow");

            Outcome outcome = service.importOnce(
                    request, data, failDemo);

            // This runs after the @Transactional proxy has committed successfully.
            log.info(
                    "event=csv.import.done runId={} outcome={} rows={} sha256={}",
                    runId, outcome, data.rows().size(), data.sha256());
        };
    }

    private static String required(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Must pass exactly one --" + name + "=...");
        }
        return values.get(0).trim();
    }
}
~~~

**Observing the call flow:**

1. `SpringApplication.run` builds the context, sets up `DataSource`, and initializes the Spring Cloud Task lifecycle.
2. `ApplicationRunner` receives parameters, parses the file, and validates it.
3. Calls `service.importOnce(...)` **through the Spring bean**, so `@Transactional` applies.
4. The service returns `CREATED` or `ALREADY_APPLIED` after the transaction has committed from the caller's viewpoint.
5. Spring Cloud Task records completion in `TaskRepository` when the infrastructure is healthy.

If the parser or service throws an exception, the runner **does not swallow the error**. Spring Boot/Task handles the failure through its lifecycle mechanism; exit codes and metadata are inspected in the verification steps. `runId` correlates logs between scheduler and application, **not** as a business deduplication key.

### Why Not Call System.exit Directly in the Runner?

Calling `System.exit(...)` before the Spring Cloud Task lifecycle finishes can prevent recording `END_TIME`/`EXIT_CODE` and cleanly closing resources. In this example, let Spring Boot/Task orchestrate the lifecycle; in environments requiring explicit exit handling, apply exit policies only after the context/lifecycle completes and verify against your version.

## 12. Packaging and Running the First Import

From the practice project root:

~~~bash
./mvnw clean package
~~~

If using a pre-installed Maven binary, use `mvn clean package`; on Windows, use `mvnw.cmd clean package`. Example artifact:

~~~text
target/csv-import-task-1.0.0.jar
~~~

Run with the input path relative to the current working directory:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-24 --sourceVersion=v1 --input=data/sales-2026-11-24.csv --runId=demo-001
~~~

Expect business logs containing messages similar to:

~~~text
event=csv.import.start runId=demo-001 tenant=shop-01 date=2026-11-24 version=v1
event=csv.import.done runId=demo-001 outcome=CREATED rows=3 sha256=<64-char hash>
~~~

The exact `TASK_EXECUTION_ID` and hash depend on the framework and file bytes. Simply seeing `outcome=CREATED` in logs does not prove `TaskRepository` wrote final metadata; the SQL verification step confirms that.

## 13. Querying PostgreSQL to Verify Business Data

In `psql` or your SQL client, run:

~~~sql
SELECT tenant_id, business_date, source_version,
       row_count, input_sha256, completed_at
FROM csv_import
ORDER BY completed_at DESC;
~~~

Expect one ledger entry for `shop-01, 2026-11-24, v1` with `row_count=3`.

~~~sql
SELECT external_id, amount, currency
FROM sales_line
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1'
ORDER BY external_id;
~~~

Expected:

| external_id | amount | currency |
| --- | ---: | --- |
| S-001 | 10.50 | USD |
| S-002 | 22.00 | USD |
| S-003 | 3.25 | USD |

Aggregation:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales_line
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1';
~~~

Expected:

~~~text
row_count   | total_amount
3           | 35.75
~~~

**Important invariant:** business data is identified by the **business key**, not by `TASK_EXECUTION_ID`, because each attempt can receive a new Task ID.

## 14. Querying Persistent Spring Cloud Task History

If the Task infrastructure initialized its tables successfully, inspect:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'csv-import-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Fields to understand:

| Field | Meaning |
| --- | --- |
| `TASK_EXECUTION_ID` | Unique ID of **each application run** |
| `TASK_NAME` | Task name from configuration |
| `START_TIME` | Timestamp when framework recorded startup |
| `END_TIME` | Timestamp when framework recorded completion, if persisted |
| `EXIT_CODE` | Result code per Spring Boot/Spring Cloud Task mechanism |
| `EXIT_MESSAGE` | Completion message if set by the application or listener |
| `ERROR_MESSAGE` | May contain exception stack-trace excerpts when a Task-observed error occurs |

The demo application **does not explicitly set `EXIT_MESSAGE`**, so this field may be empty. Do not expect `CREATED` or `ALREADY_APPLIED` to appear automatically in `EXIT_MESSAGE`: those two values are currently written in the runner logs.

### Interpreting Common Outcomes

- Normal successful run: expect `END_TIME` populated and `EXIT_CODE=0` per framework policy.
- Runner throws an exception: expect a failure code and possibly `ERROR_MESSAGE`; exact content varies by version and column limits.
- If the JVM is killed, DB connection drops, or bootstrap fails very early: the record may **lack `END_TIME` or not exist**.
- Having multiple `TASK_EXECUTION` rows with the same `TASK_NAME` is normal after retries; inspect business tables to verify there are no duplicates.

### Why Does History Survive JVM Exit?

Because `spring.datasource` points to **PostgreSQL** with a persistent volume rather than an in-memory Map repository or H2 `mem:`. History is stored in the database, not inside beans of a terminated process.

However, **a persistent database is not a backup**. Volumes can be deleted, disks can fail, or databases can suffer data corruption; production requires backups, restore drills, retention policies, access control, and schema migrations.

## 15. Re-importing the Same File and Verifying Idempotency

Run a second time, **keeping tenant/date/version/input identical**, changing only `runId`:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-24 --sourceVersion=v1 --input=data/sales-2026-11-24.csv --runId=demo-002
~~~

Expected log:

~~~text
event=csv.import.done runId=demo-002 outcome=ALREADY_APPLIED rows=3 sha256=<same hash>
~~~

Verify:

~~~sql
SELECT COUNT(*) FROM sales_line
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1';

SELECT COUNT(*) FROM csv_import
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1';
~~~

Expect **3** and **1** respectively. Meanwhile:

~~~sql
SELECT TASK_EXECUTION_ID, START_TIME, END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'csv-import-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

will show **one more execution** if `TaskRepository` succeeded in recording it. This is the right result: **multiple attempts, one business effect**.

### Same Key with a Different File

Create a copy of the CSV and change `S-003,3.25,USD` to `S-003,99.00,USD`, then try running with the same `tenant`, `businessDate`, and `sourceVersion`. The hash differs and the service must report:

~~~text
IDEMPOTENCY_CONFLICT: key already bound to another file
~~~

Previously imported data **is unchanged**. If you truly want to publish a new import/report, choose a **new business version** (e.g., `--sourceVersion=v2`) per system rules instead of silently mutating `v1` history.

## 16. Testing Pre-Transaction Validation Errors

Edit a copy of the file, for example:

~~~csv
external_id,amount,currency
S-101,10.50,USD
S-102,not-a-number,USD
~~~

Run with a **different `businessDate`** so it does not collide with already-succeeded data:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-25 --sourceVersion=v1 --input=data/invalid-sales.csv --runId=demo-invalid
~~~

Expected:

- Parser throws `INVALID_AMOUNT`.
- No rows exist for `2026-11-25` in `csv_import` or `sales_line`.
- Spring Boot/Task reflects the runner error if context and repository initialized sufficiently; check `EXIT_CODE` and `ERROR_MESSAGE`.
- The scheduler or shell observes **process failure**, not success simply because JDBC wrote no data.

With SQL:

~~~sql
SELECT COUNT(*) FROM csv_import
WHERE business_date = DATE '2026-11-25';

SELECT COUNT(*) FROM sales_line
WHERE business_date = DATE '2026-11-25';
~~~

Both are expected to be `0` on this test database. Instead of parsing with `split(",")` and catching errors manually, keep parser/validation separate to surface clear error codes and avoid holding connections/transactions open while reading files.

## 17. Testing Rollback When an Error Occurs Mid-Transaction

To prove the transaction truly protects **both tables**, run the valid file with an **unused business key** and the `--failAfterFirstRow` flag:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-26 --sourceVersion=v1 --input=data/sales-2026-11-24.csv --runId=demo-rollback --failAfterFirstRow
~~~

According to section 10's code, the logical sequence is:

1. Insert one `csv_import` ledger row.
2. Insert row `S-001` into `sales_line`.
3. Throw `DEMO_FAILURE_BEFORE_COMMIT`.
4. Spring's transaction interceptor marks rollback, and PostgreSQL rolls back both changes.

Query:

~~~sql
SELECT COUNT(*) FROM csv_import
WHERE business_date = DATE '2026-11-26';

SELECT COUNT(*) FROM sales_line
WHERE business_date = DATE '2026-11-26';
~~~

Expect **0** and **0**. If the ledger remains while rows are missing, verify whether `@Transactional` actually ran through a bean proxy, whether both use the same `DataSource`/transaction manager, and whether any code committed outside the transaction.

After removing `--failAfterFirstRow` and re-running with the same business key, the program must create all 3 rows (`CREATED`). This differs from a **post-commit** timeout; in that case, results may already exist and the next run returns `ALREADY_APPLIED`.

### Note on This Test

This tests an **exception before commit**, and does not replicate a network failure **right after PostgreSQL commits but before the client receives the ACK**. For uncertain commits, use connection/driver fault injection or simulate the caller receiving an exception after service commit, then verify the retry produces no duplicates.

## 18. Testing Durability Across JVM and PostgreSQL Restarts

First, stop all `java -jar` processes. In `psql`, note the counts of ledger, sales, and `TaskExecution` rows.

Then stop and restart PostgreSQL **without removing the volume**:

~~~bash
docker stop csv-task-postgres
docker start csv-task-postgres
docker exec csv-task-postgres pg_isready -U taskdemo -d taskdemo
~~~

Reconnect:

~~~bash
docker exec -it csv-task-postgres psql -U taskdemo -d taskdemo
~~~

Check:

~~~sql
SELECT COUNT(*) FROM csv_import;
SELECT COUNT(*) FROM sales_line;
SELECT COUNT(*) FROM TASK_EXECUTION;
~~~

Counts must match what they were before stopping the container if no other process modified data and the volume remained intact. After restarting the JAR, importing the same `2026-11-24/v1` key must return `ALREADY_APPLIED` and record another `TaskExecution`; this demonstrates the difference between **persistent JDBC metadata** and an in-memory store tied to JVM lifetime.

To truly test production failover/backups, perform **backup/restore** and recovery drills on a fresh DB rather than merely stopping/starting a container.

## 19. Testing Two Concurrent Processes

`TaskRepository` only tracks individual `TaskExecution`s; it does not replace database-level deduplication. An additional experiment:

1. Prepare a fresh business key, e.g., `shop-01|2026-11-27|v1`.
2. Launch **two `java -jar` processes** with the same key and same CSV nearly simultaneously.
3. Wait for both to finish.
4. Query `csv_import` and `sales_line` for that period.

Expected:

- Exactly **1 ledger** and **3 `sales_line` rows**.
- One process may return `CREATED`; the other, after the unique conflict resolves, returns `ALREADY_APPLIED`.
- `TASK_EXECUTION` can record **2 runs**.
- PostgreSQL may cause one transaction to wait for the other to resolve the unique key; not every race condition will surface visibly in logs.

The primary key constraint in PostgreSQL must exist before running the test. Do not run both processes with `--failAfterFirstRow` to infer success behavior. In production, add concurrency limits, timeouts, and scheduler retry controls, because unique constraints **do not prevent two tasks from wasting excess CPU/IO simultaneously**.

## 20. When TaskRepository Has No Completion Record

An important part of this lesson is knowing **the limits of observability**:

| Situation | Business Data | `TASK_EXECUTION` Metadata | Action Required |
| --- | --- | --- | --- |
| Normal success | Committed | Usually has `END_TIME`, `EXIT_CODE=0` | Verify outputs |
| Invalid CSV before transaction | No new results | May record runner error | Check logs and `ERROR_MESSAGE` |
| Exception inside transaction | Rolled back | May record failure | Verify via SQL |
| Network drop right around commit | **Indeterminate** until reconciled | May be missing or show error code | Query business table by key |
| JVM receives `SIGKILL` after commit | Results may be complete | May lack `END_TIME` | Reconcile DB + process state |
| `ApplicationContext` fails before Task is ready | Runner did not execute | **May have no record** | Check bootstrap/scheduler logs |
| Database unreachable at startup | Task cannot save metadata | May create no record | Check DB and infrastructure |

**Conclusion:** `END_TIME IS NULL` does not prove the task is still running; having no `TaskExecution` does not prove the JVM never started. Combine scheduler/container state, logs, metadata, and **committed business results**.

## 21. Differences Between TaskRepository and the Ledger Table

It is easy to confuse `TaskRepository` and `csv_import` because both relate to "history":

- `TaskRepository`: history of **multiple technical runs**. It helps answer when a run happened, what exit code it produced, and why a runner failed.
- `csv_import`: history of **completed business imports** for a business key. It decides whether data may be written again.

Example of three attempts:

| Attempt | Task Exit Code | Ledger for Same Key | Sales Lines |
| --- | --- | ---: | ---: |
| 1 — failure before commit | Nonzero per policy | 0 | 0 |
| 2 — successful import | 0 | 1 | 3 |
| 3 — re-import same bytes | 0 | 1 | 3 |

Never delete failed `TaskExecution` rows to "clean up" reports. And never use `TASK_EXECUTION_ID` as the unique key for sales data: it changes on every retry, preventing duplicate detection.

## 22. Implementing with Spring Batch Instead

For large datasets or checkpoint-based restarts, replace `ApplicationRunner` with a **Spring Batch Job** (still running inside a Spring Cloud Task application):

~~~mermaid
flowchart LR
    A["FlatFileItemReader<SaleRow>"] --> B["ItemProcessor: validation"]
    B --> C["JdbcBatchItemWriter: PostgreSQL"]
    C --> D["JobRepository: checkpoint/StepExecution"]
    E["Spring Cloud Task"] --> F["TaskRepository: TaskExecution"]
    D --> G["Reconcile by business key"]
    F --> G
~~~

A typical Job includes:

- `FlatFileItemReader` reading CSV in chunks; configure `LineMapper`/`FieldSetMapper` to match the schema.
- `ItemProcessor` validating transaction IDs, amounts, checksums, or normalization.
- `JdbcBatchItemWriter` writing rows, participating in chunk transactions when properly configured.
- `JobRepository` persisting `JobExecution`, `StepExecution`, and `ExecutionContext` to support restarts.
- `TaskRepository` persisting **one application run**, independent of per-Step checkpoints.

When combining them, verify whether `BatchStatus.FAILED` propagates to the Task exit code. On supported versions you can set `spring.cloud.task.batch.fail-on-job-failure=true`. Never assume Spring Batch guarantees exactly-once delivery for external APIs, output files, or message brokers.

**Restart warning:** a multi-chunk Batch Job may have committed earlier chunks before failing. Retrying the whole process with different `JobParameters` can create a new `JobInstance` and reprocess data. Even with checkpoints, **unique business keys and idempotent writes** remain necessary.

## 23. Deploying on a Schedule or via API

A scheduler can invoke the JAR daily with arguments:

~~~text
--tenant=shop-01
--businessDate=2026-11-24
--sourceVersion=v1
--input=/data/imports/sales-2026-11-24.csv
--runId=schedule-20261124-attempt1
~~~

**You must pin `businessDate` to the actual scheduled occurrence**, rather than calling `LocalDate.now()` inside the runner and picking the wrong period if a schedule runs late. `runId` may vary across attempts, while `tenant/businessDate/sourceVersion` must remain unchanged for the same logical request.

When using Kubernetes CronJob or Spring Cloud Data Flow:

1. **Identify the request** before launch and record a receipt.
2. **Prevent overlapping runs** with an appropriate scheduler policy; DB unique constraints remain the final safety net.
3. **Verify completion** via `TaskExecution` and process exit code; do not treat a launch ACK as success.
4. **Reconcile outputs** before automatically retrying after timeouts or uncertain commit failures.
5. **Cap retry counts** and execution durations to avoid request storms.
6. Pass files through controlled volumes/object storage rather than ephemeral pod paths.
7. Centralize logs with `runId`, without logging secrets or sensitive full CSV payloads.

## 24. Common Issues and How to Handle Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `Connection refused` | PostgreSQL not running, wrong host/port | `pg_isready`, port mapping, `DB_URL` |
| `relation "task_execution" does not exist` | Task schema not created, wrong schema/prefix | Initializer, migrations, `search_path` |
| `permission denied for table` | JDBC user lacks privileges | SELECT/INSERT/UPDATE grants, separate migration user |
| `INPUT_HEADER_INVALID` | Wrong header, BOM, or renamed/recased columns | Check UTF-8 and the three standard columns |
| `INVALID_AMOUNT` | Comma decimal separator, letters, or >2 decimal places | Use dots and `BigDecimal` per contract |
| `DUPLICATE_EXTERNAL_ID` | CSV has two rows with the same ID | Fix source file; never silently drop a row |
| `IDEMPOTENCY_CONFLICT` | Same period/version but file content changed | Reconcile; use a new version if valid |
| `ALREADY_APPLIED` with no new rows | Expected result of re-running same request | Verify ledger and committed rows |
| Ledger exists while sales rows are missing | Different schema/transaction, manual DB edit, or design bug | Check transactions and `INTEGRITY_MISMATCH` |
| `END_TIME IS NULL` | JVM still running or failed before final update | Inspect runtime/logs/DB; do not guess |
| Second run fails trying to recreate schema | Initializer/version/schema mismatch | Switch to formal migrations, `initialize-enabled: false` |
| Data lost after container removal | Volume not preserved or wrong DB targeted | Check volume, JDBC URL, backups |
| Task exits nonzero but sales rows exist | Failure occurred after commit | Reconcile key/hash before retrying |

## 25. Safe Operations Checklist

- [ ] Compatible Java/Spring Boot/Spring Cloud Task versions and reproducible Maven build.
- [ ] PostgreSQL uses persistent storage; production has tested backup/restore.
- [ ] `TASK_*` schema is managed per exact framework version, not guessed by hand.
- [ ] Business key and import version are determined before execution.
- [ ] CSV validates encoding, headers, column count, data types, size limits, and duplicate IDs.
- [ ] Both ledger and rows are written **in a single transaction**.
- [ ] `PRIMARY KEY`/`UNIQUE` prevents duplicate writes across processes.
- [ ] Same key + same checksum → no duplicate write; same key + different checksum → conflict.
- [ ] Reconciliation procedure exists for commit-time disconnects; never assume rollback.
- [ ] On failure, runner never swallows exceptions causing false scheduler success.
- [ ] Rollback, re-import, PostgreSQL restart, and concurrent execution have all been tested.
- [ ] Logs include `runId`, bound message length, and never expose passwords or PII.
- [ ] Scheduler defines deadlines, retry budgets, and missed-window handling.
- [ ] For large files, migrate to Spring Batch chunk processing or streaming with checkpoints/idempotency.

## 26. Advanced Exercises

**Exercise A — Rename the file while keeping contents identical.** Copy the CSV to another path, run with the same business key, and verify the hash. Explain why the second run must return `ALREADY_APPLIED`.

**Exercise B — Modify contents.** Append `S-004,5.00,USD` to the CSV while keeping `sourceVersion=v1`. Why should the system not automatically append that row to an already-completed import?

**Exercise C — Concurrent deduplication.** Open two terminals and run with the same new key. Verify one ledger, three sales rows, and two `TaskExecution` rows under normal operation.

**Exercise D — Mid-write failure.** Run with `--failAfterFirstRow`. Explain why both the ledger and sales rows roll back when `@Transactional` is active.

**Exercise E — Metadata after a crash.** In a test environment, deliberately kill a process after DB commit but before `TaskRepository`'s final update. Compare exit code, `END_TIME`, ledger, and sales rows. Write a pre-retry verification plan.

**Exercise F — Batch.** Replace the parser and insert loop with `FlatFileItemReader`, `ItemProcessor`, `JdbcBatchItemWriter`, and `JobRepository`. Test restarting after one chunk commits and a later chunk fails.

**Exercise G — Change checksum policy.** Design canonicalization independent of CRLF/LF, introduce a `hashVersion`, and test two files with different bytes but equivalent records. Explain why hashing logic must not be changed without versioning legacy data.

## 27. Knowledge Self-Check

**Question 1.** Why might `TASK_EXECUTION` contain three rows even though `csv_import` has only one ledger entry?

**Question 2.** When the CSV file changes while `tenant`, `businessDate`, and `sourceVersion` stay the same, what must the system do? Why not overwrite automatically?

**Question 3.** Does an `SQLException` at `COMMIT` time prove that PostgreSQL rolled back?

**Question 4.** Why is `jdbc:postgresql://...` with a persistent volume critical for cross-run history compared to an in-JVM Map repository?

**Question 5.** Does `@Transactional` on a service take effect if the method is called directly from another method in the same class (self-invocation)?

**Question 6.** How does parsing CSV with `String.split(",")` differ from using a CSV library supporting quoting and headers?

**Question 7.** How would you change the architecture and restart strategy to process a 10-million-row file?

## 28. Key Takeaways

- **Spring Cloud Task** manages metadata for a finite run; **PostgreSQL TaskRepository** preserves history after the JVM exits.
- **CSV ingestion** requires validating format/encoding/schema and business data; never parse with `split(",")`.
- `@Transactional` combined with `PRIMARY KEY` constraints commits the ledger and sales rows atomically, protecting against partial writes on pre-commit failures.
- **The idempotency key** is `tenant + businessDate + sourceVersion`; the byte hash tells you whether a retry is using the exact same file.
- A Task may run multiple times but should produce **only one result per business key**; `TASK_EXECUTION_ID` is not a business deduplication key.
- **Network errors around `COMMIT` create an indeterminate state**, requiring reconciliation against committed data before retrying.
- `END_TIME IS NULL` or a missing `TaskExecution` does not prove work did not run, because bootstrap failures, JVM kills, and DB outages can lose metadata.
- For very large datasets, use Spring Batch or streaming/chunk architectures while keeping writes idempotent.

## References

- [Spring Cloud Task Reference — Features and Task Lifecycle](https://docs.spring.io/spring-cloud-task/reference/features.html): creating/updating `TaskExecution`, `TaskRepository`, and startup failure recording limits.
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html): `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, and related tables.
- [Spring Cloud Task — TaskRepositoryInitializer API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/support/TaskRepositoryInitializer.html): initializing Task tables when a `DataSource` and `initialize-enabled` are present.
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud/): matching Spring Cloud and Spring Boot versions.
- [Spring Cloud 2025.0.2 Release Announcement](https://spring.io/blog/2026/04/02/spring-cloud-2025-0-2-aka-northfields-has-been-released/): Spring Boot 3.5.13 baseline.
- [Apache Commons CSV — User Guide and API](https://commons.apache.org/proper/commons-csv/): RFC 4180 parser, headers, quoting, and record consistency.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT DO NOTHING` behavior.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): consistency and concurrent transactions.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxies, and rollback.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): upgrade path for large datasets.

**Note:** The JAR paths, database names, passwords, and input values in this lesson are illustrative. This is a guide for building and running the project yourself, **not a claim that the code was compiled/tested in the workspace**. Before production use, verify versions, DDL, PostgreSQL permissions, data limits, and run your own integration test suite. Content QA per the content workflow will take place after authoring.
