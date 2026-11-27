# Subscriptions, API Products, and the Developer Portal

A development team has a REST API serving internal customers, partners, and mobile apps. They want to publish documentation, allow developers to register for access, issue credentials per application, throttle traffic, and revoke access when a contract ends. If they simply expose the backend URL publicly and share a single common API key, operations will struggle to know who is calling the API, revoke a single customer independently, or change policies without modifying code.

**Azure API Management (APIM)** helps manage the API publishing and consumption lifecycle with a **gateway**, **APIs**, **products**, **subscriptions**, **policies**, and a **developer portal**. In APIM, a product is a bundle of APIs and usage terms; a subscription represents an entitlement bound to a scope and can provide subscription keys; the developer portal is where users discover documentation, subscribe, and try calling APIs. These components complement each other, **but do not replace authentication/business authorization mechanisms** such as Microsoft Entra ID, OAuth 2.0, or backend-level authorization.

This lesson belongs to the **API and Workflow Integration** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, while teaching how to deploy, monitor, secure, and control application architecture costs. In this chapter, APIM sits between consumers and backends for **controlled publishing**, service integration, monitoring, and API developer experience management.

## 1. Learning objectives

After this lesson, you will be able to:

- Describe the **consumer → gateway → backend** flow and the role of the developer portal.
- Distinguish APIs, operations, products, groups, users, subscriptions, and subscription keys in APIM.
- Choose the appropriate subscription scope: **product, single API, or all APIs** based on requirements and governance boundaries.
- Design API products with publication state, subscription requirements, approvals, and access limits.
- Understand the subscription lifecycle: creation, approval requests, activation, suspension, revocation, and key rotation.
- Configure the developer portal so users can discover APIs, read OpenAPI docs, try API calls, and request subscriptions.
- Distinguish a **subscription key** from an OAuth2 access token, JWT, mTLS, and backend authorization.
- Apply rate limits, quotas, JWT validation, CORS, and monitoring at the right policy scopes.
- Build CI/CD/IaC workflows for APIs and products without leaking secrets.
- Troubleshoot issues such as 401/403, missing products in the portal, failed Try it calls, 429 rate limits, and 502 backend errors.

## 2. API Management architecture

~~~text
         API developer / partner
                  |
                  v
        Developer portal (docs,
        onboarding, subscription)
                  |
                  | Obtain credentials / understand API
                  v
          Client application
                  |
                  | HTTPS request
                  | Subscription key and/or JWT
                  v
        Azure API Management gateway
          +-----------------------+
          | API + operation route |
          | Subscription checks   |
          | Inbound policies      |
          | Backend forwarding    |
          | Outbound/on-error     |
          +-----------+-----------+
                      |
                      | HTTPS, private networking,
                      | backend auth if needed
                      v
             Backend: App Service /
             AKS / Functions / VM / API
                      |
                      v
                   Response
~~~

Three planes to recognize:

| Component | Primary function | Notes |
|---|---|---|
| **Management plane** | Define APIs, products, subscriptions, groups, users, policies | Configured via Azure RBAC and APIM management interfaces |
| **Gateway/data plane** | Receive requests, apply policies, call backends, return responses | Does not itself become a business backend |
| **Developer portal** | Documentation, registration, and trying API calls | Not the gateway and not a billing system by default |

The **APIM gateway** has a default hostname formatted as **<APIM_NAME>.azure-api.net** per service configuration; custom domains/TLS can be used depending on tier capabilities. The **Developer portal** has its own URL depending on portal type/configuration and is not the hostname for applications to send live API traffic.

### Difference between APIM and the backend

APIM can authenticate, validate tokens, cache, transform headers, enforce rate limits, and route traffic. The backend remains responsible for **business authorization checks**, transaction execution, data protection, and error handling. An API call with a valid subscription key does not mean the caller is allowed to view another account's invoices.

## 3. From APIs to products and subscriptions

Consider a set of APIs:

~~~text
APIM service: apim-contoso
|
+-- API: Catalog
|     +-- GET /products
|     +-- GET /products/{id}
|
+-- API: Orders
|     +-- POST /orders
|     +-- GET /orders/{id}
|
+-- API: Inventory
      +-- GET /stock/{sku}

Products:
  Catalog Starter  -> Catalog API
  Partner Commerce -> Catalog + Orders APIs
  Internal Ops     -> Orders + Inventory APIs

Subscriptions:
  mobile-store-subscription -> Catalog Starter
  partner-abc-subscription  -> Partner Commerce
~~~

An API can belong to **multiple products**; each product includes one or more APIs; and each consumer can hold **multiple subscriptions** serving different apps/packages. APIM **does not restrict an API to belonging to only one product**.

### Object comparison table

| Object | Meaning | Example |
|---|---|---|
| **API** | Defines interface, base path, backend, and operations | Orders API |
| **Operation** | HTTP method + URL template + schema/responses | `POST /orders` |
| **Product** | Bundle of APIs, description, policies, and subscription terms | Partner Commerce |
| **Group** | User group permitted to view/access a product per configuration | Partners |
| **User** | Developer identity in APIM | `developer@partner.example` |
| **Subscription** | Entitlement tied to a scope, owner, and state | `partner-abc-orders` |
| **Subscription key** | Credential used to prove subscription when keys are required | Primary/secondary key |
| **Policy** | Gateway logic to validate/transform/throttle requests | `rate-limit`, `validate-jwt` |

Note that **subscription here refers to an APIM subscription**, **not an Azure subscription** used for cloud billing. An Azure subscription is an Azure billing/management boundary; an APIM subscription is an API access object inside an APIM service.

## 4. What is an API product?

A **Product** packages a set of APIs for publishing to a specific customer segment or use case. A product can include:

- Display name, description, terms of use, and technical identifier.
- The set of APIs users can consume through the product.
- **Published / Not published** state.
- **Subscription required** setting.
- Optional **Requires approval** for subscription requests where supported.
- Product-scoped policies such as rate limits/quotas.
- Visibility/subscription eligibility by **groups** and portal configuration.
- Maximum subscriptions per user according to supported properties/features.

### Example tiering of packages

| Product | APIs | Subscription | Approval | Suggested policies |
|---|---|---|---|---|
| **Public Catalog** | Catalog GET | Can be optional by design | No | Throttle by IP/client, read-only |
| **Developer Sandbox** | Catalog + Orders sandbox | Required | Can be self-service | Low rate limit, mock backend |
| **Partner Commerce** | Catalog + Orders | Required | Yes | Per-subscription rate/quota, JWT validation |
| **Internal Operations** | Inventory + Orders admin | Required plus separate IAM | By workflow | Private networking, RBAC/JWT, audit |

This is an **illustrative design**, not default pricing or built-in APIM tiers. Naming a product “Premium” or putting a “price” in its description **does not automatically turn APIM into a payment processor, invoicing engine, or API billing system**. Selling commercial APIs requires separate contracting/billing and usage reconciliation solutions.

### Products are not pricing plans

Products express **access packages**, not payment processing. You can attach quota policies to a product, but charging fees, contracting, renewals, taxes, and invoicing must be handled by other systems if your organization requires them.

## 5. Published, subscription required, and requires approval

Three properties that are easily confused:

| Property | Meaning | Common misconception |
|---|---|---|
| **Published** | Product is published so authorized users can discover/subscribe | “Published” does not automatically make an API unconditionally public |
| **Subscription required** | Using APIs via the product requires a subscription key per APIM mechanics | Does not mean the end user is authenticated |
| **Requires approval** | Subscription requests must be approved before activation | Does not automatically approve commercial contracts or KYC |

An unpublished product may be hidden and unavailable for standard registration in the developer portal. However, **do not treat portal state as the sole security boundary**: you must still evaluate API-level settings, subscriptions at other scopes, access restrictions, policies, and the backend.

A product with **subscription not required** can be called under gateway/API access rules without a product subscription key. In that case, you still need **JWT/OAuth, mTLS, IP restrictions, backend authorization, or another mechanism** if the API is not meant for anonymous access.

### Controlled product approval workflow

~~~text
Developer sees product in portal
      |
      v
Reads docs / terms of use
      |
      v
Submits subscription request
      |
      +-- No approval required --> Activated per configuration
      |
      +-- Requires approval --> Pending / reviewed
                                   |
                            Approve or Reject
                                   |
                                   v
                            Subscription active
                                   |
                            Issue/display key
~~~

Exact UI steps and states depend on the portal and APIM service configuration. For customers requiring legal contracts, place an **external approval workflow** ahead of an administrator activating the subscription.

## 6. What subscription scopes exist in APIM?

APIM supports different subscription scopes depending on the service's management model, typically including:

| Scope | Behavior | When appropriate |
|---|---|---|
| **Product scope** | Grants access to APIs exposed through a specific product | Partner subscribes to a package needing clear quotas/plans |
| **Single-API scope** | Direct access to one API without necessarily requiring product enrollment | Internal app integrating with one specific API |
| **All-APIs / service scope** | Broad access across APIs in the APIM service per supported model | Trusted administrative/integration systems, tightly restricted |

**Broad-scoped subscriptions are not equivalent to product approval.** An all-APIs key can access more APIs than intended for a partner group. If granted broadly, every newly added API may expand the access surface for that client depending on APIM configuration.

APIM may include built-in/special subscriptions created by the platform for administrators/testing depending on the current model. **Never place an administrative or all-access key inside a customer application** just because it makes testing easier.

### One user can hold multiple subscriptions

A developer can have:

- A subscription for the mobile sandbox app.
- A subscription for the production commerce backend.
- A subscription for a private API they are authorized to pilot.

Manage **subscriptions per application, environment, and usage purpose**, instead of issuing one shared key to all partners. When Partner A needs to be revoked, Partner B should remain unaffected.

## 7. Primary key and secondary key

For APIM subscriptions requiring a key, the service provides a **primary** and **secondary subscription key** so clients can rotate credentials with minimal downtime.

~~~text
Subscription: partner-abc-prod
    |
    +-- Primary key (currently used by client)
    |
    +-- Secondary key (backup key / used for rotation)
~~~

Both keys carry **identical permissions within the same subscription**; primary does not grant write access while secondary only grants read. Which key is sent in a request does not change the granted product/API scope.

### Common header pattern

~~~http
GET /catalog/products HTTP/1.1
Host: <APIM_GATEWAY_HOST>
Ocp-Apim-Subscription-Key: <VALID_SUBSCRIPTION_KEY>
Accept: application/json
~~~

The default header is typically **Ocp-Apim-Subscription-Key**. APIM can allow configuring header/query parameter names per API or passing keys via query string, **but secrets should never be passed in URLs** because they end up in logs, browser history, monitoring/referrers, and link-sharing tools.

### Zero-downtime rotation by design

1. Inventory clients using the primary key and their dependencies.
2. Confirm the secondary key is valid or regenerate the **unused key**.
3. Deliver the secondary key via a secure secret manager and update clients.
4. Monitor traffic/401s and verify all clients have switched to the secondary key.
5. Regenerate the old primary key once the transition window ends, invalidating it.
6. Record the audit trail, update the runbook, and schedule the next rotation.

**Never regenerate both keys at the same time** without a plan to migrate all clients. Regenerating a key immediately rejects any client still presenting that key once the change takes effect.

Never commit keys to Git, embed them directly in public frontend JavaScript, Dockerfiles, or screenshots; a **subscription key is a secret**, even though it is not an OAuth access token.

## 8. Subscription lifecycle and revocation rights

A subscription has an owner/scope, display name, keys, and state. Depending on the API/portal/management model, states can include **Submitted/Pending**, **Active**, **Suspended**, **Rejected**, **Cancelled**, or equivalent statuses.

Operational actions:

| Action | When to use | Impact to verify |
|---|---|---|
| **Create/request** | Developer wants to use a product/API | Pending approval or active per policy |
| **Approve/activate** | Passed onboarding/terms | Client can use key if gateway/other auth permits |
| **Suspend** | Temporarily block for violation/overdue status | Requests relying on that subscription are impacted |
| **Reactivate** | Issue resolved and approved | Audit trail and restored access |
| **Regenerate key** | Leaked credential / scheduled rotation | Clients using the old key must update |
| **Cancel/delete** | Contract ended / account cleanup | Avoid losing audit records required by policy |

In many scenarios, an administrator can issue an **API-scoped subscription** directly without the user self-registering via the developer portal. Thus, “not seeing a Subscribe button” does not mean no subscription exists or can be created through the management plane.

### When a key leaks

Runbook:

1. Assess the subscription's scope and which clients use it.
2. If there is immediate risk of abuse, suspend the subscription or rotate the key based on security/availability priority.
3. Inspect gateway logs, rates, IPs, API operations, and anomalous timestamps.
4. Never paste the full key into incident tickets or investigation logs.
5. Distribute the replacement key via an audited secret vault.
6. Add IAM/network/token validation to limit blast radius if a key leaks again.

For subscription keys used in browsers/mobile apps, revisit the architecture: secrets embedded in end-user distributed apps are very hard to keep confidential. Use a backend-for-frontend or token-based access to avoid placing sensitive credentials inside public clients.

## 9. API products and group membership

APIM provides a **groups** model to control visibility and subscription access to products per portal and subscription workflow settings.

Common built-in groups include **Administrators**, **Developers**, and **Guests**; custom groups or external group/identity integrations can also be used depending on supported features and authentication models.

~~~text
User: developer@partner.example
        |
        v
Group: Partners
        |
        v
Visible Product: Partner Commerce
        |
        v
Subscription request/approval
        |
        v
Subscription key with product scope
~~~

### Group visibility and gateway authorization are different

Assigning a product to the `Partners` group controls **who can discover/subscribe to the product via the APIM developer experience** per configuration. However, **group membership does not satisfy backend authorization requirements**, and group visibility alone must not be relied upon to protect data.

For example, combine:

- Valid APIM subscription at the right scope.
- OAuth/JWT to identify the application/user.
- Scope/role/claim validation at the gateway and backend.
- Tenant-level authorization to prevent Partner A from viewing Partner B's data.
- Network restrictions when APIs are internal.

If a partner is removed from a group while still holding an active subscription or a key issued at another scope, explicitly inspect and revoke actual access. **Removing a user from a group does not automatically revoke all keys or tokens.**

## 10. What is the Developer portal?

APIM's **Developer portal** is the interface for people building applications against your APIs. Typically, the portal provides:

- Catalog of APIs and products visible to the user.
- Endpoint documentation, operations, parameters, and response schemas.
- OpenAPI descriptions and request/response examples.
- Onboarding content, terms, integration guides, and code examples.
- Subscription/key registration and management based on roles and settings.
- **Try it** feature to test API requests through the APIM gateway.
- Customizable pages for branding, navigation, documentation, and supported integrations.

The portal **is not the API execution engine**. When a user clicks **Try it**, the request still goes to the **APIM gateway**; depending on the API, they still need a subscription key, OAuth/JWT, or other authorization.

### Managed portal, self-hosted portal, and supported features

APIM offers an Azure-managed developer portal experience alongside deployment/customization capabilities that vary by tier/version. Self-hosting the portal can require operating hosting, updates, CORS, authentication, and integration configurations yourself. **Do not assume every APIM tier supports the same developer portal and custom domain features**; verify your selected service tier and current documentation.

### Before publishing the portal

1. Verify domain, HTTPS/TLS certificates, and routing.
2. Configure identity providers and registration/sign-in policies.
3. Expose only approved APIs/products.
4. Remove examples containing secrets or undisclosed internal backend URLs.
5. Add Terms of Service/privacy notices and support contact details.
6. Test with a real least-privileged developer account, not just an admin account.

## 11. Onboarding developers from sign-up to first request

An external workflow for a partner:

~~~text
Partner receives invitation / onboarding docs
       |
       v
Opens developer portal over HTTPS
       |
       v
Signs up or signs in with supported identity
       |
       v
Reads API reference + products + terms
       |
       v
Selects Partner Commerce, submits subscription request
       |
       +-- Pending approval -> administrator reviews
       |
       v
Subscription Active -> retrieves key securely
       |
       v
Calls API via gateway with key and JWT if required
       |
       v
Monitors 200/401/403/429, quotas, and support
~~~

### Enterprise processes to clarify

- Who approves partners, and which contract/tenant checks are required?
- Can one person register multiple applications/subscriptions?
- Which products apply to sandbox vs. production?
- How are keys distributed, stored in a secret vault, and rotated on schedule?
- How are breaking-change docs communicated?
- Who can suspend a subscription and approve reactivation?
- When a user leaves the partner company, who owns and manages the subscription?

Do not just email a key and consider onboarding complete. A sound model needs **owners, auditing, support, a test environment, and a revocation process**.

## 12. Configuring products via the Azure Portal

Assume a **lab APIM service** already exists, and a **Catalog** API has been imported or created from OpenAPI. The goal is to create a partner product and test registration.

### Step 1: select the right APIM service

1. Go to the [Azure Portal](https://portal.azure.com) and select the right subscription/resource group.
2. Open **API Management services** and choose the test instance.
3. Check the **tier**, region, gateway hostname, network access, and current administrative permissions.
4. Go to **APIs** and verify the Catalog API has valid operations and backend URL.
5. Check whether the API requires a subscription, its base path, and inherited policies.

Do not modify a production APIM instance just because the lab lacks a product. Policy/subscription changes can impact all consumers.

### Step 2: create the product

1. In APIM, locate **Products**.
2. Select **Add/Create product** per the current UI.
3. Enter name **Partner Catalog**, product ID, description, and terms of use.
4. Enable **Subscription required**.
5. Enable **Requires approval** if administrator review is needed.
6. Set state to **Published** when ready to publish.
7. Save the product.

Example properties:

~~~text
Display name: Partner Catalog
Product ID: partner-catalog
Description: Product catalog API for approved partners
Subscription required: true
Approval required: true
State: published
Subscription limit: per requirements and supported features
~~~

### Step 3: attach API and group

1. Inside the **Partner Catalog** product, add the **Catalog API**.
2. Add the **Partners** group or an appropriate test developer group.
3. Do not grant the product to **Guests** if the API is not meant for anonymous onboarding.
4. Verify the product is published and visible to a user in that group.
5. Check that backend/gateway policies do not allow unintended scope escalation.

### Step 4: add usage policies

Set appropriate rate/quota limits, starting low for sandbox. Carefully review existing global/API/operation policies to avoid duplicates or unintended overrides.

### Step 5: test with a developer user

Sign in to the portal as a **non-Administrator** user. Verify:

- The product is visible when the user belongs to the proper group.
- Users outside the group cannot self-subscribe to the product per expected workflow.
- Subscription requests require approval if enabled.
- After approval, the key successfully calls the Catalog API.
- The key cannot access other APIs outside its scope.
- The gateway still checks JWT/backend permissions if policies require them.

**Access must be proven with comparative testing**, not merely by checking whether the Subscribe button appears.

## 13. Importing and publishing the API before adding it to a product

A product does not replace an API definition. Before developers can use an API, a proper **API definition** must exist:

| API property | Example | Why it matters |
|---|---|---|
| **API display name** | Catalog API | Friendly name for developers |
| **API ID** | `catalog-v1` | Stable identifier for IaC/policies |
| **API URL suffix** | `catalog` | Gateway routes paths under `/catalog/...` |
| **Web service URL/backend** | `https://catalog.internal.example` | Target where the gateway forwards requests |
| **Operations** | `GET /products`, `GET /products/{id}` | Routes/schemas documented in the portal |
| **Subscription settings** | Required/optional per API/product | Affects request validation |
| **OpenAPI document** | Supported OpenAPI 3.x | Documentation and Try it |

Example OpenAPI **snippet with full core structure** for a GET operation:

~~~yaml
openapi: 3.0.3
info:
  title: Catalog API
  version: 1.0.0
servers:
  - url: https://api.example.test
paths:
  /products:
    get:
      operationId: listProducts
      summary: List products
      responses:
        "200":
          description: Product list returned
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: string
                    name:
                      type: string
~~~

**`api.example.test`** is an illustrative address, not an already-provisioned backend. When importing OpenAPI into APIM, verify the gateway path, backend URL, query/header names, request/response schemas, and inherited policies. A successful import does not validate backend permissions.

### API revisions and versions differ from products

APIM supports **API revisions** and **API versions/version sets** in supported scenarios:

- **Revisions** adjust definitions/policies without necessarily changing the public contract version.
- **Versions** express distinct API contracts, such as **v1/v2**.
- **Products** group APIs and define consumption terms.
- **Subscriptions** grant consumption rights by scope.

Do not name a product “v2” and assume you have versioned the endpoint. Product plans and API contract versions have separate lifecycles; retiring v1 requires proper notifications, migration, and revocation policies.

## 14. Subscribing and testing requests

A developer granted the **Partner Catalog** product with an **Active** subscription can call the gateway at the endpoint published by APIM.

Bash example:

~~~bash
GATEWAY="<APIM_GATEWAY_HOST>"    # e.g. myapim.azure-api.net
SUBSCRIPTION_KEY="<TEST_KEY>"    # retrieved from a lab secret store

curl --fail-with-body --silent --show-error \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY" \
  -H "Accept: application/json" \
  "https://$GATEWAY/catalog/products"
~~~

**Note:** depending on your local `curl` version, **`--fail-with-body`** may not be supported; you can use **`curl -i`** to inspect the status. Never store real keys in scripts/repositories or print them to stdout. In shared environments, use a secret store and avoid shell tracing.

### Interpreting results

| Result | What it may indicate | Next check |
|---|---|---|
| **200 OK** | Key and applicable policies accepted the request | Is business data accurate, and is anything leaked? |
| **401 Unauthorized** | Missing/wrong key or JWT/auth policy rejected | Gateway response, auth headers, scope, token |
| **403 Forbidden** | Subscription inactive/insufficient permissions, or access policy denied | Subscription state, product/API scope, JWT roles, network |
| **404 Not Found** | API operation/path mismatch or backend returned 404 | API URL suffix, revision, operation template, backend logs |
| **429 Too Many Requests** | Rate-limit/quota policy may be blocking | Policy, counter key, reset window, `Retry-After` if present |
| **502/503** | Backend/gateway unreachable or unavailable under current conditions | Backend URL, TLS, DNS, VNet, health, and logs |

Status codes alone do not identify a single root cause; gateway policies can customize statuses/responses. Use correlation IDs, traces/logs, and backend checks.

### Testing without a key

~~~bash
curl -i "https://<APIM_GATEWAY_HOST>/catalog/products"
~~~

If the API/product requires a subscription, a keyless request is normally rejected by APIM. However, **a keyless request succeeding** can mean the API/product allows anonymous access, policies changed, or traffic bypassed the expected route; verify every case.

### Testing with a key from another product

Use a subscription dedicated to **Catalog Starter** and attempt an API belonging only to **Internal Ops**. Expect rejection **if that key lacks the required scope and the API is not exposed via another product/API**. If an all-APIs key or another product/API grants access, the result differs; verify actual entitlements rather than relying on key names.

## 15. A subscription key is not an OAuth access token

One dangerous misconception is treating a subscription key as proof of **who the end user is**.

| Aspect | APIM subscription key | OAuth 2.0 / JWT access token |
|---|---|---|
| Primary role | Proves an APIM subscription | Carries claims about client/user, issuer, audience, scopes/roles |
| Issuance | APIM generates or manages subscription/keys | Identity provider / token endpoint |
| Expiration | Follows subscription key lifecycle/rotation | Follows token `exp` / validity and IdP policy |
| Scope | API/product/all-APIs per subscription | Resources, scopes, roles, claims |
| Control | Active/suspended/key regeneration | Issuer/audience/scope validation, revocation strategy |
| Risk | Shared secret can be copied | Token can leak/be abused; requires signature and claim validation |

A partner holding a valid key **must not automatically be allowed to view every order**. **`tenantId`, `userId`, and scopes/roles** must be checked according to the security design, and the backend must enforce business authorization.

### Layering multiple controls

~~~text
Request:
  Ocp-Apim-Subscription-Key: Partner ABC's subscription
  Authorization: Bearer <ACCESS_TOKEN>
           |
           v
APIM:
  1. Is subscription scope permitted?
  2. Are JWT issuer/audience/signature/expiry valid?
  3. Are rate-limit/quotas satisfied?
  4. Is header forwarding safe?
           |
           v
Backend:
  5. Do principal/tenant/scopes allow the action?
  6. Which tenant owns the target object ID?
~~~

**Object-level authorization in the backend remains essential.** Never trust a client-supplied **`tenantId`** query parameter as proof that the caller belongs to that tenant.

## 16. OAuth 2.0 and developer portal sign-in are two separate problems

A developer may sign in to the portal via **Microsoft Entra ID** or a supported identity provider to browse docs and subscriptions. That is **developer portal sign-in**. When an API is protected by OAuth 2.0, client applications still need an **access token targeted at that API/resource**.

| Activity | Identity involved | Notes |
|---|---|---|
| Signing in to developer portal | Developer account (configured IdP) | Controls portal user experience |
| Requesting product subscription | APIM user/group/approval workflow | Controls entitlement |
| Using Try it on an OAuth API | OAuth client/authorization server/token flow | Requires configuring portal to acquire tokens with right audience/scopes |
| Calling production API from an app | Client application/service principal or end user | Backend authorization must still run |

**Signing in to the portal successfully does not automatically mint a Bearer token to call every API.** Conversely, an app holding a valid token may still lack an APIM subscription key if the product/API requires registration.

### Configuring Try it with OAuth

To allow users to test an OAuth-protected API:

1. Configure an **authorization server/OAuth integration** or token acquisition experience per current portal/APIM capabilities.
2. Register the client application with the identity provider and exact redirect URI.
3. Choose the appropriate flow (e.g., authorization code + PKCE for public clients).
4. Define the audience/scopes/permissions to request.
5. Configure the API security scheme so the portal attaches the token in the **Authorization** header.
6. Test with an authorized developer account rather than using a global admin as proof.

Never place a confidential client's **client secret** in public JavaScript. For browser/public clients, use flows that do not store client secrets (such as PKCE) per current guidance.

## 17. Policies and inheritance scopes

APIM policies are gateway rules executed across pipeline stages:

- **Inbound:** authentication, rate limiting, URI rewriting, `set-header`, IP filtering, cache lookup.
- **Backend:** how requests are forwarded to or routed among backends.
- **Outbound:** response header edits, cache storage, transformations.
- **On-error:** error handling, telemetry, custom responses per policy.

Policies can be attached at scopes such as **global (all APIs)**, **product**, **API**, and **operation** per supported model. When an API belongs to multiple products or a request does not arrive via a product subscription, **whether a product policy applies depends on the subscription/routing context**—do not assume product policies always execute on every path to an API.

### Inheritance via the base element

Conceptual example of **policy XML structure**:

~~~xml
<policies>
  <inbound>
    <base />
    <set-header name="x-api-channel" exists-action="override">
      <value>partner</value>
    </set-header>
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

**`<base />`** generally marks where policies from parent scopes are inherited. Omitting `<base />` or misordering it can bypass expected global/API-scope controls or alter behavior. **Never push policies to production without reviewing the effective policy**, especially when an API spans multiple products or enforces token validation.

### Policies do not exempt backend validation

For example, APIM can check headers and JWTs, yet the backend must still verify **whether the user/tenant may access a specific resource ID**. An APIM rate limit does not replace SQL injection defenses, and a CORS policy is not authentication.

## 18. Request throttling by subscription

Two common controls:

| Policy | Meaning | Example |
|---|---|---|
| **Rate limit** | Limits request count over a short window | 100 calls per 60 seconds |
| **Quota** | Limits total calls/bandwidth over a billing/usage period | 10,000 calls per day |

APIM provides policies such as **rate-limit**, **rate-limit-by-key**, **quota**, or **quota-by-key** depending on tier/gateway and supported scope. Counters can bind to a subscription or another identifier expression.

### Rate limiting by subscription

Illustrative XML for a gateway-supported policy:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="60"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? &quot;anonymous&quot;)" />
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

This is a **conditional example**: the expression uses `context.Subscription.Id` when a subscription exists; if a product does not require a subscription and receives anonymous traffic, **all anonymous requests share the same counter key**, rather than per-caller limits. For production, base the policy on a **verified token principal ID, client app ID, or subscription identity**, and check the gateway/tier support matrix.

**Never use an unverified header like `x-user-id` as `counter-key`**: callers can spoof different values to evade throttling. With JWTs, use claims only after the token has been validated.

### Distributed rate limits are approximate

Across multi-region APIM, self-hosted gateways, or multiple gateway units, counters have specific synchronization/update characteristics. **Do not promise an exact 60-request global cutoff down to the millisecond** without verifying the product's consistency model. Gateway limits are a protective layer; backends must still handle load and protect sensitive resources.

### HTTP 429

When a rate/quota threshold is exceeded, APIM typically returns **429 Too Many Requests**, depending on policies and customizations. Clients should:

- Read **`Retry-After`** or provided headers when present.
- Back off with jitter rather than hammering with tight retries.
- Limit concurrency and batch/cache where appropriate.
- Never rotate across multiple subscription keys to circumvent quotas in violation of terms.

## 19. Blocking invalid tokens with validate-jwt

To enforce user/client authentication, APIM supports JWT validation policies per supported configuration. **Illustrative** `validate-jwt` example:

~~~xml
<policies>
  <inbound>
    <base />
    <validate-jwt header-name="Authorization"
                  require-scheme="Bearer"
                  failed-validation-httpcode="401"
                  failed-validation-error-message="Unauthorized">
      <openid-config
        url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>api://API_APPLICATION_ID</audience>
      </audiences>
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

Replace **TENANT_ID** and **API_APPLICATION_ID** with your actual Entra ID settings; the API audience may be an App ID URI or client ID depending on how the resource server is registered. Verify policy schema/tier, issuer, algorithm, token lifetime, required claims, and cloud environment. The example above **does not yet check specific scopes/roles**; for least privilege, add claim checks in APIM and/or the backend as appropriate.

### Avoid overly permissive configurations

- Do not accept tokens whose audience belongs to a different API.
- Do not merely check that a JWT has three dot-separated segments while skipping signature/issuer checks.
- Do not accept any arbitrary issuer when the organization permits only a single tenant/issuer.
- Do not grant tenant data access solely because a token is valid.
- Do not log the full `Authorization` header or token for debugging.

A valid access token does not guarantee permission for **`POST /orders`**. The backend or gateway must verify scopes/roles, tenant identity, and resource-level authorization.

## 20. CORS and the Try it experience in the developer portal

The **Try it** button normally executes requests from a browser. Browsers may block requests due to **CORS** when the developer portal's origin differs from the APIM gateway's origin.

~~~text
Browser at https://portal.example.test
      |
      | Request to https://api.example.test
      v
Browser performs preflight if required
      |
      v
APIM CORS policy -> Allowed origins/methods/headers?
      |
      +-- Allowed -> actual API request
      |
      +-- Blocked -> browser reports CORS error
~~~

### Illustrative CORS policy

~~~xml
<cors allow-credentials="false">
  <allowed-origins>
    <origin>https://portal.example.test</origin>
  </allowed-origins>
  <allowed-methods>
    <method>GET</method>
    <method>POST</method>
  </allowed-methods>
  <allowed-headers>
    <header>authorization</header>
    <header>ocp-apim-subscription-key</header>
    <header>content-type</header>
  </allowed-headers>
</cors>
~~~

This is a **policy fragment**, not a complete XML policies document. Place it in **`inbound`** according to APIM's inheritance/scope rules, and verify the portal's real origin along with required headers and preflight behavior.

**CORS is not an authorization system**: server-side clients such as `curl` are not constrained by browser CORS sandboxing. Never treat `allowed-origins` as a security boundary for APIs handling sensitive data. Use real JWT/permission/network protections.

### Try it fails while curl succeeds

Check:

1. Browser DevTools: is it a CORS/preflight failure or an actual HTTP 401/403?
2. Is the portal calling the **right gateway hostname** rather than an internal backend?
3. Does `allowed-origins` match the developer portal's custom domain?
4. Does the APIM policy allow **`Ocp-Apim-Subscription-Key`** and **`Authorization`** headers?
5. Does the token have the right audience/scope, and is the subscription active?
6. Do network restrictions/private gateway settings allow public browser access?

Never open wildcard origins or expose secrets to the client just to make the Try it button work.

## 21. Backend authentication and preventing bypass paths

APIM protects an API **only when requests actually flow through the gateway**. If an App Service/Functions backend remains public at its default URL without independent authorization, callers can bypass APIM subscription checks and rate limits.

~~~text
Client --> APIM Gateway --> Backend API     (managed path)

Client -----------------> Backend API     (bypass path if backend is open)
~~~

Mitigations:

- Restrict backend ingress via private networking, VNet Integration, Private Endpoints, access restrictions, or supported controls.
- Authenticate **APIM → backend** with managed identity, mTLS, OAuth, or managed backend credentials.
- Never trust internal headers simply because a client sent the same header name; the backend must verify source or cryptographic identity.
- Enforce HTTPS/TLS and certificate rotation procedures.
- Verify routing when backends run on AKS, Functions, App Service, or on-premises networks.

### Managed identity from APIM to backend

In supported configurations, APIM can use **managed identity** to obtain an access token when calling a backend Azure resource/API protected by Entra ID. When designing, check:

1. APIM identity is enabled.
2. The backend/identity provider recognizes the API's resource audience.
3. APIM has been granted the proper role/app permission.
4. The **`authentication-managed-identity`** policy is at the right scope and supported for token acquisition.
5. The backend properly validates token/issuer/audience/authorization.

Do not treat the subscription key as a default backend credential. Subscription keys are presented by clients for APIM gateway entitlement checks; backends should have their own authentication mechanism where needed.

## 22. Product policies and API policies can interact

Suppose **Catalog API** belongs to both Product A and Product B:

~~~text
Catalog API
   |
   +-- Product A (quota 10,000/day)
   |
   +-- Product B (quota 100,000/day)
~~~

When a client uses a valid **product-scoped subscription**, the request is governed by that product's policy alongside global/API/operation policies in the effective pipeline. However, if a client uses an **API-scoped or all-APIs subscription**, do not assume the gateway picks Product A or B to enforce limits.

### Designing to avoid policy gaps

- Place **mandatory baseline controls** such as authentication/JWT validation at the proper scope (global/API/operation) so protection never depends on a product-specific subscription context if all requests must be secured.
- Place **commercial/tier-specific quotas** at product scope when request entitlement flows through a product.
- Verify the **effective policy** across product keys, API keys, all-access keys, and anonymous calls.
- Avoid duplicating rate policies across multiple scopes unintentionally, which can create extra counters or unexpected results.
- Write tests proving keys from a narrow product cannot call operations outside their scope.

**Subscription scope is part of your authorization and policy execution model.** Designing neat products in the Portal is not enough if an API-scoped key or another policy scope creates an unintended path.

## 23. Administering the developer portal securely

The portal carries the company's branding and is often a partner's first touchpoint. Because it can expose documentation, subscriptions, and credentials, govern it like an application holding sensitive data.

### Layers of protection

| Layer | Recommended control |
|---|---|
| **Identity** | Choose a supported sign-in provider, preferring Entra ID or corporate IdP |
| **User lifecycle** | Invitation, approval, offboarding departing users, revoking subscriptions |
| **Groups** | Bind products to groups; test visibility with real user accounts |
| **Secrets** | Never put primary/secondary keys in docs, analytics, or screenshots |
| **TLS** | HTTPS, custom domain certificates, and rotation where applicable |
| **Content** | Version-control guides and API breaking-change warnings |
| **Try it** | CORS, token acquisition, and avoid hitting production data from risky examples |
| **Audit** | Track changes to users, products, subscriptions, and policies |
| **Support** | Support contact, SLA, terms, status page, deprecation notices |

### Portal content must be published intentionally

An OpenAPI document may contain examples with tokens, database URLs, or PII fields. Before publishing:

- Remove all real credentials.
- Use fake domains and user IDs in examples.
- Document HTTP statuses, pagination, retries, and request limits.
- Separate **sandbox URLs** from **production URLs**.
- State API versions, deprecation/sunset dates, and migration steps if applicable.
- Verify internal operations did not accidentally leak into a public product.

### Governing portal editor permissions

Developers consuming the portal should not have rights to alter APIM management plane settings. Content/website administrators should receive role-based permissions within supported scopes; tightly restrict who can modify **APIs, policies, products, and subscription states** in the Azure Portal. Record change reviews and audits when publishing new documentation.

## 24. Configuring via IaC instead of only clicking in the Portal

When operating multiple APIM services (dev/staging/prod), manual product edits easily introduce drift:

~~~text
Dev:
  Partner Commerce -> Catalog + Orders
  subscriptionRequired=true
  quota=10,000

Prod:
  Partner Commerce -> Catalog only (missing Orders bug)
  subscriptionRequired=false   (policy bug)
  no quota                     (drift bug)
~~~

Manage configurations using **Infrastructure as Code** or APIM automation per organizational standards:

- API definitions/OpenAPI documents and API versions/revisions.
- Product IDs, display names, descriptions, and published state.
- Product ↔ API and product ↔ group associations.
- Global/product/API/operation policies.
- Backend definitions and named values (preferring Key Vault references for secrets).
- Diagnostics, logs, tags, and alert configurations.
- Developer portal content/configuration where supported by tooling.
- Subscription lifecycles involving sensitive credentials, governed via dedicated workflows rather than committing keys to Git.

### Bicep example declaring a product

A **Bicep snippet** describing an APIM product; place it in a parameterized module and verify the supported `apiVersion` at deployment time:

~~~bicep
param apimName string
param productId string = 'partner-catalog'

resource apim 'Microsoft.ApiManagement/service@2022-08-01' existing = {
  name: apimName
}

resource product 'Microsoft.ApiManagement/service/products@2022-08-01' = {
  parent: apim
  name: productId
  properties: {
    displayName: 'Partner Catalog'
    description: 'Catalog API for approved partners'
    state: 'published'
    subscriptionRequired: true
    approvalRequired: true
    subscriptionsLimit: 1
  }
}
~~~

This is a **product resource declaration sample**; it **does not yet link APIs or groups** and does not create a complete onboarding system. Add resources/automation for API associations, group associations, and policies per current schema versions. **Never place subscription primary/secondary keys in Bicep**, as secrets can leak via source control, deployment history, or state files.

### API versioning and product ID stability

Changing product IDs frequently can break subscriptions and portal links. Distinguish:

- **Technical ID** used as a reference in IaC/APIs.
- **Display name** shown to developers, which can be updated as designed.
- **API version** defining the request/response contract.
- **Product version/tier** representing a business/entitlement decision, not necessarily matching API versions.

When updating product/API associations, never delete an old product before auditing active subscriptions.

## 25. Operating multiple APIM environments

An enterprise typically runs API backends across dev/staging/prod. Using the same APIM service and product for every environment creates risks:

- A testing partner might accidentally hit the production backend.
- A dev rate-limit policy impacts live clients.
- A key issued for sandbox grants access to production APIs under an uncontrolled scope.
- The developer portal mixes v1/v2 docs and environments.

### Isolation pattern

~~~text
Git / IaC + approved API definitions
             |
      +------+------+----------------+
      |             |                |
      v             v                v
 APIM DEV       APIM STAGING      APIM PROD
  Product A       Product A         Product A
  Dev key         Staging key       Production key
  Dev backend     Staging backend   Prod backend
  Dev portal      Staging portal    Production portal
~~~

This is a reference architecture. Running three separate APIM instances can carry significant cost depending on tier/SKU. Some organizations use a shared APIM service with strict API/product partitioning and policies; in that case, assess **risk, isolation, management plane permissions, networking, and lifecycle**.

### Settings that must differ

| Component | Dev/staging | Production |
|---|---|---|
| Backend endpoint | Test/mock/sandbox | Real business endpoint |
| Subscription | Dedicated test keys | Keys with approval/rotation processes |
| OAuth audience/issuer | Test app registrations | Prod app registrations |
| Quota/rate | Used to stress-test limits without breaking backend | Aligned with SLA/contract and capacity |
| Logging | Can be more verbose without exposing secrets | Capture minimum useful telemetry, compliant with data policies |
| Developer portal | Test content, no production guarantees | Official docs/versions/ToS |
| IaC approval | Automated build/test | Change review and rollback |
| Identity/network | Sandbox RBAC | Least privilege, private connectivity when needed |

**An environment variable named `APP_ENV` does not create isolation.** Verify actual subscription keys, identities, product scopes, and backend targets in every environment.

## 26. Monitoring subscriptions, products, and the gateway

Key signals for an API platform:

| Signal | Operational question |
|---|---|
| Request count/RPS | How much traffic flows through APIM? |
| HTTP 4xx/5xx | Are errors from clients, policies, or backends? |
| 401/403 | Spike in key/JWT errors or IAM changes? |
| 429 | Is a product/client exceeding rates/quotas? |
| Gateway vs. backend latency | Is the bottleneck a policy or the backend? |
| Subscription usage | Which tier/consumer needs limit consultation? |
| Backend availability | Can APIM not reach the backend, or is the backend failing? |
| Cache hit/miss if used | Is backend load reduced as expected? |
| Changes to policies/products | Who edited configuration before errors began? |
| Portal usage | Are developers finding docs and completing onboarding? |

**Azure Monitor**, API Management diagnostics, and Application Insights/Log Analytics can help depending on integration level and tier. Do not assume a specific metric or dimension is available across every SKU/region/gateway topology.

### Logging principles

- Never log **`Ocp-Apim-Subscription-Key`**, `Authorization` headers, client secrets, cookies, or PII.
- Configure appropriate retention and access controls.
- Propagate a safe correlation/request ID between gateway and backend.
- Separate APIM management Activity Logs from runtime gateway traffic logs.
- When investigating rates/quotas, log **scope, subscription ID, or a hashed/tokenized identity** rather than the raw key.
- Verify the Log Analytics schema before writing KQL, as table/column names vary with diagnostics settings.

### Interpreting a 401 spike

A surge in HTTP 401s right after a key rotation may indicate:

1. A client is still sending the old key.
2. The API enabled `subscription required` or the product scope changed.
3. JWT access tokens have a wrong audience/issuer or expired.
4. Requests are hitting a different revision/host.

Analyze **gateway responses, policy traces/correlation, subscription IDs, deployment timelines, and client versions**. Do not hastily enable anonymous access in production.

## 27. CI/CD pipeline for API products and the portal

An APIM pipeline should not deploy API definitions while forgetting product membership.

~~~mermaid
flowchart TD
  A[Commit OpenAPI + product IaC + policy] --> B[Schema lint + security checks]
  B --> C[Deploy APIM dev]
  C --> D[Attach API to product + groups]
  D --> E[Test subscription + JWT + negative cases]
  E --> F[Staging approval]
  F --> G[Deploy staging + portal/docs review]
  G --> H{Production approval?}
  H -- No --> I[Stop, remediate]
  H -- Yes --> J[Deploy prod with versioned config]
  J --> K[Smoke tests, monitoring, notify developers]
  K --> L{Healthy?}
  L -- No --> M[Rollback policies/API config safely]
  L -- Yes --> N[Record release]
~~~

### Mandatory test cases

- Product is published and visible only to permitted groups.
- Non-group users cannot self-subscribe to sensitive products per workflow.
- An active product subscription can call APIs within scope.
- An API/product subscription cannot call APIs outside its entitlement.
- Suspended/regenerated keys are rejected (verified in test environment).
- Missing, wrong-audience, or expired JWTs are rejected per policy.
- CORS permits only exact origins/headers.
- Rate limits/quotas trigger 429 under configured conditions.
- Backend bypass paths are blocked by design.
- Portal Try it works with a test identity without using admin secrets.
- Logs contain no keys/tokens.

**Never test quotas by blasting destructive load at a production API.** Use a sandbox and rate-limited tools within approved thresholds.

### Rollbacks must account for subscription lifecycles

Reverting to an older product/policy definition does not delete already-issued subscriptions or restore rotated keys. Deleting and recreating a product can alter associations and permissions. Instead:

1. Version and store API/policy/product configurations prior to rollout.
2. Inventory subscriptions, products, and associations that must be preserved.
3. Modify only approved objects with a clear revert path.
4. If a new configuration over-exposed permissions, prioritize restoring protective policies first.
5. Re-test access with control identities after rollback.

## 28. Real-world scenario A: partner reports 401 after receiving key

**Context:** Partner ABC was approved for the `Partner Commerce` product and received the primary key in a secret vault. They call:

~~~http
GET /orders/123 HTTP/1.1
Host: <APIM_GATEWAY_HOST>
Ocp-Apim-Subscription-Key: <PARTNER_ABC_KEY>
~~~

The gateway returns **401**. The development team suspects the key is broken and wants to issue an all-access key.

### Systematic analysis

1. **Hostname/path:** did the request reach the right APIM gateway with the right API URL suffix and operation?
2. **Subscription state:** is the key's subscription `Active` rather than `Pending`/`Suspended`?
3. **Subscription scope:** does `Partner Commerce` actually contain the Orders API, or only Catalog?
4. **Key rotation:** is the client using the new primary/secondary key or a regenerated old one?
5. **API subscription settings:** if the API requires a key, is the header name exact and not stripped by a proxy?
6. **JWT policy:** does Orders API have a **`validate-jwt`** policy requiring a Bearer token in addition to the subscription key?
7. **Backend response:** did the backend return 401 rather than APIM subscription validation?

### Remediation

- Safely inspect gateway errors/correlation without asking the partner to email raw keys.
- Verify product/API membership and subscription status.
- If a JWT is required, provide token flow/audience/scope guidance.
- Verify with a properly scoped test client rather than masking the issue with an all-access key.
- Once resolved, update portal docs, add negative tests, and complete an RCA.

**Never issue an all-APIs key as a fix for 401.** Doing so can grant the partner access to other APIs outside their contract.

## 29. Real-world scenario B: developer portal does not show product

**Context:** The team created the `Internal Operations` product and added the Inventory API, but a test developer cannot find the product in the portal.

Possible causes:

- The product is still **Not published**.
- The product is not linked to the group the developer belongs to.
- The user signed in with a different identity than the APIM user assigned to the group.
- Portal content/configuration has not been published/updated under the model in use.
- The product contains no APIs or is filtered by permissions/state.
- The portal points to a different APIM instance/environment.

### Troubleshooting checklist

1. Verify product state, name/ID, and API associations.
2. Verify group associations and user membership.
3. Sign back in using a non-admin test developer account in the group.
4. Confirm the portal points to the right APIM service, domain, and published content.
5. Verify the subscription workflow and approval settings.
6. Do not switch an internal product to public/open just to make it appear.

Once the product appears, **still test gateway entitlements** to prove the user can access only the intended APIs.

## 30. Real-world scenario C: API throttled by rate limits

**Context:** The `Developer Sandbox` product limits callers to **60 calls/minute/subscription**. A client sends 300 requests/minute and 429 responses spike.

### Analysis

- Is the rate limit placed at the right policy scope?
- Does the counter key genuinely partition by **subscription ID** or verified client identity?
- If keyless, is anonymous traffic lumped together?
- Can an API shared across multiple products/key scopes traverse different effective policies?
- Does running across multiple gateway units/regions affect counter accuracy?
- Is the client tight-retrying and multiplying traffic?

### Resolution steps

1. Inspect RPS/429 charts and separate traffic by subscription.
2. Verify the limit using a sandbox client.
3. Guide the client on retry/backoff, caching, pagination, or batching.
4. Raise quotas only after evaluating backend capacity and contracts.
5. If abuse/credential leak is detected, suspend/rotate keys and audit.

**Never disable production APIM rate limiting globally** just to drop the 429 chart to zero; the purpose is protecting backends and ensuring fair usage.

## 31. Hands-on lab: publishing Catalog API for partners

### Requirements

This lab has two modes:

- **Design/read-only:** no Azure resource creation needed, suitable if budget/permissions are unavailable.
- **Sandbox with APIM:** create/edit a product on an authorized lab APIM instance without touching production.

Assume a Catalog API with **`GET /catalog/products`** and **`GET /catalog/products/{id}`**. Objectives:

1. Product **Partner Catalog**, Published.
2. Subscription required and requires approval.
3. Only the `Partners` group can register.
4. Rate limit of 60 requests/minute/subscription.
5. Partner tests the API using the key after approval.
6. Sensitive APIs still enforce JWT/claims authorization if private data is involved.
7. Never expose keys in docs/logs.

### Part A: object design

| Object | Lab configuration | Evidence to verify |
|---|---|---|
| API | Catalog, suffix `catalog`, test backend | Operations/paths match |
| Product | Partner Catalog | Published, `subscriptionRequired` |
| Group | Partners | Test developer belongs to group |
| Approval | Required | Request enters pending state and gets approved |
| Subscription | `partner-client-test` | Active, scope = product |
| Key | Primary/secondary | Stored only in secret store, omitted from report |
| Rate-limit | 60/60s | Returns 429 when exceeded in lab |
| Portal | API docs, ToS, Try it | Test user sees content and executes calls |
| JWT policy | On protected APIs | Invalid tokens rejected |
| Monitoring | Request status and latency | Distinguishes key, JWT, and backend errors |

### Part B: Portal/APIM sandbox setup

1. Confirm the lab APIM service, right subscription, and tier.
2. Import/create Catalog API with a **test** backend, using no production data.
3. Create product `Partner Catalog` with Published, subscription required, and requires approval.
4. Attach Catalog API and the `Partners` group.
5. Add an appropriate rate limit after reviewing existing global/API policies.
6. Create two test developers: **`partner-user`** and **`outsider-user`**.
7. Verify the outsider cannot self-subscribe to the restricted product.
8. Partner requests subscription; admin approves per workflow.
9. Retrieve the key via an authorized UI/secret channel; never screenshot or paste into reports.
10. Call the API through the gateway and verify responses plus 401 when the key is omitted.

### Part C: lab request verification

Success test sample:

~~~bash
GATEWAY="<LAB_APIM_GATEWAY_HOST>"
KEY="<KEY_FROM_SECURE_SOURCE>"

curl -i \
  -H "Ocp-Apim-Subscription-Key: $KEY" \
  "https://$GATEWAY/catalog/products"
~~~

Missing-key test sample:

~~~bash
curl -i "https://$GATEWAY/catalog/products"
~~~

Wrong-scope test sample: use a **different test key** assigned only to a product without Catalog, or try the Partner Catalog key on an internal API outside its entitlement. Never run tests against live production data.

### Part D: Try it verification

1. Open the developer portal as the `Partners` user.
2. Navigate to `Partner Catalog` → `Catalog API` → `GET /products`.
3. Select the valid subscription and complete OAuth sign-in/token acquisition if required by the API.
4. Use **Try it** to send a request to the sandbox gateway.
5. If errors occur, use Browser DevTools to distinguish CORS, 401/403, and network issues.
6. Confirm no raw subscription keys or JWTs appear in documentation or shareable URLs.

### Part E: recording results

| Report field | Value recorded by learner |
|---|---|
| APIM service + environment | Lab environment name |
| API + operations | Catalog name/paths |
| Product state | Published / Not published |
| Group visibility | Who can view/subscribe |
| Subscription scope | Product/API/service |
| Approval result | Pending → Active, timestamp |
| HTTP test | Status + latency + correlation |
| Security negative test | Missing key / wrong key / wrong scope / invalid JWT |
| Rate limit | Test request count, 429, and retry behavior |
| Portal | Docs/Try it/CORS verified |
| Secret safety | Record only where keys are managed, **never the keys themselves** |
| Cost/cleanup | Resources used and accountable owner |

If you only have read permissions, document the architecture, planned Bicep/product configuration, policies, and test matrix without creating a new APIM service.

### Safe cleanup

- Delete only products/subscriptions/users **created by the lab**, after confirming no other clients depend on them.
- Never regenerate production keys to practice rotation.
- Never delete shared APIM services or resource groups.
- Purge test secrets from local shells/CI artifacts per procedure.
- Record before/after state and confirm test subscriptions are revoked if no longer needed.

## 32. Security and costs in API distribution

### Costs to account for

| Component | Cost category |
|---|---|
| **APIM service tier/units** | Capacity or billing units per current SKU/plan |
| **Gateway requests** | Call volume/throughput per tier and pricing model |
| **Networking** | Private endpoints, VNet, NAT, egress, custom domains/certificates |
| **Azure Monitor/Application Insights** | Log/metric ingestion, retention, and alerts |
| **Developer portal customization** | Hosting/maintenance if self-hosted, content upkeep |
| **Backend service** | App Service, AKS, Functions, databases, compute/requests |
| **Identity/Key Vault** | Authentication integration, secret operations, logging |
| **CI/CD** | Build runners, IaC drift checks, release testing |

Never quote a fixed price without factoring in **region, tier, capacity, gateway topology, requests, and dependent services**. Use the **Azure Pricing Calculator** and **Cost Management**. **APIM products do not automatically invoice customers**, and **budget alerts do not automatically halt all spending**.

### 10 security principles to remember

1. Subscription keys are **secrets**; never put them in source code or public frontends.
2. Product approval does not replace user/tenant authorization.
3. Gateway subscription checks do not replace backend security.
4. JWTs must be validated for signature/issuer/audience/expiry and appropriate scopes/roles.
5. Product membership is only an entitlement/portal experience layer.
6. Critical security policies must account for API-scoped and all-APIs subscriptions.
7. Backends must not leave APIM bypass paths open if gateway mediation is required.
8. Logs/traces must never store raw keys, tokens, or unnecessary personal data.
9. Key rotation and suspension require runbooks, auditing, and partner communication.
10. The developer portal/Try it must use HTTPS, strict CORS, secure identity, and docs free of real credentials.

## 33. Pre-production API publishing checklist

- [ ] API backend, URL suffix, operations, schemas, and version/revision confirmed.
- [ ] Product purpose, published state, groups, and subscription/approval rules clearly defined.
- [ ] Product ↔ API and Product ↔ Group associations verified.
- [ ] Developer onboarding workflow, ToS, support, deprecation, and ownership established.
- [ ] Scopes of product/API/all-APIs subscriptions audited; overly broad access removed.
- [ ] No global/admin subscription keys shared with external clients.
- [ ] Primary/secondary keys stored in a secret manager with a rotation plan.
- [ ] JWT/OAuth/mTLS/managed identity enforced where required rather than relying on keys alone.
- [ ] Backend enforces tenant/object-level authorization and is protected against bypass.
- [ ] Rate-limit/quota uses a valid identity-based counter key sized to backend capacity.
- [ ] Effective policies across global/product/API/operation scopes reviewed.
- [ ] Developer portal published and tested with a non-admin user.
- [ ] Try it uses the right gateway, CORS, OAuth audience, and subscription key.
- [ ] Negative tests executed: missing/wrong/suspended key, wrong scope, invalid JWT, outsider user.
- [ ] Logging/auditing/alerting enabled properly without capturing raw credentials/PII.
- [ ] IaC/pipelines manage OpenAPI, products, groups, policies, and configurations.
- [ ] Rollback procedures avoid accidentally deleting active partner subscriptions.
- [ ] Runbook exists for 401/403/429/502 errors and emergency key revocation.
- [ ] APIM tier/units, log ingestion, and backend costs reviewed.

## 34. Self-check questions

1. How does an APIM subscription differ from an Azure subscription used to manage cloud resources?
2. How do APIs, operations, products, and subscriptions relate to one another?
3. Can an API belong to multiple products? How does that impact policies?
4. Does a Published product mean the API becomes anonymously public?
5. How does `Subscription required` differ from `Requires approval`?
6. How does a product-scoped subscription key differ from single-API and all-APIs scopes?
7. Why should you not issue an all-APIs key to a partner who only needs Catalog API?
8. Do primary and secondary keys have different permissions? How do you rotate them to minimize downtime?
9. Why is a subscription key insufficient to identify a user/tenant and authorize viewing an order?
10. Are signing in to the developer portal and obtaining an OAuth token to call an API the same process?
11. Does the `Partners` group in APIM replace backend authorization?
12. Why is product visibility not a standalone security boundary?
13. When requests arrive with product-scoped keys vs. API-scoped keys, which policies must be checked?
14. How do rate limits and quotas differ? Why might anonymous traffic share a single counter?
15. What is dangerous about using an unverified `x-user-id` header as a rate-limit counter key?
16. Does CORS stop a server-side client from making unauthorized API calls?
17. If Try it throws a CORS error while `curl` succeeds, what are the first checks to perform?
18. Why can a public backend nullify gateway controls?
19. Where can a 401 come from—a subscription check or a JWT policy?
20. When rotating keys, why shouldn't you regenerate both keys at once?
21. Do API products automatically bill and invoice callers based on request counts?
22. Which artifacts should be placed under version control/IaC when releasing a new API?
23. When rolling back policies, why must existing subscription states and API associations be preserved?
24. If the portal does not show a product, which state, groups, and user settings should you check?
25. After publishing an API, which metrics/logs prove the client experience is healthy?

## 35. References

- [Azure API Management overview](https://learn.microsoft.com/azure/api-management/api-management-key-concepts) — API, product, policy, gateway, and developer portal concepts.
- [Create and publish an API product](https://learn.microsoft.com/azure/api-management/api-management-howto-add-products) — products, APIs, and groups.
- [Subscriptions in Azure API Management](https://learn.microsoft.com/azure/api-management/api-management-subscriptions) — scopes, states, and key management.
- [Subscriptions for access to APIs](https://learn.microsoft.com/azure/api-management/api-management-howto-create-subscriptions) — registering and operating subscriptions.
- [Developer portal overview](https://learn.microsoft.com/azure/api-management/api-management-howto-developer-portal) — managed portal, content, and developer experience.
- [Developer portal administration](https://learn.microsoft.com/azure/api-management/api-management-howto-developer-portal-customize) — customizing and publishing the portal.
- [Azure API Management policies](https://learn.microsoft.com/azure/api-management/api-management-howto-policies) — inbound/backend/outbound/on-error and scopes.
- [API Management policy reference](https://learn.microsoft.com/azure/api-management/api-management-policies) — policy catalog.
- [Rate limit by key policy](https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy) — throttling by counter-key.
- [Quota by key policy](https://learn.microsoft.com/azure/api-management/quota-by-key-policy) — periodic quotas.
- [Validate JWT policy](https://learn.microsoft.com/azure/api-management/validate-jwt-policy) — token verification.
- [CORS policy](https://learn.microsoft.com/azure/api-management/cors-policy) — permitting browser origins.
- [Authentication with managed identity policy](https://learn.microsoft.com/azure/api-management/authentication-managed-identity-policy) — APIM calling Entra ID-protected backends.
- [Azure API Management monitoring](https://learn.microsoft.com/azure/api-management/api-management-howto-use-azure-monitor) — gateway monitoring.
- [Azure API Management infrastructure as code](https://learn.microsoft.com/azure/azure-resource-manager/bicep/overview) — managing Azure resources with Bicep.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating APIM and dependent service costs.

**Conclusion:** In Azure API Management, **APIs** define functionality, **products** package consumption entitlements, **subscriptions** establish access credentials, and the **developer portal** supports discovery, onboarding, and testing. Publishing an API securely requires more than creating a product and handing out keys: you must verify subscription scopes and lifecycles, user groups, JWT/authorization, policies, CORS, networking/backends, logging, and rollback-capable release workflows. When these layers are governed consistently, development teams can open APIs conveniently to partners while preserving security, operational reliability, and cost control.
