# Workflows Connectors, HTTP Calls, and Authentication

> **Chapter:** Application Orchestration and Integration  
> **Module:** CLOUD_PROVIDERS_GCP

An e-commerce service receives an order-processing request: it calls an internal API running on **Cloud Run** to check status, publishes an event to **Pub/Sub**, and when necessary communicates with a partner over HTTPS. Writing direct calls inside a single HTTP request can create a dependency chain that is hard to retry, hard to trace, and hard to pinpoint which step failed. **Google Cloud Workflows** lets you represent that process as **stateful steps with branching, retries, and execution outcomes**.

This lesson belongs to the **Application Orchestration and Integration** chapter of the **CLOUD_PROVIDERS_GCP** module, connecting concepts from projects/IAM, Cloud Run, Pub/Sub, Secret Manager, and observability. The focus is distinguishing three choices:

- **Workflows connector** (`googleapis.*`): calls Google Cloud product APIs via built-in functions, automatically handling IAM authentication and certain retry/long-running operation mechanisms.
- **HTTP call** (`http.get`, `http.post`, `http.request`): calls HTTP/HTTPS endpoints such as Cloud Run, Google APIs without a connector, or partner APIs.
- **Authentication**: choosing the right **OIDC ID token**, **OAuth 2.0 access token**, or third-party credential; never equating API call permissions with network reachability.

**After this lesson, you will be able to:**

1. Write Workflows YAML using `params`, `steps`, `assign`, `call`, `result`, `switch`, and `return`.
2. Choose a connector over raw HTTP for Google Cloud APIs when a supported method exists.
3. Call authenticated Cloud Run using `auth.type: OIDC` and `*.googleapis.com` APIs using `OAuth2`.
4. Call Pub/Sub via connector, Base64-encode payloads in the proper format, and handle results.
5. Manage runtime service accounts, IAM permissions, Secret Manager, and third-party credentials.
6. Apply timeouts, retries, idempotency, `try/except`, and safe log monitoring.
7. Deploy/test a workflow and diagnose 401/403/404/429/5xx errors.
8. Evaluate when Service Directory is needed to call private endpoints in a VPC.

## 1. Where Does Workflows Fit in the Architecture?

~~~mermaid
flowchart LR
    START["Caller / Cloud Scheduler / Eventarc"] -->|"Workflows execution"| WF["Google Cloud Workflows\nOrchestration steps"]
    WF -->|"HTTPS + OIDC ID token"| RUN["Cloud Run\norders-read API"]
    WF -->|"Pub/Sub connector + IAM"| PS["Pub/Sub topic\norders-events"]
    WF -->|"Secret Manager connector"| SM["Secret Manager\npartner credential"]
    WF -->|"HTTPS + external auth"| EXT["Partner API"]
    WF --> MON["Execution history\nCloud Logging / Monitoring"]
~~~

**Workflows is an orchestration tool, not a runtime for heavy compute logic.** It fits processes involving multiple API calls, decision branches, awaiting results, or needing execution-level traceability. CPU-intensive processing, large data manipulation, or processing millions of records should live in **Cloud Run jobs, Cloud Functions, Dataflow, BigQuery**, or dedicated services invoked by Workflows.

### 1.1. Three Commonly Confused Concepts

| Concept | Example | Who Is Responsible? |
| --- | --- | --- |
| **Workflow definition** | `orders-orchestrator.yaml` | Describes the steps; deployed as a Workflows resource |
| **Execution** | A single run with `order_id=ord-123` | Workflows manages state, timing, errors, and output |
| **Workflow runtime identity** | `wf-orders@PROJECT_ID.iam.gserviceaccount.com` | Service account used when Workflows calls other resources |

The **caller starting an execution** and the **runtime service account** are **two distinct identities**. The caller may only have `roles/workflows.invoker`; the runtime account must have permissions on each destination, such as `roles/run.invoker` and `roles/pubsub.publisher`.

### 1.2. YAML and Data Between Steps

Example without network calls:

~~~yaml
main:
  params: [args]
  steps:
    - initialize:
        assign:
          - order_id: ${args.order_id}
          - current_status: "received"
    - check_order:
        switch:
          - condition: ${order_id == ""}
            next: invalid_order
        next: success
    - invalid_order:
        raise: "order_id must not be empty"
    - success:
        return:
          order_id: ${order_id}
          status: ${current_status}
~~~

`assign` sets execution variables; `switch` picks a branch; `raise` throws an error; `return` finishes and returns output. Workflows expressions live inside `${...}` and are evaluated at **runtime**. All values in the example are hypothetical; no Google Cloud resources are called.

**YAML note:** If a Workflows expression contains colons, brackets, or quotes that could confuse the YAML parser, wrap the entire expression in **YAML single quotes**. Never use tabs for indentation.

## 2. Choosing a Connector vs. an HTTP Call

| Criterion | Workflows Connector | HTTP Call |
| --- | --- | --- |
| Syntax | `call: googleapis.<service>.<version>.<method>` | `call: http.get/post/put/delete/request` |
| Common targets | **Google Cloud APIs** with connectors | Cloud Run services, REST Google APIs, SaaS/partner APIs, private HTTP endpoints |
| Authentication | Automatically uses workflow service account | Must declare `auth` for OIDC/OAuth2 or custom headers |
| Request/response | Follows API method schema; `args` typically include resource name, body | URL, query, headers, body, status code, and response body |
| Retry | Built-in per-method policies | Add `try/retry` manually as needed |
| Long-running operation | Some connectors auto-poll until completion | Implement polling/callbacks manually if API lacks helpers |
| Permissions | Runtime service account needs IAM on target resource | IAM/OIDC, OAuth scope, or provider credential depending on target |

**Connectors are not a generic HTTP proxy.** Do not use `googleapis.run.v2...` just to invoke an HTTP handler running on Cloud Run: the Cloud Run API connector is for **Cloud Run resource management**. To call **application endpoints**, use `http.get`/`http.post` and OIDC.

### 2.1. When to Use Connectors

Common method groups:

- `googleapis.pubsub.v1.projects.topics.publish` — publishes a message to a Pub/Sub topic.
- `googleapis.secretmanager.v1.projects.secrets.versions.access` — reads a secret version.
- `googleapis.bigquery.v2.jobs.query` — submits a SQL query to BigQuery.
- `googleapis.storage.v1.objects.get` — retrieves Cloud Storage object metadata.
- Other Cloud Run/GKE/Compute/Firestore management functions depending on the current connector catalog.

Connectors **do not eliminate** requirements for enabling APIs, IAM, quotas, billing, or argument formatting. Always read the exact schema in the **Workflows Connectors reference** rather than guessing method names from HTTP URLs.

### 2.2. When to Use HTTP

- Calling an authenticated **Cloud Run app URL**.
- Calling third-party REST endpoints, e.g., payment/shipping providers.
- Calling a Google API at `https://SERVICE.googleapis.com/...` when no suitable connector exists.
- Calling a private HTTP endpoint via **Service Directory** (covered later).

**Distinguish authentication types:** Google Cloud APIs use **OAuth2 access tokens**; Cloud Run invocations typically use **OIDC ID tokens**; external APIs depend on the external system (API key, bearer token, OAuth2, mTLS, etc.). Seeing "Bearer" in a header does not guarantee it is the right token type.

## 3. Runtime Service Account, IAM, and Three Auth Groups

~~~mermaid
flowchart TD
    WF["Execution: Workflows runtime SA"] --> C{"Destination?"}
    C -->|"Google connector"| GOOGLE["Automatic IAM\nGoogle API permissions"]
    C -->|"googleapis.com HTTP"| OAUTH["auth.type: OAuth2\nAccess token"]
    C -->|"Cloud Run HTTPS"| OIDC["auth.type: OIDC\nID token + audience"]
    C -->|"Partner HTTPS"| APIKEY["Partner header/API key/OAuth\nCredential in Secret Manager"]
    GOOGLE --> R["Check permissions on target resource"]
    OAUTH --> R
    OIDC --> R
    APIKEY --> P["Check permissions on partner system"]
~~~

### 3.1. Least Privilege by Role

| Actor | Typically Needed Permissions | Scope |
| --- | --- | --- |
| CI/deployer | Permissions to create/update Workflows resources; `iam.serviceAccounts.actAs` | Project and runtime SA |
| User/app invoking workflow | `roles/workflows.invoker` | Appropriate workflow/project |
| **Workflow runtime SA → Cloud Run** | `roles/run.invoker` | **Callee Cloud Run service** |
| Runtime SA → Pub/Sub | `roles/pubsub.publisher` | **Specific topic** |
| Runtime SA → Secret Manager | `roles/secretmanager.secretAccessor` | **Specific secret** |
| Runtime SA → another Google API | API-specific permissions | Corresponding project/dataset/bucket/resource |
| Workflows service agent | Google-managed system role; extra permissions when using Service Directory | Distinct from runtime SA |

**Never** assign `roles/editor`/Owner to a runtime SA just because an HTTP call returns 403. Identify the method, target resource project, actual principal, audience/scope, and org policy before changing IAM.

### 3.2. OIDC: Calling Cloud Run

~~~yaml
- call_cloud_run:
    call: http.post
    args:
      url: https://orders-api-EXAMPLE-uc.a.run.app/process
      auth:
        type: OIDC
        audience: https://orders-api-EXAMPLE-uc.a.run.app
      headers:
        Content-Type: application/json
      body:
        order_id: "ord-123"
    result: run_response
~~~

- `type: OIDC` instructs Workflows to mint an **ID token** using the runtime SA.
- `audience` should be the Cloud Run **service root URL** (without `/process`), unless the callee configures **custom audiences**.
- The callee must allow the runtime SA via **`roles/run.invoker`** and have a compatible **ingress policy**.
- For `http.post`, successful responses typically populate `run_response.body` and `run_response.code`.

**Do not substitute an OAuth2 access token for an ID token** on a default-authenticated Cloud Run endpoint. The `auth` block automatically populates the Authorization header; never inject a fake bearer token into the same request.

### 3.3. OAuth2: Calling Google REST APIs Without a Connector

~~~yaml
- get_project:
    call: http.get
    args:
      url: https://cloudresourcemanager.googleapis.com/v3/projects/LAB_PROJECT_ID
      auth:
        type: OAuth2
        # scopes: https://www.googleapis.com/auth/cloud-platform
    result: project_response
~~~

This mechanism applies to HTTPS endpoints whose hostname ends in `.googleapis.com`; the default scope is `https://www.googleapis.com/auth/cloud-platform`. **Scopes do not replace IAM permissions**: the account must still hold the API permission, e.g., to view project metadata. Never copy this OAuth2 pattern for arbitrary partner hostnames.

### 3.4. Third Parties: Credentials from Secret Manager

For a partner API requiring a static API token, you can read the secret using a Workflows helper:

~~~yaml
- load_partner_token:
    call: googleapis.secretmanager.v1.projects.secrets.versions.accessString
    args:
      secret_id: "partner-api-token"
      version: "7"
      project_id: ${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}
    result: partner_token

- call_partner:
    call: http.get
    args:
      url: https://api.partner.example.com/v1/status
      headers:
        Authorization: ${"Bearer " + partner_token}
    result: partner_response
~~~

This is a **sample step snippet**, not a complete workflow; `api.partner.example.com` is a placeholder hostname. The account must hold Secret Accessor on the exact secret, the provider must accept this Bearer format, and the request must use HTTPS. **Never log `partner_token` or `partner_response` if it contains sensitive data.**

**Important warning:** `--call-log-level=log-all-calls` can write call arguments or responses, including **secret values returned by `accessString`**, to Cloud Logging. In systems handling credentials/PII, prefer lower logging levels, restrict execution history retention/contents per policy, and use `sys.log` only with sanitized data.

## 4. HTTP Calls: URL, Headers, Body, Results, and Errors

Common standard library functions are `http.get`, `http.post`, `http.put`, `http.patch`, `http.delete`, and `http.request` when an arbitrary method is needed. Each call accepts:

~~~yaml
- fetch_order:
    call: http.get
    args:
      url: https://example.com/orders/ord-123
      headers:
        Accept: application/json
      query:
        include_items: true
      timeout: 30
    result: response
~~~

If the API returns JSON with `Content-Type: application/json`, Workflows usually decodes the body into a map/list, accessible via `response.body.status` or `response.body["status"]`. If the target returns text/binary, handle the corresponding data type without assuming a `status` field always exists.

### 4.1. Field Meanings

| Property | Usage |
| --- | --- |
| `url` | Exact URL; avoid building hostnames/paths from unvalidated input |
| `headers` | Header map; avoid logging credentials |
| `query` | Map URL-encoded as query parameters |
| `body` | JSON map/list or matching payload; API must support it |
| `auth` | `OIDC` or `OAuth2` when Workflows supports the target |
| `timeout` | Timeout **per HTTP request**, not for the entire workflow |
| `result` | Variable receiving the response for downstream steps |
| `try/retry/except` | Retries recoverable errors and catches final failures |

Per documentation, the default HTTP request timeout is **300 seconds**, up to a maximum of **1,800 seconds** per request; align this with the callee's timeout. If a job runs for hours, do not hold an HTTP request open indefinitely; use an LRO connector, bounded polling, or callbacks/events.

### 4.2. HTTP Responses and Exceptions

- For 2xx responses, `result` typically contains `code`, `headers`, and `body`.
- For HTTP 4xx/5xx responses, Workflows normally **raises `HttpError`** rather than proceeding to steps referencing `result`.
- Timeout/connection errors carry different tags; do not assume every error has `e.code`.
- Workflows errors have `tags` and `message`; inspect them in `except` to classify failures.

Example handling 404 **without futile retries**:

~~~yaml
- lookup:
    try:
      call: http.get
      args:
        url: https://example.com/orders/ord-123
      result: order_response
    except:
      as: e
      steps:
        - handle_not_found:
            switch:
              - condition: ${"HttpError" in e.tags and e.code == 404}
                next: return_not_found
            next: rethrow_other_error
        - return_not_found:
            return:
              status: "not-found"
        - rethrow_other_error:
            raise: ${e}
~~~

Use `raise: ${e}` for unhandled errors so the execution fails with evidence, instead of returning success even when backend calls failed.

## 5. Retries, Idempotency, and Long-Running Operations

### 5.1. Retrying HTTP According to Operation Type

Workflows provides default policies:

| Policy | Recommended Target | Retried Errors |
| --- | --- | --- |
| `http.default_retry` | **Idempotent** calls, usually GET | 429, 502, 503, 504, and certain connection/timeout errors |
| `http.default_retry_non_idempotent` | POST/side effects lacking idempotency guarantees | 429, 503, or connection failures per default policy |

GET example:

~~~yaml
- check_inventory:
    try:
      call: http.get
      args:
        url: https://inventory.example.com/items/sku-123
        timeout: 20
      result: inventory
    retry: ${http.default_retry}
~~~

Default policies use up to **5 retries** with increasing backoff. Retries add **billed steps**, increase latency, and can amplify backend traffic. If tighter bounds are needed, specify `retry.predicate`, `max_retries`, and `backoff`.

### 5.2. Why Does POST Need an Idempotency Key?

Suppose a workflow sends `POST /payments`, the backend **records the payment**, and the response is lost; Workflows assumes failure and retries. If the backend creates a new transaction on each POST, the customer gets charged twice.

**Preventive design:**

- Pass a business-unique **idempotency key**, e.g. `payment_id`, so the backend detects duplicate requests.
- Persist state keyed by that key in the database using unique constraints/transactions.
- Retry only error classes and methods with a clear idempotency contract.
- If an earlier step succeeded and a later step failed, use **compensation/saga** when business rules allow.
- Pub/Sub may redeliver messages; consumers need **deduplication**, as Workflows does not make side effects exactly-once.

**Do not give `POST` an idempotent retry policy simply because it calls an internal endpoint.** Base the decision on business semantics, not hostname.

### 5.3. Connector Retries and LRO Polling

Connectors include built-in retries for Google API operations; for supported long-running operations (LROs), the connector can **wait and poll** until completion or failure. Per documentation, default request timeouts are **30 minutes**; overall LRO timeouts can be tuned via `connector_params`. Each poll iteration may count as a **billable step**, so do not configure an overly aggressive poll interval for jobs running for hours.

**Connectors do not mean "every API call will automatically retry until it succeeds".** On permission or invalid-data errors, fix the root cause; if an operation partially applied, handle compensation/reconciliation before starting a new execution.

## 6. End-to-End Example: Cloud Run → Pub/Sub

### 6.1. Context and API Contract

- Cloud Run service **`orders-read`** exposes `GET /orders/{order_id}`, requires an authenticated invoker, and returns JSON like `{"id":"ord-123","status":"READY"}`.
- Pub/Sub topic **`orders-events`** exists in the lab project.
- Workflow **`orders-orchestrator`** accepts input `{"order_id":"ord-123"}`, calls Cloud Run via OIDC, and publishes an event via connector.
- The runtime service account only holds `roles/run.invoker` on `orders-read` and `roles/pubsub.publisher` on `orders-events`.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant W as Workflows
    participant R as Cloud Run orders-read
    participant P as Pub/Sub orders-events
    C->>W: Execute(order_id)
    W->>R: GET /orders/{id} + OIDC ID token
    R-->>W: 200 {"status":"READY"}
    W->>P: Pub/Sub connector publish(Base64 JSON)
    P-->>W: messageIds
    W-->>C: Execution result
~~~

**Important:** This example publishes a **read/checked event** without processing payments or mutating orders. When using POST to create transactions, design idempotency and error recovery separately.

### 6.2. Complete Workflows YAML

Create `orders-orchestrator.yaml` **on your lab machine** (not inside this lesson folder):

~~~yaml
main:
  params: [args]
  steps:
    - init:
        assign:
          - project_id: ${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}
          - run_url: ${sys.get_env("RUN_SERVICE_URL")}
          - topic_id: ${sys.get_env("TOPIC_ID")}
          - order_id: ${args.order_id}

    - get_order:
        try:
          call: http.get
          args:
            url: ${run_url + "/orders/" + order_id}
            auth:
              type: OIDC
              audience: ${run_url}
            timeout: 30
          result: order_response
        retry: ${http.default_retry}

    - build_event:
        assign:
          - event:
              event_type: "order.checked"
              order_id: ${order_id}
              status: ${order_response.body.status}
          - encoded_event: ${base64.encode(json.encode(event))}

    - publish_event:
        call: googleapis.pubsub.v1.projects.topics.publish
        args:
          topic: ${"projects/" + project_id + "/topics/" + topic_id}
          body:
            messages:
              - data: ${encoded_event}
                attributes:
                  origin: "orders-orchestrator"
        result: publish_result

    - done:
        return:
          order_id: ${order_id}
          checked_status: ${order_response.body.status}
          message_ids: ${publish_result.messageIds}
~~~

**Step-by-step explanation:**

1. `sys.get_env` reads the project ID and two **user-defined environment variables** on the workflow. `RUN_SERVICE_URL` must be the Cloud Run root URL, **without a trailing slash**, e.g. `https://orders-read-...run.app`.
2. `http.get` calls `/orders/ord-123`; the OIDC `audience` is the root Cloud Run URL.
3. The backend is assumed to return JSON with a `status` field; if the API returns text or another field, update the mapping.
4. `json.encode(event)` produces bytes; `base64.encode(...)` satisfies the `PubsubMessage.data` format.
5. The `googleapis.pubsub.v1.projects.topics.publish` connector uses the workflow service account and returns `messageIds`.
6. The workflow returns **metadata** rather than secrets or full sensitive responses.

**Input constraints:** The example constructs a URL from `order_id`. Production workflows must validate that only safe path characters (e.g., alphanumerics/hyphens) are allowed or URL-encode properly; never concatenate URLs from untrusted input. Handle missing `order_id` and HTTP 404 per business contract, and do not publish if GET failed.

**Duplicate note:** Retrying HTTP GET is safe when it causes no side effects; however, the Pub/Sub publish step may execute again if the execution is replayed or a request succeeded before the response was lost. Consumers should use `event_id/order_id` to deduplicate when required by business rules.

## 7. Deploying and Testing the Workflow

**Lab context:** Project `LAB_PROJECT_ID`; region `asia-southeast1`; Cloud Run service `orders-read` already serves JSON matching the contract; Pub/Sub topic `orders-events` already exists. You have a dedicated service account `wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com`.

**Never run these IAM/deploy commands against production without approval.** Workflows, Cloud Run, Pub/Sub, and Cloud Logging can incur charges. Do not run demos with real order data.

### 7.1. Preflight Checks

~~~bash
# Read-only, to avoid targeting the wrong project or region
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud run services describe orders-read \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud pubsub topics describe orders-events \
  --project=LAB_PROJECT_ID

gcloud iam service-accounts describe \
  wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --project=LAB_PROJECT_ID
~~~

If the service account does not yet exist, an authorized admin creates it **in the lab project**:

~~~bash
# Mutates project; run only when authorized
gcloud iam service-accounts create wf-orders \
  --display-name="Workflows orders runtime" \
  --project=LAB_PROJECT_ID
~~~

Ensure the **Workflows API** and target APIs are enabled in the appropriate project. A workflow that only needs connectors or HTTP calls **does not** require storing a Google Cloud service account key locally or in YAML source.

### 7.2. Granting Permissions to the Runtime Identity

~~~bash
# Cloud Run callee: allow runtime SA to invoke the specific service
gcloud run services add-iam-policy-binding orders-read \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --member="serviceAccount:wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Pub/Sub topic: allow publishing only, do not grant Subscriber/Admin
gcloud pubsub topics add-iam-policy-binding orders-events \
  --project=LAB_PROJECT_ID \
  --member="serviceAccount:wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
~~~

The deployer needs workflow management permissions and **`iam.serviceAccounts.actAs`** on `wf-orders`; callers invoking the workflow need **separate** invoker permissions. If Cloud Run and the topic live in another project, grant IAM on the **target project/resource**, not only the Workflows project.

### 7.3. Deploying the Workflow with Environment Variables

~~~bash
# Mutates Workflows resource; RUN_SERVICE_URL must be the real Cloud Run URL
gcloud workflows deploy orders-orchestrator \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --source=orders-orchestrator.yaml \
  --service-account=wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars=RUN_SERVICE_URL=https://orders-read-EXAMPLE-as.a.run.app,TOPIC_ID=orders-events
~~~

`RUN_SERVICE_URL` is the **root URL** of the Cloud Run service, not the placeholder URL in this lesson. Do not use `https://orders-read-EXAMPLE-as.a.run.app` literally. For a workflow calling a Cloud Run service, the URL env var name is not a credential; **never store passwords/API keys in Workflows environment variables** when Secret Manager is appropriate.

Verify the definition:

~~~bash
gcloud workflows describe orders-orchestrator \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

### 7.4. Executing with Mock Data

~~~bash
# Creates an execution and awaits output; CALLS Cloud Run and publishes to Pub/Sub
gcloud workflows run orders-orchestrator \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --data='{"order_id":"ord-123"}'
~~~

Expected result when Cloud Run returns `{"id":"ord-123","status":"READY"}`:

~~~json
{
  "order_id": "ord-123",
  "checked_status": "READY",
  "message_ids": ["MESSAGE_ID_FROM_PUBSUB"]
}
~~~

`MESSAGE_ID_FROM_PUBSUB` is a placeholder. The workflow result confirms Pub/Sub accepted the publish, **not** that subscribers have finished processing. If downstream confirmation is required, use response events/callbacks or a separate status record.

You can use `gcloud workflows execute` to **launch without waiting** and check execution status later. In Google Cloud Console: **Workflows → select workflow → Executions** to inspect succeeded or failed steps.

### 7.5. Safe Test Scenarios

| Test | Expected Behavior |
| --- | --- |
| `order_id=ord-123` exists | Cloud Run returns 200; Pub/Sub receives message |
| `order_id` does not exist | HTTP 404; workflow fails or returns structured error if `except` is added |
| Workflow SA lacks `run.invoker` | HTTP auth/permission error; never reaches publish |
| Workflow SA lacks Pub/Sub Publisher | Cloud Run GET may succeed; publish connector is denied |
| Cloud Run returns transient 503 | `http.default_retry` may retry and fail if limit exceeded |
| Topic does not exist | Publish connector reports resource error; does not auto-create topic |

**Lab cleanup:** Only delete workflows/topics/service accounts created specifically by the lab when no callers/subscribers depend on them. Deleting a topic can drop subscription data and break integrations; verify ownership first.

## 8. Advanced Connectors: Pub/Sub, Secret Manager, and LROs

### 8.1. What Does Pub/Sub Publish Do?

The complete workflow in Section 6 uses `googleapis.pubsub.v1.projects.topics.publish`. Pub/Sub requires `data` as a **Base64 string**: `json.encode` produces bytes, and `base64.encode` yields Base64 text. `attributes` are string metadata for routing/filtering subscriptions and must never contain PII or secrets.

**Do not assume exactly-once side effects:** if a workflow retries or replays an execution, multiple equivalent messages may be published. Consumers need appropriate contracts and idempotency.

### 8.2. Secret Manager: Two Ways to Read

| Connector | Result | When to Use |
| --- | --- | --- |
| `googleapis.secretmanager.v1.projects.secrets.versions.access` | Response contains Base64 `payload.data` | Need to handle raw bytes/metadata |
| `googleapis.secretmanager.v1.projects.secrets.versions.accessString` | Decoded UTF-8 string | Credential is plain text |

Example using `access`:

~~~yaml
- get_secret_version:
    call: googleapis.secretmanager.v1.projects.secrets.versions.access
    args:
      name: projects/LAB_PROJECT_ID/secrets/partner-token/versions/7
    result: secret_response

- decode_secret:
    assign:
      - partner_token: ${text.decode(base64.decode(secret_response.payload.data))}
~~~

**Never return or log `partner_token`.** When calling `accessString`, avoid enabling `log-all-calls` because the connector could write the plaintext secret into response logs. Accessing secrets via Workflows still requires **Secret Accessor** on the exact secret; do not grant project-wide access if only one credential is needed.

### 8.3. Long-Running Operations: Controlling Poll Costs

Some Google APIs, such as creating resources or running batch jobs, return a **long-running operation**. Connectors can **poll** until the terminal state, avoiding manual `while + sys.sleep + http.get` loops for every API.

- Check whether the connector method supports LRO handling.
- Use `connector_params` per the reference to tune **total timeout** and polling policy.
- Monitor quotas, timeouts, and `OperationError` failures; the underlying operation may already have caused side effects even if the workflow did not receive the expected result.
- Each poll may be billed as **a billable step**, so avoid needlessly short poll intervals.

**Do not assume every connector call is an LRO**: reading GCS metadata and publishing to Pub/Sub are standard synchronous API operations.

## 9. Calling Private Endpoints in a VPC

If a workflow must call a **VM** or internal HTTP backend with only a private IP, Workflows is not placed inside a subnet like a Compute Engine VM and does not directly use Cloud Run **Direct VPC egress**. Google Cloud provides **Service Directory** integration to send HTTP requests to private VPC endpoints.

### 9.1. Network Requirements

1. Create/register the private endpoint in a **Service Directory namespace/service** in a supported region.
2. Register **one endpoint per Service Directory service** when used with Workflows; if multiple exist, Workflows may pick any endpoint.
3. Configure VPC firewall rules, service listening port, return paths, and DNS.
4. Grant the **Workflows service agent** (distinct from the runtime SA) Service Directory Viewer and PSC Authorized Service permissions per the guide.
5. If the backend requires authentication, design **IAP/OIDC**, tokens, or mTLS according to supported capabilities.

### 9.2. Example Private HTTP Call with Service Directory

~~~yaml
- check_private_inventory:
    call: http.get
    args:
      url: http://10.20.0.5:8080/health
      private_service_name: projects/LAB_PROJECT_ID/locations/asia-southeast1/namespaces/internal/services/inventory
      timeout: 15
    result: inventory_health
~~~

This is an **example IP address** and only works after actually creating the Service Directory service/endpoint, IAM bindings, and corresponding firewall rules. This mechanism **does not automatically provide application authentication or TLS for HTTP endpoints**. For sensitive data, require HTTPS/mTLS or IAP per architecture rather than treating a private IP as sufficient security.

**Internal Cloud Run ingress:** Per documentation, Workflows can call ingress-restricted internal Cloud Run under supported conditions, though `OIDC` and `run.invoker` are still required. Do not assume all private/internal URLs or custom domains are reachable like a Cloud Run `run.app` URL.

## 10. Safety: Inputs, Errors, Retries, and Partial State

### 10.1. Validating Input Before Calling

- Restrict `order_id` format; never build URLs/hostnames from unvalidated user-supplied strings.
- Never put secrets in URL query parameters or workflow inputs.
- For APIs accessing user data, enforce authorization at the **backend**, not solely in the workflow.
- Input parameters may be stored in execution history, logs, or audit records depending on config; never pass tokens/passwords via `--data`.
- Bound payload sizes; pass **Cloud Storage object references** for large data objects rather than passing entire files through steps.

### 10.2. Three Error States to Distinguish

| Scenario | What Happened | Strategy |
| --- | --- | --- |
| Cloud Run GET times out before response | Unknown what backend did; GET is ideally idempotent | Bounded retry and investigate timeout |
| Pub/Sub publish returns 403 | Prior Cloud Run GET succeeded; publish was rejected | Fix IAM/topic, replay execution in controlled manner |
| Publish succeeded but workflow lost response | Message may already exist | Do not blindly republish indefinitely; downstream dedupes |

**There is no automatic distributed transaction** across Cloud Run, Pub/Sub, and partner APIs. For multi-system update chains, design **sagas/compensation**, workflow state, durable idempotency keys, and test failure injection in a lab environment.

### 10.3. Bounded Retry Policy

~~~yaml
- read_with_bounded_retry:
    try:
      call: http.get
      args:
        url: https://example.com/health
        timeout: 10
      result: resp
    retry:
      predicate: ${http.default_retry_predicate}
      max_retries: 3
      backoff:
        initial_delay: 2
        max_delay: 20
        multiplier: 2
~~~

Choose `max_retries` based on SLOs and backend capacity. For 401/403 caused by wrong permissions, retrying will not fix IAM. For 429/503, examine quotas and capacity rather than increasing retries indefinitely.

### 10.4. Catching Errors and Returning Business Codes

To let callers distinguish "order missing" from "infrastructure error", define an error contract:

~~~yaml
- call_order:
    try:
      call: http.get
      args:
        url: https://example.com/orders/ord-123
      result: order_response
    except:
      as: e
      steps:
        - choose_error:
            switch:
              - condition: ${"HttpError" in e.tags and e.code == 404}
                next: not_found
            next: unexpected_error
        - not_found:
            return:
              ok: false
              reason: "order-not-found"
        - unexpected_error:
            raise: ${e}
~~~

Never return the entire `e.body` to callers if it may expose stack traces, response payloads, credentials, or PII. In production, provide a **correlation ID** and safe error category, keeping detailed error info in access-controlled logs.

## 11. Observability, Operations, Quotas, and Cost

### 11.1. Tracking Executions

Cloud Workflows records execution states such as RUNNING/SUCCEEDED/FAILED and maintains **execution history** showing which steps ran. In the Console: Workflows → workflow → **Executions**; Cloud Logging captures execution start/end logs per service configuration.

Recommended **PII-free** fields to log:

- Correlation ID or approved business key.
- Workflow name, execution ID, and running version/revision.
- Step name, start/end timestamps, and status.
- HTTP code/connector error tag and retry count.
- Pub/Sub message ID and downstream acknowledgment when available.
- Total processing duration, external call count, and estimated cost.

### 11.2. Call Logging and Secrets

| Level/Practice | Risk |
| --- | --- |
| `log-none` or no call-detail logging | Low risk of leaking payloads/credentials; requires separate minimal business logs |
| `log-errors-only` | Helpful for debugging; still check if error body/headers contain secrets |
| `log-all-calls` | **High risk** when calling Secret Manager, APIs with bearer headers, or user data |
| Custom `sys.log` | Gives content control, though still billed and must redact secrets |
| Detailed execution history | May persist step variables/state; evaluate data classification/IAM |

**Do not enable detailed history/call-all in production simply because debugging is hard.** Before raising verbosity, review retention, log access permissions, masking, and data policies. Prefer logging error codes or correlation IDs over full HTTP bodies.

### 11.3. Costs to Account For

- Workflows bills by **internal/external steps** depending on call type; retries and polling increase step counts.
- HTTP calls to other services can generate **Cloud Run requests/compute, Pub/Sub messages, Secret Manager accesses, and network egress**.
- Cloud Logging/Monitoring, Eventarc/Scheduler triggers, Service Directory, Cloud NAT, or private backend endpoints may carry separate charges.
- **Quotas** apply to concurrency, execution history, request/response size, and HTTP timeouts; exceeding quotas can cause 429/ResourceExhausted errors.
- A workflow running for hours due to inefficient polling can be cheap or expensive depending on step count and downstream calls; **measure in Cloud Billing and Monitoring** rather than guessing from wall-clock duration alone.

**Optimization:** Combine `assign` operations sensibly, retry only transient errors, use LRO connectors/callbacks instead of tight polling, keep payloads small, and avoid excessive logging.

## 12. Troubleshooting Matrix

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Deploy fails on YAML | Bad indentation, unquoted expression, wrong `steps/args` fields | Consult Workflows syntax reference, inspect reported line/step |
| Workflow runs but `args.order_id` errors | Input missing field or wrong map shape | Inspect `--data` JSON and input validation |
| Cloud Run returns 401 | Invalid OIDC token/audience | Verify `auth.type=OIDC`, root service URL, custom audience |
| Cloud Run returns 403 | Runtime SA lacks `run.invoker` or ingress blocks source | Check **callee** IAM and ingress policy |
| Google API HTTP returns 401 | Wrong `OAuth2`/scope or endpoint | Check `*.googleapis.com`, auth block, API activation |
| Pub/Sub connector returns 403 | Runtime SA lacks Publisher on topic | Check topic IAM, project ID, and topic name |
| Secret Manager access returns 403 | Missing Secret Accessor on specific secret/version | Check IAM and version existence |
| HTTP 404 | Wrong URL/path; resource does not exist | Verify full path, Cloud Run handler, order ID |
| HTTP 429 | Quota, rate limit, or backend overload | Check quotas, Monitoring, backoff |
| HTTP 502/503/504 | Upstream error/transient overload | Use bounded retries, inspect backend logs/SLO |
| Timeout | Exceeded `timeout`, network/connection issue, or slow backend | Check HTTP timeout, Cloud Run request timeout, correlation ID |
| Pub/Sub message missing at subscriber | Mismatched subscriber/subscription/filter | Check message ID, topic, subscription, DLQ |
| Double processing | Execution replay/retry without idempotency | Check dedupe keys, event IDs, consumer logs |
| Private endpoint unreachable | Missing Service Directory/IAM/route/firewall | Check service agent roles, endpoint registry, VPC |
| Credential appears in logs | `log-all-calls` or `sys.log` included response/token | Lower logging level, revoke/rotate secret, incident response |

**Diagnostic order:** check **workflow definition → runtime SA/IAM → right token type → DNS/network → HTTP response/error → backend business logic → retries/side effects**. Never escalate IAM to Editor or enable anonymous Cloud Run invocation just to "make it work".

## 13. Capstone Lab and Submission Criteria

**Goal:** Complete one Cloud Run → Pub/Sub execution, verifying each authentication layer and ensuring retries do not break traceability.

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | Select lab project, existing Cloud Run service, and Pub/Sub topic | Resource names, region, enabled APIs |
| 2 | Create a dedicated runtime SA | Email and least-privilege IAM bindings |
| 3 | Deploy the complete workflow YAML | Active workflow, valid URL/topic env vars |
| 4 | Run with `order_id=ord-123` | Execution SUCCEEDED |
| 5 | Inspect Cloud Run logs and Pub/Sub publish result | Status JSON and message ID |
| 7 | Use a test SA lacking Pub/Sub Publisher | Connector reports permission denied without leaking data |
| 8 | Restore test IAM / evaluate idempotency | No unintended duplicate publishes |
| 9 | Optional: model a Service Directory private endpoint | Diagram of service agent IAM + network |
| 10 | Clean up lab resources by ownership | Shared resources left untouched |

**Do not modify a production SA's IAM to test errors.** Instead, use a separate test workflow/service account, or simulate via case study if no sandbox is available.

### 13.1. Extension Question

Suppose Cloud Run returns 200 and Pub/Sub publish also succeeded, yet the execution is retried at another step or the caller re-launches the entire workflow. Design:

- A unique `event_id` for the same business operation.
- Unique constraint/deduplication at the consumer.
- Keyed processing state in the database.
- A bounded retry policy and DLQ for persistent errors.
- A way to detect "already completed" without repeating the business action.

## 14. Self-Check Exercises

1. **How does a connector differ from an HTTP call?** Connectors use built-in API methods and IAM with retry/LRO support; HTTP requires explicit URL, headers/body, and auth.
2. **Which token should Cloud Run use?** A Google-signed **OIDC ID token**, and the caller needs `run.invoker`.
3. **Which token do `*.googleapis.com` Google REST APIs use?** An OAuth2 access token; scopes do not replace IAM permissions.
4. **Do external SaaS APIs automatically support `auth.type=OIDC`?** Not by default; follow the API contract, usually using provider credentials.
5. **Does the workflow caller automatically become the runtime SA?** No; invocation identity and workflow SA are distinct.
6. **Is a JSON service account key needed for Workflows to call Pub/Sub?** No; connectors use the runtime identity.
7. **What format does the Pub/Sub connector require for payload `data`?** Base64-encoded bytes, e.g. `base64.encode(json.encode(event))`.
8. **On HTTP 404, does Workflows automatically return `response.code=404` as success?** It usually raises `HttpError`, requiring `except`.
9. **If POST wrote data but the response was lost, is retrying safe?** Only if the backend handles idempotency/compensation properly.
10. **Do GET 429/503 retries incur cost?** They can increase billed steps and latency.
11. **What does a Service Directory private endpoint need besides a private IP URL?** Registration, service agent permissions, VPC routes/firewalls, and app auth.
12. **Can an LRO connector wait until an operation finishes?** Yes, for supported methods; polling bills per step.
13. **Should `log-all-calls` be enabled when calling `accessString`?** No, because the plaintext secret may end up in logs.
14. **Does Workflow SUCCEEDED guarantee the Pub/Sub subscriber processed the message?** No; publish acknowledgment differs from downstream completion.
15. **Is Cloud Run 403 always a missing `run.invoker`?** No; also check ingress, principal, audience, and org policy.
16. **Does placing Workflows in a region guarantee all outbound calls originate from that region?** No; workflow regionality and HTTP request egress origin must be evaluated separately.

## 15. Production Checklist and Official Documentation

- [ ] Workflow has an input/output contract, timeouts, error contract, and owner.
- [ ] Uses connectors where appropriate; HTTP for app endpoints or external APIs.
- [ ] Dedicated runtime SA; `workflows.invoker` is not confused with runtime SA permissions.
- [ ] Cloud Run is called with OIDC and proper `audience`; Google APIs with OAuth2.
- [ ] Pub/Sub topic/Secret Manager IAM is scoped to the exact resource; Editor is not used.
- [ ] Third-party credentials reside in Secret Manager, never in source/YAML/logs.
- [ ] Bounded retries align with idempotency; POST side effects and consumers perform deduplication.
- [ ] 4xx/5xx, timeouts, and connector errors have clear handling and alerts.
- [ ] Private endpoint calls use Service Directory/IAP and valid routing where needed.
- [ ] Sensitive request bodies/secrets are never logged; execution history and IAM are reviewed.
- [ ] Monitoring, correlation IDs, and alerts exist for FAILED executions and backend SLOs.
- [ ] Workflows steps/polling, API quotas, downstream costs, and egress are accounted for.
- [ ] Deployed via lab/canary first; rollback exists for workflow definitions/versions on errors.
- [ ] A reconciliation runbook exists when an execution fails after partial steps completed.

**Official Google Cloud Sources:**

- [Workflows overview](https://docs.cloud.google.com/workflows/docs/overview) — execution model, regionality, and limits.
- [Understand connectors](https://docs.cloud.google.com/workflows/docs/connectors) — automatic IAM, retries, and LROs.
- [Connectors reference](https://docs.cloud.google.com/workflows/docs/reference/connectors) — `googleapis.*` catalog and args schemas.
- [Make an HTTP request](https://docs.cloud.google.com/workflows/docs/http-requests) — `http.get/post/request`, headers/body.
- [Authenticate from a workflow](https://docs.cloud.google.com/workflows/docs/authenticate-from-workflow) — OIDC, OAuth2, and external APIs.
- [Invoke Cloud Run from Workflows](https://docs.cloud.google.com/workflows/docs/calling-run-functions) — ID tokens and Invoker.
- [Publish Pub/Sub message](https://docs.cloud.google.com/workflows/docs/publish-pubsub-message) — Base64 payload and connector.
- [Secret Manager connector](https://docs.cloud.google.com/workflows/docs/use-secret-manager) — `access`/`accessString`, IAM.
- [Retry steps](https://docs.cloud.google.com/workflows/docs/reference/syntax/retrying) — predicates/backoff.
- [Catch errors](https://docs.cloud.google.com/workflows/docs/reference/syntax/catching-errors) — `try/except` and HTTP errors.
- [Invoke private endpoint using Service Directory](https://docs.cloud.google.com/workflows/docs/invoke-private-endpoint-vpc) — `private_service_name`, VPC, and service agent.
- [Create/manage workflows](https://docs.cloud.google.com/workflows/docs/creating-updating-workflow) — deployment and runtime identity.
- [Send execution logs](https://docs.cloud.google.com/workflows/docs/log-workflow) — logging risks and history.
- [gcloud workflows run](https://docs.cloud.google.com/sdk/gcloud/reference/workflows/run) — executing with `--data`.
- [Workflows pricing](https://cloud.google.com/workflows/pricing) — internal/external steps.

**Key takeaway:** Use **connectors** for Google Cloud APIs when a matching method exists; use **HTTP + OIDC** to call Cloud Run, **HTTP + OAuth2** for Google REST APIs, and dedicated credentials for partner APIs. Networking paths, IAM, and application authentication are independent layers. A reliable workflow must have **bounded retries, idempotency, observable errors, and zero leaked secrets**.
