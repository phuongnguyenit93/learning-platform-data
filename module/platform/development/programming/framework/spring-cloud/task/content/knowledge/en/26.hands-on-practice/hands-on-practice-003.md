# Daily Report Generation with Safe Retry Handling

A task that generates a daily report seems simple: read paid invoices for the day, count them, sum the totals, save a report row, and exit. In practice, however, **the same day can be executed multiple times** when operators click re-run, Kubernetes Jobs retry, backfill schedules run, two Pods start simultaneously, or a process dies after writing data. If every run `INSERT`s another report or adds to the total amount, the system ends up with duplicate records and corrupted figures.

This hands-on lab belongs to the **Hands-On Practice** chapter of **Spring Cloud Task**. We build a finite **Spring Boot + Spring Cloud Task + PostgreSQL** application that generates a **daily invoice report per date and tenant**, persists results durably, records history in `TaskRepository`, and proves through tests that retries, concurrent runs, and pre-commit failures **never create two reports for the same business key**.

The core solution uses:

- **Business key:** `(tenant_id, business_date, report_version)`.
- **Explicit day boundaries:** `Asia/Ho_Chi_Minh`, converted to two UTC instants when querying `timestamptz`.
- **Single atomic aggregate-and-insert statement:** `INSERT ... SELECT ... ON CONFLICT DO NOTHING`, executed inside a transaction.
- **No cumulative addition on retry:** if the report already exists, return `ALREADY_EXISTS` instead of adding more data.
- **Separated state:** `TaskExecution` is history of *each technical run*, whereas the report table holds the result of *each business period*.

> **Important limitation:** This lab assumes source invoices for the day have been **finalized/frozen** before generating the report and report results are stored **in the same PostgreSQL database**. If source data changes after cutoff, the old report does not auto-update; a report versioning or source snapshot mechanism is needed. If you also send emails, write to object storage, or call external APIs outside the DB, design a dedicated outbox/idempotency layer. Never treat a SQL transaction as an exactly-once guarantee across external systems.

## 1. Objectives and Completion Criteria

After completing this lesson, you will be able to:

1. Run a Spring Cloud Task JAR accepting `--tenant-id`, `--business-date`, and `--report-version`.
2. Query `PAID` invoices belonging to the exact local day, cleanly excluding records right on midnight boundaries.
3. Store exactly **one report row per `(tenant, date, version)`** using a PostgreSQL unique constraint.
4. Re-run with the same parameters and observe `ALREADY_EXISTS`, without increasing `invoice_count` or `total_amount`.
5. Launch two processes concurrently and confirm **only one business result is created**.
6. Simulate an exception after the write statement but **before commit**, observe rollback, and re-run successfully.
7. Distinguish each attempt's `TaskExecution ID` from the report's business key.
8. Identify pattern limitations when source data changes, multiple systems are written, or the Task is killed.

### Expected Test Data

We use **2026-11-23** in **Vietnam time (UTC+07:00)** for tenant `acme`. In the sample dataset, only **3 `PAID` invoices** totaling **250.00** fall within that exact day.

| businessDate | tenantId | reportVersion | invoiceCount | totalAmount |
| --- | --- | ---: | ---: | ---: |
| `2026-11-23` | `acme` | `1` | **3** | **250.00** |

The first run returns `CREATED`; the second run with the same three parameters returns `ALREADY_EXISTS`; the report table still contains **one** row. This outcome is verifiable via SQL, not just logs.

## 2. Architecture: TaskExecution Is Not a Business Report

~~~mermaid
flowchart TD
    S["CronJob / API / terminal"] --> T["Spring Boot + @EnableTask"]
    T --> TR[("TaskRepository<br/>TASK_EXECUTION")]
    T --> A["ApplicationRunner: validate args"]
    A --> B["DailyReportService @Transactional"]
    B --> Q["INSERT ... SELECT ... ON CONFLICT DO NOTHING"]
    Q --> I[("invoice: finalized source data")]
    Q --> R[("daily_invoice_report<br/>PRIMARY KEY tenant + date + version")]
    B --> O["CREATED / ALREADY_EXISTS"]
    O --> T
~~~

**Two distinct types of identity:**

| Identifier | Example | Purpose |
| --- | --- | --- |
| `TaskExecution ID` | `4101` then `4102` | Distinguishes two Spring Cloud Task process runs |
| Business key | `acme / 2026-11-23 / v1` | Identifies **one logical report** |
| Kubernetes Job/Pod UID | Cluster-generated | Investigates a technical run |
| Spring Batch `JobInstance` (if extended) | Job name + identifying JobParameters | Manages Batch restarts/checkpoints |

A Task may end **technically successfully without inserting a new row** because the report already exists: that is `ALREADY_EXISTS`, a valid idempotent outcome. Conversely, in more complex architectures, a Task may fail after business data has committed; therefore **never use `TaskExecution` as the report deduplication mechanism**.

## 3. Environment Setup and Dependencies

You need:

- A JDK compatible with your project's Spring Boot/Spring Cloud Task versions; with **Spring Boot 3.x**, **JDK 17+** is standard.
- Maven or Gradle and a Spring Boot application with `spring-cloud-starter-task`.
- PostgreSQL for **both `TaskRepository` and the lab tables**; the practice setup uses **one `DataSource`** to keep transactions simple.
- Table-creation privileges for the migration account and read/write privileges for the Task runtime account.
- Ability to invoke the same JAR multiple times, or optionally a Kubernetes Job for the advanced section.

### 3.1. Maven Dependencies

In a Spring Boot project `pom.xml` configured with a **compatible Spring Cloud BOM**, the core dependencies are:

~~~xml
<dependencies>
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is a dependency snippet, **not a complete `pom.xml`**. Declare `spring-boot-starter-parent`/plugins and the Spring Cloud release train BOM **matching the exact version** you selected. Never mix arbitrary Spring Boot and Spring Cloud Task versions just because dependencies resolve.

This lab uses **plain JDBC** instead of Spring Batch. Spring Cloud Task still provides lifecycle management and metadata; later, if large data volumes require chunks/checkpoints, you can swap the aggregation core for Spring Batch while keeping the same business key and idempotency requirements.

### 3.2. Application Configuration

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: daily-invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      maximum-pool-size: 3
  cloud:
    task:
      initialize-enabled: false
      closecontext-enabled: true
~~~

**Why these settings?** `web-application-type: none` avoids keeping an HTTP server alive after the runner finishes. `closecontext-enabled: true` closes the context after the Task lifecycle completes. A pool of 3 connections is just a starting point for a small Task and should be benchmarked as concurrency grows.

`initialize-enabled: false` is only valid when the **`TaskRepository` schema has already been migrated** using DDL compatible with your Spring Cloud Task version. This lab creates only the two business tables and **does not hand-write `TASK_EXECUTION` DDL**. If metadata tables are missing, the Task may fail at startup; run the Task schema migrations provided by the library version instead of guessing table structures manually.

Never put real passwords in YAML/CLI. Supply `TASK_DB_URL`, `TASK_DB_USER`, and `TASK_DB_PASSWORD` via environment variables or Secrets. **Spring Cloud Task may store arguments in `TASK_EXECUTION_PARAMS`**, so never pass `--spring.datasource.password=...` when running a Task.

## 4. Creating the Business Schema

The following statements run on your **lab PostgreSQL instance**, not directly in production.

### 4.1. Source Invoice Table

~~~sql
CREATE TABLE invoice (
    id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id   varchar(64) NOT NULL,
    paid_at     timestamptz NOT NULL,
    status      varchar(16) NOT NULL,
    amount      numeric(18, 2) NOT NULL CHECK (amount >= 0)
);

CREATE INDEX idx_invoice_paid_tenant_time
    ON invoice (tenant_id, paid_at)
    WHERE status = 'PAID';
~~~

`paid_at` is stored as `timestamptz`, representing **an absolute point in time**. When reporting by calendar day in Vietnam, never compare a `YYYY-MM-DD` string directly against timestamps while ignoring timezones.

This sample table simplifies behavior: invoice `status` is confirmed before publication and does not change within a finalized reporting period. In real systems, analyze late arrivals, refunds, cancellations, and reissue requests.

### 4.2. Deduplicated Report Table

~~~sql
CREATE TABLE daily_invoice_report (
    tenant_id       varchar(64) NOT NULL,
    business_date   date NOT NULL,
    report_version  integer NOT NULL CHECK (report_version >= 1),
    invoice_count   bigint NOT NULL CHECK (invoice_count >= 0),
    total_amount    numeric(20, 2) NOT NULL,
    generated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

**The three-column PRIMARY KEY is the decisive deduplication barrier.** Two concurrent processes may both pass a "does not exist yet" check in Java, but the DB allows only **one row** for a given `(tenant_id, business_date, report_version)`.

Therefore, **never use a pre-check like this as your sole protection**:

~~~text
if (!reportExists(tenant, date)) {
    insertReport(tenant, date);
}
~~~

That is a *check-then-act* race: two Pods can both see no row and both insert. You need a **unique constraint + atomic statement**, or an equally consistent locking mechanism.

### 4.3. Seeding Boundary Test Data

Run only in the lab database where you just created the tables; **never run `TRUNCATE` on real data**:

~~~sql
TRUNCATE TABLE daily_invoice_report, invoice RESTART IDENTITY;

INSERT INTO invoice (tenant_id, paid_at, status, amount)
VALUES
  ('acme', '2026-11-22T16:59:59+00:00', 'PAID', 100.00),
  ('acme', '2026-11-22T17:00:00+00:00', 'PAID', 120.00),
  ('acme', '2026-11-23T05:30:00+00:00', 'PAID',  80.00),
  ('acme', '2026-11-23T16:59:59+00:00', 'PAID',  50.00),
  ('acme', '2026-11-23T17:00:00+00:00', 'PAID', 300.00),
  ('acme', '2026-11-23T06:00:00+00:00', 'CANCELLED', 70.00),
  ('beta', '2026-11-23T07:00:00+00:00', 'PAID', 999.00);
~~~

The date **2026-11-23** in `Asia/Ho_Chi_Minh` corresponds to:

~~~text
startInclusive = 2026-11-22T17:00:00Z
endExclusive   = 2026-11-23T17:00:00Z

Condition: startInclusive <= paid_at < endExclusive
~~~

| Record | Outcome |
| --- | --- |
| `acme`, Nov 22 16:59:59Z, 100 | Excluded: before start of day |
| `acme`, Nov 22 17:00:00Z, 120 | **Included** |
| `acme`, Nov 23 05:30:00Z, 80 | **Included** |
| `acme`, Nov 23 16:59:59Z, 50 | **Included** |
| `acme`, Nov 23 17:00:00Z, 300 | Excluded: belongs to next day |
| `acme`, `CANCELLED`, 70 | Excluded: not `PAID` |
| `beta`, Nov 23 07:00Z, 999 | Excluded: different tenant |

**Exact expectation:** `invoice_count=3`, `total_amount=250.00`. This seed set tests timezone, tenant, status, and half-open boundaries simultaneously.

## 5. Java: Parsing Arguments and Exiting Cleanly

Create `DailyInvoiceReportTaskApplication.java`:

~~~java
package example.reporting;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyInvoiceReportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(DailyInvoiceReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner reportRunner(DailyReportService service) {
        return args -> {
            String tenant = required(args, "tenant-id");
            LocalDate date = parseDate(required(args, "business-date"));
            int version = parseVersion(required(args, "report-version"));

            // For lab use only to test transaction rollback.
            // Remove this switch before deploying to production.
            boolean failBeforeCommit =
                    args.containsOption("lab-fail-before-commit");

            boolean created = service.generate(
                    tenant, date, version, failBeforeCommit);

            System.out.printf(
                    "report tenant=%s date=%s version=%d outcome=%s%n",
                    tenant,
                    date,
                    version,
                    created ? "CREATED" : "ALREADY_EXISTS");
        };
    }

    private static String required(ApplicationArguments args, String key) {
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1
                || values.get(0) == null || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid option: " + key);
        }
        return values.get(0);
    }

    private static LocalDate parseDate(String value) {
        try {
            return LocalDate.parse(value); // yyyy-MM-dd
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Invalid --business-date; expected yyyy-MM-dd");
        }
    }

    private static int parseVersion(String value) {
        try {
            int version = Integer.parseInt(value);
            if (version < 1) {
                throw new NumberFormatException();
            }
            return version;
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Invalid --report-version; expected positive integer");
        }
    }
}
~~~

**Explanation:**

- `@EnableTask` enables the Spring Cloud Task lifecycle; runners are invoked during startup.
- `ApplicationArguments` reads options like `--tenant-id=acme`; strings must include **`--`** when read via `getOptionValues`.
- Never log all of `args.getSourceArgs()`, as it may expose sensitive data or personal information. This example logs only three allowlisted values.
- If validation or the service throws an exception, the runner **must not swallow it**; verify the application exit code so the scheduler sees the Task fail.
- `ALREADY_EXISTS` is not an error: it is an **intentional no-op** when a reporting period has already been published.
- The `--lab-fail-before-commit` switch is strictly a lab fault-injection tool and **must not remain in production builds**.

The application runs no HTTP server and the runner executes **synchronously**, so upon completion Spring Cloud Task can record results and close the context. If the service later uses `CompletableFuture`, it must wait for the Future to finish before the runner returns.

## 6. Java: Atomic Aggregation and Report Insertion

Create `DailyReportService.java` in the same package:

~~~java
package example.reporting;

import java.sql.Date;
import java.sql.Types;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DailyReportService {

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static final String INSERT_REPORT = """
        INSERT INTO daily_invoice_report (
            tenant_id,
            business_date,
            report_version,
            invoice_count,
            total_amount,
            generated_at
        )
        SELECT :tenantId,
               :businessDate,
               :reportVersion,
               COUNT(i.id),
               COALESCE(SUM(i.amount), 0),
               CURRENT_TIMESTAMP
        FROM invoice i
        WHERE i.tenant_id = :tenantId
          AND i.status = 'PAID'
          AND i.paid_at >= :fromUtc
          AND i.paid_at < :toUtc
        ON CONFLICT (tenant_id, business_date, report_version)
        DO NOTHING
        """;

    private final NamedParameterJdbcTemplate jdbc;

    public DailyReportService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean generate(
            String tenantId,
            LocalDate businessDate,
            int reportVersion,
            boolean labFailBeforeCommit) {

        if (tenantId == null ||
                !tenantId.matches("[a-z0-9][a-z0-9_-]{0,63}")) {
            throw new IllegalArgumentException(
                    "Invalid tenant-id format");
        }
        if (businessDate == null || reportVersion < 1) {
            throw new IllegalArgumentException(
                    "Invalid report date or version");
        }

        Instant from = businessDate
                .atStartOfDay(BUSINESS_ZONE)
                .toInstant();
        Instant to = businessDate.plusDays(1)
                .atStartOfDay(BUSINESS_ZONE)
                .toInstant();

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("businessDate",
                          Date.valueOf(businessDate), Types.DATE)
                .addValue("reportVersion", reportVersion)
                .addValue("fromUtc",
                          OffsetDateTime.ofInstant(from, ZoneOffset.UTC),
                          Types.TIMESTAMP_WITH_TIMEZONE)
                .addValue("toUtc",
                          OffsetDateTime.ofInstant(to, ZoneOffset.UTC),
                          Types.TIMESTAMP_WITH_TIMEZONE);

        int insertedRows = jdbc.update(INSERT_REPORT, params);

        // Lab only: proves an exception rolls back the inserted row.
        if (labFailBeforeCommit) {
            throw new IllegalStateException(
                    "LAB_SIMULATED_FAILURE_BEFORE_COMMIT");
        }

        if (insertedRows != 0 && insertedRows != 1) {
            throw new IllegalStateException(
                    "Unexpected number of report rows");
        }
        return insertedRows == 1;
    }
}
~~~

### 6.1. Why Use INSERT ... SELECT ... ON CONFLICT?

This is **a single SQL statement** performing both aggregation and insertion of one record. It avoids the race-prone "SELECT to check → compute in application → INSERT" cycle between two processes. PostgreSQL executes each statement atomically; `@Transactional` also allows verifying pre-commit rollback and provides an extension point if an outbox insert is later added in the same transaction.

When two transactions try to write **the same primary key**:

- The first transaction succeeds and commits: it creates **one report**.
- The second transaction hits a conflict: with `ON CONFLICT DO NOTHING`, inserted rows is **0**; the application returns `ALREADY_EXISTS`.
- If the first transaction fails **before commit** and rolls back: the second transaction can proceed to insert; no partial report is committed.

Under PostgreSQL's default `READ COMMITTED` isolation level, contention may force one transaction to **wait for the other** to commit or roll back. Do not assume two Pods never block each other; what is guaranteed is **no duplicate business keys are inserted** while the DB constraint is active.

### 6.2. Why Not Use Cumulative Addition?

Wrong for a finalized daily report:

~~~sql
-- ANTI-PATTERN: retries can add the amount again.
UPDATE daily_invoice_report
SET total_amount = total_amount + :new_amount
WHERE tenant_id = :tenant_id
  AND business_date = :business_date;
~~~

If the application re-runs after this transaction commits, the total amount gets doubled. This lab **computes an absolute sum** from the source and performs **insert-once**. `ON CONFLICT DO NOTHING` preserves the originally published version.

Another option for recomputable problems is `ON CONFLICT DO UPDATE SET total_amount = EXCLUDED.total_amount` (assigning the absolute value). However, if source rows changed, re-running would **alter an already published report**; that is a different policy, not the desired behavior in this lab.

### 6.3. Why Finalize Source Data First?

The `SELECT` reads a transactional snapshot at execution time. If a late invoice arrives **after the first run**, retrying with `reportVersion=1` hits the conflict and **does not alter the result**. This is **immutability of a published report**, not a guarantee that late invoices are automatically folded in.

In production, establish a pre-launch workflow before triggering the report:

1. Wait for source feeds for `businessDate` to complete/finalize.
2. Record a **READY/FINALIZED** source status or immutable snapshot/version.
3. Launch the report only when sources are ready, using consistent timezone and dataset boundaries.
4. If corrections are needed after publication, run **`reportVersion=2`** under a controlled republish policy while keeping v1 history for audit reconciliation.

The current sample code **assumes source finalization happens externally** and does not check a READY state itself. To productionize, bring the READY/snapshot check into **the same transaction boundary or a reliable orchestration step** to avoid empty reports from late sources.

## 7. First Run: Report Is Created

First configure the JDBC environment; for example:

~~~text
TASK_DB_URL=jdbc:postgresql://db.example.internal:5432/task_lab
TASK_DB_USER=task_runtime
TASK_DB_PASSWORD=<fetched from secret store; never pass via CLI>
~~~

These values merely illustrate configuration variables; never enter real passwords into shell commands or logs. Ensure the `TaskRepository` schema has been migrated and both business tables exist beforehand.

Build the project with the standard Maven workflow, e.g.:

~~~bash
mvn -DskipTests package
~~~

This article does not execute the command itself; when running locally, replace the JAR filename below with your built artifact name. First run:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=1
~~~

Application log printed by the runner (illustrative):

~~~text
report tenant=acme date=2026-11-23 version=1 outcome=CREATED
~~~

Query the result in PostgreSQL:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       invoice_count,
       total_amount,
       generated_at
FROM daily_invoice_report
ORDER BY tenant_id, business_date, report_version;
~~~

Expect **one row**: `acme` / `2026-11-23` / v1 / `3` / `250.00`. `generated_at` is the timestamp when the database wrote the report; it is **not** `businessDate`.

### 7.1. Verifying Totals Directly from Source

~~~sql
SELECT COUNT(*) AS invoice_count,
       COALESCE(SUM(amount), 0) AS total_amount
FROM invoice
WHERE tenant_id = 'acme'
  AND status = 'PAID'
  AND paid_at >= TIMESTAMPTZ '2026-11-22T17:00:00+00:00'
  AND paid_at <  TIMESTAMPTZ '2026-11-23T17:00:00+00:00';
~~~

The result must be `3` and `250.00`. If different, check seed data, timezone, status filter, and the `< endExclusive` condition.

## 8. Re-running with Same Parameters: No Duplicate Record Created

Run the exact same command again:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=1
~~~

This time the runner is expected to print:

~~~text
report tenant=acme date=2026-11-23 version=1 outcome=ALREADY_EXISTS
~~~

Verify directly:

~~~sql
SELECT COUNT(*) AS reports,
       MIN(invoice_count) AS invoice_count,
       MIN(total_amount) AS total_amount
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
  AND report_version = 1;
~~~

**Expected result:** `reports=1`, `invoice_count=3`, `total_amount=250.00`. Running it 10 more times yields the exact same result.

**Two Java runs do not share a single `TaskExecution`.** When both processes finish and save metadata normally, `TaskRepository` records **two technical executions**, while the business table holds only **one logical report**. This is the key property of the lab.

### 8.1. Cross-checking TaskRepository

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-invoice-report-task'
ORDER BY START_TIME DESC;
~~~

Normally each run has a distinct `TASK_EXECUTION_ID`. `EXIT_CODE=0` only confirms the process completed technically; **it does not mean every run inserted a new row**. `ALREADY_EXISTS` is a valid no-op when report v1 already exists.

Note: `TaskRepository` and the business table **can** diverge if they live in different transactions or the Task is killed. Therefore, always rely on the **business key** when deciding whether to re-run business work, not solely on the Task exit code.

## 9. Testing Pre-Commit Failure and Safe Retry

This step demonstrates rollback. Use an **unused business key**, e.g., v2, once source data is finalized. The first run intentionally throws an exception **after `jdbc.update` but before the `@Transactional` method returns**:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=2 \
  --lab-fail-before-commit
~~~

Expect the Task to **fail** and the transaction to **roll back**. Verify:

~~~sql
SELECT COUNT(*) AS reports_v2
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
  AND report_version = 2;
~~~

The result must be `reports_v2=0`. If v2 still appears, check whether `@Transactional` actually ran through a Spring proxy, whether `NamedParameterJdbcTemplate` uses the right transaction manager/`DataSource`, and whether the error was caught and swallowed inside the service.

Re-run **without the failure flag**:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=2
~~~

Now expect `CREATED` and **one** v2 report. Version v1 remains intact; the two versions are **two distinct business keys**, not duplicate rows. In production, creating v2 must be a **controlled republish decision**, never a trick that auto-increments versions on retry.

### 9.1. What If the Process Dies After Commit Before Writing END?

~~~text
1. Database committed daily_invoice_report(v1).
2. Pod/JVM dies before TaskRepository writes final status.
3. Operator sees TaskExecution missing END_TIME.
4. Retry with the same business key v1.
5. INSERT ... ON CONFLICT DO NOTHING => ALREADY_EXISTS.
~~~

This is why **idempotency in the business database** must be independent of Task metadata. Conversely, if the Pod dies **before commit**, PostgreSQL rolls back the uncommitted transaction when the connection closes; the next run can create the report.

A Task killed by `SIGKILL` may skip `finally`, `TaskExecution` listeners, and context shutdown. Never treat `END_TIME IS NULL` as proof the report was not saved; check **the `daily_invoice_report` table and Pod status**.

## 10. Testing Two Concurrent Processes

In the lab environment, pick **a fresh business key** (e.g., `reportVersion=3`), then launch **two JVMs simultaneously**. In a Bash-capable shell:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=3 &

java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=3 &

wait
~~~

Both processes may read the invoices, yet both attempt to INSERT the same unique key. Expected result:

~~~text
One process:   outcome=CREATED
Other process: outcome=ALREADY_EXISTS
~~~

**Log order is non-deterministic**, and one process may block on the other's index/transaction lock. After both finish, query:

~~~sql
SELECT COUNT(*) AS reports_v3,
       SUM(total_amount) AS sum_of_report_rows
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
  AND report_version = 3;
~~~

Expect `reports_v3=1` and `sum_of_report_rows=250.00`. If the test produced two rows, likely the schema lacks the proper primary key, the processes wrote to **different databases/schemas**, or the key omits one of the three columns.

### 10.1. Why Not Rely Only on synchronized or CronJob Forbid?

- `synchronized` in Java only locks within **one JVM**, offering no protection across two Pods.
- `concurrencyPolicy: Forbid` only limits Jobs spawned by **the same Kubernetes CronJob**, not manual operator Jobs or another CronJob.
- `spring.cloud.task.single-instance-enabled` (when using compatible JDBC locking) guards by **Task name** across a shared lock store, not necessarily per tenant/date/version.
- **The DB unique constraint** remains the final safeguard for the report's business key.

In this example, two concurrent Pods **do not corrupt results**, though they may waste CPU/SQL aggregating the same input. For multi-hour heavy queries, design a **claim + lease + fencing** mechanism keyed by business key to avoid wasting resources across two Pods; never ship naive locks without TTL to production.

## 11. Business Date, Timezone, and Scheduling

Suppose "yesterday's" report runs at 02:00 Vietnam time:

~~~text
Schedule tick: 2026-11-24 02:00 Asia/Ho_Chi_Minh
businessDate:  2026-11-23
~~~

**Always pass an explicit date** from the orchestrator:

~~~text
--tenant-id=acme
--business-date=2026-11-23
--report-version=1
~~~

Never pass an abstract value like `--business-date=yesterday` in systems requiring accurate backfills/retries. If a Pod runs late on Nov 26 and computes "yesterday" from the current clock, it will wrongly process **Nov 25** instead of Nov 23.

Kubernetes CronJob `jobTemplate.args` is a **static template**; Kubernetes does not automatically substitute dates inside `--business-date=...` per run. For variable dates, use a **launcher** that reads the scheduled timestamp and creates a Job with immutable date arguments, or an external workflow/scheduler.

### 11.1. Example Job Manifest for a Specific Period

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: invoice-report-acme-20261123-v1
  namespace: batch-jobs
spec:
  backoffLimit: 2
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: report-task
          image: registry.example.com/batch/daily-invoice-report-task:1.0.0
          args:
            - "--tenant-id=acme"
            - "--business-date=2026-11-23"
            - "--report-version=1"
          envFrom:
            - secretRef:
                name: task-db-runtime
~~~

This is a **static Job example**, not a CronJob that computes dates automatically. Secret `task-db-runtime` must supply `TASK_DB_URL`, `TASK_DB_USER`, and `TASK_DB_PASSWORD`; namespace, image, ServiceAccount, resources, and policies must be tailored to your real environment.

Retries of the **same Kubernetes Job** reuse the same `args` in the Pod template; never use Pod UID or TaskExecution ID as a parameter that changes the report version. To re-run a completed Job, create a new Job name or use a proper launcher while **preserving the business key**; PostgreSQL protects idempotency.

### 11.2. Day Boundaries in Timezones with DST

This lesson uses Vietnam, which currently has no DST. Yet computing bounds with:

~~~java
Instant from = businessDate.atStartOfDay(zone).toInstant();
Instant to = businessDate.plusDays(1).atStartOfDay(zone).toInstant();
~~~

also works properly for timezones whose local calendar days can be 23 or 25 hours long. Avoid `from.plus(Duration.ofHours(24))` when business semantics are **local calendar days**. Querying with `>= from` and `< to` also prevents double-counting at midnight between adjacent periods.

## 12. Changing Inputs and Republishing Policy

Two distinct request patterns exist:

| Request | Desired Behavior |
| --- | --- |
| **Retry of an already published period** | Keep version, `ON CONFLICT DO NOTHING`, result `ALREADY_EXISTS` |
| **Pre-commit failure** | Keep version, transaction rolls back, retry can create the report |
| **Late-arriving source invoices** | Requires a republish workflow, typically bumping `reportVersion` under control |
| **Correcting published figures** | Create a new version or audited amendment; never silently add/overwrite |
| **Snapshot-consistent results required** | Pin input revision/high-water mark and reuse the same snapshot across retries |
| **Two report versions active in parallel** | Define policy for accepting/rejecting old versions and determining "latest" consistently |

### 12.1. Practicing Late-Arriving Data

After v1 exists, insert another paid `acme` invoice for Nov 23:

~~~sql
INSERT INTO invoice (tenant_id, paid_at, status, amount)
VALUES ('acme', '2026-11-23T10:00:00+00:00', 'PAID', 200.00);
~~~

In this **lab simulating post-cutoff source changes**, re-run **v1**:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=1
~~~

The outcome remains `ALREADY_EXISTS`, and v1 stays at **3 invoices, 250.00**. If **approved** to publish v4 over the new dataset (assuming earlier versions v1/v2/v3 exist), run:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=4
~~~

Expect v4 to have **4 invoices, 450.00**, while v1 stays untouched. This is **intentional versioning**, not "auto-increment version on retry". In production, also record the correction reason, requester, input revision, and active-version selection rules.

**Pattern limitation:** v4 reads data as of execution time. If invoices keep changing continuously during generation, you need a snapshot or READY gate confirming source stability; incrementing version alone does not create a snapshot.

## 13. What If the Report Must Also Send Emails or External Files?

Writing a row to PostgreSQL inside a transaction **does not guarantee** an email is sent only once. Dangerous scenario:

~~~text
COMMIT report v1
   → call email API
   → process dies before receiving response
   → retry sees report already exists and skips
   → unknown whether email was sent
~~~

Or sending the email **before commit**: email succeeds, transaction rolls back, and the retry sends it again. No simple call ordering solves both issues at once.

The standard solution is a **transactional outbox**:

1. Within the **same transaction** creating `daily_invoice_report`, insert an outbox record with a unique event key, e.g., `report:acme:2026-11-23:v1`.
2. A separate publisher reads the outbox after commit and dispatches messages/emails/uploads with retries.
3. The consumer/target must support an **idempotency key**, or the publisher must track delivery state and reconcile.
4. If the Task is killed mid-flight, the outbox record persists so the publisher can recover.

~~~mermaid
flowchart LR
    T["Task @Transactional"] --> R[("daily_invoice_report")]
    T --> O[("report_outbox")]
    O --> P["Independent publisher + retry"]
    P --> X["Email / object storage / API"]
    X --> K["Idempotency key / deduplication"]
~~~

A minimal outbox table could look like:

~~~sql
CREATE TABLE report_outbox (
    event_key   varchar(200) PRIMARY KEY,
    tenant_id   varchar(64) NOT NULL,
    business_date date NOT NULL,
    report_version integer NOT NULL,
    status      varchar(20) NOT NULL DEFAULT 'PENDING',
    created_at  timestamptz NOT NULL DEFAULT now()
);
~~~

This table is an **extension path**; the current `DailyReportService` code **does not write to an outbox yet**. To implement it, add `INSERT INTO report_outbox...ON CONFLICT DO NOTHING` inside the **same `@Transactional` method** only when creating a new report, then build the publisher/retry/dead-letter flow and target-side idempotency. Never mark `SENT` as soon as a request is fired without proper confirmation.

## 14. Required Test Matrix

| ID | How to Test | Expected Result |
| --- | --- | --- |
| **T1** | Run v1 for the first time | `CREATED`; one row `3 / 250.00` |
| **T2** | Re-run v1 a second time | `ALREADY_EXISTS`; result unchanged |
| **T3** | Run v1 10 times | Still only one row |
| **T4** | Two JVMs run v3 concurrently | One `CREATED`, one `ALREADY_EXISTS`; one row |
| **T5** | v2 with `--lab-fail-before-commit` | Task fails; no v2 row exists |
| **T6** | Remove error flag, re-run v2 | `CREATED`; one v2 row |
| **T7** | Different tenant, same date/version | Created separately; does not affect `acme` |
| **T8** | Next day, same tenant/version | Created separately; no time-window overlap |
| **T9** | Seeds near 17:00Z and `CANCELLED` | Includes only the 3 matching `acme` invoices |
| **T10** | Late data arrives after v1 | v1 unchanged; new version reflects new source |
| **T11** | Process killed before/after commit | Reconcile DB to decide retry; do not trust `END_TIME` alone |
| **T12** | Missing `--business-date` or invalid version | Runner fails fast; writes no report |
| **T13** | DB offline | Task errors; never treated as completed report |
| **T14** | Multiple concurrent CronJob Pods | DB still blocks duplicates by business key |

**Evidence to capture while practicing:** `CREATED/ALREADY_EXISTS` logs, two distinct execution IDs, SQL query outputs per version, concurrent test commands, and rollback verification. For intentional failures, verify **no partial data exists** rather than only checking that Java printed an exception.

## 15. Common Pitfalls and Fixes

| Pitfall | Why Is It Wrong? | Fix |
| --- | --- | --- |
| Using `TaskExecution ID` as business key | Retries get new `TaskExecution ID`s | Use tenant/date/version |
| Only `if (!exists) insert()` | Race condition across Pods | Unique constraint + atomic `INSERT` |
| `total = total + newTotal` on retry | Easily double-counts | Absolute aggregation and insert-once/versioning |
| Not pinning `businessDate` explicitly | Retries/late runs may shift date | Fix the date at the launcher |
| Comparing `DATE(paid_at)` in DB timezone | Can shift days and hinder index use | Convert bounds in business zone and query `[from,to)` |
| Using `<= end` | Midnight records counted in two days | Use `< endExclusive` |
| Omitting `@Transactional` across multiple related SQLs | Partial commit if later step fails | Transaction spanning all atomic changes |
| Calling transactional method via `this.generate()` | Spring proxy may bypass advice | Call through Spring-managed service bean |
| Unique key exists across separate DBs | Two processes do not share constraint | Ensure one authoritative DB/schema |
| Swallowing exceptions and returning exit 0 | Scheduler thinks job succeeded | Propagate errors and verify exit code |
| Late invoice arrives, only retry same version | `DO NOTHING` keeps old data | Freeze input, issue new controlled version |
| Sending email inside DB transaction | DB cannot roll back sent email | Transactional outbox + idempotent consumer |
| Assuming `END_TIME=NULL` means no report saved | Pod may have died after commit | Query the report table |
| Passing password via command-line | `TaskRepository` may save arguments | Kubernetes Secret/env/mounted file |
| Holding hour-long transactions for huge reports | Long locks and connections | Snapshots, staged aggregation, claim/lease/fencing |

### 15.1. When Data Volume Exceeds a Single Statement

The `INSERT ... SELECT` pattern fits aggregations that complete within a **relatively short transaction**. When processing hundreds of millions of invoices, multiple sources, or multi-file reports, consider **Spring Batch** with chunks/checkpoints, or staging tables keyed by `runId` and business key. You must still clearly define:

- Do all processing partitions read the same **source snapshot**?
- Are intermediate results retryable/idempotent per partition?
- Who is authorized to **publish** a report once all partitions finish?
- When a worker dies, who takes over and how do you block the stale worker from writing (**fencing**)?
- Does a retry change `reportVersion`? Usually **no**.

Do not blindly convert every daily report to remote partitioning or enable `single-instance-enabled` as a substitute for business-table unique constraints.

## 16. Post-Run Operational Reconciliation

A solid monitoring workflow combines **scheduler, `TaskRepository`, and business results**:

~~~text
Kubernetes Job / Scheduled launch
   │   per-period orchestration, Pod retries
   ▼
TaskExecution
   │   ID, start/end, exit code
   ▼
DailyInvoiceReport
       business key, count, sum, generatedAt
~~~

Try querying:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       invoice_count,
       total_amount,
       generated_at
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
ORDER BY report_version;
~~~

In the lab after steps T1–T6, before adding late data, versions `1`, `2`, and `3` will exist, each with **3 invoices, 250.00**. If you then create v4 from the updated source, v4 has **4 invoices, 450.00**. A failed and rolled-back Task **creates no extra version** beyond the successfully committed ones.

### 16.1. Alerting and Investigation

- **No `TaskExecution` for the day:** check CronJob/launcher, image pull, DB startup; the Task may never have started.
- **Task `FAILED`:** check safe logs, `TaskRepository`, and PostgreSQL errors/locks/transactions.
- **Task exits 0 with no new row:** if `ALREADY_EXISTS`, this may be a safe retry; verify the business key instead of raising false alarms.
- **Task exits 0 with wrong new report:** reconcile source snapshot, timezone, `PAID` status, and late data.
- **Two concurrent Tasks:** inspect `ON CONFLICT` and report row count; do not assume an error merely because two `TaskExecution` rows exist.
- **`TaskExecution` lacks end time while report exists:** process likely died after commit; idempotent retry on the same key is safe.

Include `taskExecutionId`, `Kubernetes Job UID`, and `businessKey` in structured logs or lookup metadata, without putting high-cardinality IDs into metric labels. Never log DB passwords or pass tokens as arguments because Task history can persist them.

## 17. Summary

1. **Idempotency is a property of business behavior**, not how many times Kubernetes or Spring Cloud Task launches a process.
2. For daily reports, identify work by **`(tenant_id, business_date, report_version)`**, enforced inside **the same PostgreSQL DB** with a unique constraint.
3. **`INSERT ... SELECT ... ON CONFLICT DO NOTHING`** avoids check-then-insert races and double-counting; `@Transactional` enables rollback on pre-commit service failures.
4. Re-running with the same key after success must return **`ALREADY_EXISTS`** without inserting a new row. Seeing a new `TaskExecution` is normal.
5. Compute day ranges using the business timezone and **`[startInclusive,endExclusive)`** to avoid midnight boundary shifts or double-counting.
6. **Source data must be finalized or snapshotted** prior to publication. When data changes after publication, issue a new version by policy rather than silently overwriting v1.
7. Retries after pre-commit failure can create the report; retries after commit should no-op. **Never use `END_TIME` or exit code as sole proof** of whether a report was saved.
8. Across multiple Pods, `synchronized` or `Forbid` cannot replace a primary key on the business table.
9. When side effects occur outside PostgreSQL, use **an outbox, idempotency keys, and reconciliation**; a DB transaction does not create global exactly-once delivery.
10. **Measure and verify in practice** using SQL, rollback scenarios, concurrent runs, late data, and `TaskRepository` state before scheduling in production.

### References

- [Spring Cloud Task — Features and Task Lifecycle](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — TaskRepository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Boot — SQL Databases and JdbcTemplate](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [PostgreSQL — INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL — Date/Time Types and Time Zones](https://www.postgresql.org/docs/current/datatype-datetime.html)
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
