# Testing Input/Output Resources in Spring Batch

## 1. Objectives and Scope

In Spring Batch, data typically flows from an **input resource** (CSV, TXT, JSON, XML, files from external systems...) through `ItemReader`, `ItemProcessor`, and into an **output resource**. A job finishing with `COMPLETED` status is not enough to prove file contents are accurate: rows may be missed, bad data may be skipped unexpectedly, encoding may be wrong, duplicate headers may be written, or the wrong file may be overwritten.

This lesson focuses on **testing input/output resources** in *Spring Batch Core Processing*, under *Testing batch*. After studying it, you will be able to:

- Choose how to construct input fixtures and output locations appropriate for each test level.
- Test `FlatFileItemReader`: data parsing, skipping headers, end-of-file handling, and failing on missing/corrupted resources.
- Test `FlatFileItemWriter`: line formatting, record order, headers, encoding, and file creation/replacement behavior.
- Run a real `Step` or `Job` to verify both **output data** and **execution metrics**.
- Design test cases for `@StepScope`, I/O errors, multiple resources, and restarts.

Example scope: **Java 17+, JUnit Jupiter, Spring Boot 3.x, and Spring Batch 5.2.x**. A dedicated section at the end highlights key differences when using Spring Batch 6.x. Do not mix imports from the two version lines in the same project.

## 2. What Is a Resource and Why Test It Separately?

Spring uses the `org.springframework.core.io.Resource` abstraction to represent data locations. `FlatFileItemReader` requires a readable `Resource`; `FlatFileItemWriter` requires a `WritableResource`.

```text
                   Input resource                    Output resource
                    (orders.csv)                     (report.csv)
                          │                                ▲
                          ▼                                │
                   FlatFileItemReader               FlatFileItemWriter
                          │                                ▲
                          ▼                                │
                      ItemProcessor ────────────────────────┘
                              │
                      Step / Job metadata
                   (readCount, writeCount,
                    skipCount, BatchStatus...)
```

Two contract layers must be verified:

1. **Content contract:** does the input file have the expected row/column counts, data types, order, and values? Does the output file have the expected structure, encoding, line count, and contents?
2. **Operational contract:** if a file is missing, does the job fail or skip? Are inputs closed after use? Does writing to the same path delete, append, or resume per `ExecutionContext`? Does metadata record accurate counts?

### Choosing a Resource Type for Tests

| Resource | Usage in Tests | Notes |
|---|---|---|
| `ClassPathResource` | Reading fixed fixtures in `src/test/resources` | Good for read-only inputs; never write outputs into the classpath. |
| `ByteArrayResource` | Building small inputs directly from in-memory strings/bytes | Creates no disk files; suited for reader unit tests needing reopenable data. |
| `FileSystemResource` | Pointing to files in a temporary test directory | Required for writers and tests confirming files are created on disk. |
| `InputStreamResource` | Wrapping an existing `InputStream` | Many streams are read-once; avoid for reopen/restart tests. |
| `UrlResource` or resources from external services | Controlled integration tests or tests with mock adapters | Availability, permissions, and stability depend on external environments. |

Example creating a small in-memory fixture:

```java
byte[] csv = "id,amount\n101,10.00\n102,20.50\n"
        .getBytes(StandardCharsets.UTF_8);
Resource resource = new ByteArrayResource(csv);
// Attach this resource to FlatFileItemReader via builder.resource(resource).
```

Example creating real files isolated across test runs:

```java
@TempDir
Path tempDir;

@Test
void resourceExample() throws IOException {
    Path input = tempDir.resolve("input.csv");
    Path output = tempDir.resolve("output.csv");

    Files.writeString(input, "id,amount\n101,10.00\n",
            StandardCharsets.UTF_8);

    Resource inputResource = new FileSystemResource(input);
    WritableResource outputResource = new FileSystemResource(output);
}
```

`@TempDir` is managed by JUnit Jupiter, avoiding shared writes to `./data/output.csv` or dependence on leftover files from prior runs. On Windows environments, closing streams properly also prevents file-lock errors when the temporary directory is cleaned up.

## 3. Choosing the Appropriate Testing Level

| Testing Level | What Runs? | What to Assert? | When to Use? |
|---|---|---|---|
| Reader unit test | `open → read → close` of the reader | Mapping, headers, EOF, format errors, missing files | When input parsing is complex or fast feedback is needed |
| Writer unit test | `open → write → close` of the writer | Headers, per-line format, ordering, encoding, overwrite rules | When output structure is a business contract |
| Step integration test | Real step with temporary input/output | Read/write/filter/skip counts and output | When testing chunking, processor, reader, and writer together |
| Job integration test | Full job with `JobParameters` | Final status, output file results, multi-step flow | When verifying end-to-end behavior |
| Restart/error test | Intentional failure then rerun | Resume position, missing/duplicate records, file handling | When the job must restart safely after failures |

An effective strategy is writing **a few targeted unit tests** for both I/O ends and **at least one integration test** exercising the real pipeline. Assertions checking only `BatchStatus.COMPLETED` miss many content defects.

## 4. End-to-End Problem: Reading CSV and Producing CSV

Suppose a system receives a list of payments. Each payment has an `id` and `amount`; processing adds a fixed fee of `1.00` and writes `id,total`.

**Input — `payments.csv`**

```csv
id,amount
101,10.00
102,20.50
103,0.00
```

**Expected Output — `invoices.csv`**

```csv
id,total
101,11.00
102,21.50
103,1.00
```

Conventions for the example:

- Input has a single header line; output always has a header line too.
- Each valid record produces exactly one output record in input order.
- Use `BigDecimal` to avoid floating-point rounding errors on monetary amounts.
- Missing input is an error; tests should detect errors early.
- Encoding is UTF-8; each test run has its own input/output directory.

### 4.1. Dependencies for Testing

For a project using Spring Boot with Gradle and Boot's dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    runtimeOnly 'com.h2database:h2' // JobRepository metadata in local demo

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Spring Boot manages compatible versions. A production app can use PostgreSQL/MySQL instead of H2; the example simply needs a `DataSource` and the Spring Batch metadata tables to run integration tests.

### 4.2. Sample Batch Configuration

Place the class below in package `com.example.batch`. The imports target **Spring Batch 5.2.x**.

```java
package com.example.batch;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class PaymentBatchConfig {

    public record Payment(long id, BigDecimal amount) {}
    public record Invoice(long id, BigDecimal total) {}

    @Bean
    @StepScope
    public FlatFileItemReader<Payment> paymentReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<Payment>()
                .name("paymentReader")
                .resource(new FileSystemResource(inputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .linesToSkip(1)
                .strict(true)
                .delimited()
                .delimiter(",")
                .names("id", "amount")
                .fieldSetMapper(fs -> new Payment(
                        fs.readLong("id"),
                        fs.readBigDecimal("amount")))
                .build();
    }

    @Bean
    @StepScope
    public FlatFileItemWriter<Invoice> invoiceWriter(
            @Value("#{jobParameters['outputFile']}") String outputFile) {

        return new FlatFileItemWriterBuilder<Invoice>()
                .name("invoiceWriter")
                .resource(new FileSystemResource(outputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .headerCallback(w -> w.write("id,total"))
                .lineAggregator(invoice ->
                        invoice.id() + "," + invoice.total().toPlainString())
                .shouldDeleteIfExists(true)
                .build();
    }

    @Bean
    public Step paymentStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Payment> paymentReader,
            FlatFileItemWriter<Invoice> invoiceWriter) {

        return new StepBuilder("paymentStep", jobRepository)
                .<Payment, Invoice>chunk(2, transactionManager)
                .reader(paymentReader)
                .processor(payment -> new Invoice(
                        payment.id(),
                        payment.amount().add(new BigDecimal("1.00"))))
                .writer(invoiceWriter)
                .build();
    }

    @Bean
    public Job paymentJob(JobRepository jobRepository, Step paymentStep) {
        return new JobBuilder("paymentJob", jobRepository)
                .start(paymentStep)
                .build();
    }
}
```

Use a standard application entry point in the same package:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoBatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoBatchApplication.class, args);
    }
}
```

Here, `@StepScope` lets the reader and writer receive paths from `JobParameters` at step execution time. Both reader and writer are `ItemStream` implementations: when Spring Batch runs for real, the framework manages the `open`, `update`, and `close` lifecycle. In unit tests calling them directly, the test author must control that lifecycle.

**Note:** `shouldDeleteIfExists(true)` fits the scenario of generating fresh output. For jobs requiring restart or append behavior, test the file policy and `ExecutionContext` strictly per business requirements; never assume file writes and database transactions form a single atomic transaction.

## 5. Unit Testing Input Resources and FlatFileItemReader

The first test verifies: skipping the header, mapping `id/amount` accurately, reading in order, and `read()` returning `null` at EOF.

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.ItemStreamException;

import com.example.batch.PaymentBatchConfig.Payment;

class PaymentInputResourceTest {

    @TempDir
    Path tempDir;

    private final PaymentBatchConfig config = new PaymentBatchConfig();

    @Test
    void readsHeaderAndAllRecordsInOrder() throws Exception {
        Path input = tempDir.resolve("payments.csv");
        Files.writeString(input,
                "id,amount\n101,10.00\n102,20.50\n103,0.00\n",
                StandardCharsets.UTF_8);

        FlatFileItemReader<Payment> reader =
                config.paymentReader(input.toString());
        reader.open(new ExecutionContext());
        try {
            assertEquals(new Payment(101L, new BigDecimal("10.00")),
                    reader.read());
            assertEquals(new Payment(102L, new BigDecimal("20.50")),
                    reader.read());
            assertEquals(new Payment(103L, new BigDecimal("0.00")),
                    reader.read());
            assertNull(reader.read()); // EOF
        } finally {
            reader.close();
        }
    }

    @Test
    void failsWhenInputResourceDoesNotExist() {
        Path missing = tempDir.resolve("missing.csv");

        FlatFileItemReader<Payment> reader =
                config.paymentReader(missing.toString());

        try {
            assertThrows(ItemStreamException.class,
                    () -> reader.open(new ExecutionContext()));
        } finally {
            reader.close();
        }
    }

    @Test
    void reportsMalformedCsvLine() throws Exception {
        Path input = tempDir.resolve("invalid.csv");
        Files.writeString(input,
                "id,amount\n101,10.00\n102,INVALID\n",
                StandardCharsets.UTF_8);

        FlatFileItemReader<Payment> reader =
                config.paymentReader(input.toString());
        reader.open(new ExecutionContext());
        try {
            assertNotNull(reader.read());

            FlatFileParseException error = assertThrows(
                    FlatFileParseException.class, () -> reader.read());
            assertEquals(3, error.getLineNumber());
            assertEquals("102,INVALID", error.getInput());
        } finally {
            reader.close();
        }
    }
}
```

Calling `config.paymentReader(path)` above invokes **a plain Java factory method**, so there is no need to boot a Spring context just to test file parsing. When you want to test `@Value("#{jobParameters[...]}")` expressions and the `@StepScope` proxy, use the integration test in a later section.

### Additional Cases to Cover for the Reader

| Input Case | Recommended Assertion |
|---|---|
| Header-only file | `read() == null` on the first call; step reads 0 items. |
| Empty file | Outcome per chosen contract: EOF or application-level validation error. |
| Extra/missing columns | Parser throws error if tokenizer is configured strict on field count. |
| Negative amounts, zero values, large numbers | Mapping to `BigDecimal` and business rules handle them accurately. |
| Wrong header names/order | If schema must be validated, add a header validation step (`linesToSkip(1)` only skips lines, **does not validate column names**). |
| Commas inside quoted fields | Ensure tokenizer and fixture reflect real CSV formatting. |
| Vietnamese characters, Unicode, BOM | Read UTF-8 accurately; check and handle BOM if source includes one. |
| Deleted or unreadable file | Receive appropriate error, never report false success. |

Distinguish two easily confused `strict` settings:

- `FlatFileItemReaderBuilder.strict(true)`: requires the input resource to exist, failing if the input cannot be opened.
- `DelimitedLineTokenizer.strict(true)`: requires each record's token count to match the declared column structure. This is a separate setting and does not automatically validate header content.

If `reader.strict(false)` is enabled, a missing file may result in zero items read. Choose that behavior only when a missing input is genuinely valid in your system.

## 6. Unit Testing Output Resources and FlatFileItemWriter

Readers can use read-only in-memory resources; writers typically require a real `WritableResource`. We use `FileSystemResource` pointing to a file inside `@TempDir`, invoke `write(Chunk)`, close the writer, and read back the output.

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemWriter;

import com.example.batch.PaymentBatchConfig.Invoice;

class PaymentOutputResourceTest {

    @TempDir
    Path tempDir;

    private final PaymentBatchConfig config = new PaymentBatchConfig();

    @Test
    void writesExpectedCsvHeaderAndRows() throws Exception {
        Path output = tempDir.resolve("invoices.csv");
        FlatFileItemWriter<Invoice> writer =
                config.invoiceWriter(output.toString());

        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                    new Invoice(101L, new BigDecimal("11.00")),
                    new Invoice(102L, new BigDecimal("21.50")),
                    new Invoice(103L, new BigDecimal("1.00")))));
        } finally {
            writer.close();
        }

        assertTrue(Files.exists(output));
        assertEquals(List.of(
                "id,total",
                "101,11.00",
                "102,21.50",
                "103,1.00"),
                Files.readAllLines(output, StandardCharsets.UTF_8));
    }

    @Test
    void replacesAnOldOutputFileOnFreshRun() throws Exception {
        Path output = tempDir.resolve("invoices.csv");
        Files.writeString(output, "OLD_DATA\n",
                StandardCharsets.UTF_8);

        FlatFileItemWriter<Invoice> writer =
                config.invoiceWriter(output.toString());
        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                    new Invoice(201L, new BigDecimal("6.00")))));
        } finally {
            writer.close();
        }

        assertEquals(List.of("id,total", "201,6.00"),
                Files.readAllLines(output, StandardCharsets.UTF_8));
    }
}
```

Compare **line by line as an ordered list** if order is part of the contract. `Files.readAllLines` abstracts away `\n` / `\r\n` line-ending differences between Linux and Windows; if byte-for-byte precision is required, use `Files.readAllBytes` and compare bytes against the specified encoding and line endings.

Never omit `close()`: the writer may still hold buffers and file handles. A test reading output before closing can see unflushed content or fail due to file locks on Windows.

### Important Output Edge Cases

- **Zero items:** verify whether a header-only file, an empty file, or file deletion via `shouldDeleteIfEmpty` matches the contract.
- **Pre-existing file:** verify delete/overwrite, append, or rejection; never let results depend on stale files.
- **Records containing delimiters, quotes, or newlines:** manual string concatenation in `lineAggregator` in the example is safe only because both fields are numeric. For text containing commas, use a proper CSV generator with escaping and test it.
- **Write permissions / invalid paths:** verify the step fails and never publishes an incomplete output as a successful file.
- **Number / date-time formatting:** specify locale, time zone, decimal scale, and output format explicitly; never rely on the CI machine's default locale.
- **Ordering:** if a step runs in parallel or partitioned mode, assert ordering only when the pipeline guarantees preserving order.

## 7. Integration Test: Running the Job and Checking Both Files and Metadata

Unit tests for reader and writer can both pass while the job still fails due to wrong bean wiring, wrong `JobParameters`, or misconfigured processor/chunk settings. `spring-batch-test` provides `@SpringBatchTest` and `JobLauncherTestUtils` in Spring Batch 5.2.

The example below assumes a `paymentJob` bean exists in the context (class `DemoBatchApplication` scans `PaymentBatchConfig` in the same package).

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(
    classes = DemoBatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class PaymentJobIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path tempDir;

    @Test
    void transformsInputCsvIntoExpectedOutputCsv() throws Exception {
        Path input = tempDir.resolve("payments.csv");
        Path output = tempDir.resolve("invoices.csv");

        Files.writeString(input,
                "id,amount\n101,10.00\n102,20.50\n103,0.00\n",
                StandardCharsets.UTF_8);

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", input.toString())
                .addString("outputFile", output.toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(List.of(
                "id,total",
                "101,11.00",
                "102,21.50",
                "103,1.00"),
                Files.readAllLines(output, StandardCharsets.UTF_8));

        StepExecution step = execution.getStepExecutions().stream()
                .filter(s -> s.getStepName().equals("paymentStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(3L, step.getReadCount());
        assertEquals(3L, step.getWriteCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(0L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
    }
}
```

Key takeaways:

1. `spring.batch.job.enabled=false` stops Boot from auto-launching the job before the test provides paths; the test explicitly calls `launchJob(params)`.
2. Input and output live inside `@TempDir`, giving each test isolated data. Within the same `JobRepository`, re-running **the exact same** `JobParameters` for an already completed `JobInstance` may trigger `JobInstanceAlreadyCompleteException`; provide appropriate run-identifying parameters when intentionally creating a new instance.
3. `@StepScope` receives `inputFile/outputFile` when the step runs, not when Spring builds the context.
4. Combining status assertions with **real output** and **read/write/skip counts** catches jobs that technically succeed while being wrong on business logic.
5. If tests have multiple `Job` beans, call `jobLauncherTestUtils.setJob(paymentJob)` (injecting the target `Job` via qualifier) to avoid launching the wrong job.

### Running Only a Single Step

When a job has multiple steps, you can test the file-processing step alone with:

```java
JobExecution execution =
        jobLauncherTestUtils.launchStep("paymentStep", params);
```

`launchStep` also establishes a step execution context and runs the real reader/processor/writer; this is handy when you want to skip preparatory steps while still validating input/output resources at integration level.

If the step uses data placed into `JobExecutionContext` by another step, an overload of `launchStep` accepts an `ExecutionContext` to supply the required data.

## 8. Testing @StepScope and Resource-Bound Job Parameters

Input/output paths are often supplied at job launch time, for example:

```java
@StepScope
@Bean
FlatFileItemReader<Payment> reader(
        @Value("#{jobParameters['inputFile']}") String file) {
    // Configure reader with FileSystemResource(file)
}
```

Testing with `new PaymentBatchConfig().paymentReader(path)` only verifies reader construction logic. To verify Spring's **late binding**, step scope must be active. There are two approaches:

- **Most realistic approach:** run an integration test with `launchStep`/`launchJob` using real `JobParameters`, then inspect the file.
- **Bean-isolation approach:** use `StepScopeTestUtils.doInStepScope(stepExecution, callable)`, or `@SpringBatchTest` combined with `StepScopeTestExecutionListener`, to provide a `StepExecution` for the step-scoped bean.

Sketch of the second approach:

```java
StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(
                new JobParametersBuilder()
                        .addString("inputFile", input.toString())
                        .toJobParameters());

// Reader injected from Spring context is a @StepScope bean:
Payment first = StepScopeTestUtils.doInStepScope(stepExecution, () -> {
    stepScopedReader.open(new ExecutionContext());
    try {
        return stepScopedReader.read();
    } finally {
        stepScopedReader.close();
    }
});
```

Here, `stepScopedReader` must come **from the ApplicationContext** with `StepScope` enabled, never constructed with `new`. When testing binding, what matters is that the `JobParameters` value actually reaches the resource. For simple tests, running the real step is usually clearer and requires less boilerplate.

## 9. Designing Test Cases for Input/Output Errors

Do not rely on a single valid file. Build a scenario matrix based on your system's concrete contract.

| Scenario | Expected Outcome | What to Check |
|---|---|---|
| Input exists, 3 valid rows | `COMPLETED` | Output has exact 3 data rows, right header and values. |
| Input missing | `FAILED` when `strict(true)` | Do not treat 0 items read as success. |
| Header-only input | Per contract, usually `COMPLETED` | `readCount=0`; output matches empty-file policy. |
| CSV line with invalid numeric type | Fails by default unless fault tolerance configured | Parse error includes line number and bad input; `BatchStatus` and output file stay consistent. |
| Parse error with `skip` configured | May end `COMPLETED` within allowed limit | `readSkipCount`, output row count, list of excluded records matches rules. |
| Processor returns `null` | Item filtered, not an error | Inspect `filterCount` and `writeCount`. |
| Writer cannot open file | `FAILED` | No invalid output published as successful; error/log observed. |
| Output already exists | Per delete/append/restart policy | New file contains no stale data; exact header count. |
| UTF-8 file with Vietnamese diacritics | Read/written intact | No replacement characters or BOM artifacts. |
| Multiple input resources | All files read in defined order | No missing, duplicated, or unexpectedly reordered items. |

If the job configures `faultTolerant().skip(...).skipLimit(...)`, prove all three aspects: allowed skippable exception type, bounded skip count, and accurate post-skip output. Asserting only "job completed" can mask data loss.

### Actually Validating the Header

`linesToSkip(1)` only skips the first line of input. If the contract requires the exact header `id,amount`, use `skippedLinesCallback` to inspect it, or add a dedicated schema validation step prior to processing. Then add a test with an input like `amount,id` to confirm the job rejects files with wrong column ordering.

### Separating Data Errors from Resource Errors

- **Resource errors**: file does not exist, lacks read/write permissions, path points to a directory instead of a file, file locked by another process.
- **Format errors**: wrong delimiter, missing columns, unparseable numbers, invalid characters, wrong header.
- **Business errors**: duplicate IDs, disallowed negative values, missing reference data.

Classifying errors helps configure retry/skip properly: do not blindly retry a malformed line forever; likewise, do not skip an entire mandatory source file merely because of an I/O failure.

## 10. Testing Restart and Output Consistency

Spring Batch saves `ItemStream` state via `ExecutionContext` to support restarts. For line-based readers, saved state allows returning to the last checkpointed position; for writers, file state must be preserved across reruns.

### Illustrating a Position-Saving Reader

Standalone test idea:

```java
ExecutionContext context = new ExecutionContext();

FlatFileItemReader<Payment> firstReader =
        config.paymentReader(input.toString());
firstReader.open(context);
Payment first = firstReader.read();  // 101
firstReader.update(context);         // Simulate saving checkpoint
firstReader.close();

// Use a new reader with the same name and resource, and the saved context.
FlatFileItemReader<Payment> resumedReader =
        config.paymentReader(input.toString());
resumedReader.open(context);
try {
    Payment next = resumedReader.read(); // Expect 102
    assertEquals(102L, next.id());
} finally {
    resumedReader.close();
}
```

This example illustrates part of the checkpoint mechanism; in a real job, `JobRepository` persists state along commit boundaries. When testing restart at the job level, deliberately inject an error after a few chunks and rerun **the same JobInstance** under valid restart conditions. Verify that **final output has no missing or duplicate records**, rather than merely checking `COMPLETED` after the second run.

Important points:

- `saveState(false)` disables resuming from a saved position; unsuitable if accurate restart is expected.
- Changing reader/writer names or mutating the input between two runs can invalidate checkpoints.
- `shouldDeleteIfExists`, `append`, and writer state must be tested across both **fresh runs** and **restart runs**; these two scenarios follow different rules.
- File output is not inherently atomic with database commits. When combining file writes, DB writes, and event emission, adopt an atomic file-publishing policy (e.g., write to a temp file then rename in a final step) and test failure points.

## 11. Multiple Resources, Other Formats, and Test Environments

### Multiple Input Files

With `MultiResourceItemReader`, tests should create several small files and verify: total items collected across all files, well-defined file ordering (configure a comparator if needed), and transitions from file A to file B neither drop nor duplicate records. If the writer uses `MultiResourceItemWriter`, verify generated file counts, file names, per-file item limits, and combined contents.

### JSON, XML, JDBC, or External Resources

The testing mindset remains the same:

- **JSON/XML readers:** prepare minimal yet structurally valid fixtures, test missing nodes/properties, invalid values, and empty input; verify object mapping.
- **JSON/XML writers:** parse output using a matching parser to compare structure and data, avoiding raw string equality when property order or whitespace is not part of the contract.
- **JDBC input/output:** use isolated test schemas and data; assert DB row counts and transactions, not just status.
- **HTTP/object storage:** isolate adapters/resources in unit tests; integration tests should only hit controlled test environments. Avoid tests dependent on external networks or production services.

### Keeping Tests Stable

- Give each test its own input and output; never share hardcoded file paths.
- Specify encoding explicitly and normalize line endings before comparing.
- Close readers/writers in `finally` or equivalent mechanisms.
- Fix clocks, locales, and time zones if data generation depends on them.
- If tests run in parallel, never share file names or `JobRepository` state.
- Avoid overly brittle verbatim error-message assertions when asserting exception type, offending line, and business effect suffices.
- For large files, check counts/checksums plus representative records; for small fixtures, comparing the entire output is clearer.

## 12. Version Notes: Spring Batch 5.x and 6.x

The Java examples above use **Spring Batch 5.2.x** APIs. In **Spring Batch 6.x**, two notable changes exist:

| Aspect | Spring Batch 5.2.x | Spring Batch 6.x |
|---|---|---|
| Job/Step test runner utility | `JobLauncherTestUtils.launchJob()/launchStep()` | `JobOperatorTestUtils.startJob()/startStep()`; the old utility is deprecated |
| Item/file API package | `org.springframework.batch.item...` | Mostly moved to `org.springframework.batch.infrastructure.item...`, e.g., `...infrastructure.item.file.builder.FlatFileItemReaderBuilder` |
| JUnit | JUnit Jupiter supported | JUnit 4 no longer supported |

Equivalent test calls in Spring Batch 6.x:

```java
@Autowired
JobOperatorTestUtils jobOperatorTestUtils;

// Use startJob instead of launchJob.
JobExecution execution = jobOperatorTestUtils.startJob(params);

// Or test a step individually:
JobExecution stepExecution =
        jobOperatorTestUtils.startStep("paymentStep");
```

When upgrading, adjust imports against the **Javadoc of the exact version in use** and keep Spring Boot/Spring Batch dependencies aligned; do not change only the utility name while keeping 5.x item imports.

## 13. Practice Exercises

**Exercise 1 — Corrupted input:** change row `102,20.50` to `102,abc`. Write a reader unit test verifying `FlatFileParseException` and the offending line number. Next, run the job to verify `BatchStatus` matches your chosen error configuration.

**Exercise 2 — Precision output:** add an input row with value `999999999999.99`. Prove that adding `1.00` is exact and produces no scientific notation violating the system's CSV convention.

**Exercise 3 — Invalid header:** create a CSV with header `amount,id`, keeping the same data rows. Add a header validation step and a test confirming the job rejects inputs with wrong column order.

**Exercise 4 — Missing resource:** write a test with a non-existent input. Compare behavior between `reader.strict(true)` and explicitly setting `strict(false)`, then explain the right choice for a mandatory payment file.

**Exercise 5 — Restart:** build a processor that fails on the third record after the first chunk commits, remove the failure condition, and restart the same JobInstance. Cross-check the final output file, line count, and header to ensure no data is lost or duplicated.

## 14. References

- [Spring Batch 5.2 – Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, step/job testing and step scope.
- [Spring Batch 6 – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): current testing APIs with `JobOperatorTestUtils`.
- [Spring Batch – FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): `Resource`, `LineMapper`, tokenizer, parse error handling.
- [Spring Batch – FlatFileItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-writer.html): output resources, line aggregators, headers, and existing-file policies.
- [Spring Batch – Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): using `@StepScope` and `JobParameters` to select resources per run.

When testing input/output resources, the ultimate goal is proving **what data was read, what data was written, and how the application reacts to abnormal conditions**. Job status, metadata, and resource contents are three complementary perspectives.
