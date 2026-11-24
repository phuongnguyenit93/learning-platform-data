# JobExecutionDecider and decision status

In Spring Batch, `JobExecutionDecider` allows a Job flow to pick the next branch based on a condition at runtime. The decider receives `JobExecution` and `StepExecution` (if present), then returns a `FlowExecutionStatus` so the Job flow can match it and transition to the appropriate Step.

A decider is useful when orchestration depends on `JobParameters`, data produced by an earlier Step, state stored in `ExecutionContext`, or a business condition checked at runtime. For example, a Job can choose between full import and incremental import, route to a review branch when records require inspection, or finish normally when there is no data.

The key point is that a decider decides **where the flow goes next**. It is not a Step, and the status it returns is `FlowExecutionStatus`, which differs from a Step's `BatchStatus` and `ExitStatus`.

## 1. What is JobExecutionDecider?

`JobExecutionDecider` is a Spring Batch interface for decision logic inside a Job flow. Its primary method has the form:

```java
public interface JobExecutionDecider {
    FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) throws Exception;
}
```

The decider receives two objects:

- `JobExecution`: represents the current Job execution. You can read `JobParameters`, Job-level `ExecutionContext`, and metadata related to the run.
- `StepExecution`: represents the most recent Step before the decider in the flow, if the decider is invoked after a Step. It can be `null` when the decider is at the beginning of the flow and no Step has run yet.

The return value is a `FlowExecutionStatus`. The Job flow uses this status name to pick a transition declared with `.on(...)`.

A decider does not create its own `StepExecution`, does not read/write items like a chunk Step, and has no `BatchStatus` of its own. It is an orchestration state within the flow.

## 2. FlowExecutionStatus as the decision status

`FlowExecutionStatus` represents the state of the flow at the decider's position. Spring Batch has standard statuses such as `COMPLETED`, `FAILED`, `STOPPED`, `UNKNOWN`; applications can also return custom names like `FULL_IMPORT`, `DELTA_IMPORT`, `NO_DATA`, or `NEEDS_REVIEW`.

Example:

```java
return new FlowExecutionStatus("FULL_IMPORT");
```

The flow builder looks for a transition whose pattern matches `FULL_IMPORT`:

```java
.from(importModeDecider)
    .on("FULL_IMPORT").to(fullImportStep)
```

The status name returned by the decider must match a declared pattern. If the decider returns `FULL_IMPORT` while the Job only declares `DELTA_IMPORT` and `NO_DATA`, the flow has no matching branch. Explicitly define all statuses that can arise and include a fallback transition.

## 3. Distinguishing FlowExecutionStatus, ExitStatus, and BatchStatus

These three status types serve different purposes:

| Status type | Belongs to | Purpose |
|---|---|---|
| `BatchStatus` | `JobExecution` or `StepExecution` | Describes the execution lifecycle, e.g., `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |
| `ExitStatus` | `StepExecution` | Describes the exit outcome of a Step; its exit code is typically used for transitions originating from a Step |
| `FlowExecutionStatus` | Flow/decider state | Describes the decision outcome at the decider position to choose the next branch |

For example, a Step may end with `BatchStatus.COMPLETED` and `ExitStatus.COMPLETED_WITH_SKIPS`. The Job flow can use that `ExitStatus` to decide whether to run a review Step. After that Step, another decider might return `FlowExecutionStatus("SEND_NOTIFICATION")` to pick a notification branch.

Do not use `ExitStatus` as the return type of `JobExecutionDecider`. The `decide()` method must return `FlowExecutionStatus`.

## 4. Implementing a decider based on JobParameters

A straightforward case is selecting a flow based on an input parameter. For instance, an order import Job supports `FULL` and `DELTA` modes:

```java
public class ImportModeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        String mode = jobExecution.getJobParameters().getString("mode");

        if ("FULL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("FULL_IMPORT");
        }

        if ("DELTA".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("DELTA_IMPORT");
        }

        return new FlowExecutionStatus("INVALID_MODE");
    }
}
```

The decider simply reads the parameter and returns a status. It does not need to store `mode` in a mutable field, because `JobParameters` is already attached to the current `JobExecution`.

Registering the decider as a bean:

```java
@Bean
public JobExecutionDecider importModeDecider() {
    return new ImportModeDecider();
}
```

When building `JobParameters`, the application should validate and normalize `mode` before launching. Returning `INVALID_MODE` allows the flow to handle invalid input on an explicit branch, though critical validation should still occur early at the launch layer or via `JobParametersValidator`.

## 5. Placing a decider between Steps

A common usage is running a data-preparation Step first, then using a decider to choose the next Step:

```text
prepareInputStep
       |
       v
ImportModeDecider
       |
       +-- FULL_IMPORT  --> fullImportStep
       |
       +-- DELTA_IMPORT --> deltaImportStep
       |
       +-- INVALID_MODE --> invalidModeStep / fail
```

Declaring the Job flow in Java:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Step fullImportStep,
        Step deltaImportStep,
        Step invalidModeStep,
        JobExecutionDecider importModeDecider) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(prepareInputStep)
            .next(importModeDecider)
                .on("FULL_IMPORT").to(fullImportStep)
            .from(importModeDecider)
                .on("DELTA_IMPORT").to(deltaImportStep)
            .from(importModeDecider)
                .on("INVALID_MODE").to(invalidModeStep)
            .from(importModeDecider)
                .on("*").fail()
            .end()
            .build();
}
```

`.next(importModeDecider)` places the decider after `prepareInputStep`. `.from(importModeDecider)` declares the branches originating from the decider. `.on(...)` matches the `FlowExecutionStatus` returned by the decider, and `.to(...)` transitions to the selected Step.

In a production flow, declare subsequent transitions from the target Steps if they are not terminal states. For example, after `fullImportStep` and `deltaImportStep`, the Job might route to a summary reporting Step or terminate via appropriate transitions.

## 6. Placing a decider at the start of a Job flow

A decider can also be the very first state of a Job, before any Step runs:

```java
@Bean
public Job initialDecisionJob(
        JobRepository jobRepository,
        JobExecutionDecider initialDecider,
        Step fullStep,
        Step deltaStep) {

    return new JobBuilder("initialDecisionJob", jobRepository)
            .start(initialDecider)
                .on("FULL").to(fullStep)
            .from(initialDecider)
                .on("DELTA").to(deltaStep)
            .from(initialDecider)
                .on("*").fail()
            .end()
            .build();
}
```

In this case, the `stepExecution` argument passed to `decide()` can be `null`, since no Step has executed yet. If a decider can be used at the start of a flow, check for null before accessing it:

```java
@Override
public FlowExecutionStatus decide(
        JobExecution jobExecution,
        StepExecution stepExecution) {

    if (stepExecution == null) {
        // Decision is based only on JobParameters or JobExecutionContext.
        return new FlowExecutionStatus("INITIAL_RUN");
    }

    return new FlowExecutionStatus("AFTER_STEP");
}
```

Never assume `stepExecution` is always non-null. This is crucial when reusing the same decider across multiple positions in a flow.

## 7. Reading results of the previous Step

When a decider follows a Step, it can use the passed-in `StepExecution` to read results and metadata from the Step that just ran.

For example, after a data-validation Step, the decider chooses a branch based on skipped item count:

```java
public class ReviewRequiredDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution == null) {
            return new FlowExecutionStatus("NO_PREVIOUS_STEP");
        }

        if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
            return new FlowExecutionStatus("STEP_NOT_COMPLETED");
        }

        if (stepExecution.getSkipCount() > 0) {
            return new FlowExecutionStatus("NEEDS_REVIEW");
        }

        return new FlowExecutionStatus("CONTINUE");
    }
}
```

The flow can route to the review Step when needed:

```java
.start(validateOrdersStep)
.next(reviewRequiredDecider)
    .on("NEEDS_REVIEW").to(reviewSkippedOrdersStep)
.from(reviewRequiredDecider)
    .on("CONTINUE").to(importOrdersStep)
.from(reviewRequiredDecider)
    .on("*").fail()
```

Here, the decider only reads counters from the previous Step. It does not modify that Step's `BatchStatus` or `ExitStatus`.

If you want to route solely based on a Step outcome already captured in `ExitStatus`, you can use a direct conditional transition on `ExitStatus`. A decider fits when combining multiple pieces of data or computing a distinct decision at the flow level.

## 8. Reading JobExecutionContext and StepExecutionContext

A decider can read data from Job-level `ExecutionContext`:

```java
String sourceSystem = jobExecution.getExecutionContext()
        .getString("sourceSystem", "UNKNOWN");
```

If invoked after a Step, the decider can also read Step-level `ExecutionContext`:

```java
if (stepExecution != null) {
    String validationResult = stepExecution.getExecutionContext()
            .getString("validationResult", "NOT_AVAILABLE");
}
```

This is useful when an earlier Step computes a complex value and stores the result for the decider. For example, a file-analysis Step can save `inputCategory=LEGACY`; the decider reads that key and chooses the matching converter.

Store only small values needed for orchestration. Do not place large business payloads in `ExecutionContext`. Also understand when contexts are persisted by `JobRepository`; modifying an in-memory object does not mean metadata has been durably written immediately.

## 9. Decision statuses should follow a clear convention

Statuses returned by a decider form a contract between the decider and the Job flow. If the code returns one string while the flow matches another, the branch will not be selected as expected.

You can define constants:

```java
public final class ImportFlowStatuses {
    public static final String FULL_IMPORT = "FULL_IMPORT";
    public static final String DELTA_IMPORT = "DELTA_IMPORT";
    public static final String NO_DATA = "NO_DATA";
    public static final String NEEDS_REVIEW = "NEEDS_REVIEW";
    public static final String INVALID_INPUT = "INVALID_INPUT";

    private ImportFlowStatuses() {
    }
}
```

Then use the same constants in the decider and flow builder:

```java
return new FlowExecutionStatus(ImportFlowStatuses.NEEDS_REVIEW);
```

```java
.from(reviewDecider)
    .on(ImportFlowStatuses.NEEDS_REVIEW).to(reviewStep)
```

Status names should describe the business decision or branch; avoid vague strings like `1`, `2`, `OK`, or `OTHER`. When renaming a status, update all dependent transitions.

## 10. Wildcards and fallback branches

The flow should handle every status a decider can return. A wildcard branch can act as a fallback:

```java
.from(importModeDecider)
    .on("FULL_IMPORT").to(fullImportStep)
.from(importModeDecider)
    .on("DELTA_IMPORT").to(deltaImportStep)
.from(importModeDecider)
    .on("NO_DATA").end()
.from(importModeDecider)
    .on("*").fail()
```

Specific patterns clearly express expected outcomes; the final wildcard handles unanticipated statuses. Without a matching transition, the Job flow may fail with a missing-transition error instead of following a safe default branch.

Do not use a wildcard to silently send all unfamiliar statuses onto a success branch. For unrecognized statuses, `.fail()` is usually safer because it forces the system to record an orchestration error and prompt investigation.

## 11. Distinguishing JobExecutionDecider from StepExecutionListener

Both mechanisms can influence a Job flow, but their roles differ:

| Criterion | `StepExecutionListener` | `JobExecutionDecider` |
|---|---|---|
| Belongs to | A Step | A position in the Job flow |
| Callbacks | `beforeStep()` and `afterStep()` | `decide()` |
| Input | `StepExecution` | `JobExecution` and optionally `StepExecution` |
| Result | Can return `ExitStatus` from `afterStep()` | Returns `FlowExecutionStatus` |
| Role | Observes lifecycle and classifies Step outcome | Picks flow branch based on runtime conditions |
| Own `StepExecution`? | Invoked within the current `StepExecution` lifecycle | Does not create its own `StepExecution` |

If a condition depends only on a single Step's outcome, a listener can return a custom `ExitStatus` and transitions can match on `ExitStatus`. If a decision is needed at a standalone flow point combining `JobParameters`, `JobExecutionContext`, or prior Step metadata, a decider usually expresses it more cleanly.

## 12. Distinguishing JobExecutionDecider from direct conditional transitions

Direct conditional transitions use `.on(...)` to check the `ExitStatus` of the Step that just completed. `JobExecutionDecider` is a dedicated flow state invoked to compute and return a `FlowExecutionStatus`.

Example using a direct transition:

```java
.start(validateStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(validateStep)
    .on("COMPLETED").to(importStep)
```

Example using a decider:

```java
.start(validateStep)
.next(reviewRequiredDecider)
    .on("NEEDS_REVIEW").to(reviewStep)
.from(reviewRequiredDecider)
    .on("CONTINUE").to(importStep)
```

Direct transitions fit when the Step already knows the outcome and publishes it via `ExitStatus`. A decider fits when you want dedicated decision logic in the flow or need to inspect multiple sources to pick a branch.

Do not add a decider when a simple transition already expresses the requirement. Keeping flows easy to read helps operators see why a Job took a specific branch.

## 13. Restart and determinism of decisions

A Job can be restarted after a branch has partially executed. As the flow resumes, the decider may be called again depending on execution position and Job metadata. Therefore, decision logic should be deterministic for the same unit of business work.

A safe decider typically:

- Relies on identifying `JobParameters` or durably persisted data.
- Reads results from Job/Step `ExecutionContext` or a repository consistently.
- Returns the same status when business inputs are unchanged.
- Performs no side effects such as creating transactions, sending emails, or publishing messages.
- Does not rely on mutable fields in a singleton bean to remember prior calls.

Example of what not to do:

```java
public class UnsafeDecider implements JobExecutionDecider {

    private boolean firstCall = true;

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (firstCall) {
            firstCall = false;
            return new FlowExecutionStatus("FIRST_BRANCH");
        }

        return new FlowExecutionStatus("SECOND_BRANCH");
    }
}
```

Here the outcome depends on in-memory call history. When the application restarts, the decider instance can be recreated with `firstCall` back to `true`; when multiple Jobs run concurrently, executions can interfere with each other.

If a decision must stay fixed across restarts, durably persist the decision or its source inputs and read them back. Never use decider instance fields as checkpoints.

## 14. Do not place non-repeatable side effects in decide()

`decide()` is for computing the orchestration status. It can be invoked again during restarts or flow re-executions. If every call to the decider inserts a new record, sends an email, or calls a transaction-creating API, the system can duplicate side effects.

Inappropriate example:

```java
@Override
public FlowExecutionStatus decide(
        JobExecution jobExecution,
        StepExecution stepExecution) {

    notificationService.send("Import is starting");
    return new FlowExecutionStatus("CONTINUE");
}
```

Instead, let the decider only choose the branch:

```java
@Override
public FlowExecutionStatus decide(
        JobExecution jobExecution,
        StepExecution stepExecution) {

    boolean needsNotification = readNotificationRequirement(jobExecution);
    return new FlowExecutionStatus(
            needsNotification ? "SEND_NOTIFICATION" : "CONTINUE"
    );
}
```

Then, if a notification needs to be sent, transition to a dedicated Step with explicit transaction, retry, and idempotency design. This separates orchestration decisions from business actions.

## 15. Testing a decider

A decider is typically a small component that can be unit tested directly using sample `JobExecution` and `StepExecution` instances.

Cases that should be tested:

- Each valid `JobParameters` value returns the expected `FlowExecutionStatus`.
- Missing or invalid values return the proper error/fallback status.
- `stepExecution == null` is handled if the decider can stand at the start of a flow.
- Preceding Step `FAILED`, `COMPLETED`, or with skips leads to the right decision.
- The same set of parameters and metadata yields a deterministic result.
- The decider creates no side effects when invoked multiple times.

Simple test example:

```java
@Test
void selectsFullImportForFullMode() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("mode", "FULL")
            .toJobParameters();

    JobExecution jobExecution = new JobExecution(1L, parameters);
    ImportModeDecider decider = new ImportModeDecider();

    FlowExecutionStatus result = decider.decide(jobExecution, null);

    assertEquals("FULL_IMPORT", result.getName());
}
```

Beyond unit tests, write integration tests for the Job flow to confirm each `FlowExecutionStatus` actually routes to the right Step or terminal state. Testing the decider alone does not prove the flow builder declared all transitions properly.

## 16. Common misconceptions

**Thinking a decider is a Step.** A decider is a flow state; it has no `StepExecution`, reader, processor, or writer of its own.

**Returning ExitStatus from `decide()`.** The method must return `FlowExecutionStatus`. `ExitStatus` belongs to `StepExecution`.

**Assuming StepExecution is always non-null.** When a decider stands at the start of a Job flow, no Step has run yet so this argument can be null.

**Using BatchStatus as a decision status name.** A decider returns `FlowExecutionStatus`. You may use standard names like `COMPLETED`, but that is a flow status name—not the decider changing the `BatchStatus` of a Job or Step.

**Omitting branches for custom statuses.** If the flow lacks a matching transition, the Job does not know where to go. List all possible return statuses and add a fallback.

**Holding decision state in mutable fields.** Fields can be lost on restart or shared across concurrent `JobExecution`s. Rely on parameters and durable data.

**Performing side effects inside `decide()`.** A decider may be re-invoked. Move side effects to a dedicated Step and protect them with idempotency.

## 17. How to design a JobExecutionDecider

Start by identifying the business branches and naming a `FlowExecutionStatus` for each branch. Write the decider accepting `JobExecution` and `StepExecution`, guard against null if it can stand at the start of a flow, read input data or prior Step outcomes, and return a single status. Declare specific transitions for each status and a safe fallback branch.

Keep `decide()` focused on computing the decision, without performing side effects. If the decision must stay consistent across restarts, rely on `JobParameters` or durably persisted metadata rather than in-memory fields. When `FlowExecutionStatus`, `ExitStatus`, and `BatchStatus` are clearly distinguished, `JobExecutionDecider` enables Job flows to handle business branching flexibly while remaining easy to control.
