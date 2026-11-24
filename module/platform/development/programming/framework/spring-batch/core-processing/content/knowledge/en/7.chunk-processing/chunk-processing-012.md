# Ensuring the reader, processor, and writer share the same contract

In chunk-oriented processing, `ItemReader`, `ItemProcessor`, and `ItemWriter` form a data processing pipeline. The three components must agree on the data types and on the meaning of the data passing through each boundary. The reader supplies input items, the processor receives that exact type and produces output items, and the writer must accept the processor's output type.

The general type contract can be represented as follows:

```text
ItemReader<I>
     | reads one item of type I
     v
ItemProcessor<I, O>
     | converts I to O, or returns null to filter
     v
ItemWriter<O>
     | writes a Chunk of items of type O
     v
Destination data
```

What must be agreed on is not only the generic type. The components must also share the same understanding of data fields, units of measure, formats, null, identifying keys, ordering, errors, and transaction boundaries. If one component changes the meaning of the data and the next component does not know, the job may compile successfully but still write incorrect data.

## 1. The contract between the three components

The three main interfaces in Spring Batch each have their own role and data type:

| Component | Contract | Responsibility |
|---|---|---|
| `ItemReader<I>` | `read()` returns `I` or `null` when the data has run out | Read each input item |
| `ItemProcessor<I, O>` | Receives `I`, returns `O` or `null` to drop the item | Validate, filter, or transform data |
| `ItemWriter<O>` | Receives a `Chunk<? extends O>` | Write the group of output items |

In Spring Batch 5, the writer method receives a `Chunk`:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}

public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}

public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

The data-type connection points must match:

- The type `I` of `ItemProcessor<I, O>` must be compatible with the item type the reader returns.
- The type `O` of the processor must be compatible with the item type the writer receives.
- The type declared in the step's `chunk<I, O>(...)` must accurately describe the pipeline's input and output.

Generics help the compiler detect many connection errors at compile time. However, generics cannot verify that `amount` is in VND or USD, that a timestamp is UTC or local time, or that `customerId` is truly a unique business key. Those rules need to be described and checked in the data contract.

## 2. Declaring a chunk step with input and output types

In Spring Batch 5, the step builder declares the pipeline's two data types with `.<I, O>chunk(size, transactionManager)`.

For example, a job that imports customer data: the reader reads a CSV line into `CustomerRow`, the processor converts it into a normalized `Customer` object, and the writer writes `Customer` to the database.

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerRow> customerReader,
        ItemProcessor<CustomerRow, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomers", jobRepository)
        .<CustomerRow, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
}
```

In this declaration:

- `CustomerRow` is the type the reader returns and the processor receives.
- `Customer` is the type the processor returns and the writer receives.
- `100` is the commit interval: the step processes in chunks and commits per the configured transaction.

If you do not need to transform the data type, you can use the same type for both parameters, for example `.<Customer, Customer>chunk(100, transactionManager)`. When there is a processor that transforms the data, you should declare both types explicitly to express the input and output contract.

## 3. An example of a pipeline with a clear contract

First, define two different data models:

```java
public record CustomerRow(
        String customerId,
        String name,
        String email) {
}

public record Customer(
        String customerId,
        String displayName,
        String normalizedEmail) {
}
```

`CustomerRow` represents the structure read from the source. `Customer` represents data that has been validated and normalized for saving into the target system.

The processor receives `CustomerRow` and returns `Customer`:

```java
@Bean
ItemProcessor<CustomerRow, Customer> customerProcessor() {
    return row -> {
        if (row.email() == null || row.email().isBlank()) {
            return null; // Skip the item per the filter rule
        }

        if (row.customerId() == null || row.customerId().isBlank()) {
            throw new InvalidCustomerException("Missing customer ID");
        }

        return new Customer(
            row.customerId().trim(),
            row.name() == null ? "" : row.name().trim(),
            row.email().trim().toLowerCase(Locale.ROOT)
        );
    };
}
```

The writer receives a `Chunk` containing `Customer`s and writes to the database:

```java
@Bean
ItemWriter<Customer> customerWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> jdbcTemplate.batchUpdate(
        """
        INSERT INTO CUSTOMER (CUSTOMER_ID, DISPLAY_NAME, EMAIL)
        VALUES (?, ?, ?)
        """,
        chunk.getItems(),
        chunk.size(),
        (statement, customer) -> {
            statement.setString(1, customer.customerId());
            statement.setString(2, customer.displayName());
            statement.setString(3, customer.normalizedEmail());
        }
    );
}
```

The example writer uses `JdbcTemplate` and assumes the step's transaction manager manages the same JDBC datasource. Depending on the data policy, the `INSERT` statement can be replaced with an upsert or another operation, but the rule for handling duplicate keys needs to be clearly defined.

The three components match each other in sequence:

```text
CSV row / CustomerRow
        |
        v
customerProcessor(CustomerRow)
        |
        v
Customer
        |
        v
customerWriter(Chunk<Customer>)
        |
        v
CUSTOMER table
```

## 4. Reader: agreeing on the input data structure

The reader is responsible for reading one item at a time. Each `read()` call returns one item, or `null` when there are no more items.

The reader needs to ensure:

- Each item returned is exactly the type the processor declares it receives.
- The rules for column mapping, required fields, encoding, delimiter, and date/number formats must be clear.
- The record's identifying key needs to be preserved so the processor and writer can match or update the right record.
- The rule for handling error lines must be consistent: throw an exception, convert to an error object, or skip per the chosen policy.
- The read order needs to be determined if the order affects the business or the checkpoint.

For example, if the reader maps the column `customer_code` to `customerId`, all subsequent components must use the same meaning of this field. Do not let the reader use an internal code while the writer treats it as an external customer code.

### End-of-data and null conventions

`null` from `ItemReader.read()` is the signal that the data has run out. The reader should not return `null` to represent an invalid line of data, because Spring Batch will interpret that the source has ended and will not read the following lines.

For an invalid record, the reader should throw an appropriate exception or return an input data type that can represent the error so the processor handles it. This choice must be agreed with the skip policy and the audit requirements.

## 5. Processor: agreeing on the transformation rules

The processor is the transformation boundary from the input type `I` to the output type `O`. The processor can keep the same type, create a new type, validate, enrich data, or filter items.

Rules that need to be agreed:

1. **Mapping:** determine which source field maps to which target field.
2. **Validation:** determine which data is valid and which errors must throw an exception.
3. **Normalization:** agree on how to trim strings, normalize emails, encoding, timezones, and units.
4. **Filtering:** determine the condition for returning `null` to skip an item.
5. **Determinism:** with the same input and the same context, the result should be stable if the business requires it to be retryable/restartable.
6. **Side effects:** avoid writing to a database or calling external services in the processor if those operations can repeat on retry.

### Distinguishing filter from skip

A processor returning `null` means the item is deliberately filtered. This is not an error and does not produce a skip exception.

Conversely, if the processor throws an exception and that exception is configured in the skip policy, the item can be considered skipped. If the exception is not allowed to be skipped, the chunk can fail and the transaction is rolled back.

| Processor behavior | Meaning | Result at the writer |
|---|---|---|
| Returns an object of type `O` | Accept and transform the item | The writer receives the output item |
| Returns `null` | Filter the item | The writer does not receive that item |
| Throws an exception accepted by the skip policy | Skip the item per the skip policy | The writer does not receive the failing item |
| Throws an exception not skippable | Chunk processing fails | The chunk is not written successfully |

Do not use `null` to hide data errors. If you need to know why a record was dropped, record a metric, an audit, or a separate reject flow per the design.

## 6. Writer: agreeing on the output data type and meaning

The writer receives a `Chunk` of items that have passed through the processor. In Spring Batch 5, `ItemWriter<T>.write` receives `Chunk<? extends T>`. The writer needs to understand exactly the type and data rules that the processor produces.

For example, if the processor creates `Customer` with a normalized email, the writer must write the correct `normalizedEmail` into the target email column. If the writer instead expects to receive `CustomerRow` or assumes the email is not normalized, the contract between the two components has been broken.

The writer needs to clearly specify:

- Whether to insert, update, or upsert when the key already exists.
- Whether it guarantees an item is written only once.
- Which NOT NULL, unique key, and foreign key constraints must be satisfied.
- Whether the order of items in the chunk is preserved.
- Which exceptions cause the chunk to roll back and which can be skipped/retried.
- Which operations participate in the same transaction as the JobRepository and which lie outside that transaction.

The writer should not assume the chunk always has exactly the number of items equal to the commit interval. If the processor filters some items, the number of items the writer receives can be fewer than the number the reader read in the chunk.

## 7. Chunk size and the pipeline's contract

Chunk-oriented processing reads, processes, and writes items in groups. When the commit interval is reached, Spring Batch calls the writer for the current chunk in the step's transaction. After a successful write, the transaction is committed; if an error occurs, the transaction can roll back per the configuration.

```text
Read item 1 -> Process item 1
Read item 2 -> Process item 2
Read item 3 -> Process item 3 (filter -> null)
...
Read item N -> Process item N
             |
             v
        ItemWriter
             |
             v
        Transaction commit
```

Because the processor can filter items, the output chunk can be smaller than the input chunk. The writer receives only the items the processor accepted.

Chunk size also affects resources and error behavior. A large chunk reduces the number of commits but holds many items in memory and can lengthen the transaction. A small chunk usually commits more often but increases overhead. The reader, processor, and writer must be designed to work correctly with the chosen chunk size.

## 8. Transactions, retry, and idempotency

When the writer writes to a database managed by the step's transaction manager, an error in the chunk can cause the chunk's changes to roll back. On retry, the reader or processor may be called again depending on the fault-tolerance mechanism and the saved state.

Therefore:

- The processor should avoid side effects that cannot be rolled back, such as sending emails, calling payments, or writing to a system that does not participate in the transaction.
- The writer should use the transaction resource that matches the step's transaction manager.
- If writing to an external system, you need an idempotency key or an outbox/reconciliation mechanism to handle being called again.
- The unique key and upsert rules must be consistent with how restart/retry works.
- Do not assume each item is called exactly once by the processor or writer in every error scenario.

For example, if the writer calls a payment API and then the chunk rolls back due to a database error, a retry can call the payment API again. Use an idempotency key based on the business transaction identifier so the service recognizes a repeated request.

## 9. Skip and retry must match the data contract

Fault tolerance lets you configure which exceptions are retried or skipped. However, the policy must reflect the meaning of the error:

- A transient error such as a timeout may suit a bounded retry.
- Invalid data may suit skip and recording the reason.
- A contract violation such as a wrong schema or widespread wrong data types should usually stop the job to avoid mass incorrect writes.
- A writer error due to a constraint may indicate the processor has not normalized or validated the data enough.

An example skip configuration in Spring Batch 5:

```java
return new StepBuilder("importCustomers", jobRepository)
    .<CustomerRow, Customer>chunk(100, transactionManager)
    .reader(customerReader)
    .processor(customerProcessor)
    .writer(customerWriter)
    .faultTolerant()
    .skip(InvalidCustomerException.class)
    .skipLimit(50)
    .build();
```

The configuration snippet only illustrates a skip policy for the chosen exception type. You need to ensure `InvalidCustomerException` truly represents a skippable error, and that skipped data is recorded sufficiently to handle later. Do not skip every `Exception` because it can hide infrastructure errors or contract errors.

## 10. The contract when chaining multiple processors

When the pipeline has multiple transformation stages, the output type of the previous processor must be compatible with the input type of the next processor.

```text
CustomerRow
    |
    v
ItemProcessor<CustomerRow, ValidatedCustomer>
    |
    v
ItemProcessor<ValidatedCustomer, EnrichedCustomer>
    |
    v
ItemProcessor<EnrichedCustomer, CustomerEntity>
    |
    v
ItemWriter<CustomerEntity>
```

You can use `CompositeItemProcessor` to chain processors. You need to declare the delegates in order and ensure the generic types between each consecutive pair match. If a delegate returns `null`, the item is filtered and the subsequent delegates do not process that item.

For a writer with multiple destinations, you can use `CompositeItemWriter` or a custom writer. The delegates must receive the same output type `O`. If multiple writers write to multiple different resources, you need to clearly understand whether the transaction manager can manage all of them; calling multiple writers does not by itself guarantee an atomic transaction across multiple databases.

## 11. State and restart contract

A reader or writer with state needs to implement `ItemStream` or use a ready-made component that supports saving state. Spring Batch calls lifecycle methods such as `open`, `update`, and `close` to restore or save the `ExecutionContext`.

On restart, the reader can continue from the committed checkpoint position. Therefore, the data contract needs to be stable across runs: the source order, the record key, the data format, and how the checkpoint is interpreted should not change unexpectedly.

If a new version changes the item structure or the meaning of a field but still reuses an old checkpoint, the processor/writer may receive data that no longer matches the original assumptions. When changing the source schema or the checkpoint structure, have a compatibility strategy, a migration, or finish the old JobInstances before deploying.

## 12. Thread safety and shared resources

When a step runs multi-threaded or uses partitioning, the reader, processor, and writer can be called concurrently depending on the configuration. Do not assume every implementation is thread-safe by default.

- A reader that holds a pointer or mutable state needs to be protected or use a separate instance for each partition.
- The processor should avoid mutable shared state; if you need a cache or counter, there must be appropriate synchronization.
- The writer needs to be checked for concurrent write capability, unique keys, and commit order.
- Delegates shared across partitions need to be evaluated for thread safety and lifecycle.

For a non-thread-safe reader, you may need partitioning with separate state or an appropriate synchronizing decorator. Synchronizing a reader can reduce parallelism, so choose a model based on the nature of the data source and the throughput requirements.

## 13. Common contract errors

| Error | Consequence | How to handle |
|---|---|---|
| The reader returns `A` but the processor declares it receives `B` | Does not compile or requires an unsafe cast | Declare the generic `ItemProcessor<A, O>` to match the reader |
| The processor returns `O` but the writer receives a different type | Does not compile, or mapping is wrong at runtime if using a raw type | Use `ItemWriter<O>` and avoid raw types |
| Using `null` from the reader to represent an error line | The reader is interpreted as having run out of data | Throw an exception or represent the error with a clear data type |
| Using `null` from the processor to represent an error | The item is silently filtered | Throw an exception and configure skip/retry if appropriate |
| The writer assumes the chunk is always full | Mishandles when items are filtered or at the end of the source | Iterate over the actual items in the chunk correctly |
| The processor changes timezone or units without specification | Output data is wrong but still type-valid | Clearly define the format, timezone, and units in the contract |
| The processor or writer creates non-idempotent side effects | Retry/restart can create duplicate operations | Use transactions, idempotency keys, or an outbox |
| Multiple components share non-thread-safe state | Race conditions and wrong data | Use separate state, synchronization, or appropriate partitioning |

## 14. How to verify the contract between components

You can verify the pipeline at multiple levels:

1. **Compile-time:** use concrete generics for the reader, processor, writer, and step; avoid raw types or unnecessary casts.
2. **Reader unit tests:** confirm mapping, encoding, order, end-of-source data, and how errors are reported.
3. **Processor unit tests:** confirm output mapping, normalization, validation, filtering with `null`, and exceptions.
4. **Writer unit tests:** confirm the writer receives the right type, writes all items, handles duplicate keys, and reacts when persistence fails.
5. **Step integration tests:** run with an appropriate JobRepository and transaction manager, and confirm chunk commit/rollback, skip, retry, and restart.
6. **Data contract tests:** check the schema, column types, nullability, units of measure, timezone, and business keys between source and destination.

A useful test suite should include valid items, filtered items, validation-failing items, a last chunk that is not full size, a write error mid-chunk, and a restart-from-checkpoint scenario.

## Conclusion

The reader, processor, and writer need to be connected by a clear contract: `ItemReader<I>` supplies the input type, `ItemProcessor<I, O>` transforms to the output type, and `ItemWriter<O>` writes the output items in chunks. The generic types must match, while the rules on schema, null, validation, identity, transactions, retry, and restart must be agreed on in the business sense.

When the contract is clearly defined, the compiler can catch data-type errors early, tests can confirm each boundary, and the job can handle errors or restart without distorting the meaning of the data.
