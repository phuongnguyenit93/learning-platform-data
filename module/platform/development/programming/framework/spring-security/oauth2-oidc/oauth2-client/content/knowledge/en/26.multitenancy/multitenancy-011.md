# 26.11. Separating Secrets, Tokens, Sessions, and Identity Data by Tenant

## 1. Problem: OIDC Login Succeeds, Yet Data Can Still Leak Across Tenants

An **Employee Portal** SaaS platform serves multiple organizations. Each organization is a **tenant** with its own employees, OIDC configuration, resources, and access permissions.

~~~text
Tenant ACME
  Public host: https://acme.portal.example.com
  OIDC issuer: https://login.acme.example/oidc
  Client registration: portal-acme
  Client secret: ACME_SECRET
  Authorized clients: ACME_TOKENS
  Business data: ACME_DATA

Tenant GLOBEX
  Public host: https://globex.portal.example.com
  OIDC issuer: https://identity.globex.example/oidc
  Client registration: portal-globex
  Client secret: GLOBEX_SECRET
  Authorized clients: GLOBEX_TOKENS
  Business data: GLOBEX_DATA
~~~

An ACME user is already logged in, yet sends:

~~~http
GET /api/reports?tenant=globex HTTP/1.1
Host: acme.portal.example.com
Cookie: __Host-SESSION=<opaque-session-id>
~~~

If the backend trusts the `tenant=globex` parameter and retrieves GLOBEX's token or data, the system violates **tenant isolation**. Even when OAuth2/OIDC login, the ID Token signature, and HTTPS are all valid, **cross-tenant authorization** is still broken.

Another bug is often subtler:

~~~text
Token cache key = "alice"

ACME alice logs in   -> cache["alice"] = AT-ACME
GLOBEX alice logs in -> cache["alice"] = AT-GLOBEX
ACME alice calls API -> cache["alice"] returns AT-GLOBEX
~~~

The issue is not that the Authorization Server issued an invalid token; the backend used a **storage key missing tenant and client registration**.

This lesson explains how to design four layers of isolation:

1. **Secret isolation** — client secrets, private keys, mTLS keys, and secret references.
2. **Token isolation** — access tokens, refresh tokens, authorized-client stores, and token lifecycles.
3. **Session isolation** — session cookies, `SecurityContext`, OAuth `state`, `nonce`, PKCE, and login callbacks.
4. **Identity/data isolation** — `(tenant, issuer, subject)`, memberships, RBAC, business data, and auditing.

> Technical context: Java 17+, Spring Boot 3, Spring Security 6, Spring MVC/Servlet OAuth2/OIDC Client; some sections compare WebFlux/Reactive. Tenant names, hosts, secrets, and tokens are illustrative. No single Spring Security property guarantees full tenant isolation on its own.

## 2. Tenant ID, Issuer, Client Registration, and Principal Differ

| Concept | Example | Security meaning |
|---|---|---|
| Tenant ID | `acme` | Organization/data/permission scope in the SaaS |
| OpenID issuer | `https://login.acme.example/oidc` | Trusted identity/token issuing authority |
| Registration ID | `portal-acme` | Specific OAuth2 client in Spring Security |
| Client ID | `acme-portal-web` | ID issued by the Authorization Server for the OAuth client |
| Subject | `sub=employee-42` | Subject identifier within the issuer/sector scope |
| Principal key | `acme:user-42` | Authorized client storage key chosen reliably by the system |
| Session ID | An opaque string | Used by browser to locate server-side session |
| Internal user ID | `u-1038` | User ID inside the application |

**Tenant ID does not necessarily equal issuer.** You may have:

- Each tenant has its own issuer.
- Multiple tenants share one issuer.
- One tenant has multiple issuers for employees/partners.
- One issuer provides multiple `ClientRegistration`s per tenant or per function.

Therefore, a rule `tenantId = token.iss` is only safe if that is genuinely a governed trust/tenant mapping contract.

### 2.1. User-Requested Tenant Is Not Yet an Authorized Tenant

Distinguish carefully:

~~~text
candidateTenant
  -> tenant derived from request host/path/query/header

authenticatedIdentity
  -> identity authenticated by OIDC or a trusted mechanism

authorizedTenant
  -> tenant where the identity genuinely holds active membership
     and permission for the current operation
~~~

**Use only `authorizedTenant` to fetch privileged credentials, query data, or make security decisions.**

### 2.2. Isolation Across Multiple Layers

Tenant isolation does not merely mean one database per tenant. A shared database can still be safe with proper queries and RLS/ACLs, whereas separate databases still leak if the backend picks the wrong connection using unverified input.

For complete protection, you need **identity trust + authorization + credentials + storage + network/API destination + lifecycle**.

## 3. Reference Architecture

~~~mermaid
flowchart TD
    A["Browser ACME"] --> R["Tenant resolver / trusted ingress"]
    B["Browser GLOBEX"] --> R
    R --> S["Tenant-bound session & authentication"]
    S --> P["Membership + authorization policy"]
    P --> C["Tenant registry / ClientRegistration"]
    C --> CA["portal-acme"]
    C --> CG["portal-globex"]
    CA --> VA["ACME secret reference / Vault"]
    CG --> VG["GLOBEX secret reference / Vault"]
    CA --> IA["ACME OpenID Provider"]
    CG --> IG["GLOBEX OpenID Provider"]
    P --> T["Tenant-aware authorized-client store"]
    T --> TA["ACME tokens"]
    T --> TG["GLOBEX tokens"]
    P --> D["Tenant-filtered business data"]
    P --> API["Allowlisted tenant downstream API"]
~~~

A valid request:

~~~text
HTTP request
  -> resolve candidate tenant using configured routing
  -> authenticate user/service
  -> verify membership and resource permission
  -> select tenant-owned ClientRegistration
  -> load authorized client from tenant partition
  -> call only trusted tenant Resource Server
  -> query data constrained by authorized tenant
~~~

Never invert the order by fetching a GLOBEX admin token first and checking afterward whether the ACME user has permission.

## 4. Tenant Resolution Rules: Host, Path, and Header Are Only Input

Common tenant sources:

~~~text
https://acme.portal.example.com
https://portal.example.com/t/acme/reports
X-Tenant-ID: acme
?tenant=acme
~~~

From host/path/header, the backend can find a **candidate tenant**. Only membership/authorization results promote it to an **authorized tenant**.

### 4.1. Use a Governed Tenant Registry

A registry should store:

~~~json
{
  "tenantId": "acme",
  "status": "ACTIVE",
  "publicHost": "acme.portal.example.com",
  "loginRegistrationId": "portal-acme",
  "serviceRegistrationId": "reports-acme-service",
  "issuer": "https://login.acme.example/oidc",
  "reportsApiBaseUri": "https://reports.acme.example",
  "clientSecretRef": "vault://oauth-clients/acme/portal/current"
}
~~~

`vault://` is an illustrative URI for a secret reference, **not standard Spring Security syntax**. In production, apply the corresponding secret manager's API/config adapter.

The registry must be updated through an administrative workflow—never let an HTTP user directly change issuer/secret reference/token endpoint.

### 4.2. Validate Host and Forwarded Headers

When using a reverse proxy:

~~~text
Browser -> HTTPS acme.portal.example.com
Ingress -> HTTP portal-service:8080
~~~

Ingress must normalize `Host`, `Forwarded`, and `X-Forwarded-Host` at the trust boundary; strip/overwrite headers sent by Internet clients.

If the app trusts an attacker-sent `X-Forwarded-Host: globex.portal.example.com`, the tenant resolver can be tricked into picking GLOBEX. Configuring `server.forward-headers-strategy` must be paired with **proxy trust**; it does not automatically make headers trustworthy.

### 4.3. Never Let Users Choose Arbitrary Registrations

Wrong:

~~~java
String registrationId =
    httpRequest.getParameter("tenant") + "-admin";
~~~

An attacker can probe a privileged registration. Use instead:

~~~text
authorized tenant -> registry allowlist -> permitted registration ID
~~~

## 5. Secret Isolation: Separating OAuth2 Credentials per Tenant

A confidential OAuth client may use:

- `client_secret_basic` or `client_secret_post`.
- `private_key_jwt` and private keys.
- mTLS certificates/private keys.
- Secrets for trusted ticket signers or workload credential issuers.

For ACME and GLOBEX, each client requires credentials per its Authorization Server registration. **Sharing an IdP does not mean sharing a client secret.**

### 5.1. Secret Key Design

A logical key:

~~~text
(tenantId, registrationId, credentialVersion)
~~~

For example:

~~~text
oauth-clients/acme/portal/v4
oauth-clients/acme/reports-service/v2
oauth-clients/globex/portal/v7
~~~

Avoid caching secrets under a shared `oauthClientSecret` key across all tenants.

### 5.2. Never Put Raw Secrets into the Tenant Database

A configuration table may hold:

~~~text
tenant_id
registration_id
issuer_uri
client_id
secret_ref
status
~~~

Where `secret_ref` is only a pointer to Vault/KMS. Actual credentials must be governed by storage/ACL/audit/rotation policies.

### 5.3. Workload Access and Blast Radius

If an ACME microservice can call the Vault API to read all GLOBEX secrets, an `/acme/` prefix is merely a convention, not isolation. Stronger boundaries require:

- Per-workload/per-tenant secret manager ACLs.
- Least-privilege IAM/service accounts.
- Auditing every read/rotation.
- Encryption in transit and at rest.
- Optionally separating pods/processes or secret brokers for tenants requiring high isolation.

A shared SaaS process sometimes must hold privileges to serve multiple tenants; understand the actual blast radius reduction and never market a namespace as an absolute security boundary.

## 6. Example Spring Boot `ClientRegistration` per Tenant

~~~yaml
# application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-acme:
            provider: acme-oidc
            client-id: ${ACME_OIDC_CLIENT_ID}
            client-secret: ${ACME_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read

          portal-globex:
            provider: globex-oidc
            client-id: ${GLOBEX_OIDC_CLIENT_ID}
            client-secret: ${GLOBEX_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read

        provider:
          acme-oidc:
            issuer-uri: https://login.acme.example/oidc
          globex-oidc:
            issuer-uri: https://identity.globex.example/oidc
~~~

`ClientRegistration` `portal-acme` and `portal-globex` have **separate registration IDs**. Placeholder values should come from a secret manager or secure runtime environment; never commit real client secrets into source code.

### 6.1. Sharing an Issuer Can Still Have Separate Registrations

If ACME and GLOBEX share an issuer:

~~~text
issuer = https://login.saas.example
~~~

the two registrations can share the provider alias in YAML while having different client IDs/secrets/scopes/redirects.

**Using a shared provider does not mean two tenants share tokens or memberships.**

### 6.2. Not Every Tenant Needs Its Own Issuer

Tenant is the business isolation boundary; issuer is the identity trust boundary. A system with one standard OP serving multiple tenants still requires per-tenant RBAC and data isolation.

### 6.3. `registrationId` Must Be Unique Within a Shared Repository

`ClientRegistrationRepository.findByRegistrationId(String)` has no tenant parameter. When using a shared repository, naming IDs like `portal-acme` and `portal-globex` avoids collisions. Never use `portal` for both in the same repository and rely on an unverified `ThreadLocal`.

## 7. Per-Tenant Client Secret Rotation

Example:

~~~text
ACME:   portal secret v4 -> v5
GLOBEX: portal secret v7 stays unchanged
~~~

A rotation workflow:

1. Verify the exact tenant and registration.
2. Create a new credential at the Authorization Server.
3. Store it in the secret manager under a new version with ACLs attached.
4. Update the `ClientRegistration`/secret resolver via an intentional deployment mechanism.
5. Test token exchange for that tenant.
6. Revoke the old credential per the rotation window.
7. Monitor `invalid_client` and audit logs.

Never rotate/disable GLOBEX just because ACME had an issue.

### 7.1. Rotation Does Not Mean Token Revocation

Changing a client secret **does not guarantee** all old access/refresh tokens were revoked. The Authorization Server has its own revocation and token validity policies. When credential compromise is suspected, review both token grants and sessions per incident response.

### 7.2. Never Keep Secrets Cached Indefinitely

A secret resolver may cache credentials temporarily, but requires TTLs, invalidation, and version handling. If Vault updates while the process retains the old client secret forever, the token endpoint may keep returning `invalid_client`.

## 8. Dynamic Onboarding and Issuer Discovery Must Be Controlled

With thousands of tenants, hardcoding YAML may not scale. The app can implement `ClientRegistrationRepository` backed by a tenant registry/secret manager.

Secure onboarding workflow:

~~~text
Tenant application
  -> verify organization ownership
  -> approve OIDC issuer and public endpoints
  -> inspect discovery metadata and exact issuer
  -> register OAuth client/redirect URIs
  -> assign secret reference and ACL
  -> approve scopes/audience/claim mapping
  -> activate tenant
~~~

Never accept a browser-entered issuer URI and auto-create a trusted OAuth client.

### 8.1. SSRF from OIDC Discovery

Example URLs that must not be accepted merely because they are syntactically valid:

~~~text
http://localhost:8080/admin
http://169.254.169.254/
https://unapproved.example/.well-known/openid-configuration
~~~

Issuer onboarding requires HTTPS, allowlists, DNS/IP egress restrictions, redirect checks, metadata issuer matching, and SSRF/DNS-rebinding protections. Never disable issuer verification because "a tenant's IdP has an unusual setup".

### 8.2. One Tenant Having Multiple Issuers

If ACME has both an employee IdP and a partner IdP, external identities must include the exact issuer, and provider configurations must isolate trust boundaries. Never rely solely on email across two issuers to merge users.

## 9. Token Isolation: Authorized Clients Must Be Separated by Tenant and Registration

Spring Security uses:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
~~~

It carries:

~~~text
ClientRegistration
principalName
accessToken
refreshToken (if issued)
~~~

An ACME authorized client **must never be used** for GLOBEX simply because two issuers share a hostname or two users share an email.

### 9.1. Storage Keys Should Describe the Tenant as Well

~~~text
(tenantId, clientRegistrationId, trustedPrincipalKey)
~~~

| Tenant | Registration | Principal | Token |
|---|---|---|---|
| acme | portal-acme | acme-u42 | AT-A |
| globex | portal-globex | globex-u42 | AT-G |
| acme | reports-acme-service | reports-job-acme | AT-AS |
| globex | reports-globex-service | reports-job-globex | AT-GS |

Never key by:

~~~text
oauth2:access-token:<username>
oauth2:access-token:<email>
oauth2:access-token:<issuer>
~~~

because username/email/issuer do not sufficiently distinguish client/tenant.

### 9.2. Spring Security's Default `OAuth2AuthorizedClientService`

The synchronous interface has methods:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

**There is no separate `tenantId` parameter.** If using the standard service on a shared store, registration IDs must be uniquely namespaced per tenant/client. If storage keys must also partition by tenant, the app needs a different adapter/repository or an explicitly designed storage scope.

### 9.3. A Key Prefix Alone Does Not Guarantee Authorization

Redis keys:

~~~text
oauth2:acme:portal-acme:acme-u42
oauth2:globex:portal-globex:globex-u42
~~~

reduce collision risk. Yet if any method can read `oauth2:globex:*` without tenant authorization, data can still leak. **Prefixes and ACLs/policies must go together.**

### 9.4. Principal Must Not Come from User Input

Wrong:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("portal-globex")
    .principal(requestParameterUserName)
    .build();
~~~

That can make the backend look up another principal's authorized client by storage key. In user-delegated flows, the principal must be an `Authentication` verified by Spring Security and aligned with the tenant.

## 10. Access Tokens Must Match the Resource Server and Tenant

Example token:

~~~text
iss = https://login.acme.example/oidc
aud = reports-acme-api
scope = reports.read
tenant_id = acme (if the token contract includes this claim)
~~~

Never send it to:

~~~text
https://reports.globex.example
~~~

expecting the token to be trusted because its signature is valid. The Resource Server must verify:

- Trusted issuer per policy.
- Signature/JWT or token introspection.
- Audience/resource indicator.
- Scopes/roles.
- Tenant binding and membership where applicable.
- Resource ownership.
- Expiration and revocation.

**A client JWT decoder must never read unverified claims and treat them as tenant permissions.** Issuer/audience/tenant claims are evidence only after verification under the proper contract.

### 10.1. An Access Token Is Not an ID Token

OIDC ID Tokens serve OAuth client authentication; access tokens are for Resource Servers. Never take an ACME ID Token and send it to GLOBEX's API or use an ID Token as data authorization.

### 10.2. Never Escalate Scopes in the Client

Editing `OAuth2AuthorizedClient` or a JWT JSON payload grants no extra rights. Scopes/audiences must be issued by the Authorization Server and verified by the API.

## 11. Refresh-Token Rotation and Concurrency

Two tenants have distinct token families:

~~~text
ACME:
  RT-A1 -> RT-A2 + AT-A2

GLOBEX:
  RT-G1 -> RT-G2 + AT-G2
~~~

Never write `RT-A2` over GLOBEX's row, and never retry `RT-A1` infinitely if the provider enforces rotation/reuse detection.

### 11.1. Intra-Tenant Races

~~~mermaid
sequenceDiagram
    participant A as Node A
    participant B as Node B
    participant DB as Authorized Client Store
    participant OP as ACME Token Endpoint

    A->>DB: load RT-A1
    B->>DB: load RT-A1
    A->>OP: refresh RT-A1
    B->>OP: refresh RT-A1
    OP-->>A: AT-A2, RT-A2
    OP-->>B: invalid_grant / provider behavior
    A->>DB: save RT-A2
    B->>DB: failure handler must not delete newer RT-A2
~~~

Mitigations under high load:

- Single-flight/locking per `tenant+registration+principal`.
- Optimistic versioning and compare-and-update.
- Failure cleanup aware of token generation/known version.
- Token endpoint rate limiting and timeouts.
- Never lock all tenants globally because one client is refreshing.

Local `synchronized` does not protect against races across multiple pods.

### 11.2. Distinguishing Errors

| Error | Layer | Remediation |
|---|---|---|
| `invalid_grant` | Token endpoint | Invalid refresh token/code; clean up per policy |
| `invalid_client` | Token endpoint | Wrong secret/client auth; inspect registration |
| `401 invalid_token` | Resource Server | Access token rejected; verify correct client/token |
| `403 insufficient_scope` | Resource Server | Insufficient permissions; never retry to escalate |
| HTTP 503/timeout | Transport/AS/API | Infrastructure failure; do not delete tokens by default |

Never wipe authorized clients across all tenants merely because one request hit 503.

## 12. Selecting Tokens via Manager in a Servlet Request

The following example only illustrates the contract; `tenantBinding` must be provided by registry/policy after the user is verified:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

String registrationId = tenantBinding.loginRegistrationId();

OAuth2AuthorizeRequest authorization = OAuth2AuthorizeRequest
    .withClientRegistrationId(registrationId)
    .principal(authentication)
    .build();

OAuth2AuthorizedClient authorizedClient =
    authorizedClientManager.authorize(authorization);
~~~

Preconditions:

1. Tenant membership has been verified.
2. Registration belongs to the right tenant.
3. `Authentication` was verified by Spring Security.
4. The user-delegated token was genuinely issued for that registration/tenant.
5. Manager/repository fits the Servlet request context.

**Never call the manager for GLOBEX's registration with ACME's principal hoping to gain GLOBEX access.** Accessing another tenant as a user requires corresponding authorization/consent.

### 12.1. Manager for Background Jobs

A task using `client_credentials` without an `HttpServletRequest` typically needs:

~~~java
AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

with the `clientCredentials()` provider:

~~~java
OAuth2AuthorizeRequest serviceRequest = OAuth2AuthorizeRequest
    .withClientRegistrationId("reports-acme-service")
    .principal("reports-job:acme")
    .build();
~~~

`reports-job:acme` is a service storage principal, not an IdP-authenticated human user. The job's tenant identity must come from trusted job configuration/validated message metadata.

## 13. `WebClient`/`RestClient`: Right Token with Wrong URL Is Still Dangerous

An HTTP gateway must select **both registration and destination** from a trusted tenant catalog:

~~~text
ACME:
  portal-acme -> https://reports.acme.example

GLOBEX:
  portal-globex -> https://reports.globex.example
~~~

Never do:

~~~java
String target = request.getParameter("target");
webClient.get().uri(target)
    .headers(h -> h.setBearerAuth(token))
    .retrieve();
~~~

That is an SSRF/credential exfiltration risk.

### 13.1. Domain DTO for the Tenant Registry

~~~java
public record TenantOAuthBinding(
    String tenantId,
    String loginRegistrationId,
    String serviceRegistrationId,
    java.net.URI reportsApiBaseUri
) {}
~~~

This is an **application-defined type**. The registry must validate HTTPS URIs, active tenant status, allowlisted clients/destinations, and persistence.

### 13.2. Gateway Illustrating Pre-Token-Use Checks

~~~java
package com.example.portal.reports;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class TenantReportsGateway {
    private final TenantRegistry registry;
    private final TenantAccessPolicy policy;
    private final OAuth2AuthorizedClientManager manager;
    private final WebClient.Builder webClientBuilder;

    public TenantReportsGateway(
        TenantRegistry registry,
        TenantAccessPolicy policy,
        OAuth2AuthorizedClientManager manager,
        WebClient.Builder webClientBuilder
    ) {
        this.registry = registry;
        this.policy = policy;
        this.manager = manager;
        this.webClientBuilder = webClientBuilder;
    }

    // Invoked inside an authenticated Servlet request.
    public Mono<String> readReport(
        String candidateTenant,
        Authentication authentication
    ) {
        TenantOAuthBinding binding =
            registry.requireActiveTenant(candidateTenant);

        // Must verify permission before acquiring the tenant's token.
        policy.assertCanReadReports(
            authentication, binding.tenantId());

        // If a delegated token is needed, login must bind to the exact tenant.
        policy.assertLoginBoundToTenant(
            authentication,
            binding.tenantId(),
            binding.loginRegistrationId());

        OAuth2AuthorizeRequest authorization =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(binding.loginRegistrationId())
                .principal(authentication)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(authorization);
        if (client == null) {
            return Mono.error(new IllegalStateException(
                "Tenant authorized client unavailable"));
        }

        // API URI comes from the trusted registry, not browser input.
        return webClientBuilder
            .baseUrl(binding.reportsApiBaseUri().toString())
            .build()
            .get()
            .uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                client.getAccessToken().getTokenValue()))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

`TenantRegistry` and `TenantAccessPolicy` are **application services not defined in the snippet**:

~~~java
public interface TenantRegistry {
    TenantOAuthBinding requireActiveTenant(String tenantId);
}

public interface TenantAccessPolicy {
    void assertCanReadReports(
        Authentication authentication, String tenantId);
    void assertLoginBoundToTenant(
        Authentication authentication,
        String tenantId,
        String expectedRegistrationId);
}
~~~

This illustrates the sequence of security checks, not a standalone runnable project. Production should manage `WebClient`/connection pools across their lifecycle rather than building an HTTP client per request. With Servlet + asynchronous `WebClient`, the manager needs the proper Servlet/security context at `authorize()` time.

### 13.3. Never Forward Bearer Tokens to Unallowlisted Redirect Hosts

If a downstream API returns a redirect to another hostname, the HTTP client must not automatically forward the Bearer token to the unfamiliar host. A fixed base URL does not automatically block absolute URIs passed via input; destination validation is still required.

## 14. Session Isolation: Session Cookie Is Not an Access Token

A browser request:

~~~http
Cookie: JSESSIONID=<opaque-id>
~~~

normally carries only a **session identifier**. Server-side `HttpSession` holds `SecurityContext` and may store `OAuth2AuthorizationRequest` during login. The authorized-client repository/service holds access/refresh tokens per configuration.

### 14.1. Three Separate Storage/Lifecycles

~~~text
Browser:
  opaque session cookie

Portal session store:
  session ID, authenticated identity, active/bound tenant
  state/nonce/PKCE correlation while login pending

OAuth2 authorized-client store:
  tenant + registration + principal -> access/refresh tokens
~~~

Session TTL does not equal token TTL. Local browser logout does not automatically revoke tokens at the OP.

### 14.2. Per-Tenant Session Models

| Model | Pros | Risks/requirements |
|---|---|---|
| Dedicated subdomain + host-only cookie | Browser isolates cookie scope automatically | Proper HTTPS, callback/host binding |
| Dedicated origin | Stronger browser isolation | DNS/cert/routing setup |
| Shared host, tenant in URL path | Simple deployment | Mandatory server-side session tenant partitioning |
| Shared session with active tenant | Easy tenant switching | Recheck membership + token/context switching |
| Dedicated session store per tenant | Reduces blast radius | Managing multi-store/TTL/lookups |

Cookie `Path`/`Domain` is a **browser transport policy**, not an authorization decision.

## 15. Host-Only Cookies and the `__Host-` Prefix

With:

~~~text
https://acme.portal.example.com
https://globex.portal.example.com
~~~

consider **host-only** session cookies:

~~~http
Set-Cookie: __Host-SESSION=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

The `__Host-` prefix requires `Secure`, `Path=/`, and no `Domain`. The browser will not send ACME's host-only cookie to GLOBEX's hostname.

### 15.1. Why Not Set a Shared Domain?

~~~http
Set-Cookie: SESSION=abc; Domain=portal.example.com; Path=/; Secure
~~~

can cause the cookie to be sent to multiple tenant subdomains. The server must then strictly enforce session tenant binding; widening `Domain` is not how to achieve IdP SSO.

SSO at the OpenID Provider has the IdP's own cookie. **There is no need to share the Portal session cookie across tenants to share IdP SSO.**

### 15.2. Shared Host by Path

~~~text
https://portal.example.com/t/acme/
https://portal.example.com/t/globex/
~~~

can share a browser session. The session must store `boundTenantId`/active tenant and check membership on every request. Setting a narrow Cookie `Path` **does not replace** backend RBAC/tenant checks.

## 16. `SameSite`, OAuth Callback, and Tenant Correlation

ACME's Authorization Code Flow:

~~~text
GET /oauth2/authorization/portal-acme
  -> generate state=S-A
  -> save original authorization request in ACME session
  -> redirect to ACME OpenID Provider
  -> browser callback /login/oauth2/code/portal-acme?code=...&state=S-A
~~~

The browser must send the right session cookie so Spring Security can retrieve the original authorization request.

### 16.1. `SameSite` Table

| SameSite | Cross-site top-level GET callback | Cross-site `form_post` POST |
|---|---|---|
| Strict | Usually does not send cookie | Does not send |
| Lax | Usually sends cookie | Usually does not send |
| None; Secure | Can send | Can send, subject to browser privacy/CSRF policy |

For GET callbacks, `Lax` is usually practical. For OIDC `response_mode=form_post`, review `None; Secure` cookies and intentional CSRF callback POST handling. **Never disable app-wide CSRF, `state`, `nonce`, or PKCE to fix callbacks.**

### 16.2. Cookie Host Mismatch

If ACME starts at:

~~~text
https://acme.portal.example.com/oauth2/authorization/portal-acme
~~~

but the callback arrives at:

~~~text
https://globex.portal.example.com/login/oauth2/code/portal-acme
~~~

the browser does not send ACME's host-only cookie, and the callback host/registration also mismatches. Fix the redirect URI, public host/proxy, and tenant binding; do not widen the cookie `Domain` indiscriminately.

## 17. Binding the Session and OAuth Authorization Request to the Tenant

A server-side session model:

~~~text
sessionId
boundTenantId
authenticatedInternalUserId
authenticationIssuer
authenticationSubject
loginRegistrationId
securityContext
createdAt / lastAccessedAt
~~~

This is an **application model**, not default `HttpSession` fields.

At the callback, verify against:

~~~text
expectedTenant from original authorization request
expectedRegistrationId
expectedIssuer
state
nonce
PKCE code_verifier
redirect URI
~~~

Never allow a callback query `?tenant=globex` to alter the expected tenant of ACME's `state`.

### 17.1. OAuth Mix-Up

When multiple Authorization Servers are supported, the app must avoid processing an authorization response from issuer A using the token endpoint/client of issuer B. Use state-bound original requests, registration/issuer binding, callback validation, and OIDC issuer/ID Token checks; if the protocol includes issuer identification in the authorization response, verify it per the appropriate standard.

**Never dynamically pick a token endpoint from an unverified issuer URL in the callback.**

### 17.2. Session Fixation Protection

Spring Security may rotate the session ID after authentication:

~~~text
Before login: S1
After login: S2
~~~

This can be proper security behavior. What matters is that `S1` matches the right tenant during the callback and `S2` preserves the tenant-bound authenticated context after login.

### 17.3. Multiple Tabs and Concurrent Logins

If tab A starts an ACME login and tab B starts a GLOBEX login around the same time in a shared session, the authorization-request repository may suffer overwrites/collisions depending on the implementation. When multi-flow support is needed, design pending requests keyed by `state`/tenant with TTL and replay protection rather than using a single global `pending_oauth_request` for all attempts.

## 18. Configuring Spring Boot Servlet Session Cookies

~~~yaml
# application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        name: __Host-SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

This is a general application/container configuration. When each tenant has its own host, host-only cookies are separated by hostname by the browser.

If sharing a host, this configuration **does not automatically create session tenant partitions**; explicit server-side binding or separate origins are required.

### 18.1. Spring Session Cookie Serializer

When the application uses Spring Session Redis/JDBC:

~~~java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer =
        new DefaultCookieSerializer();
    serializer.setCookieName("__Host-SESSION");
    serializer.setCookiePath("/");
    serializer.setUseSecureCookie(true);
    serializer.setUseHttpOnlyCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
~~~

This is an illustrative snippet and requires Spring Session dependencies/bean imports. Do not set `Domain` when using a `__Host-` cookie. Inspect the actual `Set-Cookie` header in the browser; Spring Session may use a `SESSION` cookie distinct from the container's `JSESSIONID`.

### 18.2. Multi-Node Session Storage

If Node A creates the OAuth authorization request and the callback lands on Node B without the server-side session on B, the flow still fails even with the right cookie. Use a shared Spring Session store or intentional routing strategy; **`SameSite` does not fix session store inconsistency**.

If the session store is shared across multiple tenants, protect both key namespacing and backend tenant binding.

## 19. Identity Isolation: From OIDC `(iss, sub)` to Tenant Membership

In OIDC, `sub` is only interpreted within the context of the issuer. For tenant data, a logical identity key is typically:

~~~text
(tenantId, issuer, subject)
~~~

Example:

~~~text
ACME:
  tenantId = acme
  iss = https://login.acme.example/oidc
  sub = 42

GLOBEX:
  tenantId = globex
  iss = https://identity.globex.example/oidc
  sub = 42
~~~

Two `sub=42` values do not prove the two identities are the same person when the issuers differ. Even with the same issuer and subject, memberships in each tenant remain independent.

### 19.1. Internal User vs. Tenant Memberships

One design:

~~~text
app_user:
  global internal user ID

tenant_membership:
  tenant ID
  user ID
  role
  status

external_identity:
  tenant ID
  issuer
  subject
  mapped internal user ID
~~~

A user may have the same internal ID across ACME/GLOBEX yet hold different roles. Never apply a global `ROLE_ADMIN` across all tenants if the policy is tenant-scoped.

### 19.2. Email Is Not a Stable Identity Key

Emails can change, be unverified, be reassigned, or collide. Never automatically map two accounts simply because:

~~~text
email = alice@example.com
~~~

Account linking requires verified identity evidence or authoritative mapping, not merely an email string.

### 19.3. Pairwise OIDC Subjects

An OP may issue different pairwise `sub` values per sector/client registration even for the same person. Having the same email and issuer with different `sub` values must not auto-link; having different subjects is also insufficient to conclude they are different people. An explicit/authoritative linking policy is required.

## 20. Reference SQL Schema

This is an **application-designed schema**, not default Spring Security tables:

~~~sql
CREATE TABLE tenant (
    id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE app_user (
    id VARCHAR(80) PRIMARY KEY
);

CREATE TABLE tenant_membership (
    tenant_id VARCHAR(80) NOT NULL,
    app_user_id VARCHAR(80) NOT NULL,
    status VARCHAR(30) NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, app_user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    FOREIGN KEY (app_user_id) REFERENCES app_user(id)
);

CREATE TABLE external_identity (
    id VARCHAR(80) PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    app_user_id VARCHAR(80) NOT NULL,
    UNIQUE (tenant_id, issuer, subject),
    FOREIGN KEY (tenant_id, app_user_id)
        REFERENCES tenant_membership(tenant_id, app_user_id)
);

CREATE TABLE tenant_oauth_registration (
    tenant_id VARCHAR(80) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    client_id VARCHAR(256) NOT NULL,
    secret_ref VARCHAR(512),
    registration_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, registration_id),
    UNIQUE (registration_id),
    FOREIGN KEY (tenant_id) REFERENCES tenant(id)
);

CREATE TABLE tenant_authorized_client (
    tenant_id VARCHAR(80) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    principal_key VARCHAR(256) NOT NULL,
    encrypted_access_token BLOB,
    encrypted_refresh_token BLOB,
    expires_at TIMESTAMP,
    token_generation BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, registration_id, principal_key),
    FOREIGN KEY (tenant_id, registration_id)
        REFERENCES tenant_oauth_registration(tenant_id, registration_id)
);
~~~

The SQL only illustrates the design; `BLOB` types, foreign keys, and timestamps must be adapted to the DBMS. The `encrypted_access_token` column must genuinely be encrypted by the storage adapter/KMS, not merely renamed.

### 20.1. Why `UNIQUE(registration_id)`?

A shared `ClientRegistrationRepository` is looked up by `registrationId` without a tenant parameter. Unique IDs across the repository/store scope prevent an ACME `portal` client from overwriting a GLOBEX `portal` client.

### 20.2. Queries Must Always Carry a Tenant Predicate

Not just:

~~~sql
SELECT * FROM invoice WHERE id = :invoiceId;
~~~

Instead:

~~~sql
SELECT *
FROM invoice
WHERE tenant_id = :authorizedTenantId
  AND id = :invoiceId;
~~~

`:authorizedTenantId` must be verified by the backend, not copied directly from a query parameter.

### 20.3. Row-Level Security Is Defense-in-Depth

PostgreSQL RLS can add a tenant filter layer at the DB. However, you must manage connection pool tenant context, transaction lifetimes, roles that bypass RLS, and privileged/admin operations. RLS does not replace application authorization or external identity validation.

## 21. Caches, Object Storage, Search, and Queues Must Also Be Separated

| Storage | Anti-pattern | Design to consider |
|---|---|---|
| Redis cache | `report:100` | `tenant:acme:report:100` + ACL |
| OAuth cache | `alice` | Tenant+registration+principal |
| Search index | Query without tenant filter | Tenant-scoped search & authorization |
| Object storage | `reports/2026.pdf` | Bucket/path/ACL + tenant binding |
| Queue | Job with only `userId` | Authenticated producer + tenant & authorization context |
| CDN | Caching private responses publicly | Private/no-store or correctly partitioned cache |
| Logs/traces | Tokens/emails in labels | Safe IDs, redaction, cardinality controls |

**A cache prefix alone does not solve the issue of the backend having permission to read all data.** Authorization and store policies are required.

## 22. Tenant Switching Must Preserve Permissions and Token Context

Suppose a user is a member of both ACME and GLOBEX and selects "Switch tenant":

~~~http
POST /api/tenant/switch HTTP/1.1
Content-Type: application/json
Cookie: __Host-SESSION=<opaque>

{"tenantId":"globex"}
~~~

The backend must:

1. Authenticate the request and apply CSRF protection for session-based actions.
2. Verify active membership in GLOBEX.
3. Determine whether GLOBEX login/consent already exists.
4. Never use ACME's delegated token for GLOBEX's API.
5. Update `activeTenant` consistently within the session/transaction.
6. Clear request caches/derived data belonging to ACME.
7. Fetch GLOBEX's roles/permissions and audit the tenant switch.

Do not simply run:

~~~java
session.setAttribute("activeTenant", request.getTenantId());
~~~

and reuse all prior permissions. Switching context does not grant permissions on its own.

### 22.1. Two Subdomains

If tenant URLs have different hosts, you can redirect to the GLOBEX host; browser host-only cookies help separate sessions. The IdP may reuse SSO, but GLOBEX still needs its own authorization request/callback and membership checks.

### 22.2. One Shared Host

If sharing `portal.example.com` and differing only by path, the session cookie is typically shared. In that case, server-side tenant binding/active-tenant policy and tenant-scoped data access must be implemented with extreme care.

## 23. Tenant-Specific Authorization Differs from Global Authorization

A user may have:

~~~text
Tenant ACME:
  role = REPORTS_ADMIN

Tenant GLOBEX:
  role = REPORTS_VIEWER
~~~

Do not attach `ROLE_REPORTS_ADMIN` to `Authentication` and grant access across every tenant's data if the role is actually tenant-scoped.

An illustrative policy interface:

~~~java
public interface TenantAuthorizationService {
    void requireMembership(
        Authentication authentication, String tenantId);

    void requirePermission(
        Authentication authentication,
        String tenantId,
        String permission);

    void requireResourceOwnership(
        String tenantId, String resourceId);
}
~~~

`@PreAuthorize("hasRole('ADMIN')")` does not inherently know which tenant is targeted; a custom authorization bean/method security checking membership and resource ownership may be needed.

### 23.1. Disabled Membership

A user can be disabled in ACME while still active in GLOBEX. Successful OIDC authentication does not prove ACME membership is still active.

### 23.2. Tenant Claim from a Token

If the IdP issues a `tenant_id` claim, you must verify the token and map the claim to tenant policy. Never trust a header or an unverified JWT payload self-declaring a tenant.

## 24. Session Logout, OAuth Token Cleanup, and OP Logout Are Three Different Things

When a user logs out of ACME:

~~~text
ACME browser session: invalidate.
ACME authorized clients: cleanup/revoke per policy.
ACME OP SSO session: logout if needed and supported by the OP.
GLOBEX state: not automatically destroyed unless governed by a shared policy.
~~~

### 24.1. Local Cleanup Does Not Revoke Tokens at the AS

Deleting `OAuth2AuthorizedClient` from the database does not ensure tokens were revoked at the Authorization Server. A token revocation endpoint or dedicated OP policy is needed if required.

### 24.2. Back-Channel Logout

If receiving back-channel logout from an OP, verify issuer, signature, audience, logout token events/subject/session binding, and map to the exact tenant/registration. Never look up sessions by email and destroy them across all tenants.

### 24.3. Deprovisioning a Tenant

A workflow includes:

- Stopping new logins and token authorizations for the tenant.
- Disabling related service jobs/queue consumers.
- Rotating/revoking client secrets and authorized clients per policy.
- Invalidating sessions and caches.
- Blocking API/business data access.
- Deleting/retaining identity/business records per legal and data retention requirements.
- Reviewing backups, object storage, logs, and search indexes.
- Auditing the deprovisioning without affecting other tenants.

## 25. Encryption, KMS, and Blast Radius

When a shared database stores tokens/PII, envelope encryption can be used:

~~~text
ACME ciphertext -> data key A -> KMS policy/key A
GLOBEX ciphertext -> data key G -> KMS policy/key G
~~~

This design can reduce the blast radius if one key is compromised, but requires:

- KMS IAM and per-workload decrypt permissions.
- Key rotation and versioning.
- Auditing key usage.
- Secure backup/recovery.
- Policies for deleting keys/data when deprovisioning a tenant.

**A per-tenant KMS key is not sufficient** if the app process has permission to decrypt all tenants and a user-controlled tenant ID decides which key is used.

## 26. Reactive / WebFlux: Do Not Use `ThreadLocal` Tenants Indiscriminately

Spring WebFlux uses Reactive `SecurityContext`/Reactor Context; do not store the current tenant in a static mutable variable or rely on default `ThreadLocal` when pipelines switch schedulers.

### 26.1. Corresponding Components

| Servlet | Reactive |
|---|---|
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| `HttpServletRequest` context | `ServerWebExchange` / Reactor context |

Service-based managers are for background jobs; web request managers use the appropriate repository and request context.

### 26.2. Passing the Authorized Tenant Explicitly

~~~java
public Mono<String> readReport(
    String candidateTenant,
    Authentication principal
) {
    return tenantPolicy.verify(candidateTenant, principal)
        .flatMap(authorizedTenant ->
            tenantGateway.readWithTenantRegistration(
                authorizedTenant, principal));
}
~~~

`tenantPolicy`/`tenantGateway` are application services, not built-ins. `verify()` returns an immutable authorized tenant context. **Reactor Context only propagates data; it does not prove the tenant data is trustworthy.**

## 27. Testing Cross-Tenant Isolation: Negative Tests Matter More Than Happy Paths

| Scenario | Expected outcome to enforce |
|---|---|
| ACME user requests `tenant=globex` | 403 before acquiring GLOBEX token |
| ACME session cookie sent to GLOBEX host | Host-only cookie does not match |
| ACME OAuth `state` sent to GLOBEX callback | Rejected, does not switch to GLOBEX registration |
| ACME ID Token has GLOBEX issuer | Rejected for wrong issuer |
| ACME AT calls GLOBEX API | Resource Server rejects audience/tenant |
| Two users with same username in two tenants | No collision in authorized-client store |
| Two external users with same email | No auto-linking |
| ACME RT rotates | Does not overwrite GLOBEX RT |
| ACME `invalid_grant` cleanup | Does not delete GLOBEX authorized client |
| ACME admin role, GLOBEX viewer | No admin rights in GLOBEX |
| Tenant suspended | Even with live session/token, data cannot be read |
| ACME secret rotation | GLOBEX token client secret is unchanged |
| Same resource ID in two tenants | Query/cache only returns authorized tenant |
| Two pods refresh same token | Stale failure does not delete newer token |
| Spoofed `X-Forwarded-Host` | Does not change authorized tenant/issuer |
| Dynamic issuer is `localhost` | Onboarding rejects / SSRF prevention |

### 27.1. Unit Testing Authorization Rules

~~~java
@Test
void acmeUserCannotUseGlobexAuthorizedClient() {
    Authentication acme = authenticatedAcmeFixture();

    assertThrows(AccessDeniedException.class, () ->
        tenantPolicy.assertCanReadReports(acme, "globex"));
}
~~~

This is a **test fragment**; `authenticatedAcmeFixture()` and `tenantPolicy` are defined by the application/test. The test must verify the policy fails before the manager/secret store is called.

### 27.2. Testing the Authorized-Client Store Key

~~~text
Given:
  (acme, portal-acme, alice) -> AT-A
  (globex, portal-globex, alice) -> AT-G

Then:
  load ACME returns AT-A
  load GLOBEX returns AT-G
  removing ACME does not remove GLOBEX
~~~

If using Spring Security's default service keyed by `(registrationId, principalName)`, verify registration IDs are unique per tenant in the shared store.

### 27.3. Testing Callback Mix-Up

~~~text
Given: authorization request ACME, state=S-A
When:  callback /login/oauth2/code/portal-globex uses S-A
Then:  must not authenticate as GLOBEX
~~~

Never disable `state`/`nonce`/PKCE/issuer validation merely to make integration tests easier to write.

## 28. Failure Scenario: Token Cache Keyed by Username

Suppose:

~~~java
cache.put(authentication.getName(), authorizedClient);
~~~

ACME/GLOBEX both have `alice`. Sequential operations can overwrite the token. As a result, an ACME request carries a GLOBEX token:

- A proper Resource Server will reject it, yet the client has still violated credential isolation.
- A misconfigured Resource Server may leak data.
- Wrong token cleanup also causes widespread logouts/re-authorizations.

Remediation:

1. Stop using cache keys missing tenant/registration.
2. Invalidate entries that may have been tainted.
3. Identify affected sessions/tokens/requests via audit logs.
4. Rotate/revoke credentials as needed.
5. Add negative tests for duplicate principal names.

**A `401` from the Resource Server does not mean the system has avoided a security issue.**

## 29. Failure Scenario: Broad Cookie `Domain` Across All Tenants

A cookie:

~~~http
Set-Cookie: SESSION=abc; Domain=portal.example.com; Secure; HttpOnly
~~~

can be sent to multiple subdomains. If the server only looks up the session ID and allows the tenant based on the request host, session confusion can occur.

Solution:

- Host-only cookies if tenants reside on subdomains.
- Bound tenant ID in the server-side session.
- Reject requests whose tenant differs from the session unless an authorized switch flow exists.
- Keep `state`/registration/issuer correlation on callbacks.
- Never use cookie `Path`/`Domain` as a substitute for authorization.

## 30. Tenant Kill Switch and Incident Response

A SaaS needs the ability to suspend a tenant:

~~~text
tenant.status = SUSPENDED
~~~

The system must:

1. Reject new OAuth login initiations for the tenant.
2. Stop issuing new service tokens.
3. Block all business API access at the authorization layer.
4. Invalidate tenant sessions per policy.
5. Clean up/revoke authorized clients and rotate secrets if needed.
6. Stop related jobs/queues/webhooks.
7. Audit and verify other tenants are unaffected.

**Merely deleting `ClientRegistration` is not enough**, because users may still have active sessions/tokens and Resource Servers still serve data.

### 30.1. Tenant-Scoped vs. Global Incidents

A compromised ACME secret may affect only ACME if isolation is sound. However, a global cache key bug mixing authorized clients may require investigating the entire SaaS, not just the first tenant discovered.

## 31. Monitoring/Auditing Without Leaking Secrets

Metrics/events should distinguish:

~~~text
oauth.login.failure{tenant=acme,registration=portal-acme}
oauth.token.refresh.failure{tenant=globex,registration=portal-globex}
tenant.authorization.denied{tenant=acme,reason=cross_tenant}
session.tenant_mismatch{tenant=globex}
secret.rotation.event{tenant=acme,registration=portal-acme}
~~~

These names are **application-created instrumentation examples**, not all emitted by Spring Security by default.

Never log:

~~~text
client_secret=<actual>
access_token=<actual>
refresh_token=<actual>
private_key=<actual>
Cookie: SESSION=<actual>
Authorization: Bearer <actual>
authorization_code=<actual>
OIDC id_token=<actual>
~~~

Audit logs should record tenant ID, registration ID, controlled internal user ID, action, resource ID, allow/deny decision, correlation ID, and timestamp. Do not put emails/subjects/tokens into overly granular metric labels.

## 32. Troubleshooting by Symptom

| Symptom | Possible cause | Resolution |
|---|---|---|
| ACME user sees GLOBEX data | Missing tenant filter/RBAC/cache isolation | Check queries, policies, RLS |
| Tokens swapped across tenants | Key missing tenant/registration | Fix store key and invalidate cache |
| Only ACME `invalid_client` | Wrong/rotated ACME client secret | Check Vault and IAM records |
| All tenants `invalid_client` | Global secret resolver/config failure | Check deployment |
| ACME callback hits GLOBEX | Wrong redirect/correlation | Check `state`, issuer, host, registration |
| `authorization_request_not_found` | Cookie/session store or concurrent login | Browser DevTools/Redis |
| Browser sends cookie A to B | Broad cookie `Domain` | Host-only + server tenant binding |
| ACME admin user has admin rights in GLOBEX | Role not tenant-scoped | Membership/RBAC policy |
| Users with same email merged | Auto-linked by email | Use `tenant+issuer+sub` |
| ACME refresh deletes GLOBEX token | Overly broad failure handler | Scoped cleanup/token generation |
| Suspended tenant still reads data | Only disabled login | Enforce status on every API request |
| `X-Forwarded-Host` changes tenant | Header spoofing | Ingress strip/overwrite |
| Discovery calls `localhost` | Dynamic issuer SSRF | Allowlist + network policy |
| Fails only when scaling multiple pods | Local session/token store | Shared storage |
| API 403 despite valid token | Scope/role/resource permission | Do not retry token infinitely |
| HTTP 503 wipes all tokens | Wrong error mapping/cleanup | Only handle invalid token/grant |

### 32.1. Investigation Order

~~~text
Cross-tenant access / login / token failure
    |
    v
Where did the candidate tenant come from?
    |
    v
Are the authenticated principal and issuer/subject valid?
    |
    v
Are tenant membership/resource permissions verified?
    |
    v
Does ClientRegistration belong to the right tenant?
    |
    v
Are secret reference tenant and version correct?
    |
    v
Does authorized-client key match tenant+registration+principal?
    |
    v
Are session/callback state/nonce/PKCE bound to the right tenant?
    |
    v
Are downstream audience/URL and DB/cache tenant filtering correct?
    |
    v
Check rotation, revocation, concurrency, and audit logs.
~~~

## 33. Anti-Patterns to Avoid

**1. Trusting `X-Tenant-ID` or query tenant as access permission.** Input requires membership/authorization.

**2. Caching tokens solely by email/username.** Prone to collisions across issuers/tenants.

**3. One global client secret for multiple independent clients.** Increases blast radius and may violate contracts.

**4. Storing raw secrets in the tenant database with unrestricted read access.** Use a secret manager/ACL.

**5. Letting users choose arbitrary OAuth registrations/issuers/token endpoints.** Creates SSRF/confused deputy risks.

**6. Using an ACME token to call GLOBEX API because of a shared provider.** Audience/scope/tenant rights differ.

**7. Broad cookie `Domain` to "share SSO".** OP SSO differs from Portal sessions.

**8. Not binding the tenant to `state`/authorization request.** Risk of callback mix-up.

**9. Auto-linking users by email.** Unstable and not always verified.

**10. Applying a global `ROLE_ADMIN` across all tenants.** Permissions are typically tenant-scoped.

**11. Querying resources solely by `id`, omitting `tenant_id`.** Leads to IDOR/cross-tenant disclosure.

**12. Deleting all tokens when one tenant gets `invalid_grant`/503.** Cleanup must be scoped.

**13. Disabling CSRF/`state`/`nonce`/PKCE so multi-tenant login works easily.** Weakens security.

**14. Assuming a per-tenant KMS key suffices when the backend has decrypt-all rights.** IAM/authorization is required.

**15. Testing only happy paths.** Must test that tenant A users cannot use tenant B secrets/tokens/sessions/data.

## 34. Practice Exercises

### Exercise 1 — Tenant from Query

~~~http
GET /api/reports?tenant=globex HTTP/1.1
Cookie: __Host-SESSION=<acme-session>
~~~

**Question:** Should you fetch the GLOBEX token immediately?

**Answer:** No. You must verify user membership/permissions in GLOBEX and the corresponding login/grant token first.

### Exercise 2 — Token Cache Key

~~~text
key = issuer + ":" + username
~~~

**Question:** Why is this insufficient?

**Answer:** One issuer can serve multiple clients/tenants, and usernames can collide. You need `tenant+registration+trusted principal key` or an equivalent partition.

### Exercise 3 — Same Issuer, Different Tenants

ACME/GLOBEX use one issuer but separate client IDs.

**Question:** Can a single provider configuration be used?

**Answer:** Yes, if the issuer/endpoints are genuinely shared. However, client registrations, secrets, authorized clients, and tenant data remain independent.

### Exercise 4 — Cookie Domain

~~~http
Set-Cookie: SESSION=...; Domain=portal.example.com; Secure; HttpOnly
~~~

**Question:** What is the risk when two tenants are on two subdomains?

**Answer:** The cookie can be sent to both hosts. Use host-only cookies where appropriate and enforce server-side session tenant binding.

### Exercise 5 — RT Rotation Race

Node A has saved `RT-A2`; Node B encounters `invalid_grant` from `RT-A1`.

**Question:** Should all ACME/GLOBEX authorized clients be deleted?

**Answer:** No. You need single-flight/version-aware cleanup scoped to the exact authorized client; never delete newer tokens or cross-tenant records.

### Exercise 6 — Duplicate Email

~~~text
ACME: iss=A, sub=11, email=jane@example.com
GLOBEX: iss=G, sub=92, email=jane@example.com
~~~

**Question:** Should they be auto-merged into the same internal user?

**Answer:** No. Use authoritative identity mapping/account linking; email is not a stable identity key.

### Exercise 7 — SSO Is Not Tenant Authorization

A user is already logged into ACME; OP SSO quickly completes the GLOBEX callback, yet the user has no GLOBEX membership.

**Question:** Should GLOBEX access be granted?

**Answer:** No. Successful authentication/SSO differs from tenant membership and resource permissions.

### Exercise 8 — Dynamic Issuer

An admin enters an arbitrary issuer URL causing the backend to run discovery immediately.

**Question:** What are the risks?

**Answer:** SSRF and metadata trust confusion. You need allowlists/ownership verification, HTTPS, DNS/egress rules, and issuer metadata validation.

### Exercise 9 — Suspended Tenant

A tenant is suspended while web sessions/access tokens are still valid.

**Question:** Is deleting `ClientRegistration` enough?

**Answer:** No. You must enforce `tenant.status` and permissions at the API, invalidate sessions, stop jobs, and clean up/revoke tokens per policy.

### Exercise 10 — Isolation Testing

ACME and GLOBEX share the same `principalName` `alice`.

**Question:** What are the minimum tests?

**Answer:** Separate save/load/remove of authorized clients, denying cross-tenant authorization, verifying callback `state`/issuer, resource audience, and DB/cache tenant filters.

## 35. Implementation Checklist

| Question | Requirement to ensure |
|---|---|
| Do tenant IDs have a canonical format? | Yes, do not accept arbitrary strings |
| From what source is the candidate tenant resolved? | Trusted routing/registry |
| Is the user authorized for the tenant? | Membership/permission before token use |
| Is issuer metadata verified? | Exact issuer, HTTPS, anti-SSRF |
| Is the registration ID unique across the store? | No collisions |
| Is `secretRef` scoped by tenant/registration/version? | Yes |
| Are Vault/KMS ACLs restricted? | Yes |
| Is client credential rotation independent? | Yes |
| Is the authorized-client key tenant-scoped? | Yes |
| Are token encryption/ACLs appropriate? | Yes |
| Are refresh rotation/concurrency handled? | Yes if needed |
| Is the failure handler scoped? | Do not wipe an entire issuer |
| Are API destinations allowlisted? | Yes |
| Does the Resource Server check audience/scope? | Yes |
| Is the session cookie `Secure`/`HttpOnly`? | Yes in production |
| Is a host-only cookie used with subdomains? | Preferred |
| Is the session bound to the tenant? | Yes |
| Are OAuth `state`/nonce/PKCE matched to the tenant? | Yes |
| Are proxy headers trusted? | Ingress strip/overwrite |
| Is the identity key `(tenant,iss,sub)`? | Appropriate identity mapping |
| Is account linking verified? | Never link solely by email |
| Are roles/permissions tenant-scoped? | Yes |
| Do DB queries and caches have tenant filters? | Yes |
| Do logout/deprovisioning clean up properly? | Yes |
| Has the tenant kill switch been tested? | Yes |
| Are logs free of exposed tokens/secrets? | Yes |
| Are there cross-tenant negative tests? | Yes |

## 36. Summary

In **multi-tenant Spring Security OAuth 2.0/OIDC Client** systems, separating **secrets, tokens, sessions, and identity data** is a cross-cutting architectural concern, not merely adding a tenant prefix in YAML. **Secrets** must belong to the right tenant/registration and be managed via a secret manager/ACL. **`OAuth2AuthorizedClient`** must be selected/stored by verified registration/principal, with a tenant namespace or equivalent storage partition. **Browser sessions/cookies and OAuth callbacks** must preserve the right tenant, `state`, `nonce`, PKCE, registration, and issuer. **Identities and business data** require mapping by tenant/issuer/subject, tenant membership, RBAC, and resource ownership.

Multiple tenants can **share one issuer** while still separating credentials, tokens, sessions, and permissions. Conversely, multiple issuers require strict callback/issuer binding to prevent mix-ups. When using a shared database/Redis, ensure composite keys, tenant-scoped authorization, encryption, ACLs, and cross-tenant negative tests.

**The most important principle:** the tenant requested by the browser is only a **candidate**; only a tenant verified by the backend's authorization checks is an **authorized tenant**. Every operation that fetches secrets, loads tokens, validates callbacks, reads sessions, or queries data must preserve this boundary. That is the foundation for containing an incident within one tenant rather than letting it spread across the entire SaaS.
