# API Keys Represent Applications, Services, or Accounts Under a Specific Policy

An API key is a **credential**: a secret string that a client presents when calling an API so the server can verify usage permission. When the credential is valid, the application must next answer **who this key represents**. Depending on the provisioning policy, that may be an application, an automated service (service account), or a user/organization account (account).

**Having a valid key does not mean being allowed to do everything.** A key is only proof of possessing a credential. The identity (principal), tenant, scopes, status, and effective permissions are determined by the provisioning record together with server-side policies. This is the most important boundary when designing API keys with Spring Security.

This lesson clearly distinguishes key ID, secret, principal, and owner; presents the three representation models; explains how to build `Authentication` and `GrantedAuthority`; covers tenant/resource authorization principles; details key lifecycle; and provides Java 17+ examples and Spring Security Servlet configuration snippets.

## 1. Key, principal, owner, and key creator are four distinct concepts

A client may send:

~~~http
GET /api/catalog/items HTTP/1.1
Host: api.example.org
X-API-Key: <client-stored-secret>
~~~

The `X-API-Key` header is only an application convention for passing a credential. **Spring Security does not authenticate every X-API-Key header by default**; the system needs a dedicated filter/provider/verifier or a properly configured trusted gateway.

A provisioning record may contain:

| Component | Example | Meaning |
| --- | --- | --- |
| Raw API key | Long random string issued to the client | Secret proving permission to use the credential |
| Public key ID | `ak_7c82d1` | Record identifier for lookup, audit, revocation; not a secret |
| Subject type | `APPLICATION`, `SERVICE_ACCOUNT`, `ACCOUNT` | Type of entity represented by the key |
| Subject ID | `app:checkout`, `svc:billing-sync`, `user:lan` | ID of the principal recognized by the API |
| Owner ID | `team:commerce`, `team:finance`, `user:lan` | Who manages and is responsible for the key |
| Created by | `user:security-admin` | Who requested/issued the key |
| Tenant ID | `tenant-a` | Permitted organization/data scope |
| Key scopes | `CATALOG_READ`, `INVOICE_WRITE` | Ceiling of permissions that can be requested via the key |
| Status, expiry | `ACTIVE`, expiration timestamp | Conditions for continued use |

**The owner is not necessarily the principal:** a team lead may manage the key for `svc:billing-sync`, but when the job calls the API, the principal must be the service account, not the team lead. Nor does the key creator automatically become the end user of every request.

**A key ID is not sufficient for authentication:** the public identifier may appear in admin UIs or controlled logs; having only the ID without a valid secret must not grant an Authentication.

**The principal differs from the resource subject:** a request called by a service may operate on a customer's invoice. The customer is the resource owner, not the actor executing the HTTP request.

## 2. Three identity representation policies

### 2.1. API key representing an application (application key)

Example:

~~~yaml
keyId: ak_app_01
subjectType: APPLICATION
subjectId: app:checkout
ownerId: team:commerce
tenantId: tenant-a
keyScopes:
  - CATALOG_READ
status: ACTIVE
~~~

This key proves the client knows the credential issued to the **checkout application**. If 10,000 users all operate through the same backend, from this key alone **it is impossible to deduce who the end user is**.

When identifying the end user is required, the application must add an appropriate user authentication/authorization mechanism such as a session, OAuth2/OIDC, or an access token carrying a user subject. You cannot let the client simply send `X-User: admin` and treat that as proof of authorization.

A static key embedded in a JavaScript bundle, public web app, or public mobile app can usually be extracted. It can be used to identify the *client type* or support public quotas, but should not be treated as a strong secret to protect sensitive data.

**Permission example:** `app:checkout` is allowed to read the catalog, not modify user accounts, and not pay on behalf of a buyer merely because it holds an application key.

### 2.2. API key representing a service (service account key)

Example:

~~~yaml
keyId: ak_service_01
subjectType: SERVICE_ACCOUNT
subjectId: svc:billing-sync
ownerId: team:finance-platform
tenantId: tenant-a
keyScopes:
  - INVOICE_READ
  - INVOICE_WRITE
status: ACTIVE
~~~

A scheduled invoice synchronization job has its own **machine identity**. Requests to the API are actions of `svc:billing-sync`. This account is not a real user and does not necessarily have a login screen/MFA. Its permissions are granted according to its task: synchronizing invoices for the right tenant and endpoints.

Service keys should be bound to an environment or workload so they can be revoked independently. If every service in an organization shares a single `internal-admin` key, audits cannot distinguish who called what, permissions are overly broad, and a single incident can affect everything.

If stronger assurance about the executing machine is needed, consider workload identity, mTLS, or OAuth2 client credentials. A regular bearer API key proves **the sender possesses the secret string**, not that it is a specific process or machine.

### 2.3. API key bound to an account (account-bound key)

For example, user Lan creates a key for a reporting script:

~~~yaml
keyId: ak_user_01
subjectType: ACCOUNT
subjectId: user:lan
ownerId: user:lan
tenantId: tenant-a
keyScopes:
  - REPORT_READ
status: ACTIVE
~~~

The API can recognize the request under account `user:lan`, **but must not conclude that Lan just interacted directly**. Any script or party holding the key can use it. Audits must record the authentication method as API key to distinguish it from interactive login.

Personal keys must be constrained by current account status and permissions. If the account is disabled, removed from the tenant, or loses report-read permission, the key must not retain those permissions indefinitely simply because it was permitted at issuance time.

An "Account" can also be an organization account, project, or billing account: `account:billing-prod`. In that case, the principal must reflect the proper account type, rather than being automatically assigned to the person who clicked the create-key button.

### Comparison

| Criterion | Application | Service account | Account-bound |
| --- | --- | --- | --- |
| Primary identity | Client application | Workload/job/service | Specific account |
| Usually managed by | App development team | Operations team | Account owner or admin |
| Proves user is acting directly? | No | No | Does not prove direct interaction |
| Scope to restrict | App features, tenant, environment | Service tasks, resources | Current account permissions ∩ key scopes |
| Prominent risk | Key leaked from public client | Overly broad shared key | Key outlives revoked permissions |
| Audit actor | app ID | service ID | account ID + API key method |

A system may use all three types, but must define separate provisioning policies and never silently switch a key from one principal to another.

## 3. Actor, resource owner, createdBy, and on-behalf-of

Example:

~~~text
keyId           = ak_service_01
actorPrincipal  = svc:billing-sync
owner           = team:finance-platform
createdBy       = user:security-admin
resourceOwner   = customer:42
tenant          = tenant-a
~~~

**Actor principal** is the service calling the API. **Resource owner** is the customer whose invoice is being processed. **Key owner** is the team administering the secret. **CreatedBy** is the person who created the key. These four pieces of information serve different purposes and must not be conflated.

If a service needs to act *on behalf of* a user, separate proof of delegation is required: who approved it, who is authorized, which scopes/resources, for how long, and how to revoke it. A client-supplied header such as:

~~~http
X-API-Key: <secret>
X-Acting-User: admin
~~~

is not proof of authorization. OAuth2 Authorization Code or a properly designed delegation/token exchange mechanism can be used when user identity is needed across a chain of multiple services.

Audits should record at least `actorType`, `actorId`, `keyId`, `tenantId`, `resourceOwnerId`, action, outcome, and correlation ID. Do not put raw API keys or secret hashes into logs.

## 4. Pipeline from credential to Authentication

A request using an API key in a Servlet application typically goes through these steps:

~~~text
Client sends X-API-Key over HTTPS
    |
    v
API gateway / Spring Security filter
    |
    v
Check format, length, header count
    |
    v
Look up keyId and verify secret against trusted digest/HMAC
    |
    v
Check revoked/expiry/status/tenant/environment
    |
    v
Determine subjectType, subjectId, owner, and server-side policy
    |
    v
Check principal is still valid; compute effective authorities
    |
    v
Create Authentication (principal, authorities; do not retain raw key)
    |
    v
Request SecurityContext
    |
    v
Authorization by action + tenant + resource
    |
    v
Allow or deny
~~~

It is necessary to distinguish the outcome classes:

- **Missing credential** on an API-key-only endpoint: unauthenticated, typically returns **401**.
- **Wrong, expired, or revoked key:** do not create an authenticated principal; typically **401** with a generic message.
- **Valid key but insufficient scope or resource policy:** the caller is identified but not permitted; typically **403**.
- **Key store, HSM, or policy store unavailable:** fail closed, do not create a default principal; may return **5xx/503** by design.
- **Rate limit/quota:** may return **429**, which is an additional policy, not a substitute for authorization checks.

In Spring Security Servlet, `Authentication` holds `principal`, `credentials`, and `authorities`. `SecurityContextHolder` manages the authentication context for the processing thread; do not store the current principal in a `static` field or mutable singleton.

Spring Security provides `AuthenticationManager`, `ProviderManager`, and `AuthenticationProvider` to structure the authentication flow. With custom API keys, the application can implement an AuthenticationProvider or a filter calling a dedicated verification service. **There is no default rule that every valid X-API-Key automatically becomes a user in Spring Security.**

## 5. Effective permissions are the intersection of multiple conditions

Being authenticated and being authorized are two different questions. An access control model:

~~~text
ALLOW(request) =
    key_valid
  AND principal_active
  AND key_tenant_matches_resource
  AND requested_action_in_key_scopes
  AND requested_action_in_principal_entitlements
  AND resource_policy_allows
  AND contextual_constraints_allow
~~~

In particular, **key scope is an upper bound and does not grant permissions exceeding the principal's**.

For example, Lan's key has scopes `REPORT_READ` and `REPORT_EXPORT`. If Lan's account currently only has `REPORT_READ`, then export must be denied. Conversely, if Lan's account has `REPORT_EXPORT` but the key only grants `REPORT_READ`, export is also denied.

For application/service accounts, "principal entitlements" may come from a machine identity policy store, not necessarily user RBAC.

A key belonging to `tenant-a` must not read tenant B's resources even with the same authority name `INVOICE_READ`. Tenant restrictions must originate from a trusted server-side principal/policy, **not** merely from a `tenantId` parameter requested by the client.

### Java 17+: standalone program

Create file **ApiKeyIdentityDemo.java**:

~~~java
import java.util.Set;

public class ApiKeyIdentityDemo {

    enum SubjectType { APPLICATION, SERVICE_ACCOUNT, ACCOUNT }

    record KeyPolicy(
            String keyId,
            SubjectType type,
            String subjectId,
            String ownerId,
            String tenantId,
            Set<String> keyScopes,
            Set<String> subjectEntitlements,
            boolean active) {
    }

    static String principal(KeyPolicy key) {
        return key.type() + ":" + key.subjectId();
    }

    static boolean allows(KeyPolicy key, String resourceTenant,
                          String action) {
        return key.active()
                && key.tenantId().equals(resourceTenant)
                && key.keyScopes().contains(action)
                && key.subjectEntitlements().contains(action);
    }

    public static void main(String[] args) {
        KeyPolicy app = new KeyPolicy(
                "key-app", SubjectType.APPLICATION, "app:checkout",
                "team:commerce", "tenant-a",
                Set.of("CATALOG_READ"),
                Set.of("CATALOG_READ", "ORDER_WRITE"), true);

        KeyPolicy service = new KeyPolicy(
                "key-service", SubjectType.SERVICE_ACCOUNT,
                "svc:billing-sync", "team:finance", "tenant-a",
                Set.of("INVOICE_WRITE"), Set.of("INVOICE_WRITE"), true);

        KeyPolicy account = new KeyPolicy(
                "key-account", SubjectType.ACCOUNT, "user:lan",
                "user:lan", "tenant-a",
                Set.of("REPORT_READ", "REPORT_EXPORT"),
                Set.of("REPORT_READ"), true);

        KeyPolicy revoked = new KeyPolicy(
                "key-revoked", SubjectType.ACCOUNT, "user:lan",
                "user:lan", "tenant-a",
                Set.of("REPORT_READ"), Set.of("REPORT_READ"), false);

        System.out.println("App principal = " + principal(app));
        System.out.println("Service principal = " + principal(service));
        System.out.println("Account principal = " + principal(account));
        System.out.println("App catalog read = "
                + allows(app, "tenant-a", "CATALOG_READ"));
        System.out.println("App order write = "
                + allows(app, "tenant-a", "ORDER_WRITE"));
        System.out.println("Service invoice write = "
                + allows(service, "tenant-a", "INVOICE_WRITE"));
        System.out.println("Account report export = "
                + allows(account, "tenant-a", "REPORT_EXPORT"));
        System.out.println("Cross-tenant report read = "
                + allows(account, "tenant-b", "REPORT_READ"));
        System.out.println("Revoked key report read = "
                + allows(revoked, "tenant-a", "REPORT_READ"));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ApiKeyIdentityDemo.java
java ApiKeyIdentityDemo
~~~

Exact stdout:

~~~text
App principal = APPLICATION:app:checkout
Service principal = SERVICE_ACCOUNT:svc:billing-sync
Account principal = ACCOUNT:user:lan
App catalog read = true
App order write = false
Service invoice write = true
Account report export = false
Cross-tenant report read = false
Revoked key report read = false
~~~

Each key is bound to **one** principal. `App order write = false` because the key scope lacks write permission, even though the app's entitlements may have it. `Account report export = false` because the account lost that permission. `Cross-tenant... = false` because the tenant does not match. The revoked key fails even though all other data remains valid.

This is a **post-credential-verification policy model**, not a complete API key handling library. A real system must also fetch principal/tenant status and permissions from a trusted source, check resource ownership, and handle permission update caches.

## 6. Provisioning keys with structured identity

An internal keys table might contain:

| Field | Purpose |
| --- | --- |
| `key_id` | Public identifier used for lookup/audit |
| `secret_digest` / `secret_mac` | Secret verification digest, avoiding plaintext storage |
| `subject_type` | APPLICATION, SERVICE_ACCOUNT, or ACCOUNT |
| `subject_id` | Immutable ID of the app/service/account |
| `owner_id` / `created_by` | Governance and traceability |
| `tenant_id` / `environment` | Organization and deployment partitioning |
| `allowed_scopes` | Upper bound of key permissions |
| `status` / `created_at` / `expires_at` | Lifecycle management |
| `revoked_at` / `last_used_at` | Revocation, operations |
| `rotation_group_id` | Links old/new credentials if a rotation policy exists |

Metadata might look like this:

~~~yaml
keyId: ak_7c82d1
subjectType: SERVICE_ACCOUNT
subjectId: svc:billing-sync
ownerId: team:finance-platform
tenantId: tenant-a
environment: production
allowedScopes:
  - INVOICE_READ
  - INVOICE_WRITE
status: ACTIVE
expiresAt: "2027-01-01T00:00:00Z"
~~~

This is illustrative data. **Never create an Authentication solely from a public keyId/metadata before checking the secret.** The `subject_id` field is a server-assigned identity; do not take it directly from a client-chosen header or body.

If an account is deleted/disabled, policy must decide whether active keys may continue to be used. For personal keys, they typically must be disabled along with the account; for service keys, **administrative ownership** can be transferred to a new team while preserving the service principal, provided the process is approved and audited.

## 7. Generating and storing secrets securely

Use a cryptographic random number generator such as `SecureRandom` to generate keys with high entropy (e.g., 256 bits). It can be formatted as:

~~~text
ak_live_<public-id>.<random-secret>
~~~

The prefix and public-id help classify/look up records, **not as proof of authentication**. The random-secret part is the actual secret. Distinct IDs per environment are needed; production keys must not be reused in staging/dev.

Workflow:

1. The server generates a unique public key ID and a cryptographically random secret.
2. Store a digest of the high-entropy secret (SHA-256) or HMAC-SHA-256 with a pepper protected outside the database, along with metadata.
3. Display the raw secret **once** to the client over a secure channel; do not put it in logs, traces, URLs, or unprotected emails.
4. When a request arrives, check format and length limits, look up the record by ID, recompute the digest/MAC, and compare in constant time on the digest bytes.
5. Check status, expiry, principal, tenant, scope, and resource policy before accepting the request.

For sufficiently strong random secrets, a fast cryptographic digest can be appropriate because offline brute force is impractical. User-chosen passwords typically have low entropy and thus require slow password hashers (Argon2/bcrypt/scrypt) under a separate policy. Do not use timestamps, usernames, or regular random generators as API keys.

Standalone Java 17+ example generating a secret **without printing the secret**:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public class ApiKeySecretDemo {
    public static void main(String[] args) {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);

        System.out.println("Secret bytes = " + secret.length);
        System.out.println("Encoded characters = " + encoded.length());
        System.out.println("URL-safe = "
                + encoded.matches("[A-Za-z0-9_-]+"));
    }
}
~~~

Run:

~~~bash
javac ApiKeySecretDemo.java
java ApiKeySecretDemo
~~~

Exact stdout:

~~~text
Secret bytes = 32
Encoded characters = 43
URL-safe = true
~~~

The value of `encoded` is not printed to avoid accidentally putting a secret into terminal logs. This program only demonstrates secret generation; a real system needs IDs, a database, digest/MAC, TTL, auditing, and an issuance workflow.

Compare digest bytes using the built-in API:

~~~java
boolean accepted = java.security.MessageDigest.isEqual(
        computedDigestBytes,
        storedDigestBytes);
~~~

This is an **illustrative code snippet**; both variables must be digest byte arrays produced with the same algorithm, not raw passwords. Constant-time comparison only addresses one small risk; rate limiting brute-force attempts, access lockouts, and error messages that do not leak which keys exist are still needed.

Prefer passing keys via **headers over HTTPS**, never in query strings because URLs frequently leak into access logs, browser history, referrers, proxies, and APMs. Headers carrying keys must also be redacted in logs/tracing. Secrets embedded in public frontends/mobile apps must not be considered trustworthy secrets.

## 8. Mapping an API key to a Spring Security principal

Spring Security uses `Authentication` to represent the principal and authorities. In an API key authentication application, a structured principal might look like:

~~~text
ApiPrincipal
    type        = SERVICE_ACCOUNT
    subjectId   = svc:billing-sync
    tenantId    = tenant-a
    keyId       = ak_7c82d1
~~~

After verifying the key and policy, the server can create an authenticated `Authentication` without retaining the raw secret as credentials. Authorities like `INVOICE_READ` and `INVOICE_WRITE` must be computed from **server-side policies**, not from a client-supplied `X-Scope` header.

### 8.1. Illustrative filter for Servlet

File **ApiKeyAuthenticationFilter.java** uses Spring Boot 3.x / Spring Security 6.x with the Jakarta Servlet API; it can be placed into an appropriate project. The `Verifier` interface is the contract for the key store and policy system: it must be implemented by a secure service.

~~~java
package demo.apikey;

import java.io.IOException;
import java.util.Enumeration;
import java.util.List;
import java.util.Optional;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

    public record ApiPrincipal(
            String type, String subjectId, String tenantId, String keyId) {
    }

    public record VerifiedKey(
            ApiPrincipal principal, List<GrantedAuthority> authorities) {
    }

    @FunctionalInterface
    public interface Verifier {
        Optional<VerifiedKey> verify(String rawKey);
    }

    private final Verifier verifier;

    public ApiKeyAuthenticationFilter(Verifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders("X-API-Key");
        if (!values.hasMoreElements()) {
            chain.doFilter(request, response);
            return;
        }

        String raw = values.nextElement();
        if (raw == null || raw.isBlank() || values.hasMoreElements()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        Optional<VerifiedKey> verified = verifier.verify(raw);
        if (verified.isEmpty()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        VerifiedKey result = verified.get();
        var authentication = new UsernamePasswordAuthenticationToken(
                result.principal(), null, result.authorities());

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Security explanation:**

- Missing header: the filter forwards the request; the authorization layer must require Authentication for API-key-only endpoints.
- Malformed header or failed verification: returns 401, **never** constructs an "anonymous-admin" principal.
- `Verifier.verify` must check the raw secret, key status, subject, and policy. The `VerifiedKey` result contains only server-verified principal/authorities.
- The `UsernamePasswordAuthenticationToken(principal, null, authorities)` constructor creates an authenticated object. Use it only **after** the verification step; never construct it from unverified key data.
- `SecurityContextHolder.createEmptyContext()` isolates the new context; `finally` clears the synchronous thread context.
- If the verifier encounters a database/KMS/timeout error, it must **fail closed**; do not return fallback permissions. This filter snippet does not cover async Servlets, gateway integration, distributed tracing, or a real verifier implementation.

This is code for **Spring Security Servlet**. Do not copy synchronous `OncePerRequestFilter` and `SecurityContextHolder` directly to WebFlux; the reactive stack uses `SecurityWebFilterChain`, `ReactiveAuthenticationManager`, and Reactor Context.

### 8.2. Restricting the filter chain and permissions

File **ApiSecurityConfig.java**:

~~~java
package demo.apikey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutFilter;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            ApiKeyAuthenticationFilter.Verifier verifier)
            throws Exception {

        return http
                .securityMatcher("/api/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((request, response, ex) ->
                                response.sendError(401)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                        .hasAuthority("CATALOG_READ")
                        .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                        .hasAuthority("INVOICE_WRITE")
                        .anyRequest().denyAll())
                .addFilterAfter(
                        new ApiKeyAuthenticationFilter(verifier),
                        LogoutFilter.class)
                .build();
    }
}
~~~

This is a Servlet configuration class in Spring Boot and **does not run standalone with `javac`**. It requires a bean implementing `ApiKeyAuthenticationFilter.Verifier`, the `spring-boot-starter-security` dependency, and actual API controllers. The filter is instantiated directly inside the security chain to avoid double registration via `@Component`/Servlet container.

- `securityMatcher("/api/**")` selects only API paths; if the app also has web pages, non-API endpoints must have another chain/protection.
- `SessionCreationPolicy.STATELESS` fits APIs that pass a key on every request.
- Disabling CSRF in the example is solely because this API branch **does not use cookies/browser sessions** for authentication. Do not apply this blindly to endpoints that use cookies.
- `hasAuthority` matches the exact permission string; `hasRole("ADMIN")` defaults to a different `ROLE_` prefix convention.
- `anyRequest().denyAll()` rejects API paths outside the declared policies.
- The filter should run before authorization. Using `AuthenticationManager`/`AuthenticationProvider` can separate the responsibilities of credential verification and Authentication creation more cleanly.

**Important:** HTTP-level authorities are not enough for multi-tenant systems. Controllers/services must also check access permissions on the **specific resource**.

## 9. Tenant and resource owner in business logic

Suppose `svc:billing-sync` belongs to tenant A and has authority `INVOICE_READ`. It sends:

~~~http
GET /api/invoices/INV-100 HTTP/1.1
X-API-Key: <tenant-a-secret>
~~~

If invoice `INV-100` belongs to tenant B, checking only the authority will leak data. Add the condition:

~~~text
principal.tenantId == invoice.tenantId
AND principal is allowed to access this invoice type
AND keyScopes contains INVOICE_READ
AND resource policy allows
~~~

Tenant checks can be implemented in the repository with a query containing both `invoiceId` and `tenantId`, avoiding loading another tenant's data and forgetting to check. The client must not be allowed to pick a tenant via a query parameter to bypass the restriction.

A resource may have an owner distinct from the tenant: an invoice belonging to `customer:42` in tenant A. When handling complex authorization, also check account/project/resource ownership, ACLs, or relationship policies. Do not assume a service account named "internal" is allowed to access all data.

## 10. Controlling credential and principal lifecycles

An API key should have clear states/transitions:

~~~text
CREATED
   |
   v
ACTIVE
   |--- ROTATING: old key + new key both valid within approved window
   |                     |
   |                     v
   |                 REVOKED old key
   |--- SUSPENDED
   |--- EXPIRED
   +--- REVOKED
~~~

For account-bound keys, account status changes must affect the key according to the designed SLA:

| Event | Policy to define |
| --- | --- |
| User changes password | Are personal keys revoked or still valid? Must be explicitly defined |
| User locked/disabled | Keys may be disabled along with the account |
| User leaves tenant | Key loses access to that tenant's resources |
| User loses role | Effective permissions of the key decrease accordingly |
| Service decommissioned | Revoke service key |
| Team changes manager | Transfer administrative owner, keep service principal if appropriate |
| Suspected secret leak | Revoke immediately, issue new credential, review audit logs |
| Key expires | Reject authentication and use rotation mechanism |

**Caching is a common trap:** if an API verifies keys using a 30-minute cached result, emergency revocation may not take effect immediately. Design TTL/invalidation or per-request lookup for sensitive status.

### Rotating without changing the principal

1. Create a new key with the **same principal** and re-approved permission policy.
2. Distribute the new secret via a secure secret manager/CI/CD.
3. Test the new credential and observe the public key ID in audit logs.
4. Keep both keys active briefly when transition overlap is needed.
5. Revoke the old key and verify no valid requests still use it.

The fact that old and new keys represent the same service does not mean the two secrets may be shared with all other services. **Key and principal have two separate lifecycles**: a secret can be rotated without changing the service identity.

## 11. Quota, billing, and auditing by key or by account?

API keys are often also used for rate limiting, billing, or analytics. Separate the purposes:

- **Rate limit by keyId**: limits a specific credential.
- **Rate limit by principalId**: limits total requests of an app/service/account across multiple keys.
- **Rate limit by tenant**: organization-level quota.
- **Billing owner**: the entity charged may be an organization or project, distinct from the actor principal.
- **Authorization**: decides resource access permissions; **never** inferred from whether a key has remaining quota.

If a service key is shared across multiple environments, auditing `keyId` only tells which credential was used, not which instance. Issue separate keys per deployment/environment or use workload identity to improve traceability.

Example audit log with secret omitted:

~~~json
{
  "requestId": "req-8f42",
  "keyId": "ak_service_01",
  "actorType": "SERVICE_ACCOUNT",
  "actorId": "svc:billing-sync",
  "tenantId": "tenant-a",
  "action": "INVOICE_WRITE",
  "decision": "DENY",
  "reasonCode": "RESOURCE_TENANT_MISMATCH"
}
~~~

Do not log raw `X-API-Key`, HMAC keys, secret digests, private keys, or Authorization headers containing credentials. Proxies/APMs, access logs, and exception messages need redaction rules.

If a gateway verifies the key and forwards principal info to the backend, the backend must trust only **internal headers from the authenticated gateway** and prevent Internet clients from spoofing those headers. The gateway-to-backend channel needs a trust mechanism and protection against direct access bypassing the gateway.

## 12. Comparing API keys with other authentication mechanisms

| Mechanism | Typical identity represented | Characteristics |
| --- | --- | --- |
| Opaque API key | App, service, or account per policy | Bearer secret, lifecycle self-managed by the system |
| OAuth2 client credentials | Machine-to-machine client/service | Time-limited/scoped token issued by authorization server |
| OAuth2 Authorization Code + OIDC | User and authorized client | Includes user login/consent workflow |
| JWT access token | Subject per verified issuer/audience/claims | Digitally signed, expiration; must verify issuer, audience, signature |
| mTLS client certificate | Machine/workload/device per PKI | Proves private key over TLS |
| Session cookie | Interactive browser user | Depends on cookies/sessions and CSRF policy |

An API key **does not turn into a JWT** merely because the string is sent in the `Authorization` header. If using Spring Security `oauth2ResourceServer().jwt()`, there must actually be a JWT issued and verified under the corresponding configuration. For self-issued opaque keys, use a verifier/key store or a system-supported token introspection mechanism.

When requirements demand user delegation, short-lived tokens, multiple downstream services, complex tenancy, or stronger workload identity proof, consider specialized protocols/infrastructure. API keys remain suitable for many simple integrations when scope, expiry, revocation, and auditing are properly managed.

## 13. Common mistakes

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Treating every key as the current user | Incorrect audits, blurred user/service boundary | Store `principalType` and `subjectId` explicitly |
| Letting the client send `userId`/`role` | Identity spoofing | Resolve principal/authorities on the server |
| Granting admin to every valid key | Key leak leads to broad access | Least privilege, scopes, and resource policies |
| Using one key across all tenants | Data leaks, hard to revoke | Bind key to tenant, check resource tenant |
| Using a public frontend key as a secret | Secret easily extracted | Appropriate mechanism for public clients |
| Storing plaintext secrets | Entire credential store exposed on DB breach | Digest/HMAC and secret lifecycle |
| Putting keys in URL/query | Logs and browser history leak secret | Header over HTTPS, redaction |
| Keys without expiry/revocation | Leaked keys remain valid too long | TTL, rotate, revoke |
| Key keeps permissions after account loses role | Bypasses account access governance | Intersect key scopes with current entitlements |
| Revoked key still passes via cache | Revocation does not take effect promptly | Invalidation or SLA-bounded TTL |
| Over-trusting gateway headers | Client spoofs authenticated actor | Trust gateway only over protected internal channel |
| Sharing one key across multiple actors | Impossible to tell who acted | Separate keys per app/service/tenant |
| Mutating `subjectId` of an issued key | Old credential silently becomes a new identity | Issue new key and log migration audit |

## 14. Testing representation semantics

Tests should cover credential, principal, and permission layers:

| Test | Expected result |
| --- | --- |
| Missing key to API-key-only endpoint | 401 |
| Wrong/expired/revoked key | No authenticated principal |
| Valid `APPLICATION` key | Principal type `APPLICATION`, matching app `subjectId` |
| Valid `SERVICE_ACCOUNT` key | Principal type `SERVICE_ACCOUNT`, matching service |
| Lan's `ACCOUNT` key | Principal is Lan's account but audit logs `authenticationMethod=API_KEY` |
| Client also sends `X-Acting-User: admin` | Does not change principal without verified delegation |
| Key scope lacks write action | 403 |
| Key has scope but principal lost permission | 403 |
| Tenant A key accesses tenant B | 403 or 404 per resource-existence protection policy |
| Disabled service principal | Key can no longer be used |
| Revoke one of two keys for same principal | Revoked key fails, remaining key works |
| Rotation during overlap window | Both approved keys work, then old key is invalidated |
| Database/key store outage | Fail closed, never auto-grant roles |
| Duplicate or oversized header | Rejected by validation |
| API gateway bypassed | Backend rejects forged headers |
| Log/APM contains raw key | Test detects it and requires redaction |

You can use MockMvc to test FilterChain/Authentication in Spring Boot Servlet, test repositories/key lifecycle with integration tests, and unit test scope/tenant policies separately. If the system relies on a gateway, test direct access paths to the backend to ensure identity cannot be spoofed.

## 15. Pre-deployment checklist

1. **Identity:** is the principal type `APPLICATION`, `SERVICE_ACCOUNT`, or `ACCOUNT`? Is the Subject ID stable/unique per tenant?
2. **Ownership:** who creates, manages, rotates, and revokes keys? Is the owner confused with the actor?
3. **Secrets:** does the key have high entropy, stored as digest/HMAC, and shown once? Is it protected in transit and logs?
4. **Permissions:** are `keyScopes`, `principalEntitlements`, tenant, and resource policies enforced simultaneously?
5. **Runtime:** does the verifier fail closed and grant `Authentication` only after verification? Is the filter chain properly scoped?
6. **Lifecycle:** do expiry, revocation, rotation, and disabled accounts take effect promptly?
7. **Audit:** are key ID, actor, tenant, resource, action, and decision logged without logging secrets?
8. **Delegation:** if acting on behalf of a user is required, is there a separate delegation mechanism in place?

Conclusion: **An API key authenticates a credential; the provisioning record and server-side policy determine whether that credential represents an application, a service, or an account.** Only after resolving the right principal and simultaneously checking scopes, entitlements, tenant, and resource policies may the system permit the operation. Never equate a valid key with an interactive user identity or default administrative privileges.

### Official references

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Security Filter Chain and Custom Filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html
- OWASP — Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
