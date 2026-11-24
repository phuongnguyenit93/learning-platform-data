# Handling missing headers, user switching, and stale sessions in proxy authentication

## 1. Context and objectives

In the **Spring Security – federation** architecture, many applications do not collect passwords themselves or perform browser OIDC/SAML challenges. Instead, a **reverse proxy / identity-aware proxy / access gateway** authenticates the user upstream and forwards identity information to the backend via **managed HTTP headers**.

Example:

~~~text
Browser
   |
   | Gateway / external SSO cookie
   v
Trusted Identity Gateway / Reverse Proxy
   | - enforce OIDC/SAML/Kerberos/enterprise SSO login
   | - verify upstream session still valid
   | - STRIP client-supplied identity headers
   | - emit trusted identity header to backend
   v
Spring Boot Application
   | - RequestHeaderAuthenticationFilter
   | - PreAuthenticatedAuthenticationProvider
   | - UserDetailsService / authorization
   | - may store SecurityContext in HttpSession
   v
API / Database / Business Operations
~~~

Typically the gateway emits a header representing the user, for example:

~~~http
X-Authenticated-Subject: employee-42
~~~

**A header is not cryptographic proof on its own.** Spring Security pre-authentication **assumes an upstream system already authenticated the user and protected the path**. If an app accepts arbitrary headers directly from the Internet, an attacker can send `X-Authenticated-Subject: admin` to impersonate them.

This lesson belongs to the **Proxy Authentication** group, addressing three tricky yet common situations:

1. **Missing header:** the gateway omits the header because upstream SSO expired, the request took the wrong route, middleware dropped the header, or a client called the backend directly. Even if the browser still holds `JSESSIONID`, the app **must never retain the old identity** merely because a local session still exists.
2. **Header switches users:** the gateway starts reporting `bob` instead of `alice` due to account switching, re-authentication, upstream cookie change, or identity relinking. The app must **prevent Alice's session/roles from being used on Bob's request**, never silently continuing with the old SecurityContext.
3. **Stale session persists:** Spring SecurityContext/`HttpSession`/Spring Session retains an Authentication from an earlier request; this can happen when upstream logs out without notifying the app, cookies remain, a user is locked, or roles/tenants change.

After this lesson you should know how to:

- Clearly separate **gateway identity**, **request headers**, **SecurityContext**, and **HttpSession**; each has a distinct lifecycle and owner.
- Read the exact behavior of `RequestHeaderAuthenticationFilter` and `AbstractPreAuthenticatedProcessingFilter`, especially `setExceptionIfHeaderMissing`, `setCheckForPrincipalChanges`, `setInvalidateSessionOnPrincipalChange`, and `setContinueFilterChainOnUnsuccessfulAuthentication`.
- Configure **fail-closed** handling on missing/blank/duplicate headers, even when the request carries an old session cookie.
- Handle identity changes by **re-authenticating and rotating/invalidating sessions**, never inheriting old authorities or business caches onto a new account.
- Distinguish **username/display name** from a stable identity key **issuer + tenant + subject**, adding **upstream session ID** when needed.
- Choose **stateful** or **stateless per-request** deliberately without mixing policies accidentally.
- Build a test matrix and runbook prior to production.

**Rule:** access for each request must derive from the **currently verified upstream identity** plus **appropriate local session/authorization state**, never merely from an Authentication cached in an old session.

## 2. Components and what may be trusted

| Artifact | Where created/stored? | What is it used for? | Sufficient to grant access? |
| --- | --- | --- | --- |
| **Gateway SSO session** | Identity proxy/OP/IdP | Determines whether the browser is currently logged into the gateway | Only the gateway can confirm |
| **Trusted identity header** | Emitted by gateway after auth and sanitization | Carries principal/claims to backend | **Only when the gateway→backend channel is protected** |
| **Client-supplied header** | Browser/API caller | Arbitrary HTTP input | **No**, must be stripped before backend |
| **Spring Authentication** | SecurityContext after pre-auth provider | Current principal + GrantedAuthorities | Must correspond to a still-valid upstream identity |
| **HttpSession / JSESSIONID** | Spring app, session store, browser cookie | Persists app state/SecurityContext | **Does not** substitute for proof of active gateway login |
| **Spring Session store** | Redis/JDBC/... | Session state shared across replicas | May hold stale Authentication |
| **UserDetails/local roles** | Application DB/LDAP/authorization service | User status, tenant, roles, business privileges | Must enforce freshness and scope policies |
| **Logout/revocation event** | Gateway/IdP/session registry | Signals identity session termination | Useful only if delivered and processed |
| **API bearer token** | Issuer/resource server | Authenticates API independently of gateway headers | Does not automatically share lifecycle with browser sessions |

A classic mental trap is: "The header is just to create the session initially; after that the cookie alone suffices." That is **true only under an explicit delegation design**, such as when the gateway/API intentionally lets the app manage an independent session with an acceptable lifetime. For **pre-auth requiring gateway verification on every request**, keeping privileges from an old session when the header disappears is a security bug.

### 2.1. Real flow with two session layers

~~~text
Call 1: Gateway holds upstream session A
          -> X-Authenticated-Subject: alice
          -> App creates SecurityContext = alice, HttpSession S1

Call 2: Gateway still authenticates alice
          -> header alice
          -> Browser sends JSESSIONID=S1
          -> App continues if identity and policy are consistent

Call 3: Gateway loses auth / emits no header
          -> Browser still sends JSESSIONID=S1
          -> App MUST NOT use SecurityContext=alice to grant access

Call 4: Gateway authenticated bob instead of alice
          -> header bob
          -> Browser still sends JSESSIONID=S1
          -> App must invalidate/rotate S1 and treat bob as new session
~~~

**Missing header** and **lingering old session cookie** are independent observations. Browsers can hold cookies longer than gateway SSO, or users can open multiple tabs and switch accounts.

## 3. Trust boundary: only the gateway creates identity headers

Before analyzing Spring Security behavior, an infrastructure boundary is **mandatory**:

~~~text
Internet request:
  X-Authenticated-Subject: admin   # attacker self-added

Gateway:
  - strip X-Authenticated-* from client
  - authenticate SSO session/token
  - if valid, set X-Authenticated-Subject to verified identity
  - if invalid, 401/redirect login; do not forward stale header

Backend:
  - accept traffic only from trusted gateway/sidecar
  - mTLS/private routing/service identity/network policy
  - never treat direct traffic carrying headers as trusted
~~~

**`RequestHeaderAuthenticationFilter` checks neither signatures nor passwords on the header.** Spring Security's Javadoc states plainly: the filter only reads a username from a header, relying completely on an external authentication system. Putting this filter on a backend directly reachable from the Internet is dangerous.

Controls at gateway and network layers:

- Strip every possible client-sent identity header name, including **duplicates, case variants, underscore/dash variants, and forwarded headers** that proxy stacks may normalize differently.
- Emit **one single principal header**, never passing raw user input back as the principal.
- Block **direct-to-backend** paths using network policies, firewalls, mTLS, or controlled service-mesh identities.
- With multiple gateways, every gateway must enforce the exact same issuer/tenant/header contract and trust config; never mix trusted and untrusted paths.
- Never use `X-Forwarded-For` or raw source IP checks across an untrusted proxy chain as proof the user logged in.
- Have the gateway verify the **upstream session/token at the committed cadence**; never emit headers from a logged-out upstream cookie due to bad gateway caching.
- Never leak identity headers into public logs or unauthorized downstream calls.
- When signed identity assertions are required, use JWT/PASETO or a format signed by the gateway where the backend verifies issuer/audience/expiry/replay per profile; **plain-text headers and `RequestHeaderAuthenticationFilter` do not do this**.

### 3.1. Do not use arbitrary ungoverned header names

`RequestHeaderAuthenticationFilter` Javadoc defaults `principalRequestHeader="SM_USER"` for CA SiteMinder compatibility. These examples use:

~~~text
X-Authenticated-Subject: employee-42
~~~

This name is an **illustrative application convention**, not a mandatory Spring/OIDC standard. Real systems must standardize name, issuer, encoding, byte length, duplicate handling, and value format across the gateway, proxy chain, and app.

### 3.2. Use stable subjects instead of email/display name

When the gateway has upstream OIDC:

~~~text
Issuer:  https://identity.example.test/realms/company
Tenant:  business-a
Subject: 67e2a83f-...
Email:   alice@example.test
~~~

Bind identity by **(issuer, tenant, sub)** or a governed key. **Email/display name** can change, be recycled, or collide across tenants; they should not be the default session-binding key in multi-IdP designs.

If the gateway sends separate `X-Authenticated-Subject` and `X-Authenticated-Tenant` headers, the backend must verify the **entire tuple** came from a verified gateway. Checking `Authentication.getName()` for subject alone while ignoring tenant can mix sessions.

## 4. What does RequestHeaderAuthenticationFilter actually do?

Spring Security provides:

~~~text
org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter
~~~

It extends:

~~~text
AbstractPreAuthenticatedProcessingFilter
~~~

and typically pairs with:

~~~text
PreAuthenticatedAuthenticationProvider
  + AuthenticationUserDetailsService
  + UserDetailsByNameServiceWrapper / appropriate user-details provider
~~~

Fresh flow (no prior Authentication):

~~~text
Incoming HTTP request having passed trusted gateway
   |
   v
RequestHeaderAuthenticationFilter
  getPreAuthenticatedPrincipal()
     -> X-Authenticated-Subject
  getPreAuthenticatedCredentials()
     -> "N/A" if credentialsRequestHeader not configured
   |
   v
PreAuthenticatedAuthenticationToken (initial request)
   |
   v
AuthenticationManager / ProviderManager
   |
   v
PreAuthenticatedAuthenticationProvider
  -> AuthenticationUserDetailsService
  -> load/check user mapping and authorities per policy
   |
   v
Authenticated Authentication
   |
   v
SecurityContextHolder + SecurityContextRepository
   |
   v
AuthorizationFilter -> business endpoint
~~~

**`PreAuthenticatedAuthenticationProvider` does not verify on its own that the user truly logged in at the gateway.** It primarily loads UserDetails based on external authentication asserted by the gateway. A user existing in the database **is not proof the header is valid** if network trust is broken.

### 4.1. Default header behavior

Per current Spring Security Javadoc:

- Defaults to reading username from header **`SM_USER`**.
- When the header **does not exist**, `getPreAuthenticatedPrincipal` **throws `PreAuthenticatedCredentialsNotFoundException`** under the default `exceptionIfHeaderMissing=true`.
- You can set `setExceptionIfHeaderMissing(false)` so a missing header returns **null**, though that **does not by itself mean fail closed**.
- Without a credentials header, `getPreAuthenticatedCredentials` normally returns **`"N/A"`**; that is **not a user secret/password**.
- The filter **performs no real authentication**; all assurance lives at the proxy.

### 4.2. The "skip if already authenticated" default is critical

`AbstractPreAuthenticatedProcessingFilter` Javadoc notes: if `SecurityContext` **already contains an Authentication**, the filter **does nothing by default**. To compare principals on every request, you must enable:

~~~java
filter.setCheckForPrincipalChanges(true);
~~~

If left at the default without checking:

~~~text
Request 1:
  header = alice, no local session
  -> create Authentication=alice, session S1

Request 2:
  header = bob, cookie still S1
  -> SecurityContext of S1 is still alice
  -> default filter may SKIP re-authentication
  -> backend still sees Authentication=alice
~~~

This is a form of **stale principal / account confusion**. Never assume "if a new header arrives, the filter surely re-runs".

### 4.3. Authentication errors and continuing the filter chain

Also per Javadoc, if `AuthenticationManager` throws `AuthenticationException` during pre-auth:

~~~java
filter.setContinueFilterChainOnUnsuccessfulAuthentication(false);
~~~

can let the exception propagate instead of silently letting the filter chain continue and try another authentication mechanism. However:

- By default `continueFilterChainOnUnsuccessfulAuthentication` is **true** to allow other mechanisms to attempt authentication.
- **`false` does not handle cases where principal returns null**, since the filter may not start authentication and the chain proceeds.
- **`false` also fails to catch missing headers when the filter skips completely because SecurityContext is already authenticated**.
- Exceptions must translate to proper HTTP 401/403 via filter/error/entrypoint integration; never assume every throw is handled cleanly by Spring if thrown before `ExceptionTranslationFilter`.
- In **proxy-only** systems, avoid unapproved form login/HTTP Basic fallbacks: they can turn gateway failures into weaker authentication bypasses.

**Section takeaway:** setting `setCheckForPrincipalChanges(true)` and `setContinueFilterChainOnUnsuccessfulAuthentication(false)` is valuable, yet to guarantee **missing header + old session gets invalidated**, pair them with a **request-boundary guard** checking the header before restored SecurityContext is used for authorization.

## 5. Missing header with lingering old session cookie: failing closed

### 5.1. Failure scenario

~~~text
T0: alice logs in via gateway -> proxy header alice -> app session S1.
T1: alice logs out upstream, gateway clears SSO cookie.
T2: Browser still holds app JSESSIONID=S1.
T3: Request arrives at backend:
      Cookie: JSESSIONID=S1
      X-Authenticated-Subject: [MISSING]
T4: If relying solely on S1:
      Spring SecurityContextHolder may load Alice
      Authorization still treats request as authenticated
~~~

**Expected:** reject the request, **never serving data under Alice's identity**. If policy mandates the header on every protected request, invalidate local session S1, clear the old security context, and require re-login at the gateway. Never proceed to business controllers.

### 5.2. Header states that all need handling

| Header on request reaching backend | Assessment |
| --- | --- |
| Header name absent | **DENY**, never use old local session |
| Header name present yet empty value | **DENY** |
| Whitespace only | **DENY** |
| Multiple same-named headers with two values | **DENY**, never pick "first value" |
| Single header with comma-joined value like `alice,bob` | **DENY** when contract allows one subject, avoiding coalescing ambiguity |
| Header containing CR/LF/control chars | **DENY**; gateway must reject too |
| Valid format yet arriving over direct/untrusted connection | **DENY**; never check strings alone |
| Valid header from trusted gateway | Not enough without tenant/account/session binding and authorization |
| Header Alice, session Bob | **DENY old session**, re-authenticate/rotate |
| Header Alice, session Alice yet upstream SSO logged out | Accept only if gateway **genuinely** asserts an active session; otherwise deny |

**Never call `request.getHeader(...)` to take the first string and ignore duplicates**. Proxies and Servlet containers handle duplicate headers, case folding, and comma coalescing differently. Gateway and backend need **one single contract**: strip client headers, one single value, explicit format and length limits.

### 5.3. Fail-closed pattern for session-backed apps

When the guard determines **no trusted upstream identity is present**:

1. **Never run business controllers** or authorization against the old Authentication.
2. If a local `HttpSession` exists: call `invalidate()` to purge `SecurityContext`/`SavedRequest` and session-scoped state.
3. Clear `SecurityContext` for the current request/thread according to filter placement; if the guard runs **before `SecurityContextHolderFilter`**, invalidation happens **before the old context is restored**.
4. If the context was already loaded, both clear the context and invalidate/save an empty context per Spring Security version; **never call only `SecurityContextHolder.clearContext()` while the repository still holds the old Authentication**.
5. Respond with **401 Unauthorized** when re-authentication is needed, or **403 Forbidden** for unauthorized identities/trust violations per API contract; avoid redirect loops.
6. Optionally clear the browser's `JSESSIONID` cookie with exact Path/Domain/SameSite/Secure if the app manages cookies; server-side `invalidate()` is what prevents session reuse—clearing only the browser cookie is insufficient.
7. Log **reason code + correlation ID**, never raw identities/SSO tokens.

### 5.4. What if the header is missing due to a proxy error rather than logout?

Still fail closed, then fix the infrastructure. **Never use an old local session as an "offline fallback mode"** unless it is an explicit **business continuity mechanism** with its own policy/TTL/assurance, risk assessment, and tests. By default assume the identity header is mandatory per request.

## 6. Header switches users: never inherit sessions or privileges

Example:

~~~text
Request A:
  Trusted gateway identity = (issuer=corp, tenant=A, sub=alice)
  App session S1 = alice, roles=[ROLE_FINANCE_READER]

Request B:
  Trusted gateway identity = (issuer=corp, tenant=A, sub=bob)
  Browser still sends Cookie JSESSIONID=S1
~~~

There are two valid strategies **when explicitly designed**:

- **Reject-on-change (simpler, stricter):** invalidate S1, return 401, and require a fresh login/session flow; Bob's request **cannot see any of Alice's data**.
- **Reauthenticate-and-rotate:** invalidate or replace the entire authentication/session identity; re-run provider/local authorization for Bob, create/rotate a new session, and discard all old principal-specific state. Requires **atomicity** and session fixation protection.

What you **must never do**:

~~~text
SecurityContext still holds alice
Current header = bob
-> controller reads alice's profile/permissions/session cache
-> returns alice's data to browser acting as bob
~~~

### 6.1. Spring provides an API to detect principal changes

~~~java
filter.setCheckForPrincipalChanges(true);
filter.setInvalidateSessionOnPrincipalChange(true);
~~~

`AbstractPreAuthenticatedProcessingFilter` Javadoc explains that when `checkForPrincipalChanges` is enabled, the filter compares the incoming header principal against the existing `Authentication.getName()`, re-authenticating on change. `invalidateSessionOnPrincipalChange` defaults to **true** when this check runs; setting it explicitly in code clarifies security intent for reviewers.

**Yet understand the limitations:** default comparison relies primarily on **principal name**; it **does not automatically detect** when:

- Two tenants share the same subject/email under different issuers.
- The upstream session ID changed while the subject stayed identical.
- The user was locked or changed role groups without changing principal name.
- The gateway switched OP/IdP aliases with colliding usernames.
- The IdP changed authentication assurance while keeping the same display name.

If your system has those requirements, extend identity-binding checks **before authorization** with verified issuer/tenant/subject/session rather than relying on name alone.

### 6.2. Never use email to detect user switches across multiple IdPs

Example:

~~~text
Gateway before:
  issuer = https://idp-a.example.test
  tenant = alpha
  subject = e7cf...
  email = manager@example.test

Gateway after:
  issuer = https://idp-b.example.test
  tenant = beta
  subject = 5b02...
  email = manager@example.test
~~~

Matching emails **do not prove two principals are the same person**. Store local bindings keyed by **(trusted issuer, tenant, stable subject)** with an account-linking policy for merges. Requests carrying an old session must be rejected/rotated whenever the binding changes.

## 7. Same user yet upstream session changed: another boundary

When the proxy supports a trusted session claim, e.g.:

~~~text
X-Authenticated-Issuer: corp-sso
X-Authenticated-Tenant: tenant-a
X-Authenticated-Subject: alice-001
X-Authenticated-Session: upstream-session-7
~~~

If the identity stays Alice while `upstream-session-7` changes to `upstream-session-8`, comparing only the name Alice sees "no change". For shared-device setups or strict session-freshness requirements:

- Bind local session S1 to the **verified upstream session ID**.
- When the ID changes, invalidate S1 and issue a new session per policy.
- Never let browser-controlled queries/headers dictate session binding.
- If upstream provides no trusted session ID, do not invent one from IP, User-Agent, or email; use **session epochs/token expiry and back-channel logout** if available, or strict session policies.
- Never store raw upstream session tokens/cookies in `HttpSession`; store an **opaque binding ID/hash or internal session reference** as needed.
- If the RP/gateway learns a session was revoked, local sessions must be invalidated/blocked within the system's SLA.

**Note:** `X-Authenticated-Issuer/Tenant/Session` headers are **illustrative conventions**, not universal OIDC/SAML standards. Using them in production requires an authentication contract, normalization, and transport protection from gateway to backend.

## 8. Stale session persists: distinguishing where state lives

### 8.1. SecurityContextHolder is per-request/thread

`SecurityContextHolder` holds the Authentication used for the current request (normally in a ThreadLocal or equivalent strategy). `SecurityContextHolder.clearContext()` clears only the **current context**, not automatically copies stored in:

- `HttpSession`/Spring Session store;
- Redis/JDBC session persistence;
- Spring Security `SessionRegistry` if managing concurrent sessions;
- Application-specific user profile/tenant caches;
- `SavedRequest`, CSRF tokens, shopping carts, or PII-bearing view models;
- Browser cookies across tabs;
- The identity gateway's own token session.

### 8.2. SecurityContextRepository can restore old auth

In a stateful Servlet app:

~~~text
Request: Cookie JSESSIONID=S1
    |
    v
SecurityContextHolderFilter
    |
    v
SecurityContextRepository.loadContext(...)
    |
    v
HttpSession/Spring Session -> Authentication=alice (from before)
    |
    v
Filters + Authorization
~~~

If you want every request to carry a fresh proxy header, **never rely solely on the restored Authentication**. Add a guard before context restoration or per-request enforcement after context load, aligned cleanly with filter ordering.

### 8.3. Spring Security 6/7 and explicit save

Since Spring Security 6, Servlet uses `SecurityContextHolderFilter` and **explicit-save semantics** for custom authentication; `SecurityContextPersistenceFilter`/`SessionManagementFilter` are no longer defaults as in Spring Security 5. Spring docs explain that custom filters/controllers creating an Authentication must persist it via `SecurityContextRepository.saveContext` when persistence is wanted.

`AbstractPreAuthenticatedProcessingFilter` provides `setSecurityContextRepository(...)` and saves context after successful authentication. For stateful pre-auth:

~~~java
HttpSessionSecurityContextRepository repository =
    new HttpSessionSecurityContextRepository();
filter.setSecurityContextRepository(repository);
~~~

Use the **same policy/repository** on `SecurityFilterChain`; if a controller/handler clears context manually, ensure the **repository does not retain the old copy**. Never rely on calling `SecurityContextHolder.clearContext()` in one code path while the next request reloads `Authentication=alice` from `HttpSession`.

### 8.4. Session fixation vs. user-switch

- **Session fixation:** attacker knows/presets a session ID before the victim logs in. Rotate `JSESSIONID` or create a new session on login per framework strategy.
- **User-switch stale state:** session S1 belongs to Alice, then the gateway switches to Bob. Even though the Session ID rotated when Alice logged in, it is still the **wrong user's session** on Bob's request. Handle principal changes separately.
- **Session expiry:** sessions expire after a TTL, yet that **is not enough** to prevent wrong-user access during the remaining TTL window.
- **Gateway logout:** upstream session expiry does not make the local Spring session vanish automatically without propagation or a guard.

These controls complement rather than replace one another.

## 9. Spring Security configuration example: RequestHeaderAuthenticationFilter

Example for **Spring Boot 3.x/Spring Security 6.x** or modern Servlet branches with matching APIs. This is **integration illustration code**, not standalone runnable with plain JDK without Spring dependencies and a configured gateway.

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration
public class ProxyPreAuthSecurityConfig {
    @Bean
    SecurityFilterChain proxyFilterChain(
            HttpSecurity http,
            UserDetailsService userDetailsService) throws Exception {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            details = new UserDetailsByNameServiceWrapper<>();
        details.setUserDetailsService(userDetailsService);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(details);

        RequestHeaderAuthenticationFilter filter =
            new RequestHeaderAuthenticationFilter();
        filter.setPrincipalRequestHeader("X-Authenticated-Subject");
        filter.setExceptionIfHeaderMissing(true);
        filter.setCheckForPrincipalChanges(true);
        filter.setInvalidateSessionOnPrincipalChange(true);
        filter.setContinueFilterChainOnUnsuccessfulAuthentication(false);

        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();
        filter.setSecurityContextRepository(repository);
        filter.setAuthenticationManager(new ProviderManager(provider));

        http
            .securityMatcher("/app/**", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .securityContext(ctx -> ctx
                .securityContextRepository(repository))
            .authenticationProvider(provider)
            .addFilterBefore(
                new TrustedProxyHeaderGuard(),
                SecurityContextHolderFilter.class)
            .addFilterBefore(
                filter,
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**To use this code**, define `TrustedProxyHeaderGuard` from the next section and supply a real `UserDetailsService`. `securityMatcher` scopes the example to `/app/**` and `/api/**`; other URLs must have **dedicated SecurityFilterChains/route policies**, leaving no sensitive paths outside the chain. You may use one app-wide chain with explicit health/static exclusions if your architecture suits it.

Key choices:

- `setExceptionIfHeaderMissing(true)`: **takes effect only when the filter actually calls `getPreAuthenticatedPrincipal`**; the upstream guard handles cases where the filter would skip due to an existing context.
- `setCheckForPrincipalChanges(true)`: compares header user against the current Authentication when a saved context exists.
- `setInvalidateSessionOnPrincipalChange(true)`: triggers session invalidation on principal change, avoiding retaining the prior user's attributes.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)`: prevents falling through to another auth mechanism when the pre-auth manager fails. **Does not by itself handle `principal=null` or stale contexts**.
- `setSecurityContextRepository(repository)`: saves pre-auth state on success consistently with the chain. If choosing **stateless**, do not use an HttpSession repository.
- `new ProviderManager(provider)`: the provider only loads user/roles after gateway authentication. **Never treat the provider as a header signature verifier**.
- `addFilterBefore(guard, SecurityContextHolderFilter.class)`: runs the guard **before restoring SecurityContext from HttpSession**, so missing headers cannot ride on cookie S1.
- `addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)`: runs pre-auth after context restoration and before authorization in default configs; **verify ordering with integration tests**, especially with multiple chains or custom filters.
- Never enable form login/basic auth on this trusted-proxy-only chain without a dedicated assurance/fallback design.

**Version note:** Spring Security 6/7 may alter APIs/ordering; never assume this snippet replaces integration tests against your actual project and Servlet container. Default `UserDetailsService` setups may **not proactively reject disabled/locked accounts** in every pre-auth setup; ensure **account state is checked and rejected** per policy rather than merely loading an existing record.

## 10. Missing-header guard running before session load

A clean pattern is a `OncePerRequestFilter` running **before `SecurityContextHolderFilter`** on infrastructure-protected pre-auth paths.

File `TrustedProxyHeaderGuard.java` (Spring Boot Servlet, not standalone JDK):

~~~java
package com.example.portal.security;

import java.io.IOException;
import java.util.Collections;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.web.filter.OncePerRequestFilter;

public final class TrustedProxyHeaderGuard extends OncePerRequestFilter {
    private static final String SUBJECT = "X-Authenticated-Subject";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        List<String> headers = Collections.list(
            request.getHeaders(SUBJECT));

        boolean invalid = headers.size() != 1;
        if (!invalid) {
            String subject = headers.get(0);
            invalid = subject == null
                || !subject.matches("[A-Za-z0-9._@:-]{1,160}")
                || subject.indexOf(',') >= 0;
        }

        if (invalid) {
            // Guards BEFORE SecurityContextHolderFilter restores session.
            HttpSession previous = request.getSession(false);
            if (previous != null) {
                previous.invalidate();
            }
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED,
                "Trusted identity is required");
            return;
        }
        chain.doFilter(request, response);
    }
}
~~~

### 10.1. What this guard guarantees

- **Missing header**, blank header, multiple values, or characters violating the contract → **401**.
- **Old session cookie present** without the header → server invalidates `HttpSession` before the old SecurityContext loads.
- Invalid requests never reach protected endpoints.
- Needs no knowledge of the prior username to clear the session; works even when unauthenticated.

### 10.2. What this guard does NOT guarantee

**Very important:** this example guard only checks **header syntax**; it **does not verify that the proxy is actually trusted**. Production **must** enforce mTLS/network routing and gateway strip-and-inject; even better is a gateway-authenticated principal/assertion trusted over a verified network context.

Additionally:

- If a reverse proxy folds duplicates into a single string, the comma check is only defense-in-depth for the example contract; ingress must still reject ambiguous syntax.
- The example regex permits ASCII subjects from a limited character set; opaque OIDC `sub` values may need different Unicode/encoding rules—align gateway and backend, and **never blindly trim/canonicalize identities** lest two distinct principals collide.
- The regex does not check issuer/tenant/upstream session; where needed, enforce a separate **binding guard** on `(issuer, tenant, subject, upstreamSid)`.
- `HttpSession.invalidate()` does not replace logout notifications to the gateway/IdP or token revocation elsewhere.
- This code does not delete browser cookies automatically; add `Clear-Site-Data`/`Set-Cookie` per design for domains/paths owned by the app.
- `OncePerRequestFilter` runs once per dispatch, which does not automatically cover every URL: any URL outside `SecurityFilterChain` or bypassed by the filter must be protected separately.
- When session invalidation runs after context loading, clear/update `SecurityContextRepository` properly; this example deliberately sits **before `SecurityContextHolderFilter`**.

**Never copy this guard as the sole defense on public web apps**. It only checks header presence/format, without authenticating the user.

## 11. Checking principal changes and invalidating sessions

When the header switches from Alice to Bob, `RequestHeaderAuthenticationFilter` can compare users automatically:

~~~java
filter.setCheckForPrincipalChanges(true);
filter.setInvalidateSessionOnPrincipalChange(true);
~~~

Per `AbstractPreAuthenticatedProcessingFilter` Javadoc, by default:

- `checkForPrincipalChanges` is **disabled**: if a current Authentication exists, the pre-auth filter may skip.
- When enabled, `principalChanged` normally compares the **header String** to `Authentication.getName()`.
- `invalidateSessionOnPrincipalChange` defaults to **true**, taking effect only when principal-change checking runs and detects a change.
- The filter attempts re-authentication and saves the result via `SecurityContextRepository`; verify session strategy, business session state, and actual runtime behavior.

### 11.1. Why is username alone insufficient?

Suppose:

~~~text
Session S1:
  header user = alice
  tenant = A
  upstreamSession = sid-7
  authorities = [ROLE_FINANCE_READER]

New request:
  header user = alice
  tenant = B
  upstreamSession = sid-19
~~~

`Authentication.getName() == "alice"`, so **the name did not change**. Yet tenant, upstream session, and permissions may have changed completely. When policy needs to protect this boundary, build a **`SessionIdentityBinding`** such as:

~~~text
issuer
tenant
stableSubject
upstreamSessionId or sessionEpoch (if upstream supports)
authorizationRevision (if app supports role revocation)
localSessionIssuedAt
~~~

Every binding field must come from a **verified gateway context** or server-side state, never from a free-form query or username. Before serving a request, compare the **full binding** against current identity; on mismatch → deny + invalidate session, never reusing cached UserDetails/roles.

### 11.2. Role of downstream session registries and policy versions

With Spring Session/Redis/JDBC:

- `HttpSession.invalidate()` on one node must prevent other nodes from accepting the session via a shared session store.
- With `SessionRegistry`, verify cleanup/events for invalidated sessions so stale registry references never leak user state.
- When a user is disabled or loses a role, a pre-auth filter checking only the principal String may **fail to reload authorities**. Design one of: authorization revisions, per-request authorization checks, short session expiry, cache invalidation, or explicit session revocation events.
- When tenant or principal changes, purge session attributes holding prior profile/tenant data, request caches, and session-bound business caches.
- With distributed sessions, test logout/race conditions across two replicas/concurrent requests.

**Changing a user's roles in the database does not automatically update an Authentication cached in HttpSession.** Stale-authority checks are a distinct requirement from principal switching.

## 12. Should you use stateless per-request pre-auth?

One option that reduces **stale HttpSession** risk is persisting no Authentication across requests:

~~~text
Each request:
  trusted gateway ensures valid upstream session
  -> fresh identity headers
  -> backend validate trust/identity binding
  -> load/check local authorization
  -> execute
  -> do not persist Authentication to HttpSession
~~~

Spring Security Servlet can configure:

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .securityContext(ctx -> ctx
        .securityContextRepository(new NullSecurityContextRepository()))
    .requestCache(cache -> cache
        .requestCache(new NullRequestCache()));
~~~

This is a **configuration fragment**, requiring imports:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
~~~

When using stateless mode, **never simultaneously configure `HttpSessionSecurityContextRepository` on the pre-auth filter**. Every authentication mechanism in the chain must follow a consistent policy. Stateless mode carries tradeoffs:

- UserDetails/roles lookup on every request unless backed by a freshness-checked cache.
- Gateway must emit trusted identity on **every** protected request.
- Endpoints requiring browser CSRF/session state may need a separate chain/architecture.
- Does not guarantee the upstream gateway token/SSO is still valid if the gateway itself caches badly.
- Does not stop header spoofing on its own if the backend remains directly reachable.

**Stateful is not inherently wrong.** Many apps need sessions and pair invalidate-on-change with per-request guards; what matters is specifying **exactly when local Authentication stops being trustworthy**.

## 13. Four access states that must be distinguished

| Gateway header | App cookie | Local state handling required |
| --- | --- | --- |
| Valid Alice | None | Pre-auth + local user policy → create session if stateful |
| Valid Alice | Alice session with matching binding | Allow if binding/account/roles remain valid |
| Missing | Alice session present | **401 and invalidation**, never use Alice |
| Valid Bob | Alice session | **401/new login or reauthenticate+rotate**, never inherit state |
| Valid Alice | Bob session | **DENY**, invalidate Bob session |
| Alice, tenant B | Alice session, tenant A | **DENY** despite identical username string |
| Alice, new upstream session | Alice session, old upstream session | Under session-binding policy: **DENY old session** |
| Valid Alice | Expired/unknown session | Do not restore S1; authenticate/issue new session per policy |
| Valid Alice | Alice session with revoked roles | **DENY/reload roles**, never continue with old authorities |
| Client-forged header | Any | **DENY** at gateway/network, never trust header |
| Duplicate/malformed header | Alice session | **DENY**, never pick an arbitrary value |
| Header Alice yet gateway logged user out | Alice session | Gateway must stop emitting header; if mis-emitted, app needs revocation/freshness controls |
| Gateway session expired | No local session | 401/SSO login; never create an authorized anonymous user |
| Service-to-service job bypassing gateway | None | **Never** share the trusted-proxy chain; use a dedicated verified service-auth route |

To prevent old sessions from resurfacing unpredictably, **on mismatch** pick one of two policies:

- **Deny then new session:** return appropriate 401/403; browser re-navigates login, next request carries valid identity without cookie S1, and creates session S2.
- **Atomic replace:** within the same request, invalidate S1, verify full identity and local policy for Bob, create S2, rotate the session ID, and confirm zero Alice state remains; verify via integration tests. More error-prone when apps hold many caches/session attributes.

## 14. Standalone Java 17 demo: simulating identity binding and session invalidation

The snippet below **runs on JDK 17+** with no Spring, proxy, KDC, OIDC, or Redis. It simulates a **deny-on-identity-mismatch** policy enforcing these invariants:

- Browser arrives with a **trusted gateway assertion** → app creates a local session.
- Subsequent requests reuse the session only when **issuer/tenant/subject/upstreamSession** still match.
- Missing/duplicate headers **cannot be rescued by an old cookie**.
- New user header with old cookie: invalidate session and require a **new session**.
- Same username with different tenant or upstream session: deny.
- Unverified gateway (untrusted direct caller): deny.
- Disabled/unknown local user or changed role revision: deny.
- Revoked/expired upstream session: deny; local session age past policy: deny.
- Authorities always come from **server-side local policy**, never headers.

**Mandatory limitations:** `edgeVerified`, `upstreamActive`, and `Identity` values in the demo are **simulated inputs from a protected gateway/verifier**, **never taken directly from HTTP JSON/headers/queries or client-supplied booleans**. The demo **does not verify mTLS, JWT signatures, OIDC sessions, SAML assertions, or network identity**. `HashMap` is not a distributed session store, and `local-1` is not a production-grade random session ID. Its sole goal is testing **continuity logic**, not building real authentication middleware.

File **ProxyIdentityContinuityDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ProxyIdentityContinuityDemo {
    static final String ISSUER = "trusted-gateway";
    static final Instant START = Instant.parse("2026-01-01T10:00:00Z");

    record Identity(String issuer, String tenant, String subject,
                    String upstreamSession) {}
    record Request(boolean edgeVerified, List<Identity> headers,
                   String cookie, boolean upstreamActive, Instant now) {}
    record Account(boolean enabled, int permissionsRevision,
                   Set<String> roles) {}
    record LocalSession(String id, Identity identity,
                        int permissionsRevision, Instant createdAt) {}
    record Result(int status, String reason, String sessionId,
                  Set<String> roles) {
        boolean ok() { return status == 200; }
    }

    static final class Service {
        private final Map<String, LocalSession> sessions = new HashMap<>();
        private final Map<String, Account> accounts = new HashMap<>();
        private int nextId = 1;

        Service() {
            accounts.put("tenant-a/alice",
                new Account(true, 1, Set.of("ROLE_READER")));
            accounts.put("tenant-a/bob",
                new Account(true, 1, Set.of("ROLE_EDITOR")));
            accounts.put("tenant-a/disabled",
                new Account(false, 1, Set.of("ROLE_READER")));
            accounts.put("tenant-b/alice",
                new Account(true, 1, Set.of("ROLE_TENANT_B")));
        }

        void changeRoles(String key) {
            Account current = accounts.get(key);
            accounts.put(key, new Account(current.enabled(),
                current.permissionsRevision() + 1, Set.of("ROLE_BASIC")));
        }

        boolean contains(String sessionId) {
            return sessions.containsKey(sessionId);
        }

        private Result deny(int status, String reason, String cookie) {
            if (cookie != null) sessions.remove(cookie);
            return new Result(status, reason, null, Set.of());
        }

        Result handle(Request request) {
            if (!request.edgeVerified()) {
                // In production the edge blocks untrusted traffic before app.
                return new Result(403, "untrusted-edge", null, Set.of());
            }
            if (request.headers() == null || request.headers().size() != 1) {
                return deny(401, "header-missing-or-duplicate", request.cookie());
            }
            Identity id = request.headers().get(0);
            if (id == null || !ISSUER.equals(id.issuer())
                    || id.tenant() == null || id.subject() == null
                    || id.upstreamSession() == null
                    || id.tenant().isBlank() || id.subject().isBlank()
                    || id.upstreamSession().isBlank()) {
                return deny(403, "untrusted-or-invalid-identity",
                    request.cookie());
            }
            if (!request.upstreamActive()) {
                return deny(401, "upstream-session-expired", request.cookie());
            }
            Account account = accounts.get(id.tenant() + "/" + id.subject());
            if (account == null || !account.enabled()) {
                return deny(403, "account-not-authorized", request.cookie());
            }
            if (request.cookie() == null) {
                String sid = "local-" + nextId++;
                sessions.put(sid, new LocalSession(
                    sid, id, account.permissionsRevision(), request.now()));
                return new Result(200, "new-session", sid, account.roles());
            }
            LocalSession previous = sessions.get(request.cookie());
            if (previous == null) {
                return deny(401, "stale-cookie", request.cookie());
            }
            if (!previous.identity().equals(id)) {
                return deny(401, "identity-or-upstream-session-switched",
                    request.cookie());
            }
            if (!request.now().isBefore(
                    previous.createdAt().plus(Duration.ofMinutes(30)))) {
                return deny(401, "session-too-old", request.cookie());
            }
            if (previous.permissionsRevision() !=
                    account.permissionsRevision()) {
                return deny(401, "roles-changed", request.cookie());
            }
            return new Result(200, "same-identity",
                previous.id(), account.roles());
        }
    }

    static Identity id(String tenant, String user, String upstreamSession) {
        return new Identity(ISSUER, tenant, user, upstreamSession);
    }

    static Request req(Identity identity, String cookie) {
        return new Request(true, List.of(identity), cookie, true, START);
    }

    public static void main(String[] args) {
        Service app = new Service();
        Identity alice = id("tenant-a", "alice", "upstream-1");
        Identity bob = id("tenant-a", "bob", "upstream-2");
        Result first = app.handle(req(alice, null));
        String sid1 = first.sessionId();

        System.out.println("firstHeaderCreatesSession=" + first.ok());
        System.out.println("sameUserReusesSession=" +
            app.handle(req(alice, sid1)).ok());
        System.out.println("rolesFromLocalPolicy=" +
            first.roles().equals(Set.of("ROLE_READER")));

        Result missing = app.handle(
            new Request(true, List.of(), sid1, true, START));
        System.out.println("missingHeaderDenied=" + (missing.status() == 401));
        System.out.println("missingHeaderRevokesOldSession=" +
            !app.contains(sid1));
        System.out.println("staleCookieDenied=" +
            !app.handle(req(alice, sid1)).ok());

        Result recovered = app.handle(req(alice, null));
        String sid2 = recovered.sessionId();
        System.out.println("newSessionAfterFreshAuth=" +
            (recovered.ok() && !sid2.equals(sid1)));

        Result switched = app.handle(req(bob, sid2));
        System.out.println("switchDenied=" + (switched.status() == 401));
        System.out.println("switchRevokesOldSession=" +
            !app.contains(sid2));
        System.out.println("newUserNeedsNewSession=" +
            app.handle(req(bob, null)).ok());

        Result forUpstream = app.handle(req(alice, null));
        System.out.println("upstreamSessionChangeDenied=" +
            !app.handle(req(
                id("tenant-a", "alice", "upstream-new"),
                forUpstream.sessionId())).ok());

        Result forTenant = app.handle(req(alice, null));
        System.out.println("tenantSwitchDenied=" +
            !app.handle(req(
                id("tenant-b", "alice", "upstream-1"),
                forTenant.sessionId())).ok());

        System.out.println("duplicateHeaderDenied=" +
            !app.handle(new Request(true, List.of(alice, bob),
                null, true, START)).ok());
        System.out.println("untrustedEdgeDenied=" +
            !app.handle(new Request(false, List.of(alice),
                null, true, START)).ok());
        System.out.println("disabledAccountDenied=" +
            !app.handle(req(id("tenant-a", "disabled", "u-3"),
                null)).ok());

        Result beforeRolesChange = app.handle(req(alice, null));
        app.changeRoles("tenant-a/alice");
        System.out.println("rolesChangeRevokesSession=" +
            !app.handle(req(alice, beforeRolesChange.sessionId())).ok());

        Result beforeUpstreamLogout = app.handle(req(alice, null));
        System.out.println("upstreamLogoutRevokesSession=" +
            !app.handle(new Request(true, List.of(alice),
                beforeUpstreamLogout.sessionId(), false, START)).ok());

        Result beforeTimeout = app.handle(req(alice, null));
        System.out.println("localSessionLifetimeEnforced=" +
            !app.handle(new Request(true, List.of(alice),
                beforeTimeout.sessionId(), true,
                START.plus(Duration.ofMinutes(31)))).ok());
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 ProxyIdentityContinuityDemo.java
java ProxyIdentityContinuityDemo
~~~

**Verified exact stdout**:

~~~text
firstHeaderCreatesSession=true
sameUserReusesSession=true
rolesFromLocalPolicy=true
missingHeaderDenied=true
missingHeaderRevokesOldSession=true
staleCookieDenied=true
newSessionAfterFreshAuth=true
switchDenied=true
switchRevokesOldSession=true
newUserNeedsNewSession=true
upstreamSessionChangeDenied=true
tenantSwitchDenied=true
duplicateHeaderDenied=true
untrustedEdgeDenied=true
disabledAccountDenied=true
rolesChangeRevokesSession=true
upstreamLogoutRevokesSession=true
localSessionLifetimeEnforced=true
~~~

**Meaning:** all `...Denied=true`/`...Revokes...=true` lines show **the policy rejected and purged old state as expected**, not 401/403 responses from a production Spring app. The demo also illustrates that switching users requires a **new session** rather than reusing Alice's cookie for Bob.

## 15. Integration and security test matrix

| Test case | Scenario | Expected |
| --- | --- | --- |
| Valid header, no cookie | Gateway verified Alice | App authenticates Alice and issues session S1 |
| Valid header, valid cookie | Alice + S1 | Allowed if binding/account/roles remain valid |
| Missing header, cookie S1 | Gateway logout or proxy dropped header | **401, invalidate S1**, serve zero Alice data |
| Empty header, cookie S1 | `X-Authenticated-Subject:` | 401, invalidate |
| Whitespace header | Header contains spaces only | 401, invalidate |
| Duplicate headers | Alice and Bob under same header name | 401, never pick first value |
| Comma-joined header | `alice,bob` | Reject per header format contract |
| Control chars in header | Newline/CR or illegal characters | Reject at proxy/backend |
| Direct-backend header | Caller bypasses gateway, sets Alice | **403/network reject** |
| Proxy skips stripping header | Client sends admin, gateway forwards untouched | Security test FAILS; fix gateway |
| Alice → Bob, cookie S1 | Upstream user switch | Invalidate S1; serve zero Alice data |
| Bob → Alice, cookie S1 | Switch account back | Re-authenticate/new session, never reuse |
| Same username, tenant changed | Tenant A/Alice → B/Alice | Reject old binding |
| Same email, issuer changed | IdP A → IdP B | Reject if principal binding changed |
| Same subject, new upstream session | sid-7 → sid-8 | Reject/rotate per policy |
| Gateway session revoked | Header disappears after logout | Local session never reused |
| Gateway emits stale header | SSO logged out yet gateway cache still emits | Gateway security test FAILS; app needs freshness/revocation |
| Browser holds stale JSESSIONID | Session ID absent from store | Never restores old Authentication |
| Session S1 past TTL | Local session expired | Reject/re-auth per policy |
| User disabled in local DB | Valid header yet local account locked | 403, invalidation per policy |
| Local role revoked | Old session auth has elevated privileges | Reload/deny or invalidate per role revision |
| SavedRequest holds Alice data | Alice→Bob | Never replay cached requests/profile data to new user |
| Two tabs sharing cookie | Tab A Alice, Tab B switches to Bob | Never mix session data/authorities |
| Concurrent requests on 2 nodes | Shared Redis/JDBC sessions | Invalidation visible across nodes; races handled |
| Proxy header absent on static | Public static path | Allowed only via explicit public chain; never weakens protected routes |
| Filter on wrong chain | `/api/private` bypasses guard | Integration test FAILS |
| `setExceptionIfHeaderMissing(false)` | Missing header, stale auth persists | Test catches fail-open |
| `checkForPrincipalChanges=false` | Header Bob, context Alice | Test catches stale principal |
| `setContinueFilterChainOnUnsuccessfulAuthentication=true` | Provider fails then form fallback | Catch downgrade if no explicit policy |
| Pre-auth provider returns user without status check | Disabled user exists | Authorization test fails; add local policy |
| Logout clears context only | Session repository keeps old auth | Next request must not restore it |
| Cookie deleted in browser while store persists | Client kept/stole cookie | Server-side session invalidation mandatory |
| Session fixation | Session ID identical before and after login outside policy | Rotate session per security strategy |
| API bearer auth on another route | No proxy header | Route enforces its own chain/credential policy |
| Reverse proxy trust shift | Different gateway or header name changed | Deny until contract is updated |
| Gateway loses connection to IdP | Gateway cannot validate session | Fail closed; never emit old identity |
| Full headers logged | Raw subject/SSO/assertions printed | Redact; audit privacy |
| Session ID in URL | `;jsessionid` or query accepted outside policy | Disable URL session tracking; test |
| Cross-tenant same subject | `alice` across multiple partners | User bindings never merged |
| Retry 401 after missing header | Browser logs back in at gateway | New session created only after valid upstream proof |

**Do not unit-test `RequestHeaderAuthenticationFilter` alone.** Run E2E tests spanning **browser → gateway → backend**, with real header sanitization, session cookies, filter chains, Redis/Spring Session, and response codes.

### 15.1. Testing the most dangerous bug properly

~~~text
Arrange:
  GET /api/reports with gateway header Alice -> 200
  Capture JSESSIONID=S1

Act:
  GET /api/reports
  Cookie JSESSIONID=S1
  NO X-Authenticated-Subject

Assert:
  status = 401 (or policy deny)
  NO business data in response
  Session S1 invalidated in server/session store
  Retry with S1 is rejected
~~~

If the test returns 200 for Alice merely because `HttpSession` survived, proxy pre-auth **fails contract continuity**.

### 15.2. Testing identity switching across two tabs

~~~text
Tab 1:
  gateway Alice -> app session S1

Tab 2:
  gateway Bob yet browser still sends S1

Expected:
  no request from Bob ever sees Alice data
  S1 invalidated or safely re-authenticated/rotated
  new session S2 holds only Bob roles/tenant data
  old session S1 no longer valid on other replicas
~~~

### 15.3. Testing header spoofing

~~~text
Request bypassing gateway:
  X-Authenticated-Subject: admin

Expected:
  network deny/mTLS fail/edge policy deny
  backend does not rely on raw header string to grant ROLE_ADMIN
~~~

**Do not test only requests traversing the trusted gateway**, because network bypass channels are a primary threat model.

## 16. Troubleshooting and safe logging

| Symptom | Common cause | How to investigate |
| --- | --- | --- |
| Missing header yet request still authenticated | Old SecurityContext loaded; pre-auth filter skips when already authenticated | Check `checkForPrincipalChanges` and guard ordering |
| Header is Bob yet controller sees Alice | Filter does not check principal changes by default | Enable check + invalidate and test |
| Header Alice tenant B keeps tenant A permissions | Comparing name without tenant binding | Full identity-binding guard |
| Upstream logged out yet app session survives | Missing header-presence check/logout event/session invalidation | Gateway session policy + app guard |
| Missing header returns HTTP 500 | Unhandled filter exception | Request-boundary guard sends 401; check filter order |
| `exceptionIfHeaderMissing=false` enabled to fix 500 | Turns into null principal and chain keeps running | Do not use as a fail-closed fix |
| `continueFilterChainOnUnsuccessfulAuthentication=false` yet fails open | No principal returned or filter skipped due to existing context | Guard before context load |
| Some URLs skip guard | Multiple SecurityFilterChains, uncovered matchers | Review URL coverage and MockMvc integration |
| Duplicate headers give random results | `getHeader` picks first/coalesced value | Strip/reject duplicates at gateway/backend |
| User switch creates new session yet retains Alice's cart | `migrateSession`/copied old session attributes | Invalidate + clean new session; purge business caches |
| User role revoked yet context holds old role | `UserDetails` cached in session | Role revision/periodic recheck/invalidation |
| Distributed session revoked on one node only | Redis/JDBC sync lag or local cache | Shared session store, events, TTL/invalidation |
| Re-authentication loop | 401 causes gateway redirect while app retains stale cookie/route | Clear session cookie; align forwarding/login routes |
| User gets 403 after gateway success | Local account disabled/tenant policy | `PreAuthenticatedAuthenticationProvider` + user policy |
| URL host/proxy headers differ across environments | Differing header contracts/ingress normalization | Edge config and proxy-hop sanitization |
| Direct HTTP header impersonation | Backend publicly exposed, broken network trust | Block external traffic, enforce mTLS, gateway strip |
| Bearer-token API route blocked for missing proxy header | Overlapping filter/chain matchers | Separate chains and auth schemes per route |
| Logout returns 200 then next request is authenticated again | Gateway SSO still active and emits fresh header | Distinguish app logout from gateway logout |
| `JSESSIONID` expired while header Alice remains | Gateway still authenticates Alice | Issue new local session if policy permits |
| Bad header format after upgrade | Issuer/subject encoding/duplicate behavior changed | Contract tests; reject fail-closed |

### 16.1. Suggested logs

~~~text
event=PROXY_IDENTITY_GUARD_REJECT
reason=HEADER_MISSING
route=/api/reports
gatewayId=corp-edge
localSessionPresent=true
traceId=trace-8b2c
status=401
~~~

~~~text
event=PROXY_IDENTITY_SESSION_MISMATCH
reason=PRINCIPAL_SWITCH
previousBindingHash=sha256:...
currentBindingHash=sha256:...
policyVersion=proxy-auth-v5
traceId=trace-b9f4
status=401
~~~

The hashes above are **log format placeholders**, not verifiable hashes. Avoid logging raw identity headers, cookies, bearer tokens, mTLS private key data, serialized Spring Authentication objects, session DB contents, or PII.

### 16.2. Layered runbook

1. **Gateway:** did the request actually traverse the authenticated/mTLS gateway? Did it strip and inject headers?
2. **Header:** do name/value match contract? Are there missing/blank/duplicate headers or inconsistent forwarding?
3. **Spring filter chain:** did the URL hit the right chain? Did the guard run **before `SecurityContextHolderFilter`**? Does pre-auth check principal changes?
4. **SecurityContext:** was Authentication loaded from an old session or freshly created by the provider? Do user/tenant/issuer/upstream bindings match?
5. **Local policy:** are account enabled, role revision, tenant access, and resource ACLs still valid?
6. **Session:** was `HttpSession`/Spring Session invalidated across all replicas? Can old cookies still be used?
7. **Upstream lifecycle:** if the gateway keeps emitting headers after logout, is the proxy session/cache/revocation broken? The backend cannot fix that merely by deleting a cookie.
8. **Response:** do 401/403/302 statuses match the API/browser contract? Are there login loops or unauthorized data leaks?
9. **Observability:** correlation IDs, event reason, hashed issuer/tenant (no raw PII), `gatewayId`, route, `policyVersion`.
10. **Remediation:** never enable missing-header fallbacks or drop session checks just to silence 401s; fix the root cause with negative tests.

## 17. Threat-model-driven design choices

### 17.1. Is invalidating the local session on every missing header too strict?

If the contract is **"every protected request must pass through an authenticated gateway"**, it is a sound, auditable policy. Public requests, health checks, or static assets needing no identity belong on a **separate URL allowlist/chain**, never letting protected APIs read sessions without headers.

### 17.2. Can Bob's new request create a session immediately after switching?

Yes, provided you implement **atomic re-authentication + session rotation** and the app retains zero Alice session data. Still, the deny-on-change model in the demo is **simpler to prove safe**. On shared devices/multiple tabs, prompting users to confirm account switching is also helpful.

### 17.3. Must you invalidate when email changes while `sub` stays unchanged?

Not necessarily if the stable **issuer+tenant+sub** binding remains intact and local roles/policies align. **Email/display name** should not govern session identity in SSO federation. However, if the app uses email as a business key, design migration/cache invalidation to avoid account mix-ups.

### 17.4. Is it risky if the session changes while the user stays the same?

It can be. In security-sensitive products, a new upstream session ID signals a **distinct upstream login**. Reusing the old local session can carry over prior saved requests/roles/state or bypass re-authentication freshness. Rotating may be necessary, though you can only enforce it if the gateway supplies a **trusted, durable session binding**.

### 17.5. When a user is disabled, can the header still be valid?

Yes. External authentication can stay valid for a window after local policy revoked access. `PreAuthenticatedAuthenticationProvider` does not continuously re-check local status if Authentication is reused from session. Use per-request authorization/revisions/TTLs or revocation events. **Never equate "gateway authenticated" with "business account enabled".**

### 17.6. Should proxy-only setups enable form login in the same SecurityFilterChain?

Spring Security's `RequestHeaderAuthenticationFilter` docs warn against mixing casually with other auth mechanisms, as it can create a bypass around the external system. If recovery login is strictly mandated, use separate routes, threat models, provider ordering, assurance, auditing, and credential-downgrade policies; never swallow `AuthenticationException` and fall through to a weaker mechanism.

### 17.7. How do local browser logout and gateway logout differ?

Local app logout only invalidates `HttpSession`. If the gateway SSO session remains active, the next request is authenticated by the gateway and emits Alice's header → the app quickly logs right back in. That is a **fresh session after proxy authentication**, not necessarily an un-deleted `HttpSession`. Ending upstream SSO requires protocol-level logout at the gateway/IdP, not Spring local logout alone.

### 17.8. Defending when the gateway emits multi-identity headers

Some proxies send groups/roles or identities from multiple tenants. Never accept uncontracted/untrusted `roles` fields or resolve multiple identities by picking the first item. Prefer identity assertions with issuer, audience, subject, tenant, session, and permissions either signed or sent over a trusted channel; map roles via a local allowlist and reject ambiguous inputs.

## 18. Production deployment checklist

- [ ] Documented browser → identity gateway → Spring app trust diagram with zero direct backend bypasses.
- [ ] Gateway strips all client-supplied identity headers and injects **one** exact identity header.
- [ ] Backend accepts only the gateway via network policies/mTLS/service identity; never trusts `X-Forwarded-For` as proof.
- [ ] Header contract specifies name, format, charset, length, duplicate handling, and issuer/tenant/subject/session semantics.
- [ ] Missing headers **never** reuse old session S1; protected requests return 401 and invalidate the session.
- [ ] Blank, whitespace, comma-joined, duplicate, or invalidly encoded headers are rejected.
- [ ] `RequestHeaderAuthenticationFilter` sets the right `principalRequestHeader`; never mistakenly defaults to `SM_USER`.
- [ ] `setExceptionIfHeaderMissing(true)` is set, understanding it applies only when the filter is invoked.
- [ ] `setCheckForPrincipalChanges(true)` is enabled so user switches are not ignored inside an existing `SecurityContext`.
- [ ] `setInvalidateSessionOnPrincipalChange(true)` is enabled with business session-state cleanup tested.
- [ ] `setContinueFilterChainOnUnsuccessfulAuthentication(false)` is set in proxy-only mode to avoid unapproved fallbacks.
- [ ] Guard/binding policy handles missing headers **before or regardless of an existing SecurityContext**.
- [ ] Guard applies only to the right `SecurityFilterChain`; static/health/other auth routes have explicit separate policies.
- [ ] Invalidation executes in the **server/session store**, not merely clearing client cookies.
- [ ] When clearing `SecurityContext` manually, `SecurityContextRepository` is also updated/cleared properly.
- [ ] Session binding uses stable issuer+tenant+subject, never email as default key.
- [ ] If the gateway supplies a trusted upstream session ID, session changes are detected per policy.
- [ ] If a user is disabled or roles are revoked, old Authentication never retains access indefinitely; revision/recheck policies exist.
- [ ] `UserDetailsService`/`AuthenticationUserDetailsService` enforces account status and local roles; never grants `ROLE_ADMIN` from headers.
- [ ] On principal change, prior user's `SavedRequest`, cart, profile cache, and tenant context are purged.
- [ ] `SessionFixationProtection` is not treated as a substitute for user-switch handling.
- [ ] In stateful mode, `HttpSessionSecurityContextRepository`/Spring Session and filter save/load align consistently.
- [ ] In stateless mode, `SessionCreationPolicy.STATELESS`/`NullSecurityContextRepository` requires identity headers on every request.
- [ ] Multiple replicas observe revoked sessions consistently; race conditions/parallel requests are tested.
- [ ] Separate bearer-auth APIs use dedicated chains/routes without mistaking missing proxy headers for permitted anonymous access.
- [ ] HTTPS, CSRF/cookies/session timeouts remain enforced even though authentication runs at the gateway.
- [ ] App logout is distinct from gateway/IdP logout; UX never claims SSO ended if only the local session cleared.
- [ ] Tested missing/blank/duplicate/spoofed headers, Alice→Bob, tenant/issuer switches, upstream logout, and revoked roles.
- [ ] Tested identity switching with old cookies across two browser tabs and a Spring Session/Redis cluster.
- [ ] Logs capture reason, correlation ID, and `policyVersion` without logging raw tokens/cookies/PII.
- [ ] Runbooks exist for 401 loops, missing proxy headers, stale sessions, provider fallbacks, and broken deployments.

## 19. Self-check questions

**1. The header disappeared yet `JSESSIONID` remains—may the app use the old SecurityContext?**

If the contract requires a gateway-authenticated header on every protected request, **no**. Reject and invalidate the old session rather than authorizing from a cached Authentication.

**2. Why might `RequestHeaderAuthenticationFilter` miss Alice→Bob by default?**

Because `AbstractPreAuthenticatedProcessingFilter` **skips by default when SecurityContext already holds an Authentication**. Enable `setCheckForPrincipalChanges(true)` to compare users on each request.

**3. Is `setExceptionIfHeaderMissing(true)` enough to stop missing-header stale-session bugs?**

Not automatically. If the filter skips due to an existing Authentication, header-reading methods may never execute. You need a guard enforcing header presence or an equivalent check on every protected request.

**4. Does `setContinueFilterChainOnUnsuccessfulAuthentication(false)` block `principal=null` automatically?**

No. Javadoc states it affects only `AuthenticationException` from `AuthenticationManager`; `principal=null` can still let the filter chain continue normally.

**5. Does `setInvalidateSessionOnPrincipalChange(true)` take effect when `checkForPrincipalChanges=false`?**

Not as intended: you must **enable principal-change checking** to trigger user-switch detection.

**6. When the header becomes Bob, can the app keep Alice's roles while changing only the principal name to Bob?**

No. All session-specific data and authorities must be reloaded for Bob per policy; ideally invalidate S1 and create a new session.

**7. Should two users with the same email at two IdPs share a session?**

Not automatically. Bind by **issuer + tenant + stable subject**; account linking requires its own policy.

**8. If the upstream SSO session changes while username stays identical, will `checkForPrincipalChanges` detect it?**

Not guaranteed. Name comparison will see "no change". Add a trusted upstream session binding/epoch if required by the product.

**9. Does `PreAuthenticatedAuthenticationProvider` verify whether the gateway actually logged in the user?**

No. It assumes the external system authenticated them. Network/header trust at the gateway is mandatory.

**10. What if the local user is locked while the gateway still emits a valid header?**

The application must check user status/authorization and deny. Gateway authentication does not create business privileges on its own.

**11. Does `SecurityContextHolder.clearContext()` clear `HttpSession` and Spring Session?**

No. Invalidate the session or clear/update `SecurityContextRepository` properly; otherwise the next request can restore the old auth.

**12. Why must duplicate identity headers be rejected?**

Because proxies/Servlet stacks may pick the first value, merge, or parse inconsistently, creating **identity ambiguity** and spoofing risks.

**13. When are 401 and 403 used?**

Typically **401** when re-authentication is required (missing header/expired session), and **403** when identity is known yet unauthorized or trust is violated; follow your API/security contract. Never return 200 with a stale principal.

**14. Without an upstream session ID, may you bind sessions using IP/UA?**

Avoid it. IP/UA are not stable security identities and can change or be spoofed; use a gateway-issued session ID/epoch or an approved freshness policy.

**15. Does stateless mode eliminate all proxy auth risks?**

No. It reduces stale app sessions, yet the backend must still trust only the right gateway, block header spoofing, check local authorization, and ensure gateway session freshness.

**16. If refreshing after local logout logs back in immediately, is session deletion broken?**

Not necessarily. Gateway SSO may still be active and emit a fresh header, causing the app to create a new Authentication/session. Distinguish app logout from upstream logout.

**17. Why run integration tests across two replicas?**

Because local invalidation on one node might not clear sessions in another node's store or cache. Verify shared session semantics and concurrent requests.

**18. Is a guard checking only header regex enough for production?**

No. It checks format only. You need a **trusted gateway/mTLS/network boundary**, issuer/tenant/session bindings, local account/role checks, and full authorization.

## 20. Official documentation and references

- Spring Security, **Pre-Authentication Scenarios** — external system boundaries, `RequestHeaderAuthenticationFilter`, `PreAuthenticatedAuthenticationProvider`, and UserDetails services: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security Javadoc, **RequestHeaderAuthenticationFilter** — default `SM_USER`, `exceptionIfHeaderMissing=true`, warnings on header spoofing and mixing login mechanisms: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- Spring Security Javadoc, **AbstractPreAuthenticatedProcessingFilter** — default skip when SecurityContext has Authentication, `checkForPrincipalChanges`, `invalidateSessionOnPrincipalChange`, `continueFilterChainOnUnsuccessfulAuthentication`, and `SecurityContextRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Security Javadoc, **PreAuthenticatedAuthenticationProvider** — handles pre-auth tokens, loads UserDetails without authenticating external users itself: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security, **Authentication Persistence and Session Management** — `SecurityContextHolderFilter`, explicit save, `HttpSessionSecurityContextRepository`, session fixation, and logout: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security, **SecurityContextHolder** — storing current context/auth per strategy: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security, **Servlet Logout** — session invalidation and SecurityContext cleanup: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security, **Java Configuration / FilterChain** — `securityMatcher`, filter order, and authorization: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- OWASP, **Session Management Cheat Sheet** — session fixation, expiration, logout/invalidation, and cookies: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP, **Authentication Cheat Sheet** — identity lifecycle, re-authentication, and controls: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP, **Authorization Cheat Sheet** — deny by default, permission checks, least privilege: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Key takeaway:** in proxy authentication, **missing headers**, **user switching**, and **lingering old sessions** are distinct events that easily combine into impersonation or stale-authorization bugs. `RequestHeaderAuthenticationFilter` only extracts the principal from a header without verifying external identity; by default, `AbstractPreAuthenticatedProcessingFilter` may skip requests when an Authentication already exists. Verify **gateway trust first**, require **current identity headers** on protected requests, enable principal-change detection when stateful, bind **issuer/tenant/subject/upstream session** as needed, invalidate/rotate sessions on identity changes, and recheck local permissions before returning data. **Never let an old `JSESSIONID` substitute for disappeared upstream authentication.**