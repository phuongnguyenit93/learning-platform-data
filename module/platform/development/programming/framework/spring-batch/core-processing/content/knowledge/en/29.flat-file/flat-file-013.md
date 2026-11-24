# FlatFileItemWriter

In Spring Batch, **FlatFileItemWriter** writes items from a chunk as lines of text into a file. The writer takes processed objects, converts each object into a line `String` via a `LineAggregator`, encodes that line into bytes, and writes it to the target `Resource`.

FlatFileItemWriter is commonly used to produce CSV, tab-delimited, fixed-width, or custom text files conforming to a data exchange contract. To write files reliably, you must properly configure the resource, item-to-line conversion, encoding, headers/footers, existing-file policies, transactions, and restart checkpoints.

## 1. Position of FlatFileItemWriter in chunk processing

In a chunk-oriented Step, ItemReader reads data, ItemProcessor transforms items, and ItemWriter writes results:

~~~text
Input resource
     |
     v
ItemReader
     |
     v
ItemProcessor
     |
     v
Chunk of output items
     |
     v
FlatFileItemWriter
     |
     v
Output file
~~~

For example, a Job reads orders from a database, recalculates totals, and exports a file for the accounting system. The reader returns OrderInput, the processor produces OrderExport, and FlatFileItemWriter writes each OrderExport as a line.

FlatFileItemWriter is responsible for writing lines and managing file state within the Step lifecycle. It does not itself decide business rules for turning an Order into columns; that belongs to LineAggregator and FieldExtractor or the corresponding conversion logic.

## 2. Basic writer configuration

In Spring Batch 5, you can create the writer using FlatFileItemWriterBuilder:

~~~java
@Bean
public FlatFileItemWriter<OrderExport> orderExportWriter(
        Resource outputFile) {

    return new FlatFileItemWriterBuilder<OrderExport>()
            .name("orderExportWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerCode() + ","
                    + order.getTotalAmount())
            .saveState(true)
            .build();
}
~~~

Key parts:

- **name**: stable name of the writer, used when saving state in ExecutionContext.
- **resource**: the file or Resource the writer writes to.
- **encoding**: charset used to encode Strings into bytes.
- **lineAggregator**: converts each item into a line.
- **saveState(true)**: enables the writer to persist progress for restart.

LineAggregator is mandatory because the writer needs to know how to represent an item as text. For complex CSV files, avoid arbitrary string concatenation; explicitly define quoting, escaping, null handling, and number/date formatting rules.

## 3. Output resources

FlatFileItemWriter writes to a Spring Resource. For filesystem files, FileSystemResource is commonly used:

~~~java
Resource outputFile =
        new FileSystemResource("output/orders.csv");
~~~

The parent directory must exist and the application must have write permissions. The writer does not automatically create the entire directory tree in every situation. Prepare the output directory before the Step opens the writer.

If the path comes from JobParameters, use late binding:

~~~java
@Bean
@StepScope
public FlatFileItemWriter<OrderExport> orderExportWriter(
        @Value("#{jobParameters['outputFile']}") String outputPath) {

    return new FlatFileItemWriterBuilder<OrderExport>()
            .name("orderExportWriter")
            .resource(new FileSystemResource(outputPath))
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerCode() + ","
                    + order.getTotalAmount())
            .saveState(true)
            .build();
}
~~~

@StepScope defers creating the writer until a StepExecution is active, when JobParameters can be resolved. This is useful when separate runs use different output files or when partitioned workers write their own files.

Do not use classpath resources as regular output files because resources inside a JAR are usually not writable. Choose a writable resource and verify permissions in the deployment environment.

## 4. LineAggregator converts items into lines

LineAggregator is an abstraction that takes an item and returns a String representing the line to write:

~~~java
public interface LineAggregator<T> {
    String aggregate(T item);
}
~~~

A simple LineAggregator can be a lambda:

~~~java
.lineAggregator(order ->
        order.getOrderId() + ","
        + order.getCustomerCode() + ","
        + order.getTotalAmount())
~~~

This works well for small examples and simple data. When there are many fields, complex formatting, or escaping, extract the logic into a dedicated LineAggregator for easier testing and maintenance.

Spring Batch provides several common implementations:

| Implementation | Purpose |
| --- | --- |
| PassThroughLineAggregator | Writes the item directly as a String |
| DelimitedLineAggregator | Joins fields with a delimiter |
| FormatterLineAggregator | Formats fields using a format string |
| Custom LineAggregator | Applies custom rules such as quoting, escaping, or special layouts |

## 5. Using FieldExtractor and DelimitedLineAggregator

When items are Java objects, FieldExtractor extracts the values to write from the object. DelimitedLineAggregator joins those values with a delimiter.

Example:

~~~java
BeanWrapperFieldExtractor<OrderExport> extractor =
        new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
        "orderId",
        "customerCode",
        "totalAmount"
});

DelimitedLineAggregator<OrderExport> aggregator =
        new DelimitedLineAggregator<>();
aggregator.setDelimiter(",");
aggregator.setFieldExtractor(extractor);
~~~

Pass the aggregator to the writer:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .encoding("UTF-8")
        .lineAggregator(aggregator)
        .build();
~~~

BeanWrapperFieldExtractor reads properties by name. The properties must exist and be accessible via matching getters. The order of names in setNames determines column order.

For example, if you declare:

~~~java
extractor.setNames(new String[] {
        "orderId", "customerCode", "totalAmount"
});
~~~

the generated line follows the order:

~~~text
orderId,customerCode,totalAmount
~~~

DelimitedLineAggregator helps join fields, but do not assume it performs full standard CSV escaping for every value. If fields can contain commas, double quotes, or newlines, use an aggregator with explicit quoting/escaping rules or a suitable CSV library.

## 6. Creating safe CSV with quoting and escaping

Valid CSV must protect delimiters appearing inside field values. Under common CSV rules, fields containing commas, double quotes, or newlines are enclosed in double quotes; internal double quotes are doubled.

Example:

~~~text
1001,"Nguyen, An",250000
1002,"Customer said ""OK""",180000
~~~

You can write a simple aggregator if your application's CSV format only requires basic rules:

~~~java
public class OrderCsvLineAggregator
        implements LineAggregator<OrderExport> {

    @Override
    public String aggregate(OrderExport order) {
        return String.join(",",
                quote(order.getOrderId()),
                quote(order.getCustomerCode()),
                quote(order.getCustomerName()),
                quote(order.getTotalAmount().toPlainString()));
    }

    private String quote(String value) {
        String safeValue = value == null ? "" : value;
        return "\"" + safeValue.replace("\"", "\"\"") + "\"";
    }
}
~~~

This example quotes every field. Null values are converted to empty strings; if the system needs to distinguish null from an empty string, define a distinct representation. You must also decide how to handle newlines and control characters per the file contract.

For critical interchange files, prefer a dedicated CSV library to handle edge cases cleanly. Do not treat comma-joining strings as a complete CSV writer.

## 7. Writing fixed-width files

Not every text file is CSV. Some systems require fixed-width fields—for instance, a 10-character customer code, 30-character name, and 12-character amount.

You can use FormatterLineAggregator together with FieldExtractor:

~~~java
BeanWrapperFieldExtractor<CustomerExport> extractor =
        new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
        "customerCode",
        "customerName",
        "balance"
});

FormatterLineAggregator<CustomerExport> aggregator =
        new FormatterLineAggregator<>();
aggregator.setFormat("%-10s%-30s%012.2f");
aggregator.setFieldExtractor(extractor);
~~~

Then configure the writer with the aggregator:

~~~java
return new FlatFileItemWriterBuilder<CustomerExport>()
        .name("customerFixedWidthWriter")
        .resource(outputFile)
        .encoding("UTF-8")
        .lineAggregator(aggregator)
        .build();
~~~

The format string must match the actual data types. Check character lengths, byte widths, and padding rules of the receiving system. With UTF-8, characters can vary in byte count, so fixed-width by characters is not necessarily identical to fixed-width by bytes.

If a partner requires each record to have an exact byte count, determine the encoding and measure length after encoding. Do not rely solely on String.length().

## 8. Headers and footers

FlatFileItemWriter supports callbacks to write content at the beginning and end of a file.

### Header callback

HeaderCallback writes a title line or metadata when the writer opens the file:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .encoding("UTF-8")
        .headerCallback(writer ->
                writer.write("orderId,customerCode,totalAmount"))
        .lineAggregator(order ->
                order.getOrderId() + ","
                + order.getCustomerCode() + ","
                + order.getTotalAmount())
        .build();
~~~

The header must follow the same encoding and line format as the data section. If the file has no header per the contract, do not configure this callback.

### Footer callback

FooterCallback writes trailing content when the writer closes:

~~~java
.footerCallback(writer ->
        writer.write("END_OF_FILE"))
~~~

The footer can hold a total record count or an end marker. If a total record count is needed, obtain it from properly managed state rather than a static variable shared across JobExecutions.

The footer is tied to the writer-close lifecycle. Do not treat the presence of a footer as sole proof that the entire Job succeeded. Check BatchStatus, ExitStatus, and the file publish workflow before treating output as ready for consumers.

During restarts or appends, test header/footer behavior with your actual configuration to avoid duplicate headers or mid-file footers.

## 9. Encoding and line separators

The writer encodes String lines into bytes using the configured charset. Specify encoding explicitly:

~~~java
.encoding("UTF-8")
~~~

If unconfigured, the writer may fall back to the runtime's default charset. Results can differ between developer machines and production.

The line separator determines how each line ends. Choose LF or CRLF according to the receiving system's requirements:

~~~java
.lineSeparator("\n")
~~~

Or:

~~~java
.lineSeparator("\r\n")
~~~

Encoding and line separator are two independent settings. UTF-8 does not force LF; a UTF-8 file can certainly use CRLF.

For files containing Vietnamese characters, test byte output in UTF-8. If the receiving system requires a legacy charset, verify that every character to be written can be represented in that charset.

## 10. Policies when the file already exists

When a Step runs, the output file may already exist from a prior run or another process. The writer must be configured explicitly for how to handle it.

Common strategies:

| Strategy | Meaning | When appropriate |
| --- | --- | --- |
| Write new file and delete old one | Creates a clean output for a new run | Each JobInstance produces its own output file |
| Append | Appends to the end of an existing file | Output is designed to accumulate records across runs |
| Reject existing file | Protects prior data and prevents accidental overwrite | Filenames must be unique or publish is strictly controlled |

Example telling the writer to delete an existing file when starting a new run:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .shouldDeleteIfExists(true)
        .lineAggregator(order -> toCsv(order))
        .build();
~~~

If you want to append to an existing file, enable the writer's append mode (such as setAppendAllowed(true) on the writer) and configure existing-file retention consistently. Do not combine append with file deletion in contradictory ways.

Distinguish a brand-new run from a restart of the same JobInstance. Restart must use saved state to resume at the exact offset; a new run may need a fresh file or append depending on business rules. Never delete the file before a restart, as that destroys data from already-committed chunks.

## 11. shouldDeleteIfEmpty

In some pipelines, there is no reason to keep an output file when zero items were written. The writer supports the shouldDeleteIfEmpty policy:

~~~java
.shouldDeleteIfEmpty(true)
~~~

When enabled, the writer can delete the file if no data was written according to implementation conditions. Test cases where the file has only a header or a footer, because the definition of “empty” can interact with item counts and lifecycle callbacks.

Do not enable it indiscriminately if the receiving system expects an empty file to signal a zero-record batch. Confirm the output contract before choosing.

## 12. Transactional writing and rollback

By default, FlatFileItemWriter supports chunk-transactional writing through a buffer mechanism. On transaction commit, buffered data is written to the file. On transaction rollback, uncommitted writes can be discarded instead of leaving rows from a failed chunk behind.

~~~text
Chunk transaction
     |
     +-- FlatFileItemWriter receives items
     |
     +-- Writes to transactional buffer
     |
     +-- On COMMIT
     |      |
     |      +--> Flush chunk data to file
     |
     +-- On ROLLBACK
            |
            +--> Discard uncommitted data from buffer
~~~

Transactional behavior can be adjusted via the writer's transactional setting. If transaction buffering is disabled, data may be written directly to the file; when a chunk rolls back, already-written lines can remain in the output.

Only disable buffering if you understand the consequences and have a matching recovery strategy. For typical batch outputs, keeping default transactional behavior is safer.

### Files and databases do not automatically form a distributed transaction

FlatFileItemWriter's transactional buffering coordinates file writes with chunk transactions per the writer's mechanism. It does not turn a file and a database into a shared XA resource.

If a chunk writes to both a database and a file, you must still consider cases where one resource commits while the other fails. For high-reliability file exports, a common pattern is:

1. Write the file to a temporary path scoped to the JobExecution.
2. Complete the Step and verify the Job/business outcome.
3. Validate the file, size, record count, or checksum.
4. Move the temporary file to the official filename via an appropriate publish operation.
5. Only afterward notify the receiving system.

This prevents consumers from reading a partially written file. Whether rename is atomic depends on the filesystem and source/target locations.

## 13. saveState and restart

FlatFileItemWriter can store state in ExecutionContext for restart. Set a stable writer name and enable saveState:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .lineAggregator(order -> toCsv(order))
        .saveState(true)
        .build();
~~~

The writer saves necessary progress information, typically including file position at the checkpoint. When the Job restarts under the same JobInstance, the writer reopens the file and resumes from the last committed position.

Example with chunk size 100:

~~~text
Chunk 1: write records 1-100     -> COMMIT
Chunk 2: write records 101-200   -> COMMIT
Chunk 3: write records 201-300   -> ROLLBACK

Writer checkpoint: after record 200

Restart:
  resume from position after record 200
  re-write records 201 onward
~~~

Do not delete or replace the output file between the initial run and restart. Do not change the writer name, output path, or format while an old JobInstance still needs restarting unless a compatibility plan is in place.

### saveState(false)

If saveState is disabled, the writer does not store a position for recovery:

~~~java
.saveState(false)
~~~

This can fit writers that do not need restart or when the application uses an alternate recovery mechanism. However, if the Step fails and is restarted, the writer will not know where to resume. It risks rewriting from the beginning, writing duplicates, or writing at the wrong offset.

Do not disable saveState merely to avoid metadata if the Job needs restartability. Test actual behavior with the exact writer and resource.

## 14. Writer name and ExecutionContext

The writer name must be stable and unique within any Step that saves state. Spring Batch uses this name as part of the namespace for ExecutionContext keys.

If two writers in the same Step share the same name, their state can collide. If you rename a writer between the initial run and restart, the writer will not find its old checkpoint.

With partitioning, each worker has its own StepExecution, so each writer needs its own resource or a safe file-writing strategy. Never let multiple workers write to the same file using independent writers without proper synchronization and a compatible output format.

## 15. Append and restart

Append decides how to treat an existing file when opening the writer. Restart decides how to resume an execution that already has a checkpoint. These two concepts are related yet distinct.

Key principles:

- New runs append when output is designed to accumulate data across runs.
- Restarting the same JobInstance must rely on saved state, not blindly appending at EOF.
- If a file is created per JobExecution, use a stable path for restarts of that execution.
- If multiple JobInstances write to a single file, use locking or coordination to prevent interleaved lines.
- If output is published by date or batch ID, tie filenames to stable business keys.

Do not treat shouldDeleteIfExists(false) as a complete restart mechanism. Configure append, saveState, writer name, and JobParameters consistently, and test both fresh runs and restarts.

## 16. Footers, headers, and restart

Headers and footers are special content outside items:

- Headers are usually written when opening a new output file.
- Footers are written during writer close.
- When appending or restarting, avoid duplicating headers mid-file.
- If a Step fails, never use the footer as the sole indicator of a complete file.

If the file needs a footer with a total record count, ensure the count is restored properly across restarts or computed from committed data. If the footer is written on close, test Job failures, rollbacks, and restarts matching the application's exact lifecycle.

A safe operational option is writing a temporary file, verifying Job status, and publishing the finished file only after the Job ends successfully per business rules.

## 17. Writing empty files and header-only files

Some Jobs find zero matching items. Define the desired output explicitly:

- Create no file.
- Create a file containing only the header.
- Create an empty file with no header.
- Create a file with a footer and zero-record statistics.

Header/footer callbacks and shouldDeleteIfEmpty can all affect the final output. Test the exact combination instead of checking Step status alone.

If the receiving system relies on file existence as a signal that the batch completed, specify the zero-record behavior clearly. Do not delete empty files if a missing file would be misinterpreted as the batch never running.

## 18. Writing multiple files with MultiResourceItemWriter

FlatFileItemWriter writes to a single Resource. If output must be split across multiple files by item count, size, or data group, use MultiResourceItemWriter with FlatFileItemWriter as its delegate.

Skeleton example:

~~~java
@Bean
public MultiResourceItemWriter<OrderExport> multiOrderWriter(
        FlatFileItemWriter<OrderExport> delegate,
        Resource outputDirectory) {

    return new MultiResourceItemWriterBuilder<OrderExport>()
            .name("multiOrderWriter")
            .resource(outputDirectory)
            .delegate(delegate)
            .itemCountLimitPerResource(10000)
            .resourceSuffixCreator(index ->
                    String.format("-%03d.csv", index))
            .build();
}
~~~

In real deployments, the base resource and suffix assembly must fit your MultiResourceItemWriter version; this example illustrates the configuration structure. The delegate writer still requires appropriate lineAggregator, encoding, and state configuration.

On restart, resource ordering, suffixes, and input ordering must remain deterministic so the writer resumes the right file. If multiple partitions create files, include the partition ID or business key in filenames to avoid overwrites.

## 19. Thread safety and partitioning

FlatFileItemWriter holds state including its resource, write position, buffers, and lifecycle. Do not assume a single instance can safely accept concurrent write calls from multiple threads.

In a multi-threaded Step:

- Multiple threads may invoke the writer simultaneously.
- Lines can interleave if the writer is unsynchronized.
- Write position state and checkpoints may no longer reflect intended order.
- A chunk rollback can interfere with another thread's data if transactions and writers are not designed together.

If a shared writer is required in a multi-threaded environment, consider a synchronizing decorator such as SynchronizedItemStreamWriter when compatible with your version and Step semantics. Synchronization reduces throughput and does not solve every transaction or business-ordering concern.

With partitioning, a cleaner option is having each partition write its own separate file:

~~~text
partition0 -> orders-part-000.csv
partition1 -> orders-part-001.csv
partition2 -> orders-part-002.csv
                  |
                  v
             merge/publish
~~~

After all partitions complete, a separate Step can merge or publish the files. This avoids multiple workers writing to the same resource concurrently.

## 20. forceSync and data durability

The writer has a forceSync option to request OS-level storage synchronization according to implementation capabilities. Enabling forceSync can improve durability against sudden process or OS crashes, at the cost of extra I/O and potentially lower throughput.

~~~java
.forceSync(true)
~~~

Do not enable it just to make writes feel “100% safe.” Force sync does not create distributed transactions, does not guarantee the filesystem or storage hardware cannot fail, and does not replace backups, checksums, or atomic publishing.

Choose based on durability requirements and benchmark performance on real storage.

## 21. Closing the writer and managing file lifecycle

FlatFileItemWriter must be opened, state-updated, and closed by Spring Batch. Never close the writer from a processor or service while the Step is still active.

Overview of the lifecycle:

~~~text
Step starts
    |
    v
Writer.open(ExecutionContext)
    |
    v
Writer.write(chunk)
    |
    v
Writer.update(ExecutionContext)
    |
    v
Commit / rollback
    |
    v
Repeat for chunks
    |
    v
Writer.close()
~~~

When the Step finishes, the framework invokes the appropriate lifecycle methods to release resources. If wrapping the writer in a decorator, ensure ItemStream lifecycle callbacks are forwarded to the delegate. Otherwise, the writer may fail to open, fail to save checkpoints, or fail to close properly.

Never point two concurrently running JobExecutions at the same output path without coordination. Two writers can overwrite, interleave data, or corrupt each other's checkpoints.

## 22. Observing and verifying output

After the Step runs, verify both Batch status and file contents:

- Are JobExecution and StepExecution COMPLETED?
- Does ExitStatus carry any custom codes or warnings?
- Do read, write, filter, and skip counts match expectations?
- Does the file exist with a reasonable size?
- Are headers/footers accurate and non-duplicated?
- Do encoding, delimiter, quoting, and line separators match the contract?
- Was a partial file left behind after a failure?
- Do checksums or record counts match the source?

You can use JobExplorer to inspect StepExecution and its counters. File verification should happen in a dedicated verification/publish step when the file is a critical output.

Never manually edit JobRepository metadata or truncate files to force a restart without first verifying checkpoints and committed data.

## 23. Common pitfalls

### Missing LineAggregator configuration

The writer does not know how to convert items into lines. Configure a LineAggregator matching the output format.

### Joining CSV with commas without escaping

Fields containing commas, quotes, or newlines shift columns. Use an aggregator with explicit CSV rules or a CSV library.

### Relying on the default charset

Files vary across environments. Declare encoding explicitly.

### Writing to a nonexistent directory or lacking permissions

The writer fails to open the resource. Prepare directories and permissions before the Step runs.

### Deleting existing files on restart

This can destroy data from committed chunks. Distinguish fresh runs from restarts of the same JobInstance.

### Uncontrolled appending

Can duplicate headers, duplicate records, or mix data from two different JobInstances. Use clear business keys, output paths, and state.

### Disabling saveState while expecting restart

The writer has no checkpoint to restore its position. Keep saveState enabled or implement a custom recovery mechanism.

### Using a singleton writer across concurrent StepExecutions

State and file resources get shared. Use Step scope or separate writer/resource instances per execution.

### Multiple partitions writing to the same file

Lines interleave or state collides. Write separate files per partition and merge afterward.

### Assuming transaction buffering makes files and databases atomic

Writer buffering protects chunk writes per the writer's mechanism, but it does not create XA across file and database. Use staging/publish or idempotency when needed.

### Treating the footer as a Job success signal

Footers belong to writer lifecycle. Check Job status and the publish workflow before announcing output.

### Failing to test unrepresentable characters

Limited charsets can lose characters. Verify the encoder and round-trip behavior against the contract.

## 24. FlatFileItemWriter design checklist

When building a file-export Step, determine:

1. Which file is the output Resource, and does the directory exist with write permissions?
2. Is each item formatted as CSV, fixed-width, or a custom text layout?
3. In what order does FieldExtractor extract properties?
4. Do delimiters, quotes, and newlines need quoting/escaping?
5. What charset and line separator does the receiving system require?
6. Are headers or footers needed?
7. When an output file already exists, should it be deleted, appended, or rejected?
8. Should an empty output file be kept when there are zero items?
9. Does the writer need default transactional buffering?
10. Are saveState and the writer name stable for restart?
11. Will multiple JobExecutions or partitions write files concurrently?
12. Are temporary staging files, checksums, record counts, and a publish step required?
13. Is the file confirmed successful based on BatchStatus, ExitStatus, or specific business checks?

Test new files, existing files, chunk rollbacks, restarts after committed chunks, empty outputs, fields with delimiters/quotes/newlines, Unicode characters, appends, multiple partitions, and process crashes mid-write. Verify the final output bytes using the receiving system's exact charset and parser whenever possible.

## Conclusion

FlatFileItemWriter writes items as text lines via LineAggregator and encodes Strings into bytes using the configured encoding. A reliable writer requires a writable resource, contract-compliant line formatting, controlled headers/footers, an explicit existing-file policy, transactional buffering, and saveState configured for restarts. For CSV, handle quoting and escaping; for fixed-width, distinguish character width from byte width. Never share a stateful writer across concurrent executions or partitions writing to one file. For critical outputs, write to a temporary staging file, verify status and contents, and only then publish to the receiving system.
