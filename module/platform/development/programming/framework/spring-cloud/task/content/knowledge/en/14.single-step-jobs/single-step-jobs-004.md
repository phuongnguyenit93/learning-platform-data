# Reading CSV and Fixed-Width Files

## 1. Problem statement and objectives

In a **Spring Cloud Task** application, a single run typically receives parameters, processes a bounded dataset, and terminates. For example, each night an organization receives a customer file from a partner, reads each line, validates the data, and updates a database. Spring Cloud Task tracks the **application execution** via `TaskRepository`; when the import involves many records, **Spring Batch** provides readers, writers, transactions, and restart capabilities.

The **Single-Step Jobs** chapter focuses on workloads with a simple pipeline: **read a file → map to objects → write results**, structured as **one `Job` with one chunk-oriented `Step`**. This lesson examines two common input file formats:

- **CSV (Comma-Separated Values):** columns are separated by commas; strings containing commas can be enclosed in double quotes.
- **Fixed-width file:** no delimiter character is required; each field occupies a designated range of character positions.

After this lesson, you will be able to:

1. Define a data contract for CSV and fixed-width files.
2. Distinguish `FlatFileItemReader`, `LineTokenizer`, `FieldSetMapper`, and `LineMapper`.
3. Use `DelimitedLineTokenizer` to read CSV and `FixedLengthTokenizer` to read fixed-column records.
4. Wire both options into **one Spring Batch Job with one Step**, selecting the format via `JobParameters`.
5. Read logs, verify database results, handle bad lines, and restart after a chunk failure.
6. Distinguish Spring Cloud Task's `TaskRepository` from Spring Batch's `JobRepository` and `ExecutionContext`.

> The primary Java snippets in this lesson use the **Spring Boot 3.x and Spring Batch 5.x** API style, with examples persisting to PostgreSQL. Spring Batch 6 changes several packages/APIs; use sample code and a BOM matching your actual version rather than mixing imports across versions.

## 2. One Job, one Step, and two input formats

A Spring Batch `Job` can contain multiple steps, but this use case needs only **one step**. The same step configuration receives an `ItemReader` built for the file format of that run.

~~~mermaid
flowchart LR
    A["Parameters: inputFile, inputFormat"] --> B["Job: importCustomerFileJob"]
    B --> C["Step: importCustomersStep"]
    C --> D{"inputFormat?"}
    D -->|csv| E["DelimitedLineTokenizer"]
    D -->|fixed| F["FixedLengthTokenizer"]
    E --> G["FieldSetMapper → CustomerRow"]
    F --> G
    G --> H["ItemWriter / business database"]
    C --> I[("JobRepository: chunk, step, job state")]
    B --> J[("TaskRepository: task application lifecycle")]
~~~

**Two separate repositories:**

| Spring Cloud Task | Spring Batch |
| --- | --- |
| `TaskRepository` records each launch of the task application | `JobRepository` records `JobInstance`, `JobExecution`, `StepExecution` |
| Tracks process start/end times and exit code | Tracks item read/write counts, step status, and restart checkpoints |
| Reruns create a new `TaskExecution` | A Job can restart under its `JobInstance` and `JobParameters` identity |
| Does not automatically track line position in a file | `ItemStream` and `ExecutionContext` can persist read position at commit points |

If you include **`spring-cloud-task-batch`** alongside `Job`, Spring Cloud Task can auto-configure `TaskBatchExecutionListener` to link a `JobExecution` to its corresponding `TaskExecution`. That link helps lookup, but it **does not replace** the two separate metadata stores.

## 3. Data contract for the example

We import customer data with three fields:

| Java field | Meaning | Rules |
| --- | --- | --- |
| `customerId` | Customer code | 5-character string, e.g., `C0001` |
| `customerName` | Customer name | Non-blank; max 20 characters for fixed-width |
| `monthlyFee` | Monthly fee | Non-negative decimal; e.g., `120000` |

Data record:

~~~java
import java.math.BigDecimal;

public record CustomerRow(
        String customerId,
        String customerName,
        BigDecimal monthlyFee
) {}
~~~

### 3.1. CSV file

Contents of `customers.csv` (UTF-8):

~~~csv
customer_id,customer_name,monthly_fee
C0001,"Nguyen, An",120000
C0002,Tran Binh,95000
C0003,Le Minh,150000
~~~

**Key points to note:**

- The first line is a **header**, not a customer record. The reader will skip one line.
- `"Nguyen, An"` contains a comma inside double quotes, so it remains **one** field.
- Column names in the header are user-defined; `DelimitedLineTokenizer` uses its configured list of internal field names **positionally**. Skipping the header **does not automatically verify** that column names match expectations.
- Lines with fewer or more columns than expected are rejected as errors when the tokenizer is in **strict** mode.

### 3.2. Fixed-width file

Contents of `customers.fw` have **no header** and each line is **35 characters** long:

| Field | Character positions (1-based) | Width | Representation |
| --- | ---: | ---: | --- |
| `customerId` | 1–5 | 5 | Left-aligned |
| `customerName` | 6–25 | 20 | Left-aligned, right-padded with spaces |
| `monthlyFee` | 26–35 | 10 | Non-negative integer, left-padded with zeros |

To generate an exact file, use the following Java snippet (names are written in ASCII to avoid confusing byte counts with character counts):

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

public class FixedWidthSampleGenerator {

    public static void main(String[] args) throws Exception {
        String one = String.format(
                Locale.ROOT, "%-5s%-20s%010d",
                "C0001", "Nguyen, An", 120000);

        String two = String.format(
                Locale.ROOT, "%-5s%-20s%010d",
                "C0002", "Tran Binh", 95000);

        Files.write(
                Path.of("customers.fw"),
                List.of(one, two),
                StandardCharsets.UTF_8);
    }
}
~~~

Both generated lines in `customers.fw` have exactly 35 characters. **There is no `|` or comma delimiter**; the comma inside `Nguyen, An` is simply part of the field content.

If a partner specifies fields by **byte count** instead of character positions, account for encoding before using `FixedLengthTokenizer`. For example, UTF-8 encodes certain accented Vietnamese characters using multiple bytes; byte offsets and character offsets are not always identical. Agree on the encoding and width-measurement rules with the partner upfront.

## 4. Transformation pipeline: from text line to CustomerRow

Spring Batch `FlatFileItemReader` reads a `Resource` and converts each text record into an object. Responsibilities:

| Component | Responsibility |
| --- | --- |
| `Resource` | Identifies the file to read (e.g., `FileSystemResource`) |
| `FlatFileItemReader<CustomerRow>` | Manages opening/closing the file, reading records, and saving read state for restarts |
| `LineTokenizer` | Splits a line into fields |
| `DelimitedLineTokenizer` | Splits by delimiter, with rules for quoted fields |
| `FixedLengthTokenizer` | Splits by declared column ranges |
| `FieldSet` | Represents extracted values accessible by name or column index |
| `FieldSetMapper<CustomerRow>` | Maps extracted values into a Java object |
| `DefaultLineMapper<CustomerRow>` | Combines a tokenizer and field set mapper into a `LineMapper` |

~~~mermaid
flowchart TD
    A["One record as String"] --> B["LineTokenizer"]
    B --> C["FieldSet with id, name, fee"]
    C --> D["FieldSetMapper"]
    D --> E["CustomerRow"]
    E --> F["ItemWriter"]
~~~

Between CSV and fixed-width formats, **only the tokenizer differs**. Mapping from `FieldSet` to `CustomerRow` can be shared as long as the field names configured on both tokenizers match.

### 4.1. Configuring the CSV tokenizer

~~~java
DelimitedLineTokenizer csv = new DelimitedLineTokenizer();
csv.setDelimiter(",");
csv.setNames("customerId", "customerName", "monthlyFee");
csv.setStrict(true);
~~~

In the CSV example, double quotes around the name containing a comma allow the tokenizer to parse three fields accurately. Do not split lines manually with `line.split(",")`, as that breaks values like `"Nguyen, An"`.

### 4.2. Configuring the fixed-width tokenizer

~~~java
FixedLengthTokenizer fixed = new FixedLengthTokenizer();
fixed.setNames("customerId", "customerName", "monthlyFee");
fixed.setColumns(
        new Range(1, 5),
        new Range(6, 25),
        new Range(26, 35)
);
fixed.setStrict(true);
~~~

`Range(1, 5)` is **inclusive at both ends** and **1-based** in Spring Batch. With strict enabled, record lengths must match the defined layout; lines that are too short or too long throw `IncorrectLineLengthException`. If the file contract allows a variable-length trailing field, adjust the tokenizer design to match that contract.

### 4.3. Mapping the parsed result

~~~java
DefaultLineMapper<CustomerRow> mapper = new DefaultLineMapper<>();
mapper.setLineTokenizer(tokenizer);
mapper.setFieldSetMapper(fields -> new CustomerRow(
        fields.readString("customerId").trim(),
        fields.readString("customerName").trim(),
        new BigDecimal(fields.readString("monthlyFee").trim())
));
mapper.afterPropertiesSet();
~~~

After this step, both formats produce identical Java objects:

~~~text
CustomerRow(
    customerId="C0001",
    customerName="Nguyen, An",
    monthlyFee=120000
)
~~~

**Data parsing differs from business validation.** Invalid numeric strings throw a parse error in `BigDecimal`; business rules such as "ID must be 5 characters", "name non-blank", and "fee non-negative" should be validated further in the mapper or an `ItemProcessor`. When files use locale-specific date or currency formats, declare explicit parsing rules rather than relying on the JVM default locale.

## 5. Full configuration of a single-Step Job

The next example uses **Spring Batch 5.x**; Spring Boot supplies Batch configuration automatically when the starter is present and auto-configuration is not disabled. We define **one Job bean, one Step bean**, and construct the reader using the run's `JobParameters`.

### 5.1. Core dependencies

Maven example with versions managed by compatible Spring Boot and Spring Cloud BOMs:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-task-batch</artifactId>
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
</dependencies>
~~~

`spring-cloud-task-batch` is useful when you want to **link Batch job history with task executions**; core file-reading features belong to Spring Batch. Do not add `@EnableBatchProcessing` when relying on Spring Boot auto-configuration, as that annotation can alter what Spring Boot auto-configures. If a project opts for full manual Batch configuration, align `JobRepository`, `JobLauncher`, and transaction managers consistently.

### 5.2. Spring Boot Task application

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class CustomerFileTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerFileTaskApplication.class, args);
    }
}
~~~

The application only needs Spring Boot to auto-launch the single job. Do not add another `ApplicationRunner` that manually calls `JobLauncher.run(...)`, as doing so can **launch the job twice**. If multiple jobs exist, explicitly specify which job to run or manage launching through a single mechanism.

### 5.3. Reader bean selecting tokenizer via JobParameters

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FixedLengthTokenizer;
import org.springframework.batch.item.file.transform.LineTokenizer;
import org.springframework.batch.item.file.transform.Range;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class FileReaderConfiguration {

    @Bean
    @StepScope
    public FlatFileItemReader<CustomerRow> customerFileReader(
            @Value("#{jobParameters['inputFile']}") String inputFile,
            @Value("#{jobParameters['inputFormat']}") String inputFormat) {

        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("Missing inputFile");
        }
        if (inputFormat == null) {
            throw new IllegalArgumentException("Missing inputFormat");
        }

        String format = inputFormat.toLowerCase(Locale.ROOT);
        LineTokenizer tokenizer;

        if ("csv".equals(format)) {
            DelimitedLineTokenizer csv = new DelimitedLineTokenizer();
            csv.setDelimiter(",");
            csv.setNames(
                    "customerId", "customerName", "monthlyFee");
            csv.setStrict(true);
            tokenizer = csv;
        }
        else if ("fixed".equals(format)) {
            FixedLengthTokenizer fixed = new FixedLengthTokenizer();
            fixed.setNames(
                    "customerId", "customerName", "monthlyFee");
            fixed.setColumns(
                    new Range(1, 5),
                    new Range(6, 25),
                    new Range(26, 35));
            fixed.setStrict(true);
            tokenizer = fixed;
        }
        else {
            throw new IllegalArgumentException(
                    "Supported formats: csv, fixed");
        }

        DefaultLineMapper<CustomerRow> mapper =
                new DefaultLineMapper<>();
        mapper.setLineTokenizer(tokenizer);
        mapper.setFieldSetMapper(fields -> new CustomerRow(
                fields.readString("customerId").trim(),
                fields.readString("customerName").trim(),
                new BigDecimal(
                        fields.readString("monthlyFee").trim())
        ));
        mapper.afterPropertiesSet();

        return new FlatFileItemReaderBuilder<CustomerRow>()
                .name("customerFileReader")
                .resource(new FileSystemResource(inputFile))
                .encoding("UTF-8")
                .linesToSkip("csv".equals(format) ? 1 : 0)
                .strict(true)
                .lineMapper(mapper)
                .saveState(true)
                .build();
    }
}
~~~

**Why use `@StepScope`?** `inputFile` and `inputFormat` are **JobParameters** only known when the job launches. Creating the reader eagerly in singleton scope to resolve those values would fail because they might not exist yet. Step scope instantiates the reader right when the step executes and preserves state for that run.

**Intentional configuration choices:**

- `.name("customerFileReader")` assigns a stable name for storing reader state keys in `ExecutionContext`.
- `.resource(new FileSystemResource(inputFile))` reads a file from the filesystem visible to the process. When running in a container, the path must exist **inside the container**.
- `.encoding("UTF-8")` explicitly sets the encoding for the example.
- `.linesToSkip(1)` applies only to CSV because it has a header; the sample fixed-width file has no header.
- `.strict(true)` on the reader turns a missing file into an error instead of silently running with empty data. `setStrict(true)` on the tokenizer enforces expected column counts/widths per format.
- `.saveState(true)` persists read progress into `ExecutionContext` on step commits to support restarts.

**Note:** `linesToSkip(1)` does not verify that header column names and order are correct. For critical datasets, use `skippedLinesCallback` to validate the expected header, and handle BOM/encodings deliberately if partners export files differently.

### 5.4. Target table and writer

Example using PostgreSQL, target table:

~~~sql
CREATE TABLE import_customer (
    customer_id   VARCHAR(5) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    monthly_fee   NUMERIC(18, 2) NOT NULL
);
~~~

A simple `ItemWriter<CustomerRow>` using `JdbcTemplate` inside the chunk transaction:

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class CustomerWriterConfiguration {

    @Bean
    public ItemWriter<CustomerRow> customerWriter(JdbcTemplate jdbc) {
        return chunk -> {
            for (CustomerRow row : chunk) {
                jdbc.update("""
                    INSERT INTO import_customer
                        (customer_id, customer_name, monthly_fee)
                    VALUES (?, ?, ?)
                    ON CONFLICT (customer_id)
                    DO UPDATE SET
                        customer_name = EXCLUDED.customer_name,
                        monthly_fee = EXCLUDED.monthly_fee
                    """,
                    row.customerId(),
                    row.customerName(),
                    row.monthlyFee());
            }
        };
    }
}
~~~

`ON CONFLICT` lets us upsert a customer by the same key without creating duplicate rows; that is **a simple idempotency example**. In real systems, only overwrite when business policy allows it. If you need to distinguish records across separate imports, the unique key should include an appropriate `sourceVersion` or `importId`. For large datasets, consider `JdbcBatchItemWriter` / batch updates to avoid per-row SQL round trips.

### 5.5. Wiring one Step and one Job

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class CustomerBatchJobConfiguration {

    @Bean
    public Step importCustomersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<CustomerRow> customerFileReader,
            ItemWriter<CustomerRow> customerWriter) {

        return new StepBuilder("importCustomersStep", jobRepository)
                .<CustomerRow, CustomerRow>chunk(50, transactionManager)
                .reader(customerFileReader)
                .writer(customerWriter)
                .build();
    }

    @Bean
    public Job importCustomerFileJob(
            JobRepository jobRepository,
            Step importCustomersStep) {

        return new JobBuilder("importCustomerFileJob", jobRepository)
                .start(importCustomersStep)
                .build();
    }
}
~~~

This remains a **single-step Job** even with two file formats: `inputFormat` only selects how to read; the Job always consists of `importCustomersStep`.

With `chunk(50, transactionManager)`, the framework typically reads up to 50 items, passes them to the writer, and commits. Step/reader state is persisted at appropriate commit points to enable restarts. This assumes `JobRepository` and the transaction manager are reliably configured. If the Batch metadata database differs from the target data database, the two commit scopes may **not be atomic**; in that case, idempotency and safe replay are mandatory.

## 6. Application configuration and launching

Example `application.yml` with PostgreSQL whose schemas are already provisioned via migrations:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://localhost:5432/task_batch_db
    username: import_task
    # Provide SPRING_DATASOURCE_PASSWORD via environment secret.
  batch:
    jdbc:
      initialize-schema: never
    job:
      enabled: true
  cloud:
    task:
      name: customer-file-import-task
      initialize-enabled: false
~~~

Complete schemas for both **Spring Batch** (e.g., `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, and `BATCH_STEP_EXECUTION_CONTEXT`) and **Spring Cloud Task** (e.g., `TASK_EXECUTION`) compatible with your versions must exist. Use `initialize-schema: never` and `initialize-enabled: false` only when schemas are already prepared; against an empty database, the application will fail to start the job.

Spring Boot normally **auto-launches the single Job** in the context on startup, unless disabled or overridden by a custom launcher. When you already have one `Job`, do not build an extra internal scheduler inside the task.

### 6.1. Running CSV

~~~bash
java -jar customer-import-task.jar inputFile=/data/customers.csv inputFormat=csv
~~~

### 6.2. Running fixed-width

~~~bash
java -jar customer-import-task.jar inputFile=/data/customers.fw inputFormat=fixed
~~~

**Distinguishing Boot arguments from JobParameters:** when Spring Boot auto-launches a Batch job, arguments **without the `--` prefix** such as `inputFile=...` are converted into `JobParameters`. Conversely, `--spring.profiles.active=prod` is a Spring Boot environment property, not a business parameter automatically passed to the job.

The command can combine both:

~~~bash
java -jar customer-import-task.jar \
  --spring.profiles.active=prod \
  inputFile=/data/customers.csv inputFormat=csv
~~~

In PowerShell, place the entire command on **one line**; backslash line continuation in the snippet above is for Linux/macOS shells.

### 6.3. Be careful with JobInstance identity

Spring Batch identifies a `JobInstance` by **job name and identifying JobParameters**. If a `JobInstance` is already `COMPLETED`, invoking it again with the **same identifying parameters** is rejected with `JobInstanceAlreadyCompleteException`.

If you want to process a new input version, pass **JobParameters that accurately describe the data version** (e.g., source version or a valid run ID) instead of deleting Batch metadata. To **restart a FAILED JobExecution**, normally rerun with the same identifying parameters and keep the input file unchanged; non-identifying values must also be passed again when using the command-line launcher.

In the demo, the file path and format act as identifying parameters. If you reuse the same path after **the file contents have changed**, the Batch checkpoint from the failed run may no longer align with the right records. Use **immutable** files/snapshots or checksums with versioning to ensure restarts read the exact same data.

## 7. Verifying logs and actual results

After a successful CSV import run, query the results:

~~~sql
SELECT customer_id, customer_name, monthly_fee
FROM import_customer
ORDER BY customer_id;
~~~

Expected result for the sample CSV: three customers, where `C0001` has name `Nguyen, An` and fee `120000`.

Spring Batch stores per-run metadata in `BATCH_JOB_EXECUTION` and `BATCH_STEP_EXECUTION`. For example:

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE, START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

~~~sql
SELECT STEP_EXECUTION_ID, STEP_NAME, STATUS,
       READ_COUNT, WRITE_COUNT, READ_SKIP_COUNT,
       PROCESS_SKIP_COUNT, WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID DESC;
~~~

Checking **`TaskRepository`** alone is insufficient to know how many items were read/written because those counters belong to **Spring Batch `StepExecution`**. With `spring-cloud-task-batch` and matching schema setup, the `TASK_TASK_BATCH` link table lets you trace from `TaskExecution` to `JobExecution`:

~~~sql
SELECT TASK_EXECUTION_ID, JOB_EXECUTION_ID
FROM TASK_TASK_BATCH
ORDER BY TASK_EXECUTION_ID DESC;
~~~

**Inspect everything together:** process exit code, job/step status in `JobRepository`, the `TaskExecution` record, and actual customer data. A `"Started"` log line does not prove the entire file was imported; an exit code of 0 does not replace checking business invariants.

## 8. Handling bad files and choosing a skip policy

Common issues:

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| CSV row has 4 columns instead of 3 | Unquoted comma or schema mismatch | Inspect source line and quoting rules |
| CSV contains newlines inside quoted field | Multi-line record; reader needs matching record separator policy | Configure `RecordSeparatorPolicy` or a contract-compliant multi-line parser |
| Fixed-width line missing 2 characters | Record shorter than 35 positions | Report format error; do not shift boundaries |
| Fee is not numeric | `BigDecimal` parse error or locale format | Standardize decimal/currency format; report bad line |
| Vietnamese characters garbled | Source encoding is not UTF-8 or has BOM | Check charset, BOM, and byte vs. character width rules |
| File not found | Wrong path inside container or missing volume mount | Check `Resource`, read permissions, absolute path |
| Rerun rejected | Same `JobInstance` already completed | Clarify whether restarting `FAILED` or running new data |
| Retry re-reads wrong lines | File changed or reader/`JobRepository` state not persisted | Keep input immutable; ensure `saveState` and proper Batch schemas |

### 8.1. Fail or skip bad lines?

In the baseline example, **a parse error fails the step**. This is the right choice for small files or strict data contracts: broken data should be fixed and rerun.

If business rules permit skipping up to a strictly bounded number of malformed lines, Spring Batch supports `faultTolerant()` with `skipLimit(...)` and `skip(...)`. Example **illustrating only the replacement step configuration**:

~~~java
return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerRow, CustomerRow>chunk(50, transactionManager)
        .reader(customerFileReader)
        .writer(customerWriter)
        .faultTolerant()
        .skipLimit(3)
        .skip(org.springframework.batch.item.file.FlatFileParseException.class)
        .build();
~~~

**Do not blindly skip every exception.** When skipping bad lines, record the **line number, reason, and workflow for handling rejected records** so everything can be reconciled. Batch's `READ_SKIP_COUNT` counts skips but does not replace detailed error reporting. Never skip system errors such as database disconnects or write failures where doing so risks silent data loss.

### 8.2. Validate headers, don't just skip them

`linesToSkip(1)` simply discards the first line. If a partner reorders columns in the CSV, the reader continues mapping by declared position and **can silently misread data**.

Example header check when building the CSV reader:

~~~java
// Add to FlatFileItemReaderBuilder for csv format:
.skippedLinesCallback(line -> {
    if (!line.equals("customer_id,customer_name,monthly_fee")) {
        throw new IllegalArgumentException(
                "Unexpected CSV header: " + line);
    }
})
~~~

Apply this callback only to CSV files that include a header per the contract, not to headerless fixed-width files. For real CSV files with a BOM, strip/handle the BOM properly before comparing.

## 9. Restarting after a chunk failure

Suppose a CSV has 250 items and chunk size is 50:

1. The Step reads/writes the first 50 items and **commits**.
2. The Step proceeds to chunk 51–100, but hits an error at line 80.
3. Because the error rolls back the chunk, items 51–100 are **not committed**.
4. `JobRepository` stores step metadata and `ExecutionContext` at the last commit point. When restarting the same `JobInstance`, the reader restores its position right after the committed chunk.
5. Provided the file is unchanged and the writer is properly idempotent, the step resumes without creating duplicate results.

**Key property of `FlatFileItemReader`:** it implements `ItemStream`, allowing state persistence when `saveState(true)` is enabled with a stable name. Reopening the reader at the right offset on restart relies on Spring Batch's `ExecutionContext`, **not** Spring Cloud Task's `TASK_EXECUTION_ID`.

~~~mermaid
flowchart TD
    A["JobExecution #1: start reading CSV"] --> B["Commit chunk 1–50"]
    B --> C["Error in chunk 51–100"]
    C --> D["JobExecution FAILED"]
    D --> E["JobExecution #2: restart same JobInstance"]
    E --> F["Read committed checkpoint from ExecutionContext"]
    F --> G["Resume from safe boundary"]
    G --> H["COMPLETED"]
~~~

**Conditions for safe restarts:**

- The input file is **unchanged** between runs of the same `JobInstance`, including line ordering and header.
- `JobRepository` and `ExecutionContext` are stored in a persistent database.
- The Reader and Step retain **consistent names** to reload saved state.
- The Writer uses transactions and idempotency where needed, especially if business data and Batch metadata live on separate transaction resources.
- Never let `ApplicationRunner` exit early while a Batch job runs asynchronously and treat `TaskExecution` as the completion status of the import.

If you need per-record reconciliation, complex retries, partitioning, or multiple steps, study Spring Batch's checkpoint, skip, and restart mechanisms further. For this lesson, one `Job` with one `Step` is sufficient to demonstrate reading and importing finite files.

## 10. CSV vs. fixed-width: how to choose?

| Criterion | CSV | Fixed-width file |
| --- | --- | --- |
| Field separation | Delimiters and quoting | Predefined character positions |
| Schema | Optional header; column count checkable | Strictly defined order and widths |
| Values containing commas | Can be quoted with double quotes | Commas are ordinary content characters |
| Missing data | Can be empty fields; requires validation | Can cause wrong line length or space padding |
| Common pitfalls | Quote escaping, delimiters, embedded newlines, encoding | Padding, field boundaries, multi-byte characters, exact length |
| Spring Batch tokenizer | `DelimitedLineTokenizer` | `FixedLengthTokenizer` |
| Best suited for | General data exchange and human-readable integrations | Legacy systems, partner formats with rigid layouts |

Both can be handled with **`FlatFileItemReader`**; choose the tokenizer based on the **source contract**, not the filename extension. If a file mixes multiple record types—such as header, detail, and trailer lines with distinct schemas—use a record-dispatching mechanism like `PatternMatchingCompositeLineMapper` or split into controlled steps.

## 11. Self-check labs

### Lab A — CSV

Create `customers.csv` as shown at the beginning of the lesson and run the job with `inputFormat=csv`. Verify:

- Three items are read; the header line is not counted as an item.
- `"Nguyen, An"` is mapped as a single string containing a comma.
- The `import_customer` table contains three rows with accurate fees.
- `StepExecution` shows `READ_COUNT=3` and `WRITE_COUNT=3` when no skips or filters apply.

### Lab B — Fixed-width

Run the generator to create `customers.fw`, then invoke the job with `inputFormat=fixed`. Verify:

- The reader does not skip the first line because the file has no header.
- Ranges 1–5, 6–25, and 26–35 are parsed accurately.
- Two items are written; if run against the same table, customers with matching IDs are **updated** without creating duplicate IDs.
- Changing one line to 34 characters triggers a failure when the tokenizer is strict.

### Lab C — Restart

Create a 120-record file and trigger a controlled failure in a chunk after the first chunk has committed. Rerun with the **same identifying JobParameters** and an **immutable file** to restart. Verify the final row count is exact, no duplicates were introduced, and Batch metadata shows one `JobInstance` with multiple `JobExecution` records for the restart.

### Lesson completion checklist

- [ ] Distinguished `TaskRepository` from `JobRepository`.
- [ ] Understood the difference between `DelimitedLineTokenizer` and `FixedLengthTokenizer`.
- [ ] Verified encoding, header, schema, quoting, and widths against the source contract.
- [ ] Used `@StepScope` to bind `inputFile` and `inputFormat` at job launch time.
- [ ] Configured a Job with **a single Step** whose reader adapts to the run's format.
- [ ] Tested CSV column count errors and fixed-width line length errors.
- [ ] Kept Spring Boot `--...` options separate from Batch `name=value` JobParameters.
- [ ] Inspected `READ_COUNT`, `WRITE_COUNT`, and skip counts in `BATCH_STEP_EXECUTION`.
- [ ] Kept input files immutable across restarts and enabled reader `ExecutionContext` state saving.
- [ ] Configured transactions and appropriate idempotency in the writer.
- [ ] Kept secrets out of `JobParameters`, `TaskRepository`, and logs.
- [ ] Verified business outcomes before treating a job as successful.

## 12. Takeaways

**A single-step Spring Batch Job** can read both CSV and fixed-width files using the same processing pipeline. `FlatFileItemReader` reads records; `DelimitedLineTokenizer` and `FixedLengthTokenizer` define field extraction; `FieldSetMapper` maps fields into objects; `ItemWriter` persists results. `JobRepository` manages Step progress and restarts, while **Spring Cloud Task's `TaskRepository`** tracks the lifecycle of the application launching the job.

In operations, enforce an **explicit file contract**, keep input files **immutable across restarts**, handle malformed records according to policy, and make writes **consistent/idempotent**. These matter far more than simply seeing `"Job completed"` in the logs.

### References

- [Spring Batch 5.2 — FlatFileItemReader, CSV and fixed-length](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch 5.2 — Configuring a Chunk-Oriented Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html)
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html)
- [Spring Boot — Running Batch Jobs from the Command Line](https://docs.spring.io/spring-boot/how-to/batch.html)
- [Spring Cloud Task — Spring Batch integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
