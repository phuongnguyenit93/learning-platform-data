# Files with faulty lines and skip

When processing CSV, TSV, or fixed-width files with Spring Batch, not every line contains valid data. A line might miss a column, have extra tokens, use an invalid date format, contain an unparseable number, or violate business rules. If every error halted the Job, a large file could fail to process because of a few bad records.

Spring Batch supports **skip** to bypass permitted faulty items and continue processing valid lines. For Flat Files, parse errors are typically represented by **FlatFileParseException**. A Step can configure this exception as skippable, set a skip limit, and use a SkipListener to record rejected lines.

It is important to distinguish a single faulty data line from a resource-wide failure. A malformed CSV line can be skipped; a missing file, insufficient read permissions, or inability to open the file is a resource initialization failure and should fail the Step.

## 1. Common error types in flat files

An input file can contain several categories of errors:

| Error type | Example | Typically detected at |
|---|---|---|
| Missing or extra columns | CSV line has 2 fields when 3 are expected | Tokenizer |
| Wrong data type | Invalid date format, letters in a monetary amount | FieldSetMapper or conversion |
| Malformed line structure | Invalid delimiter or quoting | LineTokenizer / RecordSeparatorPolicy |
| Missing mandatory value | Empty customerId | Mapper or ItemProcessor |
| Business rule violation | Invalid customer code | ItemProcessor |
| Missing resource | Wrong file path | Reader open |
| Insufficient permissions | Application account cannot read the file | Reader open |
| I/O failure mid-read | Filesystem or storage device failure | Reader read |

Not all of these errors should be handled by skipping. Skip is best suited to errors tied to a specific record that can be excluded while processing the rest. Infrastructure or resource errors usually affect the entire run and should not be treated as a single bad data line.

## 2. How FlatFileItemReader processes each line

FlatFileItemReader reads the resource line by line and converts each line into an item via LineMapper. LineMapper usually combines a LineTokenizer to split fields and a FieldSetMapper to map fields to an object.

Basic processing flow:

~~~text
File resource
    |
    v
FlatFileItemReader
    |
    v
Read physical line
    |
    v
LineMapper
    |
    +--> LineTokenizer
    |       |
    |       v
    |    FieldSet
    |
    +--> FieldSetMapper
            |
            v
       Input object
            |
            v
      ItemProcessor
            |
            v
        ItemWriter
~~~

If the tokenizer cannot split a line according to the expected structure or the mapper cannot convert data, LineMapper may throw an exception. FlatFileItemReader typically wraps line-mapping errors into FlatFileParseException, including the raw input and line number to aid investigation.

Example CSV file:

~~~csv
customerId,fullName,age
C001,An Nguyen,30
C002,Binh Tran,not-a-number
C003,Chi Le,28
C004,Du Pham
C005,Em Vo,35
~~~

If the age field maps to a numeric type, line C002 triggers a conversion error. Line C004 misses a field compared to the expected schema and triggers a token count error if the tokenizer is configured as strict. The remaining lines can be read normally.

## 3. What information does FlatFileParseException carry?

FlatFileParseException is the dedicated exception for flat-file line parsing failures. It typically provides:

- Error message and root cause.
- Associated line number via getLineNumber().
- Raw input line content via getInput().

This information is essential when recording skipped lines because the onSkipInRead callback does not receive an item object. Since the reader could not construct a valid item, the listener receives only the exception.

Example:

~~~java
if (t instanceof FlatFileParseException ex) {
    log.warn("Cannot parse line {}: {}",
            ex.getLineNumber(), ex.getInput());
}
~~~

In production, consider sensitive data policies before logging full input lines. A line may contain names, emails, account numbers, or personal details. Store raw lines in an access-controlled quarantine area while logging only the file ID, line number, business key if identifiable, and error code.

Not every error raised while reading a file is a FlatFileParseException. Resource-open errors, I/O errors, or infrastructure failures may surface as different exceptions. Therefore, do not configure a broad skip over all exceptions just to ignore read failures.

## 4. Configuring the reader for CSV

Example reader reading a CSV file with a header:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "Required JobParameter input.file is missing");
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("customerId", "fullName", "age")
            .targetType(CustomerInput.class)
            .strict(true)
            .saveState(true)
            .build();
}
~~~

In this example:

- The resource is chosen from JobParameter input.file.
- The first line is skipped as the header.
- The tokenizer splits data using the default delimiter of the delimited builder.
- Field names map to CustomerInput.
- strict(true) requires the resource to exist when the reader opens.
- saveState(true) enables the reader to save state for restart.

CustomerInput must be compatible with the chosen mapping mechanism—for instance, a JavaBean with matching properties and setters. If custom delimiters, quoting, escaping, or conversions are needed, configure the tokenizer/mapper explicitly rather than relying on defaults.

File paths should be validated against permitted directories. Never concatenate arbitrary external paths directly without validation, especially if Jobs are launched via an API.

## 5. Configuring skip for parse errors

To skip lines with parse errors, configure the Step with fault tolerance and declare FlatFileParseException as skippable:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter,
        CustomerSkipListener skipListener) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skipLimit(25)
            .listener(skipListener)
            .build();
}
~~~

With this configuration, the Step permits up to 25 skipped items under its skip policy. FlatFileParseException during the read phase can be skipped, and subsequent lines continue being read. If the skip count exceeds the limit, the Step fails.

skipLimit applies to the combined skips across read, process, and write in the Step—not 25 errors per stage. If you only intend to skip reader parse errors, declare only the appropriate exception type and do not broaden it to skip every Exception.

Registering a SkipListener alone without configuring skip does not cause faulty lines to be skipped automatically. The listener records skip decisions already approved by the Step; it is not the policy deciding which exceptions are skippable.

## 6. Example data before and after skipping

Suppose a file has five data lines after the header:

~~~csv
customerId,fullName,age
C001,An Nguyen,30
C002,Binh Tran,not-a-number
C003,Chi Le,28
C004,Du Pham
C005,Em Vo,35
~~~

Given a schema requiring three fields where age must convert to a number:

| Physical line | Content | Result |
|---:|---|---|
| 1 | Header | Skipped via linesToSkip |
| 2 | C001,An Nguyen,30 | Read successfully |
| 3 | C002,Binh Tran,not-a-number | Mapping/parse error, skipped if policy permits |
| 4 | C003,Chi Le,28 | Read successfully |
| 5 | C004,Du Pham | Field count error if tokenizer is strict |
| 6 | C005,Em Vo,35 | Read successfully |

If both errors are classified as skippable and the skip limit has capacity, items C001, C003, and C005 still flow to the processor/writer. SkipListener receives details of both faulty lines to persist an audit trail or reprocess later.

Note: the line number in the exception is usually the resource's physical line number, not the valid item index after stripping headers. For multi-line records, verify how the reader and RecordSeparatorPolicy report error positions.

## 7. Recording faulty lines with SkipListener

SkipListener has three callbacks. For parse errors in the reader, the relevant callback is onSkipInRead(Throwable t). This callback receives no item because the reader never created an input object.

~~~java
public class CustomerSkipListener
        implements SkipListener<CustomerInput, Customer> {

    private final SkippedLineService skippedLineService;

    public CustomerSkipListener(SkippedLineService skippedLineService) {
        this.skippedLineService = skippedLineService;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        if (t instanceof FlatFileParseException ex) {
            skippedLineService.record(
                    ex.getLineNumber(),
                    ex.getInput(),
                    ex.getCause() == null
                            ? ex.getMessage()
                            : ex.getCause().getMessage());
        } else {
            skippedLineService.recordUnknownReadFailure(
                    t.getClass().getName(),
                    t.getMessage());
        }
    }

    @Override
    public void onSkipInProcess(CustomerInput item, Throwable t) {
        skippedLineService.recordValidationFailure(
                item.customerId(), t.getClass().getName(), t.getMessage());
    }

    @Override
    public void onSkipInWrite(Customer item, Throwable t) {
        skippedLineService.recordWriteFailure(
                item.customerId(), t.getClass().getName(), t.getMessage());
    }
}
~~~

The methods on SkippedLineService represent an illustrative API. In real applications, also persist:

- JobExecution ID and StepExecution ID.
- File ID or normalized resource path.
- Line number and raw line if data policy permits storing it.
- Exception type, error code, and sanitized cause.
- Skip timestamp and batch ID.
- Reprocessing status such as NEW, FIXED, or REPLAYED.

SkipListener is typically called just before the chunk transaction commits. If audit records are written to the same database with the same transaction manager, skip records commit together with the chunk transaction. If writing to an external system, that operation will not roll back automatically with the database transaction; consider an outbox or idempotency.

## 8. Distinguishing faulty lines from headers and comments

Not every line that the reader does not turn into an item is a line skipped due to an error.

### Headers via linesToSkip

The reader can skip a number of leading lines:

~~~java
.linesToSkip(1)
~~~

This is header handling, not fault-tolerant skipping. Header lines do not increment readSkipCount and do not consume skipLimit.

If you need to inspect the header, use skippedLinesCallback to receive the skipped leading lines and validate column names. That callback is separate from SkipListener.

### Comment lines

FlatFileItemReader can be configured with comment prefixes so comment lines are not treated as items. Comment lines are handled by reader rules, not skipped due to exceptions.

### Filtering in the processor

If the processor returns null, the item is intentionally filtered. filterCount increases, but skip counts do not increment and SkipListener is not called.

| Case | Mechanism | Increments skip count? |
|---|---|---|
| Header skipped | linesToSkip | No |
| Comment line | Comment prefix | No |
| Processor returns null | Filter | No |
| Tokenizer/mapper throws skippable exception | Read skip | Yes |
| Processor throws skippable exception | Process skip | Yes |

## 9. Parse errors vs. file-open errors are different

A faulty data line typically occurs after the reader has successfully opened the resource. By contrast, if a file does not exist or the application lacks read permission, the error occurs when opening the resource.

Examples:

| Situation | Phase | Typically appropriate handling |
|---|---|---|
| CSV line has wrong column count | While parsing a record | Can skip FlatFileParseException |
| Date in one line has wrong format | While mapping fields | Can skip parse error if policy allows |
| File does not exist | On reader open | Step usually fails |
| No permission to read file | On open or resource access | Step usually fails |
| Filesystem disconnects mid-read | During read | Retry if transient and supported by reader; otherwise fail |
| File replaced between run and restart | On checkpoint restore or read | Verify resource/version; do not blindly continue |

Do not mark IOException or Exception in general as skippable if that error leaves the reader unable to continue. Skip only makes sense when the framework can bypass one specific record and move cleanly to the next.

strict(true) mainly controls behavior when the resource is missing on open. It does not replace a skip policy for lines with malformed contents.

## 10. Configuring tokenizer and mapper to catch bad lines

Skip accuracy depends on the reader detecting errors accurately. For CSV, DelimitedLineTokenizer splits fields by delimiter and handles quotes as configured. For fixed-width files, FixedLengthTokenizer uses Ranges to define field positions.

Custom tokenizer example:

~~~java
@Bean
LineMapper<CustomerInput> customerLineMapper() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("customerId", "fullName", "age");
    tokenizer.setStrict(true);

    BeanWrapperFieldSetMapper<CustomerInput> fieldSetMapper =
            new BeanWrapperFieldSetMapper<>();
    fieldSetMapper.setTargetType(CustomerInput.class);

    DefaultLineMapper<CustomerInput> lineMapper = new DefaultLineMapper<>();
    lineMapper.setLineTokenizer(tokenizer);
    lineMapper.setFieldSetMapper(fieldSetMapper);
    return lineMapper;
}
~~~

Then attach LineMapper to the reader:

~~~java
return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(resource)
        .linesToSkip(1)
        .lineMapper(customerLineMapper)
        .saveState(true)
        .build();
~~~

With a strict tokenizer, mismatched token counts raise an error instead of silently dropping fields. This helps detect bad data early. However, strictness must match the file contract; if the source allows optional trailing columns, the mapper should handle them explicitly.

For fixed-width files, configure exact ranges and validate line lengths. If a line is shorter or longer than the schema, decide whether it is a skippable data error or a structural file error making the whole batch untrustworthy.

## 11. CSV records spanning multiple physical lines

CSV can contain newlines inside quoted fields. In that case, a single logical record spans multiple physical lines. The reader uses RecordSeparatorPolicy to decide when a record is complete.

Example:

~~~csv
customerId,comment
C001,"First line
second line"
C002,"Normal comment"
~~~

Record C001 is one logical record occupying two physical lines. If a quote is not closed properly, the reader may continue absorbing subsequent lines into the same record or fail only when reaching the end of the resource, depending on RecordSeparatorPolicy.

Therefore:

- Do not assume each skip always corresponds to exactly one physical line.
- Log both line number and input from the exception when available.
- Test files containing quoted newlines and missing quotes.
- Use a RecordSeparatorPolicy matching the source format.
- If the source prohibits multiline fields, enforce that rule explicitly.

In operations, distinguish the count of skipped records from the number of physical lines involved. A single faulty record can span multiple file lines.

## 12. Processor errors vs. parse errors

A line may parse into a valid object yet still contain invalid business data—for example, a negative age, nonexistent customer code, or out-of-range effective date.

Parse errors occur in the reader/LineMapper; business errors are usually caught in ItemProcessor:

~~~java
@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    @Override
    public Customer process(CustomerInput input) {
        if (input.getAge() < 0) {
            throw new InvalidCustomerException(
                    "Age cannot be negative for " + input.getCustomerId());
        }

        return new Customer(input.getCustomerId(), input.getFullName(),
                input.getAge());
    }
}
~~~

If business errors should also be skipped, declare the corresponding exception:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skipLimit(25)
~~~

Processor errors have an input item, so onSkipInProcess receives CustomerInput. Reader errors have no constructed item, so onSkipInRead receives only Throwable. Keeping this distinction lets you record business keys when available and fall back to line number/raw input when object creation failed.

## 13. Skip limit and handling threshold breaches

skipLimit sets the total number of allowed skips in the Step. Example:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skipLimit(10)
~~~

The Step accepts at most 10 skips in total. The 11th skip fails the Step. The limit applies across read, process, and write combined—not 10 per stage.

When the limit is exceeded:

- The Step transitions to FAILED unless flow rules handle the outcome differently.
- The current chunk is handled per transaction/rollback policy.
- Previously committed chunks remain persisted.
- Subsequent items are not processed in that execution.
- StepExecution metadata retains counters for investigation.

Do not raise the skip limit just to force Jobs to finish. For critical files, a high error rate often indicates the wrong file version, wrong delimiter, or changed upstream schema. Stop and investigate rather than producing incomplete output.

## 14. Writing faulty lines to quarantine or a dead-letter file

A production import pipeline usually needs to store skipped lines so operators can fix and replay them. You can write them to a quarantine table or a separate error file.

A quarantine record should include:

| Field | Purpose |
|---|---|
| batchId | Links to the import run |
| sourceFile | Identifies the source file |
| lineNumber | Locates the line |
| rawInput | Line content if allowed to be stored |
| exceptionType | Error category |
| errorMessage | Sanitized failure reason |
| status | NEW, FIXED, REPLAYED, or REJECTED |
| createdAt | Timestamp recorded |

For parse errors, extract line number and raw input from FlatFileParseException. For processor errors, store the business key and parsed input object. For writer errors, store the business key of the output object.

If writing dead-letter records in the same database transaction as the Step, remember that quarantine rows can roll back along with the chunk. If audit records must survive even when a chunk rolls back, design a separate transaction or deliberate outbox pattern; do not assume a repository call is automatically isolated from the active transaction.

Never log sensitive payloads or write them to unprotected error files. Store a reference ID instead of raw data and restrict access and retention.

## 15. Restart when faulty lines occur

FlatFileItemReader supports saving state via ItemStream. When saveState is enabled, the reader persists checkpoints in StepExecutionContext to resume on Job restart.

Example:

~~~text
Initial run:
  open(file A, checkpoint 0)
  read initial records
  skip one faulty line
  commit chunk and save checkpoint
  continue reading
  critical error in later chunk
  Job FAILED

Restart same JobInstance:
  open(file A, saved checkpoint)
  resume from checkpoint
  do not re-read committed chunks per reader state
~~~

For reliable restarts:

- Use the exact same identifying JobParameters on restart.
- Keep the source file unchanged or verify checksum/version.
- Keep the reader name stable so checkpoint keys do not change.
- Enable saveState if read position recovery is required.
- Do not alter schema/tokenizer between the initial run and restart in ways that change how already-read data is parsed.
- Ensure the writer is idempotent for any side effects outside transactions.

If the file has been edited or replaced, the old checkpoint may point to an offset that no longer matches. Decide explicitly whether to start a new JobInstance with a new input version or restore the original file; never resume against unknown data.

## 16. Testing files with faulty lines and skip

Create small test fixtures with a header, valid rows, rows with wrong column counts, rows with wrong data types, and valid rows afterward. Tests must verify both output data and metadata.

Example test using Spring Batch Test:

~~~java
@SpringBatchTest
@SpringJUnitConfig(ImportJobTestConfiguration.class)
class FlatFileSkipTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void skipsMalformedRowsAndWritesValidCustomers() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "src/test/resources/customers-with-errors.csv", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions()
                .stream()
                .filter(s -> s.getStepName().equals("importCustomersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(2, step.getReadSkipCount());
        assertEquals(expectedCustomerIds, customerRepository.findAllIds());
    }
}
~~~

This is an illustrative skeleton; skip counts and outputs should match your actual fixture. Clean the JobRepository and test database between tests so metadata/JobInstances from previous runs do not affect results.

Scenarios to cover:

1. All lines valid: zero skips.
2. One line with wrong column count: readSkipCount increments by one.
3. One line with wrong data type: parse exception skipped as configured.
4. One line parses cleanly yet fails business validation: processSkipCount increments if exception is skippable.
5. Faulty lines exceed skip limit: Step FAILED.
6. Non-skippable exception thrown: Step FAILED.
7. File does not exist: reader open fails; not counted as an item skip.
8. Invalid header: caught via skippedLinesCallback or header validation step, not counted toward skip count.
9. CSV with quoted newline: verify record boundaries and line numbers.
10. Restart after committing chunks: checkpoints and outputs have no gaps or duplicates.

## 17. Common mistakes

**Skipping every Exception:** file-open, I/O, or infrastructure errors can be hidden. Only skip exception types tied to individual records.

**Assuming every faulty line produces FlatFileParseException:** business errors in the processor have their own exceptions; resource-open errors may be ItemStreamException or other I/O exceptions.

**Forgetting to enable fault tolerance:** registering a listener alone does not make the reader skip bad lines. Configure faultTolerant(), skip policy, and an appropriate skipLimit.

**Setting skip limit too high:** Jobs can complete while silently omitting most of the data. Choose thresholds from business requirements and monitor skip rates.

**Confusing headers with skips:** linesToSkip and skippedLinesCallback handle leading file lines and do not consume the skip limit.

**Not recording line numbers and sources:** makes it hard to locate bad lines in large files or multi-file Jobs.

**Logging raw lines containing sensitive data:** can expose personal info or business secrets. Store in controlled quarantine or log minimal metadata.

**Not testing fixed-width and multi-line CSV:** parsers may resolve record boundaries differently from assuming one physical line per item.

**Confusing parse errors with resource errors:** a file that cannot be opened has no single item to skip.

**Replacing files before restart:** old checkpoints no longer match content. Keep files immutable or verify versions/checksums.

**Never replaying faulty lines:** skipping keeps the batch moving, yet excluded data still needs auditing, fixing, and replay if business completeness is required.

## Conclusion

To handle files containing faulty lines in Spring Batch, configure FlatFileItemReader with an appropriate tokenizer and mapper, declare parse exceptions such as FlatFileParseException as skippable in a fault-tolerant Step, and enforce a controlled skipLimit. SkipListener.onSkipInRead can extract the line number, raw input, and cause from the exception to store faulty lines in quarantine. Clearly distinguish bad data lines from resource-open failures, headers, comments, and filtered items, as each has a different mechanism. Keep source files stable, enable checkpoints for restarts, verify output data alongside skip counters, and build a replay workflow so skipped lines never lose business traceability.
