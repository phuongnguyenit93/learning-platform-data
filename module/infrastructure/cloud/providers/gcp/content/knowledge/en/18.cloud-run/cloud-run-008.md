# Service Identity and Service-to-Service Authentication in Cloud Run

A system runs `orders-api` on Cloud Run to receive order requests and calls `inventory-api` to check stock. `inventory-api` should not allow anyone with its URL to call it. At the same time, `orders-api` must prove **the service's own identity** when calling internal APIs without storing a JSON service account key inside the container.

Cloud Run solves this need using **service identity** (the runtime service account), **Cloud Run IAM Invoker** on the target service, and a **Google-signed OpenID Connect (OIDC) ID token** with the matching audience. Within the **Cloud Run** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson connects IAM, HTTP, VPC networking, releasing, and monitoring to implement secure service-to-service communication.

After this lesson, you can:

1. Distinguish runtime service identity, deployer identity, service agent, and end users.
2. Grant invocation permissions following the **principle of least privilege** on the exact target Cloud Run service.
3. Fetch an ID token inside Cloud Run, set `aud`, and send requests with the right header.
4. Distinguish identity authentication from ingress controls, network connectivity, and business-level authorization.
5. Diagnose 401/403 errors, wrong audiences, missing permissions, or network failures; handle tokens safely.
6. Practice a two-Cloud-Run-service workflow and test both allowed and denied requests.

## 1. Authentication Flow Between Two Services

~~~mermaid
sequenceDiagram
    participant C as Authorized client calling A
    participant A as Cloud Run orders-api
    participant M as Metadata server
    participant B as Cloud Run inventory-api
    C->>A: HTTP request to A
    A->>M: Request ID token with audience URL(B)
    M-->>A: Google-signed ID token for A's SA
    A->>B: HTTPS + Authorization Bearer ID_TOKEN
    B->>B: Verify token, aud, IAM Invoker, and ingress
    B-->>A: Inventory result
    A-->>C: Application response
~~~

In the diagram, A has its own identity, such as `orders-caller@PROJECT_ID.iam.gserviceaccount.com`; B has a separate runtime identity, such as `inventory-runtime@PROJECT_ID.iam.gserviceaccount.com`. Permission to **call B** is granted to **A's service account on B**. B's permissions to access databases or Secret Manager are granted separately to B's service account on those respective resources.

| Entity | Role in the flow | Typical permissions needed |
| --- | --- | --- |
| **Deployer / CI for A** | Deploys revisions and attaches runtime service account | Cloud Run deploy permissions and `iam.serviceAccounts.actAs` on the service account attached to A |
| **A's runtime service account** | Represents the identity of code running inside A | `roles/run.invoker` **on B**, not a project-wide Admin role |
| **Cloud Run service B** | Receives requests and checks IAM at the Cloud Run layer before forwarding to the container | Configured to require authentication; IAM policy for A |
| **B's runtime service account** | Identity used when B's code calls Google Cloud APIs | Minimal roles on the databases, buckets, secrets, etc. that B actually uses |
| **Cloud Run service agent** | Google-managed identity for operating Cloud Run infrastructure | Not a service account that application containers should use to authenticate calls to B |
| **End user** | Customer using the application through A | Business permissions managed by the app/identity provider; does not implicitly get permission to call B directly |

### 1.1. Two Separate Questions

- **Authentication:** "Who is calling?" — Cloud Run verifies the Google-signed token and principal identity.
- **Authorization:** "Is that identity allowed to call B?" — The target service's IAM requires the `run.routes.invoke` permission, typically via `roles/run.invoker`.

Even when A is authorized to call B, B's code must still enforce **business authorization**: for instance, which user is allowed to view which order. Never assume that every request arriving through A is allowed to read every record in B.

### 1.2. Service Identity and Service Agent Are Not the Same

**Service identity** is the service account attached to a Cloud Run service/revision, used as the identity for the container to call Google Cloud APIs and fetch tokens. If no dedicated service account is attached, Cloud Run may fall back to the project's Compute Engine default service account per default configuration; best practice is creating a **dedicated user-managed service account per workload**.

**Cloud Run service agent** is a Google-managed account used to operate Cloud Run infrastructure and plays a different role from the runtime identity. The **deployer** is a third identity: the user or CI/CD pipeline needing deployment permissions plus `roles/iam.serviceAccountUser` (which includes `iam.serviceAccounts.actAs`) on the runtime service account in order to attach it to the service.

Do not use `roles/iam.serviceAccountTokenCreator` as a substitute for `roles/iam.serviceAccountUser` or `roles/run.invoker`. For A → B calls inside Cloud Run, A normally fetches ID tokens from the metadata server **without downloading JSON keys or impersonating another service account**.

## 2. Target Service IAM and Ingress Choices

### 2.1. Place Permissions in the Right Scope

Suppose only `orders-api` should invoke `inventory-api`. Grant `roles/run.invoker` to A's service account **on B**, rather than granting it to `allUsers` or across the entire project unnecessarily:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export CALLER="orders-api"
export TARGET="inventory-api"
export CALLER_SA="orders-caller@$PROJECT_ID.iam.gserviceaccount.com"

# IAM write operation; run once approved on the exact target service B
gcloud run services add-iam-policy-binding "$TARGET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$CALLER_SA" \
  --role="roles/run.invoker"

# Read-only: verify B's policy
gcloud run services get-iam-policy "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

`roles/run.invoker` grants the `run.routes.invoke` permission. Account A **does not need** `roles/run.admin` or permission to modify IAM on B simply to send requests. If B uses Cloud SQL, B needs its own database permissions and connectivity config; Invoker IAM on B does not grant database privileges.

### 2.2. IAM Check and Network Ingress Are Two Layers

| Control | What does it check? | Notes |
| --- | --- | --- |
| **Require authentication / Invoker IAM check** | Whether the principal has a valid token and permission to invoke the service | An endpoint may be reachable from the Internet yet still reject calls lacking permission. |
| **`ingress=all`** | Allows requests from valid ingress paths, including the Internet | **Does not** open IAM automatically; still requires a token if IAM check is enabled. |
| **`ingress=internal`** | Accepts only network sources/paths recognized by Cloud Run as internal | Cloud Run → Cloud Run usually requires proper **VPC egress/routing** configuration to be recognized as internal. |
| **`ingress=internal-and-cloud-load-balancing`** | Internal sources plus requests via a matching external Application Load Balancer | Commonly used to enforce Cloud Armor/IAP or centralize entrypoints at a load balancer. |

Do not assume "two Cloud Run services in the same project can always reach `internal` automatically." When Cloud Run is the caller, consult guidance on **receiving requests from other Cloud Run services**, Direct VPC egress or Serverless VPC Access, and proper routing. A valid token cannot bypass an ingress policy blocking the network path.

Conversely, `ingress=internal` **does not replace IAM**, because many internal workloads may share the same VPC. For private APIs, combine **controlled ingress** with **narrowly scoped Invoker IAM** where architecture calls for it.

### 2.3. Guarding Against Confused Deputy

If A is authorized to call B, yet A exposes a public `/proxy?url=...` endpoint that forwards arbitrary callers' requests straight to B, outsiders can abuse A's identity to perform unauthorized actions. This is the **confused deputy** vulnerability.

Therefore, A must authenticate callers, authorize each action, restrict allowed target endpoints/paths, avoid forwarding arbitrary tokens or inputs, and emit proper audit logs. Service-to-service authorization **does not** mean forwarding end-user ID tokens in place of service tokens.

## 3. ID Tokens: Getting the Right Identity and Audience

To invoke a Cloud Run service with Invoker IAM checks enabled, the standard mechanism is a **Google-signed OIDC ID token**. The token carries claims like `iss`, `sub`, `aud`, `iat`, and `exp`; Cloud Run validates signature, expiration, audience, and corresponding IAM permissions. **Never treat an OAuth access token for Google APIs as an interchangeable substitute for a Cloud Run ID token.**

### 3.1. Audience Rules

Suppose service B has the canonical URL:

~~~text
https://inventory-api-abcdef-uc.a.run.app
~~~

| Called endpoint | `aud` value to use |
| --- | --- |
| `https://inventory-api-abcdef-uc.a.run.app/health` | **Base** URL of service B |
| `https://inventory-api-abcdef-uc.a.run.app/api/items?id=1` | **Base** URL of service B; do not append path/query |
| URL of a **traffic tag** on B | Still use B's **base** URL, not the tag URL as audience |
| B invoked via a custom domain | Do not use the custom domain as audience by default; use the canonical URL or a **custom audience** configured on B |

Retrieve the canonical URL with a read-only command:

~~~bash
TARGET_URL="$(gcloud run services describe "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
printf 'Cloud Run target: %s\n' "$TARGET_URL"
~~~

**Distinction:** `TARGET_URL` used to mint the token is the **service base URL**, whereas the HTTP request endpoint can be `$TARGET_URL/health` or a business route. If using a custom audience, declare that audience on B and pass the exact configured string.

### 3.2. Recommended Method: Google Auth Library

Inside container A running on Cloud Run, the Google Auth library fetches an ID token from the runtime environment. Python example (code running inside **service A**, not in Cloud Shell):

~~~python
import os

import google.auth.transport.requests
import google.oauth2.id_token
import requests

target_url = os.environ["TARGET_URL"].rstrip("/")

def request_inventory():
    # audience must be the base URL of the target service, NOT /health
    auth_request = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(
        auth_request, target_url
    )
    response = requests.get(
        f"{target_url}/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.text
~~~

`google-auth` automatically picks up the environment's credentials, including Cloud Run's metadata server. No JSON service account key is needed. ID tokens typically expire after **one hour**; let the library manage tokens or refresh based on `exp` if caching. **Never log tokens** and never send them to untrusted hostnames.

### 3.3. Querying the Metadata Server Directly

When debugging or writing a custom client, code **inside Cloud Run A** can call the metadata server:

~~~bash
# Run INSIDE Cloud Run A's container; DO NOT run from a laptop or Cloud Shell
TARGET_URL="https://SERVICE_B_DEFAULT_RUN_APP_URL"
TOKEN="$(curl --fail --silent --show-error --get \
  -H "Metadata-Flavor: Google" \
  --data-urlencode "audience=$TARGET_URL" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity")"

curl --fail --show-error --silent \
  --max-time 10 \
  -H "Authorization: Bearer $TOKEN" \
  "$TARGET_URL/"

unset TOKEN
~~~

`default` in the metadata URL is an **alias for the service account attached to the revision**; it does not mean Cloud Run is necessarily using the project's Compute Engine default service account. The metadata endpoint returns an ID token carrying A's runtime identity; the request must include `Metadata-Flavor: Google`.

Never print `$TOKEN` to the terminal, store it in Cloud Logging, or pass it in query parameters. Use HTTPS to call B; bound retries, set timeouts, and send tokens only to trusted, explicitly configured target endpoints.

### 3.4. Which Header Should You Use?

Cloud Run accepts two headers for service authentication:

~~~http
Authorization: Bearer GOOGLE_SIGNED_ID_TOKEN
~~~

or:

~~~http
X-Serverless-Authorization: Bearer GOOGLE_SIGNED_ID_TOKEN
~~~

Use `X-Serverless-Authorization` when `Authorization` is already used by the application to carry an end-user credential. If both are sent, **Cloud Run prioritizes verifying `X-Serverless-Authorization`**; per Cloud Run's mechanism, the token signature in this header is stripped before headers reach the user container. Do not rely on it as a pass-through channel to forward the raw token to B.

**Two identity layers:** Cloud Run can authenticate **service A** via the token in `X-Serverless-Authorization` while container B inspects a separate end-user token in `Authorization`. B must still independently verify the user token and authorize access to business resources. Never assume both tokens represent the same principal.

### 3.5. Mechanisms Not to Confuse

| Mechanism | Used for | Does not replace |
| --- | --- | --- |
| **OIDC ID token** with `aud` set to B | Proving identity when A calls private Cloud Run B | Business authorization or Invoker IAM on B |
| **OAuth 2.0 access token** | Typically calling Google Cloud APIs like Cloud Storage/Secret Manager | Audience-bound ID token for invoking Cloud Run in the standard flow |
| **JSON service account key** | Only special cases with strict key lifecycle governance | Runtime identity minting tokens from the metadata server |
| **Self-signed custom JWT** | Certain federation or supported token-exchange protocols | Google-signed ID token validated by Cloud Run |
| **Cloud Run IAM policy** | Deciding which identities may invoke B | Ingress/VPC controls or business-tier authorization |

For workloads **outside Google Cloud**, prefer **Workload Identity Federation** to obtain short-lived credentials instead of downloading long-lived JSON keys. For developers testing via gcloud, `gcloud auth print-identity-token` is a manual testing tool; never use user tokens lacking an explicit audience as a production solution.

## 4. Lab: Cloud Run A Calling Cloud Run B with an ID Token

The following lab uses **Cloud Run service B** as the receiver and **Cloud Run service A** as the caller. B requires authentication; only A's runtime service account has Invoker permission on B. For simplicity, both services use `run.app` URLs and an ingress setting allowing requests to reach the IAM check layer. If your project enforces `internal` ingress, configure VPC egress first as covered in Section 2.2.

**Prerequisites:** a lab project with billing and permissions to create service accounts, deploy Cloud Run services, set IAM on **services A/B**, hold `iam.serviceAccounts.actAs` on the chosen service accounts, required build APIs, and a test budget. These commands are instructions only; **do not run them in production**.

### 4.1. Create Separate Identities

Run in Bash/Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export CALLER="orders-api-lab"
export TARGET="inventory-api-lab"
export CALLER_SA="orders-caller@$PROJECT_ID.iam.gserviceaccount.com"
export TARGET_SA="inventory-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com iam.googleapis.com

gcloud iam service-accounts create orders-caller \
  --display-name="Cloud Run caller lab"
gcloud iam service-accounts create inventory-runtime \
  --display-name="Cloud Run target lab"
~~~

Before continuing, the deployer needs `roles/iam.serviceAccountUser` on **both service accounts** plus Cloud Run deployment permissions per policy. To deploy from source using `--source`, Cloud Build/Artifact Registry permissions for the source deployment flow are also required. Never grant project-wide Editor/Owner or Token Creator just to work around a deploy permission error.

### 4.2. Deploy Service B Requiring Authentication

Use an organization-approved sample HTTP container. For example, Cloud Run's public sample image:

~~~bash
export TARGET_IMAGE="us-docker.pkg.dev/cloudrun/container/hello"

gcloud run deploy "$TARGET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$TARGET_IMAGE" \
  --service-account="$TARGET_SA" \
  --no-allow-unauthenticated

TARGET_URL="$(gcloud run services describe "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
printf 'B URL: %s\n' "$TARGET_URL"
~~~

`--no-allow-unauthenticated` tells Cloud Run to enforce Invoker IAM checks. It **does not automatically make the endpoint private on the network**; B's ingress must also be checked against project policy. In this lab calling B's `run.app` URL directly from A, if B sets `ingress=internal`, networking must ensure traffic is recognized as internal.

### 4.3. Grant Permission Strictly A → B

~~~bash
gcloud run services add-iam-policy-binding "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:$CALLER_SA" \
  --role="roles/run.invoker"

gcloud run services get-iam-policy "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Verify the policy **does not contain `allUsers`** and does not accidentally grant Invoker to B's service account, broad user groups, or the whole project needlessly. The IAM binding on B is what permits A to call B, not the `TARGET_URL` environment variable name.

### 4.4. Caller A Source Code

On the lab machine, create a `caller/` directory with the three files below. The code simply calls B's root endpoint, fetches an ID token with audience B, and **never returns the token in the HTTP response**.

**`caller/main.py`**

~~~python
import os

from flask import Flask, jsonify
import google.auth.transport.requests
import google.oauth2.id_token
import requests

app = Flask(__name__)
TARGET_URL = os.environ["TARGET_URL"].rstrip("/")

@app.get("/call")
def call_target():
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(
        auth_req, TARGET_URL
    )
    upstream = requests.get(
        TARGET_URL + "/",
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=10,
    )
    # Do not reflect the token or B's private payload back to A's client
    return jsonify(
        upstream_status=upstream.status_code,
        upstream_bytes=len(upstream.content),
    ), 200 if upstream.ok else 502
~~~

**`caller/requirements.txt`**

~~~text
Flask>=3,<4
gunicorn>=22,<24
google-auth>=2,<4
requests>=2,<3
~~~

**`caller/Procfile`**

~~~text
web: gunicorn --bind :$PORT main:app
~~~

The example constrains dependencies by major version; for real deployments, pin tested versions and scan dependencies. This is a demo and omits production-grade tracing, circuit breakers, and full error handling.

### 4.5. Deploy A with Its Dedicated Service Account

From the parent directory containing `caller/`:

~~~bash
gcloud run deploy "$CALLER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source=./caller \
  --service-account="$CALLER_SA" \
  --set-env-vars="TARGET_URL=$TARGET_URL" \
  --no-allow-unauthenticated

CALLER_URL="$(gcloud run services describe "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
printf 'A URL: %s\n' "$CALLER_URL"
~~~

`--source` requires the build pipeline to be enabled along with build/deploy identity permissions. A's entrypoint also requires authentication; this is intentional to avoid creating a public proxy wielding A's identity. Never let `TARGET_URL` accept arbitrary values from user query parameters.

### 4.6. Test Both Authorized and Denied Access

**Negative test:** call B **without a token**:

~~~bash
curl --silent --show-error --include "$TARGET_URL/"
~~~

Expected result: **401 or 403** depending on how Cloud Run evaluates the request and policy; crucially, it **must not return a successful business response**. If you receive 200 from B, inspect Invoker IAM checks and IAM bindings before continuing.

**Grant the tester permission to call A, without granting access to B:**

~~~bash
# Use only a real user principal in the lab project, with approval
TEST_USER="YOUR_DEVELOPER_EMAIL"
gcloud run services add-iam-policy-binding "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="user:$TEST_USER" \
  --role="roles/run.invoker"
~~~

**Positive test through A** (only for `TEST_USER` authenticated in gcloud):

~~~bash
# User's gcloud token is ONLY for TESTING, not the runtime A->B token
USER_TOKEN="$(gcloud auth print-identity-token)"
curl --silent --show-error --include \
  -H "Authorization: Bearer $USER_TOKEN" \
  "$CALLER_URL/call"
unset USER_TOKEN
~~~

Expected result: A returns JSON with `upstream_status: 200` if sample service B is healthy, caller A uses the right runtime identity, and Invoker is granted on B. The user token sent to A is **distinct** from the ID token that A mints to call B.

Next, use the same tester account to call B directly: as long as that account **lacks** Invoker permission on B, the request must be rejected. This confirms permissions were not overly broad or leaked to the user.

**Control check:** temporarily revoke A → B permission in the lab and repeat the request to A; the internal call must stop succeeding. Only run this control check if approved and planned for re-granting—never test this on a production service.

### 4.7. Clean Up Only Lab Resources

After confirming these are the **two lab services** with no other apps depending on them:

~~~bash
gcloud run services delete "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" --quiet
gcloud run services delete "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" --quiet

# Delete ONLY the two service accounts created for this lab and unused elsewhere
gcloud iam service-accounts delete "$CALLER_SA" \
  --project="$PROJECT_ID" --quiet
gcloud iam service-accounts delete "$TARGET_SA" \
  --project="$PROJECT_ID" --quiet
~~~

If you granted the deployer `roles/iam.serviceAccountUser` or created an Artifact Registry repository, build artifacts, and dedicated logs for the exercise, check and clean up **only those lab-managed resources** per policy. Deleting a service does not automatically clean up all images, logs, or broader IAM bindings. Cloud Build, Artifact Registry, Cloud Run, and Cloud Logging costs may appear with a billing delay.

## 5. Synchronous and Asynchronous Invocation

### 5.1. Synchronous HTTP A → B

The pattern in Section 4 is **synchronous invocation**: A sends an HTTP request and waits for B to respond. It fits when A needs an immediate answer, but you must define **timeouts, retries, idempotency, and concurrency limits**:

- Set an HTTP timeout shorter than A's business deadline; never wait indefinitely.
- Retry only on appropriate errors, using backoff with jitter and a bounded retry count; a **POST creating an order** needs an idempotency key to prevent duplicate execution.
- Use circuit breakers or fallbacks if B becomes unavailable; avoid cascading failures stalling every instance of A.
- Monitor p95/p99 latency and error rates per hop, not just final HTTP status codes.
- If A uses `X-Serverless-Authorization` to authenticate to B, B can still receive a separate user token in `Authorization` by design, but must validate that user token independently.

### 5.2. Cloud Tasks Calling B with OIDC

For tasks that do not need an immediate result, A can enqueue work into **Cloud Tasks**. Cloud Tasks calls B's URL and automatically attaches an OIDC token for the service account configured on the task. Conceptual flow:

~~~mermaid
flowchart LR
    A["Cloud Run A"] -->|Create task| Q["Cloud Tasks queue"]
    Q -->|"POST + OIDC ID token"| B["Cloud Run B"]
    B -->|2xx on success| Q
    Q -. "Retry per policy on failure" .-> B
~~~

When creating an HTTP task:

- `oidcToken.serviceAccountEmail` specifies the identity Cloud Tasks uses to call B; it generally must belong to the **same project as the queue**.
- That service account needs `roles/run.invoker` **on B**.
- The principal creating the task needs enqueuer permission plus `iam.serviceAccounts.actAs` on the task's service account per Cloud Tasks rules.
- Set **`audience` to B's base URL**, especially when the task URL includes a path like `/process`. Do not omit audience if the default would use the full URL including the path.
- Handler B must handle **at-least-once delivery**, retries, duplicate tasks, dead-letter queues, and timeouts as required.

Illustrative CLI command after the **queue, identity, and permissions are already prepared**:

~~~bash
gcloud tasks create-http-task \
  --queue="orders-queue" \
  --location="$REGION" \
  --url="$TARGET_URL/process" \
  --method=POST \
  --oidc-service-account-email="tasks-caller@$PROJECT_ID.iam.gserviceaccount.com" \
  --oidc-token-audience="$TARGET_URL"
~~~

Syntax and flags may vary across gcloud versions; check `gcloud tasks create-http-task --help` in an authorized environment. This command **creates a task that can trigger a real request**; do not run it against a production queue without approval. Cloud Run B must also expose `/process` with idempotent handling; the sample `hello` container in the earlier lab **does not have** this endpoint.

### 5.3. Other Options

**Pub/Sub push** and **Cloud Scheduler** can also use OIDC identities to invoke Cloud Run when configured per product docs. With asynchronous delivery, the event producer typically does not need to fetch B's ID token itself; the intermediary service attaches tokens using an authorized identity. Cloud Run also offers managed internal connectivity depending on product release, such as **express links (Preview)**; use these only after checking support status, limits, and organization policies.

Never assume asynchronous delivery eliminates IAM requirements: the principal invoking B still needs proper permissions, and B must still validate business payloads.

## 6. Diagnosing Authentication and Connectivity Errors

### 6.1. Error Table by Layer

| Symptom | Common root cause | What to check |
| --- | --- | --- |
| HTTP **401** or **403** calling B with no token | B requires authentication — likely working as designed | Verify endpoint and policy; never open public access just to clear the error. |
| **401/403** even though A sends a token | Wrong audience, expired/invalid token, A's SA missing Invoker | Compare `aud` URL, A's runtime service account, and B's IAM policy. |
| **403** with valid token when B has `ingress=internal` | Traffic is not arriving over a path Cloud Run treats as internal | Check B's ingress and A's VPC egress/routing; a token cannot bypass network checks. |
| **403** deploying A with a new service account | Deployer missing `iam.serviceAccounts.actAs` or deploy permission | Grant `roles/iam.serviceAccountUser` on the exact runtime SA plus appropriate deploy role. |
| Cannot fetch token from metadata | Running on laptop/Cloud Shell, missing header, broken runtime env | Metadata endpoint example only works **inside a compatible Cloud Run/Compute environment**. |
| A uses an OAuth access token while B expects an ID token | Confused Google APIs auth flow with private Cloud Run | Use a Google-signed ID token carrying B's audience. |
| B returns **404/405** after authenticating | Wrong path or method; container B does not support the endpoint | Inspect routes/paths, HTTP method, and B's app logs. |
| A returns **502/504** after calling B | Upstream timeout, DNS, TLS, quota, B crashed, or A forwards errors | Inspect both A/B logs; check networking, retries, and backend health. |
| Request to traffic tag rejected | Token set `aud` to the tag URL instead of the base service URL | Use B's canonical base URL for token audience while targeting the tag URL for the request. |
| Direct call to B succeeds from an unknown account | Overly broad IAM policy, `allUsers`, or Invoker IAM check disabled | Audit IAM bindings and service security settings immediately. |
| A succeeds but user data leaks | B trusts A's identity alone without checking end-user/tenant permissions | Add business-layer authorization; review confused deputy risks. |

You cannot determine the exact root cause from an HTTP status code alone. Correlate **status code, request path, IAM policy, ingress, audience, service status, and logs**; requests blocked before reaching the container may not appear in application logs.

### 6.2. Inspecting Identities and IAM in Order

Read-only commands:

~~~bash
gcloud config get-value project

# Verify which service account service A is using
gcloud run services describe "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(spec.template.spec.serviceAccountName,status.url)"

# Inspect which identities B allows to invoke it
gcloud run services get-iam-policy "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION"

# Confirm the right URL for audience
gcloud run services describe "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url)"
~~~

Different CLI versions may render YAML paths slightly differently; if a field is empty, run `gcloud run services describe "$CALLER" --format=yaml` and locate the runtime service account in the actual output. Never share full service dumps containing environment variables or secrets in unauthorized channels.

### 6.3. Reading Request Logs and Correlating Both Services

Example Cloud Logging Query Language filter for error requests on A:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api-lab"
httpRequest.status>=400
~~~

Similarly, swap `orders-api-lab` for B's name to find requests that reached service B and were recorded by Logging. If B shows no logs, **do not conclude B never received a request**: the call may have been blocked by IAM/ingress before the container, filtered by log scope/retention, or missed by an overly narrow query.

Inside the app, log **request ID / trace ID**, service name, revision, status, and latency, but never log `Authorization`, `X-Serverless-Authorization`, ID tokens, or sensitive payloads. Cloud Audit Logs help trace IAM/deployment changes, though they do not replace request logs for latency analysis.

### 6.4. Cross-Project and Multi-Environment Setups

If A lives in project X and B lives in project Y, the **IAM binding on B** must still specify A's exact service account and comply with organization policies. If A's runtime identity is itself a service account **in a different project from A**, cross-project service account attachment imposes additional conditions on the Cloud Run service agent and organization policies; never assume `roles/iam.serviceAccountUser` alone suffices.

Separate identities across **dev/staging/prod**, and never grant a single service account Invoker across every production service. Across multiple regions or VPC Service Controls perimeters, also account for egress paths, ingress policies, quotas, latency, and data residency.

## 7. Production Design: Least Privilege and Operability

A secure A → B design should be reviewed from **infrastructure to business logic**:

| Layer | Recommended decision |
| --- | --- |
| **Identity** | Every workload gets its own runtime service account; avoid shared JSON keys or over-privileged default accounts. |
| **IAM** | Only A's SA gets Invoker **on B**; B's service account gets only the permissions its dependencies require. |
| **Deployment** | CI/CD holds deploy rights and `actAs` on the exact service account; avoid unnecessary Token Creator/Owner roles. |
| **Ingress** | Choose `internal` when VPC/routing is configured, or another appropriate ingress setting; never confuse ingress with IAM. |
| **Tokens** | Environment-minted OIDC ID tokens with B's URL as audience and bounded lifetime; never log or store long-term. |
| **HTTP** | TLS, timeouts, bounded retries/backoff, idempotency for writes, and confused-deputy protections. |
| **Observability** | Request/trace IDs, 401/403/5xx, p99 latency, IAM/deployment audits, SLO-based alerts. |
| **Reliability** | Quotas, concurrency, autoscaling behavior, cascading failure protection, queues for async work. |
| **Cost** | Factor in Cloud Run requests, CPU, path-based networking, Cloud Tasks (if used), and Logging. |

**Pragmatic authorization rule:** a service needing to call three target services should hold three Invoker bindings—one on each target—rather than becoming Cloud Run Admin across the project. When a service is deleted or refactored, review and revoke unneeded bindings.

## 8. Exercises and Self-Check Questions

### Scenario A — Wrong Audience Despite Having Permission

`orders-api` uses service account `orders-caller` and already has Invoker on `inventory-api`. Yet A's code calls `https://inventory.example.com/check` and mints a token with `aud=https://inventory.example.com/check`. B returns 401/403.

**Task:** identify the bug and propose a fix without making B public.

**Suggested answer:** retrieve **B's** canonical `run.app` URL and set it as the ID token audience; the HTTP request can still hit a path or custom domain if ingress/routing supports it. If a custom audience is required, configure a **valid custom audience on B**. Do not grant Admin/Owner because this is not a missing privilege issue.

### Scenario B — A Has Invoker, Yet B Sets Internal Ingress

Two Cloud Run services are in the same project. A sends a valid ID token and holds IAM Invoker, yet requests to B are still blocked. B has `ingress=internal`, while A has no VPC egress/routing configured.

**Task:** explain the two independent checks and propose the remediation.

**Suggested answer:** IAM verifies identity/permissions, whereas ingress verifies the network path. Configure **Direct VPC egress or a connector** with appropriate routing (e.g., all-traffic with Private Google Access or a supported internal path), then re-test. Never switch B to public just to skip network design.

### Scenario C — One Shared Service Account

An operations team attaches a single project-wide Editor service account to `payments`, `inventory`, and `email`, then grants Invoker across all services. A vulnerability in `email` can now be leveraged to call payment APIs.

**Task:** redesign using least privilege.

**Suggested answer:** create separate runtime service accounts per workload and environment, grant Invoker only on genuinely required services, separate database/bucket/secret permissions, audit deployer `actAs` permissions, and remove unnecessary Editor roles. Add business-tier authentication/authorization inside `payments` to prevent confused deputy attacks.

### Applied Exercise

Draw a **Frontend → Orders → Inventory** diagram where only Frontend calls Orders and only Orders calls Inventory. Build a table listing: **service**, **runtime SA**, **target IAM Invoker**, **ingress**, **ID token audience**, and **negative test**. Also answer: if Orders uses Cloud Tasks to call Inventory asynchronously, **which service account** must have Invoker on Inventory and who needs `actAs` permission when creating the task?

### Self-Check Questions

1. **What is Cloud Run's runtime identity?** — The service account attached to a service/revision used by application code to access Google Cloud or mint ID tokens.
2. **Should Invoker be granted on A or B?** — On **B**, granted to the principal representing A's runtime service account.
3. **What permission does the deployer need to attach a runtime SA?** — `iam.serviceAccounts.actAs`, typically via `roles/iam.serviceAccountUser`, plus Cloud Run deploy permissions.
4. **Does A need a JSON service account key inside the container?** — No; use the metadata server / Google Auth library and the service's attached identity.
5. **What is `aud` when calling `B/path`?** — B's base URL or a configured custom audience, not the path.
6. **If both authorization headers carry tokens, which one does Cloud Run use?** — `X-Serverless-Authorization` takes precedence.
7. **Does `ingress=internal` replace IAM?** — No. They are two separate control layers.
8. **Once the receiver authenticates A, does it still need to check user permissions?** — Yes, whenever business operations depend on user identity or roles.
9. **Should a developer's gcloud token be used in production?** — No; use audience-bound ID tokens minted from the runtime service identity.
10. **Should a timed-out POST request be retried unconditionally?** — No; enforce idempotency, bound retries, and assess whether the operation may have already completed.

## 9. Official Documentation

- [Cloud Run — Authenticating service-to-service](https://cloud.google.com/run/docs/authenticating/service-to-service): ID tokens, audiences, headers, and token retrieval methods.
- [Cloud Run — Introduction to service identity](https://cloud.google.com/run/docs/securing/service-identity): service identity, metadata server, and credentials.
- [Cloud Run — Configure service identity](https://cloud.google.com/run/docs/configuring/services/service-identity): runtime service accounts and `iam.serviceAccounts.actAs`.
- [Cloud Run — Access control with IAM](https://cloud.google.com/run/docs/securing/managing-access): Invoker role, authentication requirements, and policies.
- [Cloud Run — Restrict ingress](https://cloud.google.com/run/docs/securing/ingress): `all`, `internal`, `internal-and-cloud-load-balancing`.
- [Cloud Run — Private networking](https://cloud.google.com/run/docs/securing/private-networking): VPC routing requirements between Cloud Run services using internal ingress.
- [Cloud Run — Troubleshooting](https://cloud.google.com/run/docs/troubleshooting): diagnosing 401/403, IAM, service configurations, and failed requests.
- [Cloud Tasks — Create HTTP tasks](https://cloud.google.com/tasks/docs/create-tasks): OIDC service accounts, audiences, and retries for HTTP targets.
- [gcloud tasks create-http-task](https://cloud.google.com/sdk/gcloud/reference/tasks/create-http-task): OIDC flag syntax.

**Takeaway:** a secure A → B flow requires three independent conditions: **A runs under the right service identity**, **A sends a Google-signed ID token with B's audience**, and **B authorizes A's principal via IAM over a permitted ingress path**. Applications must still enforce their own business authorization. Keeping these layers distinct lets you diagnose failures accurately without over-granting permissions or unintentionally exposing services publicly.
