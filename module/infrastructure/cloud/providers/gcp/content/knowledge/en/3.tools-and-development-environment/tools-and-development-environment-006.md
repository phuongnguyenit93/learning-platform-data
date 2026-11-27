# Calling Google Cloud REST APIs and Discovering APIs

When operating on Google Cloud, learners usually start with the Google Cloud Console or `gcloud` commands. Behind many of those operations, however, are APIs that can be called from programs, CI/CD pipelines, or automation tools. Knowing how to read REST API documentation and make an authenticated call helps you understand exactly **which resource is being affected, with what permissions, via which HTTP method, and how the outcome can be verified**.

This lesson belongs to the **GCP Tools and Development Environment** chapter of the `CLOUD_PROVIDERS_GCP` module. API calling skills support the entire Google Cloud learning journey: exploring projects and IAM, inspecting VPC, Compute Engine, GKE, Cloud Run, storage and database services, and then automating releases, observing reliability, and managing costs. The primary hands-on example is **listing Cloud Run services via the REST API using a read-only HTTP request**.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish Google Cloud management APIs from the HTTP endpoints of your own applications running on GCP.
2. Locate the right service, API version, REST method, parent resource, parameters, permissions, and response types.
3. Call an API securely using an OAuth 2.0 access token with `curl` or PowerShell without putting tokens in source code.
4. Read JSON responses, handle pagination, and recognize `400`, `401`, `403`, `404`, `429`, and `5xx` errors.
5. Know when to use direct REST, `gcloud`, a client library, or Infrastructure as Code; plan safely before calling resource-writing APIs.

## 2. Where Do REST APIs Sit in Google Cloud?

Picture Google Cloud as having two distinct HTTP layers:

| Layer | Example | Purpose and Authentication |
| --- | --- | --- |
| **Google Cloud API (control plane)** | `run.googleapis.com`, `compute.googleapis.com`, `cloudresourcemanager.googleapis.com` | List, create, configure, or delete cloud resources; typically authenticated with an OAuth 2.0 access token and governed by IAM. |
| **Application API (data/application plane)** | `https://my-service-...run.app/orders` | Handle business logic you wrote. Authentication is decided by the application and access config; private Cloud Run services usually require an **OIDC ID token** matching the audience. |

**Do not confuse an access token with an ID token.** Google Cloud management REST APIs typically accept `Authorization: Bearer ACCESS_TOKEN`. When calling an authenticated Cloud Run service endpoint, the usual mechanism is `Authorization: Bearer ID_TOKEN` with the appropriate audience. The two token types serve two different purposes; do not swap them out of habit.

Google Cloud APIs may be exposed over REST/JSON, gRPC, or both. REST documentation describes how resource operations map to paths, HTTP methods, and JSON. Even when using an SDK or `gcloud`, being able to read REST documentation helps you understand fields and errors at a low level.

## 3. Anatomy of a REST Call

Consider a request to list Cloud Run services in a project and region:

```http
GET https://run.googleapis.com/v2/projects/PROJECT_ID/locations/REGION/services?pageSize=20
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
```

| Component | Meaning | What Must Be Verified |
| --- | --- | --- |
| `GET` | Read a list without requesting resource changes | Does the method documentation match `list` and use `GET`? |
| `https://run.googleapis.com` | Cloud Run management API host | Is this the right product API to operate on? |
| `/v2` | REST API version | Does it match the documentation version and JSON schema? |
| `projects/PROJECT_ID` | Project scope | Are you using the real project ID of an authorized environment? |
| `locations/REGION` | Region scope | Which region does the service live in? Does the API accept that location? |
| `services` | Resource collection | Do you need `list` or `get` for a specific name? |
| `pageSize=20` | Query parameter | Does the method support `pageSize` and `pageToken`? |
| `Authorization` | Identity of the calling user/workload | Is the token unexpired and does the principal have required IAM permissions? |

In resource-oriented APIs, resource names usually take a hierarchical form:

```text
projects/PROJECT_ID/locations/REGION/services/SERVICE_NAME
```

That differs from the application URL that end users visit. The resource name is used for management APIs, whereas the application URL is used to send business traffic.

Common HTTP methods:

| Method | Common Effect | Caution |
| --- | --- | --- |
| `GET` | Read one resource or a list | May return multiple pages; IAM and quota requirements still apply. |
| `POST` | Create a resource or invoke an action | Do not automatically assume it can be retried safely. |
| `PATCH` | Partially update a resource | Some APIs require `updateMask`, version/etag, or asynchronous operations. |
| `PUT` | Replace/update a resource where supported | Check exact semantics to avoid dropping fields that were omitted. |
| `DELETE` | Delete a resource | Check dependencies, retention, deletion conditions, and recovery plan. |

Not every API provides every method, the same parameter names, or the same write semantics. **The documentation for the specific method is the authoritative source**, not guesses from other APIs.

## 4. Workflow for Discovering a Google Cloud API

An effective discovery workflow moves from **need → service name → resource type → method → auth requirements → test call**.

### Step 1: Write the Desired Action as a Clear Sentence

Example: "List the Cloud Run services in project `demo-learning`, region `asia-southeast1` that this account is allowed to see." This sentence clearly identifies the object, scope, and read-only operation. A vague phrase like "view services" is not enough to find the exact endpoint.

### Step 2: Find the Method in the REST Reference

For the example above, check the official documentation:

- [Cloud Run Admin API v2 — projects.locations.services.list](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/list)
- [Cloud Run Admin API v2 — projects.locations.services.get](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/get)
- [Google Cloud APIs Overview](https://cloud.google.com/apis/docs/overview)

For each method, read at least six sections: **HTTP request**, path parameters, query parameters, request body, response body, and OAuth scopes/IAM permissions. If the method creates/updates/deletes resources, also read conditions on long-running operations, concurrency/etag, and quotas.

Some services have multiple versions like `v1`, `v2` or multiple management interfaces. Do not mix a URL path taken from `v2` with a JSON schema described in `v1` documentation.

### Step 3: Explore Interactively with APIs Explorer

Many Google REST reference pages show a **Try this method / APIs Explorer** panel. This tool lets you fill in parameters, inspect requests and responses, and test OAuth with an authorized account. When practicing:

1. Start with a `GET/list` method first.
2. Enter the right project and location for your test environment.
3. Read the scopes and permissions required by the tool.
4. Inspect the HTTP status and JSON response; move to write methods only after understanding their effect.

Do not paste access tokens, private keys, customer data, or passwords into documentation, screenshots, or public shares. APIs Explorer helps you learn syntax; it does not replace production change control workflows.

### Step 4: Discover Programmatically with the Discovery Document (When Supported)

Google APIs Discovery Service provides metadata describing published APIs, including names, versions, and discovery document URLs. You can query the public directory and find the `run` entry:

```bash
curl --silent --show-error \
  "https://discovery.googleapis.com/discovery/v1/apis" \
  | jq '.items[] | select(.name == "run") | {name, version, discoveryRestUrl}'
```

If a version has a `discoveryRestUrl`, open that URL to inspect resources/methods, parameters, and schemas (actual structure depends on each API). For APIs without a suitable Discovery document, read the REST reference or the service's official OpenAPI documentation. **Do not assume Discovery lists every gRPC interface or every new feature of every product.**

### Step 5: Cross-Check with `gcloud` or Client Libraries

A CLI command helps verify the output a user sees:

```bash
gcloud run services list \
  --project="demo-learning" \
  --region="asia-southeast1"
```

CLI and REST results may differ in display format, pagination, or default fields; compare by **resource name and status**, without expecting both outputs to always share the exact same structure.

## 5. Preparing the Environment and Access Permissions

Practice requires:

- **Google Cloud CLI** installed (to obtain tokens) and an HTTP client such as `curl` or PowerShell `Invoke-RestMethod`. `jq` is an optional utility for reading JSON.
- An authorized **project ID** and **region** to inspect. Examples use `demo-learning` and `asia-southeast1` for illustration; replace them with your own environment values.
- The **Cloud Run API** (`run.googleapis.com`) enabled for the project according to organization policy.
- The calling principal granted appropriate permissions; listing Cloud Run services requires the `run.services.list` IAM permission at the right scope. A common role to consider is `roles/run.viewer`; apply the principle of least privilege rather than using Owner/Editor.

Check the project currently selected in gcloud and the API enablement status:

```bash
gcloud config get-value project

gcloud services list --enabled \
  --project="demo-learning" \
  --filter="name:run.googleapis.com"
```

`gcloud config get-value project` only shows the **current CLI configuration**; it does not automatically set the project inside a REST URL you construct manually. If the API is disabled or the account lacks permissions, ask an administrator to handle it in the permitted environment. Enabling APIs, granting IAM, and creating resources are configuration-changing operations, not read-only inspection steps.

## 6. Authentication: OAuth 2.0, ADC, Service Accounts, and IAM

### 6.1. Accounts for Manual Operations

When learning on a personal machine, sign in to the CLI with an authorized Google account:

```bash
gcloud auth login
gcloud auth list
```

Obtain a short-lived access token for Google Cloud APIs:

```bash
gcloud auth print-access-token
```

This command **prints the token to stdout**, so run it only in a private terminal and do not copy the token into chats, issues, CI logs, or commits. In the next example, the token is stored in a temporary shell variable to send over HTTPS.

### 6.2. Distinguishing Authentication from Authorization

A valid token only proves identity and authentication scope (OAuth scope). **IAM** determines whether that identity is allowed to perform `run.services.list`, `compute.instances.list`, or other operations on a specific resource. Having a token does not mean having permission to view every project.

When calling Google Cloud APIs, a common scope is `https://www.googleapis.com/auth/cloud-platform`. Scope is an OAuth-layer condition; it does not replace IAM. Some APIs also enforce project conditions, service enablement status, quotas, VPC Service Controls, or Organization Policy.

### 6.3. Application Default Credentials (ADC) for Application Code

When an application uses a Google Cloud client library, the library typically looks for **Application Default Credentials**. On a development machine, you can configure separate credentials for ADC:

```bash
gcloud auth application-default login
gcloud auth application-default print-access-token
```

**Two separate credential stores:** `gcloud auth login` serves the CLI identity, while `gcloud auth application-default login` creates credentials for ADC. They can point to different principals. Some APIs with user credentials also require a quota project; when encountering that error, check `gcloud auth application-default set-quota-project PROJECT_ID` and the `serviceusage.services.use` permission.

On Cloud Run, GKE, or Compute Engine, applications should use the **workload identity** provided by the platform (such as a service account attached to the resource, or Workload Identity Federation where appropriate), preferring short-lived tokens. Avoid issuing long-lived service account key files unless necessary; control runtime IAM and secret storage carefully.

### 6.4. Can API Keys and ID Tokens Replace Access Tokens?

There is no "one credential type for all APIs" rule:

| Auth Method | When Commonly Used | Things to Remember |
| --- | --- | --- |
| OAuth 2.0 **access token** | Google Cloud management APIs requiring IAM | Token expires; effective permissions depend on principal, scopes, and IAM. |
| **ADC** | Apps/client libraries needing Google credentials based on environment | ADC is a **credential-lookup mechanism**, not a new token type. |
| OIDC **ID token** | Calling private Cloud Run apps and certain audience-validated endpoints | Proves identity to the target service; not used in place of an access token when calling Cloud Run Admin API. |
| **API key** | Certain Google APIs supporting key-based access and rate limits | Cannot replace an IAM principal for resource management operations requiring OAuth. |

## 7. Hands-On: Calling the Cloud Run REST API with `curl`

### 7.1. Sending a Request to List Services

The following example uses Bash and performs an HTTP `GET` only:

```bash
PROJECT_ID="demo-learning"
REGION="asia-southeast1"
GCLOUD_ACCESS_TOKEN="$(gcloud auth print-access-token)"

curl --silent --show-error --fail-with-body \
  --get "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services" \
  --data-urlencode "pageSize=20" \
  -H "Authorization: Bearer ${GCLOUD_ACCESS_TOKEN}" \
  -H "Accept: application/json"
```

Replace `PROJECT_ID` and `REGION` with an authorized test environment. On some older `curl` versions that do not support `--fail-with-body`, you can use `--fail` and add separate logic to capture status/response body. Turn off shell tracing (`set -x`) before handling tokens to avoid leaking values in logs.

What happened?

1. `gcloud` fetches a short-lived OAuth access token for the current CLI account.
2. `curl` sends `GET` to `run.googleapis.com` over TLS with the `Authorization: Bearer ...` header.
3. Google validates the token, enabled API, and principal's IAM permission.
4. If valid, the server returns JSON containing a list of services (possibly empty) and a next-page token if more results exist.

You can also specify a quota/billing project using the `x-goog-user-project` header **when required by the API and credential type**:

```http
x-goog-user-project: PROJECT_ID
```

This is not a way to "borrow permissions": the principal still needs permission to use the quota project (typically `serviceusage.services.use`), along with IAM permissions on the target resource. Do not blindly add the header and assume every `403` is solely an auth issue.

### 7.2. PowerShell Version

If using PowerShell 5.1/7 on Windows:

```powershell
$ProjectId = "demo-learning"
$Region = "asia-southeast1"
$AccessToken = gcloud auth print-access-token
$Url = "https://run.googleapis.com/v2/projects/$ProjectId/locations/$Region/services?pageSize=20"

$Headers = @{
    Authorization = "Bearer $AccessToken"
    Accept = "application/json"
}

$Result = Invoke-RestMethod -Method Get -Uri $Url -Headers $Headers
$Result.services | Select-Object name, uri, ingress
```

`$Result` represents the JSON object parsed by PowerShell; if there are no services, the `services` property may be empty or absent. HTTP errors in PowerShell typically throw exceptions; catch them and inspect status/response body when diagnosing.

### 7.3. Reading JSON Responses Properly

An illustrative response looks like:

```json
{
  "services": [
    {
      "name": "projects/demo-learning/locations/asia-southeast1/services/order-api",
      "uri": "https://order-api-example.a.run.app",
      "ingress": "INGRESS_TRAFFIC_ALL"
    }
  ],
  "nextPageToken": "TOKEN_IF_MORE_RESULTS"
}
```

This is **illustrative data**, not a real resource. Only use properties and enum values matching the response schema of the API version you call. The `uri` field is the service URL, while `name` is the resource name used in management APIs. If `nextPageToken` is absent or empty, you have normally reached the last page.

With `jq`, extract the key fields:

```bash
curl --silent --show-error --fail-with-body \
  "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services?pageSize=20" \
  -H "Authorization: Bearer ${GCLOUD_ACCESS_TOKEN}" \
  | jq '{items: [(.services // [])[] | {name, uri, ingress}], nextPageToken}'
```

`.services // []` also handles responses that have no `services` list. Do not write automation that depends on fields not guaranteed by the API.

### 7.4. Getting a Specific Service

When you already know the service name:

```bash
SERVICE_NAME="order-api"

curl --silent --show-error --fail-with-body \
  "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services/${SERVICE_NAME}" \
  -H "Authorization: Bearer ${GCLOUD_ACCESS_TOKEN}" \
  -H "Accept: application/json"
```

This is the `projects.locations.services.get` method, which requires `run.services.get`. Do not use `get` to view all services because that method requires a specific resource name.

## 8. Pagination, Filters, Quotas, and Consistent Results

For large resource sets, many Google Cloud `list` APIs return a subset of results together with `nextPageToken`. Do not conclude that a project only has 20 services because the first call used `pageSize=20`.

Safe pagination flow:

```text
GET .../services?pageSize=20
  ├─ services: [page 1]
  └─ nextPageToken: "abc"
GET .../services?pageSize=20&pageToken=abc
  ├─ services: [page 2]
  └─ nextPageToken: ""
=> Complete when nextPageToken is empty/absent.
```

When writing scripts:

1. Use the `pageToken` returned from **the same method**; do not construct or decode tokens yourself.
2. Keep query parameters consistent across pages; URL-encode tokens properly.
3. Do not assume stable sort order unless guaranteed by the API; lists may shift while resources are added or deleted.
4. Do not assume every method supports `filter`, `orderBy`, and `pageSize` identically; check the reference.
5. Set request limits, reasonable retries, and monitor quotas; an infinite pagination loop can also incur costs or hit rate limits.

For systems requiring a consistent snapshot, calling `list` across multiple pages while resources continuously change may not meet requirements; verify the API's guarantees or design an appropriate reconciliation process.

## 9. Reading HTTP Errors and Handling Retries

When testing REST APIs, do not look only at the HTTP status. Read the JSON error body as well (usually containing `error.code`, `error.message`, `error.status`, and sometimes `error.details`), and record the timestamp, method, resource name, and request ID if provided.

| HTTP status | Common Causes | Direction to Check |
| --- | --- | --- |
| `400 Bad Request` | Wrong path/query/body, invalid field, missing parent | Read the reference and error details; check field names, region, enums, and URL encoding. |
| `401 Unauthorized` | Missing/invalid/expired access token or missing scope | Obtain a fresh token of the right type; verify `Authorization` header and OAuth scopes. |
| `403 Forbidden` | Missing IAM permission, disabled API, unauthorized quota project, or org constraint | Read reason/details; check principal, resource, API enablement, quota/billing, Organization Policy. |
| `404 Not Found` | Wrong project/region/resource, wrong API version/path, or resource does not exist | Check full resource name and region; some systems intentionally do not reveal resource existence. |
| `409 Conflict` | Duplicate resource, update conflict, operation state not appropriate | Verify current state and method semantics; avoid unconditional retries. |
| `429 Too Many Requests` | Quota exceeded or rate limited | Slow down, inspect quotas, apply backoff and `Retry-After` if present. |
| `500/502/503/504` | Server error or transient network/dependency error | Controlled retry with exponential backoff and jitter, based on operation safety. |

Example of a common error JSON (illustrative):

```json
{
  "error": {
    "code": 403,
    "message": "Permission denied on resource.",
    "status": "PERMISSION_DENIED"
  }
}
```

**Retrying is safe only when you understand request semantics.** `GET` can usually be retried because it makes no changes. For a `POST` that creates a resource or triggers business logic, a timeout does not mean the server failed to process it: you may need a `requestId`/idempotency key if supported by the API, or you must read the state before retrying. For `PATCH`, check the API's specific `etag`/precondition and `updateMask`. Cap retry attempts, add increasing delays and jitter to avoid amplifying outages.

An ordered diagnostic checklist: **URL/version → project/region/resource name → token & scopes → IAM permission → API enabled → quota/policy → request JSON/schema**. This is far more effective than randomly trying Administrator permissions.

## 10. Moving from Read Operations to Resource-Modifying Operations

With `POST`, `PATCH`, and `DELETE`, look beyond HTTP syntax. For instance, a configuration update request may return a **long-running Operation** instead of the completed resource record; scripts must poll the Operation until completion and then re-read the resource to verify.

Before writing automation that modifies GCP, answer:

- **Scope:** are project, region, resource name, and dev/staging/prod environment passed explicitly?
- **Permissions:** which identity runs the command, and is it granted least-privilege permissions?
- **Idempotency:** could re-running create duplicates or unintended overwrites? Does the API provide `requestId`, `etag`, or preconditions?
- **Async state:** does the API return the resource immediately or require waiting for an Operation to finish?
- **Recovery:** have configuration/data been backed up, before/after state recorded, and a valid rollback prepared?
- **Auditing:** do logs identify the actor, change ID, and resource name without exposing access tokens/secrets?

A safe development path is to test `list/get` in a sandbox → specify exact payloads and permissions → verify in a test environment → use tools like Terraform to manage long-term configuration and detect drift where appropriate.

## 11. Choosing the Right Tool for the Situation

| Tool | Best Suited When | Things to Remember |
| --- | --- | --- |
| **REST + curl/PowerShell** | Learning APIs, testing new methods, integrating systems without a client library, debugging raw requests | You handle tokens, retries, pagination, encoding, and response schemas yourself. |
| **APIs Explorer** | Quickly exploring parameters and responses | Useful for controlled testing; avoid accidental writes in real projects. |
| **Google Cloud CLI (gcloud)** | Manual administration and exploration, simple scripting | CLI often combines multiple requests or transforms results; refer to `--format=json` when needed. |
| **Client library** | Production apps calling Google Cloud APIs regularly | Integrates ADC, request models, and per-library/API retry/pagination support; still must understand IAM and quotas. |
| **Terraform / IaC** | Declaring and maintaining long-lived resources, reviewing changes via Git | Uses plan/review and safe state management; does not replace every operational task. |

You do not need to call REST directly just to prove an API exists. A development team might use Terraform to manage infrastructure, client libraries to process messages, `gcloud` for manual checks, and `curl` when needing to debug one exact method.

### APIs Worth Knowing Next

| Need in Module | Suggested REST API to Look Up | Read-Only Starting Methods |
| --- | --- | --- |
| Organization/project | Cloud Resource Manager API | `projects.get`, `projects.list` (check parent/filter per version) |
| Access permissions | Cloud Resource Manager/IAM API | `getIamPolicy` per resource type and permission requirements |
| Compute Engine | Compute Engine API | `instances.list` by project/zone |
| GKE | Kubernetes Engine API | `projects.locations.clusters.list` |
| Cloud Run | Cloud Run Admin API | `projects.locations.services.list/get` |
| Object storage | Cloud Storage JSON API | `buckets.list`, `objects.list` |
| Relational data | Cloud SQL Admin API | `instances.list/get` |
| Service monitoring | Cloud Monitoring API | List metric descriptors and read time series per permissions |

Method names and resource structures change across API versions; the table above is a **starting point for finding documentation**, not URLs to copy verbatim. For example, Compute Engine API uses `zones/ZONE` when listing VMs in a zone, whereas Cloud Run uses `locations/REGION`. You cannot replace "services" with "instances" in the same base URL and expect a valid endpoint.

## 12. Guided Practice

### Exercise A — Explore Without Modifying Resources

1. Pick a sandbox project with permission to view Cloud Run. Note the project ID and region; verify the Cloud Run API is enabled.
2. Open the `projects.locations.services.list` REST reference and identify the method, URL, path parameters, query parameters, OAuth scopes, permissions, and JSON response.
3. Obtain a CLI token with `gcloud auth print-access-token`; issue a `GET` request with `curl` or PowerShell.
4. If the response contains services, take one `name` to try `projects.locations.services.get`; if empty, note that this can still be a valid result.
5. Compare resource names with `gcloud run services list`; if different, verify the project, region, and identity of both commands.
6. Test pagination only when enough resources exist; document the `nextPageToken` rule even if it does not appear in a small environment.

**Completion evidence:** request URL with token redacted; HTTP status; 1–2 relevant JSON fields; explanation of required IAM permissions; note on pagination.

### Exercise B — Read and Resolve a Configuration Error in Sandbox

Suppose a `GET` request returns `403 PERMISSION_DENIED`. Do not guess immediately that the Editor role is needed: first record the active principal, distinguish an unenabled API from missing `run.services.list`, read `error.details` if present, and check quota project usage permissions when prompted. Then describe the **minimal permission change** to propose to the administrator. Do not request broad admin roles just to get past the error.

### Exercise C — Choose the Right API for Three Requests

| Request | Where to Look for the API | What Must Be Verified |
| --- | --- | --- |
| "List VMs in a zone" | Compute Engine REST API, `instances` resource | Project, zone, `instances.list`, and `compute.instances.list`. |
| "Know which Cloud SQL instances exist" | Cloud SQL Admin REST API | `instances.list`, project, IAM, API status. |
| "Check whether a Cloud Run service has public ingress" | Cloud Run REST API v2, `services.get` | `ingress`, invoker/IAM auth config, and network policy; ingress alone does not describe all access permissions. |

Submit a short record for each case using this template:

```text
Need:
API / version / method:
HTTP method + resource URL (no token):
Project / region / zone:
IAM permission + credential type:
JSON field(s) to inspect:
Possible errors/limits:
Equivalent CLI or client library option:
```

## 13. Self-Check and Takeaways

1. Why does `gcloud auth print-access-token` not guarantee the account has `run.services.list` permission?
2. How do the Cloud Run Admin API and a Cloud Run application URL differ in what they manage and which token type they use?
3. When a REST `list` response includes `nextPageToken`, what must you do before concluding the list is complete?
4. Why can the same `403` error require different fixes?
5. When a `POST` request times out, why should you not automatically retry indefinitely?
6. When should you use `curl`, when `gcloud`, and when a client library or Terraform?

**Workflow takeaway:** define the need → find the right REST reference and version → verify project/location, API, and IAM → obtain the appropriate credential → run a controlled `GET` → inspect JSON, status, and pagination → automate only after understanding retries, quotas, idempotency, and permissions.

### Official References

- [Google Cloud APIs overview](https://cloud.google.com/apis/docs/overview)
- [Cloud Run v2 REST reference](https://cloud.google.com/run/docs/reference/rest/v2)
- [Google Cloud authentication overview](https://cloud.google.com/docs/authentication)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Google APIs Discovery Service](https://developers.google.com/discovery/v1/getting_started)
- [Cloud IAM overview](https://cloud.google.com/iam/docs/overview)

API versions, quota limits, and authentication methods can vary by product. In real deployments, cross-check the specific method in official documentation and the active project's configuration.
