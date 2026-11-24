# Testing Restart After Process Termination in Spring Batch

A Spring Batch job may complete accurately when running uninterrupted, yet lose or duplicate data if the JVM is terminated mid-run. In production, processes can terminate due to deployments, operator stop requests, Kubernetes Pod replacements, OS signals, or power loss. These scenarios differ in how Spring Batch persists metadata updates, so you must **test restarts across two genuinely separate processes**, rather than merely invoking the job twice inside a single JUnit test.

This practice project belongs to **Spring Batch Core Processing → Practice Projects** and centers on the question:

> After a job process terminates mid-run, can a new process use persisted metadata to resume **without losing or duplicating** already committed records?

We will build a small project with CSV input, a chunk-oriented step, a PostgreSQL database storing `JobRepository` and output, a stop flag checked **after each chunk commit**, and then start a new JVM with the **same identifying `JobParameters`**. At the end we also test an **abrupt process kill** to recognize an important limitation: `SIGKILL` or `Stop-Process -Force` can leave metadata in the `STARTED` state; in that case, **never assume Spring Batch will automatically restart it as it would a recorded `STOPPED` or `FAILED` execution**.

## 1. Objectives and Completion Criteria

After this lesson, you should be able to:

1. Explain the relationship among `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`, and checkpoints.
2. Use a **persistent PostgreSQL database** for metadata instead of in-memory H2, which disappears with the JVM.
3. Let the job commit several chunks, issue a **controlled stop**, confirm the `STOPPED` status, and let the process exit.
4. Start a new JVM with the **same `businessDate` and `sourceVersion`**, confirming that restarting creates a new `JobExecution` under the old `JobInstance`.
5. Reconcile final output by business key: complete record set, no duplicates, accurate payloads.
6. Test a hard kill and distinguish "process died" from "Batch saved a restartable state."
7. Design a runbook for handling executions stuck in `STARTED` and controlling input/output resources.

**The most important criterion:** A `JobExecution` with `COMPLETED` is only a necessary condition. This practice project is only considered successful when **physical output** and metadata prove accurate resumption.

## 2. Restart Mechanism When a Process Terminates

Spring Batch identifies a `JobInstance` by **job name + set of identifying `JobParameters`**. Each execution of that instance has its own `JobExecution`; each step execution has its own `StepExecution`.

```text
Job name = importOrdersJob
Identifying parameters:
  businessDate  = 2026-11-16
  sourceVersion = orders-v1
                 |
                 v
           JobInstance #41
                 |
       +---------+----------+
       |                    |
       v                    v
JobExecution #101       JobExecution #102
    STOPPED                 COMPLETED
       |                    |
       v                    v
StepExecution #501      StepExecution #502
chunk 1..N commit       reader reopens checkpoint
context persisted       writes remaining items
```

A restartable reader (such as `FlatFileItemReader` with `saveState=true`) uses `ItemStream`:

```java
open(ExecutionContext savedState);    // Restore saved position.
read();                               // Read next item.
update(ExecutionContext state);       // Prepare checkpoint.
close();                              // Release resources.
```

In a chunk-oriented step, the reader/processor/writer process a group of items, state is updated, and the transaction commits. When a chunk fails, uncommitted items can be re-read. This holds if the writer participates in an appropriate transaction or is **idempotent** for external side effects.

Example with chunk size 10:

```text
Input: O0001 ........................................ O0200

Chunk 1:  O0001..O0010   -> COMMIT
Chunk 2:  O0011..O0020   -> COMMIT
Chunk 3:  O0021..O0030   -> COMMIT
Chunk 4:  O0031..O0040   -> STOP REQUESTED before next chunk

PostgreSQL:
  processed_orders has 40 committed rows.
  BATCH_STEP_EXECUTION_CONTEXT stores state after chunk #4.

Process A exits.
Process B starts with the same JobInstance:
  Reader restores checkpoint and reads the rest.
  Final result has 200 unique business keys.
```

**Never infer the restart point solely from `readCount`, the last logged item line, or an in-memory cursor position.** The source of truth for recovery is state persisted in `JobRepository`, combined with input stability and transaction/output guarantees.

## 3. Classifying "Process Termination": Differences Matter Greatly

| Termination Type | Typical Cause | Observable Metadata State | How to Verify |
| --- | --- | --- | --- |
| **Controlled stop by Spring Batch** | Stop request issued, step finishes current chunk, framework writes status | Usually `STOPPED` | Start a new process and restart the same instance |
| **Process exits after `FAILED` job** | Exception occurs, framework handles exception and saves metadata | `FAILED` if updated in time | Fix root cause, restart the exact instance |
| **OS sends `SIGTERM`/normal shutdown** | Deployment, Pod terminating, `kill -TERM` | Depends on how app handles shutdown and grace period | Do not assume automatic `STOPPED`; inspect DB |
| **Hard kill** | Linux `kill -KILL`, Windows `Stop-Process -Force`, OOM kill, power loss | May remain `STARTED`/`STARTING` because JVM could not save final status | Needs a runbook to detect and handle stale executions before restart |

This is the core point of the practice project. **A process no longer running does not mean `JobRepository` knows it died.** If the repository still records an execution as `STARTED`, launching with the same parameters may be rejected because Spring Batch thinks an execution of that `JobInstance` is still running. Never blindly update `status` via SQL in an automated script just to make tests "turn green."

In the main practice section, we build a **request-stop-after-commit** mechanism to obtain a genuine `STOPPED` state, then shut down the process and restart from another JVM. The hard-kill scenario is tested separately with different expected outcomes.

## 4. Practice Project Architecture

```text
restart-lab/
  build.gradle
  docker-compose.yml
  src/main/java/com/example/restartlab/
    RestartLabApplication.java
    OrderLine.java
    StoredOrder.java
    BatchConfiguration.java
    StopAfterChunkListener.java
    RunJobOnce.java
  src/main/resources/
    application.yml
    schema.sql
  data/
    orders.csv
  control/
    stop.request              <-- appears only when stop is requested
```

Flow:

```text
                   JVM A / JVM B
                        |
                  ApplicationRunner
                        |
               importOrdersJob
                        |
               importOrdersStep
                        |
    FlatFileItemReader (ItemStream, saveState=true)
                        |
             ItemProcessor (small delay)
                        |
               JdbcBatchItemWriter
                        |
                  PostgreSQL
            +-----------+-----------+
            |                       |
     processed_orders           BATCH_* tables
     (business output)        (metadata/checkpoint)
            +-----------+-----------+
                        |
              Same DataSource /
              transaction manager
```

PostgreSQL is used for **both Batch metadata and the output table** so the transaction scenario is easy to explain. After verifying this model, you can expand to two separate datasources, file writers, or external APIs; in those cases, evaluate atomicity and idempotency separately.

The project assumes **Java 17+, Spring Boot 3.x, Spring Batch 5.x, Gradle**. API and package examples follow Spring Batch 5 configuration style; if using Spring Batch 6, update imports, builders, and test utilities for your running version.

## 5. Preparing Persistent PostgreSQL

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: batch_lab
      POSTGRES_USER: batch_lab
      POSTGRES_PASSWORD: batch_lab_pw
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Start the database:

```bash
docker compose up -d
```

The `pgdata` volume exists independently of the batch JVM. **Do not run `docker compose down -v` between the two executions**: the `-v` flag deletes the volume and the metadata needed for restarts. The sample password is for local lab use only, never for real environments.

### 5.1. Gradle Dependencies

For a Spring Boot 3.x project that already has compatible Gradle plugins and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

To run the project, configure the Spring Boot/Java plugins and versions per your project template. Do not arbitrarily combine Spring Boot 3 with Spring Batch 6 if your project's dependency management does not support it.

### 5.2. `application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: ${BATCH_DB_URL:jdbc:postgresql://localhost:5433/batch_lab}
    username: ${BATCH_DB_USER:batch_lab}
    password: ${BATCH_DB_PASSWORD:batch_lab_pw}
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
  sql:
    init:
      mode: always

demo:
  mode: run
  business-date: "2026-11-16"
  source-version: "orders-v1"
  input-path: "./data/orders.csv"
  stop-file: "./control/stop.request"
  pause-ms: 120
```

`spring.batch.job.enabled=false` prevents Spring Boot from auto-launching jobs outside the lab's controlled calls. `spring.batch.jdbc.initialize-schema=never` is crucial: **do not recreate the `BATCH_*` schema on every JVM restart**. In the bootstrap step we temporarily enable `always` **once only** to create the metadata schema, then switch back to `never`.

`spring.sql.init.mode=always` makes Spring Boot execute the demo's `schema.sql` on startup. The SQL file must be idempotent; production should manage schemas via migrations instead of repeating automatic scripts.

### 5.3. Business Output Schema

Create `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS processed_orders (
    source_version VARCHAR(80) NOT NULL,
    order_id       VARCHAR(32) NOT NULL,
    amount         INTEGER NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (source_version, order_id)
);
```

The `(source_version, order_id)` key prevents two writes of the same logical record from creating two physical rows. This is a **database-level idempotency layer**, not a replacement for checkpoints. Without this key, a transaction error or unintended rerun could duplicate output even if the job eventually reports `COMPLETED`.

## 6. Writing a Spring Boot Application That Runs One Job and Exits

Create `RestartLabApplication.java`:

```java
package com.example.restartlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RestartLabApplication {
    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(RestartLabApplication.class, args);

        // Once ApplicationRunner completes, close the context and JVM.
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

The goal is for each `java -jar` invocation to create **a separate process**, connect to the existing repository, run the job once, close the context, and exit. The lab does not allow a scheduler to auto-launch jobs concurrently with manual operations.

Create two data records in two separate Java files:

```java
// OrderLine.java
package com.example.restartlab;

public record OrderLine(String orderId, int amount) {}
```

```java
// StoredOrder.java
package com.example.restartlab;

public record StoredOrder(
    String sourceVersion,
    String orderId,
    int amount
) {}
```

To keep the practice easy to observe, the input contains only `orderId` and `amount`; `sourceVersion` comes from `JobParameters` and is attached to the output record in the processor.

## 7. Configuring the Reader, Processor, Writer, and Step

Create `BatchConfiguration.java`:

```java
package com.example.restartlab;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class BatchConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<OrderLine> ordersReader(
            @Value("#{jobParameters['inputPath']}") String inputPath) {

        return new FlatFileItemReaderBuilder<OrderLine>()
            .name("ordersReader")
            .resource(new FileSystemResource(inputPath))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderLine(
                fields.readString("orderId"),
                fields.readInt("amount")
            ))
            .saveState(true)
            .build();
    }

    @Bean
    @StepScope
    ItemProcessor<OrderLine, StoredOrder> ordersProcessor(
            @Value("#{jobParameters['sourceVersion']}") String sourceVersion,
            @Value("${demo.pause-ms:120}") long pauseMs) {

        return item -> {
            // Add only a small delay to allow observation and sending a stop signal.
            Thread.sleep(pauseMs);
            return new StoredOrder(
                sourceVersion, item.orderId(), item.amount());
        };
    }

    @Bean
    JdbcBatchItemWriter<StoredOrder> ordersWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<StoredOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO processed_orders (
                    source_version, order_id, amount
                ) VALUES (?, ?, ?)
                ON CONFLICT (source_version, order_id) DO NOTHING
                """)
            .itemPreparedStatementSetter((item, ps) -> {
                ps.setString(1, item.sourceVersion());
                ps.setString(2, item.orderId());
                ps.setInt(3, item.amount());
            })
            // DO NOTHING may return JDBC update count = 0.
            .assertUpdates(false)
            .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("ordersReader") FlatFileItemReader<OrderLine> reader,
            @Qualifier("ordersProcessor")
                ItemProcessor<OrderLine, StoredOrder> processor,
            @Qualifier("ordersWriter")
                JdbcBatchItemWriter<StoredOrder> writer,
            StopAfterChunkListener stopListener) {

        return new StepBuilder("importOrdersStep", repository)
            .<OrderLine, StoredOrder>chunk(10, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener((ChunkListener) stopListener)
            .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository repository,
            @Qualifier("importOrdersStep") Step step) {

        return new JobBuilder("importOrdersJob", repository)
            .start(step)
            .build();
    }
}
```

### 7.1. Why Must the Reader Have `@StepScope` and `saveState(true)`?

`FlatFileItemReader` is a stateful reader: it must know how far it has read. `@StepScope` creates a fresh reader with the `inputPath` for each step execution, avoiding reusing an instance already at EOF. `.name("ordersReader")` gives a stable name for the reader's state. `.saveState(true)` lets the framework persist checkpoints into `ExecutionContext` so it can reopen after a restart.

**A checkpoint is meaningful only when the input does not change.** If you edit `orders.csv`, reorder lines, or replace the file at the same path between runs, the saved position may point to a different line. In production, pass `sourceVersion`, object version/checksum, and keep the input copy immutable until the processing period concludes.

### 7.2. Why Does the Writer Use a Unique Key and `ON CONFLICT`?

Chunk transactions on the same datasource keep data and metadata coordinated consistently in the lab. However, when a system crashes at the commit boundary, or during a rerun, a unique key also prevents duplicate output. `ON CONFLICT DO NOTHING` is appropriate only when **same source version + same order ID** must represent identical data; if two writes share the same key yet have different amounts, the application should raise a conflict instead of silently ignoring it. In the lab, input is kept immutable so that condition holds.

`ON CONFLICT` is PostgreSQL syntax; if using H2, MySQL, or Oracle, adapt SQL to the dialect.

### 7.3. Why Chunk Size 10?

Chunk size 10 produces multiple commit points when processing 200 rows. The `Thread.sleep` delay in the processor merely gives learners time to send a stop signal; in production, never add sleep as part of business processing.

Increasing chunk size yields fewer checkpoints, yet on failure more items may need reprocessing. Decreasing chunk size increases transactions and metadata updates. Pick a commit interval based on benchmarks and failure-path testing, not throughput alone.

## 8. Creating a Stop Signal After Chunk Commit

To produce a **stop and restart recognized by Spring Batch**, we do not use `kill -9` in the primary run. Instead, we place a `control/stop.request` file; the listener checks after a successful chunk and asks the step to stop at a safe boundary.

Create `StopAfterChunkListener.java`:

```java
package com.example.restartlab;

import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StopAfterChunkListener implements ChunkListener {

    private static final Logger log =
        LoggerFactory.getLogger(StopAfterChunkListener.class);

    private final Path stopFile;

    public StopAfterChunkListener(
            @Value("${demo.stop-file:./control/stop.request}")
            String stopFilePath) {
        this.stopFile = Path.of(stopFilePath)
            .toAbsolutePath().normalize();
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();

        log.info(
            "event=chunk.committed jobExecutionId={} stepExecutionId={} "
                + "read={} write={} commits={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getCommitCount()
        );

        if (Files.exists(stopFile)) {
            // Ask Batch not to start another chunk after this point.
            step.setTerminateOnly();
            log.warn(
                "event=stop.requested stepExecutionId={} afterCommit={}",
                step.getId(), step.getCommitCount()
            );
        }
    }
}
```

The listener reads the flag in **`afterChunk`**, after a successful chunk, avoiding stopping mid-write while the writer is updating data. `setTerminateOnly()` asks the step to terminate via the framework mechanism; in a standard step lifecycle, Spring Batch can transition the execution to the appropriate stopped state. **The actual status must be verified in the repository**, not merely inferred from the listener logging `stop.requested`.

This file-flag mechanism is a **lab tool**, not a full-fledged job-stopping service. In production applications, use `JobOperator.stop(...)` and an access-controlled mechanism suited to your version and architecture. If the process receives `SIGKILL`, `afterChunk` may not run; that is a separate scenario covered later.

## 9. Running the Job with `JobParameters` and Returning an Exit Code

Create `RunJobOnce.java`:

```java
package com.example.restartlab;

import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.stereotype.Component;

@Component
public class RunJobOnce implements ApplicationRunner, ExitCodeGenerator {

    private static final Logger log = LoggerFactory.getLogger(RunJobOnce.class);

    private final JobLauncher launcher;
    private final Job job;

    @Value("${demo.mode:run}")
    private String mode;

    @Value("${demo.business-date:2026-11-16}")
    private String businessDate;

    @Value("${demo.source-version:orders-v1}")
    private String sourceVersion;

    @Value("${demo.input-path:./data/orders.csv}")
    private String inputPath;

    private int exitCode = 0;

    public RunJobOnce(
            JobLauncher launcher,
            @Qualifier("importOrdersJob") Job job) {
        this.launcher = launcher;
        this.job = job;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        if ("init".equals(mode)) {
            log.info("Schema bootstrap mode: no batch job launched");
            return;
        }
        if (!"run".equals(mode)) {
            throw new IllegalArgumentException("Unknown demo.mode: " + mode);
        }

        Path input = Path.of(inputPath).toAbsolutePath().normalize();
        if (!Files.isRegularFile(input)) {
            throw new IllegalStateException("Input file does not exist");
        }

        JobParameters parameters = new JobParametersBuilder()
            // These two parameters are IDENTIFYING: keep unchanged on restart.
            .addString("businessDate", businessDate)
            .addString("sourceVersion", sourceVersion)
            // Path is supplementary info only; must keep pointing to the
            // exact old file version throughout the execution chain.
            .addString("inputPath", input.toString(), false)
            .toJobParameters();

        JobExecution execution = launcher.run(job, parameters);

        log.info(
            "event=job.finished jobInstanceId={} jobExecutionId={} "
                + "status={} exitCode={}",
            execution.getJobInstance().getId(),
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus().getExitCode()
        );

        exitCode = execution.getStatus() == BatchStatus.COMPLETED ? 0
            : execution.getStatus() == BatchStatus.STOPPED ? 2
            : 1;
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
```

`ApplicationRunner` runs when Spring Boot starts; in the synchronous launcher configuration typically used in the lab, it waits for the job to finish. Then `RestartLabApplication.main` closes the Spring context and exits the JVM with an exit code:

- `0`: job completed.
- `2`: job was stopped in a controlled way.
- `1`: job returned another status.

If the launcher is configured **asynchronously**, `run(...)` may return before the job finishes; this runner pattern must be adapted to wait for the terminal status. The lab uses a synchronous launcher. If `launcher.run` throws an exception immediately upon failing to launch (e.g., the instance is still `STARTED`), Spring Boot may fail startup; inspect the exception and repository to classify it.

**`inputPath` is non-identifying because logical input identity in the lab is controlled by `sourceVersion`.** In production, ensure `sourceVersion` is truly bound to an immutable file and optionally store a checksum/object version. Never point `inputPath` to a different file on restart just because it is excluded from `JOB_KEY`.

## 10. Initializing the Metadata Schema Exactly Once

Spring Batch needs `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, and params/context tables to persist state. For PostgreSQL, Spring Batch provides versioned schema scripts.

In this lab, we use the Spring Boot initializer **once**:

```bash
# Build the JAR per the created Spring Boot project configuration.
./gradlew bootJar

# ONE-TIME ONLY: create the BATCH_* metadata tables.
java -jar build/libs/restart-lab-0.0.1-SNAPSHOT.jar \
  --demo.mode=init \
  --spring.batch.jdbc.initialize-schema=always
```

The JAR name above is an example; use the file name actually built by Gradle. On Windows PowerShell you can place all arguments on a single line. With `demo.mode=init`, the runner does not launch the job, while the Batch schema initializer creates the tables. All **subsequent** runs use `spring.batch.jdbc.initialize-schema=never` as in `application.yml`.

If the schema already exists, **do not blindly re-run `initialize-schema=always`**: versioned table creation scripts may error on existing tables. In real systems, use Flyway/Liquibase or controlled migration workflows. Also, **never drop the schema to "reset" an ongoing restart exercise**, as that wipes all history.

The application's `schema.sql` uses `CREATE TABLE IF NOT EXISTS`, so `processed_orders` can be checked/created at startup without deleting data between two JVMs.

## 11. Creating a Fixed Input and Observing the First Run

Create 200 rows of data, from `O0001` to `O0200`. On **PowerShell**:

```powershell
New-Item -ItemType Directory -Force .\data, .\control | Out-Null

$rows = @("orderId,amount") + (1..200 | ForEach-Object {
    "O{0:D4},{1}" -f $_, ($_ * 10)
})

[System.IO.File]::WriteAllLines(
    (Join-Path (Get-Location) "data\orders.csv"),
    $rows,
    (New-Object System.Text.UTF8Encoding($false))
)

# Clear any stop flag from the previous test; DO NOT clear the database.
Remove-Item .\control\stop.request -ErrorAction SilentlyContinue
```

On **Bash/Linux/macOS**:

```bash
mkdir -p data control
{
  echo 'orderId,amount'
  for i in $(seq 1 200); do
    printf 'O%04d,%d\n' "$i" "$((i * 10))"
  done
} > data/orders.csv

rm -f control/stop.request
```

Do not edit file content or row order during the test. If you want to create a new test case, use a **different `sourceVersion`** and new file/version path instead of overwriting the old instance's input.

### 11.1. Launching Process A

In the first terminal, run:

```bash
java -jar build/libs/restart-lab-0.0.1-SNAPSHOT.jar \
  --demo.mode=run \
  --demo.business-date=2026-11-16 \
  --demo.source-version=orders-v1 \
  --demo.input-path=./data/orders.csv
```

In PowerShell 5.1, you can write it on one line:

```powershell
java -jar .\build\libs\restart-lab-0.0.1-SNAPSHOT.jar --demo.mode=run --demo.business-date=2026-11-16 --demo.source-version=orders-v1 --demo.input-path=.\data\orders.csv
```

With `pause-ms=120`, each chunk of 10 items takes roughly one second plus I/O. Logs may look like:

```text
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=10 write=10 commits=1
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=20 write=20 commits=2
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=30 write=30 commits=3
```

The IDs and timings are **examples**, not fixed in real environments. `afterChunk` signals a successful commit cycle, useful for knowing when to send the stop request. Do not rely on the last log number as an absolute checkpoint if the process dies before flushing logs.

### 11.2. Sending the Stop Request from a Second Terminal

After seeing several `chunk.committed` lines, create the stop file in the second terminal:

```powershell
New-Item -ItemType File -Force .\control\stop.request | Out-Null
```

Or Bash:

```bash
touch control/stop.request
```

The next `afterChunk` will detect the file, call `step.setTerminateOnly()`, and ask the step to stop; the framework updates metadata and the runner exits. Example log:

```text
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=40 write=40 commits=4
event=stop.requested stepExecutionId=501 afterCommit=4
event=job.finished jobInstanceId=41 jobExecutionId=101 status=STOPPED exitCode=STOPPED
```

At this point **Process A has exited**. Do not launch Process B while Process A is still alive; restart may be rejected because the old execution is still running, or it may create a race condition.

If you stop too late, the job may have already processed all 200 rows and `COMPLETED`. In that case, use a **new `sourceVersion`** to repeat the scenario, or increase `demo.pause-ms`/row count for the new attempt. Never delete metadata of a completed instance and call that a restart test.

## 12. Inspecting State After Process A Exits

Connect to PostgreSQL, for example:

```bash
docker compose exec postgres psql -U batch_lab -d batch_lab
```

### 12.1. Counting Committed Output

```sql
SELECT COUNT(*) AS committed_rows
FROM processed_orders
WHERE source_version = 'orders-v1';
```

If a stop command was issued mid-run, expect:

```text
0 < committed_rows < 200
```

For example, `committed_rows=40` when stopping after the fourth chunk. The exact number depends on when the flag was created. `processed_orders` retains committed results across JVM exits because the data lives in the PostgreSQL volume.

### 12.2. Inspecting `JobExecution`s

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS AS JOB_STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID;
```

Expected in the controlled-stop phase: the latest execution of the `orders-v1` instance has `STATUS='STOPPED'`. If you see `STARTED`, **do not consider the controlled-stop test complete**: check whether the process is still alive and which stop mechanism was actually used.

To inspect identifying parameters in the Spring Batch 5.x JDBC schema:

```sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE PARAMETER_NAME IN (
    'businessDate', 'sourceVersion', 'inputPath'
)
ORDER BY JOB_EXECUTION_ID, PARAMETER_NAME;
```

Verify `businessDate` and `sourceVersion` are identifying; `inputPath` is non-identifying. If a test suite has multiple instances of the same job name, filter/compare full parameters to avoid reading the wrong execution.

### 12.3. Inspecting Steps and Checkpoints

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

Checkpoint metadata lives in `BATCH_STEP_EXECUTION_CONTEXT`, attached to the step execution. **Do not edit or delete the context** at this step. Context may be serialized by the framework in a version-dependent format; for structured reading in code, use `JobExplorer` and `StepExecution.getExecutionContext()` rather than manually parsing `SERIALIZED_CONTEXT` via SQL.

Example service reading Spring Batch 5.x metadata:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

void showStepState(JobExplorer explorer, long executionId) {
    JobExecution execution = explorer.getJobExecution(executionId);
    if (execution == null) {
        throw new IllegalArgumentException("Unknown executionId");
    }
    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
            "step=%s status=%s context=%s%n",
            step.getStepName(),
            step.getStatus(),
            step.getExecutionContext()
        );
    }
}
```

This snippet is for observation in the **lab**; never log the full `ExecutionContext` in production, as it may contain sensitive data or large state. In real usage, emit only approved checkpoint keys.

## 13. Launching Process B and Confirming the Restart

First **delete the stop flag**, but **do not delete the database or input file**:

```powershell
Remove-Item .\control\stop.request -ErrorAction SilentlyContinue
```

From a new terminal, run again with the **exact identifying parameters**:

```powershell
java -jar .\build\libs\restart-lab-0.0.1-SNAPSHOT.jar --demo.mode=run --demo.business-date=2026-11-16 --demo.source-version=orders-v1 --demo.input-path=.\data\orders.csv
```

This time, do not create a stop flag. Process B must use the **same database**, **same `sourceVersion` and `businessDate`**, and **same immutable input**. Spring Batch will create a new `JobExecution` under the stopped `JobInstance`; `FlatFileItemReader` is recreated and uses persisted state to resume. Once the step completes, Process B exits with exit code `0` in the demo configuration.

### 13.1. Metadata Evidence

Query the executions of that instance and verify the pattern:

```text
JobInstance #41
  ├─ JobExecution #101  STOPPED
  └─ JobExecution #102  COMPLETED
```

The key check is that **`JOB_INSTANCE_ID` is identical**, while **`JOB_EXECUTION_ID` differs**. If the two runs have different `JOB_INSTANCE_ID`s, you **created a new instance** rather than proving checkpoint-based restart.

When querying multiple executions, inspect metadata specifically for the test period, rather than merely looking at the highest ID across all jobs. A successful `JobExecution` also does not replace output assertions.

### 13.2. Output Data Evidence

```sql
-- All 200 output rows for this sourceVersion.
SELECT COUNT(*) AS total
FROM processed_orders
WHERE source_version = 'orders-v1';

-- Exactly 200 distinct business keys.
SELECT COUNT(DISTINCT order_id) AS distinct_orders
FROM processed_orders
WHERE source_version = 'orders-v1';

-- No duplicates under the chosen business key.
SELECT source_version, order_id, COUNT(*) AS occurrences
FROM processed_orders
WHERE source_version = 'orders-v1'
GROUP BY source_version, order_id
HAVING COUNT(*) > 1;

-- Reconcile first and last values.
SELECT order_id, amount
FROM processed_orders
WHERE source_version = 'orders-v1'
  AND order_id IN ('O0001', 'O0100', 'O0200')
ORDER BY order_id;
```

Expected:

| Check | Result |
| --- | --- |
| Row count | `200` |
| Distinct `order_id` count | `200` |
| Duplicate query | `0` rows |
| `O0001` | `amount=10` |
| `O0100` | `amount=1000` |
| `O0200` | `amount=2000` |
| Job instance ID across two processes | Unchanged |
| Initial execution and restart execution | `STOPPED` then `COMPLETED` |

Because the table has primary key `(source_version, order_id)`, duplicate queries on that key will always return zero rows if the constraint works. To prove **no lost items**, verify row count, key set, and payloads. A writer using `ON CONFLICT DO NOTHING` can mask reprocessing already-existing items; `COUNT(*)=200` alone does not prove the reader saved work via checkpoints. To verify the **exact resume point**, check `ExecutionContext`, the restart's read count, and log milestones.

### 13.3. Why Not Sum All `readCount`s and Compare to 200?

`StepExecution` has separate counters per execution. An uncommitted chunk may be read, rolled back, and then re-read on restart. When a step uses retries, actual processor/writer calls also need not equal unique business items. Therefore, summed counters across multiple `JobExecution`s may **differ from unique source counts**, depending on stop point and implementation. Final conclusions must rely on the dataset and output, while counters help explain the execution path.

## 14. Testing a Hard Kill: What Actually Happens?

After completing the standard stop exercise, use a **new `sourceVersion`** (such as `orders-hardkill-v1`) to isolate results. Ensure `control/stop.request` does not exist, then launch a new process with that version.

**This is an experiment that intentionally kills a process. Perform it only in a lab with an isolated database and output, never on a production job.**

### 14.1. Linux/macOS: Sending `SIGKILL`

Launch in the first terminal with `sourceVersion=orders-hardkill-v1`; once logs show a few chunks committed, find the process PID and send:

```bash
kill -KILL <PID_CUA_JAVA_PROCESS>
```

`<PID_CUA_JAVA_PROCESS>` is a placeholder; replace it with the exact PID of the **lab JVM**, not Postgres or another application.

### 14.2. Windows PowerShell: Force-Stopping the Right PID

If the process was launched via `Start-Process` in the lab environment:

```powershell
$p = Start-Process -FilePath "java" -ArgumentList @(
    "-jar",
    ".\build\libs\restart-lab-0.0.1-SNAPSHOT.jar",
    "--demo.mode=run",
    "--demo.business-date=2026-11-16",
    "--demo.source-version=orders-hardkill-v1",
    "--demo.input-path=.\data\orders.csv"
) -PassThru

# Observe the PID and dedicated log per configuration as needed.
$p.Id

# Only once confirmed to be the right lab process:
Stop-Process -Id $p.Id -Force
```

**Do not run `Stop-Process` immediately before the job commits a chunk** if the goal is to observe partial metadata/output mid-run. Use logs or DB queries to determine timing; the command example only shows the technical operation and does not auto-time a safe milestone.

### 14.3. Results to Observe, Not Guess

When a JVM is abruptly killed, Java shutdown hooks, `finally` blocks, and Spring Batch lifecycle callbacks **may not run**. Metadata may remain:

```text
JobExecution #103: STARTED
StepExecution #503: STARTED
END_TIME: null
```

At the same time, PostgreSQL may have committed several chunks before the process died, while the open chunk rolled back when the connection dropped. A `STARTED` record is not proof that a worker is still alive; nor is it a terminal state permitting normal restart.

If you immediately re-run with the **exact same identifying parameters**, Spring Batch may reject it with `JobExecutionAlreadyRunningException` or an error indicating the instance is still considered running. **This is a meaningful test result**, not a sign that the repository lost metadata.

### 14.4. Why Not Directly Edit `BATCH_*` Tables Yourself?

A data-loss-prone approach is:

```text
Kill process
   ↓
UPDATE BATCH_JOB_EXECUTION SET STATUS='FAILED' ...  (uncontrolled)
   ↓
Relaunch
```

Arbitrarily mutating job status can overlook step status, version fields, `ExecutionContext`, in-flight transactions, or mistake an execution **actually still running on another node**. The result is two executions concurrently writing output or restarting from an inconsistent checkpoint.

When a stale `STARTED` occurs, the operational procedure must:

1. **Confirm the old worker/process truly died** across all relevant nodes; check schedulers, Pods, and distributed locks, not just one machine.
2. **Ensure resources are released** and no other transaction/worker is still writing to the same dataset.
3. **Reconcile committed output** against the last verifiable checkpoint and input version.
4. **Back up metadata and log an incident** before performing any recovery procedure.
5. **Apply an approved administrative recovery procedure compatible with your Spring Batch version** to bring stuck executions to a consistent state per project runbooks. This may require controlled metadata maintenance; never keep a generic "auto-fix status" script for every job.
6. Only once the state is safe, **restart or rerun per business policy**, then verify output has no missing or duplicate records.

`JobOperator.abandon(...)` **is not a shortcut to restart**: a step/job marked `ABANDONED` means it will not continue via normal restarts. Misuse can cause steps to be skipped or instances to become unrestartable as expected. Never call `stop(...)` on an execution whose process has vanished and assume statuses will update completely.

**Conclusion of the hard-kill test:** Persistent JDBC metadata is necessary for recovery, yet **does not automatically detect every process death or auto-heal every stale state**. Recovery plans must cover infrastructure and abrupt process deaths.

## 15. `SIGTERM`, Graceful Shutdown, and Kubernetes

In production, a Pod typically receives `SIGTERM` during a rolling deployment or Kubernetes scale-down, followed by a *grace period* before forced kill. However:

- A JVM receiving `SIGTERM` **does not mean** Batch automatically transitions `JobExecution` to `STOPPED`.
- If a process is running a job synchronously, Spring context shutdown and metadata updates can race against time.
- If `terminationGracePeriodSeconds` expires, the Pod may be killed before the chunk/step completes.
- If a worker ignores stop requests or is blocked on long I/O, status may remain `STARTED`.
- Each Pod has its own filesystem; input/output files on ephemeral storage are lost when the Pod is replaced.

For batches needing restarts on a new Pod, use PostgreSQL or a persistent metadata store **outside the Pod**, immutable input/object versions, and durable output staging. Design a **cooperative stop** via the Batch operator, orchestration state, or tested lifecycle hooks. Only use `preStop`/shutdown hooks when you understand timing and APIs to call; they do not replace reconciliation after an abrupt Pod kill.

A production scenario can split into two flows:

```text
Controlled stop flow:
  request stop → finish chunk → save STOPPED
  → process exits → new Pod restarts same JobInstance

Uncontrolled stop flow:
  process dies → repository may remain STARTED
  → detect stale + confirm worker dead
  → controlled recovery → restart/rerun + reconcile
```

Never conflate the two flows when writing runbooks or setting SLOs.

## 16. Sources of Duplicates or Lost Data After Restart

Even when metadata is recorded and the `JobInstance` is right, restarts can still be unsafe if the input or writer does not uphold the contract.

| Cause | Symptom | Prevention |
| --- | --- | --- |
| Using in-memory H2 | New JVM cannot see old checkpoints | Use PostgreSQL/RDBMS or persistent metadata storage |
| Adding identifying `UUID` on every run | Creates new instance, re-reads from start | Keep `businessDate` and `sourceVersion` for the same logical run |
| Editing CSV while process is stopped | Old offset points to a different line | Pin file/object version, hash/checksum |
| `.saveState(false)` | Reader does not restore saved position | Enable `saveState(true)` for stateful readers |
| Changing `reader.name` between restarts | Context key changes | Keep state name and format contract stable |
| Reader not managed by framework as `ItemStream` | `open/update/close` do not run properly | Register stream or forward delegate lifecycle properly |
| Writer calls API outside transaction | Timeout yet API processed, retry resends | Idempotency key + outbox/reconciliation |
| Two datasources commit independently | Business output and metadata diverge | Review transaction boundaries, unique keys, and recovery |
| Paging query lacks stable `ORDER BY` | Restart skips or re-reads rows | Use unique sort key and snapshot |
| Partition range changed | New worker scans old worker's range | Keep ranges/names stable per instance |
| Deleting temp output file when `STOPPED` | Reader resumes yet lacks old output | Clean up by instance lifecycle, never early |
| Two nodes run same period | Duplicate writes or output contention | Scheduler coordination + identifying params + constraints |
| Hard kill leaves `STARTED` | Restart rejected | Detect stale executions and run controlled recovery |

For **zero duplicates**, never check only `writeCount`. With JDBC upsert, the same item can be sent to the writer twice while the table still holds one row. To prove checkpoint-accurate restart, combine context, logs, and items actually reprocessed. For APIs, also reconcile request/idempotency history on the target.

## 17. Extension: Testing Failure Inside a Chunk Instead of Stopping

The main practice project stops at a chunk boundary. To test rollbacks, you can intentionally make the writer throw an exception on an item after several chunks have committed.

Example of a **test-only** writer decorator:

```java
public final class FailOnceWriter<T> implements ItemWriter<T> {
    private final ItemWriter<T> delegate;
    private final java.util.concurrent.atomic.AtomicBoolean failOnce;

    public FailOnceWriter(
            ItemWriter<T> delegate,
            java.util.concurrent.atomic.AtomicBoolean failOnce) {
        this.delegate = delegate;
        this.failOnce = failOnce;
    }

    @Override
    public void write(Chunk<? extends T> items) throws Exception {
        if (failOnce.compareAndSet(true, false)) {
            throw new IllegalStateException("Injected failure before writing");
        }
        delegate.write(items);
    }
}
```

This is a sample component; `ItemWriter` and `Chunk` imports from Spring Batch 5.x must be declared in the actual test class. An `AtomicBoolean` living in the same JVM does not automatically survive a process restart; to trigger a failure **once across two processes**, use an external flag configuration or a durable, controlled test state.

After failure:

1. The first execution has `FAILED` if the framework managed to persist the status.
2. Previously committed chunks remain in output.
3. The failing chunk rolls back if the writer shares the same DB transaction.
4. Restart with the old identifying parameters and persisted state.
5. The final result must be identical to an error-free run.

In particular, test failing **before commit** and **after an off-transaction side effect is confirmed by the target**, because the two failure points have very different consequences.

## 18. Suggestions for Automated Multi-Process Integration Tests

Once done manually, you can build an integration test harness controlling **child processes**, a test database, and the stop flag. This automates better than simulating everything inside a single `@SpringBootTest`.

```text
Test harness (parent process)
       |
       +--> Dedicated PostgreSQL test container / DB
       |
       +--> Process A: java -jar restart-lab.jar
       |        |
       |        +-- poll DB/log: commitCount >= 3
       |        +-- create stop.request
       |        +-- wait for process exit with timeout
       |
       +--> Assert DB: STOPPED, 0 < outputCount < expected
       |
       +--> delete stop.request
       |
       +--> Process B: java -jar restart-lab.jar
       |        |
       |        +-- wait for process exit
       |
       +--> Assert DB: COMPLETED, same JobInstance,
                       different JobExecution,
                       accurate/non-duplicate output
```

This is a **test harness outline**, not Gradle commands required to run in this lesson. When implementing:

- Use a **dedicated database/port/volume for tests**.
- Wait for real conditions from the DB or structured logs, rather than `Thread.sleep(3000)` and assuming commits finished.
- Set reasonable timeouts and clean up all test processes, flag files, and DB containers.
- Never let tests touch production databases/files.
- Check results even when a child process exits with an unexpected exit code.
- Avoid depending on auto-incremented repository IDs; assert identity/status relationships.

Java snippet of a harness using `ProcessBuilder`:

```java
Process first = new ProcessBuilder(
    "java", "-jar", jarPath,
    "--demo.mode=run",
    "--demo.business-date=2026-11-16",
    "--demo.source-version=fixture-v1",
    "--demo.input-path=" + inputPath
).inheritIO().start();

// Poll DB until several chunks have committed.
// Create stop file then wait for Process A to exit with timeout.
// Use the right database and file of the test fixture.

if (!first.waitFor(60, java.util.concurrent.TimeUnit.SECONDS)) {
    first.destroyForcibly();
    throw new IllegalStateException("Process A did not stop in time");
}
```

`jarPath` and `inputPath` are variables prepared by the harness. The illustrative code only shows how to launch processes; polling/stop/assertions must be fully implemented in the real test project. For Process B, reuse the same `fixture-v1`, same file, and same database.

### 18.1. Assertions for the Two Executions

After retrieving `firstExecution` and `restartExecution` from `JobExplorer` or querying metadata:

```java
assertThat(firstExecution.getStatus())
    .isEqualTo(BatchStatus.STOPPED);

assertThat(restartExecution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

assertThat(restartExecution.getJobInstance().getId())
    .isEqualTo(firstExecution.getJobInstance().getId());

assertThat(restartExecution.getId())
    .isNotEqualTo(firstExecution.getId());

Integer resultCount = jdbcTemplate.queryForObject(
    """
    SELECT COUNT(*) FROM processed_orders
    WHERE source_version = ?
    """,
    Integer.class,
    "fixture-v1"
);
assertThat(resultCount).isEqualTo(200);
```

These are illustrative assertions, assuming objects/fixtures are initialized in the test harness. Add checks for the `order_id` set and `amount`, not just row counts.

## 19. How to Write a Practice Result Report

After each run, record an evidence sheet instead of just screenshotting a `COMPLETED` message:

| Field | Result to Record |
| --- | --- |
| `jobName` | `importOrdersJob` |
| Input | `orders.csv`, 200 rows, source version and checksum |
| Identifying parameters | `businessDate=2026-11-16`, `sourceVersion=orders-v1` |
| Metadata storage | PostgreSQL on Docker volume intact between both JVMs |
| Process A | PID, launch command, stop timestamp, exit code |
| Execution A | `JobInstance ID`, `JobExecution ID`, status `STOPPED` |
| Output A | Committed row count less than 200 |
| Process B | New PID/launch command, stop file absent |
| Execution B | Same `JobInstance ID`, different `JobExecution ID`, `COMPLETED` |
| Output B | 200 rows and 200 unique keys, accurate amounts |
| Hard-kill case | Whether stale `STARTED` appeared; recovery procedure applied |

The IDs or row counts in the example do not need to match literally because stop timing varies. What matters is the **relationship between the two executions**, input immutability, persisted checkpoints, and final output.

## 20. Common Mistakes When Doing the Lab

### 20.1. Error "relation BATCH_JOB_INSTANCE already exists"

You ran the `initialize-schema=always` schema bootstrap a second time. Keep `initialize-schema=never` after initial creation; to start a completely fresh lab, create another test database or reset intentionally after saving evidence, never dropping the schema of an instance under restart testing.

### 20.2. `JobInstanceAlreadyCompleteException`

A Job with the same identifying parameters is already `COMPLETED`. That is correct behavior: Spring Batch does not auto-rerun a completed job instance. To test a **new period**, intentionally change `sourceVersion`/business key; to test a restart, you must start with a genuinely `STOPPED` or `FAILED` execution.

### 20.3. `JobExecutionAlreadyRunningException`

Either the previous process is still running, or it was hard-killed and metadata remains `STARTED`. Inspect real workers/nodes and the repository; never update status with a quick SQL command lacking a runbook.

### 20.4. Restart Reprocesses the Entire File

Check identifying parameters, `@StepScope`, reader name, `.saveState(true)`, whether `ExecutionContext` exists, and whether the input file remained unchanged. If `sourceVersion` changed, that is a **new `JobInstance`**, not a restart.

### 20.5. Restart Produces Incomplete Output

The input may have been reordered, a file on an old Pod may have been lost, the output path changed, or checkpoints and transactions across separate datasources diverged. Compare business key sets between input and output, then investigate reader state and commit boundaries.

### 20.6. Database Has All 200 Rows Yet the Reader Actually Re-Read from the Beginning

Unique keys/`ON CONFLICT DO NOTHING` can mask re-reading errors. Inspect `JobInstance`, step context, chunk milestone logs, and actual items read in Execution B. Idempotency and checkpoint-accurate restarts are **two distinct properties** and must be verified separately.

### 20.7. Stop File Still Exists on Restart

The listener will request a stop after Process B's first chunk, so the job becomes `STOPPED` again. Delete `control/stop.request` before relaunching. Do not delete the input file or metadata at the same time.

### 20.8. `docker compose down -v` Between Phases

The `-v` flag deletes the PostgreSQL volume containing `BATCH_*` and output tables. After that, the test can no longer prove cross-process restarts. Use `docker compose stop` or keep the DB running across both phases; clean up volumes only after completing the entire lab.

### 20.9. Sending `SIGTERM` and Assuming the Job Is `STOPPED`

`SIGTERM` is an OS signal, not automatically a `JobOperator.stop` operation. Observe actual metadata, Spring context shutdown time, and chunk states; for hard kills, follow the stale-metadata scenario.

## 21. Advanced Exercises

1. **Change chunk size:** run the lab with chunk sizes 5, 10, 25. Observe checkpoint counts and items needing reprocessing while keeping final output accurate.
2. **Kill JVM mid-chunk:** use a hard kill, record `JobExecution.STATUS`, committed output, and differences from a controlled stop; write a handling runbook.
3. **Change input version:** try editing `orders.csv` between two executions and prove why line-based checkpoints are no longer reliable. Then add an input checksum to block restarts when the source changes.
4. **File writer:** replace the JDBC writer with `FlatFileItemWriter`, store files in persistent storage, and check file/append/header behavior on restart; write to a temp file and publish once.
5. **API without shared transaction:** simulate an API accepting a request successfully while the client times out, measure duplicates on retry; add an idempotency key from business identity.
6. **Two application instances:** have two launchers with identical identifying parameters try running concurrently and observe the repository; repeat with different parameters targeting the same output to see why unique constraints and scheduler coordination are needed.
7. **Multi-process automated test:** implement `ProcessBuilder` + DB polling + PostgreSQL Testcontainers, run on CI, and report not only status but also output data.

## 22. Conclusion

**Testing restart after process termination** is more than re-running `java -jar`. A worthwhile test preserves a **persistent metadata database**, uses the right **`JobInstance`**, preserves the **input version**, verifies **checkpoints and transactions**, and proves **final output has no missing or duplicate data**.

Controlled stops after a chunk and **hard kills** are two distinct scenarios. For `STOPPED`/`FAILED` recorded by Spring Batch, a new process can restart from metadata when configuration permits. For an abruptly killed process, metadata may remain stuck in `STARTED`; in that case, detect stale executions, confirm the worker died, and perform controlled recovery before attempting to continue. Proper design covers the **happy path, failure path, and operational runbook**.

## References

- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobExecution`, identifying parameters, and restarts.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): commit intervals, chunks, and transactions.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close`, and checkpoints in `ExecutionContext`.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): persistent metadata storage and transaction configuration.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_*` tables used to inspect job/step status.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): testing jobs, steps, statuses, and restartability.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): auto-configuration and job launching.
- [Kubernetes Documentation — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): termination signals and container/Pod lifecycles.
