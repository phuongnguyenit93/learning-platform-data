# Amazon States Language and state types

> **Chapter:** Events and Orchestration  
> **Module:** `CLOUD_PROVIDERS_AWS` — exploring AWS across Region/AZ, IAM, VPC, compute, storage, databases, integration, and serverless; building skills to design secure, observable, resilient, and cost-controlled applications.

Suppose an order must run through several steps: validating data, reserving inventory, waiting for a payment response, sending a confirmation, and updating the shipping system. Writing all of this in one HTTP call or a single Lambda forces the application to track **which step it is on**, what happens on timeout, which step needs retries, and how to resume if a worker stops.

**AWS Step Functions** is a managed workflow orchestration service. You describe a workflow as a **state machine** using **Amazon States Language (ASL)**. Each **state** represents a decision, processing step, parallel branch, wait, or termination; Step Functions tracks progress and transitions states based on that definition.

ASL is a **JSON-based declarative language**, not a general-purpose programming language replacing Java, JavaScript, or Lambda. The state machine defines **orchestration order and data flow**, while business logic runs in Lambda, ECS, AWS Batch, other AWS services, or external systems via callbacks.

This lesson focuses on **ASL structure and state types**, while illustrating JSONPath/JSONata, error handling, service integrations, and production design limits. ARNs, AWS accounts, queue names, and payloads are illustrative data.

## 1. Learning objectives

After this lesson, learners will be able to:

1. Read and write a valid ASL definition with `StartAt`, `States`, `Type`, `Next`, and `End`.
2. Distinguish all **eight state types**: **Task, Pass, Choice, Wait, Succeed, Fail, Parallel, Map**.
3. Explain the differences between **state**, **transition**, **execution**, **task**, and **service integration**.
4. Pass data across states using **JSONPath** (`InputPath`, `Parameters`, `ResultSelector`, `ResultPath`, `OutputPath`) or **JSONata** (`Arguments`, `Assign`, `Output`, `Condition`).
5. Design `Retry`, `Catch`, timeouts, heartbeats, and bounded **fallback/compensation**.
6. Choose **Standard** or **Express Workflow** based on duration, reliability, workload nature, and cost model.
7. Apply `Parallel` and `Map` for branching/collection processing, understanding concurrency limits and side effects.
8. Inspect state machines via AWS Console/CLI, and observe execution history, IAM, and costs.

## 2. ASL is a workflow blueprint, not code running inside one container

### 2.1. Core concepts

| Term | Meaning |
| --- | --- |
| **State machine** | Workflow definition consisting of states and transition rules |
| **State** | A typed step such as `Task`, `Choice`, or `Wait` |
| **Execution** | A single run of a state machine with its own input and execution context |
| **Transition** | Moving workflow control from one state to another |
| **Task** | A state invoking work or an AWS service integration |
| **Input / Output** | JSON entering / leaving a state, optionally transformed |
| **Execution history** | Record of executed steps, outcomes/errors, and timestamps depending on workflow type and logging |
| **State machine role** | IAM execution role used by Step Functions to call integrated services |

A state machine might receive input:

~~~json
{
  "orderId": "order-101",
  "customerId": "customer-42",
  "amount": 350000,
  "currency": "VND"
}
~~~

State `ReserveInventory` processes and produces output, then `CheckReservation` chooses a branch. Step Functions does not automatically grant every task database access: **IAM roles**, networking, endpoints, and application logic must be configured separately.

### 2.2. Smallest meaningful example

~~~json
{
  "Comment": "ASL example calling no external services",
  "StartAt": "PrepareGreeting",
  "States": {
    "PrepareGreeting": {
      "Type": "Pass",
      "Result": {
        "message": "Hello AWS Step Functions"
      },
      "End": true
    }
  }
}
~~~

Reading in order:

1. `StartAt` names the initial state: `PrepareGreeting`.
2. `States` is an object containing **uniquely named states within that scope**.
3. `Type: "Pass"` means this step calls no Lambda or external API.
4. `Result` supplies fixed result JSON for a Pass state in **JSONPath** mode.
5. `End: true` marks successful completion of the active branch; there is no next state.

This is **strict JSON**—do not add `//...` comments to an ASL JSON definition file. ASL provides the `Comment` property for notes; do not confuse it with JSON comments.

### 2.3. State transition flow

~~~mermaid
flowchart LR
    START(["StartAt"]) --> A["State A"]
    A -->|"Next"| B["State B"]
    B -->|"Next"| C{"Choice"}
    C -->|"True"| D["Task"]
    C -->|"False"| F["Fail"]
    D --> E(["Succeed / End=true"])
~~~

Normal non-terminal states use **`Next`** or mark **`End: true`**; **never set both on the same state**. Certain state types have their own termination mechanics:

- **`Choice`** transitions via its rules and `Default`, without using `End` like Task/Pass.
- **`Succeed`** and **`Fail`** are terminal states; neither `Next` nor `End` is needed.
- A **branch** inside `Parallel` or `Map` has its own start and end.

### 2.4. Common top-level fields

| Property | Function |
| --- | --- |
| `Comment` | Optional description for the state machine |
| `StartAt` | Name of the first state; required |
| `States` | Map of state definitions; required |
| `Version` | ASL version (usually `"1.0"` if declared) |
| `TimeoutSeconds` | Execution time limit where supported |
| `QueryLanguage` | `"JSONPath"` (default) or `"JSONata"` per configuration |

Do not assume fields prefixed with `Parameters`/`ResultPath` are valid in **every** state or `QueryLanguage`. Validity depends on **state type**, **JSONPath/JSONata mode**, and current service documentation.

## 3. Eight state types in ASL

| State type | Primary function | Notable properties | Example |
| --- | --- | --- | --- |
| **Task** | Performs work via service integration / activity | `Resource`, `Parameters`/`Arguments`, `Retry`, `Catch` | Call Lambda to check inventory |
| **Pass** | Passes or transforms JSON without external calls | `Result`, `Parameters`, `ResultPath`, or `Output` | Normalize data |
| **Choice** | Branches on conditions | `Choices`, `Default` | Approve / reject |
| **Wait** | Waits for a duration or timestamp | `Seconds`, `Timestamp`, and Path/JSONata variants | Wait until email send time |
| **Succeed** | Ends branch/execution successfully | `Type: "Succeed"` | Complete order |
| **Fail** | Ends branch/execution in failure | `Error`, `Cause`, or supported expressions | Invalid input data |
| **Parallel** | Runs multiple branches concurrently and combines outputs | `Branches` | Check inventory and fraud |
| **Map** | Runs a sub-workflow over each item in a collection | `ItemsPath`, `ItemProcessor`, `MaxConcurrency` | Process each order line item |

These states serve **different purposes**. `Parallel` does not create two Lambda functions on its own; it orchestrates branches you define. `Map` does not split SQS messages or process big data without observing limits. `Choice` only evaluates conditions—it does not replace backend business validation.

## 4. `Task`: invoking Lambda and AWS service integrations

**`Task`** is the state that executes work. Its core property is **`Resource`**—an ARN or integration identifier understood by Step Functions.

### 4.1. Task invoking Lambda via optimized integration

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock",
    "Payload.$": "$"
  },
  "ResultSelector": {
    "stock.$": "$.Payload"
  },
  "ResultPath": "$.stockCheck",
  "Next": "DecideStock"
}
~~~

With **JSONPath**:

- `Resource` selects the **optimized Lambda integration**.
- `FunctionName` is the target Lambda function ARN.
- `"Payload.$": "$"` forwards **the entire Task input** as the Lambda payload.
- The optimized Lambda integration returns metadata plus `Payload`; `ResultSelector` keeps the business payload under `stock`.
- `ResultPath: "$.stockCheck"` inserts the result into `stockCheck` while preserving existing input fields.
- `Next` specifies the next state.

Example Task input:

~~~json
{"orderId":"order-101","qty":2}
~~~

Lambda response payload (assumed):

~~~json
{"available":true,"warehouse":"A"}
~~~

Output after `ResultSelector` and `ResultPath`:

~~~json
{
  "orderId": "order-101",
  "qty": 2,
  "stockCheck": {
    "stock": {
      "available": true,
      "warehouse": "A"
    }
  }
}
~~~

**If you omit `ResultPath`**, the result **replaces the entire input** by default; downstream states will no longer find `orderId` at `$.orderId` as expected. This is a very common ASL design mistake.

### 4.2. Task integration patterns

Step Functions supports integration patterns depending on service and API:

| Pattern | Meaning | When appropriate |
| --- | --- | --- |
| **Request-response** | Sends service API call and continues once the API response returns | Synchronous Lambda invoke, sending an SQS message, calling an AWS API |
| **Run a job (`.sync`)** | Waits for a supported service job to finish | ECS task, Batch job, or long job per supported integration |
| **Wait for callback (`.waitForTaskToken`)** | Hands a task token to an external system and waits for callback | Human approvals, external workers |

Not every AWS service/API supports all three patterns. Always check **supported integration patterns** for the specific `Resource`.

Common service integration examples:

~~~text
arn:aws:states:::lambda:invoke        (Lambda optimized)
arn:aws:states:::sqs:sendMessage     (SQS)
arn:aws:states:::sns:publish         (SNS)
arn:aws:states:::events:putEvents    (EventBridge)
arn:aws:states:::ecs:runTask.sync    (run and wait for ECS task as supported)
~~~

A Task calling SQS `SendMessage` succeeds when **SQS accepts the message**, not when a consumer finishes processing the business job. If you need to **wait for downstream completion**, use a callback/job-completion pattern or a separate workflow—never treat an enqueue 200 response as job completion.

### 4.3. Task timeouts and heartbeats

`TimeoutSeconds` and `HeartbeatSeconds` apply to **`Task`** depending on mode/integration, helping Step Functions detect stalled tasks or missing heartbeats when waiting on callbacks/activities.

- **Timeout**: caps task execution duration.
- **Heartbeat**: checks worker liveness in integrations that report progress.
- **`HeartbeatSeconds` does not turn a Lambda invoke into a heartbeat task**; the service/pattern must support it.
- A Task may already have performed an external side effect before the workflow sees a timeout error. Retries **must be idempotent**.

A callback task example is shown in the advanced patterns section.

## 5. `Pass`: transforming data without calling a backend

A **`Pass` state** is useful for building new input structures, attaching metadata, debugging flows, or mocking outputs without deploying a Lambda solely to reshape JSON.

Example using **`Parameters`** in JSONPath ASL:

~~~json
{
  "Type": "Pass",
  "Parameters": {
    "orderId.$": "$.orderId",
    "source": "web",
    "priority": "normal"
  },
  "ResultPath": "$.normalized",
  "Next": "CheckStock"
}
~~~

Given input:

~~~json
{"orderId":"order-101","amount":350000}
~~~

Output adds:

~~~json
{
  "orderId": "order-101",
  "amount": 350000,
  "normalized": {
    "orderId": "order-101",
    "source": "web",
    "priority": "normal"
  }
}
~~~

Recognizing the **`.$`** suffix in JSONPath:

- `"orderId.$": "$.orderId"` reads **the value from JSONPath**.
- `"source": "web"` is a **literal** string, not an input lookup.
- `"priority": "normal"` is also a literal.

A missing JSONPath target can cause a runtime error rather than silently yielding `null`; check with `Choice IsPresent` or ensure defaults.

### 5.1. `ResultPath: null` to discard results

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:audit-only",
    "Payload.$": "$"
  },
  "ResultPath": null,
  "Next": "ContinueProcessing"
}
~~~

In JSONPath mode, `ResultPath: null` **discards the Task result** and forwards the original input to the next state. Use it when only the side effect matters (such as writing an audit record), while still handling errors/catches; discarding a result **does not** mean the side effect ran exactly once.

## 6. `Choice`: branching and handling unmatched conditions

A **`Choice` state** reads input values, evaluates **choice rules**, and transitions to one of the defined target states.

~~~json
{
  "Type": "Choice",
  "Choices": [
    {
      "Variable": "$.amount",
      "NumericGreaterThan": 0,
      "Next": "ProcessPayment"
    },
    {
      "Variable": "$.amount",
      "NumericEquals": 0,
      "Next": "ProcessFreeOrder"
    }
  ],
  "Default": "RejectAmount"
}
~~~

Conditions are evaluated in order, taking the first matching branch. If no rule matches **and no `Default` is defined**, the state machine can fail with no valid transition.

### 6.1. Validate field presence and type before comparing

Do not assume `$.amount` is always present or numeric. Combine operators:

~~~json
{
  "Type": "Choice",
  "Choices": [
    {
      "And": [
        { "Variable": "$.amount", "IsPresent": true },
        { "Variable": "$.amount", "IsNumeric": true },
        { "Variable": "$.amount", "NumericGreaterThan": 0 }
      ],
      "Next": "ProcessPayment"
    }
  ],
  "Default": "RejectAmount"
}
~~~

JSONPath operators support comparisons such as `StringEquals`, `NumericGreaterThan`, `BooleanEquals`, `IsPresent`, `IsNull`, `IsString`, `Timestamp...`, and `And`, `Or`, `Not` combinations per schema. For loosely typed inputs, validate at the application boundary too rather than relying solely on `Choice`.

### 6.2. `Choice` does not provide error handling by itself

`Choice` only routes:

~~~mermaid
flowchart TB
    V{"Choice\namount > 0?"}
    V -->|"Yes"| PAY["Task: ChargePayment"]
    V -->|"No"| FAIL["Fail: InvalidAmount"]
~~~

It does not catch exceptions thrown by `ChargePayment`. If that Task can fail, attach **`Retry` / `Catch` to the Task** (or supported states), then route to the corresponding compensation or notification step.

## 7. `Wait`: pausing for a duration or until a timestamp

A **`Wait` state** expresses an explicit pause in a workflow without burning `Thread.sleep` inside a billed Lambda execution.

Example waiting **10 seconds**:

~~~json
{
  "Type": "Wait",
  "Seconds": 10,
  "Next": "RecheckStatus"
}
~~~

Example waiting until a fixed UTC timestamp:

~~~json
{
  "Type": "Wait",
  "Timestamp": "2027-01-15T09:00:00Z",
  "Next": "SendReminder"
}
~~~

In JSONPath, wait times can come dynamically from input via `SecondsPath` or `TimestampPath`, e.g.:

~~~json
{
  "Type": "Wait",
  "SecondsPath": "$.retryDelaySeconds",
  "Next": "RetryBusinessCheck"
}
~~~

**Use only one** wait property per Wait state. Keep maximum execution durations in mind between Standard and Express; never place a multi-hour `Wait` inside a short-lived Express execution. For very long waits or recurring schedules, evaluate EventBridge Scheduler and the right workflow type.

### 7.1. `Wait` does not replace `Retry`

A polling loop:

~~~text
CheckStatus Task → Choice
  Completed  → Succeed
  Pending    → Wait 10s → CheckStatus Task
  Failed     → Fail
~~~

can be useful when an external API only exposes polling status. Always bound **attempt counts/total duration**, track cancellation state, and set an overall workflow timeout to prevent costly infinite loops.

If a Task fails due to a transient technical error and can resend the same request, **`Retry`** is usually cleaner than a hand-rolled `Choice`/`Wait` loop. When business logic needs to poll a legitimate `PENDING` state (not a technical error), a `Wait` loop is more appropriate.

## 8. `Succeed` and `Fail`: intentional termination

### 8.1. Successful termination

~~~json
{
  "Type": "Succeed"
}
~~~

`Succeed` terminates the corresponding branch or execution successfully. If one branch inside `Parallel` reaches `Succeed`, **only that branch finishes**; `Parallel` still waits for sibling branches per its semantics.

### 8.2. Failed termination

~~~json
{
  "Type": "Fail",
  "Error": "InvalidOrderAmount",
  "Cause": "Order amount must be a positive number"
}
~~~

`Fail` signals an intentional failure, such as unacceptable input. It differs from an uncaught Task exception, though both can result in a **failed execution**.

Completing a compensating step (such as successfully releasing reserved stock) does not mean the order itself succeeded. You may end with `Fail` so upstream systems know the **business transaction was rejected**, or end with `Succeed` returning `status: REJECTED` if your contract explicitly defines that. Align metrics and API contracts accordingly.

### 8.3. Do not use `Fail` to hide transient errors

If Lambda returns 429 or an upstream returns 503, classify errors, apply bounded retries, and use fallbacks/queues/DLQs. Routing every transient error straight to `Fail` lowers success rates; conversely, retrying endlessly overloads downstream services.

## 9. `Parallel`: running multiple independent branches

A **`Parallel` state** coordinates multiple **branches**, where each branch is a sub-state-machine with its own `StartAt` and `States`. Branches execute concurrently at the workflow level; Step Functions waits for branches per `Parallel` semantics before advancing.

Example checking two independent conditions (runnable with Pass):

~~~json
{
  "Type": "Parallel",
  "Branches": [
    {
      "StartAt": "CheckStock",
      "States": {
        "CheckStock": {
          "Type": "Pass",
          "Result": { "stockAvailable": true },
          "End": true
        }
      }
    },
    {
      "StartAt": "CheckFraud",
      "States": {
        "CheckFraud": {
          "Type": "Pass",
          "Result": { "risk": "LOW" },
          "End": true
        }
      }
    }
  ],
  "ResultPath": "$.checks",
  "Next": "DecideOrder"
}
~~~

The result of `Parallel` is typically **an array** matching branch outputs in declared order:

~~~json
{
  "checks": [
    { "stockAvailable": true },
    { "risk": "LOW" }
  ]
}
~~~

Because `ResultPath: "$.checks"` is used, if the input also had `orderId`, the output preserves `orderId` alongside the new `checks` field.

### 9.1. When a branch fails

If one branch fails without being caught, the **`Parallel` state fails without waiting for other branches to complete normally**. Actions already taken by sibling branches (emails, DB writes, external API calls) **are not automatically rolled back**.

Therefore:

- Side effects inside branches must be **idempotent**.
- When compensation is needed, design explicit compensating Tasks based on committed results rather than expecting automatic rollback.
- Understand that `Retry`/`Catch` on a **child Task** differs from `Retry`/`Catch` wrapping **`Parallel`**: retrying the entire `Parallel` state can re-run multiple branches, including ones that already succeeded.

### 9.2. When should you use `Parallel`?

**Good fit:** checking independent credit and inventory rules before deciding; calling two high-latency systems with no data dependency between them. **Poor fit:** one branch generates a booking ID that the other branch needs—that is a sequential dependency.

## 10. `Map`: running a sub-workflow per item

A **`Map` state** acts like an orchestrated loop. It takes a collection, creates an **iteration** for each element, and runs the states inside `ItemProcessor`.

~~~mermaid
flowchart TB
    INPUT["Input: items = [A, B, C]"] --> MAP["Map state"]
    MAP --> A["ItemProcessor(A)"]
    MAP --> B["ItemProcessor(B)"]
    MAP --> C["ItemProcessor(C)"]
    A --> ARR["Array of iteration outputs"]
    B --> ARR
    C --> ARR
    ARR --> NEXT["Next state"]
~~~

### 10.1. Inline `Map` with `ItemsPath` and `ItemSelector`

Valid **JSONPath** example iterating over `$.items`:

~~~json
{
  "Type": "Map",
  "ItemsPath": "$.items",
  "MaxConcurrency": 3,
  "ItemSelector": {
    "orderId.$": "$.orderId",
    "item.$": "$$.Map.Item.Value",
    "itemIndex.$": "$$.Map.Item.Index"
  },
  "ItemProcessor": {
    "ProcessorConfig": {
      "Mode": "INLINE"
    },
    "StartAt": "MakeItemResult",
    "States": {
      "MakeItemResult": {
        "Type": "Pass",
        "Parameters": {
          "itemId.$": "$.item.id",
          "processed": true,
          "itemIndex.$": "$.itemIndex"
        },
        "End": true
      }
    }
  },
  "ResultPath": "$.itemResults",
  "Next": "SummarizeOrder"
}
~~~

Input:

~~~json
{
  "orderId": "order-101",
  "items": [
    { "id": "sku-A" },
    { "id": "sku-B" },
    { "id": "sku-C" }
  ]
}
~~~

With `ItemSelector`, each iteration receives both order context and its specific item. The Map output is an **array** placed at `$.itemResults`:

~~~json
{
  "orderId": "order-101",
  "items": [
    { "id": "sku-A" },
    { "id": "sku-B" },
    { "id": "sku-C" }
  ],
  "itemResults": [
    { "itemId": "sku-A", "processed": true, "itemIndex": 0 },
    { "itemId": "sku-B", "processed": true, "itemIndex": 1 },
    { "itemId": "sku-C", "processed": true, "itemIndex": 2 }
  ]
}
~~~

**`ItemSelector`** shapes the input passed to each iteration, whereas **`ItemsPath`** selects the input collection. **`ItemProcessor`** defines a sub-workflow, not a single Lambda ARN. This example uses only `Pass`, so it produces no side effects.

### 10.2. `Map` vs. `Parallel`

| Criterion | `Parallel` | `Map` |
| --- | --- | --- |
| Branches | Branches are **explicitly defined** in `Branches` | One `ItemProcessor` repeated across a collection |
| Count | Fixed number of branches in the definition | Iteration count driven by input data or reader |
| Result | Array of branch outputs | Array of iteration outputs (or result writer for Distributed Map) |
| Purpose | Multiple **distinct** independent checks | Repeating the same logic over **many uniform items** |
| Concurrency | Branches can run concurrently | Controlled via `MaxConcurrency` and mode limits |

To evaluate `creditRisk` and `stock` with two different workflows, use `Parallel`. To inspect 500 order line items with the same logic, use `Map`, sizing mode to scale.

### 10.3. Inline vs. Distributed Map

Step Functions offers two Map modes with different characteristics:

- **Inline Map:** iterations run inside the parent execution; suited for smaller collections within concurrency and execution history limits.
- **Distributed Map:** launches **child workflow executions** for large datasets as supported; can read sources like S3 using `ItemReader`, `ItemBatcher`, `ResultWriter`, and specialized settings.

**Never cram hundreds of thousands of records directly into state machine JSON input**: you will hit payload and execution history limits. Distributed Map can read collections from S3 and write outputs to S3, though you must plan IAM, quotas, child execution failure handling, and **execution/transition costs**.

### 10.4. Concurrency and downstream capacity

If `Map` runs 500 concurrent iterations and each opens a database connection, the DB connection pool can saturate. Never set `MaxConcurrency` solely by item count; size it using:

1. Downstream connection/request limits.
2. Safe parallelism of Lambda/ECS/third-party APIs.
3. Input nature: is ordering or per-entity serialization required?
4. Budget, retry counts, and Step Functions quotas.

`Map` **does not guarantee exactly-once side effects**; iterations can retry and external writes may already have occurred. Idempotency remains mandatory.

### 10.5. How does a single failed iteration affect execution?

With Inline Map, an unhandled error in one iteration can fail the **entire Map state**. Put `Catch` on the inner Task to record per-item failures and continue, or put `Catch` on the Map state to handle whole-Map failures.

With Distributed Map, you also have **failure tolerance** settings (tolerated failure rate/count) and Map Run controls. Choose carefully: "continue even if 5% fail" is only valid when the business **genuinely tolerates** losing/delaying those items and has a remediation path.

## 11. JSONPath data flow: the path through a state

In default ASL using **`QueryLanguage: JSONPath`**, Step Functions provides fields to control data flow:

~~~mermaid
flowchart LR
    IN["State input"] --> IP["InputPath\nfilter input"]
    IP --> PARAM["Parameters\nprepare task payload"]
    PARAM --> TASK["Task/State work"]
    TASK --> RS["ResultSelector\nselect result"]
    RS --> RP["ResultPath\nmerge input + result"]
    RP --> OP["OutputPath\nfilter output"]
    OP --> OUT["Next state input"]
~~~

*The diagram shows the relative order of fields in supported states; not every field is valid on all state types. With JSONata, the field model differs.*

### 11.1. Four paths easily confused

| Property | Purpose | Example |
| --- | --- | --- |
| **`InputPath`** | Selects the portion of JSON input entering the state | `"$.order"` |
| **`Parameters`** | Builds task payload/arguments from literals, paths, and intrinsics | `"orderId.$": "$.id"` |
| **`ResultSelector`** | Transforms/subsets the raw output of Task, Parallel, or Map as supported | `"data.$": "$.Payload"` |
| **`ResultPath`** | Attaches result into input, replaces input, or discards result | `"$.result"`, `"$"`, `null` |
| **`OutputPath`** | Selects the portion of output JSON passed to the next state | `"$.response"` |

Omitting `ResultPath` does not "auto-merge input + result." Its default is typically `"$"`, meaning **the result replaces the entire input**. That is why many examples explicitly specify `"ResultPath": "$.something"`.

### 11.2. Step-by-step example

Suppose a Task receives input:

~~~json
{
  "order": {
    "id": "order-101",
    "amount": 350000
  },
  "requestMeta": {
    "source": "web"
  }
}
~~~

If `InputPath: "$.order"` is set, the Task sees only:

~~~json
{"id":"order-101","amount":350000}
~~~

Then `Parameters` can construct the request:

~~~json
{
  "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:calculate-discount",
  "Payload": {
    "orderId": "order-101",
    "amount": 350000
  }
}
~~~

Suppose Lambda returns `Payload: {"discount":10000}` and `ResultSelector` extracts it. With `ResultPath: "$.discountData"`, the output merges into the **input already filtered by `InputPath`**:

~~~json
{
  "id": "order-101",
  "amount": 350000,
  "discountData": {
    "discount": 10000
  }
}
~~~

`requestMeta` does not come back because `InputPath` stripped it at state entry. To keep it, **do not drop it upfront**, or structure `Parameters`/`ResultPath` differently.

### 11.3. JSONPath and `.$` inside `Parameters`

~~~json
{
  "Parameters": {
    "fixed": "constant",
    "orderId.$": "$.order.id",
    "executionId.$": "$$.Execution.Id",
    "firstItem.$": "$.items[0]"
  }
}
~~~

This is a **`Parameters` fragment**, not a standalone state definition. Values:

- `$` represents the current JSON input.
- `$$` accesses the **Context object** (e.g., `$$.Execution.Id`).
- Key suffix `.$` indicates a supported path or intrinsic evaluation, **not a literal string**.

The **Context object** also exposes state, execution, task, and Map item metadata where applicable. Avoid dumping the full context into logs indiscriminately since it can include internal IDs/tokens.

### 11.4. Intrinsic functions in JSONPath

ASL supports intrinsic functions in certain JSONPath fields, for example:

~~~json
{
  "Parameters": {
    "orderId.$": "$.orderId",
    "uniqueExecutionId.$": "$$.Execution.Id",
    "itemCount.$": "States.ArrayLength($.items)",
    "serializedOrder.$": "States.JsonToString($.order)"
  }
}
~~~

This is also a **fragment**. Intrinsics handle string formatting, arrays, JSON, math, and simple transforms without creating a Lambda for trivial logic. **Never use `States.*` intrinsics inside JSONata fields**, because the two languages use different syntax.

### 11.5. Payload size and sensitive data

Every state passes JSON subject to Step Functions payload limits. Large objects like images, report files, or millions of records belong in **Amazon S3**, passing only **S3 bucket/key/metadata** between states.

Do not pass access tokens, secrets, payment card numbers, or unnecessary PII in state inputs/outputs; execution history and logs may capture them depending on settings. Apply encryption, IAM, redaction, and retention controls.

## 12. JSONata: writing expressions without the JSONPath field set

ASL supports **JSONata** as a query language for more expressive JSON transformations and conditions. Choosing the language is a **syntactic decision**, not just renaming fields.

### 12.1. How do JSONPath and JSONata differ?

| Topic | ASL JSONPath | ASL JSONata |
| --- | --- | --- |
| Default | Yes if `QueryLanguage` is omitted | Requires `QueryLanguage: "JSONata"` at state machine or state level |
| Data paths | `InputPath`, `Parameters`, `ResultSelector`, `ResultPath`, `OutputPath` | Uses `Arguments`, `Assign`, `Output`; JSONata expressions |
| Choice condition | `Variable` + `StringEquals` / `NumericGreaterThan`… | `Condition` containing a JSONata expression |
| Input/result references | `$` and `$$` context | `$states.input`, `$states.result`, `$states.context` per field scope |
| Expressions | JSONPath/intrinsics such as `States.ArrayLength` | JSONata functions, operators, and `{% ... %}` |
| Best suited for | Familiar workflows, simple paths | Structured transformations, math, complex conditions |

**Never mix fields from both modes arbitrarily inside the same state.** For example, a Task using JSONata must not simultaneously include JSONPath-only `Parameters` or `ResultPath`.

### 12.2. A simple JSONata workflow

~~~json
{
  "QueryLanguage": "JSONata",
  "StartAt": "CalculateGross",
  "States": {
    "CalculateGross": {
      "Type": "Pass",
      "Output": {
        "orderId": "{% $states.input.orderId %}",
        "gross": "{% $states.input.unitPrice * $states.input.quantity %}"
      },
      "End": true
    }
  }
}
~~~

Input:

~~~json
{"orderId":"order-101","unitPrice":100000,"quantity":3}
~~~

Output:

~~~json
{"orderId":"order-101","gross":300000}
~~~

`{% ... %}` is evaluated by Step Functions as a **JSONata expression** in supported fields. `gross` is a number because the expression evaluates multiplication, not a literal string with braces.

### 12.3. JSONata `Choice`

~~~json
{
  "Type": "Choice",
  "QueryLanguage": "JSONata",
  "Choices": [
    {
      "Condition": "{% $states.input.amount > 0 %}",
      "Next": "AcceptOrder"
    }
  ],
  "Default": "RejectOrder"
}
~~~

This fragment sits inside a state machine defining those target states. In JSONata, conditions are expressions returning a **Boolean**, without `Variable` and `NumericGreaterThan` as in JSONPath.

### 12.4. `Arguments` and `Output` in a JSONata `Task`

~~~json
{
  "Type": "Task",
  "QueryLanguage": "JSONata",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Arguments": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock",
    "Payload": "{% $states.input %}"
  },
  "Output": {
    "orderId": "{% $states.input.orderId %}",
    "stock": "{% $states.result.Payload %}"
  },
  "Next": "DecideStock"
}
~~~

Here:

- `$states.input` is the state's input.
- `Arguments` builds the request for the Lambda integration.
- `$states.result` is the Task result accessible in `Output`.
- `Output` constructs the JSON sent to the next state instead of `ResultSelector`/`ResultPath`/`OutputPath`.

**If the Task fails**, `$states.result` does not hold a success output; use compatible `Catch`/error handling. The example also assumes the IAM role can invoke Lambda and the function returns JSON with the expected schema.

### 12.5. `Assign` and variables

JSONata supports declaring state machine **variables** with `Assign` to store values across states under scoping rules. Example:

~~~json
{
  "Type": "Pass",
  "QueryLanguage": "JSONata",
  "Assign": {
    "savedOrderId": "{% $states.input.orderId %}"
  },
  "Output": {
    "validated": true
  },
  "Next": "DoWork"
}
~~~

Later states can read `$savedOrderId` within valid scope. ASL variables are not a persistent database or shared memory between **two different executions**. Visibility inside **`Parallel`/`Map`** and concurrent evaluation of `Assign`/`Output` follow ASL variable scoping/assignment rules; do not assume branches can freely mutate one shared global variable.

### 12.6. Migrating gradually from JSONPath to JSONata

In a state machine with **top-level JSONPath**, individual states can set `QueryLanguage: "JSONata"` to migrate incrementally. If top-level is **`JSONata`**, do not casually switch child states back to JSONPath. When migrating:

1. Write input/output unit tests first.
2. Convert JSONPath fields to their JSONata equivalents.
3. Verify `Retry`/`Catch`, `Choice`, `Map`, and variable scopes.
4. Run the workflow in a test environment and compare before/after outputs.
5. Avoid changing query syntax and business schemas in the same deployment whenever possible.

## 13. `Retry` and `Catch`: defining how workflows handle failures

### 13.1. Retrying transient errors

Tasks can fail due to throttling, service unavailability, or transient network errors. **`Retry`** lets Step Functions re-execute the state according to a policy:

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:reserve-inventory",
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
      "MaxAttempts": 3,
      "BackoffRate": 2,
      "MaxDelaySeconds": 30,
      "JitterStrategy": "FULL"
    }
  ],
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "ResultPath": "$.error",
      "Next": "HandleInventoryFailure"
    }
  ],
  "Next": "CheckReservation"
}
~~~

**Explanation:**

- `ErrorEquals` selects which **error types** trigger retries.
- `IntervalSeconds` is the initial wait; `BackoffRate` scales the wait on each retry.
- `MaxAttempts` caps the number of **retries** per policy; verify service semantics so you do not confuse it with guaranteed total calls.
- `JitterStrategy: "FULL"` prevents concurrent executions from retrying in lockstep.
- `MaxDelaySeconds` caps the exponential backoff delay.
- `Catch` runs when an error is not retried or retries are exhausted, transitioning to the error-handling state.

Never retry all errors blindly with `States.ALL` indefinitely. For missing required fields, IAM denials, or bad schemas, retrying only wastes money and hammers downstream systems with the same error.

### 13.2. Capturing error details via `Catch.ResultPath`

Suppose input before the Task is:

~~~json
{"orderId":"order-101","attempt":1}
~~~

The Task fails and `Catch` specifies `ResultPath: "$.error"`. State `HandleInventoryFailure` receives:

~~~json
{
  "orderId": "order-101",
  "attempt": 1,
  "error": {
    "Error": "Lambda.ServiceException",
    "Cause": "Failure details supplied by integration"
  }
}
~~~

`Error` and `Cause` are diagnostic fields; `Cause` may contain technical details or sensitive data depending on the integration, so **never expose the raw `Cause` directly to end clients**.

### 13.3. Key built-in error names

| Error name | Common meaning | Recommended action |
| --- | --- | --- |
| **`States.Timeout`** | State/task exceeded its timeout | Inspect timeouts; decide retry/cancel/compensate |
| **`States.HeartbeatTimeout`** | Task missed expected heartbeats | Check worker/callback, timeouts, and retries |
| **`States.TaskFailed`** | Matches general task failures (not all timeouts) | Contextual fallback catch |
| **`States.Permissions`** | Insufficient permissions to call service | Fix IAM; do not retry indefinitely |
| **`States.DataLimitExceeded`** | Payload exceeded Step Functions limit | Shrink state payload; offload files to S3 |
| **`States.Runtime`** | Runtime evaluation failure like invalid path/type | Fix definition/schema |
| **`States.ALL`** | Catch-all for many catchable error types | Place after specific catchers |

**Often overlooked:** `States.ALL` **cannot catch every error in all situations**—notably, terminal errors such as `States.DataLimitExceeded` and `States.Runtime` cannot be caught normally. Never rely on "Catch ALL" to claim a workflow can never fail.

### 13.4. Ordering and scope of `Retry`/`Catch`

- Retry rules are evaluated top-to-bottom to pick the matching policy.
- `States.ALL` must obey syntax constraints and sit alone at the end rather than mixing with other error names in the same `ErrorEquals`.
- Catchers are also evaluated in order; place specific errors before catch-all.
- Retrying a **Task inside `Map`/`Parallel`** differs from retrying the outer **`Map`/`Parallel` state**: retrying the outer state can re-execute side effects across multiple branches/items.
- Never treat `Retry` as **transaction rollback**.

### 13.5. Separating technical errors from business rejections

Example:

~~~text
Inventory API returns "not enough stock" (valid response)
  → Choice branches to RejectOrder

Inventory API times out or Lambda throttles (technical error)
  → Bounded Retry
  → Catch to an outage-handling branch
~~~

Lumping both into one `throw Error` causes workflows to needlessly retry out-of-stock orders, inflating latency and cost.

## 14. Complete state machine: validating and queuing order notifications

This example uses **JSONPath** and includes all pieces of a cohesive workflow: validate input, invoke Lambda, inspect result, build payload, send to SQS, and terminate. It performs no real payments or stock reservations.

### 14.1. Input

~~~json
{
  "orderId": "order-101",
  "amount": 350000,
  "currency": "VND",
  "items": [
    { "sku": "A-100", "quantity": 2 }
  ]
}
~~~

### 14.2. ASL definition

~~~json
{
  "Comment": "Illustrative ASL: validate, check stock, queue notification",
  "StartAt": "ValidateOrder",
  "States": {
    "ValidateOrder": {
      "Type": "Choice",
      "Choices": [
        {
          "And": [
            { "Variable": "$.orderId", "IsPresent": true },
            { "Variable": "$.amount", "IsNumeric": true },
            { "Variable": "$.amount", "NumericGreaterThan": 0 },
            { "Variable": "$.items", "IsPresent": true }
          ],
          "Next": "CheckStock"
        }
      ],
      "Default": "RejectInvalidInput"
    },
    "CheckStock": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock",
        "Payload.$": "$"
      },
      "ResultSelector": {
        "availability.$": "$.Payload"
      },
      "ResultPath": "$.inventory",
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
          "ResultPath": "$.inventoryError",
          "Next": "FailDependency"
        }
      ],
      "Next": "RouteByStock"
    },
    "RouteByStock": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.inventory.availability.available",
          "BooleanEquals": true,
          "Next": "PrepareNotification"
        }
      ],
      "Default": "RejectOutOfStock"
    },
    "PrepareNotification": {
      "Type": "Pass",
      "Parameters": {
        "orderId.$": "$.orderId",
        "status": "STOCK_CHECK_PASSED"
      },
      "ResultPath": "$.notification",
      "Next": "SendNotification"
    },
    "SendNotification": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sqs:sendMessage",
      "Parameters": {
        "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/order-events-lab",
        "MessageBody.$": "States.JsonToString($.notification)"
      },
      "ResultPath": "$.sendResult",
      "Retry": [
        {
          "ErrorEquals": ["States.TaskFailed"],
          "IntervalSeconds": 2,
          "MaxAttempts": 2,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.sendError",
          "Next": "FailDependency"
        }
      ],
      "Next": "Completed"
    },
    "Completed": {
      "Type": "Succeed"
    },
    "RejectInvalidInput": {
      "Type": "Fail",
      "Error": "InvalidOrder",
      "Cause": "Required fields or amount are invalid"
    },
    "RejectOutOfStock": {
      "Type": "Fail",
      "Error": "OutOfStock",
      "Cause": "Stock is not available"
    },
    "FailDependency": {
      "Type": "Fail",
      "Error": "UpstreamServiceFailure",
      "Cause": "A dependency failed after retry or recovery was not possible"
    }
  }
}
~~~

This example uses **`Choice`, `Task`, `Pass`, `Succeed`, and `Fail`**. `Wait`, `Parallel`, and `Map` were demonstrated separately above; a valid definition does not need every state type in a single workflow.

### 14.3. Workflow diagram

~~~mermaid
flowchart TD
    A(["StartAt: ValidateOrder"]) --> V{"Required fields valid?"}
    V -->|"No"| BAD["Fail: RejectInvalidInput"]
    V -->|"Yes"| INV["Task: CheckStock\nLambda + Retry/Catch"]
    INV -->|"Unrecoverable error"| DEP["Fail: FailDependency"]
    INV --> CHECK{"available == true?"}
    CHECK -->|"No"| OUT["Fail: RejectOutOfStock"]
    CHECK -->|"Yes"| P["Pass: PrepareNotification"]
    P --> SEND["Task: SendNotification\nSQS + Retry/Catch"]
    SEND -->|"Unrecoverable error"| DEP
    SEND -->|"Success"| OK(["Succeed: Completed"])
~~~

### 14.4. Tracing the output flow

Suppose Lambda `check-stock` returns:

~~~json
{"available":true,"warehouse":"SG-01"}
~~~

After `CheckStock` with `ResultPath: "$.inventory"`, state contains:

~~~json
{
  "orderId": "order-101",
  "amount": 350000,
  "currency": "VND",
  "items": [
    { "sku": "A-100", "quantity": 2 }
  ],
  "inventory": {
    "availability": {
      "available": true,
      "warehouse": "SG-01"
    }
  }
}
~~~

After `PrepareNotification`, this is added:

~~~json
{
  "notification": {
    "orderId": "order-101",
    "status": "STOCK_CHECK_PASSED"
  }
}
~~~

*The JSON above shows only the newly added portion, not the full output.* After `SendNotification`, `$.sendResult` holds the SQS integration response; `Completed` finishes the execution successfully.

**Important semantic point:** `SendNotification` succeeding means **SQS accepted the enqueue call per the integration**, not that the customer received an email. If Step Functions retries due to an ambiguous response, SQS Standard may receive duplicate messages. Consumers must be idempotent.

### 14.5. Prerequisites to run the example

This state machine JSON is a workflow definition—it **does not automatically create** dependent resources:

1. Lambda `check-stock` actually exists in the Region and returns `{"available": true/false}`.
2. SQS `order-events-lab` exists with the exact queue URL/ARN.
3. The Step Functions execution role has `lambda:InvokeFunction` for Lambda and `sqs:SendMessage` for the queue.
4. Producers/consumers, data, retries, CloudWatch logging, and IAM security are properly configured.
5. Callers have `states:StartExecution` if launching executions.
6. The ordering system agrees that **checking stock** is not **reserving stock**; if real reservation is required, add business reservation logic and compensation per transaction design.

## 15. Callback pattern with task tokens: waiting for external systems

Not every step runs immediately. A workflow requiring a department manager to approve a large order may need to wait several hours. Step Functions **Standard Workflow** can use the **wait for callback** pattern, passing a **task token** to an external worker/application.

~~~mermaid
sequenceDiagram
    participant SF as Step Functions
    participant Q as SQS approval queue
    participant W as Approval worker/service
    participant H as Human reviewer
    SF->>Q: SendMessage with taskToken
    Note over SF: Workflow waits for callback
    Q->>W: Worker receives work item
    W->>H: Request approval
    H-->>W: Approve / Reject
    alt Completed
        W->>SF: SendTaskSuccess(token, JSON output)
        SF-->>SF: Proceed to Next state
    else Error or timeout
        W->>SF: SendTaskFailure or task expires
        SF-->>SF: Retry/Catch/Fail per definition
    end
~~~

### 15.1. Task sending to SQS and waiting for callback

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
  "Parameters": {
    "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/approvals-lab",
    "MessageBody": {
      "orderId.$": "$.orderId",
      "taskToken.$": "$$.Task.Token"
    }
  },
  "TimeoutSeconds": 3600,
  "ResultPath": "$.approval",
  "Next": "CheckApproval"
}
~~~

This is a **Task fragment** using the `.waitForTaskToken` integration pattern supported for SQS. The external system extracts the token and calls Step Functions **`SendTaskSuccess`** or **`SendTaskFailure`** with appropriate IAM permissions. Without a callback before timeout, the Task fails and needs an error-handling branch.

**Security:** a task token is a **bearer capability that can complete the task**. Never email tokens in plain text, log them where broad staff can read them, or let unauthenticated clients call `SendTaskSuccess`. Workers must verify approval decisions and write an audit trail before calling back. **Account/Region and token usage constraints** apply; check callback workflow docs before building cross-account approvals.

### 15.2. Heartbeats vs. timeouts

For activity/callback-style tasks supporting heartbeats:

- `HeartbeatSeconds` sets the maximum gap between `SendTaskHeartbeat` calls.
- `TimeoutSeconds` caps total Task duration; heartbeats do not bypass the total timeout.
- If a callback arrives after the token expires or was already consumed, completion fails; backends must recognize and handle late results.
- A task token is **not a business side-effect idempotency key**; track separate business IDs and transaction states.

### 15.3. Standard vs. Express for callbacks

**`.sync`** and **`.waitForTaskToken`** belong to integration patterns supported on **Standard Workflows**—do not blindly apply them to Express just because both use ASL. Express uses **request-response** integrations; for long-running waits, design with Standard, nested workflows, or an appropriate event/callback architecture.

## 16. When to choose Standard vs. Express Workflows?

AWS Step Functions offers two workflow types with distinct execution, observability, and cost traits:

| Criterion | **Standard** | **Express** |
| --- | --- | --- |
| Duration | Long-running workflows, commonly used for hours/days of waiting within service limits | Short-duration workflows, commonly capped at **5 minutes** |
| Semantics | Stateful orchestrated workflows with history per Standard semantics; mind Task retries | Async Express is typically at-least-once; Sync Express differs; idempotency required |
| Execution history | History in Step Functions API/Console as supported | Observed primarily via CloudWatch Logs/metrics and logging configuration |
| Integrations | Request-response; `.sync` and callback patterns supported per service | Primarily request-response; do not assume callback/job-run support |
| Primary cost driver | **State transitions** and related components | **Execution count, duration/resources** per pricing model |
| Best suited for | Approvals, order sagas, long batch jobs, auditable flows | Short event processing, short API orchestration, high traffic |

**Never equate Standard's exactly-once workflow orchestration with exactly-once business side effects.** For example, if a Lambda writes to a DB and times out, `Retry` can invoke Lambda again. Payments, vouchers, emails, and inventory still require **business idempotency**.

### 16.1. Quick selection heuristics

- Includes **waiting for human approval** until the next day: usually choose **Standard**.
- **Chaining 3 short Lambdas** under heavy load taking a few seconds each: consider **Express** or Standard depending on cost/observability.
- Need **detailed execution history** to audit every transaction: Standard has an advantage.
- Need to process massive image batches via **Distributed Map**: evaluate Standard support for Map Runs and child execution costs.
- Involves **irreversible financial actions**: lock down transaction semantics and idempotency—never pick a type based solely on "exactly once" marketing phrasing.

## 17. Orchestration patterns: Saga, fan-out/fan-in, and async workflows

### 17.1. Saga / compensation

A transaction spanning Inventory, Payment, and Shipping is hard to wrap in **one ACID transaction** across all systems. One pattern is a **Saga**:

~~~mermaid
flowchart TD
    I["Reserve inventory"] --> P["Charge payment"]
    P --> S["Create shipment"]
    S --> DONE(["Order succeeded"])
    P -->|"Payment failed"| RI["Release inventory reservation"]
    S -->|"Shipment failed"| REF["Refund / void payment"]
    REF --> RI
    RI --> FAILED(["Order failed / needs review"])
~~~

**Compensation is not automatic rollback by Step Functions**:

- Each Task must track which side effects ran and persist **business state**.
- Compensating Tasks must be idempotent (canceling a reservation twice must not corrupt stock).
- When a compensation fails, retries, DLQs, runbooks, and operator intervention may be required.
- Some actions cannot truly be "undone," like sent emails or SMS alerts. Design meaningful business compensation states.
- Step Functions execution history is not the sole transaction database; Order/Payment systems still need authoritative sources of truth and audits.

### 17.2. Fan-out/fan-in

Use **`Parallel`** when branches perform distinct tasks, such as risk analysis and stock checks. Use **`Map`** when repeating the same logic across line items or S3 files. After all branches/iterations finish per policy, an aggregator Task can perform **fan-in**.

~~~text
Order input
  → Map: calculate each line item
  → array of item results
  → Task: summarize bill
  → Choice: allow payment?
~~~

When inputs are large, do not pass all results inline through execution JSON. Store outputs in S3/DynamoDB and pass **references** to the aggregator step.

### 17.3. Choreography and orchestration

| Model | How it works | Pros | Risks |
| --- | --- | --- | --- |
| **Choreography** (EventBridge/SNS/SQS) | Services react independently to events | Low temporal coupling, strong fan-out | Hard to see end-to-end progress; distributed business flow |
| **Orchestration** (Step Functions) | State machine coordinates sequence, errors, branches, waits | Visual, easy per-execution inspection, explicit retry/catch | State machine can become a coupling point across services |

Both models **can be combined**: EventBridge receives `OrderPlaced`, starts a Step Functions execution, and the workflow publishes `OrderCompleted` or enqueues SQS downstream. Never force every service into one giant workflow where ownership boundaries conflict.

### 17.4. When NOT to use Step Functions?

Step Functions is not always the right tool for:

- A trivial HTTP handler with no branching, multi-step flow, or durable workflow needs.
- Tight CPU-bound loops running in milliseconds per step where state transition overhead is uneconomical.
- Continuous per-packet streaming; Kafka/Kinesis/stream processors fit better.
- Local database transactions needing strict ACID commits that cannot accept Saga semantics.

Evaluate **business goals, latency SLOs, workflow duration, failure semantics, and cost**.

## 18. IAM, networking, and data protection

### 18.1. IAM execution role for a state machine

Step Functions needs an **IAM execution role** trusting `states.amazonaws.com`, with exact permissions to call Lambda/SQS/ECS/other integrations.

Illustrative policy for the workflow in section 14:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeInventoryFunction",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock"
    },
    {
      "Sid": "SendOrderNotification",
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:order-events-lab"
    }
  ]
}
~~~

This is only an illustrative **identity policy**, not a complete IAM role/trust setup. If the state machine calls `StartExecution` on nested workflows, `ecs:RunTask`, `iam:PassRole`, or KMS, check the exact integration policies. **Never attach `AdministratorAccess` just to resolve `"AccessDenied"`.**

### 18.2. Caller IAM role differs from execution role

- The caller/API launching the workflow needs permissions like **`states:StartExecution`** on the target state machine ARN.
- Step Functions uses the **state machine execution role** to invoke Lambda, `SendMessage`, etc.
- The Lambda function uses its **own Lambda execution role** to access DBs, Secrets Manager, or business AWS APIs.
- ECS Tasks also have their own task/execution roles. Never assume the Step Functions role grants permissions inside containers.

A caller can launch a workflow without directly holding `sqs:SendMessage`; Step Functions performs that action under its configured role if permitted.

### 18.3. Often-overlooked networking details

Step Functions is a managed orchestration service, **not an EC2 instance placed inside a private subnet you pick**. Task Lambdas/ECS tasks may require VPC networking to reach RDS, PrivateLink, or internal apps. Service integrations use their respective endpoints/IAM—never assume "the state machine is in VPC A" so it can directly reach private IPs.

If a private-subnet Lambda needs an Internet API, it may need a NAT Gateway or VPC endpoint; that is a **Lambda networking** requirement, not caused by Task JSON. Similarly, callback workers need network and IAM access to the Step Functions API.

### 18.4. Securing inputs/outputs and execution history

- Keep raw access tokens/credentials and unnecessary sensitive data out of state inputs.
- Use **Secrets Manager/SSM** per supported mechanisms, passing secret references only when appropriate.
- Enable CloudWatch Logs and govern **retention/access**, noting `IncludeExecutionData` can capture sensitive inputs/outputs.
- Use KMS encryption and proper access policies as required.
- Restrict who can call `DescribeExecution`, `GetExecutionHistory`, `StopExecution`, `UpdateStateMachine`, and `StartExecution`.
- Use CloudTrail, IAM change reviews, and audits to track definition/role edits.

Execution history exists to troubleshoot progress, not as a permanent archive of all customer data.

## 19. Observing state machines and measuring performance

### 19.1. Metrics across three layers

| Layer | Signals to watch | Meaning |
| --- | --- | --- |
| **Workflow** | Executions started/succeeded/failed/timed out/aborted | Success rate and end-to-end duration |
| **State/task** | Task duration, Retry/Catch errors, transition counts | Which step is slow or expensive |
| **Downstream** | Lambda errors/throttles, SQS age, ECS tasks, RDS latency | Where the actual underlying failure lives |

Step Functions provides **CloudWatch metrics**, Console execution views, and logging/tracing per configuration and workflow type. Common metric names include `ExecutionsStarted`, `ExecutionsSucceeded`, `ExecutionsFailed`, `ExecutionsTimedOut`, `ExecutionsAborted`, and throttling metrics where applicable. However, **a `Succeeded` execution does not guarantee an SQS downstream consumer finished processing the message**.

### 19.2. Attaching a business correlation ID

A state machine receives:

~~~json
{
  "orderId": "order-101",
  "correlationId": "trace-abc-123",
  "customerId": "customer-42"
}
~~~

Pass `orderId`/`correlationId` to Lambda/SQS or application logs per data policies. CloudWatch/X-Ray and application logs can correlate failures via this ID. **Never log entire sensitive payloads just for tracing**; enforce redaction and least-privilege log access.

### 19.3. Watch output shapes, not just HTTP 200

Step Functions bugs often come from **schema mismatches**:

- Lambda returns `{"approved":true}`, while `Choice` checks `$.Payload.approved` after `ResultSelector` moved it to `$.verification.data.approved`.
- JSONPath references a missing field → runtime failure.
- Default `ResultPath` overwrites input → next step loses `orderId`.
- SQS `sendMessage` succeeds, yet the next state expects original input intact because `ResultPath` was omitted.
- One `Parallel` branch returns an array/object shape different from what the aggregator expects.

In staging, define **expected JSON schemas** for each Task's input/output, testing success, business rejections, and technical failures.

### 19.4. SLO-aligned alarms

Suppose the service SLO is **99% of accepted orders orchestrated within 2 minutes**:

~~~text
Workflow:
  99% of executions reach a valid terminal state < 2 minutes

Failure alarm:
  ExecutionsFailed / ExecutionsStarted exceeds threshold

Latency alarm:
  End-to-end duration p95/p99 exceeds SLO

Downstream alarm:
  Lambda errors/throttles or SQS oldest message age rises
~~~

Thresholds are illustrative. Distinguish executions ending in **`Fail`** due to invalid orders (normal business rejections) from Lambda/throttling failures. If every business rejection uses `Fail`, `ExecutionsFailed` can spike even when infrastructure is healthy; add dedicated business status metrics and dashboards.

## 20. AWS CLI: reading and inspecting state machines safely

These commands are primarily **read-only**, except local definition validation (which does not deploy). Replace ARNs, accounts, and Regions with authorized resources. Never run `start-execution`, `stop-execution`, `update-state-machine`, or `delete-state-machine` in production outside approved change procedures.

### 20.1. List state machines

~~~bash
aws stepfunctions list-state-machines \
  --region ap-southeast-1 \
  --query "stateMachines[].{Name:name,Arn:stateMachineArn,Type:type}" \
  --output table
~~~

`stateMachineArn` is the full identifier, not just the display name. Match exact Region/account ARNs so you do not inspect a same-named workflow in another environment.

### 20.2. Inspect definition, IAM role, and workflow type

~~~bash
aws stepfunctions describe-state-machine \
  --region ap-southeast-1 \
  --state-machine-arn arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderWorkflowLab \
  --query "{Name:name,Type:type,Role:roleArn,Definition:definition,Logging:loggingConfiguration}" \
  --output json
~~~

Check `StartAt`, `States`, `QueryLanguage`, Task `Resource`, `Retry`/`Catch`, and IAM role. Never edit JSON directly in the Console and forget to sync IaC/Git.

### 20.3. Inspect executions of a Standard state machine

~~~bash
aws stepfunctions list-executions \
  --region ap-southeast-1 \
  --state-machine-arn arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderWorkflowLab \
  --max-results 20

aws stepfunctions describe-execution \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:123456789012:execution:OrderWorkflowLab:example-execution-id
~~~

`DescribeExecution` can return input/output alongside status, timestamps, and error/cause; restrict and protect read access accordingly. For **Express**, viewing history works differently—rely on CloudWatch Logs/metrics and Express-specific tooling rather than `GetExecutionHistory`.

### 20.4. Inspect event history of a Standard execution

~~~bash
aws stepfunctions get-execution-history \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:123456789012:execution:OrderWorkflowLab:example-execution-id \
  --max-results 30 \
  --query "events[].{Id:id,Type:type,Timestamp:timestamp,Previous:previousEventId}" \
  --output table
~~~

Focus on events like **`TaskStateEntered`**, service integration scheduled/started/succeeded/failed, and `Retry`/`Catch` transitions per actual event types. To find root cause, read the detailed event entry rather than guessing from a single `TaskFailed` row.

### 20.5. Validate an ASL definition before deploying

Once a sample definition is saved in an authorized local workspace, call the **validate API**:

~~~bash
aws stepfunctions validate-state-machine-definition \
  --region ap-southeast-1 \
  --definition file://order-workflow.asl.json
~~~

This is a **definition check**; it does not start executions or alter state machines. It returns **OK/FAIL and diagnostics** per your AWS CLI/Step Functions version. A **syntactically valid** definition can still fail at runtime if a Lambda ARN is missing, IAM is wrong, JSON input mismatches, or downstream returns 503—run integration tests.

### 20.6. Why not run `StartExecution` carelessly?

A state machine may have Tasks that send emails, deduct inventory, charge payments, or delete files. **Starting an execution mutates business state and can cost money.** When testing:

1. Use a dedicated lab/staging environment.
2. Use mock Lambdas/SQS or test accounts with synthetic data.
3. Run with non-real-customer `orderId` and correlation IDs.
4. Check outputs/history, cleanup/compensation, and cost.
5. Restrict production executions to approved permissions and procedures.

## 21. Troubleshooting by ASL error type

| Symptom | Primary suspect | How to investigate |
| --- | --- | --- |
| **Validation failed** | `StartAt` points to missing state; invalid `Next`; unsupported field | Validate ASL, check state names/`QueryLanguage` |
| **State takes wrong branch** | Choice rules evaluated in order; missing `Default`; unexpected type | Compare input JSON and choice operators |
| **No Choice matched / execution failed** | No rule matched and no `Default` defined | Add an intentional fallback branch |
| **`ResultPath` overwrites input** | Default result replaces input | Set explicit `ResultPath` or `null` when needed |
| **`States.Runtime`** | JSONPath/JSONata expression references invalid data or wrong type | Inspect event history; test state input/output |
| **`States.DataLimitExceeded`** | Workflow payload exceeded limit | Move large data to S3; pass references |
| **Lambda Task access denied** | State machine role missing `lambda:InvokeFunction` or another policy blocks | IAM role, resource ARN, CloudTrail |
| **Task timeout** | Lambda/ECS/worker ran too long or callback never arrived | `TimeoutSeconds`, downstream logs, token expiry |
| **`States.HeartbeatTimeout`** | Worker stopped sending heartbeats per policy | Check worker health, timeout, and callback mode |
| **Retry storm / downstream 429** | Excessive retries, missing jitter, or unbounded concurrency | Backoff, `MaxAttempts`, throttles, service quotas |
| **`Map` execution fails on one item** | Unhandled error, bad schema, failure threshold exceeded | `ItemProcessor` events/Map Run, item input, `Catch` |
| **`Parallel` Task sent email twice** | Retrying outer `Parallel` re-ran side-effect branch | Move retries onto individual Tasks; add idempotency |
| **`$.field` missing after Lambda** | `ResultPath`/`OutputPath` or `InputPath` stripped it | Trace data flow state by state |
| **Callback does not resume execution** | Wrong/expired/cross-account token or missing IAM | Callback worker logs, token lifecycle, `SendTaskSuccess` status |
| **Workflow succeeded yet business incomplete** | SQS enqueue is request-response; downstream runs async | Check queue/consumer; adjust contract or use callbacks |
| **Bill spikes under load** | High state transitions/`Map` child runs/retries/logs | Estimate costs, cap concurrency, streamline workflow |

### 21.1. Quick diagnostic procedure

1. **Definition**: Valid JSON? Do `StartAt` and all `Next`/`Default` targets exist? Is `QueryLanguage` consistent?
2. **Input/output**: What entered the state, did expressions pick the right fields, and is payload within size limits?
3. **Integration**: Does the Step Functions role have permissions? Are ARN/Region/account and backend healthy?
4. **Retry/Catch**: What error code occurred; did it over-retry or mis-catch? Are there side effects needing idempotency/compensation?
5. **Downstream**: Lambda/DB/SQS/third-party logs, throttling, timeouts, and concurrency limits.
6. **Recovery**: Can the execution be redriven, workflow retried, or compensated manually safely? Never blindly replay financial transactions.

### 21.2. Bugs from updating a definition mid-execution

Teams often update a state machine while executions are in flight. Never assume running executions automatically switch to the **newly deployed definition**. Use versions/aliases where supported, tag executions with their **definition version**, and follow reviewed release processes. Migrating in-flight state requires its own business plan.

## 22. Performance, concurrency, and cost control

### 22.1. Guiding cost formulas

For **Standard Workflows**, charges primarily track **state transitions**. For example, a simple execution traverses:

~~~text
ValidateOrder (Choice)
  → CheckStock (Task)
  → RouteByStock (Choice)
  → PrepareNotification (Pass)
  → SendNotification (Task)
  → Completed (Succeed)

≈ 6 state transitions (illustrative counting model)
~~~

With **20,000 executions/day**, a baseline estimate is:

~~~text
20,000 executions/day × 6 transitions/execution
  = 120,000 transitions/day
~~~

Actual counts increase with **Retries, `Map`/`Parallel` branches, and other transitions** per current billing rules. Check AWS pricing tables and usage metrics for exact dollar figures—no hypothetical unit price is assumed here.

### 22.2. Express and duration

For **Express**, billing typically combines **request/execution counts and resource-duration**, alongside logs and integrated services. Long `Wait` pauses affect Express cost/duration differently from Standard. Pick workflow types by total workload profile, not a single line item.

### 22.3. Cost sources outside Step Functions

| Component | Potential costs incurred |
| --- | --- |
| **Lambda** | Invocations, duration, memory, concurrency |
| **SQS/SNS/EventBridge** | API requests, payload/throughput, message volume |
| **ECS/Fargate/Batch** | vCPU/RAM/runtime, job attempts |
| **DynamoDB/RDS/S3** | Requests/compute/storage, backups, and data transfer |
| **CloudWatch/X-Ray** | Log ingestion/retention, metrics, tracing |
| **KMS/Networking** | Encryption calls, NAT/VPC endpoints/data transfer if used |
| **Workflow** | Transitions/`Map` child runs/retries or Express duration |

**`Wait` is not "free of everything."** Even though a workflow waiting on approval does not spin Lambda continuously, it still holds an open execution subject to duration/quota limits and potential monitoring/cost impacts depending on workflow type.

### 22.4. Concurrency and bottlenecks

When a workflow calls many Tasks simultaneously:

- `Parallel` fans out across its branches.
- `Map MaxConcurrency` or Distributed Map launches many iterations/child executions.
- `Retry` multiplies calls to Lambda/ECS/APIs.
- When downstream returns 429/503, scaling workflows can trigger a **retry storm**.

Design backpressure:

1. Cap `Map` concurrency to match DB/API capacity.
2. Offload long or non-urgent work to SQS/Batch with bounded queue consumers.
3. Retry with exponential backoff/jitter and `MaxAttempts`.
4. Route poison items to DLQs/exception workflows.
5. Set CloudWatch alarms on failed executions, p99 duration, and downstream saturation.

## 23. Reinforcement exercises

### Exercise 1 — Choosing states

A workflow needs to (a) call Lambda to process an order, (b) branch on `approved`, (c) wait 15 minutes, and (d) end successfully.

**Hint:** chain **`Task → Choice → Wait → Succeed`**. Never build four Lambda functions just to express branching, waiting, and termination.

### Exercise 2 — `Next` and `End`

A `Pass` state declares both `"Next":"B"` and `"End":true`.

**Hint:** conflicting transition syntax; a normal state chooses **either `Next` or `End`**, never both. Also verify state `B` exists.

### Exercise 3 — Task output loses `orderId`

Input: `{"orderId":"o-1","qty":2}`. An optimized Lambda integration Task returns metadata and `Payload`. The next state looks for `$.orderId` and fails to find it.

**Hint:** Tasks replace input with result by default. Use `ResultSelector` to extract what you need and `ResultPath: "$.stock"` to merge the result into input.

### Exercise 4 — `Choice` field may be missing

You write `"Variable":"$.amount","NumericGreaterThan":0`, yet input occasionally omits `amount` or sends a string.

**Hint:** check `IsPresent` and `IsNumeric` in the rule or normalize/validate input beforehand, and include a `Default` branch.

### Exercise 5 — `Parallel` or `Map`?

One workflow independently checks Fraud Risk and Inventory. Another generates thumbnails for 200 S3 images.

**Hint:** Fraud/Inventory are two distinct tasks → **`Parallel`**. Thumbnails repeat one process across many files → **`Map`**; choose Inline vs. Distributed based on item count and payload.

### Exercise 6 — Retries causing double charges

A Task calling a payment API succeeded in charging, yet Step Functions timed out and retried the Task, charging the customer a second time.

**Hint:** Task timeouts do not roll back external side effects. Use a payment-level **idempotency key** and durable status store, reconcile outcomes before retrying, cap `Retry`, and design compensation.

### Exercise 7 — What does an SQS Task succeeding mean?

A workflow uses `arn:aws:states:::sqs:sendMessage` and then `Succeed`. The email worker is down, so the customer never receives an email.

**Hint:** SQS `sendMessage` only confirms **enqueuing**, not that the consumer sent the email. Update the business contract to `ACCEPTED_FOR_PROCESSING`, or use callbacks/events when true completion is required.

### Exercise 8 — JSONPath or JSONata?

You want to compute `gross = unitPrice × quantity` directly inside a state without Lambda and return a new output containing `orderId` and `gross`.

**Hint:** a **JSONata `Pass` state** with `Output` and `{% $states.input.unitPrice * $states.input.quantity %}` fits cleanly; in JSONPath you could check supported intrinsics, though never mix syntaxes.

### Exercise 9 — Waiting three days for approval

HR may approve a request within three days, and the backend must resume the exact execution upon callback.

**Hint:** evaluate **Standard Workflow + `.waitForTaskToken`** instead of short-lived Express; protect the task token, set appropriate timeouts/heartbeats, and add an expiration branch.

### Exercise 10 — `Map` processing many items

`Map` runs 1,000 iterations, each calling a database allowing at most 30 concurrent connections. You plan `MaxConcurrency=1000`.

**Hint:** unsuitable; cap concurrency to match downstream throughput/connection pools and Step Functions/Lambda quotas. For large datasets, consider Distributed Map and S3 while still enforcing backpressure.

### Exercise 11 — `Catch ALL` cannot handle everything

A Task has `Catch ErrorEquals=["States.ALL"]`, yet the execution still fails with `States.DataLimitExceeded`.

**Hint:** `States.ALL` does not catch every terminal error. Shrink payloads, offload data to S3, and fix schemas/definitions—a single `Catch` cannot fix every failure.

### Exercise 12 — Choosing a workflow type

One team orchestrates a 2-Lambda API flow under 3 seconds at millions of executions/day. Another team has multi-day approvals.

**Hint:** the first team should **evaluate Express** for delivery/cost/observability fit; the second typically uses **Standard** for long duration and callbacks. Benchmark and check real quotas and integration patterns.

## 24. Production deployment checklist

- [ ] Business workflow diagram exists with clear input/output schemas and success/failure criteria.
- [ ] ASL validated; `StartAt`, state names, `Next`/`End`/`Default`, and branches are valid.
- [ ] Every state uses consistent **JSONPath or JSONata** syntax without mixing incompatible fields.
- [ ] Task `Resource`/`Parameters`/`Arguments` match service integrations and IAM roles.
- [ ] `ResultPath`/`Output` preserve required data; business IDs are not lost after Lambda calls.
- [ ] `Choice` rules check types/nulls/missing fields and define a `Default` fallback.
- [ ] Task timeouts and `Retry`/`Catch` separate transient errors, permanent errors, and business rejections.
- [ ] Sensitive side effects have idempotency/outbox; compensations are audited and handle failures.
- [ ] `Map`/`Parallel` concurrency fits downstream limits; outer retries do not duplicate side effects.
- [ ] Standard vs. Express workflow type, duration, callback support, and pricing have been compared.
- [ ] Large payloads are offloaded to S3 or a datastore; inputs/outputs/logs exclude unnecessary secrets.
- [ ] CloudWatch alerts, logs, traces/correlation IDs, and workflow execution metrics are configured.
- [ ] Roles are scoped to exact Lambda/SQS/ECS/Service ARNs, separating caller and execution roles.
- [ ] Tests cover success, business rejection, IAM errors, timeouts, throttling, Map item failures, and compensation.
- [ ] Definitions live in IaC/Git with versions/aliases and proper rollout/rollback procedures.
- [ ] Budgets account for state transitions, retries, Map child executions, Lambda/ECS/SQS, and logs.

## 25. Key takeaways

**Amazon States Language** is the declarative language for **workflow state machines** in AWS Step Functions:

1. **`StartAt`** picks the starting state, **`States`** defines all states, and each state directs flow via **`Next`, `End`, or type-specific rules**.
2. There are **eight state types**: **Task, Pass, Choice, Wait, Succeed, Fail, Parallel, Map**. Using the right type avoids unnecessary glue Lambdas.
3. **JSONPath** uses `InputPath`/`Parameters`/`ResultSelector`/`ResultPath`/`OutputPath`; **JSONata** uses fields/expressions like `Arguments`/`Assign`/`Output`/`Condition`. Never mix syntaxes carelessly.
4. **`Retry`/`Catch`** help recover from technical faults, yet **do not automatically roll back side effects**. Idempotency and compensation remain application responsibilities.
5. **`Parallel`/`Map`** enable fan-out, but require controlling concurrency, payloads, data consistency, and branch/iteration failures.
6. **Standard/Express** differ in duration, execution semantics, integrations, and pricing; choose based on SLOs and audit needs.
7. **Step Functions orchestrates; it does not replace business sources of truth.** Databases, queues, IAM, logging, and downstream systems must be designed alongside the workflow.

### Official AWS documentation

- [What is AWS Step Functions?](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) — service overview and concepts.
- [Amazon States Language specification](https://states-language.net/spec.html) — language spec, syntax, states, data flow, and errors.
- [State types in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-states.html) — Task, Pass, Choice, Wait, Succeed, Fail, Parallel, Map.
- [Using JSONPath paths in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/amazon-states-language-paths.html) — JSONPath and data selection.
- [Processing input and output in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-input-output-filtering.html) — InputPath, Parameters, ResultSelector, ResultPath, OutputPath.
- [Transforming data with JSONata](https://docs.aws.amazon.com/step-functions/latest/dg/transforming-data.html) — JSONata, Arguments/Assign/Output.
- [State machine context object](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-contextobject.html) — `$$` and `$states.context`.
- [Error handling in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html) — Retry, Catch, timeouts, and error names.
- [Integrating services with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html) — request-response, `.sync`, task tokens.
- [Lambda integration in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-lambda.html) — optimized Lambda Task.
- [SQS integration in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-sqs.html) — SendMessage and callback pattern.
- [Map state processing modes](https://docs.aws.amazon.com/step-functions/latest/dg/state-map.html) — Inline/Distributed Map and concurrency.
- [Standard vs. Express Workflows](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html) — duration, semantics, and observability.
- [Validating state machine definitions](https://docs.aws.amazon.com/step-functions/latest/apireference/API_ValidateStateMachineDefinition.html) — syntax checks and diagnostics.
- [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) — state transitions, executions, and related charges.
