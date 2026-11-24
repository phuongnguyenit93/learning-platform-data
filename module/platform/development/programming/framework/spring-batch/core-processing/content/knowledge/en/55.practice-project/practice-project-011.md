# Writing Unit and Integration Tests for a Spring Batch Project

A batch job can finish with status `COMPLETED` yet still miss records, duplicate processing on restart, skip too many data errors, or leave committed chunks behind when a later step fails. Therefore, Spring Batch testing must not stop at calling `jobLauncher.run(...)` and checking that the application throws no exception. You must verify **per-item processing rules**, **actual reader/processor/writer behavior**, **transactions, metadata, skip/retry, restarts**, and ultimately **output data**.

This lesson belongs to **Spring Batch Core Processing → Practice Projects** and guides writing **unit tests and integration tests** through a CSV-to-database order import project. Examples use **Java 17, Spring Boot 3.x, Spring Batch 5.x, JUnit 5, AssertJ, Spring Batch Test, and H2**. Tests specific to PostgreSQL/MySQL behavior can be run with Testcontainers rather than assuming H2 fully simulates the production database.

## 1. Distinguishing Unit Tests from Integration Tests in Batch

**Unit tests** verify a small component with deterministic inputs without booting the full Spring context or using a real `JobRepository`. **Integration tests** verify multiple components working together with the Spring Batch runtime, datasource, transactions, and metadata.

| Scope | Goal | Example Assertions |
| --- | --- | --- |
| Unit test `ItemProcessor` | Validation, mapping, filtering by business rules | Valid data produces output; invalid throws exception; filtered returns `null` |
| Unit test reader or mapper | Parsing and reader lifecycle | Reads expected fields; returns `null` at EOF; releases resources |
| Unit test policy | Skip, quality, and business-date decisions | Exact error codes and thresholds at boundary cases |
| Integration test step | Reader + processor + writer + transaction | `readCount`, `writeCount`, `filterCount`, skip counts, DB data |
| Integration test job | Job flow, `JobRepository`, final status | Job `COMPLETED`/`FAILED`, steps in order, accurate output |
| Restart/failure test | Consistency across failures and re-runs | Same instance creates new execution; no duplicate writes |
| Contract/real-dependency test | SQL, isolation, locking, API contracts | Unique keys, rollbacks, retries, and idempotency work properly |

The goal is not to write every test as `@SpringBootTest`. Short, readable, fast unit tests should form the majority; integration tests confirm what unit tests cannot prove.

```text
Business rules                        Spring Batch infrastructure
      |                                           |
      v                                           v
Unit tests                                Integration tests
      |                                           |
      +-- Processor / mapper                     +-- Reader -> Processor -> Writer
      +-- Error classifier                       +-- Transaction / chunk
      +-- Filtering policy                       +-- JobRepository metadata
      +-- Quality thresholds                     +-- Skip / restart / status
      |                                           |
      +----------------+--------------------------+
                       |
                       v
               Release confidence
```

## 2. Practice Project: `importOrdersJob`

Suppose each day the system receives an order CSV file. Pipeline:

```text
CSV input
   |
   v
FlatFileItemReader<RawOrder>
   |
   v
OrderProcessor
   |-- ACTIVE + valid amount ---> AcceptedOrder
   |-- CANCELLED ---------------> null (FILTER)
   |-- invalid amount ----------> InvalidOrderException (bounded SKIP)
   v
JdbcBatchItemWriter<AcceptedOrder>
   |
   v
accepted_orders (database)
   |
   v
JobRepository: JobExecution / StepExecution / counts
```

Illustrative contract:

- An `ACTIVE` record with a valid order ID and `amount > 0` is written.
- A `CANCELLED` record is excluded per the approved **filter rule**, not counted as a skip.
- A record missing `order_id` or having an invalid `amount` throws `InvalidOrderException`.
- A step may skip at most **2 items** of the types above. A third failing item fails the step.
- The target table has primary key `(source_batch_id, order_id)` to identify an order within a data version.
- Tests verify both **Spring Batch metadata** and **actual database records**.

This is a learning project and omits checksum preflight and downstream publish gates. When deploying critical business data, add source checks, quarantine, and conditional staging/publishing.

### 2.1. Directory Structure

```text
src/
├── main/
│   └── java/com/example/batch/
│       ├── OrdersBatchApplication.java
│       ├── RawOrder.java
│       ├── AcceptedOrder.java
│       ├── InvalidOrderException.java
│       ├── OrderProcessor.java
│       └── OrdersJobConfig.java
└── test/
    ├── java/com/example/batch/
    │   ├── OrderProcessorTest.java
    │   ├── OrderReaderTest.java
    │   └── ImportOrdersJobIT.java
    └── resources/
        ├── application-test.properties
        ├── schema.sql
        └── fixtures/
            ├── orders-mixed.csv
            ├── orders-valid.csv
            └── orders-too-many-invalid.csv
```

File and class names below match the structure above. Each `public` class/record resides in its own `.java` file.

## 3. Dependencies and Test Environment

Example `build.gradle` for a Spring Boot 3 project using a specific Boot 3.x version for illustration (not a recommendation to use an old version in production):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot manages Spring Batch and compatible dependency versions via dependency management. When integrating into a project with its own Boot version, use the project's version and BOM; avoid manually mixing incompatible Spring Batch, Spring Framework, and Spring Retry versions.

Core libraries:

| Dependency | Role in Tests |
| --- | --- |
| `spring-boot-starter-test` | JUnit 5, AssertJ, Mockito, Spring Boot Test infrastructure |
| `spring-batch-test` | `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, step-scope utilities |
| H2 | Embedded database for JDBC tests and `BATCH_*` metadata tables |
| `spring-boot-starter-batch` | Jobs, steps, readers/writers, `JobRepository`, transaction integration |
| `spring-boot-starter-jdbc` | Datasource, `JdbcTemplate`, JDBC transactions |

H2 is suitable for running this lesson and testing general batch rules. PostgreSQL/MySQL-specific behaviors such as keys, transaction isolation, deadlocks, `ON CONFLICT` syntax, and query performance should also be tested against the real database engine using Testcontainers or an isolated test environment.

### 3.1. Application Entry Point

`OrdersBatchApplication.java`:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersBatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersBatchApplication.class, args);
    }
}
```

With Spring Boot 3 and standard batch auto-configuration, you do not need to manually add `@EnableBatchProcessing`. That annotation can alter how Boot auto-configures infrastructure, so use it only when the project genuinely needs manual batch infrastructure configuration.

## 4. Implementing Business Logic for Testing

### 4.1. Input and Output Data

`RawOrder.java`:

```java
package com.example.batch;

public record RawOrder(
        String orderId,
        String status,
        String amountText) {}
```

`AcceptedOrder.java`:

```java
package com.example.batch;

import java.math.BigDecimal;

public record AcceptedOrder(
        String sourceBatchId,
        String orderId,
        BigDecimal amount) {}
```

`sourceBatchId` identifies the source data version. When a job re-runs or replays, this identifier helps reconcile output against a specific batch. Never add a random `run.id` to the writer's business key, as that can defeat duplicate prevention.

`InvalidOrderException.java`:

```java
package com.example.batch;

public class InvalidOrderException extends RuntimeException {

    private final String reasonCode;

    public InvalidOrderException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
```

The exception uses a **fixed reason code** rather than putting raw CSV data, emails, or sensitive details into the message.

### 4.2. Processor Independent of the Spring Context

`OrderProcessor.java`:

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<RawOrder, AcceptedOrder> {

    private final String sourceBatchId;

    public OrderProcessor(String sourceBatchId) {
        if (sourceBatchId == null || sourceBatchId.isBlank()) {
            throw new IllegalArgumentException(
                    "sourceBatchId is required");
        }
        this.sourceBatchId = sourceBatchId;
    }

    @Override
    public AcceptedOrder process(RawOrder row) {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("MISSING_ORDER_ID");
        }

        if ("CANCELLED".equals(row.status())) {
            return null; // Filtering allowed by business rule.
        }

        if (!"ACTIVE".equals(row.status())) {
            throw new InvalidOrderException("UNSUPPORTED_STATUS");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(row.amountText());
        } catch (NumberFormatException | NullPointerException ex) {
            throw new InvalidOrderException("INVALID_AMOUNT");
        }

        if (amount.signum() <= 0) {
            throw new InvalidOrderException("NON_POSITIVE_AMOUNT");
        }

        return new AcceptedOrder(
                sourceBatchId, row.orderId(), amount);
    }
}
```

The processor has no dependency on datasources, loggers, or `JobRepository`, so it can be tested directly with `new OrderProcessor(...)`. In real programs, the `CANCELLED` rule must be confirmed against the business contract: intentional filtering does not mean corrupted data.

## 5. Wiring Reader, Processor, Writer, and Job

`OrdersJobConfig.java`:

```java
package com.example.batch;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersJobConfig {

    @Bean
    @StepScope
    FlatFileItemReader<RawOrder> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<RawOrder>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("order_id", "status", "amount")
                .fieldSetMapper(fields -> new RawOrder(
                        fields.readString("order_id"),
                        fields.readString("status"),
                        fields.readString("amount")))
                .build();
    }

    @Bean
    @StepScope
    OrderProcessor orderProcessor(
            @Value("#{jobParameters['sourceBatchId']}")
            String sourceBatchId) {
        return new OrderProcessor(sourceBatchId);
    }

    @Bean
    JdbcBatchItemWriter<AcceptedOrder> orderWriter(
            DataSource dataSource) {

        return new JdbcBatchItemWriterBuilder<AcceptedOrder>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO accepted_orders
                         (source_batch_id, order_id, amount)
                     VALUES (:sourceBatchId, :orderId, :amount)
                     """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("sourceBatchId",
                                        item.sourceBatchId())
                                .addValue("orderId", item.orderId())
                                .addValue("amount", item.amount()))
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> reader,
            OrderProcessor processor,
            JdbcBatchItemWriter<AcceptedOrder> writer) {

        return new StepBuilder("importOrdersStep", repository)
                .<RawOrder, AcceptedOrder>chunk(2, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .skip(InvalidOrderException.class)
                .skipLimit(2)
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

In the configuration above:

- `@StepScope` on the reader and processor allows receiving `JobParameters` for the specific execution; avoid reading parameters too early when creating a singleton.
- Chunk size is **2** so tests can easily observe commits/rollbacks across small groups; production sizes must be chosen based on real load.
- `.skipLimit(2)` applies only to `InvalidOrderException`. Never use `.skip(Exception.class)`, which can mask JDBC errors and programming bugs.
- The writer uses `MapSqlParameterSource` explicitly to map **Java record accessors** to SQL parameters.
- The test application has only one `Job`, `importOrdersJob`; if multiple jobs exist, tests must target the right bean.

`FlatFileItemReader.linesToSkip(1)` **does not validate headers**. Tests must add preflight/header validation if the project requires enforcing input schema versions. A real job also needs to define how rejects/quarantine are persisted when skips are allowed.

## 6. Preparing the Test Database and Fixtures

`src/test/resources/application-test.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:orders_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Tests explicitly launch the job; prevent Boot from auto-launching on context load.
spring.batch.job.enabled=false
spring.batch.jdbc.initialize-schema=always

# Execute the application's schema.sql in the test database.
spring.sql.init.mode=always
```

`src/test/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS accepted_orders (
    source_batch_id VARCHAR(100) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL,
    PRIMARY KEY (source_batch_id, order_id)
);
```

The `BATCH_*` schema is initialized by Spring Boot when `spring.batch.jdbc.initialize-schema=always` is set with H2 in the example. The `accepted_orders` table is created by `schema.sql`. Test data tables must be **completely isolated from production**.

### 6.1. Fixture Covering Cases for Counter Calculations

`src/test/resources/fixtures/orders-mixed.csv`:

```csv
order_id,status,amount
o-001,ACTIVE,120.00
o-002,ACTIVE,BAD
o-003,CANCELLED,50.00
o-004,ACTIVE,75.00
o-005,ACTIVE,10.00
```

Expected:

| Record | Processing | Result |
| --- | --- | --- |
| `o-001` | Valid `ACTIVE` | Writes 120.00 |
| `o-002` | `BAD` unparseable as number | Skipped with `INVALID_AMOUNT` |
| `o-003` | `CANCELLED` | Filtered, not written |
| `o-004` | Valid `ACTIVE` | Writes 75.00 |
| `o-005` | Valid `ACTIVE` | Writes 10.00 |

On a successful run, the expected counter model is:

```text
readCount          = 5
processSkipCount   = 1
filterCount        = 1
writeCount         = 3
skipCount          = 1

5 input = 3 accepted + 1 rejected + 1 filtered
```

`src/test/resources/fixtures/orders-valid.csv`:

```csv
order_id,status,amount
o-101,ACTIVE,15.00
o-102,ACTIVE,24.00
```

`src/test/resources/fixtures/orders-too-many-invalid.csv`:

```csv
order_id,status,amount
o-201,ACTIVE,BAD
o-202,ACTIVE,BAD
o-203,ACTIVE,BAD
o-204,ACTIVE,20.00
```

With `skipLimit(2)`, a third input needing a skip exceeds the threshold, causing the step to fail; this must never be treated as a successful import.

## 7. Unit Testing `ItemProcessor`

`OrderProcessorTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class OrderProcessorTest {

    private final OrderProcessor processor =
            new OrderProcessor("fixture-batch");

    @Test
    void activeOrderProducesAcceptedOrder() throws Exception {
        RawOrder input = new RawOrder(
                "o-001", "ACTIVE", "120.50");

        AcceptedOrder actual = processor.process(input);

        assertThat(actual).isEqualTo(new AcceptedOrder(
                "fixture-batch",
                "o-001",
                new BigDecimal("120.50")));
    }

    @Test
    void cancelledOrderIsFiltered() throws Exception {
        RawOrder input = new RawOrder(
                "o-002", "CANCELLED", "999.00");

        assertThat(processor.process(input)).isNull();
    }

    @ParameterizedTest
    @CsvSource({
        "o-003, ACTIVE, abc, INVALID_AMOUNT",
        "o-004, ACTIVE, -1, NON_POSITIVE_AMOUNT",
        "o-005, ACTIVE, 0, NON_POSITIVE_AMOUNT",
        "o-006, UNKNOWN, 10, UNSUPPORTED_STATUS"
    })
    void invalidOrdersHaveStableReasonCodes(
            String id, String status, String amount, String expectedCode) {

        assertThatThrownBy(() -> processor.process(
                new RawOrder(id, status, amount)))
                .isInstanceOf(InvalidOrderException.class)
                .hasMessage(expectedCode);
    }

    @Test
    void missingIdIsNotSilentlyFiltered() {
        assertThatThrownBy(() -> processor.process(
                new RawOrder("", "ACTIVE", "10")))
                .isInstanceOf(InvalidOrderException.class)
                .hasMessage("MISSING_ORDER_ID");
    }
}
```

Why is this a unit test?

- Does not use `@SpringBootTest` or a database.
- Fixed inputs, independent of clocks or networks.
- Tests both the **happy path** and business-meaningful error branches.
- Tests only **processor behavior**: this test does not prove Spring Batch increments `skipCount` when an exception occurs, because skipping is a fault-tolerant step mechanism.

Do not call `processor.process(...)` and assume you tested `JobRepository`, retries, or transactions. Those require integration tests.

## 8. Unit Testing the Lifecycle of `FlatFileItemReader`

A reader has open/close state and depends on a resource. You can test the reader without booting a Spring context by constructing it directly and supplying an `ExecutionContext`.

`OrderReaderTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

class OrderReaderTest {

    @TempDir
    Path tempDir;

    @Test
    void readsRowsThenReturnsNullAtEndOfFile() throws Exception {
        Path csv = tempDir.resolve("orders.csv");
        Files.writeString(csv, """
                order_id,status,amount
                o-001,ACTIVE,10.00
                o-002,CANCELLED,20.00
                """, StandardCharsets.UTF_8);

        FlatFileItemReader<RawOrder> reader =
                new FlatFileItemReaderBuilder<RawOrder>()
                        .name("readerUnderTest")
                        .resource(new FileSystemResource(csv))
                        .linesToSkip(1)
                        .delimited()
                        .names("order_id", "status", "amount")
                        .fieldSetMapper(f -> new RawOrder(
                                f.readString("order_id"),
                                f.readString("status"),
                                f.readString("amount")))
                        .build();

        try {
            reader.open(new ExecutionContext());

            assertThat(reader.read()).isEqualTo(
                    new RawOrder("o-001", "ACTIVE", "10.00"));
            assertThat(reader.read()).isEqualTo(
                    new RawOrder("o-002", "CANCELLED", "20.00"));
            assertThat(reader.read()).isNull();
        } finally {
            reader.close();
        }
    }
}
```

`@TempDir` creates an isolated directory for the test and avoids depending on a file at an absolute path on a developer's machine. When using a stateful reader, do not forget **`open(...)` and `close()`**, and for restart tests also check `update(ExecutionContext)`/checkpoints per the actual reader.

With `FlatFileItemReader` and `linesToSkip(1)`, this test only verifies parsing the two lines after the header. To ensure column names are right, write a separate test for **header validation** in a preflight step; skipping one line does not automatically validate that line's content.

## 9. Integration Testing the Full Job

`@SpringBatchTest` provides convenient utilities to launch jobs/steps and work with Spring Batch's test scope. Combine it with `@SpringBootTest` to load the application context, datasource, transaction manager, and `JobRepository`.

Example `ImportOrdersJobIT.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class ImportOrdersJobIT {

    @Autowired
    private JobLauncherTestUtils jobs;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void prepare() {
        jobs.setJob(importOrdersJob);
        // Delete application data only in an isolated test database.
        jdbc.update("DELETE FROM accepted_orders");
    }

    private JobParameters params(String fixture) throws Exception {
        Path file = Path.of(new ClassPathResource(
                "fixtures/" + fixture).getURI());

        return new JobParametersBuilder()
                .addString("inputFile", file.toString(), true)
                .addString("sourceBatchId",
                        "test-" + UUID.randomUUID(), true)
                .toJobParameters();
    }

    @Test
    void importsAcceptedRowsAndCountsSkipsAndFilters() throws Exception {
        JobExecution execution =
                jobs.launchJob(params("orders-mixed.csv"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        StepExecution step = execution.getStepExecutions()
                .stream()
                .filter(s -> "importOrdersStep".equals(s.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(step.getReadCount()).isEqualTo(5);
        assertThat(step.getProcessSkipCount()).isEqualTo(1);
        assertThat(step.getFilterCount()).isEqualTo(1);
        assertThat(step.getSkipCount()).isEqualTo(1);
        assertThat(step.getWriteCount()).isEqualTo(3);

        Integer saved = jdbc.queryForObject(
                "SELECT COUNT(*) FROM accepted_orders",
                Integer.class);
        assertThat(saved).isEqualTo(3);

        Double sum = jdbc.queryForObject(
                "SELECT SUM(amount) FROM accepted_orders",
                Double.class);
        assertThat(sum).isEqualTo(205.0);
    }

    @Test
    void failsWhenSkipLimitIsExceeded() throws Exception {
        JobExecution execution =
                jobs.launchJob(params("orders-too-many-invalid.csv"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.FAILED);

        // Do not treat chunks committed prior to FAILED as
        // complete data for downstream consumption.
    }

    @Test
    void completedInstanceCannotBeLaunchedAgainWithSameParameters()
            throws Exception {

        JobParameters sameParams = params("orders-valid.csv");

        JobExecution first = jobs.launchJob(sameParams);
        assertThat(first.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        assertThatThrownBy(() -> jobs.launchJob(sameParams))
                .isInstanceOf(
                        JobInstanceAlreadyCompleteException.class);
    }
}
```

**Explanation of the `params(...)` helper:**

- Each test receives a random `sourceBatchId` so it does not collide with completed `JobInstance`s of other tests.
- In the *re-run same instance* test, we keep the exact same `sameParams` object. Creating a new parameter set would no longer test the duplicate-instance rule properly.
- `ClassPathResource.getURI()` can convert to `Path` in a test environment when the resource is a file on the filesystem. For packaged resources inside an executable JAR, use another mechanism (e.g., copying to `@TempDir` or reading via `Resource`).
- The test uses `@BeforeEach` to clear the output table in a **dedicated test H2 database**. Never do this on a datasource shared with other environments.

**Why also check the database?** `BatchStatus.COMPLETED` and `writeCount=3` are technical metadata. Querying the table confirms the writer persisted the right number of records to the database. For financial or aggregate workloads, also compare **total amounts, unique keys, checksums, and per-row values**, rather than only row count.

In the example, `120.00 + 75.00 + 10.00 = 205.00`. `Double` is used to illustrate a simple sum query; in financial applications, retrieve and compare **`BigDecimal`** to avoid floating-point precision errors.

### 9.1. Test Names and Gradle Configuration

Gradle's `test` task by default detects classes named `*Test`, `*Tests`, or patterns supported by the framework; for classes with an `IT` suffix, **make sure the test task configuration actually includes them** (or rename to `ImportOrdersJobTest`). If using a separate `integrationTest` task, configure source sets and classpaths per project. Never assume the `IT` suffix is automatically picked up by every Gradle setup.

Command used in the project once properly configured:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

These commands are shown for learners; when writing Markdown in a documentation workflow, there is no need to run builds or Content QA.

## 10. Testing a Single Step with `JobLauncherTestUtils`

When a job has multiple steps such as `validateSourceStep -> importOrdersStep -> publishStep`, sometimes you only want to focus on `importOrdersStep`:

```java
JobExecution execution = jobs.launchStep(
        "importOrdersStep",
        params("orders-mixed.csv"));
```

`launchStep(...)` runs a single step in the test context created by Spring Batch Test rather than running the entire production flow every time. Keep in mind:

1. It **does not prove** preceding/following steps are orchestrated properly.
2. If the step depends on an `ExecutionContext` populated by a prior step, the test must provide the matching context data.
3. Verifying a step `COMPLETED` does not replace testing the full job, especially with quality gates/publishing.
4. Testing step scope and parameters still requires valid `JobParameters`.

With `@SpringBatchTest`, Spring Batch Test also provides `StepScopeTestUtils` and `JobScopeTestUtils` to test scoped beans in a simulated context. They are useful when beans use `@Value("#{jobParameters[...] }")`, `StepExecutionContext`, or `JobExecutionContext`. However, unit testing business rules usually **does not require** setting up a `StepScope`: extract business logic into plain Java classes like `OrderProcessor` and instantiate them directly.

## 11. Testing Errors, Rollbacks, and `FAILED` Properly

With chunk size 2, an exception near the end of the file can happen **after earlier chunks already committed**:

```text
Chunk #1 -> COMMIT
Chunk #2 -> COMMIT
Chunk #3 -> FAIL

JobExecution = FAILED
DB may still retain output from Chunk #1 and #2.
```

Never write tests assuming "if a job is `FAILED`, the target table must be empty" when the application writes per chunk transaction. That is a wrong expectation about transaction boundaries.

Instead, tests should assert explicitly:

- If output goes to **staging**, committed chunks may remain without being published.
- If the writer must be **idempotent**, retries/restarts must not create duplicates.
- If policy requires **batch-level all-or-nothing**, you need a publish gate or snapshot version; you cannot rely solely on a single chunk's transaction.
- If skips are configured, exceptions in reader/processor/writer may lead to `COMPLETED` with `skipCount > 0`, not automatically `FAILED`.

One way to build a controlled failure scenario is a test double throwing an exception only on a specific item/call. Do not rely on randomly shutting down the database or using `Thread.sleep(...)` to "wait for errors," as that creates flaky, hard-to-reproduce tests.

### 11.1. Avoid Asserting Only Exception Counts

In a fault-tolerant step, rollbacks and retries can invoke processor/writer callbacks multiple times. For example, `ItemProcessListener.onProcessError()` may log an event for a failed attempt even if the item later succeeds on retry. `SkipListener` reflects items actually skipped under the framework mechanism. Thus:

```text
Retry attempts != Skip count
Process error callback count != Number of finally rejected items
Rollback count != Number of invalid records
```

Tests should assert the **final outcome** via `StepExecution` counters, DB state, and the reject/audit store; if per-attempt counts are needed, use a dedicated counter in the test double or listener.

## 12. Testing Restart with the Same `JobInstance`

Restarts are far more important than simply re-calling a successful job.

```text
JobInstance(importOrdersJob, sourceBatchId=v1)
  ├── JobExecution #1: FAILED
  └── JobExecution #2: COMPLETED (restart)
```

Principles:

- Keep the **exact same identifying `JobParameters`** on restart. Changing `run.id` or an identifying `sourceBatchId` creates a new instance.
- Keep `JobRepository` metadata and the source data unchanged relative to checkpoints.
- Verify the writer and side effects can be re-executed without creating duplicates.
- If the source file was revised from v1 to v2, usually use a **new source version** and a replay workflow rather than applying old checkpoints to a different file.

### 12.1. Fail-Once Test Scenario

A small fixture can throw on the first run and succeed on restart:

```java
AtomicBoolean firstAttempt = new AtomicBoolean(true);

Tasklet failOnceTasklet = (contribution, chunkContext) -> {
    if (firstAttempt.getAndSet(false)) {
        throw new IllegalStateException("SIMULATED_TRANSIENT_FAILURE");
    }
    return RepeatStatus.FINISHED;
};
```

This is a **fixture snippet** to register in a dedicated `Step` in test configuration, not a standalone Java file. Import `AtomicBoolean`, `Tasklet`, and `RepeatStatus`. Never use an in-JVM boolean flag to manage real recovery; test doubles only simulate two deterministic outcomes.

A test launching with the same parameters looks like:

```java
JobParameters sameParams = new JobParametersBuilder()
        .addString("sourceBatchId", "restart-fixture-v1", true)
        .toJobParameters();

JobExecution first = launcher.run(failOnceJob, sameParams);
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);

JobExecution second = launcher.run(failOnceJob, sameParams);
assertThat(second.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(second.getJobInstance().getId())
        .isEqualTo(first.getJobInstance().getId());
assertThat(second.getId()).isNotEqualTo(first.getId());
```

This is an **integration test excerpt**: `launcher`, `failOnceJob`, and the `failOnceTasklet` bean must be configured in a test application context using a `JobRepository` that persists across both runs. Isolate parameters/metadata across test runs to avoid `JobInstanceAlreadyCompleteException` from prior tests.

For a file-reading job with checkpoints and a JDBC writer, a complete restart test must also verify:

1. Part of the data committed during the first execution.
2. The first execution `FAILED` at a deterministic point.
3. The new execution resumes only the remaining work per actual checkpointing.
4. No duplicate business keys exist and final output totals reconcile.
5. Published data (if any) appears only after the job completes and the quality gate passes.

## 13. Testing `@StepScope`, `JobParameters`, and Metadata

Some bugs appear only when Spring creates scoped beans at step execution time:

```java
@StepScope
@Bean
OrderProcessor orderProcessor(
        @Value("#{jobParameters['sourceBatchId']}")
        String sourceBatchId) { ... }
```

If writing a direct unit test `new OrderProcessor("fixture-batch")`, you checked business rules yet **did not** verify the SpEL expression reads the right parameter name. The integration test in Section 9 tests that path because it launches the job with `sourceBatchId`.

Test cases to include:

| Scenario | Expected Behavior |
| --- | --- |
| Valid `inputFile` and `sourceBatchId` | Step creates scoped beans and runs |
| Missing `sourceBatchId` | Step does not silently process with an empty key; fails clearly |
| Missing `inputFile` | Reader fails to open resource and job/step does not report success |
| Repeated identifying params after `COMPLETED` | Does not auto-create a new execution for the same instance |
| Different params for a new date or version | Creates a new `JobInstance` when identification rules change |
| `StepExecution` with exception | Persists status, counts, and appropriate failure details |

Do not indiscriminately wipe `JobRepository` just to "make tests pass easily." If metadata cleanup in an isolated H2 test is needed, use `JobRepositoryTestUtils` from `spring-batch-test` and ensure no executions are running. With parallel tests sharing a context/database, wiping the whole repository in one test can affect others; it is usually easier to **use distinct identifying params per test** or isolated databases/contexts.

## 14. Testing Dependencies and Production Conditions

### 14.1. DB-Specific Integration via Testcontainers

H2 does not faithfully emulate every PostgreSQL/MySQL feature. If production uses PostgreSQL, critical tests must run against real PostgreSQL or an equivalent container to verify:

- Unique constraints and upserts in the writer.
- Transaction isolation, locks, deadlocks, timeouts, and rollbacks.
- SQL dialects, data types, precision/scale, and timezones.
- Paging queries with stable `ORDER BY` on restart.
- Connection pool behavior under concurrency.

Testcontainers spins up an isolated database; configuration depends on library versions and CI environments supporting containers. You do not need to move **every unit test** onto Testcontainers: only integration tests relying on database semantics need it.

### 14.2. API Dependencies: Mock for Logic Tests, Stub Server for Contract Tests

If `ItemProcessor` calls a partner API:

- Unit tests: mock the gateway to verify requests, mapping, and exception classification.
- HTTP adapter integration tests: use a stub server with `200`, `400`, `429`, `503`, timeouts, and boundary payloads.
- Job tests: verify bounded retry policies, no retrying validation/permanent errors, and no skipping widespread outages.
- Side-effect tests: use a **stable idempotency key** and verify retries/restarts do not create duplicate transactions.

Never mock `JobRepository` in integration tests if the goal is to verify restarts or real metadata. A mocked repository hides real transactions, concurrency locks, and checkpoints.

### 14.3. Testing Business Outcomes, Not Just Framework Status

For critical data pipelines, add reconciliation:

```text
expected_source_count
  = accepted_count + rejected_count + filtered_count
```

This count check holds only if each source record is classified into exactly one group with no splitting/merging. With upserts, aggregations, or multiple output tables, use another reconciliation formula matching the business contract. Also check total amounts, unique keys, and source versions.

A job can be `COMPLETED` even after skipping items within `skipLimit`. If downstream cannot tolerate missing records, test that the **quality gate rejects publishing** when rejects exceed threshold, even though the import step could complete under fault-tolerance policy.

## 15. Test Independence and Stability

Common sources of flaky tests:

| Issue | Why It Breaks | Resolution |
| --- | --- | --- |
| Sharing identifying params across tests | Unexpected `JobInstanceAlreadyCompleteException` | Use distinct params; keep identical only in duplicate/restart tests |
| Shared database with global cleanup | One test deletes another test's metadata/output | Dedicated DB/schema; do not parallelize without isolation |
| Using `Thread.sleep()` to wait for async jobs | CI speed varies | `CountDownLatch` or polling with a bounded timeout |
| Checking exact `STARTING` right after async launch | Race condition; job may already be `STARTED` | Check valid status set or wait for final status |
| Relying on record order in multi-threaded steps | Completion order is not guaranteed | Compare results by key/set |
| Mocking writer yet trying to test commits | Mocks have no transactions | Integration test with a real DB |
| Not calling `close()` on reader | Resource leaks across tests | `try/finally`, explicit lifecycle |
| Treating H2 as identical to PostgreSQL | Different dialects/locks/isolation | Testcontainers for critical SQL/transactions |
| Asserting exception messages contain raw input | Risks leaking data in logs/test artifacts | Safe error codes and vetted fields |
| Checking only `COMPLETED` | Misses skips/filters/duplicates | Check `StepExecution` and output |

### 15.1. If a Job Is Launched Asynchronously

`JobLauncher.run(...)` with `ThreadPoolTaskExecutor` can return while the job is still `STARTING` or `STARTED`. Tests must not immediately assert `COMPLETED`. Poll `JobExplorer.getJobExecution(executionId)` until a terminal status with an explicit timeout, and fail if it times out.

```text
launch async
    |
    v
JobExecution id
    |
    +--> poll / JobExplorer
             |
             +-- STARTING / STARTED -> keep polling
             +-- COMPLETED ---------> verify output
             +-- FAILED / STOPPED --> inspect error path
```

When testing jobs via `JobLauncherTestUtils`, a synchronous launcher configuration is usually simpler and makes results deterministic. Use async tests only when **asynchronous behavior** itself is the requirement under test.

## 16. Running Tests in CI

A simple project workflow:

```text
Pull request
  |
  v
Compile + unit tests
  |
  +-- OrderProcessorTest
  +-- OrderReaderTest
  |
  v
Integration tests
  |
  +-- ImportOrdersJob test
  +-- Skip-limit failure test
  +-- Restart/idempotency test
  |
  v
Quality / security checks
  |
  v
Build artifact
```

In larger projects, you can split `test` and `integrationTest` into two Gradle tasks so fast unit tests run first and database/container tests run later. Regardless of how tasks are split, **verify that the CI report actually lists the integration test names**, avoiding a case where an `IT` suffix is missed by the `test` task.

Never commit real credentials or user data into fixtures. Use synthetic data only; if testing redaction/logging, use a synthetic test-only marker and assert it never appears in log output.

## 17. Extension Practice Tasks

After running the CSV → DB example, extend the exercises:

1. **Processor unit tests:** add checks for `null`, blank strings, unsupported statuses, very large amounts, and decimal precision per business rules.
2. **Reader unit tests:** use `@TempDir` to create missing-column files, empty files, and lines with Unicode characters, verifying parsing/EOF/resource lifecycle.
3. **Skip integration tests:** run a fixture with one invalid record and compare `readCount`, `processSkipCount`, `filterCount`, and `writeCount` against the output table.
4. **Threshold-exceeded integration test:** three invalid records with `skipLimit(2)` must mark the step/job `FAILED`; verify partial data is not published.
5. **Duplicate instance:** launch again with the same identifying parameters after `COMPLETED`, observing the `JobRepository` exception.
6. **Restart:** create a fail-once writer/tasklet, keep identifying params unchanged, and verify a new execution ID and duplicate-free output.
7. **Transactions:** intentionally fail the writer after several committed chunks; inspect staging data and per-chunk rollback behavior.
8. **Quarantine:** attach a `SkipListener` writing rejects with reason codes; match persistent reject counts against skip metadata.
9. **Data quality gate:** add an error-rate threshold requiring total records from a manifest and publishing only when reconciliation passes.
10. **SQL integration:** run the same job against PostgreSQL Testcontainers; test unique constraints, transactions, and restarts outside H2.
11. **Concurrency:** test a multi-threaded step with thread-safe reader/writer, verifying each business key is written once without relying on log order.
12. **Async launch:** if using a REST API, test that `202 Accepted` is only submission; poll to terminal status and verify failure outcomes too.

## 18. Summary

When writing Spring Batch tests, pick the **testing level matching what you need to prove**:

- **Unit tests** verify processor, mapper, and policy business rules quickly, independently, and reproducibly.
- **Integration tests** verify real step/job behavior, metadata, transactions, skips, restarts, and JDBC writers.
- **Output data** must be verified by business key, totals, and quality criteria, not only `BatchStatus`.
- **Restart/replay** must be tested with stable identifying parameters, immutable sources, and idempotent writers.
- **Test environments** must be isolated without wiping shared metadata or relying on arbitrary timing.

A good test suite does more than answer "did the job run?"—it answers **where every item went, what data committed, how failures recover, and when output is trustworthy for downstream consumers**.
