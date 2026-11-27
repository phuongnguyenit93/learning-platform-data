# Azure API Management and API Organization

Suppose a company has **orders**, **customers**, and **payments** services. The mobile app needs to look up orders; the website calls the shopping cart API; logistics partners are only allowed to view delivery status; and internal teams have additional administrative permissions. If each client group calls the backends directly, every service will have to solve the same problems on its own: token validation, traffic throttling, routing, versioning, providing documentation, tracking errors, and protecting APIs when backends fail.

**Azure API Management (APIM)** provides an **API gateway and API lifecycle governance** layer between clients and backends. It helps publish APIs under clear contracts, group related operations, apply shared or specific policies, grant access by product/user group, monitor usage, and support API evolution without forcing every consumer to understand the underlying infrastructure details.

This lesson belongs to the **API and Workflow Integration** chapter of the **CLOUD_PROVIDERS_AZURE** module. Within the Microsoft Azure landscape—from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data—APIM is a component that connects applications to backends such as **Azure App Service, Azure Functions, Azure Container Apps, AKS, Azure SQL**, or external APIs. API organization must go hand in hand with security, observability, resilience, and cost control; simply “putting a URL behind a gateway” is not enough.

After completing this lesson, you will be able to:

- Describe the role and components of API Management: **instance, gateway, API, operation, product, group, subscription, backend, policy, and developer portal**.
- Design an API surface by bounded context, route, OpenAPI contract, consumer, version, and permissions.
- Distinguish between **API version** and **API revision**, and choose an appropriate versioning strategy and compatible change process.
- Apply APIM policies such as `validate-jwt`, `rate-limit-by-key`, `quota-by-key`, `set-backend-service`, `rewrite-uri`, `set-header`, and `cors` for the right purposes.
- Distinguish **APIM subscription key** from **Microsoft Entra access token**, managed identity, and backend authorization.
- Import an API from OpenAPI using Azure CLI/Portal, configure a product, and verify the gateway → backend path.
- Design private networking, backend protection, error observability, CI/CD automation, and rollback procedures.
- Choose a SKU/deployment tier based on load, latency, networking, features, SLA, and cost.

## 1. What is APIM and what problems does it solve?

**Azure API Management** is a service for managing APIs published to internal clients, partners, or the public. An APIM instance consists of the following main functional planes:

1. **API gateway:** receives requests, evaluates policies, routes to backends, and returns responses.
2. **Management plane:** configures APIs, operations, products, groups, subscriptions, policies, backends, identities, and governance resources.
3. **Developer portal:** provides an API catalog/documentation and developer onboarding workflow according to the service's configuration and features.
4. **Observability/integration:** tracks usage, diagnostics, traces/logs, and connects to Azure Monitor or supported observability systems.

APIM acts as the **logical front door for APIs**, but it should not be confused with a backend application. APIM can validate JWTs, rewrite URIs, set headers, cache responses, or throttle requests; most **business logic and data transactions** still belong to the backends.

### 1.1. Example request flow

~~~mermaid
flowchart LR
    CLIENT[Mobile / web / partner] -->|HTTPS + token/key| GATEWAY[APIM Gateway]
    GATEWAY -->|Policies| POLICY[Validate / rate-limit / rewrite]
    POLICY -->|Forward| ORDERS[Orders API - App Service]
    POLICY -->|Forward| DELIVERY[Shipping API - Container Apps]
    POLICY -->|Forward| PAY[Payments API - AKS]
    ORDERS --> DB[(Azure SQL)]
    DELIVERY --> BUS[Azure Service Bus]
    PAY --> KV[Azure Key Vault]
    GATEWAY -. Request metrics/traces .-> MON[Azure Monitor]
    ADMIN[API platform team] -. Config/APIs/products .-> GATEWAY
~~~

Example consumer call:

~~~http
GET https://api.contoso.example/orders/v1/orders/INV-98421 HTTP/1.1
Authorization: Bearer <access-token>
Ocp-Apim-Subscription-Key: <subscription-key-if-required>
X-Correlation-ID: req-8f0a
~~~

The gateway can validate the token, check quotas, and then route the request to `https://orders-backend.internal/api/orders/INV-98421`. The consumer sees the **public** path and contract without needing to know the backend's hostname or deployment architecture.

### 1.2. When should you use APIM?

| Scenario | What APIM provides | What you still have to design yourself |
|---|---|---|
| Multiple backends exposing public APIs | Unified gateway and consistent API contract | Ownership of each API, domain boundaries |
| Publishing APIs to partners | Products, onboarding, subscriptions, developer portal | Business permissions, legal agreements, SLA |
| Protecting APIs | JWT validation, throttling, routing policies | Final AuthN/AuthZ in the backend, WAF/DoS defense per architecture |
| API version changes | Version sets, revisions, publication management | Backward compatibility, deprecation/migration |
| API observability | Metrics, diagnostics, correlation | Backend instrumentation, SLOs, and alerting |
| Hybrid or multi-region environments | Supported gateway/network models | DNS, private routing, failover, DR |

APIM is usually a good fit when there are **multiple consumers** or when API policies are shared across multiple backends. For a small application with only a single private endpoint and no need for governance/API catalog yet, adding APIM can introduce unnecessary cost and complexity. Choose based on actual requirements.

### 1.3. What does APIM not replace?

- **Does not replace Azure Application Gateway/Front Door with WAF:** APIM is primarily an API gateway and API lifecycle service; HTTP protection against certain attacks may require a dedicated WAF/edge.
- **Does not automatically solve business authorization:** checking that an access token is valid is not enough to know **which specific order** a user may view; the backend must verify ownership/permissions.
- **Is not an equivalent to a service mesh/Kubernetes ingress controller:** these products address different operational layers.
- **Is not a queue, workflow engine, or database:** Service Bus/Event Grid/Logic Apps/SQL fulfill those respective roles.
- **Does not turn a broken backend into a healthy one:** retry, cache, and circuit-breaker policies do not replace resilience in the application/data layer.

## 2. APIM architecture in the Azure ecosystem

APIM is placed within a **subscription and resource group** alongside application resources. An APIM instance runs on a specific tier/SKU, with gateway and management hostnames and corresponding components/features.

~~~mermaid
flowchart TB
    USER[Consumer / partner] --> EDGE[Azure Front Door + WAF - if needed]
    EDGE --> G[APIM Gateway]
    DEVPORT[Developer Portal] -. API docs + onboarding .-> USER
    ADMIN[Platform team: Entra + Azure RBAC] -. Management plane .-> G
    G -->|HTTPS| WEB[App Service backend]
    G -->|HTTPS| FN[Functions backend]
    G -->|HTTPS via approved network| AKS[AKS backend]
    WEB --> SQL[(Azure SQL)]
    FN --> BLOB[(Blob Storage)]
    AKS --> SERVICEBUS[(Service Bus)]
    G -. Diagnostics .-> OBS[Azure Monitor / App Insights]
    KV[Key Vault] -. Certificates / secrets via identity .-> G
~~~

### 2.1. Three paths that must be verified

1. **Client → APIM gateway (inbound):** hostname, public/private exposure, TLS, certificate, WAF/access restrictions, and client authentication.
2. **APIM → backend (outbound):** backend URL, DNS, VNet connectivity/private endpoint, TLS, and backend credentials/managed identity.
3. **Operator/CI → APIM management plane:** Azure RBAC, Azure Resource Manager or management API, CI/CD, and policy deployment.

A client being able to reach APIM **does not prove** that APIM can call the backend. Conversely, the gateway reaching a private backend does not mean public clients are allowed into the gateway. A solution must test each path separately and verify where authorization is enforced.

### 2.2. Gateway and control plane are different

| Functional plane | Example activities | Permissions/controls |
|---|---|---|
| **Data plane - gateway** | Calling `GET /orders`, applying policies, forwarding to backend | Authentication token, subscription key, quotas, network |
| **Management plane** | Creating APIs, editing products, modifying policies, creating versions | Microsoft Entra, Azure RBAC, deployment approval |
| **Developer plane** | Viewing docs, subscribing to products, testing APIs | Portal user/group, product visibility, subscription approval |
| **Backend data plane** | Fetching orders from SQL or publishing Service Bus messages | Workload identity, database row-level/business auth |

Do not use the `Contributor` role on a resource group as proof that a user has permission to **call business APIs**. Someone can manage APIM without having a valid JWT to call `POST /payments`; conversely, a consumer may hold a subscription without having permission to change policies.

## 3. Resource organization: from instance to API operation

One way to visualize it:

~~~text
APIM instance: apim-shared-prod
├── API: Orders API
│   ├── GET  /orders/{id}
│   ├── POST /orders
│   └── GET  /orders/{id}/status
├── API: Catalog API
│   ├── GET  /products
│   └── GET  /products/{id}
├── API: Shipping API
│   └── GET /shipments/{id}
├── Products
│   ├── Partner Basic → Orders read + Shipping read
│   └── Internal Pro → Orders + Catalog + Shipping
├── Groups / Subscriptions
├── Named values / Backends / Policies
└── Developer portal / Diagnostics
~~~

### 3.1. Core concepts

| Object | What is it? | Example and purpose |
|---|---|---|
| **APIM instance/service** | Gateway/management resource in Azure | `apim-shared-prod` |
| **API** | Collection of operations sharing a contract and public URL suffix | `Orders API`, suffix `orders/v1` |
| **Operation** | An HTTP method + URL template (or corresponding API model) | `GET /orders/{id}` |
| **Product** | A bundle publishing one or more APIs to consumers with appropriate subscriptions/policies | `Partner Basic` |
| **Group** | A user/developer group in APIM to manage product visibility/subscription permissions | `partners`, `internal` |
| **Subscription** | A registration/credential relationship for accessing an API/product by subscription scope | Key issued by APIM to a consumer |
| **Backend entity** | Backend target configuration and certain credential/circuit breaker options depending on features | `orders-backend` |
| **Policy** | Request/response processing rules at a given scope | `validate-jwt`, `rate-limit-by-key` |
| **Named value** | Reusable configuration value in policies, optionally linked to Key Vault | `orders-backend-url` |
| **API version set** | Groups API versions belonging to a logical API | `Orders v1` and `Orders v2` |
| **API revision** | Non-breaking change to an API/version contract | `Orders v1;rev=2` |

**API vs. Product:** An API describes the contract and operations; a Product describes the **access package** intended for a consumer audience. An API can be placed in multiple products when supported by the APIM model and appropriate for requirements. A Product is not a container runtime and does not create copies of the backend.

### 3.2. Domain-based ownership model

APIs should be split by **business capability** rather than by a UI screen or strictly 1:1 with microservices:

| API domain | Owner | Primary clients | Current backend | Data classification |
|---|---|---|---|---|
| Orders | Order team | Web/mobile/partner | App Service | Order data |
| Catalog | Commerce team | Web/mobile | Container Apps | Public catalog |
| Payments | Payment team | Internal/payment partner | AKS/private service | Sensitive financial data |
| Shipping | Logistics team | Partner/internal | Azure Functions | Delivery status |

An API contract may be backed by multiple backends in the future; consumers should not have to change endpoints just because operations moved a backend from a VM to App Service. Avoid creating a “super API” that mixes all domains under the same auth/rate limit, making version and ownership control difficult.

### 3.3. API classification when publishing

- **Public APIs:** intended for external consumers, with clear contracts/terms.
- **Partner APIs:** only for contracted partners, with per-partner registration and monitoring mechanisms.
- **Internal APIs:** serve internal systems/employees, potentially requiring a private gateway and internal identity.
- **Administrative APIs:** high-privilege, should not be published as a general API product.

This classification does not create security by itself. **It must be combined with network exposure, token audience/scopes, APIM policies, backend authorization, and auditing**.

## 4. API contracts and operation standardization

Before importing into APIM, design the API contract: URLs, methods, schemas, error codes, authentication, pagination, idempotency, versioning, and backward compatibility. **OpenAPI** is a common way to describe HTTP REST APIs and generate documentation/SDKs/tests.

### 4.1. Path and HTTP method conventions

Example:

~~~text
GET    /orders/v1/orders                List/search orders
POST   /orders/v1/orders                Create order
GET    /orders/v1/orders/{orderId}      Get order by ID
GET    /orders/v1/orders/{orderId}/status
PATCH  /orders/v1/orders/{orderId}      Update selected fields
~~~

Here `orders/v1` is the **API suffix on the APIM gateway**, and `/orders/{orderId}` is the operation path within the API. When importing an OpenAPI spec that contains `servers`/paths, check the final mapping to avoid duplicated paths such as `/orders/v1/orders/v1/orders`.

| Rule | Reason |
|---|---|
| Use HTTP methods with proper semantics | GET does not mutate business state; POST can create resources |
| Use clear resource names | Easier API discovery and maintenance |
| Define a consistent error model | Clients distinguish 400/401/403/404/409/429/500/503 |
| Pagination and filtering | Do not return millions of records in a single response |
| Idempotency key when needed | Retrying POST after a network timeout does not create duplicate orders |
| Correlation/request ID | Debug across APIM and backend |
| Define response schemas and content types | Prevent clients from depending on undocumented fields |
| Document deprecation | Consumers have time to migrate versions |

### 4.2. Minimal OpenAPI example

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
  description: Order management API, example used for the lesson.
servers:
  - url: https://api.contoso.example/orders/v1
paths:
  /orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Get order details
      parameters:
        - in: path
          name: orderId
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order exists
          content:
            application/json:
              schema:
                type: object
                required: [id, status]
                properties:
                  id: {type: string}
                  status: {type: string}
        "401":
          description: Missing or invalid authentication credentials
        "403":
          description: Insufficient permissions to view the order
        "404":
          description: Order not found
  /orders:
    post:
      operationId: createOrder
      summary: Create an order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [customerId]
              properties:
                customerId: {type: string}
      responses:
        "201": {description: Order created successfully}
        "400": {description: Invalid input data}
        "409": {description: Business conflict}
~~~

**This is a learning contract**, not an existing endpoint. `api.contoso.example`, order IDs, and backends must be replaced with real names from an authorized system. When importing, check the OpenAPI validator, operation path permissions, request-body validation, and how APIM extracts the server base URL.

### 4.3. Contract ≠ implementation

Importing OpenAPI creates the API/operations/documentation model in APIM; **it does not deploy a backend**, create a database, or verify that business logic is correct. APIM can forward requests according to the contract, but the backend must still guarantee returned data, authentication, per-resource authorization, and transaction integrity.

An OpenAPI contract that does not declare a security scheme does not mean the actual API is allowed to be public. Configure security requirements in OpenAPI and the corresponding policies/rules, then **test negative cases** (no token, wrong token, wrong scope, wrong consumer key, wrong order owner).

## 5. API versions and revisions: two different mechanisms

An API can evolve in compatible or contract-breaking ways. APIM provides **API versions** and **API revisions** to organize these changes.

### 5.1. When to create a new version?

Create a **new API version** when existing clients are no longer compatible with the new API contract. For example:

- Changing a required field from `amount` (decimal) to `amountMinorUnits` (integer) that older clients do not understand.
- Removing an operation that consumers are currently using.
- Changing authentication or operation semantics in a way that breaks clients.
- Changing response schemas/HTTP behavior in a way that prevents existing clients from processing responses.

With an API version set, APIM can organize multiple versions of the same logical API. Available **versioning schemes** include **path**, **query string**, or **header**, depending on configuration/features:

| Strategy | Example | Pros / cons |
|---|---|---|
| **Path-based** | `/orders/v1/orders/123` | Easy to see, test, and cache; version is exposed in the URL |
| **Query-based** | `/orders/orders/123?api-version=1` | Keeps path stable, easy to call; requires query/client consistency |
| **Header-based** | `Api-Version: v1` | Clean URL; harder to observe if tools/caches/proxies strip headers |

No strategy automatically guarantees compatibility. Choose one consistent approach for the entire system, document it, standardize the error model, and avoid changing versioning styles every time a new team joins.

### 5.2. When to use a revision?

An **API revision** fits changes that **do not break the contract** of an API/version: adding an optional response field, updating a description, tuning policies, or changing a backend route without requiring consumers to change their requests.

APIM maintains the concept of a **current revision** and non-current revisions for testing/rolling out updates according to the workflow. In some REST API models, a non-current revision can be accessed via a URL such as `;rev=2` for testing when gateway/tier/authorization conditions allow. **This is not an automatic percentage-based canary mechanism**; promoting a revision to current requires an explicit release action.

| Question | API version | API revision |
|---|---|---|
| Purpose | Manage incompatible contracts | Adjust the same contract without changing the version |
| Do clients need to select differently? | Usually yes, via path/header/query | Usually no for the current revision |
| Example | v1 and v2 coexist | v1;rev=1 and v1;rev=2 |
| For long-term migration? | Suitable for supporting v1/v2 side by side | Primarily for editing/testing before publishing as current |
| Breaking DB schema changes? | Still requires a migration/contract plan | Revisions do not automatically roll back data |

### 5.3. Safely releasing a revision

1. Record the current revision, policies, backend, and key clients.
2. Create a new revision from the existing API per APIM capabilities.
3. Modify operations/policies/backend in the **test revision**.
4. Test auth, 2xx, 4xx, 5xx, quotas, and data via the revision URL or supported test setup.
5. Approve and switch the revision to **current** following the release process.
6. Monitor requests/errors/latency and keep the ability to roll back to the previous revision if still valid.

**Rolling back an APIM revision does not roll back an application deployment or database.** If new backend code dropped a SQL column that the old version needs, switching back to an old policy/revision will not restore the schema. Data and application changes must be designed compatibly, such as expand–migrate–contract.

## 6. Products, groups, and subscriptions: publishing APIs by consumer

If an API is “what the system can do,” a **product** is “the bundle of APIs that a consumer group is allowed to discover/subscribe to with corresponding rules.” A product can group multiple APIs, configure publish/approval/subscription requirements, and apply product-level policies per APIM features.

### 6.1. Example product design

| Product | Included APIs | Audience | Illustrative limit | Onboarding workflow |
|---|---|---|---|---|
| **Partner Basic** | GET Orders, GET Shipping (must consider API/operation scope) | Logistics partners | 60 requests/minute per subscription | Partner profile review |
| **Internal Business** | Orders + Catalog + Shipping | Employee applications | Per internal quota | Entra group / approval |
| **Premium Partner** | Orders + Shipping + advanced APIs | Paid-contract partners | Per contract/SLO | Contract + approval |
| **Sandbox** | Test APIs with mock data | Trial developers | Low limit | Conditional self-service |

**Pay attention to granularity:** in APIM, products commonly associate at the **API level**, and do not necessarily allow picking a single HTTP operation per product via the add-API action. If a product should only call `GET` while the same API also contains `POST`, you must design **appropriately split APIs or authorization/operation-restriction policies**. Do not assume adding Orders API to Partner Basic automatically grants only GET just because a table description says “GET Orders.”

### 6.2. Groups are not equivalent to Azure RBAC

A group in APIM can be used to manage who can view/subscribe to a product through the developer portal. It **does not** replace:

- Microsoft Entra groups and **Azure RBAC** on APIM management plane resources;
- OAuth scopes/app roles in the client's **access token**;
- Business permissions in the backend for a specific order/customer.

A user in the `partners` group who can see a product on the portal is not automatically allowed to call `DELETE /orders`. To protect delete operations, you must check the token, product/subscription context, and final authorization in the backend.

### 6.3. Product publication and subscription approval

A product can be configured as **published/unpublished** and require subscription/approval depending on features. Consumers register a subscription to obtain access credentials when required by the API/product. Depending on APIM configuration, subscriptions can be **product-scoped** or scoped differently such as API/all-APIs; therefore, a policy at product scope **should not be assumed to always apply to every call path to an API** if a consumer holds a different subscription scope.

Decisions that must be clearly documented:

1. Which consumers can view the product and its documentation?
2. Who can register/create a subscription, and is approval required?
3. Is the subscription key tied to a product or an API? Are there rules that bypass the product?
4. When users, contracts, or terms change, who revokes/rotates keys?
5. Does the API require a **valid JWT** in addition to the subscription key?
6. Are product policies enforced across every permitted call path under the current scopes?

**Do not leave an “internal” product published to all developers and assume the product name prevents access.** You must verify the settings and test the gateway endpoint directly using under-privileged credentials.

### 6.4. Subscription keys do not prove user identity

APIM typically supports two keys per subscription for rotation. The key is sent by the client, typically via a header:

~~~http
Ocp-Apim-Subscription-Key: <apim-subscription-key>
~~~

A key can help identify a **subscription/calling application**, enforce quotas, and apply some consumption controls, but it is a **shared bearer secret**, not a user login mechanism or an OAuth 2.0 token. If a key is leaked, anyone holding it can call the API within its allowed scope until the key is rotated/revoked.

For APIs handling customer data or payments, you normally need **Entra/OAuth2/JWT or an appropriate authentication mechanism**, followed by **business authorization**, in addition to a subscription key if the organization decides to use one.

## 7. Policies: APIM's request/response processing pipeline

Policies are XML configurations that declare **how the gateway processes requests and responses**. This is a core capability of APIM, but it is also a source of risk when policies are scoped too broadly, ordered incorrectly, or leak information.

### 7.1. Four commonly used sections

~~~xml
<policies>
  <inbound>
    <base />
    <!-- validate, throttle, modify request before calling backend -->
  </inbound>
  <backend>
    <base />
    <!-- orchestrate forwarding or backend configuration -->
  </backend>
  <outbound>
    <base />
    <!-- process response returned to client -->
  </outbound>
  <on-error>
    <base />
    <!-- handle errors raised in the policy pipeline -->
  </on-error>
</policies>
~~~

| Section | Primary responsibility | Example |
|---|---|---|
| **inbound** | Apply policies to the request before the backend | Validate JWT, rate limit, rewrite, set headers |
| **backend** | Control how the request is sent to the backend | Forward-request, controlled retry configuration |
| **outbound** | Modify the response before returning to the client | Strip internal headers, set headers, cache-store |
| **on-error** | Handle errors raised by the policy pipeline when failures occur | Controlled logging, return appropriate error response |

**Distinguish normal HTTP 4xx/5xx responses returned by the backend from policy pipeline errors.** `on-error` is not a mechanism to catch every HTTP 500 and turn it into a 200. If you need to handle responses by status code, use conditions in `outbound` or design error policies with proper semantics while preserving diagnosability.

### 7.2. Policy scope and inheritance

Common scopes include:

1. **Global (all APIs)**: logging, security headers, default protection policies.
2. **Workspace** if supported by the model/tier: operational boundary for a group of APIs.
3. **Product**: policies applied to calls belonging to the product based on subscription scope and routing.
4. **API**: rules shared across all operations of an API.
5. **Operation**: specific overrides for a single HTTP method/path.

`<base />` is critical for applying policies from higher scopes according to APIM inheritance rules. **Omitting `<base />` can cause a lower-scope policy to skip parent-scope policies unexpectedly**, leading to bypassed authentication/throttling or other unintended behavior. For production, review the operation's **effective policy** after scope merging, not just a single XML file.

### 7.3. Frequently used policies

| Policy | Role | Watch out for |
|---|---|---|
| `validate-jwt` | Validate JWT from client | Issuer, audience, expiration, required claims |
| `rate-limit` / `rate-limit-by-key` | Limit request count in a short window | Choose counter key per consumer; understand approximation across multiple gateways |
| `quota` / `quota-by-key` | Limit usage over a longer period | Billing/quota is not strict transaction accounting |
| `set-backend-service` | Select backend URL/entity | Avoid deriving backend URL from untrusted client input |
| `rewrite-uri` | Map public route to backend route | Ensure path/query parameters are forwarded accurately |
| `set-header` | Add/delete/overwrite HTTP headers | Do not blindly forward client-supplied identity headers as trusted |
| `set-query-parameter` | Modify query parameters for backend | Avoid putting secrets in URLs/logs |
| `cors` | Configure Cross-Origin Resource Sharing | CORS is not authentication/authorization |
| `cache-lookup` / `cache-store` | Caching per gateway capability | Do not cache personalized responses or sensitive data with wrong keys |
| `choose` / `when` | Conditional branching based on context | Complex logic needs tests |
| `return-response` | Return response from gateway without calling backend | Use only with proper intent and status codes |
| `authentication-managed-identity` | Acquire token for APIM to call backend with managed identity | Ensure token audience is correct and backend accepts Entra tokens |

Policies may have limitations depending on gateway/tier and version. Before deploying to production, check the **policy reference** for your APIM tier/gateway and test both positive and negative cases.

## 8. Policy practice: JWT, rate limiting, and backend routing

The following examples are **samples for learning how to read XML policies**, not production-ready configuration files. Practitioners must replace tenant ID, App ID URI/audience, backend URL, counter keys, and choose the right scope after review.

### 8.1. Validate JWT from Microsoft Entra ID

Suppose an API receives an **access token** issued by an Entra tenant, with your API as the audience. The policy can be placed at the API scope:

~~~xml
<policies>
  <inbound>
    <base />
    <validate-jwt
      header-name="Authorization"
      require-scheme="Bearer"
      failed-validation-httpcode="401"
      failed-validation-error-message="Unauthorized">
      <openid-config
        url="https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>api://orders-api-app-id</audience>
      </audiences>
      <required-claims>
        <claim name="roles" match="any">
          <value>Orders.Read</value>
        </claim>
      </required-claims>
    </validate-jwt>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Step-by-step meaning:**

1. The gateway reads `Authorization: Bearer <token>` from the client.
2. The token is validated against the **trusted tenant's** OpenID configuration/JWKS, accepted audiences, and other validation rules.
3. The example policy requires the `Orders.Read` app role in the `roles` claim.
4. If validation fails, APIM returns 401 per the policy and **does not forward the request** to the backend.

**Important nuances:**

- `api://orders-api-app-id` is a **placeholder** and must be replaced with the actual audience defined by the API app registration. In production, enforce the exact token issuer/tenant, audience, expiry, and appropriate claims/scopes.
- Delegated access tokens typically use `scp`, whereas application permissions typically use `roles`. Do not use the `roles=Orders.Read` sample to conclude all delegated flows work; design the policy for the actual client type.
- If the API needs to know **who may access a specific order**, the backend must still verify customer ownership, tenant ID, resource permission, and row-level authorization.
- Do not use an **ID token** in place of an access token for an API. An ID token verifies a client sign-in session and does not inherently carry the right audience/permissions to call an API.
- When applying a policy at the operation scope—if you want this operation to accept `Orders.Write` instead of `Orders.Read`—check **policy inheritance** so you do not accidentally require two conflicting roles.

### 8.2. Rate limiting by a verified identifier

A simple example limits by subscription; for APIs where the subscription may be null/optional, design a dedicated counter key:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="60"
      renewal-period="60"
      counter-key="@(context.Subscription != null
        ? context.Subscription.Id
        : context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

The example above is **not a complete anti-abuse policy**. Without a subscription, limiting by IP can lump many users behind NAT into a single counter or be evaded when callers rotate IPs. For JWT-protected APIs, consider using a **validated claim** (tenant/application/client ID) as the key, and avoid trusting unverified client-supplied headers.

In multi-region/multiple-gateway systems, rate-limit counters and accuracy may depend on distributed mechanisms/tiers. Do not use it in place of exact billing, fraud prevention, or strictly guaranteed transaction quotas. When rate-limited, clients should handle HTTP **429**, back off, and honor `Retry-After` when present.

### 8.3. Rules for combining authentication and throttling

Policy order matters. A configuration may choose to block invalid traffic early to reduce backend load; however, JWT validation has overhead, and if rate limiting is placed after authentication, unauthenticated requests might not be counted as expected. Choose a strategy aligned with your threat model.

A typical pipeline:

~~~text
Client HTTPS request
    ↓
Edge/WAF/network admission if present
    ↓
APIM inbound
    → validate token / subscription per policy
    → limit caller/tenant/operation
    → validate required headers / transform URI
    → set backend and identity
    ↓
APIM backend: forward request
    ↓
Backend: business authorization + transaction
    ↓
APIM outbound: response headers / cache/log if appropriate
    ↓
Client response
~~~

Do not trust client-supplied `X-User-ID` or `X-Tenant-ID` as authenticated identity without validating the token and stripping/overwriting spoofed headers before forwarding to the backend.

### 8.4. Selecting a backend by configured URL

~~~xml
<policies>
  <inbound>
    <base />
    <set-backend-service
      base-url="https://orders-api.internal.example" />
    <rewrite-uri template="/api/orders/{orderId}" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

**Scope limitation of the example:** `{orderId}` must be a valid parameter defined on the operation to which this policy applies; if placed at the API scope for operations without `orderId`, the policy may be invalid or route incorrectly. Attach this example to `GET /orders/{orderId}` and test path/query handling. `orders-api.internal.example` is an illustrative hostname; the APIM gateway must have DNS/routing to the backend, not just a URL written in the policy.

### 8.5. Using backend entities and named values

For multi-environment systems, do not duplicate backend hostnames/secrets across dozens of XML policies. APIM can manage **backend entities** and **named values**, then reference them in policies where supported.

Conceptual example:

~~~xml
<set-backend-service backend-id="orders-backend" />
~~~

Or policy values can reference a named value using `{{orders-backend-url}}` syntax in supported attributes/directives. For sensitive values, use **Key Vault-backed named values** and an appropriate managed identity/role, avoiding plaintext secrets in Git or logs.

Named values enable configuration reuse but **are not an authorization rule**. If a backend URL is derived from unvalidated input, SSRF/misrouting risks remain. Only use approved backend lists and protect who has permission to edit policies/named values.

## 9. CORS, caching, transformations, and backend protection

APIM policies can address several needs between HTTP clients and backends, but boundaries must be set to avoid turning the gateway into a repository of hard-to-test business logic.

### 9.1. CORS is not API access control

**Cross-Origin Resource Sharing (CORS)** is a browser mechanism deciding whether JavaScript from one origin may call and read responses from another origin. For example, `https://portal.contoso.example` wants to call `https://api.contoso.example`.

~~~xml
<policies>
  <inbound>
    <base />
    <cors allow-credentials="false">
      <allowed-origins>
        <origin>https://portal.contoso.example</origin>
      </allowed-origins>
      <allowed-methods>
        <method>GET</method>
        <method>POST</method>
      </allowed-methods>
      <allowed-headers>
        <header>Authorization</header>
        <header>Content-Type</header>
      </allowed-headers>
    </cors>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

This is an example for a **browser client** and must be adjusted when preflight requests involve custom headers or require credentials. **CORS does not stop curl, mobile apps, or server-side callers** from accessing the gateway; protect APIs using JWTs, keys, network controls, permissions, and backend authorization. Do not carelessly set `*` for origins/headers on sensitive APIs.

### 9.2. Caching to reduce load without leaking data

APIM provides policies for gateway caching or external caching according to supported features/tiers/gateways. Caching can be useful for public or infrequently changing data:

~~~text
GET /catalog/v1/products?page=1
    → Response can be cached for a short period

GET /orders/v1/orders/INV-98421
    → Contains specific customer data, highly sensitive
    → Do not cache solely by public path if shared across users
~~~

When caching:

1. Determine whether the content can be shared across all callers.
2. Design the cache key accounting for query parameters, vary headers, and authorization/tenant when appropriate.
3. Choose TTL and invalidation based on freshness/SLA.
4. Test behavior when backend data changes or returns errors.
5. Evaluate cache support/limits by APIM tier and multi-region topology.

**Do not cache orders purely by URL** if the response depends on identity; otherwise user A risks receiving user B's data. For multi-tenant APIs, isolate cache keys by authenticated context or disable caching for sensitive endpoints.

### 9.3. Header transformation and correlation IDs

A policy can add correlation ID/tracing headers before forwarding to the backend, or remove internal headers from responses. Example:

~~~xml
<policies>
  <inbound>
    <base />
    <set-header name="X-API-Gateway" exists-action="override">
      <value>azure-apim</value>
    </set-header>
  </inbound>
  <backend><base /></backend>
  <outbound>
    <base />
    <set-header name="X-Internal-Backend-Node"
                exists-action="delete" />
  </outbound>
  <on-error><base /></on-error>
</policies>
~~~

Do not forward every `Authorization` header verbatim to a backend that does not need it, or let APIM overwrite identity headers that the backend treats as pre-authenticated without strict controls. If the backend receives the **client JWT**, explicitly decide per threat model whether the backend re-validates the token or trusts APIM verification alone; an unprotected backend might otherwise be called directly via another path.

### 9.4. Bounded response transformations

The gateway can modify status/headers/body, convert XML ↔ JSON, or validate content per supported policies/features. However, complex transformations cause:

- Increased gateway latency and CPU usage.
- Harder debugging when contract and backend payloads diverge.
- Difficulty maintaining compatibility as schemas evolve.
- Data-leak risks if policies log/return excessive details.

If transformations involve heavy business rules, consider a dedicated **adapter/backend-for-frontend** or integration service. APIM suits focused policies and should not become a place for SQL transaction processing.

### 9.5. Throttling vs. quota

| Mechanism | Question answered | Example |
|---|---|---|
| **Rate limiting** | How fast can a consumer call? | 60 requests / 60 seconds |
| **Quota** | How much total volume can a consumer use in a period? | 100,000 requests / month |
| **Backend concurrency limit** | How many requests can the backend process simultaneously? | 50 concurrent requests |
| **Client retry budget** | How should clients retry on 429/503? | Exponential backoff + jitter |

APIM rate limits/quotas do not equal **guaranteed backend capacity**. One heavy request can consume more resources than hundreds of lightweight requests. Measure per-operation usage and control concurrency/timeouts at the appropriate application/edge layers.

## 10. Authentication, authorization, and managed identity per hop

One of the biggest design mistakes is assuming “the API requires a subscription key” means “the caller is fully authenticated.” Separate the layers:

### 10.1. Three identities in a single request

~~~mermaid
flowchart LR
    APP[Client app] -->|Entra access token + optional subscription key| APIM[APIM Gateway]
    APIM -->|Managed identity token or validated client token| BACKEND[Orders backend]
    BACKEND -->|Workload identity| SQL[(Azure SQL)]
~~~

| Hop | Credential | Purpose |
|---|---|---|
| **Client → APIM** | OAuth2/OIDC access token, mTLS/client cert, or approved scheme; optionally APIM subscription key | Verify application/user, API call permissions, and usage management |
| **APIM → backend** | Managed identity token, validated client token, or protected backend key/credential | Ensure only authorized gateway/identity can call the backend |
| **Backend → database** | Workload identity and data-plane permissions, or securely managed secret | Ensure only the backend API accesses required data |

An APIM subscription key **is not** a Microsoft Entra access token. APIM's managed identity calling a backend **does not automatically represent the end user**. If the backend needs user/tenant identity to authorize data, verified identity context must be passed securely via an approved protocol and checked against business rules.

### 10.2. Managed identity when APIM calls a backend

If the backend is an API protected by Microsoft Entra and accepts tokens with the proper audience, APIM can use a **managed identity** to acquire a token:

~~~xml
<policies>
  <inbound>
    <base />
    <authentication-managed-identity
      resource="api://orders-backend-app-id" />
    <set-backend-service backend-id="orders-backend" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

**Mandatory prerequisites:**

- The APIM instance has a valid system-assigned or user-assigned managed identity per supported features/configuration.
- The backend has the proper app registration / audience and validates Entra tokens.
- The APIM identity is granted permission to **call the backend** via the appropriate Entra app role/application permission/delegation, not just Azure RBAC Contributor on the APIM resource.
- The APIM → backend network path works and HTTPS/TLS is verified.
- If **end-user** identity is needed, the backend must still have a separately verified user identity source; a token from APIM's managed identity typically identifies **APIM as the caller**, not the end user.

### 10.3. Per-operation API authorization

Example:

| Operation | Illustrative client role/scope | Backend business rule |
|---|---|---|
| `GET /orders/{id}` | `Orders.Read` | User is authorized to view that specific order ID |
| `POST /orders` | `Orders.Write` | User/tenant allowed to create orders; prices/stock valid |
| `POST /payments` | `Payments.Submit` | Verify tenant, idempotency, limits, and fraud checks |
| `GET /catalog/products` | Public or `Catalog.Read` | Strip unpublished items if needed |

Place `validate-jwt` at the appropriate API/operation scope, but **do not** rely on APIM to enforce full row-level permissions since it typically lacks database context. The backend remains the enforcement point for per-resource policies.

### 10.4. Key rotation and developer lifecycle

A subscription key can leak through logs, browser source, code repos, or partner integrations. Governance processes should:

1. Issue keys scoped to the exact consumer/application; never share one key across all partners.
2. Restrict access to where keys are viewed; avoid sending them over unsecured chat/email.
3. Use primary/secondary keys for zero-downtime rotation where applicable.
4. Monitor anomalous usage by subscription/product/API.
5. Revoke keys/consumers when contracts end or credentials leak.
6. Evaluate whether to use subscription keys **alongside** OAuth tokens or OAuth alone, based on threat model and APIM configuration.

## 11. API gateway and private networking on Azure

An APIM instance can sit in various network architectures depending on SKU/tier and features. Distinguish **where clients can reach the gateway from** versus **which backends the gateway is allowed to reach**.

### 11.1. Typical architectures

| Model | When appropriate | What to verify |
|---|---|---|
| **Public APIM gateway → public backend with auth** | Simple public API/lab | TLS, backend auth, prevent backend bypass |
| **Public gateway → private backend** | Internet consumers, but backend only in VNet | APIM outbound VNet routing, DNS, NSG/firewall, and SKU |
| **Private/internal gateway → private backend** | Internal/enterprise APIs | VNet, private DNS, client connectivity, VPN/ExpressRoute |
| **Front Door + WAF → APIM → backend** | Edge protection / multi-region needed | Origin restrictions, hostname, TLS, WAF rules, routing |
| **Hybrid/self-hosted gateway** | Backends or consumers on-premises/edge per supported model | Gateway deployment, control plane connectivity, policy feature parity |

**Do not assume every APIM SKU supports the same networking features.** Classic tiers, v2 tiers, and workspace gateways differ in VNet integration/injection, private endpoints, availability, and regional behavior. Before selecting a SKU, verify supported features for the specific region and gateway type.

### 11.2. Private DNS and backend connectivity

If an App Service backend is only accessible via a Private Endpoint, APIM must have an **outbound** path to the corresponding private IP and resolve DNS correctly:

~~~text
Partner/employee
      |
      v
APIM gateway
      |
      | HTTPS, authenticated backend access
      v
VNet connectivity + private DNS
      |
      v
Private Endpoint to App Service / Functions / SQL service
~~~

An inbound private endpoint for APIM **does not automatically grant** APIM outbound access to a private backend. If the gateway resides in a different network/subscription, design VNet peering, routing, private DNS links, NSGs/firewalls, and test DNS resolution from the gateway runtime.

For a public gateway, protect the **backend origin** so clients cannot bypass the gateway when the backend URL is also public. Use private endpoints/network restrictions, backend authentication with APIM managed identity, certificates, or allowlists per architecture; do not rely on “keeping the backend URL secret” for security.

### 11.3. Custom domains and TLS

An APIM gateway typically has a default hostname and can be configured with an appropriate custom domain, such as `api.contoso.example`. You need:

- A valid TLS certificate, managed and rotated on schedule.
- DNS/CNAME/A records matching the gateway/edge topology.
- Proper TLS/HTTPS policies, SNI, hostname validation, and backend TLS.
- Consumer documentation referencing only stable public URLs, never internal hostnames.
- A domain/certificate change procedure with rollback and pre-expiration alerts.

When using Key Vault certificates, the APIM identity must have supported permissions to access the secret/cert material; Key Vault networking and rotation lifecycle must be verified. APIM does not absolve the organization of monitoring certificate chains/expirations.

### 11.4. Workspaces and self-hosted gateways

On supported APIM SKUs/models, **workspaces** enable API teams to manage resources within a delegated scope; **self-hosted gateways** allow running the gateway in other environments like Kubernetes/on-premises under service terms. Both capabilities have distinct permissions, networking, feature support, and billing.

Do not include them in a production architecture simply because the feature name appears in the Portal: verify gateway policy compatibility, management plane connectivity, logs/diagnostics, region/tier support, SLA, upgrade lifecycle, secret distribution, and current limits.

## 12. Developer portal, documentation, and API consumer onboarding

An API that is deployed without anyone knowing its operations, schemas, auth, and error handling is difficult to adopt. APIM's **Developer portal** can help developers discover published APIs/products, view documentation, and register subscriptions per instance/tier configuration.

### 12.1. Required information for a published API

| Item | Example details needed |
|---|---|
| **Business purpose** | API provides order status, does not allow payments |
| **Base URL** | `https://api.contoso.example/orders/v1` |
| **Operations** | Methods, URL params, headers, request/response schemas |
| **Authentication** | Entra issuer/audience, scopes/app roles, subscription requirement |
| **Authorization** | Which permissions allow reading orders per tenant/customer |
| **Limits** | Rate limit, quota, payload size, timeout, retry/backoff |
| **Errors** | 400, 401, 403, 404, 409, 429, 500, 503; error response contract |
| **Version lifecycle** | Current version, deprecation, sunset date, and migration guide |
| **Support** | Owner, support channel, status page, incident escalation |
| **Examples** | Curl/SDK samples with placeholders; never share real tokens/keys |

A published product on the portal displays APIs based on visibility/authorization policies; test with a **least-privileged consumer account** to confirm only the intended catalog is visible and sensitive details are not exposed. Customizing portal content does not replace gateway runtime policies.

### 12.2. Partner onboarding workflow

~~~mermaid
flowchart LR
    PARTNER[Partner developer] --> PORTAL[Developer portal / onboarding]
    PORTAL --> PRODUCT[Select API product]
    PRODUCT --> APPROVE[Contract + approval]
    APPROVE --> CREDS[Subscription credential + OAuth client setup]
    CREDS --> TEST[Sandbox tests]
    TEST --> PROD[Production access]
    PROD --> USE[Usage monitoring + rotation]
~~~

Prerequisites for releasing to a partner should include:

1. Signed contract and appropriate data-access agreement.
2. Product/operations scoped strictly to required permissions.
3. Subscription approval/credential rotation per policy.
4. Entra/OAuth tenant/client configuration or approved identity mechanism.
5. Sandbox contains no production PII/financial data.
6. Rate limits, escalation, and error-handling tested.
7. Per-consumer monitoring, auditing, and incident revocation plan in place.

**Never use a single subscription key for all partner clients** if independent auditing/revocation is needed. And never publish an entire admin API just because a partner needs one status-read endpoint.

## 13. Azure CLI Lab: creating an APIM instance and importing Orders API

This lab uses **Azure CLI in Bash/Cloud Shell** and an OpenAPI document like the one in section 4.2. **Commands in this lesson are intended only for an authorized lab subscription**, not commands executed during authoring. An APIM instance can incur significant charges as soon as it is provisioned; choose the right SKU for your purpose and delete resources properly after practicing.

### 13.1. Prerequisites

- An Azure subscription with permissions to create resource groups and Azure API Management.
- Azure CLI logged in to the correct tenant/subscription.
- An authorized team email address to use as the publisher contact.
- A valid OpenAPI file saved in the lab directory, e.g. `orders-openapi.yaml`, containing the sample introduced earlier and adapted for your test backend.
- An **actually existing** test HTTP/API backend capable of serving GET order without production data.
- Permissions to access the backend and configure authentication/network; do not use production secrets.
- Appropriate quota/tier/region and a lab budget.

### 13.2. Set variables and verify subscription

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RESOURCE_GROUP="rg-apim-lab"
LOCATION="southeastasia"
APIM_NAME="<globally-unique-apim-name>"
PUBLISHER_NAME="API Lab Team"
PUBLISHER_EMAIL="<approved-owner-email>"
API_ID="orders-v1"
API_PATH="orders/v1"
OPENAPI_PATH="./orders-openapi.yaml"

az account set --subscription "$SUBSCRIPTION_ID"
az account show \
  --query "{id:id,name:name,tenantId:tenantId}" \
  --output table
~~~

Values in `<...>` must be replaced with valid data. `APIM_NAME` must meet naming/uniqueness rules and be available in the region. Verify the resource group/subscription is genuinely a lab environment; do not push experimental policies to a shared production APIM instance.

### 13.3. Create the resource group and APIM instance

~~~bash
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

# Developer is for learning/development only, do not use for production.
az apim create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APIM_NAME" \
  --location "$LOCATION" \
  --publisher-name "$PUBLISHER_NAME" \
  --publisher-email "$PUBLISHER_EMAIL" \
  --sku-name Developer
~~~

APIM provisioning can take a while and may require specific subscription quota/configuration. **The Developer SKU is not intended for production workloads and does not carry the same SLA/feature guarantees as production tiers.** Multiple SKU families exist (classic/v2) with differing feature availability; verify the exact tier before using networking/workspaces/availability zones.

Read back the resource:

~~~bash
az apim show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APIM_NAME" \
  --query "{name:name,location:location,provisioningState:provisioningState,sku:sku.name}" \
  --output json
~~~

If `az apim show` or `create` options differ in your installed CLI version, check `az apim --help` and `az apim create --help`; do not switch to a more expensive production SKU just to bypass a configuration error.

### 13.4. Prepare the OpenAPI spec

Save the sample OpenAPI content from section 4.2 into `orders-openapi.yaml` inside a **learner-owned lab repo**. Check before importing:

- `openapi` version and YAML syntax are valid.
- Methods/paths/operation IDs do not collide.
- The server URL and chosen APIM public suffix **do not cause duplicated paths**.
- `200/201/400/401/403/404/409` have appropriate schema/error documentation.
- No credentials, private production hostnames, or sensitive personal data are included.
- The test backend already exists and honors the contract; importing does not create a backend.

### 13.5. Import an API into APIM

~~~bash
az apim api import \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id "$API_ID" \
  --path "$API_PATH" \
  --specification-format OpenApi \
  --specification-path "$OPENAPI_PATH"
~~~

The `--specification-format` syntax and file/URL import formats depend on CLI/API version. Check `az apim api import --help` in your environment and validate the spec first. After importing:

~~~bash
az apim api list \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --output table

az apim api show \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id "$API_ID" \
  --output json

az apim api operation list \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id "$API_ID" \
  --output table
~~~

Verify that operations have the correct methods/paths and no path duplication. If the spec defines `/orders/{orderId}` and the APIM suffix is `orders/v1`, the expected public route is `/orders/v1/orders/{orderId}`, not a URL guessed from the API display name.

### 13.6. Configure the actual backend

In **Azure Portal → API Management → APIs → Orders API → Settings / Design**, set the **Web service URL** to your test backend. For example, a test backend might have:

~~~text
Public gateway:
  https://<apim-name>.azure-api.net/orders/v1/orders/INV-98421

Test backend:
  https://<orders-test-backend-domain>/api/orders/INV-98421
~~~

If the backend path differs from the public path, use `rewrite-uri` or appropriate API settings to translate the URL accurately. **Do not point an APIM Developer instance at a production backend URL** just to test: it could generate real traffic or access real data.

Creating/importing an APIM resource **does not guarantee** that a backend is connected and ready. Before declaring the “lab successful,” verify DNS, HTTPS certificate, network access, backend response, and authentication on both sides.

### 13.7. Create a product and manage subscriptions in the Portal

In the Portal:

1. Go to the APIM instance → **Products** and create a test product, such as `sandbox-orders`.
2. Set display name, description, visibility/published state, and subscription requirements as needed.
3. Add **Orders API** to the product.
4. Configure user/developer groups allowed to view/subscribe if required.
5. Create/approve a test subscription via an authorized method; store the key in a secret store, never paste it into source code.
6. Check whether the gateway/API requires a key, JWT, or both; test requests with and without sufficient credentials.

On a shared APIM instance, adding an API to a product or changing product visibility can alter access for other consumers. Therefore, always practice in an isolated lab instance with proper approval.

### 13.8. Test calling the API

If the API requires a subscription key:

~~~bash
GATEWAY_HOST="<apim-name>.azure-api.net"
ORDER_ID="INV-98421"
SUBSCRIPTION_KEY="<lab-subscription-key>"

curl -i \
  "https://$GATEWAY_HOST/orders/v1/orders/$ORDER_ID" \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY"
~~~

When JWT validation is applied, a valid bearer **access token** targeted at the API is also required:

~~~bash
ACCESS_TOKEN="<valid-access-token-for-orders-api>"

curl -i \
  "https://$GATEWAY_HOST/orders/v1/orders/$ORDER_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY"
~~~

**Do not copy commands containing real tokens/keys into shared terminal history, CI logs, or tickets.** Use secure environment secret injection and redact outputs before sharing. Never treat any sample token in this lesson as a real credential.

Expected results depending on configuration:

| Test case | Expected result |
|---|---|
| Correct URL, valid token/key, healthy backend | 2xx response per contract |
| Missing subscription key when required | 401/403 or corresponding APIM message |
| Invalid token / wrong audience | 401 from `validate-jwt` |
| Valid token lacking required role/permission | 401/403 from policy and backend |
| Resource does not exist | 404 per business contract |
| Rate limit exceeded | 429 |
| Backend unreachable | Gateway/backend error such as 502/503/504 depending on cause |

**Do not hardcode a single HTTP status for all platform errors.** APIM, backends, and policies may return different status codes/error bodies; what matters is that clients follow the contract and logs provide enough detail to pinpoint where the failure occurred.

## 14. Organizing APIs across multiple teams and environments

An APIM instance can host many APIs, products, backends, and policies. As an organization scales, the question is not just how many APIs to create, but **who is allowed to change what**, how to maintain security standards, and how to prevent cross-team impact.

### 14.1. Governance separation model

| Team | Owns | Should not be allowed to |
|---|---|---|
| **Platform/API team** | APIM instance, gateway, base policies, networking, shared backend conventions | Arbitrarily change business logic/permissions |
| **Domain API team** | OpenAPI contract, operations, API-specific policies, backend versions | Override approved global JWT/WAF/network policies |
| **Security team** | Auth standards, JWT/claims, certificate/secret policies, vulnerability reviews | Unilaterally delete APIs or alter production routes bypassing change control |
| **Partner enablement** | Products, onboarding docs, subscriptions, and support | Grant backend admin access or expose financial APIs out of scope |
| **SRE/On-call** | SLOs, diagnostics, incidents, rollbacks/runbooks | Leave permanent manual changes outside IaC/source of truth unreconciled |

Where APIM workspaces are supported, management scope can be delegated by workspace; otherwise, use Azure RBAC/custom roles, code ownership, pipeline gates, and appropriate separation of instances/resource groups. **A workspace does not automatically isolate every API into a separate network/security boundary**; gateway, identity, connectivity, and tier limitations still apply.

### 14.2. Separating environments

One way to organize:

~~~text
Subscription: app-dev
  APIM: apim-dev
    API: orders-v1 (dev backend)
    Product: sandbox (fake data)

Subscription: app-staging
  APIM: apim-staging
    API: orders-v1 (staging backend)
    Product: partner-uat

Subscription: app-prod
  APIM: apim-prod
    API: orders-v1, orders-v2
    Products: partner-basic, partner-premium, internal
~~~

Not every organization needs three full APIM instances; cost, SLA, blast radius, and feature availability drive the choice. **Never share production credentials or databases with a sandbox** just to save setup effort.

### 14.3. API taxonomy and metadata

Each API should carry metadata:

~~~yaml
# Example governance metadata in repo, not an APIM resource schema
apiId: orders-v1
businessDomain: commerce.orders
ownerTeam: orders-platform
consumerTypes: [web, mobile, partner]
dataClassification: confidential
publicPath: orders/v1
backendService: orders-api
authMode: [entra-jwt, apim-subscription]
supportedVersions: [v1]
slo:
  availabilityTarget: "99.9% (hypothetical internal target)"
  latencyP95Ms: 500
onCall: orders-oncall
deprecationPolicy: "90-day notice (example)"
~~~

That metadata supports cataloging/auditing and does not replace APIM configuration. SLO/deprecation figures are **hypothetical examples** to be agreed upon with system owners and contracts.

### 14.4. Purpose- and permission-driven product design

Instead of an `Everything` product bundling all APIs, design from **use cases**:

- `Shipping Tracking` only exposes needed shipment tracking capabilities with restricted scope/operation auth.
- `Order Fulfillment` serves fulfillment partners with stronger scopes and separate quotas.
- `Catalog Public` serves low-sensitivity public catalog data with appropriate caching/rate limits.
- `Payments Internal` serves financial APIs requiring strict identity, network, and auditing controls.

If API operations have vastly different privilege levels, **split APIs along security boundaries or apply strict authorization policies** so a product does not accidentally over-grant access. Test every consumer's tokens/keys against unauthorized endpoints.

### 14.5. Managing the API lifecycle

Recommended stages:

1. **Design:** API owner, OpenAPI, threat model, error model, rate/quota.
2. **Develop/Test:** test backend, negative tests, policy tests, performance.
3. **Publish:** products and onboarding, auth credentials, docs.
4. **Operate:** SLOs, monitoring, subscription usage, credential rotation.
5. **Evolve:** revisions, versions, backward compatibility, migration guides.
6. **Deprecate/Retire:** announcements, measuring old-version traffic, disabling/removing with approval.

Do not remove an older API version while consumers still call it without a migration path. For partners, provide a **deprecation window and formal communication** per contract.

## 15. CI/CD and Infrastructure as Code for APIM

As the number of APIs and policies grows, editing configurations manually in the Portal easily causes **configuration drift** across dev/staging/prod. Manage APIM definitions as code with a pipeline ensuring every change is tested, approved, and reversible.

### 15.1. Source of truth

Example repository structure:

~~~text
api-platform/
├── apis/
│   ├── orders/
│   │   ├── openapi.yaml
│   │   ├── api-policy.xml
│   │   ├── operations/
│   │   │   └── get-order-policy.xml
│   │   └── versions/
│   │       └── v2-openapi.yaml
│   └── shipping/
│       ├── openapi.yaml
│       └── api-policy.xml
├── products/
│   ├── partner-basic.yaml
│   └── internal.yaml
├── infrastructure/
│   ├── main.bicep
│   └── parameters/
│       ├── dev.json
│       └── prod.json
├── tests/
│   ├── contract/
│   ├── policies/
│   └── security/
└── README.md
~~~

This is a **learning structure sample**, not a requirement to create extra files in the lesson project. In real deployments, you may use Bicep/ARM/Terraform, organization-maintained APIM DevOps tooling, or the Azure Resource Manager API, but you must choose **one clear source of control** for each configuration to prevent the Portal and CI from overwriting each other.

### 15.2. What belongs in version control

- API contracts (OpenAPI/GraphQL/SOAP metadata per model).
- API suffixes, operations, policies (global/product/API/operation), and backend references.
- Products, associations, groups/visibility, and subscription requirements **without keys**.
- **Non-sensitive** named values; use Key Vault references for secrets.
- Custom domain/network/identity/tier configurations in IaC where feasible.
- Diagnostics, alerts, policy tests, and release metadata.
- API versions/revisions along with deprecation schedules.

**Never commit** APIM subscription keys, client secrets, certificate private keys, or live tokens. For secrets, store deployable references/identity bindings while keeping actual secret values in a protected secret store.

### 15.3. Controlled change pipeline

~~~mermaid
flowchart LR
    PR[Pull Request] --> LINT[OpenAPI / XML / IaC validate]
    LINT --> SEC[Security + API contract checks]
    SEC --> DIFF[What will change?]
    DIFF --> APPROVE[CODEOWNERS / approval]
    APPROVE --> DEV[Deploy to dev APIM]
    DEV --> TEST[Auth / contract / load tests]
    TEST --> PROD[Promote same config to prod]
    PROD --> OBS[Observe / rollback if needed]
~~~

A pipeline should distinguish **deploying the API contract** from **deploying the backend application**. Updating OpenAPI or a `set-backend-service` policy does not build new code or upgrade Azure SQL. When both backend and contract must change together, order changes compatibly: backend accepts old and new → add API version/revision → migrate consumers → remove old behavior.

### 15.4. Policy tests and negative tests

Before applying:

| Test | Why it is needed |
|---|---|
| Well-formed XML policy / syntax validation | Prevent deployment failures from malformed XML |
| Proper `<base />` presence | Preserve inherited security policies |
| Missing/wrong JWT | Ensure policy blocks with 401 properly |
| Valid issuer token with wrong audience | Ensure tokens from other APIs are rejected |
| Token lacking required role/scope | Protect sensitive operations |
| Missing/invalid subscription key | Enforce product/API requirements |
| Rate limits and quotas | Return 429 when threshold is reached without breaking other callers |
| Public/backend path mapping | Prevent misrewriting paths, queries, or HTTP methods |
| PII/log redaction | Never log bearer tokens, account keys, or payment details |
| Cross-tenant/isolation | Consumer A cannot view Consumer B's orders |
| Backend outage | Clients receive appropriate errors; alerts have correlation |

**Do not test only the 200 OK happy path.** A critical public API must prove 401, 403, 429, timeout, backend 5xx, and retired-version behavior.

### 15.5. Configuration rollback

When a new policy triggers 401 for every client or rewrites routes incorrectly:

1. Identify the changed commit/config, scope, and affected operations.
2. Freeze further promotions.
3. Revert the policy/config via Git/IaC through an emergency pipeline or switch back to the prior API revision if that mechanism applies.
4. Verify the **effective policy**, backend URL, and health at the gateway.
5. Run synthetic tests from the proper client types; monitor 401/403/5xx/429 and business SLOs.
6. Document the incident and reconcile final state with the source of truth.

Direct Portal edits during an emergency may be necessary under **break-glass** procedures, but must be recorded and reconciled back to Git afterward; otherwise, the next IaC apply will overwrite the emergency fix.

## 16. API observability: metrics, logs, tracing, and SLOs

An APIM instance may return 200 at the gateway while the business transaction still fails; conversely, a backend may be healthy while a gateway policy returns 401 due to a wrong audience. Separate **gateway health, backend health, and business correctness**.

### 16.1. Telemetry layers

| Layer | Data to observe | Example signals |
|---|---|---|
| **Ingress/gateway** | Request count, latency, status by API/operation/product/region | 429 spikes only for Partner Basic |
| **Policy/auth** | JWT validation failures, subscription key failures, transformation errors | 401 spikes after certificate/config rotation |
| **Backend forwarding** | Backend latency, timeouts, TLS/DNS/network errors | APIM receives 502/504 even though backend Pod is Running |
| **Backend app** | Request traces, exceptions, dependency performance | SQL query p95 increases |
| **Business** | Order success rate, payment completion, customer-facing SLO | POST returns HTTP success but no invoice is created |
| **Control plane** | Activity Log, policy deployments, role changes | Who changed rate limits or public ingress |
| **Cost/capacity** | Gateway load, network egress, log ingestion, tier capacity | Peak saturation / overprovisioning |

### 16.2. Correlation and distributed tracing

API requests traverse multiple services and require correlation:

~~~text
Client request ID
    ↓
APIM gateway request ID / trace context
    ↓
Orders backend trace ID
    ↓
SQL query / Service Bus message correlation ID
    ↓
Application Insights / OpenTelemetry distributed trace
~~~

Prefer **W3C Trace Context** (`traceparent`/`tracestate`) in instrumented systems, or a consistent correlation ID. Never treat a client-supplied header ID as proof of identity or authorization. For troubleshooting, preserve both the client-supplied ID and a system-controlled generated ID.

### 16.3. Diagnostics and sampling

APIM can export diagnostics/telemetry to Application Insights and Azure Monitor per supported configuration/tier. To operate safely:

1. Enable appropriate telemetry sources (gateway logs, metrics, backend traces).
2. Configure sampling according to traffic, audit requirements, and cost.
3. Redact/exclude `Authorization`, `Ocp-Apim-Subscription-Key`, cookies, and sensitive request bodies.
4. Set retention, access controls, and data residency per policy.
5. Verify logs actually record API, operation, response code, backend duration, and correlation.
6. Create alerts with owners; do not assume having a Log Analytics workspace means logs appear automatically.

A request rejected with 401 by `validate-jwt` may never touch the backend; looking only at backend Application Insights will miss it. Conversely, the backend may fail after APIM forwards successfully; logs from both sides are required.

### 16.4. Example SLO

Suppose an order-read API has these targets:

~~~text
Availability (user-facing): >= 99.9% per internal agreement
Latency p95: under 500 ms during defined operating hours
Error budget: managed by SLO owner
Valid 4xx contract errors: per semantics, not automatically counted as outage
Payment/data errors: covered by dedicated business checks
~~~

These numbers are illustrative only and are not an Azure SLA guarantee. Define **what constitutes a valid request**, how availability is calculated, regions/routes, and maintenance windows. For instance, returning 401 for a forged token is **correct behavior** and should not count as an API availability failure.

### 16.5. How should dashboards be segmented?

- **API/operation:** GET reads and POST writes have different latency/risk profiles.
- **Version:** v1 may spike in errors after a backend change while v2 stays healthy.
- **Product/subscription:** identify which partner exceeds quotas or sends anomalous traffic.
- **Backend:** 502/504 errors isolated to a specific backend.
- **Region/gateway:** network issues or region-specific capacity constraints.
- **Auth error category:** missing key vs. invalid token signature vs. missing role.
- **Business tenant/correlation (PII masked):** investigate impact without exposing data.

If a metric does not expose a desired dimension on the current tier/telemetry channel, supplement it with structured logs from policies/backends where supported; **do not assume every metric includes every dimension**.

## 17. Reliability, latency, retries, and failover

Placing APIM between clients and backends adds an HTTP hop. The goal is effective API governance without turning the gateway into a single point of failure or a source of retry storms.

### 17.1. Layered timeouts

A single request can encounter multiple timeouts:

~~~text
Client HTTP timeout
    ↕
Edge/WAF/Front Door timeout (if present)
    ↕
APIM gateway backend forwarding timeout
    ↕
Backend application timeout
    ↕
SQL/external dependency timeout
~~~

If the backend takes 120 seconds while the client only waits 15 seconds, raising APIM's timeout to 180 seconds **does not** improve the client experience. For long-running operations, consider returning **202 Accepted**, enqueuing a Queue Storage/Service Bus message, and providing a job-status endpoint or webhook.

### 17.2. Retries require idempotency and budgets

Retries across APIM/edge/client/backend can multiply:

~~~text
Client retries 3 times
  × Gateway retries 3 times
    × Backend retries SQL 3 times
  = can amplify processing attempts significantly
~~~

Do not blindly enable retries for `POST /payments`. If a request creates a payment and the response is lost, retrying can create duplicate payments. Use **idempotency keys**, database uniqueness constraints, outbox/transactional handling, and bounded retries/backoff/jitter. On 429, respect `Retry-After` where appropriate.

### 17.3. Circuit breakers and backend pools

APIM supports managing **backend entities/pools** and policies/circuit breakers depending on supported tiers/features. Some architectures shift traffic between primary/secondary backends to reduce errors.

Conditions for failover to be meaningful:

1. The secondary backend is genuinely healthy and has sufficient capacity.
2. Data/database replication and semantics meet RPO/RTO.
3. DNS/routes/identities/certificates are verified along the failover path.
4. Backend response contracts are compatible.
5. Traffic floods do not overwhelm and crash the secondary too.
6. A failback procedure and monitoring exist, not just a URL swap.

**Do not treat `set-backend-service` between two hostnames as complete disaster recovery.** If both backends share the same failing database, switching hostnames will not save the system.

### 17.4. Multi-region and high availability

APIM offers different regional/availability options by SKU and tier. Some production tiers support zone/region capabilities; do not generalize that every tier has regional replicas or the same SLA. Verify:

- Actual gateway availability, zone redundancy, and regional deployment.
- Azure Front Door/DNS failover, backend locality, and latency.
- Data synchronization, certificates/identities, and network rules in each region.
- Diagnostic settings and secrets when regions/gateways change.
- RPO/RTO and recovery runbooks if the APIM control plane or gateway experiences an outage.

A Developer instance used for testing **is not a fallback strategy** for production. Financial APIs require a periodically tested DR model, not just a two-region architecture diagram.

## 18. Choosing an APIM tier/SKU and managing cost

APIM offers **classic** and **v2** families (and related gateway/workspace options) with differing capabilities in SLA, scaling, network integration, workspaces, availability, and cost. Pricing and SKU names/features can vary by region and over time. There is no single default SKU right for every goal.

### 18.1. Tier selection checklist

| Criterion | Questions to ask |
|---|---|
| **Environment** | Lab/dev or production? Is an SLA mandatory? |
| **Traffic** | Requests/sec, peak load, payload size, policy complexity, latency budget? |
| **Network** | Public/internal gateway? Private backends? VNet integration/injection? |
| **Security** | Managed identity, Key Vault, mTLS, JWT policy, custom domains? |
| **Topology** | Single region or multi-region/multi-zone? DR RPO/RTO? |
| **Governance** | Are workspaces, self-hosted gateways, or multiple API teams required? |
| **Operations** | Logging/diagnostics, tracing, and capacity scaling? |
| **Cost** | Fixed gateway/units, scaling, bandwidth, private networking, monitoring? |

The **Developer tier** is generally intended for development and testing, not production. Production tiers differ in feature availability, especially between classic and v2. Verify that the **exact SKU and region** support all requirements before designing networking or deploying IaC.

### 18.2. Cost drivers

| Item | What drives cost |
|---|---|
| **APIM instance/tier/units** | Gateway infrastructure per pricing model/SKU, scaling |
| **Request processing** | Some tiers/pricing models include per-request/capacity components |
| **Network** | NAT, Firewall, Private Endpoints, egress, cross-region traffic, and edge WAF/Front Door |
| **Observability** | Application Insights/Log Analytics ingestion, retention, sampling |
| **Key Vault** | Secret operations and certificate lifecycle per service |
| **Backend compute/data** | App Service/Functions/AKS/SQL/Storage remain billed separately |
| **CI/CD and testing** | Pipeline runners, scans, staging instances, load testing |
| **DR** | Secondary regions, standby capacity, backups, and monitoring |

**APIM does not eliminate backend costs.** A well-designed caching policy can reduce backend requests; conversely, excessive body logging, uncontrolled retries, or keeping multiple high-tier environments running can significantly increase spend.

### 18.3. Optimization strategies

- Choose the SKU based on real feature/SLO needs, not the highest tier unnecessarily.
- Place APIM close to backends/regions appropriately to reduce latency and network transfer.
- Bound diagnostics payload logging and retention; use purposeful sampling/tracing.
- Separate environments appropriately without over-multiplying instances for small teams.
- Cache **only** data permitted by contract that contains no PII.
- Use per-consumer throttling/quotas to curb abuse and protect backends.
- Clean up sandbox/test resources by owner and check remaining network/log resources.
- Tag resources with owner/environment/application/costCenter; review budgets with Azure Cost Management.

**Budget alerts are not a hard spending cap.** Deleting an API object while leaving the APIM instance running will not stop gateway charges; review full resource billing and tier pricing mechanics.

## 19. Troubleshooting APIM: 401, 403, 404, 429, 502, and 504

When consumer API calls fail, do not immediately modify the backend or disable `validate-jwt`. Isolate whether the failure lies in **client → gateway policy → backend network/auth → application → data service**.

### 19.1. Symptom table

| Symptom | Possible causes | Investigation / remediation |
|---|---|---|
| `401 Access denied due to missing subscription key` | Product/API/subscription requires a key | Check product association, subscription scope/key, header, and renewal |
| `401 Unauthorized` from `validate-jwt` | Expired token, wrong issuer/audience, signature/claims mismatch | Check app registration, token type, OpenID metadata, scopes/roles |
| `403 Forbidden` | Valid token but insufficient permissions, backend authorization, or network policy | Distinguish APIM policy error vs. backend 403; check resource permissions |
| `404 Resource not found` | Wrong API suffix, operation template, version, or backend route | Inspect `api.path`, method/path, URI rewrite, and backend URL |
| `429 Too Many Requests` | Rate limit/quota hit at APIM or backend | Check counter key, limit window, product usage; back off per policy |
| `500` from backend | Application bug, database exception, dependency failure | Backend logs/traces, request correlation, recent releases |
| `502 Bad Gateway` | Gateway did not receive a valid response from backend, TLS or connection error | APIM gateway diagnostics, backend DNS/TLS, routing, and health |
| `503 Service Unavailable` | Backend/gateway overloaded or unavailable | Gateway metrics, backend replicas, capacity, health |
| `504 Gateway Timeout` | Slow backend, broken route, or policy timeout | APIM/backend latency, DNS/network, timeout chain |
| `CORS error` in browser | Allowed origin/header/method mismatch or preflight/auth issue | Browser devtools, OPTIONS behavior, APIM CORS policy |
| Portal does not show API/product | Unpublished, group access, portal cache/config | Portal user permissions, products, visibility/approval |
| Valid subscription key, backend returns 401 | Backend does not trust APIM key; backend requires JWT/managed identity | Verify APIM→backend auth separately |
| APIM routes to wrong environment | Misconfigured backend entity/named value/slot | Azure activity/config diff, backend URL, and environment |
| Operation-level policy change has no effect | Wrong scope, missing `<base />` inheritance, or policy order | Review effective policy/route, policy tester |
| Data leak via cache | Cache key missing tenant/user or non-cacheable response cached | Disable caching, purge per capability, security incident, fix key |
| New certificate causes errors | TLS trust/SNI/hostname mismatch, Key Vault permissions | Certificate chain/expiry, DNS, backend hostname, MI |
| v2 API works but v1 fails | Incompatible contract/backend schema or wrong version mapping | Test each version, migration status, and deprecation rules |

**Never arbitrarily replace status codes**—such as turning 401/403/429 into 200 “to make the app work.” That masks security failures and breaks the API contract for clients.

### 19.2. 8-step investigation runbook

**Step 1 — Confirm scope.** Are subscription, resource group, APIM instance, environment, API ID, version/revision, operation, hostname, and timestamp correct?

~~~bash
az account show --query "{id:id,name:name}" -o table

az apim show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APIM_NAME" \
  --query "{name:name,provisioningState:provisioningState}" \
  -o json

az apim api list \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --output table
~~~

**Step 2 — Identify the client request.** Do the HTTP method/path, query, and headers match the contract? Are token/key present? Do not put real credentials in incident tickets.

**Step 3 — Inspect the raw response.** Did 401/403/404/429/5xx originate from an APIM policy or the backend? Cross-check gateway logs/correlation and test the corresponding endpoint with an authorized client.

**Step 4 — Verify authentication/authorization.** For JWT 401s, inspect issuer/audience/expiration/scopes/roles and inherited policies. For key errors, check product/subscription scope and key status/rotation. For backend 403s, verify business permissions and backend identity.

**Step 5 — Verify routing/network.** Check APIM API suffix and operation mapping, backend URL, private DNS, VNet, firewall, TLS, and backend readiness.

**Step 6 — Check policy changes.** Did anyone recently modify global/product/API/operation policies, named values, or backend entities? Was `<base />` removed, breaking inheritance? Record the commit/config diff.

**Step 7 — Measure impact.** Check error rates by API/version/product/region, backend latency, number of impacted partners, and failed business transactions.

**Step 8 — Recover sustainably.** Roll back policy/revision/route from the configuration source, verify 2xx and negative auth tests, monitor business SLOs, and close the incident.

### 19.3. Specific scenario: valid key but 403

A partner sends a valid `Ocp-Apim-Subscription-Key` and receives 403 when reading an order:

~~~text
Client holds an APIM product subscription
    ↓
Gateway accepts subscription key
    ↓
JWT check succeeds
    ↓
Backend checks order.customerId / token tenant
    ↓
Backend returns 403 (user not owner)
~~~

**This may be the intended behavior.** Do not grant APIM Contributor or disable backend authorization to eliminate the 403. Verify whether the caller is actually permitted to access **that order ID**.

### 19.4. Scenario: v2 import creates duplicated paths

The OpenAPI `servers.url` already contains `/orders/v2`, but during import the admin sets API suffix `orders/v2` while importing paths `/orders/v2/orders`. The gateway ends up expecting `/orders/v2/orders/v2/orders`, causing documented client calls to receive 404.

Fix: inspect **public suffix + operation path + backend path**, standardize the contract once, test operations, and update documentation. Avoid uncoordinated edits to both APIM paths and backend routers that break existing clients.

### 19.5. Scenario: rate limit inadvertently blocks multiple customers

A policy uses `context.Request.IpAddress` as the counter key. Hundreds of employees in the same office sit behind NAT, share one public IP, and all get hit with 429.

Fix: after authenticating the caller, choose a **verified client/application/tenant/subscription identifier** as the counter key where appropriate. Never trust an arbitrary client-sent `X-Customer-ID` header for quota accounting. After making the change, test fairness across multiple consumers and verify actual backend capacity limits.

## 20. Case study: API platform for e-commerce and logistics partners

**Hypothetical scenario:** An enterprise runs an Orders API on App Service, a Catalog API on Azure Container Apps, and a Payments API on AKS. Azure SQL and Azure Service Bus backends reside in a private network. The company is preparing to expose part of its APIs to three logistics partners, allowing each partner to check shipment status without viewing payment history or another partner's data.

Requirements:

- A single public API hostname with HTTPS/TLS and WAF per architecture.
- Consumers must present Entra/OAuth credentials or approved authentication; partners have separate subscriptions for usage management.
- API v1 continues running while v2 is tested and migrated.
- Limit of 60 requests/minute per partner for the status-read endpoint, without sharing one IP counter.
- Payments API is accessible only to clients with dedicated scopes/roles, and the backend enforces business authorization.
- Partners cannot bypass APIM to call backends directly.
- Monitor 401/403/429/5xx, p95 latency, and per-consumer usage.
- Policy/revision rollback and a compatible data plan must be in place.

### 20.1. Suggested architecture

~~~mermaid
flowchart TB
    PARTNER[Partner apps] -->|HTTPS access token + subscription key| EDGE[Front Door / WAF]
    EMPLOYEE[Internal apps] -->|HTTPS access token| EDGE
    EDGE --> APIM[Azure API Management gateway]
    APIM --> POLICY[JWT + rate-limit-by-key + route]
    POLICY --> ORDERS[Orders API - App Service]
    POLICY --> SHIP[Shipping API - Azure Functions]
    POLICY --> CAT[Catalog API - Container Apps]
    POLICY --> PAY[Payments API - AKS private]
    ORDERS --> SQL[(Azure SQL)]
    SHIP --> BUS[(Azure Service Bus)]
    PAY --> SQL
    APIM -. Metrics / logs .-> MON[Azure Monitor / App Insights]
    KV[Key Vault] -. Secret/cert references .-> APIM
    ADMIN[Platform / API owners / Security] -. CI/CD + approval .-> APIM
~~~

**The diagram is logical.** Private networking works only when the APIM SKU supports the desired configuration, and VNet/private DNS/routes and backend identities are properly provisioned. Front Door/WAF is not enabled by default when creating APIM; it is an architectural choice driven by requirements and cost.

### 20.2. Splitting APIs and products

| Logical API ID | Owner | API surface | Product |
|---|---|---|---|
| `shipping-v1` | Logistics | `GET /shipments/{id}` | Partner Tracking, Internal |
| `orders-read-v1` | Orders | `GET /orders/{id}/status` with minimal data | Partner Tracking |
| `orders-admin-v1` | Orders | `POST/PATCH /orders` | Internal Business |
| `catalog-v1` | Commerce | `GET /products` | Catalog Public, Internal |
| `payments-v1` | Payments | `POST /payments` | Internal Secure Payments |

**Why separate Orders Read and Admin?** To minimize exposure and protect sensitive operations. Keeping GET and POST in one API and adding it to Partner Tracking requires very careful operation-level policies; separating the API surface generally prevents over-granting when gateway/product subscriptions have differing scopes.

### 20.3. Authentication and authorization along the flow

1. The partner application requests an **access token** with the proper audience/scope for the API.
2. The partner sends the request with its own subscription key; the gateway validates both JWT and key per policy.
3. The rate-limit counter keys off the subscription ID/verified caller identifier, not a shared IP.
4. APIM forwards over the appropriate network, using managed identity when the backend requires it.
5. Shipping/Orders backends verify the partner is authorized to view **that shipment/order**, preventing cross-tenant data leaks.
6. Responses return only necessary fields; payment details or inappropriate data classifications are excluded.
7. Logs record sanitized request ID/partner ID, API/operation/status, never tokens or keys.

### 20.4. Version v1/v2 and rollback

Suppose v2 of the Shipping API changes how status is represented:

~~~json
{
  "shipmentId": "SHP-2026-101",
  "status": "in_transit",
  "estimatedDelivery": "2026-11-25"
}
~~~

If v1 only used `status: "on_the_way"` and older clients cannot parse `in_transit`, this can be a **breaking semantic change**. Organize v1/v2 in an API version set; keep v1 alive per contract duration and publish a migration guide. If you are only fixing a description or adding an optional field, a revision can be used instead of a version.

When v2 fails, switching consumers back to v1 **does not** restore data if the backend already applied an incompatible migration. Verify response schemas and data compatibility before allowing rollback.

### 20.5. Go-live procedure

1. API owner and security review OpenAPI, policies, versioning, and partner use cases.
2. CI validates OpenAPI, XML policies, Bicep/Terraform, and security negative tests.
3. Deploy to dev/staging APIM, test backends, and production-equivalent network settings.
4. Issue sandbox subscriptions and test tokens to each partner; run contract tests.
5. Test per-subscription rate limits and role/operation restrictions.
6. Test failover/timeouts and confirm no public bypass path exists to backends.
7. Approve promotion; deploy API products and docs to production.
8. Monitor 401/403/429/5xx, latency, quotas, and business success during initial rollout.
9. Maintain a rollback plan, key rotation, and partner support per contractual SLA.

### 20.6. Handling a widespread 401 after a policy deployment

Suppose a policy update changes the audience from `api://orders-v1` to `api://orders-v2`, but partner clients are still calling v1. Every previously valid request begins returning 401.

Runbook:

1. Freeze further promotions/config changes.
2. Identify which API scope/revision received the wrong audience and which consumers are impacted.
3. Revert the policy to the approved valid audience via Git/IaC or restore the appropriate revision.
4. Do not disable JWT validation just to get 200s; it is a security gate.
5. Test **valid v1 tokens**, invalid tokens, wrong-tenant tokens, and unauthorized partners.
6. Monitor the drop in 401s, 5xx/latency, and business API results; document the incident and add tests to prevent recurrence.

## 21. Capstone lab: publishing APIs with APIM

**Scenario:** A company has two test backends: `orders-api` with `GET /orders/{id}` and `POST /orders`, and `shipping-api` with `GET /shipments/{id}`. The backends run on App Service/Functions with test data. The company wants to publish the APIs to internal teams and a logistics partner, requiring JWT authentication, subscription usage tracking, versioning, and policy rollback capability.

Execute this only in an authorized **lab subscription/resource group/APIM**. Do not run administrative commands in production or use real customer/payment data in the lab.

### 21.1. Requirements

1. **Architecture:** diagram client → edge/WAF (if needed) → APIM → backend → Azure SQL/Service Bus. Distinguish control plane from data plane.
2. **API organization:** select API IDs, public suffixes, operations, and owners for Orders/Shipping.
3. **OpenAPI:** author at least three operations with request/response/error schemas and unique `operationId`s.
4. **Versioning:** pick path/query/header for v1/v2 and explain when to use revisions.
5. **Product:** design `Partner Tracking` with status-read access only and `Internal Business` able to create orders. If Orders API contains both GET and POST, describe how to avoid over-granting via the product.
6. **Subscription:** describe the registration/approval workflow, key issuance, dual keys for rotation, and revocation when a partner exits.
7. **Azure CLI:** create an APIM Developer instance in the lab RG, import OpenAPI, list APIs/operations, and verify the backend.
8. **JWT:** add a policy validating issuer/audience and the `Orders.Read` permission on the right operation. Test missing token, expired token, wrong audience, valid token, and missing role.
9. **Throttling:** set an illustrative limit of `60 calls/60s` per subscription, explaining why not to use source IP when multiple partners share NAT.
10. **Backend routing:** design `set-backend-service`/`rewrite-uri` if the public path differs from the backend path; verify query/path parameters are preserved.
11. **CORS:** allow only a specific test origin; explain why curl can still call the API when a browser blocks it via CORS.
12. **Private networking:** if the backend only has a Private Endpoint, list the required VNet, DNS, routes, SKU features, and backend auth.
13. **Managed identity:** design APIM calling the backend with the proper token audience, distinguishing it from a user access token.
14. **Developer portal:** describe product discovery, docs, subscription approval, authentication, and sandbox data.
15. **Observability:** define a dashboard breaking down 401/403/429/5xx, p95, backend latency, version, and subscription.
16. **Rollback:** a new policy causes all requests to return 401. Write a runbook to revert config/revision, run negative tests, and monitor.
17. **FinOps:** list gateway SKU/units, network, monitoring, backend compute, and lab resources to delete afterward.
18. **Governance:** define API owner/platform/security/partner enablement responsibilities and CODEOWNERS/review gates.

### 21.2. Reference permission matrix

| Consumer | `GET /shipping` | `GET /orders/{id}` | `POST /orders` | `POST /payments` |
|---|---|---|---|---|
| **Partner logistics** | Allowed for matching shipment | Authorized orders only | Deny | Deny |
| **Internal order app** | Per granted role | Per internal permissions | Allowed with `Orders.Write` | Deny if missing Payments role |
| **Payment service** | Not by default | When needed per least privilege | Not by default | Allowed per dedicated policy |
| **Unknown caller** | Deny | Deny | Deny | Deny |

*Note:* `GET /shipping` in the table is shorthand; the real API uses an explicit contract such as `GET /shipments/{id}`. Every “Allowed” cell still depends on a valid token, subscription, and **resource-level authorization in the backend**. Never rely solely on a broad role and let a partner read arbitrary customers' orders.

### 21.3. Expected test outcomes

~~~text
Case A: missing required key
    → request blocked at gateway

Case B: key valid, JWT missing
    → validate-jwt blocks request

Case C: JWT valid, audience wrong
    → token rejected

Case D: JWT valid, role Orders.Read, wrong order owner
    → backend returns 403

Case E: token/key valid, resource permitted, backend healthy
    → returns success response per OpenAPI contract

Case F: consumer exceeds rate limit
    → HTTP 429, client must retry with backoff

Case G: APIM cannot connect to private backend
    → network/gateway error, check DNS and outbound route

Case H: policy change breaks audience
    → revert via Git/approved revision, verify valid tokens succeed
~~~

### 21.4. Discussion questions

**Question 1.** The Partner Tracking product includes `Orders API`, which has both read and create operations. The partner holds a product subscription key. Is it guaranteed that the partner cannot call `POST /orders`?

*Hint:* No. Adding an API to a product does not automatically filter operations based on the product name. You must split APIs by permission boundaries or enforce policies checking JWT scopes/roles/operations, and test directly.

**Question 2.** A token from an Entra tenant is valid, but its audience is Graph API. Should it be accepted to call Orders API?

*Hint:* No. The API requires an access token whose audience is **Orders API**, with matching issuer/claims and authorization rules; a token with a valid signature is not automatically valid for every API.

**Question 3.** An APIM Developer instance connected to a backend over a public hostname. You move the backend behind a Private Endpoint without changing gateway networking. What might happen?

*Hint:* APIM may fail to resolve or route to the private IP, causing 502/503/504 depending on the situation. You must choose an APIM tier/topology supporting outbound private connectivity, configure VNet/private DNS/routes, and verify TLS/identity.

**Question 4.** CI updates the backend to v2 and drops a DB column that v1 still reads. API v2 breaks, so you revert the APIM revision back to v1. Is the rollback complete?

*Hint:* No. Reverting the API route/policy does not bring the database column back; you need compatible migrations or data recovery using a runbook evaluated against RPO/RTO.

**Question 5.** Gateway logs show 30,000 requests returning 401 in one minute. Does that automatically mean an API outage?

*Hint:* No. A burst of unauthenticated requests or scanner traffic may be getting properly blocked by policy. Inspect errors on **valid** traffic, business SLOs, auth error categories, and recent deployments.

### 21.5. Completion criteria

The lab is complete when the learner:

- Defines an **API contract and public routes** consistent with the backend.
- Accurately distinguishes **API, operation, product, group, subscription, version, revision, and policy scopes**.
- Proves requests with valid keys/JWTs reach the backend while unauthorized requests are blocked.
- Explains how to prevent a product from over-granting access to sensitive operations.
- Verifies private backend connectivity, identity, and diagnostics without leaking secrets.
- Establishes a CI/CD and rollback workflow covering **both policies and business/data dependencies**.
- Provides a cost estimate by SKU/topology and a safe cleanup plan.

## 22. Environment-by-environment APIM deployment checklist

### 22.1. Before creating an API or product

- [ ] Confirm the correct subscription, resource group, APIM instance/SKU, environment, and owner.
- [ ] Classify APIs as public/partner/internal/admin based on data and consumers.
- [ ] Establish the OpenAPI contract, paths, methods, status/error model, versioning, and SLO.
- [ ] Identify the real backend, health endpoint, auth, networking, and deployment rollback plan.
- [ ] Verify the SKU supports required private networking, workspaces, certificates, and region/availability.
- [ ] Create a threat model covering OAuth scopes/roles, subscription keys, and backend resource authorization.
- [ ] Define secrets/certificates policy using Key Vault/managed identity where appropriate.
- [ ] Manage the APIM instance/resources via IaC or a clear source of truth.

### 22.2. Before publishing

- [ ] Validate OpenAPI and the mapping of public suffix + operation path + backend route.
- [ ] Validate XML policies; confirm effective policies inherit `<base />` properly.
- [ ] Test missing/invalid JWT, issuer/audience, wrong role/scope, and subscription key.
- [ ] Test each sensitive operation to ensure no product unintentionally over-grants access.
- [ ] Verify CORS and caching without cross-tenant data leakage.
- [ ] Verify product visibility, group access, and approval/subscription scope.
- [ ] Confirm developer portal docs clearly cover auth/limits/errors/deprecation/support.
- [ ] Test backend private endpoint/DNS/route/TLS/identity from the gateway.
- [ ] Enforce rate limits/quotas by verified identity, not solely NAT IP.
- [ ] Confirm log redaction, alert owners, tracing, and SLO monitoring are active.
- [ ] Obtain production approval, rollback path, and compatible data migration plan.

### 22.3. After publishing

- [ ] Verify 2xx requests from valid consumers at both gateway and backend.
- [ ] Confirm negative tests (401/403/429) and resource-level authorization still pass.
- [ ] Monitor error rates, p95/p99, backend latency, and quotas per API/product/version.
- [ ] Issue subscriptions/keys per consumer with rotation and revocation processes.
- [ ] Confirm no public backend bypass path or misconfigured origin policy exists.
- [ ] Track certificate/secret expirations, JWT discovery/issuer settings, and logs.
- [ ] Record deployment commit, API revision/version, and change record.
- [ ] Review usage/cost, API deprecation, and unused subscriptions.

### 22.4. During an incident

- [ ] Freeze promotions; record API/operation/version, timestamp, and correlation ID.
- [ ] Distinguish 401/403/404/429/5xx originating from APIM vs. backend; never disable security arbitrarily.
- [ ] Compare effective policy, backend route, Azure Activity Log, and recent CI diffs.
- [ ] If it is a config error, revert to an approved policy/revision and update the source of truth.
- [ ] If it is a backend/DB error, trigger application/data runbooks rather than only changing the gateway.
- [ ] Re-test valid tokens, wrong-audience tokens, under-scoped consumers, and business cases.
- [ ] Document the incident, consumer impact, recovery time, and preventive actions.

## 23. Safe lab cleanup

APIM instances and networking/logging resources can continue incurring charges even with zero requests. Before deleting:

1. Confirm the exact subscription/resource group.
2. List the APIM instance, custom domains, identities, Key Vault, private endpoints, Log Analytics, and related backends.
3. Check whether the resource group contains apps/resources shared with other teams.
4. Verify whether test products/subscriptions are actively used by any real consumer.
5. Save any required logs/evidence per policy; never save keys/tokens.
6. Delete **only a resource group dedicated 100% to the lab** with owner approval.

~~~bash
az account show --query "{id:id,name:name}" --output table

az resource list \
  --resource-group "$RESOURCE_GROUP" \
  --output table

# Deletion example for reference only, DO NOT run blindly.
# Use only if the RG is 100% dedicated to the lab and approved:
# az group delete --name "$RESOURCE_GROUP" --yes
~~~

If the APIM lab lives in a shared RG, **selectively delete the exact resources** instead of deleting the whole RG. Deleting an instance affects all APIs, products, developer portal, subscriptions, and gateway endpoints within it. Before deleting, confirm no clients rely on it and comply with retention/audit requirements.

**Do not delete a Key Vault, storage account, or network resource just because it was created on the same day as APIM.** Base cleanup strictly on ownership and actual resource dependencies.

## 24. Key takeaways

**Azure API Management** is an API governance and publishing layer comprising **gateway, management, developer portal, policies, and observability**. Good design starts with the API contract and consumer needs, before configuring URLs and products in the Portal.

Core points:

1. **Organize APIs by domain:** API → operations; products bundle API offerings, groups/subscriptions manage onboarding and usage; product membership does not automatically restrict individual HTTP operations.
2. **Versions and revisions differ:** versions handle incompatible contracts; revisions fit non-breaking changes within the same API/version.
3. **Policies have scope and order:** inbound/backend/outbound/on-error; `<base />` controls inheritance from higher scopes, so always review the effective policy.
4. **Keys differ from tokens:** APIM subscription keys manage subscriptions/usage and do not replace OAuth/JWT user identity or backend resource authorization.
5. **Managed identity for backends:** APIM can acquire tokens to call backends securely, but it does not automatically act on behalf of the end user.
6. **Networking spans multiple hops:** client → gateway and gateway → backend are separate flows; private DNS/VNet/networking must match the APIM SKU/tier.
7. **Documentation and onboarding:** OpenAPI, developer portal, products, subscription approval, rate limits, and error models must align.
8. **Operate from a source of truth:** IaC/CI/CD, negative tests, diagnostics, correlation, SLOs, and controlled policy/revision rollbacks.
9. **APIM does not replace business logic/DR:** backends, databases, credentials, data, and recovery architecture must still be protected.
10. **FinOps:** costs depend on gateway tier/capacity, networking, monitoring, and backends; choose based on actual requirements and avoid leaving unused lab APIM instances running.

Do not stop at asking **“Has the API appeared in APIM yet?”**. An API is truly ready only when consumers find the right contract, call it over a secure hostname, are accurately authenticated and authorized, the backend meets SLOs, versions have a clear change path, and operations have the evidence needed to diagnose and recover from failures.
