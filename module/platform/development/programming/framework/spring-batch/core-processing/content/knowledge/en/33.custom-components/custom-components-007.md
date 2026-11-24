# Handling Null and End of Input

In Spring Batch, `null` carries a special meaning at the `ItemReader` boundary: when `read()` returns `null`, the framework understands that the reader has reached the end of its data and no further items remain in that execution. Therefore, a custom reader must never use `null` to represent a valid but empty record, a missing data field, or a source that temporarily has no items.

Elsewhere, `ItemProcessor` can return `null` to instruct Spring Batch to filter out an item. That is filtering behavior, not end of input and not an exception-driven skip. Understanding these distinct meanings prevents jobs from terminating early, losing records, or reporting inaccurate counters.

## 1. The ItemReader.read() Contract

`ItemReader<T>` has one primary method:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

The method's contract:

- Return an item when data remains.
- Return `null` when no more items exist to read.
- Throw an exception when a read, parse, or source error occurs that needs handling.

Spring Batch invokes `read()` repeatedly until it receives `null`. At that point, the reader is considered to have reached end of input (EOF) and the step begins concluding the read phase. If a reader returns `null` mid-file merely because it hit a blank line or an invalid record, subsequent records may never be processed.

Example simple reader:

```java
public class CustomerReader implements ItemReader<Customer> {

    private final Iterator<Customer> customers;

    public CustomerReader(List<Customer> customers) {
        this.customers = customers.iterator();
    }

    @Override
    public Customer read() {
        if (!customers.hasNext()) {
            return null; // No more items: end of input.
        }
        return customers.next();
    }
}
```

The reader returns `null` only when the iterator has no elements left. Every valid element must be a non-null object.

## 2. Three Distinct Meanings of null

In a batch pipeline, distinguish at least three cases:

| Location | Meaning of `null` | Spring Batch behavior |
|---|---|---|
| `ItemReader.read()` | No next item exists. | Ends the step's reading phase. |
| `ItemProcessor.process(item)` | Do not keep this item in output. | Filters item; item is not passed to writer. |
| Field inside domain object | An attribute has no value. | Still a normal item; processor/validator decides handling. |

Example of a customer whose email was not provided:

```java
Customer customer = new Customer("C001", "Nguyen An", null);
```

The `customer` object is still a valid item at the reader boundary. `email == null` simply means the email field has no value. The reader must not return `null` for the whole object just because one field is missing.

Conversely, if `ItemProcessor` returns `null`, Spring Batch understands the item was filtered out. That is a pipeline decision after the item was successfully read.

## 3. Do Not Use null to Represent an Empty Record or Error

Suppose an input file has these lines:

```text
C001,Nguyen An,an@example.com

C002,Tran Binh,binh@example.com
INVALID-LINE
C003,Le Chi,chi@example.com
```

If a custom reader is written like this:

```java
@Override
public Customer read() throws Exception {
    String line = reader.readLine();
    if (line == null || line.isBlank()) {
        return null;
    }
    return parseCustomer(line);
}
```

then the very first blank line makes the reader return `null`. Spring Batch treats it as EOF and stops calling `read()` for `C002` or `C003`.

If an invalid line is likewise converted to `null`, errors are hidden and the rest of the file can be skipped silently. This is a severe bug because the job may finish as if it had read the entire source.

Reserve `null` exclusively for when no more data exists. For blank lines, invalid records, or missing fields, define explicit policies: intentional skipping, creating an error-representing item, or throwing an appropriate exception.

## 4. Skipping Blank Lines in a Custom Reader

If blank lines are defined as non-data lines that can be ignored, the reader can keep reading within the same call until it finds a record or reaches EOF:

```java
public class CustomerCsvReader implements ItemReader<Customer> {

    private final BufferedReader reader;

    public CustomerCsvReader(BufferedReader reader) {
        this.reader = reader;
    }

    @Override
    public Customer read() throws IOException {
        String line;

        while ((line = reader.readLine()) != null) {
            if (line.isBlank()) {
                continue; // Blank line is not EOF.
            }

            return parseCustomer(line);
        }

        return null; // Only EOF returns null.
    }

    private Customer parseCustomer(String line) {
        String[] columns = line.split(",", -1);
        return new Customer(columns[0], columns[1], columns[2]);
    }
}
```

This snippet illustrates the principle. A real reader must validate column counts, handle commas inside quoted fields, handle encoding, and report parse errors. If CSV files use quoting rules, prefer `FlatFileItemReader` with an appropriate tokenizer/line mapper rather than manual `split`.

Skipping blank lines inside the reader does not increment `filterCount` or `skipCount`, because those lines are never returned as items. If you need blank-line statistics, increment a separate counter or record via a listener/metric.

## 5. Null in Source Data vs. End of Input

Data sources can represent "no value" in many ways:

- A database column containing SQL `NULL`.
- A JSON field whose value is `null`.
- An empty CSV field.
- A file line containing only delimiters or whitespace.
- A structured record missing a required field.

None of these automatically mean the source has ended.

Database example:

```java
public Customer mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new Customer(
            rs.getString("customer_id"),
            rs.getString("name"),
            rs.getString("email")); // May be null if the SQL column is NULL.
}
```

`RowMapper` still returns a non-null `Customer`; only the `email` field can be null. If a `RowMapper` returns `null` for a row, cursor-based readers may interpret that value as an EOF signal under the `ItemReader` contract, ending reading prematurely. Always map a row to a non-null item, or handle/reject that row explicitly.

## 6. Handling JSON null Inside a JSON Array

A JSON array can contain a `null` element:

```json
[
  {"customerId":"C001","name":"Nguyen An"},
  null,
  {"customerId":"C003","name":"Le Chi"}
]
```

This is an element inside the JSON data, not the end of the array. However, the `ItemReader` contract reserves a `null` return value for end of input. If an object reader deserializes the JSON `null` element into Java `null`, the reader cannot pass it as a normal item without confusing it with EOF.

Before implementing, define the source rule:

- If a `null` element is invalid data, reject the file or raise a parse/validation error.
- If a `null` element can be ignored, the custom reader can loop to the next object and record the dropped count.
- If the "null element" event must be preserved for auditing, represent it with a non-null wrapper such as `Optional.empty()` or a status-bearing record.

Example using a wrapper:

```java
ItemReader<Optional<Customer>> reader = ...;

ItemProcessor<Optional<Customer>, Customer> processor = record ->
        record.orElse(null); // Optional.empty() becomes an intentional filter.
```

Here the reader returns `Optional.empty()` as a non-null item object. The processor then decides to filter it by returning `null`. If reasons must be recorded, log them in a processor/listener or use a typed result wrapper rather than silently filtering.

## 7. ItemProcessor Returning null Means Filter

`ItemProcessor<I, O>` can return `null`. In Spring Batch, that means the input item is excluded from reaching the writer.

Example exporting only active customers:

```java
@Bean
ItemProcessor<Customer, Customer> activeCustomerProcessor() {
    return customer -> customer.active() ? customer : null;
}
```

If `active()` is false, the processor returns `null`; the item is filtered. The step continues with remaining items.

A processor can map and then filter:

```java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.status() == CustomerStatus.DELETED) {
            return null;
        }

        return new Customer(
                input.customerId(),
                input.name(),
                input.email());
    };
}
```

Use `null` only when excluding the item is a normal business decision. Never use it to hide exceptions, malformed data, or unprocessable errors.

## 8. Filter Differs from Skip

Both filtering and skipping prevent an item from reaching the writer, but their causes and counters differ.

| Mechanism | How it occurs | Counter |
|---|---|---|
| Filter | Processor returns `null`. | `filterCount` increments. |
| Skip | Reader, processor, or writer throws an exception allowed by skip policy. | `readSkipCount`, `processSkipCount`, `writeSkipCount`, and `skipCount` increment per phase. |
| EOF | Reader returns `null` because source is exhausted. | Ends reading; neither filter nor skip. |

Filter example:

```java
return customer.isActive() ? customer : null;
```

Skip example:

```java
if (customer.customerId() == null) {
    throw new InvalidCustomerException("customerId is required");
}
```

If `InvalidCustomerException` is configured as skippable, the framework can skip the item and invoke `SkipListener`. Filtering raises no exception and therefore bypasses skip policies.

Do not return `null` from a processor merely to avoid configuring skip policies. When a bad item needs to be tracked as a data error, throw an appropriate exception and use a skip policy/`SkipListener` or a rejected-record store.

## 9. Empty Input vs. End of Input

An empty file or an empty JSON array can be syntactically valid input containing zero items.

Empty JSON array:

```json
[]
```

The reader returns `null` on its very first `read()` call. The step can complete with `readCount` equal to 0. That is normal EOF behavior, not automatically an error.

However, business rules may require a file to contain at least one record. Handle that explicitly:

- Validate the file before running the step.
- Use a listener to inspect `readCount` after the step completes and adjust the outcome if no items were read.
- Use a tasklet/validation step to confirm the minimum record count.

Do not alter the meaning of `null` just to force empty input to fail. Keep the reader contract clean and place "must not be empty" rules in the job's validation layer.

## 10. Do Not Use null for Sources Temporarily Lacking Data

For finite files, returning `null` at the end is right. However, some sources are not finite datasets—for example, queues, sockets, event streams, or polling APIs.

Suppose a queue is temporarily empty right now but will receive items in a few seconds. If a reader calls `poll()` and returns `null` when the queue is briefly empty, Spring Batch treats it as EOF and finishes the step. Items arriving afterward are never read.

Avoid writing:

```java
@Override
public Message read() {
    return queue.poll(); // null may only mean the queue is currently empty.
}
```

For asynchronous sources, define an explicit completion signal. Options include:

- Blocking/waiting until an item arrives or a completion signal is received.
- Polling in a bounded loop and distinguishing timeouts from completion.
- Using a sentinel/poison pill to mark end of stream.
- Using a message-driven or integration model suited to the source instead of emulating a finite file.

Example using a sentinel:

```java
public class QueueMessageReader implements ItemReader<Message> {

    private static final Object END_OF_STREAM = new Object();
    private final BlockingQueue<Object> queue;

    public QueueMessageReader(BlockingQueue<Object> queue) {
        this.queue = queue;
    }

    @Override
    public Message read() throws InterruptedException {
        Object next = queue.take(); // Wait for an item or sentinel.
        if (next == END_OF_STREAM) {
            return null; // Only the sentinel terminates the reader.
        }
        return (Message) next;
    }
}
```

In multi-consumer setups, send enough sentinels for every reader/worker that must terminate, or use another completion coordinator. Do not send a single sentinel if one worker consumes it while others keep waiting indefinitely.

If using `poll(timeout)` and the timeout expires, do not return `null` unless timeout genuinely signifies stream completion. Continue waiting, check a completion flag, or throw an exception aligned with your retry/poll policy.

## 11. Distinguishing EOF, Data Errors, and Source Errors

A custom reader should distinguish three outcome groups:

| Scenario | Reader action | Meaning |
|---|---|---|
| Source exhausted | Return `null`. | Normal completion. |
| Single invalid record | Throw parse/validation exception or return an error wrapper per design. | Framework/processor applies fail, retry, or skip. |
| I/O error or source temporarily unavailable | Throw corresponding exception. | Retryable if recoverable; otherwise step fails. |

Never convert all exceptions into `null`:

```java
// Not recommended: turning a read error into EOF.
try {
    return parseNextRecord();
} catch (Exception exception) {
    log.warn("Cannot read record", exception);
    return null;
}
```

The code above can make a step complete successfully even when data remains or the file is corrupted. Throw the exception so Spring Batch records the failure and applies configured policies.

## 12. Example Custom Reader Distinguishing Bad Lines from EOF

A reader can read line by line, skip blank lines per rule, and throw an exception when a record breaks format rules:

```java
public class StrictCustomerReader implements ItemReader<Customer> {

    private final BufferedReader reader;

    public StrictCustomerReader(BufferedReader reader) {
        this.reader = reader;
    }

    @Override
    public Customer read() throws IOException {
        String line;

        while ((line = reader.readLine()) != null) {
            if (line.isBlank()) {
                continue;
            }

            String[] fields = line.split(",", -1);
            if (fields.length != 3) {
                throw new InvalidCustomerRecordException(
                        "Expected 3 fields but found " + fields.length);
            }

            return new Customer(fields[0], fields[1], fields[2]);
        }

        return null;
    }
}
```

In this example:

- Blank lines are skipped.
- Records with the wrong field count raise an exception.
- The reader continues returning valid customers.
- Only when `readLine()` returns `null` does the reader return `null` to Spring Batch.

To skip bad records and keep going, let the exception pass through a skip policy. The reader must ensure that after throwing, it remains positioned to read the next record. With some sources or parsers, an exception desynchronizes the read cursor; in that case, design dedicated recovery or fail the step.

## 13. Handling null in ItemProcessor

A processor can receive a non-null item and return a non-null output, or return `null` to filter.

Example transformation and filter:

```java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.status() == null) {
            throw new InvalidCustomerException("status is required");
        }

        if (input.status() == CustomerStatus.ARCHIVED) {
            return null; // Intentional filter.
        }

        return new Customer(
                input.customerId(),
                input.name(),
                input.email());
    };
}
```

Do not return `null` when `status` is missing if a missing status is invalid data that requires error handling. In the example, `ARCHIVED` is a business filter criterion, whereas a `null` status is a data error.

A processor can be designed to filter multiple cases. Record filter reasons if auditing is needed; looking only at `filterCount` does not show which items were dropped or why.

## 14. Null and CompositeItemProcessor

When using `CompositeItemProcessor`, delegates run sequentially. If one delegate returns `null`, the pipeline has no output item to pass onward; the item is filtered and subsequent delegates do not process it.

Example:

```java
CompositeItemProcessor<CustomerInput, Customer> processor =
        new CompositeItemProcessorBuilder<CustomerInput, Customer>()
                .delegates(
                        validateCustomerProcessor,
                        filterArchivedCustomerProcessor,
                        mapCustomerProcessor)
                .build();
```

If `filterArchivedCustomerProcessor` returns `null`, `mapCustomerProcessor` is not invoked for that item. This behavior must be designed intentionally.

Do not use `null` to signal to the next delegate that an item is "not ready yet." To pass intermediate states, use a wrapper object or strongly typed result. If a delegate hits an error, throw an exception so retry/skip/fail policies trigger properly.

## 15. Null in ItemWriter

A writer receives a `Chunk` containing the pipeline's output items. In normal design, the chunk should never contain `null` items.

If a processor returns `null`, the item was filtered and excluded from the writer's chunk. If a custom reader returns `null`, Spring Batch treats it as EOF, not as a null element to write.

Therefore, the writer should never have to guess what `null` means. Ensure readers emit only valid non-null items, processors return either objects or `null` strictly for filtering, and writers receive normalized items.

If an output format needs to represent JSON `null`, build a dedicated writer/marshaller or use an explicit wrapper representing null values. Do not try to pass Java `null` as a regular item through `ItemReader`.

## 16. Empty Chunk After Filtering

A chunk may read several items that are all filtered by the processor. Then no output items remain to write. Spring Batch can still complete the chunk/step and update counters accordingly; the writer normally has nothing to write.

Example:

```text
Reader:      A, B, C, D
Processor:   A -> null
             B -> null
             C -> null
             D -> null
Writer:      no output items
```

In this case:

- `readCount` reflects items returned by the reader.
- `filterCount` reflects items excluded by the processor.
- `writeCount` does not increase for filtered items.
- `skipCount` does not increase simply because the processor returned `null`.

If business rules forbid filtering out every item, inspect counters after the step or add validation. Do not replace filtering with returning `null` from the reader to terminate early.

## 17. End of Input vs. Empty Input

These two concepts are related yet distinct:

- **Empty input:** the source contains zero items from the very beginning.
- **End of input:** the reader has finished reading every item from the current source.

With an empty file, the first `read()` call returns `null`. With a 100-item file, the reader returns 100 items and only the next call returns `null`.

Spring Batch does not treat empty input as an error by default. If a job requires at least one item, inspect `readCount` after the step:

```java
public class RequireInputListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getReadCount() == 0) {
            return ExitStatus.FAILED.addExitDescription(
                    "Input contained no records");
        }
        return null;
    }
}
```

This snippet illustrates setting a failed `ExitStatus` when zero records were read. If you need to change `BatchStatus` or control detailed flow transitions, design appropriate transitions and listeners; `ExitStatus` and `BatchStatus` are distinct concepts.

Another option is adding an input validation step before processing. That fits well when verifying file existence, minimum size, headers, or record counts before the writer starts creating output.

## 18. ItemStreamReader and End of Input on Restart

Checkpoint-capable custom readers typically implement `ItemStreamReader<T>`, combining `ItemReader` and `ItemStream`:

```java
public interface ItemStreamReader<T> extends ItemReader<T>, ItemStream {
}
```

Core lifecycle:

- `open(ExecutionContext)`: open resources and restore saved position.
- `read()`: return the next item or `null` when input ends.
- `update(ExecutionContext)`: save state required for restarts.
- `close()`: release resources.

EOF in one execution does not mean the reader lost restartability. When a job restarts, a new reader instance opens with the saved `ExecutionContext` and resumes from the appropriate checkpoint.

Do not save an `eof=true` flag in context if doing so could cause a restart to skip uncommitted data. Save checkpoints strictly per chunk/transaction semantics and ensure state commits alongside metadata.

## 19. Example Checkpointable Custom Reader

The following example uses an immutable list to illustrate separating EOF from saved state:

```java
public class CheckpointCustomerReader implements ItemStreamReader<Customer> {

    private static final String INDEX_KEY = "checkpointCustomerReader.nextIndex";

    private final List<Customer> customers;
    private int nextIndex;

    public CheckpointCustomerReader(List<Customer> customers) {
        this.customers = List.copyOf(customers);
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.getInt(INDEX_KEY, 0);
    }

    @Override
    public Customer read() {
        if (nextIndex >= customers.size()) {
            return null; // EOF, no more items.
        }

        Customer customer = customers.get(nextIndex++);
        return Objects.requireNonNull(customer,
                "Reader source must not contain null items");
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(INDEX_KEY, nextIndex);
    }

    @Override
    public void close() {
        // No external resources to close in this example.
    }
}
```

`List.copyOf` also rejects null elements, catching null-containing sources right at reader construction. This example demonstrates index checkpointing; production readers must checkpoint by real source positions/keys and require immutable sources between initial runs and restarts.

Spring Batch calls `update` per stream/chunk lifecycle to persist state. With a transaction-aware `JobRepository`, `ExecutionContext` saves with the appropriate commit. When a chunk rolls back, the previously committed checkpoint remains the reliable recovery point.

## 20. Using AbstractItemCountingItemStreamItemReader

Spring Batch provides the base class `AbstractItemCountingItemStreamItemReader<T>` for readers that track the count of read items. It manages the current item count and state for restarts.

Structural example:

```java
public class NumberItemReader
        extends AbstractItemCountingItemStreamItemReader<Integer> {

    private final int max;

    public NumberItemReader(int max) {
        this.max = max;
        setName("numberItemReader");
    }

    @Override
    protected Integer doRead() {
        int current = getCurrentItemCount();
        if (current >= max) {
            return null;
        }
        return current + 1;
    }

    @Override
    protected void doOpen() {
        // Open resource if needed.
    }

    @Override
    protected void doClose() {
        // Close resource if needed.
    }
}
```

The base class manages item counts and state restoration; the implementation must still ensure `doRead()` returns `null` only when data is truly exhausted. For sources with complex positioning, such as variable-length files or API cursors, use a checkpoint better suited than item counts.

Do not reimplement counting/checkpointing manually if the base class fits your needs. However, assign a stable reader name and enable state saving as configured.

## 21. End of Input with MultiResourceItemReader

When reading multiple files, EOF of a single resource is not necessarily EOF of the entire reader. `MultiResourceItemReader` manages a list of resources and a delegate reader.

```text
file-01.csv
   |
   +-- delegate reads until EOF
   |
   v
file-02.csv
   |
   +-- delegate reads until EOF
   |
   v
file-03.csv
   |
   +-- delegate reads until EOF
   |
   v
No more resources -> MultiResourceItemReader returns null
```

The delegate returns `null` to signal the end of the active resource. `MultiResourceItemReader` advances to the next resource and returns `null` only after every resource is exhausted.

When a custom reader/decorator wraps a delegate, preserve this semantics. Never treat `null` from a single sub-file as EOF for the entire resource set if further files remain.

## 22. Adapters and Data Sources Returning null

`ItemReaderAdapter` wraps a service/object exposing a read method. If the delegated method returns `null`, the adapter converts that result into `null` from `ItemReader.read()`, signaling EOF.

Therefore, the delegate API needs a clear contract:

- Return an item when data exists.
- Return `null` only when the source is finished.
- If no data is available right now but more may arrive later, block/poll or return a non-null status.
- On errors, throw an exception rather than returning `null`.

If an existing API uses `null` for "not found", "no data yet", and "stream ended", build an adapter with an explicit result class before integrating it into Spring Batch.

## 23. Null and Asynchronous Processing

In asynchronous or multi-threaded steps, items may pass between reader, processor, and writer via queues or futures. Preserve the contract: `null` from the reader means no more items.

Do not use `null` to signal "this worker temporarily has no work" if the reader may be called again later. For queues, use blocking waits or completion markers. For futures, use wrapper results distinguishing "incomplete", "completed without value", and "has item".

When multiple consumers exist, deliver termination signals to every consumer that must stop. A single poison pill may stop only one worker while others block forever without coordination.

Additionally, `ItemReader` is not inherently thread-safe. If multiple threads call the same reader, ensure the implementation supports concurrency or use partitioning with isolated reader instances and state.

## 24. Observing Filter, Skip, and EOF

To distinguish reading all data, filtering items, and skipping errors, check `StepExecution` counters:

| Counter | Meaning |
|---|---|
| `readCount` | Items successfully returned by the reader. |
| `filterCount` | Items filtered by the processor returning `null`. |
| `writeCount` | Items written per writer/step semantics. |
| `readSkipCount` | Read-phase errors skipped. |
| `processSkipCount` | Process-phase errors skipped. |
| `writeSkipCount` | Write-phase errors skipped. |
| `skipCount` | Total skipped items/errors. |

EOF does not have a skip counter. The reader returns `null` for normal completion. If `readCount` is unexpectedly low relative to source records, check whether a custom reader returns `null` prematurely.

Additional useful metrics:

- Blank lines skipped inside the reader.
- JSON null elements or empty records normalized.
- Rejected records broken down by reason.
- Last parser position or byte offset.
- Timestamp when the reader reached EOF.

Avoid high-cardinality metric tags like per-record item IDs. Use logs with correlation IDs or a rejected-record table for detailed tracing.

## 25. Testing the End-of-Input Contract

A custom reader should have tests verifying basic cases:

1. Single-item source: first call returns the item, next call returns `null`.
2. Multi-item source: returns all items in order and only then returns `null`.
3. Empty source: first read returns `null`.
4. Mid-file blank lines: reader skips or handles per policy while still reading subsequent records.
5. Invalid record: reader throws exception or returns error wrapper; never returns `null` posing as EOF.
6. Null fields: item is still returned if the record is valid.
7. Temporarily empty source: reader does not terminate if the stream is not complete.
8. True EOF: reader consistently returns `null` after source exhaustion.

Simple test example:

```java
@Test
void returnsItemsBeforeEndOfInput() throws Exception {
    Customer first = new Customer("C001", "Nguyen An", null);
    Customer second = new Customer("C002", "Tran Binh", "b@example.com");
    CustomerReader reader = new CustomerReader(List.of(first, second));

    assertThat(reader.read()).isEqualTo(first);
    assertThat(reader.read()).isEqualTo(second);
    assertThat(reader.read()).isNull();
}
```

Reader tests should not verify only that the final call returns `null`. Verify that all preceding records were returned intact.

## 26. Testing Filter vs. EOF

Processor tests should prove that `null` output filters only a single item without terminating the reader or step.

```java
@Test
void filtersArchivedCustomer() throws Exception {
    ItemProcessor<Customer, Customer> processor = customer ->
            customer.active() ? customer : null;

    Customer active = new Customer("C001", "Nguyen An", true);
    Customer archived = new Customer("C002", "Tran Binh", false);

    assertThat(processor.process(active)).isEqualTo(active);
    assertThat(processor.process(archived)).isNull();
}
```

Integration tests should confirm `filterCount` increments, `skipCount` does not increment from filtering, and subsequent items continue processing.

## 27. Testing Sources with Zero Data

If empty input is valid, tests should confirm the step completes with `readCount == 0` and the writer writes no items. If empty input is invalid, tests should confirm the validation step or listener transitions the outcome to an error state per design.

Do not assert solely that `reader.read()` returns `null` and conclude the entire job handles empty input properly. Check job flow, empty/missing output files per policy, and final execution status.

## 28. Testing Restarts and EOF

For stateful readers, test:

- Some chunks commit before the step fails.
- `ExecutionContext` stores the matching checkpoint.
- Restart opens a new reader and restores the right position.
- Uncommitted items are re-read.
- EOF is returned only when the source is truly exhausted.
- The reader does not save an EOF flag prematurely causing restarts to skip data.
- Input does not change between initial run and restart.

For custom readers, test `open`, `read`, `update`, and `close` across both executions. For file or queue readers, also test closing/reopening resources and missing or invalid checkpoints.

## 29. Common Pitfalls When Handling Null and EOF

| Symptom | Common cause | Fix |
|---|---|---|
| Step stops mid-file | Reader returns `null` on blank lines or bad records. | Return `null` only when source ends; skip/throw for other lines. |
| Records with SQL NULL fields lost | `RowMapper` returns `null` for the whole row instead of an object with null fields. | Return a non-null domain object keeping null in the field. |
| JSON array stops at `null` element | Null element mapped to Java `null` at reader boundary. | Skip/normalize/reject via custom reader or wrapper. |
| Filters counted as skips | Confusing processor `null` with skippable exceptions. | Inspect `filterCount` and `skipCount` separately. |
| Empty queue ends the step | `poll()` returns `null` when temporarily without messages. | Block, keep polling, or use a completion sentinel. |
| Parse errors hidden | Catching exceptions and returning `null`. | Throw appropriate exceptions for fault tolerance. |
| Empty file unexpectedly succeeds | Spring Batch treats immediate EOF as normal. | Validate `readCount` if business rules require records. |
| Multi-resource reader stops after first file | Wrapper treats delegate `null` as overall EOF. | Follow `MultiResourceItemReader` semantics and advance resources. |
| Restart skips items | Checkpoint saves inconsistent position/EOF state. | Save state on chunk commits and test restarts. |
| Writer receives null item | Reader/processor violated contract. | Normalize items before writer; never emit null as an item. |

## 30. Workflow for Designing Null and End-of-Input Handling

When writing custom components, define each case clearly:

1. **Define item boundaries:** what counts as a valid record in the source?
2. **Define EOF:** what signal proves no further data exists?
3. **Classify source nulls:** null field, empty record, explicit JSON null, or no record?
4. **Choose representation:** null field in object, wrapper/`Optional`, filter, or exception.
5. **Handle errors:** separate parse errors, data errors, and transient source errors.
6. **Protect the reader contract:** never return `null` before true EOF.
7. **Design filter/skip:** processor returns `null` to filter; exceptions and skip policies handle skippable errors.
8. **Check empty input:** decide whether the job accepts zero items.
9. **Save checkpoints:** update state consistently with chunk commits and restarts.
10. **Test boundaries:** first/last items, blank lines, null records, mid-source errors, empty input, and temporarily empty sources.
11. **Monitor counters:** distinguish reads, filters, skips, and EOF.

## 31. Key Takeaways

- `ItemReader.read()` returns `null` to signal end of input; this terminates reading for the step.
- Never return `null` for valid records, mid-file blank lines, parse errors, or sources temporarily lacking data.
- A `null` field inside a domain object is not equivalent to `null` at the reader boundary.
- `ItemProcessor.process()` returning `null` filters the item; it is neither EOF nor a skip.
- Filtering increments `filterCount`; skipped exceptions increment skip counters.
- Empty input can complete normally; if business rules require at least one item, validate separately.
- Throw exceptions for read/parse errors; do not catch all errors and return `null` to finish silently.
- For JSON arrays containing `null` elements, normalize, skip, or reject using a non-null representation.
- Asynchronous/queue sources must separate temporary absence of items from completion signals; use blocking or explicit sentinels.
- `MultiResourceItemReader` advances to the next resource when a delegate hits EOF; it terminates only when all resources are exhausted.
- Custom `ItemStreamReader`s must manage `open`, `read`, `update`, `close`, and checkpoints on transaction boundaries.
- Thoroughly test items before EOF, empty input, null fields, bad records, filtering, and restarts.

Handling `null` and end of input is part of the contract between custom readers, processors, and Spring Batch. Reserve `null` in readers strictly for EOF, use `null` in processors strictly for intentional filtering, and represent missing data with appropriate objects, fields, or wrappers. Clearly distinguishing EOF, empty input, invalid records, and temporarily empty sources prevents premature job termination and preserves error traceability and safe restarts.
