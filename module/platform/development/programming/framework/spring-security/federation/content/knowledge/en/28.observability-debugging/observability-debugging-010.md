# Distinguishing Successful Login from Post-Login Authorization Errors

> **Topic:** Spring Security – federation. **Category:** Observability and debugging. This Knowledge article explains why **OIDC/SAML2/Kerberos/CAS login can succeed while the user still gets 403 or is redirected to an access-denied page**; how to separate authentication, authorization, HTTP entry point, CSRF, session, role mapping, tenant, and business policy; and how to diagnose via Spring Security logs, events, tests, and Java 17 examples.

## 1. Typical Scenario

Alice logs in via the IdP successfully:
1. The browser is redirected to the IdP.
2. Alice authenticates with the IdP.
3. The browser returns to the Spring application.
4. Spring verifies the ID Token or SAML Response and stores `Authentication`.
5. The UI displays Alice's name.
6. Alice opens `/reports/2026`.
7. The server returns **403 Forbidden**.

There is no contradiction. **The IdP proved who Alice is**, yet the reports endpoint requires `ROLE_REPORT_VIEW` or a tenant membership Alice lacks. Inspect **the decision at steps 6–7** rather than jumping to blaming SAML signatures or OIDC tokens.

Conversely, if the callback failed signature, issuer, nonce, audience, or ticket validation, Spring **never created a valid `Authentication`**. That is an **authentication** failure, not missing post-login permissions.

### 1.1. Key Conclusions to Remember

- **Authentication success:** the system confirmed a trusted identity, such as `OidcUser`, `Saml2AuthenticatedPrincipal`, or a Kerberos principal.
- **Authorization success:** that identity is permitted to perform a specific action on a specific resource/tenant.
- **Login success ≠ access granted to every endpoint.**
- **A 403 is not always a missing business role**: it can be CSRF, CORS/preflight, method security, a resource belonging to another tenant, or a gateway/proxy returning 403 itself.
- **A 302 does not prove login succeeded**: a redirect may go to the IdP, login page, callback, or an error page.
- **A 401 is not always an IdP failure**: on an HTTP API, a request lacking a token/session is also challenged with 401 even if the browser completed SSO earlier.
- You must observe **the same request/trace**, `SecurityContext` state, authorities, applied policy, and where the response originated.

## 2. Authentication and Authorization Differ

| Aspect | Authentication | Authorization |
|---|---|---|
| Question | Who is the caller? Is the identity proof valid? | What may this identity do with this resource? |
| Input | Password, Kerberos ticket, SAML Assertion, OIDC authorization code/ID Token | `Authentication`, `GrantedAuthorities`, roles, scopes, tenant, resource owner, business policy |
| Spring components | `AuthenticationManager`, `AuthenticationProvider`, login filters | `AuthorizationManager`, `AuthorizationFilter`, `@PreAuthorize`, domain policy |
| Outcome | Authenticated principal in `SecurityContext` | Permit / deny for a request/method/action |
| Typical failure | Bad credentials, invalid token/signature, wrong issuer/nonce, expired credential | Missing authority, wrong role prefix, inactive tenant membership, ownership denied |
| User-facing | Login error, redirect, 401/challenge | Usually 403; may vary per policy/handler |
| Proper fix | Fix trusted IdP/credential/flow | Fix approved role mapping/entitlement/rule or policy |
| Wrong fix | Grant `ROLE_ADMIN` to everyone at login | Disable signature checks or `permitAll` because of 403 |

**Authorization is evaluated per resource.** A logged-in user can open `/profile` while being denied at `/admin`; that is normal least-privilege behavior.

## 3. Spring Security Servlet Filter Chain: Two Separate Gates

In the Servlet stack, requests typically flow through:

~~~text
Incoming HTTP request
   |
   v
FilterChainProxy / selected SecurityFilterChain
   |
   +-- SecurityContextHolderFilter
   |      Load context for this request (if available)
   |
   +-- CSRF / exploit protection filters
   |
   +-- Authentication filters
   |      OIDC/SAML/Basic/Bearer/Kerberos/form login ...
   |      May authenticate and save SecurityContext
   |
   +-- AnonymousAuthenticationFilter (if still anonymous)
   |
   +-- ExceptionTranslationFilter
   |      Bridges security exceptions to HTTP response
   |
   +-- AuthorizationFilter
   |      Evaluate requestMatchers / AuthorizationManager
   |      May throw AccessDeniedException
   |
   v
DispatcherServlet / Controller
   |
   +-- Method Security (@PreAuthorize, @PostAuthorize)
   +-- Domain authorization / tenant membership
   |
   v
HTTP response
~~~

This is a **conceptual** diagram: exact filter order and classes depend on version, mechanism, and configuration. Do not substitute the diagram for checking the actual `SecurityFilterChain` in startup logs.

### 3.1. When Login Succeeds

A SAML2/OIDC authentication filter verifies the credential, `Authentication` is built, and (for session login) `SecurityContext` is saved via the configured `SecurityContextRepository`. The browser receives a session cookie and redirects to the saved request or success URL. Subsequent requests reload the context from the session when persistence is configured.

**The success handler only states that the authentication flow just succeeded.** It does **not** pre-check every route/tenant/resource across the application.

### 3.2. When Authorization Denies

`AuthorizationFilter`/`AuthorizationManager` or method security checks permissions, sees missing `ROLE_REPORT_VIEW` or tenant membership → denies, typically throwing `AccessDeniedException`.

`ExceptionTranslationFilter` handles downstream exceptions:
- If the caller is anonymous/insufficiently authenticated per the trust resolver, it invokes `AuthenticationEntryPoint` to start login/challenge.
- If authenticated at the required level yet lacking permission, it delegates to `AccessDeniedHandler`, typically producing **403**.
- If it is an `AuthenticationException`, it continues/challenges authentication.
- Not every 403 passes through this filter; for instance, `CsrfFilter` can reject earlier or a proxy can return an error.

Spring documentation also notes that remember-me authentication can be treated as insufficient in flows requiring full login; therefore "having an `Authentication` object" does not always mean fully authenticated.

## 4. HTTP 302, 401, 403: Reading in Context

| Status / Symptom | Common Possibilities | How to Determine |
|---|---|---|
| 302 to IdP/login | Unauthenticated or starting SSO | Check `Location` and cookie/request state |
| 302 to saved URL after SSO | Login callback may have succeeded | Check `SecurityContext` and the next request |
| 200 from callback/landing | UI returned; **insufficient** to prove all permissions | Check local `Authentication` and authorities |
| 401 Unauthorized | Missing/insufficient credential on API | Check `WWW-Authenticate`, token/session |
| 403 Forbidden after login | Principal exists yet lacks role/tenant/resource access | Check `accessDenied` cause and matched policy |
| 403 on POST when GET works | Missing/wrong CSRF token or method policy | Check CSRF log/handler before blaming roles |
| 403 on OPTIONS/preflight | Misconfigured CORS/security gateway | Check `Origin`, CORS headers, filter chain |
| 404 after redirect | Route absent or intentionally hiding resource | Check MVC mapping and product policy |
| 405 | HTTP method unsupported by route | Check controller/request method |
| 500 during entitlement check | App/entitlement provider error | Check sanitized exception and dependencies |
| Redirect loop to login | Session/cookie/correlation not preserved | Check `SameSite`, domain, HTTPS, `RequestCache` |
| Frontend shows "access denied" yet API 200 | UI self-checking roles or cached state | Compare network/API and client route guard |

### 4.1. 401 and 403 in Browser SSO Differ from APIs

For web pages running `oauth2Login()` or `saml2Login()`:
- Unauthenticated users usually **302** to the entrypoint/IdP instead of seeing raw 401.
- Logged-in users lacking an authority usually receive **403** from `AccessDeniedHandler`.
- If the session is lost between redirect and resource request, the browser may **302** back to login.
- For REST resource servers, `BearerTokenAuthenticationEntryPoint` typically returns **401** for missing/invalid tokens; `BearerTokenAccessDeniedHandler` typically turns missing scope/authority into **403** per Bearer protocol policy.
- `WWW-Authenticate` helps distinguish `invalid_token` from `insufficient_scope`, though exact output depends on config/framework.

**Never assume every API or browser login uses one fixed handler/HTTP code.** Identify the actual `SecurityFilterChain`, authentication mechanism, and failure handler.

### 4.2. A 302 Can Mask an Authorization Error

`RequestCache` saves the original URL, e.g., `/admin`. After SSO succeeds, the success handler redirects to that saved URL:
~~~text
GET /admin
  -> redirect to IdP (anonymous)
  -> user logs in
  -> IdP callback passes
  -> redirect to /admin (saved request)
  -> 403 because ROLE_ADMIN missing
~~~

Users will say "login threw 403", yet logs show **login succeeded** and the denial happened on the post-redirect request. Trace each HTTP request individually, not just the final screen.

## 5. Decision Tree When Users Report "Logged In Yet Blocked"

~~~text
User says "login succeeded, but access denied"
                |
                v
Was SSO callback/authentication successful?
                |
           +----+----+
           |         |
          NO        YES
           |         |
  Check IdP token/   v
  signature, state,  Does current request have
  nonce, audience,   a persisted Authentication?
  session exchange        |
                    +-----+------+
                    |            |
                   NO           YES
                    |            |
           Session/cookie/      v
           wrong chain/     Which control denied?
           token missing       |
                           +----+----+---------------+
                           |         |               |
                       URL rule   Method rule     CSRF/tenant
                           |         |               |
                      authorities  @PreAuthorize   check policy,
                      & matchers   & proxy         token/resource
                           \         |              /
                            \--------+-------------/
                                     |
                          Correct policy or approved
                          role mapping; do not bypass
                          authentication/authorization
~~~

**The first step is capturing the timeline**, including callback response, next request URL/method, status, handler, `SecurityContext` on the failing request, and matched security rule.

## 6. Finding Evidence That Login Truly Succeeded

A solid evidence chain:
1. IdP redirect/callback arrived at the right endpoint.
2. Spring `AuthenticationProvider` verified the protocol and credential.
3. The resulting `Authentication` has `isAuthenticated()=true` and is **not an `AnonymousAuthenticationToken`**.
4. The principal carries a stable identity key from the right IdP realm/issuer.
5. For session-based apps, `SecurityContext` was saved and reloaded on the next request.
6. Local user ID/account mapping is approved.
7. A success event/log or authentication success handler execution exists.
8. Authorities on the denied request **can** be inspected without logging full sensitive claims.

**Caution:** `AnonymousAuthenticationToken.isAuthenticated()` can return true. Thus `auth != null && auth.isAuthenticated()` **is insufficient** to conclude an SSO user truly logged in. Use a trust resolver, `isAuthenticated()` / `isFullyAuthenticated()` expressions per Spring policy, and distinguish the `Authentication` implementation.

### 6.1. Per-Request `SecurityContext`

`SecurityContextHolder` is typically bound to the current thread/request. After the callback, opening a new request or running an async task does not automatically inherit the callback thread's context. For session logins, the repository must save/load the context; for stateless JWT APIs, every request needs a bearer token.

**If the callback passes yet the next request is anonymous**, check first:
- Was the session cookie set and sent back by the browser?
- Do cookie `Path`/`Domain`/`SameSite`/`Secure` match origin/HTTPS/redirects?
- Are Spring Session/Redis and load balancers sharing state properly?
- Is `SessionCreationPolicy.STATELESS` unintentionally active on the browser SSO chain?
- Are there multiple `SecurityFilterChain`s, and which chain did each request match?
- Did a custom success handler/repository forget to save the context in your Spring version?
- Is a reverse proxy/ingress altering forwarded host/scheme?
- Is the frontend calling an API on a different origin without sending cookies/credentials?
- Did logout/session expiry occur between the two requests?
- Is there a stale browser tab or third-party cookie restriction?

Never "fix" by removing `authenticated()` guards.

## 7. What an `Authentication` Object Contains and Does Not Contain

A successful `Authentication` provides:
- `getPrincipal()`: verified user, type depends on protocol.
- `getAuthorities()`: authorities mapped/looked up when building `Authentication`.
- `getName()`: a display/representative name, not always a stable account ID.
- `isAuthenticated()`: an `Authentication` flag; exclude anonymous/remember-me per policy.
- `getDetails()`: implementation-dependent request/context info; **never** trust as a role source.

**Not guaranteed**:
- The user holds `ROLE_ADMIN`.
- The user belongs to the target tenant.
- The local account is still active today.
- All SAML/OIDC claims mapped to application roles.
- Authorities updated instantaneously when AD/IAM changed.
- The resource owner matches the logged-in user.

### 7.1. Reading Authorities Accurately

Example authorities:
~~~text
OIDC_USER
SCOPE_openid
SCOPE_profile
ROLE_REPORT_VIEW
~~~

It does **not** include `ROLE_REPORT_APPROVE`. An endpoint requiring `hasAuthority("ROLE_REPORT_APPROVE")` must deny Alice even though she holds `OIDC_USER` and `profile` scope.

### 7.2. `isAuthenticated` Is Not an Access Decision

An app that only checks `isAuthenticated()` and opens every tenant violates least privilege. Conversely, an app missing role mapping can return 403 to legitimate users. **Authorization must be decided per action and resource**, never on "is logged in".

## 8. Roles, `GrantedAuthority`, and Prefix Mistakes

Common Spring Security authorization rules:

~~~java
.requestMatchers("/reports/**")
    .hasAuthority("ROLE_REPORT_VIEW")

.requestMatchers("/admin/**")
    .hasRole("ADMIN")
~~~

With the default role prefix:
- `hasAuthority("ROLE_REPORT_VIEW")` matches the exact authority string.
- `hasRole("ADMIN")` normally checks for `ROLE_ADMIN`.
- Passing `hasRole("ROLE_ADMIN")` when the default prefix applies can cause errors or inconsistent configuration. Use `hasAuthority("ROLE_ADMIN")` when checking the full prefixed string.
- `ROLE_Report_View` differs from `ROLE_REPORT_VIEW` in casing.
- `SCOPE_admin` is not equivalent to `ROLE_ADMIN`.
- `"GROUP_FINANCE"` from the IdP is not automatically equivalent to `ROLE_FINANCE_VIEW`.

### 8.1. Reading the Policy Applied to a URL

Examples:
~~~text
GET /reports/2026
Rule: hasAuthority("ROLE_REPORT_VIEW")
Actual: [ROLE_USER, SCOPE_profile]
Outcome: DENY

GET /reports/2026
Rule: hasAuthority("ROLE_REPORT_VIEW")
Actual: [ROLE_USER, ROLE_REPORT_VIEW]
Outcome: Potentially PERMIT at URL layer

GET /tenants/team-b/reports/42
Rule: hasAuthority("ROLE_REPORT_VIEW")
Actual: [ROLE_REPORT_VIEW]
Additional business check: Alice member of team-a only
Outcome: DENY at tenant/resource layer
~~~

"Potentially PERMIT" means the URL-level rule passes; method/domain-level policies can still deny.

### 8.2. Role Hierarchy and Permission Naming

If the project uses `RoleHierarchy`, e.g., `ADMIN` implies `REPORT_VIEW`, configure and test its behavior across both `AuthorizationManager` and method-security expressions. Never assume every layer understands role hierarchies or that "ADMIN" automatically holds every authority.

For domain permissions, you might use `REPORT_READ`, `invoice:approve`, or `ROLE_REPORT_VIEW`. Pick one version-controlled naming convention; tests must confirm matchers and mappers use the same convention.

### 8.3. Never Self-Grant Roles to Mask Failures

When Alice gets 403, never do:
~~~java
// UNSAFE: every login becomes admin.
authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
~~~

Proper fix: trace the entitlement source, issuer/tenant trust, user account mapping, and allowlisted group-to-role rules; grant only genuinely approved permissions.

## 9. OIDC/OAuth2 Login: User Exists Yet Lacks App Roles

In Spring `oauth2Login()`:
- Spring verifies the Authorization Code flow/ID Token per protocol.
- The authenticated principal may be an `OidcUser`.
- `OidcUserAuthority`/`OIDC_USER` indicates identity/claims were processed.
- `SCOPE_...` from scopes appears where applicable; those are not arbitrary app roles.
- `OAuth2AuthenticationToken.getAuthorities()` is evaluated by HTTP/method authorization.
- The app can use a `GrantedAuthoritiesMapper` or delegated `OidcUserService` to map trusted IdP claims/groups to app authorities.

### 9.1. Root-Cause Example

~~~text
IdP login status: SUCCESS
iss: https://login.example.org/realm/staff
sub: stable-subject-123
IdP claim: groups=["ReportReaders"]
Local user mapping: alice / active
Spring authorities: [OIDC_USER, SCOPE_openid, SCOPE_profile]
URL rule: hasAuthority("ROLE_REPORT_VIEW")
Decision: DENY
~~~

If the `groups` claim is unmapped, Spring will not turn it into `ROLE_REPORT_VIEW` on its own. You need a mapper keyed on stable group IDs and a trusted issuer/tenant contract, or entitlements loaded from an approved IAM/DB source.

### 9.2. Issuer-Subject Identity Mapping

In OIDC, the `iss + sub` pair is the stable identifier within the provider's scope. Email or `preferred_username` is insufficient to auto-link sensitive accounts. A successful OIDC login can land on an **unprovisioned/disabled local account**, in which case business onboarding/authorization denying access is correct.

### 9.3. OAuth2 Login Is Not OAuth2 Resource Server

`oauth2Login()`: interactive browser, sessions, IdP redirects.

`oauth2ResourceServer().jwt()`: API accepting a Bearer access token per request, verifying signature/issuer/audience/scopes per config. A browser holding an OIDC session does not automatically authenticate JavaScript calls to a Bearer-protected REST API unless a valid token is sent; a session cookie does not substitute for an access token.

Identify the right `SecurityFilterChain` before diagnosing 401/403.

## 10. SAML 2.0 Login: Valid Assertion Still Lacks Permissions

With `saml2Login()`, Spring Security verifies SAML Response/Assertion signatures, Issuer, Audience, Destination, SubjectConfirmation, Conditions, and InResponseTo per provider/profile. Upon success, `Saml2Authentication` and `Saml2AuthenticatedPrincipal` represent the verified identity.

Afterward:
- `Saml2AuthenticatedPrincipal.getName()` is not automatically a local user ID.
- `getAttributes()` holds SAML attributes per protocol/provider mapping; it is not automatically `ROLE_ADMIN`.
- `Saml2Authentication.getAuthorities()` reflects authorities assigned per configuration.
- The app still needs local account linking, role/group mapping, and tenant/resource authorization.
- XSW signature wrapping or an invalid assertion is an **authentication failure**; missing application authority after a verified assertion is an **authorization failure**.

### 10.1. Example

~~~text
SAML Issuer: urn:example:saml:idp:staff
Signed Assertion: verified
NameID: alice-staff-001
Attributes: department=Finance, groups=["ReadOnlyReports"]
Local user: 1001, active
Mapped authority: ROLE_REPORT_VIEW
Endpoint /finance/approve: requires ROLE_FINANCE_APPROVE
HTTP result: 403 after successful SAML login
~~~

Never fix by disabling signature verification or accepting raw `groups` blindly. Check policy mapping; if Alice was not granted approval rights, 403 is the right outcome.

### 10.2. SAML Logout, Assertion Expiry, and Application Sessions

SAML Assertions have a validity window, yet Spring `HttpSession` has a separate lifecycle. A user verified at login may retain an authority snapshot until the session expires or policy re-checks; removing a group at the IdP does not automatically kill all existing sessions. SAML Single Logout requires explicit design; never assume local sessions expire with assertion validity.

## 11. Kerberos, LDAP, and CAS: Permissions Remain a Separate Question

**Kerberos/SPNEGO:** the GSS ticket validator verifies principal `alice@EXAMPLE.ORG`; `KerberosServiceAuthenticationProvider` can call `UserDetailsService` to load the local account/`GrantedAuthorities`. If mapping returns empty or lacks a group, login succeeds while role-protected routes return 403.

**LDAP direct authentication:** binding with valid username/password proves credentials; `LdapAuthoritiesPopulator`/database mapping rules determine authorities. Finding an LDAP entry is not proof the user logged in; a successful bind does not grant every permission either.

**CAS:** CAS service ticket validation proves the principal from the CAS server; the app still needs local account/role/tenant mapping. A CAS-authenticated user is not automatically an admin on the portal.

**Cross-realm/tenant:** identical short usernames `Alice` in two Kerberos realms or identical emails from two OIDC issuers **do not** prove the same local user. False 403s can stem from missing identity links; true 403s prevent cross-tenant takeovers.

## 12. Method Security: URL-Level Passes Yet Service Denies

Spring Security supports `@PreAuthorize`/`@PostAuthorize` when `@EnableMethodSecurity` is active. A request can pass the URL rule `authenticated()`, enter the controller, and then be denied by the method interceptor due to missing `ROLE_REPORT_VIEW`.

Example:
~~~java
@PreAuthorize("hasAuthority('ROLE_REPORT_VIEW')")
public ReportDto loadReport(String reportId) {
    return reportService.load(reportId);
}
~~~

This is a **method fragment**: types, imports, and domain service implementations are provided by the project. The sequence to learn is:
1. URL-level `AuthorizationManager` may permit.
2. Method invocation passes through the Spring AOP interceptor.
3. `@PreAuthorize` checks authorities.
4. Missing role → `AccessDeniedException`/authorization-denied.
5. On an HTTP flow, `ExceptionTranslationFilter` can translate that into 403 via the handler.
6. If the method runs outside the HTTP/request filter chain, the app must handle the exception at another boundary.

### 12.1. Enabling Method Security

~~~java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

This is a valid Spring application class given the right dependencies. Spring Boot starter security **does not automatically activate all method-level annotations** without proper configuration.

### 12.2. Self-Invocation and AOP Proxies

A method inside the same bean calling an `@PreAuthorize`-annotated method directly can bypass the Spring AOP proxy. The consequence is normally **missing enforcement** rather than a 403 denial. When debugging, verify the call passes through the proxy, check interfaces/proxy visibility, and watch async/thread contexts. Never rely on an un-intercepted annotation to protect business resources.

### 12.3. Denials from Domain Services

For example, a route passes URL-level and method role checks, yet the business service checks that the user belongs only to tenant A while the report belongs to tenant B. The domain service may throw `AccessDeniedException` or return a business denial per documented API contract. Trace the cause and sanitized resource ID; never equate every 403 with missing `ROLE_REPORT_VIEW`.

## 13. CSRF 403 Is Not a Missing App Role

Spring `CsrfFilter` protects state-changing requests whenever session cookies carry credentials. A typical case:
~~~text
GET  /reports       -> 200 (authenticated + authorized)
POST /reports/export -> 403 (CSRF token missing)
~~~

If logs show `InvalidCsrfTokenException` or `MissingCsrfTokenException`, fix:
- UI/forms sending the proper CSRF token.
- API clients fetching/sending the token per the configured repository.
- Cookies/headers/`SameSite` configuration.
- If an API is purely stateless using Bearer tokens without cookies, CSRF policy may differ per threat model.
- Use `csrf.ignoringRequestMatchers(...)` only for protocol endpoints that genuinely require exemption per contract (e.g., Spring-managed SAML ACS); **never disable CSRF system-wide** because one POST got 403.

**Never grant `ROLE_ADMIN`** to fix CSRF. Role mappers cannot solve a missing CSRF token.

## 14. CORS/Preflight, Proxies, and 403 Origin

A browser SPA may send `OPTIONS /api/reports` before a GET carrying an `Authorization` header. If CORS/security proxies reject `OPTIONS`, the frontend may display "Forbidden" even though the user's session/roles are valid.

Check:
- Is the HTTP method `OPTIONS` or `GET`/`POST`?
- Are `Origin` and `Access-Control-Request-Headers` allowlisted?
- Has the filter chain enabled `cors()` with the right CORS configuration?
- Are authentication/authorization rules wrongly applied to preflight requests?
- Did the 403 come from Spring or from NGINX/WAF/API gateway?
- Is an internal ingress `X-Forwarded-Proto`/`Host` header affecting redirects/cookies?
- Is the API calling the right host/path and sending cookies/Bearer tokens?

**The source returning 403 matters more than the 403 code alone.** If the request never reached Spring's controller/filter chain, editing Spring roles will have zero effect.

## 15. RequestCache and Success Redirect: Tracing the Exact Request

A login success handler may redirect to:
- Saved original URL.
- Configured default success URL.
- A URL stored in the request cache.
- Frontend landing page.

If the saved URL requires more permissions than the granted `Authentication`, the user sees 403 right after callback. Log sanitized diagnostics:
~~~text
traceId=abc
event=authentication_success
mechanism=OIDC
registration=staff
principalIdHash=...
redirectTarget=/reports/review

traceId=def
event=authorization_denied
method=GET
path=/reports/review
requiredAuthority=ROLE_REPORT_APPROVE
availableAuthorityCategories=[OIDC_USER,SCOPE_profile,ROLE_REPORT_VIEW]
decision=DENY
status=403
~~~

This is a **sample log**, not a default Spring log format. HTTP trace IDs may need separate session/redirect correlation if you want to link the two requests; the two requests can have different IDs.

### 15.1. Avoiding Open Redirects

Never let clients supply arbitrary success URLs that the app redirects to unchecked. With OAuth2/OIDC/SAML, `state`/`RelayState`/request cache must be handled safely; post-login redirects should be internally allowlisted. A login success redirect does not prove the target URL is authorized.

## 16. Standalone Java 17: Modeling Post-Login Authorization Decisions

This standalone example runs with **JDK 17+, requiring no Spring or IdP**. It assumes an authentication pipeline **already** verified credentials and produced a trusted `AuthSnapshot`. The code deliberately separates authentication state, roles, tenants, and full-authentication requirements.

File `PostLoginDecisionDemo.java`:

~~~java
import java.util.Set;

public class PostLoginDecisionDemo {

    record AuthSnapshot(
            boolean hasTrustedLogin,
            boolean fullAuthentication,
            Set<String> authorities,
            Set<String> tenants) {
    }

    enum Decision {
        START_AUTHENTICATION,
        REQUIRE_FULL_LOGIN,
        FORBIDDEN_MISSING_AUTHORITY,
        FORBIDDEN_TENANT,
        ALLOW
    }

    static Decision decide(
            AuthSnapshot auth,
            String requiredAuthority,
            String resourceTenant,
            boolean requireFullLogin) {

        if (auth == null || !auth.hasTrustedLogin()) {
            return Decision.START_AUTHENTICATION;
        }

        if (requireFullLogin && !auth.fullAuthentication()) {
            return Decision.REQUIRE_FULL_LOGIN;
        }

        if (!auth.authorities().contains(requiredAuthority)) {
            return Decision.FORBIDDEN_MISSING_AUTHORITY;
        }

        if (!auth.tenants().contains(resourceTenant)) {
            return Decision.FORBIDDEN_TENANT;
        }

        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        AuthSnapshot alice = new AuthSnapshot(
                true, true,
                Set.of("OIDC_USER", "SCOPE_profile", "ROLE_REPORT_VIEW"),
                Set.of("tenant-a"));

        AuthSnapshot remembered = new AuthSnapshot(
                true, false,
                Set.of("ROLE_REPORT_VIEW"),
                Set.of("tenant-a"));

        System.out.println("anonymous=" +
                decide(null, "ROLE_REPORT_VIEW", "tenant-a", false));

        System.out.println("read=" +
                decide(alice, "ROLE_REPORT_VIEW", "tenant-a", false));

        System.out.println("approve=" +
                decide(alice, "ROLE_REPORT_APPROVE", "tenant-a", false));

        System.out.println("other-tenant=" +
                decide(alice, "ROLE_REPORT_VIEW", "tenant-b", false));

        System.out.println("remembered=" +
                decide(remembered, "ROLE_REPORT_VIEW", "tenant-a", true));

        System.out.println("scope-is-not-role=" +
                decide(alice, "ROLE_ADMIN", "tenant-a", false));
    }
}
~~~

Compile and run:

~~~bash
javac PostLoginDecisionDemo.java
java PostLoginDecisionDemo
~~~

**Exact stdout:**

~~~text
anonymous=START_AUTHENTICATION
read=ALLOW
approve=FORBIDDEN_MISSING_AUTHORITY
other-tenant=FORBIDDEN_TENANT
remembered=REQUIRE_FULL_LOGIN
scope-is-not-role=FORBIDDEN_MISSING_AUTHORITY
~~~

**Interpretation:** Alice logged in so reading `tenant-a` reports is permitted, yet she cannot approve or read `tenant-b` merely by holding `ROLE_REPORT_VIEW`. `SCOPE_profile` does not grant `ROLE_ADMIN`. A remember-me/snapshot failing a fully-authenticated policy triggers a stronger authentication step.

**Limitations:** This is a pure decision model; it does not verify OIDC/SAML/Kerberos, nor implement Spring `AuthenticationTrustResolver` or real tenant lookups. The two booleans in the record **must never come directly from a browser**. In production, Authentication and tenant entitlements must come from a trusted IdP/DB/policy service; never replace security filters with this decision model.

## 17. Standalone Java 17: Separating Login Events from Resource Decisions

The second example builds a timeline with a login success event followed by a resource denial. The goal is illustrating why **one success event does not mean every subsequent request succeeds**.

File `AuthTimelineDemo.java`:

~~~java
import java.util.List;

public class AuthTimelineDemo {

    record SecurityEvent(
            String requestId,
            String phase,
            String result) {
    }

    public static void main(String[] args) {
        List<SecurityEvent> events = List.of(
                new SecurityEvent("req-101", "AUTHENTICATION",
                        "SUCCESS:OIDC"),
                new SecurityEvent("req-102", "AUTHORIZATION",
                        "DENY:ROLE_REPORT_APPROVE"),
                new SecurityEvent("req-103", "AUTHORIZATION",
                        "ALLOW:ROLE_REPORT_VIEW"));

        for (SecurityEvent event : events) {
            System.out.println(
                    event.requestId() + " " +
                    event.phase() + " " + event.result());
        }
    }
}
~~~

Commands:

~~~bash
javac AuthTimelineDemo.java
java AuthTimelineDemo
~~~

**Exact stdout:**

~~~text
req-101 AUTHENTICATION SUCCESS:OIDC
req-102 AUTHORIZATION DENY:ROLE_REPORT_APPROVE
req-103 AUTHORIZATION ALLOW:ROLE_REPORT_VIEW
~~~

All three events can belong to the same browser session while representing different requests. This code does not read real Spring logs; it illustrates the event-correlation concept.

## 18. Spring Security Java 17: Intentional HTTP Access Rules

A Spring Boot Servlet example using OIDC login for browsers, Method Security for business services, and an explicit access-denied handler to isolate missing-permission errors. To use SAML2 instead of OIDC, configure `saml2Login(...)` with a trusted `RelyingPartyRegistration` while keeping the same URL/method security structure.

File `src/main/java/com/example/security/PortalSecurity.java`:

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class PortalSecurity {

    @Bean
    SecurityFilterChain portalChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/reports/view/**")
                    .hasAuthority("ROLE_REPORT_VIEW")
                .requestMatchers("/reports/approve/**")
                    .hasAuthority("ROLE_REPORT_APPROVE")
                .requestMatchers("/admin/**")
                    .hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .exceptionHandling(ex -> ex
                .accessDeniedHandler((request, response, denied) ->
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN)))
            .build();
    }
}
~~~

**Runtime note:** This is a Spring configuration class requiring Spring Security/Boot dependencies and configured OIDC `ClientRegistration` (issuer/client ID/client secret/redirect URI). In production, never log access tokens, ID tokens, secrets, or raw principal attributes. The browser login authentication entry point is still configured by `oauth2Login`; the explicit `accessDeniedHandler` handles legitimate denials without turning authentication failures into 403s.

### 18.1. Swapping the Flow to SAML2

When using SAML, replace:
~~~java
.oauth2Login(Customizer.withDefaults())
~~~
with:
~~~java
.saml2Login(Customizer.withDefaults())
~~~

This is a **drop-in replacement within the same Spring config**, requiring `spring-security-saml2-service-provider` and a trusted relying-party registration. Never enable/test multiple mechanisms simultaneously without a clear plan for entrypoints, request matching, and session policy.

### 18.2. Spring Boot Dependencies

POM fragment in a project using Spring Boot dependency management:

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
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

For SAML2, use the compatible `spring-security-saml2-service-provider` module instead of the OIDC-only dependency. This is not a standalone full POM; exact BOM/provider/metadata config is decided by your project.

### 18.3. Why Not Disable Filters?

When callback succeeds yet 403 occurs, never switch to `anyRequest().permitAll()` or `csrf.disable()` just to silence the error. Proper engineering identifies the root cause and fixes approved authority mapping, path matchers/tenant policies, or CSRF flows. Removing enforcement is an authentication/authorization bypass.

## 19. Debug-Only Endpoint: Inspecting `Authentication` on the Current Request

Only in **dev/test profiles**, a permission-restricted endpoint can report the `Authentication` type and authority labels. Never expose raw-claims diagnostic endpoints in production.

File `src/main/java/com/example/diagnostics/AuthDiagnostics.java`:

~~~java
package com.example.diagnostics;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("dev")
@RestController
public class AuthDiagnostics {

    @GetMapping("/internal/dev/auth-state")
    public Map<String, Object> state(Authentication authentication) {
        Map<String, Object> result = new LinkedHashMap<>();

        if (authentication == null) {
            result.put("present", false);
            return result;
        }

        result.put("present", true);
        result.put("authenticationType",
                authentication.getClass().getSimpleName());
        result.put("isAuthenticatedFlag",
                authentication.isAuthenticated());
        result.put("principalType",
                authentication.getPrincipal() == null
                    ? "null"
                    : authentication.getPrincipal()
                        .getClass().getSimpleName());
        result.put("authorityLabels",
                authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
        return result;
    }
}
~~~

**Warnings that must be followed:**
- This snippet uses Spring MVC; it is not a standalone `javac` app.
- `@Profile("dev")` only omits the bean in other profiles; **it is not an authorization guard**. Add a URL rule requiring admin authority for this route in dev and restrict network access. Never ship this endpoint in public production.
- Never return `authentication.getCredentials()`, raw `OidcIdToken`, `SAMLResponse`, user claims, or session cookies.
- `isAuthenticatedFlag=true` can also appear on `AnonymousAuthenticationToken`; inspect `authenticationType` and use an authentication trust resolver.
- Authority labels can reveal permission structure; never log/echo them to end users outside controlled environments.
- If `/internal/dev/auth-state` is blocked by `anyRequest().authenticated()`, it cannot debug anonymous requests; in dev, use safe request/trace logs rather than creating a public `permitAll` diagnostic endpoint.

### 19.1. Securing the Debug Route with an Admin Authority

In dev, add a rule **before `anyRequest().authenticated()`**:
~~~java
.requestMatchers("/internal/dev/**")
    .hasAuthority("ROLE_SECURITY_DIAGNOSTICS")
~~~

This is a fragment, not complete configuration. Diagnostic endpoints are solely for approved accounts; if debugging a user getting 403, use server-side correlation/traces instead of granting that user diagnostics privileges.

## 20. Logging the Right Layer in Spring Security

Example enabling debug temporarily only in test/dev environments:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.access: DEBUG
    org.springframework.security.authorization: DEBUG
    org.springframework.security.oauth2: DEBUG
~~~

Depending on Spring Security version and modules, exact logger names/events may vary. Do not assume every 403 logs the required role. When deeper detail is needed, use `TRACE` **briefly on a test system**, because trace logs can contain request/subject details.

**Never leave security `DEBUG`/`TRACE` on indefinitely in production.** Block logging credentials, raw Bearer tokens, `Authorization: Negotiate`, `SAMLResponse`, ID Token/refresh tokens, LDAP passwords, cookies, secrets, and sensitive PII.

### 20.1. Clues in Logs

A useful event sequence:
~~~text
[request-101] authentication_result=SUCCESS
  flow=OIDC registration=staff
  local_user_link_status=ACTIVE

[request-102] security_context=AUTHENTICATED
  auth_type=OAuth2AuthenticationToken
  url_rule=ROLE_REPORT_APPROVE
  authorization_result=DENIED
  denial_stage=HTTP_AUTHORIZATION
  response_status=403

[request-103] security_context=AUTHENTICATED
  url_rule=ROLE_REPORT_VIEW
  authorization_result=GRANTED
  response_status=200
~~~

**These are illustrative logs designed for clarity**, not default Spring output. You need instrumentation to record policy/decisions without secrets.

### 20.2. When Logs Show SUCCESS Yet Login Did Not Persist

An authentication success event or success handler execution can happen right inside the callback request. If `SecurityContextRepository`/session failed to persist properly or the browser omitted the cookie, the subsequent request is still anonymous. Therefore log **both the authn event and the auth state on the denied request** linked by appropriate correlation IDs.

## 21. Authentication Events vs. Authorization Events

Spring Security can emit events:
- `AuthenticationSuccessEvent`.
- `AbstractAuthenticationFailureEvent` and subclasses.
- `AuthorizationDeniedEvent` when configured/published at the authorization layer.
- `AuthorizationGrantedEvent` when supported by the publisher/implementation and configured.

**Important:** Event publishers, provider mechanisms, and handler wiring vary across versions/flows. Never assume every SAML/OIDC integration emits identical events at the same point. Test listeners on your actual production version and measure real logout/login/reauth flows.

### 21.1. `AuthenticationEventPublisher` Bean

Spring Security documentation example:

~~~java
package com.example.monitoring;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Configuration
public class AuthenticationEventConfiguration {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new DefaultAuthenticationEventPublisher(publisher);
    }
}
~~~

This is a Spring class with dependencies; it configures publishing for `AuthenticationManager`/providers that use the publisher by design. Do not assume every HTTP-filter or gateway failure emits the same event.

### 21.2. Listening and Classifying

~~~java
package com.example.monitoring;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;

@Component
public class AuthenticationAuditListener {

    @EventListener
    public void success(AuthenticationSuccessEvent event) {
        // Record metric/authn success with low-cardinality tags.
        // Never log credentials, tokens, or full principals.
    }

    @EventListener
    public void failure(AbstractAuthenticationFailureEvent event) {
        // Log sanitized error category; never leak username to client.
    }
}
~~~

The comments express instrumentation goals; the project needs concrete logger/metrics implementations. **Never write an event listener that mutates `Authentication` while logging.**

### 21.3. `AuthorizationDeniedEvent` Differs from `AuthenticationFailureEvent`

One user can produce:
~~~text
AuthenticationSuccessEvent(user=Alice)
AuthorizationDeniedEvent(resource=/reports/approve)
AuthorizationGrantedEvent(resource=/reports/view)
~~~

There is no contradiction: login succeeded, approve denied, view granted. When configuring publishers, prioritize logging the denial stage and policy rule; **never** increment an `authn_failure` counter for business authorization denials.

### 21.4. Micrometer/Observability

Spring Security integrates with Micrometer Observation in supported versions. Tracing should correlate:
- HTTP request ID/span.
- Authentication type/flow (bounded tags).
- Authorization decision layer.
- Denial reason category.
- Request path as a **route template** rather than raw paths containing IDs.
- SP registration/IdP category via an allowlist with controlled cardinality.
- Latency of role/IAM lookups.

Never place raw `sub`, email, `NameID`, access tokens, dynamic tenant IDs, or full resource IDs into high-cardinality metric tags. They cause metric explosions and PII leaks. Use a separate sanitized audit log when business investigations require details.

## 22. Log Table Template for Analyzing "Login Succeeded Yet 403"

A minimal dashboard should separate:

| Counter/Metric | When It Increments | Diagnostic Value |
|---|---|---|
| `authn_success_total` | Credential/protocol verification succeeded | Is IdP/protocol healthy? |
| `authn_failure_total` | Credential/protocol failed | Signature, nonce, expired token, wrong issuer? |
| `authz_denied_total` | Access policy denied | Missing role, tenant, resource? |
| `csrf_rejected_total` | CSRF token invalid/missing | POST/PUT protection issues? |
| `security_context_missing_total` | Request expected a session/token yet was anonymous | Cookie/repository/API token? |
| `authority_mapping_failure_total` | IAM/group lookup/role mapping failed | Entitlement source/config? |
| `session_expired_total` | Session timed out/invalidated | SSO loops/reauth? |
| `access_denied_by_stage_total` | HTTP, METHOD, DOMAIN, PROXY | Which root stage? |

These are **suggested metric names**, not default Spring metrics. Do not count the same authz denial twice from both filter and service as two separate 403s.

### 22.1. Authorization SLO/SLAs

Worth tracking:
- Authn success rate by IdP registration.
- 403 rate post-SSO, split between policy-denied vs. unintended missing role.
- Session persistence failures.
- Role/entitlement lookup latency and errors.
- Tenant denial counts (do not automatically treat every denial as an incident).
- False-positive denials reported by support/QA.

Never set a target of "403 must be 0"; many 403s are legitimate enforcement against unauthorized requests.

## 23. HTTP API 401/403 vs. Session-Based Web Login

If a project serves both SPA/browser routes and APIs:
- Use **separate `SecurityFilterChain`s** by path or request characteristics, with semantically matching entrypoints.
- Browser OIDC/SAML normally uses redirects + `HttpSession`.
- Bearer JWT REST APIs are normally stateless and emit `WWW-Authenticate`.
- Ensure the first chain's path matchers do not swallow callbacks/ACS or API requests belonging to the second chain.
- Never swap only an `AccessDeniedHandler` to patch broken route matching.

### 23.1. API JWT Authority Mapping

An access token carries scopes:
~~~text
scope: reports.read profile
~~~

Spring Resource Server normally maps scopes to:
~~~text
SCOPE_reports.read
SCOPE_profile
~~~

If the API rule requires `ROLE_REPORT_VIEW`, a 403 may be an **authorization mapping mismatch**, not an invalid JWT. Choose:
- API rule `hasAuthority("SCOPE_reports.read")` if the scope is trusted by the resource server and fits the contract; or
- Map trusted scopes/permissions to domain authorities via a converter with issuer/audience policies.

Never let users supply arbitrary `ROLE_ADMIN` in a JSON body/header to augment JWT authorities.

### 23.2. Valid Token Yet Wrong Audience

A JWT with a valid signature yet wrong `aud` must be rejected by authentication token validation when an audience policy is configured. Never classify a wrong-audience error as "missing role" just because the UI shows 403. Inspect the security chain and token validation outcome.

## 24. Authority Mapper, Group Lookup, and Local Identity Link Failures

Causes of 403 despite successful SSO:
1. Group claim absent in ID Token/UserInfo/Assertion.
2. App reads the wrong claim name or schema.
3. External identity `iss+sub`/SAML stable ID fails to map to the right local user.
4. Reading direct LDAP/AD groups without resolving nested groups.
5. Group IDs changed/different realm while allowlist is stale.
6. Disabled local account or inactive tenant membership.
7. Role was revoked yet the session cache still holds a stale snapshot.
8. Role granted yet app code checks a differently named authority.
9. URL role passes yet domain service checks ownership.
10. `AuthorizationManager` rule ordering/path mismatch.
11. `MethodSecurity` config enforces rules differing from HTTP matchers.
12. AOP proxy bypassed or annotation placed on the wrong method.
13. API sent the wrong access token/scope.
14. Role lookup timed out, failing closed (correct security behavior).
15. Frontend cached stale role state or has a buggy UI guard.

### 24.1. Principles for Fixing Mapping

Recommended pipeline:
~~~text
Verified IdP identity (with issuer/realm)
       |
       v
Approved identity link -> localUserId
       |
       v
Local account active/locked/tenant membership
       |
       v
Trusted group/role entitlement lookup
       |
       v
Allowlisted mapper -> GrantedAuthorities
       |
       v
SecurityContext + HTTP/method/domain authorization
~~~

If IdP authentication already succeeded, there is no need to reconfigure SAML signing keys or disable OIDC validation to fix a missing role. Fix the source mapping or policy with proper approval, test cases, and audit.

### 24.2. Revoked Permissions and Stale Sessions

`Authentication` may retain an authority snapshot until the session refreshes or is invalidated. For instance, Alice's permission was removed in AD yet her existing session still holds `ROLE_REPORT_APPROVE`; that is an **over-authorization risk**, the opposite of a missing-authority false deny. Enforce TTLs, revocation events, session invalidation, or live entitlement checks for sensitive actions per risk.

## 25. Initial State and Controlled Bug Reproduction

To debug a user issue:
1. Record request ID and exact timestamp.
2. Identify login mechanism: OIDC, SAML, Kerberos, CAS, LDAP, or JWT Bearer.
3. Identify callback endpoint and result.
4. Check browser Network/redirect chain and cookie flags **without copying tokens/cookies into the ticket**.
5. Record the exact request returning 403: method, route, matched chain, resource type.
6. Inspect auth type/context on that request via controlled server-side debugging.
7. Compare actual authority labels (sanitized) against required policy.
8. Check tenant/resource membership.
9. Check CSRF/CORS/gateway before editing roles.
10. Check recent changes to IdP metadata, role mappers, IAM groups, and authorization config.
11. Reproduce in a test environment using a synthetic principal and equivalent scopes/roles.
12. Add tests before fixing, then run authn/authz regression suites.
13. Record root cause: `AUTHN_FAILED`, `SESSION_MISSING`, `AUTHZ_DENIED_HTTP`, `AUTHZ_DENIED_METHOD`, `AUTHZ_DENIED_DOMAIN`, `CSRF_DENIED`, `CORS_DENIED`, or `PROXY_DENIED`.

### 25.1. Never Ask Users to Send Tokens for Debugging

Support should request:
- Correlation/request ID.
- Timestamp and functional route.
- Displayed error message.
- Environment, browser, and reproducibility.

**Never** ask users to send raw `SAMLResponse`, ID Tokens, access tokens, refresh tokens, Kerberos tickets, session cookies, passwords, or private keys.

## 26. Test Cases: Valid Authn vs. Missing Authz

| ID | Scenario | Expectation |
|---|---|---|
| A01 | Valid OIDC login, no app role | Login succeeds, restricted resource 403 |
| A02 | Valid signed SAML, account role `REPORT_VIEW` | View 200, approve 403 |
| A03 | Invalid SAML signature | Authentication fails, no trusted local session |
| A04 | Invalid OIDC issuer/audience/nonce | Authentication fails |
| A05 | Missing session cookie after login redirect | Next request anonymous → login challenge |
| A06 | Missing Bearer JWT | API 401/challenge |
| A07 | Valid JWT yet missing `SCOPE_reports.read` | API 403 |
| A08 | User has `ROLE_REPORT_VIEW` | `/reports/view` allowed |
| A09 | User lacks `ROLE_REPORT_APPROVE` | `/reports/approve` 403 |
| A10 | User has admin role yet resource tenant mismatches | Domain access denied |
| A11 | GET allowed, POST missing CSRF | CSRF 403, do not blame roles |
| A12 | OPTIONS blocked by proxy/CORS | Preflight denial, do not blame IdP |
| A13 | Browser saved URL `/admin`, login succeeds | Final `/admin` 403 if lacking `ROLE_ADMIN` |
| A14 | Role prefix mismatch | Deny; fix matcher/mapper convention |
| A15 | OIDC groups claim present yet unmapped by mapper | Deny, never auto-grant `ROLE_ADMIN` |
| A16 | SAML Assertion attrs outside signed coverage | Reject authentication, assign no roles |
| A17 | Valid Kerberos ticket, local user disabled | Deny local account/authorization |
| A18 | LDAP bind succeeds, role lookup returns none | Authenticated yet restricted URL denied |
| A19 | `@PreAuthorize` denies after HTTP permit | Method-level denial |
| A20 | Internal service call bypasses AOP proxy | Security regression; never treat "allow" as right |
| A21 | Role removed after session creation | Test revocation/invalidation SLA |
| A22 | Two filter chains match route wrongly | Diagnose selected chain |
| A23 | Valid IdP yet identity link conflict | Reject local account mapping |
| A24 | `AnonymousAuthenticationToken.isAuthenticated()` true | Do not treat as SSO login |
| A25 | Remember-me insufficient for sensitive method | Require full/step-up auth policy |
| A26 | Business service throws `AccessDeniedException` | Expected 403/deny per HTTP boundary |
| A27 | User belongs to `tenant-a`, resource in `tenant-b` | Deny even with global role |
| A28 | CDN/WAF returns 403; app receives no request | Fix gateway, not role mapper |
| A29 | Success handler redirects to wrong URL | Fix saved-request/redirect config |
| A30 | Right entitlement yet stale frontend role cache | Server policy wins; refresh UI view |

### 26.1. MockMvc Test Example with Authorities

File `src/test/java/com/example/ReportAccessTest.java` (fragment inside a Spring Boot test project containing `/reports/view/demo` and `/reports/approve/demo` endpoints):

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readerCanViewButCannotApprove() throws Exception {
        mvc.perform(get("/reports/view/demo")
                .with(user("synthetic-user")
                    .authorities(() -> "ROLE_REPORT_VIEW")))
            .andExpect(status().isOk());

        mvc.perform(get("/reports/approve/demo")
                .with(user("synthetic-user")
                    .authorities(() -> "ROLE_REPORT_VIEW")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Preconditions:** Test controllers/services must genuinely exist, and URL matching and `SecurityFilterChain` must align; missing endpoints may return 404. `.authorities(() -> "ROLE_REPORT_VIEW")` injects a mock `GrantedAuthority` for business authorization tests; this test does **not** verify a real OIDC token or `SAMLResponse`. You can use `saml2Login()` or `oidcLogin()` test post-processors for interface/authorization tests, while separate integration tests are required for protocol verification.

### 26.2. Anonymous Tests Differ from Unauthorized Tests

For browser OAuth2 Login, an anonymous GET to a protected URL may redirect **302**, not 401. On an API bearer chain, an anonymous GET normally returns 401. Assert the expected HTTP status per chain rather than copying a single 401 check across every mechanism.

### 26.3. Testing CSRF Independently

In a session-cookie browser app:
- Authorized GET can pass.
- POST without CSRF returns 403.
- Only POST with a valid CSRF token reaches authorization/business code.
- CSRF tests require `with(csrf())` in Spring MockMvc where appropriate.

If you want to verify a POST is denied due to a missing role, **supply a valid CSRF token** so the denial actually tests the role rather than getting stopped earlier by `CsrfFilter`.

## 27. Symptom-Based Troubleshooting Matrix

| Symptom | Possible Root Cause | Check Point |
|---|---|---|
| Login callback succeeds, `/admin` 403 | Missing `ROLE_ADMIN` | Actual authorities vs. matcher |
| Login callback succeeds, `/me` 302 login | Session not persistent | Cookie, `SecurityContextRepository` |
| Spring logs 403 on POST, GET OK | CSRF token | `CsrfFilter`/request method |
| API GET 401 despite browser OIDC login | JWT bearer/token not sent | Right `SecurityFilterChain` |
| API 403 with valid token | Missing scope/authority | `JwtGrantedAuthoritiesConverter` and policy |
| Has `OIDC_USER` yet lacks `ROLE_USER` | Mapper not mapping | Approved IdP groups/local roles |
| Has SAML attribute groups yet empty roles | Provider mapper not mapping | Verified attrs + allowlist |
| Right role yet still 403 | Tenant/owner policy | Domain authorization |
| `hasRole("ADMIN")` fails | Missing `ROLE_ADMIN` or prefix mismatch | Naming conventions |
| 403 only on `@PreAuthorize` endpoint | Method-level enforcement | AOP proxy + authority |
| Browser loops redirects continuously | Cookie/`SameSite`/secure issue | Redirect chain/session |
| 403 on `OPTIONS` | CORS/security proxy | Preflight, allowed origins |
| Role changed yet session did not update | Stale authorities snapshot | Cache invalidation/reauth |
| Account disabled yet still logs in | Missing local account policy | Identity-link/account check |
| OIDC IdP A login mapped to IdP B user | Broken issuer/sub linking | Namespaced identity + tenant |
| SAML callback signature error | Authentication failure | IdP cert/metadata, not roles |
| Frontend reports missing role yet server allows | Stale UI state | Align client/server policy |
| One node OK, another 403 | Config/session store drift | Pod roles/cert/session |
| Gateway returns 403 with no Spring log | WAF/API gateway | Proxy and upstream tracing |
| Browser SSO works, JavaScript API 401 | fetch credentials/cookie/token | Cross-origin policy |
| Auth `SuccessEvent` seen yet endpoint 403 | Expected authn/authz split | Denied event + matched rule |
| AuthService/LDAP outage | Role lookup fails closed | IAM dependencies/timeouts |
| All requests 403 including public health | Wrong chain/default rule | `SecurityFilterChain` ordering |
| POST with csrf passes yet 403 remains | Actual method/role/tenant check | `@PreAuthorize`/business service |
| Unknown redirect URL after login | `SavedRequest`/`targetUrl` config | `RequestCache`/`SuccessHandler` |

## 28. Dangerous Anti-Patterns

1. **Seeing 403 and disabling SAML/OIDC signature validation.** Does not fix roles and creates an auth bypass.
2. **Granting `ROLE_ADMIN` to every login to avoid 403.** Breaks least privilege.
3. **Setting `permitAll()` app-wide** when only one endpoint fails.
4. **Disabling CSRF system-wide** because one POST lacked a CSRF token.
5. **Trusting `auth.isAuthenticated()` without checking anonymous** when deciding SSO login.
6. **Reading arbitrary `groups` claims from browser requests** and turning them into `GrantedAuthority`.
7. **Reading raw `SAMLResponse`** and picking an unsigned NameID/role.
8. **Auto-linking local accounts by email** from an unapproved IdP.
9. **Removing tenant/owner checks** just so role-level returns 200.
10. **Counting every 302 login redirect as login success** without checking callback context.
11. **Counting every 403 as an authentication failure** in metrics.
12. **Logging raw ID/access/refresh tokens or session cookies** in support tickets.
13. **Leaving Security `TRACE` enabled across production indefinitely.**
14. **Changing `AccessDeniedHandler` to return 200** so the UI stops showing errors.
15. **Self-refreshing roles from user-controlled headers.**
16. **Relying on frontend route guards** instead of server-side authorization.
17. **Checking only scopes when API policy requires tenant/ownership.**
18. **Accidentally merging multiple `SecurityFilterChain`s** leading to mismatched entrypoints.
19. **Extending session lifetime indefinitely** to avoid re-login.
20. **Deleting failure tests** after fixing a role mapping.

**The proper fix** is proving the root cause and preserving the authentication/authorization boundary.

## 29. Checklist Before Concluding "Missing Permissions"

- [ ] Distinguished SSO callback from the post-callback resource request.
- [ ] Identified request URL/method/status/response source.
- [ ] Identified the exact `SecurityFilterChain` and entrypoint.
- [ ] Confirmed `Authentication` is present in `SecurityContext` on the failing request.
- [ ] Distinguished authenticated user from anonymous/remember-me.
- [ ] Confirmed session cookie/`Authorization` header was sent properly.
- [ ] Inspected `SavedRequest`/post-login redirect target.
- [ ] Captured actual `GrantedAuthorities` (sanitized) and required authorities.
- [ ] Confirmed `hasRole`/`hasAuthority` and `ROLE_` prefix consistency.
- [ ] Mapped OIDC scopes/roles properly without mistaking `SCOPE_` for `ROLE_`.
- [ ] Mapped verified SAML attributes from a trusted assertion.
- [ ] Verified Kerberos principal/realm/LDAP group lookup does not confuse users.
- [ ] Verified local user identity link is approved and account is active.
- [ ] Checked tenant membership and resource ownership.
- [ ] Confirmed `@EnableMethodSecurity` is active and `@PreAuthorize` runs through the proxy.
- [ ] Ruled out CSRF token issues when a POST returns 403.
- [ ] Checked CORS/OPTIONS and gateway 403s.
- [ ] Confirmed IAM/AD group caches and session authorities are not stale.
- [ ] Separated authn success/failure from authz denials in logs/metrics.
- [ ] Verified logs contain no tokens, passwords, raw claims, or sensitive PII.
- [ ] Tests cover 302/401/403, role mapping, tenant, method, CSRF, and multi-IdP.
- [ ] All role/policy changes have approval/audit trails.
- [ ] No security controls disabled to mask symptoms.

## 30. Review Questions

1. **Does successful login grant access to every URL?** No.
2. **What does authentication answer?** Who the caller is and whether credentials/protocol are valid.
3. **What does authorization answer?** Whether the identity is allowed to perform a specific action/resource access.
4. **What should you check on 403 after an OIDC callback?** `SecurityContext`, authorities, matchers, and tenant/method/resource policies.
5. **How do 401 and 403 differ?** 401 normally challenges for credentials; 403 normally denies permissions once authenticated, though handlers/contexts can vary.
6. **Does a 302 to login prove authentication failed?** No; inspect the redirect and callback outcome.
7. **What is `RequestCache` for?** Saving the original request to redirect back after login.
8. **What does `ExceptionTranslationFilter` do?** Translates `AuthenticationException`/`AccessDeniedException` into entrypoint/denied responses.
9. **What does `AuthorizationFilter` do?** Uses `AuthorizationManager` to enforce URL request rules.
10. **How does `AuthenticationEntryPoint` differ from `AccessDeniedHandler`?** One starts authentication; the other handles denials when the caller is already authenticated per trust policy.
11. **Does `isAuthenticated() == true` always mean a real user?** No, `AnonymousAuthenticationToken` can also return true.
12. **Does holding `OIDC_USER` grant `ROLE_ADMIN`?** No.
13. **Is `SCOPE_profile` equivalent to `ROLE_REPORT_VIEW`?** No.
14. **Does a signed SAML success automatically grant business roles?** No; attributes/local entitlements must be mapped.
15. **What happens with a valid Kerberos ticket when groups are unmapped?** Login may succeed yet restricted routes deny access.
16. **Which authority does `hasRole("ADMIN")` require by default?** `ROLE_ADMIN`.
17. **Can a URL rule pass while `@PreAuthorize` denies?** Yes.
18. **Can a CSRF 403 be fixed by adding roles?** No.
19. **What can cause 403 on `OPTIONS`?** CORS/preflight/gateway rules.
20. **Why does `/me` work while `/admin` fails?** The two endpoints have different policies.
21. **What if a user holds a global role yet belongs to a different tenant?** Resource-level tenant checks still deny.
22. **Why are a success event and a denied event both valid together?** They measure two different stages.
23. **Does a browser login session automatically authenticate a stateless API?** No if the API requires a bearer token and the request omits it.
24. **Callback login passes yet the next request is anonymous?** Check cookie/session/repository/chain first.
25. **Do role changes in IAM update an existing `HttpSession` immediately?** Not by default.
26. **Does a MockMvc `user()` test prove IdP token signatures?** No.
27. **Should full production `TRACE` be enabled for debugging?** No; risks leaking tokens/PII.
28. **Should you add `permitAll` first upon hitting 403?** No; identify the denial rule and root cause.
29. **Is a Java 17 decision-model snippet a real Spring filter?** No; it illustrates logic only.
30. **What does accurate diagnosis need most?** Correlation between login callback and failing request, `Authentication`, `GrantedAuthorities`, exact policy, and denial source.

## 31. Official Reference Documentation

- Spring Security – Servlet Architecture, filter chain and ExceptionTranslationFilter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – Authorize HTTP Requests, AuthorizationFilter: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security (@EnableMethodSecurity, @PreAuthorize): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security – OAuth2 Login Advanced Configuration/GrantedAuthoritiesMapper: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security – OAuth2 Login Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML2 Response Authentication: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security – MockMvc Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security – Micrometer Observability: https://docs.spring.io/spring-security/reference/observability/index.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Summary:** A federated login flow may complete cleanly in cryptography and protocol terms while Spring still **rightfully returns 403** on an endpoint where the principal lacks a `GrantedAuthority`, has the wrong tenant, fails `@PreAuthorize`, or violates CSRF/business policies. To debug, trace the chain **authentication callback → persisted `SecurityContext` → post-login request → exact `AuthorizationManager`/method/domain policy → denial source**, and fix the real cause. Never "fix 403" by disabling authentication, granting broad admin roles, dropping CSRF, or enabling trust-all. Observing authn success/failure separately from authz denials distinguishes genuine login outages from a system enforcing permissions properly.
