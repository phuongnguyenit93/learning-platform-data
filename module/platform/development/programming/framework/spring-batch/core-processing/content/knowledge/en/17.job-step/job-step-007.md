# Distinguishing JobStep from Nested Flows

In Spring Batch, both `JobStep` and nested flows help organize a large Job into separately manageable units of work. However, the two approaches have different execution boundaries.

- **`JobStep`** invokes another Job through `JobLauncher`. The invoked Job has its own `JobInstance` and `JobExecution`, with `JobParameters` extracted from the parent Job's execution.
- **A nested flow (subflow)** is a `Flow` consisting of multiple Steps embedded into the parent Job's flow. Steps inside the subflow still belong to the same `JobExecution` of the parent Job; no independent child Job is launched.

Therefore, use `JobStep` when the unit of work needs its own Job lifecycle, can run independently, receives its own parameter set, or is tracked/restarted like a separate Job. Use a subflow when you want to group and reuse a sequence of Steps within the same Job, with the same `JobExecution` context and a unified control flow.

## 1. Two Ways to Organize a Large Job

Suppose an order processing workflow has stages for data preparation, validation, enrichment, database loading, and report generation. You can divide the workflow into smaller parts in two ways.

### Using JobStep

The parent Job invokes a child Job at a Step:

```text
Parent Job
  |
  +--> Prepare Step
  |
  +--> JobStep: launch Child Job
  |       |
  |       +--> Child JobExecution
  |               |
  |               +--> Validate Step
  |               +--> Enrich Step
  |               +--> Load Step
  |
  +--> Report Step
```

The child Job has its own Job name, `JobInstance`, `JobExecution`, `JobParameters`, and `StepExecution`s. `JobStep` is the Step of the parent Job used to launch and receive the outcome from the child Job.

### Using a Nested Flow

The parent Job contains a subflow as part of the same flow:

```text
Parent JobExecution
  |
  +--> Prepare Step
  |
  +--> Processing Flow
  |       |
  |       +--> Validate Step
  |       +--> Enrich Step
  |       +--> Load Step
  |
  +--> Report Step
```

A subflow simply groups Steps into a logical unit. Internal Steps run within the parent Job's `JobExecution`. No `JobLauncher` calls a child Job and no child `JobInstance` is created.

## 2. What is JobStep?

`JobStep` is an implementation of `Step` used to run another Job. It acts as a bridge between the parent Job and the child Job:

1. The parent Job begins executing the Step configured as `JobStep`.
2. `JobStep` obtains `JobParameters` for the child Job via `JobParametersExtractor`.
3. `JobStep` invokes the child Job via `JobLauncher`.
4. The child Job creates or locates the corresponding `JobInstance`, then creates a `JobExecution` if launch conditions permit.
5. The child Job executes its own Steps and updates metadata.
6. `JobStep` receives the child Job's execution outcome and reflects it onto the parent Job's `StepExecution`.
7. The parent Job's flow continues or ends based on `JobStep`'s result.

The child Job is a real Job in Spring Batch, and can be launched separately by a scheduler or another application if configuration permits. `JobStep` is simply a way for the parent Job to invoke the child Job as part of a larger workflow.

## 3. Configuring JobStep in Spring Batch 5

You can declare `JobStep` using `StepBuilder.job(...)`, then supply `JobLauncher` and `JobParametersExtractor`:

```java
@Bean
Step childJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job childImportJob,
        JobParametersExtractor childParametersExtractor) {

    return new StepBuilder("childImportJobStep", jobRepository)
            .job(childImportJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

In this example:

- `childImportJob` is the Job to be launched.
- `jobLauncher` executes the request to launch the child Job.
- `childParametersExtractor` creates the `JobParameters` set for the child Job run.
- `childImportJobStep` is the Step residing in the parent Job's flow.

`JobStep` does not automatically turn every parameter of the parent Job into child parameters according to a suitable business rule. Configure the extractor to pass the exact values the child Job needs.

### Extracting JobParameters for the Child Job

`JobParametersExtractor` takes the `Job` and `JobStep`'s `StepExecution` to build the parameter set for the child Job. You can use `DefaultJobParametersExtractor` or implement a custom extractor.

Example of a custom extractor copying several parameters from the parent Job:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    return (childJob, stepExecution) -> {
        JobParameters parentParameters = stepExecution
                .getJobExecution()
                .getJobParameters();

        return new JobParametersBuilder()
                .addString(
                        "businessDate",
                        parentParameters.getString("businessDate"),
                        true)
                .addString(
                        "inputFile",
                        parentParameters.getString("inputFile"),
                        true)
                .addString(
                        "requestedBy",
                        parentParameters.getString("requestedBy"),
                        false)
                .toJobParameters();
    };
}
```

The example assumes the parent Job has already validated that required parameters have values. The child Job's identifying parameters must reflect the business identity of the child unit of work. If the child Job processes the same dataset, keeping the same identifying parameters helps identify the same `JobInstance`; if it is a different child batch, a distinct business key is needed.

Do not add a timestamp or random UUID to identifying parameters merely to avoid `JobInstanceAlreadyCompleteException`. Doing so can turn a restart into a new `JobInstance` and cause data to be reprocessed from the beginning.

### Using DefaultJobParametersExtractor

If you need to pass existing parameters by name, you can configure the default extractor:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    DefaultJobParametersExtractor extractor =
            new DefaultJobParametersExtractor();

    extractor.setKeys(new String[] {
            "businessDate",
            "inputFile"
    });

    return extractor;
}
```

Selected keys must exist in the scope read by the extractor according to the configuration of the Spring Batch version in use. If you need complex mapping, changing identifying flags, or combining data from Job/Step `ExecutionContext`, a custom `JobParametersExtractor` is usually clearer.

## 4. The Child Job Has Separate Metadata

An important distinction of `JobStep` is that the child Job has an independent metadata lifecycle. When launched, the child Job has:

- Its own Job name.
- Its own `JobInstance`, determined by the child Job name and its identifying `JobParameters`.
- Its own `JobExecution` for each run or restart.
- Its own `StepExecution`s for the Steps inside the child Job.
- Its own Job `ExecutionContext` and Step `ExecutionContext`.

The parent Job also has its own metadata. `JobStep` is a `StepExecution` within the parent `JobExecution`; the launched child Job creates an independent `JobExecution`. In a typical setup, both may share a `JobRepository` database for history management, yet the executions remain distinct executions.

Conceptual diagram:

```text
Parent JobInstance
  |
  +-- Parent JobExecution 7001
        |
        +-- StepExecution: prepareStep
        |
        +-- StepExecution: childJobStep
        |       |
        |       +-- Child JobInstance
        |             |
        |             +-- Child JobExecution 8101
        |                    |
        |                    +-- StepExecution: validate
        |                    +-- StepExecution: load
        |
        +-- StepExecution: reportStep
```

Consequently, you can query and observe the child Job as an independent Job via `JobExplorer`, while the parent Job still records that `JobStep` ran and its outcome.

## 5. What is a Nested Flow?

A `Flow` is a structure describing a sequence of Steps, conditional branches, and end points. A subflow is a `Flow` defined separately and then included into the parent Job's flow.

For example, grouping three Steps—validation, normalization, and loading—into a `Flow`:

```java
@Bean
Flow orderProcessingFlow(
        Step validateOrdersStep,
        Step normalizeOrdersStep,
        Step loadOrdersStep) {

    return new FlowBuilder<SimpleFlow>("orderProcessingFlow")
            .start(validateOrdersStep)
            .next(normalizeOrdersStep)
            .next(loadOrdersStep)
            .build();
}
```

Adding the subflow to the parent Job:

```java
@Bean
Job parentImportJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Flow orderProcessingFlow,
        Step createReportStep) {

    return new JobBuilder("parentImportJob", jobRepository)
            .start(prepareInputStep)
            .next(orderProcessingFlow)
            .next(createReportStep)
            .end()
            .build();
}
```

Here, `orderProcessingFlow` is simply a structural part of `parentImportJob`. Steps inside the subflow execute as Steps of the parent Job. No `JobLauncher` is called and no child `JobInstance` is created.

## 6. Subflows Can Contain Conditional Transitions

A subflow is not just a linear list of Steps. It can contain branches based on `ExitStatus`, just like a Job-level flow:

```java
@Bean
Flow validationFlow(
        Step validateStep,
        Step enrichStep,
        Step useExistingDataStep) {

    return new FlowBuilder<SimpleFlow>("validationFlow")
            .start(validateStep)
                .on("NEEDS_ENRICHMENT").to(enrichStep)
            .from(validateStep)
                .on("ALREADY_ENRICHED").to(useExistingDataStep)
            .end();
}
```

The parent Job can chain this subflow with other Steps:

```java
@Bean
Job parentJob(
        JobRepository jobRepository,
        Step prepareStep,
        Flow validationFlow,
        Step reportStep) {

    return new JobBuilder("parentJob", jobRepository)
            .start(prepareStep)
            .next(validationFlow)
            .next(reportStep)
            .end()
            .build();
}
```

A subflow keeps control logic close to related Steps. When one branch is chosen, Steps on the other branch are not executed during that run.

## 7. FlowStep: Wrapping a Flow as a Step

Besides placing a `Flow` directly into a Job flow, Spring Batch also has `FlowStep`, allowing a `Flow` to be packaged as a Step:

```java
@Bean
Step orderProcessingFlowStep(
        JobRepository jobRepository,
        Flow orderProcessingFlow) {

    return new StepBuilder("orderProcessingFlowStep", jobRepository)
            .flow(orderProcessingFlow)
            .build();
}
```

`FlowStep` is useful when you want to use a `Flow` where a Step is expected or encapsulate a cluster of Steps into one unit in a higher-level flow. It still executes the `Flow` within the parent Job's context; it does not launch another Job and does not create a child `JobInstance` like `JobStep`.

When using `FlowStep`, understand that the `Flow` is wrapped as a Step structurally. Actual Steps inside the `Flow` still have executions and metadata per Spring Batch's mechanism. Do not treat `FlowStep` as a way to create an independent Job boundary.

## 8. Comparing JobStep and Nested Flows

| Criterion | JobStep | Subflow in Parent Job |
|---|---|---|
| Component invoked | Another Job | A `Flow` of Steps |
| `JobInstance` | Has a child `JobInstance` | Does not create a new `JobInstance` |
| `JobExecution` | Has a child `JobExecution` | Uses the parent Job's `JobExecution` |
| `JobParameters` | Passed via `JobParametersExtractor` | Uses the parent Job's `JobParameters` |
| `StepExecution` | `JobStep` has a parent `StepExecution`; child Job has its own `StepExecution`s | Steps in the subflow belong to the parent `JobExecution` |
| `JobRepository` | Child Job records separate execution metadata; can share repository | Executions belong to the parent Job |
| Restart | Child Job has its own restart policy; parent Job must also handle `JobStep` outcome | Restarts per parent Job's `JobInstance` and flow |
| Independent execution | Child Job can be launched separately | Subflow is not an independent Job; needs a Job containing it |
| Reusability | Reuses a complete Job | Reuses a logical Step/flow group |
| Flow control | Parent Job controls before/after `JobStep`; child Job controls internal flow | One continuous flow controls Steps in the same Job |
| Parameters and context | Requires extracting parameters; contexts of the two Jobs are not automatically one | Steps share the parent Job's `JobExecution` context via context promotion mechanisms |
| Suitable when | There is an independent sub-workflow needing separate history and lifecycle | You want to group Steps within the same business workflow |

## 9. When Should You Use JobStep?

`JobStep` fits when the unit of work is viewed as a business or operationally independent Job.

### Child Job Needs to Run Independently

For example, the system has `customerImportJob` and `accountReconciliationJob`. A master Job can call each child Job via `JobStep`, while each child Job can also be run independently by a scheduler when needed.

### Need Separate Execution History and Status

If you want to track the child Job with its own `JobInstance`/`JobExecution`, query it separately via `JobExplorer`, or apply an independent restart policy, `JobStep` is the right choice.

### Need to Pass a Dedicated Parameter Set

The child Job may need a different business key, business date, or batch code than the parent Job. `JobParametersExtractor` lets you define the child Job's input data precisely.

### Need to Separate Deployment Teams or Ownership

A development team can manage the child Job as a complete workflow with its own Steps, listeners, validators, and restart policy. The parent Job is only responsible for orchestrating child Jobs in a broader sequence.

### Want to Nest a Job with a Complex Flow

If the sub-workflow is already a Job with multiple branches, deciders, listeners, or custom restart rules, invoking it via `JobStep` preserves independent boundaries and structure.

## 10. When Should You Use a Nested Flow?

A subflow fits when you only need to group Step logic without needing a new `JobExecution`.

### Steps Are Stages of the Same Workflow

For example, `validateStep`, `normalizeStep`, and `loadStep` are natural stages of a single import. They share business parameters and parent Job state.

### Want to Reuse a Cluster of Steps

A `Flow` can be used across multiple different Jobs if the Steps and parameters are compatible. Reusing a `Flow` does not create a child Job and does not add a `JobLauncher` layer.

### Want a Single JobExecution

If operations want one `JobExecution` representing the entire workflow, a subflow keeps Steps inside the same execution. Monitoring, restarts, and flow status are managed as one unified Job.

### No Need for an Independent Child Job

If there is no need to launch separately, no need for a separate `JobInstance`, or no need for a separate `JobParameters` set, a subflow is usually simpler than `JobStep`.

## 11. Parameters and ExecutionContext Between Parent Job and Child Job

`JobStep` creates a boundary between two Jobs. The child Job's `JobParameters` are built by `JobParametersExtractor`; do not assume all parent `JobParameters` are automatically passed or that parent and child contexts are the same object.

If the child Job needs data from the parent Job:

1. Clearly define the parameters the child needs to receive.
2. Use `JobParametersExtractor` to map those values.
3. Choose identifying flags according to the child Job's business identity.
4. Validate parameters in the child Job before performing side effects.
5. Use repository and metadata APIs to look up child executions.

With a subflow, Steps use the parent Job's `JobParameters`. If one Step produces data in Step `ExecutionContext` and another Step needs it, you can use `ExecutionContextPromotionListener` to promote the required key to Job `ExecutionContext`.

Do not use the parent Job's Job `ExecutionContext` as an automatic sharing channel with a child Job. If you need to pass large data, store the data in a database or storage and pass a safe business key/URI via `JobParameters`.

## 12. Restart and Failures When Using JobStep

`JobStep` has two layers of state:

- The parent Job's `JobExecution`, containing the `StepExecution` representing `JobStep`.
- The child Job's `JobInstance`/`JobExecution` launched from `JobStep`.

When the child Job fails, `JobStep` normally reflects the failure outcome and the parent Job's flow handles it per configured transitions. You can restart the parent Job if conditions allow; re-running `JobStep` launches the child Job with parameters generated by the extractor.

Because the child Job has its own identity, understand the behavior when the parent Job restarts:

- If the child Job failed and is restartable, the same identifying parameters allow resuming the child `JobInstance`.
- If the child Job completed yet the parent Job failed to record `JobStep` completion due to a rare failure window, re-launching with the same identifying parameters may encounter an already-completed `JobInstance` state. Test this scenario and design an appropriate recovery procedure.
- If the extractor generates new identifying parameters on every restart, the child Job may be treated as a new `JobInstance` and run from the beginning.

Do not solve the problem by adding a random ID to every invocation. Define the child business key, child execution state, and relationship between parent and child runs.

## 13. Restart and Failures When Using a Subflow

A subflow shares the same `JobInstance` and `JobExecution` as the parent Job. When the parent Job restarts:

- Already-completed Steps are normally skipped per restart policy.
- Failed or incomplete Steps are handled according to the parent Job's metadata and checkpoints.
- Subflow branches are evaluated according to the flow and execution state.
- There is no separate child Job to restart independently.

If a Step inside a subflow fails, you can restart the parent Job conditionally. You cannot launch a subflow by itself as an independent Job; if independent execution is needed, package it as a Job or create a `JobStep` calling a separate Job.

## 14. Transactions and Execution Boundaries

`JobStep` does not create a single transaction wrapping the entire parent Job and child Job. Steps inside the child Job manage transactions according to their own configuration. `JobStep` only orchestrates launching and receiving the result of the child Job.

With a subflow, Steps still belong to the parent Job, yet each chunk/Tasklet Step has transaction boundaries per its own configuration. Sharing the same `JobExecution` does not mean the entire subflow runs inside one giant transaction.

In both approaches, do not assume a JDBC transaction can roll back every side effect in external systems. If the child Job or Step sends HTTP requests, emails, messages, or manipulates files, design idempotency, outbox, or reconciliation for restarts.

## 15. Observability and Operations

### Monitoring JobStep

When using `JobStep`, you can query:

- Parent `JobExecution` to see the overall large workflow.
- Parent `StepExecution` of `JobStep` to see the status of the step that invoked the child Job.
- Child `JobExecution` to see status, exit code, timing, and `StepExecution`s inside the child Job.

A child Job can have multiple runs across restarts. Therefore, when displaying on a dashboard, link parent `JobExecution` ID with child `JobExecution` ID using explicitly stored/recorded correlation info.

### Monitoring a Subflow

With a subflow, query the parent Job's `JobExecution` and internal `StepExecution`s. Do not look for a child `JobExecution` because no child Job was launched.

## 16. Common Mistakes

### Using JobStep Just to Group a Few Steps

If Steps are merely stages of the same Job, `JobStep` creates extra `JobInstance`/`JobExecution`, requires parameter extraction, and complicates restarts. A subflow is usually more suitable.

### Using a Subflow When an Independent Sub-Workflow Is Needed

A subflow cannot be launched independently via `JobLauncher` and has no separate `JobInstance` metadata. If separate history, parameters, and restarts are required, create a child Job and invoke it with `JobStep`.

### Not Configuring JobParametersExtractor

The child Job may miss required parameters or receive incorrect identifying parameters. Define the child parameter contract and explicit mapping.

### Passing a Random Timestamp to the Child Job

This can create a new child `JobInstance` on every parent restart, breaking proper instance restart and causing duplicate processing. Use a stable business key.

### Confusing Parent and Child ExecutionContext

The child Job has its own context. Use an extractor to pass parameters or shared storage via a reference key; do not assume contexts are shared automatically.

### Thinking JobStep and Child Job Are in the Same Transaction

`JobStep` calls `JobLauncher`; the child Job's transactions are managed by its own configuration. The parent Step does not create a distributed transaction wrapping all operations.

### Thinking FlowStep Is JobStep

`FlowStep` wraps a `Flow` as a Step without launching a new Job. To get a child `JobInstance`/`JobExecution`, you need `JobStep`.

## 17. Process for Choosing Between JobStep and Nested Flows

When designing a large workflow, ask the following questions:

1. Does this unit of work need to be launched independently outside the parent Job? If yes, prefer a separate Job and `JobStep`.
2. Does it need its own `JobInstance`, `JobExecution`, `JobParameters`, and restart policy? If yes, use `JobStep`.
3. Is this unit of work simply a sequence or branch of Steps in the same workflow? If yes, use a subflow.
4. Do the Steps need to share the same `JobParameters` and Job `ExecutionContext`? If yes, a subflow is usually more natural.
5. Do you need to wrap a `Flow` to use as a Step? Consider `FlowStep`; it still does not create a child Job.
6. If using `JobStep`, have you defined stable identifying parameters and an extractor?
7. Have you tested restarting both parent and child, especially the failure window between child completion and parent metadata update?
8. Have you defined transaction boundaries and idempotency of side effects?

| Need | Suitable Choice |
|---|---|
| Calling an independent reconciliation Job from a master Job | `JobStep` |
| Child Job can be run separately by a scheduler | `JobStep` |
| Child Job needs its own `JobParameters` and restart | `JobStep` |
| Grouping validate, transform, and load within the same Job | Subflow |
| Reusing a Step sequence across multiple Jobs | Subflow |
| Wanting one `JobExecution` to track the entire workflow | Subflow |
| Wrapping a `Flow` into one Step in an upper-level flow | `FlowStep` |

## Conclusion

`JobStep` launches another Job, creates a separate `JobInstance`/`JobExecution` boundary, and passes parameters via `JobParametersExtractor`. It fits when a sub-workflow needs to run independently and have its own metadata, parameters, and restart policy. Nested flows simply group Steps within the parent Job's same `JobExecution`; they fit for organizing and reusing stages of a unified workflow. `FlowStep` can wrap a `Flow` into a Step while still not creating a child Job. Choose based on business boundaries, operational needs, parameters, restarts, and transactions rather than simply flow length.
