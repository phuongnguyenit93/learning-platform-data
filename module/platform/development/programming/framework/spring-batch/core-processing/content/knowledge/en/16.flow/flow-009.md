# Deciders for choosing the next step

In Spring Batch, `JobExecutionDecider` allows a Job to select the next Step or processing branch based on data from the current run. Instead of always following a fixed sequence of Steps, a Job can branch based on `JobParameters`, the outcome of a preceding Step, or a computed business condition.

For example, a data import Job can choose one of three paths: import all data, import only changes, or finish early when there is no data to process. The `Decider` produces the decision outcome; the Job's flow maps that outcome to the next Step.

## 1. What is JobExecutionDecider?

`JobExecutionDecider` is an interface used to decide the flow status at a given point in a Job. The interface defines a single method:

```java
public interface JobExecutionDecider {
    FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution);
}
```

The `decide()` method receives two objects:

- `JobExecution`: details of the current Job run, including `JobParameters`, Job `ExecutionContext`, and execution state.
- `StepExecution`: details of the Step execution immediately before the decision point, if any. This value can be `null` when the Decider is invoked at a position with no preceding `StepExecution`.

The Decider returns a `FlowExecutionStatus`. The flow uses this status to select a declared transition, moving to a Step, ending, failing, or stopping the Job.

A Decider does not read and process individual items like an `ItemProcessor`; nor is it a Step. It is a flow-control point placed between Steps or at the start of a flow.

## 2. What is FlowExecutionStatus used for?

`FlowExecutionStatus` represents an outcome at the flow level. Spring Batch has several common values:

| Value | General meaning |
|---|---|
| `COMPLETED` | Flow completed normally. |
| `FAILED` | Flow failed. |
| `STOPPED` | Flow was stopped. |
| `UNKNOWN` | Flow outcome could not be determined. |

A Decider can also return a custom status by creating a new `FlowExecutionStatus`:

```java
return new FlowExecutionStatus("FULL_IMPORT");
```

Custom status names should be short, meaningful, and stable because they are used in the Job's transition configuration—for example, `FULL_IMPORT`, `INCREMENTAL_IMPORT`, or `NO_DATA`.

### Distinguishing FlowExecutionStatus, ExitStatus, and BatchStatus

These three concepts often appear together but serve different purposes:

| Concept | Belongs to | Role |
|---|---|---|
| `BatchStatus` | `JobExecution` or `StepExecution` | Execution lifecycle status such as `COMPLETED`, `FAILED`, `STOPPED`. |
| `ExitStatus` | `JobExecution` or `StepExecution` | Exit outcome code; can contain custom business codes. |
| `FlowExecutionStatus` | Flow and Decider outcomes | Status used to select the next transition in the flow. |

For example, a Step may end with an `ExitStatus` of `NO_DATA`, after which a Decider reads the needed information and returns `FlowExecutionStatus("SKIP_IMPORT")`. The flow can use `SKIP_IMPORT` to go directly to a summary Step. Do not assume a Step's `ExitStatus` code is automatically the Decider's `FlowExecutionStatus`.

## 3. Simple example: choosing data import mode

Suppose `customerImportJob` supports two modes:

- `FULL`: re-import all customer data.
- `INCREMENTAL`: import only changes since the previous sync.

The mode is passed via a JobParameter named `importMode`. The Decider reads the parameter and returns the corresponding status:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.flow.FlowExecutionStatus;
import org.springframework.batch.core.job.flow.JobExecutionDecider;
import org.springframework.stereotype.Component;

@Component
public class ImportModeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        String mode = jobExecution.getJobParameters()
                .getString("importMode", "INCREMENTAL");

        if ("FULL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("FULL_IMPORT");
        }

        if ("INCREMENTAL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("INCREMENTAL_IMPORT");
        }

        return new FlowExecutionStatus("INVALID_MODE");
    }
}
```

The Decider does not invoke Steps directly. It simply returns a status so the Job flow decides which path to take. If the value is invalid, the Decider returns `INVALID_MODE`; the Job configuration must map this status to an explicit transition.

## 4. Declaring transitions in JobBuilder

From Spring Batch 5 onward, you can connect Steps and Deciders using `JobBuilder` with `start()`, `next()`, `from()`, and `on()`.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CustomerImportJobConfig {

    @Bean
    public Job customerImportJob(
            JobRepository jobRepository,
            Step validateInputStep,
            Step fullImportStep,
            Step incrementalImportStep,
            Step summaryStep,
            ImportModeDecider importModeDecider) {

        return new JobBuilder("customerImportJob", jobRepository)
                .start(validateInputStep)
                .next(importModeDecider)
                .from(importModeDecider).on("FULL_IMPORT").to(fullImportStep)
                .from(importModeDecider).on("INCREMENTAL_IMPORT").to(incrementalImportStep)
                .from(importModeDecider).on("INVALID_MODE").fail()
                .from(fullImportStep).on("*").to(summaryStep)
                .from(incrementalImportStep).on("*").to(summaryStep)
                .end()
                .build();
    }
}
```

The flow of the Job above can be visualized as follows:

```text
                 validateInputStep
                        |
                        v
                 ImportModeDecider
                  /      |       \
          FULL_IMPORT  INCREMENTAL  INVALID_MODE
               |          |             |
               v          v             v
          fullImport  incremental    Job FAILED
               |       ImportStep
               |          |
               +----+-----+
                    |
                    v
                summaryStep
                    |
                    v
                Job end
```

Meaning of the methods:

- `.start(validateInputStep)`: specifies the first Step.
- `.next(importModeDecider)`: invokes the Decider after the input-validation Step completes.
- `.from(importModeDecider).on("FULL_IMPORT").to(fullImportStep)`: if the Decider returns `FULL_IMPORT`, the flow moves to the full-import Step.
- `.from(importModeDecider).on("INCREMENTAL_IMPORT").to(incrementalImportStep)`: selects the incremental-import Step.
- `.from(importModeDecider).on("INVALID_MODE").fail()`: marks the flow as failed if the mode is invalid.
- Transitions from both import Steps to `summaryStep` merge both branches back into a single summary Step.
- `.end().build()`: finishes the Job flow definition.

`on()` patterns support pattern matching. You can use `*` as a fallback branch for any remaining statuses, though important cases should be declared explicitly to avoid an unexpected status being misrouted onto a success branch.

## 5. Deciding based on the previous Step's result

A Decider can use `StepExecution` to inspect the outcome of the Step that just ran. For instance, the file-validation Step stores the valid record count in `ExecutionContext`; the Decider reads that count to decide whether the import Step needs to run.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.flow.FlowExecutionStatus;
import org.springframework.batch.core.job.flow.JobExecutionDecider;

public class DataAvailabilityDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution == null) {
            return new FlowExecutionStatus("UNKNOWN_INPUT");
        }

        int validCount = stepExecution.getExecutionContext()
                .getInt("validRecordCount", 0);

        if (validCount > 0) {
            return new FlowExecutionStatus("HAS_DATA");
        }

        return new FlowExecutionStatus("NO_DATA");
    }
}
```

The previous Step can write the count into its Step ExecutionContext:

```java
int validCount = validateInputFile();
contribution.getStepExecution()
        .getExecutionContext()
        .putInt("validRecordCount", validCount);
return RepeatStatus.FINISHED;
```

If the Job needs this data at the Job level or multiple Steps need it, an appropriate value can be placed into the Job ExecutionContext via promotion or updated in the right place. Ensure the data has been persisted into metadata before relying on it on restart.

The flow can map the outcomes as follows:

```java
.start(validateInputStep)
.next(dataAvailabilityDecider)
.from(dataAvailabilityDecider).on("HAS_DATA").to(importStep)
.from(dataAvailabilityDecider).on("NO_DATA").to(summaryStep)
.from(dataAvailabilityDecider).on("UNKNOWN_INPUT").fail()
```

In this example, a file with zero valid records is not necessarily a technical failure. If business rules allow, the Job can skip the import Step and proceed to summary. Conversely, if there is no `StepExecution` or mandatory input data is missing, the flow can fail.

## 6. Using a Decider to end or stop a Job

Not every decision has to transition to another Step. Flow transitions can end the Job or mark it failed/stopped as required.

Example:

```java
.start(checkRequestStep)
.next(requestDecider)
.from(requestDecider).on("PROCESS").to(processRequestStep)
.from(requestDecider).on("ALREADY_DONE").end()
.from(requestDecider).on("INVALID").fail()
.end()
.build();
```

In the configuration above:

- `PROCESS`: proceed to process the request.
- `ALREADY_DONE`: end the flow normally without running the processing Step.
- `INVALID`: end the flow with a failed outcome.

`end()` and `fail()` are flow transition actions. Distinguish ending normally from marking a failure: `end()` finishes the flow normally, while `fail()` terminates the flow in an error state. If you need to stop the Job to wait for a restart or intervention, configure an appropriate stop transition rather than treating the situation as success.

A Job ending with `end()` can have `BatchStatus.COMPLETED` even when the business Step did not run. If you want to express a specific business outcome code such as `ALREADY_DONE`, configure an appropriate `ExitStatus` in the flow and check it at the Job level.

## 7. Deciders vs transitions on a Step's ExitStatus

Spring Batch can branch directly on a Step's `ExitStatus` without a Decider. When the condition is simply an outcome code already produced by the Step, direct transitions are usually shorter.

For example, if the input-validation Step returns `ExitStatus("NO_DATA")`, the flow can use:

```java
return new JobBuilder("importJob", jobRepository)
        .start(validateInputStep)
        .on("COMPLETED").to(importStep)
        .from(validateInputStep).on("NO_DATA").to(summaryStep)
        .from(validateInputStep).on("FAILED").fail()
        .end()
        .build();
```

When conditions must be computed from multiple sources, read `JobParameters`, combine the previous Step's state with business data, or apply custom decision logic, `JobExecutionDecider` centralizes that logic in one place.

| Requirement | Appropriate approach |
|---|---|
| Branch solely on an `ExitStatus` already returned by a Step | Direct transition with `.on(...)`. |
| Decide based on multiple `JobParameters` or metadata | `JobExecutionDecider`. |
| Decide based on data stored in `ExecutionContext` | `JobExecutionDecider`. |
| Condition needs queries or separate business calculation | Decider calling an appropriate service, keeping operations short and safe to repeat. |

Do not add a Decider for a simple condition already clearly expressed by a Step's `ExitStatus`. Conversely, avoid stuffing complex logic into transition chains when that logic needs independent unit testing.

## 8. Reading JobParameters and ExecutionContext safely

A Decider commonly uses `JobExecution` data to decide. When reading `JobParameters`, clarify which parameters are required vs optional and handle missing or malformed values.

Example:

```java
String mode = jobExecution.getJobParameters().getString("importMode");
if (mode == null || mode.isBlank()) {
    return new FlowExecutionStatus("INVALID_MODE");
}
```

If the Decider reads data from `StepExecution`, handle the `stepExecution == null` case before accessing its context. Do not assume every position in a flow has a preceding `StepExecution`.

`ExecutionContext` is stored at `JobExecution` or `StepExecution` scope. Pick the right scope:

- Step `ExecutionContext` is for checkpoints or outcomes private to one Step.
- Job `ExecutionContext` is for small data that needs to be shared across Steps within the same `JobExecution`.

Do not use `ExecutionContext` to store large business datasets. If the Decider needs to inspect a lot of data, store a key or summary info and query the appropriate data source.

## 9. Designing Deciders to be stable on restart

A Decider may be invoked again when a Job is restarted, depending on its position in the flow and Step statuses. Therefore, the decision result should be stable for the same unit of work, or the required state must be durably persisted.

Risk example: a Decider reads the current clock time to decide between full import and incremental import. If the first run picks `FULL_IMPORT`, fails mid-Job, and restarts the next day, the Decider could pick a different branch. That causes one `JobInstance` to continue down a different flow than its initial run.

Helpful principles:

1. Rely on identifying `JobParameters` or business data persisted for the `JobInstance` when deciding a branch that must remain stable.
2. If a decision is computed by a Step, store the result in `ExecutionContext` or a queryable status table.
3. Avoid depending on current wall-clock time, random values, or unrecorded external state.
4. If the Decider calls a service or database, prefer read operations; if there are side effects, design them to be idempotent.
5. When changing decision logic, evaluate the impact on in-flight `JobInstance`s undergoing restart.

A simple approach is computing the mode before launch, passing it as a JobParameter, and keeping that value unchanged on restart. If the mode changes, that may represent a different unit of work, requiring careful attention to identity and business workflow.

## 10. Unit testing JobExecutionDecider

A Decider is a plain Java component that can be tested directly without running the entire Job. Create a `JobExecution` with desired `JobParameters`, call `decide()`, and assert on `FlowExecutionStatus`.

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.job.flow.FlowExecutionStatus;

class ImportModeDeciderTest {

    private final ImportModeDecider decider = new ImportModeDecider();

    @Test
    void selectsFullImport() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("importMode", "FULL")
                .toJobParameters();
        JobExecution execution = new JobExecution(
                new JobInstance(1L, "customerImportJob"), parameters);

        FlowExecutionStatus status = decider.decide(execution, null);

        assertEquals("FULL_IMPORT", status.getName());
    }

    @Test
    void selectsIncrementalImport() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("importMode", "INCREMENTAL")
                .toJobParameters();
        JobExecution execution = new JobExecution(
                new JobInstance(2L, "customerImportJob"), parameters);

        FlowExecutionStatus status = decider.decide(execution, null);

        assertEquals("INCREMENTAL_IMPORT", status.getName());
    }
}
```

Unit tests should cover valid modes, invalid modes, missing parameters, and `StepExecution` being `null` if the Decider uses it. For complex decision logic, parameterized tests can check multiple input combinations.

## 11. Integration testing flows with Deciders

Unit tests verify the Decider's logic, but do not prove `JobBuilder` maps statuses to Steps properly. Integration tests should launch the Job with different `JobParameters` and verify which `StepExecution`s are created.

Illustrative example:

```java
JobParameters fullParameters = new JobParametersBuilder()
        .addString("importMode", "FULL")
        .addString("testRun", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution fullExecution = jobLauncherTestUtils.launchJob(fullParameters);

assertEquals(BatchStatus.COMPLETED, fullExecution.getStatus());
assertTrue(fullExecution.getStepExecutions().stream()
        .anyMatch(step -> step.getStepName().equals("fullImportStep")));
assertFalse(fullExecution.getStepExecutions().stream()
        .anyMatch(step -> step.getStepName().equals("incrementalImportStep")));
```

To run this test, the test context must register the Job with the Decider and corresponding Steps; `JobLauncherTestUtils` must be configured to point to the right Job. For each launch, use a unique identifying parameter such as `testRun` to avoid colliding with a `JobInstance` completed in a previous test. Similar tests can be written for `INCREMENTAL` and `INVALID_MODE`.

Integration tests should verify at least:

- Each status returned by the Decider leads to the right Step.
- Unselected branches have no `StepExecution`.
- Error statuses map to a failed flow if that is the desired policy.
- The Job ends with the expected `BatchStatus` and `ExitStatus`.
- On restart, the chosen branch matches `JobParameters` and persisted state.

## 12. Common mistakes when using Deciders

| Mistake | Cause | Fix |
|---|---|---|
| Returning a status without declaring a transition | Flow does not know where to go for that result. | Declare `.from(decider).on("STATUS").to(...)` or an appropriate terminal branch. |
| Confusing `FlowExecutionStatus` with `ExitStatus` | The two status types belong to different parts of the flow. | Use `FlowExecutionStatus` for Decider results; `ExitStatus` for Step/Job execution. |
| Declaring only the success branch | Unexpected statuses may lack explicit handling. | Add a fallback branch or fail branch for invalid cases. |
| Accessing `StepExecution` without null check | Decider may run at a point with no prior `StepExecution`. | Check for null before reading `StepExecution`. |
| Using current time or random values to choose a branch | Result may change upon restart. | Use stable `JobParameters` or persist the decision outcome. |
| Putting lengthy data processing in a Decider | No Step transaction/checkpoint covers that work. | Move processing into a Step; Decider only selects the path. |
| Using a Decider for a simple `ExitStatus` check | Flow config becomes unnecessarily complex. | Use a direct transition when the outcome is already on the Step. |
| Assuming an unexecuted branch gets a `StepExecution` | Unselected Steps normally do not create a `StepExecution` in that run. | Check actual `StepExecution`s instead of assuming all Steps appear. |

## Conclusion

`JobExecutionDecider` lets a Job pick the next step by returning a `FlowExecutionStatus`. A Decider can base its decision on `JobParameters`, `StepExecution`, or `ExecutionContext`; the Job flow maps that status to a Step, completion, or failure. Use direct transitions when branching simply on an existing `ExitStatus`, and use a Decider when dedicated decision logic is needed. To keep flows easy to operate, explicitly declare all major branches, handle invalid cases, keep decisions stable across restarts, and test both Decider logic and the integrated flow.
