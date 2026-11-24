# `read()` Returns `null` to Signal the End of Input

In Spring Batch, `ItemReader` provides items one at a time to a Step that processes data in chunks. The contract of the `read()` method defines a special meaning: when the reader returns an item, the Step continues processing that item; when the reader returns `null`, Spring Batch understands that the input source is exhausted and there are no more items to read in the current execution.

The `null` value is therefore the end-of-data signal (end of input or end of file), not an empty record and not a way to report an error. If the reader encounters an error while accessing the data source, it should throw an appropriate exception so that Spring Batch can handle it according to the Step's retry, skip, or fail configuration.

## 1. The ItemReader.read() Contract

The `ItemReader<T>` interface has one main method:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Each time it is called, `read()` returns the next item of type `T`, or returns `null` when there are no more items. The reader usually maintains an internal read position so that each subsequent call gets the next item.

Example with an input source containing three records:

```text
read() call        Return value
---------------------------------
Call 1             item-A
Call 2             item-B
Call 3             item-C
Call 4             null  -> end of input
```

Once the reader has run out of data, subsequent calls within the same execution must continue to indicate that there are no more items. The reader must not go back to the first item or generate new data after it has signaled EOF, unless it is a source designed with its own looping mechanism and a different contract.

What matters is that `read()` returns **one item per call**, not a whole chunk. Spring Batch is responsible for calling the reader repeatedly to get enough items for a chunk according to the configured commit interval.

## 2. How Does Spring Batch Use the `null` Signal?

In chunk-oriented processing, the Step calls `ItemReader.read()` repeatedly until it reaches the chunk size or the reader returns `null`.

Example of a Step with a chunk size of 4 and a reader that has only 6 items left:

```text
Chunk 1
  read() -> A
  read() -> B
  read() -> C
  read() -> D
  ItemProcessor -> processes A, B, C, D
  ItemWriter    -> writes chunk 1
  Commit

Chunk 2
  read() -> E
  read() -> F
  read() -> null  (EOF)
  ItemProcessor -> processes E, F
  ItemWriter    -> writes chunk 2
  Commit

No more items -> the Step finishes reading input
```

The last chunk can be smaller than the commit interval. When the reader returns `null` after having provided some items for the current chunk, Spring Batch still processes and writes the remaining items in that chunk. After the last chunk completes, the Step finishes the data-reading phase.

If the reader returns `null` on the very first call, the input source is empty. The Step can complete normally with a `readCount` of 0; this is not automatically treated as an error. If the business requires at least one record, the application needs to check that condition with a validator, a listener, or separate business logic.

## 3. A Simple ItemReader Example

Suppose the application has a list of data already loaded into memory. The reader can use an iterator to return the elements one by one:

```java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        if (iterator.hasNext()) {
            return iterator.next();
        }

        return null;
    }
}
```

When the iterator still has elements, the reader returns the next element. When `hasNext()` returns `false`, the reader returns `null` to signal the end of input.

This is a minimal example for learning purposes. With large data, you should not load the entire source into a `List` just to use this reader because it can consume a lot of heap. In production, you should read as a stream, with a cursor, or page by page, as appropriate for the data source.

A reader should not return `null` as a valid item. If the list contains a `null` element, the code above would make Spring Batch wrongly conclude that the source ended at that position. Check and remove invalid null data beforehand, or represent optional data fields inside a non-null object.

## 4. Example with FlatFileItemReader

For text files, `FlatFileItemReader` manages reading lines and mapping each line to an object. When there are no more lines to read, the reader returns `null` according to the `ItemReader` contract.

Example of configuring the reader in Spring Batch 5:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

In this example:

- The reader opens the file specified by the `inputFile` JobParameter.
- Each valid data line is mapped to a `CustomerInput`.
- The reader keeps returning objects one by one until the end of the file.
- At the end of the file, the reader returns `null`, telling the Step to stop fetching more items.

If the file does not exist, cannot be opened, or has a read/parse error, the reader may throw an exception. This is a different situation from a file that exists but has no data lines: EOF is a normal end, whereas an access or parse error is an error that must be handled according to the Job's policy.

## 5. Distinguishing `null` from ItemReader and `null` from ItemProcessor

These are two different meanings, even though both use the `null` value.

| Component | When it returns `null` | Meaning |
|---|---|---|
| `ItemReader.read()` | No more items to read | End of input; the Step does not request more items from the reader |
| `ItemProcessor.process(item)` | The input item is removed from the processing flow | Filter the item; the reader can still continue reading the next item |

For example, the source has 5 customers. The reader returns all 5 items, but the processor filters out inactive customers by returning `null`:

```java
@Bean
ItemProcessor<CustomerInput, Customer> activeCustomerProcessor() {
    return input -> {
        if (!input.isActive()) {
            return null; // Only drops the current item
        }

        return new Customer(input.customerId(), input.fullName());
    };
}
```

In this case, the reader is still called for the following records. A `null` from the processor does not signal the end of the file or the end of the database result set; it only means the current item is not passed to the writer. The `filterCount` counter may increase accordingly.

Conversely, when `ItemReader.read()` returns `null`, Spring Batch understands that there are no more input items to request. Therefore, you must not use `null` from the reader to indicate a record that should be skipped.

## 6. Distinguishing EOF from Read Errors

A reader can encounter two groups of situations:

**Normal end:** the source has been fully read. The reader returns `null`; the Step finishes reading and completes the last chunk if there are items remaining.

**Read error:** the source cannot be accessed, the data is corrupt, the database connection is lost, or the format cannot be parsed. The reader throws an exception; the Step handles the error according to the retry, skip, or fail configuration.

Example:

```java
@Override
public CustomerInput read() throws Exception {
    try {
        String line = bufferedReader.readLine();

        if (line == null) {
            return null; // Normal EOF
        }

        return parseCustomer(line);
    } catch (IOException ex) {
        throw new ItemStreamException("Cannot read input", ex);
    }
}
```

The code only illustrates how to distinguish EOF from an I/O error. A real reader needs to manage opening and closing resources, the read state, and exceptions appropriate to the type of source. If `parseCustomer()` detects an invalid line, the application needs to decide whether it is an error that stops the Step or an error that can be skipped according to the configuration. Do not convert every exception to `null`, because then the Job will end as if the input were exhausted and may miss unread data.

## 7. A Source That Temporarily Has No Data Does Not Mean EOF

An important point when reading from a queue, a paginated API, or a continuously generated data source is to distinguish **there is currently no data** from **the input source has ended**.

According to the `ItemReader` contract, returning `null` means the reader has run out of input for the current execution. If the reader is reading from a queue and the queue is temporarily empty, returning `null` will make the Step conclude that the work is complete. Messages that arrive afterward may not be read in this Job run.

If the business requirement is to wait for new data, you need to design the reader or the processing architecture appropriately:

- Poll the source for a predetermined period before concluding that there is no more data.
- Use a timeout and a clear wait/retry policy.
- Determine the end condition by a watermark, a batch ID, the time the batch is closed, or an end signal from the source system.
- For a continuous data flow, consider a consumer or streaming architecture instead of a batch Job with an undetermined end point.

Do not return `null` merely because an API call does not find a record at the current moment if the Job still has to wait for data in the future.

## 8. `null` and Checkpoints on Restart

For a reader that supports `ItemStream`, Spring Batch can save the read state into the `ExecutionContext` to support restart. The common callbacks are:

- `open(ExecutionContext)`: opens the resource and restores the saved state, if any.
- `update(ExecutionContext)`: saves the current state, such as the read position, into the context.
- `close()`: releases the resource when the Step ends.

A custom reader needs to implement `ItemStream` if it wants to save and restore the read position. For example, a file-reading reader can save the line number or byte position that has been processed. On restart, it uses the checkpoint to continue from the appropriate position.

```text
Input: A B C D E F G H
Chunk size: 3

Chunk 1: A B C -> COMMIT, save checkpoint after C
Chunk 2: D E F -> error before COMMIT
                 |
                 v
              Restart
                 |
                 v
        Restore checkpoint after C
        Re-read the uncommitted portion according to the reader state
```

If the reader does not save state, a restart may start reading again from the beginning or may be unable to restore the correct position. The specific handling depends on the reader and the data source. Even if the reader has a checkpoint, external side effects outside the transaction still need an idempotency mechanism because an item may be read or processed again.

A reader returning `null` when the data is truly exhausted keeps the same meaning in a restarted run. The checkpoint determines the position to resume from; `null` signals that from that position there are no more items.

## 9. Common Mistakes When Implementing an ItemReader

**Returning `null` for a faulty record:** Spring Batch interprets that as EOF and ends reading, so the data after it is not processed. Throw an exception or use an appropriate skip mechanism.

**Returning `null` when the source is temporarily empty:** the Step ends early even though data may arrive later. Clearly define the wait condition and the source end condition.

**Returning an empty object in place of EOF:** Spring Batch treats that object as a valid item and passes it to the processor/writer. Use `null` exactly when the source is exhausted.

**Putting `null` into the source collection:** an iterator-based reader may return `null` in the middle of the data, causing the framework to stop early and miss the items after it. Validate the data before reading.

**Catching every exception and returning `null`:** I/O errors or parse errors are masked as EOF, so the Job may report completion even though the data has not been fully processed.

**Not releasing resources:** file handles, cursors, or connections may be held after the Step ends. A reader that manages resources must close them in `close()` or in an appropriate lifecycle mechanism.

**Not saving reader state when restart is needed:** after a failure, the reader may read again from the beginning or continue from the wrong position. Implement `ItemStream` and a checkpoint if recovery is required.

## 10. Summary of the read() Decision Flow

When implementing a reader, you can use the following general logic:

```text
read() is called
      |
      v
Does the source still have items?
   /       \
  Yes       No
  |            |
  v            v
Read item    return null
  |            |
  v            v
Is the item valid?  Step knows input is exhausted
  /      \
Yes       No
|          |
v          v
return     Throw an exception or apply
item       an appropriate error-handling policy
```

This rule helps keep the responsibility boundaries correct: the reader is responsible for providing items and signaling the end of input; the processor decides whether to transform or filter items; the writer writes the remaining items of the chunk. When the reader clearly distinguishes EOF from errors and from data that is temporarily not ready, Spring Batch can control the chunk loop, statistics, and restart reliably.

## Conclusion

`ItemReader.read()` returns one item per call and returns `null` when there is no more input in the current execution. Spring Batch uses this signal to end reading, process the last chunk if items remain, and complete the Step. A `null` from the reader differs from a `null` from the processor: the reader signals EOF, whereas the processor filters out the current item. Use exceptions for read errors, do not use `null` to mask errors or to represent a temporarily empty source, and implement a checkpoint through `ItemStream` when the Job needs to restart from a saved position.
