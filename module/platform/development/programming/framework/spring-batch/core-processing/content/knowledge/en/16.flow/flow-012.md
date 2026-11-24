# Avoiding hard-to-follow flows with too many branches

A Job flow in Spring Batch describes how steps and flow components connect to one another. When a job has multiple business outcomes, declaring transitions helps select the right path. However, if every minor condition creates another branch, the flow quickly turns into a large graph that is hard to understand, test, and operate.

Good design keeps the number of paths to what is truly needed, places decisions in the right layer, and groups stages with shared responsibilities into readable steps or subflows. The flow should express the main orchestration structure; detailed data rules belong inside processors, services, deciders, or appropriate error policies.

## 1. Why do too many branches make a flow hard to maintain?

A job might branch by validation outcome, file type, tenant, ingestion channel, processing mode, business date, or external system status. If each value is represented by a separate transition, the number of edges and paths grows rapidly.

For example, a data import job might branch across three file types, two processing modes, and four customer groups. Combining all conditions in the flow can push the number of cases to track up to 3 × 2 × 4 = 24 combinations. Adding a new condition makes the graph even harder to read.

```text
                 +--> CSV + normal + group A
                 +--> CSV + normal + group B
                 +--> CSV + special + group A
validateInput ---+--> XML + normal + group A
                 +--> XML + special + group C
                 +--> JSON + normal + group D
                 +--> ... many other paths
```

Common problems that emerge:

- Hard to see the job's main path because specific transitions and wildcards interleave.
- The same group of steps is declared repeatedly across multiple branches.
- A small business change requires editing many transitions.
- Easy to miss an exit code or create a branch with no ending path.
- Hard to write tests covering every combination of conditions.
- Operators struggle to explain why an execution took a specific branch.

## 2. Branch only when the path is genuinely different

Not every business condition needs to become a branch in the job flow. Before adding a transition, determine whether the condition changes the **orchestration stages** or merely changes how an item is handled.

| Condition | Usually appropriate handling |
|---|---|
| Invalid record that can be ignored | Validation, exception, and skip policy inside the step |
| Record outside processing scope | Processor filtering via `null` or reader selecting the right data |
| Differs only in per-item transformation | `ItemProcessor` or strategy service |
| Transient connection error | Retry policy, timeout, and backoff |
| Validation outcome decides to run a different group of steps | Conditional flow or `JobExecutionDecider` |
| A shared stage must run after a step | Merge branches back into a shared step |

For example, there is no need to create a flow branch for each order type if they all go through the same write step. Let the processor pick a transformation strategy by order type, while the flow keeps a single `validate -> process -> write` path.

## 3. Keep the main path linear

When most of a job always runs in the same order, express the main chain with `start()` and `next()`. Split branches only at points where a genuinely different workflow must be selected.

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step classifyInputStep,
        Step processOrdersStep,
        Step publishResultStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
        .start(validateInputStep)
        .next(classifyInputStep)
        .next(processOrdersStep)
        .next(publishResultStep)
        .build();
}
```

This is a sequential flow when all steps follow the same path. If a step fails, the job stops under normal behavior and can be restarted when metadata permits. There is no need to create separate branches just to represent technical errors if step-level retry/skip already handles them.

## 4. Use meaningful exit codes and limit outcome counts

Conditional flows rely on a step's `ExitStatus`. A step can return standard exit codes like `COMPLETED`, `FAILED`, or a custom code like `EMPTY_INPUT` or `INVALID_INPUT`.

Do not create an exit code for every granular data value, such as `CSV_TENANT_A`, `CSV_TENANT_B`, `XML_TENANT_A`, `XML_TENANT_B`. Group outcomes into a small set of stable orchestration statuses.

For example, a classification step only needs to emit three outcomes:

- `READY`: valid data is present and ready to process.
- `EMPTY`: valid source but no data to import.
- `INVALID`: input violates the contract.

The flow then handles these three outcomes at the workflow level. Differences such as tenant, column layout, or mapping rules should be resolved inside dedicated components.

## 5. Use JobExecutionDecider for runtime decisions

When you need to choose a branch based on `JobParameters`, business state, or runtime details, `JobExecutionDecider` encapsulates the decision logic in a separate component. The flow only maps the decider's result to paths.

```java
@Bean
JobExecutionDecider inputDecider(InputPolicyService policyService) {
    return (jobExecution, stepExecution) -> {
        String mode = jobExecution.getJobParameters().getString("mode");
        InputDecision decision = policyService.decide(mode);

        return new FlowExecutionStatus(decision.name());
    };
}
```

Flow using the decider:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step inspectInputStep,
        JobExecutionDecider inputDecider,
        Step processStandardStep,
        Step processPriorityStep,
        Step finishEmptyInputStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(inspectInputStep)
        .next(inputDecider)
            .on("STANDARD").to(processStandardStep)
        .from(inputDecider)
            .on("PRIORITY").to(processPriorityStep)
        .from(inputDecider)
            .on("EMPTY").to(finishEmptyInputStep)
        .from(inputDecider)
            .on("*").fail()
        .end()
        .build();
}
```

A decider separates decisions from flow configuration, yet the decider itself should stay simple. Let a dedicated service compute the outcome, and have the decider convert that outcome into a small, clear `FlowExecutionStatus`. Avoid turning a decider into a dumping ground for full business logic and unrelated queries.

## 6. Merge branches back to shared steps

When different outcomes need to continue with the same stage, connect their transitions back to a shared step instead of duplicating downstream steps on every branch.

```java
return new JobBuilder("importJob", jobRepository)
    .start(classifyInputStep)
        .on("STANDARD").to(processStandardStep)
    .from(classifyInputStep)
        .on("PRIORITY").to(processPriorityStep)
    .from(processStandardStep)
        .on("COMPLETED").to(publishResultStep)
    .from(processPriorityStep)
        .on("COMPLETED").to(publishResultStep)
    .from(publishResultStep)
        .on("COMPLETED").end()
    .from(publishResultStep)
        .on("*").fail()
    .end()
    .build();
```

Here, two distinct processing branches both converge on `publishResultStep`. The result-publishing step is declared only once. This convergence reduces duplicate configuration and makes changing the shared step easier.

When converging, ensure the shared step receives the necessary data from both branches. You can store classification results or needed metadata in the `JobExecution` context, or use a unified output format.

## 7. Package step groups into subflows

When a branch consists of multiple steps with a cohesive responsibility, you can group them into a sub-`Flow`. The top-level job then shows only high-level phases, while internal details live inside the subflow.

```java
@Bean
Flow standardImportFlow(
        Step parseStandardFileStep,
        Step validateStandardRowsStep,
        Step writeStandardRowsStep) {

    return new FlowBuilder<SimpleFlow>("standardImportFlow")
        .start(parseStandardFileStep)
        .next(validateStandardRowsStep)
        .next(writeStandardRowsStep)
        .build();
}
```

The job-level flow can use this subflow alongside other flows. This organization works well when each group has a clear responsibility and is substantial enough to be read, tested, or reused independently.

Do not create a subflow for every single step. Too many nested layers also force readers to jump across multiple files just to understand the path. Extract a subflow only when its name represents a meaningful business stage.

## 8. Separate flow orchestration from error handling

One reason flows bloat is adding transitions for every error that might happen. Many errors should be resolved at the step level:

- Transient errors: bounded retry.
- Invalid items that can be discarded: skip policy and `SkipListener`.
- Valid items outside scope: filters or conditional queries.
- Severe errors: let the step fail and handle restart after fixing the root cause.

The flow needs a branch only when an outcome changes the next stage of the workflow. For example, `INVALID_INPUT` might route to a flow that stores the rejected file, whereas `TransientDataAccessException` should usually be retried inside the step rather than creating a dedicated flow branch.

## 9. Keep wildcards and transitions explicit

For conditional flows, use specific patterns for expected outcomes and a single fallback branch for remaining outcomes. Declare specific transitions before wildcards so readers immediately recognize actively handled cases.

```java
.start(validateInputStep)
    .on("INVALID_INPUT").to(rejectInputStep)
.from(validateInputStep)
    .on("COMPLETED").to(processInputStep)
.from(validateInputStep)
    .on("*").fail()
```

`on("*")` is the catch-all branch. It helps ensure unexpected outcomes have defined behavior, though a wildcard should never be used to funnel serious errors onto a completed success branch.

For each step with conditional transitions, identify every exit code that may arise and ensure each code has an appropriate path. If a step emits too many exit codes, consider consolidating outcomes or moving the decision to a decider.

## 10. Do not turn every parameter into a branch

`JobParameters` typically identify the data or scope of work, and do not necessarily alter flow structure.

For example, a job running for multiple tenants can use the exact same flow and pass `tenantId` in `JobParameters`. Readers, processors, and writers are configured to process data for that tenant. There is no need to create a branch per tenant.

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("tenantId", tenantId, true)
    .addString("businessDate", businessDate.toString(), true)
    .toJobParameters();
```

Create a branch only when a tenant or parameter truly selects a different workflow—for example, type-A tenants must pass through a separate reconciliation system. When only data values differ, keeping a shared flow scales much better.

## 11. When should you use Split and parallel execution?

`split()` is used when independent flows can run in parallel. This is a different orchestration construct from creating many sequential branches.

For example, after preparing data, a job can generate reports and update a search index independently:

```java
Flow reportFlow = new FlowBuilder<SimpleFlow>("reportFlow")
    .start(generateReportStep)
    .build();

Flow indexFlow = new FlowBuilder<SimpleFlow>("indexFlow")
    .start(updateSearchIndexStep)
    .build();

Flow parallelFlow = new FlowBuilder<SimpleFlow>("parallelFlow")
    .split(taskExecutor)
    .add(reportFlow, indexFlow)
    .build();
```

Use parallelism only when the two flows are truly independent in data, transactions, and resources. Clarify how to handle one flow failing while the other has completed, and how results are aggregated. Do not use `split()` just to make a diagram look shorter.

## 12. Keep decision logic in a testable place

When business conditions are complex, move the calculation into a pure service or policy component that can be tested independently. The decider should only call the service and return a finite outcome.

```java
public enum ImportRoute {
    STANDARD,
    PRIORITY,
    EMPTY,
    REJECT
}

@Service
public class ImportRoutingPolicy {

    public ImportRoute determine(InputSummary summary) {
        if (!summary.isValid()) {
            return ImportRoute.REJECT;
        }
        if (summary.recordCount() == 0) {
            return ImportRoute.EMPTY;
        }
        return summary.isPriority()
            ? ImportRoute.PRIORITY
            : ImportRoute.STANDARD;
    }
}
```

An enum clarifies the possible set of outcomes and avoids scattered string literals in code. You can test the policy against edge cases without launching the whole job. When policy rules change, the flow only needs adjustment if the set of paths itself changes.

## 13. Design flows to be observable and testable

Every branch should have a clear name, condition, and endpoint. Operators need to see why an execution entered a branch, and developers need to write tests for key outcomes.

Helpful practices:

1. Name exit codes after concise business statuses, without embedding personal data or dynamic values.
2. Log decision outcomes alongside the `JobExecution` ID for traceability.
3. Test every value a decider can return.
4. Test wildcard branches or invalid outcomes.
5. Test converging paths and confirm required data is available to the shared step.
6. Test restarts at potential failure points in each branch.
7. Avoid logging full `JobParameters` if they contain sensitive data.

As branch count grows, a decision table is often easier to read than a dense flow diagram:

| Classification outcome | Path |
|---|---|
| `STANDARD` | `processStandardStep` then `publishResultStep` |
| `PRIORITY` | `processPriorityStep` then `publishResultStep` |
| `EMPTY` | `finishEmptyInputStep` then end |
| `REJECT` | `rejectInputStep` then end per policy |
| Unknown outcome | End as failed for investigation |

## 14. Planning before adding a new branch

When a new requirement proposes adding a branch, clarify:

1. Does the new condition change the sequence of stages or only how items are processed?
2. Can the same step be reused with a different strategy or parameter?
3. Can branches converge back to a shared step after the divergent part?
4. Should the decision be consolidated into a `JobExecutionDecider` or policy service?
5. Does the new branch multiply combinations with existing conditions?
6. Does every branch have clear endpoints and restart semantics?
7. Can the decision logic be unit tested separately and the paths integration tested?

If a small change requires editing many transitions, that is a signal the flow structure is carrying too much business logic. Consider consolidating conditions, extracting subflows, or moving processing back into services/processors.

## 15. Common design mistakes

| Design approach | Consequence | Improvement |
|---|---|---|
| Creating a branch per tenant or customer code | Flow bloats with runtime data | Pass scope via `JobParameters` and use a shared flow |
| Creating an exit code for every input variant | Too many similar transitions | Group into meaningful orchestration statuses |
| Copying shared steps into each branch | Duplicated configuration and drift on edits | Converge branches onto shared steps |
| Putting all business logic into a decider | Decider is hard to test and read | Extract policy/service; decider only picks the route |
| Using flows for retryable/skippable errors | Flow has unnecessary technical branches | Use step-level fault tolerance |
| Using wildcards so all outcomes complete | Unexpected errors are hidden | Use safe fallback behavior, usually fail |
| Creating too many tiny subflows | Deeply nested configuration | Extract only step groups with clear responsibilities |
| Using split for data-dependent steps | Race conditions or inconsistent results | Parallelize only independent flows |

## Conclusion

Do not turn every business condition into a branch in a Spring Batch job flow. Keep the main path linear, use a small set of meaningful exit codes, delegate complex runtime decisions to a policy service or `JobExecutionDecider`, and converge branches onto shared steps whenever possible.

Subflows package sufficiently large step groups for reuse; `split()` fits only independent flows that can execute in parallel. Retry, skip, and filtering should be handled at the step or item level when they do not change the workflow stages. A well-designed flow clearly highlights the primary phases, has deterministic paths and endpoints, and remains easy to test and restart when errors occur.
