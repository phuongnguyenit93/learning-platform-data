# Designing OpenAPI Contracts for APIs on GCP

A retail system has `orders-api` running on **Cloud Run**, workers on **GKE**, and order data in **Cloud SQL**. Websites, mobile apps, and partners all need to create or look up orders. If each team interprets the JSON structure, error codes, and authentication mechanisms on its own, small backend changes can break many clients. **API-first design with OpenAPI** solves this with a versioned contract that can be reviewed and tested **before** deployment.

This lesson belongs to the **API Gateway and Apigee** chapter in the **CLOUD_PROVIDERS_GCP** module. It focuses on designing OpenAPI contracts for APIs on Google Cloud, usable with **API Gateway** or **Apigee**, while clearly distinguishing between *documentation describing the API interface* and *controls actually enforced* at the gateway, proxy, and application layers.

## 1. Objectives and Architecture Overview

After this lesson, you can:

1. Design resources, paths, methods, requests/responses, errors, pagination, and versioning with OpenAPI.
2. Write a practical **OpenAPI 3.0.x** spec with request/response examples, reusable schemas, and security descriptions.
3. Integrate **API Gateway** with a Cloud Run backend using `x-google-*` extensions matching the OpenAPI version.
4. Distinguish between **client JWT**, **gateway backend-caller identity**, and **user business authorization**.
5. Understand when you need an **Apigee API proxy**, policy validation, quota, authentication, and analytics.
6. Bring linting, contract tests, compatibility checks, and API config releases into CI/CD.
7. Identify contract errors, routing errors, auth issues, and key metrics to monitor.

~~~mermaid
flowchart LR
    C["Web / mobile / partner"] --> GW["API Gateway or Apigee proxy"]
    GW --> API["Cloud Run: orders-api"]
    API --> DB["Cloud SQL"]
    API --> PUB["Pub/Sub"]
    OAS["OpenAPI contract: paths, schemas, errors"] -. "Defines expected behavior" .-> C
    OAS -. "Configures gateway / proxy" .-> GW
    OAS -. "Contract tests" .-> API
    IAM["IAM + JWT + backend auth"] -. "Protects each boundary" .-> GW
~~~

**Key point:** OpenAPI describes how clients and servers should communicate. It **does not automatically** create databases, enforce per-order authorization, guarantee schema validation, or enable rate limits on every gateway.

## 2. What Must an API Contract Define?

### 2.1. Layers of API-First

| Layer | What to Align On | Example |
| --- | --- | --- |
| **Resource** | Name, path, HTTP method, semantics. | `POST /v1/orders`, `GET /v1/orders/{orderId}`. |
| **Representation** | JSON schema, required/optional fields, types, examples. | `quantity` is an integer greater than or equal to 1. |
| **HTTP behavior** | Status codes, headers, retries, idempotency. | Creating an order returns `201` and `Location`. |
| **Security** | Credential mechanism, permission scopes, identity. | Bearer JWT; backend checks order owner. |
| **Reliability** | Timeouts, error handling, pagination, load limits. | `429` includes `Retry-After` when appropriate. |
| **Evolution** | Versioning, backward-compatible changes, deprecation. | Keep `/v1`, do not change a field's meaning. |
| **Operations** | `operationId`, tags, trace/correlation ID, monitoring. | `createOrder`, `getOrder`. |

A YAML file that only declares paths and returns `200` for every case is **not sufficient** as a contract for production clients. Start from **business semantics**, then choose fields and encoding.

### 2.2. Do Not Confuse Schema with Business Rules

A schema can require `quantity >= 1`, but it cannot by itself prove the user is allowed to buy that product or view someone else's order. Likewise, a valid JWT does not mean the caller can modify every order.

~~~text
1. Client sends credentials and request.
2. Gateway/proxy checks configured policies.
3. Backend verifies the trust context and enforces business authorization.
4. Backend validates payload, updates data, and returns a contract-compliant response.
~~~

You must separate **authentication (who is calling)**, **authorization (what they are allowed to do)**, and **validation (whether the data is valid)**.

## 3. Choosing the OpenAPI Version and GCP Service

### 3.1. Support Status to Know

Per Google Cloud documentation verified in **11/2026**, API Gateway supports **OpenAPI 2.0, 3.0.x, and 3.1.x**. Older examples referencing only Swagger 2.0 no longer describe full current capabilities. API Gateway has **specific limitations** on certain OpenAPI 3.x features, so *uploading successfully* does not mean every keyword is enforced. [API Gateway documentation](https://cloud.google.com/api-gateway/docs/openapi-overview).

| Criterion | API Gateway | Apigee |
| --- | --- | --- |
| Role | Managed gateway for APIs/backends on Google Cloud. | API management platform with API proxies, policies, and analytics. |
| OpenAPI | Can use OAS 2.0/3.0.x/3.1.x per current support. | Can import OAS to create a proxy; **OASValidation policy** documentation supports OAS 3.0. |
| Routing | Backend declared via `x-google-*` extensions. | Proxy endpoint/target endpoint and flows/policies. |
| Security | API key/JWT per API config; separate backend auth. | VerifyAPIKey, VerifyJWT/OAuthV2, other policies if configured. |
| Validation | Does not automatically validate the entire request body just because a schema exists. | Can add **OASValidation policy**; must attach the policy and understand what parts are checked. |
| Operations | API configs, gateway deployments, metrics/quotas. | API proxy revisions, environments, API products, analytics, and policies. |

Service selection must be driven by features, governance level, security requirements, deployment complexity, and **cost**. Do not choose Apigee merely to display Swagger UI, and do not assume API Gateway has every customizable policy that Apigee offers.

### 3.2. Why Does the Example Use OpenAPI 3.0.3?

OpenAPI 3.0.3 provides clear `components.schemas`, `requestBody`, `content`, and security schemes. It is a solid baseline to share across client/backend teams and to test with Apigee OASValidation 3.0. When using **OAS 3.1**, additionally verify JSON Schema handling across tools, SDK generators, gateways, and proxy policies.

In OAS 2.0, fields such as `swagger`, `definitions`, `securityDefinitions`, `consumes`, `produces`, and how `x-google-backend` is declared **differ** from OAS 3.x. Do not copy OAS 2.0 extensions verbatim into OAS 3.x and expect the gateway to accept them properly.

## 4. Designing the Orders Resource

### 4.1. Paths and HTTP Semantics

Assume `orders-api` serves:

| Operation | URL | Success | Notes |
| --- | --- | --- | --- |
| Create order | `POST /v1/orders` | `201 Created` | `Idempotency-Key` helps prevent duplicate creation on retries. |
| Get order | `GET /v1/orders/{orderId}` | `200 OK` | Return only orders the caller is authorized to view. |
| Not found | `GET /v1/orders/{orderId}` | `404 Not Found` | Can be used to avoid leaking existence of other users' orders. |
| Invalid request | Varies by operation | `400` or `422` per agreed convention. | Standardize error shape; do not return internal messages. |
| Rate limiting | Varies by operation | `429 Too Many Requests` | When a limiting policy exists, consider `Retry-After`. |

`GET` must not mutate business state. `POST` can produce side effects; retries are only safe when the backend supports idempotency. `Idempotency-Key` is an **application convention declared in the contract**, not a built-in feature of OpenAPI or API Gateway.

### 4.2. Fields, Pricing Calculation, and Sensitive Data

Example request:

~~~json
{
  "items": [
    {"sku": "SKU-1001", "quantity": 2}
  ],
  "currency": "VND"
}
~~~

Never let the client decide the `totalPrice` to pay: the backend must look up valid prices, compute the total, and create the order inside a transaction. When representing money, prefer **integers in the currency's minor unit**, avoiding floating-point inaccuracies and clarifying rounding rules (VND currently has no fractional subunit in standard units).

A response can expose `orderId`, `status`, `totalMinor`, and `createdAt`, but **must not** expose payment tokens, passwords, Cloud SQL credentials, or unnecessary personal data.

## 5. OpenAPI 3.0.3 Example Ready for API Gateway Integration

The document below is written as an example file `openapi-orders.yaml`. The URLs `example.invalid` and `REPLACE_WITH_CLOUD_RUN_URL` are **intentional placeholders** that must be replaced with your actual JWT provider and Cloud Run service before creating an API config. Source code in this lesson section **does not create external files** outside the assigned Markdown file.

~~~yaml
openapi: 3.0.3
info:
  title: Retail Orders API
  version: 1.0.0
  description: Contract for creating and querying orders.

# Google API Gateway specific configuration for OpenAPI 3.x.
x-google-api-management:
  backends:
    orders-backend:
      address: https://REPLACE_WITH_CLOUD_RUN_URL
      jwtAudience: https://REPLACE_WITH_CLOUD_RUN_URL
      pathTranslation: APPEND_PATH_TO_ADDRESS
      deadline: 30.0
x-google-backend: orders-backend

# Default protection; avoid accidentally exposing an operation publicly.
security:
  - CustomerJwt: []

paths:
  /v1/orders:
    post:
      tags: [Orders]
      summary: Create an order
      operationId: createOrder
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          description: Stable key across retries of the same operation.
          schema:
            type: string
            minLength: 8
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Order created.
          headers:
            Location:
              description: URL of the newly created order.
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '409':
          description: Idempotency key conflicts with a different payload.
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '429':
          $ref: '#/components/responses/TooManyRequests'

  /v1/orders/{orderId}:
    get:
      tags: [Orders]
      summary: Get a single order
      operationId: getOrder
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            pattern: '^[A-Za-z0-9_-]{8,64}$'
      responses:
        '200':
          description: Authorized order details.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '404':
          description: Not found or not disclosed.
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'

components:
  securitySchemes:
    CustomerJwt:
      type: oauth2
      flows:
        implicit:
          authorizationUrl: https://idp.example.invalid/authorize
          scopes: {}
      x-google-auth:
        issuer: https://idp.example.invalid/
        jwksUri: https://idp.example.invalid/.well-known/jwks.json
        audiences: [retail-orders-client]
        jwtLocations:
          - header: Authorization
            valuePrefix: 'Bearer '

  schemas:
    OrderItem:
      type: object
      additionalProperties: false
      required: [sku, quantity]
      properties:
        sku:
          type: string
          minLength: 1
          maxLength: 64
        quantity:
          type: integer
          minimum: 1
          maximum: 100
    CreateOrderRequest:
      type: object
      additionalProperties: false
      required: [items, currency]
      properties:
        items:
          type: array
          minItems: 1
          maxItems: 50
          items:
            $ref: '#/components/schemas/OrderItem'
        currency:
          type: string
          enum: [VND]
    Order:
      type: object
      required: [orderId, status, currency, totalMinor, createdAt]
      properties:
        orderId:
          type: string
        status:
          type: string
          enum: [PENDING, CONFIRMED, CANCELLED]
        currency:
          type: string
          example: VND
        totalMinor:
          type: integer
          format: int64
          minimum: 0
        createdAt:
          type: string
          format: date-time
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        requestId:
          type: string

  responses:
    BadRequest:
      description: Invalid request.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    Unauthorized:
      description: Invalid or missing credentials.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    TooManyRequests:
      description: Request limit exceeded.
      headers:
        Retry-After:
          description: Retry delay if provided.
          schema:
            type: string
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
~~~

**Understanding the nature of this example accurately:**

- `components.schemas` describes payloads in OpenAPI 3.0, while **the backend must still validate requests**. API Gateway accepts the schema but does not enforce all constraints such as `minLength`, `pattern`, `required`, or JSON body validation.
- The listed responses represent **the contract the backend should implement**. Errors generated by the gateway/proxy itself may have bodies/headers **different** from `Problem`; test and normalize through an appropriate layer if the public API requires a uniform error envelope.
- `CustomerJwt` is an example using a JWT provider configured via **Google `x-google-auth`**. Issuer, JWKS, and audience values must come from a real IdP; `example.invalid` **is not a working endpoint**.
- `flows.implicit` in the security scheme sample reflects **how JWT is declared in API Gateway documentation**, **not a recommendation to use OAuth implicit grant for new applications**. For browser/mobile apps, consider Authorization Code + PKCE per your IdP; API Gateway validates the received JWT using the configured issuer/JWKS/audience.
- `x-google-api-management` and `x-google-backend` **are not standard OpenAPI keywords**. They are adapters for API Gateway; the contract parts like `paths`/`schemas` can still be used with other tools.
- The name `orders-backend` must match between the backend map and `x-google-backend`. When using OpenAPI 3.x, do not put the backend URL directly into `x-google-backend` as in OAS 2.0 examples.

## 6. Explaining Common Pitfalls in the Contract

### 6.1. `operationId`, Reusable Schemas, and Examples

`operationId` should be unique, stable, and readable such as `createOrder` or `getOrder`, because SDK generators and contract tests may depend on it. `$ref` enables reusing schemas/responses, avoiding each endpoint defining `Order` inconsistently.

In CI, check that:

- Every path parameter `{orderId}` is declared with `in: path`, `required: true`.
- `201`, `400`, `401`, `404`, `409`, `429` match business logic; do not document `200` when the backend routinely returns `201`.
- `application/json` and `application/problem+json` are used consistently.
- No sensitive fields appear in responses; optional/required reflects **actual data**.
- `example`/`examples` do not contain real API keys, JWTs, emails, or real orders.

An OpenAPI document that is valid YAML but defines wrong business semantics is still a poor contract. Product and API consumer reviews are as important as schema linting.

### 6.2. Idempotency and HTTP Retries

For `POST /v1/orders`, persist `Idempotency-Key` together with a payload fingerprint and the result in durable storage for a published retention window:

~~~text
Client POST key=A, body=X
  → backend creates order #100, stores result, returns 201.

Client retry key=A, body=X
  → backend returns the same stored result per policy.

Client POST key=A, body=Y
  → backend returns 409 because the key is already bound to a different body.
~~~

Merely **declaring the header in OpenAPI does not make retries safe**. You need proper transactions/unique constraints/locking; when Cloud Run scales across multiple instances, instance memory is not a reliable store for idempotency keys.

### 6.3. Pagination and Filtering as the API Grows

If `GET /v1/orders` is added later, specify `pageSize`, `pageToken`, sort order, maximum limit, and response `nextPageToken`. Treat the page token as opaque data so clients do not depend on internal token structure. Do not add pagination yet return an unbounded array, which easily increases latency and Cloud SQL load.

## 7. Two Security Boundaries in API Gateway

### 7.1. Client → Gateway: A JWT Is Not Permission to View an Order

`components.securitySchemes.CustomerJwt` with `x-google-auth` instructs API Gateway to verify the **issuer, JWKS/signature, audience, and token expiration** when properly configured. Afterward, the backend must still verify whether the user is authorized to view the specific `orderId`.

**API Gateway does not enforce OAuth scopes in OpenAPI** per current limitation docs. Do not treat `scopes: {read: ...}` in the contract as sufficient to lock down business operations. Actual roles/permissions must be enforced by the application or a supported policy.

In OpenAPI terms:

~~~yaml
# AND: two schemes within the same security requirement object.
security:
  - CustomerJwt: []
    ClientApiKey: []

# OR: multiple security requirement objects (check product limitations).
# security:
#   - CustomerJwt: []
#   - ClientApiKey: []
~~~

**API Gateway has limitations on scheme combinations**: it can require a JWT **and** an API key, but does not support every OR combination between an API key and other schemes; OAuth schemes also have restrictions. An API key is useful for identifying a project/consumer, tracking, or applying quotas, **not as a replacement for user authentication**. When using `ClientApiKey`, you must define `components.securitySchemes.ClientApiKey` and test before deploying; the snippet above only explains AND/OR logic, **not a standalone YAML file**.

### 7.2. Gateway → Cloud Run: Backend Identity Differs from User JWT

When API Gateway calls a Cloud Run service with **authentication required**, the gateway needs a **backend-auth service account** granted `roles/run.invoker` on the Cloud Run service. The API config specifies this SA at creation time; the gateway mints an ID token matching the backend audience (`jwtAudience`).

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant R as Cloud Run backend
    participant D as Cloud SQL
    C->>G: User's Bearer JWT
    G->>G: Verify issuer / signature / audience
    G->>R: Authorization: ID token of gateway SA
    Note over G,R: Client claim info forwarded via gateway header per docs
    R->>R: Check permission to view / create order
    R->>D: Query using runtime identity / DB auth
    D-->>R: Data
    R-->>C: Response via gateway
~~~

API Gateway can **replace the `Authorization` header before sending to the backend** when using backend authentication. Verified client authentication info is passed via the **`X-Apigateway-Api-Userinfo`** header per the service mechanism. Do not assume the backend always receives the raw user JWT in `Authorization`.

**Never trust headers sent directly by any client.** To trust identity context from the gateway, protect the path to the backend (grant Cloud Run Invoker only to the exact gateway SA, control ingress, and block bypass paths), verify audience/issuer according to the appropriate model, and apply least privilege to the application.

### 7.3. The Third Runtime Identity

The Cloud Run runtime service account accessing **Cloud SQL, Cloud Storage, Pub/Sub, or Secret Manager** is a **different** identity from the backend-auth SA used to invoke Cloud Run. Granting `roles/run.invoker` to the gateway SA **does not** grant backend code access to read data, or vice versa.

## 8. Google API Gateway Specifics

### 8.1. Backend Routing and Path Translation

In OAS 3.x, declare:

~~~yaml
x-google-api-management:
  backends:
    orders-backend:
      address: https://REPLACE_WITH_CLOUD_RUN_URL
      jwtAudience: https://REPLACE_WITH_CLOUD_RUN_URL
      pathTranslation: APPEND_PATH_TO_ADDRESS
x-google-backend: orders-backend
~~~

Here:

- `address` is the HTTPS backend endpoint.
- `jwtAudience` is used when the gateway needs an ID token to call the backend; for Cloud Run this is typically the base service URL accepted by the backend.
- `pathTranslation: APPEND_PATH_TO_ADDRESS` preserves the request path when forwarding, provided the backend path is configured accordingly.
- If you place the backend at the **operation** level instead of root and omit `pathTranslation`, the default behavior may differ (`CONSTANT_ADDRESS`); verify to avoid breaking `/v1/orders/{orderId}`.

OpenAPI 3.x uses `x-google-api-management.backends` and **`x-google-backend` referencing the backend name**, which differs from OAS 2.0 syntax. The documentation also covers other extensions for quotas, auth, and endpoints; only add them once you understand compatibility and impact.

### 8.2. API Config Is a Versioned Artifact

With API Gateway, **do not edit the OpenAPI content of an existing API config in place**. Each time you publish a new contract/config version, create a **new API config**, then update the gateway to point to it. When updating multiple gateways/regions, roll out and verify each gateway; for a period, old and new configs may serve traffic concurrently.

For OAS 3.x, `servers` options have limitations: API Gateway treats a server with `x-google-endpoint` as the configured server; it does not automatically use every server URL the way mock or API client tools do. In particular, **`x-google-allow` from OAS 2.0 is not supported in OAS 3.x**. Accepted path/parameter keywords also have limits; inspect errors when creating the API config.

### 8.3. Descriptive Schema vs. Enforcement

API Gateway may **accept** `required`, `minimum`, `pattern`, and JSON request body schemas, yet **does not automatically enforce all of those constraints**. Therefore:

- The Cloud Run backend must validate payloads and return errors per the contract.
- Configuring `security`/JWT at the gateway is a **separate** enforcement mechanism and does not imply application data validation.
- Declaring `429` in `responses` **does not create a quota/rate-limit policy**.
- CORS and request options must be properly configured at the gateway/backend; `servers` or `responses` do not automatically enable CORS for browsers.

## 9. Illustrative Deployment Workflow on API Gateway

The following example assumes the **Cloud Run service `orders-api` is already deployed**, running in the selected region with authentication required, and the backend SA already exists. Commands containing `create`, `add-iam-policy-binding`, `update`, or `enable` are **write operations that may incur charges**. Only run in an authorized lab project. This exercise does not create OpenAPI files in this workspace; when practicing, save section 5's content as `openapi-orders.yaml` in a separate test directory and **replace the placeholders**.

### 9.1. Choose a Supported Region

~~~bash
PROJECT_ID="retail-lab"
API_ID="retail-orders"
CONFIG_ID="orders-config-v1"
GATEWAY_ID="retail-orders-gw"
GATEWAY_REGION="us-central1"
BACKEND_SA="api-gateway-invoker@retail-lab.iam.gserviceaccount.com"
BACKEND_REGION="us-central1"
~~~

API Gateway regions **do not match every Cloud Run region**. The example uses `us-central1`, a **gateway location listed in Google Cloud guidance**; do not assume a gateway is available in every region such as `asia-southeast1`. Select a supported location, latency profile, data residency, and network transfer path before going to production.

### 9.2. Grant Backend Invocation Permission

~~~bash
# WRITE: gateway SA is only allowed to invoke the specified backend service.
gcloud run services add-iam-policy-binding orders-api \
  --project="$PROJECT_ID" \
  --region="$BACKEND_REGION" \
  --member="serviceAccount:$BACKEND_SA" \
  --role="roles/run.invoker"

# READ-ONLY: inspect backend IAM.
gcloud run services get-iam-policy orders-api \
  --project="$PROJECT_ID" \
  --region="$BACKEND_REGION"
~~~

The deployer creating the API config may need `roles/iam.serviceAccountUser` or `iam.serviceAccounts.actAs` permission on the gateway SA, in addition to permissions to create APIs/configs/gateways. Do not grant Owner to the entire team just to create a config.

### 9.3. Create the API Config

~~~bash
# READ-ONLY: check project and CLI.
gcloud config get-value project
gcloud --version

# WRITE: API ID can be created together with the config if it does not yet exist.
gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api="$API_ID" \
  --openapi-spec=openapi-orders.yaml \
  --project="$PROJECT_ID" \
  --backend-auth-service-account="$BACKEND_SA"

# READ-ONLY: verify config and status.
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" \
  --project="$PROJECT_ID"
~~~

Before this step, you must enable the **Google Cloud APIs required by API Gateway**, prepare IAM permissions/service agents, update `gcloud` to support OAS 3.x, and complete the corresponding **enable managed service** step per API Gateway documentation. Creating the config alone is not enough to prove clients can call the API: gateway deployment and backend permissions are still required.

### 9.4. Create the Gateway and Read the Hostname

~~~bash
# WRITE: incurs gateway charges per product pricing; run after reviewing the config.
gcloud api-gateway gateways create "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="$CONFIG_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID"

# READ-ONLY: inspect the gateway-assigned hostname.
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID" \
  --format="yaml(defaultHostname,state,apiConfig)"
~~~

The gateway is assigned a hostname (typically under the `gateway.dev` domain in newer deployments). The client URL is `https://<defaultHostname>/v1/orders/...`—**do not use the Cloud Run backend URL** if you want requests to pass through the gateway. If a custom domain is needed, evaluate load balancing/DNS/TLS resources and supported models.

### 9.5. Test with a Valid JWT

~~~bash
# READ/REQUEST: these values must be provided by a real system.
GATEWAY_URL="https://REPLACE_WITH_GATEWAY_HOSTNAME"
JWT="REPLACE_WITH_VALID_JWT_FROM_IDP"

# Inspect HTTP status and response.
curl -i \
  -H "Authorization: Bearer $JWT" \
  "$GATEWAY_URL/v1/orders/ORDER1234"
~~~

The example token **cannot be used as-is**: you must obtain a JWT from the actual IdP with a valid `iss`, `aud`, signature, and expiration. Never record tokens in shell history, logs, or issue trackers; in real scripts, use a secure token-retrieval workflow. Also test missing tokens, expired tokens, invalid `orderId`, and users lacking permission to view the order.

## 10. Using the Same Contract in Apigee

### 10.1. Importing OpenAPI Does Not Automatically Enable Policies

Apigee lets you generate an **API proxy from an OpenAPI Specification**, then add flows, targets, and policies. To validate requests/responses against OAS 3.0, there is the **`OASValidation` policy**; the spec is stored as a resource inside the API proxy bundle, such as `apiproxy/resources/oas/orders.yaml`, and the policy must be **attached to the appropriate flow**.

~~~mermaid
flowchart LR
    C["Client"] --> P["Apigee API proxy"]
    P --> V["VerifyJWT / VerifyAPIKey / OAuthV2"]
    V --> Q["Quota / SpikeArrest"]
    Q --> O["OASValidation (if attached to flow)"]
    O --> T["TargetEndpoint → Cloud Run / GKE"]
    T --> R["Response + analytics"]
~~~

The diagram illustrates **policies that can be used**, without claiming this exact ordering suits every proxy. Apigee OASValidation has defined scope and limits on which request/response elements it checks; if not attached, an OpenAPI schema **does not automatically block malformed payloads**. Always test policy flows, errors, latency impact, and path/basepath mapping rules before production.

### 10.2. What to Omit When Using Apigee?

Standard fields `openapi`, `info`, `paths`, `components`, and security descriptions are the reusable contract portion. With Apigee:

- Do not copy API Gateway's `x-google-api-management`/`x-google-backend` as if they automatically build an Apigee TargetEndpoint.
- Configure proxy basepath, target, virtual host/environment group, and deployment per Apigee.
- Attach **VerifyJWT/VerifyAPIKey/OAuthV2**, quota, and OASValidation policies as planned.
- Define API products/developer apps if the API distribution model requires them.
- Verify upstream identity to Cloud Run and protect the backend so it cannot be called directly bypassing the proxy.

You can maintain a **canonical OpenAPI contract** plus a layer of **deployment overlays** for Gateway/Apigee. This reduces duplication of paths/schemas while keeping infrastructure-specific controls clearly separated.

### 10.3. When to Use API Gateway vs. When to Use Apigee?

If you only need a few REST endpoints, basic routing/auth on Google Cloud, and simple deployment, API Gateway is usually worth considering first. If the organization needs multiple API products, rich policies, analytics, developer onboarding, or cross-team API governance, evaluate Apigee. Base the decision on **actual requirements, product limits, deployment locations, SLOs, and total cost**, not merely endpoint count.

## 11. Contract Testing and CI/CD Automation

### 11.1. Four Testing Layers

1. **Syntax/lint:** valid YAML, valid `$ref`, unique `operationId`, valid path parameters, and no sensitive content.
2. **Semantic review:** sensible HTTP statuses, optional/required fields, money units, pagination, versioning, and error semantics.
3. **Contract tests:** do actual Cloud Run requests/responses match the schema? Test valid payloads, invalid payloads, boundary values, and authorization.
4. **Gateway/proxy integration:** JWT/API key policies, backend IAM, path translation, timeouts, header propagation, quota/rate limits, and analytics behave as designed.

Example lint command inside **a practice directory containing the OpenAPI file**, requiring Node.js and a version-pinned CLI:

~~~bash
# READ/LOCAL VALIDATION: lint the spec without modifying GCP resources.
npx @redocly/cli lint openapi-orders.yaml
~~~

Do not treat a lint command as proof that API Gateway/Apigee **will enforce the full schema**. In addition, when publishing an API config, run the product's own validation step because extensions and supported features have specific limits.

### 11.2. Minimum Contract Tests

| Scenario | Request | Expectation |
| --- | --- | --- |
| Valid lookup | `GET /v1/orders/ORDER1234` with authorized JWT | `200`, JSON matches `Order` schema. |
| Unauthenticated | No `Authorization` sent | `401` or authentication error per configured gateway. |
| Unauthorized view | Valid JWT, but order belongs to someone else | No data leak; `403`/`404` per agreed policy. |
| Valid creation | `POST /v1/orders` + valid body + `Idempotency-Key` | `201`, `Location`, order JSON matches contract. |
| Invalid quantity | `quantity: 0` | Validation error per contract; backend does not persist order. |
| Retry same key | Two POSTs with same key/payload | Single order; response follows idempotency policy. |
| Key conflict | Same key with different payload | `409`; no second order created. |
| Rate limited | Exceeds actually configured quota | `429` if product/policy applies; observe `Retry-After` if present. |

Each test must verify **HTTP code + headers + JSON shape + side effects**, not just returned text. For authorization, test IDOR cases: user A guesses user B's order ID, and the backend still denies access.

### 11.3. Reference Pipeline

~~~mermaid
flowchart LR
    G["PR: edit OpenAPI"] --> L["Lint + semantic review"]
    L --> D["Breaking-change diff"]
    D --> M["Mock / client SDK test"]
    M --> B["Backend contract tests"]
    B --> S["Staging API Gateway/Apigee"]
    S --> E["JWT/IAM/routing/SLO tests"]
    E --> A["Approval"]
    A --> P["Publish config/proxy revision"]
    P --> O["Monitoring + rollback"]
~~~

To support rollback, keep **the built OpenAPI artifact, API config ID/proxy revision, Cloud Run image digest, IAM state, and database migrations**. When updating a gateway config, it may serve both old and new configs for a period; never assume changes take effect atomically everywhere.

## 12. Versioning and Managing Breaking Changes

| Change | Compatibility | Strategy |
| --- | --- | --- |
| Add optional response field | Usually compatible with tolerant clients. | Test older clients, document field. |
| Add a new operation | Usually does not break existing consumers. | Check routes, auth, and policies. |
| Make an optional field required | **Breaking** for clients sending old requests. | New version or migration with transition period. |
| Change `orderId` type from string to integer | **Breaking** for SDKs/clients. | Keep old contract, create v2 if needed. |
| Remove an active enum value | Can break server/client state handling. | Deprecation, compatibility tests, timeline. |
| Change HTTP 200 to 201 on existing operation | Can break client logic. | Assess impact and release with versioning. |
| Change JWT issuer/audience | Alters security contract; can block clients. | Staged IdP/token transition, test in staging. |

Manage all four identifiers:

- **`info.version`**: document/contract version, e.g., `1.1.0`.
- **Path major version**: e.g., `/v1` and `/v2` for incompatible changes.
- **API config/proxy revision**: infrastructure deployment artifact, which can update without changing the public API version.
- **Backend release**: image digest/revision, independent of API config name.

Not every doc edit requires `/v2`; however, **never alter the semantics of a v1 endpoint** without a migration path and consumer notice.

## 13. Security, SLOs, and Cost

### 13.1. Security by Boundary

| Boundary | Controls |
| --- | --- |
| Client → gateway | HTTPS, JWT/API key per policy, quota, WAF/Cloud Armor if topology supports it. |
| Gateway → Cloud Run | Backend-auth SA has `roles/run.invoker`, correct audience, no open backend bypass. |
| Cloud Run → Cloud SQL/Storage | Runtime SA, database authentication, VPC/private connectivity, Secrets. |
| Contract → CI | Reviews, linting, PII leak prevention, security diffs, and auditing. |

Never use an API key to prove user identity or determine which orders a caller may read. Never rely solely on claim headers if the backend still has uncontrolled direct access paths.

### 13.2. Metrics to Measure

- **Client SLIs:** 2xx/4xx/5xx rates, p50/p95/p99 latency, checkout success rate.
- **Gateway/proxy:** auth failures, quota rejections, upstream status, request count, routing/config errors.
- **Backend:** Cloud Run startup/instance metrics, errors/timeouts, SQL connection pool, and query latency.
- **Cost:** requests processed via gateway/Apigee, Cloud Run CPU/memory, database load, Cloud Logging/Monitoring, data transfer, and load balancing.

A clean contract **does not guarantee an SLO**: it still depends on capacity, timeouts, retries, transactions, databases, and release practices. A `429` can indicate an active safeguard working as intended, not necessarily an application bug.

## 14. Troubleshooting

| Symptom | Possible Cause | Check First |
| --- | --- | --- |
| API config creation rejected | Invalid OAS schema, wrong `x-google-*`, outdated CLI, or unsupported reference. | Lint, OAS version/extensions docs, API config error message. |
| `404` from gateway | Path/method undeclared, wrong basepath/path translation. | `paths`, `servers`, gateway config, and backend routes. |
| `401` before backend | Wrong JWT issuer/audience/signature, expired, or missing header. | `security`, `x-google-auth`, IdP JWKS, and token claims. |
| `403` when gateway calls Cloud Run | Backend-auth SA lacks `roles/run.invoker` or audience mismatch. | Backend IAM, `jwtAudience`, gateway API config SA. |
| `403` from application | Caller authenticated but lacks permission on the order. | Authorization/ownership logic and app audit logs. |
| `400` not matching contract format | Gateway/backend returned its own error; response not normalized. | Identify which layer generated the error and the error envelope contract. |
| `POST` creates duplicate orders | `Idempotency-Key` not enforced in the backend. | Transaction/idempotency store, retry traces. |
| `422` not returned for invalid payload | Gateway accepts schema without validating every field. | Backend validators / Apigee OASValidation policy tests. |
| `429` never triggers despite being documented | `responses` is descriptive; no quota/rate policy configured. | API Gateway quota or Apigee SpikeArrest/Quota. |
| p95 increases after deployment | Backend cold start, slow Cloud SQL, heavy proxy policy, or timeouts. | End-to-end trace across gateway/backend and Cloud Monitoring. |
| CI updated contract but gateway still serves old behavior | No new API config created / gateway not updated. | Active API config ID and gateway `apiConfig`. |

**Quick method:** locate request ID → gateway/proxy logs → authentication/authz → route/backend SA → Cloud Run logs → Cloud SQL/dependencies. Separate **gateway** errors from **backend** errors before editing schemas or IAM.

## 15. Exercises

### Exercise 1 — Contract Design

Design `GET /v1/products/{productId}` and `POST /v1/products` for a retail system. Specify `operationId`, path parameters, body schema, `200/201/400/404` responses, and JSON examples. Explain which fields the backend must validate even though OpenAPI already declares them.

### Exercise 2 — Find the Security Gaps

A team puts in OpenAPI:

~~~yaml
security:
  - CustomerJwt: []
~~~

But there is no security scheme, JWT issuer/JWKS, or proper backend IAM. List the missing layers when using API Gateway with OpenAPI 3.x, and distinguish a client `401` error from a gateway→Cloud Run `403` error.

### Exercise 3 — OAS 2.0 vs. OAS 3.x

A legacy spec uses `swagger: "2.0"` and `x-google-backend: {address: ...}`. You migrate to OAS 3.0.3. How must you update request body declarations, schema definitions, JWT extensions, and backend mapping? Why can you not copy the old extensions verbatim?

### Exercise 4 — Idempotency

A client's `POST /v1/orders` succeeds, but the connection drops before receiving the response. It retries three times with the same `Idempotency-Key`. State the rules the backend must enforce, the expected responses, and how to protect the transaction on Cloud SQL.

### Exercise 5 — Breaking Change

Version v1 returns `totalMinor` as an integer. The backend team wants to replace it with `total` as a decimal string and remove the old field. Is this change breaking? Propose a transition strategy for mobile clients that have not updated yet.

### Exercise 6 — Apigee Policy

The development team imports OAS 3.0 into Apigee, yet clients still send `quantity: 0` and the proxy forwards it to the backend. Explain why and describe how to verify the `OASValidation` policy, proxy flow, schema, and backend validation.

### Exercise 7 — Debug 404 and 403

`GET /v1/orders/ORDER1234` returns 404 at the gateway, while calling the backend directly returns 200. After fixing the path, it returns 403. Create a step-by-step checklist covering `paths`, `x-google-backend`, `pathTranslation`, backend SA, `roles/run.invoker`, and JWT audience.

### Exercise 8 — Contract Tests and Release

Propose an OpenAPI verification pipeline for a Cloud Run backend serving both GKE and mobile clients: linting, breaking-change diff, mock/SDK, staging gateway, JWT/authz, SLO, approval, and rollback. Include at least **one negative test** (unauthorized client).

## 16. Implementation Checklist and References

| Item | Pass Criterion |
| --- | --- |
| **API-first** | Resources, HTTP semantics, error model, security, pagination/versioning have owners and reviews. |
| **Schema** | Types, required/optional, examples, `$ref`, `operationId` are consistent; no secrets/PII exposed. |
| **OAS version** | OpenAPI 3.0.x/3.1.x or 2.0 aligns with gateway and tooling. |
| **Google extensions** | Syntax matches OAS version; backend URL/audience/path translation are valid. |
| **Authentication** | JWT/API key requirements are enforced; unenforced scopes are not trusted. |
| **Backend IAM** | Gateway SA has `run.invoker`; runtime identity is separate; no backend bypass. |
| **Validation** | Backend validates payloads; Apigee OASValidation works only when attached and tested. |
| **Reliability** | Idempotency, timeouts, error mapping, quotas, and retries are defined and enforced. |
| **CI/CD** | Linting, contract tests, compatibility diffs, config/proxy revisions, and rollback. |
| **Observability/cost** | Track latency, errors, quotas, logs, Cloud Run/SQL, and Billing by workload. |

Official sources to verify before implementation, as OpenAPI support and extensions may evolve:

- [OpenAPI Specification](https://spec.openapis.org/oas/v3.0.3)
- [API Gateway — OpenAPI overview](https://cloud.google.com/api-gateway/docs/openapi-overview)
- [API Gateway — OpenAPI 3.x extensions](https://cloud.google.com/api-gateway/docs/oasv3-extensions)
- [API Gateway — OpenAPI 3.x limitations](https://cloud.google.com/api-gateway/docs/openapi-v3-limitations)
- [API Gateway — Authenticate users with JWT](https://cloud.google.com/api-gateway/docs/authenticating-users-jwt)
- [API Gateway — Create an API config](https://cloud.google.com/api-gateway/docs/creating-api-config)
- [API Gateway — Deploy an API](https://cloud.google.com/api-gateway/docs/deploying-api)
- [API Gateway — Cloud Run backend](https://cloud.google.com/api-gateway/docs/get-started-cloud-run)
- [Apigee — Create proxy from OpenAPI](https://cloud.google.com/apigee/docs/api-platform/tutorials/create-api-proxy-openapi-spec)
- [Apigee — OASValidation policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/oas-validation-policy)
- [Cloud Run — Authentication](https://cloud.google.com/run/docs/authenticating/overview)

**Remember:** a good OpenAPI contract clearly specifies **what the client sends, receives, what errors occur, and how authentication works**; API Gateway/Apigee only enforce mechanisms that are **actually configured and supported**. Design API-first, use extensions matching the OAS version, protect client→gateway and gateway→backend separately, keep validation/authorization in the right layers, and test compatibility before release.
