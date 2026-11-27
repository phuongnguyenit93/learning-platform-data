# Callback task tokens and Saga design on AWS

In an e-commerce system, an order may need to reserve inventory, authorize payment, wait for risk-staff approval, create a shipment, and send notifications. These actions happen across disparate services such as **AWS Lambda, Amazon ECS, Amazon RDS, DynamoDB, SQS**, or external payment gateways—they do not share a single database transaction. If an earlier step commits and a later step fails, the system cannot assume all changes roll back atomically.

**AWS Step Functions** lets you model these steps as a **state machine**. When work must wait for an external reply, a **callback task token** pauses the state machine at a Task until a worker calls `SendTaskSuccess` or `SendTaskFailure` with the active token. Combining callbacks with the **saga pattern** coordinates **local transactions**, retries, timeouts, and **compensating transactions** to restore business consistency in a controlled way.

This lesson belongs to the **Events and Orchestration** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects Region/AZ, IAM, VPC, Lambda/ECS, SQS/SNS, EventBridge, DynamoDB/RDS, and CloudWatch with AWS requirements for service selection, security, monitoring, resilience, and cost control.

> **Three distinct concepts:** Callback tokens solve **when a Task resumes**; sagas solve **what must be compensated when a transaction sequence cannot complete**; business idempotency keys prevent **effects from executing twice** when requests, callbacks, or workflows are retried.

## 1. Learning objectives

After this lesson, learners will be able to:

1. Distinguish **request-response**, **Run a Job (`.sync`)**, and **Wait for Callback (`.waitForTaskToken`)**.
2. Explain why callback tokens are supported only on **Step Functions Standard Workflows**, not Express Workflows.
3. Access task tokens via `$$.Task.Token` (JSONPath) or `$states.context.Task.Token` (JSONata).
4. Write a Task sending an SQS message with a token and handle outcomes using `ResultPath`, `Choice`, `Retry`, and `Catch`.
5. Call `SendTaskSuccess`, `SendTaskFailure`, and `SendTaskHeartbeat` from AWS SDK for Java 2.x.
6. Understand the **same AWS account** callback restriction, `states:SendTask*` IAM permissions, and token security.
7. Distinguish overall Task timeouts from heartbeat timeouts, and handle expired tokens or late callbacks.
8. Design a saga with forward steps, compensations, state machines, and unknown-outcome handling.
9. Implement idempotency/outbox/inbox patterns to prevent double charges and double reservations during retries/redrives.
10. Compare Step Functions orchestration with EventBridge/SNS choreography.
11. Design human approvals via API Gateway/Lambda without exposing raw tokens.
12. Troubleshoot faults and design monitoring, DLQs, redrives, SLAs, and cost controls.

## 2. Step Functions architecture coordinating services

~~~mermaid
flowchart LR
    API["API Gateway / Order API"] --> SF["Step Functions Standard saga"]
    SF --> INV["Reserve inventory"]
    INV --> PAY["Authorize payment"]
    PAY --> WAIT["Wait for approval token"]
    WAIT --> Q["SQS approval request"]
    Q --> W["Worker / Human approval"]
    W -->|"SendTaskSuccess/Failure"| WAIT
    WAIT --> CONF["Confirm order"]
    CONF --> E["EventBridge OrderConfirmed"]
    WAIT -->|"Declined/Timeout"| COMP["Compensation"]
    COMP --> R["Void payment / Release inventory"]
~~~

Step Functions orchestrates; it **does not create a shared ACID transaction** across RDS, payment gateways, and inventory. Services must still enforce business invariants, idempotency, authentication, logging, retries, and reconciliation.

A flow might unfold like this:

~~~text
09:00:00  ReserveInventory: OK
09:00:04  AuthorizePayment: OK
09:00:05  SQS queues risk-review request; workflow pauses
09:27:41  Staff approves; worker calls SendTaskSuccess
09:27:42  ConfirmOrder: OK
09:27:43  EventBridge emits OrderConfirmed
~~~

There is no need to keep a Lambda invocation running for 27 minutes. Step Functions Standard persists state while awaiting the callback and resumes only upon a valid decision or timeout.

## 3. Three service integration patterns

| Pattern | When is the step considered complete? | Example | Workflow |
|---|---|---|---|
| **Request Response** | Service/API returns response | `arn:aws:states:::lambda:invoke` | Standard and Express where supported |
| **Run a Job `.sync`** | Integrated job finishes | ECS/Fargate/Batch/Glue with `.sync` where supported | **Standard** |
| **Wait for Callback `.waitForTaskToken`** | Worker sends token with `SendTaskSuccess`/`Failure` | SQS → worker, human approval, external job | **Standard** |

Not every AWS service action supports all three patterns. **Callbacks exist only on integrations that have a place to pass the token** in requests/payloads/headers. Always consult AWS's integration support matrix rather than appending `.waitForTaskToken` blindly to any Resource ARN.

### 3.1. Standard or Express?

| Aspect | Standard Workflows | Express Workflows |
|---|---|---|
| Callback token | **Yes** | **No** |
| `.sync` integration | Yes on supported services | No |
| Max execution duration | **1 year** | **5 minutes** |
| Billing | **State transitions** | Execution count, duration, memory |
| Best suited for | Long sagas, human approvals, multi-service audits | High-volume, short-lived, event transforms |

The **1-year** limit is a service quota, **not** a reasonable approval timeout. Without an explicit deadline, executions can stay stuck indefinitely.

### 3.2. Callbacks vs. `Wait` state and Activities

- `Wait` state advances after seconds or a timestamp, requiring no actor callback.
- `.waitForTaskToken` pauses at the Task until a valid callback arrives or it times out.
- `.sync` waits on a state-managed job integration without requiring workers to send callbacks manually.
- **Step Functions Activities** use `GetActivityTask` polling and also carry task tokens, differing from a Task proactively calling `sqs:sendMessage.waitForTaskToken`.

If a job takes an hour, never sleep a Lambda until completion; use callbacks, `.sync`, or event-driven workflows depending on the service.

## 4. Task token lifecycle

Step Functions issues a **unique token per waiting Task attempt**. The workflow injects the token into an SQS message or integration request. The worker picks up the job and sends a callback when finished.

~~~mermaid
sequenceDiagram
    participant SF as Step Functions Standard
    participant Q as SQS queue
    participant W as Java/ECS worker
    participant DB as Business database
    SF->>Q: SendMessage {orderId,taskToken}
    Note over SF: Paused at Task
    W->>Q: ReceiveMessage
    Q-->>W: Payload + token
    W->>DB: Business update, commit
    DB-->>W: OK
    W->>SF: SendTaskSuccess(token, output JSON)
    SF-->>W: API response
    W->>Q: DeleteMessage after processing
    SF->>SF: Merge callback output, advance to Next state
~~~

| Value | Purpose |
|---|---|
| `stateMachineArn` | Identifies the state machine definition |
| `executionArn` | Identifies a single saga execution |
| **`taskToken`** | Authorizes completing **one waiting Task attempt** |
| `sagaId`/`orderId` | Business and audit identifier |
| **`operationId`** | Guards against retrying business side effects |
| `eventId` | Deduplicates consumers when events republish/redeliver |
| `receiptHandle` | Identifies one SQS receive for deleting/changing visibility |

**Never use a task token as an idempotency key or saga ID.** Retrying or redriving a Task generates a new token, whereas the business `orderId` and operation stay the same.

### 4.1. AWS account restriction

AWS documentation specifies that task tokens must be called back by an **IAM principal in the same AWS account** as the execution. A worker in Account B using B's credentials **cannot directly** submit a token for a Step Functions execution in Account A.

In multi-account organizations, the worker can **assume an authorized role in Account A** via STS and invoke the callback as A's principal, or call an authenticated **callback bridge** inside Account A. IAM policies, token distribution, business approvals, and networking must still be governed.

### 4.2. Old tokens cannot replace new tokens

A token is bound to a single wait attempt. Once the Task succeeds/fails, times out, the workflow stops, or the Task re-runs via retry/redrive, the old token cannot complete the new wait. AWS issues a new token when retrying a timed-out Task. Never pull a token from historical executions to complete a new Task.

## 5. SQS callback state machine with JSONPath

Example **Standard Workflow** sending an order approval request to SQS Standard queue `order-approvals`, preserving state input and awaiting a decision. Queue/account/Region are illustrative.

~~~json
{
  "Comment": "Callback approval on a Standard workflow",
  "StartAt": "RequestApproval",
  "States": {
    "RequestApproval": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
      "Parameters": {
        "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals",
        "MessageBody": {
          "orderId.$": "$.orderId",
          "taskToken.$": "$$.Task.Token"
        }
      },
      "TimeoutSeconds": 86400,
      "ResultPath": "$.approval",
      "Catch": [
        {
          "ErrorEquals": ["States.Timeout"],
          "ResultPath": "$.approvalError",
          "Next": "ApprovalUnavailable"
        },
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.approvalError",
          "Next": "ApprovalUnavailable"
        }
      ],
      "Next": "ChooseApproval"
    },
    "ChooseApproval": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.approval.approved",
          "BooleanEquals": true,
          "Next": "Approved"
        }
      ],
      "Default": "ApprovalUnavailable"
    },
    "Approved": {
      "Type": "Succeed"
    },
    "ApprovalUnavailable": {
      "Type": "Fail",
      "Error": "ApprovalDeclinedOrExpired",
      "Cause": "Approval declined, failed or timed out"
    }
  }
}
~~~

Prerequisites to run for real: valid queue URL, state machine execution role with `sqs:SendMessage`, worker with callback IAM permissions, input containing `orderId`, same-account token caller, and approval logic.

### 5.1. Understanding Context syntax

- `"taskToken.$": "$$.Task.Token"` reads the token from the **Step Functions Context object**, not a literal string.
- `"orderId.$": "$.orderId"` reads from input.
- `"ResultPath": "$.approval"` keeps input intact and attaches callback JSON output at `approval`.
- `"TimeoutSeconds": 86400` sets a **24-hour** limit.
- `Catch` handles Task errors; `States.ALL` does not catch every terminal error, such as `States.Runtime`/`States.DataLimitExceeded`.

Without `ResultPath`, the task result **overwrites input** (default `$`), causing downstream states to lose `orderId`.

### 5.2. Same Task using JSONata

With `QueryLanguage: JSONata`, use `Arguments` and Context expression `$states.context.Task.Token` instead of JSONPath `Parameters` and `.$`:

~~~json
{
  "Type": "Task",
  "QueryLanguage": "JSONata",
  "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
  "Arguments": {
    "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals",
    "MessageBody": {
      "orderId": "{% $states.input.orderId %}",
      "taskToken": "{% $states.context.Task.Token %}"
    }
  },
  "TimeoutSeconds": 86400,
  "End": true
}
~~~

This is a **Task fragment**, not a complete state machine. Never mix JSONPath `ResultPath` casually with JSONata `Output`/`Assign`.

### 5.3. Callback output

The worker can submit JSON output like:

~~~json
{
  "approved": true,
  "decisionId": "dec-101",
  "reviewedBy": "risk-team"
}
~~~

**`SendTaskSuccess.output` must be a valid JSON string**, not an unserialized object and not an unquoted string `APPROVED`. Output size limit is **256 KiB UTF-8**, matching Step Functions task/state payload limits. Never embed large files or raw PII in callbacks; store them in S3 and return a key/URI when needed.

## 6. Callback APIs, timeouts, and heartbeats

| API | Meaning |
|---|---|
| `SendTaskSuccess` | Completes the Task successfully, advancing with JSON output |
| `SendTaskFailure` | Reports `error`/`cause`, triggering `Retry`/`Catch` if configured |
| `SendTaskHeartbeat` | Resets the **heartbeat clock**, does not finish the Task |
| `DescribeExecution` | Read-only execution status check; does not replace callbacks |
| `StopExecution` | Terminates the workflow; old tokens can no longer resume it |
| `RedriveExecution` | Re-runs failed step of an eligible Standard execution; may issue a new token |

### 6.1. Two types of clocks

`TimeoutSeconds` is the **total limit** for the Task. `HeartbeatSeconds` limits how long the Task can go without a worker heartbeat. **`SendTaskHeartbeat` only resets the heartbeat clock; it does not extend total `TimeoutSeconds`.**

For multi-hour human approvals, enforce deadlines via `TimeoutSeconds` and reminders—humans do not need continuous heartbeats.

For a long job running on ECS, set for example:

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
  "Parameters": {
    "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/long-jobs",
    "MessageBody": {
      "jobId.$": "$.jobId",
      "taskToken.$": "$$.Task.Token"
    }
  },
  "HeartbeatSeconds": 120,
  "TimeoutSeconds": 3600,
  "End": true
}
~~~

This Task fragment configures a 2-minute heartbeat and a 1-hour total limit. The worker sends `SendTaskHeartbeat` before 120 seconds elapse. If the worker dies, the Task fails early with `States.Timeout`. Even with continuous heartbeats, the Task still expires after one hour.

### 6.2. Token errors

| Error | Common explanation |
|---|---|
| `InvalidToken` | Malformed, wrong, modified, or truncated token |
| `TaskTimedOut` | Token expired or Task already closed |
| `TaskDoesNotExist` | Task no longer exists in API context |
| `AccessDenied` | IAM principal lacks `states:SendTask*` or wrong account |
| `InvalidOutput` | `SendTaskSuccess.output` is not valid JSON |
| `KmsAccessDeniedException` | Insufficient KMS key policy/caller permissions when execution is encrypted as configured |

If the worker **committed the business operation** yet the callback returned `TaskTimedOut`, never assume the business operation rolled back. Reconcile the actual outcome before retrying or compensating.

## 7. SQS workers: two independent ACKs

In an SQS → worker → Step Functions flow, there are **two acknowledgments**:

1. `SendTaskSuccess`/`Failure` completes the **Step Functions Task**.
2. `DeleteMessage` completes **SQS message consumption**.

If `SendTaskSuccess` succeeds and the worker crashes before `DeleteMessage`, SQS may redeliver the message. Retrying the callback with the old token makes Step Functions reject it as closed. **Consumers must be idempotent by business operation ID**, never executing the business effect twice.

If the callback HTTP response is lost, the worker **does not know for certain** whether Step Functions received it. Persist callback outcome/correlation, handle closed-token errors, and reconcile ambiguous states.

### 7.1. Visibility timeout, DLQ, and expired tokens

SQS `ReceiveMessage` only hides the message temporarily—it does not delete it. If visibility timeout expires before `DeleteMessage`, the message reappears; that is normal behavior, not a service bug. Workers can extend it with `ChangeMessageVisibility` during long work.

If a message lands in the DLQ before calling back, Step Functions waits until task timeout. When redriving from the DLQ later, the token may already have expired. **Never** submit an expired token for a new execution; reconcile `orderId`/`operationId` against active Task attempts.

## 8. Calling callbacks with AWS SDK for Java 2.x

Use `software.amazon.awssdk:sfn`, an IAM role in the state machine's account, and the SDK credentials provider chain. The snippets below are API examples—**they will not run without an authorized active token**.

### 8.1. `SendTaskSuccess`

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.SendTaskSuccessRequest;

public final class ApproveTask {
    public static void approve(SfnClient sfn, String taskToken, String decisionId) {
        // Serialize response objects with Jackson ObjectMapper in production.
        String safeId = decisionId.replaceAll("[^a-zA-Z0-9_-]", "");
        String output = "{\"approved\":true,\"decisionId\":\"" + safeId + "\"}";
        sfn.sendTaskSuccess(SendTaskSuccessRequest.builder()
                .taskToken(taskToken)
                .output(output)
                .build());
    }
}
~~~

Never put `taskToken` into logs/exceptions or build JSON by concatenating unvalidated input. In production, use Jackson to serialize outputs with a fixed schema. Configure `SfnClient` in the execution's Region.

### 8.2. `SendTaskFailure`

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.SendTaskFailureRequest;

public final class RejectTask {
    public static void reject(SfnClient sfn, String taskToken) {
        sfn.sendTaskFailure(SendTaskFailureRequest.builder()
                .taskToken(taskToken)
                .error("ApprovalRejected")
                .cause("Rejected by authorized reviewer")
                .build());
    }
}
~~~

`error` is a machine-readable code for `Catch`; `cause` must exclude PII and tokens. For business rejections, you can alternatively call `SendTaskSuccess` with `{"approved":false}` and branch with `Choice`.

### 8.3. `SendTaskHeartbeat`

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.SendTaskHeartbeatRequest;

public final class WorkerHeartbeat {
    public static void ping(SfnClient sfn, String token) {
        sfn.sendTaskHeartbeat(SendTaskHeartbeatRequest.builder()
                .taskToken(token)
                .build());
    }
}
~~~

Heartbeats belong to workers actively making progress—never run an unbounded heartbeat loop masking a dead job. Stop the heartbeat scheduler as soon as the Task finishes.

## 9. IAM permissions and protecting tokens

### 9.1. State machine execution role

For `sqs:sendMessage.waitForTaskToken`, the Step Functions execution role needs `sqs:SendMessage` on the exact queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SubmitApprovalRequest",
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:order-approvals"
    }
  ]
}
~~~

The execution role trusts `states.amazonaws.com`. Add `lambda:InvokeFunction` and other resource permissions as called by the state machine; never grant `AdministratorAccess`.

### 9.2. Worker callback IAM role

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CallbackOnly",
      "Effect": "Allow",
      "Action": [
        "states:SendTaskSuccess",
        "states:SendTaskFailure",
        "states:SendTaskHeartbeat"
      ],
      "Resource": "*"
    }
  ]
}
~~~

**Why `Resource:"*"`?** The AWS Service Authorization Reference notes that `states:SendTask*` actions **do not support resource-level permissions**. Consequently, **token distribution itself is a critical security boundary**: anyone holding a token and a callback IAM role can complete that task. Lock down callback roles, endpoints, token stores, and environments permitted to read messages.

Workers polling SQS also need `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`, and `sqs:ChangeMessageVisibility` on the specific queue ARN, kept separate from callback permissions.

### 9.3. Tokens are sensitive data

- Never write tokens to CloudWatch logs, trace spans, URL query parameters, Slack/email, or dashboards.
- Encrypt SQS messages at rest (SSE-SQS/SSE-KMS as required), enforce TLS in transit, and restrict queue/KMS key policies.
- Protect read access to `GetExecutionHistory`/`DescribeExecution` and CloudWatch Logs since execution data can incidentally hold tokens.
- Use a callback bridge/authentication instead of handing raw tokens to approvers.
- Set reasonable `TimeoutSeconds`, one-time `approvalId`s, and verify business state/version before calling back.

### 9.4. Private networking

ECS/EC2 workers in private subnets without NAT can use AWS PrivateLink Interface Endpoints:

~~~text
com.amazonaws.ap-southeast-1.sqs
com.amazonaws.ap-southeast-1.states
~~~

`sqs` lets workers poll/delete; `states` handles `SendTaskSuccess`/`Failure`/`Heartbeat`. Verify endpoint Security Group inbound TCP 443, Private DNS, routes/NACLs, IAM, and endpoint policies. `Step Functions → SQS` via service integration does not require deploying a VPC Link or placing Step Functions inside a private subnet.

## 10. Saga pattern: local transactions and compensations

A saga splits a business transaction into independent steps:

~~~text
T1 ReserveInventory
T2 AuthorizePayment
T3 WaitRiskApproval
T4 ConfirmOrder
~~~

If T3 is rejected, run compensations **in reverse order**:

~~~text
C2 VoidPaymentAuthorization
C1 ReleaseInventoryReservation
~~~

**Compensation is not a distributed ACID database rollback.** A captured payment may need a **refund** rather than a void; a sent email cannot be unsent; a dispatched shipment cannot be "rolled back" like a SQL transaction.

### 10.1. Saga orchestration vs. choreography

| Criterion | **Orchestration: Step Functions** | **Choreography: EventBridge/SNS/SQS** |
|---|---|---|
| Who decides the next step? | Centralized state machine | Each subscriber reacting to events |
| Observability | Execution graph/history | Distributed correlation/tracing across services |
| Retry/Catch | Declarative ASL | Each consumer implements own retry/DLQ |
| Compensation | Explicit compensation branches | Compensation events handled by subscribing services |
| Coupling | Orchestrator knows steps/targets | Services depend on event contracts |
| Best fit | Approvals, sequential sagas, complex rollbacks | Fan-out, independent reactions |

Many systems use **Step Functions for the core order saga** and **EventBridge for post-confirmation effects** (emails, analytics, loyalty). Never let an email outage unnecessarily cancel a completed payment.

### 10.2. Saga vs. 2PC

**Two-phase commit** coordinates participants to commit atomically, often holding resource locks or prepared states for extended durations. A **Saga** never holds DB locks during a 30-minute human review; it embraces **eventual consistency** and uses compensations. In return, you need business invariants, idempotency, intermediate statuses, and reconciliation.

## 11. Designing an order saga step by step

Business example with four primary actions:

~~~mermaid
flowchart TD
    START["Order PENDING"] --> INV["T1 ReserveInventory"]
    INV -->|"OK"| PAY["T2 AuthorizePayment"]
    INV -->|"Outcome unknown"| RECON["Reconcile / manual"]
    PAY -->|"OK"| APP["T3 WaitRiskApproval"]
    PAY -->|"Outcome unknown"| RECON
    APP -->|"Approved"| CONF["T4 ConfirmOrder"]
    APP -->|"Denied / Timeout"| VOID["C2 VoidAuthorization"]
    VOID --> REL["C1 ReleaseInventory"]
    REL --> CANCEL["Order CANCELLED"]
    CONF -->|"OK"| DONE["Order CONFIRMED"]
    CONF -->|"Outcome unknown"| RECON
~~~

| Forward action | Durable effect | Stable operation key | Compensation |
|---|---|---|---|
| `ReserveInventory` | Creates reservation for order | `orderId:reserve:1` | `ReleaseInventory(reservationId)` |
| `AuthorizePayment` | Creates payment authorization | `orderId:auth:1` | `VoidAuthorization(authId)` |
| `WaitRiskApproval` | Creates approval request | `orderId:approval:1` | Expire/close approval |
| `ConfirmOrder` | Persists confirmed status | `orderId:confirm:1` | Cancel/correction if allowed |
| `PublishOrderConfirmed` | Emits event downstream | `eventId` | Cannot retract event; emit correction |

**Local transactions** can commit independently. Compensations cannot "roll back" every external effect: captured funds may need refunds; emails cannot be unsent. Critically, **a timeout does not prove a local transaction failed**; verify outcomes before compensating.

### 11.1. Business state transitions

~~~text
PENDING
INVENTORY_RESERVED
PAYMENT_AUTHORIZED
AWAITING_APPROVAL
CONFIRMED
COMPENSATING
CANCELLED
RECONCILIATION_REQUIRED
~~~

Store `sagaId`/`orderId`, current business status, operation IDs, reservation/auth references, versions, timestamps, and compensation outcomes in business data. Step Functions execution history aids operations, yet **never replaces a financial or inventory ledger**.

### 11.2. Compensation order and boundaries

Compensations usually run in reverse order of succeeded steps: **void authorization → release inventory**. However, if payment was already captured, voiding no longer applies—a refund is needed, which can take days and fail. Compensations must have **retries, their own idempotency keys, a `COMPENSATION_PENDING` state, and an owner**.

## 12. Standard state machine: a minimal saga with callbacks

This example focuses on **`ReserveInventory → WaitForApproval → ConfirmOrder`**, branching to **`ReleaseInventory`** on rejection or timeout. We intentionally **omit the payment step** from this ASL because payment APIs/compensations require outcome-lookup capabilities before automating in production.

~~~json
{
  "Comment": "Minimal saga: reserve, await approval, confirm or release",
  "StartAt": "ReserveInventory",
  "States": {
    "ReserveInventory": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ReserveInventory",
        "Payload": {
          "orderId.$": "$.orderId",
          "operationId.$": "$.reserveOperationId"
        }
      },
      "ResultSelector": {
        "reservationId.$": "$.Payload.reservationId"
      },
      "ResultPath": "$.reservation",
      "Retry": [
        {
          "ErrorEquals": [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.reserveError",
          "Next": "NeedsReconciliation"
        }
      ],
      "Next": "WaitForApproval"
    },
    "WaitForApproval": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
      "Parameters": {
        "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals",
        "MessageBody": {
          "orderId.$": "$.orderId",
          "reservationId.$": "$.reservation.reservationId",
          "taskToken.$": "$$.Task.Token"
        }
      },
      "TimeoutSeconds": 86400,
      "ResultPath": "$.approval",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.approvalError",
          "Next": "ReleaseInventory"
        }
      ],
      "Next": "ApprovalDecision"
    },
    "ApprovalDecision": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.approval.approved",
          "BooleanEquals": true,
          "Next": "ConfirmOrder"
        }
      ],
      "Default": "ReleaseInventory"
    },
    "ConfirmOrder": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ConfirmOrder",
        "Payload": {
          "orderId.$": "$.orderId",
          "reservationId.$": "$.reservation.reservationId",
          "operationId.$": "$.confirmOperationId"
        }
      },
      "ResultPath": "$.confirmation",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.confirmError",
          "Next": "NeedsReconciliation"
        }
      ],
      "Next": "SagaSucceeded"
    },
    "ReleaseInventory": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ReleaseInventory",
        "Payload": {
          "orderId.$": "$.orderId",
          "reservationId.$": "$.reservation.reservationId",
          "operationId.$": "$.releaseOperationId"
        }
      },
      "ResultPath": null,
      "Retry": [
        {
          "ErrorEquals": [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ],
          "IntervalSeconds": 2,
          "MaxAttempts": 4,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.compensationError",
          "Next": "NeedsReconciliation"
        }
      ],
      "Next": "SagaCancelled"
    },
    "SagaSucceeded": {
      "Type": "Succeed"
    },
    "SagaCancelled": {
      "Type": "Fail",
      "Error": "BusinessOrderCancelled",
      "Cause": "Inventory released after decline or timeout"
    },
    "NeedsReconciliation": {
      "Type": "Fail",
      "Error": "ManualReconciliationRequired",
      "Cause": "Task or compensation outcome could not be confirmed"
    }
  }
}
~~~

### 12.1. Explaining key points

- `ReserveInventory` uses the optimized Lambda integration, extracting `reservationId` from `Payload` via `ResultSelector` and keeping `orderId` via `ResultPath`.
- `WaitForApproval` uses a callback token with a 24-hour timeout, storing output at `$.approval`.
- Output `{"approved":true}` routes `Choice` to `ConfirmOrder`. Rejection or timeout routes to `ReleaseInventory`.
- `ReleaseInventory` retries transient faults. If compensation fails, execution routes to `NeedsReconciliation`.
- `ConfirmOrder` failing does not auto-release stock because the DB may have committed right before Lambda timed out.
- `SagaCancelled` ends orchestration as a **failure**, while applications update business order status/audits per their own processes.

### 12.2. Required input

~~~json
{
  "orderId": "ord-101",
  "reserveOperationId": "ord-101:reserve:1",
  "confirmOperationId": "ord-101:confirm:1",
  "releaseOperationId": "ord-101:release:1"
}
~~~

This example is for **analyzing ASL structure**, not a deploy-ready stack: you still need actual Lambda functions, SQS queue, role permissions, IAM/KMS, application code, schema agreements, concurrency limits, and monitoring. Auto-releasing assumes the approval worker **performed no irreversible side effects itself**; if it charged or shipped, check state before compensating.

## 13. Idempotency: task tokens are not enough to prevent duplicate business effects

| Key | Who creates it? | Used for |
|---|---|---|
| `taskToken` | Step Functions per Task attempt | Resuming the exact waiting Task |
| `operationId` | Application, deterministic per order/step | Preventing duplicate reservations/payments/compensations |
| `eventId` | Producer/outbox | Preventing downstream duplicate events |
| `sagaId` | Application | Correlating operations |

If Step Functions retries `ReserveInventory`, Lambda runs twice. Business operations must be **idempotent on `operationId`**. Even when `taskToken` changes after timeout/redrive, `operationId` stays constant because the business operation is the same.

### 13.1. Transactional operation log

~~~sql
CREATE TABLE operation_log (
  operation_id VARCHAR(160) PRIMARY KEY,
  order_id VARCHAR(100) NOT NULL,
  operation_type VARCHAR(80) NOT NULL,
  outcome_json JSONB,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inventory_reservations (
  reservation_id VARCHAR(100) PRIMARY KEY,
  order_id VARCHAR(100) UNIQUE NOT NULL,
  status VARCHAR(30) NOT NULL
);
~~~

Within the **same PostgreSQL transaction**:

1. Check/insert `operationId` backed by a **unique constraint**.
2. If already completed, return the stored outcome without repeating side effects.
3. If new, execute the reservation/update and store the outcome **atomically**.
4. Commit before reporting success to Step Functions/callbacks.

Never do `SELECT processed` then `INSERT`: two concurrent requests can both see no row. Use unique constraints/locks. For `IN_PROGRESS`/`UNKNOWN` operations, use leases/outcome checks rather than returning fake success.

### 13.2. DynamoDB or external payments

With DynamoDB, use `TransactWriteItems` to write the dedup marker and business item in one transaction using `attribute_not_exists(pk)`. If the business update lives in RDS or an external payment gateway, a DynamoDB marker is **not atomic** with that side effect.

Payment gateways should receive a stable **provider idempotency key** such as `orderId:authorize:attempt1`. If a request times out after the provider charged, never retry with a new key—query the outcome and reconcile. Refunds/voids need their own idempotency keys too.

## 14. Transactional outbox, inbox, and EventBridge

### 14.1. Producer outbox

If Order Service commits to the DB and then publishes `OrderConfirmed`:

~~~text
DB COMMIT succeeds
Process crashes before EventBridge PutEvents
→ Order confirmed, yet subscribers never receive the event
~~~

Use a **transactional outbox**: in the same local transaction, update the order and insert `outbox_events(eventId, orderId, version, payload)`. A relay/CDC publishes to EventBridge/SNS/SQS. Because relays may republish on lost ACKs, downstream consumers still need **inbox idempotency**.

~~~mermaid
flowchart LR
    API["Order API"] --> TX["PostgreSQL transaction"]
    TX --> ORD["orders"]
    TX --> OUT["outbox_events"]
    OUT --> REL["Relay/CDC"]
    REL --> BUS["EventBridge"]
    BUS --> CON["Idempotent consumers"]
~~~

### 14.2. Consumer inbox

Consumers use unique key **`(consumerName,eventId)`** and persist the processed marker **in the same transaction** as business writes. On redelivery, detect the duplicate and no-op. An inbox is not atomic with an external payment gateway; use provider idempotency keys and reconciliation.

### 14.3. Orchestration + choreography

An order saga with approvals and explicit compensations belongs in Step Functions. Once `CONFIRMED`, the outbox emits events so subscribers like notifications, analytics, and loyalty run via independent choreography. Never cancel a completed payment merely because the email service hiccuped.

## 15. Compensations must be idempotent and have dedicated states

| Forward effect | Compensation | Safeguard |
|---|---|---|
| Inventory `RESERVED` | Release | Transition `RESERVED → RELEASED` once only |
| Payment `AUTHORIZED` | Void | Confirm authorization is not yet `CAPTURED` |
| Payment `CAPTURED` | Refund | Preserve history; reconcile fees |
| Shipment `CREATED` | Cancel | Only if carrier has not picked up |
| Email sent | Correction | Cannot unsend |
| AWS resource created | Delete owned resource | Ownership tags; never delete shared resources |

### 15.1. Failed compensations are not successes either

~~~text
sagaId              = saga-ord-101
businessStatus      = COMPENSATION_PENDING
compensationStep    = VOID_PAYMENT
lastError           = ProviderUnavailable
nextRetryAt         = ...
owner               = payments-ops
~~~

Retry with backoff/jitter; if exhausted, alert and escalate manually. Do not proceed to subsequent compensation steps if business policy requires waiting for the payment refund to settle.

## 16. `Retry`, `Catch`, and race conditions

### 16.1. Retry transient faults, `Catch` uncertain outcomes

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ReserveInventory",
    "Payload.$": "$"
  },
  "Retry": [
    {
      "ErrorEquals": [
        "Lambda.ServiceException",
        "Lambda.SdkClientException",
        "Lambda.TooManyRequestsException"
      ],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2,
      "JitterStrategy": "FULL"
    }
  ],
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "ResultPath": "$.error",
      "Next": "NeedsReconciliation"
    }
  ],
  "Next": "NextBusinessStep"
}
~~~

This is a **Task fragment**; referenced `Next` states must exist in the workflow. Step Functions evaluates **`Retry` before `Catch`**. `States.TaskFailed` does not match `States.Timeout`; `States.ALL` does not catch terminal errors like `States.Runtime`. Configure `MaxAttempts`, backoff, and jitter to avoid retry storms, backed by stable idempotency keys.

### 16.2. Late callback after timeout

~~~text
10:00:00  Task waiting on token T1
10:30:00  Task times out; saga enters compensation
10:30:02  Staff approves, sends SendTaskSuccess(T1)
10:30:03  Step Functions returns TaskTimedOut / InvalidToken
10:30:10  Inventory released
~~~

**The approval service should only record decisions and call back**, never ship orders or charge cards before the saga confirms status. When user cancel and staff approve race, enforce optimistic versioning/conditional writes on the order so only one transition out of `PENDING_APPROVAL` wins.

### 16.3. Lost callback ACK

The worker submits a callback, Step Functions accepts it, yet the worker loses the HTTP ACK. Retrying with `T1` returns `TaskTimedOut` because the Task already closed. The worker must not invent another token or re-run payments; check callback status/`decisionId`/execution status and business state.

### 16.4. Local operation times out after commit

If Lambda updates the DB and times out returning its response, Step Functions does not know the local write committed. **Never blindly release/void.** Query the operation log by stable `operationId`; if still unknown, set `RECONCILIATION_REQUIRED`, alert the owner, and halt actions that widen impact.

## 17. Human approvals via API Gateway and a callback bridge

**Never expose raw task tokens in emails or URLs.** A task token combined with a callback-permitted IAM principal can complete the pending Task. A safer design issues an **opaque approval ID** while keeping the token inside a protected store.

~~~mermaid
flowchart TD
    SF["Step Functions: waitForTaskToken"] --> Q["SQS {orderId, token}"]
    Q --> W["Approval worker"]
    W --> DB["DynamoDB: approvalId → encrypted token / status / expiry"]
    W --> NOTICE["Notification: signed short-lived approval link"]
    NOTICE --> HUMAN["Human reviewer"]
    HUMAN --> AUTH["API Gateway + JWT/Cognito/IAM auth"]
    AUTH --> BRIDGE["Lambda callback bridge"]
    BRIDGE --> DB
    BRIDGE -->|"SendTaskSuccess/Failure from same-account role"| SF
~~~

### 17.1. What must the callback bridge verify?

1. **The reviewer** is properly authenticated, not merely possessing a URL.
2. The reviewer's role/permissions authorize approving this `orderId`/tenant/amount.
3. `approvalId` is valid, unexpired, and unused.
4. The business order is still `AWAITING_APPROVAL` at the expected version.
5. The decision is persisted durably with a unique `decisionId`.
6. Competing reject/approve calls are serialized with **conditional writes** so only one wins.
7. The worker retrieves the active token from the store and calls back using a same-account IAM role.

### 17.2. Approval decision and callback are not atomic

A DynamoDB conditional write from `PENDING` → `APPROVED` may succeed while Lambda crashes before `SendTaskSuccess`. Conversely, the callback may succeed while the response drops, leaving the DB without `CALLBACK_SENT`. Track states:

~~~text
PENDING
DECISION_RECORDED
CALLBACK_SENT
CALLBACK_UNKNOWN
EXPIRED
RECONCILIATION_REQUIRED
~~~

A retry/reconcile job determines which decisions were called back and whether the execution is still waiting. **Never mark an order `CONFIRMED` solely because a reviewer clicked Approve**; Step Functions still must execute `ConfirmOrder` under business guardrails.

### 17.3. Tokens, encryption, and networking

Store tokens in encrypted DynamoDB/S3 records with least-privilege IAM and sensible TTLs; TTL cleanup is not authorization—always check `expiresAt` at request time. Keep tokens out of access logs, emails, and analytics. Protect API Gateway with authentication and WAF/rate limits per your threat model. A callback Lambda inside a VPC private subnet needs network reachability to the `states` endpoint, though Step Functions itself is not a container inside the customer VPC.

## 18. Redriving Standard executions, retry counters, and new tokens

**`RedriveExecution`** resumes **Standard** executions in `FAILED`, `TIMED_OUT`, or `ABORTED` states within the eligibility window (AWS currently specifies **14 days after execution ends**, plus other quotas).

- Redrive resumes from the **failed step** and **preserves outputs/history of previously succeeded steps** instead of restarting from scratch by default.
- When redriving a `Task`/`Parallel`/Inline `Map` with `Retry`, **retry counts reset to 0** for that redrive.
- A re-run callback Task may receive a **new task token**. Old messages carrying the expired token cannot complete the new Task.
- A local action may have committed previously before response loss; redrive may **re-invoke the action**. Safe only with stable `operationId`s.
- Redrive is not "undo everything and run again"; nor does it prove compensations succeeded.

**Never redrive all compensation failures blindly without review.** If payments were captured/refunded and logs are ambiguous, reconcile before repeating actions.

### 18.1. Re-execution vs. redrive

Starting a brand-new execution with the same `orderId` and new operation IDs can create a second reservation or charge. If business rules allow "retrying an order," define a **new attempt number** and explicit idempotency policy rather than reusing prior effects blindly.

## 19. Monitoring workflows, callback backlogs, and business consistency

| Component | Signals to track | Why |
|---|---|---|
| Step Functions | `ExecutionsStarted`, `ExecutionsFailed`, `ExecutionsTimedOut`, `ExecutionsAborted` | Workflow health |
| Step Functions | `OpenExecutionCount`, `ExecutionTime`, execution history | Stuck approvals and quotas |
| Callback workers | Callback success/failure/timeout, processing latency, heartbeats | Is the worker alive? |
| SQS approval queue | `ApproximateNumberOfMessagesVisible`, `ApproximateAgeOfOldestMessage`, DLQ | Backlogs and poison messages |
| ECS/Lambda | Errors, throttles, CPU/memory, duration | Compute health |
| Business DB | Pending approvals, reservation TTLs, compensation counts | Business correctness |
| Payment provider | Auth holds, settled captures, pending refunds | External money-flow drift |

### 19.1. CloudWatch, history, and CloudTrail

- **Execution history:** transitions, Task started/succeeded/failed/timed-out, `Retry`/`Catch`, callback resolution.
- **CloudWatch metrics/alarms:** failed/timed-out executions, backlogs, worker error rates, pending compensation counts.
- **CloudTrail:** audits Step Functions API calls (`StartExecution`, `StopExecution`, `SendTask*`) and IAM/definition edits per logging config.
- **App logs:** `sagaId`, `orderId`, `operationId`, `decisionId`, `correlationId`—never raw tokens.
- **DB audits:** local transaction outcomes and business versions.
- **Distributed tracing:** connects API Gateway → Step Functions → Lambda/ECS/RDS via correlation IDs.

A `SUCCEEDED` execution does not prove downstream emails went out only once; maintain a **business ledger/reconciliation**. CloudWatch metrics and SQS counts can be approximate or slightly delayed.

### 19.2. Sensitivity of execution history

Task tokens can appear in SQS payloads or execution data if workflows include them in integration requests. Restrict read access to `GetExecutionHistory`, `DescribeExecution`, CloudWatch Logs, SQS payloads, and KMS keys. Disable or restrict `include-execution-data` in logging/CLI where needed. Never paste full history containing tokens into public tickets.

### 19.3. Runbooks and ownership

Build dashboards keyed by `sagaId`/`orderId` showing current step, elapsed time, business status, timeout deadline, compensation owner, and last failure. Alert on approvals breaching SLA, missed heartbeats, DLQ backlogs, and compensation retry thresholds. Intervention runbooks must specify who may **retry, compensate, stop/redrive, or manually reconcile**, with auditing.

## 20. Availability, quotas, and total cost

### 20.1. Key limits

| Limit | Standard | Express |
|---|---|---|
| Maximum execution duration | **1 year** | **5 minutes** |
| Callback integration | Yes | No |
| Execution history events | Up to **25,000** events | Does not store Standard-style execution history |
| Task/input/output payload | **256 KiB UTF-8** | **256 KiB UTF-8** |
| Redrive Standard failed executions | Yes when eligible | Not via the same mechanism |
| Task token length | **1–2,048 characters** per `SendTaskSuccess` API | Callbacks not applicable |

Check Regional quotas for API throttling, open executions, state transitions, SQS messages, Lambda concurrency, and KMS. Leaving a Task without an explicit timeout does not make waiting indefinitely safe.

### 20.2. Cost drivers

| Item | Cost / trade-off |
|---|---|
| **Step Functions Standard** | Billed by **state transitions**; waiting for a callback incurs no Lambda duration |
| **SQS/EventBridge/SNS** | Messages/requests, event deliveries, retries, DLQs |
| **Lambda/ECS** | Invocations/duration, compute capacity, auto scaling |
| **RDS/DynamoDB** | Idempotency/approval/outbox storage and transactions |
| **CloudWatch/CloudTrail** | Logs, retention, alarms, and auditing |
| **KMS** | Key management and cryptographic requests |
| **PrivateLink/NAT** | Interface endpoint hours, data processing/egress |
| **Payment/external providers** | Authorization/refund/charge fees and operational risk |

Never try to save one state transition by skipping reconciliation or `Catch` if it raises double-charge or bad-compensation risks. Compare **total TCO**, SLOs, failure modes, and audit needs—not just Step Functions fees.

### 20.3. Recovery and Regions

Step Functions is a Regional managed service; design multi-AZ redundancy for worker and data backends separately. Database backups/Multi-AZ, IAM/KMS, queue retention, DLQs, stable IDs, and callback bridge availability all affect sagas. **Cross-Region recovery** is not copying a token to a state machine in another Region; you must migrate/cancel/reconcile business operations and issue fresh execution attempt IDs.

## 21. Read-only CLI: inspecting workflows without sending callbacks

The commands below are **read-only** and never start, stop, or redrive executions. Uses AWS CLI v2, profile `dev`, Region `ap-southeast-1`. Replace illustrative ARNs/URLs with authorized resources.

### 21.1. Caller and state machine type

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws stepfunctions list-state-machines \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws stepfunctions describe-state-machine \
  --state-machine-arn arn:aws:states:ap-southeast-1:111122223333:stateMachine:OrdersSaga \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Type:type,Status:status,Role:roleArn,Definition:definition}' \
  --output json
~~~

Verify `type` is `STANDARD` for callbacks; inspect `.waitForTaskToken` Resources and token expressions in `definition`. **Definitions may expose sensitive resource names**—never paste them into public channels.

### 21.2. Reading executions

~~~bash
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:ap-southeast-1:111122223333:stateMachine:OrdersSaga \
  --status-filter RUNNING \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:OrdersSaga:sample-run \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Status:status,Start:startDate,Stop:stopDate,Error:error,Cause:cause,RedriveCount:redriveCount}' \
  --output json
~~~

### 21.3. History without printing raw execution data

~~~bash
aws stepfunctions get-execution-history \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:OrdersSaga:sample-run \
  --max-results 20 \
  --reverse-order \
  --no-include-execution-data \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

`--no-include-execution-data` avoids printing input/output bodies containing tokens or PII. Still handle metadata per data classification. When debugging details is required, do so in a secured environment with proper permissions.

### 21.4. Checking SQS backlog without `ReceiveMessage`

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals \
  --attribute-names QueueArn VisibilityTimeout RedrivePolicy ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

`ReceiveMessage` is not a harmless read: it hides messages and increments receive counts. Never poll a production queue just to "peek at a token" in a lab.

## 22. Mutating commands: only for approved sandboxes

### 22.1. `StartExecution` triggers real business work

~~~bash
# MUTATING: starts a workflow, may invoke Lambda/SQS and write DBs.
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:ap-southeast-1:111122223333:stateMachine:OrdersSaga \
  --name lab-order-101 \
  --input '{"orderId":"ord-101","reserveOperationId":"ord-101:reserve:1","confirmOperationId":"ord-101:confirm:1","releaseOperationId":"ord-101:release:1"}' \
  --profile dev \
  --region ap-southeast-1
~~~

All resources and credentials must point to a **sandbox** when running this. For duplicate execution names, AWS enforces idempotency rules by Standard workflow status/input—never reuse execution names without understanding them.

### 22.2. Callback success or failure

~~~bash
# MUTATING: run only with a real active token and valid approval.
aws stepfunctions send-task-success \
  --task-token "$TASK_TOKEN" \
  --task-output '{"approved":true,"decisionId":"dec-101"}' \
  --profile dev \
  --region ap-southeast-1

# ALTERNATIVE: never run both on the same token.
aws stepfunctions send-task-failure \
  --task-token "$TASK_TOKEN" \
  --error ApprovalRejected \
  --cause "Rejected by authorized reviewer" \
  --profile dev \
  --region ap-southeast-1
~~~

Bash syntax example; PowerShell uses different variable/quoting syntax. Retrieve `TASK_TOKEN` securely and keep it out of logs, shell history, and tickets. In production, use a callback bridge or SDK.

### 22.3. Heartbeat is not a harmless inspection command

~~~bash
# MUTATING: resets the heartbeat clock of a pending task.
aws stepfunctions send-task-heartbeat \
  --task-token "$TASK_TOKEN" \
  --profile dev \
  --region ap-southeast-1
~~~

Never call heartbeat merely to test whether a token is valid, because the call itself extends the heartbeat timer.

## 23. Troubleshooting callbacks and sagas

| Symptom | Common cause | What to check |
|---|---|---|
| `.waitForTaskToken` unavailable | Express workflow type | `describe-state-machine.type` |
| Execution waits indefinitely | Worker never called back, no deadline | Timeouts, SQS backlog, worker health |
| `InvalidToken` | Wrong, truncated, or corrupted token | Token store/serialization; never log raw tokens |
| `TaskTimedOut` | Task timed out/closed or callback arrived late | History/timeouts, business outcome |
| Callback `AccessDenied` | Role missing `states:SendTask*` or wrong account | `sts get-caller-identity`, IAM, same-account rule |
| Worker B calls back Account A execution | Cannot use B's principal directly | Assume role in A or call bridge in A |
| `InvalidOutput` | Output is not valid JSON | JSON serialization, 256 KiB payload |
| `KmsAccessDeniedException` | Wrong KMS permissions/key policy | KMS key state/grants |
| Approval saved in DB yet Step Functions stays paused | Callback failed or response ambiguous | Callback status, execution history, retry reconcile |
| Task success drops `orderId` | Default `ResultPath` overwrote input | Configure explicit `ResultPath` |
| Worker processes message again | Crash after callback before SQS `DeleteMessage` | Inbox/`operationId` and receipt handle |
| Payment double-charged | Retried with a different payment key | Stable provider idempotency key |
| Inventory released twice | Non-idempotent compensation | Reservation state/conditional transition |
| Timeout yet operation committed | Unknown outcome treated as failed | Business query/reconciliation |
| DLQ contains expired tokens | Queue redriven after task timeout | Never reuse old tokens; reconcile active Task |
| Retry storm | `Retry` too broad / missing backoff | `MaxAttempts`, jitter, transient classification |
| Execution failed yet payment hold remains | Compensation failed/never ran | `COMPENSATION_PENDING`, manual owner |
| Private-subnet worker cannot reach Step Functions | Missing `states` VPC endpoint/NAT, bad SG/DNS | Private DNS/TCP 443/IAM |
| Redrive repeats side effects | Stable `operationId` not preserved | Idempotency store, redrive review |

### 23.1. Layered diagnostic runbook

1. Confirm account, Region, execution ARN, and **`STANDARD`** type.
2. Read history **without printing tokens**: is the Task waiting, succeeded, failed, or timed out?
3. Check `.waitForTaskToken` and `$$.Task.Token`/`$states.context.Task.Token` syntax.
4. Check worker polling SQS, same-account callback IAM principal, and `states` endpoint networking.
5. Check Task deadline/heartbeat and whether retry/redrive issued a new token.
6. Read business operation logs and provider outcomes before compensating or retrying.
7. Check DLQs, compensation states, CloudWatch metrics, and owners for audited recovery.

**Never open IAM `states:*` or bypass approvals just to "make it work."** Resolve IAM, token, and networking faults at the proper layer.

## 24. Read-only exercises and business scenarios

### 24.1. Non-mutating lab

Use a read-only Step Functions/SQS `dev` profile in AWS CLI v2, or the sample JSON if no AWS account is available.

1. Use `list-state-machines` and `describe-state-machine` to verify **`STANDARD`** type and execution role.
2. Identify states using `.waitForTaskToken`, how the Context token is extracted, and Task timeouts.
3. Use `list-executions --status-filter RUNNING` and `describe-execution` to inspect execution age.
4. Use `get-execution-history --no-include-execution-data` to find `TaskStarted`/`TimedOut`/`Failed` without printing raw tokens.
5. Use `get-queue-attributes` to inspect backlog, visibility, and DLQ settings.
6. Build a table mapping `Task → operationId → compensation → owner/alert`.
7. Explain when to **retry**, **compensate**, **manually reconcile**, or **redrive**.

### 24.2. Scenario A — Human approval

An order requires review within 24 hours. Staff approves after 45 minutes.

- Step Functions awaits SQS callback with `TimeoutSeconds=86400`.
- Approval service stores the token securely, puts only `approvalId` in links, and authenticates reviewers.
- Callback succeeds with `{"approved":true}`; saga advances to `ConfirmOrder`.
- After timeout, late callbacks are rejected/do not resume; inventory releases idempotently.

### 24.3. Scenario B — 20-minute ECS job

A video-processing job runs on ECS; total timeout 30 minutes, heartbeat 2 minutes:

- Worker sends scheduled `SendTaskHeartbeat` calls while actively processing.
- On finish, calls `SendTaskSuccess` with `jobId`/`s3ArtifactKey`.
- Never returns video bytes in output; stays within 256 KiB.
- Worker dies → heartbeat timeout triggers, followed by retry/compensation per application policy.

### 24.4. Scenario C — Lost payment response

The provider captured funds, yet the payment service timed out:

- Query the provider using the stable payment `operationId`.
- If captured, proceed or refund per policy.
- If not captured, retry with the same provider idempotency key where supported.
- If unknown, mark `RECONCILIATION_REQUIRED`; never recharge with a new key.

### 24.5. Scenario D — Redrive a day later

A Standard execution reserved stock and then failed sending the approval request. Redriving may generate a new token. Workers must discard stale requests/tokens still in the queue. Keep `reserveOperationId` unchanged so stock is not reserved twice. Operators verify reservation expiry/outcome to confirm redrive safety.

### 24.6. Self-check decision table

| Situation | Priority decision |
|---|---|
| Task waiting, no SQS message visible | Check SQS/access/networking and Task status |
| Task waiting, worker running yet heartbeat lost | Check worker health and heartbeat timeout/retry |
| Token expired, no business effect committed | Close stale approval, run timeout/compensation |
| Token expired, business already committed | **Reconcile** before compensating |
| Callback response lost | Check execution/decision; do not assume failure |
| Compensation failed | Retry idempotently, alert, keep pending status |
| Redrive failed execution | Review history, stable IDs, new token |
| SQS redelivery | Inbox no-op, check callback outcome, delete per policy |

## 25. Self-assessment questions

1. Why does `.waitForTaskToken` require a Standard workflow?
2. How does a callback differ from `.sync` and the `Wait` state?
3. In JSONPath, is the token at `$$.Task.Token` or `$.taskToken` by default?
4. Which expression accesses the token in JSONata?
5. Must `SendTaskSuccess.output` be valid JSON?
6. Why must a token never be used as `orderId`/`operationId`?
7. Can an IAM principal in Account B directly call back an execution in Account A?
8. Why does IAM `SendTaskSuccess` typically require `Resource:"*"`?
9. Does a heartbeat extend total `TimeoutSeconds`?
10. When should you use heartbeats vs. deadlines for human approvals?
11. If a worker already succeeded its callback yet the SQS message redelivers, what should it do?
12. How does `ResultPath` preserve input when receiving callback output?
13. How does a Saga differ from a distributed ACID transaction?
14. Why might compensating a captured payment require a refund instead of a void?
15. Why must compensations also be idempotent?
16. Does a Lambda action timeout prove the DB transaction did not commit?
17. What gap between DB commit and EventBridge publish does an outbox solve?
18. Does redrive re-run every previously successful step?
19. Why should a raw task token never appear in an approval URL?
20. Which metrics reflect stuck executions and compensation backlogs?
21. How do CloudTrail and Step Functions execution history assist investigations differently?
22. When is choreography via EventBridge preferable to orchestration?

### Guiding answers

- **Callback:** Standard Task `.waitForTaskToken` generates a token, and a same-account worker calls `SendTaskSuccess`/`Failure`; heartbeats reset the heartbeat clock without extending total task timeout.
- **Saga:** independent local commits; compensation is not an ACID rollback, and unknown outcomes require reconciliation.
- **Idempotency:** stable `operationId`/`eventId`, database uniqueness, outbox/inbox, and payment provider idempotency keys; tokens are never business keys.
- **Security:** restrict token distribution, callback IAM roles, approval API auth, and never log tokens.
- **Operations:** `Retry`/`Catch`, DLQs, timeouts, reviewed redrives, CloudWatch/CloudTrail, and business ledgers.

## 26. Official AWS documentation

1. [Step Functions integration patterns](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html) — Request-response, `.sync`, callbacks, same-account tokens.
2. [SQS integration with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-sqs.html) — `sqs:sendMessage.waitForTaskToken`.
3. [Lambda integration with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-lambda.html) — Lambda callback patterns.
4. [Step Functions Context object](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-contextobject.html) — JSONPath/JSONata tokens.
5. [JSONata data transformations](https://docs.aws.amazon.com/step-functions/latest/dg/transforming-data.html) — `Arguments`, `Output`, Context.
6. [Step Functions Task state](https://docs.aws.amazon.com/step-functions/latest/dg/state-task.html) — Timeouts, `Retry`, `Catch`.
7. [Step Functions error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html) — Error names, retry/backoff/jitter.
8. [Step Functions best practices](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html) — Timeouts, heartbeats, execution management.
9. [SendTaskSuccess API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_SendTaskSuccess.html) — Token/output constraints.
10. [SendTaskFailure API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_SendTaskFailure.html) — Failure details.
11. [SendTaskHeartbeat API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_SendTaskHeartbeat.html) — Resets heartbeat, not overall timeout.
12. [Step Functions IAM authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_stepfunctions.html) — `SendTask*` IAM resource support.
13. [Choosing workflow types](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html) — Standard vs. Express.
14. [Step Functions quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html) — Durations, payload/history limits.
15. [Saga pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-data-persistence/saga-pattern.html) — Local transactions and compensation.
16. [Saga orchestration pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html) — Order saga on Step Functions.
17. [Redrive executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html) — Resuming failed Standard executions.
18. [Troubleshooting Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/troubleshooting.html) — Tokens, roles, timeouts.
19. [Activities in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-activities.html) — Polling activities vs. callbacks.
20. [AWS CLI get-execution-history](https://docs.aws.amazon.com/cli/latest/reference/stepfunctions/get-execution-history.html) — Omitting execution data.
21. [AWS CLI send-task-success](https://docs.aws.amazon.com/cli/latest/reference/stepfunctions/send-task-success.html) — Callback API syntax.
22. [Step Functions VPC endpoints](https://docs.aws.amazon.com/step-functions/latest/dg/vpc-endpoints.html) — Private AWS API connectivity.
23. [Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) — Standard transitions/Express.
24. [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/) — Requests and delivery.

> **Key takeaway:** Callback tokens are the mechanism to **wait for a Task to finish**, whereas a saga is the mechanism to **coordinate local transactions and compensations**. With Step Functions Standard, configure sensible timeouts/heartbeats, protect tokens, call back from same-account principals, keep business operation IDs stable, process idempotently, reconcile unknown outcomes, and monitor compensation/recovery until the entire business state is consistent.
