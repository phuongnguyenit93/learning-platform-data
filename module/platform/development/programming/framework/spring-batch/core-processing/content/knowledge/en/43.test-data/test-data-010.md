# Cleaning Up Output Files After Tests in Spring Batch

When testing a batch job or a file-writing step, output data usually does not stay only in memory. `FlatFileItemWriter`, `JsonFileItemWriter`, `StaxEventItemWriter`, or a custom writer may create CSV, TXT, JSON, XML, temporary files, and directories on disk. If those files linger after a test, the next run may accidentally read stale results, append to an earlier file, or fail because the path already exists.

Within the **Test data** topic of **Spring Batch Core Processing**, *cleaning up output files after tests* means structuring output lifecycle as follows:

```text
Create a dedicated output area for the test
          |
          v
Run writer / step / job
          |
          v
Read and assert output file
          |
          v
Close reader, writer, stream, and related resources
          |
          v
Clean output, even if assertions or batch execution fail
```

The goal is for every test to start from a known state, run independently again, and never affect data of other tests or the real application. With **JUnit Jupiter (JUnit 5)**, the preferred approach is letting `@TempDir` manage a private directory per test. When writing elsewhere is unavoidable, set up explicit cleanup with `@AfterEach` or `try/finally` and delete only resources owned by the test.

## 1. Why clean up output files?

Suppose a step exports a report:

```text
exportOrdersStep
    ItemReader<Order>
        -> ItemProcessor<Order, String>
        -> FlatFileItemWriter<String>
        -> build/reports/orders.csv
```

The first test has three orders and writes `orders.csv`. Without cleanup, subsequent runs can suffer from these issues:

| Symptom | Possible cause | Consequence |
| --- | --- | --- |
| File contains lines from previous test | Writer configured to append or custom logic opens file in append mode | Wrong assertions, duplicate data |
| Test passes when it should fail | Test reads leftover output from a previous run without verifying new output was actually created | False positive |
| Flaky test failures | Multiple tests share the same filename, creating/deleting/reading concurrently | Order-dependent or parallel failures |
| Unable to delete file, especially on Windows | `ItemStream`, `BufferedWriter`, or input stream left unclosed | Locked file, cleanup fails |
| Junk outputs accumulate | Test fails before `delete`, or lacks teardown | CI fills with files, hard to tell old/new results apart |
| Test accidentally deletes real data | Output path points to a shared directory or reads runtime config | Data loss outside test scope |

Two actions must stay separate: **asserting file contents** proves processing is right; **cleaning up files** guarantees the environment returns to a clean state. Cleanup does not replace assertions, and passing assertions do not prove cleanup occurred.

## 2. Preferred solution: JUnit 5 `@TempDir`

JUnit Jupiter provides `@TempDir` to create a temporary directory for a test. Once the test finishes, JUnit cleans the directory and its files per the configured cleanup policy (normally deleted after the test). This applies even when assertions throw errors, since cleanup is part of the test lifecycle.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExportFileTest {

    @TempDir
    Path outputDir;

    @Test
    void writesExpectedContent() throws IOException {
        // Arrange: each test receives its own path.
        Path output = outputDir.resolve("orders.csv");

        // Simulate a writer's output to focus on file lifecycle.
        Files.write(output, List.of("A001,PAID", "A002,NEW"),
            StandardCharsets.UTF_8);

        // Assert before JUnit cleans outputDir.
        assertThat(Files.exists(output)).isTrue();
        assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
            .containsExactly("A001,PAID", "A002,NEW");

        // No need for Files.delete(output): JUnit handles it after the test finishes.
    }
}
```

`@TempDir` can be declared on a field or method parameter:

```java
@Test
void exportsOneFile(@TempDir Path outputDir) throws IOException {
    Path file = outputDir.resolve("result.csv");
    Files.writeString(file, "id,status\n1,DONE\n", StandardCharsets.UTF_8);

    assertThat(Files.readString(file, StandardCharsets.UTF_8))
        .contains("1,DONE");
}
```

This illustrates JUnit-managed output. In Spring Batch, replace `Files.write...` with running the writer or step. JUnit still handles cleanup as long as outputs actually land **inside** the allocated directory.

### 2.1. Advantages and limitations of `@TempDir`

- Per-test paths avoid filename collisions across multiple tests or parallel runs.
- Cleanup does not depend on reaching the last line of the test method; mid-test failures still trigger teardown.
- Eliminates writing recursive deletion code for directories holding many small outputs.
- JUnit only manages its allocated temporary directory tree. If a job ignores parameters and writes to `C:/data/export.csv` or external object storage, `@TempDir` cannot clean those resources.
- To preserve files for investigating failures, you can configure JUnit's cleanup mode in debug environments, while restoring default cleanup on CI.

`@TempDir` does **not** clean `JobRepository` metadata tables such as `BATCH_JOB_EXECUTION` or `BATCH_STEP_EXECUTION`; that is a separate data lifecycle.

## 3. Direct example with `FlatFileItemWriter`

Before wiring a writer into a job, you can test file writing at the component level. The example below uses **Spring Batch 5.x** APIs and JUnit Jupiter:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.core.io.FileSystemResource;

class OrderWriterTest {

    @TempDir
    Path outputDir;

    @Test
    void writesOrdersAndReleasesFileHandle() throws Exception {
        Path output = outputDir.resolve("orders.csv");

        FlatFileItemWriter<String> writer =
            new FlatFileItemWriterBuilder<String>()
                .name("orderWriter")
                .resource(new FileSystemResource(output))
                .encoding(StandardCharsets.UTF_8.name())
                .lineAggregator(item -> item)
                .build();

        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                "A001,PAID",
                "A002,NEW"
            )));
        } finally {
            // ItemStream must close even when writer.write() throws an exception.
            writer.close();
        }

        assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
            .containsExactly("A001,PAID", "A002,NEW");
        // JUnit cleans up outputDir and orders.csv after the test.
    }
}
```

`FlatFileItemWriter` implements `ItemStream`. When run inside a properly configured `Step`, Spring Batch manages `open`, `update`, and `close`. However, **when calling a writer directly in a test**, the developer must close it explicitly. `try/finally` is essential to avoid leaking file handles on write failures, especially on Windows.

If your goal is testing transactions, restarts, skips, or framework-managed writer closing, run a **real step** rather than only calling `write()` as above.

## 4. Testing a file-writing step with a test-supplied path

A common challenge in integration tests is that ApplicationContext is cached across tests while `@TempDir` changes on every run. An easily controlled approach is passing the output path in `JobParameters` and using a `@StepScope` writer to read the current run's path.

This example targets **Spring Boot 3.x, Spring Batch 5.x, JUnit 5**. Required Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

The test below defines a job with one step `exportOrdersStep`, runs it via `JobLauncherTestUtils`, verifies the CSV, and lets JUnit delete the output directory afterward.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = ExportOrdersStepTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class ExportOrdersStepTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path outputDir;

    @Test
    void exportsToItsOwnTemporaryDirectory() throws Exception {
        Path output = outputDir.resolve("orders.csv");

        JobParameters parameters = new JobParametersBuilder()
            .addString("outputPath", output.toAbsolutePath().toString())
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
            "exportOrdersStep", parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(Files.exists(output)).isTrue();
        assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
            .containsExactly("A001,PAID", "A002,NEW");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        Job exportOrdersJob(JobRepository repository,
                            @Qualifier("exportOrdersStep") Step exportStep) {
            return new JobBuilder("exportOrdersJob", repository)
                .start(exportStep)
                .build();
        }

        @Bean
        Step exportOrdersStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("ordersWriter") FlatFileItemWriter<String> writer) {

            return new StepBuilder("exportOrdersStep", repository)
                .<String, String>chunk(2, transactionManager)
                .reader(new ListItemReader<>(List.of(
                    "A001,PAID", "A002,NEW")))
                .writer(writer)
                .build();
        }

        @Bean
        @StepScope
        FlatFileItemWriter<String> ordersWriter(
                @Value("#{jobParameters['outputPath']}") String outputPath) {

            return new FlatFileItemWriterBuilder<String>()
                .name("ordersWriter")
                .resource(new FileSystemResource(outputPath))
                .encoding(StandardCharsets.UTF_8.name())
                .lineAggregator(item -> item)
                .build();
        }
    }
}
```

Key details in this example:

1. `@TempDir` provides the output path and creates the parent directory before the step starts. The `orders.csv` path does not exist yet when setting up the test.
2. `outputPath` is a `JobParameter` for the run. `@StepScope` defers instantiating the real writer until the step executes, so the writer receives the current test's `outputPath`.
3. Spring Batch opens and closes `FlatFileItemWriter` within the step lifecycle. The test only asserts after `launchStep(...)` returns.
4. When the test finishes, JUnit deletes the output directory. Even on writer or assertion errors, lifecycle cleanup runs; deletion can still fail if a resource stays locked or another process holds it.
5. Distinct paths across tests also create distinct identifying `JobParameters`, avoiding `JobInstance` collisions on a reused `JobRepository` in the test context. If using unchanging parameters across runs, manage metadata explicitly to prevent `JobInstanceAlreadyCompleteException`.

**Version note:** In Spring Batch 6.x, `JobOperatorTestUtils.startStep(...)` supersedes the `JobLauncherTestUtils.launchStep(...)` style used in Spring Batch 5.x. Spring Batch 6 also reorganizes several core packages. As for cleanup principles, `@TempDir`, `JobParameters`, and scoped writers apply just the same; adjust APIs/imports to your project's version.

## 5. When `@TempDir` cannot be used: cleanup with `@AfterEach`

Some tests integrate with programs or tools that only accept a fixed output path. If you must clean files manually, place cleanup in `@AfterEach` rather than at the end of the test method, because the test method can abort early at an assertion or exception.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FixedOutputPathTest {

    private Path testDirectory;
    private Path report;
    private Path temporaryPart;

    @BeforeEach
    void createIsolatedDirectory() throws IOException {
        testDirectory = Files.createTempDirectory("spring-batch-output-");
        report = testDirectory.resolve("report.csv");
        temporaryPart = testDirectory.resolve("report.csv.tmp");
    }

    @Test
    void exportsReport() throws IOException {
        // In a real test: invoke the step to write the report.
        Files.writeString(report, "id,total\nA001,100\n",
            StandardCharsets.UTF_8);

        assertThat(Files.readString(report, StandardCharsets.UTF_8))
            .contains("A001,100");
    }

    @AfterEach
    void removeGeneratedFiles() throws IOException {
        // Delete only files owned by this test.
        if (report != null) {
            Files.deleteIfExists(report);
        }
        if (temporaryPart != null) {
            Files.deleteIfExists(temporaryPart);
        }
        if (testDirectory != null) {
            Files.deleteIfExists(testDirectory); // directory must be empty
        }
    }
}
```

`Files.deleteIfExists(...)` does not throw if a file is absent, which helps when a batch stops before creating output. However, it still throws `IOException` when a file is open, lacks permissions, or a directory is non-empty. Often it is better to **let the test fail on cleanup errors** to catch resource leaks rather than silently swallowing exceptions.

The example above enumerates the exact two files that can be produced. If a writer generates nested subdirectories or dynamic filenames, `@TempDir` is much simpler and safer. Only when that option is unavailable should you consider recursive deletion, paired with verifying the path points **strictly** inside the test-created directory. Never run recursive deletion on a path read directly from production environment variables or untrusted `JobParameters`.

If a file is created solely within a short non-JUnit code path, `try/finally` also works well:

```java
Path output = Files.createTempFile("batch-result-", ".csv");
try {
    // Run output-writing logic and assert results.
} finally {
    Files.deleteIfExists(output);
}
```

With `FlatFileItemWriter`, ensure `close()` runs **before** `Files.deleteIfExists(output)`.

## 6. Distinguishing test cleanup from writer file-deletion options

`FlatFileItemWriter` provides options that manage output during execution:

| Option | Role | Replaces test teardown? |
| --- | --- | --- |
| `shouldDeleteIfExists(true)` | May delete an existing target file at the start of a new execution, depending on restart state | No. The newly written file remains after the step |
| `shouldDeleteIfEmpty(true)` | Deletes empty output at completion if zero items were written | No. Non-empty output remains |
| `appendAllowed(true)` | Permits appending to an existing file per writer configuration | No. Makes avoiding stale files from other tests even more critical |
| `saveState(true)` and `ExecutionContext` | Saves state to support restarts | No. This is checkpointing, not file cleanup |

Never tweak these flags just to mask missing test cleanup. For example, a test verifying append mode must deliberately create the initial file, assert the exact appended lines, and only then delete the file. A restart test must keep the file after the first run to execute the second run, cleaning up only after the entire restart scenario is asserted.

### File output behaves differently from database transactions

Spring Batch typically manages chunk transactions. However, file writing does not inherently share the same physical rollback behavior as a SQL table. When a chunk fails or a step stops midway, the file may already exist or contain partial data depending on the writer and buffering/transaction settings. Failure-path tests must verify:

- `JobExecution`/`StepExecution` has the expected status (`FAILED`, `STOPPED`, or another designed state).
- Whether the file exists, how many lines it holds, and whether unexpected data is present.
- Temporary or partial result files are handled per application policy.
- Once assertions finish, test-scoped output is cleaned up.

Do not assume database transaction rollback automatically deletes files created by a writer. If the application requires atomic file emission, design it to write a temporary file and rename/move into the destination only when the step succeeds; tests must also verify temporary-file behavior on failure.

## 7. Cleaning inputs and outputs within proper scope

A batch test often needs both input fixtures and newly generated outputs:

```text
@TempDir testDir/
    input/
        orders.csv        # test input data
    output/
        result.csv        # file generated by batch
        result.csv.tmp    # intermediate file if any
```

You can create this layout under `@TempDir`:

```java
Path inputDir = Files.createDirectories(testDir.resolve("input"));
Path outputDir = Files.createDirectories(testDir.resolve("output"));

Path input = inputDir.resolve("orders.csv");
Path output = outputDir.resolve("result.csv");

Files.writeString(input, "id,total\nA001,100\n",
    StandardCharsets.UTF_8);
```

This layout separates initial fixtures from batch outputs while letting JUnit clean both after the test. If an input fixture is an immutable file under `src/test/resources`, only read it; never delete or overwrite source fixtures. If a writer or step mutates input files (such as archiving or deleting them), **copy** the fixture into a temporary directory before running.

In many projects, tests use `build/test-output/` (or `target/test-output/`) instead of the OS temp directory. When doing so, give each test its own subdirectory and never wipe all of `build/` or `target/` in `@AfterEach`. Broad build-directory cleaning belongs to the build tool or CI pipeline, not individual unit tests.

## 8. Commonly overlooked cleanup edge cases

### 8.1. Test fails before creating the file

The batch may fail in the reader or processor so output is never created. Cleanup using `Files.deleteIfExists` or `@TempDir` handles this gracefully. Never treat a missing file as a cleanup error.

### 8.2. Output remains open when assertions run

Calling `FlatFileItemWriter` directly without `close` can leave buffered content unflushed and cause Windows to reject file deletion. Close the writer before reading/comparing output. In real steps, let Spring Batch manage `ItemStream`; for custom writers, implement resource open/close contracts properly.

### 8.3. Parallel tests

Two tests both writing `report.csv` into a shared folder easily break each other: one test deletes the file while the other is reading it. Use separate `@TempDir` directories, or generate a unique directory name per test execution. Never rely on execution order or a single fixed filename across the suite.

### 8.4. Files deleted yet Spring Batch metadata remains

`@TempDir` removes output on disk but does not delete `JobInstance`, `JobExecution`, or `StepExecution` from `JobRepository`. Reusing the same *identifying JobParameters* for a completed job still triggers `JobInstanceAlreadyCompleteException` in the next test. In a dedicated test database, use `JobRepositoryTestUtils` to clean metadata at the right scope, or supply distinct identifying parameters across tests. Never delete shared metadata of real jobs.

### 8.5. Temporary files, multiple outputs, and nested directories

A step may generate `report.csv.tmp`, partition files, dedicated log files, or multiple dated files. Tests should know which artifacts are expected and check their presence/absence before JUnit cleanup runs. With `@TempDir`, files inside the directory tree are cleaned up per the test lifecycle.

### 8.6. Output outside the local filesystem

When a writer sends data to S3, MinIO, object storage, or SFTP, `@TempDir` only cleans local files. For real integration tests, create a test-owned bucket/prefix or remote directory and delete only test-created objects in teardown; prefer fakes or storage containers to avoid impacting shared environments. Avoid broad wildcard deletes on non-test objects.

### 8.7. Keeping files to diagnose failures

On CI, automatic cleanup keeps suites clean and reproducible. When investigating tough failures, configure JUnit to retain `@TempDir` in debug mode or copy needed files to CI artifacts before teardown. Never let tests depend on a leftover file from an earlier run.

## 9. Recommended strategies by test type

| Test type | Output setup | Appropriate cleanup |
| --- | --- | --- |
| Formatter/processor unit test | No file creation needed | No output to clean |
| `FlatFileItemWriter` unit test | `FileSystemResource` pointing into `@TempDir` | Call `writer.close()` then let JUnit clean |
| Single file-writing step integration test | `outputPath` passed via `JobParameters`, `@StepScope` writer | `@TempDir` for output; handle test metadata separately |
| Multi-step job flow integration test | Create `input/` and `output/` inside one dedicated test directory | Clean after all job assertions complete |
| Retry/restart test | Keep the same output across retry/restart phases | Clean after final phase, never between restarts |
| External system integration test | Test-owned resource (bucket, prefix, remote folder) | Teardown deletes only created resources |

## 10. Principles to remember

1. **Every test output must have clear ownership and scope.** Place output in a test-specific directory rather than application runtime paths.
2. **Assert before cleaning up.** Verify contents, encoding, filename, line count, and auxiliary files per business requirements.
3. **Close resources before deleting.** For `ItemStream`, ensure `close()` executes even when writes fail.
4. **Ensure cleanup runs even on test failure.** Prefer `@TempDir`; where unsuitable, use `@AfterEach` or `try/finally`.
5. **Never delete beyond test scope.** Avoid deleting shared parent directories, source fixtures, or production data.
6. **Separate output-file cleanup from batch metadata cleanup.** Files and `JobRepository` have distinct lifecycles; handle both when tests rerun.

Applying these principles consistently keeps Spring Batch tests accurate at catching file-export bugs, independent of execution order, safe for parallelism, and clean for subsequent runs.

## References

- [JUnit 5 User Guide — Built-in Extensions, `@TempDir`](https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory): how JUnit creates and cleans temporary test directories.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): Spring Batch integration with Spring Test and step/job launchers.
- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): file writer configuration and output management options.
- [Spring Batch API — `FlatFileItemWriter`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/file/FlatFileItemWriter.html): `ItemStream` lifecycle and output-file options.
