# Opening Input and Output Files in Reader and Writer

In Spring Batch, input and output files are typically managed through Spring's `Resource` abstraction. An `ItemReader` opens a file to read data, while an `ItemWriter` opens a file to write results. For file components that support `ItemStream`, Spring Batch manages the lifecycle of opening, updating checkpoints, and closing resources according to the Step lifecycle.

When the file path changes per run, it can be obtained from JobParameters using `@Value` and declaring a `@StepScope` bean. This ensures each StepExecution receives the right file for the current JobExecution, while allowing the reader/writer to persist state for restart.

## 1. Resource abstraction in Spring

Spring uses the `Resource` interface to represent a data source. Common implementations:

| Resource | Source | Suitable Use Case |
|---|---|---|
| `FileSystemResource` | File on the filesystem | Reading an input file or writing an output file at a specific path. |
| `ClassPathResource` | Resource on the classpath | Reading sample files or data packaged with the application. |
| `UrlResource` | Resource via URL | Reading content from a URL when the reader and infrastructure support it. |
| `ByteArrayResource` | Byte array in memory | Small data already available in memory. |

Example creating a resource for a filesystem file:

```java
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource inputResource =
        new FileSystemResource("/data/in/orders.csv");
```

`Resource` describes the location and how to access data. It does not decide the CSV format, encoding, field mapping, or restart strategy. Those responsibilities belong to the Reader/Writer and their corresponding configuration.

For output files, `FileSystemResource` pointing to a writable path should be used. `ClassPathResource` is usually suitable for reading resources packaged in the application; it should not be used as an output destination because resources inside a JAR or on the classpath may not be writable.

## 2. File open and close lifecycle of ItemStream

Many Spring Batch Readers and Writers implement `ItemStream`. This interface has three main callbacks:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

- `open()` is called when the Step starts to open the file and restore saved state if present.
- `update()` is called at appropriate state-saving points, typically tied to chunk commit boundaries, to write a checkpoint to the `ExecutionContext`.
- `close()` is called when the Step finishes to release file handles, streams, and related resources.

With `FlatFileItemReader` and `FlatFileItemWriter`, there is usually no need to manually call `open()` or `close()` inside a Tasklet. Spring Batch manages the lifecycle of Readers/Writers when they are registered directly in the Step.

```text
Step starts
    |
    v
Reader.open(context) / Writer.open(context)
    |
    v
Read and write chunks
    |
    +--> update(context) at checkpoint save point
    |
    v
Step finishes or fails
    |
    v
Reader.close() / Writer.close()
```

If a Reader or Writer is wrapped inside a custom component, that component must forward the `ItemStream` lifecycle or register the delegate using `.stream(...)` on the Step builder. Otherwise, the delegate may not be opened, checkpointed, or closed properly.

## 3. Opening an input file with FlatFileItemReader

`FlatFileItemReader` reads a text file line by line and maps fields to objects. The commonly used builder is `FlatFileItemReaderBuilder`.

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

FlatFileItemReader<Order> reader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource("/data/in/orders.csv"))
                .encoding("UTF-8")
                .delimited()
                .names("orderId", "customerId", "amount")
                .targetType(Order.class)
                .linesToSkip(1)
                .saveState(true)
                .build();
```

Important configurations:

- `name(...)`: a stable name for the reader, used when storing state in the ExecutionContext.
- `resource(...)`: the source file to read.
- `encoding(...)`: the file charset; this should be explicitly declared rather than relying on the host machine's default encoding.
- `delimited()`: selects field delimiting; `names(...)` specifies the column names.
- `targetType(...)`: the object type created from each line.
- `linesToSkip(1)`: skips the header line if the file has a header.
- `saveState(true)`: enables saving read state for restart.

The example assumes a CSV file with three columns `orderId`, `customerId`, `amount` and a header on the first line. For CSV files containing commas inside quotes, quote characters, or newlines within fields, an appropriate tokenizer must be configured and the actual file format verified.

## 4. Opening an input file from JobParameters

In many Jobs, the input file varies per run. The path can be passed via JobParameters and `@StepScope` used to late-bind the value when the Step starts:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .linesToSkip(1)
            .strict(true)
            .saveState(true)
            .build();
}
```

`@StepScope` ensures the reader receives the `inputFile` of the current StepExecution. `strict(true)` requires the reader to fail if the resource does not exist or cannot be opened according to the reader's policy. This is useful behavior for mandatory files; if a file is optional, the missing-file case should be handled with an explicit validation Step or flow.

When launching the Job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.csv", true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

If the Job needs to restart, reuse the identifying parameter `inputFile` and ensure the file content at that path is still the data from the original run. Even better, use immutable files keyed by batch ID or store a file checksum/version to avoid mistakenly reading replaced content.

## 5. Validating the input file before the Step runs

A reader typically detects file-opening errors when `open()` is called. If you want to report a clear error before starting data processing, you can create a validation Step that checks the path, read permissions, and input format.

Example using Java NIO:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path inputPath = Path.of(inputFile).toAbsolutePath().normalize();

if (!Files.isRegularFile(inputPath)) {
    throw new IllegalArgumentException("Input file does not exist: " + inputPath);
}

if (!Files.isReadable(inputPath)) {
    throw new IllegalArgumentException("Input file is not readable: " + inputPath);
}
```

This check provides clear error messages, but it does not completely eliminate race conditions: the file could be deleted or modified after the check and before the Reader opens it. The Reader still needs to handle I/O errors when actually opening and reading the file.

If the path comes from an external request, do not allow callers to arbitrarily access any location on the filesystem. Restrict paths to an allowed directory, normalize the path, and verify it resides under the configured root directory. Do not log paths containing sensitive information unnecessarily.

## 6. Opening an output file with FlatFileItemWriter

`FlatFileItemWriter` writes items as text lines via a `LineAggregator`. The builder lets you specify the resource, encoding, header/footer, and policy for handling an existing file.

```java
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.core.io.FileSystemResource;

FlatFileItemWriter<ExportOrder> writer =
        new FlatFileItemWriterBuilder<ExportOrder>()
                .name("orderExportWriter")
                .resource(new FileSystemResource("/data/out/orders.csv"))
                .encoding("UTF-8")
                .lineAggregator(order -> String.join(",",
                        order.orderId(),
                        order.customerId(),
                        order.amount().toPlainString()))
                .headerCallback(output -> output.write(
                        "order_id,customer_id,amount"))
                .saveState(true)
                .shouldDeleteIfExists(true)
                .build();
```

The example uses a simple `LineAggregator` to illustrate converting an object into a line. If fields contain commas, quotes, or newline characters, proper CSV escaping/quoting or a dedicated CSV library must be used. Direct string concatenation should not be used for complex CSV data.

Important configurations:

- `name(...)`: a stable writer name for storing the write position in the ExecutionContext.
- `resource(...)`: the destination file.
- `encoding(...)`: the output file charset.
- `lineAggregator(...)`: converts each item into a line.
- `headerCallback(...)`: writes a header when creating a new file.
- `footerCallback(...)`: can write a footer/summary when the writer closes normally.
- `saveState(true)`: saves the write position to support restart.
- `shouldDeleteIfExists(true)`: configures existing-file handling to delete the old file before writing a new run; choose appropriately based on data requirements.

## 7. Handling existing output files: overwrite and append

Before opening the writer, decide clearly whether an old file should be overwritten, appended to, or cause the run to fail. These choices directly affect output data and restart behavior.

### Writing a new file or overwriting

When each batch needs to produce a new result file, `shouldDeleteIfExists(true)` can be configured to delete the old file before writing. A unique filename per batch ID can also be used to avoid overwriting results from another run.

```java
new FlatFileItemWriterBuilder<ExportOrder>()
        .name("orderExportWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(this::toCsvLine)
        .shouldDeleteIfExists(true)
        .saveState(true)
        .build();
```

### Appending to an existing file

`append(true)` allows appending content to an existing file. Use this only when business requirements truly demand appending, such as append-only logging with proper identification and deduplication mechanisms.

```java
new FlatFileItemWriterBuilder<ExportOrder>()
        .name("appendAuditWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(this::toCsvLine)
        .append(true)
        .saveState(true)
        .build();
```

Append is not a restart strategy. If a Job restarts and the writer has saved a checkpoint, Spring Batch needs to restore the exact write position of the previous execution. Do not rename the writer, swap the file, or manually append content outside the checkpoint mechanism between two runs. Test restart with the exact append configuration before using it in production.

### Refusing to overwrite

If an existing output file means results were already generated or need investigation, check the file before the Step and fail explicitly rather than deleting it. This approach is useful for handoff files that must be preserved for auditing.

Do not use the same output path for multiple concurrent JobExecutions. Two writers could open the file simultaneously and overwrite or interleave data. Generate separate filenames per batch ID/JobInstance or use locking at the orchestration layer.

## 8. Writing headers and footers

A writer can write a header when opening the file and a footer when closing the file:

```java
FlatFileItemWriter<ExportOrder> writer =
        new FlatFileItemWriterBuilder<ExportOrder>()
                .name("orderExportWriter")
                .resource(new FileSystemResource(outputFile))
                .encoding("UTF-8")
                .lineAggregator(this::toCsvLine)
                .headerCallback(output -> output.write(
                        "order_id,customer_id,amount"))
                .footerCallback(output -> output.write(
                        "# export completed"))
                .saveState(true)
                .shouldDeleteIfExists(true)
                .build();
```

Headers are typically written when starting a new file; do not manually write headers on every chunk. Footers are written when the writer closes during normal flow; if the Job fails or the process is killed, do not assume the footer is present.

If the footer contains a total item count, use an appropriate metric aggregation mechanism and verify it on restart. A footer does not replace JobExecution metadata and is not sole proof that the entire Job completed.

## 9. Dynamic output paths from JobParameters

Output files often need to be named by business date, tenant, or batch code. Use `@StepScope` to receive the parameter:

```java
@Bean
@StepScope
public FlatFileItemWriter<ExportOrder> orderExportWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    if (outputFile == null || outputFile.isBlank()) {
        throw new IllegalArgumentException("outputFile is required");
    }

    return new FlatFileItemWriterBuilder<ExportOrder>()
            .name("orderExportWriter")
            .resource(new FileSystemResource(outputFile))
            .encoding("UTF-8")
            .lineAggregator(this::toCsvLine)
            .headerCallback(output -> output.write(
                    "order_id,customer_id,amount"))
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
```

The output path can be constructed from identifying JobParameters, such as `/data/out/orders-2026-11-15.csv`. When restarting the same JobInstance, keep the same output path and ensure the file content has not been altered by another process so the writer restores its checkpoint accurately.

If the output path is only tracing metadata, do not arbitrarily make it an identifying parameter. Conversely, if the path identifies the exact result file for the unit of work, decide clearly whether it participates in identifying the JobInstance.

## 10. Ensuring the output directory exists and is writable

The writer needs a path that can be opened for writing. The parent directory must exist and the process running the Job must have permission to create files in that directory.

The directory can be checked and created in a separate preparation step:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path outputPath = Path.of(outputFile).toAbsolutePath().normalize();
Path parent = outputPath.getParent();

if (parent == null) {
    throw new IllegalArgumentException("Output path must have a parent directory");
}

Files.createDirectories(parent);

if (Files.exists(outputPath) && !Files.isWritable(outputPath)) {
    throw new IOException("Output file is not writable: " + outputPath);
}

if (!Files.isWritable(parent)) {
    throw new IOException("Output directory is not writable: " + parent);
}
```

The code above is a basic permission check example; actual permissions also depend on the process user, ACLs, mounts, and operating system. A preflight check does not eliminate subsequent I/O errors, so the Writer still needs to handle exceptions when opening or writing the file.

If the output directory is configured from external input, restrict the path to an allowed root directory. Use `normalize()` and verify that the normalized path still resides within the root directory to prevent path traversal.

## 11. Checkpoints and restart of file readers/writers

`FlatFileItemReader` and `FlatFileItemWriter` support saving state via `ExecutionContext` when `saveState(true)`. For a reader, state typically includes the read position; for a writer, state can include the write position to resume the file on restart.

Example restart flow:

```text
JobExecution #1
  Chunk 1 -> write output -> COMMIT
  Chunk 2 -> write output -> COMMIT
  Chunk 3 -> error -> ROLLBACK
       |
       v
JobExecution #2 (restart same JobInstance)
  Reader restores position after Chunk 2
  Writer restores committed file position
  Continue Chunk 3
```

For reliable restart:

1. Use stable Reader/Writer names across runs.
2. Enable state saving if checkpointing is needed.
3. Keep identifying JobParameters and corresponding file paths unchanged.
4. Do not modify the input file content between the initial run and restart.
5. Do not delete or modify the output file while the Job is running or awaiting restart.
6. Ensure the Step actually manages the Reader/Writer through the ItemStream lifecycle.

If `saveState` is disabled, the Reader/Writer will not save checkpoints in the standard way. On restart, they may start over from the beginning or fail to restore the right position. Only disable state saving when the component does not need restart or the application manages position and consistency itself.

## 12. Output files and database transactions

`FlatFileItemWriter` supports coordinating file writes with the chunk transaction through the writer's transactional mechanism. However, files on the filesystem and a database are not always a single shared transactional resource capable of atomic rollback.

Example of a chunk that both updates a database and writes a file:

```text
Chunk transaction
    |
    +--> UPDATE database
    +--> write output file buffer
    |
    v
Transaction commit
```

When a transaction rolls back, a transactional writer can avoid flushing buffered data to the file according to its behavior. However, do not generalize that every filesystem operation rolls back alongside the database. If a Tasklet manually copies, renames, or deletes files, those operations are not automatically undone by a database transaction.

For critical handoff files, a safe pattern is to write to a temporary file such as `orders.csv.part`, complete the Job, and then use a separate publish step to rename it to the final file. Publish the final file only when the Job has completed and size/checksum can be verified. Atomic rename is only guaranteed under certain filesystem conditions, typically requiring source and destination files to reside on the same filesystem.

Do not allow consumers to read an output file while the Job is still writing. Batch status, temporary filenames, or a completion manifest can be used so consumers know when the file is ready.

## 13. Closing files and handling I/O errors

Spring Batch calls `close()` on registered ItemStreams when the Step finishes. Closing files releases file handles and gives the writer a chance to complete closing operations such as footers or buffer flushes.

I/O errors can occur at several points:

- The file does not exist or lacks read permission when the Reader opens it.
- Disk full or quota exceeded when the Writer writes.
- Network filesystem disconnection.
- The file is deleted or replaced by another process.
- The process is killed before `close()` completes.

Do not manually close the internal stream of `FlatFileItemReader`/`FlatFileItemWriter` inside a Processor or another Tasklet. Let the Step manage the lifecycle. If implementing a custom ItemStream, ensure `close()` is safe when called after an error and releases all opened resources.

If an error occurs during `close()`, the Step may not finish successfully as expected. Log sufficient details including file info, StepExecution ID, and exception; avoid logging full file paths if they contain sensitive data.

## 14. When Reader/Writer is wrapped in another component

Some applications use decorators, composite readers/writers, or custom adapters. If the delegate implements `ItemStream`, its lifecycle must be forwarded.

Example Step registering a separate stream:

```java
return new StepBuilder("importStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(customReader)
        .writer(writer)
        .stream(delegateFileReader)
        .build();
```

The example assumes `customReader` wraps `delegateFileReader` without implementing/forwarding `ItemStream` itself. Registering the delegate with `.stream(...)` lets the Step invoke the corresponding lifecycle methods. If the wrapper already implements `ItemStream` and fully forwards `open`, `update`, and `close`, there is no need to register the delegate again.

Do not manage the lifecycle twice. Registering the same stream both through a wrapper and directly can cause duplicate open/close calls or unexpected state.

## 15. Testing opening input and output files

Testing should cover valid files, missing files, encoding, headers, existing output, and restart.

Useful scenarios:

1. **Reader reads a valid file:** verify item count, field mapping, and encoding.
2. **Reader does not find the file:** verify the Step fails with a clear message when `strict(true)`.
3. **Reader skips header:** verify the first line does not become a data item.
4. **Writer creates a new file:** verify header, line count, line separator, and encoding.
5. **Output already exists:** verify overwrite, append, or fail behavior matches the policy.
6. **Restart mid-file:** fail the Job after several committed chunks, restart the same JobInstance, and verify the reader/writer resume at the right position.
7. **Disk/permission failure:** verify the Step handles I/O errors and sets the appropriate Job status.
8. **Two concurrent Jobs:** verify they do not unintentionally write to the same output path.

Example using JUnit and a temporary directory:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExportFileTest {

    @TempDir
    Path tempDir;

    @Test
    void createsOutputFile() throws Exception {
        Path output = tempDir.resolve("orders.csv");

        // Launch test Step/Job with output path pointing to output.

        assertTrue(Files.exists(output));
        assertEquals("order_id,customer_id,amount",
                Files.readAllLines(output).get(0));
    }
}
```

This is an illustrative skeleton; launching the Job needs to be wired to the application's test configuration and `JobLauncherTestUtils`. For restart tests, keep the same identifying parameters and output path between the two launches, then verify the final file neither loses committed lines nor duplicates lines from reprocessed chunks.

## 16. Common Pitfalls

| Pitfall | Cause | Resolution |
|---|---|---|
| Using `ClassPathResource` as output | Resources in classpath/JAR are usually not writable. | Use `FileSystemResource` for output files. |
| Not declaring encoding | Default encoding may differ across environments. | Specify UTF-8 or the charset per data contract. |
| Not using `@StepScope` with dynamic paths | A singleton bean does not receive the execution's JobParameters properly. | Use `@StepScope` and SpEL. |
| Reader/writer name changes across restarts | ExecutionContext keys no longer match the old checkpoint. | Keep names stable throughout the Job lifecycle. |
| Deleting output file on restart | Data written in previously committed chunks is lost. | Choose overwrite for new runs and keep the file when restarting the same instance. |
| Appending to the same output across multiple executions | Data may be appended twice or interleaved. | Generate separate output paths per batch/JobInstance. |
| Input file replaced between runs | Old checkpoints may point to different content. | Use immutable files, checksums, or versions. |
| Not creating the output directory | Writer cannot open the file. | Create/verify the directory in a preparation step. |
| Wrapper not forwarding ItemStream | Delegate Reader/Writer is not opened, checkpointed, or closed properly. | Implement the lifecycle or register `.stream(delegate)`. |
| Assuming database rollback rolls back all file operations | The filesystem does not necessarily participate in database transactions. | Use temporary files, an outbox/manifest, and a separate publish step. |

## Conclusion

Spring Batch opens and closes files through Readers/Writers that implement `ItemStream`, with `open()` when the Step starts, `update()` to save checkpoints, and `close()` when the Step finishes. Use the appropriate `Resource`: `FileSystemResource` for filesystem files and `ClassPathResource` primarily for reading packaged resources. `FlatFileItemReader` and `FlatFileItemWriter` need stable names, explicit encoding, and `saveState(true)` when restart is required. For paths that vary per run, use `@StepScope` and JobParameters. Clearly choose overwrite/append behavior, ensure directories and access permissions, keep input/output files consistent across restarts, and never assume filesystem operations roll back atomically with the database.
