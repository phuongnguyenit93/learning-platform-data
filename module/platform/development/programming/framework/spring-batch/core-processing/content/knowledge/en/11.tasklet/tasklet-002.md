# RepeatStatus.FINISHED and CONTINUABLE

In Spring Batch, a `Tasklet` performs a unit of work inside a step and returns a `RepeatStatus` to indicate whether the tasklet has finished or needs to be called again. The two commonly used values are `RepeatStatus.FINISHED` and `RepeatStatus.CONTINUABLE`.

`FINISHED` ends the tasklet execution loop of the current step. `CONTINUABLE` asks Spring Batch to call `Tasklet.execute()` again within the same `StepExecution`. Therefore, `RepeatStatus` controls the repetition inside a tasklet step; it does not directly choose the next step in the job flow.

## 1. What is RepeatStatus?

`RepeatStatus` is the result of a single call to `Tasklet.execute`. A tasklet can perform part of the work and then return a status so that Spring Batch decides whether to keep calling the tasklet or stop the loop.

| Value | Meaning | Next behavior |
|---|---|---|
| `RepeatStatus.FINISHED` | The tasklet execution is complete | Spring Batch stops the tasklet step's loop |
| `RepeatStatus.CONTINUABLE` | There is still work to do | Spring Batch calls `Tasklet.execute()` again in the same step |

A simple example:

```java
public class CleanupTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        cleanupService.removeExpiredRecords();
        return RepeatStatus.FINISHED;
    }
}
```

The tasklet above only needs to perform the cleanup once, so it returns `FINISHED`. When the method returns, the tasklet step ends normally if there is no other error.

## 2. FINISHED stops the tasklet loop

When a tasklet returns `RepeatStatus.FINISHED`, Spring Batch understands that the tasklet does not need to be called again in the current step execution.

```text
TaskletStep starts
       |
       v
Tasklet.execute()
       |
       v
Returns FINISHED
       |
       v
execute() is not called again
       |
       v
Step proceeds to complete
```

`FINISHED` does not mean the entire JobExecution is complete at the moment of return. It only ends the tasklet step's loop. Afterwards, Spring Batch still performs the step completion procedures, updates the status, and continues the job flow if the job has other steps.

For example, a job with three steps:

```text
validateInput -> processFile (Tasklet returns FINISHED) -> archiveFile
```

After `processFile` returns `FINISHED`, Spring Batch can move on to `archiveFile` according to the declared flow. If `processFile` is the last step and completes successfully, the job can end with the status `COMPLETED`.

## 3. CONTINUABLE asks for Tasklet.execute to be called again

When a tasklet returns `RepeatStatus.CONTINUABLE`, Spring Batch continues the loop and calls that same tasklet again. These calls belong to the same `StepExecution`; the framework does not create a new step for each iteration.

```text
TaskletStep starts
       |
       v
Tasklet.execute() call 1
       |
       +-- CONTINUABLE
       |
       v
Tasklet.execute() call 2
       |
       +-- CONTINUABLE
       |
       v
Tasklet.execute() call 3
       |
       +-- FINISHED
       |
       v
TaskletStep ends the loop
```

`CONTINUABLE` is suitable when each tasklet call processes a finite part of the work, such as a page of data, a group of files, or a batch of records. The tasklet needs a way to determine the next part and a clear stop condition.

## 4. Example: processing data page by page

Suppose a tasklet needs to process a large data table. Instead of loading all the data into memory, each `execute()` call processes one page. The position of the next page is stored in the `ExecutionContext` so processing can continue after a restart.

```java
public class ProcessPagesTasklet implements Tasklet {

    private static final int PAGE_SIZE = 500;

    private final PageService pageService;

    public ProcessPagesTasklet(PageService pageService) {
        this.pageService = pageService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context =
            contribution.getStepExecution().getExecutionContext();

        int page = context.getInt("nextPage", 0);
        List<Record> records = pageService.loadPage(page, PAGE_SIZE);

        if (records.isEmpty()) {
            return RepeatStatus.FINISHED;
        }

        pageService.process(records);
        context.putInt("nextPage", page + 1);

        return RepeatStatus.CONTINUABLE;
    }
}
```

On each call, the tasklet reads the page number from the `ExecutionContext`, loads that page, and processes it. If there is no more data, the tasklet returns `FINISHED`. If it has processed a page, it stores the next page number and then returns `CONTINUABLE` to be called again.

In this example, when the last page contains data, the tasklet still returns `CONTINUABLE`; the next call reads an empty page and returns `FINISHED`. It can be optimized to return `FINISHED` right after processing a page shorter than `PAGE_SIZE`, provided the contract of `loadPage` guarantees that a short page is the last page.

### Declaring the TaskletStep

```java
@Bean
Step processPagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ProcessPagesTasklet processPagesTasklet) {

    return new StepBuilder("processPages", jobRepository)
        .tasklet(processPagesTasklet, transactionManager)
        .build();
}
```

`RepeatStatus` is returned from `execute()`, while `StepBuilder.tasklet(...)` declares the tasklet and the transaction manager for the step. Each tasklet call does not create a new `StepExecution`.

## 5. Transaction boundary between iterations

In a `TaskletStep`, each call to `Tasklet.execute()` is performed within the step's transaction. When the tasklet returns `CONTINUABLE`, the current call ends and Spring Batch continues with the next iteration according to the step's repeat mechanism.

This means a tasklet can process one unit of work in each transaction instead of holding one large transaction for the entire loop.

```text
Tasklet.execute() call 1
    process part A
    update ExecutionContext
    commit transaction 1
             |
             v
Tasklet.execute() call 2
    process part B
    update ExecutionContext
    commit transaction 2
             |
             v
Tasklet.execute() call 3
    return FINISHED
    commit transaction 3
```

Saving business data and the checkpoint can be committed together if they share the same transaction resource and an appropriate transaction manager. If the tasklet writes data to a different database or calls an external API, the step's transaction does not automatically roll back that side effect. Use an idempotency key, an outbox, or a reconciliation mechanism to handle retry/restart safely.

You should not perform a long-running operation or wait indefinitely inside `execute()`, because the transaction of that call may be held open for the whole waiting time. If you need to wait for an external service, use a finite timeout, limit the number of polling attempts, and apply an appropriate backoff.

## 6. Saving state between calls

When returning `CONTINUABLE`, a tasklet usually needs to know where to continue next time. The `StepExecution`'s `ExecutionContext` is a suitable place to store a checkpoint or the small amount of state needed to continue.

Examples of values that can be stored:

- The next page number or offset.
- The key of the last processed record.
- The next file name in the work list.
- The current batch code or processing phase.

`TaskletStep` coordinates updating the metadata and the `ExecutionContext` during the execution lifecycle. However, only save a checkpoint after the corresponding portion of work has been processed successfully. If you save the next position before the business data is committed, the job may skip data when an error occurs.

For large data or constantly changing sources, use keyset pagination or a stable cursor instead of an offset if adding/deleting records can change the page positions. Define a stable read order and a unique key to avoid skipping or duplicate processing.

### Example: storing the last processed key

```java
String lastId = context.getString("lastProcessedId", "");
List<Record> records = pageService.loadAfter(lastId, PAGE_SIZE);

if (records.isEmpty()) {
    return RepeatStatus.FINISHED;
}

pageService.process(records);
context.putString("lastProcessedId", records.get(records.size() - 1).id());
return RepeatStatus.CONTINUABLE;
```

This example assumes `id` has a stable order and `loadAfter` returns records whose ID is greater than the last key. With real data, you need to ensure the sort key does not change and that no two records share the same positioning key.

## 7. CONTINUABLE does not move to another step

`RepeatStatus` is often confused with `ExitStatus` or `BatchStatus`, but they serve different purposes.

| Status | Scope | Question answered |
|---|---|---|
| `RepeatStatus` | A single tasklet call and the tasklet step's loop | Should `Tasklet.execute()` be called again? |
| `ExitStatus` | The step's result, used in the job flow | With what result code did the step end? |
| `BatchStatus` | Execution lifecycle state | Is the execution running, completed, failed, or stopped? |

Examples:

- `RepeatStatus.CONTINUABLE`: call the same tasklet again in the same step.
- `RepeatStatus.FINISHED`: stop repeating the tasklet; the step proceeds to complete.
- `ExitStatus` such as `COMPLETED`, `FAILED`, or a custom code: used to decide a transition to another step or to end the job.
- `BatchStatus` such as `COMPLETED`, `FAILED`, `STOPPED`: reflects the execution state of the step/job.

If you need to move to another step based on a business result, use the job flow and transitions by `ExitStatus`, or a `JobExecutionDecider`. Returning `CONTINUABLE` does not make Spring Batch jump to the next step.

## 8. RepeatStatus in a Tasklet versus a chunk-oriented step

`RepeatStatus` belongs to the return contract of `Tasklet.execute()`. A chunk-oriented step uses `ItemReader`, `ItemProcessor`, and `ItemWriter` with a chunk loop managed by Spring Batch.

| Characteristic | TaskletStep | Chunk-oriented step |
|---|---|---|
| Processing unit | One call to `Tasklet.execute()` | One chunk of items |
| How it ends | The tasklet returns `FINISHED` | The reader signals the end of data with `null` and the last chunk completes |
| How it repeats | The tasklet returns `CONTINUABLE` | The framework reads and writes the following chunks |
| Main API | `Tasklet` and `RepeatStatus` | `ItemReader`, `ItemProcessor`, `ItemWriter` |

Do not return a `RepeatStatus` from `ItemReader.read()`. The reader returns `null` when the data is exhausted. You also do not need to write your own `CONTINUABLE` loop inside a processor or writer; Spring Batch controls the chunk loop.

Choose a Tasklet when the work is a custom operation or can be split into clear execution passes. Choose chunk-oriented processing when data needs to be read, processed, and written in groups with checkpoints and per-item/per-chunk fault tolerance.

## 9. Avoiding infinite loops

If a tasklet always returns `CONTINUABLE`, Spring Batch will keep calling it. A common mistake is a stop condition that is never reached, or progress state that is not updated correctly.

An example of the mistake:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    processCurrentBatch();
    return RepeatStatus.CONTINUABLE; // No stop condition
}
```

This tasklet can run forever until it is stopped, fails, or runs out of resources. Before returning `CONTINUABLE`, make sure the next iteration has a finite amount of work and can move closer to the end condition.

Control measures:

1. Define a clear stop condition, for example no more data pages or no more files.
2. Update the checkpoint after each portion of work completes.
3. Set a limit on the number of iterations or an overall deadline when the business requires it.
4. Log/emit metrics on the number of passes, the number of items, and progress to detect a tasklet that is not making progress.
5. Use a timeout and backoff when calling external systems.
6. If there is no new work, return `FINISHED` instead of continuing to poll without limit.

Do not use a long `Thread.sleep()` in a tasklet to wait for an event if it keeps a transaction open. For long waits, consider splitting into an orchestration step, a scheduler, a message queue, or an external waiting mechanism, then launching the job when the condition is met.

## 10. CONTINUABLE and errors/restart

If a tasklet call throws an exception, the current iteration fails and the step may end with the status `FAILED`, depending on error handling. When a valid JobInstance is restarted, Spring Batch creates a new JobExecution and can continue the step based on the metadata and the saved `ExecutionContext`.

For a safe restart, the tasklet needs to:

- Store enough checkpoint to determine the next portion of work.
- Update the checkpoint only after the corresponding data has been processed successfully.
- Be able to reprocess a portion of work if an error occurs before commit.
- Use idempotent operations or business keys for side effects that cannot be rolled back.
- Keep the key structure and the meaning of the data in the `ExecutionContext` compatible across deployments.

For example, if a tasklet processes page 5, writes the business data, and then updates `nextPage=6` in the same transaction, a restart can begin from page 6 after the transaction commits. If the transaction rolls back, the old checkpoint is still used and page 5 can be processed again. If the two operations are in two systems that do not share a transaction, you need to design for reconciliation and idempotency.

`CONTINUABLE` by itself does not save progress. It only asks for repetition. Saving state must be done by the tasklet and the related `ItemStream`/`ExecutionContext` components.

## 11. Common mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Always returning `CONTINUABLE` | The tasklet loops forever | Build a clear stop condition |
| Returning `FINISHED` while data remains | The work ends prematurely | Check the processing result and the source state before finishing |
| Using `CONTINUABLE` to move to another step | The flow does not transition as expected | Use transitions by `ExitStatus` or a decider |
| Not saving a checkpoint | A restart may start over from the beginning or not know the next portion | Store progress in the `ExecutionContext` |
| Updating the checkpoint before processing succeeds | Data may be skipped on error | Update the state after processing and within an appropriate transaction |
| Waiting indefinitely inside `execute()` | Holds the transaction and resources too long | Use a timeout, backoff, or an external orchestration mechanism |
| Non-idempotent side effects | The operation is repeated on retry/restart | Use an idempotency key, an outbox, or reconciliation |
| Using a Tasklet for a complex item pipeline without its own checkpoint | Hard to manage per-item retry/skip | Consider chunk-oriented processing |

## 12. Process for choosing a RepeatStatus

When implementing a tasklet, determine:

1. Can the work be completed in one call, or does it need multiple passes?
2. If it needs multiple passes, what finite unit does each pass process?
3. What is the exact condition for knowing there is no more work to do?
4. What progress needs to be stored in the `ExecutionContext`?
5. Can the business data and the checkpoint be committed in the same transaction?
6. If a pass is called again after a failure, is the operation safe and idempotent?
7. Is there a limit on the number of iterations, a timeout, or a mechanism to stop when there is no progress?

If the tasklet completes the work in one call, return `FINISHED`. If it has just finished one portion and there is a next portion, update the checkpoint and return `CONTINUABLE`. If you need to move to a different step, let the tasklet step end and define the transition in the job flow.

## Conclusion

`RepeatStatus.FINISHED` stops the tasklet execution loop, while `RepeatStatus.CONTINUABLE` asks Spring Batch to call `Tasklet.execute()` again within the same `StepExecution`. Each tasklet call in a `TaskletStep` is managed by the step's transaction, so you can split the work into multiple passes and store a checkpoint between passes.

`RepeatStatus` is not a job flow status and does not replace `ExitStatus` or `BatchStatus`. Use `CONTINUABLE` when there is a finite repetition condition, save progress at the right moment, avoid long waits inside a transaction, and ensure side effects are safe on retry or restart.
