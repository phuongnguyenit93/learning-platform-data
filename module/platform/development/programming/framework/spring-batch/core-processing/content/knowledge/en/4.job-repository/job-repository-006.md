# JobRepository in a Single-Instance Environment

In Spring Batch, `JobRepository` is the component that manages the metadata of batch runs. It stores information about JobInstance, JobExecution, StepExecution, and ExecutionContext so the framework knows when a Job was launched, what state it is in, which Steps have completed, and where it can resume after an error.

In a **single-instance** environment (the application runs on only one instance or one node), `JobRepository` still plays an important role. Having only one application process makes the deployment architecture simpler, but it does not remove the need for durable state storage, control of duplicate launches, and restart support after an incident. A single-instance application can still run multiple Jobs concurrently, receive multiple launch requests, or be stopped midway.

## 1. What Does JobRepository Do?

`JobRepository` is where Spring Batch stores and retrieves metadata throughout a Job's lifecycle. When a Job is launched, the framework uses the repository to create or look up a JobInstance, create a JobExecution, and record StepExecutions. During the run, the status, counters, and ExecutionContext continue to be updated.

The main kinds of information include:

- **JobInstance:** identifies a logical run of the Job, based on the Job name and the identifying JobParameters.
- **JobExecution:** a specific execution of a JobInstance, including a status such as STARTED, COMPLETED, FAILED, or STOPPED, along with the start and end times.
- **StepExecution:** the execution information of each Step, including status, read count, write count, skip count, commit count, and rollback count.
- **ExecutionContext:** state data that needs to be maintained across executions, commonly used to store checkpoints that help restart.
- **JobParameters:** the input parameters stored with the execution; the identifying parameters take part in determining the JobInstance.

For example, the Job `dailySettlementJob` runs for the business date `2026-11-15`. The repository stores the JobInstance for that date and each JobExecution. If the first run fails, a restart can create a new JobExecution for the same JobInstance and continue based on the metadata, instead of treating it as an entirely new job.

`JobRepository` is not a repository holding business data such as customers, orders, or transactions. It stores metadata to orchestrate and track batch processing. Business data is still read and written through the application's readers, writers, DAOs, or services.

## 2. Single Instance Does Not Mean JobRepository Is Not Needed

Suppose a single Spring Boot application runs on one server. A scheduler launches the Job at midnight, and then the server loses power when the Job has processed only part of the data.

If the metadata lives only in the process's memory, when the application restarts, the state of the previous run may vanish. The framework no longer knows which execution the Job created, which Step had completed, and where the reader had saved its checkpoint. A new run might reprocess the data from the beginning and create duplicate side effects.

With a `JobRepository` that stores metadata in a durable database, the application can read the state back after startup. If the Job, Step, and the read/write components support restart, operators can continue the failed JobInstance from the stored state.

Single instance only means the application is currently deployed on one node. It does not imply:

- There is only one Job in the whole system.
- Each Job runs only once throughout the application's lifetime.
- No two launch requests arrive at almost the same time.
- The process is never stopped abruptly.
- In-memory metadata can replace durable execution history.

Therefore, in a single-instance production environment, the usual choice is still a `JobRepository` that uses a relational database and is configured with a suitable transaction manager.

## 3. How Is JobRepository Organized?

With a JDBC configuration, Spring Batch stores metadata in tables with the default prefix `BATCH_`. Depending on the version and database, the specific schema may differ slightly, but the common tables include:

| Metadata Table | Main Contents |
|---|---|
| `BATCH_JOB_INSTANCE` | The JobInstances and their identities |
| `BATCH_JOB_EXECUTION` | Each Job execution, its status and run times |
| `BATCH_JOB_EXECUTION_PARAMS` | The JobParameters of the execution |
| `BATCH_STEP_EXECUTION` | The status and counters of each StepExecution |
| `BATCH_JOB_EXECUTION_CONTEXT` | The ExecutionContext at the JobExecution level |
| `BATCH_STEP_EXECUTION_CONTEXT` | The ExecutionContext at the StepExecution level |

The relationships among the records can be pictured as follows:

```text
JOB_INSTANCE
     |
     | one JobInstance can have many executions
     v
JOB_EXECUTION
     |
     +--------------------+
     |                    |
     v                    v
STEP_EXECUTION       JOB_EXECUTION_CONTEXT
     |
     v
STEP_EXECUTION_CONTEXT
```

A JobInstance can have multiple JobExecutions across restarts. A JobExecution can contain multiple StepExecutions. The ExecutionContext is stored separately by Job or Step scope so the framework can restore the appropriate state.

These tables are Spring Batch's internal structure. The application should query metadata through APIs such as `JobExplorer` or suitable monitoring tools, rather than directly updating metadata rows while a Job is running.

## 4. Configuring JobRepository in a Single-Instance Application

### Using Spring Boot's Auto-Configuration

With a Spring Boot application that has a configured DataSource, Spring Boot can auto-configure the Spring Batch infrastructure and `JobRepository`. In the normal case, you only need to provide the datasource, transaction manager, and the Job/Step definitions; there is no need to create another repository yourself.

Example datasource and schema configuration in `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batch_app
    username: batch_user
    password: ${BATCH_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  batch:
    jdbc:
      initialize-schema: never
```

In a production environment, `initialize-schema: never` is suitable when the Spring Batch schema is managed with a migration tool such as Flyway or Liquibase. In a development or test environment, you can configure Spring Boot to initialize the schema automatically if the database and Spring Batch version support it.

Example of defining a Job and Step that use the injected `JobRepository`:

```java
@Bean
Job dailySettlementJob(JobRepository jobRepository, Step settlementStep) {
    return new JobBuilder("dailySettlementJob", jobRepository)
            .start(settlementStep)
            .build();
}

@Bean
Step settlementStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<SettlementInput> reader,
        ItemProcessor<SettlementInput, Settlement> processor,
        ItemWriter<Settlement> writer) {

    return new StepBuilder("settlementStep", jobRepository)
            .<SettlementInput, Settlement>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

JobBuilder and StepBuilder receive the `JobRepository` to store the Job and Step metadata. With a chunk size of 200, Spring Batch processes a group of items in one chunk transaction according to the configured transaction manager that is provided.

You should not mechanically add `@EnableBatchProcessing` to a Spring Boot application that is using auto-configuration. Depending on the Spring Boot version, this annotation can make the application take on the responsibility of configuring the Batch infrastructure itself and affect other automatic mechanisms. Choose one consistent configuration approach according to the version and the application structure.

### When You Need to Configure the Infrastructure Manually

In a Spring application that does not use auto-configuration, you need to configure `JobRepository` based on the DataSource and transaction manager. You can use Spring Batch's infrastructure configuration mechanism or `JobRepositoryFactoryBean`, depending on the framework version.

Points to define clearly:

- The DataSource used to store metadata, which can be separated from the business DataSource.
- The transaction manager that the repository uses to manage metadata operations.
- The database type and the corresponding metadata schema.
- The transaction isolation level for the execution-creation operation.
- How to initialize and upgrade the schema when deploying a new version.

If metadata and business data live in one database, you can share the DataSource but you need to understand the transaction boundaries clearly. If you use multiple DataSources or transaction managers, you must configure them so that metadata operations and business data processing behave consistently according to the Job's requirements.

## 5. Controlling Launches Within One Instance

An application node can still receive multiple Job launch requests almost simultaneously. For example:

- A scheduler starts the Job at 00:00.
- An operator presses a manual run button at exactly that moment.
- Another API also sends a command to launch the same Job.
- A retry from an orchestration system arrives while the previous execution has not finished.

`JobRepository` helps Spring Batch check the JobInstance and existing executions. A JobInstance is determined by the Job name and the identifying JobParameters. If two requests launch the same Job with the same set of identifying parameters, the repository and the metadata constraints help prevent creating two JobInstances with the same identity.

The result depends on the current state. The caller may encounter situations such as:

- `JobExecutionAlreadyRunningException` if the JobInstance already has a running execution.
- `JobInstanceAlreadyCompleteException` if the JobInstance has already completed.
- `JobRestartException` if the instance cannot be restarted given its current state or configuration.
- `JobParametersInvalidException` if the input parameters are invalid.

For example, the business date is an identifying parameter:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.now(), true)
        .toJobParameters();

jobLauncher.run(dailySettlementJob, parameters);
```

Two calls on the same day will target the same JobInstance if the Job name and identifying parameters are the same. If the first is running, the second call should not create another independent processing for the same instance. If the first has failed, the same parameters can be used to restart according to Spring Batch's rules.

If each call adds a new identifying timestamp or UUID, Spring Batch will treat them as different JobInstances. This can be appropriate when the business allows multiple independent runs, but it is not a way to prevent duplicate runs for one business period.

## 6. Transactions and Metadata Consistency

`JobRepository` uses transactions to write metadata. The operations that create a JobExecution and StepExecution need to be protected so that concurrent launches do not produce contradictory metadata state.

With a JDBC repository, Spring Batch configures an isolation level for some execution-creation operations; the default level for the create operation is usually `SERIALIZABLE`. The specific mechanism also depends on the database, the transaction manager, and the repository configuration. The primary/unique key constraints in the metadata schema are also an important layer of protection.

In a single-instance environment, you do not need to deploy a distributed coordination system just to protect metadata among multiple nodes, because there is currently only one application node. However, you still need to keep the repository transactions and schema correct to handle concurrent launches within the same process and to protect state across incidents.

For chunk-oriented processing, a chunk's transaction usually includes the read/write operations per the configuration and the checkpoint update. When a chunk commits, the corresponding progress is saved. If the transaction rolls back, the changes belonging to that transaction are undone; the chunks that committed earlier are retained.

This should not be understood to mean that every side effect is rolled back along with the metadata. Calling an external API, sending email, writing a file, or publishing a message can happen outside the database transaction. If the process stops after the side effect has occurred but before the metadata is committed, that operation may be performed again on restart. Therefore, the Job still needs an idempotency key, a unique constraint, a transactional outbox, or a suitable reconciliation mechanism.

## 7. Monitoring JobRepository with JobExplorer

`JobRepository` serves writing and managing metadata during execution. To read execution information for an administration screen or monitoring, Spring Batch provides `JobExplorer`.

For example, you can query the executions of a JobInstance:

```java
@Service
public class BatchStatusService {

    private final JobExplorer jobExplorer;

    public BatchStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<JobExecution> executionsFor(
            String jobName, JobParameters parameters) {

        JobInstance instance = jobExplorer.getJobInstance(
                jobName, parameters);

        if (instance == null) {
            return List.of();
        }

        return jobExplorer.getJobExecutions(instance);
    }
}
```

The snippet illustrates reading metadata; depending on the specific API of the Spring Batch version, how JobParameters are created and queried may need adjusting to the overload that is provided. When building an administration endpoint, only allow authorized people to view status and avoid letting clients modify metadata directly.

The information that usually needs to be displayed includes:

- The Job name, JobInstance ID, and JobExecution ID.
- The identifying parameters of the run.
- The current status and the start/end times.
- The list of StepExecutions with each Step's status.
- Read count, write count, filter count, and skip count.
- Error information to support investigation.

With a single instance, the monitoring screen can run right inside that application. However, metadata should still be stored in the database so the history persists after the application process restarts.

## 8. Operating the Schema and Metadata Data

The Spring Batch schema is part of the application infrastructure. When deploying, you need to ensure the schema matches the Spring Batch version in use and is updated in a controlled way.

Some practical principles:

1. **Initialize the schema once in a controlled way:** a development environment can use the schema script shipped with Spring Batch; production should use controlled migrations.
2. **Do not delete metadata that is in use:** deleting metadata tables or rows can lose the JobExecution state and the checkpoints needed for restart.
3. **Have a retention policy:** metadata can grow with the number of runs. Define how long to keep history, how to archive, and when to clean up after the Job has finished and no longer needs restart.
4. **Back up the metadata database:** if restart capability and run history are important, include the metadata in the backup/restore plan.
5. **Check database permissions:** the application account needs suitable permissions to read, write, and update the metadata tables.
6. **Monitor size and performance:** the number of executions, large contexts, and update frequency can increase size or affect queries.

You should not arbitrarily edit the state in `BATCH_JOB_EXECUTION` or `BATCH_STEP_EXECUTION` with SQL to force a Job to run again. If the metadata is inconsistent, use a proven operational procedure, reconcile against business data, and preserve the history that is needed.

## 9. Limits and Notes Specific to Single Instance

The single-node model makes deployment simple but has some operational limits:

- If the node stops working, no other node automatically takes over the running Job. You need to restart the application and handle the unfinished execution through the restart procedure.
- Multiple Jobs in the same JVM can compete for CPU, memory, the connection pool, and database resources.
- A scheduler can trigger a new Job while the previous one is still running, especially when the processing time varies.
- If the application uses memory as the place to store state, restarting the process can lose history and checkpoints.
- A fault or maintenance on the node can simultaneously affect both the online API and batch jobs if they run in the same application.

To reduce risk, control the run schedule and the level of parallelism, set reasonable timeouts for dependencies, limit chunk size based on actual load, and monitor the JobExecution status. If a Job is not allowed to overlap with itself, you can use stable identifying parameters per business period combined with checking the execution status before allowing it to run.

When the system grows to multiple instances, a shared durable JobRepository used among the nodes becomes more important so the nodes see the same metadata. However, scaling to multiple nodes also requires evaluating the scheduler, work distribution, transactions, shared resources, and idempotent behavior. Having just one JobRepository does not by itself solve the whole distributed coordination problem.

## 10. Design Checklist for a Single-Instance Application

Before putting a Job into production, confirm that:

- `JobRepository` uses a durable metadata store, usually a database.
- The Spring Batch schema is initialized and upgraded in the correct version.
- The identifying JobParameters correctly reflect one business run.
- The Job can restart if the business requirements need recovery after an error.
- The reader saves an appropriate checkpoint and the input data is stable between runs.
- The writer and external side effects are safe on retry or re-run.
- The scheduler and API do not inadvertently create unintended overlapping executions.
- JobExplorer or an equivalent monitoring mechanism can provide the needed status and counters.
- The metadata is backed up and has a clear retention/cleanup policy.

## Conclusion

In a single-instance environment, `JobRepository` is still the center for storing metadata and managing the execution lifecycle of Spring Batch. A single node helps reduce deployment complexity, but it does not eliminate the need for persistence, transactions, control of concurrent launches, and restart after incidents. For a production application, you should use a JDBC JobRepository that stores metadata in a database, manage the schema by version, define JobParameters clearly, and design readers/writers to be safe when re-run. `JobExplorer` helps read metadata for monitoring, while business data is still managed through the application's own data-access components.
