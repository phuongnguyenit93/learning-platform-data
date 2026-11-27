# Workflow Steps, Expressions, and Execution Data Management

In a Java order-processing system, an API needs to check inventory, create a payment, update status, and send notifications. If every operation lives inside a single HTTP request, transient errors or timeouts can easily leave the workflow incomplete. **Google Cloud Workflows** lets you describe execution order and conditions using YAML/JSON, invoke services like Cloud Run or Google Cloud APIs, hold intermediate data, and handle errors in a controlled manner.

This lesson belongs to the **Application Orchestration and Integration** chapter in the **CLOUD_PROVIDERS_GCP** module: connecting projects, IAM, VPC, Java on Cloud Run/GKE, Cloud Storage, databases, CI/CD, reliability, and cost. The focus is on **step syntax, expressions, and per-execution data management**; Workflows does not replace business applications or databases.

After this lesson, you will be able to:

- Read and write `assign`, `call`, `switch`, `for`, `parallel`, `try/except/retry`, and `return` steps.
- Use `${...}` expressions, maps, lists, input parameters, results, and subworkflows.
- Understand variable **scope** across the workflow, loops, and parallel branches; avoid overwrites/logic races.
- Deploy a standalone workflow that calculates order totals, pass JSON input, and inspect output.
- Call Cloud Run via **OIDC** and Google Cloud APIs via **OAuth2/connectors** with least-privilege IAM.
- Design retries/idempotency, log non-sensitive data, and offload large payloads to Cloud Storage/DB.
- Explain execution memory limits, duration, quotas, logging, and per-step billing.

> **Lab note:** all project IDs, service accounts, and URLs are examples. Commands that create workflows/IAM must only be run in an authorized test project; never use real data or keys in execution arguments or logs.

## 1. Workflows Orchestrates; It Does Not Process in Place of Applications

~~~mermaid
flowchart LR
  A["Java API / Scheduler / Eventarc"] --> W["Workflows execution"]
  W --> V["Validate: steps + expressions"]
  V --> S["Cloud Run: stock service"]
  S --> P["Cloud Run: payment service"]
  P --> N["Pub/Sub / notification"]
  W --> L["Cloud Logging + execution history"]
  S --> D["Cloud SQL / Firestore"]
  P --> D
~~~

A **workflow definition** can have many independent **executions**. Each execution keeps its own variables and orchestration state; it shares no memory with other executions. Java/Cloud Run code handles business logic and persists durable data, while Workflows decides **when to call which service, which branch runs, and what to do on error**.

| Service | Primary Function | Do Not Confuse With |
|---|---|---|
| **Workflows** | Stateful orchestration, multiple API calls, conditions, retries, awaiting results | Not a message queue or database |
| **Cloud Tasks** | Queue delivering HTTP tasks with delay/rate limit/per-task retry | Does not model multi-step branching workflows itself |
| **Pub/Sub** | Message distribution, fan-out to multiple subscribers | Does not guarantee transactions across multiple services |
| **Eventarc** | Filters and routes events to supported destinations | Does not retain workflow business state |
| **Cloud Run job** | Batch processing to completion; tasks/parallelism | Does not replace multi-API sequencing and approvals |

For example: Eventarc starts a workflow when a new file is uploaded; the workflow calls Cloud Run to verify the file, then creates an OCR processing job. **Do not pass an entire PDF through Workflows variables**: pass only `bucket`, `objectName`, `generation`, and the job ID.

## 2. YAML/JSON Structure and Step Types

Workflows supports **YAML or JSON**; both formats express the same semantics. Minimal example:

~~~yaml
main:
  params: [args]
  steps:
    - initialize:
        assign:
          - customer: ${default(map.get(args, "customer"), "guest")}
    - decide:
        switch:
          - condition: ${customer == "guest"}
            next: anonymous
    - knownCustomer:
        return: ${"Hello " + customer}
    - anonymous:
        return: "Please sign in"
~~~

Steps execute **in the order defined**, unless `next`, `switch`, `return`, an error, or parallelism alters the flow. Step names must be **unique within the same subworkflow**; use descriptive names like `validate_input`, `call_orders`, `return_result` for easier execution history lookup.

| Syntax | Purpose | Keep in Mind |
|---|---|---|
| `main`, `params` | Entry point and execution parameters | Input is usually a JSON map |
| `assign` | Creates/updates variables, maps, lists | Assignments within the same step run in order |
| `call`, `args`, `result` | Calls stdlib/connector/subworkflow and saves result | `result` is a variable name, do not use `${...}` |
| `switch`, `condition` | Branches by Boolean expression | The first true condition is chosen |
| `next` | Jumps to a valid step in the same scope | `next: end` terminates without returning data |
| `for` | Iterates over a list/map or numeric range | Loop variable has its own scope |
| `parallel` | Runs branches/loops concurrently | Writing parent variables requires declaring `shared` |
| `try`, `retry`, `except`, `raise` | Retries, catches, raises errors | Only retry safe operations |
| `return` | Completes the workflow and outputs a value | Does not automatically write results to a DB |

In YAML, **indentation is significant**. The `steps` section must be a **list** (each item starting with `-`), while `assign` is a list of assignments. Do not write it like a typical Java/Spring config file expecting the engine to infer ordering.

## 3. Expressions and Data Structures Inside an Execution

Workflows uses its own runtime expression language written inside `${...}`; do not confuse it with Java expressions, shell expansion, or assume all CEL/JavaScript functions are available. Expressions are evaluated **when the step executes** and can access previously assigned variables.

~~~yaml
- init:
    assign:
      - qty: 3
      - unitPrice: 125
      - total: ${qty * unitPrice}
      - customer:
          id: "C-42"
          tier: "gold"
      - products: ["A", "B"]
- derive:
    assign:
      - customerId: ${customer.id}
      - firstSku: ${products[0]}
      - count: ${len(products)}
      - label: ${"total: " + string(total)}
- result:
    return: ${label}
~~~

The example above is a **steps snippet** to place inside `main.steps`; `total` evaluates to 375. Supported types: `null`, boolean, integer/double, string, bytes, list, and map.

| Need | How to Write | Notes |
|---|---|---|
| Read map key | `${customer.id}` or `${customer["id"]}` | Keys with special characters require `["..."]` |
| Safe map read | `${map.get(args, "orderId")}` | Missing key returns `null` |
| Default value | `${default(map.get(args, "region"), "asia-southeast1")}` | Only substitutes when value is `null` |
| Element count | `${len(items)}` | Works for list, map, string |
| Convert number to string | `${string(total)}` | Cannot concatenate string + number directly |
| Append list element | `${list.concat(items, "C")}` | Creates a **new list**, does not mutate old list in place |
| Built-in env | `${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}` | Avoids hardcoding project ID |
| Branch condition | `${total >= 1000}` | Expression must evaluate to Boolean |

**YAML pitfall:** expressions containing colons such as `${"Status: " + state}` should be wrapped in **YAML single quotes**:

~~~yaml
- format:
    assign:
      - message: '${"Status: " + state}'
~~~

Do not write `prefix-${value}` as a hybrid string; build the whole string via `${"prefix-" + value}`. The `if(condition, a, b)` function **evaluates both arguments**; if you need to avoid running a failing expression in the unchosen branch, use `switch`.

### Data Does Not Persist Automatically Outside the Execution

An `order` map in Workflows is an **execution variable**, not a Cloud SQL record. For durable transactions, write to Cloud SQL/Firestore/Cloud Storage via connectors or services; Workflows keeps **execution history/results**, but **is not a long-term business state store**.

## 4. Lab 1 — Self-Contained Workflow: Calculating Order Totals

The following example calls no external APIs. You can deploy it to test **input → validate → for loop → subworkflow → return** without creating Cloud Run or a database. Save it as `orders-total.yaml`:

~~~yaml
main:
  params: [input]
  steps:
    - initialize:
        assign:
          - orderId: ${default(map.get(input, "orderId"), "")}
          - items: ${default(map.get(input, "items"), [])}
          - total: 0
          - skus: []
          - executionId: ${sys.get_env("GOOGLE_CLOUD_WORKFLOW_EXECUTION_ID")}

    - validate:
        switch:
          - condition: ${len(orderId) == 0}
            steps:
              - missingId:
                  raise: "orderId is required"
          - condition: ${len(items) == 0}
            steps:
              - emptyItems:
                  raise: "items must not be empty"

    - accumulate:
        for:
          value: item
          in: ${items}
          steps:
            - checkQuantity:
                switch:
                  - condition: ${item.qty <= 0}
                    steps:
                      - invalidQuantity:
                          raise: "item quantity must be positive"
            - addLine:
                assign:
                  - total: ${total + item.qty * item.unitPrice}
                  - skus: ${list.concat(skus, item.sku)}

    - makeLabel:
        call: formatLabel
        args:
          orderId: ${orderId}
          amount: ${total}
        result: label

    - packageResult:
        assign:
          - output:
              orderId: ${orderId}
              total: ${total}
              skus: ${skus}
              label: ${label}
              executionId: ${executionId}
    - done:
        return: ${output}

formatLabel:
  params: [orderId, amount]
  steps:
    - build:
        return: '${"READY: " + orderId + " / " + string(amount)}'
~~~

The input must be a **JSON object** with `orderId` as a string and `items` as a list of maps containing `sku`, `qty`, `unitPrice`, where price and quantity are valid numbers. Example:

~~~json
{
  "orderId": "ORD-42",
  "items": [
    {"sku": "BOOK", "qty": 2, "unitPrice": 120},
    {"sku": "PEN", "qty": 3, "unitPrice": 15}
  ]
}
~~~

The result has `total = 285`, `skus = ["BOOK", "PEN"]`, and `label = "READY: ORD-42 / 285"`. The `executionId` field changes on every run. The `unitPrice` field only illustrates integers; for real money, **do not use double arithmetic as a financial source of truth**. Store integers in the smallest currency unit (e.g., VND/cents) and verify with a transactional service/DB.

**Why use `formatLabel`?** It is a **subworkflow** that takes parameters and returns a value. `main` invokes it via `call`, passes `args`, and stores the return value in `label`. Subworkflows do not automatically share all local variables from `main`.

## 5. Deploying, Passing JSON Input, and Checking Results

Deploying Workflows requires a project with billing and the Workflows API enabled, the Google Cloud CLI, a deployer account with appropriate permissions (e.g., `roles/workflows.admin`), and `iam.serviceAccounts.actAs` on the workflow runtime service account. Callers **running executions** use execution creation permissions like `roles/workflows.invoker`; they do not need the Admin role just to invoke a workflow.

~~~bash
PROJECT_ID="my-workflows-lab"
REGION="asia-southeast1"
WORKFLOW="orders-total-lab"
WF_SA="orders-orchestrator@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable workflows.googleapis.com \
  workflowexecutions.googleapis.com

# Only create the service account if it does not already exist.
gcloud iam service-accounts create orders-orchestrator \
  --display-name="Runtime identity for orders workflow"

# orders-total.yaml holds the complete content from Section 4.
gcloud workflows deploy "$WORKFLOW" \
  --location="$REGION" \
  --source="orders-total.yaml" \
  --service-account="$WF_SA"

gcloud workflows describe "$WORKFLOW" \
  --location="$REGION"
~~~

In this lab, the workflow only computes in memory and returns a result, so it does not yet need IAM to read buckets or call Cloud Run. When using `sys.log` or calling Google Cloud APIs, grant the **exact permissions** to `WF_SA` on the relevant resources.

Run and **wait for the execution to complete**:

~~~bash
gcloud workflows run "$WORKFLOW" \
  --location="$REGION" \
  --data='{"orderId":"ORD-42","items":[{"sku":"BOOK","qty":2,"unitPrice":120},{"sku":"PEN","qty":3,"unitPrice":15}]}'

# Read-only listing of executions and statuses.
gcloud workflows executions list "$WORKFLOW" \
  --location="$REGION"
~~~

`gcloud workflows run` waits for the result, whereas `gcloud workflows execute` starts **asynchronously** and returns the execution handle for tracking. Do not treat successful execution creation as a completed business transaction. In direct CLI commands, JSON is passed via `--data`; in Bash, wrap the JSON in single quotes so the shell does not interpret the inner double quotes.

**Testing intentional errors:**

~~~bash
# Missing orderId: workflow will become FAILED with a validation error.
gcloud workflows run "$WORKFLOW" \
  --location="$REGION" \
  --data='{"items":[{"sku":"BOOK","qty":1,"unitPrice":100}]}'

# Negative quantity: must also become FAILED.
gcloud workflows run "$WORKFLOW" \
  --location="$REGION" \
  --data='{"orderId":"BAD-1","items":[{"sku":"BOOK","qty":-1,"unitPrice":100}]}'
~~~

Never run cleanup commands against production names. Once the lab is done and nothing invokes the workflow:

~~~bash
gcloud workflows delete "$WORKFLOW" --location="$REGION"
~~~

Deleting a workflow **does not automatically delete** the service account, Logs, Cloud Storage objects, or data written to external services by previous executions.

## 6. Control Flow: `switch`, `next`, `for`, and Scope

### Conditional Branching and Next Step

A `switch` evaluates conditions **in order** and executes the first matching condition. If no condition matches, execution continues to the following step (unless a default branch `condition: true` is present). Example:

~~~yaml
- choose:
    switch:
      - condition: ${total >= 1000}
        next: manualReview
      - condition: ${total >= 500}
        next: expressProcess
    next: normalProcess
- manualReview:
    return: "REVIEW_REQUIRED"
- expressProcess:
    return: "EXPRESS"
- normalProcess:
    return: "NORMAL"
~~~

This is a **step group** and assumes `total` was assigned in a prior step. `next` only jumps to a valid step within the same scope; you cannot jump arbitrarily into or out of loops or parallel branches.

### Looping Over Lists and Ranges

~~~yaml
- initialize:
    assign:
      - total: 0
- sum:
    for:
      value: n
      in: [1, 2, 3]
      steps:
        - add:
            assign:
              - total: ${total + n}
- finish:
    return: ${total}
~~~

The result is 6. `total` was created **outside the loop**, so it can be updated and read after the loop. Conversely, `n` and variables **created only inside the loop scope** cannot be referenced outside.

With `range: [1, 3]`, both endpoints **are inclusive**, yielding three iterations (1, 2, 3). Use `next: continue` to skip the current iteration and `next: break` to exit the loop, but do not jump to an arbitrary step outside the loop.

### Scope of `except` and Subworkflows

- Variables created **outside** `for`/`except` and modified inside the block remain readable after the block.
- New variables created only **inside `for` or `except`** are locally scoped; do not reference them in subsequent steps.
- Ordinary nested `steps` **do not** create a new scope; a `subworkflow` has its own parameters and local variables.
- Inside `parallel`, parent variables are **read-only** inside branches unless declared in `shared`.

For example, if you must save an error to process after `except`, initialize `errorInfo: null` in the **parent scope** before `try`, then assign it inside `except`.

## 7. Connecting to Cloud Run and Google Cloud APIs

Workflows can use `call: http.get`/`http.post` or **Google Cloud connectors**. Every outbound call must consider **authentication** and the IAM permissions of the workflow runtime SA.

### HTTP GET to a Private Cloud Run Service (OIDC)

Suppose the workflow has an environment variable `ORDER_API_URL` set to the Cloud Run service's HTTPS root URL:

~~~yaml
main:
  params: [input]
  steps:
    - init:
        assign:
          - baseUrl: ${sys.get_env("ORDER_API_URL")}
          - orderId: ${input.orderId}
    - fetch:
        call: http.get
        args:
          url: ${baseUrl + "/orders/" + orderId}
          timeout: 30
          auth:
            type: OIDC
            audience: ${baseUrl}
        result: response
    - done:
        return: ${response.body}
~~~

Set the user-defined environment variable at deploy time:

~~~bash
gcloud workflows deploy orders-api-flow \
  --location="$REGION" \
  --source=orders-api-flow.yaml \
  --service-account="$WF_SA" \
  --set-env-vars="ORDER_API_URL=https://YOUR-SERVICE-URL.run.app"
~~~

**Mandatory** condition: `WF_SA` has `roles/run.invoker` on **that specific Cloud Run service** and the backend implements `GET /orders/{id}`. `audience` is typically the **service root URL** (without paths); Workflows' ID token is not an end-user-supplied bearer token. Cloud Run must still perform business authorization based on authenticated context.

~~~bash
gcloud run services add-iam-policy-binding orders-api \
  --region="$REGION" \
  --member="serviceAccount:$WF_SA" \
  --role="roles/run.invoker"
~~~

The `timeout` field is the timeout **for the workflow's HTTP call**, not necessarily identical to Cloud Run's request timeout; choose compatible values and design retries/idempotency in case the client times out after the backend commits.

### Connecting to Google Cloud APIs: OAuth2 or Connectors

When calling `https://...googleapis.com` via HTTP request, use an **OAuth2 access token**:

~~~yaml
- readProject:
    call: http.get
    args:
      url: ${"https://cloudresourcemanager.googleapis.com/v3/projects/" + projectId}
      auth:
        type: OAuth2
    result: projectResponse
~~~

`googleapis.*` connectors are more convenient because they automatically use the workflow runtime SA's credentials, and some support long-running operations. Example fetching Cloud Storage object **metadata**:

~~~yaml
- getObjectMetadata:
    call: googleapis.storage.v1.objects.get
    args:
      bucket: ${input.bucket}
      object: ${input.object}
    result: objectMetadata
~~~

With the direct Storage connector, the workflow SA needs metadata/object read permissions like `storage.objects.get` on the exact bucket (e.g., an appropriate Object Viewer role). `objectMetadata` is a metadata map, **not the file's raw bytes**. Never load large objects into `result` or return raw file contents in execution output.

| Target Endpoint | Authentication Mechanism | Typical Errors |
|---|---|---|
| Cloud Run private service | `auth: {type: OIDC}`, SA has Invoker | `401/403`, wrong audience, service ingress |
| Google APIs on `googleapis.com` | `auth: {type: OAuth2}` or connector | SA missing role/permission, API disabled |
| External API outside Google Cloud | Auth header per external system; protect secret | Never put API keys in source or logs |

**Do not use `type: OIDC` instead of OAuth2 for Google APIs**, nor an OAuth2 access token instead of a Cloud Run ID token. Tokens are minted by Workflows using the **workflow runtime SA**, not inherited automatically from an end-user JWT or the caller's Java service account.

## 8. Error Handling: `try/except/retry` and Idempotency

An `http.get` can fail due to network issues, `429`, `502/503/504`, or timeouts. Sensible retries help applications tolerate transient failures, but retries must never trigger extra payments or duplicate orders.

Example of a **retryable GET** using a policy tailored for idempotent operations; `baseUrl` and `orderId` are already initialized:

~~~yaml
- fetchStatus:
    try:
      call: http.get
      args:
        url: ${baseUrl + "/orders/" + orderId}
        timeout: 20
        auth:
          type: OIDC
          audience: ${baseUrl}
      result: response
    retry:
      predicate: ${http.default_retry_predicate}
      max_retries: 3
      backoff:
        initial_delay: 1
        max_delay: 8
        multiplier: 2
    except:
      as: e
      steps:
        - failWithContext:
            raise:
              stage: "fetchStatus"
              message: "Could not load order status"
~~~

`max_retries: 3` means **three retry attempts after the initial call**, not a maximum of three total calls. `except` executes when an unhandled error occurs or retries are exhausted; variable `e` is scoped solely within `except`. If logging error details, filter out fields that could contain tokens, sensitive endpoints, or payloads.

**Do not blindly use idempotent retries for `POST /charge-card`**. A request may reach the service, commit to the database, and then lose the response. Retrying will charge twice if the API lacks an **idempotency key** and transaction/unique constraint. You can use `http.default_retry_non_idempotent` when understanding its narrower retry predicate, though **a predicate cannot replace backend idempotency**.

| Error | Recommended Action |
|---|---|
| Transient `429` or `503` | Retry with backoff/jitter, bounded attempts, and deadline |
| `401/403` | Check IAM/identity; do not retry indefinitely on missing permissions |
| `400` invalid input data | Return business error; do not retry |
| `404` order does not exist | Handle per business flow; not always an infrastructure error |
| Timeout after write operation | Look up idempotency/business key before replaying |
| Unrecoverable error | `raise` with context, alert, and compensation mechanism |

Workflows does not provide distributed transactions across Cloud Run/Cloud SQL/Pub/Sub. For multi-step business flows, use a **saga**: each step maintains durable state and has a clearly defined **compensation** action (e.g., canceling a reservation if payment fails), rather than assuming automatic database rollbacks across services.

## 9. `parallel` and Shared Data Across Branches

Two independent calls such as fetching shipping rates and stock levels can run in parallel to lower latency. Example using a pre-created `results` map marked `shared` so branches can write into it:

~~~yaml
main:
  steps:
    - init:
        assign:
          - results: {}
    - fetchInParallel:
        parallel:
          shared: [results]
          concurrency_limit: 2
          branches:
            - inventory:
                steps:
                  - getStock:
                      call: http.get
                      args:
                        url: https://example.com/api/stock
                      result: stockResponse
                  - saveStock:
                      assign:
                        - results["stock"]: ${stockResponse.body}
            - shipping:
                steps:
                  - getShipping:
                      call: http.get
                      args:
                        url: https://example.com/api/shipping
                      result: shippingResponse
                  - saveShipping:
                      assign:
                        - results["shipping"]: ${shippingResponse.body}
    - done:
        return: ${results}
~~~

Both URLs here are **illustrative placeholders** and must be replaced with real endpoints plus `auth`/IAM configuration before deploying. When both branches succeed, `results` contains the `stock` and `shipping` keys, **with no guarantee which branch finished first**.

**Scope rules inside `parallel`:**

- Variables created in parent scope are **readable by default, not writable** inside branches; to write to them, declare `shared: [results]`.
- Variables created only inside a branch are **local to that branch** and cannot be read directly by other branches.
- Shared assignments in Workflows are **atomic**, but **execution order is non-deterministic**. Avoid depending on update order if logic is non-commutative.
- `concurrency_limit` limits concurrency **only for that parallel step**; it is not a system-wide quota or a limit inherited by nested parallel blocks.
- When an unhandled failure occurs in one branch, the entire `parallel` step may raise `UnhandledBranchError`; the `continueAll` exception policy lets remaining branches attempt to finish.

A `parallel: for:` loop can process multiple object IDs concurrently. Set `concurrency_limit` to match downstream Cloud Run/Cloud SQL capacity, **not arbitrarily high just to save time**. If millions of events are needed, use Pub/Sub/Dataflow/Cloud Run jobs instead of loading millions of items into a Workflows list.

## 10. Execution Data Management and Size Limits

Because Workflows retains variables per execution, orchestration should use **small metadata** rather than accumulating large data payloads. Published Workflows limits are subject to change; at the time of writing, key figures are:

| Limit | Reference Value | Consequence |
|---|---:|---|
| Total variable data, execution arguments, and Eventarc payload | **512 KB** | Do not pass large files/responses between steps |
| Single string (UTF-8) | **256 KB** | Long JSON/base64 strings can exceed the limit |
| Length of a single expression | **400 characters** | Split variables/steps/subworkflows instead of cramming logic |
| Maximum execution lifetime | **1 year** | Can await long tasks, but enforce separate business timeouts |
| Execution history/results retention after completion | **Up to 90 days** | Do not use as long-term result storage |

These are **engine limits**, not targets to approach. Particularly with `parallel`, memory across parent variables and branches/iterations is also bounded. Storing large lists or full HTTP response bodies on every iteration can fail an execution even when Cloud Run backends still have plenty of RAM.

### Good Data Management Pattern

~~~text
Java API receives document
  → Cloud Storage: gs://docs/order-42.pdf (bytes)
  → Workflows arguments:
      {"orderId":"ORD-42","bucket":"docs","object":"order-42.pdf"}
  → Cloud Run/Job processes file via Storage API
  → Cloud SQL/Firestore: processing status + result URI
  → Workflows result: {"orderId":"ORD-42","status":"DONE","resultUri":"gs://..."}
~~~

Best practices:

- Pass `id`, `generation`, URIs, status, and summary numbers; never pass full bytes or PII.
- Use `result: response` **only when the body is genuinely needed**; if responses are huge, have the backend return a URI or object ID instead.
- Release unneeded references: you can assign `largePayload: null` after consumption, though it is best **not to load large payloads into the engine** at all.
- For optional map fields, use `map.get`/`default` rather than directly indexing keys whose presence is uncertain.
- Use workflow arguments only for observable parameters; route secrets through Secret Manager/runtime identity.

### Serialization and Data Types

`json.encode_to_string(map)` converts a map/list into a JSON string for APIs expecting a string body. `json.decode(text)` parses a valid JSON string into Workflows values. An HTTP response from `http.get` includes `code`, `headers`, and `body`; depending on Content-Type, `body` may be a map, list, string, or bytes. Never assume `response.body.orderId` always exists — verify the API contract and null/error cases before reading.

**Input data needs validation**: Workflows does not automatically enforce Java Bean Validation or API Gateway schemas. If an application sends `unitPrice` as a string and a step multiplies it, a `TypeError` may occur. Place schema validation in the Java API or add steps checking `get_type`/required keys where needed.

## 11. Invoking Workflows from Java Without Long Synchronous Waits

A Java API typically **creates an execution and returns the execution ID** to the client for status lookup, rather than holding an HTTP request open while multiple services run. Use the Java library **`com.google.cloud:google-cloud-workflow-executions`** and **Application Default Credentials (ADC)** from Cloud Run/GKE/App Engine.

Java 21 example with static JSON input for illustration; library versions are managed via a compatible Google Cloud Libraries BOM:

~~~java
import com.google.cloud.workflows.executions.v1.ExecutionsClient;
import com.google.cloud.workflows.executions.v1.WorkflowName;
import com.google.cloud.workflows.executions.v1.types.Execution;

public final class StartOrderWorkflow {
    public static void main(String[] args) throws Exception {
        String projectId = "my-workflows-lab";
        String location = "asia-southeast1";
        String workflowId = "orders-total-lab";

        // JSON is a STRING inside the Execution.argument field.
        String payload = """
            {"orderId":"ORD-42","items":[
              {"sku":"BOOK","qty":2,"unitPrice":120},
              {"sku":"PEN","qty":3,"unitPrice":15}
            ]}
            """;

        try (ExecutionsClient client = ExecutionsClient.create()) {
            WorkflowName workflow =
                WorkflowName.of(projectId, location, workflowId);
            Execution request = Execution.newBuilder()
                .setArgument(payload)
                .build();
            Execution started = client.createExecution(workflow, request);

            // Execution may still be ACTIVE: this is an identifier,
            // NOT a completed business outcome.
            System.out.println("Execution started: " + started.getName());
        }
    }
}
~~~

This example **creates an execution** without polling for the result. In a real REST API, return `HTTP 202 Accepted` with the execution ID (enforcing read authorization), and use `getExecution` with polling/backoff or callbacks/notifications as business requirements dictate. For dynamic payloads, use a JSON serializer such as Jackson rather than manual string concatenation to avoid injection and escaping bugs.

For Java code to create an execution, the **Java API's runtime service account** needs `workflows.executions.create` on the workflow (typically via `roles/workflows.invoker`). This permission is **distinct** from `WF_SA` used inside the workflow to call Cloud Run/Storage. Never grant `roles/workflows.admin` to a Java API solely to execute a workflow.

## 12. Logs, Execution History, Security, and Cost

Workflows generates execution logs at start and end; when needed, you can enable **call logging** or emit custom logs using `sys.log`. Note that call logging can capture **arguments, responses, and errors** depending on the level, so do not enable `log-all-calls` in production environments handling PII/secrets without a risk review.

~~~yaml
- logProgress:
    call: sys.log
    args:
      json:
        phase: "validated"
        executionId: ${sys.get_env("GOOGLE_CLOUD_WORKFLOW_EXECUTION_ID")}
        orderId: ${orderId}
      severity: INFO
~~~

This is a step to insert into a workflow where `orderId` already exists; it requires the runtime SA to hold `logging.logEntries.create` (e.g., `roles/logging.logWriter` at the appropriate scope). **Never log JWTs, tokens, passwords, or full API bodies**. In systems handling PII, hash/mask `orderId` or omit it from logs per policy.

Monitoring signals:

| Signal | Used to Detect |
|---|---|
| Execution state: `ACTIVE/SUCCEEDED/FAILED/CANCELLED` | Whether workflows are running, failing, or stopped |
| Step execution count and duration | Excessive loops, retries, or long waits |
| HTTP 4xx/5xx and connector errors | IAM/network/backend problems |
| Retry count, backoff, and timeouts | Downstream capacity exhaustion or persistent errors |
| Workflows call logging / Cloud Logging | Per-step failures, risk of logging sensitive data |
| Cloud Run/Cloud SQL/Pub/Sub business status | Proof of task completion, not just workflow exit |
| Billing by Workflows steps and downstream APIs | Operational cost optimization |

**Workflows costs depend on executed internal/external steps**, including calls and retries according to the billing model. A `for` loop with 10,000 iterations does not bill as a single step; meanwhile, Cloud Run, Storage, Pub/Sub, logging, and network charges still apply. Measure actual step counts, execution duration, and SLO quality, not merely the number of workflow definitions.

### Short Runbook

| Error | Common Cause | Action |
|---|---|---|
| Deploy fails on YAML | Indentation, malformed `steps` list, unquoted expression containing `:` | Check source at reported step/line |
| `KeyError` or `TypeError` | Missing input key, wrong map/list/number type | `map.get`, defaults, and contract validation |
| `403` calling Cloud Run | Workflow runtime SA lacks Invoker or wrong OIDC audience | Check Cloud Run IAM policy, root URL audience |
| `403` calling Google API | Missing role on resource, API disabled, Org Policy | Check workflow SA, OAuth2/connector, effective IAM |
| `429/503` | Quota or downstream overload | Bounded retries, throttling, monitor quotas |
| Timeout on POST | Server may have committed but response was lost | Check business idempotency before retrying |
| Memory limit exceeded | Storing large payloads/lists/HTTP responses | Replace with Cloud Storage/DB URIs |
| Unexpected parallel result | Missing `shared` or relying on update order | Review scopes, commutative operations |
| Java returns execution ID yet client thinks DONE | `createExecution` is asynchronous | Poll state/`getExecution` or use callbacks |

**IAM separation:** the deployer creates/updates workflows and holds `actAs` on the runtime SA; the Java caller only holds execution creation permission; the workflow SA holds permission to invoke each downstream resource. Grant Workflows → Cloud Run Invoker and Storage Object Viewer per resource rather than defaulting to `Editor/Owner`.

## 13. Integration Scenario: Java Order Flow with Compensation

An e-commerce team implements:

~~~text
Java Orders API (Cloud Run)
       │ creates workflow execution, passes orderId
       ▼
Workflows
  ├── validate orderId and look up order
  ├── call Cloud Run Inventory: reserve(orderId) idempotently
  ├── call Cloud Run Payment: charge(orderId) idempotently
  │       └── on failure: release reservation (compensation)
  ├── update status in Cloud SQL via Orders service
  └── publish event / return status + correlation ID
~~~

### Inter-Service Data Contract

| Field | Example | Rule |
|---|---|---|
| `orderId` | `ORD-42` | Business key; never derive from execution ID |
| `requestId` | `req-123` | Used for tracing; may change across retries |
| `reservationId` | `RES-42` | Persisted durably in the Inventory service |
| `paymentId` | `PAY-42` | Persisted durably in the Payment service |
| `workflowExecutionId` | Generated by Workflows | Tracks orchestration; does not replace unique business key |
| `status` | `PENDING/PAID/FAILED` | Database/service is the source of truth |

**Step ordering alone does not guarantee transactional safety:** if Inventory reserved stock but Payment timed out, Workflows must have a strategy to **query payment status** before deciding whether to retry or release the reservation. An `except` block directly invoking compensation is only valid when the business operation is known for sure to have failed; when the state is uncertain, transition to `PENDING_RECONCILIATION` and inspect. Never compensate "blindly" when a write request might have succeeded.

### Assumptions to Test

1. Creating two workflow executions for the same `orderId`: the system still avoids double charges via idempotency/unique business constraints in Payment.
2. Workflows is cancelled/retried between two steps: the backend retains state; a reconciliation job discovers orders stuck in `PENDING`.
3. Inventory transiently returns `503`: the step retries with backoff without creating two reservations.
4. Payment returns `401/403`: fix the service account Invoker/IAM rather than increasing retries indefinitely.
5. Large order payload: pass only IDs/URIs instead of holding the full cart or files in Workflows variables.
6. Concurrent executions: Workflows **has no global shared variable** to guard stock levels; Inventory/DB must enforce concurrency control and atomic updates.

**Architectural guidance:** use Cloud Scheduler/Workflows for scheduled summary reports, Eventarc to trigger object processing, and Pub/Sub for message fan-out; focus Workflows on steps requiring **ordered orchestration and outcome-based branching**.

## 14. Pre-Production Checklist

- [ ] Main/subworkflows have clear `params`, outputs, and searchable step names.
- [ ] Schema/types of JSON inputs and each HTTP response are validated before accessing nested fields.
- [ ] `${...}` expressions use valid Workflows functions, with single quotes wrapping expressions containing colons when needed.
- [ ] Variables are declared in the right scope; `for`/`except` blocks do not leak local variables outside.
- [ ] `parallel` steps write parent variables only via `shared` and do not rely on execution order.
- [ ] Large files/responses are never stored in execution variables; Cloud Storage/DB and IDs are used instead.
- [ ] OIDC is used for Cloud Run, OAuth2/connectors for Google APIs, and IAM is scoped per resource.
- [ ] Retries apply only to safe operations or those with a business idempotency key.
- [ ] Timeouts/circuit breakers and compensation/reconciliation strategies exist for uncertain states.
- [ ] Java callers use ADC and only hold execution-creation permissions, not workflow modification permissions.
- [ ] Execution history, PII/secret-free logs, and error/latency/cost dashboards are in place.
- [ ] CI/CD deploys from reviewed revisions/sources; canary tests and rollback exist for workflow definitions.
- [ ] A cleanup process exists for test workflows, unused service accounts/permissions, and downstream lab resources.

## 15. Hands-on Exercises

**Exercise 1 — Steps and expressions.** Given `args = {"user":"Lan","items":[3,5,8]}`. Write a workflow with `params: [args]`, a `for` loop summing to 16, and a `switch` returning `"LARGE"` if the sum exceeds 15, otherwise `"SMALL"`. Explain why `sum` must be declared outside the loop.

**Exercise 2 — Handling missing data.** An execution passes only `{"orderId":"ORD-42"}`. Write `map.get`/`default` so `items` defaults to `[]` when absent. Why can directly referencing `${args.items}` fail?

**Exercise 3 — Lab execution.** Deploy `orders-total.yaml` from Section 4 into a test project with a dedicated workflow SA, run the `ORD-42` test input and a negative-quantity error test. Record expected state/results; why is `gcloud workflows execute` not confirmation that the business transaction completed?

**Exercise 4 — Scope and parallel.** Two parallel branches read Inventory and Shipping and need to write into a `results` map. Write `parallel.shared` and two local variables. State what happens if you assign `results` without marking it `shared`, and why completion order is not guaranteed.

**Exercise 5 — OIDC and OAuth2.** A workflow calls `https://orders-abc.run.app/orders/42` and `https://storage.googleapis.com/storage/v1/...`. Choose the right `auth.type` for each URL, list required IAM roles/permissions, and explain why the workflow SA differs from the Java caller SA.

**Exercise 6 — Retries and transactions.** Payment API returns a timeout after recording a charge. Design the idempotency key, status lookup, retry/compensation decision, and attempt limits. Why does `http.default_retry_predicate` not guarantee "no duplicate payments"?

**Exercise 7 — Data limits.** A service returns 800 KB of JSON containing 5,000 orders. If Workflows holds the entire body in `result`, what happens? Propose an alternative design using a Cloud Storage URI and pagination.

**Exercise 8 — Java integration.** Use `ExecutionsClient` to create an execution for `orders-total-lab` and return HTTP 202 with the execution ID. List the minimum IAM permissions for the Java runtime SA and workflow runtime SA; design a status-tracking endpoint that does not expose execution data belonging to other tenants.

**Exercise 9 — Cost and operations.** Given 100,000 executions/day, each iterating 25 items and calling two HTTP services with an average of 1.2 retries. List the cost drivers in Workflows and downstream services; propose three ways to reduce steps/calls while preserving SLOs and auditing.

## Official Reference Documentation

- [Workflows overview](https://cloud.google.com/workflows/docs/overview) — the service's role in orchestration architecture.
- [Workflows syntax overview](https://cloud.google.com/workflows/docs/reference/syntax) — step structure and reserved words.
- [Steps](https://cloud.google.com/workflows/docs/reference/syntax/steps) — execution order and step naming.
- [Expressions](https://cloud.google.com/workflows/docs/reference/syntax/expressions) — `${...}` syntax, functions, and YAML escaping.
- [Variables and scope](https://cloud.google.com/workflows/docs/reference/syntax/variables) — scope of loops/except/subworkflows.
- [Maps and lists](https://cloud.google.com/workflows/docs/reference/syntax/maps) — map keys and `map.get`; [Lists](https://cloud.google.com/workflows/docs/reference/syntax/lists) — `list.concat`.
- [Iteration](https://cloud.google.com/workflows/docs/reference/syntax/iteration) — `for`, range, break/continue.
- [Subworkflows](https://cloud.google.com/workflows/docs/reference/syntax/subworkflows) — `params`/`call`/`result`.
- [Parallel steps](https://cloud.google.com/workflows/docs/reference/syntax/parallel-steps) — `shared`, atomic updates, and concurrency.
- [Retry steps](https://cloud.google.com/workflows/docs/reference/syntax/retrying) — retry predicates and backoff.
- [Catch errors](https://cloud.google.com/workflows/docs/reference/syntax/catching-errors) — `try/except` and error maps.
- [Authenticated requests](https://cloud.google.com/workflows/docs/authenticate-from-workflow) — OIDC to Cloud Run and OAuth2 to APIs.
- [Create/deploy workflows](https://cloud.google.com/workflows/docs/creating-updating-workflow) — CLI and IAM.
- [Execute a workflow](https://cloud.google.com/workflows/docs/executing-workflow) — `run`/`execute` and results.
- [Execute workflows from Java](https://cloud.google.com/workflows/docs/execute-workflow-client-libraries) — `ExecutionsClient` and ADC.
- [Execution logging](https://cloud.google.com/workflows/docs/log-workflow) — Cloud Logging, `sys.log`, and call logging.
- [Workflows quotas and limits](https://cloud.google.com/workflows/quotas) — 512 KB data, expression length, and retention.
- [Workflows pricing](https://cloud.google.com/workflows/pricing) — per-step billing and service integrations.
