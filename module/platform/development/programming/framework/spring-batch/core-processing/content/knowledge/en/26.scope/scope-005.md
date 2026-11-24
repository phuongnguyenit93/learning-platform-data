# Step-Scoped Beans

In Spring Batch, `@StepScope` allows declaring a bean whose lifecycle is tied to a single Step execution (`StepExecution`). The bean is only created when the Step context is ready and can receive runtime values such as `JobParameters`, `StepExecutionContext`, or `JobExecutionContext` via late binding.

This is especially useful for components like `ItemReader`, `ItemProcessor`, and `ItemWriter` that need to know the input file, business date, partition ID range, or a value determined only when the Job starts running. `@StepScope` also ensures each StepExecution gets its own instance of a stateful component rather than sharing a single singleton object across the entire application context.

## 1. What Is Bean Scope?

In the Spring Framework, bean scope defines the boundary within which Spring creates and manages a bean instance. For example, a default `singleton` bean normally has one instance per application context; a `prototype` bean creates a new instance on each bean lookup.

Spring Batch adds scopes tied to the batch lifecycle:

- **Step scope:** one target bean instance per running `StepExecution`.
- **Job scope:** one target bean instance per `JobExecution`.

`@StepScope` is a convenient annotation for declaring a bean with step scope. It is equivalent to declaring scope `step` with a scoped proxy.

Example:

```java
@Bean
@StepScope
public ItemReader<Order> orderReader() {
    return new CustomOrderReader();
}
```

The bean above is not created as a target instance immediately when Spring starts the application context. Spring creates a proxy so other beans can reference it; the actual target is instantiated when an appropriate StepExecution is active and the bean is used.

## 2. Why Is @StepScope Needed?

Singleton beans are created before the Job runs, whereas many input details are only available when the Job is launched. For example, the same Job may run for different business dates or different files:

```text
Run A: businessDate=2026-11-14, inputFile=orders-14.csv
Run B: businessDate=2026-11-15, inputFile=orders-15.csv
```

If a singleton reader stores the file path in a field, two runs can inadvertently share or overwrite state. `@StepScope` enables the reader to receive the parameters of the current StepExecution and have a dedicated instance per Step execution.

Key benefits:

- **Late binding:** reads JobParameters or ExecutionContext at the moment the Step runs.
- **Per-StepExecution state:** stateful readers/writers do not need to share a target instance across different StepExecutions.
- **Flexible configuration:** the same Step definition can run with different files, dates, or data ranges.
- **Partitioning support:** each partition has its own StepExecution and can receive its own context.
- **Separating configuration from initialization code:** runtime values are injected instead of being manually read from static fields or singleton mutable state.

Not every bean in the application needs to be step-scoped. Stateless services, immutable mappers, or repositories usually still fit singleton scope. Use `@StepScope` when a bean genuinely needs runtime data or state tied to a StepExecution.

## 3. How @StepScope Works

`@StepScope` creates a scoped proxy. The proxy can be injected into Step configuration right when the application context initializes, but only when the Step is running is there a context to create or retrieve the corresponding target bean.

```text
Application context starts
        |
        +--> Create scoped proxy for orderReader
        |
        +--> Inject proxy into Step definition

Job starts importOrdersStep
        |
        +--> Create / activate StepExecution
        |
        +--> Step scope has current context
        |
        +--> Proxy creates or retrieves target orderReader
        |
        +--> Reader receives JobParameters / StepExecutionContext
        |
        +--> Step processes and completes
        |
        +--> Step scope destroys target instance
```

The key point is that the bean injected into the Step configuration is normally a proxy, not a target object already initialized with runtime parameters. When the Step calls the reader, the proxy delegates the call to the target instance belonging to the current StepExecution.

If a method on the scoped proxy is called when no active Step context exists, Spring cannot locate a target instance and may throw a scope/context error, typically stating that no context holder is available for step scope. Therefore, do not invoke methods on a step-scoped bean directly from application startup code or from a singleton before the Step runs.

## 4. Late Binding from JobParameters

A common case is a reader needing a file path passed when launching the Job. You can use `@Value` with SpEL to retrieve the JobParameter:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

The Job can be launched with parameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/orders-2026-11-15.csv")
        .addString("businessDate", "2026-11-15")
        .toJobParameters();
```

When `orderReader` is used in the Step, Spring Batch supplies the JobParameters of the current JobExecution. The reader will use the exact file specified for that run.

In the example, `.saveState(true)` enables saving the reader's checkpoint to support restarts. `@StepScope` does not save the read position by itself; the two features serve different roles: scope manages bean lifecycle, while save state/ExecutionContext manages processing progress.

Validate required parameters before creating the resource. If `inputFile` is missing or empty, throw a clear configuration error rather than letting the reader fail with an obscure error when opening the file.

## 5. Late Binding from StepExecutionContext

With a partitioned Step, each worker partition has its own StepExecution and ExecutionContext. The Partitioner can place data bounds into the context; the step-scoped reader receives those values when the target instance is created.

Example of a partitioner creating a context:

```java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1L);
context.putLong("maxId", 1000L);
```

Reader reading bounds from StepExecutionContext:

```java
@Bean
@StepScope
public JdbcPagingItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> rowMapper,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("partitionOrderReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .rowMapper(rowMapper)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Each partition can receive a different `minId`/`maxId` pair. Because the reader bean is step-scoped, the target instance of each StepExecution is created with its corresponding context.

The `PagingQueryProvider` query must use these parameters to filter the exact range and maintain a deterministic order, such as `ORDER BY order_id` where `order_id` uniquely identifies each record.

## 6. Late Binding from JobExecutionContext

JobExecutionContext holds data at the JobExecution scope, which can be shared among Steps within the same Job execution. A step-scoped bean can read that data:

```java
@Bean
@StepScope
public ItemProcessor<Order, EnrichedOrder> enrichOrderProcessor(
        @Value("#{jobExecutionContext['referenceVersion']}") String referenceVersion) {

    return order -> enrichUsingReferenceVersion(order, referenceVersion);
}
```

For example, an earlier Step determines the version of a reference table and stores it in JobExecutionContext. A later Step uses a step-scoped processor to receive that version.

You should distinguish the binding sources:

| Expression | Data Source | Scope |
|---|---|---|
| `#{jobParameters['inputFile']}` | JobParameters | Parameters of the JobExecution |
| `#{stepExecutionContext['minId']}` | Step ExecutionContext | Specific to the current StepExecution |
| `#{jobExecutionContext['referenceVersion']}` | Job ExecutionContext | Shared across Steps of the Job |

JobParameters are typically fixed inputs for the run. ExecutionContext holds state produced during Job/Step execution. Choose the right scope to avoid storing reader checkpoints in the wrong place.

## 7. Using @StepScope for ItemReader

`ItemReader` is usually the component that needs step scope the most because it can depend on a file, query parameters, or read-position state. Built-in readers such as `FlatFileItemReader`, `JdbcPagingItemReader`, and `JdbcCursorItemReader` can persist state through `ItemStream`.

Example of a reader taking a business date:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> dailyOrderReader(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    Resource resource = new FileSystemResource(
            "data/orders-" + businessDate + ".csv"
    );

    return new FlatFileItemReaderBuilder<Order>()
            .name("dailyOrderReader")
            .resource(resource)
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

The reader is created per StepExecution with the appropriate file. The reader name must stay stable across restarts; if renamed, internal keys used to persist state may change and the reader may fail to find its old checkpoint.

If the file can be replaced between the initial run and a restart, line-based checkpoints no longer guarantee pointing to the same records. Keep the input file stable, use versioning/checksums, or establish a suitable snapshot workflow.

## 8. Using @StepScope for ItemProcessor and ItemWriter

A processor or writer may also need runtime parameters or state specific to a StepExecution.

Example of a processor receiving a business threshold:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> minimumAmountProcessor(
        @Value("#{jobParameters['minimumAmount']}") BigDecimal minimumAmount) {

    return order -> order.getAmount().compareTo(minimumAmount) >= 0
            ? order
            : null;
}
```

The processor filters out orders with amounts below the threshold by returning `null`. Each StepExecution can use a different threshold.

Example of a writer building a filename from the business date:

```java
@Bean
@StepScope
public FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("dailyOrderWriter")
            .resource(new FileSystemResource(
                    "output/orders-" + businessDate + ".csv"
            ))
            .delimited()
            .names("orderId", "amount")
            .shouldDeleteIfExists(false)
            .saveState(true)
            .build();
}
```

The writer may need additional append/overwrite configuration aligned with the actual restart strategy. Do not pick `shouldDeleteIfExists` or append arbitrarily; that behavior must match checkpointing and the file generation workflow.

Not every processor or writer needs step scope. If they are stateless and require no late binding, singleton is usually simpler.

## 9. Registering a Scoped Bean in a Step

A step-scoped bean can be injected into Step configuration through a proxy:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> dailyOrderReader,
        ItemProcessor<Order, Order> minimumAmountProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(dailyOrderReader)
            .processor(minimumAmountProcessor)
            .writer(orderWriter)
            .build();
}
```

The method parameters of `importOrdersStep()` are injected by Spring when constructing the Step definition. For step-scoped beans, the injected objects are scoped proxies. Target readers/processors/writers are only created when the corresponding StepExecution is active and the Step actually accesses the bean.

This is why you can declare a singleton Step while still using step-scoped collaborators. The Step definition describes the processing structure; target beans receive runtime values per StepExecution.

Do not call `new` to manually instantiate components that need scope, because manually created objects live outside Spring's lifecycle and dependency injection. Let Spring manage the bean through `@Bean` or appropriate component scanning.

## 10. ItemStream and the @Bean Return Type

An important detail when declaring a step-scoped reader is the return type of the `@Bean` method. Spring Batch needs to recognize whether the reader implements `ItemStream` in order to call `open()`, `update()`, and `close()` during the Step lifecycle.

For example, declare the return type as `ItemStreamReader` or the concrete reader class:

```java
@Bean
@StepScope
public ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

`ItemStreamReader<T>` combines `ItemReader<T>` and `ItemStream`. If only the generic `ItemReader<T>` return type is declared, Spring Batch may not recognize the `ItemStream` contract at Step configuration time, depending on how the bean/proxy is declared. In that case, callbacks for saving/restoring state may not be registered as intended.

For custom readers, make sure the return type and registration clearly expose `ItemStream`. If the reader is wrapped in a delegate/wrapper, you may need to register the stream delegate explicitly with `.stream(delegate)` in the Step configuration.

## 11. @StepScope and Restart

`@StepScope` does not make a bean restartable on its own. The scope only manages the target instance's lifecycle per StepExecution and enables late binding. Restartability depends on whether the component persists the necessary state and whether the data source can resume from the right position.

For example, when a Job fails after the reader has committed up to line 500:

1. The old StepExecution stores the reader checkpoint in ExecutionContext.
2. The Job is restarted with the same identifying JobParameters to resume the same JobInstance.
3. Spring Batch creates a new StepExecution for the re-run of the Step.
4. Step scope creates a target reader instance for the new StepExecution.
5. The reader reopens and reads the checkpoint saved in ExecutionContext.

The new target bean does not need to retain Java fields from the previous process. It restores state from ExecutionContext or a durable data source.

For built-in readers, enable `.saveState(true)` when checkpointing is needed and configure a stable `.name(...)`. For custom readers, implement `ItemStream`, read state in `open()`, and write state in `update()`.

## 12. @StepScope in Partitioning

Partitioning creates multiple StepExecutions for the worker Step. Each partition has its own StepExecutionContext and can therefore have its own step-scoped target bean.

```text
Manager Step
   |
   +--> Worker StepExecution partition-0
   |       +--> Step-scoped reader target #0
   |       +--> stepExecutionContext: minId=1, maxId=1000
   |
   +--> Worker StepExecution partition-1
   |       +--> Step-scoped reader target #1
   |       +--> stepExecutionContext: minId=1001, maxId=2000
   |
   +--> Worker StepExecution partition-2
           +--> Step-scoped reader target #2
           +--> stepExecutionContext: minId=2001, maxId=3000
```

Thanks to step scope, every worker can use the same bean definition while each target instance receives its own data bounds. This prevents sharing reader state across partitions.

Partition names, reader names, and keys in ExecutionContext must remain stable for restart. If a partitioner generates different names or ranges between the initial run and a restart, target beans may receive contexts that no longer match old checkpoints.

## 13. @StepScope Does Not Mean Thread-Safe

A common misconception is that because a bean is step-scoped, it is automatically safe for multi-threaded execution. That is false.

In a multi-threaded Step, multiple threads can execute concurrently within one StepExecution. A step-scoped bean bound to that StepExecution can be shared among threads in the same Step. If the target bean has mutable fields or the reader does not support concurrent access, race conditions can still occur.

Unsafe example:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> sequenceProcessor() {
    return new ItemProcessor<>() {

        private long sequence;

        @Override
        public Order process(Order order) {
            sequence++;
            return order.withSequence(sequence);
        }
    };
}
```

If multiple threads call the processor concurrently, incrementing `sequence` guarantees neither business ordering nor correctness. `@StepScope` does not synchronize fields automatically, nor does it turn a non-thread-safe reader into a thread-safe one.

Design guidelines:

- Prefer stateless processors and immutable dependencies.
- Only use mutable state when the component supports concurrent access or has proper synchronization.
- With partitioning, use a separate StepExecution per partition so each partition has its own target instance.
- Do not assume a multi-threaded Step and partitioning share the same scope model; inspect which StepExecution owns the bean.
- Check thread safety of readers/writers in the specific implementation's documentation.

## 14. Comparing @StepScope and @JobScope

These two scopes differ in instance lifetime and runtime data sources.

| Criterion | `@StepScope` | `@JobScope` |
|---|---|---|
| Target instance scope | One StepExecution | One JobExecution |
| Accessible contexts | JobParameters, StepExecutionContext, JobExecutionContext | JobParameters and JobExecutionContext |
| Suitable for | Reader/processor/writer depending on Step or partition | Components sharing Job-level data across multiple Steps |
| Instances in one Job | Potentially many, one per StepExecution | One target per JobExecution |
| Restart | New target for the new StepExecution; state must be restored from metadata | New target for the new JobExecution; data kept across restarts must be stored durably |

Example of `@JobScope`:

```java
@Bean
@JobScope
public SomeJobCoordinator jobCoordinator(
        @Value("#{jobParameters['businessDate']}") String businessDate) {
    return new SomeJobCoordinator(businessDate);
}
```

If a reader needs partition-specific `minId` bounds, `@StepScope` is the right choice because each partition has its own StepExecutionContext. If a component needs data shared across the entire JobExecution and used by multiple Steps, `@JobScope` may be a better fit.

Do not use `@JobScope` for a reader with per-partition read-position state, because a target instance scoped to JobExecution could be shared across multiple worker StepExecutions.

## 15. Common Mistakes When Using @StepScope

### Accessing a bean outside a Step context

The scoped proxy is injected at application startup, but the target can only be obtained when a Step context is active. Calling methods too early from a singleton or inside `@PostConstruct` can trigger an error that no active Step scope exists.

### Forgetting the @StepScope annotation

If a bean needs `jobParameters` or `stepExecutionContext` yet is a singleton, late-binding expressions may not evaluate at the right time or may lack context. Apply the scope to the exact bean needing runtime binding.

### Using the wrong key name in SpEL

`#{jobParameters['inputFile']}` and `#{stepExecutionContext['inputFile']}` read from two different sources. Verify that keys created in JobParameters or the Partitioner match the expected name and scope.

### Returning an overly generic ItemReader when the reader needs ItemStream

If the return type does not expose `ItemStream`, the framework may fail to register lifecycle callbacks for the reader as intended. Use `ItemStreamReader<T>` or a concrete class.

### Disabling saveState while expecting restart

Scope does not persist checkpoints. Readers need `saveState(true)` or an appropriate `ItemStream` implementation.

### Using step scope to solve all thread-safety issues

A bean can still be shared within the same StepExecution across multiple threads. Concurrent access must be designed explicitly.

### Using a mutable singleton to hold Step parameters

Do not assign the current execution's JobParameters into a field on a singleton service. Concurrent Job runs can overwrite values. Use late binding, method arguments, or appropriately scoped contexts.

## 16. Testing Step-Scoped Beans

Testing a step-scoped bean requires an active Step context so the proxy can instantiate the target instance. Spring Batch Test provides utilities to build a `StepExecution` and execute code within step scope.

Example using `StepScopeTestUtils`:

```java
@SpringBatchTest
@SpringBootTest
class OrderReaderStepScopeTest {

    @Autowired
    private ItemStreamReader<Order> orderReader;

    @Test
    void readerUsesInputFileFromStepContext() throws Exception {
        StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution(
                new JobParametersBuilder()
                        .addString("inputFile", "data/test-orders.csv")
                        .toJobParameters()
        );

        Order firstOrder = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> orderReader.read()
        );

        assertNotNull(firstOrder);
    }
}
```

This is an illustrative example; real tests need to prepare fixture files and handle the `open()`/`close()` lifecycle for the reader when calling `read()` directly. You can use `StepScopeTestExecutionListener` or the test support registered via `@SpringBatchTest` to set up the scope inside test methods.

Cases to verify:

- The bean receives the exact JobParameters of the current StepExecution.
- Two different StepExecutions receive different runtime values.
- Each partition's StepExecutionContext is bound accurately.
- Accessing the target outside a Step context does not happen in normal application code.
- The reader opens, updates, and closes state properly.
- Restarts create a new target instance while restoring checkpoints from ExecutionContext.
- Multi-threaded Steps do not cause races on mutable state.

## 17. Common Misconceptions

**Thinking `@StepScope` creates a new bean for every item or every chunk.** The target instance is bound to the StepExecution, not to individual `read()` or `process()` calls.

**Thinking step-scoped beans are created right at application startup.** Spring creates a proxy upfront; the target instance is instantiated when an active Step context exists and the bean is accessed.

**Thinking `@StepScope` automatically preserves state across restarts.** Scope manages bean lifecycle; `ExecutionContext`/`ItemStream` is what persists durable checkpoints.

**Thinking `@StepScope` automatically makes a bean thread-safe.** Multiple threads within the same StepExecution can share the target. Mutable state still needs proper management.

**Thinking every component should be step-scoped.** Use scope when late binding or StepExecution-specific state is needed; stateless services can remain singletons.

**Using Job scope for per-partition state.** Partitions have separate StepExecutionContexts, so partition-dependent readers usually need StepScope.

## 18. How to Choose and Configure StepScope

Identify which beans need data available only when the Job/Step runs. If values belong to a single Step or partition, use `@StepScope` and late-bind from JobParameters or StepExecutionContext. If data spans the entire JobExecution and is shared across multiple Steps, consider `@JobScope`. Keep stateless services as singletons to keep configuration simple.

For stateful readers, ensure the return type exposes `ItemStreamReader` or a concrete implementation, configure a stable reader name, and enable `saveState` when restart is required. Do not treat scope as a checkpoint or a thread-safety mechanism. Under partitioning, each StepExecution gets its own target instance; under a multi-threaded Step, multiple threads can still share one target within the StepExecution.

Designing `@StepScope` properly lets a single Step definition run with varied runtime parameters and keep isolated state per execution, while integrating late binding cleanly with Spring Batch's checkpoint and restart mechanisms.
