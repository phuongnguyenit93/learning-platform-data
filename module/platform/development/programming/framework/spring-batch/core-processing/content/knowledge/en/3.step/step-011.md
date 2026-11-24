# The Limits of Stuffing Too Much Logic into One Step

In Spring Batch, a `Step` is an execution phase of a `Job`. A step can contain many small operations, but that does not mean all the work of a workflow should be put together in one step. When one step reads a file, validates data, updates multiple groups of tables, calls external services, generates reports, and sends notifications, it gradually becomes a processing block that is hard to understand and hard to operate.

Stuffing too much logic into one step blurs the boundaries of responsibility, making it difficult to control transactions, restart, retry, trace errors, and test. Conversely, splitting every small operation into its own step also creates a lot of metadata and makes the flow complicated. Good design divides the job into business phases with clear boundaries, while keeping operations that share the same purpose and the same recovery approach inside one step.

## 1. Why Shouldn't a Step Become a Miniature Workflow?

A step can be implemented with chunk processing or a tasklet. In chunk processing, a step usually coordinates `ItemReader`, `ItemProcessor`, and `ItemWriter` to process data in groups. In a tasklet, the application defines a task itself through the `execute` method.

Both kinds of step can contain a lot of code. The problem arises when a step takes on multiple different business phases, for example:

1. Read the input file and validate its structure.
2. Normalize and validate each record.
3. Write customer data to the database.
4. Update the balance or transaction status.
5. Call another system's API.
6. Generate a summary file and send a notification email.

If all of this sits inside one large tasklet or is driven by an overly complex processor/writer, the framework sees only one step with a single overall status. It is hard for operators to know which phase has completed, which phase failed, and where to recover from.

```text
One step holding the entire workflow

Job
 |
 +-- processEverythingStep
       +-- read the file
       +-- validate the data
       +-- write customers
       +-- update transactions
       +-- call the external API
       +-- generate the report
       +-- send the email
```

Putting a lot of logic in one step does not automatically make an application wrong. A single step can still be the right choice if the operations form a cohesive unit of processing, with the same transaction boundary and the same restart approach. However, when the operations have different lifecycles or operational requirements, grouping them together creates clear limitations.

## 2. It Is Hard to Pinpoint Where an Error Occurred

Spring Batch stores execution state at the job and step levels. With a chunk-oriented step, the framework also records metrics such as the number of items read, written, filtered, or skipped. If a step contains multiple phases that are not modeled as separate steps, the `FAILED` status only tells you that the overall step failed.

For example, a step sequentially imports data, updates a summary table, and exports a report. If an error occurs while exporting the report, the step can fail even though the data import and the summary update have completed. The operator has to read the logs or check the data manually to know what work has taken place.

When divided into meaningful steps, the status becomes clearer:

```text
validateInputStep   -> COMPLETED
importCustomerStep  -> COMPLETED
updateBalanceStep   -> COMPLETED
exportReportStep    -> FAILED
notifyResultStep    -> not yet run
```

Looking at the metadata, you can identify the phase that failed and the phases that have not started. This makes monitoring, root cause analysis, and incident handling easier.

## 3. It Is Hard to Restart the Right Part of the Work

Restart in Spring Batch is based on `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext`. When a job is restarted, a step that has completed is usually skipped; a step that failed or has not completed is executed according to the step's restart rules.

If multiple independent phases are in the same step, Spring Batch has no separate completion status for each phase inside it. When the step fails, the step's logic may be called again. The application must itself know which part has been done and ensure that re-doing it does not create duplicate side effects.

For example:

```text
A single step:
  1. writes 10,000 customers successfully
  2. updates the statistics table successfully
  3. calls the partner API, which times out
  4. the step ends FAILED

Restart:
  the step runs again
  -> risk of writing the customers again
  -> risk of updating the statistics again
  -> calls the partner API again
```

If you split into appropriate steps, the steps that are `COMPLETED` are usually skipped when the same JobInstance is restarted. The step that calls the API can be executed again according to its own state. This creates a recovery boundary that is easier to understand.

Splitting steps does not automatically guarantee that data is not duplicated. An operation may have produced an external side effect before the step recorded completion or before the metadata was committed. Therefore, writers and external integrations still need idempotency, business keys, or a reconciliation mechanism.

## 4. Transaction Boundaries Become Hard to Control

Transactions are an important reason to design steps with a sensible scope. With a chunk-oriented step, each chunk is usually processed in one transaction: read and process the items, write the chunk, and then commit. With a tasklet step, Spring Batch manages the transaction for each tasklet call according to the step's configuration.

An overly large step can combine operations that need different transaction policies. For example, updating data in the database needs to roll back when a write fails, while sending an email or making an HTTP call cannot automatically roll back along with the database transaction.

If those operations are placed together in one step, programmers can easily and unintentionally assume that an error at the end of the workflow will undo everything before it. In reality, only the resources participating in the same transaction are managed by that transaction manager. An email that has been sent or an HTTP request that a partner has already processed usually cannot be revoked by a JDBC rollback.

Dividing steps along business boundaries helps clearly identify:

- Which phase writes data in one database transaction.
- Which phase performs external side effects.
- Which phase can be re-run safely.
- Which phase needs its own retry or error handling.

Note: a step is not a global transaction spanning the entire job. When split into multiple steps, the transactions of earlier steps that have already committed are not automatically rolled back if a later step fails. Splitting steps clarifies the transaction boundaries; it does not create a distributed transaction for the entire job.

## 5. Retry, Skip, and Error-Handling Policies Are Hard to Apply Precisely

Spring Batch lets you configure retry and skip in chunk processing. These policies are usually applied at the item level or at the read, process, and write operations of a step.

Suppose a step reads a file, validates data, writes to the database, and calls a billing service. The errors can be of very different natures:

- A malformed CSV line may need to be skipped and recorded as a data error.
- A database connection error may need a retry or make the step fail.
- A billing API timeout may need a retry with backoff and an idempotency key.
- An invalid business rule may require discarding the record or putting it into a quarantine area.

If all the logic sits in one large processor or writer, exceptions can be hard to classify. A broad retry policy can repeat operations that should not be repeated; a broad skip policy can skip a serious infrastructure error as if it were a data error.

Splitting phases that have different error policies into separate steps helps place retry, skip, listeners, and run limits in the right place. Even so, retry and skip still need to be designed based on the actual error types; do not split steps merely to avoid classifying exceptions.

## 6. It Is Hard to Monitor Performance and Find Bottlenecks

A large step can perform many kinds of work with different performance characteristics. Reading a file is usually limited by I/O speed; data processing can be limited by CPU; writing to a database can be limited by indexes or locks; calling an external API depends on network latency.

If you group everything into one step, the step's overall time does not tell you exactly which phase is slow. The chunk counters also do not fully show the time spent on each custom side effect.

When split by phase, you can observe the duration and status of each step separately, and from that determine whether to optimize the reader, processor, writer, database query, or external integration. Independent steps can also be considered for partitioning or for running under an appropriate orchestration mechanism when the architecture allows.

Do not split steps just to get more metrics. If a small phase has no operational requirements of its own, a listener or a component-level metric may be enough to observe it without complicating the flow.

## 7. A Large Step Makes the Code Hard to Read and Test

A step with too many responsibilities usually brings many dependencies, conditions, and internal states. For example, a tasklet can read configuration, query multiple repositories, process business logic, call a REST client, write files, and send emails all at once.

Common consequences:

- The `execute` method is long, has many `if/else` branches, and the processing order is hard to follow.
- A small change in the report generation phase can affect the data import phase.
- Unit tests have to mock too many dependencies to check a single behavior.
- It is hard to test restart or failure scenarios for each phase on its own.
- Multiple team members edit the same class or step configuration, making conflicts likely.

Splitting steps by business phase makes the configuration and state of each part clear. The business-processing classes can still be broken into small services and called from the reader, processor, writer, or tasklet. Not every helper method has to become a step.

## 8. Example: An Overloaded Step and How to Reorganize It

Suppose a job processes a payment file. The initial implementation puts all the work in one tasklet:

```java
@Bean
Step processPaymentFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PaymentFileService paymentFileService,
        PaymentRepository paymentRepository,
        PartnerClient partnerClient,
        ReportService reportService,
        NotificationService notificationService) {

    return new StepBuilder("processPaymentFileStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                var payments = paymentFileService.readAndValidate();
                paymentRepository.saveAll(payments);
                partnerClient.publishPayments(payments);
                reportService.createReport(payments);
                notificationService.sendCompletionNotice();
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

The code is short but contains many phases with different characteristics. If `sendCompletionNotice` fails after the data has been written and the partner has received the payments, the step can still end `FAILED`. On restart, the tasklet risks running all the operations again.

You can reorganize the job into steps by phase:

```text
validatePaymentFileStep
          |
          v
importPaymentsStep
          |
          v
publishPaymentsStep
          |
          v
createPaymentReportStep
          |
          v
sendCompletionNoticeStep
```

An example of job configuration for Spring Batch 5 and later:

```java
@Configuration
public class PaymentJobConfiguration {

    @Bean
    Job paymentJob(
            JobRepository jobRepository,
            Step validatePaymentFileStep,
            Step importPaymentsStep,
            Step publishPaymentsStep,
            Step createPaymentReportStep,
            Step sendCompletionNoticeStep) {

        return new JobBuilder("paymentJob", jobRepository)
                .start(validatePaymentFileStep)
                .next(importPaymentsStep)
                .next(publishPaymentsStep)
                .next(createPaymentReportStep)
                .next(sendCompletionNoticeStep)
                .build();
    }
}
```

The `Step` beans are declared separately with the appropriate reader, processor, writer, or tasklet. For example, `importPaymentsStep` can be a chunk-oriented step to read and write many payments in groups; `createPaymentReportStep` can be a tasklet because it creates a single summary file.

After the reorganization, if the report generation step fails, the metadata clearly shows that the payment import and publishing steps have completed. When the same JobInstance is restarted, the completed steps are usually skipped and the step that needs to continue is executed according to its configuration.

For `publishPaymentsStep`, you need to ensure that the partner supports an idempotency key or there is a way to look up the status of what was received. If the partner has received the request but the client times out before receiving the response, resending may create a repeated side effect. Splitting the step makes it clear where to handle this situation, but does not by itself resolve consistency with the external system.

## 9. Not Every Operation Needs Its Own Step

Splitting steps too much also has a cost. Each step adds execution metadata, state, configuration, listeners, and relationships in the flow. A job with dozens or hundreds of very small steps can be hard to read, hard to orchestrate, and hard to maintain.

For example, if a workflow needs to trim a string, normalize upper/lower case, and check a required field for each item, there is no need to create three steps for just those three transformations. This is a chain of operations on the same item, so it can be placed in one `ItemProcessor` or in a service called by the processor.

Similarly, if a tasklet needs to create a directory and then create a marker file in the same preparation operation, the two actions can sit in the same step if they have the same purpose, the same error handling, and the same restart policy.

Splitting a step is usually reasonable when one or more of the following conditions apply:

- The phase has its own business meaning and needs its own completion status.
- The phase can fail independently and needs to be restarted independently.
- The phase has a different transaction manager, resource, or commit boundary.
- The phase needs different retry, skip, or run-limit policies.
- The phase has its own operational requirements, schedule, or monitoring.
- The phase needs to run conditionally or can be skipped depending on a previous result.
- The phase can be partitioned or distributed in its own way.

Keep operations together in one step when they are part of the same unit of processing, have the same lifecycle and the same recovery approach, and splitting them out would not add clear operational value.

## 10. Choose Chunk or Tasklet by the Nature of the Work

Stuffing logic sometimes originates from choosing the wrong kind of step. A tasklet can contain a large loop that reads each record, processes it, and writes data itself. In that case the application has to manage many concerns that chunk processing already provides.

| Need | Commonly suitable implementation |
|---|---|
| Read many items, process each item, and write in groups | Chunk-oriented step with `ItemReader`, `ItemProcessor`, `ItemWriter`. |
| Perform an operation with a clear scope such as cleaning up files or calling a stored procedure | Tasklet step. |
| Validate or prepare the input data before import | A tasklet, or a separate step if it needs its own state and restartability. |
| Transform each record by business rules | `ItemProcessor` or a service called by the processor. |
| Bulk write data to a single destination | `ItemWriter` in a chunk-oriented step. |
| Generate a report after the import completes | A separate step if the report is a business phase that can be monitored or restarted independently. |

Do not turn a tasklet into a home-grown batch processing framework if the actual requirement fits chunk processing. Conversely, there is no need to use chunk just to run one SQL statement or a simple preparation operation.

## 11. Data That Needs to Pass Between Steps

When you split a job into multiple steps, you may need to pass results from an earlier step to a later step. Spring Batch provides `ExecutionContext` at the step and job scopes. A step can store a small value, such as an output file name, a record count, or a batch ID, for a later step to use.

For example, a file validation step can store the path of the normalized file in the job execution context; the import step reads that value through late binding or an appropriate coordinating component.

```java
@Bean
Step prepareInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("prepareInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                String normalizedPath = "data/ready/orders.csv";
                chunkContext.getStepContext()
                        .getStepExecution()
                        .getJobExecution()
                        .getExecutionContext()
                        .putString("normalizedInput", normalizedPath);
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

The ExecutionContext is suited to small metadata needed for orchestration and restart. Do not use it to pass hundreds of thousands of objects or large payloads between steps. For large data, write it to a database, file, or object storage and pass a key or a reference path.

When designing data between steps, you need to define clearly who creates it, who reads it, when the data is committed, and whether the later step can be re-run safely. If a later step depends on data that has not been committed or a file that has not been fully closed, a restart may read incomplete data.

## 12. Splitting Steps and Conditional Flow Control

Another benefit of having separate steps is that the job can choose a branch based on the result of a phase. Spring Batch supports flow transitions based on `ExitStatus` and orchestration mechanisms such as `JobExecutionDecider`.

For example, after validating a file:

- If there is valid data, continue with the import.
- If the file is empty, move to a step that records the empty result.
- If the data is invalid, end the job along the business error branch.

If all the logic sits in one large step, these branches usually become many nested conditional statements inside the tasklet. When split into steps and flow transitions, the job's paths are expressed directly in the configuration.

There is no need to split a step just because there is an `if` statement. Split when a branch represents a phase with its own state, behavior, or operational policy.

## 13. How to Refactor a Step That Is Too Large

When you encounter a step with too much logic, you can improve it incrementally:

1. **List the current actions:** record the inputs, outputs, database operations, external calls, files created, and error branches.
2. **Group by business phase:** for example data preparation, import, external system synchronization, and report generation.
3. **Determine the commit boundaries:** clarify which operations share a transaction and which have already produced side effects that cannot be rolled back.
4. **Determine the recovery approach:** which phases need restart, retry, skip, or can be re-run safely.
5. **Choose the step type:** use chunk for processing items in groups; use a tasklet for single tasks or tasks controlled by the application.
6. **Extract business services:** keep the computation logic and rules in classes with clear responsibilities, called from the processor, writer, or tasklet.
7. **Declare the flow:** connect the steps in order or in the conditional branches needed.
8. **Design the transitional data:** put only keys or small metadata into the ExecutionContext; store large data in an appropriate place.
9. **Review idempotency:** ensure that re-running a step does not create duplicate records, transactions, or external requests.
10. **Test the operational scenarios:** success, failure at each phase, restart, empty data, and external service errors.

Do not split a large step by simply moving the code block into several classes without redefining the transaction and restart boundaries. The goal is to clarify responsibilities and the recovery approach, not just to shorten the `execute` method.

## 14. Some Signs That a Step Is Overloaded

You can consider redesigning when you encounter the following signs:

- A step has many dependencies belonging to unrelated systems or business domains.
- The `execute` method, processor, or writer has many sequential phases and many error branches.
- When the step fails, you have to manually check multiple tables or files to know which part has completed.
- A restart risks repeating side effects that already happened in earlier phases.
- The same step needs different retry/skip policies for several kinds of work.
- The step's logs are not enough to find the slow or failing phase.
- A change in one phase often forces you to modify or retest the entire step.

These signs are not hard rules. A step with many dependencies is not necessarily wrong if they all serve one unit of processing. Evaluate by business, transaction, and recovery boundaries rather than by merely counting lines of code or dependencies.

## 15. Limits to Consider When Splitting Into Too Many Steps

Splitting steps brings separate state and operability, but it also increases complexity:

- Each step adds metadata and a `StepExecution` that needs to be stored.
- The job flow has more edges and branches, which is harder to follow if step names or transitions are not meaningful.
- You need to pass data between steps and manage the lifecycle of files or intermediate resources.
- Additional operations may arise for initialization, closing resources, and committing metadata.
- Deploying a change that spans multiple steps may require updating many configurations.
- Earlier steps that have committed are not automatically rolled back when a later step fails; a compensation process is needed if the business requires it.

Therefore, there is no optimal number of steps that applies to every job. A data import job may need only one chunk-oriented step if the entire work is a single cohesive read-process-write flow. A job that reconciles multiple systems may need many steps because each phase has its own state, transactions, and recovery policy.

## 16. Practical Design Principles

When deciding whether to add more logic into a step or split it into a new step, ask yourself:

1. Does the new work have the same business goal as the current step?
2. Does it have the same inputs, outputs, and transaction boundary?
3. If the new work fails, do you need to retain the completed status of the earlier part?
4. Does it need its own retry, skip, run limit, or monitoring?
5. On restart, can the whole step be re-run safely?
6. Does splitting it out help operators understand the job's status better?
7. Is the additional metadata and orchestration cost proportionate to the benefit?

If two pieces of work have different lifecycles and recovery approaches, consider splitting them into separate steps. If they are just small operations within the same item-processing cycle, keeping them in the processor or a service is usually easier to manage.

A good step has a scope small enough to be understood, monitored, and recovered, yet large enough to avoid turning a job into a long chain of trivial operations. When designed along business boundaries, Spring Batch can make good use of its capabilities for transaction management, restart, retry, skip, and status tracking without making the flow tangled.
