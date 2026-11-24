# Header and footer callbacks in Spring Batch

When exporting data to a file with Spring Batch, the output often needs extra information beyond the main data lines. A CSV file may begin with a report title, business date, and column names; the end of the file may contain a total record count, monetary sum, batch ID, or end marker. These sections are called the **header** and **footer**.

For **FlatFileItemWriter**, Spring Batch provides two dedicated callbacks: **FlatFileHeaderCallback** and **FlatFileFooterCallback**. The header callback writes content at the beginning of the file when the writer initializes the output file; the footer callback writes the trailing section when the writer closes the file. Each callback receives a framework-managed `Writer` and simply writes content to it.

Header and footer callbacks belong to the file writer's lifecycle. They are not item-level listeners, nor are they signals confirming that the entire Job succeeded. In particular, a writer may be closed along a Step's failure path; thus the footer callback can run even when the Job fails. If you need to officially publish a file or stamp a SUCCESS marker, do so in a separate publish step after processing steps succeed.

This lesson explains the contract of both callbacks, how to configure FlatFileItemWriter, how to build static and dynamic headers/footers, how to combine them with JobParameters and StepExecution, behavior on empty files or restarts, multi-file handling, and considerations around transactions, encoding, CSV escaping, and testing.

## 1. Headers and footers in batch files

An exported file often follows this structure:

~~~text
CUSTOMER EXPORT
Business date: 2026-11-15
customer_id,full_name,email
C001,An,an@example.test
C002,Binh,binh@example.test
C003,Chi,chi@example.test
TOTAL_RECORDS,3
END_OF_FILE
~~~

In this example, the opening lines are the header; the data rows are produced by ItemWriter and LineAggregator; the closing lines are the footer or trailer.

The header usually holds descriptive file metadata or column names. The footer usually holds record totals, value sums, checksums, or an end-of-file marker so the receiving system knows the content is complete.

Not every format requires both. A simple CSV may only need a column header row. A fixed interchange file may require a trailer per partner specification. Use callbacks when the file format demands leading or trailing sections.

## 2. The two callbacks provided by Spring Batch

Spring Batch provides two interfaces in its file support module:

~~~java
public interface FlatFileHeaderCallback {
    void writeHeader(Writer writer) throws IOException;
}
~~~

~~~java
public interface FlatFileFooterCallback {
    void writeFooter(Writer writer) throws IOException;
}
~~~

Both callbacks receive a java.io.Writer.

- The header callback writes the beginning of the file.
- The footer callback writes the end of the file.
- Callbacks do not receive items or chunks.
- Callbacks do not open the file themselves and do not own the Writer.
- Spring Batch manages the Writer lifecycle; callbacks only write content.

Typically, callbacks are configured directly on FlatFileItemWriter using the builder:

~~~java
.headerCallback(headerCallback)
.footerCallback(footerCallback)
~~~

Callbacks are part of the file writer. If you use another ItemWriter, such as JdbcBatchItemWriter, these methods do not exist. In that case, implement separate logic or use a writer that supports files.

### Do not close the Writer inside a callback

The Writer passed to the callback is managed by FlatFileItemWriter. Callbacks should only invoke write() to emit data.

Do not call close() on the Writer, do not open another FileWriter pointing to the same path, and do not delete or rename the file inside the callback. Closing or opening another writer can corrupt buffers, write order, or FlatFileItemWriter restart state.

## 3. When is the header callback invoked?

The header callback is invoked by FlatFileItemWriter while opening the output file when the writer determines the file head needs initialization. For a new or empty file, the callback writes the header before the first items.

Example:

~~~java
FlatFileHeaderCallback header = writer -> {
    writer.write("customer_id,full_name,email");
    writer.write(System.lineSeparator());
};
~~~

By the time the writer begins writing items, the header content is already placed ahead of the data rows.

The header callback does not run per item or per chunk. It belongs to the file-open lifecycle. When a file is reopened during a restart, behavior depends on file state, checkpoints, append settings, and writer version. Normally the writer resumes the existing file without inserting another header mid-file.

Do not rely on a blanket assumption that the callback always runs once per entire Job. Test the exact invocation count for restarts, appends, empty files, and multi-resource outputs.

## 4. When is the footer callback invoked?

The footer callback is invoked by FlatFileItemWriter while closing the output file:

~~~java
FlatFileFooterCallback footer = writer -> {
    writer.write("END_OF_FILE");
    writer.write(System.lineSeparator());
};
~~~

The footer is written after all data rows processed by the writer, right before the writer finishes closing the file. The footer callback is not invoked after every chunk; it is an end-of-lifecycle callback on the writer.

### Footer does not mean Job success

This is a critical design point for batch files.

Spring Batch closes registered ItemStreams when a Step terminates through the normal lifecycle, even if the Step fails with an exception. Because FlatFileItemWriter writes the footer during close, the footer callback can execute on a failure path.

Therefore, do not write content implying JOB_STATUS,SUCCESS simply because the footer callback was invoked.

If the file needs a technical trailer, you can write END_OF_FILE or the count of written records. If you need a marker confirming the file passed checks and was published successfully, create a publish Step that runs only after processing succeeds.

## 5. Configuring FlatFileItemWriter with header and footer

Complete example using FlatFileItemWriterBuilder:

~~~java
@Bean
FlatFileItemWriter<Customer> customerWriter(Resource outputResource) {

    BeanWrapperFieldExtractor<Customer> extractor =
        new BeanWrapperFieldExtractor<>();

    extractor.setNames(new String[] {
        "customerId",
        "fullName",
        "email"
    });

    DelimitedLineAggregator<Customer> aggregator =
        new DelimitedLineAggregator<>();

    aggregator.setDelimiter(",");
    aggregator.setFieldExtractor(extractor);

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(outputResource)
        .encoding(StandardCharsets.UTF_8.name())
        .lineSeparator(System.lineSeparator())
        .lineAggregator(aggregator)
        .headerCallback(writer -> {
            writer.write("customer_id,full_name,email");
            writer.write(System.lineSeparator());
        })
        .footerCallback(writer -> {
            writer.write("END_OF_FILE");
            writer.write(System.lineSeparator());
        })
        .saveState(true)
        .build();
}
~~~

Key parts:

- name sets a stable identifier for the writer, required for saving state.
- resource specifies the output file.
- encoding selects the charset.
- lineSeparator sets the line ending for records produced by LineAggregator.
- lineAggregator converts each item into a line.
- headerCallback writes the head of the file.
- footerCallback writes the end of the file.
- saveState(true) allows the writer to save state for restart.

In the example, the callbacks write line separators themselves. The writer's lineSeparator property applies to data lines emitted by the writer; callbacks write directly to the Writer, so include newlines whenever the format requires them.

## 6. Lambda header callbacks

Because the interface has a single abstract method, a callback can be declared as a lambda:

~~~java
.headerCallback(writer ->
    writer.write("id,name,email" + System.lineSeparator())
)
~~~

This works well for short, static headers with no dependencies.

If the header is long or has formatting logic, extract it into a dedicated bean for readability and testability:

~~~java
@Bean
FlatFileHeaderCallback customerHeaderCallback() {
    return writer -> {
        writer.write("CUSTOMER EXPORT");
        writer.write(System.lineSeparator());
        writer.write("customer_id,full_name,email");
        writer.write(System.lineSeparator());
    };
}
~~~

Then inject the callback into the writer:

~~~java
@Bean
FlatFileItemWriter<Customer> customerWriter(
        Resource outputResource,
        FlatFileHeaderCallback customerHeaderCallback) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(outputResource)
        .lineAggregator(customerLineAggregator())
        .headerCallback(customerHeaderCallback)
        .build();
}
~~~

Extracting the callback lets you reuse the format across writers and unit-test header output independently.

## 7. Lambda footer callbacks

A simple footer can also be written inline:

~~~java
.footerCallback(writer -> {
    writer.write("TOTAL_RECORDS,0");
    writer.write(System.lineSeparator());
})
~~~

This example is a static footer, suitable only when the value is genuinely constant. In practice, footers usually contain record counts or monetary totals. In that case, obtain aggregated values from Step state or a dedicated tracking component.

Do not recompute all source data inside the footer callback. The callback should only write the trailer from state already aggregated during processing.

## 8. Dynamic headers from JobParameters

A header may contain the business date, batch ID, or source system passed by the caller when launching the Job.

Example JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("batchId", "BATCH-20261115")
    .addString("sourceSystem", "CRM")
    .toJobParameters();
~~~

Declare a StepScope callback to late-bind these parameters:

~~~java
@Bean
@StepScope
FlatFileHeaderCallback customerHeaderCallback(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{jobParameters['sourceSystem']}") String sourceSystem) {

    return writer -> {
        writer.write("CUSTOMER EXPORT");
        writer.write(System.lineSeparator());
        writer.write("Business date: " + businessDate);
        writer.write(System.lineSeparator());
        writer.write("Batch: " + batchId);
        writer.write(System.lineSeparator());
        writer.write("Source: " + sourceSystem);
        writer.write(System.lineSeparator());
        writer.write("customer_id,full_name,email");
        writer.write(System.lineSeparator());
    };
}
~~~

Attach the callback to the writer:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Customer> customerWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        FlatFileHeaderCallback customerHeaderCallback,
        FlatFileFooterCallback customerFooterCallback) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(customerLineAggregator())
        .headerCallback(customerHeaderCallback)
        .footerCallback(customerFooterCallback)
        .saveState(true)
        .build();
}
~~~

@StepScope defers creating the callback and writer targets until a StepExecution exists. Thus the callback receives JobParameters for the current run.

### Validating required parameters

If businessDate or batchId is mandatory, validate against null and blank values before emitting the header. Do not silently write null into the file, because downstream systems might treat it as valid metadata.

JobParametersValidator can validate parameters before the Job runs; scoped callbacks should still guard the values they directly consume.

## 9. Dynamic headers from ExecutionContext

An earlier Step can inspect an input file and store metadata in JobExecutionContext. A subsequent export Step then uses late binding to write that metadata into its header.

Example of a prior Step saving the source version:

~~~java
contribution.getStepExecution()
    .getExecutionContext()
    .putString("sourceVersion", sourceVersion);

contribution.getStepExecution()
    .getExecutionContext()
    .putString("validatedFile", validatedFile);
~~~

If a later Step needs these keys, promote them to JobExecutionContext via ExecutionContextPromotionListener or write them directly to JobExecutionContext as appropriate.

Callback reading metadata:

~~~java
@Bean
@StepScope
FlatFileHeaderCallback exportHeaderCallback(
        @Value("#{jobExecutionContext['sourceVersion']}")
        String sourceVersion,
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    return writer -> {
        writer.write("SOURCE_VERSION," + sourceVersion);
        writer.write(System.lineSeparator());
        writer.write("INPUT_FILE," + validatedFile);
        writer.write(System.lineSeparator());
        writer.write("id,name");
        writer.write(System.lineSeparator());
    };
}
~~~

Do not read keys from JobExecutionContext if they were only written to the previous Step's StepExecutionContext without promotion. The two contexts have different scopes.

## 10. Footers containing the written record count

A footer commonly contains the total record count. Although the footer callback only receives a Writer, it can hold a reference to StepExecution to read counters when the callback executes.

Example:

~~~java
@Bean
@StepScope
FlatFileFooterCallback customerFooterCallback(
        @Value("#{stepExecution}") StepExecution stepExecution) {

    return writer -> {
        writer.write(
            "TOTAL_RECORDS," + stepExecution.getWriteCount()
        );
        writer.write(System.lineSeparator());
    };
}
~~~

The key detail is injecting the StepExecution object itself and calling getWriteCount() when the callback runs. Injecting a scalar number via stepExecution.writeCount at bean creation time may bind too early and fail to reflect the final counter.

The writeCount counter tracks items written according to StepExecution metadata. It does not necessarily equal the physical line count in the file if there are headers/footers, filtered items, skipped items, writers emitting multiple lines per item, or custom logic.

If the footer needs monetary sums, total quantities, or checksums, maintain an appropriate accumulator during processing and ensure it updates consistently with transactions and restarts. Do not substitute writeCount for another business aggregation.

### Footers should not declare success status

If a Step fails after several chunks, writeCount may be greater than 0 and the footer may still be written when the writer closes. That count reflects items written per StepExecution—it does not prove the entire Job succeeded.

You can emit a statistical trailer such as ROWS_WRITTEN, while adding any SUCCESS marker in a publish step after confirming Job/Step success.

## 11. Footers containing monetary totals or checksums

A financial report may require a total monetary amount at the end of the file. An accumulator can be maintained in the processor or writer.

Example aggregator component:

~~~java
public class ExportTotals {

    private long recordCount;
    private BigDecimal totalAmount = BigDecimal.ZERO;

    public void add(Invoice invoice) {
        recordCount++;
        totalAmount = totalAmount.add(invoice.amount());
    }

    public long recordCount() {
        return recordCount;
    }

    public BigDecimal totalAmount() {
        return totalAmount;
    }
}
~~~

Writer updating the accumulator as items are written:

~~~java
@Bean
ItemWriter<Invoice> invoiceWriter(
        FlatFileItemWriter<Invoice> delegate,
        ExportTotals totals) {

    return chunk -> {
        delegate.write(chunk);
        for (Invoice invoice : chunk.getItems()) {
            totals.add(invoice);
        }
    };
}
~~~

Footer callback writing the totals:

~~~java
@Bean
FlatFileFooterCallback invoiceFooter(ExportTotals totals) {
    return writer -> {
        writer.write("TOTAL_RECORDS," + totals.recordCount());
        writer.write(System.lineSeparator());
        writer.write("TOTAL_AMOUNT," + totals.totalAmount().toPlainString());
        writer.write(System.lineSeparator());
    };
}
~~~

This example illustrates data flow only. In a restartable or multi-threaded Job, ExportTotals must be designed to persist/restore and update safely. If the delegate writes, the accumulator updates, and then the transaction rolls back, the accumulator can drift from committed data. Update state upon chunk commit or compute totals from a durable data source after the Step completes.

For checksums, define the exact algorithm and byte/record ordering. If a whole-file checksum is needed, the safest approach is to compute it after the file closes, in a separate Step that reads the completed file.

## 12. Callbacks do not replace ItemListeners

Header/footer callbacks and item listeners operate at different scopes.

| Component | When invoked | Purpose |
|---|---|---|
| FlatFileHeaderCallback | When writer initializes file head | Write metadata/header |
| FlatFileFooterCallback | When writer closes file | Write trailer/footer |
| ItemReadListener | Before/after item read or on read error | Observe reader activity |
| ItemProcessListener | Before/after process or on process error | Observe processor |
| ItemWriteListener | Before/after write or on write error | Observe writer |
| StepExecutionListener | Before/after Step | Step-level stats and lifecycle |
| JobExecutionListener | Before/after Job | Job-level lifecycle |

The header callback is not called per item. The footer callback is not called per chunk either.

If you need to write an audit line per item, use an appropriate writer or listener. Do not put item-level logic inside header/footer callbacks.

## 13. Headers and footers must write their own newlines

The callback receives a Writer and writes directly. It does not receive LineAggregator and does not automatically turn callback text into a separated item line.

Correct example:

~~~java
.headerCallback(writer -> {
    writer.write("id,name,email");
    writer.write(System.lineSeparator());
})
~~~

Omitting the newline can cause the first item line to concatenate immediately after the header depending on how the writer emits separators, producing a malformed file.

Similarly for the footer:

~~~java
.footerCallback(writer -> {
    writer.write("END_OF_FILE");
    writer.write(System.lineSeparator());
})
~~~

Follow the file format's line-ending rules. You can use a fixed LF if required by a partner regardless of operating system, or System.lineSeparator() when OS-native endings are appropriate.

Do not assume FlatFileItemWriter's lineSeparator automatically applies to callback output; callbacks write directly to the Writer and must append separators themselves.

## 14. Headers/footers and CSV escaping

Header callbacks write raw text. They do not automatically escape commas, double quotes, or newlines inside dynamic values.

If metadata is a CSV field, apply the same quoting rules as data rows. Simple helper example:

~~~java
static String csvField(String value) {
    String escaped = value.replace("\"", "\"\"");
    return "\"" + escaped + "\"";
}
~~~

Then:

~~~java
writer.write(
    "SOURCE," + csvField(sourceSystem)
        + System.lineSeparator()
);
~~~

This helper handles basic CSV quoting, though actual formatting also depends on encoding, null handling, and the receiving system's conventions.

Do not concatenate untrusted data directly into headers/footers if it might contain newlines or control characters. Validate or encode values to avoid injecting spurious lines into the file.

## 15. Headers can hold column names or custom metadata

A header can be a CSV column-name row, multiple metadata rows followed by column names, a format version record, batch ID, business date, source system, or schema identifier so downstream selects the right parser.

Example:

~~~text
FORMAT_VERSION,2
BATCH_ID,BATCH-20261115
BUSINESS_DATE,2026-11-15
SOURCE,CRM
customer_id,full_name,email
~~~

If the receiving system accepts only a column-name header on the first line, do not prepend metadata to the header. Follow the downstream consumer's exact contract.

When supporting multiple file types or versions, include the schema version in the header so parsers can choose the matching mapping.

## 16. Footers can hold trailer records

Some file interchange systems require a trailer record:

~~~text
C001,An,100.00
C002,Binh,250.00
C003,Chi,50.00
TRL,3,400.00
~~~

A trailer may contain record count, monetary sum, batch ID, checksum, file creation date, format code, or end marker.

Distinguish between input item count, filtered count, skipped count, and actual lines written. The footer must use the exact metric defined by the specification.

For example, if the processor filters 10 items and the writer writes 90 items, the trailer usually must reflect 90 data records, not the 100 items the reader read. If the writer turns one item into multiple output lines, count output lines rather than writeCount.

## 17. Behavior on empty files

A Step may read 0 items. The writer can still be opened and closed according to the Step lifecycle, while the file contents depend on configuration and how callbacks are triggered.

Questions to decide explicitly:

- Does an empty file need a header?
- Should a footer be written when there are no items?
- Should a file even be created when the source has no data?
- Does downstream accept a file containing only header/trailer?
- Should the file be deleted if there are zero records?
- Is a zero-item file a valid success or missing input data?

Do not assume shouldDeleteIfEmpty behaves identically across every combination of header/footer callbacks. Test FlatFileItemWriter with empty inputs using your exact builder flags and Spring Batch version.

If the requirement is to produce no file when there are zero records, check the item count after the Step and handle file creation/removal in a separate Step. If the file must still contain a header, configure the writer and verify actual output.

## 18. Restart and the header callback

FlatFileItemWriter supports saving state for restart. When a Step fails after several committed chunks, the writer can restore its write position from ExecutionContext and resume writing the file.

Key principles:

- Set a stable writer name.
- Enable saveState when restart is required.
- Use the same output resource for the same JobInstance if restart must resume that file.
- Do not manually delete the file on restart.
- Do not enable append arbitrarily.
- Verify the header is not duplicated mid-file.
- Verify uncommitted output is handled properly with transactions and checkpoints.
- Never let two different JobExecutions write to the same path.

The header callback typically emits the header only when the writer initializes an empty file. On restart against an existing file, the writer restores state and continues appending data rather than re-inserting the header. However, exact behavior depends on appendAllowed, shouldDeleteIfExists, saveState, and file state; write integration tests to confirm.

### Do not manually write headers in beforeStep

When using FlatFileItemWriter, let the header callback manage the start of the file. Writing headers manually in a StepExecutionListener can duplicate headers on restart or when a Step reopens.

## 19. Restart and the footer callback

The footer callback is tied to close, so it must be understood in the context of restart.

When a Step fails through its normal lifecycle, the writer can be closed and the footer callback may write a trailer. If the Step is restarted, the writer relies on its state/checkpoint to restore the file. Uncommitted output or content written after the checkpoint may need to be handled by the writer's recovery mechanism.

Do not assume a footer written during a failed run will remain intact as the final footer. Nor should you assume the callback only runs when the Job succeeds.

Test these scenarios:

1. Step succeeds: file has header, details, and exactly one footer.
2. Step fails after one chunk: verify whether a footer is written on close.
3. Step restarts: file is restored properly with no stale footer left mid-data.
4. Step fails again: cleanup and footer do not produce unexpected duplicate content.
5. File is published: only files confirmed complete become official output.

If requirements dictate that trailers appear only on successful files, do not use the footer callback as a success marker. Add the success trailer in a publish Step after the writer closes the file and the Job flow confirms processing succeeded.

## 20. Footers and errors during close

A footer callback can throw IOException if writing the trailer fails. This error occurs while closing the writer and can be wrapped as an ItemStreamException or resource-close failure.

If writing the footer fails:

- The file may be missing its trailer.
- The Step may terminate as failed due to the close error.
- If the Step already encountered another exception, the close error may appear as a secondary error.
- The staging file should be retained or quarantined per policy.
- Never publish the file as a complete output.

Do not swallow IOException and treat the file as valid. Log it with the JobExecution ID, StepExecution ID, and file path.

## 21. Combining footer callbacks with StepExecution

If the footer needs Step metrics, inject the StepExecution object into a StepScope callback bean:

~~~java
@Bean
@StepScope
FlatFileFooterCallback footerCallback(
        @Value("#{stepExecution}") StepExecution stepExecution) {

    return writer -> {
        writer.write("READ_COUNT," + stepExecution.getReadCount());
        writer.write(System.lineSeparator());

        writer.write("WRITE_COUNT," + stepExecution.getWriteCount());
        writer.write(System.lineSeparator());

        writer.write("FILTER_COUNT," + stepExecution.getFilterCount());
        writer.write(System.lineSeparator());

        writer.write("SKIP_COUNT," + stepExecution.getSkipCount());
        writer.write(System.lineSeparator());
    };
}
~~~

The callback reads counters from StepExecution when invoked. This provides useful operational information, though trailer labels should be named clearly so downstream does not confuse Step metrics with file line counts.

If the callback is created outside StepScope or captures a scalar snapshot at Step startup, the metrics will not reflect final state. Late-binding the StepExecution object lets the callback read the latest state at execution time.

Never use the footer to determine Job success. A Job's BatchStatus can only be determined after Steps and flows finish.

## 22. MultiResourceItemWriter and per-file callbacks

When splitting output across multiple files, you can use MultiResourceItemWriter with FlatFileItemWriter as its delegate.

Conceptual example:

~~~java
@Bean
MultiResourceItemWriter<Customer> multiCustomerWriter(
        FlatFileItemWriter<Customer> customerDelegate,
        Resource outputResource) {

    return new MultiResourceItemWriterBuilder<Customer>()
        .name("multiCustomerWriter")
        .resource(outputResource)
        .delegate(customerDelegate)
        .itemCountLimitPerResource(1000)
        .resourceSuffixCreator(index ->
            "-" + index + ".csv"
        )
        .build();
}
~~~

In practice, the base resource must be a Resource matching the target directory and filename; suffix creator configuration should align with application conventions.

Because the delegate is opened/closed per resource on rollover, FlatFileItemWriter's header/footer callbacks run according to each file's lifecycle. Therefore, each output file can have its own header and trailer.

Verify via tests:

- Headers appear at the start of every file.
- Footers appear when the delegate closes each file.
- The final resource closes cleanly when the Step ends.
- Restart resumes the right file without creating duplicates.
- Each file carries its own record count if the trailer requires it.
- The file set is not published until all workers/resources finish.

If the trailer needs the grand total of records across the entire batch rather than per file, do not use the delegate's local writeCount without scoping awareness. Aggregate totals at the Step/Job level or in a verification step after all files close.

## 23. Distinguishing header/footer callbacks from domain file headers/trailers

Some systems refer to leading/trailing file metadata as business headers and trailers. They may have their own schemas:

~~~text
HDR|FORMAT-02|BATCH-123|20261115
DTL|C001|100.00
DTL|C002|250.00
TRL|2|350.00
~~~

In these cases, callbacks can write HDR and TRL records. However, verify:

- Does the header record require a fixed record type code?
- Does the trailer count detail records or input items?
- Do monetary totals require specific scale and rounding?
- Is the checksum calculated over bytes, characters, or normalized records?
- Is CRLF or LF required?
- Is encoding UTF-8, UTF-16, or a partner-specified charset?
- Does the file require a byte order mark?
- Must the file be signed or encrypted after closing?

Callbacks only write text. They do not automatically perform signing, encryption, compression, or checksumming unless the application adds that logic.

## 24. Encoding and newlines

Headers and footers must use the same encoding and line-ending convention as item content.

Example:

~~~java
.encoding(StandardCharsets.UTF_8.name())
.lineSeparator("\n")
.headerCallback(writer -> {
    writer.write("id,name");
    writer.write("\n");
})
.footerCallback(writer -> {
    writer.write("END");
    writer.write("\n");
})
~~~

If the file goes to a system requiring CRLF, use CRLF consistently across both callbacks and lineSeparator. Do not mix platform-dependent newlines with fixed newlines inside callbacks if downstream expects exact byte formatting.

If a BOM is required, check whether the writer or a resource wrapper supports it. Do not write a BOM inside a callback after the writer has already emitted other bytes, because a BOM must appear at byte 0 of the file.

## 25. Headers/footers and sensitive data

Headers and footers normally hold metadata, yet they can still expose sensitive data:

- Customer or account names.
- Internal filesystem paths.
- System codes.
- Tokens or credentials.
- Operational details revealing infrastructure.

Write only fields required by the contract. Never write passwords, access tokens, or secrets to output files. If a header includes a source file reference, consider writing a logical source ID instead of a physical path.

For values coming from JobParameters or ExecutionContext, validate and escape before writing. An injected newline in metadata can create extra lines or break file structure.

## 26. Headers/footers and transactional file writing

FlatFileItemWriter has buffering and transaction-aware writing to coordinate item output with chunk transactions per configuration. However, files are not inherently transactionally unified with databases.

Understand that:

- Item rows may be buffered and flushed on chunk commit.
- Headers are normally written during writer open.
- Footers are written when the writer closes.
- Database rollback does not automatically erase file bytes already flushed to the filesystem.
- File output is not automatically atomic with database commits.
- If file publication and database state must stay consistent, design a staging and publish workflow.

### Staging and publish

A common pattern:

~~~mermaid
flowchart TD
    A["FlatFileItemWriter opens staging file"] --> B["Write header"]
    B --> C["Write items by chunk"]
    C --> D["Close writer and write footer"]
    D --> E{"Did Step and Job succeed?"}
    E -- "Yes" --> F["Publish file"]
    E -- "No" --> G["Quarantine or keep staging"]
    F --> H["Downstream receives official file"]
~~~

A separate publish Step can check file existence, size, trailer, checksum, and Step status before renaming or moving the file into the official directory.

When an atomic move is needed, use Files.move with ATOMIC_MOVE where the filesystem supports it. Otherwise implement a controlled fallback so consumers never observe partially copied files.

## 27. Callbacks should not perform heavy work

Header/footer callbacks should emit short content from already-available data. Avoid heavy database queries, remote API calls, recomputing totals across the entire source, waiting on multiple threads, publishing or emailing, or closing resources owned by other components.

The header callback runs during file open, which can block the Step before reading even starts. The footer callback runs during close; if slow or failing, Step close suffers too. Callbacks can also run again on restarts or resource rollovers. Side effects inside callbacks are hard to coordinate with transactions and restarts.

Compute needed values during the Step or in a dedicated service, then pass the results to the callback.

## 28. Testing header callbacks

Tests should verify actual file contents, not merely that the callback was called.

Example standalone callback test:

~~~java
@Test
void writesHeaderLines() throws Exception {
    StringWriter output = new StringWriter();

    FlatFileHeaderCallback callback = writer -> {
        writer.write("CUSTOMER EXPORT");
        writer.write(System.lineSeparator());
        writer.write("id,name");
        writer.write(System.lineSeparator());
    };

    callback.writeHeader(output);

    assertEquals(
        "CUSTOMER EXPORT" + System.lineSeparator()
            + "id,name" + System.lineSeparator(),
        output.toString()
    );
}
~~~

This test verifies callback logic, but it does not prove FlatFileItemWriter invokes the callback at the right time.

### Integration testing with the writer

Use a real FlatFileItemWriter with a temporary file:

1. Configure a temporary resource.
2. Register the header callback.
3. Open the writer.
4. Write several items.
5. Close the writer.
6. Read the file back.
7. Verify the header appears before the first record and only the expected number of times.

You do not need to launch an entire Job just to test builder/writer wiring. However, Job/Step tests are needed to verify scope, restart, and callback lifecycle.

## 29. Testing footer callbacks

Standalone callback test:

~~~java
@Test
void writesFooter() throws Exception {
    StringWriter output = new StringWriter();

    FlatFileFooterCallback callback = writer -> {
        writer.write("TOTAL_RECORDS,2");
        writer.write(System.lineSeparator());
        writer.write("END");
        writer.write(System.lineSeparator());
    };

    callback.writeFooter(output);

    assertEquals(
        "TOTAL_RECORDS,2" + System.lineSeparator()
            + "END" + System.lineSeparator(),
        output.toString()
    );
}
~~~

Integration tests should open FlatFileItemWriter, write items, close the writer, read the file back, confirm the footer sits at the end of the file, and verify the callback was not called after every chunk.

If the footer uses StepExecution metrics, run a real Step and verify the trailer reflects the final counters.

## 30. Testing failures and restarts

Scenarios to include:

| Scenario | What to verify |
|---|---|
| Step succeeds | Header, details, and footer in exact order |
| Step has zero items | File contents match empty-output policy |
| Processor fails | Writer closes per lifecycle; footer behavior verified |
| Writer fails | Partial file is never published |
| Footer callback throws IOException | Step/close failure is recorded |
| Restart after committed chunk | No duplicate header or lost details |
| Restart after close on failure | Stale footer is not left in the wrong position |
| Append to existing file | Header does not appear mid-data |
| MultiResourceItemWriter rollover | Each file gets header/footer per contract |
| Job rerun with new output path | Previous run's file is not overwritten |

### Checking callback invocation counts

You can use a counting callback:

~~~java
AtomicInteger headerCalls = new AtomicInteger();
AtomicInteger footerCalls = new AtomicInteger();

FlatFileHeaderCallback header = writer -> {
    headerCalls.incrementAndGet();
    writer.write("id,name" + System.lineSeparator());
};

FlatFileFooterCallback footer = writer -> {
    footerCalls.incrementAndGet();
    writer.write("END" + System.lineSeparator());
};
~~~

After running the writer or Step, assert the call counts for that specific case. With restarts and multi-resource outputs, never assume the count is always one; call counts follow the file writer/delegate lifecycle.

## 31. Common implementation mistakes

### Forgetting newlines in callbacks

Headers or footers run into adjacent data rows. Callbacks must write line separators themselves whenever the format requires them.

### Closing the Writer inside a callback

The Writer belongs to FlatFileItemWriter. Closing it inside a callback prevents the framework from continuing to write or closing cleanly.

### Writing to the file with a second Writer

Two writers targeting the same resource can cause lost data, out-of-order lines, or buffer conflicts. Use only the Writer passed to the callback.

### Using the footer as a SUCCESS marker

The footer can be written when the writer closes on a failure path. Use a publish Step after processing succeeds to add confirmation markers.

### Computing totals from source data in the footer

The footer callback becomes slow and may be invoked repeatedly. Aggregate during processing or in a separate verification Step.

### Injecting scalar StepExecution counts too early

A numeric value bound at bean creation can be a stale snapshot from Step startup. Inject the StepExecution object and read counters when the callback executes.

### Assuming headers/footers auto-escape CSV

Callbacks write raw text. Encode dynamic fields yourself per the file contract.

### Not testing empty files

A file with zero detail rows might still receive a header/footer or be deleted depending on settings. Define the requirement and test it.

### Restart creating duplicate headers/footers

Do not write headers/footers manually from listeners. Use callbacks and test with saveState, append, and real checkpoints.

### Publishing the file inside the footer callback

The footer only ends the file writer; it does not prove the entire Job succeeded. Publish in a separate Step.

### Sharing an output path across JobExecutions

Two writers can overwrite or interleave data. Create dedicated staging paths per JobInstance/run ID and publish controllably.

### Writing unescaped metadata

Newlines or delimiters in JobParameters can break file structure. Validate and encode before writing.

## 32. Workflow for implementing header/footer callbacks

When building file outputs, follow this sequence:

1. **Define the format:** headers, column names, metadata, trailers, and newlines per the downstream contract.
2. **Choose the writer:** use FlatFileItemWriter when built-in callbacks are needed.
3. **Create LineAggregator:** define how items turn into records.
4. **Write the header callback:** emit metadata and column names, adding newlines explicitly.
5. **Write the footer callback:** emit the trailer from aggregated state.
6. **Bind runtime data:** use @StepScope to read JobParameters or ExecutionContext.
7. **Configure writer state:** set a stable name and saveState suited to restart.
8. **Control output paths:** use dedicated resources per JobInstance and staging directories.
9. **Separate publishing:** publish files only after Step/Job succeeds.
10. **Test callbacks:** contents, newlines, empty files, close errors, restarts, appends, and multi-resource outputs.
11. **Monitor errors:** log IOExceptions and never publish files missing headers/footers or trailers.

## 33. Key points to remember

- FlatFileHeaderCallback writes the start of a file; FlatFileFooterCallback writes the end of a file.
- Both callbacks receive a java.io.Writer managed by FlatFileItemWriter.
- The header callback runs during file open when the writer needs to initialize the head; the footer callback runs during close.
- Callbacks do not run per item or per chunk.
- Callbacks must write their own newlines when the format requires them.
- Never close the Writer or open a second writer inside a callback.
- @StepScope and SpEL can be used to access JobParameters, JobExecutionContext, or StepExecutionContext.
- Footers can read counters from the StepExecution object at callback execution time.
- A footer is not proof of Job success because the writer may close on a failure path.
- If a SUCCESS marker is required, add it in a publish Step after processing completes.
- Headers/footers write raw text; dynamic values must be validated and CSV-escaped.
- Restart and append depend on saveState, checkpoints, appendAllowed, and file state; write integration tests.
- MultiResourceItemWriter triggers headers/footers according to each delegate file's lifecycle.
- Output files should use staging and be published only after completeness is verified.
- Test empty files, exceptions, restarts, callback failures, and resource rollovers.

Header and footer callbacks help FlatFileItemWriter produce properly structured files without mixing file metadata into per-item processing logic. When you understand when callbacks run, handle the passed Writer properly, and separate technical trailers from success confirmation, your application produces clean files, restarts safely, and avoids publishing incomplete outputs.

