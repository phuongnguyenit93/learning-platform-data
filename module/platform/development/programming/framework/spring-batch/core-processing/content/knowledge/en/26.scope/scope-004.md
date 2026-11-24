# Job-Scoped Beans

In Spring Batch, a bean sometimes needs to live across multiple steps of the same job run. For example, multiple steps may need the same report export configuration derived from `JobParameters`, a client configured per tenant, or an object providing paths and options dedicated to the current run.

If a regular singleton is used, the bean could be shared across multiple concurrent job executions. If `@StepScope` is used, each step execution gets a separate instance even when some configuration needs to be shared across multiple steps. **`@JobScope`** solves this case by creating one bean instance per `JobExecution` and keeping that instance throughout the corresponding execution's lifecycle.

Job scope also supports late binding: values from `JobParameters` and `JobExecutionContext` are injected into the bean when the bean is actually created while the job is running. However, a job-scoped bean only manages dependency lifecycle. It does not replace `ExecutionContext`, does not automatically persist state across restarts, and does not make mutable fields safe when accessed concurrently by multiple flows.

## 1. Three Common Bean Scopes

Spring Batch provides important scopes for creating beans aligned with the execution lifecycle:

| Scope | Instance lifecycle | Suitable cases |
|---|---|---|
| Singleton | One instance in the application context | Stateless services, repositories, shared mappers |
| `@StepScope` | One instance per `StepExecution` | Readers/writers holding cursors, checkpoints, or step-specific state |
| `@JobScope` | One instance per `JobExecution` | Configuration or collaborators shared across multiple steps in the same job execution |

For example, a job with three steps:

```text
dailyExportJob
  JobExecution 101
    prepareStep
    exportCustomersStep
    exportOrdersStep
```

A `@JobScope` bean is created at most once for `JobExecution 101` and can be used by the steps in that execution. If the same job runs concurrently for another business date, the second execution has its own job-scoped instance.

Each step execution can still have its own `@StepScope` beans. The two scopes serve different lifecycles and can be used together in a job.

## 2. Job Scope Is Created per JobExecution

`JobInstance` and `JobExecution` are not the same concept:

- `JobInstance` represents a logical unit of business work, identified by job name and identifying `JobParameters`.
- `JobExecution` represents a specific execution attempt of that instance.

Job scope is bound to an active run, namely a `JobExecution`. If an execution fails and is restarted, Spring Batch creates a new `JobExecution` for the same `JobInstance`. The `@JobScope` bean is created anew for the new execution.

```text
JobInstance: dailyExportJob / businessDate=2026-11-15

  JobExecution 101 (FAILED)
    Job-scoped bean instance A
    prepareStep
    exportStep

  JobExecution 108 (restart, COMPLETED)
    Job-scoped bean instance B
    resumes from saved metadata/checkpoint
```

Instance B is not object A retained in memory. If state must be restored after a restart, store the necessary state in `ExecutionContext` or a durable store. Do not rely on fields of a job-scoped bean to remember progress across executions.

## 3. When Should You Use `@JobScope`?

Job scope is appropriate when a bean needs per-job-execution configuration and is used by multiple steps within that execution.

Common examples:

- A `JobRunSettings` holding business date, tenant, and output directory taken from job parameters.
- A collaborator configured for the current run's input file or output version.
- A service wrapper holding immutable configuration shared across multiple steps.
- A bean reading a value from the job execution context after an earlier step has prepared and stored it.
- An object generating consistent output keys or resource paths within the same execution.

Do not use job scope merely because a bean is called from a job. Stateless services such as mappers, pure validators, or repositories can usually be singletons. Readers with cursors, writers with write positions, or components needing step-specific state usually fit `@StepScope` better.

## 4. Declaring a Bean with `@JobScope`

You can place `@JobScope` on a `@Bean` method so the bean is created per job execution.

Example of a class holding export configuration:

```java
public class JobRunSettings {

    private final String businessDate;
    private final Long tenantId;
    private final String outputDirectory;

    public JobRunSettings(
            String businessDate,
            Long tenantId,
            String outputDirectory) {
        this.businessDate = businessDate;
        this.tenantId = tenantId;
        this.outputDirectory = outputDirectory;
    }

    public String getBusinessDate() {
        return businessDate;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getOutputDirectory() {
        return outputDirectory;
    }
}
```

Bean declaration:

```java
@Bean
@JobScope
public JobRunSettings jobRunSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") Long tenantId,
        @Value("#{jobParameters['outputDirectory']}") String outputDirectory) {

    return new JobRunSettings(businessDate, tenantId, outputDirectory);
}
```

When a job execution is active and the bean is used for the first time, Spring creates the target instance with the values of the current execution. Another execution receives a separate target instance with its own parameter set.

In real applications, validate required parameters before use. If `tenantId` or the output path is missing, throw a clear configuration error rather than letting an error appear late in a writer.

## 5. Late Binding with JobParameters

Late binding means values are resolved when the scoped bean is created during execution, rather than at application context startup.

Example:

```java
@Bean
@JobScope
public JobRunSettings jobRunSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") Long tenantId,
        @Value("#{jobParameters['outputDirectory']}") String outputDirectory) {
    return new JobRunSettings(businessDate, tenantId, outputDirectory);
}
```

Expressions reading parameters of the running job execution:

| Expression | Value |
|---|---|
| `#{jobParameters['businessDate']}` | Job parameter named `businessDate` |
| `#{jobParameters['tenantId']}` | Job parameter named `tenantId` |
| `#{jobExecution}` | Current `JobExecution` |
| `#{jobExecutionContext['preparedInputFile']}` | Value in the job execution context |

`JobParameters` describe the inputs of a run, and identifying parameters help determine `JobInstance`. Job parameters are not a place to update processing progress. If you need to store values generated while the job runs, use the job execution context or step execution context appropriately.

## 6. Injecting a Job-Scoped Bean into a Singleton

Default `@Bean` beans are usually singletons. A singleton can depend on a job-scoped bean, but Spring must use a scoped proxy to defer obtaining the target until an active job context exists.

Example of a singleton tasklet using `JobRunSettings`:

```java
@Bean
public Tasklet prepareExportTasklet(JobRunSettings settings) {
    return (contribution, chunkContext) -> {
        Path outputDirectory = Path.of(settings.getOutputDirectory());
        Files.createDirectories(outputDirectory);
        return RepeatStatus.FINISHED;
    };
}
```

When Spring creates the singleton tasklet, the injected dependency is a proxy for the job-scoped bean. When the tasklet actually calls `settings.getOutputDirectory()` inside a running job execution, the proxy looks up the target instance corresponding to that execution.

Do not call methods on the proxy while the application context is initializing when no job execution exists yet. At that moment there is no job context to resolve the target, and the application may throw an error like `ScopeNotActiveException` or an equivalent exception.

## 7. Configuring a Job Using a Job-Scoped Bean

A more complete example with a tasklet using execution-scoped configuration:

```java
@Configuration
public class DailyExportConfiguration {

    @Bean
    @JobScope
    public JobRunSettings jobRunSettings(
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['tenantId']}") Long tenantId,
            @Value("#{jobParameters['outputDirectory']}") String outputDirectory) {
        return new JobRunSettings(businessDate, tenantId, outputDirectory);
    }

    @Bean
    public Tasklet prepareExportTasklet(JobRunSettings settings) {
        return (contribution, chunkContext) -> {
            Path directory = Path.of(settings.getOutputDirectory());
            Files.createDirectories(directory);
            return RepeatStatus.FINISHED;
        };
    }

    @Bean
    public Step prepareExportStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet prepareExportTasklet) {
        return new StepBuilder("prepareExportStep", jobRepository)
                .tasklet(prepareExportTasklet, transactionManager)
                .build();
    }

    @Bean
    public Job dailyExportJob(
            JobRepository jobRepository,
            Step prepareExportStep) {
        return new JobBuilder("dailyExportJob", jobRepository)
                .start(prepareExportStep)
                .build();
    }
}
```

The example uses the Spring Batch 5 builder API. Imports and infrastructure configuration such as `@EnableBatchProcessing`, datasource, transaction manager, and `JobRepository` are omitted to focus on job scope.

In an application, ensure parameters are passed when launching the job and the bean is only accessed while an execution is active.

## 8. Reading Data from JobExecutionContext

Besides job parameters, a job-scoped bean can receive values from `JobExecutionContext`. This is useful when an earlier step produces a value to be shared by later steps.

For example, an input-preparation step saves the path into the job context:

```java
public class PrepareInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = chunkContext
                .getStepContext()
                .getStepExecution()
                .getJobExecution();

        jobExecution.getExecutionContext()
                .putString("preparedInputFile", "staging/orders-input.csv");

        return RepeatStatus.FINISHED;
    }
}
```

A job-scoped bean used in a subsequent step can late-bind this value:

```java
@Bean
@JobScope
public PreparedInputSettings preparedInputSettings(
        @Value("#{jobExecutionContext['preparedInputFile']}") String inputFile) {
    return new PreparedInputSettings(inputFile);
}
```

An important detail is that the job-scoped target is created when first accessed and retained for the execution. Therefore, if the bean is initialized before the `preparedInputFile` key is written, the injected field will not automatically update when the context changes. Ensure the bean is first used only after the preparation step has saved the key, or read the value dynamically from `JobExecution` when needed.

For data that must survive restarts, ensure the job execution context is updated and persisted via `JobRepository` according to the step lifecycle. Changing a field on a job-scoped bean does not automatically update the execution context.

## 9. Job Scope Is Not ExecutionContext

These two mechanisms serve different purposes:

| Criterion | `@JobScope` | `ExecutionContext` |
|---|---|---|
| Nature | Bean lifecycle and scope | Key/value store for execution state |
| How long does data live? | During the active JobExecution | Persisted durably in the metadata repository |
| Shared across multiple steps? | Yes, target bean is shared within execution | Job context can be used across steps |
| Survives restart? | No, target bean is recreated | Yes, if the context was saved |
| Example | Per-tenant export configuration | `lastProcessedId`, generated output path |

Do not use a field such as `settings.lastProcessedId` to replace a checkpoint. When the process stops, objects on the heap are lost. Store checkpoints in the step execution context or another durable mechanism.

## 10. Distinguishing JobScope and StepScope

`@JobScope` and `@StepScope` are often used together, yet they do not replace each other.

For example, an import job with two steps:

```text
importJob
  validateStep
  importStep
```

A `JobRunSettings` containing `businessDate` and `tenantId` can be shared by both steps, so it fits job scope. A `FlatFileItemReader` holding line count and file pointer belongs only to `importStep`, so it fits step scope.

Example:

```java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    FlatFileItemReader<OrderInput> reader = new FlatFileItemReader<>();
    reader.setName("orderReader");
    reader.setResource(new FileSystemResource(inputFile));
    reader.setSaveState(true);
    reader.setLineMapper(orderLineMapper());
    return reader;
}
```

This reader has state specific to its `StepExecution` and supports checkpointing. There is no need to make the reader job-scoped simply because the input path comes from a job parameter; `@StepScope` can still late-bind `jobParameters`.

Practical rules:

- Use `@JobScope` for configuration or collaborators with a job-execution-wide lifecycle.
- Use `@StepScope` for state tied to a single step execution, especially readers/writers.
- Use singleton for stateless and thread-safe components.
- Use `ExecutionContext` to store state that must be recovered after restart.

## 11. Job-Scoped Beans Are Not Thread-Safe by Default

A job execution can contain parallel flows or steps using multiple threads. Because a job-scoped bean is shared within the execution, multiple branches can access the same target instance.

If the bean holds only immutable configuration such as business date, tenant ID, and output directory, sharing is usually straightforward. However, if the bean has mutable fields such as counters, lists, buffers, or current items, threads can update them concurrently and cause race conditions.

Unsafe example:

```java
@JobScope
public class JobRunState {
    private final List<String> processedIds = new ArrayList<>();

    public void add(String id) {
        processedIds.add(id);
    }
}
```

If multiple flows call `add()` at the same time, `ArrayList` is not thread-safe. Switching to a concurrent collection still does not solve checkpointing, business ordering, or durability across restarts.

Keep job-scoped beans effectively immutable. Place per-step state in the step execution context or a transactional store; write aggregated data under distinct keys and combine them after the flows complete.

## 12. Limitations of Job Scope in Parallel or Partitioned Steps

Spring Batch has practical limitations when using job scope in multi-threaded steps or partitioned steps. These mechanisms can spawn threads or execution workers where the framework does not set up the job context the way a job-scoped proxy expects on every thread. Therefore, do not assume a job-scoped bean can be safely accessed from every application-spawned thread.

Exercise particular caution with:

- Steps running with multiple threads.
- Partition workers executed via a `TaskExecutor`.
- Remote workers or separate processes.
- Parallel flows using an asynchronous executor.
- Threads manually created inside a processor or writer.

When workers need configuration, consider passing data via `StepExecution`/`ExecutionContext`, creating separate `@StepScope` beans per worker step, or using immutable configuration explicitly created and passed. Verify support for your Spring Batch version and specific executor model before using job scope in parallel execution paths.

Do not use a job-scoped bean as a shared area to synchronize workers. If data must be shared, use a database, message broker, or explicitly designed concurrency structure.

## 13. Job Scope Is Not Transaction Scope

A job-scoped bean can live across multiple transactions and multiple steps within the same job execution. The fact that the bean remains alive does not mean a database transaction stays open throughout that time.

For example, `JobRunSettings` may be used in `prepareStep`, `importStep`, and `summaryStep`. Each step/chunk still has its own transaction according to configuration. Do not retain a JDBC connection or transaction-bound resource in a field of a job-scoped bean for use across steps.

Let `JdbcTemplate`, repositories, or transaction-aware collaborators acquire resources from the active transaction. Do not store `Connection`, `ResultSet`, Hibernate sessions, or long-lived file handles inside a job-scoped configuration bean unless resource lifecycles are explicitly and appropriately managed.

## 14. Lazy Initialization and Errors When Accessed Outside a Job

A job-scoped target can only be created when Spring Batch has registered an active job context. Consequently:

- The application context can create the proxy at startup without instantiating the target bean yet.
- The target is created when the proxy is invoked inside a job execution.
- Calling the proxy from a `CommandLineRunner`, controller, or test without a job context can cause a scope-not-active error.
- Calling the proxy in a singleton's constructor or `@PostConstruct` can happen too early.

If a component needs to read configuration before a job runs, use singleton configuration or read `JobParameters` in the launcher/service and pass them at launch time. Do not try to access a job-scoped target outside the job lifecycle.

## 15. Proxies and Bean Class Types

`@JobScope` typically uses scoped proxies so shorter-lived beans can be injected into singleton beans. With class-based proxies, the target class must be proxyable; `final` classes or `final` methods can cause issues with CGLIB.

Recommendations:

- Return the concrete class type from `@Bean` methods when class proxying is needed.
- Avoid `final` classes or `final` methods that need to be proxied.
- Avoid internal self-invocation that bypasses the proxy if logic depends on the scope.
- Do not instantiate the target yourself with `new` and expect Spring to manage job scope.
- Use Spring-managed beans and inject proxies via dependency injection.

The `JobRunSettings` example above is a plain class with non-`final` getters, suitable for class-based proxying. If an application chooses interface-based proxying, keep configuration and injected types consistent.

## 16. Enabling Job Scope in Spring Batch Infrastructure

In annotation-based Spring Batch configuration, `@EnableBatchProcessing` registers the required infrastructure, including batch scopes such as job scope and step scope. Spring Boot with Batch auto-configuration also typically sets up the corresponding infrastructure.

Example:

```java
@Configuration
@EnableBatchProcessing
public class BatchInfrastructureConfiguration {
    // JobRepository, transaction manager, and related batch configuration.
}
```

Do not register duplicate scopes or create your own `JobScope` if the infrastructure already provides one. If an application uses custom Batch configuration, verify that `JobScope` is registered in the application context.

When job scope configuration does not work, check:

- Is Spring Batch infrastructure enabled properly?
- Is the bean managed by Spring via `@Bean`/component scan?
- Is `@JobScope` placed on the right bean definition?
- Is the bean instantiated or invoked before a job context is active?
- Is the job launched via `JobLauncher` with the execution context registered properly?

## 17. Using JobExecutionContext Dynamically

A job-scoped bean can receive context via `@Value`, yet because the target is created only once per execution, the injected value is whatever existed when the target was initialized. If the key changes afterward, the field does not update automatically.

For values only produced after a step, there are two approaches:

1. Ensure the job-scoped bean is initialized for the first time in a step after the key has been written to the job context.
2. If you need to read a value that changes over time, access `JobExecution`/`ExecutionContext` inside the method when used rather than snapshotting via constructor injection.

Example of reading context dynamically in a tasklet:

```java
public class ReadPreparedInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = chunkContext
                .getStepContext()
                .getStepExecution()
                .getJobExecution();

        String inputFile = jobExecution.getExecutionContext()
                .getString("preparedInputFile");

        // Use inputFile for the current step.
        return RepeatStatus.FINISHED;
    }
}
```

If a value must be used across multiple steps, consider `ExecutionContextPromotionListener` when the data starts in the step context. Job context is the right scope for values shared at the job level.

## 18. Job-Scoped Beans and Restart

When a job restarts, a new `JobExecution` is created for the same `JobInstance`. The `@JobScope` bean of the old execution has ended its lifecycle, and a new target will be created for the new execution.

Values derived from identifying `JobParameters` will normally be the same when restarting the same instance. However, mutable fields modified by the application in the old target are not restored automatically.

For example:

- `businessDate` from a job parameter: can be resolved again with the same value on restart.
- `lastProcessedId` stored in a bean field: lost when the old execution ends.
- `lastProcessedId` stored in `StepExecutionContext`: can be restored from the committed checkpoint.
- `preparedInputFile` stored in `JobExecutionContext`: can be read again if metadata was persisted.

Thus, job scope isolates configuration and objects per execution, while `ExecutionContext` is responsible for storing state needed for restart. Both mechanisms should be used for their intended purposes.

## 19. Testing Job-Scoped Beans

Testing job scope requires an active job context. If you invoke a `@JobScope` proxy directly in a unit test without setting up the scope, the test may fail with no active job context.

Spring Batch Test provides utilities to create a job execution context in tests. You can use `@SpringBatchTest` together with `JobLauncherTestUtils` to run a real job in a test configuration.

Example testing a job-scoped settings bean through a job:

```java
@SpringBatchTest
@SpringJUnitConfig(DailyExportConfiguration.class)
class JobScopedSettingsTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void usesParametersForCurrentJobExecution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .addLong("tenantId", 42L, true)
                .addString("outputDirectory", "build/test-output", false)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

This is an illustrative skeleton; the test configuration must supply the job and appropriate test infrastructure. To verify actual settings values, a tasklet can record the resolved values into a test probe, or the test can verify artifacts generated according to the parameters.

For tests focused on the scope without running the whole job, Spring Batch Test provides `JobScopeTestUtils.doInJobScope(...)` in supported versions. It can execute a callback within a constructed test `JobExecution`. Follow the API signature of the test library version in use.

## 20. Testing Isolation Between Two JobExecutions

An important goal of job scope is preventing one job's configuration from leaking into another job.

You can verify:

1. Launch the job with `tenantId=42` and output directory A.
2. Confirm the bean uses the exact values of the first execution.
3. Launch another execution with `tenantId=84` and output directory B.
4. Confirm the second execution receives a separate target bean and its own values.
5. Confirm no mutable state from the first execution remains in the subsequent execution.

If two jobs run concurrently, inspect both executions to catch singleton state accidentally holding per-job parameters. This is one reason to put per-execution configuration in a job-scoped bean rather than a singleton service's fields.

## 21. Common Mistakes

| Situation | Cause | Resolution |
|---|---|---|
| `ScopeNotActiveException` | Proxy called outside a job execution or too early | Only access target while the job is running |
| `@Value` value is null | Wrong job parameter/context key name or key did not exist when target was created | Check key names and initialization timing |
| Bean is not recreated on restart | Mistakenly assuming job scope lives per JobInstance | Remember scope is bound to the new JobExecution |
| Field state lost after restart | Using bean fields instead of ExecutionContext | Persist checkpoints in context or a durable store |
| Two steps overwrite each other's state | Using job scope for state that actually belongs to a step | Switch to `@StepScope` or separate step contexts |
| Two flows update the same field causing a race | Job-scoped bean is shared yet mutable | Keep bean immutable or use a durable/thread-safe design |
| Worker thread fails to resolve job scope | Job context is not established on that thread/worker | Avoid job scope in unsupported parallel paths; pass context explicitly |
| Proxy does not work on a final class | Class/method cannot be CGLIB proxied | Use a proxyable class or an appropriate interface proxy |
| Singleton holds job-scoped target too early | Calling proxy method in constructor or `@PostConstruct` | Only dereference within the execution lifecycle |
| Stale context value still used | Bean was created before the context key changed | Initialize after the key is available or read context dynamically |

## 22. Practical Design Rules

When deciding which scope to use, look at the data's lifecycle:

1. Is the value identical across the entire application? If yes, singleton is usually suitable.
2. Is the value specific to a job execution and needed across multiple steps? Consider `@JobScope`.
3. Is the value specific to a step execution, such as a cursor or output position? Use `@StepScope`.
4. Must the value survive a restart? Store it in `ExecutionContext` or a durable store.
5. Can the bean be accessed concurrently by multiple threads? Keep configuration immutable or design concurrency explicitly.
6. Is the value produced after the job starts? Check when the job-scoped target gets initialized.

An easy-to-operate design is typically:

- Singleton for stateless services and repositories.
- Job-scoped beans for immutable job configuration.
- Step-scoped beans for readers/writers with dedicated state.
- Job/step execution context for checkpoints and recoverable data.
- Database/outbox for business state that must be durable or shared across workers.

## 23. Principles to Remember

- `@JobScope` creates one target bean per running `JobExecution`.
- Restarts create a new `JobExecution`, so job-scoped targets are recreated even though `JobInstance` remains the same.
- Job scope fits configuration/collaborators shared across multiple steps in the same execution.
- `@Value` supports late binding from `jobParameters`, `jobExecution`, and `jobExecutionContext`.
- Scoped proxies allow injecting job-scoped beans into singletons; only invoke targets when a job context is active.
- `@JobScope` manages bean lifecycle, does not persist state durably, and does not replace `ExecutionContext`.
- Use `@StepScope` for state specific to a reader/writer or a single step execution.
- Mutable fields in job-scoped beans can be accessed by multiple flows/threads; prefer immutable configuration.
- Be cautious with job scope in multi-threaded or partitioned steps because the job context is not automatically established on every worker thread.
- If binding `jobExecutionContext` when the target is created, the injected value is a snapshot at that time; later key changes do not update fields automatically.
- Do not retain connections, cursors, or transactions inside a bean just because the bean lives for the entire job.
- Test the scope inside a real job execution or using JobScopeTestUtils appropriate for your version.

`@JobScope` helps steps within the same run share per-execution configuration without mixing parameters across concurrent jobs. By keeping job-scoped beans for immutable configuration, using step scope for local state, and storing checkpoints in `ExecutionContext`, applications can leverage Spring Batch's lifecycle properly while remaining restart-safe and operationally reliable.
