# Readers Handling Empty Input

In Spring Batch, a reader may encounter a data source with no records: a CSV file with only a header, a database query that returns no rows, an input directory that has no file yet, or a partition with no data. This is a normal situation in many batch pipelines. However, **whether empty input is considered a success or a business error depends on the job's contract**.

Technically, Spring Batch's convention is very clear: when there are no more items to read, the `ItemReader.read()` method returns `null`. A chunk step that reads through the data source without receiving any item usually completes normally with a read count and write count of 0. That does not by itself say whether the input data is valid or invalid.

This article explains the reader's EOF convention, how common readers handle an empty source, how to distinguish an empty file from a missing file or data that has been entirely filtered out, and how to design a job to accept, skip, or reject empty input according to business requirements.

## 1. The Core Convention: read() Returns null When Data Is Exhausted

The `ItemReader<T>` interface has one method for reading an item. Each time it is called, the reader returns:

- A non-`null` object if there is a next item.
- `null` if the input is exhausted and there are no more items to read.

A simple reader example:

```java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
```

If the input list is empty, the first call returns `null`. Spring Batch understands that the reader has run out of data and ends the step's reading phase.

The important point is that `null` has a flow-control meaning: it marks EOF (end of input). Do not use `null` to represent a malformed line, a skipped record, or an empty business value. If a reader returns `null` in the middle of the data source, the framework will understand that there are no more items after it and may end the step early.

### Distinguishing EOF from an Item with Empty Content

Suppose the reader has the type `ItemReader<String>`:

- Returning `""` is a valid empty-string item; the framework still treats it as an item.
- Returning an object whose fields are all empty is still an item.
- Returning `null` means there are no more items.

Similarly, if the item type is `ItemReader<List<Record>>`, an empty list is still a non-`null` object. It can be a valid item if the data contract defines it that way. The next `read()` call returns `null` only when the source has truly ended.

## 2. What Happens When a Chunk Step Reads Empty Input?

A chunk-oriented step performs a read, process, and write cycle. When the reader returns `null` on the very first read, Spring Batch recognizes that the source has ended:

```mermaid
flowchart TD
    A[Step starts] --> B[Reader.read()]
    B --> C{Has item?}
    C -->|No, returns null| D[Mark EOF]
    D --> E[No chunk to write]
    E --> F[Step ends]
    C -->|Has item| G[Processor]
    G --> H[Chunk full or EOF]
    H --> I[Writer]
    I --> B
```

For a step that reads no items at all, the commonly seen behavior is:

- The step is launched normally.
- The reader is opened and called to read.
- The reader returns `null` on the first call.
- The processor is not called.
- The writer is not called because there is no chunk of items.
- The step completes with `BatchStatus.COMPLETED`, if there are no other errors.

The step's counters usually show `READ_COUNT = 0`, `WRITE_COUNT = 0`, `FILTER_COUNT = 0`, and skip counts of 0. The job can continue to the next step according to the declared flow.

This is a normal technical completion. If the business requires at least one record, the application must add its own validation rule or routing.

## 3. Distinguishing Empty Input Situations

Not every "no data" situation is the same. You need to determine exactly what happened before choosing how to handle it.

| Situation | Example | Interpretation |
|---|---|---|
| The file does not exist | The path has no file yet | An input error or waiting for the file, depending on the contract |
| A file of size 0 | A completely empty file | The source exists but has no content |
| A file with only a header | Has column names but no records | The structure may be valid, the record count is 0 |
| A query returns no rows | No transactions in the range | May be a day with no activity |
| A partition has no records | A data region has no items | Usually acceptable |
| A blank line | A line with no characters | A separate blank-line rule must be applied |
| Malformed data | A missing column or a wrong numeric type | A parse/validation error, not EOF |
| All items are filtered | The processor returns `null` for every item | The input is not empty but the output is empty |
| All items are skipped | Every item is skipped under the skip policy | There is input but no item is written |

This distinction matters for reporting. For example, "no transactions that day" may be a good result, whereas "source file does not exist" may be a serious error.

## 4. FlatFileItemReader with an Empty File or a Header-Only File

`FlatFileItemReader` is commonly used to read CSV or text files line by line. Example:

```java
@Bean
@StepScope
FlatFileItemReader<Invoice> invoiceReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Invoice>()
            .name("invoiceReader")
            .resource(new FileSystemResource(inputFile))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("invoiceId", "customerId", "amount")
            .fieldSetMapper(fields -> new Invoice(
                    fields.readString("invoiceId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

In the example, the reader skips the first line because it is the header. The remaining lines are then mapped to `Invoice`.

### A File of Size 0

If the resource exists, is readable, and has no lines, the reader will not produce any item. The read returns `null`, so the chunk step can complete with `READ_COUNT = 0`.

### A File with Only a Header

If the file has exactly one header line and `linesToSkip(1)` is configured, there are no data lines left to map. The result is also zero items. This is usually a file that has a structure but no records.

### A File That Does Not Exist

A file that does not exist is different from an empty file. `FlatFileItemReader` has a strict mode; the default is usually strict. When the resource does not exist or cannot be read, the reader reports an error on open instead of treating it as EOF. If you deliberately set `strict(false)`, the reader may skip the missing resource and continue as if the source had no items. Use this approach only if a missing file is truly defined as valid empty input.

### A Wrong or Missing Header

If the file has no header but the configuration skips one line, the reader may skip the first data line. Conversely, a completely empty file may provide no line against which to check the header. Therefore, if the header is mandatory, you need to check it explicitly.

You can use an input validation step before the import step to check:

- Whether the resource exists and is readable.
- Whether the file has a header line.
- Whether the column names are in the correct order or match the required set of names.
- Whether the encoding and delimiter conform to the contract.
- Whether the file has data or only a header.

If the validation step reads the file itself, keep the input immutable and make sure the import reader reads the same version of the file. You can check a checksum or move the file into a fixed batch directory before running.

### A Blank Line Does Not Mean EOF

A blank line in a file is still a physical line. It does not automatically mean the reader has reached the end of the file. That line may be handled by the tokenizer/line mapper, producing an empty item or causing a parse error depending on the configuration. Clearly define whether a blank line is skipped, treated as faulty data, or mapped to a valid value.

Do not write a custom reader that returns `null` when it encounters a blank line if there is still data in the following lines. That approach would end reading early.

## 5. JdbcCursorItemReader and Queries with No Rows

With a database reader, the query may be valid but find no records:

```java
@Bean
@StepScope
JdbcCursorItemReader<Invoice> invoiceReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcCursorItemReaderBuilder<Invoice>()
            .name("invoiceReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT invoice_id, customer_id, amount
                    FROM invoice
                    WHERE business_date = ?
                    ORDER BY invoice_id
                    """)
            .preparedStatementSetter(statement ->
                    statement.setDate(
                            1,
                            java.sql.Date.valueOf(businessDate)))
            .rowMapper((resultSet, rowNum) -> new Invoice(
                    resultSet.getString("invoice_id"),
                    resultSet.getString("customer_id"),
                    resultSet.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

If the query returns no rows, the reader returns `null` when called to read. The step completes normally with zero reads. This is not a SQL error; it only indicates the query result is empty.

You do not necessarily need to run an additional `SELECT COUNT(*)` before the reader to know whether the query has data. For large tables, a count can be resource-intensive; moreover, the data may change between the count query and the reader query. If the goal is only to know whether the step read any item, `StepExecution` already has counters you can check after reading.

If the business needs a stable snapshot, choose an appropriate transaction isolation or watermark. Running a count first does not create a consistent snapshot if the two queries are not in the same snapshot transaction.

## 6. Distinguishing Empty Input from a Processor Filtering Out All Data

This is a difference that is often overlooked.

When the reader returns an item, the source has data. The processor can then return `null` to filter that item out of the output. Returning `null` from the processor does not mean the reader has run out of input.

Example:

```java
@Bean
ItemProcessor<Invoice, Invoice> validInvoiceProcessor() {
    return invoice -> {
        if (invoice.amount().signum() <= 0) {
            return null; // Filters the item, not EOF
        }
        return invoice;
    };
}
```

If the reader reads 100 items and the processor filters all of them, the step is not empty input. The counters may reflect `READ_COUNT = 100`, `FILTER_COUNT = 100`, `WRITE_COUNT = 0`.

Comparison:

| Case | READ_COUNT | FILTER_COUNT | WRITE_COUNT |
|---|---:|---:|---:|
| The reader has no items | 0 | 0 | 0 |
| 100 items, all filtered | 100 | 100 | 0 |
| 100 items, 10 filtered | 100 | 10 | 90 |
| 100 items, some skipped | 100 or the number read before the error | According to the actual filtering | Depends on the number of items written and skipped |

When monitoring production, do not use `WRITE_COUNT = 0` alone to conclude that the source is empty. Look at the read, filter, and skip counts together.

## 7. Designing a Policy for When There Is No Data

Before implementing, agree on which case empty input belongs to:

### Case A: Empty Input Is a Valid Result

Examples: a holiday with no transactions, a data region with no records, or a report with no activity lines.

The chunk step can complete normally. The job should record the count of 0 and the later steps must accept that situation. If notification is needed, you can emit a "no data" message in the aggregation step.

### Case B: Empty Input Is a Separate Branch of the Workflow

Example: the job does not need to run a heavy aggregation step when there are no items, but still needs to record that the batch successfully checked the source.

You can use a `StepExecutionListener` to set a custom exit code when `readCount` is 0:

```java
public class EmptyInputExitStatusListener
        implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getReadCount() == 0) {
            return new ExitStatus("NO_INPUT");
        }
        return null;
    }
}
```

Attach the listener to the step:

```java
return new StepBuilder("importInvoicesStep", jobRepository)
        .<Invoice, ProcessedInvoice>chunk(500, transactionManager)
        .reader(invoiceReader)
        .processor(invoiceProcessor)
        .writer(invoiceWriter)
        .listener(new EmptyInputExitStatusListener())
        .build();
```

Then route the flow by exit code:

```java
return new JobBuilder("invoiceImportJob", jobRepository)
        .start(importInvoicesStep)
            .on("NO_INPUT").to(noInputStep)
        .from(importInvoicesStep)
            .on("*").to(reconcileStep)
        .end()
        .build();
```

`NO_INPUT` is a custom exit code defined by the application. The step's `BatchStatus` can still be `COMPLETED`; the flow uses `ExitStatus` to choose the branch. The `noInputStep` step can record the zero-record result, send a notification, or end the process according to policy.

In the example, `readCount == 0` determines that the reader emitted no items. If the processor filters everything, the read count is still greater than 0 so it does not enter the `NO_INPUT` branch.

### Case C: Empty Input Is a Business Error

Examples: a settlement file must contain transactions, or the job must receive at least one reconciliation record.

You can validate before the import and fail with a specific message. For a file, the validation step can check the file, the header, and the number of data lines. For a database, you can let the data-reading step itself determine zero reads and then route to an error-reporting step; or design a checking reader/step appropriate to the snapshot requirement.

Do not pretend that the chunk step fails by itself when the reader returns `null`. The default behavior is end of data, not an error. If zero records are not valid, turn that rule into an explicit business step.

### Case D: Waiting for Input to Arrive

If the file often arrives late, you can have the scheduler or orchestration system wait until a deadline before launching. The job should not run repeatedly just to check for the file without backoff and a time limit. When the deadline arrives, the process must decide whether to keep waiting, mark the input as missing, or run with zero records.

## 8. Example of Validating a File Before Import

A Tasklet can confirm that the resource exists, is readable, and is not physically empty:

```java
@Bean
@StepScope
Tasklet validateInputFile(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        Resource resource = new FileSystemResource(inputFile);

        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Input file does not exist: " + inputFile);
        }

        if (!resource.isReadable()) {
            throw new IllegalStateException(
                    "Input file is not readable: " + inputFile);
        }

        if (resource.contentLength() == 0) {
            throw new IllegalStateException(
                    "Input file is empty: " + inputFile);
        }

        return RepeatStatus.FINISHED;
    };
}
```

This code illustrates the policy "a physically empty file is an error". If a file with only a header is considered valid, checking `contentLength()` is not enough to confirm there are records. You need to read and verify the header, then determine whether there are data lines after the header.

Validation beforehand and the import reader can create a race condition if the file is changed between the two steps. In production, you should receive the file into immutable storage, rename/move it atomically into a fixed batch directory, or record a checksum and check again before processing.

With large files, do not read the entire file just to count lines and then read it a second time if it is not necessary. You can let the reader process the data and use a step listener based on `readCount`, while validation only confirms the necessary structural conditions.

## 9. A Custom ItemReader Must Handle Empty Input Correctly

When writing your own reader, make sure of three rules:

1. Return a non-`null` item when there is data.
2. Return `null` when the source has truly ended.
3. Do not return `null` to represent an error or to skip an item.

Example of a reader that reads from an iterator:

```java
public class SafeIteratorItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public SafeIteratorItemReader(Collection<T> source) {
        this.iterator = source.iterator();
    }

    @Override
    public T read() {
        if (!iterator.hasNext()) {
            return null;
        }

        T item = iterator.next();
        if (item == null) {
            throw new IllegalStateException(
                    "Source contains a null item");
        }
        return item;
    }
}
```

This reader returns `null` immediately on the first call if the collection is empty. If the collection has a `null` element, it reports an error instead of accidentally ending the stream at that position.

In a real reader, if the source can be opened/closed, supports restart, or is paginated, you should implement the appropriate lifecycle interfaces such as `ItemStream` and save state in the `ExecutionContext`. For a reader with state, the reader name must be stable and the state must be updated at the commit boundary.

### Do Not Use Optional.empty() as an EOF Signal

If the reader type is `ItemReader<Optional<Invoice>>`, an `Optional.empty()` is a non-`null` object, so Spring Batch treats it as an item. That is correct only if the business truly needs an item representing "no invoice". If the purpose is to end the stream, return `null` according to the `ItemReader` contract.

## 10. Empty Input in Partitioning and Parallel Processing

With a partitioned step, some partitions may receive no records while other partitions have data. This is not necessarily an error. The reader of an empty partition can return `null` on the first call and the worker step completes with zero reads.

However, you need to check:

- Whether the partitions are divided without overlap and without omission.
- Whether the total number of records across the partitions matches the expected source set.
- Whether an empty partition is valid given how the data was divided or indicates a partitioning error.
- Whether the job handles correctly the case where all partitions are empty.
- Whether the summary report distinguishes an empty partition from a failed partition.

Do not fail the whole job just because one partition is empty if an empty partition is a natural result of how the data was divided. Conversely, if a partition must have data, express that condition clearly in the validation step or the partition result.

## 11. Empty Input, Skip, and Retry Are Three Different Concepts

| Behavior | Cause | Result |
|---|---|---|
| EOF | The reader has no more items | `read()` returns `null`, the step ends reading |
| Filter | The processor decides not to put the item into the output | The processor returns `null`, the filter count increases |
| Skip | An error allowed to be skipped under the fault-tolerant policy | The failed item is skipped and the skip count increases |
| Retry | An error considered transient | The framework retries the operation according to the configuration |
| Fail | An error that is not allowed to continue | The step/job fails |

Do not configure a skip policy to "skip empty input". EOF is not an exception and does not need to be skipped. If the source has no items, the policy must be expressed in the flow or validation.

If the reader encounters a parse error on the first line, that is a data-reading error. You can fail or skip according to the data-error policy, but you should not convert that error into `null`; doing so would hide the error and may skip the rest of the file.

## 12. Observability and Reporting for Empty Input

When a job completes with zero items, logs and metrics should explain that clearly. You should record:

- The job name, job execution ID, step name, and batch ID.
- The input resource or the data window that was processed.
- The number of items read, written, filtered, and skipped.
- The reason there is no data, if it can be determined.
- The policy applied: accepted, routed, or rejected.
- The check time and the run time.

Example log:

```text
job=invoiceImportJob
jobExecutionId=108
step=importInvoicesStep
batchId=daily-20261115
readCount=0
writeCount=0
exitCode=NO_INPUT
message=No invoice records found for business date
```

Do not write the entire file content or personal data into the log just to prove the file is empty. Use the batch code, the checksum, a sanitized resource name, and the record count.

A dashboard can distinguish the results:

- `COMPLETED` with a record count greater than 0: processing with data.
- `NO_INPUT`: a valid source but no records.
- `FAILED`: missing input, wrong structure, or a system error.
- `COMPLETED` with a read count greater than 0 but a write count of 0: the filter/skip policy needs to be checked.

If you use a custom exit code, standardize how the dashboard and alerts read both `BatchStatus` and `ExitStatus`.

## 13. Restart When the Previous Run Had No Data

If a step reads zero items and completes, the `JobInstance` is usually considered completed if the whole job also completes. Relaunching with the same identifying parameters usually does not create a new run; Spring Batch will report that the instance has already completed.

This matters if the input arrives late:

- If the job runs at 01:00 and the source has no data yet, the job completes with zero items.
- The file or records arrive at 01:15.
- Relaunching with the same identifying parameters may be rejected because the instance has already completed.

Decide in advance how to handle late-arriving input:

1. Wait until a deadline before launching.
2. Mark the batch as complete only after confirming the source has been finalized.
3. Create a reprocess request with a new ID/version according to business policy.
4. Use an orchestration mechanism to hold a "waiting for input" state before creating the JobInstance.

Do not add a random timestamp just to rerun the same data. If reprocessing creates a new instance, the writer must still be idempotent or have a version-recording mechanism.

If zero input is considered a valid completed result, the inability to restart the same instance afterward is the appropriate behavior. If the job must wait for data to arrive, represent the waiting state at the orchestration layer or keep the job incomplete by a clear design; do not treat EOF as an automatic waiting state.

## 14. Testing Readers with Empty Sources

Tests should cover each type of empty source and each business policy.

| Case | What to confirm |
|---|---|
| An empty collection | The first read returns `null` |
| A 0-byte file | The reader emits no item; validation follows the policy |
| A header-only file | The header is skipped and there is no data item |
| A file that does not exist | A strict reader or validation reports an error if the file is mandatory |
| A query with no rows | The step completes with a read count of 0 |
| A blank line | Handled according to the blank-line policy |
| A malformed line | Fail or skip according to the exception policy |
| A processor that filters every item | The read count is greater than 0 and the filter count reflects the number filtered |
| An empty partition | The worker step completes according to the policy |

Example unit test for a reader that uses a collection:

```java
class SafeIteratorItemReaderTest {

    @Test
    void returnsNullWhenSourceIsEmpty() throws Exception {
        ItemReader<String> reader =
                new SafeIteratorItemReader<>(List.of());

        assertNull(reader.read());
    }

    @Test
    void returnsItemsThenNullAtEnd() throws Exception {
        ItemReader<String> reader =
                new SafeIteratorItemReader<>(List.of("A", "B"));

        assertEquals("A", reader.read());
        assertEquals("B", reader.read());
        assertNull(reader.read());
    }
}
```

Besides unit tests, you should have an integration test for the step with database metadata and a test data source. The test confirms the step status, the counters, and the exit code. If you use a `NO_INPUT` flow, check that the job takes the right branch and that the downstream step is or is not run as required.

## 15. Common Design Mistakes

**Treating zero reads as an automatic error.** Spring Batch treats `null` as EOF. If zero records are not valid, add validation or a flow policy.

**Treating a missing file the same as an empty file.** A missing file may be a delivery error; an empty file may be valid input. Use strict resource validation and a separate policy.

**Using null to skip a faulty line.** Null ends the stream. Use an exception/skip policy or a processor filter according to the proper meaning.

**Looking only at the write count.** Zero writes may be due to an empty source, everything filtered, or everything skipped. Read the read/filter/skip counts too.

**Assuming a header-only file is a bad file.** Some systems allow a header-only file to represent a day with no records. Determine the business rule.

**Rerunning the job with a new timestamp after late input arrives.** That creates a new instance and may process duplicates. You need a late-data/reprocess policy together with an idempotent writer.

**Validating the file and then letting the file change before the reader runs.** The two steps may read two different contents. Fix an immutable file or check a checksum.

## 16. Decision Process When a Reader Encounters Empty Input

When designing a reader, walk through these questions:

1. Does the source exist and is it readable?
2. Is the source's structure valid, for example the header and encoding?
3. Is the source valid but without records, or was the data entirely filtered/skipped?
4. Does the business allow zero records?
5. If allowed, should the job complete normally or go through the `NO_INPUT` branch?
6. If not allowed, which step will fail and with what reason?
7. If data arrives late, what waiting or reprocessing mechanism exists?
8. On restart, does the data source remain unchanged?

A clear decision at these points helps the job avoid a "green but missing data" state and also avoids reporting errors for days with no legitimate activity.

## 17. Practical Conclusion

A reader handles empty input under a simple contract: return `null` when the data is exhausted. For a chunk step, zero items usually leads to the step completing with read/write counts of 0; the processor and writer have no items to process. This is normal technical behavior.

What needs to be designed is the business meaning of zero items. It can be accepted, routed to the `NO_INPUT` branch, or failed through validation. Distinguish a missing file, an empty file, a header-only file, a query with no rows, filtered data, and skipped data. In particular, do not use `null` to skip an item when there is still data afterward.

A good production reader does not only read correctly when there is data. It also expresses EOF clearly, preserves restart state, handles errors according to policy, and provides enough metadata for operators to understand why a batch produced no output.
