# Proxies of Scoped Beans

In Spring Batch, `@StepScope` and `@JobScope` allow creating beans whose lifecycles are tied to a single step or job execution. However, these beans are usually declared in the application context at startup, whereas `StepExecution` and `JobExecution` only exist when a job is launched.

Spring bridges that time gap with scoped proxies. Configuration components can receive the proxy as soon as the application context is created; the proxy only looks up or instantiates the target object (scoped target) when a method is invoked while the corresponding scope is active.

Therefore, it is essential to distinguish the proxy from the target: the proxy is the stand-in injected where the bean is used; the target is the actual bean created for the current `StepExecution` or `JobExecution`. Understanding this mechanism helps you use late binding for `JobParameters` and `ExecutionContext`, avoid premature scope access errors, and design parallel execution properly.

## 1. Why Are Scoped Proxies Needed?

The Spring application context normally instantiates singleton beans when the application starts up. A step configuration bean may need a reference to a reader, writer, or service whose configuration data is only available when the job runs.

For example, the input filename is passed via `JobParameters`. When Spring creates a `FlatFileItemReader` bean at startup, there is no JobExecution yet to supply that parameter. If the reader were an ordinary singleton, it would have no natural way to receive per-run values.

`@StepScope` solves this problem by deferring target creation until the step starts and the step context is ready.

```text
Application startup
  Spring creates application context
       |
       +--> create singleton Step bean
       |
       +--> inject scoped proxy for reader

Job launch
  JobExecution / StepExecution is created
       |
       v
  Step starts, StepScope is activated
       |
       v
  Step calls reader proxy
       |
       v
  Proxy looks up/creates reader target for current StepExecution
       |
       v
  Reader target uses JobParameters / ExecutionContext
```

The proxy allows dependencies to be wired early, while the target object is instantiated lazily according to the execution context.

## 2. Proxy and Target Are Two Different Objects

When a bean is declared with `@StepScope`, Spring registers a scoped proxy as the object injected into other beans. When the proxy receives a method call, it looks up the target in the active scope and delegates the call to that target.

| Object | Role | Lifecycle |
|---|---|---|
| Scoped proxy | Stand-in injected into other beans | Typically lives in the application context |
| Scoped target | Actual reader, writer, or service | Bound to the active scope, such as a StepExecution |

The proxy is not a new reader on every `read()` call. Within the same `StepExecution`, the proxy normally continues pointing to the same target for that step. When another execution runs, the scope supplies the target matching the new execution.

This is why you can inject a scoped bean into a singleton bean without causing the target to be created prematurely. The singleton holds the proxy; the proxy looks up the target in scope when used.

## 3. @StepScope Creates Proxies per StepExecution

`@StepScope` is Spring Batch's dedicated annotation for beans with `step` scope. It is equivalent to declaring scope `step` with target-class proxy mode (`TARGET_CLASS`).

Example of a reader reading a file chosen via JobParameters:

```java
@Bean
@StepScope
public FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Customer>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .delimited()
        .names("customerId", "name")
        .targetType(Customer.class)
        .build();
}
```

Spring can create the proxy for `customerReader` while configuring the application context. The `inputFile` value is resolved when the target is created inside StepScope, once the execution's JobParameters are available.

For each `StepExecution`, Spring Batch maintains a separate scope context. If the same job runs for two different files as two executions, each execution receives a reader target with its corresponding resource.

## 4. Injecting a Scoped Proxy into a Singleton Step

A Step is typically declared as a regular configuration bean. You can inject a scoped reader into the step factory method:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomers", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .writer(customerWriter)
        .build();
}
```

At the time Spring creates `importCustomersStep`, the `customerReader` dependency can be a proxy. The Step holds a reference to the proxy; when the step actually calls the reader inside a StepExecution, the proxy obtains the matching target.

There is no need to call a factory manually to construct a reader on every run. Likewise, do not store a manually constructed reader target in a static field or mutable singleton, as different runs could share state.

## 5. Late Binding with JobParameters

Late binding means resolving configuration values at the moment the scoped target is created, rather than at application context startup.

Example of a reader receiving file and encoding from JobParameters:

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['encoding']}") String encoding) {

    return new FlatFileItemReaderBuilder<Customer>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(encoding)
        .delimited()
        .names("customerId", "name")
        .targetType(Customer.class)
        .build();
}
```

When launching the job, the caller passes parameters:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("input.file", "data/customers.csv", true)
    .addString("encoding", "UTF-8", false)
    .toJobParameters();

jobLauncher.run(importCustomersJob, parameters);
```

`input.file` is marked identifying in the example because it determines the instance's data source. `encoding` is non-identifying because the example treats it merely as a technical option; if changing the encoding alters the semantic meaning of processed data, consider including it in identity.

## 6. Late Binding with ExecutionContext

In addition to JobParameters, a scoped bean can obtain data from `ExecutionContext`. This is how ranges or checkpoints are passed to a step's reader/writer.

Example of a reader in a partition receiving an ID range from step execution context:

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Order>()
        .name("partitionOrderReader")
        .dataSource(dataSource)
        .sql("""
            SELECT ORDER_ID, CUSTOMER_ID, TOTAL
            FROM ORDERS
            WHERE ORDER_ID >= ? AND ORDER_ID <= ?
            ORDER BY ORDER_ID
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
```

`minId` and `maxId` come from the worker StepExecution's context. Since each partition has its own StepExecution and context, each scoped target receives its own range without requiring a separate reader class.

Commonly used expressions:

| Expression | Value resolved from |
|---|---|
| `#{jobParameters['input.file']}` | JobParameters of the current JobExecution |
| `#{stepExecutionContext['minId']}` | Current Step ExecutionContext |
| `#{jobExecutionContext['watermark']}` | Current Job ExecutionContext |
| `#{stepExecution.stepName}` | Name of the current step execution |

Only reference keys that have already been created before the target needs that value. If a key is missing or has an incompatible type, resolution may fail when the target bean is created.

## 7. @JobScope Creates Proxies per JobExecution

`@JobScope` creates a bean whose lifecycle is tied to a single `JobExecution`. This bean can use JobParameters or the Job ExecutionContext and is shared within that execution.

Example of a service generating a report filename from the business date:

```java
@Bean
@JobScope
ReportNamingPolicy reportNamingPolicy(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new ReportNamingPolicy("orders-" + businessDate + ".csv");
}
```

Steps within the same JobExecution can use the proxy of `reportNamingPolicy`; the target is created in job scope and retained for the JobExecution lifecycle.

Distinction:

- `@StepScope`: separate target per StepExecution, suitable for readers/writers or components depending on a single step's context.
- `@JobScope`: target per JobExecution, suitable for data or policies shared at the job level.

Do not use JobScope to hold mutable state updated concurrently by parallel steps without a synchronization mechanism. For state belonging to a single worker or partition, StepScope is usually more appropriate.

## 8. When Is a Scoped Target Created and Destroyed?

A scoped target is not created simply because the application context starts up. It is normally instantiated on the first invocation through the proxy within an active scope. Afterward, the target is retained in the corresponding scope until that scope ends.

With StepScope, the general lifecycle is:

1. The job is launched and Spring Batch creates JobExecution/StepExecution.
2. The step begins and the StepScope context is established for the StepExecution.
3. The first call through the proxy triggers target creation and dependency/SpEL resolution.
4. The step uses the target while reading, processing, or writing.
5. When the step ends, appropriate lifecycle callbacks are invoked and the scope closes.
6. The target is destroyed according to registered destruction callbacks if the bean supports that lifecycle.

With JobScope, the target is bound to the JobExecution and lives for the duration of the job execution. Specific resource lifecycles also depend on the interfaces/lifecycles implemented by the bean and how the step registers streams.

## 9. Scoped Proxies and the ItemStream Lifecycle

Many Spring Batch readers and writers implement `ItemStream`, with `open`, `update`, and `close` callbacks. The Step needs to recognize these callbacks to open resources, persist checkpoints, and release resources.

When declaring a scoped bean that is an `ItemStream` component, the return type of the `@Bean` method must expose the appropriate interface. It is best to return a concrete type like `FlatFileItemReader<Customer>` or an `ItemStreamReader<Customer>` type rather than declaring only `ItemReader<Customer>` if the target needs to be managed as an `ItemStream`.

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    // Initialize reader supporting ItemStream
    return buildCustomerReader(inputFile);
}
```

Declaring an overly generic return type can prevent Spring from recognizing all necessary interfaces when creating the proxy or configuring the step. Ensure the proxy can be treated as an `ItemStream` if the step needs to invoke its lifecycle callbacks.

Do not call `open()` or `close()` manually on the target from configuration beans. Let Spring Batch manage the lifecycle of readers/writers registered on the step.

## 10. Do Not Invoke a Scoped Proxy Before the Scope Is Active

A proxy can only find a target when the corresponding scope is active. If a singleton invokes a method on a StepScoped bean during application context startup, before any StepExecution exists, Spring has no context to resolve the target.

Inappropriate example:

```java
@Component
public class StartupValidator {

    public StartupValidator(ItemReader<Customer> customerReader) {
        // Do not call reader.read() at singleton initialization time
        // StepScope is not guaranteed to be active yet
    }
}
```

Injecting the proxy is not a problem; dereferencing the proxy outside the scope is the problem. Calling a method without a StepExecution or JobExecution context typically throws an error like `ScopeNotActiveException` or an exception wrapped by bean creation/invocation.

Places to avoid calling scoped beans too early:

- Constructors of singleton beans.
- `@PostConstruct` of singleton beans.
- Logic executing during application context refresh.
- Job/step configuration methods that try to read values from the target instead of merely injecting the proxy.
- Background threads lacking a Spring Batch scope context.

Only invoke the proxy within the corresponding execution flow, once Spring Batch has established the scope.

## 11. Scoped Proxy Does Not Mean Creating a Target on Every Call

Another misconception is that every method call through the proxy causes Spring to create a new object. With StepScope and JobScope, the scope retains the target for the current execution.

For example, within the same StepExecution:

```text
readerProxy.read()  ----+
                       +--> same reader target of StepExecution X
readerProxy.update() --+
                       +--> same reader target of StepExecution X
readerProxy.close()  --+
```

When a different StepExecution starts, the proxy resolves the target according to the new context. That is how reader state such as current line or cursor stays bound to the right execution.

Do not confuse scoped proxies with prototype scope. Prototype normally creates a new instance on each bean request from the container; StepScope/JobScope retains the instance for the defined execution boundary.

## 12. Proxy Mode and Limitations of Class Proxies

`@StepScope` and `@JobScope` default to target-class proxying. Spring typically creates a class-based proxy so the proxy can be injected under the concrete bean type.

Class-based proxies require subclassing the target class. Therefore, the target class must not be `final`; methods that need to be proxied must also not be `final` or `private`. If the class cannot be proxied by the active mechanism, application context startup may fail when creating the proxy.

For example, avoid declaring a custom reader as `final` when using default `@StepScope`:

```java
// Avoid final class if scoped proxy uses class-based proxy
public class CustomerReader implements ItemStreamReader<Customer> {
    // implementation
}
```

For custom beans, use an extendable class and appropriate public/protected methods. If an interface-based design or changing the proxy mode is needed, verify the exact scope configuration and dependency types in the application; do not change the proxy mode arbitrarily because the step may require the `ItemStream` interface.

## 13. StepScope Does Not Make a Bean Thread-Safe Automatically

The scope is tied to a StepExecution, not by default one object per thread or per item. In a multi-threaded step, multiple threads can work inside the same StepExecution and access the same StepScoped target concurrently.

This is especially important for readers holding cursors or mutable fields. A stateful reader does not automatically become thread-safe just because it is annotated with `@StepScope`.

| Execution Type | StepScoped Target Scope | Notes |
|---|---|---|
| Sequential step | One target per StepExecution | Usually fits standard stateful readers |
| Multi-threaded step | Target bound to shared StepExecution | May be accessed by multiple threads; check thread safety |
| Partitioning | Each worker StepExecution has its own context | Each partition can receive its own target |
| Multiple JobExecutions | Each execution has its own scope | Do not use mutable static state to share |

With partitioning, StepScope is very helpful because each worker execution can resolve its own range from `stepExecutionContext`. With a multi-threaded step, use thread-safe readers/writers or choose partitioning if independent per-slice reader state is required.

## 14. JobScope and Parallel Processing

A JobScoped target belongs to a single JobExecution. Therefore, multiple steps in the same job can see the same job-scoped target. If multiple branches or workers access the same mutable object, race conditions can occur.

Do not use JobScope as a way to safely share variables between threads. JobScope does not replace concurrent collections, locks, database coordination, or message passing.

In multi-threaded and partitioned workloads, be cautious when relying on JobScope from threads created by executors. Spring Batch's scope context is managed per execution thread; do not assume a thread spawned manually via `@Async` or a custom executor will have all required context. Prefer passing immutable data via appropriate parameters/contexts or using explicit synchronization.

## 15. Scoped Proxies and Dependency Injection

A singleton bean can receive a scoped proxy via constructor injection:

```java
@Component
public class CustomerStepCoordinator {

    private final ItemReader<Customer> reader;

    public CustomerStepCoordinator(ItemReader<Customer> reader) {
        this.reader = reader;
    }

    public void invokeDuringStep() throws Exception {
        Customer customer = reader.read();
        // Only invoke when StepScope is active
    }
}
```

The constructor receives the proxy without forcing the target to be created immediately. However, `invokeDuringStep()` is only valid when called inside a StepExecution with an active scope.

In Spring Batch configuration, it is usually better to inject the scoped proxy directly into the step builder rather than coordinating the reader manually through a service. Spring Batch manages the `ItemStream` lifecycle better when readers/writers are declared directly on the step.

## 16. Distinguishing Scoped Proxies from Lazy Injection

Scoped proxies and lazy injection can both defer creating or retrieving beans, yet they solve different problems.

| Mechanism | Meaning |
|---|---|
| Scoped proxy | Every call is routed to the target belonging to the current scope |
| `@Lazy` | Defers bean initialization/resolution until needed |
| Prototype scope | Container creates a new instance per bean request |
| Singleton scope | One shared instance in the application context |

`@Lazy` does not turn a bean into StepScoped. If a lazy singleton is used, the bean still does not have a separate target per StepExecution. When late binding against JobParameters or ExecutionContext is needed, use `@StepScope`/`@JobScope` and their corresponding scoped proxies.

## 17. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Calling a StepScoped bean method at startup | No StepExecution exists to resolve target | Only dereference the proxy inside a running step |
| Thinking the proxy is the target | Confusing bean lifecycle and state | Distinguish the stand-in proxy from the per-execution target |
| Using a stateful singleton reader for multiple jobs | Runs can share cursors/checkpoints | Use `@StepScope` for execution-dependent readers |
| Thinking every proxy call creates a new object | Misunderstanding scope and lifecycle | Target is retained within the current scope |
| Declaring `@Bean` returning too generic a type for ItemStream | Step may fail to detect required lifecycle interfaces | Declare a concrete return type or `ItemStreamReader` |
| Using a final class with class-based scoped proxy | Cannot create subclass proxy | Use a proxyable class or appropriate proxy configuration |
| Assuming StepScope guarantees thread safety | Multiple threads in one StepExecution can share the target | Use thread-safe components or partitioning |
| Using mutable JobScope to synchronize workers | Race conditions across branches/workers | Use isolated state, immutable values, or synchronization |
| Calling scoped proxy from a thread outside execution | Scope context may not exist | Pass data explicitly or establish proper execution context |

## 18. Testing Scoped Proxies

You can test scoped beans using integration tests that run an actual step/job instead of only instantiating objects manually. The goal is to confirm the target is created in the right scope and receives the right execution data.

Cases to verify:

1. The application context starts up cleanly even when no JobExecution or StepExecution exists yet.
2. The reader target is created when the step starts and receives the right JobParameters.
3. Two JobExecutions with different files receive reader targets matching their respective files.
4. Two partitions receive separate `minId`/`maxId` values in their StepExecution contexts.
5. Invoking the proxy outside a scope produces an appropriate error rather than silently using the wrong target.
6. `ItemStream.open`, `update`, and `close` are called by Spring Batch in the right lifecycle order.
7. Restarts restore checkpoints without reusing stale runtime targets.
8. Multi-threaded steps do not access stateful targets in a way that causes race conditions.

Do not check only whether a proxy object was injected. Verify that the target is resolved within the right execution context, since that is the actual purpose of a scoped proxy.

## 19. Process for Choosing and Using Scoped Beans

When declaring an execution-dependent reader, writer, or service, determine:

1. Does the bean need per-StepExecution state or is it shared across a JobExecution?
2. Does it need late binding from JobParameters or ExecutionContext?
3. Is the bean injected into a singleton step/job configuration? If yes, use a scoped proxy.
4. Does the `@Bean` method declare a return type specific enough for Spring Batch to recognize `ItemStream` when needed?
5. Is the proxy called anywhere before the scope is activated?
6. Does the bean hold mutable state that could be accessed by multiple threads within the same StepExecution?
7. Does the target need to open/close resources or persist checkpoints?
8. Do integration tests verify the target, context, and lifecycle on both fresh runs and restarts?

## Conclusion

Scoped proxies allow injecting `@StepScope` or `@JobScope` beans into singleton beans before a job or step actually runs. The proxy is created early; the target is resolved only within an active scope and retained for the StepExecution or JobExecution lifecycle. As a result, beans can receive JobParameters and ExecutionContext via late binding.

The proxy is not the target, does not create a new object per call, and does not make a bean thread-safe. Use `@StepScope` for worker/step state, `@JobScope` for job-level data, declare return types compatible with `ItemStream`, avoid dereferencing proxies outside scope, and test concurrency when running in parallel.
