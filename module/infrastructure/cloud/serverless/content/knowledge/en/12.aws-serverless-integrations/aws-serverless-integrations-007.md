# Orchestrating Lambda with AWS Step Functions

A serverless application often consists of multiple Lambda functions and AWS services. A single business request might need to validate data, check inventory, collect payment, create a shipment, and send notifications. If one function calls all steps sequentially, it has to manage ordering, timeouts, retries, state, and recovery when an intermediate step fails.

AWS Step Functions provides workflow orchestration to coordinate these steps using a state machine. The state machine tracks execution progress, invokes Lambda or other AWS services, branches, runs steps in parallel, waits for events, and handles errors as defined. Java functions focus on individual step logic, while Step Functions manages control flow and workflow state.

This lesson explains how to design state machines, integrate Java Lambda functions, handle errors, and choose the right workflow type for real workloads.

## 1. What Problems Does Step Functions Solve?

When multiple functions coordinate, an application must answer several questions:

- Which step runs first, and which step runs only when a condition is met?
- If a step fails transiently, should it retry and how many times?
- If a step fails after an earlier step already produced side effects, how do you undo or compensate?
- How do you run independent steps in parallel?
- How do you wait hours for human approval or a partner system without keeping Lambda running?
- How do you track an order across multiple functions?
- When a workflow reruns, how do you avoid creating duplicate transactions or notifications?

Step Functions models these answers as a state machine. Each state performs an action or controls flow, then transitions to the next state.

~~~mermaid
flowchart TD
    A["Receive order request"] --> B["ValidateOrder Lambda"]
    B --> C{"Valid data?"}
    C -->|No| X["RejectOrder"]
    C -->|Yes| D["ReserveInventory Lambda"]
    D --> E["ChargePayment Lambda"]
    E --> F{"Payment succeeded?"}
    F -->|Yes| G["CreateShipment Lambda"]
    F -->|No| H["ReleaseInventory Lambda"]
    H --> X
    G --> I["NotifyCustomer Lambda"]
    I --> J["Succeed"]
~~~

No single Lambda needs to hold the entire control flow. Each Task state can invoke a dedicated function. Step Functions records outcomes and decides the next state as defined.

### 1.1. Orchestration vs. Choreography

Two common patterns coordinate services:

- **Orchestration:** a central coordinator knows the steps, sequence, and state. Step Functions is an orchestration service.
- **Choreography:** services emit and consume events; each service decides how to react without a centralized control flow.

Orchestration fits when a process has clear ordering, multiple branches, timeouts, retries, approvals, or needs end-to-end state visibility. Choreography fits independent components reacting to events with little need for a central control flow.

Both can be combined: Step Functions orchestrates a major business workflow, while one step in the workflow emits an event for other services to process independently.

## 2. Components of AWS Step Functions

A workflow typically includes:

- **State machine:** defines the process and its states.
- **Execution:** a specific run of the state machine, with input, output, status, and history.
- **State:** a step or control point in the workflow.
- **Task:** invokes Lambda, integrates with an AWS service, or executes external work.
- **Choice:** branches based on data.
- **Parallel:** runs multiple branches concurrently.
- **Map:** iterates over a collection of items and processes each item.
- **Wait:** pauses for a duration or until a timestamp.
- **Succeed/Fail:** terminates the workflow successfully or with failure.
- **Retry/Catch:** defines error-handling behavior at a state.

State machine definitions are written in Amazon States Language (ASL), usually represented in JSON. State machines can be created and deployed via the AWS Console, AWS CLI, CloudFormation, AWS CDK, or Terraform.

A state machine has `StartAt` indicating the initial state and `States` containing state definitions. Each state has a `Type` and fields specific to that state type. States transition via `Next`, terminate via `End: true`, or branch using type-specific structures.

## 3. Commonly Used State Types

| State type | Role | Example |
|---|---|---|
| Task | Performs work or calls a service | Invoke Java Lambda to validate an order |
| Choice | Branches on conditions | Payment succeeded vs. failed |
| Pass | Transforms data or injects static data | Attach metadata to input |
| Wait | Waits for a duration or until a timestamp | Wait 15 minutes before rechecking |
| Parallel | Runs multiple independent branches | Calculate tax and validate address concurrently |
| Map | Iterates over a list of elements | Process each line item in an order |
| Succeed | Ends successfully | Order completed |
| Fail | Ends with failure | Invalid input data |

Task is typically the state connecting Step Functions to Lambda or an AWS service. Choice directs flow without writing a function solely to check conditions. Parallel and Map unlock concurrency, though concurrency limits and downstream load must be considered.

## 4. Invoking Java Lambda via Optimized Integration

Step Functions provides an optimized integration for Lambda. With request-response, the state machine invokes Lambda and waits for the invocation to return before transitioning to the next state.

Commonly used resource:

~~~text
arn:aws:states:::lambda:invoke
~~~

A Task state can pass workflow input into Lambda's payload:

~~~json
{
  "StartAt": "ValidateOrder",
  "States": {
    "ValidateOrder": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:validate-order:prod",
        "Payload.$": "$"
      },
      "ResultSelector": {
        "validation.$": "$.Payload"
      },
      "ResultPath": "$.validationResult",
      "Next": "CheckValidation"
    },
    "CheckValidation": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.validationResult.validation.valid",
          "BooleanEquals": true,
          "Next": "OrderAccepted"
        }
      ],
      "Default": "OrderRejected"
    },
    "OrderAccepted": {
      "Type": "Succeed"
    },
    "OrderRejected": {
      "Type": "Fail",
      "Error": "Order.Invalid",
      "Cause": "Order validation failed"
    }
  }
}
~~~

The example uses JSONPath syntax and illustrates structure only. Replace `REGION`, `ACCOUNT`, and function names with values from your deployment environment. The `FunctionName` field can reference a function, version, or alias. Using an alias such as `prod` pins the workflow to an intentional deployment version.

When using optimized integration, Step Functions wraps the invocation result in a response object where Lambda's output sits under `Payload`. `ResultSelector` picks which fields to keep, while `ResultPath` specifies where to merge the result into the state input. Without filtering, the workflow may carry unnecessary metadata across many states.

### 4.1. Request-Response vs. Asynchronous Lambda Invocation

By default, optimized Lambda integration waits for Lambda to finish and receives the result. This is appropriate when the next step needs the function's output.

If you want to dispatch an asynchronous invocation, you can configure invocation parameters matching the Lambda API, such as `InvocationType: Event` inside `Parameters` per the integration contract. Step Functions then only knows the invoke request was submitted and does not wait for the function's final business result. If completion tracking is needed, use callbacks, queues, events, or another workflow to report completion.

Do not use asynchronous invocation merely to bypass timeouts without a tracking mechanism. If the workflow needs to know whether a task succeeded or failed, there must be an explicit continuation signal.

## 5. Java Lambda as a Workflow Step

A Java function should accept an input with a clear schema and return a small, structured result. It does not need to know the entire state machine when responsible for a single business step.

Example of an order-validation Lambda:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public class ValidateOrderHandler
        implements RequestHandler<OrderInput, ValidationResult> {

    @Override
    public ValidationResult handleRequest(
            OrderInput input,
            Context context) {

        if (input == null || input.getOrderId() == null
                || input.getItems() == null || input.getItems().isEmpty()) {
            return new ValidationResult(false, "INVALID_ORDER");
        }

        return new ValidationResult(true, "OK");
    }
}
~~~

`OrderInput` and `ValidationResult` are application-defined POJOs with constructors/getters/setters compatible with the serializer in use. The example omits full model classes to focus on the function contract.

An input might contain:

~~~json
{
  "orderId": "order-2026-00421",
  "customerId": "customer-42",
  "items": [
    {
      "sku": "book-101",
      "quantity": 2
    }
  ],
  "correlationId": "req-7d2a"
}
~~~

Outputs should contain only data needed by subsequent steps, such as `valid`, `reasonCode`, or a resource ID. Avoid putting large binaries, sensitive data, or entire database records into state input/output.

### 5.1. Do Not Rely on In-Memory State

A Task may be retried or run in a different execution environment. Therefore, do not store critical business state solely in static variables or handler object fields. Persist it in a database or durable service.

You can reuse thread-safe HTTP clients or AWS SDK clients at the process level to reduce initialization overhead, but execution-specific data must reside in inputs or a controlled state store. Never assume one Lambda instance always handles the same workflow or only a single invocation.

## 6. Passing Data Between States

The state machine passes JSON input/output from state to state. With JSONPath, commonly used fields include:

- `InputPath`: selects a subset of input to pass into the state.
- `Parameters`: constructs input for a Task or state from current data.
- `ResultSelector`: selects a subset of the returned result.
- `ResultPath`: places the result into the current input.
- `OutputPath`: selects data to pass to the next state.

For example, the initial input includes order details and metadata. Lambda only needs the order part, so a sub-object can be passed instead of the entire input. Once Lambda returns a result, the workflow can store it under `validationResult` while keeping `orderId` for later steps.

~~~text
Workflow input
    |
    +-- order
    +-- customer
    +-- correlationId
          |
          v
Parameters -> Lambda Payload
          |
          v
Lambda result
          |
          v
ResultSelector -> ResultPath
          |
          v
Next state output
~~~

Without controlling data size, state input/output can grow across steps. Step Functions enforces payload size limits on state input/output (commonly 256 KiB per state/execution payload; check current service quotas). For large files or datasets, store content in S3 and pass only the object key, version, and required metadata.

Do not put secrets, access tokens, or unnecessary personal data in execution input, as data can appear in execution history and logs depending on configuration. Use Secrets Manager, Parameter Store, or IAM roles to retrieve secrets when needed.

## 7. Branching with Choice

A Choice state picks the next step based on data. For example, after checking an order, the workflow continues only if `valid` is true.

~~~json
{
  "CheckPayment": {
    "Type": "Choice",
    "Choices": [
      {
        "Variable": "$.payment.status",
        "StringEquals": "SUCCEEDED",
        "Next": "CreateShipment"
      },
      {
        "Variable": "$.payment.status",
        "StringEquals": "PENDING",
        "Next": "WaitForPayment"
      }
    ],
    "Default": "PaymentFailed"
  }
}
~~~

Choice does not execute business logic itself; it only decides the next state. Always define a `Default` branch to handle missing or unmatched values. Otherwise, the workflow may fail when data violates assumptions.

Do not use Choice as a substitute for authorization. A field in the input having `approved=true` does not prove a user was authorized to approve. Results must be produced by an authoritative verification step and stored durably.

## 8. Retry and Catch When Lambda Fails

In distributed systems, Lambda can experience transient errors such as throttling, service unavailability, network timeouts, or dependency failures. Step Functions lets you define `Retry` to retry a Task and `Catch` to transition to an error-handling branch.

~~~json
{
  "ChargePayment": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:charge-payment:prod",
      "Payload.$": "$"
    },
    "Retry": [
      {
        "ErrorEquals": [
          "Lambda.ServiceException",
          "Lambda.AWSLambdaException",
          "Lambda.SdkClientException",
          "Lambda.TooManyRequestsException"
        ],
        "IntervalSeconds": 2,
        "BackoffRate": 2.0,
        "MaxAttempts": 3
      }
    ],
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.taskError",
        "Next": "HandlePaymentError"
      }
    ],
    "End": true
  }
}
~~~

Error names must match errors returned by the integration/runtime. `Retry` is evaluated before `Catch`: Step Functions retries according to policy, and only after exhausting attempts or hitting an unmatched error does it transition to a matching catcher.

Important properties:

- `IntervalSeconds`: wait time before the first retry.
- `BackoffRate`: multiplier increasing wait time between attempts.
- `MaxAttempts`: maximum retry attempts for the retrier definition.
- `MaxDelaySeconds`: upper cap on wait time if supported.
- `JitterStrategy`: adds randomness to backoff if supported.
- `ErrorEquals`: error types to which the policy applies.

Do not retry every error. Validation errors, missing permissions, or invalid business states generally do not resolve on retry. Retry only likely transient errors and cap attempts to avoid retry storms.

### 8.1. Idempotency on Retry

Step Functions may re-invoke a Task according to policy. Lambda might have performed a side effect and then timed out before Step Functions received the result. Retrying without idempotency could charge payment or create an order twice.

For non-idempotent operations:

- Pass `executionId`, `orderId`, or a stable idempotency key.
- Persist the operation result alongside the key in a database.
- Use unique constraints or conditional writes so execution happens only once.
- When receiving the same key again, return the previously recorded result.
- Do not generate a new key on each retry.

Step Functions' Context object can provide the execution ID in ASL. However, one execution can perform multiple business operations; combine the execution ID with a step or resource ID to form a sufficiently granular key.

### 8.2. Catch and Compensation Branches

If inventory was reserved and payment fails, the workflow must call a step to release inventory. This is a compensation action, not an automatic ACID transaction rollback across multiple services.

~~~mermaid
flowchart TD
    A["ReserveInventory"] --> B["ChargePayment"]
    B -->|Succeeded| C["CreateShipment"]
    B -->|Failed| D["ReleaseInventory"]
    D --> E["MarkOrderFailed"]
    C --> F["MarkOrderConfirmed"]
~~~

Compensation steps can also fail. Apply bounded retries, persist state needed for recovery, and route the workflow into manual handling or a recovery process if automatic completion fails.

## 9. Parallel and Map for Concurrent Processing

### 9.1. Parallel State

Parallel runs multiple branches simultaneously. For instance, after creating an order, the system can validate the address and calculate tax independently.

~~~json
{
  "EnrichOrder": {
    "Type": "Parallel",
    "Branches": [
      {
        "StartAt": "ValidateAddress",
        "States": {
          "ValidateAddress": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:validate-address:prod",
              "Payload.$": "$"
            },
            "End": true
          }
        }
      },
      {
        "StartAt": "CalculateTax",
        "States": {
          "CalculateTax": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:calculate-tax:prod",
              "Payload.$": "$"
            },
            "End": true
          }
        }
      }
    ],
    "Next": "ContinueOrder"
  }
}
~~~

Parallel waits for branches to finish per state semantics. If one branch fails, the workflow needs a policy to handle the failure of the entire Parallel state. Do not use Parallel if steps depend on each other's outputs.

### 9.2. Map State

Map iterates over a list of items and runs a sub-state machine or state sequence for each item. For example, processing each item in a batch or each file in a manifest.

Concurrency can be configured to cap how many items run simultaneously. For large datasets, Distributed Map can process data at greater scale and read items from sources such as S3, depending on mode and configuration.

Keep in mind:

- Cap concurrency so downstream databases or external APIs are not overloaded.
- Design each item's processing to be idempotent.
- Define failure behavior when one item fails: fail all, retry, log individual failure, or continue other items.
- Do not pass large payloads per item if only an object key is needed.
- Track succeeded, failed, and retried item counts.

Parallel and Map can rapidly multiply Lambda invocations. Account for total workflow concurrency alongside other callers of the function in the account.

## 10. Waiting for Asynchronous Work with Callback Tokens

Some tasks cannot finish within a single Lambda invocation—such as waiting for partner confirmation, waiting for human approval, or waiting for an external job. Step Functions supports a callback pattern using a task token.

Callback task tokens are a waiting pattern for Standard workflows. Express workflows do not support this callback integration pattern; if confirmation waiting is needed with Express, design another event/queue mechanism compatible with short workflow duration limits.

Lambda callback integration resource typically looks like:

~~~text
arn:aws:states:::lambda:invoke.waitForTaskToken
~~~

Example state:

~~~json
{
  "WaitForApproval": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:request-approval:prod",
      "Payload": {
        "taskToken.$": "$$.Task.Token",
        "order.$": "$"
      }
    },
    "TimeoutSeconds": 86400,
    "Next": "ProcessApproval"
  }
}
~~~

The `request-approval` Lambda receives the task token and order details. The function can persist the approval request, send a notification, and end its invocation. The workflow stays paused until an authorized component calls the Step Functions API to send task success or task failure along with the token.

The token is sensitive data. Do not send the token to browsers or end users. Store and transmit tokens through authenticated backends, restrict read permissions, do not log them, and associate the token with an approval ID. When an approver decides, the callback service verifies identity/permissions, persists the decision, and calls the Step Functions task-completion API.

A task token is valid only for the waiting task and expires or becomes invalid once the workflow ends. Duplicate or late callbacks must be handled safely. A transactional outbox can ensure a saved approval decision is delivered to Step Functions even if the callback service fails midway.

## 11. Standard vs. Express Workflows

Step Functions offers two main workflow types: Standard and Express. Choosing between them impacts runtime duration, execution semantics, observability, and cost.

| Criterion | Standard | Express |
|---|---|---|
| Maximum duration | Can run up to one year | Up to a few minutes (currently 5 minutes) |
| Workload | Long-running processes with waits, approvals, or multi-step orchestration | High-volume, short-lived, high-throughput processing |
| Execution history | Execution history persisted inside Step Functions | Relies more heavily on CloudWatch Logs for detailed observability |
| Delivery semantics | Exactly-once workflow execution in the Standard model; side effects and configured retries still need idempotency | Express has two modes: asynchronous at-least-once and synchronous at-most-once |
| Cost | Primarily per state transition | Primarily per execution and duration/memory |
| Long callbacks/waits | Better suited for long-waiting workflows | Unsuitable for waits exceeding duration limits |

Exactly-once/at-least-once/at-most-once semantics describe workflow execution by type and mode, and do not automatically guarantee that external service side effects happen only once. Whenever retries, ambiguous timeouts, or external callbacks occur, application-layer idempotency remains necessary.

Choose Standard when processes are long-running, involve human approvals, or need execution history and step-by-step recovery. Choose Express when workflows are short, high-frequency, and fit within the duration limit. With Express, choose synchronous or asynchronous mode based on delivery and response needs.

Limits and pricing may vary by service and region. Verify current AWS quotas and pricing before finalizing the architecture.

## 12. Sagas and Compensation for Multi-Service Processes

A multi-step workflow often updates multiple independent systems. There is no single ACID transaction spanning Lambda, DynamoDB, a payment provider, and a shipping system.

A Saga breaks the process into local transactions. Each step may have a compensating action to return business state to an acceptable condition when a later step fails.

Order example:

| Succeeded step | Possible compensation |
|---|---|
| Reserve inventory | Release inventory |
| Authorize payment | Void authorization |
| Capture payment | Refund payment, if business rules permit |
| Create shipment | Cancel shipment if carrier supports it |
| Send notification | Send a corrective notification; an already sent email cannot be recalled |

Compensation does not always cleanly reverse side effects. A sent email cannot be unsent; a refund may take processing time. Therefore, Saga design must define terminal states, audit trails, and exception-handling procedures.

Step Functions can orchestrate both the main flow and compensation branches. Use `Catch` to transition to compensation branches and record step-by-step outcomes. If compensation fails, do not mark the workflow as cleanly rolled back; record a state requiring intervention and trigger an alarm.

## 13. IAM and Workflow Security

There are two critical permission sets:

1. **Step Functions execution role:** permissions the state machine uses to invoke Lambda, write logs, or call other AWS services.
2. **Lambda execution role:** permissions of the function's code when accessing databases, S3, queues, or other services.

The Step Functions execution role should only allow invoking the exact needed functions/versions/aliases. The Lambda execution role should only access business resources that function needs. Do not share one overly broad role across all workflows and functions when responsibilities can be separated.

If Lambda needs to call `SendTaskSuccess`, `SendTaskFailure`, or `SendTaskHeartbeat`, grant the corresponding Step Functions permissions to the callback service. Never let end users call these APIs directly with a task token.

Workflow data may contain customer details, payment references, or internal records. Follow these practices:

- Pass only data needed by the next state.
- Do not put secrets in execution input/output.
- Use Secrets Manager or Parameter Store for credentials.
- Restrict access to execution history and CloudWatch Logs.
- Encrypt data according to organizational requirements.
- Audit start, stop, redrive, and workflow modification actions.
- Do not log task tokens, access tokens, or sensitive data.

## 14. Payload Limits, Timeouts, and Concurrency

Workflow input/output is passed across state transitions. Large payloads increase cost, increase serialization latency, and can exceed Step Functions limits. State input/output payload limits are commonly 256 KiB; confirm current quotas before deploying.

For large files or large datasets:

1. Store the file in S3.
2. Pass the bucket, object key, version ID, and checksum in state data.
3. Have Lambda read data via streaming or batching.
4. Write large outputs back to S3 or a database.
5. Pass only references and metadata to the next state.

Each Lambda Task is also bounded by Lambda's timeout. Step Functions task timeouts must be aligned with the function's maximum duration and business deadlines. If Step Functions times out while Lambda is still executing side effects, retries or error handlers can cause duplicate operations.

Parallel/Map can drive concurrency up sharply. Set concurrency limits on Map when needed, configure reserved concurrency on Lambda to protect dependencies, and bound connection pools. Monitor backlogs, throttling, and wait times to tune accordingly.

## 15. Monitoring Workflows and Troubleshooting

Step Functions provides execution history for Standard workflows and integrates with CloudWatch Logs, metrics, and tracing per configuration. When a workflow fails, identify which state failed, what input was passed, whether the error came from Lambda or a service integration, and how many times the state machine retried.

Metrics to monitor:

- Executions started, succeeded, failed, timed out, and aborted.
- Overall execution duration.
- Duration and retry counts per Task.
- Lambda errors, throttles, duration, and concurrency.
- Number of workflows waiting on callbacks.
- Compensation failures or workflows needing manual intervention.
- Payload sizes and state transition counts.
- Cost by workflow type and run frequency.

Use execution names and correlation IDs to link workflows with Lambda and downstream logs. Avoid logging full state input/output if it contains sensitive data. Configure log levels and data inclusion to balance observability and security.

When rerunning a failed workflow, check whether the state already performed side effects. For Standard workflows, redrive capabilities can help resume from the failed state per supported features and conditions. Redrive does not replace idempotency; verify completed steps and external state before rerunning.

## 16. Deploying State Machines with IaC

Manage state machines and IAM permissions as code so they can be reviewed, versioned, and deployed consistently. Common options include:

- AWS CloudFormation.
- AWS CDK.
- AWS SAM in configurations supporting Step Functions.
- Terraform.
- AWS CLI for controlled deployment or verification operations.

A typical deployment flow:

1. Build and test Java Lambdas.
2. Package artifacts and deploy versions/aliases.
3. Create or update the state machine definition.
4. Configure execution roles with least privilege.
5. Configure logs, tracing, and alarms.
6. Run integration tests with synthetic data.
7. Test retries, timeouts, callbacks, and compensation.
8. Deploy across dev/test/prod environments.
9. Monitor initial executions and verify rollback.

Reference Lambda aliases or version ARNs inside the state machine to control function versioning. If the state machine references `$LATEST`, behavior can change whenever the function updates without any change to the state machine. Pick a release strategy that is traceable and rollback-ready.

## 17. Testing Workflows

A workflow needs more than unit tests on individual Lambdas. Test state transitions and error handling too:

1. Valid input passes through the entire flow.
2. Invalid input follows the rejection branch.
3. Transient Lambda failure retries and succeeds.
4. Persistent Lambda failure triggers Catch into the error branch.
5. Timeout occurs after a side effect has already completed.
6. Two Parallel branches produce expected results and handle errors per policy.
7. Map handles an empty list, a large list, and a single failing item.
8. Callback token is delivered properly and duplicate callbacks arrive.
9. Callback arrives after timeout or after the workflow has already ended.
10. Compensation succeeds and compensation fails.
11. Payloads approach the state input/output size limit.
12. Execution role lacks permissions and fails clearly.
13. Lambda concurrency is throttled.
14. Redrive or rerun does not produce duplicate side effects.

AWS Step Functions Local and state machine testing tools can assist with certain scenarios, but real integration behavior with IAM, Lambda, callbacks, and service quotas must be verified in a test AWS environment.

## 18. Process for Designing a Workflow for Java Lambda

1. **Describe the business process.** Identify steps, conditions, error branches, and terminal states.
2. **Choose orchestration vs. choreography.** Use Step Functions when centralized coordination, waiting, or progress tracking is needed.
3. **Split responsibilities across Lambdas.** Each function implements one step with clear input/output.
4. **Define the state machine.** Use Task, Choice, Parallel, Map, Wait, Succeed, and Fail appropriately.
5. **Design retry and catch.** Classify transient errors, business errors, and unrecoverable errors.
6. **Ensure idempotency.** Every side effect has a stable key and durably stored state.
7. **Design compensation.** Define how to handle failures in later steps.
8. **Choose Standard or Express.** Base on duration, throughput, semantics, and cost.
9. **Bound data and concurrency.** Pass references for large data, cap Map concurrency, and protect dependencies.
10. **Configure IAM and observability.** Least privilege, logs, metrics, tracing, and alarms.
11. **Test failures and deploy.** Simulate retries, timeouts, duplicates, callbacks, and rollbacks.

Step Functions fits when a process has multiple steps needing coordination and clear state. Java Lambda remains where business logic executes; the state machine controls how steps connect, wait, retry, and recover.

## 19. Self-Check Questions

- How does Step Functions differ from one Lambda sequentially calling several other Lambdas?
- What are the responsibilities of a Task state and a Choice state?
- What structure does optimized Lambda integration return to the state machine?
- How do `ResultSelector` and `ResultPath` help control state data?
- Why is idempotency still needed even though Standard workflows have exactly-once semantics?
- When should you use Parallel vs. Map?
- How is a callback task token used to wait for asynchronous work?
- How do Standard and Express differ in duration, semantics, and cost?
- How does Saga compensation differ from a conventional transaction rollback?
- Why should you avoid passing large files or secrets in state input/output?
- How does the Step Functions execution role differ from the Lambda execution role?
- What should be checked before redriving a failed workflow?

AWS Step Functions turns a collection of Java Lambdas into a stateful, observable, and recoverable workflow by definition. Use the state machine to manage control flow, design each Lambda to be idempotent, configure retries by error type, and add compensation for multi-service side effects. When workflows are modeled clearly, systems become much easier to monitor and troubleshoot as traffic grows or a dependency fails.
