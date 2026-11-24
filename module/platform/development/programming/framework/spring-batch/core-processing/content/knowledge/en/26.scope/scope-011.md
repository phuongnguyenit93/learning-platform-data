# Do Not Use Scoped Beans for Global State in Spring Batch

Spring Batch provides scopes such as `@StepScope` and `@JobScope` to instantiate beans at the right time and bind bean lifecycles to a single step or job execution. These scopes are very useful when a bean needs to read `JobParameters`, `ExecutionContext`, or hold state belonging strictly to a specific execution.

However, scoped beans are not the place to store application-wide global state. A step-scoped bean lives only within a `StepExecution`; a job-scoped bean lives only within a `JobExecution`. If you place an application-wide counter, a cache shared across jobs, or state that must persist across multiple runs into these beans, data can become isolated per execution, vanish when the execution ends, or be accessed concurrently in unexpected ways.

To choose the right scope, determine who owns the state and how long it lives: a single item invocation, one step execution, one job execution, the entire ApplicationContext, or across multiple processes/nodes.

## 1. Bean Scope Determines Object Lifecycle

In Spring, scope defines when the container creates a bean, when injection points receive the same instance, and when that instance is destroyed. Spring singleton is the default scope: one instance per bean definition in a Spring ApplicationContext. `@StepScope` and `@JobScope` add lifecycles tied to Spring Batch executions.

| Scope | Instance boundary | Typically created when | Suitable for |
| --- | --- | --- | --- |
| Singleton | One instance per bean definition in one ApplicationContext | When context initializes or bean is first requested | Stateless services, configuration, repositories, concurrency-safe shared components |
| Job scope | One instance per `JobExecution` | When the job-scoped bean is accessed during a job execution | Values or helpers belonging strictly to a single job run |
| Step scope | One instance per `StepExecution` | When the step-scoped bean is accessed during a step execution | Readers, writers, processors, or helpers needing step-specific parameters/context |
| Prototype | A new instance each time the container is asked for the bean | On every bean lookup | Short-lived objects created explicitly; container does not manage full lifecycle after injection |

Remember that scope describes object lifecycle, not whether data is persisted durably. Fields inside `@StepScope` are still in-memory fields. When a step ends or a process stops, those fields are not automatically written to `JobRepository`.

## 2. @StepScope Belongs to One StepExecution

`@StepScope` is for beans that must be initialized in the context of a single `StepExecution`. Each step execution can receive its own target bean. That is why step-scoped readers are commonly used to retrieve parameters from `JobParameters` or step `ExecutionContext`.

Example:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate,
        @Value("#{stepExecutionContext['tenantId']}") String tenantId) {

    return new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("select id, tenant_id, total")
        .fromClause("from orders")
        .whereClause("where tenant_id = :tenantId and business_date = :businessDate")
        .parameterValues(Map.of(
            "tenantId", tenantId,
            "businessDate", businessDate
        ))
        .rowMapper(new OrderRowMapper())
        .pageSize(200)
        .saveState(true)
        .build();
}
```

`businessDate` is taken from job parameters; `tenantId` is taken from step execution context. These values are only meaningful once Spring Batch has established the corresponding execution context.

If a job runs twice with two different `JobExecutions`, each run has its own `StepExecutions`. Step-scoped beans are instantiated for their respective step executions, so state in bean fields is not global state shared by both jobs.

## 3. @JobScope Belongs to One JobExecution

`@JobScope` creates a bean scoped to a single `JobExecution`. That bean can be used across multiple steps of the same job run, while another execution gets a separate instance.

Example:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['region']}") String region) {

    return new BatchRunDescriptor(businessDate, region);
}
```

A step can inject `BatchRunDescriptor` to use shared information for the job run:

```java
@Bean
Step validateStep(JobRepository jobRepository,
                  PlatformTransactionManager transactionManager,
                  BatchRunDescriptor batchRunDescriptor) {
    return new StepBuilder("validateStep", jobRepository)
        .tasklet((contribution, chunkContext) -> {
            log.info(
                "Validating date={} region={}",
                batchRunDescriptor.businessDate(),
                batchRunDescriptor.region()
            );
            return RepeatStatus.FINISHED;
        }, transactionManager)
        .build();
}
```

A job-scoped bean can share information across steps of the same `JobExecution`. However, it is neither an application-wide singleton nor a durable data store across job runs.

If a job runs twice concurrently, each `JobExecution` gets its own `BatchRunDescriptor` target. Do not use a field in a job-scoped bean to aggregate metrics across all job executions.

## 4. Why Are Scoped Beans Not Global State?

Suppose the application needs a counter of total orders imported across the entire process. If the counter is placed in a step-scoped bean, each step execution receives a separate counter:

```text
ApplicationContext
    |
    +-- JobExecution A
    |      |
    |      +-- StepExecution A1 -> StepScopedCounter = 0
    |      +-- StepExecution A2 -> StepScopedCounter = 0
    |
    +-- JobExecution B
           |
           +-- StepExecution B1 -> StepScopedCounter = 0
```

Instances do not automatically share the same value. If the counter is placed in a job-scoped bean, steps within the same job execution can see the same target, yet another job execution still gets a separate instance:

```text
ApplicationContext
    |
    +-- JobExecution A -> JobScopedCounter = 0
    |
    +-- JobExecution B -> JobScopedCounter = 0
```

Therefore, choosing `@StepScope` or `@JobScope` merely to keep a field alive during processing leads to the wrong boundary when the state actually belongs to the entire application or multiple jobs.

A scoped bean is also not a place for long-lived state. When the scope ends, the target bean is destroyed according to lifecycle; data in fields is not automatically serialized to the metadata repository.

## 5. Distinguishing State by Scope

Before choosing a scope, classify state by its owner:

| State to store | Typical right scope | Implementation approach |
| --- | --- | --- |
| Committed reader position | Step execution | `ItemStream.update(ExecutionContext)` |
| Values specific to one partition | Partition's step execution | Step context and `@StepScope` |
| Shared parameters of one job run | Job execution | `JobParameters`, `JobExecutionContext`, `@JobScope` |
| Temporary counter for one method call | Method invocation | Local variables |
| Shared configuration, stateless services | ApplicationContext | Singleton bean |
| Cache shared within one process | ApplicationContext/process | Singleton cache with concurrency control and eviction |
| State needing to be shared across nodes | Distributed system | Database, distributed cache, or coordination service |
| History that must survive restarts | Durable data store | Business/audit tables or appropriate metadata |

No single scope fits all kinds of state. Choose based on lifetime, sharing boundary, recoverability, and concurrency level.

## 6. Use Singleton for Shared Services That Hold No Execution State

Singleton is the right choice for services that do not hold state specific to a single job/step, such as validation services, repositories, or clients with fixed configuration:

```java
@Service
public class OrderValidationService {

    public ValidationResult validate(Order order) {
        // Compute from input, do not store current item in a field.
        if (order.getCustomerId() == null) {
            return ValidationResult.invalid("Missing customer id");
        }
        return ValidationResult.valid();
    }
}
```

A singleton service can be used by multiple jobs/steps. Therefore, do not store temporary data of the current item in a mutable field:

```java
// Do not do this: this field is overwritten across executions.
private Order currentOrder;
```

Instead, pass data via parameters and local variables:

```java
public ValidationResult validate(Order order) {
    String customerId = order.getCustomerId();
    return validateCustomer(customerId);
}
```

Singleton does not mean thread-safe. If a bean holds a shared cache or counter, choose concurrent data structures, atomic operations, or proper synchronization. If state must survive JVM restarts or be shared across multiple application instances, an in-process singleton cannot satisfy that requirement.

## 7. Do Not Use @StepScope to Hold Application-Wide State

A common design mistake is putting a global cache or counter inside a step-scoped bean:

```java
@Component
@StepScope
public class GlobalImportStatistics {

    private long totalImported;

    public void increment() {
        totalImported++;
    }

    public long getTotalImported() {
        return totalImported;
    }
}
```

The bean name claims it represents global statistics, yet its scope creates instances per `StepExecution`. When another step or job execution uses the bean, it can receive a separate instance and the counter fails to reflect an application-wide total.

If statistics belong strictly to one step, name and scope the bean to match its purpose:

```java
@Component
@StepScope
public class StepImportStatistics {

    private long importedInThisStep;

    public void increment() {
        importedInThisStep++;
    }
}
```

If aggregation across multiple steps within the same job is needed, consider the job execution context, a listener aggregating from `StepExecution`, or a job-scoped service with concurrency control. If aggregation across multiple jobs is required, use a shared store with proper identifiers and transactions.

## 8. Do Not Use @JobScope for Application-Wide State

Job scope is broader than step scope, yet still belongs strictly to one `JobExecution`. For example, a counter in a job-scoped bean can aggregate data within the same job run if steps access the same target:

```java
@Component
@JobScope
public class JobRunStatistics {

    private final AtomicLong processed = new AtomicLong();

    public void addProcessed(long count) {
        processed.addAndGet(count);
    }

    public long getProcessed() {
        return processed.get();
    }
}
```

This bean does not automatically aggregate across all jobs. The next job execution gets a different target; other processes also do not share this field. If the requirement is application-wide statistics, job scope is the wrong boundary.

Even when state belongs strictly to one job, consider how multiple steps or threads may update it concurrently. `AtomicLong` makes increments atomic within one process, yet does not turn the bean into a distributed store or ensure data survives restarts.

## 9. Scoped Proxies Allow Injecting Beans into Singletons

A singleton bean can inject step-scoped or job-scoped dependencies via scoped proxies. The proxy is created early, while the real target is resolved when the corresponding scope is active.

Example:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new OrderReader(inputFile);
}

@Bean
Step importStep(JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                OrderReader orderReader) {
    return new StepBuilder("importStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .build();
}
```

The `Step` bean is typically a singleton constructed when the ApplicationContext initializes. If Spring injected a step-scoped target directly before a `StepExecution` existed, the bean could not resolve `jobParameters`. Scoped proxies solve this by deferring target access until step scope is active.

Spring Batch's `@StepScope` annotation configures the scoped proxy appropriately. When declaring `@Scope` manually, understand proxy modes and injection so you do not retain an old execution's target inside a singleton.

Do not obtain a scoped target bean and retain a long-lived reference to it in a static field or singleton cache. Doing so can keep an instance alive after its scope ends or access a target outside a valid execution.

## 10. @StepScope Does Not Mean One Instance per Thread

This is critical when running a multi-threaded step. Step scope binds to `StepExecution`; it does not automatically create a separate target for each thread processing items.

In a multi-threaded step, multiple threads can access the same step-scoped target simultaneously. If the bean has mutable fields, threads can overwrite or read each other's state.

Dangerous example:

```java
@Component
@StepScope
public class CurrentItemHolder {

    private Order current;

    public void setCurrent(Order order) {
        current = order;
    }

    public Order getCurrent() {
        return current;
    }
}
```

If multiple threads call `setCurrent()` and `getCurrent()`, one thread can read an order written by another thread. Step scope does not provide per-item thread isolation.

Prefer processors/readers/writers that are stateless per invocation. Use local variables or pass items directly via method arguments. If shared state is genuinely needed in a multi-threaded step, design synchronization explicitly and define correctness when items process in parallel.

## 11. Partitioning Creates a Separate StepExecution per Partition

In partitioning, each worker partition gets its own `StepExecution`. Therefore, a worker's step-scoped bean can receive its partition's dedicated `ExecutionContext`:

```text
Manager Step
    |
    +-- Partition 0 / StepExecution 0
    |       @StepScope target 0
    |       step context: minId=1, maxId=1000
    |
    +-- Partition 1 / StepExecution 1
    |       @StepScope target 1
    |       step context: minId=1001, maxId=2000
    |
    +-- Partition 2 / StepExecution 2
            @StepScope target 2
            step context: minId=2001, maxId=3000
```

This is a fitting use case for `@StepScope`: each worker gets its own reader or helper with its own data bounds. There is no need to place a global `currentPartition` variable in a singleton and mutate it before workers run; workers can run concurrently and overwrite that variable.

Reader example:

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("select id, name from customer where id between ? and ? order by id")
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new BeanPropertyRowMapper<>(Customer.class))
        .saveState(true)
        .build();
}
```

Do not use `@JobScope` to substitute for per-partition state. A job-scoped target belongs to the job execution; multiple workers in the same job can see the same target. For partition-specific state, use step execution context and step scope.

## 12. Be Cautious with @JobScope in Multi-Threading and Partitioning

A job-scoped bean is tied to a `JobExecution`, so multiple steps within the same job can access the target concurrently. In concurrent execution models, you must understand which threads have a batch context and how scopes propagate to workers.

Spring Batch notes that job scope is unsuitable for certain multi-threaded/partitioned step cases because the framework does not always control or propagate the job context to every thread spawned by executors or remote workers. Do not rely on a job-scoped target behaving like thread-local state across all concurrency models.

For partition workers, prefer:

- Passing worker-specific data via partition `ExecutionContext`.
- Using `@StepScope` for readers/processors/writers needing partition data.
- Using stateless singleton services for shared logic.
- Using an external database/cache when real cross-worker data sharing is required.

If a shared job-level value is needed, store it in `JobExecutionContext` and read it via mechanisms supported by Spring Batch. Never use mutable fields in a job-scoped bean as a coordination channel between workers.

## 13. Use ExecutionContext for State Needed on Restart

If state must be restored after a rollback or process restart, fields on a scoped bean are not enough. Spring Batch provides `ExecutionContext` attached to `StepExecution` and `JobExecution`, managed by `JobRepository`.

Example of a reader saving a checkpoint:

```java
public class OrderReader implements ItemStreamReader<Order> {

    private static final String LAST_ID = "orderReader.lastId";
    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
            ? context.getLong(LAST_ID)
            : 0L;
    }

    @Override
    public Order read() {
        // Read the next item with ID greater than lastId.
        // Update lastId according to the item read.
        return findNextOrder();
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
```

In this example, the `lastId` field is the reader's runtime state; `ExecutionContext` is the checkpoint persisted during lifecycle updates. When the step restarts, `open()` restores the field from the saved context.

Do not confuse a reader being step-scoped with checkpoints persisting automatically. The reader must implement `ItemStream` or be wrapped by an `ItemStream`-supporting component, and save state properly. Bean scope manages objects; `ExecutionContext` manages recovery state.

## 14. Use JobParameters for Immutable Inputs of a Run

If a value is an input to the job, such as business date, input file, or tenant, pass it via `JobParameters` instead of placing it in a global field:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("inputFile", "orders-2026-11-15.csv", false)
    .toJobParameters();
```

Identifying parameters participate in determining `JobInstance`; non-identifying parameters provide additional information without altering instance identity. Choose identifying flags according to the logical unit of business work of the job.

A step-scoped bean can inject job parameters:

```java
@Bean
@StepScope
OrderFileReader orderFileReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new OrderFileReader(Path.of(inputFile));
}
```

`JobParameters` should be treated as inputs of a run, not a region for writing mutable state. If progress updates are needed, use execution context or an appropriate data store.

## 15. Global State Within One ApplicationContext

If the application genuinely needs a shared cache or service within a single JVM, a singleton bean can be suitable. For example, a cache of infrequently changing metadata:

```java
@Component
public class ProductMetadataCache {

    private final ConcurrentMap<String, ProductMetadata> cache =
        new ConcurrentHashMap<>();

    public ProductMetadata get(String productId) {
        return cache.computeIfAbsent(productId, this::loadMetadata);
    }

    private ProductMetadata loadMetadata(String productId) {
        // Load metadata from the authoritative source.
        return metadataRepository.findById(productId)
            .orElseThrow();
    }
}
```

This singleton cache is shared across jobs/steps in the same ApplicationContext. Still, consider:

- The cache can be lost when the application restarts.
- Each application replica has its own separate cache.
- Multiple jobs/threads may access it concurrently.
- Eviction or invalidation is needed when source data changes.
- Do not store critical business state solely on the heap.

If aggregation across all job executions across multiple nodes is required, a singleton cache is insufficient. Use a database or distributed cache with appropriate keys and atomic updates.

## 16. Global State in a Multi-Node Environment

In a multi-instance deployment, each JVM has its own ApplicationContext and singleton beans. `@JobScope` and `@StepScope` also exist only within the process executing that bean.

```text
Cluster
  |
  +-- Node A / ApplicationContext A
  |       Singleton cache A
  |       JobScope A
  |       StepScope A
  |
  +-- Node B / ApplicationContext B
          Singleton cache B
          JobScope B
          StepScope B
```

No field in any scoped bean synchronizes automatically between Node A and Node B. If multiple workers must share state, use a shared system:

- Database with transactions and unique constraints.
- Distributed cache with atomic operations/TTL.
- Message broker for exchanging events.
- Coordination service or distributed locks when coordination is genuinely required.

Record identifiers should include boundaries such as job instance, tenant, partition, or business key so different executions do not overwrite each other's state.

## 17. Do Not Use Static Fields to Replace Scope

A common flawed fix is changing a field in a scoped bean to `static` so all executions share it:

```java
public class ImportState {
    public static long processedCount;
}
```

This creates state shared within one classloader/process, yet introduces many issues:

- No automatic transactions or checkpoints.
- No isolation by job execution, tenant, or partition.
- Concurrent threads can update it and lose increments.
- Values persist across jobs in the same JVM even when logic expects a reset.
- Not shared across multiple nodes and lost on process restart.
- Tests can interfere with one another due to leftover static state.

If a counter within a single execution is needed, use `StepExecution`/`JobExecution` counters or context. If an application-wide counter is needed, use a thread-safe singleton service or durable store depending on requirements. Static fields are not a batch state management mechanism.

## 18. Choosing Scopes for Readers, Processors, Writers, and Listeners

Not every component in a step needs to be a scoped bean. Choose based on the data the component requires:

| Component | Commonly used scope | Reason |
| --- | --- | --- |
| Reader needing job parameters or partition context | `@StepScope` | Each step execution has its own input/context. |
| Writer creating a step-specific file | `@StepScope` | Each step execution has its own resource and lifecycle. |
| Stateless processor transforming items only | Singleton is usually enough | No separate target per execution needed. |
| Processor depending on step/job parameters | `@StepScope` or `@JobScope` depending on boundary | Late binding values per execution. |
| Shared repository/service | Singleton | Stateless service or explicit concurrency management. |
| Listener needing step-specific parameters | `@StepScope` if late binding is needed | Target bound to the matching execution. |
| Process-wide cache | Managed singleton cache | Shared within one ApplicationContext. |

Do not add `@StepScope` to every bean merely because it is invoked from a step. Scopes add proxies and lifecycle overhead; use them when late binding or execution-specific state/resources are genuinely needed.

## 19. Testing Bean Lifecycle and Boundaries

Verify that two separate executions receive isolated state while callers within the same scope share the right target. For step-scoped beans, run two `StepExecutions` or two job executions and verify runtime fields are not shared inadvertently.

Scenarios to verify:

1. Two `JobExecutions` with different parameters receive matching job/step scope targets.
2. Two `StepExecutions` with different partition contexts receive reader targets with separate ranges.
3. Singleton services do not retain items or context from an earlier execution.
4. Step-scoped beans are not accessed before step scope is active.
5. Reader checkpoints are saved in `ExecutionContext` and restored after restart.
6. Beans with mutable state are not used concurrently in unintended ways inside multi-threaded steps.
7. Multi-node state is read/written via a shared store rather than heap fields.

You can use `StepScopeTestUtils` or Spring Batch test support to set up `StepExecution` when unit-testing step-scoped beans. For integration tests, launch a real job via a test launcher to verify proxies and lifecycles work in a real context.

Do not merely test whether the bean gets instantiated. Test the exact sharing boundary and whether state persists across the required milestones.

## 20. Common Mistakes When Using Scoped Beans for State

**Using a step-scoped bean as a global cache:** each `StepExecution` gets a separate target; caches are not automatically shared across steps/jobs. Use a singleton or distributed cache matching the needed scope.

**Using a job-scoped bean across all jobs:** each `JobExecution` gets a separate target. State is not shared across runs.

**Confusing bean scope with persistence:** fields in scoped beans live in heap memory. Use `ExecutionContext` or a database when restart/durability is needed.

**Assuming singletons are always thread-safe:** singletons can be called concurrently by multiple workers. Avoid unsynchronized mutable fields or use appropriate concurrent primitives.

**Assuming step scope creates per-thread instances:** step scope binds to `StepExecution`; multi-threaded steps can share the target. Do not store the current item in a field of a step-scoped bean.

**Using job scope for per-partition state:** partitions have separate `StepExecutions`. Use step context and `@StepScope` for partition-specific state.

**Using static fields to share state:** statics have no checkpoints, transactions, or cross-node synchronization. Choose a store matching the required scope and durability.

**Retaining a scoped target bean in a singleton/static field:** the reference can outlive the scope and point to an invalid target. Let Spring manage scoped proxies.

**Using scoped beans instead of JobParameters:** immutable job inputs should be job parameters, not mutable fields.

**Using a singleton cache for cluster-consistent data:** each node has its own cache. Use a shared store with clear invalidation/coordination.

## 21. Process for Choosing Where to Store State

Before creating a bean, answer four questions:

1. Does the state belong to an item, step execution, job execution, application process, or the whole cluster?
2. How long must the state live: one method, one step, one job, across restarts, or permanently?
3. How many threads, partitions, or nodes may read/write simultaneously?
4. Does the state need transactions, checkpoints, auditing, or recoverability?

Then choose the mechanism:

- Temporary data within one call: local variables.
- Job input parameters: `JobParameters`.
- Step-specific state: `@StepScope` and `StepExecutionContext`.
- Shared state within one job execution: `@JobScope` or `JobExecutionContext`, with concurrency considered.
- Service/config/cache within one process: thread-safe singleton.
- State needed on restart: `ExecutionContext` or database.
- State shared across multiple nodes: database/distributed store/message broker.

Do not use a scoped bean as a catch-all solution for every kind of state. Bean scope only solves object lifecycle; transactions, persistence, thread safety, and distributed coordination still must be designed separately.

## 22. Design Example: Isolating State to the Right Boundaries

Suppose a job imports orders by tenant and business date. A design could include:

- `JobParameters`: `businessDate`, `inputFile`, and batch identifier.
- `@JobScope`: immutable descriptor for the run, used to configure steps.
- `@StepScope`: separate reader per step execution, reading tenant/range from step context.
- Singleton `OrderValidationService`: shared stateless validation logic.
- `StepExecutionContext`: reader checkpoints and state needed on restart.
- Database/outbox: business state that must survive process restarts and side effects to be emitted.

```text
JobParameters
  businessDate, batchId, inputFile
          |
          v
JobExecution
  JobExecutionContext
          |
          +-- ValidateStep / StepExecution
          |      @StepScope reader/worker
          |      StepExecutionContext checkpoint
          |
          +-- ImportStep / StepExecution
          |      @StepScope reader/writer
          |      StepExecutionContext checkpoint
          |
          +-- ReportStep / StepExecution
                 @StepScope output resource

Singleton services: stateless logic shared in one ApplicationContext
Database/outbox: durable state shared across executions and nodes
```

Each kind of state has a clear owner. When the job restarts, Spring Batch uses parameters and execution context to restore the processing flow; singleton services are recreated with the ApplicationContext; the database/outbox retains durable state. There is no need for a global field to pass state across steps or nodes.

## 23. Designing Scoped Beans in Production

First, use `@StepScope` for components needing parameters or context specific to a `StepExecution`, especially readers/writers per partition, file, or tenant. Use `@JobScope` for objects needing information belonging to one `JobExecution`, while taking care when flows involve multi-threading or partitioning. Use singletons for stateless services, repositories, and shared configuration.

Next, do not treat fields inside scoped beans as durable state storage. Use `ExecutionContext` for checkpoints and recoverable job/step data; use `JobParameters` for run inputs; use a database or distributed store for state shared across executions/processes/nodes.

Finally, inspect concurrency against the actual scope. A step-scoped target does not automatically create one instance per thread within the same step; a job-scoped target is likewise not per-partition state. Avoid mutable fields in singleton/scoped beans without explicit synchronization. Test two concurrent jobs, parallel partitions, and restarts to confirm state never leaks across executions.

Not using scoped beans for global state is a principle of data ownership and lifecycle. `@StepScope` is for one step execution, `@JobScope` is for one job execution, singleton is for one ApplicationContext, and durable or multi-node shared state belongs in an appropriate store. Choosing the right boundary enables jobs to run concurrently and restart without mixing state across executions.
