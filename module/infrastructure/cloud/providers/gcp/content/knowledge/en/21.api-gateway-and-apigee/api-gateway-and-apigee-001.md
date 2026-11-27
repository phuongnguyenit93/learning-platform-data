# Choosing API Gateway, Cloud Endpoints, and Apigee

> **Chapter:** API Gateway and Apigee  
> **Lesson:** Choosing API Gateway, Cloud Endpoints, and Apigee  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, databases, deployment automation, reliability, and cost. When a Java application needs to expose APIs to a mobile app, partners, or multiple microservices, the question is not just "opening an HTTPS port," but **who is allowed to call the API, how traffic is controlled, how usage is tracked, and who operates the intermediary layer**.

Google Cloud offers three approaches with varying levels of complexity:

- **API Gateway:** a **Google-managed** gateway, with API configuration using supported OpenAPI or gRPC specs; suitable for a relatively lightweight approach for APIs on Google Cloud.
- **Cloud Endpoints:** manages APIs through an **ESP/ESPv2 proxy deployed and operated by the team** alongside or in front of the backend; useful when you need control over proxy placement, integration with certain GKE/Compute Engine environments, or gRPC.
- **Apigee:** a **full-lifecycle API management** platform with API proxies, policies, products, developer experience, analytics, and broader deployment/governance options; suitable for API programs across multiple teams, partners, and environments.

**None of these products replaces the business authorization logic of the Java API.** An API key is not equivalent to user authentication; a valid proxy does not mean the caller is allowed to view every invoice. The best choice must balance **security, operability, API product needs, latency, cost, and team responsibilities**.

Project names, images, and endpoints are examples; the lab sections should only be run in an authorized sandbox. Features, pricing, region limits, and editions change over time, so consult the official documentation before designing for production.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish between an **API gateway** (request processing layer) and **API management** (API lifecycle and developer ecosystem).
2. Describe the architecture of API Gateway, Cloud Endpoints ESPv2, and Apigee, along with the components the team must operate themselves.
3. Compare authentication, authorization, quota, rate limiting, analytics, API products, portals, and policy mediation.
4. Choose a solution for Java APIs on Cloud Run, GKE, Compute Engine, B2B APIs, and multi-environment backends.
5. Design **API Gateway → Cloud Run private backend** with OpenAPI, a backend service account, and `roles/run.invoker`.
6. Explain the **ESPv2 + Service Management/Service Control** model of Cloud Endpoints.
7. Understand the basic components of an **Apigee API proxy** and the workflow for publishing an API product to partners.
8. Evaluate security, operations, API versioning, SLOs, quotas, cost, and migration risks.
9. Diagnose common errors and complete the solution-selection exercises.

## 2. Which Problems Does the API Layer Solve?

~~~mermaid
flowchart LR
    Client["Mobile / partner / frontend"] --> Edge["API entry point<br/>Gateway / ESPv2 / Apigee proxy"]
    Edge -->|"Auth, route, policy"| Java["Java Orders API<br/>Cloud Run / GKE / VM"]
    Java --> SQL["Cloud SQL"]
    Java --> Storage["Cloud Storage"]
    Ops["Logging / Monitoring<br/>IAM / Billing"] -. "Observability" .-> Edge
    Ops -. "Observability" .-> Java
~~~

There are three layers to separate:

| Layer | Key Question | Example |
|---|---|---|
| **Transport / entry point** | Which hostname does the client call over HTTPS? | Gateway endpoint, proxy host, external HTTPS load balancer |
| **API enforcement** | Does the request have valid credentials, quota/policy compliance, and a matching route? | JWT validation, API key, traffic rules, policies |
| **Application authorization** | Does user A have permission to view order B? | Java service checks tenant, scope, owner, and data |

A load balancer can handle TLS, routing, health checks, or WAF when properly integrated, but **it does not automatically become an API product platform**. Conversely, Apigee provides API management, yet still needs the backend to protect its own data and SLOs.

**First question when choosing a product:** do you actually need **a secure HTTPS entry point for a few APIs**, **a proxy running alongside the backend**, or **an API program with partners, products, onboarding, analytics, and policies across multiple teams**?

## 3. Quick Comparison of the Three Products

| Criterion | API Gateway | Cloud Endpoints (ESPv2) | Apigee |
|---|---|---|---|
| Product type | Fully managed API gateway | API management + **self-deployed proxy** | Full-lifecycle API management |
| Runtime unit | Google operates the gateway | Team runs the ESPv2 container/proxy | Apigee runtime/environment managed per chosen model |
| API definition | OpenAPI 2.0/3.x and gRPC in supported configurations | OpenAPI, gRPC; some framework-specific options | API proxy flows, policies, target endpoints, API products |
| Authentication | API key, JWT, and supported methods | API key/JWT via ESPv2/Service Control | API keys, OAuth 2.0, JWT, mTLS, and supported policies |
| Quota / traffic controls | Quota per API/service consumer | Service Control quota/monitoring | Quota, SpikeArrest, policies, and API-product-level rules |
| Complex request/response transformation | Limited; does not replace integration middleware | Limited compared to Apigee | Rich set of policies/flows |
| Developer portal / API products | Not the primary focus | API console and API sharing | Developer portal, API products, developer apps, analytics |
| Self-management level | Low | Manage ESPv2 lifecycle, sizing, patching, scaling | Manage policies, environments, onboarding, and governance |
| Common architecture | Cloud Run/Google Cloud backend | GKE/VM/services needing a co-located proxy | Many APIs, partners, multi-environment, hybrid |
| Primary costs | Gateway usage and related services | ESPv2 compute + networking + service infrastructure usage | Apigee environment, traffic, add-ons, and related items |

**This is a directional matrix**, not a guarantee that every feature is available in every region, edition, version, or protocol. For example, **Apigee portal/API products/monetization and advanced security** may be subject to edition/add-on limits; **API Gateway streaming** also has its own support status. Do not decide based solely on a single feature checkmark.

## 4. When to Choose API Gateway?

API Gateway is a streamlined approach when you want Google Cloud to **operate the gateway layer** and you need an OpenAPI/gRPC contract with basic policies.

~~~mermaid
flowchart LR
    Users["Client app"] -->|"HTTPS + key/JWT"| GW["API Gateway<br/>managed runtime"]
    GW -->|"ID token of backend identity"| Run["Cloud Run Java service<br/>private"]
    Run --> DB["Database / Storage"]
    Config["OpenAPI / API config"] -. "Deploy" .-> GW
~~~

### 4.1. Strengths

- No need to maintain proxy deployments/containers for the gateway.
- Uses an OpenAPI contract with `x-google-backend` to map routes to backends.
- Supports API keys, JWT authentication, and quotas per service configuration.
- Integrates with Cloud Logging/Monitoring and the API Gateway management interface.
- Can use a **backend authentication service account** to invoke a private Cloud Run service.
- Fits small Java teams that want to decouple API protection/routing from business code.

### 4.2. Limitations to Evaluate

- Not **full-lifecycle API management** with API products/developer portals like Apigee.
- Policy/mediation capabilities are less flexible than Apigee for complex B2B workflows.
- Need to check limits for **gateway locations, payload sizes, streaming, quotas, and timeouts** in the current documentation.
- API Gateway has a service-assigned public hostname; custom domain/TLS and ingress require designing an appropriate frontend if needed.
- Quotas configured at the API level affect API configs/gateways sharing the same API; version management must consider metrics compatibility.
- Does not replace database-level access control, tenant isolation logic, or authorization checks in Java.

### 4.3. Good-Fit Example

A team has an **Orders API** running on Cloud Run: `GET /v1/orders`, `POST /v1/orders`, needing customer authentication, basic quotas, and error tracking. There is no need for 100 API products, onboarding portals, or complex XML/SOAP transformations. **API Gateway is a reasonable default candidate**, provided deployment locations and limits meet requirements.

## 5. When to Choose Cloud Endpoints?

Cloud Endpoints provides API management via **Extensible Service Proxy (ESP)** or **ESPv2** combined with Google Service Management and Service Control.

~~~mermaid
flowchart LR
    Caller["Client"] --> ESP["ESPv2<br/>Envoy-based proxy"]
    ESP --> Java["Java API<br/>GKE / VM / Cloud Run"]
    SM["Service Management<br/>API config"] -. "Config" .-> ESP
    SC["Service Control<br/>quota/telemetry"] <-.-> ESP
    Team["Platform team"] -. "Build, patch, scale proxy" .-> ESP
~~~

**ESPv2** is Envoy-based and supports OpenAPI and gRPC within published scopes. **Legacy ESP** is an NGINX-based proxy, mainly maintained for existing users; for new deployments, **prefer ESPv2** per Google Cloud guidance. Cloud Endpoints remains a documented and supported product—**it is not deprecated merely because API Gateway exists**.

### 5.1. Steps the Team Handles Themselves

1. Define the API (OpenAPI or gRPC).
2. Deploy the service config to **Service Management**.
3. Package/deploy **ESPv2** in front of or alongside the backend in a supported environment.
4. Configure the service name, backend routing, auth, and quota.
5. Manage proxy container images, liveness/readiness probes, scaling, logging, and security updates.
6. Benchmark performance of both the proxy and the Java backend.

In GKE, ESPv2 can run as a sidecar or a proxy deployment depending on the architecture; the choice changes **failure points, resource requests/limits, and the traffic path**. With Compute Engine, you also need to operate the ESPv2 runtime. Cloud Run has separate ESPv2 deployment instructions, but you should not assume the entire feature set of API Gateway and Endpoints is identical.

### 5.2. Strengths and Trade-offs

| When It Fits | When to Consider Another Solution |
|---|---|
| Already have a GKE/VM platform team experienced in operating Envoy/proxies | Do not want to handle proxy patching/scaling/rollouts |
| gRPC backend or infrastructure specifics requiring a co-located proxy | Only need a few HTTP endpoints on Cloud Run |
| Need control over runtime placement and private connectivity paths | Need a developer portal, products, approval flows, deep analytics |
| Want Service Management/Service Control integration | Team lacks SRE capacity to monitor proxies |

**Cloud Endpoints is not "operations-free"** just because the control plane belongs to Google Cloud. Costs and risks here include **ESPv2 resources, networking, logs, and maintenance effort**.

## 6. When to Choose Apigee?

**Apigee** is an API management platform featuring **API proxies, policies, environments, products, developer apps, developer portals, and analytics**. The need is no longer just "route a request to the Orders API," but **managing dozens of APIs across multiple teams and partners**.

~~~mermaid
flowchart LR
    Partners["Partners A/B<br/>developer apps"] --> Portal["Developer portal<br/>docs + onboarding"]
    Portal --> Product["API products<br/>operations + quotas"]
    Partners --> Proxy["Apigee API proxy<br/>Auth + policy + analytics"]
    Proxy --> Java["Java Orders/Billing APIs"]
    Product -. "Permissions/plan" .-> Proxy
    Analytics["API analytics & governance"] -. "Monitor" .-> Proxy
~~~

### 6.1. Apigee Concepts

- **API proxy:** an endpoint provided by Apigee that defines flows to receive requests, apply policies, and forward to target services.
- **Policy:** a request/response processing component such as VerifyAPIKey, OAuthV2/JWT, SpikeArrest, Quota, AssignMessage, transformations, or threat protection depending on enabled features.
- **Environment:** a logical deployment zone for proxies and runtime rules.
- **API product:** a bundle of operations permitted for a developer app; can attach quota/access rules.
- **Developer app / developer portal:** clients/partners register applications, obtain credentials, read docs, and consume APIs by product.
- **Analytics:** analyzes usage, errors, latency, consumer behavior, and operational/business activity.
- **Apigee hybrid:** the control plane and runtime have separate deployment models; the runtime can run in organization-operated Kubernetes, suitable for data/traffic placement requirements.

### 6.2. Example API Product for a Logistics Partner

| Element | Design |
|---|---|
| Product | `Orders Partner API` |
| Operations | `GET /v1/orders/{id}`; `POST /v1/shipments` |
| Consumer | Partner's application, onboarded/approved |
| Identity | Developer app credentials, OAuth/JWT, and authentication policies |
| Traffic | Quota per product, spike protection at the proxy |
| Backend | Orders Java API, Billing API, logistics service |
| Analytics | Traffic by partner, error rate, p95 latency |
| Governance | Versioning, SLA, deprecation notice, audit, chargeback |

Apigee can reduce cross-cutting logic inside Java APIs, but **the application must still check permissions on each resource**: a partner allowed to call `GET /v1/orders/{id}` must not be able to read another partner's order.

### 6.3. Trade-offs

Apigee requires designing organizations/environments, API proxies, policies, routing, identities, developer onboarding, and operational processes. Costs include **active environments, API calls, add-ons, networking, analytics, and SLA/edition**, not merely the cost of "a gateway in front of an app." A two-endpoint demo system likely does not need that scale.

Do not assume **every edition** includes monetization, advanced security, a developer portal, or every proxy type. Before choosing, check **Pay-as-you-go vs subscription tiers**, deployment limits, supported regions, and billing/SLA terms.

## 7. Product Selection Matrix by Use Case

| Requirement | Starting Option | Rationale |
|---|---|---|
| A few Java REST APIs on Cloud Run | **API Gateway** | Easy to manage, no proxy operations |
| GKE gRPC service, platform team knows Envoy | **Cloud Endpoints/ESPv2** or API Gateway if features fit | Decided by protocol, topology, and operational ownership |
| Hundreds of APIs for multiple B2B partners | **Apigee** | Products, onboarding, policies, analytics |
| Multi-cloud/on-prem backends, complex policies | **Apigee / Apigee hybrid** | Multi-environment governance and mediation |
| Simple internal API for one service calling another | Might **need none of the three** | Cloud Run IAM, service-to-service auth, HTTPS/LB if sufficient |
| Already invested in ESPv2 on GKE, want to keep a private proxy | **Cloud Endpoints** | No need to switch to a managed gateway just because a new product exists |
| Need only API key + JWT + basic quota | **API Gateway** or **Endpoints** | Choose based on operational level and infrastructure |
| Need API product contracts, developer self-service, partner analytics | **Apigee** | API management rather than just request routing |
| HTTP traffic needing strong WAF, caching/CDN, L7 DDoS | Design **Application Load Balancer + Cloud Armor/CDN** as appropriate | This is a complementary network/security layer, not a replacement for all API products |

**Decision order:** (1) mandatory capabilities, (2) environment/protocol, (3) identity/security, (4) traffic and SLOs, (5) operations, (6) total cost. Do not start with "Apigee has the most features so it is always best."

## 8. Hands-on: API Gateway Protecting a Java API on Cloud Run

This lab assumes a Java Orders API is already running on a **private Cloud Run backend** with an HTTPS URI and accepts `GET /v1/orders`. For simplicity, use **API Gateway in `us-central1`**, a location supported in the documentation; re-check the location list for real deployments. The example Cloud Run backend is also in `us-central1`, although the gateway and backend can be in different locations if the design is supported.

**Prerequisites:** a sandbox project with billing enabled and the `apigateway.googleapis.com`, `servicemanagement.googleapis.com`, and `servicecontrol.googleapis.com` APIs enabled; the operator has IAM permissions to create APIs/Gateways, attach service accounts, and manage Cloud Run IAM appropriately.

### 8.1. Security Diagram of the Pattern

~~~mermaid
flowchart LR
    C["Client HTTPS"] -->|"Gateway public URL"| G["API Gateway: orders-gw"]
    G -->|"Google-signed ID token<br/>backend SA"| R["Cloud Run private<br/>orders-backend"]
    SA["apigw-backend SA<br/>roles/run.invoker"] -. "Used by Gateway" .-> G
    R --> DB["Cloud SQL / data"]
~~~

- **Client → Gateway:** requires an API key/JWT policy if you want to restrict callers. The basic sample below **does not yet enable client authentication**, so the Gateway endpoint can be called publicly.
- **Gateway → Cloud Run:** uses a **backend authentication service account**, which must have **`roles/run.invoker` on the Cloud Run service**.
- **Cloud Run → database:** uses the Java service's runtime service account and separate database authentication; do not use the Gateway backend SA as the runtime SA.

### 8.2. Prepare and Inspect the Backend

Read-only commands:

~~~bash
gcloud run services describe orders-backend \
  --project=PROJECT_ID \
  --region=us-central1 \
  --format="value(status.url)"

gcloud run services get-iam-policy orders-backend \
  --project=PROJECT_ID \
  --region=us-central1
~~~

Assume the backend URL looks like `https://orders-backend-EXAMPLE-uc.a.run.app`. The actual URI is returned by Cloud Run; **do not copy the example name as a real address**.

If the Java API uses Spring Boot, a minimal controller:

~~~java
package com.example.orders;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {
    @GetMapping("/v1/orders")
    public List<String> listOrders() {
        return List.of("OD-1001", "OD-1002");
    }
}
~~~

The controller is a small part of an existing Spring Boot application; **it is not a complete single-file Java program**. When running on Cloud Run, the container must listen on `0.0.0.0` on the port provided by `PORT` or as configured for the Cloud Run container. Ensure the image and health checks have been tested independently.

### 8.3. Create the Backend Service Account

**Commands from here on modify real IAM/resources**—only run in a sandbox:

~~~bash
gcloud iam service-accounts create apigw-backend \
  --project=PROJECT_ID \
  --display-name="API Gateway backend caller"

gcloud run services add-iam-policy-binding orders-backend \
  --project=PROJECT_ID \
  --region=us-central1 \
  --member="serviceAccount:apigw-backend@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Bind `roles/run.invoker` on the **target service** rather than at the project level to limit scope. The user creating the API config needs permission to use the service account per Cloud IAM (`iam.serviceAccounts.actAs` when required), but publishers should not be granted Owner. The Cloud Run runtime SA must **not** be confused with API Gateway's backend-auth SA.

### 8.4. Define the API with OpenAPI 2.0

Create the file `openapi-orders.yaml` **in your local lab directory** (not in the knowledge article repository). Replace `BACKEND_URL` with the actual Cloud Run URL, without an unintended trailing slash:

~~~yaml
swagger: "2.0"
info:
  title: orders-api
  version: "1.0.0"
  description: Orders API fronted by API Gateway
schemes:
- https
produces:
- application/json
x-google-backend:
  address: https://orders-backend-EXAMPLE-uc.a.run.app
  jwt_audience: https://orders-backend-EXAMPLE-uc.a.run.app
  path_translation: APPEND_PATH_TO_ADDRESS
paths:
  /v1/orders:
    get:
      operationId: listOrders
      summary: List orders (lab)
      responses:
        "200":
          description: Orders returned
          schema:
            type: array
            items:
              type: string
~~~

**Important explanations:**

- `swagger: "2.0"` is OpenAPI 2.0; API Gateway also supports OpenAPI 3.x, but the extensions have **different syntax**. Do not copy OpenAPI 2 style `x-google-backend` verbatim into a 3.x schema.
- `x-google-backend.address` is the backend server URL; `path_translation: APPEND_PATH_TO_ADDRESS` preserves the `/v1/orders` route per the sample design.
- `jwt_audience` specifies the audience of the ID token **sent by the Gateway to Cloud Run**. If using revision tags or custom path URLs, the default audience may not match; set the value explicitly to match the Cloud Run service.
- The sample **does not configure `securityDefinitions`/`security` for callers**; do not apply it directly to a production API holding sensitive data.
- Never put API secrets or JSON keys inside the OpenAPI spec.

### 8.5. Create the API Config and Gateway

~~~bash
gcloud api-gateway api-configs create orders-config-v1 \
  --project=PROJECT_ID \
  --api=orders-api \
  --openapi-spec=openapi-orders.yaml \
  --backend-auth-service-account=apigw-backend@PROJECT_ID.iam.gserviceaccount.com

gcloud api-gateway gateways create orders-gw \
  --project=PROJECT_ID \
  --api=orders-api \
  --api-config=orders-config-v1 \
  --location=us-central1
~~~

Creating an API config can take several minutes to propagate; **do not rush to create a second config for the same API before the first completes**. Deploying the gateway creates a public endpoint. Check status:

~~~bash
gcloud api-gateway api-configs describe orders-config-v1 \
  --project=PROJECT_ID \
  --api=orders-api

gcloud api-gateway gateways describe orders-gw \
  --project=PROJECT_ID \
  --location=us-central1

gcloud api-gateway gateways list \
  --project=PROJECT_ID \
  --location=us-central1
~~~

Read the **defaultHostname** field or corresponding gateway URL from the actual resource; send a test request over HTTPS. If the endpoint is not ready yet, check gateway state/config propagation instead of repeatedly creating resources.

### 8.6. Test and Add Caller Authentication

~~~bash
# Illustrative only after retrieving the actual HOSTNAME from gateway describe.
curl -i "https://GATEWAY_HOSTNAME/v1/orders"
~~~

The illustrative sample does not restrict callers, so **use non-sensitive test data**. To protect production:

- **JWT authentication:** configure the security scheme/issuer/JWKS/audience per your identity provider; API Gateway verifies the JWT at ingress.
- **API key:** used to identify the consumer project, for quota/monitoring, and to apply limits; **not sufficient to authenticate users for sensitive data**.
- **Backend IAM:** keep Cloud Run private, with only the Gateway backend SA having Invoker; do not open `allUsers` to "fix" a 403 error.
- **Business authorization:** the Java backend checks `tenantId`/`orderId` and user roles once the trust boundary is clear.
- **Quota:** size based on abuse risk and backend capacity; quotas do not replace WAF, load testing, or HPA/max-instances.

**Two separate authentication paths:** The client must satisfy the **Gateway policy**; the Gateway uses the **backend SA + ID token** to call private Cloud Run. Do not take the client's token as an IAM token for the Gateway to gain backend permissions.

## 9. If You Choose Cloud Endpoints: How Does Deployment Change?

With the same Java Orders API, if the backend runs in GKE and the team wants to use ESPv2:

1. Define the OpenAPI/gRPC service and authentication/quota rules.
2. Deploy the config to **Service Management** using the appropriate Endpoints commands/documentation.
3. Deploy the **ESPv2 image** alongside or in front of the Java backend in GKE.
4. Configure the proxy with the Service Management service name and backend URI.
5. Grant the proxy runtime identity the permissions needed to interact with Google service infrastructure.
6. Attach Service/Ingress/Load Balancer according to actual network access; pay attention to auth, TLS, and private/public entry points.
7. Monitor CPU/memory/latency/restarts of **both ESPv2 and the Java container**.
8. Perform rolling updates of the proxy separately from the backend while maintaining compatibility.

### 9.1. Why Is Resource Sizing Different from API Gateway?

With API Gateway, Google operates gateway capacity at the service level. With an ESPv2 sidecar on GKE, suppose each Pod includes:

~~~yaml
containers:
- name: java-orders
  resources:
    requests:
      cpu: "500m"
      memory: "768Mi"
- name: espv2-proxy
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
~~~

The scheduler must account for requests of **both containers**; for example, each Pod requests a total of **600m CPU, 896Mi RAM**, excluding init containers/overhead. This is an **illustration of the resources section**, not a deployable ESPv2 manifest: you still need the image, args, ports, probes, certificates, and service configuration.

### 9.2. When to Move Away from Endpoints?

If the team struggles to maintain ESPv2, does not need a co-located proxy, and workloads are primarily on Cloud Run, you can **try API Gateway**. If API product/partner governance expands, consider **Apigee**. Migration must re-verify **OpenAPI extensions, backend auth, quota semantics, headers, routing, gateway latency, and logging**—never assume a single config file drops in as a complete proxy replacement.

## 10. If You Choose Apigee: Differences in API Organization

For the same Orders API, the Apigee workflow goes further:

1. Provision an Apigee organization and environments per the chosen model/tier.
2. Design a public-facing **API proxy**, base path `/orders/v1`, and target endpoint pointing to the Java API.
3. Attach security policies to the appropriate flows: verify credentials, JWT/OAuth, quota/spike protection, mediation.
4. Package operations into an **API product** for partners.
5. Create developer apps/credentials and configure approvals/portal per policy.
6. Deploy the proxy revision to a test environment, checking traffic, policy errors, and analytics.
7. Promote to a production environment with audit/change processes.
8. Monitor API traffic by developer/app/product and backend SLOs.

### 10.1. Illustrative Policy Examples

Sample Apigee VerifyAPIKey (**only a policy fragment**, not a complete proxy bundle):

~~~xml
<VerifyAPIKey name="VerifyPartnerKey">
  <DisplayName>Verify Partner API Key</DisplayName>
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

Sample SpikeArrest:

~~~xml
<SpikeArrest name="LimitSpikes">
  <Rate>30ps</Rate>
</SpikeArrest>
~~~

For policies to take effect, they must be **attached to a flow**, the proxy deployed, API products/developer apps configured, and a supported version/edition used. `30ps` is an example, not a universally "safe" rate for all workloads. **SpikeArrest** smooths short-term spikes; **Quota** manages allowances over a time window. Both differ from **HPA**, which scales backend replicas.

### 10.2. Why Not Put All Logic Inside the Proxy?

Apigee can handle auth, validation, header/URL transformation, and shared policies. However, domain logic such as pricing calculations, inventory checks, tenant-scoped order permissions, database transactions, and business audits should stay in the Java backend or dedicated services. **Avoid overly complex proxies where API changes turn into hard-to-test business logic changes.**

## 11. Authentication, Quota, and IAM: Do Not Conflate Them

| Mechanism | What Does It Answer? | What Does It Not Replace? |
|---|---|---|
| **API key** | Which app/project is calling for quota/billing/monitoring? | User identity or order-level authorization |
| **JWT/OIDC** | Was the token issued by a trusted issuer with valid signature/audience/time? | Permissions on individual objects |
| **OAuth 2.0** | What scopes/tokens were granted to the client/user per the authorization flow? | Domain-level authorization in Java |
| **`roles/run.invoker`** | Can the Gateway backend SA invoke private Cloud Run? | Caller JWT, rate limiting, database auth |
| **Quota** | How many requests can a consumer make within a period? | Instantaneous protection against spikes or DDoS |
| **Rate limit / SpikeArrest** | Should bursts exceeding a threshold be throttled? | Long-term quotas, autoscaling, hard backend capacity |
| **Cloud Armor / WAF** | Should certain malicious traffic be filtered at supported edge layers? | API identity/consent/business authorization |
| **mTLS** | Do both ends authenticate via certificates as designed? | Tenant delegation or business roles |

**Safe pattern for B2B Java APIs:** verify credentials at the edge, pass identity/claims over a trusted contract, have the backend verify the context and enforce tenant checks; audit all IAM changes. Never accept a client-supplied `X-User-Id` header as proof of identity unless there is a clear trust boundary and explicit verification/override mechanism.

### 11.1. Notes on Headers and Gateways

A gateway/proxy may replace or add the `Authorization` header when authenticating to the backend. If the Java backend needs the original user token, design how identity is forwarded/verified according to the product documentation; never assume requests preserve every auth header unchanged. With API Gateway, check the `X-Forwarded-Authorization`/backend auth behavior and test end-to-end. Never log raw access tokens, API keys, or personal data.

## 12. Diagnostics and Operations

| Symptom | Likely Cause | Check First |
|---|---|---|
| API Gateway returns 401 to client | Wrong JWT issuer/audience/signature/header | API security config and client token |
| API Gateway returns 403 when calling Cloud Run | Backend SA lacks `roles/run.invoker` | Cloud Run IAM, backend SA, ID token audience |
| Gateway 404 | Wrong base path, operation, or route config | OpenAPI paths, path translation, and gateway config |
| Gateway 5xx or timeout | Unhealthy backend, deadline, network, or infrastructure quota | Gateway/Cloud Run logs, latency, Service Control |
| API key rejected | Key not authorized for API, wrong restrictions | API key restrictions, service enablement, and config |
| ESPv2 503 while Java is healthy | Proxy missing config/service name/route or overloaded | ESPv2 logs, Service Management config, Pod metrics |
| Endpoints missing telemetry/quota | Wrong proxy service identity or Service Control config | Service Control IAM/logs, service config |
| Apigee returns policy fault 401/429 | Rejected by VerifyAPIKey/OAuth/Quota/SpikeArrest | Proxy trace/debug, product/app/flow, and policy |
| Apigee 502/504 | Target endpoint/TLS/private networking or backend timeout | Target health, certs, network, timeouts |
| p95 latency increases after adding gateway | Extra hop, policy overhead, cold start/scale, or backend | Separate proxy latency from backend latency |
| Two configs have different quotas | Quota metrics changed when deploying a new config for the same API | Check quotas at API scope and across all gateways |
| Cost exceeds estimate | Traffic, gateway usage, ESPv2 nodes, or Apigee environments | Billing Reports, request count, active resources |

### 12.1. API Gateway Observability Commands

~~~bash
gcloud api-gateway apis list --project=PROJECT_ID

gcloud api-gateway api-configs list \
  --project=PROJECT_ID \
  --api=orders-api

gcloud api-gateway gateways describe orders-gw \
  --project=PROJECT_ID \
  --location=us-central1

gcloud run services logs read orders-backend \
  --project=PROJECT_ID \
  --region=us-central1 \
  --limit=50
~~~

When diagnosing, always isolate whether the **failure is at client → gateway** or **gateway → backend**:

- Fails only at the gateway and the backend sees no request: check client authentication/API key/quota/route.
- Gateway calls the backend and receives 403: check the backend auth service account + Cloud Run IAM/`aud`.
- Backend receives the request and returns 500: check Java logs, DB/Secret Manager permissions, business errors.
- ESPv2 or Apigee has its own proxy: inspect runtime logs/traces and health on both the proxy and the backend.

### 12.2. Rollout and Rollback

**API Gateway:** create a **new API config** when changing OpenAPI, test with a controlled gateway/canary; switch the gateway to the tested config per current guidance. Shared quota metrics on the same API can affect gateways still running older configs, so verify version semantics.

**Cloud Endpoints:** update the Service Management config and roll out ESPv2 in a controlled manner; maintain version compatibility between proxy and backend. In GKE, ensure requests/limits/PDBs and autoscaling are configured.

**Apigee:** manage API proxy revisions, shared flows, and environment deployments; perform canary/rollback per platform policy. Check API products/developer apps to avoid accidentally revoking partner access.

**Do not delete an API config, ESPv2 deployment, or Apigee proxy revision that consumers are still using** simply because a newer version exists.

## 13. Cost and TCO Evaluation

| Component | API Gateway | Cloud Endpoints | Apigee |
|---|---|---|---|
| Gateway/proxy runtime | Usage pricing | Compute/memory of ESPv2 where you run it | Active environments/traffic per plan |
| Traffic/egress | May apply | May apply | May apply |
| Logging/Monitoring | Based on data/logging | Based on data + proxy logs | Analytics/logging per tier/capabilities |
| Self-management | Minimal | Patch/scale/proxy rollout | Provisioning, products, policies, portal |
| Security | IAM/JWT/key + backend | IAM/JWT/key + proxy lifecycle | Policies, products, and optional add-ons |
| Organizational cost | Small for simple use cases | Includes SRE/DevOps overhead | Includes API program/platform governance |

**Use Total Cost of Ownership (TCO), not just per-request unit price:**

~~~text
TCO ≈ Gateway/proxy service fees
    + compute/network/observability resources
    + managing identities, certs, security
    + engineering & operational time
    + incident / missed-SLO costs
    + partner onboarding and governance costs
~~~

For Apigee, **Pay-as-you-go** and **Subscription** tiers have different billing models. For Endpoints, thinking "the proxy is free" is incomplete: compute, networking, and operational overhead still apply. API Gateway being simpler does not automatically make it cheapest at every traffic pattern or suitable for APIs with complex governance.

**FinOps checklist:** region/tier, request volume and payload size, latency, active environments, proxy compute, egress, Cloud Armor/LB (if any), log retention, CI/CD, and on-call. Verify pricing from official pricing pages when budgeting.

## 14. Case Study: RetailOne Opening APIs to Partners

### 14.1. Context

`RetailOne` has three Java services: `orders-api` on Cloud Run, `billing-api` on GKE, and `shipping-api` on Compute Engine. Initially there was only an internal web app; six months later, 30 logistics partners need API contracts, quotas, onboarding, the ability to temporarily suspend a partner, per-partner analytics, and some data transformation policies.

### 14.2. Phased Decisions

| Phase | Actual Need | Choice |
|---|---|---|
| **Phase A:** 1 internal REST API, low traffic | Basic HTTPS, JWT, IAM | API Gateway, or just Cloud Run IAM if sufficient |
| **Phase B:** GKE backend needing ESPv2 near app | gRPC/co-located proxy, operator skills | Cloud Endpoints when runtime control is needed |
| **Phase C:** 30 partners and 3 backends | API products, onboarding, per-partner quotas, analytics | Evaluate Apigee based on TCO/edition |
| **Phase D:** multi-cloud / data placement constraints | Shared policies and distributed runtime environments | Apigee hybrid when requirements are met |

**Do not migrate solely because the endpoint count grows.** Set **decision thresholds**: number of API products, developer onboarding hours, number of custom policies, usage reporting, incident cost, and SLOs. Even with 30 partners, if flows are very simple, still measure Apigee ROI.

### 14.3. Validation Plan Before Choosing

1. Identify OpenAPI contracts, auth mechanisms, token issuers, quotas, and current data classification.
2. Estimate average/peak RPS, payload sizes, p95 latency, and 4xx/5xx rates.
3. Proof-of-concept one end-to-end flow with a **private backend** and negative tests.
4. Compare protocol support, policies, IP/private connectivity, and deployment locations.
5. Verify developer onboarding, API product model, analytics/usage export, and auditing.
6. Measure gateway-added latency, retry behavior, backend overload, and outage blast radius.
7. Estimate 12-month TCO and operational staffing, not just lab costs.
8. Plan migration/rollback, ownership, and protection of older API versions.

## 15. Practice Exercises and Self-Assessment

### Exercise 1 — API Gateway or Apigee?

A company has one Java API on Cloud Run, three endpoints, 20,000 requests/day, and only needs JWT and basic metrics. There are no external partners or portal.

**Question:** which solution should be tried first? Why might Apigee be overkill?

**Hint:** API Gateway, or direct Cloud Run IAM if sufficient; Apigee adds disproportionate platform overhead/cost.

### Exercise 2 — Endpoints on GKE

A team has a gRPC backend on GKE, wants a proxy in the same Pod to control the traffic path, and has SREs managing Envoy.

**Question:** which product is the candidate and what operational costs must be accounted for?

**Hint:** Cloud Endpoints ESPv2; proxy resources, rollouts, patching, networking, logs, and quotas.

### Exercise 3 — Partner API Program

An enterprise has 50 partners, each with different API operation bundles and quotas, requiring a portal, onboarding, usage analytics, and a deprecation policy.

**Question:** which solution meets this at the product level? What edition/pricing prerequisites must be checked?

### Exercise 4 — Cloud Run Backend 403

API Gateway has a working hostname, but calling `GET /v1/orders` returns 403; Cloud Run is private. Someone suggests `--allow-unauthenticated`.

**Question:** why should the backend not be opened publicly? Which service account and role should be checked?

**Hint:** The API config's backend-auth SA needs `roles/run.invoker` on the exact Cloud Run service, along with the right `jwt_audience`.

### Exercise 5 — API Key Is Not Enough

A sensitive API uses a key to limit requests to 100 requests/minute. Anyone with a key can view every customer's orders.

**Question:** at which layer is the design flawed? Add caller auth and business authorization.

### Exercise 6 — Quota and Rate Limiting

Orders API has 3 partners, each with a monthly allowance, while the backend can only handle 500 RPS at peak.

**Question:** which problem does long-term quota solve, and which problem does rate limiting/SpikeArrest solve? Does HPA replace quotas?

### Exercise 7 — Performance and Incidents

After adding an ESPv2 sidecar, the Java Pod stays `Pending` due to `Insufficient cpu`, whereas it did not happen before.

**Question:** recalculate total resource requests and name other actions to check besides increasing node count?

### Exercise 8 — Risk-Controlled Migration

A team currently uses Endpoints/ESPv2 and wants to migrate to API Gateway to reduce operational burden.

**Question:** list what must be compared before cutover: API spec/extensions, auth/JWT, backend identity, URLs, quotas, headers, telemetry, error codes, traffic splitting, and rollback.

### Exercise 9 — Product Selection Under Constraints

An internal Java API runs on Cloud Run with no external customers, is called by another Cloud Run service using an ID token, and has no special quota/portal/analytics requirements.

**Question:** is there any need to buy/attach API Gateway/Endpoints/Apigee? Explain the simpler approach.

### Exercise 10 — Overall Architecture Plan

Create a decision table for three workloads:

- Java REST Orders API on Cloud Run, needing basic auth/quota.
- Java gRPC risk engine on GKE, needing a proxy close to the app.
- Multi-backend B2B logistics API system with onboarding and analytics.

For each workload, state the **choice**, **governance subject**, **auth policy**, **budget considerations**, **observability, and rollback plan**.

## 16. Pre-Production API Platform Checklist

- [ ] Identify API consumers, auth mode, data sensitivity, protocol, and network topology.
- [ ] Distinguish gateway ingress, backend invocation, and application-level authorization.
- [ ] Choose the minimum capabilities that meet requirements; avoid over-buying API management.
- [ ] Verify product availability, location, API specification support, and request/streaming limits.
- [ ] For API Gateway, OpenAPI config has `x-google-backend`, auth policy, and appropriate backend SA.
- [ ] Keep Cloud Run backend private when needed; Gateway backend SA has scoped `roles/run.invoker`.
- [ ] Restrict API keys and do not treat them as credentials for sensitive data.
- [ ] Test JWT/OIDC issuer/audience/claims and how identity is propagated to the backend.
- [ ] For Endpoints, ESPv2 is up to date with probes, resource sizing, telemetry, and separate rollouts.
- [ ] For Apigee, proxy policies, API products, developer apps, and analytics match the edition/tier.
- [ ] Distinguish long-term quotas, spike control, WAF, and backend autoscaling.
- [ ] Test 401/403/404/429/5xx, TLS, timeouts, header forwarding, and rate limits.
- [ ] Have Cloud Logging/Monitoring, p95/p99 latency, quota/usage metrics, and alerts.
- [ ] Have canary/rollout, version compatibility, and a tested rollback path.
- [ ] Have a threat model, IAM least privilege, audit, policy review, and data privacy controls.
- [ ] Budget for gateway/ESPv2/Apigee tier, backend, networking, monitoring, and operational costs.
- [ ] Clean up sandbox resources in dependency order; do not delete API configs/proxies with active consumers.

## 17. Official Google Cloud Documentation

Verify versions, pricing, regions, SLAs, and policy support when implementing:

- [API Gateway — About API Gateway](https://docs.cloud.google.com/api-gateway/docs/about-api-gateway)
- [API Gateway — Get started with Cloud Run](https://docs.cloud.google.com/api-gateway/docs/get-started-cloud-run)
- [API Gateway — Authentication methods](https://docs.cloud.google.com/api-gateway/docs/authentication-method)
- [API Gateway — Securing backend services](https://docs.cloud.google.com/api-gateway/docs/securing-backend-services)
- [API Gateway — API keys](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys)
- [API Gateway — Quotas and limits](https://docs.cloud.google.com/api-gateway/docs/quotas)
- [API Gateway — API configs](https://docs.cloud.google.com/api-gateway/docs/creating-api-config)
- [Cloud Endpoints — About Endpoints](https://docs.cloud.google.com/endpoints/docs/openapi/about-cloud-endpoints)
- [Cloud Endpoints — ESPv2 architecture](https://docs.cloud.google.com/endpoints/docs/openapi/architecture-overview)
- [Cloud Endpoints — Choose an Endpoints option](https://docs.cloud.google.com/endpoints/docs/choose-endpoints-option)
- [Apigee — What is Apigee?](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/what-apigee)
- [Apigee — API products](https://docs.cloud.google.com/apigee/docs/api-platform/publish/what-api-product)
- [Apigee — API Analytics](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/analytics-services-overview)
- [API Gateway pricing](https://cloud.google.com/api-gateway/pricing)
- [Apigee pricing](https://cloud.google.com/apigee/pricing)

**Key takeaway:** **API Gateway** fits exposing Cloud Run/Google Cloud APIs behind a managed endpoint with basic policies. **Cloud Endpoints/ESPv2** fits when you need to run a proxy alongside the backend and control the runtime. **Apigee** fits governing APIs as products for many consumers/partners with policies, onboarding, and analytics. Choose based on **actual requirements, operations team, security, latency, SLA, and total cost**; regardless of the product used, the Java backend must still enforce **user/tenant-level data authorization** and maintain observability, release, and rollback processes.
