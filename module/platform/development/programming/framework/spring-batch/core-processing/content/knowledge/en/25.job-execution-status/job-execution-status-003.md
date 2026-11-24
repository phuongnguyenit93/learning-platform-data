# Exit Codes for Schedulers

When running Spring Batch from a scheduler such as cron, Windows Task Scheduler, or an enterprise batch orchestration system, the scheduler usually needs to know whether a Job succeeded or failed. A common way is to read the process exit code of the Java program. Spring Batch represents a Job outcome with ExitStatus using a string code, whereas an operating system scheduler expects an integer. Therefore, the application needs a clear mapping step from the Job outcome to a process exit code.

Three concepts must be distinguished: BatchStatus describes the execution lifecycle state; ExitStatus describes the logical outcome of a Job or Step; process exit code is the integer the process returns to the operating system. Without proper mapping, a scheduler may mark a failed Job as successful, or vice versa, even though metadata in JobRepository records the correct status.

## 1. Three Types of Status to Distinguish

Spring Batch and the operating system use different data types to represent outcomes.

| Concept | Data Type | Purpose | Example |
|---|---|---|---|
| BatchStatus | Enum | Lifecycle state of JobExecution or StepExecution | STARTED, COMPLETED, FAILED, STOPPED |
| ExitStatus | Value object with String exit code | Logical outcome and termination description of Job/Step | COMPLETED, FAILED, COMPLETED_WITH_WARNINGS |
| Process exit code | Integer | Process outcome returned to OS or scheduler | 0, 1, 4, 10 |

BatchStatus answers whether the execution completed, failed, or was stopped. ExitStatus answers the stage's outcome according to application conventions and can be used in flow transitions. Process exit code is the contract between the program and the external scheduler.

For example, a Job might have:

~~~text
BatchStatus: COMPLETED
ExitStatus:  COMPLETED_WITH_WARNINGS
Process code: 4
~~~

This case means the Job completed in terms of lifecycle, but had business warnings, such as some items being skipped. The scheduler can be configured to treat code 4 as completed with warnings and perform notification or reconciliation steps.

These three values should not be treated as one and the same. A custom ExitStatus does not automatically change BatchStatus, and a string ExitStatus does not automatically become an integer process exit code.

## 2. ExitStatus of Job and Step

ExitStatus is the outcome of a Step or Job. It has two main parts:

- exit code: a string identifying the outcome.
- exit description: an additional description, typically used for diagnostic info.

Common values include COMPLETED, EXECUTING, FAILED, NOOP, STOPPED, and UNKNOWN. An application can create custom codes such as COMPLETED_WITH_WARNINGS or VALIDATION_FAILED if flows and schedulers need to distinguish those outcomes.

Example of creating a custom ExitStatus:

~~~java
ExitStatus warningStatus =
        new ExitStatus("COMPLETED_WITH_WARNINGS",
                "Completed with skipped records");
~~~

ExitStatus is not an operating system error code. The value COMPLETED_WITH_WARNINGS must be mapped to a separate integer before being returned to the scheduler.

A Step can return an ExitStatus in StepExecutionListener.afterStep. JobExecution also has a final ExitStatus, aggregated from Step results and adjustable by JobExecutionListener. When mapping for a scheduler, you should usually base it on the final outcome of JobExecution, since that represents the outcome of the entire Job.

## 3. BatchStatus and ExitStatus Can Differ

BatchStatus and ExitStatus are related but not identical.

| BatchStatus | ExitStatus | Interpretation |
|---|---|---|
| COMPLETED | COMPLETED | Job completed normally |
| COMPLETED | COMPLETED_WITH_WARNINGS | Job completed with warnings per application convention |
| FAILED | FAILED | Job failed |
| STOPPED | STOPPED | Job stopped in a controlled manner |
| COMPLETED | custom code | Lifecycle completed; logical outcome defined by application |

BatchStatus is used by the framework to manage lifecycle, restart, and execution status in JobRepository. ExitStatus is typically used to control flows, record outcomes, and communicate termination meaning to external systems.

Do not set BatchStatus to COMPLETED just so the scheduler receives code 0 when the Job actually failed. Nor should you arbitrarily set ExitStatus to FAILED while BatchStatus remains COMPLETED, unless that is a clearly designed and tested convention. Both the scheduler and operators need to understand both fields.

## 4. Why Do Schedulers Need Process Exit Codes?

A scheduler usually launches a process, waits for the process to finish, and reads its exit code. Common convention across many operating systems:

- 0 usually indicates success.
- Non-zero values usually indicate an error or special outcome.

Example:

~~~text
Scheduler
   |
   | start java -jar batch-app.jar
   v
Spring Batch Job
   |
   | execute Steps
   v
JobExecution finishes
   |
   | ExitStatus = COMPLETED
   v
Map ExitStatus -> integer
   |
   v
Process exits with code 0
   |
   v
Scheduler marks SUCCESS
~~~

If the application always terminates the process with code 0 regardless of JobExecution, the scheduler cannot distinguish a successful Job from a failed Job. This often happens when an application launches a Job and exits without propagating the Batch outcome out of main.

Process exit codes are suitable when a scheduler runs a standalone batch application per schedule. For a long-running Spring Boot application such as a service or API server, the process typically does not exit after each Job; in that model, the scheduler should monitor the Job via API, JobRepository, or events instead of relying on the server process exit code.

## 5. Mapping ExitStatus to Numeric Codes

You should define a clear mapping table between string exit codes and process codes.

Example:

| Job ExitStatus | Process exit code | Meaning to scheduler |
|---|---:|---|
| COMPLETED | 0 | Success |
| COMPLETED_WITH_WARNINGS | 4 | Completed with warnings |
| STOPPED | 20 | Controlled stop |
| FAILED | 10 | Failed |
| VALIDATION_FAILED | 11 | Invalid input data |
| UNKNOWN or unrecognized code | 30 | Unknown outcome |

The numbers above are example conventions, not mandatory Spring Batch standards. They must be agreed upon with scheduler configuration and organizational operational conventions. Some schedulers treat every non-zero code as failure; if you want code 4 to be treated as warning/success-with-warning, you must configure the scheduler to recognize that code specifically.

Keep the mapping table centralized in a single class or configuration, rather than scattering integers across multiple listeners and scripts. When changing a code, the application and scheduler must be updated in sync.

## 6. ExitCodeMapper in Spring Batch

Spring Batch provides the ExitCodeMapper interface to map a String exit code to an integer:

~~~java
public interface ExitCodeMapper {
    int intValue(String exitCode);
}
~~~

A custom implementation can define conventions for the scheduler:

~~~java
public class SchedulerExitCodeMapper implements ExitCodeMapper {

    @Override
    public int intValue(String exitCode) {
        if ("COMPLETED".equals(exitCode)) {
            return 0;
        }
        if ("COMPLETED_WITH_WARNINGS".equals(exitCode)) {
            return 4;
        }
        if ("STOPPED".equals(exitCode)) {
            return 20;
        }
        if ("VALIDATION_FAILED".equals(exitCode)) {
            return 11;
        }
        if ("FAILED".equals(exitCode)) {
            return 10;
        }

        // Unrecognized codes must be handled cautiously.
        return 30;
    }
}
~~~

The critical point is handling unrecognized codes as well. Returning 0 for an unfamiliar ExitStatus could cause a future error to be interpreted by the scheduler as success. A non-zero value for UNKNOWN/default is much safer.

In Spring Batch, CommandLineJobRunner uses ExitCodeMapper to convert the Job result into a process exit code. You can supply an appropriate mapper through the runner's extension point or use a launcher wrapper if the application has a custom launch mechanism. Check the API of the Spring Batch version in use, as runner configuration can differ across versions.

## 7. Default SimpleJvmExitCodeMapper

Spring Batch includes SimpleJvmExitCodeMapper to provide simple integer mapping for command-line execution. The default mapping commonly uses codes such as:

- COMPLETED maps to 0.
- FAILED maps to 1.
- NOOP maps to 2.
- Exit codes not in the mapping map to a non-zero default code.

Exact default mapping details should be confirmed for the framework version in use. Do not rely on default codes if the scheduler needs to distinguish multiple business states such as completed-with-warning, stopped, or validation failure.

When the scheduler only needs success/failure, simple mapping may suffice. When branching based on outcomes is required, define an explicit mapper and document the code contract in operational runbooks.

## 8. Setting a Custom ExitStatus from a Step

A Step can change ExitStatus via StepExecutionListener.afterStep. For example, a Step finishes but has some skipped items:

~~~java
public class WarningExitStatusListener
        implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        long skipped = execution.getReadSkipCount()
                + execution.getProcessSkipCount()
                + execution.getWriteSkipCount();

        if (execution.getStatus() == BatchStatus.COMPLETED
                && skipped > 0) {
            return execution.getExitStatus().and(
                    new ExitStatus("COMPLETED_WITH_WARNINGS"));
        }

        return execution.getExitStatus();
    }
}
~~~

Register the listener on the Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        WarningExitStatusListener warningListener,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(warningListener)
            .build();
}
~~~

The listener only produces a warning code when the Step's BatchStatus is COMPLETED and there are skips. If the Step FAILED, the listener preserves the current ExitStatus so as not to mask the failure.

In the flow DSL, a Step's ExitStatus can be used to choose transitions. If the Job has multiple Steps, determine how each Step's outcome aggregates into the Job's final ExitStatus. Do not assume one Step's custom code will always become the Job's final code if subsequent Steps can alter the result.

## 9. Setting the Final ExitStatus at the Job Level

When reporting the overall outcome to the scheduler, you can use JobExecutionListener to adjust the Job's final ExitStatus based on BatchStatus and Step counters.

Example:

~~~java
public class JobResultListener implements JobExecutionListener {

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() != BatchStatus.COMPLETED) {
            return;
        }

        long totalSkips = jobExecution.getStepExecutions()
                .stream()
                .mapToLong(step -> step.getReadSkipCount()
                        + step.getProcessSkipCount()
                        + step.getWriteSkipCount())
                .sum();

        if (totalSkips > 0) {
            jobExecution.setExitStatus(
                    new ExitStatus(
                            "COMPLETED_WITH_WARNINGS",
                            "Job completed with " + totalSkips + " skipped items"));
        }
    }
}
~~~

Register the listener on the Job:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        JobResultListener resultListener,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .listener(resultListener)
            .start(importOrdersStep)
            .build();
}
~~~

This example preserves BatchStatus COMPLETED and only changes ExitStatus to a warning code. JobRepository persists execution status according to the Job lifecycle; verify actual behavior with integration tests for your Spring Batch version.

If the Job failed, do not overwrite ExitStatus FAILED with COMPLETED_WITH_WARNINGS. The scheduler must receive the corresponding failure code.

## 10. Flow Transitions and Scheduler Exit Codes Are Separate Concerns

ExitStatus can drive the flow inside a Job. Process exit code, on the other hand, is used after the Job finishes to report the outcome to the operating system.

For example, a flow can handle validation status separately:

~~~java
return new JobBuilder("importOrdersJob", jobRepository)
        .start(validateInputStep)
            .on("VALIDATION_FAILED").fail()
        .from(validateInputStep)
            .on("COMPLETED").to(importOrdersStep)
        .from(importOrdersStep)
            .on("*").end()
        .end()
        .build();
~~~

The snippet illustrates branching by ExitStatus; actual flows must be configured according to the statuses returned by Steps and the builder API of the version in use.

Flow transitions do not call the scheduler directly and do not automatically generate a process exit code. Only after the Job finishes does the launcher or wrapper read the final ExitStatus and map it to an integer.

Avoid using the same exit code string for two different meanings. For example, if VALIDATION_FAILED is used to terminate the Job in the flow, agree on whether it means BatchStatus FAILED or a business state that completed cleanly with no valid input. BatchStatus, ExitStatus, and process code must all reflect the chosen contract consistently.

## 11. Using CommandLineJobRunner

CommandLineJobRunner is the way Spring Batch provides to launch a Job from the command line. The runner loads configuration, locates the Job, receives JobParameters, runs the Job, and uses ExitCodeMapper to convert ExitStatus to a process exit code.

Overview flow:

~~~text
java command
    |
    v
CommandLineJobRunner
    |
    +--> create ApplicationContext
    |
    +--> find Job and parse JobParameters
    |
    +--> JobLauncher.run(...)
    |
    +--> receive JobExecution
    |
    +--> get ExitStatus.exitCode
    |
    +--> ExitCodeMapper.intValue(...)
    |
    v
process exit code
~~~

When using the runner, verify command-line arguments, Job name, classpath, and JobParameters. If using a custom ExitCodeMapper, ensure the runner is actually configured to use that mapper. A custom mapper declared as a bean but not wired into the runner will not change the process exit code.

With newer Spring Batch versions or Spring Boot applications, launching may rely on a custom launcher rather than CommandLineJobRunner. The principle remains the same: a final component must read the JobExecution result and return an integer for the process.

## 12. Spring Boot and Process Exit Codes

A Spring Boot application can automatically run a Job at startup. However, the Job finishing and the JVM returning an exit code are two separate steps. If the application runs as a standalone batch process, you must explicitly translate the Job outcome into an exit code before the process terminates.

Spring Boot provides ExitCodeGenerator and SpringApplication.exit to retrieve the exit code from the application context. You can create a bean that both listens to the Job and supplies the numeric code:

~~~java
@Component
public class BatchProcessExitCode
        implements JobExecutionListener, ExitCodeGenerator {

    private volatile int exitCode = 30;

    @Override
    public void beforeJob(JobExecution execution) {
        // Default to an error code until the final result is available.
        exitCode = 30;
    }

    @Override
    public void afterJob(JobExecution execution) {
        String code = execution.getExitStatus().getExitCode();

        if ("COMPLETED".equals(code)) {
            exitCode = 0;
        } else if ("COMPLETED_WITH_WARNINGS".equals(code)) {
            exitCode = 4;
        } else if ("STOPPED".equals(code)) {
            exitCode = 20;
        } else if ("VALIDATION_FAILED".equals(code)) {
            exitCode = 11;
        } else {
            exitCode = 10;
        }
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
~~~

In the main method of a standalone batch application:

~~~java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(BatchApplication.class, args);

    int code = SpringApplication.exit(
            context,
            context.getBean(BatchProcessExitCode.class));

    System.exit(code);
}
~~~

The example assumes the Job runs synchronously during the startup flow and the listener has received afterJob before SpringApplication.exit is called. If using an asynchronous JobLauncher, main may exit before the Job finishes; in that case, wait for execution completion or use a different orchestration model.

Do not call System.exit from a listener or from item processing code. Terminating the JVM immediately inside a callback can skip cleanup, close resources improperly outside lifecycle, and leave metadata incompletely updated.

For a long-running Spring Boot server, do not use System.exit after each Job. A server process may run multiple Jobs and serve other requests; expose status via JobRepository, management APIs, events, or monitoring systems.

## 13. Ensuring the Job Finishes Before Process Exit

For the scheduler to receive the right code, the process should exit only after JobExecution has reached a terminal state and its result has been persisted.

Points to check:

- Whether JobLauncher runs synchronously or asynchronously.
- Whether the application waits for JobExecution to complete.
- Whether JobExecutionListener.afterJob has been invoked.
- Whether JobRepository has updated the final BatchStatus and ExitStatus.
- Whether the custom ExitCodeGenerator received the correct outcome.
- Whether main passes that numeric code out to the process.

If the launcher returns a JobExecution still in STARTED because it runs asynchronously, you cannot obtain the final exit status at that moment. The process must wait or use a separate callback/monitoring mechanism.

Do not extract status from log text or from the mere fact that a thread was spawned. Use JobExecution and JobRepository as the authoritative source of status.

## 14. Exit Code Conventions with Schedulers

Schedulers usually let you define which codes count as success, warning, retryable failure, or fatal failure. Agree on conventions before deployment.

Example:

| Code | Meaning | Illustrative scheduler action |
|---:|---|---|
| 0 | Normal completion | Mark success |
| 4 | Completed with warnings | Success with warning, send notification |
| 10 | Processing error | Mark failed, send alert |
| 11 | Invalid input data | Halt pipeline and request data inspection |
| 20 | Controlled stop | Wait for restart decision |
| 30 | Unknown outcome | Route to investigation, do not auto-treat as success |

These codes are only examples. Some schedulers have only two buckets (success/failure) and treat any non-zero code as failure. If you need code 4 to be a warning rather than a failure, configure the scheduler accordingly.

Do not use code 0 for a state where downstream cannot safely proceed. The scheduler might immediately trigger dependent Jobs based on code 0.

## 15. Process Exit Codes on Unix and Windows

On Unix-like systems, shells typically use 0 for success and non-zero for failure. Many shells only preserve a limited range of exit status values; choose small, manageable codes and do not rely on values outside the portable range.

On Windows, processes also return an integer exit code, though schedulers or wrapper scripts may interpret them differently. Confirm how your orchestration tool captures the code from the Java process.

If using a shell script, ensure the script returns the Java process's exit code. Shell example:

~~~bash
java -jar batch-app.jar
exit $?
~~~

If the script runs additional commands after Java, save the result code before subsequent commands overwrite the exit status value.

With PowerShell, you can propagate the native process code with:

~~~powershell
java -jar batch-app.jar
exit $LASTEXITCODE
~~~

A wrapper that fails to propagate the exit code can cause the scheduler to see the result of the last command in the script instead of the Job's outcome.

## 16. Logging and Auditing Scheduler Return Outcomes

When a Job ends, log enough fields to correlate the scheduler outcome with Spring Batch metadata:

- Job name.
- JobInstance ID.
- JobExecution ID.
- BatchStatus.
- ExitStatus exit code.
- Sanitized exit description.
- Final process exit code.
- Start and end times.
- Key read/write/filter/skip counts.

Structured log example:

~~~text
event=job_finished
job=importOrdersJob
jobInstanceId=842
jobExecutionId=108
batchStatus=COMPLETED
exitStatus=COMPLETED_WITH_WARNINGS
processExitCode=4
readCount=12000
writeCount=11995
skipCount=5
~~~

Do not log full JobParameters or payloads if they may contain credentials or personal data. Use execution ID to correlate with JobRepository and the audit store.

When investigating a Job reported failed by the scheduler, compare the process exit code with BatchStatus and ExitStatus. If the two systems disagree, inspect the mapper and wrapper script before concluding the Job processed data incorrectly.

## 17. Preventing Custom Exit Codes from Masking BatchStatus

An exit code convention can categorize outcomes in detail, but it should never misrepresent lifecycle status.

For example, a Job has BatchStatus FAILED because the database is unavailable. If a listener sets ExitStatus to COMPLETED_WITH_WARNINGS and the mapper returns 4, the scheduler may interpret this as a success with warnings. That masks a critical failure.

Establish precedence rules:

1. BatchStatus FAILED always maps to a failure process code, unless an explicitly approved special procedure dictates otherwise.
2. BatchStatus STOPPED maps to a distinct stop code if the scheduler needs to distinguish it.
3. Classify as warning only when BatchStatus is COMPLETED and warning conditions are clearly defined.
4. UNKNOWN or unrecognized exit codes must map to non-zero.
5. Never let a listener change a FAILED outcome to COMPLETED just so the scheduler runs a downstream step.

If a Job has a special business state such as VALIDATION_FAILED, decide explicitly whether it is a failed Job or a completed Job with rejected input. Schedulers, dashboards, and operators must share the exact same definition.

## 18. Testing Exit Codes

Both the mapping and the actual process must be tested. Unit tests for the mapper are not enough to prove the JVM returns the right code to the scheduler.

### Unit testing the mapper

~~~java
@Test
void mapsBatchExitStatusesToSchedulerCodes() {
    SchedulerExitCodeMapper mapper = new SchedulerExitCodeMapper();

    assertEquals(0, mapper.intValue("COMPLETED"));
    assertEquals(4, mapper.intValue("COMPLETED_WITH_WARNINGS"));
    assertEquals(20, mapper.intValue("STOPPED"));
    assertEquals(10, mapper.intValue("FAILED"));
    assertEquals(30, mapper.intValue("UNRECOGNIZED"));
}
~~~

Tests must match the application's actual mapping table.

### Integration testing the Job

Run the Job across scenarios:

- Job completes normally.
- Job completes with skips and produces warning status.
- Job fails in reader, processor, or writer.
- Job undergoes a controlled stop.
- Custom ExitStatus aggregates properly on JobExecution.
- Exceptions in listeners do not unintentionally lose outcomes or metadata.

### Testing the actual process

Launch the application using the exact command the scheduler uses, then check the process exit code in the shell or process test harness. Verify:

- Code 0 when the Job completes.
- Non-zero code when the Job fails.
- Agreed warning code when the Job completes with warnings.
- Unknown exit status is not mapped to 0.
- Wrapper script propagates the Java process code accurately.
- Process exits only after JobExecution completes.

For Spring Boot, test main/exit integration or spawn a child process in the test environment. Do not merely assert ExitCodeGenerator.getExitCode() and assume the scheduler will receive the right value.

## 19. Common Pitfalls

**Confusing ExitStatus with process exit code.** ExitStatus is a string; schedulers need an integer. A mapper is required.

**Checking only BatchStatus.** A Job may be COMPLETED while a custom ExitStatus indicates warnings.

**Always returning code 0.** The scheduler may mark a FAILED Job as successful.

**Using unspecified codes.** Schedulers may mishandle new states. Always have a non-zero default for unknown codes.

**Custom mapper not used by the runner.** Declaring a bean does not guarantee integration into the command-line runner. Verify actual wiring.

**Process exiting before the Job finishes.** With an asynchronous launcher, the exit code may reflect an intermediate state.

**Wrapper script losing the return code.** Commands after Java can overwrite exit status if the script does not save and return the code.

**Calling System.exit inside a listener.** Can cut short lifecycle execution and prevent metadata from being fully saved.

**Using process exit codes for long-running servers.** Servers should not exit after each Job's result; use APIs or JobRepository for tracking.

**Changing mapping without updating the scheduler.** The two systems no longer agree on code meanings.

## 20. Workflow for Implementing Scheduler Exit Codes

When integrating Spring Batch with a scheduler, follow this sequence:

1. Determine whether the scheduler needs only success/failure or also warnings, stopped, and validation failure.
2. Choose a process exit code convention, documenting codes and meanings.
3. Distinguish BatchStatus, ExitStatus, and process exit code in the design.
4. Create custom ExitStatus at Step/Job level only when genuinely needed.
5. Ensure BatchStatus FAILED is never converted into a success code.
6. Configure ExitCodeMapper or ExitCodeGenerator appropriate to the launch method.
7. If using CommandLineJobRunner, confirm the runner uses the chosen mapper.
8. If using Spring Boot, wait for the Job to finish, then call SpringApplication.exit and return the code from main to the process.
9. Ensure shell/PowerShell wrappers propagate Java's exit code.
10. Test using the exact command and environment the scheduler will run.

ExitStatus tells Spring Batch what logical outcome a Job ended with; ExitCodeMapper or ExitCodeGenerator translates that outcome into an integer for the process; the scheduler uses the process exit code to decide the next step. When these three layers are designed and tested together, the Job status in JobRepository, the JVM return code, and the status displayed by the scheduler remain consistent.

