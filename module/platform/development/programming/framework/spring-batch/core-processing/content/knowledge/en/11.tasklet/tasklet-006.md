# A Tasklet that processes a file or calls a procedure

In Spring Batch, `Tasklet` suits a batch task with a fairly clear unit of work, such as checking or moving a file, creating a marker file, cleaning up temporary data, or calling a stored procedure in the database. Instead of reading item by item through an `ItemReader`, processing through an `ItemProcessor`, and then writing in chunks, a Tasklet performs the work in the `execute()` method.

A Step that uses a Tasklet is managed by `TaskletStep`. Spring Batch calls `execute()` and relies on `RepeatStatus` to know whether the task has completed or needs to be called again. A Tasklet usually returns `RepeatStatus.FINISHED` when the work is done. If it needs to keep repeating, it can return `RepeatStatus.CONTINUABLE`.

## 1. What is a Tasklet?

`Tasklet` is a simple interface in Spring Batch that defines a single execution operation:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

The two objects passed in have different roles:

- `StepContribution` lets the Tasklet update the Step's contributions, such as the number of records read or written, and the `ExitStatus`.
- `ChunkContext` provides the context of the current chunk/tasklet execution, including the `StepContext` and related attributes.

A Tasklet is not required to process data item by item. It can perform an overall operation such as calling a calculation procedure in the database or moving an input file to an archive directory.

### How do a Tasklet and chunk processing differ?

| Criterion | Tasklet | Chunk-oriented processing |
|---|---|---|
| Processing unit | One task or one execution of logic | A group of items per commit interval |
| Main components | `Tasklet.execute()` | `ItemReader`, `ItemProcessor`, `ItemWriter` |
| Suitable for | Calling a stored procedure, checking a file, cleaning data, overall operations | Reading and processing many records group by group |
| Transaction control | The TaskletStep's transaction manager | A transaction per chunk |
| Tracking item counts | The Tasklet updates the contribution itself if needed | Spring Batch updates the read, process, and write counters |

If the requirement is to call a database procedure to aggregate a period of data, a Tasklet is usually simple and easy to understand. If you need to read millions of lines, validate each line, and write in batches, chunk processing is usually more suitable.

## 2. RepeatStatus and the Tasklet lifecycle

`execute()` returns a `RepeatStatus` to control repetition:

- `RepeatStatus.FINISHED`: the task is complete; the Step can end normally.
- `RepeatStatus.CONTINUABLE`: the Tasklet needs to be called again in the same Step.

General flow:

```text
TaskletStep starts
       |
       v
Call Tasklet.execute()
       |
       +----> FINISHED ------> Step completes
       |
       +----> CONTINUABLE --> Call execute() again
       |
       +----> Exception ----> Step fails / handled per policy
```

For a Tasklet that performs a single operation such as moving a file or calling a stored procedure once, it normally returns `FINISHED`. Use `CONTINUABLE` only when there is a clear reason to split the task into multiple calls, for example processing a long task part by part or checking the status of an asynchronous process.

TaskletStep manages the transaction through the `PlatformTransactionManager` provided when the Step is declared. Each Tasklet call is performed in a transaction managed by the Step. However, the transaction only covers the resources that participate in it; filesystem operations or HTTP services do not automatically become transactional.

## 3. Declaring a Tasklet Step

With Spring Batch 5 or later, you can create a Step with `StepBuilder` and provide the Tasklet together with the transaction manager:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MaintenanceJobConfig {

    @Bean
    public Step cleanupStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet cleanupTasklet) {

        return new StepBuilder("cleanupStep", jobRepository)
                .tasklet(cleanupTasklet, transactionManager)
                .build();
    }
}
```

The `JobRepository` stores the metadata of the Job and Step; the `PlatformTransactionManager` manages the transaction for the TaskletStep. A Tasklet can be declared as a separate bean or written directly as a lambda if the logic is short.

A simple lambda example:

```java
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

@Bean
public Tasklet logStartTasklet() {
    return (contribution, chunkContext) -> {
        System.out.println("Starting maintenance task");
        return RepeatStatus.FINISHED;
    };
}
```

When the logic has many branches or dependencies, or needs to be tested separately, extract it into a class implementing `Tasklet` or a bean with a method that creates the Tasklet so the configuration is easier to read.

## 4. Example: a Tasklet that checks and moves a file

A common task is moving a successfully imported file from the `incoming` directory to the `archive` directory. The file path should be passed through JobParameters so the same Job can process many files without changing the source code.

An example of running the Job:

```bash
java -jar batch-app.jar \
    --spring.batch.job.name=archiveInputJob \
    inputFile=/data/incoming/orders-2026-11-15.csv \
    archiveDir=/data/archive
```

The Tasklet gets the values from JobParameters through `@StepScope`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ArchiveFileTaskletConfig {

    @Bean
    @StepScope
    public Tasklet archiveFileTasklet(
            @Value("#{jobParameters['inputFile']}") String inputFile,
            @Value("#{jobParameters['archiveDir']}") String archiveDir) {

        return (contribution, chunkContext) -> {
            Path source = Path.of(inputFile);
            Path target = Path.of(archiveDir).resolve(source.getFileName());

            if (Files.exists(target) && !Files.exists(source)) {
                // The previous run may have moved the file before the application stopped.
                return RepeatStatus.FINISHED;
            }

            if (!Files.isRegularFile(source)) {
                throw new IllegalStateException(
                        "Input file does not exist: " + source);
            }

            if (Files.exists(target)) {
                throw new IllegalStateException(
                        "Archive target already exists: " + target);
            }

            Files.createDirectories(target.getParent());
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);

            return RepeatStatus.FINISHED;
        };
    }
}
```

The code assumes the source file and the archive directory are on the same filesystem to support `ATOMIC_MOVE`. If the filesystem does not support atomic operations or the two paths are on different filesystems, you need to choose a strategy of copying, verifying the content, and then deleting the source that suits the deployment environment.

### Why does the example need to check the target file?

A file move operation does not participate in Spring Batch's database transaction. It can happen that the file has been moved successfully but the transaction or the process stops before the Step records completion. On restart, the source file no longer exists but the target file already exists.

The example's check that `target` exists and `source` no longer exists helps recognize the case where the move operation completed earlier. If both exist, the Tasklet stops with an error to avoid overwriting the archive file. In a real system, you should also confirm a checksum, size, or file code to be sure that the target file really is the file from this run.

If the target file may exist from a different import, checking only the file name is not enough. You can store a batch code or checksum in metadata/the database and use it as an idempotency key.

## 5. Example: a Tasklet that calls a stored procedure

Another Tasklet can call a stored procedure to perform a calculation or update data directly in the database. This is a suitable choice when most of the logic has already been implemented in a SQL procedure and the Job only needs to trigger it with input parameters.

Suppose the database has a stored procedure `process_daily_sales` that takes a business date and returns the number of processed records. You can use `SimpleJdbcCall`:

```java
import java.sql.Date;
import java.sql.Types;
import java.time.LocalDate;
import java.util.Map;

import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration
public class DailySalesProcedureTaskletConfig {

    @Bean
    @StepScope
    public Tasklet processDailySalesTasklet(
            JdbcTemplate jdbcTemplate,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        SimpleJdbcCall procedure = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("process_daily_sales")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_business_date", Types.DATE),
                        new SqlOutParameter("p_processed_count", Types.INTEGER));

        return (contribution, chunkContext) -> {
            LocalDate date = LocalDate.parse(businessDate);
            Map<String, Object> result = procedure.execute(
                    new MapSqlParameterSource()
                            .addValue("p_business_date", Date.valueOf(date)));

            Number processedCount =
                    (Number) result.get("p_processed_count");
            if (processedCount == null || processedCount.intValue() < 0) {
                throw new IllegalStateException(
                        "Stored procedure returned an invalid processed count");
            }

            contribution.incrementWriteCount(processedCount.intValue());
            return RepeatStatus.FINISHED;
        };
    }
}
```

The procedure name, parameter names, and SQL types in the example need to be adjusted for the database in use. `withoutProcedureColumnMetaDataAccess()` requires you to explicitly declare the in/out parameters; this is useful when the database's procedure metadata is not discovered automatically or when you want explicit control over the mapping.

`JdbcTemplate` uses the `DataSource` configured in Spring. If the `JdbcTemplate` and the TaskletStep use the same DataSource and the same transaction manager, the stored procedure call usually participates in the current transaction. When the procedure throws a SQL error, the exception propagates out of the Tasklet and the Step can roll back the transaction.

### Notes on the stored procedure's transaction

Not every stored procedure obeys the transaction managed by Spring. Some procedures may `COMMIT` or `ROLLBACK` on their own, use autonomous transactions, or call external systems. In that case, a rollback on the Spring side cannot necessarily undo all of the procedure's changes.

Before using a Tasklet that calls a procedure, determine:

- Does the procedure commit or roll back on its own?
- Does the procedure run on the same DataSource and transaction manager as the Step?
- Does the procedure call another database or an external service?
- If the Job restarts and the procedure is called again, will data be updated or written twice?
- Can the procedure accept a batch code to identify the processing run?

Design the procedure to be idempotent or have a control table that tracks status by date/processing batch. If the procedure has committed independently before the Tasklet fails, a restart may call the procedure again.

## 6. Declaring the Step and Job for a Tasklet

A Tasklet is attached to a Step with `.tasklet(tasklet, transactionManager)`. You can organize several Tasklet Steps in the same Job, for example checking the file, calling a data-loading procedure, and then archiving the file:

```java
@Configuration
public class ImportFileJobConfig {

    @Bean
    public Step processFileStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet processFileTasklet) {
        return new StepBuilder("processFileStep", jobRepository)
                .tasklet(processFileTasklet, transactionManager)
                .build();
    }

    @Bean
    public Job importFileJob(
            JobRepository jobRepository,
            Step processFileStep) {
        return new JobBuilder("importFileJob", jobRepository)
                .start(processFileStep)
                .build();
    }
}
```

The imports and bean dependencies are omitted in this example to focus on how to combine a Step and a Job. `processFileTasklet` must be a Tasklet bean that has been declared; if the Job has multiple Steps, you can chain them with `.next(...)` or configure a flow based on exit status.

## 7. A Tasklet can be called multiple times

Although a Tasklet usually performs a single operation, Spring Batch can call `execute()` multiple times if the Tasklet returns `RepeatStatus.CONTINUABLE`.

An example of a Tasklet that checks the status of an external task and keeps waiting if it is not complete:

```java
@Bean
public Tasklet checkExternalTaskTasklet(ExternalTaskService service) {
    return (contribution, chunkContext) -> {
        boolean completed = service.isCompleted();
        if (completed) {
            return RepeatStatus.FINISHED;
        }
        return RepeatStatus.CONTINUABLE;
    };
}
```

The example above only illustrates the meaning of `CONTINUABLE`. In a real application, you should not create an unbounded waiting loop. You need a timeout, a limit on the number of checks, or a polling mechanism with backoff to avoid holding resources and a transaction for too long. For a long-running asynchronous process, it is usually better to store the task code, end the current run, and then use an appropriate orchestration mechanism to check later.

## 8. Error handling and restarting a Tasklet

If a Tasklet throws an exception, the TaskletStep records the error and the Step usually ends `FAILED`. If the Job allows restart, Spring Batch can create a new JobExecution for the same JobInstance when it is relaunched with the same identifying JobParameters.

However, a restart does not automatically undo operations outside the transaction:

| Tasklet work | When an error occurs after the operation has been performed | How to design for restart |
|---|---|---|
| Moving a file | The file may already be in the target directory | Check the source/target, checksum, and batch code before moving again. |
| Writing a result file | The file may have been created partially or completely | Write to a temporary file, verify, then rename; handle an existing file by a clear rule. |
| Calling a stored procedure | The procedure may have already committed data | The procedure needs an idempotency key or a batch status table. |
| Calling an HTTP API | The target system may have already processed the request | Use a request ID/idempotency key and look up the result before resending. |

Do not rely on the previous JobExecution being `FAILED` to conclude that all side effects have been rolled back. You need to consider the actual transaction boundary and the task's recoverability.

### Use ExecutionContext when you need to store state

If a Tasklet processes multiple parts or needs to record progress, you can use the `ExecutionContext` through the `StepExecution` to store a checkpoint. For example, storing the name of the file that has been processed or the current batch code:

```java
String inputFile = jobParameters.getString("inputFile");
stepExecution.getExecutionContext().putString("inputFile", inputFile);
```

In a Tasklet, you can get the StepExecution through `contribution.getStepExecution()`. The state in the ExecutionContext is saved by Spring Batch through the repository mechanism; store the small values needed for restart, and do not use it as a place to hold file content or large business data.

## 9. Tracking the Tasklet's results

A Tasklet does not automatically count items like a chunk-oriented Step. If a Tasklet calls a stored procedure that processes 500 records and receives an output count of 500, it can update the `StepContribution`:

```java
contribution.incrementWriteCount(500);
```

If a Tasklet checks a file or creates a marker without any notion of items read/written, you do not need to set artificial counters. You can write structured logs, store the business result in the database, or update the `ExitStatus` to express a specific result.

An example of setting a custom exit code:

```java
contribution.setExitStatus(new ExitStatus("FILE_ARCHIVED"));
return RepeatStatus.FINISHED;
```

If the Job uses the Step's result to branch, you can configure the flow based on `ExitStatus`. You need to distinguish `ExitStatus` from `BatchStatus`: the exit code expresses the Step's result, while BatchStatus represents the execution state such as `COMPLETED` or `FAILED`.

## 10. When should you use a Tasklet?

A Tasklet is usually suitable when the work is an overall operation that does not need the framework to divide the data into chunks. For example:

- Checking a file's existence, size, or checksum.
- Moving, renaming, compressing, or creating a marker file.
- Calling a stored procedure to calculate or synchronize data.
- Cleaning up temporary data or updating the status of a batch.
- Calling an external tool or service with a mechanism to control the result.

Chunk processing is usually more suitable when you need to read, validate, transform, and write each record per commit interval. If a Tasklet writes its own loop to read a file with millions of lines and processes each line itself, the application will have to manage buffers, checkpoints, retry, skip, and transactions itself. In that case, `ItemReader`/`ItemProcessor`/`ItemWriter` usually provide a clearer structure and better observability.

## 11. Common mistakes

| Mistake | Cause | How to handle |
|---|---|---|
| The Tasklet is called repeatedly unexpectedly | It returns `CONTINUABLE` instead of `FINISHED`. | Only return `CONTINUABLE` when repetition is truly needed. |
| The file has been moved but the Step is still FAILED | The filesystem is not part of the database transaction; the error occurred after the move. | Design source/target checks, checksums, and idempotent operations. |
| The stored procedure runs again on restart | The procedure committed independently before the Job failed. | Use a batch key, processing status, or idempotent logic inside the procedure. |
| The transaction does not roll back the procedure's data | The procedure uses a different transaction or commits on its own. | Check the transaction semantics of the database and the procedure. |
| The Tasklet holds a transaction too long | One execute does too much work or polls without limit. | Split the work, use a bounded `CONTINUABLE`, or move to chunk processing. |
| The number of processed records is not visible | The Tasklet does not increment item counters itself. | Update the contribution from the actual figures returned by the task. |
| Using a Tasklet for large line-by-line processing | Re-implementing many mechanisms that chunk processing already supports. | Use a chunk-oriented Step when you need to process items in groups. |

## Conclusion

A Tasklet is a way to implement a Step for a specific batch task such as checking or moving a file, cleaning up data, or calling a stored procedure. `TaskletStep` manages the lifecycle and the transaction, while `RepeatStatus.FINISHED` signals that the task has completed. For file and procedure operations, remember that side effects outside the transaction are not automatically rolled back. Designing for idempotency, checking state before acting, and storing a checkpoint when needed will help the Job restart safely. When the requirement shifts to processing many items in groups, chunk-oriented processing is usually the more suitable choice.
