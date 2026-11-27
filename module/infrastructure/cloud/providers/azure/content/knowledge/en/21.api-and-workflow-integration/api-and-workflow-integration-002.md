# OpenAPI Import, Versions, and Revisions in API Management

When an application system grows to have multiple customers, mobile apps, partners, and internal services sharing an API, changing an endpoint is no longer as simple as deploying new code. A seemingly minor change—renaming a JSON field, removing an operation, updating a path, or changing an authentication policy—can immediately break clients that have not upgraded yet.

**Azure API Management (APIM)** provides a gateway layer to publish and manage APIs in a controlled manner. From an **OpenAPI** specification, development teams can import operations and schemas into APIM. They can then manage **API versions** to maintain different contracts for different client groups, and **API revisions** to test, release, or roll back changes to an API without forcing every client to change URLs immediately.

In the **API and Workflow Integration** chapter of the **CLOUD_PROVIDERS_AZURE** module, this lesson connects APIM with Azure subscriptions, resource groups, Microsoft Entra ID, virtual networks, App Service/Azure Functions/AKS backends, monitoring, security, and cost control. The focus is not merely clicking the import button, but **governing the API contract lifecycle** from design, release, and compatibility through version retirement.

## 1. Learning objectives

After completing this lesson, you will be able to:

1. Explain APIM components: gateway, backend, API, operation, product, subscription, policy, and developer portal.
2. Read a basic OpenAPI document and identify the elements APIM uses during import.
3. Import OpenAPI via Azure Portal or Azure CLI into a new API, and verify operations and the backend URL.
4. Distinguish **OpenAPI info.version**, **API version set**, **API version identifier**, and **API revision**.
5. Choose a versioning scheme by URL path, HTTP header, or query string based on clients and API requirements.
6. Design backward-compatible and contract-breaking changes; decide whether to create a revision or a new version.
7. Create a non-current revision, test it via its dedicated revision address, and promote it to current in a controlled way.
8. Apply safe import practices: avoid overwriting production, verify policies, schemas, products, and authorization.
9. Plan rollback/release notes strategies, track version adoption, and deprecate/sunset old versions.
10. Diagnose import failures, duplicate routes, wrong backend URLs, 401/403/404/429/5xx errors, and version routing issues.
11. Build a production checklist, CI/CD workflow, and APIM governance using Infrastructure as Code.

CLI, YAML, and HTTP examples are **illustrative** and not executed automatically. Service names, backend URLs, versions, and subscription keys must be replaced with valid approved values when applied to a real subscription.

## 2. Where does Azure API Management sit in the architecture?

### 2.1. One API gateway, multiple backends

~~~mermaid
flowchart LR
    C1["Web / Mobile"] --> G["Azure API Management Gateway"]
    C2["Partner"] --> G
    C3["Internal Client"] --> G
    G --> P["Products / Subscriptions / Policies"]
    P --> A1["Orders API"]
    P --> A2["Payments API"]
    P --> A3["Reporting API"]
    A1 --> B1["App Service"]
    A2 --> B2["Azure Functions"]
    A3 --> B3["AKS / Container Apps"]
    G --> M["Azure Monitor / App Insights"]
~~~

Clients call the APIM **gateway endpoint**. APIM applies policies and routes requests to the configured **backend API**. The backend must still be operational and protected by its own policies; APIM does not automatically generate business logic from OpenAPI.

Example:

~~~text
Client calls:
  https://api.contoso.example/orders/42

APIM Gateway:
  identifies the API/operation from path and method
  validates subscription/identity per configuration
  applies policies: validate-jwt, rate-limit, transform...
  forwards the request to the backend URL

Backend:
  https://orders-backend.example.internal/orders/42
~~~

Domain names here are examples. In practice, APIM can use a default domain or a custom domain, and the backend URL can differ from the gateway path. If APIM is deployed with private networking, verify DNS, routing, firewalls, and the corresponding gateway exposure model.

### 2.2. Concepts to distinguish

| Concept | Role | Should not be confused with |
|---|---|---|
| APIM service | Resource managing the gateway and API configuration | A backend app |
| API | Set of operations, metadata, policies, and backend configuration | A container image/source code |
| Operation | A method + URL template and related properties | A dedicated Function/App Service that must exist per operation |
| API URL suffix/path | Path segment APIM uses to distinguish APIs | Backend URL |
| Backend | Actual service processing the request | API version set |
| Product | Group of APIs for publishing/access control | Code release |
| Subscription | Mechanism issuing keys and usage scope in APIM per configuration | Default Microsoft Entra authentication |
| Policy | Gateway rules: auth, rewrite, transform, quota, logging... | Pure OpenAPI description |
| API version | An API contract with a distinct version identifier | Revision number 2 |
| API revision | A change to an API, identified by a revision number | An independent API major version |
| Release | Record noting a revision made current and release notes | Backend code deployment |
| OpenAPI | Contract describing HTTP operations/schemas/security metadata | Automatic enforcement of all auth/policies |

### 2.3. Two operational planes

- **Management plane:** Azure Portal, Azure Resource Manager, Azure CLI/REST/IaC used to create APIs, import specs, manage versions/revisions, products, and policies.
- **Gateway/data plane:** clients send HTTP/HTTPS to the APIM gateway; the system routes requests, enforces auth/rate limit/policies, calls backends, and returns responses.

Being granted Azure RBAC permissions to edit the APIM service on the management plane **does not mean** the user can call every gateway operation as a client. Conversely, holding an APIM subscription key does not grant permission to edit API definitions in the Azure Portal.

## 3. What is OpenAPI and what does APIM import?

### 3.1. OpenAPI is an HTTP API contract

The OpenAPI Specification (OAS) is typically written in YAML or JSON and describes:

- **openapi:** OpenAPI syntax version, e.g. 3.0.3.
- **info:** name, description, contact, license, and version of the specification.
- **servers:** documented server addresses or environments.
- **paths:** list of URL paths and HTTP methods.
- **parameters:** path/query/header parameters.
- **requestBody:** required data types, schemas, and examples.
- **responses:** HTTP statuses, response bodies, and error schemas.
- **components.schemas:** reusable data models.
- **components.securitySchemes:** authentication schemes documented in the contract.
- **security:** documented security requirements at API/operation scope.

Not every OpenAPI attribute is imported or handled by APIM with the exact same semantics as the original authoring tool. APIM supports specific **OpenAPI versions and feature sets**; check the import restrictions documentation for your SKU/API type at the time of deployment.

### 3.2. Importing does not automatically create a backend

OpenAPI describes an HTTP API. Importing it into APIM can create or update API/operation configurations on the gateway, but it **does not** automatically:

- Create database tables or implement CRUD.
- Deploy an Azure Function/App Service/AKS workload.
- Generate Java/Python source code.
- Migrate data between old and new schemas.
- Grant managed identity permissions to call the backend.
- Guarantee valid JWT signatures merely because OpenAPI defines `securitySchemes`.
- Automatically generate full policies such as `validate-jwt`, rate-limit, CORS, or rewrite.
- Test whether every request/response conforms to the schema.

After importing, you must configure and verify the **backend service URL**, networking, authentication, operation templates, products, subscriptions, and policies.

### 3.3. Two version definitions that are easily confused

OpenAPI example:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: "1.4.0"
~~~

The value **info.version = 1.4.0** is metadata of the API specification document. It **does not automatically** mean APIM created version identifier **v1** or revision **4**. APIM API versions and revisions are managed through separate properties and lifecycles.

| Value | Where it lives | Purpose |
|---|---|---|
| openapi: 3.0.3 | Top of the OpenAPI document | OAS syntax/version |
| info.version: 1.4.0 | OpenAPI info | API contract metadata |
| API version identifier: v1 | APIM API version set | Routing/identification of the contract version |
| API revision: 2 | APIM revision lifecycle | A change being tested or released |
| Backend artifact: build-417 | CI/CD or runtime | Code currently deployed to the backend |

Do not use a single number for all of these purposes. Release records should track each one explicitly.

## 4. Sample OpenAPI document for Orders API

To practice importing, use OpenAPI 3.0.3 with two operations: get order and create order. This document contains no real credentials.

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: "1.0.0"
  description: Order management API for the commerce system.
servers:
  - url: https://orders-backend.example.internal
paths:
  /orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Get order by ID
      parameters:
        - name: orderId
          in: path
          required: true
          description: Order identifier.
          schema:
            type: string
      responses:
        "200":
          description: Order found.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "404":
          description: Order not found.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
  /orders:
    post:
      operationId: createOrder
      summary: Create an order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateOrderRequest"
      responses:
        "201":
          description: Created successfully.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "400":
          description: Invalid request.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, amount]
      properties:
        customerId:
          type: string
        amount:
          type: number
          format: double
          minimum: 0
    Order:
      type: object
      required: [id, status, customerId, amount]
      properties:
        id:
          type: string
        status:
          type: string
          enum: [pending, paid, canceled]
        customerId:
          type: string
        amount:
          type: number
          format: double
    Error:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
~~~

Here:

- The API gateway can use an **API URL suffix** such as `orders`.
- The get-order operation template is **GET /orders/{orderId}** relative to the API's operation path.
- If the API suffix is also `orders`, the effective gateway URL may contain **/orders/orders/{orderId}**. To design clean paths, account for both the suffix and operation path from the design phase—do not assume APIM deduplicates overlapping segments.
- **servers.url** is metadata in OpenAPI; after importing, explicitly verify the backend URL used by APIM, especially when importing across multiple environments.
- The OpenAPI example above does not declare a security scheme yet. For production use, add security documentation and the corresponding enforcement policies.

### 4.1. Pre-import contract checks

A contract review process should check:

1. Valid YAML/JSON with no duplicate keys.
2. OAS version supported by APIM.
3. Clear, stable, and unique `operationId` values.
4. Unambiguous paths and HTTP methods.
5. Accurate `required` flags and schemas on path parameters.
6. Request bodies and response statuses aligned with the real backend.
7. Consistent use of schemas, nullable/required properties, and enums.
8. No tokens, credential-bearing URLs, or real customer data in examples.
9. Security settings documented accurately without assuming APIM enforces them automatically.
10. Any OpenAPI constructs unsupported by APIM import identified through validation/dry-run import.

Valid YAML syntax is only the baseline condition. A contract can be syntactically valid yet **incompatible** with deployed clients.

## 5. Preparing Azure API Management

### 5.1. Required resources

Suppose the lab architecture is:

~~~text
Subscription: sub-commerce-lab
Resource group: rg-api-lab
Region: southeastasia
APIM service: apim-commerce-lab
Backend: https://orders-backend.example.internal
API id: orders-api
API URL suffix: orders
OpenAPI file: orders-openapi.yaml
~~~

Resource names and domains are purely illustrative; the APIM service must exist, be provisioned, and have an active gateway. Do not create a production APIM instance just for lab exercises; APIM has different tiers, pricing models, networking capabilities, and developer portal features.

### 5.2. Questions before importing

- Is the APIM resource in the right subscription/resource group?
- Do you have sufficient Azure RBAC permissions to modify API definitions?
- Does the API URL suffix collide with another API?
- Does the backend exist, and is there network connectivity from APIM to the backend?
- Does the backend require an OAuth token, mTLS, managed identity, header/API key, or another method?
- Is the product/subscription configuration defined?
- Are clients currently calling this API, or is it brand new?
- Are there policies at global/product/API/operation scope that the import could interact with?
- Is monitoring/tracing available to observe requests before and after the change?
- Is there a version/revision strategy and a rollback owner?

### 5.3. Verify the Azure context

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az apim show \
  --resource-group rg-api-lab \
  --name apim-commerce-lab \
  --query "{name:name,location:location,sku:sku.name,gatewayUrl:gatewayUrl}" \
  --output json
~~~

These are metadata read commands. Returned query fields may vary by API/CLI response; inspect the actual resource. Do not infer the APIM gateway hostname solely from the service name if a custom domain is in use.

## 6. Importing OpenAPI via the Azure Portal

### 6.1. Workflow

In the Azure Portal:

1. Open the target Azure API Management instance.
2. Go to **APIs**.
3. Choose to create an API from **OpenAPI** or the corresponding Import option in your portal version.
4. Provide the OpenAPI file or URL using the supported option.
5. Verify **Display name**, **Name/API identifier**, **API URL suffix**, protocols, and backend **Web service URL**.
6. If creating a new API, select the appropriate version strategy or create the API first and manage the version set deliberately.
7. Import.
8. Open the API's operations list, schemas, and settings to confirm.
9. Test from the gateway test console or an authorized HTTP client.
10. Publish the API to products and the developer portal only according to the approval workflow.

Do not assume the UI has identical buttons or fields across every APIM tier/interface. What matters is the final result: API ID, path, backend, operations, policies, and publication status match the design.

### 6.2. Fields to understand clearly

| Field | Purpose | Risk if wrong |
|---|---|---|
| Display name | Display name in Portal/developer portal | Clients find the wrong API |
| Name/API identifier | Administrative ID of the API in APIM | Reusing an existing ID may update an existing API |
| API URL suffix | Gateway route partition | Path collisions or URL mismatch with contract |
| Web service URL | Backend address APIM forwards requests to | 404/502/timeouts or hitting the wrong environment |
| Protocols | HTTP/HTTPS per configuration capability | Exposing unwanted protocols |
| Subscription required | Require a key per product/API/subscription | API accidentally public or tests fail with 401 |
| API version | Contract version identifier within a version set | Clients do not know which version to call |
| API revision | Change configuration of an API | Overwriting current instead of creating non-current |
| API products | API distribution groups | Partners cannot see the API or receive overly broad access |

### 6.3. Import from file or URL?

- **File in pipeline:** pinned to a commit and checksum; easy to review and roll back.
- **Public/private OpenAPI URL:** convenient when an upstream source continuously publishes specs, but requires controlling availability, access permissions, networking, trust, and whether content changes between imports.
- **Artifact in CI/CD:** generally prefer a versioned, immutable OpenAPI spec produced by a verified build.

Do not configure production to automatically import the “latest spec” from a mutable URL on every deploy without diff inspection and approval. The same URL can serve a new contract and alter the API unexpectedly.

## 7. Importing OpenAPI via Azure CLI

### 7.1. Import a new API

Suppose the sample OpenAPI file is saved as **orders-openapi.yaml** in an authorized working directory. Illustrative command:

~~~bash
az apim api import \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --api-id orders-api \
  --path orders \
  --specification-format OpenApi \
  --specification-path "./orders-openapi.yaml" \
  --service-url "https://orders-backend.example.internal"
~~~

Meaning:

- **--resource-group, --service-name:** identify the APIM resource.
- **--api-id:** administrative API ID, not the URL.
- **--path:** the API URL suffix at the gateway.
- **--specification-format:** specifies how to parse the OpenAPI document.
- **--specification-path:** the API specification file.
- **--service-url:** backend URL used by APIM per configuration.

Accepted values for **--specification-format** and supported flags can vary by Azure CLI version, OpenAPI file format (YAML/JSON), and released features. Before running for real, check:

~~~bash
az apim api import --help
~~~

If your project uses OpenAPI JSON, select the exact import format supported by your CLI version; do not rename file extensions instead of converting data.

**Overwrite warning:** if the API ID already exists, importing can update that API's configuration. Do not run this command against a current production API to experiment with a new spec. Use a lab API/instance or create a non-current revision first.

### 7.2. Verify the API after import

~~~bash
az apim api show \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --api-id orders-api \
  --output json
~~~

List existing APIs:

~~~bash
az apim api list \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --output table
~~~

Some Azure CLI versions have dedicated subcommand groups to list operations and policies. Use the Portal or CLI help to confirm subcommands/parameters before placing them in a production pipeline. Do not only check that the API resource exists; compare **all operations/methods/templates** against the OpenAPI input.

### 7.3. Verify via gateway HTTP

Suppose the gateway domain is **api.contoso.example**, the APIM suffix is `orders`, and the spec operation path is `/orders/{orderId}`:

~~~bash
curl -i \
  "https://api.contoso.example/orders/orders/42" \
  -H "Accept: application/json" \
  -H "Ocp-Apim-Subscription-Key: <APIM_SUBSCRIPTION_KEY>"
~~~

The repeated `orders` segment in the example is intentional to highlight the **API URL suffix + operation path** relationship. Choosing a different suffix changes the gateway URL. Depending on subscription, authentication, and policy settings, the request may require a Bearer token instead of or in addition to the subscription key.

**Do not store real subscription keys in shell history, public HTTP traces, or documentation.** Prefer a secret store or secured terminal environment and control command logging.

### 7.4. Verify the backend URL independently

The APIM gateway URL and the backend URL are not the same. If the gateway returns 404, check:

1. Does APIM have the right API suffix?
2. Does the operation template match the URL?
3. Is the request hitting the intended version/revision?
4. Do policies apply `rewrite-uri` or `set-backend-service`?
5. Does the backend receive the expected path?

If the backend returns 404 while the gateway matches the operation successfully, the issue may lie in the path mapping between APIM and the backend. Do not rush to edit the OpenAPI contract before confirming what request actually reaches the backend.

### 7.5. Compare before and after import

A safe process records evidence:

~~~text
Source commit:      <COMMIT_SHA>
OpenAPI checksum:   <SHA256>
APIM service:       apim-commerce-lab
API ID:             orders-api
Target revision:    <REVISION>
Imported at UTC:    <TIMESTAMP>
Operations before:  <COUNT / LIST>
Operations after:   <COUNT / LIST>
Policy diff:        <REVIEW_LINK>
Backend URL:        <EXPECTED_URL>
Approver:           <IDENTITY>
~~~

The above is a sample release record, not the output of an executed import.

## 8. API versions in API Management

### 8.1. When is a new version needed?

API versions allow mutually incompatible contracts to run side by side.

Example:

~~~text
v1:
  GET /orders/{id}
  Response: {"id":"42","totalPrice":150}

v2:
  GET /orders/{id}
  Response: {"id":"42","total":{"amount":150,"currency":"USD"}}
~~~

A v1 client reading `totalPrice` will fail or misread data if switched directly to v2. When a change breaks the contract, publish a new API version and keep v1 running during an agreed migration window.

### 8.2. Version set

In APIM, API versions of the same logical contract can be organized via an **API version set**. A version set defines how clients select a version—such as path, header, or query string. Each version is typically an API resource with an **API version identifier** and corresponding configuration.

~~~mermaid
flowchart TD
    V["API Version Set: Orders"] --> V1["Version v1"]
    V --> V2["Version v2"]
    V1 --> R11["Revision 1"]
    V1 --> R12["Revision 2"]
    V2 --> R21["Revision 1"]
    V2 --> R22["Revision 2"]
    R11 -.-> C1["V1 current revision"]
    R21 -.-> C2["V2 current revision"]
~~~

This diagram is conceptual: at any point in time, one revision per API version is current; in practice, the current pointer shifts during releases. A version can have multiple independent revisions without forcing clients onto another version.

### 8.3. Distinguishing two types of changes

| Change | Example | How to evaluate |
|---|---|---|
| Edit operation description | Update summary, response examples | Revision is usually appropriate |
| Add optional response field | Add optional `trackingCode` | Can be a revision if all clients remain compatible |
| Add optional query parameter | Add optional `sortBy` | Can be a revision |
| Add a new operation | `GET /orders/{id}/events` | Can be a revision if non-breaking |
| Remove a used response field | Delete `totalPrice` | New version |
| Change data type | `totalPrice` from number to object | New version |
| Change HTTP method or required URL | `GET` changed to `POST` | New version |
| Tighten required request field | Require `customerSegment` | New version if old clients do not send it |
| Change error schema or required auth | Old clients cannot comply | Must evaluate as breaking change; usually new version |
| Swap internal backend while keeping contract | App Service to AKS | Can be a revision/rollout; test compatibility |
| Change rate limit | 1000 req/min down to 100 | Can break client needs even if schema is unchanged; requires notice/plan |

**Compatibility goes beyond OpenAPI.** Authentication, status codes, error behavior, rate limits, latency, ordering, pagination, and side effects are also part of the effective contract.

### 8.4. Version identifiers and semantic versioning

A public API may publish **v1**, **v2**, while OpenAPI `info.version` or backend releases are `1.4.7`, `2.1.0`.

You do not need to create a new API version for every backend patch release. As long as the contract version remains unchanged, code releases or APIM revisions can stay under the same version.

Similarly, do not call a new version `v2` simply because you created revision 2. Revision numbers and API version identifiers have different meanings.

## 9. Three ways to identify an API version

### 9.1. Path (URL segment)

Clients pass the version in the URL path:

~~~http
GET /v1/orders/42 HTTP/1.1
Host: api.contoso.example
Accept: application/json
~~~

Version v2:

~~~http
GET /v2/orders/42 HTTP/1.1
Host: api.contoso.example
Accept: application/json
~~~

**Pros:** easy to observe in URLs, cache keys, and logs; users easily see the version.

**Cons:** changing versions changes the URL; clients, proxies, reverse proxies, or SDKs with hardcoded routing must update.

The example above illustrates one desired path structure. APIM combines the version segment with the API URL suffix/operation path based on the version set configuration; always **verify the actual URL shown in the Portal**, rather than copying the example string verbatim if you configured a different suffix.

### 9.2. Header

The version travels in an HTTP header, with the header name defined by the version set:

~~~http
GET /orders/42 HTTP/1.1
Host: api.contoso.example
api-version: v1
Accept: application/json
~~~

**Pros:** consistent URL across versions; well suited to clients capable of setting custom headers.

**Cons:** some proxies/caches/logs/SDKs do not preserve or differentiate headers by default. If caching responses, account for the version header in cache keys, `Vary`, and gateway design.

Do not assume the header name is `api-version` if the APIM version set is configured with a different name.

### 9.3. Query string

The version is placed in a query parameter:

~~~http
GET /orders/42?api-version=v1 HTTP/1.1
Host: api.contoso.example
Accept: application/json
~~~

**Pros:** easy to test from a browser or HTTP client; version is visible in the URL.

**Cons:** clients must preserve the query parameter; caches/proxies/SDKs must distinguish variants. Avoid putting secrets in URL queries since query strings leak easily into logs; a version identifier itself is not a secret.

### 9.4. Comparison for decision-making

| Criterion | Path | Header | Query |
|---|---|---|---|
| Client sees version in URL | Yes | No | Yes |
| SDK must add header | No | Yes | No |
| Impacts URL on version upgrade | Yes | No | Yes |
| Cache key considerations | By path | By header | By query |
| Ease of manual testing | High | Moderate | High |
| Ease of sharing versioned URLs | High | Low | High |
| Risk of proxy stripping metadata | Lower with path | Can be higher | Must verify query forwarding |

Choose the scheme based on **how clients are built**, caching/CDN/Front Door behavior, API gateway routing, and operational policies. Once many clients use production, changing schemes can itself be a breaking change requiring a dedicated migration plan.

## 10. Creating an API version set and managing versions

### 10.1. Via the Azure Portal

A typical workflow:

1. Open APIM → APIs.
2. Select the existing Orders API or create an appropriate version set.
3. Choose the **Versions** management option.
4. Create/set the **version set display name** and **versioning scheme** (Path/Header/Query).
5. Enter an identifier such as **v1** for the current API or create a new API version **v2**.
6. Verify v1/v2 API IDs do not collide and displayed URLs are accurate.
7. Import/author operations for the new version per that version's contract.
8. Configure backend URLs, products, policies, and tests for each version.
9. Publish the version through approved channels and plans.

Do not assume all version set fields can be changed effortlessly after publishing. Changing the versioning scheme may require clients to update URLs/headers/queries as well as cache/integration systems.

### 10.2. Azure CLI options

Azure CLI provides command groups to manage APIM API version sets. Illustrative syntax:

~~~bash
az apim api versionset create \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --version-set-id orders-versions \
  --display-name "Orders API versions" \
  --versioning-scheme Segment
~~~

In CLI versions, **Segment** typically corresponds to path/URL segment versioning; header/query options have dedicated header/query name properties. Before running in production, check:

~~~bash
az apim api versionset create --help
~~~

Do not infer that simply because the version set exists, v1/v2 API objects have been created. Each API version must be created or linked to the proper version set using supported tooling.

### 10.3. Linking an API version

Each API version in a version set must have:

- A distinct API ID in the management plane.
- A version identifier, such as `v1` or `v2`.
- A reference to the API version set.
- Operations and policies for that version.
- Backend configuration and test cases.
- Appropriately published products/subscriptions.

When using CLI or IaC, you may need to pass the **API version set resource ID** rather than the display name. Retrieve the ID from the actual version set resource instead of constructing strings blindly without verifying the subscription/resource group.

### 10.4. Creating a new version without overwriting the old one

A v2 release strategy:

~~~mermaid
flowchart TD
    C["Orders v1 in production"] --> N["Design OpenAPI v2"]
    N --> D["Contract diff + breaking-change review"]
    D --> V["Create API v2 in version set"]
    V --> I["Import OpenAPI v2 into API v2"]
    I --> T["Test policy, backend, auth, responses"]
    T --> P["Publish v2 to client group"]
    P --> M["Monitor v1/v2 adoption"]
    M --> E["Deprecate/sunset v1 per plan"]
~~~

**Do not edit OpenAPI `info.version` from `1.0.0` to `2.0.0` and assume APIM automatically creates API v2.** The version set and API version identifier must be configured explicitly.

### 10.5. Keeping v1 during the transition period

While v1 clients remain active:

- Continue supporting v1 until the announced sunset date.
- Apply only necessary security/stability fixes.
- Provide a migration guide and sample v2 requests.
- Monitor version traffic and which subscriptions/clients still call v1.
- Avoid altering v1 backend responses to match the v2 schema unless a compatibility adapter is in place.
- Keep v2 rollback independent without impacting v1.

APIM can route v1/v2 to the same backend codebase using different routes/policies, but that is safe only when the backend understands and is tested for both contracts.

## 11. API revisions: changes within a version

### 11.1. Revisions differ from versions

**Revisions** allow creating a modified copy of the **same API contract/version** for testing before applying it to the official URL. Revisions are particularly suitable for:

- Adding compatible operations.
- Updating documentation/examples.
- Updating mapping/rewrite policies.
- Changing backend/service URLs while preserving the contract.
- Adding non-breaking validation or telemetry.
- Staging policy changes and testing before publishing.

~~~mermaid
flowchart TD
    V["Orders v1"] --> R1["Revision 1: current"]
    V --> R2["Revision 2: non-current"]
    V --> R3["Revision 3: non-current"]
    R2 --> T["Test via revision URL"]
    T --> G{"Release gate passed?"}
    G -->|Yes| C["Make revision 2 current"]
    G -->|No| H["Keep current revision 1"]
~~~

For v2, it can have its own revision 1 and revision 2. Never treat revision 2 of v1 as API version v2.

### 11.2. Current and non-current

- **Current revision:** the active configuration currently serving customers via the API version's normal gateway URL.
- **Non-current revision:** a staged change not yet promoted to current, accessible via a revision-specific gateway URL per features and policies.
- **Make current:** the action promoting a tested revision to current, changing the configuration used by the normal URL.
- **Release notes:** record the reason and content of changes for users/internal audits.
- **Rollback:** a previous revision can be made current again if state and policies permit, though backend/data side effects must be evaluated.

Creating a revision **does not** automatically make it current; that separation is what enables testing without immediately disrupting production callers.

### 11.3. Revision access paths

APIM uses a revision suffix URL mechanism, typically expressed as **;rev={revisionNumber}** in the API path segment. Illustrative example for API suffix `orders`:

~~~text
Current:
  https://api.contoso.example/orders/orders/42

Non-current revision 2:
  https://api.contoso.example/orders;rev=2/orders/42
~~~

This is an illustrative example; if the APIM API uses path/header/query versioning, the effective URL also depends on the **versioning scheme, API URL suffix, and operation template**. Always retrieve the exact URL provided by the Portal/gateway configuration.

Some clients/proxies/routers handle semicolons in paths differently. Test WAF, Application Gateway/Front Door, reverse proxies, and real SDKs before relying on revision URLs for testing.

Non-current revisions still enforce API call permissions per product/subscription/policy settings; **`;rev=2` is not an authentication mechanism**.

### 11.4. Creating a revision in the Portal

1. Open the target API or exact **API version v1** in APIM.
2. Go to **Revisions**.
3. Select **Add revision**.
4. Enter the new revision number and change description.
5. Keep the existing current revision serving production traffic.
6. Open the new revision to import/update the OpenAPI spec and policies under test.
7. Configure/verify the backend URL, operation templates, and schemas.
8. Call the revision-specific URL with proper auth, subscription key, and test cases.
9. Only after acceptance and approval, select **Make current**.
10. Record release notes, timestamp, approver, config/commit SHA, and test results.

**Do not edit the current revision directly while preparing untested changes.** Importing with the same API ID without targeting the intended revision can alter production unexpectedly.

### 11.5. Configuring imports to target a revision

When automating, explicitly specify the **API revision target**, not just the API display name.

Some APIM tools represent a revision in the management API ID using a suffix like **;rev=2**. In CLI/shells, the semicolon must be properly quoted/escaped—for example, keeping the revision-qualified API identifier inside a string:

~~~text
orders-api;rev=2
~~~

Do not assume all CLI/API commands accept this identifier in the same parameter. Before building a pipeline, verify whether your tool expects an API ID with a revision suffix or a separate revision parameter, and test in an APIM lab. Only run imports when certain you are targeting a **non-current revision**.

### 11.6. Make current and API releases

A typical workflow:

~~~mermaid
sequenceDiagram
    participant D as Developer / CI
    participant A as APIM Non-current Revision
    participant Q as QA / Security
    participant G as APIM Gateway Current
    participant M as Monitoring
    D->>A: Import OpenAPI + policies
    Q->>A: Test revision URL
    A-->>Q: Responses and traces
    Q->>D: Approval / sign-off
    D->>G: Make revision current
    G->>M: Production traffic under new config
    M-->>D: Error rate, latency, business checks
~~~

**Make current does not deploy backend code.** If a revision references a new backend, ensure the backend version is already deployed and compatible. An API release can record which revision was made current; client notifications and release documentation must be managed under their own lifecycle.

### 11.7. Limitations of revision rollback

Rolling back to a prior revision can restore part of the APIM configuration such as operations or API-level policies per revision semantics. However, it does not automatically undo:

- Database schema migrations already executed in the backend.
- Data mutated by the new API.
- Secret rotations, Key Vault permissions, or VNet/Private Endpoint networking outside the API resource.
- Global/product-scope policies edited separately.
- Independently deployed/rolled-back backend artifacts.
- Caches, subscriptions, client state, or external services.

Therefore, maintain backward-compatible backends or a rollback/feature-flag plan; simply clicking “Make old revision current” is not a full-system transactional rollback.

## 12. Choosing version vs. revision: decision matrix

| Scenario | Initial recommendation | Reason |
|---|---|---|
| Fix typo in operation description | Revision | Does not alter client contract |
| Add optional response field | Revision if compatibility-tested | Old clients usually ignore unknown fields, though not always |
| Add a new GET endpoint | Revision | Existing operations remain intact |
| Swap mock for production backend, same contract | Revision | Implementation swap after testing |
| Change auth policy blocking old clients | New version or governed migration | Breaking operational behavior |
| Remove a required response field | New version | Old clients may fail |
| Change property from string to number | New version | Breaking schema change |
| Change required path | New version | Clients must change requests |
| Change pagination semantics | New version if incompatible | Client logic may break |
| Tightly reduce timeout/429 quota | Release change with notice; consider version | More than just schema |
| Deploy backend bugfix with unchanged contract | Release/revision per governance | No need to multiply API versions |
| Open beta API for independent client group | Version/preview API per strategy | Do not misuse revision URLs as long-term public beta |
| Test a new policy before production | Non-current revision | Provides test endpoint and promotion gate |

**Do not use version numbers as an excuse to skip testing.** API v2 still requires contract tests, security tests, and backend observability.

### 12.1. A pragmatic rule of thumb

- Client-breaking change → create a **new version**.
- Compatible change needing pre-publish testing → create a **new revision**.
- Backend-only deployment with no APIM configuration impact → manage via backend CI/CD; a revision may be unnecessary unless APIM audit/promotion tracking is required.
- Security, routing, quota, or business-error changes invisible in schemas → assess impact as a breaking change rather than relying solely on an OpenAPI diff.

## 13. Standard workflow from contract to release

### 13.1. Contract-first workflow

~~~mermaid
flowchart TD
    R["Requirement / change request"] --> O["Edit OpenAPI in Git"]
    O --> D["OpenAPI lint + diff"]
    D --> B{"Breaking change?"}
    B -->|Yes| V["Create new API version"]
    B -->|No| N["Create non-current revision"]
    V --> I["Import to exact API target"]
    N --> I
    I --> T["Validate operations, policies, backend"]
    T --> S["Security + contract tests"]
    S --> A{"Approval"}
    A -->|No| F["Keep current serving version"]
    A -->|Yes| P["Make revision current / Publish version"]
    P --> M["Monitor errors, latency, adoption"]
    M --> K["Release notes + rollback readiness"]
~~~

Not every CI pipeline handles revision creation identically; use supported and tested API Management REST/ARM/Bicep/CLI mechanisms, and do not treat manual Portal clicks as the entire source of truth if reproducible operations are required.

### 13.2. Before importing into APIM

1. Review the OpenAPI diff from the commit against the current version/revision.
2. Run a linter/schema validator using the team's chosen tool.
3. Classify changes as breaking or non-breaking.
4. Prepare rollback/compatibility plans for backend, database, and messaging.
5. Identify the exact APIM service, version set, API ID, and revision target.
6. Confirm backend URL, identity, networking, and policies to apply.
7. Record artifact SHA/commit SHA and approver.
8. Back up/export metadata needed for rollback if required by governance.
9. Never let pipelines import directly into current production without QA verification.

### 13.3. After importing

Compare the source OpenAPI against the APIM API:

| Check | What to verify |
|---|---|
| API ID and URL suffix | Exact name, no route collisions |
| API version/version set | Correct identifier and scheme |
| Target revision | Non-current or current as planned |
| Operations | Count, methods, path templates |
| Parameters | Accurate required/path/query/header definitions |
| Request/response schemas | Important structures not dropped |
| Backend URL | Matches dev/staging/prod |
| Policies | Auth, CORS, transformations, throttling still work |
| Products/subscriptions | Correct permitted user groups |
| Developer portal | Docs/try-it/links valid when published |
| Gateway connectivity | HTTP 2xx/4xx/5xx and TLS/network behavior accurate |
| Monitoring | Diagnostics/logs receiving data |
| Contract tests | v1/v2 clients remain compatible |
| Rollback | Current/previous revision and recovery steps verified |

If the import emits warnings about unsupported OpenAPI constructs, do not ignore them just because a test HTTP GET returns 200. Document what was omitted and whether it affects validation or client documentation.

## 14. Testing gateway, versions, and revisions

### 14.1. Minimum test matrix

| Test | Current v1 | Non-current v1 revision | Version v2 |
|---|---|---|---|
| Valid `GET /orders/{id}` | 200 per v1 schema | 200 per expected revision schema | 200 per v2 schema |
| Non-existent ID | 404 with v1 error contract | 404 with tested format | 404 per v2 contract |
| Invalid POST payload | 400/422 per contract | Still compatible with v1 | Per v2 |
| Missing subscription/token | Rejected per policy | Rejected similarly unless testing auth | Rejected per v2 policy |
| Insufficient permissions | 403 per policy | 403 | 403 |
| Rate limit | Current policy | New policy if under test | Configured policy |
| Backend timeout | Error mapping/observability | Verify no regressions | Test separately |
| OpenAPI contract | v1 | Non-breaking v1 | v2 |
| Metrics/tracing | Baseline | Compare during tests | Per version adoption |

Exact HTTP status codes depend on the real contract and policies; not every validation error must return 422. The goal is verifying **what the API actually promised**.

### 14.2. Testing auth and subscriptions

APIM subscription keys are typically passed via a configured header, for example:

~~~http
GET /orders/orders/42 HTTP/1.1
Host: api.contoso.example
Ocp-Apim-Subscription-Key: <SUBSCRIPTION_KEY>
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

An API may require one or both depending on product/subscription settings and `validate-jwt`/`validate-azure-ad-token` policies. **OpenAPI `securitySchemes` do not cause the gateway to automatically require and validate JWTs** without a configured policy or authentication mechanism.

### 14.3. Common errors to distinguish

- **401:** missing/invalid subscription key, invalid bearer token, or policy authentication rejection.
- **403:** caller identified but lacks permissions, blocked by IP/policy/product, or rejected by backend.
- **404:** APIM could not match API/operation/version/revision route, or backend returned 404 after routing.
- **405:** method not allowed, or operation was not imported/routed as expected.
- **429:** rate-limit/quota or backend throttling; determine whether gateway or backend raised it.
- **500:** policy expression failure or backend/internal error; check logs/traces.
- **502/503/504:** backend connectivity, DNS/TLS, timeout, upstream availability, or gateway issue.

Do not jump to the conclusion that 404 means the OpenAPI path is wrong. Trace the actual request through gateway and backend to isolate the failing layer.

### 14.4. Verify version routing matches the scheme

With path versioning:

~~~text
Call current v1 via v1 URL.
Call new v2 via v2 URL.
Do not omit version segment if required.
~~~

With header versioning:

~~~http
GET /orders/orders/42 HTTP/1.1
Host: api.contoso.example
api-version: v2
~~~

With query versioning:

~~~http
GET /orders/orders/42?api-version=v2 HTTP/1.1
Host: api.contoso.example
~~~

URLs are illustrative; actual paths and header/query names depend on the version set. Pay special attention to testing proxies/CDNs/caches so a v2 response is never served to a v1 request.

### 14.5. Testing the revision URL

After creating revision 2:

~~~text
Current v1:
  https://api.contoso.example/orders/orders/42

Non-current revision 2:
  https://api.contoso.example/orders;rev=2/orders/42
~~~

For APIs with an existing versioning scheme, retrieve the exact URL from APIM and apply the revision per supported routing. When testing, preserve full subscription/auth policies. Never allow a revision endpoint to expose unpublished data merely by assuming callers must guess `;rev=2`.

## 15. Keeping backend, policies, and OpenAPI contract aligned

### 15.1. APIM does not make backends compatible automatically

Suppose revision 2 adds a `discountCode` field to the request body. Backend v1 code might ignore it or return 400. Importing into APIM does not deploy a backend that understands the new field.

A release must ensure:

- The backend already supports the new contract or has an adapter.
- APIM mapping/rewrite policies are accurate.
- Any fields/headers stripped or altered by policies are documented.
- Error codes/messages match the contract.
- The backend version does not break API v1 when sharing a service.
- Data migrations/DB schemas remain compatible with active versions.
- Rollback paths exist for both API and backend.

### 15.2. Policy scopes

APIM policies can be applied at multiple scopes, such as:

- Global.
- Product.
- API.
- Operation.

Effective behavior depends on evaluation order, inheritance policies, and `<base />` usage. When testing a new revision, do not assume product/global policies are versioned along with the API revision. Editing a global policy can impact both v1 and v2 even from a single XML edit.

Common policy categories:

| Policy | Goal | What to verify |
|---|---|---|
| `validate-jwt` / Entra token validation | Validate JWT | Issuer/audience, signing keys, claims, expiry |
| `rate-limit` / `quota` | Protect backend, allocate usage | Counter scope, client key, 429 behavior |
| `set-backend-service` | Select backend | Environment, TLS, DNS, failover |
| `rewrite-uri` | Map gateway path to backend path | Path params, method, query |
| `set-header` | Add/remove/modify headers | Avoid leaking tokens or breaking signatures |
| `CORS` | Define browser origins/headers | Does not replace authentication |
| `validate-content` / `validate-parameters` | Validate requests/responses per supported config | Runtime cost, schema support, and error behavior |
| `cache` | Reduce backend requests | Cache keys must separate version/auth/tenant properly |
| `trace/logging` | Request diagnostics | Never log secrets/PII |

Do not assume OpenAPI import creates all validation policies automatically. Documentation and runtime enforcement are distinct concerns.

### 15.3. OpenAPI securitySchemes is documentation, not enforcement

Example document snippet:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
~~~

This states that clients must send a Bearer token per contract. For APIM to actually verify JWT claims and issuer, appropriate policies/authentication integrations are required, and the backend must also be protected per architecture. Do not treat `securitySchemes` as an automatic access block.

### 15.4. Managed identity to backend

If the backend supports Microsoft Entra ID, APIM can use managed identity and an appropriate policy to acquire a token for calling the backend per product capabilities. You need to:

1. Enable identity on the APIM resource for the supported scenario.
2. Grant the APIM identity permissions on the backend/resource.
3. Configure the exact token resource/audience.
4. Ensure network DNS/routing and TLS.
5. Verify policy scope/version/revision.
6. Never log bearer tokens or backend credentials.

If the backend is an Azure Function using a function key, use named values/Key Vault integration and proper protection policies; never write keys directly into OpenAPI examples or pipeline source.

## 16. Versioning and revisions in CI/CD

### 16.1. Single source of truth

Production API governance should have a reviewable configuration source:

~~~text
Repository
  ├─ openapi/orders-v1.yaml
  ├─ openapi/orders-v2.yaml
  ├─ apim/api-definitions/
  ├─ apim/policies/
  ├─ apim/version-sets/
  ├─ tests/contract/
  └─ release-metadata/
~~~

The structure above only illustrates a folder layout **for a team's project**, not a requirement to create files during this lesson. Do not create these files solely from the example.

You can use Bicep, Terraform, ARM templates, APIM DevOps tooling, or REST/CLI according to your organization's standards. What matters is that version sets, API metadata, policies, and import sources are all under change control.

### 16.2. Safe release pipeline

~~~mermaid
flowchart TD
    S["OpenAPI commit"] --> L["Lint / validate OAS"]
    L --> D["Diff against current contract"]
    D --> C{"Breaking change?"}
    C -->|Yes| V["New API version"]
    C -->|No| R["New non-current revision"]
    V --> I["Import into target"]
    R --> I
    I --> Q["Contract + gateway security tests"]
    Q --> G{"Approval"}
    G -->|Fail| H["Keep production current"]
    G -->|Pass| P["Publish version / Make current"]
    P --> O["Monitor + release notes"]
~~~

Separate roles:

- CI identity reads source, builds OpenAPI artifacts, and runs linters.
- CD identity has permission to import into APIM staging or non-current revisions.
- Release approvers decide when to switch current/publish a version.
- APIM runtime identity accesses backends with least privilege.
- API clients use subscription/Entra credentials on the data plane.

Never grant subscription-wide Owner to a pipeline just to import an API.

### 16.3. Controlling drift from manual Portal edits

If a team manages APIM with IaC but someone edits operations/policies directly in the Portal:

- The next deployment may overwrite those edits.
- The OpenAPI file no longer reflects runtime state.
- Audit trails struggle to identify the source of changes.
- A revision may lack a corresponding export/release record.

Require production changes to go through PRs/change tickets; if an emergency Portal edit occurs, update IaC/source afterward and log reconciliation.

### 16.4. Release metadata

~~~yaml
releaseId: "orders-api-v1-rev3-2026-11-20"
apimService: "apim-commerce-lab"
apiId: "orders-v1"
apiVersionSet: "orders-versions"
apiVersion: "v1"
revision: "3"
previousCurrentRevision: "2"
sourceCommit: "<COMMIT_SHA>"
openapiChecksum: "<SHA256>"
backendVersion: "<BUILD_SHA>"
approval: "<APPROVER_ID>"
changeType: "non-breaking"
tests:
  contract: "passed"
  gatewayAuth: "passed"
  backendConnectivity: "passed"
  regression: "passed"
rollback:
  previousRevisionAvailable: true
  backendCompatible: true
~~~

This is illustrative metadata, **not a mandatory Azure CLI/APIM schema**. Any `"passed"` status must be backed by actual verification logs/artifacts; never write `"passed"` into a production release record if the tests were not run.

## 17. Rollback strategy and client migration governance

### 17.1. Rolling back an API revision

If revision 3 was just promoted to current and a policy error surfaces:

1. Assess impact: 401, 403, 429, 5xx, response schemas, affected clients.
2. Check whether backend/data changed.
3. If appropriate, make the known-good revision 2 current again per APIM workflow.
4. Compare gateway responses against baseline.
5. Monitor error rates/latency and transactions.
6. Record incident/release notes and preventive actions.

**Switching back to a previous current revision** can restore revision-scoped routes/policies, but will not automatically roll back a database migration or edited global policies.

### 17.2. Rolling back an API version

If v2 encounters errors, clients calling v2 generally need to:

- Adjust client routing/feature flags if supported.
- Or deploy a bugfix for v2.
- Or keep v1 operational so clients can fall back.
- Verify whether data written by v2 can still be read by v1.

You cannot force v2 clients back to v1 merely by changing the current revision of API v1; **version v1 and version v2 are two distinct contract routes**.

### 17.3. Deprecation and sunset

A v1 → v2 plan:

1. Publish v2 with docs, OpenAPI contract, and migration guide.
2. Let clients test against staging/sandbox if available.
3. Monitor traffic, version identifiers, response errors, and subscription/client adoption.
4. Send deprecation notices with concrete dates.
5. Support the transition window per SLA.
6. Optionally emit deprecation/sunset response headers per policy if desired; configure and test them explicitly.
7. Remove v1 only when legal/contractual terms and telemetry permit.
8. Retain release records, audits, and rollback plans during retirement.

Do not delete a published version simply because request volume looked low on a single day. Monthly scheduled clients or batch jobs may still depend on it.

### 17.4. Version adoption metrics

Track:

- Request counts by version, product, and privacy-safe subscription/client identifier.
- Error rates and p95/p99 latency by version.
- Which v1 operations are still being called.
- Success rate on new v2 clients.
- Partner integration test results.
- Contractually mandated end-of-support dates.

Protect customer identity data and never log subscription keys or bearer tokens into Log Analytics.

## 18. Security when importing, testing, and publishing APIs

### 18.1. APIM management permissions

Use Azure RBAC and PIM following least privilege:

- Designers can review OpenAPI specs without needing permissions to edit production APIM.
- CI/CD automation holds import permissions within a controlled scope.
- Approvers hold permissions to switch the current revision per workflow.
- Operators hold permissions to read diagnostics and troubleshoot incidents.
- Never grant permission to delete the APIM service to someone who only needs to update one API.

### 18.2. Protecting data and credentials

- Never store APIM subscription keys in OpenAPI files/examples.
- Never embed backend API keys in specs or CLI logs.
- Use Key Vault/named values per supported APIM features.
- When importing via URL, control the source and verify artifact checksums.
- Call test revisions only with authorized accounts/subscriptions.
- Configure `validate-jwt`, IP restrictions, mTLS, CORS, and rate limits per threat model.
- Never assume an “unguessable” revision endpoint is secure.
- Mask PII in traces and response bodies where required.
- Protect the developer portal and expose APIs only to intended products/audiences.

### 18.3. Networking

APIM can call backends over public or private networks depending on tier/topology:

- Verify backend DNS.
- Verify VNet/Private Endpoint/VNet integration when required.
- Verify outbound TLS and certificate trust.
- Verify WAF/Front Door, proxy, and path/header forwarding.
- Verify application-level auth to the backend.
- Never open a firewall to the entire Internet as a quick fix for an APIM 502.

A gateway 502 caused by backend unreachability is not automatically an OpenAPI import bug; inspect networking, DNS, TLS, and backend logs.

## 19. Monitoring and API Management cost

### 19.1. Signals to observe

| Signal | Operational question |
|---|---|
| Gateway request count | Which version is being called? |
| 4xx by API/version | Client/auth/version routing error or contract change? |
| 429 | APIM rate limit or backend throttling? |
| 5xx | Policy/gateway/backend failure? |
| Gateway response duration | Is APIM adding latency? |
| Backend response duration | Did the backend slow down after release? |
| Policy errors | Are expressions/JWT/rewrites failing? |
| Product/subscription usage | Which client group is impacted? |
| APIM capacity/scale | Does the tier handle the load? |
| Backend availability | Is the target service healthy? |
| Cost by resource/tag | How much do APIM tier, logs, networking, and backends cost? |

### 19.2. Logs and traces may depend on configuration

Use Azure Monitor metrics, APIM diagnostics, Log Analytics, and Application Insights integration per enabled features. For troubleshooting, capture:

- UTC timestamp.
- APIM service/API ID.
- Version identifier/revision.
- Operation and request ID/correlation ID.
- Gateway status and backend status.
- Durations/latency.
- Standardized policy/error code.
- Backend version/build ID if provided by the application.
- Client identity/subscription identifier at the necessary level, never keys/tokens.

Do not assume every request/response body is stored: logging involves sampling, privacy, and retention. **Never enable full body logging on sensitive data** merely to compare revisions.

### 19.3. Alerts after Make current

During the observation window (thresholds are examples; base them on real baselines):

- 5xx exceeds agreed threshold for 5 minutes.
- Sudden spike in 401/403 after an auth policy change.
- Spike in 404/405 on newly imported operations.
- Spike in 429 after modifying a rate-limit policy.
- Unusual p95 latency increase.
- Backend dependency/health failures.
- Telemetry drops from the gateway after diagnostics changes.
- Unexpected version adoption or client regression.

Do not auto-rollback on a single metric without defined decision rules and accountable owners. Some errors stem from backend or data migrations that an APIM rollback cannot fix.

### 19.4. Costs to consider

Azure API Management has different service tiers/pricing models, capacity limits, and networking features. When designing multiple versions/revisions:

- Versions/revisions themselves are gateway configurations, not separate APIM instances; however, all versions share the APIM service's capacity/load.
- APIM capacity/tier/scale drives most gateway costs under the chosen pricing model.
- Each API version can increase request volume, policy execution, and backend compute costs.
- Application Insights/Log Analytics incur ingestion and retention fees.
- Custom domains/certificates, networking, WAF/Front Door, and private networking may add extra charges.
- Caching or heavy policies can affect latency/compute utilization.
- Keeping many legacy API versions increases operational overhead and partner support costs.

Do not choose Premium/isolated tiers just for a new version demo; evaluate features and pricing against real requirements, region, VNet, and SLA.

## 20. Real-world scenario: Orders API from v1 to v2

### 20.1. Context

An enterprise has:

- Mobile app v1 calling Orders API and reading `totalPrice`.
- Partner integrations using dedicated subscription keys.
- Backend running on App Service with an orders database.
- APIM gateway protecting the API with an Entra auth policy for internal teams and appropriate subscriptions/products for partners.
- The development team wants to introduce a new money structure **total.amount + total.currency**.

Replacing `totalPrice` with an object is a breaking change. Safe plan:

1. Keep Orders v1 running.
2. Create Orders v2 in the version set.
3. Import OpenAPI v2 compatible with the new backend.
4. Backend supports both v1/v2 or uses separate adapters/routes.
5. Test security and response schemas for both versions.
6. Publish v2 to pilot clients.
7. Monitor migration by product/subscription.
8. Within v2, use revisions to test adding optional fields or tuning policies.
9. Sunset v1 only after the notice period and confirming clients have upgraded.

### 20.2. Release model

~~~mermaid
flowchart TD
    VS["Orders Version Set"] --> V1["API v1"]
    VS --> V2["API v2"]
    V1 --> B1["Backend adapter v1"]
    V2 --> B2["Backend adapter v2"]
    V2 --> R1["Revision 1 current"]
    V2 --> R2["Revision 2 non-current"]
    R2 --> T["Test policy/operation"]
    T --> C["Make revision 2 current"]
    B1 --> DB["Orders database"]
    B2 --> DB
~~~

If the database schema must change, use backward-compatible migrations (such as expand–migrate–contract) so both v1 and v2 function during the transition. APIM versioning does not orchestrate database migrations.

### 20.3. Release runbook

~~~yaml
release:
  service: "apim-commerce-lab"
  resourceGroup: "rg-api-prod"
  versionSet: "orders"
  apiId: "orders-v2"
  version: "v2"
  targetRevision: "2"
  previousCurrentRevision: "1"
  openapiArtifact: "orders-v2.yaml"
preflight:
  - "Confirm API version set and routing scheme"
  - "Confirm revision 2 is non-current"
  - "Check OpenAPI diff and unsupported constructs"
  - "Validate backend URL and Entra/Key Vault permissions"
  - "Test gateway revision URL and policy inheritance"
  - "Contract regression for both v1 and v2"
approval:
  required: true
promotion:
  action: "Make revision 2 current"
postRelease:
  - "Verify normal v2 URL serves revision 2"
  - "Check 4xx/5xx/429/p95 latency"
  - "Confirm v1 contract remains valid"
  - "Record release notes and source SHA"
rollback:
  - "Evaluate backend/data compatibility"
  - "If safe, make revision 1 current again"
  - "Run gateway and business smoke tests"
~~~

This YAML runbook is an **operational template**, not a file to execute directly via Azure CLI or DevOps. Items like `"Confirm..."` represent steps requiring execution evidence.

### 20.4. Release completion criteria

- OpenAPI v1 and v2 have verified artifacts/checksums.
- API versions resolve accurately via path/header/query.
- Each version has a distinct API ID in the right version set.
- The new revision was tested without modifying current prior to approval.
- Authentication, subscription policies, and product visibility are accurate.
- The backend receives the expected path, token, and schema.
- v1 clients are unaffected by the v2 release.
- Gateway logs accurately capture API version/operation and request status.
- A migration guide and v1 sunset date exist.
- Revision rollback and data compatibility are verified.

## 21. Common troubleshooting scenarios

| Symptom | Possible cause | Remediation direction |
|---|---|---|
| Import reports invalid OpenAPI | Malformed YAML/JSON, unsupported OAS version, unsupported schema construct | Validate OAS, review warnings, fix formatting |
| Import succeeds but operation missing | Unsupported operation template, path/parameter error | Compare imported operations against source |
| API ID already exists | Import targeted production API instead of a new API | Stop, verify target, use proper revision/API ID |
| Gateway returns 404 | Wrong API suffix + operation path, missing version identifier | Check actual URL, method, and scheme |
| Backend returns 404 | APIM rewrite/set-backend-service routed wrong path | Inspect APIM/backend traces, check URL |
| Header version has no effect | Wrong header name or proxy stripped header | Inspect version set and forwarding |
| Query version has no effect | Wrong query parameter name/value | Compare against version set settings |
| Revision URL inaccessible | Misplaced `;rev` suffix, proxy semicolon handling, auth | Fetch exact URL and test gateway directly |
| Non-current revision altered production | Accidentally imported into current API | Restore config/revision, fix CD targets |
| Both v1 and v2 fail after policy change | Global/product policy modified | Check policy inheritance and roll back the right scope |
| 401/403 after import | Wrong subscription/product/auth policy or missing backend permission | Separate gateway auth from backend auth |
| 429 after Make current | Rate-limit/quota policy changed or backend throttling | Compare counters/quotas/logs |
| 500 after editing policy | Broken policy expression or invalid mapping | Trace policy and test rollback |
| 502/503/504 | Backend DNS, TLS, network, service unavailable | Check APIM→backend connectivity |
| OpenAPI `securitySchemes` exists but clients still get through | No runtime auth policy enforced | Configure `validate-jwt`/authorization |
| Custom domain works but revision fails | WAF/proxy path rewrite strips `;rev` | Inspect end-to-end routing |
| v1 clients break after v2 import | Shared backend schema/policy broke v1 | Contract regression, backend compatibility |
| Errors persist after revision rollback | Database/backend/global policy changed outside revision | Recover at the impacted layer |
| Developer portal does not show v2 | Not published to right product or portal config | Check product/visibility/publishing |
| APIM logs show no requests | Diagnostics/sampling disabled or wrong workspace | Inspect telemetry pipeline |

### 21.1. Investigation order

1. **Azure resource:** right subscription, service, and API ID?
2. **Route:** right suffix, version set scheme, version identifier, and revision?
3. **Operation:** is the method/path template present in APIM?
4. **Product/subscription:** are key and permissions valid?
5. **Policies:** did auth, rewrite, backend routing, or rate limit change?
6. **Backend:** are DNS/TLS/network/service URL and runtime healthy?
7. **Contract:** do requests/responses match the imported OpenAPI?
8. **Metrics:** what are error rates, latency, and client version distribution?
9. **Release metadata:** what commit, revision, backend artifact, and timestamp?
10. **Rollback:** is a prior configuration available and data-compatible?

Never resolve a 404 by exposing the backend directly to the Internet or deleting all policies. The goal is identifying whether the fault is in gateway routing, authorization, or the backend.

## 22. Production checklist

### OpenAPI contract

- [ ] OpenAPI version and YAML/JSON file supported by APIM.
- [ ] Complete operations, parameters, `requestBody`, and response schemas.
- [ ] Unique and stable `operationId` values.
- [ ] No secrets/real accounts in specs or examples.
- [ ] OpenAPI diff classified into breaking/non-breaking.
- [ ] Document `info.version` not confused with APIM API version.
- [ ] Import warnings and unsupported fields reviewed.
- [ ] Artifact checksum and source commit recorded.

### Versions and revisions

- [ ] Version set uses Path/Header/Query scheme suited to clients.
- [ ] v1/v2 have distinct API IDs in the right version set.
- [ ] Version identifier appears accurately in gateway requests.
- [ ] Compatible changes tested in a non-current revision.
- [ ] Current revision untouched before approval.
- [ ] Revision URL tested through actual gateway and proxies.
- [ ] Make current accompanied by release notes, approver, and timestamp.
- [ ] Revision rollback and backend rollback evaluated.
- [ ] v1 clients still supported during the migration window.

### Security and networking

- [ ] Backend URL, TLS/DNS, and private networking accurate.
- [ ] APIM identity/Key Vault/named values granted least privilege.
- [ ] Subscription products and scopes do not accidentally expose APIs.
- [ ] JWT/auth policies actively enforced; not relying solely on OpenAPI security metadata.
- [ ] CORS, rate limits, cache keys, and rewrite policies verified.
- [ ] Subscription keys, Bearer tokens, and PII excluded from logs.
- [ ] CI/CD identity has no broader permissions than needed for import/release.

### Monitoring and operations

- [ ] Smoke tests cover current/revision/version gateway endpoints.
- [ ] Baselines/alerts set for 4xx/5xx/429 and p95 latency.
- [ ] Per-version client adoption metrics in place.
- [ ] Backend health and dependency logs available.
- [ ] Incident runbook ready if import/current promotion causes errors.
- [ ] Migration guide and deprecation/sunset plan ready.
- [ ] APIM, Monitor, networking, and backend costs tracked.
- [ ] IaC/repository metadata reflects runtime configuration without drift.

## 23. Self-check questions

1. **Does Azure API Management automatically run business code after importing OpenAPI?** No; APIM manages the gateway/operations/policies, while the backend handles business logic.
2. **Is OpenAPI `info.version` the APIM API version identifier?** Not automatically.
3. **How does the API URL suffix differ from the operation path?** The suffix identifies the API on the gateway; the operation path is the route inside the API.
4. **Why can a successful import still return 502?** APIM may fail to reach the backend due to DNS/TLS/networking.
5. **When is an API version used?** When multiple differing API contracts must run in parallel, usually due to breaking changes.
6. **When is an API revision used?** When testing/changing an API version without immediately affecting the current gateway URL.
7. **Does revision 2 mean version v2?** No.
8. **What is the current revision?** The revision actively serving through the API version's normal URL.
9. **How can a non-current revision be tested?** Through a revision-specific URL per APIM features, with proper auth and policies.
10. **Is `;rev=2` syntax a password?** No; it is purely revision routing.
11. **Can path/header/query be used to select an API version?** Yes, depending on the version set scheme.
12. **What are the pros and cons of header-based versioning?** Preserves the URL, but requires handling header forwarding and cache keys.
13. **When changing a required response field, what should you consider?** It is a breaking change; consider a new version.
14. **Is adding an optional query parameter guaranteed not to break clients?** Not certain; contract/regression tests are still required.
15. **Does importing OpenAPI automatically create a `validate-jwt` policy?** Do not assume so; it must be configured and tested.
16. **Why inspect products/subscriptions after importing?** To ensure the API is visible and authorized only to the intended client groups.
17. **Why avoid importing directly into the current API from an unreviewed branch?** Risk of overwriting production operations/policies.
18. **Which revision event are release notes associated with?** Typically when a revision is released/made current in the APIM lifecycle.
19. **Does rolling back a revision roll back the database?** No.
20. **Does a new v2 version automatically stop v1?** No; both versions and backend compatibility must be managed.
21. **What should be tested after importing?** Operations, schemas, backend, auth, policies, gateway errors, and client contracts.
22. **How do you distinguish an APIM 404 from a backend 404?** By inspecting gateway/backend traces, operation matching, and logs.
23. **Why can lowering a rate limit be a breaking change?** Existing clients may exceed the quota and receive 429s.
24. **What is the risk of changing the versioning scheme after clients adopt it?** The URL/header/query contract changes, and proxies/caches may mismatch.
25. **Can v1 and v2 share the same backend?** Yes, when the backend supports both contracts or proper adapters.
26. **Why track release artifacts/checksums?** To verify exactly which spec was imported and enable recovery/reproducibility.
27. **Should OpenAPI/policies be managed in Git/IaC?** Yes, for review, auditing, and reducing drift.
28. **Is a non-current revision automatically protected from outsiders?** No; auth, subscriptions, and network controls are required.
29. **When should v1 be sunset?** After notice, the migration window, verifying client adoption, and meeting support obligations.
30. **What does a successful APIM release require beyond Make current?** Contract tests, security, backend connectivity, metrics, rollback readiness, and client compatibility.

## 24. References

- [Azure API Management documentation](https://learn.microsoft.com/azure/api-management/) — service, gateway, products, policies, and API lifecycle management.
- [Import and publish an API](https://learn.microsoft.com/azure/api-management/import-and-publish) — importing and testing an API.
- [Import restrictions and known issues](https://learn.microsoft.com/azure/api-management/api-management-api-import-restrictions) — format/spec limitations during import.
- [Versions in Azure API Management](https://learn.microsoft.com/azure/api-management/api-management-versions) — version sets and path/header/query versioning.
- [Revisions in Azure API Management](https://learn.microsoft.com/azure/api-management/api-management-revisions) — revisions, current revision, and release lifecycle.
- [API Management policies](https://learn.microsoft.com/azure/api-management/api-management-howto-policies) — policy scopes, inheritance, and gateway configuration.
- [Authentication and authorization in APIM](https://learn.microsoft.com/azure/api-management/authentication-authorization-overview) — gateway/backend/client authentication.
- [API Management REST API reference](https://learn.microsoft.com/rest/api/apimanagement/) — automation for managing APIs, versions, revisions, and releases.
- [Azure CLI az apim api reference](https://learn.microsoft.com/cli/azure/apim/api) — import, list, show, and supported operations.
- [Azure CLI az apim api versionset reference](https://learn.microsoft.com/cli/azure/apim/api/versionset) — managing API version sets.
- [Azure Monitor for API Management](https://learn.microsoft.com/azure/api-management/api-management-howto-use-azure-monitor) — metrics, logs, and diagnostics.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — HTTP API contract documentation standard.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — monitoring pricing and per-resource costs.

**Conclusion:** OpenAPI describes the contract; Azure API Management imports that contract into gateway-governed APIs/operations; **API versions** let multiple client contracts coexist, while **API revisions** let each version be modified and tested before becoming current. To release safely, **import into the exact target API ID/revision**, verify backend and policies, confirm version routing, run security/contract tests, measure client impact, and maintain rollback readiness for both APIM and backend/data. Never treat an “import succeeded” message or a “make current” click as proof that an API release is complete.
