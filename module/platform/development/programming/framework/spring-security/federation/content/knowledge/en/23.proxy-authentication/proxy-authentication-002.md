# RequestHeaderAuthenticationFilter and PreAuthenticatedAuthenticationProvider

## 1. The problem: proxy authenticates, application receives the verified identity

In the **Spring Security - federation** architecture, under the **Proxy Authentication** branch, users may sign in at an **identity-aware reverse proxy / access gateway** before the request reaches the Spring Boot application. The gateway may use OIDC, SAML, mTLS, Kerberos, or another enterprise authentication policy. After authenticating, the gateway sends an internal header, such as `X-Authenticated-User: alice@corp.example`, to the backend to report **who has been authenticated**.

Spring Security supports the **pre-authentication** model with two core components:

- **`RequestHeaderAuthenticationFilter`**: extracts the principal (typically a username) from an HTTP request header; extends `AbstractPreAuthenticatedProcessingFilter`. **It does not verify passwords, OIDC tokens, SAML signatures, or caller identity.**
- **`PreAuthenticatedAuthenticationProvider`**: receives the `PreAuthenticatedAuthenticationToken` from the filter, loads `UserDetails` and authorities via `AuthenticationUserDetailsService`, runs the configured account checks, and produces a Spring `Authentication`. **It likewise does not prove that the header was actually emitted by a trusted gateway.**

This design is safe **only when the entire trust boundary in front of Spring is enforced**: clients cannot attach/overwrite the header, the backend cannot be reached directly, the gateway authenticates every protected endpoint, the gateway → application channel is protected, and the application enforces **local account admission/authorization** before resource access.

> **Most critical invariant:** `X-Authenticated-User` **is not a self-verifying credential**. If an untrusted request can set `X-Authenticated-User: admin` and Spring treats it as an authenticated principal, that is a **complete identity spoofing vulnerability**, even though the application uses Spring Security.

This lesson covers the full flow, setter semantics and defaults, Servlet SecurityFilterChain configuration, stateless vs. stateful selection, missing-header behavior, spoofing controls, identity/authority mapping, a standalone Java 17 demo, plus a test matrix and operational checklist.

## 2. Trust boundary diagram

~~~text
Untrusted Internet / Browser
        |
        | GET /reports
        | Attacker-supplied header:
        | X-Authenticated-User: admin@corp.example
        v
+-----------------------------------------+
| Trusted Identity-Aware Gateway          |
| 1. Terminate TLS & authenticate request |
| 2. STRIP all client-supplied identity   |
|    headers and equivalent variants      |
| 3. Check IdP session, policy, context   |
| 4. If OK: WRITE NEW single header       |
|    X-Authenticated-User: alice@corp.example
| 5. If FAIL: reject, DO NOT forward      |
+-----------------------------------------+
        |
        | HTTPS / mTLS / private network
        | X-Authenticated-User: alice@corp.example
        v
+-----------------------------------------+
| Spring Boot application                 |
| RequestHeaderAuthenticationFilter       |
|  -> principal: alice@corp.example       |
|  -> PreAuthenticatedAuthenticationToken |
|  -> AuthenticationManager               |
|  -> PreAuthenticatedAuthenticationProvider
|  -> UserDetailsService                  |
|  -> AccountStatusUserDetailsChecker     |
|  -> local GrantedAuthority              |
|  -> SecurityContext for request         |
|  -> authorization: tenant / resource    |
+-----------------------------------------+
        |
        +--> 200 if both identity and permissions are valid
        +--> 403 if missing principal/permissions per policy
~~~

The **gateway** is where upstream authentication happens; the **Spring pre-auth filter/provider** is the layer that **accepts and integrates** the external result into the `Authentication`/`GrantedAuthority` model. If either side is missing, the system can either reject legitimate users or admit spoofed attackers.

### 2.1. Distinguishing evidence, attributes, and permissions

| Data | Issued by whom? | What does it prove? | What does it not yet prove? |
| --- | --- | --- | --- |
| OIDC/SAML/mTLS session at gateway | Trusted Gateway/IdP | The user passed upstream authentication per contract. | That the local app account is still active; or has permission on resource X. |
| `X-Authenticated-User` header | Gateway **after** strip/overwrite | The gateway asserts the corresponding principal. | Does not prevent spoofing on its own if clients can reach the backend directly. |
| Initial `PreAuthenticatedAuthenticationToken` | Spring filter | A principal has been asserted externally. | The token has not yet had user/details loaded or account checks run by the provider. |
| `UserDetails` | Application directory/DB | Local user/authorities/status as of lookup time. | Does not guarantee the header came from the gateway if network trust is broken. |
| Completed `Authentication` | Spring provider | The application accepted the principal and authorities per policy. | Does not automatically grant access across every tenant/resource. |
| HTTP session / SecurityContext | Spring repository | May retain the result across requests, depending on configuration. | Does not automatically reflect immediate gateway logout/revocation. |

### 2.2. This is not "authentication via a password header"

By design, `RequestHeaderAuthenticationFilter` **does not need the user's password**, and by default returns the string **`"N/A"`** for credentials. This is intentional because the gateway already authenticated upstream. Putting a password, access token, or JWT into a header named `credentialsRequestHeader` hoping the provider will verify it is the **wrong model**. If you want the backend to verify a bearer JWT itself, use **OAuth2 Resource Server**; if Spring itself should perform OIDC login, use **`oauth2Login()`**; for SAML Web SSO, use SAML2 support. Pre-auth does not replace those validators.

## 3. RequestHeaderAuthenticationFilter: API, defaults, and risks

Class:

~~~java
org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter
~~~

Extends:

~~~java
org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter
~~~

Behaviors defined in the Javadoc:

| Component | Value / behavior | Security impact |
| --- | --- | --- |
| `principalRequestHeader` | Default **`SM_USER`** (CA SiteMinder compatibility). | If the gateway sends a different header, configure it explicitly; never auto-guess from arbitrary headers. |
| `setPrincipalRequestHeader(String)` | Selects the username header, e.g. `X-Authenticated-User`. | Header name does not create trust; requires gateway stripping and signature/transport trust per architecture. |
| `getPreAuthenticatedPrincipal(request)` | Reads `request.getHeader(principalRequestHeader)`. | **Does not verify** the value and does not normalize namespace/tenant for you. |
| `exceptionIfHeaderMissing` | Default **`true`**: throws `PreAuthenticatedCredentialsNotFoundException` if header is missing. | Actual response depends on how the exception is handled; must test 401/403/5xx. |
| `setExceptionIfHeaderMissing(false)` | Allows returning `null` when principal is missing. | Safe only if the chain **still denies** anonymous and has no accidental auth fallback. |
| `credentialsRequestHeader` | Unset by default. | If set, provider reads the header value; **does not verify** it. |
| `getPreAuthenticatedCredentials(request)` | Defaults to returning the dummy string **`N/A`**. | Provider requires non-null credentials; dummy is not a verified password. |
| `setAuthenticationManager(...)` | Inherited from base filter. | Must be wired to the appropriate provider. |
| `setCheckForPrincipalChanges(...)` | By default does not continuously check against the principal already in session. | If using sessions and the header can change, review principal-change checks/invalidations. |
| `setContinueFilterChainOnUnsuccessfulAuthentication(...)` | Default **`true`** when provider throws `AuthenticationException`. | If another provider exists in the same chain, may trigger an unintended fallback. |
| `setSecurityContextRepository(...)` | Allows choosing where Authentication is persisted. | Affects stale sessions and ability to revoke on gateway logout. |

### 3.1. Default header SM_USER

A historical SiteMinder deployment might send:

~~~http
GET /reports HTTP/1.1
Host: portal.example.org
SM_USER: alice
~~~

If your gateway uses:

~~~http
X-Authenticated-User: alice@corp.example
~~~

then you need:

~~~java
RequestHeaderAuthenticationFilter filter =
        new RequestHeaderAuthenticationFilter();
filter.setPrincipalRequestHeader("X-Authenticated-User");
~~~

**There is no magic auto-discovery:** the filter does not know whether `X-Forwarded-User`, `X-Remote-User`, `X-User`, or `SM_USER` from any gateway is "trusted"; it reads **only the single configured header name**. The header name must belong to the **deployment contract** between gateway and backend, along with canonicalization logic, missing/duplicate handling, and lifecycle rules.

### 3.2. Missing header: true vs. false, yet neither is a full policy alone

Default:

~~~java
filter.setExceptionIfHeaderMissing(true);
~~~

If the header is missing, `getPreAuthenticatedPrincipal` throws `PreAuthenticatedCredentialsNotFoundException`. In the base filter's source code, extracting the principal occurs **before** the `try/catch` block wrapping the `AuthenticationManager` call; therefore **do not assume it will automatically return 403 under every filter ordering and error handler**. Test the actual HTTP status; if an exception escapes the filter untranslated, the container may turn it into a 5xx.

Another intentional configuration:

~~~java
filter.setExceptionIfHeaderMissing(false);
~~~

The filter can proceed if the principal is `null`. **This is not an instruction to "let anonymous in"!** If the entire chain uses `anyRequest().authenticated()`, has no fallback, and uses a stateless context, a request without the header is still rejected (typically 403 via `Http403ForbiddenEntryPoint`). However, if the same chain also permits form login, a stale session, or anonymous access, lacking the header can yield different behavior.

**Practical recommendation:** have the **gateway block unauthenticated requests before forwarding**, while Spring maintains an explicit deny policy; do not expect the backend to safely rescue a gateway design that "sometimes sends a header and sometimes does not".

### 3.3. Why do credentials default to N/A?

`AbstractPreAuthenticatedProcessingFilter` builds an authentication request with **principal and credentials**. `PreAuthenticatedAuthenticationProvider` normally ignores the request if either principal **or** credentials is `null` (or throws if `throwExceptionWhenTokenRejected` is enabled). `RequestHeaderAuthenticationFilter` therefore supplies the dummy value `N/A` when `credentialsRequestHeader` is not configured.

**Do not interpret N/A as a password.** It merely satisfies the token shape contract. Putting a "shared secret" into a credentials header likewise does not create secure proxy authentication, because this provider **does not compare secrets**. If you need to prove a request came from the gateway, use **mTLS/network isolation and gateway policy**, or a signed token verified by a real backend validator rather than relying on dummy credentials.

## 4. PreAuthenticatedAuthenticationProvider: exact role

Class:

~~~java
org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider
~~~

This is a Spring `AuthenticationProvider` dedicated to handling `PreAuthenticatedAuthenticationToken`. Unlike `DaoAuthenticationProvider`, it **does not check passwords**; it trusts the assumption that the pre-authentication source performed primary authentication.

A typical pipeline:

~~~text
PreAuthenticatedAuthenticationToken(
  principal = "alice@corp.example",
  credentials = "N/A",
  authenticated = false
)
    |
    v
PreAuthenticatedAuthenticationProvider
  1. supports(PreAuthenticatedAuthenticationToken)
  2. Reject/ignore null principal or null credentials
  3. AuthenticationUserDetailsService.loadUserDetails(token)
  4. UserDetailsChecker.check(userDetails)
  5. Build authenticated PreAuthenticatedAuthenticationToken
     with UserDetails + GrantedAuthorities
    |
    v
SecurityContextHolder
    |
    v
Authorization decisions for application/resource
~~~

**The provider does not know** how the reverse proxy performed OIDC/SAML/mTLS login, whether the request traversed a trusted gateway, or whether an attacker injected the header onto the network. That belongs to the **deployment boundary**.

### 4.1. Key setters and defaults

| API | Effect | Notes |
| --- | --- | --- |
| `setPreAuthenticatedUserDetailsService(...)` | Configures the service loading `UserDetails` from the Authentication request. | **Essential**; without it, account/authorities cannot be resolved per policy. |
| `setThrowExceptionWhenTokenRejected(true)` | Converts null principal/credentials into `BadCredentialsException` instead of returning `null`. | Does not prove header origin; only changes input handling. |
| `setUserDetailsChecker(...)` | Selects how `UserDetails` status is validated. | Defaults to **`AccountStatusUserDetailsChecker`**; avoid disabling it and bypassing DISABLED/LOCKED. |
| `setGrantedAuthoritySupplier(...)` | Supplies additional authorities per configuration in versions with this API. | Never grant strong privileges by default or treat every header role as trusted. |
| `supports(...)` | Supports only `PreAuthenticatedAuthenticationToken`/subclasses. | Does not process `UsernamePasswordAuthenticationToken` like a password provider. |

Per recent source code, the provider calls `userDetailsChecker.check(userDetails)` **after** the loader returns user info, then constructs an authenticated token with those authorities. This checks states such as locked/disabled against the loaded data. Still, **business permissions, tenant, ownership, and account status updates occurring between requests** require explicit application-level policy.

### 4.2. UserDetailsByNameServiceWrapper

`AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` receives an **Authentication token**, not merely a username String. If you already have a traditional `UserDetailsService`, Spring provides:

~~~java
new UserDetailsByNameServiceWrapper<
        PreAuthenticatedAuthenticationToken>(userDetailsService)
~~~

This class delegates loading to `userDetailsService.loadUserByUsername(authentication.getName())` semantically. It fits when the principal emitted by the gateway **is already the exact, unique account key in the application**.

If the gateway serves multiple IdPs/tenants, you may need a custom `AuthenticationUserDetailsService` to map:
- `verifiedIssuer` + `verifiedSubject` from a verifiable **trust contract**.
- Tenant resolved independently by the system.
- Local account ID/disabled status.
- Authorities approved for **this specific application**.

**Do not use bare email as the merge key across multiple issuers** when emails can change or be recycled. Avoid ambiguous realm/domain stripping; if the gateway sends only `alice` and two identity systems share usernames, the trust contract itself must resolve collisions.

### 4.3. PreAuthenticatedGrantedAuthoritiesWebAuthenticationDetails and group roles

Spring offers classes such as `PreAuthenticatedGrantedAuthoritiesWebAuthenticationDetails` and `PreAuthenticatedGrantedAuthoritiesUserDetailsService` to consume pre-auth authorities attached to authentication details. They are useful **only when the source of authorities is trustworthy and governed by a strict contract**.

Dangerous example:

~~~text
Untrusted request:
  X-Authenticated-User: alice
  X-Role: ADMIN

Backend mapper:
  any X-Role -> ROLE_ADMIN
~~~

An attacker has escalated privileges if that request passes through or reaches the backend directly. Even when the gateway genuinely emits `groups=admins`, an IdP group is **not by default** `ROLE_ADMIN` in the portal. Use a local entitlement service and allowlisted mapping scoped by issuer, tenant, and app. For admin/finance actions, enforce **deny precedence** when a local account is locked or permissions are revoked.

## 5. Most dangerous failure: header spoofing

### 5.1. Exploitation scenario when the backend is directly reachable

Suppose an attacker discovers a pod/service address via an overlooked LB or public IP:

~~~http
GET /admin/users HTTP/1.1
Host: backend.example.org
X-Authenticated-User: admin@corp.example
~~~

If the backend uses `RequestHeaderAuthenticationFilter` and `PreAuthenticatedAuthenticationProvider` with a local directory containing `admin@corp.example`, the request can be treated as admin **without knowing a password or holding an IdP session**. Having a `UserDetailsService` does not fix this bug, because the loader simply looks up the account and roles of whatever principal the caller claimed.

**Proper defense:** the backend accepts connections exclusively from authorized gateway/service-mesh identities (mTLS, network ACL, Kubernetes NetworkPolicy, security groups), with no NodePort/secondary ingress/port-forward/public route bypass; the gateway must strip client-supplied headers before emitting verified values.

### 5.2. Scenario where the gateway forwards a forged header

A misconfigured proxy:

~~~text
client -> X-Authenticated-User: admin@corp.example
gateway -> authenticate alice
gateway -> proxy_pass with ORIGINAL client header
backend -> sees admin@corp.example
~~~

Even when the gateway genuinely authenticates `alice`, **failing to overwrite** the header lets the attacker use the gateway as a relay for a self-asserted identity. The header must be **stripped at the trust ingress and re-emitted solely from the verified principal**, not "added only if the client did not send one".

Protections must cover variants:
- Case-insensitive HTTP header names.
- Hyphens and underscores if proxies/frameworks normalize names.
- Duplicate headers, multi-values, header folding, whitespace.
- HTTP/2 → HTTP/1.1 translation and path routing.
- Other headers serving the same role such as `X-User`, `X-Remote-User`, `SM_USER`, `X-Auth-Request-User`.
- Identity headers added by another internal CDN/LB that was not authenticated.

**Do not strip only one header name at one ingress while allowing requests to reach the service through a second ingress with different rules.**

### 5.3. Why X-Forwarded-For does not prove a trusted request

`X-Forwarded-For`, `X-Real-IP`, `Forwarded`, and `X-Forwarded-Proto` are **networking metadata**, not identity credentials. Clients can send them themselves if proxies do not govern them. `ForwardedHeaderFilter` or trusted-proxy settings help keep URLs/schemes accurate, yet **do not verify that the principal header was emitted by gateway authentication**.

`request.getRemoteAddr()` can identify the nearest hop, yet in meshes/LBs that alone does not prove the gateway authenticated the user. **Trusting caller identity** requires mTLS/service identity/network policy + controlled routing + header sanitization; never substitute an IP copied from an HTTP header.

## 6. Contract between gateway and Spring: questions that must be answered

Before writing Java config, both sides must agree on:

| Category | Must be explicitly specified |
| --- | --- |
| **Upstream authenticator** | Which OIDC OP/SAML IdP/mTLS/enterprise SSO authenticates users, trusted issuers, MFA/assurance if required. |
| **Request coverage** | Which paths/hosts/methods require authentication; whether admin/actuator/WebSocket/gRPC shortcuts exist. |
| **Identity header** | Exact name, format, max length, charset, case folding, duplicate handling, null/empty rules. |
| **Identity namespace** | Whether subject is an opaque ID or realm-qualified username, and whether issuer and tenant must accompany it. |
| **Sanitization** | Gateway strips all incoming identity headers and writes exactly one from the verified principal. |
| **Channel trust** | TLS/mTLS or network isolation, gateway service identity, firewall/NetworkPolicy blocking direct backend access. |
| **Lifecycle** | Upstream logout, session expiry, revocation, refresh, and edge cache TTL; whether every request carries the header. |
| **Authorization** | Local user status, authorities, tenant, resource owner; whether admin role mapping requires approval. |
| **Error contract** | Gateway failure → 401/403/redirect; backend missing header → deny; upstream timeout → fail closed. |
| **Observability** | Event correlation IDs, hashed identity refs, no raw tokens/headers in logs. |
| **Deployment/testing** | Ingress paths, health endpoints, failover, chaos tests blocking mTLS and direct service access. |

### 6.1. Choosing a stable principal format

There are at least three options:

**A. Domain-qualified username**, e.g. `alice@corp.example`: easy to look up in a local directory, yet may change or be reused. Use only if the organization guarantees sufficient identity immutability/uniqueness.

**B. Opaque stable ID**, e.g. `employee-uuid-7cf1`: resilient against renames given good directory mapping, yet requires namespace/issuer to prevent cross-tenant collisions.

**C. Composite issuer + sub**, e.g. `corp-op|sub-pairwise-091`: explicit namespace, though it requires canonicalization rules and delimiter-collision protection. Better yet, send two separate fields **only if the gateway authenticates and emits both** and the backend **binds them as a single attested identity assertion**; never take tenant from a browser-supplied header.

`UserDetailsByNameServiceWrapper` works conveniently for A or a canonicalized composite key. With multiple issuers, a custom `AuthenticationUserDetailsService` is usually better suited to look up by `(issuer, subject, tenant)`, yet **never concatenate strings from untrusted headers and query the DB**.

### 6.2. "Authoritative" vs. "transient" attributes

If the gateway emits `X-Authenticated-User` after authentication, that is a gateway assertion. If it also emits `X-Groups` or `X-Email`, the backend must know:
- Does the attribute come from HR/LDAP/IdP or user self-edit?
- When was it updated, and is it still valid?
- Where do tenant/group namespaces live?
- Is the attribute for display only or authorized for access control?
- When the source is unavailable or the claim is missing, should the app deny, hide, or fall back to a local source?

Never assign `ROLE_ADMIN` merely because `X-Groups: admin`. **Authentication ≠ authorization**.

## 7. Spring Security 6+ / Java 17 configuration: a stateless pre-auth chain

The following example intentionally enforces a **strict assumption**: **all requests reaching the application in the trust zone must come via the gateway**; the gateway **authenticates or rejects before forwarding** and strips/overwrites identity headers, while Spring **does not persist Authentication across requests**. When the header is missing, Spring denies via authorization; there is no form login fallback in the same chain.

File `src/main/java/example/security/GatewayPreauthConfig.java`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class GatewayPreauthConfig {

    @Bean
    SecurityFilterChain gatewaySecurityFilterChain(
            HttpSecurity http, UserDetailsService localUsers)
            throws Exception {

        // Provider: loads user/authorities; does not verify header source.
        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();

        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<
                        PreAuthenticatedAuthenticationToken>(localUsers));
        provider.setThrowExceptionWhenTokenRejected(true);

        // Do not register filter as a second Servlet @Bean:
        // only add this instance to the Spring Security FilterChain.
        RequestHeaderAuthenticationFilter preAuth =
                new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Authenticated-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(new ProviderManager(provider));

        // Same stateless choice for both filter and HttpSecurity.
        NullSecurityContextRepository noSession =
                new NullSecurityContextRepository();
        preAuth.setSecurityContextRepository(noSession);

        http
            .securityContext(sc -> sc.securityContextRepository(noSession))
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
            .addFilterBefore(
                preAuth, UsernamePasswordAuthenticationFilter.class);

        // Do not enable formLogin/httpBasic in this pre-auth chain.
        // Default CSRF is not disabled in this example.
        return http.build();
    }
}
~~~

**Scope of this snippet:** this is configuration **for a Spring Boot Servlet project**, requiring `spring-boot-starter-security` and `spring-boot-starter-web` dependencies, a **real** `UserDetailsService` bean (database/LDAP/local directory), a hardened gateway, and Spring bootstrapping. It is **not a standalone Java SE program compiled with `javac`**. Additionally, Jakarta Servlet/Spring Security compatibility must be confirmed for your project version.

### 7.1. Why does this configuration not create a Bean for the filter?

Spring Boot can **automatically register any Servlet Filter `@Bean` into the container filter chain**. If you also call `http.addFilterBefore(filter, ...)` with the same bean, the filter can run **twice** (once outside Spring Security's FilterChainProxy, once inside the chain), causing out-of-order identity context or hard-to-diagnose bugs.

The pattern above instantiates `new RequestHeaderAuthenticationFilter()` **inside the SecurityFilterChain configuration method**, without registering a separate Servlet Filter Bean. If your organization wants the filter as a bean for DI/metrics, intentionally **disable container auto-registration** via `FilterRegistrationBean#setEnabled(false)` while still adding it to the right security chain. Never assume both mechanisms work cleanly together by default.

### 7.2. Why use stateless?

`NullSecurityContextRepository` **does not store** `Authentication` in HttpSession. Subsequent requests to be accepted must carry the gateway's assertion **in that request**. As a result:
- Gateway terminates the session/upstream stops sending the header → Spring does not keep user privileges from a prior session.
- Gateway returns a different principal → Spring authenticates under the new principal in the new request.
- No Spring `JSESSIONID` cookie acts as a parallel identity source alongside the gateway.
- Easy to test: missing/forged headers are blocked at the gateway, or denied at the backend by the chain.

**However:** `STATELESS` **does not guarantee** CSRF safety on its own. If the browser uses a gateway SSO cookie and the gateway automatically attaches the identity header on every request, that cookie is an **ambient credential**. A malicious site can trigger state-changing requests via the browser; appropriate **CSRF/origin defenses** are still required. The example leaves default CSRF enabled; in real API/browser apps configure a CSRF token repository and CORS matching the client type, test POST/PUT/DELETE, and do not call `csrf.disable()` out of habit.

If an HTML login UI and session-based app are needed, you can choose **stateful**, provided SSO lifecycle and logout propagation are explicitly designed (see section 8); never run Spring sessions and gateway identity side by side without knowing which source wins.

### 7.3. Why is `exceptionIfHeaderMissing(false)` still safe in this model?

1. **The gateway** does not forward unauthenticated requests.
2. The Spring filter receives a request missing the header (if a gateway/deployment bug occurs) and **creates no Authentication**.
3. `NullSecurityContextRepository` **does not restore an old authenticated session**.
4. The chain's `anyRequest().authenticated()` and `Http403ForbiddenEntryPoint` **reject** anonymous requests.
5. No formLogin/httpBasic/provider fallback exists in the chain to accept another identity outside the contract.

**If any of these assumptions does not hold, the conclusion no longer holds either.** For instance, setting `/admin/**` to `permitAll()` or letting browsers connect directly to the backend breaks protection; you cannot blame `setExceptionIfHeaderMissing(false)` in isolation. Where an API needs status code 401 instead of 403, an appropriate entry point can be used, changing only the error response and **not the trust model**.

### 7.4. Why not set `setContinueFilterChainOnUnsuccessfulAuthentication(false)` casually?

`AbstractPreAuthenticatedProcessingFilter` by default **continues the filter chain** when `AuthenticationManager` throws `AuthenticationException` after clearing SecurityContext. This is safe in a **stateless, deny-all-otherwise chain with no other auth mechanisms** like the snippet; anonymous gets rejected at the end. Yet if the chain includes formLogin or an alternative provider, that default could open an unintended authentication path.

Setting `false` causes the exception to be **thrown out of the pre-auth filter**; depending on filter order and exception handlers, the exception may bypass `ExceptionTranslationFilter` and become a 5xx if no proper failure handler exists. **Do not claim `false` automatically returns HTTP 403.** If fail-fast behavior is needed, build a tested failure handler/error mapping and separate security chains for independent auth modes.

### 7.5. Providing a real UserDetailsService

The bean can be backed by an application service repository; example business flow:

~~~text
loadUserByUsername("alice@corp.example"):
  find local identity binding by canonical principal
  if not found -> UsernameNotFoundException
  load local account status
  if DISABLED/LOCKED -> UserDetails reflects status
  load approved authorities for this app + tenant
  return UserDetails with stable username and authorities
~~~

For production, you need **stable local mapping keys**, an entitlements source, a revocation policy, caching, and protection against account takeover when usernames/emails change. Never create an `InMemoryUserDetailsManager` containing demo admins in production just to log in quickly.

**The provider includes `AccountStatusUserDetailsChecker` by default**, yet an account whose permissions change while a request is in flight still requires policy-driven authorization/resource checks; never treat "UserDetails loaded once" as an unbounded grant.

## 8. If the application needs HttpSession: lifecycle risks

Some server-rendered applications use sessions and want to **retain the pre-auth result** across requests. The base filter can use `HttpSessionSecurityContextRepository`, and normally when an `Authentication` already exists, the filter **skips** re-authenticating new requests by default. This risks keeping stale privileges after a user logs out of the gateway or the gateway switches users while Spring's cookie is still sent.

### 8.1. Setters to examine

- `setCheckForPrincipalChanges(true)`: forces comparing the incoming principal against `Authentication.getName()`, re-authenticating on mismatch.
- `setInvalidateSessionOnPrincipalChange(true)`: default when principal-change checking is enabled can invalidate the session on change, reducing the risk of leaking user A's data to user B.
- `setSecurityContextRepository(...)`: controls when/how Authentication is persisted.
- `setRequiresAuthenticationRequestMatcher(...)`: limits pre-auth processing to the intended request scope.
- Configure `SessionAuthenticationStrategy` and session fixation protection per Spring Security version.
- Gateway logout/revocation and local session flows: if the gateway logs out while the Spring session remains, define proper conditions to **invalidate/revoke the session**.

**Warning:** `checkForPrincipalChanges` only addresses principal comparison when requests pass through the filter; it does **not automatically** detect that the upstream session was revoked if headers remain stale, nor does it refresh local account status/permissions freshness. With empty/missing headers, behavior also depends on `exceptionIfHeaderMissing`, matchers, and the current SecurityContext; write integration tests instead of guessing.

### 8.2. Example of two requests with different identities

~~~text
Request 1:
  Gateway authenticated alice
  X-Authenticated-User: alice@corp.example
  App stores SecurityContext (alice) in JSESSIONID=J1

Request 2:
  Same JSESSIONID J1 but Gateway now authenticates bob
  X-Authenticated-User: bob@corp.example

Unsafe if filter skips because existing session auth:
  Application still uses alice identity

Required semantics:
  detect principal change
  invalidate old app session where appropriate
  create authentication for bob only after trusted header
  do not inherit alice's local authorities/cache
~~~

When two users share a device/browser, this scenario is especially dangerous. **Stateless pre-auth on every request** is simpler whenever the gateway reliably attaches the real principal on every request. Otherwise, design verifiable identity/session binding and timeouts.

### 8.3. Local logout does not terminate upstream SSO

If the application's local `/logout` destroys `JSESSIONID`, while the gateway still holds an SSO cookie and authenticates the browser, the next request will receive `X-Authenticated-User` again and may immediately log back in. This is **not automatically a Spring bug**. If the UI promises "global logout", log out at the gateway/IdP using the proper protocol, and revoke app sessions and API tokens accordingly. Never run local logout alone and claim the upstream session is gone.

## 9. Authorization: UserDetails, GrantedAuthority, and tenants

`PreAuthenticatedAuthenticationProvider` loads `UserDetails` and assigns `GrantedAuthority` from the configured service. This helps separate:

- **Upstream authentication**: Gateway authenticated `alice` under the trust agreement.
- **Local admission**: Does `alice`'s Spring account exist, is it ACTIVE, and is it not LOCKED/DISABLED?
- **Local authorization**: Does `alice` hold `reports:read`, `users:manage`, or `payments:approve` on the right tenant/resource?

### 9.1. Two role sources must be clearly reconciled

Suppose the gateway emits:

~~~http
X-Authenticated-User: alice@corp.example
X-Authenticated-Groups: all-staff,finance-viewers
~~~

The application should consume only groups whose **source, namespace, freshness, and release policy are attested by the gateway**; it still needs an **allowlist** mapping them to app authorities. Policy pattern:

~~~text
Gateway:
  authenticated identity = (trusted-issuer, stable-subject)
  upstream groups = known source + timestamp + namespace

App:
  map verified identity -> local account
  enforce account ACTIVE
  map approved group IDs -> candidate app roles
  intersect with local entitlements and tenant constraints
  deny revoked/locked roles
  enforce resource-owner and action policy
~~~

Never convert `X-Groups: admin` into `ROLE_ADMIN` arbitrarily. A partner's `admins` group may hold zero authority in your finance application. **Local deny overrides upstream groups** under a well-designed policy.

### 9.2. Method security

Spring service example:

~~~java
package example.reports;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports:read')")
    public String readReport() {
        return "Authorized by local report policy";
    }
}
~~~

Using this annotation requires `@EnableMethodSecurity` in the appropriate Spring configuration. This is **not** a plain Java SE program. `hasAuthority` is only one layer of checks; reports also need owner/tenant classification when fine-grained access depends on the target object.

### 9.3. A header is not an MFA trust contract

If the proxy performed MFA for a sensitive transaction and the application needs **assurance level and auth_time**, it cannot rely solely on `X-Authenticated-User`. You need:
- A gateway contract covering the source, method, and recency of the authentication event.
- An appropriate context propagation/verification mechanism (trusted assertion, mTLS-scoped data, or a signed token with the proper audience).
- A step-up policy when assurance is insufficient.
- Decision auditing without logging credentials.

**Never fabricate `acr=mfa` or `amr=otp` from a role or username header.** A gateway signature over another claim does not justify elevating assurance.

## 10. Duplicate headers, username normalization, and HTTP parsing

A proxy chain might receive variants like:

~~~http
X-Authenticated-User: alice@corp.example
x-authenticated-user: admin@corp.example
~~~

HTTP header names are **case-insensitive**; some Servlet containers handle multiple values by having `getHeader(name)` return the **first value**, while another proxy joins them with commas. Therefore **two lines cannot be treated as two safely isolated principals**. Gateway rules:

1. **Strip** all incoming identity header names and aliases prior to authentication.
2. After auth, **set/replace with exactly one authoritative identity header**.
3. **Reject duplicate/conflicting identity headers**, never silently "pick the last one".
4. Enforce limits on length, charset, whitespace, CR/LF, and value count; log violation metadata (without logging raw identities).
5. Canonicalize username/subject in **one single place**, preserving the right namespace and documenting case sensitivity.
6. Pin trusted gateways / reverse proxy identities rather than relying on spoofable headers.

### 10.1. Do not trim or case-fold blindly

Usernames can be case-sensitive per IdP, and opaque subjects may contain characters lacking email-style canonicalization rules. Examples:

~~~text
Alice@Corp.Example
alice@corp.example
alice
CORP\alice
opaque-sub:001
opaque-sub:1
~~~

These can represent **different identities** depending on source and contract. Do not turn `CORP\alice` into `alice` if the same username exists in another realm. An IdP/OIDC OP may issue pairwise `sub` values per client; never merge accounts by email alone.

### 10.2. Multiple proxy hops

~~~text
Browser -> CDN -> WAF -> OIDC Gateway -> Service Mesh -> Spring
             (untrusted identity until trusted gateway injects)
~~~

Every hop needs a contract: who strips headers, who injects, who overwrites, and who may call the backend. If a Service Mesh issues mTLS identities to pods, you still need a gateway-only **authorization policy** in the mesh (specific service account/namespace/port), not merely "service mesh mTLS enabled across all pods". **mTLS between all pods** does not prove a request came from the **right authenticated gateway**.

## 11. Standalone Java 17 demo: simulating a safe trust boundary

The following program simulates two halves:
- **Outside Spring**: the gateway authenticates before forwarding, **ignores client-supplied headers**, and emits the verified identity.
- **Inside the application**: verifies the principal matches approved format/namespaces, local account is active, and resource permissions pass.

This is **standalone Java SE 17**, with no Spring imports. It **does not** connect to a real gateway, performs no TLS/mTLS/OIDC/SAML validation, and booleans like `trustedConnection` are **simulations only**. In production those guarantees must be proven by infrastructure/gateway, **never read from any HTTP request header**.

File **`TrustedProxyBoundaryDemo.java`**:

~~~java
import java.util.Set;

public final class TrustedProxyBoundaryDemo {

    record Incoming(
            boolean trustedConnection,
            String clientSuppliedHeader,
            boolean gatewayAuthenticated,
            String verifiedPrincipal,
            boolean localAccountActive,
            boolean hasReportsPermission) {}

    private static final Set<String> PROVISIONED =
            Set.of("alice@corp.example", "bob@corp.example");

    static String evaluate(Incoming in) {
        if (!in.trustedConnection()) {
            return "EDGE_REJECT";
        }
        if (!in.gatewayAuthenticated()) {
            return "UPSTREAM_DENIED";
        }

        // Gateway MUST strip clientSuppliedHeader.
        // Only an upstream-verified identity may reach backend.
        String principal = in.verifiedPrincipal();

        if (principal == null || principal.isBlank()) {
            return "NO_PRINCIPAL";
        }
        if (!principal.matches("[a-z][a-z0-9._-]{0,30}@corp\\.example")) {
            return "BAD_PRINCIPAL";
        }
        if (!PROVISIONED.contains(principal)) {
            return "NOT_PROVISIONED";
        }
        if (!in.localAccountActive()) {
            return "ACCOUNT_DISABLED";
        }
        if (!in.hasReportsPermission()) {
            return "FORBIDDEN";
        }
        return "ALLOW:" + principal;
    }

    public static void main(String[] args) {
        System.out.println(evaluate(new Incoming(
                false, "admin@corp.example", true,
                "alice@corp.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", false,
                null, true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "alice@corp.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "eve@other.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "bob@corp.example", false, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "bob@corp.example", true, false)));

        System.out.println(evaluate(new Incoming(
                true, null, true,
                "alice@corp.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                null, true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "mallory@corp.example", true, true)));
    }
}
~~~

Run commands:

~~~bash
javac TrustedProxyBoundaryDemo.java
java TrustedProxyBoundaryDemo
~~~

**Exact stdout:**

~~~text
EDGE_REJECT
UPSTREAM_DENIED
ALLOW:alice@corp.example
BAD_PRINCIPAL
ACCOUNT_DISABLED
FORBIDDEN
ALLOW:alice@corp.example
NO_PRINCIPAL
NOT_PROVISIONED
~~~

Explanation:

1. Caller bypassed the trusted gateway → **EDGE_REJECT**, even when headers or principal look valid.
2. Gateway has not authenticated, while client sent `admin` → **UPSTREAM_DENIED**.
3. Gateway authenticated `alice` and overwrote client header `admin` → application accepts **alice**, not admin.
4. Gateway emitted a principal outside the approved namespace → **BAD_PRINCIPAL**.
5. Kerberos/OIDC/SAML gateway authenticated `bob` yet local account is disabled → **ACCOUNT_DISABLED**.
6. `bob` is active yet lacks report permission → **FORBIDDEN**.
7. Client sent no self-asserted header while gateway authenticated `alice` → still allows `alice`.
8. Upstream supplied no principal → **NO_PRINCIPAL**, never falling back to the client header.
9. Principal matches format yet is not locally provisioned → **NOT_PROVISIONED**.

**Real limitations:** the demo uses a mocked `PROVISIONED` set, fixed `@corp.example` format, and boolean `gatewayAuthenticated`. Never use such variables as a proxy authentication control in a Spring controller; you need real mTLS evidence, header sanitization, gateway auth middleware, and a real user repository. What it demonstrates is the **order of checks** and why you must **never read `clientSuppliedHeader` back as the user**.

### 11.1. Exercises modifying the demo code

- Change `trustedConnection` to `false` even with `gatewayAuthenticated=true`: still yields EDGE_REJECT.
- Change `verifiedPrincipal` to `admin@corp.example` while keeping `localAccountActive=true`: yields NOT_PROVISIONED because the local DB has no admin, unlike "header says admin so auto-grant admin".
- Change `clientSuppliedHeader` to another string: outcome is unchanged as long as gateway verified principal is unchanged.
- Set `gatewayAuthenticated=false` with a non-null `verifiedPrincipal`: still yields UPSTREAM_DENIED.
- Set `hasReportsPermission=false`: even with an authenticated principal, still yields FORBIDDEN.
- Add tenant/account status checks, ensuring cross-tenant denial and blocked local users.
- Add tests preventing conflation of two similar subject values (case, realm, delimiter) when accepting multiple identity providers.

## 12. Operational scenarios: faulty proxy, misconfigured backend

| Symptom | Possible cause | Safe check |
| --- | --- | --- |
| All requests to Spring return 403. | Gateway emits no principal, backend lacks UserDetails, entry point does not fall back. | Trace gateway auth success → header injected metadata → Spring loader; do not print raw JWT/cookie. |
| Header arrives at Spring as `null`. | Proxy mistakenly strips its own set header, traffic uses a different route, filter reads wrong name. | Compare exact `principalRequestHeader` against gateway output on the trusted hop. |
| `SM_USER` header is present while filter expects `X-Authenticated-User`. | Mismatched contract. | Configure one standard name; never auto-read "any header". |
| Direct pod request with `X-Authenticated-User: admin` succeeds. | NetworkPolicy/ingress bypass. | **Security incident**: block direct path, enforce mTLS/ACL, and strip headers. |
| Client sends admin while gateway authenticates alice, yet app sees admin. | Gateway fails to overwrite or duplicate canonicalization bug. | Fix strip/replace at ingress; test duplicates/case/underscores. |
| App receives header yet denies access. | `UserDetailsService` lacks authorities, local account status/tenant deny. | Distinguish authentication from authorization; do not bypass account checks. |
| User is disabled yet app stays active. | Old session or stale user-details cache; disabled status checker. | Check stateless per-request behavior, cache TTL, revoked epoch. |
| Browser logs out of SSO yet Spring keeps granting access. | SecurityContext/HttpSession persists or proxy still sends stale identity. | Compare local session vs. gateway lifetime, recheck and revoke. |
| Principal switches from alice to bob on same cookie, app stays alice. | Base filter skips when session is already authenticated. | Use stateless or `checkForPrincipalChanges` + invalidate session and test. |
| Login fails only when filter is added as `@Bean`. | Spring Boot auto-registers Servlet filter outside Security chain. | Disable auto-registration; ensure filter runs once. |
| Provider does not process token. | `AuthenticationManager` not set, mismatched token type, missing wrapper. | Inspect FilterChain and ProviderManager wiring. |
| Missing credentials in provider. | Custom filter returns null credentials (unlike default N/A). | Fix contract; never treat N/A as a secret. |
| Missing header produces 500. | `exceptionIfHeaderMissing=true` throws before auth manager handler; filter order/error mapping. | Test exception path, gateway deny, and Spring error policy. |
| Form login and header auth share one chain. | Fallback accidentally opens a trust perimeter bypass. | Separate chains/hosts with matchers and policies, or remove fallback. |
| API bearer token fails in pre-auth app. | `RequestHeaderAuthenticationFilter` is not a JWT decoder. | Use `oauth2ResourceServer` with dedicated token validation. |
| One tenant sees another tenant's data. | Username mapped without issuer/tenant namespace, missing permission checks. | Bind identity tuple and resource/tenant authorization. |
| Multi-node behavior is inconsistent. | Local sessions, differing header paths, diverging user/role caches. | Shared policy/DB, stateless or consistent session store, load test. |
| Header case/multiple values yield different identities. | Inconsistent HTTP normalization across CDN/gateway/backend. | Strip all variants, reject duplicates, run canonicalization tests. |
| CSRF succeeds even though app is stateless. | Browser SSO ambient cookie causes gateway to attach header automatically. | Enforce CSRF/origin/Fetch Metadata policies; never disable CSRF casually. |
| API returns 403 after upstream login. | Local user missing/disabled or permission absent. | Keep deny-by-default; do not grant admin from a group header. |
| Gateway loses IdP yet keeps forwarding old header. | Fail-open behavior/wrong cache TTL. | Fix gateway session revocation; fail closed. |

### 12.1. Ordered debugging checklist

1. Did the request **arrive from the trusted gateway**? Does the backend block direct access?
2. Did the gateway authenticate the user or hit an "allow without login" fallback?
3. Were client-supplied identity headers **stripped** before the gateway attached the verified principal?
4. Does the final header reaching Spring have **exactly one value** and the right name?
5. Does Spring have `RequestHeaderAuthenticationFilter` inside the **SecurityFilterChain**, without duplicate Servlet registration?
6. Did the filter run on that request path, and what did `getPreAuthenticatedPrincipal` return (log masked/hashed for audit)?
7. Does `AuthenticationManager` have the right `PreAuthenticatedAuthenticationProvider`?
8. Did `AuthenticationUserDetailsService` locate the right local account?
9. Do `AccountStatusUserDetailsChecker`/custom checkers enforce disabled/locked states?
10. Is `SecurityContextRepository` persisting auth unexpectedly, rendering upstream logout ineffective?
11. Do `authorizeHttpRequests` and method security enforce proper authority/tenant/resource checks?
12. Is there a formLogin/httpBasic/bearer "fallback" or `permitAll` route inadvertently exposing protected resources?
13. Do the gateway/reverse proxy preserve headers intact across HTTP/2, WAF, and service mesh without allowing duplicates?
14. Are logs/metrics detailed enough to distinguish edge deny, missing principal, loader reject, and authz deny?

## 13. Testing: beyond the happy path

### 13.1. Unit tests for filter/provider

Cases worth testing with Spring MockMvc/Servlet mocks (this is a **test specification**, not runnable code without dependencies):

| Test | Expected |
| --- | --- |
| Header `X-Authenticated-User: alice@corp.example`, local user ACTIVE, has role. | Provider creates authenticated token with approved authorities. |
| Missing header, stateless backend with `anyRequest().authenticated()`. | Deny; does not reuse identity from a prior request. |
| Empty/whitespace header. | Deny per contract/gateway validation; creates no empty-username session. |
| Header contains CR/LF or multiple values. | Edge rejects/normalizes fail-safe; does not trust container-specific first/middle value. |
| Header `SM_USER` sent while filter is configured for `X-Authenticated-User`. | Does not accept identity from an unexpected header. |
| `PreAuthenticatedAuthenticationToken` has null credentials. | Provider rejects/ignores per config; grants no Authentication. |
| Token principal is valid yet `UserDetailsService` finds no user. | Reject; does not arbitrarily auto-provision. |
| UserDetails `isEnabled=false`. | Rejected by default checker. |
| UserDetails `isAccountNonLocked=false`. | Rejected; never reaches controllers. |
| User holds `ROLE_USER` while endpoint requires `app:admin`. | 403. |
| Provider lacks `PreAuthenticatedUserDetailsService`. | Bean init/config fails; creates no default identity. |
| Stateless app: request 1 alice, then request 2 missing header. | Request 2 is no longer authenticated. |
| Stateful app: request 1 alice, then request 2 bob. | Detects change/invalidates/re-authenticates per policy and tested filter settings. |
| App logged in yet permission is revoked. | Within SLA, data source/cache policy denies new action. |

### 13.2. Integration tests with a real reverse proxy

| Scenario | Expected outcome |
| --- | --- |
| Not logged into gateway, GET protected route. | Gateway blocks/redirects before backend; no trusted principal header sent. |
| Client sends `X-Authenticated-User: admin` unauthenticated. | Gateway strips and rejects request; never reaches Spring authenticated. |
| Logged in as alice while client sends `admin`. | Gateway overwrites; backend sees only alice. |
| Header name with differing case and duplicates. | Gateway rejects/strips properly; never resolves to admin. |
| Header with underscore instead of hyphen. | No bypass caused by differing normalization. |
| Direct access to pod/node port/secondary LB. | Blocked at network level; cannot log in via self-supplied header. |
| Same header traversing CDN, WAF, ingress, and service mesh. | Not altered, duplicated, or dropped. |
| Gateway mTLS client certificate is invalid. | Backend/mesh rejects before Spring. |
| Gateway IdP temporarily unavailable. | Fail closed; never forwards stale identity beyond SLA. |
| Browser logs out upstream. | Next request carries no trusted header; stateless app denies. |
| Gateway switches users in the same browser. | Backend receives new identity, retains no old roles. |
| Local account disabled between requests. | App denies per policy, even while gateway SSO remains active. |
| Multi-tenant username collision. | Accounts are never merged due to matching email/username. |
| Browser sends state-changing POST from malicious origin. | CSRF/origin checks block it, not relying on header SSO. |
| 403 response leaks no raw principal/headers. | Error handling/logging is redacted. |
| Audit logs contain raw usernames/tokens. | Security review test must fail and require data minimization. |
| Session-based variant running across multiple pods. | Header changes/logout are consistent; no stale SecurityContext retained. |

**Highest acceptance bar:** **client header-spoofing and direct-backend attacks** must fail. A unit test where the filter returns authenticated for a request carrying a header does not prove the infrastructure is safe; it only proves the library fulfills its function of "trusting a pre-authenticated header".

### 13.3. Illustrative HTTP request examples

**Deliberate spoofing attempt from an unauthenticated client:**

~~~http
GET /admin/users HTTP/1.1
Host: portal.example.org
X-Authenticated-User: admin@corp.example
~~~

A correct system:
- Gateway blocks because client is unauthenticated;
- or gateway authenticates the real user and **overwrites** the header with the real identity;
- Spring must never see the self-asserted admin.

**Client authenticated as alice yet attempting to inject admin:**

~~~http
GET /reports HTTP/1.1
Host: portal.example.org
Cookie: edge_sso_session=browser-owned-cookie
X-Authenticated-User: admin@corp.example
~~~

The cookie line is an **illustrative placeholder only**, not a usable credential. The backend must receive **alice's gateway-authenticated identity**, not admin from the raw request. Never place real cookies/tokens into documentation or logs.

## 14. Other pre-auth options: do not pick the wrong protocol

| Architecture | Appropriate Spring integration | Why |
| --- | --- | --- |
| Gateway authenticated and sends username via private/trusted header. | `RequestHeaderAuthenticationFilter` + `PreAuthenticatedAuthenticationProvider`. | True pre-auth; does not re-verify upstream credentials itself. |
| Java EE/Jakarta container already exposes authenticated `request.getUserPrincipal()`. | `J2eePreAuthenticatedProcessingFilter` or equivalent container pre-auth mechanism. | Principal source is the container trust boundary, not a client HTTP header. |
| X.509 client certificate at Spring/trusted TLS termination. | Spring X.509 authentication/filter with certificate validation. | Certificate binding differs from a trusted gateway username. |
| Browser logs in directly via OIDC at the Spring app. | `oauth2Login()`. | Spring performs code/token validation per client registration. |
| REST API receives OAuth Bearer JWT. | `oauth2ResourceServer().jwt()` with issuer/audience checks. | Resource server must verify tokens itself rather than trusting an `X-User` header. |
| REST API receives opaque bearer token. | Resource Server introspection. | Never use PreAuthenticatedAuthenticationProvider as a decoder. |
| SAML 2.0 POST Web SSO into Spring. | `saml2Login()` and SAML2 providers/validators. | Assertion signature/audience/correlation differ from pre-auth headers. |
| Reverse proxy terminates Kerberos and sends principal header. | Pre-auth if network/headers are trusted; or GSS validation in Spring if the app terminates it. | Choose where authoritative authentication lives. |
| Microservice calls microservice with mTLS + SPIFFE identity. | mTLS/service identity + application authorization, sometimes custom principal extraction. | Never treat headers sent by arbitrary pods as end-user logins. |

Even when the gateway terminates authentication, the application still needs to know the **trust conditions** and have enough information to distinguish accounts. If an API needs independent verification of token audience/expiry/signature, **do not** use header-only pre-auth just because it is faster to wire up.

## 15. Observability and privacy

Never log raw:
- `Cookie`, `Authorization`, OIDC ID/access/refresh tokens.
- Identity headers containing emails/employee IDs in public logs.
- SAML assertions or gateway session IDs.
- Full group/role lists or user profiles.
- Sensitive private network peer details and mTLS credentials.

Use audit fields with reference identifiers:

~~~text
event=PROXY_PREAUTH_DECISION
time_utc=2026-11-07T03:00:00Z
gateway_service_ref=corp-identity-gateway
request_correlation_id=req-729c
principal_ref=HMAC(canonical-principal)
principal_header_count=1
trusted_peer_verified=true
edge_authentication_status=SUCCESS
local_account_status=ACTIVE
authority_policy_version=portal-v6
decision=ALLOW
~~~

This is a **proposed custom schema**, not Spring Security's default log format. Never allow clients to set `trusted_peer_verified=true`. Metric labels should use bounded-cardinality reason codes and service refs, never raw usernames.

Useful metrics:
- `proxy_auth_success_total` / `proxy_auth_failure_total` at the gateway.
- `preauth_header_missing_total`, `preauth_header_duplicate_total`.
- `preauth_user_not_found_total`, `preauth_account_disabled_total`.
- `preauth_authorization_denied_total` by allowed route/role metric dimensions.
- `preauth_principal_change_total` in session-based systems.
- `preauth_direct_backend_probe_denied_total` at firewall/mesh.
- `preauth_edge_header_spoof_attempt_total`.
- `preauth_gateway_idp_outage_total` and stale cache hit/expiry.

**Do not rely on a 403 spike as the sole signal:** separate `gateway reject`, `Spring missing header`, `UserDetailsService reject`, and `resource authorization deny`; fixing the wrong layer can inadvertently weaken security.

## 16. Common pitfalls

1. **"`RequestHeaderAuthenticationFilter` authenticates users via the header."** False: it only **extracts** the principal, assuming the gateway already authenticated.
2. **"`PreAuthenticatedAuthenticationProvider` checks the upstream password."** False: it loads user/authorities without validating OIDC/SAML/credentials.
3. **"Having `UserDetailsService` stops header spoofing."** False: the loader will happily look up an attacker-supplied admin account.
4. **"Checking `X-Forwarded-For` proves a trusted gateway."** False: that is network metadata, spoofable if boundaries are wrong.
5. **"Backend uses HTTPS so all request headers are trustworthy."** False: TLS does not prove the gateway stripped headers unless mutual trust/client identity is enforced.
6. **"The gateway only needs to add the header if absent."** False: client-supplied headers must be stripped and **overwritten** from the verified identity.
7. **"Default header is X-Authenticated-User."** False: the class defaults to **`SM_USER`**.
8. **"The filter automatically validates signed token headers."** False: there is no JWT/SAML decoder.
9. **"`credentialsRequestHeader` makes the provider verify passwords."** False: there is no password verification.
10. **"Missing header always returns HTTP 403 by default."** False: by default it throws; response depends on filter chain/error handlers.
11. **"`exceptionIfHeaderMissing(false)` means anonymous is allowed on all routes."** False: authorization can still deny; still, test fallbacks/sessions.
12. **"`continueFilterChainOnUnsuccessfulAuthentication(true)` is always safe."** False if the chain contains another auth method that could bypass the trust contract.
13. **"Setting false always returns 403."** False: the thrown exception needs a handler and proper filter ordering.
14. **"Creating a Filter Bean and calling `addFilterBefore` again is harmless."** False: it can cause double registration.
15. **"`STATELESS` prevents CSRF automatically."** False: a browser gateway SSO cookie can act as an ambient credential.
16. **"User completed upstream MFA so they are admin by default."** False: assurance and authorization are separate.
17. **"Proxy X-Groups=admin converts directly to ROLE_ADMIN."** False: requires a contract/allowlist/entitlements.
18. **"Same username at two issuers is always the same person."** False: identities must be namespaced.
19. **"Upstream logout automatically clears the Spring session."** Not guaranteed: sessions/cookies can have independent lifetimes.
20. **"An active application server session can change the user in the header without special handling."** False: requires principal-change reauth/invalidation or stateless mode.
21. **"With mTLS between all pods, only the gateway can call the backend."** False: an **authorization** policy permitting only the gateway's service identity is required.
22. **"When the gateway fails, the application can accept old headers."** False: fail closed per SLA and trust contract.
23. **"Headers are case-sensitive so sending x-authenticated-user creates a separate claim."** False: HTTP header names are case-insensitive.
24. **"Making `/admin/**` permitAll is safe because the proxy blocks it."** That breaks defense-in-depth and risks routing bypass.
25. **"Pre-auth replaces resource authorization."** False: tenant/owner/action checks must still run in business services.

## 17. Pre-production checklist

1. Has the gateway proven **upstream authentication** via IdP/SSO/mTLS per contract?
2. Does the backend **block direct network paths** (public IP, NodePort, secondary ingress, unauthorized service mesh sources)?
3. Does the gateway **strip all client-supplied identity headers** and **overwrite exactly one header** from the verified principal?
4. Does the gateway reject unauthenticated requests, IdP outages, invalid sessions, and revoked tokens rather than forwarding stale headers?
5. Does the gateway→backend channel have appropriate TLS/mTLS/service identity or network isolation?
6. Do username/subject/issuer/tenant have stable namespaces preventing collisions and rename takeovers?
7. Does `RequestHeaderAuthenticationFilter` have the exact `principalRequestHeader` name, tested for missing/empty/duplicate values?
8. Is `PreAuthenticatedAuthenticationProvider` wired properly to `AuthenticationUserDetailsService` / `UserDetailsByNameServiceWrapper`?
9. Does `UserDetailsChecker` check locked/disabled state and enforce local authorization denial?
10. Is the filter inside the right **Spring Security FilterChain** without duplicate Servlet registration?
11. Are defaults for `exceptionIfHeaderMissing`, `continueFilterChainOnUnsuccessfulAuthentication`, and `checkForPrincipalChanges` well understood?
12. Have you deliberately chosen **stateless** or **session-based**, and tested user switches, logout, and revoked entitlements?
13. Are formLogin/httpBasic/Bearer fallbacks restricted to separate chains/hosts/URLs without bypassing pre-auth?
14. Are CSRF/origin defenses preserved for browser SSO cookies alongside proper CORS policy?
15. Are `authentication` and `authorization` separated, with tenant/resource ownership enforced at the backend?
16. Do logs capture correlation IDs/reason codes without logging raw identity tokens/PII?
17. Do integration tests cover sending **forged admin headers** from the Internet, direct pod access, duplicate headers, and gateway failures?
18. Have multi-node behavior, DNS/TLS rotation, source identity policy, session storage/expiry, and authz updates been tested?
19. For admin/finance endpoints, are trusted step-up/assurance evidence and separate local entitlements enforced?
20. Is there an owner/approval/review process for changes to the gateway header contract, service identities, and permissions?

## 18. Self-check quiz

1. **What does `RequestHeaderAuthenticationFilter` do?** — Reads the principal from a configured header and creates a pre-authentication request; does not verify upstream credentials.
2. **What is the default header?** — **`SM_USER`**.
3. **What does `PreAuthenticatedAuthenticationProvider` do?** — Uses `AuthenticationUserDetailsService` to load `UserDetails`/authorities and check account status, producing an authenticated token.
4. **Why can a user impersonate admin if the backend is directly reachable?** — Because the filter trusts the header, and the header itself carries no cryptographic proof.
5. **What must the proxy do with client-supplied headers?** — Strip all self-asserted identity headers before emitting a single authoritative header from the verified principal.
6. **What is `N/A` in credentials?** — A dummy value, not a password.
7. **What happens by default when the header is missing?** — The filter throws `PreAuthenticatedCredentialsNotFoundException`; the HTTP response must be tested against error handling/filter ordering.
8. **Does `exceptionIfHeaderMissing(false)` always let anonymous requests through?** — No; the chain must deny anonymous access if the route requires auth.
9. **When should `UserDetailsByNameServiceWrapper` be used?** — When the principal is already a unique key suitable for lookup via `UserDetailsService.loadUserByUsername`.
10. **Why not map an upstream admin group directly to app admin?** — Because namespaces/semantics differ and local entitlements are required.
11. **Why is stateless mode advantageous when the gateway injects a header on every request?** — It avoids retaining stale SecurityContext when upstream stops emitting assertions.
12. **Why does stateless mode not eliminate CSRF by itself?** — A gateway SSO cookie can cause the browser to be re-authenticated automatically without user intent.
13. **What does `checkForPrincipalChanges(true)` solve?** — Compares the new principal header against the old session authentication when requests traverse the filter.
14. **Why is `invalidateSessionOnPrincipalChange` needed?** — Reduces the risk of reusing stale session/data when the identity changes.
15. **Why should formLogin and pre-auth not be mixed in the same chain?** — It can create a bypass around the external authentication system.
16. **How does an API JWT differ from a pre-auth header?** — A JWT must have its signature, issuer, audience, and expiry verified by the backend; header-only pre-auth does not do that.
17. **What is the difference between 403 and 401 in pre-auth?** — Depends on entry point/error policy; `Http403ForbiddenEntryPoint` typically returns 403 when no principal is present.
18. **What is the strongest test evidence for gateway trust?** — Admin header spoofing and direct-backend attempts both fail, while legitimately authenticated users still map correctly.
19. **Why is mTLS between all pods insufficient?** — You must authorize only the specific gateway service identity to call the backend.
20. **Can you rely on un-namespaced email/username across multiple IdPs?** — Unsafe due to potential collisions, renames, or reuse.
21. **When the local account is DISABLED while the upstream header is still valid, what must happen?** — Deny admission/authorization per the status checker and policy.
22. **Does Spring Security know whether the gateway used MFA?** — Not from a username header alone; requires contracted, verified assurance evidence.
23. **How do you configure the filter so it does not run twice?** — Add the filter to the right SecurityFilterChain without simultaneously auto-registering it as a Servlet Filter Bean.
24. **After upstream logout, can a local session remain?** — Yes, if session-based and lacking revocation/identity refresh; a policy is needed.
25. **Where does actual identity verification live in this model?** — Gateway/IdP + trusted channel; Spring only accepts and maps the verified identity.

## References

- [Spring Security — Pre-Authentication Scenarios: Request-Header, provider, Http403ForbiddenEntryPoint](https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html)
- [Spring Security API — RequestHeaderAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html)
- [Spring Security API — AbstractPreAuthenticatedProcessingFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html)
- [Spring Security API — PreAuthenticatedAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [Spring Security API — UserDetailsByNameServiceWrapper](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security GitHub — RequestHeaderAuthenticationFilter implementation](https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.java)
- [Spring Security GitHub — PreAuthenticatedAuthenticationProvider implementation](https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.java)
- [OWASP — HTTP Security Response Headers and reverse-proxy architecture guidance](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
