# JWT Validation Policies and Backend API Protection

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data services. The goal is not only deploying applications to Azure, but also knowing how to **monitor, secure, and control costs** for a real-world architecture. In the **API and Workflow Integration** chapter, this lesson focuses on using **Azure API Management (APIM)** to validate JSON Web Tokens (JWTs), apply access control policies, and protect **backend APIs**, combining application authentication/authorization with network security layers.

Suppose an ordering system has a **Java REST API** running on Azure App Service or Azure Kubernetes Service. A web app calls `GET /orders` to read orders and `POST /orders` to create orders. An internal worker calls `POST /orders/reconcile` for reconciliation. These three callers have different permissions, yet all pass through API Management. If the gateway only checks that a token has a valid signature **without checking audience, issuer, permissions, and caller source**, the API can be invoked with a token meant for a different service. And if the backend is exposed directly to the Internet without authentication, an attacker can bypass all gateway policies entirely.

After this lesson, you will be able to:

- Distinguish **JWT**, **OAuth 2.0 access token**, **OpenID Connect ID token**, authentication, and authorization.
- Explain why you must verify **signature, issuer, audience, expiration, and not-before** alongside **scopes/roles**.
- Configure APIM's **`validate-jwt`** policy using OpenID Connect discovery/JWKS with Microsoft Entra ID.
- Design policies per **API/operation**, **delegated scopes (`scp`)**, and **application roles (`roles`)** without over-granting permissions.
- Understand policy inheritance across **global, product, API, and operation scopes**, avoiding accidentally letting an operation skip validation.
- Combine the gateway with **backend authentication**, managed identity/mTLS, and network isolation.
- Apply rate limiting, request validation, strict CORS, secrets management, TLS, and diagnostic logging.
- Test invalid/expired/under-privileged token scenarios, backend bypass, and design a production runbook.

## 1. The big picture: where does API Management sit?

**Azure API Management** provides a gateway, API management plane, and developer-facing experience depending on tier/configuration. Here, the gateway receives client requests and applies **policies** before forwarding to the configured backend.

```text
Browser / mobile app                Background job
      |                                   |
      | OAuth2 Authorization Code + PKCE  | Client Credentials
      v                                   v
  Microsoft Entra ID                 Microsoft Entra ID
      |                                   |
      +----------- JWT access token ------+
                       |
                       | Authorization: Bearer <access-token>
                       v
                Azure API Management
                +----------------------+
                | validate-jwt         |
                | validate claims      |
                | rate limit / quota   |
                | request validation   |
                | route to backend     |
                +----------------------+
                       |
                       | Backend authentication + private networking
                       v
              Orders Java API / backend
                       |
                 Azure SQL / Storage
```

This flow has **at least three security boundaries**:

1. **Client → Identity Provider:** users or applications authenticate with Microsoft Entra ID and receive an access token with the right permissions.
2. **Client → APIM:** the gateway validates the token and API/operation policies, rejecting invalid requests before they reach the backend.
3. **APIM → backend:** the backend accepts only authorized traffic, verifying caller identity/authorization by design without blindly trusting that clients always pass through APIM.

**APIM does not automatically make a backend private or secure.** Gateway policies do not protect requests sent directly to the backend URL if the backend has an unrestricted public path.

### 1.1. API Management is a gateway, not an Identity Provider

APIM **does not** replace Microsoft Entra ID or a token-issuing system. In a typical architecture, Entra ID is the JWT **issuer**; APIM is a **verifier** and policy enforcer; and the Java API is the **resource server** executing business logic. The API can continue validating tokens and enforcing business authorization at the application layer.

### 1.2. When is this model needed?

| Scenario | Value of APIM | Additional layers to watch |
|---|---|---|
| Multiple apps sharing one backend API | Consistent policies, routing, versioning, quotas, and diagnostics | Backend RBAC and object-level authorization |
| Mobile/web app calling APIs | Bearer access token checks, per-operation scopes | OAuth2 code + PKCE, strict origin CORS |
| Daemon calling APIs | App roles and caller app identity checks | Client credentials, credential/federation, and least privilege |
| Public API needing abuse mitigation | Rate limiting, request validation, edge WAF where appropriate | DDoS/edge protection, bot defense, security monitoring |
| Backend should accept traffic only from gateway | Network controls and service-to-service identity | Private endpoints, VNet routing, mTLS/managed identity |

Not every system needs APIM: a small internal API may be sufficient with application-level auth and direct networking. As the number of APIs, callers, and policies grows, a gateway centralizes governance—at the cost of **additional expense, latency, infrastructure dependency, and shared-configuration risk**.

## 2. What is a JWT and what is inside it?

A **JSON Web Token (JWT)** in compact serialization consists of three Base64URL-encoded segments separated by dots:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Example **simulated** payload of an access token:

```json
{
  "iss": "https://login.microsoftonline.com/<tenant-id>/v2.0",
  "aud": "api://<orders-api-app-id>",
  "sub": "<subject>",
  "tid": "<tenant-id>",
  "scp": "orders.read orders.write",
  "iat": 1795150000,
  "nbf": 1795150000,
  "exp": 1795153600
}
```

**This is not a real JWT**: the payload above has no signature. Do not copy it into tests expecting APIM to accept it. In real tokens, claims vary by token version, tenant, grant type, and API configuration; both `scp` and `roles` are not always present together.

### 2.1. Header, payload, signature

| Component | Example | Meaning |
|---|---|---|
| JWT header | `alg`, `kid`, `typ` | Signing algorithm, signing key ID, token type metadata |
| JWT payload | `iss`, `aud`, `exp`, `nbf`, `scp`, `roles` | Claims asserted by the issuer about the token/caller |
| JWT signature | Digital signature value | Verifier proves the token was not tampered with and was signed by a trusted key |

**Base64URL is not encryption.** Anyone holding a standard signed JWT can decode the payload; never put passwords, keys, or confidential data in custom claims just because the token is signed.

### 2.2. Core claims that must be inspected

| Claim | Meaning | Required check |
|---|---|---|
| `iss` | Token issuer | Matches a trusted issuer, including the expected tenant/token version |
| `aud` | Audience – intended recipient resource | Matches the **exact backend API**, not an SPA or another API |
| `exp` | Expiration | Reject expired tokens, allowing only intentional small clock skew |
| `nbf` | Not before | Reject tokens prior to their validity start time |
| `iat` | Issued at | Useful for auditing/time checks; does not replace `exp` |
| `tid` | Tenant identifier in Microsoft Entra tokens | Can be used to pin allowed tenants where appropriate |
| `sub` | Subject | An identifier within the token context; not necessarily a global user key |
| `oid` | Principal Object ID in Entra depending on token type | Used with tenant to identify a principal; does not replace authorization |
| `azp` or `appid` | Client application ID depending on token version | Used to allowlist approved callers when required by threat model |
| `scp` | Delegated scopes | Check user-delegated permissions for specific operations |
| `roles` | App roles | Check application permissions or declared roles |

**Do not rely solely on `sub`, `oid`, `email`, or `preferred_username` to grant access to every API.** A valid signature only proves the issuer signed those claims; authorization must still verify **permissions and business scope**.

### 2.3. A valid JWT signature is not enough

A JWT signed by Microsoft Entra ID might still:

- Be intended for **Microsoft Graph** instead of Orders API (wrong `aud`).
- Come from a **different tenant** that Orders API does not trust (wrong `iss`/tenant).
- Be expired or not yet valid.
- Lack `orders.write` while the caller attempts `POST /orders`.
- Carry a role meant only for another backend or an unapproved app.

Therefore, **token validation** and **permission checks** are two distinct layers, even when configured inside the same `validate-jwt` policy.

## 3. How does an OAuth 2.0 access token differ from an OIDC ID token?

Clients can receive several token types, but **backend APIs must validate an access token issued specifically for that API**.

| Type | Primary audience | Usage |
|---|---|---|
| **ID token** | Client application handling sign-in, e.g., an SPA | Proves user authentication to the client; not proof of authorization to call Orders API |
| **Access token** | Resource/API the client is permitted to call | Sent in `Authorization: Bearer`; API verifies signature, claims, and permissions |
| **Refresh token** | Used in OAuth token lifecycle by authorized clients | Never sent to Orders API to access resources |

For web/mobile public clients, the standard approach is **OAuth 2.0 Authorization Code + PKCE** with an appropriate identity library. Resource Owner Password Credentials and embedding client secrets in browser JavaScript are **discouraged**.

For non-interactive jobs/daemons, **Client Credentials** uses an application identity and appropriate application permissions/app roles. Do not fake a user-delegated `scp` onto an app-only token.

### 3.1. Delegated scopes and application roles

Suppose Orders API exposes:

- Delegated scopes: `orders.read`, `orders.write`.
- Application role: `Orders.Reconcile` for the reconciliation daemon.

Business rules:

| Operation | Caller | Claim to verify |
|---|---|---|
| `GET /orders` | User via web/mobile | `scp` contains `orders.read` or another policy-approved permission |
| `POST /orders` | User via web/mobile | `scp` contains `orders.write` |
| `POST /orders/reconcile` | Internal daemon | `roles` contains `Orders.Reconcile`, plus consider allowlisting the caller app |

This is **one specific design pattern**; other systems might assign app roles to users or combine mechanisms, but how user-delegated vs. app-only callers are distinguished must be documented. Never use a vague condition like “has any `scp` **or** any `roles`” across all operations.

### 3.2. Audience must come from real tokens and App Registration settings

When registering an API in Entra ID, the app gets an **Application (client) ID** and optionally an **Application ID URI** such as `api://<orders-api-app-id>`. The actual `aud` claim in an access token may be the **GUID client ID** or the **URI**, depending on token/API configuration.

Always compare a real access token issued **specifically for the API** against the App Registration and APIM policy; never guess that every valid token uses `aud = api://...`.

### 3.3. Tenants and token versions

Microsoft Entra ID can issue access tokens with different issuers between **v1 and v2**, depending on the resource's token version configuration. For example, issuers can look like:

```text
https://login.microsoftonline.com/<tenant-id>/v2.0
https://sts.windows.net/<tenant-id>/
```

Do not use the `/common` endpoint as a vague trust boundary for a **single-tenant** API without justification. For **multi-tenant** APIs, validate issuer/tenant per onboarded organization, enforce a tenant allowlist, and isolate data by tenant. Accepting tokens from any tenant simply because Microsoft signed them can cause cross-tenant access vulnerabilities.

## 4. Request processing chain through Azure API Management

APIM policies are organized into **inbound, backend, outbound, and on-error** sections:

```text
Client request
     |
     v
Inbound policies
  - validate JWT
  - check scopes/roles
  - rate limit and validate request
  - rewrite/set headers
     |
     v
Backend policies
  - forward request
  - route/backend authentication
     |
     v
Backend response
     |
     v
Outbound policies
  - response shaping / safe headers per design
     |
     v
Client response

If policy/transport error: on-error handles per configuration.
```

### 4.1. Why does authentication live in inbound?

JWT validation and permission checks should run **before `forward-request`**, preventing invalid requests from consuming backend compute/database resources. After validating the token, continue controlling request content/size, quotas, routing, and backend identity.

### 4.2. Distinguishing policy scopes

Common scopes:

- **Global:** gateway-wide policies (where supported).
- **Product:** behavior for APIs published within that product.
- **API:** rules applied to an entire API.
- **Operation:** authorization/validation tailored to a single path/method.

Support and effective evaluation rules can vary by tier/gateway/workspace/feature. The **`<base />`** element controls where policies from parent scopes are inherited. Deleting `<base />` or misplacing it can cause an operation to **stop inheriting** API/global validation as operators expect.

**Rule:** after every change, inspect the **effective policy** on the published operation itself—never open only the top-level API policy and assume every request is protected.

### 4.3. Subscription keys do not replace access tokens

APIM may require a **subscription key** for developer/product management, quotas, and tracing. This is not inherently a user authentication mechanism or business data authorization check. Never use “has `Ocp-Apim-Subscription-Key`” in place of JWT validation, scopes/roles, and object-level permissions.

In multi-tenant public APIs, a shared or leaked subscription key could be reused by another client; document its security role separately and keep its trust minimal.

## 5. Preparing Microsoft Entra ID for Orders API

The hands-on example uses an Entra ID tenant controlled by the engineering team. `<tenant-id>` and `<orders-api-app-id>` are **placeholders**; replace them with real protected values in your lab environment.

### 5.1. Registering the API resource

In the Microsoft Entra admin center:

1. Create or select an **App Registration** representing **Orders API**.
2. Record the **Application (client) ID**, **Directory (tenant) ID**, and App ID URI if configured.
3. Under **Expose an API**, publish delegated scopes such as `orders.read` and `orders.write` per design.
4. Create the **`Orders.Reconcile` app role** for workload automation with the appropriate permitted member types.
5. Grant/consent scopes or application roles only to the right client applications.
6. Inspect a real access token to confirm `iss`, `aud`, `scp`, `roles`, and token version.

### 5.2. Registering clients

- Web/mobile public clients must use an appropriate OAuth flow, controlled redirect URIs, **PKCE**, and no embedded client secrets.
- Backend daemons can use a service principal/managed identity or workload federation with consented app roles.
- Do not grant `orders.write` to every app that only reads orders, and never grant `Orders.Reconcile` to a browser SPA.

### 5.3. Three identifiers that are easily confused

| Value | Example | Purpose |
|---|---|---|
| Tenant ID | `<tenant-id>` | Pins the trusted issuer/tenant |
| API Application ID / App ID URI | `<orders-api-app-id>` or `api://...` | Audience of the access token accepted by the API |
| Client application ID | `<web-client-id>` or `<daemon-client-id>` | Identifies the calling app requesting the token; can be allowlisted |

**Never use the SPA's `client_id` as the `aud` for Orders API.** That could cause the gateway to accept client ID tokens instead of API-scoped access tokens.

## 6. APIM `validate-jwt` policy: verifying access tokens

**`validate-jwt`** is the policy used to validate a JWT from a request or configured token source. For standard OAuth 2.0 APIs, the JWT arrives in:

```http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
```

The policy should verify **signature, issuer, audience, lifetime**, and claims aligned with the threat model. With Microsoft Entra ID, APIM can fetch public keys via **OpenID Connect configuration/JWKS** rather than hardcoding a single signing key in the policy.

### 6.1. Example API-level token validation policy

The XML below illustrates a policy for an API accepting **single-tenant v2 access tokens** issued for Orders API. Replace all `TENANT_ID` and `ORDERS_API_AUDIENCE` strings with verified real values:

```xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        require-scheme="Bearer"
        require-signed-tokens="true"
        require-expiration-time="true"
        clock-skew="60"
        failed-validation-httpcode="401"
        failed-validation-error-message="Unauthorized"
        output-token-variable-name="validatedJwt">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>ORDERS_API_AUDIENCE</audience>
      </audiences>
      <issuers>
        <issuer>https://login.microsoftonline.com/TENANT_ID/v2.0</issuer>
      </issuers>
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
```

For example, if the real API App ID URI is `api://11111111-2222-3333-4444-555555555555`, replace `ORDERS_API_AUDIENCE` with that string **if real access tokens use that value in `aud`**. If `aud` is the GUID, configure the GUID as the audience. Never accept an arbitrary list of audiences just “to make it work.”

### 6.2. Meaning of key attributes

| Attribute / element | Meaning |
|---|---|
| `header-name="Authorization"` | Reads the JWT from the HTTP header |
| `require-scheme="Bearer"` | Enforces the proper authorization scheme |
| `require-signed-tokens="true"` | Rejects unsigned tokens per policy configuration |
| `require-expiration-time="true"` | Requires a valid expiration claim |
| `clock-skew="60"` | Allows minor clock drift in seconds per policy |
| `failed-validation-httpcode="401"` | Rejects the request when the token is invalid |
| `failed-validation-error-message` | Generic message without leaking internal reasons/keys |
| `openid-config` | OpenID discovery endpoint for verifying issuer/signing keys |
| `audiences` | Token must target the protected API |
| `issuers` | Trust only configured issuers |
| `output-token-variable-name` | Stores the validated JWT object for downstream policies if needed |

**Never disable signature or lifetime checks to work around clock, issuer, or JWKS errors.** Find the mismatch root cause and fix the configuration or clock synchronization properly.

### 6.3. OpenID Connect discovery and key rotation

The issuer's OpenID Connect metadata tells verifiers where to retrieve **public signing keys**. When Entra ID rotates signing keys, APIM must fetch updated metadata/keys via the platform's caching/refresh mechanism.

Points to note:

1. `kid` in the JWT header locates the matching signing key in JWKS, but **does not prove the key is trustworthy** if JWKS comes from an untrusted URL.
2. The `openid-config` URL must belong to an approved issuer/tenant; **never** construct that URL from client-supplied claims/tokens.
3. Accepted signing algorithms must follow issuer and validator policy; never allow `alg=none` or symmetric/asymmetric key confusion.
4. When the issuer rotates keys, new tokens may carry a new `kid`. Processes should support metadata refresh, monitor errors, and avoid unnecessary manual public-key pinning.
5. Token validation must enforce `exp` and `nbf` against the gateway clock plus small allowed skew—never accept long-expired tokens “so clients don't get errors.”

**Never fetch signing keys from a URL embedded inside the JWT itself** unless the system verifies that URL is a trusted source. Issuer policies must be fixed or chosen from a vetted list of onboarded tenants.

### 6.4. When APIM receives both v1 and v2 tokens

If real access tokens are **v1** with corresponding issuer and claims, the v2-only policy above will reject them even when the client signed in to Entra ID validly. That is right if the API intentionally supports only v2. If both must be supported:

- Document the compatibility rationale clearly.
- Validate **each** issuer, audience, claim shape, and metadata source explicitly.
- Configure the policy with deliberate trust conditions.
- Write tests for tokens from unpermitted versions.

Never simply drop `issuers` or `audiences` to “accept every token.”

## 7. Enforcing delegated scopes per operation

After verifying the token's issuer and audience, check whether the client is permitted to invoke the **specific operation**. For instance, `GET /orders` requires delegated scope `orders.read`.

### 7.1. Policy for GET /orders

Example using `validate-jwt` with `required-claims`, placed on the **`GET /orders` operation** or at the effective scope matching your API structure:

```xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        require-scheme="Bearer"
        require-signed-tokens="true"
        require-expiration-time="true"
        failed-validation-httpcode="403"
        failed-validation-error-message="Forbidden">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>ORDERS_API_AUDIENCE</audience>
      </audiences>
      <issuers>
        <issuer>https://login.microsoftonline.com/TENANT_ID/v2.0</issuer>
      </issuers>
      <required-claims>
        <claim name="scp" match="any" separator=" ">
          <value>orders.read</value>
        </claim>
      </required-claims>
    </validate-jwt>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
```

This example **intentionally re-validates the JWT at the operation level** so `scp` checking does not rely on a custom-written parser expression. If `validate-jwt` is already at API scope and `<base />` is inherited, this may **re-verify the token** on the same request; in production, consider policy fragments or authorization expressions reading the **already-validated JWT** with thorough tests to avoid duplication. Regardless of optimization, **never skip signature/issuer/audience validation before trusting claims**.

Note on response codes: this policy is set to return **403** if any validation step at this scope fails, including an invalid token if not already rejected earlier. Under standard HTTP semantics, missing/invalid tokens return **401**, while authenticated-but-unauthorized callers receive **403**. Separate policies can be configured to distinguish them cleanly, provided effective policies are tested and error messages remain safe.

### 7.2. Multi-value scopes and spaces

Microsoft Entra delegated tokens typically represent `scp` as a **space-delimited** string of scopes:

```text
"scp": "orders.read orders.write"
```

In `required-claims`, `separator=" "` matches discrete values per policy rules. Never use naive substring matching such as:

```text
If scp contains the substring "orders.read", allow it.
```

Substring matching could mistakenly accept similar scopes such as `orders.read.all` or another party's permission name. Authorization must check **exact full scope names**.

### 7.3. POST /orders requires a different permission

For `POST /orders`, replace `orders.read` with:

```xml
<required-claims>
  <claim name="scp" match="any" separator=" ">
    <value>orders.write</value>
  </claim>
</required-claims>
```

This is a fragment used **inside** a `validate-jwt` block that fully validates signature, issuer, audience, and lifetime—**not a standalone complete policy**. If the API exposes `DELETE /orders/{id}`, do not allow it automatically just because a caller holds `orders.write`; define an explicit delete permission and enforce business authorization in the backend.

## 8. Enforcing application roles for daemons

Automation/daemon apps typically acquire access tokens via **client credentials**, without a signed-in user. In typical app-only flows, tokens carry **`roles`** rather than delegated `scp`.

For example, `POST /orders/reconcile` requires `Orders.Reconcile` and should only be callable by an approved daemon.

### 8.1. Role-checking policy

```xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        require-scheme="Bearer"
        require-signed-tokens="true"
        require-expiration-time="true"
        failed-validation-httpcode="403"
        failed-validation-error-message="Forbidden">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>ORDERS_API_AUDIENCE</audience>
      </audiences>
      <issuers>
        <issuer>https://login.microsoftonline.com/TENANT_ID/v2.0</issuer>
      </issuers>
      <required-claims>
        <claim name="roles" match="any">
          <value>Orders.Reconcile</value>
        </claim>
      </required-claims>
    </validate-jwt>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
```

As with the `scp` example, this may re-validate the token if `<base />` already inherits baseline validation. In production you can optimize it, **provided full authorization enforcement is preserved**.

### 8.2. Adding an application allowlist when needed

A role states the client was granted an application permission. For highly sensitive operations, security teams may also restrict the **calling application** via `azp` (v2 tokens) or `appid` (v1 tokens), alongside tenant and other conditions. Example policy fragment:

```xml
<required-claims>
  <claim name="roles" match="any">
    <value>Orders.Reconcile</value>
  </claim>
  <claim name="azp" match="any">
    <value>APPROVED_DAEMON_CLIENT_ID</value>
  </claim>
</required-claims>
```

This fragment **applies only to token shapes carrying `azp`**, not blindly across all v1/v2 tokens. Inspect real tokens, protected operations, and managed identity/service principal claims before deploying. Never use a client-supplied header value instead of signature-verified `azp`.

### 8.3. Why not share an unconditional `scp` and `roles` policy?

If `POST /orders/reconcile` accepts any token with `orders.write` **or** `Orders.Reconcile`, a web user holding write scope could trigger reconciliation even though business rules restrict it to the daemon. Separating **user-delegated** and **app-only** authorization per operation prevents unintended privilege escalation.

In multi-tenant systems or complex impersonation/delegation flows, also distinguish principal types, allowed clients, tenant boundaries, and data ownership; never treat a single claim as sufficient proof for every security requirement.

## 9. Policy inheritance and evaluation order

A dangerous operational mistake is **assuming APIM validates JWTs at the API level**, while an operation override accidentally drops inheritance of that policy.

### 9.1. `<base />` is not just XML decoration

Example API-level inbound:

```xml
<inbound>
  <base />
  <validate-jwt ...>
    <!-- Validates issuer, audience, signature, lifetime -->
  </validate-jwt>
</inbound>
```

At the operation level, if you write:

```xml
<inbound>
  <base />
  <!-- Operation-specific authorization policy -->
</inbound>
```

inherited policies are inserted at `<base />` per APIM's model. If an operation **omits** `<base />`, or another scope overrides policies unexpectedly, parent validation may no longer execute as operators believe.

### 9.2. Safe policy organization rules

1. Establish **one clearly owned place** for baseline API token validation.
2. Perform **operation-level permission checks** after the token is validated.
3. Never leave a sensitive operation unauthenticated by copying a public endpoint's policy.
4. Review **effective policies** across **global/product/API/operation** before and after deployment.
5. Use **policy fragments** or IaC when shared logic grows, versioning and reviewing them like code.
6. Test every critical operation with **missing/invalid/wrong-audience/insufficient-scope tokens**, not just an API root path.

### 9.3. What about public endpoint exceptions?

An API might expose `GET /health` or a public OpenAPI document. If JWT validation must be exempted, create a **dedicated operation**, review what data it exposes, and control the route carefully. Never configure an entire API to “skip JWT” just because of one public route.

Public health endpoints should return **minimal** status signals—never connection strings, sensitive backend hostnames, stack traces, or secret lists.

## 10. API authorization does not replace object-level authorization

A JWT with `orders.read` proves the caller is allowed to perform the **action type** of reading orders—not that they may read **every** order in the database.

Example:

```http
GET /orders/ORD-1042
Authorization: Bearer <valid-token-with-orders.read>
```

The backend must still verify the order's user/tenant:

```text
Valid token?
     |
     v
Has scope orders.read?
     |
     v
Does ORD-1042 belong to a tenant/user permitted for caller?
     |
     +-- Yes -> return authorized data
     |
     +-- No  -> 403 or 404 per anti-enumeration policy
```

**Broken Object Level Authorization (BOLA)** occurs if the backend trusts the `scp` claim alone without checking record `tenantId`/owner relationships. Gateways generally lack sufficient business data or transaction context to perform exact object ownership checks, so this responsibility belongs to the backend.

### 10.1. Never trust tenant IDs from arbitrary queries or headers

If a client sends `X-Tenant-Id: tenant-b` or `?tenantId=tenant-b`, the backend must never accept that as proof of access to `tenant-b`. Derive authorized tenants from the **verified identity** and authoritative authorization records in the system.

In multi-tenant SaaS apps, establish authorization tables, data isolation, tenant allowlists, and cross-tenant access policies independently of JWT signing.

### 10.2. Do not pack too much authorization state into JWTs

Tokens can remain valid for many minutes or hours per policy. If a user's permissions change while a token is still active, old claims may continue being accepted until expiration or revocation/enrichment kicks in.

For frequently changing sensitive permissions, the backend may need to **query current permissions in a database/authorization service**, use short-lived tokens, or apply appropriate session/revocation strategies. Do not expect portal permission changes to take instant effect on already-issued access tokens.

## 11. Preventing direct backend access that bypasses API Management

Suppose normal clients call:

```text
https://api.orders.example.com/orders
        |
        v
     Azure APIM
        |
        v
https://orders-api-prod.azurewebsites.net
```

If the backend has a public hostname and **enforces no authentication**, anyone who discovers the backend URL can call:

```text
https://orders-api-prod.azurewebsites.net/orders
```

instead of going through APIM. All `validate-jwt`, rate-limit, and request-validation gateway policies are **completely bypassed**. This is a severe design flaw even if APIM policies are flawless.

### 11.1. Three protection layers that should work together

| Layer | Goal | Examples |
|---|---|---|
| **Network** | Only approved sources can connect to the backend | Private endpoint, VNet topology, access restrictions, internal ingress, NSG/firewall |
| **Service-to-service identity** | Backend verifies the caller is an authorized component | APIM managed identity, Microsoft Entra token, mTLS where appropriate |
| **Application authorization** | Permit only operations and data owned by the caller | JWT validation, scopes/roles, tenant membership, object ownership |

No single layer should be used as an excuse to skip the other two. A private endpoint does not verify user scopes. A valid JWT does not restrict inbound network exposure. An mTLS certificate identifies a peer per trust store, not which orders a user may read.

### 11.2. Backend options on Azure

**Azure App Service:** consider **private endpoints** and disabling/restricting public network access per tier capabilities, or access restrictions scoped to controlled source addresses. **App Service Authentication/Authorization (Easy Auth)** can validate Entra tokens; verify audience and allowed client applications align with your architecture.

**AKS:** consider an internal ingress/load balancer or VNet-connected gateway, Kubernetes NetworkPolicy, and identity/authentication at ingress/API. Pods should never be exposed to the Internet inadvertently via a public `LoadBalancer` Service.

**Azure Container Apps:** configure internal/private ingress per environment, networking, authentication, and directional routing. Never assume an endpoint is private merely because the Container Apps environment is attached to a VNet.

APIM connectivity over VNet, private endpoints/private links, internal gateways, and APIM features depend on **tier, service generation, and region**. Before finalizing diagrams, verify supported features for your exact gateway; never copy networking configs blindly from a different APIM tier.

### 11.3. Is an IP allowlist enough?

Blocking all traffic except APIM's egress IP can help in some architectures, but:

- Egress IPs can depend on deployment mode, NAT, region, and configuration; use only when the source address is **static and verified**.
- IPs can be shared or change over infrastructure lifecycles.
- An IP does not prove the caller holds a valid token.
- If a backend has multiple ingress paths, an allowlist in one place will not block another path.

When strong isolation is required, combine **private networking + verified service-to-service identity + backend auth/authorization**.

## 12. Two authentication models between APIM and backend

There are **two** common models; choose intentionally rather than mixing them and accidentally losing user identity.

### 12.1. Model A: end-to-end user access token

```text
Client --(User JWT for Orders API)--> APIM
  APIM: validate JWT, tenant, scope, rate limit
                           |
                           v
Backend Java API: re-validate JWT,
  check scope/role + owner/tenant per order
                           |
                           v
Database
```

Pros: the backend sees the API-targeted user token and can enforce object-level authorization directly. It also resists bypass better if the backend URL leaks, since the backend rejects unauthenticated/unauthorized calls.

Network controls are still necessary because holding a valid token does not entitle a client to **bypass APIM quotas, logging, and gateway policies**. If the backend is public, a valid-but-malicious user could evade APIM rate limits by calling directly.

### 12.2. Model B: APIM uses managed identity to call the backend

APIM can use a **managed identity** to obtain an access token for a protected backend resource via the `authentication-managed-identity` policy when supported by tier/features.

```xml
<policies>
  <inbound>
    <base />
    <!-- Place after inbound JWT/scope checks. -->
    <authentication-managed-identity resource="api://BACKEND_APP_ID" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
```

**Architectural fragment only**: the policy above assumes full validation and authorization at the parent scope, intact `<base />` inheritance, APIM managed identity enabled, and the backend registered in Entra as `api://BACKEND_APP_ID` accepting tokens from that APIM principal. **Never treat this XML snippet alone as a complete security policy.**

In this flow, the gateway acquires a token **representing APIM's managed identity** to authenticate to the backend; it may **replace the `Authorization` header** sent by the client. Thus the backend sees the **service identity**, not automatically the full end-user identity. If the backend must also enforce per-user or per-order authorization, design a **verifiable user-context propagation mechanism** and corresponding authorization checks, or prefer Model A.

### 12.3. Never trust client-declared `X-User-Id` headers

For example, a backend that simply reads:

```http
X-User-Id: alice
X-Tenant-Id: tenant-a
```

and grants data access is **unsafe** if clients can inject or modify those headers. Even when APIM injects headers, you must:

1. Delete/overwrite any same-named header from the client request **before forwarding**.
2. Ensure the backend **is reachable only through an authenticated channel** and verifies the service identity.
3. Ensure user identity/context is backed by **verifiable proof** (e.g., backend-validated token, trusted signed assertion, or backend authorization service).
4. Never treat headers as the sole source of truth for financial decisions or sensitive objects.

APIM's managed identity is the **gateway's identity**, not permission to access every end user's data. Never turn “APIM can call the backend” into “every user is authorized.”

### 12.4. When the backend calls further downstream services

If Orders API calls Microsoft Graph, Azure SQL, or another API, an access token issued **for Orders API** does not automatically have the right audience for the downstream service. Never blindly forward arbitrary access tokens downstream expecting acceptance. Consider:

- **On-Behalf-Of (OBO)** when downstream calls genuinely require user-delegated permissions and the app flow supports it.
- **Managed identity** when the backend acts under its own workload identity.
- **Client credentials** or federation per service-to-service requirements.

Every downstream API requires an access token with its **own audience and scopes/roles**, plus tenant, data-access, and least-privilege policies.

## 13. Java Spring Security: backend self-validating JWTs

A Java backend using **Spring Boot / Spring Security OAuth2 Resource Server** can validate tokens issued by Microsoft Entra ID as an independent defense layer behind APIM.

### 13.1. Dependencies

With a properly managed Spring Boot dependency setup:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
</dependencies>
```

This example assumes a Spring Boot/Spring Security generation supporting this configuration; actual versions must be managed via an appropriate BOM/plugin and tested before deployment.

### 13.2. Configuring issuer and audience

Example `application.yml`:

```yaml
security:
  orders-api:
    audience: "api://ORDERS_API_APP_ID"

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://login.microsoftonline.com/TENANT_ID/v2.0"
          audiences:
            - "api://ORDERS_API_APP_ID"
```

The `audiences` property is supported in modern Spring Boot versions; if your project uses an older version, configure an explicit **audience validator** on `JwtDecoder` and test it. Never set only `issuer-uri` and assume the backend checks the API audience automatically. You can remove `security.orders-api.audience` in real deployments if unused to avoid dual configuration sources.

### 13.3. Applying scopes and app roles per endpoint

Spring Security typically maps delegated `scope`/`scp` claims to authorities prefixed with `SCOPE_`. For Entra application `roles`, add an explicit converter; do not assume Spring automatically prefixes app roles the way your code expects.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/orders/reconcile")
                    .hasAuthority("APPROLE_Orders.Reconcile")
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
        ).oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())
        ));

        return http.build();
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
                new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> scopeAuthorities =
                    scopeConverter.convert(jwt);
            List<GrantedAuthority> authorities = new ArrayList<>();
            if (scopeAuthorities != null) {
                authorities.addAll(scopeAuthorities);
            }

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                roles.forEach(role -> authorities.add(
                        new SimpleGrantedAuthority("APPROLE_" + role)));
            }
            return authorities;
        });
        return converter;
    }
}
```

In the example above:

- By default **denies all** endpoints without explicit rules (explicitly permit health endpoints if needed).
- Checks `SCOPE_orders.read`/`SCOPE_orders.write` for delegated APIs.
- Maps `roles` to `APPROLE_...` so the daemon endpoint can require `Orders.Reconcile`.
- Relies on resource-server JWT validation to verify signature, issuer, lifetime, and audience **when fully configured**.

**Do not treat this example as a complete production security configuration.** Review CSRF for your app type (stateless bearer-token APIs differ from browser cookie/session apps), CORS, exception handling, session management, method security, authentication entry points, and all real endpoints. If token roles carry meanings other than daemon permissions, add checks for **client application ID, tenant, and principal type** rather than matching role names alone.

### 13.4. Per-order authorization in Java

The controller checks only scopes; the business service must enforce **object ownership**:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {
    private final OrdersService service;

    public OrdersController(OrdersService service) {
        this.service = service;
    }

    @GetMapping("/orders/{orderId}")
    public OrderDto readOrder(
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        String issuerTenantId = jwt.getClaimAsString("tid");
        String principalObjectId = jwt.getClaimAsString("oid");

        // Service pseudocode: map principal/tenant to business permissions,
        // verify order ownership before reading or returning data.
        return service.findOrderAuthorized(
                orderId, issuerTenantId, principalObjectId);
    }
}
```

`OrdersService` and `OrderDto` are illustrative domain types, not Spring Security classes. The backend must check the exact claims of the token type in use; `tid` and `oid` are only identity inputs for an **authorization lookup**—never assume an Entra tenant always maps 1:1 to a SaaS data tenant.

### 13.5. Keep APIM and Java backend policies aligned

If APIM requires `orders.write` while the Java backend accidentally checks only `authenticated()`, the backend remains weaker if accessed directly. Conversely, if Java requires a different audience than APIM, requests valid at the gateway will be rejected by the backend.

A shared **security contract** between both tiers should align on:

- Allowed issuers/tenants and token versions.
- Allowed API audiences.
- `scp`/`roles` definitions per operation.
- How principals map to tenants/users/business authorization.
- 401/403 handling, auditing, and token/key rotation.
- Service-to-service authentication if the gateway uses managed identity.

## 14. Rate limiting, quotas, and abuse protection

JWT validation only determines who may call an operation; it does not limit request volume. A valid client can accidentally or maliciously generate heavy load that overwhelms the backend.

### 14.1. Rate limiting by principal

The example below assumes `validate-jwt` has already executed, validated the token, and stored the JWT object in `validatedJwt`. You can then limit calls per window by `Subject`:

```xml
<rate-limit-by-key
    calls="60"
    renewal-period="60"
    counter-key="@(((Jwt)context.Variables[&quot;validatedJwt&quot;]).Subject)" />
```

This is a **policy fragment** that must be placed **after `validate-jwt`** in `inbound` within an APIM environment supporting the expression/policy. The example assumes a single trusted tenant and `sub` claim; in multi-tenant setups or mixed user/app-only traffic, construct a **composite key distinguishing tenant + principal/client** to avoid collisions or shared quotas.

Gateway rate limiting can be approximate or have consistency limits across gateway units/regions depending on features, topology, and policies. Never use it as an **exact financial transaction quota**; enforce critical business quotas in the backend/database.

### 14.2. Do not use IP as the default user identifier

If many users share an IP behind NAT/proxies, IP-based rate limiting can block the entire group unfairly. Conversely, an attacker rotating IPs can evade simple limits. For JWT-protected APIs, throttling by **verified tenant, client application, or principal** is generally much more meaningful depending on fairness and abuse risk.

### 14.3. Quotas and backend throttling

**Rate limits** protect against short-term bursts. **Quotas** cap total consumption over a longer window per policy/feature. In addition:

- Backends should enforce appropriate concurrency limits, timeouts, and circuit breakers.
- Downstream services like databases, Service Bus, and Key Vault have their own quotas.
- Large HTTP requests need body-size limits and schema validation.
- On 429, clients should retry with backoff/jitter per headers/guidance to avoid retry storms.
- Backend autoscaling does not replace blocking invalid or abusive traffic at the edge.

### 14.4. Blocking oversized requests and schema-invalid payloads

Beyond JWTs, use APIM's **request/content validation** capabilities where appropriate for your API definition and SKU:

1. Restrict `Content-Type` and body size on JSON-accepting endpoints.
2. Validate against OpenAPI schemas or JSON schemas per supported mechanisms.
3. Never allow clients to drive unapproved dynamic backend URLs/routes.
4. Restrict published HTTP methods and paths; never forward all methods unconditionally to the backend.
5. Continue validating inputs in the backend, as the gateway does not know every business invariant.

Request validation in APIM **does not replace** parameterized SQL, output encoding, file-upload checks, or object-level authorization in the Java API.

## 15. CORS, TLS, headers, and HTTP-layer safety

A production API also needs HTTP- and browser-layer protections. These mechanisms complement OAuth/JWT, **but must never replace authentication**.

### 15.1. CORS is a browser policy, not API authorization

**Cross-Origin Resource Sharing (CORS)** lets browsers decide which origin's JavaScript may read responses from another origin. An APIM policy can specify allowed origins, methods, and headers:

```xml
<cors allow-credentials="false">
  <allowed-origins>
    <origin>https://app.orders.example.com</origin>
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
```

This fragment goes in `inbound` ordered appropriately relative to **CORS preflight** and JWT policies. Preflight `OPTIONS` requests normally carry no bearer token; structure CORS policies and API operation handling so browser preflight works safely while business requests remain protected.

CORS **does not block** `curl`, mobile apps, or server-side callers. Non-browser clients can still send bearer tokens. Thus CORS does not prove identity or replace `aud`/`scp`/`roles` validation.

Never pair wildcard origins with browser credentials in violation of CORS rules. If cookie/session auth is used, CSRF defenses are also required; sending bearer tokens in `Authorization` behaves differently from browser-auto-attached cookies.

### 15.2. HTTPS/TLS

- All access tokens must travel over **HTTPS/TLS**; never accept bearer tokens over plaintext HTTP.
- Both APIM and backend domains need valid certificates, trusted chains, and renewal plans.
- For private backends, **a private network does not make TLS optional**.
- With **mTLS**, manage certificate trust, rotation, and revocation—not just certificate presence.
- When APIM calls backends, verify certificate validation, DNS, and routing; never disable certificate checks as a quick fix for handshake errors.

### 15.3. Headers are not an authorization source

APIM can use `set-header` to pass trace/correlation IDs, strip unwanted headers, or inject metadata. However:

- Caller-supplied `X-User-Id`, `X-Roles`, or `X-Tenant-Id` must be treated as **untrusted** unless backed by a verifiable chain of trust.
- Never forward a client's `Authorization` header to a backend that is not the token's audience.
- Never log `Authorization`, cookies, API keys, or secret header values.
- `X-Request-Id` can assist correlation, but normalize/bound its length and never treat it as authentication proof.

### 15.4. Identity-sensitive caching

Gateway caching reduces load, but cache keys **based purely on URL** are dangerous for user/tenant-specific responses:

```text
GET /orders/ORD-1042
  Alice -> Alice's response cached by URL
  Bob   -> calls same URL, could receive wrong data without isolation
```

For personal/order data, **disable public caching by default** unless `Cache-Control`, tenant/principal-aware cache keys, and invalidation are explicitly designed. Caching never replaces object-level authorization.

## 16. Testing policies: token and permission matrix

Policies are verified only after testing **both allow and deny cases**. JWTs especially require negative tests: an overly broad audience or an operation missing `<base />` can expose unintended access.

### 16.1. GET/POST test matrix

Assume:

- `GET /orders`: delegated `scp` contains `orders.read`.
- `POST /orders`: delegated `scp` contains `orders.write`.
- `POST /orders/reconcile`: app-only `roles` contains `Orders.Reconcile` and approved caller.

| Case | GET /orders | POST /orders | POST /orders/reconcile |
|---|---|---|---|
| Missing `Authorization` header | Deny | Deny | Deny |
| Bearer token with tampered signature | Deny | Deny | Deny |
| Expired access token | Deny | Deny | Deny |
| Token before `nbf` | Deny | Deny | Deny |
| Token from untrusted tenant | Deny | Deny | Deny |
| Token with `aud` = Microsoft Graph | Deny | Deny | Deny |
| ID token with `aud` = web client | Deny | Deny | Deny |
| Delegated `scp=orders.read` | Allow at gateway | Deny | Deny |
| Delegated `scp=orders.write`, no read | Deny per example | Allow at gateway | Deny |
| Delegated `scp=orders.read orders.write` | Allow | Allow | Deny |
| App-only `roles=Orders.Reconcile` from valid client | Deny | Deny | Allow |
| App-only missing required role | Deny | Deny | Deny |

“Allow at gateway” **does not mean** the backend returns 200: the Java API can still reject based on object/tenant permissions or business rules. Depending on how validation/authorization is split, actual status codes may be **401**, **403**, or another deliberate policy status; verify against the contract.

### 16.2. Testing object-level authorization

With a JWT carrying `orders.read`:

1. Alice calls `GET /orders/ORD-A` owned by Alice: valid response.
2. Alice calls `GET /orders/ORD-B` owned by Bob: **denied** (403 or 404 per policy).
3. Alice adds `X-Tenant-Id: tenant-b`: must not expand access.
4. Daemon holding only `Orders.Reconcile` calls `GET /orders/ORD-A`: denied unless explicitly permitted by policy.
5. User's permissions change in the system: backend reflects current membership by design rather than trusting stale claims for highly sensitive data.

These are **backend** and data-authorization tests—never substitute APIM returning 401 for an invalid token.

### 16.3. Testing backend bypass

In an authorized environment:

- Call via APIM with a valid access token: verify expected outcome.
- Call the backend hostname directly from an **unapproved source**: must be rejected by network restrictions and/or backend authentication.
- Call the backend with a token intended for a different API: rejected.
- Call the backend with a valid token lacking the required scope: backend rejects.
- Check administrative, health, debug/Swagger/OpenAPI, actuator, and deployment/SCM endpoints too—not just `/orders`.

**Never run penetration tests against resources you do not own.** Test in lab/staging or production according to security/change procedures.

### 16.4. Testing key rotation and clock skew

In a controlled test environment:

- Verify JWKS/OpenID metadata refreshes updated signing keys.
- Test expired JWTs, pre-`nbf` tokens, missing `exp`, and slight clock skew.
- Test valid and invalid token versions/issuers.
- Test metadata endpoint outages against APIM's cache/refetch behavior.
- Confirm the policy never falls back to “allow all” when metadata fails to load.

### 16.5. Quick verification with curl

Assuming `ACCESS_TOKEN` was obtained from an authorized OAuth client **specifically for Orders API**:

```bash
API_BASE="https://api.orders.example.com"

# Do not echo the token or enable shell tracing that logs the Authorization header.
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "$API_BASE/orders"

# Without token: expect rejection if the endpoint requires authentication.
curl -i "$API_BASE/orders"
```

`curl -i` prints response headers/body without needing to print the request `Authorization` header; however, **never** use `curl -v` or `set -x` on machines with shared logs when holding real tokens.

**Never grab an arbitrary token from `az account get-access-token` and assume it carries `scp=orders.read`.** Azure CLI tokens depend on resource and delegated grants; verify real audience/claims or use MSAL/an OAuth client registered with the proper scopes.

## 17. Deploying APIM policies in a controlled manner

### 17.1. Managing policies as source code

In multi-API workflows, policy XML should be managed via **Git + pull requests + IaC** (such as Bicep/ARM/Terraform targeting the Azure API Management resource provider), rather than manual Portal edits alone.

- Maintain a **baseline validation policy** with clear owners, tests, and versions.
- Use **policy fragments** for shared logic where supported instead of copying drifting variants.
- Parameterize `TENANT_ID`, `AUDIENCE`, and backend IDs per environment; never store access tokens/secrets/private keys in repositories.
- Review `<base />` inheritance and **effective policies** after deployment.
- Separate dev/test/prod and run per-operation positive/negative tests.
- Use **what-if/plan** and pre-production validation where tooling supports it.

### 17.2. One gateway hosting multiple APIs

An APIM instance can host multiple APIs with distinct audiences. If a global policy validates only the Microsoft Entra issuer **without validating each API's exact audience**, a token for API-A could be accepted on API-B.

A gateway-wide baseline can enforce common rules, **but does not replace audience-specific checks**. API/operation policies must verify the exact audience. Regardless of structure, **cross-audience token testing** is mandatory.

### 17.3. Deploying via pipeline

```text
Developer modifies APIM policy XML
       |
       v
Pull request + security review
       |
       v
Lint/validate policy syntax + environment config
       |
       v
Deploy DEV APIM
       |
       v
Positive/negative JWT tests + backend bypass tests
       |
       v
Deploy STAGING + canary/controlled traffic
       |
       v
Approval
       |
       v
Deploy PROD + verify effective policies, logs, alerts
       |
       v
Roll back to tested policy version if needed
```

**Successful XML parsing does not prove security**: a policy can be syntactically valid yet have the wrong audience, wrong order, missing `<base />`, or overly broad conditions.

### 17.4. Separation of duties across teams

- **Identity team** manages Entra App Registrations, scopes, app roles, and consent.
- **API/platform team** manages APIM, policies, backend routing, and networking.
- **Backend team** manages Java code, business authorization, and data.
- **Security/SRE** reviews least privilege, logs/alerts, and incident response.

A single CI identity should not automatically hold subscription **Owner**, App Registration edit rights, and production APIM policy permissions all together.

## 18. Error handling and safe client responses

An API must return meaningful errors without leaking internal details.

| Situation | Typical code | Principle |
|---|---|---|
| Missing bearer token | 401 | Do not forward to backend; return concise error |
| Invalid signature / expired / wrong audience token | 401 | Never leak token or key contents |
| Valid token lacking scope/role | 403 | Never disclose info about other users' permissions |
| Valid user reading another user's record | 403 or 404 by design | Prevent object enumeration |
| Rate limit exceeded | 429 | Support sensible retry/backoff |
| Invalid body schema | 400 or contract-specified code | Return controlled validation error |
| Backend temporarily unavailable | 502/503/504 per cause | Never return stack traces or infrastructure secrets |

Safe response example:

```json
{
  "error": {
    "code": "ACCESS_DENIED",
    "message": "You do not have permission to perform this operation.",
    "correlationId": "req-7f95c2"
  }
}
```

Never include raw JWTs, signing keys, private database URLs, or policy expression exceptions in responses. Trace/correlation IDs let SREs locate logs without exposing security details.

### 18.1. Combining `on-error` with auditing

APIM provides an `on-error` section to handle errors raised in policies/gateway per capabilities. Use it to standardize error messages, emit safe telemetry, or attach correlation IDs—**never use `on-error` to return 200 on a failed JWT validation**.

If using `return-response` to return a generic message, preserve the blocking status code, omit internal exceptions, and keep audit logs intact. Downstream failures must not masquerade as “user not signed in” when the real cause is a backend outage.

### 18.2. 401 and 403 in diagnostics

In the earlier scope/role policy example, `failed-validation-httpcode="403"` can return 403 even for an invalid token during that validation pass. Thus **HTTP status alone** cannot prove “valid token lacking permission.” In production, cleanly separate **authentication (401)** from **authorization (403)** with tested policies, while keeping internal logs detailed enough to distinguish causes.

Never emit raw tokens, full `kid`/JWT payloads, or issuer/private-key configuration in public responses. Internal logs must be protected with RBAC and appropriate retention.

## 19. Logging, Azure Monitor, and incident investigation

Azure API Management integrates with **Azure Monitor**, **diagnostic settings**, **Log Analytics**, and **Application Insights** per tier capabilities. The goal is knowing whether requests stopped at the gateway or reached the backend **without logging full payloads or tokens**.

### 19.1. Key signals

| Source | Signal | Purpose |
|---|---|---|
| APIM gateway diagnostics | Status, API/operation, duration, backend status, correlation ID | Distinguish policy, gateway, and backend errors |
| Entra sign-in / workload identity telemetry | Token acquisition/consent/trust errors per available permissions/data | Check whether callers obtained tokens |
| Java backend logs | Authorization denied, request ID, sanitized principal/tenant, business decisions | Investigate per-order permissions |
| Application Insights/tracing | Request/dependency latency, exceptions, distributed traces | Isolate code, database, or downstream issues |
| Azure Activity Log | Changes to APIM policies, networking, and IAM resources | Identify recent config changes causing failures |
| WAF/edge logs if present | Rates, bot/attack patterns, blocked rules | Separate security abuse from client bugs |

APIM gateway logs will not capture requests blocked **in front of the gateway** by WAF, DNS, or network rules; each layer observes only traffic that reaches it.

### 19.2. Example KQL for APIM gateway logs

If APIM diagnostic settings send gateway logs to Log Analytics into the **`ApiManagementGatewayLogs`** table:

```kusto
ApiManagementGatewayLogs
| where TimeGenerated > ago(1h)
| summarize Requests=count()
    by bin(TimeGenerated, 5m), ResponseCode
| order by TimeGenerated asc
```

To inspect rejected requests:

```kusto
ApiManagementGatewayLogs
| where TimeGenerated > ago(1h)
| where ResponseCode in (401, 403, 429)
| summarize Rejections=count()
    by bin(TimeGenerated, 5m), ResponseCode, ApiId
| order by TimeGenerated asc
```

Table and column names can vary by **diagnostic category, resource-specific table mode, APIM tier, and current settings**. Legacy setups may use `AzureDiagnostics`. If a query reports a missing table, check diagnostic settings, the **target workspace**, and the actual schema rather than guessing column names.

**Do not assume every 401/403 is an attack**: clients may have expired tokens, wrong audiences, missing consent, recently updated policies, or cross-environment identity mismatches.

### 19.3. Questions to ask during a 401 spike

1. Which **API/operation**, tenant, or caller type is experiencing the spike?
2. Did it start immediately after a change to Entra App Registration, audience, scopes, or APIM policies?
3. Did JWT token version/issuer change, or did signing keys rotate recently?
4. Was the token acquired for the **right resource** and sent with the Bearer scheme?
5. Is the 401 coming from APIM or the Java backend? Is there any backend response?
6. Is a single client affected, or all clients?
7. Are there signs of tokenless scans, tampered tokens, or anomalous replays?

When debugging, log only **sanitized metadata** and correlation IDs. Never attach raw access tokens to support tickets or unsecured chat channels.

### 19.4. Dashboards and alerts

Recommended dashboard widgets:

- Request volume by API/operation and environment.
- 401/403/429 rates over time, safely segmented by tenant/client where available.
- 5xx rates and p50/p95/p99 latency at gateway and backend.
- Backend availability/timeout rates.
- Policy deployment frequency and Azure Activity Log changes.
- APIM capacity/usage, rate-limited requests, and tier costs.

Useful alerts: sudden 401 spikes after a policy deployment; elevated 403s on sensitive operations; sustained 429 spikes; backend 5xx exceeding SLO; or backend public access enabled outside change control.

**Every alert needs an owner, threshold, evaluation window, action group, and runbook.** An alert like “401 > 0” on a public API generates constant noise and zero operational value.

## 20. Troubleshooting: bad token, bad policy, or bad backend?

A 401/403/502 response can originate at several layers. Ordered investigation flow:

```text
Did the client acquire an access token?
      |
      +-- No  -> check OAuth grant, redirect/PKCE,
      |          consent, client/federated credential
      v
Is Authorization header using the right scheme?
      |
      +-- No  -> fix client; never loosen APIM validation
      v
Did APIM validate signature/issuer/audience/lifetime?
      |
      +-- Fail -> compare App Registration, token version,
      |           metadata/JWKS, clock, and scope
      v
Did APIM validate operation scp/roles?
      |
      +-- Fail -> inspect principal, grant, consent,
      |           effective policy, <base />
      v
Can gateway route to backend?
      |
      +-- No  -> VNet/DNS/NSG/firewall, backend TLS,
      |          managed identity/mTLS, policy routing
      v
Did backend authenticate/authorize the request?
      |
      +-- No  -> issuer/audience in Java, object ownership,
      |          backend roles, user/tenant mapping
      v
Are business logic and dependencies healthy?
      |
      +-- No  -> database, downstream, timeouts, app logs
      v
Request succeeds per contract
```

### 20.1. Symptom – cause – check table

| Symptom | Possible cause | What to check |
|---|---|---|
| Immediate 401 at APIM | Missing token, wrong scheme, invalid/expired token | `Authorization` header, validation logs, access token metadata |
| 401 after a login change | API audience/issuer or token version changed | `aud`/`iss`/`ver`, App Registration, APIM policy |
| 401 after key rotation | JWKS metadata not refreshed or wrong issuer URL | Trusted discovery URL, safe `kid`, cache/refetch behavior |
| 403 on one operation | Missing delegated scope/app role or client allowlist | `scp`, `roles`, `azp`/`appid`, effective policy |
| GET works but POST returns 403 | Has `orders.read` but lacks `orders.write` | Permission model/consent, operation `required-claims` |
| Daemon gets 403 while user GET works | App-only token lacks `Orders.Reconcile` | App role assignment, client credentials token, approved caller |
| 401 from Java after passing gateway | Backend issuer/audience differs or token replaced | Auth model A/B, request headers, Spring Resource Server |
| Java returns 403 after gateway allows | Object-level authorization or backend role missing | Order owner/tenant membership, service permission lookup |
| 502/504 reaching backend | DNS, TLS, network, or backend outage | APIM backend diagnostics, private endpoint, App Service/AKS health |
| Direct backend call succeeds with no token | Backend unprotected | Private networking, Easy Auth/Spring auth, route restrictions |
| CORS preflight fails | `OPTIONS` mishandled, origin/method/header blocked | Policy order, allowed origins, browser console |
| 429 increases | Rate-limit/quota or downstream throttling | Counter key, scopes, SLO, client retries |
| Valid token lets one tenant read another's data | Broken object-level authorization | Backend membership/data isolation; never trust user headers |

### 20.2. Do not “fix” issues by disabling validation

Dangerous “fixes”:

- Removing `<audiences>` to accept tokens from any API.
- Using `/common` issuer and accepting un-onboarded tenants.
- Setting `require-signed-tokens="false"`.
- Allowing long-expired `exp` tokens or disabling expiration checks.
- Granting `orders.write`/`Orders.Reconcile` to every user.
- Opening the backend publicly and disabling Easy Auth/Spring Security.
- Trusting client-sent `X-User-Id` or checking only subscription keys.
- Enabling verbose logging that captures raw bearer tokens.

The right fix is **isolating the failing layer**, comparing token/resource/policy against the contract, and applying a minimal verified correction.

### 20.3. Works locally, fails in production

Local environments may use **a different client application, token audience, or Entra tenant** than production. For daemons, local developer `az login` often carries delegated scopes, whereas production managed identity receives **app-only roles**. Never assume two tokens have identical claims simply because both came from Entra ID.

Keep a comparison table **without raw tokens**: tenant, issuer, audience, grant type, client ID, scopes/roles, API operation, timestamp, policy version, and error code. Compare metadata in dev/test to pinpoint the mismatch.

## 21. Architecture scenario: Orders API for web and daemon

### 21.1. Business requirements

An enterprise wants to publish an API:

```text
GET    /orders                  Users view their own order list
GET    /orders/{orderId}        Users view details of orders they own
POST   /orders                  Users create an order
POST   /orders/reconcile        Internal daemon reconciles orders
GET    /health                  Minimal health endpoint per policy
```

The web app uses Microsoft Entra ID sign-in. The daemon has its own service principal/managed identity rather than signing in as a human user. The Java backend runs on Azure App Service backed by Azure SQL. APIM is the sole public gateway permitted to forward traffic to the backend under the designed topology.

**Security requirements:** bearer JWTs must have the right issuer and audience; web callers receive only granted `orders.read`/`orders.write` permissions; the daemon can reconcile only with `Orders.Reconcile` and an allowlisted caller application; the Java API checks ownership of every order; and the backend allows no direct access bypassing APIM.

### 21.2. Proposed design

```text
                          Microsoft Entra ID
                          /                \
               web user access token   daemon app token
                       |                     |
                       v                     v
                 Azure API Management
                 -----------------------------
                 Inbound:
                 - verify signature via trusted JWKS
                 - verify iss, aud, exp, nbf
                 - GET: orders.read
                 - POST: orders.write
                 - reconcile: Orders.Reconcile
                 - limit requests and validate input
                 -----------------------------
                               |
                               | private network / allowed path
                               v
                       Orders Java API
                       - validate JWT again
                       - check scope/role
                       - check tenant/order ownership
                               |
                               v
                            Azure SQL
```

In this diagram, **Model A** is chosen: preserve the Orders API-targeted user access token so the backend re-validates it. APIM sits in an appropriate network topology to reach the backend via an approved path. DNS, TLS, private endpoints, and network support parameters must be verified against the actual APIM and App Service tiers.

### 21.3. Design permission matrix

| Role/Scope | GET /orders | POST /orders | POST /orders/reconcile |
|---|---|---|---|
| `orders.read` | Yes, per ownership | No | No |
| `orders.write` | No, unless read granted | Yes, per business rules | No |
| `Orders.Reconcile` from approved app-only caller | No | No | Yes |
| Missing required permission claim | No | No | No |

The matrix shows **API operation-level authorization**. A user holding `orders.read` still sees only orders confirmed by the backend as within their permitted scope. App role `Orders.Reconcile` does not automatically let the daemon edit arbitrary tables; the backend must restrict transactions, database permissions, and auditing.

### 21.4. Implementation steps

1. Register the Orders API resource and clients in Entra ID; expose delegated scopes and app role.
2. Grant permissions/consent per policy; inspect real web and daemon access tokens.
3. Create or select the APIM gateway; publish API definitions and backend routes.
4. Configure mandatory JWT validation checking exact issuer and audience.
5. Apply per-operation `scp`/`roles`, daemon allowlists, and rate limits.
6. Configure Java Resource Server with matching audience/issuer, endpoint authorization, and ownership checks.
7. Design private routing/ingress restrictions preventing backend bypass.
8. Enable safe diagnostics, alerts, dashboards, and correlation IDs.
9. Execute the test matrix (positive/negative/cross-tenant/bypass).
10. Deploy to staging/canary, review effective policies, then roll out to production.

### 21.5. Acceptance criteria

- Missing, malformed, expired, or wrong-audience tokens never reach the business backend.
- Per-operation scopes/roles are enforced without policy inheritance gaps.
- Orders belonging to another tenant/user cannot be read even with a valid token.
- Direct backend URLs reject unapproved clients attempting to bypass the gateway.
- App-only daemons cannot invoke user-only endpoints without explicit policy approval.
- Logs/audits support incident response without storing bearer tokens, secrets, or unnecessary sensitive data.
- Rate limits/quotas do not break legitimate clients due to poorly chosen counter keys.

## 22. Threat modeling: ways designs can fail

Before promoting an API to production, test not only happy paths but also attempts to misuse tokens or configurations.

### 22.1. Cross-audience token reuse

A user holds a token issued for Microsoft Graph. If APIM validates only the issuer without checking `aud`, that token could mistakenly access Orders API.

**Mitigation:** `aud` must match the exact approved resource per token version and API registration; verify tokens from other resources are rejected.

### 22.2. Multi-tenant issuer confusion

A multi-tenant app accepts tokens from un-onboarded tenants. If the backend keys solely on `oid` without combining `tid` or tenant mapping, identity collisions or cross-tenant access can occur.

**Mitigation:** validate issuer/tenant, maintain an onboarded-tenant allowlist, key principals properly with tenant context, and check tenant membership on every data access.

### 22.3. Delegated scope vs. app role confusion

A daemon holds app role `Orders.Reconcile`, while a user endpoint checks only “any valid token is allowed”; or a user with `orders.write` invokes reconcile.

**Mitigation:** specify accepted grant/claim/caller types per operation; check roles **alongside** issuer, audience, tenant, and client ID where appropriate.

### 22.4. Privilege escalation via policy override

An operation omits `<base />`, causing parent token validation to stop being inherited.

**Mitigation:** inspect effective policies, lint/scan policy diffs, run negative tests on every operation, and restrict security policy edits to approved teams.

### 22.5. Gateway bypass

The backend's public URL lacks authentication, allowing callers to hit the backend directly and skip gateway validation/rate limits.

**Mitigation:** use private networking or strict access restrictions, enforce backend JWT/service auth, and test direct access from external sources.

### 22.6. Object-level authorization bypass

Alice holds `orders.read` and changes the URL to Bob's order; the Java API checks only scope and returns Bob's data.

**Mitigation:** enforce ownership/tenant checks in repository/service layers, apply least-privilege database access, and add cross-user/cross-tenant tests.

### 22.7. Stolen bearer token

An attacker obtains a valid bearer token and replays it elsewhere within its lifetime.

**Mitigation:** protect transport/storage, avoid logging/sharing tokens, enforce short lifetimes per policy, use IdP risk controls, and adopt sender-constrained tokens where supported. Never assume a JWT signature prevents **replay**; signatures do not verify the token is used on the original device.

### 22.8. Header spoofing and forwarded identity

The backend trusts client-declared `X-User-Id`, or an unapproved gateway can inject headers.

**Mitigation:** strip untrusted headers, authenticate APIM-to-backend calls, rely on verifiable identity proofs, and never trust standalone headers in the backend.

### 22.9. Denial of service by a valid client

A client with a valid token floods requests and exhausts the SQL connection pool.

**Mitigation:** rate-limit by verified principal/tenant, cap request/resource sizes, enforce backend concurrency controls, autoscale, add circuit breakers, and monitor.

## 23. Cost, availability, and lifecycle governance

JWT validation is essential for security, yet operating gateways and observability incurs cost and latency. Optimization means choosing the right architecture and eliminating redundant work—not skipping security checks.

### 23.1. Cost factors

| Item | What drives it |
|---|---|
| **API Management tier/capacity** | APIM SKU, gateway units/locations, uptime, and feature limits |
| **Traffic** | Request volume, outbound bandwidth, networking, and WAF/Front Door integration |
| **Backend** | App Service Plan/AKS compute, databases, storage, dependent APIs |
| **Observability** | Log Analytics ingestion/retention, Application Insights, alerts |
| **Identity** | Entra ID/Conditional Access features or related licensing per requirements |
| **Networking/security** | Private endpoints, NAT, Firewall, VNet gateways, certificates |
| **Operations** | Policy reviews, incident response, schema/contract tests, permission maintenance |

Never quote a fixed unit price across all regions/tiers. When budgeting, use the **Azure Pricing Calculator** and **Cost Management** post-deployment to inspect real cost drivers.

### 23.2. OpenID key caching and verification latency

APIM caches and refreshes metadata and public keys for token verification; it **does not** need to call Microsoft Entra ID to introspect every JWT on every request under standard `validate-jwt`. Still:

- Signing key rotation and cache refresh remain operational events to plan for.
- Repeating identical `validate-jwt` policies unnecessarily across multiple scopes adds avoidable overhead.
- Never reduce overhead by **removing signature/issuer/audience/lifetime checks**.
- Review complex policy expressions carefully, especially under high traffic.

### 23.3. APIM as a dependency in the request path

Placing APIM as a centralized gateway brings governance benefits, while also requiring:

- Gateway and backend SLOs.
- Testing failure modes when APIM is unavailable or backend connectivity fails.
- Capacity planning for rate limits, gateway units/regions, and networking.
- Policy rollback procedures that never accidentally open the API.
- DNS, certificate rotation, and disaster recovery plans suited to the tier.

**Never create an unauthenticated public “backup” bypass path** straight to the backend. Any failover path must preserve the same security boundaries.

### 23.4. Secrets and certificates

When backend client certificates or credentials cannot be replaced with managed identity:

1. Store secrets in a secure managed store (such as Azure Key Vault where supported).
2. Grant least-privilege access to APIM/backends needing retrieval.
3. Assign owners, rotation/expiry alerts, and dual-key/certificate rollover where supported.
4. Never place secrets in policy XML, Git, logs, or support tickets.
5. Verify Key Vault network/identity access before production rotations.

Managed identity reduces long-lived client secrets, **but does not** replace permission governance and auditing.

## 24. Hands-on exercises

### Exercise A: audience and issuer policy

**Context:** APIM is currently accepting a Microsoft Entra ID JWT whose `aud` is Microsoft Graph, whereas the target resource is Orders API.

**Tasks:**

1. Explain why a valid signature alone is insufficient.
2. Write the `<audiences>` and `<issuers>` sections for Orders API.
3. Explain what must change if the API receives v1 tokens instead of v2.
4. Describe a negative test proving a Graph token cannot call Orders API.

**Solution guide:** pin the issuer to the exact tenant/version and audience to the Orders API resource; do not remove validation even though Entra signed the token. Use a real access token issued for Orders API when testing.

### Exercise B: delegated and daemon permissions

An API has three operations: `GET /orders`, `POST /orders`, and `POST /orders/reconcile`.

**Task:** design `required-claims` so GET requires `scp=orders.read`, POST requires `scp=orders.write`, and reconcile requires `roles=Orders.Reconcile` plus an approved client ID. Evaluate why a daemon should not carry a fake `scp` to pass policy.

**Solution guide:** each operation has distinct permissions; delegated tokens and app-only tokens carry different claim structures. Trust claims only after signature/issuer/audience validation; never trust a client-supplied “clientId” header.

### Exercise C: detecting backend bypass

A Java API runs on App Service at `https://orders-api-prod.azurewebsites.net`. Clients without JWTs can still call it directly, even though calling via APIM returns 401.

**Task:** present two independent remediation layers: network restriction and backend authentication. Write a test proving direct calls from unapproved sources are rejected.

**Solution guide:** use private endpoints/access restrictions aligned with the APIM tier/topology, combined with Spring Security/Easy Auth or trusted service identity. Never rely solely on hiding hostnames or renaming DNS.

### Exercise D: object authorization

User Alice holds scope `orders.read` and calls `GET /orders/ORD-B` owned by Bob.

**Task:** explain why APIM may allow the call through while the Java API must reject it; propose how to map `tid`/`oid` to data permissions without trusting `X-Tenant-Id`.

**Solution guide:** `orders.read` grants permission for an action type, not all users' data. The backend must verify membership and ownership against a trusted authorization store.

### Exercise E: operational incident

After a policy change, all clients receive 401. APIM logs show surging `ResponseCode=401`, and the backend receives zero requests.

**Task:** outline the investigation sequence across policy version, issuer, audience, `<base />`, OpenID metadata/JWKS, request token type, and safe rollback.

**Solution guide:** identify the latest change, inspect non-sensitive access token metadata, compare issuer/audience/version, check effective policies, and execute rollback **to the prior valid policy** without disabling validation.

### Exercise F: optimizing rate limiting

One hundred employees share a NAT IP. An IP-based rate-limit policy triggers widespread 429s despite low per-user request volume.

**Task:** propose rate limiting by verified principal or tenant, noting conditions for app-only daemons and multi-tenant callers. Account for how gateway scaling makes counters approximate.

**Solution guide:** use an identity-based key after JWT validation, combining tenant/principal to avoid collisions; enforce exact business quotas in a dedicated backend data store.

## 25. Self-check questions

**1. Is a JWT with a valid signature enough for a backend API?** No. You must also verify issuer, audience, lifetime, per-operation permissions, and object-level authorization.

**2. What should the `aud` of an access token be?** The target resource/API the caller intends to invoke—not by default the SPA client or Microsoft Graph.

**3. Should an ID token be used instead of an access token to call a REST API?** No. An ID token's audience is the sign-in client, not proof of permission to call a resource API.

**4. How do `scp` and `roles` differ?** `scp` typically represents delegated scopes while `roles` typically represents app roles depending on token/grant; policies must distinguish caller types.

**5. Why is `iss` important?** It identifies the token issuer; APIs must trust only approved issuers/tenants/versions.

**6. What does `openid-config` provide?** It gives the validator access to metadata/public keys from a trusted issuer to verify signatures and handle key rotation.

**7. Why must `alg=none` never be accepted?** An unsigned token cannot prove its claims were issued by a trusted issuer.

**8. Why does `scp=orders.read` not mean a caller can read every user's orders?** Scope grants operation-type permission only; the backend must check ownership/tenant membership per record.

**9. What is `<base />` used for in APIM policies?** It marks where policies from parent scopes are inherited; omitting it can accidentally drop shared validation.

**10. Can an APIM subscription key replace a JWT access token?** No. It manages API subscriptions/quotas under the product model and does not replace user authentication and authorization.

**11. Does CORS block `curl` from calling an API?** No. CORS is enforced only by web browsers.

**12. Does a backend with only a private endpoint still need authentication?** Yes, per threat model; private networking controls connectivity, not user data permissions.

**13. Who does APIM's managed identity represent?** APIM's gateway/service principal—not individual end users automatically.

**14. Why validate JWTs in the Java backend even when APIM already validates them?** For defense-in-depth, protection against direct access, and properly scoped operation/data authorization.

**15. What problems can IP-based rate limiting cause?** Many users behind NAT get blocked together, while malicious clients can rotate IPs to evade limits.

**16. How do 401 and 403 differ under standard semantics?** 401 means unauthenticated/invalid token; 403 means authenticated but lacking permissions. Policies may need tuning to preserve this distinction.

**17. Why must bearer tokens never be logged?** They are credentials vulnerable to replay while valid; logs are stored and accessed much more broadly than application memory.

**18. When JWKS key rotation happens, should signature verification be disabled?** No. Check the trusted metadata source, cache/refetch behavior, and signing key policy.

**19. When 401s appear after deployment, what is the first step?** Identify the affected operation, policy version, JWT issuer/audience, and failure point—never open permissions or disable validation.

**20. Why inspect the effective policy per operation?** An operation can inherit or override rules differently from the API-level policy an operator is looking at.

## 26. Production readiness checklist

### 26.1. Identity and tokens

- [ ] Orders API has an App Registration and **audience verified from real access tokens**.
- [ ] Trusted issuers/tenants and token versions are locked down rather than trusting all tenants by default.
- [ ] API rejects unsigned, invalid-signature, expired, and not-yet-valid tokens.
- [ ] OpenID discovery/JWKS comes from an approved issuer; key rotation plan is ready.
- [ ] Browser/mobile clients use OAuth2 Authorization Code + PKCE where appropriate with no embedded client secrets.
- [ ] Daemons use app-only identity and least-privilege roles, with caller allowlisting where needed.
- [ ] `scp`/`roles` and other claims are checked from **verified tokens**, never client-declared headers.
- [ ] Tested missing, expired, wrong-tenant, wrong-audience, wrong-grant-type, and tampered-signature tokens.

### 26.2. API Management policies

- [ ] `validate-jwt` executes before traffic reaches the backend, checking issuer/audience/lifetime.
- [ ] Sensitive operations enforce exact scopes/roles rather than one overly broad rule.
- [ ] `<base />` and **effective policies** verified across global/product/API/operation scopes.
- [ ] Subscription keys are never used as the sole authentication mechanism.
- [ ] Rate limits, quotas, and input validation align with SLOs and threat model.
- [ ] CORS permits exact origins/methods/headers, handling preflight without opening business requests.
- [ ] User-specific responses are never cached by shared URL lacking principal/tenant boundaries.
- [ ] Error responses never leak JWTs, signing keys, internal paths, or stack traces.
- [ ] APIM policies are versioned, reviewed, tested, and have a clear rollback path.

### 26.3. Backend and networking

- [ ] Backend cannot be called directly from unapproved sources to bypass gateway controls.
- [ ] End-to-end JWT vs. gateway managed identity chosen intentionally.
- [ ] If APIM uses managed identity, backend verifies the exact APIM principal/audience and handles user authorization separately when needed.
- [ ] Java Resource Server verifies issuer/audience/expiration/roles/scopes per the security contract.
- [ ] Java service verifies tenant membership and object ownership for every record.
- [ ] Backend never trusts self-declared `X-User-Id`/`X-Tenant-Id`.
- [ ] HTTPS/TLS, certificate lifecycle, private DNS/routing, firewalls, and endpoint exposure reviewed.
- [ ] Secrets/certificates managed in an approved store, never hardcoded in policies/code/logs.

### 26.4. Observability and operations

- [ ] APIM diagnostic settings / Log Analytics / Application Insights enabled per needs and permissions.
- [ ] Logs capture correlation ID, API/operation, status, and latency **without raw tokens**.
- [ ] Dashboards track 401/403/429, backend 5xx, latency, and policy rollouts.
- [ ] Alerts define thresholds, owners, action groups, and runbooks.
- [ ] Direct backend access, cross-tenant access, and cross-audience tokens tested.
- [ ] Metadata/JWKS refresh and issuer change procedures tested.
- [ ] IAM access controls cover policies, App Registrations, backends, and diagnostic data.
- [ ] APIM, monitoring, networking, and backend costs and capacity estimated.
- [ ] Canary/staging rollout and **security-preserving** rollback ready.

## 27. Conclusion

**Azure API Management** governs and validates API access through policies like **`validate-jwt`**, but real protection goes well beyond “having a bearer token.” APIs must verify **signature, issuer, audience, lifetime**, and per-operation **delegated scopes or application roles**. With Microsoft Entra ID, OpenID Connect discovery/JWKS establishes a clear trust chain and supports signing-key rotation; APIM policy inheritance must be verified so no endpoint accidentally skips validation.

Equally critical protections live **behind the gateway**: restricting direct backend access, authenticating service-to-service or end-user identities accurately, enforcing **object-level authorization** in Java, and controlling request rates, CORS, TLS, secrets, and telemetry. Combining **security policy as code, negative tests, monitoring, and runbooks** lets teams run APIs on Azure securely, auditably, and at scale without trading security for convenience.
