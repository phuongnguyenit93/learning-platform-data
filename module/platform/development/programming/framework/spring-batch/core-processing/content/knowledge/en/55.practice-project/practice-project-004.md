# Designing Identifying JobParameters in Spring Batch

## 1. Practice Project Context

In Spring Batch Core Processing, **JobParameters** are not just values passed into a Job. Parameters marked as **identifying** determine whether Spring Batch treats a request as an existing business unit of work that needs a restart, or as a completely new unit of work.

A daily order-import application may receive the following requests:

- Schedulers on two pods trigger the Job simultaneously at 02:00.
- An API client resends a request after timing out.
- The initial run fails mid-chunk and requires a restart.
- A partner sends a corrected version of the file on the same day.
- An operator is approved to re-run an already `COMPLETED` period.

If every trigger generates a random **`run.id`**, requests for the same business work may create multiple `JobInstance`s and cause duplicate processing. If only **`businessDate`** is used as the identity, data from two tenants or two snapshots on the same day can collide.

This practice project designs an **`importOrdersJob`** along four dimensions:

~~~text
tenantId         = tenant-a
businessDate     = 2026-11-15
sourceSnapshotId = snap-a-20261115-v1
generation       = 1
~~~

End-of-lesson objectives:

1. Identify **a single unique business batch** using meaningful identifying `JobParameters`.
2. Distinguish **`JobInstance`** from **`JobExecution`** and HTTP requests.
3. Restart a failed run using the **same identifying parameters** without creating a new instance.
4. Create a new instance **intentionally** when the snapshot or generation changes.
5. Ensure schedulers, APIs, and operators follow the exact same parameter-construction rules.
6. Keep inputs immutable and outputs idempotent so results remain accurate after retries/restarts.
7. Test duplicates, completions, failures, re-runs, and concurrent launches.

The examples use **Java 17, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC, and PostgreSQL**. The illustrative source snippets plug into an application that already has an appropriate `JobRepository`, `DataSource`, and transaction manager.

## 2. Job, JobInstance, and JobExecution

**Job** is the workflow definition, for example **`importOrdersJob`** with Steps to read a file, process items, write to the database, and reconcile.

**JobInstance** is a unit of work identified by the **Job name and the set of identifying `JobParameters`**. In this example, it is the import batch for `tenant-a`, date `2026-11-15`, snapshot `v1`, generation `1`.

**JobExecution** is an **execution attempt** of a `JobInstance`. If the first execution is `FAILED` and then restarted, the framework creates a new `JobExecution` for the **same `JobInstance`**, using appropriate metadata and checkpoints.

~~~text
Job definition
  importOrdersJob
         |
         v
JobInstance #31
  tenant-a / 2026-11-15 / snap-v1 / generation=1
         |
    +----+------------------+
    |                       |
    v                       v
JobExecution #101       JobExecution #105
    FAILED                  COMPLETED
    |                       |
StepExecution #501      StepExecution #508
  committed some chunks     resumes from checkpoint
~~~

**`JobExecution` ID is not an identifying parameter to generate before execution**; the ID is assigned by `JobRepository` when a new execution is created. Never include the execution ID in a business key.

When launching concurrently or repeatedly with the same identity, typical behavior is:

| Current State | Behavior on Same-Identity Launch |
| --- | --- |
| No `JobInstance` yet | Creates a new `JobInstance` and `JobExecution` |
| Currently running | May be rejected with **`JobExecutionAlreadyRunningException`** |
| Already `COMPLETED` | May be rejected with **`JobInstanceAlreadyCompleteException`** |
| `FAILED` or `STOPPED` | May create a new `JobExecution` to restart if the Job allows it |
| Restart not allowed | May receive **`JobRestartException`** |
| Invalid parameters | **`JobParametersInvalidException`** if caught by the validator |

Exact behavior depends on the actual state and Job configuration. Never edit `BATCH_JOB_EXECUTION` via SQL just to "force a run."

## 3. Identifying and Non-Identifying Parameters

A **`JobParameter`** has a data type, value, and **identifying** flag.

- **Identifying = true:** participates in `JobInstance` identity.
- **Identifying = false:** passed into the execution but does not participate in identity.

Example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("tenantId", "tenant-a", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSnapshotId", "snap-a-20261115-v1", true)
        .addLong("generation", 1L, true)
        .addString("requestedBy", "scheduler", false)
        .addString("traceId", "req-4281", false)
        .toJobParameters();
~~~

The first four parameters identify the batch unit of work. **`requestedBy`** and **`traceId`** support auditing and tracing. If an operator submits the same identity with a different `traceId`, Spring Batch still recognizes the **same `JobInstance`**.

| Parameter | Identifying | Explanation |
| --- | --- | --- |
| `tenantId` | Yes | Same period for a different tenant is a different job |
| `businessDate` | Yes | Each business date is a processing period |
| `sourceSnapshotId` | Yes | A new source snapshot represents new data |
| `generation` | Yes | An approved re-processing or re-publication run |
| `requestedBy` | No | Who launched the job does not change the data to process |
| `traceId` | No | Each HTTP request may have a different ID |
| `retryCount` | No | Attempt count does not create new business work |
| `hostname/podId` | No | Multiple pods may still process the same batch |
| `processingRuleVersion` | Must be fixed by contract | If it changes results, it must be in the identity or an immutable snapshot/generation |

**Setting `identifying=false` does not encrypt or hide values.** Non-identifying parameters can still be persisted in metadata. Never store passwords, API keys, or real tokens here.

### Warning When Restarting

The framework can accept a new set of non-identifying values while still resolving the same `JobInstance`. That is only safe when those values **do not affect business outcomes**.

If **`taxRate`**, **`currency`**, **`inputFile`**, or **`ruleVersion`** is marked non-identifying and changes between two executions, the Job may process the first chunk under old rules and the next chunk under new rules. Therefore, any factor affecting input/output must be **pinned to the business run key**.

## 4. Defining the Business Run Key Before Writing Code

The project's unit of work is:

~~~text
ImportRunKey = (
    tenantId,
    businessDate,
    sourceSnapshotId,
    generation
)
~~~

This is a business contract designed by the application. Spring Batch also includes the **Job name** in its `JobInstance` identity.

Why is each dimension needed?

**`tenantId`:** ensures two independent customers are not merged into one batch. You must verify the caller is authorized to access that tenant.

**`businessDate`:** defines the period according to the business calendar, not necessarily the system clock date. When backfilling last month, you still use the original date of the data.

**`sourceSnapshotId`:** points to a finalized source dataset. If a partner sends a corrected version later, a new snapshot ID/version must be issued.

**`generation`:** enables intentional re-runs after an instance has completed, such as when fixing an algorithm and needing to produce a replacement output. It is not an automatic retry counter.

Several decisions must be agreed upon before implementation:

- How many snapshots can a tenant/day have?
- Are snapshots guaranteed immutable once finalized?
- If a file with the same name is overwritten, is there an object version or digest to distinguish it?
- When running generation 2, is the old output kept, replaced, or invalidated?
- Who has permission to request a new generation?
- Must a restart step continue with the exact old snapshot and rule version?
- If input data is not yet finalized, should the Job reject or defer execution?

**Good `JobParameters` cannot save a mutable input**: if an old `snapshotId` points to modified data, the reader's checkpoint may become invalid even though the identity hasn't changed.

## 5. Canonicalizing Types and Values So All Entry Points Recognize One Batch

Two representations that look similar can produce different identities:

~~~text
tenant-a    and TENANT-A
2026-11-15  and 15/11/2026
Long 1      and String "1"
snap-v1     and " snap-v1 "
~~~

A canonical representation standard must be designed:

- Use **`LocalDate`** for `businessDate` in the domain layer, converting to an **ISO `yyyy-MM-dd`** string in `JobParameters`.
- Use **`Long`** for `generation`; never mix `Long` in one place and `String` in another.
- Apply a consistent tenant ID rule: case-sensitive or case-insensitive depending on business rules.
- Trim meaningless whitespace and reject invalid characters in `snapshotId`.
- Keep parameter names stable across application versions.
- For hourly/minutely windows, express window start/end using a **defined timezone and interval** rather than an arbitrary current timestamp.

Specifically avoid building keys like:

~~~java
JobParameters wrong = new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis(), true)
        .toJobParameters();
~~~

If two pods run the cron simultaneously, different current timestamps will create two `JobInstance`s. **`run.id`** is only appropriate when the contract genuinely treats every run as new work; it is not the default solution for daily batches requiring idempotency.

## 6. Building the `ImportRunKey` Data Type

A value object helps schedulers, controllers, and tests share the same rules:

~~~java
import java.time.LocalDate;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public record ImportRunKey(
        String tenantId,
        LocalDate businessDate,
        String sourceSnapshotId,
        long generation) {

    private static final Pattern TENANT =
            Pattern.compile("[a-z0-9][a-z0-9_-]{0,31}");

    private static final Pattern SNAPSHOT =
            Pattern.compile("[A-Za-z0-9_-]{1,80}");

    public ImportRunKey {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(businessDate, "businessDate");
        Objects.requireNonNull(sourceSnapshotId, "sourceSnapshotId");

        tenantId = tenantId.trim().toLowerCase(Locale.ROOT);
        sourceSnapshotId = sourceSnapshotId.trim();

        if (!TENANT.matcher(tenantId).matches()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        if (!SNAPSHOT.matcher(sourceSnapshotId).matches()) {
            throw new IllegalArgumentException("Invalid snapshot ID");
        }
        if (generation < 1L) {
            throw new IllegalArgumentException(
                    "generation must be positive");
        }
    }

    public JobParameters toParameters(
            String requestedBy, String traceId) {

        return new JobParametersBuilder()
                .addString("tenantId", tenantId, true)
                .addString("businessDate", businessDate.toString(), true)
                .addString("sourceSnapshotId", sourceSnapshotId, true)
                .addLong("generation", generation, true)
                .addString("requestedBy", requestedBy, false)
                .addString("traceId", traceId, false)
                .toJobParameters();
    }
}
~~~

With a record compact constructor, reassigning local parameters in the constructor normalizes the stored components. The example assumes **`requestedBy`** and **`traceId`** are non-null and validated at the ingestion boundary; a real application must enforce length limits, handle optional values, and avoid putting sensitive data into metadata.

Only **lowercase `tenantId`** if the business confirms tenants are case-insensitive. If **`ABC`** and **`abc`** are distinct tenants, canonicalization must preserve that distinction.

## 7. Source Snapshot: The Job's Key Must Point to Immutable Data

Snapshots can be managed via a table:

~~~sql
CREATE TABLE source_snapshot (
    tenant_id        VARCHAR(32) NOT NULL,
    snapshot_id      VARCHAR(80) NOT NULL,
    business_date    DATE NOT NULL,
    content_digest   VARCHAR(128) NOT NULL,
    status           VARCHAR(20) NOT NULL,
    finalized_at     TIMESTAMP,
    PRIMARY KEY (tenant_id, snapshot_id)
);

CREATE TABLE source_order (
    tenant_id        VARCHAR(32) NOT NULL,
    snapshot_id      VARCHAR(80) NOT NULL,
    order_id         VARCHAR(64) NOT NULL,
    amount           DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (tenant_id, snapshot_id, order_id)
);
~~~

Example rules:

1. The file is uploaded to an unfinalized area.
2. Validate schema, checksum, and row count.
3. Generate a snapshot ID and a manifest containing the content digest.
4. Mark the snapshot **`FINALIZED`**.
5. Never update source rows of a `FINALIZED` snapshot.
6. Only launch the Job if the snapshot belongs to the right tenant/`businessDate` and is `FINALIZED`.

Illustrative data:

~~~text
Snapshot: snap-a-20261115-v1
Tenant  : tenant-a
Date    : 2026-11-15

order_id    amount
--------    ------
O-101       100.00
O-102       250.00
O-103        75.00
O-104       125.00

Row count: 4; total amount: 550.00
~~~

If a partner corrects the amount of O-102, issue **`snap-a-20261115-v2`** or a new version/manifest instead of overwriting `v1`'s data. That way restarts and audits can trace back to the exact original input.

## 8. Output Must Also Reflect the Identifying Scope

Illustrative target table:

~~~sql
CREATE TABLE imported_order (
    tenant_id          VARCHAR(32) NOT NULL,
    business_date      DATE NOT NULL,
    source_snapshot_id VARCHAR(80) NOT NULL,
    generation         BIGINT NOT NULL,
    order_id           VARCHAR(64) NOT NULL,
    amount             DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (
        tenant_id, business_date,
        source_snapshot_id, generation, order_id
    )
);
~~~

This key scope ensures:

- Retries/restarts of the same `JobInstance` write to the right data region.
- Snapshot `v2` does not overwrite snapshot `v1`'s output region.
- A new generation has its own result region for reconciliation before publishing.
- Tenants are isolated from one another.

However, **never query both generation 1 and generation 2 together to compute final revenue** if the business wants only one published version. You need a publication pointer or policy to select the approved valid result.

Writer idempotency must be designed independently. If the writer sends emails, calls APIs, or executes off-database transactions, a primary key in `imported_order` will not prevent all side effects from repeating.

## 9. Configuring the Reader to Read by `JobParameters`

Models:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record SourceOrder(
        String orderId,
        BigDecimal amount) {}

public record ImportedOrder(
        String tenantId,
        LocalDate businessDate,
        String sourceSnapshotId,
        Long generation,
        String orderId,
        BigDecimal amount) {}
~~~

Spring Batch 5.x reader:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<SourceOrder> sourceOrderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['sourceSnapshotId']}")
                String snapshotId) {

    return new JdbcCursorItemReaderBuilder<SourceOrder>()
            .name("sourceOrderReader")
            .dataSource(dataSource)
            .sql("""
                SELECT order_id, amount
                FROM source_order
                WHERE tenant_id = ? AND snapshot_id = ?
                ORDER BY order_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, tenantId);
                ps.setString(2, snapshotId);
            })
            .rowMapper((rs, rowNum) -> new SourceOrder(
                    rs.getString("order_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

**`@StepScope`** enables late binding of `JobParameters` at Step execution time. The reader filters by tenant/snapshot; if the SQL query does not filter by identity, a well-designed `JobParameters` structure still cannot prevent reading the wrong data.

**`ORDER BY order_id`** creates a stable ordering within the snapshot, while the primary key guarantees `order_id` uniqueness within the tenant/snapshot scope. For restarts, verify `ItemStream` reader state and source data immutability.

## 10. Processor and Writer Bound to the Same Business Key

The processor produces output with all four dimensions:

~~~java
@Bean
@StepScope
ItemProcessor<SourceOrder, ImportedOrder> orderProcessor(
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['sourceSnapshotId']}")
                String snapshotId,
        @Value("#{jobParameters['generation']}") Long generation) {

    LocalDate date = LocalDate.parse(businessDate);

    return source -> new ImportedOrder(
            tenantId,
            date,
            snapshotId,
            generation,
            source.orderId(),
            source.amount());
}
~~~

The processor must not use `traceId`/`requestedBy` to alter results. If an algorithm version changes mapping or amounts, pin it to an identifying parameter or an immutable manifest/generation. Especially when restarting after a new deployment, never silently change rules for the remaining unprocessed input.

The PostgreSQL writer uses upsert to avoid creating two rows for the same business key:

~~~java
@Bean
JdbcBatchItemWriter<ImportedOrder> importedOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ImportedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order (
                    tenant_id, business_date, source_snapshot_id,
                    generation, order_id, amount
                ) VALUES (
                    :tenantId, :businessDate, :sourceSnapshotId,
                    :generation, :orderId, :amount
                )
                ON CONFLICT (
                    tenant_id, business_date, source_snapshot_id,
                    generation, order_id
                )
                DO UPDATE SET amount = EXCLUDED.amount
                """)
            .beanMapped()
            .build();
}
~~~

Upsert here works when data and transformations are deterministic. A financial system might choose to **reject an update if the amount differs** instead of silently overwriting; that is a business rule. Upsert also does not replace reconciliation or protect off-transaction side effects.

Declaring the Step and Job:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<SourceOrder> reader,
        ItemProcessor<SourceOrder, ImportedOrder> processor,
        JdbcBatchItemWriter<ImportedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<SourceOrder, ImportedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(importParametersValidator)
            .start(importOrdersStep)
            .build();
}
~~~

This configuration assumes a `DataSource` and transaction manager compatible with the reader/writer and `JobRepository`. If metadata and business output use two different databases, design transaction boundaries, checkpoints, and idempotency strictly; two local transaction managers do not automatically form an atomic distributed transaction.

## 11. JobParametersValidator: Checking the Contract at the Job Boundary

Controllers may validate requests, but a Job can also be triggered via schedulers, CLIs, or admin tools. Attaching a **`JobParametersValidator`** to the Job itself ensures every entry path obeys the same contract.

~~~java
@Bean
JobParametersValidator importParametersValidator() {
    return params -> {
        String tenant = params.getString("tenantId");
        String date = params.getString("businessDate");
        String snapshot = params.getString("sourceSnapshotId");
        Long generation = params.getLong("generation");

        if (tenant == null || tenant.isBlank()
                || date == null || date.isBlank()
                || snapshot == null || snapshot.isBlank()
                || generation == null || generation < 1L) {
            throw new JobParametersInvalidException(
                    "Missing or invalid import identity");
        }

        try {
            LocalDate parsed = LocalDate.parse(date);
            if (!parsed.toString().equals(date)) {
                throw new IllegalArgumentException("Date not canonical");
            }
        } catch (RuntimeException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use yyyy-MM-dd");
        }

        for (String key : List.of(
                "tenantId", "businessDate",
                "sourceSnapshotId", "generation")) {

            var value = params.getParameters().get(key);

            if (value == null || !value.isIdentifying()) {
                throw new JobParametersInvalidException(
                        key + " must be identifying");
            }
        }

        for (String key : List.of("requestedBy", "traceId")) {
            var value = params.getParameters().get(key);
            if (value != null && value.isIdentifying()) {
                throw new JobParametersInvalidException(
                        key + " must not be identifying");
            }
        }
    };
}
~~~

You must import **`java.time.LocalDate`**, **`java.util.List`**, **`JobParametersValidator`**, and **`JobParametersInvalidException`** along with the corresponding Spring Batch classes.

This validator focuses on required/identifying/date checks. Production systems should also check patterns, data types, length limits, extra parameters, and snapshot access rights. **`JobParametersValidator` does not replace authorization or checking whether a snapshot is `FINALIZED`**.

## 12. A Shared Launch Service for All Entry Points

Avoid letting controllers, schedulers, and CLIs construct `JobParameters` differently. Use one orchestrating service:

~~~java
@Service
public class OrderImportLauncher {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;
    private final SourceSnapshotService snapshotService;

    public OrderImportLauncher(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob,
            SourceSnapshotService snapshotService) {

        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
        this.snapshotService = snapshotService;
    }

    public JobExecution launch(
            ImportRunKey key,
            String requestedBy,
            String traceId) throws Exception {

        snapshotService.requireFinalized(
                key.tenantId(),
                key.businessDate(),
                key.sourceSnapshotId());

        JobParameters params =
                key.toParameters(requestedBy, traceId);

        return jobLauncher.run(importOrdersJob, params);
    }
}
~~~

**`SourceSnapshotService`** is a domain service the project must implement: verifying the snapshot belongs to the tenant/date, is finalized, and its content has not changed. A controller must also verify user permissions for the tenant, generation, and reprocessing rights. Syntactically valid values **do not mean the caller is authorized to process them**.

### Interpreting Launch Results

| Result | Caller Action |
| --- | --- |
| Returns `JobExecution COMPLETED` | Return completion details and execution ID |
| Returns `JobExecution FAILED` | Log error, provide restart procedure |
| `JobInstanceAlreadyCompleteException` | Return already-processed result, do not auto-generate `run.id` |
| `JobExecutionAlreadyRunningException` | Return running status |
| `JobRestartException` | Investigate why restart is disallowed by policy |
| `JobParametersInvalidException` | Report invalid-parameter error |
| `JobRepository` unreachable | Do not assume whether the Job ran or not; inspect metadata before retrying |

The example assumes a **synchronous** launcher. With **`TaskExecutorJobLauncher`** configured with an asynchronous `TaskExecutor`, calling `run` may return a `JobExecution` in `STARTING`/`STARTED`. Query `JobExplorer` or wait for completion when the final status is needed.

Do not catch all exceptions and bump generation/UUID just to "force a run at all costs." That turns a metadata problem into duplicate processing.

## 13. Multi-Instance Schedulers Must Use the Same Identity

For a daily data import scheduled at 02:00 in the business timezone:

~~~java
@Component
public class DailyOrderScheduler {

    private final OrderImportLauncher imports;
    private final SourceSnapshotService snapshots;
    private final Clock clock;

    public DailyOrderScheduler(
            OrderImportLauncher imports,
            SourceSnapshotService snapshots,
            Clock clock) {

        this.imports = imports;
        this.snapshots = snapshots;
        this.clock = clock;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
    public void importPreviousDay() throws Exception {
        LocalDate businessDate =
                LocalDate.now(clock).minusDays(1);

        String tenantId = "tenant-a";
        String snapshotId = snapshots.finalizedSnapshotId(
                tenantId, businessDate);

        ImportRunKey key = new ImportRunKey(
                tenantId, businessDate, snapshotId, 1L);

        imports.launch(key, "scheduler", "daily-schedule");
    }
}
~~~

Clock bean:

~~~java
@Bean
Clock businessClock() {
    return Clock.system(
            ZoneId.of("Asia/Ho_Chi_Minh"));
}
~~~

The example requires enabling **`@EnableScheduling`** and importing Spring Scheduling classes, **`Clock`**, **`ZoneId`**, and **`LocalDate`**. Production may need to process multiple tenants or receive the processing period from an orchestration layer rather than hardcoding one tenant.

If two pods compute:

~~~text
Pod A -> tenant-a, 2026-11-15, snap-v1, generation=1
Pod B -> tenant-a, 2026-11-15, snap-v1, generation=1
                        |
                        v
                  Same JobInstance
~~~

Both must access the **same JDBC `JobRepository`** to keep identity consistent. If each pod uses an in-memory H2 repository or a separate schema, they do not actually coordinate on the same `JobInstance`.

A scheduler lock can prevent pods from triggering simultaneously, but **does not replace identifying `JobParameters`**: a REST API or operator can still launch the Job outside the scheduler lock.

Mind day boundaries and clocks: use an explicit timezone; if the snapshot is not yet `FINALIZED`, do not generate a random ID to force a run. Define defer/retry rules per business period.

## 14. Restarts Must Preserve Identifying Parameters

Suppose a Job imports seven orders, chunk size 3, with a controlled error at the fifth item:

~~~text
Input: O-101 ... O-107

Execution #201:
  Chunk 1: O-101, O-102, O-103 -> commit
  Chunk 2: O-104, O-105, O-106 -> error, rollback
  Job FAILED

Execution #202:
  Restart same JobInstance
  Re-reads from supported checkpoint
  Completes uncommitted portions
  Job COMPLETED
~~~

Launch snippet:

~~~java
ImportRunKey key = new ImportRunKey(
        "tenant-a",
        LocalDate.of(2026, 11, 15),
        "snap-a-20261115-v1",
        1L);

JobParameters params =
        key.toParameters("integration-test", "restart-case");

JobExecution first = jobLauncher.run(importOrdersJob, params);
// Assume the first run fails and returns FAILED.

// Remove the failure condition; DO NOT change key/params.
JobExecution restarted = jobLauncher.run(importOrdersJob, params);
~~~

Key conditions:

1. The input snapshot preserves the exact bytes, content, and reader order.
2. `JobRepository`/`ExecutionContext` are not deleted or manually edited.
3. Reader/writer `ItemStream`s are properly configured for checkpoint/restart.
4. The writer and side effects have proper transactions/idempotency.
5. Parameters that alter business output must not change between restarts.
6. If a Step is already `COMPLETED`, a default restart may skip that Step; when reprocessing is required, use a dedicated workflow.

Using a new identifying timestamp on the second execution **is not a restart**. It creates a different `JobInstance`, may re-read from the start, and causes duplicates.

## 15. HTTP Retries Differ from Job Restarts

A client calls the API to launch and times out. Not knowing whether the server created a `JobExecution`, it retries the request.

Two HTTP requests do not necessarily represent two business units of work. Proper design:

~~~text
HTTP request A: requestId=req-100
HTTP request B: requestId=req-101 (retry)

Business identity for both:
  tenant-a / 2026-11-15 / snap-v1 / gen=1
~~~

You can use an **HTTP `Idempotency-Key`** at the API layer, but the **business run key** must still remain stable even if `requestId` changes.

Suggested flow:

1. Resolve and canonicalize `ImportRunKey`.
2. Check authorization and `FINALIZED` snapshot.
3. Look up current status if needed for display.
4. Invoke `JobLauncher` with the same identifying parameters.
5. Handle `COMPLETED`, `RUNNING`, or `FAILED` according to the contract.
6. Do not create a new generation when only retrying HTTP.
7. If a race occurs between lookup and launch, rely on `JobRepository` constraints/transactions to resolve the concurrent outcome.

**Look-up-then-launch is not an atomic operation.** Two threads can both observe "not yet present"; a properly configured JDBC `JobRepository` is the underlying control layer, not a check-then-act in the controller.

## 16. Reprocessing After COMPLETED via Intentional Generation

A generation 1 `JobInstance` has completed, yet the business requests recalculation after an algorithm fix. Never append the current timestamp just to bypass **`JobInstanceAlreadyCompleteException`**.

~~~text
Generation 1:
  tenant-a / 2026-11-15 / snap-v1 / generation=1
  JobInstance #31
  COMPLETED

Generation 2 (approved):
  tenant-a / 2026-11-15 / snap-v1 / generation=2
  JobInstance #47
  Reprocessed result
~~~

If input changes, use a new snapshot:

~~~text
Before: snap-v1, generation=1
After:  snap-v2, generation=1
~~~

Different meanings:

- **`snapshot v2`**: a different source dataset.
- **`generation 2`**: intentionally producing a new processed/published output version over a finalized source and ruleset.

Audit **who requested it, the reason, timestamp, algorithm version, previous generation, reconciliation result, and publish approval**. Do not let users arbitrarily increment generation to create unbounded `JobInstance`s or duplicate transactions.

If the writer has off-database effects such as sending emails or transferring funds, a new generation can repeat side effects. You need explicit reprocessing rules, idempotency keys, or compensation; never treat generation alone as sufficient protection.

## 17. Decision Table for Key Scenarios

| Scenario | Identifying Values | Expected JobInstance |
| --- | --- | --- |
| Two pods run the same period/snapshot | Identical | Same |
| API times out and retries | Identical | Same |
| Job `FAILED` and restarts | Identical | Same, new `JobExecution` |
| `COMPLETED` Job re-launched | Identical | Re-run rejected, no new instance |
| Two tenants on the same day | Different `tenantId` | Different |
| Same tenant/day, new snapshot | Different `snapshotId` | Different |
| Approved reprocess | Different `generation` | Different |
| `requestedBy`/`traceId` changed | Identifying unchanged | Same |
| Random `run.id` changed | Different identifying | Different, usually undesirable |
| Processing rule changed altering output | Must pin revision in key | Different or versioned workflow |

**A UUID is not always wrong.** If a Job is designed to process individual messages and the message ID is genuinely the durable business identity, the message's UUID can be a valid identifying parameter. The mistake is using a random ID **per attempt** when all attempts process the same batch.

## 18. Testing JobInstance with Spring Batch Test

Verify identity against a **real `JobRepository`**, rather than merely assembling strings and comparing them.

Example with JUnit 5, Spring Batch Test, Spring Boot Test, and AssertJ; assumes the Job is configured and has an immutable snapshot fixture:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportJobIdentityTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @Test
    void refusesSecondLaunchAfterCompleted() throws Exception {
        String snapshotId = createFinalizedSnapshotFixture();

        ImportRunKey key = new ImportRunKey(
                "tenant-a",
                LocalDate.of(2026, 11, 15),
                snapshotId,
                1L);

        JobParameters parameters =
                key.toParameters("test", "trace-a");

        JobExecution first =
                jobLauncher.run(importOrdersJob, parameters);

        assertThat(first.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        assertThatThrownBy(
                () -> jobLauncher.run(importOrdersJob, parameters))
                .isInstanceOf(JobInstanceAlreadyCompleteException.class);
    }
}
~~~

**`createFinalizedSnapshotFixture()`** is a helper you must implement yourself to insert source data and mark the snapshot `FINALIZED`. This snippet shows the identity assertion. The test must configure the database/schema, the Job bean, and a synchronous launcher or explicitly wait for completion.

If the context has multiple Jobs, inject using **`@Qualifier`** to target the right Job. Do not share one fixed snapshot across independent tests if they can run in parallel.

### Testing That Changing Non-Identifying Parameters Does Not Create a New JobInstance

~~~java
JobParameters firstParams =
        key.toParameters("scheduler", "trace-1");

JobParameters anotherRequest =
        key.toParameters("operator", "trace-2");

JobExecution first =
        jobLauncher.run(importOrdersJob, firstParams);

assertThat(first.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThatThrownBy(
        () -> jobLauncher.run(importOrdersJob, anotherRequest))
        .isInstanceOf(JobInstanceAlreadyCompleteException.class);
~~~

If this test creates a different `JobInstance`, **`traceId`** or **`requestedBy`** was likely marked `identifying=true` in some code path.

### Testing That Different Snapshots/Generations Create Different JobInstances

~~~java
ImportRunKey keyV1 =
        new ImportRunKey("tenant-a", date, "snapshot-v1", 1L);

ImportRunKey keyV2 =
        new ImportRunKey("tenant-a", date, "snapshot-v2", 1L);

JobExecution v1 = jobLauncher.run(
        importOrdersJob, keyV1.toParameters("test", "t1"));

JobExecution v2 = jobLauncher.run(
        importOrdersJob, keyV2.toParameters("test", "t2"));

assertThat(v1.getJobInstance().getId())
        .isNotEqualTo(v2.getJobInstance().getId());
~~~

Both snapshots must be created and finalized before running. This test only checks identity; to confirm business correctness, reconcile the actual output of each snapshot.

### Testing That Restart Uses the Same JobInstance

~~~java
JobParameters params =
        key.toParameters("test", "restart-case");

JobExecution failed = jobLauncher.run(importOrdersJob, params);
assertThat(failed.getStatus()).isEqualTo(BatchStatus.FAILED);

// Disable failure injection of the test fixture.
JobExecution recovered =
        jobLauncher.run(importOrdersJob, params);

assertThat(recovered.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(recovered.getId()).isNotEqualTo(failed.getId());
assertThat(recovered.getJobInstance().getId())
        .isEqualTo(failed.getJobInstance().getId());
~~~

To be meaningful, the test must trigger a failure **after a committed chunk**, keep the input immutable, and then verify output records have no missing or duplicate entries. Asserting the `JobInstance` ID alone is insufficient to prove data-correct restarts.

## 19. Testing Concurrent Scheduler Launches

A multi-pod system needs to prove that two concurrent requests with the same key **do not create two `JobInstance`s**.

~~~text
Thread A --+
           +--> launch(same Job, same identifying parameters)
Thread B --+
                         |
                         v
                Shared JDBC JobRepository
                         |
                         +--> One JobInstance for the business key
                         +--> Execution state decides
                              which request is allowed to run
~~~

Integration test design:

1. Create a dedicated snapshot and an `ImportRunKey`.
2. Launch two threads near-simultaneously using **`CountDownLatch`** or **`CyclicBarrier`**.
3. Keep the Job running long enough if verifying the `STARTED` state is needed.
4. Record the execution/exception of each request; **do not assume Thread A always wins**.
5. Query `JobRepository` to verify only one `JobInstance` exists for the key.
6. Verify the final output has one accurate set of records with no duplicates.

Do not rely solely on **`Thread.sleep`** for test synchronization; arbitrary timing creates flaky tests. Two independent in-memory H2 repositories also do not prove multi-JVM coordination. Share one JDBC repository just as in real architecture.

## 20. Common Design Mistakes

### Generating a Different `run.id` for Every Run

~~~java
new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
~~~

In the builder, parameters often default to `identifying=true` if omitted. When that happens, the same data may be run repeatedly as different `JobInstance`s. Use a stable business key.

### Identifying Solely by `businessDate`

If a Job handles multiple tenants or multiple snapshots per day, `businessDate` alone is insufficient. A valid request might be rejected because another instance already `COMPLETED`.

### Changing Identifying Parameters to Restart

Restarts need the same `JobInstance`. Changing timestamp or generation immediately after a failure can bypass checkpoints and reprocess from the start.

### Making `sourceSnapshotId` Non-Identifying

A new snapshot may be grouped into the old `JobInstance` or restart with changed input. Explicitly decide whether a new source represents new work.

### Using a Mutable File Path as Identity

The path **`/incoming/orders.csv`** can be overwritten. Use an immutable snapshot ID or object version/digest.

### Not Pinning Transformation Logic Versions

After a deployment, a `FAILED` Job restarted with new logic can mix two versions in its output. Version rules and restart/reprocess policies.

### Mixing Generations in Output

A new generation has its own `JobInstance`, yet downstream reads both results. Design a publication pointer or version contract.

### Editing `BATCH_JOB_INSTANCE`/`BATCH_JOB_EXECUTION` via SQL

Changing `STATUS`, `JOB_KEY`, or deleting metadata to force a run can corrupt history and checkpoints. Use lifecycle APIs and controlled operational workflows.

### Storing Secrets in Parameters

`Identifying=false` is not a security mechanism. Secrets must live in a proper secrets management system.

### Checking Only `JobInstance` Count While Ignoring Data

A single `JobInstance` can still write wrong amounts or process mutable input. You need validation, idempotency, and reconciliation.

## 21. Production Deployment Workflow

~~~text
Scheduler / API / Operator
           |
           v
Authentication + tenant authorization
           |
           v
Canonicalize business key
           |
           v
Check snapshot FINALIZED + immutable version
           |
           v
Build JobParameters with explicit identifying flags
           |
           v
JobLauncher + shared JobRepository
           |
    +------+--------+---------+
    |               |         |
   NEW          RUNNING     COMPLETED
    |               |         |
    v               v         v
  Run Job        Return      Return
                 status      existing result
    |
    +--> FAILED: restart same identity
    |
    +--> COMPLETED: reconcile and publish
    |
    +--> Approved reprocess: new generation/snapshot
~~~

The orchestration layer should log/audit **Job name, `tenantId`, `businessDate`, `snapshotId`, `generation`, `JobInstance` ID, `JobExecution` ID, `requestedBy`, and reprocessing reason**, per organizational data permissions. Never log passwords or raw `ExecutionContext`.

The system must respond consistently to retried requests and races: never auto-create a new identity to avoid an exception. On repository errors, verify whether an execution was already created before retrying.

## 22. Practice Project Completion Checklist

- [ ] Clearly define one **business unit of work** for the Job.
- [ ] Have a factory/value object that constructs identity consistently.
- [ ] Tenant, date, snapshot, and generation have canonical types and values.
- [ ] Input snapshot stays immutable across restarts.
- [ ] Parameters affecting output are identifying or pinned to an immutable version.
- [ ] `requestedBy` and `traceId` do not create a new `JobInstance`.
- [ ] `JobParametersValidator` rejects missing keys, invalid formats, and wrong identifying flags.
- [ ] Reader reads only input belonging to the right tenant/snapshot.
- [ ] Writer writes to the right data scope with idempotency.
- [ ] Scheduler/API/operator share the exact same parameter-building rules.
- [ ] Duplicate launches of a `COMPLETED` Job do not turn into new runs.
- [ ] Restarts of `FAILED` use the exact same identifying parameters.
- [ ] Reprocessing after `COMPLETED` uses an approved new snapshot/generation.
- [ ] Concurrent launch tests exist against a shared `JobRepository`.
- [ ] Restart tests exist and reconcile output with no missing/duplicate rows.
- [ ] Downstream selects only the published generation.
- [ ] No secrets reside in `JobParameters` metadata.

## 23. Conclusion

The core question when designing **`JobParameters`** is not **"how do I make the Job run again?"** but **"what constitutes a single unique unit of business work?"**.

For a multi-tenant order-import project, **Job name + `(tenantId, businessDate, sourceSnapshotId, generation)`** creates a meaningful identity. If the initial run fails, Spring Batch **restarts the same `JobInstance`** using the old identifying parameters. If there is a new snapshot or an approved reprocess, the application **intentionally creates a different `JobInstance`**. Values like `requestedBy`/`traceId` aid observability without changing the unit of work.

Combining **canonicalization, validation, immutable snapshots, a shared `JobRepository`, an idempotent writer, and integration tests** avoids two opposite pitfalls: reprocessing the same data twice or falsely rejecting a new batch. This forms the foundation for a Spring Batch system that can restart, backfill, audit, and scale across multiple instances safely.

