# ExecutionContext of a Job and Step

In Spring Batch, `ExecutionContext` is a storage area for key/value pairs attached to the execution process. The framework uses it to hold state needed between processing stages, store checkpoints, and support restart when a Job is interrupted. There are two main scopes: the `ExecutionContext` of a `JobExecution` and the `ExecutionContext` of a `StepExecution`.

Both contexts have the type `ExecutionContext`, but they represent two different scopes. The Job context serves data that needs to exist at the scope of the whole Job and can be used by Steps. The Step context stores the state of a single Step execution, and is especially useful for reader or writer checkpoints.

## 1. What Is ExecutionContext?

`ExecutionContext` is a key/value data structure managed by Spring Batch. Each entry has a key name and a value. For example, a Step can store the number of records read, the ID of the last processed record, or the name of the input file in use.

```java
ExecutionContext context = new ExecutionContext();

context.putString("inputFile", "orders.csv");
context.putLong("lastProcessedId", 4200L);

String inputFile = context.getString("inputFile");
long lastProcessedId = context.getLong("lastProcessedId");
```

In a Spring Batch application, you normally do not create a new context yourself as in the example above to manage execution state. Get the context attached to the current `JobExecution` or `StepExecution`. Spring Batch and `JobRepository` are responsible for storing the context metadata according to the execution lifecycle.

ExecutionContext has these important characteristics:

- Data is organized by key so it can be read back at a later point in execution.
- The context belongs to a specific execution, not to the Job's static configuration.
- The framework stores the context in the metadata repository to support monitoring and restart.
- Values need to be handled by the serializer the application configures. Simple types such as String, numbers, and Serializable objects are more suitable than large objects or objects that depend on runtime resources.
- Keys need to be stable and clearly meaningful because code in the next run may depend on that very key.

ExecutionContext is the place to store execution state, not the place to store all business data. For example, storing the ID of the last committed record is usually more reasonable than storing a list of millions of records in the context.

## 2. Job ExecutionContext and Step ExecutionContext

Each `JobExecution` has a Job-level `ExecutionContext`. Each `StepExecution` has a Step-level `ExecutionContext`. A JobExecution can contain many StepExecutions, so in one Job run there can be one Job context and many Step contexts.

```text
JobExecution
  |
  +-- Job ExecutionContext
  |     +-- inputFile
  |     +-- businessDate
  |     +-- validatedRecordCount
  |
  +-- StepExecution: validateStep
  |     +-- Step ExecutionContext
  |           +-- currentLine
  |           +-- validationCheckpoint
  |
  +-- StepExecution: importStep
  |     +-- Step ExecutionContext
  |           +-- lastCommittedOrderId
  |           +-- readPosition
  |
  +-- StepExecution: reportStep
        +-- Step ExecutionContext
              +-- reportPage
```

| Criterion | Job ExecutionContext | Step ExecutionContext |
|---|---|---|
| Belongs to | One `JobExecution` | One `StepExecution` |
| Scope | The whole Job run | A specific Step run |
| Purpose | Holds state shared among Steps or needed at the Job scope | Holds the Step's own checkpoint and state |
| Usual save timing | Updated in the repository at Step completion boundaries | Saved at the Step's commit points and when the Step ends |
| Example | Business date, input path, number of records checked for later Steps to use | Reader position, last committed ID, page currently being processed |

A Step can access both contexts through the StepExecution:

```java
StepExecution stepExecution = contribution.getStepExecution();

ExecutionContext stepContext = stepExecution.getExecutionContext();
ExecutionContext jobContext = stepExecution.getJobExecution().getExecutionContext();
```

The two variables above both have the type `ExecutionContext`, but which variable you write to determines the scope and when the data is persisted.

## 3. Storing Data in the Job ExecutionContext

The Job context is suitable for data that many Steps need to use, or state that is meaningful at the scope of the whole Job run. For example, the first Step determines the input file and the next Step needs to read that file path again.

You can write to the Job context from code running in a Step:

```java
public class PrepareInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = contribution.getStepExecution().getJobExecution();
        ExecutionContext jobContext = jobExecution.getExecutionContext();

        jobContext.putString("inputFile", "data/orders-2026-11-15.csv");
        jobContext.putString("businessDate", "2026-11-15");

        return RepeatStatus.FINISHED;
    }
}
```

In the next Step, you can read the values back from the current JobExecution:

```java
public class ImportOrdersTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext jobContext = contribution.getStepExecution()
                .getJobExecution()
                .getExecutionContext();

        String inputFile = jobContext.getString("inputFile");
        String businessDate = jobContext.getString("businessDate");

        // Use inputFile and businessDate to perform the data import work.
        return RepeatStatus.FINISHED;
    }
}
```

The Job context is saved at Step boundaries. Therefore, when the next Step starts, it can read the Job context changes that were saved after the previous Step completed. If the Job fails while a Step is running, you should not assume that every new Job context change made in that Step has been saved immediately.

Use the Job context for data that needs to be shared at the Job scope. If you need fine-grained checkpoints within a running Step, the Step context is usually more suitable because it is saved at the Step's commit points.

## 4. Saving Checkpoints in the Step ExecutionContext

The Step context is commonly used to store a Step's processing progress. In chunk-oriented processing, a Step reads, processes, and writes data chunk by chunk. When a chunk commits successfully, Spring Batch can save the Step's state so a restart knows how far progress has been confirmed.

A stateful reader usually implements `ItemStream` (or an extending interface such as `ItemStreamReader`) to receive and update the ExecutionContext:

```java
public class CheckpointingReader implements ItemStreamReader<Order> {

    private int currentIndex;
    private List<Order> orders;

    @Override
    public void open(ExecutionContext executionContext) {
        currentIndex = executionContext.getInt("currentIndex", 0);
        orders = loadOrders();
    }

    @Override
    public Order read() {
        if (currentIndex >= orders.size()) {
            return null;
        }

        return orders.get(currentIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt("currentIndex", currentIndex);
    }

    @Override
    public void close() {
        // Release resources if the reader has opened any.
    }

    private List<Order> loadOrders() {
        // Illustrative example: load data from the input source.
        return List.of();
    }
}
```

Spring Batch calls `open` when the stream starts, passing in the restored Step ExecutionContext. The reader reads the saved position to continue. During processing, the framework calls `update` at the state-saving points so the reader writes its current checkpoint into the context. When the Step is restarted, `open` receives the saved checkpoint again.

The code above illustrates the mechanism; a real reader needs to ensure the checkpoint position corresponds to the data that has been committed. With a data source that can change, storing only a row index may not be enough. You may need to store a stable key, an offset, or a token provided by the data source.

Built-in readers and writers such as `FlatFileItemReader` already support the stream mechanism and state saving when configured appropriately. When using an existing component, you need to keep its state saving enabled if you want to support restart; do not implement a checkpoint yourself if the component already manages progress safely.

## 5. Sharing Data from the Step Context to the Job Context

A common case is that the first Step computes a value and the next Step needs to use it. You can write the result into the Step context and then use `ExecutionContextPromotionListener` to promote some keys to the Job context after the Step completes successfully.

In the Step that produces the data, store the value in the Step ExecutionContext:

```java
public class ValidateOrdersTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext stepContext = contribution.getStepExecution()
                .getExecutionContext();

        long validatedCount = validateInput();
        stepContext.putLong("validatedCount", validatedCount);

        return RepeatStatus.FINISHED;
    }

    private long validateInput() {
        // Perform the check and return the number of valid records.
        return 250L;
    }
}
```

Declare the promotion listener for the Step:

```java
@Bean
public ExecutionContextPromotionListener validationPromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"validatedCount"});
    listener.setStatuses(new String[] {"COMPLETED"});
    return listener;
}
```

Register the listener in the Step configuration:

```java
@Bean
public Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ValidateOrdersTasklet tasklet,
        ExecutionContextPromotionListener validationPromotionListener) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .listener(validationPromotionListener)
            .build();
}
```

After the Step completes with a suitable exit code, the listener copies the specified keys from the Step ExecutionContext to the Job ExecutionContext. A later Step can read the value from the Job context:

```java
long validatedCount = contribution.getStepExecution()
        .getJobExecution()
        .getExecutionContext()
        .getLong("validatedCount");
```

Promotion is useful when you want a Step to keep internal data while running, and then publish only some necessary results to the rest of the Job. Configure an explicit list of keys and only promote data that later Steps truly need.

## 6. When Context Is Saved and Restored

Save timing is an important point when designing restart:

| Context | Usual Save Timing | Meaning on Restart |
|---|---|---|
| Step ExecutionContext | At the Step's commit points; updated when the Step ends | Can restore the Step's most recent saved checkpoint |
| Job ExecutionContext | At each Step's completion boundary | The next Step or a restart can use the Job state that was saved after the previous Step |

With a chunk-oriented Step, Step context changes are tied to the commit boundary. If a chunk fails and the transaction rolls back, that chunk's checkpoint should not be considered committed. On restart, the reader needs to continue from a checkpoint consistent with the committed data.

The Job context is not designed to replace per-chunk checkpoints. If a Step processes millions of records and only writes the processed count into the Job context, that value may not reflect the latest progress when the Step fails midway. Store fine-grained progress in the Step context or in the reader/writer's appropriate checkpoint mechanism.

Storing metadata and the business data transaction needs to be designed consistently. With a usual repository and transaction configuration, Spring Batch coordinates state updates at the processing boundary. However, if business data lives in a different system or transaction manager, you need to consider failures between two commits and design safe repeat processing (idempotent) or a reconciliation mechanism.

## 7. Distinguishing ExecutionContext from JobParameters

`JobParameters` and `ExecutionContext` can both contain data related to a run, but their purposes differ:

| Criterion | JobParameters | ExecutionContext |
|---|---|---|
| Role | Input when launching the Job | State that arises during execution |
| Provided by | The application or scheduler calling JobLauncher | The Job/Step and components during the run |
| Example contents | Business date, file path, processing mode | Reader position, number of records checked, last committed ID |
| Identifying | Can be marked identifying to determine the JobInstance | Not used to determine the JobInstance |
| Changes during the run | Treated as the run's input parameters | Updated to store progress and state |

For example, `businessDate=2026-11-15` can be an identifying JobParameter to determine the data-import job for that date. Meanwhile, `lastProcessedOrderId=4200` is a checkpoint that arises during the run and suits the Step ExecutionContext.

You should not use ExecutionContext to replace input data that the scheduler needs to provide explicitly. Nor should you try to change JobParameters to store progress; use the context in the right scope.

## 8. Rules for Designing Keys and Values

ExecutionContext is stored longer than the lifetime of a Java method or object. Therefore, you need to design keys and values to be stable:

- Use descriptive keys, such as `lastCommittedOrderId` instead of `x1`.
- Avoid key collisions among components within the same context. You can add a Step or component name prefix, for example `importOrders.lastCommittedId`.
- Only store small values needed for orchestration or restart; large business data should live in a database or object storage.
- Choose data types that the configured serializer supports and keep them compatible when deploying new application versions.
- Avoid storing connections, streams, threads, file handles, or objects that depend on runtime state; these resources need to be reopened in a new execution.
- Do not store passwords, access tokens, or secrets in the context without a suitable protection mechanism, because metadata may be stored in a database and looked up by operators.
- Be careful when modifying a mutable object already placed in the context: the framework tracks the context's changed state through put/remove operations and does not necessarily notice every change inside an object. Prefer immutable values or reset the value with `put` after updating.

If the structure of data stored in the context changes between application versions, you need to consider the ability to read old contexts on restart. For example, changing a key's data type or renaming a key can make new code unable to read metadata created by the previous version. You can maintain compatibility by supporting the old key during a transition period or proactively finishing old executions before deploying the change.

## 9. Common Misunderstandings

**Using the Job context to store a checkpoint for each chunk.** The Job context is usually saved at Step boundaries. Use the Step context for fine-grained progress within a running Step.

**Thinking the two contexts are a single data area.** The Job context and Step context have different scopes and save lifecycles. Writing a key to the Step context does not automatically make the key appear in the Job context; use a promotion listener when you need to move data.

**Thinking every context change is written to the database immediately.** Save timing depends on the context scope and the commit/Step boundary. Restart design must rely on checkpoints that have been saved.

**Storing entire business objects in the context.** The context serves metadata and checkpoints. Storing large data makes metadata heavy, increases serialization cost, and makes it hard to change object structure.

**Using JobParameters to record progress.** JobParameters are the input that identifies a run; ExecutionContext is where state that arises during the run is stored.

**Assuming the Step context is automatically shared with the next Step.** The Step context belongs to one StepExecution. To let a later Step read a value, store it in the Job context or promote it from the Step context.

## 10. Choosing the Right Context for Each Need

When you need a reader to continue from its read position after a restart, store the checkpoint in the Step ExecutionContext. When the first Step determines a value that many later Steps need, store it in the Job ExecutionContext or promote the key from the Step context. When the scheduler passes the business date or the input file path, use JobParameters. When large data needs to be processed, store the data in the business store and keep only a small key or checkpoint in the context.

Correctly distinguishing the Job and Step scopes helps Spring Batch restore progress consistently, share data among Steps deliberately, and avoid depending on state that exists only in the memory of a single run.
