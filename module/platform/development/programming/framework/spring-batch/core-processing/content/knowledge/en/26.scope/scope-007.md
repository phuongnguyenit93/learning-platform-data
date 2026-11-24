# Readers or Writers That Need Step Scope

In Spring Batch, readers and writers are often stateful components tied to a single Step execution. A reader may keep its current read position, a writer may hold an open file handle or checkpoint, and both often need values available only when the Job/Step starts, such as a filename, processing date, or partition data range. If these components are declared as ordinary singletons, multiple Step runs can share one instance and accidentally share state.

@StepScope lets Spring instantiate the target bean within the scope of a single StepExecution. This mechanism also supports late binding: the bean is only initialized while the Step is running, at which point values from JobParameters, Job ExecutionContext, and Step ExecutionContext can be passed into the factory method. Therefore, readers or writers that need per-StepExecution runtime data should usually be declared step-scoped.

## 1. Spring Beans Are Singletons by Default

Without another scope declared, Spring beans normally have singleton scope. Spring creates one instance in the ApplicationContext and reuses that instance wherever the bean is injected.

Example of a singleton reader:

~~~java
@Bean
FlatFileItemReader<Order> orderReader() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource("/data/orders.csv"))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .build();
}
~~~

The configuration above works when the resource and configuration are genuinely fixed and the component can be safely reused. However, readers often hold state such as the current position in a file, number of items read, open resource handles, and checkpoints. If the same instance is used across multiple StepExecutions, state can be shared unintentionally.

Writers can also hold an open output file, write buffers, or write state. If two JobExecutions share a writer instance, they could write to the same resource or interfere with each other's open/close lifecycle.

The issue is not limited to mutable fields declared by the application. Readers/writers may hold state inside underlying libraries, delegates, or resources not directly visible to the application. Therefore, examine the actual lifecycle of the component.

## 2. What Is Step Scope?

Step scope is a Spring scope provided by Spring Batch. A bean in this scope has a target instance bound to the current StepExecution. When another StepExecution runs, Spring creates a different target instance for the same bean definition.

~~~text
ApplicationContext
      |
      +--> Bean definition: orderReader
                 |
                 v
          Injected scoped proxy
                 |
       +---------+---------+
       |                   |
       v                   v
 StepExecution A      StepExecution B
       |                   |
       v                   v
 Target reader A      Target reader B
       |                   |
       v                   v
 State/checkpoint A   State/checkpoint B
~~~

Scoped proxies allow singleton beans such as Job and Step definitions to reference step-scoped readers/writers right when the ApplicationContext is created. The proxy looks up the appropriate target instance when invoked within an active StepExecution.

The @StepScope annotation is a convenient way to declare step scope. It is commonly placed on the @Bean method declaring a reader or writer:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader() {
    // Target reader is created when Step scope is active.
}
~~~

This scope does not mean the bean lives forever with the Job or the whole application. The target is managed according to the StepExecution lifecycle and destroyed when the corresponding scope ends.

## 3. Why Do Readers Often Need Step Scope?

Readers are frequently stateful components. For example:

- FlatFileItemReader holds the current line position and resource state.
- JdbcPagingItemReader holds page tracking or read position state.
- JpaPagingItemReader manages pages and read state.
- A custom ItemReader may hold a last ID, offset, cursor, or pagination token.
- A reader receiving a partition range needs the start/end bounds of the current partition.

If a reader is reused across multiple executions, a singleton instance can retain checkpoints or resources from a previous run. That causes bugs such as continuing from an old position, using the wrong file, or sharing state across partitions.

For example, a Job running daily with a different file each day, where the filename is a JobParameter:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

Each JobExecution can pass a different inputFile. Because the reader is created in Step scope, it receives the exact value of the running execution.

If @StepScope is omitted, Spring tries to create the singleton bean when initializing the ApplicationContext. At that time there is no specific StepExecution to resolve jobParameters['inputFile']; late binding cannot work properly.

## 4. Why Do Writers Often Need Step Scope?

Writers can also hold state and resources:

- FlatFileItemWriter holds the output file, write buffers, and write state.
- Paging or batch writers can maintain counters or checkpoints.
- Custom writers may receive a filename, target table, tenant, or partition ID.
- A writer may need to create a dedicated resource per JobExecution.

For example, each JobExecution writes to a file passed via a JobParameter:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

In a real application, the policy for handling an existing file must be decided explicitly. The example above only illustrates passing a resource per JobExecution; you should avoid accidentally overwriting files from another run.

A singleton writer could retain an open resource or state from a previous run. Step scope creates a separate target per StepExecution and binds the writer's lifecycle to that run.

## 5. Late Binding from JobParameters

JobParameters are supplied when launching the Job. Step-scoped beans can receive those values using SpEL:

~~~java
@Value("#{jobParameters['inputFile']}")
String inputFile
~~~

Reader example:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

Values are only resolved when the target bean is created in Step scope. This allows the same Job definition to run with many different parameter sets without creating a new bean definition for each run.

JobParameters describe the Job's inputs. If a parameter is marked identifying, it participates in identifying the JobInstance. If non-identifying, it does not alter JobInstance identity, though it can still be stored in metadata. Do not place passwords or tokens into JobParameters just because they can be injected via SpEL.

## 6. Late Binding from Job ExecutionContext

One Step can produce metadata for a later Step to use. Values stored in Job ExecutionContext can be injected into a step-scoped reader/writer.

Example of a Step preparing a validated file:

~~~java
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String validatedFile =
                "/data/batch/validated-orders.csv";

        contribution.getStepExecution()
                .getJobExecution()
                .getExecutionContext()
                .putString("validatedFile", validatedFile);

        return RepeatStatus.FINISHED;
    }
}
~~~

The next Step's reader receives the path:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> validatedOrderReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("validatedOrderReader")
            .resource(new FileSystemResource(validatedFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

Job ExecutionContext is shared across Steps within the same JobExecution. It fits small metadata that must be passed between Steps, such as a file path, resolved business date, or staging batch code.

If the previous Step only writes data to Step ExecutionContext, the next Step will not automatically see that key through jobExecutionContext. When promotion is needed, use ExecutionContextPromotionListener or design the earlier Step to write into the Job context scope.

## 7. Late Binding from Step ExecutionContext

Step ExecutionContext holds state specific to a single StepExecution. With partitioning, each worker StepExecution has its own context, typically containing the data range the worker should process.

Example of a Partitioner setting two bounds:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1001L);
context.putLong("maxIdExclusive", 2001L);
~~~

Reader receiving those values:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}")
        Long maxIdExclusive) {

    // Configure query to read only IDs within the partition range.
}
~~~

Each partition has its own StepExecution and target reader. Therefore, workers can share the same bean definition while receiving different bounds.

Do not use a static variable or a mutable singleton to swap min/max before each worker. When partitions run concurrently, workers can overwrite each other's parameters.

## 8. Declaring a Step-Scoped Reader in Java Configuration

A typical configuration combines a step-scoped reader with a singleton Step:

~~~java
@Configuration
public class OrderBatchConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<Order> orderReader(
            @Value("#{jobParameters['inputFile']}")
            String inputFile) {

        return new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Order> orderReader,
            ItemWriter<Order> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, Order>chunk(100, transactionManager)
                .reader(orderReader)
                .writer(orderWriter)
                .build();
    }
}
~~~

The Step definition can be a singleton. When configuring the Step, the injected `orderReader` variable is actually a scoped proxy. When the Step runs, the proxy resolves the target reader of the current StepExecution.

Do not call `new FlatFileItemReader` elsewhere to replace a bean declared as step-scoped. Manual instantiation bypasses container scope, late binding, and Spring's resource management lifecycle.

## 9. Declaring a Step-Scoped Writer in Java Configuration

A writer can receive an output path or destination details from JobParameters:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

The Step uses the proxy just like with a reader:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        FlatFileItemWriter<Order> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}
~~~

The example shows the output resource being determined at the time the Step runs. In an application supporting restart, you must decide how the writer reopens the file and how checkpoints are persisted. Do not change the output path between the initial run and a restart of the same JobInstance if the writer relies on the existing file to continue.

## 10. @Bean Return Type and ItemStream

An important detail when declaring stateful readers/writers is the return type of the @Bean method.

If the component implements ItemStream, declare a return type specific enough for Spring Batch to recognize that lifecycle. It is best to use a concrete class such as FlatFileItemReader<Order> or the appropriate ItemStreamReader<Order>/ItemStreamWriter<Order> interface.

Example:

~~~java
@Bean
@StepScope
ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

If only ItemReader<Order> is declared as the return type while the implementation also implements ItemStream, type information may not be visible when configuring the Step. That can prevent the open, update, and close lifecycles from being registered as expected.

For custom stateful readers/writers, implement ItemStreamReader or ItemStreamWriter and make the declared return type reflect the stream-aware interface.

## 11. Step Scope and the ItemStream Lifecycle

@StepScope and ItemStream solve two related yet distinct problems:

- Step scope manages the target bean's lifecycle per StepExecution and enables late binding.
- ItemStream provides a lifecycle to open resources, restore state, save checkpoints, and close resources.

A step-scoped reader does not automatically save all its fields to the JobRepository. To support restart, the component must persist state in ExecutionContext through the ItemStream lifecycle or use an appropriate checkpoint mechanism.

ItemStream callbacks:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

In a chunk-oriented Step, Spring Batch calls open when the Step starts, update at checkpoints, and close when the Step finishes according to the lifecycle. The reader/writer can restore state from ExecutionContext in open and update checkpoints in update.

Example of a custom reader:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private static final String LAST_ID = "customerReader.lastId";
    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
                ? context.getLong(LAST_ID)
                : 0L;
    }

    @Override
    public Customer read() {
        Customer customer = loadNextAfter(lastId);
        if (customer != null) {
            lastId = customer.getId();
        }
        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastId);
    }

    @Override
    public void close() {
        // Close resources if any.
    }
}
~~~

If this bean is created with Step scope, each StepExecution gets its own target reader. ItemStream remains the mechanism for persisting checkpoints; scope does not replace it.

## 12. Delegates and Composite Readers/Writers

A reader or writer may wrap other delegates. For instance, a composite writer coordinates multiple child writers, or a custom reader uses a delegate to read a file.

When a delegate implements ItemStream, ensure the delegate is registered with the Step so the framework calls open, update, and close. Simply wrapping a delegate inside a step-scoped bean does not guarantee every child stream is automatically detected in every structure.

Items to verify:

- Does the composite implement ItemStream?
- Are delegate streams registered in the proper lifecycle?
- Do delegates have their own state that needs saving to ExecutionContext?
- Are component names in the context stable and free of collisions?
- Are resources closed when the Step succeeds or fails?

If a custom wrapper hides the delegate's ItemStream interface, implement/delegate lifecycle callbacks properly or register the stream using the Step's mechanism. Otherwise, the Job may succeed on the first run yet fail to restore state properly on restart.

## 13. Step Scope vs. Job Scope

Spring Batch has both @StepScope and @JobScope.

| Scope | Target lifecycle | Use when |
|---|---|---|
| Singleton | One instance in ApplicationContext | Stateless bean, fixed configuration, and safe to share |
| Job scope | Bound to a single JobExecution | Bean needs data or state shared within a JobExecution |
| Step scope | Bound to a single StepExecution | Reader/writer or component needing Step-specific state and parameters |

@JobScope is helpful for components that need to live across a single JobExecution, such as a coordinator bean using metadata shared across Steps. @StepScope is better suited for readers/writers needing a checkpoint or partition parameters for a single StepExecution.

JobParameters can be injected into both Job-scoped and Step-scoped beans. However, if the component is a Step reader/writer, step scope usually expresses its lifecycle more accurately.

Do not use Job scope to store reader checkpoints dedicated to individual Steps. If a Job has multiple Steps or partitions, reader state must belong to the corresponding StepExecution.

## 14. When Doesn't a Reader/Writer Need Step Scope?

Not every reader or writer must be step-scoped. A stateless, thread-safe component using fixed configuration and holding no dedicated resources or checkpoints can be used as a singleton if its lifecycle permits.

For example, a writer that only forwards data to a thread-safe service and holds no state may not need a separate scope. Still, verify:

- No mutable fields per execution.
- No open resources held across multiple runs.
- No need for late binding from JobParameters or ExecutionContext.
- Can be invoked concurrently by multiple StepExecutions.
- Holds no checkpoints or temporary data belonging to a Step.

If unsure whether a component holds hidden state, inspect its implementation and ItemStream contract. Do not mechanically add @StepScope to every bean; choose the scope based on the lifecycle and data the component genuinely needs.

## 15. Step Scope in Partitioning

In a partitioned Step, the manager creates multiple worker StepExecutions. Each worker has its own Step ExecutionContext, so readers/writers must receive the parameters of their respective partition.

Example:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionCustomerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}")
        Long maxIdExclusive) {

    // Create reader restricted to the worker's ID range.
}
~~~

If there are four partitions, Spring creates a target reader per StepExecution. Workers can use the same bean definition while each target receives its own min/max bounds.

This is a primary reason to use Step scope in partitioning. Do not use a singleton reader whose parameters are mutated per partition; when workers run in parallel, they can read duplicates or skip records.

## 16. Step Scope and Multi-Threaded Execution Within One Step

Distinguish partitioning from a multi-threaded Step.

In partitioning, each worker has its own StepExecution, so each StepExecution gets its own scoped target. In a multi-threaded Step, multiple threads can work concurrently inside a single StepExecution. A step-scoped bean does not automatically mean a separate instance per thread or per item.

If a step-scoped reader/writer holds mutable state while the Step processes concurrently with multiple threads, thread safety still depends on the implementation. A non-thread-safe reader may need synchronization, reader splitting, or another design suited to the concurrency model.

Do not treat @StepScope as an automatic solution to every race condition. Determine:

- How many StepExecutions exist?
- How many threads process a single StepExecution simultaneously?
- Do the reader/writer support concurrent calls?
- Can checkpoints be updated concurrently?
- Are transaction boundaries and commit ordering guaranteed?

For a multi-threaded Step, check the thread-safety capabilities of the specific component and test under parallel load. For partitioning, prefer isolated state per worker StepExecution.

## 17. How Is Step Scope Enabled?

Step scope requires Spring Batch infrastructure to be configured. Common setups such as @EnableBatchProcessing or DefaultBatchConfiguration register the required scope. Spring Boot with Batch auto-configuration also sets up this infrastructure.

Example:

~~~java
@Configuration
@EnableBatchProcessing
public class BatchConfiguration {
    // Declare Job, Step, and scoped components.
}
~~~

In an application using Spring Boot's Batch auto-configuration, do not add duplicate infrastructure configuration just to enable Step scope. Use one repository/Batch configuration model consistent with your framework version.

@StepScope creates a scoped proxy for the bean. When the proxy is invoked outside an active StepExecution, Spring cannot find the target in scope and may throw ScopeNotActiveException or an error related to an unregistered context.

This commonly happens when:
- Calling a reader directly while the ApplicationContext is starting up.
- Using a scoped bean in a singleton's @PostConstruct.
- Instantiating Step components manually outside the Job/Step lifecycle.
- Testing a bean without setting up a StepExecution context.

Do not invoke methods of a step-scoped reader/writer during configuration initialization. Let the Step framework invoke components while the Step is running.

## 18. Proxies and Bean Types

Because @StepScope uses a scoped proxy, the bean injected into the Job/Step definition is normally a proxy, while the actual target is only created when the scope is active.

Key considerations:

- Avoid declaring the target class `final` when using class-based scoped proxies.
- Do not invoke methods that depend on runtime context before the Step starts.
- Keep the @Bean return type specific enough, especially with ItemStream.
- Do not instantiate instances with `new` to replace a scoped proxy.
- Do not retain references to the target bean after Step scope ends.
- Use constructor injection for stable dependencies; use @Value for runtime values.

In Java configuration examples, the @Bean method can receive JobParameters or context values via @Value parameters. Spring creates the target only when the scope can resolve those values.

## 19. Common Mistakes When Using @StepScope

**Forgetting to declare Step scope.** SpEL referencing JobParameters or ExecutionContext is evaluated too early when creating singletons.

**Using a stateful reader/writer as a singleton.** Multiple executions can share checkpoints or resources.

**Calling a scoped bean outside a Step.** There is no active StepExecution to create the target.

**Declaring only ItemReader/ItemWriter as the return type.** The framework may fail to detect the implementation's ItemStream lifecycle. Use a stream-aware or concrete type.

**Thinking scope automatically persists checkpoints.** Step scope manages instances; ItemStream and ExecutionContext persist recoverable state.

**Confusing Job scope with Step scope.** Job scope binds to a JobExecution, whereas reader/writer checkpoints belong to a StepExecution.

**Sharing one reader across partitions.** Workers can overwrite parameters and state. Create separate targets per StepExecution.

**Assuming a step-scoped bean is dedicated per thread.** A StepExecution can have multiple threads and the target bean can still be shared depending on execution configuration.

**Wrapping an ItemStream delegate without registering lifecycle callbacks.** Child readers/writers may not receive open/update/close callbacks.

**Changing reader/writer names on restart.** Old ExecutionContext keys may no longer be restored as expected.

## 20. Testing Step-Scoped Readers and Writers

You can test scoped beans with Spring Batch Test. Tests must create a StepExecution context so the proxy can instantiate the target and resolve late-bound values.

Example using StepScopeTestUtils:

~~~java
@Test
void readerUsesInputFileFromJobParameters() throws Exception {
    StepExecution stepExecution =
            MetaDataInstanceFactory.createStepExecution();

    StepScopeTestUtils.doInStepScope(stepExecution, () -> {
        FlatFileItemReader<Order> reader =
                applicationContext.getBean("orderReader",
                        FlatFileItemReader.class);

        reader.open(new ExecutionContext());
        Order first = reader.read();
        reader.close();

        assertNotNull(first);
        return null;
    });
}
~~~

This is an illustrative example of activating Step scope in a test; it requires a configured ApplicationContext bean and a matching fixture file. If values are injected from JobParameters, create a JobExecution with the required parameters before running the test.

You can use StepScopeTestExecutionListener or the corresponding utility for your Spring Batch Test version. Verify the exact package/API in the version in use.

Scenarios to verify:

- JobParameters are injected properly into the reader/writer.
- Job ExecutionContext is read properly.
- Partition Step ExecutionContext is read properly.
- Two different StepExecutions receive separate target instances and states.
- ItemStream open/update/close callbacks are invoked.
- Checkpoints are saved and restored on restart.
- Readers/writers are not invoked outside scope.
- Multi-threaded Steps do not access state unsafely.

## 21. Process for Deciding Whether a Reader/Writer Needs Step Scope

When declaring a reader or writer, check in order:

1. Does the component need JobParameters, Job ExecutionContext, or Step ExecutionContext? If yes, use Step scope to late-bind.
2. Does the component hold mutable per-run state? If yes, use a separate target per StepExecution.
3. Does the component hold open files, cursors, connections, or resources? Inspect the lifecycle and avoid sharing instances.
4. Does the component implement ItemStream? Ensure the framework recognizes and calls open/update/close.
5. Does the component run under partitioning? Each worker needs its own context.
6. Does the Step run multi-threaded? Verify thread safety; scope does not automatically create per-thread instances.
7. Is the bean called before the Step starts? Avoid dereferencing scoped proxies outside the lifecycle.
8. Must state survive restart? Save checkpoints via ExecutionContext and keep component names and keys stable.
9. Are there delegates/composites? Register all ItemStream delegates properly.
10. Test at least two StepExecutions with different parameters to verify no state is shared.

@StepScope is especially useful for readers and writers that are stateful or depend on runtime data. It gives each StepExecution its own target bean and enables late binding from JobParameters, Job ExecutionContext, or Step ExecutionContext. Combining Step scope with ItemStream, checkpointing, and proper concurrency configuration lets readers and writers run independently across executions and recover cleanly when a Job restarts.

