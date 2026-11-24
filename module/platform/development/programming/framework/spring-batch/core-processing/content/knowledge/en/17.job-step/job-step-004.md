# JobStep execution context

Spring Batch provides `ExecutionContext` to store the runtime state of a Job and a Step. The context is a key/value structure persisted by `JobRepository` along with execution metadata, enabling components in a workflow to share information and allowing readers or writers to restore checkpoints when a Job is restarted.

There are two context scopes to distinguish: Job ExecutionContext and Step ExecutionContext. Job context is used to share a small amount of metadata across Steps within the same `JobExecution`. Step context holds the private state of a single `StepExecution`, typically the read position, writer state, or data needed to resume the Step after an error.

Understanding these two scopes properly helps you choose the right place to store data, pass information between Steps, configure scope expressions, and design reliable restarts.

## 1. What is ExecutionContext?

`ExecutionContext` is a key/value storage area attached to an execution. Each key is a string and each value is data that Spring Batch's serializer can save and restore.

Example:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("input.fileVersion", "orders-v4");
context.putLong("reader.lastCustomerId", 8500L);
context.putInt("reader.page", 12);
context.putBoolean("validation.completed", true);
~~~

These values do not live only inside a Java object. When Spring Batch updates metadata via `JobRepository`, the context is serialized and saved to the repository. When the execution is reloaded or restarted, the framework restores the saved values.

`ExecutionContext` is suitable for small metadata and checkpoints. Do not use it as a store for entire business datasets, large item lists, or file contents. For large data, store it in a database, file, or object storage and place the ID or path into the context.

## 2. Two Scopes: Job Context and Step Context

Each `JobExecution` has one Job ExecutionContext. Each `StepExecution` has its own Step ExecutionContext.

| Characteristic | Job ExecutionContext | Step ExecutionContext |
|---|---|---|
| Scope | One `JobExecution` | One `StepExecution` |
| Primary purpose | Share metadata between Steps | Store Step-specific state |
| Examples | Prepared file path, batch code, resolved business date | Reader position, page number, writer checkpoint |
| Typical persist timing | When a Step completes and `JobExecution` is updated | At Step checkpoints/commits and when the Step finishes |
| On restart | Context from the previous execution is used to initialize the new execution per restart mechanism | State of the prior Step is used to restore the Step that needs to re-run |

Job context is shared among Steps within the same Job run. Step context is isolated per `StepExecution` so one Step does not accidentally overwrite another Step's internal checkpoint.

Example of an order import Job:

~~~text
JobExecution
  Job ExecutionContext
    businessDate = 2026-11-15
    validatedFile = /data/batch/validated.csv

  Step validateInput
    Step ExecutionContext
      sourceLine = 1200
      validationCount = 1200

  Step importOrders
    Step ExecutionContext
      reader.lastId = 9500
      writer.lastCommittedId = 9500

  Step createReport
    Step ExecutionContext
      reportPage = 4
~~~

The `importOrders` Step can read `validatedFile` from the Job context while keeping `reader.lastId` in its own Step context.

## 3. Accessing Job ExecutionContext and Step ExecutionContext

From `StepExecution`, both scopes can be accessed:

~~~java
JobExecution jobExecution =
        stepExecution.getJobExecution();

ExecutionContext jobContext =
        jobExecution.getExecutionContext();

ExecutionContext stepContext =
        stepExecution.getExecutionContext();
~~~

Writing a value to Job context:

~~~java
jobContext.putString(
        "validatedFile",
        "/data/batch/validated-orders.csv");
~~~

Writing a value to Step context:

~~~java
stepContext.putLong("reader.lastId", 9500L);
~~~

Inside a Tasklet, you can obtain `StepExecution` via `contribution`:

~~~java
@Bean
Tasklet prepareInputTasklet() {
    return (contribution, chunkContext) -> {
        StepExecution stepExecution = contribution.getStepExecution();
        JobExecution jobExecution = stepExecution.getJobExecution();

        jobExecution.getExecutionContext()
                .putString(
                        "validatedFile",
                        "/data/batch/validated-orders.csv");

        stepExecution.getExecutionContext()
                .putLong("validation.recordCount", 1200L);

        return RepeatStatus.FINISHED;
    };
}
~~~

The Tasklet writes the file path into Job context for a later Step to use. The checked record count is stored in Step context because it is state belonging specifically to the data preparation Step.

Do not use Job context to store every piece of state just because it is easy to access. Place each key in the narrowest scope that satisfies its usage.

## 4. Sharing Small Data Between Steps

A common case is when an earlier Step produces information that a later Step needs.

Example:

~~~text
validateInputStep
      |
      | creates validated file
      | saves validatedFile to Job context
      v
importOrdersStep
      |
      | reads validatedFile
      v
createReportStep
~~~

The first Step can write the path to Job ExecutionContext:

~~~java
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String validatedFile =
                "/data/batch/validated-orders.csv";

        JobExecution jobExecution =
                contribution.getStepExecution().getJobExecution();

        jobExecution.getExecutionContext()
                .putString("validatedFile", validatedFile);

        return RepeatStatus.FINISHED;
    }
}
~~~

The subsequent Step uses Job context to receive the path. With a Step-scoped bean, the value can be injected via an expression:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> validatedOrderReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("validatedOrderReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper(orderLineMapper())
            .saveState(true)
            .build();
}
~~~

`@StepScope` defers reader creation until the Step starts, at which point Job ExecutionContext can already be resolved. The reader only receives the path and reads the data; the file contents are not placed into the context.

Ensure the file-creating Step finishes successfully before the reading Step starts. If the file can be deleted or altered between runs, also store a version code, checksum, or batch ID to verify that the next Step uses the right output.

## 5. Using Step ExecutionContext for Checkpoints

Stateful readers and writers typically use Step context to store recovery information. For example, a reader needs to know the next record after a restart.

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private static final String LAST_ID =
            "customerReader.lastId";

    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
                ? context.getLong(LAST_ID)
                : 0L;
    }

    @Override
    public Customer read() {
        Customer next = loadCustomerAfter(lastId);

        if (next != null) {
            lastId = next.getId();
        }

        return next;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastId);
    }

    @Override
    public void close() {
        // Close resource if the reader opened one.
    }
}
~~~

This is an illustrative example; `loadCustomerAfter` must be implemented against the actual data source. The reader saves the last read ID in Step context. When the Step restarts, `open()` receives the saved context and resumes after the corresponding ID.

For a chunk-oriented Step, Spring Batch invokes the `ItemStream` lifecycle to update state at checkpoints. Step context is therefore the right place for read positions or writer state that must be recovered along commit boundaries.

Do not use Job context as the place to store each reader's internal read position. If a Job has multiple Steps or multiple partitions, reader state can collide across executions if shared keys are used at too broad a scope.

## 6. Promoting Values from Step Context to Job Context

There are cases where a component should write state to Step context, yet a later Step needs some of those values. Spring Batch provides `ExecutionContextPromotionListener` to select keys to promote from Step context to Job context when the Step finishes in a configured status.

Listener example:

~~~java
@Bean
ExecutionContextPromotionListener promoteValidatedFile() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] { "validatedFile" });
    return listener;
}
~~~

Register the listener on the Step that produces the value:

~~~java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet,
        ExecutionContextPromotionListener promoteValidatedFile) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateInputTasklet, transactionManager)
            .listener(promoteValidatedFile)
            .build();
}
~~~

The Tasklet writes the key into Step context:

~~~java
contribution.getStepExecution()
        .getExecutionContext()
        .putString(
                "validatedFile",
                "/data/batch/validated-orders.csv");
~~~

When the Step finishes with a status accepted by the promotion listener, the `validatedFile` key is promoted to Job context. The subsequent Step can access it via `jobExecutionContext`.

By default, the listener typically promotes on `COMPLETED` status; you can configure the list of statuses using `setStatuses` if business logic requires another condition. Promote only the keys that need sharing; do not copy the entire Step context up to Job context.

Promotion helps separate internal state from information published for other Steps. A reader can keep its checkpoint in Step context while only the output file path is promoted to Job context.

## 7. How Does JobParameters Differ from ExecutionContext?

`JobParameters` and `ExecutionContext` can both hold values used by a Step, but their purposes differ.

| Attribute | JobParameters | ExecutionContext |
|---|---|---|
| Role | Input of `JobInstance`/`JobExecution` | State generated during execution |
| Typical provider | `JobLauncher`, scheduler, or caller | Reader, writer, Step, or Job logic |
| Used to identify `JobInstance` | Identifying parameters participate | No |
| Mutated during execution | Not used to update checkpoints | Can be updated via context API |
| Examples | `businessDate`, `sourceFileId`, `tenant` | `validatedFile`, `lastReadId`, `pageNumber` |

Example:

~~~text
JobParameters
  businessDate = 2026-11-15
  sourceFileId = file-8421

Job ExecutionContext
  validatedFile = /data/batch/validated-orders.csv

Step ExecutionContext
  customerReader.lastId = 9500
~~~

`JobParameters` describe the requested work. Job context stores shared runtime metadata. Step context stores the Step's internal checkpoints.

Do not put passwords or tokens into `JobParameters` or `ExecutionContext`. Non-identifying parameters can still be persisted in metadata; the identifying flag is not a security mechanism.

## 8. Accessing Context via Scope Expressions

Spring Batch provides scope expressions for Step-scoped or Job-scoped beans.

Common expressions:

| Expression | Value Accessed |
|---|---|
| `jobParameters['inputFile']` | `JobParameter` with key `inputFile` |
| `jobExecutionContext['validatedFile']` | Key in Job ExecutionContext |
| `stepExecutionContext['reader.lastId']` | Key in Step ExecutionContext |

Example of a reader receiving a path from Job context:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String inputFile) {
    // Create reader from the file prepared by the previous Step.
}
~~~

Example of a Tasklet receiving a checkpoint value or Step-specific configuration:

~~~java
@Bean
@StepScope
Tasklet processPartitionTasklet(
        @Value("#{stepExecutionContext['partitionStart']}")
        Long startId,
        @Value("#{stepExecutionContext['partitionEnd']}")
        Long endId) {
    // Process the ID range of the current partition.
}
~~~

Runtime values are only available when the corresponding scope is active. If injected directly into a singleton bean at application startup, the expression cannot be resolved because there is no current `StepExecution` or `JobExecution` yet.

## 9. Persistence Timing and Consistency

Calling `put()` updates `ExecutionContext` in memory. It does not mean the value is written to the database immediately at that line of code.

For Step context, Spring Batch saves state along the Step lifecycle and chunk checkpoints. For Job context, changes made within a Step are normally persisted when the Step completes and `JobExecution` is updated. Therefore, do not use Job context as a per-chunk checkpoint mechanism.

High-level flow:

~~~text
Running Step
   |
   +--> updates Step ExecutionContext
   |       |
   |       +--> checkpoint per chunk
   |               |
   |               v
   |           JobRepository
   |
   +--> updates Job ExecutionContext
           |
           +--> Step completes
                   |
                   v
               JobRepository
~~~

If Job context is updated mid-Step, a later Step in the same `JobExecution` can use that value after the current Step completes and the flow transitions. If the process stops before the context is persisted, unsaved changes may be lost upon restart.

If you need state saved regularly per chunk for restart, use Step ExecutionContext and the `ItemStream` lifecycle. Do not rely on a key in Job context as if it were checkpointed with every chunk.

## 10. Restart and Context Recovery

When a `JobExecution` fails and the `JobInstance` is restarted, Spring Batch creates a new `JobExecution` for the same `JobInstance` if status and configuration permit. Saved context from the previous execution is used to initialize the new execution according to the restart mechanism.

For Steps already completed, the flow normally skips them. For a Step that needs to re-run, the framework restores Step context from saved state if the Step and its components support restart.

Example:

~~~text
JobInstance: importOrders, businessDate=2026-11-15

JobExecution 101:
  validateInputStep -> COMPLETED
  importOrdersStep  -> FAILED
      reader.lastId = 9500
  createReportStep  -> NOT STARTED

JobExecution 108 (restart):
  validateInputStep -> skipped (already completed)
  importOrdersStep  -> checkpoint restored
      reader resumes after ID 9500
  createReportStep  -> runs after importOrdersStep completes
~~~

For restart to work properly:

- Keep identifying `JobParameters` unchanged to resume the same `JobInstance`.
- Keep Step names stable while old metadata is still needed.
- Keep context keys and their semantics compatible across versions.
- Ensure referenced files or source/target data still exist.
- Readers and writers must support `ItemStream` if state recovery is required.
- Do not mutate source data in ways that cause old checkpoints to point to different records.

If a previous Step completed and created a file for the next Step, that file must still exist on restart. Checkpoint metadata does not recreate the contents of a deleted file.

## 11. Job Context Does Not Replace a Business Data Store

`ExecutionContext` is designed for small metadata, not for passing entire datasets between Steps.

Do not store:

- Lists of thousands or millions of entities.
- Entire JSON/XML payloads.
- Large file contents or binary data.
- JPA entity graphs with lazy relationships.
- Open JDBC Connections, streams, threads, or resources.

Instead, store references:

~~~java
jobExecution.getExecutionContext()
        .putLong("staging.batchId", 8421L);

jobExecution.getExecutionContext()
        .putString(
                "staging.file",
                "/data/batch/staging/orders-8421.csv");
~~~

The subsequent Step uses the batch ID to query the staging table or uses the path to open the file. This keeps the context small, easy to serialize, and easy to recover.

If a later Step needs a large amount of data produced by an earlier Step, store the data in a staging table or durable file and pass only the ID, filename, version, or checksum through the context.

## 12. Serialization and Data Types in Context

`JobRepository` must serialize the context to persist metadata. Data types placed into the context must be supported by the configured serializer.

Simple types such as `String`, `Long`, `Integer`, and `Boolean` are usually easy to manage. Custom objects can introduce dependencies on classes and object structure when the application is upgraded.

Examples to prefer:

~~~java
context.putLong("lastProcessedId", 9500L);
context.putString("source.version", "v4");
context.putBoolean("validation.completed", true);
~~~

Avoid storing large business objects or non-serializable resources:

~~~java
// Do not store open resources or large object graphs.
context.put("connection", connection);
context.put("bufferedReader", bufferedReader);
context.put("customerAggregate", customerAggregate);
~~~

If the serializer cannot save a value, the error may surface when the framework persists context at a checkpoint or when the Step ends, not necessarily right at the `put()` call. When designing context usage, test round-trip serialization with the actual serializer and keep keys/values stable across versions.

## 13. Key Naming and Versioning

A Job can have multiple readers, writers, and Steps writing to context together. Keys should be namespaced to avoid collisions:

~~~text
validateInput.outputFile
customerReader.lastId
customerReader.page
orderWriter.lastCommittedId
reportWriter.currentPage
~~~

Avoid overly generic keys like `status`, `count`, or `position` if multiple components share the context.

When changing state structure, consider versioning:

~~~java
private static final String STATE_VERSION =
        "customerReader.stateVersion";

private static final String LAST_ID =
        "customerReader.lastId";

void saveState(ExecutionContext context, long lastId) {
    context.putInt(STATE_VERSION, 2);
    context.putLong(LAST_ID, lastId);
}
~~~

When opening the reader, code can inspect the version and support any remaining state formats. Do not arbitrarily delete or rename old keys while executions still exist that may need to restart from metadata created by a previous application version.

## 14. Context in Partitioning and Parallel Execution

In a partitioned Step, each partition has its own `StepExecution` and Step ExecutionContext. This is the appropriate place to store the partition's data range, such as start and end IDs.

~~~text
Master Step
   |
   +--> Partition 1
   |      Step context: startId=1, endId=1000
   |
   +--> Partition 2
   |      Step context: startId=1001, endId=2000
   |
   +--> Partition 3
          Step context: startId=2001, endId=3000
~~~

Worker Steps can read these values using `stepExecutionContext` expressions. Each partition keeps separate state so it can restart independently under the partitioning model.

Job ExecutionContext is a shared area scoped to the `JobExecution`. If multiple branches or workers concurrently update a key in Job context, overwrites or lost updates can occur depending on synchronization and persistence behavior. Do not use Job context as a mutable shared area across multiple worker threads. Use separate Step contexts, a database, or an appropriate synchronization mechanism for concurrently shared data.

## 15. Data Security in ExecutionContext

Context is stored in the metadata repository. Serialization does not mean encryption. If you put passwords, API tokens, private keys, or credentials into the context, those values can be stored and queried alongside metadata.

Do not store secrets in Job context or Step context. Use a secret manager and store only a non-sensitive reference if a Step needs to know which secret to retrieve.

Also control personal data in the context. Only store information genuinely needed for restart and restrict `JobRepository` read permissions by role. Database encryption at rest is an additional layer of protection, not a substitute for avoiding unnecessary storage of sensitive data.

## 16. Common Mistakes

**Using the wrong context scope.** Saving a reader checkpoint in Job context exposes Step-internal state too broadly. Use Step context for private state, and Job context for metadata shared between Steps.

**Assuming put() writes immediately to the repository.** Values are persisted according to Spring Batch's lifecycle and transactions. Do not query the database right after `put()` assuming it is already saved.

**Using Job context for per-chunk checkpoints.** Job context is typically updated when a Step completes; per-chunk state belongs in Step context via `ItemStream`.

**Storing large datasets.** Bloated contexts increase serialization, database, backup, and restore costs. Store IDs or references to a data store.

**Forgetting to promote keys that need sharing.** If state stays only in Step context, a later Step will not automatically see it via Job context. Use `ExecutionContextPromotionListener` or write directly to Job context by design.

**Using generic keys.** Components can overwrite each other's values. Namespace keys by Step or component name.

**Changing keys or data types across restarts.** Old executions may fail to recover. Maintain compatibility or use a versioning strategy.

**Using context as a thread synchronization mechanism.** Context does not replace locks, queues, or database coordination when multiple workers update state concurrently.

**Storing secrets or resources.** Credentials and objects like Connections/streams are unsuitable for persistence. Use a secret manager and reopen resources through lifecycle callbacks.

## 17. Testing Job and Step ExecutionContext

Test the values written, the persistence timing, and recovery capability.

Scenarios to include:

| Scenario | What to Verify |
|---|---|
| Step writes Job context | Subsequent Step reads the key after the prior Step completes |
| Step writes Step context | Checkpoint is stored within the right `StepExecution` scope |
| Promotion listener | Only selected keys are promoted to Job context |
| Restart after failure | Reader/writer restores committed state |
| Multi-step Job | Keys do not collide across Steps |
| Partitioning | Each partition has its own context and range |
| Non-serializable data | Error is detected and diagnosed properly |
| Large context | Design uses references instead of payloads |
| Application upgrade | Old keys and data types remain readable when restart is needed |

An integration test can run the Job the first time, intentionally make a Step fail after a checkpoint, then restart the same `JobInstance` and verify the Step resumes at the exact position. Use a real `JobRepository` in the test environment to verify that context is persisted and reloaded.

Do not check only the in-memory context object. Verify that the repository saved state at the appropriate time and that the new execution actually recovers the required keys.

## 18. Process for Choosing Where to Store Context

When a Step needs to keep or share a value, ask yourself:

1. Is this value a fixed input to the Job? If yes, consider `JobParameters`.
2. Does the value serve only as an internal checkpoint of a single Step? Use Step ExecutionContext.
3. Does a later Step need a value produced by an earlier Step? Use Job ExecutionContext or a promotion listener.
4. Is the value large business data? Store it in a database/file/object storage and put only the ID or reference in the context.
5. Does the value need to survive restarts? Ensure the context is persisted and data types remain compatible.
6. Is the value sensitive? Do not store secrets or unnecessary personal data.
7. Are multiple partitions or workers updating concurrently? Use per-`StepExecution` state or a synchronized storage mechanism.

Job ExecutionContext and Step ExecutionContext are complementary tools. Job context lets Steps coordinate using small metadata; Step context holds private checkpoints so readers, writers, and Steps can resume after failure. When data is placed in the right scope, persisted via lifecycle callbacks, and kept compact, a Job can share information and restart without turning metadata into a business data store.

