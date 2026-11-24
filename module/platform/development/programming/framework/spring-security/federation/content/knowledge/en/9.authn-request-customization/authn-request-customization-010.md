# Customizing the AuthnRequest Repository in Multi-Node Deployments

> **Topic:** Spring Security – federation · **Group:** AuthnRequest Customization. This article explains how to store and restore **pending SAML 2.0 AuthnRequests** when a Spring Security Servlet application runs across multiple instances/pods. The focus is the difference between storing in a shared `HttpSession` versus storing directly in a distributed cache, version-specific Spring Security implementations, protecting login transactions against replay/login injection, testing cross-node callbacks, and handling Redis/session failures. Standalone Java examples use **JDK 17+**, while Spring configurations require compatible application and dependencies.

## 1. Goal and Problem Statement

A Service Provider (SP) application lets users sign in via a SAML Identity Provider (IdP). The system runs behind a load balancer with two nodes:

```text
Browser                      Load balancer                 Spring SP
   |                               |                          |
   | GET /saml2/authenticate/corp  |                          |
   |------------------------------>|---- routed to POD A ---->|
   |                               |                          |
   |                               |        POD A:
   |                               |        - create AuthnRequest ID=_r1
   |                               |        - save pending request
   |<------------------------------|<--- Redirect to IdP      |
   |                                                           
   | Browser authenticates at IdP; IdP returns SAMLResponse    
   | POST /login/saml2/sso/corp  |                            
   |---------------------------->|---- routed to POD B ------>|
   |                               |        POD B:
   |                               |        - find pending _r1?
   |                               |        - verify response?
```

If the pending request lives only in **POD A's local memory**, POD B cannot find it. Consequences can include `InResponseTo` mismatches, failure to resolve the registration, login errors, or teams trying to “fix” it by disabling transaction checks. Disabling correlation verification to avoid routing errors is a **security mistake**.

A sound design must help a callback on POD B retrieve the right transaction, **while still knowing the response belongs to a login flow initiated by that browser/SP**, rather than fetching an arbitrary record solely by an ID supplied by the sender.

### After This Lesson, Learners Can

1. Distinguish `HttpSession`, `Saml2AuthenticationRequestRepository`, `RequestCache`, and the post-login user session store.
2. Choose between **Spring Session + Redis** (shared `HttpSession`) and a **custom/distributed request repository**; recognize when sticky sessions are insufficient.
3. Understand the contract of `saveAuthenticationRequest`, `loadAuthenticationRequest`, and `removeAuthenticationRequest`.
4. Specify lookup keys, TTL, one-time consumption, collisions, cookie binding, and replay handling in multi-node setups.
5. Apply Spring Security 6.x configuration to a realistic scenario and understand version-specific API limits.
6. Test happy paths, replay, lost cookies, cross-pod callbacks, multi-tab flows, outages, and tenant isolation.

## 2. What Is a Pending AuthnRequest in SAML2?

In SP-initiated Web SSO, Spring Security's request filter constructs `<samlp:AuthnRequest>` and sends it to the IdP via the browser. The IdP authenticates the user and returns `<samlp:Response>` to the SP's Assertion Consumer Service (ACS). The Response typically includes `InResponseTo` referencing the issued request ID.

Abbreviated conceptual illustration:

```text
SP creates: AuthnRequest ID="_req_a01"
  Issuer = https://portal.example.org/sp
  Destination = https://login.example.org/saml/sso
  ACS = https://portal.example.org/login/saml2/sso/corp

IdP returns: SAMLResponse InResponseTo="_req_a01"
  Issuer = https://login.example.org/idp
  assertion intended for registered SP entityID / ACS
```

To process the response, the SP must remember prior request details: registration, correlation values, RelayState/context, and data stored in `AbstractSaml2AuthenticationRequest`. This is **pending authentication state**. It is not a verified SAML assertion, not an access token, and not user permissions.

### 2.1. Why Must Requests Be Stored?

- **Correlation:** match the response's `InResponseTo` against the issued AuthnRequest to avoid accepting a response meant for another transaction.
- **Selecting IdP/SP configuration:** the callback must resolve the right `RelyingPartyRegistration` and trusted key set to verify signatures/issuer.
- **Transaction binding:** when using `HttpSession`, state is bound to the pre-login browser session; a request is never accepted just because someone else supplied a RelayState/ID present in the store.
- **Preventing reuse:** a processed request must not be accepted again; decide TTL, one-time semantics, and replay protection per policy.
- **Flow restoration:** perform valid post-authentication redirects without confusing them with saved requests or unverified client claims.

### 2.2. Four Distinct Stores

| Store / Component | Data | Purpose |
| --- | --- | --- |
| `Saml2AuthenticationRequestRepository` | `AbstractSaml2AuthenticationRequest` awaiting SAML response | Correlate and retrieve SAML requests |
| `HttpSession` / Spring Session | Browser session attributes, potentially including pending SAML state and post-login SecurityContext | Maintain session across requests and across instances when shared |
| `RequestCache` | Request URL the user wanted to open before login, e.g., `/reports` | Redirect back to the original page after login |
| `SecurityContextRepository` | Authenticated `Authentication` / `SecurityContext` | Identify the user on subsequent requests |

**Do not use `RequestCache` or `SecurityContextRepository` to replace `Saml2AuthenticationRequestRepository`.** These stores serve different purposes. A deployment may use Redis for both sessions and caches, yet must never mix their keys, lifetimes, or trust boundaries.

## 3. Who Reads and Writes Saml2AuthenticationRequestRepository?

Typical Spring Security Servlet flow:

```text
GET /saml2/authenticate/{registrationId}
    |
    v
Saml2WebSsoAuthenticationRequestFilter
    |
    v
Saml2AuthenticationRequestResolver
    |
    v
AbstractSaml2AuthenticationRequest
    |
    +--> repository.saveAuthenticationRequest(...)
    |
    +--> HTTP Redirect/POST SAMLRequest to IdP

IdP authenticates then redirects browser to SP ACS

POST /login/saml2/sso/{registrationId}
    |
    v
Saml2WebSsoAuthenticationFilter
    |
    v
Saml2AuthenticationTokenConverter
    |
    +--> repository.loadAuthenticationRequest(...)
    +--> repository.removeAuthenticationRequest(...)
    |
    v
SAML authentication provider:
  signature/trust + issuer + audience + recipient + time
  + InResponseTo/subject confirmation + protocol checks
    |
    v
Authentication / SecurityContext or rejection
```

This is a **conceptual flow**. Exact timing of `load` and `remove` calls or fallback rules depends on the version/converter. Do not assume every framework release consumes pending requests at the exact same moment or includes a cross-node replay cache out of the box. When customizing the repository, test against the source/Javadoc of your running version.

### 3.1. Actual Interface

In Spring Security 6.3–6.5, the interface resides in package:

```java
org.springframework.security.saml2.provider.service.web
    .Saml2AuthenticationRequestRepository<T>
```

With `T extends AbstractSaml2AuthenticationRequest`, it has three methods:

```java
T loadAuthenticationRequest(HttpServletRequest request);

void saveAuthenticationRequest(
        T authenticationRequest,
        HttpServletRequest request,
        HttpServletResponse response);

T removeAuthenticationRequest(
        HttpServletRequest request,
        HttpServletResponse response);
```

This is an **excerpted interface signature for learning**, not a standalone compilable Java class: it requires Jakarta Servlet/Spring Security imports and the interface declaration of `T`. Meaning:

- `save` takes the prepared AuthnRequest and HTTP context to persist state.
- `load` retrieves the pending request matching the HTTP callback; returns `null` if absent.
- `remove` deletes and returns the pending request; with a shared cache, ensure consistent consumption semantics under concurrency.
- Never add a local `static Map` and call it a multi-node repository; each JVM has separate memory.

### 3.2. Default Component

`HttpSessionSaml2AuthenticationRequestRepository` stores the pending request in `HttpSession`. It carries a security advantage: when an attacker creates a SAML login request in the **attacker's session**, a victim's browser using a **different session** cannot automatically load that pending request. This helps defend against login fixation/login injection.

However, an `HttpSession` **residing solely in one node's memory** is not shared automatically with other nodes. You must ensure the callback sees the right session via **sticky sessions**, **session replication**, or a **shared session store**. In systems with auto-scaling/failover, a shared store is usually more resilient than pure sticky routing.

## 4. Three Multi-Node Architectures and Trade-Offs

| Architecture | Where Is Pending AuthnRequest? | Can POD B Read Callback Created on POD A? | Operational / Security Risks |
| --- | --- | --- | --- |
| Local Servlet HttpSession + sticky routing | RAM of POD A | Usually no; only if callback routes back to POD A | Pod death loses pending request; no guarantee on route changes |
| **Spring Session backed by Redis** + `HttpSessionSaml2AuthenticationRequestRepository` | Redis-backed browser session | **Yes**, if browser sends matching session cookie and nodes share the store | Requires proper cookies/serialization/TTL/Redis availability |
| **Distributed cache AuthnRequest repository** | Redis/cluster cache by state/request key | Possible even if session cookie is lost | Must design browser binding, TTL/atomic consume; easy to introduce login injection if looking up solely by RelayState |

**Key decision point:** a custom request repository shares only the **pending AuthnRequest**; it does not automatically share `SecurityContext` or other session data. If POD B creates a new post-login session and the next request hits POD A, the app still needs shared sessions or session affinity to keep the authenticated session alive.

**Not every application needs a custom repository.** If the goal is cross-pod callbacks while the browser still carries normal session cookies, **sharing HttpSession via Spring Session** preserves session-based correlation with minimal changes to SAML code. When cookies do not traverse cross-site POSTs or the system is intentionally sessionless, consider a distributed request cache, but solve login binding separately.

## 5. Option A: Sharing HttpSession with Spring Session + Redis

### 5.1. Concept

```text
                         ┌─────────────────────┐
Browser ───> LoadBalancer│                     │
                         │  POD A / POD B      │
                         │  Spring Security    │
                         └────────┬────────────┘
                                  │
                             Redis Session
                                  │
                     ┌────────────▼───────────┐
                     │ sessionId = S-browser  │
                     │ pending AuthnRequest   │
                     │ SecurityContext ...    │
                     └────────────────────────┘

Request starts at POD A:
  HttpSession[S-browser].pending = AuthnRequest(_req_A)

Callback arrives at POD B; browser sends same session cookie:
  Spring Session loads S-browser from Redis
  HttpSessionSaml2AuthenticationRequestRepository finds _req_A
  Valid SAMLResponse -> Authentication/session
```

Spring Session replaces the servlet container's `HttpSession` storage with a Redis-backed implementation. Spring Security code still reads/writes `HttpSession`; only the session backend changes. This **preserves the default browser-session boundary** across a multi-pod topology.

### 5.2. Maven Dependencies

In a Spring Boot Servlet project using Spring Security SAML2, add dependencies managed by the matching Spring Boot BOM:

```xml
<dependencies>
    <!-- Spring Security / SAML2 service provider already configured by the project -->
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
```

This is a **`pom.xml` fragment**, not a complete POM. In practice you also need `spring-boot-starter-web`, `spring-boot-starter-security`, and dependencies/OpenSAML repositories compatible with your Spring Boot/Spring Security version. Do not hard-code arbitrary versions; let the BOM manage compatible Spring releases.

### 5.3. Example application.yml

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
  session:
    redis:
      namespace: "portal:sessions"

server:
  servlet:
    session:
      timeout: 30m
```

This YAML **illustrates connection and namespace settings only**, not a production Redis cluster. Configure TLS, authentication/secret management, high availability, per-environment namespaces, serialization policies, and timeouts per infrastructure. `server.servlet.session.timeout` is the idle session timeout in this example, not a separate TTL for every pending AuthnRequest.

All pods must agree on:

- The same Redis cluster/database or shared session backend, with compatible namespaces/serializers.
- The same SAML `RelyingPartyRegistration`, IdP metadata/certificates, and public SP entityID/ACS; never let POD A issue a registration unknown to POD B.
- The same public HTTPS origin and consistent session cookie name/scope/path, never returning an internal hostname to the browser.
- Handling key rotation, rolling deployments, and serialization compatibility while multiple app versions run concurrently.
- Synchronized session expiration/logout and behavior when Redis is unavailable.

### 5.4. Filter Chain Without Rewriting the Request Repository

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlWebSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

This is a **source-complete Spring Security class**, yet the application still requires configured SAML registrations, Spring Boot web/security dependencies, Redis, and an IdP; this class is not a `main` program run with plain `javac`.

Core idea: keep the default `HttpSessionSaml2AuthenticationRequestRepository`; Spring Session makes `HttpSession` readable across every pod. When a request starts on A and the callback lands on B **with the same session cookie**, the pending request can be retrieved. This is the first practical option to evaluate before replacing the request state mechanism entirely.

### 5.5. Test in Practice Instead of Just Reading YAML

1. Start two pods A/B sharing the Redis Session store.
2. Start login at POD A; record a **non-sensitive request correlation ID** and test backend key/namespace with session IDs redacted.
3. Route the ACS POST to POD B in the test environment; the browser must send the matching session cookie.
4. Confirm the response is not rejected for a missing request, then verify post-login resource access works on both A and B.
5. Shut down POD A after initiating the request to verify failover, Redis availability, and timeouts.
6. Run two app versions during a rolling deployment to catch serialization incompatibilities or registration drift.

**Limitation of Option A:** if the browser **does not send the session cookie** on a cross-site SAML POST, POD B cannot select the right session even when Redis is healthy. That is a browser/session binding issue, not “Redis out of sync.”

## 6. SameSite and Callbacks Missing the Session Cookie

### 6.1. Why Does SameSite Affect SAML?

In common flows, the browser leaves the SP for the IdP and returns to the SP via a **cross-site POST** carrying `SAMLResponse`. With an SP cookie set to `SameSite=Lax` or `Strict`, the browser may withhold that cookie on the POST. Then:

```text
POD A creates session S42 and saves AuthnRequest(_req_42) in Redis.
Browser stores cookie SESSION=S42.
IdP has browser POST SAMLResponse to SP ACS.
Cookie SESSION=S42 blocked by browser due to cross-site POST.
POD B receives POST without session S42.
Default repository cannot find _req_42.
```

Therefore, inspect all of the following:

- Actual cookie attributes in `Set-Cookie`: `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`.
- Does the browser send the `Cookie` header on the ACS POST?
- Does a proxy alter scheme/host/cookie attributes?
- Are browser, IdP, and SP same-site under schemeful same-site rules or genuinely cross-site? Do not judge subdomains by eye alone.
- Are reverse proxy/ingress settings trusted for computing `{baseUrl}`/ACS and cookie security?

### 6.2. Appropriate Cookie Strategy

Depending on browsers, IdP mechanisms, and application requirements, cookies needed on cross-site POSTs may require `SameSite=None; Secure`. This **does not prevent CSRF**, so business endpoints must keep CSRF protection and other safeguards. `HttpOnly` reduces JavaScript cookie-reading risk, though it does not stop XSS from acting on the user's behalf.

In an application using Spring Session, you can configure `DefaultCookieSerializer` depending on version:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("None");
        return serializer;
    }
}
```

This is a **cookie policy example for cases requiring cross-site POST**, not a mandatory setting for every SP. Check your Spring Session version, real-browser SameSite behavior, and CSRF/HTTPS before adopting. If an app insists on `SameSite=Strict` by internal policy, it must design another state mechanism that still preserves login fixation defenses rather than dropping correlation.

## 7. Option B: Dedicated Distributed Cache for AuthnRequest

### 7.1. When to Consider?

- The system must retrieve requests outside `HttpSession` (e.g., cookie-less callbacks).
- Requirements demand active-active operation or state caching decoupled from session lifecycle.
- A solution for multiple concurrent/multi-tab AuthnRequests where testing shows the default session repository falls short.
- The application uses Spring Security 6.5+ with `CacheSaml2AuthenticationRequestRepository` or implements `Saml2AuthenticationRequestRepository` directly on older versions.

However, **shared pending request data does not mean the current browser is authorized to use that request**. If `RelayState`/`InResponseTo` serves as the sole lookup key, an attacker can initiate a request in their own browser and trick a victim's browser into submitting a response matching that key. Official Spring Security docs note that out-of-session caches can lose the natural login fixation protection of sessions. Decide your trust model and browser/transaction binding mechanisms before choosing this path.

### 7.2. Spring Security 6.5+: CacheSaml2AuthenticationRequestRepository

**Version is critical:** `CacheSaml2AuthenticationRequestRepository` was introduced in **Spring Security 6.5**. This class cannot be used directly in a Spring Security 6.3 project. The 6.5 Javadoc explicitly states its **default cache is in-memory**, unsuitable for multi-node setups; you must configure an `org.springframework.cache.Cache` **backed by a distributed store**.

Example class for **Spring Security 6.5+**, assuming the app provides a `CacheManager` with a cache named `samlAuthnRequests`:

```java
import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.web.CacheSaml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.authentication.AbstractSaml2AuthenticationRequest;

@Configuration
public class SharedSamlAuthnRequestConfiguration {

    @Bean
    Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>
    authenticationRequestRepository(CacheManager cacheManager) {

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("samlAuthnRequests"),
                "Distributed SAML request cache must be configured");

        CacheSaml2AuthenticationRequestRepository repository =
                new CacheSaml2AuthenticationRequestRepository();
        repository.setCache(cache);
        return repository;
    }
}
```

**Conditions for use:**

- The class is **Spring configuration**, with no `main` to run standalone; it requires Spring Security **6.5+** and a `CacheManager` genuinely backed by Redis or a distributed store.
- Simply calling `getCache("samlAuthnRequests")` **does not guarantee** a distributed cache. A local `ConcurrentMapCacheManager` still leaves each pod with its own copy; verify runtime beans and run cross-pod tests.
- The cache bean needs a short TTL and an explicit serialization policy for `AbstractSaml2AuthenticationRequest`/subtypes. Verify serializers and rolling-deploy versioning; do not assume every framework object works automatically with JSON or JDK serialization.
- `CacheSaml2AuthenticationRequestRepository` uses state/RelayState lookup mechanisms in documented releases; evaluate login injection/browser binding independently. This is **not** inherently more secure than the default session-bound approach.
- Do not create a second conflicting request repository bean. Ensure DSL/SAML filters use **the exact same instance** for both save and load/remove.

Example Redis cache config in Spring Boot (YAML fragment; requires real cache manager dependencies and Redis):

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
  cache:
    type: redis
    cache-names: samlAuthnRequests
    redis:
      time-to-live: 5m
```

`spring.cache.redis.time-to-live` typically affects the Redis cache manager across corresponding caches, so if the project has multiple caches with distinct TTLs, **configure the `samlAuthnRequests` cache individually** rather than setting a global TTL accidentally. This YAML snippet omits keyspace isolation, TLS/auth, serializers, and single-use consumption rules. Never use the sample with a default in-memory cache in a cluster.

### 7.3. For Spring Security 6.3–6.4: Controlled Custom Interface Implementation

When `CacheSaml2AuthenticationRequestRepository` is unavailable, one option is implementing `Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>`. This carries a significant security surface; evaluate Spring Session first if browsers can still carry cookies. If you must write a repository, define an explicit data contract:

| Component | Responsibility |
| --- | --- |
| Cache key | Opaque random state/ID with ample entropy, scoped to registration/tenant; never derived from email/username |
| Value | Prepared request details needed to restore `AbstractSaml2AuthenticationRequest` and protected context |
| Save | Write with TTL and cardinality limits; avoid overwriting another transaction |
| Load | Consistently identify the pending transaction, checking session/browser binding if present |
| Remove | Single-use consumption, atomic for the same key across pods |
| Expiry | Bound the login wait window and clean up storage; never retain requests indefinitely |
| Availability | When cache is unreachable, fail closed safely rather than letting login bypass checks |
| Multi-tenant | Prevent an ID/issuer/registration from tenant A from retrieving tenant B's request |
| Serialization | Version-compatible; never store keys/private material or unnecessary data |
| Telemetry | Log events/correlation IDs; never log SAMLResponse/cookies/secrets/raw state |

**Architectural** pseudocode, not copy-pasteable Java/Spring implementation:

```text
SAVE(pendingRequest, browserContext):
    assert registration is trusted
    state := cryptographically-random, short opaque key
    record := {
        requestId, registrationId, expectedIdpIssuer,
        createdAt, expiresAt, browserBinding,
        preparedRequest
    }
    sharedStore.PUT_IF_ABSENT(state, record, TTL)
    return state for protocol RelayState

LOAD(callback):
    state := validated opaque RelayState or secured lookup context
    record := sharedStore.READ(state)
    if missing, expired, wrong browserBinding/registration: REJECT
    return preparedRequest for SAML validation

REMOVE(callback):
    apply one-time atomic consume semantics across pods
    return consumed preparedRequest or null
```

In real deployments, Spring Security controls when `load`/`remove` are invoked; you cannot arbitrarily decide “validate then remove” contrary to the filter contract. Inspect the lifecycle of your exact version. Consuming a record prematurely on an invalid callback can cause **denial of service** for an in-flight login; consuming late without atomicity enables replay races. Balance safety, retryability on errors, and one-time guarantees per threat model.

### 7.4. Browser Binding Is the Hardest Part

Suppose:

```text
Attacker Browser A   -> SP creates Request ID=_attack
                       RelayState=R_attack
                       sharedStore[R_attack] = pending(_attack)

Victim Browser B     -> POST SAMLResponse with RelayState=R_attack
                       to SP ACS
```

If the SP simply looks up `R_attack` and finds a valid request, it **cannot tell that request was issued to Browser A rather than B**. A signed SAMLResponse with valid issuer/audience does not prove B initiated login either. That is a form of **login CSRF/login fixation/session confusion**, often leading to logging the victim into an unintended identity and, in some apps, account-linking vulnerabilities.

Mitigations must be designed **together**:

1. Keep browser/session binding wherever possible: a dedicated nonce/transaction cookie with callback-compatible attributes, or a real session. Trust cookies only under signed/protected policy and check expiration.
2. Use high-entropy, short-lived, single-use RelayState; **never treat RelayState secrecy as sole proof** that the browser initiated login if an attacker can steer or relay it.
3. Bind request ID, registration, tenant, IdP issuer, and session correlation to the browser's request.
4. Verify `InResponseTo` and signed SAMLResponse/assertion, audience, recipient, ACS, issuer, subject confirmation, and validity window in the standard authentication provider.
5. Enforce anti-replay (response/assertion IDs) with an atomic/shared store per policy; never assume deleting the pending request alone suffices.
6. Cap pending entries per browser, request size, and total pending keys to prevent cache bloat/DoS attacks.
7. If strong browser binding cannot be achieved under current cookie/browser constraints, **do not claim state-keyed distributed lookup is security-equivalent to a session-bound repository**.

## 8. Designing Keys, TTL, Single-Use, and Consistency

### 8.1. Secure Storage Keys

A good `state` key is an opaque random value with high entropy, leaking no user ID/email and carrying no business meaning. If using request IDs or RelayState, validate origin, uniqueness, and scope; reject malformed or oversized states.

**Do not key solely by email or tenant.** Two logins for the same user would overwrite each other, and one tenant could affect another transaction. Separate environment, version, registration, and state cleanly in storage keyspaces.

Illustrative keyspace example:

```text
saml:pending:v1:prod:<registrationId>:<opaqueState>
```

Items in `<...>` are placeholder notation, not special Redis/Spring keywords. Namespaces must be canonicalized/trusted to prevent cache key injection. Records must never expose raw session IDs in logs.

### 8.2. TTL and System Clocks

Example policy for an environment (tune for your actual IdP and user experience):

| Parameter | **Illustrative** Value | Explanation |
| --- | --- | --- |
| Pending AuthnRequest TTL | 5 minutes | Maximum window to retrieve an incomplete request |
| Max pending requests per browser | 3 | Limits multi-tab/DoS while allowing some concurrent logins |
| SAML clock skew allowance | 60 seconds | Tolerates minor clock drift; never widen acceptance arbitrarily |
| Redis record expiry | No later than policy-allowed window | Never retain stale requests for hours or indefinitely |
| Authentication session timeout | 30 minutes idle (separate example) | Post-login user session differs from pending request TTL |

Pending TTL is **not** session timeout, and session timeout is **not** SAML assertion lifetime. When an IdP requires complex MFA that takes time, balance TTL against UX and replay risk. All SP pods and IdPs should sync via NTP; never use huge clock skew to mask clock drift.

### 8.3. Atomic Consumption and Concurrent Callbacks

If two pods read the same key:

```text
POD A: GET(state) -> exists
POD B: GET(state) -> exists
POD A: DELETE(state) -> success
POD B: DELETE(state) -> success/ignored
```

Both could think they own processing if load/remove are non-atomic. On supported backends, use single-use operations like Redis `GETDEL` (Redis 6.2+) or suitable Lua scripts/transactions; yet **consumption timing must adhere to Spring Security's lifecycle** so you neither break validation nor create DoS. Consuming pending state alone **does not replace** protocol-level assertion/response anti-replay.

Once a request expires past TTL, `load`/`remove` must report absent/expired per policy and reject authentication accordingly. Never synthesize a replacement request “to match” a callback arriving without a stored record.

### 8.4. Consistency and Failover

- All pods must know the same registrations and IdP trust/certificates; shared Redis alone is insufficient if pod configs diverge.
- Cache systems can experience replication lag, failover, eviction, and split-brain; verify backend **read-after-write** and atomicity guarantees.
- Never use an aggressively evicting cache for pending logins without monitoring `request not found` rates.
- Storing Java objects requires rolling-deployment-compatible serializers. Encrypt data at rest and in transit, restrict Redis ACLs, and never expose caches directly to the Internet.
- When the cache fails, fail closed for missing authentication state; optionally let users restart login with a clear message.
- Test callbacks landing on another pod, during rolling restarts, and during Redis primary failovers to verify real behavior.

## 9. Coordinating the Request Repository with SAML Validation

Even when the pending request is retrieved accurately, the SP must still verify the **SAMLResponse**:

| Check | Goal |
| --- | --- |
| Trusted IdP signing certificate/issuer | Response/assertion came from the configured IdP, not a browser-supplied key |
| XML signature over actual consumed data | Prevent signature wrapping / reading an unsigned assertion |
| `AudienceRestriction` / SP entityID | Assertion is intended for this exact SP |
| `Destination` and `Recipient`/ACS | Response was sent to the right SP endpoint |
| `InResponseTo` | Response answers the issued/saved AuthnRequest |
| `NotBefore` / `NotOnOrAfter` | Assertion and subject confirmation are still valid |
| Registration/tenant/account mapping | Do not mix data from IdP A into tenant B |
| Response/assertion replay handling | Do not accept previously used evidence again |
| Post-login authorization | Grant access only per endpoint/role/tenant/object policy |

**Do not turn `Saml2AuthenticationRequestRepository` into an authentication provider.** The repository handles pending requests and correlation; signature verification belongs to the Spring Security/OpenSAML provider. When customizing response validation, keep default checks intact rather than replacing them with a “pass-through” validator for cache compatibility.

For unsolicited IdP-initiated responses, `InResponseTo` may be absent. If the application does not need that flow, reject it per policy. If needed, design browser binding, recipient/issuer validation, and replay protection explicitly; never let a cache lookup failure automatically accept an unsolicited response.

## 10. Hands-On Java 17: Shared State Across Two Nodes and Atomic Consumption

The following demo **runs on plain Java 17**, simulating two nodes sharing one store in a single process. It checks **browser binding**, expiration, and single-use consumption via `ConcurrentHashMap.remove(key, expectedValue)`; it does not build/decode XML, verify SAML signatures, connect to Redis, or run two real JVMs. Its purpose is demonstrating **distributed pending-state logic**, not a production SAML repository.

Save `MultiNodeAuthnRequestDemo.java`:

```java
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

public class MultiNodeAuthnRequestDemo {

    record PendingRequest(
            String requestId,
            String registrationId,
            String browserBinding,
            Instant expiresAt) {}

    static final class SharedStore {
        private final ConcurrentHashMap<String, PendingRequest> pending =
                new ConcurrentHashMap<>();

        void save(String key, PendingRequest request) {
            if (pending.putIfAbsent(key, request) != null) {
                throw new IllegalStateException("Duplicate pending key");
            }
        }

        boolean consume(String key, String registrationId,
                        String browserBinding, Instant now) {
            PendingRequest original = pending.get(key);
            if (original == null) {
                return false;
            }
            if (!original.registrationId().equals(registrationId)
                    || !original.browserBinding().equals(browserBinding)
                    || !now.isBefore(original.expiresAt())) {
                return false;
            }
            return pending.remove(key, original);
        }
    }

    static final class Node {
        private final SharedStore store;

        Node(SharedStore store) {
            this.store = store;
        }

        void begin(String key, PendingRequest request) {
            store.save(key, request);
        }

        boolean finish(String key, String registrationId,
                       String browserBinding, Instant now) {
            return store.consume(key, registrationId, browserBinding, now);
        }
    }

    public static void main(String[] args) {
        SharedStore shared = new SharedStore();
        Node podA = new Node(shared);
        Node podB = new Node(shared);
        Instant now = Instant.parse("2026-11-07T03:00:00Z");

        podA.begin("state-1", new PendingRequest(
                "_req_1", "corp", "browser-1", now.plusSeconds(300)));
        System.out.println("wrong browser: "
                + podB.finish("state-1", "corp", "browser-2", now));
        System.out.println("wrong registration: "
                + podB.finish("state-1", "partner", "browser-1", now));
        System.out.println("cross-pod success: "
                + podB.finish("state-1", "corp", "browser-1", now));
        System.out.println("replay: "
                + podA.finish("state-1", "corp", "browser-1", now));

        podA.begin("state-2", new PendingRequest(
                "_req_2", "corp", "browser-1", now.minusSeconds(1)));
        System.out.println("expired: "
                + podB.finish("state-2", "corp", "browser-1", now));
    }
}
```

Run:

```bash
javac MultiNodeAuthnRequestDemo.java
java MultiNodeAuthnRequestDemo
```

**Exact** stdout:

```text
wrong browser: false
wrong registration: false
cross-pod success: true
replay: false
expired: false
```

Explanation:

- `wrong browser=false`: a callback with a different browser binding cannot consume pending state.
- `wrong registration=false`: matching key but wrong registration is still rejected.
- `cross-pod success=true`: POD A saves, POD B consumes from the **same** `SharedStore`.
- `replay=false`: record was removed, so a second attempt cannot consume it.
- `expired=false`: unexpired and expired states are distinguished at check time. The demo leaves expired records in the map to stay brief; production requires TTL eviction.

**Crucial caveat:** `browserBinding` is just a String simulating a trusted binding; an attacker could guess/supply values in the demo, with no cryptographic validation. `ConcurrentHashMap` shares state only within **one JVM**; never use it instead of Redis in a cluster. Check-then-remove does not mirror the exact lifecycle of every Spring Security repository, and the demo does not verify signed `SAMLResponse`/`InResponseTo`/audience/time conditions per SAML. Never drop this code directly into a production SAML filter.

## 11. What Should Multi-Node Testing Cover?

### 11.1. Real Cross-Pod Happy Path

Set up a test environment with:

- Two SP instances sharing registrations/keys behind the same load balancer and public HTTPS origin.
- A test IdP issuing validly signed SAML Responses/Assertions with registered ACS URL/metadata.
- Shared Redis/session or cache with test-configured namespaces and TTLs.
- Controlled routing to deliberately send `/saml2/authenticate/corp` to POD A and the ACS POST to POD B.

Test:

```text
Given  POD A and POD B share the intended repository
When   the browser begins SP-initiated SSO on POD A
And    valid SAMLResponse reaches ACS on POD B
Then   B finds correct pending request and validates response
And    user obtains an authorized session that works on both pods
```

Observe via logs **containing no raw SAML payloads**. Record `nodeId`, `registrationId`, correlation ID, result/error code, latency, and backend availability. Never log session cookies, secret RelayState, or full SAMLResponse in logs/traces.

### 11.2. Negative Test Matrix

| Scenario | Expectation |
| --- | --- |
| Request created on A, callback hits B | PASS if browser/session and storage align |
| A dies after sending request, B receives callback | PASS or fail safely per HA policy; never bypass validation |
| Browser omits session cookie | Session-bound repo misses state; handle clearly, never auto-accept unsolicited response |
| Callback uses never-issued request ID | Reject |
| `InResponseTo` matches already-consumed request ID | Reject |
| Same response replayed concurrently to A and B | Succeeds at most once or zero times per policy; never two sessions from replay |
| RelayState altered, empty, oversized, or malformed | Reject or handle per policy; no arbitrary lookups |
| Invalid SAML signature | Reject even if cache found pending request |
| Wrong Issuer/Audience/Recipient/ACS | Reject even if cache found pending request |
| Registration/tenant A with tenant B's state | Reject; never cross-map users |
| Pending TTL expires while user is at IdP MFA | Reject with restartable error; never set infinite TTL |
| Redis outage on save | Do not treat issued request as successfully stored |
| Redis outage on load/remove | Fail closed; never skip transaction correlation |
| Premature cache eviction | Diagnosable login failure; never auto-disable verification |
| Two login tabs in the same browser | Do not mix request IDs/registrations; verify exact repository behavior |
| Cross-version rolling deployment | Compatible serializer or safe logged failure |
| Logged-out/invalidated session | Do not reuse pending state contrary to policy |
| `SameSite=Lax`/`Strict` cookie on cross-site POST | Accurate browser test; handle session/cookie policy deliberately |
| Attacker and victim have different cookies | Never accept attacker's request for victim's browser |
| Using default in-memory cache of `CacheSaml2AuthenticationRequestRepository` | Cross-pod test FAILS as expected; must supply distributed `Cache` |
| Authenticated user hits another pod | Session/`SecurityContext` persists too, not only pending SAML state |

### 11.3. Single-Use and Concurrent Race Test

Take one validly signed test response and fire two **concurrent** callbacks to POD A and POD B. Verify two authentications never succeed contrary to policy; verify consistent consumption of the pending record and replay detection at the SAML layer. With a real Spring Security release, if `removeAuthenticationRequest` runs inside or after the converter, observe timing to confirm atomicity. Do not rely solely on unit tests calling repository methods directly while skipping end-to-end filter/provider tests.

### 11.4. Independent Session Binding Test

Run two browser profiles A and B, each with its own session cookie. Browser A starts login, then try submitting the corresponding response/state from B in the test environment. A session-bound design must reject it, whereas a RelayState-only cache may behave differently. This is a security test to run **before** approving a replacement for the default repository.

## 12. Common Issues and Troubleshooting

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| Login works only with sticky sessions enabled | Request state lives only in local session/JVM | Share `HttpSession` or use a suitable repository |
| Already using Redis, yet callbacks still lose requests | Browser omits session cookie, wrong Redis namespace, serializer, timeout | Browser network ACS POST, `Set-Cookie`, pod config, Redis availability |
| POD A saves, POD B cannot read | Different Redis cluster/database/namespace or local cache | Inspect runtime `CacheManager` bean, logs/cache TTL |
| `CacheSaml2AuthenticationRequestRepository` works on 1 pod, fails on 2 | Forgot to call `setCache(distributedCache)` | Javadoc: default cache is in-memory |
| Validly signed SAMLResponse fails `InResponseTo` | Request TTL expired, tab/session state mixed, registration mismatch | Correlation logs, request repository, TTL, same browser |
| After POD B login, next request to POD A prompts re-login | Only AuthnRequest was shared; authenticated session stayed local | Spring Session/shared `SecurityContext` or affinity |
| `SameSite=None` set, yet cookie still omitted | Missing `Secure`, browser third-party cookie policy, wrong domain/path | Cookie attributes and browser console/network |
| Redis timeouts cause widespread login failures | Dependency outage/latency | Circuit breakers/error budgets, HA Redis, fail closed |
| Raising TTL excessively fixes login but increases replay risk | Masked root cause of state/cookie loss | Investigate SameSite, IdP MFA duration, expiration policy |
| Two nodes emit different SP entityID/ACS | Configuration drift | Compare metadata, boot configs, and release pipeline |
| App fails deserializing pending objects after rollout | Java/framework serialization incompatibility | Versioning/serializers, rollout tests, migration policy |
| Logged into unintended account after swapping repo | Lost browser binding, looked up by state alone | Login CSRF/fixation review, restore binding |
| Cache bloat from excessive pending requests | Unbounded pending requests/key sizes | Quotas, TTL, rate limits, and monitoring |
| 404 at ACS after proxy change | Bad routing/`SecurityFilterChain` | Ingress paths, public ACS, matchers/filter chain |
| 403 at ACS POST | CSRF endpoint matcher/cookie/authorization | Never disable CSRF globally; configure SAML callback properly |
| Replay across 2 pods still succeeds | Non-atomic consume or missing replay detection | Load tests, Redis atomic ops, SAML replay policy |

### 12.1. Observability and Alerting

Log data-minimized events:

```text
event=saml_pending_request_saved
node=pod-a
registration=corp
request_correlation_id=<redacted-id>
backend=redis
result=success
timestamp=...

event=saml_pending_request_missing
node=pod-b
registration=corp
reason=NOT_FOUND_OR_EXPIRED
backend=redis
timestamp=...
```

This is a **log schema sample**, not real logs. Never log `SAMLRequest`/`SAMLResponse`/assertions, session cookies, SP private signing keys, or secret RelayState in production. A request ID/RelayState can correlate transactions, so log sanitized internal fingerprints/IDs with retention and access controls.

Monitor `pending NOT_FOUND` rate, `InResponseTo mismatch` rate, Redis latency, eviction/TTL expiry, save/load/remove errors, session loss after rolling restarts, replay attempts, anomalous pending key counts, per-pod login success, and cross-pod callback rate.

## 13. Choosing a Solution by Requirement

| Requirement | Option to Evaluate First | Why |
| --- | --- | --- |
| Two pods, browser keeps session cookie on callback | Spring Session shared `HttpSession` | Preserves session binding with minimal SAML code changes |
| Only need pod-failover resilience | Shared session or affinity + failover policy | Avoids custom state parsers |
| Cross-site SAML POST drops cookies | Inspect SameSite/browser policy; design matching state/cookies | Even Redis-backed sessions need cookies to find the right session |
| Must enforce `SameSite=Strict` everywhere | Distributed cache + custom browser binding design | Alters trust model; requires security review and login injection tests |
| Spring Security 6.5+ already has distributed `Cache` | `CacheSaml2AuthenticationRequestRepository#setCache(...)` | Framework-provided API, but ensure cache is genuinely shared |
| Spring Security 6.3–6.4, cannot use sessions | Custom `Saml2AuthenticationRequestRepository` | Must handle lifecycle, browser binding, atomicity, and serialization yourself |
| Post-login sessions must also span all pods | Spring Session/shared authenticated session | A custom pending repo alone does not solve post-login sessions |
| Multi-region active-active | Backend with consistency/atomic consume, clear routing and failover strategy | Eventual consistency can allow replay or drop requests |

**No single choice fits every system.** The rule is preserving the security properties of SAML transactions while solving multi-node requirements. If switching from session-bound to state-keyed lookup, explicitly document **how login fixation defenses change** and test accordingly.

## 14. Pre-Production Review Checklist

- [ ] Selected an architecture—shared HttpSession, sticky session, distributed pending cache, or hybrid—with rationale and threat model.
- [ ] `Saml2WebSsoAuthenticationRequestFilter` and callback converter/filter use **the exact same repository**; no conflicting config beans.
- [ ] Multi-node A → B and failover tests ran against a test IdP; post-login `SecurityContext` also works across all pods.
- [ ] If using Spring Session, all pods share the backend, namespace, serializer, session cookie, and trusted proxy config.
- [ ] If using `CacheSaml2AuthenticationRequestRepository`, version is **>= 6.5** and `setCache(...)` points to a real distributed cache; default in-memory does not count as clustered.
- [ ] Pending requests have TTL, key entropy, and resource caps; cache outages fail closed.
- [ ] Browser/session binding is preserved or replaced by a security-reviewed mechanism; never trust RelayState/`InResponseTo` alone.
- [ ] SAML signed responses/assertions are validated with trusted IdP keys; issuer/audience/recipient/time/correlation and replay checks remain active.
- [ ] Atomic consume/race tested with concurrent callbacks on two pods; tested submitting the same state multiple times.
- [ ] `Secure`, `HttpOnly`, `SameSite`/Domain/Path cookies work in real browsers and ACS POSTs; CSRF is not disabled app-wide.
- [ ] All SP pods share identical registrations/IdP signing certs/ACS/entityIDs and passed rolling key-rotation tests.
- [ ] Serialization, TTL, data privacy, Redis auth/TLS/ACLs, monitoring, and cleanup are production-ready.
- [ ] No raw SAML payloads, session cookies, secrets, or replayable credentials are logged.
- [ ] Negative tests cover lost cookies, expired/missing requests, wrong tenants, invalid signatures, replay, multi-tab, and Redis outages.

## 15. Review Questions

**1. Why might an AuthnRequest created on POD A not be found when the response arrives at POD B?**  
Because A's local `HttpSession` or in-memory cache does not automatically share state with B. You need shared sessions or a distributed repository while preserving browser/transaction binding.

**2. Does Spring Session Redis require modifying `Saml2WebSsoAuthenticationRequestFilter`?**  
Usually no. Spring Session replaces the `HttpSession` backend, so `HttpSessionSaml2AuthenticationRequestRepository` can continue to be used.

**3. Is sharing Redis sessions enough if the browser omits the cookie on the ACS POST?**  
Not enough. The SP needs the cookie/session identifier to look up the right session; inspect SameSite/HTTPS/browsers rather than dropping `InResponseTo`.

**4. Is `CacheSaml2AuthenticationRequestRepository` cluster-ready by default?**  
No. Introduced in Spring Security 6.5, its default cache is in-memory. You must inject a distributed `Cache` via `setCache(...)` and verify cross-pod behavior.

**5. Why can looking up solely by RelayState increase login fixation risk?**  
RelayState only locates a record; it does not prove the callback browser initiated login. An attacker could try transferring a response/state between two browsers.

**6. Are `loadAuthenticationRequest` and `removeAuthenticationRequest` the same?**  
No. `load` reads the record; `remove` deletes/returns it. With a shared cache, ensure single-use semantics and proper concurrency per framework lifecycle.

**7. If a pending request is retrieved from Redis, can the SP skip signature validation?**  
No. Pending state proves a transaction was initiated; the SAMLResponse must still be verified against IdP trust and protocol conditions.

**8. Does a custom repository automatically make post-login authenticated sessions work across pods?**  
No. It manages only pending AuthnRequests. User sessions and `SecurityContext` require shared sessions or a separate mechanism.

**9. What is the single most important multi-node test?**  
Intentionally send the AuthnRequest through POD A and the SAMLResponse callback through POD B; then test replay, lost cookies, wrong browser binding, and concurrent callbacks.

**10. Why can't request TTL mechanically equal session lifetime?**  
Pending requests need to live only for a short login window, whereas authenticated sessions last longer. Overly long TTLs widen abuse windows; overly short TTLs break MFA logins.

## 16. Official Documentation

- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request filter responsibilities, replacing `Saml2AuthenticationRequestRepository`, and RelayState cache warnings.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): request flow, callbacks, registrations, and providers.
- [Spring Security 6.5 — Saml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html): `save`/`load`/`remove` contract.
- [Spring Security 6.5 — CacheSaml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/CacheSaml2AuthenticationRequestRepository.html): class introduced in 6.5, `setCache`, and default in-memory cache warning.
- [Spring Session — Spring Boot Redis Guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): using Redis to share `HttpSession`.
- [Spring Session — Spring Session and Spring Security](https://docs.spring.io/spring-session/reference/guides/java-security.html): Spring Session replacing `HttpSession` and interacting with `SecurityContext`.
- [Spring Session — API / DefaultCookieSerializer](https://docs.spring.io/spring-session/reference/api.html): cookie names, `Secure`, `HttpOnly`, and `SameSite`.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `AuthnRequest`, `Response`, `InResponseTo`, and conditions.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): replay, trust, and callback validation.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet): cookie security, lifecycle, fixation, and hijacking.

**Practical conclusion:** when a `SAMLResponse` may return to a different pod, the SP must retrieve the exact **pending AuthnRequest** initiated by that browser. **Spring Session + shared HttpSession** usually preserves browser binding best when cookies work. **Distributed request caches** solve certain operational/cross-site POST issues, yet demand careful evaluation of login fixation, TTL, single-use atomic consumption, serializers, and SAML validation. The goal is not merely “POD B found a request”: it is **restoring the right transaction and logging in only after all SAML evidence is valid**.