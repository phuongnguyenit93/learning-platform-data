# Versioning, Deprecation, and API Catalog Governance on Google Cloud

> **Chapter:** API Gateway and Apigee  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability and cost.

An API already consumed by multiple applications is an **integration contract**, not merely a URL. Renaming a JSON field, removing an endpoint, or changing authentication can simultaneously break mobile apps, partners, and batch jobs. Conversely, keeping every old version forever increases maintenance cost, vulnerabilities, and operational complexity.

This lesson builds a lifecycle governance workflow—**design → release → replace → deprecation notice → sunset/retirement**—using the right tools: **API Gateway** managing API configs/gateways, **Apigee** managing API proxies/API products, and **Apigee API hub** serving as the API catalog. The running example is an **Orders API** migrating from **`/v1/orders`** to **`/v2/orders`**. Dates illustrate policy milestones, not default Google Cloud deadlines.

## Learning Objectives

After this lesson, learners can:

1. Distinguish **public API version**, **OpenAPI `info.version`**, **API Gateway API config**, **Apigee proxy revision**, **Apigee API product**, and **API hub version**.
2. Classify backward-compatible vs. breaking changes and choose an appropriate versioning policy.
3. Describe how **deprecation** differs from **sunset**, and implement notices per **RFC 9745** and **RFC 8594**.
4. Build OpenAPI contracts for v1/v2, migration guides, and contract test suites.
5. Design rollouts/rollbacks on API Gateway or Apigee without confusing configuration revisions with external versions.
6. Build an API catalog entry with owners, consumers, dependencies, deployments, SLA/SLOs, security, lifecycle, and retirement dates.
7. Measure remaining v1 callers, define exit criteria, coordinate Security/SRE/FinOps, and manage change control.
8. Complete the documentation lab, read-only CLI exercises, and scenario drills.

## 1. Four "Version" Layers Not to Confuse

| Concept | Example | Who Sees It? | Meaning |
|---|---|---|---|
| **Public API version** | **`GET /v1/orders/{id}`**, **`/v2/orders/{id}`** | Consumers | Request/response contract and behavior |
| **Specification version** | **OpenAPI `info.version: 1.7.2`** | Developers/CI/catalog | Contract document version; does not automatically change URLs |
| **API Gateway API config** | **`orders-config-20270301`** | Platform operators | Gateway config snapshot created when uploading an API definition |
| **Apigee API proxy revision** | Proxy **`orders`**, revision **17** | Apigee operators | Technical revision number of the proxy bundle, not the public version |
| **API hub API version** | Orders API → **`v1`**, **`v2`** | API catalog users | Metadata entity linking specs, operations, deployments, and lifecycle |
| **Apigee API product** | **`orders-read-v1`**, **`orders-read-v2`** | App/developer portal | Bundle of operations/paths/methods/quotas/access for clients |
| **Backend release** | `checkout-service` image digest | SRE/CI | Running code on Cloud Run/GKE/VMs; not automatically a public API version |

**Key takeaway:** moving from Apigee proxy revision **16** to **17** does not automatically turn **`/v1`** into **`/v2`**. Similarly, creating **`orders-config-20270301`** in API Gateway does not alter public URLs if the spec and gateway routes remain unchanged. The public version belongs to the **contract that clients depend on**.

~~~mermaid
flowchart LR
    C["Clients: mobile, partner, batch"] --> V1["Public /v1/orders"]
    C --> V2["Public /v2/orders"]
    V1 --> G["API Gateway / Apigee"]
    V2 --> G
    G --> B["Cloud Run / GKE backend"]
    SPECS["OpenAPI v1, v2"] -. "Contract docs" .-> G
    HUB["API hub catalog\nversion, owner, lifecycle"] -. "Describes" .-> SPECS
    CICD["CI/CD config/proxy revisions"] -. "Deploys" .-> G
~~~

### 1.1. Roles of the Three Google Cloud Products

- **API Gateway:** manages APIs using **OpenAPI/gRPC definitions**, with immutable configs, regional gateway deployments, and supported auth, quota, and monitoring features. Fits relatively streamlined management needs.
- **Apigee:** an API management platform with **API proxies**, policies, environments, API products, developer apps, analytics, and product-level consumer/API governance.
- **Apigee API hub:** a **catalog and governance layer** for registering APIs from multiple sources, managing API versions/specs/deployments/dependencies/lifecycles, and enabling search. **API hub does not cut off traffic itself, does not automatically enforce Sunset, and does not replace a runtime gateway.**

You can use API hub to track APIs exposed via API Gateway, Apigee, or other platforms. When API Gateway is connected to API hub via the supported integration, API metadata can sync automatically; you must still verify **owners, lifecycle policies, and data freshness**.

## 2. Choosing a Versioning Strategy Based on Contract Changes

A versioning policy must state: **what constitutes a breaking change**, where the version appears, and how long clients have to migrate.

### 2.1. Compatibility Classification

| Change | Usually Compatible? | What to Verify |
|---|---|---|
| Add a new independent endpoint | Yes | Does not cause routing/security conflicts |
| Add an **optional** response field | Usually yes | Clients do not fail on unknown fields; schema is accurate |
| Add an **optional** request field | Usually yes | Default behavior remains unchanged |
| Add an enum value | **Potentially breaking** | Clients using exhaustive switches or strict deserialization |
| Rename/remove a JSON field | **Breaking** | Clients reading/writing the old field |
| Change type **string → number** | **Breaking** | JSON schemas and generated SDKs |
| Change optional parameter to required | **Breaking** | Existing requests become invalid |
| Change currency unit **VND → minor units** | **Breaking** unless field/schema changes | Data semantics change |
| Change status code / error shape | **Potentially breaking** | Retry and client error mapping logic |
| Restrict previously allowed permissions | Potentially breaking, yet required for security | Migration/exceptions and risk review |
| Tighten rate limits / quotas | **Potentially breaking** | Consumer throughput and SLA contracts |
| Change backend while keeping output/semantics | Usually no | Performance, consistency, idempotency |

**Never assume "adding fields is always safe."** Generated Java clients, mobile apps with strict enums, or canonical JSON signing systems can break even when the provider considers a change additive.

### 2.2. How to Expose the Version in the Public Contract

| Approach | Example | Pros | Trade-offs |
|---|---|---|---|
| URL path | **`/v1/orders/{id}`** | Easy to recognize; clear caching/logging/gateway routing | Each version has a different URL |
| Host | **`v2.api.example.com`** | Clear separation of deployments/traffic | More complex DNS/certs and operations |
| Header | **`API-Version: 2`** | Stable URLs | Requires `Vary` caching, client observability, thorough docs |
| Media type | **`Accept: application/vnd.example.v2+json`** | Binds version to representation | Complex tooling/debugging |
| Query parameter | **`?version=2`** | Easy to test | Caching/routing/documentation must stay consistent |

This lesson uses **path major versions**: **`/v1`** and **`/v2`** coexisting. Regardless of approach, the public version must be **consistent** across OpenAPI, SDKs, docs, gateways, telemetry, and the catalog.

### 2.3. Major/Minor/Patch Is a Policy, Not a Gateway Default

Example internal convention:

- **Major** (v1 → v2): incompatible changes.
- **Minor** (1.7 → 1.8): backward-compatible additions.
- **Patch** (1.8.1 → 1.8.2): bug fixes without contract changes.

Use OpenAPI's **`info.version`** to mark published spec versions. API Gateway itself does not enforce SemVer rules to block breaking changes; CI and review processes must enforce them.

## 3. Designing Orders API v1 and v2 Before Changing Runtime

**Hypothetical contract:**

- **v1:** `GET /v1/orders/{orderId}`, response has **`id`**, **`totalAmount`** (in VND), **`status`**.
- **v2:** `GET /v2/orders/{orderId}`, response has **`id`**, **`amount: { value, currency }`**, **`status`**.

Because v1 uses **`totalAmount`** and v2 replaces it with the **`amount`** object, that is a breaking change. Never silently switch v1 responses to v2's shape, as doing so breaks existing clients.

### 3.1. OpenAPI 3.0 Contract for v1 (Documentation, Not Yet a Complete Gateway Deploy Spec)

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.4.0
  description: Version v1 - deprecated per organization policy
servers:
  - url: https://api.example.com
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrderV1
      deprecated: true
      summary: Read order, v1
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                type: object
                required: [id, totalAmount, status]
                properties:
                  id: {type: string}
                  totalAmount:
                    type: integer
                    format: int64
                    description: Total amount, in VND
                  status: {type: string}
        '404':
          description: Order not found
~~~

### 3.2. Contract v2

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 2.0.0
servers:
  - url: https://api.example.com
paths:
  /v2/orders/{orderId}:
    get:
      operationId: getOrderV2
      summary: Read order, v2
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                type: object
                required: [id, amount, status]
                properties:
                  id: {type: string}
                  amount:
                    type: object
                    required: [value, currency]
                    properties:
                      value: {type: integer, format: int64}
                      currency: {type: string, example: VND}
                  status: {type: string}
        '404':
          description: Order not found
~~~

Example response:

~~~json
{
  "id": "ord-1001",
  "amount": {"value": 150000, "currency": "VND"},
  "status": "PAID"
}
~~~

**Distinction:** the **`deprecated: true`** property on an OpenAPI operation communicates documentation status to users and tooling; it **does not block requests, emit a `Sunset` header, or remove the endpoint**. You must implement headers/policies/route removal in the backend or gateway when the milestone arrives.

**Security note:** these two OpenAPI snippets intentionally focus on the contract and **omit security schemes, backend mapping, authentication, and full error schemas**. Never deploy them as public production APIs merely because the schema is valid. The API Gateway deployment example later requires a complete spec and separate backend/auth configuration.

### 3.3. Data Mapping Table

| v1 | v2 | How to Migrate |
|---|---|---|
| `totalAmount: 150000` | `amount.value: 150000` | Update field read path |
| Implicit VND | `amount.currency: "VND"` | Handle currency unit explicitly |
| `/v1/orders/{id}` | `/v2/orders/{id}` | Update URL and client SDK |
| `getOrderV1` | `getOrderV2` | Regenerate SDK or add adapter |
| OpenAPI deprecated | OpenAPI active | Update docs, changelog, and runbooks |

Supporting v1 → v2 can be handled by **parallel backend support** or an Apigee proxy transformation, depending on architecture. Avoid relying on gateway transformations to mask deep behavioral differences long-term, as that increases complexity and latency cost.

## 4. How Deprecation Differs from Sunset

| Status | Meaning for Clients | Provider Action |
|---|---|---|
| **Design** | Not yet in production | Review contract, security, owner |
| **Preview/Beta** | Subject to change under preview terms | Label clearly, limit consumers |
| **Active/GA** | Recommended for use, covered by SLO/support policy | Manage versions, monitor |
| **Deprecated** | Still operational, but **avoid new integrations**; prepare to migrate | Notify, support v2, measure v1 |
| **Sunset reached** | Scheduled end-of-service date reached | Execute approved cutoff decision, return error guidance |
| **Retired** | v1 contract is no longer served | Remove live routes/keys/docs, archive audit records |

**Deprecated does not mean disabled.** A deprecated endpoint can continue returning HTTP 200 normally. **Sunset is the scheduled end-of-service milestone**, yet an HTTP header alone does not shut down an endpoint; operators must execute routing/proxy/backend changes and verify them. **Retired** is the governance state confirming v1 service has ceased.

### 4.1. Illustrative Timeline for Orders API

| Time (UTC) | Event | Expectation |
|---|---|---|
| **02/01/2027** | Publish v2, migration guide, and v1 plan | Consumer owners acknowledge notice |
| **03/01/2027** | v1 enters **Deprecated** | v1 responses include `Deprecation` + `Link`; open dashboard |
| **06/01/2027** | Mid-point checkpoint | Remaining top v1 consumers have migration plans |
| **09/01/2027** | **Scheduled Sunset** | Change board decides cutoff/extension based on metrics |
| **After confirmed cutoff** | Retired | API hub and docs updated; rollback window closed |

These dates are **examples of an organizational policy**, not SLAs or deadlines enforced automatically by API Gateway or Apigee. Real notice periods must reflect partner contracts, mobile app release cycles, industry/legal rules, data retention, and risk level.

### 4.2. HTTP Deprecation, Sunset, and Link Headers

**RFC 9745** defines the **`Deprecation`** header as a *Structured Field Date* using Unix epoch seconds prefixed with **`@`**. **RFC 8594** defines **`Sunset`** in **HTTP-date** format, which differs from Deprecation.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1803859200
Sunset: Wed, 01 Sep 2027 00:00:00 GMT
Link: <https://developer.example.com/orders/migrate-v2>; rel="deprecation"; type="text/html"

{"id":"ord-1001","totalAmount":150000,"status":"PAID"}
~~~

- **`Deprecation: @1803859200`** is **2027-03-01 00:00:00 UTC**.
- **`Sunset`** is **2027-09-01 00:00:00 UTC** in HTTP-date format.
- **`Link`** points to the migration guide with changelog, request/response examples, SDKs, and support schedule; the URL is illustrative.
- **Sunset must never precede Deprecation** in notices for the same resource; keep docs, headers, and catalog aligned.
- Adding headers **does not automatically route requests to v2**, alter response schemas, or reject traffic.

Before 2027-03-01, a provider may send a future-dated `Deprecation` header as an early warning, provided docs stay consistent. When a specific resource advertises Deprecation/Sunset, the default scope is that resource; if the notice applies to all of **`/v1`**, state that scope clearly in docs and emit consistent headers across affected operations.

### 4.3. Java/Spring Boot Example Returning Deprecation Headers

Suppose a Spring Boot application already has an order-reading service:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
public class OrdersV1Controller {

    @GetMapping("/v1/orders/{orderId}")
    public ResponseEntity<Map<String, Object>> getOrder(
            @PathVariable String orderId) {

        // Mock data example, not a real repository/database.
        Map<String, Object> body = Map.of(
                "id", orderId,
                "totalAmount", 150000,
                "status", "PAID"
        );

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("Deprecation", "@1803859200")
                .header("Sunset", "Wed, 01 Sep 2027 00:00:00 GMT")
                .header(
                        HttpHeaders.LINK,
                        "<https://developer.example.com/orders/migrate-v2>"
                        + "; rel=\"deprecation\""
                )
                .body(body);
    }
}
~~~

This example only demonstrates **v1** HTTP headers/schema; production must use **centralized date/version configuration**, have contract tests, and avoid hardcoding data or order IDs. Ensure significant error responses (4xx/5xx) also include appropriate info when required by policy; avoid returning deprecation headers on **`/v2`** if only v1 is deprecated.

**Do not use 301/302 redirects from v1 to v2 as a default solution**: POST clients, authentication, idempotency, response schemas, and cache semantics can differ, causing redirects to drop data or produce unexpected failures.

### 4.4. When Cutoff Day Arrives, What Should the API Return?

There is no single mandatory HTTP status code for every retired API. One policy option:

- After disabling the route, return **410 Gone** with a link to the migration guide if supported by the platform/backend and without leaking unauthorized data.
- For unauthorized requests, **401/403** must still follow auth policy; never disable authentication just to show a migration message.
- On API Gateway/Apigee, how status/body are returned depends on the backend or proxy policy; **it is not an automatic feature of API hub lifecycle status**.
- Continue monitoring requests to v1 to catch unmigrated clients; keep an approved emergency re-enable procedure during the rollback window.

## 5. API Gateway: Updating API Configs Across Release Cycles

**API Gateway has two primary layers:**

- **API config:** created by uploading an OpenAPI/gRPC definition; logical configuration is largely **immutable** (only display name/labels can be updated).
- **Gateway:** a regional deployment resource serving **one API config at a time**; you can update the gateway to point to a new config.

~~~mermaid
flowchart LR
    SPECA["openapi-v1.yaml"] --> CA["API config: orders-config-001"]
    SPECB["openapi-v1-updated.yaml"] --> CB["API config: orders-config-002"]
    CA --> GW["Gateway: orders-gw\nregion X"]
    CB -. "Deploy new config" .-> GW
    GW --> CLIENT["Consumers /v1, /v2\nif the same config includes both"]
~~~

### 5.1. Distinguish Config Rollouts from Versioning

- **`orders-config-001 → 002`** might simply add monitoring or update a backend target **while keeping v1**.
- If a single gateway must serve both **`/v1` and `/v2`**, the API definition **deployed in that config** must declare both paths, or you must design additional gateways/domains/routing above it. You cannot attach **two API configs** simultaneously to **one gateway**.
- During a gateway update, the platform supports non-disruptive config transitions per product design, yet **for a period some requests may still follow the old config**. Keep both configs and the backend compatible during transitions.
- If the same API has gateways in multiple regions, update **each gateway individually** and watch for deployment drift.

### 5.2. Inspect Before Changing (Read-Only)

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
API_ID="orders-api"
GATEWAY_REGION="YOUR_SUPPORTED_GATEWAY_REGION"
GATEWAY_ID="orders-gw"

gcloud auth list
gcloud config list project

gcloud api-gateway apis list \
  --project="$PROJECT_ID"

gcloud api-gateway api-configs list \
  --api="$API_ID" --project="$PROJECT_ID"

gcloud api-gateway gateways list \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID"

gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

Run only when the API exists and you have authorized access. **The region must be in the API Gateway supported locations list**; never assume Gateway supports a region merely because Cloud Run/GKE does. Inspect the gateway's active **`apiConfig`**, update time, traffic, and managed service before intervening.

### 5.3. Example Pipeline Creating a New Config and Updating the Gateway

Assume **`openapi-orders.yaml`** already declares complete API Gateway backend/security settings, passed linting, and was approved by the owner. **Do not use the two conceptual OpenAPI snippets from section 3 directly to expose a public API**, as they lack backend/auth definitions.

~~~bash
# REAL CHANGE — run only in an approved lab project/gateway.
CONFIG_ID="orders-config-20270301"
BACKEND_SA="gateway-backend@$PROJECT_ID.iam.gserviceaccount.com"

gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api="$API_ID" \
  --openapi-spec="openapi-orders.yaml" \
  --backend-auth-service-account="$BACKEND_SA" \
  --project="$PROJECT_ID"

# READ-ONLY — wait for config ACTIVE and verify contract metadata.
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"

# MODIFIES GATEWAY — requires change window and rollback plan.
gcloud api-gateway gateways update "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="$CONFIG_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID"

# READ-ONLY — confirm the gateway uses the new config.
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID" \
  --format="yaml(apiConfig,state,defaultHostname)"
~~~

**Prerequisites:** the deployer holds appropriate IAM permissions to create API configs/update gateways, and the service account is granted backend access. A config **currently referenced by a gateway** generally cannot be deleted until the gateway switches to another config or is deleted. Do not rush to delete old API configs needed for rollback.

### 5.4. Quotas and Older API Configs

API Gateway has **quota metrics/limits scoped at the API level**, not isolated strictly per API config. Changing quota declarations in a new config can affect gateways still running an older config; renaming or removing an unsynchronized metric can cause quota errors on older operations. Before updating, verify **consistent metrics/limits across all active configs**, especially multi-region.

Do not use a config change meant to deprecate v1 as a shortcut to "turn off v1 immediately": consumer contracts and notice timelines must be handled separately. Inspect gateway metrics by **`api_config`, `gateway_id`, `location`, `response_code_class`** and logs to detect out-of-sync rollouts.

## 6. Apigee: Proxy Revisions, Environments, and API Products

Apigee adds a rich **API management** layer for policies and consumer governance. Distinguish three entities:

- **API proxy:** defines **ProxyEndpoint** (client-facing URL/base path/policies) and **TargetEndpoint** (backend routing/policies).
- **Proxy revision:** a sequentially numbered technical configuration snapshot deployed to an environment such as **`test`** or **`prod`**. A revision is **not** public v1/v2.
- **API product:** bundles operations by API proxy, resource paths, HTTP methods, and quotas/scopes/access; developer apps subscribe and receive API credentials/permissions per product.

### 6.1. Two Public Versions and Deployment Revisions

Example where a company chooses two separate proxies:

~~~text
Apigee environment: prod
  API proxy: orders-v1
    BasePath: /v1/orders
    Deployed proxy revision: 12

  API proxy: orders-v2
    BasePath: /v2/orders
    Deployed proxy revision: 4

API products:
  orders-read-v1 -> proxy orders-v1, GET /{orderId}
  orders-read-v2 -> proxy orders-v2, GET /{orderId}
~~~

This is **one design option**—not every Apigee organization is required to create a separate proxy per major version. You can route multiple versions inside one proxy if configured clearly; what matters is making the public contract, base path, and ownership easy to observe. Never deploy two proxies/versions with **conflicting base paths in the same environment group** without inspecting the deployment change report.

### 6.2. Deploy Proxy Revisions Without Arbitrarily Changing Public Paths

In Apigee, when modifying policies/targets of a running proxy, create a **new revision** and deploy it to replace the old one. A deployed revision is read-only per product design; do not edit XML files at runtime expecting the live revision to change.

~~~bash
# ILLUSTRATIVE ONLY — requires a provisioned Apigee organization,
# sufficient deployer IAM, and change approval.
ORG="YOUR_APIGEE_ORG"
ENV="test"
API="orders-v1"
REV="13"

# READ-ONLY before acting.
gcloud apigee apis list --organization="$ORG"
gcloud apigee apis describe "$API" --organization="$ORG"

# REAL CHANGE — run only after revision 13 has been reviewed.
gcloud apigee apis deploy "$REV" \
  --api="$API" \
  --environment="$ENV" \
  --organization="$ORG" \
  --override
~~~

**Note:** across CLI versions, check **`gcloud apigee apis deploy --help`**, and confirm revision **13** actually exists in the organization. The **`--override`** flag replaces an already deployed revision and should be reviewed before deployment. Afterward, verify deployment status, health, and analytics in the target environment.

**Zero-downtime deployment does not replace rollback.** If the new revision introduces a policy/backend bug, you must be able to redeploy the previous revision and verify consumer SLOs. API proxy deployment and API contract versioning are two distinct decisions.

### 6.3. API Products Supporting Version Migration

In Apigee, an **API product** can restrict operations/paths/methods and manage app access. Example:

| Product | Operations | Consumer Policy |
|---|---|---|
| **orders-read-v1** | `GET /v1/orders/{id}` | Disallow new registrations once v1 is Deprecated |
| **orders-read-v2** | `GET /v2/orders/{id}` | Recommended for all new integrations |
| **orders-partner-premium** | Approved GET/POST on v2 | Contractual quotas and scopes |

To execute this:

1. Create the **v2 proxy** with a non-conflicting base path and deploy to `test`.
2. Create the **v2 API product** covering the exact proxy/operations and authorization policies.
3. Publish the v2 product in the portal/docs, registering developer apps or granting access to existing apps per process.
4. Track **traffic by app/product/version** and reach out to consumers.
5. Block **new subscriptions/approvals on v1** if policy dictates, while continuing to honor existing grants during the migration window.
6. When sunset criteria are met, revoke/undeploy v1 **under change approval**—being careful not to remove v2 accidentally.

**Important:** declaring a quota on an API product **does not automatically enforce it**; the Apigee proxy needs corresponding Quota/VerifyAPIKey/OAuth policies properly configured in its flows. Nor is an API key proof of end-user identity; API keys typically identify the consuming application and must be paired with proper authn/authz.

### 6.4. Sunset Behavior Does Not Happen Automatically

To make v1 return **`Deprecation`** and **`Sunset`** headers, you can:

- Emit them directly from the backend as in the Spring Boot example.
- Use an Apigee **`AssignMessage` policy** or configured/tested response flow to add headers.
- Document schedules and migration links in the developer portal/docs.

At retirement, you can deploy a controlled policy returning **410 Gone** or undeploy/stop routing the endpoint, depending on policy. Maintain **auth, logging, request metrics, and rollback readiness**; changing an API product or API hub lifecycle state to Deprecated does not block live traffic by itself.

## 7. API Hub: Centralized Catalog for Governing Many APIs

An organization's biggest challenge is often not "how many routes exist," but **not knowing owners, consumers, deployed contracts, and end-of-support dates**. API hub provides an object model of **API → versions → specifications/operations → deployments/dependencies**, searchable in one catalog.

~~~mermaid
flowchart TD
    A["API: Orders"] --> V1["Version v1\nLifecycle: Deprecated"]
    A --> V2["Version v2\nLifecycle: Active"]
    V1 --> S1["OpenAPI v1\noperations"]
    V2 --> S2["OpenAPI v2\noperations"]
    V1 --> D1["Deployment: API Gateway/Apigee prod"]
    V2 --> D2["Deployment: API Gateway/Apigee prod"]
    V1 --> OWNER["Owner / contact / migration guide"]
    V2 --> OWNER
    C["Consumer & dependency records"] -. "Track risk" .-> A
~~~

### 7.1. Minimum Metadata per API/Version

| Field | Orders API Example | Why Is It Mandatory for Governance? |
|---|---|---|
| API ID / Display name | `orders` | Catalog identifier |
| API owner / technical contact | `commerce-platform/on-call` | Clear accountability |
| Business domain / classification | `Checkout / internal partner` | Access control, compliance |
| Public version | `v1`, `v2` | Distinguishes contracts |
| Lifecycle | `Deprecated` / `Active` | Shows current state |
| Spec URL, checksum/version | OpenAPI v1.4.0 / v2.0.0 | Source of truth to diff breaking changes |
| Operations | `GET order`; `POST order`... | Search and impact analysis |
| Deployment environment/endpoint | test/prod URL, region, gateway/proxy | Know which version runs where |
| Consumer owners/dependencies | `mobile`, `partner-A`, `batch-B` | Assess blast radius before retiring v1 |
| Authentication/authorization | OAuth/OIDC, API key policy | Never publish APIs with unclear protection |
| SLO/SLA and support tier | p95 latency, availability | Control release risk |
| Deprecation/sunset dates | 2027-03-01 and 2027-09-01 UTC | Consistent schedule and notices |
| Migration guide/replacement | `/v2/orders`; doc link | Clear upgrade path for clients |
| Data sensitivity/retention | order metadata, PII classification | Data protection and auditing |
| Cost center / business value | `commerce` | Allocate maintenance costs |
| Approval/change record | `CAB-XXXX` | Audit trail for lifecycle transitions |

**Distinguish data sources:** API hub supports Lifecycle/version/deployment/spec/dependency attributes, yet not every field in this table is built in or synced automatically. Consumer owners, SLOs, sunset dates, risk scores, and approvals may require **custom attributes/links/governance processes outside API hub**. Never assume creating an API hub version configures Gateway/Apigee runtimes.

### 7.2. Working in API Hub (Authorized Read and Governance Practice)

In **Google Cloud Console → Apigee → API hub** with a provisioned API hub instance:

1. Locate **Orders API** or register a new API with catalog editor permissions.
2. Add **`v1`** and **`v2`** under the same API resource.
3. Attach the corresponding OpenAPI specs and verify API hub parses operations.
4. Attach deployments (endpoint, environment, platform) for each version.
5. Set the lifecycle attribute to **Deprecated** for v1 and **Active** for v2; add migration URL/dates via attributes/docs per organizational governance.
6. Link dependencies/owners and use search/filters to list versions approaching sunset.
7. Verify the catalog matches runtime reality: which endpoints and proxies/gateways actually serve v1 and v2 right now.

**API hub can auto-register Apigee proxies and integrate with API Gateway** via supported connectors, yet synced metadata does not automatically include complete owners, policies, or client migration details. Those fields require API team review and sync with some delay; always verify live runtime state before cutting off traffic.

### 7.3. Sample Catalog Record (Internal Convention, Not an API Hub Import Schema)

~~~yaml
apiId: orders
version: v1
owner: commerce-platform
lifecycle: deprecated
specRef: docs/orders/openapi-v1.yaml
deployments:
  - environment: production
    gateway: orders-gw
    basePath: /v1/orders
deprecationAt: "2027-03-01T00:00:00Z"
sunsetAt: "2027-09-01T00:00:00Z"
replacement: /v2/orders
migrationGuide: https://developer.example.com/orders/migrate-v2
consumers:
  - mobile-checkout
  - partner-a
approval: CAB-EXAMPLE
~~~

This record is for discussing an **organization's governance schema**; do not pass it directly to **`gcloud`** or the API hub REST API as a native import payload. When automating, map each field to the appropriate API hub resources/attributes and store external links where the product lacks a built-in field.

## 8. Consumer Notification and Migration Workflow

A successful deprecation plan must answer: **who is calling v1, who owns the decision to switch, which version replaces it, what is the cutoff schedule, and what proves completion**.

### 8.1. Phased Playbook

| Phase | Actions Required | Evidence |
|---|---|---|
| **Inventory** | Identify all v1 clients, app IDs, key/token owners, scheduled jobs | Traffic dashboards + dependency list |
| **Design v2** | Contract diff, migration examples, SDKs, changelog | Reviews and spec version |
| **Announce** | Portal, email/partner notices, OpenAPI `deprecated`, HTTP headers | Sent notices and recipients |
| **Migration** | Client canary, contract tests, compatibility window | Falling % of v1 usage; client sign-off |
| **Final warning** | Contact unmigrated consumers, review exceptions | Approved waivers/extensions |
| **Sunset decision** | Check SLOs, traffic, compliance, business approval | Change record and rollback window |
| **Retire** | Disable routes/access within scope, monitor errors/legacy traffic | Updated runtime; API hub + docs synced |

**Do not shut down v1 merely because the date arrived** if a critical consumer contract prohibits it: use an exception/extension process with an owner and expiry date, without letting exceptions turn into indefinite unscheduled support.

### 8.2. Scenario: Consumers Without Clear Identity

Request logs exist, yet you cannot tell who is calling v1 because the API shares a single API key or lacks client identifiers. This is a **governance gap to fix before sunset**:

- Migrate to credentials distinguishing developer apps or service accounts per policy.
- Attach consumer identity to logs/analytics once privacy requirements are satisfied.
- Collect SDK version/`User-Agent` appropriately without treating `User-Agent` as trusted identity.
- Coordinate with mobile app/partner owners and inventory infrequent batch jobs.
- Never log raw `Authorization` headers, API keys, PII, or full request bodies just to identify callers.

In Apigee, developer app and API product dimensions identify consumers when the proxy enforces the corresponding verification policies. On API Gateway, metrics and logs provide gateway/config/response dimensions, requiring correlation with application identity or configured API key/consumer metadata—do not assume a single log column always identifies every caller.

### 8.3. Sample Consumer Notice Template

~~~text
Subject: Orders API v1 - Deprecation and Migration Plan to v2

Orders API v1 (/v1/orders) will transition to Deprecated starting
2027-03-01 00:00 UTC. Scheduled end-of-support (Sunset): 2027-09-01 00:00 UTC.

Replacement version: /v2/orders
Key breaking difference: totalAmount -> amount.value + amount.currency
Contract and migration guide: [Organization's real URL]
Next steps:
1. Request v2 permissions/credentials if required.
2. Update SDKs, URLs, and JSON models, and test in staging.
3. Report your migration completion date to the API owner before the deadline.
4. Support contact: [official channel]

If you cannot migrate before the deadline, submit an exception request
with your consumer ID, traffic volume, justification, and target completion date.
~~~

This template **does not replace contractual notices**. A public API with SLAs/terms requires wording, timelines, and communication channels approved by Legal/Support/Partner Management.

## 9. Measuring v1 Usage and Setting "Exit Criteria" Before Sunset

The decision to retire an API must rely on **per-public-version metrics**, not merely whether a gateway or proxy has traffic. One gateway config can serve **both v1 and v2**; total requests per API config are insufficient to prove v1 has zero users.

### 9.1. Metrics to Monitor

| Metric | Meaning for Retirement Decisions |
|---|---|
| **Requests by `/v1` and `/v2`** | Actual consumption of each public version |
| **Active consumers per version** | How many apps/partners/jobs still call v1 |
| **Last-seen timestamp** | Low-frequency consumers that may be critical, e.g., monthly batch jobs |
| **Error rate / p95 latency** | Ensure migration does not degrade SLOs |
| **401/403/429/5xx** | Separate credential, rate-limit, and backend errors |
| **Deprecated operations** | An API might sunset only one endpoint rather than the entire version |
| **Top consumers and SLA tiers** | Prioritize support and exception handling |
| **v1 traffic after notice** | Verify communication effectiveness |
| **Cloud Billing by SKU** | Cost of running two versions in parallel |

In **API Gateway**, Cloud Monitoring provides **`API Gateway → Proxy → Request Count`**, filterable by **`gateway_id`, `api_config`, `location`, `response_code_class`**. To separate **`/v1` vs. `/v2`** usage, combine request logs/route data or properly instrumented backend metrics.

In **Apigee**, analytics provides proxy/product/developer app insights per configured policies; without API key/app verification, do not claim you have a complete list of consumer owners. Logs/analytics and catalog data must protect PII and keys.

### 9.2. Reference Cloud Logging Query

This is a **read-only filter for Logs Explorer**, not a `gcloud` command. Substitute your project/location/gateway and adapt to your actual request log schema:

~~~text
resource.type="apigateway.googleapis.com/Gateway"
resource.labels.gateway_id="orders-gw"
resource.labels.location="YOUR_SUPPORTED_GATEWAY_REGION"
log_name="projects/YOUR_PROJECT_ID/logs/apigateway.googleapis.com%2Frequests"
~~~

After filtering, verify **which log fields carry path/operation/consumer**, then build dashboards/metrics for `/v1` and `/v2`. Never guess JSON field names from a tutorial for a different product version and silently drop unmatched requests. If logs lack attribution, add **structured logging in the backend** or Apigee analytics policies within privacy rules.

### 9.3. Exit Criteria for Retiring v1 (Illustrative Policy)

A change board may require all of these conditions simultaneously:

1. **100% of contracted/critical partners** confirm migration, or hold a valid exception.
2. **Zero known active v1 clients** for at least 30 days, spanning monthly batch cycles.
3. v1 request volume is under **0.1% of total Orders API requests** over 14 days—**never using this ratio as a substitute for condition 1**.
4. v2 meets SLOs, security reviews, and compatibility tests.
5. Docs, headers, and migration guide are published; final notice has been acknowledged.
6. Rollback plan, feature flags/routing, and post-cutoff alert dashboards are ready.
7. Products, proxies/gateways, API hub metadata, and support teams reflect the same final state.

**These thresholds are illustrative choices**, not rules imposed by API Gateway/Apigee. A partner sending 1 request/month can carry higher business impact than millions of internal calls; evaluate **impact**, not just traffic percentage.

### 9.4. Do Not Forget Long-Tail Consumers

Commonly overlooked clients: un-updated mobile apps, browser extensions, month-end batch jobs, webhook receivers, SDKs embedded in third-party software, DR standby environments, and cron jobs that run only during incidents. For unidentifiable consumers, record an approved **risk acceptance** decision.

## 10. Integrating Contract Governance into Git and CI/CD

A catalog with clean metadata still cannot prevent breaking deployments if a **change gate** is missing. A strong control point is OpenAPI specs in Git, automatically checked before generating gateway configs or Apigee proxy revisions.

### 10.1. Recommended Pipeline

~~~mermaid
flowchart TD
    PR["Pull request: OpenAPI + implementation"] --> LINT["Lint OpenAPI and policies"]
    LINT --> DIFF["Diff against latest public release"]
    DIFF --> BREAK{"Breaking change?"}
    BREAK -- "Yes" --> NEW["Require new major version or waiver"]
    BREAK -- "No" --> TEST["Contract & security tests"]
    NEW --> REVIEW["Owner + security/consumer review"]
    REVIEW --> TEST
    TEST --> STAGE["Deploy stage: gateway config/proxy revision"]
    STAGE --> SMOKE["Smoke & canary; measure errors/latency"]
    SMOKE --> PROD["Promote to prod per change approval"]
    PROD --> CATALOG["Update API hub/docs/deprecation"]
~~~

**Mandatory checks to include:**

- YAML/OpenAPI parses and lints cleanly.
- Diff request/response schemas, parameters, status/error codes, and security requirements against the live public version.
- Block breaking changes on **v1** unless granted a time-bounded waiver with a consumer migration plan.
- Verify implementation adheres to spec: contract tests and smoke tests for both v1 and v2.
- Verify authn/authz, rate limits, input validation, max payload sizes, and backend errors.
- Verify metadata: owner, public version, release notes, spec checksum, deployment URL.
- Ensure v1 remains operational throughout the migration window when deploying v2.
- Reconcile gateway/Apigee deployment status, version, and API hub/catalog after promotion.

### 10.2. Reading an OpenAPI Diff

Example diff report:

~~~text
GET /v1/orders/{orderId}
- response.totalAmount: integer, required
+ response.amount: object, required

Classification: BREAKING for consumers of v1
Decision:
  Reject change on /v1
  Introduce /v2/orders/{orderId}
  Keep v1 response schema until approved sunset
~~~

Automated diff tools can miss **business semantics**: changing currency units from VND to cents while keeping type `integer` may **go undetected by static tools**. Combine automated diffs with API owner reviews and consumer contract tests.

### 10.3. Sample Pull Request Review Checklist

~~~text
API_ID / PUBLIC_VERSION:
SPEC_COMMIT / SPEC_CHECKSUM:
CHANGE_TYPE: additive / breaking / security / behavioral
AFFECTED_OPERATIONS:
BREAKING_DIFF_REVIEW:
OWNER_APPROVAL:
SECURITY_REVIEW:
CONSUMER_IMPACT / NOTIFICATION:
GATEWAY_CONFIG_ID / APIGEE_PROXY_REVISION:
STAGING_URL / CONTRACT_TEST_RESULT:
PROD_ROLLOUT_WINDOW:
DEPRECATION_DATE / SUNSET_DATE (IF ANY):
API_HUB_METADATA_UPDATED:
MONITORING / ROLLBACK:
~~~

Never substitute a "green" CI check for human sign-off when consumer contracts or compliance require explicit approval.

## 11. Security, Permissions, and Cost Across the API Lifecycle

### 11.1. Responsibility Boundaries

| Component | Permissions and Limits |
|---|---|
| **API Gateway** | Who creates configs/updates gateways, backend service account, IAM, and API key/JWT per spec |
| **Apigee** | Who edits/deploys proxy revisions, policies, products, developer apps, and analytics |
| **API hub** | Who views/edits catalog/versions/lifecycle/specs/deployments |
| **Cloud Run/GKE backend** | Runtime identity, IAM, database authorization, VPC access |
| **Consumer** | API keys/OAuth credentials, quotas/scopes, and contractual permissions |

**Never grant platform deploy rights to someone who only needs to update catalog metadata.** Likewise, do not grant API hub Editor assuming it changes production runtimes or IAM "automatically propagates to the gateway": each system has its own boundary.

### 11.2. When Deprecating an API Handling Sensitive Data

- Never log raw API keys, JWTs, `Authorization` headers, account IDs, or order payloads.
- When tracking consumers, use **app identity** or protected principals; use pseudonymous identifiers where feasible.
- Honor retention/privacy policies for API logs, telemetry, and consumer registries.
- An older v1 with a critical vulnerability may require an **emergency security change** ahead of sunset, backed by risk review, notice, and mitigation.
- Never redirect requests carrying credentials or request bodies to a new endpoint without evaluating auth/HTTPS/redirect semantics.
- Ensure HTTP `Deprecation`/`Link` headers never expose internal details on public endpoints.

### 11.3. Optimizing Cost Without Reckless Cuts

Running v1 and v2 side by side can increase costs:

- API Gateway requests and gateways deployed across multiple regions.
- Apigee capacity/proxy deployment units, policies, and analytics per pricing/entitlements.
- Cloud Run/GKE/DB compute, caching, and network traffic.
- Logging, trace retention, dashboards, and API hub/governance.
- Support staffing, security patches, and test maintenance for two contracts.

Do not assume deleting an **API Gateway config** reduces the running gateway's cost: configs and gateways are separate resources, and real billing depends on provisioned SKUs/resources and request volume. On Apigee, keeping a v1 proxy deployed can consume **proxy deployment units** per environment/instance. Measure actual spend in **Cloud Billing** and entitlements rather than counting versions in API hub.

At sunset, retire only **gateway/proxy/SDK/spec deployments with no remaining consumers** after verifying owners, SLOs, compliance, and rollback readiness. Never delete logs or contract archives still within mandatory retention windows.

## 12. Lab: Managing v1/v2 with Specs, Gateway Configs, and Catalogs

The lab has two tiers: **A. Documentation-only practice without creating cloud resources**, and **B. Optional deployment in an approved project**. In production, API Gateway/Apigee and API hub incur costs, IAM, quotas, and provisioning prerequisites; never spin up resources just for a quick test without organizational approval.

### 12.1. Lab A — Contract-Only, Can Be Done Offline

Prepare two OpenAPI files (v1 and v2) from section 3 in a **separate learner practice folder**. Then fill out the matrix:

| Test | v1 | v2 | PASS When |
|---|---|---|---|
| `GET` order 200 | Has `totalAmount` | Has `amount.value`/`currency` | Schema matches spec |
| Non-existent ID | 404 | 404 | Consistent error handling |
| Missing auth | 401/403 per policy | 401/403 | No data exposed |
| Total amount | 150000 VND | `value=150000`, `currency=VND` | No unit drift |
| Deprecated marker | `true` | `false`/undeclared | Docs clear |
| Deprecation response header | Present on v1 per policy date | Not applicable | Valid RFC 9745 format |
| Sunset header | UTC date per policy | Not applicable | Valid RFC 8594 format |

Discussion: if the v1 response drops **`totalAmount`** without changing the public path, which contract test fails? If v2 introduces a new response while the database schema changed, which checks ensure v1 continues working?

### 12.2. Lab B — OpenAPI 2.0 for API Gateway (Only in an Authorized Lab Environment)

The example below is an **illustrative config with core structure** for a gateway calling an existing Cloud Run backend. The backend **must implement both `/v1` and `/v2`**, enforce proper IAM, and manage API keys securely. Replace with real URLs; never deploy with placeholder URLs.

~~~yaml
swagger: "2.0"
info:
  title: Orders API Lab
  description: API Gateway demo, v1 deprecated and v2 active
  version: "2.0.0"
schemes:
  - https
produces:
  - application/json
x-google-allow: configured
x-google-backend:
  address: https://REPLACE_WITH_CLOUD_RUN_SERVICE_URL
  path_translation: APPEND_PATH_TO_ADDRESS
securityDefinitions:
  api_key:
    type: apiKey
    name: key
    in: query
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrderV1
      deprecated: true
      security:
        - api_key: []
      parameters:
        - name: orderId
          in: path
          required: true
          type: string
      responses:
        "200":
          description: Order v1
          schema:
            type: object
            required: [id, totalAmount, status]
            properties:
              id: {type: string}
              totalAmount: {type: integer, format: int64}
              status: {type: string}
        "404":
          description: Not found
  /v2/orders/{orderId}:
    get:
      operationId: getOrderV2
      security:
        - api_key: []
      parameters:
        - name: orderId
          in: path
          required: true
          type: string
      responses:
        "200":
          description: Order v2
          schema:
            type: object
            required: [id, amount, status]
            properties:
              id: {type: string}
              amount:
                type: object
                required: [value, currency]
                properties:
                  value: {type: integer, format: int64}
                  currency: {type: string}
              status: {type: string}
        "404":
          description: Not found
~~~

Save as **`openapi-orders.yaml`** inside the **learner's lab folder**, not in the Markdown/YAML knowledge repository. Confirm before deploying:

- The Cloud Run backend is live, handles both routes/response schemas, and requires proper IAM.
- **`x-google-backend.address`** is a real HTTPS URL with no unintended trailing path; **`APPEND_PATH_TO_ADDRESS`** preserves the public request path when proxying to the backend.
- **Backend authentication** uses the API Gateway service account, and Cloud Run authorizes that principal.
- An API key requirement means the gateway identifies the consumer project/quota; **an API key does not replace end-user authentication** when endpoints return order data. Add OAuth/JWT/application authorization as required.
- The API Gateway managed service is enabled for the consumer/keys project per workflow; `securityDefinitions` alone is not enough.
- This OpenAPI 2.0 document is an educational example; verify current OpenAPI extension limits and Google Cloud docs at execution time.

After creating the new config from section 5 (if authorized), verify:

~~~bash
# READ-ONLY.
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"

gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID"

# Backend/gateway URLs and API keys must come from real resources.
# Never print tokens/keys into logs or lab reports.
~~~

Test HTTP from an **authorized** client:

~~~bash
# SEND REQUESTS ONLY; do not create or delete cloud resources.
# Replace URL and auth per actual security policy.
curl -i "https://REAL_GATEWAY_HOST/v1/orders/ord-1001"
curl -i "https://REAL_GATEWAY_HOST/v2/orders/ord-1001"
~~~

Because the spec requires an API key, requests without a key will be rejected—which is expected. Never paste logs containing the **`key`** query parameter into study reports. Verify **`/v1`** includes `Deprecation`/`Sunset` headers from the backend/proxy if implemented, since OpenAPI **`deprecated: true`** does not inject those headers automatically.

### 12.3. Lab C — Inventory an Existing API in API Hub

If your organization has API hub provisioned and grants view access:

1. Find an API owned by your team.
2. Identify the owner and registered versions.
3. Open each version's spec and compare operations.
4. Check test/prod deployments, platform, endpoints, and lifecycle state.
5. Record consumers/dependencies from catalog/analytics/owners where available.
6. Cross-check a **Deprecated** version against live logs/traffic; if still active, open a migration ticket.
7. Never alter lifecycle status or cut traffic when tasked solely with inventory.

Output a **portfolio table** of 3–5 APIs listing owner, version, lifecycle, last deployment, deprecation/sunset dates, consumers, and gaps. If a field is missing, record **`UNKNOWN`** rather than guessing.

## 13. Production Sunset and Rollback Runbook

### 13.1. Day Before Cutoff

- Freeze breaking changes on v1, accepting only reviewed security fixes.
- Audit traffic/callers across a sufficient cycle, confirming periodic batch jobs.
- Confirm v2 meets SLOs and passes client contract tests with zero migration blockers.
- Verify v2 API product credentials, developer apps, and backend IAM.
- Capture a deployment config snapshot: **API Gateway config ID** or **Apigee proxy revision**, plus backend release/digest and policies.
- Publish the "final reminder" with UTC date/time, support channel, and approved exceptions.
- Create a change record with **go/no-go criteria**, rollback owner, and recovery deadline.

### 13.2. Executing the Cutoff

~~~mermaid
flowchart TD
    READY["Go/no-go approved"] --> BASE["Snapshot logs, traffic, configs"]
    BASE --> CHANGE["Disable /v1 within exact scope"]
    CHANGE --> TEST["Smoke /v2 + auth + 404/410 /v1"]
    TEST --> OK{"SLOs / errors / consumer impact acceptable?"}
    OK -- "No" --> ROLL["Roll back config/revision/route"]
    OK -- "Yes" --> WATCH["Observe 4xx, 5xx, support tickets"]
    WATCH --> UPDATE["Update API hub, docs, and records"]
~~~

**Platform-specific order:**

- **API Gateway:** create a new config containing post-cutoff routes/policies, update **gateway(s)**, and monitor. Retain the previous config for rollback while still valid. Never delete an old config while any gateway still references it.
- **Apigee:** deploy a new proxy revision or update API products/policies per plan. Avoid deleting shared credentials still used by v2. If returning 410 Gone, implement verified policy/backend behavior.
- **API hub:** update lifecycle to **Retired** and update deployment metadata **after the runtime actually changes**; API hub does not execute the cutoff.

### 13.3. Post-Cutoff

Monitor v1 request rates, 4xx/5xx sources, client complaints, batch impacts, on-call pages, and recovery readiness. Record **exactly which version, path, and region** were disabled; a gateway in another region still running the old config means retirement is incomplete.

Do not delete all v1 logs/docs immediately: keep them for auditing, troubleshooting, and retention compliance. You can keep the **v1 spec and migration guide archived** in the catalog even after the endpoint stops serving.

## 14. Case Study: Orders API in an E-Commerce System

### 14.1. Context

Orders API is served via **API Gateway** to a Java service on Cloud Run. Mobile apps and three partners call **`/v1/orders`**. One partner runs reconciliation only on the last day of each month. The company wants to standardize money representation as an object with currency in **v2** and needs an API catalog covering 100+ APIs.

**Plan:**

1. Keep v1 running while releasing v2 under a separate contract.
2. Register both in API hub with owners, specs, and deployments.
3. Publish Deprecation/Sunset milestones via docs, portal, and v1 headers.
4. Issue v2 credentials/products if using Apigee API products.
5. Collect per-client metrics, **not just aggregate traffic**.
6. Rehearse cutoff in staging, then production within a change window.
7. Move v1 to Retired only after runtime stops and zero approved exceptions remain.

### 14.2. Hypothetical Incident

In August 2027, dashboards show only 0.05% v1 traffic, so the team plans immediate removal. However, an insurance partner calls the API once at month-end for payment reconciliation—low request count, high business impact. API hub listed an owner but had not recorded that consumer dependency.

**Mistake:** using a raw traffic percentage threshold instead of risk analysis. **Remediation:** contact the partner, complete v2 integration tests, add the dependency/owner to the catalog, and grant a time-boxed exception until the partner migrates. Only then execute sunset.

### 14.3. Success Criteria

- Both v1 and v2 return valid schemas; v1 never breaks during the migration window.
- Critical consumers have verified evidence of migrating to v2.
- API hub accurately reflects versions, deployments, owners, and lifecycle states.
- No v2 API products/keys are accidentally revoked while closing v1.
- p95 latency, 5xx, auth errors, and partner support tickets remain stable.
- v1 support/infrastructure costs drop post-retirement while maintaining audit/retention compliance.

## 15. Practice Exercises and Answers

### 15.1. Exercise A — Evaluating Breaking Changes

Given v1:

~~~json
{"id":"ord-1001","totalAmount":150000,"status":"PAID"}
~~~

The Java team proposes four changes:

1. Add an optional **`createdAt`** response field.
2. Replace **`totalAmount`** with **`amount: {value, currency}`**.
3. Change **`status="PAID"`** to **`status="SETTLED"`** even though the schema stays `string`.
4. Require a new **`locale`** query parameter on every request.

**Question:** which changes are likely breaking and require a new version? Are there cases an OpenAPI diff tool might miss?

**Suggested Answer:** (2) breaking due to schema change; (4) breaking due to adding a required parameter; (3) potentially breaking semantically/for client enums even without a type change; (1) usually compatible, though test strict clients. In case (3), a plain `string` schema type can prevent static diff tools from catching the semantic change.

### 15.2. Exercise B — Reading Three Version Layers Correctly

Current system state:

~~~text
Public API: /v1/orders
OpenAPI info.version: 1.4.2
API Gateway API config: orders-config-202702
Apigee proxy: orders-v1, revision 19
API hub: Orders API, version v1, Lifecycle Deprecated
Backend: checkout-api revision 20270212
~~~

**Questions:**

1. Does creating API Gateway config **`orders-config-202703`** force clients to switch to **`/v2`**?
2. Does Apigee proxy revision 20 mean public API version 20?
3. Does changing API hub lifecycle for v1 to `Retired` automatically stop requests?
4. Does rolling the backend from revision 20270212 to 20270301 require changing the public version?

**Answer:** all four are **not automatic**. Whether the public contract changes depends on the spec, behavior, routing, and compatibility policy; runtime configs, proxy revisions, and catalog metadata are separate layers.

### 15.3. Exercise C — Calculating Traffic Share and Sunset Decision

Over 14 days:

| Consumer | v1 Requests | Critical? |
|---|---:|---|
| Legacy mobile | 3,000 | No |
| Reconciliation partner | 20 | **Yes** |
| Internal batch | 500 | No |
| Total API v1 + v2 | 5,000,000 | — |

**Calculation:** v1 accounts for **3,520 / 5,000,000 = 0.0704%** of traffic.

**Question:** it is below the 0.1% threshold; should we sunset v1 immediately?

**Answer:** **criteria not met**, because a critical partner still calls v1; require migration/sign-off or a time-boxed exception. Request percentage is an indicator, not a replacement for impact and contractual assessment.

### 15.4. Exercise D — Diagnosing Post-API Gateway Rollout

A gateway just switched from config A to config B. For several minutes, some requests still follow config A, and some requests report quota errors.

**Analyze:**

- Which update behavior explains this observation?
- Why does changing a quota metric definition in config B pose a risk to config A?
- Which dimensions should you inspect in metrics/logs?
- If SLOs are breached, how do you roll back and what must you verify?

**Suggested Answer:** the gateway may serve both old and new configs during transition; quota declarations apply at the API level, so older configs can fail if metrics are renamed/removed. Inspect gateway ID, region, `api_config`, response codes/errors, and backend logs, then update the gateway back to the previously verified config; confirm quota policies remain compatible and run smoke tests.

### 15.5. Exercise E — Write a 90-Day Deprecation Plan

Pick a hypothetical API with three consumers, one of which is a monthly batch job. Write a one-page plan covering:

- v1/v2 contracts and breaking diff.
- Announcement, deprecation, and sunset dates (UTC), consumer owners, and migrations.
- RFC 9745/8594 headers, migration guide URL, and API hub catalog entry.
- SLO/traffic dashboards and how to detect infrequent callers.
- Go/no-go criteria, exceptions/extensions, and rollback.
- Evidence required for the Retired state.

**Grading criteria:** consistent timeline dates, no confusion among spec version / proxy revision / public version, no assumption that API hub shuts down endpoints automatically, critical consumer sign-off, zero leaked credentials/PII, and post-cutoff monitoring.

### 15.6. Inventory and Acceptance Checklist Template

~~~text
API_ID / BUSINESS_OWNER / TECHNICAL_OWNER:
PUBLIC_VERSION(S) / OPENAPI_SPEC_VERSION(S):
BREAKING_CHANGE_REVIEW:
API_GATEWAY_API_CONFIG(S) / REGION / GATEWAY(S):
APIGEE_PROXY / REVISION / ENVIRONMENT / API_PRODUCT:
API_HUB_API / VERSION / LIFECYCLE / DEPLOYMENT:
AUTH / QUOTA / BACKEND_IDENTITY:
DEPRECATION_AT / SUNSET_AT / TIMEZONE:
HEADER_DEPRECATION / HEADER_SUNSET / LINK:
MIGRATION_GUIDE / SDK / CHANGELOG:
KNOWN_CONSUMERS / LAST_SEEN / CRITICAL_SIGN_OFF:
V1_REQUESTS / V2_REQUESTS / 4XX / 5XX / P95:
SLO_AND_COST_IMPACT:
GO_NO_GO / EXCEPTIONS / ROLLBACK:
ACTUAL_RETIREMENT_DATE / REGION_COVERAGE:
DOCS_CATALOG_UPDATED / CHANGE_TICKET / OWNER:
OPEN_ISSUES:
~~~

Never mark **PASS** based solely on design docs or without production visibility. Record **`UNKNOWN`**, an owner, and the next verification step. Never include access tokens, API keys, or order details in reports.

## 16. References and Takeaways

**Google Cloud — API Gateway:**

- [Deployment model and API configs](https://docs.cloud.google.com/api-gateway/docs/deployment-model)
- [Create/update API config](https://docs.cloud.google.com/api-gateway/docs/creating-api-config)
- [Deploy/update gateway](https://docs.cloud.google.com/api-gateway/docs/deploying-api)
- [OpenAPI versions supported](https://docs.cloud.google.com/api-gateway/docs/openapi-overview)
- [OpenAPI 2.0 extensions and backend routing](https://docs.cloud.google.com/api-gateway/docs/oasv2-extensions)
- [Use API keys](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys)
- [Monitor API Gateway metrics/logs](https://docs.cloud.google.com/api-gateway/docs/monitoring)
- [Connect API Gateway with API hub](https://docs.cloud.google.com/api-gateway/docs/api-hub-overview)

**Google Cloud — Apigee and API hub:**

- [Understanding API proxies, revisions and policies](https://docs.cloud.google.com/apigee/docs/api-platform/fundamentals/understanding-apis-and-api-proxies)
- [Deploy API proxy revisions](https://docs.cloud.google.com/apigee/docs/api-platform/deploy/ui-deploy-new)
- [API products](https://docs.cloud.google.com/apigee/docs/api-platform/publish/what-api-product)
- [Managing API products](https://docs.cloud.google.com/apigee/docs/api-platform/publish/create-api-products)
- [What is Apigee API hub?](https://docs.cloud.google.com/apigee/docs/apihub/what-is-api-hub/)
- [API hub versions overview](https://docs.cloud.google.com/apigee/docs/apihub/versions-intro)
- [Manage API hub versions](https://docs.cloud.google.com/apigee/docs/apihub/manage-versions)
- [Manage API hub lifecycle attributes](https://docs.cloud.google.com/apigee/docs/apihub/manage-attributes)

**HTTP and OpenAPI Standards:**

- [RFC 9745 — Deprecation HTTP Response Header](https://www.rfc-editor.org/rfc/rfc9745)
- [RFC 8594 — Sunset HTTP Header](https://www.rfc-editor.org/rfc/rfc8594)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)

**Key takeaway:** **Versioning** protects client contracts; **deprecation** signals the need to migrate without automatically stopping service; **sunset/retirement** requires change approval, telemetry, and real runtime actions. API Gateway API configs and Apigee proxy revisions are **deployment configuration artifacts**, not public API versions. **API hub** tracks which API is in which state, who owns it, where it runs, and which consumers are impacted—yet does not replace runtime traffic management.

**Connecting to the CLOUD_PROVIDERS_GCP track:** governing API versions requires coordinating **IAM/authentication**, **Cloud Run/GKE backend deployments**, **VPC/networking**, **Cloud Monitoring/Logging**, **Cloud Billing**, and CI/CD pipelines. A successful API does not merely "deploy and run"—it must have **a clear contract, clear ownership, verified version transitions, transparent notices, and the ability to retire older versions without breaking users**.
