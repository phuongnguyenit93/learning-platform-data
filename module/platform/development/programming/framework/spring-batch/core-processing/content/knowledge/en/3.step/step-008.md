# How Stable Must a Step Name Be?

In Spring Batch, the name of a `Step` is part of the identifier stored in the metadata. This name helps the `JobRepository` recognize which step has run in a `JobInstance`, find its execution history, and recover state when the job is restarted. Therefore, a step name needs to stably describe a processing phase in the job across deployments.

If you rename a step arbitrarily, Spring Batch may treat that step as a new step and run it again from the beginning. If you keep the same name for a phase whose meaning has changed, Spring Batch may treat it as the old step and apply history or checkpoints that no longer fit. Both cases can break restart behavior.

## 1. The Step Name Is an Identifier in the Metadata

When a step is created, the name passed to `StepBuilder` becomes the name of the `Step` object and is written into the `StepExecution` every time the step runs.

An example using the Spring Batch 5 API:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    return new StepBuilder("validateInput", jobRepository)
        .tasklet(validateInputTasklet, transactionManager)
        .build();
}
```

In this example, `validateInput` is the Step name. The method name `validateInputStep` is the name of the bean-declaring method; the Spring bean name can also be configured separately. Spring Batch's metadata uses the name that the `Step` returns through `getName()`, that is, the value passed to `StepBuilder`.

When the step is executed, Spring Batch creates a `StepExecution` containing information such as the step name, status, start/end times, the number of records read/written, and the `ExecutionContext`. In the default metadata schema, the step name is stored in the `STEP_NAME` column of the `BATCH_STEP_EXECUTION` table.

## 2. How Does the Step Name Affect Restart?

A `JobInstance` is identified by the job name together with the identifying `JobParameters`. Within a JobInstance, Spring Batch uses the step name to find the execution history of each phase. On restart, the framework needs to know which steps have completed, which steps need to run again, and which state can be recovered.

For example, a job with three steps:

```text
JobInstance: importOrders(businessDate=2026-11-15)

  Execution #1
    validateInput  -> COMPLETED
    importOrders   -> FAILED
    archiveFile    -> not yet run

  Restart: Execution #2
    validateInput  -> skipped because it has completed
    importOrders   -> run again per the restart policy
    archiveFile    -> runs after importOrders completes
```

Steps with stable names help Spring Batch match a new execution against the history of the same JobInstance. If you rename `importOrders` to `loadOrders` while the JobInstance is still unfinished, the framework may not find the step's history under the old name. The new step may be treated as never having run and start over from the beginning.

This is especially important if the step created side effects before it failed, such as writing data to an external system or sending notifications. Running again from the beginning can create duplicate records or repeat operations.

## 3. Renaming a Step Can Break the Link to Old History

Suppose the first version of the job uses the name `importOrders`:

```java
new StepBuilder("importOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();
```

After a deployment, the development team renames it to `processOrders` just to make the code name more readable:

```java
new StepBuilder("processOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();
```

For a JobInstance that ran with the old version but did not complete, the new name no longer matches the earlier `StepExecution`. On restart, `processOrders` may be treated as a new phase. Spring Batch does not understand on its own that `processOrders` is the `importOrders` that was renamed in the source code.

Therefore, renaming a step is not simply changing a display label. It can change how the framework finds the previous execution, how the run-count limit is applied, and how it decides whether a completed step needs to run again.

## 4. Keep the Name Stable Across Refactors

When you only rename a class, method, package, or the structure of the Java configuration while the business phase is still the same step, keep the name passed into `StepBuilder` unchanged.

For example, you can rename the bean method without changing the metadata identifier:

```java
// New bean method name
@Bean
Step inputValidation(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    // Keep the Step name that was used in previous runs
    return new StepBuilder("validateInput", jobRepository)
        .tasklet(validateInputTasklet, transactionManager)
        .build();
}
```

The following changes usually do not require changing the Step name:

- Renaming the `@Bean` method or a variable in Java.
- Moving the step configuration into another configuration class.
- Splitting the tasklet or reader/writer into separate beans.
- Internal refactoring that keeps the same processing responsibility and the ability to recover checkpoints.
- Improving performance without changing the meaning of the saved state data.

A step name should represent the stable role of the phase and should not reflect temporary implementation details.

## 5. Naming Rules That Are Easy to Maintain

Choose names that are short, meaningful, consistent, and descriptive of the work. For example:

| Recommended name | Meaning |
|---|---|
| `validateInput` | Validate the input data |
| `readOrders` | Read orders |
| `transformOrders` | Transform orders |
| `writeOrders` | Write orders |
| `archiveInputFile` | Archive the input file |
| `publishSummary` | Publish the summary report |

You should apply the following principles:

1. **Use names based on business responsibility.** A person reading the metadata or logs can understand what the step is doing without opening the code.
2. **Keep one naming convention.** For example, use lower camel case for all steps in the project.
3. **Avoid names that are too generic.** `step1`, `process`, and `taskA` do not tell you the role of the phase.
4. **Avoid attaching runtime data to the name.** The processing date, tenant, file name, UUID, or timestamp should be JobParameters or data in the `ExecutionContext`.
5. **Give separate names to different logical phases.** Do not use one name for two steps with different responsibilities just because they call the same service.
6. **Do not use display names or names translated into the user's language.** The step name is a technical identifier that needs to be stable.

For example, you should not create names based on the run date:

```java
// Not recommended: each day creates a different step identifier
String stepName = "importOrders-" + businessDate;
```

Instead, keep the step name fixed and pass the business date through JobParameters:

```java
new StepBuilder("importOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();

// businessDate is passed in the JobParameters of the JobExecution
```

JobParameters identify the unit of work; the Step name identifies the phase within that unit of work. Do not use one concept to replace the other.

## 6. The Step Name Needs to Be Unique Within a Job

In terms of design, each logical phase in the same job should have its own Step name. Avoid declaring two different steps with the same name, even when they use the same kind of tasklet or call the same service.

For example, two phases that share an implementation but have different responsibilities:

```java
@Bean
Step validateCustomerFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet customerValidationTasklet) {
    return new StepBuilder("validateCustomerFile", jobRepository)
        .tasklet(customerValidationTasklet, transactionManager)
        .build();
}

@Bean
Step validateProductFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet productValidationTasklet) {
    return new StepBuilder("validateProductFile", jobRepository)
        .tasklet(productValidationTasklet, transactionManager)
        .build();
}
```

You do not need to create a globally unique name across every job in the application. Two different jobs can have steps with the same name if they are two separate job definitions. However, within the same JobInstance, the names need to distinguish the phases so that the history and the restart policy are not ambiguous.

If you want to reuse logic, reuse the tasklet, reader, writer, or service; each place in the job where the logic is processed should still have a Step name that expresses its role.

## 7. Step Name and ExecutionContext

The `ExecutionContext` contains the state that a step needs to store to continue after a restart, such as the last read position, the number of pages processed, or the current batch ID. This state is stored attached to the `StepExecution` in the JobRepository.

When the Step name changes, Spring Batch may create a new `StepExecution` instead of finding the old execution by name. In that case, the new execution has its own `ExecutionContext` and does not automatically recover the old step's checkpoint.

An example of a reader that saves its read position:

```text
Step name: readOrders

Execution #1
  chunk 1 -> commit
  chunk 2 -> commit
  chunk 3 -> error
  ExecutionContext stores the position after chunk 2

Restart with the same Step name
  find the previous StepExecution
  restore the reader state
  continue after chunk 2
```

If you rename `readOrders` to `loadOrders` before the restart, the new step may not reuse the checkpoint saved under the old name. It may read again from the beginning or initialize a new state, depending on the reader and the configuration.

Besides the Step name, the data structure in the `ExecutionContext` also needs to be compatible across code versions. Keeping the step name does not guarantee a successful restart if the new version no longer understands the saved keys or data types. When you change the checkpoint structure, design a compatibility strategy or handle the old JobInstances before deploying.

## 8. Impact on startLimit and allowStartIfComplete

Some step policies are based on the `StepExecution` history of the JobInstance:

- `startLimit(n)` limits the number of times a step is started.
- `allowStartIfComplete(true)` allows a completed step to be run again when the job is restarted.

For example:

```java
Step refreshReferenceData = new StepBuilder("refreshReferenceData", jobRepository)
    .tasklet(refreshTasklet, transactionManager)
    .allowStartIfComplete(true)
    .startLimit(3)
    .build();
```

These policies rely on the step's execution history. If you rename the step, the history under the new name may not contain the starts or completion status of the old name. The consequence can be that the step runs again unexpectedly or that the run limit no longer reflects the earlier attempts.

Conversely, if you keep the same name for a new step with a different meaning, Spring Batch may apply the old phase's completion history or limits to the new phase. Therefore, the name must be stable when the responsibility does not change and must be changed deliberately when the definition of the work really changes.

## 9. When Should You Rename a Step?

Not every code change requires a new name. Distinguish an implementation change from a change in the definition of the work.

| Change | Recommendation |
|---|---|
| Renaming a method or configuration class | Keep the Step name |
| Optimizing the reader/writer while the checkpoint remains compatible | Keep the Step name |
| Fixing a processing bug while keeping the same responsibility and safe restartability | Usually keep the Step name |
| Splitting one step into two phases with separate responsibilities | Give the new steps their own names and plan for in-flight JobInstances |
| Merging several steps into one step with different state | Handle the old executions explicitly before changing the flow and names |
| Changing the business meaning or an incompatible checkpoint format | Treat this as a process version change and design a deliberate migration |

Renaming a step when its responsibility has changed significantly can help distinguish the metadata of the new process. However, for old JobInstances that have not completed, the new name may cause the phase to run again from the beginning. Determine how to handle these instances before release.

## 10. Deployment Strategy When You Need to Change a Step Name

When you really need to rename or restructure the steps, plan based on the state of the jobs that currently exist:

1. **Identify the in-flight JobInstances.** Check the executions that are running, failed, or stopped and may need to restart.
2. **Assess compatibility.** Determine whether the new code can continue from the old `ExecutionContext` and which side effects might be repeated.
3. **Choose a transition approach.** You can let the old instances finish on the old version, maintain compatibility logic during the transition period, or create a new job definition if this really is a new process.
4. **Check idempotency.** If the step can run again from the beginning, ensure that writing data or calling external services does not produce duplicate results.
5. **Test restart with representative metadata.** Test the cases where the previous step has completed, the current step failed midway, and the step has a checkpoint.

Changing the Job name or adding an identifying JobParameter for the version can create a new JobInstance. This is an option for separating a new process definition from the old history, but the new execution will not be a restart of the previous JobInstance. If you need to continue an in-flight JobInstance, creating a new identity will not meet that need.

Do not directly edit the `STEP_NAME` column in the metadata table just to make the new name match the old history. The metadata has relationships with StepExecution, ExecutionContext, and related tables; manual updates can corrupt the links or state. If you must migrate metadata, you need a separately designed, backed-up, and verified migration process.

## 11. Step Names in a Partitioned Job

With a partitioned step, Spring Batch creates multiple `StepExecution`s for the partitions. The worker execution name is usually built from the base step name together with the partition name, for example `processOrders:partition0` and `processOrders:partition1`.

```text
processOrders
  +-- processOrders:partition0
  +-- processOrders:partition1
  +-- processOrders:partition2
```

The base step name still needs to be stable. The partition name should also stably identify the same unit of data across restarts, so the framework can match the corresponding partition's state. Do not add a timestamp or UUID to the partition name yourself if the goal is to recover the same partition on a later run.

The specific rules for worker names depend on the partition handler and how partitions are named. Let the partition mechanism build names following a consistent convention, and ensure the partition key represents a stable partition of work.

## 12. Checklist for Declaring a Step Name

Before adding a step to a job, ask yourself the following questions:

- Does the name clearly describe the responsibility of the phase?
- Does the name remain unchanged across deployments when the responsibility and checkpoint definition remain compatible?
- Does the name inadvertently contain a date, file, tenant, UUID, or runtime data?
- Is another logical step in the same job using a duplicate name?
- If the name changes, how will old JobInstances that are running or need to restart be handled?
- If you keep the name for new logic, are the old completion history and ExecutionContext still appropriate?
- For a partitioned step, is the partition name stable across restarts?

You can check the Step name at the configuration level with `step.getName()` and check the metadata in the database when investigating restart issues. Integration tests should use a JobRepository that stores real metadata to confirm behavior across multiple JobExecutions.

## Conclusion

The Step name is the metadata identifier of a phase in Spring Batch. The `JobRepository` uses this name together with the JobInstance's history to recognize earlier StepExecutions, decide whether a step has completed or needs to run again, and recover the appropriate state.

Choose names that describe the business responsibility, are unique for each logical phase within the same job, and keep them stable across refactors, deployments, and restarts. Rename only when the definition of the work really changes, and have a plan for old JobInstances, checkpoints, and side effects that may be performed again.
