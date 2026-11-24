# Practice Project: Building a CSV-to-Database Job with Spring Batch

## 1. Objectives and Expected Outcomes

In this hands-on project, we build a complete **Spring Boot + Spring Batch** application to read orders from a CSV file, validate the data, and write valid records to a database using a **chunk-oriented step**. This is an end-to-end example covering everything from project structure to launching the job, inspecting output, handling errors, and testing restartability.

After completing this project, you will be able to:

1. Create a Spring Boot project with Spring Batch, JDBC, and H2 dependencies.
2. Define business tables and Spring Batch metadata tables.
3. Read CSV records item by item using `FlatFileItemReader`.
4. Validate and transform data using `ItemProcessor`.
5. Write batches to the database using `JdbcBatchItemWriter`.
6. Create a `Step` with `chunk(size, transactionManager)` and assemble it into a `Job`.
7. Accept `inputFile` and `businessDate` via `JobParameters` instead of hardcoding inputs.
8. Run the job and inspect `BatchStatus`, step counters, and output table data.
9. Write tests with `spring-batch-test` to handle schema mismatches and business validation errors.
10. Explain restartability, checkpoints, and idempotency to scale the demo into a production-ready system.

**Technical scope:** This example uses Java 17, Spring Boot 3.x, Spring Batch 5.x, and Maven. The Maven parent version is specified as an illustrative version for the Boot 3 branch; if your project uses a different Boot/Spring Batch version, keep the dependencies and APIs compatible. In-memory H2 is used for learning and testing, **not as a persistent metadata storage configuration for production**.

## 2. Business Problem

The system receives a daily order file:

```text
inbound/orders-2026-11-16.csv
```

CSV content:

```csv
order_id,customer_code,amount,order_date
ORD-001,C001,120.50,2026-11-16
ORD-002,C002,45.00,2026-11-16
ORD-003,C001,399.90,2026-11-16
ORD-004,C003,12.75,2026-11-16
ORD-005,C004,80.00,2026-11-16
```

Processing rules:

- The header must exactly match `order_id,customer_code,amount,order_date`.
- The file resides in a server-configured inbound directory; arbitrary path access is not allowed.
- `order_id` and `customer_code` must not be blank.
- `amount` must be greater than 0.
- `order_date` must equal the job's `businessDate`.
- Each `order_id` appears only once in the target table; the database enforces this via the primary key.
- On validation errors, the initial version of this practice project **fails fast** instead of silently skipping items.
- With valid data, the job finishes with `COMPLETED` and writes all five rows.

Expected output:

| order_id | customer_code | amount | order_date |
| --- | --- | ---: | --- |
| ORD-001 | C001 | 120.50 | 2026-11-16 |
| ORD-002 | C002 | 45.00 | 2026-11-16 |
| ORD-003 | C001 | 399.90 | 2026-11-16 |
| ORD-004 | C003 | 12.75 | 2026-11-16 |
| ORD-005 | C004 | 80.00 | 2026-11-16 |

## 3. Overall Job Architecture

```text
                 CLI / Scheduler
                       |
                       v
             JobParametersValidator
             - inputFile required
             - businessDate yyyy-MM-dd
                       |
                       v
                  importOrdersJob
                       |
                       v
                preflightStep
                   (Tasklet)
              - approved input root
              - file exists/readable
              - header/size checks
                       |
                       v
               importOrdersStep
              (chunk-oriented)
                       |
               FlatFileItemReader
                       |
                OrderCsvRow
                       |
                 ItemProcessor
           - validate order fields
           - validate businessDate
                       |
                 ImportedOrder
                       |
                JdbcBatchItemWriter
                       |
                  H2 database
                       |
                 commit per chunk
```

This example intentionally combines **tasklet** and **chunk** steps:

- `preflightStep` validates a single file before processing. Because the task has a clear, single-unit scope, a tasklet is used.
- `importOrdersStep` iterates over records and requires grouped transactions and checkpoints, so a chunk-oriented step is used.

If preflight fails, the import step must not run in the normal success flow. When an import chunk fails, previously committed chunks may still remain in the database; therefore, **primary keys, input snapshots, and repository state** are critical for restarts.

## 4. Environment Setup and Project Structure

Requirements:

- JDK 17 or any JDK supported by Spring Boot 3.x.
- Maven 3.9 or the corresponding Maven Wrapper.
- An IDE with Java and Spring Boot support.
- No PostgreSQL installation is required for the in-memory H2 version.

Directory structure:

```text
orders-csv-batch/
├── pom.xml
├── inbound/
│   └── orders-2026-11-16.csv
├── src/
│   ├── main/
│   │   ├── java/com/example/ordersbatch/
│   │   │   ├── OrdersBatchApplication.java
│   │   │   ├── BatchCommandRunner.java
│   │   │   ├── config/
│   │   │   │   └── OrderImportConfiguration.java
│   │   │   ├── input/
│   │   │   │   └── ApprovedInputResolver.java
│   │   │   ├── model/
│   │   │   │   ├── OrderCsvRow.java
│   │   │   │   └── ImportedOrder.java
│   │   │   └── validation/
│   │   │       ├── InvalidOrderException.java
│   │   │       └── ImportParametersValidator.java
│   │   └── resources/
│   │       ├── application.yml
│   │       └── schema.sql
│   └── test/
│       ├── java/com/example/ordersbatch/
│       │   ├── OrderImportJobIT.java
│       │   └── ImportParametersValidatorTest.java
│       └── resources/inbound/
│           ├── orders-test.csv
│           └── orders-bad-header.csv
```

The class and file names in this lesson belong to a standalone sample project; they do not require reading or modifying any other Spring Batch projects.

## 5. Declaring Dependencies in pom.xml

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-csv-batch</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>orders-csv-batch</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-batch</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.batch</groupId>
            <artifactId>spring-batch-test</artifactId>
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
```

Role of each dependency:

| Dependency | Purpose |
| --- | --- |
| `spring-boot-starter-batch` | Spring Batch runtime, Job/Step, JobRepository, reader/writer builders |
| `spring-boot-starter-jdbc` | `DataSource`, `JdbcTemplate`, transaction JDBC |
| `h2` | Embedded database for demo and testing |
| `spring-boot-starter-test` | JUnit 5, assertions, and Spring Boot test utilities |
| `spring-batch-test` | `@SpringBatchTest`, `JobLauncherTestUtils`, and batch testing utilities |

The Boot parent manages dependency versions through dependency management. Do not force an incompatible Spring Batch version into a starter without checking compatibility. In production projects, use a supported Boot 3.x version according to your organization's policy; version `3.3.5` here is only an illustrative milestone to demonstrate Spring Batch 5.x APIs.

## 6. Configuring DataSource, Spring Batch, and Schema

### 6.1. application.yml

Create `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: orders-csv-batch
  datasource:
    url: jdbc:h2:mem:orders_demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  batch:
    input-root: ./inbound

logging:
  level:
    org.springframework.batch: INFO
    com.example.ordersbatch: INFO
```

Explanation:

- `jdbc:h2:mem:orders_demo` creates an in-memory database. When the JVM exits, the metadata and output tables **disappear**. This is simple for a tutorial, but not a choice for production jobs that need to restart across processes.
- `DB_CLOSE_DELAY=-1` keeps the in-memory database alive when the last connection closes while the JVM is still running.
- `spring.sql.init.mode=always` allows Spring Boot to run `schema.sql` to create the business table.
- `spring.batch.jdbc.initialize-schema=always` creates the `BATCH_*` metadata tables on the fresh demo database.
- `spring.batch.job.enabled=false` prevents Boot from auto-launching jobs by default; in this lesson, we use an `ApplicationRunner` to explicitly accept CLI arguments and run a single job.
- `app.batch.input-root` defines the server-side input root. Callers may only provide **relative file names** within this root.

Do not set `initialize-schema=always` as shown above on a production database that already holds metadata if schema initialization could conflict. In production, use schema migration (Flyway/Liquibase or a DBA process) for both business tables and Spring Batch metadata tables.

### 6.2. schema.sql

Create `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS imported_order (
    order_id       VARCHAR(80) PRIMARY KEY,
    customer_code  VARCHAR(80) NOT NULL,
    amount         DECIMAL(18, 2) NOT NULL,
    order_date     DATE NOT NULL,
    imported_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

`order_id` is the primary key to prevent writing the same order code multiple times. `DECIMAL(18,2)` suits monetary amounts with exact two decimal places; the Java application uses `BigDecimal`, never `double`, for monetary calculations.

**Two distinct table groups:**

1. `imported_order` is the **business table** defined by `schema.sql`.
2. `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, the `ExecutionContext` tables, and related sequences are **Spring Batch metadata**, initialized by the framework's schema.

Do not arbitrarily modify or delete batch metadata just to "re-run" a job, because it is used to identify `JobInstance`, track status history, and support restarts.

## 7. Creating the Spring Boot Main Class

`src/main/java/com/example/ordersbatch/OrdersBatchApplication.java`:

```java
package com.example.ordersbatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersBatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersBatchApplication.class, args);
    }
}
```

`@SpringBootApplication` automatically discovers `@Configuration` and components under the `com.example.ordersbatch` subpackage. You do not need to manually build a `JobRepository` if auto-configuration already provides one compatible with your `DataSource` and Spring Batch version.

## 8. Models: Separating CSV Records from Database Entities

### 8.1. OrderCsvRow.java

```java
package com.example.ordersbatch.model;

import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderCsvRow(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDate orderDate
) {}
```

`OrderCsvRow` represents data converted from CSV to Java by the parser. It does not need to be a JPA entity and requires no ORM annotations. Using a `record` creates a concise, immutable data object.

### 8.2. ImportedOrder.java

```java
package com.example.ordersbatch.model;

import java.math.BigDecimal;
import java.time.LocalDate;

public record ImportedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDate orderDate
) {}
```

In this simple example, both types share the same fields but have **different roles**:

- `OrderCsvRow`: raw input data from the file, which may not have been validated yet.
- `ImportedOrder`: a record validated and normalized by the processor, eligible to be passed to the writer.

In a real-world application, the output type may also include a source ID, version, business timestamp, or customer lookup information.

## 9. Defining Data Validation Exceptions for the Processor

`src/main/java/com/example/ordersbatch/validation/InvalidOrderException.java`:

```java
package com.example.ordersbatch.validation;

public final class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Using a dedicated exception helps distinguish **data errors** from **infrastructure/bug errors**. In the initial version of the project, any validation error causes the step to end as `FAILED`; the extension section demonstrates how to allow controlled skips.

## 10. Validating JobParameters Before Launch

A file-import batch job must know **which file it is processing and for which business period**. Two parameters:

```text
inputFile=orders-2026-11-16.csv
businessDate=2026-11-16
```

In Spring Batch 5.x, we can implement `JobParametersValidator`.

`src/main/java/com/example/ordersbatch/validation/ImportParametersValidator.java`:

```java
package com.example.ordersbatch.validation;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class ImportParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters == null) {
            throw new JobParametersInvalidException(
                    "JobParameters must not be null");
        }

        String inputFile = parameters.getString("inputFile");
        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFile is required");
        }

        String dateText = parameters.getString("businessDate");
        if (dateText == null || dateText.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        try {
            LocalDate.parse(dateText);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use yyyy-MM-dd");
        }
    }
}
```

This validator checks **parameter formatting** without opening the file. This is intentional: I/O operations such as file and schema checks should live in `preflightStep` so they appear as a trackable `StepExecution` with its own status.

Job parameters can contain both instance-identifying information and supplementary parameters. Only parameters marked as **identifying** determine the identity of a `JobInstance`; keep them stable when you need to restart the same instance.

## 11. Restricting Input Paths to the Inbound Directory

You should not construct a `FileSystemResource` directly from an arbitrary absolute path passed by the caller. In this project, the caller may only pass a relative name. `ApprovedInputResolver` resolves the path under the configured root and checks that symlinks do not point outside the root.

`src/main/java/com/example/ordersbatch/input/ApprovedInputResolver.java`:

```java
package com.example.ordersbatch.input;

import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class ApprovedInputResolver {

    private final Path inputRoot;

    public ApprovedInputResolver(
            @Value("${app.batch.input-root}") String configuredRoot)
            throws IOException {

        inputRoot = Path.of(configuredRoot).toRealPath();
        if (!Files.isDirectory(inputRoot)) {
            throw new IllegalStateException(
                    "Input root must be a directory");
        }
    }

    public Path resolve(String inputFile) throws IOException {
        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("inputFile is required");
        }

        Path supplied = Path.of(inputFile);
        if (supplied.isAbsolute()) {
            throw new SecurityException(
                    "Absolute input path is not allowed");
        }

        Path candidate = inputRoot.resolve(supplied).normalize();
        if (!candidate.startsWith(inputRoot)) {
            throw new SecurityException("Input path escapes inbound root");
        }

        Path realFile = candidate.toRealPath();
        if (!realFile.startsWith(inputRoot)) {
            throw new SecurityException("Input symlink escapes inbound root");
        }
        if (!Files.isRegularFile(realFile)) {
            throw new IllegalArgumentException(
                    "Input is not a regular file");
        }
        if (!Files.isReadable(realFile)) {
            throw new AccessDeniedException(realFile.toString());
        }
        return realFile;
    }
}
```

**Why must the input root be protected?** A job often runs with a service account that has access to many internal files. If a caller could supply `../../secrets/file`, reading the input could become a path traversal vulnerability.

**Limitation of this example:** `toRealPath()` and `Files.isReadable()` check the state at the current point in time. If another party has permission to replace the file or symlink before the reader opens it, a *time of check vs time of use* (TOCTOU) race can occur. In production, use an immutable staging snapshot, restrict producer write permissions, and attach a version/hash to the source identity.

Create the `inbound/` directory before running the application because the resolver checks it during bean initialization.

## 12. OrderImportConfiguration: Creating the Job and Two Steps

This is the central configuration file of the practice project:

```text
config/OrderImportConfiguration.java
    ├── preflightTasklet(...)
    ├── preflightStep(...)
    ├── orderReader(...)
    ├── orderProcessor(...)
    ├── orderWriter(...)
    ├── importOrdersStep(...)
    └── importOrdersJob(...)
```

For clarity, the snippets below belong to the same `@Configuration` class; when creating the actual file, combine them **into one class** with shared imports.

### 12.1. Class Skeleton and Imports

`src/main/java/com/example/ordersbatch/config/OrderImportConfiguration.java`:

```java
package com.example.ordersbatch.config;

import com.example.ordersbatch.input.ApprovedInputResolver;
import com.example.ordersbatch.model.ImportedOrder;
import com.example.ordersbatch.model.OrderCsvRow;
import com.example.ordersbatch.validation.ImportParametersValidator;
import com.example.ordersbatch.validation.InvalidOrderException;
import java.io.BufferedReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import javax.sql.DataSource;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportConfiguration {
    // Paste the @Bean methods from the following sections here.
}
```

The following snippets are **method definitions inside the class**, not standalone Java files. Do not create multiple `OrderImportConfiguration` classes with the same name.

### 12.2. preflightTasklet: Checking the File Before Import

Add to `OrderImportConfiguration`:

```java
@Bean
@StepScope
public Tasklet preflightTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) {

    return (contribution, context) -> {
        Path file = resolver.resolve(inputFile);

        if (Files.size(file) == 0) {
            throw new IllegalStateException("Input file is empty");
        }

        try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {

            String header = reader.readLine();
            if (!"order_id,customer_code,amount,order_date".equals(header)) {
                throw new IllegalStateException("Unexpected CSV header");
            }
            if (reader.readLine() == null) {
                throw new IllegalStateException("CSV contains no data rows");
            }
        }

        return RepeatStatus.FINISHED;
    };
}
```

Preflight:

- Retrieves the file name from job parameters when the step executes.
- Passes the file through the resolver to restrict read scope.
- Rejects empty files or files with an incorrect header.
- Requires at least one line after the header.
- Returns `RepeatStatus.FINISHED` to allow the flow to continue when valid.

The code uses exact header comparison per the demo contract. Files with a UTF-8 BOM or headers with different whitespace will be rejected; if business rules allow, you can normalize BOMs or use a CSV parser for advanced schema validation. Checking that "a line exists after the header" does not guarantee that line contains valid data; per-record validation is handled by the reader and processor.

### 12.3. preflightStep

```java
@Bean
public Step preflightStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet preflightTasklet) {

    return new StepBuilder("preflightStep", jobRepository)
            .tasklet(preflightTasklet, transactionManager)
            .build();
}
```

A tasklet is appropriate because it checks **a single resource** without iterating over items. If an exception occurs in preflight, the step typically ends as `FAILED` and the import step does not run under the default flow.

### 12.4. FlatFileItemReader: Reading CSV into OrderCsvRow

```java
@Bean
@StepScope
public FlatFileItemReader<OrderCsvRow> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) throws Exception {

    Path approved = resolver.resolve(inputFile);

    return new FlatFileItemReaderBuilder<OrderCsvRow>()
            .name("orderCsvReader")
            .resource(new FileSystemResource(approved))
            .strict(true)
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("order_id", "customer_code", "amount", "order_date")
            .fieldSetMapper(fields -> new OrderCsvRow(
                    fields.readString("order_id"),
                    fields.readString("customer_code"),
                    fields.readBigDecimal("amount"),
                    LocalDate.parse(fields.readString("order_date"))
            ))
            .build();
}
```

**How it works:**

1. `FlatFileItemReader` opens the resource when the step starts.
2. `linesToSkip(1)` skips the header already verified by preflight.
3. The delimited tokenizer splits the CSV fields according to the configuration.
4. `FieldSetMapper` maps each line into an `OrderCsvRow`.
5. The reader supplies one item per `read()` call to Spring Batch, returning `null` at the end of the file.

`name("orderCsvReader")` saves the reader's state in `ExecutionContext` for restarts. `strict(true)` requires throwing an error when the resource is missing; do not disable strict mode just to prevent the job from failing if a file is lost.

**Parser errors vs. processor errors:** If `amount` contains the string `abc` or an unparseable date, the error may occur inside `FieldSetMapper` during reading, **before the processor receives the item**. Therefore, when analyzing metadata, distinguish `readSkipCount` from `processSkipCount`.

### 12.5. ItemProcessor: Validation and Normalization

```java
@Bean
@StepScope
public ItemProcessor<OrderCsvRow, ImportedOrder> orderProcessor(
        @Value("#{jobParameters['businessDate']}") String businessDateText) {

    LocalDate businessDate = LocalDate.parse(businessDateText);

    return row -> {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("order_id is required");
        }
        if (row.customerCode() == null
                || row.customerCode().isBlank()) {
            throw new InvalidOrderException(
                    "customer_code is required for " + row.orderId());
        }
        if (row.amount() == null
                || row.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderException(
                    "amount must be positive for " + row.orderId());
        }
        if (!businessDate.equals(row.orderDate())) {
            throw new InvalidOrderException(
                    "order_date does not match businessDate for "
                            + row.orderId());
        }

        return new ImportedOrder(
                row.orderId().strip(),
                row.customerCode().strip(),
                row.amount().setScale(2),
                row.orderDate()
        );
    };
}
```

Because the processor returns `ImportedOrder`, the item proceeds to the writer. If it returns `null`, Spring Batch treats that as an **intentional filter**, not a failure. In this project, data violating the contract throws `InvalidOrderException` so the job fails rather than silently dropping records.

`setScale(2)` uses the default rounding mode `UNNECESSARY`: if `amount` has more than two decimal places and cannot be represented exactly at scale 2, Java may throw an `ArithmeticException`. This is an intentional choice for a demo requiring monetary precision; when the business contract allows rounding, specify an explicit `RoundingMode`.

### 12.6. JdbcBatchItemWriter: Writing Multiple Items in a Transaction

```java
@Bean
public JdbcBatchItemWriter<ImportedOrder> orderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ImportedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order
                    (order_id, customer_code, amount, order_date)
                VALUES
                    (:orderId, :customerCode, :amount, :orderDate)
                """)
            .itemSqlParameterSourceProvider(row ->
                    new MapSqlParameterSource()
                            .addValue("orderId", row.orderId())
                            .addValue("customerCode", row.customerCode())
                            .addValue("amount", row.amount())
                            .addValue("orderDate", row.orderDate()))
            .build();
}
```

The writer uses `MapSqlParameterSource` instead of relying on JavaBeans property mapping for a `record`. This makes it explicit which fields are bound to SQL, which is useful when database column names differ from model field names.

`JdbcBatchItemWriter` can group statements into a JDBC batch to optimize round-trips. On duplicate `order_id`, the database raises a primary key error, and the corresponding chunk may roll back. **A primary key does not automatically create an upsert policy**: if you want to accept duplicate files or handle versioned data, design that explicitly.

### 12.7. Chunk Step

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderCsvRow> orderReader,
        ItemProcessor<OrderCsvRow, ImportedOrder> orderProcessor,
        JdbcBatchItemWriter<ImportedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderCsvRow, ImportedOrder>chunk(3, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

We chose `chunk(3)` to make behavior easy to observe in this practice project. With five valid items:

```text
Chunk 1: ORD-001, ORD-002, ORD-003 -> COMMIT
Chunk 2: ORD-004, ORD-005          -> COMMIT
```

In production, the chunk size usually needs to be larger and tuned against throughput, transaction latency, memory, and rollback scope; there is no single universal optimal value.

**Transactions matter:** If the fourth item causes an error and no skip policy is configured, the first committed chunk may still persist. When re-running, you must restart the exact `JobInstance` and preserve metadata; do not simply create a new job against the same table with a primary key and expect the system to skip old data automatically.

### 12.8. Assembling the Job and Registering the Validator

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step preflightStep,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(new ImportParametersValidator())
            .start(preflightStep)
            .next(importOrdersStep)
            .build();
}
```

The job runs preflight first, then imports if preflight succeeds. `validator(...)` validates `inputFile`/`businessDate` against the contract, while preflight's `StepExecution` records the actual resource check.

## 13. Launching the Job from the Command Line

Because `spring.batch.job.enabled=false`, Spring Boot does not automatically run the job. We add an `ApplicationRunner` to accept the two options for this example, convert them into `JobParameters`, and invoke `JobLauncher`.

`src/main/java/com/example/ordersbatch/BatchCommandRunner.java`:

```java
package com.example.ordersbatch;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class BatchCommandRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(BatchCommandRunner.class);

    private final JobLauncher launcher;
    private final Job importOrdersJob;

    public BatchCommandRunner(
            JobLauncher launcher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.launcher = launcher;
        this.importOrdersJob = importOrdersJob;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        // In SpringBootTest, these options are not passed:
        // only the context is loaded, without auto-launching the job.
        if (!args.containsOption("inputFile")
                && !args.containsOption("businessDate")) {
            return;
        }

        String inputFile = required(args, "inputFile");
        String businessDate = required(args, "businessDate");

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", inputFile, true)
                .addString("businessDate", businessDate, true)
                .toJobParameters();

        JobExecution execution = launcher.run(importOrdersJob, params);
        log.info("Job execution id={}, status={}",
                execution.getId(), execution.getStatus());

        if (execution.getStatus() != BatchStatus.COMPLETED) {
            throw new IllegalStateException(
                    "Import job did not complete: "
                            + execution.getStatus());
        }
    }

    private static String required(
            ApplicationArguments args, String name) {

        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0) == null
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Required CLI option --" + name + "=value");
        }
        return values.get(0);
    }
}
```

The two parameters marked `true` are **identifying parameters**. The job name together with the set of identifying parameters determines the `JobInstance`. When restarting a failed instance, you must use the same identity; changing `businessDate` or `inputFile` launches a different logical unit of work.

**Synchronous launcher assumption:** The runner above checks `JobExecution.getStatus()` immediately after `launch(...)`. In a typical Spring Batch setup with a synchronous launcher, the call returns after the job has finished. If a project switches to an asynchronous launcher, the runner must wait for or observe the execution via `JobExplorer` or an appropriate orchestration mechanism before concluding the status; never inspect an unfinished status and report a false failure.

In production, the job can be invoked via `JobOperator`, a scheduler, an orchestration platform, or a message trigger. The CLI runner here serves the lesson and keeps launch conditions explicit.

## 14. Running the Project

### 14.1. Preparing the File

Create the `inbound` directory at the project root and save:

```text
inbound/orders-2026-11-16.csv
```

with the exact CSV content from Section 2. The file should use UTF-8, comma as the delimiter, and no BOM in this example. The `./inbound` root is resolved relative to the process's working directory.

### 14.2. Build and Run

The commands below are instructions for learners to execute in the sample project (not build output already executed in this article):

```bash
mvn clean package
java -jar target/orders-csv-batch-0.0.1-SNAPSHOT.jar \
  --inputFile=orders-2026-11-16.csv \
  --businessDate=2026-11-16
```

On PowerShell, you can write this on one line:

```powershell
java -jar target/orders-csv-batch-0.0.1-SNAPSHOT.jar --inputFile=orders-2026-11-16.csv --businessDate=2026-11-16
```

Do not pass `/srv/...` or a path outside `inbound`, because `ApprovedInputResolver` intentionally rejects absolute paths and traversal.

### 14.3. Expected Output

When the file and configuration are valid:

```text
importOrdersJob
  preflightStep      COMPLETED
  importOrdersStep   COMPLETED

JobExecution status = COMPLETED
readCount  = 5
writeCount = 5
filterCount = 0
skipCount  = 0
```

Exact log lines may vary by version and logging pattern. Do not test by comparing framework logs verbatim; focus on statuses, metadata, and database contents.

Because H2 runs in memory, once the `java -jar` process exits, the demo database disappears. To inspect rows with SQL, add an integration test using `JdbcTemplate`, or open an H2 console/query **within the same JVM** using an appropriate mechanism. Do not expect a connection from a new H2 process to see data again after the old JVM has shut down.

## 15. Inspecting Data and Metadata

After the job runs successfully in an active JVM, query:

```sql
SELECT order_id, customer_code, amount, order_date
FROM imported_order
ORDER BY order_id;
```

Five rows from Section 2 are expected. You can verify the row count:

```sql
SELECT COUNT(*) AS total_orders
FROM imported_order;
```

Expected: `total_orders = 5`.

### 15.1. Spring Batch Metadata

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
ORDER BY je.JOB_EXECUTION_ID DESC;
```

And the step statuses:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

For `preflightStep`, read/write counters typically do not represent CSV record counts because it is a tasklet. The 5 read / 5 write counts belong to `importOrdersStep`.

### 15.2. Why Are Both Metadata and Business Tables Needed?

`BatchStatus.COMPLETED` indicates that the step/job completed according to the flow, but it does not by itself prove the business data is correct. The reader may filter/skip items, the writer may upsert, or the database may have triggers. Therefore, both are needed:

- **Job/Step metadata:** status, timestamps, read/write/skip/filter counts.
- **Target table data:** actual row counts, business keys, monetary amounts/dates.
- **Reconciliation:** record counts per manifest and total amount if required by the input contract.

## 16. Unit Testing the Job Validator

Create `src/test/java/com/example/ordersbatch/ImportParametersValidatorTest.java`:

```java
package com.example.ordersbatch;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.ordersbatch.validation.ImportParametersValidator;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;

class ImportParametersValidatorTest {

    private final ImportParametersValidator validator =
            new ImportParametersValidator();

    @Test
    void acceptsCorrectParameters() {
        var params = new JobParametersBuilder()
                .addString("inputFile", "orders-2026-11-16.csv")
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        assertDoesNotThrow(() -> validator.validate(params));
    }

    @Test
    void rejectsMissingInputFile() {
        var params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        assertThrows(JobParametersInvalidException.class,
                () -> validator.validate(params));
    }

    @Test
    void rejectsWrongDateFormat() {
        var params = new JobParametersBuilder()
                .addString("inputFile", "orders.csv")
                .addString("businessDate", "16/11/2026")
                .toJobParameters();

        assertThrows(JobParametersInvalidException.class,
                () -> validator.validate(params));
    }
}
```

This is a pure Java unit test; no database or Spring context is needed. It verifies the `JobParameters` contract before running the job.

## 17. Integration Test: Running the Job and Checking the Database

To truly test through the reader, processor, writer, `JobRepository`, and transactions, use `@SpringBatchTest` with `@SpringBootTest`.

### 17.1. Preparing Fixtures

Create `src/test/resources/inbound/orders-test.csv`:

```csv
order_id,customer_code,amount,order_date
TEST-001,C001,100.00,2026-11-16
TEST-002,C002,250.50,2026-11-16
TEST-003,C003,30.25,2026-11-16
```

Create `src/test/resources/inbound/orders-bad-header.csv`:

```csv
order_id,wrong_customer_column,amount,order_date
BAD-001,C001,100.00,2026-11-16
```

`@SpringBootTest` will use `app.batch.input-root=src/test/resources/inbound` for tests, instead of files in the production/demo directory. There is no need to modify main resources during testing.

### 17.2. Integration Test Class

`src/test/java/com/example/ordersbatch/OrderImportJobIT.java`:

```java
package com.example.ordersbatch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "app.batch.input-root=src/test/resources/inbound",
        "spring.datasource.url=jdbc:h2:mem:orders_test;DB_CLOSE_DELAY=-1"
})
class OrderImportJobIT {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void clearBusinessOutput() {
        jdbc.update("DELETE FROM imported_order");
    }

    private JobParameters params(String file) {
        return new JobParametersBuilder()
                .addString("inputFile", file)
                .addString("businessDate", "2026-11-16")
                .addString("testExecution", UUID.randomUUID().toString())
                .toJobParameters();
    }

    @Test
    void importsThreeCsvOrders() throws Exception {
        JobExecution execution =
                launcher.launchJob(params("orders-test.csv"));

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
                .filter(s -> s.getStepName().equals("importOrdersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(3, step.getReadCount());
        assertEquals(3, step.getWriteCount());
        assertEquals(0, step.getSkipCount());

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_order", Long.class);
        assertEquals(3L, count);

        String amount = jdbc.queryForObject(
                "SELECT CAST(amount AS VARCHAR) "
                        + "FROM imported_order WHERE order_id = ?",
                String.class,
                "TEST-002");
        assertTrue(amount.startsWith("250.5"));
    }

    @Test
    void badHeaderStopsJobBeforeImport() throws Exception {
        JobExecution execution =
                launcher.launchJob(params("orders-bad-header.csv"));

        assertEquals(BatchStatus.FAILED, execution.getStatus());
        assertTrue(execution.getStepExecutions().stream()
                .anyMatch(s -> s.getStepName().equals("preflightStep")
                        && s.getStatus() == BatchStatus.FAILED));
        assertTrue(execution.getStepExecutions().stream()
                .noneMatch(s -> s.getStepName().equals("importOrdersStep")));

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_order", Long.class);
        assertEquals(0L, count);
    }
}
```

**Explanation of test choices:**

- `@SpringBatchTest` sets up the test infrastructure for launching jobs and reading metadata.
- `@SpringBootTest` boots the real application with the test database configuration and test input root.
- `spring.batch.job.enabled=false` prevents Spring Boot from auto-running any job when the context starts.
- `BatchCommandRunner` also does not auto-launch because the test does not pass the two CLI options from the demo.
- A random `testExecution` creates a distinct identity for each **independent test**, avoiding `JobInstance` collisions across test runs. **Do not use this random parameter when testing restarts of the same instance**, because a restart must preserve the original identity.
- `DELETE FROM imported_order` clears the **business table** before each test. The metadata tables still keep separate executions; this is an independent testing scenario, not a restart.

The snippet asserting monetary amounts converts `DECIMAL` to strings merely to illustrate an output check. In a real system, use `BigDecimal` via JDBC and `compareTo(...)` or `assertEquals` after normalizing scale to verify monetary values more cleanly.

**Note on Maven Surefire:** Maven Surefire recognizes names like `*Test.java` by default, whereas classes ending in `*IT.java` may not be run by `mvn test` unless the Failsafe plugin or an include pattern is configured. To have `mvn test` run this integration class immediately in the demo, you can rename the file/class to `OrderImportJobTest`. If keeping the `IT` suffix, configure `maven-failsafe-plugin` and run the `verify` phase.

Example Failsafe configuration in `pom.xml` (placed inside `<plugins>`):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Learners can then run `mvn verify` to execute both unit and integration tests in the Maven lifecycle. Running these build commands is not required to understand the contract of this lesson.

## 18. Testing Failure Scenarios

Create different test files and inspect the exact statuses:

| Input data | Where error occurs | Expected result |
| --- | --- | --- |
| Missing file | Resolver or preflight | Step `preflightStep FAILED`, no output |
| Invalid header | Preflight | Job `FAILED`, import does not run |
| Header-only file | Preflight | Rejected due to no data rows |
| `amount=abc` | Reader/FieldSetMapper | `importOrdersStep FAILED` during parsing |
| `amount=-1` | Processor | `InvalidOrderException`, step fails |
| Malformed `order_date` | Reader | Parse error, step fails |
| `order_date` differs from businessDate | Processor | Validation fails |
| Duplicate `order_id` within one file | Writer/database | Primary key conflict, chunk fails |
| Path `../secret.txt` | Resolver | Security rejection before reading |
| All records valid | Reader → processor → writer | `COMPLETED`, output matches input |

### 18.1. Processor Error in the Second Chunk

With `chunk(3)` and a five-record file:

```text
1: ORD-001 OK
2: ORD-002 OK
3: ORD-003 OK
4: ORD-004 amount=-10
5: ORD-005 OK
```

General behavior in a fail-fast configuration with standard JDBC transactions:

```text
Chunk 1: ORD-001..003 -> COMMIT
Chunk 2: ORD-004     -> processor throws InvalidOrderException
         chunk transaction does not complete
Step: FAILED
```

When inspecting the target table, you will typically still see the three rows from the first chunk. However, do not infer solely from the `FAILED` status that there are always exactly three rows in every configuration: the datasource, transaction manager, writer side effects, or retry strategy can change the outcome. Always verify the actual database and `StepExecution`.

### 18.2. Distinguishing Filter, Skip, and Failure

- `processor.process(...)` returns an object: the item is passed to the writer.
- `processor.process(...)` returns `null`: the item is **filtered**, incrementing `filterCount`.
- Processor throws an exception that is not handled: the step may become **FAILED**.
- Processor throws a skippable exception: increments `processSkipCount` according to the fault-tolerant policy.

Do not catch all exceptions and `return null`: doing so hides data errors and causes the job to report success even though records were lost.

## 19. Extension: Allowing Controlled Skips

In the first version, a single invalid record fails the job. If the data contract allows accepting valid records and rejecting invalid rows, configure a **fault-tolerant step**.

Example replacing the `importOrdersStep` builder snippet:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderCsvRow, ImportedOrder>chunk(3, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(2)
        .build();
```

While within the limit, an item throwing `InvalidOrderException` can be skipped and the step continues. **Only the configured exception type is allowed to be skipped**. `skipLimit(2)` is a step-level limit, not per chunk. If more errors occur than the limit allows, the step fails.

If the reader fails to parse `amount=abc`, the exception might not be `InvalidOrderException`, so the job still fails. To skip read errors, you must design a matching policy, and preferably add a `SkipListener`/quarantine so data is not dropped without a trace.

Example listener:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class OrderSkipListener
        implements SkipListener<OrderCsvRow, ImportedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInProcess(OrderCsvRow item, Throwable error) {
        log.warn("Skipping orderId={}, reason={}",
                item.orderId(), error.getClass().getSimpleName());
    }
}
```

Register it with `.listener(new OrderSkipListener())` in the step configuration. When auditing real data, do not log sensitive full payloads or exception messages containing personal data; use error categories and allowed business keys.

**Important:** Skipping is not suitable for every business domain. For financial reconciliation where not a single transaction may be missing, the right policy may be to **fail the entire batch**, move it into a remediation state, and reprocess it after approval.

## 20. Retry and Infrastructure Errors

A data error like a negative amount or invalid date will generally not become valid by retrying the same item. However, transient network timeouts or database deadlocks may warrant bounded retries.

For an external dependency used by the processor, you can define an exception type such as:

```java
public final class TemporaryCatalogException extends RuntimeException {
    public TemporaryCatalogException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Then configure the chunk:

```java
.faultTolerant()
.retry(TemporaryCatalogException.class)
.retryLimit(3)
```

The snippet above is a continuation of the builder, not a standalone statement. Choose specific exception types, timeouts, and backoff according to the downstream system. Do not configure `retry(Exception.class)` for all errors: retrying bugs or invalid inputs causes futile loops and increases system load.

**Processor idempotency:** Rollbacks and retries can cause an item to be processed multiple times. Therefore, avoid having the processor call payment-creation APIs, send emails, or write non-idempotent state. In this demo, the processor only validates and transforms data, while the JDBC writer writes within the chunk transaction.

## 21. Restart and Handling Partially Committed Batches

### 21.1. JobInstance vs. JobExecution

```text
Job: importOrdersJob
  |
  +-- JobInstance(inputFile=A, businessDate=D)
         |
         +-- JobExecution #101 FAILED
         |      preflightStep COMPLETED
         |      importOrdersStep FAILED
         |
         +-- JobExecution #102 COMPLETED (restart)
                importOrdersStep COMPLETED
```

A `JobInstance` is identified by the job name and identifying `JobParameters`. An instance can have multiple `JobExecution`s when it fails and restarts. `StepExecution`s are created for the steps that actually re-run.

In the in-memory H2 demo, metadata is **lost when the JVM stops**. You can only test restarts within the **same database lifecycle while it remains alive** or by switching to a persistent database. In production, the metadata database must persist across process restarts.

### 21.2. How to Restart Safely

1. Keep the exact identifying parameters `inputFile` and `businessDate` of the failed instance.
2. Keep the `JobRepository` metadata and `ExecutionContext` from the previous run.
3. Keep the content, record order, and schema of the checkpointed input file unchanged.
4. Have the reader save its state under the stable name `orderCsvReader`.
5. Ensure the writer produces no unintended side effects when a chunk is reprocessed.
6. Do not delete metadata tables just to run a new job.

**Editing a file during restart is dangerous.** If the processor failed because the fourth line had a negative amount, editing the file in-place can alter the byte stream or record order that was checkpointed. Under strict production requirements, use immutable versioned files, mark the batch as rejected, and ingest a new version through the proper workflow.

### 21.3. Re-running a COMPLETED Job

With the same job name and the same identifying parameters, a `JobInstance` that is already `COMPLETED` cannot be launched as a normal new run. Spring Batch may throw `JobInstanceAlreadyCompleteException`.

Changing `run.id` or `businessDate` to force a re-run can create a different `JobInstance`, but **does not guarantee data safety**. The `imported_order` table still has a primary key; re-running the same order IDs will cause a duplicate conflict if the writer still performs an `INSERT`.

If the business requires a re-run, decide explicitly:

- Write only records that do not yet exist (**idempotent insert/upsert**).
- Allow overwriting by source version after reconciliation.
- Delete/rebuild a partition or an approved source.
- Reject duplicate batch processing based on `sourceId`/checksum.

A re-run policy is a business decision; never rely on deleting `BATCH_*` tables.

## 22. Moving from Demo H2 to Production PostgreSQL

H2 helps you learn the API, but a production job needs:

- A persistent database for business data and Spring Batch metadata.
- Versioned schema migrations.
- Transaction, connection pool, and timeout management.
- Explicit unique-key and duplicate-handling policies.
- Appropriate indexes for queries and reporting.
- Connection security, least privilege, and secret management.
- Backup/retention and metadata monitoring.

Example dependencies to change:

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Illustrative production configuration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_batch_user
    password: <provided-by-secret-management>
  batch:
    jdbc:
      initialize-schema: never
  sql:
    init:
      mode: never
```

The YAML snippet uses placeholders **for explanation**, not real passwords or a configuration file to commit to a repository. Real deployments must inject credentials via environment variables or a secret manager, configure TLS as required, and create schemas via migrations. Do not run a production project with DBA privileges solely so Spring Batch can create metadata tables.

In PostgreSQL, one strategy to prevent duplicate inserts on re-run is `INSERT ... ON CONFLICT` on the business key. However, `DO NOTHING` skips duplicates; if a duplicate has different content from the existing data, skipping it could silently drop an important update. Define the data contract clearly before choosing an upsert.

Example SQL for the case where **ignoring existing records is allowed**:

```sql
INSERT INTO imported_order
    (order_id, customer_code, amount, order_date)
VALUES
    (:orderId, :customerCode, :amount, :orderDate)
ON CONFLICT (order_id) DO NOTHING;
```

When using `DO NOTHING`, Spring Batch's `writeCount` does not naturally equal the number of newly inserted rows; query or audit the database if you need to measure the actual **inserted count**.

## 23. Operations, Logging, and Observability

Useful log fields for a CSV import job:

```text
jobName
jobInstanceId
jobExecutionId
stepName
stepExecutionId
businessDate
sourceId / inputFile (controlled)
batchStatus
readCount
writeCount
filterCount
readSkipCount
processSkipCount
writeSkipCount
rollbackCount
errorCategory
```

Do not log raw CSV containing sensitive data, credentials, or secret paths. You can put `jobExecutionId`/`stepExecutionId` into SLF4J MDC so every log line in an execution shares a correlation key; if the step runs multi-threaded, you must propagate MDC across worker threads in a controlled way.

Some metrics to monitor:

| Metric | Why It Matters |
| --- | --- |
| Daily job success/failure | Know whether the import completed on schedule |
| Import step duration | Detect slow batches or an overloaded database |
| Read/write count | Track throughput and reconcile row counts |
| Read/process/write skip | Detect degrading data quality |
| Rollback/retry | Detect DB contention or downstream errors |
| Last successful completion | Detect jobs that failed to run or finish |
| Input source age | Know when data arrives late |

Do not use high-cardinality fields like `orderId`, `sourceId`, or `stepExecutionId` as metric labels. Store detailed IDs in logs/traces and aggregate metrics by `jobName`, `stepName`, `status`, or bounded error categories.

## 24. Common Project Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Application startup fails because inbound directory is not found | `./inbound` directory not created or working directory differs from expectations | Create the directory or set an absolute root in configuration |
| Job does not run automatically | `spring.batch.job.enabled=false` and CLI options are not passed | Pass both `--inputFile` and `--businessDate` |
| Job is rejected because file is not found | File is outside the approved input root or file name is wrong | Place the file under `inbound` and pass a relative path |
| Invalid CSV header | Column names or order differ from contract | Fix the source/contract; do not arbitrarily disable preflight |
| Error at reader when amount is text | `BigDecimal` mapping cannot parse the value | Fix the data or design quarantine/read skip |
| Error at processor due to negative amount | Violates `amount > 0` rule | Fix the data or choose a controlled skip policy |
| Job FAILED in the second chunk but DB has records | The earlier chunk already committed | Restart the same instance and preserve checkpoints |
| Duplicate primary key | Re-running the same business key or input contains duplicates | Design idempotency/upsert and reconciliation |
| `JobInstanceAlreadyCompleteException` | Re-running an already completed identity | Do not delete the repository; design a rerun/version policy |
| `BATCH_*` tables not found | Batch schema init/migration missing | Initialize the schema appropriate for the DB and version |
| H2 has no data after app shutdown | The database is in-memory | Use tests in the same JVM or a persistent DB |
| `@StepScope` resolution fails | Calling the bean outside step context or missing job parameters | Let the framework run the step and pass parameters properly |
| Reader reports unreadable source | OS/volume/IAM permissions or missing source | Check process identity, mounts, and snapshots |
| Integration tests do not run with `mvn test` | Class has `IT` suffix without Failsafe configured | Name it `*Test` or configure Failsafe and run `verify` |
| Job reports COMPLETED but output is wrong | Filter/skip/write logic differs from expectations | Assert target table data, not only `BatchStatus` |

## 25. Extension Exercises After Running the Demo

**Exercise 1 — Multi-field validation.** Add `currency` and `country_code` to the CSV. Require a valid currency, positive amount, and order date in the right period. Put business errors into a dedicated exception.

**Exercise 2 — Skipping invalid data.** Allow up to two validation-error records, and add a `SkipListener` to write to quarantine/audit. Assert `processSkipCount` and verify skipped records do not appear in the target table.

**Exercise 3 — Duplicate source.** Run an import with a file containing two rows with the same `order_id`. Observe the unique constraint and transaction rollback. Then design an explicit duplicate-handling policy.

**Exercise 4 — Real restart.** Switch from in-memory H2 to PostgreSQL or file-based H2 with stable schema migrations. Trigger an error in the second chunk, preserve metadata, fix the root cause, and restart the same instance. Verify the output has no missing or duplicate rows.

**Exercise 5 — File snapshot.** Create a manifest containing file name, `businessDate`, `recordCount`, and checksum. Block the job if the checksum differs or the file is not yet marked READY.

**Exercise 6 — Tuning chunk size.** Scale input to 100,000 rows and compare `chunk(10)`, `chunk(100)`, and `chunk(500)`. Record throughput, transaction duration, and memory instead of comparing total time alone.

**Exercise 7 — Reconciliation.** Add a final tasklet to verify row counts and total amount between the source and the staging table. Block publishing when results do not match.

**Exercise 8 — Scheduled job.** Replace the CLI with a scheduler or orchestration tool. Define the expected schedule, `businessDate` with an explicit timezone, and how to detect late batches.

**Exercise 9 — Multi-source ingestion.** Add `sourceId` and `schemaVersion`; check per-tenant source access permissions, store the version, and define a rerun policy.

**Exercise 10 — Observability and alerts.** Add log correlation by `jobExecutionId`/`stepExecutionId`, measure read/write/skip counts, and alert when an import does not finish on time.

## 26. Summary of the Project Flow

| Component | Responsibility |
| --- | --- |
| `JobParametersValidator` | Reject missing/invalid `inputFile` or `businessDate` |
| `ApprovedInputResolver` | Restrict input to the allowed directory |
| `preflightStep` | Check file, header, and minimum requirements before import |
| `FlatFileItemReader` | Read and parse each CSV record |
| `ItemProcessor` | Validate business rules and normalize output |
| `JdbcBatchItemWriter` | Write valid items to the database |
| `importOrdersStep` | Orchestrate reader → processor → writer within chunk transactions |
| `importOrdersJob` | Coordinate flow and apply the validator |
| `JobRepository` | Persist `JobInstance`/`JobExecution`/`StepExecution` metadata and checkpoints |
| `JobLauncher` | Launch the job with a defined set of parameters |
| Integration tests | Verify end-to-end results, DB data, and preflight failures |

In practice, a good Spring Batch application does more than just "read a file and insert rows." It also needs **input version control, data error handling, transactions, restartability, access control, output quality, and observability**. The project above provides a foundation to extend these requirements while keeping the processing flow clear.

### References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch Reference — JDBC Item Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html)
- [Spring Batch Reference — JobParameters and JobInstance](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference — Late Binding and StepScope](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Boot Reference — Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html)
