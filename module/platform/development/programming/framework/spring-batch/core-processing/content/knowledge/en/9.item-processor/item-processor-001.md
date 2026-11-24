# ItemProcessor transforms or validates items

In Spring Batch, `ItemProcessor` is the component that processes an item after `ItemReader` reads it and before `ItemWriter` writes the result. A processor is typically used to validate data, normalize values, apply business rules, or convert an input data type into a type that fits the target system.

`ItemProcessor` separates the logic that processes each record from the logic that reads and writes data. The reader is responsible for fetching items, the processor decides how an item should be transformed or discarded, and the writer receives the valid results and writes them in chunks. As a result, the same processor can be used with different data sources or writers as long as the data contract is compatible.

## 1. Where does ItemProcessor sit in chunk processing?

In a chunk-oriented Step, Spring Batch performs a read, process, and write cycle on each group of items:

```text
Data source
     |
     v
   ItemReader<I>
     |
     v
ItemProcessor<I, O>
     |
     v
   ItemWriter<O>
     |
     v
  Commit chunk
```

Where:

- `I` is the item type that the reader returns.
- `O` is the item type that the processor returns and the writer accepts.
- The processor is called for each item that is read, in the Step's processing order.
- The processor's result can be a new item, a modified item, or `null` to filter the item out of the flow.

For example, the reader reads `CustomerInput` from a CSV file, the processor validates the email and normalizes the name, then converts it into a `Customer` so the writer can save it to the database:

```java
ItemReader<CustomerInput> reader;
ItemProcessor<CustomerInput, Customer> processor;
ItemWriter<Customer> writer;
```

The input and output types do not need to be the same. This is useful when the source data has a different structure from the model the application wants to store.

## 2. The ItemProcessor contract

The basic interface looks like this:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

The `process` method receives an item and returns the processing result. The method can throw an exception if the item cannot be processed or if an error occurs that the Step must handle according to the configured policy.

There are three important outcomes:

1. Return a different object: the item has been transformed into a new result.
2. Return the input object itself: the item is kept, and may have been updated if the model allows modification.
3. Return `null`: the item is filtered out and is not passed to the writer.

If the processor throws an exception, the chunk step handles the error according to the transaction, skip, and retry configuration. If there is no suitable error-handling policy, the error can cause the Step to fail.

## 3. Using ItemProcessor to validate data

A common task for a processor is to validate an item before it is written. For example, an order must have an order ID, a customer ID, and a positive amount.

```java
public class OrderValidationProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        if (item.customerId() == null || item.customerId().isBlank()) {
            throw new InvalidOrderException("Customer ID is required");
        }

        if (item.amount() == null || item.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return item;
    }
}
```

The processor above returns the item if the data is valid and throws `InvalidOrderException` if a rule is violated. The Step can configure this exception as a skippable error if the business allows skipping malformed records.

Validation in the processor suits rules that depend on each individual item, for example required fields, value ranges, or relationships between fields of the same record. Overall checks such as whether the Job parameters are valid usually belong to `JobParametersValidator`; checking shared resource conditions before running can belong to a preflight Step.

### Distinguishing validation errors from filtering items

Not every item that does not need to be written is an erroneous item. If an item is valid but falls outside the scope to be processed, the processor can return `null`. If an item violates a data rule and needs to be recorded as an error, the processor can throw an exception.

For example, a cancelled order can be filtered out according to a reporting requirement; an order missing its identifier can be bad data:

```java
@Override
public Order process(OrderInput item) {
    if (item.cancelled()) {
        return null;
    }

    if (item.orderId() == null || item.orderId().isBlank()) {
        throw new InvalidOrderException("Missing order ID");
    }

    return toOrder(item);
}
```

`null` means the processor deliberately removes the item from the pipeline. An exception means that processing the item encountered an error; depending on the configuration, the error can be skipped, retried, or cause the Step to fail. Do not use `null` to hide bad data if the application needs to report or investigate those records.

## 4. Using ItemProcessor to transform data

A processor is also commonly used to convert a source data type into the target model. For example, a CSV file provides the amount as a string and the date as text, while the entity needs `BigDecimal` and `LocalDate`.

```java
public class InvoiceProcessor
        implements ItemProcessor<InvoiceInput, Invoice> {

    @Override
    public Invoice process(InvoiceInput input) {
        BigDecimal amount = new BigDecimal(input.amountText());
        LocalDate invoiceDate = LocalDate.parse(input.dateText());

        return new Invoice(
                input.invoiceNumber().trim(),
                input.customerCode().trim(),
                amount,
                invoiceDate);
    }
}
```

The example illustrates format conversion. In a real application, you need to handle parse errors separately, define the locale/format of the source data, and determine which exception types are considered skippable data errors.

Common kinds of transformation:

- Normalizing whitespace, upper/lower case, or identifiers.
- Converting strings to dates, numbers, currencies, or enums.
- Mapping an input DTO to an entity or target model.
- Computing derived fields such as total amount, tax, or fees.
- Combining values within the same item to create a new data structure.
- Attaching business metadata needed for the output record.

A processor should focus on processing a single item. Reading data from the source and writing results to the destination should still belong to the reader and writer so the pipeline is easy to follow.

## 5. Combining validation and transformation in one processor

A single processor can both validate data and normalize and convert it into the target type. For example:

```java
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    @Override
    public Customer process(CustomerInput input) {
        String email = input.email() == null
                ? ""
                : input.email().trim().toLowerCase(Locale.ROOT);

        if (email.isBlank() || !email.contains("@")) {
            throw new InvalidCustomerException("Invalid email address");
        }

        String name = input.name() == null ? "" : input.name().trim();
        if (name.isBlank()) {
            throw new InvalidCustomerException("Customer name is required");
        }

        return new Customer(input.customerId(), name, email);
    }
}
```

This processor turns `CustomerInput` into `Customer` and does not pass invalid items to the writer. `Locale.ROOT` normalizes lowercase using a stable locale, preventing results from changing depending on the locale of the machine running the Job.

For complex logic, you can split validation and transformation into separate classes and then combine them using a composite processor. This approach makes each rule easier to test and reuse.

## 6. Registering ItemProcessor in a Step

In Spring Batch 5, you can declare a chunk Step with `StepBuilder` and pass in the reader, processor, and writer:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(200, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

The chunk size is 200 in this example. Spring Batch reads and processes items, then passes the unfiltered results to the writer when the chunk is completed according to the Step's cycle.

If the processor does not need any transformation, you can use a processor that returns the item as is, or omit the processor when there is no processing logic. There is no need to create an empty processor just to fill a slot in the configuration.

## 7. Processors returning null and the filtering mechanism

When `process` returns `null`, Spring Batch considers that item filtered. The item is not passed to the writer. This is the official way to remove an item from the chunk flow.

For example, exporting only confirmed invoices:

```java
public class ConfirmedInvoiceProcessor
        implements ItemProcessor<InvoiceInput, Invoice> {

    @Override
    public Invoice process(InvoiceInput item) {
        if (!item.confirmed()) {
            return null;
        }
        return toInvoice(item);
    }
}
```

Filtered items are reflected in the `filterCount` of `StepExecution`. When monitoring results, you need to distinguish between:

- `readCount`: the number of items read by the reader.
- `filterCount`: the number of items the processor filtered by returning `null`.
- `writeCount`: the number of items the writer has written.
- The skip counts: the number of items skipped due to exceptions configured as skippable in the reader, processor, or writer.

Do not confuse filtering with skipping. Filtering is a deliberate business outcome of the processor; skipping is a fault-tolerance policy that handles an exception.

## 8. Exceptions in ItemProcessor and skip/retry

`process` can throw an exception. In a chunk step, exceptions are handled according to the Step's fault-tolerance configuration and rollback rules.

Example configuration that skips one kind of data error:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(200, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(InvalidCustomerException.class)
        .skipLimit(50)
        .build();
```

In this example, up to 50 errors of type `InvalidCustomerException` can be skipped according to the policy. When the limit is exceeded or an error that is not skippable occurs, the Step can fail.

Retry is better suited to transient errors, for example a recoverable service error or a database access error. Do not retry a data error that cannot change by itself, because the same item will keep failing.

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
```

Retry can cause the processor to be called again for the same item. Therefore, a processor should avoid side effects such as sending email, writing to a database outside the transaction, or calling an API without idempotency. If side effects are needed, design a deduplication mechanism or move that task to a separate step.

## 9. Splitting multiple processing steps with CompositeItemProcessor

When the logic consists of several independent transformations, you can use `CompositeItemProcessor` to chain multiple processors into a pipeline. The output of the previous processor becomes the input of the next processor.

For example:

```java
@Bean
CompositeItemProcessor<CustomerInput, Customer> customerCompositeProcessor(
        ItemProcessor<CustomerInput, CustomerInput> validationProcessor,
        ItemProcessor<CustomerInput, NormalizedCustomer> normalizationProcessor,
        ItemProcessor<NormalizedCustomer, Customer> mappingProcessor) {

    return new CompositeItemProcessorBuilder<CustomerInput, Customer>()
            .delegates(
                    validationProcessor,
                    normalizationProcessor,
                    mappingProcessor)
            .build();
}
```

The example describes three stages: data validation, normalization, and mapping to an entity. The generic types must chain together exactly: the output type of one delegate must be compatible with the input type of the next delegate.

A composite processor is useful when each step has its own responsibility and can be tested independently or reused. If there are only a few lines of simple logic, a single processor may be easier to read.

If a delegate returns `null`, the item has been filtered out of the pipeline; the following delegates do not process that item. If a delegate throws an exception, the error is propagated to the chunk Step and handled according to the configured skip/retry policy.

## 10. ClassifierCompositeItemProcessor

When items belong to multiple types and a different processor must be chosen for each item, you can use `ClassifierCompositeItemProcessor`. The classifier decides the appropriate delegate based on the item's content.

For example, a system imports two kinds of transactions:

```java
@Bean
ClassifierCompositeItemProcessor<TransactionInput, Transaction> transactionProcessor(
        ItemProcessor<TransactionInput, Transaction> transferProcessor,
        ItemProcessor<TransactionInput, Transaction> paymentProcessor) {

    ClassifierCompositeItemProcessor<TransactionInput, Transaction> processor =
            new ClassifierCompositeItemProcessor<>();

    processor.setClassifier(item -> {
        if (item.type() == TransactionType.TRANSFER) {
            return transferProcessor;
        }
        if (item.type() == TransactionType.PAYMENT) {
            return paymentProcessor;
        }
        throw new IllegalArgumentException("Unsupported transaction type");
    });

    return processor;
}
```

This is a way to organize things when groups of items have different processing rules but all produce the same output type, `Transaction`. If the branches return different data types, you need to design a common output type or convert the results before passing them to the writer.

## 11. ItemProcessor and transactions

The processor runs within the processing cycle of the chunk Step, but you should not assume that every action in `process` will be rolled back. A transaction usually protects the resources that participate in the configured transaction manager, such as the corresponding database transaction.

If a processor only transforms objects in memory and returns the result, it does not need to open a transaction itself. If a processor calls a database or an external service, you need to consider the transaction boundary and the possibility of repetition.

Principles to apply:

- Keep the processor as free of side effects as possible.
- Do not send email or call non-idempotent APIs in `process`.
- Avoid writing business data to another database outside the transaction that the Step manages unless there is a coordination mechanism.
- If you need to look up reference data, consider a cache or bulk lookup to avoid a separate query for each item.
- Ensure that retry does not duplicate side effects.

A processor can call a service to perform calculations, but if the service writes data, you need to design rollback and retry explicitly. It is usually better to have the processor focus on producing the result, while the writer is responsible for writing the result within the chunk's transaction.

## 12. ItemProcessor performance

The processor is called for each item, so a small per-item cost can become large when processing millions of records.

For example, if each item runs one SQL statement to fetch customer information, the Job can generate millions of small queries. You can improve this by:

- Loading reference data into a cache if the data has a suitable size and lifetime.
- Using a reader with a join query or projection to fetch the needed data up front.
- Designing the enrichment step to work in batches if the service supports bulk requests.
- Avoiding unnecessary repeated parsing/formatting.
- Using immutable objects or reusing suitable structures to control memory allocation.
- Measuring per-item processing time, throughput, and error rate before optimizing.

Do not put an unbounded cache in the processor when the number of keys can grow with the entire dataset. You need to consider memory, the eviction policy, and the consistency of the reference data.

## 13. Testing ItemProcessor

Because a processor usually handles a single item independently, it can be tested with a unit test without launching the entire Job.

Example of testing a transformation:

```java
class CustomerProcessorTest {

    private final CustomerProcessor processor = new CustomerProcessor();

    @Test
    void normalizesEmailAndName() throws Exception {
        CustomerInput input = new CustomerInput(
                "C-100", "  Nguyen An  ", " AN@EXAMPLE.COM ");

        Customer result = processor.process(input);

        assertEquals("Nguyen An", result.name());
        assertEquals("an@example.com", result.email());
    }
}
```

You should have these groups of cases:

- A valid item is transformed correctly.
- Boundary values such as an empty string, null, a negative number, or an invalid date.
- A filtered item must return `null`.
- A bad item must throw the correct exception.
- Normalization rules must be stable with respect to locale and data format.
- A composite processor chains the data types and the delegate order correctly.

Unit tests verify the per-item rules. An integration test at the Step level can additionally verify how exceptions interact with skip/retry, the filter count, the writer, and transactions.

## 14. Common mistakes when implementing ItemProcessor

### Returning null because you don't know how to handle an error

`null` means deliberately filtering an item. If an item is invalid and needs to be counted, investigated, or reprocessed, throw an appropriate exception so that skip/retry applies or the Step fails.

### Writing data in the processor

If the processor writes data itself while the writer also writes, responsibility is scattered and can create side effects that are hard to roll back or that repeat on retry. Prefer producing the result in the processor and letting the writer perform the write.

### Calling an external system for each item without controlling the load

One API call per item can create heavy load, timeouts, and rate limiting. Consider a bulk API, rate limiting, timeouts, and retry with backoff; make sure requests can be safely repeated.

### Using exceptions that are too generic

Throwing `Exception` or `RuntimeException` for every case makes it hard to distinguish data errors from system errors. Create clear business exceptions so you can configure skip/retry precisely.

### Sharing mutable state across items

If a processor holds a shared mutable object and modifies it for each item, data can leak between calls or cause errors in parallel processing. Create a separate result for each item and control thread safety if the processor is used in a multi-threaded environment.

### Assuming the processor runs exactly once per item

Retry, rollback, and restart can cause the processing logic to be called again. Do not put non-idempotent side effects in the processor, and do not rely on the number of calls to generate business IDs.

## 15. ItemProcessor design workflow

When building a processor for a Job, you can follow this sequence:

1. Determine the item type the reader returns and the data type the writer needs to receive.
2. List the validation rules that apply to each item.
3. Determine the normalization, calculation, and mapping to perform.
4. Decide which cases are filtered with `null` and which must throw an exception.
5. Classify exceptions so that skip/retry can be configured appropriately in the Step.
6. Keep the processor free of side effects and design it to be safe when called again.
7. Split the stages into delegates if the logic is complex or needs to be reused.
8. Test the valid, boundary, filtered, and error cases.
9. Measure performance with representative data to detect per-item queries or API calls that are too expensive.

| Need | How to handle it in the processor |
|---|---|
| Check required fields | Throw a business exception on violation. |
| Normalize a name or email | Return the normalized item or a new object. |
| Convert a DTO to an entity | Return an output type different from the input type. |
| Discard a valid item that is out of scope | Return `null`. |
| Transient error from a reference service | Throw an appropriate exception and configure retry in the Step if it is safe. |
| Multiple independent transformation rules | Combine delegates using a composite processor. |

## Conclusion

`ItemProcessor<I, O>` processes each item between the reader and the writer. It can validate data, normalize, calculate, and convert the input type into the output type. Returning `null` filters the item out before the writer; throwing an exception hands the error to the skip/retry policy or causes the Step to fail. When designing a processor, keep the logic focused on each individual item, limit side effects, ensure safety under retry/restart, and split complex processing steps into components that can be tested independently.
