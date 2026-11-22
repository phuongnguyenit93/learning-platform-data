# Atomic rename file

An atomic rename is a way to publish a completed output file so that downstream consumers never observe the file while Spring Batch is still writing it. The job writes to a temporary path first. After the writing step has completed and closed the file, a later step renames that temporary file to its final name in one filesystem operation.

This pattern improves **output consistency**. A consumer that opens the final path sees a complete published file, while an incomplete run leaves its temporary file under a name that consumers ignore.

## Why a normal output file can be inconsistent

An item writer usually writes records over time. For example, a `FlatFileItemWriter` may write several chunks during a step. Chunk transactions control the step's transactional work, but they do not make the whole output file appear at once. A process that reads the destination while the step is running can therefore see only the records written so far.

That can cause problems when another application treats the existence of a file as a signal that the export is ready. It might read a truncated CSV, process only part of a report, or move the file before the batch job has finished.

Writing to a staging name separates file creation from file publication:

```text
orders.csv.part     <- Spring Batch writes here
orders.csv          <- consumers read this only after publication
```

The `.part` suffix is a convention. Choose a temporary name that downstream applications do not scan as a completed output.

## The publication sequence

1. **Choose both paths.** Put the temporary file and final file in the same directory, and therefore on the same filesystem. Give each job instance or business output a well-defined path.
2. **Write the temporary file.** Configure the item writer to use the temporary path. Let the writer manage its normal buffering and restart state.
3. **Wait for the writer step to finish.** Spring Batch closes the step's streams as the step ends. A following step runs after that lifecycle has completed, so the file is no longer being written by the item writer.
4. **Publish only after success.** Add a finalization step after the writing step. It moves the temporary path to the final path only when the earlier step has completed successfully.
5. **Have consumers watch the final name.** Consumers should ignore temporary names and process only files that have been published.

Using a separate finalization step makes publication part of the job flow. If the move fails, Spring Batch can record the publication step as failed and the job does not report a successful run.

## Configure the writer to use a temporary resource

The important part of the writer configuration is its resource. It points to the staging file rather than the name that consumers use.

```java
@Bean
FlatFileItemWriter<Order> orderWriter(
        @Value("${batch.output.temp}") Resource temporaryResource) {
    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(temporaryResource)
            .lineAggregator(order ->
                    order.id() + "," + order.amount())
            .saveState(true)
            .build();
}
```

For a restartable job, keep the temporary path stable when restarting the same `JobInstance`, and keep the writer's saved state enabled. Spring Batch can then use the `ExecutionContext` to resume the writer at the appropriate position. A new job instance should receive its own temporary path so that two executions do not write to the same file.

For example, the paths can be supplied as job-specific configuration:

```properties
batch.output.temp=/var/app/output/orders-2026-11-15-42.csv.part
batch.output.final=/var/app/output/orders-2026-11-15-42.csv
```

The date and execution identifier above are illustrative. In a real job, derive the paths from the job parameters or persist the chosen path in the job execution context. Keep both paths on the same filesystem.

## Publish the file with a tasklet

The finalization tasklet performs the rename. It checks that the staging file exists and then asks the filesystem provider for an atomic move.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public final class PublishOutputTasklet implements Tasklet {

    private final Path temporaryFile;
    private final Path finalFile;

    public PublishOutputTasklet(Path temporaryFile, Path finalFile) {
        this.temporaryFile = temporaryFile;
        this.finalFile = finalFile;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        if (!Files.isRegularFile(temporaryFile)) {
            throw new IllegalStateException(
                    "Temporary output file does not exist: " + temporaryFile);
        }

        Files.move(
                temporaryFile,
                finalFile,
                StandardCopyOption.ATOMIC_MOVE);

        return RepeatStatus.FINISHED;
    }
}
```

Wire the tasklet into a step that follows the step containing the writer:

```java
@Bean
Step publishOutputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PublishOutputTasklet publishOutputTasklet) {
    return new StepBuilder("publishOutput", jobRepository)
            .tasklet(publishOutputTasklet, transactionManager)
            .build();
}

@Bean
Job exportOrdersJob(
        JobRepository jobRepository,
        Step writeOrdersStep,
        Step publishOutputStep) {
    return new JobBuilder("exportOrders", jobRepository)
            .start(writeOrdersStep)
            .next(publishOutputStep)
            .build();
}
```

Create the `PublishOutputTasklet` bean with the configured temporary and final paths. The sequence matters: `publishOutputStep` must run after `writeOrdersStep`, not in parallel with it. Spring Batch only reaches the next step when the previous step completes successfully.

The tasklet lets an `IOException` or `AtomicMoveNotSupportedException` escape. Spring Batch then records the step failure. Do not catch an atomic-move failure and silently copy the file instead; copying can expose a partially copied final file and removes the consistency guarantee this pattern is intended to provide.

## What makes the rename atomic

Atomicity is a property of the filesystem operation, not of the Spring Batch transaction. When the filesystem supports an atomic move, the directory entry changes as one operation. A process opening the final path sees the published file after the rename; it does not see the file gradually copied into that name.

There are practical limits:

- **Keep the paths on one filesystem.** A move across filesystem boundaries commonly becomes a copy-and-delete operation and cannot provide the same atomic visibility. Using the same directory for both paths is the simplest arrangement.
- **Check filesystem support.** Java's `ATOMIC_MOVE` option can throw `AtomicMoveNotSupportedException` when the provider cannot perform the operation atomically. Treat that as a publication failure and choose a supported storage design.
- **Decide what happens when the final name already exists.** With `ATOMIC_MOVE`, Java specifies that behavior for an existing target is implementation-dependent. A unique final name per run avoids an ambiguous replacement policy. If the job must replace a stable filename, verify the target filesystem's replacement behavior and test it on the deployment platform.
- **Atomic visibility is not the same as durable storage.** Closing the writer before the move ensures its normal output stream is finished. Applications with strict power-loss durability requirements may also need filesystem-specific flushing of file data and directory metadata.

## Restart and concurrent execution

The temporary path is part of the job's restart design. A restart of the same `JobInstance` must be able to find the same staging file and the writer's saved state. If the path changes on every restart, the writer may start a different file instead of resuming the original output.

Separate job instances need separate temporary paths. Otherwise, concurrent executions can overwrite or rename each other's output. If several executions are allowed to publish to one stable destination, define an explicit ownership or locking rule for that destination.

Consider the failure points:

| Failure point | Expected file state | Recovery concern |
| --- | --- | --- |
| The writing step fails | A partial `.part` file may remain; the final file is not published | Restart the same job instance using its saved writer state, or clean up an abandoned file according to the job's retention policy |
| The publish step cannot move the file | The temporary file normally remains and the publish step fails | Fix the filesystem or path issue, then restart or reconcile the failed execution |
| The process stops just after the move | The final file may exist even if the repository has not recorded the step as complete | Make publication restart handling idempotent, using the run identifier or a manifest/checksum to establish that the existing final file belongs to this execution |

Do not treat “the final file exists” by itself as proof that the current execution published it. It could be output from an earlier run. A run-specific final name, or a small manifest containing the execution identity and output checksum, makes recovery decisions safer.

## Important boundaries

An atomic rename protects readers of the file from seeing a partially written file. It does not make file output part of the database transaction used by a chunk-oriented step. Database changes committed by earlier chunks remain committed if the later publication step fails. If the database and file must represent one logical delivery, design an explicit recovery or delivery protocol around both resources.

The same limitation applies when a job publishes several files. Renaming each file atomically does not make the whole group appear atomically. One common approach is to write all files under staging names, move each completed file, and publish a manifest or ready marker last. Consumers treat the manifest or marker as the signal that the complete set is available.

The key design rule is to make the final filename mean “this output is ready.” Spring Batch writes and closes a staging file first, then a successful finalization step performs the atomic move. That gives downstream processes a clear publication boundary and keeps incomplete output out of their normal input path.
