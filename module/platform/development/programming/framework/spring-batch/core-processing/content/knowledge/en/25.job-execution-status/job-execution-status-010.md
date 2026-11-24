# Do Not Use Status Messages Instead of BatchStatus

In Spring Batch, job and step execution statuses are managed using `BatchStatus`. A descriptive string or message such as “processing finished”, “12 failed records”, or “awaiting reconciliation” cannot replace this status.

`BatchStatus` represents the execution lifecycle that the framework and `JobRepository` need to know whether an execution is running, completed, failed, or stopped. `ExitStatus`, on the other hand, represents the exit outcome of a step/job, consisting of an exit code and a description. The message/description is meant for human readers; it should not be used as control data or to infer lifecycle status.

Properly distinguishing these three concepts prevents jobs from reporting incorrect statuses, flows from branching wrongly, and monitoring systems from misunderstanding whether an execution has finished.

## 1. BatchStatus Represents the Execution Lifecycle

`BatchStatus` is a Spring Batch enum used to represent the execution state of `JobExecution` and `StepExecution`. The framework updates this status while launching, executing, stopping, and finishing a job/step.

Common values:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | Execution is in the initialization phase |
| `STARTED` | Execution is running |
| `STOPPING` | Stop requested and waiting for safe stop |
| `STOPPED` | Execution stopped upon request |
| `COMPLETED` | Execution completed normally |
| `FAILED` | Execution failed |
| `ABANDONED` | Execution marked not to continue/restart via normal procedure |
| `UNKNOWN` | Reliable status cannot be determined |

For example, while a step is processing chunks, `StepExecution.getStatus()` is normally `STARTED`. When the step finishes successfully, the status is updated to `COMPLETED`; if an unhandled exception causes the step to fail, the status is `FAILED`.

`BatchStatus` is not the place to store long descriptions of why a run succeeded or failed. It is a lifecycle status with clear semantics for the framework, operators, and monitoring systems.

## 2. ExitStatus Is the Exit Outcome of a Step/Job

`ExitStatus` is a different object from `BatchStatus`. It has two main parts:

- `exitCode`: a short outcome code, either a standard code or a custom code.
- `exitDescription`: supplemental descriptive text, usually human-readable information for operators.

Common standard codes include `COMPLETED`, `EXECUTING`, `NOOP`, `STOPPED`, `FAILED`, and `UNKNOWN`. Applications can use custom codes to express business outcomes such as `COMPLETED_WITH_SKIPS` or `EMPTY_INPUT`.

For example, a step may have:

```text
BatchStatus:    COMPLETED
ExitStatus code: COMPLETED_WITH_SKIPS
Exit description: Skipped 12 invalid rows
```

Meaning: the step finished its lifecycle, while the business outcome indicates 12 items were skipped. The custom exit code can be used to drive flow routing; the description helps humans understand further details.

## 3. A Message Is Not a BatchStatus

A message like `statusMessage = "Import finished"` is just text. It does not update `StepExecution` or `JobExecution`, does not govern transactions, and does not change lifecycle status.

Practices that cause confusion:

- Writing “SUCCESS” into a message and treating the job as completed.
- Logging “FAILED” while `BatchStatus` remains `COMPLETED`.
- Parsing `exitDescription` text to decide the next step.
- Packing variable details into status strings and parsing them back in the job flow or monitoring.

Messages can be reworded, translated, appended to, or truncated. Using free-form text for system control couples logic to phrasing and easily breaks when wording changes.

## 4. Three Layers of Information to Separate

When observing an execution, keep these separate:

| Information | Represented By | Used For |
|---|---|---|
| Execution lifecycle | `BatchStatus` | Knowing whether job/step is running, completed, failed, or stopped |
| Routing outcome | `ExitStatus.exitCode` | Selecting transitions or classifying step results |
| Human explanation | `ExitStatus.exitDescription`, logs, or business messages | Providing details, causes, and counts |

Example:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED_WITH_SKIPS
Description = "Skipped 12 of 10,000 input records"
```

Do not merge these three pieces into a single string such as `COMPLETED_WITH_SKIPS:12`. Keep exit codes stable, store numbers in appropriate counters/metadata, and use messages for explanation.

## 5. Reading BatchStatus from JobExecution and StepExecution

You can obtain lifecycle status directly from execution objects:

```java
BatchStatus jobStatus = jobExecution.getStatus();
BatchStatus stepStatus = stepExecution.getStatus();

if (stepStatus == BatchStatus.FAILED) {
    log.error("Step {} failed", stepExecution.getStepName());
} else if (stepStatus == BatchStatus.COMPLETED) {
    log.info("Step {} completed", stepExecution.getStepName());
}
```

When checking status, use the enum instead of comparing messages:

```java
if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
    // Job lifecycle completed normally
}
```

Do not write:

```java
// Bad: depends on exact wording inside a message
if ("Job completed successfully".equals(statusMessage)) {
    // Treat job as completed
}
```

Messages can change without changing execution status. Enums allow the compiler and APIs to express intent clearly.

## 6. Reading ExitStatus Code and Description Separately

When you need the business outcome or transition code, access `ExitStatus` and read the right property:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();

String exitCode = exitStatus.getExitCode();
String description = exitStatus.getExitDescription();

log.info(
    "Step {} ended with exitCode={} description={}",
    stepExecution.getStepName(),
    exitCode,
    description
);
```

`exitCode` is the part usable for flow control. `exitDescription` is the descriptive text. Do not use `getExitDescription()` to infer an outcome code by searching for keywords like “success”, “warning”, or “failed”.

## 7. Job Flows Use Exit Code, Not Messages

Transitions in a job flow are selected based on a step's exit status code, not on a `BatchStatus` message or `exitDescription`.

For instance, if a step finishes with skipped items, it can return a custom exit code to route to a review step:

```java
return new JobBuilder("importJob", jobRepository)
    .start(importStep)
        .on("COMPLETED_WITH_SKIPS").to(reviewRejectsStep)
    .from(importStep)
        .on("COMPLETED").to(publishStep)
    .from(importStep)
        .on("FAILED").fail()
    .end()
    .build();
```

Here, the pattern in `.on(...)` matches the exit code. A descriptive string like “Skipped 12 invalid rows” is not used to select transitions.

When declaring conditional flows, define a small, stable, meaningful set of exit codes. Always include a fallback transition for unexpected outcomes so the job never accidentally enters a success path.

## 8. Creating Custom ExitStatus Without Altering BatchStatus

You can use `StepExecutionListener.afterStep` to return a custom exit status based on step outcomes. For example, a step finishes with skips:

```java
public class SkipOutcomeListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {

            return new ExitStatus("COMPLETED_WITH_SKIPS")
                .addExitDescription(
                    "Skipped " + stepExecution.getSkipCount() + " items");
        }

        return null;
    }
}
```

The listener only changes the exit outcome. `BatchStatus` remains managed by the step's lifecycle. This example only attaches `COMPLETED_WITH_SKIPS` when the step genuinely `COMPLETED`; if the step `FAILED`, the listener must not turn it into a success outcome.

When multiple listeners modify `ExitStatus`, the final result is combined according to Spring Batch's rules. Verify the final exit code in integration tests, especially if other listeners also return custom statuses.

## 9. Do Not Use exitDescription as a Machine-Readable Protocol

`exitDescription` is useful for adding details such as exception summaries, warnings, record counts, or operational context. However, descriptive text is not a stable protocol.

Avoid:

```java
if (stepExecution.getExitStatus()
        .getExitDescription()
        .contains("12 skipped")) {
    // Route based on message string
}
```

Instead, use a stable exit code and store metrics in the proper place:

```java
if ("COMPLETED_WITH_SKIPS".equals(
        stepExecution.getExitStatus().getExitCode())) {
    // Handle according to defined outcome code
}

long skipped = stepExecution.getSkipCount();
```

If additional structured data is needed, use `ExecutionContext`, execution counters, business tables, or a dedicated event schema. Do not stuff JSON or custom delimited strings into messages and parse them back if that data is part of a system contract.

## 10. BatchStatus and ExitStatus Can Differ

`BatchStatus` and `ExitStatus` are related, not two names for the same thing. A step can complete its lifecycle while carrying a custom business exit code.

| BatchStatus | ExitStatus code | Interpretation |
|---|---|---|
| `COMPLETED` | `COMPLETED` | Normal completion |
| `COMPLETED` | `COMPLETED_WITH_SKIPS` | Completed with skipped items |
| `COMPLETED` | `EMPTY_INPUT` | Valid completion with empty source |
| `FAILED` | `FAILED` | Step failed |
| `STOPPED` | `STOPPED` | Step stopped |

Custom codes must be designed consistently. Never produce an exit code that misrepresents the lifecycle, such as letting a step `FAILED` yet returning exit code `COMPLETED` just to continue along a success branch.

## 11. BatchStatus Is Managed by the Framework

In business code, never arbitrarily assign `BatchStatus` to make a job appear completed or failed. The framework manages execution lifecycles through `JobExecution`, `StepExecution`, step implementations, exception handling, stop requests, and repository updates.

For example, do not do this inside a processor or writer:

```java
// Bad: mutating lifecycle status from item processing logic
stepExecution.setStatus(BatchStatus.COMPLETED);
```

Manually modifying status while a step is still running can put metadata out of sync with transactions, exit status, counters, and actual state. If you want to drive flow routing based on business results, return a custom `ExitStatus` from a listener or use `JobExecutionDecider`.

If you need to request stopping a job, use Spring Batch's stop/abandon/restart mechanisms and let the framework complete the lifecycle. Never represent a stop request by writing a “STOPPED” message.

## 12. Persisting Metadata in JobRepository

In Spring Batch's standard JDBC schema, job and step metadata store status, exit code, and exit message/description in separate columns.

| Metadata | Typical Field | Content |
|---|---|---|
| Job execution | `STATUS` | `BatchStatus` lifecycle value |
| Job execution | `EXIT_CODE` | Job exit code |
| Job execution | `EXIT_MESSAGE` | Outcome or error description |
| Step execution | `STATUS` | `BatchStatus` lifecycle value |
| Step execution | `EXIT_CODE` | Step exit code |
| Step execution | `EXIT_MESSAGE` | Outcome or error description |

Separating columns lets the framework and operational tools read the exact type of information they need. Never write message strings into the status field or manually update metadata tables to force an execution into another state.

When querying metadata for monitoring, use `STATUS` for lifecycle state, `EXIT_CODE` for outcome classification, and `EXIT_MESSAGE` for details. Avoid writing queries that search for keywords in `EXIT_MESSAGE` to determine whether a job succeeded or failed.

## 13. BatchStatus Does Not Replace Business Exit Codes

Sometimes `BatchStatus.COMPLETED` is not enough to express business outcomes. For instance, a step finished running but the source had no data, or some items were skipped per policy.

Never invent custom `BatchStatus` values like `COMPLETED_WITH_WARNINGS` or `EMPTY`. `BatchStatus` is a standard framework lifecycle enum. Use a custom `ExitStatus` for those outcomes.

Example exit codes you can use:

- `COMPLETED`: normal completion.
- `COMPLETED_WITH_SKIPS`: completed with skipped items.
- `EMPTY_INPUT`: valid source with zero items.
- `REJECTED_INPUT`: input did not satisfy business policy.
- `FAILED`: step/job failed.

Choose codes based on routing or reporting needs. If an outcome only needs human explanation and does not affect flow routing, keep the standard exit code and add an exit description.

## 14. JobExecution and StepExecution Have Distinct Statuses

A job consists of multiple steps, so one step's status does not necessarily match the job's final status at every moment.

Example:

```text
JobExecution: STARTED
  validateInputStep: COMPLETED
  importRecordsStep: STARTED
  archiveInputStep: not run yet
```

While `importRecordsStep` is running, the job can remain in `STARTED`. After steps finish, the framework updates `JobExecution` status based on the overall job outcome. Never use a single step's message to conclude the job has finished.

When diagnosing, examine both job-level and step-level metadata. A job can be `FAILED` while some steps are `COMPLETED`; that does not mean metadata is corrupted. It reflects that part of the workflow finished before another step failed.

## 15. Using Status Properly in APIs and Monitoring

When building REST APIs, dashboards, or alerts, return separate fields instead of one generic status string.

Example structured response:

```json
{
  "jobName": "dailyImportJob",
  "jobExecutionId": 8452,
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED_WITH_SKIPS",
  "exitDescription": "Skipped 12 invalid rows",
  "readCount": 10000,
  "writeCount": 9988,
  "skipCount": 12
}
```

With this structure:

- UI uses `batchStatus` to show lifecycle state.
- Routing rules or business classification use `exitCode`.
- Operators read `exitDescription` for details.
- Read/write/skip numbers come from execution counters.

Never use `exitDescription` as a substitute for counters because messages can be modified or truncated. Never use `exitCode` in place of `BatchStatus` because custom exit codes may not reflect lifecycle state.

## 16. Handling Error Messages Properly

When a step fails, exceptions and error details can be recorded in exit description or logs. Messages should be concise, helpful, and free of sensitive data.

Guidelines:

- Keep the original exception in logs/stack traces for investigation.
- Use stable exit codes to classify errors.
- Use descriptions to provide human-readable context.
- Never include passwords, tokens, connection strings, or full sensitive payloads.
- Never rely on message content to retry, skip, or transition flows.
- Avoid overly long messages that make metadata hard to read or hit schema column limits.

Example suitable description: `Partner API timed out after 3 attempts`. Exit code can be `FAILED` or a dedicated error classification code per design; `BatchStatus` remains updated by the framework based on execution results.

## 17. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Writing “SUCCESS” in a message and assuming job completed | Lifecycle metadata may still be `STARTED` or `FAILED` | Read `JobExecution.getStatus()` |
| Parsing `exitDescription` to pick transitions | Flow depends on wording and breaks on message edits | Use `ExitStatus.exitCode` |
| Using custom `BatchStatus` for business outcomes | Incompatible with framework lifecycle enum | Use custom `ExitStatus` codes |
| Setting `BatchStatus.COMPLETED` manually in processor/writer | Lifecycle and actual results diverge | Let the framework manage status |
| Treating a custom exit code as BatchStatus | Monitoring misclassifies state | Store batchStatus and exitCode separately |
| Embedding error counts in messages and parsing them | Fragile data and hard to query | Use skip/read/write counters |
| Using one message for both UI and flow control | UI wording changes break logic | Separate lifecycle, exit code, and description |
| Returning a success exit code when step FAILED | Flow may enter an unintended business branch | Only emit exit codes matching actual state |

## 18. Testing BatchStatus and ExitStatus

Integration tests should verify lifecycle, exit code, and description separately.

Cases to check:

1. Step succeeds: `BatchStatus.COMPLETED` and expected standard or custom exit code.
2. Step throws unhandled exception: `BatchStatus.FAILED` and diagnosable failure details.
3. Step has skips: lifecycle completes if policy allows, exit code reflects skipped outcome if the flow needs to distinguish it.
4. Step stops: lifecycle status is `STOPPED`, not inferred from a message.
5. Custom exit code: transition matches code, independent of exit description.
6. Message text changed: flow and monitoring still work because they do not parse wording.
7. Multi-step job: job-level status is verified separately from individual step statuses.

Example assertions:

```java
assertThat(stepExecution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

assertThat(stepExecution.getExitStatus().getExitCode())
    .isEqualTo("COMPLETED_WITH_SKIPS");

assertThat(stepExecution.getExitStatus().getExitDescription())
    .contains("Skipped");
```

These assertions check three distinct dimensions: lifecycle, outcome code, and description. Never assert only a message and conclude the entire step completed properly.

## 19. Workflow for Designing Job Status

When designing a job or dashboard, determine:

1. Which lifecycle states of the job and steps need tracking? Use `BatchStatus`.
2. Which business outcomes must the flow distinguish? Define stable exit codes in `ExitStatus`.
3. What details do operators need? Record `exitDescription`, logs, or structured events.
4. Are quantitative metrics like read/write/skip counts needed? Use execution counters.
5. Is outcome-based routing needed? Use transitions matching `ExitStatus.exitCode` or `JobExecutionDecider`.
6. Are you parsing messages or manually setting BatchStatus anywhere? Remove those dependencies.
7. Test job status, step status, exit code, and messages separately.

## Conclusion

Do not use messages or free-form status strings instead of `BatchStatus`. `BatchStatus` represents the execution lifecycle of a job/step; `ExitStatus.exitCode` represents the exit outcome and can drive job flows; `ExitStatus.exitDescription` only adds human-readable context.

Read lifecycle state with `JobExecution.getStatus()` or `StepExecution.getStatus()`, route flows using stable exit codes, and use descriptions/logs/counters for details. Let Spring Batch manage `BatchStatus`, never parse messages to infer success/failure, and never place custom business statuses into the lifecycle enum.
