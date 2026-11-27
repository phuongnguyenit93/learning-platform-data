# Networking, secrets, and resource configuration for Cloud Run functions

A retail system receives new image events on **Cloud Storage** via **Eventarc**, runs a function to generate thumbnails, and writes the results back to a bucket. Another function receives HTTP requests from an internal application to sync orders with a partner service. Both require choosing the right network path, identities, and compute limits: never exposing internal admin endpoints unintentionally; never embedding API keys in source code; and never opening excessive **Cloud SQL** connections during event spikes.

**Cloud Run functions** (the modern name for the functions model built on Cloud Run; older workflows often call it *Cloud Functions 2nd gen*) lets you deploy code as HTTP or event-handling functions. For networking, secrets, and resources, think in terms of three questions: **who can call the function, where can the function reach, and how many resources can a single instance consume?**

This lesson belongs to the **Cloud Run functions and Eventarc** chapter of the **CLOUD_PROVIDERS_GCP** module. It ties together IAM/VPC, Cloud Run, Cloud Storage, Cloud SQL, release workflows, data protection, reliability controls, and cost. Examples prioritize brevity, conditional hands-on practice, and self-contained explanations without requiring prior lessons.

## 1. Objectives and high-level model

After this lesson, you will be able to:

1. Distinguish **ingress** into a function from **egress** out of a function, and HTTP authentication from data-access authorization.
2. Choose between **Direct VPC egress**, a **Serverless VPC Access connector**, or the public Internet/Google APIs path.
3. Use **Secret Manager** via runtime identity, understanding the difference between secrets injected as environment variables and mounted as volumes.
4. Choose **memory, CPU, timeout, concurrency, and min/max instances** based on workload, SLOs, and cost.
5. Understand the **Eventarc trigger** path, function invocation permissions, and duplicate event handling requirements.
6. Deploy, verify, and troubleshoot configuration errors using `gcloud`, Cloud Logging, and Cloud Monitoring.

~~~mermaid
flowchart LR
    C["HTTP client / Eventarc"] --> IN["Ingress + authentication"]
    IN --> F["Cloud Run function"]
    SEC["Secret Manager"] -. "Runtime identity" .-> F
    F --> VPC["VPC: Cloud SQL / internal"]
    F --> API["Google APIs / partners"]
    RES["CPU, RAM, timeout, concurrency, scaling"] -. "Execution limits" .-> F
~~~

In the diagram, **Ingress/IAM**, **egress path**, and **application permissions** are three distinct layers. Having a network path to Cloud SQL does not automatically grant the function permission to log into the database.

## 2. Configuration scope and deployment paths

### 2.1. Functions run on the Cloud Run platform

A function consists of **source code + entry point + runtime**, built into a runnable artifact on Cloud Run infrastructure. Applicable configuration groups include:

| Group | Examples | Question answered |
| --- | --- | --- |
| **Trigger** | HTTP, Eventarc/CloudEvents | Which event or request triggers the function? |
| **Ingress** | Internal, all, internal + Cloud Load Balancing (per deploy type) | Which network sources can reach the endpoint? |
| **Authentication** | IAM Invoker, Eventarc identity | Which principals are allowed to invoke? |
| **Egress** | Direct VPC egress, connector, Internet/Google APIs | How does the function reach internal backends and external services? |
| **Secrets** | Secret Manager env/volume | Who has read access and which secret version is used? |
| **Capacity** | CPU, memory, timeout, concurrency, min/max instances | Under load, how does the function consume resources and incur cost? |

**Note on management interfaces:** you can deploy functions via the **Cloud Run** interface or the **`gcloud functions` 2nd gen** workflow. Flag names can differ: for instance, `gcloud functions deploy` ingress modes use values like `internal-only`, whereas `gcloud run` uses the corresponding Cloud Run interface values. **Do not mix the two flag sets in one command**; check `gcloud ... --help` for the deployment path you are using.

### 2.2. Two common function types

- **HTTP function**: exposes an HTTP endpoint; you must define ingress, authentication, timeout, and valid HTTP responses. If public, add application/Cloud Run authentication, HTTPS, and load protection as needed.
- **Event-driven function**: Eventarc routes events (such as Cloud Storage object finalized) to the destination; you must configure the **trigger, service account, receive/invoke permissions, and event filters**. This does not mean Internet users need permission to call the function.

Eventarc can deliver events **at least once**, so the handler must guard against duplicates and write data using an **idempotency key**. Retries can cause sudden load spikes, directly impacting `max instances`, Cloud SQL, and cost.

## 3. Ingress: who can connect to the endpoint?

### 3.1. Ingress is not IAM

Ingress mode governs **which network paths are accepted**; IAM governs **which principals can invoke**. An endpoint with ingress `all` can still require an authorized identity to invoke it. Conversely, allowing unauthenticated access on an externally reachable endpoint can expose sensitive functionality.

| Goal | Initial design consideration |
| --- | --- |
| Public webhook from a partner | Internet-appropriate ingress, signature/webhook token validation, rate limiting, logging, and HTTP-layer protection. |
| Internal organizational API | Internal ingress or internal load balancer per architecture; IAM authentication. |
| Accessible only via external Application Load Balancer | Combined internal + Cloud Load Balancing mode where supported, adding Cloud Armor/IAP as appropriate. |
| Receiving Eventarc | Ensure the **event delivery path from Eventarc is permitted** and the trigger's service account has invoke permission. |

Do not assume "internal" means every VM in any VPC or every service in the same project can invoke it. Check internal source rules, project/VPC boundaries, and the product's ingress semantics.

### 3.2. HTTP authentication via IAM

For services requiring authentication, callers need an appropriate token and invoke permission on the destination. For 2nd gen functions running on Cloud Run, HTTP invocation typically involves **Cloud Run Invoker** (`roles/run.invoker`) and the corresponding managed resource; roles and attachment methods may differ from earlier function generations.

Example invoking an **authorized** endpoint using an identity token:

~~~bash
FUNCTION_URL="https://FUNCTION_URL_FROM_DEPLOY"

# READ/REQUEST: call only if the principal already holds invoke permission.
TOKEN="$(gcloud auth print-identity-token)"
curl --fail-with-body -H "Authorization: Bearer $TOKEN" "$FUNCTION_URL"
~~~

`FUNCTION_URL` is a placeholder. This is a test example using a logged-in `gcloud` identity; for **production service-to-service**, use an identity token minted for the exact service account with `audience` set to the target URL (or configured custom audience), per Cloud Run docs. The `--audiences` flag on `gcloud auth print-identity-token` has restrictions depending on credential/impersonation type, so do not apply it blindly to user tokens. Never print tokens to logs. `curl --fail-with-body` requires curl support; otherwise use `curl -i`. Permission to view a function **does not necessarily** grant permission to invoke it.

### 3.3. Eventarc has its own delivery identity

An Eventarc trigger typically uses a **service account** to authenticate delivery requests to the Cloud Run destination. Beyond permission to invoke the destination, some trigger types require **Eventarc Event Receiver** and roles tied to Pub/Sub or the event source, depending on event type and project.

~~~text
Cloud Storage object finalized
      ↓
Eventarc trigger + event filters
      ↓   [trigger service account / IAM]
Cloud Run function
      ↓   [runtime service account / IAM]
Cloud Storage / Cloud SQL
~~~

**The trigger identity and runtime identity are not the same.** Granting bucket read access to the trigger SA does not grant the function code access to read objects, and granting permissions to the runtime SA does not let Eventarc invoke the destination without its own invoke permission.

## 4. Egress: where does the function connect?

### 4.1. Three destination groups

1. **Google APIs:** Cloud Storage, Secret Manager, Pub/Sub, etc. require valid egress/DNS and IAM permissions; they do not necessarily require entering a private VPC.
2. **Private resources in a VPC:** Cloud SQL private IP, VMs without public IPs, internal load balancers; require a mechanism to route traffic into the VPC.
3. **Internet or partner services:** require egress policies, DNS, TLS, and potentially a fixed source IP address for partner allowlisting.

**Network configuration does not grant IAM.** Opening a TCP route to Cloud SQL does not automatically grant `cloudsql.instances.connect` or PostgreSQL login permissions.

### 4.2. Direct VPC egress vs. Serverless VPC Access connector

| Connection method | Description | When to consider |
| --- | --- | --- |
| **Direct VPC egress** | Cloud Run-backed function sends outbound traffic to a VPC via product-supported network/subnet configuration, **without a connector**. | Prefer evaluating in supported environments to eliminate connector management overhead. |
| **Serverless VPC Access connector** | Provisions a managed connector for the function to enter the VPC; requires appropriate region, subnet/CIDR, capacity, and IAM. | Use when current workflows/features require a connector or existing architecture standardizes on it. |
| **No VPC connection** | Calls Google APIs and public endpoints via the platform's default egress model. | Function needs no private resources. |

Direct VPC egress and a connector **should not be configured overlapping** on the same flow without a supported design. Depending on the function deployment interface and service generation, flags for Direct VPC egress may differ; check the exact `gcloud run deploy`/`gcloud functions deploy` reference and current docs.

### 4.3. Choosing which traffic routes into the VPC

- **`private-ranges-only`**: routes destinations matching private/recognized ranges through the VPC path; other traffic follows the default egress path.
- **`all`**: routes all outbound traffic through the configured VPC, including traffic destined for the Internet, so **Cloud NAT/routes/firewalls** or another egress mechanism may be required.

Do not treat `private-ranges-only` as a security filter that only allows private IP connections. It is a **routing choice**, not a firewall. With Direct VPC egress, the CLI flag may be `--vpc-egress` rather than the connector workflow's `--egress-settings`.

~~~mermaid
flowchart TB
    F["Cloud Run function"] --> E{"Egress mode?"}
    E -- "private ranges" --> PRIV["Private IP → VPC"]
    E -- "all traffic" --> VPC["All outbound → VPC"]
    F --> API["Google APIs/public endpoints\nvia appropriate egress path"]
    VPC --> NAT["Cloud NAT/proxy/firewall\nif Internet needed"]
    PRIV --> SQL["Cloud SQL private IP / VM / internal LB"]
~~~

This diagram simplifies routing: the actual path to Google APIs depends on **DNS and VPC route scope**. When using restricted/private Google APIs endpoints or Private Service Connect, you must configure DNS, routes, and policies explicitly rather than flipping a single flag.

### 4.4. Commonly forgotten networking conditions

- The function, VPC subnet/connector, and target resource must have compatible **regions**, routes, and Shared VPC permissions if applicable.
- For Cloud SQL private IP, check **Private Service Access or Private Service Connect**, database endpoint selection, and database auth.
- With `all` traffic, the function still needs an **egress path to Google APIs**, Artifact Registry, or external sources per architecture and policy.
- If a partner requires allowlisting a fixed source IP, design VPC egress + **Cloud NAT with static IP addresses** or an equivalent egress proxy, then **verify the actual source IP**; Cloud Run does not guarantee a static public egress IP on its own.
- **VPC firewalls, routes, Cloud NAT, DNS, and IAM** serve distinct roles. Timeout errors should not be "fixed" with the Editor role.

## 5. Secret Manager and runtime identity

### 5.1. Secrets are not plain environment variables

**Secret Manager** stores secret versions (API tokens, database credentials, etc.), and the function references a secret in its configuration. Common mechanisms:

| Mechanism | When the secret is read | Advantages | Risks to manage |
| --- | --- | --- | --- |
| **Secret → environment variable** | Provided to the instance per version at startup. | Simple for apps to read via `os.getenv`/`System.getenv`. | Running instances do not auto-refresh new values; requires rollout/restart policy and avoiding env logging. |
| **Secret → mounted volume** | Read as a file inside the container per supported mount/version behavior. | Separated from process env; may support reading updates depending on config. | Filesystem permissions, read timing, caching, and application reload support. |
| **Calling Secret Manager API in code** | On demand by the application. | Flexible control over timing, versions, and caching. | Extra API calls/latency, retry handling, and IAM/network dependencies. |

Never store secrets directly in `--set-env-vars=API_TOKEN=secret-value`, Git, Docker images, startup scripts, or logs. A **secret resource name/ID** is usually not a secret value itself, though it should follow organizational naming conventions.

### 5.2. Least privilege to read a secret

Suppose runtime service account `fn-orders-runtime@retail-lab.iam.gserviceaccount.com` needs to read **only** secret `partner-api-token`. Grant `roles/secretmanager.secretAccessor` scoped to that **specific secret**:

~~~bash
# WRITE: illustrative IAM binding; SA and secret must exist.
gcloud secrets add-iam-policy-binding partner-api-token \
  --project=retail-lab \
  --member="serviceAccount:fn-orders-runtime@retail-lab.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# READ-ONLY: inspect bindings directly on the secret.
gcloud secrets get-iam-policy partner-api-token \
  --project=retail-lab
~~~

Do not grant `roles/secretmanager.admin` to a function that only reads secrets. Permissions inherited from the project or ancestor levels may be broader than expected; inspect **effective permissions** along with IAM conditions/deny policies, not just bindings on the secret itself.

### 5.3. Pinning secrets by version

Example configuring Cloud Run functions via 2nd gen `gcloud functions deploy`:

~~~bash
# WRITE: pass a secret reference, never the secret value on the CLI.
# Using a tested numeric version makes deployments reproducible.
gcloud functions deploy orders-hook \
  --gen2 \
  --project=retail-lab \
  --region=asia-southeast1 \
  --runtime=python312 \
  --source=. \
  --entry-point=orders_hook \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account=fn-orders-runtime@retail-lab.iam.gserviceaccount.com \
  --set-secrets="PARTNER_API_TOKEN=partner-api-token:3"
~~~

The value `3` is only an **example secret version**. Use it only after creating an actual secret version; do not treat `:latest` as the best default when you need releases that roll back cleanly. With volume mounts, flag syntax differs and you must verify path permissions and version-refresh behavior. **Do not run the command without source code** and without checking region, runtime, and flag support.

For functions created via the Cloud Run console/`gcloud run`, secret configuration may use different flags (`--set-secrets`/volume mounts per supported workflow). Do not copy `gcloud functions` flags into `gcloud run` without checking `--help`.

### 5.4. Rotation and recovery

A safe rotation plan:

1. Create a **new secret version**; do not overwrite the old secret.
2. Verify the new token works with the partner/database and runtime IAM remains intact.
3. Update the function to the new version or mount mechanism per architecture; roll out in a controlled manner.
4. Monitor 401/403 responses from the partner, 5xx errors, retries, and latency.
5. Revoke the old token **after** verifying all instances/revisions are using the new token.

Assigning `latest` to an environment variable **does not make running instances automatically refresh their environment variables**. Secret mounts can reflect updates when re-reading the file, provided the application **re-reads it** instead of caching indefinitely; verify actual version and volume behavior.

## 6. Resource configuration and scaling behavior

### 6.1. Key limits

| Setting | Impact | Risk if misconfigured |
| --- | --- | --- |
| **Memory** | RAM for runtime, libraries, intermediate data. | OOM when decoding large images/files, terminating the function. |
| **CPU** | Processing and startup speed; must align with memory/concurrency. | Slowness from CPU starvation or wasted spend from over-provisioning. |
| **Timeout** | Maximum duration allowed per request/instance execution per function type. | Timeouts on long tasks; retries may repeat side effects. |
| **Concurrency** | Concurrent requests/events per instance where supported. | Races, memory contention, connection pool exhaustion. |
| **Minimum instances** | Keeps warm capacity to reduce cold-start probability. | Higher baseline cost during low traffic. |
| **Maximum instances** | Caps scale-out instances per policy. | Too low increases backlog/latency; too high overwhelms downstream. |

**Available settings depend on deployment method and platform.** Cloud Run functions, Cloud Run services, and 1st gen functions do not share identical limits or CLI flags. For event-triggered workloads, request timeouts and Eventarc retry mechanics must be evaluated together; a redelivered event can run concurrently with an earlier attempt if the design lacks locks/idempotency.

### 6.2. Balancing concurrency and Cloud SQL

Suppose a function is configured with:

~~~text
max instances = 20
concurrency = 10
max DB connection pool per instance = 5
~~~

These are **theoretical upper bounds**, not always-open connections:

~~~text
Max concurrent requests accepted ≈ 20 × 10 = 200
Max DB connections from pools ≈ 20 × 5 = 100
~~~

If Cloud SQL only has 60 available connections for this workload, the pool/max-instances configuration above can cause errors even while the function still has CPU headroom. You need **load testing, connection reuse, pool sizing, retry/backoff**, and fan-out control from Eventarc.

### 6.3. Timeouts and long-running tasks

Do not set a massive timeout just to "make sure the job finishes." An event-handling function can still be terminated or retried, so:

- Break event work into small steps; persist checkpoints and idempotency keys durably.
- Return success **only when** side effects are safely committed.
- If tasks exceed runtime limits or need complex checkpointing, consider **Cloud Run jobs**, **Cloud Batch**, Workflows, or queue workers.
- When calling slow downstream services, set **HTTP client timeouts** shorter than the function timeout and handle errors explicitly.

### 6.4. Cost of minimum instances

Minimum instances can reduce startup latency for low-traffic functions with strict latency SLOs. However, they do not eliminate all cold starts when scaling past the minimum or deploying a new revision. Measure:

- p95/p99 request or event completion latency;
- spawned instances, concurrency, CPU/memory;
- error/timeout/retry rates;
- **Cloud Run billing**, VPC connector/NAT charges, and log volume.

## 7. Hands-on example: HTTP function with a secret

### 7.1. Self-contained source code

Minimal Python example using `functions-framework`, reading a secret **via environment injection**, and returning configuration status (without exposing the secret). Create these two files **in your hands-on source directory** when deploying; the lesson repo does not include them.

`main.py`:

~~~python
import os
import functions_framework

@functions_framework.http
def orders_hook(request):
    # Use IAM-authenticated invocation only in this environment.
    # Never return, log, or write the raw secret value.
    token = os.getenv("PARTNER_API_TOKEN")
    if not token:
        return {"error": "server_not_configured"}, 503

    # Demo: a real app uses the token to call the partner over HTTPS,
    # with client timeouts, log redaction, and idempotency.
    return {"status": "configured"}, 200
~~~

`requirements.txt`:

~~~text
functions-framework>=3,<4
~~~

This example only demonstrates **reading Secret Manager via runtime injection**. It does not prove a partner transaction succeeded. In real development, pin dependency versions for reproducible builds, test HTTPS/authentication, and never treat this token as a substitute for IAM Invoker.

### 7.2. Creating the secret and service account

The following resources must be created/approved before deploying. Replace placeholder project/email values:

~~~bash
# READ-ONLY: verify context before any write operations.
gcloud auth list
gcloud config get-value project

gcloud secrets describe partner-api-token --project=retail-lab
gcloud iam service-accounts describe \
  fn-orders-runtime@retail-lab.iam.gserviceaccount.com \
  --project=retail-lab
~~~

If the secret/SA does not exist yet, create it via your organization's IAM/Secret Manager workflow and grant `secretAccessor` as shown in section 5. **Do not use `echo "SECRET"` or store secret values in files/shell history** when illustrating version creation.

### 7.3. Deploying with resource limits

Inside the source directory containing `main.py` and `requirements.txt`:

~~~bash
# WRITE: deploy gen2 function; requires appropriate API/IAM/build permissions.
gcloud functions deploy orders-hook \
  --gen2 \
  --project=retail-lab \
  --region=asia-southeast1 \
  --runtime=python312 \
  --source=. \
  --entry-point=orders_hook \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account=fn-orders-runtime@retail-lab.iam.gserviceaccount.com \
  --set-secrets="PARTNER_API_TOKEN=partner-api-token:3" \
  --memory=512MB \
  --timeout=60s \
  --max-instances=10 \
  --min-instances=0
~~~

This example uses 2nd gen `gcloud functions` to illustrate common parameters; concurrency/CPU support depends on CLI and runtime. If using the newer Cloud Run functions deployment interface, use its corresponding flags and verify the configuration post-deploy. When the function reads Secret Manager, the runtime SA must have `secretAccessor` on the referenced secret/version; otherwise the container may **fail to start** or lack the secret at runtime.

### 7.4. Adding VPC egress only when actually needed

If the function must reach a **Cloud SQL private IP** or an internal HTTP service, choose **one** supported networking option. Example with an already-managed and authorized connector:

~~~bash
# WRITE: update by redeploying via the same workflow and source.
# The flags below are ADDITIONS to the deploy command above,
# not standalone commands to run on their own.
--vpc-connector=projects/retail-lab/locations/asia-southeast1/connectors/retail-egress
--egress-settings=private-ranges-only
~~~

If choosing **Direct VPC egress** in a workflow supporting Cloud Run configuration, specify the network/subnet and VPC egress flags per that CLI/API **without attaching a connector simultaneously**. Verify Shared VPC IAM, subnet capacity, firewall rules, DNS, and the route to Cloud SQL. With `all` traffic, ensure a valid egress path exists to the Internet/Google APIs.

### 7.5. Inspecting live configuration and testing

~~~bash
# READ-ONLY: verify function configuration after deployment.
gcloud functions describe orders-hook \
  --gen2 \
  --project=retail-lab \
  --region=asia-southeast1 \
  --format=yaml
~~~

Inspect fields under **serviceConfig**, ingress, egress, secret injection, service account, memory, timeout, concurrency, and scaling. Never rely solely on the flags you passed: org policies, APIs, or CLI versions can affect the resulting configuration.

Send an HTTP request with an identity token matching the audience and invoke permission as in section 3; expect `{"status":"configured"}` if the secret/version mounted properly. If it returns 503, check the Secret Manager reference and runtime permissions — **never enable unauthenticated access to fix errors**.

## 8. Eventarc: separating event delivery from function egress

### 8.1. Cloud Storage finalized event example

A new object is written to a bucket and Eventarc delivers a CloudEvent to the function:

~~~mermaid
sequenceDiagram
    participant G as Cloud Storage
    participant E as Eventarc trigger
    participant F as Cloud Run function
    participant S as Cloud Storage output
    G->>E: Object finalized event
    E->>F: CloudEvent via trigger identity
    F->>S: Read/write object using runtime SA
    F-->>E: Complete or report error
~~~

Do not confuse three permissions: **source emitting events**, **trigger invoking destination**, and **function accessing buckets**. When deploying an Eventarc trigger, align the event source, location, filters, trigger SA, and delivery retries with the target service. If ingress is overly restrictive and blocks Eventarc's delivery path, the function may never receive events even though the Eventarc trigger exists.

### 8.2. Illustrative CloudEvent handler

~~~python
import functions_framework

@functions_framework.cloud_event
def on_image_finalized(event):
    event_id = event["id"]
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")
    generation = data.get("generation")

    if not bucket or not name:
        raise ValueError("Missing Cloud Storage object metadata")

    # Use (bucket, name, generation) as the idempotency key.
    # Persist COMMITTED state durably before acknowledging success;
    # never use instance memory for deduplication.
    print(f"event_id={event_id} object={bucket}/{name} generation={generation}")
~~~

The snippet above only reads metadata and **does not yet generate thumbnails or write outputs**. A production solution must handle:

- Events delivered **repeatedly** or out of the desired order.
- Using `event_id` and object `generation` for identification, rather than checking an in-RAM variable.
- Avoiding **trigger loops** if the function writes output back to the same bucket/prefix matched by the trigger filter.
- Using retries/backoff and dead-letter/observability appropriate to the source/trigger for transient errors, while avoiding infinite loops on deterministic data errors.
- Capping max instances so event bursts do not overload Cloud SQL or partner services.

## 9. Security, operations, and cost

### 9.1. Separating identities

| Principal | Need | Permission scope |
| --- | --- | --- |
| **CI/deployer** | Build/deploy function, attach runtime SA/trigger. | Appropriate deployment permissions and `iam.serviceAccounts.actAs` where needed. |
| **Eventarc trigger SA** | Deliver events to the function. | Event receiver/invoker and source permissions per workflow. |
| **Runtime SA** | Read secrets, Cloud Storage/Cloud SQL. | Secret Accessor and **least-privilege** data permissions. |
| **HTTP caller** | Invoke protected function. | Cloud Run Invoker on destination where applicable. |
| **SRE/auditor** | View logs, metrics, and configs. | Appropriate Reader/Logging/Monitoring roles; no default Admin. |

Secrets, event payloads, and request metadata may contain sensitive data. Never log tokens, secret headers, database passwords, or full CloudEvent payloads without assessing personal data risks.

### 9.2. Quantifying cost

~~~text
Total operational cost ≈
  Cloud Run CPU/RAM/requests/instance time
  + minimum instances (if enabled)
  + VPC connector or Direct VPC egress-related networking
  + Cloud NAT / transfer / load balancing (if used)
  + Secret Manager access/version storage
  + Eventarc / Pub/Sub and downstream services
  + Cloud Logging / Monitoring
~~~

This is a breakdown model, not an official billing formula. A function with 2 GiB RAM may be overkill for a small webhook, whereas a large-image resizing function might OOM at 256 MiB. Measure **p95 latency, peak memory, errors, retries, instance counts, and cost per completed event**, not just single-call duration.

### 9.3. Safe rollout milestones

1. Read current configuration and record source revision/runtime SA/trigger state.
2. Apply networking/secrets/capacity changes in staging first.
3. Test valid requests/events, IAM failures, and retry/idempotency cases.
4. Observe Cloud Logging/Monitoring, Secret Manager audit logs, and Cloud SQL connections.
5. Release with review and a configuration/secret-version rollback plan.

Do not change ingress, VPC egress, secret version, and timeout **all at once** in one test without a baseline; if something fails, root-cause isolation becomes difficult.

## 10. Symptom-based troubleshooting

| Symptom | Common causes | First thing to check |
| --- | --- | --- |
| HTTP `403` before reaching handler | Caller lacks invoke permission or token has wrong audience. | Function/Cloud Run IAM, identity token, ingress mode. |
| Client timeout, no application logs | Ingress/network route/DNS issue or endpoint unreachable. | Ingress settings, LB, DNS/TCP/TLS, and logs. |
| Eventarc trigger exists yet function does not run | Wrong filter, trigger identity lacks role, invalid delivery/ingress. | Eventarc trigger state, service agent/Invoker, logs. |
| Container fails startup on secret | Secret/version missing or runtime SA lacks `secretAccessor`. | Secret reference, IAM binding, revision logs. |
| Still using old token after rotation | Env var cached on old instance or app-level cache. | Revision/instance lifecycle, version reference, volume behavior. |
| Cloud SQL private IP timeout | Missing VPC egress, route/PSA/PSC, firewall, or DNS. | Egress mode, connector/Direct VPC, subnet/DB connectivity. |
| Google APIs fail when `all` traffic enabled | Missing Cloud NAT/route/DNS/private API path. | VPC routes, NAT, DNS, and Google APIs endpoints. |
| Event burst causes 5xx or exhausts DB connections | Max instances/concurrency/pool/retries too high. | Instance count, DB connections, queue/retry metrics. |
| Function OOM or timeout | Memory too low, task too long, or slow remote dependency. | Peak memory, request duration, per-client-call timeouts. |
| Cost rises after enabling min instances/connector | Warm capacity, connector/NAT, and logging persist during low traffic. | Billing by SKU, instance count, and network usage. |

**Diagnostic order:** (1) trigger/HTTP ingress → (2) caller IAM → (3) runtime SA/secrets → (4) egress DNS/VPC/firewall → (5) CPU/RAM/timeout/concurrency → (6) downstream and idempotency logic. A `PERMISSION_DENIED` error from Secret Manager is never fixed by adding RAM.

## 11. Exercises

### Exercise 1 — Distinguishing ingress and egress

An HTTP function is called only by internal services yet must reach a partner's public API. Which criteria govern ingress and egress selection? Why doesn't `internal-only` prevent the function from calling the Internet?

### Exercise 2 — Cloud SQL private IP

A function reads its secret successfully yet cannot connect to PostgreSQL via `10.x.x.x:5432`. Propose an ordered check across **Direct VPC egress or connector, subnet/region, PSA/PSC, DNS, routes, firewall, and database auth**. Why won't granting `secretAccessor` fix a network error?

### Exercise 3 — Least-privilege IAM

Design permissions for the deployer, Eventarc trigger SA, runtime SA, and HTTP caller. Which principal needs Reader/Accessor on Secret Manager? Which principals need invoke? Why shouldn't you grant project Editor to all of them?

### Exercise 4 — Rotation

A function uses `PARTNER_API_TOKEN=partner-api-token:3` via an environment variable. After creating version `4`, does the function automatically switch to the new version? Write a checklist for upgrading the version and rolling back.

### Exercise 5 — Choosing resources

An image-resizing function has 700 MiB peak RAM, p95 duration of 18 seconds, and occasional bursts of 2,000 events in one minute. Propose test values for memory, timeout, concurrency, and max instances; what must you measure before finalizing settings?

### Exercise 6 — Connection pool analysis

A function has `max instances=20`, `concurrency=10`, and max 5 DB connections per instance. Calculate the theoretical max concurrent requests and DB connections, then propose how to shed load when Cloud SQL only has 60 connections remaining.

**Hint:** 200 requests and 100 connections are theoretical ceilings; effective limits also depend on CPU, memory, and application behavior.

### Exercise 7 — Eventarc duplicate delivery

A Cloud Storage finalized event is processed twice because the first attempt generated the thumbnail but the handler timed out before acknowledging. Design the idempotency key, durable commit state, and a way to prevent output writes from triggering an infinite event loop.

### Exercise 8 — Cost comparison

Compare two options: function A with min instances 0 and no VPC connector; function B with min instances 1, a connector, and Cloud NAT. At only 30 requests/day, which factors would you measure to justify whether B is worth the cost?

## 12. Pre-production checklist

| Item | Criterion |
| --- | --- |
| **Trigger/ingress** | HTTP/Eventarc clearly defined, valid event delivery path, never unintentionally public. |
| **Authentication** | Invoker/trigger SA scoped to exact destination, valid token/audience. |
| **Runtime identity** | Dedicated SA with required Secret Manager and data permissions; no static JSON keys. |
| **VPC egress** | Direct VPC or connector intentionally chosen, matching network/subnet/region. |
| **Network path** | DNS, routes, firewall, Cloud NAT/Google APIs/PSA/PSC tested. |
| **Secrets** | Secret references used, version/rotation/rollback clear; never logged. |
| **Resources** | CPU/memory/timeout/concurrency/min/max instances load-tested against SLOs. |
| **Event semantics** | Idempotency, retry/backoff, loop prevention, and burst controls in place. |
| **Observability** | Logs/traces/errors, event deliveries, memory, DB connections, and cost tracked. |
| **Release** | Source/revision/config managed with staging, approvals, and rollback. |

## 13. Official documentation

Verify limits, CLI flags, and IAM permissions for your current Cloud Run functions model:

- [Cloud Run functions overview](https://cloud.google.com/run/docs/functions/overview)
- [Write Cloud Run functions](https://cloud.google.com/run/docs/write-functions)
- [Cloud Run ingress](https://cloud.google.com/run/docs/securing/ingress)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Serverless VPC Access connectors](https://cloud.google.com/vpc/docs/serverless-vpc-access)
- [Configure secrets for Cloud Run](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Secret Manager access control](https://cloud.google.com/secret-manager/docs/access-control)
- [Cloud Run CPU and memory](https://cloud.google.com/run/docs/configuring/services/cpu)
- [Cloud Run concurrency](https://cloud.google.com/run/docs/configuring/concurrency)
- [Cloud Run scaling and instance limits](https://cloud.google.com/run/docs/about-instance-autoscaling)
- [Eventarc triggers and CloudEvents](https://cloud.google.com/eventarc/docs/overview)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [gcloud functions deploy](https://cloud.google.com/sdk/gcloud/reference/functions/deploy)

**Takeaway:** secure function configuration requires **the right callers (ingress + IAM), the right outbound path (egress + VPC/DNS/NAT), the right identity for reading secrets (runtime SA + Secret Manager)**, and **proper resource limits**. With Eventarc, separate event delivery permissions from runtime permissions and design retry-tolerant handlers. Measure latency, errors, result durability, and cost under realistic workloads before going to production.
