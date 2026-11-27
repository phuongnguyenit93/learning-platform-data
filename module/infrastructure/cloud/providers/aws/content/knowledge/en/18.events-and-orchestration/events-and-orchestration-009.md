# `Parallel`, `Map`, and batch data processing orchestration

An e-commerce system may need to **check inventory, calculate shipping fees, and assess fraud risk** concurrently before confirming an order. Meanwhile, a data analytics pipeline may need to process **millions of CSV rows or thousands of S3 objects** in chunks, write results, and retry only failed pieces. Both scenarios require parallel execution, yet their scale, data-passing patterns, and error strategies differ dramatically.

**AWS Step Functions** is a workflow orchestration service built on **Amazon States Language (ASL)**. In this lesson, the three mechanisms to distinguish are:

- **`Parallel` state:** runs **a fixed set of independent workflow branches**, then waits for branches to finish and aggregates their results.
- **`Map` state – Inline:** iterates a workflow over **each element of a JSON array**, with bounded concurrency and shared execution history inside the parent workflow.
- **`Map` state – Distributed:** fans out a large dataset into **child workflow executions**, capable of reading data from S3, batching items, writing outputs to S3, and enforcing failure tolerance thresholds.

This lesson belongs to the **Events and Orchestration** chapter of the **CLOUD_PROVIDERS_AWS** module. Learners connect Step Functions with Region/AZ, IAM, VPC, Lambda, ECS, S3, databases, and integration services to design systems that are secure, observable, resilient, and cost-controlled.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish running **multiple different branches** from **processing each item in a single dataset**.
2. Write **ASL `Parallel`** and understand input fan-out, output arrays, result ordering, and `Retry`/`Catch`.
3. Write **Inline `Map`** with **`ItemsPath`, `ItemSelector`, `ItemProcessor`, `MaxConcurrency`**, and `ResultPath`.
4. Design **Distributed `Map`** using **`ItemReader`, `ItemBatcher`, `ResultWriter`**, child workflows, and **Map Runs**.
5. Understand **256 KiB payload**, **25,000 history events**, concurrency **40** and **10,000** constraints, and real-world throttling.
6. Choose **Standard/Express** for parent/child workflows and estimate impacts on semantics, logs, and cost.
7. Design **retries, backoff, failure thresholds, idempotency, redrive, and checkpoints**.
8. Configure IAM, S3/KMS, CloudWatch, inspect Map Runs, and troubleshoot production failures.
9. Apply these patterns to ETL pipelines, image processing, catalog imports, budget control, and batch reporting.

## 2. Architectural overview: fan-out and fan-in

~~~mermaid
flowchart TD
    EVENT["EventBridge / API / Schedule"] --> SF["AWS Step Functions<br/>Standard workflow"]
    SF --> CHOICE{"Which parallelism fits?"}
    CHOICE -->|"Distinct functions"| PAR["Parallel<br/>Inventory + pricing + risk checks"]
    CHOICE -->|"Small JSON array"| INLINE["Inline Map<br/>Process each item"]
    CHOICE -->|"Large dataset / S3"| DIST["Distributed Map<br/>Map Run"]
    PAR --> JOIN["Fan-in / aggregate results"]
    INLINE --> JOIN
    DIST --> JOIN
    DIST --> S3["S3 ItemReader / ResultWriter"]
    INLINE --> L["Lambda / ECS / AWS SDK integrations"]
    PAR --> L
    DIST --> L
    JOIN --> DB["S3 / DynamoDB / RDS / notifications"]
~~~

**Fan-out** splits work into concurrent branches or runs. **Fan-in** waits and aggregates outputs once the work completes. Orchestration does not automatically make sequential work safe to parallelize: check **data dependencies**, **operation ordering**, **downstream concurrency capacity**, and **idempotency** of side effects.

| Problem | Initial choice | Reason |
|---|---|---|
| Simultaneously check inventory, promotions, and fraud | **Parallel** | Three different logic branches, fixed branch count |
| Iterate 20 items in one order | **Inline Map** | Small input array, identical logic per item |
| Score 500,000 CSV records on S3 | **Distributed Map** | Large dataset, isolated concurrency and histories |
| A job must run step A then B then C | **Sequential Tasks** | Sequential dependency; must not parallelize |
| One event sent to many systems with no fan-in wait | **SNS/EventBridge fan-out** | Pub/sub fits better than fan-in orchestration |
| Push work to consumers with long-term backpressure | **SQS + consumers**, optionally paired with Step Functions | Queue buffering beats keeping unlimited concurrent workflows open |

### 2.1. Step Functions is not a heavy CPU compute runtime

Step Functions holds **orchestration state**; it does not replace Lambda, ECS, AWS Batch, or Amazon EMR. A **`Task`** state invokes a worker service, so worker costs and limits still apply. For heavy video/data processing, Step Functions coordinates **ECS/Batch/EMR/Glue** and waits for results per supported integration patterns.

## 3. `Parallel` state: running independent branches

A **`Parallel`** state defines a list of **`Branches`**, where each branch is a sub-state-machine with its own `StartAt` and `States`. Each branch receives the **same `Parallel` input** (after applicable input transforms), executes concurrently within service limits, and `Parallel` waits for all branches to succeed.

~~~mermaid
flowchart LR
    INPUT["Order input"] --> PAR["Parallel"]
    PAR --> A["Validate schema"]
    PAR --> B["Check inventory"]
    PAR --> C["Calculate shipping"]
    A --> JOIN["Result array<br/>[A, B, C]"]
    B --> JOIN
    C --> JOIN
    JOIN --> NEXT["Authorize payment"]
~~~

**Branches are isolated in state transitions:** branch A cannot transition directly to a state name inside branch B; shared data across branches must come from the common input or an appropriate external store/synchronizer. Never rely on vague shared DB state assuming `Parallel` provides cross-branch transaction isolation.

### 3.1. `Parallel` output is an array in branch declaration order

If branch A returns:

~~~json
{"check":"schema","ok":true}
~~~

And branch B returns:

~~~json
{"check":"stock","available":true}
~~~

Default `Parallel` output is:

~~~json
[
  {"check":"schema","ok":true},
  {"check":"stock","available":true}
]
~~~

Elements follow **branch declaration order**, **not** completion order. To label results clearly, have each branch return a named object or apply **`ResultSelector`/`ResultPath`**. Never assume a faster branch appears first in the output array.

### 3.2. Complete ASL: `Parallel` with no external AWS resources

This example uses **`Pass`** states to demonstrate fan-out/fan-in without real Lambdas:

~~~json
{
  "Comment": "Run independent checks in parallel",
  "StartAt": "CheckOrder",
  "States": {
    "CheckOrder": {
      "Type": "Parallel",
      "Branches": [
        {
          "StartAt": "ValidateSchema",
          "States": {
            "ValidateSchema": {
              "Type": "Pass",
              "Result": {"check": "schema", "ok": true},
              "End": true
            }
          }
        },
        {
          "StartAt": "CheckStock",
          "States": {
            "CheckStock": {
              "Type": "Pass",
              "Result": {"check": "stock", "available": true},
              "End": true
            }
          }
        }
      ],
      "ResultPath": "$.checks",
      "Next": "BuildResponse"
    },
    "BuildResponse": {
      "Type": "Pass",
      "Parameters": {
        "orderId.$": "$.orderId",
        "checks.$": "$.checks"
      },
      "End": true
    }
  }
}
~~~

Illustrative input:

~~~json
{"orderId":"o-101"}
~~~

Output is an object containing **`orderId`** and the **`checks`** array. **`ResultPath = $.checks`** keeps the original input and inserts the `Parallel` array; omitting `ResultPath` causes the array to replace the state's input by default. `Parameters` in the Pass state above uses JSONPath to pick fields; examples in this lesson use **JSONPath** ASL for consistency.

### 3.3. Shared input, independent outputs

| Property | `Parallel` | Design consequence |
|---|---|---|
| **Branches** | Independent workflows running concurrently | One branch cannot `Next` into another branch's state |
| **Input** | Each branch receives an independent copy of `Parallel` input | Do not expect in-memory mutations to leak across branches |
| **Output** | Array of outputs in branch order | Map/label items explicitly |
| **Completion** | Waits for all branches to succeed | Slowest branch gates fan-in |
| **Failure** | One unhandled branch failure fails `Parallel` | Design `Retry`/`Catch` and idempotent side effects |

### 3.4. What happens if one branch fails?

When a branch raises an unhandled error, **`Parallel` fails and Step Functions stops sibling branches at the workflow level**. However, **already-invoked Lambdas may keep running**; external work in ECS, APIs, or databases is not automatically rolled back or killed. Keep this in mind for branches that mutate data or issue invoices.

Two strategies:

- **Orchestration all-or-nothing:** let errors propagate to `Parallel`, then `Catch`/compensate at the workflow level after accounting for side effects.
- **Best effort:** each branch catches errors into a structured object such as **`{"ok":false,"error":...}`**, letting sibling branches finish so the parent evaluates all outcomes.

**Retrying at the `Parallel` level** can re-run branches that previously succeeded. Avoid broad outer retries when branches transfer money, write databases, or send notifications. Prefer bounded retries on individual Tasks paired with **idempotency keys**.

## 4. Inline `Map`: applying one workflow across many items

Given a JSON array, **`Map`** executes **`ItemProcessor`** for each item. **Inline `Map`** runs iterations inside the parent's **shared execution history**; per AWS, it supports up to **40 concurrent iterations**. For moderate item counts and small inputs, Inline is simpler than Distributed Map.

~~~mermaid
flowchart LR
    INPUT["Input<br/>items:[A,B,C,D]"] --> MAP["Inline Map<br/>MaxConcurrency=2"]
    MAP --> I1["Item A → workflow"]
    MAP --> I2["Item B → workflow"]
    I1 --> I3["Item C → workflow"]
    I2 --> I4["Item D → workflow"]
    I3 --> OUT["Results array"]
    I4 --> OUT
~~~

### 4.1. Key ASL fields

| Field | Meaning | Example |
|---|---|---|
| **`Type: Map`** | State iterating over items | `Map` |
| **`ItemsPath`** | JSONPath to input array (JSONPath workflows) | **`$.items`** |
| **`ItemSelector`** | Constructs per-iteration input, including context | Current item, index, `batchId` |
| **`ItemProcessor`** | Sub-workflow run for each item | Validate → Transform → Store |
| **`ProcessorConfig.Mode: INLINE`** | Selects Inline Map | No separate child workflow executions |
| **`MaxConcurrency`** | Maximum concurrent iterations | 5, 10, or 0 |
| **`ResultPath`** | Where `Map` results attach to input | **`$.processed`** |
| **`Retry / Catch`** | Error handling on `Map`/iterations | Bounded retries |

**`MaxConcurrency = 0`** removes an explicit cap so `Map` runs as concurrently as the service allows (still capped at 40 for Inline). **`MaxConcurrency = 1`** executes items sequentially one by one, useful for rate limiting or strict ordering—**it still does not guarantee exactly-once business processing**.

### 4.2. Complete ASL: Inline `Map` with `ItemSelector`

~~~json
{
  "Comment": "Illustrate an Inline Map without external services",
  "StartAt": "ProcessItems",
  "States": {
    "ProcessItems": {
      "Type": "Map",
      "ItemsPath": "$.items",
      "MaxConcurrency": 5,
      "ItemSelector": {
        "item.$": "$$.Map.Item.Value",
        "index.$": "$$.Map.Item.Index",
        "batchId.$": "$.batchId"
      },
      "ItemProcessor": {
        "ProcessorConfig": {"Mode": "INLINE"},
        "StartAt": "Transform",
        "States": {
          "Transform": {
            "Type": "Pass",
            "Parameters": {
              "itemId.$": "$.item.id",
              "sourceIndex.$": "$.index",
              "status": "SIMULATED"
            },
            "End": true
          }
        }
      },
      "ResultPath": "$.processed",
      "End": true
    }
  }
}
~~~

Sample input:

~~~json
{
  "batchId": "batch-2026-11-20",
  "items": [
    {"id":"a1"},
    {"id":"a2"},
    {"id":"a3"}
  ]
}
~~~

`Map` returns the original input plus the **`processed`** array. Each item yields **`itemId`, `sourceIndex`, `status`**. **`$$.Map.Item.Index`/`Value`** read from the **`Map` Context object**; map them in **`ItemSelector`** to pass them into each iteration. This example performs no external actions, making it easy to validate ASL structure before plugging in real Tasks.

### 4.3. What are Inline `Map`'s limits?

- Input must be a **JSON array** inside state input; large item datasets belong in S3 with Distributed Map.
- State input/output is capped at **256 KiB** per general Step Functions quotas.
- Every event across all iterations counts toward the parent workflow's history; Standard executions cap at **25,000 history events**.
- One unhandled iteration error can fail the **entire `Map`**, halting other iterations at the workflow level.
- `MaxConcurrency` does not bypass IAM permissions or Lambda/DynamoDB/S3 quotas.

**Never assume 100 items is always safe for Inline**: if each item traverses 20 Task states and retries several times, history events explode quickly. Conversely, 100 items passing through one lightweight Pass state may fit easily. Estimate **history events and output size**, not just item count.

## 5. Comparing `Parallel`, Inline `Map`, and Distributed `Map`

| Criterion | `Parallel` | Inline `Map` | Distributed `Map` |
|---|---|---|---|
| **Purpose** | Run multiple branches with **different logic** | Repeat **one workflow** over items | Process large datasets across child executions |
| **Input** | Shared input for branches | JSON array in state input | JSON array/object or S3 datasets |
| **Concurrency unit** | Branch | Inline iteration | Child workflow execution |
| **Concurrency** | Configured branches, bounded by quotas/load | Up to **40** | Up to **10,000** child executions/Map Run |
| **History** | Shared with parent | Shared with parent | Child histories separated from parent |
| **Payload** | **256 KiB** state/execution limit | **256 KiB**, easily hit by output array | Reads large S3 datasets; each child I/O still bounded |
| **Built-in S3 reader** | No `ItemReader` | No `ItemReader` | **`ItemReader`** for supported formats |
| **Batching items** | Build manually in branch | No Distributed `ItemBatcher` | **`ItemBatcher`** |
| **Exporting results** | Call Task to write S3 manually | Call Task to write S3 manually | **`ResultWriter`** to S3 |
| **Per-item failure tolerance** | Via `Catch` in branches | Via `Catch` in iterations | **`ToleratedFailureCount`/`Percentage`** |
| **Parent workflow type** | Standard or Express as supported | Standard or Express as supported | **Standard parent**; child **Standard or Express** |
| **Best fit** | 3–5 independent checks | A few to a few dozen items | Thousands/millions of items depending on size/quotas |

**The 10,000 limit is a ceiling, not a recommended default.** A job firing 10,000 concurrent child invocations at RDS can bring down the database. In operations, set **`MaxConcurrency` based on downstream capacity** and ramp up after benchmarking.

### 5.1. Simple decision tree

~~~mermaid
flowchart TD
    START["Parallel work needed?"] --> N{"Do branches share the same workflow<br/>per item?"}
    N -->|"No"| PAR["Parallel<br/>Functional fan-out"]
    N -->|"Yes"| BIG{"Dataset > 256 KiB,<br/>large history, or need >40?"}
    BIG -->|"No"| IN["Inline Map"]
    BIG -->|"Yes"| DIS["Distributed Map<br/>Standard parent"]
    DIS --> LIM["Set MaxConcurrency,<br/>IAM, ItemReader/ResultWriter"]
    IN --> SAFETY["Retries/idempotency +<br/>output limits"]
    PAR --> SAFETY
    LIM --> SAFETY
~~~

## 6. Distributed `Map`: Map Runs and child workflows

**Distributed `Map`** runs inside a **Standard parent workflow**. It creates a **Map Run** with its own ARN and status, reads datasets (JSON array/objects or S3), and orchestrates **child workflow executions**. Each child has its own execution history; the parent does not record every per-item transition like Inline `Map`.

~~~mermaid
flowchart TB
    EVENT["Schedule / API / EventBridge"] --> PARENT["Standard parent state machine"]
    PARENT --> MAP["Distributed Map / Map Run"]
    S3IN["S3 CSV / JSON / JSONL / Parquet<br/>object list / inventory / manifest"] --> READER["ItemReader"]
    READER --> BATCH["ItemSelector + ItemBatcher"]
    BATCH --> MAP
    MAP --> C1["Child workflow #1<br/>Standard or Express"]
    MAP --> C2["Child workflow #2"]
    MAP --> CN["Child workflow #N"]
    C1 --> WORKER["Lambda / ECS / Batch"]
    C2 --> WORKER
    CN --> WORKER
    C1 --> WRITER["ResultWriter"]
    C2 --> WRITER
    CN --> WRITER
    WRITER --> S3OUT["S3 status / output / failure files"]
    MAP --> PARENT
~~~

### 6.1. Relationship between parent, Map Run, and child execution

| Object | Role | How to observe |
|---|---|---|
| **Parent execution** | Orchestrates the overall batch job | `DescribeExecution` and execution graph |
| **Map Run** | Represents one Distributed Map run; tracks progress/error rates | `DescribeMapRun`, `ListMapRuns`, Map Run metrics |
| **Child execution** | Processes one item or one batch | Child execution ARN, status, and logs |
| **Worker** | Lambda/ECS/Batch doing actual work | Service metrics, traces, logs, and worker IAM |
| **S3 input/output** | Large datasets and outputs | S3 object versions, bucket policies, KMS, lifecycle |

**Distributed `Map` does not scale infinitely.** AWS Step Functions enforces a hard quota of **1,000 open Map Runs** and up to **10,000 concurrent child executions per Map Run** per docs at writing time. Dispatching child workflows is also constrained by API/Region throughput and real capacity; active children may run below `MaxConcurrency` even with large backlogs.

### 6.2. Standard or Express for children?

| Child execution type | Suitable characteristics | Caveats |
|---|---|---|
| **`STANDARD`** | Longer workflows needing detailed history and fault-tolerant orchestration | State transition billing, independent execution histories |
| **`EXPRESS`** | Short, high-volume tasks optimizing cost/throughput | **5-minute** limit, at-least-once semantics in async Express, different logs/monitoring from Standard |

**The parent containing Distributed `Map` must be Standard**, whereas **`ItemProcessor.ProcessorConfig.ExecutionType`** can be **`STANDARD`** or **`EXPRESS`** per AWS capabilities. Express children cannot use service integration patterns like **`.sync`** or **`.waitForTaskToken`** callbacks. Never pick Express if each item waits hours on jobs or callbacks.

### 6.3. Why use Map Run instead of firing thousands of Lambdas directly?

- Step Functions provides **centralized job state and progress metrics**.
- Supports **tolerated failure thresholds** and eligible redrives.
- Built-in **`ItemReader`** for S3 datasets, **`ItemBatcher`** for grouping items, and **`ResultWriter`** for exporting outputs.
- **`MaxConcurrency`** caps simultaneous downstream load.
- Each child has an isolated scope, making failed items far easier to pinpoint than one Lambda spawning 10,000 untracked calls.

However, when inputs arrive continuously and require long-term buffering/backpressure, **SQS + Lambda/ECS consumers** or AWS Batch may fit better than launching a Distributed Map for every small event. Choose based on **latency, traffic patterns, retry semantics, cost, and operations**.

## 7. Complete ASL: Distributed `Map` reading CSV from S3

Suppose object **`s3://batch-lab-input-example/imports/2026-11-20/orders.csv`** contains:

~~~csv
orderId,totalAmount,currency
o-101,120.00,USD
o-102,85.50,USD
o-103,32.00,USD
~~~

The parent workflow reads CSV with a header row, sends each record to a Lambda processor with concurrency capped at **50**, and writes outputs to an S3 bucket in the same account/Region.

~~~json
{
  "Comment": "Example Distributed Map processing a CSV dataset",
  "StartAt": "ProcessCsv",
  "States": {
    "ProcessCsv": {
      "Type": "Map",
      "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {
          "InputType": "CSV",
          "CSVHeaderLocation": "FIRST_ROW"
        },
        "Parameters": {
          "Bucket": "batch-lab-input-example",
          "Key": "imports/2026-11-20/orders.csv"
        }
      },
      "ItemSelector": {
        "record.$": "$$.Map.Item.Value",
        "index.$": "$$.Map.Item.Index"
      },
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "DISTRIBUTED",
          "ExecutionType": "STANDARD"
        },
        "StartAt": "ProcessOne",
        "States": {
          "ProcessOne": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-one",
              "Payload.$": "$"
            },
            "OutputPath": "$.Payload",
            "Retry": [
              {
                "ErrorEquals": [
                  "Lambda.ServiceException",
                  "Lambda.AWSLambdaException",
                  "Lambda.SdkClientException"
                ],
                "IntervalSeconds": 2,
                "BackoffRate": 2,
                "MaxAttempts": 3
              }
            ],
            "End": true
          }
        }
      },
      "MaxConcurrency": 50,
      "ToleratedFailureCount": 5,
      "ResultWriter": {
        "Resource": "arn:aws:states:::s3:putObject",
        "Parameters": {
          "Bucket": "batch-lab-results-example",
          "Prefix": "results/2026-11-20/"
        }
      },
      "End": true
    }
  }
}
~~~

**This is sample ASL with fictitious resource names.** It will not run until the input bucket/CSV, Lambda function, IAM execution role, and KMS permissions exist. It uses default **JSONPath `QueryLanguage`**; in **`JSONata`** workflows, fields differ (such as **`Arguments`** instead of `Parameters` and **`Items`** instead of `ItemsPath`). Never mix syntaxes.

### 7.1. Explaining the key fields

| Field | Role | In this example |
|---|---|---|
| **`ItemReader`** | Reads input records | S3 CSV with `FIRST_ROW` header |
| **`ItemSelector`** | Packages each record and index | Child input has **`record`**, **`index`** |
| **`ItemProcessor`** | Steps run per record | Lambda Invoke |
| **`Mode: DISTRIBUTED`** | Spawns child executions in a Map Run | Distributed processing |
| **`ExecutionType: STANDARD`** | Chooses Standard children | Independent execution history |
| **`MaxConcurrency: 50`** | Up to 50 active children concurrently | Prevents slamming RDS with 10,000 Lambdas |
| **`ToleratedFailureCount: 5`** | Allows up to 5 failed items/children before Map Run trips threshold | Does not discard error records; inspect `ResultWriter` |
| **`ResultWriter`** | Writes status-grouped results to S3 | Prevents results from bloating parent payload |

**`ToleratedFailureCount = 5` does not guarantee the Map stops the instant the 6th child fails.** AWS may already have dispatched sibling children, some of which finish while the threshold trips. Backends must tolerate overlap and duplicate runs during retries/redrives.

### 7.2. Actual child input

A child receives:

~~~json
{
  "record": {
    "orderId": "o-101",
    "totalAmount": "120.00",
    "currency": "USD"
  },
  "index": 0
}
~~~

The CSV reader emits **string values**; Java applications should parse amounts accurately using **`BigDecimal`** and validate currency and schema. Never assume CSV fields arrive as JSON numbers or that every row is clean. Use **`record ID + dataset version/job ID`** as the idempotency key to prevent duplicate financial effects.

### 7.3. Where are results written?

**`ResultWriter`** writes child run outputs to S3 by status and format rather than returning all records into the parent's 256 KiB payload limit. Monitor output paths, IAM **`s3:PutObject`**, and KMS permissions if the bucket uses SSE-KMS. **The `ResultWriter` bucket must reside in the same AWS account and Region as the state machine** per AWS docs; violating this can trigger **`States.ResultWriterFailed`**.

## 8. `ItemReader`: data sources, formats, and safety

In Distributed `Map`, **`ItemReader`** defines the item set for the Map Run. Depending on requirements, it accepts:

| Source | How it reads | Key points |
|---|---|---|
| JSON array/object from state input | No S3 `ItemReader` needed | Still constrained by parent's 256 KiB payload |
| **CSV S3** | **`s3:getObject`** + `InputType` `CSV` | Headers, delimiters, encoding, schema, PII |
| **JSON S3** | `InputType` `JSON` | Can select a nested node with **`ItemsPointer`** |
| **JSON Lines S3** | `InputType` `JSONL` | One valid JSON record per line |
| **Parquet S3** | `InputType` `PARQUET` | Columnar data, types/schemas, S3 permissions |
| **S3 object listing** | **`s3:listObjectsV2`** | Returns object metadata or reads contents via `Transformation` |
| **Athena manifest** | Manifest pointing to data files | Ensures consistent input set and source permissions |
| **S3 Inventory manifest** | Object list from S3 Inventory | Schema and files per supported inventory format |

`ItemReader` supports compression formats like **GZIP/ZSTD** for supported AWS data types. AWS also supports **`Transformation: LOAD_AND_FLATTEN`** on **`S3 ListObjectsV2`** sources to read and flatten records inside matching objects instead of only iterating object metadata.

**Never omit a trailing slash on S3 listing prefixes.** Prefix **`exports/order`** matches both **`exports/orders/`** and **`exports/order-backup/`**; include the trailing **`/`** and verify object scope. Pair least-privilege **`s3:ListBucket`** scoped by prefix with **`s3:GetObject`** on exact resources.

### 8.1. Source file size differs from per-child input size

An input S3 CSV can exceed 256 KiB, yet **each child execution's input/output is still capped at 256 KiB**. AWS documents separate limits for **each S3 source file** and supported formats; for oversized items, use **`ItemSelector`** to extract only needed fields or keep large blobs in S3 and pass object keys. Never inline whole binary/base64 files into a child input.

When using **`ItemsPointer`** on nested JSON, verify the pointer targets a valid array/object. When using **`LOAD_AND_FLATTEN`**, semantics shift from **one child per object metadata** to **items extracted from inside files**; test fan-out counts so you do not launch far more children than budgeted.

## 9. `ItemBatcher`: grouping items to cut orchestration overhead

**`ItemBatcher`** in Distributed `Map` packs multiple items into **one child execution**. This helps when processing 1,000,000 rows that each take milliseconds, where spawning one execution per row incurs heavy orchestration overhead and cost.

Example declaration:

~~~json
{
  "ItemBatcher": {
    "MaxItemsPerBatch": 100,
    "MaxInputBytesPerBatch": 131072,
    "BatchInput": {
      "schemaVersion": "2026-11"
    }
  }
}
~~~

This is a **fragment** inside Distributed `Map`, not a standalone state machine. **`MaxItemsPerBatch = 100`** and **`MaxInputBytesPerBatch = 131,072` bytes** (128 KiB) cap each child at 100 items and below the byte threshold—whichever limit is reached first closes the batch. Batch input size must still stay within Step Functions quotas.

Child input typically looks like:

~~~json
{
  "BatchInput": {
    "schemaVersion": "2026-11"
  },
  "Items": [
    {"orderId": "o-101"},
    {"orderId": "o-102"}
  ]
}
~~~

**Trade-off:** batching lowers child workflow counts while increasing per-child runtime and retry blast radius. If one bad row fails the **entire batch**, hundreds of succeeded rows might re-run. Workers should return **per-item outcomes**, use checkpoints/idempotency, and isolate poison records before tuning batch sizes.

### 9.1. Impact on concurrency

If `Map` has **`MaxConcurrency = 50`** and each batch holds 100 rows, roughly **5,000 rows can be in flight across 50 child executions**, though that is only a batch-size calculation—there is no guarantee workers process 100 rows concurrently. A child Lambda may process its 100 rows **sequentially**, and total throughput depends on handler duration, memory, databases, and service quotas.

## 10. Data transformation: `InputPath`, `ItemSelector`, `ResultSelector`, `ResultPath`

A Step Functions state should carry **only necessary data**, not raw responses from every service. For instance, Lambda Invoke returns SDK/HTTP metadata when the next branch only needs **`Payload`**.

| Component | Where commonly used | Purpose |
|---|---|---|
| **`InputPath`** | JSONPath states | Selects a subset of state input |
| **`Parameters`** | JSONPath Task/Pass and integrations | Builds Task request payload |
| **`ItemsPath`** | JSONPath `Map` | Selects array to iterate |
| **`ItemSelector`** | `Map` | Builds each iteration/child input from value/index/global state |
| **`ResultSelector`** | JSONPath states | Selects/reshapes results before `ResultPath` |
| **`ResultPath`** | JSONPath states | Merges result into input, or discards result with **`null`** |
| **`OutputPath`** | JSONPath states | Filters final state output |
| **`ResultWriter`** | Distributed `Map` | Writes child results to S3 instead of accumulating large outputs |
| **`Assign` / `Output`** | JSONata or workflow variables as supported | Different syntax/transforms; do not mix JSONPath fields mechanically |

### 10.1. Three ways to avoid `States.DataLimitExceeded`

1. **Keep references instead of datasets:** pass **`s3://bucket/key`**, a record ID, or a job ID instead of carrying whole files in state.
2. **Trim per-item outputs:** use **`OutputPath`/`ResultSelector`** to drop unneeded metadata, or **`ResultPath: null`** once side effects are persisted in a DB.
3. **Use `ResultWriter`** in Distributed `Map` to export large outputs to S3 and forward only paths/summaries to later states.

**`States.DataLimitExceeded`** is not cured by retrying. Once state I/O exceeds the 256 KiB hard quota, change the data design; a generic `Catch` **`States.ALL`** cannot rescue this terminal failure as desired.

## 11. `Retry`, `Catch`, and failure thresholds in parallel processing

**`Retry`** re-attempts a Task/State on defined errors; **`Catch`** branches to error handling once retries are spent or an error is unretriable. These are orchestration controls—they **do not roll back** writes already committed to S3, DynamoDB, RDS, or external systems.

### 11.1. Bounded retries with exponential backoff

Example Lambda Task fragment retrying transient faults:

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:validate-one",
    "Payload.$": "$"
  },
  "OutputPath": "$.Payload",
  "Retry": [
    {
      "ErrorEquals": [
        "Lambda.ServiceException",
        "Lambda.AWSLambdaException",
        "Lambda.SdkClientException"
      ],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2
    }
  ],
  "End": true
}
~~~

This is a **Task state fragment**, not a full state machine. When many tasks run concurrently, add **`MaxDelaySeconds`/`JitterStrategy`** or jitter per Step Functions capabilities to prevent retry storms. Never retry **validation errors, invalid inputs, permission denials**, or non-idempotent financial calls endlessly.

### 11.2. Catching per branch or per item

To allow a batch to **tolerate bad records without aborting the entire job**, place `Catch` inside **`ItemProcessor`**:

~~~json
{
  "ProcessOne": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:validate-one",
      "Payload.$": "$"
    },
    "OutputPath": "$.Payload",
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.error",
        "Next": "RecordFailure"
      }
    ],
    "End": true
  },
  "RecordFailure": {
    "Type": "Pass",
    "Parameters": {
      "ok": false,
      "reason.$": "$.error.Error"
    },
    "End": true
  }
}
~~~

These two states are a **fragment for `ItemProcessor.States`**, not standalone ASL. When **`Catch` converts an error into a clean output**, Step Functions treats the **child execution as succeeded at the workflow level**: **`ToleratedFailureCount`/`Percentage` will not count that item as a failed child**. If you want Map Run thresholds to track failures, let the child fail after recording error details or transition to a controlled **`Fail` state**.

With `Parallel`, a branch can catch internally and return **`ok=false`** so the parent evaluates all branches. Still, if one branch executed an irreversible action, a failure in another branch needs explicit **compensation/saga** logic—never mistake `Catch` for a DB rollback.

### 11.3. Distributed `Map` failure thresholds

| Field | Meaning | Example |
|---|---|---|
| **`ToleratedFailureCount`** | Maximum failed items allowed | `5` |
| **`ToleratedFailurePercentage`** | Maximum percentage of failed/timed-out items | `2` (2%) |
| **`ToleratedFailureCountPath`** | Dynamic count read from input (JSONPath) | `$.allowFailures` |
| **`ToleratedFailurePercentagePath`** | Dynamic percentage read from input (JSONPath) | `$.allowFailurePct` |
| **`States.ExceedToleratedFailureThreshold`** | Map Run failure error when threshold is breached | Inspect item failures and exported outputs |

Without tolerances set, **0% failures are tolerated** by default. If both count and percentage are configured, **exceeding either one** fails the Map Run. Tolerances express business rules like "allow up to 10 bad rows," yet **they do not turn bad data into valid data**. Downstream steps must still inspect counts and report failed records.

### 11.4. Distinguishing infrastructure vs. business errors

| Category | Examples | Sensible action |
|---|---|---|
| **Transient** | Lambda 5xx, throttling, network timeouts | Retry with backoff + jitter |
| **Permanent input** | Bad CSV schema, missing object key | Record failure/DLQ; do not retry endlessly |
| **Authorization** | S3 `AccessDenied`, missing IAM role permissions | Fix roles, KMS, resource policies |
| **Capacity** | RDS max connections, downstream rate limits | Lower concurrency, queue/throttle, scale capacity with evidence |
| **Data limit** | State output > 256 KiB | Pass S3 references / `ResultWriter` |
| **Tolerated failure exceeded** | Too many child workflows failed | Inspect dataset, fix worker, then redrive |

### 11.5. Note on `States.ALL` and terminal errors

**`States.ALL`** catches many errors in `Retry`/`Catch`, yet **does not catch all Step Functions errors**. Errors like **`States.Runtime`** and **`States.DataLimitExceeded`** are terminal per service rules; never rely on a generic `Catch` to mask JSONPath or payload-size bugs. Validate ASL inputs, paths, and payload sizes before deployment.

## 12. Redrive, idempotency, and recovering batch jobs

**Redrive** resumes eligible failed executions per AWS rules. In **Distributed `Map`**, when an eligible parent **Standard execution** is redriven, Step Functions can redrive only failed child executions in the Map Run rather than re-running every item. Note the difference:

- **Standard children:** redriven from their failed state using original execution history when eligible, preserving detailed history.
- **Express children:** on Map Run redrive, failed children **restart from the beginning** via `StartExecution` rather than resuming mid-state.
- **Parent Standard executions** are subject to status, redrive window, and history quota rules. AWS documents **14 days** after execution end as the redrive window, among other constraints.
- Certain **`States.DataLimitExceeded`/`States.Runtime`** faults may require a new Map Run or fail redrive eligibility; check actual status.

**Redrive does not undo side effects that already occurred before failure.** For instance, a child that inserted an order into a DB and timed out before reporting success will re-run on retry/redrive and write duplicates if not idempotent.

### 12.1. Idempotency keys

Use a stable key such as:

~~~text
jobId + datasetVersion + recordId + operationType
~~~

For example, **`import-2026-11-20 + s3-etag-or-version + o-101 + upsert`**. Never rely solely on `Map.Item.Index` if dataset row order can change or new files are uploaded. Enforce **unique constraints**, DynamoDB conditional writes, or transaction semantics so replays produce no duplicate side effects.

### 12.2. When is manual/automated compensation actually needed?

| Operation | Replay risk | Safeguard |
|---|---|---|
| Read S3 image, write deterministic thumbnail | Lower | Conditional upsert/overwrite, version check |
| Catalog import via upsert | Medium | Schema validation, idempotency key, version |
| Send email/SMS | High duplicate-notification risk | Notification deduplication and send-status ledger |
| Charge / refund money | Very high | Payment idempotency key, ledger, saga/compensation |
| Write across multiple independent systems | High | Transactional outbox, saga, state audit |

In `Parallel` with multiple mutating branches, avoid **outer `Parallel` retries** without strict idempotency contracts. In Distributed `Map`, set **failure tolerances** to match business rules and emit a list of records needing manual follow-up.

## 13. Concurrency and backpressure: fast without breaking the backend

Concurrency sizing depends on more than Step Functions limits. Real bottlenecks sit in **Lambda Reserved/Account Concurrency, ECS/Batch quotas, RDS connections, DynamoDB RCUs/WCUs, API rate limits, NAT/VPCE, and service throttling**.

### 13.1. Simple estimation

If one worker averages **2 seconds/item**, `MaxConcurrency` **50** yields an ideal throughput of roughly **25 items/second** assuming zero overhead or throttling. However, a database handling only **10 writes/second** becomes the bottleneck; raising `MaxConcurrency` to 500 only generates retries and extra charges.

**This is an approximation.** Real-world latency distributions, batch sizes, cold starts, retries, networks, Lambda throttles, and capacities fluctuate over time. Measure real throughput, p95/p99 latency, and backlogs before tuning.

### 13.2. Dynamic limits

In JSONPath workflows, you can set:

~~~json
{
  "MaxConcurrencyPath": "$.workerLimit"
}
~~~

This is a **`Map` state fragment**. Input must supply `workerLimit` as a valid integer; **never** specify both `MaxConcurrency` and `MaxConcurrencyPath` together. In JSONata, use supported ASL expressions. Never let untrusted user input set concurrency arbitrarily and trigger thousands of downstream calls and runaway bills—enforce organizational policy/capacity bounds.

### 13.3. How to protect downstream systems

1. Start batch jobs in production with a **conservative `MaxConcurrency`** and raise after load testing.
2. Cap Lambda concurrency and container worker capacity independently.
3. Use **retries with backoff/jitter** on 429/5xx, bounding attempt counts and total duration.
4. Use **`ItemBatcher`** for tiny rows, increasing batch size only as handlers handle the load.
5. Use **SQS** to buffer long-term bursts, or **AWS Batch/ECS** for CPU-heavy workloads.
6. For databases, use connection pooling/proxies/partitioning as needed and verify consistency.
7. Set timeouts, cancellation/compensation, and threshold alerts.

### 13.4. Quotas to verify before go-live

| Quota / limit | Reference value from AWS docs | Meaning |
|---|---|---|
| State input/output | **256 KiB** | Data payload limit per state/execution |
| Standard history | **25,000 events** | Inline iterations consume parent history |
| Inline `Map` | **40 concurrent iterations** | Data in JSON array |
| Distributed `Map` | **10,000 concurrent child executions** per Map Run | Hard upper bound, not a target recommendation |
| Open Map Runs | **1,000** per account/Region per quota docs | New Map Runs may stay pending when exceeded |
| Express execution duration | **Max 5 minutes** | Unsuitable for multi-hour item jobs |
| Standard execution duration | **Max 1 year** | Suits long workflows within quotas |
| State machine definition | **1 MiB** per API quota | Never inline thousands of items in definition |

AWS limits/throttling vary by Region and over time. Beyond hard quotas, monitor orchestration throughput, **`StartExecution` API**, Lambda API, S3 requests, Batch, and downstream services. Check **Service Quotas** for your actual account/Region before launch.

## 14. IAM and security when running `Parallel`/`Map`

The **Step Functions execution role** is assumed by Step Functions to call Task integrations, read datasets, and write results. **Lambda execution roles**, **ECS task roles**, or **AWS Batch job roles** still govern each worker's business permissions.

### 14.1. Permission matrix

| Principal | Illustrative permissions | Why |
|---|---|---|
| **State machine role** | **`lambda:InvokeFunction`** on worker | Step Functions invokes Lambda |
| **State machine role** | **`s3:GetObject`** on input prefix | Distributed Map `ItemReader` reads dataset |
| **State machine role** | **`s3:PutObject`** on result prefix | `ResultWriter` writes child outputs |
| **State machine role** | **`states:StartExecution`/`DescribeExecution`** on exact child workflow ARN | Distributed Map starts and monitors child executions |
| **Worker Lambda role** | DynamoDB, S3, RDS secrets per business logic | Handler executes domain work |
| **Operator IAM principal** | `DescribeExecution`/`DescribeMapRun`/`ListMapRuns`, read logs | Monitor batches without modifying production |
| **CI/CD role** | `Create`/`UpdateStateMachine`, scoped `iam:PassRole` | Controlled workflow governance |

Example **identity-based IAM policy fragment** for the state machine role in section 7:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadBatchInput",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::batch-lab-input-example/imports/*"
    },
    {
      "Sid": "WriteBatchResults",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::batch-lab-results-example/results/*"
    },
    {
      "Sid": "InvokeOnlyWorker",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-one"
    },
    {
      "Sid": "StartChildWorkflow",
      "Effect": "Allow",
      "Action": "states:StartExecution",
      "Resource": "arn:aws:states:ap-southeast-1:111122223333:stateMachine:batch-workflow"
    },
    {
      "Sid": "ObserveChildWorkflow",
      "Effect": "Allow",
      "Action": "states:DescribeExecution",
      "Resource": "arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:*"
    }
  ]
}
~~~

**This sample requires replacing ARNs and adapting to real integrations**—it is not a universal permission bundle. Redrives may require **`states:RedriveExecution`** on execution ARNs per documentation. If S3 inputs use **SSE-KMS**, bucket/KMS key policies and **`kms:Decrypt`** must grant access to the state machine role; `ResultWriter` with SSE-KMS may need **`kms:GenerateDataKey`** and matching key policies. **An IAM Allow never overrides an explicit Deny** in bucket policies, KMS policies, SCPs, or VPC endpoint policies.

### 14.2. Least privilege on datasets

Never grant **`s3:*` account-wide** to a state machine just to read one CSV. Scope to the exact bucket/prefix, require HTTPS, and use KMS/bucket policies and S3 versioning for reproducibility. When `ItemReader` uses **`ListObjectsV2`**, grant **`s3:ListBucket`** on the bucket with a prefix condition, separate from **`s3:GetObject`** on object ARNs.

### 14.3. Protecting sensitive data

- **Never put raw PII or secrets into execution names, state inputs/outputs, or CloudWatch Logs** unnecessarily.
- For multi-tenant workflows, isolate dataset prefixes, KMS permissions, job metadata, and outputs per tenant.
- Restrict **`StartExecution`/`StopExecution`/`RedriveExecution`**; re-running workflows can trigger business side effects.
- For callback patterns, treat task tokens as sensitive; never log or share them loosely.
- Use **CloudTrail** for control-plane API audits and Step Functions logging as configured; never assume CloudTrail logs every child's full data payload by default.
- Apply tags/ownership and retention/lifecycle rules to **`ResultWriter` outputs**, as batch results may hold sensitive inputs or error details.

## 15. Monitoring and AWS CLI for inspecting a Map Run

### 15.1. Observability sources

| Source | What to observe |
|---|---|
| **Step Functions execution graph** | Which state/branch/Map failed |
| **`DescribeExecution` / `GetExecutionHistory`** | Parent/Standard child statuses and transitions |
| **`DescribeMapRun`** | Map Run progress and counts of succeeded/failed/timed-out/pending children |
| **CloudWatch Step Functions metrics** | `ExecutionsSucceeded`/`Failed`/`TimedOut`, Map Run and child metrics |
| **CloudWatch Logs** | Workflow logs as configured, especially for Express |
| **Lambda/ECS/Batch logs** | App errors, timeouts, networking, and retries |
| **S3 `ResultWriter` outputs** | Per-child successes/failures and outputs |
| **CloudTrail** | Who updated definitions/roles or called `StartExecution`/Redrive |

**A succeeded Map Run does not prove 100% of records succeeded** if failure tolerances were set or child errors were caught into success outputs. Inspect **Map Run item counts, `ResultWriter` error files, and business reconciliation** before declaring a job done.

### 15.2. Validate ASL before deployment

Once a sample ASL file is saved in your project (not a required file creation step in this lesson):

~~~bash
# Validates definition only; does not create a state machine.
aws stepfunctions validate-state-machine-definition \
  --region ap-southeast-1 \
  --definition file://workflow.asl.json \
  --type STANDARD
~~~

The API returns **`result = OK/FAIL`** plus diagnostics. Automation should gate on **`result`** rather than hardcoding warning text, as AWS may refine diagnostic wording. Static validation **does not prove** Lambda ARNs, IAM, S3 keys, networking, or KMS work; test in staging.

### 15.3. Inspecting executions and Map Runs (read-only)

~~~bash
# Inspect parent execution.
aws stepfunctions describe-execution \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:run-001

# List Map Runs of parent execution.
aws stepfunctions list-map-runs \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:run-001

# Use the real MapRunArn returned by list-map-runs.
aws stepfunctions describe-map-run \
  --region ap-southeast-1 \
  --map-run-arn arn:aws:states:ap-southeast-1:111122223333:mapRun:batch-workflow/demo:REPLACE_UUID

# Optionally list child executions of a Map Run.
aws stepfunctions list-executions \
  --region ap-southeast-1 \
  --map-run-arn arn:aws:states:ap-southeast-1:111122223333:mapRun:batch-workflow/demo:REPLACE_UUID
~~~

**`REPLACE_UUID`** is only a placeholder; Map Run ARNs are generated by AWS rather than guessed from execution IDs. For **Express children**, accessing history/traces differs from Standard; enable proper logging and Map Run tracking. If a Lambda fails due to a database fault, `DescribeMapRun` reports only that the child failed—read Lambda logs/metrics for root cause.

### 15.4. Redriving affects data

~~~bash
# Mutating command: run only after fixing root cause,
# checking idempotency, budgets, and obtaining approval.
aws stepfunctions redrive-execution \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:run-001
~~~

Redrive can **re-launch failed child executions**, rewriting databases or re-sending notifications if handlers are not idempotent. Before running, check eligibility status, Standard vs. Express child replay semantics, KMS permissions, and dataset state.

## 16. Example architecture: bulk catalog import

**Context:** daily, a partner uploads **`products.csv`** (~300,000 rows) to S3. The system must validate rows, normalize each product, upsert into DynamoDB, generate an error report, and notify only after completion.

### 16.1. Overall design

~~~mermaid
flowchart TD
    S3["S3 input dataset<br/>products.csv"] --> EVT["EventBridge / Scheduler"]
    EVT --> PARENT["Step Functions Standard parent"]
    PARENT --> PRE["Validate manifest/schema<br/>Lambda Task"]
    PRE --> MAP["Distributed Map<br/>MaxConcurrency=100"]
    S3 --> READER["ItemReader CSV"]
    READER --> BATCH["ItemBatcher<br/>e.g., 50 rows/child"]
    BATCH --> MAP
    MAP --> CHILD["Child workflow<br/>Validate → Normalize → Upsert"]
    CHILD --> DDB["DynamoDB<br/>Idempotent writes"]
    MAP --> RESULT["ResultWriter S3<br/>success/failure"]
    RESULT --> SUMMARY["Summarize counts/errors"]
    SUMMARY --> NOTIFY["SNS / EventBridge notification"]
    SUMMARY --> AUDIT["DynamoDB job ledger<br/>jobId + status"]
~~~

### 16.2. Design sequence

1. **Immutable dataset source:** record S3 input **`VersionId`/`ETag`** to identify the exact dataset processed.
2. **Job initialization:** assign **`jobId`**, persist job metadata, and key idempotency on job/version to avoid duplicate triggers.
3. **Pre-flight validation:** check file size, schema/headers, encoding, and IAM/KMS before fan-out.
4. **Distributed `Map`:** read CSV from S3, select needed fields, and batch carefully.
5. **Worker:** parse types cleanly, enforce business rules, and conditionally upsert by product/version.
6. **`ResultWriter`:** export child outcomes, separating succeeded/failed records and keeping report paths.
7. **Reconcile:** input records = succeeded + failed + unknown; save stats and check tolerances.
8. **Notify:** send verified status only; report partial failures explicitly rather than claiming "100% success."
9. **Retention:** S3 lifecycle policies for inputs/results, CloudWatch logs, and the job ledger.

### 16.3. Where does `Parallel` fit in the same architecture?

Before Distributed `Map`, the workflow can run **`Parallel`** to:

- Validate **CSV schema**.
- Check **reference catalogs/currency codes**.
- Check **storage quotas and bucket permissions**.

These three branches perform **distinct validation logic** against job metadata. Once all succeed, the parent enters Distributed `Map`. **Never** manually declare 300,000 `Parallel` branches; `Map` is the dataset iteration construct.

### 16.4. What if 2% of records fail?

If the business tolerates up to 2% invalid rows, two designs behave differently:

| Approach | Consequence |
|---|---|
| Worker returns an **error object while child succeeds** | Map Run does **not** count the child as failed; you must aggregate invalid-row rates yourself |
| Child workflow **`Fail`s** on invalid items with `ToleratedFailurePercentage` | Map Run counts failed items/children; ensure retryable errors are not conflated with permanent errors |

With **`ItemBatcher`**, a child holding 50 records can be marked as one failed execution even if only one row was bad, meaning Map Run failure rate no longer equals row error rate. If business rules measure **record** percentages, have workers emit **per-record outcomes** and reconcile by **record count** rather than equating failed child batches to failed rows.

### 16.5. Single-AZ failures and resilience

Step Functions is a Regional AWS-managed service; Lambda/ECS workers have their own availability mechanics and limits. If an ECS task fails during a single-AZ disruption, children need retries/backoff and healthy-AZ rescheduling, while S3 and DynamoDB provide Regional durability per their SLAs. Multi-AZ backend compute **does not automatically solve** duplicate writes from retries, missing permissions, or bad data models.

**Step Functions Distributed `Map` is not a default Multi-Region DR solution.** For Region-level RTO/RPO, plan separately for state machine definitions, input/output S3 buckets, KMS keys, worker images, database replication, event replay, and duplicate prevention.

## 17. `Parallel`/`Map` troubleshooting runbook

### 17.1. Symptom and investigation table

| Symptom | Possible cause | Priority evidence |
|---|---|---|
| **`Parallel` failed early** | Uncaught error in one branch, or a `Fail` state | Per-branch execution history, Task logs |
| **Workflow succeeded yet a check was skipped** | Branch caught error into `ok=false` and parent ignored it | Output array and fan-in validation |
| **Inline `Map` hit `States.DataLimitExceeded`** | Large output array / raw Lambda metadata kept in state | Execution input/output size, `OutputPath`/`ResultPath` |
| **Inline `Map` hit history limit** | Too many iterations, retries, or Task transitions | Parent execution event count vs. 25,000 limit |
| **`ItemsPath` cannot find array** | `InputPath` stripped the field or wrong key | Test input path, pre-Map state data |
| **Child input missing record** | `ItemSelector` points to wrong Context/Data path | Inspect `ChildExecution` input JSON |
| **Distributed `Map` cannot read S3** | Missing `s3:GetObject`/`ListBucket`, `kms:Decrypt`, wrong key | `ItemReader` path, state machine IAM role, KMS |
| **`States.ItemReaderFailed`** | Dataset unreadable or invalid format | `ItemReader`, S3 source, permissions/schema |
| **`States.ResultWriterFailed`** | Result bucket in wrong account/Region, missing `PutObject`/KMS | `ResultWriter` path, bucket/role policy, KMS |
| **`States.ExceedToleratedFailureThreshold`** | Too many children failed/timed out | `DescribeMapRun` counts, child errors, worker logs |
| **Child Lambdas throttled** | `MaxConcurrency` too high, low reserved/account concurrency | Lambda `Throttles`/`ConcurrentExecutions` |
| **DB connection storm** | Concurrent children exhausting connections | RDS connections/latency, backoff/concurrency |
| **Map Run `Pending` too long** | Dispatch throttling/open Map Run quota or capacity limits | `DescribeMapRun`, Service Quotas, status events |
| **S3 output missing or empty** | Invalid child outputs, wrong `ResultWriter`/path/permissions | `ResultWriter` artifacts, Map status, worker outputs |
| **Redrive duplicates transactions** | Non-idempotent worker, child replays side effect | Job ledger, idempotency keys, DB/notification logs |
| **Step Functions bill spikes** | Excessive child executions/transitions/retries/logs | Cost Explorer, transition metrics, Map counts |

### 17.2. Analyzing a failed Distributed `Map`

~~~mermaid
flowchart TD
    ALERT["Map Run FAILED / TIMED_OUT"] --> P["Identify parent execution ARN<br/>and Map Run ARN"]
    P --> STATUS["DescribeMapRun:<br/>Succeeded/Failed/TimedOut/Pending"]
    STATUS --> KIND{"Which error category?"}
    KIND -->|"ItemReader / ResultWriter"| IO["S3 key/Region/account,<br/>IAM, KMS, payload"]
    KIND -->|"Child execution"| CHILD["Child error + Lambda/ECS logs<br/>schema, timeout, retries"]
    KIND -->|"Quota / throttling"| LIMIT["MaxConcurrency, Service Quotas,<br/>Lambda/DB/network"]
    IO --> FIX["Fix root cause<br/>in staging"]
    CHILD --> FIX
    LIMIT --> FIX
    FIX --> RECOVER["Check idempotency and redrive eligibility"]
    RECOVER --> CHECK["Reconcile records + outputs + SLO"]
~~~

Steps:

1. Grab the **parent execution ARN**, Map Run ARN, and state machine/dataset versions.
2. Read **Map Run status/counters** to isolate input, child, output, or orchestration failures.
3. For child errors, sample a failed item and classify: **schema, IAM, KMS, timeout, throttling, or business validation**.
4. Inspect **logs** in the right Region, worker service, child execution ARN, and correlation ID.
5. For capacity errors, lower concurrency/batch size before blindly requesting quota increases.
6. Fix root cause, reproduce in staging, and confirm business side effects are idempotent.
7. If eligible, **redrive** carefully; otherwise launch a targeted new job with only the failed records and an idempotency ledger.
8. Reconcile **input records, successes, failures, skipped items, DLQs, and S3 outputs** before signaling completion.

### 17.3. Why not retry the entire job when one item fails?

An input with 100,000 records has one row containing malformed characters. Retrying the entire job 5 times will never fix that row, while multiplying state transitions, Lambda/S3/DynamoDB writes, and duplicate risks. Write **permanent validation errors** to a failure report, and retry **transient errors** with bounded backoff. After fixing the source, replay only failed records/batches.

## 18. Costs and orchestration optimization

Step Functions bills differently for **Standard** and **Express**, while integrations like Lambda, ECS, Batch, S3, Glue, and CloudWatch carry separate charges. Never estimate total cost solely by item count.

| Item | What to include in estimates |
|---|---|
| **Standard transitions** | Transitions, `Retry`/`Catch`, branches, and child workflows |
| **Express requests/duration/memory** | Execution counts, duration, and memory per current pricing |
| **Distributed Map child executions** | Child starts, `STANDARD`/`EXPRESS` type, inner Task states |
| **`ItemBatcher`** | Cuts child starts, yet may raise batch retries and duration |
| **Lambda/ECS/Batch** | CPU/RAM, duration, provisioned capacity, cold starts, Spot |
| **S3/KMS** | `GetObject`/`PutObject`/`ListObjects`, storage, KMS API calls, encryption |
| **CloudWatch/X-Ray** | Logs, metrics/tracing, retention, and queries |
| **External dependencies** | RDS/DynamoDB writes, API rate limits, notifications |
| **Redrives/retries** | Tasks and child executions re-executed |

### 18.1. Qualitative batching example

With **1,000,000 items**, spawning one child execution per item can produce up to one million child workflow starts across the job. Batching **100 items** per child reduces ideal child executions to roughly **10,000**, in exchange for each child handling multiple records and tracking per-item results. This illustrates the model, **not a price quote**; account for the 256 KiB batch payload limit, item sizes, worker costs, and retry requirements.

### 18.2. Valid cost optimizations

- Do not spawn a Map child per tiny record when workers can safely process batches.
- Use **Express children** for short, replay-safe tasks that do not need unsupported service integration patterns.
- Avoid pointless retries; separate schema bugs from transient infrastructure faults.
- Trim payloads and log verbosity; avoid emitting huge data objects repeatedly.
- Match **`MaxConcurrency` to backend throughput** so throttling/overload does not inflate bills.
- Configure S3 lifecycles for inputs/results and CloudWatch retention.
- Compare **Step Functions** against **SQS + workers/Glue/Batch** when workloads are simple, long-lived, or need buffering rather than centralized fan-in.

**Never cut costs by disabling logging, KMS, or access checks.** Decisions must balance **security, reliability, auditability, latency, and TCO**.

## 19. Scenario exercises

### Scenario A — Validating an order across three APIs

An order must call **Inventory**, **Shipping**, and **Fraud** independently. All three results are needed before authorizing payment; each API takes 200–800 ms.

**Question:** should you use `Parallel` or `Map`?

**Hint:** **`Parallel`** with three independent branches and `ResultPath` storing outputs, followed by evaluating results. Give each branch proper timeouts/retries and decide whether errors fail fast or return **`ok=false`**. Never treat `Parallel` as a transactional rollback.

### Scenario B — 30 products to validate

An order input contains an array of 30 products, each checked by the same Lambda. JSON payload is small and each item needs only one state.

**Question:** which mode and concurrency setting fit?

**Hint:** **Inline `Map`** with `ItemsPath` **`$.items`** and `MaxConcurrency` tuned to downstream (e.g., 5). Use `ItemSelector` to pass `orderId`, item, and index, and `ResultPath` to keep results. Verify total output stays under 256 KiB.

### Scenario C — Processing 500,000 CSV rows

A partner uploads a 500,000-row file to S3. Each row must be normalized and upserted to DynamoDB, with error statistics and an end-of-job report.

**Question:** is Inline `Map` sufficient?

**Hint:** unsuitable due to dataset size and execution history limits. Use **Distributed `Map`** with CSV `ItemReader`, `ItemBatcher` if needed, `MaxConcurrency` sized to DynamoDB capacity, S3 `ResultWriter`, failure thresholds, and job reconciliation.

### Scenario D — 100 rows/batch, 1 bad row

One child processes 100 rows, and a single schema error fails the child. The Map Run sets `ToleratedFailurePercentage` to 1%.

**Question:** can you conclude only 1% of records failed?

**Hint:** no. Tolerance counts failed items/child executions per Map Run semantics, while each child holds a whole batch. Emit **per-row results**, separate permanent validation errors from transient failures, and reconcile by record count.

### Scenario E — 10,000 concurrent Lambdas crash RDS

An engineering team omits **`MaxConcurrency`** after seeing Distributed `Map` supports up to 10,000 child executions. After deployment, RDS runs out of connections and Lambdas retry endlessly.

**Question:** which layers need fixing?

**Hint:** cap `MaxConcurrency` to DB capacity, tune batch size/connection pooling or RDS Proxy, set Lambda concurrency limits, add backoff + jitter, and benchmark p95/p99. Raising Step Functions limits never cures RDS saturation.

### Scenario F — Redrive sends duplicate emails

A child sends an email successfully yet times out before reporting success. The Map Run fails, an operator redrives, and the same customer gets emailed twice.

**Question:** does Step Functions guarantee exactly-once emails?

**Hint:** no. Maintain an idempotency/notification ledger keyed on `jobId + recipient + template/version`, persist send status, and separate committed side effects from orchestration outcomes. Never blindly retry external side effects.

### Scenario G — `ResultWriter` fails

A parent workflow runs in `ap-southeast-1` in Account A, while `ResultWriter` targets a bucket in another Region/account and the role lacks `PutObject`.

**Question:** what should you check first?

**Hint:** the `ResultWriter` S3 bucket must be in the same account and Region as the state machine, with exact **`s3:PutObject`** and KMS policies if customer-managed encryption is used. Inspect **`States.ResultWriterFailed`** rather than increasing `MaxConcurrency` to fix permissions.

### Scenario H — Mixing JSONPath and JSONata

A developer copies **`Parameters`** and **`ItemsPath`** from a JSONPath example into a state declaring **`QueryLanguage: JSONata`**.

**Question:** why does validation fail?

**Hint:** JSONata uses its own fields like **`Arguments`, `Items`**, and expressions, whereas JSONPath uses `Parameters`/`ItemsPath`/`ItemSelector` with path fields. Stick consistently to one supported syntax per state/definition and validate before deploying.

## 20. Production checklist

- [ ] Pattern matches requirement: **`Parallel`** for distinct functional branches; **`Map`** for per-item iteration.
- [ ] **Inline** vs. **Distributed** chosen based on input size, history events, concurrency, and data source.
- [ ] For Distributed `Map`, parent is **Standard**, and child execution type matches duration/semantics.
- [ ] Checked hard quotas (**256 KiB, 25,000 events, 40 Inline, 10,000 Distributed**) and live account/Region quotas.
- [ ] Configured **`ItemReader`** for dataset format/S3 path, testing schema and encoding.
- [ ] Verified **`ItemSelector`/`ItemsPath`/JSONPath or JSONata** and each child's input shape.
- [ ] Evaluated **`ItemBatcher`** and how per-record failures inside each batch are tracked.
- [ ] Sized **`MaxConcurrency`** to Lambda/ECS/Batch, DB, API, and quota limits.
- [ ] Enabled **`ResultWriter`** for large outputs and long-term success/failure tracking.
- [ ] Implemented **`Retry`/`Catch`**, timeouts, backoff/jitter, and business failure tolerances.
- [ ] Separated **permanent validation errors** from retryable infrastructure faults.
- [ ] Designed **idempotency keys, job ledgers, and compensations** for all side effects.
- [ ] Secured state machine execution IAM roles, worker roles, and S3/KMS/bucket policies.
- [ ] Enabled needed logs/metrics/traces while keeping PII/secrets out of state I/O and logs.
- [ ] Defined Map Run alerts, failure counters, child logs, and business reconciliation.
- [ ] Tested S3 missing/403, KMS Deny, Lambda throttling, DB saturation, malformed CSVs, and oversized outputs.
- [ ] Tested redrive in staging, understanding Standard vs. Express child replay semantics.
- [ ] Established canary deployments/rollbacks, versioned input datasets, and AZ/Region incident recovery.
- [ ] Budgeted Step Functions transitions/Express, child executions, compute, S3/KMS, logs, and retries.
- [ ] Defined clear **COMPLETED, PARTIAL, FAILED** job states, audit reports, and retention.

## 21. Key takeaways

Use **`Parallel`** when a workflow needs **distinct branches running concurrently** on shared input and collected in **branch order**. Use **Inline `Map`** to iterate one workflow over a **small JSON array**, capped at 40 concurrent iterations and sharing parent execution history. Use **Distributed `Map`** for **large datasets**, supporting S3 **`ItemReader`**, batching, **`ResultWriter`**, **Map Runs**, and child executions (up to 10,000 concurrent per service quota). A Distributed `Map` parent must be **Standard**, while children can be **Standard** or **Express** within supported limits.

To operate safely, master **256 KiB input/output**, **25,000 history events**, **`MaxConcurrency`**, **`Retry`/`Catch`**, failure tolerances, **idempotency, and redrive**. A succeeded Map Run does not guarantee every record succeeded if errors were caught or tolerances allowed partial failures—always reconcile results. The ultimate goal is **reliable orchestration, accurate data, strong IAM/KMS security, complete observability, and costs aligned with downstream capacity**.

### Official AWS documentation to reference when deploying

- [AWS Step Functions overview](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) — workflow orchestration overview.
- [Parallel workflow state](https://docs.aws.amazon.com/step-functions/latest/dg/state-parallel.html) — branches, result arrays, and error handling.
- [Map workflow state](https://docs.aws.amazon.com/step-functions/latest/dg/state-map.html) — choosing Inline vs. Distributed.
- [Inline Map state](https://docs.aws.amazon.com/step-functions/latest/dg/state-map-inline.html) — `ItemsPath`/`ItemSelector`/`ItemProcessor`.
- [Distributed Map state](https://docs.aws.amazon.com/step-functions/latest/dg/state-map-distributed.html) — Map Runs, child workflows, concurrency, and failure thresholds.
- [Map ItemReader](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-itemreader.html) — CSV, JSON, JSONL, Parquet, manifests, S3 listing.
- [Map ItemBatcher](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-itembatcher.html) — batching, item counts/sizes.
- [Map ResultWriter](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-resultwriter.html) — exporting outputs to S3 and IAM.
- [Map input/output processing](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-fields-dist-map.html) — data transformations.
- [Choosing Standard vs Express](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html) — execution semantics and pricing.
- [Redriving Map Runs](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html) — redrive eligibility and child replay.
- [IAM policies for Distributed Map](https://docs.aws.amazon.com/step-functions/latest/dg/iam-policies-eg-dist-map.html) — `StartExecution`/`DescribeExecution`/S3.
- [Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html) — 256 KiB, 25,000 history events, and concurrency.
- [Best practices for Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html) — errors, history, payloads, costs.
- [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) and [AWS Pricing Calculator](https://calculator.aws/) — workflow and integration costs.
