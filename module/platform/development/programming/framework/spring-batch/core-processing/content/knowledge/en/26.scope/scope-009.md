# Scope in Multi-Threaded Execution

In Spring Batch, scope determines the lifecycle and lifetime boundary of a Spring bean. When a job runs across multiple threads, scope selection directly affects how threads see and use the same instance. A singleton bean can be invoked concurrently by multiple workers; a step-scoped bean is created per StepExecution; a job-scoped bean belongs to a JobExecution. These scopes manage bean lifecycles, yet scope itself does not automatically make an object thread-safe.

This is a critical point when configuring a multi-threaded step, partitioning, or parallel flows. If a reader holds a mutable cursor and multiple threads call it simultaneously, records can be read twice or skipped. If a singleton service stores the current batch ID in a field, one thread can overwrite another thread's data. If multiple flows update the same Job ExecutionContext key, the final result may depend on execution order.

Proper design separates three concerns: within what boundary a bean exists, which threads can access that bean, and what state may be shared. Scope answers the first question; thread safety and transaction/concurrency design must be addressed separately.

## 1. What Is Scope?

Spring bean scope defines when a bean is created, across what boundary an instance is shared, and when the instance is destroyed. Common scopes include:

| Scope | Basic lifecycle | Common usage |
|---|---|---|
| Singleton | One instance per Spring ApplicationContext | Stateless services, repositories, templates, shared configuration |
| Prototype | Creates a new instance each time the container is asked for the bean | Objects needing a fresh instance, with additional lifecycle managed by the application |
| Step | One instance within a StepExecution | Readers, writers, or processors needing step-level late binding |
| Job | One instance within a JobExecution | Data/configuration shared within one job execution |

Spring creates singleton beans by default. That only means the container manages one instance; it does not mean method calls are synchronized or that each thread receives its own copy.

Similarly, prototype does not automatically create a new instance on every method call. If a prototype bean is injected directly into a singleton, the instance is normally created when the singleton is initialized and retained by that singleton thereafter. To obtain a fresh prototype per usage, use ObjectProvider, Provider, or an appropriate lookup mechanism.

Spring Batch adds StepScope and JobScope so beans can access execution runtime data, such as JobParameters or ExecutionContext. They are useful for late binding, though their boundaries must be well understood when multiple threads execute concurrently.

## 2. Scope Does Not Equal Thread Safety

Scope manages object lifecycles. Thread safety is the ability of an object to be used concurrently by multiple threads without corrupting data or violating invariants.

Example of a singleton service holding no per-request state:

~~~java
@Service
public class CustomerLookupService {

    private final CustomerRepository repository;

    public CustomerLookupService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer findRequired(String customerId) {
        return repository.findById(customerId)
                .orElseThrow(() ->
                        new CustomerNotFoundException(customerId));
    }
}
~~~

The service uses only dependencies and local variables inside the method. Multiple flows can invoke it concurrently without overwriting a shared state field, provided the repository and dependencies also support concurrent use.

Conversely, a singleton with per-run mutable state easily causes race conditions:

~~~java
@Component
public class UnsafeBatchState {

    private String currentBatchId;

    public void setBatchId(String batchId) {
        this.currentBatchId = batchId;
    }

    public void process(Order order) {
        // Another thread might have changed currentBatchId.
        saveOrder(order, currentBatchId);
    }
}
~~~

If flow A sets the batch ID to A, and then flow B sets the batch ID to B before flow A calls process, A's order may be recorded under batch B. Moving the bean to another scope does not fix the state design on its own if the new scope is still shared across multiple threads.

Practical rules:

- Prefer stateless services and immutable configuration data.
- Pass per-call data via method arguments rather than storing it in singleton fields.
- Keep worker-specific state inside StepExecution or worker-dedicated objects.
- If shared state must truly be updated, use synchronization or a data store with atomic operations.

## 3. StepScope in Spring Batch

StepScope is the scope for beans bound to a single StepExecution. When the step starts, Spring Batch creates or retrieves the corresponding scoped bean instance; the bean can read runtime data from step context, job context, and job parameters.

A step-scoped bean is typically declared with @StepScope:

~~~java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

The reader is created when the step execution already has JobParameters available. Consequently, the same job configuration can process different files across different runs.

StepScope is usually implemented via a scoped proxy. The bean injected into the step configuration is a proxy; while the step is executing, the proxy looks up the target instance bound to the current StepExecution. Therefore, do not invoke methods on a scoped bean during application context initialization when no StepExecution is active yet.

## 4. Late Binding from Execution Context

A step-scoped bean can pull values from several sources:

| SpEL | Data Source |
|---|---|
| `#{jobParameters['batchId']}` | JobParameters of the current job |
| `#{jobExecutionContext['referenceFile']}` | Job ExecutionContext |
| `#{stepExecutionContext['partitionId']}` | Step ExecutionContext of the current step |

Example of a worker reader receiving an ID range generated by a Partitioner:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Order> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    // Create reader according to the current StepExecution's range.
    return createOrderReader(dataSource, minId, maxIdExclusive);
}
~~~

Late binding enables reusing one bean definition across many step executions with different values. However, injected values do not automatically become thread-local data. If the same target bean is called by multiple threads, fields inside the target can still be accessed concurrently.

Use late binding for execution configuration such as input file, range, tenant, or batch ID. Do not use a mutable field on a scoped bean to hold the "current item" if multiple threads can invoke that bean simultaneously.

## 5. JobScope in Spring Batch

JobScope creates one bean instance within the scope of a JobExecution. It fits data/configuration shared across multiple steps of the same job run, such as an artifact reference or a value prepared at the start of the job.

Example:

~~~java
@Bean
@JobScope
BatchRunSettings batchRunSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new BatchRunSettings(
            LocalDate.parse(businessDate),
            batchId);
}
~~~

A job-scoped bean is shared within the JobExecution. If parallel steps or flows access that bean, they can call the same instance. Thus, a job-scoped bean should contain immutable configuration or explicitly protected state; do not use it as a mutable scratchpad for multiple workers.

JobScope has an important limitation in multi-threaded execution: Spring Batch does not control every thread spawned by a multi-threaded step. The scope context is not always set up properly on those threads. Consequently, Spring Batch documentation recommends against using JobScope in multi-threaded or partitioned steps when the bean needs to be accessed from worker threads. Check the guidance for your exact version and how executors are configured; the safer design is usually passing required data into the worker context and using StepScope per StepExecution.

Even in a parallel flow, where each branch has its own StepExecution yet belongs to the same JobExecution, JobScope still represents a shared job-wide boundary. If multiple branches write mutable state into a job-scoped bean, synchronization or a redesigned flow where each branch writes separate outputs is required.

## 6. Multi-Threaded Step: One StepExecution, Multiple Processing Threads

In a multi-threaded step, a single step uses a TaskExecutor to process chunks or work items on multiple threads. Unlike partitioning, this model does not necessarily create a separate StepExecution per worker. Workers can operate inside a single step execution and share some components.

This has implications for scope:

- A step-scoped bean belongs to that step's StepExecution; do not assume each worker thread gets a separate target instance.
- If the reader, processor, or writer target is called concurrently, the component must be thread-safe or wrapped/designed to avoid unsafe concurrent access.
- Step ExecutionContext belongs to the step execution; do not use it as a place where multiple threads update the same key without synchronization rules.
- Transactions are normally created and managed on the thread executing the chunk; one thread's transaction does not automatically span another thread.

Example of a multi-threaded chunk step:

~~~java
@Bean
Step multiThreadedImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ImportedOrder> processor,
        ItemWriter<ImportedOrder> writer,
        TaskExecutor chunkTaskExecutor) {

    return new StepBuilder("multiThreadedImportStep", jobRepository)
            .<Order, ImportedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(chunkTaskExecutor)
            .build();
}
~~~

In this configuration, do not assume the reader or writer is invoked sequentially. A standard FlatFileItemReader has a cursor and mutable state; if multiple threads call read() concurrently, a safe strategy is needed. You can serialize reads with a synchronized wrapper like SynchronizedItemStreamReader where appropriate, or choose partitioning so each worker gets its own reader. Synchronizing reads does not make the entire pipeline sequential, nor does it guarantee item ordering at the writer.

With a multi-threaded step, @StepScope remains useful for late binding and step-level lifecycle, yet it is not an automatic solution that creates one instance per chunk thread. Identify clearly which components are invoked concurrently and check thread safety of target objects.

## 7. Partitioning: Each Worker Has Its Own StepExecution

Partitioning splits data into multiple partitions and creates one StepExecution per worker partition. Each execution has its own Step ExecutionContext, so this is usually the right model when independent per-worker reader/writer state is needed.

Example:

| Worker | StepExecution context | Reader |
|---|---|---|
| partition0 | minId=1, maxId=1001 | Reader for range 1–1000 |
| partition1 | minId=1001, maxId=2001 | Reader for range 1001–2000 |
| partition2 | minId=2001, maxId=3001 | Reader for range 2001–3000 |

The worker reader can be step-scoped:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Order> workerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("workerReader")
            .dataSource(dataSource)
            .sql("""
                    select id, customer_id, amount
                    from orders
                    where id >= ? and id < ?
                    order by id
                    """)
            .preparedStatementSetter(ps -> {
                ps.setLong(1, minId);
                ps.setLong(2, maxIdExclusive);
            })
            .rowMapper(orderRowMapper())
            .saveState(true)
            .build();
}
~~~

Each worker StepExecution receives its own context, so Spring Batch can instantiate a separate target reader per partition. One worker's cursor, checkpoint, and resources are not shared with another worker, provided the bean is genuinely created in StepScope and workers do not hold an external singleton resource.

Partitioning does not automatically solve database data contention. If two partitions have overlapping ranges or update the same business key, duplicates, lock contention, or lost updates can still happen. The Partitioner must produce stable, non-overlapping ranges.

## 8. Parallel Flow: Multiple StepExecutions in One JobExecution

A parallel flow runs multiple independent branches of a job concurrently, typically via split(TaskExecutor). Each branch has its own StepExecutions while belonging to the same JobExecution.

This creates two state boundaries:

- StepScope isolates target beans per StepExecution of each step/branch.
- JobScope has a shared JobExecution boundary and can be accessed by multiple branches.

Example structure:

~~~java
@Bean
Job parallelJob(
        JobRepository jobRepository,
        Flow customerFlow,
        Flow productFlow,
        TaskExecutor flowExecutor) {

    return new JobBuilder("parallelJob", jobRepository)
            .start(customerFlow)
            .split(flowExecutor)
            .add(productFlow)
            .end()
            .build();
}
~~~

If each flow uses a step-scoped reader, each step execution gets its own reader. If two flows use a stateless singleton service, the service can be shared. If two flows use a job-scoped bean with mutable fields, they can contend on the same state.

Do not assume flow A always finishes before flow B in declaration order. If flow B needs data produced by flow A, place a preparation step before the split, store data in a shared store with clear semantics, or move the dependent step after the split completes.

## 9. Comparing Execution Models and Bean Scopes

| Model | Executions created | Components potentially called concurrently | How to organize state |
|---|---|---|---|
| Sequential step | One StepExecution at a time | Normally no multiple chunk threads within the same step | StepScope fits step-level state |
| Multi-threaded step | One StepExecution, multiple worker threads processing | Reader/processor/writer may be invoked concurrently | Components must be thread-safe; do not treat StepScope as per-thread |
| Partitioning | One StepExecution per partition worker | Worker steps execute concurrently | Separate StepScope and Step ExecutionContext per partition |
| Parallel flow | Multiple StepExecutions within the same JobExecution | Steps/flows may execute concurrently | StepScope isolates per step; JobScope is shared job-wide |
| Remote partitioning | Worker StepExecutions run on other processes/nodes | Distributed workers may execute concurrently | Pass partition context via partitioning mechanism; avoid relying on manager in-memory state |

The right model depends on the data source type and how work is divided. If the reader is not thread-safe and needs independent checkpoints, partitioning is usually easier to reason about than a multi-threaded step. If flows are independent in data and logic, parallel flows can be a good fit.

## 10. Prototype Is Not an Automatic Solution for Multi-Threading

Some developers switch a bean from singleton to prototype hoping each thread will get its own instance. This does not happen automatically when a prototype bean is injected into a singleton:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class MutableProcessorState {
    private int currentCount;
}

@Component
public class ImportService {

    private final MutableProcessorState state;

    public ImportService(MutableProcessorState state) {
        this.state = state;
    }
}
~~~

In this example, Spring creates one MutableProcessorState when creating ImportService, and the singleton holds onto that instance. Threads calling ImportService still end up sharing state.

If you truly need a fresh prototype instance per usage, inject ObjectProvider:

~~~java
@Component
public class ImportService {

    private final ObjectProvider<MutableProcessorState> stateProvider;

    public ImportService(
            ObjectProvider<MutableProcessorState> stateProvider) {
        this.stateProvider = stateProvider;
    }

    public void processBatch() {
        MutableProcessorState state = stateProvider.getObject();
        // New instance for this lookup.
    }
}
~~~

However, prototype instances do not automatically have their full destruction lifecycle managed by Spring after being returned to the client. The application must release resources if the object holds file handles, cursors, or other resources. In Spring Batch, StepScope is usually a more natural fit when state belongs to a StepExecution.

## 11. Designing Readers Safely for Multi-Threaded Reading

Readers are usually the component most prone to issues because they hold cursors, pages, offsets, or stream state.

Options:

**Thread-safe reader:** use a reader designed to support concurrent reads per its contract. Read the specific documentation; do not infer thread safety merely from whether the bean is singleton or step-scoped.

**SynchronizedItemStreamReader:** wrap a reader to synchronize read() calls. This serializes reading while allowing processors and writers to run concurrently. Processing/writing order may differ from read order; evaluate restart and reprocessing semantics carefully.

**Partitioning:** create a separate reader instance per worker StepExecution and split the input into non-overlapping ranges. This is often the cleanest option when the data source can be partitioned.

**Page/range-stateless reader:** design the reader so each read uses an explicit key or page token, avoiding a shared mutable cursor.

Example of a synchronized wrapper:

~~~java
@Bean
@StepScope
SynchronizedItemStreamReader<Order> synchronizedReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    FlatFileItemReader<Order> delegate = createReader(inputFile);

    return new SynchronizedItemStreamReaderBuilder<Order>()
            .delegate(delegate)
            .build();
}
~~~

The wrapper only synchronizes the read operation. It does not make the writer, processor, ExecutionContext, or external side effects thread-safe. If exact output ordering is required, record a sequence key and sort/aggregate in a later step.

## 12. Processors and Writers in Multi-Threaded Execution

Processors are usually easy to make thread-safe if they only transform input into output using local variables. Avoid storing the current item or temporary state in fields:

~~~java
@Component
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        BigDecimal normalizedAmount =
                input.amount().setScale(2, RoundingMode.HALF_UP);
        return new Order(input.orderId(), input.customerId(), normalizedAmount);
    }
}
~~~

Writers require closer inspection. A writer may hold buffers, file handles, batch statements, or retry state. If multiple threads call the same writer:

- Check whether the implementation supports concurrent writes.
- When writing to a database, use per-thread transactions/connections and avoid shared mutable statements.
- When writing to files, usually use separate outputs per worker or serialize all write operations through an appropriate mechanism.
- When sending APIs/messages, use idempotency keys and bound concurrency to match external service limits.
- Do not use a singleton mutable collection as a shared buffer without synchronization.

A stateless processor/writer can still call a non-thread-safe dependency. Inspect the entire dependency graph, not just the class annotated with @Component.

## 13. ExecutionContext Is Not Thread-Local Storage

Step ExecutionContext and Job ExecutionContext are state managed by Spring Batch and persisted to the JobRepository according to the corresponding lifecycle/transactions. They are not a synchronized map for arbitrary threads to exchange data instantaneously.

In a multi-threaded step, multiple chunks can belong to one StepExecution. If threads concurrently write a key like currentOffset, lastId, or count to the same execution context, values can be overwritten or updated out of order. Do not use the context to count concurrently processed items without synchronization and clear checkpoint semantics.

In a parallel flow, steps have separate StepExecutionContexts yet can access the same Job ExecutionContext. Two flows writing the same key can cause a race condition or completion-order-dependent results.

Safe alternatives:

- Use Step ExecutionContext for checkpoints owned by a single worker.
- Use distinct keys per partition/flow when storing small metadata.
- Have an aggregation step after the split read results already written to a database.
- Use a coordination table with unique keys/atomic updates when durable shared state is needed.
- Use concurrent data structures for temporary metrics within one JVM, without treating them as durable checkpoints.

## 14. ThreadLocal and Scope Context

Some Spring mechanisms bind the execution context to the current thread via ThreadLocal. This is how the framework identifies the active step/job when a scoped proxy needs to look up the target bean.

Do not create your own ThreadLocal to store JobParameters or StepExecution and assume it automatically propagates to threads created by a TaskExecutor. ThreadLocal does not inherit automatically to thread pool workers, and thread pools reuse threads across tasks. If you manage a ThreadLocal yourself, you must register and clear it properly in a finally block; otherwise, data from an earlier execution can leak into a later task.

Spring Batch sets up the scope context on execution paths managed by the framework. On application-spawned threads or custom executors, do not assume context was propagated. Use partitioning/step execution mechanisms supported by Spring Batch, pass data explicitly through task context, or design independent workers.

In particular, do not call a step-scoped or job-scoped proxy from an arbitrary thread outside the step/job lifecycle when no corresponding scope context exists. You may encounter an error stating no active context exists or retrieve stale state.

## 15. Transactions and Scope Are Independent Concepts

Scope does not dictate transactions. A step-scoped bean can be invoked across many chunk transactions; a singleton repository can participate in different transactions on different threads.

In a multi-threaded step:

- Each chunk normally runs in its own transaction on the thread processing that chunk.
- Thread A's transaction does not automatically span thread B.
- Do not share JDBC Connections, EntityManagers, or TransactionStatuses across worker threads.
- One chunk rolling back does not automatically roll back chunks committed by another thread.

In partitioning, each worker StepExecution processes chunks in its own transaction. In parallel flows, steps on different branches also have separate transactions. If the entire job must publish results as a single business unit, write to staging keyed by batch ID and run a reconciliation/publish step after all branches succeed.

Do not use @JobScope or @StepScope as a way to share transactions or lock data. If transaction coordination is needed, design it via transaction managers, database constraints, locking, or an appropriate coordination mechanism.

## 16. JobScope in Worker Threads: Limitations and Alternatives

JobScope is very useful when a bean needs job parameters and is used across sequential steps. However, in a multi-threaded or partitioned step, worker threads may not have the job scope context established like the coordinating thread. Spring Batch documentation recommends avoiding job-scoped beans in these worker paths.

Instead of letting worker threads access a mutable job-scoped bean directly:

1. Read JobParameters or Job ExecutionContext where the scope context is supported.
2. Put required values into the partition's Step ExecutionContext or worker configuration.
3. Use StepScope to create beans per worker StepExecution.
4. Keep shared configuration data immutable.
5. If aggregated results are needed, write each worker's results separately and aggregate afterward.

Example of a Partitioner placing batch ID and range into context:

~~~java
Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

ExecutionContext context = new ExecutionContext();
context.putString("batchId", batchId);
context.putLong("minId", startId);
context.putLong("maxIdExclusive", endId);

partitions.put("partition0", context);
~~~

Worker bean reading values from step context:

~~~java
@Bean
@StepScope
OrderReader workerReader(
        @Value("#{stepExecutionContext['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new OrderReader(batchId, minId, maxId);
}
~~~

Each partition receives its own values via StepExecutionContext. This is a cleaner model for worker-owned state than having workers access a shared mutable job-scoped bean.

## 17. Strategies for Protecting Shared State

When state genuinely must be shared, choose a mechanism matching the requirements:

| Strategy | Suitable when | Limitations |
|---|---|---|
| Immutable object | Read-only configuration data | Cannot be used for results that need updating |
| Method arguments/local variables | State belongs to a single call | Parameters must be passed through layers |
| StepScope/partition context | State belongs to a StepExecution/partition | Does not automatically create one instance per chunk thread |
| synchronized/Lock | Need to serialize a critical section within one JVM | Can reduce throughput; does not protect across multiple processes |
| Atomic/concurrent collection | Temporary counters/caches within one JVM | Not durable across restarts; business semantics still need definition |
| Database unique constraint/atomic update | Shared state must be durable and updated concurrently by multiple nodes | Can cause contention; requires key/index design |
| Message/coordination service | Workers must coordinate across processes/nodes | Adds operational complexity and delivery/error handling |

Do not wrap an entire processor/writer in synchronized just to avoid race conditions if state can be partitioned instead. Synchronizing the whole pipeline can negate the benefits of parallelism. Lock only small critical sections and measure performance impact.

## 18. Scope, Resource Cleanup, and Restart

Readers/writers may open files, cursors, or connections during a step's lifecycle. StepScope helps tie resources to the StepExecution so Spring Batch invokes the corresponding lifecycle via ItemStream or bean destruction callbacks.

When using multi-threaded execution:

- Do not share the same file handle/cursor across workers if the implementation does not support it.
- Each partition should have its own resource or independent read/write range.
- Ensure close is called when the step completes or fails.
- Do not store runtime resources such as Connection, InputStream, or EntityManager in ExecutionContext.
- Persist small, serializable checkpoints so workers can recover after a restart.

Scope does not replace ItemStream. A step-scoped reader still needs to implement ItemStream or use a state-aware builder so Spring Batch opens, updates, and closes the reader at the right moments.

For restarts, keep partition names/ranges stable and use the same identifying JobParameters as the initial run. If every restart generates new ranges or uses singleton state to track position, workers may duplicate or skip records.

## 19. Configuring Executors and Concurrency

Safe scoping does not mean thread count can grow unboundedly. A TaskExecutor must bound concurrency according to CPU, connection pools, memory, and external system limits.

Example of a bounded executor:

~~~java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(60);
    return executor;
}
~~~

If four workers write to the database concurrently, the connection pool needs enough capacity for those workers plus other components. If workers call an external API, concurrency must stay within rate limits. Raising thread counts when downstream is already saturated can reduce throughput and increase timeouts.

Monitor active threads, queue depth, connection acquisition time, database lock waits, API latency, and step durations. Naming threads helps correlate logs with flows/workers during investigations.

## 20. Testing Scope in Multi-Threaded Execution

Tests must verify that bean instances and state behave properly under the actual concurrency model. A sequentially executed test cannot prove that a singleton or scoped bean is safe when accessed concurrently by multiple threads.

Scenarios to test:

1. Stateless singleton: multiple threads call the same service with different data; verify no cross-talk.
2. Mutable singleton: if state exists, run concurrently to verify synchronization or uncover races.
3. StepScope late binding: each StepExecution receives its exact JobParameters/Step ExecutionContext.
4. Multi-threaded step: verify the reader, processor, and writer are safe under concurrent calls; do not assume StepScope creates per-thread targets.
5. Partitioning: each worker gets its own target reader and exact range/context.
6. Parallel flow: steps have separate StepScopes; shared Job ExecutionContext keys are not overwritten.
7. JobScope: do not rely on mutable job-scoped beans in worker threads; test scope context boundaries under the real executor setup.
8. Prototype injection: verify fresh prototypes are fetched via ObjectProvider when required.
9. Resource lifecycle: verify readers/writers are closed and do not leak resources after the step.
10. Restart: workers restore checkpoints accurately after a partition or step fails.
11. Transaction isolation: a rollback in one worker does not undo chunks committed by another worker.
12. Shutdown: stop a job while workers are active and verify resources are released as designed.

You can use CountDownLatch or CyclicBarrier in tests to force multiple threads to enter a code section simultaneously, creating reproducible race conditions. Avoid relying on Thread.sleep() to guess thread timing. For integration tests, use the real JobRepository and transaction manager of the test configuration; verify final data as well, not only BatchStatus.

## 21. Common Mistakes

**Assuming singleton beans are safe because Spring manages them.** Singleton only means one instance in the ApplicationContext. If mutable fields exist, multiple threads can overwrite state.

**Assuming StepScope is per-thread.** StepScope binds to StepExecution, not a promise that each chunk thread gets a separate target. Components must still be thread-safe if called by multiple threads.

**Using JobScope for mutable worker state.** JobScope belongs to JobExecution and has context limitations in multi-threaded/partitioned execution. Pass data into the worker context and use StepScope appropriately.

**Using prototype yet injecting directly into a singleton.** The singleton can retain a single prototype instance. Use ObjectProvider if a fresh instance per lookup is genuinely needed.

**Sharing a cursor-based reader.** Non-thread-safe readers can duplicate or skip items. Use a safe reader, an appropriate synchronized wrapper, or partitioning.

**Writing the same ExecutionContext key from multiple threads.** State can be overwritten or checkpoints corrupted. Partition key ownership and aggregate afterward.

**Using custom ThreadLocals without propagation/cleanup.** Thread pools reuse threads; old state can leak into new tasks. Use the framework's scope context or pass data explicitly.

**Assuming scope shares transactions.** Transactions belong to the execution thread and transaction manager; bean scope does not propagate transactions across threads.

**Increasing concurrency without accounting for resources.** Database pools, API quotas, and CPU can become bottlenecks. Bound executors and monitor load.

## 22. Process for Choosing Scope for Workers

When a bean is used in multi-threaded execution, determine:

1. Does the bean hold state or contain only stateless logic?
2. Does state belong to the entire application, a JobExecution, a StepExecution, a partition, or a single invocation?
3. How many threads can invoke the same target instance?
4. Does the framework establish the scope context on those threads?
5. Do the bean and its dependencies support concurrent use?
6. Must state survive restart or is it purely transient?
7. When must resources be closed?
8. Can state be partitioned instead of synchronizing shared state?
9. Must results be written to a database/ExecutionContext, and who owns each key?
10. Are concurrency tests and restart tests in place?

Common selection guidelines:

- Stateless service: singleton.
- Reader/writer needing JobParameters or Step ExecutionContext: StepScope.
- Per-partition state: StepScope paired with the partition's Step ExecutionContext.
- Immutable configuration used within a job: JobScope can be considered, but avoid having worker threads update mutable state; note JobScope limitations in multi-threaded/partitioned steps.
- Fresh object per call: ObjectProvider/prototype if the lifecycle fits.
- Durable shared state: database or coordination store instead of singleton fields.

## Conclusion

Scope in multi-threaded execution determines the boundary within which beans are created and shared, yet does not automatically guarantee thread safety. Singletons are often invoked concurrently by multiple flows or workers; StepScope binds to StepExecution rather than creating a separate instance per chunk thread; JobScope is scoped to JobExecution and is not recommended on worker paths in multi-threaded or partitioned steps where scope context is not guaranteed.

Keep services stateless, use StepScope for configuration and state belonging to a worker execution, create dedicated readers/writers per partition when independent checkpoints are needed, and avoid using ExecutionContext or ThreadLocal as ad-hoc synchronization mechanisms. Verify thread safety across the entire dependency graph, transaction boundaries, and resource lifecycles. Finally, run concurrency and restart tests to confirm no state is mixed, no items are lost, and no duplicate side effects occur when workers run concurrently.
