# JobScope and StepScope

In Spring Batch, **JobScope** and **StepScope** are two scopes that create beans aligned with the execution lifecycle of a Job or a Step. They are especially useful when a bean needs data that is only available when a Job starts, such as JobParameters, the Job ExecutionContext, or the Step ExecutionContext.

These two scopes solve a common problem: beans declared in the Spring ApplicationContext are typically singletons created before the Job runs, whereas execution-specific data only exists after Spring Batch creates a JobExecution or StepExecution.

- **JobScope** creates one target bean per JobExecution. Steps within the same Job run can use that same instance.
- **StepScope** creates one target bean per StepExecution. Each Step execution has its own state and instance.

A practical rule: use JobScope for data or objects shared at the level of a single Job run; use StepScope for a reader, processor, writer, or component that needs Step-specific parameters and state. For a reader that requires late binding, StepScope is usually the right choice.

## 1. Why Are JobScope and StepScope Needed?

Spring creates singleton beans when initializing the ApplicationContext. At that moment the Job may not have run yet, so there are no JobParameters, JobExecution, or StepExecution to inject.

For example, configuring a reader that needs a file path from JobParameters:

~~~java
@Bean
public FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // ...
}
~~~

If the bean is an ordinary singleton, Spring may attempt to resolve the jobParameters expression when the ApplicationContext initializes, before any JobExecution exists. The bean cannot obtain the right runtime data.

When using StepScope:

~~~java
@Bean
@StepScope
public FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // ...
}
~~~

Spring creates a scoped proxy when configuring the application, and then creates the target reader when the StepExecution actually becomes active. At that point JobParameters are ready and the expression can be resolved.

This is the **late binding** mechanism: values are bound to the bean when the corresponding scope is active, rather than at ApplicationContext startup.

## 2. What Is JobScope?

JobScope binds the lifecycle of a target bean to a single JobExecution.

A JobInstance can have multiple JobExecutions if the Job is restarted. Each JobExecution is a specific execution attempt and has its own Job ExecutionContext. A Job-scoped bean is created specifically for that running JobExecution.

~~~text
ApplicationContext
      |
      +--> JobExecution A
      |       |
      |       +--> Job-scoped bean A
      |       |
      |       +--> Step 1
      |       +--> Step 2
      |       +--> Step 3
      |
      +--> JobExecution B (restart)
              |
              +--> Job-scoped bean B
              |
              +--> Step 1
              +--> Step 2
              +--> Step 3
~~~

Steps within the same JobExecution can access the same JobScope target bean. When another JobExecution starts, Spring Batch creates a target bean scoped to the new run.

JobScope is useful when:

- Multiple Steps need the same runtime configuration.
- An object needs to hold shared state within the scope of a JobExecution.
- A bean needs to read JobParameters or the Job ExecutionContext.
- You want to avoid using a mutable singleton to store per-run Job state.

JobScope is not a persistent state store that replaces the JobRepository. If recovery is needed after a process stops, data to be restored must be stored in the ExecutionContext or a durable store. A field in a Job-scoped bean only lives in memory for the current execution.

## 3. Declaring a Bean with @JobScope

Spring Batch provides the @JobScope annotation to declare a bean with job scope.

For example, an object holding import configuration shared across Steps:

~~~java
public record ImportSettings(
        String businessDate,
        String tenantId,
        String mode) {
}
~~~

Bean declaration:

~~~java
@Bean
@JobScope
public ImportSettings importSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['mode']}") String mode) {

    return new ImportSettings(
            businessDate,
            tenantId,
            mode);
}
~~~

Steps can inject ImportSettings:

~~~java
@Bean
public Step validateStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // Uses the configuration of the current JobExecution.
    // ...
}
~~~

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // Uses the same Job-scoped configuration.
    // ...
}
~~~

Each JobExecution receives an ImportSettings resolved from that run's JobParameters. Steps in the same JobExecution can use the same target instance.

If you only need to read JobParameters in a single Step, creating a JobScope bean is not strictly necessary. StepScope is usually simpler and limits the lifecycle more clearly.

## 4. What Is StepScope?

StepScope binds a target bean to a single StepExecution.

A Step can be run across different JobExecutions. Each execution creates its own StepExecution with its own ExecutionContext, state, and counters. A Step-scoped bean is created specifically for that StepExecution.

~~~text
JobExecution
    |
    +--> StepExecution A
    |       |
    |       +--> Step-scoped reader A
    |       +--> Step-scoped processor A
    |
    +--> StepExecution B
            |
            +--> Step-scoped reader B
            +--> Step-scoped processor B
~~~

StepScope fits well for:

- An ItemReader whose resource or query depends on runtime parameters.
- An ItemProcessor that needs Step-specific or partition-specific parameters.
- An ItemWriter that needs a specific output path or write mode.
- A custom component that holds state meaningful only within a single StepExecution.
- A bean that needs to read the Step ExecutionContext or Job ExecutionContext when the Step runs.

For example, a Step reading a specific file:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // Creates the reader for the current run's file.
    // ...
}
~~~

When the Step runs, the reader receives the Resource from JobParameters. When the StepExecution finishes, the StepScope target bean is destroyed according to the scope's lifecycle.

## 5. Declaring a Bean with @StepScope

For example, a reader receiving a file path and a configuration flag:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile,
        @Value("#{jobParameters['skipHeader']}") Boolean skipHeader) {

    FlatFileItemReaderBuilder<CustomerInput> builder =
            new FlatFileItemReaderBuilder<CustomerInput>()
                    .name("customerReader")
                    .resource(inputFile)
                    .delimited()
                    .names("id", "name", "email")
                    .targetType(CustomerInput.class)
                    .saveState(true);

    if (Boolean.TRUE.equals(skipHeader)) {
        builder.linesToSkip(1);
    }

    return builder.build();
}
~~~

Here:

- @StepScope defers creating the target reader until the Step is active.
- jobParameters supplies the inputs for the JobExecution.
- saveState(true) allows the reader to save checkpoints to support restart.
- A stable reader name helps distinguish state in the ExecutionContext.

A StepScope bean can still read JobParameters. The difference is that the target bean's lifecycle is tied to the StepExecution, not the JobExecution.

## 6. Comparing JobScope and StepScope

| Criterion | JobScope | StepScope |
|---|---|---|
| Target bean lifecycle | One JobExecution | One StepExecution |
| Shared across Steps | Yes, within the same JobExecution | No, each StepExecution has its own target |
| Reads JobParameters | Yes | Yes |
| Reads Job ExecutionContext | Yes | Yes |
| Reads Step ExecutionContext | No specific Step to reference | Yes |
| Used for Step-specific reader | Usually not the first choice | Suitable |
| Used for Job-wide shared configuration | Suitable | Each Step gets a separate instance |
| New JobExecution on restart | New target bean | New target bean for the executed StepExecution |
| State in fields | Shared within JobExecution scope | Shared within StepExecution scope |

Choose the scope based on the data range to access and the object's lifecycle. Do not choose JobScope just because a bean needs to read JobParameters; StepScope can also read JobParameters and is usually more appropriate for chunk components.

## 7. Commonly Used SpEL Expressions

Spring Batch provides contexts to late-bind data into beans.

| Expression | Value |
|---|---|
| jobParameters['inputFile'] | Job input parameter |
| jobExecutionContext['key'] | Key in the Job ExecutionContext |
| stepExecutionContext['key'] | Key in the Step ExecutionContext |
| jobExecution | Current JobExecution |
| stepExecution | Current StepExecution |
| stepExecution.stepName | Name of the current Step |
| stepExecution.jobExecutionId | JobExecution ID of the Step |

Example reading a file parameter:

~~~java
@Value("#{jobParameters['inputFile']}")
Resource inputFile
~~~

Reading shared Job state:

~~~java
@Value("#{jobExecutionContext['reportId']}")
Long reportId
~~~

Reading Step-specific state:

~~~java
@Value("#{stepExecutionContext['fromId']}")
Long fromId
~~~

These expressions must be resolved within an active scope. StepScope has the context of both JobExecution and StepExecution, so it can read jobParameters, jobExecutionContext, and stepExecutionContext.

JobScope does not have a specific StepExecution. Do not use a job-scoped bean to read stepExecutionContext.

## 8. Passing Data from JobParameters into StepScope

JobParameters are built before the Job runs:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("mode", "FULL", false)
        .toJobParameters();

JobExecution execution =
        jobLauncher.run(customerImportJob, parameters);
~~~

A StepScope reader can receive those values:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(inputFile)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

If a value identifies an independent unit of work, consider marking it identifying in JobParameters. JobParameters identify the JobInstance; the scope only determines when the bean receives that value.

Do not use fields in JobScope or StepScope to replace identifying parameters. A field inside a bean does not participate in identifying a JobInstance.

## 9. Using StepScope to Read Step ExecutionContext

A Partitioner or a previous Step can write values into the Step ExecutionContext. A worker Step uses StepScope to receive the exact values for its StepExecution.

For example, a reader reading an ID range:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    return buildOrderReader(dataSource, fromId, toId);
}
~~~

Each partition has its own StepExecution context. When worker partition 0 runs, the reader receives the bounds for partition 0; when worker partition 1 runs, the reader receives the bounds for partition 1.

This is a key reason why a partition's reader uses StepScope. If a stateful singleton reader were used, workers could share the same fields and overwrite each other's range or read position.

## 10. Using JobScope for Data Shared Across Multiple Steps

Suppose a Job has three Steps:

1. validateFileStep determines the import configuration.
2. importCustomersStep imports the data.
3. createSummaryStep generates the report.

An immutable configuration object derived from JobParameters can be shared:

~~~java
@Bean
@JobScope
public ImportSettings importSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return new ImportSettings(businessDate, tenantId, "FULL");
}
~~~

The Steps inject this bean:

~~~java
@Bean
public Step validateFileStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // ...
}
~~~

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // ...
}
~~~

~~~java
@Bean
public Step createSummaryStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // ...
}
~~~

The same JobExecution uses the same configuration. If a Job restart creates a new JobExecution, a new JobScope bean is created with the parameters of that run.

Immutable configuration objects should be preferred. If multiple Steps mutate the same Job-scoped mutable object, execution order and concurrency can affect the result.

## 11. Passing Data Between Steps via Job ExecutionContext

JobScope does not automatically transfer every local variable from an earlier Step to a later Step. The standard way to pass durable state between Steps is the Job ExecutionContext.

For example, a report-creation Step writes reportId into the Step ExecutionContext:

~~~java
public class CreateReportTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StepExecution stepExecution = chunkContext
                .getStepContext()
                .getStepExecution();

        stepExecution.getExecutionContext()
                .putLong("reportId", 12345L);

        return RepeatStatus.FINISHED;
    }
}
~~~

Use ExecutionContextPromotionListener to promote the key to the Job ExecutionContext:

~~~java
@Bean
public ExecutionContextPromotionListener reportPromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"reportId"});
    return listener;
}
~~~

Register the listener on the report-creation Step:

~~~java
@Bean
public Step createReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ExecutionContextPromotionListener reportPromotionListener) {

    return new StepBuilder("createReportStep", jobRepository)
            .tasklet(new CreateReportTasklet(), transactionManager)
            .listener(reportPromotionListener)
            .build();
}
~~~

A subsequent Step can read the Job ExecutionContext using StepScope:

~~~java
@Bean
@StepScope
public ItemWriter<ReportRow> reportWriter(
        @Value("#{jobExecutionContext['reportId']}") Long reportId) {
    return new ReportWriter(reportId);
}
~~~

Here StepScope is used because the writer belongs to a specific Step; the expression fetches reportId from the Job ExecutionContext. Promoted data can survive restarts thanks to the JobRepository.

Do not read a previous Step's stepExecutionContext from another Step. Each StepExecution has its own context; to share state, promote it or intentionally update the Job ExecutionContext.

## 12. JobScope and StepScope Are Not Checkpoint Storage

Scopes manage in-memory object lifecycles. ExecutionContext manages state that can be persisted to the JobRepository.

For example, a StepScope bean with a field:

~~~java
@Bean
@StepScope
public ItemProcessor<OrderInput, Order> processor() {
    return new ItemProcessor<>() {
        private long processed;

        @Override
        public Order process(OrderInput input) {
            processed++;
            return convert(input);
        }
    };
}
~~~

The processed field exists in the target bean of the current StepExecution. When the process finishes or the application stops, the field is not automatically persisted for restart.

If a counter needs to be recovered, store it in the Step ExecutionContext or appropriate metadata. If you only need statistics within the current run, a field or a Micrometer counter can be used, provided you understand its lifecycle and concurrency.

Similarly, fields in JobScope are not durable data. Do not use them as checkpoints instead of the ExecutionContext.

## 13. How Do Proxies and Late Binding Work?

When Spring encounters a bean with @JobScope or @StepScope, it creates a scoped proxy so that other beans can inject it before the Job/Step runs.

~~~text
ApplicationContext starts
        |
        v
Create scoped proxy
        |
        v
Step/Job is configured
        |
        v
JobExecution / StepExecution starts
        |
        v
Scope is activated
        |
        v
Proxy looks up or creates target bean
        |
        v
Resolve JobParameters / ExecutionContext
        |
        v
Invoke method on target
~~~

The proxy allows Step configuration to inject a StepScope reader even though the real reader has not been created yet. When the Step executes, the proxy delegates calls to the target bean bound to the current StepExecution.

This also explains why you should not invoke a scoped bean directly while the ApplicationContext is starting up or from a thread without a Batch execution context. When the scope is not active, Spring cannot resolve the target.

The @JobScope and @StepScope annotations typically use class-based proxies. With final classes or non-overridable methods, keep proxy limitations in mind; you can inject via an appropriate interface or design the class as non-final.

## 14. Differences from Singleton and Prototype

| Scope | Lifecycle |
|---|---|
| singleton | One instance per ApplicationContext |
| prototype | New instance each time the container is asked to create the bean |
| job | One target instance per JobExecution |
| step | One target instance per StepExecution |

Singleton is suited for stateless services such as validators or mappers that hold no per-run state.

Prototype does not replace StepScope. Prototype creates an instance when the bean is requested, but it neither binds the instance to a StepExecution nor late-binds JobParameters or ExecutionContext.

JobScope and StepScope understand the context managed by Spring Batch, ensuring target beans are created and destroyed in alignment with the execution lifecycle.

## 15. Can JobScope Be Used for a Reader?

A reader can be declared as JobScope if it is genuinely shared at the JobExecution level and does not need the StepExecution context. However, a reader normally belongs to a single Step and has per-Step state, so StepScope is usually a better fit.

For example, you should not use JobScope for a reader that has per-Step checkpoints:

~~~java
@Bean
@JobScope
public FlatFileItemReader<Customer> customerReader(...) {
    // Reader state could be shared across Steps
    // within the same JobExecution.
}
~~~

If two Steps use this reader, they could access the same target bean and the same state. That easily causes conflicts over read position, open/close lifecycle, or checkpoints.

Use StepScope for each Step's reader. Only use JobScope if the object is truly a Job-level shared resource with a clearly designed lifecycle and concurrency model.

## 16. JobScope in Multi-Threaded and Partitioned Steps

JobScope is useful in sequential Jobs, but requires caution in parallel execution models. Spring Batch warns against using JobScope in multi-threaded or partitioned Steps because the context may not be propagated to threads managed by an executor or distribution mechanism.

A Job-scoped bean may be accessed by multiple workers concurrently. If the bean holds mutable state, workers can overwrite data or encounter race conditions.

With partitioning:

- Each worker has its own StepExecution and Step ExecutionContext.
- Use StepScope to obtain fromId, toId, or the partition key.
- Do not use JobScope to hold per-partition state.
- Only share a JobScope object when the object is concurrency-safe and the scope context is supported in the architecture being used.

With a multi-threaded Step, multiple threads can process the same StepExecution. StepScope does not automatically create one bean per thread; the target bean is bound to the StepExecution and can be shared among threads in that Step. Stateful readers or processors must be thread-safe or use an appropriate partitioning design.

Do not assume a scoped proxy automatically makes a bean thread-safe. The scope only manages lifecycle and target lookup; it provides no synchronization for mutable fields.

## 17. Which Beans Should Have @StepScope?

Beans that are typically good candidates for StepScope:

| Bean | When to use StepScope |
|---|---|
| ItemReader | Resource, query, or partition range depends on runtime; stateful reader |
| ItemProcessor | Processing rules depend on Step-specific parameters |
| ItemWriter | Specific output path, batch ID, or write configuration |
| Tasklet | Logic needs late-bound parameters or Step state |
| Listener | Needs to read StepExecution/ExecutionContext when the Step runs |

There is no need to put @StepScope on every bean. Shared stateless services can remain singletons for simplicity and to save object allocations.

For example, a stateless processor that only calls a service:

~~~java
@Bean
public ItemProcessor<OrderInput, Order> orderProcessor(
        OrderValidationService validationService) {
    return input -> {
        validationService.validate(input);
        return convert(input);
    };
}
~~~

If the processor does not need runtime data or per-Step state, an ordinary singleton is sufficient.

## 18. Which Beans Should Have @JobScope?

JobScope fits configuration or coordination objects shared across Steps within a JobExecution.

Examples:

- ImportSettings containing business date, tenant, and mode.
- ReportContext holding a shared report code within a JobExecution.
- Job-level configuration resolved from JobParameters.
- An immutable object aggregating input parameters.

Do not use JobScope for:

- A reader with a Step-specific read position.
- Partition-specific state.
- Mutable caches without concurrency control.
- Data that must survive restart but is held only in fields.
- A bean that needs to access stepExecutionContext.

If data must be shared across Steps and survive restarts, store it in the Job ExecutionContext or a database; JobScope only provides an in-memory instance.

## 19. Scope Not Active Errors

If a scoped bean is accessed when there is no current JobExecution or StepExecution, Spring may report an error similar to:

~~~text
Scope 'step' is not active for the current thread
Scope 'job' is not active for the current thread
~~~

Common causes:

- Calling a StepScope bean in the constructor or @PostConstruct of a singleton.
- Calling a scoped bean from an application startup listener before the Job runs.
- Spawning a custom thread and accessing a scoped bean without a Batch context.
- Unit tests calling a bean without activating StepScope or JobScope.
- Using JobScope in a parallel topology that does not propagate the context.

How to handle it:

1. Only access scoped beans within the Job/Step lifecycle.
2. Inject the scoped proxy instead of manually retrieving the target before the scope is active.
3. Use StepScope for Step-specific data.
4. For worker threads or partitions, verify how the execution context is propagated.
5. In tests, activate the scope using Spring Batch test support or create an appropriate StepExecution/JobExecution.

Do not create a custom static holder to keep a global JobExecution or StepExecution. That approach can mix contexts across concurrent runs.

## 20. Testing JobScope and StepScope

When testing scoped beans, you need to create the corresponding execution context. Spring Batch test support provides listeners to activate the scope in tests.

For Spring Batch configuration tests, you can use @SpringBatchTest:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchConfiguration.class)
class CustomerReaderScopeTest {

    @Autowired
    private ItemReader<CustomerInput> customerReader;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "/tmp/customers.csv", true)
                .toJobParameters();

        JobExecution jobExecution =
                new JobExecution(1L, parameters);

        StepExecution stepExecution =
                new StepExecution("importStep", jobExecution);

        stepExecution.getExecutionContext()
                .putString("source", "test");

        return stepExecution;
    }

    @Test
    void readerIsAvailableInsideStepScope() throws Exception {
        assertNotNull(customerReader);
        // Can invoke the reader after the scope has been activated.
    }
}
~~~

Spring Batch test support can use the getStepExecution() method to create the context for StepScope. You need to provide an existing test resource if the test actually opens and reads a file.

For JobScope, tests can provide a JobExecution test context via JobScopeTestExecutionListener or run the Job with JobLauncherTestUtils so the scope is activated according to the real lifecycle.

### Testing late binding

You should verify that values are resolved properly:

- JobParameters of the current JobExecution.
- Job ExecutionContext saved before the Step.
- Step ExecutionContext of the current Step.
- Two different JobExecutions receive different target beans.
- Two different StepExecutions receive separate Step-scoped targets.

### Testing restart

If a scoped bean holds state in fields, restart tests should verify that durable state is restored from the ExecutionContext or database. Do not expect fields of an old target bean to survive across a new JobExecution.

## 21. Common Mistakes

### Injecting JobParameters into a singleton

Singletons are created before the Job runs and thus have no runtime context. Use JobScope or StepScope to late-bind.

### Using JobScope for a Step-specific reader

JobScope shares the target within the same JobExecution. The reader can end up sharing state across Steps. Use StepScope for each Step's reader.

### Using StepScope to share an object across Steps

Each StepExecution has its own target. If shared data is needed, use JobScope for an appropriate object or the Job ExecutionContext for state that must be persisted durably.

### Thinking scope is a checkpoint

Fields in a target bean are not automatically persisted on chunk commit. Use ItemStream and the ExecutionContext for reader state.

### Thinking StepScope creates one instance per thread

StepScope creates a target per StepExecution. In a multi-threaded Step, multiple threads can access the target concurrently. Thread safety must be handled.

### Thinking JobScope is safe in every partition topology

Context may not be propagated properly to worker threads or processes. Use StepScope for partition-specific state and test the topology.

### Accessing a scoped bean before the scope is active

The bean has no current JobExecution/StepExecution to resolve against. Only use it within the appropriate lifecycle.

### Storing shared mutable state in JobScope

Multiple Steps or workers can mutate state concurrently. Prefer immutable objects or synchronized, durable state storage.

### Using prototype instead of StepScope

Prototype does not provide late binding or a StepExecution-bound lifecycle. Use Spring Batch scopes when an execution context is needed.

## 22. Process for Choosing a Scope for a Bean

When declaring a bean in Spring Batch, ask:

1. Does the bean need JobParameters or ExecutionContext?
2. Does the bean belong to a JobExecution or a StepExecution?
3. Do multiple Steps in the same Job need to use the same target instance?
4. Does the bean hold state that varies per run?
5. Is that state only needed in memory or must it be recovered after restart?
6. Will the bean be accessed from multiple threads or partitions?
7. Can the bean be a stateless singleton?

You can use the following rules:

| Need | Choice |
|---|---|
| Stateless service, no runtime context needed | singleton |
| Shared configuration for one JobExecution | JobScope |
| Reader/processor/writer specific to one StepExecution | StepScope |
| Input parameters known at launch | JobParameters, injected via scope if needed |
| Reader-specific checkpoint | Step ExecutionContext and ItemStream |
| Data needed by a later Step | Job ExecutionContext or promotion |
| Per-partition state | StepScope in the worker Step |

JobScope and StepScope help beans receive data at the right time and have lifecycles aligned with Spring Batch. JobScope binds a target bean to a JobExecution and allows sharing across Steps of that run. StepScope binds a target bean to a StepExecution, making it suitable for readers and components that need Step-specific state or parameters. Use ExecutionContext for durable checkpoints, use JobParameters for Job inputs, and always consider concurrency when scoped beans are accessed from multiple workers.
