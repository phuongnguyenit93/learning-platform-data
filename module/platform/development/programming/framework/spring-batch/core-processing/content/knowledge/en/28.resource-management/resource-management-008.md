# Naming Outputs by Job Instance

In Spring Batch, a JobInstance represents a single logical run with a set of identifying JobParameters. One JobInstance can have multiple JobExecutions when a previous run failed or was stopped and then restarted. When generating output files, decide whether the filename is tied to the JobInstance or each JobExecution.

If the goal is to restart and continue the same result, the output name should remain stable per JobInstance. A restart will reuse the same JobInstance ID and the same output path, allowing the writer to restore its saved checkpoint. If the filename contains the JobExecution ID or a new timestamp on every launch, each restart may create a different file and split the result into multiple parts.

## 1. How do JobInstance and JobExecution differ?

JobInstance represents a logical unit of work. It is identified by the Job name and the JobParameters marked as identifying.

JobExecution is a specific execution attempt of a JobInstance. When a Job fails and is restarted, Spring Batch creates a new JobExecution that still belongs to the old JobInstance.

~~~text
Job: exportOrders
Identifying parameters:
  businessDate = 2026-11-15
  sourceBatch = 8421
            |
            v
       JobInstance 52
            |
       +----+----+
       |         |
       v         v
  Execution 90  Execution 94
     FAILED      COMPLETED
       |         ^
       +---------+
          restart
~~~

In this example, Execution 90 and 94 are two runs of the same JobInstance 52. The JobInstance ID stays constant across restarts; the JobExecution ID changes for each execution attempt.

This difference dictates how outputs are named:

- Use JobInstance ID if you want a single logical file across the entire processing lifecycle, including restarts.
- Use JobExecution ID if you intentionally want each execution attempt to produce a separate artifact, such as diagnostic files or per-attempt staging files.
- Use an identifying business key if filenames need to be human-readable and stable per business context, while ensuring the key is unique and safe for filenames.

## 2. Why should output be tied to JobInstance?

A Job can read data, aggregate it, and generate a report file. If the first run processes several chunks and then fails, a restart must continue the same work. The writer must reopen the exact file already created and restore the saved write position.

Example filename by JobInstance:

~~~text
orders-job-52.csv
~~~

Both the first run and the restart use this file:

~~~text
JobExecution 90 (FAILED)
  -> writes some chunks to orders-job-52.csv

JobExecution 94 (RESTART)
  -> reopens orders-job-52.csv
  -> restores writer checkpoint
  -> continues writing the rest
~~~

If instead a name based on JobExecution ID is used:

~~~text
orders-execution-90.csv
orders-execution-94.csv
~~~

then a restart may create a new file. The first file contains data written in the earlier attempt and the second file contains the remainder; downstream would have to merge and reconcile them itself. That is rarely the desired behavior when restarting the same JobInstance.

Naming outputs by JobInstance gives one logical unit of work a stable path. It also helps operators look up files from the JobInstance ID in JobRepository.

## 3. Choosing components to build the output name

Several common options exist:

| Name Component | Stable across restarts of same JobInstance? | Suitable When |
|---|---|---|
| JobInstance ID | Yes | Needing unique repository-scoped identification |
| JobExecution ID | No | Wanting a separate artifact per attempt |
| Identifying business parameter | Yes if kept unchanged | Wanting business-meaningful filenames |
| Non-identifying parameter | Not guaranteed | Used only as auxiliary metadata, not output identity |
| Timestamp generated on each launch | No | Wanting a separate file per new run, not for restarts |
| UUID generated on each launch | No | Creating independent artifacts without continuing checkpoints |

JobInstance ID is usually a simple choice when the filename only needs to be unique within a JobRepository. This value is assigned by the repository once the JobInstance is created.

You can combine the ID with the Job name or business date for readability:

~~~text
exportOrders-20261115-instance-52.csv
~~~

If using a business key as the primary name, verify whether the key is truly unique. For example, using only a date can collide if multiple data sources or multiple tenants share the same date. Combine the date with a source batch ID or JobInstance ID.

## 4. Obtaining the JobInstance ID while the Job runs

The JobInstance is already created before the JobExecution begins its Steps. Therefore, when beforeJob is called, the application can retrieve the ID from the JobExecution:

~~~java
long jobInstanceId =
        jobExecution.getJobInstance().getInstanceId();
~~~

You can build the filename and store the path in the Job ExecutionContext. This lets readers/writers in later Steps receive the path via late binding.

Example listener:

~~~java
public class OutputPathJobListener implements JobExecutionListener {

    private final Path outputDirectory;

    public OutputPathJobListener(Path outputDirectory) {
        this.outputDirectory =
                outputDirectory.toAbsolutePath().normalize();
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        try {
            Files.createDirectories(outputDirectory);
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Cannot create batch output directory",
                    exception);
        }

        long instanceId =
                jobExecution.getJobInstance().getInstanceId();

        String fileName = "orders-" + instanceId + ".csv";
        Path outputPath =
                outputDirectory.resolve(fileName).normalize();

        if (!outputPath.startsWith(outputDirectory)) {
            throw new IllegalStateException(
                    "Output path is outside the configured directory");
        }

        jobExecution.getExecutionContext().putString(
                "orders.output.path",
                outputPath.toString());
    }
}
~~~

Because the listener uses the JobInstance ID, restarting the same instance computes the exact same filename. The path value is also placed into the Job ExecutionContext so Steps can consume it.

The directory path should come from application configuration or a trusted source. Do not concatenate arbitrary user-supplied strings directly into filenames without validation, because sequences like ../ could escape the intended output directory.

## 5. Registering the listener on the Job

Declare the listener as a bean and register it on JobBuilder:

~~~java
@Bean
OutputPathJobListener outputPathJobListener(Environment environment) {
    String directory =
            environment.getRequiredProperty("batch.output.directory");
    return new OutputPathJobListener(Paths.get(directory));
}

@Bean
Job exportOrdersJob(
        JobRepository jobRepository,
        OutputPathJobListener outputPathJobListener,
        Step exportOrdersStep) {

    return new JobBuilder("exportOrdersJob", jobRepository)
            .listener(outputPathJobListener)
            .start(exportOrdersStep)
            .build();
}
~~~

beforeJob runs after the JobExecution is created and before any Steps execute. This is the right moment to compute runtime metadata tied to the JobInstance.

In this example, the listener only computes the path and writes it to the Job ExecutionContext. The actual file is opened by the writer inside the Step. Separating name resolution from file writing keeps Job orchestration from managing output contents directly.

On restart, beforeJob runs again for the new JobExecution. Since the JobInstance ID does not change, the computed path matches the first run. Do not generate a new UUID or timestamp inside the listener if output must resume in the same file.

## 6. Using Job ExecutionContext to pass the output path

A step-scoped reader/writer can receive the path from the Job ExecutionContext via SpEL:

~~~java
@Value("#{jobExecutionContext['orders.output.path']}")
String outputPath
~~~

Job ExecutionContext is well suited for runtime values shared across Steps within the same JobExecution. In this example, orders.output.path is small metadata, while the file content resides on the filesystem.

If the output path must stay identical across restarts, the listener can recompute it from the JobInstance ID as shown above. Additional fields like output version or format can also be stored to validate when reopening the file.

Do not store file contents or lists of records in the ExecutionContext. The context should hold paths, batch codes, versions, or checksums; output data belongs in files or dedicated storage.

## 7. Declaring a step-scoped writer with the output path

The writer must be created when the StepExecution is active so it can read the value from the Job ExecutionContext.

Example FlatFileItemWriter:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobExecutionContext['orders.output.path']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("ordersWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

Key points:

- @StepScope enables late binding to retrieve the output path when the Step runs.
- name("ordersWriter") provides a stable name for writer state in the ExecutionContext.
- resource(...) points to the file identified by the JobInstance.
- saveState(true) lets the writer save checkpoints needed for restart.

The writer name should also remain stable across deployments if restarting from older metadata is required. Renaming the component can change the keys the writer uses in the ExecutionContext.

Do not instantiate the writer with new inside a processor or tasklet to bypass scoping. Let Spring manage the bean, target instance, and ItemStream lifecycle.

## 8. Wiring the writer into Step and Job

The Step uses the step-scoped writer:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        FlatFileItemWriter<Order> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}
~~~

The Job registers the listener to resolve the path before the Step starts:

~~~java
@Bean
Job exportOrdersJob(
        JobRepository jobRepository,
        OutputPathJobListener outputPathJobListener,
        Step exportOrdersStep) {

    return new JobBuilder("exportOrdersJob", jobRepository)
            .listener(outputPathJobListener)
            .start(exportOrdersStep)
            .build();
}
~~~

The Step definition can be a singleton because the reader/writer are injected as scoped proxies. The actual target writer is instantiated in Step scope with the current JobExecution's output path.

If a Job has multiple Steps writing different files, multiple keys can be stored in the Job ExecutionContext, such as orders.output.path, summary.output.path, and rejects.output.path. Each step-scoped writer receives its corresponding key.

## 9. Output names must stay stable across restarts

A restart creates a new JobExecution for the same JobInstance. Therefore, the output path used during restart must match the path from the initial run.

Factors to keep stable:

- Job name and identifying JobParameters of the JobInstance.
- How the filename is computed from JobInstance ID or business key.
- Output directory and path normalization rules.
- Writer name used to store checkpoints.
- File format and schema.
- Source data being exported by the writer.
- Writer configuration regarding append, restart, and state.

Example:

~~~text
First run:
  JobInstance ID = 52
  output = /batch/output/orders-52.csv

Restart:
  JobInstance ID = 52
  output = /batch/output/orders-52.csv

New logical run:
  JobInstance ID = 53
  output = /batch/output/orders-53.csv
~~~

If the output directory changes between the initial run and restart, the writer may open a new file while ExecutionContext holds the checkpoint for the old file. Configure a stable directory or persist the chosen path in durable metadata and validate it before resuming.

## 10. Do not use JobExecution ID if you want one file per JobInstance

The JobExecution ID changes on every restart. Thus, using it in the filename creates a different output for each attempt.

Example:

~~~text
orders-execution-90.csv
orders-execution-94.csv
~~~

This approach fits when you want to retain separate artifacts per attempt, for example:
- Saving an output snapshot for each run for investigation.
- Creating an independent staging file before confirming results.
- Preserving output from a failed run for analysis.
- Comparing different execution attempts.

However, if the writer must resume an incomplete file, naming by JobExecution ID is inappropriate. On restart, the new JobExecution will point to a different file and the writer's checkpoint will no longer match that resource.

Two naming tiers can be used if both goals are needed:
- Working files keyed by JobInstance for restart.
- Logs or audit records keyed by JobExecution to distinguish each attempt.

## 11. Identifying JobParameters and business-based filenames

Filenames can be constructed from identifying JobParameters instead of the numeric JobInstance ID. For example:

~~~text
orders-20261115-source-8421.csv
~~~

This makes filenames easier for operators to understand. However, ensure the parameters forming the filename are truly identifying and sufficient to distinguish JobInstances.

Example JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("sourceBatchId", 8421L, true)
        .toJobParameters();
~~~

The filename can be built from these two values once normalized. A different JobInstance must have a different businessDate or sourceBatchId per business rules.

Do not use non-identifying parameters to build an output path that can vary across restarts. Those parameters do not create a new JobInstance; consequently two launches may be treated as the same instance yet write to two different files.

To simplify uniqueness, use the JobInstance ID as the primary identifier and add a formatted business date for operator readability.

## 12. Normalizing and protecting filenames

Filenames are often built from Job name, business key, tenant, or caller-supplied parameters. Restrict characters and paths to avoid collisions or access outside the intended directory.

Key principles:

- Use the numeric JobInstance ID as a unique component.
- Normalize business dates to a fixed format, such as yyyyMMdd.
- Allow only a safe character set in tenant codes or source keys.
- Never use raw path strings supplied by callers without validation.
- Normalize paths with Path.normalize() and verify they remain inside the output directory.
- Separate directories by environment or tenant if different repositories can generate the same IDs.
- Keep extensions and file formats consistent.

Example filenames:

~~~text
/batch/output/
  orders-20261115-instance-52.csv
  orders-20261116-instance-53.csv
~~~

If JobInstance ID is only unique within one JobRepository, do not assume that ID is unique company-wide or across all environments. Include the Job name, environment, or normalized tenant in the path.

## 13. Output directories across multiple runtime environments

An application may run in development, staging, and production. If the same filesystem or object storage is shared, filenames containing only JobInstance ID could collide across two independent repositories.

Example:

~~~text
/batch/dev/exportOrders/instance-52.csv
/batch/prod/exportOrders/instance-52.csv
~~~

Organize output directories by:
- Environment.
- Job name.
- Tenant or business domain if isolation is needed.
- JobInstance ID or identifying business key.

The root path should be configured via a property:

~~~properties
batch.output.directory=/var/app/batch/output
~~~

Do not hard-code absolute paths into the writer. That allows deploying the same Job across multiple environments while preserving filename conventions.

If output resides on a shared filesystem or object storage, verify read/write permissions, consistency, rename capabilities, and retention policies of that storage.

## 14. Writer restart and file checkpoints

FlatFileItemWriter implements ItemStream, so it can save state into the Step ExecutionContext. When a Step restarts, the writer uses the saved state to resume the corresponding resource.

For this mechanism to work:

- The writer must have a stable name.
- The resource path must match the previous run.
- saveState(true) must be enabled if checkpointing is needed.
- The partially written file must still exist.
- Do not delete the file or create an empty file before the writer restores state.
- Do not change the format or data ordering across restarts.

The writer can store line counts or information needed to know the written position. When reopened in restart mode, the implementation uses the ExecutionContext to restore state. Do not manually append outside the writer's lifecycle without understanding checkpoints, as doing so can duplicate data or leave the file out of sync with metadata.

If using a custom writer, implement ItemStream and save checkpoints in the Step ExecutionContext. @StepScope only manages the target instance; it does not save writer state automatically.

## 15. Existing output files: overwrite, append, or restart?

Distinguish three situations:

1. **New JobInstance:** a file for the new ID normally does not exist yet; the writer creates a new output.
2. **Restarting the same JobInstance:** the file may already contain data from previously committed chunks; the writer needs to restore its checkpoint and continue.
3. **Intentional re-run with a new JobInstance:** create a separate output to preserve the result of the new logical processing run.

Do not set one blanket overwrite/append policy for every case without considering restarts. With FlatFileItemWriter, properties like append, shouldDeleteIfExists, and saveState carry different meanings. Rely on the writer's restart behavior and test with a real JobRepository; never delete the old file before the framework reads the checkpoint.

If a file for the same JobInstance already exists without a corresponding checkpoint, it may be an orphan file from an out-of-lifecycle process termination or out-of-sync metadata. Do not automatically append to it. Cross-check JobExecution/StepExecution, determine how much data committed, and apply a recovery procedure.

## 16. Using staging files and publishing only after Job success

If downstream systems must not see incomplete files, write to a JobInstance-keyed staging file first and publish after all required Steps complete.

Example:

~~~text
/batch/staging/orders-instance-52.part
               |
               | writer writes and can restart
               v
         Job completes
               |
               | final publish step
               v
/batch/published/orders-instance-52.csv
~~~

Approach:

1. The writer writes to a stable staging path per JobInstance.
2. Restarts resume the staging file via checkpoints.
3. A final Step validates the file, record count, and checksum.
4. The publish Step moves or copies the file to the published directory.
5. Downstream reads only the published directory or confirmed manifests.

If staging and published reside on the same filesystem, atomic move can prevent consumers from seeing a partially moved file, depending on the filesystem and implementation. With object storage, renaming is usually not atomic; copying and then updating a manifest or publication status may be necessary.

Use a dedicated publish Step rather than performing complex side effects in afterJob when clear transactions, retries, and metadata are needed. A publish Step can be restarted and can check whether the output has already been published.

## 17. Handling new JobInstances and old outputs

When creating a new JobInstance, a new output name avoids overwriting the previous instance's file. However, a retention policy is needed so the output directory does not grow indefinitely.

Management practices:

- Store outputs by date or batch partition.
- Delete staging files of old executions after the retention window.
- Retain published files per business policy.
- Store manifests containing JobInstance ID, final JobExecution ID, path, and checksum.
- Never delete outputs of running or still-restartable JobInstances.
- Use a cleanup process that verifies JobRepository status.

Do not delete a file simply because the latest JobExecution FAILED. The file may contain committed chunk data required for restart. Clean up only after confirming the JobInstance will no longer restart or the output has been handled per storage policy.

## 18. Multiple Jobs running concurrently

Two different JobInstances can run concurrently. Output names must avoid collisions between them.

Using JobInstance ID normally prevents collisions within the same JobRepository. If names are based on business keys, ensure appropriate uniqueness. For example, if two tenants share the same business date, a name containing only the date will collide.

In a partitioned Step, multiple workers may write output simultaneously. Do not let all workers open the same file with independent writers unless an explicit synchronization/aggregation design exists. Typically, each partition writes its own file by partition name or ID, and an aggregation Step produces the final output.

Example:

~~~text
orders-instance-52/
  partition-0.csv
  partition-1.csv
  partition-2.csv
  merged.csv
~~~

The JobInstance ID defines the directory for the logical run. The partition key defines the child artifact. On restart, partition filenames must remain stable per partition execution so workers resume the right files.

## 19. Recording output metadata for traceability

Beyond the filename, output metadata can be stored in the Job ExecutionContext or an artifact registry table.

Useful fields:

- JobInstance ID.
- JobExecution ID that created or completed the output.
- Job name.
- Business date or source batch ID.
- Output path.
- Output format/version.
- Record count.
- File size.
- Checksum.
- Publication status and timestamp.

Example metadata:

~~~json
{
  "jobName": "exportOrdersJob",
  "jobInstanceId": 52,
  "jobExecutionId": 94,
  "outputFile": "/batch/published/orders-52.csv",
  "formatVersion": "v2",
  "recordCount": 12000,
  "publicationStatus": "PUBLISHED"
}
~~~

JobInstance ID indicates which logical processing unit the file belongs to; JobExecution ID indicates which execution attempt finished creating or publishing the file. These two identifiers complement each other.

Do not put sensitive content in filenames or metadata. Use approved IDs and restrict read access to the artifact registry.

## 20. Testing output naming by JobInstance

Test both naming rules and actual restart behavior.

Scenarios:

| Scenario | What to Verify |
|---|---|
| First Job launch | Output name contains the created JobInstance ID |
| Restart same JobInstance | Output path matches the initial run |
| New JobInstance | New output path, does not overwrite old file |
| Changing identifying parameter | Creates new instance and new output name |
| Changing non-identifying parameter | Does not accidentally change output path of the same instance |
| Writer restart | Restores checkpoint and resumes the right file |
| Staging file | Consumers do not see the file before publish |
| Publish Step retry | Does not double-publish or lose the file |
| Two concurrent JobInstances | Do not write to a shared output |
| Two tenants on same business date | No collision when tenant is part of the key |
| Output directory missing | Created per policy or Job fails clearly |
| Invalid path | Job rejects paths outside allowed directory |
| Partitioning | Each partition writes its own resource or merges properly |
| Cleanup | Does not delete files still needed for restart |

A typical integration test:
1. Launch the Job with fixed identifying parameters.
2. Have the writer write several chunks and intentionally fail the Step.
3. Record the JobInstance ID and output path.
4. Restart the same JobInstance.
5. Verify JobExecution ID changes while JobInstance ID and output path stay the same.
6. Verify the final file has all records with no duplicate lines.
7. Launch with new identifying parameters and verify a different output path.

Tests should use a JobRepository and writer matching production configuration. A unit test checking only the filename helper will not prove checkpoints are restored properly.

## 21. Common Pitfalls

**Using JobExecution ID for restartable outputs.** Each restart creates a new file, fragmenting the output.

**Generating a new timestamp or UUID in beforeJob.** Restarting the same JobInstance may receive a different path and fail to match the old checkpoint.

**Using non-identifying parameters for unique names.** The parameter can change while the JobInstance remains the same; the output path is no longer stable.

**Changing output directory across runs.** The writer opens a different resource while metadata holds the old file's checkpoint.

**Not enabling state saving on the writer.** The writer lacks the checkpoint needed to resume at the right position.

**Changing the writer name.** ExecutionContext keys may no longer match saved metadata.

**Deleting the file on restart.** Committed data from previous chunks may be lost.

**Appending manually outside checkpoints.** Can write duplicates or corrupt record ordering.

**Letting consumers read in-progress files.** Downstream may process incomplete data; use staging and publishing.

**Using business date alone as the filename.** Multiple sources or tenants on the same day can collide.

**Letting multiple partitions write the same file unsynchronized.** Can lose data, scramble ordering, or corrupt the file.

**Cleaning up files of FAILED Jobs too early.** Files may still be needed for restarting the same JobInstance.

## 22. Process for designing output names by JobInstance

When creating output files for Spring Batch, follow this sequence:

1. Determine whether the file belongs to a JobInstance or an individual JobExecution.
2. If restart must resume the same file, use JobInstance ID or a stable identifying business key.
3. Do not use JobExecution ID, new timestamps, or new UUIDs for resumable outputs.
4. Build the output path after JobExecution/JobInstance exists, such as in beforeJob.
5. Store the path in Job ExecutionContext so a Step-scoped writer late-binds it.
6. Use @StepScope and saveState(true) for writers needing checkpoints.
7. Keep output directory, writer name, format, and input stable across restarts.
8. Normalize paths and verify outputs reside inside the allowed directory.
9. Use staging and a publish Step if downstream may only read complete files.
10. Implement retention/cleanup based on JobInstance status and storage requirements.
11. For partitioning, create separate resources per partition or a controlled merge mechanism.
12. Test that JobInstance ID stays constant across restarts, JobExecution ID changes, and the final file has no missing/duplicate records.

Naming outputs by JobInstance creates a durable identifier for the artifact of a logical processing run. JobExecution ID traces each attempt; JobInstance ID preserves the same output path across restarts. Combining stable identifiers, Step-scoped writers, checkpoints, and publishing workflows lets Spring Batch resume partially written files and deliver complete outputs to downstream systems.

