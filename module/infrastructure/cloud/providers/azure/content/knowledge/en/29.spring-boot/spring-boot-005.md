# Protecting a REST API with Microsoft Entra Access Tokens

A Spring Boot application deployed on **Azure App Service**, **Azure Container Apps**, or **Azure Kubernetes Service (AKS)** exposes an order-management REST API. The frontend signs in with corporate accounts via **Microsoft Entra ID** and sends requests to `GET /api/orders`. If the backend merely checks whether the `Authorization` header starts with `Bearer`, an attacker can send a forged string and read data. If the backend merely decodes the JWT payload without validating signature, issuer, audience, and permissions, tokens issued for other services can also be misused.

**Protecting a REST API with Microsoft Entra access tokens** means configuring Spring Boot as an **OAuth 2.0 Resource Server**: accepting access tokens, verifying they were issued by a trusted identity provider **specifically for this API**, checking lifetimes and mandatory claims, and enforcing **authorization** by scope, app role, and data ownership. A cryptographically valid token **does not automatically permit** the caller to read every resource.

This lesson belongs to the **Spring Boot on Azure** chapter of the **CLOUD_PROVIDERS_AZURE** module, connecting your Azure learning path from subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, and storage to deployment, monitoring, security, and cost control. Examples use **Java 17+, Spring Boot 3.x, Spring Security 6, and OAuth2 Resource Server**. Property names, dependencies, APIs, and token-authentication capabilities must be verified against your actual version; never store real secrets or access tokens in source code, logs, or lab notes.

> **Scope:** this lesson focuses on a **Microsoft Entra ID workforce tenant** and **JWT access tokens for organization-registered APIs**. Microsoft Entra External ID, legacy B2C, Microsoft Graph–specific tokens, tenant-specific configurations, and endpoints with custom claim policies may require separate validation logic. Never assume every access token can be decoded by the frontend or carries the exact same set of claims.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish **OAuth 2.0**, **OpenID Connect**, **access tokens**, **ID tokens**, and **refresh tokens**.
2. Describe registering an **API app registration** and declaring **delegated scopes** and **application app roles** in Microsoft Entra ID.
3. Explain **Authorization Code + PKCE**, **client credentials**, and when to use **On-Behalf-Of (OBO)**.
4. Configure Spring Boot as an **OAuth2 Resource Server** to validate JWT signatures via OpenID Connect/JWKS.
5. Properly verify **issuer (`iss`), audience (`aud`), expiration (`exp`), not-before (`nbf`), tenant (`tid`)**, and related claims.
6. Map `scp` to `SCOPE_*` authorities, `roles` to `ROLE_*` authorities, and apply method security.
7. Distinguish **401 Unauthorized** from **403 Forbidden** and design per-endpoint API authorization.
8. Enforce **tenant isolation** and ownership checks at the data layer rather than relying solely on a broad scope.
9. Write tests for valid tokens, wrong audience/issuer, expired tokens, missing scopes/roles, and cross-tenant access.
10. Deploy cleanly to Azure, safeguard secrets, monitor security errors, and build incident runbooks.

## 2. Security Model: Who Issues the Token, Who Validates It?

~~~mermaid
sequenceDiagram
  participant U as User
  participant C as Frontend / Client
  participant E as Microsoft Entra ID
  participant A as Spring Boot REST API
  participant D as Database
  U->>C: Initiate sign-in
  C->>E: OAuth Authorization Code + PKCE
  E-->>C: Access token for authorized API
  C->>A: GET /api/orders + Authorization Bearer
  A->>E: Fetch OpenID metadata/JWKS when needed
  E-->>A: Public signing keys / metadata
  A->>A: Verify signature, issuer, audience, time
  A->>A: Check scope/role and tenant
  A->>D: Query data by identity and permissions
  D-->>A: Permitted orders
  A-->>C: 200 with filtered data
~~~

Roles:

| Role | In this example | Responsibility |
|---|---|---|
| **Resource Owner** | Enterprise user | Grants client access within appropriate boundaries |
| **Client** | SPA/mobile/backend | Requests access tokens and calls the API |
| **Authorization Server** | Microsoft Entra ID | Authenticates principals and issues tokens after policy/consent |
| **Resource Server** | Spring Boot REST API | Validates tokens and enforces data access rules |
| **Downstream resource** | Azure SQL/Cosmos DB/Graph | Enforces its own authentication/authorization |

**The Spring Boot API must never blindly trust that "the frontend already signed in."** Every token-bearing request must be validated by the resource server per policy; the frontend is not a trusted boundary.

### JWT Signature Verification Normally Does Not Call Entra Per Request

For JWT access tokens accepted by the API, the resource server usually downloads **public keys from the JWKS endpoint**, caches them per HTTP/SDK behavior, and verifies signatures locally without calling Entra ID to introspect every token. However:

- Startup or key refresh has a network/metadata dependency.
- Key rotation and caching must be handled properly.
- Offline JWT verification does not provide instant token revocation on its own.
- Non-JWT tokens or other API types may require different validation mechanisms.

## 3. Where Does OAuth 2.0 Differ from OpenID Connect?

**OAuth 2.0** is primarily an authorization framework: a client obtains an **access token** to call a resource/API within granted scopes. **OpenID Connect (OIDC)** extends OAuth to authenticate user identity using an **ID token** and identity claims.

| Token | Intended consumer | Purpose |
|---|---|---|
| **Access token** | Resource server/API listed in `aud` | Authorizes API calls with specific scopes/roles |
| **ID token** | **Client application** matching the client ID audience | Tells the client that login/user authentication occurred |
| **Refresh token** | Authorized OAuth client holding the token | Acquires fresh access tokens per session/policy |
| **Client credentials access token** | Downstream API | Calls an API under application identity, with no user context |

Critical mistake: **accepting an ID token as a Bearer token in an API**. An ID token normally carries the frontend/client's `aud`, not the REST API's audience. An API must require an **access token issued specifically for itself**, never repurposing an ID token simply because its payload has `name` or `email`.

### An ID Token Does Not Prove API Authorization

Successful user login only shows Entra authenticated the user for the client flow. The user might still:

- Lack a delegated scope for the API.
- Lack a required app role.
- Belong to an unauthorized tenant.
- Lack permission to view a specific database record.
- Be blocked by organizational access policies.

**Authentication** answers "who is the principal"; **authorization** answers "is this principal allowed to perform this action on this resource."

## 4. Three Essential Flows for Obtaining Access Tokens

| Flow | When to use | User present? | Typical permissions |
|---|---|---|---|
| **Authorization Code + PKCE** | SPA/mobile/native app signing in a user | Yes | Delegated scopes in `scp` |
| **Client Credentials** | Daemon/job/service-to-service | No | Application permissions/app roles in `roles` |
| **On-Behalf-Of (OBO)** | API A must call API B on the user's behalf | Yes | Delegated permissions for API B |

### Authorization Code + PKCE

The client signs in via browser/redirect, protects the authorization code with **PKCE**, and requests an access token with the API's scope, e.g., `api://<API_APP_ID>/Orders.Read`. For a SPA, never embed a client secret because a SPA is a public client. Use MSAL or a supported OAuth/OIDC client library instead of hand-crafting token requests.

### Client Credentials

A background job acquires an access token under a governed **application identity**, typically requesting `api://<API_APP_ID>/.default` with admin-consented/assigned application permissions. An app-only token **has no user** to populate `currentUserEmail`.

### On-Behalf-Of

If Java API A receives an access token meant for **A** and needs to call API B on the user's behalf, never forward the `aud=A` token straight to B. API A executes the **OBO flow** to exchange it for a new `aud=B` token with the appropriate delegated permissions. Calling Microsoft Graph requires a Graph access token rather than API A's token.

## 5. Microsoft Entra App Registrations: API and Client

Separating into **two app registrations** keeps trust boundaries clear.

### A. Registering the REST API

In an authorized tenant:

1. Open Microsoft Entra admin center → **App registrations**.
2. Create an app, e.g., `orders-api-dev`.
3. Note the API's **Application (client) ID** and **Directory (tenant) ID**. These are identifiers, not secrets.
4. Pick **Supported account types** (this lab uses **single tenant**).
5. Open **Expose an API** and set the **Application ID URI**, e.g., `api://<API_APP_ID>`.
6. Define delegated scopes such as `Orders.Read` and `Orders.Write`, specifying who can consent and clear descriptions.
7. For service-to-service calls, create **App roles** targeting applications, e.g., `Orders.Read.All` or `Jobs.Run`; verify values and allowed member types.
8. Configure the desired token version and claims in the app manifest/schema, especially when using the v2 issuer.
9. Configure owners, publisher details, enterprise app settings, and assignment policies.
10. Document expected audience, issuer tenant, scopes, roles, and owner.

**Scopes and roles are logical permissions you define**; creating their names does not automatically grant access to users or apps. Clients still need scope requests and consent, or app-role assignment/admin consent depending on the flow.

### B. Registering the Frontend / Consumer Client

1. Create a separate app registration, e.g., `orders-spa-dev`.
2. Choose the client type and redirect URI matching the platform.
3. For a SPA, use **authorization code + PKCE** with MSAL; never issue a client secret to browser JavaScript.
4. Under **API permissions**, add delegated permissions `Orders.Read`/`Orders.Write` exposed by the API.
5. Complete user/admin consent per tenant policy.
6. Configure the client with the specific tenant authority and full scope URI.
7. Ensure the frontend calls the API with an **access token**, never an ID token.

### C. Service Client

For a daemon app, grant and consent/assign the corresponding application permission or app role. Do not assume client credentials tokens contain `scp`; app-only tokens usually carry roles in `roles`. In some cases an app-only token may carry no roles if the API relies on ACLs; if your API requires roles, **reject tokens lacking roles** rather than treating absence as permission.

### Why Is There an Application ID URI?

Scope strings often look like `api://<API_APP_ID>/Orders.Read`, yet the access token's `aud` is not necessarily that full scope string. In many v2 access token setups, `aud` is the **API's client ID**; in some v1/custom API configurations, it may be the **Application ID URI**. Set expected audience according to the **actual token contract and API configuration** rather than using the full scope string as `aud`.

## 6. v1/v2 Access Tokens and Choosing the Issuer

Microsoft Entra supports **v1.0** and **v2.0** access token formats. The issued format depends largely on the **resource/API app registration** receiving the token, not solely on whether the client hits `/oauth2/v2.0/authorize`.

| Token format | Common issuer example | Condition |
|---|---|---|
| v2.0 | `https://login.microsoftonline.com/<TENANT_ID>/v2.0` | API configured to accept v2 access tokens |
| v1.0 | `https://sts.windows.net/<TENANT_ID>/` | API/resource configured for v1 token format |

This lab uses **v2, single tenant** with issuer `https://login.microsoftonline.com/<TENANT_ID>/v2.0`. If an actual token arrives with `ver=1.0`, its issuer and audience will differ from v2 expectations: **never disable issuer validation to "let it through."** Check `requestedAccessTokenVersion`/token format settings on the API app registration and acquire a matching token.

### Never Use `/common` as a Fixed Issuer for All Tokens

`/common` or `/organizations` are login authorities for multi-tenant scenarios where supported. Issued access tokens carry a **tenant-specific issuer**, so never blindly set a `/common` URL as the expected `iss`. Multi-tenant APIs require a trusted issuer resolver/allowlist per issuer and tenant rather than trusting every tenant with a valid signature.

## 7. Understanding Essential JWT Claims

A JWT has three Base64url-encoded parts: `header.payload.signature`. You can **decode** the first two parts to inspect them, but decoding **is not verification**.

**Illustrative payload (not a real token):**

~~~json
{
  "ver": "2.0",
  "iss": "https://login.microsoftonline.com/<TENANT_ID>/v2.0",
  "aud": "<API_APP_CLIENT_ID>",
  "tid": "<TENANT_ID>",
  "oid": "<USER_OBJECT_ID>",
  "sub": "<PAIRWISE_SUBJECT>",
  "azp": "<CLIENT_APP_ID>",
  "scp": "Orders.Read Orders.Write",
  "iat": 1795160000,
  "nbf": 1795160000,
  "exp": 1795163600
}
~~~

| Claim | Interpretation | Validation / usage |
|---|---|---|
| `iss` | Issuer | Matches trusted tenant/version issuer |
| `aud` | Audience | Must match the configured resource/API identifier |
| `exp` | Expiration | Reject expired tokens per clock skew policy |
| `nbf` | Not before | Reject tokens not yet valid |
| `iat` | Issued at | Useful for telemetry/policy, not authorization |
| `ver` | Token format version | Aligns issuer and claim mappings |
| `tid` | Tenant ID | Supports tenant allowlists and data partitioning |
| `oid` | Principal object ID in tenant | Primary identity key for many data queries |
| `sub` | Subject/pairwise identifier | Do not assume it equals email or `oid` |
| `scp` | Space-delimited delegated scopes | Mapped to `SCOPE_Orders.Read` |
| `roles` | Assigned app roles/permissions | Mapped to `ROLE_Jobs.Run` |
| `azp` | Authorized party / client app ID (typical in v2) | Client allowlist when policy requires |
| `appid` | Client app ID in some v1 tokens | Not guaranteed present in v2 |
| `groups` | Groups if emitted in token | Subject to size limits / group overage |

### Claims **Not** Suitable as Durable Authorization Keys

`name`, `preferred_username`, and `email` can change, be absent, or lack uniqueness guarantees. **Never use email as the primary authorization key** in multi-tenant systems. When user identity applies, use `(tid, oid)` per your identity contract alongside explicit business authorization logic.

### Never Trust Claims Before Verification

Anyone can build JSON `{"roles":["Admin"]}` and Base64url-encode it as a payload. Claims carry authority for policy decisions only after signature, issuer, audience, timestamps, and algorithms are verified against trusted keys.

## 8. The Request Protection Chain Must Be Complete

~~~mermaid
flowchart TD
  R["HTTP Authorization: Bearer token"] --> F{"Valid Bearer token format?"}
  F -->|No| E401["401"]
  F -->|Yes| S{"Signature / alg / trusted JWKS?"}
  S -->|No| E401
  S -->|Yes| I{"Valid iss + aud + exp/nbf?"}
  I -->|No| E401
  I -->|Yes| P{"Has required scope/role?"}
  P -->|No| E403["403"]
  P -->|Yes| O{"Valid tenant + record ownership?"}
  O -->|No| E403
  O -->|Yes| OK["200/201 with authorized data"]
~~~

For endpoints requiring layered checks, enforce:

1. Token is valid **for this specific API**.
2. Client/tenant is in the allowlist (if policy requires).
3. Principal holds the required scope or app role.
4. Principal is authorized for the specific resource ID.
5. DB queries filter by tenant/owner.
6. Returned fields are masked or filtered by role if required.
7. Writes/deletes enforce concurrency control, auditing, and approvals if required.

**Never stop at step 1.** A valid token carrying `Orders.Read` is not a license to read every customer's orders.

## 9. Bootstrapping a Spring Boot Resource Server

Examples target **Java 17+, Spring Boot 3.x**, and Spring Security 6 with Maven `spring-boot-starter-parent` or equivalent dependency management:

~~~xml
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
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
</dependencies>
~~~

Resource Server JWT validation requires Spring Security OAuth2/Jose modules; the **Spring Boot resource-server starter** pulls the aligned BOM dependencies. Never mix Spring Security 5 and 6. With WebFlux instead of MVC, security configuration APIs differ (`SecurityWebFilterChain`, `ServerHttpSecurity`).

### An API Resource Server Does Not Require Login Redirects

The backend handles HTTP API requests with access tokens; it **does not render a Microsoft login page** per request. Spring Security's `oauth2ResourceServer().jwt()` validates JWTs. Spring OAuth2 Client and login sessions apply only when **the application itself also acts as an OAuth client**.

## 10. Configuring Issuer and Audience

For a single-tenant setup and **v2** access tokens:

~~~yaml
# application.yml - illustrative config, no hard-coded secrets
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.microsoftonline.com/${ENTRA_TENANT_ID}/v2.0
          audiences:
            - ${ENTRA_API_AUDIENCE}

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Set environment variables in the runtime environment:

~~~text
ENTRA_TENANT_ID=<TENANT_GUID>
ENTRA_API_AUDIENCE=<EXPECTED_ACCESS_TOKEN_AUD_CLAIM>
~~~

**The property `spring.security.oauth2.resourceserver.jwt.audiences` is supported in modern compatible Spring Boot releases; verify against your exact BOM version.** If your version lacks this property, implement an **explicit audience validator** instead of skipping audience checks.

### Three Easily Confused Values

- **Tenant ID:** identifies the issuing tenant.
- **API Application (client) ID:** identifies the API app registration.
- **Application ID URI/scope:** `api://<API_APP_ID>/Orders.Read` is a client-requested scope, **not automatically the `aud` value**.

Confirm the expected audience from your resource/API token contract and a **validly issued token** in the lab; never accept arbitrary audiences simply because token formats vary.

### What Does Spring Do Under the Hood?

When properly configured, Spring Resource Server uses the issuer's OpenID Provider metadata/JWKS to verify signatures and standard token validators (issuer/timestamps). **Audience must be explicitly enforced via property or validator**—never assume `issuer-uri` alone restricts tokens to your API.

## 11. Deny-by-Default Spring SecurityFilterChain

Example configuration for the REST API:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter converter
    ) throws Exception {

        http
            .csrf(csrf -> csrf.disable()) // Only for bearer-only/stateless APIs; see CSRF section.
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_Orders.Read")
                .requestMatchers(HttpMethod.POST, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_Orders.Write")
                .requestMatchers("/api/internal/jobs/**")
                    .hasAuthority("ROLE_Jobs.Run")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(converter))
            );

        return http.build();
    }
}
~~~

### Why Declare Rules This Way?

- `STATELESS`: never relies on HTTP sessions to remember users.
- `GET /api/orders/**`: requires delegated `Orders.Read`.
- `POST /api/orders/**`: requires delegated `Orders.Write`.
- `/api/internal/jobs/**`: requires app role `Jobs.Run`.
- `anyRequest().denyAll()`: rejects any undeclared route/method, preventing newly added APIs from accidentally opening up to any authenticated caller.
- `actuator/health`: exposes only the minimal health endpoint while keeping other actuator endpoints protected.
- `oauth2ResourceServer(jwt)`: validates Bearer tokens rather than trusting headers.
- `@EnableMethodSecurity`: enables `@PreAuthorize` on services and controllers.

**Caution:** path/method rules depend on actual routing. When adding `PATCH`, `PUT`, `DELETE`, or new endpoints, declare explicit policies and security tests; defaulting to `denyAll()` avoids missing authorization gaps. Whether unmapped endpoints return 404 or 403 in tests also depends on Spring MVC routing and filter ordering; never treat path rules as a substitute for data-layer ownership checks.

## 12. Converting `scp` and `roles` into Spring Authorities

Spring Security Resource Server recognizes `scope` or `scp` by default and prefixes them with `SCOPE_`. For explicit handling of Entra `roles` alongside custom policies, define a converter:

~~~java
package com.example.orders.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthorityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
        scopes.setAuthoritiesClaimName("scp");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter((Jwt jwt) -> {
            List<GrantedAuthority> result = new ArrayList<>();

            Collection<GrantedAuthority> scopeAuthorities = scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    result.add(new SimpleGrantedAuthority("ROLE_" + role));
                }
            }
            return result;
        });
        return converter;
    }
}
~~~

Mapping example:

~~~text
JWT: "scp": "Orders.Read Orders.Write"
  -> SCOPE_Orders.Read
  -> SCOPE_Orders.Write

JWT: "roles": ["Jobs.Run", "Orders.Read.All"]
  -> ROLE_Jobs.Run
  -> ROLE_Orders.Read.All
~~~

### Scopes and Roles Are Not Interchangeable

- **Delegated `scp`**: permissions in a user/caller context; you must still check **which records the user owns**.
- **Application `roles`**: commonly used service-to-service with no user context.
- **Roles can also appear in a user token** when app roles are assigned to users/groups, so never assume `roles` always means app-only and skip other checks.
- Daemon endpoints may require **an app role plus an authorized client/service principal allowlist**, not merely any token carrying a matching role name.

### Do Not Misuse `hasRole("...")` When Prefixes Differ

Spring `hasRole("Admin")` looks for authority `ROLE_Admin`. If `scp` is mapped as `SCOPE_Orders.Read`, check `hasAuthority("SCOPE_Orders.Read")`. Keep naming consistent across app registrations, code, and tests.

## 13. API Controller: Delegated Scopes and Caller Identity

Example endpoint restricted to user-delegated tokens carrying `Orders.Read`:

~~~java
package com.example.orders.api;

import java.util.List;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    private final OrderReader orderReader;

    public OrdersController(OrderReader orderReader) {
        this.orderReader = orderReader;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_Orders.Read')")
    public List<OrderDto> myOrders(@AuthenticationPrincipal Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tid");
        String objectId = jwt.getClaimAsString("oid");

        if (tenantId == null || objectId == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Required principal claims missing");
        }

        return orderReader.findForOwner(tenantId, objectId);
    }

    // OrderReader and OrderDto are business abstractions
    // implemented by a repository/service in the application.
}
~~~

**Never trust `tenantId` or `userId` passed by the client in the URL to determine ownership.** Services query using `(tid, oid)` from the verified JWT and database ownership filters.

Example business interface:

~~~java
public interface OrderReader {
    java.util.List<OrderDto> findForOwner(
        String tenantId, String userObjectId);
}
~~~

A sound SQL query might look like:

~~~sql
SELECT OrderId, Status, TotalMinor
FROM dbo.Orders
WHERE TenantId = :tenantId
  AND OwnerObjectId = :userObjectId;
~~~

`:tenantId` and `:userObjectId` are **parameters** bound via prepared statements or the data-access framework; **never** concatenate raw claims into SQL strings. The repository layer must enforce tenancy/ownership even if the controller already checks it.

## 14. Protect by Resource and Tenant, Not Just Endpoint

Suppose `Orders.Read` is valid, yet User A calls `GET /api/orders/999` where order 999 belongs to User B. The token is valid, but if the server calls `findById(999)` and returns the record, that is **Broken Object Level Authorization (BOLA/IDOR)**.

### Wrong

~~~java
// Pseudocode anti-pattern:
Order order = repository.findById(requestedId);
return order;
~~~

### Structurally Sound

~~~java
// Pseudocode:
Order order = repository
    .findByIdAndTenantIdAndOwnerObjectId(
        requestedId,
        validatedJwtTenantId,
        validatedJwtObjectId
    )
    .orElseThrow(NotFoundException::new);
~~~

You may return **404** instead of **403** for unauthorized resources if policy avoids leaking ID existence; stay consistent and never mask authentication failures.

### Multi-Tenant Key

The `(tid, oid)` pair usually uniquely identifies an Entra user within a tenant. `oid` alone is insufficient as an identity key across multiple tenants. If B2B guest accounts are allowed, a guest may have a different `oid` in the resource tenant; define canonical business identities and mappings per policy.

### Scopes vs. Record-Level Permissions

`SCOPE_Orders.Read` answers "does the client/user hold delegated permission to read the Orders API"; it **does not answer** "is this user permitted to view another tenant's order." Database filters, policy services, or authorization evaluators remain mandatory.

## 15. Protecting Service-to-Service Calls with Application Roles

A job running on Azure Functions/AKS calls internal endpoint `POST /api/internal/jobs/reconcile`. It uses an **application identity** and an access token carrying appropriate `roles`, with no delegated user context.

Example principal claims:

~~~json
{
  "ver": "2.0",
  "iss": "https://login.microsoftonline.com/<TENANT_ID>/v2.0",
  "aud": "<API_APP_CLIENT_ID>",
  "tid": "<TENANT_ID>",
  "azp": "<DAEMON_APP_CLIENT_ID>",
  "roles": ["Jobs.Run"],
  "exp": 1795163600
}
~~~

**This is an illustrative payload, not a signed access token.**

### Policy Rules

- Accept only authorized caller clients (verify `azp`/`appid` per token format or another verified service principal identity).
- Require `ROLE_Jobs.Run`.
- Do not let service-to-service endpoints fall back to user scopes without a clear reason.
- Scope write access by tenant, workspace, or resource.
- Audit by client identity, operation ID, and resource.
- Enforce idempotency keys and rate limits on mutating operations.
- Never let a daemon app with `Jobs.Run` administer arbitrary Azure resources.
- If policy demands **app-only tokens exclusively**, add explicit checks for application-token claims emitted by Entra (such as `idtyp=app` when configured and supported) alongside app-role assignments and client allowlists; the mere absence of `scp` does not prove a token is app-only.

### App-Only Token Does Not Make Every Daemon Trusted

A properly signed token carrying a different role or wrong issuer/audience must still be rejected. If an application assignment/consent is revoked before an existing token expires, consider token lifetime and revocation policies.

## 16. 401 and 403: Exact HTTP Semantics

| Scenario | Typical status | Explanation |
|---|---|---|
| No Bearer token on a protected endpoint | **401** | Unauthenticated |
| Tampered token signature | **401** | Invalid authentication token |
| Expired or not-yet-valid token | **401** | Invalid token lifetime |
| Wrong issuer or audience | **401** | Token not intended for a trusted API |
| Valid token missing `Orders.Read` | **403** | Authenticated identity lacks permission |
| User has scope, accesses someone else's record | **403/404** per policy | Object-level authorization |
| Rate limit/quota exceeded | **429** | Not an authentication error |
| Non-security API failure | **5xx** | Never turn every error into 401 |

In an OAuth2 Bearer Resource Server, `WWW-Authenticate: Bearer ...` conveys standard error metadata. Never leak claims, tokens, or internal key details in error bodies.

Safe error body example:

~~~json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Insufficient permission",
  "requestId": "req-illustration-001"
}
~~~

Spring Security provides default authentication entry-point and access-denied handling; if customizing error bodies, **never return 200 for blocked requests** and preserve Bearer challenge semantics where appropriate.

## 17. Custom Audience Validator When Boot Property Is Unsupported

If a project runs a Spring Boot version lacking the `jwt.audiences` property, **never remove audience validation**. Configure a `JwtDecoder` with issuer and audience validators.

Java example using `NimbusJwtDecoder`. The JWKS URL must come from **the exact tenant/issuer's OpenID metadata**—never trust a `jku` URL declared inside a JWT header:

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;

@Configuration
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer-uri}") String issuer,
            @Value("${app.security.audience}") String audience,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> correctAudience = token ->
            token.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Access token audience is not this API",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, correctAudience
            )
        );
        return decoder;
    }
}
~~~

Configuration properties:

~~~yaml
app:
  security:
    issuer-uri: https://login.microsoftonline.com/${ENTRA_TENANT_ID}/v2.0
    audience: ${ENTRA_API_AUDIENCE}
    jwk-set-uri: https://login.microsoftonline.com/${ENTRA_TENANT_ID}/discovery/v2.0/keys
~~~

### Choose **One** Consistent Strategy

- Use Spring Boot `issuer-uri` + `audiences` properties **if supported by your framework version**; or
- Declare a custom `JwtDecoder` bean with explicit issuer/time/audience validators and trusted JWKS.

Avoid accidentally creating two overlapping configurations and assuming default properties still apply once a custom decoder replaces auto-configuration. With a custom decoder, verify all validators, JWS algorithms, key rotation, time skew, and supported issuer metadata.

## 18. JWT Signatures and Key Rotation

Entra ID signs JWTs with a private signing key; the API verifies them with the **public key** from the JWKS endpoint advertised in the issuer's OIDC metadata.

### Verification Steps

1. Receive Bearer JWT.
2. Check structure and JWS algorithm against trusted decoder config.
3. Locate the signing key by `kid` in the **trusted issuer's** JWKS metadata.
4. Verify the cryptographic signature.
5. Validate `iss`, `aud`, `exp`, `nbf`, and other policy claims.
6. Convert authorities and enforce access control.

### Key Rollover

Microsoft Entra periodically introduces new signing keys. The resource server must use an SDK/library that refreshes JWKS per policy. Avoid:

- Permanently hard-coding **a single** PEM public key.
- Fetching arbitrary JWK URLs read from a caller's JWT header.
- Disabling signature validation when a `kid` is missing from cache.
- Continuously restarting every pod to work around refresh failures without checking network/metadata.
- Logging raw JWTs to debug key mismatches.

### Network Impact on Authentication

If Azure Container Apps/AKS restricts egress and a firewall blocks OpenID metadata/JWKS, the resource server may fail at startup or key refresh. Permit outbound access to the proper Entra endpoints per security policy, verify proxy/TLS trust and health checks, and **never fall back to accepting unsigned tokens**.

## 19. Clock Skew, Expiration, Revocation, and Sessions

Access tokens have finite lifetimes, though **never assume they are always 60 minutes**. Lifetimes vary by policy and token type. JWT validators must enforce `exp`, `nbf`, and clock skew per library/configuration.

### Clock Synchronization

- Synchronize system clocks across pods and VMs.
- Clock drift can reject newly issued tokens as "not yet valid" or wrongly accept expired tokens.
- Keep clock skew small and standard; never widen skew to hours to "fix" clock errors.

### Token Revocation

An offline-verified JWT can remain valid until `exp` even if permissions or sessions change, unless additional policies or service capabilities are implemented. **Never promise immediate revocation of all tokens simply because a user logs out or is disabled.**

For high-risk operations:

- Enforce shorter lifetimes via supported identity policies.
- Re-check user/tenant/entitlement status on the backend where needed.
- Evaluate Conditional Access / Continuous Access Evaluation where supported by the resource and client.
- Maintain auditing, anomaly detection, token-theft response, and least privilege.
- Never use a refresh token as a Bearer token for an API.

### Where Do Refresh Tokens Live?

Refresh tokens are managed by the OAuth client/MSAL according to client type and security policy; the Resource Server **does not need refresh tokens** simply to authenticate API requests.

## 20. CORS, CSRF, and Browser Security

Three frequently confused concepts:

- **CORS:** tells the browser which origins' JavaScript may read responses from the API. CORS **does not replace authorization** and does not block non-browser callers.
- **CSRF:** exploits credentials automatically attached by the browser (typically cookies/sessions).
- **Bearer token in the Authorization header:** attached explicitly by frontend code; for stateless Bearer-only APIs with no auth cookies, CSRF can be disabled by design. However, if sessions/cookies or an OAuth login flow coexist in the same app, re-evaluate CSRF carefully.

### Properly Scoped CORS Policy

~~~java
// Example fragment; integrate inside an appropriate Spring Security configuration.
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

If the API needs CORS, enable `http.cors(...)` in `SecurityFilterChain` for your Spring Security version and register this bean. This snippet is a fragment, not a standalone Java class.

**Never configure `allowedOrigins("*")` with credentials "for convenience."** Even requests from an allowed origin **must** carry a valid access token with the right scope/role.

## 21. Acquiring Tokens Safely from the Frontend

The frontend should use an MSAL/OIDC library suited to its application type:

~~~text
Frontend public client registration:
  authority: tenant-specific trusted authority
  clientId: frontend client ID
  redirectUri: registered URI
  requested scopes:
    api://<API_APP_ID>/Orders.Read

Flow:
  redirect/login with authorization code + PKCE
  acquireTokenSilent when supported
  interactive authorization if required
  call API with Authorization: Bearer <access_token>
~~~

**Never place access tokens in query strings, referrers, or casual `localStorage`** when XSS or log-leakage risks exist. Evaluate caching/storage strategies against library guidance and your threat model; every SPA must still defend against XSS, enforce CSP, patch dependency vulnerabilities, and guard against malicious browser extensions.

### Do Not Use a Graph Token to Call Custom APIs

A token whose audience is **Microsoft Graph** belongs to Graph. Even if the user holds `User.Read` on Graph, the Orders API backend must **reject** that token due to the wrong `aud`. To call Orders API, the client must request Orders API scopes.

### Client ID Is Not a Secret

App client IDs and tenant IDs are identifiers. They must be accurate, but knowing them proves nothing about caller trust. Confidential clients require credentials/identity and app consent per flow.

## 22. Service-to-Service with Managed Identity

A service running on Azure can use **managed identity** or workload identity to obtain tokens without storing long-lived client secrets, provided the resource provider/API and permissions are properly configured.

### Logical Steps

1. Enable managed identity/workload identity on the compute/service.
2. Identify the **service principal identity** representing the service.
3. Assign the API's **app role** to that identity via the appropriate Entra/Graph process.
4. The client requests a token with resource scope `api://<API_APP_ID>/.default` per credential/provider support.
5. The API validates issuer/audience and requires `ROLE_Jobs.Run`.
6. Beyond roles, verify caller-identity allowlists and resource-level authorization where needed.

Java example using **Azure Identity** (for a backend worker, never in a frontend):

~~~java
import com.azure.core.credential.AccessToken;
import com.azure.core.credential.TokenRequestContext;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.time.Duration;

public final class TokenForWorker {
    public static AccessToken acquire(String apiAppId) {
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        TokenRequestContext context = new TokenRequestContext()
            .addScopes("api://" + apiAppId + "/.default");

        AccessToken token = credential.getToken(context)
            .block(Duration.ofSeconds(20));

        if (token == null) {
            throw new IllegalStateException("Could not obtain access token");
        }
        return token;
    }
}
~~~

**Limitations:** this snippet calls `block()`, making it suitable only for **blocking worker** threads—never place it on a Reactor event loop. Production code should **reuse credentials**, use proper SDK/client auth integrations, handle 401/403, and rely on library caching/expiry. Never call `System.out.println(token.getToken())`. Identity/app-role assignments and custom API compatibility with managed identity must be verified before running.

To run this example, add **`com.azure:azure-identity`** and manage compatible versions via an approved **Azure SDK BOM** or dependency management; the Spring Security Resource Server Maven starters shown earlier do not pull in the Azure Identity SDK automatically. For confidential clients needing certificates or secrets, prefer **managed identity/federation/certificates** per your threat model; if secrets remain necessary, keep them in **Azure Key Vault** with least-privilege read access, track rotation, and never commit them to Git or print tokens in logs.

## 23. On-Behalf-Of (OBO) When an API Calls Another Service

Suppose the frontend sends a token with `aud=Orders API` and delegated `Orders.Read`. Orders API needs to query user information from **Microsoft Graph**:

~~~mermaid
sequenceDiagram
  participant C as Frontend
  participant A as Orders API
  participant E as Entra ID
  participant G as Microsoft Graph
  C->>A: Bearer token aud=Orders API
  A->>A: Validate and authorize
  A->>E: OBO exchange with delegated Graph scopes
  E-->>A: New access token aud=Graph
  A->>G: Authorization Bearer Graph token
  G-->>A: Graph response
  A-->>C: Filtered API response
~~~

Never forward the original token directly to Graph. OBO requires client configuration, delegated permissions/consent, and confidential client authentication; use MSAL Java or a supported library rather than hand-crafting assertion exchanges.

### OBO vs. Managed Identity

- **OBO:** calls downstream **on the user's behalf** with delegated permissions.
- **Managed identity:** service calls downstream **under application identity**, with no delegated user context.

Choose per business need: reading "the current user's" data generally requires user delegation and permission checks; userless system jobs can use managed identity and app roles.

## 24. Client Allowlists and Tenant Restrictions

Some APIs permit only specific frontend or service clients even when a token carries a valid scope.

- In v2 access tokens, the `azp` claim can indicate the authorized client app.
- In v1 access tokens, `appid` may appear instead.
- Presence and values must be interpreted per token/version contract.
- Perform **issuer/audience/signature verification first**, then enforce client claims in policy.
- A **client allowlist** is defense-in-depth, not a replacement for scopes, roles, or record-level auth.
- Never rely on a self-declared `X-Client-Id` HTTP header to prove client identity.

### Multi-Tenant APIs

If supporting multiple Entra tenants:

1. Maintain an explicit allowlist of tenants or a tenant onboarding/approval workflow.
2. Configure JWT validation resolution against **trusted issuers** rather than blindly accepting any caller's tenant.
3. Validate `iss` and `tid` for each tenant.
4. Keep audience scoped to the registered API with proper permissions.
5. Partition data by tenant and verify ownership.
6. Account for B2B guests and home vs. resource tenant contexts.
7. Add tests for issuer confusion and cross-tenant replay.

**Never use a naive `JwtDecoder` that checks only a shared signing-key endpoint while skipping tenant issuer checks.** Multi-tenant validation requires deliberate design—never simply swap a single-tenant issuer to `/common` for everything.

## 25. App Roles, Groups, and Group Overage

Microsoft Entra can emit a `groups` claim in certain configurations, yet JWTs have size limits. When a user belongs to many groups, the token may omit the full list of group IDs and emit a **group overage indicator** (such as `hasgroups` or claims mapping).

### Risk

If the API checks only the `groups` array and treats its absence as belonging to no groups, users in many groups get falsely denied; worse, if code **defaults to allow** when `groups` is missing, it opens a vulnerability.

### Recommendations

- For API authorization, prefer governed **app roles** to avoid relying on large group lists inside tokens.
- If group-based policies are required, handle overage per documentation using authorized Graph queries and a caching policy.
- Never call Graph with an Orders API access token whose audience is not Graph.
- Never assume every token contains email, preferred username, groups, or roles.
- Document the source of truth for group membership and propagation lag when permissions change.

## 26. Security Testing: Do Not Test Only HTTP 200

A minimal test matrix:

| Test | Token / condition | Expected outcome |
|---|---|---|
| No Authorization header | No token | 401 |
| Malformed Bearer header | Arbitrary string | 401 |
| Invalid signature | Tampered JWT payload | 401 |
| Expired | Past `exp` | 401 |
| Not yet valid | Future `nbf` | 401 |
| Wrong tenant issuer | Untrusted `iss` | 401 |
| Graph token | `aud` is Graph | 401 |
| Frontend ID token | `aud` is frontend client | 401 |
| Delegated `Orders.Read` only | GET Orders | Allowed if matching owner |
| Delegated `Orders.Read` only | POST Orders | 403 |
| App-only `Jobs.Run` | Internal job route | Allowed when client/tenant policy matches |
| App-only missing role | Internal job route | 403 |
| User A reads Order B | Valid scope, wrong owner | 403/404 per policy |
| Tenant A accesses Tenant B | Valid JWT, wrong data boundary | Denied |
| Health endpoint | No token | Minimal health info only |
| Unknown route | Valid token, unmapped route | 404/403 per routing/policy |

### Direct Testing with MockMvc

With `spring-security-test`, mock JWTs can test **authorization**:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getOrdersRequiresReadAuthority() throws Exception {
        mvc.perform(get("/api/orders").with(jwt()
                .jwt(token -> token
                    .claim("tid", "tenant-test")
                    .claim("oid", "user-test"))
                .authorities(new SimpleGrantedAuthority("SCOPE_Orders.Read"))))
            .andExpect(status().isOk());
    }

    @Test
    void getOrdersWithoutRequiredAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/orders").with(jwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_Other.Read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

**This is an illustrative test:** you must provide an `OrderReader` bean/repository (mock or test database) and the `spring-security-test` dependency. By default, MockMvc's `jwt()` **bypasses signature verification and the real `JwtDecoder`**; manually injecting authorities also **bypasses the production converter**. Therefore, **never treat the test above as proof** that issuer, audience, and signature verification work.

### Integration Tests Must Exercise the Real JwtDecoder

Use a local test issuer/JWKS server with **controlled local signing keys**, configure matching audience/issuer settings, and send validly and invalidly signed JWTs to verify 401/403. Never extract Entra's private signing keys or try to forge production Azure tokens. Test boundaries:

- Wrong `iss`, `aud`, `exp`, `nbf`, and unsupported algorithms.
- Key ID not present in trusted JWKS.
- Scope/role converters and method security.
- v1-format tokens rejected when the API requires v2.
- Tenant/owner filters in repositories.
- Fail closed when JWKS is unavailable with no valid cached keys.

## 27. Manual Lab Testing with cURL / Postman

Once you have a **valid access token for Orders API** acquired by an authorized client via MSAL/OAuth flow:

~~~bash
API_URL="https://orders-api.example.com"
# ACCESS_TOKEN: keep in a secure environment variable; never echo or log to shell history.
curl --fail-with-body \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/json" \
  "${API_URL}/api/orders"
~~~

**Never** place tokens into URLs, request logs, or screenshots shared outside authorized channels. Older `curl` versions may lack `--fail-with-body`; use `-i` or another safe status-checking option.

### Acquiring a Test Token

- User client: MSAL + Authorization Code PKCE or Postman OAuth2 flow with registered redirect URI and API scope.
- App-only client: confidential client flow using `.default` with approved app role assignment.
- Azure workload: managed/workload identity with proper configuration and permissions.

If you only have an ID token or Graph access token, **do not force the API to accept it**. Fix token acquisition in client registration/permissions rather than disabling audience validation on the API.

### Test Record

~~~text
Test case: delegated user with Orders.Read
Issuer tenant: <TENANT_ID>
Expected audience: <API_AUDIENCE>
Requested scope: api://<API_APP_ID>/Orders.Read
HTTP result: 200
Returned rows: only own tenant/owner
Token value: NEVER LOGGED
RequestId: lab-test-001
~~~

## 28. Do API Management and Gateways Replace the Resource Server?

Azure API Management (APIM), Application Gateway, or ingress controllers can handle **TLS termination, gateway authentication, rate limiting, logging, routing, and security policies**. APIM can also enforce JWT validation policies for issuer/audience and claims where supported.

Yet trust boundaries must still be defined:

- If the backend is **directly reachable**, validating tokens only at APIM can be bypassed.
- If the gateway forwards identity headers, the backend must trust them only from a **protected and authenticated** gateway to prevent header spoofing.
- If the backend also acts as a resource server, it can re-verify tokens for defense-in-depth.
- Gateway JWT validation does not check `orderId` ownership in the database.
- Rate-limiting policies do not replace API scopes or roles.

### Reference Architecture

~~~mermaid
flowchart LR
  B["Browser / Mobile"] --> APIM["APIM: TLS, JWT, rate limit"]
  APIM --> API["Spring Boot Resource Server"]
  API --> AUTH["Scope/role + tenant/owner checks"]
  AUTH --> DB["Azure SQL / Cosmos DB"]
  API --> MON["Azure Monitor / App Insights"]
  APIM --> MON
~~~

Depending on requirements, you can combine gateway validation with independent backend JWT verification; neither requires calling Entra on every runtime request once JWKS keys are cached properly.

## 29. Deploying the Spring Boot Resource Server on Azure

Common hosting options:

- **Azure App Service:** runs the Java app with configured runtime/plan, app settings, and networking.
- **Azure Container Apps:** runs containers with managed identity, ingress, secrets, and revisions.
- **AKS:** pods, Kubernetes services/ingress, workload identity, and network policies.

Regardless of host:

1. Supply `ENTRA_TENANT_ID` and `ENTRA_API_AUDIENCE` via external configuration.
2. Enforce HTTPS/TLS on public endpoints and gateways.
3. Permit outbound access to Entra OIDC metadata/JWKS endpoints.
4. Configure ingress/public/private access per policy.
5. Use private networking/endpoints for Storage/SQL when accessing internal data.
6. Attach managed/workload identity for **downstream Azure resources**—never use it to bypass client Bearer token checks.
7. Never store tokens/secrets in container images, Dockerfiles, public ConfigMaps, or Git.
8. Configure appropriate liveness/readiness probes and limit exposed health details.
9. Configure autoscaling, rate limiting, and quotas appropriately.
10. Set up logging, tracing, budgets, and runbooks for identity-provider/JWKS outages.

### App Service Easy Auth Case

Azure App Service Authentication/Authorization ("Easy Auth") can handle authentication at the platform layer, but if the app already uses Spring Security Resource Server, clearly design **where tokens are validated, which audiences are accepted, and how caller identity traverses the proxy**. Never assume Easy Auth and Spring Security automatically align permissions when configured separately.

## 30. Observability and Azure Monitor

A secure API must track not only latency, but also rejection reasons.

| Metric/log | Meaning |
|---|---|
| Request count by route/method/status | 401/403/429/5xx and overall traffic |
| Authentication failures by category | Missing token, bad signature, wrong issuer/audience, expired |
| Authorization denials | Missing scope/role, tenant/owner mismatch |
| OIDC/JWKS refresh failures | Issues fetching or trusting signing keys |
| Spring Security filter latency | AuthN/AuthZ processing cost |
| Downstream DB latency/403 | Data or identity issues |
| Client token acquisition failures | Consent/credential/managed identity errors |
| Suspicious bursts | Token replay, brute force, unexpected client identities |
| JWT decoder/cache behavior | Key rotation and availability |
| p95/p99 latency, 5xx, availability | SLO/UX |
| App/container/ingress networking | TLS, proxy, DNS, egress |
| Audit events | Role/permission/app registration changes |

### Safe Logging

~~~json
{
  "timeUtc": "2026-11-20T12:00:00Z",
  "requestId": "req-example-001",
  "route": "GET /api/orders",
  "status": 403,
  "reasonCategory": "missing_scope",
  "tenantKey": "tenant-hash",
  "clientKey": "client-hash",
  "latencyMs": 12
}
~~~

Never log raw JWTs/access tokens, `Authorization` headers, refresh tokens, signatures, full claims containing PII, or secrets. `oid`/`tid` are identifiers governed by privacy/log access policies; hash or pseudonymize them where appropriate.

### Actionable Alerts

- Rising 401/403 rates after deployments or app registration changes.
- Simultaneous 401 spikes caused by key-refresh or issuer mismatches.
- Surging 403s from revoked role assignments or consent.
- Access requests from tenant/client IDs outside the allowlist.
- Rising API 5xx/p95 after enabling network restrictions.
- Anomalous role/app permission changes in Entra audit logs.
- Cross-tenant DB queries or owner mismatches if security audit events exist.
- Spiking log costs from recording oversized payloads on every denial.

**Do not turn every 401 into a PagerDuty incident**: expired tokens or unauthorized user attempts can be normal. Alert on rates, baselines, affected tenants, and user impact.

## 31. Symptom-Based Troubleshooting

| Symptom | Possible cause | Investigation step |
|---|---|---|
| 401 despite frontend login | Sent ID token instead of access token | Inspect token type/`aud` in lab |
| 401 with Graph token | `aud` is not the API | Have client request the right API scope |
| 401 issuer mismatch | v1/v2 mismatch or wrong tenant | Check `iss`, `ver`, tenant/API registration |
| 401 after key rotation | JWKS cache/egress/metadata issue | Check JWKS refresh, DNS/proxy/TLS |
| 401 token expired | `exp` passed or local clock drift | Sync clocks, MSAL silent acquisition |
| 401 invalid signature | Tampered token or untrusted key | Never disable signature validation |
| 403 missing authority | Missing scope/role or wrong converter | Check `scp`, `roles`, `SCOPE_`/`ROLE_` |
| 403 app-only despite token | Missing app role assignment/admin consent | Check Entra Enterprise app roles/claims |
| 403 user has scope, sees no orders | Owner/tenant filtering | Check repository filters and user data |
| User A reads User B's order | BOLA/IDOR | Enforce ownership checks at database layer |
| CORS preflight fails | Origin/method/headers mismatch | Check CORS + Spring filter ordering |
| 403 on browser POST | CSRF/session cookie mixed with Bearer | Review session/security architecture |
| Works locally, fails on Azure | JWKS egress DNS/proxy/issuer config | Check container/VM network and env vars |
| 403 downstream Azure SQL/Storage | API token differs from Azure data-plane role | Check managed identity/RBAC/ACLs |
| Client credentials token lacks `scp` | App-only flows use `roles` | Check endpoint policy/service registration |
| User in many groups lacks `groups` claim | Group overage | Use app roles or authorized Graph lookup |
| Multi-tenant user rejected | Tenant allowlist/issuer resolver | Verify onboarding and guest identity rules |
| 401 on all requests post-deploy | Wrong audience env var | Redeploy correct setting, add regression test |

### Never Fix Errors By

- Disabling issuer or audience checks.
- Accepting Graph tokens or ID tokens.
- Setting `permitAll()` temporarily on an API and forgetting to revert it.
- Granting every user the Admin role.
- Using `TrustAll` SSL or disabling TLS verification.
- Logging tokens to ask someone else to debug.
- Ignoring BOLA because the frontend "hides" other users' orders.

## 32. Threat Modeling: Common Security Flaws

### Token Substitution

An attacker presents a **validly signed token issued for a different resource**. Defense: **audience validation**.

### Issuer / Tenant Confusion

A token arrives from an untrusted tenant. Defense: exact trusted issuer(s), tenant allowlists, and onboarding policies; never trust `tid` from an unverified token.

### Overbroad Authorization

A user only needs to view their own orders, yet the API treats `SCOPE_Orders.Read` as permission to read all orders. Defense: ownership and business permissions in services/repositories.

### Scope-Role Confusion

An API defines an app role for a daemon yet guards the route with `authenticated()` or accepts user roles by mistake. Defense: endpoint-specific scopes/app roles and principal-type/caller policies.

### Token Leakage

Tokens appear in query strings, local logs, client telemetry, or crash dumps. Defense: TLS, redaction, secure storage, short lifetimes, and auditing.

### Algorithm / Key Confusion

Custom JWT verifiers accept `alg=none` or attacker-chosen JWK URLs. Defense: trusted Spring Security/Nimbus JWT decoder configuration; never roll custom crypto.

### Replay

A stolen Bearer token is replayed before expiration. Defense: token protection, TLS, device/Conditional Access controls where supported, rate/anomaly detection, and risk-based authorization; standard Bearer JWTs lack proof-of-possession.

### Consent / Permission Misconfiguration

Overly broad admin-consented application permissions or wrong app-role assignments. Defense: review API permissions, owners, approval workflows, and least privilege.

### Open Redirect / CORS Misconfiguration

Overly broad client redirect URIs, frontend XSS, or wildcard CORS `"*"`. Defense: exact redirects, PKCE, CSP, input validation, and strict CORS allowlists.

## 33. Cost and Operations

JWT validation can execute locally without calling Entra on every HTTP request, yet total cost still includes:

- Spring Boot compute on App Service/Container Apps/AKS.
- API Management/Application Gateway/WAF if used.
- Network egress, proxies, and private networking.
- Database/Storage queries for authorized callers.
- Azure Monitor/Application Insights/Log Analytics ingestion and retention.
- CI/CD security testing, scanning, and certificate/identity operations.
- Extra cost from retries, token acquisition failures, 401/403 floods, or traffic abuse.
- Licensing/Entra governance features depending on organizational plans.

### Optimize Without Trading Off Security

- Use local resource-server JWT validation/JWKS caching instead of per-request introspection when appropriate.
- Reuse HTTP clients and credentials for downstream calls.
- Protect APIs with ingress/rate limits, separating auth errors from backend overload.
- Log aggregated 401/403 metrics by route and reason category without raw claims.
- Keep public health endpoints minimal and protect detailed diagnostics.
- Set budgets and cost tags per environment.
- Never disable JWT checks to shave latency.
- Benchmark p95 in staging prior to rollout.

## 34. Case Study: Orders API and Reconciliation Worker

### Context

An enterprise runs a Vue/React frontend, a Spring Boot REST API on Azure Container Apps, Azure SQL storing Orders, and a scheduled Azure Function for reconciliation. Requirements:

- Users can view only their own orders.
- Users can modify orders only with `Orders.Write` and matching business rules.
- The reconciliation daemon calls an internal endpoint without impersonating a user.
- Microsoft Graph tokens must be rejected by Orders API.
- Every request carries audit metadata without logging tokens or PII.
- The API serves multiple onboarded tenants while rejecting arbitrary tenants.

### Design

~~~mermaid
flowchart LR
  SPA["Frontend + MSAL PKCE"] --> ENTRA["Microsoft Entra ID"]
  ENTRA -->|Access token aud=Orders API| SPA
  SPA --> API["Spring Boot Resource Server"]
  FUNC["Function / Managed Identity"] -->|App-only token + Jobs.Run| API
  API --> V["JWT verify: signature/iss/aud/time"]
  V --> P["SCOPE_/ROLE_ + tenant/owner policy"]
  P --> SQL["Azure SQL: TenantId + OwnerObjectId"]
  API --> OBS["Azure Monitor + App Insights"]
~~~

### Specific Policies

- Frontend requests `api://<API_APP_ID>/Orders.Read`; POST requires `Orders.Write`.
- API enforces exact v2 issuer and expected audience.
- Controller extracts `tid` and `oid` from the verified `Jwt`; service queries `TenantId` and `OwnerObjectId`.
- Function uses a managed identity assigned the `Jobs.Run` app role.
- Internal endpoint requires `ROLE_Jobs.Run` and an authorized caller.
- APIM/ingress enforces TLS and rate limits while the backend enforces authorization.
- Health endpoint is minimally public; all other debug/actuator endpoints are protected.
- Metrics track route, status, reason category, and pseudonymized identities.

### Failure Drills

1. Frontend accidentally sends an ID token: API returns 401 for wrong audience.
2. Daemon runs before app-role assignment: API returns 403.
3. `Orders.Read` token calls POST: API returns 403.
4. User A alters the URL to User B's order: service returns 404/403.
5. API pod cannot reach JWKS during signing-key rotation: auth fails safely, egress/JWKS alert fires, signature checks remain **enabled**.
6. Overbroad application permission granted accidentally: security review revokes it, inspects still-valid tokens, and audits calls.

## 35. Hands-On Exercise: Protecting a Spring Boot REST API

> **Safety:** work only in approved lab Entra tenants, app registrations, and Azure resources. Altering scopes, roles, or consent on production apps can break downstream consumers. Never include real tokens in Markdown notes, repos, issue trackers, or logs.

### Part A — Entra Registration

1. Confirm your lab tenant and permissions to create app registrations.
2. Create `orders-api-dev` and record the API app client ID and tenant ID.
3. Expose the API with an appropriate Application ID URI.
4. Create delegated scopes `Orders.Read` and `Orders.Write`.
5. Create app role `Jobs.Run` for application clients.
6. Create `orders-spa-dev` with matching redirect URI/PKCE settings.
7. Assign delegated API permissions and grant consent per policy.
8. If permitted in the lab, create a service identity/daemon with the app role and permissions.
9. Confirm the API accepts v2 access tokens and the expected issuer.
10. Document the expected audience per the resource token contract.

### Part B — Spring Boot

1. Create a Java 17+ project with web, security, oauth2-resource-server, and actuator starters.
2. Configure `issuer-uri` and `audiences` via environment variables.
3. Add `SecurityFilterChain` with deny-by-default rules for GET, POST, and internal jobs.
4. Add the `scp`/`roles` authorities converter.
5. Enable `@EnableMethodSecurity` and `@PreAuthorize`.
6. Implement the controller querying data by `tid`/`oid` from the validated JWT.
7. Write repository tests verifying tenant/owner filters.
8. Restrict actuator to minimal health without exposing sensitive endpoints.
9. If using a SPA, configure a strict CORS allowlist.
10. Write tests for missing tokens, wrong scopes, and wrong record ownership.

### Part C — End-to-End Token Tests

1. Use the lab MSAL/PKCE client to acquire an access token for the API scope.
2. Inspect issuer, audience, and timestamps safely using internal tools; never paste tokens into external websites.
3. Call GET Orders with a valid token → 200 containing only the user's records.
4. Call POST with only `Orders.Read` → 403.
5. Send an ID token or Graph access token → 401.
6. Send an expired or invalidly signed token in an integration test with local keys → 401.
7. Send an app-only token lacking the app role → 403.
8. Send an app-only token with `Jobs.Run` from an allowlisted caller → internal endpoint succeeds.
9. Attempt cross-tenant access from Tenant B to Tenant A → denied.
10. Confirm zero tokens or PII appear in request logs or traces.

### Part D — Deployment and Operations

1. Pick a lab Azure App Service, Container Apps, or AKS environment.
2. Supply configuration from environment/secret stores without hard-coding cross-environment identifiers.
3. Verify TLS, ingress, private networking, and metadata/JWKS egress.
4. Attach managed identity for downstream Storage/SQL if needed.
5. Enable Azure Monitor/App Insights with redacted security metrics.
6. Set alerts for abnormal 401/403 spikes or JWKS refresh failures.
7. Verify CORS/CSRF behavior with the real frontend.
8. Set up CI/CD tests using locally signed JWT fixtures.
9. Conduct a security review covering permissions, consent, RBAC, and tenant isolation.
10. Clean up lab resources per permissions; record lessons learned and runbooks.

## 36. Self-Check Questions

**Question 1.** How do an OAuth2 access token and an OIDC ID token differ in purpose and audience?

**Question 2.** Why must a Spring Boot API never trust that "the frontend already signed in"?

**Question 3.** Should the API and SPA have separate Azure app registrations, and why?

**Question 4.** How do a delegated scope and an application app role differ?

**Question 5.** Why does a client credentials token normally lack `scp` and have no user context?

**Question 6.** Is a token acquired via `/oauth2/v2.0` always a v2 access token?

**Question 7.** What must be checked for issuer and audience? Can audience checks be skipped when the issuer is valid?

**Question 8.** Why must Microsoft Graph tokens or ID tokens never be accepted by Orders API?

**Question 9.** How do `iss`, `tid`, `oid`, and `sub` differ?

**Question 10.** Are `name` and `email` suitable as durable ownership keys?

**Question 11.** Does decoding a JWT verify its signature?

**Question 12.** Where does a Resource Server obtain public signing keys and how does it handle key rotation?

**Question 13.** Why must you never trust a `jku` URL declared inside an incoming token?

**Question 14.** Does `issuer-uri` automatically guarantee audience validation across every Spring Boot version?

**Question 15.** How does Spring Security map `scp` and `roles` into authorities?

**Question 16.** How does `hasAuthority("SCOPE_Orders.Read")` differ from `hasRole("Orders.Read")`?

**Question 17.** Is a token carrying `Orders.Read` sufficient to read any `OrderId`? Why or why not?

**Question 18.** What role does the `(tid, oid)` pair play in multi-tenant ownership policies?

**Question 19.** How do 401 and 403 differ, and when might BOLA return 404?

**Question 20.** Under what conditions can CSRF be disabled, and does CORS replace authentication?

**Question 21.** Why should Bearer tokens never appear in URLs or request logs?

**Question 22.** Is a worker's managed identity automatically accepted by the API without an app role assignment?

**Question 23.** When Orders API must call Graph on a user's behalf, why use OBO instead of forwarding the incoming token?

**Question 24.** Why should `/common` never be used as a fixed expected issuer for multi-tenant tokens?

**Question 25.** Does Spring Security MockMvc `jwt()` prove signature, audience, and issuer validation?

**Question 26.** Is an offline-verified JWT immediately invalidated when a user logs out?

**Question 27.** Why must group overage be handled deliberately?

**Question 28.** Does APIM JWT validation replace database-level ownership checks?

**Question 29.** Which metrics help distinguish an issuer mismatch from a missing API scope?

**Question 30.** What should you do if 401 errors spike after key rotation instead of disabling security?

**Completion criteria:** learners accurately explain OAuth2/OIDC and token purposes, configure API/client app registrations, implement a Spring Resource Server validating issuer/audience/signature/lifetime, map scopes/app roles, enforce tenant/owner authorization, write negative tests, and establish logging, monitoring, and incident-response plans.

## Conclusion

**Protecting a REST API with Microsoft Entra access tokens** means far more than checking for an `Authorization: Bearer` header. A proper Spring Boot **OAuth2 Resource Server** verifies the access token's **signature, issuer, audience, and lifetime**, then enforces authorization via **delegated scopes, application roles, tenant/client restrictions, and data ownership**. A valid JWT only proves the token met those cryptographic and structural checks—it never replaces business authorization.

When deploying to Azure App Service, Container Apps, or AKS, combine **Entra app registration/consent, Spring Security 6, managed identity, HTTPS/private networking, trusted JWKS refresh, 401/403 tests, BOLA prevention, token redaction, Azure Monitor, and cost controls**. You can start with a small single-tenant API and expand to multi-tenant or OBO flows as needed, without ever dropping mandatory validations just to let requests pass.
