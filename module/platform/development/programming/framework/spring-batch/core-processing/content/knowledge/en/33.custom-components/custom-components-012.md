# Registering Components in a Step

In Spring Batch, a step needs more than just an `ItemReader`, `ItemProcessor`, and `ItemWriter`, or a `Tasklet`. A step may also need listeners to observe lifecycle events, `ItemStream`s to manage resources and checkpoints, or auxiliary components nested inside composites/delegates. For these components to function properly, they must be registered with the step in their appropriate roles.

Registering components means letting Spring Batch know which components participate in processing and which must receive lifecycle callbacks. Having a bean in the Spring application context does not mean the step will automatically invoke all its methods. For instance, a `StepExecutionListener` must be attached to the step; an `ItemStream` hidden inside a wrapper may require explicit registration to receive `open`, `update`, and `close`.

Distinguish three primary mechanisms:

- **Configuring processing components:** `.reader(...)`, `.processor(...)`, `.writer(...)`, or `.tasklet(...)` designates the component doing the work.
- **Registering streams:** `.stream(...)` enrolls an `ItemStream` in the step's resource and checkpoint management lifecycle.
- **Registering listeners:** `.listener(...)` attaches callbacks for job, step, chunk, or item lifecycle events.

A single component may fulfill multiple roles—for example, a reader that is both `ItemReader` and `ItemStream`. Understand which roles the builder detects automatically and which require explicit registration, avoiding missed callbacks or duplicate registration.

## Component Types in a Step

A chunk-oriented step typically comprises the following components:

| Component | Interface/role | How to attach to the step |
| --- | --- | --- |
| Reader | `ItemReader<I>` | `.reader(reader)` |
| Processor | `ItemProcessor<I, O>` | `.processor(processor)` |
| Writer | `ItemWriter<O>` | `.writer(writer)` |
| Tasklet step | `Tasklet` | `.tasklet(tasklet, transactionManager)` |
| Stream resource | `ItemStream` | Auto-detected when passed directly in builder-supported positions; if hidden as a delegate, register `.stream(stream)` |
| Step listener | `StepExecutionListener` | `.listener(listener)` |
| Chunk listener | `ChunkListener` | `.listener(listener)` |
| Item listeners | `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener` | `.listener(listener)` |
| Skip listener | `SkipListener` | `.listener(listener)` |

`ItemReader`, `ItemProcessor`, `ItemWriter`, and `Tasklet` define the work. `ItemStream` defines resource/state lifecycles. Listeners receive events for logging, metrics, auditing, or lifecycle coordination. A component does not automatically assume every role merely by being declared a bean.

## Registering Reader, Processor, and Writer

With Java configuration, primary components attach directly to `StepBuilder`:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

`.reader`, `.processor`, and `.writer` define the chunk pipeline. The step calls the reader for inputs, the processor for transformation/filtering, and the writer for persisting outputs. If no processor is needed, omit `.processor(...)`; in that case, the chunk's input/output types must align directly between reader and writer.

This registers the processing roles. You do not need to blindly add `.stream(reader)` just because the reader implements `ItemStream`. Readers/writers implementing `ItemStream` that are passed directly to the step are automatically registered by Spring Batch for lifecycle management. Explicit stream registration is typically needed for streams hidden behind delegates or wrappers that the step does not inspect directly.

### Beans Must Be Spring-Managed When Dependency Injection Is Needed

Declaring components via `@Bean` enables Spring dependency injection and scope management:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor(OrderValidator validator) {
    return input -> {
        validator.validate(input);
        return new Order(input.orderId(), input.amount());
    };
}
```

Avoid instantiating components with `new` inside step configuration methods if they need dependency injection, scopes, or Spring proxies:

```java
// Do not instantiate manually if the component needs Spring management
.processor(new OrderProcessor())
```

Manual instantiation bypasses bean post-processors, `@StepScope`, transaction proxies, dependency injection, and other lifecycle mechanisms. For pure, stateless components needing nothing from Spring, direct instantiation can be valid; however, managed beans are generally easier to configure and test.

## Registering ItemStream

`ItemStream` is the lifecycle contract for components needing to open/close resources or store restart state:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

In the real API, methods declare `ItemStreamException`; the snippet simplifies signatures to highlight roles.

| Callback | Role |
| --- | --- |
| `open(context)` | Open resources and restore saved state |
| `update(context)` | Save current state to `ExecutionContext` at checkpoints |
| `close()` | Close and release resources |

Example custom reader tracking read position:

```java
public class OrderFileReader
        implements ItemReader<Order>, ItemStream {

    private static final String LINE_KEY = "orderReader.line";
    private BufferedReader reader;
    private int currentLine;

    @Override
    public void open(ExecutionContext context) {
        currentLine = context.getInt(LINE_KEY, 0);
        openFileAndSkipLines(currentLine);
    }

    @Override
    public Order read() {
        Order order = readNextOrder();
        if (order != null) {
            currentLine++;
        }
        return order;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(LINE_KEY, currentLine);
    }

    @Override
    public void close() {
        closeReaderQuietly();
    }
}
```

`openFileAndSkipLines`, `readNextOrder`, and `closeReaderQuietly` represent illustrative application logic. A real reader must handle rollbacks properly and persist checkpoints representing only committed data. Do not use this simple counter example as a production implementation for arbitrary file formats.

When the reader is passed directly to `.reader(orderReader)` and implements `ItemStream`, Spring Batch detects and registers the stream automatically. When the reader sits inside a wrapper and the step sees only the wrapper, check whether the wrapper forwards the `ItemStream` lifecycle.

## When Is `.stream(...)` Needed?

Suppose a step uses a composite writer to write to both a database and a file:

```text
Step
  |
  v
Composite writer
  |
  +--> JdbcBatchItemWriter
  |
  +--> FlatFileItemWriter
```

The step sees `CompositeItemWriter` in `.writer(...)`. If the file writer is a hidden delegate inside the composite and its stream lifecycle is not automatically forwarded or registered, the step will never invoke `open`, `update`, and `close` on that delegate. The file writer may write on the first run yet fail to save checkpoints or restart properly.

Register the delegate `ItemStream` explicitly:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        CompositeItemWriter<Order> compositeWriter,
        FlatFileItemWriter<Order> fileDelegate) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(compositeWriter)
            .stream(fileDelegate)
            .build();
}
```

This illustrates a case requiring separate delegate registration. If your wrapper/composite already forwards the full lifecycle or registers delegates internally, do not register redundantly. Check the wrapper's contract and your Spring Batch version to confirm which streams the step already manages.

### Custom Wrappers Must Forward the Lifecycle or Register Delegates

A wrapper might implement `ItemWriter<T>` without implementing `ItemStream`, even though its inner delegate requires a lifecycle:

```java
public class AuditingWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;

    public AuditingWriter(ItemWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
    }
}
```

If `delegate` is a `FlatFileItemWriter`, the step sees only `AuditingWriter`; the file writer's stream is hidden. There are two options:

1. Register `delegate` via `.stream(fileWriter)` on the step.
2. Design the wrapper to implement `ItemStreamWriter<T>` and forward `open`, `update`, and `close` to the delegate.

Example lifecycle-forwarding wrapper:

```java
public class StreamingAuditingWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;

    public StreamingAuditingWriter(ItemStreamWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context) {
        delegate.update(context);
    }

    @Override
    public void close() {
        delegate.close();
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
        // Perform appropriate auditing after the delegate writes.
    }
}
```

This is an illustrative skeleton. When a wrapper forwards the lifecycle, registering the wrapper directly as the writer is usually sufficient for the step to manage the stream. When the wrapper does not forward, register the delegate separately. Avoid both forwarding and registering the same delegate if that causes callbacks to run twice.

### Registering Multiple Streams

A step can have multiple auxiliary streams:

```java
return new StepBuilder("exportStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .stream(fileWriter)
        .stream(checkpointStore)
        .build();
```

Each stream needs clear responsibilities and distinct `ExecutionContext` keys. If multiple streams write to the same key, one component overwrites another's state.

Never register the same stream instance twice through different paths. Repeated `open`, `update`, or `close` calls can open files twice, write duplicate checkpoints, or close already closed resources.

## Registering Listeners in a Step

Listeners receive callbacks at lifecycle milestones. For Spring Batch to invoke a listener, attach it to the step via `.listener(...)` or declare it in the corresponding XML namespace element.

Example `StepExecutionListener`:

```java
public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Finished step {} with status {}",
                stepExecution.getStepName(), stepExecution.getStatus());
        return null; // Keep existing ExitStatus
    }
}
```

Registration:

```java
return new StepBuilder("importStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(importStepListener)
        .build();
```

`beforeStep` runs when the step starts; `afterStep` runs when the step ends. `afterStep` can return an `ExitStatus` to influence flow outcomes. Returning `null` generally preserves the current exit status. Never overwrite status solely to mask an execution failure.

## Common Listener Types

Spring Batch provides listeners at multiple levels:

| Listener | Typical callbacks | Scope |
| --- | --- | --- |
| `StepExecutionListener` | `beforeStep`, `afterStep` | One step execution |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | One chunk |
| `ItemReadListener<T>` | `beforeRead`, `afterRead`, `onReadError` | One item read |
| `ItemProcessListener<I, O>` | `beforeProcess`, `afterProcess`, `onProcessError` | One item process |
| `ItemWriteListener<T>` | `beforeWrite`, `afterWrite`, `onWriteError` | One chunk write |
| `SkipListener<I, O>` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Skipped items |
| `RetryListener` | Retry lifecycle callbacks | One retry operation, when retry is configured |

Listeners fit logging, metrics, auditing, and event reactions. Avoid placing core business logic in listeners when it belongs in a reader/processor/writer or dedicated service.

### ChunkListener

```java
public class ImportChunkListener implements ChunkListener {

    @Override
    public void beforeChunk(ChunkContext context) {
        log.debug("Starting a chunk");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("Chunk completed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk ended with an error");
    }
}
```

Attaching the listener:

```java
.listener(importChunkListener)
```

`ChunkListener` does not replace `ItemWriteListener`: one observes chunk boundaries, while the other observes writer callbacks. To inspect which items were skipped, use `SkipListener`.

### ItemReadListener, ItemProcessListener, and ItemWriteListener

Example process listener:

```java
public class OrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    @Override
    public void beforeProcess(OrderInput item) {
        log.debug("Processing order {}", item.orderId());
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        log.debug("Processed order {}", item.orderId());
    }

    @Override
    public void onProcessError(OrderInput item, Exception exception) {
        log.error("Cannot process order {}", item.orderId(), exception);
    }
}
```

Register with `.listener(orderProcessListener)`. Multiple distinct listeners can be registered on the same step, each handling a concern such as metrics, tracing, or auditing.

### SkipListener

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Input record was skipped", exception);
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable exception) {
        log.warn("Order {} was skipped during processing",
                item.orderId(), exception);
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        log.warn("Order {} was skipped during writing",
                item.orderId(), exception);
    }
}
```

The listener is called when a fault-tolerant step actually skips an item. It works well for writing reject records or auditing. If the listener writes to a file or separate-transaction database, evaluate idempotency because callbacks can execute within flows involving rollbacks and retries.

## Registering Multiple Listeners and Streams Together

The builder allows calling `.listener(...)` multiple times:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(stepExecutionListener)
        .listener(chunkListener)
        .listener(readListener)
        .listener(processListener)
        .listener(writeListener)
        .listener(skipListener)
        .stream(rejectFileWriter)
        .build();
```

This example combines multiple listeners across different interfaces with an auxiliary stream writing a reject file. `rejectFileWriter` must open, update checkpoints, and close alongside the step. If a single object acts as both listener and stream, clarify registration so lifecycle callbacks do not run twice.

When registering multiple listeners of the same interface, verify the ordering behavior enforced by your builder/framework version. Do not rely on implicit ordering if business logic requires listener A to run before listener B. When order matters strictly, consolidate into an orchestrating listener or service with explicit ordering.

## Registering Components in a Tasklet Step

A tasklet step uses a `Tasklet` instead of a reader/processor/writer pipeline:

```java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupTasklet cleanupTasklet,
        StepExecutionListener stepListener) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet(cleanupTasklet, transactionManager)
            .listener(stepListener)
            .build();
}
```

The `Tasklet` is the main execution component. Listeners must still be registered with the step to receive callbacks. If the tasklet holds resources/state and implements `ItemStream`, ensure the step manages its stream lifecycle. For tasklets or auxiliary components not auto-detected by the builder, register `.stream(...)` explicitly.

Example stateful tasklet:

```java
public class CleanupTasklet implements Tasklet, ItemStream {

    private static final String CURSOR_KEY = "cleanup.cursor";
    private long cursor;

    @Override
    public void open(ExecutionContext context) {
        cursor = context.getLong(CURSOR_KEY, 0L);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(CURSOR_KEY, cursor);
    }

    @Override
    public void close() {
        closeResources();
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {
        processNextPartition(cursor);
        cursor++;
        return hasMoreWork(cursor)
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

To be explicit, you can register the stream:

```java
return new StepBuilder("cleanupStep", jobRepository)
        .tasklet(cleanupTasklet, transactionManager)
        .stream(cleanupTasklet)
        .build();
```

Do so only when the tasklet is not automatically registered as a stream in your configuration path/version; avoid double-registering the same stream. Another approach is extracting state/resource management into a dedicated `ItemStream` and registering that stream.

## Registering Components in the XML Namespace

The XML namespace provides elements for referencing listeners and streams. In a chunk step, reader/processor/writer are referenced by bean ID; auxiliary listeners and streams are declared in their respective child elements.

Example:

```xml
<batch:step id="importOrdersStep">
    <batch:tasklet>
        <batch:chunk reader="orderReader"
                     processor="orderProcessor"
                     writer="compositeWriter"
                     commit-interval="100">

            <batch:streams>
                <batch:stream ref="fileWriterDelegate"/>
                <batch:stream ref="rejectFileWriter"/>
            </batch:streams>

            <batch:listeners>
                <batch:listener ref="readListener"/>
                <batch:listener ref="processListener"/>
                <batch:listener ref="writeListener"/>
                <batch:listener ref="skipListener"/>
            </batch:listeners>
        </batch:chunk>
    </batch:tasklet>

    <batch:listeners>
        <batch:listener ref="stepExecutionListener"/>
        <batch:listener ref="chunkListener"/>
    </batch:listeners>
</batch:step>
```

Referenced beans must exist in the application context. `batch:streams` registers auxiliary streams not directly visible to the step through reader/writer; `batch:listeners` attaches callbacks at the chunk or step level according to element placement in the XSD. Exact XML syntax must match your Spring Batch version's schema.

Bean declarations:

```xml
<bean id="stepExecutionListener"
      class="com.example.batch.ImportStepListener"/>

<bean id="fileWriterDelegate"
      class="org.springframework.batch.item.file.FlatFileItemWriter">
    <!-- Resource, line aggregator, and required properties -->
</bean>
```

When using the XML namespace, use IDE schema completion and validate against the dependency's bundled XSD to confirm valid placement of `streams` and `listeners`. Never place `batch:listeners` in an arbitrary element merely because the XML is well-formed; the XSD dictates valid structure.

## Annotation-Based Listeners

Spring Batch supports listener callbacks via interfaces or method annotations. Example:

```java
public class OrderAuditListener {

    @BeforeStep
    public void beforeStep(StepExecution stepExecution) {
        log.info("Step started: {}", stepExecution.getStepName());
    }

    @AfterStep
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Read {}, wrote {}",
                stepExecution.getReadCount(),
                stepExecution.getWriteCount());
        return null;
    }
}
```

Registering the object as a listener:

```java
.listener(orderAuditListener)
```

Spring Batch detects supported listener annotations when the object is registered. Annotations on a class do not automatically make it a listener for every step; the object must still be attached to the appropriate step/job.

Use interfaces when you want compiler-verified contracts, and annotations when grouping callbacks in one class. Avoid mixing multiple mechanisms for the same callback without clear reason.

## Distinguishing Job-Level and Step-Level Listeners

`JobExecutionListener` belongs to the job lifecycle, whereas `StepExecutionListener` belongs to the step lifecycle.

| Listener | Where registered | Scope |
| --- | --- | --- |
| `JobExecutionListener` | `.listener(...)` on `JobBuilder` or job config | Before/after the entire job execution |
| `StepExecutionListener` | `.listener(...)` on `StepBuilder` | Before/after one step execution |
| `ChunkListener` | `.listener(...)` on a chunk step | Before/after each chunk |
| Item listeners | `.listener(...)` on a step | Per read/process/write |

Example job listener:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        JobExecutionListener jobListener) {

    return new JobBuilder("importJob", jobRepository)
            .listener(jobListener)
            .start(importStep)
            .build();
}
```

Do not attach a `JobExecutionListener` to a step expecting it to cover the whole job. Pick the scope matching the events you need to observe.

## StepScope and Late Binding for Components

A reader, processor, writer, or tasklet may depend on `JobParameters` or the current execution's `ExecutionContext`. Use `@StepScope` so the target bean is created when the step runs:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

The scoped bean is injected into step configuration via a proxy. The step registers the proxy as the reader; Spring Batch manages the target corresponding to the active execution. Do not invoke methods on a target by manually creating objects outside the scope.

In XML, use `scope="step"` for beans depending on job/step context. Ensure the scope infrastructure is enabled by the appropriate Spring Batch configuration.

## Listeners and ItemStream Are Distinct Mechanisms

A listener observes events; a stream manages resources and state. Do not substitute one for the other.

Examples:

- `ItemWriteListener.afterWrite` notifies that the writer processed a chunk.
- `ItemStream.update` saves state for restarts.
- `StepExecutionListener.afterStep` observes the final step outcome.
- `ItemStream.close` closes files or cursors.

If a component needs both audit callbacks and checkpoints, it can implement both the listener interface and `ItemStream`, then be registered in the appropriate roles. Builders may auto-detect interfaces on direct components; for wrapped components, register each role that the wrapper does not forward.

Never use `afterStep` instead of `close()` to close resources that must be released regardless of how the step exits. The stream lifecycle is the proper place to open and close resources.

## Conceptual Lifecycle Ordering

For a chunk step, the conceptual lifecycle runs as follows:

```text
Step starts
  |
  +--> StepExecutionListener.beforeStep
  |
  +--> ItemStream.open
  |
  +--> Repeat chunks
  |       |
  |       +--> ChunkListener.beforeChunk
  |       +--> Reader / Processor / Writer
  |       +--> Item listeners on each operation
  |       +--> ItemStream.update at checkpoint
  |       +--> ChunkListener.afterChunk or afterChunkError
  |
  +--> ItemStream.close
  |
  +--> StepExecutionListener.afterStep
  |
Step ends
```

This is a conceptual diagram, not a strict guarantee of exact ordering between every internal callback or transaction synchronization. Exact ordering can depend on step type and version. If business logic relies on a callback running before or after commit, inspect the API contract and test with real transactions.

## Stream Registration and Restartability

A properly registered `ItemStream` opens with the step's `ExecutionContext` and updates state at checkpoints. On restart, the component restores saved state.

Principles:

- Give readers/writers stable names so state keys do not change.
- Use namespaced `ExecutionContext` keys per component.
- Store only small, serializable values compatible across restarts.
- Keep input/output resources stable while a job remains restartable.
- Never store `FileChannel`, JDBC connections, streams, or runtime objects in contexts.
- Register every delegate needing lifecycle callbacks if wrappers do not forward them.
- Never register the same stream multiple times.

If a delegate is unregistered, `open` may not run and resources fail to open properly; `update` fails to save checkpoints; `close` fails to release resources per lifecycle. Such bugs often surface only during restarts or long-running steps.

## Registering Components with Side Effects

Listeners and streams may perform side effects such as auditing, sending notifications, or publishing events. Place them in the appropriate lifecycle phase:

- Metrics/logging fit in listeners.
- Writing rejected items fits in `SkipListener` or a dedicated writer.
- Saving checkpoints belongs in `ItemStream.update`.
- Closing resources belongs in `ItemStream.close`.
- Publishing final outputs can belong in a finalization step after outputs are complete.

Listeners do not automatically make side effects join the chunk transaction. If a listener writes to a separate resource, database rollbacks will not undo that side effect. Use idempotency keys, outboxes, or reconciliation when callbacks can re-run.

Avoid sending emails or calling non-idempotent APIs in `afterChunk`/`afterStep` if jobs can restart and callbacks may execute again operationally. If events must publish post-commit, design an outbox or deduplicatable event publisher.

## Thread Safety of Registered Components

A singleton bean can be invoked by multiple job executions or threads under parallel execution. Registering a component with a step does not automatically make it thread-safe.

Principles:

- Readers with mutable cursors usually need per-step-execution instances or proper synchronization.
- Writers holding file/resource state must not share a single instance across concurrent steps unless explicitly designed for it.
- Listeners using mutable fields must isolate state per execution; avoid storing the current `StepExecution` in a singleton field.
- `ItemStream`s must use isolated context keys and avoid shared runtime state across executions.
- Use `@StepScope` when components depend on single-step-execution data.
- In partitioning, give each partition isolated resources/state or an explicitly designed sharing mechanism.

Example listener that should not store `StepExecution` in a singleton field:

```java
// Not recommended if the bean is used concurrently by multiple step executions
private StepExecution currentExecution;

@Override
public void beforeStep(StepExecution stepExecution) {
    this.currentExecution = stepExecution;
}
```

Instead, take the execution from the callback parameter and pass it into helper methods at the moment needed. When per-execution state is required, use step scope or the appropriate context.

## Testing Component Registration

Unit testing a component in isolation proves only its internal logic. Confirming proper step registration requires step/job tests proving callbacks fire and stream state persists.

### Testing That a Listener Is Invoked

Create a counting test double or use a mock:

```java
@Test
void registersStepExecutionListener() throws Exception {
    StepExecutionListener listener = mock(StepExecutionListener.class);
    Step step = new StepBuilder("testStep", jobRepository)
            .tasklet((contribution, chunkContext) -> RepeatStatus.FINISHED,
                    transactionManager)
            .listener(listener)
            .build();

    JobExecution execution = launchSingleStep(step);

    verify(listener).beforeStep(any(StepExecution.class));
    verify(listener).afterStep(any(StepExecution.class));
}
```

`launchSingleStep` is an application-defined test helper or can be replaced with `JobLauncherTestUtils`/`StepRunner` per your test setup. The test must run a real step to prove the builder registered the listener.

### Testing the ItemStream Lifecycle

Create a stream test double recording `open`, `update`, and `close`. Register it with `.stream(stream)` and run the step:

```java
ItemStream stream = new ItemStream() {
    @Override
    public void open(ExecutionContext context) {
        opened = true;
    }

    @Override
    public void update(ExecutionContext context) {
        updateCount++;
        context.putInt("testStream.counter", updateCount);
    }

    @Override
    public void close() {
        closed = true;
    }
};
```

Verify the stream opens, updates, and closes according to the step lifecycle. In chunk steps, confirm `update` is called at checkpoints. Never invoke callbacks directly in unit tests alone, as that does not prove the step registered the stream.

### Testing Delegates in Composites

Create a writer wrapper/composite holding a delegate implementing `ItemStream`. Run steps with and without `.stream(delegate)` in separate fixtures; confirm the delegate receives lifecycle callbacks when properly registered. Verify `open`/`close` are not called twice when the wrapper also forwards the lifecycle.

### Testing Restarts

Run a step across several chunks, then force the step to fail. Restart with identical identifying `JobParameters`; confirm stream `open` receives the saved context, reader/writer resume from the exact checkpoint, and outputs have no gaps or duplicates. Keep component names and resource paths identical across both runs.

### Testing Listener Exceptions

If a listener can throw exceptions, verify how the step/job reacts under real lifecycle and transaction boundaries. Do not let listeners silently swallow failures when callbacks enforce mandatory audits or business invariants.

## Common Mistakes

### Assuming Beans in Context Are Invoked Automatically by Steps

Beans must be attached to the step in their proper roles. Register listeners with `.listener(...)`, streams with `.stream(...)`, and readers/writers with their respective builder methods.

### Forgetting to Register Delegate ItemStreams

The step sees only the wrapper/composite and does not know the delegate needs `open`/`update`/`close`. Register the delegate via `.stream(...)` or have the wrapper forward the lifecycle.

### Registering a Stream Twice

A component may be auto-registered as a direct reader/writer and then also added via `.stream(...)`. Duplicate callbacks can double-open or mishandle resource closing. Explicitly register only unmanaged streams.

### Confusing Listeners with Streams

Listeners receive events; streams manage resources and checkpoints. A single component may need both, yet their callbacks differ.

### Attaching JobExecutionListener to a Step

Job listeners belong on `JobBuilder`; step listeners belong on `StepBuilder`. Choose the right lifecycle scope.

### Instantiating Components with new

Manual construction can bypass Spring DI, proxies, scopes, and lifecycles. Declare beans when components need dependencies or execution-specific state.

### Using Singletons with Mutable State

Concurrent executions can overwrite each other's fields. Use stateless components, `@StepScope`, or execution-isolated state.

### Failing to Hold Resources Across the Full Step

Releasing locks, connections, or file handles too early disrupts other components still using them in the step. Use the appropriate stream lifecycle.

### Performing Non-Idempotent Side Effects in Listeners

Retries/restarts can re-run callbacks or repeat business operations. Use idempotency/outboxes and align side effects with transaction boundaries.

### Testing Only the Component Without Testing Registration

A component passing direct calls does not prove the step registered its callbacks. Test real steps/jobs and verify lifecycles.

## Design Principles

When registering custom components in a step, verify:

1. Is the component a reader, processor, writer, tasklet, listener, or stream?
2. Is the component directly visible to the step or hidden inside a wrapper/delegate?
3. If implementing `ItemStream`, who calls `open`, `update`, and `close`?
4. If it is a listener, does it belong at job, step, chunk, or item scope?
5. Is the component Spring-managed with the right scope?
6. Is explicit `.stream(...)` or `.listener(...)` needed?
7. Is there any risk of duplicate registration or missed callbacks?
8. Does state/checkpointing use isolated keys compatible with restarts?
9. Is the component safe when multiple executions, threads, or partitions run concurrently?
10. Are side effects in callbacks idempotent and aligned with transaction boundaries?
11. Have integration tests confirmed callbacks and lifecycles actually run?

Configure readers/processors/writers/tasklets via the builder, register listeners in their proper lifecycle scopes, and explicitly register `ItemStream`s hidden behind wrappers/delegates. Keep components stateless or isolate state per step execution; use `ItemStream` for resources/checkpoints and listeners for events. Test real steps/jobs to verify components run once per contract, streams recover on restart, and side effects never duplicate data.

## Summary

Registering components in a step involves three distinct actions: attaching a reader/processor/writer or tasklet as the processing component, registering `ItemStream`s to manage `open`/`update`/`close` and checkpoints, and registering listeners for lifecycle callbacks. Components configured directly on a step are normally detected by Spring Batch; streams or listeners tucked inside wrappers/delegates may require explicit `.stream(...)` or `.listener(...)`. In XML, use `batch:streams` and `batch:listeners` in their XSD-defined locations. Never register the same stream twice, do not confuse listeners with streams, keep components safe under concurrent execution, and ensure state persists accurately for restarts. Verify by running real steps/jobs to confirm callbacks, stream lifecycles, delegate registration, and post-restart outputs.
