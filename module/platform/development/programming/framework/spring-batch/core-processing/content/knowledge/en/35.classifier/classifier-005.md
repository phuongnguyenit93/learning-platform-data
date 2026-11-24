# ClassifierCompositeItemWriter

In Spring Batch, `ClassifierCompositeItemWriter<T>` routes each input item to an `ItemWriter` selected by a `Classifier`. For each item, the classifier inspects the data and returns the matching writer; that writer is responsible for writing the item. This is useful when a chunk contains multiple result types or business categories that must be written to different destinations.

For example, a step reads payment transactions but needs to write `CARD` transactions to a card writer and `BANK_TRANSFER` transactions to a bank-transfer writer. The reader and processor still produce the same `Payment` type; the classifier chooses the writer based on the payment method.

`ClassifierCompositeItemWriter` performs routing, not broadcasting. Each item is forwarded to the selected writer rather than sending the same item to all delegates. If the goal is writing every item to multiple writers, see `CompositeItemWriter`. If items need to be transformed by type before writing, see a classifying processor such as `ClassifierCompositeItemProcessor`.

## 1. Role in a Chunk-Oriented Step

In a chunk step, the reader fetches items, the processor can normalize or transform them, and then the writer writes the results. `ClassifierCompositeItemWriter` sits at the writer position and accepts the processor's final output type.

~~~mermaid
flowchart LR
    A[ItemReader] --> B[ItemProcessor]
    B --> C[Chunk of items]
    C --> D[ClassifierCompositeItemWriter]
    D --> E{Classifier}
    E -->|Route A| F[Writer A]
    E -->|Route B| G[Writer B]
    E -->|Route C| H[Writer C]
~~~

Example of a chunk with items in sequence:

| Item | Classification property | Selected writer |
|---|---|---|
| Payment 1 | CARD | cardPaymentWriter |
| Payment 2 | BANK_TRANSFER | bankTransferWriter |
| Payment 3 | CARD | cardPaymentWriter |
| Payment 4 | CASH | cashPaymentWriter |

A chunk can contain items going to multiple different writers. The classifier is applied per item, so classification does not require the entire chunk to have only one data type.

## 2. Key Components

There are three components to understand:

| Component | Responsibility |
|---|---|
| Classifier<T, C> | Receives an item of type T and selects a target object of type C |
| ItemWriter<T> | Writes a chunk of items of compatible type T |
| ClassifierCompositeItemWriter<T> | Invokes the classifier for each item and forwards the item to the selected writer |

In terms of generics, the composite writer's classifier returns a writer that can accept item type `T`, typically declared as `ItemWriter<? super T>`. This means delegate writers must accept the item type itself or a supertype of it.

For example, if the composite has type `ClassifierCompositeItemWriter<Payment>`, delegates like `ItemWriter<Payment>` or `ItemWriter<Object>` can fit. An `ItemWriter<CardPayment>` cannot be wired directly if `CardPayment` is a subtype of `Payment`, because that writer only accepts `CardPayment` and not every `Payment`. To route different subtypes to writers with narrower generics, use an adapter with a common input type and safe type checking/casting.

## 3. How It Works When Writing

`ClassifierCompositeItemWriter` receives a `Chunk<? extends T>`. For each item in the chunk, it invokes the classifier to obtain a writer and then passes the item to that writer. In the standard implementation, delegates are called with a chunk containing the item under consideration; thus a writer may be invoked multiple times within a single composite write call.

Processing flow:

1. The step completes read/process for the current chunk.
2. The step calls `write(chunk)` on the composite writer.
3. The composite iterates through each item in the chunk.
4. The classifier selects a delegate writer based on the item.
5. The composite calls the selected writer to write that item.
6. After all write calls finish, the step proceeds to commit the transaction as configured.

This differs from a writer that groups all items by destination first and calls each delegate once with its corresponding list. Therefore, if a delegate performs bulk inserts or batch API calls, keep in mind that per-item routing can reduce batching efficiency. You may need a custom routing writer to group items by destination before invoking each writer.

## 4. Basic Configuration with a Classifier

A `Classifier` can be written as a lambda. Example routing payments by method:

~~~java
@Bean
ClassifierCompositeItemWriter<Payment> paymentWriter(
        ItemWriter<Payment> cardPaymentWriter,
        ItemWriter<Payment> bankTransferWriter,
        ItemWriter<Payment> cashPaymentWriter) {

    Classifier<Payment, ItemWriter<? super Payment>> classifier =
            payment -> switch (payment.method()) {
                case CARD -> cardPaymentWriter;
                case BANK_TRANSFER -> bankTransferWriter;
                case CASH -> cashPaymentWriter;
            };

    ClassifierCompositeItemWriter<Payment> writer =
            new ClassifierCompositeItemWriter<>();
    writer.setClassifier(classifier);
    return writer;
}
~~~

In this example, all three delegates accept `Payment`. The classifier reads `payment.method()` and returns the right writer. Switching on an enum helps the compiler flag unhandled cases when the enum grows, depending on the Java version and switch form.

If the classifier cannot find a writer, it should not return `null`. Define an explicit default route or throw a meaningful exception so the step fails per policy. A `null` writer will cause writing to fail at dispatch time and make the root cause harder to understand.

## 5. Configuring by Business Conditions

A classifier does not have to rely solely on an enum. It can use any stable property of the item:

- Transaction status.
- Customer type.
- Sales channel.
- Tenant or data region.
- Priority level.
- Record type.

Example routing active orders and archived orders:

~~~java
Classifier<Order, ItemWriter<? super Order>> orderClassifier =
        order -> {
            if (order.status() == OrderStatus.ARCHIVED) {
                return archivedOrderWriter;
            }
            return activeOrderWriter;
        };
~~~

If the data has many states, use a switch or explicit map instead of many nested `if` branches. If a state is unsupported, decide whether to reject, write to an error writer, or fail the job. Do not automatically route unknown data to a default writer if doing so could corrupt reports or lose control.

## 6. Declaring Delegate Writers

Delegates can be built-in Spring Batch writers or custom writers. For example, the same `Payment` type written to two different tables:

~~~java
@Bean
JdbcBatchItemWriter<Payment> cardPaymentWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Payment>()
            .dataSource(dataSource)
            .sql("""
                    insert into card_payment
                        (payment_id, amount, card_reference)
                    values
                        (:paymentId, :amount, :reference)
                    """)
            .beanMapped()
            .build();
}

@Bean
JdbcBatchItemWriter<Payment> bankTransferWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Payment>()
            .dataSource(dataSource)
            .sql("""
                    insert into bank_transfer_payment
                        (payment_id, amount, bank_reference)
                    values
                        (:paymentId, :amount, :reference)
                    """)
            .beanMapped()
            .build();
}
~~~

This example assumes the `Payment` model has the properties needed by both SQL statements. In real applications, writers can use a common model, a custom `ItemPreparedStatementSetter`, or an `ItemSqlParameterSourceProvider` to map fields accurately.

An item is written to the writer selected by the classifier. If you need to write simultaneously to both tables to create an audit copy, classifier composite does not fulfill broadcasting requirements; use `CompositeItemWriter` or a dedicated coordinating writer.

## 7. Attaching ClassifierCompositeItemWriter to a Step

At the step level, the composite writer is declared as an ordinary `ItemWriter<T>`:

~~~java
@Bean
Step routePaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> paymentReader,
        ItemProcessor<PaymentInput, Payment> paymentProcessor,
        ItemWriter<Payment> paymentWriter) {

    return new StepBuilder("routePaymentsStep", jobRepository)
            .<PaymentInput, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .processor(paymentProcessor)
            .writer(paymentWriter)
            .build();
}
~~~

The reader supplies `PaymentInput`, the processor returns `Payment`, and the classifier writer routes each `Payment` to the right destination. The step does not need to know the number of delegates or the specific routing criteria.

This allows changing route mappings or adding new writers without modifying the reader and processor, as long as the pipeline's output type remains `Payment`.

## 8. Distinguishing Routing from Broadcasting

Two composite writer types are frequently confused:

| Writer | Behavior |
|---|---|
| ClassifierCompositeItemWriter<T> | Selects one writer for each item |
| CompositeItemWriter<T> | Sends the chunk to configured delegate writers in order |

For example, if a `CARD` payment must only be written to the card payment table, use a classifier writer. If every payment must be written to the main payment table and also have an audit record written, use a composite writer or an intentional coordinating writer.

Do not configure multiple delegates in a classifier expecting the item to be written to all of them. The classifier returns a single target writer for the item being classified.

## 9. Routing by Subtype and Generic Types

A common case is a reader returning multiple subtypes implementing a shared interface:

~~~java
public interface ImportRecord {
    String recordId();
}

public record CustomerRecord(
        String recordId,
        String customerName) implements ImportRecord {
}

public record OrderRecord(
        String recordId,
        String customerId,
        BigDecimal amount) implements ImportRecord {
}
~~~

The composite writer has the overall type `ClassifierCompositeItemWriter<ImportRecord>`. However, `ItemWriter<CustomerRecord>` cannot be used directly as `ItemWriter<? super ImportRecord>` because it cannot accept `OrderRecord`.

You can use an adapter accepting the parent type and checking the subtype before forwarding to the specialized writer:

~~~java
public class CustomerRecordWriter implements ItemWriter<ImportRecord> {

    private final ItemWriter<CustomerRecord> delegate;

    public CustomerRecordWriter(ItemWriter<CustomerRecord> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends ImportRecord> items)
            throws Exception {
        for (ImportRecord item : items) {
            if (!(item instanceof CustomerRecord customer)) {
                throw new IllegalArgumentException(
                        "Expected CustomerRecord but got "
                                + item.getClass().getName());
            }
            delegate.write(Chunk.of(customer));
        }
    }
}
~~~

A similar adapter can be written for `OrderRecord`. The classifier selects the adapter by subtype. This keeps type checking at a clear boundary instead of using raw types or unchecked casts inside the classifier.

If the writers can accept a shared base class/interface and handle common properties themselves, using `ItemWriter<ImportRecord>` directly can be simpler.

## 10. Using a Class-Based Classifier

When routing depends on subtype, you can use a dedicated classifier or an `instanceof` lambda:

~~~java
Classifier<ImportRecord, ItemWriter<? super ImportRecord>> classifier =
        record -> {
            if (record instanceof CustomerRecord) {
                return customerRecordWriter;
            }
            if (record instanceof OrderRecord) {
                return orderRecordWriter;
            }
            throw new IllegalArgumentException(
                    "Unsupported record type: "
                            + record.getClass().getName());
        };
~~~

With many subtypes, a map from class to writer can be easier to manage. If using a classifier by superclass/interface, define a clear priority order when a class matches multiple rules. Do not rely on unguaranteed map iteration order to decide routes.

## 11. Registering Delegate ItemStream Lifecycle

An important point when using a classifier writer is the lifecycle of delegates. `ClassifierCompositeItemWriter` dispatches write calls, but it does not automatically open, update, and close all delegate writers as an aggregate `ItemStream`.

If a delegate writer implements `ItemStream` or `ItemStreamWriter`, register each delegate with the step so Spring Batch invokes its lifecycle:

~~~java
@Bean
Step exportPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> paymentReader,
        ItemWriter<Payment> classifierWriter,
        FlatFileItemWriter<Payment> cardFileWriter,
        FlatFileItemWriter<Payment> bankFileWriter) {

    return new StepBuilder("exportPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .writer(classifierWriter)
            .stream(cardFileWriter)
            .stream(bankFileWriter)
            .build();
}
~~~

`stream(...)` registers delegate streams with the step so they are opened, have state updated, and are closed according to the step lifecycle. Without registration, file-based writers may not be initialized/closed properly or fail to save checkpoints as expected.

You do not need to register delegates separately if they do not implement `ItemStream`. However, inspect the actual writer type, especially with custom writers or wrappers. If an adapter hides the delegate's `ItemStream` interface, register the underlying stream or design the adapter to implement and forward the lifecycle as well.

## 12. Restart and State per Writer

Some writers maintain state such as file position, number of written records, or metadata required to resume after a restart. When a classifier has multiple delegates, each writer can have its own state.

To restart properly:

- Register every `ItemStream` delegate with the step.
- Assign a stable and unique `name` to each writer that needs to save state.
- Keep resources/output paths and routing rules stable across restarts.
- Do not change classification criteria so subsequent items go to a different destination than the initial run if prior state depends on the route.
- Define how outputs are recovered if one writer already wrote partial data before the step failed.

For example, if writer A writes `card.csv` and writer B writes `bank.csv`, both files must have independent lifecycles and checkpoints. If you restart the job with new file paths or changed routes, results may become inconsistent with what was previously written.

## 13. Transactions and Multiple Writers

Delegates are invoked during the write phase of the same chunk. If writers write to the same database transaction and share the same transaction manager/resource, an error in one delegate can roll back the chunk transaction as configured.

However, do not assume every output type rolls back atomically:

- Two `JdbcBatchItemWriter` instances using the same transaction-managed `DataSource` can usually participate in the same transaction.
- A writer writing to a different database or transaction manager may not belong to that transaction.
- Calling REST APIs, sending messages directly, or writing files does not automatically share atomicity with a database transaction.
- One delegate may have already produced side effects before a later delegate throws an exception.

If a chunk fails after one delegate has already written, a retry may call that writer again. Idempotency keys, unique constraints, outboxes, or reconciliation procedures are needed to prevent duplicates.

For file writers, Spring Batch provides state mechanisms and transaction-aware behavior depending on implementation/configuration, but do not treat multiple file outputs as a distributed transaction. Test rollback/restart with the actual writers and storage.

## 14. Exceptions from Delegate Writers

If the selected writer throws an exception, the exception propagates out of `ClassifierCompositeItemWriter.write`. The step can apply retry, skip, or fail policies:

~~~java
return new StepBuilder("routePaymentsStep", jobRepository)
        .<PaymentInput, Payment>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(paymentProcessor)
        .writer(paymentWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidPaymentException.class)
        .skipLimit(10)
        .build();
~~~

Only configure retry for genuinely transient errors that are safe to repeat. If a writer already sent a message or wrote to an external system before failing, retrying can create duplicate records.

If a route hits an item-specific data error, you can use a dedicated exception and a skip policy if business rules allow. If a route is missing a writer or the classifier has a bug, failing the job is usually better than skipping because that is a configuration/program error.

## 15. Do Not Use a Classifier Writer to Filter

A classifier writer only picks the write destination. It does not replace `ItemProcessor` and has no contract to return `null` to filter an item.

If an item does not need to be written, filter it in the processor:

~~~java
public class EligiblePaymentProcessor
        implements ItemProcessor<PaymentInput, Payment> {

    @Override
    public Payment process(PaymentInput input) {
        if (!input.eligible()) {
            return null;
        }
        return toPayment(input);
    }
}
~~~

If an item is valid yet has an unknown route, that is a classification issue. Route it to a reject writer or throw an exception with context. Do not return a no-op writer to silently drop data unless that is an explicitly documented business behavior.

## 16. Classifying by Configuration Data

A classifier may need to rely on job configuration such as tenant or export mode. Inject a classifier configured for the `JobExecution` or use a factory to create the right classifier. Do not mutate mutable fields on a singleton classifier while a job is running.

Example using a route enum normalized in the processor:

~~~java
public enum ExportRoute {
    CARD,
    BANK,
    REVIEW
}

public record PaymentExport(
        String paymentId,
        ExportRoute route,
        BigDecimal amount) {
}
~~~

The processor determines the route from business rules and creates `PaymentExport`. The classifier writer simply reads `route()` and picks a writer. This separation prevents business logic from mixing with I/O mechanics.

If the route depends on `JobParameters`, ensure that value is fixed for the `JobInstance` and preserved on restart. With partitioning, each worker can have its own route/resource via `StepExecutionContext`; use step-scoped writers or appropriate worker configuration.

## 17. Performance and Batching

In the standard implementation, the composite classifies and dispatches item by item. A chunk of 100 items can lead to many write calls on delegates; even if all 100 items take the same route, that writer may still be called 100 times with singleton chunks.

This can reduce the batching benefits of `JdbcBatchItemWriter`, HTTP batch writers, or writers with per-call initialization overhead.

Options:

- Use the classifier writer when routing is simple and per-call write cost is acceptable.
- If per-destination batching is needed, write a custom `ItemWriter<T>` that groups items by route and calls each delegate once with the corresponding chunk.
- If routes have different queries against the same database, consider a custom writer grouping by SQL/statement.
- Measure delegate write call counts, round trips, latency, and throughput on representative data.

Grouping idea example:

~~~java
Map<ExportRoute, List<PaymentExport>> groups =
        items.getItems().stream()
                .collect(Collectors.groupingBy(PaymentExport::route));

List<PaymentExport> cardItems =
        groups.getOrDefault(ExportRoute.CARD, List.of());
if (!cardItems.isEmpty()) {
    cardWriter.write(new Chunk<>(cardItems));
}

List<PaymentExport> bankItems =
        groups.getOrDefault(ExportRoute.BANK, List.of());
if (!bankItems.isEmpty()) {
    bankWriter.write(new Chunk<>(bankItems));
}
~~~

This is an outline for a custom grouped writer, not a configuration of `ClassifierCompositeItemWriter`. In a real implementation, handle unsupported routes, preserve ordering if required by business rules, and register lifecycles for all `ItemStream` delegates.

## 18. Thread Safety and Multi-Threaded Steps

`ClassifierCompositeItemWriter` and its delegates must be reviewed when a step uses multiple threads. If multiple chunks are written concurrently, the same classifier writer or delegate writer may be invoked from multiple threads.

Verify:

- Is the classifier stateless/thread-safe?
- Do delegate writers support concurrent writes?
- Can two threads write to the same file/resource?
- Do writers share mutable buffers or statements?
- Are database connections/transactions acquired per thread properly?
- Can routing rules change while the step is running?

Prefer immutable classifiers and thread-safe delegate writers. For file outputs, it is usually easier to control if each partition/worker has its own resource. If you must serialize access to a writer, use explicit synchronization and measure throughput impact; do not assume the composite locks delegates automatically.

With partitioning, each worker step can create its own writer with `@StepScope` and receive its resource path/route via `StepExecutionContext`. Avoid having multiple workers open the same output file unless the writer is designed for concurrent appends.

## 19. Adapters for Writers of Different Data Types

As noted, the classifier of `ClassifierCompositeItemWriter<T>` must return a writer accepting `T` or a supertype of `T`. If you need to write subtypes using writers with specialized generics, create an adapter with the common input type.

Example:

~~~java
public class OrderRecordWriter implements ItemWriter<ImportRecord> {

    private final ItemWriter<OrderRecord> delegate;

    public OrderRecordWriter(ItemWriter<OrderRecord> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends ImportRecord> items)
            throws Exception {
        for (ImportRecord item : items) {
            if (!(item instanceof OrderRecord order)) {
                throw new IllegalArgumentException(
                        "Expected OrderRecord");
            }
            delegate.write(Chunk.of(order));
        }
    }
}
~~~

The adapter checks the item type and forwards it to the specialized writer. If the adapter's delegate implements `ItemStream`, ensure the lifecycle is forwarded or register the underlying delegate with the step. Do not use unchecked casts without verifying the subtype.

## 20. Comparison with ClassifierCompositeItemProcessor

The two classes have similar names but operate at two different stages:

| Component | Stage | Responsibility |
|---|---|---|
| ClassifierCompositeItemProcessor | Processor stage | Select a processor to transform items |
| ClassifierCompositeItemWriter | Writer stage | Select a writer to write processed items |

For example:

- If a `CARD` `PaymentInput` needs to be transformed by one rule and `BANK_TRANSFER` needs a different rule, use a classifier processor.
- If both are already normalized into `Payment` yet must be written to different tables/files, use a classifier writer.
- If both behaviors are needed, you can use a classifier processor first and then a classifier writer afterward.

Do not put complex mapping logic into a classifier writer. The writer stage should receive items ready to be written.

## 21. Testing the Classifier and Delegates

Test the classifier independently and the composite writer at the unit level:

1. An item on route A selects writer A.
2. An item on route B selects writer B.
3. Each item is sent to only one writer.
4. Multiple items in the same chunk can go to different writers.
5. Unsupported routes are handled per default/reject/fail policy.
6. The classifier does not return `null`.
7. Delegate writers receive the right items and in the required order.
8. Delegate exceptions propagate outward.
9. Stream delegates are opened, updated, and closed when the step runs.
10. Concurrent writes do not corrupt state or outputs.
11. Retries/restarts do not produce unexpected duplicates.
12. Delegate call counts match expected performance.

Example unit test checking routing:

~~~java
@Test
void routesCardPaymentToCardWriter() throws Exception {
    ItemWriter<Payment> cardWriter = mock(ItemWriter.class);
    ItemWriter<Payment> bankWriter = mock(ItemWriter.class);

    Classifier<Payment, ItemWriter<? super Payment>> classifier =
            payment -> payment.method() == PaymentMethod.CARD
                    ? cardWriter : bankWriter;

    ClassifierCompositeItemWriter<Payment> writer =
            new ClassifierCompositeItemWriter<>();
    writer.setClassifier(classifier);

    Payment payment = new Payment(
            "PAY-1", PaymentMethod.CARD, new BigDecimal("10.00"));

    writer.write(Chunk.of(payment));

    verify(cardWriter).write(Chunk.of(payment));
    verifyNoInteractions(bankWriter);
}
~~~

This snippet illustrates single-item routing; in real tests, you can capture the chunk passed to the delegate to compare contents rather than relying on `Chunk` object equality.

## 22. Integration Testing in a Step

Integration tests should run the step with multiple item types and writers whose output can be observed. For example, an input with three `CARD`, two `BANK_TRANSFER`, and one `CASH` items; after the step, verify each destination received the right count and exact items.

Points to verify:

- The job/step completes when all routes are valid.
- No item is written to two destinations when the classifier selects only one writer.
- Unknown routes trigger rejection or failure per policy.
- Delegate `ItemStream` components open/close and checkpoint properly.
- If a delegate fails, the transaction rolls back according to the resource/transaction manager.
- Restart restores writer state and does not repeat committed outputs.
- Output files have proper headers/footers and are not overwritten by multiple workers.

Test against a real database or Testcontainers when verifying transactions, SQL, and indexes. For file writers, read back output files and parse contents rather than only checking file existence.

## 23. Common Pitfalls

**Confusing routing with broadcasting.** A classifier selects one writer per item; use `CompositeItemWriter` if you need to send to all delegates.

**Classifier returning null.** There is no write destination and an error occurs on dispatch. Return a reject/default writer or throw a clear exception.

**Generic-incompatible delegate writers.** `ItemWriter<Subtype>` cannot accept every item of the base type. Use a type-checking adapter or a writer accepting the common type.

**Forgetting to register delegate ItemStreams.** File writers may not be opened/closed or persist state properly. Register each stream with `.stream(...)`.

**Assuming one composite write equals one delegate write.** Standard dispatch happens item by item; it may issue many singleton chunk calls. Measure and consider a grouped writer if batching is needed.

**Routes changing between initial run and restart.** Items may go to a different output than already written data. Keep the classifier and `JobParameters` stable.

**Multiple writers writing to one file.** Can cause interleaving, overwrites, or file corruption. Use separate resources or writers designed for coordination.

**Assuming multiple outputs roll back atomically together.** Files/APIs/databases have different transaction semantics. Use outboxes, staging, and reconciliation when needed.

**Non-thread-safe delegates.** Multi-threaded steps may invoke writers concurrently. Check each delegate or partition resources separately.

**Using a writer to filter items.** A writer's job is writing. Filter in the processor or write rejects via a designed route.

## 24. Implementation Workflow

When building a `ClassifierCompositeItemWriter`, follow this sequence:

1. Identify the final item type received by the writer.
2. Identify stable classification criteria and valid routes.
3. Create delegate writers capable of accepting the item type or a compatible supertype.
4. Write the classifier with explicit default/reject/fail behavior.
5. Configure `ClassifierCompositeItemWriter` and attach it to the step.
6. Register delegates implementing `ItemStream` separately.
7. Define transactions, restart, and idempotency for each output resource.
8. Evaluate writer call counts and batching opportunities per route.
9. Check thread safety if using multi-threading or partitioning.
10. Write unit tests for routing and integration tests for transactions, lifecycle, and restart.

## Conclusion

`ClassifierCompositeItemWriter<T>` routes each item to an `ItemWriter` selected by a `Classifier`. It fits when the same pipeline needs to write groups of items to different destinations. The writer type returned by the classifier must accept item type `T`; for subtype-specialized writers, use an adapter with type checking.

Define stable routes, handle unknown routes explicitly, distinguish routing from broadcasting, and remember to register `ItemStream` delegates with the step so they are opened, updated, and closed following the proper lifecycle. Delegate calls occur within the chunk's write phase yet do not guarantee atomic rollback across all output types. Evaluate batching, transactions, restart, idempotency, and thread safety for each writer. Test multiple routes within the same chunk, lifecycles, delegate failures, and restarts to ensure data reaches the right destination without loss or duplication.
