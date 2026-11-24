# Out-of-Scope Bean Errors

In Spring Batch, certain beans can only be instantiated or used while the corresponding JobExecution or StepExecution is active. For example, a reader needs to fetch a filename from JobParameters or an ID range from StepExecutionContext. If the bean is declared as a regular singleton yet accesses data that only exists in Job/Step scope, the application may fail during bean initialization, on method invocation, or when running the Job.

This category of errors typically appears when using late binding without placing the bean in the right scope. Spring Batch provides **@StepScope** and **@JobScope** to defer creating the target bean until the proper execution time and bind the bean's lifecycle to a StepExecution or JobExecution.

Understanding scopes helps prevent errors like **Scope 'step' is not active for the current thread**, prevent using wrong parameters across runs, and avoid sharing reader/writer state across StepExecutions.

## 1. Why Can a Bean Be Out of Scope?

Spring manages beans according to scope. Scope determines when a bean is created, how long it lives, and the boundary within which an instance is shared.

Common scopes:

| Scope | Lifecycle |
| --- | --- |
| singleton | One instance per bean definition in a Spring ApplicationContext |
| prototype | Creates a new instance each time the container is asked for the bean |
| request/session | Bound to an HTTP request or session in web applications |
| step | One target bean for an active StepExecution |
| job | One target bean for an active JobExecution |

In a standard Spring application, singletons are created when the ApplicationContext initializes or when the bean is first requested. At that point, JobExecution and StepExecution may not exist yet.

For example, a reader needing to read `inputFile` from JobParameters:

~~~java
@Bean
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(OrderInput.class)
            .build();
}
~~~

The bean above defaults to singleton. Spring may have to resolve the jobParameters expression before any active JobExecution exists. As a result, no corresponding Job or Step context is found.

Even if the bean manages to initialize, a singleton holds a single value bound at creation time. If the same bean is used across multiple JobExecutions with different inputs, stale values may be reused or one run's state may affect another run.

## 2. Common Symptoms of Out-of-Scope Errors

Some common error messages:

~~~text
Scope 'step' is not active for the current thread
~~~

~~~text
Scope 'job' is not active for the current thread
~~~

~~~text
No context holder available for step scope
~~~

Exact messages may vary by Spring version, Spring Batch version, and how the bean is accessed. The general meaning is that a bean or scoped proxy needs a StepExecution/JobExecution, yet the current thread lacks the corresponding context.

Other symptoms:

- The Job runs in tests yet fails when calling the reader directly from a test method.
- Bean initialization fails at ApplicationContext startup because jobParameters or stepExecutionContext expressions have no values yet.
- Two runs use different inputs yet the reader reuses the same file, tenant, or data range.
- A partition worker reads another partition's range by mistake.
- `@Value` returns null or fails to resolve a key due to the wrong context name or the bean being created outside scope.
- `@StepScope` is declared yet the error still occurs because the target is invoked before the Step starts or on a thread without a Batch context.

Do not simply work around this by catching exceptions or setting default values for every parameter. First determine which bean needs a Job/Step context, who creates the bean, and at what moment the target is invoked.

## 3. Using @StepScope for Beans Depending on StepExecution

@StepScope binds a target bean's lifecycle to a single StepExecution. It is the common choice for a reader, processor, or writer needing:

- stepExecutionContext.
- stepExecution.
- jobParameters used within the Step's scope.
- State specific to a single Step execution.

Fix the reader example by adding @StepScope:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

With this configuration, Spring creates a scoped proxy when the ApplicationContext initializes. The target FlatFileItemReader is created when an appropriate StepExecution is active and JobParameters values can be resolved.

@StepScope is a convenience annotation for step scope with a scoped proxy. Thus, the bean can be injected into Step configuration before the Step runs; the proxy routes calls to the target bound to the current StepExecution.

### Late binding from StepExecutionContext

In a partitioned Step, each worker must receive a dedicated data range:

~~~java
@Bean
@StepScope
public ItemReader<Order> orderRangeReader(
        OrderRepository repository,
        @Value("#{stepExecutionContext['minOrderId']}") Long minId,
        @Value("#{stepExecutionContext['maxOrderId']}") Long maxId) {

    return new OrderRangeReader(repository, minId, maxId);
}
~~~

The Master Step creates distinct ExecutionContexts for each partition. When partition 0's worker runs, the target reader receives partition 0's minOrderId and maxOrderId. Partition 1's worker gets a target reader and context matching partition 1.

If @StepScope is omitted, the reader can be created too early or become a shared singleton, causing partitions to read the wrong range.

## 4. Using @JobScope for Data Bound to JobExecution

@JobScope binds a target bean to a single JobExecution. It fits when a bean needs data shared across the entire Job, such as:

- Job parameters.
- Values in JobExecutionContext.
- State shared at the Job scope and not tied exclusively to one Step.

Example:

~~~java
@Bean
@JobScope
public ImportSettings importSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobExecutionContext['sourceSystem']}") String sourceSystem) {

    return new ImportSettings(businessDate, sourceSystem);
}
~~~

The ImportSettings bean is created for the current JobExecution. Steps belonging to the Job can use the proxy to access the same target within that JobExecution's scope.

Do not use @JobScope to read stepExecutionContext, because that data belongs to a specific StepExecution. If values vary per worker or partition, use @StepScope.

### Choosing Step scope or Job scope?

| Need | Appropriate scope |
| --- | --- |
| Reader needing filename from JobParameters | @StepScope is usually appropriate |
| Reader needing partition min/max IDs | @StepScope |
| Processor needing StepExecution-specific values | @StepScope |
| Bean holding configuration shared across the whole JobExecution | @JobScope |
| Bean needing to read jobExecutionContext | @JobScope or @StepScope if accessed inside a Step |
| Bean needing to read stepExecutionContext | @StepScope |
| Stateless service independent of execution context | regular singleton |

Choose scope based on the data the bean needs and the desired lifecycle, not solely by class category. Not every reader, processor, or writer needs a special scope.

## 5. Scoped Proxies Solve Premature Bean Creation

When a singleton Step configuration injects a @StepScope bean, the Step-scoped target is not created immediately. Spring injects a representative proxy:

~~~text
ApplicationContext initializes
        |
        v
Create scoped proxy for orderReader
        |
        v
Proxy is injected into Step definition
        |
        v
Job starts
        |
        v
StepExecution is created and context is activated
        |
        v
Proxy requests target
        |
        v
Create FlatFileItemReader with current JobParameters
~~~

The proxy allows the bean to be referenced from singleton configuration without instantiating the target too early. When a call passes through the proxy inside a valid scope, Spring looks up or creates the target bound to the current execution.

### Do not invoke the target directly when scope is inactive

Avoid accessing methods of a scoped bean in:

- A singleton bean's constructor.
- A singleton bean's @PostConstruct.
- Configuration logic executed at ApplicationContext initialization time.
- A test calling the reader before creating a StepExecution context.
- A custom-spawned thread lacking a Batch context.

Example to avoid:

~~~java
@Component
public class StartupInspector {

    public StartupInspector(ItemReader<OrderInput> orderReader) {
        // Do not call orderReader.read() here.
        // Step scope is not guaranteed to be active yet.
    }
}
~~~

Injecting the proxy is valid; calling the target before the Job/Step context is established is the problem.

## 6. Distinguishing Scope from Prototype

A common mistaken fix is changing singleton to prototype:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public ItemReader<OrderInput> orderReader(...) {
    // ...
}
~~~

Prototype only asks Spring to create a new instance each time the container is called to retrieve the bean. It does not bind the instance to a StepExecution, does not resolve late-bound values at the right moment, and does not manage open, update, and close lifecycles per Step.

If a singleton receives a prototype via dependency injection, the prototype instance is normally created when the singleton is created and retained by that singleton thereafter. Thus, prototype does not replace @StepScope.

When you need one instance per StepExecution along with context access and lifecycle managed by Spring Batch, use @StepScope.

## 7. Scope Infrastructure Must Be Registered

@StepScope and @JobScope require Spring Batch's scope infrastructure. In an application using standard Batch configuration, the infrastructure is usually registered via Spring Batch configuration, such as @EnableBatchProcessing, or provided by Spring Boot auto-configuration depending on how Batch is configured.

Example Batch configuration:

~~~java
@Configuration
@EnableBatchProcessing
public class BatchInfrastructureConfiguration {
}
~~~

If the application configures infrastructure manually, verify that StepScope and JobScope are registered. When Spring does not recognize the scope, the error typically looks like:

~~~text
No Scope registered for scope name 'step'
~~~

This error differs from Scope 'step' is not active: the first means the scope is not registered in the container; the second means the scope exists yet no active StepExecution context is present at access time.

Do not register duplicate scope beans if the infrastructure already supplies them. Mixing multiple Batch configurations or inconsistently toggling auto-configuration can produce duplicate or missing infrastructure beans.

## 8. Wrong Key or Wrong Context Type Errors

Even when a bean has @StepScope, SpEL must still use the exact context name:

| Expression | Data |
| --- | --- |
| #{jobParameters['inputFile']} | Job parameter |
| #{jobExecutionContext['sourceSystem']} | JobExecutionContext |
| #{stepExecutionContext['minOrderId']} | StepExecutionContext |
| #{jobExecution.jobId} | JobExecution information |
| #{stepExecution.stepName} | StepExecution information |

For example, if the Partitioner writes:

~~~java
context.putLong("minOrderId", 1000L);
~~~

then the reader must read the exact key:

~~~java
@Value("#{stepExecutionContext['minOrderId']}") Long minOrderId
~~~

Common mistakes:

- Writing key minOrderId yet reading minId.
- Writing a value to JobExecutionContext yet reading from StepExecutionContext.
- Using mismatched letter casing in key names.
- Value not yet added to context before the worker starts.
- Incompatible type conversion, such as storing a numeric value as a String while the bean expects Long.

When a key might not exist, clarify whether that is valid or a configuration error. You can use a default value in SpEL for optional cases, but do not set a default for a required partition boundary because that could cause a worker to read the wrong range.

## 9. Do Not Hold Execution State in a Singleton

A singleton bean is shared across the ApplicationContext. Storing JobParameters, StepExecution, file paths, or counters of one run in mutable fields lets concurrent runs overwrite each other's data.

Unsafe example:

~~~java
@Component
public class CurrentImportState {

    private String inputFile;

    public void setInputFile(String inputFile) {
        this.inputFile = inputFile;
    }

    public String getInputFile() {
        return inputFile;
    }
}
~~~

If two JobExecutions run concurrently and both write inputFile, one Job can end up reading the other Job's file.

Choose one of these approaches:

- Put the value in JobParameters if it is a fixed input of the JobInstance.
- Put the value in JobExecutionContext if it is shared state within the JobExecution.
- Put the value in StepExecutionContext if it is specific to a Step or partition.
- Use a @StepScope/@JobScope bean to bind data to the matching execution.
- Keep singleton services stateless and pass parameters via methods.

Do not turn a business service into a scoped bean solely to hold a temporary value when explicit parameter passing works.

## 10. Scope in Multi-Threaded Steps and Partitioning

Scope does not solve every concurrency problem by itself.

### Partitioned Step

Each partition has its own StepExecution. A @StepScope bean is instantiated per partition's StepExecution, so it can bind minOrderId, maxOrderId, or a dedicated file for each worker.

~~~text
Master Step
    |
    +--> partition0 / StepExecution 0
    |       +--> step-scoped reader 0
    |
    +--> partition1 / StepExecution 1
    |       +--> step-scoped reader 1
    |
    +--> partition2 / StepExecution 2
            +--> step-scoped reader 2
~~~

This is the canonical case for using Step scope for readers depending on partition context.

### Multi-threaded Step

In a multi-threaded Step, multiple threads can process a single StepExecution concurrently. @StepScope binds the target to the StepExecution; it does not automatically create one separate target per thread. If a reader, writer, or processor holds mutable state, inspect thread safety and how the framework propagates Batch context to worker threads.

Do not assume adding @StepScope makes a cursor-based reader safe when called concurrently by multiple threads. Use concurrency-safe components, synchronize access, or choose partitioning when a dedicated reader per unit of work is needed.

### Job scope in concurrent processing

@JobScope provides one target per JobExecution. Thus, multiple Steps or workers in the same Job can access that target concurrently. Avoid storing non-thread-safe mutable state in a job-scoped bean if the Job has concurrent branches or workers.

For partition-specific data, prefer Step scope over Job scope. Job scope also has limitations in multi-threaded or partitioned execution because propagating Job context across worker threads is not always guaranteed by the framework in the way applications might expect.

## 11. Bean Scope and the ItemStream Lifecycle

Readers or writers implementing ItemStream need Spring Batch to manage their lifecycle:

- open(ExecutionContext) when the Step starts or restarts.
- update(ExecutionContext) at chunk boundaries to persist checkpoints.
- close() when the Step ends.

If a scoped bean is wrapped by a proxy or decorator, ensure the ItemStream delegate is properly registered with the Step. Standard builders normally detect readers/writers passed directly, yet a custom wrapper might fail to forward the ItemStream lifecycle.

Example of a delegate reader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> delegateReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("delegateReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

If wrapping this reader in a custom decorator, the decorator should implement and forward ItemStream so checkpoints are not lost. A bean with the right scope whose stream lifecycle is never invoked can still restart incorrectly.

## 12. Testing Step-Scoped Beans

A common testing error is calling methods on a scoped bean without setting up a StepExecution context. Tests must activate the scope with a simulated execution or run via Spring Batch test support.

You can use StepScopeTestUtils:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchConfiguration.class)
class OrderReaderTest {

    @Autowired
    private ItemReader<OrderInput> orderReader;

    @Test
    void readsFromInputDefinedByJobParameters() throws Exception {
        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(
                        new JobParametersBuilder()
                                .addString("inputFile", "orders.csv")
                                .toJobParameters());

        OrderInput first = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> orderReader.read());

        assertNotNull(first);
    }
}
~~~

This example illustrates activating Step scope for a call in a test. You must provide an actual resource, reader bean, and fixture matching your project's configuration.

Another approach is using StepScopeTestExecutionListener and a factory method supplying StepExecution:

~~~java
@SpringBatchTest
class ScopedReaderIntegrationTest {

    @Autowired
    private ItemReader<OrderInput> orderReader;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "orders-test.csv")
                .toJobParameters();

        return MetaDataInstanceFactory.createStepExecution(parameters);
    }

    @Test
    void readerIsCreatedInsideStepScope() throws Exception {
        assertNotNull(orderReader.read());
    }
}
~~~

Listener names and how test support is enabled must match the Spring Batch Test version in use. If you test a bean method directly outside the container, @StepScope cannot automatically create a StepExecution context for the test.

## 13. How to Diagnose Out-of-Scope Errors

When encountering scope errors, check in order:

1. **Which bean needs context?** Look for `@Value` with jobParameters, jobExecutionContext, or stepExecutionContext, or code calling StepSynchronizationManager.
2. **What scope does the bean currently have?** If it needs execution-specific data yet is still a singleton, add `@StepScope` or `@JobScope` as appropriate.
3. **When is the target invoked?** Avoid calling it in constructors, `@PostConstruct`, startup callbacks, or before the Job/Step starts.
4. **Is scope infrastructure registered?** Distinguish an unregistered scope error from an inactive scope error.
5. **Does the current thread have a Batch context?** Check executors, manually spawned threads, and the concurrency model.
6. **Are context keys exact?** Compare keys written to ExecutionContext with keys read by SpEL.
7. **Are multiple JobExecutions running concurrently?** Look for mutable state placed inside singletons.
8. **Is there a wrapper/decorator?** Verify scoped proxies and ItemStream lifecycles are forwarded.
9. **Did the test activate the scope?** Use test utilities instead of calling targets outside context.

Do not work around this by calling `StepSynchronizationManager.register(...)` manually in business code unless you genuinely manage the full lifecycle and cleanup. Manual context registration can leak state across runs or threads.

## 14. Common Mistakes

### Using singleton for a bean needing JobParameters

Singletons are created before JobExecution exists or retain the first run's values. Use Step scope or Job scope for late binding.

### Using @StepScope yet calling the bean before the Step runs

The proxy can be injected early, but the target can only be created when Step scope is active. Do not invoke methods in startup callbacks or constructors.

### Using @JobScope to read stepExecutionContext

Job scope does not represent a specific StepExecution. Use @StepScope for Step/partition-specific values.

### Using prototype instead of Step scope

Prototype does not bind the bean to a StepExecution and does not automatically supply context or lifecycle. Use @StepScope when per-Step late binding is needed.

### Scope not registered

The error `No Scope registered for scope name 'step'` usually indicates Batch infrastructure has not registered the scope or configuration is missing/duplicated. Check `@EnableBatchProcessing` or the active auto-configuration.

### Scope not active on worker threads

The error `Scope 'step' is not active for the current thread` can occur when the target is invoked outside the Step lifecycle or Batch context is not propagated to that thread. Inspect the executor and how workers are launched.

### Treating a scoped bean as having one instance per thread

Step scope binds to StepExecution, not thread. In a multi-threaded Step, the target can be used by multiple threads concurrently. Verify thread safety.

### Singleton retaining data from a previous run

Do not store per-Job input files, tenants, execution IDs, or counters in mutable fields of a singleton.

### Wrapping a reader yet losing ItemStream

Decorators must forward open/update/close. Otherwise, checkpoints may fail to save or restore.

### Tests not creating a StepExecution context

Activate scope with StepScopeTestUtils or a Spring Batch test listener before invoking scoped beans.

## 15. Process for Choosing a Scope for a Bean

When declaring a bean in Batch configuration, determine:

1. Does the bean depend on data that exists only inside a JobExecution or StepExecution?
2. Is that data Job-wide or limited to one Step/partition?
3. Does the bean need a separate target per execution?
4. Can values be passed via method parameters instead of holding state?
5. Does the bean have mutable state and concurrent access by multiple threads?
6. Is the scoped proxy injected and invoked only when the scope is active?
7. Is scope infrastructure registered by Spring Batch?
8. If it is a reader/writer, is the ItemStream lifecycle forwarded?
9. Do tests establish the proper Job/Step context?
10. Could Job restarts or parallel runs cause the bean to receive the wrong data?

Typically, stateless business services should be singletons. Beans needing per-StepExecution late binding should use @StepScope. Configuration or state shared across a JobExecution can use @JobScope, with attention to concurrency.

## Conclusion

Out-of-scope bean errors arise when a bean needs a Job/Step context yet is created or invoked outside the corresponding execution lifecycle. Singleton beans may be initialized too early and fail to resolve jobParameters or stepExecutionContext, or may retain state shared across runs. Use @StepScope for StepExecution/partition-specific data and @JobScope for JobExecution-specific data; scoped proxies allow injecting beans into singleton configurations while only creating targets when the scope is active. Register Batch scope infrastructure, invoke beans within the proper lifecycle, verify thread safety, preserve the ItemStream lifecycle, and set up contexts in tests.
